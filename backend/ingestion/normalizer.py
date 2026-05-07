"""Convert raw CricAPI JSON dicts into validated Pydantic models.

The raw CricAPI surface is messy:

  * Match types arrive lowercase ("t20i") and sometimes mid-cased ("Test").
  * Player names arrive with combining diacritics, leading/trailing spaces,
    or double-encoded UTF-8.
  * Country names show up as ICC codes ("Pak"), full names ("Pakistan"),
    or with a "Women"/"Men" suffix appended.
  * Optional stats (balls faced, extras, dismissal) drop in and out
    depending on how old the source record is.
  * Some derived fields (strike rate, economy) are sometimes present and
    sometimes have to be computed.

The normalizer's job is to absorb all that and emit
`Normalized*` models that the loader can insert without further
validation. Anything we can't make sense of becomes None on optional
fields; for required fields, Pydantic raises ValidationError so the
seed script can log + skip the offending row.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping, TypeVar

from app.models.enums import MatchType, PlayerRole, TossDecision

from .exceptions import SkipRecord
from .schemas import (
    NormalizedBattingStats,
    NormalizedBowlingStats,
    NormalizedMatch,
    NormalizedMatchResult,
    NormalizedPlayer,
)

# Pattern used to filter women's cricket out at the normalizer layer.
# Project scope is men's cricket only — keeping it out at this layer
# (rather than the seed script) means the rule holds regardless of
# caller, including any future ad-hoc ingestion paths.
_WOMEN_PATTERN = re.compile(r"\bwomen\b", re.IGNORECASE)


def _looks_like_womens(value: Any) -> bool:
    """True if `value` mentions a women's team/squad in any casing."""
    if value is None:
        return False
    return bool(_WOMEN_PATTERN.search(str(value)))

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Enum)


# --------------------------------------------------------------- enums

def _coerce_enum(value: Any, enum_cls: type[E]) -> E | None:
    """Case-insensitive, whitespace-tolerant enum lookup.

    Returns None on unknown values rather than raising — this matters
    because most enum-typed fields are nullable in the schemas, so a
    weird historical record shouldn't break the whole ingestion run.
    For required enum fields (e.g. NormalizedMatch.match_type) the
    Pydantic layer will raise downstream, which the seed script handles.
    """
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value

    needle = str(value).strip().casefold()
    if not needle:
        return None

    for member in enum_cls:
        if member.value.casefold() == needle or member.name.casefold() == needle:
            return member

    logger.warning("unknown %s value %r — coerced to None", enum_cls.__name__, value)
    return None


# --------------------------------------------------------------- text

# Matches the team-code suffix CricAPI appends to team display names,
# e.g. "Pakistan Women [PAKW]", "Mumbai Indians [MI]", "Pakistan A
# [PAK-A]". Accepts letters, digits, and hyphens, length 2-8 — keeps
# the pattern strict enough not to swallow legitimate bracketed text
# elsewhere in the name.
_BRACKET_SUFFIX = re.compile(r"\s*\[[A-Z0-9\-]{2,8}\]\s*$")
_GENDER_SUFFIX = re.compile(r"\s+(?:Women|Men)\s*$", re.IGNORECASE)


def _clean_str(value: Any) -> str | None:
    """Trim whitespace, NFKC-normalize, collapse internal runs of spaces.

    NFKC folds compatibility characters and recomposes diacritics so
    "Riȥwan" and "Riẓwan" survive intact while "Babar  Azam" (two
    spaces) becomes "Babar Azam".
    """
    if value is None:
        return None
    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


# --------------------------------------------------------------- countries

