# Data sources — depth analysis 2026-05-10

A practical audit of how deep the Inderes MCP actually goes (anchored
to a single well-covered company, **Sampo / `COMPANY:258`**, queried
2026-05-10), plus an assessment of two proposed external data sources:
**company websites** and **X / Twitter via Grok**. The goal is to
inform what feeds the Wk 5–6 *Analyst Walkthrough* feature (§12)
should plug into and which are worth building.

## TL;DR

- **The Inderes MCP is much deeper than we use today.** A single
  company surfaces ~57 PDF reports + ~10–100s of analyst comments +
  full transcripts + insider transactions + a 6,617-post forum
  thread + 7 years of fundamentals + forward estimates + calendar.
  Today's QUANT/RESEARCH/SENTIMENT subagents tap maybe 30 % of this
  surface — the §12 Walkthrough has a lot of room to grow without
  reaching outside.
- **Company-website crawl: don't build it.** Inderes already
  digests strategy, segments, business areas, ESG, and management
  changes in `COMPANY_REPORT` + `EXTENSIVE_COMPANY_REPORT` content
  (e.g. *"Introducing Sampo's business areas: Private UK"*). Crawling
  the company site competes with this — same data, dirtier source.
- **X / Twitter: yes, but narrowly.** Sentiment for **Nordic
  small-mid caps** outside Inderes' coverage is the only place where
  X reliably adds signal Inderes doesn't already have. For Sampo /
  Nokia / Nordea, the Inderes forum is a strictly better source
  (qualitative depth, analyst replies, lower noise). Build X as an
  optional fallback, not a default channel.

## Method

One company (Sampo, `COMPANY:258`) queried across all 16 MCP tools
on 2026-05-10. Sampo chosen because it's heavily covered (large-cap
Finnish, 6,617 forum posts, EN+FI+DK content), so it surfaces the
**upper bound of what's available**. A thinly-covered company would
likely show 5–10× less data per dimension.

## What Inderes MCP exposes (Sampo as the lens)

### Per-dimension depth

