"""Smoke tests for player/match/single-player-analytics routers.

Per the user's instruction, /compare got the deep treatment in
test_analytics_compare.py. The remaining endpoints are simpler
CRUD/aggregation, so this file focuses on:

  * Status codes are correct (200 / 404 / 422).
  * Response shape matches the schema (Pydantic does the heavy lifting).
  * One sanity check per endpoint that the SQL is right.

Reuses the same async_db_session + ASGITransport pattern from the
/compare tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BattingStats, Match, Player
from app.models.enums import MatchType, PlayerRole, TossDecision
from app.routers import analytics, matches, players


@pytest.fixture
def app(async_db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(players.router, prefix="/api/v1")
    app.include_router(matches.router, prefix="/api/v1")
    app.include_router(analytics.router, prefix="/api/v1")

    async def _override_get_db():
        yield async_db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ====================================================================
# /players
# ====================================================================

class TestPlayersRouter:

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/players")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_search_substring_match(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        for nm in ["Babar Azam", "Mohammad Rizwan", "Virat Kohli"]:
            async_db_session.add(Player(
                external_id=f"ext-{nm}", name=nm, country="Pakistan",
                role=PlayerRole.BATSMAN,
            ))
        await async_db_session.commit()

        resp = await client.get("/api/v1/players/search?name=babar")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "Babar Azam" in names
        assert "Virat Kohli" not in names

    @pytest.mark.asyncio
    async def test_test_nations_filter_excludes_associates(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        # Two players share the same name but represent different nations.
        # Default test_nations_only=true must return only the Pakistani
        # entry; opting out must return both.
        async_db_session.add_all([
            Player(
                external_id="ext-shaheen-pk",
                name="Shaheen Afridi",
                country="Pakistan",
                role=PlayerRole.BOWLER,
            ),
            Player(
                external_id="ext-shaheen-ls",
                name="Shaheen Afridi",
                country="Lesotho",
                role=PlayerRole.BOWLER,
            ),
        ])
        await async_db_session.commit()

        # Default (test_nations_only=true) → Pakistan only.
        resp = await client.get("/api/v1/players")
        assert resp.status_code == 200
        countries = sorted(p["country"] for p in resp.json())
        assert countries == ["Pakistan"]

        # Opt-out → both rows.
        resp = await client.get("/api/v1/players?test_nations_only=false")
        assert resp.status_code == 200
        countries = sorted(p["country"] for p in resp.json())
        assert countries == ["Lesotho", "Pakistan"]

        # /search default → Pakistan only.
        resp = await client.get("/api/v1/players/search?name=shaheen")
        assert resp.status_code == 200
        countries = sorted(p["country"] for p in resp.json())
        assert countries == ["Pakistan"]

        # /search opt-out → both rows.
        resp = await client.get(
            "/api/v1/players/search?name=shaheen&test_nations_only=false"
        )
        assert resp.status_code == 200
        countries = sorted(p["country"] for p in resp.json())
        assert countries == ["Lesotho", "Pakistan"]

    @pytest.mark.asyncio
    async def test_get_one_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/players/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_player_stats_with_format(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar = Player(
            external_id="ext-babar", name="Babar Azam",
            country="Pakistan", role=PlayerRole.BATSMAN,
        )
        async_db_session.add(babar)
        await async_db_session.flush()
        # 6 T20I innings of 50 runs each → average 50, no warning
        for i in range(6):
            m = Match(
                external_id=f"m-{i}",
                match_type=MatchType.T20I,
                date=datetime(2025, 5, 1 + i, tzinfo=timezone.utc),
                team1="Pakistan",
                team2="India",
                toss_winner="Pakistan",
                toss_decision=TossDecision.BAT,
            )
            async_db_session.add(m)
            await async_db_session.flush()
            async_db_session.add(BattingStats(
                player_id=babar.id, match_id=m.id,
                runs=50, balls_faced=35, fours=4, sixes=1,
                strike_rate=142.86, dismissal_type="bowled",
                innings_number=1,
            ))
        await async_db_session.commit()

        resp = await client.get(
            f"/api/v1/players/{babar.id}/stats?format=T20I"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["primary_role"] == "batsman"
        assert body["batting"]["innings"] == 6
        assert body["batting"]["runs"] == 300


# ====================================================================
# /matches
# ====================================================================

class TestMatchesRouter:

    @pytest.mark.asyncio
    async def test_list_with_filters(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        for i, fmt in enumerate((MatchType.T20I, MatchType.T20I, MatchType.ODI)):
            async_db_session.add(Match(
                external_id=f"m-{fmt.value}-{i}",
                match_type=fmt,
                date=datetime(2025, 1, 1 + i, tzinfo=timezone.utc),
                team1="Pakistan", team2="India",
            ))
        await async_db_session.commit()

        resp = await client.get("/api/v1/matches?format=T20I")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_recent_caps(self, client: AsyncClient):
        resp = await client.get("/api/v1/matches/recent")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_one_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/matches/9999")
        assert resp.status_code == 404


# ====================================================================
# /analytics single-player + venue + h2h
# ====================================================================

class TestAnalyticsExtras:

    @pytest.mark.asyncio
    async def test_player_average_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/analytics/player/9999/average")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_player_form_requires_format(self, client: AsyncClient):
        resp = await client.get("/api/v1/analytics/player/1/form")
        # Missing format → 422 from FastAPI's parameter validation.
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_head_to_head_with_data(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        # 5 Pakistan-India T20Is — Pakistan won 3.
        for i in range(5):
            async_db_session.add(Match(
                external_id=f"m-pi-{i}",
                match_type=MatchType.T20I,
                date=datetime(2025, 1, 1 + i, tzinfo=timezone.utc),
                team1="Pakistan", team2="India",
                toss_winner="Pakistan", toss_decision=TossDecision.BAT,
                winner="Pakistan" if i < 3 else "India",
            ))
        await async_db_session.commit()

        resp = await client.get(
            "/api/v1/analytics/head-to-head?team1=Pakistan&team2=India&format=T20I"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_matches"] == 5
        assert body["team1_wins"] == 3
        assert body["team2_wins"] == 2

    @pytest.mark.asyncio
    async def test_head_to_head_same_team_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/analytics/head-to-head?team1=Pakistan&team2=Pakistan&format=T20I"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_venue_stats_empty(self, client: AsyncClient):
        # Empty DB → 200 with matches=0, all percentages null.
        resp = await client.get("/api/v1/analytics/venue?ground=Lahore")
        assert resp.status_code == 200
        body = resp.json()
        assert body["matches"] == 0
        assert body["bat_first_win_pct"] is None
