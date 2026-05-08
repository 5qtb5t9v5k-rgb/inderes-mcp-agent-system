"""Unit tests for the deterministic valuation engine.

Coverage:
  - Happy path (laatuyhtiö, ROE > k)
  - Boundary cases (ROE == k, ROE just below k)
  - Mediocre case (ROE < k → kasvu tuhoaa arvoa)
  - Input validation (k <= g, negative inputs)
  - Algebraic identity FV_Gordon == EPV × GM
  - Entry levels arithmetic
  - Pure-vs-Excel output divergence at quality boundary

These run in milliseconds; no LLM, no MCP, no I/O.
"""

from __future__ import annotations

import math

import pytest

from inderes_agent.valuation import value_stock
from inderes_agent.valuation.engine import Valuation


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — laatuyhtiö
# ─────────────────────────────────────────────────────────────────────────────


def test_alma_media_laatuyhtio() -> None:
    """ALMA Media: ROE 19% > k 9% → kasvu lisää arvoa, FV > EPV."""
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)

    assert v.quality == "laatu"
    assert v.fair_value == pytest.approx(9.38, abs=0.01)
    assert v.fv_gordon == pytest.approx(9.38, abs=0.01)
    assert v.epv_pure == pytest.approx(5.66, abs=0.01)
    assert v.growth_value_pure == pytest.approx(3.72, abs=0.01)
    assert v.gm == pytest.approx(1.66, abs=0.01)

    # Excel-compatible outputs equal pure outputs for laatuyhtiö
    assert v.epv_excel == pytest.approx(v.epv_pure, abs=1e-9)
    assert v.gv_excel == pytest.approx(v.growth_value_pure, abs=1e-9)

    # Market comparison — yli_ali_pct uses fair_value as denominator
    # (matches Excel I column convention: (price-fv)/fv).
    assert v.pb == pytest.approx(8.20 / 2.68, abs=1e-6)
    assert v.yli_ali_pct == pytest.approx((8.20 - 9.38) / 9.38 * 100, abs=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# Mediocre case — ROE < k
# ─────────────────────────────────────────────────────────────────────────────


def test_aktia_keskinkertainen() -> None:
    """AKTIA: ROE 9.1% < k 10% → kasvu tuhoaa arvoa, FV_Gordon < EPV pure."""
    v = value_stock(bvps=10.17, roe=0.091, k=0.10, g=0.05, price=9.58)

    assert v.quality == "tuhoutuva"
    # Pure values
    assert v.fv_gordon == pytest.approx(8.34, abs=0.01)
    assert v.epv_pure == pytest.approx(9.25, abs=0.01)
    # Growth value is negative when ROE < k (destructive growth)
    assert v.growth_value_pure < 0
    assert v.gm < 1.0  # Greenwald: <1 means growth destroys value

    # Excel-compatible: EPV column "rebased" to fv_gordon, GV zeroed
    assert v.epv_excel == pytest.approx(8.34, abs=0.01)
    assert v.gv_excel == pytest.approx(0.0, abs=1e-9)

    # Fair value is fv_gordon (the lower, more conservative number)
    assert v.fair_value == pytest.approx(8.34, abs=0.01)


def test_keskinkertainen_when_roe_equals_k_within_band() -> None:
    """ROE within ±2% of k → 'keskinkertainen' (not 'laatu' or 'tuhoutuva')."""
    # ROE 0.098, k 0.10 → ROE/k = 0.98 → within band
    v = value_stock(bvps=10.0, roe=0.098, k=0.10, g=0.04, price=10.0)
    assert v.quality == "keskinkertainen"
    # Excel-compatible: still rebased like tuhoutuva
    assert v.gv_excel == pytest.approx(0.0, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Algebraic identity — FV_Gordon == EPV × GM
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bvps,roe,k,g", [
    (5.0, 0.20, 0.09, 0.05),
    (12.0, 0.15, 0.10, 0.04),
    (3.0, 0.30, 0.08, 0.06),
    (8.0, 0.085, 0.09, 0.04),  # close-to-mediocre
])
def test_fv_gordon_equals_epv_times_gm(bvps: float, roe: float, k: float, g: float) -> None:
    """The whole point of Greenwald's TV decomposition: TV = EPV × GM."""
    v = value_stock(bvps=bvps, roe=roe, k=k, g=g, price=10.0)
    reconstructed = v.epv_pure * v.gm
    assert reconstructed == pytest.approx(v.fv_gordon, rel=1e-9), (
        f"GM decomposition broken: epv_pure × gm = {reconstructed}, "
        f"but fv_gordon = {v.fv_gordon}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Input validation — fail loud for bad inputs
# ─────────────────────────────────────────────────────────────────────────────


def test_k_must_exceed_g() -> None:
    with pytest.raises(ValueError, match="k.*must be > g"):
        value_stock(bvps=10.0, roe=0.15, k=0.05, g=0.05, price=10.0)
    with pytest.raises(ValueError, match="k.*must be > g"):
        value_stock(bvps=10.0, roe=0.15, k=0.04, g=0.05, price=10.0)


def test_negative_or_zero_price_rejected() -> None:
    with pytest.raises(ValueError, match="price"):
        value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=0)
    with pytest.raises(ValueError, match="price"):
        value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=-1.0)


