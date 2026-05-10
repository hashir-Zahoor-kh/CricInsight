"""CricAPI HTTP client.

Composition over inheritance: the client owns a `ResponseCache`, a
`DailyQuota`, and an `httpx.Client`, and orchestrates all three around
each request. The flow for every method is identical:

    1. Build (endpoint, params).
    2. If `force_refresh=False` and cache has it → return cached.
    3. Otherwise charge one call against the daily quota.
    4. GET the endpoint, retrying on 5xx / network errors with
       exponential backoff (1s, 2s, 4s).
    5. On success, write to cache and return.

Sync httpx (not async) on purpose: the only caller is the seed CLI
(Phase 3.4), which is one-shot. Async would just add ceremony.

Tests inject a custom `httpx.Client` (built from `MockTransport`) so
nothing actually hits the network; the public surface stays the same.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from .cache import ResponseCache
from .exceptions import APIError, NetworkError, RateLimitError
from .rate_limit import DEFAULT_DAILY_LIMIT, DailyQuota

logger = logging.getLogger(__name__)

# Endpoints the project actually calls. Listed once here so the test
# suite can iterate over them and confirm each method routes correctly.
ENDPOINT_CRIC_SCORE = "/cricScore"
ENDPOINT_SERIES = "/series"
ENDPOINT_MATCHES = "/matches"
ENDPOINT_MATCH = "/match"
ENDPOINT_PLAYERS = "/players"
ENDPOINT_PLAYER_STATS = "/playerStats"

# Backoff schedule for retryable errors: 1s, 2s, 4s. 4 attempts total.
# Kept short so tests don't have to monkey-patch sleep — pytest still
# completes fast even when all 4 attempts fire, but production seed
# runs get enough breathing room for transient network blips.
_RETRY_DELAYS = (1.0, 2.0, 4.0)


class CricAPIClient:
    """Cache-first, quota-aware client for CricAPI."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.cricapi.com/v1",
        *,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        cache_root: Path | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "CRICAPI_KEY is empty — set it in .env before constructing "
                "CricAPIClient."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._cache = ResponseCache(api_key=api_key, cache_root=cache_root)
        self._quota = DailyQuota(
            api_key=api_key, limit=daily_limit, cache_root=cache_root
        )
        # Tests inject their own client; production constructs a default.
        self._http = http_client or httpx.Client(timeout=timeout)
        self._owns_http = http_client is None

    # --- context manager so callers can `with CricAPIClient(...) as c:` ---

    def __enter__(self) -> "CricAPIClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._owns_http:
            self._http.close()

    @property
    def quota(self) -> DailyQuota:
        return self._quota

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    # --- core request pipeline ---

    def _get(
        self,
        endpoint: str,
        params: Mapping[str, Any] | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Cache-first GET with retry/backoff and quota enforcement.

        The `apikey` query param is added internally so cache keys never
        depend on it (and never end up in log lines).
        """
        params = dict(params or {})

        # Cache lookup — happens BEFORE quota check on purpose. A cache
        # hit doesn't touch the network, so it doesn't burn quota.
        if not force_refresh:
            cached = self._cache.get("GET", endpoint, params)
            if cached is not None:
                logger.info(
                    "cache hit  %s params=%s remaining=%s/%s",
                    endpoint, params, self._quota.remaining(), self._quota.limit,
                )
                return cached

        # About to hit the network — charge the quota first so a failure
        # to write the cache doesn't double-charge.
        self._quota.consume()
        logger.info(
            "cache miss %s params=%s remaining=%s/%s (post-charge)",
            endpoint, params, self._quota.remaining(), self._quota.limit,
        )

        # Inject apikey at request time only; never include in cache key.
        request_params = {**params, "apikey": self._api_key}
        url = f"{self._base_url}{endpoint}"

        last_network_error: Exception | None = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                response = self._http.get(url, params=request_params)
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                # Retry transient transport failures with backoff.
                last_network_error = exc
                if attempt < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "network error on %s (attempt %d): %s — retrying in %.1fs",
                        endpoint, attempt + 1, exc, delay,
                    )
                    time.sleep(delay)
                    continue
                raise NetworkError(
                    f"GET {endpoint}: {exc} after {attempt + 1} attempts"
                ) from exc

            # 5xx is retryable, 4xx is not.
            if 500 <= response.status_code < 600:
                last_network_error = httpx.HTTPStatusError(
                    f"server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
                if attempt < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[attempt]
                    logger.warning(
                        "5xx on %s (attempt %d, status=%s) — retrying in %.1fs",
                        endpoint, attempt + 1, response.status_code, delay,
                    )
                    time.sleep(delay)
                    continue
                raise NetworkError(
                    f"GET {endpoint}: server returned {response.status_code} "
                    f"after {attempt + 1} attempts"
                )

            if 400 <= response.status_code < 500:
                # Don't retry — it's a config bug (bad key, wrong params)
                # and retrying would just burn quota.
                raise APIError(response.status_code, response.text[:500])

            # 2xx — parse JSON and check CricAPI's in-band status field.
            try:
                payload = response.json()
            except ValueError as exc:
                raise APIError(
                    response.status_code, f"non-JSON body: {exc}"
                ) from exc

            # CricAPI wraps everything in `{status: "success"|"failure", ...}`.
            # A "failure" can mean "rate limit hit" — handle that explicitly
            # so callers see a RateLimitError instead of a generic APIError.
            api_status = payload.get("status")
            if api_status == "failure":
                msg = payload.get("reason") or payload.get("message") or ""
                if "limit" in msg.lower() or "quota" in msg.lower():
                    raise RateLimitError(
                        used=self._quota.used(), limit=self._quota.limit
                    )
                raise APIError(response.status_code, msg)

            self._cache.set("GET", endpoint, params, payload)
            return payload

        # Unreachable — every loop iteration either returns, raises, or
        # falls through to the next iteration. Defensive line for mypy.
        raise NetworkError(  # pragma: no cover
            f"GET {endpoint}: exhausted retries ({last_network_error})"
        )

    # --- public methods (one per CricAPI endpoint we use) ---

    def cric_score(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return self._get(ENDPOINT_CRIC_SCORE, force_refresh=force_refresh)

    def series(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return self._get(ENDPOINT_SERIES, force_refresh=force_refresh)

    def matches(
        self, *, offset: int = 0, force_refresh: bool = False
    ) -> dict[str, Any]:
        # Only include offset in params when > 0 so the offset=0 cache
        # key matches the original (paramless) /matches calls and stays
        # warm across this refactor. CricAPI paginates ~25/page on free
        # tier; the seed walks 3-5 pages to build a candidate pool.
        params = {} if offset == 0 else {"offset": offset}
        return self._get(
            ENDPOINT_MATCHES, params=params, force_refresh=force_refresh
        )

    def match(self, match_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        return self._get(
            ENDPOINT_MATCH,
            params={"id": match_id},
            force_refresh=force_refresh,
        )

    def players(
        self, search: str, *, force_refresh: bool = False
    ) -> dict[str, Any]:
        return self._get(
            ENDPOINT_PLAYERS,
            params={"search": search},
            force_refresh=force_refresh,
        )

    def player_stats(
        self, player_id: str, *, force_refresh: bool = False
    ) -> dict[str, Any]:
        return self._get(
            ENDPOINT_PLAYER_STATS,
            params={"id": player_id},
            force_refresh=force_refresh,
        )
