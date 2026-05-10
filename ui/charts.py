"""Time-series chart rendering for QUANT subagent data.

Parses fundamentals + estimates from QUANT's tool_calls, builds Plotly
figures themed to match the Trading-Desk dark UI, and renders them in a
collapsible "📊 Aikasarjat" expander next to LEAD's answer body.

Design choices:
  - One figure per metric (ROE, P/E, EBIT-%, dividend yield, revenue).
  - Multi-line when multiple companies are in the routing (per-company
    persona color from PERSONAS dict).
  - Vertical separator between historical actuals (LFY and earlier)
    and Inderes estimates (LFY+1 onwards).
  - Minimal chrome: no plotly logo, no zoom toolbar, no legend when
    single-company. Background matches `--bg-1` so the chart sits
    flush in the answer card.
  - Tables remain LEAD's responsibility — these charts are *additive*,
    never replace the perussetti tables in Tila C.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Lazy import: plotly is a soft dep (UI-only). The CLI must not crash
# if it isn't installed.
try:
    import plotly.graph_objects as go  # type: ignore
    _PLOTLY_AVAILABLE = True
except ImportError:  # pragma: no cover
    go = None  # type: ignore
    _PLOTLY_AVAILABLE = False

import streamlit as st


# ---------------------------------------------------------------------------
# Metric catalogue
# ---------------------------------------------------------------------------

# Each metric: (label_fi, label_en, axis_format, threshold_for_chart)
# `axis_format`: "percent" → values are decimals (0.18 → 18 %); "euro"
# → currency; "ratio" → plain decimal.
# `min_points`: skip charting if fewer real values are available
# (otherwise a single-point line looks broken).
METRIC_CATALOG: dict[str, dict[str, Any]] = {
    "roe": {
        "label_fi": "Oman pääoman tuotto (ROE)",
        "label_en": "Return on equity (ROE)",
        "axis_format": "percent",
        "min_points": 3,
        "decimals": 1,
    },
    "ebitPercent": {
        "label_fi": "Liiketulos-% (EBIT-%)",
        "label_en": "EBIT margin",
        "axis_format": "percent",
        "min_points": 3,
        "decimals": 1,
    },
    "pe": {
        "label_fi": "P/E-luku",
        "label_en": "P/E ratio",
        "axis_format": "ratio",
        "min_points": 3,
        "decimals": 1,
    },
    "dividendYield": {
        "label_fi": "Osinkotuotto",
        "label_en": "Dividend yield",
        "axis_format": "percent",
        "min_points": 3,
        "decimals": 2,
    },
    "revenue": {
        "label_fi": "Liikevaihto (M€)",
        "label_en": "Revenue (M€)",
        "axis_format": "millions",
        "min_points": 3,
        "decimals": 0,
    },
}

# Per-company colors when multiple are charted side-by-side. Falls back
# to a neutral palette beyond the 6 known personas.
DEFAULT_PALETTE = ["#f5b942", "#5fd28a", "#6aa9ff", "#ff7eb3", "#c294ff", "#FFB85F"]


# ---------------------------------------------------------------------------
# Parsing — extract time-series from QUANT's tool_calls
# ---------------------------------------------------------------------------


def _safe_json_load_inline(text: str) -> Any:
    """Tool result_text is sometimes truncated; try parsing as JSON,
    fall back to None on any decode error so the caller skips that
    series instead of crashing the whole page."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_fundamentals_series(
    tool_call: dict[str, Any],
    company_name_fallback: str | None,
) -> tuple[str | None, dict[str, list[tuple[int, float]]]]:
    """Parse a single `get-fundamentals` result into per-metric year-series.

    Returns (company_name, {metric_name: [(year, value), ...]}). Skips
    null values and quarters > 0 (we only chart annual fundamentals).
    """
    blob = _safe_json_load_inline(tool_call.get("result_text") or "")
    if not isinstance(blob, dict):
        return None, {}
    companies = blob.get("companies") or []
    if not companies:
        return None, {}
    co = companies[0]  # one fundamentals call = one company
    name = co.get("companyName") or company_name_fallback
    transactions = co.get("transactions") or []
    if not transactions:
        return name, {}
    fundamentals = transactions[0].get("fundamentals") or []

    series: dict[str, list[tuple[int, float]]] = {m: [] for m in METRIC_CATALOG}
    for entry in fundamentals:
        if entry.get("quarter") not in (0, None):
            continue  # skip quarterly rows; only chart annual
        year = entry.get("year")
        if not isinstance(year, int):
            continue
        for metric in METRIC_CATALOG:
            value = entry.get(metric)
            if value is None or not isinstance(value, (int, float)):
                continue
            series[metric].append((year, float(value)))
    return name, series


