# inderes-research-agent

Multi-agent stock research conversation system for Nordic equities. Built on **Microsoft Agent Framework 1.0+** (Python), powered by **Google Gemini** with automatic primary→fallback model selection, querying **Inderes MCP** at `https://mcp.inderes.com`.

```bash
python -m inderes_agent "Mitä Sammon nykytilanteesta tulisi ajatella?"
```

A lead orchestrator (`aino-lead`) classifies the query, fans out to specialized subagents (`aino-quant`, `aino-research`, `aino-sentiment`, `aino-portfolio`), each running its own tool-calling loop against a focused subset of Inderes MCP tools, and synthesizes a unified answer. The system **surfaces signals** — Inderes' own recommendation, target price, insider activity, analyst notes, forum sentiment — but **never gives buy/sell recommendations of its own**.

For deep architecture: [ARCHITECTURE.md](ARCHITECTURE.md). For known issues: [TROUBLESHOOTING.md](TROUBLESHOOTING.md). For decision history: [CHANGELOG.md](CHANGELOG.md).

---

## Quick start

```bash
# 1. Prerequisites
#    - Apple Silicon Mac or Linux ARM/x86_64
#    - uv installed: curl -LsSf https://astral.sh/uv/install.sh | sh
#    - Inderes Premium subscription (https://www.inderes.fi/premium)
#    - Gemini API key (free at https://aistudio.google.com)

# 2. Clone and install
git clone <repo-url>
cd inderes-research-agent
uv python install 3.13
uv venv --python-preference only-managed --python 3.13
source .venv/bin/activate
uv pip install --pre -e .

# 3. Configure
cp .env.example .env
# Edit .env: set GEMINI_API_KEY

# 4. Run (first time opens browser for Inderes OAuth)
python -m inderes_agent "What's Konecranes' current P/E?"

# Or interactive REPL
python -m inderes_agent
```

The `--pre` flag is required because `agent-framework-gemini` is currently published as a pre-release.

---

## Modes

```bash
# One-shot
python -m inderes_agent "Compare Sampo and Nordea on profitability"

# Interactive REPL
python -m inderes_agent
> Anna pikakatsaus Konecranesista.
> Entä insider-aktiivisuus?
> /explain
> /exit
```

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

---

## Per-run logs

Every query writes a complete forensic record to `~/.inderes_agent/runs/<timestamp>/`:

```
20260501-203226-880/
├── query.txt              # the user question
├── routing.json           # which subagents the router picked, plus reasoning
├── subagent-01-quant.json # full output of each subagent (text, model used, error)
├── subagent-02-research.json
├── subagent-03-sentiment.json
├── synthesis.txt          # lead's final synthesized answer
├── meta.json              # duration, fallback events, error counts
├── console.log            # raw HTTP/MCP/fallback log lines with timestamps
└── narrative.md           # human-readable timeline (auto-generated)
```

`narrative.md` is the single best file to read when you want to understand what happened. It includes routing decision + reasoning, a tool-call timeline with timing per agent, each subagent's output, the lead's synthesis, and a footer with stats.

You can also regenerate the narrative for any past run via the CLI helper:

```bash
python scripts/explain.py                       # latest run
python scripts/explain.py 20260501-203226-880   # specific run
```

---

## Architecture

```
                  User question
                       │
                       ▼
                ┌──────────────┐
                │  Router LLM  │  ← Gemini call with structured-output JSON
                └──────┬───────┘
                       │
          ┌────────────┼────────────┬─────────────┐
          ▼            ▼            ▼             ▼
     aino-quant  aino-research aino-sentiment aino-portfolio
                                                                ← subagents (Gemini + AFC loop + MCP tools)
          │            │            │             │
          └────────────┴────────────┴─────────────┘
                       │
                       ▼     ← bounded by MAX_CONCURRENT_AGENTS (default 2)
                Inderes MCP (16 tools, partitioned per subagent)
                       │
                       ▼
                ┌──────────────┐
                │   aino-lead  │  ← reads subagent outputs, synthesizes one answer
                └──────┬───────┘
                       ▼
                  Final answer
```

### Subagent → MCP tool mapping

| Agent | MCP tools |
|---|---|
| `aino-quant` | `search-companies`, `get-fundamentals`, `get-inderes-estimates` |
| `aino-research` | `search-companies`, `list-content`, `get-content`, `list-transcripts`, `get-transcript`, `list-company-documents`, `get-document`, `read-document-sections` |
| `aino-sentiment` | `search-companies`, `list-insider-transactions`, `search-forum-topics`, `get-forum-posts`, `list-calendar-events` |
| `aino-portfolio` | `get-model-portfolio-content`, `get-model-portfolio-price`, `search-companies` |

