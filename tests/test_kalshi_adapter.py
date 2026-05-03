"""Tests for lipmm.execution.adapters.kalshi.KalshiExchangeAdapter.

Uses an in-memory FakeKalshiClient to exercise the adapter without
hitting Kalshi production. Validates:
  - Protocol satisfaction
  - Type translation (Kalshi dicts → lipmm dataclasses)
  - Error semantics (4xx → None/False, 5xx → raise)
  - Batch cancel with verify+fallback
  - Order parsing edge cases
  - Position parsing (position_fp float-string → int)
  - Balance parsing (cents → dollars)
  - Orderbook depth parsing (sorted highest-first)
"""

from __future__ import annotations

from typing import Any

import pytest

from feeds.kalshi.errors import KalshiResponseError

from lipmm.execution import (
    ExchangeClient,
    Order,
    OrderbookLevels,
    PlaceOrderRequest,
    Position,
)
from lipmm.execution.adapters import KalshiExchangeAdapter


# ── Fake KalshiClient ──────────────────────────────────────────────────


class FakeKalshiClient:
    """In-memory stub of KalshiClient for adapter tests.

    Does NOT inherit from KalshiClient — adapter only depends on
    duck-typed methods so structural typing is enough.
    """

    def __init__(self) -> None:
        # Per-method canned responses; tests configure as needed
        self.create_order_response: dict | Exception = {"order": {}}
        self.amend_order_response: dict | Exception = {"order": {}}
        self.cancel_order_response: Any = {}  # success returns dict
        self.batch_cancel_response: Any = {}
        self.orderbook_response: dict = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
        self.orders_response: dict = {"orders": []}
        self.positions_response: dict = {"market_positions": []}
        self.balance_response: dict = {"balance": 0, "portfolio_value": 0}
        self.calls: list[tuple[str, dict]] = []

    @staticmethod
    def _maybe_raise(value: Any) -> Any:
        if isinstance(value, Exception):
            raise value
        return value

    async def create_order(self, **kwargs: Any) -> dict:
        self.calls.append(("create_order", kwargs))
        return self._maybe_raise(self.create_order_response)

    async def amend_order(self, order_id: str, **kwargs: Any) -> dict:
        self.calls.append(("amend_order", {"order_id": order_id, **kwargs}))
        return self._maybe_raise(self.amend_order_response)

    async def cancel_order(self, order_id: str) -> dict:
        self.calls.append(("cancel_order", {"order_id": order_id}))
        return self._maybe_raise(self.cancel_order_response)

    async def batch_cancel_orders(self, order_ids: list[str]) -> dict:
        self.calls.append(("batch_cancel_orders", {"order_ids": order_ids}))
        return self._maybe_raise(self.batch_cancel_response)

    async def get_orderbook(self, ticker: str) -> dict:
        self.calls.append(("get_orderbook", {"ticker": ticker}))
        return self.orderbook_response

    async def get_orders(self, **kwargs: Any) -> dict:
        self.calls.append(("get_orders", kwargs))
        return self.orders_response

    async def get_positions(self, **kwargs: Any) -> dict:
        self.calls.append(("get_positions", kwargs))
        return self.positions_response

    async def get_balance(self) -> dict:
        self.calls.append(("get_balance", {}))
        return self.balance_response


def _adapter() -> tuple[KalshiExchangeAdapter, FakeKalshiClient]:
    fake = FakeKalshiClient()
    adapter = KalshiExchangeAdapter.from_client(fake)  # type: ignore[arg-type]
    return adapter, fake


# ── Protocol satisfaction ─────────────────────────────────────────────


def test_satisfies_exchange_client_protocol() -> None:
    adapter, _ = _adapter()
    assert isinstance(adapter, ExchangeClient)


# ── place_order ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_place_order_happy_path() -> None:
    adapter, fake = _adapter()
    fake.create_order_response = {
        "order": {
            "order_id": "abc-123",
            "ticker": "KX-T50",
            "action": "buy",
            "side": "yes",
            "yes_price": 44,
            "remaining_count": 10,
            "status": "resting",
        }
    }
    req = PlaceOrderRequest(
        ticker="KX-T50", action="buy", side="yes",
        count=10, limit_price_cents=44,
    )
    order = await adapter.place_order(req)
    assert isinstance(order, Order)
    assert order.order_id == "abc-123"
    assert order.limit_price_cents == 44
    assert order.remaining_count == 10
    # Adapter should NOT have sent time_in_force (Kalshi 400s on it)
    place_call = [c for c in fake.calls if c[0] == "create_order"][0][1]
    assert "time_in_force" not in place_call