# Lowercased keys → canonical English names. Coverage is intentionally
# Pakistan-cricket-centric since that's the project's focus; expand as
# needed when we ingest more series.
_COUNTRY_ALIASES: dict[str, str] = {
    "pak": "Pakistan",
    "pakistan": "Pakistan",
    # Pakistan A (development tour squad) and Pakistan Shaheens (B-team)
    # collapse into the senior side. They share most personnel and
    # tracking them separately would just fragment analytics for the
    # comparison pages without adding insight.
    "pakistan a": "Pakistan",
    "pakistan shaheens": "Pakistan",
    "pakistan b": "Pakistan",
    "ind": "India",
    "india": "India",
    "aus": "Australia",
    "australia": "Australia",
    "eng": "England",
    "england": "England",
    "rsa": "South Africa",
    "sa": "South Africa",
    "south africa": "South Africa",
    "nz": "New Zealand",
    "new zealand": "New Zealand",
    "ban": "Bangladesh",
    "bangladesh": "Bangladesh",
    "sl": "Sri Lanka",
    "sri lanka": "Sri Lanka",
    "wi": "West Indies",
    "west indies": "West Indies",
    "afg": "Afghanistan",
    "afghanistan": "Afghanistan",
    "zim": "Zimbabwe",
    "zimbabwe": "Zimbabwe",
    "ire": "Ireland",
    "ireland": "Ireland",
    "nep": "Nepal",
    "nepal": "Nepal",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "usa": "United States of America",
    "us": "United States of America",
    "united states of america": "United States of America",
    "scotland": "Scotland",
    "sco": "Scotland",
}


def _normalize_country(value: Any) -> str | None:
    """Map CricAPI's country/team display strings to canonical names.

    Strips bracket codes ("[PAKW]") and gender suffixes ("Women") so
    "Pakistan Women [PAKW]" → "Pakistan". Returns None if we don't
    recognise the result, which is the right choice for franchise
    teams (Mumbai Indians, etc.) — those have no country.
    """
    cleaned = _clean_str(value)
    if cleaned is None:
        return None

    cleaned = _BRACKET_SUFFIX.sub("", cleaned).strip()
    cleaned = _GENDER_SUFFIX.sub("", cleaned).strip()

    canonical = _COUNTRY_ALIASES.get(cleaned.casefold())
    if canonical is not None:
        return canonical
    return None


def _normalize_team_name(value: Any) -> str | None:
    """Like `_normalize_country` but keeps the franchise name when no
    country mapping exists (e.g. "Mumbai Indians").
    """
    cleaned = _clean_str(value)
    if cleaned is None:
        return None

    cleaned = _BRACKET_SUFFIX.sub("", cleaned).strip()

    country = _COUNTRY_ALIASES.get(_GENDER_SUFFIX.sub("", cleaned).casefold().strip())
    if country is not None:
        # Preserve "Pakistan Women" as a distinct team rather than
        # collapsing it to "Pakistan" — match-level analytics needs to
        # tell women's and men's matches apart.
        if _GENDER_SUFFIX.search(cleaned):
            return cleaned
        return country
    return cleaned or None


# --------------------------------------------------------------- dates

