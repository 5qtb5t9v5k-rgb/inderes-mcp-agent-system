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
    fv_gordon: float                 # (ROE-g)/(k-g) × BVPS
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
    yli_ali_pct: float               # (price - fair_value) / price × 100

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

    return Valuation(
        bvps=bvps,
        roe=roe,
        k=k,
        g=g,
        price=price,
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
        entry_aloitus=0.90 * fair_value,
        entry_nosto=0.80 * fair_value,
        entry_taysi=0.75 * fair_value,
    )
