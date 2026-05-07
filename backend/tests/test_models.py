"""Phase 2.2 model tests.

These tests do NOT touch a database. They verify three things:

1. Every model imports without error (catches typos, missing columns).
2. SQLAlchemy can fully configure all mappers — this is what catches
   broken `relationship()` definitions, missing FK targets, or unresolved
   string-form class references.
3. The expected columns and relationships exist on each class.

`configure_mappers()` is the key call — it forces SQLAlchemy to resolve
every `back_populates` and FK string lazily-deferred during class
construction. Without it, a typo in `back_populates="batting_statz"`
would only surface at first runtime query, not at import time.
"""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

from app.models import (
    Base,
    BattingStats,
    BowlingStats,
    Match,
    MatchType,
    Player,
    PlayerRole,
    TossDecision,
)


def test_all_models_import() -> None:
    # Just reaching this point already proves imports worked, but assert
    # the symbols are non-None to catch accidental `= None` typos.
    assert Player is not None
    assert Match is not None
    assert BattingStats is not None
    assert BowlingStats is not None
    assert MatchType.TEST.value == "Test"
    assert PlayerRole.BATSMAN.value == "batsman"
    assert TossDecision.BAT.value == "bat"


def test_metadata_registers_all_tables() -> None:
    expected_tables = {"players", "matches", "batting_stats", "bowling_stats"}
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_mappers_resolve_without_db() -> None:
    """If any relationship string is wrong, this raises before any query."""
    configure_mappers()


def test_player_relationships() -> None:
    rels = {r.key for r in Player.__mapper__.relationships}
    assert {"batting_stats", "bowling_stats"} <= rels

    bs_rel = Player.__mapper__.relationships["batting_stats"]
    assert bs_rel.mapper.class_ is BattingStats
    # The cascade=all+delete-orphan we set on Player should be active.
    assert bs_rel.cascade.delete_orphan is True


def test_match_relationships() -> None:
    rels = {r.key for r in Match.__mapper__.relationships}
    assert {"batting_stats", "bowling_stats"} <= rels


def test_batting_stats_relationships_and_keys() -> None:
    rels = {r.key for r in BattingStats.__mapper__.relationships}
    assert {"player", "match"} <= rels

    cols = {c.name for c in BattingStats.__table__.columns}
    expected = {
        "id", "player_id", "match_id", "runs", "balls_faced",
        "fours", "sixes", "strike_rate", "dismissal_type",
        "innings_number", "position",
    }
    assert expected <= cols

    # The unique constraint enforces one batting card per player per
    # innings — also the upsert key for the loader.
    uq_names = {uc.name for uc in BattingStats.__table__.constraints
                if uc.__class__.__name__ == "UniqueConstraint"}
    assert "uq_batting_stats_match_player_innings" in uq_names


def test_bowling_stats_relationships_and_keys() -> None:
    rels = {r.key for r in BowlingStats.__mapper__.relationships}
    assert {"player", "match"} <= rels

    cols = {c.name for c in BowlingStats.__table__.columns}
    expected = {
        "id", "player_id", "match_id", "overs", "maidens",
        "runs_conceded", "wickets", "economy_rate", "extras",
        "innings_number",
    }
    assert expected <= cols


def test_player_columns() -> None:
    cols = {c.name for c in Player.__table__.columns}
    expected = {
        "id", "external_id", "name", "country", "batting_style",
        "bowling_style", "role", "date_of_birth",
        "created_at", "updated_at",
    }
    assert expected <= cols


def test_match_columns() -> None:
    cols = {c.name for c in Match.__table__.columns}
    expected = {
        "id", "external_id", "match_type", "venue", "ground", "date",
        "team1", "team2", "winner", "toss_winner", "toss_decision",
        "result_margin", "created_at", "updated_at",
    }
    assert expected <= cols
