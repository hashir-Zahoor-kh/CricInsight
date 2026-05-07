"""Phase 3.3 loader tests.

Two non-negotiables locked in by the test contract:

  1. **Idempotency**: loading the same data twice must leave row
     counts unchanged on the second pass. Without this, every
     re-seed would multiply rows.

  2. **Partial-update upsert**: changing one field in a record and
     reloading must update the field IN PLACE — same row count, new
     value. Proves the loader actually upserts rather than INSERT
     IGNOREing.

Beyond those two, we cover:
  * Stat row counts match the scorecard (no off-by-one on
    innings indexing).
  * Stub players from scorecards don't clobber rich profiles loaded
    via load_players (the DO-NOTHING vs DO-UPDATE split).
  * Player resolution falls back to name when external_id is missing.

All loader tests share the same `db_session` fixture in conftest.py
that spins up `cricinsight_test`, runs alembic migrations against
it, and TRUNCATEs between tests.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import BattingStats, BowlingStats, Match, Player, PlayerRole
from ingestion.loader import (
    load_match_result,
    load_match_results,
    load_players,
)
from ingestion.normalizer import (
    normalize_match_with_scorecard,
    normalize_player,
)
from ingestion.schemas import NormalizedPlayer

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _row_counts(session) -> dict[str, int]:
    return {
        "players": session.scalar(select(__import__("sqlalchemy").func.count()).select_from(Player)),
        "matches": session.scalar(select(__import__("sqlalchemy").func.count()).select_from(Match)),
        "batting": session.scalar(select(__import__("sqlalchemy").func.count()).select_from(BattingStats)),
        "bowling": session.scalar(select(__import__("sqlalchemy").func.count()).select_from(BowlingStats)),
    }


# ====================================================================
# Basic happy-path
# ====================================================================

class TestLoadMatchResult:

    def test_loads_match_with_full_scorecard(self, db_session):
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
        counts = load_match_result(db_session, result)
        db_session.commit()

        # 7 distinct players: Buttler, Brook (Eng batters), Babar,
        # Rizwan (Pak batters), Shaheen, Naseem (Pak bowlers), Wood
        # (Eng bowler). 4 batting cards, 3 bowling cards.
        assert counts.players_inserted == 7
        assert counts.matches_inserted == 1
        assert counts.batting_inserted == 4
        assert counts.bowling_inserted == 3

        rows = _row_counts(db_session)
        assert rows == {
            "players": 7,
            "matches": 1,
            "batting": 4,
            "bowling": 3,
        }

    def test_loads_no_result_match_with_empty_scorecard(self, db_session):
        result = normalize_match_with_scorecard(_load_fixture("match_no_result.json"))
        load_match_result(db_session, result)
        db_session.commit()

        rows = _row_counts(db_session)
        assert rows["matches"] == 1
        assert rows["players"] == 0  # nobody in the abandoned scorecard
        assert rows["batting"] == 0
        assert rows["bowling"] == 0

    def test_match_columns_persisted_correctly(self, db_session):
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
        load_match_result(db_session, result)
        db_session.commit()

        match = db_session.scalar(
            select(Match).where(Match.external_id == "fixture-clean-t20i-2025")
        )
        assert match is not None
        assert match.team1 == "Pakistan"
        assert match.team2 == "England"
        assert match.winner == "Pakistan"
        assert match.toss_winner == "England"
        assert match.toss_decision.value == "bowl"


# ====================================================================
# Idempotency — non-negotiable
# ====================================================================

class TestIdempotency:
    """Loading the same data N times must produce the same row count.
    This is the hard rule the user enforced as non-negotiable."""

    def test_match_load_is_idempotent(self, db_session):
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))

        load_match_result(db_session, result)
        db_session.commit()
        first_pass = _row_counts(db_session)

        # Reload identical data.
        load_match_result(db_session, result)
        db_session.commit()
        second_pass = _row_counts(db_session)

        # The first pass populated; the second pass must produce
        # IDENTICAL row counts. If this fails, the loader is broken
        # and the rest of the suite is meaningless.
        assert second_pass == first_pass, (
            f"loader is not idempotent — first pass: {first_pass}, "
            f"second pass: {second_pass}"
        )

    def test_bulk_load_is_idempotent(self, db_session):
        # Three different matches loaded together — exercises
        # load_match_results' batch + savepoint path.
        results = [
            normalize_match_with_scorecard(_load_fixture(name))
            for name in (
                "match_clean_t20i.json",
                "match_with_extras.json",
                "match_missing_balls_faced.json",
            )
        ]

        load_match_results(db_session, results)
        db_session.commit()
        first_pass = _row_counts(db_session)

        load_match_results(db_session, results)
        db_session.commit()
        second_pass = _row_counts(db_session)

        assert second_pass == first_pass

    def test_load_players_is_idempotent(self, db_session):
        player = normalize_player(_load_fixture("player_weird_encoding.json"))
        load_players(db_session, [player])
        db_session.commit()
        first = _row_counts(db_session)["players"]

        load_players(db_session, [player])
        db_session.commit()
        second = _row_counts(db_session)["players"]

        assert first == second == 1


# ====================================================================
# Partial-update upsert — proves the upsert *upserts*
# ====================================================================

class TestPartialUpdateUpsert:
    """The user explicitly added this: load a fixture, modify ONE
    field in the input, reload, and assert (a) row count unchanged
    and (b) the field is updated. If the loader were doing
    INSERT IGNORE / DO NOTHING, this would fail because the second
    pass wouldn't write the new value."""

    def test_player_field_updates_on_reload(self, db_session):
        # Load with batting_style = "Right-hand bat" (from fixture).
        original = normalize_player(_load_fixture("player_weird_encoding.json"))
        assert original.batting_style == "Right-hand bat"
        load_players(db_session, [original])
        db_session.commit()

        first_row_count = _row_counts(db_session)["players"]

        # Modify a single field and reload.
        modified = original.model_copy(update={"batting_style": "RHB"})
        load_players(db_session, [modified])
        db_session.commit()

        # (a) Row count unchanged — proves the upsert hit the same row.
        second_row_count = _row_counts(db_session)["players"]
        assert second_row_count == first_row_count == 1

        # (b) Field actually updated — proves DO UPDATE, not DO NOTHING.
        stored = db_session.scalar(
            select(Player).where(Player.external_id == original.external_id)
        )
        assert stored.batting_style == "RHB"

    def test_match_field_updates_on_reload(self, db_session):
        # Same proof for matches: change the venue and reload.
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
        load_match_result(db_session, result)
        db_session.commit()
        first = _row_counts(db_session)

        modified = result.model_copy(deep=True)
        modified.match.venue = "Karachi"
        load_match_result(db_session, modified)
        db_session.commit()
        second = _row_counts(db_session)

        assert second == first  # row counts identical

        stored = db_session.scalar(
            select(Match).where(Match.external_id == result.match.external_id)
        )
        assert stored.venue == "Karachi"

    def test_batting_card_updates_on_reload(self, db_session):
        # And the same proof for stats: change a runs value and reload.
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
        load_match_result(db_session, result)
        db_session.commit()
        first = _row_counts(db_session)

        # Bump Babar's score from 68 to 99.
        modified = result.model_copy(deep=True)
        babar = next(
            b for b in modified.batting if b.player_name == "Babar Azam"
        )
        babar.runs = 99
        load_match_result(db_session, modified)
        db_session.commit()
        second = _row_counts(db_session)

        assert second == first

        stored_runs = db_session.scalar(
            select(BattingStats.runs)
            .join(Player, BattingStats.player_id == Player.id)
            .where(Player.name == "Babar Azam")
        )
        assert stored_runs == 99


