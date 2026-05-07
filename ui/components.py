"""Trading Desk visual components for the Streamlit app.

Two injection methods are used here, each for a different reason:

* ``inject_theme()`` uses ``st.markdown(..., unsafe_allow_html=True)``
  with a ``<style>`` block. This is the documented Streamlit way to
  inject page-level CSS — the style rules apply to the whole app.
* All other ``render_*`` helpers use ``st.html()``, which renders a
  raw HTML chunk into the page DOM (no markdown processing, no
  escape). They rely on the page-level CSS that ``inject_theme``
  loaded — they don't carry their own ``<style>`` tags.

We don't render the stylesheet via ``st.html`` because that wraps the
payload in a scoped container; ``<style>`` tags inside that wrapper
apply only to siblings within it, not to the surrounding Streamlit
chrome.

Keeping the components in one module means ``ui/app.py`` stays mostly
the same — we just swap in a few calls.

Drop-in usage:

    from ui.components import (
        inject_theme, render_titlebar, render_ticker, render_disclaimer,
        render_idle_hero, render_routing_card, render_metrics_row,
        render_agent_row, render_agent_output, render_statusbar,
    )

The agent persona table mirrors the five-agent system in
``src/inderes_agent/agents/``. Codes match the domain enum names.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

import streamlit as st


# ---------------------------------------------------------------------------
# Persona table — purely cosmetic. Matches src/inderes_agent/agents/* codes.
# ---------------------------------------------------------------------------

# Persona colors live in BOTH places: theme.css (--p-lead etc.) for CSS-only
# usage, and these hex literals for inline-style usage in Python-rendered HTML
# (Streamlit's f-string injection). Keep the two in sync — the source of
# truth is `ui/redesign-handoff/IMPLEMENTATION_NOTES.md`.
PERSONAS: dict[str, dict[str, Any]] = {
    "LEAD": {
        "glyph": "◆", "color": "#F5B942",
        "role_fi": "Päätoimittaja", "role_en": "Editor-in-chief",
        "desc_fi": "Reitittää kysymyksen, jakaa työn subagenteille ja kirjoittaa lopullisen vastauksen.",
        "desc_en": "Routes the query, dispatches subagents and writes the final synthesis.",
    },
    "QUANT": {
        "glyph": "▲", "color": "#5FD28A",
        "role_fi": "Numerot", "role_en": "Numbers",
        "desc_fi": "Hakee fundamentaalit ja Inderesin estimaatit, ajaa Python-laskut (CAGR, suhdeluvut) sandboxissa.",
        "desc_en": "Pulls fundamentals + Inderes estimates, runs Python math (CAGR, ratios) in a sandbox.",
    },
    "RESEARCH": {
        "glyph": "■", "color": "#6AA9FF",
        "role_fi": "Analyytikko", "role_en": "Analyst",
        "desc_fi": "Lukee Inderesin raportit ja transkriptit, etsii laadulliset ajurit ja näkemykset.",
        "desc_en": "Reads Inderes reports + transcripts, surfaces qualitative drivers and theses.",
    },
    "SENTIMENT": {
        "glyph": "●", "color": "#FF7EB3",
        "role_fi": "Tunnelmat", "role_en": "Vibes",
        "desc_fi": "Kahlaa keskustelupalstan ja sisäpiirikaupat, raportoi yksityissijoittajien tunnelman.",
        "desc_en": "Trawls forum threads + insider trades, reports retail sentiment and signals.",
    },
    "PORTFOLIO": {
        "glyph": "✦", "color": "#C294FF",
        "role_fi": "Mallisalkku", "role_en": "Model book",
        "desc_fi": "Tarkastaa onko yhtiö Inderesin mallisalkussa ja millä painoilla.",
        "desc_en": "Checks whether the company is in Inderes' model portfolio and at what weight.",
    },
}

# Mock ticker — replace with a real feed if/when available.
TAPE_ITEMS = [
    ("SAMPO", "9.84", "+0.42%", True),
    ("NDA-FI", "11.22", "-0.18%", False),
    ("KCR", "62.10", "+1.20%", True),
    ("NOKIAN-RT", "8.76", "+0.05%", True),
    ("FORTUM", "14.93", "-0.32%", False),
    ("ELISA", "44.20", "+0.10%", True),
    ("NESTE", "12.05", "-2.10%", False),
    ("WRT1V", "20.18", "+0.55%", True),
    ("OUT1V", "5.62", "+0.36%", True),
    ("TYRES", "8.99", "+0.48%", True),
]


# ---------------------------------------------------------------------------
# Theme injection
# ---------------------------------------------------------------------------

def inject_theme() -> None:
    """Inject the Trading Desk CSS once per Streamlit session.

    `st.html()` wraps its payload in a scoped container (`<div data-testid=
    "stHtml">…</div>`) — `<style>` tags inside that wrapper apply only to
    siblings within the wrapper, NOT to the rest of the Streamlit page. So
    rendering a stylesheet via `st.html` produces zero styling on the
    surrounding chrome.

    The documented way to inject page-level CSS in Streamlit is
    `st.markdown(..., unsafe_allow_html=True)` with a `<style>` block —
    those tags ARE preserved and applied to the entire page.

    The font is embedded as a CSS `@import` rather than a separate `<link>`
    tag — `@import` lives inside the `<style>` block and travels with it.
    """
    css_path = Path(__file__).parent / "theme.css"
    if not css_path.exists():
        return
    css = css_path.read_text(encoding="utf-8")
    font_import = (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=JetBrains+Mono:wght@400;500;600;700&display=swap');\n"
        # Streamlit uses Material Symbols Rounded for chevrons + sidebar
        # collapse arrow. We load it explicitly so it's available even if
        # Streamlit's CDN load races with our font-family overrides.
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@"
        "20..48,100..700,0..1,-50..200');\n"
    )
    st.markdown(
        f"<style>{font_import}{css}</style>",
        unsafe_allow_html=True,
    )
    # JS belt-and-suspenders: capture the scroll position before any <details>
    # toggles and restore it right after. Chrome's implicit "scroll the
    # opening element into view" behaviour can't be killed by CSS alone,
    # but freezing window.scrollY across the toggle event hides the jump.
    st.markdown(
        """
        <script>
        (function() {
          if (window.__inderes_scroll_lock_installed) return;
          window.__inderes_scroll_lock_installed = true;
          const root = window.parent || window;
          root.document.addEventListener('click', (e) => {
            const summary = e.target.closest('summary');
            if (!summary) return;
            const before = root.scrollY;
            // Restore on the next two animation frames — Chrome's auto-scroll
            // happens after the toggle event commits.
            requestAnimationFrame(() => {
              root.scrollTo({ top: before, behavior: 'instant' });
              requestAnimationFrame(() => {
                root.scrollTo({ top: before, behavior: 'instant' });
              });
            });
          }, true);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header chrome
# ---------------------------------------------------------------------------

def render_titlebar(lang: str = "fi") -> None:
    online = "ONLINE" if lang == "en" else "VERKOSSA"
    html = (
        '<div class="ia-titlebar">'
        '<span class="ia-brand">INDERES//AGENT</span>'
        '<span class="ia-tag">DESK</span>'
        '<span class="ia-spacer"></span>'
        f'<span class="ia-online">{online}</span>'
        "</div>"
    )
    st.html(html)


def render_ticker() -> None:
    items = []
    for tk, px, chg, up in TAPE_ITEMS * 3:  # repeat for seamless scroll
        cls = "ia-up" if up else "ia-dn"
        arrow = "▲" if up else "▼"
        items.append(
            f'<span class="ia-tape-item">'
            f'<span class="ia-tk">{tk}</span>'
            f'<span class="ia-px">{px}</span>'
            f'<span class="{cls}">{arrow} {chg}</span>'
            f"</span>"
        )
    html = (
        '<div class="ia-tape"><div class="ia-tape-track">'
        + "".join(items)
        + "</div></div>"
    )
    st.html(html)


# ---------------------------------------------------------------------------
# Disclaimer + idle hero
# ---------------------------------------------------------------------------

GITHUB_URL = "https://github.com/5qtb5t9v5k-rgb/inderes-mcp-agent-system"


def render_disclaimer(lang: str = "fi") -> None:
    """Hero panel: brand equation + one-line tagline + agent roster.

    The not-affiliated notice lives in the sidebar disclaimer, not here, so
    this panel reads as an inviting intro instead of a legal notice.
    """
    if lang == "fi":
        tag = "MULTI-AGENT RESEARCH"
        tagline = "Tutki pohjoismaisia osakkeita viiden erikoistuneen agentin kautta."
    else:
        tag = "MULTI-AGENT RESEARCH"
        tagline = "Research Nordic equities through five specialised agents."

    # Equation — INDERES + MCP + AGENTIT = INSIGHTS — captures what this is
    # at a glance. Operators and the equals sign get colored separately so
    # the eye lands on the three operands.
    eq_html = (
        '<span class="op">INDERES</span>'
        '<span class="plus"> + </span>'
        '<span class="op">MCP</span>'
        '<span class="plus"> + </span>'
        '<span class="op">AGENTIT</span>'
        '<span class="eq"> = </span>'
        '<span class="result">INSIGHTS</span>'
    )

    agents_html = ""
    for code, p in PERSONAS.items():
        agents_html += (
            f'<span class="ag" style="color:{p["color"]}">'
            f'{p["glyph"]} {code}</span>'
        )

    html = (
        '<div class="ia-hero">'
        f'<div class="ia-hero-tag">{tag}</div>'
        f'<div class="ia-hero-eq">{eq_html}</div>'
        f'<div class="ia-hero-text">{tagline}</div>'
        f'<div class="ia-hero-agents">{agents_html}</div>'
        '</div>'
    )
    st.html(html)


def render_sidebar_disclaimer(lang: str = "fi") -> None:
    """Red-bordered fine-print disclaimer at the very top of the sidebar.

    The single source of truth for the legal notice: not endorsed by Inderes,
    not investment advice, user takes their own decisions. No other panel
    repeats this — they focus on what the project IS, not what it isn't.
    """
    if lang == "fi":
        head = "HUOM"
        body = (
            "Ei Inderes Oyj:n tuottama tai hyväksymä. Ei sijoitusneuvoja — "
            "käyttäjä vastaa omista päätöksistään."
        )
    else:
        head = "DISCLAIMER"
        body = (
            "Not produced or endorsed by Inderes Oyj. Not investment advice "
            "— the user is responsible for their own decisions."
        )
    html = (
        f'<div class="ia-side-disclaimer">'
        f'<div class="ia-sd-h">{head}</div>'
        f'<div class="ia-sd-b">{body}</div>'
        '</div>'
    )
    st.html(html)


def render_github_link(lang: str = "fi") -> None:
    """GitHub CTA button — slot anywhere in the sidebar."""
    label = "LISÄTIEDOT GITHUBISSA →" if lang == "fi" else "MORE INFO ON GITHUB →"
    html = (
        f'<a class="ia-side-cta" href="{GITHUB_URL}" target="_blank" rel="noopener">'
        f'{label}</a>'
    )
    st.html(html)


def render_idle_hero(lang: str = "fi") -> None:
    title = "INDERES // AGENT TERMINAL"
    sub = "Kirjoita kysely tai valitse alta" if lang == "fi" else "Type a query or pick one below"
    html = (
        '<div class="ia-idle">'
        '<div class="ia-glyphs">◆ ▲ ■ ● ✦</div>'
        f'<div class="ia-title">{title}</div>'
        f'<div class="ia-sub">{sub}</div>'
        "</div>"
    )
    st.html(html)


# ---------------------------------------------------------------------------
# Routing card
# ---------------------------------------------------------------------------

def render_routing_card(routing: dict, lang: str = "fi") -> None:
    """``routing`` is the parsed contents of ``run_dir/routing.json``."""
    domains = routing.get("domains", [])
    companies = routing.get("companies") or []
    is_cmp = routing.get("is_comparison")
    reason = routing.get("reasoning", "")

    pills = ""
    for d in domains:
        code = d.upper()
        p = PERSONAS.get(code, {"glyph": "•", "color": "#888"})
        pills += (
            f'<span class="ia-pill" '
            f'style="color:{p["color"]};border-color:{p["color"]}">'
            f'{p["glyph"]} {code}</span>'
        )

    co_label = "COMPANY" if lang == "en" else "YHTIÖ"
    dom_label = "DOMAINS" if lang == "en" else "DOMAINIT"
    cmp_label = "COMPARISON" if lang == "en" else "VERTAILU"
    rea_label = "REASON" if lang == "en" else "PERUSTELU"
    yes = "yes" if lang == "en" else "kyllä"
    no  = "no"  if lang == "en" else "ei"

    html = (
        '<div class="ia-routing">'
        f'<div><div class="ia-rl">{co_label}</div>'
        f'<div class="ia-rv amber">{", ".join(companies) or "—"}</div></div>'
        f'<div><div class="ia-rl">{dom_label}</div>'
        f'<div class="ia-rv">{pills}</div></div>'
        f'<div><div class="ia-rl">{cmp_label}</div>'
        f'<div class="ia-rv">{yes if is_cmp else no}</div></div>'
        # PERUSTELU gets its own pink-ish accent so it's visually distinct
        # from the structured fields above — it's free-form prose, the others
        # are categorical.
        f'<div><div class="ia-rl reason">{rea_label}</div>'
        f'<div class="ia-rv reason">{_esc(reason)}</div></div>'
        "</div>"
    )
    st.html(html)


# ---------------------------------------------------------------------------
# Metric row — best-effort: pulls metrics from the QUANT subagent's
# JSON if it includes a ``metrics`` block. Otherwise renders nothing.
# ---------------------------------------------------------------------------

def render_metrics_row(run_dir: Path, lang: str = "fi") -> None:
    quant_files = list(run_dir.glob("subagent-*-quant.json"))
    if not quant_files:
        return
    try:
        sa = json.loads(quant_files[0].read_text(encoding="utf-8"))
    except Exception:
        return
    m = sa.get("metrics") or {}
    if not m:
        return  # don't render an empty row

    pe_label  = "P/E"
    tg_label  = "TARGET" if lang == "en" else "TAVOITE"
    rec_label = "REC"    if lang == "en" else "SUOSITUS"
    div_label = "DIV YIELD" if lang == "en" else "OSINKOTUOTTO"

    def _fmt(v):
        if v is None: return "—"
        if isinstance(v, (int, float)):
            s = f"{v:.2f}" if v % 1 else f"{v:.0f}"
            return s.replace(".", ",") if lang == "fi" else s
        return str(v)

    pe = m.get("pe_2025") or m.get("pe")
    pe_e = m.get("pe_2026e")
    tgt = m.get("target")
    rec = m.get("rec") or "—"
    dy  = m.get("div_yield")

    html = (
        '<div class="ia-metrics">'
        f'<div class="ia-metric"><div class="ia-ml">{pe_label} 2025</div>'
        f'<div class="ia-mv green">{_fmt(pe)}</div>'
        f'<div class="ia-ms">2026e {_fmt(pe_e)}</div></div>'
        f'<div class="ia-metric"><div class="ia-ml">{tg_label}</div>'
        f'<div class="ia-mv">€{_fmt(tgt)}</div>'
        f'<div class="ia-ms">Inderes</div></div>'
        f'<div class="ia-metric"><div class="ia-ml">{rec_label}</div>'
        f'<div class="ia-mv blue small">{rec}</div>'
        f'<div class="ia-ms">{rec}</div></div>'
        f'<div class="ia-metric"><div class="ia-ml">{div_label}</div>'
        f'<div class="ia-mv">{_fmt(dy)}%</div>'
        f'<div class="ia-ms">2026e</div></div>'
        "</div>"
    )
    st.html(html)


# ---------------------------------------------------------------------------
# Agent trace rows (one per subagent) — replaces the plain markdown header
# in the existing render_trace_expander.
# ---------------------------------------------------------------------------

def render_agent_row(sa: dict, lang: str = "fi") -> None:
    domain = (sa.get("domain") or "?").upper()
    company = sa.get("company")
    model = sa.get("model_used", "?")
    err = sa.get("error")
    duration = sa.get("duration_seconds")  # set by run_log >= the timing-instrumentation commit
    tool_call_count = len(sa.get("tool_calls") or [])
    p = PERSONAS.get(domain, {"glyph": "•", "color": "#888", "role_fi": "—", "role_en": "—"})
    role = p["role_en"] if lang == "en" else p["role_fi"]
    status = ("ERROR" if err else ("OK" if lang == "en" else "VALMIS"))
    cls = "err" if err else "done"

    name = domain + (f" / {company}" if company else "")

    # Status cell now shows status + timing + tool-call count for richer
    # at-a-glance visibility ("how long did this take, how many tools did
    # it call"). Falls back gracefully if duration is missing (older runs).
    extras: list[str] = []
    if isinstance(duration, (int, float)) and duration > 0:
        extras.append(f"{duration:.1f}s")
    if tool_call_count:
        tool_label = "tool call" if tool_call_count == 1 else "tool calls"
        if lang == "fi":
            tool_label = "kutsu" if tool_call_count == 1 else "kutsua"
        extras.append(f"{tool_call_count} {tool_label}")
    extras_html = (
        f'<div style="font-size:11px; color: var(--ia-faint, #888); margin-top:2px;">'
        f'{" · ".join(extras)}</div>'
    ) if extras else ""

    html = (
        f'<div class="ia-agent-row {cls}">'
        f'<div class="ia-glyph" style="color:{p["color"]}">{p["glyph"]}</div>'
        f'<div><div class="ia-name" style="color:{p["color"]}">{_esc(name)}</div>'
        f'<div class="ia-role">{_esc(role)}</div></div>'
        f'<div class="ia-model">{_esc(model)}</div>'
        f'<div class="ia-status">{status}{extras_html}</div>'
        f'<div></div>'
        "</div>"
    )
    st.html(html)


def _ensure_python_fenced(text: str) -> str:
    """Wrap raw Python source in a ```python fence if no fences are present.

    QUANT sometimes returns Python code without any markdown fencing — its
    first line is a comment (``# Puuilon …``) or an assignment, which the
    markdown renderer otherwise interprets as headings / paragraphs. Detect
    that case and add a fence so it renders as a proper code block.
    """
    import re

    if not text or "```" in text:
        return text
    first = text.lstrip().split("\n", 1)[0]
    py_lead = re.compile(
        r"^\s*(#\s|import\s+\w|from\s+\w[\w.]*\s+import\b|"
        r"def\s+\w+\s*\(|class\s+\w+\s*[:(]|"
        r"\w+\s*=\s*[\[\{\(\d\'\"]|"  # assignment to literal
        r"print\(|for\s+\w+\s+in\b)"
    )
    if py_lead.match(first):
        return f"```python\n{text.rstrip()}\n```"
    return text


def _looks_like_python_output(s: str) -> bool:
    """Does this paragraph look like Python sandbox stdout (vs. prose)?

    Catches:
      * Python repr starts: ``{``, ``[``, ``(``, ``'``, ``"``, digit
      * pandas DataFrame output (alphabetic column names + 2+ aligned
        whitespace runs on the same line)
      * Output containing ``NaN`` / ``None`` / ``True`` / ``False`` / ``dtype``
      * Numeric-heavy text without sentence terminators
    """
    import re

    s = s.strip()
    if not s:
        return False
    if s[0] in "{[('\"0123456789":
        return True
    # DataFrame-style: column names with 2+ spaces between them
    if re.search(r"\S {2,}\S", s):
        return True
    # Characteristic Python output tokens
    if re.search(r"\b(NaN|None|True|False|dtype|Name:|object|float64|int64)\b", s):
        return True
    # Numeric and not a sentence (no terminal . ! ? :)
    if re.search(r"\d", s) and not s.rstrip().endswith((".", "!", "?", ":")):
        return True
    return False


def _wrap_python_output(text: str) -> str:
    """Wrap Python sandbox stdout (the paragraph right after a ```python block)
    as a fenced ``output`` block so it renders distinctly from both code and
    prose.

    Heuristics live in ``_looks_like_python_output`` so we can extend them
    without touching the regex. Discriminates against actual prose
    (paragraphs ending in a period, no numbers, etc.) so explanation text
    after a code block doesn't get mis-styled.
    """
    import re

    pat = re.compile(
        r"(^```\s*$\n)"      # 1: closing fence on its own line
        r"\n+"               #    one or more blank lines
        r"(.+?)"             # 2: candidate paragraph (greedy-min)
        r"(?=\n\s*\n|\Z)",   #    stop at blank line or end-of-string
        re.MULTILINE | re.DOTALL,
    )

    def _replace(m: "re.Match[str]") -> str:
        end_fence = m.group(1)
        candidate = m.group(2)
        if _looks_like_python_output(candidate):
            return f"{end_fence}\n```output\n{candidate}\n```"
        return m.group(0)  # leave prose untouched

    return pat.sub(_replace, text)


def render_agent_output(text: str | None) -> None:
    """Render the subagent's text in a styled box.

    Each `st.html()` call is its own DOM block, so we can't open a div in
    one call and close it in another. Instead we convert the markdown text
    to HTML via `markdown-it-py` (already an indirect dependency through
    Streamlit's own rich-rendering stack) and wrap the result in our
    `ia-agent-output` div in a single st.html call.

    Before rendering we pre-process the text so a stdout-looking paragraph
    that immediately follows a ```python``` block gets wrapped in its own
    ```output``` fenced block — the CSS then gives it a green left border so
    it's visually distinct from the (blue-bordered) source-code block above.
    """
    if not text:
        text = "_(empty response)_"
    text = _ensure_python_fenced(text)
    text = _wrap_python_output(text)
    try:
        from markdown_it import MarkdownIt

        # `commonmark` preset doesn't include tables — explicitly enable them
        # so subagent markdown like `| col | col |` renders as <table>, not
        # raw pipe text. Also enable strikethrough since QUANT/LEAD outputs
        # occasionally use it.
        md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
        html_content = md.render(text)
    except Exception:
        # If markdown_it isn't available for some reason, fall back to a
        # `<pre>` block — formatting is lost but content still readable.
        from html import escape as _html_escape

        html_content = f"<pre>{_html_escape(text)}</pre>"
    html_content = _externalize_links(html_content)
    st.html(f'<div class="ia-agent-output">{html_content}</div>')


def split_followups(text: str) -> tuple[str, list[str]]:
    """Split a LEAD synthesis into (main_answer, followup_questions).

    LEAD's prompt instructs it to end every synthesis with a
    ``## 💡 Voisit kysyä myös`` (or ``## 💡 You could also ask``) section
    containing exactly three bullet questions. We strip that section out of
    the main answer (so it doesn't render as a heading + bullets) and return
    the questions as a list for the UI to render as clickable buttons.

    Tolerant to LEAD wobble:
      * 1-3 ``#`` characters in the heading (h1/h2/h3 all accepted)
      * Optional ``💡`` emoji
      * Optional trailing colon
      * Bullets starting with ``-``, ``*``, or numbered ``1.`` ``2)`` etc.
      * Filters out placeholder bullets (``[...]``, ``<...>``) just in case
        LEAD copies the prompt's example text literally.

    If no such section exists, returns (text, []) — graceful fallback.
    """
    import re

    # Header: 1-3 hashes, optional emoji, FI or EN phrase, optional colon.
    pat = re.compile(
        r"^#{1,3}\s*(?:[💡✨🤔]\s*)?"
        r"(?:Voisit\s+kysy[äa]\s+my[öo]s|You\s+could\s+also\s+ask)"
        r"\s*:?\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    m = pat.search(text)
    if not m:
        return text, []
    main = text[: m.start()].rstrip()
    after = text[m.end():]

    # Match bullets: leading "- ", "* ", "• ", "1. ", "1) ", etc.
    bullet_pat = re.compile(
        r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$",
        flags=re.MULTILINE,
    )
    raw_bullets = bullet_pat.findall(after)
    # Strip markdown emphasis around the question and filter out placeholder
    # text (anything wrapped entirely in [] or <> braces or starting with
    # "Tähän" / "Question" — LEAD echoing the prompt's example).
    bullets = []
    for b in raw_bullets:
        cleaned = b.strip().strip("*_`")
        if not cleaned:
            continue
        if cleaned.startswith(("[", "<")) and cleaned.endswith(("]", ">")):
            continue
        if re.match(r"(Tähän|Question \d+|<\.\.\.>)", cleaned, re.IGNORECASE):
            continue
        bullets.append(cleaned)
    return main, bullets[:3]  # cap at 3 just in case


def _externalize_links(html: str) -> str:
    """Add ``target="_blank" rel="noopener noreferrer"`` to every ``<a>`` in
    a chunk of rendered markdown so source links open in a new tab.

    markdown_it doesn't do this by default and we don't want to pull in a
    plugin just for one rule — a simple regex sub is enough since our
    rendered HTML never contains nested anchors.
    """
    import re

    return re.sub(
        r'<a\s+href="([^"]+)"',
        r'<a href="\1" target="_blank" rel="noopener noreferrer"',
        html,
    )


def render_activity_panel(run_dir: Path, lang: str = "fi", active_tab: str = "summary") -> None:
    """Render the right-side activity panel as a position:fixed overlay.

    Translates ui/redesign-handoff/parts.jsx :: ActivityPanel. Reads from
    `run_dir` (latest run's persisted state) and emits a single HTML block
    styled by the `.ia-panel` rules in theme.css. The panel is anchored to
    the right edge via position:fixed; the main column is automatically
    pushed left by a `:has()` selector in CSS — the redesigned layout
    needs no Python-side column gymnastics.

    Tabs (`active_tab`):
      - "summary" (default): metric cards + stage bars + per-agent cards
      - "agents":  per-agent cards only
      - "tools":   flat list of every tool call across all subagents
      - "conflicts": conflict-detector report
    Clicking a tab navigates with `?panel_tab=NNN` so the rerun shows the
    filtered view.
    """
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    duration = meta.get("duration_seconds", 0)
    sub_count = meta.get("subagent_count", 0)
    sub_errors = meta.get("subagent_errors", 0)
    fallbacks = meta.get("fallback_events", 0)
    stage = meta.get("stage_timings") or {}
    fanout_s = stage.get("fanout_seconds")
    detector_s = stage.get("conflict_detector_seconds") or 0
    lead_s = stage.get("lead_seconds") or 0
    per_subagent = stage.get("per_subagent") or []

    # Count tool calls + collect persona codes used (for the chip row).
    tool_call_count = 0
    persona_codes: list[str] = []
    sub_files = sorted(run_dir.glob("subagent-*.json"))
    sub_blobs: list[dict] = []
    for path in sub_files:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sub_blobs.append(blob)
        tool_call_count += len(blob.get("tool_calls") or [])
        domain = (blob.get("domain") or "").upper()
        if domain and domain not in persona_codes:
            persona_codes.append(domain)

    # Conflict count
    conflicts_path = run_dir / "conflicts.json"
    conflict_count = 0
    if conflicts_path.exists():
        try:
            cblob = json.loads(conflicts_path.read_text(encoding="utf-8"))
            parsed = (cblob or {}).get("parsed") or {}
            conflict_count = len(parsed.get("conflicts") or [])
        except (OSError, json.JSONDecodeError):
            pass

    # Localization helpers
    L = {
        "head":      ("AGENTTIEN TOIMINTALOKI", "AGENT ACTIVITY LOG"),
        "yhteenveto": ("Yhteenveto", "Summary"),
        "agentit":   ("Agentit",     "Agents"),
        "tyokalut":  ("Työkalut",    "Tools"),
        "konfliktit": ("Konfliktit", "Conflicts"),
        "duration":  ("KESTO",        "DURATION"),
        "subagentit": ("SUBAGENTIT",  "SUBAGENTS"),
        "tools":     ("TYÖKALUKUTSUT", "TOOL CALLS"),
        "errors":    ("VIRHEET",      "ERRORS"),
        "all_ok":    ("kaikki onnistuivat", "all succeeded"),
        "fallback":  ("0 fallback",   "0 fallback"),
        "kutsua":    ("kutsua",       "calls"),
        "valmis":    ("valmis",       "done"),
    }
    fi = lang == "fi"
    def t(key: str) -> str:
        return L[key][0] if fi else L[key][1]

    # Tabs row — each tab is an <a> with ?panel_tab= query param. Clicking
    # reloads the page with the new param; app.py reads it and passes it
    # back to active_tab here so the corresponding content renders.
    def tab_html(slug: str, label: str, count: int | None = None) -> str:
        is_active = slug == active_tab
        cls = "tab is-active" if is_active else "tab"
        n_html = f' <span class="n">{count}</span>' if count is not None else ""
        return f'<a class="{cls}" href="?panel=open&panel_tab={slug}">{label}{n_html}</a>'

    tabs_html = (
        f'<div class="ia-panel-tabs">'
        f'{tab_html("summary", t("yhteenveto"))}'
        f'{tab_html("agents", t("agentit"), sub_count)}'
        f'{tab_html("tools", t("tyokalut"), tool_call_count)}'
        f'{tab_html("conflicts", t("konfliktit"), conflict_count)}'
        f'</div>'
    )

    # 2×2 metric cards
    fanout_str = f"{fanout_s:.1f}s" if fanout_s is not None else "—"
    detector_str = f"{detector_s:.1f}s" if detector_s else "—"
    lead_str = f"{lead_s:.1f}s" if lead_s else "—"
    metrics_html = (
        '<div class="ia-panel-metrics">'
        f'<div class="metric"><div class="lab">{t("duration")}</div>'
        f'<div class="v num">{duration:.1f}s</div>'
        f'<div class="sub">fan-out {fanout_str} · konflikti {detector_str} · LEAD {lead_str}</div></div>'
        f'<div class="metric"><div class="lab">{t("subagentit")}</div>'
        f'<div class="v num">{sub_count}</div>'
        f'<div class="sub">{" · ".join(persona_codes) if persona_codes else "—"}</div></div>'
        f'<div class="metric"><div class="lab">{t("tools")}</div>'
        f'<div class="v num">{tool_call_count}</div>'
        f'<div class="sub">Inderes MCP · {fallbacks} fallback</div></div>'
        f'<div class="metric"><div class="lab">{t("errors")}</div>'
        f'<div class="v num {"ok" if sub_errors == 0 else "err"}">{sub_errors}</div>'
        f'<div class="sub">{t("all_ok") if sub_errors == 0 else ""}</div></div>'
        '</div>'
    )

    # Stage gantt bars: routing | QUANT | RESEARCH | ... | conflicts | LEAD
    # Total wall-clock = duration. Each stage rendered as a colored bar.
    stages_html_parts: list[str] = ['<div class="ia-panel-stages">']
    if fanout_s is not None:
        # Per-subagent bars (parallel — all start near 0, vary in length)
        for ent in per_subagent:
            persona = (ent.get("domain") or "").upper()
            color = PERSONAS.get(persona, {}).get("color", "#888")
            ds = ent.get("duration_seconds", 0) or 0
            company = ent.get("company")
            label = persona + (f"·{company}" if company else "")
            width_pct = min(99.0, (ds / max(duration, 0.1)) * 100)
            stages_html_parts.append(
                f'<div class="stage"><span class="nm">{label}</span>'
                f'<div class="bar"><i style="left:0%; width:{width_pct:.1f}%; background:{color}"></i></div>'
                f'<span class="v">{ds:.1f}s</span></div>'
            )
    if detector_s:
        # Conflict detector runs after fan-out
        offset_pct = (fanout_s / max(duration, 0.1)) * 100 if fanout_s else 0
        width_pct = (detector_s / max(duration, 0.1)) * 100
        stages_html_parts.append(
            f'<div class="stage"><span class="nm">conflicts</span>'
            f'<div class="bar"><i style="left:{offset_pct:.1f}%; width:{width_pct:.1f}%; background:var(--ink-2)"></i></div>'
            f'<span class="v">{detector_s:.1f}s</span></div>'
        )
    if lead_s:
        # LEAD runs after conflict detector
        offset_pct = ((fanout_s or 0) + detector_s) / max(duration, 0.1) * 100
        width_pct = (lead_s / max(duration, 0.1)) * 100
        stages_html_parts.append(
            f'<div class="stage"><span class="nm">LEAD</span>'
            f'<div class="bar"><i style="left:{offset_pct:.1f}%; width:{width_pct:.1f}%; background:var(--p-lead)"></i></div>'
            f'<span class="v">{lead_s:.1f}s</span></div>'
        )
    stages_html_parts.append('</div>')

    # Per-agent cards
    agent_cards: list[str] = []
    for blob in sub_blobs:
        domain = (blob.get("domain") or "").upper()
        company = blob.get("company")
        persona = PERSONAS.get(domain, {"glyph": "•", "color": "#888", "role_fi": "—", "role_en": "—"})
        role = persona["role_fi"] if fi else persona["role_en"]
        ds = blob.get("duration_seconds", 0) or 0
        n_calls = len(blob.get("tool_calls") or [])
        text = blob.get("text") or ""
        # Take the "Ajatus:" line as a compact preview if present, else first 200 chars.
        thought = ""
        m = re.search(r"\*\*Ajatus:\*\*\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
        if m:
            thought = m.group(1).strip()
        else:
            mb = re.search(r"Ajatus:\s*(.+?)(?:\n\n|$)", text, re.DOTALL)
            if mb:
                thought = mb.group(1).strip()
            else:
                thought = text[:200].strip()
        if len(thought) > 240:
            thought = thought[:240].rstrip() + "…"

        # Tool list (compact)
        tool_list = ""
        for tc in (blob.get("tool_calls") or [])[:6]:
            tname = tc.get("name") or "?"
            count = tc.get("item_count")
            names = tc.get("item_names") or []
            preview = ", ".join(names[:3])
            if len(names) > 3:
                preview += "…"
            count_str = f"{count} items" if count is not None else "—"
            tool_list += (
                f'<li><span class="tool" style="color:{persona["color"]}">{tname}</span>'
                f' <span class="ret">→ {count_str}{(" · " + preview) if preview else ""}</span></li>'
            )
        if not tool_list:
            tool_list = '<li style="color:var(--ink-3)">—</li>'

        label = domain + (f" / {company}" if company else "")

        agent_cards.append(
            f'<div class="ia-panel-agcard" style="border-left:2px solid {persona["color"]}">'
            f'<div class="head">'
            f'<span class="glyph" style="color:{persona["color"]}">{persona["glyph"]}</span>'
            f'<span class="nm" style="color:{persona["color"]}">{label}</span>'
            f'<span class="role">{role}</span>'
            f'<span class="meta"><span class="ok">✓ {t("valmis")}</span> '
            f'<span>{ds:.1f}s</span> <span>{n_calls} {t("kutsua")}</span></span>'
            f'</div>'
            f'<div class="body"><div class="think"><b>Ajatus:</b> {thought}</div></div>'
            # Tool list as native <details> — click summary to expand. Default
            # closed so a fan-out with 10 agents × 4 tools doesn't dump 40
            # rows on the user. They click to drill in.
            f'<details class="tools"><summary class="toolhead">▾ TYÖKALUT ({n_calls})</summary>'
            f'<ol>{tool_list}</ol></details>'
            f'</div>'
        )

    # Build body content per active tab. Each tab is a focused view of the
    # same underlying data, not a different data source — so user can switch
    # tabs without losing context, and the URL ?panel_tab= keeps the choice
    # across reruns.
    if active_tab == "agents":
        body_html = "".join(agent_cards) or '<div style="color:var(--ink-3)">—</div>'
    elif active_tab == "tools":
        # Flat list of every tool call across all subagents, persona-colored.
        tool_rows: list[str] = []
        for blob in sub_blobs:
            persona_code = (blob.get("domain") or "").upper()
            company = blob.get("company")
            p = PERSONAS.get(persona_code, {"glyph": "•", "color": "#888"})
            origin = persona_code + (f"/{company}" if company else "")
            for tc in (blob.get("tool_calls") or []):
                tname = tc.get("name") or "?"
                args = tc.get("arguments")
                args_str = json.dumps(args, ensure_ascii=False) if args else "{}"
                if len(args_str) > 120:
                    args_str = args_str[:120] + "…"
                count = tc.get("item_count")
                names = tc.get("item_names") or []
                preview = ", ".join(names[:5])
                if len(names) > 5:
                    preview += "…"
                count_str = f"{count} items" if count is not None else "—"
                tool_rows.append(
                    f'<div class="ia-panel-toolrow">'
                    f'<div class="origin"><span class="glyph" style="color:{p["color"]}">{p["glyph"]}</span> '
                    f'<span style="color:{p["color"]}">{origin}</span></div>'
                    f'<div class="tool" style="color:{p["color"]}">{tname}</div>'
                    f'<div class="args">{args_str}</div>'
                    f'<div class="ret">→ {count_str}{(" · " + preview) if preview else ""}</div>'
                    f'</div>'
                )
        body_html = "".join(tool_rows) or '<div style="color:var(--ink-3)">—</div>'
    elif active_tab == "conflicts":
        # Conflict-detector report (raw + parsed structure)
        if conflict_count == 0:
            body_html = (
                '<div style="color:var(--ink-2); padding: 16px 0;">'
                + ("Ei ristiriitoja tässä ajossa." if fi else "No conflicts in this run.")
                + '</div>'
            )
        else:
            try:
                cblob = json.loads(conflicts_path.read_text(encoding="utf-8"))
                parsed = (cblob or {}).get("parsed") or {}
            except (OSError, json.JSONDecodeError):
                parsed = {}
            rows: list[str] = []
            for c in (parsed.get("conflicts") or []):
                topic = c.get("topic") or ""
                rows.append(f'<div class="ia-conflict-topic" style="color:var(--ink-1)">— {topic}</div>')
                for pos in (c.get("positions") or []):
                    claim = pos.get("claim") or ""
                    sup = pos.get("supported_by") or []
                    bare = sup[0].split("—")[0].strip().upper() if sup else ""
                    p = PERSONAS.get(bare, {"glyph": "•", "color": "#888"})
                    who = sup[0] if sup else "?"
                    rows.append(
                        f'<div class="ia-conflict-row">'
                        f'<span class="ia-conflict-who" style="color:{p["color"]}">{p["glyph"]} {who}</span>'
                        f'<span class="claim">{claim}</span></div>'
                    )
            body_html = '<div class="ia-conflict" style="border:0; background:none; margin:0; padding:0">' + "".join(rows) + '</div>'
    else:
        # "summary" — default: metric cards + stage bars + agent cards
        body_html = (
            f'{metrics_html}'
            f'{"".join(stages_html_parts)}'
            f'{"".join(agent_cards)}'
        )

    panel_html = (
        '<aside class="ia-panel">'
        f'<div class="ia-panel-head"><span>🔍</span><b>{t("head")}</b></div>'
        f'{tabs_html}'
        f'<div class="ia-panel-body">'
        f'{body_html}'
        '</div>'
        '</aside>'
    )
    st.html(panel_html)


def render_timeline_strip(run_dir: Path, lang: str = "fi") -> None:
    """Render the collapsed Aikajana strip — single-line summary above the answer.

    Replaces the live-status block once synthesis lands. Shows wall-clock
    duration, agent count, and the agents' persona glyphs in their colors.
    Designed as a clickable affordance to open the full activity log
    (currently it's purely informational; activity log is its own
    expander further down). Translates ui/redesign-handoff/parts.jsx ::
    TimelineStrip.
    """
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return
    try:
        m = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    duration = m.get("duration_seconds")
    if duration is None:
        return
    subagent_count = m.get("subagent_count", 0)
    stage = m.get("stage_timings") or {}
    per_subagent = stage.get("per_subagent") or []

    # Build the agent-glyph row from per-subagent entries (deduped — one
    # glyph per persona even if fan-out spawned multiple per company).
    seen_personas: list[str] = []
    for entry in per_subagent:
        persona = (entry.get("domain") or "").upper()
        if persona and persona not in seen_personas:
            seen_personas.append(persona)

    glyphs_html = "".join(
        f'<span style="color:{PERSONAS.get(p, {}).get("color", "#888")}">'
        f'{PERSONAS.get(p, {}).get("glyph", "•")} {p}</span>'
        for p in seen_personas
    )

    lab = "AIKAJANA" if lang == "fi" else "TIMELINE"
    agentit = "agenttia" if lang == "fi" else "agents"
    # Optional: stage-timing hint as the third inline metric. Keeps the
    # strip terse but tells the user where time went.
    fanout_s = stage.get("fanout_seconds")
    lead_s = stage.get("lead_seconds")
    extras = ""
    if fanout_s is not None and lead_s is not None:
        extras = (
            f' · <span class="lab">fan-out</span> '
            f'<span class="v">{fanout_s:.1f}s</span> · '
            f'<span class="lab">lead</span> '
            f'<span class="v">{lead_s:.1f}s</span>'
        )

    open_lab = "avaa loki ›" if lang == "fi" else "open log ›"
    html = (
        '<a class="ia-timeline" href="?panel=open&panel_tab=summary">'
        f'<span class="lab">{lab}</span> '
        f'<span class="v">{duration:.1f}s</span> '
        f'<span class="lab">·</span> '
        f'<span class="v">{subagent_count} {agentit}</span> '
        f'<span class="ag">{glyphs_html}</span>'
        f"{extras}"
        f'<span class="open">{open_lab}</span>'
        "</a>"
    )
    st.html(html)


# Inline footnote markers in answer text. LEAD's prompt should produce
# `[¹]` / `[²]` style numbered superscript markers at the end of sentences
# that are backed by specific tool calls. Here we post-process the
# rendered HTML to wrap those markers in persona-colored spans so they
# stand out (and later: become clickable to scroll the activity panel).
#
# The model isn't disciplined about always producing them, so this is
# best-effort styling: we match `[1]`, `[2]`, etc. (or unicode ¹²³),
# and color them by the persona that backed the claim — IF the surrounding
# text gave a hint via class="fn q/r/s/p" (translated from the redesign).
# When no hint is present we color them neutrally.
_FOOTNOTE_MARKER_RE = re.compile(
    r"\[(\d+)\]"  # plain ASCII [N] form — model emits this
)
_FOOTNOTE_PERSONA_HINT_RE = re.compile(
    r'<sup\s+class="fn-([qrsp])"[^>]*>(\d+)</sup>'  # hinted form
)


def _style_footnote_markers(html: str) -> str:
    """Wrap `[N]` markers in styled <sup> tags so they read as inline footnotes.

    `[1]` → `<sup class="ia-fn">[1]</sup>` (color-neutral baseline).
    Sentences with persona hints get persona-colored markers later.

    This is best-effort: the model sometimes uses `(1)` or `[1.]` or
    parenthetical citations; we only catch the canonical `[N]` form and
    leave others as-is. The risk of false positives (a literal `[1]` in
    a quoted text) is low in this domain.
    """
    return _FOOTNOTE_MARKER_RE.sub(
        r'<sup class="ia-fn">[\1]</sup>',
        html,
    )


def render_conflict_callout(run_dir: Path, lang: str = "fi") -> None:
    """Render a 🔀 callout when subagents had genuine disagreements.

    Reads `conflicts.json` and surfaces the `conflicts` array (NOT
    `agreements` or `isolated_claims` — those don't merit the callout).
    Renders a red-bordered box with topic + positions, each tagged with
    the supporting subagent's persona color.

    Translates ui/redesign-handoff/parts.jsx :: ConflictCallout. Renders
    above the answer body to draw attention before the user reads the
    synthesis.

    Threshold (v1): renders for any non-empty conflicts list. Future
    refinement: only render when LEAD's Päättely indicates the resolution
    is genuinely uncertain (`uncertain` slot has content) — for now we err
    on the side of surfacing, since hidden conflicts are the bigger risk.
    """
    conflicts_path = run_dir / "conflicts.json"
    if not conflicts_path.exists():
        return
    try:
        blob = json.loads(conflicts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    parsed = (blob or {}).get("parsed") or {}
    conflicts = parsed.get("conflicts") or []
    if not conflicts:
        return

    head_label = (
        "🔀 SUBAGENTIT ERIMIELTÄ"
        if lang == "fi"
        else "🔀 SUBAGENTS DISAGREE"
    )

    rows: list[str] = []
    for c in conflicts:
        topic = c.get("topic") or ""
        positions = c.get("positions") or []
        if not positions:
            continue

        # Topic header for each conflict
        rows.append(
            f'<div class="ia-conflict-topic">— {topic}</div>'
        )

        for pos in positions:
            claim = pos.get("claim") or ""
            supported_by = pos.get("supported_by") or []
            # Use the FIRST supporting subagent's persona for the chip color.
            # If multiple subagents support the same claim, persona ambiguous;
            # use the first as a representative.
            who_chip = ""
            if supported_by:
                first = supported_by[0]
                # Strip any "— Company" suffix to get the bare persona code.
                bare = first.split(" — ")[0].split("—")[0].strip().upper()
                p = PERSONAS.get(bare, {"glyph": "•", "color": "#888"})
                who_chip = (
                    f'<span class="ia-conflict-who" style="color:{p["color"]}">'
                    f'{p["glyph"]} {first}</span>'
                )
            else:
                who_chip = '<span class="ia-conflict-who" style="color:var(--ink-3)">?</span>'
            rows.append(
                f'<div class="ia-conflict-row">{who_chip}<span class="claim">{claim}</span></div>'
            )

    if not rows:
        return

    html = (
        f'<div class="ia-conflict">'
        f'<div class="ia-conflict-head">{head_label}</div>'
        f'{"".join(rows)}'
        f'</div>'
    )
    st.html(html)


def render_paattely_b(paattely: dict | None, lang: str = "fi") -> None:
    """Render LEAD's visible-reasoning block — either a 2×2 slot grid (when
    LEAD emitted JSON) or a styled prose block inside an expander (when
    LEAD emitted free prose, the current default).

    Schema accepted:
      - {disagree, resolution, uncertain, skipped}: structured JSON form.
        Each slot rendered as a labeled card in 2×2 grid; missing/null
        slots hidden.
      - {prose: str}: free-prose form. Rendered as styled italic block
        inside the same expander shell.

    Renders nothing if `paattely` is None or empty (graceful degradation —
    the answer body still reads fine if LEAD skipped the section).
    """
    if not paattely or not isinstance(paattely, dict):
        return

    header_label_outer = "Päättely" if lang == "fi" else "Reasoning"
    open_label = (
        "avaa nähdäksesi ajatusketju"
        if lang == "fi"
        else "open to see reasoning"
    )

    # Prose form: simpler shell, just the prose text inside the expander.
    if "prose" in paattely:
        body = paattely.get("prose") or ""
        if not body.strip():
            return
        # Render newlines as <br> for paragraph breaks; preserve as-is otherwise.
        try:
            from markdown_it import MarkdownIt
            md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
            body_html = md.render(body)
        except Exception:
            from html import escape as _esc
            body_html = "<p>" + _esc(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        html = (
            '<details class="ia-paattely-b ia-paattely-prose">'
            f'<summary class="ia-paattely-head">'
            f'<span>🧠</span><b>{header_label_outer}</b>'
            f'<span class="meta">{open_label}</span>'
            f'</summary>'
            f'<div class="ia-paattely-prose-body">{body_html}</div>'
            "</details>"
        )
        st.html(html)
        return

    # Structured JSON form: 2×2 slot grid.
    slots_present = {k: v for k, v in paattely.items() if v}
    if not slots_present:
        return

    # Slot definitions: (key, fi-label, en-label, icon)
    slot_defs = [
        ("disagree",   "ERIMIELISYYS",       "DISAGREEMENT",   "⚡"),
        ("resolution", "MITEN RATKAISIN",    "HOW I RESOLVED", "✓"),
        ("uncertain",  "EPÄVARMA",           "UNCERTAIN",      "?"),
        ("skipped",    "JÄTIN TEKEMÄTTÄ",    "SKIPPED",        "⊘"),
    ]

    rendered_slots: list[str] = []
    for key, fi_lab, en_lab, icon in slot_defs:
        value = slots_present.get(key)
        if not value:
            continue
        lab = fi_lab if lang == "fi" else en_lab
        # Each slot uses a CSS class with its own accent color (matches
        # the design tokens: disagree=red, resolution=amber, uncertain=blue,
        # skipped=muted).
        rendered_slots.append(
            f'<div class="ia-paattely-slot ia-paattely-{key}">'
            f'<div class="ia-paattely-lab"><span class="icn">{icon}</span> {lab}</div>'
            f'<div class="ia-paattely-body">{value}</div>'
            f"</div>"
        )

    if not rendered_slots:
        return

    header_label = "Päättely" if lang == "fi" else "Reasoning"
    meta = (
        f"{len(rendered_slots)} / 4 slottia · LEAD"
        if lang == "fi"
        else f"{len(rendered_slots)} / 4 slots · LEAD"
    )

    # 2×2 grid wrapped in <details> expander. Default closed so the answer
    # stays scannable; user clicks to open the structured reasoning view.
    html = (
        '<details class="ia-paattely-b">'
        f'<summary class="ia-paattely-head">'
        f'<span>🧠</span><b>{header_label}</b>'
        f'<span class="meta">{meta} · {open_label}</span>'
        f'</summary>'
        f'<div class="ia-paattely-grid">{"".join(rendered_slots)}</div>'
        "</details>"
    )
    st.html(html)


# Match the **💭 Perustelut:** callout at the start of LEAD's text.
# Captures the body up to the next double-newline (paragraph break).
_PERUSTELUT_RE = re.compile(
    r"^\s*\*\*\s*💭\s*(?:Perustelut|Reasoning)\s*:?\s*\*\*\s*"
    r"(?P<body>.+?)"
    r"(?=\n\s*\n|\n\s*#|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def extract_perustelut(text: str) -> tuple[str, str | None]:
    """Pull the **💭 Perustelut:** opening paragraph out of LEAD's response.

    Returns (cleaned_text, perustelut_body_or_None). The cleaned text has
    the matched callout removed so render_lead_answer can render the rest
    of the synthesis as the answer body, and the caller can render
    Perustelut as its own boxed callout (matching subagent "Ajatus:"
    boxes).
    """
    if not text:
        return text, None
    m = _PERUSTELUT_RE.search(text)
    if not m:
        return text, None
    body = m.group("body").strip()
    cleaned = (text[: m.start()] + text[m.end() :]).lstrip()
    return cleaned, body or None


def render_perustelut_box(body: str | None, lang: str = "fi") -> None:
    """Render the LEAD's `💭 Perustelut` as its own callout box.

    Designed to sit BELOW the 🧠 Päättely block (per user feedback: show the
    deeper reasoning first, then the meta-summary). Matches the visual
    weight of subagent `Ajatus:` boxes so the LEAD's meta line reads as
    a peer of the subagent thoughts, not as a header for the answer.
    """
    if not body:
        return
    label = "Perustelut" if lang == "fi" else "Reasoning"
    # Render markdown so any inline code / bold / italic in the body works.
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
        body_html = md.render(body)
    except Exception:
        from html import escape as _esc
        body_html = "<p>" + _esc(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    html = (
        '<div class="ia-perustelut-box">'
        f'<div class="ia-perustelut-lab">💭 {label}</div>'
        f'<div class="ia-perustelut-body">{body_html}</div>'
        "</div>"
    )
    st.html(html)


def render_lead_answer(text: str | None) -> None:
    """Render LEAD's synthesis answer body (Perustelut + Päättely already
    extracted by callers).

    NOTE on history (2026-05-07 redesign): This function used to also render
    the **💭 Perustelut:** callout inline as the first paragraph. Per user
    feedback, Perustelut and Päättely now render as their own boxes ABOVE
    the answer body via render_perustelut_box() and render_paattely_b().
    Callers should call extract_perustelut() first to strip the callout
    out of the text before passing it here.

    LEAD's prompt instructs it to start with ``**💭 Perustelut:** [meta-level
    reasoning]``. The CSS scopes its callout styling to ``.ia-lead-answer``,
    and gives the first paragraph (the bold-led reasoning line) an
    amber-bordered look distinct from the violet ``Ajatus`` traces of the
    subagents. This preserves visual hierarchy: ◆ LEAD = amber accent,
    subagents = their persona colors.

    The trailing ``## 💡 Voisit kysyä myös`` section is **removed** from the
    rendered HTML — those followup questions are surfaced separately by
    ``render_followup_chips`` so the UI can make them clickable buttons.

    Same Python-fence + stdout-wrap preprocessing as ``render_agent_output``
    so code blocks land styled correctly inside the answer body.

    Source links (``[Title](https://www.inderes.fi/...)`` produced by
    subagents and preserved by LEAD) are post-processed to open in a new
    tab via ``target="_blank"``.
    """
    if not text:
        text = "_(empty)_"
    main, _followups = split_followups(text)
    main = _ensure_python_fenced(main)
    main = _wrap_python_output(main)
    try:
        from markdown_it import MarkdownIt

        md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
        html_content = md.render(main)
    except Exception:
        from html import escape as _html_escape

        html_content = f"<pre>{_html_escape(main)}</pre>"
    html_content = _externalize_links(html_content)
    html_content = _style_footnote_markers(html_content)
    st.html(f'<div class="ia-lead-answer">{html_content}</div>')


def render_followup_chips(text: str | None, run_dir_name: str = "live") -> None:
    """Render LEAD's followup questions as small horizontal chip buttons.

    Three buttons sit side-by-side in equal columns so they're tertiary in
    visual hierarchy — "if you're curious, here are next steps" rather than
    "do this now". Click writes the question into
    ``st.session_state.pending_query``, which the main script picks up next
    rerun and treats as if the user had typed and submitted it.

    Buttons need unique keys per chat-message; we seed them with
    ``run_dir_name`` so old assistant messages can still surface their
    followups without colliding with newer ones.
    """
    if not text:
        return
    _, followups = split_followups(text)
    if not followups:
        return

    label = "💡 Voisit kysyä myös"
    st.markdown(
        f'<div class="ia-followup-label">{label}</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(followups))
    for i, question in enumerate(followups):
        with cols[i]:
            key = f"sugg_{run_dir_name}_{i}"
            if st.button(
                question,
                key=key,
                use_container_width=True,
                type="secondary",
            ):
                st.session_state["pending_query"] = question
                st.rerun()


# ---------------------------------------------------------------------------
# Inderes recommendation badge — extracted from QUANT's structured output
# ---------------------------------------------------------------------------

# Maps recommendation labels to a persona color from theme.css.
_RECOMMENDATION_COLORS = {
    # bullish
    "BUY":         "var(--ia-green)",
    "OSTA":        "var(--ia-green)",
    "ACCUMULATE":  "var(--ia-green)",
    "LISÄÄ":       "var(--ia-green)",
    "OVERWEIGHT":  "var(--ia-green)",
    # neutral
    "HOLD":        "var(--ia-amber)",
    "PIDÄ":        "var(--ia-amber)",
    "NEUTRAL":     "var(--ia-amber)",
    # bearish
    "REDUCE":      "var(--ia-red)",
    "VÄHENNÄ":     "var(--ia-red)",
    "SELL":        "var(--ia-red)",
    "MYY":         "var(--ia-red)",
    "UNDERWEIGHT": "var(--ia-red)",
}


def extract_inderes_view(quant_text: str | None) -> dict | None:
    """Pull recommendation / target / risk / EPS out of QUANT's structured text.

    QUANT's prompt mandates an ``INDERES VIEW:`` block with a few fixed
    fields. We don't enforce a strict YAML parser — agents wobble — but
    field-by-field regex pulls out what's there and leaves the rest as None.
    Returns None if no recommendation field could be parsed (no badge to
    render).
    """
    import re

    if not quant_text:
        return None
    rec_match = re.search(
        r"recommendation:\s*([A-Za-zÄäÖö]+)",
        quant_text,
        flags=re.IGNORECASE,
    )
    tgt_match = re.search(
        r"target_price:\s*€?\s*([\d,.]+)\s*€?",
        quant_text,
        flags=re.IGNORECASE,
    )
    risk_match = re.search(
        r"risk_score:\s*([\d/.]+)",
        quant_text,
        flags=re.IGNORECASE,
    )
    eps_match = re.search(
        r"next_year_eps:\s*€?\s*([\d,.]+)",
        quant_text,
        flags=re.IGNORECASE,
    )
    if not rec_match:
        return None
    return {
        "recommendation": rec_match.group(1).upper(),
        "target_price": tgt_match.group(1) if tgt_match else None,
        "risk_score": risk_match.group(1) if risk_match else None,
        "next_year_eps": eps_match.group(1) if eps_match else None,
    }


def render_recommendation_badge(run_dir: Path, lang: str = "fi") -> None:
    """Render Inderes' recommendation badge above the LEAD synthesis.

    Reads QUANT's subagent JSON, extracts the INDERES VIEW block, and
    renders a single-line badge with persona colors driven by the
    recommendation (BUY → green, HOLD → amber, REDUCE/SELL → red).

    Only renders when there is **exactly one** QUANT subagent file for the
    run — i.e. a single-company query. For comparisons (fan-out per
    company → multiple QUANT files) the badge would have no clear
    referent and the synthesis already shows both companies' calls in a
    table; rendering "the first company's badge" was confusing in user
    testing, so we skip the badge entirely in that case.

    No-ops if QUANT didn't run for this query or didn't surface a
    recommendation in its INDERES VIEW block.
    """
    quant_files = list(run_dir.glob("subagent-*-quant.json"))
    if len(quant_files) != 1:
        # 0 = QUANT not invoked; >1 = comparison query, info already in
        # the synthesis table. Either way no clean single-company badge
        # to show.
        return
    try:
        sa = json.loads(quant_files[0].read_text(encoding="utf-8"))
    except Exception:
        return
    view = extract_inderes_view(sa.get("text"))
    if not view:
        return

    company = sa.get("company") or ""
    color = _RECOMMENDATION_COLORS.get(view["recommendation"], "var(--ia-text)")
    label = "INDERESIN NÄKEMYS" if lang == "fi" else "INDERES VIEW"
    if company:
        label = f"{label} · {company.upper()}"

    parts = [
        f'<span class="ia-rec-mark" style="color:{color}">{view["recommendation"]}</span>'
    ]
    if view.get("target_price"):
        parts.append(f'<span class="ia-rec-tgt">€{view["target_price"]}</span>')
    if view.get("risk_score"):
        risk_lbl = "Riski" if lang == "fi" else "Risk"
        parts.append(f'<span class="ia-rec-risk">{risk_lbl} {view["risk_score"]}</span>')
    if view.get("next_year_eps"):
        eps_lbl = "Ensi vuoden EPS" if lang == "fi" else "Next-year EPS"
        parts.append(f'<span class="ia-rec-eps">{eps_lbl} €{view["next_year_eps"]}</span>')

    html = (
        f'<div class="ia-rec">'
        f'<div class="ia-rec-label">📌 {label}</div>'
        f'<div class="ia-rec-row">{" · ".join(parts)}</div>'
        f'</div>'
    )
    st.html(html)


def render_full_narrative(run_dir: Path, lang: str = "fi") -> None:
    """Render the full narrative.md (routing + tool-call timeline + subagent
    answers) in a scrollable container at the bottom of the trace.

    Same data as the per-section breakdown above, but in one easy-to-scan
    document — useful for getting a feel for how the agent progressed (which
    tools it called, in what order, how long each took).
    """
    narrative_path = run_dir / "narrative.md"
    if not narrative_path.exists():
        return
    text = narrative_path.read_text(encoding="utf-8")
    title = "TÄYDELLINEN AJOLOKI" if lang == "fi" else "FULL RUN LOG"
    sub = (
        "Reititys, työkalukutsujen aikajana ja subagenttien raakat vastaukset."
        if lang == "fi"
        else "Routing, tool-call timeline, and raw subagent answers."
    )
    try:
        from markdown_it import MarkdownIt

        text = _ensure_python_fenced(text)
        text = _wrap_python_output(text)
        md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
        html_content = md.render(text)
    except Exception:
        from html import escape as _html_escape

        html_content = f"<pre>{_html_escape(text)}</pre>"
    st.html(
        f'<div class="ia-narrative-h">{title}</div>'
        f'<div class="ia-narrative-sub">{sub}</div>'
        f'<div class="ia-narrative">{html_content}</div>'
    )





# ---------------------------------------------------------------------------
# Statusbar — pinned at the bottom of the main column
# ---------------------------------------------------------------------------

# Per-domain action-verb phrases used in the live status box. Key matches
# the lowercase domain enum value (quant / research / sentiment / portfolio).
DOMAIN_VERBS_FI: dict[str, str] = {
    "quant":     "etsii tunnuslukuja ja laskee Pythonissa",
    "research":  "kahlaa Inderesin analyysiarkistoa",
    "sentiment": "tarkistaa sisäpiirin kaupat ja foorumin",
    "portfolio": "tarkastaa Inderesin mallisalkun",
}
DOMAIN_VERBS_EN: dict[str, str] = {
    "quant":     "fetching fundamentals + Python math",
    "research":  "trawling Inderes' research archive",
    "sentiment": "checking insider trades + forum buzz",
    "portfolio": "inspecting Inderes' model portfolio",
}


class CustomStatus:
    """Drop-in replacement for ``st.status`` that doesn't use Material Symbols.

    Same surface API (``write``, ``update``, context-manager) but renders a
    plain ``<details>``/``<summary>`` block via ``st.markdown(..., unsafe_html)``.
    No icon font race, no transition animations, no "ieckalmis"-style
    overlap. State (running / complete / error) drives the left-border color
    and a label-side dot indicator.

    Use just like st.status::

        status = CustomStatus("Käsittelen kysymystäsi…", expanded=True)
        status.write("⚙️  Reitittäjä…")
        status.write('<span style="color:#F5B942">◆ LEAD</span>', html=True)
        status.update(label="Valmis", state="complete", expanded=False)
    """

    def __init__(self, label: str, expanded: bool = True) -> None:
        self._placeholder = st.empty()
        self._label = label
        # Each entry is (kind, content). kind="text" gets HTML-escaped on
        # render; kind="html" is trusted raw HTML (used for persona-styled
        # status lines that need inline color via <span style>).
        self._lines: list[tuple[str, str]] = []
        self._state = "running"
        self._expanded = expanded
        self._render()

    def write(self, text: str, html: bool = False) -> None:
        kind = "html" if html else "text"
        self._lines.append((kind, str(text)))
        self._render()

    def update(
        self,
        label: str | None = None,
        state: str | None = None,
        expanded: bool | None = None,
    ) -> None:
        if label is not None:
            self._label = label
        if state is not None:
            self._state = state
        if expanded is not None:
            self._expanded = expanded
        self._render()

    def __enter__(self) -> "CustomStatus":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def _render(self) -> None:
        details_attr = " open" if self._expanded else ""
        rendered_lines = []
        for kind, content in self._lines:
            rendered_lines.append(content if kind == "html" else _esc(content))
        body_html = "<br>".join(rendered_lines)
        html = (
            f'<details class="ia-cs ia-cs-{_esc(self._state)}"{details_attr}>'
            f'<summary><span class="ia-cs-dot"></span>'
            f'<span class="ia-cs-label">{_esc(self._label)}</span></summary>'
            f'<div class="ia-cs-body">{body_html}</div>'
            f'</details>'
        )
        # st.html() would scope this away; we want page-level CSS to apply.
        self._placeholder.markdown(html, unsafe_allow_html=True)


def render_statusbar(meta: dict | None = None, lang: str = "fi") -> None:
    """Tech status footer — only system info, no disclaimer text.

    The legal notice is already in the sidebar disclaimer; repeating it
    here would be the fourth time the user sees the same warning.
    """
    meta = meta or {}
    errors = meta.get("subagent_errors", 0)
    fbacks = meta.get("fallback_events", 0)
    err_lbl = "errors" if lang == "en" else "virheet"
    fb_lbl  = "fallbacks" if lang == "en" else "fallbackit"

    html = (
        '<div class="ia-statusbar">'
        '<span class="ia-hot">● mcp.inderes.com</span>'
        '<span>│ gemini-3.1-flash-lite</span>'
        f'<span>│ {err_lbl}: <span class="ia-warn">{errors}</span></span>'
        f'<span>│ {fb_lbl}: {fbacks}</span>'
        '<span class="ia-spacer"></span>'
        '</div>'
    )
    st.html(html)


# ---------------------------------------------------------------------------
# Sidebar panels — agent personas + project description
# ---------------------------------------------------------------------------

def render_personas_panel(lang: str = "fi") -> None:
    """Render the 5-agent roster in the sidebar with glyphs, colors, descriptions."""
    title = "AGENTIT" if lang == "fi" else "AGENTS"
    rows = []
    for code, p in PERSONAS.items():
        role = p["role_en"] if lang == "en" else p["role_fi"]
        desc = p["desc_en"] if lang == "en" else p["desc_fi"]
        rows.append(
            f'<div class="ia-persona">'
            f'<div class="ia-pg" style="color:{p["color"]}">{p["glyph"]}</div>'
            f'<div>'
            f'<div class="ia-pn" style="color:{p["color"]}">{code}</div>'
            f'<div class="ia-pr">{_esc(role)}</div>'
            f'<div class="ia-pd">{_esc(desc)}</div>'
            f'</div></div>'
        )
    html = f'<div class="ia-side-h">{title}</div>' + "".join(rows)
    st.html(html)


def render_about_panel(lang: str = "fi") -> None:
    """Architecture summary in the sidebar.

    Focuses on HOW the system works — routing, MCP tools, synthesis. The
    legal "not Inderes-affiliated" part lives in render_sidebar_disclaimer
    above, not here.
    """
    title = "ARKKITEHTUURI" if lang == "fi" else "ARCHITECTURE"
    if lang == "fi":
        intro = (
            "LEAD reitittää kysymyksen 1–4 subagentille, jokainen kutsuu "
            "Inderes MCP:tä omilla työkaluillaan. LEAD kokoaa vastaukset "
            "yhdeksi synteesiksi."
        )
        kv = [
            ("STACK", "MAF + Gemini Flash"),
            ("DATA", "Inderes MCP", "amber"),
            ("LOG", "narrative.md / ajo"),
            ("STATUS", "● Live", "green"),
        ]
    else:
        intro = (
            "LEAD routes the query to 1–4 subagents, each calls the "
            "Inderes MCP with its own toolset. LEAD synthesises the answers."
        )
        kv = [
            ("STACK", "MAF + Gemini Flash"),
            ("DATA", "Inderes MCP", "amber"),
            ("LOG", "narrative.md / run"),
            ("STATUS", "● Live", "green"),
        ]
    rows = ""
    for item in kv:
        k, v = item[0], item[1]
        cls = item[2] if len(item) > 2 else ""
        rows += f'<div class="ia-kv"><span class="k">{k}</span><span class="v {cls}">{_esc(v)}</span></div>'
    html = (
        f'<div class="ia-side-h">{title}</div>'
        f'<div class="ia-about"><p>{intro}</p>{rows}</div>'
    )
    st.html(html)


def _esc(s: Any) -> str:
    """Minimal HTML escape so user-supplied strings can't break our markup."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
