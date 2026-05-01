"""Inderes MCP connection helpers.

The MCP server at https://mcp.inderes.com requires a Bearer token from Inderes'
Keycloak SSO. Microsoft Agent Framework's `MCPStreamableHTTPTool` exposes only:
  - `header_provider` — called per-tool-invocation, NOT during MCP `initialize`
  - `http_client`     — the underlying `httpx.AsyncClient`, applied to ALL requests

Because the 401 happens during `initialize` (before any tool call), we MUST attach
auth via the `http_client`. We pass a custom `httpx.Auth` that fetches the access
token from our OAuth cache (`oauth.py`) for every request, so token refresh on
expiry works transparently mid-session.

First run opens a browser for the OAuth flow (BUILD_SPEC §6.2). We trigger this
*eagerly* at app startup via `prefetch_token()` so all 4 agents share one cached
token rather than racing to authenticate.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Iterable

import httpx
from agent_framework import MCPStreamableHTTPTool

from ..settings import Settings, get_settings
from .oauth import get_inderes_access_token

# JSON-Schema metadata fields that Inderes MCP tool schemas include but Gemini's
# `FunctionDeclaration` Pydantic model rejects (extra='forbid'). Stripping them
# recursively before any tool call solves the validation crash.
_INCOMPATIBLE_SCHEMA_KEYS: tuple[str, ...] = ("$schema", "$id", "$ref", "$defs", "$comment")


def _scrub_schema_in_place(schema: Any) -> None:
    if isinstance(schema, dict):
        for key in _INCOMPATIBLE_SCHEMA_KEYS:
            schema.pop(key, None)
        for v in schema.values():
            _scrub_schema_in_place(v)
    elif isinstance(schema, list):
        for item in schema:
            _scrub_schema_in_place(item)


class _SanitizingMCPTool(MCPStreamableHTTPTool):
    """MCPStreamableHTTPTool that strips JSON-Schema fields incompatible with Gemini.

    Subclassed because there is no schema-sanitization hook in MAF 1.x. After the
    parent's `connect()` populates `self._functions`, each FunctionTool's cached
    input schema is mutated in place to remove `$schema` and friends.
    """

    async def connect(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        result = await super().connect(*args, **kwargs)
        for func in getattr(self, "_functions", []):
            cached = getattr(func, "_input_schema_cached", None)
            if cached is not None:
                _scrub_schema_in_place(cached)
        return result

# Tool inventory per BUILD_SPEC §3, partitioned per subagent (BUILD_SPEC §4.1).
QUANT_TOOLS: tuple[str, ...] = (
    "search-companies",
    "get-fundamentals",
    "get-inderes-estimates",
)

RESEARCH_TOOLS: tuple[str, ...] = (
    "search-companies",
    "list-content",
    "get-content",
    "list-transcripts",
    "get-transcript",
    "list-company-documents",
    "get-document",
    "read-document-sections",
)

SENTIMENT_TOOLS: tuple[str, ...] = (
    "search-companies",
    "list-insider-transactions",
    "search-forum-topics",
    "get-forum-posts",
    "list-calendar-events",
)

PORTFOLIO_TOOLS: tuple[str, ...] = (
    "get-model-portfolio-content",
    "get-model-portfolio-price",
    "search-companies",
)


class _InderesBearerAuth(httpx.Auth):
    """Per-request httpx.Auth that fetches the latest cached Inderes token.

    Because `get_inderes_access_token` consults the cache and refreshes on expiry,
    long-running sessions don't fail mid-call when the access token expires.
    """

    def __init__(self, resource_url: str, client_id: str) -> None:
        self.resource_url = resource_url
        self.client_id = client_id

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        token = get_inderes_access_token(
            resource_url=self.resource_url,
            client_id=self.client_id,
        )
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def prefetch_token(settings: Settings | None = None) -> None:
    """Trigger OAuth flow (or refresh) once at app startup.

    Subsequent calls within `_InderesBearerAuth.auth_flow` then read from the cache.
    Without this, four parallel agent builds could each launch the OAuth browser flow.
    """
    s = settings or get_settings()
    get_inderes_access_token(
        resource_url=s.INDERES_MCP_URL,
        client_id=s.INDERES_MCP_CLIENT_ID,
    )


def build_mcp_tool(
    name: str,
    allowed: Iterable[str],
    settings: Settings | None = None,
) -> MCPStreamableHTTPTool:
    """Construct an MCPStreamableHTTPTool restricted to `allowed` tools, with OAuth auth."""
    s = settings or get_settings()
    auth = _InderesBearerAuth(
        resource_url=s.INDERES_MCP_URL,
        client_id=s.INDERES_MCP_CLIENT_ID,
    )
    http_client = httpx.AsyncClient(auth=auth, timeout=30.0)
    return _SanitizingMCPTool(
        name=name,
        url=s.INDERES_MCP_URL,
        allowed_tools=list(allowed),
        approval_mode="never_require",
        http_client=http_client,
        # Inderes MCP exposes only tools — no prompts. With the default load_prompts=True,
        # MAF calls prompts/list during initialize and the server responds "Method not found",
        # which crashes the agent context manager. Disable prompt loading.
        load_prompts=False,
    )
