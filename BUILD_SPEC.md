# inderes-research-agent — build specification

> **Status**: design specification for a multi-agent stock research system on Microsoft Agent Framework (Python) using Google Gemini and Inderes MCP. The implementation has authority to make decisions where this spec is silent.
>
> **Note**: this is the original specification used to bootstrap the project. The current implementation is described in [`ARCHITECTURE.md`](ARCHITECTURE.md). Some details here (e.g. exact API choices) were updated during build; see [`CHANGELOG.md`](CHANGELOG.md) for what changed.

---

## 1. What This Project Is

A conversational multi-agent system that lets the user ask questions in natural language ("How does Konecranes look right now?", "Compare Sampo and If P&C", "What's hot in the Inderes model portfolio this month?") and gets back a synthesized answer based on real data fetched live from Inderes MCP.

Different from `stock-agent-ts` (the previous project): that one is a structured valuation tool with fixed report templates. This one is a **research conversation partner** — open-ended, adaptive, queries Inderes data based on what the user actually asks.

**End-state command**:
```bash
python -m inderes_agent
> Compare Konecranes and Cargotec on profitability and analyst views
[multi-agent system queries Inderes, synthesizes answer]
```

Or with a one-shot question:
```bash
python -m inderes_agent "What insider activity has there been at Sampo in the last 90 days?"
```

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Agent framework | `agent-framework` (Microsoft Agent Framework 1.0+) |
| LLM provider | Google Gemini via `google-genai` package |
| Primary model | `gemini-3.1-flash-lite-preview` |
| Fallback model | `gemini-2.5-flash` (used on 503/429 from primary) |
| MCP client | Built into Agent Framework (native MCP support since 1.0) |
| Data source | Inderes MCP at `https://mcp.inderes.com` |
| CLI | `rich` for output, `prompt_toolkit` for input |
| Logging | `structlog` (JSON in production) |
| Tests | `pytest` + `pytest-asyncio` |
| Env | `python-dotenv`, `pydantic-settings` |

### 2.1 Model selection

The system uses two Gemini Flash-tier models with automatic fallback:

- ✅ `gemini-3.1-flash-lite-preview` — primary, can return `503 UNAVAILABLE` during capacity spikes
- ✅ `gemini-2.5-flash` — fallback, used on persistent 503 or any 429
- ❌ `gemini-3.1-flash-lite` (without `-preview` suffix) — `404 model not found`

**Architectural implication**: lead orchestrator and all subagents share the same model class. Synthesis quality comes from prompt engineering, not from upgrading the lead to a smarter model. See §6.8 for the fallback implementation.

The system runs on the paid Gemini API tier in production. The free tier worked for early development but TPM (tokens-per-minute) limits became a bottleneck once code execution and multi-agent fan-out were enabled — paid tier removes those limits and substantially reduces 503 capacity errors. Per-query cost is roughly $0.005–0.02 depending on complexity.

**Why these stack choices**:
- Microsoft Agent Framework — alignment with the OP-aligned learning goal
- Gemini — best price/quality at Flash tier and native code execution support
- Python — broad MAF support and the developer's preferred language
- MCP — first-class support in MAF 1.0+, no custom client needed

---

## 3. Inderes MCP — Tool Inventory

The MCP server at `https://mcp.inderes.com` exposes 16 tools. Subagent specializations must be designed around these tool groups — do NOT give one agent all 16 tools; split by responsibility.

### 3.1 Discovery & Identifiers (every workflow starts here)

| Tool | Purpose |
|---|---|
| `search-companies(query)` | Company name → `COMPANY:nnn` ID. Almost every other tool needs this ID. |

### 3.2 Quantitative — Fundamentals & Estimates

| Tool | Purpose |
|---|---|
| `get-fundamentals(companyIds, fields?, startYear?, endYear?, resolution?)` | Historical financials. Fields include: revenue, ebitda, ebitPercent, epsReported, dividend, dividendYield, pe, pb, evEbit, evEbitda, evSales, marketCap, enterpriseValue, equityRatio, gearingRatio, roe, roi, sharesTotal, currency. yearly or quarterly. |
| `get-inderes-estimates(fields, companyIds?, count?, includeQuarters?, yearCount?)` | Forward-looking estimates + **recommendation (BUY/HOLD/SELL), target price, risk score**. yearCount defines how many forward years. Quarters available. |

