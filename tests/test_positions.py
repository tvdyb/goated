"""Tests for state/positions.py -- ACT-09 position store.

Covers: fill application, exposure per-event, max-loss accounting,
reconciliation, edge cases, thread safety.
"""

from __future__ import annotations

import threading

import pytest

from state.positions import (
    EventExposure,
    Fill,
    MarketPosition,
    PositionReconciliationError,
    PositionStore,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _fill(
    ticker: str = "KXSOYBEANW-26APR24-17",
    side: str = "yes",
    action: str = "buy",
    count: int = 10,
    price_cents: int = 30,
    fill_id: str = "f1",
) -> Fill:
    return Fill(
        market_ticker=ticker,
        side=side,
        action=action,
        count=count,
        price_cents=price_cents,
        fill_id=fill_id,
    )


# ── Fill validation ──────────────────────────────────────────────────


class TestFillValidation:
    def test_valid_fill(self) -> None:
        f = _fill()
        assert f.count == 10

    def test_invalid_side(self) -> None:
        with pytest.raises(ValueError, match="side"):
            _fill(side="maybe")

    def test_invalid_action(self) -> None:
        with pytest.raises(ValueError, match="action"):
            _fill(action="hold")

    def test_zero_count(self) -> None:
        with pytest.raises(ValueError, match="count"):
            _fill(count=0)

    def test_negative_count(self) -> None:
        with pytest.raises(ValueError, match="count"):
            _fill(count=-5)

    def test_price_cents_too_low(self) -> None:
        with pytest.raises(ValueError, match="price_cents"):
            _fill(price_cents=0)

    def test_price_cents_too_high(self) -> None:
        with pytest.raises(ValueError, match="price_cents"):
            _fill(price_cents=100)

    def test_empty_fill_id(self) -> None:
        with pytest.raises(ValueError, match="fill_id"):
            _fill(fill_id="")

    def test_empty_ticker(self) -> None:
        with pytest.raises(ValueError, match="market_ticker"):
            _fill(ticker="")


# ── Buy Yes (long) ───────────────────────────────────────────────────


class TestBuyYes:
    def test_single_buy_yes(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="buy", count=10, price_cents=30, fill_id="f1"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 10
        assert pos.total_cost_cents == 300  # 10 * 30

    def test_multiple_buy_yes(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(count=10, price_cents=30, fill_id="f1"))
        store.apply_fill(_fill(count=5, price_cents=40, fill_id="f2"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 15
        assert pos.total_cost_cents == 500  # 300 + 200

    def test_max_loss_long(self) -> None:
        """Max loss on long = total cost (contracts become worthless)."""
        store = PositionStore()
        store.apply_fill(_fill(count=10, price_cents=30, fill_id="f1"))
        assert store.max_loss_cents("KXSOYBEANW-26APR24-17") == 300


# ── Sell Yes (short) ─────────────────────────────────────────────────


class TestSellYes:
    def test_single_sell_yes(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="sell", count=10, price_cents=70, fill_id="f1"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == -10
        assert pos.total_cost_cents == 700  # 10 * 70

    def test_max_loss_short(self) -> None:
        """Max loss on short = |qty| * 100 - received (settle at $1)."""
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="sell", count=10, price_cents=70, fill_id="f1"))
        # Max loss = 10 * 100 - 700 = 300
        assert store.max_loss_cents("KXSOYBEANW-26APR24-17") == 300


# ── Buy No (equivalent to selling Yes) ──────────────────────────────


class TestBuyNo:
    def test_buy_no_is_short_yes(self) -> None:
        store = PositionStore()
        # Buy No at 40 cents => sell Yes equivalent, cost = 100 - 40 = 60
        store.apply_fill(_fill(side="no", action="buy", count=10, price_cents=40, fill_id="f1"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == -10
        assert pos.total_cost_cents == 600  # 10 * (100 - 40)

    def test_max_loss_buy_no(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="no", action="buy", count=10, price_cents=40, fill_id="f1"))
        # Short 10 at cost 600: max loss = 10*100 - 600 = 400
        assert store.max_loss_cents("KXSOYBEANW-26APR24-17") == 400


# ── Sell No (equivalent to buying Yes) ──────────────────────────────


class TestSellNo:
    def test_sell_no_is_long_yes(self) -> None:
        store = PositionStore()
        # Sell No at 40 cents => buy Yes equivalent, cost = 100 - 40 = 60
        store.apply_fill(_fill(side="no", action="sell", count=10, price_cents=40, fill_id="f1"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 10
        assert pos.total_cost_cents == 600  # 10 * (100 - 40)


# ── Position reduction and flips ─────────────────────────────────────


class TestPositionReduction:
    def test_partial_close(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="buy", count=10, price_cents=30, fill_id="f1"))
        store.apply_fill(_fill(side="yes", action="sell", count=4, price_cents=50, fill_id="f2"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 6
        # Realized PnL: sold 4 at 50, avg cost was 30 => 4*(50-30) = 80
        assert pos.realized_pnl_cents == 80
        # Remaining cost: 6 * 30 = 180
        assert pos.total_cost_cents == 180

    def test_full_close(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="buy", count=10, price_cents=30, fill_id="f1"))
        store.apply_fill(_fill(side="yes", action="sell", count=10, price_cents=50, fill_id="f2"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 0
        assert pos.total_cost_cents == 0
        assert pos.realized_pnl_cents == 200  # 10 * (50 - 30)
        assert pos.max_loss_cents == 0

    def test_flip_long_to_short(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="buy", count=10, price_cents=30, fill_id="f1"))
        # Sell 15: close 10 long, open 5 short
        store.apply_fill(_fill(side="yes", action="sell", count=15, price_cents=50, fill_id="f2"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == -5
        # Realized from closing 10 long: 10 * 50 - 300 = 200
        assert pos.realized_pnl_cents == 200
        # New short cost: 5 * 50 = 250
        assert pos.total_cost_cents == 250

    def test_flip_short_to_long(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(side="yes", action="sell", count=10, price_cents=70, fill_id="f1"))
        # Buy 15: close 10 short, open 5 long
        store.apply_fill(_fill(side="yes", action="buy", count=15, price_cents=50, fill_id="f2"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 5
        # Realized from closing short: cost(700) - 10*50(500) = 200
        assert pos.realized_pnl_cents == 200
        # New long cost: 5 * 50 = 250
        assert pos.total_cost_cents == 250


# ── Fill dedup ───────────────────────────────────────────────────────


class TestFillDedup:
    def test_duplicate_fill_ignored(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(fill_id="dup1"))
        store.apply_fill(_fill(fill_id="dup1"))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 10  # Only applied once


# ── Per-Event exposure ───────────────────────────────────────────────


class TestEventExposure:
    def test_single_market(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            count=10, price_cents=30, fill_id="f1",
        ))
        exp = store.get_event_exposure("KXSOYBEANW-26APR24")
        assert exp.signed_exposure == 10
        assert exp.max_loss_cents == 300
        assert exp.n_markets == 1

    def test_multiple_markets_same_event(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy",
            count=10, price_cents=30, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-18",
            side="yes", action="sell",
            count=5, price_cents=70, fill_id="f2",
        ))
        exp = store.get_event_exposure("KXSOYBEANW-26APR24")
        assert exp.signed_exposure == 5  # 10 + (-5)
        assert exp.max_loss_cents == 300 + 150  # long max-loss + short max-loss
        assert exp.n_markets == 2

    def test_opposing_positions_same_event(self) -> None:
        """Long bucket-17 and short bucket-18 in the same event."""
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy",
            count=10, price_cents=50, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-18",
            side="yes", action="sell",
            count=10, price_cents=50, fill_id="f2",
        ))
        exp = store.get_event_exposure("KXSOYBEANW-26APR24")
        assert exp.signed_exposure == 0
        # Max loss still sums individually: 500 + 500 = 1000
        assert exp.max_loss_cents == 1000
        assert exp.n_markets == 2

    def test_different_events(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            count=10, price_cents=30, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26MAY01-17",
            count=5, price_cents=40, fill_id="f2",
        ))
        exp_apr = store.get_event_exposure("KXSOYBEANW-26APR24")
        exp_may = store.get_event_exposure("KXSOYBEANW-26MAY01")
        assert exp_apr.signed_exposure == 10
        assert exp_may.signed_exposure == 5

    def test_all_event_exposures(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            count=10, price_cents=30, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26MAY01-17",
            count=5, price_cents=40, fill_id="f2",
        ))
        all_exp = store.get_all_event_exposures()
        assert len(all_exp) == 2
        assert "KXSOYBEANW-26APR24" in all_exp
        assert "KXSOYBEANW-26MAY01" in all_exp


# ── Total max loss ───────────────────────────────────────────────────


class TestTotalMaxLoss:
    def test_total_across_events(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            count=10, price_cents=30, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26MAY01-17",
            count=5, price_cents=40, fill_id="f2",
        ))
        assert store.total_max_loss_cents() == 300 + 200  # 10*30 + 5*40


# ── Empty store edge cases ───────────────────────────────────────────


class TestEmptyStore:
    def test_empty_position(self) -> None:
        store = PositionStore()
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 0
        assert pos.total_cost_cents == 0
        assert pos.max_loss_cents == 0

    def test_empty_event_exposure(self) -> None:
        store = PositionStore()
        exp = store.get_event_exposure("KXSOYBEANW-26APR24")
        assert exp.signed_exposure == 0
        assert exp.max_loss_cents == 0
        assert exp.n_markets == 0

    def test_empty_total_max_loss(self) -> None:
        store = PositionStore()
        assert store.total_max_loss_cents() == 0

    def test_empty_snapshot(self) -> None:
        store = PositionStore()
        assert store.snapshot() == {}

    def test_empty_all_exposures(self) -> None:
        store = PositionStore()
        assert store.get_all_event_exposures() == {}

    def test_clear(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(fill_id="f1"))
        store.clear()
        assert store.snapshot() == {}
        assert store.total_max_loss_cents() == 0


# ── Reconciliation ───────────────────────────────────────────────────


class TestReconciliation:
    def test_reconciliation_match(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy",
            count=10, price_cents=30, fill_id="f1",
        ))
        api_positions = [
            {"ticker": "KXSOYBEANW-26APR24-17", "market_exposure": 10},
        ]
        result = store.reconcile(api_positions)
        assert result == []

    def test_reconciliation_mismatch_raises(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy",
            count=10, price_cents=30, fill_id="f1",
        ))
        api_positions = [
            {"ticker": "KXSOYBEANW-26APR24-17", "market_exposure": 5},
        ]
        with pytest.raises(PositionReconciliationError) as exc_info:
            store.reconcile(api_positions)
        assert "local=10" in str(exc_info.value)
        assert "api=5" in str(exc_info.value)

    def test_reconciliation_local_not_in_api(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            count=10, price_cents=30, fill_id="f1",
        ))
        # API returns empty
        with pytest.raises(PositionReconciliationError, match="not in API"):
            store.reconcile([])

    def test_reconciliation_api_extra_zero(self) -> None:
        """API reports a ticker we don't have -- that's fine if both are zero."""
        store = PositionStore()
        api_positions = [
            {"ticker": "KXSOYBEANW-26APR24-17", "market_exposure": 0},
        ]
        result = store.reconcile(api_positions)
        assert result == []

    def test_reconciliation_api_extra_nonzero(self) -> None:
        """API reports a position we don't have locally."""
        store = PositionStore()
        api_positions = [
            {"ticker": "KXSOYBEANW-26APR24-17", "market_exposure": 5},
        ]
        with pytest.raises(PositionReconciliationError):
            store.reconcile(api_positions)

    def test_reconciliation_missing_ticker_raises(self) -> None:
        store = PositionStore()
        with pytest.raises(ValueError, match="ticker"):
            store.reconcile([{"market_exposure": 10}])

    def test_reconciliation_missing_exposure_raises(self) -> None:
        store = PositionStore()
        with pytest.raises(ValueError, match="market_exposure"):
            store.reconcile([{"ticker": "KXSOYBEANW-26APR24-17"}])

    def test_reconciliation_short_position(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="sell",
            count=10, price_cents=70, fill_id="f1",
        ))
        api_positions = [
            {"ticker": "KXSOYBEANW-26APR24-17", "market_exposure": -10},
        ]
        result = store.reconcile(api_positions)
        assert result == []


