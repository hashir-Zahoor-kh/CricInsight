"""Domain-specific exceptions raised by the CricAPI client.

Three classes so callers can react differently:

  * `RateLimitError`  — quota exhausted; back off until UTC midnight.
  * `APIError`        — CricAPI returned a 4xx, or a 200 with an
                        error payload. Don't retry — it's our bug.
  * `NetworkError`    — DNS / TCP / read-timeout / 5xx. Retryable.

Inheriting all three from a common `CricAPIError` lets callers catch
"anything from this client" in a single except clause when they don't
care about the distinction (e.g. test fixtures, generic logging).
"""

from __future__ import annotations


class CricAPIError(Exception):
    """Base for all CricAPI client errors."""


class RateLimitError(CricAPIError):
    """Daily quota exhausted. Surfaces remaining/limit for log messages."""

    def __init__(self, used: int, limit: int) -> None:
        self.used = used
        self.limit = limit
        super().__init__(
            f"CricAPI daily quota exhausted ({used}/{limit}); "
            "resets at next UTC midnight."
        )


class APIError(CricAPIError):
    """Non-retryable error: 4xx HTTP status or status='failure' in body."""

    def __init__(self, status_code: int | None, message: str) -> None:
        self.status_code = status_code
        super().__init__(
            f"CricAPI returned error (status={status_code}): {message}"
        )


class NetworkError(CricAPIError):
    """Retryable error: 5xx, connection failure, timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
