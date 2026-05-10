"""Streamlit chat UI for inderes-research-agent.

Run locally:
    streamlit run ui/app.py

Cloud deployment (single-user, public app, password-gated):
    See ui/DEPLOY.md.

The agent code is identical to the CLI — this module just adds:
- a chat surface,
- a password gate (Streamlit secrets) to limit drive-by access,
- a daily query cap so a leaked password can't burn unlimited Gemini quota,
- bridging from st.secrets to os.environ so oauth.py can pick up
  INDERES_OAUTH_TOKENS_JSON in cloud deployments.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

import streamlit as st
from dotenv import load_dotenv

# IMPORTANT: bridge Streamlit secrets to os.environ BEFORE importing any
# inderes_agent module — oauth.py reads INDERES_OAUTH_TOKENS_JSON at module
# load time and again on every token request, but the env var has to be set
# before the very first call.
def _bridge_secrets_to_env() -> None:
    """Copy each Streamlit secret into os.environ so non-Streamlit code can read it.

    Streamlit secrets aren't auto-exposed as env vars. We do it here so
    `inderes_agent.mcp.oauth` (which reads `os.environ["INDERES_OAUTH_TOKENS_JSON"]`)
    works without depending on Streamlit.

    Locally there's typically no secrets.toml — accessing `st.secrets.items()`
    raises `StreamlitSecretNotFoundError` in that case. We treat that as "no
    secrets to bridge" and continue silently.

    Uses direct assignment (not setdefault) so that if the env var was
    pre-seeded with an empty/stale value somewhere upstream, the secret
    still wins. Also prints a one-liner at startup listing which secret
    keys got bridged — useful when debugging "why isn't my new secret
    being read" issues in the cloud logs.
    """
    try:
        items = list(st.secrets.items())
    except Exception as exc:
        print(f"[secrets] bridge skipped: {exc}", flush=True)
        return  # no secrets.toml configured — fine in local dev
    bridged: list[str] = []
    for key, value in items:
        # Nested TOML tables (like [INDERES_OAUTH_TOKENS]) get serialised to JSON.
        if isinstance(value, dict):
            os.environ[f"{key}_JSON"] = json.dumps(value)
            bridged.append(f"{key}_JSON")
        else:
            os.environ[key] = str(value)
            bridged.append(key)
    # Mask values that look like secrets in the print, but show keys so we
    # can verify the right ones got bridged.
    print(f"[secrets] bridged {len(bridged)} keys: {', '.join(sorted(bridged))}", flush=True)


_bridge_secrets_to_env()

from inderes_agent.cli.repl import ConversationState  # noqa: E402
from inderes_agent.llm.gemini_client import QuotaExhaustedError  # noqa: E402
from inderes_agent.logging import configure_logging  # noqa: E402
from inderes_agent.mcp.inderes_client import prefetch_token  # noqa: E402
from inderes_agent.mcp.oauth import HeadlessAuthError  # noqa: E402
from inderes_agent.observability.narrate import write_narrative  # noqa: E402
from inderes_agent.observability.run_log import (  # noqa: E402
    RUNS_ROOT,
    attach_console_log_handler,
    detach_console_log_handler,
    new_run_dir,
    write_run,
)
from inderes_agent.orchestration.router import classify_query  # noqa: E402
from inderes_agent.orchestration.synthesis import synthesize  # noqa: E402
from inderes_agent.orchestration.workflows import run_planner, run_workflow  # noqa: E402

# Trading Desk visual layer — pure cosmetics, no agent-pipeline impact.
# `streamlit run ui/app.py` puts `ui/` on sys.path (not the repo root), so we
# import the sibling module by its bare name. Works the same in cloud + local.
from components import (  # noqa: E402
    inject_theme,
    render_titlebar,
    render_ticker,
    render_disclaimer,
    render_routing_card,
    render_metrics_row,
    render_agent_row,
    render_agent_output,
    render_statusbar,
    render_personas_panel,
    render_about_panel,
    render_full_narrative,
    render_sidebar_disclaimer,
    render_github_link,
    render_lead_answer,
    render_followup_chips,
    render_recommendation_badge,
    render_paattely_b,
    render_plan_expander,
    render_timeline_strip,
    render_activity_panel,
    build_conflict_html,
    render_perustelut_box,
    extract_perustelut,
    CustomStatus,
    PERSONAS,
    DOMAIN_VERBS_FI,
)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    # Tab title — kept tight (full repo name was too long and visually
    # clashed with the deployment URL which deliberately starts with
    # "not-inderes-..."). 'Inderes//Agent' matches the brand mark used
    # throughout the UI and decks.
    page_title="Inderes//Agent",
    # Favicon — orange diamond, same glyph as the chat-assistant
    # avatar. The diamond is LEAD's persona mark used throughout
    # the UI and decks; using it as the favicon ties the browser-tab
    # identity to the brand mark.
    page_icon="🔶",
    layout="wide",
    # Sidebar collapsed by default (redesign iter-2: Grok-like empty state).
    # User can re-open via Streamlit's native sidebar arrow. The right-side
    # activity panel is the new home for "agent log" content; the left
    # sidebar mostly carries chrome (HUOM, KIELI, KESKUSTELU buttons).
    initial_sidebar_state="collapsed",
)

# Trading Desk theme — must run right after set_page_config so the CSS lands
# before any other widget is rendered.
inject_theme()


# ---------------------------------------------------------------------------
# Password gate REMOVED 2026-05-07 per user request. The gate was triggering
# unwanted re-prompts every time the page rerendered with a new query param
# (?panel=open caused a "page reload" that bounced through the password
# screen). The daily query cap below still applies as the only damage-limit
# mechanism.


# ---------------------------------------------------------------------------
# Daily query cap (limits damage if password leaks)
# ---------------------------------------------------------------------------

_QUERY_COUNTER_PATH = Path(os.environ.get("INDERES_AGENT_CACHE", "/tmp/inderes_agent")) / "query_count.json"


def _query_count_today() -> int:
    today = date.today().isoformat()
    if _QUERY_COUNTER_PATH.exists():
        try:
            data = json.loads(_QUERY_COUNTER_PATH.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return int(data.get("count", 0))
        except Exception:
            pass
    return 0


def _increment_query_count() -> int:
    today = date.today().isoformat()
    count = _query_count_today() + 1
    _QUERY_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _QUERY_COUNTER_PATH.write_text(
        json.dumps({"date": today, "count": count}), encoding="utf-8"
    )
    return count


def _daily_cap() -> int:
    raw = os.environ.get("DAILY_QUERY_CAP", "")
    try:
        return int(raw) if raw else 0  # 0 = no cap
    except ValueError:
        return 0


def _enforce_daily_cap_or_stop() -> None:
    cap = _daily_cap()
    if cap <= 0:
        return
    used = _query_count_today()
    if used >= cap:
        st.error(
            f"Päivittäinen kyselyraja täynnä ({used}/{cap}). "
            "Kokeile huomenna uudelleen."
        )
        st.stop()


# ---------------------------------------------------------------------------
# Title and header — Trading Desk chrome
# ---------------------------------------------------------------------------

# Language switcher: ?lang=fi / ?lang=en in the URL (clicked from the
# titlebar's tiny FI // EN links) writes ui_lang into session_state and
# clears the query param so deep-link sharing stays clean. The default is
# Finnish — the primary audience is Nordic and the brand is Finnish-first.
_lang_qp = st.query_params.get("lang")
if _lang_qp in ("fi", "en"):
    if st.session_state.get("ui_lang") != _lang_qp:
        st.session_state.ui_lang = _lang_qp
    # Clean URL after the click so subsequent shares don't pin a language.
    try:
        del st.query_params["lang"]
    except KeyError:
        pass

_lang = st.session_state.get("ui_lang", "fi")
render_titlebar(_lang)
# render_ticker() — disabled: distracting, replace with a real feed if/when one's available

# Hero / equation block: shown ONLY on the empty state (Grok-like clean entry).
# Once the user has asked anything, the hero collapses to keep the chat the
# focus and avoid repeating the marketing on every page. The feature toggles
# (valuation, plan-then-execute, model tier) are rendered INLINE here so
# first-time users can configure them without hunting in the sidebar — the
# sidebar version of the same controls is rendered only after the first
# query (see sidebar block below) to avoid Streamlit duplicate-key errors.
if not st.session_state.get("history"):
    render_disclaimer(_lang)
    from components import render_feature_toggles
    render_feature_toggles(_lang)


# ---------------------------------------------------------------------------
# Trading Desk chat avatars
# ---------------------------------------------------------------------------
# Streamlit's chat_message(avatar=...) only accepts URLs, image paths, or
# *real* emoji codepoints — Unicode dingbats like ❯ (U+276F) or ◆ (U+25C6)
# are NOT detected as emoji and Streamlit treats them as file paths,
# crashing with FileNotFoundError. So we use proper emoji that match the
# Trading Desk theme as closely as the emoji vocabulary allows:
#   💼 — briefcase, the "research desk" side
#   🔶 — orange diamond, matches LEAD's amber ◆ glyph

USER_AVATAR = "👤"
ASSISTANT_AVATAR = "🔶"


# ---------------------------------------------------------------------------
# Public-safe error rendering
# ---------------------------------------------------------------------------

DEMO_VIDEO_URL = "https://www.youtube.com/watch?v=2lw6lC2ho_c"

# Help-request counter is persisted as a separate file in the same gist
# that already mirrors tokens.json, so we don't need a second secret.
HELP_REQUESTS_GIST_FILE = "help_requests.json"


def _read_help_request_state() -> dict:
    """Read the recovery-requests counter from the gist mirror.

    Best-effort: if the gist isn't configured, the file doesn't exist,
    or the GitHub API hiccups, returns zeros so the UI still renders.
    """
    gist_id = os.environ.get("INDERES_TOKENS_GIST_ID", "").strip()
    gh_token = os.environ.get("INDERES_TOKENS_GH_TOKEN", "").strip()
    if not (gist_id and gh_token):
        return {"count": 0, "last_at": None}

    try:
        import httpx
        r = httpx.get(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"token {gh_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            return {"count": 0, "last_at": None}
        files = r.json().get("files", {}) or {}
        content = (files.get(HELP_REQUESTS_GIST_FILE) or {}).get("content")
        if not content:
            return {"count": 0, "last_at": None}
        data = json.loads(content)
        return {
            "count": int(data.get("count", 0)),
            "last_at": data.get("last_request_at"),
        }
    except Exception as exc:
        log.warning("help_request_state_read_failed %s", exc)
        return {"count": 0, "last_at": None}


def _record_help_request() -> tuple[bool, dict]:
    """Increment the counter and push back to the gist. Returns (ok, state).

    On any failure returns (False, current_state_or_zeros) so the caller
    can show a soft "yritä uudelleen" hint without losing the prior
    count from the UI.
    """
    gist_id = os.environ.get("INDERES_TOKENS_GIST_ID", "").strip()
    gh_token = os.environ.get("INDERES_TOKENS_GH_TOKEN", "").strip()
    if not (gist_id and gh_token):
        return False, {"count": 0, "last_at": None}

    current = _read_help_request_state()
    from datetime import datetime, timezone
    new_payload = {
        "count": current["count"] + 1,
        "last_request_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        import httpx
        r = httpx.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"token {gh_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
            json={
                "files": {
                    HELP_REQUESTS_GIST_FILE: {
                        "content": json.dumps(new_payload, indent=2),
                    },
                },
            },
            timeout=10.0,
        )
        if r.status_code in (200, 201):
            return True, {
                "count": new_payload["count"],
                "last_at": new_payload["last_request_at"],
            }
        log.warning(
            "help_request_state_write_failed status=%d body=%s",
            r.status_code,
            r.text[:200],
        )
    except Exception as exc:
        log.warning("help_request_state_write_exception %s", exc)
    return False, current


def _format_timestamp_fi(iso_ts: str | None) -> str:
    """Format an ISO UTC timestamp as a Finnish absolute timestamp.

    Converts to Europe/Helsinki local time and formats as `4.5.2026 klo 20.34`.
    Used for the auth-expired card's "Viimeisin" caption — visitors find
    an actual timestamp easier to reason about than relative text like
    "5 min sitten" (especially across day boundaries).
    """
    if not iso_ts:
        return ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ts_utc = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        ts_local = ts_utc.astimezone(ZoneInfo("Europe/Helsinki"))
        # Use %d.%m.%Y to keep cross-platform — leading zeros are fine,
        # %-d / %#d are platform-specific and break on either Linux or
        # Windows depending on which we pick.
        return ts_local.strftime("%d.%m.%Y klo %H.%M")
    except Exception:
        return ""


def _get_cached_help_state(max_age_s: int = 30) -> dict:
    """Get the help-request state, caching for max_age_s seconds in
    session_state. Avoids hammering the gist API on every Streamlit
    rerun (the page rerenders every time the user interacts with
    anything, including hovering certain components).
    """
    cache = st.session_state.get("_help_state_cache")
    cache_ts = st.session_state.get("_help_state_cache_ts", 0.0)
    if cache is not None and (time.time() - cache_ts) < max_age_s:
        return cache
    fresh = _read_help_request_state()
    st.session_state["_help_state_cache"] = fresh
    st.session_state["_help_state_cache_ts"] = time.time()
    return fresh


def _render_auth_expired() -> None:
    """Generic message for expired Inderes auth — safe to show to anyone.

    The Streamlit app sits behind a password gate, but anything we render
    is potentially visible to whoever knows the password (or anyone who
    eventually gets past it). So this message doesn't expose internal
    paths, scripts, repo names, or implementation details.

    Adds three affordances on top of the bare error:
    - An embedded demo video so a first-time visitor can still see what
      the tool does even when it can't run live.
    - A "Pyydä apua" button that increments a counter persisted in the
      gist mirror — operator sees the counter rise and knows people are
      waiting.
    - The counter itself rendered as a metric so visitors get social
      proof ("you're not the first") and the operator gets a glanceable
      activity gauge.

    Anti-spam: per-session_state flag prevents re-clicking within the
    same browser session. Cross-session abuse is mitigated by the
    password gate; this is a hobby-project tradeoff.
    """
    st.error(
        "🔴  **Järjestelmä alhaalla.**\n\n"
        "Yhteys Inderesin dataan täytyy autentikoida uudelleen. "
        "Sillä välin voit katsoa alla olevan demovideon ja pyytää "
        "yhteyden korjaamista yhdellä klikkauksella. ↓"
    )

    try:
        st.video(DEMO_VIDEO_URL)
    except Exception as exc:
        log.warning("demo_video_embed_failed %s", exc)
        st.markdown(f"[Katso demo YouTubessa]({DEMO_VIDEO_URL})")

    st.markdown("---")

    state = _get_cached_help_state()

    left, right = st.columns([3, 2], vertical_alignment="center")

    with left:
        if st.session_state.get("_help_request_sent"):
            st.success(
                "✓ Pyyntösi on tallennettu. Laitan yhteyden takaisin "
                "pystyyn mahdollisimman pian.\n\n"
                f"Tämä oli pyyntö **#{state['count']}** palvelun elinaikana."
            )
        else:
            if st.button(
                "📧 Pyydä yhteyden korjaamista",
                type="primary",
                use_container_width=True,
            ):
                ok, new_state = _record_help_request()
                if ok:
                    st.session_state["_help_request_sent"] = True
                    st.session_state["_help_state_cache"] = new_state
                    st.session_state["_help_state_cache_ts"] = time.time()
                    st.rerun()
                else:
                    st.warning(
                        "Pyynnön tallennus ei mennyt läpi. "
                        "Yritä hetken päästä uudelleen."
                    )

    with right:
        st.metric(
            label="Apupyyntöjä yhteensä",
            value=str(state["count"]),
        )
        if state["last_at"]:
            st.caption(f"Viimeisin: {_format_timestamp_fi(state['last_at'])}")
        else:
            st.caption("Ei vielä pyyntöjä")


# ---------------------------------------------------------------------------
# One-time setup (per Streamlit session)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Authenticating with Inderes…")
def _bootstrap_auth() -> bool:
    """Auth-bootstrap step, cached so we don't re-auth on every rerun.

    IMPORTANT: do NOT call any st.* widget functions (button, text_area,
    metric, video, …) inside this function. Streamlit's cache decorator
    prevents widgets from re-rendering on cache hits, so widgets here
    would either warn or silently disappear after the first call. The
    auth-expired UI is rendered in the *caller* outside the cache.
    """
    load_dotenv()
    configure_logging()
    prefetch_token()
    return True


def _bootstrap() -> None:
    """Top-level bootstrap orchestrator. Either succeeds quietly or
    renders the auth-expired UI (with widgets) and st.stop()s.

    Uses a session-state flag to remember "auth is broken" so we don't
    keep retrying the OAuth refresh on every Streamlit rerun while the
    visitor sits on the help-request screen.
    """
    if not st.session_state.get("_auth_broken"):
        try:
            _bootstrap_auth()
            return  # success, let the rest of the app render
        except HeadlessAuthError:
            log.exception("oauth_headless_at_bootstrap")
            st.session_state["_auth_broken"] = True
            # fall through to render the auth-expired UI

    _render_auth_expired()
    st.stop()


_bootstrap()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "state" not in st.session_state:
    st.session_state.state = ConversationState()
if "history" not in st.session_state:
    # List of {role: "user"|"assistant", content: str, run_dir: str | None}
    st.session_state.history = []


# ---------------------------------------------------------------------------
# Trace rendering helper
# ---------------------------------------------------------------------------

def _render_subagent_text(run_dir: Path, sa: dict) -> None:
    """Render a subagent's text. Image extraction is not supported in this
    build (`agent_framework_gemini` doesn't surface inline_data parts), so
    we just render the markdown directly. `extract_parts` has already
    stripped any dangling `![alt](...)` references that would render as
    broken icons.
    """
    text = sa.get("text") or "_(empty response)_"
    st.markdown(text)


def render_trace_expander(run_dir: Path) -> None:
    """Show routing + per-subagent trace inside a collapsed expander at the
    bottom of the assistant message.

    The whole agent activity log lives behind one outer expander that's closed
    by default — when you open it, you see everything inline (routing card,
    metrics, each agent's full structured output starting with its **Ajatus:**
    line). No nested per-agent expanders inside; the Ajatus row makes it easy
    to scan the agent's reasoning at a glance even with long outputs below.

    The old "Täydellinen ajoloki" full-narrative renderer is removed — it
    rendered the same data twice and was the dominant slowdown as chat
    history grew. narrative.md is still written to disk by the pipeline.
    """
    routing_path = run_dir / "routing.json"
    meta_path = run_dir / "meta.json"
    lang = st.session_state.get("ui_lang", "fi")

    _trace_label = (
        "🔍 Agenttien toimintaloki" if lang == "fi" else "🔍 Agent activity log"
    )
    with st.expander(_trace_label, expanded=False):
        if routing_path.exists():
            r = json.loads(routing_path.read_text(encoding="utf-8"))
            render_routing_card(r, lang)

        # Big metric cards from QUANT's structured output (if present —
        # silently no-ops when the subagent JSON has no `metrics` block).
        render_metrics_row(run_dir, lang)

        if meta_path.exists():
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            cols = st.columns(4)
            cols[0].metric("Duration", f"{m.get('duration_seconds', 0):.1f} s")
            cols[1].metric("Subagents", m.get("subagent_count", 0))
            cols[2].metric("Errors", m.get("subagent_errors", 0))
            cols[3].metric("Fallbacks", m.get("fallback_events", 0))

            # Stage-level timing breakdown — planner/fanout/conflict-detector/lead
            stage = m.get("stage_timings") or {}
            if stage:
                bits: list[str] = []
                # Planner timing comes from plan.json (run_log persists it
                # there, not in stage_timings yet — read it here for the
                # row when it exists).
                _plan_path_for_timing = run_dir / "plan.json"
                if _plan_path_for_timing.exists():
                    try:
                        _pblob = json.loads(_plan_path_for_timing.read_text(encoding="utf-8"))
                        _plan_dur = _pblob.get("duration_seconds")
                        if _plan_dur:
                            bits.append(
                                f"suunnitelma: <strong>{_plan_dur:.2f}s</strong>"
                                if lang == "fi"
                                else f"plan: <strong>{_plan_dur:.2f}s</strong>"
                            )
                    except (OSError, json.JSONDecodeError):
                        pass
                if (v := stage.get("fanout_seconds")) is not None:
                    bits.append(
                        f"fan-out: <strong>{v:.2f}s</strong>"
                        if lang == "fi"
                        else f"fan-out: <strong>{v:.2f}s</strong>"
                    )
                if (v := stage.get("conflict_detector_seconds")) is not None:
                    bits.append(f"konflikti-detektori: <strong>{v:.2f}s</strong>"
                                if lang == "fi" else f"conflict-detector: <strong>{v:.2f}s</strong>")
                if (v := stage.get("lead_seconds")) is not None:
                    bits.append(f"LEAD-synteesi: <strong>{v:.2f}s</strong>"
                                if lang == "fi" else f"LEAD synthesis: <strong>{v:.2f}s</strong>")
                if bits:
                    label = "Vaihekohtainen kesto" if lang == "fi" else "Per-stage timing"
                    st.markdown(
                        f'<div style="font-size:13px; color: var(--ia-faint, #888); '
                        f'margin: 4px 0 8px 0;">{label}: ' + " · ".join(bits) + "</div>",
                        unsafe_allow_html=True,
                    )

        # Lead planner card (when "Käytä pidempää suunnittelua" was on).
        # Sits ABOVE the per-subagent rows because the planner runs
        # FIRST chronologically. Silent no-op when plan.json missing.
        plan_path = run_dir / "plan.json"
        if plan_path.exists():
            try:
                _plan_blob = json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _plan_blob = None
            if _plan_blob:
                from components import _build_planner_card_html
                _planner_html = _build_planner_card_html(_plan_blob, lang)
                if _planner_html:
                    st.html(_planner_html)

        for sub_path in sorted(run_dir.glob("subagent-*.json")):
            sa = json.loads(sub_path.read_text(encoding="utf-8"))
            render_agent_row(sa, lang)
            if sa.get("error"):
                st.error(sa["error"])
            else:
                render_agent_output(sa.get("text"))
                _render_tool_calls(sa.get("tool_calls") or [], lang)

        # LEAD synthesis card — chronological LAST step. Surfaces LEAD's
        # "Ajatus" (= Perustelut callout) + "Yhteenveto" so the bottom
        # log mirrors the right activity panel's full agent timeline:
        # planner → subagents → LEAD synthesis. Silent no-op if synth
        # is missing (very early-stage runs).
        if (run_dir / "synthesis.txt").exists():
            from components import _build_lead_synthesis_card_html
            _lead_synth_html = _build_lead_synthesis_card_html(run_dir, lang)
            if _lead_synth_html:
                st.html(_lead_synth_html)


def _render_tool_calls(tool_calls: list[dict], lang: str) -> None:
    """Render the subagent's tool calls — what the MCP tools actually returned.

    BACKLOG #10 provenance threading: gives the user transparency into the
    structured ground-truth the agent saw. Each tool call shows args + a
    compact summary of items returned, with the full JSON behind a nested
    `<details>` block.
    """
    if not tool_calls:
        return
    label = (
        f"🔧 Työkalukutsut ({len(tool_calls)})"
        if lang == "fi"
        else f"🔧 Tool calls ({len(tool_calls)})"
    )
    with st.expander(label, expanded=False):
        for i, tc in enumerate(tool_calls, 1):
            name = tc.get("name") or "<unknown>"
            args = tc.get("arguments") or {}
            err = tc.get("error")
            count = tc.get("item_count")
            names = tc.get("item_names") or []
            result_text = tc.get("result_text") or ""

            args_repr = json.dumps(args, ensure_ascii=False)
            if len(args_repr) > 200:
                args_repr = args_repr[:200] + "…"
            st.markdown(f"**{i}. `{name}`** &nbsp; `{args_repr}`", unsafe_allow_html=True)

            if err:
                st.error(err)
                continue

            if count is not None:
                preview_n = min(20, len(names))
                preview = ", ".join(names[:preview_n])
                more = f" *(+{len(names) - preview_n} more)*" if len(names) > preview_n else ""
                lbl = "tulosta" if lang == "fi" else "items"
                st.caption(f"{count} {lbl}: {preview}{more}")
            elif result_text:
                head = result_text[:300].replace("\n", " ")
                st.caption(head + ("…" if len(result_text) > 300 else ""))
            else:
                st.caption("(empty)" if lang == "en" else "(tyhjä)")
            # Full raw JSON is in run_dir/subagent-NN-*.json; not surfaced in
            # the UI to keep the panel scannable when fan-out is wide.


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    _lang_side = st.session_state.get("ui_lang", "fi")

    # Red disclaimer at the very top — sets expectations before anything else
    render_sidebar_disclaimer(_lang_side)

    # Project description
    render_about_panel(_lang_side)

    # GitHub CTA — link out for more info
    render_github_link(_lang_side)

    # Agent roster
    render_personas_panel(_lang_side)

    # Conversation controls
    _conv_h = "KESKUSTELU" if _lang_side == "fi" else "CONVERSATION"
    _clear_lbl = "🗑️ Tyhjennä keskustelu" if _lang_side == "fi" else "🗑️ Clear chat"
    st.markdown(f'<div class="ia-side-h">{_conv_h}</div>', unsafe_allow_html=True)
    if st.button(_clear_lbl, use_container_width=True):
        st.session_state.state = ConversationState()
        st.session_state.history = []
        st.rerun()

    # Alternative-valuation toggle — opt-in extension on top of the
    # default research flow. When enabled, every company-specific query
    # also dispatches the `valuation` subagent which fetches BVPS/ROE,
    # decides k/g with rationale, and a deterministic Python engine
    # computes the user's own fair value. LEAD's synthesis includes a
    # `Oma malli vs Inderes` comparison section.
    # Feature toggles — rendered ONLY after the user has asked their
    # first question. On the idle screen the same controls live in the
    # hero (see `render_feature_toggles`), so we'd hit Streamlit's
    # duplicate-key error if we rendered both unconditionally. The hero
    # is the natural first-time-config affordance; the sidebar takes
    # over once the chat is active.
    _show_sidebar_toggles = bool(st.session_state.get("history"))

    _val_h = "MOODI" if _lang_side == "fi" else "MODE"
    _val_label = (
        "Käytä vaihtoehtoista arvonmääritystä"
        if _lang_side == "fi"
        else "Use alternative valuation"
    )
    _val_help = (
        "Lisää oma Greenwald-Gordon -malli vastauksen rinnalle. "
        "Toimii yhtiökyselyihin (esim. 'tee arvonmääritys Sammosta'). "
        "Lisää yhden agentin ajon — kasvattaa kestoa ~3–5 s."
        if _lang_side == "fi"
        else "Adds a Greenwald-Gordon model alongside the answer. "
        "Works for company queries. Adds ~3–5 s per query."
    )
    if _show_sidebar_toggles:
        st.markdown(f'<div class="ia-side-h">{_val_h}</div>', unsafe_allow_html=True)
        st.checkbox(
            _val_label,
            key="valuation_mode_on",
            help=_val_help,
        )

    # Plan-then-execute toggle — adds a strategic planning step before
    # subagent dispatch. The planner reads the routing decision and
    # writes per-subagent guidance + comparison axis + watchouts. Then
    # subagents see this guidance in their prompts. Mostly useful for
    # complex / nuanced queries; on simple ones it adds latency without
    # changing much. Default OFF to preserve baseline cost + latency.
    _plan_label = (
        "🧠 Käytä pidempää suunnittelua"
        if _lang_side == "fi"
        else "🧠 Use deeper planning"
    )
    _plan_help = (
        "Lisää pre-dispatch -suunnitteluvaiheen: LEAD kirjoittaa lyhyen "
        "strukturoidun suunnitelman ennen subagenttien dispatchia. "
        "Subagentit saavat tämän kontekstin promptiinsa, joten haut "
        "ovat tarkempia. Lisää ~5–10 s + ~20 % kustannus.\n\n"
        "Hyödyllinen monimutkaisille kyselyille (vertailut, vivahteikkaat "
        "kysymykset, tutkimukselliset 'miksi' -kysymykset)."
        if _lang_side == "fi"
        else "Adds a pre-dispatch planning step: LEAD writes a short "
        "structured plan before subagents are dispatched. Subagents "
        "receive this context in their prompts, so their fetches are "
        "more focused. Adds ~5–10 s + ~20 % cost.\n\n"
        "Useful for complex queries (comparisons, nuanced questions, "
        "exploratory 'why' questions)."
    )
    if _show_sidebar_toggles:
        st.checkbox(
            _plan_label,
            key="plan_then_execute_on",
            help=_plan_help,
        )

    # LEAD-tier selector — opt-in upgrade for synthesis quality.
    # Default "Vakio" keeps everything on Flash Lite (paid tier base
    # cost ~$0.015/query). "Tarkka LEAD" swaps the synthesis call to
    # Gemini 2.5 Pro (paid tier ~5x cost on the LEAD step, ~$0.07
    # extra per query). Subagents stay on Flash Lite either way —
    # they're data-gathering agents, Flash handles tool-calling well.
    _tier_h = "MALLIN VALINTA" if _lang_side == "fi" else "MODEL SELECTION"
    _tier_options_fi = [
        "Vakio (Gemini 3.1 Flash Lite)",
        "Pro LEAD (Gemini 2.5 Pro)",
        "Pro kaikki (Gemini 2.5 Pro)",
    ]
    _tier_options_en = [
        "Standard (Gemini 3.1 Flash Lite)",
        "Pro LEAD (Gemini 2.5 Pro)",
        "Pro all (Gemini 2.5 Pro)",
    ]
    _tier_options = _tier_options_fi if _lang_side == "fi" else _tier_options_en
    _tier_help = (
        "**Miksi vaihtaa Pro-malliin?**\n\n"
        "Pro (Gemini 2.5 Pro) on Flash Liteä huomattavasti vivahteikkaampi "
        "vertailussa, syy-seuraus-päättelyssä ja monimutkaisten kysymysten "
        "purkamisessa. Vakio (Flash Lite) on nopeampi ja halvempi, riittää "
        "useimpiin yhtiökyselyihin.\n\n"
        "**Vaikutukset:**\n\n"
        "• **Vakio (Flash Lite):** ~$0,015/kysely, latenssi 10–20 s.\n\n"
        "• **Pro LEAD:** vain LEAD-synteesi + suunnittelija Pro:lla, "
        "subagentit Flash Litellä. ~$0,07 lisää/kysely, +5–10 s. "
        "Suositeltu vivahteikkaisiin kysymyksiin.\n\n"
        "• **Pro kaikki:** KAIKKI agentit Pro:lla — subagentit, "
        "conflict-detector, suunnittelija, LEAD. ~$0,30 lisää/kysely "
        "(~20× vakio), latenssi +15–25 s. Käytä kun jokainen sana "
        "ratkaisee."
        if _lang_side == "fi"
        else "**Why switch to Pro?**\n\n"
        "Pro (Gemini 2.5 Pro) is significantly more nuanced than Flash "
        "Lite at comparison, causal reasoning, and unpacking complex "
        "questions. Standard (Flash Lite) is faster and cheaper, "
        "sufficient for most company queries.\n\n"
        "**Impact:**\n\n"
        "• **Standard (Flash Lite):** ~$0.015/query, latency 10–20 s.\n\n"
        "• **Pro LEAD:** only LEAD synthesis + planner on Pro, "
        "subagents on Flash Lite. ~$0.07 extra/query, +5–10 s. "
        "Recommended for nuanced queries.\n\n"
        "• **Pro all:** ALL agents on Pro — subagents, conflict-"
        "detector, planner, LEAD. ~$0.30 extra/query (~20× baseline), "
        "latency +15–25 s. Use when every word matters."
    )
    if _show_sidebar_toggles:
        st.markdown(f'<div class="ia-side-h">{_tier_h}</div>', unsafe_allow_html=True)
        st.radio(
            _tier_h,
            options=_tier_options,
            key="lead_tier",
            help=_tier_help,
            label_visibility="collapsed",
        )

    # Recent runs
    _runs_h = "VIIMEISIMMÄT AJOT" if _lang_side == "fi" else "RECENT RUNS"
    _runs_cap = (
        "Jokainen ajo tallentaa kysymyksen, reitityksen, subagenttien vastaukset "
        "ja aikajanan levylle. Kahdeksan viimeisintä alla."
        if _lang_side == "fi"
        else "Each run saves the query, routing, subagent outputs, and timeline "
        "to disk. The eight most recent are listed below."
    )
    st.markdown(f'<div class="ia-side-h">{_runs_h}</div>', unsafe_allow_html=True)
    st.caption(_runs_cap)
    if RUNS_ROOT.exists():
        recent = sorted(RUNS_ROOT.iterdir(), reverse=True)[:8]
        for d in recent:
            qfile = d / "query.txt"
            label = qfile.read_text(encoding="utf-8").strip() if qfile.exists() else d.name
            label = label[:60] + ("…" if len(label) > 60 else "")
            st.caption(f"`{d.name[:15]}` — {label}")
    else:
        st.caption("Ei vielä ajoja." if _lang_side == "fi" else "No runs yet.")

    # Activity panel is now opened by clicking the Aikajana strip on a
    # message (?panel=open in the URL). This sidebar toggle is kept as a
    # fallback for keyboard / non-mouse users who can't click the strip.
    if st.session_state.get("activity_panel_open"):
        _close_label = "✕ Sulje aktiviteettiloki" if _lang_side == "fi" else "✕ Close activity log"
        if st.button(_close_label, use_container_width=True, key="panel_close_btn"):
            st.session_state.activity_panel_open = False
            st.query_params.clear()
            st.rerun()

    # Daily quota progress bar removed from the sidebar — the cap still
    # applies (enforced before each query in `_enforce_daily_cap_or_stop`),
    # we just don't surface the count in the chrome anymore.

    # Logs path note
    runs_dir_display = str(RUNS_ROOT)
    if _lang_side == "fi":
        storage_note = (
            "Lokit ephemeraalisessa container-storagessa — nollautuvat "
            "uudelleenkäynnistyksessä."
            if runs_dir_display.startswith("/tmp")
            else "Lokit tallennetaan pysyvästi."
        )
        st.caption(f"Logit: `{runs_dir_display}`. {storage_note}")
    else:
        storage_note = (
            "Per-run logs saved to ephemeral container storage — they reset on "
            "every container restart."
            if runs_dir_display.startswith("/tmp")
            else "Per-run logs saved persistently."
        )
        st.caption(f"Logs at `{runs_dir_display}`. {storage_note}")


# ---------------------------------------------------------------------------
# Render past history
# ---------------------------------------------------------------------------

for msg in st.session_state.history:
    avatar = ASSISTANT_AVATAR if msg["role"] == "assistant" else USER_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        # LEAD answers go through render_lead_answer so the
        # **💭 Perustelut:** callout gets its amber styling. User messages
        # are plain markdown.
        if msg["role"] == "assistant":
            run_dir = Path(msg["run_dir"]) if msg.get("run_dir") else None
            # Inderes recommendation badge — only renders if QUANT surfaced
            # a recommendation in this run; silently no-ops otherwise.
            if run_dir is not None:
                render_recommendation_badge(run_dir)
                # Aikajana strip — collapsed timeline summary above the answer
                # (redesign §6.3). Reads meta.json; silently no-ops if missing.
                render_timeline_strip(run_dir, lang=st.session_state.get("ui_lang", "fi"))

            # Order per user feedback (2026-05-07): Päättely TOP, then
            # Perustelut (own box like subagent Ajatus), then answer body.
            # First extract the Perustelut callout from the text so we can
            # render it as a separate box below Päättely.
            _lang_main = st.session_state.get("ui_lang", "fi")
            _cleaned_text, _perustelut_body = extract_perustelut(msg["content"])

            # 1a. 🧠 Suunnitelma (plan-then-execute output, expander).
            #     Renders FIRST chronologically — the plan was the
            #     pre-dispatch decision, before subagents fired. Silently
            #     no-ops when plan.json is missing (= toggle was off).
            if run_dir is not None:
                render_plan_expander(run_dir, lang=_lang_main)

            # 1b. 🧠 Päättely (deeper reasoning, expander; first because the
            #    user wants the work shown before the meta-summary).
            #    The conflict callout — when there are actual disagreements
            #    in conflicts.json — is embedded INSIDE this expander now,
            #    above the prose body, per user feedback 2026-05-07.
            if run_dir is not None:
                _paattely_path = run_dir / "paattely.json"
                _conflict_html_main = build_conflict_html(run_dir, lang=_lang_main)
                _paattely_parsed = None
                if _paattely_path.exists():
                    try:
                        _paattely_blob = json.loads(_paattely_path.read_text(encoding="utf-8"))
                        _paattely_parsed = _paattely_blob.get("parsed")
                    except (OSError, json.JSONDecodeError):
                        _paattely_parsed = None
                render_paattely_b(
                    _paattely_parsed,
                    lang=_lang_main,
                    conflict_html=_conflict_html_main,
                )

            # 2. 💭 Perustelut (meta-summary, own box).
            render_perustelut_box(_perustelut_body, lang=_lang_main)

            # 3. Answer body (Perustelut already extracted out of it).
            render_lead_answer(_cleaned_text)

            # 4. Time-series charts (📊 Aikasarjat) — additive context
            # alongside LEAD's tables. Parses QUANT's get-fundamentals
            # + get-inderes-estimates results into Plotly line charts.
            # Silent no-op when no QUANT data or insufficient points
            # (< 3 actuals per metric).
            if run_dir is not None:
                from charts import render_time_series_charts
                render_time_series_charts(run_dir, lang=_lang_main)

            # Followup question chips — extracted from the LEAD synthesis
            # itself; clicking one writes to st.session_state.pending_query
            # and triggers a rerun that submits it as a new query.
            render_followup_chips(
                msg["content"],
                run_dir_name=(run_dir.name if run_dir else f"hist{id(msg)}"),
            )
            if run_dir is not None:
                render_trace_expander(run_dir)
        else:
            st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Right-side activity panel (redesign §6.1 option A) — renders if the user
# toggled "📊 Aktiviteettiloki paneelina" in the sidebar. Anchored to the
# latest run dir. Position:fixed via CSS; main content shifts left via the
# `:has()` rule in theme.css.
# ---------------------------------------------------------------------------

# Activity panel state is held in session_state directly (set by the
# Streamlit button in render_timeline_strip). Avoiding URL-navigation
# patterns because they cause a hard reload that can wipe state.
_panel_tab = st.session_state.get("_panel_tab", "summary")
if _panel_tab not in {"summary", "agents", "tools", "conflicts"}:
    _panel_tab = "summary"

if st.session_state.get("activity_panel_open"):
    _state = st.session_state.get("state")
    _last_run_dir = getattr(_state, "last_run_dir", None) if _state else None
    if _last_run_dir:
        from pathlib import Path as _P
        render_activity_panel(
            _P(_last_run_dir),
            lang=st.session_state.get("ui_lang", "fi"),
            active_tab=_panel_tab,
        )


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

async def run_pipeline(query: str, state: ConversationState, status) -> tuple[str, Path]:
    """Execute the full router → workflow → synthesis pipeline with status updates."""
    run_dir = new_run_dir()
    handler = attach_console_log_handler(run_dir)
    t0 = time.time()

    def _persona_chip(domain_value: str) -> str:
        """Render `▲ QUANT` (or whichever) with its persona color."""
        code = domain_value.upper()
        p = PERSONAS.get(code, {"glyph": "•", "color": "#888"})
        return (
            f'<span style="color:{p["color"]}; font-weight:600">'
            f'{p["glyph"]} {code}</span>'
        )

    # Narration voice: consistent 3rd-person describing what the SYSTEM
    # does — like a sports commentator. Avoids the earlier mix of 1st-
    # person ("Tunnistan…", "Käynnistän…") and passive voice
    # ("Reititys valmis…"). Each phase has a "starting" line + a
    # "completed" line so the user sees both the activity and the
    # outcome with consistent ✓/❌/… markers.
    _ui_lang_now = st.session_state.get("ui_lang", "fi")
    _fi = _ui_lang_now == "fi"
    def _t(fi: str, en: str) -> str:
        return fi if _fi else en

    try:
        # Phase 1: routing
        status.write(_t(
            "🧭 Reitittäjä tutkii millaisia agentteja kysymys vaatii…",
            "🧭 Router deciding which agents this query needs…",
        ))
        ctx = ", ".join(state.last_companies) if state.last_companies else ""
        ctx_hint = f"previous turn discussed: {ctx}" if ctx else ""
        classification = await classify_query(query, conversation_context=ctx_hint)
        if not classification.companies and state.last_companies:
            classification.companies = state.last_companies

        # Alternative-valuation opt-in: when the user has the sidebar toggle
        # on AND the query targets a real company AND the query has clear
        # valuation intent, append VALUATION to the dispatch list. We also
        # force-include QUANT (Inderes' target/recommendation) so LEAD has
        # both sides for the "Oma malli vs Inderes" comparison.
        #
        # The valuation-intent gate (added 2026-05-09) prevents toggle
        # leakage: previously, ANY company-mentioning query would fire
        # valuation when the toggle was on, including purely qualitative
        # questions like "selitä mistä Nordean kannattavuus tulee" — the
        # user got an unwanted Greenwald-Gordon table. The heuristic in
        # router.query_has_valuation_intent() restricts firing to queries
        # that actually ask for valuation (sensitivity, multiples, "mitä
        # jos…", "tavoitehinta", explicit "arvonmääritys", etc.).
        from inderes_agent.orchestration.router import (
            Domain as _Dom,
            query_has_valuation_intent,
        )
        # Two-channel intent detection:
        #   1. classification.has_valuation_intent — semantic decision
        #      from the router LLM (post-2026-05-10 change). Handles
        #      typos and morphology cleanly.
        #   2. query_has_valuation_intent() — keyword/stem fallback,
        #      kept as a safety net so a hard-coded match never has
        #      to wait on the LLM agreeing.
        # If EITHER says yes, run valuation. The toggle is the user's
        # explicit consent to add valuation to the dispatch list.
        intent_via_llm = bool(classification.has_valuation_intent)
        intent_via_keywords = query_has_valuation_intent(query)
        if (
            st.session_state.get("valuation_mode_on")
            and classification.companies
            and (intent_via_llm or intent_via_keywords)
        ):
            if _Dom.VALUATION not in classification.domains:
                classification.domains.append(_Dom.VALUATION)
            if _Dom.QUANT not in classification.domains:
                classification.domains.append(_Dom.QUANT)

        domains_html = " + ".join(_persona_chip(d.value) for d in classification.domains)
        companies_html = (
            f'<span style="color:var(--p-lead)">{", ".join(classification.companies)}</span>'
            if classification.companies else "—"
        )
        # "Reititys valmis: {chips} käsittelevät kohdetta {company}"
        # — descriptive, third person, completes the routing phase.
        status.write(
            _t(
                f"✓ Reititys valmis: {domains_html} käsittelevät kohdetta {companies_html}",
                f"✓ Routing done: {domains_html} will investigate {companies_html}",
            ),
            html=True,
        )

        # Inject conversation context into the SUBAGENT prompt as well, not
        # just the router. Without this, a followup like "Onko jompikumpi
        # näistä yhtiöistä mallisalkussa?" lands on the subagent without
        # any indication of what "näistä" refers to, and the subagent has
        # to ask for clarification. The router already knows the previous
        # turn's companies, but it routes — it doesn't propagate context to
        # subagent prompts. So we do that here.
        augmented_query = query
        if state.last_companies and not classification.is_comparison:
            ctx_line = (
                f"[CONTEXT: edellinen kysely käsitteli yhtiöitä: "
                f"{', '.join(state.last_companies)}. "
                f"Jos tämä kysymys viittaa 'näihin yhtiöihin', 'jompaan kumpaan' "
                f"tai pronominein ilman selvää viittausta, tulkitse niiden "
                f"viittaavan yllä mainittuihin yhtiöihin.]\n\n"
            )
            augmented_query = ctx_line + query

        # Resolve model-tier early — used by planner, workflow, and
        # synthesis. Three tiers map to two booleans. We accept both the
        # current option labels (with model name) AND legacy labels
        # (without) so a session cached on the old labels keeps working
        # through one redeploy.
        #   "Vakio (Flash Lite)" / "Standard (Flash Lite)"        → all False
        #   "Pro LEAD (Gemini 2.5 Pro)"                           → LEAD + planner on Pro
        #   "Pro kaikki (Gemini 2.5 Pro)" / "Pro all (Gemini …)"  → everything on Pro
        _selected_tier = st.session_state.get("lead_tier", "")
        deep_lead = _selected_tier in (
            # current
            "Pro LEAD (Gemini 2.5 Pro)",
            "Pro kaikki (Gemini 2.5 Pro)",
            "Pro all (Gemini 2.5 Pro)",
            # legacy
            "Tarkka LEAD", "Premium LEAD",
            "Tarkka kaikki", "Premium all",
        )
        deep_subagents = _selected_tier in (
            # current
            "Pro kaikki (Gemini 2.5 Pro)",
            "Pro all (Gemini 2.5 Pro)",
            # legacy
            "Tarkka kaikki", "Premium all",
        )

        # Plan-then-execute step (only when toggle is on). Adds one
        # LLM call before the workflow; the resulting plan is embedded
        # in each subagent's prompt and surfaced in the UI later as a
        # "🧠 Suunnitelma" expander.
        plan = None
        _pro_tag = " (Pro-tilassa)" if deep_lead and _fi else (
            " (Pro mode)" if deep_lead else ""
        )
        if st.session_state.get("plan_then_execute_on"):
            status.write(
                _t(
                    f"🧠 Suunnittelija laatii strategian agenteille{_pro_tag}…",
                    f"🧠 Planner drafts strategy for the agents{_pro_tag}…",
                ),
                html=True,
            )
            plan = await run_planner(
                augmented_query, classification, deep=deep_lead,
            )
            status.write(
                _t(
                    f"  ✓ Suunnitelma valmis ({plan.duration_seconds:.1f}s)",
                    f"  ✓ Plan ready ({plan.duration_seconds:.1f}s)",
                )
            )

        # Phase 3: dispatch — write a per-agent task description BEFORE
        # awaiting so the user sees who's working during the (often 10–30s)
        # parallel run.
        status.write(_t(
            "⚙ Agentit käynnistyvät rinnakkain:",
            "⚙ Agents starting in parallel:",
        ))
        for d in classification.domains:
            verb_dict = DOMAIN_VERBS_FI if _fi else DOMAIN_VERBS_EN
            verb = verb_dict.get(d.value, _t("tutkii aineistoa", "investigates data"))
            status.write(
                f"  {_persona_chip(d.value)} {verb}",
                html=True,
            )

        workflow_result = await run_workflow(
            augmented_query, classification, run_dir=run_dir,
            plan=plan, subagents_deep=deep_subagents,
        )

        # Phase 4: per-agent results
        for sr in workflow_result.subagent_results:
            chip = _persona_chip(sr.domain.value)
            company = f" · {sr.company}" if sr.company else ""
            if sr.error:
                status.write(
                    _t(
                        f"  {chip}{company} ❌ keskeytyi: {sr.error[:60]}",
                        f"  {chip}{company} ❌ failed: {sr.error[:60]}",
                    ),
                    html=True,
                )
            else:
                n_tools = len(sr.tool_calls or [])
                tools_lab = _t(
                    f"{n_tools} työkalukutsua",
                    f"{n_tools} tool calls",
                )
                status.write(
                    f"  {chip}{company} ✓ {sr.duration_seconds:.1f}s, "
                    f"{tools_lab} "
                    f'<span style="color:var(--ink-3); font-size:10px">'
                    f'({sr.model_used})</span>',
                    html=True,
                )

        # Phase 5: synthesis. `deep_lead` was resolved earlier so both
        # planner and synthesis use the same model tier.
        status.write(
            _t(
                f"{_persona_chip('lead')} kokoaa subagenttien tulokset yhdeksi vastaukseksi{_pro_tag}…",
                f"{_persona_chip('lead')} synthesises the subagent outputs into the final answer{_pro_tag}…",
            ),
            html=True,
        )
        answer, lead_model, synth_trace = await synthesize(
            query, workflow_result,
            deep_lead=deep_lead, deep_subagents=deep_subagents,
        )
        conflict_report = synth_trace.conflict_report

        write_run(
            run_dir=run_dir,
            query=query,
            workflow=workflow_result,
            answer=answer,
            lead_model=lead_model,
            duration_s=time.time() - t0,
            conflict_report=conflict_report,
            synth_trace=synth_trace,
        )
        write_narrative(run_dir)

        # Update state for follow-up turns
        state.last_workflow = workflow_result
        state.last_lead_model = lead_model
        state.last_companies = classification.companies or state.last_companies
        state.last_summary = answer[:400]
        state.last_run_dir = str(run_dir)
        for sr in workflow_result.subagent_results:
            state.invoked_agents.add(f"aino-{sr.domain.value}")

        return answer, run_dir
    finally:
        detach_console_log_handler(handler)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

prompt = st.chat_input("Kysy jotain Pohjoismaisista osakkeista…")

# A followup-chip click sets st.session_state.pending_query and reruns. If
# the user didn't type anything THIS rerun, pick up the queued query and
# treat it as if they typed it.
if not prompt and st.session_state.get("pending_query"):
    prompt = st.session_state.pop("pending_query")

if prompt:
    # Enforce the daily cap BEFORE we charge a query against the cap. The
    # increment happens after a successful run.
    _enforce_daily_cap_or_stop()

    st.session_state.history.append({"role": "user", "content": prompt, "run_dir": None})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        # CustomStatus replaces st.status — same surface API, but pure
        # HTML/CSS rendering with no Material Symbols icon (which kept
        # racing the icon font load and producing "ieckalmis"-style
        # overlap with the label text).
        status = CustomStatus("Käsittelen kysymystäsi…", expanded=True)
        try:
            answer, run_dir = asyncio.run(
                run_pipeline(prompt, st.session_state.state, status)
            )
            _increment_query_count()
            status.update(label="Valmis", state="complete", expanded=False)
            # Render order matches the chat-history loop (redesign 2026-05-07):
            # badge → Aikajana strip → 🧠 Päättely (with conflict box embedded
            # inside) → 💭 Perustelut (own box) → answer body → followups → trace.
            _lang_live = st.session_state.get("ui_lang", "fi")
            render_recommendation_badge(run_dir)
            render_timeline_strip(run_dir, lang=_lang_live)

            _cleaned_live, _perustelut_live = extract_perustelut(answer)

            # 🧠 Päättely (top — deeper reasoning before meta-summary).
            # Conflict callout (when present) is embedded inside this expander.
            _paattely_live_path = run_dir / "paattely.json"
            _conflict_html_live = build_conflict_html(run_dir, lang=_lang_live)
            _paattely_live_parsed = None
            if _paattely_live_path.exists():
                try:
                    _paattely_live_blob = json.loads(_paattely_live_path.read_text(encoding="utf-8"))
                    _paattely_live_parsed = _paattely_live_blob.get("parsed")
                except (OSError, json.JSONDecodeError):
                    _paattely_live_parsed = None
            render_paattely_b(
                _paattely_live_parsed,
                lang=_lang_live,
                conflict_html=_conflict_html_live,
            )

            # 💭 Perustelut box
            render_perustelut_box(_perustelut_live, lang=_lang_live)

            # Answer body (Perustelut already extracted out)
            render_lead_answer(_cleaned_live)
            # Time-series charts — same additive panel as in history
            # rendering. Silent no-op without QUANT data.
            from charts import render_time_series_charts as _rtc
            _rtc(run_dir, lang=_lang_live)
            render_followup_chips(answer, run_dir_name=run_dir.name)
            render_trace_expander(run_dir)
            st.session_state.history.append(
                {"role": "assistant", "content": answer, "run_dir": str(run_dir)}
            )
        except QuotaExhaustedError as exc:
            status.update(label="Quota exhausted", state="error", expanded=True)
            st.error(str(exc))
        except HeadlessAuthError:
            # Auth expired mid-query (tokens died between cold start and now).
            # Mark session as broken AND invalidate the cached _bootstrap_auth
            # so the very next rerun goes through the full auth path again,
            # detects the failure, and shows the persistent "Järjestelmä
            # alhaalla" card. Without this the cached "True" return makes
            # the app look healthy until the operator manually reboots.
            status.update(label="Inderes-yhteys vanhentunut", state="error", expanded=True)
            log.exception("oauth_headless_during_query")
            st.session_state["_auth_broken"] = True
            try:
                _bootstrap_auth.clear()
            except Exception:
                pass
            _render_auth_expired()
        except asyncio.CancelledError:
            # MCP / anyio cancels the request scope when the upstream stream
            # dies mid-handshake. Common cause: Inderes Keycloak's 10h SSO
            # Session Max kicks in and the MCP server closes the stream
            # before raising a clean OAuth error, so we get a bare
            # CancelledError instead of HeadlessAuthError.
            #
            # CancelledError inherits from BaseException, NOT Exception, so
            # the generic `except Exception` below would NEVER catch it —
            # the script crashes silently and the UI just freezes. Treat it
            # as the same "auth probably broken" state and surface the same
            # card so the user has something actionable.
            status.update(label="Yhteys keskeytyi", state="error", expanded=True)
            log.warning("mcp_cancelled_likely_auth_or_network")
            st.session_state["_auth_broken"] = True
            try:
                _bootstrap_auth.clear()
            except Exception:
                pass
            _render_auth_expired()
        except Exception as exc:
            # If anything looks like an auth/refresh problem, mask it the
            # same way. Otherwise show the (already-non-sensitive)
            # exception class — type names are safe.
            msg = str(exc).lower()
            if any(t in msg for t in ("session not active", "token is not active",
                                       "invalid_grant", "headless")):
                status.update(label="Inderes-yhteys vanhentunut", state="error", expanded=True)
                log.exception("oauth_likely_failure_in_query")
                # Same auth-broken latch as above — push the app into the
                # consistent "broken" state so the user sees the same card
                # on every subsequent rerun.
                st.session_state["_auth_broken"] = True
                try:
                    _bootstrap_auth.clear()
                except Exception:
                    pass
                _render_auth_expired()
            else:
                status.update(label="Error", state="error", expanded=True)
                st.error(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Trading Desk statusbar pinned at the bottom — pulls last run's stats
# ---------------------------------------------------------------------------

_last_meta: dict = {}
if st.session_state.history:
    _last = st.session_state.history[-1]
    if _last.get("run_dir"):
        _meta_path = Path(_last["run_dir"]) / "meta.json"
        if _meta_path.exists():
            try:
                _last_meta = json.loads(_meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
render_statusbar(_last_meta, st.session_state.get("ui_lang", "fi"))
