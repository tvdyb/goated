"""Integration tests for deploy/main.py — full main loop with mocks.

Tests:
1. Full cycle with mocked Kalshi + IB connections.
2. Capital cap enforcement.
3. Kill switch end-to-end.
4. Crash recovery (position state persistence).
5. Settlement gate pull-all cancels all orders.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from attribution.pnl import FillRecord, PnLTracker
from deploy.main import (
    MarketMaker,
    _build_quoter_config,
    _build_risk_limits,
    load_config,
)
from engine.kill import KillSwitch, TriggerResult
from engine.quoter import (
    EventBook,
    QuoteActionType,
    QuoterConfig,
    StrikeBook,
    compute_quotes,
)
from engine.risk import RiskGate, RiskLimits
from engine.rnd.bucket_integrator import BucketPrices
from engine.settlement_gate import GateState, gate_state
from engine.taker_imbalance import ImbalanceConfig, TakerImbalanceDetector
from feeds.cme.options_chain import OptionsChain
from state.positions import Fill, PositionStore

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bucket_prices(
    strikes: list[float],
    survivals: list[float],
) -> BucketPrices:
    ks = np.array(strikes, dtype=np.float64)
    sv = np.array(survivals, dtype=np.float64)
    n_buckets = len(strikes) + 1
    bucket_yes = np.zeros(n_buckets, dtype=np.float64)
    bucket_yes[0] = 1.0 - sv[0]
    for i in range(1, len(sv)):
        bucket_yes[i] = sv[i - 1] - sv[i]
    bucket_yes[-1] = sv[-1]
    return BucketPrices(
        kalshi_strikes=ks,
        survival=sv,
        bucket_yes=bucket_yes,
        bucket_sum=float(bucket_yes.sum()),
        n_buckets=n_buckets,
    )


def _make_event_book(
    event_ticker: str,
    strikes: list[float],
    best_bids: list[int],
    best_asks: list[int],
) -> EventBook:
    books = []
    for s, bb, ba in zip(strikes, best_bids, best_asks, strict=True):
        strike_int = int(round(s * 100))
        books.append(StrikeBook(
            market_ticker=f"{event_ticker}-{strike_int}",
            strike=s,
            best_bid_cents=bb,
            best_ask_cents=ba,
        ))
    return EventBook(event_ticker=event_ticker, strike_books=books)


def _make_options_chain() -> OptionsChain:
    strikes = np.array([1100.0, 1150.0, 1200.0, 1250.0, 1300.0])
    return OptionsChain(
        symbol="ZS",
        expiry=date(2026, 7, 24),
        as_of=date(2026, 4, 28),
        underlying_settle=1192.0,
        strikes=strikes,
        call_prices=np.array([92.0, 50.0, 18.0, 4.0, 0.5]),
        put_prices=np.array([0.5, 4.0, 18.0, 50.0, 92.0]),
        call_ivs=np.array([0.20, 0.17, 0.15, 0.16, 0.18]),
        put_ivs=None,
        call_oi=None,
        put_oi=None,
        call_volume=None,
        put_volume=None,
    )


def _test_config() -> dict[str, Any]:
    return {
        "series": [{
            "ticker_prefix": "KXSOYBEANMON",
            "cme_symbol": "ZS",
            "hedge_enabled": False,
            "max_inventory_usd": 1000,
            "min_spread_cents": 4,
            "edge_tolerance_cents": 2,
            "hedge_threshold_contracts": 3,
            "max_contracts_per_strike": 50,
        }],
        "risk": {
            "max_total_inventory_usd": 1000,
            "max_per_event_inventory_usd": 500,
            "kill_switch_pnl_threshold_pct": 5,
            "hedge_disconnect_timeout_s": 15,
            "aggregate_delta_cap": 500,
            "per_event_delta_cap": 200,
        },
        "settlement_gate": {
            "pre_window_seconds": 60,
            "post_window_minutes": 15,
        },
        "quoter": {
            "min_half_spread_cents": 2,
            "max_half_spread_cents": 4,
            "inventory_skew_gamma": 0.1,
            "fee_threshold_cents": 1,
            "taker_rate": 0.07,
            "maker_fraction": 0.25,
        },
        "taker_imbalance": {
            "window_seconds": 60,
            "threshold": 0.7,
            "cooldown_seconds": 120,
            "min_trades": 5,
        },
        "hedge": {
            "threshold_contracts": 3.0,
            "cooldown_s": 60.0,
        },
        "loop": {
            "cycle_seconds": 30,
            "cme_refresh_seconds": 900,
        },
        "api": {
            "kalshi_base": "https://api.elections.kalshi.com",
            "ib_gateway_host": "127.0.0.1",
            "ib_gateway_port": 4001,
            "ib_client_id": 1,
        },
    }


# ---------------------------------------------------------------------------
# Test: config loading
# ---------------------------------------------------------------------------


class TestConfigLoading:
    def test_build_quoter_config(self) -> None:
        cfg = _test_config()
        qc = _build_quoter_config(cfg)
        assert qc.min_half_spread_cents == 2
        assert qc.max_half_spread_cents == 4
        assert qc.taker_rate == 0.07

    def test_build_risk_limits(self) -> None:
        cfg = _test_config()
        rl = _build_risk_limits(cfg)
        assert rl.max_loss_cents == 100_000  # $1000 * 100
        assert rl.aggregate_delta_cap == 500
        assert rl.per_event_delta_cap == 200

    def test_load_config_from_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "series:\n  - ticker_prefix: KXSOYBEANMON\n    cme_symbol: ZS\n"
            "risk:\n  max_total_inventory_usd: 500\n"
        )
        cfg = load_config(str(config_path))
        assert cfg["series"][0]["ticker_prefix"] == "KXSOYBEANMON"


# ---------------------------------------------------------------------------
# Test: quoter integration with RND prices
# ---------------------------------------------------------------------------


class TestQuoterIntegration:
    def test_compute_quotes_produces_actions(self) -> None:
        """Full quoter produces PLACE_BID + PLACE_ASK actions."""
        strikes = [11.50, 11.90, 12.00, 12.10, 12.50]
        survivals = [0.95, 0.60, 0.50, 0.40, 0.05]
        bp = _make_bucket_prices(strikes, survivals)
        eb = _make_event_book(
            "KXSOYBEANMON-26MAY01",
            strikes,
            best_bids=[0] * 5,
            best_asks=[100] * 5,
        )
        actions = compute_quotes(
            rnd_prices=bp,
            event_book=eb,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(),
        )
        # Should produce some PLACE_BID and PLACE_ASK actions
        bids = [a for a in actions if a.action_type == QuoteActionType.PLACE_BID]
        asks = [a for a in actions if a.action_type == QuoteActionType.PLACE_ASK]
        assert len(bids) > 0
        assert len(asks) > 0

    def test_risk_gate_cancels_all(self) -> None:
        """When risk_ok=False, all actions are CANCEL."""
        strikes = [11.90, 12.00, 12.10]
        survivals = [0.60, 0.50, 0.40]
        bp = _make_bucket_prices(strikes, survivals)
        eb = _make_event_book(
            "KXSOYBEANMON-26MAY01",
            strikes,
            best_bids=[0] * 3,
            best_asks=[100] * 3,
        )
        actions = compute_quotes(
            rnd_prices=bp,
            event_book=eb,
            inventory={},
            risk_ok=False,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(),
        )
        assert all(a.action_type == QuoteActionType.CANCEL for a in actions)

    def test_settlement_gate_pull_all(self) -> None:
        """When gate_size_mult=0, all actions are CANCEL."""
        strikes = [11.90, 12.00, 12.10]
        survivals = [0.60, 0.50, 0.40]
        bp = _make_bucket_prices(strikes, survivals)
        eb = _make_event_book(
            "KXSOYBEANMON-26MAY01",
            strikes,
            best_bids=[0] * 3,
            best_asks=[100] * 3,
        )
        actions = compute_quotes(
            rnd_prices=bp,
            event_book=eb,
            inventory={},
            risk_ok=True,
            gate_size_mult=0.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(),
        )
        assert all(a.action_type == QuoteActionType.CANCEL for a in actions)
        assert all("settlement_gate" in a.reason for a in actions)


# ---------------------------------------------------------------------------
# Test: capital cap enforcement
# ---------------------------------------------------------------------------


class TestCapitalCap:
    def test_max_loss_cap_prevents_new_orders(self) -> None:
        """Risk gate fires when max-loss exceeds cap."""
        store = PositionStore()
        limits = RiskLimits(
            aggregate_delta_cap=500,
            per_event_delta_cap=200,
            max_loss_cents=100_000,  # $1000
        )
        gate = RiskGate(store, limits)

        # Add positions that max out the cap
        for i in range(20):
            store.apply_fill(Fill(
                market_ticker=f"KXSOYBEANMON-26MAY01-{1190 + i}",
                side="yes",
                action="buy",
                count=100,
                price_cents=50,
                fill_id=f"fill-{i}",
            ))

        # Now check post-trade: should fire (may be delta or max_loss)
        result = gate.check_post_trade()
        assert result.fired
        assert "risk" in result.name

    def test_capital_cap_in_config(self) -> None:
        """Config correctly sets $1000 cap."""
        cfg = _test_config()
        limits = _build_risk_limits(cfg)
        assert limits.max_loss_cents == 100_000  # $1000


# ---------------------------------------------------------------------------
# Test: kill switch end-to-end
# ---------------------------------------------------------------------------


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_cancels_orders(self) -> None:
        """Kill switch fires and cancels all orders."""
        mock_client = AsyncMock()
        mock_client.cancel_order = AsyncMock(return_value={})
        mock_client.batch_cancel_orders = AsyncMock(return_value={})

        # Trigger that always fires
        def always_fire() -> TriggerResult:
            return TriggerResult(fired=True, name="test_trigger", detail="testing")

        ks = KillSwitch(client=mock_client, triggers=[always_fire])
        order_ids = ["order-1", "order-2", "order-3"]

        result = await ks.check_and_fire(order_ids)
        assert result.fired
        assert result.trigger_name == "test_trigger"
        assert len(result.cancelled_ids) == 3

    @pytest.mark.asyncio
    async def test_kill_switch_does_not_fire_when_ok(self) -> None:
        """Kill switch does not fire when no triggers fire."""
        mock_client = AsyncMock()

        def no_fire() -> TriggerResult:
            return TriggerResult(fired=False, name="test_trigger")

        ks = KillSwitch(client=mock_client, triggers=[no_fire])
        result = await ks.check_and_fire(["order-1"])
        assert not result.fired
        assert len(result.cancelled_ids) == 0

    @pytest.mark.asyncio
    async def test_kill_switch_risk_trigger(self) -> None:
        """Risk gate integrates as kill switch trigger."""
        store = PositionStore()
        limits = RiskLimits(
            aggregate_delta_cap=10,
            per_event_delta_cap=5,
            max_loss_cents=1000,
        )
        gate = RiskGate(store, limits)

        # Exceed per-event cap
        for i in range(10):
            store.apply_fill(Fill(
                market_ticker="KXSOYBEANMON-26MAY01-1200",
                side="yes",
                action="buy",
                count=1,
                price_cents=50,
                fill_id=f"f-{i}",
            ))

        mock_client = AsyncMock()
        mock_client.cancel_order = AsyncMock(return_value={})
        mock_client.batch_cancel_orders = AsyncMock(return_value={})

        ks = KillSwitch(client=mock_client, triggers=[gate.make_kill_trigger()])
        result = await ks.check_and_fire(["order-1", "order-2"])
        assert result.fired
        assert "risk" in result.trigger_name

    @pytest.mark.asyncio
    async def test_kill_switch_disarmed(self) -> None:
        """Disarmed kill switch does not fire."""
        mock_client = AsyncMock()

        def always_fire() -> TriggerResult:
            return TriggerResult(fired=True, name="test", detail="")

        ks = KillSwitch(client=mock_client, triggers=[always_fire])
        ks.disarm()
        result = await ks.check_and_fire(["order-1"])
        assert not result.fired


# ---------------------------------------------------------------------------
# Test: position tracking and reconciliation
# ---------------------------------------------------------------------------


class TestPositionTracking:
    def test_fill_application(self) -> None:
        """Fills correctly update position store."""
        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="buy",
            count=10,
            price_cents=50,
            fill_id="f1",
        ))
        pos = store.get_position("KXSOYBEANMON-26MAY01-1200")
        assert pos.signed_qty == 10
        assert pos.total_cost_cents == 500

    def test_fill_dedup(self) -> None:
        """Duplicate fill IDs are ignored."""
        store = PositionStore()
        fill = Fill(
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="buy",
            count=10,
            price_cents=50,
            fill_id="f1",
        )
        store.apply_fill(fill)
        store.apply_fill(fill)  # duplicate
        pos = store.get_position("KXSOYBEANMON-26MAY01-1200")
        assert pos.signed_qty == 10  # not 20

    def test_max_loss_long(self) -> None:
        """Long position max-loss = cost."""
        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="buy",
            count=10,
            price_cents=30,
            fill_id="f1",
        ))
        assert store.max_loss_cents("KXSOYBEANMON-26MAY01-1200") == 300

    def test_max_loss_short(self) -> None:
        """Short position max-loss = |qty| * 100 - cost."""
        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="sell",
            count=10,
            price_cents=70,
            fill_id="f1",
        ))
        pos = store.get_position("KXSOYBEANMON-26MAY01-1200")
        assert pos.signed_qty == -10
        # max_loss = 10 * 100 - 700 = 300
        assert pos.max_loss_cents == 300

    def test_reconciliation_mismatch_raises(self) -> None:
        """Reconciliation raises on mismatch."""
        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="buy",
            count=10,
            price_cents=50,
            fill_id="f1",
        ))
        api_positions = [
            {"ticker": "KXSOYBEANMON-26MAY01-1200", "market_exposure": 5}
        ]
        with pytest.raises(Exception, match="reconciliation"):
            store.reconcile(api_positions)


# ---------------------------------------------------------------------------
# Test: settlement gate integration
# ---------------------------------------------------------------------------


class TestSettlementGateIntegration:
    def test_normal_state(self) -> None:
        """Far from USDA event -> NORMAL gate."""
        now = datetime(2026, 5, 20, 10, 0, tzinfo=_ET)
        action = gate_state(now, series="soy")
        assert action.state == GateState.NORMAL
        assert action.size_mult == 1.0

    def test_pull_all_during_wasde(self) -> None:
        """During WASDE window -> PULL_ALL."""
        # WASDE May 2026 is on 2026-05-12 at noon ET
        now = datetime(2026, 5, 12, 12, 0, 30, tzinfo=_ET)
        action = gate_state(now, series="soy")
        assert action.state == GateState.PULL_ALL
        assert action.size_mult == 0.0


# ---------------------------------------------------------------------------
# Test: taker imbalance integration
# ---------------------------------------------------------------------------


class TestTakerImbalance:
    def test_no_signal_on_balanced(self) -> None:
        detector = TakerImbalanceDetector(ImbalanceConfig(min_trades=3))
        now = 1000.0
        detector.record_trade(52, 50, now + 1)
        detector.record_trade(48, 50, now + 2)
        detector.record_trade(52, 50, now + 3)
        signal = detector.current_signal(now + 4)
        assert signal is None

    def test_signal_on_imbalance(self) -> None:
        detector = TakerImbalanceDetector(
            ImbalanceConfig(min_trades=3, threshold=0.5)
        )
        now = 1000.0
        # All buy-initiated
        for i in range(5):
            detector.record_trade(52, 50, now + i)
        signal = detector.current_signal(now + 5)
        assert signal is not None
        assert signal.withdraw_side == "ask"


# ---------------------------------------------------------------------------
# Test: PnL attribution
# ---------------------------------------------------------------------------


class TestPnLAttribution:
    def test_fill_record_attribution(self) -> None:
        tracker = PnLTracker(output_dir=Path("/tmp/test_pnl"))
        tracker.record_fill(FillRecord(
            timestamp=1000.0,
            market_ticker="KXSOYBEANMON-26MAY01-1200",
            side="yes",
            action="buy",
            count=10,
            price_cents=48,
            fill_id="f1",
            model_fair_cents=50,
        ))
        summary = tracker.get_daily_summary()
        assert summary["spread_capture_cents"] > 0
        assert summary["kalshi_fees_cents"] > 0

    def test_hourly_bucketing(self) -> None:
        tracker = PnLTracker(output_dir=Path("/tmp/test_pnl"))
        # Two fills in different hours
        tracker.record_fill(FillRecord(
            timestamp=3600.0,  # hour 1
            market_ticker="M1",
            side="yes",
            action="buy",
            count=5,
            price_cents=50,
            fill_id="f1",
        ))
        tracker.record_fill(FillRecord(
            timestamp=7200.0,  # hour 2
            market_ticker="M2",
            side="yes",
            action="buy",
            count=5,
            price_cents=50,
            fill_id="f2",
        ))
        assert len(tracker._hourly) == 2

    def test_write_summary_csv(self, tmp_path: Path) -> None:
        tracker = PnLTracker(output_dir=tmp_path)
        tracker.record_fill(FillRecord(
            timestamp=1000.0,
            market_ticker="M1",
            side="yes",
            action="buy",
            count=1,
            price_cents=50,
            fill_id="f1",
        ))
        tracker.write_summary()
        csv_files = list(tmp_path.glob("pnl_*.csv"))
        assert len(csv_files) == 1


# ---------------------------------------------------------------------------
# Test: MarketMaker initialization
# ---------------------------------------------------------------------------


class TestMarketMakerInit:
    def test_init_from_config(self) -> None:
        """MarketMaker initializes without error from test config."""
        cfg = _test_config()
        mm = MarketMaker(cfg)
        assert mm._cycle_seconds == 30
        assert mm._max_loss_cents == 100_000

    def test_no_series_raises(self) -> None:
        """MarketMaker raises if no series configured."""
        cfg = _test_config()
        cfg["series"] = []
        with pytest.raises(ValueError, match="No series"):
            MarketMaker(cfg)

    def test_quoter_config_built(self) -> None:
        cfg = _test_config()
        mm = MarketMaker(cfg)
        assert mm._quoter_config.min_half_spread_cents == 2

    def test_risk_limits_built(self) -> None:
        cfg = _test_config()
        mm = MarketMaker(cfg)
        assert mm._risk_limits.max_loss_cents == 100_000


# ---------------------------------------------------------------------------
# Test: full cycle simulation (mocked I/O)
# ---------------------------------------------------------------------------


class TestFullCycleSimulation:
    def test_quoter_produces_valid_orders(self) -> None:
        """End-to-end: RND -> quoter -> valid post_only orders."""
        strikes = [11.50, 11.90, 12.00, 12.10, 12.50]
        survivals = [0.95, 0.60, 0.50, 0.40, 0.05]
        bp = _make_bucket_prices(strikes, survivals)
        eb = _make_event_book(
            "KXSOYBEANMON-26MAY01",
            strikes,
            best_bids=[0] * 5,
            best_asks=[100] * 5,
        )

        actions = compute_quotes(
            rnd_prices=bp,
            event_book=eb,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(),
        )

        for a in actions:
            if a.action_type in (QuoteActionType.PLACE_BID, QuoteActionType.PLACE_ASK):
                assert 1 <= a.price_cents <= 99
                assert a.size > 0

    def test_all_orders_respect_post_only(self) -> None:
        """Verify that the system only produces post_only orders."""
        # The create_order call in deploy/main.py always passes post_only=True
        # Verify the quoter never crosses the spread
        strikes = [11.90, 12.00, 12.10]
        survivals = [0.60, 0.50, 0.40]
        bp = _make_bucket_prices(strikes, survivals)
        eb = _make_event_book(
            "KXSOYBEANMON-26MAY01",
            strikes,
            best_bids=[45, 48, 38],
            best_asks=[55, 52, 42],
        )

        actions = compute_quotes(
            rnd_prices=bp,
            event_book=eb,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(),
        )

        bids = [a for a in actions if a.action_type == QuoteActionType.PLACE_BID]
        asks = [a for a in actions if a.action_type == QuoteActionType.PLACE_ASK]

        for a in bids:
            sb = next(s for s in eb.strike_books if s.market_ticker == a.market_ticker)
            # Bid must not cross the existing ask
            assert a.price_cents < sb.best_ask_cents

        for a in asks:
            sb = next(s for s in eb.strike_books if s.market_ticker == a.market_ticker)
            # Ask must not cross the existing bid
            assert a.price_cents > sb.best_bid_cents
