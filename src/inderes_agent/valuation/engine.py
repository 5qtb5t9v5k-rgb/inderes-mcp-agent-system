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

In addition to single-point ``value_stock()``, the engine also exposes
``sensitivity_grid()`` which sweeps two axes (ROE, k, or g) over a
caller-specified range and returns a 2D fair-value grid. Used by the
UI's heatmap renderer to show how robust a valuation is to assumption
changes — the analyst's "what if I'm 1% off on k" sanity check
visible at a glance instead of a separate mental computation.
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

    # ── EPV-ankkuri: how much of the GROWTH VALUE is the market paying for? ──
    # Greenwald's framing for laatuyhtiöitä: split the price into "what
    # you're paying for current earning power" (= EPV) and "what you're
    # paying for expected growth" (= price - EPV). Then ask: how much of
    # the model's expected growth value (= FV - EPV) has the market priced
    # in already?
    #
    #   growth_paid_for_pct = (price − EPV) / (FV − EPV) × 100
    #
    # Reading:
    #   0 %   → market values the stock at EPV; ALL expected growth is
    #           "free upside" if the model is right
    #   100 % → market values the stock at full Gordon FV; you're paying
    #           for every cent of expected growth
    #   >100% → overpaying for growth (price above FV)
    #   <0 %  → market is below EPV; even the no-growth case is discounted
    #
    # This is the most actionable single number for laatu-luokan entries:
    # "Of the upside the model expects, how much have I locked in by paying
    # today's price?" Closely related to safety_margin_to_fv_pct but with
    # a more meaningful denominator for quality companies.
    #
    # None for tuhoutuva / keskinkertainen — those have growth_value_pure
    # ≤ 0 (or near-zero), so the ratio is undefined or misleading. The
    # whole "kasvun hinnoittelu" framing only makes sense when growth
    # actually adds value.
    growth_paid_for_pct: float | None

    # ── Entry levels — two parallel anchorings ──
    #
    # The 90/80/75 % FV thresholds (`entry_aloitus / nosto / taysi`) come
    # from the user's original Excel methodology. They're well-defined and
    # have Excel-parity tests pinning them, so we keep them.
    #
    # For LAATU companies (ROE > k), there's a much more meaningful
    # anchoring: the three semantically interpretable price points along
    # the EPV → FV spectrum. We surface the midpoint here; EPV-taso is
    # `epv_pure` and FV-taso is `fair_value` (already exposed as fields).
    #
    #   EPV-taso (epv_pure)                        → 0 % growth priced
    #   Kasvun puoliväli (entry_growth_midpoint)   → 50 % growth priced
    #   Fair value (fair_value)                    → 100 % growth priced
    #
    # For tuhoutuva and keskinkertainen the EPV-anchor framing inverts
    # (growth ≤ 0), so the midpoint is None and the synthesis renderer
    # falls back to the 90/80/75 % FV thresholds for those cases.
    entry_growth_midpoint: float | None

    # 90/80/75 % FV thresholds — kept for tuhoutuva / keskinkertainen
    # rendering, plus Excel-parity testing. Synthesis hides them for
    # laatu companies where the EPV-anchored levels above are clearer.
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

    # EPV-ankkuri: only meaningful for laatuyhtiöitä, where growth_value_pure
    # is a positive number (= the dollar amount of value growth contributes
    # on top of EPV). For tuhoutuva (ROE < k), growth_value_pure is negative
    # — the ratio would invert sign in confusing ways. For keskinkertainen
    # (ROE ≈ k), growth_value_pure is near zero — ratio explodes. In both
    # non-laatu cases the question "what fraction of growth has the market
    # priced in?" doesn't make narrative sense, so return None and let
    # callers omit the framing entirely.
    growth_paid_for_pct: float | None
    if quality == "laatu" and growth_value_pure > 1e-6:
        growth_paid_for_pct = (price - epv_pure) / growth_value_pure * 100.0
    else:
        growth_paid_for_pct = None

    # Kasvun puoliväli — the price at which exactly 50 % of the model's
    # expected growth value has been priced in. Equivalent to (EPV + FV)/2
    # but expressed as "EPV plus half of growth value" makes the meaning
    # explicit. Only meaningful for laatuyhtiöitä; None for the others.
    entry_growth_midpoint: float | None
    if quality == "laatu" and growth_value_pure > 1e-6:
        entry_growth_midpoint = epv_pure + 0.5 * growth_value_pure
    else:
        entry_growth_midpoint = None

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
        growth_paid_for_pct=growth_paid_for_pct,
        entry_growth_midpoint=entry_growth_midpoint,
        entry_aloitus=0.90 * fair_value,
        entry_nosto=0.80 * fair_value,
        entry_taysi=0.75 * fair_value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sensitivity grids
