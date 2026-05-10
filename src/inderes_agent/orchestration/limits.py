"""Hard limits + cancel token for the agent pipeline (OWASP Agentic T1).

Background — the system has been observed to:
  - loop a single subagent past 300 seconds when the MCP catalog miss
    triggers retries (Vincit run, 2026-05-02)
  - emit ~12 tool calls in a row when an agent over-explores
  - silently drift past sensible cost thresholds when Pro tier + plan-
    then-execute + valuation are all on simultaneously

Reflexion (BACKLOG §0 Wk 2) introduces RETRY mechanisms that compound
this risk — retry-on-weird-output without a hard cap is a classic
infinite-loop foot-gun.

This module ships the **hard caps** that the loose subagent contract
(prompts + heuristics) cannot enforce on its own. Empirical baselines
came from the Tier 0 SQLite index over 183 historical runs — see
`evals/findings_2026-05-09.md` for the percentiles.

Design notes:
  - Limits are dataclass-defaults so callers (CLI, Streamlit, future
    nightly cron) can override per-context. The Streamlit UI uses
    one set, the autonomous nightly eval might use tighter / looser
    ones.
  - Enforcement is a mix:
      * `asyncio.wait_for()` timeouts at subagent + workflow level
      * Post-hoc tool-call count check (we can't stop an agent
        mid-flight from emitting more calls; we can flag it after)
      * Cooperative cancel via CancelToken (the UI's "🛑 Pysäytä"
        button signals through this; subagents check it between
        dispatches)
  - `BudgetExceededError` is the canonical exception. Caller chooses
    whether to surface it as a user-facing error or silently fall
    back to a partial result.

The Reflexion loop (when shipped) will share the same RunBudget —
each retry counts against `max_reflexion_iterations` and the wall-
clock budget so a runaway self-correction can't escape the cap.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

# Empirical baselines from the Tier 0 SQLite index (183 real runs):
#
#   metric                    mean    p95     max     suggested_cap
#   duration_s                21.2    30      308     180
#   tool_calls_per_subagent   3.3     6       10      12
#   total_tool_calls_per_run  7.9     14      30      40
#
# Suggested caps are ~3× the observed p95 so legitimate heavy queries
# (e.g. 4-bank comparison fan-out) still pass while runaway agents get
# stopped. Tighten in autonomous-nightly mode where speed matters.

DEFAULT_MAX_SUBAGENT_DURATION_S = 90
"""Per-subagent wall-clock cap. The Vincit-style 308s loop is cut at
this threshold. Comparison fan-outs run subagents in parallel so the
total wall-clock isn't N × 90s."""

DEFAULT_MAX_WORKFLOW_DURATION_S = 180
"""Total subagent fan-out + planner + conflict + LEAD synthesis cap.
After this the user gets a "tämä kysely kesti liian kauan" error."""

DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT = 12
"""Post-hoc check: a subagent that emitted >12 tool calls likely got
stuck in a search-then-search-again loop. Flagged via the run log
even when the data eventually came back."""

DEFAULT_MAX_TOTAL_TOOL_CALLS = 40
"""Across all subagents in one run. 4-bank comparison × 3 domains =
~24 calls; 40 leaves headroom for Reflexion retries."""

DEFAULT_MAX_REFLEXION_ITERATIONS = 1
"""Per-subagent retry cap. Reflexion 1 retry is plenty — if the
output is still wrong after one self-critique pass, deeper iteration
just compounds the error."""

DEFAULT_MAX_COST_USD = 0.50
"""Total LLM cost cap per run. Pro tier + plan-then-execute + valuation
worst case: ~$0.30. Cap at $0.50 to leave Reflexion + LEAD-deep
headroom but stop a runaway from going to $5+."""


class BudgetExceededError(Exception):
    """Raised when a RunBudget hard cap fires.

    Always carries a human-readable reason in `args[0]` plus a
    structured `kind` attribute so callers can render different UI
    affordances per cap (timeout banner vs cost banner vs cancel
    confirmation).
    """

    KIND_TIMEOUT_SUBAGENT = "timeout_subagent"
    KIND_TIMEOUT_WORKFLOW = "timeout_workflow"
    KIND_TOOL_CALLS_SUBAGENT = "tool_calls_subagent"
    KIND_TOOL_CALLS_TOTAL = "tool_calls_total"
    KIND_COST = "cost"
    KIND_REFLEXION_DEPTH = "reflexion_depth"
    KIND_USER_CANCELLED = "user_cancelled"

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


