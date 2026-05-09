"""Async SQLAlchemy engine + session factory + FastAPI dependency.

Pool sizing (`pool_size=5, max_overflow=10`) is intentionally
conservative: aimed at a Fargate 256 CPU / 512 MB container. Five
steady connections handle the usual dashboard load; the overflow of
ten absorbs short bursts (e.g. a few users hitting the comparison
endpoint at once) without exceeding the RDS connection cap.

Two complementary stale-connection defences:

  * `pool_pre_ping=True` — issues `SELECT 1` on each checkout. Adds
    one round-trip on first use after idle but eliminates the
    ResourceClosedError class of failures that otherwise surface on
    RDS failovers / VPC NAT timeouts.

  * `pool_recycle=1800` — refresh every connection at most once per
    30 min. RDS quietly drops idle connections at ~60 min; recycling
    proactively means we never hand out one that's about to die.

`get_db()` is the FastAPI dependency. It yields one async session
per request and rolls back on exception so a handler raising mid-write
doesn't leak a partial-write transaction.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


def _build_engine(settings: Settings):
    """Construct the async engine using the settings object.

    Pulled into its own function so tests can build a throwaway
    engine pointed at the test database without poking module
    globals.
    """
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=settings.db_pool_pre_ping,
        echo=settings.debug,  # SQL traces only when DEBUG=true
        future=True,
    )


# Module-level engine + session factory. Built lazily on first use so
# importing this module under unit-test conditions doesn't immediately
# open a connection to whatever DATABASE_URL points to.
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings())
        logger.info(
            "async engine built — pool_size=%d max_overflow=%d "
            "recycle=%ds pre_ping=%s",
            get_settings().db_pool_size,
            get_settings().db_max_overflow,
            get_settings().db_pool_recycle_seconds,
            get_settings().db_pool_pre_ping,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            # Stop SQLAlchemy from expiring loaded attributes after
            # commit — we frequently want to serialise a row to the
            # response right after writing it, and re-fetching every
            # column is just wasted round-trips.
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session, ensure rollback on failure."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        # Don't auto-commit — handlers commit explicitly when they want
        # writes to persist. Read-only handlers don't pay the commit cost.
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Close the engine's pool. Called from FastAPI's shutdown event."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
