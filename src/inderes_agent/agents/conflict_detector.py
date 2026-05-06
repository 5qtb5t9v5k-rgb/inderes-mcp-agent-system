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
from ._common import load_prompt


def build_conflict_detector_agent() -> Agent:
    return Agent(
        client=build_chat_client(),
        name="aino-conflict-detector",
        instructions=load_prompt("conflict_detector.md"),
        tools=None,
    )
