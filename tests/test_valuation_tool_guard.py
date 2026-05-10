"""Tool-call guard for the valuation pipeline — regression suite.

Background: in production run ``20260508-205057-769`` ("entäs jos roe olisi
13%") the ``aino-valuation`` agent emitted a complete-looking JSON output
**without making a single MCP call**. Flash Lite decided the prior turn's
context was "enough" and hallucinated:

  - wrong company_id (``COMPANY:345`` instead of the real ``COMPANY:382``)
  - invented price (12.85€ vs the actual 16.09€)
  - fabricated ROE history that conveniently produced 5y_median = 13%

The deterministic engine math then operated on these phantom inputs and
produced a +18.2% safety margin shown to the user. The visible artifact
was honest-looking; the foundation was air.

The guard added in ``synthesis._process_valuation_subagents`` rejects any
VALUATION subagent output that has zero ``get-fundamentals`` calls — the
load-bearing tool for BVPS / ROE / price. These tests pin that behavior
so it can't silently regress.
"""

from __future__ import annotations

from inderes_agent.observability.output_parts import ToolCallTrace
from inderes_agent.orchestration.router import Domain, QueryClassification
from inderes_agent.orchestration.synthesis import _process_valuation_subagents
from inderes_agent.orchestration.workflows import SubagentResult, WorkflowResult

# ── Fixture: realistic JSON output that LOOKS valid but has no MCP backing ──
# Mirrors the Q2 ("entäs jos roe olisi 13%") production hallucination.
HALLUCINATED_AGENT_TEXT = """\
**Ajatus:** Käytän manual_override-asetusta ja asetan ROE:ksi 0.13.

```json
{
  "company": "Nordea Bank Abp",
  "company_id": "COMPANY:345",
  "ticker": "NDA FI",
  "bvps": 9.42,
  "bvps_date": "2025-12-31",
  "price": 12.85,
  "price_date": "2026-05-08",
  "roe_used": 0.13,
  "roe_version": "manual_override",
  "roe_history": {
    "raw": [[2021, 0.08], [2022, 0.11], [2023, 0.15], [2024, 0.14], [2025, 0.13]],
    "lfy": 0.13,
    "3y_median": 0.14,
    "5y_median": 0.13,
    "trend_weighted": 0.135,
    "trend_label": "vakaa"
  },
  "k": 0.09,
  "k_rationale": "Pankkisektorin keskimääräinen tuottovaatimus.",
  "g": 0.03,
  "g_rationale": "Maltillinen nominaalinen kasvu.",
  "roe_rationale": "Käyttäjän pyytämä manuaalinen taso.",
  "warnings": ["ROE-taso on asetettu manuaalisesti."]
}
```
"""


def _make_workflow(tool_calls: list[ToolCallTrace]) -> WorkflowResult:
    """Build a minimal WorkflowResult around one valuation subagent."""
    sr = SubagentResult(
        domain=Domain.VALUATION,
        company="Nordea",
        text=HALLUCINATED_AGENT_TEXT,
        model_used="gemini-3.1-flash-lite-preview",
        tool_calls=tool_calls,
    )
    classification = QueryClassification(
        domains=[Domain.VALUATION],
        companies=["Nordea"],
        is_comparison=False,
        reasoning="test",
    )
    return WorkflowResult(classification=classification, subagent_results=[sr])


# ─────────────────────────────────────────────────────────────────────────────
# Reject branch: agent skipped MCP entirely (Q2 production failure mode)
# ─────────────────────────────────────────────────────────────────────────────


def test_zero_tool_calls_rejected_as_hallucination() -> None:
    """The exact Q2 failure mode: valid-looking JSON, zero tool calls."""
    workflow = _make_workflow(tool_calls=[])
    records = _process_valuation_subagents(workflow)

    assert len(records) == 1
    rec = records[0]
    assert rec.parse_error is not None
    # Error message names the missing call so the LEAD prompt's Tila B
    # rendering surfaces a meaningful reason — not a generic "parse failed".
    assert "get-fundamentals" in rec.parse_error
    # Engine must NOT have run — fabricated inputs would have produced
    # a fair value that then misled the user.
    assert rec.valuation is None
    assert rec.agent_output is None


