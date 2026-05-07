"""ORM model registry.

Re-exports every model so consumers (Alembic env.py, tests, services) can
just `from app.models import Player, Match, ...` without needing to know
the per-file layout. Importing this module also forces every mapper to
register on the shared metadata, which is what `alembic --autogenerate`
relies on.
"""

from .base import Base
from .batting_stats import BattingStats
from .bowling_stats import BowlingStats
from .enums import MatchType, PlayerRole, TossDecision
from .match import Match
from .player import Player

__all__ = [
    "Base",
    "BattingStats",
    "BowlingStats",
    "Match",
    "MatchType",
    "Player",
    "PlayerRole",
    "TossDecision",
]
