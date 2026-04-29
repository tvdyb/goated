"""Tests for feeds.kalshi.lip_score -- LIP Score Tracker.

Covers:
  - Distance multiplier at various distances
  - Score computation with known orders and orderbook
  - Projected share calculation (normal, zero-total, single-participant)
  - Rolling window stats
  - Target Size threshold detection
  - Edge cases: empty orderbook, no competitors, all orders outside decay
"""

from __future__ import annotations

import numpy as np
import pytest

from feeds.kalshi.lip_score import (
    DEFAULT_DECAY_TICKS,
    LIPScoreTracker,
    MarketOrderbook,
    MarketOrderbookError,
    OrderbookSide,
    RestingOrder,
    RollingScoreWindow,
    ScoreSnapshot,
    _compute_score_array,
    distance_multiplier,
)

MARKET = "KXSOYBEANW-26APR27-17"

# ── distance_multiplier tests ──────────────────────────────────────


class TestDistanceMultiplier:
    """Distance multiplier function at various distances."""

    def test_at_best(self) -> None:
        assert distance_multiplier(50, 50) == 1.0

    def test_one_tick_away(self) -> None:
        # Default decay_ticks=5: 1 tick away => 1 - 1/5 = 0.8
        assert distance_multiplier(49, 50) == pytest.approx(0.8)
        assert distance_multiplier(51, 50) == pytest.approx(0.8)

    def test_mid_decay(self) -> None:
        # 3 ticks away with decay=5 => 1 - 3/5 = 0.4
        assert distance_multiplier(47, 50, decay_ticks=5) == pytest.approx(0.4)

    def test_at_boundary(self) -> None:
        # Exactly at decay_ticks => 0.0
        assert distance_multiplier(45, 50, decay_ticks=5) == 0.0

    def test_beyond_boundary(self) -> None:
        # Beyond decay_ticks => 0.0
        assert distance_multiplier(40, 50, decay_ticks=5) == 0.0

    def test_decay_one_tick(self) -> None:
        # decay_ticks=1: only at-best counts
        assert distance_multiplier(50, 50, decay_ticks=1) == 1.0
        assert distance_multiplier(49, 50, decay_ticks=1) == 0.0

    def test_large_decay(self) -> None:
        # decay_ticks=100: 10 ticks away => 1 - 10/100 = 0.9
        assert distance_multiplier(40, 50, decay_ticks=100) == pytest.approx(0.9)

    def test_invalid_decay(self) -> None:
        with pytest.raises(ValueError, match="decay_ticks must be >= 1"):
            distance_multiplier(50, 50, decay_ticks=0)

    def test_symmetric(self) -> None:
        """Multiplier is symmetric around best price."""
        for d in range(10):
            assert distance_multiplier(50 - d, 50) == distance_multiplier(50 + d, 50)


# ── _compute_score_array tests ─────────────────────────────────────


class TestComputeScoreArray:
    """Numba-accelerated score array computation."""

    def test_single_order_at_best(self) -> None:
        prices = np.array([50], dtype=np.int32)
        sizes = np.array([100.0], dtype=np.float64)
        score = _compute_score_array(prices, sizes, 50, 5)
        assert score == pytest.approx(100.0)

    def test_multiple_orders(self) -> None:
        # Order at best: 100 * 1.0 = 100
        # Order 2 ticks away: 50 * 0.6 = 30
        prices = np.array([50, 48], dtype=np.int32)
        sizes = np.array([100.0, 50.0], dtype=np.float64)
        score = _compute_score_array(prices, sizes, 50, 5)
        assert score == pytest.approx(130.0)

    def test_all_outside_decay(self) -> None:
        prices = np.array([10, 20], dtype=np.int32)
        sizes = np.array([100.0, 200.0], dtype=np.float64)
        score = _compute_score_array(prices, sizes, 50, 5)
        assert score == pytest.approx(0.0)

    def test_empty_arrays(self) -> None:
        prices = np.array([], dtype=np.int32)
        sizes = np.array([], dtype=np.float64)
        score = _compute_score_array(prices, sizes, 50, 5)
        assert score == pytest.approx(0.0)


# ── OrderbookSide tests ───────────────────────────────────────────


