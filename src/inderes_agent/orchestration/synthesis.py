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
import re
import time
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
    duration_seconds: float = 0.0

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
            "duration_seconds": round(self.duration_seconds, 3),
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


def _format_tool_call_trace(result: WorkflowResult) -> str:
    """Render every subagent's tool calls as ground-truth context for synthesis.

    BACKLOG #10 provenance threading: lead synthesis needs to see what tools
    actually returned, not just the subagent's text summary, so it can:
      - drop hallucinated entities (in agent text but not in tool output)
      - surface omitted-but-relevant entities (in tool output but not in agent text)
      - cross-check numbers and attributions against raw data
    """
    lines: list[str] = []
    for i, sr in enumerate(result.subagent_results, 1):
        if not sr.tool_calls:
            continue
        label = sr.domain.value
        if sr.company:
            label += f" — {sr.company}"
        lines.append(f"### Subagent {i} ({label}) — {len(sr.tool_calls)} tool call(s):")
        for tc in sr.tool_calls:
            args_repr = json.dumps(tc.arguments, ensure_ascii=False) if tc.arguments is not None else "{}"
            if len(args_repr) > 300:
                args_repr = args_repr[:300] + "…"
            lines.append(f"- `{tc.name}` args={args_repr}")
            lines.append(f"    → {tc.result_summary(max_items=30)}")
        lines.append("")
    if not lines:
        return "_no tool calls captured for any subagent_"
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

    t_start = time.time()
    try:
        async with build_conflict_detector_agent() as detector:
            result = await detector.run(prompt)
            raw = result.text if hasattr(result, "text") else str(result)
            model_used = getattr(detector.client, "last_used_model", "unknown")
    except Exception as exc:
        log.warning("conflict-detector call failed: %s", exc)
        return ConflictReport(error=str(exc)[:500], duration_seconds=time.time() - t_start)

    duration = time.time() - t_start

    cleaned = _strip_json_fences(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("conflict-detector returned non-JSON output: %s", exc)
        return ConflictReport(
            raw=raw, model_used=model_used,
            error=f"JSON parse failed: {exc}",
            duration_seconds=duration,
        )

    return ConflictReport(raw=raw, parsed=parsed, model_used=model_used, duration_seconds=duration)


def _format_conflict_block(report: ConflictReport) -> str:
    """Render the conflict report as a prompt section for the lead."""
    if not report.has_signal:
        if report.skipped_reason:
            return f"_conflict-detector skipped: {report.skipped_reason}_"
        if report.error:
            return f"_conflict-detector errored: {report.error}_"
        return "_conflict-detector found no notable agreements, conflicts, or isolated claims._"
    return json.dumps(report.parsed, ensure_ascii=False, indent=2)


@dataclass
class SynthesisTrace:
    """Per-stage timings + conflict report + parsed Päättely from one synthesize() call.

    `paattely` is the parsed JSON the LEAD emits as its visible-reasoning
    block (BACKLOG #9). Schema: `{disagree, resolution, uncertain, skipped}`,
    each value a string or null. None when LEAD did not emit a parseable
    block. The UI renders this as a 2×2 slot grid.

    `paattely_raw` is the raw text matched (block-with-fences) for forensics
    even when JSON parse fails.
    """
    conflict_report: ConflictReport
    lead_seconds: float = 0.0
    paattely: dict[str, Any] | None = None
    paattely_raw: str | None = None
    paattely_error: str | None = None


# Compiled once: matches `**🧠 Päättely**` (or `**🧠 Reasoning**`) followed by
# a fenced JSON block. Works whether the model put one or many blank lines
# between the marker and the fence, and whether the fence is ```json or ```.
_PAATTELY_RE = re.compile(
    r"\*\*\s*🧠\s*(?:Päättely|Reasoning)\s*\*\*\s*\n+\s*```(?:json)?\s*\n(?P<body>\{.*?\})\s*\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_paattely(text: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Pull the **🧠 Päättely** JSON block out of the LEAD's response.

    Returns (cleaned_text, raw_block_or_None, parsed_or_None, error_or_None).
    `cleaned_text` has the matched block (and one trailing blank line) stripped
    so the UI doesn't render the JSON in the answer body — it renders as a
    2×2 slot grid instead.

    On JSON parse failure, returns (cleaned_text, raw, None, error_msg).
    On no match, returns (text, None, None, None).
    """
    m = _PAATTELY_RE.search(text)
    if not m:
        return text, None, None, None

    raw_full = m.group(0)
    body = m.group("body")
    cleaned = (text[: m.start()] + text[m.end() :]).rstrip() + "\n"

    try:
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            return cleaned, raw_full, None, "päättely body is not a JSON object"
        # Normalize: ensure expected keys exist (None if missing).
        normalized = {k: parsed.get(k) for k in ("disagree", "resolution", "uncertain", "skipped")}
        return cleaned, raw_full, normalized, None
    except json.JSONDecodeError as exc:
        return cleaned, raw_full, None, f"JSON parse failed: {exc}"


async def synthesize(
    query: str, workflow_result: WorkflowResult
) -> tuple[str, str, SynthesisTrace]:
    """Run the lead agent over the subagents' outputs.

    Returns (final_answer_text, lead_model_used, synthesis_trace) where
    `synthesis_trace.conflict_report` is the conflict-detector output and
    `synthesis_trace.lead_seconds` is the wall clock for the LEAD synthesis call.
    """
    from ..agents._common import today_prompt_prefix

    conflict_report = await detect_conflicts(workflow_result)

    subagents_block = _format_subagent_results(workflow_result)
    tool_trace_block = _format_tool_call_trace(workflow_result)
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

SUBAGENT OUTPUTS (the agent's own narrative summary):
{subagents_block}

TOOL CALL TRACE (ground truth — what the MCP tools actually returned):
{tool_trace_block}

How to use the tool call trace:
- This is the **structured ground truth**. The subagent text above is its summary; this section shows what the tools actually returned.
- **Hallucination check**: if a subagent named a specific entity (company, person, date) that does NOT appear in the tool result's `item_names`, **drop that entity from your answer**. Do not surface unsupported claims.
- **Completeness check**: if the tool returned N items and the subagent only mentioned M < N when the user asked for a list, either include the missing items or explicitly state which subset and why. Do not silently truncate.
- **Numerical & attribution check**: if a subagent quoted a specific number, name, or date, the tool result is the source of truth — prefer it when there's a conflict.
- If `item_names` is empty for a tool call, the result was non-structured (e.g. document body, transcript) and the subagent's summary is the best you have.

CONFLICT REPORT (pre-synthesis structural analysis of subagent outputs):
{conflict_block}

How to use the conflict report:
- Treat `agreements` as load-bearing: claims confirmed by multiple subagents are safer to surface.
- For each item in `conflicts`: do NOT silently pick one side. Either resolve it (state which subagent's claim is more likely correct AND why), or flag the disagreement explicitly to the user.
- For `isolated_claims`: be skeptical. A specific factual claim (a company name in a list, a number, an attributed quote) that only one subagent made and that no other corroborated is the most common hallucination shape. Either drop it, or surface it with an explicit "single-source" caveat.

Now synthesize a final answer for the user, following your instructions.
"""

    t_lead = time.time()
    async with build_lead_agent() as lead:
        result = await lead.run(prompt)
        text = result.text if hasattr(result, "text") else str(result)
        model_used = getattr(lead.client, "last_used_model", "unknown")
    lead_seconds = time.time() - t_lead

    # Pull out the JSON Päättely block — UI renders it as a 2×2 slot grid,
    # not inline text. The raw text returned to the caller has the block
    # stripped so render_lead_answer doesn't dump JSON into the answer body.
    cleaned_text, paattely_raw, paattely, paattely_err = _extract_paattely(text)
    if paattely_err:
        log.warning("päättely JSON extraction failed: %s", paattely_err)

    trace = SynthesisTrace(
        conflict_report=conflict_report,
        lead_seconds=lead_seconds,
        paattely=paattely,
        paattely_raw=paattely_raw,
        paattely_error=paattely_err,
    )
    return cleaned_text, model_used, trace
