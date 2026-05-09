"""Match endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Match
from app.models.enums import MatchType
from app.schemas import MatchResponse

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=list[MatchResponse])
async def list_matches(
    format: MatchType | None = Query(default=None),
    team: str | None = Query(default=None, description="Returns matches involving this team."),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[MatchResponse]:
    stmt = select(Match).order_by(Match.date.desc())
    if format is not None:
        stmt = stmt.where(Match.match_type == format)
    if team:
        stmt = stmt.where((Match.team1 == team) | (Match.team2 == team))
    if date_from is not None:
        stmt = stmt.where(Match.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Match.date <= date_to)

    rows = (
        (await session.execute(stmt.limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return [MatchResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/recent", response_model=list[MatchResponse])
async def recent_matches(
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[MatchResponse]:
    stmt = select(Match).order_by(Match.date.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [MatchResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{match_id}", response_model=MatchResponse)
async def get_one_match(
    match_id: int,
    session: AsyncSession = Depends(get_db),
) -> MatchResponse:
    match = await session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match not found: id={match_id}")
    return MatchResponse.model_validate(match, from_attributes=True)
