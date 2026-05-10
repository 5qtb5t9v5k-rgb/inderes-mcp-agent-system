"""Tests for the hard-limits module (orchestration/limits.py).

OWASP Agentic Top 10 #T1 — excessive agency. The limits module ships
the hard caps that the loose subagent contract (prompts + heuristics)
cannot enforce on its own. Empirical baselines came from the Tier 0
SQLite index over 183 historical runs (mean 21s, p95 30s, max 308s
for duration; mean 3.3, p95 6, max 10 for tool calls per subagent).

This file unit-tests the limits primitives in isolation. End-to-end
tests covering `run_workflow` + a real subagent with a forced timeout
would need an async pytest setup the project doesn't currently have;
once Reflexion ships and brings asyncio test fixtures with it, those
should land here too.
"""

from __future__ import annotations

import pytest

from inderes_agent.orchestration.limits import (
    DEFAULT_MAX_COST_USD,
    DEFAULT_MAX_REFLEXION_ITERATIONS,
    DEFAULT_MAX_SUBAGENT_DURATION_S,
    DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT,
    DEFAULT_MAX_TOTAL_TOOL_CALLS,
    DEFAULT_MAX_WORKFLOW_DURATION_S,
    BudgetExceededError,
    CancelToken,
    RunBudget,
    check_tool_call_caps,
)


# ---------------------------------------------------------------------------
# RunBudget defaults
# ---------------------------------------------------------------------------


def test_run_budget_defaults_match_module_constants():
    """Lock the canonical defaults — change-here-not-there guard.
    If someone bumps DEFAULT_MAX_SUBAGENT_DURATION_S they must also
    bump this test, which forces a moment of "is this the value I
    actually want?" instead of silent drift."""
    b = RunBudget()
    assert b.max_subagent_duration_s == DEFAULT_MAX_SUBAGENT_DURATION_S == 90
    assert b.max_workflow_duration_s == DEFAULT_MAX_WORKFLOW_DURATION_S == 180
    assert b.max_tool_calls_per_subagent == DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT == 12
    assert b.max_total_tool_calls == DEFAULT_MAX_TOTAL_TOOL_CALLS == 40
    assert b.max_reflexion_iterations == DEFAULT_MAX_REFLEXION_ITERATIONS == 1
    assert b.max_cost_usd == DEFAULT_MAX_COST_USD == pytest.approx(0.50)


def test_run_budget_override_per_call_site():
    """A nightly-eval caller may want tighter caps; an interactive UI
    call may want generous. Both override the same fields."""
    nightly = RunBudget(
        max_workflow_duration_s=120,
        max_reflexion_iterations=0,
        max_cost_usd=0.20,
    )
    assert nightly.max_workflow_duration_s == 120
    assert nightly.max_reflexion_iterations == 0
    assert nightly.max_cost_usd == 0.20
    # Untouched fields keep their defaults
    assert nightly.max_tool_calls_per_subagent == DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT


# ---------------------------------------------------------------------------
# BudgetExceededError
# ---------------------------------------------------------------------------


def test_budget_exceeded_error_carries_kind_and_reason():
    """The structured `kind` lets the UI render different banners per
    cap (timeout vs cost vs cancel). Both attributes preserved."""
    exc = BudgetExceededError(
        BudgetExceededError.KIND_TIMEOUT_SUBAGENT,
        "Subagent foo exceeded 90s",
    )
    assert exc.kind == "timeout_subagent"
    assert exc.reason == "Subagent foo exceeded 90s"
    # str() returns the reason (str.args[0])
    assert str(exc) == "Subagent foo exceeded 90s"


def test_budget_exceeded_error_kind_constants():
    """Pin the kind constants so a typo in caller code (e.g.
    `if exc.kind == "timeout"`) fails the test, not silently miss
    the branch."""
    assert BudgetExceededError.KIND_TIMEOUT_SUBAGENT == "timeout_subagent"
    assert BudgetExceededError.KIND_TIMEOUT_WORKFLOW == "timeout_workflow"
    assert BudgetExceededError.KIND_TOOL_CALLS_SUBAGENT == "tool_calls_subagent"
    assert BudgetExceededError.KIND_TOOL_CALLS_TOTAL == "tool_calls_total"
    assert BudgetExceededError.KIND_COST == "cost"
    assert BudgetExceededError.KIND_REFLEXION_DEPTH == "reflexion_depth"
    assert BudgetExceededError.KIND_USER_CANCELLED == "user_cancelled"


# ---------------------------------------------------------------------------
# CancelToken
# ---------------------------------------------------------------------------


def test_cancel_token_default_does_not_raise():
    """Fresh token: no cancellation signalled, .check() is a no-op."""
    tok = CancelToken()
    tok.check()  # should not raise


def test_cancel_token_raises_when_flagged():
    """Once .cancelled = True, .check() raises with the structured
    KIND_USER_CANCELLED so callers can distinguish from a timeout."""
    tok = CancelToken()
    tok.cancelled = True
    with pytest.raises(BudgetExceededError) as exc_info:
        tok.check()
    assert exc_info.value.kind == BudgetExceededError.KIND_USER_CANCELLED


def test_cancel_token_independent_instances():
    """Two tokens don't share state — important when multiple runs
    are in flight (e.g. nightly eval + concurrent UI)."""
    a = CancelToken()
    b = CancelToken()
    a.cancelled = True
    a_raised = False
    try:
        a.check()
    except BudgetExceededError:
        a_raised = True
    assert a_raised
    b.check()  # independent — should not raise


# ---------------------------------------------------------------------------
# check_tool_call_caps — post-hoc warnings
# ---------------------------------------------------------------------------


def test_tool_call_caps_silent_when_under_budget():
    """Counts within budget → no warnings."""
    budget = RunBudget()
    warnings = check_tool_call_caps(
        budget=budget,
        per_subagent_counts={"quant-Sampo": 5, "research-Sampo": 8},
        total_count=13,
    )
    assert warnings == []


def test_tool_call_caps_per_subagent_warning():
    """A subagent exceeding its cap → one warning per excess agent.
    Doesn't raise — data is already fetched, run still has value."""
    budget = RunBudget(max_tool_calls_per_subagent=10)
    warnings = check_tool_call_caps(
        budget=budget,
        per_subagent_counts={"quant-Sampo": 5, "research-Sampo": 15},
        total_count=20,
    )
    assert len(warnings) == 1
    assert "research-Sampo" in warnings[0]
    assert "15 tool calls" in warnings[0]
    assert "cap 10" in warnings[0]


def test_tool_call_caps_total_warning():
    """Aggregate cap — sum exceeded → standalone warning."""
    budget = RunBudget(max_total_tool_calls=20)
    warnings = check_tool_call_caps(
        budget=budget,
        per_subagent_counts={"quant-Sampo": 8, "research-Sampo": 8, "sentiment-Sampo": 9},
        total_count=25,
    )
    # Per-subagent are all under cap; only the total fires
    assert len(warnings) == 1
    assert "Run total: 25" in warnings[0]


def test_tool_call_caps_both_layers_can_fire():
    """When both per-subagent AND total exceed, both warn — the user
    sees the full picture."""
    budget = RunBudget(max_tool_calls_per_subagent=5, max_total_tool_calls=15)
    warnings = check_tool_call_caps(
        budget=budget,
        per_subagent_counts={"quant-Sampo": 8, "research-Sampo": 6, "sentiment-Sampo": 4},
        total_count=18,
    )
    assert len(warnings) == 3
    assert any("quant-Sampo" in w for w in warnings)
    assert any("research-Sampo" in w for w in warnings)
    assert any("Run total: 18" in w for w in warnings)
