"""Yahoo Finance MCP connection helpers.

Mirror of `inderes_client.py` for our self-hosted Yahoo MCP server
(repo: https://github.com/5qtb5t9v5k-rgb/yahoo-finance-mcp). Unlike
Inderes MCP this one is unauthenticated — the server is single-tenant
and not on the public internet (Modal-deployed or localhost during
development).

Per-agent tool partitioning mirrors the Inderes partitioning logic
(see `inderes_client.py:63–111`):

  - `get_holders` is the Yahoo parallel of Inderes
    `list-insider-transactions` → SENTIMENT-only
  - `get_snapshot` is the Yahoo parallel of `get-fundamentals` /
    `get-inderes-estimates` (price + ratios + BVPS + consensus) →
    QUANT + VALUATION
  - `get_news` is the Yahoo parallel of `list-content` (narrative
    information) → RESEARCH + SENTIMENT
  - `get_history` has *no Inderes parallel* — Inderes MCP doesn't
    expose price-history time series at all → QUANT + PORTFOLIO,
    enables Plotly charting for Finnish AND international names
  - `search_ticker` is universal like Inderes `search-companies`

Toggle: when `YAHOO_MCP_URL` env var is empty, `build_yahoo_mcp_tool`
returns None and the agents skip Yahoo cleanly. Inderes-only flow is
unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx
from agent_framework import MCPStreamableHTTPTool

from ..settings import Settings, get_settings
from ._compat import SanitizingMCPTool

# Per-subagent tool partitioning. Same shape as `inderes_client.py`.
YAHOO_QUANT_TOOLS: tuple[str, ...] = (
    "search_ticker",
    "get_snapshot",
    "get_history",
)

YAHOO_VALUATION_TOOLS: tuple[str, ...] = (
    "search_ticker",
    "get_snapshot",
)

YAHOO_RESEARCH_TOOLS: tuple[str, ...] = (
    "search_ticker",
    "get_news",
)

YAHOO_SENTIMENT_TOOLS: tuple[str, ...] = (
    "search_ticker",
    "get_news",
    "get_holders",
)

YAHOO_PORTFOLIO_TOOLS: tuple[str, ...] = (
    "search_ticker",
    "get_snapshot",
    "get_history",
)


def build_yahoo_mcp_tool(
    name: str,
    allowed: Iterable[str],
    settings: Settings | None = None,
) -> MCPStreamableHTTPTool | None:
    """Construct a Yahoo MCP tool restricted to ``allowed`` tools.

    Returns ``None`` when ``YAHOO_MCP_URL`` is empty so callers can do
    a clean ``if yahoo_tool is not None: tools.append(yahoo_tool)``
    pattern. This makes Yahoo a strictly additive capability — no
    breakage if the env var is unset (Streamlit Cloud's initial deploy,
    fresh `.env`, CI without external services, etc.).
    """
    s = settings or get_settings()
    url = (s.YAHOO_MCP_URL or "").strip()
    if not url:
        return None

    # No auth shim — Yahoo MCP is unauthenticated (single-tenant,
    # behind Modal's private URL or localhost). If we later add a
    # shared secret, attach it here via httpx.Auth like Inderes.
    http_client = httpx.AsyncClient(timeout=30.0)
    return SanitizingMCPTool(
        name=name,
        url=url,
        allowed_tools=list(allowed),
        approval_mode="never_require",
        http_client=http_client,
        # FastMCP exposes only tools (no prompts/resources). Same
        # rationale as Inderes — avoid prompts/list 404 on initialize.
        load_prompts=False,
    )
