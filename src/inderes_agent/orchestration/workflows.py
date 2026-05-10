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
from .limits import (
    BudgetExceededError,
    CancelToken,
    RunBudget,
    with_subagent_timeout,
)
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


# ─────────────────────────────────────────────────────────────────────────────
# Fabrication detector
#
# Background: case_004 (evals/golden.yaml) caught a "trust killer" run
# (20260502-205706-108, "mitäs vincitin osakkeesta..."). Vincit isn't in
# the Inderes catalog — search-companies would have errored — but
# instead of failing, all three subagents returned 0 tool calls AND
# fabricated a complete narrative with target prices, margins, and even
# a fake "Sources: get-fundamentals, ..." line. LEAD synthesised the
# fabrications into one polished answer; the user has no way to know
# the entire thing is invented.
#
# A subagent with MCP tools attached should NEVER produce a long
# domain-loaded text without making at least one MCP call. If it does,
# the text is by definition not grounded in retrieved data — it's the
# model's training-time guess.
#
# This detector is the analogue of the valuation tool-call guard in
# synthesis.py:354 (commit 045872e), generalised to all subagent
# domains. Triggers REPLACE the text with empty + set the error field,
# so LEAD's synthesis prompt sees the failure honestly and (with
# `_all_subagents_fabricated_or_errored()` in synthesis.py) routes to
# the no-data answer instead of synthesising on top of nothing.
# ─────────────────────────────────────────────────────────────────────────────


# Length under which an empty-tool-calls response is excused as a
# legitimate "I have nothing to say" reply. A real "I couldn't find
# anything" answer is < ~300 chars; the Vincit fabrication was 1500+.
_FABRICATION_MIN_TEXT_CHARS = 300

# Phrases that strongly imply the agent claimed grounded output —
# either a recommendation, a euro/percent figure, a target price, or a
# fake "Sources:" line. If any appear in a 0-tool-call response, the
# response is fabricated.
#
# Curation note: short English words like "buy"/"sell"/"hold" and short
# Finnish stems like "lisää"/"osta"/"myy" caused false positives via
# substring matches against legitimate prose ("yleisellä" contains
# "sell", "kallista" contains nothing-but-could). The list below
# focuses on UNAMBIGUOUS markers — multi-character stems that don't
# coincide with everyday Finnish vocabulary plus literal symbols and
# section headers that appear only in synthesised analysis. Real
# fabrications hit 5+ of these simultaneously, so dropping the
# ambiguous ones doesn't reduce sensitivity meaningfully.
_FABRICATION_GROUNDED_MARKERS: tuple[str, ...] = (
    "tavoitehint",      # tavoitehinta / tavoitehinnan / tavoitehintaa
    "target price",
    "vähennä",          # one of two Finnish recommendation verbs that's
                        # not a common everyday word — kept; "lisää",
                        # "osta", "myy" are too common, dropped
    "p/e",
    "ev/ebit",
    "ebit-",            # ebit-marginaali, EBITA-, EBITDA-
    "p/b",
    "€",
    "sources:",
    "lähteet:",
    "inderes view",
    "inderesin näkemys",
    "inderes näkemys",
    "epv",              # Greenwald-Gordon engine output (not user vocab)
    "turvamarginaal",
)


def _detect_fabrication(result: SubagentResult) -> str | None:
    """Return an error reason if the result looks fabricated, else None.

    Heuristic: long domain-loaded text WITH zero MCP tool calls = the
    model wrote from training memory, not from retrieved data. We
    exclude already-errored results (they have a real error already)
    and very short responses (legitimately empty).
    """
    if result.error:
        return None  # already failed — different problem
    if result.tool_calls:
        return None  # any tool call at all → not a pure fabrication
    text = (result.text or "").strip()
    if len(text) < _FABRICATION_MIN_TEXT_CHARS:
        return None  # too short to confidently flag
    text_lower = text.lower()
    hit_markers = [m for m in _FABRICATION_GROUNDED_MARKERS if m in text_lower]
    if not hit_markers:
        return None  # no grounded-claim markers — could be a meta reply
    return (
        f"fabricated_no_tool_calls: agent emitted {len(text)} chars of "
        f"domain-loaded text (markers: {hit_markers[:3]}) but made 0 "
        f"MCP calls — output is not grounded in retrieved data"
    )


