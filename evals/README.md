# `evals/` — eval foundation

Three layers, each producing actionable signal about the agent
pipeline's quality.

## Layout

| Path | What |
|---|---|
| `judge_selection.md` | Why we picked Gemini 2.5 Pro as judge (benchmark-backed, May 2026) |
| `findings_2026-05-09.md` | Heikkoudet löydetty 183 oikean ajon analyysistä (baseline) |
| `findings_2026-05-10.md` | Status audit — the four 2026-05-09 fail-cases were all already fixed by commits 5e5dea7 / 80c6fd0 / 2039967 / 870749a before re-baselining. Re-baseline cadence added as outstanding action. |
| `golden.yaml` | Eval cases (`case_001` … `case_008`+). Each has `hard` (deterministic) and `soft` (LLM-graded) assertions. **Structural validation is CI-gated** via `tests/test_evals_yaml.py` (9 tests on every push, no live LLM run). |
| `rubric.md` | Rubric prompt the LLM-judge sees |
| `judge.py` | `JudgeBackend` Protocol + `GeminiJudge` impl. Designed so GPT-4.1 can be added later |
| `runner.py` | Orchestrator. Loads golden, runs hard asserts, calls judge, writes report |
| `sample_queries.sql` | Diagnostic SQL against the runs index |
| `results/` | Timestamped output dirs (gitignored except first baseline) |
| `known-cases.md` | Hand-picked failure cases — feed into golden.yaml as new cases |

## Quick start

```bash
# 1. Build / refresh the run index from ~/.inderes_agent/runs/
python scripts/build_runs_index.py

# 2. Run all eval cases (hard-only — no LLM judge)
python evals/runner.py --hard-only

# 3. Run with LLM judge (needs GEMINI_API_KEY in env or .env)
python evals/runner.py

# 4. Run a single case
python evals/runner.py --case case_001_comparison_routing

# 5. Inspect results
cat evals/results/latest/report.md
```

## Tier roadmap

The eval foundation is built in three layers, each strictly more
capable than the last. We are currently at **Tier 1**.

| Tier | What | Status | Cost |
|---|---|---|---|
| 0 | SQLite index of all runs + 10 diagnostic SQL queries | ✅ done | free |
| 1 | golden.yaml + Gemini Pro judge + report.md | ✅ done | ~$0.05 / 6-case run |
| 2 | Supabase migration — runs + judgments queryable cross-device | 🚧 planned (BACKLOG §8) | $0 (existing project) |
| 3 | Autonomous nightly cron with repair-agent + auto-fixes branch | 🚧 planned (BACKLOG §10) | ~$10 / month |

## Adding a new case

When a user 👍/👎 surfaces a bug, or a code review finds a regression:

1. Add an entry to `golden.yaml` with `id`, `query_match`, `rationale`,
   and at least one `hard` assertion that captures the bug deterministically.
2. Run `python evals/runner.py --case <id>` and verify it fails today
   on the captured run.
3. Fix the bug in the pipeline, rebuild the index, re-run the case,
   confirm it passes.
4. Commit the case — it now guards against regression.

The deterministic assertions are the contract. Soft (LLM-judge) scores
are *signal*, not ground truth — they help spot quality drift across
versions but should not gate ship/no-ship decisions on their own.

## Adding a different judge backend

`judge.py` exposes a `JudgeBackend` Protocol. To add e.g. GPT-4.1 for
cross-family validation:

1. Implement `OpenAIJudge` with the same `grade()` signature.
2. Wire it into `get_judge_backend()` in `judge.py`.
3. Configure with `JUDGE_BACKEND=gpt-4.1` env var.

The runner stays unchanged. See `judge_selection.md` for why GPT-4.1
is the recommended cross-family validator (Arena-Hard primary judge,
low hallucination on grounded summarisation).

## Notes on Gemini 2.5 Pro as judge

- Pro REQUIRES thinking mode (`thinking_budget=0` returns 400). Set
  `max_output_tokens=8192` to leave headroom — at 2048 the thinking
  block consumed the budget and we got empty responses.
- Same-family bias: Gemini judging Gemini Flash Lite outputs
  inflates absolute scores ~5–10 % vs cross-family judges. Delta
  detection (regression sensitivity) is preserved at ~98 %.
- For absolute calibration, run weekly cross-checks with GPT-4.1 once
  the cron lands (Tier 3).
