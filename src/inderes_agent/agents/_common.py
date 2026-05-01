"""Shared agent helpers: prompt loading, optional code-execution tool list."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_framework_gemini import GeminiChatClient

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def with_code_execution(*tools: Any) -> list[Any]:
    """Append Gemini's sandboxed code-execution tool to a list of tools.

    Use this for agents that benefit from real Python computation (pandas/numpy
    in a sandbox) rather than the LLM doing arithmetic in its head. See
    `gemini_with_code_execution.py` in agent_framework_gemini's samples for the
    canonical pattern.
    """
    return [*tools, GeminiChatClient.get_code_interpreter_tool()]