class TestOrderbookSide:
    """OrderbookSide state management."""

    def test_empty_best_price(self) -> None:
        side = OrderbookSide()
        assert side.best_price is None

    def test_set_level_and_best(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.set_level(48, 50.0)
        assert side.best_price == 50

    def test_apply_delta(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.apply_delta(50, -30.0)
        assert side.levels[50] == pytest.approx(70.0)

    def test_apply_delta_removes_zero(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.apply_delta(50, -100.0)
        assert 50 not in side.levels

    def test_total_size(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.set_level(48, 50.0)
        assert side.total_size() == pytest.approx(150.0)

    def test_to_arrays_empty(self) -> None:
        side = OrderbookSide()
        prices, sizes = side.to_arrays()
        assert len(prices) == 0
        assert len(sizes) == 0

    def test_to_arrays(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.set_level(48, 50.0)
        prices, sizes = side.to_arrays()
        assert len(prices) == 2
        assert set(prices.tolist()) == {48, 50}

    def test_clear(self) -> None:
        side = OrderbookSide()
        side.set_level(50, 100.0)
        side.clear()
        assert side.best_price is None


# ── MarketOrderbook tests ─────────────────────────────────────────


class TestMarketOrderbook:
    """MarketOrderbook best bid/ask derivation."""

    def test_best_bid(self) -> None:
        ob = MarketOrderbook(market_ticker=MARKET)
        ob.yes_side.set_level(50, 100.0)
        ob.yes_side.set_level(48, 50.0)
        assert ob.best_bid_cents() == 50

    def test_best_ask_from_no_side(self) -> None:
        ob = MarketOrderbook(market_ticker=MARKET)
        ob.no_side.set_level(52, 100.0)  # No price 52 => Yes ask = 100 - 52 = 48
        assert ob.best_ask_cents() == 48

    def test_no_bid_raises(self) -> None:
        ob = MarketOrderbook(market_ticker=MARKET)
        with pytest.raises(MarketOrderbookError, match="No yes-side bid"):
            ob.best_bid_cents()

    def test_no_ask_raises(self) -> None:
        ob = MarketOrderbook(market_ticker=MARKET)
        with pytest.raises(MarketOrderbookError, match="No ask levels"):
            ob.best_ask_cents()


# ── LIPScoreTracker tests ─────────────────────────────────────────


def _make_tracker(
    target_size: float = 100.0,
    decay_ticks: int = 5,
    pool_size_usd: float = 500.0,
) -> LIPScoreTracker:
    """Create a tracker with a standard orderbook setup."""
    t = LIPScoreTracker(
        market_ticker=MARKET,
        target_size=target_size,
        decay_ticks=decay_ticks,
        pool_size_usd=pool_size_usd,
    )
    # Set up orderbook: yes bids at 50 (200 size), 48 (100 size)
    #                   no bids at 52 (150 size), 54 (100 size)
    t.orderbook.yes_side.set_level(50, 200.0)
    t.orderbook.yes_side.set_level(48, 100.0)
    t.orderbook.no_side.set_level(52, 150.0)
    t.orderbook.no_side.set_level(54, 100.0)
    t.orderbook.mark_updated()
    return t


class TestLIPScoreTracker:
    """Score computation and snapshot generation."""

    def test_our_score_at_best(self) -> None:
        t = _make_tracker()
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 50.0),
        ])
        # Our order at best bid (50): 50 * 1.0 = 50.0
        assert t.compute_our_score() == pytest.approx(50.0)

    def test_our_score_off_best(self) -> None:
        t = _make_tracker()
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 48, 100.0),
        ])
        # Best bid = 50, order at 48 => dist=2, mult=1-2/5=0.6
        # Score = 100 * 0.6 = 60.0
        assert t.compute_our_score() == pytest.approx(60.0)

    def test_our_score_both_sides(self) -> None:
        t = _make_tracker()
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 50.0),
            RestingOrder("o2", MARKET, "no", 52, 30.0),
        ])
        # Yes: 50 * 1.0 = 50.0 (best bid=50)
        # No: best_no=54 (highest no level), order at 52 => dist=2, mult=0.6
        # No score: 30 * 0.6 = 18.0
        assert t.compute_our_score() == pytest.approx(68.0)

    def test_total_score(self) -> None:
        t = _make_tracker()
        # Yes side: best=50. level 50 (200 sz, dist=0, mult=1.0) + level 48 (100 sz, dist=2, mult=0.6)
        # Yes total = 200*1.0 + 100*0.6 = 260.0
        # No side: best=54 (highest). level 54 (100 sz, dist=0, mult=1.0) + level 52 (150 sz, dist=2, mult=0.6)
        # No total = 100*1.0 + 150*0.6 = 190.0
        expected = 260.0 + 190.0  # 450.0
        assert t.compute_total_score() == pytest.approx(expected)

    def test_projected_share(self) -> None:
        t = _make_tracker()
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 50.0),
        ])
        snap = t.compute_snapshot(timestamp_ns=1_000_000)
        # our=50, total=450
        assert snap.our_score == pytest.approx(50.0)
        assert snap.total_score == pytest.approx(450.0)
        assert snap.projected_share == pytest.approx(50.0 / 450.0)

    def test_zero_total_score(self) -> None:
        """When orderbook is empty on both sides, total_score=0 and share=0."""
        t = LIPScoreTracker(market_ticker=MARKET)
        # No orderbook levels => compute_total_score returns 0
        assert t.compute_total_score() == 0.0

    def test_snapshot_zero_total_share(self) -> None:
        """Snapshot with no orderbook => share = 0.0, not division error."""
        t = LIPScoreTracker(market_ticker=MARKET)
        # No orders, no orderbook => our_score=0, total=0, share=0
        snap = t.compute_snapshot(timestamp_ns=1_000_000)
        assert snap.projected_share == 0.0

    def test_no_our_orders(self) -> None:
        t = _make_tracker()
        assert t.compute_our_score() == pytest.approx(0.0)

    def test_order_ticker_mismatch_raises(self) -> None:
        t = _make_tracker()
        with pytest.raises(ValueError, match="expected"):
            t.set_our_orders([
                RestingOrder("o1", "WRONG-TICKER", "yes", 50, 50.0),
            ])

    def test_invalid_decay_ticks(self) -> None:
        with pytest.raises(ValueError, match="decay_ticks"):
            LIPScoreTracker(market_ticker=MARKET, decay_ticks=0)

    def test_invalid_target_size(self) -> None:
        with pytest.raises(ValueError, match="target_size"):
            LIPScoreTracker(market_ticker=MARKET, target_size=-1)


