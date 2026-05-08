"""Parse aino-valuation agent's output into structured engine inputs.

The agent emits one ```json … ``` block (per ``prompts/valuation.md``).
This module:

  1. Pulls that block out of the agent's free text (defensively — the
     agent might prepend the **Ajatus:** line, append commentary, etc.)
  2. Validates the schema (required fields, sane ranges)
  3. Returns either:
     - a ``ValuationAgentOutput`` ready to feed into ``engine.value_stock``,
     - a ``ValuationAgentSkipped`` when the agent flagged ``valid=false``
       (e.g., loss-making company), or
     - raises ``ValuationParseError`` with the original raw text for
       forensic logging when the JSON is malformed or missing required
       fields.

The parser is intentionally strict: agents that drift from the schema
should fail loudly so we notice and fix the prompt rather than letting
silently-wrong numbers reach the user.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

# Match the first ```json ... ``` (or just ``` ... ```) fenced block in the text.
# Greedy-but-non-overlapping; the agent emits exactly one per prompt.
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*\n(?P<body>\{.*?\})\s*\n?```",
    re.DOTALL | re.IGNORECASE,
)


class ValuationParseError(ValueError):
    """Raised when the agent's output does not contain a parseable JSON block.

    Carries the original raw text in ``raw_text`` so the orchestrator can
    log it for prompt-iteration purposes.
    """

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(frozen=True)
class ValuationAgentSkipped:
    """The agent decided the company can't be valued with this methodology.

    Typical causes: loss-making (ROE ≤ 0), negative book equity, missing
    fundamentals data. The orchestrator should surface ``warnings`` to
    LEAD instead of running the engine.
    """

    company: str
    warnings: list[str]


@dataclass(frozen=True)
class ValuationAgentOutput:
    """Validated agent output — engine-ready inputs + audit trail.

    Pass ``to_engine_kwargs()`` to ``inderes_agent.valuation.value_stock``
    to compute the actual fair value. The other fields (rationales,
    history, dates) are forwarded to the LEAD prompt for the report.
    """

    # Identity
    company: str
    company_id: str | None
    ticker: str | None

    # Inputs to engine
    bvps: float
    bvps_date: str | None
    price: float
    price_date: str | None
    roe_used: float
    k: float
    g: float

    # Audit trail (passed to LEAD, not to engine)
    roe_version: str
    roe_history: dict[str, Any]
    k_rationale: str
    g_rationale: str
    warnings: list[str] = field(default_factory=list)

    def to_engine_kwargs(self) -> dict[str, float]:
        """Keyword args ready to splat into ``engine.value_stock(**...)``."""
        return {
            "bvps": self.bvps,
            "roe": self.roe_used,
            "k": self.k,
            "g": self.g,
            "price": self.price,
        }


# Allowed roe_version values (must match the prompt).
_ALLOWED_ROE_VERSIONS = frozenset({
    "lfy", "3y_avg", "5y_avg",
    "trend_weighted", "min_3y_trend", "avg_3y_trend",
    "manual_override",
})


def _extract_json_block(text: str) -> str:
    """Pull the first fenced JSON block out of the agent's response."""
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        raise ValuationParseError(
            "No ```json ... ``` block found in agent output", raw_text=text
        )
    return m.group("body")


def _ensure_float(blob: dict[str, Any], key: str, raw_text: str) -> float:
    val = blob.get(key)
    if val is None:
        raise ValuationParseError(
            f"Missing required numeric field {key!r}", raw_text=raw_text
        )
    try:
        return float(val)
    except (TypeError, ValueError) as exc:
        raise ValuationParseError(
            f"Field {key!r} is not numeric: {val!r}", raw_text=raw_text
        ) from exc


def _ensure_str(blob: dict[str, Any], key: str, raw_text: str, *, allow_none: bool = False) -> str | None:
    val = blob.get(key)
    if val is None:
        if allow_none:
            return None
        raise ValuationParseError(
            f"Missing required string field {key!r}", raw_text=raw_text
        )
    return str(val)


