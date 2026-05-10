"""Parity test: engine output must match the user's ``Arvonmääritys2023.xlsx``.

The 10 cases below were extracted from the Data-sheet of the spreadsheet
on 2026-05-08. They cover the full range of quality categories:

  - **Laatuyhtiöt** (ROE > k, kasvu lisää arvoa):
      AALLON, ADMCM, ALMA, BITTI, ELISA, EQV1V
  - **Keskinkertaiset / tuhoutuvat** (ROE ≤ k, kasvu tuhoaa arvoa):
      AKTIA, CGCBV, CTY1S, FIA1S

For every case the engine must reproduce Excel's columns:
  H = fair-value,
  S = epv (Excel's quality-aware reporting),
  T = gv  (Excel's quality-aware reporting),
  M = P/B,
  N = Kasvukerroin (GM),
  P = Rock Bottom,
  I = yli_ali_pct.

Tolerance: 0.02 absolute (Excel rounds 2dp for display; engine carries full
precision). For ratios (P/B, GM) tolerance is 0.005.

If this test breaks because Excel was updated, regenerate the fixture by
running the helper at the bottom of this file. Don't tweak tolerances to
make a real bug pass.
"""

from __future__ import annotations

import pytest

from inderes_agent.valuation import value_stock

# ─────────────────────────────────────────────────────────────────────────────
# Fixture: 10 Finnish companies, hand-picked from
# /Users/juhorissanen/Downloads/Arvonmääritys2023.xlsx, Data-sheet, 2026-05-08.
# Numbers carry the rounding precision Excel exposed in the cached cells.
# ─────────────────────────────────────────────────────────────────────────────
EXCEL_PARITY_CASES: list[dict] = [
    dict(
        ticker="AALLON", yhtio="Aallon Group Oyj",
        bvps=3.708, roe=0.20, k=0.08, g=0.05, price=9.40,
        expected={
            "fv": 18.54, "epv_excel": 9.27, "gv_excel": 9.27,
            "gm": 2.0, "pb": 2.5351, "rock_bottom": 6.18,
            "yli_ali_pct": -49.2988,
        },
    ),
    dict(
        ticker="ADMCM", yhtio="Admicom Oyj",
        bvps=5.762, roe=0.271, k=0.08, g=0.06, price=50.60,
        expected={
            "fv": 60.79, "epv_excel": 19.52, "gv_excel": 41.27,
            "gm": 3.1144, "pb": 8.7817, "rock_bottom": 13.01,
            "yli_ali_pct": -16.7613,
        },
    ),
    dict(
        ticker="AKTIA", yhtio="Aktia Bank Abp",
        bvps=10.17, roe=0.091, k=0.10, g=0.05, price=9.58,
        expected={
            "fv": 8.34, "epv_excel": 8.34, "gv_excel": 0.0,
            "gm": 0.9011, "pb": 0.942, "rock_bottom": 7.71,
            "yli_ali_pct": 14.8819,
        },
    ),
    dict(
        ticker="ALMA", yhtio="Alma Media Oyj",
        bvps=2.679, roe=0.19, k=0.09, g=0.05, price=11.00,
        expected={
            "fv": 9.38, "epv_excel": 5.66, "gv_excel": 3.72,
            "gm": 1.6579, "pb": 4.106, "rock_bottom": 4.24,
            "yli_ali_pct": 17.3083,
        },
    ),
    dict(
        ticker="BITTI", yhtio="Bittium Oyj",
        bvps=3.032, roe=0.13, k=0.10, g=0.06, price=6.66,
        expected={
            "fv": 5.31, "epv_excel": 3.94, "gv_excel": 1.36,
            "gm": 1.3462, "pb": 2.1966, "rock_bottom": 3.28,
            "yli_ali_pct": 25.5183,
        },
    ),
    dict(
        ticker="CGCBV", yhtio="Cargotec Corp",
        bvps=18.683, roe=0.09, k=0.10, g=0.05, price=46.67,
        expected={
            "fv": 14.95, "epv_excel": 14.95, "gv_excel": 0.0,
            "gm": 0.8889, "pb": 2.498, "rock_bottom": 14.01,
            "yli_ali_pct": 212.2575,
        },
    ),
    dict(
        ticker="CTY1S", yhtio="Citycon Oyj",
        bvps=10.90, roe=0.07, k=0.10, g=0.05, price=3.37,
        expected={
            "fv": 4.36, "epv_excel": 4.36, "gv_excel": 0.0,
            "gm": 0.5714, "pb": 0.3092, "rock_bottom": 6.36,
            "yli_ali_pct": -22.7064,
        },
    ),
    dict(
        ticker="ELISA", yhtio="Elisa Oyj",
        bvps=7.478, roe=0.27, k=0.08, g=0.05, price=43.10,
        expected={
            "fv": 54.84, "epv_excel": 25.24, "gv_excel": 29.60,
            "gm": 2.1728, "pb": 5.7636, "rock_bottom": 16.83,
            "yli_ali_pct": -21.4063,
        },
    ),
    dict(
        ticker="EQV1V", yhtio="eQ Oyj",
        bvps=1.636, roe=0.24, k=0.08, g=0.06, price=12.10,
        expected={
            "fv": 14.72, "epv_excel": 4.91, "gv_excel": 9.82,
            "gm": 3.0, "pb": 7.3961, "rock_bottom": 3.27,
            "yli_ali_pct": -17.8212,
        },
    ),
    dict(
        ticker="FIA1S", yhtio="Finnair Oyj",
        bvps=2.872, roe=0.09, k=0.10, g=0.05, price=2.3055,
        expected={
            "fv": 2.30, "epv_excel": 2.30, "gv_excel": 0.0,
            "gm": 0.8889, "pb": 0.8028, "rock_bottom": 2.15,
            "yli_ali_pct": 0.3264,
        },
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Tolerances — Excel shows 2dp; engine carries full precision. The tolerance
# is set to absorb the Excel display rounding without hiding genuine bugs.
# ─────────────────────────────────────────────────────────────────────────────
ABS_TOL_EUR = 0.02     # for euro amounts (FV, EPV, GV, Rock Bottom)
ABS_TOL_RATIO = 0.005  # for ratios (P/B, GM)
ABS_TOL_PCT = 0.05     # for yli_ali_pct (which is shown to 4dp in Excel)


@pytest.mark.parametrize(
    "case",
    EXCEL_PARITY_CASES,
    ids=[c["ticker"] for c in EXCEL_PARITY_CASES],
)
def test_engine_matches_excel(case: dict) -> None:
    """Engine output for the 10 fixture rows must match Excel's Data-sheet."""
    v = value_stock(
        bvps=case["bvps"],
        roe=case["roe"],
        k=case["k"],
        g=case["g"],
        price=case["price"],
    )
    e = case["expected"]

    # Headline numbers
    assert v.fair_value == pytest.approx(e["fv"], abs=ABS_TOL_EUR), \
        f"{case['ticker']}: fair_value mismatch"
    assert v.epv_excel == pytest.approx(e["epv_excel"], abs=ABS_TOL_EUR), \
        f"{case['ticker']}: epv_excel mismatch"
    assert v.gv_excel == pytest.approx(e["gv_excel"], abs=ABS_TOL_EUR), \
        f"{case['ticker']}: gv_excel mismatch"
    assert v.rock_bottom == pytest.approx(e["rock_bottom"], abs=ABS_TOL_EUR), \
        f"{case['ticker']}: rock_bottom mismatch"

    # Ratios
    assert v.pb == pytest.approx(e["pb"], abs=ABS_TOL_RATIO), \
        f"{case['ticker']}: pb mismatch"
    assert v.gm == pytest.approx(e["gm"], abs=ABS_TOL_RATIO), \
        f"{case['ticker']}: gm mismatch"

    # Yli/ali percentage
    assert v.yli_ali_pct == pytest.approx(e["yli_ali_pct"], abs=ABS_TOL_PCT), \
        f"{case['ticker']}: yli_ali_pct mismatch"


# ─────────────────────────────────────────────────────────────────────────────
# Quality classification — make the engine's labelling explicit per case.
# This is a sanity check that the laatu/keskinkertainen/tuhoutuva decision
# matches what we'd expect from each row's ROE vs k.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "ticker,expected_quality",
    [
        ("AALLON", "laatu"),         # ROE 20% >> k 8%
        ("ADMCM", "laatu"),          # ROE 27% >> k 8%
        ("AKTIA", "tuhoutuva"),      # ROE 9.1% < k 10%
        ("ALMA", "laatu"),           # ROE 19% > k 9%
        ("BITTI", "laatu"),          # ROE 13% > k 10%
        ("CGCBV", "tuhoutuva"),      # ROE 9% < k 10%
        ("CTY1S", "tuhoutuva"),      # ROE 7% << k 10%
        ("ELISA", "laatu"),          # ROE 27% >> k 8%
        ("EQV1V", "laatu"),          # ROE 24% >> k 8%
        ("FIA1S", "tuhoutuva"),      # ROE 9% < k 10%
    ],
)
def test_quality_classification(ticker: str, expected_quality: str) -> None:
    case = next(c for c in EXCEL_PARITY_CASES if c["ticker"] == ticker)
    v = value_stock(
        bvps=case["bvps"], roe=case["roe"],
        k=case["k"], g=case["g"], price=case["price"],
    )
    assert v.quality == expected_quality, (
        f"{ticker}: expected quality={expected_quality!r}, got {v.quality!r}. "
        f"ROE={case['roe']}, k={case['k']}"
    )