# ── Target Size threshold tests ────────────────────────────────────


class TestTargetSize:
    """Target Size threshold detection."""

    def test_below_target(self) -> None:
        t = _make_tracker(target_size=200.0)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 100.0),
        ])
        assert t.below_target_size("yes") is True

    def test_at_target(self) -> None:
        t = _make_tracker(target_size=100.0)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 100.0),
        ])
        assert t.below_target_size("yes") is False

    def test_above_target(self) -> None:
        t = _make_tracker(target_size=100.0)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 150.0),
        ])
        assert t.below_target_size("yes") is False

    def test_no_orders_below_target(self) -> None:
        t = _make_tracker(target_size=100.0)
        assert t.below_target_size("yes") is True
        assert t.below_target_size("no") is True

    def test_snapshot_flags(self) -> None:
        t = _make_tracker(target_size=200.0)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 100.0),
            RestingOrder("o2", MARKET, "no", 52, 300.0),
        ])
        snap = t.compute_snapshot(timestamp_ns=1_000_000)
        assert snap.below_target_yes is True   # 100 < 200
        assert snap.below_target_no is False    # 300 >= 200


# ── Rolling window tests ──────────────────────────────────────────


class TestRollingScoreWindow:
    """Rolling window statistics."""

    def test_empty_window(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        assert w.count == 0
        assert w.mean_share() == 0.0
        assert w.std_share() == 0.0

    def test_single_entry(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, our_score=50.0, total_score=100.0)
        assert w.count == 1
        assert w.mean_share() == pytest.approx(0.5)
        assert w.std_share() == 0.0  # need >= 2 for std

    def test_multiple_entries(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 100.0)   # share = 0.5
        w.add(200, 30.0, 100.0)   # share = 0.3
        w.add(300, 40.0, 100.0)   # share = 0.4
        assert w.count == 3
        assert w.mean_share() == pytest.approx(0.4)

    def test_window_eviction(self) -> None:
        w = RollingScoreWindow(window_ns=1000)
        w.add(100, 50.0, 100.0)
        w.add(200, 30.0, 100.0)
        # Now add at timestamp 1200 => window back to 200, so ts=100 gets evicted
        w.add(1200, 40.0, 100.0)
        assert w.count == 2  # ts=200 and ts=1200

    def test_zero_total_excluded_from_share(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 0.0)    # total=0, excluded
        w.add(200, 30.0, 100.0)  # share = 0.3
        assert w.mean_share() == pytest.approx(0.3)

    def test_all_zero_total(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 0.0)
        w.add(200, 30.0, 0.0)
        assert w.mean_share() == 0.0

    def test_mean_our_score(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 100.0)
        w.add(200, 30.0, 100.0)
        assert w.mean_our_score() == pytest.approx(40.0)

    def test_mean_total_score(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 200.0)
        w.add(200, 30.0, 100.0)
        assert w.mean_total_score() == pytest.approx(150.0)

    def test_std_share(self) -> None:
        w = RollingScoreWindow(window_ns=1_000_000)
        w.add(100, 50.0, 100.0)  # 0.5
        w.add(200, 30.0, 100.0)  # 0.3
        expected_std = float(np.std([0.5, 0.3], ddof=1))
        assert w.std_share() == pytest.approx(expected_std)


# ── Projected reward tests ─────────────────────────────────────────


class TestProjectedReward:
    """Projected reward computation from rolling window."""

    def test_projected_reward(self) -> None:
        t = _make_tracker(pool_size_usd=500.0)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 50.0),
        ])
        # Compute a few snapshots to populate the window
        for i in range(3):
            t.compute_snapshot(timestamp_ns=i * 1_000_000)

        reward = t.projected_reward()
        # share ~ 50/450 ~ 0.1111
        expected = (50.0 / 450.0) * 500.0
        assert reward == pytest.approx(expected, rel=1e-3)

    def test_projected_reward_empty(self) -> None:
        t = _make_tracker(pool_size_usd=500.0)
        assert t.projected_reward() == 0.0


