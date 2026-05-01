# Troubleshooting

Issues encountered while building this system, with the diagnosis and fix for each. Read this if something breaks.

---

## Imports take 30–60 seconds on Apple Silicon

**Symptom**: `python -m inderes_agent ...` hangs at import for 30–60+ seconds, even on simple commands. Pressing Ctrl-C shows the traceback inside `markdown_it`, `google.genai`, or `attrs` — never the actual app code.

**Diagnosis**:
```bash
uname -m                # arm64? You're on Apple Silicon
which python            # /usr/local/... means Intel Homebrew
python -c "import platform; print(platform.machine())"   # x86_64 = Intel via Rosetta
```

If `uname -m` says `arm64` but `python` reports `x86_64`, you're running Intel Python through Rosetta 2 translation. Every dynamic library load (`.so`, `.dylib`) is translated on the fly → 10× slower cold imports.

**Fix**: Install ARM-native Python via `uv` and recreate the venv:
```bash
deactivate                       # leave broken venv
/bin/rm -rf ./.venv              # plain `rm -rf .venv` errors in some zsh configs
uv python install 3.13           # downloads ARM-native CPython
uv venv --python-preference only-managed --python 3.13
source .venv/bin/activate
python -c "import platform; print(platform.machine())"   # should print arm64
uv pip install --pre -e .
```

**Verification**: cold-import benchmark should show roughly 1–2 s wall-clock with high CPU%, not 7+ s with 7% CPU:
```bash
time python -c "from agent_framework_gemini import GeminiChatClient"
```

---

## `pip install -e .` fails: "Could not find a version that satisfies the requirement agent-framework-gemini>=1.0"

**Diagnosis**: `agent-framework-gemini` is published only as a pre-release on PyPI (e.g., `1.0.0a260429`). Plain `pip install` excludes pre-releases by default.

**Fix**: Use `--pre`:
```bash
uv pip install --pre -e .
# or
pip install --pre -e .
```

---

## `zsh: unknown file attribute: v` when running `rm -rf .venv`

**Diagnosis**: Some zsh configurations interpret `-rf` as glob qualifier syntax when the next argument starts with `.`.

**Fix**: Use the full path to `rm`:
```bash
/bin/rm -rf ./.venv
```

---

## Inderes MCP returns 401 Unauthorized

**Symptom**:
```
HTTP Request: POST https://mcp.inderes.com "HTTP/1.1 401 Unauthorized"
McpError('Method not found')   # or some other crash inside MAF's MCP layer
```

**Diagnosis**: The MCP server requires a Bearer token from Inderes' Keycloak SSO. MAF's `MCPStreamableHTTPTool.header_provider` is **only called for tool invocations**, not for the connection-time `initialize` call. So the first POST has no `Authorization` header.

**Fix**: This is already handled in `src/inderes_agent/mcp/inderes_client.py` — we attach auth via `httpx.AsyncClient(auth=BearerAuth(...))` so every request (including `initialize`) carries the token. If you're still getting 401, your token might be invalid or expired — see the next entry.

---

## "invalid_grant: Session not active" / OAuth keeps re-prompting

**Symptom**: Every run opens the browser even though you logged in earlier:
```
refresh_failed status=400 body={"error":"invalid_grant","error_description":"Session not active"}
```

**Diagnosis**: Keycloak refresh tokens have a session lifetime; if you don't use the agent for ~30 days (or your Inderes Premium subscription state changes), the refresh token becomes invalid and a fresh login is required.

**Fix**: Just complete the browser flow again. The new tokens get cached at `~/.inderes_agent/tokens.json`. To force a fresh login at any time:
```bash
rm ~/.inderes_agent/tokens.json
```

---

## MCP error: `('Failed to enter context manager.', McpError('Method not found'))`

**Diagnosis**: MAF's `MCPStreamableHTTPTool` calls `prompts/list` during `initialize` by default (`load_prompts=True`). Inderes MCP exposes only tools, not prompts → server responds "Method not found" → MCP context manager fails to enter → agent crashes before any tool call.

**Fix**: Set `load_prompts=False` when constructing the MCP tool. Already applied in `src/inderes_agent/mcp/inderes_client.py`:
```python
return _SanitizingMCPTool(
    name=name,
    url=...,
    allowed_tools=...,
    load_prompts=False,    # ← this
    ...
)
```

---

## `1 validation error for FunctionDeclaration / parameters.$schema / Extra inputs are not permitted`

**Diagnosis**: Inderes MCP tool schemas include `$schema: "http://json-schema.org/..."` (and similar JSON-Schema metadata). Google's `genai.types.FunctionDeclaration` Pydantic model has `extra='forbid'` and rejects `$schema`, `$id`, `$ref`, `$defs`, `$comment`.

**Fix**: We subclass `MCPStreamableHTTPTool` and override `connect()` to strip these keys recursively from each tool's cached input schema. See `_SanitizingMCPTool` and `_scrub_schema_in_place()` in `src/inderes_agent/mcp/inderes_client.py`.

---

## 503 errors from Gemini

