"""aino-conflict-detector — structural pre-synthesis pass.

Reads N subagent outputs, emits strict JSON describing where they agree,
disagree, and which claims are isolated to a single subagent. The downstream
LEAD synthesis sees this structured map as explicit context.

This is the BACKLOG #1 (plan-then-execute) extension that makes the
emergent multi-subagent self-correction observed in Case 003 of
evals/known-cases.md *explicit and loggable* rather than implicit in the
lead's training-data priors.
"""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ._common import load_prompt, resolve_deep_model_override


def build_conflict_detector_agent(deep: bool = False) -> Agent:
    """Build the pre-synthesis conflict-detector agent. ``deep=True`` runs
    on Pro — useful at the "Tarkka kaikki" tier where every step gets
    upgraded reasoning."""
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-conflict-detector",
        instructions=load_prompt("conflict_detector.md"),
        tools=None,
    )
