"""aino-sentiment — market signals subagent."""

from __future__ import annotations

from agent_framework import Agent

from ..llm.gemini_client import build_chat_client
from ..mcp.inderes_client import SENTIMENT_TOOLS, build_mcp_tool
from ..mcp.yahoo_client import YAHOO_SENTIMENT_TOOLS, build_yahoo_mcp_tool
from ._common import load_prompt, resolve_deep_model_override, with_yahoo


def build_sentiment_agent(deep: bool = False) -> Agent:
    """Construct the sentiment subagent.

    When ``YAHOO_MCP_URL`` is set, SENTIMENT also gets Yahoo's
    ``search_ticker / get_news / get_holders``. ``get_holders`` is the
    Yahoo parallel of Inderes ``list-insider-transactions`` — same
    "who is positioned" question, different jurisdiction.
    """
    inderes = build_mcp_tool(name="inderes-sentiment", allowed=SENTIMENT_TOOLS)
    yahoo = build_yahoo_mcp_tool(name="yahoo-sentiment", allowed=YAHOO_SENTIMENT_TOOLS)
    return Agent(
        client=build_chat_client(primary_model=resolve_deep_model_override(deep)),
        name="aino-sentiment",
        instructions=load_prompt("sentiment.md"),
        tools=with_yahoo(inderes, yahoo),
    )
