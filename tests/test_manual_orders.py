"""Tests for the manual_orders module — synthesize, risk-check, execute.

Uses an in-memory mock exchange + real OrderManager + optional RiskRegistry
to exercise every code path of submit_manual_order.
"""

from __future__ import annotations

from typing import Any

import pytest

from lipmm.control import ControlState, submit_manual_order
from lipmm.control.manual_orders import ManualOrderOutcome
from lipmm.execution import (
    Balance, ExchangeClient, Order, OrderbookLevels, OrderManager,
    PlaceOrderRequest, Position,
)
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    RiskRegistry,
)


# ── mock exchange ────────────────────────────────────────────────────


class _MockExchange:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.next_id = 1
        self.reject_place = False

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        if self.reject_place:
            return None
        oid = f"o-{self.next_id}"
        self.next_id += 1
        self.orders[oid] = Order(
            order_id=oid, ticker=request.ticker, action=request.action,
            side=request.side, limit_price_cents=request.limit_price_cents,
            remaining_count=request.count, status="resting",
        )
        return self.orders[oid]

    async def amend_order(self, order_id, **kwargs):
        return self.orders.get(order_id)

    async def cancel_order(self, order_id: str) -> bool:
        return self.orders.pop(order_id, None) is not None

    async def cancel_orders(self, order_ids):
        return {oid: await self.cancel_order(oid) for oid in order_ids}

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        return OrderbookLevels(ticker=ticker, yes_levels=[], no_levels=[])

    async def list_resting_orders(self) -> list[Order]:
        return list(self.orders.values())

    async def list_positions(self) -> list[Position]:
        return []

    async def get_balance(self) -> Balance:
        return Balance(cash_dollars=100.0, portfolio_value_dollars=0.0)


# ── happy path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_buy_places_order() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=44,
    )
    assert isinstance(out, ManualOrderOutcome)
    assert out.succeeded is True
    assert out.risk_vetoed is False
    assert out.execution.action == "place_new"
    assert out.execution.price_cents == 44
    assert out.execution.size == 10
    # Exchange has the order
    assert len(ex.orders) == 1
    # OrderManager tracks it
    assert om.get_resting("KX-T50", "bid") is not None


@pytest.mark.asyncio
async def test_manual_sell_places_order() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="ask", count=5, limit_price_cents=70,
    )
    assert out.succeeded is True
    placed = list(ex.orders.values())[0]
    assert placed.action == "sell"
    assert placed.limit_price_cents == 70


# ── input validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_side_raises() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    with pytest.raises(ValueError):
        await submit_manual_order(
            state=state, order_manager=om, exchange=ex, risk_registry=None,
            ticker="X", side="invalid",  # type: ignore[arg-type]
            count=10, limit_price_cents=50,
        )


@pytest.mark.asyncio
async def test_invalid_count_raises() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    with pytest.raises(ValueError):
        await submit_manual_order(
            state=state, order_manager=om, exchange=ex, risk_registry=None,
            ticker="X", side="bid", count=0, limit_price_cents=50,
        )


@pytest.mark.asyncio
async def test_invalid_price_raises() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    with pytest.raises(ValueError):
        await submit_manual_order(
            state=state, order_manager=om, exchange=ex, risk_registry=None,
            ticker="X", side="bid", count=10, limit_price_cents=100,
        )
    with pytest.raises(ValueError):
        await submit_manual_order(
            state=state, order_manager=om, exchange=ex, risk_registry=None,
            ticker="X", side="bid", count=10, limit_price_cents=0,
        )


# ── risk gate integration ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_risk_gate_vetoes_oversized_manual_order() -> None:
    """A MaxNotionalPerSideGate configured at $1 vetoes a $5 manual order."""
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    risk = RiskRegistry([MaxNotionalPerSideGate(max_dollars=1.0)])
    # Bid 50c × 10 = $5 notional → vetoed
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=risk,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=50,
    )
    assert out.succeeded is False
    assert out.risk_vetoed is True
    assert out.execution.action == "skipped"
    assert "risk vetoed" in out.execution.reason
    # Risk audit captures the gate's verdict
    assert any(a["gate"] == "MaxNotionalPerSideGate" for a in out.risk_audit)
    # No order on the exchange
    assert len(ex.orders) == 0


@pytest.mark.asyncio
async def test_risk_gate_allows_within_budget() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    risk = RiskRegistry([MaxNotionalPerSideGate(max_dollars=10.0)])
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=risk,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=50,
    )
    assert out.succeeded is True
    assert out.risk_vetoed is False
    assert len(ex.orders) == 1


@pytest.mark.asyncio
async def test_endgame_gate_does_not_block_manual_orders() -> None:
    """The neutral theo (confidence=0) means EndgameGuardrailGate's
    theo-aware logic doesn't fire on manual orders. Operators get to
    place wing orders even near settle (they assume the responsibility)."""
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    # EndgameGuardrailGate normally vetoes deep-OTM bids near settle. But:
    # manual order's theo is neutral (yes_prob=0.5), so the gate's
    # theo_yes <= deep_otm check doesn't trip.
    risk = RiskRegistry([
        EndgameGuardrailGate(min_seconds_to_settle=3600,
                             deep_otm_threshold=10, deep_itm_threshold=90),
    ])
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=risk,
        ticker="KX-T1196.99", side="bid", count=10, limit_price_cents=2,
    )
    # Allowed despite being a small bid (which would normally be blocked
    # by endgame gate during a deep-OTM regime).
    assert out.succeeded is True


# ── exchange rejection ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_rejection_returns_failure() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    ex.reject_place = True
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=44,
    )
    assert out.succeeded is False
    assert out.risk_vetoed is False
    assert out.execution.action == "place_failed"


# ── lock_after semantics ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_after_locks_side_on_success() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=44,
        lock_after=True,
    )
    assert out.succeeded is True
    assert out.lock_applied is True
    assert state.is_side_locked("KX-T50", "bid") is True
    # Lock has the right reason
    lock = state.get_side_lock("KX-T50", "bid")
    assert lock is not None
    assert "auto-locked" in lock.reason


@pytest.mark.asyncio
async def test_lock_after_with_ttl_sets_auto_unlock() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=44,
        lock_after=True, lock_auto_unlock_seconds=3600,
    )
    assert out.lock_applied is True
    assert out.lock_auto_unlock_at is not None
    lock = state.get_side_lock("KX-T50", "bid")
    assert lock.auto_unlock_at is not None
    # Within seconds of "now + 3600"
    import time
    assert abs(lock.auto_unlock_at - (time.time() + 3600)) < 5


@pytest.mark.asyncio
async def test_lock_after_skipped_on_risk_veto() -> None:
    """If the manual order is risk-vetoed, the side is NOT locked.
    Locking only on success — operator may want to retry."""
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    risk = RiskRegistry([MaxNotionalPerSideGate(max_dollars=0.50)])
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=risk,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=50,
        lock_after=True,
    )
    assert out.succeeded is False
    assert out.lock_applied is False
    assert state.is_side_locked("KX-T50", "bid") is False


@pytest.mark.asyncio
async def test_lock_after_skipped_on_exchange_rejection() -> None:
    state = ControlState()
    om = OrderManager()
    ex = _MockExchange()
    ex.reject_place = True
    out = await submit_manual_order(
        state=state, order_manager=om, exchange=ex, risk_registry=None,
        ticker="KX-T50", side="bid", count=10, limit_price_cents=44,
        lock_after=True,
    )
    assert out.succeeded is False
    assert out.lock_applied is False
    assert state.is_side_locked("KX-T50", "bid") is False
