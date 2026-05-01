"""aino-portfolio — Inderes model portfolio subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import PORTFOLIO_TOOLS, build_mcp_tool
from ._common import load_prompt


def build_portfolio_agent() -> Agent:
    return Agent(
        client=build_chat_client(),
        name="aino-portfolio",
        instructions=load_prompt("portfolio.md"),
        tools=build_mcp_tool(name="inderes-portfolio", allowed=PORTFOLIO_TOOLS),
    )
