# Changelog

All notable changes to this project. Format roughly follows
[Keep a Changelog](https://keepachangelog.com); the project does not yet follow
[SemVer](https://semver.org) strictly.

## [unreleased] — 2026-05-12 (Gemini error classification + UI toggle fix)

### Fixed — Gemini quota-error misclassification (`e44a053`)

The previous heuristic `_is_quota_exhausted` matched any "429" /
"quota" / "resource_exhausted" substring in `str(exc)` and escalated
immediately to `QuotaExhaustedError` with a misleading *"Daily Gemini
quota exhausted, upgrade to paid tier"* message. The user is on paid
Tier 1 with dashboard showing 0.1% RPD usage — the "Daily quota"
verdict was empirically wrong.

Debug session captured the smoking gun: 5 quick-fire failures on
2026-05-11 21:04–21:19, each with primary failing in <400ms and
fallback engaging without further log output. The <400ms reject
pattern was an immediate 4xx, NOT a 503 overload — almost certainly
per-minute or concurrent-request limits that resolve in 30–90s. The
old code gave up on every 429 instead of retrying.

Replaced with three components:

- **`_classify_gemini_error(exc)`** parses real
  `google.genai.errors.APIError` by code + status + quotaId, returning
  one of `transient` / `rate_limit_minute` / `rate_limit_day` /
  `other`. Defensive default for 429 without quotaId: treat as
  per-minute (safer than locking the user out for a day).
- **`_log_genai_error(event, model, exc)`** extracts `code`, `status`,
  `message`, and `quota_violations` from APIError and emits structured
  log lines at every failover point. Previous code logged only
  `falling_back_to_secondary` without the triggering exception,
  leaving zero visibility into what actually broke.
- **Retry-with-backoff**: primary attempts 3× with 30s/60s backoff
  before falling back; fallback uses same schedule. `QuotaExhaustedError`
  fires ONLY when both models confirm explicit daily quotaId.

The diagnostic logging immediately paid off — first real-world hit
revealed the actual cause was a **project monthly spending cap**
(`'message': 'Your project has exceeded its monthly spending cap'`),
not any rate limit. User raised the cap; system recovered.

17 new tests in `test_fallback.py` covering classifier categories,
legacy-shim compat, end-to-end retry-fallback scenarios.

### Fixed — FI/EN language toggle on landing page (`9607953`)

Bug #5 reported 2026-05-11 evening. Two issues conspiring: (1) `<a
href="?lang=...">` links carried legacy `target="_top"` inherited
from an older `st.html`-based render — actively breaks Streamlit
Cloud navigation; (2) `del st.query_params["lang"]` schedules rerun
AFTER the current run completes, so titlebar + hero + toggles could
render with stale `_lang`. Removed the target + added explicit
`st.rerun()` after lang change.

### Updated — Documentation refresh for system as it stands today

- `README.md` dual-MCP architecture (Inderes + Yahoo) in description,
  architecture diagram, subagent-tool-mapping table. Updated test
  count 146 → 375. Doc map references new agentic patterns +
  research docs and sidecar repos.
- `TROUBLESHOOTING.md` added project spend cap, stale-Streamlit-
  process trap, Cloud token staleness entries.
- `LESSONS.md` added 3 distilled lessons from 2026-05-11/12:
  diagnostic logging beats heuristic refinement, OAuth gist-pull
  is one-shot per process, stale processes are the modal LLM-app
  bug.

---

## [unreleased] — 2026-05-11 (Yahoo MCP integration + agentic patterns docs)

### Added — yahoo-finance-mcp integration into agent fleet (`3137a4f`)

Wires a self-hosted Yahoo Finance MCP sidecar
([`yahoo-finance-mcp`](https://github.com/5qtb5t9v5k-rgb/yahoo-finance-mcp),
MIT-public, 5 tools + tests + CI) into all 5 subagents behind a single
`YAHOO_MCP_URL` env-var toggle. Empty (default) = no change, Inderes-
only flow preserved bit-for-bit. Non-empty = each agent picks up its
assigned Yahoo subset alongside its Inderes tools.

Per-agent partitioning mirrors `inderes_client.py:63–111`:

```
QUANT     = search_ticker, get_snapshot, get_history
VALUATION = search_ticker, get_snapshot
RESEARCH  = search_ticker, get_news
SENTIMENT = search_ticker, get_news, get_holders
PORTFOLIO = search_ticker, get_snapshot, get_history
```

Rationale: `get_holders` ≈ Inderes `list-insider-transactions`
(SENTIMENT-only), `get_snapshot` ≈ `get-fundamentals` (QUANT +
VALUATION shared), `get_news` ≈ `list-content` (RESEARCH + SENTIMENT
for tone). `get_history` has *no Inderes parallel* — pure new
capability for QUANT/PORTFOLIO charting on Finnish AND international
tickers.

15 live test queries on 2026-05-11 evening confirmed end-to-end.
Critical empirical finding: **`get_holders` and `get_history` fired
automatically without prompt nudging** — LLM picked them from tool
descriptions alone.

Changes:

- `src/inderes_agent/mcp/_compat.py` (new) — shared `SanitizingMCPTool`.
- `src/inderes_agent/mcp/yahoo_client.py` (new) — 5 tool partitions +
  `build_yahoo_mcp_tool` returning None when `YAHOO_MCP_URL` empty.
- `settings.py` — `YAHOO_MCP_URL: str = ""`.
- `agents/_common.py` — `with_yahoo(inderes, yahoo)` helper.
- 5 agent builders updated.
- `tests/test_yahoo_mcp_wiring.py` (new) — 11 tests covering toggle,
  partitioning, regression-when-disabled.

### Added — auto-relogin headless Keycloak via Playwright

Separate private repo
[`inderes-mcp-auto-relogin`](https://github.com/5qtb5t9v5k-rgb/inderes-mcp-auto-relogin).
GitHub Actions cron runs Playwright + Chromium twice per day (02:00
+ 17:00 UTC, outside Helsinki 08–16) for full Keycloak OAuth re-auth.
Pushes fresh tokens to shared gist. Removes the previously-required
daily manual `bash scripts/relogin.sh` step.

7-iteration debug arc through custom-Keycloak-theme + JS-driven
submit + `chrome-error://`-URL masking. Critical fix:
`page.on("request", listener)` captures callback URL BEFORE Chromium
tries to load `localhost:9999` and fails.

Repo kept private because workflow file contains
`INDERES_USERNAME` + `INDERES_PASSWORD` as repo secrets.

### Added — UI bug fixes (`6a9f592`, `d357c10`)

- **"Avaa suunnitelma" rendering** — previously didn't appear until
  user clicked "Avaa loki" first. Root cause: `st.button` +
  `session_state` + `st.rerun` pattern didn't paint on first render.
  Replaced with native `<details>/<summary>` HTML element.
- **Sentiment.md prompt tightened** — 226 → 195 lines. Insider
  taxonomy compressed 54 → 14 lines while preserving three-bucket
  structure (Voluntary / Compensation / Risk).
- **Subagent error surfacing** — agent-card status pill now shows
  actual error text instead of generic "error".

### Added — Documentation pass for agentic patterns + research

- `docs/agentic_patterns_mapping_2026-05-11.md` (~720 lines) — deep
  mapping of this project against
  [nibzard/awesome-agentic-patterns](https://github.com/nibzard/awesome-agentic-patterns).
  ~12 patterns we already implement (★-rated), 8 BACKLOG'd, 6 worth
  adopting (Lethal Trifecta, Action Replay, Subject Hygiene, etc.),
  5 explicitly skipped with reasoning. Decision framework for
  nibzard (micro) vs Google Cloud (macro) catalogues.
- `docs/research_prompts/agentic_ai_expansions_2026-05-11.md` —
  self-contained 30-axis research prompt for Deep Research
  sessions. Includes nibzard + Google Cloud as seed material.
- `docs/research_outputs/agentic_expansions_synthesis_2026-05-11.md`
  — verbatim capture of external research synthesis (12-month
  roadmap, 6-axis taxonomy).
- `docs/agentic_research_digest_2026-05-11.md` — critical reading
  filtered against project constraints. 5 BACKLOG pulls + 4
  verify-first + 6 context-specific skips. Captures the
  "continuity + evidence + proof" trinity as the keeper insight.

### Updated — `BACKLOG.md` mass cleanup

- Yahoo MCP entry has full Fly.io deployment plan (Path A vs B vs C
  analysis), per-agent partitioning constants, empirically-confirmed
  status.
- Cross-source retry promoted to 🟡 *next* with ASML + Smart Eye
  evidence captured.
- Gap 5 sector-level queries added (research+sentiment fab when no
  anchor company).
- Gap 6 Yahoo-first BVPS+price added (Q-fresh Yahoo vs LFY-locked
  Inderes for banks).
- §4 Quota-error-diagnostic + heuristic-refinement entry with full
  patch snippets (later shipped 2026-05-12 morning).
- Avaa-suunnitelma + FI/EN bugs marked ✅ shipped with commit refs.
- Grounding-with-Google-Search added as §1 Open-medium with risk
  analysis (provenance dilution, fabrication-guard interference) +
  opt-in pattern recommendation.

---

## [unreleased] — 2026-05-10 (afternoon — Wk 2 foundation + quick wins)

### Added — CI gate (`0a16299`)

First automated test gate on `main`. Closes the Wk 2 #1 priority
in BACKLOG §6 ("smoke test in pytest CI") and the gap that let the
morning's `render_feedback_widget` ImportError run on Streamlit
Cloud unnoticed for ~4 hours.

- **`.github/workflows/ci.yml`** — runs ruff + pytest on every push
  and PR to `main`. Concurrency cancellation, uv-cache on lock-hash,
  GEMINI_API_KEY=dummy injection. Ruff format gate intentionally
  NOT enabled yet (would reformat 33 files; deferred to a separate
  cleanup commit).
- **`tests/test_app_imports.py`** — smoke test mimicking Streamlit's
  runtime sys.path setup; imports `ui/components.py`, py_compiles
  `ui/app.py`, asserts every name in `from components import (…)`
  resolves. Would have caught the morning's regression at PR time.
- Same commit fixed: stale tests after a recent refactor
  (`test_output_parts.py` × 7, `test_workflows.py` × 3), 68 ruff
  auto-fixes, and a real bug found by `ruff F821`: `ui/app.py` used
  `DOMAIN_VERBS_EN` without importing it — would have crashed for
  English-language users.

### Added — multi-company valuation parser fix (`5f581c5`)

Production bug: when valuation runs as a per-company fan-out (e.g.
Sampo + Nordea + Aktia), the agent occasionally emits a JSON array
containing all companies in EVERY worker's response. Pre-fix parser
rejected non-object roots → silent fall-through to Tila B for every
multi-company comparison. Single-company queries unaffected, so the
bug hid for an unknown duration.

- **`valuation/parser.py`** — accepts JSON arrays at the root.
  `parse()` takes optional `expected_company` keyword to disambiguate.
  Single-element arrays unwrap; ≥2 entries with no expected company
  is loud failure (with the list of companies found); duplicate
  matches refuse to guess.
- **`orchestration/synthesis.py`** — passes the fan-out worker's
  `company` name to `parse()` at the only call site.
- **`tests/valuation/test_parser.py`** — 9 new tests covering
  single-element unwrap, 3-company match (the production case),
  case-insensitive matching, ambiguous-without-expected, no-match,
  empty array, duplicate match, mixed valid+skipped, single-object
  backwards-compat.

### Added — OAuth runtime tests (`c78607e`)

`mcp/oauth.py` (573 LOC) had ZERO unit tests; single largest Tier-A
coverage gap from `docs/testing_strategy.md`. The morning's Streamlit
Cloud failure ran along this exact path (stale `/tmp` tokens.json
fighting fresh gist copy). 16 new tests:

- **TokenSet behaviour** (4): freshness, refresh-buffer staleness,
  forward-compat `from_dict` (gist tokens.json carries cron-worker
  bookkeeping fields), to/from round-trip.
- **`_refresh_tokens`** (4): happy path; 400 invalid_grant returns
  None; no refresh token returns None without a network call;
  response missing `refresh_token` keeps the old one.
- **Gist push/pull** (5): silent no-op when env vars missing; PATCH
  with auth header; GET happy path; missing tokens.json returns
  None; network exception returns None.
- **`_load_tokens` priority order** (3): first call within process
  pulls gist and overwrites stale local cache (the morning's bug);
  subsequent calls hit local cache only; corrupt cache falls
  through to env bootstrap.

OAuth coverage: 0 % → ~70 % of public surface. Mocking via
`monkeypatch` on `httpx`; no new dev-deps.

### Added — case_008 + eval status audit (`7a07d06`)

New regression case for the parser bug above, plus a status-audit
document mapping the 2026-05-09 baseline ("12 pass / 4 fail")
against fix commits shipped since.

- **`evals/golden.yaml`** —
  `case_008_multi_company_valuation_comparison` with 10 hard
  assertions and 3 soft assertions. Exercises the comparison-floor
  (case_001) and hard-limits (case_006) chain end-to-end.
- **`evals/findings_2026-05-10.md`** — re-baseline status check.
  Predicts post-rerun result of 7/8 pass at the case level.
  Documents what's still missing from coverage: cost-ceiling per
  case (lands with HITL Step 1), eval-runner CI hook, BUY-only
  insider quality case, Walkthrough placeholder for Wk 5-6.

### Added — golden.yaml structural CI (`89e8d78`)

`tests/test_evals_yaml.py` — 9 deterministic tests catching yaml
mistakes that would otherwise only surface during a manual
`evals/runner.py` run:

- golden.yaml parses, has at least one case; case IDs unique;
  every case has id + query_match + (hard OR soft) + rationale.
- Every hard assertion is a syntactically valid Python expression.
- Every hard assertion only references names exposed by
  `runner.py:_eval_context` (catches typos like `routing.domain`
  singular, `tool_calls` instead of `tc_count_per_agent`, etc.).
- Soft assertions are `{snake_case_key: rubric_string}` dicts.
- Tier-1 baseline cases remain present — removing one flags
  in PR review.

Subtle bit: the AST walker for "names referenced" excludes
comprehension-bound targets, so `all(r.has_synthesis for r in runs)`
resolves correctly. First-pass implementation got this wrong; the
failing test caught its own implementation bug.

### Added — smart insider taxonomy + transcript-default (`64c8309`)

Two prompt-quality changes (Wk 2b) plus a docs correction.

**SENTIMENT — `sentiment.md`.** Earlier draft proposed `types=["BUY"]`
as the default; user push-back caught the cherry-pick — sells ARE
signal. Real problem was undifferentiated compulsory share-premium
grants drowning voluntary trades.

Fix at description layer, not data layer:
- Tool default no longer filters by type; full picture (50 most
  recent in window).
- New "Insider transaction taxonomy" section enumerates 19
  `transactionType` values into three buckets:
  - **A. Voluntary trades (TRUE signal)** — BUY, SELL, SUBSCRIPTION,
    EXERCISE_OF_*, SHORT_SELL.
  - **B. Compensation flow (NOT signal)** — RECEPTION_OF_SHARE_PREMIUM,
    APPROVAL_OF_SHARE_OPTION, GIFTs, MATURITY_OF_PRODUCT.
  - **C. Risk indicators** — PLEDGE, BORROWING, LENDING.
- Net direction computed only over Bucket A; compensation context
  reported separately. Single voluntary trades >€1M named explicitly.

**RESEARCH — `research.md`.** Workflow case for investment-thesis
questions: pull `list-transcripts` + `get-transcript` alongside the
report when query keywords match ("näkymä", "strategia", "kasvu",
"riskit", "outlook", "thesis", etc.). Management's own words under
analyst Q&A pressure beat a synthesised summary.

(Initial version added 36 lines; that triggered fabrication-guard
regressions on Flash-Lite by diluting the HARD GATE — see
`LESSONS.md` "Prompt length erodes hard gates". Tightened to 6
lines in a follow-up edit.)

**Docs correction — `data_sources_analysis_2026-05-10.md`.**
Verified `get-fundamentals` against Sampo (1:5 split in 2024):
server returns split-adjusted prices, "Plotly cliff" bug doesn't
exist. Two struck-through sections plus verification notes.

### Changed — `.env` default model

`PRIMARY_MODEL` flipped from `gemini-3.1-flash-lite-preview` to
`gemini-2.5-flash` after fabrication-guard regressions on the
weaker model. Cost ~4× per query (~$0.005 → ~$0.020) but
instruction-following on RESEARCH/QUANT prompts noticeably more
reliable. `gemini-3.1-flash-lite-preview` remains an option via
env override for cost-sensitive workloads. Backup file
`.env.bak` retained.

### Added — HITL proposal + testing strategy docs (`085ab8a`)

Two design docs grounded in the morning's findings (sync audit,
code structure, test coverage 48 %, no CI). Senior-PM call: do Wk 2
in two parallel tracks — foundation (CI + tests) and learning
feature (HITL Level 1).

- **`docs/hitl_proposal.md`** (Human-in-the-Loop, Level 1 MVP) —
  Pre-flight estimate + risk-tier gate + accept/cancel UI + token/
  cost tracking + estimator accuracy log. Explicit learning
  hypotheses: cost-estimator MAPE per query class, gate-show %,
  cancel/approve ratio. Decision points after 2 weeks of data
  drive whether Level 2 (mid-run checkpoints) is worth building.
- **`docs/testing_strategy.md`** — Tier A/B/C module classification,
  test-category guide (unit/integration/eval/smoke), CI strategy,
  agent-specific testing patterns at 5 ROI-ranked levels (builder,
  prompt sanity, output schema, tool-call mocks, evals). Wk 2
  testing tasks itemised. Anti-patterns explicit.

### Repo hygiene — branch cleanup

23 stale remote branches deleted; `git branch -a` shrank from
~24 lines to 2. All squash-merged into `main`; no unique work
recovered. Diagnostic + recipe captured in `LESSONS.md` "Branch
hygiene needs automation, not discipline".

---

### Added — eval foundation (Tier 0 + Tier 1)

Two-layer eval scaffold built in one sprint. Tier 0 indexes every
historical run for fast diagnostic queries; Tier 1 grades captured
runs against a golden case set with an LLM-judge.

- **`scripts/build_runs_index.py`** (`9bcf4f0`) — walks
  `~/.inderes_agent/runs/<ts>/` and writes a SQLite database with
  two tables (`runs`, `tool_calls`). Idempotent. 183 existing runs +
  457 tool calls indexed in ~1 s.
- **`evals/sample_queries.sql`** — 10 diagnostic SQL queries, each
  targeting a specific weakness category (under-routed comparisons,
  noise runs, repeat queries, conflict-detector hit rate, tool error
  rates, latency outliers).
- **`evals/findings_2026-05-09.md`** — 7 systemic weaknesses surfaced
  on the first diagnostic pass.
- **`evals/judge_selection.md`** — benchmark-backed model choice
  (Vectara HHEM v2, RewardBench 2, Arena-Hard, JudgeBench). Gemini
  2.5 Pro picked over Sonnet 4.5 / GPT-5 because reasoning models
  hallucinate >10 % on grounded summarisation — exactly the failure
  mode we cannot import into a finance-research judge.
- **`evals/golden.yaml`** (`8971f66`) — 7 cases, each tied to a real
  finding. Hard (deterministic) + soft (judge-graded) assertions.
- **`evals/judge.py`** — `JudgeBackend` Protocol + `GeminiJudge` impl.
  Designed so GPT-4.1 can be added later as cross-family validator
  without runner changes.
- **`evals/runner.py`** — orchestrator. Picks most-recent matching
  run from index, runs hard expressions in sandboxed eval(), calls
  judge for soft criteria, writes timestamped report.

### Added — fabrication guard at orchestration boundary

- **`workflows.py:_detect_fabrication`** (`870749a`) — universal
  trust-killer defence. If a subagent emits ≥300 char domain-loaded
  text but ZERO MCP calls, the result is replaced with
  `error="fabricated_no_tool_calls: ..."`. Closes the trust-killer
  pattern from run `20260502-205706-108` ("Vincit: VÄHENNÄ 1,25 €"
  fabricated).
- **`synthesis.py:_no_data_response`** — when ALL subagents errored,
  short-circuit to a fixed honest "ei löytynyt"-style answer. No
  euros, no recommendations, no fabricated context.
- 14 unit tests in `tests/test_fabrication_guard.py`.

### Added — agent-prompt HARD GATE on all 5 subagents

Universal prompt-side enforcement that all subagents MUST execute
their MCP tool calls before emitting output.

- `valuation.md` (`08e7e93`), `sentiment.md` (`d36dd72`),
  `research.md` + `quant.md` + `portfolio.md` (`2039967`) — same
  pattern, agent-specific tool lists. Forbidden-numbers-from-memory
  clause. "Yhtiö ei ole seurannassa" treated as a fine finding when
  it's true (Konecranes).
- Verified: 12/12 subagent dispatches in a 4-bank comparison
  (Nordea/Aktia/Ålandsbanken/OmaSP) made tool calls, zero
  fabrication-guard rejections.

### Added — Tila C activation banner for LEAD synthesis

- **`synthesis.py`** (`08e7e93`) — when the valuation engine actually
  computed, pre-pend a high-visibility banner to LEAD's prompt
  enumerating the 4 required Tila C section headings. The banner is
  the FIRST thing LEAD reads, before the 600-line prompt body.
  Pre-fix Tila C reliability ~2/3; post-fix 5/5 verified.
- 4 unit tests in `tests/test_tila_c_banner.py`.

### Fixed — comparison routing floor

- **`router.py`** (`5e5dea7`) — both prompt rule (comparison MUST
  include `{quant, research, sentiment}`) AND `_enforce_comparison_floor()`
  post-processor as belt-and-braces. The previous few-shot example
  for "Compare Sampo and Nordea" was the bug source itself, showing
  `["quant"]` only.
- 5 unit tests cover both layers.

### Fixed — päättely structured-form lift + conflict-naming

- **`synthesis.py:_extract_paattely`** (`80c6fd0`) — when prose
  conforms to the 4-paragraph spec, lift to structured slots
  (`disagree`, `resolution`, `uncertain`, `skipped`). The lead.md
  spec was perfect; the parser was the missing link. 0 of 183
  historical runs produced JSON form, but 55 had perfect
  4-paragraph prose.
- **`scripts/reclassify_paattely.py`** — applies same lift
  retroactively. 56/59 historical prose päättelys converted.
- **`lead.md`** — HARD REQUIREMENT for conflict naming.
  Päättely §1 MUST name the conflict topic verbatim, §2 MUST state
  which value was kept and why.

### Fixed — trend classifier severe-decline branch

- **`roe_selection.py`** (`152c3bf`) — UPM-Kymmene regression. ROE
  `[12.7, 13.1, 3.3, 3.9, 4.5] %` (delta -48 %) was misclassified
  vakaa because lfy ticked up within the depressed window. **Three
  UPM runs failed in a row.** Fix: severe-decline branch fires on
  `delta < -0.20` regardless of LFY position. Symmetric severe-rise
  branch added.
- 5 new tests in `tests/valuation/test_roe_selection.py`.

### UI — major polish pass

- **`render_feature_toggles`** — collapsed `<details>` expander
  matching results-section "AVAA PÄÄTTELY ›" look (caps-micro amber
  summary, mono-meta body).
- **FI / EN switcher** — tiny inline toggle in titlebar via
  `?lang=` query param.
- **Plan expander** — converted to `st.button + session_state` after
  `<details>` proved unreliable in `chat_message`. Matches AVAA LOKI
  / AVAA PÄÄTTELY visually.
- **Material Icons leak fix** — `:not([class*="material"])` selectors
  prevent "keyboard_arrow_down" text from leaking through.
- **Statusbar trim** — dropped `virheet: 0 / fallbackit: 0` noise.
- **Tier label clarity** — radio options now name the model exactly
  ("Vakio (Gemini 3.1 Flash Lite)", etc.). Native `?` help icon for
  trade-off explanations.

### Documentation

- **`docs/sprint_lessons_2026-05-09.md`** — long-form session
  retrospective: 7 lesson categories, chronological commit
  walkthrough, user emotional arc, re-prioritised backlog rationale.
- **`BACKLOG.md §0`** — re-prioritised. Plotly charts promoted to
  Wk 1 #1 (user-stated top priority). Hard limits + 👍/👎 Wk 1.
  Reflexion + footnotes Wk 2. Devil's advocate demoted to Wk 4+.

---

## [unreleased] — 2026-05-09

### Added — alternative valuation feature (opt-in Greenwald-Gordon)

A user-controlled fifth specialist subagent (`aino-valuation`) plus a
deterministic Python valuation engine, integrated end-to-end through the
LEAD synthesis. Activated via the *"Käytä vaihtoehtoista arvonmääritystä"*
sidebar toggle. Default flow remains unchanged — when the toggle is off,
no new code paths execute (verified via the LEAD prompt's *Tila A* mode
which explicitly tells the model to ignore valuation guidance).

**Methodology**: an 8-step Greenwald-Gordon hybrid. `FV = ((ROE−g)/(k−g)) ×
BVPS`, EPV = `(ROE/k) × BVPS`, growth value = `FV − EPV` for laatuyhtiöt
(ROE > k) and 0 otherwise. Quality classification with a ±2% buffer around
k (laatu / keskinkertainen / tuhoutuva). Dual implied values surface that
Gordon's equation has two unknowns (ROE, g) but one constraint (price):
`implied_g` (holds ROE) and `implied_roe` (holds g), shown side-by-side so
neither dimension is presented as "the" market reading.

**Components**:
- `src/inderes_agent/valuation/engine.py` — pure-Python deterministic
  computation, validated against the user's `Arvonmääritys2023.xlsx`
  Data-sheet outputs for 10 hand-picked Finnish companies (laatu /
  tuhoutuva mix), within 0.02€ tolerance per cell
- `src/inderes_agent/valuation/roe_selection.py` — single source of truth
  for the **sustainable-ROE rule** (median dominates the mean for "typical
  year" thinking; 5y_median for vakaa/nouseva, min(3y_median,
  trend_weighted) for laskeva). Used both by the agent prompt
  (documentation) and by the parser (validation; agent can't silently
  mis-compute medians)
- `src/inderes_agent/valuation/parser.py` — strict JSON validator with
  Levenshtein-≤2 fuzzy match for `*_rationale` field typos (sibling
  protection: `g_rationale` cannot absorb `k_rationale`'s value)
- `src/inderes_agent/agents/valuation.py` + `prompts/valuation.md` —
  `aino-valuation` agent that fetches BVPS, ROE history, and current
  share price via `get-fundamentals` and emits structured JSON. The
  agent **never does math** — it extracts parameters and rationale; the
  deterministic engine handles all computation
- `src/inderes_agent/orchestration/synthesis.py` —
  `_process_valuation_subagents()` runs the agent JSON through parser
  and engine; `_format_valuation_block()` renders results for the LEAD
  prompt with edge-case warnings for absurd safety-margins
- `src/inderes_agent/orchestration/router.py` —
  `query_has_valuation_intent()` heuristic gates the toggle, so purely
  qualitative questions ("explain why...") don't trigger an unwanted
  Greenwald-Gordon table. Conservatively biased — false negatives are
  far less damaging than false positives
- `src/inderes_agent/agents/prompts/lead.md` — three-state synthesis
  guide: A (toggle off, default flow unchanged), B (parse error,
  honest skip with explicit "do not hand-compute Gordon" guards), C
  (success, 4-section structure: Yhteenveto / Inderesin näkemys / Oma
  arvonmääritys / Vertailu, plus a static methodology infobox)

**Tool-call guard at the orchestration boundary**

Production run `20260508-205057-769` ("entäs jos roe olisi 13%")
demonstrated a trust-killer hallucination: Flash Lite emitted a
fully-formed JSON output with **zero MCP calls**, inventing
`company_id`, current price, and ROE history from conversation context.
Engine math then produced a confident but fabricated +18.2% safety
margin shown to the user.

Defense: `_process_valuation_subagents` counts `get-fundamentals` calls
*before* parsing. Zero calls → reject as hallucination, route into
LEAD's Tila B with an honest "agent did not query MCP" message.
Prompt-level "always fetch fresh data" instructions don't suffice —
structural enforcement at the orchestration boundary is the only
reliable defense.

**Test coverage** (108 new tests, 146 total green):
- 26 engine unit tests (math, edge cases, dual implied)
- 20 Excel-parity tests (10 companies × 2 assertion sets)
- 21 sustainable-ROE rule tests (medians, trend, validation)
- 35 parser tests (validation, typo tolerance, sibling protection)
- 10 tool-guard + edge-case warning tests
- 33 router intent-gate tests (explicit valuation queries fire,
  qualitative queries don't, Finnish morphology variants)

**Known limitation** (deferred to follow-up): per-company fan-out for
multi-company comparisons currently produces JSON arrays from each
subagent (each agent thinks the whole comparison is its scope) — parser
expects single objects, so all three companies' valuations fail to
parse and LEAD falls into Tila B for the whole query. Single-company
valuations work correctly. Tracked in `BACKLOG.md`.

## [previous] — 2026-05-06

### Added — pre-synthesis conflict detection

A new LLM step runs between subagent execution and lead synthesis. The
detector reads all subagent outputs and emits strict JSON with three
buckets: **agreements** (claims 2+ subagents support), **conflicts**
(claims subagents disagree on, with positions per side), and
**isolated_claims** (single-source factual claims that, if hallucinated,
would mislead). The lead synthesis prompt now receives this structured
report alongside the raw subagent outputs and explicit instructions on
how to use it. Persisted as `conflicts.json` in every run dir.

This is the BACKLOG #1 plan-then-execute extension — it turns the
emergent multi-subagent self-correction observed in
`evals/known-cases.md` Case 003 into something *explicit and loggable*
rather than implicit in the lead's training-data priors.

Empirically observed on a 10-subagent Puuilo-vs-Tokmanni-vs-Kesko run:
the detector caught a real disagreement between two `sentiment` branches
(one saw the Joller insider trade, the other did not) and the lead
resolved it explicitly in the synthesis preamble. Without the explicit
conflict map, that disambiguation would happen quietly via priors, if
at all.

### Fixed — Streamlit Cloud installer regression

The previous commit (d8186d2) accidentally checked `uv.lock` into the
repo via `git add -A`. Streamlit Cloud's installer-selection heuristic
prefers `uv-sync uv.lock` over `requirements.txt` when both exist, and
uv-sync skipped the `[ui]` extra — so streamlit got uninstalled from
the cloud venv, breaking the app with `streamlit: command not found`.
Removed `uv.lock` from the repo and gitignored it; `requirements.txt`
stays the documented source of truth.

## [previous batch] — 2026-05-02 → 2026-05-05

A heavy iteration on the Streamlit UI plus substantial operational
improvements to the agent layer and OAuth/cloud infrastructure. No
breaking changes.

### Added — public-safe error UI on auth-expired card

- **Embedded demo video** on the auth-expired card so first-time visitors
  past the password gate can still see what the tool does even when it
  can't run live.
- **"📧 Pyydä yhteyden korjaamista" button** that increments a recovery
  counter persisted in the same gist mirror used for tokens. Operator
  sees the counter on the card after a session death and knows people
  are waiting; visitor sees they're not the first to hit the wall.
- **Public-safe error masking**: `HeadlessAuthError` (and any exception
  whose message hints at auth/session problems) is rendered as a clean
  "Järjestelmä alhaalla — yhteys täytyy autentikoida uudelleen" card
  rather than a raw traceback that exposed local paths and recovery
  scripts.
- **Theme-matching chat avatars** (👤 user, 🔶 assistant) replacing
  Streamlit's default cartoon icons.
- **Absolute Helsinki-time timestamps** on the recovery counter
  ("Viimeisin: 04.05.2026 klo 20.34") instead of relative phrases that
  re-render inconsistently across day boundaries.

### Added — infrastructure (durable session keepalive)

- **`scripts/relogin.sh`** — one-shot recovery script that wraps the
  full flow: stash old tokens, run agent (browser opens for fresh
  login), sync to gist, trigger cron to verify, print a clear
  ✅/⚠ verdict.
- **`scripts/sync_local_tokens_to_gist.py`** — pushes local
  `~/.inderes_agent/tokens.json` to the gist via `gh` CLI (no
  GH_TOKEN needed in `.env`). Runs in `relogin.sh` and stand-alone.
- **MCP keepalive in cron worker** — after each successful Keycloak
  refresh, the cron also makes one authenticated MCP `initialize`
  call. Diagnostic test for whether Keycloak's idle timer treats
  /token vs MCP API activity differently (verdict: it doesn't —
  but the test confirmed the assumption).
- **Cron cadence `*/15` → `*/5`** with a documented caveat that
  GitHub Actions free-tier scheduling is best-effort and may skip
  runs under load. *Real* reliable scheduling moved to an external
  service (cron-job.org) that hits the same workflow via the
  GitHub API.
- **Smart cron notification** — exit 1 only on the ok→failed
  transition (tracked via `_last_refresh_status` field in the gist),
  exit 0 while ongoing-failed. Result: GitHub emails the maintainer
  exactly *once* when a session dies, not every 5 minutes.
- **Cross-cron-cloud rotation race recovery** in `oauth.py` — when
  cloud's in-memory refresh_token is invalidated by cron rotation,
  cloud now force-pulls the gist and retries with the fresh token
  before raising `HeadlessAuthError`.

### Added — empirical Inderes Session Max measurement

- **Confirmed: Inderes Keycloak SSO Session Max = exactly 10 hours
  wall-clock from login.** Measured by holding a fresh session alive
  with cron-job.org-driven token rotation every 5 minutes. Rotation
  succeeded ~120 times in a row, then failed with `invalid_grant:
  Token is not active` at minute 601. Documented in
  `LESSONS.md` and `MULTI_AGENT_ARCHITECTURE.md` as a worked
  example of "session lifetime is set by the IdP, not by you."

### Added — documentation

- **`MULTI_AGENT_ARCHITECTURE.md`** — generic layered-model primer
  for multi-agent systems. Five layers (Surface / Brain / Action /
  Data / Harness) plus two cross-cutting planes (Evals & Observability,
  Governance) plus memory tiers, with this project as a worked
  example throughout. Companion to `ARCHITECTURE.md` (which covers
  the concrete current implementation file by file).

### Fixed

- **URL hallucination** in source-link rendering. Agents had been
  generating `/fi/tapahtumat`-style fabricated category-root URLs
  when a tool didn't return a per-item URL. Tightened both
  `sentiment.md` and `lead.md` prompts with an explicit known-good
  section-roots block (calendar, forum, companies, mallisalkku) and
  a "common hallucinations to avoid" list.
- **Empty-result blindness** on calendar queries. Agents called
  `list-calendar-events` with `types=[INTERIM_REPORT, BUSINESS_REVIEW]`,
  got 0 results because the type filter was over-narrow, and
  reported "ei tapahtumia" even though the calendar visibly had 5+
  earnings reports. Fix: prompt now recommends omitting `types`
  filter for "what's today" -style queries, plus a new "empty-result
  skepticism" rule under sentiment.md `## Rules` mandating one
  broader retry before reporting nothing.
- **`TokenSet.from_dict` rejecting unknown fields**. The smart cron
  notification (above) added `_last_refresh_status` and
  `_last_refresh_at` to the gist's tokens.json, which made the
  cloud's `TokenSet.from_dict()` raise `unexpected keyword argument`
  on parse. Fixed by filtering to the dataclass's known fields
  before construction — forward-compatible to future bookkeeping
  fields.
- **CachedWidgetWarning on auth-expired card**. The `_bootstrap()`
  function was decorated with `@st.cache_resource` and called
  `_render_auth_expired()` (containing widgets) inside its except
  branch. Streamlit cache prevents widgets from re-rendering on
  cache hits. Refactored: bootstrap-auth step is cached, the
  auth-expired UI rendering happens outside the cache.
- **Chat avatars rendered as broken file paths**. First attempt
  used `❯` and `◆` (Unicode dingbats), which Streamlit doesn't
  detect as emoji and falls through to file-path interpretation,
  crashing with `FileNotFoundError`. Replaced with proper emoji.

### Added — Streamlit UI ("Trading Desk" visual layer)

### Added — UI polish (recommendation, followups, sources, status)

- **Inderes recommendation badge** rendered above the LEAD synthesis when the
  router has resolved a single primary company (PR #28). Pulls
  `recommendation` + `target_price` from `get-inderes-estimates` and renders
  them as a colored chip (green / amber / red) so the user sees Inderes' own
  call before reading the synthesis prose.
- **Follow-up suggestion chips** below the synthesis (PR #28): LEAD generates
  three short, clickable next-question chips ("💡 Voisit kysyä myös: …"). The
  chips are rendered as Streamlit buttons that re-submit on click. The chips
  list comes from a structured tail block in the LEAD prompt; if the model
  omits it, the UI just doesn't render chips.
- **Clickable Inderes source links** in the synthesis "Lähteet:" footer and
  in each subagent's output (PR #29). Tool results are post-processed so any
  `pageUrl` / `url` / `threadUrl` field is woven back into the markdown as a
  proper link to inderes.fi rather than a bare tool-name token.
- **Persona-styled, descriptive live status box** during query execution
  (PR #23): replaces the generic "LEAD"/"Subagentit" labels with one-line
  state descriptions in the persona color, e.g. `▲ aino-quant: hakee P/E:tä
  ja tavoitehintaa…`. Driven by phase + classification context so the user
  can read what's happening rather than just seeing a spinner.

### Added — infrastructure (durable OAuth on Streamlit Cloud)

- **GitHub Action cron `refresh-inderes-tokens.yml`** runs every 15 min and
  refreshes the Inderes OAuth tokens via the gist mirror (PR #25). Solves the
  Streamlit Cloud failure mode where containers idle long enough that the
  refresh-token rotation chain breaks. The cron keeps the Keycloak SSO
  session warm without requiring a real user query. Same gist (configured by
  `INDERES_TOKENS_GIST_ID`) is shared between the cron and the running app;
  the app pulls fresh tokens on each cold start.
- **Force gist pull on first auth call** (PR #27): the previous `pull only on
  cache miss` policy meant a stale local `tokens.json` survived restarts and
  blocked the rotation chain. Now we always pull the gist version once at
  startup; the local file is only authoritative once we've confirmed it
  matches the gist.
- **Debug logging for secrets→env bridge + gist visibility** (PR #26): logs
  whether each Streamlit secret bridged to env, and whether the gist ID/token
  are visible at OAuth time. Made it possible to diagnose
  "tokens persist locally but not on cloud" failures without speculation.

### Added — Streamlit UI ("Trading Desk" visual layer)

- Bloomberg-style dark theme: JetBrains Mono throughout, amber accents, agent
  glyphs (◆ LEAD, ▲ QUANT, ■ RESEARCH, ● SENTIMENT, ✦ PORTFOLIO).
- Hero panel with brand equation `INDERES + MCP + AGENTIT = INSIGHTS` + agent
  roster.
- Sidebar: red disclaimer at top (single source of truth for legal notice),
  architecture summary, GitHub CTA, agent personas with descriptions,
  recent runs list.
- Routing card with colored domain pills + free-form `PERUSTELU` (pink/violet
  accent so prose reasoning is distinct from categorical fields).
- Per-agent rows in the activity log expander: glyph + role + model + status
  badge; full structured output renders inline below each row.
- `CustomStatus` widget replaces `st.status` — pulsing CSS-only dot
  indicator for state, no Material Symbols icon-font race conditions.
- Markdown table + strikethrough rendering enabled for subagent output.
- Python sandbox stdout (e.g. `print(df)` results) auto-detected and wrapped
  in a green-bordered ```output``` block, distinct from the blue-bordered
  source-code blocks.
- `.streamlit/config.toml` sets primary color to amber so Streamlit's own
  chrome (chat input focus ring, progress bars) is on-brand.

### Added — agent reasoning visibility (#3 from BACKLOG.md)

- Mandatory `**Ajatus:**` thought-trace line at the top of every subagent
  response — surfaces tool-selection reasoning before the structured answer.
  Violet-bordered italic styling in `.ia-agent-output`.
- Mandatory `**💭 Perustelut:**` reasoning callout at the top of every LEAD
  synthesis — meta-level commentary on how the subagents' outputs were
  combined. Amber-bordered styling in `.ia-lead-answer`, distinct from the
  subagents' violet so visual hierarchy is preserved.

### Added — date awareness in prompts

- `load_prompt()` now prepends a `# CURRENT DATE` header (ISO + Finnish
  weekday) to every loaded subagent prompt. Without this, Gemini was
  answering "tänään 14.5.2025" when the system date was 2026-05-03.
- `today_prompt_prefix()` also prefixes every per-query user prompt with
  the same date stamp (belt-and-suspenders against system-instruction
  attention loss in long contexts).

### Added — durable OAuth token persistence

- New optional GitHub Gist mirror for `tokens.json`. Configure
  `INDERES_TOKENS_GIST_ID` and `INDERES_TOKENS_GH_TOKEN` and the agent
  pushes refreshed tokens to a private gist on every refresh, pulls from
  the gist on cold start. Solves the Streamlit Cloud problem where
  refresh-token rotation eats itself across container restarts.
- See `ui/DEPLOY.md §6.5` for setup.

### Fixed

- Material Symbols icon font no longer overridden by the global mono font
  rule (fixed `keyboard_double_arrow_right` ligature text in sidebar
  collapse arrow + `check_circle` overlap on status widget).
- Markdown tables in subagent output now render correctly (was missing
  `table` extension on `MarkdownIt("commonmark")`).
- Raw Python source from QUANT (no fences) auto-wraps in ```python``` so
  it renders as code instead of as headers/paragraphs.
- Trace-expander toggling no longer auto-scrolls Chrome to the bottom of
  the page (`overflow-anchor: none` + JS scrollY restore on summary
  click).

### Removed

- "📜 Täydellinen ajoloki" expander — was rendering the full narrative.md
  inline for every old assistant message on every Streamlit rerun, the
  dominant slowdown as chat history grew. The narrative.md file is still
  written to disk by the pipeline.
- Daily-quota progress bar from the sidebar — cap mechanism still works
  server-side; just don't surface the count.

### Reverted

- Tightened thought-trace format experiment (PR #24, reverted in the same
  series): forcing a one-line `**Ajatus:**` produced more model refusals
  than it solved rendering quirks. Original looser rubric restored.

### Parked

- **LEAD on Pro-tier model toggle** (`feat/lead-pro-toggle` branch, not
  merged). Goal: let the user opt-in to `gemini-2.5-pro` for the synthesis
  step only — bigger reasoning, better synthesis, only one extra LLM call
  per query so cost impact is small. Blocked on a MAF / Gemini compatibility
  issue: Pro rejects requests with `Function calling config is set without
  function_declarations` even though LEAD has `tools=None`. Three attempts
  in `_prepare_config()` to clear `tool_config` / `tools` when no function
  declarations are present did not unblock it. The branch keeps the WIP and
  a debug-logging hook (`INDERES_DEBUG_GEMINI_CONFIG=1`) for whoever picks
  it up next; root cause is in MAF's internal config building.

---

## [0.1.0] — 2026-05-01

Initial release. The system is functionally complete: it ingests natural-language
stock-research questions, routes them across four specialized subagents, and
synthesizes a final answer with sources. Tested end-to-end against real Inderes
MCP and paid Gemini.

### Added — core architecture

- Five-agent system on Microsoft Agent Framework 1.0+: `aino-lead` orchestrator
  plus four specialized subagents (`aino-quant`, `aino-research`,
  `aino-sentiment`, `aino-portfolio`).
- Each subagent gets a focused subset of Inderes MCP tools (3–8 tools each, not
  all 16) — improves tool-call accuracy materially over a monolithic agent.
- Lead has no tools; synthesizes subagent outputs from a structured prompt.
- Router uses structured-output Gemini call (JSON) with few-shot examples.
- Workflow uses `asyncio.gather` + `Semaphore(MAX_CONCURRENT_AGENTS)` instead of
  MAF's `ConcurrentBuilder` — runtime-decided fan-out for comparison queries
  and a hard quota cap.

### Added — Gemini fallback

- `FallbackGeminiChatClient` subclass with primary→retry→fallback chain.
- Default models: primary `gemini-3.1-flash-lite-preview`, fallback
  `gemini-2.5-flash`. Both are free-tier-eligible.
- Fallback policy: 1 retry on primary with `RETRY_DELAY_MS`; switch to fallback
  on persistent 503 or any 429; fallback gets 2 attempts with 2 s/4 s backoff.
- `last_used_model` recorded per chat client so the trace and `narrative.md`
  show which model handled each request.
- `QuotaExhaustedError` raised when both primary and fallback exhaust quota.
- No reference to `gemini-2.5-pro` anywhere — quota is zero on free tier.

### Added — Inderes MCP integration

- OAuth 2.0 Authorization Code + PKCE flow against Inderes' Keycloak SSO
  (`src/inderes_agent/mcp/oauth.py`):
  - Discovery from `/.well-known/oauth-protected-resource` (RFC 9728), then
    `/.well-known/openid-configuration`.
  - Localhost callback server handles the redirect.
  - Tokens cached at `~/.inderes_agent/tokens.json` with `0600` permissions.
  - Refresh-token reuse on subsequent runs.
- `_InderesBearerAuth(httpx.Auth)` injects the latest cached token per request,
  handling refresh-on-expiry transparently.
- `prefetch_token()` called eagerly in `__main__.py` so concurrent agent builds
  share the cached token instead of racing four OAuth flows.
- `_SanitizingMCPTool` subclass strips `$schema`, `$id`, `$ref`, `$defs`,
  `$comment` from tool input schemas after `connect()`. Inderes' MCP schemas
  include these JSON-Schema metadata fields; Gemini's `FunctionDeclaration`
  Pydantic validator rejects them.
- `load_prompts=False` on every MCP tool: Inderes MCP doesn't implement
  `prompts/list`. Default `load_prompts=True` would crash with `Method not found`.

### Added — observability

- Per-run directory at `~/.inderes_agent/runs/<timestamp>/` containing:
  `query.txt`, `routing.json`, `subagent-NN-<domain>.json`, `synthesis.txt`,
  `meta.json`, `console.log`, `narrative.md`.
- `narrate.py` parses `console.log` (extracts function-call timings) and JSON
  files into a human-readable markdown narrative with routing decision,
  per-tool-call timeline, per-subagent outputs, synthesis, and statistics.
- REPL slash commands: `/explain`, `/trace`, `/last`, `/runs`, `/agents`,
  `/clear`, `/help`, `/exit`.
- One-shot mode auto-prints a compact subagent trace plus paths to the run log
  and `narrative.md`.
- OpenTelemetry tracer with `ConsoleSpanExporter` configured (MAF emits spans
  natively).

### Added — CLI

- `rich` for terminal output: markdown answers, tables, error panels.
- `prompt_toolkit` for REPL input with history.
- Inline progress lines per phase (router → subagents → synthesis) so users
  don't think the system is hung during multi-second waits.
- Standalone `scripts/diag.py` that probes Gemini and MCP connectivity
  independently with per-step timing.
- `scripts/explain.py` regenerates `narrative.md` for any past run.

### Added — tests

- 13 unit tests covering:
  - Router JSON parsing (with code fences, prose leaks, plain JSON)
  - `QueryClassification` Pydantic validation
  - `FallbackGeminiChatClient`: 503 retry, 429 quota exhaustion,
    success-without-fallback paths
  - Workflow: per-company fan-out for comparisons, no fan-out for
    single-domain queries, concurrency cap enforcement
- End-to-end tests against real services not in CI (require credentials and
  consume Gemini quota).

### Build environment

- Python 3.11+ required; 3.13 in development via `uv`-managed CPython.
- `uv` recommended over plain pip for install speed and ARM-native Python
  management.
- `agent-framework-gemini` requires `--pre` flag (currently alpha-versioned on
  PyPI as `1.0.0aN`).
- ARM-native Python required on Apple Silicon: Intel Python via Rosetta 2 is
  ~10× slower for cold imports.
- 20+ GB free disk space recommended: APFS becomes unstable above ~90 % capacity
  (manifests as `mmap` failures, `bus error`, truncated reads — affecting both
  the application and git).

### Known limitations

- Synthesis quality is bounded by the lite-tier model on free Gemini. Paid tier
  enables upgrading the lead to `gemini-2.5-pro` (~few €/month additional)
  without changing the rest of the stack.
- During Gemini-side capacity spikes, both primary and fallback can return 503
  simultaneously. The system gracefully degrades (lead synthesizes from
  whichever subagents succeeded) but the failed subagents return empty data
  that the lead has to acknowledge.
- Tool-call attribution in `narrative.md` is heuristic. Tools unique to one
  agent (e.g. `get-fundamentals`) attribute correctly; tools shared across
  agents (e.g. `search-companies`) are marked `[shared]`.
- The system doesn't implement Magentic-One-style dynamic re-planning. If a
  subagent fails, the lead does its best with the remaining outputs but can't
  replan the workflow to compensate.

---

## Roadmap (not yet implemented)

Ideas worth exploring; none are committed.

- Upgrade only the lead to a stronger model (e.g. `gemini-2.5-pro`) for better
  synthesis quality without 4× cost on subagents.
- ~~Web UI via Streamlit hosted on Streamlit Community Cloud with a single
  pre-cached OAuth token (personal-use deployment).~~ Implemented in
  [unreleased]; tokens persist via optional GitHub Gist mirror. See
  `BACKLOG.md` for further agentic-improvement ideas.
- Streaming synthesis output in the REPL (the streaming path in
  `FallbackGeminiChatClient` is wired but not used by the current REPL flow).
- Automatic retry-the-whole-query if too many subagents fail simultaneously
  (rather than letting the lead degrade).
- Per-day quota usage display in `/trace` (currently you have to consult the
  Google AI Studio dashboard).
- Time-window filtering for `aino-research` to avoid pulling stale reports
  when the user explicitly wants only recent material.
