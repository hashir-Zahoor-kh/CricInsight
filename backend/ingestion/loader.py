"""Idempotent loader for normalized CricInsight records.

Inputs are already-validated `Normalized*` Pydantic models from the
normalizer. This module's job is purely to push them into Postgres
in a way that's safe to re-run on the same data.

Three upsert paths:

  Full player upsert
      ON CONFLICT (external_id) DO UPDATE every column. Used by the
      seed script for explicit player profiles where we have rich
      data (country, role, styles, DOB).

  Stub player upsert
      ON CONFLICT (external_id) DO NOTHING. Used internally when we
      see a player in a scorecard but don't have their full profile.
      The DO-NOTHING is critical: without it, ingesting a match
      would overwrite a richly-populated player record with the
      scorecard's name+external_id-only stub.

  Match / stats upsert
      ON CONFLICT (external_id) / (match_id, player_id, innings_number)
      DO UPDATE all data columns. Stats can legitimately change if a
      scorecard is amended after the fact (correction, super-over
      revision); upsert lets us absorb that.

All DO-UPDATE statements explicitly set `updated_at = NOW()` because
SQLAlchemy's onupdate= callback only fires on ORM-driven UPDATEs, not
on raw pg_insert ON CONFLICT DO UPDATE.

Caller is responsible for committing the session — the loader runs
inside whatever transaction context the caller provides. That keeps
this module testable (rollback after each test) and lets the seed
script wrap a whole match's worth of writes in one transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    BattingStats,
    BowlingStats,
    Match,
    Player,
)

from .schemas import (
    NormalizedBattingStats,
    NormalizedBowlingStats,
    NormalizedMatch,
    NormalizedMatchResult,
    NormalizedPlayer,
)

logger = logging.getLogger(__name__)


@dataclass
class LoadCounts:
    """How many rows the loader touched.

    `inserted` is rows that didn't previously exist; `updated` is
    rows that ON CONFLICT updated. Sum = batch size minus skipped.
    """

    players_inserted: int = 0
    players_updated: int = 0
    matches_inserted: int = 0
    matches_updated: int = 0
    batting_inserted: int = 0
    batting_updated: int = 0
    bowling_inserted: int = 0
    bowling_updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def __add__(self, other: "LoadCounts") -> "LoadCounts":
        return LoadCounts(
            players_inserted=self.players_inserted + other.players_inserted,
            players_updated=self.players_updated + other.players_updated,
            matches_inserted=self.matches_inserted + other.matches_inserted,
            matches_updated=self.matches_updated + other.matches_updated,
            batting_inserted=self.batting_inserted + other.batting_inserted,
            batting_updated=self.batting_updated + other.batting_updated,
            bowling_inserted=self.bowling_inserted + other.bowling_inserted,
            bowling_updated=self.bowling_updated + other.bowling_updated,
            skipped=self.skipped + other.skipped,
            errors=self.errors + other.errors,
        )

    def summary(self) -> str:
        return (
            f"players: {self.players_inserted} inserted / "
            f"{self.players_updated} updated, "
            f"matches: {self.matches_inserted} inserted / "
            f"{self.matches_updated} updated, "
            f"batting: {self.batting_inserted} inserted / "
            f"{self.batting_updated} updated, "
            f"bowling: {self.bowling_inserted} inserted / "
            f"{self.bowling_updated} updated, "
            f"skipped: {self.skipped}"
        )


# ---------------------------------------------------------------- helpers

def _player_dict(p: NormalizedPlayer) -> dict[str, Any]:
    """Convert a NormalizedPlayer to the column dict pg_insert expects."""
    return {
        "external_id": p.external_id,
        "name": p.name,
        "country": p.country,
        "batting_style": p.batting_style,
        "bowling_style": p.bowling_style,
        # Pydantic enum members → their .value for SQLAlchemy's enum column.
        "role": p.role.value if p.role is not None else None,
        "date_of_birth": p.date_of_birth,
    }


def _match_dict(m: NormalizedMatch) -> dict[str, Any]:
    return {
        "external_id": m.external_id,
        "match_type": m.match_type.value,
        "venue": m.venue,
        "ground": m.ground,
        "date": m.date,
        "team1": m.team1,
        "team2": m.team2,
        "winner": m.winner,
        "toss_winner": m.toss_winner,
        "toss_decision": m.toss_decision.value if m.toss_decision is not None else None,
        "result_margin": m.result_margin,
    }


def _count(session: Session, model) -> int:
    """Single-row COUNT(*) — used to compute inserted-vs-updated deltas."""
    return session.scalar(select(func.count()).select_from(model)) or 0


# ---------------------------------------------------------------- players

def _upsert_players_full(
    session: Session, players: list[NormalizedPlayer]
) -> tuple[int, int]:
    """Full upsert of explicit player profiles. Returns (inserted, updated)."""
    if not players:
        return 0, 0

    # Collapse on external_id within the batch — pg_insert can't have two
    # rows with the same conflict target in a single INSERT. Take the
    # last occurrence (later wins) since callers may stream updates.
    deduped: dict[str | None, NormalizedPlayer] = {}
    for p in players:
        if p.external_id is None:
            # No external_id means no upsert key; insert whatever it is
            # and accept it'll dupe on re-runs. Nothing in the seed
            # path actually triggers this — every CricAPI player has an
            # id — but defending the function in isolation.
            deduped[id(p)] = p  # synthesise a unique key
        else:
            deduped[p.external_id] = p

    rows = [_player_dict(p) for p in deduped.values()]

    before = _count(session, Player)

    stmt = pg_insert(Player).values(rows)
    # Build the SET clause: every data column gets refreshed from the
    # incoming row, plus updated_at is bumped to NOW() since pg_insert
    # bypasses the SQLAlchemy onupdate= hook.
    update_cols = {
        "name": stmt.excluded.name,
        "country": stmt.excluded.country,
        "batting_style": stmt.excluded.batting_style,
        "bowling_style": stmt.excluded.bowling_style,
        "role": stmt.excluded.role,
        "date_of_birth": stmt.excluded.date_of_birth,
        "updated_at": func.now(),
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["external_id"],
        set_=update_cols,
    )
    session.execute(stmt)
    session.flush()

    after = _count(session, Player)
    inserted = after - before
    updated = len(rows) - inserted
    return inserted, updated


def _upsert_players_stub(
    session: Session, players: list[NormalizedPlayer]
) -> tuple[int, int]:
    """Insert-only upsert for players seen in scorecards.

    DO NOTHING on conflict so we never overwrite a rich profile with
    a name+external_id-only stub. Returns (inserted, conflicted).
    """
    if not players:
        return 0, 0

    deduped = {p.external_id: p for p in players if p.external_id is not None}
    if not deduped:
        return 0, 0

    rows = [_player_dict(p) for p in deduped.values()]

    before = _count(session, Player)
    stmt = pg_insert(Player).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"])
    session.execute(stmt)
    session.flush()
    after = _count(session, Player)

    inserted = after - before
    conflicted = len(rows) - inserted
    return inserted, conflicted


def load_players(
    session: Session, players: Iterable[NormalizedPlayer]
) -> LoadCounts:
    """Public entry point for loading explicit player profiles."""
    counts = LoadCounts()
    batch = list(players)
    inserted, updated = _upsert_players_full(session, batch)
    counts.players_inserted += inserted
    counts.players_updated += updated
    logger.info(
        "load_players: %d inserted, %d updated", inserted, updated
    )
    return counts


# ---------------------------------------------------------- match + stats

def _resolve_player_ids(
    session: Session,
    refs: list[tuple[str | None, str]],
) -> dict[tuple[str | None, str], int]:
    """Map (external_id, name) tuples to player.id.

    Prefers external_id; falls back to a case-sensitive name lookup
    when external_id is missing or doesn't match any row. The
    fallback path matters for older fixtures that lack CricAPI UUIDs.
    """
    ext_ids = {ref[0] for ref in refs if ref[0]}
    names = {ref[1] for ref in refs if ref[1]}

    rows = session.execute(
        select(Player.id, Player.external_id, Player.name).where(
            (Player.external_id.in_(ext_ids) if ext_ids else False)
            | (Player.name.in_(names) if names else False)
        )
    ).all()
    by_ext: dict[str, int] = {}
    by_name: dict[str, int] = {}
    for player_id, external_id, name in rows:
        if external_id:
            by_ext[external_id] = player_id
        if name:
            by_name.setdefault(name, player_id)

    resolved: dict[tuple[str | None, str], int] = {}
    for ref in refs:
        external_id, name = ref
        if external_id and external_id in by_ext:
            resolved[ref] = by_ext[external_id]
        elif name in by_name:
            resolved[ref] = by_name[name]
    return resolved


def _upsert_match(session: Session, match: NormalizedMatch) -> tuple[int, int]:
    """Upsert a single match by external_id. Returns (inserted, updated)."""
    before = _count(session, Match)

    stmt = pg_insert(Match).values([_match_dict(match)])
    stmt = stmt.on_conflict_do_update(
        index_elements=["external_id"],
        set_={
            "match_type": stmt.excluded.match_type,
            "venue": stmt.excluded.venue,
            "ground": stmt.excluded.ground,
            "date": stmt.excluded.date,
            "team1": stmt.excluded.team1,
            "team2": stmt.excluded.team2,
            "winner": stmt.excluded.winner,
            "toss_winner": stmt.excluded.toss_winner,
            "toss_decision": stmt.excluded.toss_decision,
            "result_margin": stmt.excluded.result_margin,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)
    session.flush()

    after = _count(session, Match)
    inserted = after - before  # 0 or 1
    updated = 1 - inserted
    return inserted, updated


def _match_id_for(session: Session, external_id: str) -> int:
    """Look up a match's internal id after upsert."""
    pid = session.scalar(
        select(Match.id).where(Match.external_id == external_id)
    )
    if pid is None:  # pragma: no cover — only reachable if upsert silently failed
        raise RuntimeError(f"match upsert for {external_id} produced no id")
    return pid


