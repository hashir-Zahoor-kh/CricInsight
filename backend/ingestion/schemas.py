"""Pydantic schemas used by the ingestion layer.

These are deliberately separate from the FastAPI HTTP schemas in
`app.schemas` (Phase 4.2). The two layers solve different problems:

  * `app.schemas`   — request/response shapes the React dashboard sees.
  * `ingestion.schemas` — cleaned, validated rows ready for the loader.

Keeping them split means a CricAPI shape change only ripples through
the ingestion layer, not the API contract the frontend depends on.

The schemas mirror the SQLAlchemy models field-for-field but carry the
*external* identifiers (CricAPI UUIDs) instead of the internal DB ids,
because the loader hasn't run yet when these are constructed.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MatchType, PlayerRole, TossDecision


class _Base(BaseModel):
    # Stricter than Pydantic's default: any unknown keys in the input get
    # rejected. Helps catch new CricAPI fields we forgot to handle, rather
    # than silently dropping data.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NormalizedPlayer(_Base):
    external_id: str | None = None
    name: str
    country: str | None = None
    batting_style: str | None = None
    bowling_style: str | None = None
    role: PlayerRole | None = None
    date_of_birth: date | None = None


class NormalizedBattingStats(_Base):
    """A batting card scoped to (player, innings) within some match.

    The match link is implicit — these come back inside a
    NormalizedMatchResult, so the parent match supplies the match_id.
    Player linkage is by external_id when available, falling back to
    name (the loader resolves both).
    """

    player_external_id: str | None = None
    player_name: str

    runs: int = Field(ge=0)
    # Nullable because older CricAPI records sometimes omit balls faced
    # entirely. Treating null as "unknown" preserves that distinction
    # from "0 balls" (which would be a real 0-ball duck).
    balls_faced: int | None = Field(default=None, ge=0)
    fours: int = Field(default=0, ge=0)
    sixes: int = Field(default=0, ge=0)
    strike_rate: float | None = Field(default=None, ge=0)
    dismissal_type: str | None = None
    innings_number: int = Field(ge=1)
    position: int | None = Field(default=None, ge=1)


class NormalizedBowlingStats(_Base):
    player_external_id: str | None = None
    player_name: str

    overs: float = Field(ge=0)
    maidens: int = Field(default=0, ge=0)
    runs_conceded: int = Field(default=0, ge=0)
    wickets: int = Field(default=0, ge=0, le=10)
    economy_rate: float | None = Field(default=None, ge=0)
    extras: int | None = Field(default=None, ge=0)
    innings_number: int = Field(ge=1)


class NormalizedMatch(_Base):
    external_id: str
    match_type: MatchType
    venue: str | None = None
    ground: str | None = None
    date: datetime
    team1: str
    team2: str
    winner: str | None = None
    toss_winner: str | None = None
    toss_decision: TossDecision | None = None
    result_margin: str | None = None


class NormalizedMatchResult(_Base):
    """Everything the loader needs for one match: the match row plus
    every batting and bowling card across all innings."""

    match: NormalizedMatch
    batting: list[NormalizedBattingStats] = Field(default_factory=list)
    bowling: list[NormalizedBowlingStats] = Field(default_factory=list)
