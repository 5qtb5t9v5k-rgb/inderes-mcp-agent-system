# Strategy — themes, stories, and roadmap

**Date:** 2026-05-12
**Author:** the project owner, with engineer input
**Status:** Strategy document. Living. Update in place as decisions land.
**Audience:** the project owner (executive PM hat), anyone joining the
project who needs the *why-do-we-do-the-things-we-do* frame above the
1961-line `BACKLOG.md`.

---

## TL;DR — where we are, where we're going

Eight weeks of iterative building produced a working multi-agent chat
that answers Nordic-equity research questions. The shape of the product
is now clear, and so is the gap between what it does today (reactive
Q&A) and what the project owner actually wants from it (sustained
analyst workflow). This document distills 89 backlog items + a major
product pivot proposal into **five coherent themes**, each with a
defensible goal, a few sample user stories, sequencing, and risks.

**The five themes:**

1. **Operational reliability** — keep the lights on so anything else can ship
2. **Analyst depth** — make each single-company answer rival ChatGPT/Bloomberg-lite quality
3. **Sustained-monitoring product** — from reactive Q&A to morning-driver leaderboard
4. **Source coverage** — beyond Helsinki / Inderes-only
5. **Agent quality** — make the multi-agent reasoning measurably better

**This is not BACKLOG.md.** BACKLOG holds 71 ✅ shipped + 89 💭 ideas at
the work-item level. This doc sits one layer above and answers "which
themes do those items serve, in what order, with what trade-offs."

---

## Map

