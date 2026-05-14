"""HTTP response schemas for analytics endpoints, including the
flagship `ComparisonResponse` for `GET /api/v1/analytics/compare`.

`ComparisonResponse` was designed first because it sets the contract
every other analytics response borrows from — `BattingCareerStats`,
`BowlingCareerStats`, and `FormGuideEntry` are reused on the
single-player /average and /form endpoints so the dashboard's chart
components stay format-stable across pages.

Role-aware contract: each `PlayerComparisonSlot` carries a
`primary_role` field that the dashboard uses to decide which panel to
render first (batting up top for batters, bowling up top for bowlers,
both for all-rounders). The frontend does not have to guess from
stats — the backend computes this in the service layer based on the
player's declared role and falls back to "more batting innings than
bowling innings" heuristic only when the declared role is None.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MatchType, PlayerRole


# ====================================================================
# Profile card — lightweight, used everywhere a player is referenced
# ====================================================================

class PlayerProfileCard(BaseModel):
    """The minimum a UI needs to render a player chip / card."""

    id: int
    external_id: str | None = None
    name: str
    country: str | None = None
    role: PlayerRole | None = None
    # primary_role is ALWAYS populated, even when role is None — the
    # service layer derives it from stats heuristically. The dashboard
    # uses it to choose the leading panel without inspecting stats.
    primary_role: PlayerRole
    batting_style: str | None = None
    bowling_style: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ====================================================================
# Career stat rollups — reused on /compare AND /player/{id}/average
# ====================================================================

class BattingCareerStats(BaseModel):
    """Batting career rollup, scoped to a format.

    `average` is runs / (innings - not_outs) — undefined when the
    player has never been out (returns None, not "infinity"). Same
    convention everywhere null appears in this module: null means
    "undefined / cannot be computed", never "zero".
    """

    matches: int = Field(ge=0)
    innings: int = Field(ge=0)
    not_outs: int = Field(ge=0)
    runs: int = Field(ge=0)
    average: float | None = Field(default=None, ge=0)
    strike_rate: float | None = Field(default=None, ge=0)
    fifties: int = Field(ge=0)
    hundreds: int = Field(ge=0)
    highest_score: int = Field(ge=0)
    fours: int = Field(ge=0)
    sixes: int = Field(ge=0)


class BowlingCareerStats(BaseModel):
    matches: int = Field(ge=0)
    innings: int = Field(ge=0)
    overs_bowled: float = Field(ge=0)
    runs_conceded: int = Field(ge=0)
    wickets: int = Field(ge=0)
    average: float | None = Field(default=None, ge=0)  # runs / wickets
    economy: float | None = Field(default=None, ge=0)
    # Bowling strike rate: balls bowled / wickets — different concept
    # from batting SR; sharing the field name would be misleading.
    bowling_strike_rate: float | None = Field(default=None, ge=0)
    # Wickets per match — derived rather than raw, so the dashboard's
    # bowling radar can use a "high is better" axis without needing
    # to divide on the client. Null when matches == 0.
    wickets_per_match: float | None = Field(default=None, ge=0)
    # Dot-ball percentage — not derivable from per-innings aggregates;
    # would need ball-by-ball storage. Reserved as null so the API
    # contract is stable when we move to ball-level data.
    dot_ball_pct: float | None = Field(default=None, ge=0, le=100)
    five_wicket_hauls: int = Field(ge=0)
    best_figures: str | None = None  # "5/28" — not parseable into a number


# ====================================================================
# Form guide — last N innings as sparkline source
# ====================================================================

class FormGuideEntry(BaseModel):
    """One innings of either batting or bowling.

    Both halves are nullable because some innings are pure batting
    (specialist batter not bowling) or pure bowling (bowler who didn't
    come out to bat). The dashboard's sparkline component reads
    whichever half matches the player's primary_role.
    """

    match_external_id: str
    date: datetime
    opponent: str
    venue: str | None = None
    match_type: MatchType

    # Batting half — populated when the player batted in this innings.
    batting_runs: int | None = Field(default=None, ge=0)
    batting_balls: int | None = Field(default=None, ge=0)
    batting_strike_rate: float | None = Field(default=None, ge=0)
    not_out: bool | None = None

    # Bowling half — populated when the player bowled in this innings.
    bowling_overs: float | None = Field(default=None, ge=0)
    bowling_wickets: int | None = Field(default=None, ge=0, le=10)
    bowling_runs_conceded: int | None = Field(default=None, ge=0)
    bowling_economy: float | None = Field(default=None, ge=0)


# ====================================================================
# Common opponents — used inside ComparisonResponse
# ====================================================================

class CommonOpponentBlock(BaseModel):
    """Per-opponent rollup that lets the dashboard render
    'Babar vs India: avg 52.7, SR 130' alongside Kohli's equivalent."""

    opponent: str
    player1_matches: int = Field(ge=0)
    player2_matches: int = Field(ge=0)

    # Batting view — populated for batter-style comparisons.
    player1_batting_average: float | None = Field(default=None, ge=0)
    player1_batting_strike_rate: float | None = Field(default=None, ge=0)
    player2_batting_average: float | None = Field(default=None, ge=0)
    player2_batting_strike_rate: float | None = Field(default=None, ge=0)

    # Bowling view — populated for bowler-style comparisons.
    player1_bowling_wickets: int | None = Field(default=None, ge=0)
    player1_bowling_economy: float | None = Field(default=None, ge=0)
    player2_bowling_wickets: int | None = Field(default=None, ge=0)
    player2_bowling_economy: float | None = Field(default=None, ge=0)


