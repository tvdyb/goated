"""KalshiIncentiveProvider — hits Kalshi's public /incentive_programs.

The endpoint is documented at:
  https://docs.kalshi.com/api-reference/incentive-programs/get-incentives

It's **unauthenticated** so we don't need the heavy `KalshiClient` auth
machinery — a thin httpx call suffices. Pagination is via `next_cursor`
in the response; we walk it until exhausted (or a configurable page cap
hits, to bound worst-case work).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from lipmm.incentives.base import IncentiveProgram

logger = logging.getLogger(__name__)


_DEFAULT_BASE_URL = "https://api.elections.kalshi.com"
_INCENTIVES_PATH = "/trade-api/v2/incentive_programs"
_DEFAULT_TIMEOUT_S = 10.0
_MAX_PAGES = 100   # 100 × 10000 = 1M rows; sanity cap on runaway pagination


class KalshiIncentiveProvider:
    """Fetch active Kalshi incentive programs.

    Args:
        base_url: Override for tests; defaults to production Kalshi.
        timeout_s: Per-request timeout. Cache layer absorbs failures so
            this can be tight.
        incentive_type: Server-side filter. "liquidity" by default; pass
            "all" to also include volume incentives.
        status: Server-side filter. "active" by default.
        page_limit: How many entries per page. 1000 keeps payload small
            but typically only one page is needed.
        client: Optional pre-built httpx.AsyncClient for tests; the
            provider does NOT close it (caller manages lifecycle).
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        incentive_type: str = "liquidity",
        status: str = "active",
        page_limit: int = 1000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (1 <= page_limit <= 10_000):
            raise ValueError(
                f"page_limit must be in [1, 10000]; got {page_limit}"
            )
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._incentive_type = incentive_type
        self._status = status
        self._page_limit = page_limit
        self._client = client
        self._owns_client = client is None

    async def list_active(self) -> list[IncentiveProgram]:
        """One full pagination walk. Raises on transport / API failure."""
        client = self._client
        owns = self._owns_client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_s)
            owns = True
        try:
            return await self._paginate(client)
        finally:
            if owns:
                await client.aclose()

    async def _paginate(self, client: httpx.AsyncClient) -> list[IncentiveProgram]:
        url = f"{self._base_url}{_INCENTIVES_PATH}"
        cursor: str | None = None
        out: list[IncentiveProgram] = []
        for _ in range(_MAX_PAGES):
            params: dict[str, Any] = {
                "status": self._status,
                "type": self._incentive_type,
                "limit": self._page_limit,
            }
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
            entries = body.get("incentive_programs", []) or []
            for entry in entries:
                try:
                    out.append(IncentiveProgram.from_api(entry))
                except Exception as exc:
                    logger.warning(
                        "incentive parse failed: %s; entry=%s", exc, entry,
                    )
            cursor = body.get("next_cursor") or None
            if not cursor:
                return out
        logger.warning(
            "KalshiIncentiveProvider hit MAX_PAGES=%d; truncating",
            _MAX_PAGES,
        )
        return out
