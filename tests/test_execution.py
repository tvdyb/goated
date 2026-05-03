"""Tests for lipmm.execution: ExchangeClient protocol + OrderManager."""

from __future__ import annotations

import time
from typing import Any

import pytest

from lipmm.execution import (
    Balance,
    ExchangeClient,
    Order,
    OrderbookLevels,
    OrderManager,
    PlaceOrderRequest,
    Position,
    RestingOrder,
)
from lipmm.quoting import SideDecision


# ── A minimal in-memory exchange for tests ────────────────────────────


class MockExchange:
    """Minimal in-memory ExchangeClient for tests.

    Supports configurable rejection of place / amend operations so tests
    can exercise the OrderManager's fallback paths.
    """

    def __init__(
        self, *,
        reject_amend: bool = False,
        reject_place: bool = False,
        reject_cancel: bool = False,
    ) -> None:
        self.orders: dict[str, Order] = {}
        self.next_id = 1
        self.reject_amend = reject_amend
        self.reject_place = reject_place
        self.reject_cancel = reject_cancel
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        self.calls.append(("place", {"request": request}))
        if self.reject_place:
            return None
        oid = f"o-{self.next_id}"
        self.next_id += 1
        order = Order(
            order_id=oid,
            ticker=request.ticker,
            action=request.action,
            side=request.side,
            limit_price_cents=request.limit_price_cents,
            remaining_count=request.count,
            status="resting",
        )
        self.orders[oid] = order
        return order

    async def amend_order(
        self, order_id: str, *,
        new_limit_price_cents: int | None = None,
        new_count: int | None = None,
    ) -> Order | None:
        self.calls.append(("amend", {
            "order_id": order_id,
            "new_limit_price_cents": new_limit_price_cents,
            "new_count": new_count,
        }))
        if self.reject_amend:
            return None
        if order_id not in self.orders:
            return None
        existing = self.orders[order_id]
        updated = Order(
            order_id=existing.order_id,
            ticker=existing.ticker,
            action=existing.action,
            side=existing.side,
            limit_price_cents=new_limit_price_cents or existing.limit_price_cents,
            remaining_count=new_count or existing.remaining_count,
            status="resting",
        )
        self.orders[order_id] = updated
        return updated

    async def cancel_order(self, order_id: str) -> bool:
        self.calls.append(("cancel", {"order_id": order_id}))
        if self.reject_cancel:
            return False
        return self.orders.pop(order_id, None) is not None

    async def cancel_orders(self, order_ids: list[str]) -> dict[str, bool]:
        return {oid: await self.cancel_order(oid) for oid in order_ids}

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        return OrderbookLevels(ticker=ticker, yes_levels=[], no_levels=[])

    async def list_resting_orders(self) -> list[Order]:
        return list(self.orders.values())

    async def list_positions(self) -> list[Position]:
        return []

    async def get_balance(self) -> Balance:
        return Balance(cash_dollars=100.0, portfolio_value_dollars=0.0)


# ── Protocol shape ────────────────────────────────────────────────────


def test_mock_exchange_satisfies_protocol() -> None:
    assert isinstance(MockExchange(), ExchangeClient)


def test_place_order_request_is_frozen() -> None:
    req = PlaceOrderRequest(
        ticker="X", action="buy", side="yes", count=10,
        limit_price_cents=50,
    )
    with pytest.raises(Exception):
        req.count = 20  # type: ignore


# ── OrderManager: place-new path ──────────────────────────────────────


def _bid_decision(price: int, size: int, **kw: Any) -> SideDecision:
    return SideDecision(price=price, size=size, skip=False,
                        reason=kw.get("reason", "test"))


@pytest.mark.asyncio
async def test_apply_places_new_when_no_resting() -> None:
    om = OrderManager()
    ex = MockExchange()
    out = await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    assert out.action == "place_new"
    assert out.order_id is not None
    assert out.price_cents == 45
    assert out.size == 10
    # Internal state updated
    cur = om.get_resting("KX-T50", "bid")
    assert cur is not None
    assert cur.price_cents == 45


@pytest.mark.asyncio
async def test_apply_no_change_when_decision_matches_resting() -> None:
    om = OrderManager()
    ex = MockExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    out2 = await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    assert out2.action == "no_change"
    # Only one place call was made
    assert sum(1 for c, _ in ex.calls if c == "place") == 1