| Dimension | Tool | Sampo result | Rate of update | Coverage gap |
|---|---|---|---|---|
| **Company filings (raw)** | `list-company-documents` | **57 PDFs** total, going back many quarters in EN+FI | Live (Q1'26 indexed within hours) | None for covered cos |
| **Inderes analyst content** | `list-content` | 10 latest visible, hasNextPage. Mix of `ANALYST_COMMENT` + `COMPANY_REPORT` + `ARTICLE` | 2-day-old most recent | None |
| **Earnings transcripts** | `list-transcripts` | Only 3 (Q1'26, Q1'25, Q1'24) | Quarterly but sparse | Misses CMD / extra audiocasts |
| **Insider transactions** | `list-insider-transactions` | 10+ visible, hasNextPage. BUY + RECEPTION_OF_SHARE_PREMIUM + 18 other types | Real-time post-disclosure | None |
| **Calendar events** | `list-calendar-events` | 2 forward events (Q2/Q3 2026) | Forward only | Past events lost — use list-content |
| **Forward estimates** | `get-inderes-estimates` | 3-year forward, full table (revenue / ebitda / EPS / divid / P/E / P/B / ROE), recommendation, target, business + valuation risk | Updated on each new report (latest 2026-05-06) | None |
| **Historical fundamentals** | `get-fundamentals` | 2019–2025, all 26 fields available | Yearly + quarterly | Goes back to 2019 typically — older data sparse |
| **Forum sentiment** | `get-forum-posts` (Sammon ketju) | **6,617 total posts**, 7,281 numbered, includes analyst (Sauli_Vilen) replies to user questions | Real-time (latest 3 days old) | None |
| **Forum search** | `search-forum-topics` | Title-only search across all threads | n/a | Body-search not exposed |
| **Document section reading** | `get-document` → `read-document-sections` | Q1'26 PDF parsed into **85 sections** (TOC: tulos, segmentit, vakavaraisuus, riskit, henkilöstö, tilinpäätös, liitetiedot…) | Live | None |
| **Model portfolio** | `get-model-portfolio-content` / `get-model-portfolio-price` | Inderes' own portfolio holdings | Live | n/a |

### Where the depth is actually surprising

Three dimensions stood out beyond what I expected the MCP to expose:

**1. Section-level PDF parsing.** The Q1'26 Sampo PDF (Millistream
report, 926 kB) was parsed into **85 navigable sections** with a TOC.
The agent can selectively read just *"Tulevaisuudennäkymät"* +
*"Konsernijohtajan kommentti"* without touching the full 60-page
filing. This is the technical primitive that makes Walkthrough
feasible — a 6-dimension report doesn't need to retrieve the whole
PDF, it can target the 4–6 sections per dimension that matter.

**2. Forum content quality.** The Sammon thread isn't just retail
chatter — it has **analyst replies in-thread**. Example from
2026-05-06: a user spotted a linkage error in the report's dividend
growth column; analyst Sauli_Vilen replied within 50 minutes
explaining the model assumption + saying *"corrected report now
out!"*. That's a level of analyst-investor dialogue you don't get
from any X timeline. **The forum is signal, not noise**, for covered
companies.

**3. Insider transaction richness.** Not just "X bought Y shares" —
the API distinguishes 18 transaction types including
`RECEPTION_OF_SHARE_PREMIUM` (compensation, near-zero conviction
signal) vs `BUY` (real conviction, e.g. Antti Mäkinen 2026-02-12 @
€8.98). A SENTIMENT subagent that filters on `BUY` only would
produce dramatically cleaner signal than today's "any insider
transaction" approach.

### Where the MCP is genuinely thin

- **Transcripts** — Sampo only has 3 across 3 years. Other companies
  may have more if Inderes hosted the audiocast, but coverage is
  patchy. For investment-thesis work, this is where company-IR
  pages might fill gaps (most large caps publish their own
  earnings-call transcripts).
- **`search-forum-topics` is title-only.** Body search would be
  a major upgrade — *"who is talking about Sammon vakavaraisuus
  ratio"* can't be answered today without paginating thousands of
  posts. Listed under §4 BACKLOG-worthy gaps below.
- **No competitive comparison primitive.** You can `get-fundamentals`
  on multiple `companyIds` but there's no *"who are Sampo's listed
  peers"* tool. Today's COMPARISON queries rely on the LLM knowing
  Nordea / Tryg / Gjensidige are peers, which Flash Lite usually
  does but which is fragile.
- **No ESG / sustainability scoring.** Sampo's ESG narrative lives
  in `EXTENSIVE_COMPANY_REPORT` but isn't scorable. For Walkthrough's
  "Risk" + "Strategy" dimensions, this is the genuine data gap.

## How today's subagents use this surface

A point-in-time read of `src/inderes_agent/agents/prompts/*.md`:

| Subagent | Tools used today | Tools available but unused |
|---|---|---|
| **QUANT** | `get-fundamentals`, `get-inderes-estimates`, `search-companies` | `list-company-documents` (could pull historical Q-reports for trend storytelling) |
| **RESEARCH** | `read-document-sections`, `list-content`, `get-content` | `list-transcripts` + `get-transcript` (rarely invoked — major loss for thesis depth) |
| **SENTIMENT** | `search-forum-topics`, `get-forum-posts` | `list-insider-transactions` (used inconsistently — should be a default for sentiment) |
| **PORTFOLIO** | `get-model-portfolio-content` / `get-model-portfolio-price` | n/a |
| **VALUATION** | (no MCP — uses computed engine) | None — engine is deterministic by design |

**The biggest unused-surface gain:** `list-transcripts` +
`get-transcript`. RESEARCH should always pull the most recent
audiocast for an investment-thesis query. CFO / CEO direct quotes
are higher-fidelity than Inderes' synthesised version of them.

## Implications for upcoming features

### §12 Analyst Walkthrough — direct mapping

The 6 Walkthrough dimensions map cleanly onto MCP primitives:

| Dimension | Primary tools | Section-level reads |
|---|---|---|
| **LAATU** (Quality) | `get-fundamentals` (2019–2025 ROE / margins) + `read-document-sections` (latest annual report → "Konsernijohtajan kommentti") | 4–6 sections |
| **KASVU** (Growth) | `get-inderes-estimates` (3y forward) + `read-document-sections` ("Tulevaisuudennäkymät" + "Segmentit") | 6–8 sections |
| **ARVOSTUS** (Valuation) | The deterministic engine + `get-fundamentals` historical band | n/a — engine output |
| **STRATEGIA** (Strategy) | `list-content` filtered to `EXTENSIVE_COMPANY_REPORT` + `ARTICLE` (e.g. "Introducing Sampo's business areas") + `read-document-sections` ("Muut tapahtumat") | 4–6 sections |
| **RISKI** (Risk) | `read-document-sections` ("Riskit ja epävarmuustekijät" + "Velka-asema") + `list-insider-transactions` | 3–4 sections |
| **SENTIMENTTI** (Sentiment) | `get-forum-posts` (last 50–100 posts, filtered for analyst replies) + `list-insider-transactions` (BUY only) + `get-inderes-estimates` (recommendation history if `count > 1`) | n/a |

**Token budget estimate:** with selective section reads (~500 tokens
per section × 25 sections) + estimates + forum tail + insider filter,
a Walkthrough lands around **~30k input tokens / ~4k output tokens**
per company. That's 4–5× a normal Q&A but well within Pro-tier
budget, and the bulk is in the documents — exactly the place where
Pro is worth the spend.

### §1 Reflexion (Wk 2)

Reflexion will need **same-source comparison** to detect "weird"
output — e.g. if QUANT says ROE was 28% but `get-fundamentals` shows
26.4%, that's a contradiction the agent can detect against its own
input. The MCP exposes this — every subagent already has the
ground-truth tool, the loop just needs to compare its output
against the data it pulled.

### §10 Autonomous nightly eval

The 223-run dataset already on disk plus the Tier 0 indexer can
test new prompt variants against historical answers. **No new MCP
work needed for this** — it's purely a runtime + storage problem.

## Should we build company-website crawl?

**No.**

The user's intuition was sound — strategy / segment / management info
is publicly available on every IR site. But Inderes already digests
this:

- **Strategy** → `EXTENSIVE_COMPANY_REPORT` annual deep-dives
- **Segments** → recurring `ARTICLE`s like *"Introducing Sampo's
  business areas: Private UK"*, one per segment
- **Management** → `ARTICLE` *"Introducing Lars Kufall Beck, the
  new CFO at Sampo"* (April 2026)
- **ESG** → embedded in `EXTENSIVE_COMPANY_REPORT`

What we'd gain by crawling the IR site:
- Strategy decks not yet in Inderes' system (delay: hours to days)
- The original CFO bio video / multimedia
- Press-release fine print before Inderes publishes their take

What we'd lose:
- Engineering time (parsing 200+ different IR site templates)
- Trust — IR sites are corporate marketing, Inderes-digested versions
  are analyst-filtered for what's actually decision-relevant
- A canonical schema — every IR site has its own structure

**The right move** is to keep the agent inside the Inderes MCP for
the next 2–3 features and revisit *only if* an eval surfaces a
specific information gap that a website crawl would close. Right
now the gaps (transcripts coverage, ESG scoring) are MCP-side
upgrades, not crawl candidates.

## Should we add X / Twitter / Grok-style crawl?

**Yes, but narrowly.** Three lenses:

### Where X adds genuine signal beyond Inderes

| Use case | Why X wins | Why Inderes can't |
|---|---|---|
| Nordic small-cap sentiment outside Inderes coverage | Inderes covers ~150–200 companies; X has chatter on the next 500 | Inderes simply doesn't track them |
| Real-time reactions to global macro news (rate decisions, oil shocks) hitting Nordic stocks within minutes | X is fastest medium for cross-asset reaction | Forum delays by hours |
| Anglo-Saxon analyst takes on Finnish / Nordic exporters (UPM, Nokia, Wärtsilä) — different audience perspective | Different reader base = different framing | Inderes is Nordic-domestic-focused |
| Detecting "narrative violations" — when the consensus shifts before earnings | High-velocity sentiment signal | Forum is conviction-y, not velocity-y |

### Where X is strictly worse than the Inderes forum

- **For covered Nordic large-caps** (Sampo, Nordea, Kone, UPM,
  Wärtsilä) the forum has higher signal density. The 6,617-post
  Sampo thread has more substance per scroll than X's noisy
  cross-talk.
- **Quality of source.** Forum users have a community-enforced
  norm of citing reports + Inderes' own analysts replying
  in-thread. X has neither.
- **Language coverage.** Finnish stock-Twitter is small; Inderes
  forum is the *de facto* Finnish equity discussion venue.

### Practical implementation considerations

If we did build it:

- **Grok API** is the natural choice — direct X access, decent
  filtering, native sentiment hooks. Anthropic's Claude doesn't
  have first-party X integration.
- **Cost:** Grok-X queries are paid; need rate limits in `RunBudget`.
- **Trust:** X output should be flagged with a different persona
  colour and a **"social-media derived"** badge — never blended
  into Inderes-quality footnotes. Same lineage discipline as
  fabrication-guard logic.
- **Eval:** would need a separate eval set — currently we have
  no labelled X data for Nordic stocks. This is non-trivial; the
  forum eval substrate works because Inderes labels are implicit.

### Recommendation

**Don't build X integration as a Wk 1–6 feature.** The marginal
signal for Inderes-covered Nordic large-caps is small, and
small-cap coverage extension (the only place X clearly wins)
isn't on the roadmap. Revisit after Walkthrough ships and we
have evidence of the *specific* gap X would close.

If/when we do build it, the cleanest entry point is a new
**aino-x-sentiment** subagent (parallels existing SENTIMENT) with
its own persona colour, gated by a sidebar toggle, opt-in not
default.

## BACKLOG-worthy gaps this surfaced

These belong in the existing BACKLOG sections — flagged here so
they don't get lost:

- **§4 Tech debt:** `list-transcripts` should be a SENTIMENT default
  pull, not optional. RESEARCH likewise.
- **§4 Tech debt:** Insider-transaction filtering — SENTIMENT prompt
  should explicitly weight `BUY` >> `RECEPTION_OF_SHARE_PREMIUM`.
- **§1 AI capabilities:** Add a "competitor discovery" tool wrapper
  that uses fundamentals similarity (sector + market cap + region)
  to suggest peers, replacing today's LLM-knowledge-based matching.
- **§1 AI capabilities:** Body-text forum search — Inderes MCP
  exposes title search only; we could add a secondary indexer in
  Tier 2 Supabase that lets the agent search post bodies.
- **§12 Analyst Walkthrough:** prereq stack already captured. This
  doc adds: section-budget per dimension (~25 sections × 500
  tokens = 12k input from PDFs alone).

---

## Appendix A — Deep probe samples (Sampo, 2026-05-10)

Concrete sample outputs from the MCP, captured during the audit.
Included so future readers can verify the "depth" claims aren't
hand-wavy and can see exactly what the agent has access to.

### A.1 Section-level CEO commentary — `read-document-sections`

Reading section 4 of the Q1'26 PDF (`cmotmrwoy0003s6015in73dpy`,
section "Konsernijohtajan kommentti") returned **~6,500 characters
of substantive CEO prose**. Sample:

> *"Sampo säilytti vankan operatiivisen vireensä, ja kannattavuus
> oli vahva kaikissa segmenteissä, mikä siivitti underwriting-tuloksen
> 9 prosentin kasvuun kiintein valuuttakurssein. Samalla taseemme
> säilyi vahvana lisääntyneestä geopoliittisesta epävarmuudesta ja
> markkinaheilunnasta huolimatta…"*

The same call returned the "Tulevaisuudennäkymät" (forward-looking)
and "Riskit ja epävarmuustekijät" sections, including macro-aware
CEO commentary on **the Middle East war (Hormuzin salmen häiriöt),
ECB inflation undershoot, AI-driven valuation premia, hybridiuhat
(hybrid threats)**, and Sampo's specific insurance-side reasoning
about claims inflation.

This is verbatim CEO communication, not Inderes' synthesis of it —
exactly the primitive Walkthrough's "Strategy" + "Risk" dimensions
need. **One section-read call ≈ a Walkthrough dimension's input
budget.**

### A.2 BUY-only insider transactions

`list-insider-transactions` with `types: ["BUY"]` for Sampo returned
10 events, hasNextPage=true. The signal-quality jump from "all
transactions" is dramatic:

| Date | Insider | Position | Volume | Price | Notable |
|---|---|---|---|---|---|
| 2026-02-12 | Antti Mäkinen | Board member | 11,140 | €8.98 | Recent — modest size |
| 2025-06-23 | Sara Mella | Board member | 5,500 | €9.14 | Recent |
| 2025-02-07 | Morten Thorsrud | (became CEO) | 5,050+2,450+2,450+5,050 | €41.08–41.13 | **CEO buying his own stock pre-promotion** |
| 2022-11-04 | **Björn Wahlroos** | Board member | **600,000** | €46.00 | **€27.6M conviction trade** |
| 2022-01-05 | Björn Wahlroos | Board member | 100,000+100,000 | €45.29 | Wahlroos accumulating |

