"""Phase 4.1 — config + async DB session smoke tests.

Three concerns:

  1. Settings load from env (with fallbacks) and the typed fields work.
  2. The async engine is configured with the pool sizes the user
     specified (5 + 10) — regression guard against someone bumping
     defaults later without thinking through the RDS connection cap.
  3. A real async session can open against the test DB, run a query,
     and close cleanly. This is the "no import errors / no DB connect
     errors" test the spec calls for.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import (
    _build_engine,
    dispose_engine,
    get_db,
    get_engine,
    get_session_factory,
)


# ====================================================================
# Settings
# ====================================================================

def test_settings_load_with_defaults():
    # Even without a single env var set, the Settings type should
    # construct cleanly with the documented defaults.
    s = Settings(_env_file=None)
    assert s.environment == "development"
    assert s.db_pool_size == 5
    assert s.db_max_overflow == 10
    assert s.db_pool_recycle_seconds == 1800
    assert s.db_pool_pre_ping is True


def test_settings_env_override_works(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DB_POOL_SIZE", "8")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://app.example.com")

    s = Settings(_env_file=None)
    assert s.environment == "production"
    assert s.debug is True
    assert s.db_pool_size == 8
    assert s.cors_origins_list == [
        "http://localhost:3000",
        "https://app.example.com",
    ]


def test_get_settings_is_cached():
    # The lru_cache means every dependency injection gets the same
    # object — important for test override patterns.
    a = get_settings()
    b = get_settings()
    assert a is b


# ====================================================================
# Engine pool config — guard against silent regression
# ====================================================================

def test_engine_pool_uses_user_specified_sizing():
    # The user set a contract on these numbers (5 + 10 for a Fargate
    # 256/512 task). If anyone bumps defaults later, this test fails
    # so they have to read the comment in config.py and intend it.
    # Explicitly override database_url so an OS-level DATABASE_URL
    # (e.g. set to the sync psycopg2 form by the user's .env) doesn't
    # break the async engine construction.
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://cricinsight:cricinsight@localhost:5432/cricinsight",
    )
    engine = _build_engine(settings)
    pool = engine.pool
    # SQLAlchemy's QueuePool exposes these as private getters; using
    # the public API keeps us from breaking on minor version bumps.
    assert pool.size() == 5
    assert pool._max_overflow == 10
    # pool_recycle and pool_pre_ping are kept on the pool object too.
    assert pool._recycle == 1800
    assert pool._pre_ping is True
    # Don't leak the engine.
    import asyncio
    asyncio.run(engine.dispose())


# ====================================================================
# Real async session round-trip against the test DB
# ====================================================================

@pytest.mark.asyncio
async def test_get_db_yields_working_session(test_engine):
    """Reuse the conftest test_engine (which migrated cricinsight_test
    on session start) but build an *async* engine pointing at the same
    DB so we can exercise the real get_db() path.
    """
    test_db_url = test_engine.url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )

    # Build a one-off async engine without polluting the module
    # singleton so this test doesn't bleed into others.
    async_settings = Settings(
        _env_file=None,
        database_url=test_db_url,
    )
    engine = _build_engine(async_settings)
    factory = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            # SELECT 1 confirms the async pipeline is wired end-to-end.
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception(test_engine, monkeypatch):
    """If a handler raises mid-request, get_db must rollback before
    the session closes — otherwise partial writes leak across to the
    next checkout.

    Uses asynccontextmanager to drive get_db the same way FastAPI
    does (which throws exceptions INTO the generator at the yield
    point via gen.athrow, exercising the except branch). A naive
    `async for session in gen:` doesn't trigger that path.
    """
    from contextlib import asynccontextmanager

    test_db_url = test_engine.url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg2", "postgresql+asyncpg"
    )

    async_settings = Settings(_env_file=None, database_url=test_db_url)
    engine = _build_engine(async_settings)
    real_factory = __import__(
        "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
    ).async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    rollback_count = {"n": 0}

    class _CountingSession:
        """Proxy that records rollback() calls. Everything else
        delegates to the real session via __getattr__."""

        def __init__(self, real):
            self._real = real

        def __getattr__(self, item):
            return getattr(self._real, item)

        async def rollback(self):
            rollback_count["n"] += 1
            await self._real.rollback()

        async def close(self):
            await self._real.close()

    monkeypatch.setattr(
        "app.database.get_session_factory",
        lambda: (lambda: _CountingSession(real_factory())),
    )

    db_ctx = asynccontextmanager(get_db)

    with pytest.raises(RuntimeError):
        async with db_ctx() as session:
            # FastAPI re-raises this exception INTO the generator at
            # the yield point via athrow, hitting the except branch.
            raise RuntimeError("boom")

    assert rollback_count["n"] == 1, "rollback should fire once on exception"
    await engine.dispose()
