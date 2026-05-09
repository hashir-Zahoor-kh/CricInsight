"""Centralised settings for the FastAPI app.

Wraps pydantic-settings BaseSettings so every config knob is:

  * Type-checked (so DEBUG=true and DEBUG="true" both yield bool(True)).
  * Documented in one place — readers don't have to grep for env-var
    names scattered across modules.
  * Loaded from `.env` automatically (backend/.env first, then the
    repo-root .env as a fallback — same precedence used everywhere
    else in the project).

Cached via `@lru_cache` so every `get_settings()` call across the app
returns the same instance — important so the FastAPI dependency
overhead is one dict lookup rather than re-parsing the environment on
every request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_file_path() -> tuple[str, ...]:
    """Pick the first existing .env in our search order."""
    for candidate in (BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"):
        if candidate.exists():
            return (str(candidate),)
    return ()


class Settings(BaseSettings):
    # --- App ---
    environment: str = Field(
        default="development",
        description="dev | staging | production — surfaced on /health.",
    )
    debug: bool = Field(
        default=False,
        description="Enables verbose logging + sqlalchemy echo when True.",
    )
    log_level: str = Field(
        default="INFO",
        description="Root logger level. Override to DEBUG for SQL traces.",
    )

    # --- Database ---
    # async URL for the FastAPI runtime (asyncpg driver)
    database_url: str = Field(
        default="postgresql+asyncpg://cricinsight:cricinsight@localhost:5432/cricinsight",
        description="async DSN used by the FastAPI app.",
    )
    # sync URL for Alembic / one-shot scripts (psycopg2 driver)
    database_url_sync: str = Field(
        default="postgresql+psycopg2://cricinsight:cricinsight@localhost:5432/cricinsight",
        description="sync DSN used by Alembic and the seed CLI.",
    )

    # --- DB pool — sized for a Fargate 256 CPU / 512 MB container.
    # Five steady connections per task plus ten burst slots covers a
    # typical dashboard request mix without exhausting the RDS
    # max_connections cap (the t3.micro default is 87, so 1 task =
    # 15 max, headroom for 5+ tasks before contention).
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)
    # Recycle connections older than 30 min — RDS quietly closes idle
    # connections at ~60 min, so 30 keeps us safely under that.
    db_pool_recycle_seconds: int = Field(default=1800)
    # Dispose-and-redial check before handing a connection out. Adds
    # ~1 round-trip on first request after a stall but prevents the
    # "stale connection" 500s that otherwise hit you after RDS
    # failover, container restart, or a long idle period.
    db_pool_pre_ping: bool = Field(default=True)

    # --- CricAPI (still consumed by the seed CLI; not by FastAPI) ---
    cricapi_key: str = Field(default="")
    cricapi_base_url: str = Field(default="https://api.cricapi.com/v1")

    # --- AWS ---
    aws_region: str = Field(default="us-east-1")

    # --- CORS — comma-separated origins ---
    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of origins allowed to call the API.",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        # Don't be strict about extra env vars — Docker, AWS, CI all
        # inject things we don't care about (PATH, PWD, AWS_*).
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor used as a FastAPI dependency.

    `lru_cache` makes repeated calls cheap; tests that need to
    override values can monkey-patch `get_settings.__wrapped__()` or
    call `get_settings.cache_clear()` to force a re-read.
    """
    return Settings()
