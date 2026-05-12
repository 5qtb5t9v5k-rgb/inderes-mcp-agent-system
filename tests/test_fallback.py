"""FallbackGeminiChatClient — verify classification, retry-with-backoff, and
fallback semantics without hitting the live API.

History note: the original tests pre-dated 2026-05-11's quota-error
investigation. They asserted that ANY ``RuntimeError("429")`` triggers
``QuotaExhaustedError``, which masked the real bug — per-minute rate
limits and concurrent-request limits were being misdiagnosed as daily
quota exhaustion (locking the user out for a day when 60s would have
sufficed). The rewritten suite below tests the **structured
classification** (`APIError.code` + `quotaId` parsing) and the **retry-
with-backoff path** for non-fatal rate limits.
"""

from __future__ import annotations

from typing import Any

import pytest

from inderes_agent.llm.gemini_client import (
    FallbackGeminiChatClient,
    QuotaExhaustedError,
    _classify_gemini_error,
    _is_quota_exhausted,
    _is_rate_limited_transient,
    _is_unavailable,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_api_error(
    code: int,
    status: str = "RESOURCE_EXHAUSTED",
    quota_id: str | None = None,
    message: str = "test error",
) -> BaseException:
    """Construct a real ``google.genai.errors.APIError`` mirroring the shape
    the SDK actually returns. Used to test classification without mocking."""
    from google.genai.errors import APIError

    response_json: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "status": status,
            "details": [],
        }
    }
    if quota_id is not None:
        response_json["error"]["details"] = [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": quota_id, "quotaMetric": "test/metric"}],
            }
        ]
    return APIError(code=code, response_json=response_json)


def _make_uninitialized_client(retry_delay: float = 0.0) -> FallbackGeminiChatClient:
    """Build a FallbackGeminiChatClient bypassing the parent constructor.

    The ``retry_delay`` defaults to 0 so unit tests don't actually wait
    through the 30s/60s production backoff schedule.
    """
    client = FallbackGeminiChatClient.__new__(FallbackGeminiChatClient)
    client.primary_model = "gemini-3.1-flash-lite-preview"
    client.fallback_model = "gemini-2.5-flash"
    client.retry_delay = retry_delay
    client.max_retries = 1
    client.last_used_model = client.primary_model
    client.fallback_event_count = 0
    client.model = client.primary_model
    return client


@pytest.fixture(autouse=True)
def _skip_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``asyncio.sleep`` with a no-op so unit tests don't actually
    spend 30+ seconds per backoff. We only care that the retry logic
    fires, not that real wall-clock time elapses."""
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("inderes_agent.llm.gemini_client.asyncio.sleep", _instant_sleep)


# ─────────────────────────────────────────────────────────────────────────────
# _classify_gemini_error — the structured classifier
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_503_is_transient():
    """5xx server errors are transient — retry with backoff, eventually fall back."""
    exc = _make_api_error(code=503, status="UNAVAILABLE")
    assert _classify_gemini_error(exc) == "transient"


def test_classify_504_is_transient():
    exc = _make_api_error(code=504, status="DEADLINE_EXCEEDED")
    assert _classify_gemini_error(exc) == "transient"


def test_classify_429_with_perminute_quotaid_is_rate_limit_minute():
    """The critical case from tonight's debug: per-minute rate limit should
    NOT be treated as fatal daily exhaustion."""
    exc = _make_api_error(
        code=429,
        status="RESOURCE_EXHAUSTED",
        quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
    )
    assert _classify_gemini_error(exc) == "rate_limit_minute"


def test_classify_429_with_perday_quotaid_is_rate_limit_day():
    """The genuine daily-quota case. Only this should escalate to
    QuotaExhaustedError."""
    exc = _make_api_error(
        code=429,
        status="RESOURCE_EXHAUSTED",
        quota_id="GenerateRequestsPerDayPerProjectPerModel",
    )
    assert _classify_gemini_error(exc) == "rate_limit_day"


def test_classify_429_with_token_perminute_quotaid_is_rate_limit_minute():
    exc = _make_api_error(
        code=429,
        status="RESOURCE_EXHAUSTED",
        quota_id="GenerateContentInputTokensPerModelPerMinute",
    )
    assert _classify_gemini_error(exc) == "rate_limit_minute"


def test_classify_429_with_no_quotaid_defaults_to_minute():
    """Defensive default — if we can't tell, assume retryable rather than
    locking the user out for a day."""
    exc = _make_api_error(code=429, status="RESOURCE_EXHAUSTED")
    assert _classify_gemini_error(exc) == "rate_limit_minute"


def test_classify_400_bad_request_is_other():
    """4xx that aren't 429 — propagate immediately, this is a bug."""
    exc = _make_api_error(code=400, status="INVALID_ARGUMENT")
    assert _classify_gemini_error(exc) == "other"


