"""pytest config + DB fixtures for tests that need a real Postgres.

Two responsibilities:

1. sys.path tweak so `from app.models import Player` works regardless
   of pytest's working directory.

2. Test database lifecycle. Tests that touch the DB request the
   `db_session` fixture, which:

      * On first use in the session: drops + creates `cricinsight_test`
        and runs `alembic upgrade head` against it. Using migrations
        (not Base.metadata.create_all) means the test schema matches
        the production migration path exactly — any drift between the
        ORM models and the migrations surfaces here, not in prod.

      * For each test: TRUNCATEs all tables before yielding so tests
        are isolated, then closes the session afterwards.

The test DB is dropped at session teardown so a CI run leaves no
stragglers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Load .env so DATABASE_URL_SYNC etc. are available without exporting
# manually. Same precedence used everywhere: backend/.env first,
# repo-root .env as fallback.
try:
    from dotenv import load_dotenv

    for _candidate in (BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ModuleNotFoundError:  # pragma: no cover
    pass


# ------------------------------------------------------------ DB fixtures

# The dev DB Alembic migrated in Phase 2.3 — used as the "admin"
# connection from which we CREATE/DROP the test database. CONNECTING TO
# the dev DB is fine; we never write to it.
DEV_DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://cricinsight:cricinsight@localhost:5432/cricinsight",
)
TEST_DB_NAME = "cricinsight_test"
TEST_DB_URL = DEV_DB_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


def _is_postgres_reachable() -> bool:
    """Cheap probe so the loader tests can self-skip if Postgres isn't
    running. Avoids long connect-timeout failures in CI."""
    try:
        engine = create_engine(DEV_DB_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """Spin up `cricinsight_test`, migrate it, dispose it on teardown."""
    if not _is_postgres_reachable():
        pytest.skip(
            "Postgres unreachable at DATABASE_URL_SYNC — start the "
            "docker-compose db service before running loader tests."
        )

    # Use AUTOCOMMIT so CREATE/DROP DATABASE statements (which can't
    # run inside a transaction) work.
    admin_engine = create_engine(DEV_DB_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        # DROP IF EXISTS handles a leftover DB from a previous failed run.
        # Terminate any existing connections first or DROP DATABASE blocks.
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ),
            {"db": TEST_DB_NAME},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    # Run alembic migrations against the new DB. We override the URL via
    # env var because alembic/env.py reads DATABASE_URL_SYNC from there
    # (with a fallback to the dev URL).
    from alembic import command
    from alembic.config import Config

    original_url = os.environ.get("DATABASE_URL_SYNC")
    os.environ["DATABASE_URL_SYNC"] = TEST_DB_URL
    try:
        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
    finally:
        # Restore so the rest of the test session sees the dev URL
        # again (for code that reads os.environ later).
        if original_url is None:
            os.environ.pop("DATABASE_URL_SYNC", None)
        else:
            os.environ["DATABASE_URL_SYNC"] = original_url

    engine = create_engine(TEST_DB_URL, future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        # Tear down the test DB at session end so CI leaves no traces.
        admin_engine = create_engine(DEV_DB_URL, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": TEST_DB_NAME},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        admin_engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    """A clean Session: TRUNCATEs every table before each test."""
    SessionLocal = sessionmaker(
        bind=test_engine, expire_on_commit=False, future=True
    )
    session = SessionLocal()

    # Wipe in dependency order. RESTART IDENTITY resets the SERIAL
    # sequences so id values are predictable across tests; CASCADE
    # cleans up FK-bound rows in one statement.
    session.execute(
        text(
            "TRUNCATE TABLE batting_stats, bowling_stats, matches, players "
            "RESTART IDENTITY CASCADE"
        )
    )
    session.commit()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
