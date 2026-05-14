"""Schemas for the live scores feed."""

from __future__ import annotations

from pydantic import BaseModel


class LiveMatch(BaseModel):
    match_id: str
    name: str
    status: str
    match_type: str
    venue: str | None = None
    teams: list[str]
    # team_name → "180/6 (20 ov)" — only populated sides appear.
    scores: dict[str, str]
    is_live: bool = False


class LiveScoreResponse(BaseModel):
    live_available: bool
    matches: list[LiveMatch]
