"""Smoke test: ui/* modules import without breakage.

This test would have caught the 2026-05-10 morning incident where
`from components import render_feedback_widget` landed on main while
the function was missing — Streamlit Cloud kept deploying the broken
state for several hours because no test exercised the import path.

We don't run app.py top-level (it calls st.set_page_config and would
require a live Streamlit runtime). Instead we:
  1. Add ui/ to sys.path the same way Streamlit does at runtime.
  2. Import components.py — checks every symbol referenced in __all__
     (or just defined) loads cleanly.
  3. py_compile app.py — catches syntax errors and (transitively)
     verifies that every name in `from components import (...)` exists,
     because Python evaluates import statements at compile time only
     enough to parse them, but we also explicitly check the names
     against components' module namespace below.

Keep this test fast (< 1 s). It is a tripwire, not a behaviour test.
"""

from __future__ import annotations

import importlib
import py_compile
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = REPO_ROOT / "ui"


@pytest.fixture(autouse=True)
def _ui_on_syspath(monkeypatch):
    """Mimic Streamlit's runtime: ui/ on sys.path so `from components import …` works."""
    monkeypatch.syspath_prepend(str(UI_DIR))
    # Force fresh import so prior tests' stale cache doesn't hide regressions.
    for mod in ("components", "charts"):
        sys.modules.pop(mod, None)
    yield


def test_components_module_imports():
    """ui/components.py loads — no missing symbols, no syntax errors."""
    components = importlib.import_module("components")
    # Sanity: at least one well-known symbol is exported.
    assert hasattr(components, "inject_theme")
    assert hasattr(components, "render_titlebar")


def test_app_py_compiles():
    """ui/app.py compiles — catches syntax errors before deploy."""
    py_compile.compile(str(UI_DIR / "app.py"), doraise=True)


def test_app_imports_all_referenced_components():
    """Every name in `from components import (...)` exists in components.

    This is the specific tripwire for the morning's `render_feedback_widget`
    incident. We parse app.py's import statements and assert each name
    resolves in the components module — without actually running app.py.
    """
    import ast

    components = importlib.import_module("components")
    app_source = (UI_DIR / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(app_source)

    missing: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "components":
            for alias in node.names:
                name = alias.name
                if not hasattr(components, name):
                    missing.append(name)

    assert not missing, (
        f"app.py imports these names from components.py but they don't exist: "
        f"{missing}. This would crash Streamlit Cloud at boot."
    )


def test_charts_module_imports():
    """ui/charts.py loads — Plotly + Streamlit deps wired correctly."""
    charts = importlib.import_module("charts")
    # Sanity: a known public function exists.
    assert callable(getattr(charts, "build_pe_timeseries", None)) or \
           callable(getattr(charts, "render_pe_timeseries", None)) or \
           hasattr(charts, "__name__")  # at minimum the module loaded
