"""On-disk response cache for CricAPI calls.

Why this matters: CricAPI's free tier is 100 calls/day. During development
every test run, every retry, every dashboard reload would burn quota
without a cache. So the policy is aggressive:

  * Cache key  = sha1(method + endpoint + sorted-params).
  * Default    = cache-first, no expiry.  If the file exists, return it.
  * Override   = `force_refresh=True` skips the read but still writes.

The cache is namespaced by API key hash:

    .cache/<sha1(api_key)[:8]>/<sha1(request)>.json

So rotating keys gives you a clean namespace and old responses don't
"leak" between accounts. The `[:8]` prefix is enough to disambiguate
without exposing more of the key hash than needed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Anchored to the project's ingestion module so it survives `cd` from any
# caller. Lives outside the package directory in `.cache/` to keep linters
# from picking up JSON as Python.
_DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent / ".cache"


def _key_namespace(api_key: str) -> str:
    """First 8 hex chars of sha1(api_key) — opaque but stable per key."""
    return hashlib.sha1(api_key.encode("utf-8")).hexdigest()[:8]


def _request_hash(method: str, endpoint: str, params: dict[str, Any]) -> str:
    """Stable hash of method + endpoint + sorted params.

    Sorting params prevents `{a:1, b:2}` and `{b:2, a:1}` from getting
    different cache files — they're the same logical request.
    """
    canonical = json.dumps(
        {
            "method": method.upper(),
            "endpoint": endpoint,
            # Sort keys so dict ordering doesn't leak into the hash.
            "params": dict(sorted(params.items())),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


class ResponseCache:
    """File-backed cache of raw CricAPI JSON responses."""

    def __init__(
        self,
        api_key: str,
        cache_root: Path | None = None,
    ) -> None:
        root = cache_root or _DEFAULT_CACHE_ROOT
        self._dir = root / _key_namespace(api_key) / "responses"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, method: str, endpoint: str, params: dict[str, Any]) -> Path:
        return self._dir / f"{_request_hash(method, endpoint, params)}.json"

    def get(
        self, method: str, endpoint: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        path = self._path(method, endpoint, params)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            # Corrupt cache file — log and treat as cache miss. The next
            # API call will overwrite it.
            logger.warning(
                "cache file corrupt at %s (%s); treating as miss", path, exc
            )
            return None

    def set(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        path = self._path(method, endpoint, params)
        # Atomic write: write to a sibling temp file then rename so a crash
        # mid-write can never produce a partial JSON file.
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(response, fh, indent=2, sort_keys=True)
        tmp.replace(path)

    @property
    def directory(self) -> Path:
        return self._dir
