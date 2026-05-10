"""Cricsheet → NormalizedMatchResult parser.

Cricsheet (https://cricsheet.org) ships ball-by-ball JSON archives
for every men's international match (and many domestic). It's free,
unlimited, and the de-facto standard for cricket analytics — exactly
the right pivot from CricAPI's paid /match endpoint.

This module:

  * Downloads + caches the per-format archives (T20I / ODI / Test) on
    first use. The user re-running ingestion never re-downloads.

  * Parses each match JSON's ball-by-ball innings into per-player
    batting and bowling rollups, emitting Pydantic `NormalizedMatch`,
    `NormalizedBattingStats`, and `NormalizedBowlingStats` records
    that feed straight into the existing `loader.py` (no bypass).

  * Filters out women's matches (info.gender != 'male') and any
    match that doesn't include at least one player from our seeded
    roster — otherwise the DB would balloon with thousands of
    matches we'll never look at.

Cricsheet's name format quirks (handled here):
  * `info.players.<team>` and `info.registry.people` use abbreviated
    initial-style names ("BA Stokes", "V Kohli"). The seed list is
    full names ("Ben Stokes", "Virat Kohli"). Match by surname +
    first-initial fallback so both formats line up.
  * Toss decision is "bat" or "field"; we map field→bowl to match
    our TossDecision enum.
  * `match_type` arrives as "T20", "ODI", "Test", "T20I" — already
    matches our MatchType enum values directly.
"""

from __future__ import annotations

import json
import logging
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.models.enums import MatchType, PlayerRole, TossDecision