@dataclass
class RunBudget:
    """Per-run hard limits.

    Defaults are calibrated from real-traffic baselines (Tier 0 SQLite
    index, 2026-05-09). Override per call site:

        # Streamlit UI — generous to allow Pro-tier + valuation
        budget = RunBudget()

        # Pro-tier subagents — Pro is 2-3× slower than Flash Lite
        budget = RunBudget.for_pro_tier()

        # Nightly eval — tighter, no Reflexion
        budget = RunBudget(
            max_workflow_duration_s=120,
            max_reflexion_iterations=0,
            max_cost_usd=0.20,
        )
    """
    max_subagent_duration_s: int = DEFAULT_MAX_SUBAGENT_DURATION_S
    max_workflow_duration_s: int = DEFAULT_MAX_WORKFLOW_DURATION_S
    max_tool_calls_per_subagent: int = DEFAULT_MAX_TOOL_CALLS_PER_SUBAGENT
    max_total_tool_calls: int = DEFAULT_MAX_TOTAL_TOOL_CALLS
    max_reflexion_iterations: int = DEFAULT_MAX_REFLEXION_ITERATIONS
    max_cost_usd: float = DEFAULT_MAX_COST_USD

    @classmethod
    def for_pro_tier(cls) -> RunBudget:
        """Loosened budget for runs where subagents use Gemini 2.5 Pro
        instead of Flash Lite. Pro is empirically 2-3× slower per
        tool-call cycle (research subagent timed out at 90s on Pro
        in run 20260510-131450-759 — same prompt completes in ~30s
        on Flash Lite). Triple the wall-clock budgets and double
        the cost cap (Pro is ~10× more expensive too).
        """
        return cls(
            max_subagent_duration_s=180,
            max_workflow_duration_s=360,
            max_cost_usd=2.00,
        )


@dataclass
class CancelToken:
    """Cooperative cancellation signal — caller flips ``cancelled``,
    long-running coroutines check it at safe points and raise
    ``BudgetExceededError(kind=KIND_USER_CANCELLED)``.

    The Streamlit UI's "🛑 Pysäytä" button writes through here. CLI
    callers can ignore the field — its default is False, no checks
    means no cancellation.
    """
    cancelled: bool = False

    def check(self) -> None:
        """Raise if the caller has signalled cancellation."""
        if self.cancelled:
            raise BudgetExceededError(
                BudgetExceededError.KIND_USER_CANCELLED,
                "User cancelled the run",
            )


# ---------------------------------------------------------------------------
# Enforcement helpers — used by workflows.py + synthesis.py
# ---------------------------------------------------------------------------


async def with_subagent_timeout(coro, *, budget: RunBudget, label: str):
    """Wrap a subagent coroutine in `asyncio.wait_for(timeout)`.

    Translates the raw `TimeoutError` into a `BudgetExceededError` with
    the structured `kind=KIND_TIMEOUT_SUBAGENT` so callers can render a
    consistent error message.
    """
    try:
        return await asyncio.wait_for(coro, timeout=budget.max_subagent_duration_s)
    except TimeoutError as exc:
        raise BudgetExceededError(
            BudgetExceededError.KIND_TIMEOUT_SUBAGENT,
            f"Subagent {label!r} exceeded {budget.max_subagent_duration_s}s "
            f"wall-clock budget",
        ) from exc


def check_tool_call_caps(
    *,
    budget: RunBudget,
    per_subagent_counts: dict[str, int],
    total_count: int,
) -> list[str]:
    """Post-hoc tool-call cap check. Returns a list of human-readable
    warnings for each cap exceeded — does NOT raise, because the data
    has already been fetched and the run has value even if the agent
    over-shopped.

    The warnings are surfaced to the user via the run log + an info
    banner so they can see "agent X made 15 tool calls (cap 12)" and
    decide whether to retune the prompt.
    """
    warnings: list[str] = []
    for label, count in per_subagent_counts.items():
        if count > budget.max_tool_calls_per_subagent:
            warnings.append(
                f"Subagent {label!r} made {count} tool calls "
                f"(cap {budget.max_tool_calls_per_subagent}) — "
                f"prompt may be sending the agent in circles"
            )
    if total_count > budget.max_total_tool_calls:
        warnings.append(
            f"Run total: {total_count} tool calls "
            f"(cap {budget.max_total_tool_calls}) — consider "
            f"narrowing the question or fewer companies in scope"
        )
    return warnings
