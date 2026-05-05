"""KalshiExchangeAdapter — adapts feeds.kalshi.KalshiClient to ExchangeClient.

Translation responsibilities:

  - **Type mapping**: Kalshi REST returns `dict[str, Any]`. The adapter
    parses these into typed dataclasses (`Order`, `OrderbookLevels`,
    `Position`, `Balance`).
  - **Unit conversion**: Kalshi uses cents (int strings) for prices and
    `position_fp` / `balance` cents (int) for cash. The adapter exposes
    dollar floats where appropriate.
  - **Error semantics**: Kalshi raises `KalshiResponseError` on 4xx and
    5xx. The protocol contract says: rejection (insufficient funds,
    post-only cross, wrong format) → return None / False; transient error
    (network, 5xx, rate limit) → raise. Adapter inspects status_code to
    distinguish.
  - **Quirks**: don't send `time_in_force` for default GTC (Kalshi 400s
    on it). Use `/portfolio/orders/batched` (with the 'ed' suffix) for
    batch cancel — the existing client already does this correctly.

Lifecycle: adapter owns the underlying `KalshiClient`. Construction takes
auth + base_url; `aopen()` opens the underlying client; `aclose()` closes
it. Tests can inject a pre-built client via `from_client()` to avoid
construction.

What this adapter does NOT do:
  - Series / event listing (that's TickerSource's job, not ExchangeClient).
  - Auth setup beyond accepting a `KalshiAuth` instance — the caller
    constructs auth from API key + private key.
  - Rate limiting (lives inside KalshiClient — already token-bucketed).
"""

from __future__ import annotations

import logging
from typing import Any

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from feeds.kalshi.errors import KalshiResponseError

from lipmm.execution.base import (
    Balance,
    Order,
    OrderbookLevels,
    PlaceOrderRequest,
    Position,
)

logger = logging.getLogger(__name__)


