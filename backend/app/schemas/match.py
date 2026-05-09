"""HTTP schemas for the matches domain."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MatchType, TossDecision


class MatchBase(BaseModel):
    match_type: MatchType
    venue: str | None = None
    ground: str | None = None
    date: datetime
    team1: str = Field(min_length=1, max_length=64)
    team2: str = Field(min_length=1, max_length=64)


class MatchCreate(MatchBase):
    external_id: str = Field(min_length=1, max_length=64)


class MatchResponse(MatchBase):
    id: int
    external_id: str
    winner: str | None = None
    toss_winner: str | None = None
    toss_decision: TossDecision | None = None
    result_margin: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
