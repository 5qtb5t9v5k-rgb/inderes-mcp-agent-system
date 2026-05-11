"""aino-portfolio — Inderes model portfolio subagent (with sandboxed Python)."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import PORTFOLIO_TOOLS, build_mcp_tool
from ..mcp.yahoo_client import YAHOO_PORTFOLIO_TOOLS, build_yahoo_mcp_tool
from ._common import (
    load_prompt,
    resolve_deep_model_override,
    with_code_execution,
    with_yahoo,
)


def build_portfolio_agent(deep: bool = False) -> Agent:
    """Construct the portfolio subagent.

    When ``YAHOO_MCP_URL`` is set, PORTFOLIO also gets Yahoo's
    ``search_ticker / get_snapshot / get_history`` — useful for
    portfolio-wide pricing snapshots and historical performance
    charts across mixed Finnish + international holdings.
    """
    inderes = build_mcp_tool(name="inderes-portfolio", allowed=PORTFOLIO_TOOLS)
    yahoo = build_yahoo_mcp_tool(name="yahoo-portfolio", allowed=YAHOO_PORTFOLIO_TOOLS)
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-portfolio",
        instructions=load_prompt("portfolio.md"),
        tools=with_code_execution(*with_yahoo(inderes, yahoo), deep=deep),
    )
