"""Workflow execution: fan out to subagents, collect results, hand to synthesis.

We use direct Agent.run() calls bounded by a semaphore (MAX_CONCURRENT_AGENTS)
rather than ConcurrentBuilder. Reasons:
  - Free-tier Gemini quotas burn fast; we need fine-grained per-agent caps.
  - Per-company fan-out for comparisons needs sequential queueing if N > limit.
  - The MAF orchestration builders are great for fixed pipelines but we want to
    decide subagent set per query at runtime.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..agents import (
    build_portfolio_agent,
    build_quant_agent,
    build_research_agent,
    build_sentiment_agent,
    build_valuation_agent,
)
from ..observability.output_parts import ToolCallTrace, extract_parts
from ..settings import get_settings
from .router import Domain, QueryClassification


@dataclass
class SubagentResult:
    domain: Domain
    company: str | None
    text: str
    model_used: str
    error: str | None = None
    image_paths: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    duration_seconds: float = 0.0  # per-subagent wall clock from start to finish


@dataclass
class WorkflowResult:
    classification: QueryClassification
    subagent_results: list[SubagentResult] = field(default_factory=list)
    fallback_events: int = 0
    fanout_seconds: float = 0.0  # wall clock for the whole asyncio.gather (limited by slowest)
    # Optional plan from the lead-planner step (when the user enables
    # the "Käytä pidempää suunnittelua" sidebar toggle). When present,
    # it's embedded in each subagent's prompt for sharper focus, and
    # rendered in the UI as a "🧠 Suunnitelma" expander.
    plan: PlanResult | None = None


@dataclass
class PlanResult:
    """Output of the lead-planner step. None of these fields is required
    to be populated — the planner can return an empty plan when the
    query is too simple to benefit from one."""
    raw_text: str = ""           # the agent's full response (JSON + narrative)
    parsed: dict | None = None   # parsed JSON object: thinking, per_subagent, axis, watchouts
    narrative: str = ""          # the human-readable narrative after the JSON
    duration_seconds: float = 0.0
    model_used: str = ""


_AGENT_BUILDERS = {
    Domain.QUANT: build_quant_agent,
    Domain.RESEARCH: build_research_agent,
    Domain.SENTIMENT: build_sentiment_agent,
    Domain.PORTFOLIO: build_portfolio_agent,
    Domain.VALUATION: build_valuation_agent,
}


async def _run_one(
    domain: Domain,
    query: str,
    company: str | None,
    sem: asyncio.Semaphore,
    run_dir: Path,
    plan: PlanResult | None = None,
) -> SubagentResult:
    builder = _AGENT_BUILDERS[domain]
    async with sem:
        t_start = time.time()
        try:
            async with builder() as agent:
                # If a specific company was specified for this fan-out branch,
                # rephrase the prompt for the subagent so it focuses there.
                from ..agents._common import today_prompt_prefix
                base = query if company is None else f"For {company}: {query}"
                # When plan-then-execute is enabled, append the planner's
                # per-domain guidance as additional context. Empty string
                # when no plan or no guidance for this domain — making
                # this composition safe in all cases.
                plan_snippet = _format_plan_for_subagent(plan, domain) if plan else ""
                prompt = today_prompt_prefix() + base + plan_snippet
                result = await agent.run(prompt)
                model_used = getattr(agent.client, "last_used_model", "unknown")
                # Walk response parts so code blocks, code outputs and images
                # land structured rather than flattened into one text blob.
                label = f"{domain.value}-{company}" if company else domain.value
                text, image_paths, tool_calls = extract_parts(
                    result, run_dir=run_dir, agent_label=label
                )
                return SubagentResult(
                    domain=domain,
                    company=company,
                    text=text,
                    model_used=model_used,
                    image_paths=image_paths,
                    tool_calls=tool_calls,
                    duration_seconds=time.time() - t_start,
                )
        except Exception as exc:
            return SubagentResult(
                domain=domain,
                company=company,
                text="",
                model_used="error",
                error=str(exc)[:500],
                duration_seconds=time.time() - t_start,
            )


async def run_planner(
    query: str,
    classification: QueryClassification,
    *,
    deep: bool = False,
) -> PlanResult:
    """Run the lead-planner agent BEFORE subagent dispatch.

    Reads the user's query + the routing decision and emits a strategic
    plan: per-subagent guidance, comparison axis, watchouts. Output is
    embedded in each subagent's prompt for sharper focus, and surfaced
    in the UI as a "🧠 Suunnitelma" expander.

    The planner has no tools — it's a pure LLM reasoning step. ``deep=True``
    runs it on Gemini Pro for higher-quality plans (matches the LEAD-tier
    radio in the UI).

    Returns a ``PlanResult`` with raw text + parsed JSON (when extractable)
    + the human narrative. Caller is responsible for surfacing this to
    UI + embedding into subagent prompts.
    """
    import json
    import re
    from ..agents import build_lead_planner_agent
    from ..agents._common import today_prompt_prefix

    prompt = today_prompt_prefix() + f"""\
