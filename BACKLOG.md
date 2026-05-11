# Backlog

A single-file overview of what's done, in flight, paused, and worth thinking
about. Last updated 2026-05-10 (evening — Wk 2 foundation + quick wins
shipped; eval baseline status audit + branch cleanup; see CHANGELOG and
`docs/agentic_dev_session_2026-05-10.md` for the full session arc).

## Status markers

- ✅ **shipped** — code is meaningfully in use
- 🚧 **in flight** — on a branch but not yet on main / not yet tested
- ⏸ **paused** — started but blocked (reason given)
- 💭 **idea** — under consideration, not yet committed

## Map

- [§0 Agreed roadmap (May–June 2026)](#0-agreed-roadmap-mayjune-2026)
- [§1 AI / agent capabilities](#1-ai--agent-capabilities)
- [§2 Valuation feature (own model)](#2-valuation-feature-own-model)
- [§3 UI / UX](#3-ui--ux)
- [§4 Tech debt + observability](#4-tech-debt--observability)
- [§5 Product / strategy](#5-product--strategy)
- [§6 Evals — gateway for AI features](#6-evals--gateway-for-ai-features)
- [§7 Recently shipped](#7-recently-shipped)
- [§8 Frontend rewrite — Vercel / Next.js + hybrid backend](#8-frontend-rewrite--vercel--nextjs--hybrid-backend)
- [§9 Agentic patterns from *State of the possible*](#9-agentic-patterns-from-state-of-the-possible)
- [§10 Autonomous nightly eval + self-repair loop](#10-autonomous-nightly-eval--self-repair-loop)
- [§11 AI Lab — public lab-notebook page](#11-ai-lab--public-lab-notebook-page)
- [§12 Analyst Walkthrough — in-depth analysis & scoring](#12-analyst-walkthrough--in-depth-analysis--scoring)

---

## 0. Agreed roadmap (May–June 2026)

The committed sequencing — what we actually ship and in what order. Each
phase lives elsewhere in the backlog as its own item; this section is the
**execution plan**, not the spec.

### Why this order

- **Visible features first, infra in parallel** — Devil's advocate +
  Reflexion + Footnotes are demoable to a non-technical user. Each adds
  a clear capability that "shows" the agent reasoning more visibly. This
  carries momentum.
- **Hard limits ride along, not block** — OWASP Agentic Top 10 #T1
  (excessive agency) is real, but it's a 0.5-day patch, not a 2-day
  blocker. We bake it in alongside Devil's advocate so multi-agent
  expansion is safe by the time we get there.
- **Eval foundation builds in parallel with features**, not before
  them. The autonomous nightly eval (§10) is the long-term goal; the
  manual `evals/golden.yaml` (§6) is the bridge.
- **Frontend rewrite is the inflection point** — once we have 3–4
  visible features in Streamlit, the spec for what the Next.js frontend
  needs to render is concrete. Doing the rewrite earlier means coding
  features twice; doing it later means accepting Streamlit's UX ceiling.

### Timeline (2026-05-10 re-prioritisation — see `docs/sprint_lessons_2026-05-09.md`)

| Wk | Phase | Items | Status |
|---|---|---|---|
| 1 | **Plotly charts for QUANT** *(1 d)* | §3 → ROE/P/E timeline + peer comparison | ✅ shipped |
| 1 | **Hard limits at orchestration boundary** *(0.5 d)* | §4 → max_iter / max_tool_calls / max_cost / max_duration / kill switch (OWASP T1) | ✅ shipped |
| 1 | **👍 / 👎 feedback in UI** *(0.5 d)* | §6 step 1 — `feedback.json` per run | ✅ shipped |
| **2a** | **CI gate (pytest + ruff)** *(0.5 d)* | §6 step 2 — was Wk 3, pulled in after morning's deploy incident | ✅ shipped (`0a16299`) |
| **2a** | **Multi-company valuation parser fix** *(0.5 d)* | §2 — production bug; agent emits JSON array in fan-out, parser rejected; now accepts arrays + disambiguates by company | ✅ shipped (`5f581c5`) |
| **2a** | **OAuth runtime tests** *(0.5 d)* | §4 — 16 tests covering refresh, gist sync, _load_tokens priorities; was zero coverage on 573 LOC | ✅ shipped (`c78607e`) |
| **2a** | **case_008 + eval status audit** *(2 h)* | §6 — multi-company regression case + status doc that 4 fail-cases from 2026-05-09 baseline are already fixed | ✅ shipped (`7a07d06`) |
| **2a** | **Eval golden.yaml structural CI** *(2 h)* | §6 — yaml validation on every push (no live LLM run, but catches typos/dead names) | ✅ shipped (`89e8d78`) |
| **2b** | **Smart insider taxonomy in SENTIMENT** *(1 h)* | §1 — 19 transactionType values bucketed (voluntary/compensation/risk); fixes share-premium drowning out signal | ✅ shipped (`64c8309`) |
| **2b** | **Transcript-default for thesis queries** *(0.5 h)* | §1 — RESEARCH pulls `list-transcripts` + `get-transcript` on outlook/strategy/risk queries | ✅ shipped (`64c8309` + tightened in same window) |
| 3 | **Reflexion / retry on weird output** *(1 d)* | §1 → "#2 Reflection + retry" — per-subagent + pipeline-level; cost tracking from HITL Step 1 makes retries visible | 🟡 next (depends on cost tracking) |
| 3 | **Footnote markers + sources panel** *(1 d)* | §1 → activates dead `.ia-fn` CSS. Per-claim `[¹]` → tool call provenance | 🟡 next |
| 3 | **HITL Step 1 — cost tracking + pre-flight gate** *(1 d)* | new §7 — see `docs/hitl_proposal.md`. Cost tracker + estimator + accept/cancel gate + accuracy log | 💭 spec ready |
| 3 | **Per-claim confidence scoring** *(0.5 d)* | §1 → 🟢🟡🔴 markers. Subagents report 1–5/claim, LEAD propagates | 💭 |
| 3 | **Tier 2 Supabase migration** *(1–2 h)* | §8 — runs + judgments queryable cross-device | 💭 |
| 4+ | **Devil's advocate** *(2 h)* | §1 — was Wk 1, demoted | 💭 |
| 4+ | **Frontend rewrite (Polku B / hybrid)** *(1.5–2 wk)* | §8 → FastAPI + Next.js + Vercel AI SDK | 💭 |
| 5+ | **Bull/Bear debate** | §1 → "#8 Bull/Bear" + judge | 💭 |
| 5–6 | **Analyst Walkthrough — in-depth scoring** *(2–3 d)* | §12 → 6-dimension qualitative+quantitative report. User-proposed flagship feature. | 💭 spec in §12 |
| 5+ | **Auto-orchestrator (Magentic ledger)** | §1 + §9 — meta-router decides tier + features | 💭 |
| 6+ | **Autonomous nightly eval + self-repair** | §10 — cron, prompts-only auto-fixes | 💭 |

### Decision log

- **2026-05-10 (evening — Wk 2 retrospective)**: Senior-PM-style
  user push-back caught two spec errors before they ate engineering
  hours: (a) the BUY-only insider filter would have hidden real
  signal (cherry-pick), replaced by smart-taxonomy prompt change;
  (b) the stock-split adjustment "bug" doesn't exist — MCP returns
  split-adjusted data server-side, verified live. **0.5–1 d of
  unnecessary work avoided per error.** New rule of thumb: verify
  any "found a bug" claim in docs against the actual data source
  before spec'ing a fix. See `LESSONS.md` "Verify before specifying".
  Also today: discovery that the four 2026-05-09 eval fail-cases
  were already fixed in `5e5dea7`/`80c6fd0`/`2039967`/`870749a` —
  baseline was 5 days stale. Re-baseline cadence added as an
  outstanding action.
- **2026-05-10 (afternoon — Wk 2a/2b execution)**: Two parallel
  tracks chosen over the original "Reflexion + Footnotes" Wk 2 plan.
  Foundation track (CI + valuation parser fix + OAuth tests + eval
  structural CI) shipped first to unblock all Wk 3+ work. Quick-wins
  track (smart insider, transcript-default) shipped second. Reflexion
  + Footnotes pushed to Wk 3, partially because HITL Step 1's cost
  tracking is a useful prerequisite for "retries don't silently
  double the bill".
- **2026-05-10 (morning — re-prioritisation)**: After 14 commits in
  one sprint, user explicitly stated priorities: *charts > retry >
  sources/footnotes > evals*. Re-ordered Wk 1–3 to match. Devil's
  advocate demoted from Wk 1 to Wk 4+ because Reflexion is the more
  pressing trust-amplifier. Tier 2 Supabase promoted into Wk 3
  because pushing-from-phone friction was a real blocker.
- **2026-05-09 (initial roadmap)**: User chose the *visible-feature-first*
  sequencing over the eval-first ordering. Counter-balanced by
  parallel manual eval scaffold + autonomous nightly system as the
  long-term destination.
- **Earlier**: Plan-then-execute shipped as a toggle, not default.
  LEAD Pro tier toggle shipped (Pro tool_config bug fixed in
  `gemini_client.py`).

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

- ✅ **Plan-then-execute toggle** (was BACKLOG #1 large-architectural) —
  LEAD-planner subagent emits structured JSON (per-subagent guidance,
  comparison axis, watch-outs) BEFORE fan-out. Subagents see this in
  their prompt. Toggle-based, default off. Sparring memo's mitigations
  honored: opt-in not default, LEAD's manager-bias risk capped by short
  plan (max 4 fields per subagent), opportunistic discovery preserved
  because subagents still see their full tool surface. Magentic Task
  Ledger primitive — outer-loop planning is now live, inner Progress
  Ledger is the next layer (§9).

- ✅ **LEAD Pro tier toggle + "Tarkka kaikki"** (was paused on
  `feat/lead-pro-toggle`) — fixed by stripping `tool_config` when
  `function_declarations` is empty (Pro rejects the combo, Flash Lite
  silently accepts). Three tiers: Vakio (Flash Lite throughout) /
  Tarkka LEAD (Pro synthesis only) / Tarkka kaikki (Pro everywhere
  including subagents, conflict-detector, planner). Code interpreter
  silently disabled on Pro because Pro rejects "tool call context
  circulation".

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

- *(none — the previously paused LEAD Pro toggle shipped on 2026-05-08
  after the `tool_config` bug was diagnosed; see Shipped above)*

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

- 💭 **Yahoo Finance integration as fresh-data side-channel** — Inderes
  MCP exposes neither real-time per-stock prices nor quarterly book
  values (verified by exhaustive probe of all 16 tools, 2026-05-09).
  Best Inderes can do: `get-inderes-estimates.sharePrice` is 1–3 weeks
  old (analyst snapshot), and BVPS is locked to LFY year-end (130+ days
  stale by mid-year). The current implementation always-on disclaimers
  this honestly, but doesn't fix the underlying staleness.

  Yahoo Finance via the `yfinance` Python library would provide:
    - `info["currentPrice"]` — 15-min-delayed live quote (free tier)
    - `info["bookValue"]` — per-share book value updated after each
      Q-report (e.g., Nordea Q1 2026 book value available ~22.4.2026,
      ~3 weeks fresher than LFY 2025 year-end)
    - Helsinki tickers all work (`.HE` suffix: `NDA-FI.HE`, `SAMPO.HE`,
      `KNEBV.HE`, etc.)

  **Architecture**: Yahoo as a *side-channel*, not a replacement.
  Inderes still owns ROE history, analyst sentiment, Nordic context.
  Yahoo provides only `(price, bookValue, lastQuarterEnd)` for the
  valuation snapshot. New `src/inderes_agent/market_data/yahoo_client.py`
  + new `get-yahoo-snapshot(ticker)` tool exposed to the valuation
  agent's tool-set. Falls back to Inderes MCP if Yahoo doesn't recognise
  the ticker.

  **When to do this**: not now — current disclaimers are honest enough
  for a single-user research tool where the user always opens a broker
  app to see live prices. Activate this when:
    - Watchlist + daily briefing feature ships (BACKLOG §1, #4) — fresh
      morning data becomes load-bearing
    - User feedback indicates 17-day price lag is misleading on actual
      decisions
    - We move to multi-user / public deployment where staleness is
      legally riskier
  **~1 day total** (50 lines client + 5 tool integration + ticker
  mapping for OMXH companies + 10 tests + docs).

  *Risks*: yfinance is unofficial (Yahoo could change API any day),
  occasional rate limits, ticker mismatches for some Nordic small-caps,
  TOS for free-tier personal research is permissive but not guaranteed.

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
- ✅ **Idle hero — minimalist settings expander** (2026-05-09) — feature
  toggles (valuation / plan-then-execute / model tier) collapsed into a
  themed `<details>` matching the results-section "AVAA PÄÄTTELY ›"
  look. Summary text in `--p-lead` amber so the affordance reads as
  primary on an otherwise quiet hero. CSS scoped via
  `.ia-hero-toggles-anchor` + `:has()` so other Streamlit expanders
  (activity log) stay visually separate
- ✅ **Idle vs active dual-render of feature toggles** (2026-05-09) —
  toggles live on the hero before the first query and migrate to the
  sidebar after, gated by `st.session_state.get("history")`. Same
  session_state keys so values persist across the transition;
  Streamlit duplicate-key error avoided
- ✅ **VALUATION removed from default agent roster** (2026-05-09) — opt-in
  feature, no longer mis-listed as "always-on" in the hero
- ✅ **Narration consistency pass** (2026-05-09) — third-person sportscaster
  voice across all live-status lines (router → planner → fan-out →
  synthesis), bilingual

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
- ✅ **Auto-relogin (Playwright headless)** *(2026-05-11)* — separate
  private repo
  [`inderes-mcp-auto-relogin`](https://github.com/5qtb5t9v5k-rgb/inderes-mcp-auto-relogin).
  GitHub Actions cron runs Playwright + Chromium twice per day (02:00 +
  17:00 UTC, deliberately outside Helsinki 08-16 working window),
  performs full Keycloak OAuth re-auth, pushes fresh tokens to the
  shared gist. Removes the previously-required daily manual
  `bash scripts/relogin.sh` step before each work morning. 7-iteration
  debug arc to get past CI-Chromium quirks (custom Keycloak theme,
  JS-driven submit button, chrome-error:// URL masking the real
  callback) — kept private because the workflow file contains
  `INDERES_USERNAME` + `INDERES_PASSWORD` as repo secrets.

### Open — small (next session pickups)

- 💭 **Cron health-check** — the pre-existing
  `refresh-inderes-tokens.yml` cron returns "success" exit status even
  when its refresh-token POST gets 400 invalid_grant (SSO Session Max
  iski). Discovered 2026-05-11 morning. Should fail-red so the
  email-on-failure alert fires; right now we only notice when the
  Streamlit app starts returning empty results.
- 💭 **Auto-relogin smart-timing** — currently re-logs in unconditionally
  twice per day. Could decode the JWT in the gist tokens, read
  `auth_time`, and skip when SSO Session Max is still >2 h away.
  Useful when the user does a manual relogin during the day. Spec
  + skip-logic outline in `inderes-mcp-auto-relogin/README.md`.
- 💭 **sentiment.md prompt length** — same issue as research.md two
  sessions ago. The smart-insider-taxonomy block expanded the prompt
  significantly; Flash-Lite started occasionally skipping MCP calls
  (fabrication-guard catches them but the UX is "agent errored").
  Tighten in the same style as research.md (Wk 2 commit `5efb5f1`).

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

### ✅ Tier 0 + Tier 1 shipped (2026-05-09)

- ✅ **`scripts/build_runs_index.py`** — SQLite index over
  `~/.inderes_agent/runs/`. 183 runs, 457 tool calls, idempotent rebuild.
- ✅ **`evals/sample_queries.sql`** — 10 diagnostic SQL queries
  surfacing real weaknesses (comparison routing too thin, päättely
  structured form dead, conflict-detector under-firing, etc.).
- ✅ **`evals/findings_2026-05-09.md`** — first systematic analysis
  against the indexed run data. Seven concrete weaknesses ranked
  by severity.
- ✅ **`evals/judge_selection.md`** — benchmark-backed model choice.
  Gemini 2.5 Pro picked over Sonnet 4.5 / GPT-5 because the Vectara
  HHEM v2 leaderboard shows reasoning models hallucinate >10 % on
  grounded summarisation — exactly the failure mode we cannot import
  into the judge for a finance-research pipeline.
- ✅ **`evals/golden.yaml`** — 6 starter cases, each one mapping to a
  finding from the diagnostic pass. Hard + soft assertions per case.
- ✅ **`evals/judge.py`** — `JudgeBackend` Protocol + `GeminiJudge`
  impl using the new `google-genai` SDK. Same API key as the
  pipeline. Output via `response_mime_type=application/json`.
- ✅ **`evals/runner.py`** — orchestrator. Picks most-recent matching
  run from the index, runs hard expressions in a sandboxed `eval()`
  scope, calls the judge for soft criteria, writes a timestamped
  report.md + results.json. `--hard-only`, `--case`, `--backend`
  flags supported.
- ✅ **`evals/rubric.md`** — judge prompt with explicit JSON-output
  contract.
- ✅ **`evals/README.md`** + **`evals/results/baseline_tier1/`** as
  the committed reference report.

**Tier 1 baseline result (12 pass / 4 fail across 6 cases, 16 hard
assertions total):**
- case_001 comparison routing: hard fails confirm router under-routes
  (only `quant`); judge soft 2/5 — *"hallucinated business model
  reasoning because no research agent ran"*
- case_002 päättely schema: 0/1 — structured form is dead, prose
  fallback only. Judge confirms LEAD ignored conflict-detector finding
- case_003 conflict coverage: 2/2 — Bittium ROE 5% case fires
  conflict + warning correctly, but judge flags LEAD's päättely as
  generic
- case_004 search robustness: 1/2 — Vincit fabricated data with empty
  tool_calls. Judge soft 1/5 — *"complete failure, hallucinated entire
  analysis"*. Highest-priority fix.
- case_005 reproducibility: 3/3 — three Nordea-arvonmääritys runs are
  structurally consistent. ✓
- case_006 latency cap: 2/2 — Nordea kannattavuus deep-dive stayed
  under 120 s, ≤12 tool calls per agent. ✓

These results ARE the new regression baseline. Any prompt change that
moves a passing case to fail will be caught on the next run.

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

## 8. Frontend rewrite — Vercel / Next.js + hybrid backend

**Status:** 💭 idea, scheduled for Wk 3–4 of the agreed roadmap (§0).

### Why

The Streamlit ceiling. The repo is getting big, and the visual delta
between Streamlit and a real Next.js app (shadcn/ui, Vercel AI SDK,
streaming token-by-token, generative artifact panels, mobile UX) is
significant. The right time to do the rewrite is *after* we know what
the AI features need to render — meaning after Devil's advocate,
Reflexion, and Footnotes are concrete in Streamlit and we can copy
their requirements into the Next.js spec.

### Three paths considered

| Path | Effort | Risk | Reward |
|---|---|---|---|
| **A — Full rewrite Python → TypeScript** | 3–5 wk | high (MAF TS port less mature, Excel-parity needs revalidation, MCP client repo) | top-tier UX |
| **B — Hybrid: Python backend + Next.js frontend** ⭐ | 1.5–2 wk | low (backend stable, controlled rewrite) | ~90% of A's UX gain, ~30% of the risk |
| **C — Stay on Streamlit, polish further** | 0 | none | ceiling on UX |

### Polku B — implementation sketch

**Backend (mostly unchanged):**
- Wrap the existing orchestration in a thin FastAPI service. Single
  endpoint `/api/run` that accepts `{query, options}` and returns an
  SSE stream of typed events:
  - `routing` (router decision)
  - `plan` (when plan-then-execute is on)
  - `subagent.start` / `subagent.tool_call` / `subagent.delta` /
    `subagent.complete`
  - `conflict` (from conflict detector)
  - `synthesis.delta` / `synthesis.complete`
  - `error` / `done`
- Auth: Bearer token shared with frontend via env. Inderes MCP OAuth
  unchanged.
- Deploy: Fly.io (probably) or Render — needs persistent disk for
  `~/.inderes_agent/runs/` forensic logging unless we move that to S3.

**Frontend (full rewrite):**
- Next.js 15 App Router on Vercel Edge.
- Vercel AI SDK 5 for stream parsing + UI hooks.
- shadcn/ui + Tailwind for the design system.
- `useEventSource` hook subscribed to `/api/run` SSE.
- Components mirroring current Streamlit cards: `<RouterCard>`,
  `<AgentCard variant="quant|research|...">`, `<PaattelyExpander>`,
  `<PlanExpander>`, `<MetricsRow>`, `<ConflictCallout>`,
  `<ValuationPanel>`. Each accepts a typed event stream and updates
  in place.
- Generative-UI: agent cards animate in as `subagent.start` arrives,
  status flips on `subagent.complete`, tool-call chips appear inline.
  No reruns / flicker.
- Artifacts panel (ChatGPT/Claude.ai style): valuation table, big
  metrics, source documents open in a side panel rather than inline.
- Theme parity: same colors / token system, ported to Tailwind CSS
  variables. Mono font for code/numbers, sans for prose.
- AG-UI protocol fit: this stream IS an AG-UI implementation — open
  the door for other agents to render into our shell later.

### What ports cleanly, what doesn't

| Asset | Action |
|---|---|
| Prompt files (`*.md`) | Reused as-is |
| Greenwald-Gordon engine | Stays in Python backend |
| Excel-parity tests | Stay in Python |
| Telemetry / forensic logs | Stay in Python; frontend reads via `/api/runs/<id>` |
| MCP OAuth + Gist-mirror cron | Stays in Python |
| Tool-call guard | Stays in Python |
| Streamlit `components.py` (~2000 lines) | Rewritten as React components |
| Streamlit `theme.css` (~1500 lines) | Ported to Tailwind config + minimal CSS modules |
| Streamlit narration | Re-expressed as event-stream consumer |

### Open questions before kicking off

- **Auth on the /api/run endpoint** — how do we keep Inderes data
  behind a non-public gate? Per-user JWT? Single shared token (still
  not great)? Vercel Edge middleware for IP allowlist for now?
- **Forensic logging** — does it stay on the backend filesystem, or
  do we move to S3-compatible storage (R2, Backblaze B2)?
- **Streamlit retirement plan** — keep `ui/` working in parallel for
  N weeks, or hard-cut at the rewrite? Probably parallel for 2 weeks,
  then deprecate.
- **Vercel cost** — Edge runtime is generous on free tier, but if we
  do server-side rendering with long SSE streams we may hit limits.
  Test before committing.

---

## 9. Agentic patterns from *State of the possible*

Long-term research-backed extensions, sequenced after the §0 roadmap.
Each is a known pattern with peer-reviewed or industry-validated
performance claims. Don't ship without an eval to prove the lift on our
own data — see §10.

### Reasoning patterns

- 💭 **ReAct (Reason + Act, Yao et al. 2022)** — already implicit in
  every subagent (Ajatus → tool call → response). Make it explicit by
  surfacing the loop step count + reasoning trace per subagent. Useful
  for debugging tool-call cascades.
- 💭 **ReWOO (Reason WithOut Observation, Xu et al. 2023)** — separate
  the *plan* from the *execute*: planner emits the full tool-call DAG
  upfront, executor runs it, solver synthesizes. Plan-then-execute (§1
  shipped) is the primitive; ReWOO is the next step where plan output
  IS the dispatch DAG, not just guidance text.
- 💭 **Reflexion (Shinn et al. 2023)** — already in the roadmap (Wk 1).
  Verbal self-reinforcement after each run, stored in episodic memory
  for the next run.
- 💭 **Tree of Thoughts (Yao et al. 2023)** — branch on uncertainty:
  when LEAD is "unsure" between 2–3 framings, fan out N synthesis
  attempts, score, pick best. Heavy — only for `Tarkka kaikki` tier.
- 💭 **Graph of Thoughts (Besta et al. 2024)** — generalisation of ToT;
  arbitrary DAG of intermediate thoughts. Probably overkill for our
  domain unless we go to multi-step research questions.

### Memory patterns (CoALA taxonomy, Sumers et al. 2024)

We have **working memory** only (the per-run context). Add the rest:

- 💭 **Procedural memory** — versioned prompt store with auto-rollback
  on regression. Today prompts are git-tracked, no auto-rollback. The
  autonomous nightly eval (§10) is the natural integration point.
- 💭 **Episodic memory** — per-company "what happened last time we
  asked about X" log. `~/.inderes_agent/episodes/<company>.jsonl`.
  LEAD can reference: *"in your previous Sampo analysis (4 weeks ago)
  you flagged the dividend cut; that flag has since resolved"*.
- 💭 **Semantic memory** — distilled facts ("Sampo is a Finnish P&C
  insurer with strong Nordic exposure"). Separate from episodic in
  that it's de-duplicated and used as background, not narrative.
- 💭 **Long-term insight ledger** (already in §1 as #5) — overlaps
  with episodic + semantic; the §1 entry should be split into the
  three CoALA tiers.

### Orchestration patterns

- 💭 **Magentic Task Ledger + Progress Ledger** (Microsoft Research
  2024, Fourney et al.) — outer ledger tracks "what we're solving",
  inner ledger tracks "what's been done so far". Plan-then-execute
  (§1 shipped) is the outer; the inner Progress Ledger is the missing
  layer. With it, mid-run replan becomes possible (current setup is
  fan-out-then-synthesize, no mid-flight correction).
- 💭 **Manager + workers pattern (Anthropic Cookbook, OpenAI
  agents-as-a-tool)** — closest to what we already do. Make it
  explicit: LEAD becomes a "manager" that can call subagents iteratively
  rather than once. Adds latency; adds correctness on multi-step
  questions. Hard limit: max N iterations per run (OWASP T1).
- 💭 **Auto-orchestrator (meta-router)** — already in §0 roadmap as
  Wk 5+. The LLM decides: which agents, which tier, which features,
  iteratively. Risk: blows latency + cost budgets if unconstrained.
  Hard limits + observability before this ships.

### Protocol patterns

- 💭 **MCP (already on)** — Inderes MCP, Yahoo MCP (when §2 lands),
  health/finance/Todoist MCPs available locally. Possibly expose our
  OWN MCP: *"Inderes-Agent" as an MCP server* so other agents can call
  it as a tool.
- 💭 **A2A (Agent-to-Agent, draft 2025)** — over-engineered for our
  in-process subagents. Would matter only if we expose subagents as
  separate services (microservice split — not on the roadmap).
- 💭 **AG-UI (Agent-to-User UI, draft 2025)** — natural fit once §8
  Next.js frontend ships. The SSE event stream we design for §8 IS
  effectively an AG-UI implementation; aligning vocabulary lets us
  swap in someone else's frontend or run our backend behind someone
  else's shell.

### Safety / governance patterns

- 💭 **OWASP Agentic Top 10 (Dec 2025) tier-1 priorities**:
  - **T1: Excessive Agency** → hard limits (Wk 1 of §0)
  - **T2: Memory Poisoning** → episodic memory needs sanitization
    (relevant before §9 episodic-memory item ships)
  - **T3: Tool Misuse** → tool-call guard already in (§4 shipped);
    extend to all subagents, not just valuation
  - **T4: Identity Spoofing** → not a current vector (single-user app),
    but matters before public deployment
- 💭 **MiFID II Test 4 alignment** — strict avoidance of personal
  recommendations. Add a "personalisation lint" step in synthesis: if
  the answer addresses the user as "you" + names a single product
  recommendation → flag → soften.
- 💭 **BCBS 239 lineage** — every claim in synthesis must trace to a
  tool call. Footnote markers (§0 Wk 2) are the visible side; the
  invisible side is a lineage graph stored alongside the run.
- 💭 **EU AI Act risk classification** — single-user research tool is
  currently unlisted. Public deployment would need classification
  review. Document this in `docs/regulatory.md` before any public-beta.

---

## 10. Autonomous nightly eval + self-repair loop

> **The big idea.** A cron-driven nightly system that runs 20–30 cases,
> grades them with an LLM-judge, and produces concrete fix proposals —
> or commits prompt-only auto-fixes directly — with **no human
> approval in the loop**. Morning review = read the diff report, accept
> or revert.

**Status:** 💭 idea, scheduled for Wk 6+ of the agreed roadmap (§0).
Depends on §6 manual eval scaffold being live first.

### Why this matters

- The slowest part of agent development is the *"is this prompt change
  better?"* question. Today: manual, takes hours, gets skipped.
- LLM-judge over a stable golden set is cheap (~$1–2 per nightly run
  at our scale) and runs while the user sleeps.
- Without approval gates, the system can iterate 5–10× in a week
  instead of 1× — *if* the guardrails hold.
- This is also the only path to **catching regressions from external
  changes** (Inderes MCP schema drifts, Gemini model swaps, OAuth
  token-rotation edge cases).

### Architecture

```
              ┌─────────────────────────────────────┐
              │  cron (02:00 UTC, GitHub Actions)   │
              └─────────────────┬───────────────────┘
                                │
                                ▼
        ┌─────────────────────────────────────────────┐
        │  evals/runner.py                            │
        │  - load evals/golden.yaml                   │
        │  - run each case through real pipeline      │
        │  - capture: routing, tool calls, synthesis  │
        └─────────────────┬───────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────────┐
        │  evals/judge.py (LLM-as-judge — Sonnet)     │
        │  rubric: factual accuracy, tool coverage,   │
        │  structure compliance, citation, entity-    │
        │  presence, hallucination flags              │
        │  → score 1–5 per case + rationale           │
        └─────────────────┬───────────────────────────┘
                          │
                          ▼
                  any case below 3/5 ?
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     no failures                  failures
              │                       │
              │                       ▼
              │      ┌────────────────────────────────┐
              │      │  evals/repair_agent.py         │
              │      │  - read judge rationale        │
              │      │  - localise: which prompt?     │
              │      │  - propose patch (text-only)   │
              │      │  - re-run all 30 cases with    │
              │      │    proposed patch              │
              │      │  - delta check: helps without  │
              │      │    breaking others?            │
              │      └────────────┬───────────────────┘
              │                   │
              │      ┌────────────┴───────────┐
              │      ▼                        ▼
              │   green (helps,           amber (mixed)
              │   breaks nothing)            │
              │      │                        ▼
              │      ▼              evals/proposals/<date>/
              │  auto-commit to     <case_id>.patch
              │  branch             + rationale.md
              │  `auto-fixes/yyyy-       │
              │  mm-dd` with full        │
              │  audit trail             │
              ▼      ▼                    ▼
        ┌─────────────────────────────────────────────┐
        │  evals/runs/<date>/report.md                │
        │  - case-by-case scores                      │
        │  - which auto-fixes applied                 │
        │  - which proposals need human eyes          │
        │  - which cases regressed (if any)           │
        │  → Slack/Telegram notify                    │
        └─────────────────────────────────────────────┘
```

### Hard guardrails (non-negotiable)

- **Auto-fixes touch ONLY prompt files** (`agents/prompts/*.md`).
  Python code is never modified by the auto-fixer.
- **Auto-fixes go to `auto-fixes/yyyy-mm-dd` branch**, never to `main`.
  Merging is a manual decision.
- **Hard cap**: max 3 auto-commits per night. If >3 cases fail and
  the repair agent thinks ≥4 fixes are needed, downgrade ALL of them
  to `proposals/` for human review.
- **Regression check**: every proposed patch must re-run the FULL
  case set. Net score must improve. One regression in another case
  → downgrade to proposal.
- **Cost cap**: max $5 per nightly run. Hit the cap → abort, write
  partial report, notify.
- **Time cap**: max 90 min wall-clock per nightly run.
- **Rollback button**: a single command (`git revert auto-fixes/...`)
  restores any night's changes.
- **Observability**: every prompt change logged with the LLM-judge
  rationale that motivated it. BCBS 239 lineage friendly.

### Phasing

| Phase | What | Effort |
|---|---|---|
| 10.1 | Cron + runner + LLM-judge (no auto-repair) — *just* nightly grading + Slack notify | 1 d |
| 10.2 | Repair-agent v1: proposes patches, writes to `proposals/` only — no commits | 1.5 d |
| 10.3 | Auto-commit on green-only patches with all guardrails | 1 d |
| 10.4 | Multi-night memory: agent reads last 7 nights' reports to spot patterns | 1.5 d |

### Open questions

- **Judge model choice** — Sonnet is the obvious pick (good at
  rubric-style grading), but ~$0.05/case adds up. Test with Haiku
  first; upgrade if calibration is off.
- **Regression definition** — should "case regressed but new failure
  is less severe" still count as regression? Probably yes, to be
  conservative.
- **Golden set evolution** — when do we ADD to the golden set? After
  every user 👍? Or weekly batch? Need a curation process so the set
  stays representative, not just easy.
- **External-shift detection** — if all 30 cases regress overnight
  with the same root cause (e.g. Inderes MCP schema change), the
  repair agent should NOT propose 30 prompt fixes. Need a
  "stop-the-world" detector that flags systemic shifts and pages a
  human.
- **Could the user be the judge once a week?** — sample 3 cases,
  show side-by-side, ask 👍/👎. Trains LLM-judge calibration over
  time.

### Why "no approval gate" is the right call

- The user explicitly chose this — speed over caution.
- Guardrails above keep the blast radius small (prompts only, branch
  only, regression-checked, capped).
- The cost of a wrong auto-fix is "morning review reverts it" —
  cheap and reversible.
- The cost of an approval gate is "1 day of decisions sit in a queue"
  — and we've seen this kill momentum on every prior eval attempt.
- This *is* the AI-research-grade workflow that the rest of the
  field is converging on.

---

## 11. AI Lab — public lab-notebook page

**Status:** 💭 idea, parked. To be revisited after §0 Wk 2 (footnotes
ship). Senior-PM sparring captured here so we don't lose the framing.

### Product vision (one sentence)

> **AI Lab is the Inderes-Agent's living public lab-notebook —
> shipped features, current experiments, design decisions, and metrics —
> so a reader can see where we're going and why.**

### What it is NOT

- Not a dry changelog (only "shipped" entries)
- Not a marketing landing page (sales tone)
- Not a heavy technical blog (pulls momentum away from the app itself)

### What it IS

- "Lab notebook" voice — *what we're trying now, what worked, what
  didn't*
- Per-feature lifecycle stamps: `[KOKEILEMME]` → `[BETA]` → `[VAKIO]`
- "Try it" link from every feature back into the live app
- Brand-loyal — same mono font, same colors, same tokens as the main UI

### Audience hypotheses (3 personas)

1. **Curious peer-investor** (~30 s scan) — *"is this worth a query?"*
2. **Fintech-Twitter / informed amateur** — *"how is this built?"* —
   wants architecture, agent patterns, motivation
3. **Self / future demo audiences** — see momentum: living lab, not
   frozen project

### Differentiators vs other investing tools

1. **Open development process** — most AI products hide their
   internals; this shows agents, prompts, experiments, conflicts,
   fixes
2. **Anchored in Inderes quality** — not "another LLM predicting
   prices" but "Inderes research data + agent fabric that makes it
   queryable"
3. **Research-grounded** — every feature traces to a paper or
   pattern (Magentic, ReWOO, Reflexion, BCBS 239); the Lab tells
   *why this*, not just *what*
4. **Nordic perspective** — distinct in a market dominated by
   US-centric OpenAI/Anthropic/Perplexity tooling

### Page sections (sketch)

```
HERO          — AI Lab — kehitysmuistio. One-line: where, where to
NYT KOKEILEMME — 3 in-flight items + "Kokeile" button into app
VAKIINTUNEET   — sliding timeline of shipped features
AGENTIT        — 5 + 1 cards (glyph, role, tools, sample query)
TULOSSA        — §0 roadmap distilled
TUTKIMUSTAUSTA — links: Magentic, ReWOO, MCP, OWASP, BCBS 239
PALAUTE        — GitHub, email
```

### Open PM decisions (resolve before kicking off)

1. **Hosting:** Streamlit-multipage (`pages/2_AI_Lab.py`) now → Next.js
   static port when §8 lands? Or build static directly?
   - *Recommendation:* Streamlit-multipage v0 (~3 h), port to Next.js
     in §8
2. **Languages:** FI + EN toggle (same as main app)? *Recommendation:* yes
3. **Lifecycle taxonomy:** `[KOKEILEMME]` / `[BETA]` / `[VAKIO]`?
   *Recommendation:* yes — three states is enough; don't over-engineer
4. **Update cadence:** manual per-ship, or auto-generate from
   BACKLOG.md "✅ shipped" entries?
   *Recommendation:* manual at v0; auto-generation when §10 ships
5. **v0 scope:** 3 sections (NYT KOKEILEMME / VAKIINTUNEET / TULOSSA),
   manual markdown cards, ~3 h work

### Implementation note when we resume

- `pages/2_AI_Lab.py` Streamlit multi-page entry
- Reuse the existing theme via `inject_theme()` at the top
- New CSS classes namespaced `.ia-lab-*` for cards / lifecycle stamps
- No new dependencies
- Port to Next.js becomes part of §8 (it's just another route in
  the new frontend)

---

## 12. Analyst Walkthrough — in-depth analysis & scoring

**Status:** 💭 idea, captured 2026-05-10. Provisional Wk 5–6 slot.
User-proposed flagship feature. PM-level analysis below; not yet
committed to roadmap because it depends on three Wk 2–3 prerequisites
shipping first (Reflexion, per-claim confidence, Tier 2 Supabase).

### Product vision (one sentence)

> **The agent reads several recent Inderes analyst reports on a single
> company and synthesises a structured, multi-dimensional analyst-style
> walkthrough — not just a Q&A answer, but an opinionated investment
> thesis with a transparent score and the data trail to back it.**

### Why this, why now

The current LEAD synthesis answers a question. The Analyst Walkthrough
**produces a thesis** — closer to what an Inderes analyst delivers
internally before publishing a recommendation. It's the natural
endgame of every trust-building feature we've shipped:

- **Footnotes** (Wk 2) say *"this number came from this tool call"*
- **Confidence** (Wk 3) says *"how much should you trust this number"*
- **Walkthrough** (Wk 5–6) says *"here's the whole picture, scored,
  with the lineage to verify every dimension"*

It also positions the product clearly: not a chat-with-a-stock app, but
**"Inderes-grade analyst output, on demand, for any of the 200+
covered companies."**

### What it is (output shape)

A long-form report with **6 dimensions**, each scored 1–5 and backed
by a 2–4 sentence rationale + footnoted data points:

```
1. LAATU (Quality)        — ROE, margins, capital efficiency,
                            management track record
2. KASVU (Growth)          — revenue trajectory, organic vs M&A,
                            forward estimates, TAM trends
3. ARVOSTUS (Valuation)    — fv (Gordon, multiples), peer multiples,
                            DCF if available, vs historical band
4. STRATEGIA (Strategy)    — moat, segment mix, ESG, capital allocation,
                            recent strategic moves
5. RISKI (Risk)            — cyclicality, leverage, regulatory,
                            geographic, single-customer
6. SENTIMENTTI (Sentiment) — analyst recos, insider flow, forum tone,
                            short interest where available
```

Plus a **composite score** (weighted average) and a one-paragraph
"BOTTOM LINE" — the agent's synthesis of *what would an analyst say
about this company today*.

### What makes it different from today's LEAD synthesis

| Today's LEAD synthesis | Analyst Walkthrough |
|---|---|
| Answers one question | Produces a structured report |
| Single-dimension (whatever was asked) | Always 6 dimensions |
| Reads tool data | Reads tool data **+ recent analyst reports as documents** |
| ~400 token answer | ~2,000–3,000 token report |
| Free-form prose | Fixed structure, rendered as cards |
| Triggered by question | Triggered by toggle / button on company page |

### Architecture paths (3 candidates)

**Path A: New "ANALYST" subagent**
- Adds a 6th persona to the current 5
- Owns the report structure, called only when the toggle fires
- Pros: clean separation, can be evolved independently
- Cons: requires new prompt + persona; another model call layer

**Path B: Deep mode of existing LEAD**
- Same 5 subagents fan out, but LEAD's prompt switches to
  "produce a 6-dimension report" instead of "answer the question"
- Pros: reuses entire infrastructure; no new persona
- Cons: prompt becomes a megaswitch; harder to eval cleanly

**Path C: Sequential refinement (recommended)**
- Phase 1: existing 5 subagents fan out as today
- Phase 2: a new **REPORT** synthesiser (separate from LEAD) reads
  all 5 outputs + pulls 2–3 most recent Inderes reports via
  `read-document-sections` and produces the structured 6-dimension
  output
- Pros: each phase is independently eval-able; document-reading
  isolated to Phase 2 (today's subagents already have that tool but
  rarely use it well); can ship Path C incrementally — even just the
  document-reader without scoring is useful on day 1
- Cons: slower (extra LLM round), more cost per query

**Recommendation:** Path C. The sequential separation matches how a
human analyst actually works: gather data first, structure the
opinion second.

### Prerequisites (must be shipped before this lands)

| Prereq | Status | Why |
|---|---|---|
| ✅ Hard limits + cancel token (Wk 1 #3) | shipped | A 3,000-token report could runaway-loop without budgets |
| ✅ Persona-prefixed footnotes (Wk 2 → done in Wk 1) | shipped | Each scored dimension needs `[X<n>]` provenance |
| 🟡 Reflexion / retry on weird output (Wk 2) | pending | Self-correction matters more for a long-form report than for a Q&A — one bad dimension poisons the whole score |
| 🟡 Per-claim confidence scoring (Wk 3) | pending | The composite score needs per-dimension confidence to weight; otherwise "5/5" on a thinly-sourced dimension drags the average |
| 🟡 Tier 2 Supabase migration (Wk 3) | pending | Reports are heavy artifacts — running them on phone but reading them on laptop is the obvious workflow |
| 🟡 Smoke test in CI (Wk 3) | pending | Walkthrough is the highest-stakes output; needs golden examples gated by CI before it goes near users |

### Open PM decisions (resolve before kicking off)

1. **Trigger:** dedicated toggle (*"📊 Analyytikon syväanalyysi"*) or
   inferred from query intent (*"give me a full picture of Sampo"*)?
   - *Lean:* explicit toggle at v0 — costs 5–10× a normal query, must
     be opt-in. Add intent inference later if usage validates.
2. **Scope:** single company only, or also peer-comparison walkthroughs?
   - *Lean:* single company at v0. Peer comparison is its own beast
     (axis × dimension matrix) — separate v2.
3. **Document corpus:** all available Inderes reports for the company,
   or last N (3? 5?) by date?
   - *Lean:* last 3 by date + the most recent quarterly. Caps token
     usage; freshness wins over depth at this stage.
4. **Score weighting:** equal across dimensions, or domain-specific
   (banks weight risk more, growth co's weight growth more)?
   - *Lean:* equal at v0, log the weighted score for offline analysis.
   Domain-specific weighting once we have data on what correlates
   with Inderes' published recommendation.
5. **Output format:** rendered cards in app, or exportable PDF/markdown?
   - *Lean:* cards in app at v0; export comes after Tier 2 lands and
     reports are first-class persisted artifacts.
6. **Evals:** golden walkthroughs for 3–5 well-known companies
   (Sampo, Nordea, Kone, UPM, Nokia)? Judge prompt that scores
   "would a real analyst sign this"?
   - *Lean:* yes — this is exactly why the smoke-test infra needs to
     ship first.

### Why this could be the killer feature

Every other Inderes-data product (the website, the iPad app) lets a
user *read* analyst output. None lets a user *ask for a synthesis on
demand*. If Walkthrough produces output an Inderes analyst would
recognise as "yes, that's how I'd structure it", it's a category-
defining feature — not a faster Bloomberg, but an *agentic analyst
desk*.

The risk is the inverse: produce output that's plausibly-wrong, and
the trust deficit poisons the rest of the product. That's why the
prereq stack matters — Reflexion + confidence + smoke tests are not
nice-to-haves before shipping this; they're the gate.

### Implementation note when we resume

- New module `src/inderes_agent/orchestration/walkthrough.py` —
  Phase 2 synthesiser. Phase 1 reuses existing `run_workflow()`.
- New prompt `src/inderes_agent/agents/prompts/walkthrough.md`
- Output schema as a Pydantic model (`WalkthroughReport`) with the
  6 dimensions + scores + bottom line + footnote refs
- New UI render `render_walkthrough_report(report)` in components.py
  — card-per-dimension with score chip, rationale, footnote markers
- CSS namespace `.ia-walk-*`
- Toggle in the existing `render_feature_toggles()` panel
- Eval set in `evals/walkthrough_golden.yaml` — 3–5 companies, judge
  prompt that scores structural completeness + factual grounding

---

## Reading guide

- **Before adding to §1** — verify §6 (evals) is up to date. Without a
  yardstick we can't tell whether feature changes are improving things.
- **The structure stays:** every section has a "Shipped / Open /
  Paused" split. If a status changes, update its marker.
- **When considering "do we do this?"** — check whether §6 lists it as
  a gateway-needing item. If yes, build the evals foundation first.
