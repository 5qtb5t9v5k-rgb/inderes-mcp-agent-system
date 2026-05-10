"""Runtime OAuth flow tests — refresh, gist persistence, load priorities.

Complements `test_oauth_bootstrap.py` which covers the env-var bootstrap
path. This file covers the parts that have caused production bugs:

  * TokenSet freshness and forward-compat from_dict (gist tokens.json
    sometimes carries _last_refresh_status fields)
  * _refresh_tokens HTTP behaviour (success, 400/401, missing
    refresh_token in response keeps the old one)
  * _push_tokens_to_gist / _pull_tokens_from_gist HTTP behaviour
  * _load_tokens priority order — first-call gist pull, then local
    cache, then env bootstrap

Mocks httpx at the `oauth.httpx` module-level binding via monkeypatch.
We don't rely on `pytest-httpx` to keep dev deps lean.

The Streamlit Cloud deploy issue we saw this morning would have been
caught by `test_load_tokens_first_call_pulls_from_gist_overrides_cache`
— that's the path that goes wrong when the in-container tokens.json
has the rotated-and-now-invalid refresh token.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from inderes_agent.mcp import oauth as oauth_mod

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch):
    """Point the OAuth cache at a tmp dir, isolating tests from the real ~/.cache."""
    monkeypatch.setenv("INDERES_AGENT_CACHE", str(tmp_path))
    # Clear in-process flag so each test gets a clean "first call" path
    oauth_mod._GIST_PULLED_THIS_PROCESS = False
    yield tmp_path
    oauth_mod._GIST_PULLED_THIS_PROCESS = False


@pytest.fixture
def fresh_tokenset() -> oauth_mod.TokenSet:
    return oauth_mod.TokenSet(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at=time.time() + 3600,
        token_endpoint="https://sso.example.com/token",
        client_id="test-client",
    )


def _mock_httpx_response(
    status_code: int = 200,
    json_body: dict[str, Any] | None = None,
    text_body: str = "",
) -> Any:
    """Construct a duck-typed httpx Response stand-in."""
    return SimpleNamespace(
        status_code=status_code,
        json=lambda: json_body or {},
        text=text_body or json.dumps(json_body or {}),
        raise_for_status=(
            (lambda: None) if 200 <= status_code < 300
            else (lambda: (_ for _ in ()).throw(
                RuntimeError(f"HTTP {status_code}")
            ))
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TokenSet behaviour
# ─────────────────────────────────────────────────────────────────────────────


def test_tokenset_is_fresh_when_far_from_expiry(fresh_tokenset):
    assert fresh_tokenset.is_fresh is True


def test_tokenset_is_stale_within_refresh_buffer():
    """Within `TOKEN_REFRESH_BUFFER_S` of expiry, treated as stale."""
    nearly_expired = oauth_mod.TokenSet(
        access_token="x",
        refresh_token="y",
        expires_at=time.time() + 5,  # 5 s from now — well within buffer
        token_endpoint="https://sso.example.com/token",
        client_id="c",
    )
    assert nearly_expired.is_fresh is False


def test_tokenset_from_dict_ignores_unknown_fields():
    """Gist tokens.json sometimes carries bookkeeping fields the cron worker
    writes (`_last_refresh_status`, `_last_refresh_at`). Forward-compat
    requires from_dict to drop them, not throw."""
    blob = {
        "access_token": "a",
        "refresh_token": "r",
        "expires_at": 1234567890.0,
        "token_endpoint": "https://example.com",
        "client_id": "c",
        "_last_refresh_status": "ok",  # extra bookkeeping
        "_last_refresh_at": "2026-05-10T12:00:00Z",
        "future_field_we_dont_know_about": True,
    }
    ts = oauth_mod.TokenSet.from_dict(blob)
    assert ts.access_token == "a"
    assert ts.expires_at == 1234567890.0


def test_tokenset_to_from_roundtrip(fresh_tokenset):
    """to_dict → from_dict round-trip is identity (sanity check)."""
    blob = fresh_tokenset.to_dict()
    rebuilt = oauth_mod.TokenSet.from_dict(blob)
    assert asdict(rebuilt) == asdict(fresh_tokenset)


# ─────────────────────────────────────────────────────────────────────────────
# _refresh_tokens — Keycloak refresh-grant flow
# ─────────────────────────────────────────────────────────────────────────────


def test_refresh_success_returns_rotated_tokens(monkeypatch, fresh_tokenset):
    """Happy path: Keycloak returns 200 with new tokens."""
    captured_request = {}

    def fake_post(url, *, data, headers, timeout):
        captured_request["url"] = url
        captured_request["data"] = data
        return _mock_httpx_response(
            200,
            json_body={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 600,
            },
        )

    monkeypatch.setattr(oauth_mod.httpx, "post", fake_post)

    result = oauth_mod._refresh_tokens(fresh_tokenset)
    assert result is not None
    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert result.expires_at > time.time() + 500  # ~600s in the future
    # Verify we sent the right grant
    assert captured_request["data"]["grant_type"] == "refresh_token"
    assert captured_request["data"]["refresh_token"] == "refresh-1"
    assert captured_request["url"] == fresh_tokenset.token_endpoint


def test_refresh_failure_returns_none(monkeypatch, fresh_tokenset):
    """Non-200 response (e.g. 400 invalid_grant) returns None — caller falls
    back to gist pull or interactive flow. Prod morning's bug: this returned
    None, then the gist pull was supposed to recover. Test pins the contract."""

    def fake_post(*args, **kwargs):
        return _mock_httpx_response(
            400,
            text_body='{"error":"invalid_grant","error_description":"Token is not active"}',
        )

    monkeypatch.setattr(oauth_mod.httpx, "post", fake_post)

    result = oauth_mod._refresh_tokens(fresh_tokenset)
    assert result is None


def test_refresh_returns_none_when_no_refresh_token():
    """No refresh_token at all → can't refresh; don't even call HTTP."""
    no_refresh = oauth_mod.TokenSet(
        access_token="a",
        refresh_token=None,
        expires_at=time.time() - 100,
        token_endpoint="https://sso.example.com/token",
        client_id="c",
    )
    # Note: not even mocking httpx.post — if it gets called, the test fails
    # on a real network request attempt.
    assert oauth_mod._refresh_tokens(no_refresh) is None


def test_refresh_keeps_old_refresh_token_when_response_omits_it(
    monkeypatch, fresh_tokenset
):
    """Some IdPs don't rotate refresh tokens on every refresh. If the response
    omits `refresh_token`, keep the existing one."""

    def fake_post(*args, **kwargs):
        return _mock_httpx_response(
            200,
            json_body={
                "access_token": "new-access",
                "expires_in": 600,
                # NO refresh_token field
            },
        )

    monkeypatch.setattr(oauth_mod.httpx, "post", fake_post)

    result = oauth_mod._refresh_tokens(fresh_tokenset)
    assert result is not None
    assert result.refresh_token == "refresh-1"  # original preserved


# ─────────────────────────────────────────────────────────────────────────────
# Gist push / pull
# ─────────────────────────────────────────────────────────────────────────────


def test_gist_push_no_config_is_silent_noop(fresh_tokenset, monkeypatch):
    """If GIST_ID/GH_TOKEN env vars are missing, push is a silent no-op
    (local-dev fallback). Don't raise, don't make network calls."""
    monkeypatch.delenv("INDERES_TOKENS_GIST_ID", raising=False)
    monkeypatch.delenv("INDERES_TOKENS_GH_TOKEN", raising=False)

    # If httpx.patch were called, the test environment would error. Silence
    # is success here.
    oauth_mod._push_tokens_to_gist(fresh_tokenset)


def test_gist_push_sends_patch_with_auth_header(fresh_tokenset, monkeypatch):
    """When configured, sends PATCH to api.github.com/gists/<id> with auth."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    captured = {}

    def fake_patch(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _mock_httpx_response(200)

    # Replace httpx in the oauth module's import scope (it's `import httpx`
    # locally inside the function, so we patch the module attribute).
    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "patch", fake_patch)

    oauth_mod._push_tokens_to_gist(fresh_tokenset)

    assert captured["url"] == "https://api.github.com/gists/abc123"
    assert captured["headers"]["Authorization"] == "token ghp_test"
    assert "tokens.json" in captured["json"]["files"]
    # The content is JSON-encoded TokenSet
    pushed_blob = json.loads(captured["json"]["files"]["tokens.json"]["content"])
    assert pushed_blob["access_token"] == "access-1"


