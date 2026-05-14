"""FastAPI application entry point.

Glue code only — every substantive line of business logic lives in
`app.routers` and `app.services`. This module's job is exactly four
things:

  1. Build the FastAPI app.
  2. Lifespan: ping the DB on startup, dispose the pool on shutdown.
  3. CORS: allow the React dashboard's dev origin (both localhost
     and 127.0.0.1 variants — CRA resolves to either depending on
     launch flags, and we want neither to error).
  4. /health endpoint that ACTUALLY tests the database with a
     SELECT 1 instead of trivially returning ok. The ECS task
     health check (Phase 6) reads this; a stub that always says
     "ok" would let a broken backend stay in service.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import get_settings
from .database import dispose_engine, get_session_factory
from .routers import analytics, live, matches, players

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- lifespan

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Replaces the deprecated @app.on_event handlers.

    Startup: ping the DB so a misconfigured DATABASE_URL fails fast
    at boot rather than at first request. We don't want a container
    to start, register healthy with the load balancer, and only then
    discover it can't reach Postgres.

    Shutdown: dispose the engine pool so in-flight connections get
    closed cleanly. ECS sends SIGTERM with a 30s grace window; this
    helps avoid leaking sockets to RDS during rolling deploys.
    """
    settings = get_settings()
    logger.info(
        "starting CricInsight API in environment=%s debug=%s",
        settings.environment, settings.debug,
    )
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("database reachable on startup")
    except Exception as exc:
        # Log but don't crash — we want the container to start so
        # /health can report "degraded" and a human can see it. The
        # alternative (crashlooping) hides the real diagnostic.
        logger.error("database unreachable on startup: %s", exc)

    try:
        yield
    finally:
        await dispose_engine()
        logger.info("CricInsight API shut down cleanly")


# ---------------------------------------------------------------- app

def _build_app() -> FastAPI:
    """Factory pattern so tests can construct fresh app instances
    without polluting module globals (and override dependencies
    independently per test)."""
    settings = get_settings()

    app = FastAPI(
        title="CricInsight API",
        description=(
            "Backend for the CricInsight cricket analytics dashboard. "
            "Flagship endpoint is /api/v1/analytics/compare — side-by-side "
            "player comparison in a chosen format."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        # Keep methods/headers wide-open for now — the dashboard only
        # GETs anyway, but later admin endpoints may POST.
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All API routers live under /api/v1 so the dashboard can hit a
    # stable prefix and we can version forward later without breakage.
    api_prefix = "/api/v1"
    app.include_router(analytics.router, prefix=api_prefix)
    app.include_router(players.router, prefix=api_prefix)
    app.include_router(matches.router, prefix=api_prefix)
    app.include_router(live.router, prefix=api_prefix)

    @app.get("/health", tags=["meta"], summary="Health check (DB-aware).")
    async def health() -> dict[str, str]:
        """ECS / load balancer health probe.

        Always returns 200 (so the LB knows the process is alive),
        but the body's `db` field reports the DB status:

          ok          → DB reachable, ready to serve traffic
          degraded    → DB unreachable, container should be replaced

        The 200 is deliberate: returning 503 would have ECS replace
        the task immediately, which can mask a transient RDS hiccup
        and turn a 30-second blip into a rolling-restart storm.
        Surfacing the status in the body lets monitoring decide.
        """
        try:
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok", "db": "connected"}
        except Exception as exc:
            logger.warning("/health DB ping failed: %s", exc)
            return {"status": "degraded", "db": "unreachable"}

    @app.get("/", tags=["meta"], summary="Root — points at /docs.")
    async def root() -> dict[str, str]:
        return {
            "service": "cricinsight",
            "docs": "/docs",
            "health": "/health",
            "api": "/api/v1",
        }

    return app


app = _build_app()
