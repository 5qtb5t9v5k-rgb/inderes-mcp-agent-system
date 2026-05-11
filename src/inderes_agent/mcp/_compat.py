"""Cross-MCP-server compatibility shim for Gemini.

Centralises the JSON-Schema sanitization step so every MCP client we
build (Inderes, Yahoo, future SEC/FRED/…) can share the same
``_SanitizingMCPTool``. Without sanitization, Gemini's
``FunctionDeclaration`` Pydantic model rejects MCP tool schemas that
include ``$schema`` / ``$ref`` / ``$defs`` (extra='forbid'), crashing
the agent before the first tool call.

The pattern: subclass ``MCPStreamableHTTPTool``, hook ``connect()`` to
scrub the cached input schemas in place after the parent populates them.
"""

from __future__ import annotations

from typing import Any

from agent_framework import MCPStreamableHTTPTool

# JSON-Schema metadata fields that Gemini's FunctionDeclaration rejects.
_INCOMPATIBLE_SCHEMA_KEYS: tuple[str, ...] = ("$schema", "$id", "$ref", "$defs", "$comment")


def scrub_schema_in_place(schema: Any) -> None:
    """Recursively strip Gemini-incompatible metadata keys from a JSON
    schema, in place. Idempotent."""
    if isinstance(schema, dict):
        for key in _INCOMPATIBLE_SCHEMA_KEYS:
            schema.pop(key, None)
        for v in schema.values():
            scrub_schema_in_place(v)
    elif isinstance(schema, list):
        for item in schema:
            scrub_schema_in_place(item)


class SanitizingMCPTool(MCPStreamableHTTPTool):
    """MCPStreamableHTTPTool that strips JSON-Schema fields incompatible
    with Gemini after ``connect()`` populates its function cache.

    Subclassed because there is no schema-sanitization hook in MAF 1.x.
    """

    async def connect(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        result = await super().connect(*args, **kwargs)
        for func in getattr(self, "_functions", []):
            cached = getattr(func, "_input_schema_cached", None)
            if cached is not None:
                scrub_schema_in_place(cached)
        return result
