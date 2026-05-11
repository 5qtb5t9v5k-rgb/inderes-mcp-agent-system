"""Tests for the Yahoo MCP wiring into the agent fleet.

Verifies the toggle semantics (empty ``YAHOO_MCP_URL`` ⇒ Yahoo disabled,
Inderes-only behaviour preserved bit-for-bit) and the per-agent
partitioning (each agent gets only its assigned subset of Yahoo tools).

The tests don't hit Yahoo — they validate the build-time wiring, which
is where regressions would actually bite (wrong tool-set passed to an
agent, missing import on a new agent, env-var toggle inversion, etc.).
"""

from __future__ import annotations

import importlib

import pytest

from inderes_agent.agents._common import with_yahoo


# ─────────────────────────────────────────────────────────────────────────────
# with_yahoo helper
# ─────────────────────────────────────────────────────────────────────────────


def test_with_yahoo_returns_single_tool_when_yahoo_is_none():
    """When Yahoo is disabled, the agent should see exactly one tool —
    the Inderes one — and nothing else."""
    inderes_sentinel = object()
    out = with_yahoo(inderes_sentinel, None)
    assert out == [inderes_sentinel]


def test_with_yahoo_returns_both_tools_when_yahoo_is_present():
    inderes_sentinel = object()
    yahoo_sentinel = object()
    out = with_yahoo(inderes_sentinel, yahoo_sentinel)
    assert out == [inderes_sentinel, yahoo_sentinel]


# ─────────────────────────────────────────────────────────────────────────────
# build_yahoo_mcp_tool env-var toggle
# ─────────────────────────────────────────────────────────────────────────────


def test_yahoo_tool_returns_none_when_env_var_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("YAHOO_MCP_URL", raising=False)
    # The settings object is cached via lru_cache, so reload to pick up the env change
    from inderes_agent import settings

    importlib.reload(settings)
    from inderes_agent.mcp import yahoo_client

    importlib.reload(yahoo_client)

    tool = yahoo_client.build_yahoo_mcp_tool("test", yahoo_client.YAHOO_QUANT_TOOLS)
    assert tool is None


def test_yahoo_tool_returns_none_when_env_var_whitespace(monkeypatch: pytest.MonkeyPatch):
    """An accidentally-whitespace value (common copy-paste mistake)
    should be treated the same as empty — we don't want to ship a
    request to ``http://   ``."""
    monkeypatch.setenv("YAHOO_MCP_URL", "   ")
    from inderes_agent import settings

    importlib.reload(settings)
    from inderes_agent.mcp import yahoo_client

    importlib.reload(yahoo_client)

    tool = yahoo_client.build_yahoo_mcp_tool("test", yahoo_client.YAHOO_QUANT_TOOLS)
    assert tool is None


def test_yahoo_tool_constructed_when_env_var_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YAHOO_MCP_URL", "http://localhost:8000/mcp")
    from inderes_agent import settings

    importlib.reload(settings)
    from inderes_agent.mcp import yahoo_client

    importlib.reload(yahoo_client)

    tool = yahoo_client.build_yahoo_mcp_tool("test-quant", yahoo_client.YAHOO_QUANT_TOOLS)
    assert tool is not None
    # Allowed-tools list is preserved → no leakage across agents.
    assert list(tool.allowed_tools) == list(yahoo_client.YAHOO_QUANT_TOOLS)
    assert tool.name == "test-quant"


# ─────────────────────────────────────────────────────────────────────────────
# Per-agent partitioning
# ─────────────────────────────────────────────────────────────────────────────


def test_quant_partition_includes_history_but_not_holders():
    """QUANT gets get_history (only available source for price-series
    charting) but NOT get_holders (which is a sentiment signal)."""
    from inderes_agent.mcp.yahoo_client import YAHOO_QUANT_TOOLS

    assert "get_history" in YAHOO_QUANT_TOOLS
    assert "get_snapshot" in YAHOO_QUANT_TOOLS
    assert "get_holders" not in YAHOO_QUANT_TOOLS
    assert "get_news" not in YAHOO_QUANT_TOOLS


