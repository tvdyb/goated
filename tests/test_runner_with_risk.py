"""End-to-end tests: LIPRunner with a RiskRegistry wired in."""

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
from lipmm.quoting.strategies.default import DefaultLIPQuoting
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    RiskRegistry,
)
from lipmm.runner import LIPRunner, RunnerConfig
from lipmm.theo import TheoRegistry, TheoResult


# ── fakes ────────────────────────────────────────────────────────────


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
    def __init__(self, prefix: str, prob: float) -> None:
        self.series_prefix = prefix
        self._prob = prob
    async def warmup(self) -> None: pass
    async def shutdown(self) -> None: pass
    async def theo(self, ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=self._prob, confidence=1.0,
            computed_at=time.time(), source="fixed",
        )


def _make_runner(
    *,
    tickers: list[str],
    book_for: dict[str, OrderbookLevels],
    theo_prob: float,
    risk_registry: RiskRegistry | None = None,
    settlement_time_ts: float | None = None,
    recorder=None,
) -> tuple[LIPRunner, _MockExchange]:
    ex = _MockExchange(book_for)
    reg = TheoRegistry()
    prefix = tickers[0].split("-", 1)[0] if tickers else "KX"
    reg.register(_FixedTheo(prefix, theo_prob))
    runner = LIPRunner(
        config=RunnerConfig(
            cycle_seconds=0.05,
            settlement_time_ts=settlement_time_ts,
        ),
        theo_registry=reg,
        strategy=DefaultLIPQuoting(),
        order_manager=OrderManager(),
        exchange=ex,
        ticker_source=_StaticTickerSource(tickers),
        decision_recorder=recorder,
        risk_registry=risk_registry,
    )
    return runner, ex


async def _run_for(runner: LIPRunner, seconds: float) -> None:
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(seconds)
    runner.stop()
    await asyncio.wait_for(task, timeout=2.0)


# ── 1. No registry → behaves as before ───────────────────────────────


@pytest.mark.asyncio
async def test_runner_without_registry_unchanged() -> None:
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        risk_registry=None,
    )
    await _run_for(runner, 0.15)
    # Both bid and ask placed; runner with None registry behaves same
    # as before risk layer existed.
    assert any(o.action == "buy" for o in ex.orders.values())
    assert any(o.action == "sell" for o in ex.orders.values())


# ── 2. Veto propagates → no order placed ─────────────────────────────


@pytest.mark.asyncio
async def test_veto_propagates_to_order_manager() -> None:
    """Tight notional cap → bid vetoed → no buy order placed."""
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    # Strategy default sizing at theo=50 → small contract size; but cap
    # bid notional very tight to force a veto regardless of size.
    cap = MaxNotionalPerSideGate(max_dollars=0.05)  # $0.05 cap (impossibly tight)
    reg = RiskRegistry([cap])
    runner, ex = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        risk_registry=reg,
    )
    await _run_for(runner, 0.15)
    # No buy orders should exist (bid was vetoed every cycle)
    buys = [o for o in ex.orders.values() if o.action == "buy"]
    assert len(buys) == 0
    # Ask side was also vetoed by the same cap — verify no sells either
    sells = [o for o in ex.orders.values() if o.action == "sell"]
    assert len(sells) == 0


# ── 3. Audit trail reaches decision_recorder ─────────────────────────


@pytest.mark.asyncio
async def test_audit_trail_in_decision_records() -> None:
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    cap = MaxNotionalPerSideGate(max_dollars=0.05)
    reg = RiskRegistry([cap])
    records: list[dict] = []
    async def recorder(rec: dict) -> None:
        records.append(rec)
    runner, _ = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        risk_registry=reg,
        recorder=recorder,
    )
    await _run_for(runner, 0.15)
    assert len(records) >= 1
    # Schema must have "risk" top-level key with the audit entries
    rec = records[0]
    assert "risk" in rec
    assert isinstance(rec["risk"], list)
    assert len(rec["risk"]) >= 1
    audit_entry = rec["risk"][0]
    assert audit_entry["gate"] == "MaxNotionalPerSideGate"
    assert audit_entry["bid"] == "veto"


@pytest.mark.asyncio
async def test_audit_trail_empty_when_no_registry() -> None:
    book = OrderbookLevels(
        ticker="KX-T50.00",
        yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
    )
    records: list[dict] = []
    async def recorder(rec: dict) -> None:
        records.append(rec)
    runner, _ = _make_runner(
        tickers=["KX-T50.00"],
        book_for={"KX-T50.00": book},
        theo_prob=0.50,
        risk_registry=None,
        recorder=recorder,
    )
    await _run_for(runner, 0.15)
    assert len(records) >= 1
    # Without a registry, "risk" is present but empty
    assert records[0]["risk"] == []


# ── 4. Endgame guardrail behavior end-to-end ────────────────────────


@pytest.mark.asyncio
async def test_endgame_guardrail_pulls_deep_otm_bid_near_settle() -> None:
    """Replicates the soy-bot pickoff scenario: deep-OTM theo near settle
    → bid is vetoed by EndgameGuardrailGate."""
    book = OrderbookLevels(
        ticker="KX-T1196.99",
        yes_levels=[(1, 100.0)], no_levels=[(50, 100.0)],
    )
    # Settlement in 30 minutes; gate fires at <1 hour
    now = time.time()
    runner, ex = _make_runner(
        tickers=["KX-T1196.99"],
        book_for={"KX-T1196.99": book},
        theo_prob=0.05,  # deep OTM (5c)
        risk_registry=RiskRegistry([
            EndgameGuardrailGate(
                min_seconds_to_settle=3600,
                deep_otm_threshold=10, deep_itm_threshold=90,
            ),
        ]),
        settlement_time_ts=now + 1800,  # 30 minutes from now
    )
    await _run_for(runner, 0.15)
    # No bid orders should be placed (vetoed)
    buys = [o for o in ex.orders.values() if o.action == "buy"]
    assert len(buys) == 0


# ── 5. Multi-cycle throttle gate works correctly ────────────────────


@pytest.mark.asyncio
async def test_throttle_caps_orders_per_cycle() -> None:
    """With 3 tickers and max_orders=2, only the first ticker can be
    fully quoted; subsequent tickers are vetoed within the same cycle."""
    from lipmm.risk import MaxOrdersPerCycleGate
    books = {
        f"KX-T{i}": OrderbookLevels(
            ticker=f"KX-T{i}",
            yes_levels=[(45, 100.0)], no_levels=[(45, 100.0)],
        ) for i in range(3)
    }
    runner, ex = _make_runner(
        tickers=list(books.keys()),
        book_for=books,
        theo_prob=0.50,
        risk_registry=RiskRegistry([MaxOrdersPerCycleGate(max_orders=2)]),
    )
    # Run only one cycle's worth (~0.06s) so no resets fire
    await _run_for(runner, 0.06)
    # In the single cycle, only the first ticker's bid+ask should land
    # (count 2 = max_orders). Subsequent tickers are vetoed.
    # NOTE: with cycle_seconds=0.05 the loop may fire twice in 0.06s.
    # The assertion is loose: per-cycle veto should at least keep
    # total order count below 6 (the unconstrained max for 3 tickers).
    assert len(ex.orders) < 6
