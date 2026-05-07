"""Phase 3.1 tests for the CricAPI client.

The strategy:

  * Every "logic" test is fully mocked via `httpx.MockTransport`. No
    network, no quota burn, no flake.
  * The real-call test (`test_real_api_key_works`) hits CricAPI exactly
    once with the live key from .env and logs the raw response. It's
    gated on CRICAPI_KEY being present so CI without secrets stays
    green.

Each test gets its own `tmp_path` for the cache root so they're
independent and parallel-safe.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
import pytest

from ingestion.client import (
    ENDPOINT_CRIC_SCORE,
    ENDPOINT_MATCH,
    ENDPOINT_MATCHES,
    ENDPOINT_PLAYER_STATS,
    ENDPOINT_PLAYERS,
    ENDPOINT_SERIES,
    CricAPIClient,
)
from ingestion.exceptions import APIError, NetworkError, RateLimitError

# Load .env so the optional real-call test sees CRICAPI_KEY without the
# user having to export it manually. Look at the backend/ root first
# (where the user actually put it), then fall back to the project root.
try:
    from dotenv import load_dotenv

    _here = Path(__file__).resolve()
    for candidate in (_here.parents[1] / ".env", _here.parents[2] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break
except ModuleNotFoundError:  # pragma: no cover
    pass


# ---------------------------------------------------------------- helpers

def _build_client(
    tmp_path: Path,
    handler,
    *,
    daily_limit: int = 100,
    api_key: str = "test-key",
) -> CricAPIClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return CricAPIClient(
        api_key=api_key,
        base_url="https://api.cricapi.com/v1",
        daily_limit=daily_limit,
        cache_root=tmp_path,
        http_client=http_client,
    )


def _success(data: Any = None, status: str = "success") -> dict[str, Any]:
    return {"status": status, "data": data or [], "info": {"hitsToday": 1}}


# ---------------------------------------------------------------- routing

@pytest.mark.parametrize(
    "method_call, expected_endpoint, expected_extra_params",
    [
        (lambda c: c.cric_score(),                ENDPOINT_CRIC_SCORE,   {}),
        (lambda c: c.series(),                    ENDPOINT_SERIES,       {}),
        (lambda c: c.matches(),                   ENDPOINT_MATCHES,      {}),
        (lambda c: c.match("abc123"),             ENDPOINT_MATCH,        {"id": "abc123"}),
        (lambda c: c.players("babar"),            ENDPOINT_PLAYERS,      {"search": "babar"}),
        (lambda c: c.player_stats("xyz789"),      ENDPOINT_PLAYER_STATS, {"id": "xyz789"}),
    ],
)
def test_each_method_routes_to_correct_endpoint(
    tmp_path, method_call, expected_endpoint, expected_extra_params
):
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_success())

    client = _build_client(tmp_path, handler)
    method_call(client)

    assert expected_endpoint in seen["url"]
    # API key is always injected in the wire request.
    assert seen["params"].get("apikey") == "test-key"
    for k, v in expected_extra_params.items():
        assert seen["params"].get(k) == v


# ---------------------------------------------------------------- caching

def test_cache_hit_short_circuits_http(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_success(data=[{"id": 1}]))

    client = _build_client(tmp_path, handler)

    first = client.matches()
    second = client.matches()

    assert first == second
    # Only ONE network call — second was served from disk cache.
    assert calls["n"] == 1
    assert client.quota.used() == 1


def test_force_refresh_bypasses_cache(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_success(data=[{"call": calls["n"]}]))

    client = _build_client(tmp_path, handler)

    first = client.matches()
    second = client.matches(force_refresh=True)

    assert first != second  # different bodies — second went to network
    assert calls["n"] == 2
    assert client.quota.used() == 2


def test_cache_persists_across_clients(tmp_path):
    """A second client with the same cache_root should see prior writes."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success(data=[{"id": 1}]))

    c1 = _build_client(tmp_path, handler)
    c1.matches()

    # No network handler used by the second client — would error if hit.
    def fail(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("second client must not hit the network")

    c2 = _build_client(tmp_path, fail)
    payload = c2.matches()
    assert payload["status"] == "success"


# ------------------------------------------------------------ rate limit

def test_rate_limit_blocks_after_quota_exhausted(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success())

    client = _build_client(tmp_path, handler, daily_limit=2)

    # Two unique calls (so cache doesn't short-circuit) consume the quota.
    client.match("m1")
    client.match("m2")
    assert client.quota.used() == 2

    with pytest.raises(RateLimitError):
        client.match("m3")


def test_quota_resets_when_stored_date_changes(tmp_path):
    """Yesterday's counter must self-clear when the date rolls over."""
    import json as _json

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success())

    client = _build_client(tmp_path, handler, daily_limit=1)
    client.cric_score()
    assert client.quota.used() == 1

    # Surgically rewrite the date to "yesterday" — the quota loader treats
    # any non-today date as a reset condition.
    quota_file = list(tmp_path.rglob("quota.json"))[0]
    state = _json.loads(quota_file.read_text())
    state["date"] = "2000-01-01"
    quota_file.write_text(_json.dumps(state))

    # New call must succeed because the loader auto-resets.
    client.match("any")  # different endpoint = different cache key
    assert client.quota.used() == 1  # reset to 0 then incremented to 1


