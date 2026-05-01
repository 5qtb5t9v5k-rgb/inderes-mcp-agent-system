# Troubleshooting

Every issue encountered while building and running this system, with the diagnosis
and fix for each. Read this when something breaks.

## Quick index

- **System / disk**
  - [Disk full / mmap errors / bus errors / short reads](#disk-full--mmap-errors--bus-errors--short-reads)
  - [Imports take 30-60 seconds on Apple Silicon](#imports-take-30-60-seconds-on-apple-silicon)
- **Install / Python**
  - [`pip install -e .` fails: "Could not find a version that satisfies agent-framework-gemini"](#pip-install--e--fails-could-not-find-a-version-that-satisfies-agent-framework-gemini)
  - [`zsh: unknown file attribute: v` when running `rm -rf .venv`](#zsh-unknown-file-attribute-v-when-running-rm--rf-venv)
  - [`No module named inderes_agent` after editable install](#no-module-named-inderes_agent-after-editable-install)
  - [`No module named inderes_agent` outside venv](#no-module-named-inderes_agent-outside-venv)
- **Inderes MCP**
  - [Inderes MCP returns 401 Unauthorized](#inderes-mcp-returns-401-unauthorized)
  - [`invalid_grant: Session not active` / OAuth keeps re-prompting](#invalid_grant-session-not-active--oauth-keeps-re-prompting)
  - [MCP error `Failed to enter context manager / Method not found`](#mcp-error-failed-to-enter-context-manager--method-not-found)
  - [`1 validation error for FunctionDeclaration / parameters.$schema`](#1-validation-error-for-functiondeclaration--parametersschema)
- **Gemini**
  - [503 errors from Gemini](#503-errors-from-gemini)
  - [Free-tier daily quota exhausted (429)](#free-tier-daily-quota-exhausted-429)
- **CLI / shell**
  - [`command not found: #` in zsh](#command-not-found--in-zsh)
  - [Agent runs forever without printing anything](#agent-runs-forever-without-printing-anything)
- **Git**
  - [`mmap failed: Operation timed out` during `git push`](#mmap-failed-operation-timed-out-during-git-push)
  - [`bus error` from git, missing `.git/HEAD`, "no commits yet"](#bus-error-from-git-missing-githead-no-commits-yet)
  - [SSH passphrase prompt when pushing](#ssh-passphrase-prompt-when-pushing)
- **Other**
  - [Where are my run logs?](#where-are-my-run-logs)
  - [Where is my OAuth token?](#where-is-my-oauth-token)

---

## Disk full / mmap errors / bus errors / short reads

**Symptoms** (any of these):
```
fatal: mmap failed: Operation timed out
zsh: bus error  git cat-file -t <sha>
error: short read while indexing <some file>
fatal: failed to push some refs to '...'
```

…and unrelated tools (Python imports, `git`, etc.) start failing in odd ways.

**Diagnosis**:
```bash
df -h .
```

If `Capacity` is **above ~90 %**, this is the cause. APFS becomes unstable when
free space drops below ~10 %: failed `mmap` calls, truncated I/O, missing files.
This is filesystem-level — not a bug in the application or git.

**Fix**:
1. Free up at least **10–15 GB**, ideally more. Targets:
   - Empty Trash (`rm -rf ~/.Trash/*`)
   - Old Time Machine local snapshots: `tmutil listlocalsnapshots /` then
     `sudo tmutil deletelocalsnapshots <name>`
   - Package caches: `uv cache clean`, `pip cache purge`, `npm cache clean --force`
   - Xcode DerivedData: `rm -rf ~/Library/Developer/Xcode/DerivedData/*`
   - Docker volumes if you use Docker
   - macOS → System Settings → General → Storage → Manage shows the heaviest
     consumers
2. Verify: `df -h .` should show at least 20 GB free.
3. If git's `.git` directory got corrupted by the disk-full state (missing HEAD,
   bad object files), see [the git recovery section below](#bus-error-from-git-missing-githead-no-commits-yet).

---

## Imports take 30-60 seconds on Apple Silicon

**Symptom**: `python -m inderes_agent ...` hangs at import for 30–60+ seconds even
on simple commands. Pressing Ctrl-C shows the traceback inside `markdown_it`,
`google.genai`, or `attrs` — never application code.

**Diagnosis**:
```bash
uname -m                                                    # arm64? You're on Apple Silicon
which python                                                # /usr/local/... means Intel Homebrew
python -c "import platform; print(platform.machine())"      # x86_64 = Intel via Rosetta
```

If `uname -m` says `arm64` but `python` reports `x86_64`, you're running Intel
Python through Rosetta 2 translation. Every dynamic library load (`.so`,
`.dylib`) is translated on the fly → ~10× slower cold imports.

**Fix**: Install ARM-native Python via `uv` and recreate the venv:
```bash
deactivate
/bin/rm -rf ./.venv                                         # plain rm -rf .venv errors in some zsh configs
uv python install 3.13                                      # downloads ARM-native CPython
uv venv --python-preference only-managed --python 3.13
source .venv/bin/activate
python -c "import platform; print(platform.machine())"      # should print arm64
uv pip install --pre -e .
```

**Verification**: cold-import benchmark should show ~1–2 s wall-clock with high
CPU%, not 7+ s with 7% CPU:
```bash
time python -c "from agent_framework_gemini import GeminiChatClient"
```

---

## `pip install -e .` fails: "Could not find a version that satisfies agent-framework-gemini"

**Diagnosis**: `agent-framework-gemini` is published only as a pre-release on
PyPI (e.g. `1.0.0a260429`). Plain `pip install` excludes pre-releases by default.

**Fix**:
```bash
uv pip install --pre -e .
# or
pip install --pre -e .
```

---

## `zsh: unknown file attribute: v` when running `rm -rf .venv`

**Diagnosis**: Some zsh configurations interpret `-rf` as glob-qualifier syntax
when the next argument starts with `.`.

**Fix**: Use the full path to `rm`:
```bash
/bin/rm -rf ./.venv
```

---

## `No module named inderes_agent` after editable install

**Symptom**:
```
/.../python: No module named inderes_agent
```
…even though `ls .venv/lib/python3.13/site-packages/ | grep inderes` shows the
dist-info directory exists.

**Diagnosis**: The `_editable_impl_inderes_agent.pth` file in `site-packages` may
be missing its trailing newline, which Python's `site.py` requires to register
the source directory.

**Fix**:
```bash
uv pip install --force-reinstall --pre -e .
```

---

## `No module named inderes_agent` outside venv

**Symptom**: You forgot to activate the venv.

**Fix**:
```bash
source .venv/bin/activate
which python                                                # should print .../.venv/bin/python
```

---

## Inderes MCP returns 401 Unauthorized

**Symptom**:
```
HTTP Request: POST https://mcp.inderes.com "HTTP/1.1 401 Unauthorized"
McpError('Method not found')
```

**Diagnosis**: The MCP server requires a Bearer token from Inderes' Keycloak SSO.
MAF's `MCPStreamableHTTPTool.header_provider` is **only called for tool
invocations**, not for the connection-time `initialize` call — so the first POST
has no `Authorization` header.

**Fix**: The codebase already handles this — `src/inderes_agent/mcp/inderes_client.py`
attaches auth via `httpx.AsyncClient(auth=BearerAuth(...))` so every request
including `initialize` carries the token. If you're still getting 401:

1. Check that `~/.inderes_agent/tokens.json` exists and contains a valid
   `access_token`.
2. Verify your Inderes Premium subscription is active.
3. Force a fresh login: `rm ~/.inderes_agent/tokens.json` then re-run.
4. Confirm the `_InderesBearerAuth.auth_flow()` is being called (set
   `LOG_LEVEL=DEBUG`).

---

## `invalid_grant: Session not active` / OAuth keeps re-prompting

**Symptom**: Every run opens the browser even though you logged in earlier:
```
refresh_failed status=400 body={"error":"invalid_grant","error_description":"Session not active"}
```

**Diagnosis**: Keycloak refresh tokens have a session lifetime; if you don't use
the agent for ~30 days, or your Inderes Premium subscription state changes, the
refresh token becomes invalid and a fresh login is required.

**Fix**: Just complete the browser flow again — the new tokens get cached
automatically. To force a fresh login at any time:
```bash
rm ~/.inderes_agent/tokens.json
```

---

## MCP error `Failed to enter context manager / Method not found`

**Symptom**:
```
('Failed to enter context manager.', McpError('Method not found'))
```

**Diagnosis**: MAF's `MCPStreamableHTTPTool` calls `prompts/list` during
`initialize` by default (`load_prompts=True`). Inderes MCP exposes only tools,
not prompts → server responds "Method not found" → MCP context manager fails to
enter → agent crashes before any tool call.

**Fix**: Already applied — `_SanitizingMCPTool` is constructed with
`load_prompts=False` in `src/inderes_agent/mcp/inderes_client.py`. If you're
seeing this error after modifying that file, ensure the constructor call still
passes `load_prompts=False`.

---

## `1 validation error for FunctionDeclaration / parameters.$schema`

**Symptom**:
```
1 validation error for FunctionDeclaration
parameters.$schema
  Extra inputs are not permitted
```

**Diagnosis**: Inderes MCP tool schemas include `$schema` (and similar
JSON-Schema metadata: `$id`, `$ref`, `$defs`, `$comment`). Google's
`google.genai.types.FunctionDeclaration` Pydantic model has `extra='forbid'` and
rejects these as `extra_forbidden`.

**Fix**: Already applied — `_SanitizingMCPTool` overrides `connect()` to strip
these keys recursively from each tool's cached input schema. See
`_scrub_schema_in_place()` in `src/inderes_agent/mcp/inderes_client.py`. If a new
JSON-Schema metadata key appears in a future Inderes update and Gemini rejects
it, add it to `_INCOMPATIBLE_SCHEMA_KEYS`.

---

## 503 errors from Gemini

**Symptoms**:
```
primary_model_503_retry model=gemini-3.1-flash-lite-preview
falling_back_to_secondary primary=gemini-3.1-flash-lite-preview fallback=gemini-2.5-flash
fallback_503_retry attempt=1
```
…and sometimes a subagent ends with `ERROR 503 UNAVAILABLE`.

**Diagnosis**: Gemini's free-tier *and* paid-tier capacity is occasionally
exhausted globally. This is a **service-side** issue, not a quota issue. The
fallback wrapper retries primary once → falls back to secondary → retries
fallback twice. If both models return 503 across all those attempts, the
subagent fails.

**Fix**:
1. **Wait a few minutes and retry.** These spikes are usually short-lived.
2. **Switch to paid tier** at [Google AI Studio billing](https://aistudio.google.com/app/apikey).
   Paid users get priority + much higher quotas. Costs ~$0.005–0.02/query.
3. **Reduce concurrent agents**: `MAX_CONCURRENT_AGENTS=1` in `.env` makes
   single-agent queries less likely to coincide with capacity spikes (at the cost
   of slower comparisons).
4. **Accept graceful degradation**: even when 1–2 subagents fail, the lead still
   synthesizes a useful answer from whatever did succeed. The `subagent trace`
   and `narrative.md` show exactly which agent failed.

**Important**: 503 ≠ quota exhaustion. Quota errors are 429, not 503. The
fallback wrapper handles both.

---

## Free-tier daily quota exhausted (429)

**Symptom**:
```
QuotaExhaustedError: Daily Gemini quota exhausted on both primary and fallback
models. Try again tomorrow or upgrade to paid tier.
```

**Diagnosis**: Free-tier daily limits are very tight:

| Model | Requests/day |
|---|---|
| `gemini-3.1-flash-lite-preview` (primary) | 500 |
| `gemini-2.5-flash` (fallback) | 20 |

A single multi-domain query can burn 8–15 LLM calls. Realistic free-tier
capacity is ~30–50 queries/day before hitting limits, mostly bounded by the
fallback model's 20-RPD limit.

**Fix**:
1. **Wait until midnight Pacific Time** (10:00 Helsinki time) for daily reset.
2. **Switch to paid tier** for sustained use.
3. **Test with simpler single-domain queries** while developing — they use
   fewer LLM calls.

Inspect your usage at https://aistudio.google.com/app/usage.

---

## `command not found: #` in zsh

**Symptom**: You pasted multiple lines starting with `#`:
```
# poista vanha venv
deactivate
zsh: command not found: #
```

**Diagnosis**: Pasting multiple lines that include `#` comments confuses zsh in
some configurations — the `#` doesn't always get treated as a comment when
pasted as part of a multi-line block.

**Fix**: Paste one command at a time, or strip the `#` lines before pasting.

---

## Agent runs forever without printing anything

**Symptom**: After `python -m inderes_agent "..."` you see no output for a long
time, then panic and Ctrl-C.

**Diagnosis**: First cold-start imports take 5–10 s even on ARM-native Python.
The router LLM call adds another 5–15 s. The first MCP `initialize` adds 1–2 s.
Total time to the first visible progress line: **10–30 s is normal**.

If imports themselves take >30 s, you're likely on Intel Python via Rosetta —
see [Imports take 30-60 seconds on Apple Silicon](#imports-take-30-60-seconds-on-apple-silicon).

**Fix**: **Be patient.** Don't Ctrl-C unless you've waited at least **60 seconds**
without any output. The progress lines (`reitittäjä päättää…`,
`subagentit ajetaan…`, etc.) appear once each phase actually starts.

For minute-by-minute confirmation that things are working, run the diagnostic:
```bash
python scripts/diag.py
```
which probes Gemini and MCP independently with timing on each step.

---

## `mmap failed: Operation timed out` during `git push`

**Symptom**:
```
Enumerating objects: 59, done.
fatal: mmap failed: Operation timed out
fatal: the remote end hung up unexpectedly
send-pack: unexpected disconnect while reading sideband packet
```

**Diagnosis**: Almost always a side effect of [low disk space](#disk-full--mmap-errors--bus-errors--short-reads).
APFS gets unhappy below ~10 % free, and git's `mmap`-based object packing fails.

A secondary cause is genuine network instability, but the disk issue is far more
common.

**Fix**:
1. Free disk space (see [the disk-full section](#disk-full--mmap-errors--bus-errors--short-reads)).
2. Retry: `git push -u origin main`.
3. If retry fails again with the same error, switch to SSH which uses different
   transport: `git remote set-url origin git@github.com:<user>/<repo>.git` and
   `git push`.

---

## `bus error` from git, missing `.git/HEAD`, "no commits yet"

**Symptom** (any of these together or separately):
```
zsh: bus error  git cat-file -t <sha>
fatal: your current branch 'main' does not have any commits yet
ls -la .git/    # shows files but no HEAD
git add -A
error: short read while indexing <file>
```

**Diagnosis**: `.git` got corrupted, almost always due to running git operations
while disk space was low. The disk-full state caused incomplete writes to
`.git/HEAD`, `.git/objects/...`, etc.

**Fix**:
1. Free disk space first (see [disk-full section](#disk-full--mmap-errors--bus-errors--short-reads)).
2. Verify your source files are intact: `md5 src/inderes_agent/agents/prompts/lead.md`.
   If MD5 succeeds, files are fine — only `.git` is broken.
3. Reinitialize git (you'll lose local commit history but not source files):
   ```bash
   /bin/rm -rf .git
   git init -b main
   git add -A
   git commit -m "Initial commit"
   git remote add origin git@github.com:<user>/<repo>.git
   git push -u origin main
   ```
4. If you had multiple local commits you want to preserve, instead try:
   ```bash
   echo "ref: refs/heads/main" > .git/HEAD     # if HEAD is missing
   cat .git/refs/heads/main                    # should print a SHA
   git fsck --full                             # check for corrupted objects
   ```

---

## SSH passphrase prompt when pushing

**Symptom**:
```
git push -u origin main
Enter passphrase for key '/Users/.../.ssh/id_ed25519':
```
…and you don't remember setting a passphrase, or don't want to type it on every push.

**Diagnosis**: Your SSH key has a passphrase set. Either it was set at key
generation, or your system policy required one.

**Fix options**:

1. **Just type the passphrase** (if you remember it). macOS will offer to add it
   to Keychain so you don't get prompted again.

2. **Switch to HTTPS** (uses your `gh` credentials, no passphrase):
   ```bash
   git remote set-url origin https://github.com/<user>/<repo>.git
   gh auth setup-git
   git push -u origin main
   ```

3. **Remove the SSH passphrase** (if you never wanted one and don't recall setting it):
   ```bash
   ssh-keygen -p -f ~/.ssh/id_ed25519
   # Enter old passphrase (or just Enter if there really is none)
   # New passphrase: <Enter>
   # Confirm: <Enter>
   ```

---

## Where are my run logs?

`~/.inderes_agent/runs/<timestamp>/`. Per-run directory contains:

| File | Contents |
|---|---|
| `query.txt` | The user's question |
| `routing.json` | Router classification: domains, companies, comparison flag, reasoning |
| `subagent-NN-<domain>.json` | Each subagent's full output, model used, errors |
| `synthesis.txt` | Lead's final synthesized answer |
| `meta.json` | Duration, fallback events, error counts |
| `console.log` | Raw HTTP/MCP/fallback log lines with timestamps |
| `narrative.md` | Human-readable summary, auto-generated post-run |

Quick access:
```bash
ls -1t ~/.inderes_agent/runs/ | head -5            # 5 most recent
python scripts/explain.py                          # narrative for latest
python scripts/explain.py 20260501-205122-776     # narrative for specific run
```

In the REPL: `/last`, `/runs`, `/explain`.

---

## Where is my OAuth token?

`~/.inderes_agent/tokens.json` (file mode `0600`).

Inspect:
```bash
cat ~/.inderes_agent/tokens.json | python3 -m json.tool
```

Force re-login:
```bash
rm ~/.inderes_agent/tokens.json
```

The token contains both an `access_token` (short-lived, ~5 min) and a
`refresh_token` (longer-lived, ~30 days). The refresh happens transparently when
the access token nears expiry, with `_InderesBearerAuth.auth_flow()` re-fetching
on each request.
