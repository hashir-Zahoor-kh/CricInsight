"""Live scores service — wraps CricAPI with a 60s in-memory cache.

Design goals:
  - Never raises. Any failure (network, quota, missing key) returns
    LiveScoreResponse(live_available=False, matches=[]).
  - One outbound call per 60s regardless of dashboard polling frequency.
  - Filters out women's matches — dashboard is men's-cricket-only for now.
"""

from __future__ import annotations

import os
import time

import httpx

from app.schemas.live import LiveMatch, LiveScoreResponse

CRICAPI_URL = "https://api.cricapi.com/v1/currentMatches"
CACHE_TTL = 60.0  # seconds

# Module-level cache — simple dict avoids asyncio.Lock complexity;
# the worst case is two simultaneous cold-cache requests each making
# one outbound call, which is acceptable.
_cache: dict = {"response": None, "at": 0.0}


async def get_live_scores() -> LiveScoreResponse:
    now = time.monotonic()
    if _cache["response"] is not None and (now - _cache["at"]) < CACHE_TTL:
        return _cache["response"]

    result = await _fetch()
    _cache["response"] = result
    _cache["at"] = now
    return result


async def _fetch() -> LiveScoreResponse:
    api_key = os.getenv("CRICAPI_KEY")
    if not api_key:
        return LiveScoreResponse(live_available=False, matches=[])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                CRICAPI_URL,
                params={"apikey": api_key, "offset": 0},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return LiveScoreResponse(live_available=False, matches=[])

    if data.get("status") != "success":
        return LiveScoreResponse(live_available=False, matches=[])

    matches: list[LiveMatch] = []
    for m in data.get("data", []):
        name: str = m.get("name", "")
        if "women" in name.lower():
            continue

        raw_scores: list[dict] = m.get("score", [])
        scores: dict[str, str] = {}
        for s in raw_scores:
            # "Pakistan Inning 1" → "Pakistan"
            team = (
                s.get("inning", "")
                .replace(" Inning 1", "")
                .replace(" Inning 2", "")
            )
            r, w, o = s.get("r", 0), s.get("w", 0), s.get("o", 0)
            scores[team] = f"{r}/{w} ({o} ov)"

        is_live = bool(m.get("matchStarted")) and not bool(m.get("matchEnded"))

        matches.append(
            LiveMatch(
                match_id=str(m.get("id", "")),
                name=name,
                status=m.get("status", ""),
                match_type=m.get("matchType", ""),
                venue=m.get("venue") or None,
                teams=m.get("teams", []),
                scores=scores,
                is_live=is_live,
            )
        )

    return LiveScoreResponse(live_available=True, matches=matches)
