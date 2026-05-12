# Human-in-the-Loop (HITL) — proposal

**Status:** Draft proposal — **not yet implemented**
**Date drafted:** 2026-05-10
**Last review:** 2026-05-12 — still applicable; tracked in BACKLOG §1 Wk 3
**Owner:** core
**Track:** Originally Wk 2 "learning feature" — deferred to Wk 3+ as
Reflexion was also deferred (no cost-doubling has materialised yet)

> **Status update 2026-05-12.** HITL Step 1 (pre-flight cost gate) is
> BACKLOG'd but unshipped. Reflexion + retry was also deferred
> (BACKLOG §1 #2 still 💭), so the cost-doubling concern in §1.2
> hasn't yet materialised in practice. When Reflexion lands, this
> proposal becomes a prerequisite.
>
> Relevant developments since this proposal was drafted:
>
> - **Hard limits at orchestration boundary** shipped Wk 1 (OWASP T1
>   `max_iter` / `max_tool_calls` / `max_cost` / `max_duration` /
>   kill-switch). These are the *automatic* ceiling. HITL would add a
>   *user-visible* pre-flight gate before the request goes out.
> - **Project spend cap** (Google AI Studio billing-side limit) is
>   now a known failure mode — see TROUBLESHOOTING.md. A pre-flight
>   HITL gate would have surfaced "you have $X left this month, this
>   query will cost ~$Y" cleanly. Different layer than the in-app
>   limits, but related UX.

---

## 1. Why this exists

Two motivations, ranked:

### 1.1 Trust gap that LESSONS.md keeps surfacing
> *"Multi-agent systems hide their work by default. Hidden work erodes trust."*

Wk 1 shipped persona glyphs, clickable sources, live status lines and the
👍/👎 widget. They closed the *retrospective* trust gap — user can audit
what happened. They do **not** close the *prospective* gap — user has no
idea what is *about to* happen, or what it will cost, before launch.

### 1.2 Reflexion will silently double the bill
Wk 2 introduces Reflexion: automatic retry on weird output. Without
cost visibility, a single user query can run the pipeline 2× without
the user noticing. Hard limits prevent infinite loops; they do not
prevent surprise. HITL closes that gap by surfacing the *expected*
cost up-front and showing each retry against the budget.

### 1.3 Learning hypothesis (the real reason this is a feature, not a button)

**We don't know how good our cost/duration estimates are.** The Tier 0
SQLite index has 183 historical runs, but most of them are similar
single-company queries. Multi-company fan-outs, valuation-heavy runs,
and Pro-tier escalations are sparse in the dataset. The estimator we
build *will* be wrong on edge cases.

HITL is therefore a learning loop:
- The estimator predicts before the run.
- The actual cost is recorded after the run.
- Per-class accuracy (mean-absolute-error) goes into the run-log.
- We decide *with data* whether the threshold-based gate is too loose
  (annoying), too tight (surprises), or about right.

After 2 weeks of real use we should have:
- a calibrated estimator with documented error bars per query class,
- a gate threshold tuned to the user's actual annoyance/surprise tradeoff,
- a clear answer to whether mid-run checkpoints (Level 2) are worth building.

**Without the learning instrumentation HITL is shallow — a button. With
it, HITL is a feedback mechanism that improves itself.**

---

## 2. Scope (Level 1 MVP)

### In
- Pre-flight estimator: predicts duration_s, tool_calls, cost_usd from
  the LEAD planner output before any subagent runs.
- Risk-tier threshold: queries above `threshold_cost_usd` OR
  `threshold_duration_s` go through the approval gate. Below thresholds
  run silently as today.
- Approval card UI: shows plan breakdown, estimate, and Suorita / Peruuta
  buttons.
- Token + cost tracking: `usage_metadata` captured from every Gemini
  call, written to `run_log.json`.
- Estimator accuracy log: every run records `predicted_*` vs `actual_*`
  for offline analysis.

### Out (later levels, do not build now)
- Mid-run checkpoint ("50 % budget used, continue?") — Level 2, defer
  until Walkthrough Phase 2 (Wk 4–5).
- Risk-tier auto-tuning — Level 3, defer until ≥30 gated queries.
- Per-tool-call cost visibility — defer (MCP tools are zero-cost; LLM
  calls are the only cost source).

### Won't build
- Cost-prediction-as-a-separate-LLM-call. The planner output already
  enumerates subagents; estimation is a deterministic table lookup
  + small fudge factor, not an LLM problem.

---

## 3. Architecture

### 3.1 Data flow

```
User query
   │
   ▼
[ROUTER]                       (no change)
   │
   ▼
[LEAD PLANNER] ─ produces Plan { subagents: [...], domains: [...] }
   │
   ▼
[ESTIMATOR]    ── new       ── reads Plan, looks up historical
   │                            per-subagent baselines, returns
   │                            { duration_s, tool_calls, cost_usd,
   │                              confidence_band }
   ▼
[GATE LOGIC]   ── new       ── if cost > threshold OR duration > threshold:
   │                              show approval card, await accept/cancel
   │                            else: proceed silently
   ▼
[WORKFLOW EXECUTOR]            (no change to internals; cost-tracker
   │                            wrapper added at Gemini-client layer)
   ▼
[RUN LOG]       ── extended ── now records predicted_* alongside actual_*
                                for accuracy tracking
```

### 3.2 Module additions

| New / changed | Module | LOC est. |
|---|---|---|
| New | `src/inderes_agent/orchestration/estimator.py` | ~120 |
| New | `src/inderes_agent/orchestration/gate.py` | ~80 |
| Changed | `src/inderes_agent/llm/gemini_client.py` — capture `usage_metadata` | ~30 |
| Changed | `src/inderes_agent/observability/run_log.py` — add cost & predicted fields | ~40 |
| New | `ui/hitl_panel.py` (or section in `app.py` until Wk 3 refactor) — approval card | ~150 |
| New tests | `tests/test_estimator.py`, `tests/test_gate.py` | ~200 |

Total: ~620 LOC new + ~70 modified. Roughly one focused day.

### 3.3 Estimator inputs and method

The estimator does **not** call an LLM. It uses:

1. **Plan breakdown** from `lead_planner.py`:
   - subagents: list of (type, count) e.g. `[(RESEARCH, 3), (VALUATION, 3), (SENTIMENT, 3)]`
   - domains: which domain agents are invoked
   - flags: pro-tier? code execution? deep planner?

2. **Historical baselines** (already in Tier 0 SQLite):
   - per-subagent: mean tool calls, mean duration, mean tokens (input + output)
   - we pre-compute this once at module import; no DB query at runtime

3. **Pricing table** (Gemini Flash + Pro, hardcoded — update on price change):
   - flash: $0.075/M input, $0.30/M output
   - pro: $1.25/M input, $5.00/M output

4. **Compose** with simple linear combination + 1.2× safety factor:
   ```
   predicted_duration_s   = max(per_subagent_duration_s)  # parallel fan-out
                            + 15 (lead synthesis)
                            + 5  (planner)
   predicted_tool_calls   = sum(per_subagent_tool_calls)
   predicted_cost_usd     = sum(per_subagent_input_tokens * input_price
                                + per_subagent_output_tokens * output_price)
                            * 1.2
   ```

5. **Confidence band**: ±1σ from historical p50–p84 spread. Shown as
   `~$0.37 ± $0.12` so the user calibrates expectations.

### 3.4 Approval card UX

Plan-card structure (Streamlit `st.expander` + custom HTML):

```
🔍 Suunnitelma (klikkaa nähdäksesi yksityiskohdat)

  Vertaile Sampoa, Nordeaa ja Aktiaa kannattavuuden ja
  arvostuksen näkökulmasta.

  ├─ RESEARCH × 3 yhtiötä (rinnakkain)         ~25 s
  ├─ VALUATION × 3                              ~40 s, syvä laskenta
  ├─ SENTIMENT × 3                              ~20 s
  └─ LEAD-synteesi + konfliktintunnistus        ~15 s
                                                ─────────
                                  Yhteensä:     ~100 s
                                  Arvio:        $0.37 ± $0.12
                                  Työkalut:     ~13 kutsua

  [✅ Suorita]  [✗ Peruuta]
```

State machine (Streamlit session_state):
- `idle` → user types → `awaiting_plan` (planner runs)
- `awaiting_plan` → plan ready → if cost > threshold: `awaiting_approval`
- `awaiting_approval` → user clicks Suorita: `running`
- `awaiting_approval` → user clicks Peruuta: `cancelled` → return to `idle`
- `running` → workflow done: `complete`

### 3.5 Threshold defaults

Settings (in `settings.py`):

```python
HITL_COST_THRESHOLD_USD = 0.20
HITL_DURATION_THRESHOLD_S = 60.0
HITL_ENABLED = True  # false = always run, no gate (for nightly cron)
```

p95 of 183 historical runs: duration 30 s, est. cost ~$0.10. So 60 s
and $0.20 catch the top ~5 % of queries — plausibly the multi-company
fan-outs + Pro-escalations + walkthroughs. Tunable after 2 weeks of
real data.

---

## 4. Implementation order (1 day)

### Step 1 — Cost tracking (~2 h, foundational)
File: `src/inderes_agent/llm/gemini_client.py`

- Capture `response.usage_metadata.prompt_token_count` and
  `candidates_token_count` from every chat turn.
- Sum into a per-run `CostTracker` (new dataclass, lives in
  `observability/run_log.py` alongside other run state).
- Write `total_input_tokens`, `total_output_tokens`, `cost_usd` to
  `run_log.json`.

**Test:** `tests/test_cost_tracker.py` — synthetic Gemini response
fixtures, assert price math is correct for Flash and Pro.

### Step 2 — Estimator (~3 h)
File: `src/inderes_agent/orchestration/estimator.py`

- Module-level constants: `_BASELINE_BY_SUBAGENT_TYPE` dict (mean
  duration, tool calls, tokens) — derived from Tier 0 SQLite, hardcoded
  for now.
- `estimate_plan(plan: Plan) -> Estimate` function.
- Estimate dataclass: `predicted_duration_s`, `predicted_tool_calls`,
  `predicted_cost_usd`, `confidence_band_usd`.

**Test:** `tests/test_estimator.py` — given known plan shapes, asserts
output is in expected ranges. Goldened.

### Step 3 — Gate logic (~1 h)
File: `src/inderes_agent/orchestration/gate.py`

- `should_gate(estimate: Estimate, settings: Settings) -> bool`
- Pure function, easy to test.

**Test:** `tests/test_gate.py` — 6 cases (under both thresholds, over
each individually, over both, gate disabled, edge values).

### Step 4 — UI integration (~3 h)
- Modify `ui/app.py` to insert estimator + gate after planner, before
  workflow.
- Render approval card in same area as the existing plan-expander.
- State machine: 5 states (idle → awaiting_plan → awaiting_approval →
  running → complete).

**Test:** manual smoke + the existing eval suite. UI is hard to unit
test — accept that.

### Step 5 — Estimator accuracy logging (~1 h)
- After every run, compute `predicted_cost_usd - actual_cost_usd`,
  `predicted_duration_s - actual_duration_s`, write to run_log.
- Add a small CLI: `scripts/estimator_accuracy.py` that reads last N
  runs and prints MAE / MAPE.

---

## 5. Learning instrumentation

This is the part that turns HITL from a button into a research feature.

### 5.1 What we want to learn

| Question | Metric | Threshold for "learned" |
|---|---|---|
| Is the cost estimator accurate? | MAPE per query class | < 30 % within 2 weeks |
| Is the threshold annoying? | % of queries that hit the gate | aim for 5–15 % |
| Do users actually cancel? | cancel/(cancel+approve) ratio | aim for >5 % (else gate is theatre) |
| Does HITL change behaviour? | comparison: same user before/after — query patterns, query depth | qualitative, weekly review |
| Does Reflexion blow the budget? | pred_cost vs actual when retry fired | actual ≤ 1.5× predicted |

### 5.2 Where data lives

- Per-run: `run_log.json` gets `predicted_*`, `actual_*`, `gate_shown`,
  `user_action` ∈ {silent, approved, cancelled}.
- Aggregated: `scripts/estimator_accuracy.py` produces a markdown
  report on demand, no dashboard yet.
- Reviewed in BACKLOG.md weekly retro section.

### 5.3 Decision points (when do we know it's working?)

After 2 weeks of real use:
- If MAPE > 50 %, the estimator is broken — investigate per-class
  errors before adding Level 2.
- If cancel rate < 1 %, the gate is theatre — either lower threshold
  or remove the gate.
- If MAPE < 20 % AND cancel rate > 5 %, **build Level 2** (mid-run
  checkpoints). The accuracy is good enough to predict mid-run, and
  users actually engage with the gate.

---

## 6. Out of scope, explicitly

- **No LLM-as-estimator.** The planner already enumerated subagents;
  using an LLM to predict cost is overkill and adds another estimation
  error.
- **No mid-run pause** in v1. Adds state machine complexity and a UI
  problem (how does Streamlit pause cleanly?). Defer.
- **No tool-level cost prediction.** All MCP tools are free; the only
  cost is LLM tokens. Don't model what isn't there.
- **No nightly-cron behaviour change.** HITL_ENABLED=false in cron
  mode; the gate is a personal-use feature, not infra.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Estimator badly wrong on rare query classes | 1.2× safety factor + show confidence band; learning loop catches systematic error within 2 weeks |
| Approval gate annoys user | Threshold tuned to top ~5 % of queries; user can disable via settings; we measure annoyance via cancel/skip ratio |
| Streamlit state machine fights us | Keep it 5-state, no nesting. Test happy path manually; observe edge cases in real use. |
| Reflexion + HITL interaction (retry doubles cost mid-run) | When retry triggers, show a follow-up status line: "↻ Korjaava ajo 2/2: $X lisäkustannus". Hard cap (max_reflexion_iterations=1) prevents 3+ retries. |
| Cost tracking misses some Gemini calls (e.g. inside agent-framework SDK) | Audit every code path that creates a `ChatClient`. Ship with logging that warns when a turn arrives without `usage_metadata`. |

---

## 8. Definition of Done (Wk 2)

- [ ] Cost tracking: `run_log.json` shows tokens + cost for every run
- [ ] Estimator: 8+ test cases pass; MAPE on existing 183-run dataset < 40 %
- [ ] Gate: shows on multi-company comparison; does NOT show on single-company quick lookup
- [ ] UI: approval card renders; Suorita / Peruuta buttons work; cancelled state cleans up
- [ ] Run-log: `predicted_*` and `user_action` fields populated for all gated runs
- [ ] Threshold tuning: thresholds documented in settings.py, no code changes needed to tune
- [ ] Eval suite still passes: 12 pass / 4 fail baseline holds
- [ ] BACKLOG.md updated with §7 HITL section reflecting shipped state

---

## 9. After Wk 2: what does Level 2 look like

(Sketched here so we know where Level 1 is heading, NOT to be built now.)

Mid-run checkpoint triggers when:
- 50 % of estimated duration consumed, AND
- > 1 subagent fan-out remaining

User sees inline:
> ↻ Olen käsitellyt RESEARCH 3/3, VALUATION 1/3. Käytetty 45 s / arvio 100 s.
> Jatketaanko VALUATION 2/3 + 3/3, vai onko nykyinen riittävä?
> [✅ Jatka] [⚡ Riittää, syntetisoi nyt]

Requires:
- Cooperative pause point in `workflows.py` between subagent batches.
- Streamlit-friendly state preservation across reruns.
- ~4 h of work; needs Level 1 cost tracking as foundation.
