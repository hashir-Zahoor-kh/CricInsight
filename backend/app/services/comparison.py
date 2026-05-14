"""Service layer for the flagship `/compare` endpoint.

Heavy SQL aggregation kept here so the router stays a thin
URL→service→response wrapper. The service consumes an AsyncSession
and returns the validated `ComparisonResponse` ready to ship.

Five sub-queries per call:

  1. Both players' profile rows (lookup by id).
  2. Career batting rollup per player in the requested format.
  3. Career bowling rollup per player in the requested format.
  4. Last-10 batting + bowling innings per player (form guide).
  5. Common-opponent breakdown.

Each is a single round-trip; total = 5 RTTs to Postgres for one
/compare request. Could be folded into fewer queries with CTEs
but the readability win of separate queries outweighs the latency
delta at this scale.

Minimum-data threshold (5 innings) is checked AFTER each rollup —
the corresponding block is still returned (with raw counts) but a
DataQualityWarning is appended so the dashboard can render an
"insufficient data" notice rather than a chart from 2 innings.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from sqlalchemy import (
    Float,
    Integer,
    and_,
    case,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BattingStats, BowlingStats, Match, Player
from app.models.enums import MatchType, PlayerRole
from app.schemas import (
    BattingCareerStats,
    BowlingCareerStats,
    CommonOpponentBlock,
    ComparisonResponse,
    DataQualityWarning,
    FormGuideEntry,
    PlayerComparisonSlot,
    PlayerProfileCard,
)

logger = logging.getLogger(__name__)

# Minimum innings before we consider a stat block "trustworthy". Below
# this we still return the numbers (the dashboard renders them) but
# attach a data_quality warning.
MIN_INNINGS_THRESHOLD = 5

# Form guide cap — must match the Pydantic max_length on FormGuideEntry.
FORM_GUIDE_LIMIT = 10


# ====================================================================
# Errors
# ====================================================================

class PlayerNotFound(Exception):
    """Raised when a requested player id doesn't exist. Router maps
    this to a 404."""

    def __init__(self, player_id: int):
        self.player_id = player_id
        super().__init__(f"player not found: id={player_id}")


# ====================================================================
# primary_role derivation
# ====================================================================

async def _derive_roles(
    session: AsyncSession, player: Player
) -> tuple[PlayerRole, PlayerRole | None]:
    """Return (primary_role, secondary_role) for a player.

    primary_role rules (Feature 1.2 explicit form):
      * Declared `player.role` wins if present.
      * 0 batting innings + >0 bowling innings → BOWLER.
      * >0 batting innings + 0 bowling innings → BATSMAN.
      * Both > 0 → 1.5× innings-ratio decides BATSMAN vs BOWLER vs
        ALL_ROUNDER.
      * 0 + 0 → BATSMAN (sensible default for the cold-start case).

    secondary_role surfaces a non-trivial second skill so the
    dashboard can label "primarily a bowler, also a batter" without
    re-doing the analytics on the client:
      * primary BATSMAN / WICKETKEEPER with any bowling innings
        → secondary BOWLER
      * primary BOWLER with any batting innings
        → secondary BATSMAN
      * primary ALL_ROUNDER → secondary reflects the dominant side
        (BATSMAN if bat innings ≥ bowl innings, else BOWLER).
      * Otherwise null.
    """
    bat_innings = await session.scalar(
        select(func.count(BattingStats.id)).where(BattingStats.player_id == player.id)
    ) or 0
    bowl_innings = await session.scalar(
        select(func.count(BowlingStats.id)).where(BowlingStats.player_id == player.id)
    ) or 0

    # ---- primary ----
    if player.role is not None:
        primary = player.role
    elif bat_innings == 0 and bowl_innings == 0:
        primary = PlayerRole.BATSMAN
    elif bat_innings == 0 and bowl_innings > 0:
        primary = PlayerRole.BOWLER
    elif bowl_innings == 0 and bat_innings > 0:
        primary = PlayerRole.BATSMAN
    elif bat_innings >= 1.5 * bowl_innings:
        primary = PlayerRole.BATSMAN
    elif bowl_innings >= 1.5 * bat_innings:
        primary = PlayerRole.BOWLER
    else:
        primary = PlayerRole.ALL_ROUNDER

    # ---- secondary ----
    secondary: PlayerRole | None = None
    if primary in (PlayerRole.BATSMAN, PlayerRole.WICKETKEEPER):
        if bowl_innings > 0:
            secondary = PlayerRole.BOWLER
    elif primary is PlayerRole.BOWLER:
        if bat_innings > 0:
            secondary = PlayerRole.BATSMAN
    elif primary is PlayerRole.ALL_ROUNDER:
        # All-rounder already implies both sides — surface the
        # dominant skill as a tiebreaker so the dashboard can render
        # an "all-rounder · leans batting" tag.
        secondary = (
            PlayerRole.BATSMAN
            if bat_innings >= bowl_innings
            else PlayerRole.BOWLER
        )

    return primary, secondary


async def _derive_primary_role(
    session: AsyncSession, player: Player
) -> PlayerRole:
    """Back-compat shim — Feature 1.2 added _derive_roles which
    returns the (primary, secondary) tuple. Older call sites that
    only need primary call this thin wrapper."""
    primary, _ = await _derive_roles(session, player)
    return primary


# ====================================================================
# Profile card
# ====================================================================

async def _build_profile(
    session: AsyncSession, player: Player
) -> PlayerProfileCard:
    primary = await _derive_primary_role(session, player)
    return PlayerProfileCard(
        id=player.id,
        external_id=player.external_id,
        name=player.name,
        country=player.country,
        role=player.role,
        primary_role=primary,
        batting_style=player.batting_style,
        bowling_style=player.bowling_style,
    )


# ====================================================================
# Career batting / bowling rollup in a format
# ====================================================================

async def _batting_career_stats(
    session: AsyncSession, player_id: int, fmt: MatchType
) -> BattingCareerStats | None:
    """Aggregate batting career stats for one player in a format.

    Returns None when the player has 0 batting innings in the format
    (so the slot's `batting` field can stay null rather than carry
    a meaningless all-zero block).
    """
    # `not_outs` is derived from dismissal_type — null OR "not out" is
    # treated as a not-out. CricAPI's wording varies (some entries say
    # "not out", others "didn't bat" — the latter shouldn't be in our
    # data because we only insert rows where the player batted, but
    # the COALESCE keeps the COUNT honest if it ever creeps in).
    not_out_predicate = or_(
        BattingStats.dismissal_type.is_(None),
        func.lower(BattingStats.dismissal_type).like("%not out%"),
    )

    stmt = (
        select(
            func.count(func.distinct(BattingStats.match_id)).label("matches"),
            func.count(BattingStats.id).label("innings"),
            func.sum(case((not_out_predicate, 1), else_=0)).label("not_outs"),
            func.coalesce(func.sum(BattingStats.runs), 0).label("runs"),
            func.coalesce(func.sum(BattingStats.fours), 0).label("fours"),
            func.coalesce(func.sum(BattingStats.sixes), 0).label("sixes"),
            func.max(BattingStats.runs).label("highest"),
            # Counters for milestone stats — runs >= 50 and < 100 = 50,
            # runs >= 100 = 100. SQL CASE keeps it inline.
            func.sum(
                case((and_(BattingStats.runs >= 50, BattingStats.runs < 100), 1), else_=0)
            ).label("fifties"),
            func.sum(case((BattingStats.runs >= 100, 1), else_=0)).label("hundreds"),
            # Total balls faced (only over rows where balls is non-null)
            func.coalesce(func.sum(BattingStats.balls_faced), 0).label("balls_faced"),
        )
        .join(Match, BattingStats.match_id == Match.id)
        .where(BattingStats.player_id == player_id, Match.match_type == fmt)
    )

    row = (await session.execute(stmt)).one()
    innings = int(row.innings or 0)
    if innings == 0:
        return None

    not_outs = int(row.not_outs or 0)
    runs = int(row.runs or 0)
    balls_faced = int(row.balls_faced or 0)

    # Average = runs / (innings - not_outs). Undefined when every
    # innings was a not-out (denominator 0); return None there.
    dismissals = innings - not_outs
    average = round(runs / dismissals, 2) if dismissals > 0 else None

    # Strike rate = (runs / balls_faced) * 100. Undefined when
    # balls_faced is 0 — early-era records that lacked balls data.
    strike_rate = (
        round((runs / balls_faced) * 100, 2) if balls_faced > 0 else None
    )

    return BattingCareerStats(
        matches=int(row.matches or 0),
        innings=innings,
        not_outs=not_outs,
        runs=runs,
        average=average,
        strike_rate=strike_rate,
        fifties=int(row.fifties or 0),
        hundreds=int(row.hundreds or 0),
        highest_score=int(row.highest or 0),
        fours=int(row.fours or 0),
        sixes=int(row.sixes or 0),
    )


async def _bowling_career_stats(
    session: AsyncSession, player_id: int, fmt: MatchType
) -> BowlingCareerStats | None:
    stmt = (
        select(
            func.count(func.distinct(BowlingStats.match_id)).label("matches"),
            func.count(BowlingStats.id).label("innings"),
            func.coalesce(func.sum(BowlingStats.overs), 0.0).label("overs"),
            func.coalesce(func.sum(BowlingStats.runs_conceded), 0).label("runs"),
            func.coalesce(func.sum(BowlingStats.wickets), 0).label("wickets"),
            func.sum(case((BowlingStats.wickets >= 5, 1), else_=0)).label("five_fers"),
            # Best figures: fewest runs at the highest wicket count.
            # Fetched separately below — easier to reason about.
        )
        .join(Match, BowlingStats.match_id == Match.id)
        .where(BowlingStats.player_id == player_id, Match.match_type == fmt)
    )

    row = (await session.execute(stmt)).one()
    innings = int(row.innings or 0)
    if innings == 0:
        return None

    overs = float(row.overs or 0.0)
    runs_conceded = int(row.runs or 0)
    wickets = int(row.wickets or 0)

    average = round(runs_conceded / wickets, 2) if wickets > 0 else None
    economy = round(runs_conceded / overs, 2) if overs > 0 else None
    # Bowling strike rate = balls bowled / wickets. Cricket overs are
    # decimal-but-not-base-10 (4.3 = 4 overs + 3 balls), but for
    # rollups we use the simple 6-balls-per-over conversion.
    bowling_sr = (
        round((overs * 6) / wickets, 2) if wickets > 0 and overs > 0 else None
    )

    best_figures = await _best_bowling_figures(session, player_id, fmt)

    matches = int(row.matches or 0)
    # wickets_per_match: derived metric for the bowling radar's
    # "high is better" axis. Null when matches == 0 so the dashboard
    # can distinguish "no data" from "0 wickets per match".
    wickets_per_match = (
        round(wickets / matches, 2) if matches > 0 else None
    )
    # dot_ball_pct stays None — needs ball-by-ball storage. Reserved
    # as a null field on the response so the API contract is stable
    # when we move to per-delivery ingestion.

    return BowlingCareerStats(
        matches=matches,
        innings=innings,
        overs_bowled=overs,
        runs_conceded=runs_conceded,
        wickets=wickets,
        average=average,
        economy=economy,
        bowling_strike_rate=bowling_sr,
        wickets_per_match=wickets_per_match,
        dot_ball_pct=None,
        five_wicket_hauls=int(row.five_fers or 0),
        best_figures=best_figures,
    )


async def _best_bowling_figures(
    session: AsyncSession, player_id: int, fmt: MatchType
) -> str | None:
    """Highest wickets, lowest runs as the tiebreaker. Returns "5/28"
    style or None for bowlers with no wickets in the format."""
    stmt = (
        select(BowlingStats.wickets, BowlingStats.runs_conceded)
        .join(Match, BowlingStats.match_id == Match.id)
        .where(BowlingStats.player_id == player_id, Match.match_type == fmt)
        .order_by(BowlingStats.wickets.desc(), BowlingStats.runs_conceded.asc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None or row.wickets == 0:
        return None
    return f"{row.wickets}/{row.runs_conceded}"


# ====================================================================
# Form guide — last 10 innings
# ====================================================================

def _opponent_for(player_country: str | None, m: Match) -> str:
    """Whichever team isn't the player's country."""
    if player_country and m.team1 == player_country:
        return m.team2
    if player_country and m.team2 == player_country:
        return m.team1
    # If the player has no declared country, fall back to team2 — the
    # form-guide field still has a value, even if it's not strictly
    # "their opponent". The dashboard treats this as informational.
    return m.team2


async def _form_guide(
    session: AsyncSession,
    player: Player,
    fmt: MatchType,
    primary_role: PlayerRole,
) -> list[FormGuideEntry]:
    """Most-recent-10 innings for the player in the format.

    Pure batters: only batting innings.
    Pure bowlers: only bowling innings.
    All-rounders: most recent 10 across either side.

    Implementation: merge two queries (batting innings + bowling
    innings) by match date in Python, then take top 10. The dataset
    per player is small (hundreds of rows max), so the merge cost is
    negligible compared to the query simplicity gain.
    """
    entries: list[tuple[Match, BattingStats | None, BowlingStats | None]] = []

    if primary_role in (PlayerRole.BATSMAN, PlayerRole.WICKETKEEPER, PlayerRole.ALL_ROUNDER):
        stmt = (
            select(Match, BattingStats)
            .join(Match, BattingStats.match_id == Match.id)
            .where(BattingStats.player_id == player.id, Match.match_type == fmt)
            .order_by(Match.date.desc())
            .limit(FORM_GUIDE_LIMIT)
        )
        for match, bs in (await session.execute(stmt)).all():
            entries.append((match, bs, None))

    if primary_role in (PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER):
        stmt = (
            select(Match, BowlingStats)
            .join(Match, BowlingStats.match_id == Match.id)
            .where(BowlingStats.player_id == player.id, Match.match_type == fmt)
            .order_by(Match.date.desc())
            .limit(FORM_GUIDE_LIMIT)
        )
        for match, bs in (await session.execute(stmt)).all():
            entries.append((match, None, bs))

    # Sort merged list by match date desc and take top N.
    entries.sort(key=lambda e: e[0].date, reverse=True)
    entries = entries[:FORM_GUIDE_LIMIT]

    out: list[FormGuideEntry] = []
    for match, bat, bowl in entries:
        opponent = _opponent_for(player.country, match)
        out.append(
            FormGuideEntry(
                match_external_id=match.external_id,
                date=match.date,
                opponent=opponent,
                venue=match.venue,
                match_type=match.match_type,
                batting_runs=bat.runs if bat else None,
                batting_balls=bat.balls_faced if bat else None,
                batting_strike_rate=bat.strike_rate if bat else None,
                not_out=(
                    (bat.dismissal_type is None
                     or "not out" in (bat.dismissal_type or "").lower())
                    if bat else None
                ),
                bowling_overs=bowl.overs if bowl else None,
                bowling_wickets=bowl.wickets if bowl else None,
                bowling_runs_conceded=bowl.runs_conceded if bowl else None,
                bowling_economy=bowl.economy_rate if bowl else None,
            )
        )
    return out


# ====================================================================
# Common opponents
# ====================================================================

async def _opponents_set(
    session: AsyncSession,
    player_id: int,
    player_country: str | None,
    fmt: MatchType,
) -> set[str]:
    """Set of distinct opponent team names this player has faced in
    the format. Built from both batting and bowling participation."""
    if player_country is None:
        return set()

    # Distinct matches the player participated in (either batting or
    # bowling), filtered to the requested format.
    stmt = (
        select(Match.team1, Match.team2)
        .where(
            Match.match_type == fmt,
            Match.id.in_(
                select(BattingStats.match_id).where(BattingStats.player_id == player_id)
            )
            | Match.id.in_(
                select(BowlingStats.match_id).where(BowlingStats.player_id == player_id)
            ),
        )
        .distinct()
    )
    opponents: set[str] = set()
    for team1, team2 in (await session.execute(stmt)).all():
        if team1 == player_country and team2:
            opponents.add(team2)
        elif team2 == player_country and team1:
            opponents.add(team1)
    return opponents


async def _vs_opponent_batting(
    session: AsyncSession,
    player_id: int,
    player_country: str,
    opponent: str,
    fmt: MatchType,
) -> tuple[int, float | None, float | None]:
    """Returns (matches, batting_avg, batting_sr) for player vs opponent."""
    stmt = (
        select(
            func.count(func.distinct(BattingStats.match_id)).label("matches"),
            func.coalesce(func.sum(BattingStats.runs), 0).label("runs"),
            func.coalesce(func.sum(BattingStats.balls_faced), 0).label("balls"),
            func.count(BattingStats.id).label("innings"),
            func.sum(
                case(
                    (
                        or_(
                            BattingStats.dismissal_type.is_(None),
                            func.lower(BattingStats.dismissal_type).like("%not out%"),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("not_outs"),
        )
        .join(Match, BattingStats.match_id == Match.id)
        .where(
            BattingStats.player_id == player_id,
            Match.match_type == fmt,
            or_(
                and_(Match.team1 == player_country, Match.team2 == opponent),
                and_(Match.team2 == player_country, Match.team1 == opponent),
            ),
        )
    )
    row = (await session.execute(stmt)).one()
    innings = int(row.innings or 0)
    runs = int(row.runs or 0)
    balls = int(row.balls or 0)
    not_outs = int(row.not_outs or 0)
    dismissals = innings - not_outs
    avg = round(runs / dismissals, 2) if dismissals > 0 else None
    sr = round((runs / balls) * 100, 2) if balls > 0 else None
    return int(row.matches or 0), avg, sr


async def _vs_opponent_bowling(
    session: AsyncSession,
    player_id: int,
    player_country: str,
    opponent: str,
    fmt: MatchType,
) -> tuple[int, int, float | None]:
    """Returns (matches, wickets, economy) for player vs opponent."""
    stmt = (
        select(
            func.count(func.distinct(BowlingStats.match_id)).label("matches"),
            func.coalesce(func.sum(BowlingStats.wickets), 0).label("wickets"),
            func.coalesce(func.sum(BowlingStats.runs_conceded), 0).label("runs"),
            func.coalesce(func.sum(BowlingStats.overs), 0.0).label("overs"),
        )
        .join(Match, BowlingStats.match_id == Match.id)
        .where(
            BowlingStats.player_id == player_id,
            Match.match_type == fmt,
            or_(
                and_(Match.team1 == player_country, Match.team2 == opponent),
                and_(Match.team2 == player_country, Match.team1 == opponent),
            ),
        )
    )
    row = (await session.execute(stmt)).one()
    matches = int(row.matches or 0)
    wickets = int(row.wickets or 0)
    overs = float(row.overs or 0.0)
    runs = int(row.runs or 0)
    economy = round(runs / overs, 2) if overs > 0 else None
    return matches, wickets, economy


async def _common_opponents_block(
    session: AsyncSession,
    p1: Player,
    p2: Player,
    fmt: MatchType,
    show_batting: bool,
    show_bowling: bool,
) -> list[CommonOpponentBlock]:
    """Build per-opponent rollup for opponents both players have faced."""
    # Both players need a country to anchor the "opponent" axis. If
    # either is missing, return empty list — the dashboard hides the
    # section.
    if not p1.country or not p2.country:
        return []

    common = (
        await _opponents_set(session, p1.id, p1.country, fmt)
    ) & (
        await _opponents_set(session, p2.id, p2.country, fmt)
    )
    # Remove "self" — if both players share country (e.g., two
    # Pakistan players in the same comparison), each other's country
    # would otherwise show up. Doesn't make sense as an opponent.
    common.discard(p1.country)
    common.discard(p2.country)

    blocks: list[CommonOpponentBlock] = []
    # Sort for stable response shape across runs.
    for opponent in sorted(common):
        block_kwargs: dict = {
            "opponent": opponent,
            "player1_matches": 0,
            "player2_matches": 0,
        }
        if show_batting:
            m1, avg1, sr1 = await _vs_opponent_batting(session, p1.id, p1.country, opponent, fmt)
            m2, avg2, sr2 = await _vs_opponent_batting(session, p2.id, p2.country, opponent, fmt)
            block_kwargs["player1_matches"] = max(block_kwargs["player1_matches"], m1)
            block_kwargs["player2_matches"] = max(block_kwargs["player2_matches"], m2)
            block_kwargs["player1_batting_average"] = avg1
            block_kwargs["player1_batting_strike_rate"] = sr1
            block_kwargs["player2_batting_average"] = avg2
            block_kwargs["player2_batting_strike_rate"] = sr2
        if show_bowling:
            m1, w1, e1 = await _vs_opponent_bowling(session, p1.id, p1.country, opponent, fmt)
            m2, w2, e2 = await _vs_opponent_bowling(session, p2.id, p2.country, opponent, fmt)
            block_kwargs["player1_matches"] = max(block_kwargs["player1_matches"], m1)
            block_kwargs["player2_matches"] = max(block_kwargs["player2_matches"], m2)
            block_kwargs["player1_bowling_wickets"] = w1
            block_kwargs["player1_bowling_economy"] = e1
            block_kwargs["player2_bowling_wickets"] = w2
            block_kwargs["player2_bowling_economy"] = e2
        blocks.append(CommonOpponentBlock(**block_kwargs))
    return blocks


# ====================================================================
# Top-level service entry
# ====================================================================

async def build_comparison(
    session: AsyncSession,
    player1_id: int,
    player2_id: int,
    fmt: MatchType,
) -> ComparisonResponse:
    """End-to-end /compare assembly."""
    # Load both players, raise if either is missing.
    p1 = await session.get(Player, player1_id)
    if p1 is None:
        raise PlayerNotFound(player1_id)
    p2 = await session.get(Player, player2_id)
    if p2 is None:
        raise PlayerNotFound(player2_id)

    p1_profile = await _build_profile(session, p1)
    p2_profile = await _build_profile(session, p2)

    # Pull secondary roles separately so the slot can surface them.
    # Cheap — _derive_roles re-runs the inning counts but those queries
    # are millisecond on indexed FKs. Could be unified with _build_profile
    # in a future refactor; keeping it minimal here for the Feature 1.2
    # diff.
    _, p1_secondary = await _derive_roles(session, p1)
    _, p2_secondary = await _derive_roles(session, p2)

    # Decide which panels to populate per side, based on primary_role.
    #
    # Pure batters → batting panel only.
    # Pure bowlers → bowling panel only.
    # All-rounders / wicketkeepers → both.
    #
    # We still query the "off side" because some all-rounders' stats
    # are dominated by one role and the user wants to see both numbers.
    def _wants_batting(role: PlayerRole) -> bool:
        return role in (
            PlayerRole.BATSMAN,
            PlayerRole.WICKETKEEPER,
            PlayerRole.ALL_ROUNDER,
        )

    def _wants_bowling(role: PlayerRole) -> bool:
        return role in (PlayerRole.BOWLER, PlayerRole.ALL_ROUNDER)

    p1_bat = (
        await _batting_career_stats(session, p1.id, fmt)
        if _wants_batting(p1_profile.primary_role) else None
    )
    p1_bowl = (
        await _bowling_career_stats(session, p1.id, fmt)
        if _wants_bowling(p1_profile.primary_role) else None
    )
    p2_bat = (
        await _batting_career_stats(session, p2.id, fmt)
        if _wants_batting(p2_profile.primary_role) else None
    )
    p2_bowl = (
        await _bowling_career_stats(session, p2.id, fmt)
        if _wants_bowling(p2_profile.primary_role) else None
    )

    p1_form = await _form_guide(session, p1, fmt, p1_profile.primary_role)
    p2_form = await _form_guide(session, p2, fmt, p2_profile.primary_role)

    # Common-opponent block: lean on whichever side both players
    # actually have stats for. Batters compare on batting, bowlers
    # compare on bowling, all-rounders show both rows.
    show_batting = (p1_bat is not None) and (p2_bat is not None)
    show_bowling = (p1_bowl is not None) and (p2_bowl is not None)
    common = await _common_opponents_block(
        session, p1, p2, fmt, show_batting, show_bowling
    )

    # Data-quality warnings — applied AFTER the rollups exist so the
    # dashboard still gets the raw counts to show "3 innings only"
    # underneath the chart. Threshold = 5 innings per side per panel.
    warnings: list[DataQualityWarning] = []

    def _check_innings(
        block: BattingCareerStats | BowlingCareerStats | None,
        player: str,
        kind: str,
    ) -> None:
        if block is None:
            return
        if block.innings < MIN_INNINGS_THRESHOLD:
            warnings.append(
                DataQualityWarning(
                    code=f"insufficient_innings_{player}_{kind}",
                    message=(
                        f"{kind} stats based on only {block.innings} innings "
                        f"in {fmt.value} (threshold {MIN_INNINGS_THRESHOLD}); "
                        f"averages may not be representative."
                    ),
                    affected=player,
                )
            )

    _check_innings(p1_bat, "player1", "batting")
    _check_innings(p1_bowl, "player1", "bowling")
    _check_innings(p2_bat, "player2", "batting")
    _check_innings(p2_bowl, "player2", "bowling")

    return ComparisonResponse(
        format=fmt,
        player1=PlayerComparisonSlot(
            profile=p1_profile,
            batting=p1_bat,
            bowling=p1_bowl,
            form_guide=p1_form,
            secondary_role=p1_secondary,
        ),
        player2=PlayerComparisonSlot(
            profile=p2_profile,
            batting=p2_bat,
            bowling=p2_bowl,
            form_guide=p2_form,
            secondary_role=p2_secondary,
        ),
        common_opponents=common,
        data_quality=warnings,
    )
