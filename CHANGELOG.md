# Changelog

All notable changes to this project. Format roughly follows
[Keep a Changelog](https://keepachangelog.com); the project does not yet follow
[SemVer](https://semver.org) strictly.

## [unreleased] — 2026-05-10

### Added — eval foundation (Tier 0 + Tier 1)

Two-layer eval scaffold built in one sprint. Tier 0 indexes every
historical run for fast diagnostic queries; Tier 1 grades captured
runs against a golden case set with an LLM-judge.

- **`scripts/build_runs_index.py`** (`9bcf4f0`) — walks
  `~/.inderes_agent/runs/<ts>/` and writes a SQLite database with
  two tables (`runs`, `tool_calls`). Idempotent. 183 existing runs +
  457 tool calls indexed in ~1 s.
- **`evals/sample_queries.sql`** — 10 diagnostic SQL queries, each
  targeting a specific weakness category (under-routed comparisons,
  noise runs, repeat queries, conflict-detector hit rate, tool error
  rates, latency outliers).
- **`evals/findings_2026-05-09.md`** — 7 systemic weaknesses surfaced
  on the first diagnostic pass.
- **`evals/judge_selection.md`** — benchmark-backed model choice
  (Vectara HHEM v2, RewardBench 2, Arena-Hard, JudgeBench). Gemini
  2.5 Pro picked over Sonnet 4.5 / GPT-5 because reasoning models
  hallucinate >10 % on grounded summarisation — exactly the failure
  mode we cannot import into a finance-research judge.
- **`evals/golden.yaml`** (`8971f66`) — 7 cases, each tied to a real
  finding. Hard (deterministic) + soft (judge-graded) assertions.
- **`evals/judge.py`** — `JudgeBackend` Protocol + `GeminiJudge` impl.
  Designed so GPT-4.1 can be added later as cross-family validator
  without runner changes.
- **`evals/runner.py`** — orchestrator. Picks most-recent matching
  run from index, runs hard expressions in sandboxed eval(), calls
  judge for soft criteria, writes timestamped report.

### Added — fabrication guard at orchestration boundary

- **`workflows.py:_detect_fabrication`** (`870749a`) — universal
  trust-killer defence. If a subagent emits ≥300 char domain-loaded
  text but ZERO MCP calls, the result is replaced with
  `error="fabricated_no_tool_calls: ..."`. Closes the trust-killer
  pattern from run `20260502-205706-108` ("Vincit: VÄHENNÄ 1,25 €"
  fabricated).
- **`synthesis.py:_no_data_response`** — when ALL subagents errored,
  short-circuit to a fixed honest "ei löytynyt"-style answer. No
  euros, no recommendations, no fabricated context.
- 14 unit tests in `tests/test_fabrication_guard.py`.

### Added — agent-prompt HARD GATE on all 5 subagents

Universal prompt-side enforcement that all subagents MUST execute
their MCP tool calls before emitting output.

- `valuation.md` (`08e7e93`), `sentiment.md` (`d36dd72`),
  `research.md` + `quant.md` + `portfolio.md` (`2039967`) — same
  pattern, agent-specific tool lists. Forbidden-numbers-from-memory
  clause. "Yhtiö ei ole seurannassa" treated as a fine finding when
  it's true (Konecranes).
- Verified: 12/12 subagent dispatches in a 4-bank comparison
  (Nordea/Aktia/Ålandsbanken/OmaSP) made tool calls, zero
  fabrication-guard rejections.

### Added — Tila C activation banner for LEAD synthesis

- **`synthesis.py`** (`08e7e93`) — when the valuation engine actually
  computed, pre-pend a high-visibility banner to LEAD's prompt
  enumerating the 4 required Tila C section headings. The banner is
  the FIRST thing LEAD reads, before the 600-line prompt body.
  Pre-fix Tila C reliability ~2/3; post-fix 5/5 verified.
- 4 unit tests in `tests/test_tila_c_banner.py`.

### Fixed — comparison routing floor

- **`router.py`** (`5e5dea7`) — both prompt rule (comparison MUST
  include `{quant, research, sentiment}`) AND `_enforce_comparison_floor()`
  post-processor as belt-and-braces. The previous few-shot example
  for "Compare Sampo and Nordea" was the bug source itself, showing
  `["quant"]` only.
- 5 unit tests cover both layers.

### Fixed — päättely structured-form lift + conflict-naming

- **`synthesis.py:_extract_paattely`** (`80c6fd0`) — when prose
  conforms to the 4-paragraph spec, lift to structured slots
  (`disagree`, `resolution`, `uncertain`, `skipped`). The lead.md
  spec was perfect; the parser was the missing link. 0 of 183
  historical runs produced JSON form, but 55 had perfect
  4-paragraph prose.
- **`scripts/reclassify_paattely.py`** — applies same lift
  retroactively. 56/59 historical prose päättelys converted.
- **`lead.md`** — HARD REQUIREMENT for conflict naming.
  Päättely §1 MUST name the conflict topic verbatim, §2 MUST state
  which value was kept and why.

### Fixed — trend classifier severe-decline branch

- **`roe_selection.py`** (`152c3bf`) — UPM-Kymmene regression. ROE
  `[12.7, 13.1, 3.3, 3.9, 4.5] %` (delta -48 %) was misclassified
  vakaa because lfy ticked up within the depressed window. **Three
  UPM runs failed in a row.** Fix: severe-decline branch fires on
  `delta < -0.20` regardless of LFY position. Symmetric severe-rise
  branch added.
- 5 new tests in `tests/valuation/test_roe_selection.py`.

### UI — major polish pass

- **`render_feature_toggles`** — collapsed `<details>` expander
  matching results-section "AVAA PÄÄTTELY ›" look (caps-micro amber
  summary, mono-meta body).
- **FI / EN switcher** — tiny inline toggle in titlebar via
  `?lang=` query param.
- **Plan expander** — converted to `st.button + session_state` after
  `<details>` proved unreliable in `chat_message`. Matches AVAA LOKI
  / AVAA PÄÄTTELY visually.
- **Material Icons leak fix** — `:not([class*="material"])` selectors
  prevent "keyboard_arrow_down" text from leaking through.
- **Statusbar trim** — dropped `virheet: 0 / fallbackit: 0` noise.
- **Tier label clarity** — radio options now name the model exactly
  ("Vakio (Gemini 3.1 Flash Lite)", etc.). Native `?` help icon for
  trade-off explanations.

### Documentation

- **`docs/sprint_lessons_2026-05-09.md`** — long-form session
  retrospective: 7 lesson categories, chronological commit
  walkthrough, user emotional arc, re-prioritised backlog rationale.
- **`BACKLOG.md §0`** — re-prioritised. Plotly charts promoted to
  Wk 1 #1 (user-stated top priority). Hard limits + 👍/👎 Wk 1.
  Reflexion + footnotes Wk 2. Devil's advocate demoted to Wk 4+.

---

## [unreleased] — 2026-05-09

### Added — alternative valuation feature (opt-in Greenwald-Gordon)

A user-controlled fifth specialist subagent (`aino-valuation`) plus a
deterministic Python valuation engine, integrated end-to-end through the
LEAD synthesis. Activated via the *"Käytä vaihtoehtoista arvonmääritystä"*
sidebar toggle. Default flow remains unchanged — when the toggle is off,
no new code paths execute (verified via the LEAD prompt's *Tila A* mode
which explicitly tells the model to ignore valuation guidance).

**Methodology**: an 8-step Greenwald-Gordon hybrid. `FV = ((ROE−g)/(k−g)) ×
BVPS`, EPV = `(ROE/k) × BVPS`, growth value = `FV − EPV` for laatuyhtiöt
(ROE > k) and 0 otherwise. Quality classification with a ±2% buffer around
k (laatu / keskinkertainen / tuhoutuva). Dual implied values surface that
Gordon's equation has two unknowns (ROE, g) but one constraint (price):
`implied_g` (holds ROE) and `implied_roe` (holds g), shown side-by-side so
neither dimension is presented as "the" market reading.

**Components**:
- `src/inderes_agent/valuation/engine.py` — pure-Python deterministic
  computation, validated against the user's `Arvonmääritys2023.xlsx`
  Data-sheet outputs for 10 hand-picked Finnish companies (laatu /
  tuhoutuva mix), within 0.02€ tolerance per cell
- `src/inderes_agent/valuation/roe_selection.py` — single source of truth
  for the **sustainable-ROE rule** (median dominates the mean for "typical
  year" thinking; 5y_median for vakaa/nouseva, min(3y_median,
  trend_weighted) for laskeva). Used both by the agent prompt
  (documentation) and by the parser (validation; agent can't silently
  mis-compute medians)
- `src/inderes_agent/valuation/parser.py` — strict JSON validator with
  Levenshtein-≤2 fuzzy match for `*_rationale` field typos (sibling
  protection: `g_rationale` cannot absorb `k_rationale`'s value)
- `src/inderes_agent/agents/valuation.py` + `prompts/valuation.md` —
  `aino-valuation` agent that fetches BVPS, ROE history, and current
  share price via `get-fundamentals` and emits structured JSON. The
  agent **never does math** — it extracts parameters and rationale; the
  deterministic engine handles all computation
- `src/inderes_agent/orchestration/synthesis.py` —
  `_process_valuation_subagents()` runs the agent JSON through parser
  and engine; `_format_valuation_block()` renders results for the LEAD
  prompt with edge-case warnings for absurd safety-margins
- `src/inderes_agent/orchestration/router.py` —
  `query_has_valuation_intent()` heuristic gates the toggle, so purely
  qualitative questions ("explain why...") don't trigger an unwanted
  Greenwald-Gordon table. Conservatively biased — false negatives are
  far less damaging than false positives
- `src/inderes_agent/agents/prompts/lead.md` — three-state synthesis
  guide: A (toggle off, default flow unchanged), B (parse error,
  honest skip with explicit "do not hand-compute Gordon" guards), C
  (success, 4-section structure: Yhteenveto / Inderesin näkemys / Oma
  arvonmääritys / Vertailu, plus a static methodology infobox)

**Tool-call guard at the orchestration boundary**

Production run `20260508-205057-769` ("entäs jos roe olisi 13%")
demonstrated a trust-killer hallucination: Flash Lite emitted a
fully-formed JSON output with **zero MCP calls**, inventing
`company_id`, current price, and ROE history from conversation context.
Engine math then produced a confident but fabricated +18.2% safety
margin shown to the user.

Defense: `_process_valuation_subagents` counts `get-fundamentals` calls
*before* parsing. Zero calls → reject as hallucination, route into
LEAD's Tila B with an honest "agent did not query MCP" message.
Prompt-level "always fetch fresh data" instructions don't suffice —
structural enforcement at the orchestration boundary is the only
reliable defense.

**Test coverage** (108 new tests, 146 total green):
- 26 engine unit tests (math, edge cases, dual implied)
- 20 Excel-parity tests (10 companies × 2 assertion sets)
- 21 sustainable-ROE rule tests (medians, trend, validation)
- 35 parser tests (validation, typo tolerance, sibling protection)
- 10 tool-guard + edge-case warning tests
- 33 router intent-gate tests (explicit valuation queries fire,
  qualitative queries don't, Finnish morphology variants)

**Known limitation** (deferred to follow-up): per-company fan-out for
multi-company comparisons currently produces JSON arrays from each
subagent (each agent thinks the whole comparison is its scope) — parser
expects single objects, so all three companies' valuations fail to
parse and LEAD falls into Tila B for the whole query. Single-company
valuations work correctly. Tracked in `BACKLOG.md`.

## [previous] — 2026-05-06

### Added — pre-synthesis conflict detection

A new LLM step runs between subagent execution and lead synthesis. The
detector reads all subagent outputs and emits strict JSON with three
buckets: **agreements** (claims 2+ subagents support), **conflicts**
(claims subagents disagree on, with positions per side), and
**isolated_claims** (single-source factual claims that, if hallucinated,
would mislead). The lead synthesis prompt now receives this structured
report alongside the raw subagent outputs and explicit instructions on
how to use it. Persisted as `conflicts.json` in every run dir.

This is the BACKLOG #1 plan-then-execute extension — it turns the
emergent multi-subagent self-correction observed in
`evals/known-cases.md` Case 003 into something *explicit and loggable*
rather than implicit in the lead's training-data priors.

Empirically observed on a 10-subagent Puuilo-vs-Tokmanni-vs-Kesko run:
the detector caught a real disagreement between two `sentiment` branches
(one saw the Joller insider trade, the other did not) and the lead
resolved it explicitly in the synthesis preamble. Without the explicit
conflict map, that disambiguation would happen quietly via priors, if
at all.

### Fixed — Streamlit Cloud installer regression

The previous commit (d8186d2) accidentally checked `uv.lock` into the
repo via `git add -A`. Streamlit Cloud's installer-selection heuristic
prefers `uv-sync uv.lock` over `requirements.txt` when both exist, and
uv-sync skipped the `[ui]` extra — so streamlit got uninstalled from
the cloud venv, breaking the app with `streamlit: command not found`.
Removed `uv.lock` from the repo and gitignored it; `requirements.txt`
stays the documented source of truth.

## [previous batch] — 2026-05-02 → 2026-05-05

A heavy iteration on the Streamlit UI plus substantial operational
improvements to the agent layer and OAuth/cloud infrastructure. No
breaking changes.

### Added — public-safe error UI on auth-expired card

- **Embedded demo video** on the auth-expired card so first-time visitors
  past the password gate can still see what the tool does even when it
  can't run live.
- **"📧 Pyydä yhteyden korjaamista" button** that increments a recovery
  counter persisted in the same gist mirror used for tokens. Operator
  sees the counter on the card after a session death and knows people
  are waiting; visitor sees they're not the first to hit the wall.
- **Public-safe error masking**: `HeadlessAuthError` (and any exception
  whose message hints at auth/session problems) is rendered as a clean
  "Järjestelmä alhaalla — yhteys täytyy autentikoida uudelleen" card
  rather than a raw traceback that exposed local paths and recovery
  scripts.
- **Theme-matching chat avatars** (👤 user, 🔶 assistant) replacing
  Streamlit's default cartoon icons.
- **Absolute Helsinki-time timestamps** on the recovery counter
  ("Viimeisin: 04.05.2026 klo 20.34") instead of relative phrases that
  re-render inconsistently across day boundaries.

### Added — infrastructure (durable session keepalive)

- **`scripts/relogin.sh`** — one-shot recovery script that wraps the
  full flow: stash old tokens, run agent (browser opens for fresh
  login), sync to gist, trigger cron to verify, print a clear
  ✅/⚠ verdict.
- **`scripts/sync_local_tokens_to_gist.py`** — pushes local
  `~/.inderes_agent/tokens.json` to the gist via `gh` CLI (no
  GH_TOKEN needed in `.env`). Runs in `relogin.sh` and stand-alone.
- **MCP keepalive in cron worker** — after each successful Keycloak
  refresh, the cron also makes one authenticated MCP `initialize`
  call. Diagnostic test for whether Keycloak's idle timer treats
  /token vs MCP API activity differently (verdict: it doesn't —
  but the test confirmed the assumption).
- **Cron cadence `*/15` → `*/5`** with a documented caveat that
  GitHub Actions free-tier scheduling is best-effort and may skip
  runs under load. *Real* reliable scheduling moved to an external
  service (cron-job.org) that hits the same workflow via the
  GitHub API.
- **Smart cron notification** — exit 1 only on the ok→failed
  transition (tracked via `_last_refresh_status` field in the gist),
  exit 0 while ongoing-failed. Result: GitHub emails the maintainer
  exactly *once* when a session dies, not every 5 minutes.
- **Cross-cron-cloud rotation race recovery** in `oauth.py` — when
  cloud's in-memory refresh_token is invalidated by cron rotation,
  cloud now force-pulls the gist and retries with the fresh token
  before raising `HeadlessAuthError`.

### Added — empirical Inderes Session Max measurement

- **Confirmed: Inderes Keycloak SSO Session Max = exactly 10 hours
  wall-clock from login.** Measured by holding a fresh session alive
  with cron-job.org-driven token rotation every 5 minutes. Rotation
  succeeded ~120 times in a row, then failed with `invalid_grant:
  Token is not active` at minute 601. Documented in
  `LESSONS.md` and `MULTI_AGENT_ARCHITECTURE.md` as a worked
  example of "session lifetime is set by the IdP, not by you."

### Added — documentation

- **`MULTI_AGENT_ARCHITECTURE.md`** — generic layered-model primer
  for multi-agent systems. Five layers (Surface / Brain / Action /
  Data / Harness) plus two cross-cutting planes (Evals & Observability,
  Governance) plus memory tiers, with this project as a worked
  example throughout. Companion to `ARCHITECTURE.md` (which covers
  the concrete current implementation file by file).

### Fixed

- **URL hallucination** in source-link rendering. Agents had been
  generating `/fi/tapahtumat`-style fabricated category-root URLs
  when a tool didn't return a per-item URL. Tightened both
  `sentiment.md` and `lead.md` prompts with an explicit known-good
  section-roots block (calendar, forum, companies, mallisalkku) and
  a "common hallucinations to avoid" list.
- **Empty-result blindness** on calendar queries. Agents called
  `list-calendar-events` with `types=[INTERIM_REPORT, BUSINESS_REVIEW]`,
  got 0 results because the type filter was over-narrow, and
  reported "ei tapahtumia" even though the calendar visibly had 5+
  earnings reports. Fix: prompt now recommends omitting `types`
  filter for "what's today" -style queries, plus a new "empty-result
  skepticism" rule under sentiment.md `## Rules` mandating one
  broader retry before reporting nothing.
- **`TokenSet.from_dict` rejecting unknown fields**. The smart cron
  notification (above) added `_last_refresh_status` and
  `_last_refresh_at` to the gist's tokens.json, which made the
  cloud's `TokenSet.from_dict()` raise `unexpected keyword argument`
  on parse. Fixed by filtering to the dataclass's known fields
  before construction — forward-compatible to future bookkeeping
  fields.
- **CachedWidgetWarning on auth-expired card**. The `_bootstrap()`
  function was decorated with `@st.cache_resource` and called
  `_render_auth_expired()` (containing widgets) inside its except
  branch. Streamlit cache prevents widgets from re-rendering on
  cache hits. Refactored: bootstrap-auth step is cached, the
  auth-expired UI rendering happens outside the cache.
- **Chat avatars rendered as broken file paths**. First attempt
  used `❯` and `◆` (Unicode dingbats), which Streamlit doesn't
  detect as emoji and falls through to file-path interpretation,
  crashing with `FileNotFoundError`. Replaced with proper emoji.

### Added — Streamlit UI ("Trading Desk" visual layer)

### Added — UI polish (recommendation, followups, sources, status)

- **Inderes recommendation badge** rendered above the LEAD synthesis when the
  router has resolved a single primary company (PR #28). Pulls
  `recommendation` + `target_price` from `get-inderes-estimates` and renders
  them as a colored chip (green / amber / red) so the user sees Inderes' own
  call before reading the synthesis prose.
- **Follow-up suggestion chips** below the synthesis (PR #28): LEAD generates
  three short, clickable next-question chips ("💡 Voisit kysyä myös: …"). The
  chips are rendered as Streamlit buttons that re-submit on click. The chips
  list comes from a structured tail block in the LEAD prompt; if the model
  omits it, the UI just doesn't render chips.
- **Clickable Inderes source links** in the synthesis "Lähteet:" footer and
  in each subagent's output (PR #29). Tool results are post-processed so any
  `pageUrl` / `url` / `threadUrl` field is woven back into the markdown as a
  proper link to inderes.fi rather than a bare tool-name token.
- **Persona-styled, descriptive live status box** during query execution
  (PR #23): replaces the generic "LEAD"/"Subagentit" labels with one-line
  state descriptions in the persona color, e.g. `▲ aino-quant: hakee P/E:tä
  ja tavoitehintaa…`. Driven by phase + classification context so the user
  can read what's happening rather than just seeing a spinner.

### Added — infrastructure (durable OAuth on Streamlit Cloud)

- **GitHub Action cron `refresh-inderes-tokens.yml`** runs every 15 min and
  refreshes the Inderes OAuth tokens via the gist mirror (PR #25). Solves the
  Streamlit Cloud failure mode where containers idle long enough that the
  refresh-token rotation chain breaks. The cron keeps the Keycloak SSO
  session warm without requiring a real user query. Same gist (configured by
  `INDERES_TOKENS_GIST_ID`) is shared between the cron and the running app;
  the app pulls fresh tokens on each cold start.
- **Force gist pull on first auth call** (PR #27): the previous `pull only on
  cache miss` policy meant a stale local `tokens.json` survived restarts and
  blocked the rotation chain. Now we always pull the gist version once at
  startup; the local file is only authoritative once we've confirmed it
  matches the gist.
- **Debug logging for secrets→env bridge + gist visibility** (PR #26): logs
  whether each Streamlit secret bridged to env, and whether the gist ID/token
  are visible at OAuth time. Made it possible to diagnose
  "tokens persist locally but not on cloud" failures without speculation.

### Added — Streamlit UI ("Trading Desk" visual layer)

- Bloomberg-style dark theme: JetBrains Mono throughout, amber accents, agent
  glyphs (◆ LEAD, ▲ QUANT, ■ RESEARCH, ● SENTIMENT, ✦ PORTFOLIO).
- Hero panel with brand equation `INDERES + MCP + AGENTIT = INSIGHTS` + agent
  roster.
- Sidebar: red disclaimer at top (single source of truth for legal notice),
  architecture summary, GitHub CTA, agent personas with descriptions,
  recent runs list.
- Routing card with colored domain pills + free-form `PERUSTELU` (pink/violet
  accent so prose reasoning is distinct from categorical fields).
- Per-agent rows in the activity log expander: glyph + role + model + status
  badge; full structured output renders inline below each row.
- `CustomStatus` widget replaces `st.status` — pulsing CSS-only dot
  indicator for state, no Material Symbols icon-font race conditions.
- Markdown table + strikethrough rendering enabled for subagent output.
- Python sandbox stdout (e.g. `print(df)` results) auto-detected and wrapped
  in a green-bordered ```output``` block, distinct from the blue-bordered
  source-code blocks.
- `.streamlit/config.toml` sets primary color to amber so Streamlit's own
  chrome (chat input focus ring, progress bars) is on-brand.

### Added — agent reasoning visibility (#3 from BACKLOG.md)

- Mandatory `**Ajatus:**` thought-trace line at the top of every subagent
  response — surfaces tool-selection reasoning before the structured answer.
  Violet-bordered italic styling in `.ia-agent-output`.
- Mandatory `**💭 Perustelut:**` reasoning callout at the top of every LEAD
  synthesis — meta-level commentary on how the subagents' outputs were
  combined. Amber-bordered styling in `.ia-lead-answer`, distinct from the
  subagents' violet so visual hierarchy is preserved.

### Added — date awareness in prompts

- `load_prompt()` now prepends a `# CURRENT DATE` header (ISO + Finnish
  weekday) to every loaded subagent prompt. Without this, Gemini was
  answering "tänään 14.5.2025" when the system date was 2026-05-03.
- `today_prompt_prefix()` also prefixes every per-query user prompt with
  the same date stamp (belt-and-suspenders against system-instruction
  attention loss in long contexts).

### Added — durable OAuth token persistence

- New optional GitHub Gist mirror for `tokens.json`. Configure
  `INDERES_TOKENS_GIST_ID` and `INDERES_TOKENS_GH_TOKEN` and the agent
  pushes refreshed tokens to a private gist on every refresh, pulls from
  the gist on cold start. Solves the Streamlit Cloud problem where
  refresh-token rotation eats itself across container restarts.
- See `ui/DEPLOY.md §6.5` for setup.

### Fixed

- Material Symbols icon font no longer overridden by the global mono font
  rule (fixed `keyboard_double_arrow_right` ligature text in sidebar
  collapse arrow + `check_circle` overlap on status widget).
- Markdown tables in subagent output now render correctly (was missing
  `table` extension on `MarkdownIt("commonmark")`).
- Raw Python source from QUANT (no fences) auto-wraps in ```python``` so
  it renders as code instead of as headers/paragraphs.
- Trace-expander toggling no longer auto-scrolls Chrome to the bottom of
  the page (`overflow-anchor: none` + JS scrollY restore on summary
  click).

### Removed

- "📜 Täydellinen ajoloki" expander — was rendering the full narrative.md
  inline for every old assistant message on every Streamlit rerun, the
  dominant slowdown as chat history grew. The narrative.md file is still
  written to disk by the pipeline.
- Daily-quota progress bar from the sidebar — cap mechanism still works
  server-side; just don't surface the count.

### Reverted

- Tightened thought-trace format experiment (PR #24, reverted in the same
  series): forcing a one-line `**Ajatus:**` produced more model refusals
  than it solved rendering quirks. Original looser rubric restored.

### Parked

- **LEAD on Pro-tier model toggle** (`feat/lead-pro-toggle` branch, not
  merged). Goal: let the user opt-in to `gemini-2.5-pro` for the synthesis
  step only — bigger reasoning, better synthesis, only one extra LLM call
  per query so cost impact is small. Blocked on a MAF / Gemini compatibility
  issue: Pro rejects requests with `Function calling config is set without
  function_declarations` even though LEAD has `tools=None`. Three attempts
  in `_prepare_config()` to clear `tool_config` / `tools` when no function
  declarations are present did not unblock it. The branch keeps the WIP and
  a debug-logging hook (`INDERES_DEBUG_GEMINI_CONFIG=1`) for whoever picks
  it up next; root cause is in MAF's internal config building.

---

## [0.1.0] — 2026-05-01

Initial release. The system is functionally complete: it ingests natural-language
stock-research questions, routes them across four specialized subagents, and
synthesizes a final answer with sources. Tested end-to-end against real Inderes
MCP and paid Gemini.

### Added — core architecture

- Five-agent system on Microsoft Agent Framework 1.0+: `aino-lead` orchestrator
  plus four specialized subagents (`aino-quant`, `aino-research`,
  `aino-sentiment`, `aino-portfolio`).
- Each subagent gets a focused subset of Inderes MCP tools (3–8 tools each, not
  all 16) — improves tool-call accuracy materially over a monolithic agent.
- Lead has no tools; synthesizes subagent outputs from a structured prompt.
- Router uses structured-output Gemini call (JSON) with few-shot examples.
- Workflow uses `asyncio.gather` + `Semaphore(MAX_CONCURRENT_AGENTS)` instead of
  MAF's `ConcurrentBuilder` — runtime-decided fan-out for comparison queries
  and a hard quota cap.

### Added — Gemini fallback

- `FallbackGeminiChatClient` subclass with primary→retry→fallback chain.
- Default models: primary `gemini-3.1-flash-lite-preview`, fallback
  `gemini-2.5-flash`. Both are free-tier-eligible.
- Fallback policy: 1 retry on primary with `RETRY_DELAY_MS`; switch to fallback
  on persistent 503 or any 429; fallback gets 2 attempts with 2 s/4 s backoff.
- `last_used_model` recorded per chat client so the trace and `narrative.md`
  show which model handled each request.
- `QuotaExhaustedError` raised when both primary and fallback exhaust quota.
- No reference to `gemini-2.5-pro` anywhere — quota is zero on free tier.

### Added — Inderes MCP integration

- OAuth 2.0 Authorization Code + PKCE flow against Inderes' Keycloak SSO
  (`src/inderes_agent/mcp/oauth.py`):
  - Discovery from `/.well-known/oauth-protected-resource` (RFC 9728), then
    `/.well-known/openid-configuration`.
  - Localhost callback server handles the redirect.
  - Tokens cached at `~/.inderes_agent/tokens.json` with `0600` permissions.
  - Refresh-token reuse on subsequent runs.
- `_InderesBearerAuth(httpx.Auth)` injects the latest cached token per request,
  handling refresh-on-expiry transparently.
- `prefetch_token()` called eagerly in `__main__.py` so concurrent agent builds
  share the cached token instead of racing four OAuth flows.
- `_SanitizingMCPTool` subclass strips `$schema`, `$id`, `$ref`, `$defs`,
  `$comment` from tool input schemas after `connect()`. Inderes' MCP schemas
  include these JSON-Schema metadata fields; Gemini's `FunctionDeclaration`
  Pydantic validator rejects them.
- `load_prompts=False` on every MCP tool: Inderes MCP doesn't implement
  `prompts/list`. Default `load_prompts=True` would crash with `Method not found`.

### Added — observability

- Per-run directory at `~/.inderes_agent/runs/<timestamp>/` containing:
  `query.txt`, `routing.json`, `subagent-NN-<domain>.json`, `synthesis.txt`,
  `meta.json`, `console.log`, `narrative.md`.
- `narrate.py` parses `console.log` (extracts function-call timings) and JSON
  files into a human-readable markdown narrative with routing decision,
  per-tool-call timeline, per-subagent outputs, synthesis, and statistics.
- REPL slash commands: `/explain`, `/trace`, `/last`, `/runs`, `/agents`,
  `/clear`, `/help`, `/exit`.
- One-shot mode auto-prints a compact subagent trace plus paths to the run log
  and `narrative.md`.
- OpenTelemetry tracer with `ConsoleSpanExporter` configured (MAF emits spans
  natively).

### Added — CLI

- `rich` for terminal output: markdown answers, tables, error panels.
- `prompt_toolkit` for REPL input with history.
- Inline progress lines per phase (router → subagents → synthesis) so users
  don't think the system is hung during multi-second waits.
- Standalone `scripts/diag.py` that probes Gemini and MCP connectivity
  independently with per-step timing.
- `scripts/explain.py` regenerates `narrative.md` for any past run.

### Added — tests

- 13 unit tests covering:
  - Router JSON parsing (with code fences, prose leaks, plain JSON)
  - `QueryClassification` Pydantic validation
  - `FallbackGeminiChatClient`: 503 retry, 429 quota exhaustion,
    success-without-fallback paths
  - Workflow: per-company fan-out for comparisons, no fan-out for
    single-domain queries, concurrency cap enforcement
- End-to-end tests against real services not in CI (require credentials and
  consume Gemini quota).

### Build environment

- Python 3.11+ required; 3.13 in development via `uv`-managed CPython.
- `uv` recommended over plain pip for install speed and ARM-native Python
  management.
- `agent-framework-gemini` requires `--pre` flag (currently alpha-versioned on
  PyPI as `1.0.0aN`).
- ARM-native Python required on Apple Silicon: Intel Python via Rosetta 2 is
  ~10× slower for cold imports.
- 20+ GB free disk space recommended: APFS becomes unstable above ~90 % capacity
  (manifests as `mmap` failures, `bus error`, truncated reads — affecting both
  the application and git).

### Known limitations

- Synthesis quality is bounded by the lite-tier model on free Gemini. Paid tier
  enables upgrading the lead to `gemini-2.5-pro` (~few €/month additional)
  without changing the rest of the stack.
- During Gemini-side capacity spikes, both primary and fallback can return 503
  simultaneously. The system gracefully degrades (lead synthesizes from
  whichever subagents succeeded) but the failed subagents return empty data
  that the lead has to acknowledge.
- Tool-call attribution in `narrative.md` is heuristic. Tools unique to one
  agent (e.g. `get-fundamentals`) attribute correctly; tools shared across
  agents (e.g. `search-companies`) are marked `[shared]`.
- The system doesn't implement Magentic-One-style dynamic re-planning. If a
  subagent fails, the lead does its best with the remaining outputs but can't
  replan the workflow to compensate.

---

## Roadmap (not yet implemented)

Ideas worth exploring; none are committed.

- Upgrade only the lead to a stronger model (e.g. `gemini-2.5-pro`) for better
  synthesis quality without 4× cost on subagents.
- ~~Web UI via Streamlit hosted on Streamlit Community Cloud with a single
  pre-cached OAuth token (personal-use deployment).~~ Implemented in
  [unreleased]; tokens persist via optional GitHub Gist mirror. See
  `BACKLOG.md` for further agentic-improvement ideas.
- Streaming synthesis output in the REPL (the streaming path in
  `FallbackGeminiChatClient` is wired but not used by the current REPL flow).
- Automatic retry-the-whole-query if too many subagents fail simultaneously
  (rather than letting the lead degrade).
- Per-day quota usage display in `/trace` (currently you have to consult the
  Google AI Studio dashboard).
- Time-window filtering for `aino-research` to avoid pulling stale reports
  when the user explicitly wants only recent material.
