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
from dataclasses import dataclass, field
from typing import Any

from ..agents import build_conflict_detector_agent, build_lead_agent
from ..valuation import (
    Valuation,
    ValuationAgentOutput,
    ValuationAgentSkipped,
    ValuationParseError,
    parse as parse_valuation_agent,
    value_stock,
)
from .router import Domain
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
class ValuationRecord:
    """One company's alternative-valuation result.

    Holds the agent's parsed output + the engine's deterministic computation,
    so run_log.write_run can persist both the agent's parameter rationale
    and the resulting fair value to ``valuation.json``.
    """
    company: str
    agent_output: ValuationAgentOutput | None = None
    valuation: Valuation | None = None
    skipped: ValuationAgentSkipped | None = None
    parse_error: str | None = None
    raw_text: str | None = None  # for forensic logging when parse fails


@dataclass
class SynthesisTrace:
    """Per-stage timings + conflict report + parsed Päättely from one synthesize() call.

    `paattely` is the parsed JSON the LEAD emits as its visible-reasoning
    block (BACKLOG #9). Schema: `{disagree, resolution, uncertain, skipped}`,
    each value a string or null. None when LEAD did not emit a parseable
    block. The UI renders this as a 2×2 slot grid.

    `paattely_raw` is the raw text matched (block-with-fences) for forensics
    even when JSON parse fails.

    `valuations` is the list of per-company alternative-valuation records,
    populated only when the user enabled the "Käytä vaihtoehtoista
    arvonmääritystä" toggle and the workflow dispatched VALUATION agents.
    Empty list otherwise.
    """
    conflict_report: ConflictReport
    lead_seconds: float = 0.0
    paattely: dict[str, Any] | None = None
    paattely_raw: str | None = None
    paattely_error: str | None = None
    valuations: list[ValuationRecord] = field(default_factory=list)