def _upsert_batting(
    session: Session,
    match_id: int,
    cards: list[NormalizedBattingStats],
    player_ids: dict[tuple[str | None, str], int],
) -> tuple[int, int]:
    if not cards:
        return 0, 0

    rows: list[dict[str, Any]] = []
    for c in cards:
        ref = (c.player_external_id, c.player_name)
        player_id = player_ids.get(ref)
        if player_id is None:
            logger.warning(
                "batting card for unknown player %r (external_id=%r) — skipped",
                c.player_name, c.player_external_id,
            )
            continue
        rows.append({
            "player_id": player_id,
            "match_id": match_id,
            "runs": c.runs,
            "balls_faced": c.balls_faced,
            "fours": c.fours,
            "sixes": c.sixes,
            "strike_rate": c.strike_rate,
            "dismissal_type": c.dismissal_type,
            "innings_number": c.innings_number,
            "position": c.position,
        })

    if not rows:
        return 0, 0

    before = _count(session, BattingStats)
    stmt = pg_insert(BattingStats).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["match_id", "player_id", "innings_number"],
        set_={
            "runs": stmt.excluded.runs,
            "balls_faced": stmt.excluded.balls_faced,
            "fours": stmt.excluded.fours,
            "sixes": stmt.excluded.sixes,
            "strike_rate": stmt.excluded.strike_rate,
            "dismissal_type": stmt.excluded.dismissal_type,
            "position": stmt.excluded.position,
        },
    )
    session.execute(stmt)
    session.flush()
    after = _count(session, BattingStats)

    inserted = after - before
    updated = len(rows) - inserted
    return inserted, updated


