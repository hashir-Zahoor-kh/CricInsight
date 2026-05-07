"""Shared declarative base for all ORM models.

Centralising the Base in one module is what lets Alembic's autogenerate
discover every table — `target_metadata = Base.metadata` in env.py picks up
anything imported under app.models.

A naming convention is set on the metadata so Alembic emits stable, readable
constraint names (`pk_players`, `fk_batting_stats_player_id_players`) instead
of database-generated ones that drift between Postgres versions.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Adds created_at/updated_at managed by the database itself.

    Using `server_default=func.now()` keeps timestamps consistent regardless
    of which client (FastAPI, Alembic seed scripts, manual psql) inserts a
    row. `onupdate` fires on every UPDATE so updated_at always reflects the
    last write.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