def test_negative_or_zero_bvps_rejected() -> None:
    with pytest.raises(ValueError, match="bvps"):
        value_stock(bvps=0.0, roe=0.15, k=0.09, g=0.05, price=10.0)
    with pytest.raises(ValueError, match="bvps"):
        value_stock(bvps=-2.0, roe=0.15, k=0.09, g=0.05, price=10.0)


def test_negative_or_zero_roe_rejected() -> None:
    """Negative-ROE companies need a different framework — fail loud."""
    with pytest.raises(ValueError, match="roe"):
        value_stock(bvps=10.0, roe=0.0, k=0.09, g=0.05, price=10.0)
    with pytest.raises(ValueError, match="roe"):
        value_stock(bvps=10.0, roe=-0.05, k=0.09, g=0.05, price=10.0)


# ─────────────────────────────────────────────────────────────────────────────
# Entry levels — straight arithmetic, easy to verify
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_levels_match_methodology_percentages() -> None:
    """Entry tasot per methodology/formulas.md: 90/80/75% of fair value."""
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)
    assert v.entry_aloitus == pytest.approx(0.90 * v.fair_value, abs=1e-9)
    assert v.entry_nosto == pytest.approx(0.80 * v.fair_value, abs=1e-9)
    assert v.entry_taysi == pytest.approx(0.75 * v.fair_value, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Yli/ali — sign convention
# ─────────────────────────────────────────────────────────────────────────────


def test_yli_ali_negative_when_undervalued() -> None:
    """Undervalued = price below fair_value → yli_ali_pct negative."""
    # ALMA: price 8.20, fv 9.38 → undervalued
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)
    assert v.yli_ali_pct < 0


def test_yli_ali_positive_when_overvalued() -> None:
    """Overvalued = price above fair_value → yli_ali_pct positive."""
    # AKTIA: price 9.58 vs FV 8.34 → overvalued
    v = value_stock(bvps=10.17, roe=0.091, k=0.10, g=0.05, price=9.58)
    assert v.yli_ali_pct > 0


# ─────────────────────────────────────────────────────────────────────────────
# Rock Bottom — pessimistic anchor at k=12%
# ─────────────────────────────────────────────────────────────────────────────


def test_rock_bottom_uses_12pct_required_return() -> None:
    """Rock Bottom is the conservative anchor: ROE/0.12 × BVPS."""
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)
    expected = (0.19 / 0.12) * 2.68
    assert v.rock_bottom == pytest.approx(expected, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Determinism — same inputs always produce same output
# ─────────────────────────────────────────────────────────────────────────────


def test_engine_is_deterministic() -> None:
    """Two calls with identical inputs must produce identical outputs."""
    args = dict(bvps=5.0, roe=0.18, k=0.09, g=0.05, price=12.0)
    v1 = value_stock(**args)
    v2 = value_stock(**args)
    # All numeric fields must match exactly (no floating-point drift in the
    # same process, no hidden state)
    for field_name in v1.__dataclass_fields__:
        a = getattr(v1, field_name)
        b = getattr(v2, field_name)
        if isinstance(a, float):
            assert a == b, f"{field_name} differs: {a} vs {b}"
        elif isinstance(a, str):
            assert a == b, f"{field_name} differs: {a!r} vs {b!r}"


def test_returns_valuation_dataclass() -> None:
    """Sanity: ensure the public return type is the documented dataclass."""
    v = value_stock(bvps=5.0, roe=0.18, k=0.09, g=0.05, price=12.0)
    assert isinstance(v, Valuation)