### 3.3 Qualitative — Inderes' own content

| Tool | Purpose |
|---|---|
| `list-content(companyId?, types?, first?, after?)` | Browse Inderes-authored material. Types: `ANALYST_COMMENT`, `ARTICLE`, `COMPANY_REPORT`, `EXTENSIVE_COMPANY_REPORT`, `THIRD_PARTY_COMPANY_REPORT`, `PRESS_RELEASE`, `STOCK_EXCHANGE_RELEASE`, `QA`, `TRANSCRIPT`, `VIDEO`, `WEBCAST`. **High-volume types (PRESS_RELEASE, STOCK_EXCHANGE_RELEASE) should be fetched separately.** |
| `get-content(contentId? OR url?, lang?)` | Full body of a single piece. Returns markdown for articles, OR for ingested PDF reports returns `documentId` + sections TOC. |
| `list-transcripts(companyId?, first?, after?)` | Earnings webcast / analyst interview transcripts metadata. |
| `get-transcript(transcriptId, lang?)` | Full transcript text with speaker labels. |

### 3.4 Company-issued documents

| Tool | Purpose |
|---|---|
| `list-company-documents(companyId, first?, after?)` | Company's own filings (annual reports, interim reports). |
| `get-document(documentId)` | Document metadata + table of contents. |
| `read-document-sections(documentId, sectionNumbers)` | Read specific sections by number. |

### 3.5 Forum (community sentiment)

| Tool | Purpose |
|---|---|
| `search-forum-topics(text, order?)` | Title-based topic search; up to 10 threads. |
| `get-forum-posts(threadUrl, first?/last?, after?/before?)` | Posts from a thread. Use `last: N` for most recent. |

### 3.6 Market signals

| Tool | Purpose |
|---|---|
| `list-calendar-events(companyId?, dateFrom?, dateTo?, types?, regions?, first?)` | Earnings dates, dividends, AGMs, capital market days. Types include all standard event types. |
| `list-insider-transactions(companyId?, dateFrom?, dateTo?, types?, regions?, first?)` | Insider buy/sell signals. Types include BUY, SELL, SUBSCRIPTION, EXERCISE_OF_SHARE_OPTION, etc. |

### 3.7 Inderes model portfolio

| Tool | Purpose |
|---|---|
| `get-model-portfolio-content()` | Current positions, EUR amounts (acquisition vs current). |
| `get-model-portfolio-price(dateFrom?, scale?)` | Historical total portfolio value. |

### 3.8 Workflow patterns (for subagent design)

```
Common chain: Company name → search-companies → companyId → other tools

Quantitative analysis chain:
  search-companies → get-fundamentals (historical) → get-inderes-estimates (forward) → done

Qualitative deep-dive:
  search-companies → list-content (filter by COMPANY_REPORT) → get-content (latest report)
                   → list-transcripts → get-transcript (latest earnings call)

Insider/sentiment chain:
  search-companies → list-insider-transactions (last 90 days)
                   → search-forum-topics → get-forum-posts (most recent)

Calendar awareness:
  list-calendar-events (no filter, dateFrom=today, types=[INTERIM_REPORT, ANNUAL_REPORT])
```

---

## 4. Agent Architecture

### 4.1 Agents

Implement these as separate `Agent` instances. Each has a focused tool subset and a clear role description.

#### Lead Orchestrator: `aino-lead`
- **Model**: `gemini-3.1-flash-lite-preview` (primary), `gemini-2.5-flash` (fallback) — see Section 6.8
- **Tools**: NONE directly. Delegates everything.
- **Role**: Parse user question → decide which subagent(s) to call → optionally call multiple in parallel → synthesize final answer
- **Orchestration pattern**: Use MAF's **handoff** pattern for routing decisions; **concurrent** when multiple subagents needed simultaneously
- **Note on synthesis quality**: since primary model is a small lite-preview model, lead's system prompt must be more explicit and structured than usual. Use few-shot examples in the prompt for routing decisions.

