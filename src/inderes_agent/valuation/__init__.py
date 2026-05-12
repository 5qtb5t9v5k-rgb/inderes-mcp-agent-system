"""Vaihtoehtoinen arvonmääritys — käyttäjän oma metodologia.

Implements Juho's 8-step valuation philosophy as a deterministic, LLM-free
Python module. The engine takes raw inputs (BVPS, ROE, k, g, price) and
produces a structured ``Valuation`` result that mirrors the user's
``Arvonmääritys2023.xlsx`` Data-sheet outputs.

Public API:
    >>> from inderes_agent.valuation import value_stock
    >>> v = value_stock(bvps=2.68, roe=0.19, k=0.09, g=0.05, price=8.20)
    >>> v.fair_value
    9.38
    >>> v.quality
    'laatu'

The engine is consumed by the ``valuation`` agent (see ``agents/valuation.py``)
when the user has the "vaihtoehtoinen arvonmääritys" toggle enabled in the UI.
"""

from .engine import (
    SensitivityAxis,
    SensitivityGrid,
    Valuation,
    sensitivity_grid,
    value_stock,
)
from .parser import (
    ValuationAgentOutput,
    ValuationAgentSkipped,
    ValuationParseError,
    parse,
)

__all__ = [
    "SensitivityAxis",
    "SensitivityGrid",
    "Valuation",
    "ValuationAgentOutput",
    "ValuationAgentSkipped",
    "ValuationParseError",
    "parse",
    "sensitivity_grid",
    "value_stock",
]
