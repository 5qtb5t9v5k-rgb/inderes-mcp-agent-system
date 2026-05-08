"""Tests for the valuation-agent JSON parser.

Verifies that ``inderes_agent.valuation.parser.parse`` correctly handles:
  - well-formed agent outputs (happy path)
  - the explicit "valid=false" skip path
  - common malformations (missing fields, percentages instead of decimals,
    bad roe_version, k <= g, prose-only outputs)

These run without the LLM — fixtures are constructed strings simulating
what aino-valuation would emit.
"""

from __future__ import annotations

import pytest

from inderes_agent.valuation import (
    ValuationAgentOutput,
    ValuationAgentSkipped,
    ValuationParseError,
    parse,
    value_stock,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


SAMPO_GOOD = """\
**Ajatus:** Lasken Sammon arvonmäärityksen omalla mallilla. Vakuutusyhtiö
on defensiivinen — käytän k=9% ja g=2.5%. ROE on ollut vakaa 14–15%
viime 5 vuotta, joten käytän 5v keskiarvoa.

```json
{
  "company": "Sampo Oyj",
  "company_id": "COMPANY:382",
  "ticker": "SAMPO",
  "bvps": 18.20,
  "bvps_date": "2025-12-31",
  "price": 39.85,
  "price_date": "2026-05-08",
  "roe_used": 0.149,
  "roe_version": "5y_avg",
  "roe_history": {
    "lfy": 0.141,
    "3y_avg": 0.140,
    "5y_avg": 0.149,
    "trend_weighted": 0.143,
    "trend_label": "vakaa"
  },
  "k": 0.09,
  "g": 0.025,
  "k_rationale": "Vakuutusyhtiö, defensiivinen sektori — k=9%.",
  "g_rationale": "Pohjoismainen vakuutus on kypsä — varovainen 2.5%.",
  "warnings": []
}
```
"""


def _good_agent_text(**overrides) -> str:
    """Build a minimal valid agent output, overriding fields as needed."""
    base = {
        "company": "Test Oyj", "company_id": "COMPANY:1", "ticker": "TST",
        "bvps": 10.0, "bvps_date": "2025-12-31",
        "price": 12.0, "price_date": "2026-05-08",
        "roe_used": 0.15, "roe_version": "5y_avg",
        "roe_history": {"lfy": 0.15, "5y_avg": 0.15, "trend_label": "vakaa"},
        "k": 0.09, "g": 0.05,
        "k_rationale": "test", "g_rationale": "test",
        "warnings": [],
    }
    base.update(overrides)
    import json as _json
    return f"**Ajatus:** test.\n\n```json\n{_json.dumps(base)}\n```"


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_parses_full_sampo_output() -> None:
    result = parse(SAMPO_GOOD)
    assert isinstance(result, ValuationAgentOutput)
    assert result.company == "Sampo Oyj"
    assert result.company_id == "COMPANY:382"
    assert result.ticker == "SAMPO"
    assert result.bvps == 18.20
    assert result.price == 39.85
    assert result.roe_used == 0.149
    assert result.roe_version == "5y_avg"
    assert result.k == 0.09
    assert result.g == 0.025
    assert result.warnings == []
    assert result.roe_history["trend_label"] == "vakaa"


def test_engine_kwargs_round_trip() -> None:
    """Parser output should feed straight into engine.value_stock(**kwargs)."""
    result = parse(SAMPO_GOOD)
    assert isinstance(result, ValuationAgentOutput)
    v = value_stock(**result.to_engine_kwargs())
    # Sampo with ROE 14.9% > k 9% → laatuyhtiö
    assert v.quality == "laatu"
    assert v.fair_value > v.epv_pure


def test_parser_handles_prose_after_json() -> None:
    """The parser must extract JSON even when there's text before AND after."""
    text = (
        _good_agent_text()
        + "\n\nLisätietoa: tämä prose pitäisi pudota pois.\n"
    )
    result = parse(text)
    assert isinstance(result, ValuationAgentOutput)


def test_parser_handles_no_json_fence_marker() -> None:
    """Some models emit just ``` instead of ```json — accept both."""
    text = _good_agent_text().replace("```json", "```")
    result = parse(text)
    assert isinstance(result, ValuationAgentOutput)


# ─────────────────────────────────────────────────────────────────────────────
# Skipped path — valid=false
# ─────────────────────────────────────────────────────────────────────────────


def test_skipped_for_loss_making_company() -> None:
    text = """**Ajatus:** Yhtiö on tappiollinen.

```json
{
  "company": "Loss Co Oyj",
  "valid": false,
  "warnings": ["ROE oli -3.2% LFY:llä — tappiollinen, omaa Gordon-mallia ei voi soveltaa"]
}
```
"""
    result = parse(text)
    assert isinstance(result, ValuationAgentSkipped)
    assert result.company == "Loss Co Oyj"
    assert len(result.warnings) == 1


def test_skipped_provides_default_warning_if_none() -> None:
    text = """```json
{"company": "X", "valid": false}
```"""
    result = parse(text)
    assert isinstance(result, ValuationAgentSkipped)
    assert len(result.warnings) == 1
    assert "valid=false" in result.warnings[0]


# ─────────────────────────────────────────────────────────────────────────────
# Error paths — strict failure for malformed output
# ─────────────────────────────────────────────────────────────────────────────


def test_no_json_block_raises() -> None:
    text = "Just prose, no JSON anywhere."
    with pytest.raises(ValuationParseError, match="No.*json.*block"):
        parse(text)


def test_malformed_json_raises() -> None:
    text = "```json\n{not valid json}\n```"
    with pytest.raises(ValuationParseError, match="JSON parse failed"):
        parse(text)


def test_missing_required_field_raises() -> None:
    """If bvps missing, parser must fail loudly."""
    text = _good_agent_text()
    text = text.replace('"bvps": 10.0, ', "")
    with pytest.raises(ValuationParseError, match="bvps"):
        parse(text)


def test_percentage_instead_of_decimal_for_k_caught() -> None:
    """Common LLM mistake: emitting 9 instead of 0.09 for k."""
    text = _good_agent_text(k=9.0)  # should be 0.09
    with pytest.raises(ValuationParseError, match="k=.*sane decimal range"):
        parse(text)


def test_percentage_instead_of_decimal_for_g_caught() -> None:
    text = _good_agent_text(g=5.0)  # should be 0.05
    with pytest.raises(ValuationParseError, match="g=.*sane decimal range"):
        parse(text)


def test_percentage_instead_of_decimal_for_roe_caught() -> None:
    text = _good_agent_text(roe_used=15.0)  # should be 0.15
    with pytest.raises(ValuationParseError, match="roe_used=.*sane decimal range"):
        parse(text)


def test_k_below_g_caught_before_engine() -> None:
    """Parser catches Gordon violation before engine even sees the input."""
    text = _good_agent_text(k=0.04, g=0.05)
    with pytest.raises(ValuationParseError, match="k.*must be > g"):
        parse(text)


def test_negative_bvps_caught() -> None:
    text = _good_agent_text(bvps=-1.0)
    with pytest.raises(ValuationParseError, match="bvps"):
        parse(text)


def test_negative_price_caught() -> None:
    text = _good_agent_text(price=-1.0)
    with pytest.raises(ValuationParseError, match="price"):
        parse(text)


def test_invalid_roe_version_rejected() -> None:
    text = _good_agent_text(roe_version="averaged_somehow")
    with pytest.raises(ValuationParseError, match="roe_version"):
        parse(text)


def test_parse_error_carries_raw_text_for_logging() -> None:
    """Forensic logging contract: ValuationParseError exposes raw_text."""
    raw = "totally unparseable content"
    with pytest.raises(ValuationParseError) as exc_info:
        parse(raw)
    assert exc_info.value.raw_text == raw
