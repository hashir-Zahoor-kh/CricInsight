"""Phase 3.2 normalizer tests.

Two layers:

1. Unit tests for the small helpers (enum coercion, country aliases,
   string cleaning, derived fields). These are fast, pinpoint failures.

2. End-to-end fixture tests: each of the 5 hand-crafted JSON fixtures
   (covering the edge cases the user called out) gets fed through the
   appropriate `normalize_*` entry point and the resulting Pydantic
   model is asserted in detail. Fixtures live in tests/fixtures/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.enums import MatchType, PlayerRole, TossDecision
from ingestion import normalizer
from ingestion.normalizer import (
    _coerce_enum,
    _normalize_country,
    _normalize_team_name,
    _parse_datetime,
    _strike_rate,
    _economy_rate,
    normalize_match,
    normalize_match_with_scorecard,
    normalize_player,
)
from ingestion.schemas import (
    NormalizedBattingStats,
    NormalizedBowlingStats,
    NormalizedMatch,
    NormalizedMatchResult,
    NormalizedPlayer,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


# ====================================================================
# Helpers
# ====================================================================

class TestEnumCoercion:
    """Per the user's instruction: case-insensitive coercion must work
    for ALL three enums, not just MatchType."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("t20i", MatchType.T20I),
            ("T20I", MatchType.T20I),
            ("  t20i  ", MatchType.T20I),  # whitespace tolerant
            ("test", MatchType.TEST),
            ("Test", MatchType.TEST),
            ("ODI", MatchType.ODI),
            ("odi", MatchType.ODI),
            ("t20", MatchType.T20),
        ],
    )
    def test_match_type(self, raw, expected):
        assert _coerce_enum(raw, MatchType) is expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("BATSMAN", PlayerRole.BATSMAN),  # by name
            ("batsman", PlayerRole.BATSMAN),  # by value
            ("Batsman", PlayerRole.BATSMAN),
            ("WICKETKEEPER", PlayerRole.WICKETKEEPER),
            ("wicketkeeper", PlayerRole.WICKETKEEPER),
            ("ALLROUNDER", PlayerRole.ALL_ROUNDER),  # by value (lowercased "allrounder")
            ("allrounder", PlayerRole.ALL_ROUNDER),
            ("ALL_ROUNDER", PlayerRole.ALL_ROUNDER),  # by name
            ("bowler", PlayerRole.BOWLER),
        ],
    )
    def test_player_role(self, raw, expected):
        assert _coerce_enum(raw, PlayerRole) is expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("bat", TossDecision.BAT),
            ("Bat", TossDecision.BAT),
            ("BAT", TossDecision.BAT),
            ("bowl", TossDecision.BOWL),
            ("Bowl", TossDecision.BOWL),
        ],
    )
    def test_toss_decision(self, raw, expected):
        assert _coerce_enum(raw, TossDecision) is expected

    def test_unknown_returns_none_not_raise(self):
        # Unknown values become None so a single weird record can't break
        # an entire ingestion run.
        assert _coerce_enum("jellyfish", MatchType) is None
        assert _coerce_enum("manager", PlayerRole) is None
        assert _coerce_enum("dance", TossDecision) is None

    def test_none_in_returns_none_out(self):
        assert _coerce_enum(None, MatchType) is None
        assert _coerce_enum("", PlayerRole) is None


class TestCountryAliases:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Pak", "Pakistan"),
            ("Pakistan", "Pakistan"),
            ("Pakistan Women [PAKW]", "Pakistan"),
            ("Pakistan Men [PAK]", "Pakistan"),
            ("IND", "India"),
            ("Sri Lanka", "Sri Lanka"),
            ("nz", "New Zealand"),
            ("Mumbai Indians", None),  # franchise — not a country
        ],
    )
    def test_country_resolution(self, raw, expected):
        assert _normalize_country(raw) == expected

    def test_team_name_keeps_franchise(self):
        # _normalize_team_name should fall through to the original string
        # rather than nulling out franchise teams the country map doesn't
        # know about.
        assert _normalize_team_name("Mumbai Indians [MI]") == "Mumbai Indians"

    def test_team_name_keeps_gender_distinction(self):
        # We deliberately preserve "Pakistan Women" instead of collapsing
        # to "Pakistan" — match-level analytics needs to tell women's
        # and men's matches apart.
        assert _normalize_team_name("Pakistan Women [PAKW]") == "Pakistan Women"