from .exceptions import SkipRecord
from .schemas import (
    NormalizedBattingStats,
    NormalizedBowlingStats,
    NormalizedMatch,
    NormalizedMatchResult,
    NormalizedPlayer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- config

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "cricsheet_data"

# Cricsheet's per-format men's-only archives. Filenames are stable;
# Cricsheet has shipped them under these URLs for years.
ARCHIVE_URLS: dict[MatchType, str] = {
    MatchType.T20I: "https://cricsheet.org/downloads/t20s_male_json.zip",
    MatchType.ODI: "https://cricsheet.org/downloads/odis_male_json.zip",
    MatchType.TEST: "https://cricsheet.org/downloads/tests_male_json.zip",
}


@dataclass
class FilterConfig:
    """Seeded-player filter — load only matches involving at least one
    of these names (full or abbreviated form). Exposed as a dataclass
    so the seed CLI can override per-run for testing."""

    seed_full_names: list[str]

    @property
    def surname_initials(self) -> set[tuple[str, str]]:
        """Set of (surname, first-initial) tuples derived from the seed
        list — used to match Cricsheet's "BA Stokes" abbreviated names
        against our full-name seed list."""
        out: set[tuple[str, str]] = set()
        for full in self.seed_full_names:
            parts = full.split()
            if len(parts) >= 2:
                out.add((parts[-1], parts[0][0]))
        return out

    @property
    def surname_set(self) -> set[str]:
        """Surname-only set, intentionally NOT used by the filter
        anymore — kept for callers that explicitly want loose matching.
        The filter relies on the surname+initial pair instead because
        surname-only matched any 'Smith'/'Khan'/'Singh' player and
        flooded the seed with irrelevant matches."""
        return {n.split()[-1] for n in self.seed_full_names if n.split()}


# ---------------------------------------------------------------- download

def ensure_archive(
    fmt: MatchType,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    force: bool = False,
) -> Path:
    """Download + extract the per-format archive if not already present.

    Returns the directory containing the extracted JSON files. Each
    Cricsheet archive expands to one .json per match.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    fmt_dir = data_dir / fmt.value.lower()
    archive_path = data_dir / f"{fmt.value.lower()}_male_json.zip"

    if fmt_dir.exists() and any(fmt_dir.glob("*.json")) and not force:
        logger.info(
            "%s archive already extracted at %s (%d files)",
            fmt.value, fmt_dir, len(list(fmt_dir.glob("*.json"))),
        )
        return fmt_dir

    url = ARCHIVE_URLS[fmt]
    logger.info("downloading %s archive from %s", fmt.value, url)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        archive_path.write_bytes(response.content)

    logger.info("extracting to %s", fmt_dir)
    fmt_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(fmt_dir)

    return fmt_dir


# ---------------------------------------------------------------- parse

def _coerce_match_type(raw: Any) -> MatchType | None:
    if not isinstance(raw, str):
        return None
    cf = raw.strip().casefold()
    for member in MatchType:
        if member.value.casefold() == cf:
            return member
    return None


def _coerce_toss_decision(raw: Any) -> TossDecision | None:
    if not isinstance(raw, str):
        return None
    cf = raw.strip().casefold()
    # Cricsheet says "field"; our enum says "bowl".
    if cf == "field":
        return TossDecision.BOWL
    for member in TossDecision:
        if member.value.casefold() == cf:
            return member
    return None


def _format_outcome(outcome: dict) -> str | None:
    """Build a "won by 7 wickets"-style margin string from the JSON."""
    if not outcome:
        return None
    winner = outcome.get("winner")
    if winner is None:
        if outcome.get("result") == "no result":
            return "no result"
        if outcome.get("result") == "tie":
            return "tied"
        if outcome.get("result") == "draw":
            return "drawn"
        return None
    by = outcome.get("by") or {}
    if "runs" in by:
        return f"{winner} won by {by['runs']} runs"
    if "wickets" in by:
        return f"{winner} won by {by['wickets']} wickets"
    if "innings" in by:
        runs = by.get("runs", 0)
        return f"{winner} won by an innings and {runs} runs"
    return f"{winner} won"


def _parse_dates(dates: list[str] | None) -> datetime:
    """Cricsheet's `dates` is a list of ISO date strings (longer matches
    span multiple days). Use the first one and attach UTC."""
    if not dates:
        raise ValueError("match has no date")
    parsed = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return parsed


def _aggregate_innings(
    innings_list: list[dict],
    registry: dict[str, str],
) -> tuple[list[NormalizedBattingStats], list[NormalizedBowlingStats]]:
    """Walk every ball in every innings and accumulate per-player
    batting and bowling rollups.

    Returns (batting_rows, bowling_rows). Each row is a Pydantic
    `NormalizedBattingStats` / `NormalizedBowlingStats` ready for
    the loader.
    """
    batting_out: list[NormalizedBattingStats] = []
    bowling_out: list[NormalizedBowlingStats] = []

    for innings_idx, innings in enumerate(innings_list, start=1):
        # Per-player batting accumulator: name → dict of running totals
        bat_agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "runs": 0,
                "balls": 0,  # legal deliveries faced
                "fours": 0,
                "sixes": 0,
                "out": False,
                "dismissal": None,
                "position": None,
            }
        )
        bowl_agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "balls": 0,  # legal deliveries bowled
                "runs": 0,  # runs conceded (incl wides/nb but excl byes/lb)
                "wickets": 0,
                "maidens": 0,
                "extras_credited": 0,
            }
        )

        # Track batting order by first appearance in the innings.
        seen_batters: list[str] = []

        for over in innings.get("overs", []) or []:
            over_runs = 0  # for maiden detection
            for delivery in over.get("deliveries", []) or []:
                batter = delivery.get("batter")
                bowler = delivery.get("bowler")
                runs = delivery.get("runs") or {}
                extras = delivery.get("extras") or {}

                if batter and batter not in seen_batters:
                    seen_batters.append(batter)

                # Determine if this delivery counts as a "legal ball"
                # for batting and bowling balls-faced/bowled tallies.
                # Wides and no-balls don't count toward batter's balls
                # faced; only no-balls don't count toward bowler's
                # legal-deliveries tally either, but wides DO count
                # against the bowler's runs without counting toward
                # batter's balls.
                is_wide = "wides" in extras
                is_no_ball = "noballs" in extras
                is_legal_for_batter = not (is_wide or is_no_ball)
                is_legal_for_bowler = not (is_wide or is_no_ball)

                # Batter line
                if batter:
                    batter_runs = int(runs.get("batter", 0) or 0)
                    bat_agg[batter]["runs"] += batter_runs
                    if is_legal_for_batter:
                        bat_agg[batter]["balls"] += 1
                    if batter_runs == 4:
                        bat_agg[batter]["fours"] += 1
                    elif batter_runs == 6:
                        bat_agg[batter]["sixes"] += 1

                # Bowler line
                if bowler:
                    # Runs conceded = total minus byes / leg-byes
                    # (those aren't credited against the bowler).
                    total_run = int(runs.get("total", 0) or 0)
                    byes = int(extras.get("byes", 0) or 0)
                    legbyes = int(extras.get("legbyes", 0) or 0)
                    conceded = total_run - byes - legbyes
                    bowl_agg[bowler]["runs"] += conceded
                    over_runs += conceded
                    if is_legal_for_bowler:
                        bowl_agg[bowler]["balls"] += 1
                    # Track wides + no-balls credited as extras to the
                    # bowler — useful as a stat for the dashboard.
                    if is_wide:
                        bowl_agg[bowler]["extras_credited"] += int(
                            extras.get("wides", 0) or 0
                        )
                    if is_no_ball:
                        bowl_agg[bowler]["extras_credited"] += int(
                            extras.get("noballs", 0) or 0
                        )

                # Wickets — a delivery may have multiple wickets (rare:
                # run-outs on a no-ball edge etc.).
                for wicket in delivery.get("wickets", []) or []:
                    out_kind = wicket.get("kind", "")
                    player_out = wicket.get("player_out")
                    # Only credit the bowler if the dismissal type is
                    # bowler-credited (caught, bowled, lbw, stumped,
                    # caught and bowled, hit wicket). Run-outs aren't.
                    bowler_credited = out_kind in {
                        "caught", "bowled", "lbw", "stumped",
                        "caught and bowled", "hit wicket",
                    }
                    if bowler_credited and bowler:
                        bowl_agg[bowler]["wickets"] += 1
                    if player_out:
                        bat_agg[player_out]["out"] = True
                        bat_agg[player_out]["dismissal"] = out_kind

            if over_runs == 0 and any(
                "balls" in bowl_agg[b] and bowl_agg[b]["balls"] > 0
                for b in bowl_agg
            ):
                # Maiden detection per bowler in this over: simpler to
                # do at over close. Identify the bowler of this over by
                # which bowler had a delivery — usually one bowler per
                # over (skip detection if mixed, rare).
                bowler_of_over = (
                    over.get("deliveries", [{}])[0].get("bowler")
                    if over.get("deliveries")
                    else None
                )
                if bowler_of_over:
                    # Only call it a maiden if the bowler bowled all 6
                    # legal balls of this over (i.e. no wides/no-balls).
                    delivs = over.get("deliveries") or []
                    legal_count = sum(
                        1
                        for d in delivs
                        if d.get("bowler") == bowler_of_over
                        and "wides" not in (d.get("extras") or {})
                        and "noballs" not in (d.get("extras") or {})
                    )
                    if legal_count == 6:
                        bowl_agg[bowler_of_over]["maidens"] += 1

        # Convert accumulators to NormalizedBattingStats rows
        for batter, agg in bat_agg.items():
            position = (
                seen_batters.index(batter) + 1 if batter in seen_batters else None
            )
            balls = agg["balls"] or None
            sr = (
                round((agg["runs"] / balls) * 100, 2) if balls else None
            )
            batting_out.append(
                NormalizedBattingStats(
                    player_external_id=registry.get(batter),
                    player_name=batter,
                    runs=agg["runs"],
                    balls_faced=balls,
                    fours=agg["fours"],
                    sixes=agg["sixes"],
                    strike_rate=sr,
                    dismissal_type=agg["dismissal"] if agg["out"] else None,
                    innings_number=innings_idx,
                    position=position,
                )
            )

        # ... and bowling
        for bowler, agg in bowl_agg.items():
            balls = agg["balls"]
            # Cricket overs are "X.Y" where Y is balls in current over.
            # E.g. 4 overs + 3 balls = 4.3 (not 4.5). For analytics we
            # store the raw float that the existing schema expects.
            overs_int, balls_in = divmod(balls, 6)
            overs_decimal = float(overs_int) + balls_in / 10.0
            economy = (
                round((agg["runs"] / overs_int), 2)
                if overs_int > 0
                else None
            ) if balls_in == 0 else (
                round((agg["runs"] / (overs_int + balls_in / 6)), 2)
                if balls > 0
                else None
            )
            bowling_out.append(
                NormalizedBowlingStats(
                    player_external_id=registry.get(bowler),
                    player_name=bowler,
                    overs=overs_decimal,
                    maidens=agg["maidens"],
                    runs_conceded=agg["runs"],
                    wickets=agg["wickets"],
                    economy_rate=economy,
                    extras=agg["extras_credited"],
                    innings_number=innings_idx,
                )
            )

    return batting_out, bowling_out


def parse_match(
    data: dict,
    *,
    source_id: str,
    forced_match_type: MatchType | None = None,
) -> NormalizedMatchResult:
    """One Cricsheet match JSON → NormalizedMatchResult.

    `source_id` is the filename stem (Cricsheet's match number) used
    as `external_id` since Cricsheet doesn't expose a per-match UUID
    in the JSON itself.

    `forced_match_type`: Cricsheet's per-archive JSONs use the same
    `match_type: "T20"` value for both internationals and franchise
    matches — the international flag is implicit in the archive
    name (t20s_male, odis_male, tests_male). Callers iterating from
    a known-format archive directory pass forced_match_type to
    override the JSON value. Without it, all T20I matches would
    land in the franchise T20 bucket.

    Raises SkipRecord for women's matches (info.gender != 'male'),
    matching the project's exclusion-of-scope policy.
    """
    info = data.get("info") or {}

    if info.get("gender", "").lower() != "male":
        raise SkipRecord(f"women's/youth match (gender={info.get('gender')})")

    teams = info.get("teams") or []
    if len(teams) < 2:
        raise ValueError(f"match {source_id}: fewer than 2 teams")

    if forced_match_type is not None:
        match_type = forced_match_type
    else:
        match_type = _coerce_match_type(info.get("match_type"))
        if match_type is None:
            raise ValueError(
                f"match {source_id}: unknown match_type {info.get('match_type')!r}"
            )

    outcome = info.get("outcome") or {}
    toss = info.get("toss") or {}

    match = NormalizedMatch(
        external_id=f"cs:{source_id}",  # cs: prefix to avoid colliding
                                        # with eventual CricAPI ids
        match_type=match_type,
        venue=info.get("city"),
        ground=info.get("venue"),
        date=_parse_dates(info.get("dates")),
        team1=teams[0],
        team2=teams[1],
        winner=outcome.get("winner"),
        toss_winner=toss.get("winner"),
        toss_decision=_coerce_toss_decision(toss.get("decision")),
        result_margin=_format_outcome(outcome),
    )

    registry = (info.get("registry") or {}).get("people") or {}

    batting, bowling = _aggregate_innings(
        data.get("innings") or [], registry
    )

    return NormalizedMatchResult(match=match, batting=batting, bowling=bowling)


# ---------------------------------------------------------------- filter

def match_involves_seeded_player(
    info: dict,
    cfg: FilterConfig,
) -> bool:
    """True if any player in `info.players` matches a seeded name.

    Two-stage match:
      1. exact full-name match against the seed list
      2. surname + first-initial pair — covers Cricsheet's
         "BA Stokes" / "B Azam" / "JE Root" abbreviated form

    Surname-only fallback was DELIBERATELY removed: it matched any
    "Smith", "Khan", "Singh" — flooding the seed with hundreds of
    matches that had no seeded player in them.
    """
    players_per_team = info.get("players") or {}
    seed_set = set(cfg.seed_full_names)
    surname_initial = cfg.surname_initials

    for team_players in players_per_team.values():
        for cs_name in team_players or []:
            if cs_name in seed_set:
                return True
            parts = cs_name.split()
            if len(parts) >= 2:
                first_token = parts[0]
                surname = parts[-1]
                if (surname, first_token[0]) in surname_initial:
                    return True
    return False


# ---------------------------------------------------------------- iterator

def _team_membership_map(info: dict) -> dict[str, str]:
    """Build a player → country map from `info.players.<team>` and
    `info.registry.people`. Both Cricsheet name forms (full and
    abbreviated) get keys so the loader can look up by either.
    """
    name_to_team: dict[str, str] = {}
    for team, players in (info.get("players") or {}).items():
        for p in players or []:
            name_to_team[p] = team

    # Add external_id (cricsheet UUID) → team mapping too so the
    # downstream roster builder can resolve countries by ext_id when
    # the name spelling drifts.
    registry = (info.get("registry") or {}).get("people") or {}
    out = dict(name_to_team)
    for name, ext_id in registry.items():
        if name in name_to_team:
            out[ext_id] = name_to_team[name]
    return out


def iter_filtered_matches(
    fmt: MatchType,
    cfg: FilterConfig,
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    limit: int | None = None,
) -> Iterator[tuple[str, NormalizedMatchResult, dict[str, str]]]:
    """Yields (source_id, normalized_result, player_country_map) for
    every cricsheet match of the given format that involves a seeded
    player.

    `player_country_map` is the per-match name/ext_id → team-name
    dict — passed through so the roster builder can backfill the
    `players.country` column without a second JSON pass.

    `limit` caps total emissions per format — useful when targeting
    "30 ODIs" without iterating thousands of files.
    """
    fmt_dir = ensure_archive(fmt, data_dir=data_dir)

    files = sorted(fmt_dir.glob("*.json"), reverse=True)  # newest-first
    yielded = 0
    skipped_unfiltered = 0
    skipped_womens_or_unparseable = 0

    for path in files:
        if path.name == "README.txt" or not path.name.endswith(".json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        info = data.get("info") or {}

        # Cheap pre-filter — drop women's matches and matches without
        # any seeded player BEFORE doing the heavier ball-by-ball parse.
        if info.get("gender", "").lower() != "male":
            skipped_womens_or_unparseable += 1
            continue
        if not match_involves_seeded_player(info, cfg):
            skipped_unfiltered += 1
            continue

        try:
            # Pass `forced_match_type=fmt` so the archive directory is
            # the source of truth for international vs franchise — the
            # per-match JSON value is ambiguous between T20I and
            # franchise T20 (both arrive as "T20").
            result = parse_match(data, source_id=path.stem, forced_match_type=fmt)
        except (SkipRecord, ValueError):
            skipped_womens_or_unparseable += 1
            continue

        country_map = _team_membership_map(info)
        yield (path.stem, result, country_map)
        yielded += 1
        if limit is not None and yielded >= limit:
            break

    logger.info(
        "%s: yielded %d matches (filtered out %d non-seeded, %d unparseable/skip)",
        fmt.value, yielded, skipped_unfiltered, skipped_womens_or_unparseable,
    )


# ---------------------------------------------------------------- player roster

def player_roster_from_results(
    results: Iterable[NormalizedMatchResult],
    *,
    seed_full_names: list[str],
    country_map: dict[str, str] | None = None,
) -> list[NormalizedPlayer]:
    """Build a NormalizedPlayer list for the rich-profile load_players()
    path, drawing from the players seen across all loaded matches.

    `country_map` is the merged per-match {ext_id_or_name → country}
    dict yielded by iter_filtered_matches. Used to backfill the
    `country` column so the comparison page's common-opponents panel
    has something to anchor.

    The 22 seeded names get full-profile rows; everyone else is left
    as a stub the per-match loader will create via DO-NOTHING upsert.
    """
    cfg = FilterConfig(seed_full_names=seed_full_names)
    seed_set = set(cfg.seed_full_names)
    surname_initial_to_full = {
        (n.split()[-1], n.split()[0][0]): n
        for n in seed_full_names
        if len(n.split()) >= 2
    }
    country_map = country_map or {}

    seen: dict[str, NormalizedPlayer] = {}
    for r in results:
        for card in [*r.batting, *r.bowling]:
            cs_name = card.player_name
            ext_id = card.player_external_id
            full_name = cs_name
            # Resolve country by ext_id first (most reliable across
            # spelling drift), then by cricsheet name as fallback.
            country = (
                country_map.get(ext_id) if ext_id else None
            ) or country_map.get(cs_name)
            # Try to resolve to a full seeded name where possible so
            # the dashboard's player picker shows the friendly form.
            if cs_name in seed_set:
                full_name = cs_name
            else:
                parts = cs_name.split()
                if len(parts) >= 2:
                    key = (parts[-1], parts[0][0])
                    full_name = surname_initial_to_full.get(key, cs_name)

            dedup_key = ext_id or full_name
            if dedup_key in seen:
                # If a later match has a country we didn't have
                # before, fill it in. (Some Cricsheet entries omit
                # registry entries; the match's player list still
                # has the team membership.)
                if country is not None and seen[dedup_key].country is None:
                    seen[dedup_key].country = country
                continue
            seen[dedup_key] = NormalizedPlayer(
                external_id=ext_id,
                name=full_name,
                country=country,
            )
    return list(seen.values())