def _upsert_bowling(
    session: Session,
    match_id: int,
    cards: list[NormalizedBowlingStats],
    player_ids: dict[tuple[str | None, str], int],
) -> tuple[int, int]:
    if not cards:
        return 0, 0

    rows: list[dict[str, Any]] = []
    for c in cards:
        ref = (c.player_external_id, c.player_name)
        player_id = player_ids.get(ref)
        if player_id is None:
            logger.warning(
                "bowling card for unknown player %r (external_id=%r) — skipped",
                c.player_name, c.player_external_id,
            )
            continue
        rows.append({
            "player_id": player_id,
            "match_id": match_id,
            "overs": c.overs,
            "maidens": c.maidens,
            "runs_conceded": c.runs_conceded,
            "wickets": c.wickets,
            "economy_rate": c.economy_rate,
            "extras": c.extras,
            "innings_number": c.innings_number,
        })

    if not rows:
        return 0, 0

    before = _count(session, BowlingStats)
    stmt = pg_insert(BowlingStats).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["match_id", "player_id", "innings_number"],
        set_={
            "overs": stmt.excluded.overs,
            "maidens": stmt.excluded.maidens,
            "runs_conceded": stmt.excluded.runs_conceded,
            "wickets": stmt.excluded.wickets,
            "economy_rate": stmt.excluded.economy_rate,
            "extras": stmt.excluded.extras,
        },
    )
    session.execute(stmt)
    session.flush()
    after = _count(session, BowlingStats)

    inserted = after - before
    updated = len(rows) - inserted
    return inserted, updated