# ── Thread safety ────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_fills(self) -> None:
        """Apply many fills from multiple threads without data corruption."""
        store = PositionStore()
        n_threads = 8
        fills_per_thread = 100
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(fills_per_thread):
                    store.apply_fill(Fill(
                        market_ticker="KXSOYBEANW-26APR24-17",
                        side="yes",
                        action="buy",
                        count=1,
                        price_cents=50,
                        fill_id=f"t{thread_id}-f{i}",
                    ))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(t,))
            for t in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == n_threads * fills_per_thread


# ── Snapshot ─────────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_excludes_zero(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy", count=10, price_cents=30, fill_id="f1",
        ))
        store.apply_fill(_fill(
            ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="sell", count=10, price_cents=30, fill_id="f2",
        ))
        snap = store.snapshot()
        assert len(snap) == 0

    def test_snapshot_returns_copies(self) -> None:
        store = PositionStore()
        store.apply_fill(_fill(fill_id="f1"))
        snap = store.snapshot()
        # Mutating the snapshot should not affect the store
        snap["KXSOYBEANW-26APR24-17"].signed_qty = 999
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        assert pos.signed_qty == 10


# ── MarketPosition.max_loss_cents property ───────────────────────────


class TestMarketPositionMaxLoss:
    def test_flat(self) -> None:
        p = MarketPosition(market_ticker="X-26APR24-1", event_ticker="X-26APR24")
        assert p.max_loss_cents == 0

    def test_long(self) -> None:
        p = MarketPosition(
            market_ticker="X-26APR24-1", event_ticker="X-26APR24",
            signed_qty=10, total_cost_cents=300,
        )
        assert p.max_loss_cents == 300

    def test_short(self) -> None:
        p = MarketPosition(
            market_ticker="X-26APR24-1", event_ticker="X-26APR24",
            signed_qty=-10, total_cost_cents=700,
        )
        # max loss = 10*100 - 700 = 300
        assert p.max_loss_cents == 300
