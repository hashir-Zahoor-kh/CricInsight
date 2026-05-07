"""Enums shared across ORM models.

Kept in a separate module so Pydantic schemas (Phase 4.2) can import them
without pulling in SQLAlchemy.
"""

from enum import Enum


class MatchType(str, Enum):
    """Cricket match formats CricInsight tracks.

    Inheriting from `str` makes JSON serialisation trivial (FastAPI emits the
    member value directly) and lets the values flow through SQLAlchemy's
    Enum type without explicit casting.
    """

    TEST = "Test"
    ODI = "ODI"
    T20I = "T20I"
    T20 = "T20"


class PlayerRole(str, Enum):
    BATSMAN = "batsman"
    BOWLER = "bowler"
    ALL_ROUNDER = "allrounder"
    WICKETKEEPER = "wicketkeeper"


class TossDecision(str, Enum):
    BAT = "bat"
    BOWL = "bowl"
