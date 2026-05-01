"""Query classification — which subagents to invoke, fan out per company?

Implemented as a structured-output Gemini call. The lead model is small
(`gemini-3.1-flash-lite-preview`), so we keep the prompt very explicit.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ..llm.gemini_client import build_chat_client


class Domain(str, Enum):
    QUANT = "quant"
    RESEARCH = "research"
    SENTIMENT = "sentiment"
    PORTFOLIO = "portfolio"


class QueryClassification(BaseModel):
    domains: list[Domain] = Field(description="Subagents to invoke; can be 1..4")
    companies: list[str] = Field(default_factory=list, description="Company names mentioned")
    is_comparison: bool = False
    reasoning: str = ""


_ROUTER_INSTRUCTIONS = """\
You are a router for a Nordic stock research assistant. Classify the user query.

Output ONLY a JSON object matching this schema:
{
  "domains":      array of strings, any subset of ["quant","research","sentiment","portfolio"],
  "companies":    array of strings (company names mentioned by user, may be empty),
  "is_comparison": boolean (true if user wants two or more companies compared),
  "reasoning":    short string explaining your routing choice (max 1 sentence)
}

Domain meanings:
- quant      → financial numbers (P/E, ROE, growth, target price, recommendation)
- research   → Inderes' analyst reports, articles, earnings call transcripts, company filings
- sentiment  → insider transactions, forum buzz, calendar events (earnings dates etc.)
- portfolio  → Inderes' model portfolio (holdings, performance)

Few-shot examples:
- "What's Konecranes' P/E?"                     → {"domains":["quant"], "companies":["Konecranes"], "is_comparison":false}
- "Compare Sampo and Nordea on profitability"   → {"domains":["quant"], "companies":["Sampo","Nordea"], "is_comparison":true}
- "Should I be worried about Sampo?"            → {"domains":["quant","research","sentiment"], "companies":["Sampo"], "is_comparison":false}
- "What does Inderes hold right now?"           → {"domains":["portfolio"], "companies":[], "is_comparison":false}
- "Earnings reports this week?"                 → {"domains":["sentiment"], "companies":[], "is_comparison":false}
- "What's interesting in industrials?"          → {"domains":["research","sentiment","portfolio"], "companies":[], "is_comparison":false}
- "Insider activity at Nokia 90 days?"          → {"domains":["sentiment"], "companies":["Nokia"], "is_comparison":false}
- "Latest analyst note on Wärtsilä"             → {"domains":["research"], "companies":["Wärtsilä"], "is_comparison":false}

If the user follow-up is ambiguous (e.g. "and the dividend yield?"), assume continuation: copy companies from previous turn (if provided in CONVERSATION_CONTEXT) and pick the matching domain.

Output only the JSON. No markdown fences. No prose.
"""


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction — strips code fences if Gemini wrapped output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find the first JSON object substring if any prose leaked in.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


async def classify_query(query: str, conversation_context: str = "") -> QueryClassification:
    """Run the router LLM call. Returns a typed classification."""
    from agent_framework import Agent

    prompt = _ROUTER_INSTRUCTIONS
    if conversation_context:
        prompt += f"\n\nCONVERSATION_CONTEXT (last turn summary):\n{conversation_context}\n"

    async with Agent(
        client=build_chat_client(),
        name="router",
        instructions=prompt,
    ) as agent:
        result = await agent.run(query)
        text = result.text if hasattr(result, "text") else str(result)

    try:
        data = _extract_json(text)
        return QueryClassification(**data)
    except Exception:
        # Defensive fallback: route to all domains and let the lead synthesize.
        return QueryClassification(
            domains=[Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT],
            companies=[],
            is_comparison=False,
            reasoning=f"router_parse_failed: {text[:200]}",
        )