Wahlroos is a legendary Finnish capital-markets figure; a 600,000-
share buy is a textbook conviction signal. **Today's SENTIMENT
subagent doesn't differentiate this from a routine RECEPTION_OF_
SHARE_PREMIUM** (which is just compensation, near-zero conviction).
Filtering on `types=["BUY"]` is a one-line change with order-of-
magnitude effect on signal quality.

**Stock-split status — verified, NO bug:** earlier draft of this
document flagged the Sampo 1:5 split (2024) as a likely cause of a
Plotly P/E "cliff". Re-verified 2026-05-10 by querying
`get-fundamentals` directly: prices are €7–10 across 2020–2026 and
sharesTotal is 2.5–2.8 B for the entire window — i.e. the data is
**already split-adjusted server-side**. Raw 2020 price would be
~€35 with ~550 M shares; we see neither. So there is **nothing for
the chart code to normalise**, and any "cliff" reported earlier was
a misread of historical data plus the post-split market reaction
(€46 → €9 reflects both the split AND the 2023–24 sell-off, which
is real). No backlog item needed.

### A.3 EXTENSIVE_COMPANY_REPORT availability

`list-content` filtered to `EXTENSIVE_COMPANY_REPORT` returned
**only 1 result** for Sampo: *"Sampo: The King of the Nordic P&C
insurance market"*, dated 2023-06-14 — almost 3 years old.

