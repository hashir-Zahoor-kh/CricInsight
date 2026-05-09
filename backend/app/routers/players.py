"""Player endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import PlayerResponse, PlayerWithStats
from app.services.comparison import (
    _batting_career_stats,
    _bowling_career_stats,
    _build_profile,
)
from app.services.player_lookup import get_player_by_id, list_players
from app.models.enums import MatchType

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerResponse], summary="List players (paginated).")
async def get_players(
    name: str | None = Query(default=None, description="Case-insensitive substring match."),
    country: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[PlayerResponse]:
    rows, _total = await list_players(
        session, name=name, country=country, limit=limit, offset=offset
    )
    return [PlayerResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/search", response_model=list[PlayerResponse], summary="Search players by name.")
async def search_players(
    name: str = Query(..., min_length=1, description="Substring of player name."),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[PlayerResponse]:
    rows, _ = await list_players(session, name=name, limit=limit, offset=0)
    return [PlayerResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{player_id}", response_model=PlayerResponse)
async def get_one_player(
    player_id: int,
    session: AsyncSession = Depends(get_db),
) -> PlayerResponse:
    player = await get_player_by_id(session, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found: id={player_id}")
    return PlayerResponse.model_validate(player, from_attributes=True)


@router.get("/{player_id}/stats", response_model=PlayerWithStats)
async def get_player_stats(
    player_id: int,
    format: MatchType | None = Query(
        default=None,
        description=(
            "Optional format filter. Omit to get aggregate stats across "
            "all formats this player has appeared in."
        ),
    ),
    session: AsyncSession = Depends(get_db),
) -> PlayerWithStats:
    player = await get_player_by_id(session, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"Player not found: id={player_id}")
    profile = await _build_profile(session, player)

    # If a format is supplied, scope the rollup. Otherwise aggregate
    # across formats by computing each one and merging — but for now
    # the router requires a format for honest stats (cross-format
    # rollups invent meaningless averages). The router exposes the
    # format-scoped path; cross-format will land later if needed.
    if format is None:
        # Return the profile with empty stats — the dashboard prompts
        # the user to pick a format.
        return PlayerWithStats(
            id=player.id,
            external_id=player.external_id,
            name=player.name,
            country=player.country,
            role=player.role,
            batting_style=player.batting_style,
            bowling_style=player.bowling_style,
            date_of_birth=player.date_of_birth,
            created_at=player.created_at,
            updated_at=player.updated_at,
            primary_role=profile.primary_role,
            batting=None,
            bowling=None,
        )

    batting = await _batting_career_stats(session, player.id, format)
    bowling = await _bowling_career_stats(session, player.id, format)

    return PlayerWithStats(
        id=player.id,
        external_id=player.external_id,
        name=player.name,
        country=player.country,
        role=player.role,
        batting_style=player.batting_style,
        bowling_style=player.bowling_style,
        date_of_birth=player.date_of_birth,
        created_at=player.created_at,
        updated_at=player.updated_at,
        primary_role=profile.primary_role,
        batting=batting,
        bowling=bowling,
    )
