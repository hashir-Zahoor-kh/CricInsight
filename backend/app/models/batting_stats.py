"""BattingStats ORM model — one row per (player, match, innings)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .match import Match
    from .player import Player


class BattingStats(Base):
    __tablename__ = "batting_stats"

    id: Mapped[int] = mapped_column(primary_key=True)

    # `ondelete="CASCADE"` mirrors the ORM-side cascade on Player/Match —
    # if either parent is deleted, the stats row goes too. `index=True` on
    # FKs is essential: nearly every analytics query joins through them.
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # `balls_faced` is nullable: CricAPI sometimes reports runs without
    # balls (especially for older Tests). Treating null and 0 as different
    # matters — strike rate is undefined for 0 balls, not zero.
    balls_faced: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sixes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stored even though it's derivable. Reasons: (1) historical reports
    # sometimes round differently, and (2) avoids a CASE expression in
    # every analytics query.
    strike_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Free-form: "bowled", "caught", "lbw", "not out", etc.
    dismissal_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- relationships ---
    player: Mapped["Player"] = relationship(back_populates="batting_stats")
    match: Mapped["Match"] = relationship(back_populates="batting_stats")

    __table_args__ = (
        # A player can only have one batting card per innings of a match.
        # This is also the natural upsert key for the loader.
        UniqueConstraint(
            "match_id",
            "player_id",
            "innings_number",
            name="uq_batting_stats_match_player_innings",
        ),
        CheckConstraint("runs >= 0", name="runs_non_negative"),
        CheckConstraint(
            "balls_faced IS NULL OR balls_faced >= 0",
            name="balls_faced_non_negative",
        ),
        CheckConstraint("innings_number > 0", name="innings_number_positive"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BattingStats player_id={self.player_id} "
            f"match_id={self.match_id} runs={self.runs}>"
        )