This **changes the Walkthrough architecture assumption**. The
"deep-dive" reports are rare (every 1–3 years per company), not
quarterly. So Walkthrough Phase 2's document-reader can't always
pull the latest EXTENSIVE_COMPANY_REPORT — it has to fall back
to:

1. Most recent quarterly Q-report sections (always available)
2. Recent ANALYST_COMMENT entries (latest take)
3. Older EXTENSIVE_COMPANY_REPORT for structural / strategic
   framing — flag age in footnote

The deep-dive doesn't *replace* the quarterly read; it *augments*
it. Walkthrough should always pull both.

### A.4 Quarterly fundamentals — gaps

`get-fundamentals` with `resolution: "quarterly"` for 2024–2025
returned 8 quarters with `revenue / ebitda / epsReported` filled
but **`roe: null` for every quarter**. ROE is annual-only.

Implications:
- Quarterly ROE charts will silently empty out — chart code needs
  to skip / annotate
- Walkthrough's "LAATU" dimension that wants ROE trend has to
  use yearly resolution, fine for Sampo (2019–2025 = 7 datapoints)
- A subagent that computes "ROE this quarter" from net income
  and book value would close the gap, but that's a deterministic
  engine extension (like the existing valuation engine), not a
  prompt change

### A.5 Forum coverage is uneven