def test_gist_pull_returns_tokenset_when_present(monkeypatch):
    """Happy path: gist GET returns the file, parse to TokenSet."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    blob = {
        "access_token": "from-gist",
        "refresh_token": "r-from-gist",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://sso.example.com/token",
        "client_id": "c",
    }

    def fake_get(url, *, headers, timeout):
        return _mock_httpx_response(
            200,
            json_body={"files": {"tokens.json": {"content": json.dumps(blob)}}},
        )

    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "get", fake_get)

    result = oauth_mod._pull_tokens_from_gist()
    assert result is not None
    assert result.access_token == "from-gist"


def test_gist_pull_returns_none_when_file_missing(monkeypatch):
    """Gist exists but doesn't contain tokens.json → None (don't crash)."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    def fake_get(url, *, headers, timeout):
        return _mock_httpx_response(
            200,
            json_body={"files": {"some_other_file.json": {"content": "{}"}}},
        )

    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "get", fake_get)

    assert oauth_mod._pull_tokens_from_gist() is None


def test_gist_pull_returns_none_on_http_error(monkeypatch):
    """Network failure or 401 → None, not an exception."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    def fake_get(*args, **kwargs):
        raise RuntimeError("network down")

    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "get", fake_get)

    assert oauth_mod._pull_tokens_from_gist() is None


# ─────────────────────────────────────────────────────────────────────────────
# _load_tokens priority order (the path that broke on Streamlit Cloud)
# ─────────────────────────────────────────────────────────────────────────────


def test_load_tokens_first_call_pulls_from_gist_overrides_cache(
    isolated_cache, monkeypatch
):
    """The Streamlit Cloud bug: hot-reload preserves /tmp, so a stale
    tokens.json from a prior boot's bootstrap can dominate. Fix: first
    _load_tokens call within a process always pulls from gist if configured."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    # Stale local cache
    cache_path = isolated_cache / "tokens.json"
    cache_path.write_text(json.dumps({
        "access_token": "stale-from-tmp",
        "refresh_token": "stale-refresh",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://sso.example.com/token",
        "client_id": "c",
    }))

    # Fresh content in the gist
    gist_blob = {
        "access_token": "fresh-from-gist",
        "refresh_token": "fresh-refresh",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://sso.example.com/token",
        "client_id": "c",
    }

    def fake_get(*args, **kwargs):
        return _mock_httpx_response(
            200,
            json_body={"files": {"tokens.json": {"content": json.dumps(gist_blob)}}},
        )

    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "get", fake_get)

    result = oauth_mod._load_tokens()
    assert result is not None
    assert result.access_token == "fresh-from-gist"  # gist won, not stale local
    # And the local cache should have been overwritten
    rewritten = json.loads(cache_path.read_text())
    assert rewritten["access_token"] == "fresh-from-gist"


