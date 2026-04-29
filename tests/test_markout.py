"""Tests for engine.markout — per-bucket fill markout tracker."""

from __future__ import annotations

import pytest

from engine.markout import (
    HORIZON_1M,
    HORIZON_5M,
    HORIZON_30M,
    BucketMarkout,
    FillMarkout,
    MarkoutTracker,
)


# ---------------------------------------------------------------------------
# FillMarkout basics
# ---------------------------------------------------------------------------


class TestFillMarkout:
    def test_initial_snapshots_are_none(self) -> None:
        fm = FillMarkout(
            timestamp=100.0,
            market_ticker="MKT-A",
            side="buy",
            fill_price_cents=45,
            theo_at_fill_cents=46.0,
        )
        assert fm.snapshots[HORIZON_1M] is None
        assert fm.snapshots[HORIZON_5M] is None
        assert fm.snapshots[HORIZON_30M] is None
        assert not fm.is_complete

    def test_is_complete_when_all_snapped(self) -> None:
        fm = FillMarkout(
            timestamp=0.0,
            market_ticker="X",
            side="buy",
            fill_price_cents=50,
            theo_at_fill_cents=50.0,
            snapshots={HORIZON_1M: 1.0, HORIZON_5M: 2.0, HORIZON_30M: 3.0},
        )
        assert fm.is_complete


# ---------------------------------------------------------------------------
# MarkoutTracker — record and update
# ---------------------------------------------------------------------------


class TestMarkoutTracker:
    def test_record_fill_adds_to_active(self) -> None:
        t = MarkoutTracker()
        t.record_fill(100.0, "MKT-A", "buy", 45, 46.0)
        assert t.active_count() == 1
        assert t.completed_count() == 0

    def test_update_snaps_1m(self) -> None:
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)

        # At 60s, 1m horizon should snap
        t.update(60.0, {"MKT-A": 48.0})
        # Still active (5m and 30m not snapped yet)
        assert t.active_count() == 1
        assert t.completed_count() == 0

    def test_update_completes_all_horizons(self) -> None:
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)

        # Snap all at once by jumping past 30m
        t.update(1801.0, {"MKT-A": 50.0})
        assert t.active_count() == 0
        assert t.completed_count() == 1

    def test_buy_positive_markout(self) -> None:
        """Buy fill, theo goes up -> positive markout (good fill)."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)
        t.update(1801.0, {"MKT-A": 50.0})

        stats = t.bucket_stats()
        assert len(stats) == 1
        bs = stats[0]
        assert bs.market_ticker == "MKT-A"
        # markout = theo_now - theo_at_fill = 50 - 46 = +4
        assert bs.avg_1m == pytest.approx(4.0)
        assert bs.avg_5m == pytest.approx(4.0)
        assert bs.avg_30m == pytest.approx(4.0)

    def test_buy_negative_markout(self) -> None:
        """Buy fill, theo goes down -> negative markout (adverse selection)."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)
        t.update(1801.0, {"MKT-A": 42.0})

        stats = t.bucket_stats()
        bs = stats[0]
        # markout = 42 - 46 = -4
        assert bs.avg_1m == pytest.approx(-4.0)

    def test_sell_positive_markout(self) -> None:
        """Sell fill, theo goes down -> positive markout (good fill)."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "sell", 55, 54.0)
        t.update(1801.0, {"MKT-A": 50.0})

        stats = t.bucket_stats()
        bs = stats[0]
        # raw = 50 - 54 = -4, negated for sell -> +4
        assert bs.avg_5m == pytest.approx(4.0)

    def test_sell_negative_markout(self) -> None:
        """Sell fill, theo goes up -> negative markout (adverse selection)."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "sell", 55, 54.0)
        t.update(1801.0, {"MKT-A": 58.0})

        stats = t.bucket_stats()
        bs = stats[0]
        # raw = 58 - 54 = +4, negated for sell -> -4
        assert bs.avg_5m == pytest.approx(-4.0)

    def test_incremental_snapping(self) -> None:
        """Snapshots happen at appropriate horizons, not all at once."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 50, 50.0)

        # At 60s with theo=52: snap 1m=+2
        t.update(60.0, {"MKT-A": 52.0})
        assert t.active_count() == 1

        # At 300s with theo=48: snap 5m=-2
        t.update(300.0, {"MKT-A": 48.0})
        assert t.active_count() == 1

        # At 1800s with theo=51: snap 30m=+1
        t.update(1800.0, {"MKT-A": 51.0})
        assert t.active_count() == 0
        assert t.completed_count() == 1

        stats = t.bucket_stats()
        bs = stats[0]
        assert bs.avg_1m == pytest.approx(2.0)
        assert bs.avg_5m == pytest.approx(-2.0)
        assert bs.avg_30m == pytest.approx(1.0)

    def test_multiple_fills_same_bucket(self) -> None:
        """Average markout across multiple fills in the same bucket."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)
        t.record_fill(1.0, "MKT-A", "buy", 44, 44.0)

        # Both complete at 1801s
        t.update(1802.0, {"MKT-A": 50.0})
        assert t.completed_count() == 2

        stats = t.bucket_stats()
        bs = stats[0]
        # Fill 1: 50 - 46 = +4
        # Fill 2: 50 - 44 = +6
        # avg = 5.0
        assert bs.avg_5m == pytest.approx(5.0)
        assert bs.n_fills == 2

    def test_multiple_buckets(self) -> None:
        """Stats computed separately per bucket."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 45, 46.0)
        t.record_fill(0.0, "MKT-B", "sell", 55, 54.0)

        t.update(1801.0, {"MKT-A": 50.0, "MKT-B": 50.0})

        stats = t.bucket_stats()
        assert len(stats) == 2
        by_ticker = {bs.market_ticker: bs for bs in stats}
        # MKT-A buy: 50 - 46 = +4
        assert by_ticker["MKT-A"].avg_5m == pytest.approx(4.0)
        # MKT-B sell: -(50 - 54) = +4
        assert by_ticker["MKT-B"].avg_5m == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Toxic strike detection
# ---------------------------------------------------------------------------


class TestToxicStrikes:
    def test_no_toxic_when_no_fills(self) -> None:
        t = MarkoutTracker()
        assert t.get_toxic_strikes() == []

    def test_toxic_strike_detected(self) -> None:
        t = MarkoutTracker()
        # Two fills with bad markout
        t.record_fill(0.0, "MKT-TOXIC", "buy", 50, 50.0)
        t.record_fill(1.0, "MKT-TOXIC", "buy", 50, 50.0)
        t.update(1802.0, {"MKT-TOXIC": 45.0})  # markout = -5c

        toxic = t.get_toxic_strikes()
        assert "MKT-TOXIC" in toxic

    def test_good_strike_not_toxic(self) -> None:
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-GOOD", "buy", 50, 50.0)
        t.record_fill(1.0, "MKT-GOOD", "buy", 50, 50.0)
        t.update(1802.0, {"MKT-GOOD": 55.0})  # markout = +5c

        toxic = t.get_toxic_strikes()
        assert toxic == []

    def test_single_fill_not_toxic(self) -> None:
        """Need at least 2 fills to declare toxic."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-X", "buy", 50, 50.0)
        t.update(1801.0, {"MKT-X": 40.0})  # markout = -10c but only 1 fill

        toxic = t.get_toxic_strikes()
        assert toxic == []

    def test_custom_toxic_threshold(self) -> None:
        t = MarkoutTracker(toxic_threshold_cents=-5.0)
        t.record_fill(0.0, "MKT-X", "buy", 50, 50.0)
        t.record_fill(1.0, "MKT-X", "buy", 50, 50.0)
        t.update(1802.0, {"MKT-X": 47.0})  # markout = -3c

        # -3c > -5c threshold, so NOT toxic
        toxic = t.get_toxic_strikes()
        assert toxic == []


