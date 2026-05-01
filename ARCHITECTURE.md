# Architecture

Deep walkthrough of `inderes-research-agent` — what each piece does, why it exists, and how the pieces fit together.

---

## 30-second mental model

A user asks a natural-language question about a Nordic stock. A **router** classifies it. A **fan-out workflow** spawns 1–4 **specialized subagents** in parallel, each with its own focused subset of Inderes MCP tools. Each subagent runs an LLM tool-calling loop, gathers data from Inderes, and returns a structured text block. A **lead** synthesizes those blocks into one final answer. Everything that happened gets recorded to disk as a **narrative** for later inspection.

```
User question
    ↓
Router (Gemini, JSON output)
    ↓
Workflow (asyncio.gather, MAX_CONCURRENT_AGENTS semaphore)
    ↓
Subagents in parallel (each: Gemini + AFC loop + MCP tool subset)
    ↓
Lead synthesis (Gemini, no tools, reads subagent outputs as text)
    ↓
Final answer + narrative.md persisted
```

---

## Component map

### Routing & orchestration — `orchestration/`

| File | Role |
|---|---|
| `router.py` | One Gemini call with structured-output JSON prompt → `QueryClassification(domains, companies, is_comparison, reasoning)`. Few-shot examples in the prompt drive consistency. |
| `workflows.py` | Spawns subagents per the classification. `asyncio.Semaphore(MAX_CONCURRENT_AGENTS)` caps parallelism. For comparisons (N>1 companies × multi-domain), fans out per-company per-domain. |
| `synthesis.py` | Builds a structured prompt from subagent outputs and feeds it to the lead agent. |

**Why `asyncio.gather` instead of MAF's `ConcurrentBuilder`?** Three reasons: (1) per-company fan-out for comparisons must be decided at runtime; (2) free-tier quota requires a hard concurrency cap (semaphore); (3) the orchestration logic is short enough that direct asyncio is more readable than wrapping it in MAF's builder API. We retain MAF's per-agent infrastructure (chat client + MCP tool + AFC loop), just not its orchestration layer.

### Agents — `agents/`

Five `Agent` instances built via factory functions. Each gets:

- A **system prompt** (`agents/prompts/<role>.md`) that tells it its role, the available tools, the workflow, and the output format
- A **chat client** (the `FallbackGeminiChatClient`)
- A **filtered MCP tool** (only the subset of Inderes tools relevant to its specialty)

| Agent | Purpose | MCP tools |
|---|---|---|
| `aino-quant` | Numerical analysis (P/E, ROE, target prices, recommendations) | `search-companies`, `get-fundamentals`, `get-inderes-estimates` |
| `aino-research` | Qualitative content from Inderes (analyst reports, transcripts, filings) | `search-companies`, `list-content`, `get-content`, `list-transcripts`, `get-transcript`, `list-company-documents`, `get-document`, `read-document-sections` |
| `aino-sentiment` | Market signals (insider trades, forum, calendar) | `search-companies`, `list-insider-transactions`, `search-forum-topics`, `get-forum-posts`, `list-calendar-events` |
| `aino-portfolio` | Inderes' own model portfolio | `get-model-portfolio-content`, `get-model-portfolio-price`, `search-companies` |
| `aino-lead` | Synthesizes subagent outputs (no tools, just an LLM call over a structured prompt) | — |

**Why partition tools per agent?** A monolithic agent with all 16 MCP tools would have too many options at every step → degraded tool-call accuracy. Splitting by responsibility makes each LLM context tight and keeps each system prompt focused.

### Inderes MCP integration — `mcp/`

| File | Role |
|---|---|
| `oauth.py` | OAuth 2.0 Authorization Code + PKCE flow against Keycloak. Discovers endpoints from `https://mcp.inderes.com/.well-known/oauth-protected-resource`. Browser opens for first-time login; tokens cached at `~/.inderes_agent/tokens.json` with `0600` permissions. Refresh token used silently on subsequent runs. |
| `inderes_client.py` | Builds `MCPStreamableHTTPTool` per agent with: (a) `allowed_tools` filtering, (b) `httpx.AsyncClient` with custom `BearerAuth` for per-request token injection, (c) `_SanitizingMCPTool` subclass that strips `$schema` and other JSON-Schema metadata that Gemini's `FunctionDeclaration` rejects, (d) `load_prompts=False` because Inderes MCP exposes only tools (not prompts) and the default `prompts/list` call would crash with `Method not found`. |

**Why custom OAuth instead of MAF's auth?** MAF's `MCPStreamableHTTPTool` exposes `header_provider` (per-tool-call) but no auth provider for the connection-time `initialize` call. The 401 happens during `initialize`, before any tool call, so we attach auth via `httpx.AsyncClient.auth=` instead. This way every request — including `initialize` — has the Bearer token.

**Why eagerly trigger OAuth in `__main__.py`?** The 4 subagents are built concurrently inside `asyncio.gather`. If we let OAuth trigger inside one of them, the other 3 might race to start their own OAuth flows. Calling `prefetch_token()` once at startup ensures the browser opens exactly once and all 4 agents share the cached token.

### Gemini client with fallback — `llm/gemini_client.py`

`FallbackGeminiChatClient` subclasses `agent_framework_gemini.GeminiChatClient` and overrides `get_response`. Logic:

1. Try **primary** (`gemini-3.1-flash-lite-preview`)
2. On `503 UNAVAILABLE` → wait `RETRY_DELAY_MS`, retry primary once
3. On second 503 OR any `429 RESOURCE_EXHAUSTED` → switch to **fallback** (`gemini-2.5-flash`) for that single request
4. Fallback gets two more attempts with 2s/4s backoff
5. If both exhausted → raise `QuotaExhaustedError`

The model that handled each request is recorded on `self.last_used_model` for `/trace` and `narrative.md`.

**Why subclass instead of middleware?** MAF middleware operates at the agent level. We need control at the chat-client level — every LLM call regardless of which agent makes it.

### CLI — `cli/`

| File | Role |
|---|---|
| `repl.py` | Interactive REPL, slash commands (`/help`, `/explain`, `/trace`, `/runs`, `/last`, `/clear`, `/agents`, `/exit`), inline progress reporting, conversation state |
| `render.py` | rich-formatted output: routing summary, answer (markdown), error panels, compact subagent trace |

The REPL maintains a `ConversationState` between turns. The router gets a "previous turn discussed: X" hint, and the workflow inherits company context if the new query lacks an explicit name (so "and the dividend yield?" implicitly means the same company as the previous turn).

### Observability — `observability/`

| File | Role |
|---|---|
| `tracing.py` | OpenTelemetry tracer with `ConsoleSpanExporter`. MAF emits spans natively; this just wires them up. |
| `run_log.py` | `attach_console_log_handler()` adds a `FileHandler` to the root logger so HTTP/MCP/fallback logs go to `console.log`. `write_run()` dumps query, routing, per-subagent, synthesis, meta to JSON files. |
| `narrate.py` | Reads a run directory and produces a markdown narrative: routing decision → tool-call timeline → per-subagent outputs → synthesis → stats. |

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
      │
      ├─ run_workflow()          ← For each (domain, company): build agent, run, collect result
      │   └─ Per agent, in parallel (capped by semaphore):
      │       ├─ Build chat client (FallbackGeminiChatClient)
      │       ├─ Build MCP tool (_SanitizingMCPTool with BearerAuth)
      │       ├─ async with Agent(...) as a:
      │       │     └─ result = await a.run(prompt)
      │       │           ↓
      │       │     [AFC loop]: Gemini decides tool → SDK calls MCP → result fed back
      │       │     until Gemini returns final text
      │       └─ Capture text, model_used, errors → SubagentResult
      │
      ├─ synthesize()            ← Lead LLM call over structured prompt of subagent outputs
      │
      ├─ render.render_answer()  ← Print to user
      │
      ├─ write_run()             ← Persist query.txt, routing.json, subagent-NN-*.json,
      │                             synthesis.txt, meta.json
      │
      ├─ write_narrative()       ← Combine the above + parse console.log → narrative.md
      │
      └─ render compact trace + paths to logs
```

---

## Key design decisions

### 1. Per-subagent LLM call with own tool subset
Trades concurrency cost for tool-call accuracy. A single agent with 16 tools makes more wrong choices than 4 agents with 3–8 tools each.

### 2. Lead has no tools
Forces lead to synthesize from what subagents returned (text in prompt) rather than re-querying. Keeps lead fast and prevents duplicating MCP calls.

### 3. Structured-output router instead of handoff/group-chat
Gemini's structured output is reliable and cheap. The classification is fully deterministic given the prompt and few-shot examples. No need for a multi-turn handoff dance.

### 4. Custom OAuth flow with token cache
MAF doesn't bridge MCP OAuth to chat-client requests. We do the dance ourselves with PKCE, cache tokens to `~/.inderes_agent/tokens.json`, and inject Bearer per-request via `httpx.Auth`.

### 5. JSON-Schema sanitization wrapper
Inderes MCP tool schemas include `$schema` and other JSON-Schema metadata. Gemini's `FunctionDeclaration` validator rejects these as `extra_forbidden`. We subclass `MCPStreamableHTTPTool`, intercept its `connect()`, and strip those keys recursively from each tool's cached input schema.

### 6. `load_prompts=False` on every MCP tool
Inderes MCP doesn't implement `prompts/list`. With the default `load_prompts=True`, MAF calls it during `initialize` and the server returns "Method not found", crashing the connection. Disabling prompt loading sidesteps this.

### 7. Per-run directory of files (not a database)
A single SQLite or JSONL log would be more queryable, but per-run directories are dramatically easier to read by hand, share by zipping, and grep through. Each run is self-contained.

### 8. `narrative.md` parses from `console.log`
The narrative needs per-tool-call timing, but recording that explicitly would require MAF middleware on every agent. Parsing the existing `console.log` (which captures `agent_framework`'s "Function name: X" / "Function X succeeded" messages with timestamps) is simpler and works.

### 9. ARM-native Python required on Apple Silicon
Intel Python via Rosetta is 10× slower for cold imports. The README and TROUBLESHOOTING both call this out; the install steps use `uv` with `--python-preference only-managed` to guarantee an ARM-native interpreter.

---

## What this is and isn't

This is an **orchestrator-worker multi-agent system** in the loose, current-industry sense — multiple LLM-driven agents with specialized roles and tool subsets, coordinated by a lead. It is **not** a peer-to-peer agent network with dynamic delegation, shared memory, or self-organization. The agents don't talk to each other; the lead reads each one's output as text in its prompt.

If you want a richer pattern (group chat, handoff with tool approvals, Magentic-One-style dynamic planning), Microsoft Agent Framework provides those builders out of the box (`agent_framework.orchestrations`). The decision to use a static fan-out + synthesis pattern here is intentional: it's predictable, debuggable, fits free-tier quotas, and is enough for this use case.
