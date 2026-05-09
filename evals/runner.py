"""Eval runner — Tier 1.

Loads ``evals/golden.yaml``, picks the most-recent matching run from
the SQLite index for each case, runs hard assertions against the
indexed artifacts, optionally calls the LLM-judge for soft criteria,
and writes a timestamped report.

Two modes:
  - **Hard-only** (no judge backend configured) — instant, no LLM
    cost, surfaces structural regressions.
  - **Full** (judge backend available) — adds qualitative grading.

Usage::

    python evals/runner.py                     # hard-only or full per env
    python evals/runner.py --hard-only         # skip the judge even if available
    python evals/runner.py --case case_001     # run a single case

Output:
    evals/results/<run_ts>/results.json   # machine-readable
    evals/results/<run_ts>/report.md      # human-readable summary
    evals/results/latest -> <run_ts>/     # symlink for convenience
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Allow running as a script from repo root: add this dir to sys.path so
# `from judge import ...` resolves regardless of cwd.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from judge import JudgeBackend, get_judge_backend  # noqa: E402


REPO_ROOT = _THIS_DIR.parent
DEFAULT_DB = Path.home() / ".inderes_agent" / "evals" / "runs_index.sqlite"
DEFAULT_RUNS_DIR = Path.home() / ".inderes_agent" / "runs"
DEFAULT_GOLDEN = REPO_ROOT / "evals" / "golden.yaml"
DEFAULT_RUBRIC = REPO_ROOT / "evals" / "rubric.md"
DEFAULT_RESULTS_ROOT = REPO_ROOT / "evals" / "results"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class HardResult:
    expression: str
    passed: bool
    error: str | None = None


@dataclass
class CaseResult:
    case_id: str
    query_match: str
    matched_run_ids: list[str]
    hard_results: list[HardResult] = field(default_factory=list)
    soft_judgment: dict[str, Any] | None = None
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def hard_pass_count(self) -> int:
        return sum(1 for r in self.hard_results if r.passed)

    @property
    def hard_fail_count(self) -> int:
        return sum(1 for r in self.hard_results if not r.passed)


# ---------------------------------------------------------------------------
# Run-loading from SQLite + filesystem
# ---------------------------------------------------------------------------


def load_run_context(
    run_id: str, conn: sqlite3.Connection, runs_dir: Path
) -> dict[str, Any]:
    """Load a single run's full context for evaluation.

    Reads the indexed columns from SQLite, and the synthesis / paattely
    text from the filesystem. Tool calls come from the index too.
    """
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if not row:
        return {}
    cols = [d[0] for d in conn.execute("PRAGMA table_info(runs)").fetchall()]
    # PRAGMA returns (cid, name, type, ...); we want column names only.
    col_names = [c[1] for c in conn.execute("PRAGMA table_info(runs)").fetchall()]
    record = dict(zip(col_names, row))

    domains = json.loads(record.get("domains") or "[]")
    companies = json.loads(record.get("companies") or "[]")

    tool_calls = [
        {
            "agent_index": r[0],
            "agent_domain": r[1],
            "call_id": r[2],
            "tool_name": r[3],
            "arguments_json": r[4],
            "item_count": r[5],
            "has_error": bool(r[6]),
            "error_text": r[7],
        }
        for r in conn.execute(
            "SELECT agent_index, agent_domain, call_id, tool_name, "
            "arguments_json, item_count, has_error, error_text "
            "FROM tool_calls WHERE run_id = ? ORDER BY agent_index, rowid",
            (run_id,),
        ).fetchall()
    ]

    # Synthesis text from disk (not indexed in full).
    syn_path = runs_dir / run_id / "synthesis.txt"
    synthesis = syn_path.read_text(encoding="utf-8") if syn_path.exists() else ""

    return {
        "run_id": run_id,
        "ts": record.get("ts"),
        "query": record.get("query"),
        "routing_domains": domains,
        "routing_companies": companies,
        "routing_is_comparison": bool(record.get("is_comparison")),
        "routing_reasoning": record.get("routing_reasoning"),
        "duration_s": record.get("duration_s"),
        "subagent_count": record.get("subagent_count"),
        "subagent_errors": record.get("subagent_errors"),
        "tool_calls": tool_calls,
        "agreements_count": record.get("agreements_count"),
        "conflicts_count": record.get("conflicts_count"),
        "isolated_count": record.get("isolated_count"),
        "paattely_kind": record.get("paattely_kind"),
        "has_synthesis": bool(record.get("has_synthesis")),
        "has_warning_phrase": bool(record.get("has_warning_phrase")),
        "synthesis": synthesis,
    }


def find_matching_runs(
    query_match: str, conn: sqlite3.Connection, n: int = 1
) -> list[str]:
    """Pick most-recent runs whose query contains the match string (case-insensitive).

    `n=1` for normal cases; `n=3+` for reproducibility cases that
    compare across multiple runs.
    """
    rows = conn.execute(
        "SELECT run_id FROM runs "
        "WHERE has_query = 1 AND lower(query) LIKE ? "
        "ORDER BY ts DESC LIMIT ?",
        (f"%{query_match.lower()}%", n),
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Hard-assertion runner
# ---------------------------------------------------------------------------


# A namespaced object so assertions can write `routing.domains` instead
# of `routing_domains`.
class _Bag:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)

    def __repr__(self) -> str:  # debug only
        return f"<Bag {self.__dict__!r}>"


def _eval_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Build the eval-globals dict so assertions can reference natural
    names like `routing.domains`, `tc_count_per_agent`, etc."""
    routing = _Bag(
        domains=ctx.get("routing_domains") or [],
        companies=ctx.get("routing_companies") or [],
        is_comparison=bool(ctx.get("routing_is_comparison")),
        reasoning=ctx.get("routing_reasoning"),
    )
    # Per-agent tool-call counts.
    tc_count_per_agent: dict[str, int] = {}
    for tc in ctx.get("tool_calls") or []:
        ag = tc.get("agent_domain") or "unknown"
        tc_count_per_agent[ag] = tc_count_per_agent.get(ag, 0) + 1

    return {
        "routing": routing,
        "duration_s": ctx.get("duration_s") or 0,
        "subagent_count": ctx.get("subagent_count") or 0,
        "subagent_errors": ctx.get("subagent_errors") or 0,
        "agreements_count": ctx.get("agreements_count") or 0,
        "conflicts_count": ctx.get("conflicts_count") or 0,
        "isolated_count": ctx.get("isolated_count") or 0,
        "paattely_kind": ctx.get("paattely_kind"),
        "has_synthesis": bool(ctx.get("has_synthesis")),
        "has_warning_phrase": bool(ctx.get("has_warning_phrase")),
        "synthesis": ctx.get("synthesis") or "",
        "tc_count_per_agent": tc_count_per_agent,
        # Stdlib helpers commonly useful in expressions.
        "median": statistics.median,
        "len": len,
        "all": all,
        "any": any,
        "max": max,
        "min": min,
        "sum": sum,
    }


