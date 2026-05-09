"""HTTP schemas for the players domain."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PlayerRole

from .analytics import BattingCareerStats, BowlingCareerStats


class PlayerBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    country: str | None = None
    role: PlayerRole | None = None
    batting_style: str | None = None
    bowling_style: str | None = None
    date_of_birth: date | None = None


class PlayerCreate(PlayerBase):
    """Used by the (future) admin endpoint that ingests a player by hand."""

    external_id: str | None = Field(default=None, max_length=64)


class PlayerResponse(PlayerBase):
    id: int
    external_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlayerWithStats(PlayerResponse):
    """The richer view returned by /players/{id}/stats. Reuses the
    same career rollup types as the comparison endpoint so dashboard
    components don't have to handle two slightly-different shapes."""

    primary_role: PlayerRole
    batting: BattingCareerStats | None = None
    bowling: BowlingCareerStats | None = None