def _stub_players_from_scorecard(
    result: NormalizedMatchResult,
) -> list[NormalizedPlayer]:
    """Synthesise minimal NormalizedPlayer rows for everyone who
    appears in the scorecard. Deduplicated on (external_id, name).

    These are stub upserts (ON CONFLICT DO NOTHING) so they only
    create players that don't already exist — they never clobber
    rich profiles loaded by load_players().
    """
    seen: set[tuple[str | None, str]] = set()
    stubs: list[NormalizedPlayer] = []
    for card in [*result.batting, *result.bowling]:
        ref = (card.player_external_id, card.player_name)
        if ref in seen:
            continue
        seen.add(ref)
        if card.player_external_id is None:
            # No id, nothing to dedupe a stub against. The seed script
            # is unlikely to hit this path because real CricAPI data
            # always has player ids. If/when it does, we'd want to
            # query by name first; skipping for now keeps the stub
            # path simple.
            continue
        stubs.append(
            NormalizedPlayer(
                external_id=card.player_external_id,
                name=card.player_name,
            )
        )
    return stubs


def load_match_result(
    session: Session, result: NormalizedMatchResult
) -> LoadCounts:
    """Load one match (header + every batting and bowling card).

    Order of operations:
      1. Stub-upsert all players in the scorecard so FKs can resolve.
      2. Upsert the match header.
      3. Resolve internal player ids for every stat row.
      4. Upsert batting + bowling stats.
    """
    counts = LoadCounts()

    # Step 1: stub-upsert players from scorecard.
    stubs = _stub_players_from_scorecard(result)
    p_inserted, p_conflicted = _upsert_players_stub(session, stubs)
    counts.players_inserted += p_inserted
    # Stub conflicts aren't "updates" — they're rows we deliberately
    # didn't touch. Keep them out of players_updated.

    # Step 2: upsert the match header.
    m_inserted, m_updated = _upsert_match(session, result.match)
    counts.matches_inserted += m_inserted
    counts.matches_updated += m_updated

    match_id = _match_id_for(session, result.match.external_id)

    # Step 3: build the player id map.
    refs = [(c.player_external_id, c.player_name) for c in result.batting]
    refs += [(c.player_external_id, c.player_name) for c in result.bowling]
    refs = list({r for r in refs})  # dedupe
    player_ids = _resolve_player_ids(session, refs)

    # Step 4: stats.
    bi, bu = _upsert_batting(session, match_id, result.batting, player_ids)
    counts.batting_inserted += bi
    counts.batting_updated += bu

    bwi, bwu = _upsert_bowling(session, match_id, result.bowling, player_ids)
    counts.bowling_inserted += bwi
    counts.bowling_updated += bwu

    logger.info("load_match_result %s: %s", result.match.external_id, counts.summary())
    return counts


def load_match_results(
    session: Session, results: Iterable[NormalizedMatchResult]
) -> LoadCounts:
    """Bulk loader. Each match gets its own savepoint so a single
    bad record doesn't take the rest down with it."""
    total = LoadCounts()
    for result in results:
        try:
            with session.begin_nested():  # savepoint per match
                total = total + load_match_result(session, result)
        except Exception as exc:  # pragma: no cover — exercised by manual testing only
            logger.error(
                "load failed for match %s: %s",
                result.match.external_id, exc,
            )
            total.errors.append(f"{result.match.external_id}: {exc}")
            total.skipped += 1
    return total