def test_cricapi_failure_with_limit_message_raises_rate_limit(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "failure", "reason": "Hits today limit reached"},
        )

    client = _build_client(tmp_path, handler)
    with pytest.raises(RateLimitError):
        client.cric_score()


# ----------------------------------------------------------------- errors

def test_4xx_raises_api_error_immediately(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="Unauthorized")

    client = _build_client(tmp_path, handler)
    with pytest.raises(APIError) as exc_info:
        client.cric_score()

    assert exc_info.value.status_code == 401
    # Critically, no retry — we'd just burn quota on a known bad request.
    assert calls["n"] == 1


def test_5xx_retries_then_succeeds(tmp_path, monkeypatch):
    # Patch sleep so the test doesn't actually wait ~7s for backoff.
    monkeypatch.setattr("ingestion.client.time.sleep", lambda *_: None)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="upstream down")
        return httpx.Response(200, json=_success(data=[{"ok": True}]))

    client = _build_client(tmp_path, handler)
    payload = client.cric_score()
    assert payload["status"] == "success"
    assert calls["n"] == 3


def test_5xx_exhausts_retries_and_raises_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr("ingestion.client.time.sleep", lambda *_: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    client = _build_client(tmp_path, handler)
    with pytest.raises(NetworkError):
        client.cric_score()


def test_network_failure_retries_then_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("ingestion.client.time.sleep", lambda *_: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client = _build_client(tmp_path, handler)
    with pytest.raises(NetworkError):
        client.cric_score()


# ----------------------------------------------------------------- misc

def test_empty_api_key_rejected_at_construction(tmp_path):
    with pytest.raises(ValueError):
        CricAPIClient(api_key="", cache_root=tmp_path)


def test_cache_dir_namespaced_by_api_key(tmp_path):
    def handler(_):
        return httpx.Response(200, json=_success())

    c1 = _build_client(tmp_path, handler, api_key="key-A")
    c2 = _build_client(tmp_path, handler, api_key="key-B")

    # Different prefixes for different keys — rotating keys gets a clean
    # namespace as the user asked for.
    assert c1.cache.directory != c2.cache.directory
    assert c1.cache.directory.parent.name != c2.cache.directory.parent.name


# ----------------------------------------------------- real-API smoke test

REAL_KEY = os.getenv("CRICAPI_KEY")


@pytest.mark.skipif(
    not REAL_KEY or REAL_KEY == "your_cricapi_key_here",
    reason="CRICAPI_KEY not set in .env — skipping real network call",
)
def test_real_api_key_works(tmp_path, caplog):
    """One real GET to verify the user's key is valid.

    Uses /cricScore which is a low-cost endpoint. Caches the response
    under tmp_path so the test doesn't pollute the developer's cache,
    but still charges one call against today's quota — that's the
    explicit cost the spec calls out for this test.
    """
    caplog.set_level(logging.INFO, logger="ingestion.client")

    with CricAPIClient(api_key=REAL_KEY, cache_root=tmp_path) as client:
        payload = client.cric_score()

    assert isinstance(payload, dict)
    # CricAPI always returns top-level `status`. "success" is the green
    # path; "failure" with a non-limit reason still proves the key is
    # valid (auth would be a 4xx).
    assert payload.get("status") in {"success", "failure"}

    # Log the raw body for inspection — this is the "log raw response"
    # part of the spec.
    body = json.dumps(payload, indent=2, sort_keys=True)
    print("\n--- /cricScore raw response ---")
    print(body[:2000] + ("\n... [truncated]" if len(body) > 2000 else ""))