def test_only_search_companies_still_rejected() -> None:
    """search-companies returns IDs only, not BVPS/ROE/price.

    An agent that did just search-companies (no fundamentals) still
    couldn't have produced a real valuation — the JSON's numeric fields
    are necessarily invented. Guard must catch this too.
    """
    workflow = _make_workflow(tool_calls=[
        ToolCallTrace(name="search-companies", arguments={"query": "Nordea"}),
    ])
    records = _process_valuation_subagents(workflow)
    assert len(records) == 1
    assert records[0].parse_error is not None
    assert "get-fundamentals" in records[0].parse_error


def test_rejected_record_carries_raw_text_for_forensics() -> None:
    """Run-log writes the raw agent text on parse_error so we can forensically
    diff hallucinations against future fixes. Pin the contract."""
    workflow = _make_workflow(tool_calls=[])
    records = _process_valuation_subagents(workflow)
    assert records[0].raw_text == HALLUCINATED_AGENT_TEXT


# ─────────────────────────────────────────────────────────────────────────────
# Accept branch: at least one get-fundamentals call → guard passes through
# ─────────────────────────────────────────────────────────────────────────────


def test_one_fundamentals_call_passes_guard() -> None:
    """Guard only blocks the no-MCP case. With ≥1 get-fundamentals it should
    pass through to the parser — the parser itself decides validity from there."""
    workflow = _make_workflow(tool_calls=[
        ToolCallTrace(name="search-companies", arguments={"query": "Nordea"}),
        ToolCallTrace(
            name="get-fundamentals",
            arguments={"companyIds": ["COMPANY:382"], "fields": ["roe"]},
        ),
    ])
    records = _process_valuation_subagents(workflow)

    # Guard passes; parser then runs. The hallucinated JSON in the fixture
    # has manual_override (which bypasses sustainable-ROE rule validation),
    # so parser accepts it. This is fine — the guard's job was only to
    # ensure SOMETHING was fetched. We don't assert engine success here
    # because the fixture's bvps=9.42 / price=12.85 will produce a valid
    # Valuation regardless of MCP backing — the guard cannot tell whether
    # those numbers MATCH MCP, only whether MCP was queried.
    assert len(records) == 1
    rec = records[0]
    # Parser should have succeeded (manual_override + valid numeric fields)
    assert rec.parse_error is None
    assert rec.agent_output is not None
    assert rec.agent_output.roe_used == 0.13
    assert rec.valuation is not None  # engine ran successfully


def test_multiple_fundamentals_calls_pass() -> None:
    """The new 2-call pattern (Fix B): one for ROE/pb/marketCap/sharesTotal,
    one for sharePrice without year range. Both fundamentals — guard happy."""
    workflow = _make_workflow(tool_calls=[
        ToolCallTrace(name="search-companies", arguments={"query": "Nordea"}),
        ToolCallTrace(
            name="get-fundamentals",
            arguments={
                "companyIds": ["COMPANY:382"],
                "fields": ["roe", "pb", "marketCap", "sharesTotal"],
                "startYear": 2021,
                "endYear": 2025,
            },
        ),
        ToolCallTrace(
            name="get-fundamentals",
            arguments={
                "companyIds": ["COMPANY:382"],
                "fields": ["sharePrice"],
            },
        ),
    ])
    records = _process_valuation_subagents(workflow)
    assert len(records) == 1
    assert records[0].parse_error is None
    assert records[0].valuation is not None


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_agent_error_takes_precedence_over_guard() -> None:
    """If the subagent itself errored before producing output, that error
    message should reach the run-log — not the tool-guard's message.

    Both paths produce a parse_error, but the original error is more
    diagnostic than "0 fundamentals calls" (the agent never had a chance
    to make calls before erroring).
    """
    sr = SubagentResult(
        domain=Domain.VALUATION,
        company="Nordea",
        text="",
        model_used="gemini-3.1-flash-lite-preview",
        tool_calls=[],  # zero, but...
        error="API rate limit exceeded",  # ...the real cause
    )
    classification = QueryClassification(
        domains=[Domain.VALUATION], companies=["Nordea"],
        is_comparison=False, reasoning="test",
    )
    workflow = WorkflowResult(classification=classification, subagent_results=[sr])
    records = _process_valuation_subagents(workflow)

    assert len(records) == 1
    assert "API rate limit" in records[0].parse_error
    assert "get-fundamentals" not in records[0].parse_error


