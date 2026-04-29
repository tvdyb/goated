"""Tests for the hedge/ package: IBKR client, delta aggregator, sizer, trigger.

All IB interactions are mocked — no live IB Gateway required in CI.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from engine.rnd.bucket_integrator import BucketPrices
from hedge.delta_aggregator import _compute_density, _extract_strike, aggregate_delta  # noqa: PLC2701
from hedge.ibkr_client import HedgeConnectionError, IBKRClient
from hedge.sizer import compute_hedge_size
from hedge.trigger import HedgeTrigger
from state.positions import Fill, PositionStore  # noqa: I001

# ═══════════════════════════════════════════════════════════════════════
# Sizer tests
# ═══════════════════════════════════════════════════════════════════════


class TestComputeHedgeSize:
    def test_long_exposure_sells_futures(self):
        """Positive delta_port -> sell futures (negative return)."""
        # 50,000 delta-dollars at $10/bushel, 5000 bushels/contract
        # = 50000 / (5000 * 10) = 1 contract to sell
        n = compute_hedge_size(50_000.0, 10.0, 5_000)
        assert n == -1

    def test_short_exposure_buys_futures(self):
        """Negative delta_port -> buy futures (positive return)."""
        n = compute_hedge_size(-50_000.0, 10.0, 5_000)
        assert n == 1

    def test_exact_multiple(self):
        # 100,000 delta / (5000 * 10) = 2 contracts
        n = compute_hedge_size(100_000.0, 10.0, 5_000)
        assert n == -2

    def test_fractional_rounds(self):
        # 75,000 / 50,000 = 1.5 -> rounds to 2
        n = compute_hedge_size(75_000.0, 10.0, 5_000)
        assert n == -2

    def test_small_delta_minimum_one_contract(self):
        # Very small but nonzero delta -> minimum 1 contract
        n = compute_hedge_size(100.0, 10.0, 5_000)
        assert abs(n) == 1

    def test_zero_delta(self):
        n = compute_hedge_size(0.0, 10.0, 5_000)
        assert n == 0

    def test_invalid_price_raises(self):
        with pytest.raises(ValueError, match="underlying_price"):
            compute_hedge_size(1000.0, 0.0)

    def test_invalid_contract_size_raises(self):
        with pytest.raises(ValueError, match="contract_size"):
            compute_hedge_size(1000.0, 10.0, 0)

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="underlying_price"):
            compute_hedge_size(1000.0, -5.0)

    def test_realistic_soybean_example(self):
        """Realistic: delta=3 contracts @ ZS price=$10.50."""
        # 3 * 5000 * 10.50 = 157,500 dollar-delta
        n = compute_hedge_size(157_500.0, 10.50, 5_000)
        assert n == -3


# ═══════════════════════════════════════════════════════════════════════
# Delta aggregator tests
# ═══════════════════════════════════════════════════════════════════════


def _make_bucket_prices(
    strikes: np.ndarray | list,
    survival: np.ndarray | list,
) -> BucketPrices:
    """Helper to create BucketPrices for testing."""
    strikes = np.asarray(strikes, dtype=np.float64)
    survival = np.asarray(survival, dtype=np.float64)
    n_strikes = len(strikes)

    # Compute bucket_yes from survival
    bucket_yes = np.empty(n_strikes + 1)
    bucket_yes[0] = 1.0 - survival[0]  # lower tail
    for i in range(n_strikes - 1):
        bucket_yes[i + 1] = survival[i] - survival[i + 1]
    bucket_yes[-1] = survival[-1]  # upper tail

    return BucketPrices(
        kalshi_strikes=strikes,
        survival=survival,
        bucket_yes=bucket_yes,
        bucket_sum=float(bucket_yes.sum()),
        n_buckets=n_strikes + 1,
    )


class TestComputeDensity:
    def test_uniform_survival(self):
        """Linearly decreasing survival -> constant density."""
        strikes = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        survival = np.array([0.8, 0.6, 0.4, 0.2, 0.0])
        density = _compute_density(strikes, survival)
        # Constant density of 0.2 per unit strike
        np.testing.assert_allclose(density, 0.2, atol=1e-10)

    def test_density_nonnegative(self):
        """Density should always be non-negative."""
        strikes = np.array([10.0, 11.0, 12.0])
        survival = np.array([0.9, 0.5, 0.1])
        density = _compute_density(strikes, survival)
        assert np.all(density >= 0)

    def test_too_few_strikes_raises(self):
        bp = _make_bucket_prices([10.0], [0.5])
        store = PositionStore()
        with pytest.raises(ValueError, match="at least 2 strikes"):
            aggregate_delta(store, bp, "KXSOYBEANMON-26MAY01")


class TestAggregateDelta:
    def test_empty_positions_zero_delta(self):
        bp = _make_bucket_prices(
            [10.0, 11.0, 12.0], [0.8, 0.5, 0.2]
        )
        store = PositionStore()
        delta = aggregate_delta(store, bp, "KXSOYBEANMON-26MAY01")
        assert delta == 0.0

    def test_single_long_position_positive_delta(self):
        """Long position in a binary -> positive delta."""
        strikes = np.array([10.0, 11.0, 12.0])
        survival = np.array([0.8, 0.5, 0.2])
        bp = _make_bucket_prices(strikes, survival)

        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-11",
            side="yes", action="buy", count=10,
            price_cents=50, fill_id="f1",
        ))

        delta = aggregate_delta(store, bp, "KXSOYBEANMON-26MAY01")
        # density at strike=11 should be positive
        assert delta > 0

    def test_short_position_negative_delta(self):
        """Short position -> negative delta."""
        strikes = np.array([10.0, 11.0, 12.0])
        survival = np.array([0.8, 0.5, 0.2])
        bp = _make_bucket_prices(strikes, survival)

        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26MAY01-11",
            side="yes", action="sell", count=10,
            price_cents=50, fill_id="f1",
        ))

        delta = aggregate_delta(store, bp, "KXSOYBEANMON-26MAY01")
        assert delta < 0

    def test_filters_by_event(self):
        """Only positions in the specified event contribute."""
        bp = _make_bucket_prices([10.0, 11.0, 12.0], [0.8, 0.5, 0.2])
        store = PositionStore()

        # Position in a different event
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANMON-26JUN01-11",
            side="yes", action="buy", count=10,
            price_cents=50, fill_id="f1",
        ))

        delta = aggregate_delta(store, bp, "KXSOYBEANMON-26MAY01")
        assert delta == 0.0


class TestExtractStrike:
    def test_valid_ticker(self):
        assert _extract_strike("KXSOYBEANMON-26MAY01-11") == 11.0

    def test_large_strike(self):
        assert _extract_strike("KXSOYBEANMON-26MAY01-1050") == 1050.0

    def test_invalid_format(self):
        assert _extract_strike("INVALID") is None

    def test_non_numeric_strike(self):
        assert _extract_strike("KXSOYBEANMON-26MAY01-ABC") is None


# ═══════════════════════════════════════════════════════════════════════
# Trigger tests
# ═══════════════════════════════════════════════════════════════════════


class TestHedgeTrigger:
    def test_below_threshold_no_hedge(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=60.0)
        assert not trigger.should_hedge(2.5)

    def test_at_threshold_hedges(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=0.0)
        assert trigger.should_hedge(3.0)

    def test_above_threshold_hedges(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=0.0)
        assert trigger.should_hedge(5.0)

    def test_negative_delta_above_threshold(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=0.0)
        assert trigger.should_hedge(-4.0)

    def test_cooldown_prevents_hedge(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=60.0)
        now = 1000.0
        trigger.record_hedge(now=now)
        # 30s later, still in cooldown
        assert not trigger.should_hedge(5.0, now=now + 30.0)

    def test_cooldown_expires(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=60.0)
        now = 1000.0
        trigger.record_hedge(now=now)
        # 61s later, cooldown expired
        assert trigger.should_hedge(5.0, now=now + 61.0)

    def test_record_hedge_updates_time(self):
        trigger = HedgeTrigger(threshold=3.0, cooldown_s=60.0)
        trigger.record_hedge(now=500.0)
        assert trigger.last_hedge_time == 500.0

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="threshold"):
            HedgeTrigger(threshold=0.0)

    def test_invalid_cooldown_raises(self):
        with pytest.raises(ValueError, match="cooldown"):
            HedgeTrigger(cooldown_s=-1.0)


class TestHedgeTriggerKillSwitch:
    def test_ib_connected_no_fire(self):
        trigger = HedgeTrigger(threshold=3.0)
        kill_fn = trigger.make_kill_trigger(
            ib_connected_fn=lambda: True,
            delta_port_fn=lambda: 10.0,
        )
        result = kill_fn()
        assert not result.fired

    def test_ib_disconnected_below_threshold_no_fire(self):
        trigger = HedgeTrigger(threshold=3.0)
        kill_fn = trigger.make_kill_trigger(
            ib_connected_fn=lambda: False,
            delta_port_fn=lambda: 1.0,
        )
        result = kill_fn()
        assert not result.fired

    def test_ib_disconnected_above_threshold_fires(self):
        trigger = HedgeTrigger(threshold=3.0)
        kill_fn = trigger.make_kill_trigger(
            ib_connected_fn=lambda: False,
            delta_port_fn=lambda: 5.0,
        )
        result = kill_fn()
        assert result.fired
        assert result.name == "hedge_ib_disconnect"
        assert "5.00" in result.detail

    def test_ib_disconnected_negative_delta_fires(self):
        trigger = HedgeTrigger(threshold=3.0)
        kill_fn = trigger.make_kill_trigger(
            ib_connected_fn=lambda: False,
            delta_port_fn=lambda: -4.0,
        )
        result = kill_fn()
        assert result.fired


# ═══════════════════════════════════════════════════════════════════════
# IBKR Client tests (mocked)
# ═══════════════════════════════════════════════════════════════════════


class TestIBKRClient:
    def test_not_connected_raises_on_place_hedge(self):
        client = IBKRClient()
        with pytest.raises(HedgeConnectionError, match="Not connected"):
            asyncio.get_event_loop().run_until_complete(
                client.place_hedge("ZS", 1, "sell")
            )

    def test_not_connected_raises_on_get_position(self):
        client = IBKRClient()
        with pytest.raises(HedgeConnectionError, match="Not connected"):
            asyncio.get_event_loop().run_until_complete(
                client.get_position("ZS")
            )

    def test_not_connected_raises_on_get_market_data(self):
        client = IBKRClient()
        with pytest.raises(HedgeConnectionError, match="Not connected"):
            asyncio.get_event_loop().run_until_complete(
                client.get_market_data("ZS")
            )

    def test_invalid_side_raises(self):
        client = IBKRClient()
        client._connected = True
        client._ib = MagicMock()
        with pytest.raises(ValueError, match="side"):
            asyncio.get_event_loop().run_until_complete(
                client.place_hedge("ZS", 1, "invalid")
            )

    def test_invalid_quantity_raises(self):
        client = IBKRClient()
        client._connected = True
        client._ib = MagicMock()
        with pytest.raises(ValueError, match="quantity"):
            asyncio.get_event_loop().run_until_complete(
                client.place_hedge("ZS", 0, "buy")
            )

    def test_connected_property_default_false(self):
        client = IBKRClient()
        assert not client.connected

    @patch("hedge.ibkr_client.asyncio.ensure_future")
    def test_connect_failure_raises(self, mock_ensure):
        """Connection failure raises HedgeConnectionError."""
        client = IBKRClient()

        mock_ib = MagicMock()
        mock_ib.connectAsync = AsyncMock(side_effect=ConnectionRefusedError("refused"))

        mock_ib_module = MagicMock()
        mock_ib_module.IB.return_value = mock_ib

        with (
            patch.dict(sys.modules, {"ib_insync": mock_ib_module}),
            pytest.raises(HedgeConnectionError, match="Failed to connect"),
        ):
            asyncio.get_event_loop().run_until_complete(
                client.connect("127.0.0.1", 4002, 1)
            )

    def test_disconnect_cleans_up(self):
        client = IBKRClient()
        client._connected = True
        mock_ib = MagicMock()
        client._ib = mock_ib
        asyncio.get_event_loop().run_until_complete(client.disconnect())
        assert not client.connected
        assert client._ib is None
        mock_ib.disconnect.assert_called_once()

    def test_place_hedge_mocked(self):
        """Test place_hedge with a fully mocked ib_insync."""
        client = IBKRClient()
        client._connected = True

        mock_ib = MagicMock()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 42
        mock_trade.orderStatus.status = "Filled"
        mock_ib.placeOrder.return_value = mock_trade
        client._ib = mock_ib

        mock_future_cls = MagicMock()
        mock_order_cls = MagicMock()

        with (
            patch.dict("sys.modules", {
                "ib_insync": MagicMock(Future=mock_future_cls, MarketOrder=mock_order_cls),
            }),
            patch("hedge.ibkr_client.Future", mock_future_cls, create=True),
            patch("hedge.ibkr_client.MarketOrder", mock_order_cls, create=True),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                client.place_hedge("ZS", 2, "sell")
            )

        assert result["order_id"] == 42
        assert result["quantity"] == 2
        assert result["action"] == "SELL"

    def test_get_position_no_positions(self):
        """Empty positions returns 0."""
        client = IBKRClient()
        client._connected = True
        mock_ib = MagicMock()
        mock_ib.positions.return_value = []
        client._ib = mock_ib

        pos = asyncio.get_event_loop().run_until_complete(
            client.get_position("ZS")
        )
        assert pos == 0

    def test_get_position_with_match(self):
        """Returns position for matching symbol."""
        client = IBKRClient()
        client._connected = True
        mock_ib = MagicMock()
        mock_pos = MagicMock()
        mock_pos.contract.symbol = "ZS"
        mock_pos.position = -3
        mock_ib.positions.return_value = [mock_pos]
        client._ib = mock_ib

        pos = asyncio.get_event_loop().run_until_complete(
            client.get_position("ZS")
        )
        assert pos == -3
