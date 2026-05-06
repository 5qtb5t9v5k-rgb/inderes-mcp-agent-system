"""Lead synthesis: feed subagent outputs to aino-lead, get a final answer.

A pre-synthesis pass (`detect_conflicts`) runs a separate LLM call that
reads all subagent outputs and emits structured JSON describing
agreements, conflicts, and isolated single-source claims. The lead then
sees that structured map as additional context — making the emergent
self-correction observed in Case 003 (evals/known-cases.md) explicit
and loggable rather than implicit in the lead's training-data priors.

This is the BACKLOG #1 plan-then-execute extension.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..agents import build_conflict_detector_agent, build_lead_agent
from .workflows import WorkflowResult

log = logging.getLogger(__name__)


@dataclass
class ConflictReport:
    """Structured map produced by the conflict-detector pass.

    `raw` is the model's literal JSON string (preserved for the run log,
    even when it failed to parse). `parsed` is the dict if parsing
    succeeded, else None.
    """
    raw: str = ""
    parsed: dict[str, Any] | None = None
    model_used: str = "skipped"
    skipped_reason: str | None = None
    error: str | None = None

    @property
    def has_signal(self) -> bool:
        if not self.parsed:
            return False
        return any(
            self.parsed.get(k)
            for k in ("agreements", "conflicts", "isolated_claims")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_used": self.model_used,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
            "raw": self.raw,
            "parsed": self.parsed,
        }


def _format_subagent_results(result: WorkflowResult) -> str:
    """Render subagent outputs as a structured prompt for the lead."""
    lines: list[str] = []
    for i, sr in enumerate(result.subagent_results, 1):
        label = sr.domain.value
        if sr.company:
            label += f" — {sr.company}"
        header = f"### {i}. {label}  [model: {sr.model_used}]"
        lines.append(header)
        if sr.error:
            lines.append(f"_subagent error: {sr.error}_")
        else:
            lines.append(sr.text or "_(empty response)_")
        lines.append("")
    return "\n".join(lines)


def _strip_json_fences(text: str) -> str:
    """Defensively strip ```json fences in case the model added them despite the prompt."""
    s = text.strip()
    if s.startswith("```"):
        # drop opening fence (```json or just ```) and trailing ```
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


async def detect_conflicts(workflow_result: WorkflowResult) -> ConflictReport:
    """Pre-synthesis pass. Skips automatically when there's nothing to compare."""
    non_error = [sr for sr in workflow_result.subagent_results if not sr.error]
    if len(non_error) < 2:
        return ConflictReport(
            skipped_reason=f"only {len(non_error)} non-error subagent(s); nothing to compare",
        )

    subagents_block = _format_subagent_results(workflow_result)
    prompt = f"""\
SUBAGENT OUTPUTS:
{subagents_block}

Now produce the conflict report as STRICT JSON per your instructions.
"""

    try:
        async with build_conflict_detector_agent() as detector:
            result = await detector.run(prompt)
            raw = result.text if hasattr(result, "text") else str(result)
            model_used = getattr(detector.client, "last_used_model", "unknown")
    except Exception as exc:
        log.warning("conflict-detector call failed: %s", exc)
        return ConflictReport(error=str(exc)[:500])

    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("conflict-detector returned non-JSON output: %s", exc)
        return ConflictReport(raw=raw, model_used=model_used, error=f"JSON parse failed: {exc}")

    return ConflictReport(raw=raw, parsed=parsed, model_used=model_used)


def _format_conflict_block(report: ConflictReport) -> str:
    """Render the conflict report as a prompt section for the lead."""
    if not report.has_signal:
        if report.skipped_reason:
            return f"_conflict-detector skipped: {report.skipped_reason}_"
        if report.error:
            return f"_conflict-detector errored: {report.error}_"
        return "_conflict-detector found no notable agreements, conflicts, or isolated claims._"
    return json.dumps(report.parsed, ensure_ascii=False, indent=2)


async def synthesize(
    query: str, workflow_result: WorkflowResult
) -> tuple[str, str, ConflictReport]:
    """Run the lead agent over the subagents' outputs.

    Returns (final_answer_text, lead_model_used, conflict_report).
    """
    from ..agents._common import today_prompt_prefix

    conflict_report = await detect_conflicts(workflow_result)

    subagents_block = _format_subagent_results(workflow_result)
    conflict_block = _format_conflict_block(conflict_report)
    cls = workflow_result.classification

    prompt = today_prompt_prefix() + f"""\
USER QUESTION:
{query}

ROUTING DECISION:
domains   = {[d.value for d in cls.domains]}
companies = {cls.companies}
comparison = {cls.is_comparison}
reasoning = {cls.reasoning}

SUBAGENT OUTPUTS:
{subagents_block}

CONFLICT REPORT (pre-synthesis structural analysis of subagent outputs):
{conflict_block}

How to use the conflict report:
- Treat `agreements` as load-bearing: claims confirmed by multiple subagents are safer to surface.
- For each item in `conflicts`: do NOT silently pick one side. Either resolve it (state which subagent's claim is more likely correct AND why), or flag the disagreement explicitly to the user.
- For `isolated_claims`: be skeptical. A specific factual claim (a company name in a list, a number, an attributed quote) that only one subagent made and that no other corroborated is the most common hallucination shape. Either drop it, or surface it with an explicit "single-source" caveat.

Now synthesize a final answer for the user, following your instructions.
"""

    async with build_lead_agent() as lead:
        result = await lead.run(prompt)
        text = result.text if hasattr(result, "text") else str(result)
        model_used = getattr(lead.client, "last_used_model", "unknown")
        return text, model_used, conflict_report
