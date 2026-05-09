"""aino-quant — numerical analysis subagent (with sandboxed Python)."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import QUANT_TOOLS, build_mcp_tool
from ._common import load_prompt, resolve_deep_model_override, with_code_execution


def build_quant_agent(deep: bool = False) -> Agent:
    """Construct the quant subagent. Caller uses it as an async context manager.

    ``deep=True`` upgrades the agent's primary model to the configured
    ``LEAD_MODEL_DEEP`` (Gemini Pro by default). Used by the "Tarkka
    kaikki" tier — fallback stays on Flash so a Pro 503 still completes.
    """
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-quant",
        instructions=load_prompt("quant.md"),
        tools=with_code_execution(
            build_mcp_tool(name="inderes-quant", allowed=QUANT_TOOLS),
        ),
    )
