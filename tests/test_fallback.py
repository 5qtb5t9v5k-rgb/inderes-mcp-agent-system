"""FallbackGeminiChatClient — verify retry and fallback semantics without hitting the API."""

from __future__ import annotations

import pytest

from inderes_agent.llm.gemini_client import (
    FallbackGeminiChatClient,
    QuotaExhaustedError,
    _is_quota_exhausted,
    _is_unavailable,
)


def test_is_unavailable_detects_503():
    assert _is_unavailable(RuntimeError("503 UNAVAILABLE retry"))
    assert _is_unavailable(Exception("Service Unavailable"))
    assert not _is_unavailable(RuntimeError("400 bad request"))


def test_is_quota_exhausted_detects_429():
    assert _is_quota_exhausted(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert _is_quota_exhausted(Exception("quota exceeded"))
    assert not _is_quota_exhausted(RuntimeError("503"))


def _make_uninitialized_client() -> FallbackGeminiChatClient:
    """Build a FallbackGeminiChatClient bypassing the GeminiChatClient super constructor.

    This lets us test fallback logic in isolation; we patch the super().get_response
    behavior via a custom callable wired through `_super_call`.
    """
    client = FallbackGeminiChatClient.__new__(FallbackGeminiChatClient)
    client.primary_model = "gemini-3.1-flash-lite-preview"
    client.fallback_model = "gemini-2.5-flash"
    client.retry_delay = 0.0
    client.max_retries = 1
    client.last_used_model = client.primary_model
    client.fallback_event_count = 0
    client.model = client.primary_model
    return client


@pytest.mark.asyncio
async def test_fallback_on_persistent_503(monkeypatch):
    """Two 503s in a row should trigger fallback model usage."""
    client = _make_uninitialized_client()
    call_log: list[str] = []

    async def fake_super_get_response(self, messages, *args, **kwargs):
        call_log.append(self.model)
        if self.model == self.primary_model:
            raise RuntimeError("503 UNAVAILABLE")
        return "ok-from-fallback"

    # Patch the parent class method that super() resolves to.
    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response",
        fake_super_get_response,
    )

    result = await client._awaitable_call(["hi"])
    assert result == "ok-from-fallback"
    assert client.last_used_model == client.fallback_model
    assert client.fallback_event_count == 1
    assert call_log == [client.primary_model, client.primary_model, client.fallback_model]


@pytest.mark.asyncio
async def test_quota_exhausted_when_both_fail(monkeypatch):
    client = _make_uninitialized_client()

    async def always_429(self, messages, *args, **kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response",
        always_429,
    )

    with pytest.raises(QuotaExhaustedError):
        await client._awaitable_call(["hi"])


@pytest.mark.asyncio
async def test_primary_success_no_fallback(monkeypatch):
    client = _make_uninitialized_client()

    async def ok(self, messages, *args, **kwargs):
        return f"primary={self.model}"

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response",
        ok,
    )

    result = await client._awaitable_call(["hi"])
    assert result == f"primary={client.primary_model}"
    assert client.last_used_model == client.primary_model
    assert client.fallback_event_count == 0
