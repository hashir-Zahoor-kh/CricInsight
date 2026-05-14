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

from pydantic import Field, field_validator
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
    port: int = Field(
        default=8000,
        description="Port uvicorn binds on. Overridden by $PORT at runtime (Railway/ECS).",
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

    # Optional AWS integrations — all None by default so the app runs
    # cleanly without any AWS credentials in local dev.
    aws_cloudwatch_log_group: str | None = Field(
        default=None,
        description="CloudWatch log group name. When set, watchtower ships logs to AWS.",
    )
    aws_secret_arn: str | None = Field(
        default=None,
        description="Secrets Manager ARN for DB credentials (ECS task role pattern).",
    )
    cricsheet_s3_bucket: str | None = Field(
        default=None,
        description="S3 bucket holding Cricsheet archives for ECS-based seed runs.",
    )

    # --- CORS ---
    # ALLOWED_ORIGINS is the canonical field (Railway / Vercel deploy sets it
    # to the Vercel preview URL). The old cors_origins field is preserved so
    # existing .env files keep working — both feed the same middleware.
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins. Set as a comma-separated string in the env.",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]

    # Legacy field kept for backwards-compat with existing .env files that
    # set CORS_ORIGINS. If both are set, ALLOWED_ORIGINS wins (it's listed
    # first in the middleware call).
    cors_origins: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173"
        ),
        description="Comma-separated CORS origins (legacy — prefer ALLOWED_ORIGINS).",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ---- defensive URL rewriting ----
    # Users sometimes drop a single `postgresql://...` URL in .env
    # without picking the right driver. The FastAPI runtime needs
    # asyncpg and Alembic needs psycopg2; auto-rewriting both fields
    # to the right driver keeps things from blowing up at first
    # request when someone forgets to differentiate.

    @field_validator("database_url", mode="before")
    @classmethod
    def _force_async_driver(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql+asyncpg://"):
            return v
        if v.startswith("postgresql+psycopg2://"):
            return v.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("database_url_sync", mode="before")
    @classmethod
    def _force_sync_driver(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql+psycopg2://"):
            return v
        if v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

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
