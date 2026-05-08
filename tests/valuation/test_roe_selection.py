"""Tests for the deterministic sustainable-ROE selection rule.

Coverage:
  - Trend classification (nouseva / laskeva / vakaa / insufficient)
  - Selection rule per trend
  - Edge cases: short history, all-zero, near-zero divisor
  - Real-world regression: Sampo and Qt histories from the
    20260508-1717* runs (the cases that motivated the rewrite)
  - validate_agent_roe_choice: detects the Qt failure mode
"""

from __future__ import annotations

import pytest

from inderes_agent.valuation.roe_selection import (
    compute_roe_statistics,
    select_sustainable_roe,
    validate_agent_roe_choice,
)


# ─────────────────────────────────────────────────────────────────────────────
# Trend classification
# ─────────────────────────────────────────────────────────────────────────────


def test_nouseva_when_lfy_and_3y_above_5y() -> None:
    # Steady ramp: 0.10, 0.12, 0.14, 0.16, 0.18
    stats = compute_roe_statistics([0.10, 0.12, 0.14, 0.16, 0.18])
    assert stats.trend_label == "nouseva"
    assert stats.lfy == pytest.approx(0.18)
    assert stats.p5y_median == pytest.approx(0.14)
    assert stats.p3y_median == pytest.approx(0.16)


def test_laskeva_when_lfy_and_3y_below_5y() -> None:
    # Steady decline: 0.20, 0.18, 0.16, 0.14, 0.12
    stats = compute_roe_statistics([0.20, 0.18, 0.16, 0.14, 0.12])
    assert stats.trend_label == "laskeva"
    assert stats.p5y_median == pytest.approx(0.16)
    assert stats.p3y_median == pytest.approx(0.14)


def test_vakaa_when_within_10pct_band() -> None:
    stats = compute_roe_statistics([0.15, 0.14, 0.16, 0.15, 0.14])
    assert stats.trend_label == "vakaa"


def test_insufficient_history_under_3_years() -> None:
    stats = compute_roe_statistics([0.15, 0.14])
    assert stats.trend_label == "insufficient_history"
    assert stats.p3y_median is None
    assert stats.p5y_median is None
    assert stats.trend_weighted is None


def test_empty_history_returns_all_none() -> None:
    stats = compute_roe_statistics([])
    assert stats.trend_label == "insufficient_history"
    assert stats.lfy is None
    assert stats.n_years_available == 0


# ─────────────────────────────────────────────────────────────────────────────
# Selection rule per trend
# ─────────────────────────────────────────────────────────────────────────────


def test_nouseva_picks_5y_median_not_lfy_or_trend() -> None:
    """Nouseva trend → don't get excited, pick 5y median."""
    history = [0.10, 0.12, 0.14, 0.16, 0.18]
    stats = compute_roe_statistics(history)
    roe, version = select_sustainable_roe(stats)
    assert version == "5y_median"
    assert roe == pytest.approx(0.14)
    # Sanity: this is LOWER than LFY (0.18) and trend_weighted (~0.166)
    assert roe < stats.lfy
    assert roe < stats.trend_weighted


def test_laskeva_picks_lower_of_3y_median_and_trend_weighted() -> None:
    """Laskeva → recognize new regime, pick the lower."""
    # 0.30, 0.25, 0.20, 0.15, 0.10
    # 3y_median = 0.15, trend_weighted = 0.4*0.10 + 0.35*0.15 + 0.25*0.20 = 0.1425
    history = [0.30, 0.25, 0.20, 0.15, 0.10]
    stats = compute_roe_statistics(history)
    assert stats.trend_label == "laskeva"
    roe, version = select_sustainable_roe(stats)
    assert version == "min_3y_trend"
    assert roe == pytest.approx(min(0.15, 0.1425), abs=1e-6)


def test_vakaa_picks_5y_median() -> None:
    """Vakaa → robust median across full window."""
    history = [0.15, 0.14, 0.16, 0.15, 0.14]
    stats = compute_roe_statistics(history)
    roe, version = select_sustainable_roe(stats)
    assert version == "5y_median"
    assert roe == pytest.approx(0.15)


def test_insufficient_history_picks_lfy_with_warning_label() -> None:
    history = [0.15, 0.14]
    stats = compute_roe_statistics(history)
    roe, version = select_sustainable_roe(stats)
    assert version == "lfy"
    assert roe == pytest.approx(0.14)


# ─────────────────────────────────────────────────────────────────────────────
# Real-world regression: Sampo + Qt cases that motivated this rewrite
# ─────────────────────────────────────────────────────────────────────────────


def test_qt_group_real_history_picks_conservative() -> None:
    """Qt's case from run 20260508-171901-666.

    Five-year ROE history (oldest → newest from get-fundamentals):
      2021: 0.5475, 2022: 0.4078, 2023: 0.2353, 2024: 0.1810, 2025: 0.1639

    Trend: clearly laskeva — 2025's 16.4% is far below the 2021 peak.

    The agent in the original run picked trend_weighted=0.366, which was
    WRONG (well above 3y_median). The new rule must pick the conservative
    one — somewhere in the 0.18–0.22 range.
    """
    history = [0.5475, 0.4078, 0.2353, 0.1810, 0.1639]
    stats = compute_roe_statistics(history)
    assert stats.trend_label == "laskeva"

    roe, version = select_sustainable_roe(stats)
    # 3y_median over [0.2353, 0.181, 0.1639] = 0.181
    # trend_weighted = 0.4*0.1639 + 0.35*0.1810 + 0.25*0.2353 = 0.18794...
    # min = 0.181 → 3y_median wins
    assert version == "min_3y_trend"
    assert 0.18 <= roe <= 0.19, f"expected ~0.18 (conservative), got {roe}"
    # Crucial: must be MUCH lower than the agent's original pick (0.366)
    assert roe < 0.20


