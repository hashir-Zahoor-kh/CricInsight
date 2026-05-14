"""Live scores endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.live import LiveScoreResponse
from app.services.live_scores import get_live_scores

router = APIRouter(prefix="/live", tags=["live"])


@router.get(
    "/scores",
    response_model=LiveScoreResponse,
    summary="Current live cricket scores (60s cache).",
)
async def live_scores() -> LiveScoreResponse:
    """Returns in-progress matches from CricAPI.

    Cached for 60 s. Never raises — returns
    `{live_available: false, matches: []}` when the upstream API is
    unavailable or `CRICAPI_KEY` is not configured.
    """
    return await get_live_scores()
