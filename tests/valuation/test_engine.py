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


# ─────────────────────────────────────────────────────────────────────────────
# EPV / growth-pricing decomposition (the Excel "Markkinahinnoittelu" view)
# ─────────────────────────────────────────────────────────────────────────────


def test_market_premium_to_epv_for_sampo_case() -> None:
    """Sampo from run 20260508-171706-948.

    Engine inputs that the agent fed to the engine:
      BVPS=3.04, ROE=20.7%, k=8%, g=3.5%, price=9.32

    Engine computes:
      EPV_pure = (0.207/0.08) × 3.04 = 7.86
      Market premium to EPV = (9.32 - 7.86) / 7.86 ≈ +18.6%
      Growth_priced_in_share = (9.32 - 7.86) / 9.32 ≈ 15.7%
    """
    v = value_stock(bvps=3.0385, roe=0.207, k=0.08, g=0.035, price=9.32)
    assert v.epv_pure == pytest.approx(7.862, abs=0.01)
    assert v.market_premium_to_epv_pct == pytest.approx(18.5, abs=0.5)
    assert v.growth_priced_in_share == pytest.approx(0.157, abs=0.005)


def test_implied_g_for_sampo_pessimistic_market() -> None:
    """Sampo: market is pricing less growth than the model assumes."""
    v = value_stock(bvps=3.0385, roe=0.207, k=0.08, g=0.035, price=9.32)
    # implied_g = (P/B × k - ROE) / (P/B - 1)
    # P/B = 3.067; (3.067 × 0.08 - 0.207) / (3.067 - 1) ≈ 0.0185 = 1.85%
    assert v.implied_g is not None
    assert v.implied_g == pytest.approx(0.0185, abs=0.002)
    # Market (1.85%) < model (3.5%) → market is more pessimistic
    assert v.implied_g < v.g


def test_implied_g_for_qt_optimistic_market() -> None:
    """Qt: market is pricing MORE growth than the model assumes.

    Inputs (with the corrected ROE per the new sustainable rule):
      BVPS=8.25, ROE=18.1% (3y_median), k=11%, g=5.5%, price=32.94
    """
    v = value_stock(bvps=8.25, roe=0.181, k=0.11, g=0.055, price=32.94)
    # implied_g = (P/B × k - ROE) / (P/B - 1)
    # P/B = 3.99; (3.99 × 0.11 - 0.181) / (3.99 - 1) ≈ 0.0863 = 8.6%
    assert v.implied_g is not None
    assert v.implied_g == pytest.approx(0.0863, abs=0.002)
    # Market (8.6%) > model (5.5%) → market is more optimistic
    assert v.implied_g > v.g


def test_safety_margin_undervalued_positive() -> None:
    """Sampo: price 9.32 < fair_value 11.61 → positive margin (undervalued)."""
    v = value_stock(bvps=3.0385, roe=0.207, k=0.08, g=0.035, price=9.32)
    # safety_margin_to_fv_pct = (fair_value - price) / fair_value × 100
    # (11.61 - 9.32) / 11.61 = 0.197 → +19.7%
    assert v.safety_margin_to_fv_pct == pytest.approx(19.7, abs=0.5)
    assert v.safety_margin_to_fv_pct > 0


def test_safety_margin_overvalued_negative() -> None:
    """Qt with corrected ROE: price 32.94 > fair_value 22.65 → negative margin."""
    v = value_stock(bvps=8.25, roe=0.181, k=0.11, g=0.055, price=32.94)
    assert v.safety_margin_to_fv_pct < 0


def test_kasvun_saa_kaupan_paalle() -> None:
    """When price < EPV, market prices in zero or negative growth.

    Construct a case where price is well below the no-growth value.
    """
    # Build a laatu-yhtiö but price it at 80% of EPV
    v = value_stock(bvps=10.0, roe=0.20, k=0.08, g=0.05, price=20.0)
    # EPV_pure = (0.20/0.08) × 10 = 25.0
    # price 20 < epv 25 → growth_priced_in_share negative
    assert v.epv_pure == pytest.approx(25.0)
    assert v.market_premium_to_epv_pct < 0
    assert v.growth_priced_in_share < 0
    # Implied growth would be negative (or None if math degenerates)
    if v.implied_g is not None:
        # Market is pricing in less growth than zero — interpret as decline expected
        assert v.implied_g < 0.05  # below model's g, definitely


