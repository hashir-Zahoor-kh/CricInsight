"""Alembic environment.

Two adjustments from the generated stub:

1. The DB URL is read from the DATABASE_URL_SYNC env var (with a
   docker-compose-friendly fallback) instead of being baked into
   alembic.ini, so the same migration tree drives local Postgres and
   RDS without edits.

2. `target_metadata` is wired to our SQLAlchemy declarative Base so
   `alembic revision --autogenerate` actually picks up Player, Match,
   BattingStats, BowlingStats automatically.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend root is on sys.path so `from app.models import Base`
# works when alembic is invoked from any directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Base  # noqa: E402 — sys.path tweak required first

# Optionally load .env so `alembic upgrade head` works without exporting
# DATABASE_URL_SYNC by hand. Silently no-ops if python-dotenv is absent.
try:
    from dotenv import load_dotenv

    # backend/.env first (where the user keeps it), repo-root .env fallback.
    for _candidate in (BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ModuleNotFoundError:  # pragma: no cover
    pass

config = context.config

# Default points at the docker-compose db service mapped to localhost.
# Override at runtime by exporting DATABASE_URL_SYNC (CI, RDS, etc.).
DEFAULT_SYNC_URL = (
    "postgresql+psycopg2://cricinsight:cricinsight@localhost:5432/cricinsight"
)
db_url = os.getenv("DATABASE_URL_SYNC", DEFAULT_SYNC_URL)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is what `--autogenerate` diffs against the live DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout — used for `alembic upgrade --sql head` reviews."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare server_default values too so timestamps don't show as
        # spurious diffs on every autogen run.
        compare_server_default=True,
        # Detect type changes (Enum widenings, length bumps).
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Open a real connection and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_server_default=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