@pytest.mark.asyncio
async def test_place_order_400_returns_none() -> None:
    adapter, fake = _adapter()
    fake.create_order_response = KalshiResponseError(
        "post-only would cross", status_code=400, body="cross",
    )
    req = PlaceOrderRequest(
        ticker="KX-T50", action="buy", side="yes",
        count=10, limit_price_cents=44,
    )
    result = await adapter.place_order(req)
    assert result is None


@pytest.mark.asyncio
async def test_place_order_500_re_raises() -> None:
    adapter, fake = _adapter()
    fake.create_order_response = KalshiResponseError(
        "server error", status_code=503, body="boom",
    )
    req = PlaceOrderRequest(
        ticker="KX-T50", action="buy", side="yes",
        count=10, limit_price_cents=44,
    )
    with pytest.raises(KalshiResponseError):
        await adapter.place_order(req)


@pytest.mark.asyncio
async def test_place_order_uses_request_overrides_when_response_omits_fields() -> None:
    """create_order responses sometimes omit fields. Adapter falls back to
    request values for ticker/action/side/limit/count."""
    adapter, fake = _adapter()
    # Minimal response — only order_id present
    fake.create_order_response = {"order": {"order_id": "x-1"}}
    req = PlaceOrderRequest(
        ticker="KX-T75", action="sell", side="yes",
        count=5, limit_price_cents=80,
    )
    order = await adapter.place_order(req)
    assert order is not None
    assert order.ticker == "KX-T75"
    assert order.action == "sell"
    assert order.side == "yes"
    assert order.limit_price_cents == 80
    assert order.remaining_count == 5


# ── amend_order ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_amend_order_happy_path() -> None:
    adapter, fake = _adapter()
    fake.amend_order_response = {
        "order": {
            "order_id": "abc-123",
            "ticker": "KX-T50",
            "action": "buy",
            "side": "yes",
            "yes_price": 45,
            "remaining_count": 10,
            "status": "resting",
        }
    }
    order = await adapter.amend_order(
        "abc-123", new_limit_price_cents=45, new_count=10,
    )
    assert isinstance(order, Order)
    assert order.limit_price_cents == 45


@pytest.mark.asyncio
async def test_amend_order_400_returns_none() -> None:
    """Kalshi 400s on amend frequently. Caller falls back to cancel+place."""
    adapter, fake = _adapter()
    fake.amend_order_response = KalshiResponseError(
        "amend not allowed", status_code=400, body="",
    )
    result = await adapter.amend_order("abc-123", new_limit_price_cents=45)
    assert result is None


# ── cancel_order ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_order_happy_path() -> None:
    adapter, _ = _adapter()
    result = await adapter.cancel_order("abc-123")
    assert result is True


@pytest.mark.asyncio
async def test_cancel_order_404_returns_false() -> None:
    """404 = order already gone; protocol contract returns False (not raise)."""
    adapter, fake = _adapter()
    fake.cancel_order_response = KalshiResponseError(
        "not found", status_code=404, body="gone",
    )
    result = await adapter.cancel_order("abc-123")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_order_500_re_raises() -> None:
    adapter, fake = _adapter()
    fake.cancel_order_response = KalshiResponseError(
        "server error", status_code=503, body="boom",
    )
    with pytest.raises(KalshiResponseError):
        await adapter.cancel_order("abc-123")


# ── cancel_orders (batch) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_orders_batch_happy_path() -> None:
    adapter, fake = _adapter()
    # Batch succeeds; verify-orders-resting returns empty → all succeeded
    fake.batch_cancel_response = {}
    fake.orders_response = {"orders": []}
    result = await adapter.cancel_orders(["a", "b", "c"])
    assert result == {"a": True, "b": True, "c": True}


@pytest.mark.asyncio
async def test_cancel_orders_batch_failure_falls_back_to_per_order() -> None:
    """Batch endpoint errors → adapter falls back to per-order cancels."""
    adapter, fake = _adapter()
    fake.batch_cancel_response = KalshiResponseError(
        "batch unavailable", status_code=500, body="",
    )
    # Per-order cancels succeed
    result = await adapter.cancel_orders(["a", "b"])
    assert result == {"a": True, "b": True}
    # Verify per-order cancels were called
    cancel_calls = [c for c in fake.calls if c[0] == "cancel_order"]
    assert len(cancel_calls) == 2


