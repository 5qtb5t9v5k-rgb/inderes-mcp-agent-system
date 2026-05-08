"""Deterministic valuation engine — pure Python, no LLM dependency.

Implements Juho's 8-step valuation philosophy:

    1. k = tuottovaatimus (8–10%, ±1pp osakemarkkinoiden 9% tuotosta)
    2. g = pitkän aikavälin kasvu (4–6%, nominaalinen BKT-kasvu)
    3. BVPS = oman pääoman tasearvo per osake (input)
    4. FCF_ps = (ROE - g) × BVPS  — vapaa kassavirta per osake
    5. FV_Gordon = FCF_ps / (k - g) = ((ROE - g) / (k - g)) × BVPS
    6. EPV = (ROE / k) × BVPS  — Greenwald earning power value
    7. TV (laatuyhtiöt) = ((1 - g/ROE) / (1 - g/k)) × EPV  — algebraically == FV_Gordon
    8. Päätös: ROE > k → laatu (käytä FV_Gordon), ROE ≤ k → keskinkertainen (kasvu tuhoaa arvoa)

The engine reproduces the calculations on the Data-sheet of
``Arvonmääritys2023.xlsx`` exactly. See ``tests/valuation/test_excel_parity.py``
for the verification against 10 hand-picked Finnish companies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Valuation:
    """Structured result for a single (BVPS, ROE, k, g, price) valuation.

    Holds every value Excel's Data-sheet computes per row, plus the
    explicit ``quality`` decision (laatu / keskinkertainen / tuhoutuva)
    that drives whether growth is treated as additive or destructive.

    Both ``epv_pure`` (the no-growth perpetuity value `(ROE/k) × BVPS`)
    and ``epv_excel`` (Excel's S column convention — equals fv_gordon
    when ROE ≤ k) are exposed so callers can choose:
      - ``epv_pure`` for educational clarity ("pay this if no growth")
      - ``epv_excel`` for parity with the user's spreadsheet
    """

    # ── Inputs (echoed back for transparency in reports) ──
    bvps: float
    roe: float
    k: float
    g: float
    price: float

    # ── Pure derived values ──
    fcf_ps: float                    # (ROE - g) × BVPS — free cash flow per share
    fv_gordon: float                 # FCF_ps / (k-g) = (ROE-g)/(k-g) × BVPS
    epv_pure: float                  # (ROE/k) × BVPS — no-growth perpetuity
    growth_value_pure: float         # fv_gordon - epv_pure
    gm: float                        # (1-g/ROE) / (1-g/k) — Greenwald multiplier
    rock_bottom: float               # ROE/0.12 × BVPS — pessimistic anchor

    # ── Decision ──
    quality: Literal["laatu", "keskinkertainen", "tuhoutuva"]
    fair_value: float                # what the engine recommends as fair value
    rationale: str                   # one-sentence justification

    # ── Excel-compatible reporting (matches xlsx Data-sheet S, T columns) ──
    epv_excel: float                 # epv_pure when laatu, fv_gordon otherwise
    gv_excel: float                  # growth_value_pure when laatu, 0 otherwise

    # ── Market comparison ──
    pb: float                        # price / bvps
    yli_ali_pct: float               # (price - fair_value) / fair_value × 100
                                     # (matches Excel I column convention)

    # ── EPV / kasvun hinnoittelu -dekompositio ──
    # The Greenwald insight: total value = EPV + value of growth. The market
    # price decomposes the same way — so we can ask "how much of the current
    # price is the market paying for growth?" These four fields make that
    # decomposition explicit.
    market_premium_to_epv_pct: float    # (price - epv_pure) / epv_pure × 100
                                         # How much above the "no-growth"
                                         # value is the market paying?
                                         # Negative → "kasvun saa kaupan päälle PLUS alennus EPV:stä"
                                         # 0 → market prices zero growth
                                         # >0 → market pays for some growth
    growth_priced_in_share: float        # (price - epv_pure) / price
                                         # Share of current price that is
                                         # growth pricing. Can be negative
                                         # (price below EPV) or up to ~1
                                         # (almost all of price is growth).
    implied_g: float | None              # Inverse Gordon: solve for g given
                                         # current price WHILE HOLDING ROE
                                         # at the model's value. None when
                                         # math degenerates (P/B too close
                                         # to 1, or implied_g ≥ k).
    implied_roe: float                   # Dual inverse Gordon: solve for ROE
                                         # given current price WHILE HOLDING g
                                         # at the model's value.
                                         #   ROE = P/B × (k - g) + g
                                         # Always computable when k > g.
                                         #
                                         # Why both: Gordon has TWO unknowns
                                         # (ROE, g) but only ONE constraint
                                         # (price). The "missing value" vs
                                         # model's fair value can be
                                         # explained by EITHER lower-than-
                                         # assumed growth OR lower-than-
                                         # assumed ROE — or any combination.
                                         # Surface both to avoid the false
                                         # impression that "market is
                                         # pessimistic on growth specifically".
    safety_margin_to_fv_pct: float       # (fair_value - price) / fair_value × 100
                                         # Positive = market price is below
                                         # own fair value (undervalued from
                                         # this model's perspective). The
                                         # entry-level numbers below are
                                         # absolute thresholds; this is
                                         # the relative discount.

    # ── Entry levels (per methodology/formulas.md) ──
    entry_aloitus: float             # 0.90 × fair_value
    entry_nosto: float               # 0.80 × fair_value
    entry_taysi: float               # 0.75 × fair_value


def value_stock(
    *,
    bvps: float,
    roe: float,
    k: float,
    g: float,
    price: float,
) -> Valuation:
    """Compute a single valuation from raw inputs.

    All arguments are keyword-only to prevent ordering bugs — these
    five numbers are easy to mix up at call sites.

    Defaults (when the caller has no better signal):
      - k = 0.09  (osakemarkkinoiden keskimääräinen tuotto)
      - g = 0.05  (pitkän aikavälin nominaali-BKT-kasvu)

    Raises:
        ValueError: if k <= g (Gordon's formula breaks), if price <= 0,
                    if bvps <= 0, or if roe <= 0.

    Example::
        >>> v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)
        >>> v.quality
        'laatu'
        >>> round(v.fair_value, 2)
        9.38
    """
    # ── Input validation: fail loud rather than producing nonsense ──
    if k <= g:
        raise ValueError(
            f"k ({k:.4f}) must be > g ({g:.4f}) for Gordon's formula. "
            "Either lower g or raise k."
        )
    if price <= 0:
        raise ValueError(f"price must be > 0, got {price}")
    if bvps <= 0:
        raise ValueError(f"bvps (book value per share) must be > 0, got {bvps}")
    if roe <= 0:
        raise ValueError(
            f"roe must be > 0 for this engine. Got {roe}. "
            "Negative-ROE companies require a different framework "
            "(asset-based or distressed-asset analysis)."
        )

    # ── Pure formulas ──
    fcf_ps = (roe - g) * bvps                          # (4)
    fv_gordon = fcf_ps / (k - g)                       # (5) == ((ROE-g)/(k-g))*BVPS
    epv_pure = (roe / k) * bvps                        # (6)
    growth_value_pure = fv_gordon - epv_pure
    gm = (1 - g / roe) / (1 - g / k)                   # Greenwald growth multiplier
    rock_bottom = (roe / 0.12) * bvps                  # 12% required-return anchor

    # ── Quality decision (step 8) ──
    # ROE > k → growth ADDS value → use Gordon FV (which is > pure EPV)
    # ROE ≈ k → growth NEUTRAL → Gordon FV ≈ pure EPV
    # ROE < k → growth DESTROYS value → Gordon FV < pure EPV (use the lower)
    if roe > k * 1.02:  # ~2% buffer above k for "clearly laatu"
        quality: Literal["laatu", "keskinkertainen", "tuhoutuva"] = "laatu"
        rationale = (
            f"ROE {roe:.1%} > k {k:.1%} → kasvu lisää arvoa, käytetään "
            f"FV_Gordon. Growth multiplier {gm:.2f}x."
        )
    elif roe >= k * 0.98:  # within ±2% of k
        quality = "keskinkertainen"
        rationale = (
            f"ROE {roe:.1%} ≈ k {k:.1%} → kasvu neutraali, "
            f"FV_Gordon ≈ EPV. Growth multiplier {gm:.2f}x."
        )
    else:
        quality = "tuhoutuva"
        rationale = (
            f"ROE {roe:.1%} < k {k:.1%} → kasvu tuhoaa arvoa "
            f"(EPV {epv_pure:.2f} > FV_Gordon {fv_gordon:.2f}). "
            f"Growth multiplier {gm:.2f}x — alle 1.0 vahvistaa "
            f"diagnoosin."
        )

    # ── Fair value: Excel's convention is fv_gordon for both branches.
    # The "pay EPV for mediocre" alternative is exposed via epv_pure. ──
    fair_value = fv_gordon

    # ── Excel-compatible reporting (matches Data-sheet xlsx columns S, T) ──
    if quality == "laatu":
        epv_excel = epv_pure
        gv_excel = growth_value_pure
    else:
        # When ROE ≤ k, Excel treats EPV as the fair value itself and
        # zeros out growth value. This is the "kasvu tuhoaa arvoa" call:
        # don't credit destructive reinvestment as positive growth value.
        epv_excel = fv_gordon
        gv_excel = 0.0

    # ── Market comparison + entry levels ──
    # yli_ali_pct uses fair_value as the denominator (matches the user's
    # Excel column I = (G-H)/H = (price-fv)/fv). Reading: "kurssi on N%
    # yli/ali fundamentaalisen arvon."
    pb = price / bvps
    yli_ali_pct = (price - fair_value) / fair_value * 100.0

    # ── EPV / growth-pricing decomposition ──
    # The Greenwald split: market_price = EPV + (something for growth).
    # Compute three views of that decomposition.
    market_premium_to_epv_pct = (price - epv_pure) / epv_pure * 100.0
    growth_priced_in_share = (price - epv_pure) / price

    # Inverse Gordon: g_implied = (P/B × k - ROE) / (P/B - 1)
    #   Edge cases:
    #     - P/B too close to 1: denominator near zero, formula degenerates
    #     - implied_g >= k: Gordon explodes (no finite valuation)
    #   Both → return None and let the caller surface "ei laskettavissa".
    implied_g: float | None
    pb_minus_one = pb - 1.0
    if abs(pb_minus_one) < 0.001:
        # P/B ≈ 1 → market values at book → implied_g undefined
        # (any g satisfies if ROE = k; no g satisfies if ROE ≠ k).
        implied_g = None
    else:
        candidate = (pb * k - roe) / pb_minus_one
        if candidate >= k:
            # Implied growth at or above cost of capital → Gordon model
            # would explode. Surface as "off-the-chart" rather than
            # report a misleading number.
            implied_g = None
        else:
            implied_g = candidate

    # Dual inverse Gordon: solve for ROE given the current price WHILE
    # HOLDING g at the model's value. This gives the OTHER reading of the
    # same market price — instead of "market thinks growth is lower",
    # "market thinks ROE is lower". Both are mathematically valid
    # explanations for any price below model's fair value; surfacing
    # both avoids the false impression that one dimension is the
    # "real" gap.
    #
    #   P/B = (ROE - g) / (k - g)  →  ROE = P/B × (k - g) + g
    #
    # Always computable when k > g (which is enforced earlier). Can be
    # negative if P/B is very low (market pricing in decline). LEAD
    # narration handles such edge cases.
    implied_roe = pb * (k - g) + g

    # Safety margin = how much below own fair value is the price?
    # Positive = undervalued from the model's perspective.
    safety_margin_to_fv_pct = (fair_value - price) / fair_value * 100.0

    return Valuation(
        bvps=bvps,
        roe=roe,
        k=k,
        g=g,
        price=price,
        fcf_ps=fcf_ps,
        fv_gordon=fv_gordon,
        epv_pure=epv_pure,
        growth_value_pure=growth_value_pure,
        gm=gm,
        rock_bottom=rock_bottom,
        quality=quality,
        fair_value=fair_value,
        rationale=rationale,
        epv_excel=epv_excel,
        gv_excel=gv_excel,
        pb=pb,
        yli_ali_pct=yli_ali_pct,
        market_premium_to_epv_pct=market_premium_to_epv_pct,
        growth_priced_in_share=growth_priced_in_share,
        implied_g=implied_g,
        implied_roe=implied_roe,
        safety_margin_to_fv_pct=safety_margin_to_fv_pct,
        entry_aloitus=0.90 * fair_value,
        entry_nosto=0.80 * fair_value,
        entry_taysi=0.75 * fair_value,
    )
