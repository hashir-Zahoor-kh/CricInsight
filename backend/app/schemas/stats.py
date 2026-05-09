"""HTTP schemas for the per-row stats responses.

These are 1-to-1 with rows in batting_stats / bowling_stats and used
by the (less common) endpoints that expose individual scorecard rows.
The richer career-rollup types live in `analytics.py` since they're
the dashboard's bread and butter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BattingStatsResponse(BaseModel):
    id: int
    player_id: int
    match_id: int
    runs: int = Field(ge=0)
    balls_faced: int | None = Field(default=None, ge=0)
    fours: int = Field(ge=0)
    sixes: int = Field(ge=0)
    strike_rate: float | None = Field(default=None, ge=0)
    dismissal_type: str | None = None
    innings_number: int = Field(ge=1)
    position: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(from_attributes=True)


class BowlingStatsResponse(BaseModel):
    id: int
    player_id: int
    match_id: int
    overs: float = Field(ge=0)
    maidens: int = Field(ge=0)
    runs_conceded: int = Field(ge=0)
    wickets: int = Field(ge=0, le=10)
    economy_rate: float | None = Field(default=None, ge=0)
    extras: int | None = Field(default=None, ge=0)
    innings_number: int = Field(ge=1)

    model_config = ConfigDict(from_attributes=True)