#### Subagent: `aino-quant`
- **Model**: `gemini-3.1-flash-lite-preview` (primary), `gemini-2.5-flash` (fallback)
- **Tools**: `search-companies`, `get-fundamentals`, `get-inderes-estimates`
- **Role**: Numerical analysis. Historical financials, forward estimates, valuation multiples, recommendations, target prices. Returns structured numbers with brief commentary.
- **Triggers**: questions about P/E, ROE, growth, margins, target prices, analyst views (numerical part)

#### Subagent: `aino-research`
- **Model**: `gemini-3.1-flash-lite-preview` (primary), `gemini-2.5-flash` (fallback)
- **Tools**: `search-companies`, `list-content`, `get-content`, `list-transcripts`, `get-transcript`, `list-company-documents`, `get-document`, `read-document-sections`
- **Role**: Qualitative research. Reads Inderes' own analyst reports, latest articles, earnings call transcripts, company-issued reports. Extracts key narratives, strategy points, risks.
- **Triggers**: questions like "what does Inderes think", "what was said in the latest call", "summarize the strategy"
- **Note**: this agent reads long documents (transcripts, reports). Watch context window — chunk reading via `read-document-sections` rather than full documents when possible.

#### Subagent: `aino-sentiment`
- **Model**: `gemini-3.1-flash-lite-preview` (primary), `gemini-2.5-flash` (fallback)
- **Tools**: `search-companies`, `list-insider-transactions`, `search-forum-topics`, `get-forum-posts`, `list-calendar-events`
- **Role**: Market signals — insider activity, forum sentiment, upcoming events. Detects "what's brewing".
- **Triggers**: questions about insiders, sentiment, forum buzz, upcoming earnings

#### Subagent: `aino-portfolio`
- **Model**: `gemini-3.1-flash-lite-preview` (primary), `gemini-2.5-flash` (fallback)
- **Tools**: `get-model-portfolio-content`, `get-model-portfolio-price`, `search-companies` (for company name → ID when discussing positions)
- **Role**: Inderes model portfolio analysis. What's held, performance, recent changes.
- **Triggers**: questions about Inderes model portfolio, what they own, performance

### 4.2 Orchestration Patterns

Use Microsoft Agent Framework's built-in patterns. Pick based on user query type:

| Query type | Pattern | Example |
|---|---|---|
| Single-domain question | Direct delegation (sequential) | "What's Konecranes P/E?" → quant only |
| Multi-domain question | Concurrent + synthesis | "Should I buy Sampo?" → quant + research + sentiment in parallel, lead synthesizes |
| Comparison | Concurrent fan-out per company, then synthesis | "Compare Konecranes and Cargotec" → quant(KCR) ‖ quant(CGCBV) ‖ research(KCR) ‖ research(CGCBV) → synthesize |
| Open-ended exploration | Group chat between subagents | "What's interesting in industrials right now?" → research + sentiment + portfolio discuss, lead summarizes |
| Sequential refinement | Handoff | User clarifies as they go: lead routes new questions to whichever subagent is relevant |

**Default pattern**: lead receives query → classifies → spawns concurrent subagent calls → waits all → synthesizes. This is the multi-agent research system pattern.

### 4.3 Agent Loop

The agent loop follows MAF's standard:
1. User input received
2. Lead classifies query (LLM call)
3. Lead invokes subagents (handoff or concurrent)
4. Each subagent runs its own loop: think → call MCP tool → observe → think → ... → return
5. Lead receives subagent results (structured)
6. Lead synthesizes final answer
7. Lead presents to user
8. (Optional) User asks follow-up → repeat from step 1 with conversation context

Use MAF's checkpointing if the user should be able to interrupt and resume. Use streaming for the synthesis step so the user sees partial output.

---

## 5. Repository Structure