def _extract_estimates_series(
    tool_call: dict[str, Any],
    company_name_fallback: str | None,
) -> tuple[str | None, dict[str, list[tuple[int, float]]]]:
    """Parse a `get-inderes-estimates` result into per-metric year-series.

    Inderes estimate JSON shape:
        {"estimates": {"period": ["2026", "2027"],
                       "pe": [18.72, 16.0],
                       "dividendYield": [0.0429, 0.045]}}
    """
    blob = _safe_json_load_inline(tool_call.get("result_text") or "")
    if not isinstance(blob, dict):
        return None, {}
    companies = blob.get("companies") or []
    if not companies:
        return None, {}
    co = companies[0]
    name = co.get("companyName") or company_name_fallback
    transactions = co.get("transactions") or []
    if not transactions:
        return name, {}
    estimates = transactions[0].get("estimates") or {}
    periods = estimates.get("period") or []

    series: dict[str, list[tuple[int, float]]] = {m: [] for m in METRIC_CATALOG}
    for metric in METRIC_CATALOG:
        values = estimates.get(metric)
        if not isinstance(values, list) or not values:
            continue
        for period_str, value in zip(periods, values):
            if value is None or not isinstance(value, (int, float)):
                continue
            year = _coerce_period_to_year(period_str)
            if year is None:
                continue
            series[metric].append((year, float(value)))
    return name, series


_YEAR_RE = re.compile(r"\d{4}")


def _coerce_period_to_year(period: Any) -> int | None:
    """Estimate periods can be '2026', '2026e', or '2026E' — extract
    the year integer regardless."""
    if isinstance(period, int):
        return period
    if not isinstance(period, str):
        return None
    m = _YEAR_RE.search(period)
    return int(m.group(0)) if m else None


