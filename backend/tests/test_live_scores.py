"""Tests for the live scores service and router.

Strategy:
  - Patch httpx.AsyncClient at the service level so tests never make
    real network calls.
  - Reset the module-level cache before each test to avoid order
    dependence.
  - Cover: no API key, network failure, women's filter, is_live flag,
    graceful API error status.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.live_scores as svc
from app.schemas.live import LiveScoreResponse


@pytest.fixture(autouse=True)
def reset_cache():
    svc._cache["response"] = None
    svc._cache["at"] = 0.0
    yield
    svc._cache["response"] = None
    svc._cache["at"] = 0.0


def _mock_client(payload: dict):
    """Build an AsyncMock httpx.AsyncClient that returns `payload`."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=mock_resp)
    return client


class TestLiveScoresService:

    @pytest.mark.asyncio
    async def test_no_api_key_returns_unavailable(self, monkeypatch):
        monkeypatch.delenv("CRICAPI_KEY", raising=False)
        result = await svc.get_live_scores()
        assert result.live_available is False
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_network_failure_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch("app.services.live_scores.httpx.AsyncClient", return_value=client):
            result = await svc.get_live_scores()

        assert result.live_available is False
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_api_error_status_returns_unavailable(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        payload = {"status": "failure", "reason": "Quota exhausted"}

        with patch(
            "app.services.live_scores.httpx.AsyncClient",
            return_value=_mock_client(payload),
        ):
            result = await svc.get_live_scores()

        assert result.live_available is False

    @pytest.mark.asyncio
    async def test_womens_matches_filtered_out(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        payload = {
            "status": "success",
            "data": [
                {
                    "id": "w1",
                    "name": "England Women vs Australia Women, 1st T20I",
                    "matchType": "t20",
                    "status": "In Progress",
                    "venue": "Lord's",
                    "teams": ["England Women", "Australia Women"],
                    "score": [],
                    "matchStarted": True,
                    "matchEnded": False,
                },
                {
                    "id": "m1",
                    "name": "Pakistan vs India, 1st T20I",
                    "matchType": "t20",
                    "status": "In Progress",
                    "venue": "Lahore",
                    "teams": ["Pakistan", "India"],
                    "score": [],
                    "matchStarted": True,
                    "matchEnded": False,
                },
            ],
        }

        with patch(
            "app.services.live_scores.httpx.AsyncClient",
            return_value=_mock_client(payload),
        ):
            result = await svc.get_live_scores()

        assert result.live_available is True
        assert len(result.matches) == 1
        assert result.matches[0].name == "Pakistan vs India, 1st T20I"

    @pytest.mark.asyncio
    async def test_is_live_flag_set_correctly(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        payload = {
            "status": "success",
            "data": [
                {
                    "id": "fin",
                    "name": "Pakistan vs India, Final",
                    "matchType": "t20",
                    "status": "Pakistan won by 5 wickets",
                    "venue": "Lahore",
                    "teams": ["Pakistan", "India"],
                    "score": [
                        {"r": 180, "w": 6, "o": 20.0, "inning": "India Inning 1"},
                        {"r": 181, "w": 5, "o": 19.4, "inning": "Pakistan Inning 1"},
                    ],
                    "matchStarted": True,
                    "matchEnded": True,  # finished — is_live must be False
                },
                {
                    "id": "live",
                    "name": "Australia vs England, 2nd ODI",
                    "matchType": "odi",
                    "status": "Australia need 45 runs from 60 balls",
                    "venue": "MCG",
                    "teams": ["Australia", "England"],
                    "score": [],
                    "matchStarted": True,
                    "matchEnded": False,  # live
                },
            ],
        }

        with patch(
            "app.services.live_scores.httpx.AsyncClient",
            return_value=_mock_client(payload),
        ):
            result = await svc.get_live_scores()

        assert result.live_available is True
        assert len(result.matches) == 2

        finished = next(m for m in result.matches if m.match_id == "fin")
        live = next(m for m in result.matches if m.match_id == "live")
        assert finished.is_live is False
        assert live.is_live is True

    @pytest.mark.asyncio
    async def test_scores_parsed_correctly(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        payload = {
            "status": "success",
            "data": [
                {
                    "id": "s1",
                    "name": "Pakistan vs India, 1st Test",
                    "matchType": "test",
                    "status": "Day 2 - India lead by 40 runs",
                    "venue": "Karachi",
                    "teams": ["Pakistan", "India"],
                    "score": [
                        {"r": 320, "w": 10, "o": 95.3, "inning": "Pakistan Inning 1"},
                        {"r": 200, "w": 4, "o": 55.0, "inning": "India Inning 1"},
                    ],
                    "matchStarted": True,
                    "matchEnded": False,
                },
            ],
        }

        with patch(
            "app.services.live_scores.httpx.AsyncClient",
            return_value=_mock_client(payload),
        ):
            result = await svc.get_live_scores()

        m = result.matches[0]
        assert m.scores["Pakistan"] == "320/10 (95.3 ov)"
        assert m.scores["India"] == "200/4 (55.0 ov)"

    @pytest.mark.asyncio
    async def test_cache_prevents_second_call(self, monkeypatch):
        monkeypatch.setenv("CRICAPI_KEY", "test-key")
        payload = {"status": "success", "data": []}
        client = _mock_client(payload)

        with patch(
            "app.services.live_scores.httpx.AsyncClient", return_value=client
        ):
            await svc.get_live_scores()
            await svc.get_live_scores()

        # get() called exactly once — second request hit the cache.
        assert client.get.call_count == 1