def test_non_valuation_subagents_unaffected() -> None:
    """The guard is valuation-specific. quant/research subagents that
    legitimately make zero MCP calls (e.g., conceptual questions) must
    not be filtered."""
    quant_sr = SubagentResult(
        domain=Domain.QUANT, company="Nordea",
        text="some text", model_used="gemini-3.1-flash-lite-preview",
        tool_calls=[],  # zero — but this is QUANT, not VALUATION
    )
    classification = QueryClassification(
        domains=[Domain.QUANT], companies=["Nordea"],
        is_comparison=False, reasoning="test",
    )
    workflow = WorkflowResult(
        classification=classification, subagent_results=[quant_sr],
    )
    records = _process_valuation_subagents(workflow)
    # Guard processes only VALUATION domain — quant subagent ignored entirely.
    assert records == []


# ─────────────────────────────────────────────────────────────────────────────
# Edge-case warnings in _format_valuation_block
#
# Surfaced from production run 20260508-221645-249 (Bittium manual override
# ROE 5%): the engine math was correct but the resulting -3155% safety
# margin was presented as a confident verdict in the UI. The block
# formatter now flags absurd margins with ⚠️ HUOM REUNATAPAUS so LEAD
# softens the takeaway in synthesis.
# ─────────────────────────────────────────────────────────────────────────────


def test_format_block_flags_extreme_negative_margin() -> None:
    """When safety_margin < -100% (price >> FV), block must include a
    REUNATAPAUS warning so LEAD doesn't present the absurd number as a
    confident verdict.

    Reproduces the Bittium-with-ROE-5% scenario: stock priced for
    ~13% ROE, model fed manual_override 5%, FV collapses to 0.92€ vs
    real price 29.95€ → safety_margin -3155%. UX without warning would
    show a confident "buy at 0.83€" entry level.
    """
    from inderes_agent.orchestration.synthesis import (
        ValuationRecord,
        _format_valuation_block,
    )
    from inderes_agent.valuation import value_stock
    from inderes_agent.valuation.parser import ValuationAgentOutput

    v = value_stock(bvps=3.68, roe=0.05, k=0.11, g=0.03, price=29.95)
    assert v.safety_margin_to_fv_pct < -100  # sanity: this IS extreme

    agent_output = ValuationAgentOutput(
        company="Bittium",
        company_id="COMPANY:1", ticker="BITTI",
        bvps=3.68, bvps_date="2025-12-31",
        price=29.95, price_date="2026-05-09",
        roe_used=0.05, k=0.11, g=0.03,
        roe_version="manual_override",
        roe_history={"raw": [], "trend_label": "vakaa"},
        roe_rationale="manual override test",
        k_rationale="tech sector",
        g_rationale="mature",
    )
    rec = ValuationRecord(
        company="Bittium", agent_output=agent_output, valuation=v,
    )
    block = _format_valuation_block([rec])
    assert "REUNATAPAUS" in block
    assert "epärealistinen" in block.lower() or "epäsuhdassa" in block.lower()


