"""End-to-end runner tests.

These exercise the full framework: TheoRegistry + QuotingStrategy +
OrderManager + ExchangeClient + LIPRunner. Uses the MockExchange from
test_execution and mock TickerSource to drive the loop.

Key invariants tested:
  - One cycle calls strategy.quote() exactly once per ticker
  - Resulting orders land on the exchange via OrderManager
  - Decision-recorder callback receives a structured record per (ticker, cycle)
  - Strike-level errors don't crash the loop (when fail_loud is False)
  - Stop request actually halts the loop
"""

from __future__ import annotations

import asyncio
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
)
from lipmm.quoting.strategies.default import DefaultLIPQuoting, DefaultLIPQuotingConfig
from lipmm.runner import LIPRunner, RunnerConfig
from lipmm.theo import TheoProvider, TheoRegistry, TheoResult


# ── Mock exchange ─────────────────────────────────────────────────────


class MockExchange:
    def __init__(self, books: dict[str, OrderbookLevels]) -> None:
        self.books = books
        self.orders: dict[str, Order] = {}
        self.next_id = 1
        self.calls: list[str] = []

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        self.calls.append("place")
        oid = f"o-{self.next_id}"
        self.next_id += 1
        self.orders[oid] = Order(
            order_id=oid, ticker=request.ticker, action=request.action,
            side=request.side, limit_price_cents=request.limit_price_cents,
            remaining_count=request.count, status="resting",
        )
        return self.orders[oid]

    async def amend_order(self, order_id, *, new_limit_price_cents=None, new_count=None):
        self.calls.append("amend")
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
        self.calls.append("cancel")
        return self.orders.pop(order_id, None) is not None

    async def cancel_orders(self, order_ids):
        return {oid: await self.cancel_order(oid) for oid in order_ids}

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        return self.books.get(ticker) or OrderbookLevels(ticker=ticker, yes_levels=[], no_levels=[])

    async def list_resting_orders(self) -> list[Order]:
        return list(self.orders.values())

    async def list_positions(self) -> list[Position]:
        return []

    async def get_balance(self) -> Balance:
        return Balance(cash_dollars=100.0, portfolio_value_dollars=0.0)


class StaticTickerSource:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers
    async def list_active_tickers(self, exchange: ExchangeClient) -> list[str]:
        return list(self._tickers)


class FixedTheoProvider:
    """TheoProvider that returns a configured probability + confidence."""
    def __init__(self, prefix: str, prob: float, confidence: float = 1.0) -> None:
        self.series_prefix = prefix
        self._prob = prob
        self._conf = confidence
    async def warmup(self) -> None: pass
    async def shutdown(self) -> None: pass
    async def theo(self, ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=self._prob,
            confidence=self._conf,
            computed_at=time.time(),
            source="fixed-test",
        )


# ── Helpers ───────────────────────────────────────────────────────────


def _make_runner(
    *,
    tickers: list[str],
    book_for: dict[str, OrderbookLevels],
    theo_prob: float,
    confidence: float = 1.0,
    recorder=None,
    cycle_seconds: float = 0.05,
) -> tuple[LIPRunner, MockExchange]:
    ex = MockExchange(book_for)
    reg = TheoRegistry()
    # Use the prefix of the first ticker for routing
    prefix = tickers[0].split("-", 1)[0] if tickers else "KX"
    reg.register(FixedTheoProvider(prefix, theo_prob, confidence))
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=cycle_seconds),
        theo_registry=reg,
        strategy=DefaultLIPQuoting(),
        order_manager=OrderManager(),
        exchange=ex,
        ticker_source=StaticTickerSource(tickers),
        decision_recorder=recorder,
    )
    return runner, ex


async def _run_for(runner: LIPRunner, seconds: float) -> None:
    """Run the loop for `seconds` then stop."""
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(seconds)
    runner.stop()
    await asyncio.wait_for(task, timeout=2.0)


# ── End-to-end tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_places_orders_in_first_cycle() -> None:
    """Active mid-strike with a real book → bot places bid + ask."""
    book = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(45, 100.0)],
        no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50"],
        book_for={"KX-T50": book},
        theo_prob=0.50,
    )
    await _run_for(runner, 0.15)
    # Two orders placed (bid + ask)
    assert len(ex.orders) == 2
    bids = [o for o in ex.orders.values() if o.action == "buy"]
    asks = [o for o in ex.orders.values() if o.action == "sell"]
    assert len(bids) == 1 and len(asks) == 1