class KalshiExchangeAdapter:
    """Adapts `feeds.kalshi.KalshiClient` to `lipmm.execution.ExchangeClient`."""

    def __init__(
        self,
        *,
        auth: KalshiAuth,
        base_url: str = "https://api.elections.kalshi.com",
    ) -> None:
        self._client = KalshiClient(auth=auth, base_url=base_url)
        self._owned_client = True

    @classmethod
    def from_client(cls, client: KalshiClient) -> "KalshiExchangeAdapter":
        """Construct from a pre-built KalshiClient (useful for tests)."""
        adapter = cls.__new__(cls)
        adapter._client = client
        adapter._owned_client = False
        return adapter

    async def aopen(self) -> None:
        """Open the underlying HTTP client. Call once before using."""
        await self._client.open()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._owned_client:
            await self._client.close()

    async def __aenter__(self) -> "KalshiExchangeAdapter":
        await self.aopen()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ── Order lifecycle ─────────────────────────────────────────────

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        """POST /portfolio/orders. Returns Order on success, None on 4xx
        rejection (insufficient funds, post-only cross, etc.). Raises on
        5xx or transport error.

        Note: Kalshi default GTC is implicit — we never send
        `time_in_force` for GTC because Kalshi 400s on the field even
        when the value is correct.
        """
        try:
            resp = await self._client.create_order(
                ticker=request.ticker,
                action=request.action,
                side=request.side,
                order_type="limit",
                count=request.count,
                yes_price=request.limit_price_cents,
                post_only=request.post_only,
            )
        except KalshiResponseError as exc:
            if 400 <= (exc.status_code or 0) < 500:
                # Genuine rejection (post-only cross, insufficient funds, etc.)
                logger.info(
                    "Kalshi place_order rejected (status=%s): %s",
                    exc.status_code, exc,
                )
                return None
            raise

        order_dict = resp.get("order", {})
        return _parse_order(order_dict, ticker=request.ticker,
                            action=request.action, side=request.side,
                            limit_price=request.limit_price_cents,
                            count=request.count)

    async def amend_order(
        self, order_id: str, *,
        new_limit_price_cents: int | None = None,
        new_count: int | None = None,
    ) -> Order | None:
        """POST /portfolio/orders/{id}/amend. Returns Order on success,
        None if Kalshi rejects the amend (it often does — historical 400
        rate is high). Caller is expected to fall back to cancel+place."""
        try:
            resp = await self._client.amend_order(
                order_id,
                yes_price=new_limit_price_cents,
                count=new_count,
            )
        except KalshiResponseError as exc:
            if 400 <= (exc.status_code or 0) < 500:
                logger.info(
                    "Kalshi amend_order rejected (status=%s): %s",
                    exc.status_code, exc,
                )
                return None
            raise

        order_dict = resp.get("order", {})
        if not order_dict:
            return None
        return _parse_order(order_dict)

    async def cancel_order(self, order_id: str) -> bool:
        """DELETE /portfolio/orders/{id}. Returns True on success, False
        if Kalshi 404s (order already gone). Raises on 5xx."""
        try:
            await self._client.cancel_order(order_id)
            return True
        except KalshiResponseError as exc:
            if exc.status_code == 404:
                return False
            if 400 <= (exc.status_code or 0) < 500:
                logger.warning(
                    "Kalshi cancel_order non-404 4xx (status=%s): %s",
                    exc.status_code, exc,
                )
                return False
            raise

    async def cancel_orders(self, order_ids: list[str]) -> dict[str, bool]:
        """Batch cancel via `/portfolio/orders/batched`. Falls back to
        per-order cancellation on batch failure (the historical pattern
        from the soy bot, since the batched endpoint has been flaky)."""
        if not order_ids:
            return {}

        # Try batch first
        try:
            await self._client.batch_cancel_orders(order_ids)
            # Verify by re-querying resting orders — defensive against
            # silent partial success (batch returns 200 but didn't cancel
            # everything)
            try:
                resp = await self._client.get_orders(status="resting", limit=200)
                still_resting = {
                    o.get("order_id") for o in resp.get("orders", [])
                    if o.get("order_id")
                }
                return {
                    oid: oid not in still_resting for oid in order_ids
                }
            except Exception:
                # Verification failed — assume batch worked
                return {oid: True for oid in order_ids}
        except Exception as exc:
            logger.warning(
                "Kalshi batch cancel failed (%s), falling back to per-order",
                exc,
            )

        # Per-order fallback
        out: dict[str, bool] = {}
        for oid in order_ids:
            out[oid] = await self.cancel_order(oid)
        return out

    # ── Reads ───────────────────────────────────────────────────────

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        """Snapshot the orderbook for a ticker. Returns OrderbookLevels
        with yes_levels and no_levels as [(price_cents, size), ...] sorted
        highest-first."""
        resp = await self._client.get_orderbook(ticker)
        ob_fp = resp.get("orderbook_fp", {}) or {}
        yes_dollars = ob_fp.get("yes_dollars", []) or []
        no_dollars = ob_fp.get("no_dollars", []) or []
        return OrderbookLevels(
            ticker=ticker,
            yes_levels=_parse_depth(yes_dollars),
            no_levels=_parse_depth(no_dollars),
        )

    async def list_resting_orders(self) -> list[Order]:
        """All currently-resting orders for the account."""
        resp = await self._client.get_orders(status="resting", limit=200)
        return [_parse_order(o) for o in resp.get("orders", [])]

    async def list_positions(self) -> list[Position]:
        """All non-zero positions."""
        resp = await self._client.get_positions(limit=200)
        out: list[Position] = []
        for p in resp.get("market_positions", []):
            try:
                qty = int(round(float(p.get("position_fp", "0") or 0)))
            except (ValueError, TypeError):
                qty = 0
            if qty == 0:
                continue
            try:
                avg_cost_cents = int(round(float(
                    p.get("average_cost_cents", 0) or 0
                )))
            except (ValueError, TypeError):
                avg_cost_cents = 0
            try:
                realized = float(p.get("realized_pnl_dollars", 0) or 0)
            except (ValueError, TypeError):
                realized = 0.0
            try:
                fees = float(p.get("fees_paid_dollars", 0) or 0)
            except (ValueError, TypeError):
                fees = 0.0
            out.append(Position(
                ticker=p.get("ticker", ""),
                quantity=qty,
                avg_cost_cents=avg_cost_cents,
                realized_pnl_dollars=realized,
                fees_paid_dollars=fees,
            ))
        return out

    async def get_balance(self) -> Balance:
        """Account cash + portfolio value, in dollars."""
        resp = await self._client.get_balance()
        # Kalshi balance is in cents (int)
        cash_cents = float(resp.get("balance", 0) or 0)
        portfolio_cents = float(resp.get("portfolio_value", 0) or 0)
        return Balance(
            cash_dollars=cash_cents / 100.0,
            portfolio_value_dollars=portfolio_cents / 100.0,
        )


