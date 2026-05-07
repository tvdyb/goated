"""Tests for the lipmm fill-markout tracker (lipmm/observability/markout.py)."""

from __future__ import annotations

import asyncio

import pytest

from lipmm.observability.markout import MarkoutTracker, _Fill


def _stub_mid_hook_factory(values_per_call: list[float | None]):
    """Returns an async hook that yields successive values from the
    provided list, then None thereafter."""
    state = {"i": 0}

    async def _hook(ticker: str) -> float | None:
        i = state["i"]
        state["i"] += 1
        if i < len(values_per_call):
            return values_per_call[i]
        return None
    return _hook


# ── observe_position_delta ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_delta_no_fill_recorded() -> None:
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    fill = await tracker.observe_position_delta(
        "KX-T1", prev_qty=10, cur_qty=10, mid_c=50.0,
    )
    assert fill is None
    assert tracker.all_fills() == []


@pytest.mark.asyncio
async def test_delta_with_no_mid_skips_silently() -> None:
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    fill = await tracker.observe_position_delta(
        "KX-T1", prev_qty=0, cur_qty=5, mid_c=None,
    )
    assert fill is None


@pytest.mark.asyncio
async def test_positive_delta_recorded_as_bid_side() -> None:
    """Position went from 0 to +5 → we BOUGHT yes. Side = bid."""
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    fill = await tracker.observe_position_delta(
        "KX-T1", prev_qty=0, cur_qty=5, mid_c=42.0, ts=1000.0,
    )
    assert fill is not None
    assert fill.side == "bid"
    assert fill.qty == 5
    assert fill.fill_price_c == 42.0


@pytest.mark.asyncio
async def test_negative_delta_recorded_as_ask_side() -> None:
    """Position went from +5 to 0 → we SOLD yes. Side = ask."""
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    fill = await tracker.observe_position_delta(
        "KX-T1", prev_qty=5, cur_qty=0, mid_c=58.0, ts=1000.0,
    )
    assert fill is not None
    assert fill.side == "ask"
    assert fill.qty == 5


# ── _Fill.markout math ─────────────────────────────────────────────


def test_markout_long_yes_signed_correctly() -> None:
    """Bought yes at 40¢. Mid moves to 45¢. We're +5¢ in our favor."""
    f = _Fill(ticker="X", side="bid", qty=1, fill_price_c=40.0, fill_ts=0.0)
    f.sample_1m_c = 45.0
    f.sample_5m_c = 50.0
    assert f.markout_1m_c() == 5.0
    assert f.markout_5m_c() == 10.0


def test_markout_long_no_signed_correctly() -> None:
    """Sold yes at 60¢ (= bought No at 40¢). Mid drops to 55¢ → we're
    +5¢ in our favor."""
    f = _Fill(ticker="X", side="ask", qty=1, fill_price_c=60.0, fill_ts=0.0)
    f.sample_1m_c = 55.0
    f.sample_5m_c = 50.0
    assert f.markout_1m_c() == 5.0
    assert f.markout_5m_c() == 10.0


def test_markout_returns_none_when_no_sample() -> None:
    f = _Fill(ticker="X", side="bid", qty=1, fill_price_c=40.0, fill_ts=0.0)
    assert f.markout_1m_c() is None
    assert f.markout_5m_c() is None


# ── snapshot aggregation ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_empty_when_no_fills() -> None:
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    assert tracker.snapshot() == []


@pytest.mark.asyncio
async def test_snapshot_aggregates_per_ticker() -> None:
    """Two fills on T1, one on T2; pre-populate samples without spawning
    real async tasks (we test aggregation, not the sampling loop)."""
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    f1 = _Fill(ticker="T1", side="bid", qty=1, fill_price_c=40.0, fill_ts=0.0)
    f1.sample_1m_c = 41.0
    f1.sample_5m_c = 42.0
    f2 = _Fill(ticker="T1", side="bid", qty=1, fill_price_c=40.0, fill_ts=0.0)
    f2.sample_1m_c = 39.0
    f2.sample_5m_c = 38.0
    f3 = _Fill(ticker="T2", side="ask", qty=2, fill_price_c=60.0, fill_ts=0.0)
    f3.sample_5m_c = 50.0
    tracker._fills = [f1, f2, f3]

    snap = tracker.snapshot()
    by = {s.ticker: s for s in snap}
    t1 = by["T1"]
    assert t1.n_fills == 2
    # 1m markouts: +1, -1 → mean 0
    assert t1.mean_1m_c == pytest.approx(0.0)
    # 5m markouts: +2, -2 → mean 0
    assert t1.mean_5m_c == pytest.approx(0.0)
    assert t1.n_with_5m == 2
    assert t1.toxic is False

    t2 = by["T2"]
    assert t2.n_fills == 1
    # ask side at 60, mid drops to 50 → +10 in our favor
    assert t2.mean_5m_c == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_snapshot_flags_toxic_when_mean_5m_below_threshold() -> None:
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    fills = []
    for _ in range(3):
        f = _Fill(ticker="TOXIC", side="bid", qty=1, fill_price_c=50.0, fill_ts=0.0)
        f.sample_5m_c = 47.0   # 3¢ adverse on each fill
        fills.append(f)
    tracker._fills = fills
    snap = tracker.snapshot()
    assert snap[0].toxic is True
    assert snap[0].mean_5m_c == pytest.approx(-3.0)


@pytest.mark.asyncio
async def test_snapshot_no_toxic_with_only_one_5m_sample() -> None:
    """Toxic flag requires n_with_5m >= 2 to avoid one-shot noise."""
    tracker = MarkoutTracker(_stub_mid_hook_factory([]))
    f = _Fill(ticker="MAYBE", side="bid", qty=1, fill_price_c=50.0, fill_ts=0.0)
    f.sample_5m_c = 30.0   # huge adverse but only 1 sample
    tracker._fills = [f]
    snap = tracker.snapshot()
    assert snap[0].toxic is False


# ── End-to-end: scheduled samples ──────────────────────────────────


@pytest.mark.asyncio
async def test_record_fill_schedules_samples_at_horizons() -> None:
    """Use fast horizons (50ms / 100ms) and a stub mid hook to verify
    the sampler populates fields end-to-end."""
    tracker = MarkoutTracker(
        _stub_mid_hook_factory([45.0, 47.0]),
        sample_horizons_s=(0.05, 0.10),
    )
    fill = await tracker.record_fill(
        ticker="KX-T1", side="bid", qty=1,
        fill_price_c=40.0, fill_ts=0.0,
    )
    await asyncio.sleep(0.20)
    assert fill.sample_1m_c == 45.0
    assert fill.sample_5m_c == 47.0
    assert fill.markout_1m_c() == 5.0
    assert fill.markout_5m_c() == 7.0


@pytest.mark.asyncio
async def test_shutdown_cancels_pending_samplers() -> None:
    """In-flight sampling tasks should be cleaned up on shutdown
    rather than leaking past process lifetime."""
    tracker = MarkoutTracker(
        _stub_mid_hook_factory([]),
        sample_horizons_s=(60.0, 120.0),  # long horizons; we'll cancel
    )
    await tracker.record_fill(
        ticker="KX-T1", side="bid", qty=1,
        fill_price_c=40.0, fill_ts=0.0,
    )
    assert len(tracker._tasks) == 1
    await tracker.shutdown()
    assert len(tracker._tasks) == 0
