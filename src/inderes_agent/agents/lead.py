"""aino-lead — orchestrator agent. No tools; synthesizes subagent outputs."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ._common import load_prompt


def build_lead_agent() -> Agent:
    return Agent(
        client=build_chat_client(),
        name="aino-lead",
        instructions=load_prompt("lead.md"),
        tools=None,
    )