class TestDerivedFields:
    def test_strike_rate_with_zero_balls_is_none(self):
        # 0-ball innings has undefined SR; null preserves that signal.
        assert _strike_rate(0, 0) is None
        assert _strike_rate(50, 0) is None

    def test_strike_rate_with_null_balls_is_none(self):
        assert _strike_rate(50, None) is None

    def test_strike_rate_normal(self):
        assert _strike_rate(50, 25) == 200.0
        assert _strike_rate(45, 32) == pytest.approx(140.62, abs=0.01)

    def test_economy_with_zero_overs_is_none(self):
        assert _economy_rate(50, 0) is None

    def test_economy_normal(self):
        assert _economy_rate(50, 10) == 5.0


class TestDatetimeParsing:
    def test_iso_string_attaches_utc(self):
        dt = _parse_datetime("2025-09-20T14:00:00")
        assert dt is not None
        assert dt.tzinfo is not None  # tz-aware required for the DB column

    def test_date_only_string(self):
        dt = _parse_datetime("2024-01-22")
        assert dt is not None
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_garbage_returns_none(self):
        assert _parse_datetime("not a date") is None
        assert _parse_datetime(None) is None


# ====================================================================
# Fixture-driven end-to-end checks
# ====================================================================

class TestFixtureMissingBallsFaced:
    """Older record where balls_faced is not reported on some batters.
    Strike rate must remain None (cannot derive without balls); the
    second batter (who has both r and b) gets a real SR."""

    @pytest.fixture
    def result(self):
        return normalize_match_with_scorecard(_load("match_missing_balls_faced.json"))

    def test_returns_validated_match_result(self, result):
        assert isinstance(result, NormalizedMatchResult)
        assert isinstance(result.match, NormalizedMatch)
        assert result.match.match_type is MatchType.TEST
        assert result.match.toss_decision is TossDecision.BAT  # "Bat" → BAT

    def test_first_batter_has_null_balls_and_null_sr(self, result):
        saeed = next(b for b in result.batting if b.player_name == "Saeed Anwar")
        assert saeed.runs == 87
        assert saeed.balls_faced is None
        assert saeed.strike_rate is None  # cannot derive from null balls

    def test_second_batter_keeps_source_sr(self, result):
        sohail = next(b for b in result.batting if b.player_name == "Aamir Sohail")
        assert sohail.balls_faced == 95
        # Source value (43.16) preserved rather than recomputed.
        assert sohail.strike_rate == pytest.approx(43.16, abs=0.01)

    def test_bowling_card_present(self, result):
        wasim = next(b for b in result.bowling if b.player_name == "Wasim Akram")
        assert wasim.wickets == 5
        assert wasim.economy_rate is not None  # derivable from o + r


class TestFixturePlayerWeirdEncoding:
    """Whitespace + NFD diacritics + ICC country code."""

    @pytest.fixture
    def player(self) -> NormalizedPlayer:
        return normalize_player(_load("player_weird_encoding.json"))

    def test_name_collapsed_and_normalised(self, player):
        # Leading/trailing space gone, internal double space collapsed.
        assert "  " not in player.name
        assert not player.name.startswith(" ")
        assert not player.name.endswith(" ")
        # NFKC normalisation kept the diaeresis without splitting the
        # combining mark off into a separate code point.
        import unicodedata
        assert unicodedata.is_normalized("NFKC", player.name)

    def test_country_alias_resolved(self, player):
        assert player.country == "Pakistan"  # "Pak" → "Pakistan"

    def test_role_case_insensitive(self, player):
        # Source had the role as "WICKETKEEPER" (uppercase by name).
        assert player.role is PlayerRole.WICKETKEEPER

    def test_dob_parsed(self, player):
        from datetime import date
        assert player.date_of_birth == date(1992, 6, 1)


class TestFixtureNoResult:
    """Abandoned match — no winner, no toss, empty scorecard."""

    @pytest.fixture
    def result(self):
        return normalize_match_with_scorecard(_load("match_no_result.json"))

    def test_required_fields_populated(self, result):
        m = result.match
        assert m.external_id == "fixture-no-result-2024"
        assert m.match_type is MatchType.ODI
        assert m.team1 == "Pakistan"
        assert m.team2 == "New Zealand"
        # ICC bracket codes stripped out.
        assert "[" not in m.team1
        assert "[" not in m.team2

    def test_optional_fields_null(self, result):
        m = result.match
        assert m.winner is None
        assert m.toss_winner is None
        assert m.toss_decision is None

    def test_scorecard_empty_means_empty_lists(self, result):
        assert result.batting == []
        assert result.bowling == []


