"""End-to-end tests: LIPRunner with a ControlState wired in.

Verifies the runner honors:
  - Global pause (no orders placed at all)
  - Ticker pause (orders only on non-paused tickers)
  - Side pause (only the non-paused side gets quoted)
  - Kill (cancel-all + skip cycles)
  - Knob overrides (next cycle's strategy sees the override)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from lipmm.control import ControlState
from lipmm.execution import (
    Balance,
    ExchangeClient,
    Order,
    OrderbookLevels,
    OrderManager,
    PlaceOrderRequest,
    Position,
)
from lipmm.quoting.strategies.default import DefaultLIPQuoting, DefaultLIPQuotingConfig
from lipmm.runner import LIPRunner, RunnerConfig
from lipmm.theo import TheoRegistry, TheoResult


class _MockExchange:
    def __init__(self, books: dict[str, OrderbookLevels]) -> None:
        self.books = books
        self.orders: dict[str, Order] = {}
        self.next_id = 1

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        oid = f"o-{self.next_id}"
        self.next_id += 1
        self.orders[oid] = Order(
            order_id=oid, ticker=request.ticker, action=request.action,
            side=request.side, limit_price_cents=request.limit_price_cents,
            remaining_count=request.count, status="resting",
        )
        return self.orders[oid]

    async def amend_order(self, order_id, *, new_limit_price_cents=None, new_count=None):
        if order_id not in self.orders:
            return None
        o = self.orders[order_id]
        self.orders[order_id] = Order(
            order_id=o.order_id, ticker=o.ticker, action=o.action, side=o.side,
            limit_price_cents=new_limit_price_cents or o.limit_price_cents,
            remaining_count=new_count or o.remaining_count, status="resting",
        )
        return self.orders[order_id]

    async def cancel_order(self, order_id: str) -> bool:
        return self.orders.pop(order_id, None) is not None

    async def cancel_orders(self, order_ids):
        return {oid: await self.cancel_order(oid) for oid in order_ids}

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        return self.books.get(ticker) or OrderbookLevels(
            ticker=ticker, yes_levels=[], no_levels=[],
        )

    async def list_resting_orders(self) -> list[Order]:
        return list(self.orders.values())

    async def list_positions(self) -> list[Position]:
        return []

    async def get_balance(self) -> Balance:
        return Balance(cash_dollars=100.0, portfolio_value_dollars=0.0)


class _StaticTickerSource:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers
    async def list_active_tickers(self, exchange: ExchangeClient) -> list[str]:
        return list(self._tickers)


class _FixedTheo:
    def __init__(self, prefix: str, prob: float, confidence: float = 1.0) -> None:
        self.series_prefix = prefix
        self._prob = prob
        self._conf = confidence
    async def warmup(self) -> None: pass
    async def shutdown(self) -> None: pass
    async def theo(self, ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=self._prob, confidence=self._conf,
            computed_at=time.time(), source="fixed",
        )


def _make_runner(
    *,
    tickers: list[str],
    book_for: dict[str, OrderbookLevels],
    theo_prob: float,
    confidence: float = 1.0,
    control_state: ControlState | None = None,
) -> tuple[LIPRunner, _MockExchange]:
    ex = _MockExchange(book_for)
    reg = TheoRegistry()
    prefix = tickers[0].split("-", 1)[0] if tickers else "KX"
    reg.register(_FixedTheo(prefix, theo_prob, confidence))
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=reg,
        strategy=DefaultLIPQuoting(DefaultLIPQuotingConfig(
            min_theo_confidence=0.05,  # low so default theo confidence doesn't block
        )),
        order_manager=OrderManager(),
        exchange=ex,
        ticker_source=_StaticTickerSource(tickers),
        control_state=control_state,
    )
    return runner, ex


async def _run_for(runner: LIPRunner, seconds: float) -> None:
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(seconds)
    runner.stop()
    await asyncio.wait_for(task, timeout=2.0)


# ── 1. No control state → behaves as before ─────────────────────────


@pytest.mark.asyncio
async def test_runner_without_control_state_unchanged() -> None:
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=None,
    )
    await _run_for(runner, 0.15)
    assert any(o.action == "buy" for o in ex.orders.values())
    assert any(o.action == "sell" for o in ex.orders.values())


# ── 2. Global pause → no orders ─────────────────────────────────────


@pytest.mark.asyncio
async def test_global_pause_blocks_all_orders() -> None:
    cs = ControlState()
    await cs.pause_global()
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    assert len(ex.orders) == 0


# ── 3. Ticker pause → other tickers unaffected ──────────────────────


@pytest.mark.asyncio
async def test_ticker_pause_isolates_to_one_ticker() -> None:
    cs = ControlState()
    await cs.pause_ticker("KX-T50.00")
    books = {
        "KX-T50.00": OrderbookLevels(
            ticker="KX-T50.00",
            yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
        ),
        "KX-T75.00": OrderbookLevels(
            ticker="KX-T75.00",
            yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
        ),
    }
    runner, ex = _make_runner(
        tickers=list(books.keys()),
        book_for=books,
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # Only KX-T75.00 should have orders
    tickers_with_orders = {o.ticker for o in ex.orders.values()}
    assert "KX-T75.00" in tickers_with_orders
    assert "KX-T50.00" not in tickers_with_orders


# ── 4. Side pause → only the non-paused side ────────────────────────


@pytest.mark.asyncio
async def test_side_pause_blocks_one_side_only() -> None:
    cs = ControlState()
    await cs.pause_side("KX-T50.00", "bid")
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # No buys (bid paused). At least one sell (ask).
    buys = [o for o in ex.orders.values() if o.action == "buy"]
    sells = [o for o in ex.orders.values() if o.action == "sell"]
    assert len(buys) == 0
    assert len(sells) > 0


# ── 5. Kill → cancel-all + halt ─────────────────────────────────────


@pytest.mark.asyncio
async def test_kill_handler_cancels_all_resting() -> None:
    cs = ControlState()
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    # Let the runner place orders first
    await _run_for(runner, 0.10)
    initial_count = len(ex.orders)
    assert initial_count > 0

    # Now invoke the runner's cancel_all_resting (this is what /control/kill
    # would call as kill_handler after setting state.is_killed=True)
    cancelled = await runner.cancel_all_resting()
    assert cancelled > 0
    assert len(ex.orders) == 0


@pytest.mark.asyncio
async def test_killed_state_skips_all_cycles() -> None:
    cs = ControlState()
    await cs.kill()
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # No orders should have been placed
    assert len(ex.orders) == 0


# ── 6. Knob overrides reach the strategy ────────────────────────────


@pytest.mark.asyncio
async def test_knob_override_reaches_strategy() -> None:
    """Set min_theo_confidence override via control plane → strategy
    sees the override and skips when confidence below it."""
    cs = ControlState()
    # Confidence floor of 0.9; supplied theo has 0.5 confidence → skip
    await cs.set_knob("min_theo_confidence", 0.9)

    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        confidence=0.5,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # Strategy should have skipped both sides every cycle → no orders
    assert len(ex.orders) == 0


# ── 7. Side locks affect the runner the same way as side pauses ────


@pytest.mark.asyncio
async def test_side_lock_blocks_one_side() -> None:
    """A SideLock has the same runner-side effect as a pause: skip=True
    on the locked side, with a reason that mentions the lock."""
    cs = ControlState()
    await cs.lock_side("KX-T50.00", "bid", reason="manual buy hold")
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    buys = [o for o in ex.orders.values() if o.action == "buy"]
    sells = [o for o in ex.orders.values() if o.action == "sell"]
    assert len(buys) == 0   # bid locked → no buys
    assert len(sells) > 0   # ask unaffected


@pytest.mark.asyncio
async def test_side_lock_does_NOT_cancel_existing_resting_order() -> None:
    """Critical post-Phase-11 fix: a locked side must leave any existing
    resting order on the book. Before this fix, the runner forced
    skip=True on locked sides, which made OrderManager cancel the
    resting order on the next cycle — silently undoing manual orders.
    Now the runner bypasses OrderManager entirely for locked sides."""
    from lipmm.execution.order_manager import RestingOrder

    cs = ControlState()
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    # Pre-seed a manual resting order on KX-T50.00 bid (as if the
    # operator just placed one) AND lock that side so the runner has
    # to leave it alone.
    runner._om._resting[("KX-T50.00", "bid")] = RestingOrder(  # noqa: SLF001
        order_id="manual-order-1", price_cents=44, size=10,
    )
    ex.orders["manual-order-1"] = Order(
        order_id="manual-order-1", ticker="KX-T50.00", action="buy",
        side="yes", limit_price_cents=44, remaining_count=10, status="resting",
    )
    await cs.lock_side("KX-T50.00", "bid", reason="manual order placed")

    await _run_for(runner, 0.20)

    # The manual order survives — runner did not cancel it.
    assert "manual-order-1" in ex.orders
    # And the OrderManager's internal state still tracks it.
    assert runner._om.get_resting("KX-T50.00", "bid") is not None  # noqa: SLF001
    assert runner._om.get_resting("KX-T50.00", "bid").order_id == "manual-order-1"  # noqa: SLF001


@pytest.mark.asyncio
async def test_side_pause_DOES_cancel_existing_resting_order() -> None:
    """Sanity counter-test: a paused side (vs. locked) still goes
    through OrderManager and DOES cancel any existing order. That's
    the documented difference: lock = hands-off, pause = halt-and-pull."""
    from lipmm.execution.order_manager import RestingOrder

    cs = ControlState()
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    runner._om._resting[("KX-T50.00", "bid")] = RestingOrder(  # noqa: SLF001
        order_id="strat-order-1", price_cents=44, size=10,
    )
    ex.orders["strat-order-1"] = Order(
        order_id="strat-order-1", ticker="KX-T50.00", action="buy",
        side="yes", limit_price_cents=44, remaining_count=10, status="resting",
    )
    await cs.pause_side("KX-T50.00", "bid")

    await _run_for(runner, 0.20)

    # Pause path: order was cancelled (action= cancel branch in OM)
    assert "strat-order-1" not in ex.orders


@pytest.mark.asyncio
async def test_side_lock_auto_unlocks_after_ttl() -> None:
    """A lock with auto_unlock_at in the past is treated as not locked
    on the next runner check — and the lock is lazily cleared from state."""
    import time as _t
    cs = ControlState()
    # Lock with expiry already in the past
    await cs.lock_side("KX-T50.00", "bid",
                       auto_unlock_at=_t.time() - 1)
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # Bot should have placed bids despite the (expired) lock
    buys = [o for o in ex.orders.values() if o.action == "buy"]
    assert len(buys) > 0
    # And the expired lock has been cleared from state
    assert cs.get_side_lock("KX-T50.00", "bid") is None


@pytest.mark.asyncio
async def test_no_knob_override_uses_strategy_default() -> None:
    """Sanity: same scenario without the knob override → strategy uses
    its configured default (0.05) and quotes normally."""
    cs = ControlState()  # no knob set

    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        confidence=0.5,
        control_state=cs,
    )
    await _run_for(runner, 0.15)
    # Strategy default min_theo_confidence=0.05 < 0.5 → orders placed
    assert len(ex.orders) > 0
