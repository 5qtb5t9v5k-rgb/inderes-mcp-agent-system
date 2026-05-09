"""aino-lead — orchestrator agent. No tools; synthesizes subagent outputs."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ._common import load_prompt


def build_lead_agent(deep: bool = False) -> Agent:
    """Construct LEAD with either the default Flash model or a stronger Pro
    model in deep mode.

    ``deep=True`` swaps the primary model for ``settings.LEAD_MODEL_DEEP``
    (Gemini Pro by default). The fallback stays on the configured Flash
    fallback so a Pro 503 / quota cap doesn't fail the synthesis — it
    falls through to Flash. Subagents are unaffected; this only touches
    the single LEAD synthesis call.
    """
    from ..settings import get_settings

    primary_override: str | None = None
    if deep:
        primary_override = get_settings().LEAD_MODEL_DEEP
    return Agent(
        client=build_chat_client(primary_model=primary_override),
        name="aino-lead",
        instructions=load_prompt("lead.md"),
        tools=None,
    )