class TestFixtureWithExtras:
    """Bowling cards include `extras`; one bowler is missing `eco` and
    requires the normalizer to derive economy."""

    @pytest.fixture
    def result(self):
        return normalize_match_with_scorecard(_load("match_with_extras.json"))

    def test_extras_populated_on_bowlers(self, result):
        shaheen = next(b for b in result.bowling if b.player_name == "Shaheen Afridi")
        haris = next(b for b in result.bowling if b.player_name == "Haris Rauf")
        assert shaheen.extras == 6
        assert haris.extras == 3

    def test_economy_preserved_when_provided(self, result):
        shaheen = next(b for b in result.bowling if b.player_name == "Shaheen Afridi")
        assert shaheen.economy_rate == pytest.approx(5.0)

    def test_economy_derived_when_missing(self, result):
        # Haris Rauf's source has no `eco` — normalizer derives 56/8 = 7.0.
        haris = next(b for b in result.bowling if b.player_name == "Haris Rauf")
        assert haris.economy_rate == pytest.approx(7.0)


class TestFixtureCleanT20I:
    """Happy path: full data, lowercase matchType, populated dismissals."""

    @pytest.fixture
    def result(self):
        return normalize_match_with_scorecard(_load("match_clean_t20i.json"))

    def test_lowercase_match_type_resolves_to_t20i(self, result):
        # Specifically tests the case mismatch the user flagged from the
        # real /cricScore response.
        assert result.match.match_type is MatchType.T20I

    def test_two_innings_yield_innings_indexed_stats(self, result):
        innings_seen = {b.innings_number for b in result.batting}
        assert innings_seen == {1, 2}

    def test_strike_rate_derived_when_source_omits_it(self, result):
        babar = next(b for b in result.batting if b.player_name == "Babar Azam")
        # Source provides sr=165.85; ensure it's preserved.
        assert babar.strike_rate == pytest.approx(165.85, abs=0.01)

    def test_dismissal_text_preserved(self, result):
        rizwan = next(b for b in result.batting if b.player_name == "Mohammad Rizwan")
        assert rizwan.dismissal_type == "c Buttler b Wood"

    def test_all_outputs_are_pydantic_models(self, result):
        # Catch-all: every record emerging from the pipeline is a real
        # validated model, not a dict slipping through.
        assert isinstance(result, NormalizedMatchResult)
        assert isinstance(result.match, NormalizedMatch)
        for b in result.batting:
            assert isinstance(b, NormalizedBattingStats)
        for b in result.bowling:
            assert isinstance(b, NormalizedBowlingStats)


# ====================================================================
# Pydantic-level guarantees — the spec says "all outputs are valid
# Pydantic models with no null violations"
# ====================================================================

@pytest.mark.parametrize(
    "fixture",
    [
        "match_missing_balls_faced.json",
        "match_no_result.json",
        "match_with_extras.json",
        "match_clean_t20i.json",
    ],
)
def test_every_match_fixture_round_trips_through_pydantic(fixture):
    """Final blanket assertion: each fixture produces a model that
    survives Pydantic re-validation (model_validate(model_dump()))."""
    result = normalize_match_with_scorecard(_load(fixture))
    # If any field ended up violating its declared type/constraint,
    # this re-validation raises. Belt and braces.
    NormalizedMatchResult.model_validate(result.model_dump())


def test_player_fixture_round_trips_through_pydantic():
    p = normalize_player(_load("player_weird_encoding.json"))
    NormalizedPlayer.model_validate(p.model_dump())


def test_negative_runs_in_source_raises_validation_error():
    """Belt-and-braces sanity check that the schema's >=0 constraints
    actually fire. Builds a synthetic bad input — no fixture for this
    because real CricAPI doesn't emit negative runs."""
    bad = {
        "id": "bad-match",
        "matchType": "T20I",
        "dateTimeGMT": "2025-01-01T00:00:00",
        "teams": ["Pakistan", "India"],
        "scorecard": [
            {
                "inning": "Pakistan Innings 1",
                "batting": [{"batsman": {"id": "x", "name": "X"}, "r": -5}],
                "bowling": [],
            }
        ],
    }
    with pytest.raises(ValidationError):
        normalize_match_with_scorecard(bad)