# ── OrderManager: amend path ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_amends_when_decision_changes() -> None:
    om = OrderManager()
    ex = MockExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    out2 = await om.apply("KX-T50", "bid", _bid_decision(46, 10), ex)
    assert out2.action == "amend"
    assert out2.price_cents == 46
    assert sum(1 for c, _ in ex.calls if c == "amend") == 1


@pytest.mark.asyncio
async def test_amend_failure_falls_back_to_cancel_replace() -> None:
    om = OrderManager()
    ex = MockExchange(reject_amend=True)
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    out2 = await om.apply("KX-T50", "bid", _bid_decision(46, 10), ex)
    assert out2.action == "cancel_and_replace"
    assert out2.price_cents == 46
    # Should have called: place, amend, cancel, place
    actions = [c for c, _ in ex.calls]
    assert "amend" in actions
    assert "cancel" in actions
    assert actions.count("place") == 2


# ── OrderManager: skip / cooldown path ────────────────────────────────


@pytest.mark.asyncio
async def test_skip_decision_cancels_existing() -> None:
    om = OrderManager()
    ex = MockExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    skip = SideDecision(price=0, size=0, skip=True, reason="cooldown")
    out2 = await om.apply("KX-T50", "bid", skip, ex)
    assert out2.action == "cancel"
    assert om.get_resting("KX-T50", "bid") is None


@pytest.mark.asyncio
async def test_skip_when_no_resting_is_no_op() -> None:
    om = OrderManager()
    ex = MockExchange()
    skip = SideDecision(price=0, size=0, skip=True, reason="cooldown")
    out = await om.apply("KX-T50", "bid", skip, ex)
    assert out.action == "skipped"


# ── Place rejection (post-only cross, insufficient funds, etc.) ───────


@pytest.mark.asyncio
async def test_place_rejection_returns_place_failed() -> None:
    om = OrderManager()
    ex = MockExchange(reject_place=True)
    out = await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    assert out.action == "place_failed"
    assert out.order_id is None
    assert om.get_resting("KX-T50", "bid") is None


# ── Reconcile from exchange truth ─────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_populates_state_from_exchange() -> None:
    ex = MockExchange()
    # Simulate exchange has 2 pre-existing orders
    await ex.place_order(PlaceOrderRequest(
        ticker="KX-T50", action="buy", side="yes",
        count=10, limit_price_cents=45,
    ))
    await ex.place_order(PlaceOrderRequest(
        ticker="KX-T50", action="sell", side="yes",
        count=10, limit_price_cents=55,
    ))

    om = OrderManager()
    await om.reconcile(ex)

    bid = om.get_resting("KX-T50", "bid")
    ask = om.get_resting("KX-T50", "ask")
    assert bid is not None and bid.price_cents == 45
    assert ask is not None and ask.price_cents == 55


# ── Per-side independence ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bid_and_ask_tracked_independently() -> None:
    om = OrderManager()
    ex = MockExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    await om.apply(
        "KX-T50", "ask",
        SideDecision(price=55, size=10, skip=False, reason=""), ex,
    )
    assert om.get_resting("KX-T50", "bid").price_cents == 45
    assert om.get_resting("KX-T50", "ask").price_cents == 55


# ── Latency captured ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_latency_recorded_in_execution() -> None:
    om = OrderManager()
    ex = MockExchange()
    out = await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    # Should be a small but non-negative number; mock is fast
    assert out.latency_ms >= 0
    assert out.latency_ms < 1000  # mock should be sub-second


# ── Cross-ticker isolation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_isolated_per_ticker() -> None:
    om = OrderManager()
    ex = MockExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    await om.apply("KX-T75", "bid", _bid_decision(70, 10), ex)
    assert om.get_resting("KX-T50", "bid").price_cents == 45
    assert om.get_resting("KX-T75", "bid").price_cents == 70


# ── Idempotency on transient failure ──────────────────────────────────


@pytest.mark.asyncio
async def test_amend_exception_falls_back_to_cancel_replace() -> None:
    """If amend raises (transient API error), bot should still recover."""
    class FlakyExchange(MockExchange):
        async def amend_order(self, *args, **kwargs):
            raise RuntimeError("transient")

    om = OrderManager()
    ex = FlakyExchange()
    await om.apply("KX-T50", "bid", _bid_decision(45, 10), ex)
    out2 = await om.apply("KX-T50", "bid", _bid_decision(46, 10), ex)
    # Either cancel_and_replace or place_failed, but not exception
    assert out2.action in ("cancel_and_replace", "place_failed")