```
inderes-research-agent/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── BUILD_SPEC.md                 ← this file
│
├── src/
│   └── inderes_agent/
│       ├── __init__.py
│       ├── __main__.py           ← entry point
│       ├── settings.py           ← pydantic-settings, validates env
│       ├── logging.py            ← structlog setup
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── lead.py           ← aino-lead orchestrator
│       │   ├── quant.py          ← aino-quant
│       │   ├── research.py       ← aino-research
│       │   ├── sentiment.py      ← aino-sentiment
│       │   ├── portfolio.py      ← aino-portfolio
│       │   └── prompts/          ← system prompts as separate .md files
│       │       ├── lead.md
│       │       ├── quant.md
│       │       ├── research.md
│       │       ├── sentiment.md
│       │       └── portfolio.md
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── inderes_client.py ← MCP connection setup
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   └── gemini_client.py  ← Gemini chat client factory
│       │
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── router.py         ← query classification
│       │   ├── workflows.py      ← MAF workflow definitions
│       │   └── synthesis.py      ← lead synthesis logic
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── repl.py           ← interactive mode
│       │   └── render.py         ← rich-based output formatting
│       │
│       └── observability/
│           ├── __init__.py
│           └── tracing.py        ← OpenTelemetry / MAF middleware
│
├── tests/
│   ├── conftest.py
│   ├── test_router.py
│   ├── test_agents/
│   │   ├── test_quant.py
│   │   ├── test_research.py
│   │   └── test_sentiment.py
│   └── fixtures/
│       └── sample_mcp_responses.json
│
└── examples/
    ├── single_question.py
    └── conversation.py
```

---

## 6. Key Implementation Notes

### 6.1 Gemini setup with MAF

Microsoft Agent Framework 1.0+ has first-party Gemini support via the `agent_framework_gemini` package (which uses `google-genai` underneath). Verify exact import paths at the official documentation. If the direct Gemini integration is awkward in some context, the OpenAI-compatible Gemini endpoint at `https://generativelanguage.googleapis.com/v1beta/openai` works with `OpenAIChatClient` setting `base_url`.

Pattern (sketch — verify actual API at build time):

```python
from agent_framework import Agent
# Whatever the actual import is for Gemini in MAF 1.0+
from agent_framework.gemini import GeminiChatClient

agent = Agent(
    chat_client=GeminiChatClient(
        api_key=settings.GEMINI_API_KEY,
        model=settings.PRIMARY_MODEL,  # "gemini-3.1-flash-lite-preview"
    ),
    name="aino-quant",
    instructions=load_prompt("quant.md"),
    tools=[...],  # MCP tools
)
```

### 6.2 MCP integration

MAF 1.0+ supports MCP natively. Use streamable HTTP transport.

```python
# Sketch — use the actual MAF MCP API at build time
from agent_framework.mcp import McpStreamableHttp

inderes_mcp = McpStreamableHttp(
    url="https://mcp.inderes.com",
    name="inderes",
    # OAuth — first run opens browser
)

# Filter tools per agent: each agent gets only the subset it needs
quant_tools = await inderes_mcp.list_tools(filter=["search-companies", "get-fundamentals", "get-inderes-estimates"])
```

OAuth note: Inderes MCP uses OAuth. First run will open a browser. User must have Inderes Premium subscription. Document this in README.

### 6.3 Router — query classification

Lead agent classifies the user query into one or more domains. Implement as a simple structured-output LLM call.

```python
from pydantic import BaseModel
from enum import Enum

class Domain(str, Enum):
    QUANT = "quant"
    RESEARCH = "research"
    SENTIMENT = "sentiment"
    PORTFOLIO = "portfolio"

class QueryClassification(BaseModel):
    domains: list[Domain]            # which subagents to invoke
    companies: list[str]             # company names to resolve
    is_comparison: bool              # if True, fan out per company
    reasoning: str                   # short explanation, for logs
```

Lead invokes Gemini with structured output to fill this model.

### 6.4 Subagent contract

Each subagent should return a structured object that the lead can synthesize. Use Pydantic models per subagent. Examples:

```python
class QuantResult(BaseModel):
    company: str
    company_id: str
    summary: str                     # 1-3 sentence narrative
    fundamentals: dict               # key metrics
    estimates: dict | None
    recommendation: str | None       # BUY/HOLD/SELL
    target_price_eur: float | None
    sources: list[str]               # tool calls made

class ResearchResult(BaseModel):
    company: str
    summary: str
    key_themes: list[str]
    latest_report_summary: str | None
    earnings_call_highlights: list[str] | None
    sources: list[str]
```