def test_classify_non_apierror_runtime_error_is_other():
    """The promiscuous OLD heuristic would match 'session-id-429abc' as
    quota. The new classifier correctly returns 'other' for non-APIError
    exceptions whose string happens to contain '429'."""
    exc = RuntimeError("session id 429abc-xyz disconnected unexpectedly")
    assert _classify_gemini_error(exc) == "other"


# ─────────────────────────────────────────────────────────────────────────────
# Legacy shims — still work for backward-compat in code paths that pass
# plain string exceptions (rare, but kept working).
# ─────────────────────────────────────────────────────────────────────────────


def test_is_unavailable_legacy_shim_still_works_on_strings():
    """Old test pattern still works — substring fallback for non-APIError."""
    assert _is_unavailable(RuntimeError("503 UNAVAILABLE retry"))
    assert _is_unavailable(Exception("Service Unavailable"))
    assert not _is_unavailable(RuntimeError("400 bad request"))


def test_is_quota_exhausted_only_fires_on_genuine_daily():
    """Critical regression: plain RuntimeError("429 RESOURCE_EXHAUSTED") no
    longer triggers QuotaExhaustedError. Only structured APIError with
    explicit daily quotaId does."""
    assert not _is_quota_exhausted(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert not _is_quota_exhausted(Exception("quota exceeded"))

    # Only the structured daily case should fire
    daily = _make_api_error(
        code=429,
        quota_id="GenerateRequestsPerDayPerProjectPerModel",
    )
    assert _is_quota_exhausted(daily)


def test_is_rate_limited_transient_covers_minute_and_5xx():
    minute = _make_api_error(
        code=429,
        quota_id="GenerateRequestsPerMinutePerProjectPerModel",
    )
    transient = _make_api_error(code=503, status="UNAVAILABLE")
    assert _is_rate_limited_transient(minute)
    assert _is_rate_limited_transient(transient)

    daily = _make_api_error(code=429, quota_id="GenerateRequestsPerDayPerProjectPerModel")
    other = _make_api_error(code=400, status="INVALID_ARGUMENT")
    assert not _is_rate_limited_transient(daily)
    assert not _is_rate_limited_transient(other)


# ─────────────────────────────────────────────────────────────────────────────
# _awaitable_call — primary retry + fallback semantics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_success_no_fallback(monkeypatch):
    """Happy path — no retries, no fallback."""
    client = _make_uninitialized_client()

    async def ok(self, messages, *args, **kwargs):
        return f"primary={self.model}"

    monkeypatch.setattr("agent_framework_gemini.GeminiChatClient.get_response", ok)

    result = await client._awaitable_call(["hi"])
    assert result == f"primary={client.primary_model}"
    assert client.last_used_model == client.primary_model
    assert client.fallback_event_count == 0


@pytest.mark.asyncio
async def test_primary_retries_on_per_minute_rate_limit_then_succeeds(monkeypatch):
    """The headline new behavior: per-minute rate limit on primary triggers
    in-place retry (NOT immediate fallback). After 1 simulated wait, the
    rate-limit window closes and the same model succeeds.

    This is the critical fix for tonight's quota-error mystery — the old
    behavior fell back immediately on any 429, then the fallback also
    rate-limited (because both Flash Lite and Flash 2.5 share the project's
    per-minute quotas), and we ended up at QuotaExhaustedError for what
    was actually a transient 60-second burst.
    """
    client = _make_uninitialized_client(retry_delay=0.0)
    attempt_count = {"n": 0}

    async def burst_then_success(self, messages, *args, **kwargs):
        attempt_count["n"] += 1
        if attempt_count["n"] == 1:
            raise _make_api_error(
                code=429,
                quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
            )
        return f"primary={self.model}"

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response", burst_then_success,
    )

    result = await client._awaitable_call(["hi"])
    assert result == f"primary={client.primary_model}"
    assert client.fallback_event_count == 0  # NEVER fell back
    assert attempt_count["n"] == 2  # 1 failure + 1 retry success


