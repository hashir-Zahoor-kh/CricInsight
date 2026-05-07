"""Match ORM model.

Naming note: the spec lists fields as `id` (internal PK) and `match_id`
(external CricAPI id). To avoid the ambiguity of a column literally named
`match_id` on a `matches` table — every FK column in BattingStats/BowlingStats
is also called `match_id` and would shadow it — we keep `id` as the
internal PK and store CricAPI's identifier as `external_id` on this table
too, mirroring the Player model.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import MatchType, TossDecision

if TYPE_CHECKING:
    from .batting_stats import BattingStats
    from .bowling_stats import BowlingStats


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CricAPI's match id. Unique deduplication key — two ingestion runs over
    # the same match must collapse to a single row (Phase 3.3 idempotency).
    external_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    match_type: Mapped[MatchType] = mapped_column(nullable=False, index=True)

    # `venue` is the wider location ("Lahore"), `ground` is the specific
    # stadium ("Gaddafi Stadium"). CricAPI sometimes ships only one — both
    # are nullable so we never lose a match over missing metadata.
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ground: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    team1: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    team2: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # `winner` is nullable (no-result, abandoned, tied without super-over).
    winner: Mapped[str | None] = mapped_column(String(64), nullable=True)

    toss_winner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    toss_decision: Mapped[TossDecision | None] = mapped_column(nullable=True)

    # Free-form: "won by 5 wickets", "won by 28 runs", etc. Free-form because
    # CricAPI strings vary too much to parse reliably; the dashboard shows
    # them verbatim.
    result_margin: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- relationships ---
    batting_stats: Mapped[list["BattingStats"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    bowling_stats: Mapped[list["BowlingStats"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Composite index for the H2H endpoint
        # (`/analytics/head-to-head?team1=...&team2=...&format=...`).
        Index("ix_matches_teams_format", "team1", "team2", "match_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Match id={self.id} {self.team1} vs {self.team2} ({self.match_type})>"