- [§1 State of the union](#1-state-of-the-union)
- [§2 The five themes](#2-the-five-themes)
- [§3 Sample user stories](#3-sample-user-stories)
- [§4 30 / 60 / 90 day roadmap](#4-30--60--90-day-roadmap)
- [§5 Anti-themes — what we deliberately won't do](#5-anti-themes--what-we-deliberately-wont-do)
- [§6 Decisions that need an explicit call now](#6-decisions-that-need-an-explicit-call-now)
- [§7 Personas + jobs-to-be-done](#7-personas--jobs-to-be-done)

---

## 1. State of the union

### What works today, shipping in production

- Multi-agent fan-out: LEAD + QUANT + RESEARCH + SENTIMENT + PORTFOLIO + (opt-in) VALUATION
- Microsoft Agent Framework on Google Gemini, with structured error
  classification + retry-with-backoff + diagnostic logging
  *(shipped 2026-05-12, `e44a053`)*
- Inderes MCP fully integrated, OAuth-PKCE with gist mirror, auto-relogin
  Playwright sidecar at 4×/day cron *(tightened today, `a3ef68a`)*
- Streamlit "Trading Desk" UI, FI/EN toggle *(fixed today, `9607953`)*,
  forensic per-run logs, footnote-source markers, conflict detector
- Deterministic Greenwald-Gordon valuation engine with **sensitivity grids
  shipped today** *(`809e11f`)* — 5×5 heatmaps for ROE×k and g×k, ChatGPT
  Qt-Group regression test green
- 392 tests across 25 suites, CI-gated on every push

### What's wired but not yet shipped to production

- **Yahoo Finance MCP integration** — code in main, 11 wiring tests
  green, locally verified end-to-end; sidecar runs locally only. Modal
  / Fly.io hosting is the next mile.

### Major product direction newly committed (this week)

- **Pivot from chat-only to chat + sustained-monitoring** — the design
  brief at `docs/design_briefs/company_leaderboard_2026-05-12.md` lays
  out a leaderboard + per-company drill-down view to sit alongside the
  current chat. Same repo, two complementary modes, one audience.

### Tech debt and operational debt

- Refresh-tokens cron silently exits 0 even when refresh fails with
  `invalid_grant` (BACKLOG §4) — false-positive success obscures real
  state. Self-healing chain trigger is BACKLOG-priority.
- App-level token failure currently requires Cloud reboot because of
  the `_GIST_PULLED_THIS_PROCESS` one-shot.
- Disk fills weekly without automation. Hygiene cron designed,
  not yet installed.
- Eval suite (`evals/golden.yaml`) runs manually only — autonomous
  nightly variant is §10 BACKLOG.

---

## 2. The five themes

### Theme 1 — Operational reliability

> **Goal:** the demo URL is reachable at any hour, the system recovers
> from auth + quota + disk failures without manual intervention, and
> known failure modes have automated alerts before they bite the user.

**Why this is a theme not an afterthought.** Every product direction
below assumes the system stays up. Today's pattern — demo prep gets
interrupted by token expiry, then by disk full, then by Cloud-cache-
staleness — burns hours that could have been feature work. Three to
five hours of operational hardening saves dozens of hours of incident
response over the next quarter.

**Work in this theme:**

- ✅ Auto-relogin cron 2× → 4× daily *(shipped today)*
- 🟡 Self-healing chain trigger: refresh-cron → auto-relogin via repository_dispatch
- 🟡 App-level gist re-pull on `invalid_grant`
- 🟡 Disk hygiene cron + 20 GB alert threshold
- 💭 Spend cap monitoring + UI banner when approaching 80% of monthly cap
- 💭 Cloud uptime monitor (a 1-line "is the URL alive" cron with notification)
- 💭 Test all three smart-adaptation layers end-to-end with a forced SSO expiry

**Sequencing:** finish self-heal + disk hygiene first (cumulative ~2 h).
Then monitor and observe — most of this theme is "build automation,
then stop touching it."

**Risk:** none of this is glamorous. Easy to defer. Don't. Every
"sorry, the demo is down" message to a stakeholder is a credibility cost
that compounds.

---

### Theme 2 — Analyst depth

> **Goal:** when a user asks a single-company valuation question, the
> answer rivals a ChatGPT-with-fresh-sources output in numerical depth
> AND beats it on traceability + determinism + Excel-parity rigor.

**Why this is a theme.** The fastest way for someone to dismiss the
agent is "it just summarized what I could have read." The fastest way
for them to bookmark it is "look, it produced a 5-year fundamental
table with sensitivity analysis and every number is sourced." The
ChatGPT Qt-Group example the project owner shared is the bar.

**Work in this theme:**

- ✅ Greenwald-Gordon engine + Excel parity tests *(already shipped)*
- ✅ Recommendation badge above LEAD answer *(already shipped)*
- ✅ Time-series Plotly charts for ROE / P/E / margins *(already shipped)*
- ✅ Sensitivity grids (ROE × k, g × k) as collapsible heatmap *(shipped today, `809e11f`)*
- 🟡 **5y historical metrics table** — Qt-style 15-row × 6-column expander
  with kurssi/mcap/EV/BVPS/EPS/ROE/PE/PB/PS/EV-EBITDA/EV-EBIT/omavaraisuus/nettovelka
- 🟡 Footnote markers `[1] [2]` per quantitative claim → tool-call provenance
  (BACKLOG §1 — activates dead `.ia-fn` CSS, 1 day)
- 💭 Per-claim confidence scoring 🟢🟡🔴 (BACKLOG §1)
- 💭 Bloomberg-style ANR-vs-target table (BACKLOG §3)
- 💭 News context block under per-company page (replaces ad-hoc "Mitä Inderes kirjoitti" prose)

**Sequencing:** sensitivity-tables → 5y historical → footnotes →
confidence markers. Each is ~3-5 h. Combined effect: every valuation
or fundamentals query gets multi-table output where today's gives only
prose.

**Risk:** scope creep. *"Add one more metric"* is infinite. Cap the
columns/rows up-front per feature and ship the v1 even if a critic
could argue for column #16.

---

### Theme 3 — Sustained-monitoring product

> **Goal:** the daily-driver workflow shifts from typing questions one
> at a time to opening a leaderboard, scanning, clicking into the
> interesting names, asking the agent for explanation, and capturing
> insight to a persistent per-ticker notebook.

**Why this is THE theme.** The product owner explicitly said *"80 % of
my analyst-workflow value is in sustained monitoring, not Q&A."* The
chat agent is the deep-dive tool; the leaderboard is the daily-driver
landing. Without this theme, the agent stays a curio — impressive once,
forgotten by week three. With it, the agent becomes a reason to open
the laptop in the morning.

**Reference docs:**
[`docs/design_briefs/company_leaderboard_2026-05-12.md`](../design_briefs/company_leaderboard_2026-05-12.md)
(Part 1 + Part 2)

**Work in this theme (phased):**

- 💭 **Phase 1** — per-ticker markdown notebook (BACKLOG Pull #4)
  - `notes/<TICKER>.md` accumulates content over sessions
  - Two new agent tools: `read_ticker_notebook` + `append_ticker_notebook`
  - LEAD + RESEARCH agents wired (read + write); others read-only
  - ~3-4 h
- 💭 **Phase 2** — SQLite state + nightly batch cron
  - Per-ticker row: price, fair value, recommendation, last update
  - GitHub Actions cron runs daily 07:30 EET
  - Calls MCP tools, runs valuation engine, writes SQLite
  - Zero LLM calls in the batch
  - ~3 h
- 💭 **Phase 3** — Leaderboard page (Streamlit pages/01_leaderboard.py)
  - Sortable table by safety margin / Δ price / Inderes-disagreement
  - Filters by sector, recommendation, ROE threshold
  - Click row → per-company page
  - ~3 h
- 💭 **Phase 4** — Per-company drill-down page
  - 5×3 buy-price grid (Tasearvo / EPV / EPV+25/50/75% × Heikko/Perus/Hyvä)
  - Inderes consensus block + recent news
  - **"Ask agent about this"** button → chat with ticker pre-filled
  - ~4 h
- 💭 **Phase 5** — Scenario sliders + market-pricing reverse-engineer
  - Interactive scenario inputs (ROE / k / g)
  - Live recomputation via valuation engine (no LLM call)
  - "At current price, market is paying for ROE = X%, g = Y%"
  - ~4 h
- 💭 **Phase 6** — Visual polish (Claude Design loop closure)

**Sequencing:** phases are strictly additive. After Phase 3 you have
a usable leaderboard with zero per-company depth. After Phase 4 the
killer cross-mode flow lands. Phases 5-6 are quality-of-experience
improvements on top.

**Why phased, not big-bang:** each phase is shippable. You can stop
after any and still have something useful. Total: ~17-20 hours
spreadable across 5-7 evenings.

**Risk:** this is where scope discipline matters most. Resist:
- adding portfolio weight management (out of scope — see §5)
- adding real-time intraday streaming
- adding multi-user accounts

---

### Theme 4 — Source coverage

> **Goal:** the agent answers questions about non-Helsinki names with
> the same depth as Helsinki names, and cross-source consensus (Yahoo
> agrees with Inderes, or doesn't) is surfaced explicitly when both
> sources are available.

**Why this is a theme.** The Inderes-only constraint is a real
limitation for the project owner's actual workflow — international
peer comparison, ASML / Apple / Allianz drift in and out of attention,
the agent currently cannot help. Yahoo MCP integration code is shipped;
only hosting remains.

**Work in this theme:**

- ✅ Yahoo MCP sidecar repo created (MIT-public)
- ✅ Yahoo client + per-agent partitions integrated in main repo
- 🟡 **Yahoo MCP Fly.io deployment** — Path A per BACKLOG §2
  - Auto-stop machines = $0 idle
  - Bearer auth via `MCP_API_KEY`
  - ~45 min first-time
- 🟡 **Yahoo settings toggle in UI** — sidebar checkbox
  - Default OFF (preserves Inderes-first identity)
  - When ON, agents pick up Yahoo tools alongside Inderes
  - ~1-2 h
- 💭 **Cross-source consensus retry** — when Inderes BVPS lags by >2Q
  and Yahoo has fresher data, prefer Yahoo
- 💭 **Future MCPs**: SEC EDGAR (10-K/Q/8-K + Form 4), FRED (US macro),
  ECB Statistical Data Warehouse (EU macro), Statistics Finland +
  ESEF iXBRL (Helsinki machine-readable filings)

**Sequencing:** ship Yahoo to production first (Fly + toggle).
Future-MCP additions become 1-day projects each once the pattern is
proven; defer until a specific user need surfaces.

**Risk:** dual-source data conflicts. Mitigated by partition design
(SENTIMENT gets `get_holders` from Yahoo, Inderes for forum sentiment —
no overlap) but worth watching when both sources cover the same metric.

---

### Theme 5 — Agent quality

> **Goal:** the multi-agent reasoning gets measurably better at the
> three things that matter: (a) catching its own mistakes before
> synthesis, (b) handling disagreement between subagents explicitly,
> (c) refusing to fabricate when grounded data is missing.

**Why this is a theme.** Today's agent works well most of the time
but the failure modes are still observable: occasional fabrication
(caught by structural guards, but the response becomes "no answer"
instead of "here's the partial information"), occasional missed-
opportunity (one subagent could have answered but didn't fan out
correctly), occasional consensus-without-explanation (all subagents
agree but the user can't see why).

**Work in this theme:**

- ✅ Conflict detector pre-synthesis pass *(already shipped)*
- ✅ Fabrication guard at orchestration boundary *(already shipped)*
- ✅ Plan-then-execute toggle *(already shipped)*
- 🟡 **Reflexion + retry on weird output** (BACKLOG §0 Wk3, ~1 day)
- 🟡 **Numeric-trace guard** — fabrication-guard-for-numbers
  - Today's fab-guard rejects ZERO-tool-call subagents
  - Numeric guard would reject claims with numbers that don't appear in any tool call
  - BACKLOG §4
- 💭 **Devil's advocate toggle** (BACKLOG §0 Wk4+)
- 💭 **Bull/Bear debate** (BACKLOG §0 Wk5+)
- 💭 **Per-claim confidence scoring** (BACKLOG §1)
- 💭 **Auto-orchestrator (Magentic ledger)** — meta-router decides tier + features (§1 + §9)
- 💭 **Output verification loop** — pattern from nibzard catalogue

**Sequencing:** Reflexion is the highest-impact single change for
quality. Numeric-trace guard is the highest-impact correctness change.
Both before Devil's-advocate / Bull-Bear which are bigger features
better timed alongside the leaderboard's per-company pages where the
extra depth has somewhere to render.

**Risk:** each of these increases LLM cost per query. Sequence so cost
visibility (HITL Step 1) is in before retry-heavy features so the user
sees what they're spending.

---

## 3. Sample user stories

Stories follow standard form: *"As [persona], I want [capability] so
that [outcome]."* See §7 for personas.

### Theme 1 — Operational reliability

> **T1.S1.** As the only operator of the app, I want auto-relogin to
> recover within 5 minutes when Inderes' SSO Session Max expires, so
> that I can demo at any hour of the day without manual intervention.

*Already shipped:* 4×/day cron. *Remaining:* chain trigger from
refresh-cron, app-level gist re-pull.

> **T1.S2.** As the developer of the app, I want disk usage alerts
> at the 20 GB threshold, so I'm warned BEFORE Bash tools start
> failing with ENOSPC.

*Implementation:* launchd hourly check + `osascript display
notification`. ~15 min. Scripted in chat earlier today.

> **T1.S3.** As the developer of the app, I want a `make tidy`
> target that safely removes regenerable caches across the dev box,
> so I can free 5-10 GB in seconds when I notice the warning.

*Implementation:* shell script + Makefile entry. ~30 min.

> **T1.S4.** As the operator of the app, I want Cloud uptime
> monitoring (1-min ping with notification on 5-min failure), so
> that I know the demo is broken before a user reports it.

*Implementation:* GitHub Actions cron + curl + notification.
~30 min. Defer until after self-heal + disk hygiene since they
reduce the rate of incidents this would alert on.

### Theme 2 — Analyst depth

> **T2.S1.** As an analyst asking for a valuation, I want to see how
> sensitive my fair-value is to ±1pp shift in k or ±5pp in ROE, so
> I can defend my central scenario in a discussion with someone who
> challenges the inputs.

*Shipped today (`809e11f`):* collapsible 5×5 heatmap, ROE × k AND
g × k. Centre cell outlined as analyst's base scenario.

> **T2.S2.** As an analyst comparing 6 years of fundamentals, I want
> a Qt-style 5-year historical metrics table as an expander, so I
> can scan growth / margin / leverage trends without leaving the
> agent's answer.

*Status:* next up after sensitivity ships. ~4-5 h. Requires expanded
`get-fundamentals` call, parser, and table renderer.

> **T2.S3.** As an analyst reading a synthesis, I want footnote
> markers `[¹]` after every quantitative claim, so I can click and
> see which tool call produced that number.

*Status:* BACKLOG §1, "Footnote markers + sources panel" *(1 day)*.
CSS already exists (`.ia-fn`) but unwired. Activate the CSS, thread
the markers through synthesis prompt + parser.

### Theme 3 — Sustained-monitoring product

> **T3.S1.** As an analyst in the morning, I want a sortable
> leaderboard of my 30 watchlist names so I can identify the most
> attractive setups in 30 seconds without typing a query.

*Phase 3.* Default sort by safety margin DESC. Filterable by
sector / Inderes recommendation / P/B threshold. ~3 h after Phase 2.

> **T3.S2.** As an analyst noting a thesis, I want to add an
> observation to a per-ticker markdown notebook that the agent will
> reference next time I ask about that ticker, so insights compound
> rather than vanish.

*Phase 1.* Foundation step. `notes/<TICKER>.md` + agent read/write
tools. ~3-4 h. The earliest user-visible "continuity" feature.

> **T3.S3.** As an analyst noticing a name dropped 5% overnight, I
> want to click into the per-company page, see the buy-price grid +
> latest Inderes target + recent news, and ask the agent for an
> explanation in one cross-mode click, so I never lose the question
> by switching contexts.

*Phase 4.* The killer flow. ~4 h after Phase 3.

### Theme 4 — Source coverage

> **T4.S1.** As an analyst comparing Sampo to Allianz, I want both
> companies to get the same depth of treatment so I can put Nordic-
> vs-European insurance valuation in context.

*Status:* requires Yahoo MCP hosted (BACKLOG §2 Path A Fly.io
deployment). Code path is already wired.

> **T4.S2.** As an analyst worried about Inderes BVPS being stale
> (last reported Q is 2-3 quarters ago for some names), I want the
> agent to fall back to Yahoo's Q-fresh BVPS when available, so the
> valuation reflects the most recent balance sheet.

*Status:* code-pattern straightforward; needs explicit prompt
guidance to QUANT to prefer Yahoo BVPS when staleness > N months.

### Theme 5 — Agent quality

> **T5.S1.** As a user reading the agent's answer, I want every
> quantitative claim to be traceable to a tool call, so I can sanity-
> check the most important numbers without opening the trace
> expander.

*Theme 2 overlap.* T2.S3 implements this.

> **T5.S2.** As a user, I want the agent to refuse to answer when it
> doesn't have grounded data, rather than producing a plausible-
> looking guess, so I can trust the answers I get to be defensible.

*Already shipped:* structural fabrication-guard at orchestration
boundary. Numeric-trace guard is the next refinement.

> **T5.S3.** As a user with a Pro-tier model available, I want the
> agent to dispatch deeper reasoning automatically on ambiguous
> queries instead of always-Lite, so quality scales with question
> complexity.

*Status:* BACKLOG §1 "Auto-orchestrator (Magentic ledger)". Big
feature, defer until after Reflexion + footnotes ship.

---

## 4. 30 / 60 / 90 day roadmap

### Next 30 days (rest of May 2026)

**Goal:** ship operational hardening + close out Theme 2 + start Theme 3 Phase 1-2.

| Theme | Item | Effort | Status |
|---|---|---|---|
| T1 | Self-healing chain trigger | 30 min | 💭 |
| T1 | App-level gist re-pull | 30 min | 💭 |
| T1 | Disk hygiene launchd cron | 30 min | 💭 |
| T2 | Sensitivity grids | 4 h | ✅ shipped today |
| T2 | 5y historical metrics table | 4-5 h | 🟡 next |
| T2 | Footnote markers | 1 day | 🟡 next |
| T3 | Phase 1 — per-ticker notebook | 3-4 h | 💭 |
| T4 | Yahoo MCP Fly.io deployment | 45 min | 🟡 |
| T4 | Yahoo settings toggle | 1-2 h | 🟡 |
| T5 | Numeric-trace guard | 1 day | 💭 |

**~5-6 working evenings.** Realistic if 2-3 nights per week. Demo-
ready content for any technical audience.

### Next 60 days (May–June 2026)

**Goal:** Theme 3 Phases 2-4 land — leaderboard becomes the daily-driver landing.

| Theme | Item | Effort | Status |
|---|---|---|---|
| T3 | Phase 2 — SQLite state + nightly batch | 3 h | 💭 |
| T3 | Phase 3 — Leaderboard page | 3 h | 💭 |
| T3 | Phase 4 — Per-company drill-down | 4 h | 💭 |
| T5 | Reflexion + retry | 1 day | 💭 |
| T5 | HITL Step 1 — cost tracking + pre-flight | 1 day | 💭 spec ready |

After this 60-day window: a usable leaderboard with per-company depth,
plus the agent is more self-aware about its own retries and costs.

### Next 90 days (May–July 2026)

**Goal:** Theme 3 Phases 5-6 + Claude Design loop closure → ship the
"Inderes Agent Desk v0.4" milestone with leaderboard as flagship.

| Theme | Item | Effort | Status |
|---|---|---|---|
| T3 | Phase 5 — Scenario sliders + market-pricing reverse | 4 h | 💭 |
| T3 | Phase 6 — Visual polish loop with Claude Design | open | 💭 |
| T2 | Bloomberg ANR-vs-target table | 1 day | 💭 |
| T5 | Devil's advocate toggle | 2 h | 💭 |
| T4 | Second MCP source (SEC EDGAR or FRED) | 1 day | 💭 |

Beyond 90 days: Bull/Bear debate, auto-orchestrator, autonomous
nightly eval, frontend rewrite. All BACKLOG §0 items that legitimately
need this product to be more mature before they pay off.

---

## 5. Anti-themes — what we deliberately won't do

Scope discipline is half the product. Explicitly off the table:

- **Multi-user accounts / SaaS / monetisation.** Single-user personal
  tool. Adding accounts would 5× the surface area for 0× user value
  at this stage.
- **Real-time intraday price streaming.** Yahoo's 15-min delay is fine
  for fundamentals-driven methodology. Streaming would complicate
  cost + complexity for marginal analytical gain.
- **Automated trading or order routing.** Explicitly stated in
  `PURPOSE.md` non-goals. The agent surfaces signals; the user makes
  the decision.
- **Bloomberg-feature-parity.** Bloomberg is $32k/year + an entire
  business model around proprietary data. We're not chasing that —
  we're building a single-user research workflow on the SUBSET of
  questions that fundamentals-based research can answer with public + Inderes data.
- **Backtesting the valuation methodology.** The owner has 5 years of
  Excel-tracked decisions to backtest against, but that's a separate
  workstream not tied to this agent.
- **Replacement of the chat agent.** Chat stays as the deep-dive /
  explanation mode. Leaderboard is the daily-driver overlay, not a
  replacement.
- **Public exposure of the leaderboard.** Personal data (positions,
  watchlist taxonomy, thesis notes). The chat agent could plausibly
  be public; the leaderboard is single-user-only.
- **Inderes-brand parity.** Explicitly not Inderes-branded. The
  README disclaimer is load-bearing.
- **Predicting prices.** Signal-surfacing, not signal-generating.
  "Here's what Inderes thinks vs what your methodology thinks" is the
  product. "Here's what will happen" is not.

---

## 6. Decisions that need an explicit call now

Eight calls to make before too much more code lands. Most are
sequencing or yes/no questions; couple are scope.

### D1. Theme 3 fork strategy — when (if ever) to split repos

Recommendation in design brief Part 2: **same repo, defer fork until
public-exposure plans materialise** (Q4 2026 at earliest). Need
explicit acceptance to lock this in so the next several months of
work don't accidentally start with the wrong assumption.

### D2. Yahoo hosting target — Fly.io vs Modal vs Cloudflare

Fly.io plan in BACKLOG §2 Path A is the current default. Modal is a
simpler MCP-first option but $0.30/hour active. Cloudflare Workers is
free but limited tool runtime. Need a yes/no on Fly Path A so the
deployment can happen this weekend.

### D3. Yahoo UI surface — settings toggle vs hidden flag

Recommendation: **settings toggle in sidebar, default OFF.** Preserves
Inderes-first brand identity. Allows opt-in per session. See earlier
conversation transcript for rationale.

### D4. Cost-tracking and HITL Step 1

The HITL proposal (`docs/hitl_proposal.md`) was a Wk 2 plan that got
deferred. With Reflexion now Wk 3 next-up and cost-doubling risk
real, HITL Step 1 (cost tracking, no UI gate yet) should land BEFORE
Reflexion. Need acceptance.

### D5. Footnote markers — sharper renderer or wait for leaderboard?

Footnote markers are partway BACKLOG'd. Two ways to ship:
- 1-day light version: activate dead `.ia-fn` CSS, basic source link
- 2-day richer version: per-claim provenance with tool-call attribution

Recommendation: **1-day light first.** Richer version becomes natural
once leaderboard's per-company pages exist where the depth can render.

### D6. Numeric-trace guard — separate item or merge into fab-guard?

Today's fab-guard rejects zero-tool-call subagents. The numeric
variant would reject claims whose numbers don't appear in any tool
call output. Same orchestration tier, different rule.

Recommendation: **merge into existing guard module**, separate
function. Reuses the audit logging path. ~1 day.

### D7. Agentic-patterns catalogue commitments

The `docs/agentic_patterns_mapping_2026-05-11.md` document identified
6 patterns worth adopting (Lethal Trifecta Threat Model, Action
Replay, Subject Hygiene, Agent Circuit Breaker, Tool Search Lazy
Loading, etc.). Need an explicit call: which 2-3 to commit to in
the next quarter, which to keep as "good to know" reference.

### D8. 5y historical table — defer until 10-K/Q-level MCP, or proceed with Inderes-only?

Inderes MCP `get-fundamentals` may not expose all the EV / OEPS /
Q-segment metrics the Qt example needs. Two paths:
- **A.** Proceed with whatever Inderes covers, gaps marked "—"
- **B.** Wait until SEC EDGAR MCP is added (additional Theme 4 work)

Recommendation: **path A.** A 70%-filled table beats no table.

---

## 7. Personas + jobs-to-be-done

Three personas, only the first is actively building today. The other
two inform future-proofing.

### P1. Juho-the-analyst (the only active persona)

- **Daily workflow**: opens app at 07:30, scans market overnight, picks
  2-3 names to deep-dive, captures thesis notes, makes buy/sell decisions
- **Pains today**: starts fresh every session; can't browse; chat-only
  surface forces him to already know what to ask
- **Jobs**: morning brief, anomaly spotting, single-company deep dive,
  thesis capture, occasional cross-source check
- **Will love when shipped**: T3 leaderboard, T2 footnotes, T4 Yahoo
- **Will tolerate today**: chat with valuation expander

### P2. Juho-the-builder (himself, evolving the system)

- **Workflow**: iterates on prompts, evals, adds features, demos to
  technical audiences
- **Pains today**: operational fragility (token expiry, disk full),
  occasional Cloud reboots required
- **Jobs**: ship features fast without breaking demo, evals as guardrail
- **Will love when shipped**: T1 operational reliability completed
- **Will tolerate today**: manual intervention every few days

### P3. Future-collaborator (deferred, not in current scope)

- **Workflow**: would join if/when the leaderboard mode becomes a
  small-team tool (3-5 analysts)
- **Pains imagined**: no multi-user, no shared watchlist, no
  permission boundaries
- **Jobs**: same as P1 but with collaboration overlay
- **Will love if ever**: shared watchlists, comment threads on
  per-ticker pages
- **Will tolerate**: nothing yet — they're not real users

**Implication of this persona triangle:** every decision today should
serve P1's daily workflow. P2's needs are infrastructure. P3 is a
"what if" not a "what next". Don't trade P1 value for P3
hypothetical-multi-user safety.

---

## 8. Closing note

This document is a **frame**, not a contract. The five themes are
where energy should flow; the stories show what concrete work looks
like in each theme; the 30/60/90 matrix shows realistic sequencing
given evening-time effort levels.

**Update this doc in place when:**
- Theme priorities shift (e.g. a P1-level operational incident makes
  Theme 1 urgent again)
- A new theme emerges (e.g. if/when collaborator mode becomes real,
  that's a new theme not a sub-bullet)
- A theme is "done" (e.g. Theme 1 reaches stable steady-state with
  ~zero incidents/month — collapse it to maintenance)

**Re-read this doc before BACKLOG.md when:**
- Planning a new sprint
- Onboarding a coding agent for new work (point them at the relevant
  theme's "Work in this theme" list)
- Defending a "no, not now" call on a scope-creep idea
- Producing demo narrative (the five themes map cleanly to a 10-min talk)

The five themes describe what this project is becoming. The product
the owner actually wants is built in their intersection: an analyst
workflow that's deep where each answer demands depth (T2 + T5),
broad where coverage demands breadth (T4), persistent where insight
demands continuity (T3), and reliable where any of the above demands
the lights stay on (T1).