# ── Parsing helpers ───────────────────────────────────────────────────


def _parse_depth(levels: list) -> list[tuple[int, float]]:
    """Parse Kalshi `[[price_str_dollars, size_str], ...]` into
    `[(price_cents, size), ...]` sorted highest-first."""
    if not levels:
        return []
    parsed: list[tuple[int, float]] = []
    for lv in levels:
        if not isinstance(lv, (list, tuple)) or len(lv) < 2:
            continue
        try:
            px = int(round(float(lv[0]) * 100))
            sz = float(lv[1])
        except (ValueError, TypeError):
            continue
        parsed.append((px, sz))
    parsed.sort(key=lambda x: -x[0])  # highest-first
    return parsed


def _parse_order(
    o: dict[str, Any], *,
    ticker: str | None = None,
    action: str | None = None,
    side: str | None = None,
    limit_price: int | None = None,
    count: int | None = None,
) -> Order:
    """Parse a Kalshi order dict into an Order dataclass.

    Falls back to the override kwargs when fields aren't present in the
    Kalshi response (e.g., create_order's response sometimes omits some
    fields). Caller passes overrides matching the place_order request.
    """
    oid = o.get("order_id", "")
    parsed_action = o.get("action") or action or "buy"
    parsed_side = o.get("side") or side or "yes"
    parsed_ticker = o.get("ticker") or ticker or ""
    # Kalshi inconsistency: create_order returns `yes_price` as cents
    # (int), but /portfolio/orders returns `yes_price_dollars` as a
    # string like "0.4500". Check the cents field first; fall through
    # to the dollar string field; finally to the kwarg.
    if "yes_price" in o and o["yes_price"] is not None:
        try:
            parsed_limit = int(o["yes_price"])
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif "yes_price_dollars" in o and o["yes_price_dollars"] is not None:
        # "0.4500" → 45 cents
        try:
            parsed_limit = int(round(float(o["yes_price_dollars"]) * 100))
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif "no_price_dollars" in o and o["no_price_dollars"] is not None:
        # Some sell-side orders only return no_price_dollars; convert
        # via 100 - no_price.
        try:
            parsed_limit = 100 - int(round(float(o["no_price_dollars"]) * 100))
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif limit_price is not None:
        parsed_limit = limit_price
    else:
        parsed_limit = 0
    if "remaining_count" in o and o["remaining_count"] is not None:
        try:
            parsed_remaining = int(o["remaining_count"])
        except (ValueError, TypeError):
            parsed_remaining = count or 0
    elif "remaining_count_fp" in o and o["remaining_count_fp"] is not None:
        try:
            parsed_remaining = int(round(float(o["remaining_count_fp"])))
        except (ValueError, TypeError):
            parsed_remaining = count or 0
    else:
        parsed_remaining = count or 0
    parsed_status = o.get("status", "resting")
    return Order(
        order_id=oid,
        ticker=parsed_ticker,
        action=parsed_action,  # type: ignore[arg-type]
        side=parsed_side,  # type: ignore[arg-type]
        limit_price_cents=parsed_limit,
        remaining_count=parsed_remaining,
        status=parsed_status,
    )