`search-companies("Tryg")` returned `COMPANY:175` (Tryg is one of
Sampo's main Nordic insurance peers, listed in Denmark). Crucially:
**`threadUrl: null`** — no Inderes forum thread for Tryg.

Sampo has 6,617 forum posts; Tryg has 0. **Forum coverage
correlates with Finnish-domestic interest, not company importance**.
Walkthrough's SENTIMENT dimension must degrade gracefully when
there's no forum to pull from — falling back to insider data +
analyst comments only.

### A.6 Section TOC depth — Q1'26 example

`get-document` on the Q1'26 PDF returned a **TOC of 85 sections**.
Categories visible:

| Section range | Topic family | Walkthrough relevance |
|---|---|---|
| 1–8 | Konsernin avainluvut + CEO + tulevaisuus + riskit | **Strategy + Risk + Quality** dimensions |
| 9–24 | Segmentit (Pohjoismaat, UK, yritys, suurasiakkaat) | **Strategy** (segment mix), **Growth** (where) |
| 25–31 | Vakavaraisuus, velka, luottoluokitus, Solvency II model | **Risk** (capital position) |
| 32–36 | Osakkeenomistajat, palkitseminen, henkilöstö | **Strategy** (governance) |
| 37–43 | Raportointikauden jälkeiset tapahtumat | **Risk** (recent events) |
| 44–61 | Tunnusluvut + laskentakaavat + osakekohtaiset | **Quality** (metrics definitions) |
| 62–85 | Konsernitilinpäätös + liitetiedot | **Quality** (auditor-grade detail) |

This means Walkthrough can implement targeted reads:
- LAATU dimension → sections [3, 9, 50, 51, 52]
- KASVU → [11, 13, 16, 19, 22]
- ARVOSTUS → engine output (no PDF read needed)
- STRATEGIA → [4, 5, 11–23, 30, 31]
- RISKI → [8, 25, 26, 27, 38]
- SENTIMENTTI → engine + forum (no PDF needed)

Total sections per Walkthrough ≈ 22, at ~500 tokens each = 11k
input from PDFs alone. Plus estimates + forum tail + insider
filter. The §12 token-budget estimate (~30k input total) holds.

---

## Appendix B — Concrete features the depth enables

A non-exhaustive list of features that become possible once the
agent uses the full MCP surface, ordered by feasibility (lowest
to highest engineering cost):

1. **Smart insider description in SENTIMENT** *(1 h)*
   - **Revised 2026-05-10 (afternoon):** earlier draft of this
     section recommended a `types=["BUY"]` filter as the default.
     That's wrong — sells are signal too (Wahlroos has trimmed
     huge blocks before; cluster-sells precede guidance cuts; etc).
     The actual problem is that today's SENTIMENT subagent doesn't
     differentiate compulsory stock-grant flows (e.g.
     `RECEPTION_OF_SHARE_PREMIUM`) from voluntary trades. Fix is
     a prompt-quality change inside the SENTIMENT subagent, not a
     filter at the tool boundary: describe each transaction with
     `transactionType`, size relative to compensation, and net
     direction over the window. No data is hidden; meaning is added.

2. ~~**Stock-split-adjusted price series**~~ *(removed)*
   - **Verified 2026-05-10 (afternoon): Inderes MCP returns
     split-adjusted data server-side.** No client-side
     normalisation needed. See §A.2 for verification.

3. **Always-pull-transcript on investment-thesis queries** *(1 h)*
   - RESEARCH prompt change: when query is investment-thesis-y,
     always invoke `list-transcripts` + `get-transcript` for the
     most recent audiocast.

4. **Macro-context awareness** *(0.5 d)*
   - The Q1'26 CEO commentary mentions Middle East, ECB, AI
     valuations. RESEARCH could surface these as a "macro
     context" sub-section without separate tools.

5. **Peer discovery via fundamentals similarity** *(1 d)*
   - Wrap `get-fundamentals` over multiple companies, compute
     sector-region-marketcap distance, return top-3 peers. Closes
     the "router doesn't know peers" fragility.

6. **Body-text forum search via Supabase mirror** *(2 d, depends
   on Tier 2)*
   - Indexer mirrors forum posts to Supabase. Agent calls custom
     SQL search. Closes the title-only limitation.

7. **Walkthrough Phase 1 — section-level read pipeline** *(2 d)*
   - 6 dimensions × ~4 sections each, parallel reads, structured
     output. The MCP primitive is ready; this is just orchestration.

8. **Walkthrough Phase 2 — multi-document synthesis** *(3 d)*
   - Phase 1 output + 2–3 latest analyst comments + 1
     EXTENSIVE_COMPANY_REPORT (with age caveat) → composite
     6-dimension report.

9. **Insider-conviction scoring** *(1 d)*
   - Weight by volume × position × price-vs-current. Wahlroos
     buying 600k @ €46 in 2022 (now €9 post-split → ~€2.30M
     loss) is high-conviction but wrong-timing — surface this
     nuance.

10. **Live calendar-event nudges** *(1 d)*
    - On query about a company near an upcoming earnings date,
      LEAD prepends a nudge: *"⏰ Q2 raportti 2026-08-12 — vain
      94 päivää, ennakko todennäk. heinäkuussa"*. Uses
      `list-calendar-events`.

These 10 are all technically unblocked by the MCP today. The
question for prioritisation is which 2–3 land in Wk 2–3 alongside
Reflexion + confidence + Tier 2.

---

*Anchored on Sampo (`COMPANY:258`), 2026-05-10. Sampo is upper-bound;
thinly-covered companies will show 5–10× less data per dimension.
Numbers are point-in-time and grow as Inderes ingests new content.*
