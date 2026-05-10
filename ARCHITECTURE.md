# Architecture

A deep walkthrough of `inderes-mcp-agent-system`: what each piece does, why it
exists, and how the pieces fit together. Read this if you intend to extend the
system, debug it, or understand the design rationale beyond what `README.md`
covers.

## Table of contents

- [Mental model](#mental-model)
- [Component map](#component-map)
  - [Orchestration](#orchestration)
  - [Agents](#agents)
  - [Inderes MCP integration](#inderes-mcp-integration)
  - [Gemini client with fallback](#gemini-client-with-fallback)
  - [CLI](#cli)
  - [Observability](#observability)
  - [Valuation engine (opt-in feature)](#valuation-engine-opt-in-feature)
- [Run lifecycle](#run-lifecycle)
- [Key design decisions](#key-design-decisions)
- [What this is and isn't](#what-this-is-and-isnt)
- [Extending the system](#extending-the-system)

---

## Mental model

A user asks a natural-language question about a Nordic stock. A **router** classifies
it. A **fan-out workflow** spawns 1–5 **specialized subagents** in parallel, each
with its own focused subset of Inderes MCP tools. Each subagent runs an LLM
tool-calling loop, gathers data from Inderes, and returns a structured text block.
The **valuation subagent** is a special case: it emits structured JSON which a
**deterministic Python engine** consumes to compute fair value (no LLM math).
A **conflict-detector** then reads all subagent outputs and emits a structured map
of where they agree, disagree, and which claims only one subagent made.
Finally, a **lead** synthesizes the subagent outputs *and* the conflict report
into one final answer. Everything that happened gets recorded to disk as a
forensic record and a human-readable narrative.

```
User question
    │
    ▼
Router (Gemini, structured-output JSON)
    │
    ▼ + valuation-intent gate (UI-controlled toggle)
Workflow (asyncio.gather + semaphore on MAX_CONCURRENT_AGENTS)
    │
    ├──→ aino-quant     ─┐
    ├──→ aino-research  ─┤  each: own chat client, own filtered MCP tool set,
    ├──→ aino-sentiment ─┤        own AFC tool-calling loop, own structured output
    ├──→ aino-portfolio ─┤
    └──→ aino-valuation ─┘  emits JSON → tool-call guard → deterministic engine
                         │                (valuation/engine.py: pure Python,
                         │                 Greenwald-Gordon math, no LLM)
                         ▼
              aino-conflict-detector (Gemini, no tools, strict JSON)
              → agreements / conflicts / isolated_claims
                         │
                         ▼
              Lead synthesis (Gemini, no tools)
              → respects 3-state output:
                A) toggle off → default flow unchanged
                B) toggle on, parse_error → honest "skipped" message
                C) toggle on, success → 4-section structure
                         │
                         ▼
              Final answer + persisted run directory
```

A typical multi-domain query takes 8–25 seconds end-to-end. Single-domain queries
are faster (~5–10 s); per-company comparisons (multi-domain × multi-company) are
slower because of the concurrency cap.

---

## Component map

### Orchestration

Files: [`src/inderes_agent/orchestration/`](src/inderes_agent/orchestration/)

| File | Role |
|---|---|
| `router.py` | One Gemini call with a structured-output JSON prompt → `QueryClassification(domains, companies, is_comparison, reasoning)`. Few-shot examples in the prompt drive consistency. Includes tolerant JSON extraction (handles code fences, prose leaks). Also exposes `query_has_valuation_intent()` — keyword heuristic used by the UI to decide whether to extend the router's output with VALUATION when the toggle is on. |
| `workflows.py` | Spawns subagents per the classification. `asyncio.Semaphore(MAX_CONCURRENT_AGENTS)` caps parallelism. For comparisons (N>1 companies × multi-domain non-portfolio), fans out per-company. Records `last_used_model` and any errors per subagent in `SubagentResult` along with the full `tool_calls` list (used downstream by the valuation tool-call guard). |
| `synthesis.py` | Builds a structured prompt from subagent outputs and feeds it to the lead agent. Returns `(answer_text, lead_model_used, trace)`. Also runs `_process_valuation_subagents()` which (a) tool-call-guards every VALUATION subagent (rejecting outputs with zero `get-fundamentals` calls as hallucinations), (b) parses agent JSON, (c) feeds parsed parameters to the deterministic engine. The resulting `Valuation` records are formatted into a block that LEAD's prompt consumes. |

**Why `asyncio.gather` instead of MAF's `ConcurrentBuilder`?**

Three reasons:

1. Per-company fan-out for comparisons must be decided at runtime.
2. Free-tier quota requires a hard concurrency cap (semaphore).
3. The orchestration logic is short enough that direct asyncio is more readable than wrapping it in MAF's builder API.

We retain MAF's per-agent infrastructure (`Agent` context manager, chat client, MCP
tool, AFC loop), just not its orchestration layer.

### Agents

Files: [`src/inderes_agent/agents/`](src/inderes_agent/agents/) and prompts in
[`agents/prompts/`](src/inderes_agent/agents/prompts/).

Five `agent_framework.Agent` instances built via factory functions. Each gets:

- A **system prompt** (`agents/prompts/<role>.md`) that tells it its role, available
  tools, recommended workflow, and required output format.
- A **chat client** (the `FallbackGeminiChatClient`).
- A **filtered MCP tool** (only the subset of Inderes tools relevant to its specialty).

| Agent | Purpose | MCP tools |
|---|---|---|
| `aino-quant` | Numerical analysis: P/E, ROE, target prices, recommendations | `search-companies`, `get-fundamentals`, `get-inderes-estimates` |
| `aino-research` | Qualitative content: analyst reports, transcripts, filings | `search-companies`, `list-content`, `get-content`, `list-transcripts`, `get-transcript`, `list-company-documents`, `get-document`, `read-document-sections` |
| `aino-sentiment` | Market signals: insider trades, forum, calendar | `search-companies`, `list-insider-transactions`, `search-forum-topics`, `get-forum-posts`, `list-calendar-events` |
| `aino-portfolio` | Inderes' own model portfolio | `get-model-portfolio-content`, `get-model-portfolio-price`, `search-companies` |
| `aino-valuation` *(opt-in)* | Fetches BVPS, ROE history, current price; emits structured JSON for the deterministic Greenwald-Gordon engine. **Never does math itself** — the agent's job is parameter extraction with rationale, not calculation. | `search-companies`, `get-fundamentals` |
| `aino-conflict-detector` | Reads all subagent outputs and emits agreements / conflicts / isolated_claims as structured JSON | — |
| `aino-lead` | Synthesizes subagent outputs (no tools, just an LLM call over a structured prompt) | — |

**Why partition tools per agent?** A monolithic agent with all 16 MCP tools would
have too many options at every reasoning step → degraded tool-call accuracy.
Splitting by responsibility keeps each LLM context tight and each system prompt
focused. This is the highest-leverage decision in the architecture.

**Prompt preamble — current date.** `_common.load_prompt()` prepends a
`# CURRENT DATE` header (ISO + Finnish weekday) to every loaded prompt before
returning it. Without this, Gemini falls back to its training cutoff when
asked "tänään" / "tällä viikolla" — observed answers from "14.5.2025" when
the real date was 2026-05-03. The same date is also prefixed onto every
per-query user prompt in `workflows.py` and `synthesis.py` (system
instructions can lose attention in long contexts; user-prompt prefix is
read first by the model). Router's inline `_ROUTER_INSTRUCTIONS` is
intentionally exempt — routing is a classification task that doesn't need
date context.

**Prompt preamble — thought traces.** Every subagent prompt mandates a
single-line `**Ajatus:** ...` reasoning rubric at the top of its response,
explaining which tools it'll call and why. LEAD mandates a
`**💭 Perustelut:** ...` callout at the top of every synthesis describing
how it combined the subagents' outputs. The Streamlit UI styles these
distinctly (violet for subagents, amber for LEAD), surfacing the
multi-agent reasoning to the user without burying it behind tool-call
logs.

### Inderes MCP integration

Files: [`src/inderes_agent/mcp/`](src/inderes_agent/mcp/)

| File | Role |
|---|---|
| `oauth.py` | OAuth 2.0 Authorization Code + PKCE flow against Inderes' Keycloak SSO. Discovers endpoints from `https://mcp.inderes.com/.well-known/oauth-protected-resource` (RFC 9728), then `https://sso.inderes.fi/auth/realms/Inderes/.well-known/openid-configuration`. Browser opens for first-time login; tokens cached at `~/.inderes_agent/tokens.json` with `0600` permissions. Refresh token used silently on subsequent runs. |
| `inderes_client.py` | Builds `MCPStreamableHTTPTool` per agent with: (a) `allowed_tools` filtering, (b) `httpx.AsyncClient(auth=...)` with `_InderesBearerAuth` for per-request token injection, (c) `_SanitizingMCPTool` subclass that strips `$schema` and other JSON-Schema metadata that Gemini's `FunctionDeclaration` rejects, (d) `load_prompts=False` because Inderes MCP exposes only tools and the default `prompts/list` call would crash with `Method not found`. |

**Why custom OAuth instead of MAF's auth?** MAF's `MCPStreamableHTTPTool` exposes
a `header_provider` callback for tool invocations, but **not** for the
connection-time `initialize` call. The 401 happens during `initialize`, before any
tool call. So we attach auth via `httpx.AsyncClient.auth=` instead — every request
including `initialize` carries the Bearer token.

**Why eagerly trigger OAuth in `__main__.py`?** The 4–5 subagents are built
concurrently inside `asyncio.gather`. If we let OAuth trigger inside one of them,
the other three might race to start their own OAuth flows (browser opening 4
times). Calling `prefetch_token()` once at startup ensures the browser opens
exactly once and all four agents share the cached token.

**JSON-Schema sanitization.** Inderes' MCP tool schemas include JSON-Schema
metadata (`$schema`, `$id`, `$ref`, `$defs`, `$comment`). Gemini's
`google.genai.types.FunctionDeclaration` Pydantic model has `extra='forbid'` and
rejects these. `_SanitizingMCPTool` overrides `connect()` and recursively strips
those keys from each tool's cached input schema.

**Durable token storage on Streamlit Cloud.** When `INDERES_TOKENS_GIST_ID` and
`INDERES_TOKENS_GH_TOKEN` are set, the OAuth layer mirrors `tokens.json` to a
private GitHub gist on every refresh and pulls from the gist on cold start.
This solves the Streamlit Cloud failure mode where ephemeral containers lose
the local cache between restarts and the refresh-token rotation chain breaks.
A separate GitHub Actions cron — `.github/workflows/refresh-inderes-tokens.yml`
running every 15 min — performs a token refresh against Keycloak using only
the gist, with no Streamlit involvement. The cron keeps the SSO session warm
even when the app is idle for hours, so the next user query doesn't hit a
dead refresh-token. The local `tokens.json` cache and gist are kept
consistent: PR #27 changed cold-start logic to always pull the gist version
first rather than trusting a stale local file.

### Gemini client with fallback

File: [`src/inderes_agent/llm/gemini_client.py`](src/inderes_agent/llm/gemini_client.py)

`FallbackGeminiChatClient` subclasses `agent_framework_gemini.GeminiChatClient` and
overrides `get_response`. Logic:

1. Try **primary** (`gemini-3.1-flash-lite-preview` by default)
2. On `503 UNAVAILABLE` → wait `RETRY_DELAY_MS`, retry primary once
3. On second 503 OR any `429 RESOURCE_EXHAUSTED` → switch to **fallback** (`gemini-2.5-flash`) for that single request
4. Fallback gets two more attempts with 2 s and 4 s backoff
5. If all attempts exhausted → raise `QuotaExhaustedError`

The model that handled each request is recorded on `self.last_used_model`. The
workflow reads this when building `SubagentResult` so the trace and `narrative.md`
show which model handled each subagent.

Streaming and non-streaming paths are dispatched separately (streaming is wired
but not currently used by the REPL — synthesis prints the full answer at once).

**Why subclass instead of MAF middleware?** MAF middleware operates at the agent
level. We need control at the chat-client level so every LLM call goes through the
fallback wrapper regardless of which agent makes it. Subclassing is the right
seam.

### CLI

Files: [`src/inderes_agent/cli/`](src/inderes_agent/cli/)

| File | Role |
|---|---|
| `repl.py` | Interactive REPL with conversation state, slash commands, inline progress reporting. `handle_query()` is the shared per-query entry point used by both REPL and one-shot mode. |
| `render.py` | rich-formatted output: routing summary, answer (markdown), error panels, compact subagent trace. |

The REPL maintains a `ConversationState` between turns. Two key continuity
behaviors:

1. The router gets a "previous turn discussed: X" hint via `_build_context()`.
2. If the new query lacks an explicit company name but the previous turn had one, the workflow inherits it. So "and the dividend yield?" implicitly means the same company as the previous turn.

### Observability

Files: [`src/inderes_agent/observability/`](src/inderes_agent/observability/)

| File | Role |
|---|---|
| `tracing.py` | OpenTelemetry tracer with `ConsoleSpanExporter`. MAF emits spans natively; this just wires up a tracer provider. |
| `run_log.py` | `attach_console_log_handler()` adds a `FileHandler` to the root logger so HTTP/MCP/fallback logs go to `<run_dir>/console.log`. `write_run()` dumps query, routing, per-subagent, synthesis, meta to JSON files in the run directory. |
| `narrate.py` | Reads a run directory and produces `narrative.md`: routing decision → tool-call timeline → per-subagent outputs → synthesis → stats footer. Tool-call attribution is by tool name (some tools like `search-companies` are shared and marked `[shared]`). |

Per-run output structure at `~/.inderes_agent/runs/<timestamp>/`:

```
20260501-205122-776/
├── query.txt              # plain text, the user's question
├── routing.json           # {domains, companies, is_comparison, reasoning}
├── subagent-NN-<domain>.json   # {index, domain, company, model_used, error, text}
├── synthesis.txt          # plain text, lead's final answer
├── conflicts.json         # conflict-detector output (when run): agreements, conflicts, isolated_claims
├── valuation.json         # only when toggle was on: parsed agent JSON + computed Valuation per company
├── paattely.json          # LEAD's reasoning callout (when present)
├── meta.json              # {lead_model, duration_seconds, fallback_events, subagent_count, subagent_errors}
├── console.log            # HTTP/MCP/fallback log lines with ISO timestamps
└── narrative.md           # human-readable timeline (auto-generated post-run)
```

---

### Valuation engine (opt-in feature)

Files: [`src/inderes_agent/valuation/`](src/inderes_agent/valuation/) and the
`aino-valuation` agent in `agents/valuation.py`.

A deterministic Python module implementing the user's own Greenwald-Gordon hybrid
fair-value methodology. Activates when the user enables the *"Käytä vaihtoehtoista
arvonmääritystä"* sidebar toggle AND the query has explicit valuation intent
(`router.query_has_valuation_intent()`). Layered separation:

| File | Role |
|---|---|
| `engine.py` | Pure-Python valuation. Same `(BVPS, ROE, k, g, price)` always produces the same `Valuation` dataclass — no LLM dependency, no randomness, no external calls. Implements: FCF/share, FV (Gordon), EPV (Greenwald), growth multiplier (GM), Rock Bottom, dual implied values (`implied_g` holds ROE, `implied_roe` holds g), quality classification (laatu / keskinkertainen / tuhoutuva) with ±2% buffer around k, entry levels (90/80/75% of FV), safety margin. |
| `roe_selection.py` | The single source of truth for the **sustainable-ROE rule**. Trend classification (`nouseva` / `laskeva` / `vakaa` / `insufficient_history`) plus a deterministic decision: 5y_median for stable/rising trends, `min(3y_median, trend_weighted)` for falling. Used both by the agent prompt (documentation) and by the parser (validation). |
| `parser.py` | Validates `aino-valuation`'s emitted JSON before it reaches the engine. Strict on numeric ranges, `k > g` precondition, allowed `roe_version` values, and the sustainable-ROE rule (recomputed from raw history; agent can't silently mis-compute medians). Includes Levenshtein-≤2 typo tolerance for `*_rationale` fields with sibling protection (so `g_rationale` cannot absorb `k_rationale`'s value). |

The agent is intentionally minimal: fetch data via MCP, choose `k` and `g` with
written rationale, declare which ROE rule applies, and emit JSON. **All math
happens in the deterministic engine** — this prevents LLM arithmetic errors from
reaching the user. Validated against `Arvonmääritys2023.xlsx` for 10 hand-picked
Finnish companies (laatu / tuhoutuva mix), with FV/EPV/GV matching to within
0.02€ (`tests/valuation/test_excel_parity.py`).

**Tool-call guard at the orchestration boundary**

Production run `20260508-205057-769` ("entäs jos roe olisi 13%") demonstrated a
trust-killer failure mode: Flash Lite decided the prior conversation turn was
"enough context" and emitted a fully-formed JSON output with **zero MCP calls**
— hallucinating company_id, current price, and ROE history. Engine math then
operated on phantom inputs and produced a confident but fabricated +18.2 %
safety margin.

Defense: in `synthesis._process_valuation_subagents`, count `get-fundamentals`
calls *before* invoking the parser. Zero calls → reject as hallucination,
route to the LEAD-prompt's *Tila B* with an honest error message. Prompt-level
"always fetch fresh data" instructions don't suffice — Flash Lite occasionally
skips MCP regardless. Structural enforcement at the boundary is the only
reliable defense.

**Three-state LEAD synthesis**

The LEAD prompt has three explicit modes for how to integrate valuation
output (selected by inspecting the formatted block):

- **A — Toggle off**: block is the placeholder `_user did not enable...`.
  LEAD ignores the valuation guidance entirely, default flow unchanged.
- **B — Toggle on, parse error**: block contains `parse_error` text. LEAD
  emits a brief honest "skipped" message, **never** hand-computes Gordon
  math from agent's parameters even when visible in the trace.
- **C — Toggle on, success**: block contains `Engine: ...` lines. LEAD
  produces a 4-section structure (Yhteenveto / Inderesin näkemys / Oma
  arvonmääritys / Vertailu) plus a static methodology infobox.

Edge-case warnings are injected into the block when |safety_margin| > 100%
(parameters are clearly mismatched with market price) or when quality is
*tuhoutuva* due to manual_override (LEAD softens the verdict, presenting it
as a scenario rather than a verdict).

---

## Run lifecycle

A single `python -m inderes_agent "..."` invocation:

```
1. main()
   ├─ load_dotenv()
   ├─ configure_logging()
   ├─ setup_tracing()
   └─ prefetch_token()          ← OAuth flow if no cached token, else silent refresh

2. asyncio.run(_one_shot(question))
   └─ handle_query()
      ├─ new_run_dir()           ← creates ~/.inderes_agent/runs/<timestamp>/
      ├─ attach_console_log_handler()
      │
      ├─ classify_query()        ← Router LLM call → QueryClassification
      │     emit:  "→ domains: [...]  · companies: [...]"
      │
      ├─ run_workflow()
      │   For each (domain, company) pair, in parallel (capped by semaphore):
      │       Build chat client (FallbackGeminiChatClient)
      │       Build MCP tool (_SanitizingMCPTool with BearerAuth)
      │       async with Agent(...) as a:
      │           result = await a.run(prompt)
      │             [AFC loop]: Gemini decides tool → SDK calls MCP → result
      │             fed back → repeats until Gemini returns final text
      │       Capture text, model_used, errors → SubagentResult
      │     emit:  "·   <domain>: ok|ERROR (<model>)"
      │
      ├─ synthesize()            ← Lead LLM call over structured prompt of
      │                             subagent outputs → final answer text
      │
      ├─ render.render_answer()  ← print to user (rich markdown)
      │
      ├─ write_run()             ← persist query.txt, routing.json,
      │                             subagent-NN-*.json, synthesis.txt,
      │                             meta.json
      │
      ├─ write_narrative()       ← parse console.log + JSONs → narrative.md
      │
      └─ render compact trace + paths to logs

3. detach_console_log_handler() (in finally block, always)
```

If anything raises a `QuotaExhaustedError` or other exception, it's caught and
rendered in a red panel, and the per-run directory still gets the partial logs.

---

## Key design decisions

Each was made deliberately and is worth understanding before you change it.

### 1. Per-subagent LLM call with own tool subset

Trades concurrency cost for tool-call accuracy. A single agent with 16 tools makes
more wrong choices at every step than 4 agents with 3–8 tools each. The
multiplicative cost (4× LLM calls) is offset by fewer wasted iterations and
clearer per-agent prompts.

### 2. Lead has no tools

Forces the lead to synthesize from what subagents returned (text in prompt) rather
than re-querying. Keeps the lead fast, prevents duplicating MCP calls, and forces
the team's "knowledge" to flow through one bottleneck — the subagent output text.
This makes debugging much easier (you can read exactly what the lead saw).

### 3. Structured-output router instead of handoff/group-chat

Gemini's structured output is reliable and cheap. The classification is fully
deterministic given the prompt and few-shot examples. No need for a multi-turn
handoff dance. Could be replaced with a smarter classifier if requirements grow,
but for ~7 domain types the current approach works.

### 4. Custom OAuth flow with token cache

MAF doesn't bridge MCP OAuth to chat-client requests. We do the dance ourselves
with PKCE, cache tokens to `~/.inderes_agent/tokens.json`, and inject Bearer
per-request via `httpx.Auth`. The cache file is `0600` (owner-read-write only).

### 5. JSON-Schema sanitization wrapper

Inderes' MCP tool schemas include JSON-Schema metadata that Gemini's
`FunctionDeclaration` validator rejects. We subclass `MCPStreamableHTTPTool`,
intercept `connect()`, and strip those keys recursively. If Gemini relaxes its
validation in a future version, this can be removed.

### 6. `load_prompts=False` on every MCP tool

Inderes MCP doesn't implement `prompts/list`. With the default `load_prompts=True`,
MAF calls `prompts/list` during `initialize` and the server returns "Method not
found", crashing the connection. Disabling prompt loading sidesteps this.

### 7. Per-run directory of files (not a database)

A single SQLite or JSONL log would be more queryable, but per-run directories are
dramatically easier to read by hand, share by zipping, and grep through. Each run
is self-contained. Trade-off: large numbers of runs accumulate inodes.

### 8. `narrative.md` parses from `console.log`

The narrative needs per-tool-call timing, but recording that explicitly would
require MAF middleware on every agent. Parsing the existing `console.log`
(which captures `agent_framework`'s "Function name: X" / "Function X succeeded"
messages with timestamps) is simpler and works.

Limitation: tool-call attribution to a specific subagent is heuristic — a tool
like `search-companies` is allowed by multiple agents and gets marked `[shared]`
in the timeline. For unambiguous tools (`get-fundamentals`, `list-content`, etc.)
attribution is exact.

### 9. ARM-native Python required on Apple Silicon

Intel Python via Rosetta is ~10× slower for cold imports. The README and
TROUBLESHOOTING both call this out; the install instructions use `uv` with
`--python-preference only-managed` to guarantee an ARM-native interpreter.

### 10. Disk space matters

Below ~10 % free disk on macOS, APFS becomes unstable: failed `mmap` calls,
truncated reads, missing files. This manifests as inscrutable git/Python errors.
The README's pre-flight checklist mandates 20 GB free as a guardrail.

---

## Trust + reliability defenses (post-2026-05-10)

Three layers protecting the system against fabricated subagent output,
all added or strengthened in the 2026-05-09 sprint after the
[Vincit fabrication case](docs/sprint_lessons_2026-05-09.md):

### 1. Prompt-side HARD GATE (each subagent's `.md`)

Every subagent prompt now opens with an explicit **HARD GATE** block
listing the MCP tool calls it MUST execute before emitting output:

```markdown
## ⛔ HARD GATE — MCP TOOL CALLS ARE MANDATORY ⛔

Before you emit any output, you MUST execute these tool calls:
1. search-companies(query) — resolve id
2. <agent-specific tools>

A response with ZERO MCP tool calls is automatically rejected as
fabrication. Numbers/quotes from training memory are FORBIDDEN.
```

The block is intentionally placed at the TOP of the prompt so Flash
Lite reads it before the rest of the (often 200+ line) instructions.

### 2. Runtime fabrication guard (`workflows.py`)

`_detect_fabrication()` runs at the dispatch boundary on every
subagent result. If a subagent emits ≥300 chars of domain-loaded
text (containing markers like `€`, `tavoitehint`, `sources:`, etc.)
but ZERO MCP tool calls, the text is replaced with empty + error:

```python
result.error = "fabricated_no_tool_calls: agent emitted N chars ..."
result.text = ""
```

Downstream consumers (LEAD prompt assembly, conflict detector,
forensic logs) see the failure honestly. `synthesize()` further
short-circuits to a fixed *"En löytänyt yhtiötä X..."* answer when
ALL subagents fail this way — no LEAD call, no fabricated synthesis.

### 3. Eval foundation (`evals/`)

Three-tier scaffold making invisible bugs visible:

- **Tier 0** (`scripts/build_runs_index.py` → SQLite): fast SQL
  across every historical run for diagnostics.
- **Tier 1** (`evals/golden.yaml` + `evals/runner.py` +
  `evals/judge.py`): 7 golden cases each tied to a real
  weakness; hard (deterministic) + soft (Gemini-Pro judge)
  assertions per case. `evals/results/baseline_*/` committed
  as the regression contract.
- **Tier 2 (planned)**: Supabase migration so judgments are
  queryable cross-device.
- **Tier 3 (planned)**: autonomous nightly cron with
  prompts-only auto-fixes to `auto-fixes/yyyy-mm-dd` branch.

The combination implements OWASP Agentic Top 10 #T3 (tool misuse
/ hallucinated outputs) defense at three layers: prompt-side,
runtime, and post-hoc measurement. The judge model selection
(Gemini 2.5 Pro) is benchmark-backed via Vectara HHEM v2 and
RewardBench 2 — see `evals/judge_selection.md`.

---

## What this is and isn't

This is an **orchestrator-worker multi-agent system** in the loose, current-industry
sense — multiple LLM-driven agents with specialized roles and tool subsets,
coordinated by a lead. It is **not**:

- A peer-to-peer agent network with dynamic delegation (the lead reads each
  subagent's output, but they don't talk to each other).
- A self-organizing or self-improving system (no agent rewrites another's
  prompt or workflow).
- A planner-and-replanner like Magentic-One (the workflow is fixed at routing
  time; no re-planning after subagent failures).

If you want a richer pattern (group chat, handoff with tool approvals,
Magentic-One-style dynamic planning), Microsoft Agent Framework provides those
builders out of the box (`agent_framework.orchestrations`). The decision to use a
static fan-out + synthesis pattern here is intentional: predictable, debuggable,
fits free-tier quotas, and is enough for this use case.

---

## Extending the system

### Adding a new subagent

1. Add a system prompt in `src/inderes_agent/agents/prompts/<role>.md` describing
   the agent's role, tools, workflow, and output format.
2. Define the MCP tool subset in `src/inderes_agent/mcp/inderes_client.py`
   (e.g. `MY_DOMAIN_TOOLS = (...)`).
3. Add a factory in `src/inderes_agent/agents/<role>.py`:
   ```python
   def build_my_role_agent() -> Agent:
       return Agent(
           client=build_chat_client(),
           name="aino-my-role",
           instructions=load_prompt("my_role.md"),
           tools=build_mcp_tool(name="inderes-my-role", allowed=MY_DOMAIN_TOOLS),
       )
   ```
4. Export it from `src/inderes_agent/agents/__init__.py`.
5. Add the new domain to the `Domain` enum in
   `src/inderes_agent/orchestration/router.py`, and add a few-shot example to
   the router prompt.
6. Register the builder in `_AGENT_BUILDERS` in
   `src/inderes_agent/orchestration/workflows.py`.
7. Add a tool-attribution mapping in `src/inderes_agent/observability/narrate.py`
   so the timeline correctly attributes the new tools.

### Pointing at a different MCP server

If you want to repurpose the system for a different MCP server (Linear, GitHub,
your company's internal MCP):

1. Update `INDERES_MCP_URL` and `INDERES_MCP_CLIENT_ID` in `.env` (or rename them).
2. Update OAuth discovery in `src/inderes_agent/mcp/oauth.py` if the server uses a
   different auth scheme (e.g. API key via `header_provider` is simpler than PKCE).
3. Replace the tool partitioning constants and prompts to match the new domain.

The Gemini fallback wrapper, observability layer, and CLI infrastructure are
all MCP-agnostic.

### Upgrading the lead model

Synthesis quality is bounded by the model. To use a smarter model for the lead
only (cheap because the lead does just one call per query):

```python
# in src/inderes_agent/agents/lead.py
def build_lead_agent() -> Agent:
    return Agent(
        client=build_chat_client(
            settings_override=Settings(
                PRIMARY_MODEL="gemini-2.5-pro",
                FALLBACK_MODEL="gemini-2.5-flash",
            ),
        ),
        ...
    )
```

(You'll need to add a `settings_override` parameter to `build_chat_client()` —
it's a simple addition.)

This requires paid-tier Gemini, but adds only a few cents per query.