def extract_time_series_from_run(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Walk a run dir's QUANT subagent files, return per-metric series.

    Returned shape:
        {
          "roe": {
            "label": "Oman pääoman tuotto (ROE)",
            "axis_format": "percent",
            "decimals": 1,
            "companies": {
              "Sampo": {
                "actuals": [(2019, 0.18), (2020, 0.05), ...],
                "estimates": [(2026, 0.16), (2027, 0.18)],
              },
            },
          },
          ...
        }

    Metrics with no companies' data are omitted from the result so the
    caller doesn't have to filter empty series.
    """
    result: dict[str, dict[str, Any]] = {}

    for subagent_file in sorted(run_dir.glob("subagent-*-quant.json")):
        try:
            sub = json.loads(subagent_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        company_fallback = sub.get("company")
        for tc in sub.get("tool_calls") or []:
            tool_name = tc.get("name")
            if tool_name == "get-fundamentals":
                name, series = _extract_fundamentals_series(tc, company_fallback)
            elif tool_name == "get-inderes-estimates":
                name, series = _extract_estimates_series(tc, company_fallback)
            else:
                continue
            if not name:
                continue
            for metric, points in series.items():
                if not points:
                    continue
                slot = result.setdefault(metric, {
                    "label": METRIC_CATALOG[metric]["label_fi"],
                    "label_en": METRIC_CATALOG[metric]["label_en"],
                    "axis_format": METRIC_CATALOG[metric]["axis_format"],
                    "decimals": METRIC_CATALOG[metric]["decimals"],
                    "min_points": METRIC_CATALOG[metric]["min_points"],
                    "companies": {},
                })
                co_slot = slot["companies"].setdefault(name, {"actuals": [], "estimates": []})
                # Categorise by tool: get-fundamentals → actuals,
                # get-inderes-estimates → estimates. The list-merge
                # below dedupes by (year) — last one wins, which is
                # fine because both sides are sorted ascending.
                key = "actuals" if tool_name == "get-fundamentals" else "estimates"
                co_slot[key].extend(points)

    # Sort each series by year for stable rendering.
    for slot in result.values():
        for co_slot in slot["companies"].values():
            co_slot["actuals"].sort(key=lambda p: p[0])
            co_slot["estimates"].sort(key=lambda p: p[0])

    return result


# ---------------------------------------------------------------------------
# Rendering — Plotly figures
# ---------------------------------------------------------------------------


def _format_value(value: float, axis_format: str, decimals: int) -> str:
    if axis_format == "percent":
        return f"{value * 100:.{decimals}f} %"
    if axis_format == "euro":
        return f"{value:,.{decimals}f} €"
    if axis_format == "millions":
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"


def _build_figure(
    metric: str,
    slot: dict[str, Any],
    lang: str,
) -> "go.Figure | None":
    """Build a single time-series figure for one metric.

    Skips returning a figure when no company has enough points (per
    METRIC_CATALOG.min_points) — keeps the page clean of stub charts.
    """
    if not _PLOTLY_AVAILABLE:
        return None
    label = slot["label_en"] if lang == "en" else slot["label"]
    decimals = slot["decimals"]
    axis_format = slot["axis_format"]
    min_points = slot["min_points"]

    fig = go.Figure()
    qualifying_companies = 0
    palette_idx = 0
    for company_name, points in slot["companies"].items():
        actuals = points.get("actuals") or []
        estimates = points.get("estimates") or []
        # Skip companies that have too few actual data points to make
        # a meaningful line.
        if len(actuals) < min_points:
            continue
        qualifying_companies += 1

        color = DEFAULT_PALETTE[palette_idx % len(DEFAULT_PALETTE)]
        palette_idx += 1

        # Solid line for actuals — the bulk of the chart.
        years_a = [y for y, _ in actuals]
        values_a = [v for _, v in actuals]
        hover_a = [_format_value(v, axis_format, decimals) for v in values_a]
        fig.add_trace(go.Scatter(
            x=years_a, y=values_a,
            mode="lines+markers",
            name=company_name,
            line=dict(color=color, width=2),
            marker=dict(size=6, color=color),
            hovertemplate=(
                f"<b>{company_name}</b><br>"
                "%{x}: %{customdata}<extra></extra>"
            ),
            customdata=hover_a,
            showlegend=True,
        ))

        # Dashed line + lighter markers for estimates — visually
        # distinct from realised history.
        if estimates:
            # Bridge from last actual to first estimate so the line
            # is continuous on the chart.
            bridge_years = [actuals[-1][0]] + [y for y, _ in estimates]
            bridge_values = [actuals[-1][1]] + [v for _, v in estimates]
            hover_e = [_format_value(v, axis_format, decimals) for v in bridge_values]
            fig.add_trace(go.Scatter(
                x=bridge_years, y=bridge_values,
                mode="lines+markers",
                name=f"{company_name} — ennuste" if lang == "fi" else f"{company_name} — estimate",
                line=dict(color=color, width=2, dash="dot"),
                marker=dict(size=5, color=color, symbol="diamond-open"),
                hovertemplate=(
                    f"<b>{company_name}</b> "
                    f"({'ennuste' if lang == 'fi' else 'estimate'})<br>"
                    "%{x}: %{customdata}<extra></extra>"
                ),
                customdata=hover_e,
                showlegend=False,
            ))

    if qualifying_companies == 0:
        return None

    # Y-axis ticks: percentage shown as 18 % not 0.18
    if axis_format == "percent":
        tickformat = f".{decimals}%"
    elif axis_format == "millions":
        tickformat = f",.{decimals}f"
    else:
        tickformat = f".{decimals}f"

    # Plotly auto-range — Plotly is interactive (drag-select to zoom,
    # double-click to reset, pinch on mobile) so we let the user
    # focus on the part they care about rather than guessing for them.
    # An earlier IQR-clip approach (commit 8db106c) tried to clip
    # outliers from the visible axis but created its own surprises;
    # auto + interactive zoom is more honest.

    show_legend = qualifying_companies > 1
    fig.update_layout(
        title=dict(text=label, font=dict(size=13, color="#e6e8eb"), x=0, xanchor="left"),
        paper_bgcolor="#101216",
        plot_bgcolor="#101216",
        font=dict(family="Iosevka, JetBrains Mono, ui-monospace, monospace",
                  size=11, color="#b6bcc6"),
        margin=dict(l=50, r=20, t=40, b=40),
        height=240,
        hovermode="x unified",
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.35,
            xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            showgrid=True, gridcolor="#232831",
            zeroline=False,
            tickfont=dict(size=10, color="#7a828d"),
            dtick=1,  # one tick per year
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#232831",
            zeroline=False,
            tickfont=dict(size=10, color="#7a828d"),
            tickformat=tickformat,
            # range=None = auto. User pans/zooms interactively.
        ),
    )
    return fig


# NOTE: _compute_smart_y_range is preserved as dead code (not called
# from _build_figure any more). Deleting it would lose the IQR
# implementation if we want to switch back. Kept untested too so its
# behaviour doesn't drift silently.
def _compute_smart_y_range(
    slot: dict[str, Any], axis_format: str,
) -> list[float] | None:
    """Compute a Y-range that focuses on the bulk of the data, clipping
    extreme outliers from the visible axis so the trend reads clearly.

    Trade-off: an outlier year (e.g. UPM 2023 ROE collapse, Sampo 2020
    one-off write-down) used to stretch the auto-axis from -50 % to
    +25 %, squashing the bulk of years into ~5 % of the chart height.
    With the IQR-based clip below, the visible axis focuses on Q1-Q3
    ± 1.5 IQR; outliers OUTSIDE that range are still in the trace
    data — Plotly still lets you hover the year for the actual value
    — but they don't dominate the axis any more.

    Algorithm:
      1. Collect ALL (year, value) tuples across companies + actuals
         + estimates for this metric.
      2. If < 6 total points, fall back to Plotly's auto.
      3. Compute Q1 (25th percentile) and Q3 (75th percentile).
      4. IQR = Q3 - Q1. If IQR ≤ 0 (all values clustered), auto.
      5. Range = [Q1 - 1.5 IQR, Q3 + 1.5 IQR] (Tukey fences).
      6. Tighten when data fits inside the fences (use small padding
         instead of full IQR margin).
      7. Per-format guardrails:
         - percent + all values >= 0 → anchor low at 0
         - percent + outlier negative → keep IQR-based low (clips from
           axis but data is still in trace)

    Returns ``[low, high]`` or ``None`` (= auto).
    """
    all_values: list[float] = []
    for co_slot in slot["companies"].values():
        for _, v in co_slot.get("actuals") or []:
            all_values.append(v)
        for _, v in co_slot.get("estimates") or []:
            all_values.append(v)
    if len(all_values) < 6:
        return None

    sorted_values = sorted(all_values)
    n = len(sorted_values)
    q1 = sorted_values[max(0, int(n * 0.25))]
    q3 = sorted_values[min(n - 1, int(n * 0.75))]
    iqr = q3 - q1
    if iqr <= 0:
        return None  # all values clustered — let auto handle

    # Tukey fences — the standard "outside this is an outlier" range.
    fence_low = q1 - 1.5 * iqr
    fence_high = q3 + 1.5 * iqr

    data_min = sorted_values[0]
    data_max = sorted_values[-1]

    # Tighten: when actual data already lies inside the fences, use
    # a smaller margin so the trace fills the chart instead of
    # floating in the middle.
    pad = iqr * 0.20
    low = fence_low if data_min < fence_low else (data_min - pad)
    high = fence_high if data_max > fence_high else (data_max + pad)

    # Per-format guardrails
    if axis_format == "percent":
        # If data is non-negative AND no outliers below, anchor at 0.
        # Zero is the meaningful baseline for ROE / margin / yield.
        if data_min >= 0 and low > 0:
            low = 0.0
        # Don't go ridiculously high — 60 % is plenty of headroom for
        # any sensible ROE/margin/yield.
        high = min(high, 0.60)
        # Also don't go below -20 % — even a major collapse year
        # past that is "look at the data, not the chart".
        low = max(low, -0.20)

    return [low, high]


# ---------------------------------------------------------------------------
# Public renderer — called from app.py
# ---------------------------------------------------------------------------


def render_time_series_charts(run_dir: Path, lang: str = "fi") -> None:
    """Render a collapsible "📊 Aikasarjat" expander with one chart
    per metric that has enough data.

    Silent no-op when:
      - plotly isn't installed (CLI / test environments)
      - QUANT didn't produce parseable fundamentals
      - no metric has enough qualifying companies (< min_points each)
    """
    if not _PLOTLY_AVAILABLE:
        return
    series_data = extract_time_series_from_run(run_dir)
    if not series_data:
        return

    # Build figures up-front so we know whether the expander has
    # anything worth opening.
    figures: list[tuple[str, "go.Figure"]] = []
    for metric, slot in series_data.items():
        fig = _build_figure(metric, slot, lang)
        if fig is not None:
            figures.append((metric, fig))
    if not figures:
        return

    label = "📊 Aikasarjat" if lang == "fi" else "📊 Time series"
    with st.expander(label, expanded=False):
        for metric, fig in figures:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                    "responsive": True,
                    "scrollZoom": False,
                },
                key=f"chart-{run_dir.name}-{metric}",
            )
