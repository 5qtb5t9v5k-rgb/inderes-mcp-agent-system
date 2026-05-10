"""Parse aino-valuation agent's output into structured engine inputs.

The agent emits one ```json … ``` block (per ``prompts/valuation.md``).
This module:

  1. Pulls that block out of the agent's free text (defensively — the
     agent might prepend the **Ajatus:** line, append commentary, etc.)
  2. Validates the schema (required fields, sane ranges)
  3. **Validates the ROE-version choice** against the deterministic
     sustainable-ROE rule in ``valuation.roe_selection``. The agent
     provides ``roe_history.raw`` (chronological [year, roe] pairs);
     we recompute statistics from that and verify the agent picked
     what the rule prescribes.
  4. Returns either:
     - a ``ValuationAgentOutput`` ready to feed into ``engine.value_stock``,
     - a ``ValuationAgentSkipped`` when the agent flagged ``valid=false``
       (e.g., loss-making company), or
     - raises ``ValuationParseError`` with the original raw text for
       forensic logging when the JSON is malformed, missing required
       fields, or violates the deterministic rule.

The parser is intentionally strict: agents that drift from the schema
or the rule should fail loudly so we notice and fix the prompt rather
than letting silently-wrong numbers reach the user.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .roe_selection import (
    compute_roe_statistics,
    validate_agent_roe_choice,
)

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
    roe_rationale: str
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


# Allowed roe_version values. Must match the labels select_sustainable_roe
# returns plus a couple of escape hatches (3y_median for short history,
# manual_override when the analyst overrides the rule explicitly).
_ALLOWED_ROE_VERSIONS = frozenset({
    "lfy", "3y_median", "5y_median",
    "trend_weighted", "min_3y_trend",
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


def _levenshtein(a: str, b: str) -> int:
    """Standard Levenshtein edit distance — small, no dependencies.

    Used by ``_get_str_with_typo_tolerance`` to forgive single-character
    typos in long key names (e.g. ``g_ratonale`` for ``g_rationale``).
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                curr[j - 1] + 1,      # insertion
                prev[j] + 1,          # deletion
                prev[j - 1] + cost,   # substitution
            )
        prev = curr
    return prev[-1]


def _get_str_with_typo_tolerance(
    blob: dict[str, Any],
    key: str,
    raw_text: str,
    *,
    max_distance: int = 2,
) -> str:
    """Fetch a string field, accepting near-misses (1–2 char typos).

    When the agent emits ``g_ratonale`` instead of ``g_rationale``, the
    rest of the JSON is fine — the engine inputs are valid, parameters
    parse, and we can compute fair value. Discarding the whole run for a
    single typo is hostile UX. So: if the exact key is missing but a
    nearby key (Levenshtein ≤ 2) exists in the blob, use that and emit
    a soft warning later via the orchestrator's logging.

    Restrictions to keep this safe:
      - only triggers when the EXACT key is absent (never overrides a
        present field)
      - candidate must be ≤ ``max_distance`` edits away (default 2)
      - candidate must be > 6 chars (avoids matching short fields like
        ``k`` ↔ ``g``)
      - candidate must not be one of the OTHER required field names
        (so ``k_rationale`` can't claim ``g_rationale``'s slot)

    Raises ``ValuationParseError`` if no acceptable candidate is found.
    """
    if key in blob and blob[key] is not None:
        return str(blob[key])

    # Don't typo-match short keys — too risky.
    if len(key) <= 6:
        raise ValuationParseError(
            f"Missing required string field {key!r}", raw_text=raw_text
        )

    # Other required keys we should NEVER mistakenly absorb.
    siblings = {
        "k_rationale", "g_rationale", "roe_rationale", "roe_version",
        "company", "company_id", "ticker", "bvps_date", "price_date",
    } - {key}

    best_match: str | None = None
    best_distance = max_distance + 1
    for candidate in blob.keys():
        if not isinstance(candidate, str):
            continue
        if candidate in siblings:
            continue
        if blob.get(candidate) is None:
            continue
        d = _levenshtein(candidate, key)
        if d < best_distance and d > 0:  # >0 ensures not the exact same key
            best_distance = d
            best_match = candidate

    if best_match is None:
        raise ValuationParseError(
            f"Missing required string field {key!r} (no near-match found)",
            raw_text=raw_text,
        )
    return str(blob[best_match])


def _validate_roe_against_rule(
    blob: dict[str, Any],
    roe_used: float,
    roe_version: str,
    raw_text: str,
) -> None:
    """Check that the agent picked the ROE the deterministic rule prescribes.

    Requires the agent to include ``roe_history.raw`` — a chronological
    list of ``[year, roe]`` pairs (oldest first), with `null` for years
    where the metric was not reported.

    We recompute statistics from this raw history (so the agent can't
    silently mis-compute medians) and call ``validate_agent_roe_choice``
    on the result.

    Raises ``ValuationParseError`` if:
      - roe_history.raw is missing or malformed
      - the recomputed rule disagrees with the agent's ``roe_used``
    """
    history_obj = blob.get("roe_history") or {}
    if not isinstance(history_obj, dict):
        raise ValuationParseError(
            "roe_history must be an object", raw_text=raw_text
        )

    raw = history_obj.get("raw")
    if not isinstance(raw, list) or not raw:
        raise ValuationParseError(
            "roe_history.raw is required: a non-empty chronological list of "
            "[year, roe] pairs (oldest first). Use null for years where ROE "
            "was not reported (those years are skipped).",
            raw_text=raw_text,
        )

    # Extract just the ROE values, dropping null years and validating shape
    history_values: list[float] = []
    for i, item in enumerate(raw):
        if not isinstance(item, list) or len(item) != 2:
            raise ValuationParseError(
                f"roe_history.raw[{i}] must be a [year, roe] pair, got {item!r}",
                raw_text=raw_text,
            )
        _, roe_val = item
        if roe_val is None:
            continue  # skip years without reported ROE
        if not isinstance(roe_val, (int, float)):
            raise ValuationParseError(
                f"roe_history.raw[{i}][1] must be numeric or null, got {roe_val!r}",
                raw_text=raw_text,
            )
        history_values.append(float(roe_val))

    if not history_values:
        raise ValuationParseError(
            "roe_history.raw contains no valid (year, roe) pairs after dropping nulls",
            raw_text=raw_text,
        )

    stats = compute_roe_statistics(history_values)
    ok, msg = validate_agent_roe_choice(roe_used, roe_version, stats)
    if not ok:
        raise ValuationParseError(
            f"Sustainable-ROE rule violation: {msg}",
            raw_text=raw_text,
        )


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

    # ── Deterministic sustainable-ROE rule check ──
    # The agent provides roe_history.raw (chronological [year, roe] pairs).
    # We recompute statistics from scratch and verify the agent's choice
    # matches what the rule prescribes. Skipped only for manual_override.
    if roe_version_raw != "manual_override":
        _validate_roe_against_rule(blob, roe_used, roe_version_raw, raw_text)

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
        k_rationale=_get_str_with_typo_tolerance(blob, "k_rationale", raw_text),
        g_rationale=_get_str_with_typo_tolerance(blob, "g_rationale", raw_text),
        roe_rationale=_get_str_with_typo_tolerance(blob, "roe_rationale", raw_text),
        warnings=list(blob.get("warnings") or []),
    )
