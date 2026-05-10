"""Tests for the fabrication guard + no-data synthesis short-circuit.

Both protect against the case_004 trust-killer pattern documented in
evals/golden.yaml: subagents producing long domain-loaded text without
making any MCP tool calls (i.e. fabricating from training memory).

The guard belongs in two places, tested in parallel here:

  1. workflows.py — the per-subagent fabrication detector that flips a
     fabricated SubagentResult to error before it leaves the boundary.
  2. synthesis.py — the orchestration-level short-circuit that returns
     a fixed "no data" response when ALL subagents have errored.
"""

from __future__ import annotations

from inderes_agent.orchestration.router import Domain, QueryClassification
from inderes_agent.orchestration.synthesis import (
    _all_subagents_failed_or_fabricated,
    _no_data_response,
)
from inderes_agent.orchestration.workflows import (
    SubagentResult,
    WorkflowResult,
    _apply_fabrication_guard,
    _detect_fabrication,
)

# ---------------------------------------------------------------------------
# Layer 1 — _detect_fabrication (the heuristic itself)
# ---------------------------------------------------------------------------


def _result(text: str = "", tool_calls: list | None = None, error: str | None = None) -> SubagentResult:
    return SubagentResult(
        domain=Domain.RESEARCH,
        company=None,
        text=text,
        model_used="gemini-3.1-flash-lite-preview",
        error=error,
        tool_calls=tool_calls or [],
    )


# A faithful reproduction of the Vincit fabrication that case_004
# captured. Long, with euro signs, recommendation words, "Sources:"
# line — every red flag.
VINCIT_FABRICATED_TEXT = """\
Vincitin osakkeeseen suhtaudutaan tällä hetkellä markkinoilla varovaisesti.

**Inderes view: VÄHENNÄ, tavoitehinta 1,25 €**

| Mittari | Tilanne |
| :--- | :--- |
| Kannattavuus | Heikko (Q1'26 EBITA-marginaali 1,8 %) |
| Riski | 4/5 |

Sources: get-fundamentals, get-inderes-estimates, list-content, get-content,
list-transcripts, list-insider-transactions, get-forum-posts
"""


def test_detect_fabrication_flags_vincit_pattern():
    """The exact Vincit failure case should be caught."""
    r = _result(text=VINCIT_FABRICATED_TEXT, tool_calls=[])
    reason = _detect_fabrication(r)
    assert reason is not None
    assert "fabricated_no_tool_calls" in reason
    # Sanity: the reason names some markers it found.
    assert "tavoitehint" in reason or "vähennä" in reason or "€" in reason


def test_detect_fabrication_passes_short_response():
    """A short 'I have nothing to say' reply is NOT a fabrication."""
    r = _result(text="Nothing relevant found in the catalog.", tool_calls=[])
    assert _detect_fabrication(r) is None


def test_detect_fabrication_passes_with_any_tool_call():
    """Any MCP call at all → not a pure fabrication.

    A response with one tool call followed by a long synthesis is a
    different (and acceptable) shape. The guard is for ZERO-call
    cases only.
    """
    from inderes_agent.observability.output_parts import ToolCallTrace
    tc = ToolCallTrace(
        name="search-companies", arguments={"query": "Vincit"},
        result_text="{}", item_count=None, item_names=[],
        error=None, call_id="abc",
    )
    r = _result(text=VINCIT_FABRICATED_TEXT, tool_calls=[tc])
    assert _detect_fabrication(r) is None


def test_detect_fabrication_passes_already_errored():
    """Don't double-flag a result that already has an error."""
    r = _result(
        text=VINCIT_FABRICATED_TEXT, tool_calls=[],
        error="something else broke"
    )
    assert _detect_fabrication(r) is None


def test_detect_fabrication_passes_long_meta_reply():
    """A long reply WITHOUT grounded markers (no €, no recommendation
    words, no Sources line) is not flagged.

    Edge case: an agent might write a long methodological aside that
    legitimately contains no MCP calls. We don't want to flag that.
    """
    long_meta = (
        "Tämä on metakeskustelu siitä, miten arvostuksia kannattaa "
        "tulkita yleisellä tasolla. " * 20  # ~1200 chars, no domain markers
    )
    r = _result(text=long_meta, tool_calls=[])
    assert _detect_fabrication(r) is None


# ---------------------------------------------------------------------------
# Layer 1 — _apply_fabrication_guard (the wrapper that flips state)
# ---------------------------------------------------------------------------