# ─────────────────────────────────────────────────────────────────────────────


# Axis identifiers — restricted to the three Gordon inputs that the analyst
# varies in practice. ``bvps`` is treated as a fixed observation (it's a
# reported number, not a judgement call); ``price`` is the market data point
# the grid is rendered against rather than swept over.
SensitivityAxis = Literal["roe", "k", "g"]


@dataclass(frozen=True)
class SensitivityGrid:
    """A 2D fair-value grid for two-axis sensitivity analysis.

    Used to render Excel-style heatmaps that answer "how robust is my
    valuation to a ±1pp shift in k, or a ±5pp shift in ROE?" — the
    standard "show your work + show the band" output that turns a
    single fair-value number into a defensible range.

    Structure:
      ``x_axis``, ``y_axis`` — which two of {roe, k, g} are swept
      ``x_values``, ``y_values`` — the actual sweep ticks (length ≥ 2)
      ``values`` — fair-value at each (y, x) cell; ``values[i][j]``
                   is the fair value when y_axis=y_values[i],
                   x_axis=x_values[j]. ``None`` when the formula
                   degenerates (k ≤ g) so the renderer can mark cells
                   as undefined rather than producing a misleading
                   number.
      ``base_x``, ``base_y`` — the analyst's chosen base values
                                (highlight position on the heatmap)
      ``base_fair_value`` — fair-value at the base point, redundant
                            with the cell at (base_y, base_x) but
                            exposed as a top-level field so callers
                            don't have to index.
      ``fixed`` — the third Gordon input that was held constant,
                   e.g. {"bvps": 8.25, "g": 0.04} when sweeping
                   roe × k.
      ``price`` — current market price, included so the heatmap
                   renderer can colour cells relative to it ("which
                   assumption combinations imply the stock is
                   undervalued vs overvalued at the current price").

    The grid is intentionally a frozen dataclass rather than a
    DataFrame: keeps the engine layer free of pandas dependency
    and makes the structure trivially serialisable for JSON
    transport between engine → workflow → UI.
    """

    x_axis: SensitivityAxis
    y_axis: SensitivityAxis
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    values: tuple[tuple[float | None, ...], ...]
    base_x: float
    base_y: float
    base_fair_value: float
    fixed: dict[str, float]
    price: float


def _fmt_axis(name: str) -> str:
    """Human-readable axis label for tooling/logging. Not for UI render."""
    return {"roe": "ROE", "k": "k (tuottovaatimus)", "g": "g (kasvu)"}.get(
        name, name
    )


