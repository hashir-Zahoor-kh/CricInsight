"""Seed CricInsight's database with the comparison player roster + a
historical match sample.

Quota-aware design — CricAPI free tier is 100 calls/day:

  * Worst-case call count is calculated up front (player_search +
    player_stats + match_detail) and logged before any network IO.

  * Default mode aborts cleanly if `worst_case > quota_remaining`.
    The user gets a clear message and runs again either after the
    UTC midnight reset or with --partial.

  * --partial keeps going until the quota actually exhausts, then
    stops gracefully. Re-running picks up where it left off because
    every CricAPI response is cached on disk and the DB loader is
    idempotent (Phase 3.3) — no special "resume state" file is
    needed. Cache + DB == resume.

  * Women's records are filtered at the normalizer layer
    (SkipRecord); the seed catches them and increments a counter.

Run:
    python -m ingestion.seed              # strict abort if over quota
    python -m ingestion.seed --partial    # do as much as quota allows
    python -m ingestion.seed --plan       # print the plan, no calls
    python -m ingestion.seed --force-refresh  # bypass cache, refetch
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.enums import MatchType
from ingestion.client import (
    ENDPOINT_MATCH,
    ENDPOINT_PLAYER_STATS,
    ENDPOINT_PLAYERS,
    CricAPIClient,
)
from ingestion.exceptions import APIError, RateLimitError, SkipRecord
from ingestion.loader import (
    LoadCounts,
    load_match_results,
    load_players,
)
from ingestion.normalizer import (
    normalize_match_with_scorecard,
    normalize_player,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- config

# Names are passed verbatim to /players?search= so they need to match
# CricAPI's display strings well enough to land the right player at top
# of results. The seed picks the first non-women's hit by default.
PLAYER_SEED_LIST: list[str] = [
    # Pakistan core
    "Babar Azam",
    "Mohammad Rizwan",
    "Fakhar Zaman",
    "Shaheen Afridi",
    "Naseem Shah",
    "Haris Rauf",
    "Shadab Khan",
    # India
    "Virat Kohli",
    "Rohit Sharma",
    "Jasprit Bumrah",
    # England
    "Joe Root",
    "Ben Stokes",
    "Jofra Archer",
    # Australia
    "Steve Smith",
    "Pat Cummins",
    "Mitchell Starc",
    # New Zealand
    "Kane Williamson",
    "Trent Boult",
    # South Africa
    "Kagiso Rabada",
    "Quinton de Kock",
    # Sri Lanka
    "Wanindu Hasaranga",
    # Bangladesh
    "Shakib Al Hasan",
]

# Format-mix targets for the historical match sample.
TARGET_MIX: dict[MatchType, int] = {
    MatchType.T20I: 30,
    MatchType.ODI: 30,
    MatchType.TEST: 25,
    MatchType.T20: 15,  # franchise T20s (IPL/PSL/BBL/etc.)
}
TOTAL_MATCH_TARGET = sum(TARGET_MIX.values())


# --------------------------------------------------------------- result

@dataclass
class SeedReport:
    """End-of-run summary."""

    worst_case_calls: int = 0
    quota_remaining_at_start: int = 0
    quota_remaining_at_end: int = 0
    players_resolved: int = 0
    players_skipped_women: int = 0
    matches_picked: int = 0
    matches_loaded: int = 0
    matches_skipped_women: int = 0
    rate_limit_hit: bool = False
    aborted_pre_flight: bool = False
    db_counts: LoadCounts = field(default_factory=LoadCounts)

    def log(self) -> None:
        logger.info("=" * 60)
        logger.info("seed report")
        logger.info("  worst-case calls projected:    %d", self.worst_case_calls)
        logger.info("  quota at start:                %d", self.quota_remaining_at_start)
        logger.info("  quota at end:                  %d", self.quota_remaining_at_end)
        logger.info("  players resolved:              %d", self.players_resolved)
        logger.info("  players skipped (women's):     %d", self.players_skipped_women)
        logger.info("  matches picked:                %d", self.matches_picked)
        logger.info("  matches loaded:                %d", self.matches_loaded)
        logger.info("  matches skipped (women's):     %d", self.matches_skipped_women)
        logger.info("  rate-limit hit mid-run:        %s", self.rate_limit_hit)
        logger.info("  aborted at pre-flight:         %s", self.aborted_pre_flight)
        logger.info("  DB: %s", self.db_counts.summary())
        logger.info("=" * 60)


# ------------------------------------------------------- plan & pre-flight

def _projected_uncached_calls(
    client: CricAPIClient,
    players: list[str],
    target_matches: int,
) -> int:
    """Upper bound on uncached network calls.

    For player searches and stats, we can check the cache directly
    because the (endpoint, params) tuple is fully known up front. For
    match details, the IDs come from /playerStats responses we
    haven't fetched yet — so we just assume worst case (target_matches
    uncached) and let RateLimitError stop us if reality is worse.
    """
    uncached = 0
    for name in players:
        if client.cache.get("GET", ENDPOINT_PLAYERS, {"search": name}) is None:
            uncached += 1
    # Player stats lookups are keyed by external_id which we don't yet
    # know, so assume worst case = one /playerStats per player.
    uncached += len(players)
    # And one /match per target match (best estimate; some may already
    # be cached after a partial run).
    uncached += target_matches
    return uncached


# ----------------------------------------------------------- player phase

def _pick_player_from_search(
    raw: dict[str, Any], target_name: str
) -> dict[str, Any] | None:
    """Pick the best non-women's match from a /players response."""
    data = raw.get("data") or []
    if not isinstance(data, list):
        return None
    target_cf = target_name.casefold()
    # Prefer exact name match; otherwise first non-women's row.
    for row in data:
        if not isinstance(row, dict):
            continue
        # Skip women's records up front so women's-only hits don't
        # consume the "first match" slot when a men's row exists later.
        country = (row.get("country") or "").lower()
        if "women" in country:
            continue
        if (row.get("name") or "").casefold() == target_cf:
            return row
    for row in data:
        if isinstance(row, dict) and "women" not in (row.get("country") or "").lower():
            return row
    return None