def parse(
    raw_text: str,
) -> ValuationAgentOutput | ValuationAgentSkipped:
    """Parse + validate one valuation-agent response.

    Returns either:
      - ``ValuationAgentOutput`` with engine-ready inputs (the happy path), or
      - ``ValuationAgentSkipped`` when the agent emitted ``"valid": false``
        (loss-making company, missing data, etc.)

    Raises ``ValuationParseError`` on malformed or schema-violating output.
    """
    json_str = _extract_json_block(raw_text)
    try:
        blob = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValuationParseError(
            f"JSON parse failed: {exc}", raw_text=raw_text
        ) from exc

    if not isinstance(blob, dict):
        raise ValuationParseError(
            f"JSON root is not an object, got {type(blob).__name__}",
            raw_text=raw_text,
        )

    # ── Skipped case: agent emitted {valid: false, ...} ──
    if blob.get("valid") is False:
        company = _ensure_str(blob, "company", raw_text) or "<unknown>"
        warnings = list(blob.get("warnings") or [])
        if not warnings:
            warnings = ["agent flagged valid=false but provided no rationale"]
        return ValuationAgentSkipped(company=company, warnings=warnings)

    # ── Happy path: full output ──
    bvps = _ensure_float(blob, "bvps", raw_text)
    price = _ensure_float(blob, "price", raw_text)
    roe_used = _ensure_float(blob, "roe_used", raw_text)
    k = _ensure_float(blob, "k", raw_text)
    g = _ensure_float(blob, "g", raw_text)

    # Range guards. Order matters: check each value individually first
    # (most diagnostic — "g=5 is outside sane range" tells you exactly
    # which value is wrong), THEN cross-check k vs g (which only fires
    # when both individuals look sane but their relation is broken).
    if not (0.0 < k < 0.30):
        raise ValuationParseError(
            f"k={k} outside sane decimal range (0, 0.30). "
            f"Did the agent emit a percentage?",
            raw_text=raw_text,
        )
    if not (0.0 < g < 0.20):
        raise ValuationParseError(
            f"g={g} outside sane decimal range (0, 0.20). "
            f"Did the agent emit a percentage?",
            raw_text=raw_text,
        )
    if not (0.0 < roe_used < 1.0):
        raise ValuationParseError(
            f"roe_used={roe_used} outside sane decimal range (0, 1.0). "
            f"Did the agent emit a percentage instead of a decimal?",
            raw_text=raw_text,
        )
    if bvps <= 0:
        raise ValuationParseError(
            f"bvps={bvps} must be > 0", raw_text=raw_text
        )
    if price <= 0:
        raise ValuationParseError(
            f"price={price} must be > 0", raw_text=raw_text
        )
    if k <= g:
        raise ValuationParseError(
            f"k ({k}) must be > g ({g}) for Gordon's formula. "
            f"Both values look numerically sane individually, but their "
            f"relation breaks the engine.",
            raw_text=raw_text,
        )

    roe_version_raw = _ensure_str(blob, "roe_version", raw_text)
    if roe_version_raw not in _ALLOWED_ROE_VERSIONS:
        raise ValuationParseError(
            f"roe_version={roe_version_raw!r} not in allowed set "
            f"{sorted(_ALLOWED_ROE_VERSIONS)}",
            raw_text=raw_text,
        )

    company = _ensure_str(blob, "company", raw_text)
    assert company is not None  # for type-checker; _ensure_str raised if missing

    return ValuationAgentOutput(
        company=company,
        company_id=_ensure_str(blob, "company_id", raw_text, allow_none=True),
        ticker=_ensure_str(blob, "ticker", raw_text, allow_none=True),
        bvps=bvps,
        bvps_date=_ensure_str(blob, "bvps_date", raw_text, allow_none=True),
        price=price,
        price_date=_ensure_str(blob, "price_date", raw_text, allow_none=True),
        roe_used=roe_used,
        k=k,
        g=g,
        roe_version=roe_version_raw,  # validated above
        roe_history=blob.get("roe_history") or {},
        k_rationale=_ensure_str(blob, "k_rationale", raw_text) or "",
        g_rationale=_ensure_str(blob, "g_rationale", raw_text) or "",
        warnings=list(blob.get("warnings") or []),
    )