def test_implied_g_returns_none_when_pb_near_one() -> None:
    """P/B ≈ 1 → market values at book → implied_g undefined."""
    # Construct so that price = bvps (P/B = 1.0)
    v = value_stock(bvps=10.0, roe=0.10, k=0.10, g=0.05, price=10.0)
    # ROE == k boundary → quality = keskinkertainen, P/B exactly 1
    assert v.pb == pytest.approx(1.0)
    assert v.implied_g is None


def test_implied_g_returns_none_when_explosion() -> None:
    """If implied_g would be ≥ k, return None rather than a misleading number."""
    # First a case that does NOT actually explode (kept as a learning comment):
    # value_stock(bvps=1.0, roe=0.10, k=0.08, g=0.04, price=20.0)
    # P/B = 20. (20 × 0.08 - 0.10) / 19 = 1.5 / 19 = 0.079 < 0.08 → not explosive.
    # Now a case that does explode:
    v2 = value_stock(bvps=1.0, roe=0.05, k=0.08, g=0.04, price=20.0)
    # P/B = 20. (20 × 0.08 - 0.05) / 19 = 1.55 / 19 = 0.0816 > 0.08 → None
    assert v2.implied_g is None


def test_decomposition_internally_consistent() -> None:
    """Sanity: market_premium_to_epv_pct ↔ growth_priced_in_share match."""
    v = value_stock(bvps=10.0, roe=0.20, k=0.10, g=0.04, price=30.0)
    # market_premium_to_epv_pct = (price - epv) / epv × 100
    # growth_priced_in_share = (price - epv) / price
    # Both have the same numerator (price - epv); just different denominators.
    expected_premium = (v.price - v.epv_pure) / v.epv_pure * 100.0
    expected_share = (v.price - v.epv_pure) / v.price
    assert v.market_premium_to_epv_pct == pytest.approx(expected_premium, abs=1e-6)
    assert v.growth_priced_in_share == pytest.approx(expected_share, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# FCF per share — exposed in dataclass for the perussetti table
# ─────────────────────────────────────────────────────────────────────────────


def test_fcf_ps_matches_definition() -> None:
    """fcf_ps = (ROE - g) × BVPS — the free cash flow per share."""
    v = value_stock(bvps=10.0, roe=0.18, k=0.09, g=0.05, price=15.0)
    expected = (0.18 - 0.05) * 10.0
    assert v.fcf_ps == pytest.approx(expected, abs=1e-9)


def test_fv_gordon_equals_fcf_over_k_minus_g() -> None:
    """Sanity that FV_Gordon = FCF_ps / (k - g)."""
    v = value_stock(bvps=10.0, roe=0.18, k=0.09, g=0.05, price=15.0)
    expected = v.fcf_ps / (v.k - v.g)
    assert v.fv_gordon == pytest.approx(expected, abs=1e-9)


def test_fcf_ps_negative_when_roe_below_g() -> None:
    """FCF goes negative when ROE < g (cash sink). Engine still computes —
    LEAD prompt warns about this case interpretively."""
    v = value_stock(bvps=10.0, roe=0.04, k=0.10, g=0.05, price=4.0)
    assert v.fcf_ps < 0
    # Quality is "tuhoutuva" since ROE < k
    assert v.quality == "tuhoutuva"


# ─────────────────────────────────────────────────────────────────────────────
# Implied ROE — dual inverse Gordon (hold g, solve ROE)
# ─────────────────────────────────────────────────────────────────────────────


def test_implied_roe_for_nordea_case() -> None:
    """Nordea (2026-05-08): BVPS 9.41, k 9%, g 3%, price 16.09.

    Implied ROE = P/B × (k - g) + g
    P/B = 16.09/9.41 = 1.7099
    implied_roe = 1.7099 × 0.06 + 0.03 = 0.1326 = 13.26%

    Compared to model's ROE=15%, market implies ROE 13.26% (at model's g=3%).
    Both are valid readings of the same gap (FV 18.86 vs price 16.09).
    """
    v = value_stock(bvps=9.41, roe=0.15, k=0.09, g=0.03, price=16.09)
    assert v.implied_roe == pytest.approx(0.1326, abs=0.001)
    assert v.implied_roe < v.roe  # market more pessimistic on ROE


def test_implied_roe_at_fair_value_equals_model_roe() -> None:
    """Sanity: when price = fair_value, implied_roe should equal model ROE."""
    v = value_stock(bvps=10.0, roe=0.18, k=0.09, g=0.05, price=10.0)
    v_at_fv = value_stock(bvps=10.0, roe=0.18, k=0.09, g=0.05, price=v.fv_gordon)
    assert v_at_fv.implied_roe == pytest.approx(0.18, abs=1e-6)


def test_implied_roe_inverse_consistency() -> None:
    """If we plug implied_roe back into Gordon with the model's g and k,
    we should recover the current price."""
    v = value_stock(bvps=9.41, roe=0.15, k=0.09, g=0.03, price=16.09)
    pb_reconstructed = (v.implied_roe - v.g) / (v.k - v.g)
    price_reconstructed = pb_reconstructed * v.bvps
    assert price_reconstructed == pytest.approx(v.price, abs=0.001)


def test_implied_roe_at_pb_one_equals_k() -> None:
    """When P/B = 1 (market values exactly at book), implied_roe = k.

    Algebraic derivation:
      P/B = (ROE - g)/(k - g) = 1
      → ROE - g = k - g
      → ROE = k

    Intuition: P/B = 1 means market expects no premium over book, which
    corresponds to ROE exactly meeting the cost of capital.
    """
    v = value_stock(bvps=10.0, roe=0.10, k=0.09, g=0.05, price=10.0)
    assert v.pb == pytest.approx(1.0, abs=1e-9)
    assert v.implied_roe == pytest.approx(v.k, abs=1e-6)


def test_implied_roe_above_model_roe_when_overvalued() -> None:
    """When price > fair_value, implied_roe > model_roe."""
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=12.0)
    assert v.price > v.fv_gordon  # overvalued
    assert v.implied_roe > v.roe  # market implies higher ROE than model


