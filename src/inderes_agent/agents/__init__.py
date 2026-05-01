"""Agent definitions. Each module exports a `build_*_agent()` factory.

Agents are async-context-manager objects (per agent_framework 1.0+ Agent API).
The build_* functions return them un-entered; callers do `async with build_quant_agent() as a:`.
"""

from .lead import build_lead_agent
from .portfolio import build_portfolio_agent
from .quant import build_quant_agent
from .research import build_research_agent
from .sentiment import build_sentiment_agent

__all__ = [
    "build_lead_agent",
    "build_portfolio_agent",
    "build_quant_agent",
    "build_research_agent",
    "build_sentiment_agent",
]
