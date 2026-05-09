"""LLM-judge backend for Tier 1 evals.

Provider-agnostic ``JudgeBackend`` Protocol + a concrete
``GeminiJudge`` implementation. The choice of Gemini 2.5 Pro is
documented in ``evals/judge_selection.md`` (data-driven from
JudgeBench, RewardBench 2, Arena-Hard, Vectara HHEM v2).

Why a separate module: the runner stays provider-neutral, so adding a
GPT-4.1 cross-family validator later is a 1-line config change.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

# Project uses the newer google-genai SDK (not google-generativeai).
# Direct import — not via the agent_framework wrapper — because the
# judge call has no tools, no streaming, no MAF integration; it's a
# single round-trip with structured JSON output.
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError as e:  # pragma: no cover - environment guard
    raise ImportError(
        "google-genai not installed. Install with `pip install google-"
        "genai` (already a dep of the project's MAF Gemini provider)."
    ) from e


# Default judge model. Can be overridden via env (JUDGE_MODEL).
DEFAULT_JUDGE_MODEL = "gemini-2.5-pro"


class JudgeBackend(Protocol):
    """Provider-neutral judge interface.

    Adding a new provider (GPT-4.1, Sonnet, multi-judge consensus) means
    implementing this protocol and registering it in ``runner.py``.
    """

    name: str

    def grade(
        self, case: dict[str, Any], context: dict[str, Any], rubric: str
    ) -> dict[str, Any]:
        """Grade a single case.

        Args:
            case: Case definition from golden.yaml (id, query_match,
                rationale, soft criteria).
            context: Run artifacts the judge sees (routing, tool_calls,
                synthesis, päättely, etc.).
            rubric: Full rubric prompt (rubric.md content).

        Returns:
            JSON-shaped dict matching the rubric's specified output:
                {scores: {...}, global_flags: {...}, overall_quality, ...}
        """
        ...


# ---------------------------------------------------------------------------
# Gemini implementation
# ---------------------------------------------------------------------------


class GeminiJudge:
    """Gemini 2.5 Pro judge — primary judge per data-driven selection.

    Setup: requires GEMINI_API_KEY env var (already used by the agent
    pipeline). No new credential needed.

    Pricing: ~$0.009/case (3000 input + 500 output tokens at $1.25/$10
    per 1M). 20-case nightly = $0.18. ~$5.25/month.
    """

    name = "gemini-2.5-pro"

    def __init__(self, model: str = DEFAULT_JUDGE_MODEL) -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
            "GOOGLE_API_KEY"
        )
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) not set. The judge "
                "needs the same Gemini key as the pipeline. Export it "
                "or add to .env."
            )
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        # response_mime_type=application/json forces structured output.
        # temperature=0 keeps the judge deterministic across retries.
        # max_output_tokens=8192 leaves headroom for Gemini 2.5 Pro's
        # default thinking budget — the model REQUIRES a positive
        # thinking budget (budget=0 returns 400 INVALID_ARGUMENT). With
        # 2048 we observed empty text on 5/6 cases because thinking
        # ate the output budget. With 8192 there's enough left for
        # both reasoning AND the JSON rubric output.
        self._gen_config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=8192,
        )

    def grade(
        self, case: dict[str, Any], context: dict[str, Any], rubric: str
    ) -> dict[str, Any]:
        prompt = _build_prompt(case, context, rubric)
        try:
            resp = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=self._gen_config,
            )
        except Exception as exc:
            return {
                "_error": f"judge call failed: {exc!r}",
                "_judge": self.name,
            }

        text = getattr(resp, "text", "") or ""
        parsed = _parse_judge_json(text)
        if parsed is None:
            return {
                "_error": "judge returned non-JSON output",
                "_raw": text[:1000],
                "_judge": self.name,
            }
        parsed["_judge"] = self.name
        parsed["_model"] = self._model_name
        return parsed


# ---------------------------------------------------------------------------
# Prompt + parsing helpers
# ---------------------------------------------------------------------------


def _build_prompt(
    case: dict[str, Any], context: dict[str, Any], rubric: str
) -> str:
    """Assemble the full judge prompt.

    Structure: rubric instructions → case under evaluation → run
    artifacts → reminder to return JSON only.

    Tool calls are truncated per-call to keep the input manageable —
    full tool results would blow past 10k+ tokens for multi-agent runs.
    The judge sees enough to verify presence of a tool call without
    needing the full payload.
    """
    soft = case.get("soft") or {}
    soft_block = "\n".join(
        f"- **{name}**: {desc.strip()}"
        for name, desc in soft.items()
    ) or "(no soft criteria for this case)"

    # Truncate tool-call results — keep first 400 chars per call.
    tool_calls_view = []
    for tc in context.get("tool_calls") or []:
        tc_view = {
            "agent": tc.get("agent_domain"),
            "tool": tc.get("tool_name"),
            "arguments": _truncate_json(tc.get("arguments_json"), 200),
            "item_count": tc.get("item_count"),
            "error": tc.get("error_text"),
        }
        tool_calls_view.append(tc_view)

    artifacts = {
        "query": context.get("query"),
        "routing": {
            "domains": context.get("routing_domains"),
            "companies": context.get("routing_companies"),
            "is_comparison": context.get("routing_is_comparison"),
            "reasoning": context.get("routing_reasoning"),
        },
        "tool_calls": tool_calls_view,
        "conflict_detector": {
            "agreements_count": context.get("agreements_count"),
            "conflicts_count": context.get("conflicts_count"),
            "isolated_count": context.get("isolated_count"),
        },
        "paattely_kind": context.get("paattely_kind"),
        "synthesis": _truncate_text(context.get("synthesis", ""), 4000),
    }

    return (
        rubric
        + "\n\n---\n\n# CASE UNDER EVALUATION\n\n"
        + f"**Case ID:** `{case.get('id')}`\n\n"
        + f"**Query:** {case.get('query_match')!r}\n\n"
        + f"**Why this case exists:**\n{(case.get('rationale') or '').strip()}\n\n"
        + "**Soft criteria to grade (1-5 each):**\n"
        + soft_block
        + "\n\n# RUN ARTIFACTS\n\n```json\n"
        + json.dumps(artifacts, ensure_ascii=False, indent=2)
        + "\n```\n\nReturn JSON only."
    )


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_judge_json(text: str) -> dict[str, Any] | None:
    """Parse the judge's response into a dict.

    Defensive: even though we set response_mime_type=application/json,
    the model occasionally wraps in ```json fences or adds a preamble.
    """
    text = text.strip()
    if not text:
        return None
    # Strip fences if present.
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: find the first '{' and last '}' and try that slice.
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(text[first : last + 1])
            except json.JSONDecodeError:
                return None
        return None


def _truncate_json(s: str | None, limit: int) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else s[:limit] + "…"


def _truncate_text(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n\n…[truncated, full length {len(s)} chars]"


# ---------------------------------------------------------------------------
# Factory — runner asks for the configured backend
# ---------------------------------------------------------------------------


def get_judge_backend(name: str | None = None) -> JudgeBackend | None:
    """Return the configured judge backend, or None if disabled.

    Selection order:
      1. ``name`` arg if provided ('gemini' / 'gpt-4.1' / 'sonnet')
      2. ``JUDGE_BACKEND`` env var
      3. Default: gemini if GEMINI_API_KEY set, else None (skip soft eval)

    Future cross-family validator (GPT-4.1) plugs in here as a new
    branch — runner.py and golden.yaml stay unchanged.
    """
    backend = (name or os.environ.get("JUDGE_BACKEND") or "").lower().strip()
    has_gemini = bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )

    if backend == "" and has_gemini:
        backend = "gemini"

    if backend == "gemini":
        return GeminiJudge()

    if backend == "off" or backend == "none":
        return None

    if backend in ("gpt-4.1", "openai"):
        # Stub for future implementation. Same JudgeBackend protocol.
        raise NotImplementedError(
            "GPT-4.1 backend not implemented yet. Selected for cross-"
            "family validation in §10 nightly cron — see "
            "evals/judge_selection.md. Add an OpenAIJudge class here."
        )

    if backend in ("sonnet", "anthropic", "claude"):
        raise NotImplementedError(
            "Claude Sonnet 4.5 ruled out as judge per "
            "evals/judge_selection.md (>10% hallucination on Vectara "
            "HHEM v2). If you really want it, add an AnthropicJudge "
            "class here, but read the rationale first."
        )

    return None
