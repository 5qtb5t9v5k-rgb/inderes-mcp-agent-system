# Changelog

A short narrative of the build journey — design decisions and the issues that drove each one. Useful for understanding why the code looks the way it does.

## 0.1.0 — 2026-05-01 (initial build)

### Core architecture
- 5-agent system on Microsoft Agent Framework 1.0+: lead orchestrator + 4 specialized subagents (quant, research, sentiment, portfolio)
- Each subagent gets a focused subset of Inderes MCP tools (3–8 tools each, not all 16) — improves tool-call accuracy
- Lead has no tools; synthesizes subagent outputs from text-in-prompt
- Router uses structured-output Gemini call (JSON) with few-shot examples
- Workflow uses `asyncio.gather` + `Semaphore(MAX_CONCURRENT_AGENTS)` instead of MAF's `ConcurrentBuilder` — runtime-decided fan-out and hard quota cap

### Free-tier-realistic Gemini fallback
- Primary: `gemini-3.1-flash-lite-preview` (500 RPD)
- Fallback: `gemini-2.5-flash` (20 RPD, used on persistent 503 / any 429)
- Fallback wrapper: 1 retry on primary with `RETRY_DELAY_MS`, then switch to fallback with 2 attempts (2s/4s backoff)
- `last_used_model` recorded per chat client for `/trace` and `narrative.md`
- No reference to `gemini-2.5-pro` anywhere — quota is zero on free tier

### Inderes OAuth integration
- MAF's `MCPStreamableHTTPTool.header_provider` only fires for tool invocations — **not** for `initialize`. So the first POST got `401` until we attached auth at the http_client level.
- Implemented OAuth Authorization Code + PKCE flow against Keycloak (`oauth.py`)
  - Discovers endpoints from `/.well-known/oauth-protected-resource` then `/.well-known/openid-configuration`
  - Localhost callback server handles the redirect
  - Tokens cached at `~/.inderes_agent/tokens.json` with `0600` permissions
  - Refresh token used silently on subsequent runs
- `_InderesBearerAuth(httpx.Auth)` injects the latest cached token per request — handles refresh-on-expiry transparently
- `prefetch_token()` called eagerly in `__main__.py` so 4 parallel agents share the cached token instead of racing 4 OAuth flows

### MCP compatibility shims
- **`load_prompts=False`** on every MCP tool: Inderes MCP doesn't implement `prompts/list`. Default `load_prompts=True` → `Method not found` → connection crash.
- **`_SanitizingMCPTool`** subclass: strips `$schema`, `$id`, `$ref`, `$defs`, `$comment` from tool input schemas after `connect()`. Inderes' MCP schemas include these JSON-Schema metadata fields; Gemini's `FunctionDeclaration` Pydantic validator rejects them with `Extra inputs are not permitted`.

### Per-run observability
- Every query writes `~/.inderes_agent/runs/<timestamp>/` with: `query.txt`, `routing.json`, `subagent-NN-<domain>.json`, `synthesis.txt`, `meta.json`, `console.log`, `narrative.md`
- `narrate.py` parses `console.log` (extracts function-call timings) + JSON files → human-readable markdown narrative
- REPL gains `/explain`, `/last`, `/runs` commands; one-shot mode auto-prints compact subagent trace + paths to logs

### CLI / DX
- `rich` for terminal output (markdown answers, tables, error panels)
- `prompt_toolkit` for REPL input with history
- Inline progress lines per phase ("reitittäjä päättää…", "subagentit ajetaan…", per-subagent done) so users don't think the system is hung
- `scripts/diag.py` standalone diagnostic that probes Gemini + MCP independently
- `scripts/explain.py` regenerates a narrative for any past run

### Build environment
- Python 3.11+ required (we use 3.13.13 in dev via uv)
- `uv` recommended over plain pip — much faster install, manages ARM-native Python
- `agent-framework-gemini` requires `--pre` flag (alpha-versioned on PyPI)
- ARM-native Python required on Apple Silicon — Intel Python via Rosetta is ~10× slower for cold imports

### Tests
- 13 unit tests cover: router JSON parsing, classification schema validation, fallback retry/quota semantics, workflow per-company fan-out, concurrency cap
- End-to-end tests against real Gemini + Inderes MCP are not in CI (require credentials)

### Known caveats
- Synthesis quality bounded by lite-tier model. Paid tier could upgrade just the lead to `gemini-2.5-pro` for a few €/month if needed.
- During Gemini-side capacity spikes, both primary and fallback can return 503 simultaneously — system gracefully degrades (lead synthesizes from whichever subagents succeeded) but the failed subagents return empty.
- Tool-call attribution in `narrative.md` is heuristic (some tools like `search-companies` are shared by multiple agents) — most calls attribute correctly via tool name.