@pytest.mark.asyncio
async def test_cancel_orders_empty_list_returns_empty_dict() -> None:
    adapter, _ = _adapter()
    assert await adapter.cancel_orders([]) == {}


@pytest.mark.asyncio
async def test_cancel_orders_batch_silent_partial_success_caught() -> None:
    """If batch returns 200 but verify shows leftovers, those map to False."""
    adapter, fake = _adapter()
    fake.batch_cancel_response = {}
    # Simulate that order "a" survived the batch
    fake.orders_response = {
        "orders": [{"order_id": "a", "ticker": "X", "action": "buy",
                    "side": "yes", "yes_price": 50, "remaining_count": 5,
                    "status": "resting"}],
    }
    result = await adapter.cancel_orders(["a", "b"])
    assert result == {"a": False, "b": True}


# ── get_orderbook ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_orderbook_parses_depth_and_sorts_highest_first() -> None:
    adapter, fake = _adapter()
    fake.orderbook_response = {
        "orderbook_fp": {
            "yes_dollars": [["0.45", "100"], ["0.46", "50"], ["0.44", "200"]],
            "no_dollars": [["0.55", "30"]],
        },
    }
    ob = await adapter.get_orderbook("KX-T50")
    assert isinstance(ob, OrderbookLevels)
    # Sorted highest-first
    assert ob.yes_levels == [(46, 50.0), (45, 100.0), (44, 200.0)]
    assert ob.no_levels == [(55, 30.0)]


@pytest.mark.asyncio
async def test_get_orderbook_handles_missing_data() -> None:
    adapter, fake = _adapter()
    fake.orderbook_response = {}  # no orderbook_fp at all
    ob = await adapter.get_orderbook("KX-T50")
    assert ob.yes_levels == []
    assert ob.no_levels == []


# ── list_resting_orders ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_resting_orders_parses_each() -> None:
    adapter, fake = _adapter()
    fake.orders_response = {
        "orders": [
            {"order_id": "a", "ticker": "KX-T50", "action": "buy",
             "side": "yes", "yes_price": 44, "remaining_count": 10,
             "status": "resting"},
            {"order_id": "b", "ticker": "KX-T50", "action": "sell",
             "side": "yes", "yes_price": 56, "remaining_count": 10,
             "status": "resting"},
        ],
    }
    orders = await adapter.list_resting_orders()
    assert len(orders) == 2
    assert orders[0].order_id == "a"
    assert orders[0].action == "buy"
    assert orders[1].order_id == "b"
    assert orders[1].action == "sell"


# ── list_positions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_positions_parses_position_fp_float_string() -> None:
    """Kalshi returns position_fp as a float-formatted string like '11.00'.
    Adapter parses → int (rounded)."""
    adapter, fake = _adapter()
    fake.positions_response = {
        "market_positions": [
            {"ticker": "KX-T50", "position_fp": "11.00",
             "average_cost_cents": 44, "realized_pnl_dollars": 1.50,
             "fees_paid_dollars": 0.05},
            {"ticker": "KX-T75", "position_fp": "-5.00",
             "average_cost_cents": 25, "realized_pnl_dollars": 0.0,
             "fees_paid_dollars": 0.0},
        ],
    }
    positions = await adapter.list_positions()
    assert len(positions) == 2
    assert positions[0].quantity == 11
    assert positions[0].avg_cost_cents == 44
    assert positions[1].quantity == -5


@pytest.mark.asyncio
async def test_list_positions_filters_zero_positions() -> None:
    adapter, fake = _adapter()
    fake.positions_response = {
        "market_positions": [
            {"ticker": "KX-T50", "position_fp": "0.00"},
            {"ticker": "KX-T75", "position_fp": "10.00",
             "average_cost_cents": 25, "realized_pnl_dollars": 0,
             "fees_paid_dollars": 0},
        ],
    }
    positions = await adapter.list_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "KX-T75"


# ── get_balance ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_converts_cents_to_dollars() -> None:
    adapter, fake = _adapter()
    fake.balance_response = {"balance": 9588, "portfolio_value": 4310}
    bal = await adapter.get_balance()
    assert bal.cash_dollars == 95.88
    assert bal.portfolio_value_dollars == 43.10


@pytest.mark.asyncio
async def test_get_balance_handles_missing_fields() -> None:
    adapter, fake = _adapter()
    fake.balance_response = {}
    bal = await adapter.get_balance()
    assert bal.cash_dollars == 0.0
    assert bal.portfolio_value_dollars == 0.0