def run_hard_assertions(
    case: dict[str, Any], ctx: dict[str, Any] | list[dict[str, Any]]
) -> list[HardResult]:
    """Evaluate hard assertions. ``ctx`` is dict for single-run cases,
    list for multi-run reproducibility cases (case has n_runs_to_compare).

    Each assertion is a string Python expression, eval'd in the context
    namespace built by ``_eval_context``. We use eval() — the strings
    come from the repo-tracked golden.yaml, same trust level as code.
    """
    results: list[HardResult] = []
    if isinstance(ctx, list):
        # Multi-run case — context exposes both `runs` (list) and `runs[0]`
        # convenience as the first run. Each run gets a _Bag wrapper so
        # `r.routing.domains` works.
        if not ctx:
            return [
                HardResult(expr, False, "no matching runs found")
                for expr in case.get("hard") or []
            ]
        run_bags = []
        for c in ctx:
            globals_for_one = _eval_context(c)
            # Wrap each run as a small bag with the fields tests reference.
            run_bags.append(_Bag(
                routing=globals_for_one["routing"],
                duration_s=globals_for_one["duration_s"],
                has_synthesis=globals_for_one["has_synthesis"],
            ))
        eval_globals = _eval_context(ctx[0])
        eval_globals["runs"] = run_bags
        for expr in case.get("hard") or []:
            try:
                # Pass our context as globals (2nd arg) so generator/list
                # comprehensions inside the expression can see names —
                # comprehensions create their own scope and ignore the
                # eval-locals (3rd arg) for outer-name lookups.
                eval_globals["__builtins__"] = {"True": True, "False": False, "None": None}
                ok = bool(eval(expr, eval_globals))
                results.append(HardResult(expr, ok))
            except Exception as exc:  # noqa: BLE001
                results.append(HardResult(expr, False, repr(exc)))
        return results

    # Single-run case.
    eval_globals = _eval_context(ctx)
    for expr in case.get("hard") or []:
        try:
            ok = bool(eval(expr, {"__builtins__": {}}, eval_globals))
            results.append(HardResult(expr, ok))
        except Exception as exc:  # noqa: BLE001
            results.append(HardResult(expr, False, repr(exc)))
    return results


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def run_eval(
    golden_path: Path = DEFAULT_GOLDEN,
    rubric_path: Path = DEFAULT_RUBRIC,
    db_path: Path = DEFAULT_DB,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    results_root: Path = DEFAULT_RESULTS_ROOT,
    case_filter: str | None = None,
    hard_only: bool = False,
    backend_name: str | None = None,
) -> dict[str, Any]:
    """Run the eval suite. Returns the full results dict (and writes to disk)."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"Index not found at {db_path}. Build first with "
            "scripts/build_runs_index.py."
        )
    if not golden_path.exists():
        raise FileNotFoundError(f"golden.yaml not found at {golden_path}")

    cases = yaml.safe_load(golden_path.read_text(encoding="utf-8")).get("cases", [])
    if case_filter:
        cases = [c for c in cases if c.get("id") == case_filter]
        if not cases:
            raise ValueError(f"No case matched filter {case_filter!r}")

    rubric = rubric_path.read_text(encoding="utf-8")
    judge: JudgeBackend | None = None if hard_only else get_judge_backend(backend_name)

    conn = sqlite3.connect(db_path)
    try:
        results_per_case: list[CaseResult] = []
        for case in cases:
            case_id = case["id"]
            query_match = case.get("query_match", "")
            n_runs = case.get("n_runs_to_compare", 1)

            run_ids = find_matching_runs(query_match, conn, n=n_runs)
            cr = CaseResult(case_id=case_id, query_match=query_match, matched_run_ids=run_ids)
            if not run_ids:
                cr.skipped = True
                cr.skip_reason = "no matching runs in index"
                results_per_case.append(cr)
                continue

            if n_runs > 1:
                contexts = [
                    load_run_context(rid, conn, runs_dir) for rid in run_ids
                ]
                cr.hard_results = run_hard_assertions(case, contexts)
                primary_ctx = contexts[0]
            else:
                primary_ctx = load_run_context(run_ids[0], conn, runs_dir)
                cr.hard_results = run_hard_assertions(case, primary_ctx)

            # Soft (LLM-judge) — primary run only.
            if judge is not None and case.get("soft"):
                try:
                    cr.soft_judgment = judge.grade(case, primary_ctx, rubric)
                except Exception as exc:  # noqa: BLE001
                    cr.soft_judgment = {"_error": f"judge raised: {exc!r}"}

            results_per_case.append(cr)
    finally:
        conn.close()

    # Materialise.
    return _write_results(results_per_case, results_root, judge)


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------


def _write_results(
    results: list[CaseResult],
    results_root: Path,
    judge: JudgeBackend | None,
) -> dict[str, Any]:
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    out_dir = results_root / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "ts": ts,
        "judge": judge.name if judge else None,
        "cases": [
            {
                "case_id": r.case_id,
                "query_match": r.query_match,
                "matched_run_ids": r.matched_run_ids,
                "hard_pass": r.hard_pass_count,
                "hard_fail": r.hard_fail_count,
                "hard_results": [asdict(h) for h in r.hard_results],
                "soft_judgment": r.soft_judgment,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
            }
            for r in results
        ],
    }

    (out_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(
        _render_report_md(payload), encoding="utf-8"
    )

    # Update `latest` convenience link.
    latest = results_root / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(ts, target_is_directory=True)
    except OSError:
        # Filesystem doesn't support symlinks (e.g., some Streamlit
        # Cloud environments). Skip — the timestamped dir is enough.
        pass

    print(f"\nresults written to {out_dir}")
    return payload


def _render_report_md(payload: dict[str, Any]) -> str:
    """Render a scannable markdown report."""
    lines = [f"# Eval results — {payload['ts']}\n"]
    judge = payload.get("judge") or "*hard-only (no LLM judge)*"
    lines.append(f"**Judge backend:** {judge}\n")

    total_hard_pass = sum(c["hard_pass"] for c in payload["cases"])
    total_hard_fail = sum(c["hard_fail"] for c in payload["cases"])
    skipped = sum(1 for c in payload["cases"] if c["skipped"])
    lines.append(
        f"**Hard assertions:** {total_hard_pass} pass / "
        f"{total_hard_fail} fail across {len(payload['cases']) - skipped} "
        f"evaluated cases ({skipped} skipped).\n"
    )

    lines.append("## Per-case results\n")
    for c in payload["cases"]:
        emoji = "⏭" if c["skipped"] else ("✅" if c["hard_fail"] == 0 else "❌")
        lines.append(f"### {emoji} `{c['case_id']}`\n")
        lines.append(f"**Query:** `{c['query_match']}`\n")
        if c["skipped"]:
            lines.append(f"*Skipped:* {c['skip_reason']}\n")
            continue
        if c["matched_run_ids"]:
            lines.append(f"**Matched runs:** {', '.join(c['matched_run_ids'])}\n")
        lines.append(f"**Hard:** {c['hard_pass']}/{c['hard_pass'] + c['hard_fail']} passed\n")
        for h in c["hard_results"]:
            mark = "✓" if h["passed"] else "✗"
            err = f" *(error: {h['error']})*" if h["error"] else ""
            lines.append(f"- {mark} `{h['expression']}`{err}")
        lines.append("")
        if c["soft_judgment"]:
            lines.append("**Soft (LLM-judge):**")
            sj = c["soft_judgment"]
            if "_error" in sj:
                lines.append(f"- ⚠ judge error: {sj['_error']}")
            else:
                scores = sj.get("scores") or {}
                for crit, blob in scores.items():
                    score = blob.get("score") if isinstance(blob, dict) else blob
                    rationale = blob.get("rationale", "") if isinstance(blob, dict) else ""
                    lines.append(f"- **{crit}**: {score}/5 — {rationale}")
                if "overall_quality" in sj:
                    lines.append(f"- **overall**: {sj.get('overall_quality')}/5 — {sj.get('overall_rationale', '')}")
                if "global_flags" in sj:
                    flags = sj["global_flags"]
                    flag_parts = ", ".join(f"{k}={v}" for k, v in flags.items())
                    lines.append(f"- *flags:* {flag_parts}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--case", type=str, default=None, help="Run only one case")
    parser.add_argument("--hard-only", action="store_true", help="Skip the LLM judge")
    parser.add_argument("--backend", type=str, default=None, help="Judge backend (gemini)")
    args = parser.parse_args()

    payload = run_eval(
        golden_path=args.golden,
        rubric_path=args.rubric,
        db_path=args.db,
        runs_dir=args.runs_dir,
        results_root=args.results_root,
        case_filter=args.case,
        hard_only=args.hard_only,
        backend_name=args.backend,
    )

    # Brief stdout summary.
    total_pass = sum(c["hard_pass"] for c in payload["cases"])
    total_fail = sum(c["hard_fail"] for c in payload["cases"])
    print(f"hard: {total_pass} pass / {total_fail} fail")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
