"""Sustainable-ROE selection — deterministic central-tendency rule.

The valuation engine needs **one** ROE number to compute fair value. The
question is which year/window represents the company's *sustainable*
return-on-equity — the rate it can plausibly maintain, not the highest it's
ever hit nor the lowest one-off dip.

This module is the **single source of truth** for that decision. It's
called from two places:

  1. ``valuation.parser.parse`` — to validate the agent's choice against
     the rule. If the agent picked something the rule wouldn't, parsing
     fails with a ``ValuationParseError`` carrying both numbers.
  2. ``agents/prompts/valuation.md`` — the prompt documents this exact
     logic so the agent has a target it can actually hit, and the
     code-vs-prompt drift stays a real bug rather than silently accumulating.

Design philosophy:

  - **Median dominates the mean** for "typical year" thinking. Mean is
    distorted by one-off years (Sampo 2020 ROE 0.3% from accounting
    transition); median ignores that and reports the middle of the pack.
  - **Trend matters but doesn't overrule.** Rising profitability ≠ "we
    can sustain the new peak"; falling profitability ≠ "panic and use
    the trough". The rule respects trend by *which* central tendency
    to use, not by chasing extremes.
  - **Less than 3y of history → use LFY + warn.** No way to compute
    a reliable trend or median from one or two points; surface the
    uncertainty rather than hide it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# What the agent (and run-log) calls each version. Kept narrow so parser
# validation has a tight allowlist.
RoeVersion = Literal[
    "lfy",            # last-fully-reported-year — used only for short history
    "3y_median",      # median of LFY, LFY-1, LFY-2
    "5y_median",      # median of LFY..LFY-4 — preferred default
    "trend_weighted", # 0.4*LFY + 0.35*LFY-1 + 0.25*LFY-2
    "min_3y_trend",   # min(3y_median, trend_weighted) — used when laskeva
]

TrendLabel = Literal["nouseva", "laskeva", "vakaa", "insufficient_history"]


@dataclass(frozen=True)
class RoeStatistics:
    """All the pre-computed central-tendencies for a ROE history.

    The agent can include any/all of these in its output — but the
    deterministic ``select_sustainable_roe`` function only consults the
    fields the rule actually needs.
    """
    lfy: float | None
    p3y_avg: float | None
    p3y_median: float | None
    p5y_avg: float | None
    p5y_median: float | None
    trend_weighted: float | None
    trend_label: TrendLabel
    n_years_available: int


def _median(xs: list[float]) -> float:
    """Pure-Python median. Handles empty list explicitly so callers can't
    accidentally consume a NaN downstream."""
    if not xs:
        raise ValueError("cannot take median of empty list")
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def compute_roe_statistics(history: list[float]) -> RoeStatistics:
    """Reduce a chronological ROE history (oldest → newest) to summary stats.

    `history` must be a list of floats, oldest first (LFY-4, LFY-3, …, LFY).
    Each entry is a ROE as decimal (e.g. 0.149 for 14.9%).

    Empty / very short histories return statistics with as many fields
    populated as possible and a ``trend_label`` of ``insufficient_history``.

    Trend classification (when ≥ 3y available):
      - **nouseva**: 3y_avg > 5y_avg by > +10% AND LFY > 3y_avg
      - **laskeva**: 3y_avg < 5y_avg by < -10% AND LFY < 3y_avg
      - **vakaa**: muut

    Edge case: if 5y_avg is undefined (only 3y available), use 3y_avg
    in its place for the comparison ratio.
    """
    if not history:
        return RoeStatistics(
            lfy=None, p3y_avg=None, p3y_median=None,
            p5y_avg=None, p5y_median=None,
            trend_weighted=None,
            trend_label="insufficient_history",
            n_years_available=0,
        )

    n = len(history)
    lfy = history[-1]

    last3 = history[-3:] if n >= 3 else None
    last5 = history[-5:] if n >= 5 else None

    p3y_avg = sum(last3) / 3 if last3 else None
    p3y_median = _median(last3) if last3 else None
    p5y_avg = sum(last5) / 5 if last5 else None
    p5y_median = _median(last5) if last5 else None

    # Trend-weighted: 0.4*LFY + 0.35*LFY-1 + 0.25*LFY-2 (only valid for ≥ 3y)
    trend_weighted: float | None = None
    if n >= 3:
        trend_weighted = (
            0.4 * history[-1]
            + 0.35 * history[-2]
            + 0.25 * history[-3]
        )

    # Trend label
    if n < 3:
        trend_label: TrendLabel = "insufficient_history"
    else:
        # Use 5y_avg if available, fall back to 3y_avg
        long_term = p5y_avg if p5y_avg is not None else p3y_avg
        assert long_term is not None  # guaranteed by n >= 3 branch
        # Avoid division by zero in pathological cases
        if abs(long_term) < 1e-9:
            trend_label = "vakaa"
        else:
            delta = (p3y_avg - long_term) / abs(long_term)
            # Severe decline (≥20 % drop in 3y avg vs long-term) is
            # always structural — classify as laskeva even if the most
            # recent year ticked up slightly within the depressed
            # window. Surfaced by UPM-Kymmene 2026-05-09:
            #   ROE 2021–25 = [12.7, 13.1, 3.3, 3.9, 4.5] %
            #   3y_avg = 3.9 %, 5y_avg = 7.5 %, delta = -48 %
            #   But LFY (4.5 %) > 3y_avg (3.9 %) so the original
            #   `delta < -0.10 AND lfy < p3y_avg` failed → vakaa →
            #   the rule prescribed 5y_median=4.5 %, mixing two
            #   regimes and rejecting the agent's conservative
            #   3y_median=3.9 % choice. Severe-decline branch fixes it.
            if delta < -0.20:
                trend_label = "laskeva"
            elif delta < -0.10 and lfy < long_term:
                # Moderate decline AND LFY below the long-term level —
                # company is in a sustained dip. (Was `lfy < p3y_avg`
                # which was even tighter; `lfy < long_term` is the
                # symmetric semantic to "below historical norm".)
                trend_label = "laskeva"
            elif delta > 0.20:
                # Symmetric: severe rise is structural, even if LFY
                # ticked down within the elevated window.
                trend_label = "nouseva"
            elif delta > 0.10 and lfy > long_term:
                trend_label = "nouseva"
            else:
                trend_label = "vakaa"

    return RoeStatistics(
        lfy=lfy,
        p3y_avg=p3y_avg,
        p3y_median=p3y_median,
        p5y_avg=p5y_avg,
        p5y_median=p5y_median,
        trend_weighted=trend_weighted,
        trend_label=trend_label,
        n_years_available=n,
    )


def select_sustainable_roe(stats: RoeStatistics) -> tuple[float, RoeVersion]:
    """Apply the kestävä-taso decision rule to pre-computed statistics.

    Returns ``(roe, version_label)`` where ``version_label`` matches the
    agent's allowed roe_version values.

    Rules — pick the central tendency that best represents what the
    company can **sustainably** earn on its equity:

      - **insufficient_history (<3y)** → ``lfy``
        We have nothing better; the agent must add a warning.
      - **nouseva (rising profitability)** → ``5y_median``
        Don't get carried away by a hot recent year. Median across the
        full window dampens recency bias and reports the typical year.
      - **laskeva (falling profitability)** → ``min(3y_median, trend_weighted)``
        Recognize the new lower regime. Trend-weighted gives more weight
        to recent years; 3y_median is the typical recent year. Pick the
        lower of the two — be conservative.
      - **vakaa (stable)** → ``5y_median``
        The full-window median. Robust to single-year accounting blips.

    Fallbacks: if a required stat is None (e.g., laskeva but only 4y of
    history so trend_weighted exists but 3y_median is from the same 3
    points), use whatever IS available, in priority order. If nothing
    works, fall back to lfy.

    Raises ``ValueError`` only if even ``lfy`` is None — i.e., empty history.
    """
    if stats.lfy is None:
        raise ValueError(
            "Cannot select sustainable ROE: history is empty (lfy is None)."
        )

    if stats.trend_label == "insufficient_history":
        return stats.lfy, "lfy"

    if stats.trend_label == "nouseva":
        # Prefer 5y_median; fall back to 3y_median if 5y not available.
        if stats.p5y_median is not None:
            return stats.p5y_median, "5y_median"
        if stats.p3y_median is not None:
            return stats.p3y_median, "3y_median"
        return stats.lfy, "lfy"

    if stats.trend_label == "laskeva":
        # min(3y_median, trend_weighted) — the conservative one.
        candidates: list[tuple[float, RoeVersion]] = []
        if stats.p3y_median is not None:
            candidates.append((stats.p3y_median, "3y_median"))
        if stats.trend_weighted is not None:
            candidates.append((stats.trend_weighted, "trend_weighted"))
        if not candidates:
            return stats.lfy, "lfy"
        # Pick the lower
        chosen_value, chosen_version = min(candidates, key=lambda c: c[0])
        # If both stats are present, the canonical label is min_3y_trend
        # so the run-log shows the rule that fired, not just the winning
        # candidate. (The numeric value is the same either way.)
        if (stats.p3y_median is not None
                and stats.trend_weighted is not None):
            return chosen_value, "min_3y_trend"
        return chosen_value, chosen_version

    # vakaa
    if stats.p5y_median is not None:
        return stats.p5y_median, "5y_median"
    if stats.p3y_median is not None:
        return stats.p3y_median, "3y_median"
    return stats.lfy, "lfy"


def validate_agent_roe_choice(
    agent_roe: float,
    agent_version: str,
    stats: RoeStatistics,
    *,
    abs_tol: float = 0.005,
    rel_tol: float = 0.01,
) -> tuple[bool, str]:
    """Check whether the agent's roe_used + roe_version match the rule.

    Returns ``(is_valid, message)``. When invalid, ``message`` is a
    human-readable explanation of what the rule expected and what it got.

    Tolerance is ``max(abs_tol, |expected_roe| × rel_tol)``:
      - ``abs_tol = 0.005`` (0.5pp) absorbs 2-decimal display rounding.
        The agent often emits ROE as 0.28 when the rule's true value is
        0.2837 — that's a 0.4pp display-rounding gap, not a real rule
        violation. Caught the Qt run 20260508-190141-372 false positive.
      - ``rel_tol = 0.01`` (1%) gives proportionally more room for
        higher ROEs while keeping low-ROE checks tight.

    Real rule violations (e.g., agent picks trend_weighted = 0.366 on a
    laskeva trend when min_3y_trend = 0.18 is required — a 0.18 gap)
    still fail cleanly because they exceed both tolerances by an order
    of magnitude.
    """
    expected_roe, expected_version = select_sustainable_roe(stats)

    if not math.isfinite(agent_roe):
        return False, f"agent's roe_used is not finite: {agent_roe!r}"

    tol = max(abs_tol, abs(expected_roe) * rel_tol)
    diff = abs(agent_roe - expected_roe)
    if diff > tol:
        return False, (
            f"agent picked roe_used={agent_roe:.4f} (version={agent_version!r}) "
            f"but the sustainable-ROE rule for trend_label={stats.trend_label!r} "
            f"requires {expected_roe:.4f} (version={expected_version!r}). "
            f"Tolerance was {tol:.4f}; difference was {diff:.4f}. "
            f"History stats: lfy={stats.lfy}, "
            f"3y_median={stats.p3y_median}, 5y_median={stats.p5y_median}, "
            f"trend_weighted={stats.trend_weighted}."
        )

    return True, "ok"