# ---------------------------------------------------------------------------
# Rolling window pruning
# ---------------------------------------------------------------------------


class TestRollingWindow:
    def test_old_fills_pruned(self) -> None:
        t = MarkoutTracker(rolling_window_s=3600.0)
        t.record_fill(0.0, "MKT-A", "buy", 50, 50.0)
        t.update(1801.0, {"MKT-A": 52.0})  # complete at t=1801

        assert t.completed_count() == 1

        # Now update well past the rolling window (fill at t=0, window=3600)
        t.update(3700.0, {"MKT-A": 52.0})
        assert t.completed_count() == 0

    def test_recent_fills_kept(self) -> None:
        t = MarkoutTracker(rolling_window_s=3600.0)
        t.record_fill(1000.0, "MKT-A", "buy", 50, 50.0)
        t.update(2801.0, {"MKT-A": 52.0})

        # Fill at t=1000, window=3600, cutoff=2801-3600=-799 -> fill kept
        assert t.completed_count() == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_missing_theo_skips_fill(self) -> None:
        """If theo is not available for a ticker, fill stays active."""
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 50, 50.0)
        t.update(1801.0, {"MKT-B": 55.0})  # MKT-A not in theo map
        assert t.active_count() == 1
        assert t.completed_count() == 0

    def test_zero_markout(self) -> None:
        t = MarkoutTracker()
        t.record_fill(0.0, "MKT-A", "buy", 50, 50.0)
        t.update(1801.0, {"MKT-A": 50.0})

        stats = t.bucket_stats()
        assert stats[0].avg_5m == pytest.approx(0.0)

    def test_empty_bucket_stats(self) -> None:
        t = MarkoutTracker()
        assert t.bucket_stats() == []