Each subagent only sees its allowed subset (enforced via `MCPStreamableHTTPTool(allowed_tools=...)`).

For a fuller architectural walkthrough — how Inderes MCP, Keycloak OAuth, the Gemini fallback wrapper and the run-log narrator fit together — see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Free-tier-realistic Gemini model fallback

Free-tier Gemini quota only allows lite-tier models. The system uses:

- **Primary**: `gemini-3.1-flash-lite-preview` — 500 requests/day, occasionally 503s under load
- **Fallback**: `gemini-2.5-flash` — 20 requests/day, used automatically on persistent 503 or any 429
- **Forbidden**: pro-tier models — quota-zero on free tier; not used anywhere

Fallback policy (Section 6.8 of `BUILD_SPEC.md`):
1. First attempt → primary model
2. On `503 UNAVAILABLE` → wait `RETRY_DELAY_MS`, retry once
3. On second 503 OR any `429 RESOURCE_EXHAUSTED` → switch to fallback for that single request
4. Fallback gets two attempts with 2s/4s backoff
5. Both exhausted → `QuotaExhaustedError` with a clear user message

Inspect which model handled each subagent call in the REPL with `/trace` or in `narrative.md`.

**Paid tier** (recommended): same code, just enable billing in Google AI Studio. Costs ~$0.005–0.02 per query depending on complexity. Lifts daily quotas and reduces 503 frequency dramatically. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#503-errors-from-gemini) for details.

---

## Concurrency budget

Multi-agent fan-out burns LLM quota fast. `MAX_CONCURRENT_AGENTS=2` (default) caps how many subagents run in parallel. Comparison queries with N>2 companies are queued, not parallelized. Override in `.env` if you have a higher quota.

---

## Configuration (`.env`)

```ini
GEMINI_API_KEY=               # required, free at aistudio.google.com
INDERES_MCP_URL=https://mcp.inderes.com
INDERES_MCP_CLIENT_ID=inderes-mcp
PRIMARY_MODEL=gemini-3.1-flash-lite-preview
FALLBACK_MODEL=gemini-2.5-flash
RETRY_DELAY_MS=1000
MAX_RETRIES=1
MAX_CONCURRENT_AGENTS=2
LOG_LEVEL=INFO
LOG_JSON=false
```

---

## Tests

```bash
uv pip install -e '.[dev]'
pytest -q
```

13 unit tests cover the router (JSON parsing, schema validation), the fallback client (503 retry, 429 quota exhaustion, success path), and workflow fan-out (per-company branching, concurrency cap). End-to-end tests against real Gemini + real Inderes MCP are not in CI — run them manually with a real API key.

---

## What this system will NOT do

- Recommend "buy" or "sell" as its own opinion (it surfaces Inderes' recommendation as a separate line)
- Replace investment advice
- Predict prices
- Use any Pro-tier Gemini model (free-tier quota is zero there)
- Hardcode company IDs (always resolves via `search-companies`)

---

## Manual setup checklist

- [ ] Apple Silicon? Use ARM-native Python via `uv` (see Quick start). Intel-Python on M-series Mac runs through Rosetta and is **10× slower** — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#imports-take-30-60-seconds-on-apple-silicon)
- [ ] `pip install --pre -e .` (or `uv pip install --pre -e .`) succeeded
- [ ] `GEMINI_API_KEY` set in `.env`
- [ ] Inderes Premium subscription active
- [ ] First-run OAuth browser flow completed (this is interactive — don't first-run in a headless environment)

---

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for module-level design. See `BUILD_SPEC.md` §5 for the original spec.

```
src/inderes_agent/
  agents/         # 5 agent factories + system prompts (.md)
  mcp/            # Inderes MCP tool partitioning + OAuth flow
  llm/            # Gemini client with primary→fallback wrapper
  orchestration/  # router, workflow execution, lead synthesis
  cli/            # REPL, render (rich), slash commands
  observability/  # OpenTelemetry tracer setup, per-run logger, narrator
  settings.py     # pydantic-settings env loader
  logging.py      # structlog setup
  __main__.py     # entry point

tests/
scripts/
  diag.py         # standalone connectivity diagnostic
  explain.py      # print narrative for any past run
examples/
```
