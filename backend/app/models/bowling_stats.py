"""BowlingStats ORM model — one row per (player, match, innings)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .match import Match
    from .player import Player


class BowlingStats(Base):
    __tablename__ = "bowling_stats"

    id: Mapped[int] = mapped_column(primary_key=True)

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

    # Overs as float because cricket scoring uses fractional overs
    # (e.g. 4.3 = "four overs and three balls"). Stored as the raw float
    # rather than (overs_int, balls_int) — analytics queries find the float
    # more convenient and we can always derive the pair when needed.
    overs: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    maidens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_conceded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wickets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Materialised for the same reasons as batting strike_rate: avoids
    # divide-by-zero CASE in queries and preserves any source rounding.
    economy_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Wides + no-balls + byes credited to the bowler. Often missing from
    # CricAPI's free tier so kept nullable.
    extras: Mapped[int | None] = mapped_column(Integer, nullable=True)

    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- relationships ---
    player: Mapped["Player"] = relationship(back_populates="bowling_stats")
    match: Mapped["Match"] = relationship(back_populates="bowling_stats")

    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "player_id",
            "innings_number",
            name="uq_bowling_stats_match_player_innings",
        ),
        CheckConstraint("overs >= 0", name="overs_non_negative"),
        CheckConstraint("wickets >= 0 AND wickets <= 10", name="wickets_in_range"),
        CheckConstraint("runs_conceded >= 0", name="runs_conceded_non_negative"),
        CheckConstraint("innings_number > 0", name="innings_number_positive"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BowlingStats player_id={self.player_id} "
            f"match_id={self.match_id} {self.wickets}/{self.runs_conceded}>"
        )
