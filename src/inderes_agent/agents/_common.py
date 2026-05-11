"""Shared agent helpers: prompt loading, optional code-execution tool list."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from agent_framework_gemini import GeminiChatClient

PROMPTS_DIR = Path(__file__).parent / "prompts"

_FI_WEEKDAYS = {
    0: "maanantai", 1: "tiistai", 2: "keskiviikko", 3: "torstai",
    4: "perjantai", 5: "lauantai", 6: "sunnuntai",
}


def _today_header() -> str:
    """Date-aware preamble injected at the top of every loaded prompt.

    Without this, when a prompt says ``dateFrom=today-90d`` or the user asks
    "mitä tuloksia tänään julkaistaan", Gemini falls back to its training
    cutoff and silently returns dates from a year or more ago. We inject the
    real current date in both ISO and Finnish-weekday form so the model has
    no excuse to guess.
    """
    today = date.today()
    iso = today.isoformat()
    weekday_fi = _FI_WEEKDAYS[today.weekday()]
    return (
        "# CURRENT DATE\n"
        f"Today is **{iso}** ({weekday_fi}). When the user asks about "
        '"today" / "tänään", "this week" / "tällä viikolla", "next 7 days", '
        "or when a tool parameter says `today`, `today-90d`, `today+7d` etc., "
        "compute it from this date. **Never** use a date older than this — "
        "if your training cutoff is earlier, ignore it; this date is "
        "authoritative.\n\n---\n\n"
    )


def today_prompt_prefix() -> str:
    """Same date preamble, formatted as a user-message prefix.

    System instructions sometimes get less attention than the user prompt
    when the conversation is long. Prefix every per-query prompt with the
    same date info so it's the very first token the model attends to.
    """
    today = date.today()
    iso = today.isoformat()
    weekday_fi = _FI_WEEKDAYS[today.weekday()]
    return (
        f"[CURRENT DATE: {iso} — {weekday_fi}. "
        "Use this for any 'today' / 'tänään' references. "
        "Never substitute a date from your training data.]\n\n"
    )


def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return _today_header() + path.read_text(encoding="utf-8")


def resolve_deep_model_override(deep: bool) -> str | None:
    """Returns the deep model name (e.g. ``'gemini-2.5-pro'``) when
    ``deep=True``, else ``None`` (= use the default Flash Lite primary).

    Used by every agent builder that accepts a ``deep`` parameter to map
    the boolean toggle into the right ``primary_model`` override for
    ``build_chat_client``. Centralised here so the model name lives in
    settings and adding a third tier later (e.g. opus/claude) only
    needs to change this function + settings.
    """
    if not deep:
        return None
    from ..settings import get_settings
    return get_settings().LEAD_MODEL_DEEP


def with_yahoo(inderes_tool: Any, yahoo_tool: Any | None) -> list[Any]:
    """Combine an agent's Inderes MCP tool with its optional Yahoo MCP
    tool into a single ``tools=`` list.

    Yahoo is strictly additive: when ``yahoo_tool is None`` (i.e.
    ``YAHOO_MCP_URL`` is unset), the Inderes-only behaviour is
    preserved bit-for-bit. When it's present, the agent gets both as
    independent MCP toolsets and the LLM chooses which to call.

    Centralising this here lets the per-agent builders stay one-liners
    while making the Yahoo opt-in pattern unambiguous in the code
    surface.
    """
    return [inderes_tool, yahoo_tool] if yahoo_tool is not None else [inderes_tool]


def with_code_execution(*tools: Any, deep: bool = False) -> list[Any]:
    """Append Gemini's sandboxed code-execution tool to a list of tools.

    Use this for agents that benefit from real Python computation (pandas/numpy
    in a sandbox) rather than the LLM doing arithmetic in its head. See
    `gemini_with_code_execution.py` in agent_framework_gemini's samples for the
    canonical pattern.

    **Pro mode caveat (deep=True):** Gemini 2.5 Pro rejects requests
    that include the code-execution tool with the error
    ``"Tool call context circulation is not enabled for models/
    gemini-2.5-pro"``. The "Tool call context circulation" plumbing
    is a Flash-only feature in google-genai's current SDK. To keep
    "Tarkka kaikki" (all-Pro) tier functional, we omit the
    code-interpreter tool when ``deep=True`` — agents fall back to
    LLM-side arithmetic. Pro's reasoning is strong enough that simple
    CAGR / ratio computations don't need a sandbox; complex stats
    work would warrant a separate solution anyway.

    Pure-Flash callers (``deep=False``, default) get the unchanged
    behaviour with the code interpreter attached.
    """
    if deep:
        # Pro mode: skip code-interpreter to avoid the context-circulation
        # rejection. Agent runs MCP tools only; LLM does arithmetic itself.
        return list(tools)
    return [*tools, GeminiChatClient.get_code_interpreter_tool()]
