# Backlog

A single-file overview of what's done, in flight, paused, and worth thinking
about. Last updated 2026-05-09.

## Status markers

- ✅ **shipped** — code is meaningfully in use
- 🚧 **in flight** — on a branch but not yet on main / not yet tested
- ⏸ **paused** — started but blocked (reason given)
- 💭 **idea** — under consideration, not yet committed

## Map

- [§1 AI / agent capabilities](#1-ai--agent-capabilities)
- [§2 Valuation feature (own model)](#2-valuation-feature-own-model)
- [§3 UI / UX](#3-ui--ux)
- [§4 Tech debt + observability](#4-tech-debt--observability)
- [§5 Product / strategy](#5-product--strategy)
- [§6 Evals — gateway for AI features](#6-evals--gateway-for-ai-features)
- [§7 Recently shipped](#7-recently-shipped)

---

## 1. AI / agent capabilities

The most interesting angle: *"why move from reactive to proactive"*.
The biggest learning value: *"how agents actually collaborate"*.

### Shipped

- ✅ **Subagent thought traces** — mandatory `**Ajatus:**` opener at the start
  of every subagent's response. PR #18, #20, #21
- ✅ **LEAD's Päättely (reasoning) block** (BACKLOG #9, prompt-only version) —
  4-paragraph prose: disagreement / resolution / uncertainty / what was left
  undone. Rendered in the UI as its own `<details>` expander
- ✅ **Conflict detector** (BACKLOG #1 post-execute side, commit `842fd92`) —
  separate LLM call between subagent execution and LEAD synthesis. Emits
  `conflicts.json` (agreements / conflicts / isolated_claims). LEAD sees
  the structural disagreement map and resolves conflicts explicitly.
  Also covers BACKLOG #6 disagreement-surfacing
- ✅ **Provenance threading** (BACKLOG #10) — tool-call trace fed into LEAD
  as a *"TOOL CALL TRACE (ground truth)"* block. LEAD can diff subagent
  claims against the raw data (`synthesis.py:80–106`)
- ✅ **Valuation toggle intent gate** (commit `46f9be9`) — heuristic
  `query_has_valuation_intent()` prevents toggle leakage on qualitative
  queries; conservatively biased (false negatives preferred over false
  positives). 33 parametrized tests
- ✅ **Tool-call guard at orchestration boundary** (commit `045872e`) —
  rejects valuation outputs with zero MCP calls as hallucinations. Closes
  the trust-killer path observed in run `20260508-205057-769` where Flash
  Lite invented company_id, price, and ROE history from conversation context

### Open — small and standalone

- 💭 **Devil's advocate toggle** — checkbox next to the chat input,
  *"🎭 Devil's advocate"*. One extra LLM call that critiques LEAD's
  own answer: *"what did you miss? what would the bear case say?"*.
  Maximum 4 sentences. UI: a new **🎭 Counter-argument** box below
  the summary. **~2 h.** High ROI for surfacing blind spots.

- 💭 **Footnote markers `[1]`, `[2]`** — quantitative claims in LEAD's
  answer get numbered; hover/click reveals subagent, tool call, and
  confidence level. CSS already in place (`.ia-fn`, `.ia-fn-q/r/s/p`);
  needs prompt update + parser. **~5 h.** Activates dead CSS.

- 💭 **Confidence scoring** — each subagent reports 1–5 confidence per
  claim. Could be combined with footnote markers.

- 💭 **Tool-result entity-validation post-processor** *(code-level)* —
  extract company names from tool result + names mentioned in the answer,
  diff them: if a name appears in answer but not in tool result → flag
  → retry. Would have caught the Case 001 hallucination. See
  `evals/known-cases.md`

- 💭 **Result-completeness check** — if a tool returns N items and the
  agent lists M < N, force an explanation. Would have resolved Case 002.

- 💭 **Default-region inference** — Finnish-language query → default
  `regions=[FINLAND]` unless said otherwise

### Open — medium

- 💭 **#2 Reflection + retry on weird output** — detect anomalous outputs
  (CAGR > 100%, empty, "no data") → retry the same agent with added
  context *"your previous answer contained: [output]. Sanity check it."*
  Cap retries at 1 per agent.
  *Risk:* retry can mask genuinely missing data with assumptions —
  must distinguish "no data" vs "weird data".

- 💭 **#5 Insight ledger — long-term memory** — each query, LEAD distills
  1–3 memorable observations and saves them to
  `~/.inderes_agent/insights.jsonl`. On subsequent queries, relevant
  insights are loaded into context → growing company knowledge across
  sessions.
  *Open questions:* insight expiry logic, how many to load (token
  budget), user-facing management UI.

- 💭 **#9 Better LEAD model — Sonnet/Opus for synthesis** — replace
  Flash Lite. Requires the parked Pro-toggle branch to be unblocked
  first. Most useful **once #10 (provenance) is in place** — without
  raw data, Sonnet can't diff claims any better. Cost ~40–200× per
  query.

### Open — large architectural

- 💭 **#1 Pre-execute plan + "Use stronger planning" toggle** — LEAD
  writes a structured **🧠 Plan** block before dispatching subagents.
  Toggle-based like valuation, *not default*. Sparring memo from
  2026-05-08:
  - **Manager bias** (Cognition 22.4.2026): *"managers default to overly
    prescriptive, which backfires when manager lacks deep context"* —
    LEAD has no tool surface, so over-direction is a real risk
  - **Opportunistic discovery is lost** — in static fan-out a subagent
    might stumble across a surprising detail; if forced into a plan, it
    can't "rightfully" stray sideways
  - **Latency + token cost** — one extra LLM call plus longer prompts.
    On simple queries, pure waste
  - **Plan ↔ result mismatch** — if the plan says "fetch X" but MCP
    returns nothing, who decides on rewriting?
  - **Right use case**: multi-step dependencies, comparisons where the
    axis isn't obvious, exploratory queries
  - **Default off, opt-in** by user

- 💭 **#7 Subagent-to-subagent calls** — QUANT can directly call
  SENTIMENT. Classic multi-agent challenge.
  *Open questions:* infinite-loop prevention, per-call cost cap,
  privacy/context isolation, tracing. May require a "team lead" agent
  as coordinator.

- 💭 **#8 Bull/Bear debate architecture** — for investment-decision-style
  queries, spawn two opposing LEADs (bull + bear) + judge. New prompts
  `bull.md`, `bear.md` (same tool set as RESEARCH).
  *Risk:* Wynn et al. (arXiv 2509.05396) showed debate can *hurt*
  accuracy when a weaker model "convinces" a stronger one
  (CommonSenseQA: 53.4% → 46.8% post-debate). Mitigation: judge always
  sees both answers *and* the original tool trace.

- 💭 **#4 Watchlist + daily briefing** — user marks *"watch Sampo"*; a
  GitHub Action runs every morning, generates a *"what's new?"*
  markdown. Sidebar **📅 Morning briefing** section. **Major shift
  from reactive to proactive.** Requires: scheduled job, watchlist
  store, brief generator, UI section.

### Paused

- ⏸ **LEAD Pro model with toggle** (`feat/lead-pro-toggle` branch) —
  blocked on a MAF/Gemini compatibility issue: Pro rejects with
  *"Function calling config is set without function_declarations"*
  even though LEAD has no tools. Needs investigation of MAF's internal
  config building. Also blocks #9.

---

## 2. Valuation feature (own model)

**Status (2026-05-09):** ✅ **Shipped to production.** PR #30 merged to
main; cloud deployment live. 146 tests green.

### Shipped (PR #30)

- ✅ **`valuation/engine.py`** — deterministic Greenwald-Gordon hybrid.
  The 8-step methodology as code:
  FV_Gordon = ((ROE−g)/(k−g)) × BVPS, EPV = (ROE/k) × BVPS, GM, Rock
  Bottom, laatu/keskinkertainen/tuhoutuva classification with ±2 %
  buffer, dual implied values (`implied_g` + `implied_roe`), entry
  levels (90/80/75 % of FV), safety margin
- ✅ **Excel parity** — 10 hand-picked Finnish companies regression-tested
  against `Arvonmääritys2023.xlsx`. All numbers within ±0.02 €
- ✅ **`aino-valuation` agent + parser** (commit `78cd1a6`) — strict JSON
  output, parser validates before engine consumes
- ✅ **Pipeline integration + sidebar toggle** (commit `79cccdc`) — the
  *"Käytä vaihtoehtoista arvonmääritystä"* checkbox
- ✅ **Sustainable-ROE rule + parser validation** (commit `4437b0f`) —
  median dominates the mean, deterministically validated in Python.
  Rising → 5y_median, falling → min(3y_median, trend_weighted), stable
  → 5y_median
- ✅ **EPV / growth-pricing decomposition** (commit `4375797`) —
  market_premium_to_epv_pct, growth_priced_in_share, implied_g,
  safety_margin_to_fv_pct
- ✅ **Richer rationale + LEAD narrative** (commit `899f828`) — agent
  prompt now requires roe_rationale + 2–4 sentences per parameter.
  LEAD prompt has the 4-section "Own model vs Inderes" structure.
  BVPS derivation switched to marketCap/sharesTotal/pb
- ✅ **Tool-call guard** (commit `045872e`) — closes the Q2 hallucination
  path
- ✅ **Edge-case warnings** (commit `045872e`) — `|safety_margin| > 100%`
  and tuhoutuva-with-manual-override get explicit ⚠️ flags so LEAD
  softens the verdict
- ✅ **Toggle intent gate** (commit `46f9be9`) — qualitative queries
  no longer trigger an unwanted Greenwald-Gordon table
- ✅ **Typo-tolerant parser** (commit `769394f`) — Levenshtein-≤2 fuzzy
  match on `*_rationale` keys with sibling protection

### Known issues — deferred to follow-up

- 🔴 **Multi-company fan-out broken** (surfaced in production run
  `20260508-221007-094` — Sampo + Nordea + Aktia comparison). Each
  fanned-out valuation subagent emits a JSON **array** containing all
  three companies' data, because each agent thinks the whole comparison
  is its scope. Parser expects single objects → "No json block found"
  for all three → all valuations fail → LEAD falls into Tila B for the
  whole query. **Single-company valuations work correctly.** Fix
  requires agent-prompt changes (scope = exactly one company) + parser
  changes (handle array case by picking own company). **~2–3 h.**

- 💭 **Conditional LEAD prompt for default flow** — current implementation
  loads the full lead.md with valuation guidance in every query. Tila A
  explicitly tells LEAD to ignore it, but ~3000 tokens per default-flow
  query are wasted. Could be made conditional via `<!-- BEGIN/END -->`
  delimiters + an `include_valuation` flag passed to `load_prompt()`.
  **~30 min.** Low priority — empirically Tila A works.

- 💭 **Regime-shift detection** for sustainable-ROE — Nordea has 2021–22
  ROE ~12 % vs 2023+ ROE ~16 % (rate environment shift). Median picks
  ~15 % which mixes two regimes. Flag when |LFY − LFY-3| > 30 % →
  suggest manual_override. **~1 h.**

### Open — readily usable extensions

- 💭 **Portfolio mode** — same valuation engine applied across the
  portfolio. Cron each morning, *"what changed in the last month"*.
  Requires: scheduled job, portfolio-level synthesis prompt, dedicated
  UI view (distinct from chat answer)

### Open — model-strengthening extensions

- 💭 **Scenario tables in UI** — Weak/Base/Strong (ROE × 0.9 / 1.0 / 1.1)
  per company, per the user's Excel "Yhtiökohtainen" sheet. Engine
  already computes; UI rendering missing
- 💭 **Sensitivity tables 6×6** — ROE × k and g × k, per the
  `methodology/sensitivity.md` style. Engine + UI
- 💭 **Visual valuation card** — spider chart or dial gauges instead of
  pure text. Especially the growth/EPV split deserves a visual
- 💭 **Composite "Rissanen Score"** — *under design, not committed*.
  Sparring notes 2026-05-08:
  - **Don't roll into one composite** — additive composition cancels
    signal (Q9+V3 and Q3+V9 yield the same score but are different
    decisions). Greenblatt's Magic Formula uses rank-cuts, not weighted
    sums
  - **Correlated dimensions double-count** — ROE/ROIC/FCF-conversion are
    80 %+ correlated, not three independent measures
  - **Inderes consensus 10 % is circular** — the architecture already
    relies on Inderes; weighting it again is double-dipping
  - **Suggested instead:** show 6 dimensions separately (spider chart),
    a "convergence flag" if they diverge, and sector-relative scoring
    rather than absolute values
  - **MCP gaps:** ROIC, WACC, FCF, earnings revisions, and short
    interest are not exposed. Which metrics are realistic on Inderes
    data?
  - **Validation**: backtest against the user's 74-company Excel
    dataset before implementing. Predictive vs descriptive purpose?

### Underlying issue

- 💭 **MCP doesn't expose `bvps` directly** — derived from
  `marketCap / sharesTotal / pb`. Documented. Longer-term improvement:
  request that Inderes add `bookValuePerShare` to the `fields` enum.

---

## 3. UI / UX

### Shipped

- ✅ **Token-system unification** (commit `30174e5`) — --t-* / --ls-* /
  --r* / --s-* tokens. Legacy --ia-* aliases removed
- ✅ **Aikajana strip + Open log + Open päättely** (commit `070e512`) —
  unified rhythm in terminal-DNA style
- ✅ **Right activity panel + close button** (commit `6acb316`)
- ✅ **Conflict box embedded in Päättely** — "Subagentit erimieltä"
  inside the Päättely expander
- ✅ **Followup chips** — yellow, larger, no text overflow
- ✅ **Inderes recommendation badge** — INCREASE/REDUCE/HOLD color-coded
- ✅ **Sources as clickable links** — Inderes.fi URLs in LEAD's answer
- ✅ **Persona-colored live status box** — agents shown in real time
- ✅ **Live narration fine-tuning** — *"Tunnistan, mitkä agentit tähän
  tarvitaan…"* style lines (commit `58bd36f`)
- ✅ **Valuation feature UI** — sidebar toggle + chip in agent row + Tila C
  4-section synthesis layout

### Open — small polish

- 💭 **Tier 6: Responsive** — right-panel breakpoints for narrow
  screens. `(max-width: 1280px)` → overlay form, `(max-width: 720px)`
  → full-screen modal. Mobile fallback (1024px) exists but isn't
  thoroughly tested. **~20 min**
- 💭 **`.streamlit/config.toml` `primaryColor` override** — could drop
  many `!important` overrides. *Risk:* every Streamlit button gets the
  color → secondary buttons may break. **~30 min testing**
- 💭 **Animation polish** — 150 ms hover transitions on all chrome
  elements (button, päättely, timeline, chat-message). Softens the
  feel. **~15 min**
- 💭 **CustomStatus token pass** — `.ia-cs` rules still use raw values
  (`padding: 8px 12px`). Snap to --s-* / --t-*. **~10 min**
- 💭 **Statusbar (`.ia-statusbar`)** — still useful now that the
  Aikajana strip shows the same? Slim, remove, or keep?

### Open — medium

- 💭 **Bottom 🔍 Agenttien toimintaloki expander** — duplicates the
  right panel's content. User decided *"can stay for now"*, but if
  behaviorally redundant, removing it would shed ~80 lines of code
- 💭 **Custom chat-message rendering** — stop using `st.chat_message`,
  render our own message bubbles. Requires a larger change but ends the
  fight against Streamlit's defaults
- 💭 **Plotly charts for QUANT** — interactive time-series, peer
  comparisons. `st.plotly_chart` natively. Recommended in priority
  comparison

### Open — broader

- 💭 **Streaming output** — token-by-token answer rendering in the
  chat bubble. Streamlit supports it, but moving MCP calls requires
  state-machine handling
- 💭 **PDF export** — *"Export this query as PDF"* → matplotlib charts
  + tables + analysis

---

## 4. Tech debt + observability

### Shipped

- ✅ **Forensic logging per run** — `~/.inderes_agent/runs/<ts>/`
  structure. Replay-friendly per BCBS 239 lineage requirements
- ✅ **HeadlessAuthError + `_auth_broken` latch** — clear error message
  when Inderes token has expired, no silent failure (commit `3f933f6`)
- ✅ **CancelledError fix** (commit `d5d9dfe`) — MCP connection drop no
  longer leaves the UI hung; shows the same "session expired" card
- ✅ **Token-rotation cron** — GitHub Actions every 5 min. PR #25
- ✅ **Gist mirror for OAuth tokens** — workaround for Streamlit Cloud's
  read-only filesystem
- ✅ **Tool-call guard for valuation** (commit `045872e`) — structural
  defense at orchestration boundary against zero-MCP-call hallucinations

### Open — high priority (gateway for AI features, see §6)

- 💭 **👍 / 👎 feedback in the UI** — `feedback.json` per run, no
  forced comment. One evening's work. *This is the gateway for
  everything else.*
- 💭 **Smoke test** — 5–10 known-good queries in pytest. Routing
  correct, at least one tool call, answer non-empty, key entities
  present. One evening's work.
- 💭 **`evals/golden.yaml` + `scripts/replay.py`** — curated run_ids
  as references, replay diffs the structure (router, tool calls, key
  entities) rather than raw text. `evals/known-cases.md` already
  exists — Case 001 + Case 002 are ready golden rows

### Open — middle

- 💭 **CircuitBreaker for `FallbackGeminiChatClient`** — handle 503/429.
  State machine (CLOSED/OPEN/HALF_OPEN), exponential backoff + jitter,
  separate cooldowns for 429 vs 5xx, per-model cooldown. ~50 extra
  lines, brings LiteLLM-grade resilience without the dependency.
  **~1–2 days**
- 💭 **OpenTelemetry GenAI Semantic Conventions v1.37** —
  `gen_ai.agent.name`, `gen_ai.operation.name`,
  `gen_ai.usage.*input_tokens` etc. for forensic logging. Enables
  later migration to OTel-compatible observability stacks (Langfuse
  self-host, Phoenix). **~4 h**
- 💭 **`.streamlit/config.toml` `primaryColor` override** — see §3,
  same item from a tech POV

### Open — longer term

- 💭 **MCP capability documentation auto-generated** — build-time
  script that reads tool schemas and distills `docs/mcp-capabilities.md`.
  LEAD prompt includes it → knows what MCP offers. Enables *"could have
  fetched X but didn't"* style reasoning. **~2 h.**
  *(Discussed in sparring 2026-05-08 — user wanted to wait)*
- 💭 **Issue register + stress-test scenarios** (BCBS 239 compliance)
  — extend `evals/known-cases.md` into a persistent register.
  **~2 days**
- 💭 **Web search for RESEARCH** — Reuters/Bloomberg headlines next to
  Inderes' own corpus. **~1 day.** *Risk:* source hygiene
- 💭 **Inline source citations per claim** — *(direct hit vs the
  observed hallucinations, see evals/known-cases.md Case 001)*.
  Footnote markers (§1) are the first step
- 💭 **Historical backtest** — *"What would you have recommended on
  Sampo 3 months ago?"* — agent restricts its context to that date and
  inspects how the prediction held up. Requires tool-side date
  filtering.

### Known issues — persistent

- ℹ️ **Inderes Keycloak 10h SSO Session Max** — refresh tokens
  invalidate after 10h regardless of refresh activity. Workaround:
  `bash scripts/relogin.sh` or cron when available. Empirically
  documented (cron-job.org tests: 120 successful rotations, the 121st
  failed at 601 min).
- ℹ️ **Streamlit Cloud deploy lag** — sometimes auto-deploy is slow;
  empty-commit force-redeploy is needed

---

## 5. Product / strategy

### Open questions

- 💭 **Audience** — only me, or a growing user base? For myself I can
  tolerate high complexity; for an audience the product needs a simpler
  story
- 💭 **Reactive vs proactive** — chat (now) vs watchlist + morning
  briefings. Mind shift; product identity changes
- 💭 **MiFID II — how close to the "personal recommendation" boundary
  do we want to go?** Stock research isn't inherently high-risk Annex
  III, but a single *"X is right for you"* triggers the whole
  investment-advice obligation pack (ESMA Test 4 — suitability)

### Possible publications

- 💭 **Blog post on architecture choices + the Keycloak 10h finding** —
  precise empirical measurement, replication instructions. Useful for
  the open-source community and Nordic banking-AI teams. Significant
  time savings for users. **~1 day**
- 💭 **PR to Keycloak documentation** about the SSO Session Max default
  and its operational impact on refresh tokens
- 💭 **MCP-Inderes integration README update** — warning about the
  10h behavior, workaround via `offline_access` scope if Inderes
  allows

### Documentation

- 💭 **DESIGN_BRIEF.md drift check** — older plan that may be out of
  date
- 💭 **`/methodology` directory sync with the engine** — code changes,
  methodology mds don't always
- 💭 **MULTI_AGENT_ARCHITECTURE.md fixes** based on sparring 2026-05-07:
  - CoALA reference for memory split (procedural tier missing from
    canonical)
  - Stronger phrasing of *"compatible with Cognition 22.4.2026, closest
    to OpenAI Cookbook agents-as-a-tool 28.5.2025 pattern"*
  - "anti-capabilities" → "least-agency rules" (OWASP Agentic Top 10)
  - MiFID II Test 4 link made explicit
  - Pitfall list extended with OWASP security perspective

### Strategic large

- 💭 **Plotly charts for QUANT** (UI feature, strategic impact) —
  visual differentiation, "Inderes Norasta" tier improvement
- 💭 **Portfolio mode as a step toward proactivity** — see §2

---

## 6. Evals — gateway for AI features

> **Until the evals foundation is built, AI capability features aren't
> worth investing in — we don't know whether the fixes work.**

### Four-step path

1. **👍 / 👎 feedback in the UI** *(one evening)* — `feedback.json` per
   run, no forced comment. Captures real-usage feedback.
2. **Smoke test** *(one evening)* — pytest fixture with 5–10 known-good
   queries. Routing correct, at least one correct tool call, answer
   non-empty, known keywords present.
3. **`evals/golden.yaml` + `scripts/replay.py`** *(one evening)* —
   curated run_ids as references; replay diffs structure (router, tool
   calls, key entities), ignoring raw text.
4. **Production monitoring** *(continuous)* — aggregation script that
   shows the week's thumbs-up/down ratio, categorizes error types.

`evals/known-cases.md` is already started — every case there is a
potential golden row. Case 001 + Case 002 are the obvious first ones.

### Strategic evaluations

- 💭 **Trajectory eval** — Phoenix or LangSmith. For step 4 progression
- 💭 **Calibration** — post-hoc calibration coefficients for output
  confidence
- 💭 **Red-teaming** — Microsoft AI Red Team taxonomy as a checklist
- 💭 **Drift detection** — Langfuse/Phoenix metrics weekly vs baseline.
  Useful only when production traffic > 100 queries/day

---

## 7. Recently shipped

(So you can see where we started → where we got)

### 2026-05-09
- ✅ **Valuation feature merged to main + deployed** (PR #30) — engine,
  agent, parser, sustainable-ROE rule, EPV decomposition, dual implied
  metrics, tool-call guard, edge-case warnings, intent gate. 13 commits,
  22 files, +3922 lines, 146 tests green. Cloud auto-rebuilt, default
  flow verified unchanged
- ✅ **README.md, ARCHITECTURE.md, CHANGELOG.md updated** to reflect
  5 specialists + valuation engine + tool-call guard
- ✅ **BACKLOG.md translated to English** for documentation consistency

### 2026-05-08
- ✅ Valuation feature on local branch (engine, agent, parser, UI,
  sustainable-ROE rule, EPV decomposition, richer rationale fields) —
  see §2

### 2026-05-07
- ✅ UI token-system unification + slim Päättely + amber chips
- ✅ Activity panel + close button + conflict embedded in Päättely
- ✅ CancelledError surfaced properly
- ✅ Live-narration polish

### Earlier
- ✅ #1 post-execute (conflict detector, `842fd92`)
- ✅ #3 thought traces (PR #18, #20, #21)
- ✅ #6 disagreement surfacing (part of #1)
- ✅ #9 prompt-only Päättely block
- ✅ #10 provenance threading (`synthesis.py:80–106`)
- ✅ Inderes recommendation badge (PR #28)
- ✅ Followup chips (PR #28)
- ✅ Clickable source links (PR #29)
- ✅ Persona-colored live status (PR #23)
- ✅ Token-rotation cron (PR #25)

---

## Reading guide

- **Before adding to §1** — verify §6 (evals) is up to date. Without a
  yardstick we can't tell whether feature changes are improving things.
- **The structure stays:** every section has a "Shipped / Open /
  Paused" split. If a status changes, update its marker.
- **When considering "do we do this?"** — check whether §6 lists it as
  a gateway-needing item. If yes, build the evals foundation first.
