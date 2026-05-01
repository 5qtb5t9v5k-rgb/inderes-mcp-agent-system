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
from dataclasses import dataclass, field

from ..agents import (
    build_portfolio_agent,
    build_quant_agent,
    build_research_agent,
    build_sentiment_agent,
)
from ..settings import get_settings
from .router import Domain, QueryClassification


@dataclass
class SubagentResult:
    domain: Domain
    company: str | None
    text: str
    model_used: str
    error: str | None = None


@dataclass
class WorkflowResult:
    classification: QueryClassification
    subagent_results: list[SubagentResult] = field(default_factory=list)
    fallback_events: int = 0


_AGENT_BUILDERS = {
    Domain.QUANT: build_quant_agent,
    Domain.RESEARCH: build_research_agent,
    Domain.SENTIMENT: build_sentiment_agent,
    Domain.PORTFOLIO: build_portfolio_agent,
}


async def _run_one(
    domain: Domain,
    query: str,
    company: str | None,
    sem: asyncio.Semaphore,
) -> SubagentResult:
    builder = _AGENT_BUILDERS[domain]
    async with sem:
        try:
            async with builder() as agent:
                # If a specific company was specified for this fan-out branch,
                # rephrase the prompt for the subagent so it focuses there.
                prompt = query if company is None else f"For {company}: {query}"
                result = await agent.run(prompt)
                text = result.text if hasattr(result, "text") else str(result)
                model_used = getattr(agent.client, "last_used_model", "unknown")
                return SubagentResult(
                    domain=domain,
                    company=company,
                    text=text,
                    model_used=model_used,
                )
        except Exception as exc:
            return SubagentResult(
                domain=domain,
                company=company,
                text="",
                model_used="error",
                error=str(exc)[:500],
            )


async def run_workflow(
    query: str,
    classification: QueryClassification,
) -> WorkflowResult:
    """Spawn subagents per the classification, respecting MAX_CONCURRENT_AGENTS."""
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
                tasks.append(asyncio.create_task(_run_one(domain, query, company, sem)))
        else:
            tasks.append(asyncio.create_task(_run_one(domain, query, None, sem)))

    results = await asyncio.gather(*tasks)

    fallback_events = sum(
        1 for r in results if r.model_used == settings.FALLBACK_MODEL
    )

    return WorkflowResult(
        classification=classification,
        subagent_results=list(results),
        fallback_events=fallback_events,
    )