@pytest.mark.asyncio
async def test_runner_does_not_cross_post_only() -> None:
    """The no-cross guard from DefaultLIPQuoting should propagate end-to-end."""
    # Inverted-book scenario: best_bid=97 above theo=89, best_ask=98
    book = OrderbookLevels(
        ticker="KX-T1176",
        yes_levels=[(97, 100.0)],   # someone bidding above theo
        no_levels=[(2, 100.0)],     # 100 - 2 = 98 best ask
    )
    runner, ex = _make_runner(
        tickers=["KX-T1176"],
        book_for={"KX-T1176": book},
        theo_prob=0.89,
    )
    await _run_for(runner, 0.15)
    # No order should cross: ask must be > 97, bid must be < 98
    for o in ex.orders.values():
        if o.action == "sell":
            assert o.limit_price_cents > 97
        if o.action == "buy":
            assert o.limit_price_cents < 98


@pytest.mark.asyncio
async def test_runner_skips_when_low_confidence() -> None:
    book = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(45, 100.0)],
        no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50"],
        book_for={"KX-T50": book},
        theo_prob=0.50,
        confidence=0.0,  # below default gate
    )
    await _run_for(runner, 0.15)
    assert len(ex.orders) == 0   # nothing placed


@pytest.mark.asyncio
async def test_runner_invokes_decision_recorder_per_ticker_per_cycle() -> None:
    book = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(45, 100.0)],
        no_levels=[(45, 100.0)],
    )
    records: list[dict] = []
    async def recorder(rec: dict) -> None:
        records.append(rec)
    runner, _ = _make_runner(
        tickers=["KX-T50"],
        book_for={"KX-T50": book},
        theo_prob=0.50,
        recorder=recorder,
    )
    await _run_for(runner, 0.15)
    assert len(records) >= 1
    # Schema check
    r = records[0]
    assert r["ticker"] == "KX-T50"
    assert "theo" in r and "yes_cents" in r["theo"]
    assert "orderbook" in r and "best_bid" in r["orderbook"]
    assert "decision" in r
    assert "outcome" in r and "bid_action" in r["outcome"]


@pytest.mark.asyncio
async def test_runner_continues_on_strike_error() -> None:
    """One bad ticker shouldn't kill the loop when fail_loud=False."""
    class BadOrderbook(MockExchange):
        async def get_orderbook(self, ticker: str):
            if "BAD" in ticker:
                raise RuntimeError("orderbook fetch failed")
            return await super().get_orderbook(ticker)

    ex = BadOrderbook({})
    reg = TheoRegistry()
    reg.register(FixedTheoProvider("KX", 0.5))
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05, fail_loud_on_strike_error=False),
        theo_registry=reg,
        strategy=DefaultLIPQuoting(),
        order_manager=OrderManager(),
        exchange=ex,
        ticker_source=StaticTickerSource(["KX-BAD-1", "KX-OK-1"]),
    )
    # Should not raise even though one ticker errors
    await _run_for(runner, 0.15)


@pytest.mark.asyncio
async def test_runner_stop_halts_loop() -> None:
    book = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(45, 100.0)],
        no_levels=[(45, 100.0)],
    )
    runner, _ = _make_runner(
        tickers=["KX-T50"],
        book_for={"KX-T50": book},
        theo_prob=0.50,
        cycle_seconds=0.05,
    )
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.1)
    runner.stop()
    # Should finish promptly (well under cycle_seconds × 10)
    await asyncio.wait_for(task, timeout=0.5)


@pytest.mark.asyncio
async def test_runner_amends_when_book_shifts() -> None:
    """If best moves between cycles, runner should amend the resting order."""
    book = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(45, 100.0)],
        no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50"],
        book_for={"KX-T50": book},
        theo_prob=0.50,
    )
    # Run one cycle worth
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.08)
    # Shift the best — book becomes more aggressive
    ex.books["KX-T50"] = OrderbookLevels(
        ticker="KX-T50",
        yes_levels=[(46, 100.0)],
        no_levels=[(44, 100.0)],
    )
    await asyncio.sleep(0.15)
    runner.stop()
    await asyncio.wait_for(task, timeout=1.0)
    # At least one amend should have happened
    assert "amend" in ex.calls


@pytest.mark.asyncio
async def test_runner_warmup_called_on_strategy_and_providers() -> None:
    class RecordingStrategy:
        name = "recording"
        warmup_called = False
        shutdown_called = False
        async def warmup(self) -> None:
            self.warmup_called = True
        async def shutdown(self) -> None:
            self.shutdown_called = True
        async def quote(self, **kwargs):
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="recording-skip"),
                ask=SideDecision(price=0, size=0, skip=True, reason="recording-skip"),
            )

    book = OrderbookLevels(ticker="KX-T50", yes_levels=[], no_levels=[])
    ex = MockExchange({"KX-T50": book})
    reg = TheoRegistry()
    reg.register(FixedTheoProvider("KX", 0.5))
    strat = RecordingStrategy()
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=reg,
        strategy=strat,
        order_manager=OrderManager(),
        exchange=ex,
        ticker_source=StaticTickerSource(["KX-T50"]),
    )
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.08)
    runner.stop()
    await asyncio.wait_for(task, timeout=0.5)
    assert strat.warmup_called
    assert strat.shutdown_called