def resolve_players(
    client: CricAPIClient,
    names: list[str],
    *,
    force_refresh: bool = False,
) -> tuple[list[Any], list[str], int]:
    """Run the search phase. Returns (normalized_players, ext_ids, women_skipped).

    Stops if a RateLimitError fires; partial results are fine because
    the cache is populated with whatever we managed to fetch and the
    next run picks up the remainder.
    """
    normalized: list[Any] = []
    external_ids: list[str] = []
    women_skipped = 0

    for name in names:
        try:
            raw = client.players(name, force_refresh=force_refresh)
        except RateLimitError:
            raise
        except APIError as exc:
            logger.warning("player search for %r failed: %s — skipping", name, exc)
            continue

        picked = _pick_player_from_search(raw, name)
        if picked is None:
            logger.warning("no usable result for %r in search response", name)
            continue

        try:
            normalized_player = normalize_player(picked)
        except SkipRecord as exc:
            women_skipped += 1
            logger.info("skipped %r: %s", name, exc.reason)
            continue
        except (ValueError, Exception) as exc:  # noqa: BLE001 — last-resort guard
            logger.warning("could not normalize %r: %s", name, exc)
            continue

        if normalized_player.external_id is None:
            logger.warning(
                "search response for %r had no usable id", name
            )
            continue

        normalized.append(normalized_player)
        external_ids.append(normalized_player.external_id)

    return normalized, external_ids, women_skipped


# ----------------------------------------------------------- stats phase

