"""Tests for ``sensitivity_grid()`` — the 2D fair-value sweep.

The single-point engine math is already covered by ``test_engine.py`` and
``test_excel_parity.py`` (~70 tests). This suite covers only what's new:
default sweep ranges, axis selection, degenerate-cell handling (k ≤ g),
and the highlight-position computation.
"""

from __future__ import annotations

import pytest

from inderes_agent.valuation.engine import (
    SensitivityGrid,
    sensitivity_grid,
    value_stock,
)

# ─────────────────────────────────────────────────────────────────────────────
# Default-range grid: ROE × k (the most common analyst question)
# ─────────────────────────────────────────────────────────────────────────────


def test_default_grid_is_5_by_5():
    """Default sweep produces 5 ticks per axis — analyst's "show me a small
    band" mental model. Smaller would lose nuance; larger would clutter."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    assert len(grid.x_values) == 5
    assert len(grid.y_values) == 5
    assert len(grid.values) == 5
    assert all(len(row) == 5 for row in grid.values)


def test_default_grid_axes_are_roe_and_k():
    """Defaults match the headline analyst question: ROE × k. The third
    Gordon input (g) is held at the analyst's central scenario."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    assert grid.y_axis == "roe"
    assert grid.x_axis == "k"
    assert "g" in grid.fixed
    assert grid.fixed["g"] == 0.04
    assert grid.fixed["bvps"] == 8.25


def test_default_range_centres_on_base():
    """Default sweep is symmetric around the base value. The base should
    appear at (or very close to) the centre tick of each axis."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    # ROE centre: 0.25 ± 5pp = 0.20..0.30, with the middle tick at 0.25
    assert grid.y_values[2] == pytest.approx(0.25, abs=0.001)
    # k centre: 0.10 ± 2pp = 0.08..0.12
    assert grid.x_values[2] == pytest.approx(0.10, abs=0.001)


def test_default_range_widths_match_axis_sensitivity():
    """Axis widths are tuned to each variable's analytical range:
    ROE ±5pp (the band where most quality-company estimates land),
    k ±2pp (the realistic cost-of-equity dispersion), g ±1pp
    (long-run growth is the most stable input)."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.05, price=19.39,
        y_axis="g", x_axis="k",
    )
    # k sweep should span ±2pp = 4pp total
    assert grid.x_values[-1] - grid.x_values[0] == pytest.approx(0.04, abs=0.0001)
    # g sweep should span ±1pp = 2pp total
    assert grid.y_values[-1] - grid.y_values[0] == pytest.approx(0.02, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# Base point and highlight position
# ─────────────────────────────────────────────────────────────────────────────


def test_base_fair_value_matches_single_point_engine():
    """The grid's ``base_fair_value`` MUST equal what ``value_stock``
    returns for the same inputs — otherwise the heatmap would highlight
    a different number from what the rest of the valuation report
    shows. This was the trap with naively reading-back the centre cell."""
    base_inputs = dict(bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39)
    grid = sensitivity_grid(**base_inputs)
    expected = value_stock(**base_inputs).fair_value
    assert grid.base_fair_value == pytest.approx(expected, rel=1e-9)


def test_base_x_and_base_y_match_inputs():
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    assert grid.base_x == 0.10  # k
    assert grid.base_y == 0.25  # roe


# ─────────────────────────────────────────────────────────────────────────────
# Cell math sanity
# ─────────────────────────────────────────────────────────────────────────────


def test_cell_values_match_single_point_engine():
    """Spot-check: every cell must equal ``value_stock(...).fair_value``
    with the same inputs — the grid is just a sweep wrapper, not a
    re-implementation of the math."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    for i, y in enumerate(grid.y_values):
        for j, x in enumerate(grid.x_values):
            cell = grid.values[i][j]
            if cell is None:
                continue  # degenerate, skip
            inputs = {"roe": 0.25, "k": 0.10, "g": 0.04}
            inputs[grid.y_axis] = y
            inputs[grid.x_axis] = x
            expected = value_stock(bvps=8.25, price=19.39, **inputs).fair_value
            assert cell == pytest.approx(expected, rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Degenerate cells: k ≤ g must return None, not crash
# ─────────────────────────────────────────────────────────────────────────────


def test_degenerate_cells_marked_none_not_raised():
    """When sweeping k near or below g, Gordon's formula degenerates.
    The grid should mark those cells ``None`` so the renderer can shade
    them as undefined, NOT raise ValueError and lose the rest of the
    grid."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
        y_axis="g", x_axis="k",
        x_values=(0.03, 0.04, 0.05, 0.08, 0.12),  # 0.03 < g=0.04 → degenerate
        y_values=(0.02, 0.04, 0.06, 0.08, 0.10),
    )
    # At least one cell should be None (where k ≤ g for that combination)
    flat = [v for row in grid.values for v in row]
    assert any(v is None for v in flat), \
        "expected at least one undefined cell when k sweep crosses g range"
    # But the bulk of the grid should still have computed values
    defined = [v for v in flat if v is not None]
    assert len(defined) >= 10, \
        f"expected most cells to compute fine; only {len(defined)} of {len(flat)} did"