def test_format_block_flags_tuhoutuva_with_manual_override() -> None:
    """Even when |margin| ≤ 100%, a 'tuhoutuva' classification combined
    with manual_override deserves a softer warning — the user-imposed ROE
    caused the verdict, not an objective observation."""
    from inderes_agent.orchestration.synthesis import (
        ValuationRecord,
        _format_valuation_block,
    )
    from inderes_agent.valuation import value_stock
    from inderes_agent.valuation.parser import ValuationAgentOutput

    # Pick parameters where margin stays mild but quality is tuhoutuva.
    # ROE 7% < k 10% → tuhoutuva, but price near FV → margin moderate.
    v = value_stock(bvps=10.0, roe=0.07, k=0.10, g=0.05, price=4.0)
    assert v.quality == "tuhoutuva"
    assert -100 <= v.safety_margin_to_fv_pct <= 100  # not extreme

    agent_output = ValuationAgentOutput(
        company="TestCo",
        company_id=None, ticker=None,
        bvps=10.0, bvps_date=None,
        price=4.0, price_date=None,
        roe_used=0.07, k=0.10, g=0.05,
        roe_version="manual_override",
        roe_history={"raw": [], "trend_label": "vakaa"},
        roe_rationale="manual override test",
        k_rationale="test", g_rationale="test",
    )
    rec = ValuationRecord(
        company="TestCo", agent_output=agent_output, valuation=v,
    )
    block = _format_valuation_block([rec])
    # Should warn about manual-override + tuhoutuva combination
    assert "manuaalisesta" in block or "manual" in block.lower()
    assert "tuhoutuva" in block.lower() or "skenaario" in block.lower()


def test_format_block_no_warning_for_normal_case() -> None:
    """Normal valuation (laatu, modest margin) must NOT include a warning —
    we don't want noise on every output."""
    from inderes_agent.orchestration.synthesis import (
        ValuationRecord,
        _format_valuation_block,
    )
    from inderes_agent.valuation import value_stock
    from inderes_agent.valuation.parser import ValuationAgentOutput

    v = value_stock(bvps=9.41, roe=0.15, k=0.09, g=0.04, price=16.09)
    assert v.quality == "laatu"
    assert -100 <= v.safety_margin_to_fv_pct <= 100  # normal range

    agent_output = ValuationAgentOutput(
        company="Nordea",
        company_id="COMPANY:382", ticker="NDA",
        bvps=9.41, bvps_date="2025-12-31",
        price=16.09, price_date="2026-05-09",  # = today, fresh
        roe_used=0.15, k=0.09, g=0.04,
        roe_version="5y_median",
        roe_history={"raw": [[2021, 0.15]], "trend_label": "vakaa"},
        roe_rationale="stable",
        k_rationale="bank sector",
        g_rationale="GDP",
    )
    rec = ValuationRecord(
        company="Nordea", agent_output=agent_output, valuation=v,
    )
    block = _format_valuation_block([rec])
    assert "REUNATAPAUS" not in block
    # No "manuaalinen ROE-override" warning either (5y_median was used)
    assert "manuaalisesta ROE-overridesta" not in block


# ─────────────────────────────────────────────────────────────────────────────
# Price-freshness warnings
#
# Inderes MCP does not expose intraday quotes — the freshest available price
# is `get-inderes-estimates.sharePrice` with a `transactionDate` that's
# typically 1-3 weeks old (Inderes refreshes their dataset on cron). When
# that date drifts further, the price-vs-FV comparison can be meaningfully
# misleading, so the synthesis block warns the user transparently.
#
# Tiers:
#   ≤ 30 days  → no warning (effectively current)
#   31-90 days → ℹ️ informational note about refresh cycle
#   > 90 days  → ⚠️ explicit "vanhentunut, mainitse käyttäjälle" guard
# ─────────────────────────────────────────────────────────────────────────────


def _make_record_with_price_date(price_date: str):
    """Helper to build a minimal ValuationRecord with a specific price_date."""
    from inderes_agent.orchestration.synthesis import ValuationRecord
    from inderes_agent.valuation import value_stock
    from inderes_agent.valuation.parser import ValuationAgentOutput
    v = value_stock(bvps=9.41, roe=0.15, k=0.09, g=0.04, price=16.09)
    agent_output = ValuationAgentOutput(
        company="Nordea", company_id="COMPANY:382", ticker="NDA",
        bvps=9.41, bvps_date="2025-12-31",
        price=16.09, price_date=price_date,
        roe_used=0.15, k=0.09, g=0.04,
        roe_version="5y_median",
        roe_history={"raw": [[2021, 0.15]], "trend_label": "vakaa"},
        roe_rationale="r", k_rationale="k", g_rationale="g",
    )
    return ValuationRecord(company="Nordea", agent_output=agent_output, valuation=v)


