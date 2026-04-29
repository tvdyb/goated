"""Tests for engine/taker_imbalance.py — taker-imbalance detector."""

from __future__ import annotations

import pytest

from engine.taker_imbalance import (
    ImbalanceConfig,
    ImbalanceSignal,
    TakerImbalanceDetector,
)


class TestRecordTrade:
    def test_buy_initiated(self):
        """Trade above mid should register as buy-initiated."""
        d = TakerImbalanceDetector()
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        ratio, buys, sells = d.compute_imbalance(100.0)
        assert buys == 1
        assert sells == 0

    def test_sell_initiated(self):
        """Trade below mid should register as sell-initiated."""
        d = TakerImbalanceDetector()
        d.record_trade(price_cents=45, mid_cents=50, now=100.0)
        ratio, buys, sells = d.compute_imbalance(100.0)
        assert buys == 0
        assert sells == 1

    def test_at_mid_skipped(self):
        """Trade at mid should be skipped (ambiguous)."""
        d = TakerImbalanceDetector()
        d.record_trade(price_cents=50, mid_cents=50, now=100.0)
        ratio, buys, sells = d.compute_imbalance(100.0)
        assert buys == 0
        assert sells == 0


class TestComputeImbalance:
    def test_balanced_trades(self):
        """Equal buys and sells -> ratio near 0."""
        d = TakerImbalanceDetector(ImbalanceConfig(min_trades=2))
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        d.record_trade(price_cents=45, mid_cents=50, now=101.0)
        ratio, buys, sells = d.compute_imbalance(102.0)
        assert buys == 1
        assert sells == 1
        assert ratio == pytest.approx(0.0)

    def test_fully_imbalanced(self):
        """All buys -> ratio = 1.0."""
        config = ImbalanceConfig(min_trades=3)
        d = TakerImbalanceDetector(config)
        for i in range(5):
            d.record_trade(price_cents=55, mid_cents=50, now=100.0 + i)
        ratio, buys, sells = d.compute_imbalance(105.0)
        assert buys == 5
        assert sells == 0
        assert ratio == pytest.approx(1.0)

    def test_below_min_trades(self):
        """Too few trades -> ratio = 0.0."""
        config = ImbalanceConfig(min_trades=5)
        d = TakerImbalanceDetector(config)
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        ratio, buys, sells = d.compute_imbalance(100.0)
        assert ratio == 0.0

    def test_window_expiry(self):
        """Old trades outside window should be pruned."""
        config = ImbalanceConfig(window_seconds=10.0, min_trades=1)
        d = TakerImbalanceDetector(config)
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        d.record_trade(price_cents=55, mid_cents=50, now=105.0)

        # At t=112, only the second trade should remain
        ratio, buys, sells = d.compute_imbalance(112.0)
        assert buys == 1
        assert sells == 0


class TestCurrentSignal:
    def test_no_signal_when_balanced(self):
        """No signal when trades are balanced."""
        config = ImbalanceConfig(min_trades=2, threshold=0.7)
        d = TakerImbalanceDetector(config)
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        d.record_trade(price_cents=45, mid_cents=50, now=101.0)
        signal = d.current_signal(102.0)
        assert signal is None

    def test_buy_imbalance_withdraws_ask(self):
        """Strong buy imbalance -> withdraw ask side."""
        config = ImbalanceConfig(min_trades=3, threshold=0.6)
        d = TakerImbalanceDetector(config)
        for i in range(5):
            d.record_trade(price_cents=55, mid_cents=50, now=100.0 + i)
        signal = d.current_signal(105.0)
        assert signal is not None
        assert signal.withdraw_side == "ask"
        assert signal.ratio >= 0.6

    def test_sell_imbalance_withdraws_bid(self):
        """Strong sell imbalance -> withdraw bid side."""
        config = ImbalanceConfig(min_trades=3, threshold=0.6)
        d = TakerImbalanceDetector(config)
        for i in range(5):
            d.record_trade(price_cents=45, mid_cents=50, now=100.0 + i)
        signal = d.current_signal(105.0)
        assert signal is not None
        assert signal.withdraw_side == "bid"

    def test_signal_persists_during_cooldown(self):
        """Signal should persist after imbalance drops below threshold."""
        config = ImbalanceConfig(
            min_trades=3,
            threshold=0.6,
            cooldown_seconds=60.0,
            window_seconds=10.0,
        )
        d = TakerImbalanceDetector(config)

        # Create imbalance at t=100
        for i in range(5):
            d.record_trade(price_cents=55, mid_cents=50, now=100.0 + i)

        signal1 = d.current_signal(105.0)
        assert signal1 is not None

        # At t=120, the trades are outside the 10s window but cooldown persists
        signal2 = d.current_signal(120.0)
        assert signal2 is not None
        assert signal2.withdraw_side == signal1.withdraw_side

    def test_signal_expires_after_cooldown(self):
        """Signal should expire after cooldown."""
        config = ImbalanceConfig(
            min_trades=3,
            threshold=0.6,
            cooldown_seconds=30.0,
            window_seconds=10.0,
        )
        d = TakerImbalanceDetector(config)

        for i in range(5):
            d.record_trade(price_cents=55, mid_cents=50, now=100.0 + i)

        signal1 = d.current_signal(105.0)
        assert signal1 is not None

        # After cooldown (105 + 30 = 135), signal should expire
        signal2 = d.current_signal(140.0)
        assert signal2 is None


class TestReset:
    def test_reset_clears_state(self):
        config = ImbalanceConfig(min_trades=1)
        d = TakerImbalanceDetector(config)
        d.record_trade(price_cents=55, mid_cents=50, now=100.0)
        d.reset()
        ratio, buys, sells = d.compute_imbalance(100.0)
        assert buys == 0
        assert sells == 0
        assert d.current_signal(100.0) is None