def _match_refs_from_stats(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-match references from a /playerStats response.

    CricAPI's player stats payload exposes match-level rows under
    `data.matchList` (current shape) — we accept a few alternates so
    schema drift doesn't take the seed offline.
    """
    data = raw.get("data") or {}
    for key in ("matchList", "matches", "recentMatches"):
        rows = data.get(key) if isinstance(data, dict) else None
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def collect_match_pool(
    client: CricAPIClient,
    player_external_ids: list[str],
    *,
    force_refresh: bool = False,
) -> tuple[list[tuple[str, MatchType | None]], int]:
    """For each player, fetch stats and accumulate (match_id, match_type)
    candidates. Deduplicates by match_id. Returns (pool, calls_used)."""
    seen: dict[str, MatchType | None] = {}
    calls_started = client.quota.used()

    for ext_id in player_external_ids:
        try:
            raw = client.player_stats(ext_id, force_refresh=force_refresh)
        except RateLimitError:
            raise
        except APIError as exc:
            logger.warning("playerStats for %s failed: %s — skipping", ext_id, exc)
            continue

        for ref in _match_refs_from_stats(raw):
            match_id = ref.get("matchId") or ref.get("id")
            if not match_id:
                continue
            # Best-effort match-type guess from the stats summary so we
            # can sort by format quota without a /match call. Falls
            # back to None which gets resolved later.
            mt_raw = ref.get("matchType") or ref.get("format")
            mt = None
            if isinstance(mt_raw, str):
                mt_cf = mt_raw.strip().casefold()
                for member in MatchType:
                    if member.value.casefold() == mt_cf:
                        mt = member
                        break
            seen[str(match_id)] = mt

    calls_used = client.quota.used() - calls_started
    pool = list(seen.items())
    logger.info(
        "collected %d unique match candidates across %d players (%d calls)",
        len(pool), len(player_external_ids), calls_used,
    )
    return pool, calls_used


# ----------------------------------------------------------- match phase

def pick_matches(
    pool: list[tuple[str, MatchType | None]],
    target: dict[MatchType, int],
) -> list[str]:
    """Pick up to `target[fmt]` matches per format from the pool.

    Unknown-format candidates spill into a leftover bucket used to top
    up T20 (franchise) since that's the most flexible bucket.
    """
    by_format: dict[MatchType, list[str]] = {fmt: [] for fmt in target}
    unknown: list[str] = []
    for match_id, mt in pool:
        if mt in by_format:
            by_format[mt].append(match_id)
        else:
            unknown.append(match_id)

    picked: list[str] = []
    for fmt, want in target.items():
        chosen = by_format[fmt][:want]
        picked.extend(chosen)
        if len(chosen) < want:
            shortfall = want - len(chosen)
            logger.info(
                "format %s short by %d (have %d / want %d) — using unknowns",
                fmt.value, shortfall, len(chosen), want,
            )
            picked.extend(unknown[:shortfall])
            unknown = unknown[shortfall:]
    return picked


def fetch_matches(
    client: CricAPIClient,
    match_ids: list[str],
    *,
    force_refresh: bool = False,
) -> tuple[list[Any], int, int]:
    """Returns (normalized_results, women_skipped, errors)."""
    results: list[Any] = []
    women_skipped = 0
    errors = 0
    for match_id in match_ids:
        try:
            raw = client.match(match_id, force_refresh=force_refresh)
        except RateLimitError:
            raise
        except APIError as exc:
            logger.warning("match %s fetch failed: %s — skipping", match_id, exc)
            errors += 1
            continue

        match_payload = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(match_payload, dict):
            logger.warning("unexpected /match shape for %s — skipping", match_id)
            errors += 1
            continue

        try:
            normalized = normalize_match_with_scorecard(match_payload)
        except SkipRecord as exc:
            women_skipped += 1
            logger.info("skipped match %s: %s", match_id, exc.reason)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not normalize match %s: %s", match_id, exc)
            errors += 1
            continue

        results.append(normalized)
    return results, women_skipped, errors


# ----------------------------------------------------------- main

def run_seed(
    *,
    partial: bool = False,
    plan_only: bool = False,
    force_refresh: bool = False,
    api_key: str | None = None,
    target_matches: int = TOTAL_MATCH_TARGET,
    target_mix: dict[MatchType, int] | None = None,
    db_session_factory=None,
) -> SeedReport:
    """Run the seed end-to-end.

    Pure-function-ish: takes a session factory so tests can inject a
    rolling-rollback session, but defaults to constructing one against
    DATABASE_URL_SYNC if not provided.
    """
    target_mix = target_mix or TARGET_MIX
    api_key = api_key or os.getenv("CRICAPI_KEY", "")
    if not api_key:
        raise RuntimeError(
            "CRICAPI_KEY not set. Put it in backend/.env before running."
        )

    report = SeedReport()

    with CricAPIClient(api_key=api_key) as client:
        # ----- pre-flight -----
        report.quota_remaining_at_start = client.quota.remaining()
        report.worst_case_calls = _projected_uncached_calls(
            client, PLAYER_SEED_LIST, target_matches
        )

        logger.info(
            "pre-flight: worst-case %d uncached calls vs %d quota remaining",
            report.worst_case_calls, report.quota_remaining_at_start,
        )

        if plan_only:
            report.quota_remaining_at_end = client.quota.remaining()
            report.log()
            return report

        if (
            report.worst_case_calls > report.quota_remaining_at_start
            and not partial
        ):
            logger.error(
                "Aborting: would need up to %d calls but only %d remain "
                "today. Re-run after UTC midnight, or pass --partial to "
                "do as much as possible now.",
                report.worst_case_calls, report.quota_remaining_at_start,
            )
            report.aborted_pre_flight = True
            return report

        # ----- player phase -----
        try:
            players, ext_ids, women_skipped = resolve_players(
                client, PLAYER_SEED_LIST, force_refresh=force_refresh
            )
        except RateLimitError:
            logger.warning("rate limit hit during player resolve — stopping")
            report.rate_limit_hit = True
            return _finalise(client, report, db_session_factory, [])

        report.players_resolved = len(players)
        report.players_skipped_women = women_skipped

        # ----- stats phase -----
        try:
            pool, _ = collect_match_pool(
                client, ext_ids, force_refresh=force_refresh
            )
        except RateLimitError:
            logger.warning("rate limit hit during stats phase — stopping")
            report.rate_limit_hit = True
            return _finalise(client, report, db_session_factory, [], players)

        # ----- match phase -----
        picked = pick_matches(pool, target_mix)
        report.matches_picked = len(picked)

        try:
            results, m_women_skipped, _ = fetch_matches(
                client, picked, force_refresh=force_refresh
            )
        except RateLimitError:
            logger.warning("rate limit hit during match phase — stopping")
            report.rate_limit_hit = True
            results = []  # we still load anything that was cached/decoded
            m_women_skipped = 0

        report.matches_loaded = len(results)
        report.matches_skipped_women = m_women_skipped

        return _finalise(client, report, db_session_factory, results, players)


def _finalise(
    client: CricAPIClient,
    report: SeedReport,
    db_session_factory,
    results: list[Any],
    players: list[Any] | None = None,
) -> SeedReport:
    """Push whatever we collected to the DB and finalise the report."""
    if db_session_factory is not None:
        with db_session_factory() as session:
            if players:
                load_counts = load_players(session, players)
                report.db_counts = report.db_counts + load_counts
            if results:
                load_counts = load_match_results(session, results)
                report.db_counts = report.db_counts + load_counts
            session.commit()

    report.quota_remaining_at_end = client.quota.remaining()
    report.log()
    return report


# ----------------------------------------------------------- CLI

def _default_session_factory():
    """Build a sessionmaker against DATABASE_URL_SYNC for the CLI path."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://cricinsight:cricinsight@localhost:5432/cricinsight",
    )
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingestion.seed",
        description="Seed the CricInsight DB with players + historical matches.",
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Run until the daily quota exhausts; resume on a later run.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the call plan and exit without making any network calls.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass the response cache and refetch every endpoint.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load .env so CRICAPI_KEY / DATABASE_URL_SYNC are available.
    try:
        from dotenv import load_dotenv

        backend_root = Path(__file__).resolve().parents[1]
        for candidate in (backend_root / ".env", backend_root.parent / ".env"):
            if candidate.exists():
                load_dotenv(candidate)
                break
    except ModuleNotFoundError:
        pass

    report = run_seed(
        partial=args.partial,
        plan_only=args.plan,
        force_refresh=args.force_refresh,
        db_session_factory=None if args.plan else _default_session_factory(),
    )
    return 1 if report.aborted_pre_flight else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