# ====================================================================
# Comparison slot — one half of the side-by-side
# ====================================================================

class PlayerComparisonSlot(BaseModel):
    profile: PlayerProfileCard
    # Batting present when the player has batting innings in this format.
    # All-rounders have both populated; pure bowlers have batting=None
    # if they've never batted (rare) or a thin BattingCareerStats with
    # tail-end numbers if they have.
    batting: BattingCareerStats | None = None
    bowling: BowlingCareerStats | None = None
    # Most recent innings first; capped at 10 by the service layer.
    form_guide: list[FormGuideEntry] = Field(default_factory=list, max_length=10)
    # Secondary role surfaces a non-trivial second skill so the
    # dashboard can label "primarily a bowler, also a batter" without
    # re-doing the analytics on the client. Null when the player has
    # only one skill in evidence. See _derive_roles in services for
    # the exact rules.
    secondary_role: PlayerRole | None = None


# ====================================================================
# The flagship comparison response
# ====================================================================

class DataQualityWarning(BaseModel):
    """One non-fatal warning about thin or missing data.

    The API returns 200 with a populated `data_quality` list rather
    than 404 / misleading averages-from-2-innings. Dashboard renders
    these as inline notices ("Insufficient data for Player X in T20I
    — only 3 innings available") next to the affected panel rather
    than failing the page.
    """

    code: str  # machine-readable: "insufficient_innings_player1_batting"
    message: str
    affected: str | None = None  # "player1" / "player2" / opponent name


class ComparisonResponse(BaseModel):
    """Side-by-side comparison of two players in a chosen format.

    Format is REQUIRED on the request side — comparing a Test player's
    average to a T20I player's strike rate would be meaningless, so
    the API refuses to do it.

    Below the minimum-innings threshold (5), the corresponding
    `batting` or `bowling` block on each slot is still returned (with
    raw counts) but a `data_quality` warning is appended so the
    dashboard can render an "insufficient data" notice instead of a
    chart computed from 2 innings.
    """

    format: MatchType
    player1: PlayerComparisonSlot
    player2: PlayerComparisonSlot
    common_opponents: list[CommonOpponentBlock] = Field(default_factory=list)
    data_quality: list[DataQualityWarning] = Field(default_factory=list)


# ====================================================================
# Single-player analytics responses (kept consistent with /compare)
# ====================================================================

class FormatBreakdown(BaseModel):
    """One row of the by-format breakdown on /player/{id}/average."""

    format: MatchType
    batting: BattingCareerStats | None = None
    bowling: BowlingCareerStats | None = None


class PlayerAverageResponse(BaseModel):
    profile: PlayerProfileCard
    by_format: list[FormatBreakdown]
    data_quality: list[DataQualityWarning] = Field(default_factory=list)


class FormGuideResponse(BaseModel):
    profile: PlayerProfileCard
    innings: list[FormGuideEntry] = Field(default_factory=list, max_length=10)
    data_quality: list[DataQualityWarning] = Field(default_factory=list)


# ====================================================================
# Head-to-head and venue — folded into ComparisonPage as panels
# rather than standalone pages, but still useful as standalone API
# endpoints for power users / future drill-downs.
# ====================================================================

class HeadToHeadResponse(BaseModel):
    team1: str
    team2: str
    format: MatchType
    total_matches: int = Field(ge=0)
    team1_wins: int = Field(ge=0)
    team2_wins: int = Field(ge=0)
    no_results: int = Field(ge=0)
    average_first_innings_score: float | None = Field(default=None, ge=0)
    bat_first_win_pct: float | None = Field(default=None, ge=0, le=100)
    bowl_first_win_pct: float | None = Field(default=None, ge=0, le=100)


class VenueStatsResponse(BaseModel):
    ground: str
    matches: int = Field(ge=0)
    average_first_innings_score: float | None = Field(default=None, ge=0)
    bat_first_win_pct: float | None = Field(default=None, ge=0, le=100)
    bowl_first_win_pct: float | None = Field(default=None, ge=0, le=100)


# ====================================================================
# Bowler phase analysis — power-play / middle / death
# ====================================================================

class BowlerPhaseStats(BaseModel):
    phase: Literal["powerplay", "middle", "death"]
    overs_bowled: float = Field(ge=0)
    wickets: int = Field(ge=0)
    economy: float | None = Field(default=None, ge=0)


class BowlerPhasesResponse(BaseModel):
    profile: PlayerProfileCard
    phases: list[BowlerPhaseStats]
