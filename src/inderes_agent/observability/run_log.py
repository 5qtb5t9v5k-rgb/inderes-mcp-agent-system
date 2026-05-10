"""Per-run trace persistence.

Every query produces a directory at ~/.inderes_agent/runs/<ISO-timestamp>/ containing:
  query.txt          — user question
  routing.json       — router classification (domains, companies, comparison flag, reasoning)
  subagent-N.json    — each subagent's domain, company, model used, full output text, error,
                        plus tool_calls: list of {name, arguments, result_summary, item_count, item_names}
                        (BACKLOG #10 provenance threading: ground-truth tool data alongside agent text)
  synthesis.txt      — final lead answer (Päättely JSON block already extracted)
  paattely.json      — parsed visible-reasoning JSON {disagree, resolution, uncertain, skipped}
  conflicts.json     — pre-synthesis conflict-detector output (agreements / conflicts / isolated_claims)
  meta.json          — timing, fallback events, lead model used
  console.log        — stderr capture (HTTP requests, MCP function calls, fallback events)

This gives a complete forensic record without needing to re-run the query.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ..orchestration.synthesis import ConflictReport, SynthesisTrace
from ..orchestration.workflows import WorkflowResult

RUNS_ROOT = Path.home() / ".inderes_agent" / "runs"


def new_run_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    p = RUNS_ROOT / ts
    p.mkdir(parents=True, exist_ok=True)
    return p


def attach_console_log_handler(run_dir: Path) -> logging.FileHandler:
    """Attach a FileHandler to the root logger so stderr-style logs also hit run_dir/console.log."""
    handler = logging.FileHandler(run_dir / "console.log", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
    )
    logging.getLogger().addHandler(handler)
    return handler


def detach_console_log_handler(handler: logging.FileHandler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()


def write_run(
    run_dir: Path,
    query: str,
    workflow: WorkflowResult,
    answer: str,
    lead_model: str,
    duration_s: float,
    conflict_report: ConflictReport | None = None,
    synth_trace: SynthesisTrace | None = None,
) -> None:
    (run_dir / "query.txt").write_text(query + "\n", encoding="utf-8")

    cls = workflow.classification
    (run_dir / "routing.json").write_text(
        json.dumps(
            {
                "domains": [d.value for d in cls.domains],
                "companies": cls.companies,
                "is_comparison": cls.is_comparison,
                "reasoning": cls.reasoning,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    for i, sr in enumerate(workflow.subagent_results, 1):
        (run_dir / f"subagent-{i:02d}-{sr.domain.value}.json").write_text(
            json.dumps(
                {
                    "index": i,
                    "domain": sr.domain.value,
                    "company": sr.company,
                    "model_used": sr.model_used,
                    "error": sr.error,
                    "text": sr.text,
                    "image_paths": sr.image_paths,
                    "tool_calls": [tc.to_dict() for tc in sr.tool_calls],
                    "duration_seconds": round(sr.duration_seconds, 3),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    (run_dir / "synthesis.txt").write_text(answer + "\n", encoding="utf-8")

    if conflict_report is not None:
        (run_dir / "conflicts.json").write_text(
            json.dumps(conflict_report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if synth_trace is not None and (synth_trace.paattely or synth_trace.paattely_raw):
        (run_dir / "paattely.json").write_text(
            json.dumps(
                {
                    "parsed": synth_trace.paattely,
                    "raw": synth_trace.paattely_raw,
                    "error": synth_trace.paattely_error,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # Plan-then-execute output, only present when the user enabled the
    # "Käytä pidempää suunnittelua" sidebar toggle. Persisting it lets
    # the user review LEAD's strategic plan after the run, and
    # eval-time replay can compare planned vs actual behaviour.
    if workflow.plan is not None:
        (run_dir / "plan.json").write_text(
            json.dumps(
                {
                    "raw": workflow.plan.raw_text,
                    "parsed": workflow.plan.parsed,
                    "narrative": workflow.plan.narrative,
                    "model_used": workflow.plan.model_used,
                    "duration_seconds": workflow.plan.duration_seconds,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # Alternative-valuation results — only present when user enabled the
    # "Käytä vaihtoehtoista arvonmääritystä" sidebar toggle and at least one
    # VALUATION subagent ran. Each record includes the agent's parsed
    # parameters + the deterministic engine's computed Valuation, so the run
    # is fully reconstructible offline (replay-friendly per BCBS 239).
    if synth_trace is not None and synth_trace.valuations:
        from dataclasses import asdict as _asdict
        valuation_payload = []
        for rec in synth_trace.valuations:
            payload: dict = {
                "company": rec.company,
                "parse_error": rec.parse_error,
                "raw_text": rec.raw_text,
            }
            if rec.agent_output is not None:
                payload["agent_output"] = _asdict(rec.agent_output)
            if rec.skipped is not None:
                payload["skipped"] = _asdict(rec.skipped)
            if rec.valuation is not None:
                payload["valuation"] = _asdict(rec.valuation)
            valuation_payload.append(payload)
        (run_dir / "valuation.json").write_text(
            json.dumps(valuation_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Stage timings make the cost of each phase visible — useful for the UI's
    # 🧠 Päättely panel and for debugging slow queries. They also let us spot
    # patterns like "conflict-detector dominates on small fan-outs" or
    # "fanout time scales with slowest subagent, not subagent count".
    stage_timings = {
        "fanout_seconds": round(workflow.fanout_seconds, 3),
        "conflict_detector_seconds": round(
            conflict_report.duration_seconds, 3
        ) if conflict_report else None,
        "lead_seconds": round(synth_trace.lead_seconds, 3) if synth_trace else None,
        "per_subagent": [
            {
                "index": i,
                "domain": sr.domain.value,
                "company": sr.company,
                "duration_seconds": round(sr.duration_seconds, 3),
            }
            for i, sr in enumerate(workflow.subagent_results, 1)
        ],
    }

    (run_dir / "meta.json").write_text(
        json.dumps(
            {
                "lead_model": lead_model,
                "conflict_detector_model": (
                    conflict_report.model_used if conflict_report else None
                ),
                "duration_seconds": round(duration_s, 3),
                "stage_timings": stage_timings,
                "fallback_events": workflow.fallback_events,
                "subagent_count": len(workflow.subagent_results),
                "subagent_errors": sum(1 for r in workflow.subagent_results if r.error),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 👍/👎 user feedback — Wk 1 #4 (sprint roadmap 2026-05-09)
#
# Feedback is persisted as a sibling file `feedback.json` inside the run dir
# (NOT folded into write_run() because feedback arrives AFTER the user has
# read the answer — minutes or never). Schema is intentionally narrow:
#
#   {"sentiment": "up" | "down", "comment": str | None, "ts": "2026-05-10T..."}
#
# Last-write-wins: a user can change their mind by clicking the other thumb.
# Aggregation across runs is left to a later eval script (the Tier 0 SQLite
# indexer can pick up feedback.json by glob); the per-run JSON is the source
# of truth.
# ---------------------------------------------------------------------------


def write_feedback(
    run_dir: Path,
    sentiment: str,
    comment: str | None = None,
) -> None:
    """Persist a thumbs-up/down rating (with optional comment) for one run.

    Always overwrites — last click wins. Caller is responsible for validating
    `sentiment` before calling, but we double-check here so a typo from a
    future call site can't silently produce garbage on disk.
    """
    if sentiment not in ("up", "down"):
        raise ValueError(f"sentiment must be 'up' or 'down', got {sentiment!r}")
    payload = {
        "sentiment": sentiment,
        "comment": comment if (comment and comment.strip()) else None,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    (run_dir / "feedback.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_feedback(run_dir: Path) -> dict | None:
    """Return the persisted feedback dict, or None if no rating exists yet.

    Returns None on parse errors too — feedback is non-critical telemetry,
    a corrupt file should not break the UI render path.
    """
    path = run_dir / "feedback.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