@pytest.mark.asyncio
async def test_persistent_5xx_falls_back_after_primary_retries_exhausted(monkeypatch):
    """When primary 5xx's persistently, fallback engages after retries are
    exhausted on the primary."""
    client = _make_uninitialized_client()
    call_log: list[str] = []

    async def primary_503_fallback_ok(self, messages, *args, **kwargs):
        call_log.append(self.model)
        if self.model == client.primary_model:
            raise _make_api_error(code=503, status="UNAVAILABLE")
        return "ok-from-fallback"

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response", primary_503_fallback_ok,
    )

    result = await client._awaitable_call(["hi"])
    assert result == "ok-from-fallback"
    assert client.last_used_model == client.fallback_model
    assert client.fallback_event_count == 1
    # Primary attempted 3 times (retries), then 1 fallback call
    assert call_log == [client.primary_model] * 3 + [client.fallback_model]


@pytest.mark.asyncio
async def test_quota_exhausted_only_on_genuine_daily(monkeypatch):
    """QuotaExhaustedError fires only when BOTH models return APIError with
    daily quotaId. Per-minute rate limits should NOT trigger this."""
    client = _make_uninitialized_client()

    async def both_daily(self, messages, *args, **kwargs):
        raise _make_api_error(
            code=429,
            quota_id="GenerateRequestsPerDayPerProjectPerModel",
        )

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response", both_daily,
    )

    with pytest.raises(QuotaExhaustedError) as exc_info:
        await client._awaitable_call(["hi"])
    # The new error message includes BOTH model names so the user knows
    # exactly which limits hit
    assert client.primary_model in str(exc_info.value)
    assert client.fallback_model in str(exc_info.value)


@pytest.mark.asyncio
async def test_per_minute_rate_limit_does_not_raise_quota_exhausted(monkeypatch):
    """Regression test for tonight's bug (2026-05-11 21:04-21:19).

    Before fix: 5 consecutive primary-then-fallback failures with per-minute
    429s incorrectly raised QuotaExhaustedError with the misleading message
    "Daily Gemini quota exhausted, upgrade to paid tier" — even though
    the user IS on paid Tier 1 and the dashboard showed 0.1% usage.

    After fix: per-minute 429s on both models exhaust retries and raise a
    descriptive RuntimeError, NOT QuotaExhaustedError. User can wait a
    minute and try again.
    """
    client = _make_uninitialized_client()

    async def always_minute_rate_limit(self, messages, *args, **kwargs):
        raise _make_api_error(
            code=429,
            quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        )

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response",
        always_minute_rate_limit,
    )

    with pytest.raises(Exception) as exc_info:
        await client._awaitable_call(["hi"])
    # Must NOT be the misleading QuotaExhaustedError
    assert not isinstance(exc_info.value, QuotaExhaustedError), (
        "Per-minute rate limit incorrectly classified as daily quota — "
        "the exact bug we just fixed"
    )
    # Should be a clear runtime error mentioning the rate-limit chain
    assert "rate" in str(exc_info.value).lower() or "429" in str(exc_info.value)


@pytest.mark.asyncio
async def test_non_retryable_error_propagates_immediately(monkeypatch):
    """A 400 BAD_REQUEST is an agent / prompt bug, not a rate limit.
    Should propagate immediately without retrying or falling back."""
    client = _make_uninitialized_client()
    call_count = {"n": 0}

    async def bad_request(self, messages, *args, **kwargs):
        call_count["n"] += 1
        raise _make_api_error(code=400, status="INVALID_ARGUMENT")

    monkeypatch.setattr(
        "agent_framework_gemini.GeminiChatClient.get_response", bad_request,
    )

    with pytest.raises(Exception) as exc_info:
        await client._awaitable_call(["hi"])
    # Real Genai error, not our wrappers
    from google.genai.errors import APIError
    assert isinstance(exc_info.value, APIError)
    # No retries — exactly 1 call
    assert call_count["n"] == 1
    assert client.fallback_event_count == 0
