"""Test fixtures and patches.

We shim the heavy framework dependencies so router/orchestration logic can be tested
without a real Gemini key or live MCP. Tests requiring the real stack are skipped
when GEMINI_API_KEY is absent.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _set_dummy_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "dummy-test-key"))
    monkeypatch.setenv("PRIMARY_MODEL", "gemini-3.1-flash-lite-preview")
    monkeypatch.setenv("FALLBACK_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("MAX_CONCURRENT_AGENTS", "2")


@pytest.fixture
def have_real_gemini():
    return bool(os.environ.get("GEMINI_API_KEY")) and os.environ["GEMINI_API_KEY"] != "dummy-test-key"
