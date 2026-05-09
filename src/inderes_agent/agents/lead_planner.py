"""aino-lead-planner — strategic planning step before subagent dispatch.

Runs as an opt-in step (UI toggle: "Käytä pidempää suunnittelua") between
the router and the workflow. Reads the user's query and the routing
decision, emits structured JSON describing per-subagent guidance, the
comparison axis (when relevant), and known traps to avoid.

The plan is then:
  1. Surfaced to the user via a "🧠 Suunnitelma" expander in the UI
  2. Embedded in each subagent's prompt as additional context, so each
     subagent's tool calls are more focused than the default
     (effectively a soft pre-execute manager pattern, opt-in to avoid
     the manager-bias trap on simple queries)

LEAD synthesis sees the plan in its prompt too — it can reference what
was planned vs what was actually delivered (e.g. "we set out to
compare ROE but quant returned only one company's data — fall back to
single-stock framing").

Returns ``None`` and skips silently when not enabled — the workflow
proceeds with default per-subagent behavior. This makes the toggle
truly additive: with toggle off, behaviour is bit-for-bit unchanged.
"""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ._common import load_prompt, resolve_deep_model_override


def build_lead_planner_agent(deep: bool = False) -> Agent:
    """Construct the planner. Caller uses it as an async context manager.

    ``deep=True`` runs the planner on Gemini Pro (matching the LEAD-tier
    radio in the UI). The planner's output drives subagent prompts, so
    a higher-quality plan compounds: better plan → better subagent
    output → better synthesis. The cost is small relative to the rest
    of the pipeline (one extra LLM call, no tools, ~1k output tokens).
    """
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-lead-planner",
        instructions=load_prompt("lead_planner.md"),
        tools=None,
    )