# ─────────────────────────────────────────────────────────────────────────────
# growth_paid_for_pct — EPV-ankkuri framing for laatuyhtiöitä
#
# Greenwald insight: split price into "what you're paying for current
# earning power" (EPV) vs "what you're paying for expected growth"
# (price - EPV). The most actionable single number for quality companies is
# the fraction of expected growth value (FV - EPV) that the market has
# already priced into today's price:
#
#   growth_paid_for_pct = (price - EPV) / (FV - EPV) × 100
#
# 0 % means you're paying just EPV — all upside is "free" if the model is
# right. 100 % means you're paying full Gordon FV. >100 % means overpaying.
# Only meaningful for laatuyhtiöitä (ROE > k, growth ADDS value); None for
# tuhoutuva and keskinkertainen because growth value ≤ 0 makes the ratio
# undefined or sign-flipped.
# ─────────────────────────────────────────────────────────────────────────────


def test_growth_paid_for_pct_for_nordea_case() -> None:
    """Nordea-style laatu case where price is just above EPV.

    With ROE 15%, k 9%, g 3.5%, BVPS 9.41, price 16.09:
      EPV = (0.15/0.09) × 9.41 ≈ 15.68
      FV  = ((0.15-0.035)/(0.09-0.035)) × 9.41 ≈ 19.68
      growth_value = FV - EPV ≈ 4.00
      price - EPV = 16.09 - 15.68 ≈ 0.41
      growth_paid_for ≈ 10 %

    User reading: "market has priced in only 10 % of expected growth
    value, so 90 % is free upside if the model is right."
    """
    v = value_stock(bvps=9.41, roe=0.15, k=0.09, g=0.035, price=16.09)
    assert v.quality == "laatu"
    assert v.growth_paid_for_pct is not None
    assert v.growth_paid_for_pct == pytest.approx(10.2, abs=1.0)


