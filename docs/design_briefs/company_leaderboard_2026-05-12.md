# Design brief — sustained company-view + leaderboard mode

**Date:** 2026-05-12
**Status:** Pre-design brief. Material to paste into Claude Design (or
similar) alongside the repo link for a design conversation.
**Audience:** designer + project owner.

---

## TL;DR

The current product is a **Q&A research agent** — user asks a
question in natural language, agents fan out, LEAD synthesises. It
works well for *"explain me X about company Y"* moments. But the
project owner's actual long-running workflow is structurally
different: a **buy-price-driven, scenario-based valuation framework**
maintained in Excel since 2021, where each company sits in a grid of
*"what would I pay at each level of growth credit"*.

This brief proposes adding a **sustained company-view + leaderboard
mode** that lifts the Excel methodology into the agent stack: each
company in scope is continuously evaluated against four scenarios
(Heikko / Perus / Hyvä / Markkinahinnoittelu), and the user browses a
leaderboard sorted by safety margin / expected return / quality
score. The chat agent stays available as the explanation/drill-down
mode underneath; the new mode is the **daily-driver landing surface**.

**Same repo, new Streamlit page.** Recommended over a separate repo
because the data layer (Inderes + Yahoo MCPs), valuation engine
(`src/inderes_agent/valuation/`), and user-context concepts (auth,
forensic logs) are shared. See [§9 *Same repo vs separate*](#9-same-repo-vs-separate).

---

## Map

- [§1 What we have today](#1-what-we-have-today)
- [§2 The product hypothesis — from Q&A to sustained view](#2-the-product-hypothesis--from-qa-to-sustained-view)
- [§3 The Excel methodology (load-bearing — don't paraphrase, render)](#3-the-excel-methodology-load-bearing--dont-paraphrase-render)
- [§4 What the new mode does, concretely](#4-what-the-new-mode-does-concretely)
- [§5 UI shape candidates](#5-ui-shape-candidates)
- [§6 Integration with the existing chat agent](#6-integration-with-the-existing-chat-agent)
- [§7 Design decisions to make explicitly](#7-design-decisions-to-make-explicitly)
- [§8 Reference systems to study](#8-reference-systems-to-study)
- [§9 Same repo vs separate](#9-same-repo-vs-separate)
- [§10 Out of scope for this brief](#10-out-of-scope-for-this-brief)

---

## 1. What we have today

`inderes-mcp-agent-system` is a multi-agent stock-research conversation
system. Quick orientation for the designer:

- **Agent fleet**: LEAD orchestrator + 5 specialised subagents
  (QUANT / RESEARCH / SENTIMENT / VALUATION / PORTFOLIO), all running
  on Microsoft Agent Framework + Gemini.
- **Data plane**: Inderes MCP (live in production — analyst
  recommendations, target prices, fundamentals, transcripts, forum,
  model portfolio). Yahoo MCP integration code shipped but sidecar
  not yet hosted — production runs Inderes-only today.
- **Valuation engine**: deterministic Greenwald-Gordon hybrid in
  `src/inderes_agent/valuation/engine.py`. ~1200 LOC of pure Python,
  ~130 tests including 20 Excel-parity cases. **This is the math
  backbone the new mode lifts.**
- **UI**: Streamlit "Trading Desk" — chat-style, dark mode, terminal
  DNA. Per-query forensic record in `~/.inderes_agent/runs/<ts>/`.
- **375 tests** across structural correctness (not LLM-output
  matching).

For full architecture see [`ARCHITECTURE.md`](../../ARCHITECTURE.md);
for the layered model see
[`MULTI_AGENT_ARCHITECTURE.md`](../../MULTI_AGENT_ARCHITECTURE.md).

**What works well in the current Q&A mode:**

- Drill-down on a specific company: *"explain Sampo's outlook for
  2026"* gets a structured multi-perspective answer with sources
- Comparative questions: *"Nordea vs Sampo on profitability"* fans
  out across both
- Surface trust signals (Inderes recommendation, target prices,
  insider activity, valuation engine math)

**What's structurally awkward in Q&A mode:**

- **No persistence across sessions** — every Sampo question starts
  fresh; the agent doesn't "remember" previous Sampo conversations
- **No browsing** — the user has to ALREADY know what they want to
  ask; serendipity ("hey, this stock looks cheap, what's going on")
  isn't supported
- **No leaderboard** — there's no way to surface *"of the 30
  companies you care about, here are the 5 with the highest current
  safety margin against Perus-scenario EPV"*
- **No multi-company state** — analysing 30 companies is 30
  conversations, no shared context

---

## 2. The product hypothesis — from Q&A to sustained view

> *"Most analyst workflows aren't 'I have a question to ask'. They're
> 'I'm watching 30–50 names, where are the opportunities, what
> changed since yesterday, where should I dig?' The Q&A agent is
> useful but it's the deep-dive tool, not the daily-driver."*

The hypothesis: **80 % of the actual workflow value lives in the
sustained-monitoring mode**, with the Q&A agent as the on-click
drill-down for the 20 % of deeper questions.

Specifically the new mode supports four jobs-to-be-done that the
current Q&A mode does badly or not at all:

| Job | Current Q&A | Proposed sustained view |
|---|---|---|
| **"What did the market do to my watchlist overnight?"** | Ask 30 individual questions | Single dashboard, sorted by `Δ price` |
| **"Which of my names is most attractive right now?"** | Impossible — no cross-company state | Leaderboard sorted by `safety margin vs Perus-scenario EPV` |
| **"Did Sampo's Inderes target change this week?"** | Ask again, hope to remember last week's answer | Persistent ticker view with timeline of `target_price` changes |
| **"Show me everything that's at -30 % to -50 % vs my valuation"** | Impossible | Filter on `current_price / fair_value` ratio |

---

## 3. The Excel methodology (load-bearing — don't paraphrase, render)

The project owner has been running a personal valuation methodology in
Excel since 2021. The Greenwald-Gordon engine in
`src/inderes_agent/valuation/engine.py` is the codified version of
this same methodology (Excel parity test suite confirms ±0.02 €
agreement on 10 reference companies).

The math is **deliberately simple and transparent**, with three
load-bearing concepts a designer must render correctly:

### 3.1 Three scenarios produce three fair-values

For each company, three inputs are estimated:

| Input | Heikko | Perus | Hyvä |
|---|---|---|---|
| **ROE (sustainable)** | conservative (e.g. 11 %) | central (e.g. 12 %) | optimistic (e.g. 13 %) |
| **Growth (g)** | typically same 5 % across all scenarios | | |
| **Required return (k)** | typically same 10 % across all scenarios | | |

The engine then computes for each scenario:

- **Tasearvo (book value)**: per-share BVPS, scenario-invariant
- **EPV (Earnings Power Value)**: `BVPS × (ROE / k)` — what the
  company is worth if it never grew, paying out all earnings forever
  at the required-return rate
- **Kasvun arvo (growth value)**: incremental value from sustained
  growth at rate g, computed from a Gordon-extension formula
- **Kokonaisarvo (fair value)**: `Tasearvo + (EPV − Tasearvo) + Kasvun arvo` (= EPV + Kasvun arvo when ROE > k, else floored at Tasearvo)

Example (Honkarakenne Oyj from the Excel screenshot):

| Komponentti | Heikko | Perus | Hyvä |
|---|---|---|---|
| EPS (normalised) | 0.30 € | 0.34 € | 0.37 € |
| EPV | 3.02 € | 3.35 € | 3.69 € |
| Tasearvo | 2.79 € | 2.79 € | 2.79 € |
| Kilpailuedun arvo (= EPV − Tasearvo) | 0.22 € | 0.56 € | 0.89 € |
| Kasvun arvo | 0.22 € | 0.56 € | 0.89 € |
| **Kokonaisarvo** | **3.24 €** | **3.91 €** | **4.58 €** |
| Nykyhinta-discount vs scenario | -19 % | -32 % | -42 % |

### 3.2 The "buy-price grid" — the killer concept

This is the **load-bearing UX innovation** in the Excel and what the
designer MUST render carefully. For each scenario, the methodology
computes five ladder rungs of *"what would I be willing to pay"*:

```
                  Heikko    Perus     Hyvä      Nykykurssi
Tasearvo          2.79      2.79      2.79         2.64
EPV               3.02      3.35      3.69         2.64
EPV+Kasvu 25 %    3.07      3.49      3.91         2.64
EPV+Kasvu 50 %    3.13      3.63      4.13         2.64
EPV+Kasvu 75 %    3.18      3.77      4.36         2.64
```

Read this as: *"In the Perus scenario, if I want to pay only for the
existing earnings power (EPV) and zero growth credit, I'd pay up to
3.35 €. If I'm willing to credit the company 50 % of the
expected growth, I'd pay up to 3.63 €."*

At the current price of 2.64 € the safety margin against Perus-EPV
is 19 % — *"I'm paying for less than the company's existing earnings
power; the market is effectively pricing zero growth."*

**This grid IS the buy decision.** Not "is the stock undervalued
yes/no" but "at which growth-credit level does the price still leave
me a safety margin in MY central scenario." It's a 5×3 grid of buy
prices, the user picks the cell that fits their risk tolerance and
conviction.

### 3.3 The market-pricing column

The fourth scenario in the Excel is "Markkinahinnoittelu" — what
ROE/growth combination would JUSTIFY the current price? When current
price < Tasearvo, this is "0 % growth, 0 % competitive advantage —
the market is paying only for book value." This is the *"what would
have to be true"* analysis.

For Honkarakenne at 2.64 € < 2.79 € book value, market is implicitly
saying "competitive advantage = 0, sustainable growth = 0, ROE < k."

### 3.4 Reference data fields the methodology needs per company

From the Yahoo-table-style structure the owner sketched:

```
Yhtiö, Markkina, Market Cap MEUR, Osakekurssi (live),
fair_value (= Perus Kokonaisarvo), yli_ali_arvostus%,
tuotto_odotus% (implied return at current price),
fcf_tuotto% (FCF yield), Ostohinta (target buy at chosen scenario),
P/B (current), GM (= EPV / Tasearvo = quality multiplier),
kasvun_hinta% (what % of fair_value comes from growth credit),
Rock Bottom (= Tasearvo or floor), kasvu_norm, tuotto-vaatimus,
EPV, GV, EPS_norm, FCF_norm, OPO/osake (BVPS),
date_book_value, ROE_laskennassa, ROE_norm,
ROE_hist_ka (5y average), ROE_hist_median, ROE_3v, ROE_5v
```

These are the data fields each row of the leaderboard would carry.

---

## 4. What the new mode does, concretely

A **"Company View" mode** running alongside the existing chat:

### 4.1 Leaderboard / screener page

Default landing. Rows = companies (the user's watchlist + Inderes
universe ~150 names, configurable). Columns:

- Yhtiö + ticker
- Sector (for filtering)
- Markkina-arvo
- Nykykurssi
- **Perus-EPV fair value** (the central anchor)
- **Safety margin vs Perus-EPV** (= `1 - price/EPV`)
- **Expected return at current price** (= rearranged from EPV math)
- Inderes recommendation + target (for cross-reference)
- ROE 5v median
- P/B current
- Quality multiplier GM (EPV / Tasearvo) — > 1 = competitive
  advantage exists
- Date of last update + freshness flag

Sortable by every column. Filterable by sector, safety margin
threshold, Inderes recommendation, custom watchlist tag.

**The killer view**: sort by Safety Margin DESC, filter by *"Inderes
recommendation in ['LISÄÄ', 'OSTA']"*, see your top 10 candidates
where Inderes also agrees the company is interesting.

### 4.2 Per-company sustained view (drill-down)

Click a row → dedicated page for that ticker. Persistent across
sessions (= a `notes/SAMPO.HE.md` style file that accumulates content
over time — already BACKLOG'd as the "per-ticker markdown notebook"
in the agentic research digest).

Top half:

- **Buy-price grid** (the 5×3 from §3.2) rendered as a heatmap with
  current price marked
- **Scenario cards**: Heikko / Perus / Hyvä side-by-side with
  inputs (ROE, k, g) editable as sliders → re-computes Kokonaisarvo
  live (no LLM call needed, pure Python via the existing valuation
  engine in `src/inderes_agent/valuation/`)
- **Markkinahinnoittelu reverse-engineered**: "at current price, the
  market is paying for ROE = X%, growth = Y%"

Bottom half:

- Inderes consensus block (recommendation + target + last update)
- Recent news / forum sentiment (when SENTIMENT subagent data exists)
- Historical ROE chart (the 6-bar chart visible in the Excel
  screenshot)
- **"Ask the agent about this company"** button — opens the existing
  chat with the ticker pre-filled as context. The chat agent is the
  drill-down explanation tool when sliders + leaderboard + sentiment
  signals raise a question.

### 4.3 Update cadence

- **Live**: current price + market cap (Yahoo MCP `get_snapshot`,
  ~15min delayed, cheap)
- **Daily**: Inderes recommendation + target (changes infrequently,
  one MCP call per company per day = ~30 calls = trivial)
- **Quarterly**: BVPS + ROE history (when Q-report lands; Yahoo MCP
  picks up Q-fresh BVPS, Inderes picks up estimates)
- **User-triggered**: scenario inputs (ROE / k / g) — user edits
  these, system recomputes immediately

Refresh strategy: a GitHub Actions cron at 07:30 EET runs a batch
script that for each company in scope, calls the existing MCP tools
for fresh data, recomputes the scenarios via the valuation engine,
writes a SQLite row. Streamlit reads SQLite on page load. No LLM
calls in the batch — the scenarios are pure math.

This is the proposed approach in the agentic-research digest as
"continuity foundation" — see
[`docs/agentic_research_digest_2026-05-11.md`](../agentic_research_digest_2026-05-11.md)
§2 Pull #4.

---

## 5. UI shape candidates

Three reference shapes the designer should evaluate against the
methodology:

### Option A — Table-first (Stockopedia / Simply Wall St -style)

Spreadsheet-like dense leaderboard at the top, click a row for
expanded detail in a side drawer. Honours the Excel-native muscle
memory of the user. Works for cold-browsing.

**Strength**: dense, sortable, comparable across columns.
**Weakness**: low visual hierarchy — every cell looks the same;
hard to direct eye to the most important number per row.

### Option B — Card-grid (Hex Magic / Julius AI -style)

Each company is a card with a mini-buy-price-heatmap + current
price marker + Inderes recommendation pill. Grid view, 3-4 cards per
row. Click → full per-company page.

**Strength**: visual scanning is fast — buy-price heatmap is
recognisable at a glance, "is this company in the green or red"
answerable in <2 seconds.
**Weakness**: takes more screen real estate per company; harder to
sort by arbitrary column.

### Option C — Hybrid (Bloomberg PORT / Tableau Pulse -style)

Sortable table view as default, but each cell renders a tiny
inline data viz where useful: micro-bar for safety margin, sparkline
for price history, coloured pill for Inderes recommendation. Cmd+K
opens scenario sliders for the focused company without leaving the
table.

**Strength**: dense like table, scannable like cards, supports
multiple parallel mental models.
**Weakness**: highest implementation complexity; needs careful
column-width design.

Designer's call. My (engineer's) bias: **C**, because the
methodology has multiple equally-important numbers per row (current
price, safety margin, Inderes target, ROE trend) and embedded viz
beats column-density-vs-readability tradeoffs.

### Important UX rendering decisions for ANY shape

1. **The buy-price grid is the centrepiece**, render it correctly.
   Heatmap (red→green from current-price marker outward), labels in
   €, the grid orientation: scenarios as columns, growth-credit
   ladder rungs as rows.
2. **Safety margin is the headline metric**. Render as a
   colour-coded pill: green > 20 %, amber 0–20 %, red < 0 %.
3. **Quality multiplier GM** (= EPV / Tasearvo) is the
   "is there a competitive advantage at all?" signal. GM ≈ 1 means
   pure book-value company, GM > 1.5 means strong competitive
   advantage. Render as a small icon or pill.
4. **Inderes recommendation + this system's safety margin should
   render side-by-side**, not stacked. Both are buy/sell signals
   from different methodologies; the user wants to see disagreements
   instantly. *"Inderes LISÄÄ but this system shows -32 % safety
   margin"* is the interesting signal.

---

## 6. Integration with the existing chat agent

The chat agent and the new sustained view are complementary, not
overlapping. Concretely:

| Workflow | Chat-mode role | Sustained-view role |
|---|---|---|
| *"Show me my top 10 candidates"* | impossible | leaderboard, sorted |
| *"Why does Sampo have such a high safety margin?"* | answers with multi-agent fan-out | leaderboard click → per-company page → "Ask agent" button → chat with ticker pre-filled |
| *"Compare Nordea and Sampo"* | answers in conversational form | not really, but per-company pages can be opened in two tabs |
| *"What changed at Sampo since last month?"* | answers if last-month data is in conversation context | per-company page shows timeline of Inderes target changes, news entries, scenario-input revisions |
| *"Add Kone to my watchlist"* | impossible | obvious watchlist-management UI |

→ **The two modes share a sidebar nav.** Default landing is the
leaderboard. Top-level button: *"💬 Ask agent"* → chat. Each
per-company page has *"💬 Ask agent about $TICKER"* shortcut.

---

## 7. Design decisions to make explicitly

These are the choices a designer must make, with my engineer's
opinion in italics where I have one:

### Q1. Universe size

*Watchlist-only (user-curated, ~30 names)* vs *Inderes
universe (~150 Helsinki names)* vs *Inderes + Yahoo international
(~500 names)*.

*My view: start watchlist-only because the data-fetch cron is then
~30 MCP calls/day = trivial cost; expand to full Inderes when the UI
proves out. International is Q2 after Yahoo MCP is hosted.*

### Q2. Update cadence

*Daily nightly batch* vs *every-N-hours* vs *on-demand per company
when user opens its page*.

*My view: daily nightly batch + on-demand override per company. The
methodology doesn't need higher resolution than daily; live price is
the only field that needs sub-daily refresh and Yahoo's 15-min cache
covers that.*

### Q3. Scenario input source

*User edits ROE/k/g manually per company* (Excel-style) vs *engine
auto-suggests from history* (current valuation agent does this) vs
*both — auto-suggest with "edit override" pencil*.

*My view: hybrid. Auto-suggest from `get-fundamentals` history (the
ROE selection rule in `tests/valuation/test_roe_selection.py` already
codifies this), user can override per company.*

### Q4. Persistence layer

*SQLite + per-ticker markdown notes* vs *Postgres + structured user
state* vs *plain JSON files*.

*My view: SQLite for structured (price snapshots, scenarios,
recommendations); markdown for user notes per ticker. SQLite is fine
at single-user single-machine scale; markdown gives the user direct
file-system access for backup + diff + manual edit.*

### Q5. Mobile?

*Mobile-first responsive* vs *desktop-only, mobile = read-only*.

*My view: desktop-only edit, mobile read-only browse. The
leaderboard works on mobile; scenario slider editing is awkward on
touch. Acceptable tradeoff for a single-user tool.*

### Q6. Leaderboard sorting defaults

*By Safety Margin vs Perus* vs *By Δ price 1d* vs *By Inderes-system
disagreement* vs *Custom per session*.

*My view: default = by Safety Margin vs Perus DESC (the central
question the methodology answers); offer Δ price + disagreement as
one-click alternate sorts.*

### Q7. Multi-portfolio / tags?

*Single flat watchlist* vs *tagged subsets (e.g. "Banks", "Real
estate")* vs *named portfolios with weighting*.

*My view: tagged subsets, no weights. Tags handle the 80 % use case
(filtering to a sector or thesis); explicit portfolio weighting
crosses into actual-money-management territory which is out of
scope.*

### Q8. "Ask the agent" trigger points

*Single button per company page* vs *contextual prompts at multiple
points* vs *agent observations rendered inline in the leaderboard*.

*My view: single button per company page + an inline "💡 Why is
Sampo at 32 % SM? Ask agent →" pre-canned-question chip when the
leaderboard shows anomalously high safety margins. The agent doesn't
push itself; the UI offers it when there's a question worth asking.*

---

## 8. Reference systems to study

For the designer to look at, ordered by relevance:

1. **Stockopedia** (UK retail stock-screener) — closest in spirit:
   methodology-driven scoring per company, leaderboard, custom
   filters, drill-down. <https://www.stockopedia.com>
2. **Simply Wall St** — visual snowflake/circle viz for valuation
   that compresses many dimensions into a glance. Heavy use of
   icons + colours. <https://simplywall.st>
3. **Bloomberg PORT / EQS** — institutional benchmark. PORT for
   portfolio analytics, EQS for screening. Inspirational for what a
   "professional" sustained-view looks like.
4. **Tableau Pulse / Hex Magic** — modern data-analytics UX with
   embedded LLM helpers. Closest to the "table + click → agent
   explains" interaction pattern.
5. **Perplexity Finance** — recent entry, AI-native financial
   research. <https://www.perplexity.ai/finance>
6. **Koyfin** — Bloomberg-on-the-web for retail. Useful for
   "professional but accessible" colour/density tradeoffs.
7. **The user's own Excel** — see the screenshots accompanying this
   brief. The buy-price grid + scenario cards + market-pricing
   reverse-engineering are the methodology essentials.

What NOT to emulate:

- Yahoo Finance, Google Finance — too low-density, not methodology-
  driven.
- Robinhood-style apps — gamified, deliberately addictive UX; we
  want the opposite of that for serious-research use case.
- TradingView — chart-first, this product is fundamentals-first.

---

## 9. Same repo vs separate

The project owner asked whether this new mode should be in the same
repo as the chat agent or a separate repo. My view: **same repo**.

**Arguments for same repo:**

- **Shared data plane**: both modes use the same Inderes MCP +
  Yahoo MCP. Two repos = two OAuth chains, two auto-relogin crons,
  two gist mirrors, two sets of Cloud secrets.
- **Shared valuation engine**: the new mode IS the valuation engine
  applied across many companies. Forking it into a separate repo
  means maintaining two copies of `valuation/engine.py` indefinitely.
- **Shared user context**: watchlist, ticker notes, auth, daily
  query cap — one user, one state.
- **Killer flow is cross-mode**: click a leaderboard row → open
  per-company page → click "Ask agent" → chat with ticker
  pre-filled. This flow is one-repo trivial, two-repo painful.

**Arguments for separate repo:**

- **Different deployment target**: if the new mode is ever
  publicly hosted as a product (with paid tier, accounts, etc.) and
  the chat agent remains personal, the boundary becomes natural.
- **Different LLM dependency**: the new mode uses LLM only for the
  on-demand drill-down. The leaderboard math is pure Python and
  could run with zero Gemini cost. Separate repo would make this
  cost separation explicit.

→ **Recommendation: same repo, Streamlit multipage app.** Migrate to
two repos only if/when the public-product hypothesis materialises
(which is out of current scope).

Structurally: `ui/app.py` becomes `ui/pages/01_chat.py` +
`ui/pages/02_company_view.py` + `ui/pages/03_leaderboard.py`,
Streamlit handles routing. Shared `ui/components.py` continues to
serve both. Backend in `src/inderes_agent/` is untouched — the new
mode adds `src/inderes_agent/company_view/` (or similar) with the
batch update script + SQLite layer.

---

## 10. Out of scope for this brief

These are NOT what the designer should solve in v1:

- **Multi-user accounts + monetisation** — single-user tool.
- **Real-time intraday price streaming** — Yahoo's 15-min delay is
  fine for this methodology.
- **Backtesting the valuation methodology against past returns** —
  the user has 5 years of Excel-tracked decisions; that's a separate
  workstream.
- **Automated trading or order routing** — explicitly out of scope
  per the project's stated non-goals.
- **Replacement of the chat agent** — chat is the drill-down /
  explanation mode, it stays.
- **Public-facing API or webhook integration** — single-user
  Streamlit Cloud deploy, not a SaaS.

---

## Appendix A — Useful context files in the repo

For the designer to reference:

- [`README.md`](../../README.md) — overall project description
- [`MULTI_AGENT_ARCHITECTURE.md`](../../MULTI_AGENT_ARCHITECTURE.md)
  — generic layered model with this project as worked example
- [`src/inderes_agent/valuation/engine.py`](../../src/inderes_agent/valuation/engine.py)
  — the math implementation (don't need to read top-to-bottom, just
  understand the shape: pure Python, fully tested, scenario inputs
  → fair-value outputs)
- [`tests/valuation/test_excel_parity.py`](../../tests/valuation/test_excel_parity.py)
  — confirms the engine matches the Excel to within 0.02 €
- [`ui/components.py`](../../ui/components.py) — current UI
  components in Streamlit (Trading Desk theme), good reference for
  visual consistency
- [`ui/theme.css`](../../ui/theme.css) — design tokens
  (`--t-*` / `--ls-*` / `--r*` / `--s-*`), the colour palette and
  typography rules the new mode should respect for consistency
- [`docs/agentic_research_digest_2026-05-11.md`](../agentic_research_digest_2026-05-11.md)
  — the per-ticker markdown notebook + watchlist work-streams that
  partially overlap with this new mode
- The Excel files
  `/Users/juhorissanen/Downloads/Arvonmääritys2023.xlsx` and
  `/Users/juhorissanen/Downloads/Arvonmääritys2021.xlsx` — the
  canonical methodology source (the 2021 file has cleaner formulas,
  the 2023 file has the current visualisations)

---

*This brief is intentionally opinionated where I have an engineer's
view, and intentionally neutral where the designer should drive.
Update the brief in place as design decisions land — it should be a
living doc, not a one-shot.*
