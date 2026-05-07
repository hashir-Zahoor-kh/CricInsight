"""Daily-resetting token bucket for the CricAPI free-tier quota.

State on disk: `quota.json` next to the response cache, namespaced by
API key hash so rotating the key doesn't carry over a stale counter:

    .cache/<sha1(api_key)[:8]>/quota.json   →   {"date": "2026-05-07", "count": 47}

The `date` field is UTC because that's CricAPI's reset boundary. On
every check, if the stored date != today (UTC), the counter resets to
zero — no cron required, the next call after midnight does it
automatically.

This is intentionally simple file-locking: the seed script and pytest
runs are sequential per developer, so atomic write-then-rename gives us
crash safety without needing fcntl. If the project ever grows multiple
concurrent ingestion workers, swap this for `filelock` or a Redis
counter; the public API stays the same.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from .exceptions import RateLimitError

logger = logging.getLogger(__name__)

# CricAPI free tier as of 2026-05.
DEFAULT_DAILY_LIMIT = 100

_DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent / ".cache"


def _key_namespace(api_key: str) -> str:
    return hashlib.sha1(api_key.encode("utf-8")).hexdigest()[:8]


class _QuotaState(TypedDict):
    date: str  # ISO date (UTC)
    count: int


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


class DailyQuota:
    """Persistent counter that auto-resets when the UTC date changes."""

    def __init__(
        self,
        api_key: str,
        limit: int = DEFAULT_DAILY_LIMIT,
        cache_root: Path | None = None,
    ) -> None:
        self._limit = limit
        root = cache_root or _DEFAULT_CACHE_ROOT
        self._path = root / _key_namespace(api_key) / "quota.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # --- internals ---

    def _load(self) -> _QuotaState:
        if not self._path.exists():
            return {"date": _today_utc(), "count": 0}
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                state: _QuotaState = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "quota file corrupt at %s (%s); resetting", self._path, exc
            )
            return {"date": _today_utc(), "count": 0}

        # The midnight-UTC reset rule: if the stored date isn't today, the
        # quota has reset on CricAPI's side too — clear our counter to
        # match. This is what stops a stale counter from causing a
        # false-empty bucket the day after first use.
        if state.get("date") != _today_utc():
            return {"date": _today_utc(), "count": 0}
        return state

    def _save(self, state: _QuotaState) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(state, fh)
        tmp.replace(self._path)

    # --- public surface ---

    def remaining(self) -> int:
        return max(0, self._limit - self._load()["count"])

    def used(self) -> int:
        return self._load()["count"]

    @property
    def limit(self) -> int:
        return self._limit

    def consume(self) -> None:
        """Charge one call against the quota.

        Raises RateLimitError if the bucket is empty. Caller should NOT
        call this for cache-hit reads — only for actual network calls.
        """
        state = self._load()
        if state["count"] >= self._limit:
            raise RateLimitError(used=state["count"], limit=self._limit)
        state["count"] += 1
        self._save(state)

    def reset(self) -> None:
        """Manually clear the counter — testing aid, not for production."""
        self._save({"date": _today_utc(), "count": 0})