def _parse_datetime(value: Any) -> datetime | None:
    """Accept ISO datetime strings, ISO date strings, or epoch ints.

    CricAPI typically returns `dateTimeGMT` as an ISO string without a
    timezone marker (the field name implies UTC). We attach UTC
    explicitly so all stored timestamps are tz-aware — DB column is
    `DateTime(timezone=True)`.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    text = str(value).strip()
    # Try a few common shapes.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Last resort: fromisoformat handles fractional seconds + offsets.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("unparseable datetime %r — coerced to None", value)
        return None


def _parse_date(value: Any) -> date | None:
    dt = _parse_datetime(value)
    return dt.date() if dt is not None else None


# --------------------------------------------------------------- numbers

def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strike_rate(runs: int | None, balls: int | None) -> float | None:
    """Strike rate is undefined for 0-ball innings; return None there."""
    if runs is None or balls is None or balls <= 0:
        return None
    return round((runs / balls) * 100, 2)


def _economy_rate(runs: int | None, overs: float | None) -> float | None:
    if runs is None or overs is None or overs <= 0:
        return None
    return round(runs / overs, 2)


# --------------------------------------------------------------- player

def normalize_player(raw: Mapping[str, Any]) -> NormalizedPlayer:
    """Convert a raw CricAPI player dict to a `NormalizedPlayer`.

    Handles both /players/search response items and /playerStats
    profile blobs — the schemas overlap heavily but use slightly
    different field names (`country` vs `nationality`, etc.).
    """
    name = _clean_str(raw.get("name") or raw.get("fullName"))
    if not name:
        raise ValueError("player record has no usable name")

    # Women's cricket is out of scope. CricAPI exposes the gender of a
    # player through `country` / `nationality` / `currentTeam` (e.g.
    # "Pakistan Women"). If any of those signals women's, skip.
    for source_field in ("country", "nationality", "currentTeam", "team"):
        if _looks_like_womens(raw.get(source_field)):
            raise SkipRecord(
                f"women's player filtered (source field {source_field!r}={raw[source_field]!r})"
            )
    if _looks_like_womens(name):
        # Belt-and-braces: some records put "Women" in the player's
        # display name itself (e.g. "Bismah Maroof (Women)").
        raise SkipRecord(f"women's player filtered (name={name!r})")

    return NormalizedPlayer(
        external_id=_clean_str(raw.get("id")) or _clean_str(raw.get("playerId")),
        name=name,
        country=_normalize_country(
            raw.get("country") or raw.get("nationality") or raw.get("currentTeam")
        ),
        batting_style=_clean_str(raw.get("battingStyle") or raw.get("batting")),
        bowling_style=_clean_str(raw.get("bowlingStyle") or raw.get("bowling")),
        role=_coerce_enum(raw.get("role") or raw.get("playingRole"), PlayerRole),
        date_of_birth=_parse_date(raw.get("dateOfBirth") or raw.get("dob")),
    )


# --------------------------------------------------------------- match

def _split_teams(raw: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Locate the two team names in a CricAPI match record.

    `/match` returns them under either `teams` (a 2-element list) or
    `t1`/`t2` (display strings). The two formats coexist across
    different endpoint variants — try both.
    """
    teams = raw.get("teams")
    if isinstance(teams, list) and len(teams) >= 2:
        return _normalize_team_name(teams[0]), _normalize_team_name(teams[1])
    return _normalize_team_name(raw.get("t1")), _normalize_team_name(raw.get("t2"))


def normalize_match(raw: Mapping[str, Any]) -> NormalizedMatch:
    """Convert a raw match dict to a `NormalizedMatch`.

    Required fields: external_id, match_type, date, team1, team2.
    If any of these can't be derived, Pydantic raises and the caller
    should skip the record.
    """
    team1, team2 = _split_teams(raw)

    # Women's cricket is out of scope (see SkipRecord docstring). The
    # check runs against the *normalized* team names so it catches both
    # "Pakistan Women [PAKW]" and "Pakistan women" alike.
    if _looks_like_womens(team1) or _looks_like_womens(team2):
        raise SkipRecord(
            f"women's match filtered (teams={team1!r} vs {team2!r})"
        )

    return NormalizedMatch(
        external_id=str(raw["id"]) if raw.get("id") is not None else None,
        match_type=_coerce_enum(raw.get("matchType") or raw.get("match_type"), MatchType),
        venue=_clean_str(raw.get("venue")),
        ground=_clean_str(raw.get("ground") or raw.get("stadium")),
        date=_parse_datetime(raw.get("dateTimeGMT") or raw.get("date")),
        team1=team1,
        team2=team2,
        winner=_normalize_team_name(raw.get("matchWinner") or raw.get("winner")),
        toss_winner=_normalize_team_name(raw.get("tossWinner")),
        toss_decision=_coerce_enum(
            raw.get("tossChoice") or raw.get("tossDecision"), TossDecision
        ),
        result_margin=_clean_str(raw.get("status") or raw.get("result")),
    )


# --------------------------------------------------------------- stats

def _player_ref(raw: Mapping[str, Any], *keys: str) -> tuple[str | None, str | None]:
    """Extract (external_id, player_name) from the various shapes
    CricAPI uses to embed a player reference in scorecard rows.

    Examples seen:
      {"batsman": {"id": "...", "name": "..."}, "r": 32, ...}
      {"player": "Babar Azam", "playerId": "uuid", ...}
      {"name": "Babar Azam", ...}  # very old records, no id
    """
    for key in keys:
        node = raw.get(key)
        if isinstance(node, Mapping):
            return _clean_str(node.get("id")), _clean_str(node.get("name"))
        if isinstance(node, str):
            return None, _clean_str(node)
    return _clean_str(raw.get("playerId") or raw.get("id")), _clean_str(raw.get("name"))


