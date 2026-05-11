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
from ..mcp.yahoo_client import YAHOO_VALUATION_TOOLS, build_yahoo_mcp_tool
from ._common import load_prompt, resolve_deep_model_override, with_yahoo


def build_valuation_agent(deep: bool = False) -> Agent:
    """Construct the valuation subagent. Caller uses it as an async context manager.

    No code-execution sandbox: the agent's job is to produce JSON, not to
    do arithmetic. The deterministic engine handles all the math.

    When ``YAHOO_MCP_URL`` is set, VALUATION also gets Yahoo's
    ``search_ticker / get_snapshot``. ``get_snapshot`` provides BVPS
    and price values that are fresher than Inderes' year-end-locked
    fundamentals (Q-report level vs LFY-only), which directly improves
    P/B-based valuation for both Finnish and international names.
    """
    inderes = build_mcp_tool(name="inderes-valuation", allowed=VALUATION_TOOLS)
    yahoo = build_yahoo_mcp_tool(name="yahoo-valuation", allowed=YAHOO_VALUATION_TOOLS)
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-valuation",
        instructions=load_prompt("valuation.md"),
        tools=with_yahoo(inderes, yahoo),
    )
