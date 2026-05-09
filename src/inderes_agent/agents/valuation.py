"""aino-valuation — vaihtoehtoinen arvonmääritys -subagentti.

Fetches BVPS / ROE history / price via Inderes MCP and emits structured
JSON describing the parameters (k, g, ROE-version + rationale). The
deterministic engine in ``inderes_agent.valuation`` consumes that JSON
and computes the actual fair value.

This agent is **opt-in** — it runs only when the user has the "Käytä
vaihtoehtoista arvonmääritystä" toggle enabled in the UI. The default
research flow (router → quant/research/sentiment/portfolio → LEAD) is
unchanged.

Output contract: see ``agents/prompts/valuation.md`` for the exact JSON
schema. The orchestrator parses it via ``valuation.parser.parse``.
"""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import VALUATION_TOOLS, build_mcp_tool
from ._common import load_prompt


def build_valuation_agent() -> Agent:
    """Construct the valuation subagent. Caller uses it as an async context manager.

    No code-execution sandbox: the agent's job is to produce JSON, not to
    do arithmetic. The deterministic engine handles all the math.
    """
    return Agent(
        client=build_chat_client(),
        name="aino-valuation",
        instructions=load_prompt("valuation.md"),
        tools=build_mcp_tool(name="inderes-valuation", allowed=VALUATION_TOOLS),
    )
