"""Phase 4.4 — main.py app integration tests.

Three contract pieces:

  1. /health actually pings the DB with SELECT 1. Returns 200 in both
     the connected and the degraded case (so a transient blip doesn't
     trigger an ECS task-replace storm); the body's `db` field
     reports which.

  2. CORS works for BOTH localhost:3000 and 127.0.0.1:3000. The React
     dev server resolves to one or the other depending on how it was
     launched, and we don't want either to fail with a CORS error.

  3. All three routers are mounted under /api/v1 — quick smoke that
     a request to each one comes back with a real status code rather
     than 404.

Uses async_db_session for /health-connected; a separate test patches
the session factory to throw, exercising the degraded path.
"""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import _build_app


@pytest.fixture
def app(async_db_session: AsyncSession) -> FastAPI:
    """A real built app with get_db overridden to use the test session."""
    app = _build_app()

    async def _override_get_db():
        yield async_db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ====================================================================
# /health
# ====================================================================

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_connected(
        self, client: AsyncClient, async_test_engine_url: str
    ):
        # Real session factory points at the test DB, which is up and
        # migrated — should return ok / connected.
        from app.database import _build_engine
        from app.config import Settings
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

        # Inject a session factory pointed at the test DB so /health's
        # SELECT 1 actually has somewhere to land.
        engine = _build_engine(
            Settings(_env_file=None, database_url=async_test_engine_url)
        )
        factory = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )
        with patch("app.main.get_session_factory", return_value=factory):
            resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok", "db": "connected"}
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_health_degraded_when_db_unreachable(self, client: AsyncClient):
        # Patch the session factory to raise — simulates a downed DB.
        # Critically: still returns 200 (not 503) so a 30-second blip
        # doesn't trigger an ECS task-replace storm. Status comes in
        # the body so monitoring can decide.
        def broken_factory():
            raise ConnectionError("pretend RDS is down")

        with patch("app.main.get_session_factory", side_effect=broken_factory):
            resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "degraded", "db": "unreachable"}


# ====================================================================
# CORS — both localhost and 127.0.0.1
# ====================================================================

class TestCors:
    """Per the user contract: the React dev server resolves to either
    localhost:3000 or 127.0.0.1:3000 depending on launch flags. Both
    must be in the allow-list out of the box."""

    @pytest.mark.asyncio
    async def test_cors_localhost_allowed(self, client: AsyncClient):
        resp = await client.options(
            "/api/v1/players",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Preflight is a 200 with the allow-origin header echoed back.
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_cors_127_0_0_1_allowed(self, client: AsyncClient):
        resp = await client.options(
            "/api/v1/players",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"

    @pytest.mark.asyncio
    async def test_cors_random_origin_not_echoed(self, client: AsyncClient):
        # Origins outside the allow list don't get the allow-origin
        # header reflected — browser will block.
        resp = await client.options(
            "/api/v1/players",
            headers={
                "Origin": "http://malicious.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Preflight may still 200 but the allow-origin header must NOT
        # echo the bad origin back.
        assert resp.headers.get("access-control-allow-origin") != "http://malicious.example.com"


# ====================================================================
# Router mounting
# ====================================================================

class TestRouterMounting:

    @pytest.mark.asyncio
    async def test_players_router_mounted(self, client: AsyncClient):
        resp = await client.get("/api/v1/players")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_matches_router_mounted(self, client: AsyncClient):
        resp = await client.get("/api/v1/matches")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_analytics_router_mounted(self, client: AsyncClient):
        # Hitting /compare with no params lands on FastAPI's parameter
        # validation (422), proving the router is mounted and reachable.
        resp = await client.get("/api/v1/analytics/compare")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_root_returns_pointer(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "cricinsight"
        assert body["docs"] == "/docs"

    @pytest.mark.asyncio
    async def test_openapi_docs_available(self, client: AsyncClient):
        resp = await client.get("/docs")
        assert resp.status_code == 200