def test_sentiment_partition_includes_holders_but_not_history():
    """SENTIMENT is the only agent with get_holders — same rationale as
    Inderes giving list-insider-transactions exclusively to SENTIMENT."""
    from inderes_agent.mcp.yahoo_client import YAHOO_SENTIMENT_TOOLS

    assert "get_holders" in YAHOO_SENTIMENT_TOOLS
    assert "get_news" in YAHOO_SENTIMENT_TOOLS
    assert "get_history" not in YAHOO_SENTIMENT_TOOLS
    assert "get_snapshot" not in YAHOO_SENTIMENT_TOOLS


def test_research_partition_is_news_only():
    """RESEARCH cares about narrative info (transcripts + news), not
    quant data or institutional ownership."""
    from inderes_agent.mcp.yahoo_client import YAHOO_RESEARCH_TOOLS

    assert "get_news" in YAHOO_RESEARCH_TOOLS
    assert "get_history" not in YAHOO_RESEARCH_TOOLS
    assert "get_snapshot" not in YAHOO_RESEARCH_TOOLS
    assert "get_holders" not in YAHOO_RESEARCH_TOOLS


def test_valuation_partition_is_snapshot_only():
    """VALUATION needs price + BVPS (in get_snapshot), nothing else.
    No news/holders/history because the agent's job is to emit JSON
    parameters for the deterministic engine, not narrative analysis."""
    from inderes_agent.mcp.yahoo_client import YAHOO_VALUATION_TOOLS

    assert "get_snapshot" in YAHOO_VALUATION_TOOLS
    assert "get_news" not in YAHOO_VALUATION_TOOLS
    assert "get_history" not in YAHOO_VALUATION_TOOLS
    assert "get_holders" not in YAHOO_VALUATION_TOOLS


def test_search_ticker_is_universal():
    """search_ticker is the Yahoo parallel of search-companies — every
    agent that touches Yahoo needs it for name→ticker resolution
    before any other call."""
    from inderes_agent.mcp.yahoo_client import (
        YAHOO_PORTFOLIO_TOOLS,
        YAHOO_QUANT_TOOLS,
        YAHOO_RESEARCH_TOOLS,
        YAHOO_SENTIMENT_TOOLS,
        YAHOO_VALUATION_TOOLS,
    )

    for partition in (
        YAHOO_QUANT_TOOLS,
        YAHOO_VALUATION_TOOLS,
        YAHOO_RESEARCH_TOOLS,
        YAHOO_SENTIMENT_TOOLS,
        YAHOO_PORTFOLIO_TOOLS,
    ):
        assert "search_ticker" in partition


# ─────────────────────────────────────────────────────────────────────────────
# Agent builders still work when Yahoo is disabled
# ─────────────────────────────────────────────────────────────────────────────


def test_agent_builders_work_without_yahoo(monkeypatch: pytest.MonkeyPatch):
    """The most important regression to prevent: Yahoo wiring must not
    break the existing Inderes-only build path. If YAHOO_MCP_URL is
    unset (default for fresh checkouts and CI), every agent builder
    should still return a working Agent with exactly its Inderes tool."""
    monkeypatch.delenv("YAHOO_MCP_URL", raising=False)
    from inderes_agent import settings

    importlib.reload(settings)
    # Reload yahoo_client first so build_yahoo_mcp_tool sees the unset env
    from inderes_agent.mcp import yahoo_client

    importlib.reload(yahoo_client)

    # Now reload each agent module so its top-of-module imports pick up
    # the freshly-reloaded yahoo_client.
    from inderes_agent.agents import portfolio, quant, research, sentiment, valuation

    for module in (quant, research, sentiment, valuation, portfolio):
        importlib.reload(module)

    # All five builders should return without exceptions.
    for builder_fn in (
        quant.build_quant_agent,
        research.build_research_agent,
        sentiment.build_sentiment_agent,
        valuation.build_valuation_agent,
        portfolio.build_portfolio_agent,
    ):
        agent = builder_fn(deep=False)
        assert agent is not None
        # Each agent must have at least one MCP tool (the Inderes one).
        assert agent.mcp_tools, f"{builder_fn.__name__} returned agent with no MCP tools"
