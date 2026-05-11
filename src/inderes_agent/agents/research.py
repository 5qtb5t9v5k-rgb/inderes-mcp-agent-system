"""aino-research — qualitative research subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import RESEARCH_TOOLS, build_mcp_tool
from ..mcp.yahoo_client import YAHOO_RESEARCH_TOOLS, build_yahoo_mcp_tool
from ._common import load_prompt, resolve_deep_model_override, with_yahoo


def build_research_agent(deep: bool = False) -> Agent:
    """Construct the research subagent.

    When ``YAHOO_MCP_URL`` is set, RESEARCH also gets Yahoo's
    ``search_ticker / get_news`` — news headlines are a narrative
    signal that fits alongside transcripts/documents from Inderes.
    """
    inderes = build_mcp_tool(name="inderes-research", allowed=RESEARCH_TOOLS)
    yahoo = build_yahoo_mcp_tool(name="yahoo-research", allowed=YAHOO_RESEARCH_TOOLS)
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-research",
        instructions=load_prompt("research.md"),
        tools=with_yahoo(inderes, yahoo),
    )