def test_price_freshness_disclaimer_always_emitted_for_recent_price() -> None:
    """Even ≤ 30 days old, the disclaimer is always emitted (Inderes MCP
    has no real-time price). The user must always know the price is not
    live and what date it's from."""
    from datetime import date, timedelta

    from inderes_agent.orchestration.synthesis import _format_valuation_block
    fresh = (date.today() - timedelta(days=5)).isoformat()
    rec = _make_record_with_price_date(fresh)
    block = _format_valuation_block([rec])
    # Always says "Kurssin lähde" or stronger
    assert "Kurssin lähde" in block or "VANHENTUNUT" in block
    # Always tells LEAD to surface the date + advise live-check
    assert "live-hinta" in block.lower()
    assert "inderes.fi" in block.lower()


def test_price_freshness_info_note_at_30_to_90_days() -> None:
    """31-90 days old → ℹ️ KURSSI HIEMAN VANHENTUNUT (heightened tone)."""
    from datetime import date, timedelta

    from inderes_agent.orchestration.synthesis import _format_valuation_block
    age = (date.today() - timedelta(days=45)).isoformat()
    rec = _make_record_with_price_date(age)
    block = _format_valuation_block([rec])
    assert "HIEMAN VANHENTUNUT" in block
    assert "45 pv vanha" in block


def test_price_freshness_strong_warning_over_90_days() -> None:
    """>90 days → ⚠️ MERKITTÄVÄSTI VANHENTUNUT, must mention age in days."""
    from datetime import date, timedelta

    from inderes_agent.orchestration.synthesis import _format_valuation_block
    age = (date.today() - timedelta(days=120)).isoformat()
    rec = _make_record_with_price_date(age)
    block = _format_valuation_block([rec])
    assert "MERKITTÄVÄSTI VANHENTUNUT" in block
    assert "120 pv vanha" in block


def test_price_freshness_handles_iso_datetime() -> None:
    """price_date may arrive as full ISO datetime (e.g. directly from
    Inderes' transactionDate field). The helper must extract the date
    portion correctly.
    """
    from datetime import date, timedelta

    from inderes_agent.orchestration.synthesis import _format_valuation_block
    # 60 days old, with a full ISO datetime suffix
    age_date = (date.today() - timedelta(days=60)).isoformat()
    iso_datetime = f"{age_date}T16:17:30.000Z"
    rec = _make_record_with_price_date(iso_datetime)
    block = _format_valuation_block([rec])
    assert "HIEMAN VANHENTUNUT" in block  # info-level warning fires


def test_price_freshness_handles_missing_or_unparseable() -> None:
    """Empty / None / garbage price_date returns None (no disclaimer to
    avoid spurious "X pv vanha" messages on missing data)."""
    from inderes_agent.orchestration.synthesis import (
        _format_valuation_block,
        _price_date_age_days,
    )
    # Direct helper unit test
    assert _price_date_age_days(None) is None
    assert _price_date_age_days("") is None
    assert _price_date_age_days("not a date") is None
    assert _price_date_age_days("13/05/2026") is None  # wrong format

    # End-to-end: an unparseable price_date doesn't emit a freshness line
    # at all (we'd be lying about age = N if we couldn't parse the date)
    rec = _make_record_with_price_date("garbage")
    block = _format_valuation_block([rec])
    assert "VANHENTUNUT" not in block
    assert "Kurssin lähde" not in block


def test_price_freshness_helper_returns_today_zero_days() -> None:
    """Sanity: today's date should yield age=0."""
    from datetime import date

    from inderes_agent.orchestration.synthesis import _price_date_age_days
    today = date.today().isoformat()
    assert _price_date_age_days(today) == 0


def test_price_freshness_helper_ignores_future_dates() -> None:
    """Future dates (clock skew, agent typo) shouldn't trigger negative age
    or false warnings — return None and stay silent."""
    from datetime import date, timedelta

    from inderes_agent.orchestration.synthesis import _price_date_age_days
    future = (date.today() + timedelta(days=30)).isoformat()
    assert _price_date_age_days(future) is None
