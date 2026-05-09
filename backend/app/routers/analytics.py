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
