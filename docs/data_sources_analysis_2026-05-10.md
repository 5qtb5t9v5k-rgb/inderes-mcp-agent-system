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

*Anchored on Sampo (`COMPANY:258`), 2026-05-10. Sampo is upper-bound;
thinly-covered companies will show 5–10× less data per dimension.
Numbers are point-in-time and grow as Inderes ingests new content.*