# ─────────────────────────────────────────────────────────────────────────────
# Axis validation
# ─────────────────────────────────────────────────────────────────────────────


def test_same_axis_for_x_and_y_raises():
    """Both axes pointing at the same variable would give a degenerate
    1D sweep mislabeled as 2D. Fail loud."""
    with pytest.raises(ValueError, match="must differ"):
        sensitivity_grid(
            bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
            x_axis="roe", y_axis="roe",
        )


def test_invalid_axis_name_raises():
    with pytest.raises(ValueError, match="axis names must be"):
        sensitivity_grid(
            bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
            x_axis="bvps",  # type: ignore[arg-type]
            y_axis="roe",
        )


# ─────────────────────────────────────────────────────────────────────────────
# All three axis combinations should work
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "y_axis,x_axis,fixed_axis",
    [
        ("roe", "k", "g"),  # the headline question
        ("g", "k", "roe"),  # "growth vs cost-of-equity, ROE fixed"
        ("roe", "g", "k"),  # "ROE vs growth, k fixed"
    ],
)
def test_all_axis_combinations_produce_valid_grids(y_axis, x_axis, fixed_axis):
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
        y_axis=y_axis, x_axis=x_axis,
    )
    assert grid.y_axis == y_axis
    assert grid.x_axis == x_axis
    assert fixed_axis in grid.fixed
    # At least the centre cell should have a value (it's the base point)
    centre = grid.values[2][2]
    assert centre is not None
    assert centre > 0


# ─────────────────────────────────────────────────────────────────────────────
# Custom ranges
# ─────────────────────────────────────────────────────────────────────────────


def test_custom_ranges_override_defaults():
    """Caller-supplied ranges should be used verbatim; the engine must
    not silently 'helpfully' re-center them around the base."""
    custom_x = (0.07, 0.08, 0.09, 0.10, 0.11)
    custom_y = (0.10, 0.15, 0.20, 0.25, 0.30)
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
        x_values=custom_x, y_values=custom_y,
    )
    assert grid.x_values == custom_x
    assert grid.y_values == custom_y


def test_custom_ranges_with_more_than_5_ticks():
    """Sweep doesn't have to be 5×5 — allow finer-grained heatmaps when
    the caller wants more resolution (e.g. for screenshots)."""
    custom_x = tuple(0.06 + i * 0.005 for i in range(11))  # 11 ticks
    custom_y = tuple(0.15 + i * 0.02 for i in range(8))  # 8 ticks
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
        x_values=custom_x, y_values=custom_y,
    )
    assert len(grid.x_values) == 11
    assert len(grid.y_values) == 8
    assert len(grid.values) == 8
    assert all(len(row) == 11 for row in grid.values)


# ─────────────────────────────────────────────────────────────────────────────
# Qt Group-style end-to-end: replicate the ChatGPT example from the user's brief
# ─────────────────────────────────────────────────────────────────────────────


def test_qt_group_style_grid_replicates_chatgpt_output():
    """ChatGPT produced a Qt Group sensitivity table with BVPS=8.25,
    ROE=25%, k=10%, g=4%. The corner-cells of that table should match
    our engine output exactly (since both are computing the same Gordon
    formula). This is the 'we match the public benchmark' regression."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
        y_axis="roe", x_axis="k",
        # Match ChatGPT's exact sweep ticks for direct comparison
        y_values=(0.15, 0.20, 0.25, 0.30, 0.35),
        x_values=(0.08, 0.09, 0.10, 0.11, 0.12),
    )
    # ChatGPT's table reports these corner values for ROE=15%, k=8% etc.
    # Engine output should match to within 0.1 € (rounding tolerance).
    #   ROE=25%, k=10%: 28.875 — ChatGPT said "28,9"
    #   ROE=15%, k=8%:  22.6875 — ChatGPT said "22,7"
    #   ROE=35%, k=12%: ~31.96875 — ChatGPT said "32,0"
    centre = grid.values[2][2]
    assert centre == pytest.approx(28.875, abs=0.05)

    top_left = grid.values[0][0]  # ROE=15%, k=8%
    assert top_left == pytest.approx(22.6875, abs=0.05)

    bottom_right = grid.values[-1][-1]  # ROE=35%, k=12%
    assert bottom_right == pytest.approx(31.96875, abs=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass shape
# ─────────────────────────────────────────────────────────────────────────────


def test_grid_is_frozen_dataclass():
    """Engine output dataclasses are frozen everywhere — prevents callers
    from accidentally mutating intermediate state and getting confused."""
    grid = sensitivity_grid(
        bvps=8.25, roe=0.25, k=0.10, g=0.04, price=19.39,
    )
    assert isinstance(grid, SensitivityGrid)
    with pytest.raises((AttributeError, Exception)):
        grid.values = ()  # type: ignore[misc]
