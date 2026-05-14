"""Phase 4.2 — Pydantic schema tests.

Three concerns:

  1. Every schema instantiates cleanly with realistic sample data and
     serialises to JSON without losing fields.
  2. Validators actually reject bad inputs (negative runs, wickets > 10,
     etc.) — guards against future field-by-field schema drift.
  3. The flagship `ComparisonResponse` round-trips through
     model_validate(model_dump()), which is what FastAPI does
     internally, so any nested-shape regression surfaces here.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.enums import MatchType, PlayerRole, TossDecision
from app.schemas import (
    BattingCareerStats,
    BattingStatsResponse,
    BowlerPhaseStats,
    BowlerPhasesResponse,
    BowlingCareerStats,
    BowlingStatsResponse,
    CommonOpponentBlock,
    ComparisonResponse,
    FormatBreakdown,
    FormGuideEntry,
    FormGuideResponse,
    HeadToHeadResponse,
    MatchResponse,
    PlayerAverageResponse,
    PlayerComparisonSlot,
    PlayerProfileCard,
    PlayerResponse,
    PlayerWithStats,
    VenueStatsResponse,
)


# ====================================================================
# Helpers — build realistic sample data once, reuse in many tests
# ====================================================================

def _profile(player_id: int = 1, role: PlayerRole = PlayerRole.BATSMAN) -> PlayerProfileCard:
    return PlayerProfileCard(
        id=player_id,
        external_id=f"p-{player_id}",
        name=f"Player {player_id}",
        country="Pakistan",
        role=role,
        primary_role=role,
        batting_style="Right-hand bat",
        bowling_style=None,
    )


def _batting() -> BattingCareerStats:
    return BattingCareerStats(
        matches=120,
        innings=115,
        not_outs=12,
        runs=4500,
        average=43.69,
        strike_rate=132.5,
        fifties=28,
        hundreds=10,
        highest_score=158,
        fours=420,
        sixes=82,
    )


def _bowling() -> BowlingCareerStats:
    return BowlingCareerStats(
        matches=80,
        innings=78,
        overs_bowled=720.4,
        runs_conceded=4900,
        wickets=145,
        average=33.79,
        economy=6.81,
        bowling_strike_rate=29.8,
        five_wicket_hauls=2,
        best_figures="6/35",
    )


def _form_entry(idx: int) -> FormGuideEntry:
    return FormGuideEntry(
        match_external_id=f"m-{idx}",
        date=datetime(2025, 9, 20 - idx, tzinfo=timezone.utc),
        opponent="India",
        venue="Lahore",
        match_type=MatchType.T20I,
        batting_runs=50 + idx,
        batting_balls=30 + idx,
        batting_strike_rate=round((50 + idx) / max(30 + idx, 1) * 100, 2),
        not_out=False,
    )


# ====================================================================
# Profile card
# ====================================================================

class TestProfileCard:
    def test_basic_round_trip(self):
        card = _profile()
        dumped = card.model_dump()
        rebuilt = PlayerProfileCard.model_validate(dumped)
        assert rebuilt == card

    def test_primary_role_is_required(self):
        with pytest.raises(ValidationError):
            PlayerProfileCard(
                id=1,
                external_id="p-1",
                name="X",
                country="Pakistan",
                role=PlayerRole.BATSMAN,
                # primary_role omitted on purpose — schema MUST require
                # it so the dashboard never has to guess from stats.
                batting_style="RHB",
            )


# ====================================================================
# Career rollups
# ====================================================================

class TestCareerRollups:
    def test_batting_serializes_with_nulls(self):
        bs = BattingCareerStats(
            matches=10,
            innings=5,
            not_outs=5,  # all not-outs → average is undefined
            runs=200,
            average=None,
            strike_rate=None,
            fifties=2,
            hundreds=0,
            highest_score=85,
            fours=18,
            sixes=2,
        )
        # null distinct from "0" — JSON output should still emit "average": null
        assert "average" in bs.model_dump()

    def test_batting_rejects_negative_runs(self):
        with pytest.raises(ValidationError):
            BattingCareerStats(
                matches=1, innings=1, not_outs=0,
                runs=-5,
                fifties=0, hundreds=0, highest_score=0, fours=0, sixes=0,
            )

    def test_bowling_rejects_more_than_ten_wickets_in_an_innings_metric(self):
        # five_wicket_hauls is a counter so >10 is fine, but any
        # per-innings wicket field on the per-row schemas caps at 10.
        with pytest.raises(ValidationError):
            BowlingStatsResponse(
                id=1, player_id=1, match_id=1,
                overs=4, maidens=0, runs_conceded=20, wickets=11,
                innings_number=1,
            )

    def test_bowling_career_stats_has_wickets_per_match_and_dot_ball_pct(self):
        # New fields added in Feature 1 for the bowling radar.
        # wickets_per_match must accept a non-negative float OR null.
        # dot_ball_pct is reserved-null (no ball-by-ball storage yet)
        # but must be representable and constrained to [0, 100].
        bs = BowlingCareerStats(
            matches=10,
            innings=10,
            overs_bowled=40.0,
            runs_conceded=200,
            wickets=15,
            average=13.33,
            economy=5.0,
            bowling_strike_rate=16.0,
            wickets_per_match=1.5,
            dot_ball_pct=None,
            five_wicket_hauls=1,
            best_figures="4/22",
        )
        assert bs.wickets_per_match == 1.5
        assert bs.dot_ball_pct is None

        # And the defaults: omitting both should still construct cleanly.
        bs_defaults = BowlingCareerStats(
            matches=0, innings=0, overs_bowled=0, runs_conceded=0, wickets=0,
            five_wicket_hauls=0,
        )
        assert bs_defaults.wickets_per_match is None
        assert bs_defaults.dot_ball_pct is None

    def test_dot_ball_pct_rejects_values_above_100(self):
        with pytest.raises(ValidationError):
            BowlingCareerStats(
                matches=10, innings=10, overs_bowled=40.0,
                runs_conceded=200, wickets=15,
                five_wicket_hauls=1,
                dot_ball_pct=150.0,  # out of [0, 100]
            )


# ====================================================================
# FormGuideEntry — both halves nullable, mutually independent
# ====================================================================

class TestFormGuideEntry:
    def test_batting_only(self):
        e = _form_entry(0)
        assert e.batting_runs is not None
        assert e.bowling_wickets is None

    def test_bowling_only(self):
        e = FormGuideEntry(
            match_external_id="m-1",
            date=datetime(2025, 9, 19, tzinfo=timezone.utc),
            opponent="India",
            match_type=MatchType.T20I,
            bowling_overs=4,
            bowling_wickets=2,
            bowling_runs_conceded=22,
            bowling_economy=5.5,
        )
        assert e.batting_runs is None
        assert e.bowling_wickets == 2


# ====================================================================
# ComparisonResponse — flagship shape, designed first
# ====================================================================

class TestComparisonResponse:

    def _build_slot(self, player_id: int, role: PlayerRole) -> PlayerComparisonSlot:
        # All-rounder slot has both batting and bowling; pure-batter
        # has just batting; pure-bowler has just bowling.
        return PlayerComparisonSlot(
            profile=_profile(player_id, role=role),
            batting=_batting() if role != PlayerRole.BOWLER else None,
            bowling=_bowling() if role != PlayerRole.BATSMAN else None,
            form_guide=[_form_entry(i) for i in range(10)],
        )

    def test_batter_vs_batter(self):
        resp = ComparisonResponse(
            format=MatchType.T20I,
            player1=self._build_slot(1, PlayerRole.BATSMAN),
            player2=self._build_slot(2, PlayerRole.BATSMAN),
            common_opponents=[
                CommonOpponentBlock(
                    opponent="India",
                    player1_matches=12,
                    player2_matches=15,
                    player1_batting_average=58.2,
                    player1_batting_strike_rate=145.3,
                    player2_batting_average=44.1,
                    player2_batting_strike_rate=139.7,
                ),
            ],
        )
        # Both slots have batting, neither has bowling.
        assert resp.player1.batting is not None
        assert resp.player1.bowling is None
        assert resp.player2.bowling is None
        assert resp.player1.profile.primary_role is PlayerRole.BATSMAN

    def test_bowler_vs_bowler(self):
        resp = ComparisonResponse(
            format=MatchType.ODI,
            player1=self._build_slot(1, PlayerRole.BOWLER),
            player2=self._build_slot(2, PlayerRole.BOWLER),
        )
        assert resp.player1.batting is None
        assert resp.player1.bowling is not None
        assert resp.player1.profile.primary_role is PlayerRole.BOWLER

    def test_all_rounder_has_both_panels(self):
        resp = ComparisonResponse(
            format=MatchType.TEST,
            player1=self._build_slot(1, PlayerRole.ALL_ROUNDER),
            player2=self._build_slot(2, PlayerRole.ALL_ROUNDER),
        )
        # All-rounders surface both panels — dashboard renders both.
        assert resp.player1.batting is not None
        assert resp.player1.bowling is not None
        assert resp.player1.profile.primary_role is PlayerRole.ALL_ROUNDER

    def test_form_guide_capped_at_ten(self):
        with pytest.raises(ValidationError):
            PlayerComparisonSlot(
                profile=_profile(),
                batting=_batting(),
                form_guide=[_form_entry(i) for i in range(11)],  # 11 > 10
            )

    def test_format_required(self):
        with pytest.raises(ValidationError):
            ComparisonResponse(
                # format omitted — must be required so we never serve
                # cross-format comparisons.
                player1=self._build_slot(1, PlayerRole.BATSMAN),
                player2=self._build_slot(2, PlayerRole.BATSMAN),
            )

    def test_round_trip_through_pydantic(self):
        original = ComparisonResponse(
            format=MatchType.T20I,
            player1=self._build_slot(1, PlayerRole.BATSMAN),
            player2=self._build_slot(2, PlayerRole.ALL_ROUNDER),
            common_opponents=[
                CommonOpponentBlock(
                    opponent="India",
                    player1_matches=12,
                    player2_matches=8,
                    player1_batting_average=52.7,
                    player2_bowling_wickets=14,
                    player2_bowling_economy=6.8,
                ),
            ],
        )
        # FastAPI internally does this dump-then-validate cycle for
        # every response. Catching shape regressions here is much
        # cheaper than catching them via curl.
        rebuilt = ComparisonResponse.model_validate(original.model_dump())
        assert rebuilt == original


# ====================================================================
# Single-player analytics
# ====================================================================

def test_player_average_response():
    resp = PlayerAverageResponse(
        profile=_profile(),
        by_format=[
            FormatBreakdown(format=MatchType.T20I, batting=_batting()),
            FormatBreakdown(format=MatchType.ODI, batting=_batting()),
            FormatBreakdown(format=MatchType.TEST, batting=_batting()),
        ],
    )
    assert len(resp.by_format) == 3


def test_form_guide_response_capped_at_ten():
    with pytest.raises(ValidationError):
        FormGuideResponse(
            profile=_profile(),
            innings=[_form_entry(i) for i in range(11)],
        )


def test_head_to_head_pct_constraint():
    # Win-percentage fields must be in [0, 100].
    with pytest.raises(ValidationError):
        HeadToHeadResponse(
            team1="Pakistan", team2="India", format=MatchType.T20I,
            total_matches=10, team1_wins=5, team2_wins=4, no_results=1,
            bat_first_win_pct=150.0,
        )


def test_venue_stats_response():
    v = VenueStatsResponse(
        ground="Gaddafi Stadium",
        matches=42,
        average_first_innings_score=178.4,
        bat_first_win_pct=58.0,
        bowl_first_win_pct=42.0,
    )
    assert v.matches == 42


def test_bowler_phases_literal():
    # phase is a Literal["powerplay","middle","death"] — anything else
    # must raise.
    with pytest.raises(ValidationError):
        BowlerPhaseStats(phase="closing", overs_bowled=4, wickets=2)


# ====================================================================
# Player and Match standalone schemas
# ====================================================================

def test_player_response_from_attributes():
    # Simulate an ORM row by using a duck-typed object — ConfigDict
    # has from_attributes=True so this should work.
    class _Row:
        id = 1
        external_id = "p-1"
        name = "Babar Azam"
        country = "Pakistan"
        role = PlayerRole.BATSMAN
        batting_style = "Right-hand bat"
        bowling_style = None
        date_of_birth = date(1994, 10, 15)
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resp = PlayerResponse.model_validate(_Row(), from_attributes=True)
    assert resp.name == "Babar Azam"
    assert resp.role is PlayerRole.BATSMAN


def test_match_response_from_attributes():
    class _Row:
        id = 1
        external_id = "m-1"
        match_type = MatchType.T20I
        venue = "Lahore"
        ground = "Gaddafi Stadium"
        date = datetime(2025, 9, 20, tzinfo=timezone.utc)
        team1 = "Pakistan"
        team2 = "England"
        winner = "Pakistan"
        toss_winner = "England"
        toss_decision = TossDecision.BOWL
        result_margin = "won by 7 wickets"
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    resp = MatchResponse.model_validate(_Row(), from_attributes=True)
    assert resp.match_type is MatchType.T20I
    assert resp.toss_decision is TossDecision.BOWL


def test_player_with_stats_includes_primary_role():
    pws = PlayerWithStats(
        id=1,
        external_id="p-1",
        name="Babar Azam",
        country="Pakistan",
        role=PlayerRole.BATSMAN,
        batting_style="Right-hand bat",
        bowling_style=None,
        date_of_birth=date(1994, 10, 15),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        primary_role=PlayerRole.BATSMAN,
        batting=_batting(),
        bowling=None,
    )
    assert pws.primary_role is PlayerRole.BATSMAN
    assert pws.batting is not None
    assert pws.bowling is None


# ====================================================================
# Per-row stats responses
# ====================================================================

def test_batting_stats_response_negative_runs_rejected():
    with pytest.raises(ValidationError):
        BattingStatsResponse(
            id=1, player_id=1, match_id=1,
            runs=-3, fours=0, sixes=0, innings_number=1,
        )


def test_bowling_stats_response_innings_number_must_be_positive():
    with pytest.raises(ValidationError):
        BowlingStatsResponse(
            id=1, player_id=1, match_id=1,
            overs=4, maidens=0, runs_conceded=22, wickets=2,
            innings_number=0,
        )