def normalize_batting_card(
    raw: Mapping[str, Any], innings_number: int
) -> NormalizedBattingStats | None:
    """One scorecard batting row → NormalizedBattingStats.

    Returns None for rows that don't represent an actual batter
    (header rows, "did not bat" stubs without a name).
    """
    external_id, player_name = _player_ref(raw, "batsman", "player")
    if not player_name:
        return None

    runs = _safe_int(raw.get("r") or raw.get("runs")) or 0
    balls = _safe_int(raw.get("b") or raw.get("balls") or raw.get("ballsFaced"))

    # Source strike rate wins when present so historical rounding is
    # preserved; fall back to computing.
    sr = _safe_float(raw.get("sr") or raw.get("strikeRate"))
    if sr is None:
        sr = _strike_rate(runs, balls)

    return NormalizedBattingStats(
        player_external_id=external_id,
        player_name=player_name,
        runs=runs,
        balls_faced=balls,
        fours=_safe_int(raw.get("4s") or raw.get("fours")) or 0,
        sixes=_safe_int(raw.get("6s") or raw.get("sixes")) or 0,
        strike_rate=sr,
        dismissal_type=_clean_str(
            raw.get("dismissal-text") or raw.get("dismissal") or raw.get("dismissalType")
        ),
        innings_number=innings_number,
        position=_safe_int(raw.get("position") or raw.get("battingOrder")),
    )


def normalize_bowling_card(
    raw: Mapping[str, Any], innings_number: int
) -> NormalizedBowlingStats | None:
    external_id, player_name = _player_ref(raw, "bowler", "player")
    if not player_name:
        return None

    overs = _safe_float(raw.get("o") or raw.get("overs")) or 0.0
    runs_conceded = _safe_int(raw.get("r") or raw.get("runs") or raw.get("runsConceded")) or 0

    economy = _safe_float(raw.get("eco") or raw.get("economyRate") or raw.get("economy"))
    if economy is None:
        economy = _economy_rate(runs_conceded, overs)

    return NormalizedBowlingStats(
        player_external_id=external_id,
        player_name=player_name,
        overs=overs,
        maidens=_safe_int(raw.get("m") or raw.get("maidens")) or 0,
        runs_conceded=runs_conceded,
        wickets=_safe_int(raw.get("w") or raw.get("wickets")) or 0,
        economy_rate=economy,
        extras=_safe_int(raw.get("extras")),
        innings_number=innings_number,
    )


# --------------------------------------------------------- match w/ scorecard

def normalize_match_with_scorecard(
    raw: Mapping[str, Any],
) -> NormalizedMatchResult:
    """Full /match response → match row + every batting/bowling card.

    `scorecard` is a list of innings; each innings has `batting` and
    `bowling` arrays. We index innings by appearance order rather than
    relying on a per-innings number field, because that field is not
    consistently present in CricAPI responses. The header strings
    ("Pakistan Innings 1", "India 2nd Inning") differ between matches.
    """
    match = normalize_match(raw)

    batting: list[NormalizedBattingStats] = []
    bowling: list[NormalizedBowlingStats] = []

    scorecard = raw.get("scorecard") or raw.get("innings") or []
    for innings_index, innings in enumerate(scorecard, start=1):
        if not isinstance(innings, Mapping):
            continue
        for row in innings.get("batting") or []:
            if isinstance(row, Mapping):
                normalized = normalize_batting_card(row, innings_index)
                if normalized is not None:
                    batting.append(normalized)
        for row in innings.get("bowling") or []:
            if isinstance(row, Mapping):
                normalized = normalize_bowling_card(row, innings_index)
                if normalized is not None:
                    bowling.append(normalized)

    return NormalizedMatchResult(match=match, batting=batting, bowling=bowling)
