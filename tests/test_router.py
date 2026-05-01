"""Router unit tests — JSON parsing, fallback behavior, conversation context."""

from __future__ import annotations

import pytest

from inderes_agent.orchestration.router import (
    Domain,
    QueryClassification,
    _extract_json,
)


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_fence():
    raw = '```json\n{"domains": ["quant"], "is_comparison": false, "companies": ["Konecranes"], "reasoning": "x"}\n```'
    parsed = _extract_json(raw)
    assert parsed["domains"] == ["quant"]


def test_extract_json_with_prose_leak():
    raw = 'Here is the JSON:\n\n{"domains":["quant"],"companies":[],"is_comparison":false,"reasoning":"x"}\n\nOK'
    parsed = _extract_json(raw)
    assert parsed["domains"] == ["quant"]


def test_query_classification_validates_domains():
    cls = QueryClassification(
        domains=[Domain.QUANT, Domain.SENTIMENT],
        companies=["Konecranes"],
        is_comparison=False,
        reasoning="single P/E",
    )
    assert Domain.QUANT in cls.domains
    assert cls.companies == ["Konecranes"]


def test_query_classification_rejects_invalid_domain():
    with pytest.raises(Exception):
        QueryClassification(
            domains=["not-a-domain"],  # type: ignore[list-item]
            companies=[],
            is_comparison=False,
            reasoning="",
        )
