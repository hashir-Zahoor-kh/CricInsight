"""HTTP schemas (Pydantic) — re-exports for clean callsites.

Routers and tests can `from app.schemas import ComparisonResponse`
without needing to know which submodule the type lives in.
"""

from .analytics import (
    BattingCareerStats,
    BowlerPhaseStats,
    BowlerPhasesResponse,
    BowlingCareerStats,
    CommonOpponentBlock,
    ComparisonResponse,
    FormatBreakdown,
    FormGuideEntry,
    FormGuideResponse,
    HeadToHeadResponse,
    PlayerAverageResponse,
    PlayerComparisonSlot,
    PlayerProfileCard,
    VenueStatsResponse,
)
from .match import MatchBase, MatchCreate, MatchResponse
from .player import PlayerBase, PlayerCreate, PlayerResponse, PlayerWithStats
from .stats import BattingStatsResponse, BowlingStatsResponse

__all__ = [
    # player
    "PlayerBase",
    "PlayerCreate",
    "PlayerResponse",
    "PlayerWithStats",
    # match
    "MatchBase",
    "MatchCreate",
    "MatchResponse",
    # stats (per-row)
    "BattingStatsResponse",
    "BowlingStatsResponse",
    # analytics — career rollups
    "BattingCareerStats",
    "BowlingCareerStats",
    # analytics — shared building blocks
    "PlayerProfileCard",
    "FormGuideEntry",
    "CommonOpponentBlock",
    # analytics — single-player endpoints
    "PlayerAverageResponse",
    "FormatBreakdown",
    "FormGuideResponse",
    "HeadToHeadResponse",
    "VenueStatsResponse",
    "BowlerPhaseStats",
    "BowlerPhasesResponse",
    # analytics — flagship comparison endpoint
    "PlayerComparisonSlot",
    "ComparisonResponse",
]