# Compiled once. The Päättely block can be EITHER:
#   (a) a fenced JSON object (legacy / structured) — `**🧠 Päättely**\n```json {...}````
#   (b) free prose (current default) — `**🧠 Päättely**\n\n<paragraphs>...\n## next-section`
# We try (a) first because it gives the UI more structure; fall back to (b)
# capturing everything until the next markdown heading or another bold marker
# (📖 Lähteet / 💡 Voisit kysyä myös) or end of text.
# Marker can be **🧠 Päättely**, ## 🧠 Päättely, ### 🧠 Päättely, or just
# 🧠 Päättely on its own line — Flash Lite picks any of these. We anchor
# on a line-start to avoid matching inside other markdown bullets/text.
_PAATTELY_JSON_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3})?\s*🧠\s*(?:Päättely|Reasoning)\s*(?:\*\*|:)?\s*\n+"
    r"\s*```(?:json)?\s*\n(?P<body>\{.*?\})\s*\n```",
    re.DOTALL | re.IGNORECASE,
)
_PAATTELY_PROSE_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3})?\s*🧠\s*(?:Päättely|Reasoning)\s*(?:\*\*|:)?\s*\n+"
    r"(?P<body>.+?)"
    r"(?=\n\s*#{1,3}\s|\n\s*\*\*\s*(?:📖|💡)|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _extract_paattely(text: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Pull the **🧠 Päättely** block out of the LEAD's response.

    Returns (cleaned_text, raw_block_or_None, parsed_or_None, error_or_None).
    `parsed` may be:
      - a dict {disagree, resolution, uncertain, skipped} when LEAD emitted
        the structured JSON form (UI renders 2×2 grid); OR
      - a dict {prose: str} when LEAD emitted free prose covering the four
        points (UI renders prose in a styled expander).

    `cleaned_text` has the matched block stripped so the UI doesn't render
    the body twice (once in the answer body, once as the Päättely callout).

    On no match, returns (text, None, None, None).
    """
    # First try the structured JSON form (legacy / preferred when present).
    m = _PAATTELY_JSON_RE.search(text)
    if m:
        raw_full = m.group(0)
        body = m.group("body")
        cleaned = (text[: m.start()] + text[m.end() :]).rstrip() + "\n"
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                # JSON valid but not an object — fall through to prose.
                pass
            else:
                normalized = {k: parsed.get(k) for k in ("disagree", "resolution", "uncertain", "skipped")}
                return cleaned, raw_full, normalized, None
        except json.JSONDecodeError:
            # Treat as prose — fall through.
            pass

    # Prose form — capture body until next section.
    m2 = _PAATTELY_PROSE_RE.search(text)
    if not m2:
        return text, None, None, None

    raw_full = m2.group(0)
    body = m2.group("body").strip()
    if not body:
        cleaned_empty = (text[: m2.start()] + text[m2.end() :]).rstrip() + "\n"
        return cleaned_empty, raw_full, None, "päättely block was empty"

    # Defensive cap: take at most the first 4 double-newline-separated
    # paragraphs from the captured body. The prompt asks for exactly 4
    # paragraphs (one per slot: erimielisyys / ratkaisu / epävarma /
    # jätin tekemättä). When LEAD forgets to start the answer body with
    # `## Yhteenveto` heading, the prose regex would otherwise suck the
    # whole answer into päättely. Strict cap at 4 keeps päättely focused
    # and pushes the rest back to the answer body.
    paragraphs = re.split(r"\n\s*\n", body)
    capped_body = "\n\n".join(p.strip() for p in paragraphs[:4] if p.strip())

    # Compute what we actually consumed from the original text — only the
    # capped portion, not the entire greedy match. The rest of the greedy
    # match goes back to the answer body so render_lead_answer renders it.
    if capped_body == body:
        consumed_end = m2.end()
    else:
        # Find where the capped body ends in the original text.
        body_start_in_text = m2.start() + (m2.group(0).find(body))
        consumed_end = body_start_in_text + len(capped_body)

    cleaned = (text[: m2.start()] + text[consumed_end:]).rstrip() + "\n"
    return cleaned, raw_full, {"prose": capped_body}, None


def _process_valuation_subagents(
    workflow_result: WorkflowResult,
) -> list[ValuationRecord]:
    """Parse each VALUATION subagent's JSON output and run the engine.

    For per-company comparisons we get one VALUATION subagent per company;
    for single-company queries we get one. Each result either:
      - parses cleanly + engine returns a Valuation → ValuationRecord with both
      - parses to ValuationAgentSkipped → record carries the skip reason
      - fails to parse → record carries the error + raw text for forensics

    Logged warnings rather than raised exceptions: a malformed VALUATION
    output should not break the rest of the synthesis pipeline.
    """
    records: list[ValuationRecord] = []
    for sr in workflow_result.subagent_results:
        if sr.domain != Domain.VALUATION:
            continue
        # Default company label: subagent's per-company tag for fanout, or
        # "<unknown>" until the parser succeeds and we can use parsed.company.
        # We deliberately do NOT fall back to sr.text[:80] — that pulls the
        # **Ajatus:** line into the run-log's company field.
        company = sr.company or "<unknown>"
        if sr.error:
            records.append(ValuationRecord(
                company=company,
                parse_error=f"agent error before output: {sr.error}",
                raw_text=sr.text,
            ))
            continue

        try:
            parsed = parse_valuation_agent(sr.text)
        except ValuationParseError as exc:
            log.warning("valuation-parser failed for %s: %s", company, exc)
            records.append(ValuationRecord(
                company=company,
                parse_error=str(exc),
                raw_text=exc.raw_text,
            ))
            continue

        if isinstance(parsed, ValuationAgentSkipped):
            records.append(ValuationRecord(
                company=parsed.company,  # use parser's company name once we have it
                skipped=parsed,
                raw_text=sr.text,
            ))
            continue

        # Happy path: agent emitted clean JSON → run the deterministic engine.
        # Use parsed.company once available — it's the canonical name from
        # the structured output, free of "**Ajatus:**" leakage.
        company = parsed.company
        try:
            valuation = value_stock(**parsed.to_engine_kwargs())
        except ValueError as exc:
            log.warning("valuation-engine rejected %s: %s", company, exc)
            records.append(ValuationRecord(
                company=company,
                agent_output=parsed,
                parse_error=f"engine validation failed: {exc}",
                raw_text=sr.text,
            ))
            continue

        records.append(ValuationRecord(
            company=company,
            agent_output=parsed,
            valuation=valuation,
            raw_text=sr.text,
        ))

    return records


def _format_valuation_block(records: list[ValuationRecord]) -> str:
    """Render valuation records as a prompt block for the LEAD agent.

    Returns a human-readable structured text — not JSON, because LEAD's
    job is to weave this into prose. For each company shows: chosen
    parameters with rationale, computed fair value with quality label,
    and the comparison-relevant numbers (yli/ali %, entry levels).
    """
    if not records:
        return "_user did not enable alternative valuation; default flow only_"

    lines: list[str] = []
    for rec in records:
        lines.append(f"### {rec.company}")
        if rec.parse_error and not rec.valuation:
            lines.append(f"_valuation skipped: {rec.parse_error}_")
            lines.append("")
            continue
        if rec.skipped:
            lines.append(f"_agent flagged invalid: {'; '.join(rec.skipped.warnings)}_")
            lines.append("")
            continue

        a = rec.agent_output
        v = rec.valuation
        assert a is not None and v is not None  # narrowed by branches above

        lines.append(f"Parametrit: BVPS {a.bvps:.2f} ({a.bvps_date or '?'}), "
                     f"price {a.price:.2f} ({a.price_date or '?'}), "
                     f"ROE {a.roe_used:.1%} ({a.roe_version}), "
                     f"k {a.k:.1%}, g {a.g:.1%}")
        # Multi-line rationales (the agent now produces 2-4 sentence
        # explanations per parameter — surface them in full so LEAD
        # can paraphrase or quote them).
        lines.append(f"  ROE-perustelu: {a.roe_rationale}")
        lines.append(f"  k-perustelu: {a.k_rationale}")
        lines.append(f"  g-perustelu: {a.g_rationale}")
        if a.warnings:
            for w in a.warnings:
                lines.append(f"  ⚠ {w}")

        # Engine output — include the new EPV/growth-decomposition fields
        # so LEAD can write the "tulosvoiman arvo + kasvun hinnoittelu"
        # section of the report.
        lines.append(f"Engine: quality={v.quality}, fair_value={v.fair_value:.2f} €, "
                     f"FV_Gordon={v.fv_gordon:.2f}, EPV_pure={v.epv_pure:.2f}, "
                     f"GM={v.gm:.2f}x, Rock Bottom={v.rock_bottom:.2f}")

        # EPV / growth-pricing decomposition — the Greenwald split that
        # answers "how much of the current price is the market paying for
        # growth?". Format chosen to be unambiguous in the LEAD prompt.
        implied_g_str = (
            f"{v.implied_g:+.2%}" if v.implied_g is not None
            else "ei laskettavissa (P/B ≈ 1 tai laskenta hajoaa)"
        )
        lines.append(
            f"  EPV-dekompositio: kurssi on {v.market_premium_to_epv_pct:+.1f}% "
            f"yli/alle EPV:n; kasvun osuus nykyhinnasta "
            f"{v.growth_priced_in_share*100:+.1f}%; "
            f"markkinan implisiittinen g = {implied_g_str} "
            f"(oma g = {a.g:.1%})"
        )
        lines.append(
            f"  Turvamarginaali oman fair valuen suhteen: "
            f"{v.safety_margin_to_fv_pct:+.1f}% "
            f"(positiivinen = aliarvostettu)"
        )
        lines.append(f"  Entry-tasot: aloitus {v.entry_aloitus:.2f}€, "
                     f"nosto {v.entry_nosto:.2f}€, täysi {v.entry_taysi:.2f}€")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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

    # Process VALUATION subagents (if any) — parse their JSON, run the
    # deterministic engine, and stash records for run_log + LEAD prompt.
    valuation_records = _process_valuation_subagents(workflow_result)

    subagents_block = _format_subagent_results(workflow_result)
    tool_trace_block = _format_tool_call_trace(workflow_result)
    conflict_block = _format_conflict_block(conflict_report)
    valuation_block = _format_valuation_block(valuation_records)
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

ALTERNATIVE VALUATION (user's own methodology, opt-in — present only when user enabled the toggle):
{valuation_block}

How to use the alternative valuation:
- This is the **user's own valuation methodology** (Greenwald-Gordon hybrid: FV = ((ROE-g)/(k-g)) × BVPS, with quality classification by ROE-vs-k). The numbers are deterministically computed by a Python engine; do NOT recalculate them.
- If the block is the placeholder "_user did not enable alternative valuation; default flow only_", **skip the comparison section entirely** — do not invent it.
- If real valuation records are present, add a section titled `## Oma malli vs Inderes` (FI) or `## Own model vs Inderes` (EN) to the answer body. In it, **per company**:
  1. State own fair value with one number (the engine's `fair_value`).
  2. State Inderes' target price (from QUANT subagent's INDERES VIEW).
  3. State the percentage delta and explain the source of the difference (different k? different g? different ROE-version chosen?).
  4. State the quality classification (laatu / keskinkertainen / tuhoutuva) and what it implies.
  5. Flag any agent warnings about data quality.
- Do NOT invent numbers not in this block. The engine has full precision; round to 2 decimals when displaying.
- The comparison section sits **after** the standard answer body but **before** `**📖 Lähteet:**`.

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
        valuations=valuation_records,
    )
    return cleaned_text, model_used, trace