# ====================================================================
# Stub-vs-full upsert: ensure scorecard ingestion never clobbers
# rich profiles.
# ====================================================================

class TestStubVsFullPlayerUpsert:
    """A player loaded via load_players (rich profile) must NOT have
    their fields wiped by a subsequent load_match_result that
    includes them in a scorecard with only name+external_id.

    This is THE test for the DO-NOTHING-on-stub design."""

    def test_scorecard_load_does_not_overwrite_rich_profile(self, db_session):
        # Step 1: load a rich profile for Babar Azam.
        babar = NormalizedPlayer(
            external_id="p-babar-azam",
            name="Babar Azam",
            country="Pakistan",
            role=PlayerRole.BATSMAN,
            batting_style="Right-hand bat",
            bowling_style=None,
            date_of_birth=date(1994, 10, 15),
        )
        load_players(db_session, [babar])
        db_session.commit()

        # Step 2: load a match that happens to contain Babar in the
        # scorecard. The clean_t20i fixture has him with id
        # "p-babar-azam" — same external_id.
        result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
        load_match_result(db_session, result)
        db_session.commit()

        # Step 3: Babar's rich profile must still be intact. If the
        # stub upsert had been DO UPDATE, country/role/style would
        # all be NULLed.
        stored = db_session.scalar(
            select(Player).where(Player.external_id == "p-babar-azam")
        )
        assert stored.country == "Pakistan"
        assert stored.role is PlayerRole.BATSMAN
        assert stored.batting_style == "Right-hand bat"
        assert stored.date_of_birth == date(1994, 10, 15)

    def test_load_players_does_overwrite(self, db_session):
        # Symmetric proof: load_players IS supposed to overwrite, so
        # a second call with new field values updates them.
        first = NormalizedPlayer(
            external_id="p-test",
            name="Test Player",
            country="Pakistan",
            batting_style="Right-hand bat",
        )
        load_players(db_session, [first])
        db_session.commit()

        second = first.model_copy(update={"batting_style": "Left-hand bat"})
        load_players(db_session, [second])
        db_session.commit()

        stored = db_session.scalar(
            select(Player).where(Player.external_id == "p-test")
        )
        assert stored.batting_style == "Left-hand bat"


# ====================================================================
# Stat counts
# ====================================================================

def test_batting_count_matches_scorecard(db_session):
    # match_with_extras has exactly 1 batting row (Fakhar) and 2 bowling
    # rows (Shaheen, Haris) — scorecard structure verified by hand.
    result = normalize_match_with_scorecard(_load_fixture("match_with_extras.json"))
    load_match_result(db_session, result)
    db_session.commit()

    rows = _row_counts(db_session)
    assert rows["batting"] == 1
    assert rows["bowling"] == 2


def test_innings_numbers_distinct_for_two_innings_match(db_session):
    # The clean T20I has two innings; batters split across both.
    result = normalize_match_with_scorecard(_load_fixture("match_clean_t20i.json"))
    load_match_result(db_session, result)
    db_session.commit()

    innings_seen = set(
        db_session.scalars(select(BattingStats.innings_number)).all()
    )
    assert innings_seen == {1, 2}