### 6.5 Synthesis

Lead receives subagent results and writes the final answer. Always include:
- Direct answer to the user's question (one paragraph)
- Supporting data (concise, only what was asked)
- Source list at the end (which Inderes tools were called)

For comparisons, format as a side-by-side table when natural.

### 6.6 Observability

MAF has OpenTelemetry built-in. Configure to log to console in dev, optionally to file in production. Capture:
- Each agent invocation (start, end, duration)
- Each tool call (name, params, success/failure, duration)
- LLM calls (input tokens, output tokens, model)
- Final synthesis duration

This is the same pattern user works with at OP. Make it visible.

### 6.7 Conversation memory

User can have multi-turn conversations. Use MAF's built-in conversation memory (`ChatHistory` or equivalent). Maintain context across turns.

When user follows up ("and the dividend yield?"), lead doesn't need to re-classify — it has context.

### 6.8 Model fallback strategy (CRITICAL)

The primary model `gemini-3.1-flash-lite-preview` is a preview model and can return `503 UNAVAILABLE` during capacity spikes (this happens on both free and paid tiers, just much less often on paid). The system must handle this gracefully without losing the user's query.

**Required behavior**:

1. **First attempt**: send request to primary model
2. **On `503 UNAVAILABLE`**: retry once after 1 second (preview models often recover quickly)
3. **On second `503` or any `429 RESOURCE_EXHAUSTED`**: switch to fallback model `gemini-2.5-flash` for this request only, and log the fallback event
4. **On fallback success**: return result, mark response with model used (visible in `/trace`)
5. **On fallback failure**: surface a clear error to the user, do not silently fail