USER QUESTION:
{query}

ROUTING DECISION (from the router):
- domains: {[d.value for d in classification.domains]}
- companies: {classification.companies}
- is_comparison: {classification.is_comparison}
- reasoning: {classification.reasoning}

Now write the plan. Emit STRICT JSON in a ```json fenced block, then a
short human narrative (3–5 sentences) summarising it. Match the user's
language (Suomi/EN) in both the per-subagent guidance strings AND the
narrative.
"""
    t0 = time.time()
    async with build_lead_planner_agent(deep=deep) as planner:
        result = await planner.run(prompt)
        text = result.text if hasattr(result, "text") else str(result)
        model_used = getattr(planner.client, "last_used_model", "unknown")
    duration = time.time() - t0

    # Best-effort JSON extraction (non-fatal — UI shows raw if parse fails)
    parsed: dict | None = None
    narrative = text
    m = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n?```", text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            parsed = json.loads(m.group(1))
            # Narrative = everything AFTER the JSON block
            narrative = text[m.end():].strip()
        except json.JSONDecodeError:
            parsed = None

    return PlanResult(
        raw_text=text,
        parsed=parsed,
        narrative=narrative,
        duration_seconds=duration,
        model_used=model_used,
    )


def _format_plan_for_subagent(plan: PlanResult, domain: Domain) -> str:
    """Render the plan's per-subagent guidance as a prompt-ready snippet
    that workflows.py can prepend to each subagent's user-prompt.

    Returns an empty string when no plan exists, no parsed JSON, or no
    guidance for this domain — making the function safe to always call.
    """
    if plan is None or plan.parsed is None:
        return ""
    per_subagent = plan.parsed.get("per_subagent") or {}
    domain_guidance = per_subagent.get(domain.value)
    if not domain_guidance:
        return ""
    bits: list[str] = [
        f"\n🧠 LEAD'S PLAN FOR YOUR STEP ({domain.value.upper()}):",
        f"  {domain_guidance}",
    ]
    watchouts = plan.parsed.get("watchouts") or []
    if watchouts:
        bits.append("  Watchouts:")
        for w in watchouts:
            bits.append(f"    - {w}")
    axis = plan.parsed.get("axis")
    if axis:
        bits.append(f"  Comparison axis (focus contrast on this): {axis}")
    return "\n".join(bits) + "\n"


async def run_workflow(
    query: str,
    classification: QueryClassification,
    run_dir: Path,
    *,
    plan: PlanResult | None = None,
) -> WorkflowResult:
    """Spawn subagents per the classification, respecting MAX_CONCURRENT_AGENTS.

    `run_dir` is needed because each subagent may extract images from its
    response into `<run_dir>/images/`.

    `plan` (optional, from `run_planner()`) — when provided, the planner's
    per-subagent guidance is embedded into each subagent's user prompt so
    the dispatch is purposeful instead of generic. None preserves the
    default behaviour bit-for-bit.
    """
    settings = get_settings()
    sem = asyncio.Semaphore(settings.MAX_CONCURRENT_AGENTS)

    tasks: list[asyncio.Task[SubagentResult]] = []

    # Per-company fan-out only for domains where it actually helps (quant, research, sentiment).
    # Portfolio and market-wide queries don't fan out.
    fanout = (
        classification.is_comparison
        and len(classification.companies) > 1
    )

    for domain in classification.domains:
        if fanout and domain != Domain.PORTFOLIO:
            for company in classification.companies:
                tasks.append(asyncio.create_task(_run_one(domain, query, company, sem, run_dir, plan)))
        else:
            tasks.append(asyncio.create_task(_run_one(domain, query, None, sem, run_dir, plan)))

    t_fanout_start = time.time()
    results = await asyncio.gather(*tasks)
    fanout_seconds = time.time() - t_fanout_start

    fallback_events = sum(
        1 for r in results if r.model_used == settings.FALLBACK_MODEL
    )

    return WorkflowResult(
        classification=classification,
        subagent_results=list(results),
        fanout_seconds=fanout_seconds,
        fallback_events=fallback_events,
        plan=plan,
    )