# ── Telemetry callback tests ──────────────────────────────────────


class TestTelemetryCallbacks:
    """Telemetry emission via callbacks."""

    def test_callback_called(self) -> None:
        t = _make_tracker()
        received: list[ScoreSnapshot] = []
        t.on_telemetry(received.append)
        t.compute_snapshot(timestamp_ns=1_000_000)
        assert len(received) == 1
        assert received[0].market_ticker == MARKET

    def test_multiple_callbacks(self) -> None:
        t = _make_tracker()
        a: list[ScoreSnapshot] = []
        b: list[ScoreSnapshot] = []
        t.on_telemetry(a.append)
        t.on_telemetry(b.append)
        t.compute_snapshot(timestamp_ns=1_000_000)
        assert len(a) == 1
        assert len(b) == 1


# ── Edge case tests ────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for score computation."""

    def test_all_orders_outside_decay(self) -> None:
        t = _make_tracker(decay_ticks=1)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 48, 100.0),  # 2 ticks from best=50
        ])
        assert t.compute_our_score() == pytest.approx(0.0)

    def test_empty_orderbook_our_score_zero(self) -> None:
        """Empty orderbook, no orders => our score is 0."""
        t = LIPScoreTracker(market_ticker=MARKET)
        assert t.compute_our_score() == 0.0

    def test_our_orders_but_no_orderbook_raises(self) -> None:
        """If we have orders but orderbook is empty, best_bid raises."""
        t = LIPScoreTracker(market_ticker=MARKET)
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 100.0),
        ])
        with pytest.raises(MarketOrderbookError):
            t.compute_our_score()

    def test_no_competitors_full_share(self) -> None:
        """When our orders are the only ones, share = 1.0."""
        t = LIPScoreTracker(market_ticker=MARKET, target_size=50.0)
        # Orderbook contains only our orders
        t.orderbook.yes_side.set_level(50, 100.0)
        t.orderbook.no_side.set_level(52, 80.0)
        t.orderbook.mark_updated()
        t.set_our_orders([
            RestingOrder("o1", MARKET, "yes", 50, 100.0),
            RestingOrder("o2", MARKET, "no", 52, 80.0),
        ])
        snap = t.compute_snapshot(timestamp_ns=1)
        # our_score == total_score => share = 1.0
        assert snap.projected_share == pytest.approx(1.0)

    def test_snapshot_populates_rolling_windows(self) -> None:
        t = _make_tracker()
        t.set_our_orders([RestingOrder("o1", MARKET, "yes", 50, 50.0)])
        t.compute_snapshot(timestamp_ns=100)
        t.compute_snapshot(timestamp_ns=200)
        assert t.window_1h.count == 2
        assert t.window_1d.count == 2