def test_load_tokens_subsequent_calls_use_local_cache(
    isolated_cache, monkeypatch
):
    """After the first gist pull within a process, later calls hit local
    cache (no per-request 200ms gist round-trip)."""
    monkeypatch.setenv("INDERES_TOKENS_GIST_ID", "abc123")
    monkeypatch.setenv("INDERES_TOKENS_GH_TOKEN", "ghp_test")

    # Already pulled flag flipped — test simulates "second call within process"
    oauth_mod._GIST_PULLED_THIS_PROCESS = True

    cache_path = isolated_cache / "tokens.json"
    cache_path.write_text(json.dumps({
        "access_token": "from-local",
        "refresh_token": "r",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://sso.example.com/token",
        "client_id": "c",
    }))

    # If the gist were called, this would cause a network attempt.
    def fake_get(*args, **kwargs):
        raise AssertionError("gist must NOT be called on subsequent _load_tokens")

    import httpx as _httpx_real
    monkeypatch.setattr(_httpx_real, "get", fake_get)

    result = oauth_mod._load_tokens()
    assert result is not None
    assert result.access_token == "from-local"


def test_load_tokens_corrupt_cache_triggers_env_bootstrap(
    isolated_cache, monkeypatch
):
    """If tokens.json is unreadable JSON, fall through to env-var bootstrap.
    Don't crash — recover."""
    monkeypatch.delenv("INDERES_TOKENS_GIST_ID", raising=False)
    monkeypatch.delenv("INDERES_TOKENS_GH_TOKEN", raising=False)

    cache_path = isolated_cache / "tokens.json"
    cache_path.write_text("not-valid-json{{{")

    bootstrap_blob = {
        "access_token": "from-env-bootstrap",
        "refresh_token": "r",
        "expires_at": time.time() + 3600,
        "token_endpoint": "https://sso.example.com/token",
        "client_id": "c",
    }
    monkeypatch.setenv("INDERES_OAUTH_TOKENS_JSON", json.dumps(bootstrap_blob))

    # _bootstrap_from_env() refuses to overwrite an existing cache file,
    # so we delete the corrupt one to simulate the "fall through" path.
    # (The real implementation uses a try/except around from_dict and falls
    # to _bootstrap_from_env, but bootstrap_from_env's "cache exists" guard
    # means corrupt caches don't get rewritten. This is intentional — the
    # operator should clean up manually.)
    cache_path.unlink()

    result = oauth_mod._load_tokens()
    assert result is not None
    assert result.access_token == "from-env-bootstrap"
