"""Kalshi authenticated REST client.

Provides typed async methods for all core Kalshi REST endpoints needed
by the quoter, kill-switch, and downstream actions.

Non-negotiables enforced:
  - asyncio for I/O only (no async business logic)
  - No silent failures: unexpected status codes raise typed exceptions
  - No pandas
  - Type hints on all public interfaces

References:
  - Kalshi API Reference: https://docs.kalshi.com/api-reference
  - Phase 07 section 8 (API and market access)
  - Phase 09 section 1.2 (endpoints that matter for a market maker)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.errors import (
    KalshiAPIError,
    KalshiAuthError,
    KalshiRateLimitError,
    KalshiResponseError,
)
from feeds.kalshi.rate_limiter import (
    CANCEL_REQUEST_COST,
    DEFAULT_REQUEST_COST,
    KalshiRateLimiter,
    KalshiTier,
)

logger = logging.getLogger(__name__)

_PROD_BASE_URL = "https://api.elections.kalshi.com"
_DEMO_BASE_URL = "https://demo-api.kalshi.co"
_API_PREFIX = "/trade-api/v2"

_DEFAULT_TIMEOUT_S = 15.0
_MAX_RETRIES = 4
_BACKOFF_BASE_S = 1.0


class KalshiClient:
    """Async Kalshi REST client with signing, rate limiting, and retry.

    Usage::

        auth = KalshiAuth(api_key="...", private_key_pem=b"...")
        async with KalshiClient(auth=auth) as client:
            event = await client.get_event("KXSOYBEANW-26APR24")
            ob = await client.get_orderbook("KXSOYBEANW-26APR24-17")
    """

    def __init__(
        self,
        *,
        auth: KalshiAuth,
        tier: KalshiTier = KalshiTier.BASIC,
        base_url: str = _PROD_BASE_URL,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._auth = auth
        self._rate_limiter = KalshiRateLimiter(tier=tier)
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    @property
    def rate_limiter(self) -> "KalshiRateLimiter":
        """Public accessor used by the dashboard / diagnostics."""
        return self._rate_limiter

    async def __aenter__(self) -> KalshiClient:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def open(self) -> None:
        """Open the underlying HTTP client."""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_s,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Core request method ──────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        is_write: bool = False,
        token_cost: float = DEFAULT_REQUEST_COST,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated, rate-limited, retrying request.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: Path relative to API prefix (e.g. ``/events``).
            params: Query parameters.
            json_body: JSON body for POST requests.
            is_write: Whether this is a write operation (for rate limiter).
            token_cost: Token cost for rate limiting.

        Returns:
            Parsed JSON response body as dict.

        Raises:
            KalshiAuthError: On 401/403.
            KalshiRateLimitError: On 429 after max retries.
            KalshiResponseError: On other non-2xx or malformed response.
            KalshiAPIError: On network/transport errors after retries.
        """
        if self._client is None:
            raise KalshiAPIError("Client not open. Call open() or use async context manager.")

        full_path = _API_PREFIX + path

        # Rate limit before sending
        if is_write:
            await self._rate_limiter.acquire_write(cost=token_cost)
        else:
            await self._rate_limiter.acquire_read(cost=token_cost)

        retries = max_retries if max_retries is not None else self._max_retries
        last_exc: Exception | None = None
        for attempt in range(retries):
            # Build auth headers fresh each attempt (timestamp changes)
            auth_headers = self._auth.build_headers(method.upper(), full_path)

            try:
                response = await self._client.request(
                    method,
                    full_path,
                    params=params,
                    json=json_body,
                    headers=auth_headers,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                wait = _BACKOFF_BASE_S * (2 ** attempt)
                logger.warning(
                    "Kalshi request error: %s %s (attempt %d/%d): %s, retrying in %.1fs",
                    method, path, attempt + 1, self._max_retries, exc, wait,
                )
                last_exc = exc
                await asyncio.sleep(wait)
                continue

            # Handle status codes
            status = response.status_code

            if status == 429:
                wait = _BACKOFF_BASE_S * (2 ** attempt)
                self._rate_limiter.note_429()
                logger.warning(
                    "Kalshi 429 rate limit: %s %s (attempt %d/%d), backing off %.1fs",
                    method, path, attempt + 1, self._max_retries, wait,
                )
                last_exc = KalshiRateLimitError(
                    f"Rate limited on {method} {path}",
                    status_code=429,
                    body=response.text,
                )
                await asyncio.sleep(wait)
                continue

            if status in (401, 403):
                raise KalshiAuthError(
                    f"Authentication failed: {status} on {method} {path}",
                    status_code=status,
                    body=response.text,
                )

            if status >= 500:
                wait = _BACKOFF_BASE_S * (2 ** attempt)
                logger.warning(
                    "Kalshi server error %d: %s %s (attempt %d/%d), retrying in %.1fs",
                    status, method, path, attempt + 1, self._max_retries, wait,
                )
                last_exc = KalshiResponseError(
                    f"Server error {status} on {method} {path}",
                    status_code=status,
                    body=response.text,
                )
                await asyncio.sleep(wait)
                continue

            if not (200 <= status < 300):
                raise KalshiResponseError(
                    f"Unexpected status {status} on {method} {path}",
                    status_code=status,
                    body=response.text,
                )

            # Parse JSON
            try:
                data = response.json()
            except Exception as exc:
                raise KalshiResponseError(
                    f"Malformed JSON response from {method} {path}: {exc}",
                    status_code=status,
                    body=response.text,
                ) from exc

            if not isinstance(data, dict):
                raise KalshiResponseError(
                    f"Expected JSON object from {method} {path}, got {type(data).__name__}",
                    status_code=status,
                    body=response.text,
                )

            return data

        # Exhausted retries -- re-raise the last typed exception if available
        if isinstance(last_exc, (KalshiRateLimitError, KalshiResponseError)):
            raise last_exc
        raise KalshiAPIError(
            f"Failed after {self._max_retries} retries: {method} {path}: {last_exc}"
        )

    # ── Market data (read) ───────────────────────────────────────────

    async def get_events(
        self,
        *,
        series_ticker: str | None = None,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /events -- list events with optional filters."""
        params: dict[str, Any] = {"limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/events", params=params)

    async def get_event(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool = False,
    ) -> dict[str, Any]:
        """GET /events/{ticker} -- single event metadata.

        By default Kalshi returns markets as a sibling top-level field
        next to `event`. Pass `with_nested_markets=True` to also nest
        them under `event.markets` for callers that expect that shape.
        """
        params = {"with_nested_markets": "true"} if with_nested_markets else None
        return await self._request(
            "GET", f"/events/{event_ticker}", params=params,
        )

    async def get_market(self, ticker: str) -> dict[str, Any]:
        """GET /markets/{ticker} -- single market metadata."""
        return await self._request("GET", f"/markets/{ticker}")

    async def get_orderbook(self, ticker: str) -> dict[str, Any]:
        """GET /markets/{ticker}/orderbook -- current orderbook snapshot."""
        return await self._request("GET", f"/markets/{ticker}/orderbook")

    async def get_trades(
        self,
        *,
        ticker: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /markets/trades -- trade prints."""
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/markets/trades", params=params)

    # ── Order lifecycle (write) ──────────────────────────────────────

    async def create_order(
        self,
        *,
        ticker: str,
        action: str,
        side: str,
        order_type: str,
        count: int,
        yes_price: int | None = None,
        no_price: int | None = None,
        time_in_force: str = "gtc",
        client_order_id: str | None = None,
        buy_max_cost: int | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
        self_trade_prevention_type: str | None = None,
    ) -> dict[str, Any]:
        """POST /portfolio/orders -- create a new order.

        Args:
            ticker: Market ticker (e.g. ``KXSOYBEANW-26APR24-17``).
            action: ``buy`` or ``sell``.
            side: ``yes`` or ``no``.
            order_type: ``limit`` or ``market``.
            count: Number of contracts.
            yes_price: Yes price in cents (1-99).
            no_price: No price in cents (1-99).
            time_in_force: ``gtc``, ``ioc``, or ``fok``.
            client_order_id: Optional idempotency key.
            buy_max_cost: Optional max cost in cents.
            post_only: If True, reject if would immediately fill.
            reduce_only: If True, only reduce existing position.
            self_trade_prevention_type: ``taker_at_cross`` or ``maker``.

        Returns:
            Order creation response.
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "type": order_type,
            "count": count,
        }
        if time_in_force != "gtc":
            body["time_in_force"] = time_in_force
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        if client_order_id is not None:
            body["client_order_id"] = client_order_id
        if buy_max_cost is not None:
            body["buy_max_cost"] = buy_max_cost
        if post_only:
            body["post_only"] = True
        if reduce_only:
            body["reduce_only"] = True
        if self_trade_prevention_type is not None:
            body["self_trade_prevention_type"] = self_trade_prevention_type

        return await self._request(
            "POST", "/portfolio/orders", json_body=body, is_write=True,
        )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """DELETE /portfolio/orders/{order_id} -- cancel a single order."""
        return await self._request(
            "DELETE",
            f"/portfolio/orders/{order_id}",
            is_write=True,
            token_cost=CANCEL_REQUEST_COST,
        )

    async def amend_order(
        self,
        order_id: str,
        *,
        yes_price: int | None = None,
        no_price: int | None = None,
        count: int | None = None,
    ) -> dict[str, Any]:
        """POST /portfolio/orders/{order_id}/amend -- amend a resting order.

        Amending preserves queue position when only size changes.
        When price changes, the order moves to the new price level with
        fresh priority — but uses one API call instead of cancel + place.

        Args:
            order_id: ID of the resting order to amend.
            yes_price: New yes price in cents (1-99), or None to keep.
            no_price: New no price in cents (1-99), or None to keep.
            count: New contract count, or None to keep.

        Returns:
            Amend response with updated order details.
        """
        body: dict[str, Any] = {}
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        if count is not None:
            body["count"] = count
        if not body:
            raise KalshiAPIError("amend_order requires at least one of yes_price, no_price, or count")
        return await self._request(
            "POST",
            f"/portfolio/orders/{order_id}/amend",
            json_body=body,
            is_write=True,
        )

    async def batch_cancel_orders(self, order_ids: list[str]) -> dict[str, Any]:
        """DELETE /portfolio/orders/batched -- cancel multiple orders.

        Path is `/batched` (not `/batch`); body uses `{"orders": [{"order_id": ...}]}`
        format. Discovered via pykalshi reference implementation. Call sites should
        wrap this in try/except and fall back to per-order cancels on failure.

        Note: batch requests are NOT discounted; cost = len(order_ids) * CANCEL_REQUEST_COST.
        """
        total_cost = float(len(order_ids) * CANCEL_REQUEST_COST)
        return await self._request(
            "DELETE",
            "/portfolio/orders/batched",
            json_body={"orders": [{"order_id": oid} for oid in order_ids]},
            is_write=True,
            token_cost=total_cost,
        )

    async def trigger_order_group(self, group_id: str) -> dict[str, Any]:
        """POST /order-groups/{group_id}/trigger -- trigger group cancellation."""
        return await self._request(
            "POST",
            f"/order-groups/{group_id}/trigger",
            is_write=True,
        )

    async def get_orders(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        status: str = "resting",
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /portfolio/orders -- list orders with optional filters."""
        params: dict[str, Any] = {"limit": limit, "status": status}
        if ticker:
            params["ticker"] = ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/portfolio/orders", params=params)

    # ── Portfolio (read) ─────────────────────────────────────────────

    async def get_positions(
        self,
        *,
        event_ticker: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /portfolio/positions -- current positions."""
        params: dict[str, Any] = {"limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/portfolio/positions", params=params)

    async def get_fills(
        self,
        *,
        ticker: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /portfolio/fills -- fill history."""
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/portfolio/fills", params=params)

    async def get_balance(self) -> dict[str, Any]:
        """GET /portfolio/balance -- account balance."""
        return await self._request("GET", "/portfolio/balance")

    async def get_settlements(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /portfolio/settlements -- settlement history."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/portfolio/settlements", params=params)

    async def get_incentive_programs(
        self,
        *,
        status: str = "active",
        type: str = "liquidity",
        limit: int = 1000,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /incentive_programs — list LIP/volume reward programs.

        This endpoint is **unauthenticated** (no Authorization header
        required). The KalshiClient still routes the request through
        its rate-limiter for politeness.

        Args:
            status: "all" | "active" | "upcoming" | "closed" | "paid_out"
            type:   "all" | "liquidity" | "volume"
            limit:  page size (1..10000)
            cursor: pagination cursor from a prior response's `next_cursor`

        Returns dict with:
            incentive_programs: list of program records
            next_cursor: str | "" (empty when paginated to end)
        """
        params: dict[str, Any] = {"status": status, "type": type, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/incentive_programs", params=params)

    async def get_exchange_status(self) -> dict[str, Any]:
        """GET /exchange/status -- maintenance/trading status.

        Single-attempt (no retries) on purpose: a 5xx response IS the
        maintenance signal, so retrying just spams logs while learning
        nothing new.

        Returns dict with:
            exchange_active: bool — False if exchange is under maintenance.
            trading_active: bool — False outside trading hours.
            exchange_estimated_resume_time: ISO8601 (only during maintenance).
        """
        return await self._request("GET", "/exchange/status", max_retries=1)
