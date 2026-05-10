"""Tests for the Plotly time-series chart pipeline.

Two layers covered:

1. Parsing — `extract_time_series_from_run` walks a synthetic run dir
   with stub `subagent-*-quant.json` files, asserts that fundamentals
   and estimates land in the right buckets per company per metric.

2. Figure construction — `_build_figure` is exercised on synthetic
   slot dicts to verify that:
     - companies with too few actuals are skipped (min_points)
     - both actual + estimate traces appear when estimates exist
     - the estimate "bridge" connects last actual → first estimate
     - empty-everything → returns None (skip the chart)

The chart renderer itself (`render_time_series_charts`) is NOT
exercised via pytest because Streamlit's runtime context isn't
available — that path is verified manually in the live UI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ui/ is not on the package path under pytest.
_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from charts import (  # noqa: E402
    METRIC_CATALOG,
    _build_figure,
    _coerce_period_to_year,
    _filter_ratio_outliers,
    extract_time_series_from_run,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal valid quant subagent JSON
# ---------------------------------------------------------------------------


def _fundamentals_blob(company_name: str, fundamentals: list[dict]) -> str:
    """Build a JSON-string mimicking get-fundamentals' wire format
    (single-company case)."""
    return json.dumps({
        "companies": [{
            "companyId": "COMPANY:1",
            "companyName": company_name,
            "transactions": [{
                "transactionDate": "2026-05-06T00:00:00Z",
                "transactionId": "test",
                "fundamentals": fundamentals,
            }],
        }],
    })


def _fundamentals_blob_multi(
    items: list[tuple[str, list[dict]]],
) -> str:
    """Build a multi-company get-fundamentals response — agent
    sometimes batches `companyIds=[a,b]` into one call. Each
    `(name, fundamentals)` tuple becomes its own companies[] entry."""
    return json.dumps({
        "companies": [
            {
                "companyId": f"COMPANY:{idx + 1}",
                "companyName": name,
                "transactions": [{
                    "transactionDate": "2026-05-06T00:00:00Z",
                    "transactionId": f"test-{idx}",
                    "fundamentals": fundamentals,
                }],
            }
            for idx, (name, fundamentals) in enumerate(items)
        ],
    })


def _estimates_blob(company_name: str, periods: list[str], **metric_lists) -> str:
    """Build a JSON-string mimicking get-inderes-estimates."""
    return json.dumps({
        "companies": [{
            "companyId": "COMPANY:1",
            "companyName": company_name,
            "transactions": [{
                "transactionDate": "2026-05-06T00:00:00Z",
                "estimates": {
                    "period": periods,
                    **metric_lists,
                },
            }],
        }],
    })


def _write_quant_subagent(run_dir: Path, tool_calls: list[dict]) -> None:
    """Drop a subagent-01-quant.json file into run_dir."""
    blob = {
        "index": 1,
        "domain": "quant",
        "company": None,
        "model_used": "test-model",
        "error": None,
        "text": "test",
        "tool_calls": tool_calls,
    }
    (run_dir / "subagent-01-quant.json").write_text(
        json.dumps(blob), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _coerce_period_to_year
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inp,expected", [
    ("2026", 2026),
    ("2026e", 2026),
    ("2026E", 2026),
    (2026, 2026),
    ("Q1/2026", 2026),  # extracts the year
    ("garbage", None),
    (None, None),
    ([], None),
])
def test_coerce_period_to_year(inp, expected):
    assert _coerce_period_to_year(inp) == expected


# ---------------------------------------------------------------------------
# extract_time_series_from_run — fundamentals path
# ---------------------------------------------------------------------------


def test_extract_fundamentals_into_actuals(tmp_path):
    """A simple Sampo fundamentals call should produce ROE actuals."""
    fundamentals = [
        {"year": 2021, "quarter": 0, "roe": 0.12, "pe": 14.0},
        {"year": 2022, "quarter": 0, "roe": 0.15, "pe": 16.5},
        {"year": 2023, "quarter": 0, "roe": 0.18, "pe": 18.2},
        {"year": 2024, "quarter": 0, "roe": 0.20, "pe": 17.0},
        {"year": 2025, "quarter": 0, "roe": 0.17, "pe": 16.0},
    ]
    _write_quant_subagent(tmp_path, [{
        "name": "get-fundamentals",
        "arguments": {"companyIds": ["COMPANY:1"]},
        "result_text": _fundamentals_blob("Sampo", fundamentals),
    }])

    result = extract_time_series_from_run(tmp_path)
    assert "roe" in result
    assert "pe" in result
    sampo_roe = result["roe"]["companies"]["Sampo"]
    assert sampo_roe["actuals"] == [
        (2021, 0.12), (2022, 0.15), (2023, 0.18), (2024, 0.20), (2025, 0.17),
    ]
    assert sampo_roe["estimates"] == []  # estimates not present in this call


def test_extract_skips_quarterly_rows(tmp_path):
    """Only annual rows (quarter=0) should land in actuals."""
    fundamentals = [
        {"year": 2024, "quarter": 0, "roe": 0.20},
        {"year": 2025, "quarter": 1, "roe": 0.18},  # Q1 — should skip
        {"year": 2025, "quarter": 0, "roe": 0.17},
    ]
    _write_quant_subagent(tmp_path, [{
        "name": "get-fundamentals", "arguments": {},
        "result_text": _fundamentals_blob("Sampo", fundamentals),
    }])
    result = extract_time_series_from_run(tmp_path)
    assert result["roe"]["companies"]["Sampo"]["actuals"] == [
        (2024, 0.20), (2025, 0.17),
    ]


def test_extract_skips_null_metric_values(tmp_path):
    """A `null` value (Inderes' way of saying "not reported") must
    NOT appear as a (year, None) tuple in the output."""
    fundamentals = [
        {"year": 2023, "quarter": 0, "roe": None, "pe": 12.0},
        {"year": 2024, "quarter": 0, "roe": 0.18, "pe": 14.0},
        {"year": 2025, "quarter": 0, "roe": 0.20, "pe": None},
    ]
    _write_quant_subagent(tmp_path, [{
        "name": "get-fundamentals", "arguments": {},
        "result_text": _fundamentals_blob("Sampo", fundamentals),
    }])
    result = extract_time_series_from_run(tmp_path)
    # ROE has years 2024+2025 (2023 was null)
    assert result["roe"]["companies"]["Sampo"]["actuals"] == [(2024, 0.18), (2025, 0.20)]
    # P/E has 2023+2024 (2025 was null)
    assert result["pe"]["companies"]["Sampo"]["actuals"] == [(2023, 12.0), (2024, 14.0)]


# ---------------------------------------------------------------------------
# extract_time_series_from_run — estimates path
# ---------------------------------------------------------------------------


def test_extract_estimates_into_estimate_bucket(tmp_path):
    _write_quant_subagent(tmp_path, [{
        "name": "get-inderes-estimates",
        "arguments": {},
        "result_text": _estimates_blob(
            "Sampo", ["2026", "2027"],
            pe=[18.7, 16.0],
            dividendYield=[0.043, 0.045],
        ),
    }])
    result = extract_time_series_from_run(tmp_path)
    sampo_pe = result["pe"]["companies"]["Sampo"]
    assert sampo_pe["estimates"] == [(2026, 18.7), (2027, 16.0)]
    assert sampo_pe["actuals"] == []


def test_extract_combines_fundamentals_and_estimates(tmp_path):
    """A single QUANT subagent typically calls both — they should
    merge into the same per-company slot."""
    _write_quant_subagent(tmp_path, [
        {
            "name": "get-fundamentals", "arguments": {},
            "result_text": _fundamentals_blob("Sampo", [
                {"year": 2024, "quarter": 0, "pe": 14.0},
                {"year": 2025, "quarter": 0, "pe": 16.0},
            ]),
        },
        {
            "name": "get-inderes-estimates", "arguments": {},
            "result_text": _estimates_blob("Sampo", ["2026", "2027"], pe=[18.0, 17.0]),
        },
    ])
    result = extract_time_series_from_run(tmp_path)
    sampo_pe = result["pe"]["companies"]["Sampo"]
    assert sampo_pe["actuals"] == [(2024, 14.0), (2025, 16.0)]
    assert sampo_pe["estimates"] == [(2026, 18.0), (2027, 17.0)]


# ---------------------------------------------------------------------------
# extract_time_series_from_run — multi-company (comparison)
# ---------------------------------------------------------------------------


def test_extract_multi_company_in_one_batched_call(tmp_path):
    """Regression for the comparison-chart-only-shows-one-company
    bug (2026-05-10). QUANT subagents in comparison fan-outs
    sometimes batch `companyIds=[a, b]` into a single
    get-fundamentals call. The response then has TWO entries in
    `companies[]` — the parser must extract both, not just companies[0]."""
    _write_quant_subagent(tmp_path, [{
        "name": "get-fundamentals",
        "arguments": {"companyIds": ["COMPANY:1", "COMPANY:2"]},
        "result_text": _fundamentals_blob_multi([
            ("Nordea Bank", [
                {"year": 2023, "quarter": 0, "roe": 0.16},
                {"year": 2024, "quarter": 0, "roe": 0.15},
                {"year": 2025, "quarter": 0, "roe": 0.14},
            ]),
            ("Sampo", [
                {"year": 2023, "quarter": 0, "roe": 0.18},
                {"year": 2024, "quarter": 0, "roe": 0.20},
                {"year": 2025, "quarter": 0, "roe": 0.17},
            ]),
        ]),
    }])
    result = extract_time_series_from_run(tmp_path)
    assert "roe" in result
    roe_companies = set(result["roe"]["companies"].keys())
    # Both companies must appear, not just companies[0]
    assert roe_companies == {"Nordea Bank", "Sampo"}
    assert result["roe"]["companies"]["Nordea Bank"]["actuals"] == [
        (2023, 0.16), (2024, 0.15), (2025, 0.14),
    ]
    assert result["roe"]["companies"]["Sampo"]["actuals"] == [
        (2023, 0.18), (2024, 0.20), (2025, 0.17),
    ]


def test_extract_multi_company_each_in_own_bucket(tmp_path):
    """Comparison run = multiple QUANT subagents (per-company fan-out).
    Each company's data should land in its own slot under the metric."""
    blob_sampo = {
        "index": 1, "domain": "quant", "company": "Sampo",
        "model_used": "x", "error": None, "text": "x",
        "tool_calls": [{
            "name": "get-fundamentals", "arguments": {},
            "result_text": _fundamentals_blob("Sampo", [
                {"year": 2023, "quarter": 0, "roe": 0.18},
                {"year": 2024, "quarter": 0, "roe": 0.20},
                {"year": 2025, "quarter": 0, "roe": 0.17},
            ]),
        }],
    }
    blob_nordea = {
        "index": 2, "domain": "quant", "company": "Nordea",
        "model_used": "x", "error": None, "text": "x",
        "tool_calls": [{
            "name": "get-fundamentals", "arguments": {},
            "result_text": _fundamentals_blob("Nordea", [
                {"year": 2023, "quarter": 0, "roe": 0.16},
                {"year": 2024, "quarter": 0, "roe": 0.15},
                {"year": 2025, "quarter": 0, "roe": 0.14},
            ]),
        }],
    }
    (tmp_path / "subagent-01-quant.json").write_text(
        json.dumps(blob_sampo), encoding="utf-8"
    )
    (tmp_path / "subagent-02-quant.json").write_text(
        json.dumps(blob_nordea), encoding="utf-8"
    )

    result = extract_time_series_from_run(tmp_path)
    roe_companies = set(result["roe"]["companies"].keys())
    assert roe_companies == {"Sampo", "Nordea"}
    assert result["roe"]["companies"]["Sampo"]["actuals"] == [
        (2023, 0.18), (2024, 0.20), (2025, 0.17),
    ]
    assert result["roe"]["companies"]["Nordea"]["actuals"] == [
        (2023, 0.16), (2024, 0.15), (2025, 0.14),
    ]


# ---------------------------------------------------------------------------
# extract_time_series_from_run — defensive
# ---------------------------------------------------------------------------


def test_extract_handles_corrupt_json_gracefully(tmp_path):
    """A subagent file with invalid JSON shouldn't kill the parser —
    just skip that file."""
    (tmp_path / "subagent-01-quant.json").write_text(
        "not json at all { bad", encoding="utf-8"
    )
    # Should not raise
    result = extract_time_series_from_run(tmp_path)
    assert result == {}


def test_extract_handles_empty_run_dir(tmp_path):
    """No subagent files → empty result, no crash."""
    assert extract_time_series_from_run(tmp_path) == {}


def test_extract_skips_non_quant_subagents(tmp_path):
    """research/sentiment/etc. files are NOT walked — only quant has
    fundamentals/estimates time series."""
    research_blob = {
        "index": 1, "domain": "research", "company": None,
        "model_used": "x", "error": None, "text": "x",
        "tool_calls": [{
            "name": "get-fundamentals",  # would technically have data
            "arguments": {},
            "result_text": _fundamentals_blob("Sampo", [
                {"year": 2025, "quarter": 0, "roe": 0.17},
            ]),
        }],
    }
    (tmp_path / "subagent-01-research.json").write_text(
        json.dumps(research_blob), encoding="utf-8"
    )
    assert extract_time_series_from_run(tmp_path) == {}


# ---------------------------------------------------------------------------
# _build_figure — gating + structure
# ---------------------------------------------------------------------------


def test_build_figure_skips_companies_below_min_points():
    """Sampo with only 2 actuals (min_points=3 for ROE) should be
    excluded from the figure entirely."""
    slot = {
        "label": "ROE", "label_en": "ROE",
        "axis_format": "percent", "decimals": 1, "min_points": 3,
        "companies": {
            "Sampo": {"actuals": [(2024, 0.20), (2025, 0.17)], "estimates": []},
        },
    }
    fig = _build_figure("roe", slot, lang="fi")
    # No qualifying companies → no figure
    assert fig is None


def test_build_figure_includes_company_with_enough_points():
    slot = {
        "label": "ROE", "label_en": "ROE",
        "axis_format": "percent", "decimals": 1, "min_points": 3,
        "companies": {
            "Sampo": {
                "actuals": [(2023, 0.18), (2024, 0.20), (2025, 0.17)],
                "estimates": [],
            },
        },
    }
    fig = _build_figure("roe", slot, lang="fi")
    assert fig is not None
    # Exactly one trace (actuals only — no estimates)
    assert len(fig.data) == 1
    assert fig.data[0].name == "Sampo"


def test_build_figure_adds_estimate_trace_when_present():
    slot = {
        "label": "P/E", "label_en": "P/E",
        "axis_format": "ratio", "decimals": 1, "min_points": 3,
        "companies": {
            "Sampo": {
                "actuals": [(2023, 12.0), (2024, 14.0), (2025, 16.0)],
                "estimates": [(2026, 18.0), (2027, 17.0)],
            },
        },
    }
    fig = _build_figure("pe", slot, lang="fi")
    assert fig is not None
    # Two traces: actuals + estimate-bridge
    assert len(fig.data) == 2
    estimate_trace = fig.data[1]
    # Bridge should start at last actual year (2025) for visual continuity
    assert estimate_trace.x[0] == 2025
    assert estimate_trace.x[-1] == 2027


def test_build_figure_assigns_distinct_colors_to_companies():
    slot = {
        "label": "ROE", "label_en": "ROE",
        "axis_format": "percent", "decimals": 1, "min_points": 3,
        "companies": {
            "Sampo": {
                "actuals": [(2023, 0.18), (2024, 0.20), (2025, 0.17)],
                "estimates": [],
            },
            "Nordea": {
                "actuals": [(2023, 0.16), (2024, 0.15), (2025, 0.14)],
                "estimates": [],
            },
        },
    }
    fig = _build_figure("roe", slot, lang="fi")
    assert fig is not None
    assert len(fig.data) == 2
    # Distinct colors
    color_a = fig.data[0].line.color
    color_b = fig.data[1].line.color
    assert color_a != color_b


# ---------------------------------------------------------------------------
# _filter_ratio_outliers — P/E spike handling
# ---------------------------------------------------------------------------


def test_ratio_outliers_filters_500x_spike():
    """User report (Sampo 2020 P/E = 500): one extreme year ruins the
    chart. Median-based filter drops anything > 5× median."""
    points = [
        (2019, 14.5),
        (2020, 500.0),  # COVID-year earnings collapse → division artefact
        (2021, 16.0),
        (2022, 17.5),
        (2023, 14.0),
        (2024, 13.5),
    ]
    filtered = _filter_ratio_outliers(points)
    years_kept = [y for y, _ in filtered]
    assert 2020 not in years_kept
    # Real history preserved
    assert {2019, 2021, 2022, 2023, 2024} == set(years_kept)


def test_ratio_outliers_keeps_normal_history_intact():
    """Series of typical P/E values 12-25 → no filtering."""
    points = [
        (2020, 14.0), (2021, 16.0), (2022, 18.0),
        (2023, 22.0), (2024, 25.0), (2025, 19.0),
    ]
    filtered = _filter_ratio_outliers(points)
    assert filtered == points  # untouched


def test_ratio_outliers_too_few_points_no_filter():
    """Below 4 points, can't compute a stable median — no filter."""
    points = [(2024, 14.0), (2025, 500.0)]
    filtered = _filter_ratio_outliers(points)
    assert filtered == points


def test_ratio_outliers_zero_median_no_filter():
    """All-zero series shouldn't produce a divide-by-zero crash."""
    points = [(2020, 0.0), (2021, 0.0), (2022, 0.0), (2023, 0.0)]
    filtered = _filter_ratio_outliers(points)
    assert filtered == points


# ---------------------------------------------------------------------------
# Smoke: METRIC_CATALOG sanity
# ---------------------------------------------------------------------------


def test_metric_catalog_has_expected_entries():
    """Lock the canonical metric set so a casual rename of a key
    doesn't silently break the chart pipeline."""
    expected = {"roe", "ebitPercent", "pe", "dividendYield", "revenue"}
    assert set(METRIC_CATALOG.keys()) == expected
    for spec in METRIC_CATALOG.values():
        assert "label_fi" in spec
        assert "label_en" in spec
        assert spec["axis_format"] in {"percent", "ratio", "euro", "millions"}
        assert spec["min_points"] >= 2
