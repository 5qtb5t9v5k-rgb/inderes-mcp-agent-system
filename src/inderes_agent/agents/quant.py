"""aino-quant — numerical analysis subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import QUANT_TOOLS, build_mcp_tool
from ._common import load_prompt


def build_quant_agent() -> Agent:
    """Construct the quant subagent. Caller uses it as an async context manager."""
    return Agent(
        client=build_chat_client(),
        name="aino-quant",
        instructions=load_prompt("quant.md"),
        tools=build_mcp_tool(name="inderes-quant", allowed=QUANT_TOOLS),
    )
