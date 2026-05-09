"""aino-sentiment — market signals subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import SENTIMENT_TOOLS, build_mcp_tool
from ._common import load_prompt, resolve_deep_model_override


def build_sentiment_agent(deep: bool = False) -> Agent:
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-sentiment",
        instructions=load_prompt("sentiment.md"),
        tools=build_mcp_tool(name="inderes-sentiment", allowed=SENTIMENT_TOOLS),
    )