def test_apply_fabrication_guard_flips_error():
    """Fabricated result → text cleared, error populated, observability
    fields preserved."""
    r = _result(text=VINCIT_FABRICATED_TEXT, tool_calls=[])
    out = _apply_fabrication_guard(r)
    assert out.text == ""
    assert out.error is not None
    assert "fabricated_no_tool_calls" in out.error
    # Preserved fields
    assert out.domain == r.domain
    assert out.model_used == r.model_used


def test_apply_fabrication_guard_passthrough_when_clean():
    """Clean result → identity (modulo dataclass copy)."""
    r = _result(text="short reply", tool_calls=[])
    out = _apply_fabrication_guard(r)
    assert out.text == "short reply"
    assert out.error is None


# ---------------------------------------------------------------------------
# Layer 2 — _all_subagents_failed_or_fabricated + _no_data_response
# ---------------------------------------------------------------------------


def _classification(companies: list[str], domains: list[Domain] | None = None) -> QueryClassification:
    return QueryClassification(
        domains=domains or [Domain.QUANT, Domain.RESEARCH, Domain.SENTIMENT],
        companies=companies,
        is_comparison=False,
        reasoning="x",
    )


def test_all_failed_detects_all_errored():
    wr = WorkflowResult(
        classification=_classification(["Vincit"]),
        subagent_results=[
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
        ],
    )
    assert _all_subagents_failed_or_fabricated(wr) is True


def test_all_failed_one_clean_subagent_keeps_normal_synthesis():
    """If even one subagent retrieved data, we proceed with normal synthesis."""
    from inderes_agent.observability.output_parts import ToolCallTrace
    clean = _result(
        text="real subagent answer",
        tool_calls=[ToolCallTrace(
            name="get-fundamentals", arguments={}, result_text="{}",
            item_count=None, item_names=[], error=None, call_id="x",
        )],
    )
    wr = WorkflowResult(
        classification=_classification(["Sampo"]),
        subagent_results=[
            clean,
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
        ],
    )
    assert _all_subagents_failed_or_fabricated(wr) is False


def test_all_failed_zero_subagents_returns_false():
    """Empty subagent list ≠ failure-by-fabrication.

    This is a routing failure (no subagent dispatched) — different
    error class, handled elsewhere.
    """
    wr = WorkflowResult(
        classification=_classification([]),
        subagent_results=[],
    )
    assert _all_subagents_failed_or_fabricated(wr) is False


def test_no_data_response_includes_company_name():
    """The fixed message names the company so the user knows what
    didn't get found."""
    wr = WorkflowResult(
        classification=_classification(["Vincit"]),
        subagent_results=[
            _result(error="fabricated_no_tool_calls: marker=€", tool_calls=[]),
        ],
    )
    text, model_used, trace = _no_data_response("vincit?", wr)
    assert "Vincit" in text
    assert "Inderes-tietokannasta" in text
    assert model_used == "skipped_no_data"
    assert trace.conflict_report.skipped_reason == "all_subagents_failed_or_fabricated"


def test_no_data_response_no_invented_numbers():
    """The hard contract: no euro signs / percentages / recommendations
    in the fixed answer. If the response itself fabricated, the whole
    point of the short-circuit collapses."""
    wr = WorkflowResult(
        classification=_classification(["Vincit"]),
        subagent_results=[
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
        ],
    )
    text, _, _ = _no_data_response("vincit?", wr)
    forbidden_invented = ["€ ", " %", "VÄHENNÄ", "LISÄÄ", "OSTA", "MYY",
                          "tavoitehinta"]
    for phrase in forbidden_invented:
        # `Inderes-tietokannasta` is fine; check phrase-level.
        assert phrase not in text, f"no-data response leaked invented phrase: {phrase!r}"


def test_no_data_response_surfaces_error_reasons():
    """The user-visible reasons should mention the error class so the
    user can debug / report."""
    wr = WorkflowResult(
        classification=_classification(["Vincit"]),
        subagent_results=[
            _result(error="fabricated_no_tool_calls: agent emitted 1500 chars", tool_calls=[]),
        ],
    )
    text, _, _ = _no_data_response("vincit?", wr)
    assert "fabricated_no_tool_calls" in text


def test_no_data_response_no_company_named_query():
    """Generic query (no companies in routing) gets a generic message."""
    wr = WorkflowResult(
        classification=_classification([]),
        subagent_results=[
            _result(error="fabricated_no_tool_calls: ...", tool_calls=[]),
        ],
    )
    text, _, _ = _no_data_response("yleinen kysymys", wr)
    # Generic copy, not company-specific.
    assert "Inderes-tietokannasta" not in text
    assert "datalähteet" in text.lower() or "lähteestä" in text.lower()
