"""aino-research — qualitative research subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import RESEARCH_TOOLS, build_mcp_tool
from ._common import load_prompt


def build_research_agent() -> Agent:
    return Agent(
        client=build_chat_client(),
        name="aino-research",
        instructions=load_prompt("research.md"),
        tools=build_mcp_tool(name="inderes-research", allowed=RESEARCH_TOOLS),
    )