**Implementation approach** (choose what fits MAF's middleware/retry hooks at build time):

Option A — middleware in MAF:
```python
# Sketch — pseudocode; use the actual MAF middleware API
class ModelFallbackMiddleware:
    async def on_request(self, ctx):
        try:
            return await ctx.call_with_model(settings.PRIMARY_MODEL)
        except UnavailableError:  # 503
            await asyncio.sleep(1.0)
            try:
                return await ctx.call_with_model(settings.PRIMARY_MODEL)
            except (UnavailableError, ResourceExhaustedError):
                logger.warning("falling_back_to_secondary",
                               primary=settings.PRIMARY_MODEL,
                               fallback=settings.FALLBACK_MODEL)
                return await ctx.call_with_model(settings.FALLBACK_MODEL)
```

Option B — wrap the chat client:
Build a `FallbackChatClient` that holds two underlying chat clients (primary + fallback) and routes per-request.

Either works. The system must NOT have a hardcoded model name in any agent constructor; all model selection goes through this fallback layer.

**Configuration**:
```
PRIMARY_MODEL=gemini-3.1-flash-lite-preview
FALLBACK_MODEL=gemini-2.5-flash
RETRY_DELAY_MS=1000
MAX_RETRIES=1
```

**Quota awareness**: free tier has tight daily request limits (500 RPD primary, 20 RPD fallback). On the paid tier these are removed but per-token cost applies. Either way, surface quota exhaustion clearly:
- On `429 RESOURCE_EXHAUSTED` from BOTH primary and fallback: surface a clear `QuotaExhaustedError` to the user.

### 6.9 Concurrency limits

Multi-agent fan-out is a request multiplier. A "compare two companies" query triggering quant + research + sentiment in parallel for both companies can be 6+ LLM calls per question; with each subagent's internal AFC loop the real number is higher.

**Mitigations**:
- Set `MAX_CONCURRENT_AGENTS=2` env var (default), capping parallel fan-out.
- For comparison queries with N companies, prefer sequential per-company processing if N > 2.
- This protects against rate-limit spikes (TPM/RPM) on either tier and keeps cost predictable.

---

## 7. CLI UX

### 7.1 Modes

```bash
# One-shot
python -m inderes_agent "What's Konecranes P/E?"

# Interactive REPL
python -m inderes_agent
> What's Konecranes P/E?
[answer]
> And dividend yield?
[answer]
> exit
```

### 7.2 Output

Use `rich` library for formatted terminal output:
- Headers in bold
- Tables for comparisons
- Code blocks for raw numbers
- Progress spinners during agent calls
- Source list at end with collapsed/expandable details

Example output:
```
🔍 Konecranes (KCR1V) — Quick view

Recommendation: BUY (Inderes, target €52.00)
P/E (LTM):      16.6×    P/E (FY+1 est): 14.2×
ROE 5y avg:     11.4 %   Dividend yield: 2.7 %

Latest analyst note: "Q1 beat on Service segment, +12 % YoY orders"
                     (Inderes ANALYST_COMMENT, 2026-04-22)

Sources: get-fundamentals, get-inderes-estimates, list-content
```

### 7.3 Slash commands in REPL

- `/help` — list commands
- `/clear` — clear conversation history
- `/agents` — show which subagents have been invoked in this session
- `/trace` — show last query's tool calls (for debugging)
- `/exit` — quit

---

## 8. Example Use Cases (Acceptance Tests)

These are the queries the system must handle correctly. Include them as examples in tests where applicable.

### 8.1 Simple quant
> "What's Konecranes' current P/E?"

Expected: lead → quant (only) → search-companies + get-fundamentals → answer with one number + small context.

### 8.2 Multi-domain
> "Should I be worried about Sampo?"

Expected: lead classifies as RESEARCH + SENTIMENT (and maybe QUANT). Concurrent fan-out. Synthesis identifies recent news, insider activity, analyst view. **No "Buy/Sell" recommendation from the system itself** — surfaces signals, user decides.

### 8.3 Comparison
> "Compare Konecranes and Cargotec on profitability and growth."

Expected: fan out per company, quant for each, side-by-side table in output.

### 8.4 Portfolio question
> "What does Inderes hold in their model portfolio right now?"

Expected: lead → portfolio (only) → list of positions with sizes + recent change.

### 8.5 Calendar / event
> "What earnings reports are coming this week?"

Expected: lead → sentiment (which has calendar tool) → list-calendar-events with date filter → formatted upcoming events.

### 8.6 Open-ended exploration
> "What's interesting in industrials right now?"

Expected: lead spawns research + sentiment + portfolio in group-chat-style discussion. Synthesis surfaces 3-5 signals.

### 8.7 Multi-turn
```
> Konecranes — quick overview?
[answer]
> What about insider activity?
[lead uses context — knows we're still talking about Konecranes; routes to sentiment only]
[answer]
> Latest earnings call highlights?
[research with transcript]
```

---

## 9. Configuration & Setup

### 9.1 .env.example

```
# Gemini API — get free key at aistudio.google.com
GEMINI_API_KEY=

# Inderes MCP
INDERES_MCP_URL=https://mcp.inderes.com
INDERES_MCP_CLIENT_ID=inderes-mcp

# Models — primary lite-preview with stable fallback
PRIMARY_MODEL=gemini-3.1-flash-lite-preview
FALLBACK_MODEL=gemini-2.5-flash

# Fallback behavior
RETRY_DELAY_MS=1000
MAX_RETRIES=1

# Concurrency control (rate-limit safety + predictable cost)
MAX_CONCURRENT_AGENTS=2

# Logging
LOG_LEVEL=INFO
```

### 9.2 pyproject.toml

```toml
[project]
name = "inderes-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "agent-framework>=1.0",      # Microsoft Agent Framework
    "google-genai",               # Gemini client
    "pydantic>=2",
    "pydantic-settings>=2",
    "structlog",
    "rich",
    "prompt_toolkit",
    "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]

[project.scripts]
inderes-agent = "inderes_agent.__main__:main"
```

### 9.3 Setup steps in README

1. `pip install -e .`
2. Copy `.env.example` to `.env`, add `GEMINI_API_KEY` (get from aistudio.google.com)
3. Subscribe to Inderes Premium (`inderes.fi/premium`)
4. Run `python -m inderes_agent` — first run opens browser for Inderes OAuth
5. Ask questions

---

## 10. Build process

1. Read this entire spec.
2. Verify the Microsoft Agent Framework Python API at https://learn.microsoft.com/en-us/agent-framework/ (the Python docs specifically) — the framework is recent enough that training-data references can be stale.
3. Verify Gemini integration approach in MAF — either native `GeminiChatClient` or OpenAI-compatible endpoint at `https://generativelanguage.googleapis.com/v1beta/openai`.
4. Verify MCP client API in MAF (especially `MCPStreamableHTTPTool` and how it accepts auth).
5. Generate the full project per §5 structure.
6. Implement all 5 agents (§4).
7. Implement orchestration patterns (§4.2).
8. Implement CLI (§7).
9. Write tests for the 7 example queries (§8).
10. Ensure `python -m inderes_agent "What's Konecranes' P/E?"` works end-to-end (mocked MCP for tests, real for manual run).

### Implementation authority

- Make implementation choices the spec doesn't cover.
- Choose specific MAF API patterns (sequential vs concurrent vs handoff) per orchestration need.
- Write subagent prompts (in `prompts/*.md`) using this spec's role descriptions as guidance.
- Add reasonable error handling and retries beyond what's described in §6.8.
- Use latest stable versions of all packages.

### Hard constraints

- Don't change the framework (MAF, not LangGraph or LangChain).
- Don't change the LLM provider (Gemini).
- Don't change the data source (Inderes MCP).
- Don't add a web frontend (CLI only).
- Don't auto-buy or recommend stocks — surface data, the user decides.

---

## 11. Anti-Patterns

❌ One mega-agent with all 16 MCP tools — split by responsibility
❌ Hardcoding company IDs — always go through `search-companies` first
❌ Passing entire MCP responses to the user — synthesize, don't dump
❌ Saying "BUY" or "SELL" as the system's view — surface Inderes' rec separately
❌ Calling `list-content` without `types` filter — gets drowned by press releases
❌ Reading entire PDF reports — use `get-document` for TOC, then `read-document-sections` for relevant sections only
❌ Hardcoding model names in agent constructors — all model selection goes through the fallback layer (§6.8)
❌ Silent fallback without logging — `/trace` and `narrative.md` must show which model handled each request
❌ Unbounded concurrent fan-out — respect `MAX_CONCURRENT_AGENTS` to control rate-limit and cost

---

## 12. Acceptance Criteria

Build is complete when:

- [ ] `pip install -e .` succeeds
- [ ] All 5 agents instantiated successfully (smoke test)
- [ ] `python -m inderes_agent "What's Konecranes' P/E?"` returns a sensible answer
- [ ] All 7 example queries (Section 8) work end-to-end
- [ ] Tests pass (`pytest`)
- [ ] OpenTelemetry traces visible in console
- [ ] Multi-turn conversation maintains context
- [ ] Comparison queries fan out and produce side-by-side output (respecting concurrency limit)
- [ ] **Model fallback works**: simulate `503` from primary, system retries then falls back to `gemini-2.5-flash` cleanly
- [ ] **Quota exhaustion handled**: simulate `429` from both models, system surfaces a clear error message
- [ ] `/trace` command shows which model handled each request
- [ ] README explains setup, OAuth flow, model fallback behavior, example questions

User-side manual steps after build:
- Add `GEMINI_API_KEY` to `.env`
- Subscribe to Inderes Premium
- Complete OAuth on first run

---

## 13. Reference Documentation

| Topic | URL |
|---|---|
| Microsoft Agent Framework (Python) | https://learn.microsoft.com/en-us/agent-framework/python/ |
| MAF GitHub | https://github.com/microsoft/agent-framework |
| MAF orchestration patterns | https://learn.microsoft.com/en-us/agent-framework/orchestration/ |
| MAF MCP integration | https://learn.microsoft.com/en-us/agent-framework/integrations/mcp |
| Gemini API | https://ai.google.dev/gemini-api/docs |
| Gemini OpenAI-compatible | https://ai.google.dev/gemini-api/docs/openai |
| Inderes MCP | https://www.inderes.fi/mcp |
| MCP protocol | https://modelcontextprotocol.io/ |

---

End of build spec.
