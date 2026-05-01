"""aino-quant — numerical analysis subagent (with sandboxed Python)."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import QUANT_TOOLS, build_mcp_tool
from ._common import load_prompt, with_code_execution


def build_quant_agent() -> Agent:
    """Construct the quant subagent. Caller uses it as an async context manager."""
    return Agent(
        client=build_chat_client(),
        name="aino-quant",
        instructions=load_prompt("quant.md"),
        tools=with_code_execution(
            build_mcp_tool(name="inderes-quant", allowed=QUANT_TOOLS),
        ),
    )
