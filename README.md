# inderes-mcp-agent-system

> **⚠️ Personal research project.** Independent learning experiment — **not affiliated with, endorsed by, or developed in collaboration with Inderes Oyj.** Uses the publicly available Inderes MCP server through the user's own Inderes Premium subscription. All Inderes analyst content (recommendations, target prices, written research) surfaced by this system is © Inderes Oyj.

A multi-agent stock-research conversation system for Nordic + international
equities. Built on **Microsoft Agent Framework 1.0+** (Python 3.11+), powered
by **Google Gemini** with structured error classification and primary→fallback
model selection. Data plane is a **dual-MCP architecture**:

- **Inderes MCP** at `https://mcp.inderes.com` — analyst content, target
  prices, transcripts, forum sentiment, model portfolio (Finnish-equity
  primary source).
- **Yahoo Finance MCP** (own MIT-public sidecar:
  [`yahoo-finance-mcp`](https://github.com/5qtb5t9v5k-rgb/yahoo-finance-mcp))
  — live price, Q-fresh BVPS, OHLCV history, news, institutional holders.
  Toggle on/off via `YAHOO_MCP_URL` env var; agents are wired with
  per-domain partitions mirroring the Inderes pattern.

Together: Inderes covers Helsinki names with depth, Yahoo covers
international + freshness gaps Inderes can't fill (BVPS lag, live price,
US/EU/Asian tickers).

```bash
$ python -m inderes_agent "Mitä Sammon nykytilanteesta tulisi ajatella?"
```

A lead orchestrator classifies the question, fans out to 1–5 specialized subagents
(quant, research, sentiment, portfolio, valuation) running in parallel, each making
targeted calls into Inderes MCP and returning structured findings. The lead then
synthesizes a single answer in the same language as the question. Every run is
persisted to disk as a forensic record (routing decision, per-subagent outputs,
full tool-call timeline).

The system **surfaces signals** — Inderes' own recommendation, target price, insider
activity, analyst notes, forum sentiment — and optionally an **alternative valuation**
(deterministic Greenwald-Gordon hybrid run on the user's own methodology, opt-in via
sidebar toggle). It **never** issues a buy/sell call of its own. The user makes the
decision; the agent shows them the data.

> **About this project.** A *learning project*, not a product. The goal is
> to develop in practice a working understanding of how multi-agent systems
> are actually built — iteratively, from a single-agent foundation toward
> production-tested multi-agent systems. The deliverable is the body of
> transferable patterns documented along the way, not just this specific
> tool. See [`PURPOSE.md`](PURPOSE.md) for the full statement of intent.

> **Documentation map**
> - [`PURPOSE.md`](PURPOSE.md) — *why* the project exists; trajectory, what's transferable, what's deliberately excluded
> - [`ARCHITECTURE.md`](ARCHITECTURE.md) — design, components, lifecycle, key decisions for *this* implementation
> - [`MULTI_AGENT_ARCHITECTURE.md`](MULTI_AGENT_ARCHITECTURE.md) — generic layered model (Surface / Brain / Action / Data / Harness + Evals & Governance planes) for thinking about any multi-agent system, with this project as a worked example
> - [`LESSONS.md`](LESSONS.md) — reflections on building this; what AI / UI / infra each contribute, what time really went to, what I'd do differently
> - [`AI_BRIEFING_PROMPT.md`](AI_BRIEFING_PROMPT.md) — copy-pasteable prompt for AI coding assistants to read this repo in a structured way and produce a briefing for someone applying its patterns to a multi-agent project of their own
> - [`AGENT_FRAMEWORK.md`](AGENT_FRAMEWORK.md) — Microsoft Agent Framework primer + which features we use
> - [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — every error encountered, with fix
> - [`CHANGELOG.md`](CHANGELOG.md) — version history and design rationale
> - [`BACKLOG.md`](BACKLOG.md) — feature ideas not yet built, ordered by interest
> - [`CONTRIBUTING.md`](CONTRIBUTING.md) — developer setup, testing, extending
> - [`BUILD_SPEC.md`](BUILD_SPEC.md) — original build specification (historical)
> - [`docs/agentic_patterns_mapping_2026-05-11.md`](docs/agentic_patterns_mapping_2026-05-11.md) — this project mapped against [nibzard's `awesome-agentic-patterns`](https://github.com/nibzard/awesome-agentic-patterns) catalogue (~178 patterns)
> - [`docs/agentic_research_digest_2026-05-11.md`](docs/agentic_research_digest_2026-05-11.md) — critical reading of an external 12-month roadmap synthesis; 5 concrete BACKLOG pulls + 4 verify-first items + 6 context-specific skips
> - [`docs/research_prompts/`](docs/research_prompts/) — self-contained research prompts for spinning off Deep Research sessions
> - **Sidecar repos**: [`yahoo-finance-mcp`](https://github.com/5qtb5t9v5k-rgb/yahoo-finance-mcp) (MIT-public, 5 tools + tests + CI), [`inderes-mcp-auto-relogin`](https://github.com/5qtb5t9v5k-rgb/inderes-mcp-auto-relogin) (private, Playwright headless re-auth cron)

---

## Table of contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Per-run logs](#per-run-logs)
- [Architecture at a glance](#architecture-at-a-glance)
- [Configuration](#configuration)
- [Cost and quotas](#cost-and-quotas)
- [Limitations and non-goals](#limitations-and-non-goals)
- [Reflections](#reflections)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Pre-flight checklist](#pre-flight-checklist)

---

## What it does

A natural-language interface to the Inderes Premium dataset. Ask about a Nordic
stock in Finnish or English; get a structured, source-cited answer:

**Example query:**
```
Mikä on Sammon P/E ja Inderesin näkemys?
```

**Example output (abbreviated):**
```
Sammon P/E-luku vuoden 2025 päätteeksi oli 12,53. Inderesin ennusteiden
perusteella arvostuskertoimien odotetaan asettuvan vuosina 2026–2028 noin
14,5–17,9 välille. Yhtiö on hinnoiteltu linjassa pohjoismaisiin verrokkeihin.

Inderesin näkemys: LISÄÄ (INCREASE), tavoitehinta 10,00 €

• Arvostus: tuotto-odotus nojaa tuloskasvuun ja ~4 %:n osinkotuottoon
• Operatiivinen suoritus: vakuutusliiketoiminta vahva
• Ennusteet: oikaistu P/E 17,9 (2026e), 15,8 (2027e), 14,5 (2028e)

Sources: search-companies, get-fundamentals, get-inderes-estimates,
         list-content, get-content
```

The same query also produces a complete trace at `~/.inderes_agent/runs/<ts>/`
including a human-readable `narrative.md` with the routing decision, per-tool-call
timeline, each subagent's full output, and the lead's synthesis.

Typical query latency: 8–25 seconds depending on complexity (single-domain → fast,
multi-domain comparison → slower due to per-company fan-out).

---

## Quick start

### Prerequisites

| Requirement | Details |
|---|---|
| **Python 3.11+** | We use 3.13 in development. ARM-native interpreter required on Apple Silicon (see [TROUBLESHOOTING](TROUBLESHOOTING.md#imports-take-30-60-seconds-on-apple-silicon)). |
| **`uv`** | Fast Python package manager. Install: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Disk space** | At least 20 GB free — APFS becomes unstable above ~90 % capacity. |
| **Inderes Premium** | Required for MCP server access. Subscribe at [inderes.fi/premium](https://www.inderes.fi/premium). |
| **Gemini API key** | Free at [aistudio.google.com](https://aistudio.google.com). Paid tier strongly recommended for sustained use. |

### Install

```bash
git clone https://github.com/5qtb5t9v5k-rgb/inderes-mcp-agent-system
cd inderes-mcp-agent-system

uv python install 3.13
uv venv --python-preference only-managed --python 3.13
source .venv/bin/activate
uv pip install --pre -e .
```

The `--pre` flag is mandatory: `agent-framework-gemini` is currently published as
an alpha pre-release on PyPI. The `--python-preference only-managed` flag ensures
`uv` uses its own bundled Python builds, which are always native to your CPU
architecture (avoids the Intel-on-Apple-Silicon performance pitfall).

### Configure

```bash
cp .env.example .env
# edit .env, set GEMINI_API_KEY=AIza...
```

Get the key from [Google AI Studio](https://aistudio.google.com/app/apikey). The
default model configuration (free-tier-realistic Gemini Flash Lite + Flash) works
on the free tier with caveats — see [Cost and quotas](#cost-and-quotas).

### First run

```bash
python -m inderes_agent "What's Konecranes' current P/E?"
```

The first run opens a browser to log in to Inderes (OAuth 2.0 + PKCE against
Keycloak). After login, your access tokens are cached at
`~/.inderes_agent/tokens.json` and refreshed silently on subsequent runs.

Cold start (imports + OAuth + first MCP call) takes about 10–20 s. Once everything
is warm, simple queries return in 8–10 s, multi-domain queries 15–25 s.

---

## Usage

### One-shot

```bash
python -m inderes_agent "Compare Sampo and Nordea on profitability"
```

### Interactive REPL

```bash
python -m inderes_agent
> Anna pikakatsaus Konecranesista.
> Entä insider-aktiivisuus?
> /explain
> /exit
```

The REPL keeps conversation context — follow-up questions like "and the dividend
yield?" inherit the company from the previous turn.

### Browser UI (Streamlit)

```bash
uv pip install --pre -e '.[ui]'
streamlit run ui/app.py
```

Opens `http://localhost:8501` with a chat interface, live phase indicators
(routing → subagents → synthesis), an Inderes recommendation badge above the
synthesis when a single company is in scope, follow-up suggestion chips, and
clickable inderes.fi source links. Same agent code as the CLI underneath. See
[`ui/README.md`](ui/README.md) and [`ui/DEPLOY.md`](ui/DEPLOY.md) for
Streamlit Cloud deployment notes (public app + password gate + daily query
cap). For long-running cloud deployments,
[`.github/workflows/refresh-inderes-tokens.yml`](.github/workflows/refresh-inderes-tokens.yml)
runs every 15 min to keep the Inderes OAuth refresh-token chain alive via a
private gist mirror — without it, an idle Streamlit Cloud container will
eventually 401 on the next user query.

### REPL slash commands

| Command | Action |
|---|---|
| `/help` | List commands |
| `/clear` | Reset conversation history |
| `/agents` | Show subagents invoked this session |
| `/trace` | Show last query's subagent outputs and which Gemini model handled each |
| `/explain` | Print a human-readable narrative of the last run |
| `/last` | Print the directory of the last run's full log |
| `/runs` | List the 10 most recent run directories |
| `/exit` | Quit |

### Programmatic use

```python
import asyncio
from inderes_agent.cli.repl import ConversationState, handle_query

async def main():
    state = ConversationState()
    await handle_query("Mikä on Konecranesin P/E?", state)

asyncio.run(main())
```

See [`examples/`](examples/) for a single-question script and a multi-turn
conversation example.

---

## Per-run logs

Every query writes a complete forensic record to `~/.inderes_agent/runs/<timestamp>/`:

```
20260501-205122-776/
├── query.txt              # the user's question
├── routing.json           # which subagents the router picked, plus reasoning
├── subagent-01-quant.json
├── subagent-02-research.json
├── subagent-03-sentiment.json
├── synthesis.txt          # lead's final synthesized answer
├── meta.json              # duration, fallback events, error counts
├── console.log            # raw HTTP/MCP/fallback log lines with timestamps
└── narrative.md           # human-readable timeline (auto-generated)
```

`narrative.md` is the single best file to inspect afterward. It includes:

1. **Routing decision** with the router's reasoning
2. **Tool-call timeline** with offsets and per-call duration, attributed by agent
3. **Each subagent's full output** (the structured response it returned to the lead)
4. **Lead's synthesis** (what the user saw)
5. **Statistics footer** — agents · tool calls · errors · 503 retries · fallbacks · total duration

You can regenerate the narrative for any past run via:

```bash
python scripts/explain.py                       # latest run
python scripts/explain.py 20260501-205122-776   # specific run
```

In the REPL: `/explain` does the same for the current session's last run.

---

## Architecture at a glance

```
                      User question
                            │
                            ▼
                    ┌─────────────┐
                    │  Router LLM │  Gemini, structured-output JSON
                    └─────┬───────┘
                          │
            ┌─────────────┴────────┐
            ▼                      ▼
       Lead-planner       Per-domain plan-snippets injected
       (opt-in toggle)    into each subagent's prompt
            │
            ▼
                ┌─────────┬─────────┬──────────┬──────────┬──────────┐
                ▼         ▼         ▼          ▼          ▼          ▼
           aino-quant  aino-research  aino-sentiment  aino-portfolio  aino-valuation
                │         │         │          │          │          │
                └────┬────┴────┬────┴────┬─────┴────┬─────┴────┬─────┘
                     │         │         │          │          │
                     ▼         ▼         ▼          ▼          ▼
         Inderes MCP        ──────────  ──────────  ─────────  ─────────
         (16 tools,       ←──── per-agent partitioning ──── (server-side
         OAuth)             enforced via allowed_tools         tool guard)
                                       │
                                       ▼
         Yahoo MCP        ←──── enabled when YAHOO_MCP_URL set ────
         (6 tools, opt-in)      partitioned identically to Inderes
                          │
                          ▼     bounded by MAX_CONCURRENT_AGENTS
                          │     ┌─ valuation/ ──── deterministic engine
                          │     │  (pure Python, Greenwald-Gordon
                          │     │   formulas, no LLM dependency)
                          │     └─ runs after agent emits JSON
                          ▼
                ┌──────────────────────┐
                │ Conflict detector    │  flags disagreements between
                │ (Gemini, JSON output)│  subagents before synthesis
                └─────────┬────────────┘
                          ▼
                ┌──────────────────────┐
                │ Fabrication guard    │  rejects subagent outputs that
                │ (orchestration tier) │  emitted text with ZERO MCP calls
                └─────────┬────────────┘
                          ▼
                    ┌─────────────┐
                    │  aino-lead  │  reads (verified) subagent outputs +
                    └─────┬───────┘  conflict report, synthesizes
                          ▼
                     Final answer + [Q1]/[R1]/[S1]/[P1]/[V1] sources
```

### Subagent → MCP tool mapping

Each subagent sees only its allowed subset of tools (enforced via
`MCPStreamableHTTPTool(allowed_tools=...)`). When `YAHOO_MCP_URL` is set,
agents additionally receive their domain-specific Yahoo tool subset.

| Agent | Role | Inderes tools | Yahoo tools *(if enabled)* |
|---|---|---|---|
| `aino-quant` | Numerical analysis: P/E, ROE, target prices, recommendations | `search-companies`, `get-fundamentals`, `get-inderes-estimates` | `search_ticker`, `get_snapshot`, `get_history` |
| `aino-research` | Analyst content, transcripts, filings, news narrative | `search-companies`, `list-content`, `get-content`, `list-transcripts`, `get-transcript`, `list-company-documents`, `get-document`, `read-document-sections` | `search_ticker`, `get_news` |
| `aino-sentiment` | Insider trades, forum sentiment, institutional ownership, calendar | `search-companies`, `list-insider-transactions`, `search-forum-topics`, `get-forum-posts`, `list-calendar-events` | `search_ticker`, `get_news`, `get_holders` |
| `aino-portfolio` | Inderes' own model portfolio | `get-model-portfolio-content`, `get-model-portfolio-price`, `search-companies` | `search_ticker`, `get_snapshot`, `get_history` |
| `aino-valuation` *(opt-in)* | Alternative valuation: BVPS, ROE history, current price → Greenwald-Gordon engine | `search-companies`, `get-fundamentals`, `get-inderes-estimates` | `search_ticker`, `get_snapshot` |
| `aino-lead` | Synthesizes subagent outputs (no tools) | — | — |

**Per-domain rationale**: `get_holders` is the Yahoo parallel of Inderes
`list-insider-transactions` (SENTIMENT-only). `get_snapshot` parallels
`get-fundamentals` (QUANT + VALUATION shared). `get_history` has *no*
Inderes equivalent — Inderes MCP doesn't expose price-history time series,
so this is a pure new capability for QUANT/PORTFOLIO charting on both
Finnish AND international tickers.

The **valuation subagent** is opt-in — it runs only when the sidebar toggle *"Käytä
vaihtoehtoista arvonmääritystä"* is enabled AND the query has clear valuation intent
(checked via a keyword heuristic so that purely qualitative questions like *"explain
why X is profitable"* don't trigger an unwanted Greenwald-Gordon table). The deterministic
engine in `inderes_agent/valuation/` consumes the agent's structured JSON output and
computes fair value, EPV, growth value, quality classification, and dual implied
metrics — the agent itself never does math. A tool-call guard at the orchestration
boundary rejects any valuation output that didn't actually fetch data from MCP, closing
the hallucination path where an LLM might invent numbers from conversation context.

For a full architectural walkthrough including the OAuth flow, the schema-sanitization
shim, the Gemini fallback wrapper, the valuation engine, and per-tool-call observability,
see [`ARCHITECTURE.md`](ARCHITECTURE.md).

### Trust + reliability layers (post-2026-05-10)

The system has two independent layers protecting against fabricated
output and a third measuring real-world quality:

1. **HARD GATE in agent prompts** — every subagent (`quant`, `research`,
   `sentiment`, `portfolio`, `valuation`) starts with an explicit
   block requiring MCP tool calls before any output. *"Numbers from
   training memory are FORBIDDEN. A response with ZERO MCP tool
   calls is automatically rejected as fabrication."*
2. **Fabrication guard at orchestration boundary**
   (`workflows.py:_detect_fabrication`) — runtime safety net. If a
   subagent emits ≥300 char domain-loaded text but ZERO MCP calls,
   the result is replaced with `error="fabricated_no_tool_calls"`
   so LEAD synthesises on top of an honest failure rather than a
   plausible-looking invention. When ALL subagents fail this way,
   `synthesize()` short-circuits to a fixed *"En löytänyt yhtiötä
   X Inderes-tietokannasta"* answer — no euros, no recommendations,
   no fabricated context.
3. **Eval foundation** (`evals/`) — Tier 0 SQLite indexer over
   `~/.inderes_agent/runs/` enables fast diagnostic SQL across all
   historical runs; Tier 1 `golden.yaml` + Gemini-Pro judge grades
   captured runs against deterministic + qualitative rubrics. 7
   golden cases lock concrete weakness categories. Score deltas
   between runs make regressions impossible to ship silently.

The combination implements OWASP Agentic Top 10 #T3 (tool misuse /
hallucinated outputs) defense at three layers: prompt-side, runtime,
and post-hoc measurement. See `docs/sprint_lessons_2026-05-09.md`
for the empirical patterns that drove these.

---

## Configuration

All configuration lives in `.env`:

```ini
# Required
GEMINI_API_KEY=               # https://aistudio.google.com/app/apikey

# Inderes MCP — change only if Inderes provides a new endpoint
INDERES_MCP_URL=https://mcp.inderes.com
INDERES_MCP_CLIENT_ID=inderes-mcp

# Models (free-tier-safe defaults)
PRIMARY_MODEL=gemini-3.1-flash-lite-preview
FALLBACK_MODEL=gemini-2.5-flash

# Fallback timing (see ARCHITECTURE.md "Gemini client with fallback")
RETRY_DELAY_MS=1000
MAX_RETRIES=1

# Concurrency cap (protects against quota burn)
MAX_CONCURRENT_AGENTS=2

# Logging
LOG_LEVEL=INFO
LOG_JSON=false
```

`.env` is gitignored. `.env.example` contains the same template with no key set.

---

## Cost and quotas

The system is designed to work on Google's free Gemini tier, but free-tier limits are
tight enough that sustained use requires the paid tier.

### Free tier daily limits (per Google AI Studio)

| Model | Requests/day |
|---|---|
| `gemini-3.1-flash-lite-preview` (primary) | 500 |
| `gemini-2.5-flash` (fallback) | 20 |

A single multi-domain query uses 6–15 LLM calls (router + N subagents with their
internal tool-call loops + lead synthesis). Realistic free-tier capacity is roughly
30–50 queries/day before hitting limits.

### Paid tier (recommended)

Enable billing at [Google AI Studio billing](https://aistudio.google.com/app/apikey).
Per-query cost is approximately:

- **Single-domain** (e.g. quant only): ~$0.005
- **Multi-domain** (3 subagents): ~$0.015–0.02
- **Comparison fan-out**: ~$0.03–0.05

A $10 budget covers 500–2000 queries depending on complexity. Paid tier also
substantially reduces 503 capacity errors. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#503-errors-from-gemini)
for details.

### Fallback policy

The system survives transient capacity issues automatically:

1. First attempt → primary model
2. On `503 UNAVAILABLE` → wait `RETRY_DELAY_MS`, retry once on primary
3. On second 503 OR any `429 RESOURCE_EXHAUSTED` → switch to fallback model
4. Fallback gets two attempts with 2 s and 4 s backoff
5. Both exhausted → `QuotaExhaustedError` with a clear message to the user

The model that handled each request is recorded for `/trace` and `narrative.md`.

---

## Limitations and non-goals

This system explicitly does **not**:

- Recommend "buy" or "sell" as its own opinion. It surfaces Inderes' recommendation
  on a separate, clearly attributed line. The user decides.
- Replace investment advice. It is a research surface, not an advisor.
- Predict prices. It quotes Inderes' estimates and analyst views without forecasting.
- Use Pro-tier Gemini models on the free tier (zero quota allocation).
- Hardcode company IDs — every workflow starts with `search-companies(name)` to
  resolve the Inderes-internal ID.

It is also **not** a peer-to-peer agent network. Subagents do not communicate with
each other; the lead reads each one's output as text in its prompt. See
[ARCHITECTURE.md → "What this is and isn't"](ARCHITECTURE.md#what-this-is-and-isnt)
for honest framing.

---

## Reflections

This started as "build a multi-agent stock-research demo" and turned into a
roughly even three-way split between the agents themselves, the UI that makes
them legible, and the infrastructure that keeps them alive in production.
Some of what I learned in the process:

- Per-agent tool partitioning beats monolithic agents at the same scale.
- Prompts are code, and they deserve to be reviewed like code.
- Multi-agent UI isn't decoration — it's epistemic infrastructure. Without
  thought traces, persona styling, and source links, users can't tell whether
  an answer is grounded.
- About half the code in this repo isn't AI at all. It's OAuth, schema
  sanitization, fallback chains, observability, deploy plumbing. That's not
  unique to this project; it seems to be the shape of agentic systems in
  general.
- "Free tier" of any LLM provider has hidden cliffs (capacity 503s, quota,
  Pro-tier zero allocation). Plan for them up front rather than getting
  surprised.

For a longer reflective write-up — the AI / UI / infra breakdown, lessons
per pillar, cross-cutting themes, things I'd do differently next time, and
the open questions I haven't resolved — see [`LESSONS.md`](LESSONS.md).
For a generic primer on multi-agent system architecture (the layered model
this project ended up illustrating), see
[`MULTI_AGENT_ARCHITECTURE.md`](MULTI_AGENT_ARCHITECTURE.md).

---

## Testing

```bash
uv pip install -e '.[dev]'
pytest -q
```

**375 tests** across the agent, MCP, valuation, observability, and UI
layers — all mocked, zero live LLM calls, CI-gated on every push. Top
categories by test count:

- **Valuation engine** (`tests/valuation/test_engine.py`): 49 tests on
  Greenwald-Gordon math (FV, EPV, growth value, dual implied), edge
  cases, quality classification with ±2% buffer.
- **Router** (`test_router.py`): 43 tests on JSON parsing variants,
  `QueryClassification` validation, valuation-intent gate (33
  parametrized cases incl. Finnish morphology).
- **Valuation parser** (`test_parser.py`): 39 tests on agent JSON →
  engine input validation, multi-company array handling, Levenshtein-≤2
  typo tolerance, sibling-protection between `*_rationale` fields.
- **QUANT charts** (`test_charts.py`): 33 tests on Plotly extraction,
  outlier filtering, provenance captions, multi-company colour
  assignment.
- **ROE selection rule** (`test_roe_selection.py`): 23 tests on the
  deterministic sustainable-ROE rule (medians, trend, agent-choice
  validation).
- **Excel parity** (`test_excel_parity.py`): 20 tests on 10 Finnish
  companies reproducing the user's `Arvonmääritys2023.xlsx` Data-sheet
  outputs to within 0.02€ tolerance.
- **Gemini fallback client** (`test_fallback.py`): 17 tests covering
  structured error classification (per-day quota vs per-minute rate
  limit vs transient 5xx vs non-retryable), retry-with-backoff,
  diagnostic logging.
- **Footnote markers** (`test_footnote_markers.py`): 17 tests on
  `[Q1]/[R1]/[S1]/[P1]/[V1]` source-tag emission.
- **Valuation tool-call guard** (`test_valuation_tool_guard.py`): 17
  tests rejecting zero-MCP-call valuation outputs.
- **OAuth runtime** (`test_oauth_runtime.py`): 16 tests on token
  refresh, gist sync, `_load_tokens` ordering.
- **Output parts** (`test_output_parts.py`): 16 tests on MAF response-
  part parsing for the Streamlit trace renderer.
- **Fabrication guard** (`test_fabrication_guard.py`): 14 tests on the
  orchestration-tier rejection of zero-tool-call subagent outputs.
- **OAuth bootstrap** (`test_oauth_bootstrap.py`): 12 tests on cold-
  start ordering, refresh-token rotation, env-bridge fallback.
- **Feedback** (`test_feedback.py`): 12 tests on 👍/👎 round-trip.
- **Yahoo MCP wiring** (`test_yahoo_mcp_wiring.py`): 11 tests on
  per-agent partitioning, `YAHOO_MCP_URL` toggle semantics, build-
  time regression checks.
- **Hard limits** (`test_limits.py`): 11 tests on OWASP T1 hard
  limits (max_iter / max_tool_calls / max_cost / max_duration).
- **Evals YAML** (`test_evals_yaml.py`): 9 tests on `golden.yaml`
  structural validation as a CI gate.
- **Other** (`test_paattely_parser`, `test_tila_c_banner`,
  `test_app_imports`, `test_workflows`): smaller suites covering
  reasoning extraction, valuation-mode UI gating, UI smoke tests,
  end-to-end orchestration.

**Design choice: tests are structural, not LLM-correctness.** They
verify the agent *refuses* to fabricate, *partitions* tools correctly,
*surfaces* sources in the expected format — not that the LLM "says the
right thing." That distinction matters: prompt-correctness drifts
across model versions; structural enforcement does not.

End-to-end tests against the real Gemini API and Inderes MCP are not in CI
(they require live credentials and consume quota). Run them manually:

```bash
python -m inderes_agent "What's Konecranes' current P/E?"
```

The diagnostic `python scripts/diag.py` independently probes Gemini and MCP
with per-step timing — useful when something is hanging.

---

## Project layout

```
src/inderes_agent/
├── __main__.py        # entry point; prefetches OAuth token before async work
├── settings.py        # pydantic-settings env loader
├── logging.py         # structlog setup
├── agents/
│   ├── lead.py        # aino-lead orchestrator (no tools)
│   ├── quant.py       # aino-quant
│   ├── research.py    # aino-research
│   ├── sentiment.py   # aino-sentiment
│   ├── portfolio.py   # aino-portfolio
│   ├── valuation.py   # aino-valuation (opt-in, fetches BVPS/ROE for engine)
│   ├── conflict_detector.py  # pre-synthesis disagreement detector
│   ├── _common.py     # load_prompt() + today_prompt_prefix() (date-aware)
│   └── prompts/       # system prompts for each agent (markdown)
├── valuation/
│   ├── engine.py            # deterministic Greenwald-Gordon + EPV math
│   ├── parser.py            # validates agent JSON before engine consumes it
│   ├── roe_selection.py     # sustainable-ROE rule (single source of truth)
│   └── __init__.py          # public API: value_stock, parse, ValuationParseError
├── llm/
│   └── gemini_client.py    # FallbackGeminiChatClient + hybrid tool-config fix
├── mcp/
│   ├── inderes_client.py   # MCP tool factory + schema sanitization
│   └── oauth.py            # OAuth Authorization Code + PKCE flow + gist mirror
├── orchestration/
│   ├── router.py      # query classification + valuation-intent gate
│   ├── workflows.py   # asyncio.gather + semaphore fan-out
│   └── synthesis.py   # lead synthesis + tool-call guard for valuation
├── cli/
│   ├── repl.py        # interactive mode + slash commands
│   └── render.py      # rich-formatted output
└── observability/
    ├── tracing.py        # OpenTelemetry tracer
    ├── run_log.py        # per-run directory writer
    ├── output_parts.py   # MAF response-part parser (text/code/result/calls)
    └── narrate.py        # narrative.md generator

ui/
├── app.py             # Streamlit Trading Desk app
├── components.py      # CustomStatus, hero panel, agent rows, chips, badge
├── theme.css          # JetBrains Mono + persona colors + dark chrome
├── README.md          # UI walkthrough
└── DEPLOY.md          # Streamlit Cloud deployment guide

scripts/
├── diag.py                       # standalone Gemini + MCP diagnostic
├── explain.py                    # regenerate narrative.md for any past run
├── probe_mcp_response.py         # raw-MCP debugging helper
└── refresh_inderes_tokens.py     # cron worker — refreshes tokens via gist

.github/workflows/
└── refresh-inderes-tokens.yml    # 15-min cron invoking the script above

tests/                 # 38 pytest unit tests (router/fallback/workflow/parts/oauth/agents)
examples/              # single_question.py, conversation.py
```

Top-level docs: `README.md`, `ARCHITECTURE.md`, `LESSONS.md`,
`AGENT_FRAMEWORK.md`, `TROUBLESHOOTING.md`, `CHANGELOG.md`, `BACKLOG.md`,
`CONTRIBUTING.md`, `BUILD_SPEC.md`.

Module-level explanations in [ARCHITECTURE.md](ARCHITECTURE.md). Build rationale
in [`BUILD_SPEC.md`](BUILD_SPEC.md). Reflective write-up in
[`LESSONS.md`](LESSONS.md).

---

## Pre-flight checklist

Before your first real run:

- [ ] Apple Silicon? Verify `python -c "import platform; print(platform.machine())"` prints `arm64`. If `x86_64`, recreate venv per [TROUBLESHOOTING](TROUBLESHOOTING.md#imports-take-30-60-seconds-on-apple-silicon).
- [ ] `uv pip install --pre -e .` succeeded without errors.
- [ ] At least 20 GB free disk space (`df -h .`).
- [ ] `GEMINI_API_KEY` set in `.env`.
- [ ] Inderes Premium subscription active.
- [ ] Running interactively (not in headless CI / SSH) — first run opens a browser for OAuth.
- [ ] Tests pass: `pytest -q`.