def test_growth_paid_for_pct_at_epv_is_zero() -> None:
    """When price equals EPV exactly, growth_paid_for = 0 %.

    User reading: "I'm paying for current earning power only; all
    expected growth is free upside."
    """
    bvps, roe, k = 10.0, 0.15, 0.09
    epv = (roe / k) * bvps  # ≈ 16.67
    v = value_stock(bvps=bvps, roe=roe, k=k, g=0.05, price=epv)
    assert v.quality == "laatu"
    assert v.growth_paid_for_pct == pytest.approx(0.0, abs=0.01)


def test_growth_paid_for_pct_at_fair_value_is_100() -> None:
    """When price equals fair_value exactly, growth_paid_for = 100 %.

    User reading: "I'm paying for the entire model-expected upside,
    no free growth, no margin."
    """
    bvps, roe, k, g = 10.0, 0.15, 0.09, 0.05
    fcf = (roe - g) * bvps
    fv = fcf / (k - g)  # 25.0
    v = value_stock(bvps=bvps, roe=roe, k=k, g=g, price=fv)
    assert v.quality == "laatu"
    assert v.growth_paid_for_pct == pytest.approx(100.0, abs=0.01)


def test_growth_paid_for_pct_above_fv_exceeds_100() -> None:
    """When price > fair_value, growth_paid_for > 100 % — overpaying."""
    v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=12.0)
    assert v.quality == "laatu"
    assert v.price > v.fv_gordon
    assert v.growth_paid_for_pct is not None
    assert v.growth_paid_for_pct > 100.0


def test_growth_paid_for_pct_below_epv_negative() -> None:
    """When price < EPV (rare for laatu), growth_paid_for < 0 % —
    market is below the no-growth value. User reading: 'kasvu kaupan
    päälle PLUS alennus EPV:stä' (growth as bonus on top of an
    already-discounted earning-power floor)."""
    v = value_stock(bvps=10.0, roe=0.20, k=0.09, g=0.05, price=15.0)
    assert v.quality == "laatu"
    epv = (0.20 / 0.09) * 10.0  # ≈ 22.22
    assert v.price < epv  # below EPV
    assert v.growth_paid_for_pct is not None
    assert v.growth_paid_for_pct < 0


def test_growth_paid_for_pct_none_for_tuhoutuva() -> None:
    """For tuhoutuva (ROE < k), growth_value_pure ≤ 0 — the EPV-anchor
    framing inverts and becomes confusing. Engine returns None and
    UI/LEAD must omit the framing."""
    v = value_stock(bvps=10.17, roe=0.091, k=0.10, g=0.05, price=9.58)
    assert v.quality == "tuhoutuva"
    assert v.growth_paid_for_pct is None


def test_growth_paid_for_pct_none_for_keskinkertainen() -> None:
    """For keskinkertainen (ROE ≈ k within ±2 % buffer), growth_value_pure
    is near zero — the ratio explodes / is misleading. Engine returns
    None just like for tuhoutuva."""
    v = value_stock(bvps=10.0, roe=0.091, k=0.09, g=0.05, price=10.0)
    assert v.quality == "keskinkertainen"
    assert v.growth_paid_for_pct is None


def test_growth_paid_for_pct_relates_to_safety_margin() -> None:
    """Sanity: when price < FV (positive safety margin) AND laatu,
    growth_paid_for < 100. When price > FV (negative safety margin),
    growth_paid_for > 100. They convey related but distinct information.

    growth_paid_for is more meaningful for laatu because:
      - It tells you "what fraction of expected upside you've locked in"
      - safety_margin tells you "by how much you got the stock cheaper than FV"
    The two converge near FV but diverge near EPV.
    """
    # Undervalued laatu: positive margin AND <100% growth paid
    v_under = value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=18.0)
    assert v_under.safety_margin_to_fv_pct > 0
    assert v_under.growth_paid_for_pct is not None
    assert v_under.growth_paid_for_pct < 100.0
    # Overvalued laatu: negative margin AND >100% growth paid
    v_over = value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=30.0)
    assert v_over.safety_margin_to_fv_pct < 0
    assert v_over.growth_paid_for_pct is not None
    assert v_over.growth_paid_for_pct > 100.0