def sensitivity_grid(
    *,
    bvps: float,
    roe: float,
    k: float,
    g: float,
    price: float,
    x_axis: SensitivityAxis = "k",
    y_axis: SensitivityAxis = "roe",
    x_values: tuple[float, ...] | None = None,
    y_values: tuple[float, ...] | None = None,
) -> SensitivityGrid:
    """Compute a 2D fair-value grid by sweeping two axes around the base.

    The two most analytically valuable grids — and the defaults if no
    custom ranges are passed:

      - ``y=roe`` × ``x=k`` — answers "is my valuation a knife-edge bet
        on the cost-of-equity assumption, or is there comfort across
        the realistic ROE band?" The most common version in the
        analyst's mental model.
      - ``y=g`` × ``x=k`` (with ``roe`` fixed) — answers "is the
        valuation driven by aggressive long-term growth or by the
        spread between ROE and k?" Tells you which assumption to
        defend hardest.

    The cells use the same ``value_stock`` math as the single-point
    valuation. When a particular (k, g) combination makes k ≤ g
    (Gordon's formula breaks), that cell is set to ``None`` so the
    renderer can mark it as undefined.

    Args:
        bvps / roe / k / g / price: the **base** inputs. These are
            the analyst's central scenario. The grid is centered
            around the base point.
        x_axis / y_axis: which two of {"roe", "k", "g"} to sweep.
            Must be distinct.
        x_values / y_values: explicit sweep ticks. If ``None``,
            the engine picks sensible defaults centred on the base:
              - roe sweep: base ±10pp in 5 ticks (e.g. 0.20→0.30 for base 0.25)
              - k sweep:   base ±4pp in 5 ticks (e.g. 0.08→0.12 for base 0.10)
              - g sweep:   base ±2pp in 5 ticks (e.g. 0.03→0.07 for base 0.05)

    Returns:
        ``SensitivityGrid`` with all cells filled and ``base_x`` /
        ``base_y`` set to the closest tick that contains the base
        value. The renderer can match these to highlight the
        analyst's central scenario on the heatmap.

    Raises:
        ValueError: if ``x_axis == y_axis``, or if either axis name
            is not one of {"roe", "k", "g"}.
    """
    if x_axis == y_axis:
        raise ValueError(
            f"x_axis and y_axis must differ, got both={x_axis!r}"
        )

    base_lookup = {"roe": roe, "k": k, "g": g}
    if x_axis not in base_lookup or y_axis not in base_lookup:
        raise ValueError(
            f"axis names must be from {set(base_lookup)}, "
            f"got x={x_axis!r} y={y_axis!r}"
        )

    # ── Default sweep ranges centred on the base value ──
    # Designed to match the analyst's mental model: "show me ±a couple
    # standard guesses around what I think it is." Width was tuned so
    # the heatmap covers both the "I'm wrong by a believable amount"
    # band AND the "this is wildly wrong" band, without wasting cells
    # on values nobody would actually defend.
    def _default_range(axis: SensitivityAxis, centre: float) -> tuple[float, ...]:
        widths = {"roe": 0.10, "k": 0.04, "g": 0.02}
        half = widths[axis] / 2
        return tuple(round(centre - half + (i / 4) * 2 * half, 4) for i in range(5))

    xs = x_values if x_values is not None else _default_range(x_axis, base_lookup[x_axis])
    ys = y_values if y_values is not None else _default_range(y_axis, base_lookup[y_axis])

    # ── Sweep ──
    # We build the grid in row-major order: outer loop over y (rows),
    # inner over x (columns). That matches how the UI will render it
    # (one HTML table row per y_value) and how an analyst reads it
    # (varying one axis at a time).
    rows: list[tuple[float | None, ...]] = []
    for y in ys:
        row: list[float | None] = []
        for x in xs:
            inputs = {"roe": roe, "k": k, "g": g}
            inputs[x_axis] = x
            inputs[y_axis] = y
            try:
                v = value_stock(bvps=bvps, price=price, **inputs)
                row.append(v.fair_value)
            except ValueError:
                # k ≤ g, or other invariant violation — Gordon's
                # formula breaks here. Mark as undefined; the
                # renderer can shade these cells differently.
                row.append(None)
        rows.append(tuple(row))

    # ── Base value for highlighting ──
    # The analyst's central scenario should sit ON the grid as a
    # highlight target, not be approximated. We re-compute at the
    # exact base point rather than relying on the closest sweep tick,
    # so the highlighted number matches the rest of the valuation
    # report exactly.
    base_fv = value_stock(bvps=bvps, roe=roe, k=k, g=g, price=price).fair_value

    # ── "Fixed" axis = whichever Gordon input isn't being swept ──
    # Plus bvps which is always fixed (it's an observation, not a
    # judgement call). The renderer uses this for the caption
    # "BVPS=8.25, g=4.0% (kiinnitetty)".
    fixed_axis = next(
        a for a in ("roe", "k", "g") if a != x_axis and a != y_axis
    )
    fixed = {fixed_axis: base_lookup[fixed_axis], "bvps": bvps}

    return SensitivityGrid(
        x_axis=x_axis,
        y_axis=y_axis,
        x_values=tuple(xs),
        y_values=tuple(ys),
        values=tuple(rows),
        base_x=base_lookup[x_axis],
        base_y=base_lookup[y_axis],
        base_fair_value=base_fv,
        fixed=fixed,
        price=price,
    )