def _apply_fabrication_guard(result: SubagentResult) -> SubagentResult:
    """If fabrication detected, replace text with empty + set error.

    Returns a new SubagentResult — keeps SubagentResult dataclass
    immutable from caller's view. Other fields (model_used,
    duration_seconds, image_paths) are preserved so observability
    still has the trace of what the agent did.
    """
    reason = _detect_fabrication(result)
    if reason is None:
        return result
    return SubagentResult(
        domain=result.domain,
        company=result.company,
        text="",
        model_used=result.model_used,
        error=reason,
        image_paths=result.image_paths,
        tool_calls=result.tool_calls,
        duration_seconds=result.duration_seconds,
    )


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
    deep: bool = False,
    *,
    budget: RunBudget | None = None,
    cancel_token: CancelToken | None = None,
) -> SubagentResult:
    """Run one subagent with optional hard limits + cooperative cancel.

    `budget` and `cancel_token` are optional so existing callers (CLI,
    older tests) work unchanged. When supplied, the agent.run() coroutine
    is wrapped in a wall-clock timeout and the cancel-token is checked
    before/after the call. Either firing produces a SubagentResult with
    `error="budget_exceeded:..."` so downstream consumers see a clean
    failure, not a partial response.
    """
    budget = budget or RunBudget()
    cancel_token = cancel_token or CancelToken()
    builder = _AGENT_BUILDERS[domain]
    label = f"{domain.value}-{company}" if company else domain.value
    async with sem:
        # Honour cancel BEFORE we even build the agent — saves cost when
        # the user clicked "🛑 Pysäytä" while still in the queue.
        try:
            cancel_token.check()
        except BudgetExceededError as exc:
            return SubagentResult(
                domain=domain, company=company, text="",
                model_used="cancelled", error=f"budget_exceeded: {exc.reason}",
                duration_seconds=0.0,
            )
        t_start = time.time()
        try:
            async with builder(deep=deep) as agent:
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
                # Per-subagent wall-clock cap — Vincit-style 308 s
                # loops get cut at 90 s. The timeout fires the OWASP
                # T1 hard limit; agent.run() is cancelled cleanly via
                # asyncio's CancelledError propagation.
                result = await with_subagent_timeout(
                    agent.run(prompt), budget=budget, label=label,
                )
                model_used = getattr(agent.client, "last_used_model", "unknown")
                # Walk response parts so code blocks, code outputs and images
                # land structured rather than flattened into one text blob.
                text, image_paths, tool_calls = extract_parts(
                    result, run_dir=run_dir, agent_label=label
                )
                # Run the fabrication guard at the boundary so every
                # downstream consumer (LEAD synthesis, conflict detector,
                # forensic logs) sees the same error. See
                # `_detect_fabrication` for the rationale.
                return _apply_fabrication_guard(SubagentResult(
                    domain=domain,
                    company=company,
                    text=text,
                    model_used=model_used,
                    image_paths=image_paths,
                    tool_calls=tool_calls,
                    duration_seconds=time.time() - t_start,
                ))
        except BudgetExceededError as exc:
            # Hard-limit fire — flagged with structured `kind` for the
            # UI to render an appropriate banner. The subagent didn't
            # finish so we have no usable text or tool_calls to surface.
            return SubagentResult(
                domain=domain,
                company=company,
                text="",
                model_used="budget_exceeded",
                error=f"budget_exceeded:{exc.kind} — {exc.reason}",
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
    subagents_deep: bool = False,
    budget: RunBudget | None = None,
    cancel_token: CancelToken | None = None,
) -> WorkflowResult:
    """Spawn subagents per the classification, respecting MAX_CONCURRENT_AGENTS.

    `run_dir` is needed because each subagent may extract images from its
    response into `<run_dir>/images/`.

    `plan` (optional, from `run_planner()`) — when provided, the planner's
    per-subagent guidance is embedded into each subagent's user prompt so
    the dispatch is purposeful instead of generic. None preserves the
    default behaviour bit-for-bit.

    `subagents_deep` (default False) — when True, every subagent's
    builder is called with ``deep=True``, swapping its primary model to
    Gemini Pro. Used by the "Tarkka kaikki" model-tier UI radio. Cost
    multiplier ~30x at the subagent step; reserve for high-stakes queries
    where every word in subagent output matters.
    """
    settings = get_settings()
    sem = asyncio.Semaphore(settings.MAX_CONCURRENT_AGENTS)
    budget = budget or RunBudget()
    cancel_token = cancel_token or CancelToken()

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
                tasks.append(asyncio.create_task(_run_one(
                    domain, query, company, sem, run_dir, plan, subagents_deep,
                    budget=budget, cancel_token=cancel_token,
                )))
        else:
            tasks.append(asyncio.create_task(_run_one(
                domain, query, None, sem, run_dir, plan, subagents_deep,
                budget=budget, cancel_token=cancel_token,
            )))

    t_fanout_start = time.time()
    # Workflow-level wall-clock cap — even with each subagent capped
    # at 90s, fan-out across 4 companies × 3 domains can drag if every
    # agent uses near-budget. 180s is the global safety net.
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=budget.max_workflow_duration_s,
        )
    except TimeoutError as exc:
        # Cancel any still-running tasks so they don't keep running
        # after we've given up on them.
        for task in tasks:
            if not task.done():
                task.cancel()
        raise BudgetExceededError(
            BudgetExceededError.KIND_TIMEOUT_WORKFLOW,
            f"Workflow exceeded {budget.max_workflow_duration_s}s wall-clock",
        ) from exc
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
