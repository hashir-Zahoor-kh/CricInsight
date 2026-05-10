"""Cricsheet-driven DB seed.

Replaces ingestion.seed (the CricAPI-driven version) for real-data
runs. Cricsheet is free and unlimited, so this script doesn't burn
any API quota — it just walks local extracted JSON files.

Pipeline:

  1. Wipe the existing DB (it had stub players with CricAPI UUIDs that
     won't match the Cricsheet UUIDs we're about to insert; cleaner
     to start fresh).

  2. For each target format, iterate Cricsheet match JSONs filtered
     to matches involving at least one seeded player, parse each
     into NormalizedMatchResult, and load via the existing
     loader.load_match_results — same idempotent upsert path the
     CricAPI seed uses, so behaviour is identical from the DB's
     perspective.

  3. After matches are loaded, build a NormalizedPlayer roster from
     the players seen across all loaded scorecards (the seeded names
     get the full-profile path; others stay as scorecard stubs that
     load_match_results inserts via DO-NOTHING upsert).

  4. Report counts and exit.

Run:
    python -m ingestion.seed_cricsheet               # default targets
    python -m ingestion.seed_cricsheet --no-wipe     # keep existing DB rows
    python -m ingestion.seed_cricsheet --no-download # use already-extracted dir
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.models.enums import MatchType
from ingestion.cricsheet_loader import (
    FilterConfig,
    ensure_archive,
    iter_filtered_matches,
    player_roster_from_results,
)
from ingestion.loader import (
    LoadCounts,
    load_match_results,
    load_players,
)
from ingestion.schemas import NormalizedMatchResult

logger = logging.getLogger(__name__)


# Same 22 names the CricAPI seed targeted — Pakistan core + the
# international comparison set. Matched fuzzily against Cricsheet's
# "BA Stokes" / "B Azam"-style names by the FilterConfig surname
# + first-initial pair logic.
SEEDED_PLAYER_NAMES: list[str] = [
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

# Per-format targets the user specified.
TARGETS: dict[MatchType, int] = {
    MatchType.T20I: 50,
    MatchType.ODI: 30,
    MatchType.TEST: 20,
}


@dataclass
class CricsheetSeedReport:
    matches_loaded_per_format: dict[str, int] = field(default_factory=dict)
    players_in_roster: int = 0
    db_counts: LoadCounts = field(default_factory=LoadCounts)
    wiped: bool = False

    def log(self) -> None:
        logger.info("=" * 60)
        logger.info("Cricsheet seed report")
        logger.info("  wiped existing data:  %s", self.wiped)
        for fmt, n in self.matches_loaded_per_format.items():
            logger.info("  %-6s matches loaded: %d", fmt, n)
        logger.info("  player roster size:   %d", self.players_in_roster)
        logger.info("  DB: %s", self.db_counts.summary())
        logger.info("=" * 60)


# --------------------------------------------------------------- helpers

def _wipe_db(session) -> None:
    """TRUNCATE everything we own, RESTART IDENTITY so id sequences
    start at 1 again. Keeps the schema (and alembic_version) intact."""
    from sqlalchemy import text
    session.execute(
        text(
            "TRUNCATE TABLE batting_stats, bowling_stats, matches, players "
            "RESTART IDENTITY CASCADE"
        )
    )
    session.commit()


def _default_session_factory():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://cricinsight:cricinsight@localhost:5432/cricinsight",
    )
    engine = create_engine(url, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


# --------------------------------------------------------------- run

def run_cricsheet_seed(
    *,
    targets: dict[MatchType, int] | None = None,
    seed_names: list[str] | None = None,
    download: bool = True,
    wipe: bool = True,
    db_session_factory=None,
) -> CricsheetSeedReport:
    """End-to-end: download → parse → filter → load."""
    targets = targets or TARGETS
    seed_names = seed_names or SEEDED_PLAYER_NAMES
    cfg = FilterConfig(seed_full_names=seed_names)

    if download:
        for fmt in targets:
            ensure_archive(fmt)

    report = CricsheetSeedReport()
    factory = db_session_factory or _default_session_factory()

    # All loaded results, retained so we can build the player roster
    # afterwards. Each NormalizedMatchResult is small (KB), so even
    # 100 matches is well under a megabyte.
    loaded_results: list[NormalizedMatchResult] = []

    with factory() as session:
        if wipe:
            _wipe_db(session)
            report.wiped = True

        # Merged player → country map across all matches; used by the
        # roster builder to backfill the `players.country` column so
        # the comparison page's common-opponents panel works.
        merged_country_map: dict[str, str] = {}

        for fmt, target in targets.items():
            count = 0
            results_for_fmt: list[NormalizedMatchResult] = []
            for source_id, result, country_map in iter_filtered_matches(
                fmt, cfg, limit=target
            ):
                results_for_fmt.append(result)
                merged_country_map.update(country_map)
                count += 1

            counts = load_match_results(session, results_for_fmt)
            report.db_counts = report.db_counts + counts
            report.matches_loaded_per_format[fmt.value] = count
            loaded_results.extend(results_for_fmt)
            session.commit()
            logger.info("loaded %d %s matches", count, fmt.value)

        # Promote seeded names to richer player profiles. Everyone else
        # remains as a scorecard-stub row inserted by load_match_results
        # via DO NOTHING upsert (so we don't clobber existing rows).
        roster = player_roster_from_results(
            loaded_results,
            seed_full_names=seed_names,
            country_map=merged_country_map,
        )
        report.players_in_roster = len(roster)
        if roster:
            counts = load_players(session, roster)
            report.db_counts = report.db_counts + counts
        session.commit()

    report.log()
    return report


# --------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingestion.seed_cricsheet",
        description="Seed CricInsight from local Cricsheet JSON archives.",
    )
    parser.add_argument(
        "--no-wipe",
        action="store_true",
        help="Keep existing DB rows. Default: TRUNCATE before load.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Don't fetch the Cricsheet archives — assume they're "
             "already extracted under cricsheet_data/.",
    )
    parser.add_argument(
        "--t20i",
        type=int,
        default=TARGETS[MatchType.T20I],
        help="Number of T20I matches to load.",
    )
    parser.add_argument(
        "--odi",
        type=int,
        default=TARGETS[MatchType.ODI],
        help="Number of ODI matches to load.",
    )
    parser.add_argument(
        "--test",
        type=int,
        default=TARGETS[MatchType.TEST],
        help="Number of Test matches to load.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load .env so DATABASE_URL_SYNC is available.
    try:
        from dotenv import load_dotenv

        backend_root = Path(__file__).resolve().parents[1]
        for candidate in (backend_root / ".env", backend_root.parent / ".env"):
            if candidate.exists():
                load_dotenv(candidate)
                break
    except ModuleNotFoundError:
        pass

    targets = {
        MatchType.T20I: args.t20i,
        MatchType.ODI: args.odi,
        MatchType.TEST: args.test,
    }

    report = run_cricsheet_seed(
        targets=targets,
        download=not args.no_download,
        wipe=not args.no_wipe,
    )
    return 0 if sum(report.matches_loaded_per_format.values()) > 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