**Symptom**:
```
primary_model_503_retry model=gemini-3.1-flash-lite-preview
falling_back_to_secondary primary=gemini-3.1-flash-lite-preview fallback=gemini-2.5-flash
fallback_503_retry attempt=1
```

…and sometimes the subagent ends in `ERROR 503 UNAVAILABLE`.

**Diagnosis**: Gemini's free-tier *and* paid-tier capacity is occasionally exhausted globally. This is a **service-side** issue, not a quota issue. The fallback wrapper retries primary once → falls back to secondary → retries fallback twice. If both models return 503 across all those attempts, the subagent fails.

**Fix**:
1. **Wait a few minutes and retry** — these spikes are usually short-lived.
2. **Switch to paid tier** ([Google AI Studio billing](https://aistudio.google.com/app/apikey)) if you haven't. Paid users get priority + higher quotas. Costs ~$0.005–0.02/query.
3. **Reduce concurrent agents**: `MAX_CONCURRENT_AGENTS=1` in `.env` makes single-agent queries less likely to coincide with capacity spikes (at the cost of slower comparisons).
4. **Accept graceful degradation**: even when 1–2 subagents fail, the lead still synthesizes a useful answer from whatever did succeed. The `subagent trace` and `narrative.md` show exactly which agent failed.

**Important**: 503 ≠ quota exhaustion. Quota errors are 429, not 503. The fallback wrapper handles both.

---

## Free-tier daily quota exhausted (429 RESOURCE_EXHAUSTED)

**Symptom**:
```
QuotaExhaustedError: Daily Gemini quota exhausted on both primary and fallback models. Try again tomorrow or upgrade to paid tier.
```

**Diagnosis**: Free-tier daily limits are very tight:
- `gemini-3.1-flash-lite-preview` (primary): 500 requests/day
- `gemini-2.5-flash` (fallback): **20 requests/day**

A single multi-domain query can burn 8–15 LLM calls. ~30 queries/day is realistic on free tier.

**Fix**:
1. **Wait until midnight Pacific Time** (10:00 Helsinki time) for daily reset.
2. **Switch to paid tier** for production use.
3. **Test with simpler single-domain queries** while developing — they use fewer LLM calls.

Inspect your usage at https://aistudio.google.com/app/usage.

---

## Module not found: `inderes_agent` (after editable install)

**Symptom**:
```
/.../python: No module named inderes_agent
```

But `ls .venv/lib/python3.13/site-packages/ | grep inderes` shows the dist-info directory exists.

**Diagnosis**: The `_editable_impl_inderes_agent.pth` file in site-packages may be missing its trailing newline, which Python's `site.py` requires to register the source directory.

**Fix**: Reinstall:
```bash
uv pip install --force-reinstall --pre -e .
```

---

## "ModuleNotFoundError: No module named 'inderes_agent'" when not in venv

**Symptom**: You forgot to activate the venv.

**Fix**:
```bash
source .venv/bin/activate
# verify
which python    # should be ./.venv/bin/python
```

---

## "command not found: #" in zsh

**Symptom**: You pasted multiple lines starting with `#`:
```
# poista vanha venv
deactivate
zsh: command not found: #
```

**Diagnosis**: Pasting multiple lines with comments confuses zsh in some cases — it doesn't always treat `#` as a comment when pasted.

**Fix**: Paste one command at a time, or strip the `#` lines before pasting.

---

## Agent runs forever without printing anything

**Symptom**: After `python -m inderes_agent "..."` you see no output for a long time, then panic and Ctrl-C.

**Diagnosis**: First cold-start imports take 5–10 seconds even on ARM-native Python. The router LLM call adds another 5–15 seconds. The first MCP `initialize` adds another 1–2 seconds. Total time to first visible output: 10–30 seconds is normal.

**Fix**: **Be patient.** Don't Ctrl-C unless you've waited at least **60 seconds** without any output. The progress lines (`reitittäjä päättää…`, `subagentit ajetaan…`, etc.) appear once each phase actually starts. If you really want minute-by-minute confirmation, run the diagnostic:
```bash
python scripts/diag.py
```
which probes Gemini and MCP independently with timing on each step.

---

## Where are my run logs?

`~/.inderes_agent/runs/<timestamp>/`. Per-run directory contains:
- `query.txt` — what you asked
- `routing.json` — the router's classification
- `subagent-NN-<domain>.json` — full output of each subagent
- `synthesis.txt` — lead's final answer
- `meta.json` — duration, fallback events
- `console.log` — raw stderr-style log
- `narrative.md` — human-readable summary (auto-generated)

Quick access:
```bash
ls -1t ~/.inderes_agent/runs/ | head -5            # 5 most recent
python scripts/explain.py                          # narrative for latest
python scripts/explain.py 20260501-203226-880     # narrative for specific
```

In the REPL: `/last`, `/runs`, `/explain`.

---

## Where is my OAuth token?

`~/.inderes_agent/tokens.json` (file mode `0600`). To force re-login: `rm ~/.inderes_agent/tokens.json`. To inspect:
```bash
cat ~/.inderes_agent/tokens.json | jq
```
