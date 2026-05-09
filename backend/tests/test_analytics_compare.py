"""Phase 4.3 — comprehensive tests for the flagship /compare endpoint.

This is THE endpoint that gets demoed and screenshotted. It must:

  * Validate format strictly (router returns 422 for bogus values).
  * Resolve player ids (404 when missing).
  * Reject self-comparison (422 — almost always a frontend bug).
  * Handle batter-vs-batter, bowler-vs-bowler, and all-rounder cases
    correctly — primary_role must be honoured so the dashboard
    knows which panel to lead with.
  * Cap form_guide at 10, ordered most-recent-first.
  * Compute career stats accurately (avg / SR / 50s / 100s).
  * Surface common opponents with per-opponent stat rollups.
  * Emit data_quality warnings when innings < 5 instead of returning
    a misleading two-innings average.

The test app constructs a fresh FastAPI instance with just the
analytics router mounted, overrides get_db to inject the
async test session, and drives requests via httpx.AsyncClient with
ASGITransport. No HTTP socket required.
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
from app.models import BattingStats, BowlingStats, Match, Player
from app.models.enums import MatchType, PlayerRole, TossDecision
from app.routers import analytics


# ====================================================================
# Test data factory
# ====================================================================

async def _make_player(
    session: AsyncSession,
    *,
    name: str,
    country: str,
    role: PlayerRole | None,
    batting_style: str | None = "Right-hand bat",
    bowling_style: str | None = None,
) -> Player:
    p = Player(
        external_id=f"ext-{name.lower().replace(' ', '-')}",
        name=name,
        country=country,
        role=role,
        batting_style=batting_style,
        bowling_style=bowling_style,
    )
    session.add(p)
    await session.flush()
    return p


async def _make_match(
    session: AsyncSession,
    *,
    external_id: str,
    fmt: MatchType,
    team1: str,
    team2: str,
    date: datetime,
    winner: str | None = None,
) -> Match:
    m = Match(
        external_id=external_id,
        match_type=fmt,
        venue="TestVenue",
        ground="TestGround",
        date=date,
        team1=team1,
        team2=team2,
        winner=winner,
        toss_winner=team1,
        toss_decision=TossDecision.BAT,
    )
    session.add(m)
    await session.flush()
    return m


async def _bat(
    session: AsyncSession,
    *,
    player: Player,
    match: Match,
    runs: int,
    balls: int = 30,
    innings: int = 1,
    not_out: bool = False,
    fours: int = 4,
    sixes: int = 1,
) -> None:
    sr = round((runs / balls) * 100, 2) if balls > 0 else None
    session.add(
        BattingStats(
            player_id=player.id,
            match_id=match.id,
            runs=runs,
            balls_faced=balls,
            fours=fours,
            sixes=sixes,
            strike_rate=sr,
            dismissal_type=None if not_out else "c keeper b bowler",
            innings_number=innings,
            position=3,
        )
    )


async def _bowl(
    session: AsyncSession,
    *,
    player: Player,
    match: Match,
    overs: float = 4.0,
    wickets: int = 2,
    runs_conceded: int = 28,
    innings: int = 1,
) -> None:
    eco = round(runs_conceded / overs, 2) if overs > 0 else None
    session.add(
        BowlingStats(
            player_id=player.id,
            match_id=match.id,
            overs=overs,
            maidens=0,
            runs_conceded=runs_conceded,
            wickets=wickets,
            economy_rate=eco,
            innings_number=innings,
        )
    )


# ====================================================================
# Test app
# ====================================================================

@pytest.fixture
def app(async_db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    app.include_router(analytics.router, prefix="/api/v1")

    async def _override_get_db():
        # Yield the SAME session the test fixtures populated. Don't
        # commit/rollback inside this dependency — the fixture
        # manages the session lifecycle.
        yield async_db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ====================================================================
# Format validation
# ====================================================================

class TestFormatValidation:
    """Per the user contract: format must be strictly validated at
    the router level, not silently default to empty stats."""

    @pytest.mark.asyncio
    async def test_invalid_format_returns_422(self, client: AsyncClient):
        # FastAPI's Query+enum validation produces a 422 with a clear
        # 'value must be one of [T20I, ODI, Test, T20]' message.
        resp = await client.get(
            "/api/v1/analytics/compare?player1_id=1&player2_id=2&format=IPL"
        )
        assert resp.status_code == 422
        body = resp.json()
        # The error payload must surface the valid enum members so the
        # client can correct itself.
        as_text = str(body).lower()
        assert "t20i" in as_text or "test" in as_text or "odi" in as_text

    @pytest.mark.asyncio
    async def test_missing_format_returns_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/analytics/compare?player1_id=1&player2_id=2"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_player_param_returns_422(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/analytics/compare?player1_id=1&format=T20I"
        )
        assert resp.status_code == 422


# ====================================================================
# 404 / 422 for player IDs
# ====================================================================

class TestPlayerIdValidation:

    @pytest.mark.asyncio
    async def test_unknown_player_returns_404(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        # Player IDs 999 and 1000 don't exist in the empty test DB.
        resp = await client.get(
            "/api/v1/analytics/compare?player1_id=999&player2_id=1000&format=T20I"
        )
        assert resp.status_code == 404
        assert "999" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_self_comparison_returns_422(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar = await _make_player(
            async_db_session, name="Babar Azam",
            country="Pakistan", role=PlayerRole.BATSMAN,
        )
        await async_db_session.commit()
        resp = await client.get(
            f"/api/v1/analytics/compare?player1_id={babar.id}&player2_id={babar.id}&format=T20I"
        )
        assert resp.status_code == 422
        assert "differ" in resp.json()["detail"].lower()


# ====================================================================
# Batter-vs-batter happy path
# ====================================================================

class TestBatterVsBatter:

    async def _seed(
        self, session: AsyncSession
    ) -> tuple[Player, Player]:
        babar = await _make_player(
            session, name="Babar Azam", country="Pakistan",
            role=PlayerRole.BATSMAN,
        )
        kohli = await _make_player(
            session, name="Virat Kohli", country="India",
            role=PlayerRole.BATSMAN,
        )

        # Pakistan vs India T20I — both played; same opponent on both
        # sides exercises the common-opponents code path.
        for i in range(8):
            m_pak_ind = await _make_match(
                session,
                external_id=f"m-pi-{i}",
                fmt=MatchType.T20I,
                team1="Pakistan",
                team2="India",
                date=datetime(2025, 1, 10 + i, tzinfo=timezone.utc),
                winner="Pakistan" if i % 2 == 0 else "India",
            )
            await _bat(session, player=babar, match=m_pak_ind, runs=50 + i, balls=35)
            await _bat(session, player=kohli, match=m_pak_ind, runs=45 + i, balls=33)

        # And each plays 5 more T20Is vs different opponents (England,
        # Australia) — used to verify the "common" filter actually
        # filters and doesn't return ALL opponents.
        for i in range(5):
            m_pak_eng = await _make_match(
                session,
                external_id=f"m-pe-{i}",
                fmt=MatchType.T20I,
                team1="Pakistan",
                team2="England",
                date=datetime(2024, 7, 1 + i, tzinfo=timezone.utc),
            )
            await _bat(session, player=babar, match=m_pak_eng, runs=30 + i, balls=22)

        for i in range(5):
            m_ind_aus = await _make_match(
                session,
                external_id=f"m-ia-{i}",
                fmt=MatchType.T20I,
                team1="India",
                team2="Australia",
                date=datetime(2024, 8, 1 + i, tzinfo=timezone.utc),
            )
            await _bat(session, player=kohli, match=m_ind_aus, runs=40 + i, balls=28)

        await session.commit()
        return babar, kohli

    @pytest.mark.asyncio
    async def test_response_shape_for_two_batters(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar, kohli = await self._seed(async_db_session)

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={babar.id}&player2_id={kohli.id}&format=T20I"
        )
        assert resp.status_code == 200
        body = resp.json()

        # Required top-level shape.
        assert body["format"] == "T20I"
        assert "player1" in body and "player2" in body
        assert "common_opponents" in body
        assert "data_quality" in body

        # Both slots: batting populated, bowling NOT (pure batters).
        assert body["player1"]["batting"] is not None
        assert body["player1"]["bowling"] is None
        assert body["player2"]["batting"] is not None
        assert body["player2"]["bowling"] is None

        # primary_role surfaced per side.
        assert body["player1"]["profile"]["primary_role"] == "batsman"
        assert body["player2"]["profile"]["primary_role"] == "batsman"

    @pytest.mark.asyncio
    async def test_career_stats_computed_correctly(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar, kohli = await self._seed(async_db_session)

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={babar.id}&player2_id={kohli.id}&format=T20I"
        )
        body = resp.json()
        babar_bat = body["player1"]["batting"]
        # 8 matches vs India (runs 50..57) + 5 matches vs England (30..34)
        # = 13 innings total, all out (no not-outs in fixtures).
        assert babar_bat["matches"] == 13
        assert babar_bat["innings"] == 13
        # 50+51+...+57 = 428 + 30+31+...+34 = 160 → 588
        assert babar_bat["runs"] == 588
        # 0 not-outs → average = 588 / 13 = 45.23
        assert babar_bat["average"] == pytest.approx(45.23, abs=0.01)

    @pytest.mark.asyncio
    async def test_form_guide_capped_and_ordered(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar, kohli = await self._seed(async_db_session)
        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={babar.id}&player2_id={kohli.id}&format=T20I"
        )
        body = resp.json()
        form = body["player1"]["form_guide"]
        assert len(form) <= 10  # cap
        assert len(form) >= 5  # we seeded 13 innings, expect 10
        # Most-recent-first ordering.
        dates = [entry["date"] for entry in form]
        assert dates == sorted(dates, reverse=True)
        # Each entry has the batting half populated.
        for entry in form:
            assert entry["batting_runs"] is not None
            assert entry["bowling_wickets"] is None

    @pytest.mark.asyncio
    async def test_common_opponents_only_includes_shared(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        babar, kohli = await self._seed(async_db_session)
        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={babar.id}&player2_id={kohli.id}&format=T20I"
        )
        body = resp.json()
        opponents = {block["opponent"] for block in body["common_opponents"]}
        # Babar faced India + England; Kohli faced Pakistan + Australia.
        # Common-opponent intersection is empty here because Babar's
        # opponents (India, England) and Kohli's (Pakistan, Australia)
        # don't overlap. India is excluded as Kohli's own country,
        # Pakistan as Babar's own. So common is empty.
        assert opponents == set(), f"unexpected common opponents: {opponents}"


# ====================================================================
# Bowler-vs-bowler
# ====================================================================

class TestBowlerVsBowler:

    @pytest.mark.asyncio
    async def test_pure_bowlers_show_only_bowling(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        shaheen = await _make_player(
            async_db_session, name="Shaheen Afridi",
            country="Pakistan", role=PlayerRole.BOWLER,
            batting_style=None, bowling_style="Left-arm fast",
        )
        bumrah = await _make_player(
            async_db_session, name="Jasprit Bumrah",
            country="India", role=PlayerRole.BOWLER,
            batting_style=None, bowling_style="Right-arm fast",
        )

        for i in range(6):
            m = await _make_match(
                async_db_session, external_id=f"m-bb-{i}",
                fmt=MatchType.ODI, team1="Pakistan", team2="India",
                date=datetime(2025, 3, 1 + i, tzinfo=timezone.utc),
            )
            await _bowl(async_db_session, player=shaheen, match=m, wickets=2)
            await _bowl(async_db_session, player=bumrah, match=m, wickets=3)
        await async_db_session.commit()

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={shaheen.id}&player2_id={bumrah.id}&format=ODI"
        )
        assert resp.status_code == 200
        body = resp.json()
        # Bowling populated, batting None — primary_role drives this.
        assert body["player1"]["bowling"] is not None
        assert body["player1"]["batting"] is None
        assert body["player2"]["batting"] is None
        assert body["player1"]["profile"]["primary_role"] == "bowler"


# ====================================================================
# All-rounder
# ====================================================================

class TestAllRounder:

    @pytest.mark.asyncio
    async def test_all_rounder_shows_both_panels(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        shadab = await _make_player(
            async_db_session, name="Shadab Khan",
            country="Pakistan", role=PlayerRole.ALL_ROUNDER,
        )
        # Pair with a batter to exercise mixed-role comparison.
        kohli = await _make_player(
            async_db_session, name="Virat Kohli",
            country="India", role=PlayerRole.BATSMAN,
        )

        for i in range(7):
            m = await _make_match(
                async_db_session, external_id=f"m-ar-{i}",
                fmt=MatchType.T20I, team1="Pakistan", team2="India",
                date=datetime(2025, 4, 1 + i, tzinfo=timezone.utc),
            )
            # Shadab bats AND bowls.
            await _bat(async_db_session, player=shadab, match=m, runs=18 + i, balls=12)
            await _bowl(async_db_session, player=shadab, match=m, wickets=1)
            await _bat(async_db_session, player=kohli, match=m, runs=40 + i, balls=28)
        await async_db_session.commit()

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={shadab.id}&player2_id={kohli.id}&format=T20I"
        )
        assert resp.status_code == 200
        body = resp.json()
        # Shadab gets BOTH panels. Kohli gets only batting.
        assert body["player1"]["batting"] is not None
        assert body["player1"]["bowling"] is not None
        assert body["player1"]["profile"]["primary_role"] == "allrounder"
        assert body["player2"]["batting"] is not None
        assert body["player2"]["bowling"] is None


# ====================================================================
# Data-quality threshold
# ====================================================================

class TestDataQualityThreshold:
    """Per the user contract: <5 innings produces a 200 with a
    data_quality warning, NOT a 404 or a misleading two-innings avg."""

    @pytest.mark.asyncio
    async def test_few_innings_attaches_warning(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        thin = await _make_player(
            async_db_session, name="New Guy",
            country="Pakistan", role=PlayerRole.BATSMAN,
        )
        veteran = await _make_player(
            async_db_session, name="Old Hand",
            country="India", role=PlayerRole.BATSMAN,
        )
        # Thin player has only 3 innings (< 5 threshold).
        for i in range(3):
            m = await _make_match(
                async_db_session, external_id=f"m-thin-{i}",
                fmt=MatchType.T20I, team1="Pakistan", team2="India",
                date=datetime(2025, 5, 1 + i, tzinfo=timezone.utc),
            )
            await _bat(async_db_session, player=thin, match=m, runs=20 + i, balls=15)
            await _bat(async_db_session, player=veteran, match=m, runs=50 + i, balls=35)
        # Veteran has 6 more innings vs other opponents to clear threshold.
        for i in range(6):
            m = await _make_match(
                async_db_session, external_id=f"m-vet-{i}",
                fmt=MatchType.T20I, team1="India", team2="England",
                date=datetime(2025, 6, 1 + i, tzinfo=timezone.utc),
            )
            await _bat(async_db_session, player=veteran, match=m, runs=60 + i, balls=42)
        await async_db_session.commit()

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={thin.id}&player2_id={veteran.id}&format=T20I"
        )
        # Critically: 200, NOT 404. The dashboard renders the data
        # alongside the warning rather than hiding it.
        assert resp.status_code == 200
        body = resp.json()
        # Player1 (thin) should have a warning; player2 (veteran) should not.
        warning_codes = [w["code"] for w in body["data_quality"]]
        assert any("player1" in c for c in warning_codes)
        assert not any("player2" in c for c in warning_codes)
        # Stats are still populated — dashboard chooses how to display.
        assert body["player1"]["batting"]["innings"] == 3

    @pytest.mark.asyncio
    async def test_above_threshold_no_warning(
        self, client: AsyncClient, async_db_session: AsyncSession
    ):
        a = await _make_player(
            async_db_session, name="A", country="Pakistan",
            role=PlayerRole.BATSMAN,
        )
        b = await _make_player(
            async_db_session, name="B", country="India",
            role=PlayerRole.BATSMAN,
        )
        for i in range(7):
            m = await _make_match(
                async_db_session, external_id=f"m-ab-{i}",
                fmt=MatchType.T20I, team1="Pakistan", team2="India",
                date=datetime(2025, 7, 1 + i, tzinfo=timezone.utc),
            )
            await _bat(async_db_session, player=a, match=m, runs=40 + i)
            await _bat(async_db_session, player=b, match=m, runs=35 + i)
        await async_db_session.commit()

        resp = await client.get(
            f"/api/v1/analytics/compare"
            f"?player1_id={a.id}&player2_id={b.id}&format=T20I"
        )
        body = resp.json()
        # Both players have 7 innings, above threshold, so no warnings.
        assert body["data_quality"] == []
