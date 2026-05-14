"""Analytics endpoints — including the flagship `/compare`.

Routers stay thin: parameter validation + dependency injection +
service-layer call + HTTPException mapping. All the SQL lives in
`app.services.comparison` (and siblings) so this file reads as a
list of API contracts rather than business logic.

Format validation runs at the parameter level: typing the `format`
query parameter as `MatchType` lets FastAPI reject anything outside
the enum with a 422 and a clear "must be one of: T20I, ODI, Test, T20"
message. No silent empty-stats surprises.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

from app.database import get_db
from app.models import BattingStats, BowlingStats, Match, Player
from app.models.enums import MatchType, TossDecision
from app.schemas import (
    ComparisonResponse,
    DataQualityWarning,
    FormatBreakdown,
    FormGuideEntry,
    FormGuideResponse,
    HeadToHeadResponse,
    PlayerAverageResponse,
    TimelineEntry,
    TimelineResponse,
    VenueStatsResponse,
)
from app.services.comparison import (
    MIN_INNINGS_THRESHOLD,
    PlayerNotFound,
    _batting_career_stats,
    _bowling_career_stats,
    _build_profile,
    _form_guide,
    build_comparison,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/compare",
    response_model=ComparisonResponse,
    summary="Side-by-side comparison of two players in a chosen format.",
    responses={
        404: {"description": "One or both player ids do not exist."},
        422: {"description": "Invalid format or missing required parameter."},
    },
)
async def compare_players(
    player1_id: int = Query(..., description="DB id of the first player."),
    player2_id: int = Query(..., description="DB id of the second player."),
    format: MatchType = Query(
        ...,
        description=(
            "Match format to scope the comparison to. Required — "
            "cross-format comparisons (T20I batting vs Test batting) "
            "are not meaningful, so the API refuses to do them."
        ),
    ),
    session: AsyncSession = Depends(get_db),
) -> ComparisonResponse:
    if player1_id == player2_id:
        # Comparing a player to themselves yields a perfect-mirror
        # response — usually a frontend bug. 422 makes the bug visible.
        raise HTTPException(
            status_code=422,
            detail="player1_id and player2_id must differ.",
        )

    try:
        return await build_comparison(session, player1_id, player2_id, format)
    except PlayerNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Player not found: id={exc.player_id}",
        ) from exc


# ====================================================================
# Single-player analytics
# ====================================================================

@router.get(
    "/player/{player_id}/average",
    response_model=PlayerAverageResponse,
    summary="Career batting/bowling averages broken down by format.",
)
async def player_averages(
    player_id: int,
    session: AsyncSession = Depends(get_db),
) -> PlayerAverageResponse:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found: id={player_id}")
    profile = await _build_profile(session, player)

    by_format: list[FormatBreakdown] = []
    warnings: list[DataQualityWarning] = []
    for fmt in MatchType:
        batting = await _batting_career_stats(session, player.id, fmt)
        bowling = await _bowling_career_stats(session, player.id, fmt)
        if batting is None and bowling is None:
            continue
        by_format.append(FormatBreakdown(format=fmt, batting=batting, bowling=bowling))
        if batting is not None and batting.innings < MIN_INNINGS_THRESHOLD:
            warnings.append(
                DataQualityWarning(
                    code=f"insufficient_innings_batting_{fmt.value.lower()}",
                    message=(
                        f"batting stats based on only {batting.innings} innings in "
                        f"{fmt.value}; threshold {MIN_INNINGS_THRESHOLD}."
                    ),
                    affected=fmt.value,
                )
            )
        if bowling is not None and bowling.innings < MIN_INNINGS_THRESHOLD:
            warnings.append(
                DataQualityWarning(
                    code=f"insufficient_innings_bowling_{fmt.value.lower()}",
                    message=(
                        f"bowling stats based on only {bowling.innings} innings in "
                        f"{fmt.value}; threshold {MIN_INNINGS_THRESHOLD}."
                    ),
                    affected=fmt.value,
                )
            )

    return PlayerAverageResponse(
        profile=profile,
        by_format=by_format,
        data_quality=warnings,
    )


@router.get(
    "/player/{player_id}/form",
    response_model=FormGuideResponse,
    summary="Last 10 innings as a sparkline-ready array.",
)
async def player_form(
    player_id: int,
    format: MatchType = Query(..., description="Format to scope the form guide to."),
    session: AsyncSession = Depends(get_db),
) -> FormGuideResponse:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found: id={player_id}")
    profile = await _build_profile(session, player)
    innings = await _form_guide(session, player, format, profile.primary_role)

    warnings: list[DataQualityWarning] = []
    if 0 < len(innings) < MIN_INNINGS_THRESHOLD:
        warnings.append(
            DataQualityWarning(
                code="insufficient_form_innings",
                message=(
                    f"only {len(innings)} innings available in {format.value}; "
                    f"sparkline rendering may be misleading below "
                    f"{MIN_INNINGS_THRESHOLD}."
                ),
            )
        )

    return FormGuideResponse(profile=profile, innings=innings, data_quality=warnings)


# ====================================================================
# Career timeline — per-year aggregation
# ====================================================================

@router.get(
    "/player/{player_id}/timeline",
    response_model=TimelineResponse,
    summary="Per-year batting and bowling stats for trend charts.",
)
async def player_timeline(
    player_id: int,
    format: MatchType = Query(..., description="Match format to scope the timeline to."),
    session: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found: id={player_id}")
    profile = await _build_profile(session, player)

    not_out_pred = or_(
        BattingStats.dismissal_type.is_(None),
        func.lower(BattingStats.dismissal_type).like("%not out%"),
    )

    bat_rows = (await session.execute(
        select(
            func.extract("year", Match.date).label("yr"),
            func.count(func.distinct(BattingStats.match_id)).label("matches"),
            func.coalesce(func.sum(BattingStats.runs), 0).label("runs"),
            func.sum(case((not_out_pred, 1), else_=0)).label("not_outs"),
            func.count(BattingStats.id).label("innings"),
            func.coalesce(func.sum(BattingStats.balls_faced), 0).label("balls_faced"),
        )
        .join(Match, BattingStats.match_id == Match.id)
        .where(BattingStats.player_id == player_id, Match.match_type == format)
        .group_by(func.extract("year", Match.date))
        .order_by(func.extract("year", Match.date))
    )).all()

    bowl_rows = (await session.execute(
        select(
            func.extract("year", Match.date).label("yr"),
            func.count(func.distinct(BowlingStats.match_id)).label("matches"),
            func.coalesce(func.sum(BowlingStats.wickets), 0).label("wickets"),
            func.coalesce(func.sum(BowlingStats.runs_conceded), 0).label("runs_conceded"),
            func.coalesce(func.sum(BowlingStats.overs), 0.0).label("overs"),
        )
        .join(Match, BowlingStats.match_id == Match.id)
        .where(BowlingStats.player_id == player_id, Match.match_type == format)
        .group_by(func.extract("year", Match.date))
        .order_by(func.extract("year", Match.date))
    )).all()

    bat_by_year = {int(r.yr): r for r in bat_rows}
    bowl_by_year = {int(r.yr): r for r in bowl_rows}
    all_years = sorted(set(bat_by_year) | set(bowl_by_year))

    entries: list[TimelineEntry] = []
    for yr in all_years:
        b = bat_by_year.get(yr)
        bw = bowl_by_year.get(yr)
        matches = max(int(b.matches) if b else 0, int(bw.matches) if bw else 0)

        runs: int | None = None
        batting_average: float | None = None
        batting_strike_rate: float | None = None
        if b and int(b.innings) > 0:
            runs = int(b.runs)
            not_outs = int(b.not_outs)
            dismissals = int(b.innings) - not_outs
            batting_average = round(runs / dismissals, 2) if dismissals > 0 else None
            balls_faced = int(b.balls_faced)
            batting_strike_rate = (
                round((runs / balls_faced) * 100, 2) if balls_faced > 0 else None
            )

        wickets: int | None = None
        bowling_economy: float | None = None
        bowling_average: float | None = None
        if bw:
            wkts = int(bw.wickets)
            overs = float(bw.overs)
            runs_c = int(bw.runs_conceded)
            if wkts > 0 or overs > 0:
                wickets = wkts
                bowling_economy = round(runs_c / overs, 2) if overs > 0 else None
                bowling_average = round(runs_c / wkts, 2) if wkts > 0 else None

        entries.append(TimelineEntry(
            year=yr,
            matches=matches,
            runs=runs,
            batting_average=batting_average,
            batting_strike_rate=batting_strike_rate,
            wickets=wickets,
            bowling_economy=bowling_economy,
            bowling_average=bowling_average,
        ))

    return TimelineResponse(profile=profile, format=format, years=entries)


# ====================================================================
# Head-to-head and venue
# ====================================================================

@router.get(
    "/head-to-head",
    response_model=HeadToHeadResponse,
    summary="Win/loss/no-result breakdown between two teams in a format.",
)
async def head_to_head(
    team1: str = Query(..., min_length=1),
    team2: str = Query(..., min_length=1),
    format: MatchType = Query(...),
    session: AsyncSession = Depends(get_db),
) -> HeadToHeadResponse:
    if team1 == team2:
        raise HTTPException(
            status_code=422, detail="team1 and team2 must differ."
        )

    # Match selector: matches that involve BOTH teams (in either slot).
    match_filter = and_(
        Match.match_type == format,
        or_(
            and_(Match.team1 == team1, Match.team2 == team2),
            and_(Match.team1 == team2, Match.team2 == team1),
        ),
    )
    rows = (await session.execute(select(Match).where(match_filter))).scalars().all()
    total = len(rows)
    team1_wins = sum(1 for m in rows if m.winner == team1)
    team2_wins = sum(1 for m in rows if m.winner == team2)
    no_results = sum(1 for m in rows if m.winner is None)

    bat_first_wins = 0
    bowl_first_wins = 0
    bat_first_total = 0
    for m in rows:
        if m.toss_winner is None or m.toss_decision is None or m.winner is None:
            continue
        team_batting_first = (
            m.toss_winner if m.toss_decision is TossDecision.BAT
            else (m.team2 if m.toss_winner == m.team1 else m.team1)
        )
        bat_first_total += 1
        if m.winner == team_batting_first:
            bat_first_wins += 1
        else:
            bowl_first_wins += 1

    bat_first_pct = (
        round((bat_first_wins / bat_first_total) * 100, 2)
        if bat_first_total > 0 else None
    )
    bowl_first_pct = (
        round((bowl_first_wins / bat_first_total) * 100, 2)
        if bat_first_total > 0 else None
    )

    # Average first-innings score: aggregate batting_stats where
    # innings_number=1 and the match is in the filter set.
    avg_first_innings = await session.scalar(
        select(func.avg(BattingStats.runs))
        .join(Match, BattingStats.match_id == Match.id)
        .where(match_filter, BattingStats.innings_number == 1)
    )

    return HeadToHeadResponse(
        team1=team1,
        team2=team2,
        format=format,
        total_matches=total,
        team1_wins=team1_wins,
        team2_wins=team2_wins,
        no_results=no_results,
        average_first_innings_score=(
            round(float(avg_first_innings), 2) if avg_first_innings is not None else None
        ),
        bat_first_win_pct=bat_first_pct,
        bowl_first_win_pct=bowl_first_pct,
    )


@router.get(
    "/venue",
    response_model=VenueStatsResponse,
    summary="Performance at a specific ground.",
)
async def venue_stats(
    ground: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db),
) -> VenueStatsResponse:
    rows = (
        await session.execute(select(Match).where(Match.ground == ground))
    ).scalars().all()
    matches = len(rows)

    avg_first_innings = await session.scalar(
        select(func.avg(BattingStats.runs))
        .join(Match, BattingStats.match_id == Match.id)
        .where(Match.ground == ground, BattingStats.innings_number == 1)
    )

    bat_first_wins = 0
    bowl_first_wins = 0
    decided = 0
    for m in rows:
        if m.toss_winner is None or m.toss_decision is None or m.winner is None:
            continue
        team_batting_first = (
            m.toss_winner if m.toss_decision is TossDecision.BAT
            else (m.team2 if m.toss_winner == m.team1 else m.team1)
        )
        decided += 1
        if m.winner == team_batting_first:
            bat_first_wins += 1
        else:
            bowl_first_wins += 1

    bat_first_pct = round((bat_first_wins / decided) * 100, 2) if decided else None
    bowl_first_pct = round((bowl_first_wins / decided) * 100, 2) if decided else None

    return VenueStatsResponse(
        ground=ground,
        matches=matches,
        average_first_innings_score=(
            round(float(avg_first_innings), 2) if avg_first_innings is not None else None
        ),
        bat_first_win_pct=bat_first_pct,
        bowl_first_win_pct=bowl_first_pct,
    )