# ─────────────────────────────────────────────────────────────────────────────
# entry_growth_midpoint — EPV-anchored entry levels for laatuyhtiöitä
#
# Replaces the arbitrary 90/80/75 % of FV thresholds for quality
# companies with a semantically meaningful three-tier scale:
#
#   EPV-taso (= epv_pure)                  → 0 % of growth priced in
#   Kasvun puoliväli (= entry_growth_midpoint) → 50 % of growth priced in
#   Fair value (= fair_value)              → 100 % of growth priced in
#
# The midpoint = epv_pure + 0.5 × growth_value_pure (algebraically same
# as (epv + fv) / 2, but the additive form makes the semantic intent
# explicit). None for tuhoutuva / keskinkertainen — those still get the
# 90/80/75 % FV thresholds in synthesis rendering.
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_growth_midpoint_for_laatu() -> None:
    """For a quality company, midpoint = (EPV + FV) / 2."""
    v = value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=20.0)
    assert v.quality == "laatu"
    assert v.entry_growth_midpoint is not None
    expected_mid = (v.epv_pure + v.fair_value) / 2.0
    assert v.entry_growth_midpoint == pytest.approx(expected_mid, abs=1e-9)


def test_entry_growth_midpoint_equals_epv_plus_half_growth() -> None:
    """The semantic formulation: midpoint = EPV + 0.5 × growth_value.
    Same number as (EPV + FV) / 2, but framed for the user's mental
    model: 'pay for EPV plus half of expected growth'."""
    v = value_stock(bvps=10.0, roe=0.20, k=0.09, g=0.05, price=20.0)
    assert v.quality == "laatu"
    expected = v.epv_pure + 0.5 * v.growth_value_pure
    assert v.entry_growth_midpoint == pytest.approx(expected, abs=1e-9)


def test_entry_growth_midpoint_at_50pct_growth_paid() -> None:
    """When price equals the midpoint, growth_paid_for_pct should be 50 %.
    This is the inverse-consistency test that ties midpoint and the
    EPV-ankkuri framing together."""
    bvps, roe, k, g = 10.0, 0.15, 0.09, 0.05
    epv = (roe / k) * bvps
    fv = ((roe - g) / (k - g)) * bvps
    midpoint = (epv + fv) / 2.0
    v = value_stock(bvps=bvps, roe=roe, k=k, g=g, price=midpoint)
    assert v.entry_growth_midpoint == pytest.approx(midpoint, abs=1e-9)
    assert v.growth_paid_for_pct == pytest.approx(50.0, abs=0.01)


def test_entry_growth_midpoint_none_for_tuhoutuva() -> None:
    """For tuhoutuva, growth ≤ 0, EPV-anchor framing doesn't apply →
    None. Synthesis falls back to 90/80/75 % FV entry thresholds."""
    v = value_stock(bvps=10.17, roe=0.091, k=0.10, g=0.05, price=9.58)
    assert v.quality == "tuhoutuva"
    assert v.entry_growth_midpoint is None


def test_entry_growth_midpoint_none_for_keskinkertainen() -> None:
    """For keskinkertainen, growth_value ≈ 0 → midpoint would be near EPV.
    Returning None keeps the framing consistent with growth_paid_for_pct
    (also None for keskinkertainen)."""
    v = value_stock(bvps=10.0, roe=0.091, k=0.09, g=0.05, price=10.0)
    assert v.quality == "keskinkertainen"
    assert v.entry_growth_midpoint is None


def test_entry_growth_midpoint_between_epv_and_fv() -> None:
    """Sanity: midpoint must lie strictly between EPV and FV for laatu."""
    v = value_stock(bvps=10.0, roe=0.20, k=0.09, g=0.05, price=20.0)
    assert v.quality == "laatu"
    assert v.epv_pure < v.entry_growth_midpoint < v.fair_value


def test_entry_levels_still_present_for_laatu() -> None:
    """The 90/80/75 % FV entry levels remain populated even for laatu;
    synthesis just chooses which set to display. Excel-parity tests
    depend on these being present unconditionally."""
    v = value_stock(bvps=10.0, roe=0.15, k=0.09, g=0.05, price=20.0)
    assert v.entry_aloitus == pytest.approx(0.90 * v.fair_value)
    assert v.entry_nosto == pytest.approx(0.80 * v.fair_value)
    assert v.entry_taysi == pytest.approx(0.75 * v.fair_value)