def test_sampo_real_history_with_2020_anomaly() -> None:
    """Sampo's case from run 20260508-171706-948.

    Seven-year history including a 2020 anomaly (vakuutusyhtiöityminen):
      2019: NULL → drop
      2020: 0.0033 (transition year, not representative)
      2021: 0.2122, 2022: 0.1881, 2023: 0.1567, 2024: 0.1751, 2025: 0.2636

    Note: median is robust to the 2020 outlier; mean would be distorted.
    """
    # Drop 2019 (None) and 2020 (anomaly handled by median naturally).
    # The agent would pass us 2021-2025 (5 years).
    history = [0.2122, 0.1881, 0.1567, 0.1751, 0.2636]
    stats = compute_roe_statistics(history)
    # 3y_avg = (0.1567+0.1751+0.2636)/3 = 0.1985
    # 5y_avg = 0.1991
    # delta = (0.1985-0.1991)/0.1991 = -0.003 → vakaa
    assert stats.trend_label == "vakaa"

    roe, version = select_sustainable_roe(stats)
    assert version == "5y_median"
    # Median of [0.1881, 0.2122, 0.1751, 0.1567, 0.2636] sorted is 0.1881
    assert roe == pytest.approx(0.1881, abs=0.001)


def test_sampo_with_2020_anomaly_in_the_window() -> None:
    """If the agent passes the 2020 anomaly through, median still saves us."""
    # Includes 2020 0.33% anomaly
    history = [0.0033, 0.2122, 0.1881, 0.1567, 0.1751]
    stats = compute_roe_statistics(history)
    # Median of [0.0033, 0.2122, 0.1881, 0.1567, 0.1751] sorted = 0.1751
    # The 0.33% outlier doesn't move the median!
    assert stats.p5y_median == pytest.approx(0.1751, abs=0.001)
    # Mean would be (0.0033+0.2122+0.1881+0.1567+0.1751)/5 = 0.1471
    assert stats.p5y_avg == pytest.approx(0.1471, abs=0.001)
    # Demonstrates median's robustness: 0.18 vs 0.15 is meaningfully different.


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────


def test_validator_accepts_correct_choice() -> None:
    history = [0.15, 0.14, 0.16, 0.15, 0.14]
    stats = compute_roe_statistics(history)
    expected_roe, expected_version = select_sustainable_roe(stats)
    ok, msg = validate_agent_roe_choice(expected_roe, expected_version, stats)
    assert ok is True
    assert msg == "ok"


def test_validator_rejects_qt_style_failure() -> None:
    """The exact failure mode that motivated this rewrite — agent picked
    trend_weighted on a laskeva trend when it should have picked min."""
    history = [0.5475, 0.4078, 0.2353, 0.1810, 0.1639]
    stats = compute_roe_statistics(history)
    # Agent picked trend_weighted=0.366 (which would be the OLD pre-1819-bugfix
    # weighted average, but the actual Qt case shows what happens regardless).
    ok, msg = validate_agent_roe_choice(0.366, "trend_weighted", stats)
    assert ok is False
    assert "0.366" in msg or "0.3660" in msg
    assert "laskeva" in msg
    assert "min_3y_trend" in msg or "0.18" in msg


def test_validator_tolerates_rounding() -> None:
    history = [0.15, 0.14, 0.16, 0.15, 0.14]
    stats = compute_roe_statistics(history)
    expected_roe, expected_version = select_sustainable_roe(stats)
    # Agent rounds to 4dp; tolerance 0.001 should still pass
    rounded = round(expected_roe, 4)
    ok, _ = validate_agent_roe_choice(rounded, expected_version, stats)
    assert ok is True


def test_validator_rejects_non_finite() -> None:
    history = [0.15, 0.14, 0.16, 0.15, 0.14]
    stats = compute_roe_statistics(history)
    ok, msg = validate_agent_roe_choice(float("nan"), "5y_median", stats)
    assert ok is False
    assert "not finite" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Median robustness — the core property we're after
# ─────────────────────────────────────────────────────────────────────────────


def test_median_ignores_one_outlier() -> None:
    """5-year window with one wild outlier — median doesn't notice."""
    normal = [0.15, 0.14, 0.16, 0.15, 0.14]
    with_outlier = [0.15, 0.14, 0.50, 0.15, 0.14]
    s_normal = compute_roe_statistics(normal)
    s_outlier = compute_roe_statistics(with_outlier)
    # Median should be unchanged
    assert s_normal.p5y_median == s_outlier.p5y_median == pytest.approx(0.15)
    # Mean differs significantly
    assert abs(s_outlier.p5y_avg - s_normal.p5y_avg) > 0.05


def test_select_handles_degenerate_zero_history() -> None:
    """All-zero history is technically valid and shouldn't crash."""
    stats = compute_roe_statistics([0.0, 0.0, 0.0, 0.0, 0.0])
    # trend label is "vakaa" because divisor protection kicks in
    assert stats.trend_label == "vakaa"
    roe, version = select_sustainable_roe(stats)
    assert roe == 0.0
    assert version == "5y_median"
