"""Player ORM model.

A Player is identified by an internal `id` for FK joins and an optional
external `external_id` (CricAPI's player UUID) used as the upsert
deduplication key in the ingestion loader.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import PlayerRole

if TYPE_CHECKING:
    # Forward-reference imports kept under TYPE_CHECKING so they don't
    # trigger circular imports at runtime — relationships use string-form
    # class names which SQLAlchemy resolves lazily.
    from .batting_stats import BattingStats
    from .bowling_stats import BowlingStats


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CricAPI's player UUID. Nullable because manually-seeded test fixtures
    # may not have one, but unique whenever set so upserts can collide.
    external_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Free-form descriptors — CricAPI returns short strings like "Right-hand
    # bat" or "Right-arm fast-medium". Cap length to keep indexes sane.
    batting_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bowling_style: Mapped[str | None] = mapped_column(String(64), nullable=True)

    role: Mapped[PlayerRole | None] = mapped_column(
        # Use the existing Python enum; let SQLAlchemy emit a Postgres ENUM.
        # `native_enum=True` is the default — explicit here as a reminder to
        # check `alembic --autogenerate` picks up enum changes (it doesn't,
        # always — they need manual review).
        nullable=True,
    )

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- relationships ---
    # `cascade="all, delete-orphan"` means deleting a player deletes their
    # stats rows. That matches the domain: stats with no player are useless.
    batting_stats: Mapped[list["BattingStats"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    bowling_stats: Mapped[list["BowlingStats"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Note: the BTREE on `name` comes from `index=True` on the column above;
    # that's enough for the dashboard's `GET /players/search?name=babar`
    # equality/prefix lookups. A trigram index for fuzzier search can come
    # later if needed.

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Player id={self.id} name={self.name!r} role={self.role}>"
