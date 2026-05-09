"""Service layer — heavy SQL stays here, routers stay thin."""

from .comparison import (
    MIN_INNINGS_THRESHOLD,
    PlayerNotFound,
    build_comparison,
)

__all__ = [
    "MIN_INNINGS_THRESHOLD",
    "PlayerNotFound",
    "build_comparison",
]
