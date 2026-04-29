"""Kalshi API error types.

Fail-loud policy: every unexpected condition raises a typed exception.
No silent swallowing.
"""

from __future__ import annotations


class KalshiAPIError(Exception):
    """Base exception for all Kalshi API errors."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class KalshiAuthError(KalshiAPIError):
    """Authentication or authorization failure (401/403)."""


class KalshiRateLimitError(KalshiAPIError):
    """Rate limit exceeded after max retries (429)."""


class KalshiResponseError(KalshiAPIError):
    """Unexpected status code or malformed response body."""
