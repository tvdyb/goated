"""Tests for SideLock semantics in ControlState.

Covers: lock/unlock mutations, lazy expiry on auto_unlock_at,
snapshot inclusion, runner-side check via is_side_locked().
"""

from __future__ import annotations

import time

import pytest

from lipmm.control import ControlState, SideLock


# ── lock / unlock basics ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lock_side_then_check() -> None:
    s = ControlState()
    assert s.is_side_locked("KX-T50", "bid") is False
    await s.lock_side("KX-T50", "bid", reason="test")
    assert s.is_side_locked("KX-T50", "bid") is True
    # Other (ticker, side) still unlocked
    assert s.is_side_locked("KX-T50", "ask") is False
    assert s.is_side_locked("KX-T75", "bid") is False


@pytest.mark.asyncio
async def test_lock_side_records_metadata() -> None:
    s = ControlState()
    await s.lock_side("KX-T50", "bid", reason="manual buy hold")
    lock = s.get_side_lock("KX-T50", "bid")
    assert lock is not None
    assert lock.mode == "lock"
    assert lock.reason == "manual buy hold"
    assert lock.locked_at > 0
    assert lock.auto_unlock_at is None


@pytest.mark.asyncio
async def test_unlock_side() -> None:
    s = ControlState()
    await s.lock_side("KX-T50", "bid")
    await s.unlock_side("KX-T50", "bid")
    assert s.is_side_locked("KX-T50", "bid") is False
    assert s.get_side_lock("KX-T50", "bid") is None


@pytest.mark.asyncio
async def test_lock_rejects_invalid_side() -> None:
    s = ControlState()
    with pytest.raises(ValueError):
        await s.lock_side("KX-T50", "invalid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_lock_rejects_unsupported_mode() -> None:
    """Phase 2 only supports mode='lock'; reduce_only is reserved for later."""
    s = ControlState()
    with pytest.raises(ValueError):
        await s.lock_side("KX-T50", "bid", mode="reduce_only")


@pytest.mark.asyncio
async def test_unlock_nonexistent_lock_is_noop() -> None:
    """Unlocking an unlocked side bumps version (operator action recorded)
    but doesn't error — caller doesn't need to check existence first."""
    s = ControlState()
    v0 = s.version
    await s.unlock_side("KX-T50", "bid")
    assert s.version == v0 + 1


# ── auto-expiry ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_unlock_at_lazy_expiry() -> None:
    """Lock with auto_unlock_at in the past → next is_side_locked check
    returns False AND the lock is cleared from state."""
    s = ControlState()
    past = time.time() - 100
    await s.lock_side("KX-T50", "bid", auto_unlock_at=past)
    # Lock is recorded
    assert s.get_side_lock("KX-T50", "bid") is not None
    # But the runner-facing check returns False (and lazily clears)
    assert s.is_side_locked("KX-T50", "bid") is False
    # State is cleaned up after the read
    assert s.get_side_lock("KX-T50", "bid") is None


@pytest.mark.asyncio
async def test_auto_unlock_at_future_still_locked() -> None:
    s = ControlState()
    future = time.time() + 1000
    await s.lock_side("KX-T50", "bid", auto_unlock_at=future)
    assert s.is_side_locked("KX-T50", "bid") is True


@pytest.mark.asyncio
async def test_is_side_locked_accepts_now_ts_param() -> None:
    """The runner passes now_ts to avoid repeated time() calls per cycle."""
    s = ControlState()
    expiry = 100.0
    await s.lock_side("KX-T50", "bid", auto_unlock_at=expiry)
    # Pass an "earlier" now_ts → still locked
    assert s.is_side_locked("KX-T50", "bid", now_ts=50.0) is True
    # Pass a "later" now_ts → expires
    assert s.is_side_locked("KX-T50", "bid", now_ts=150.0) is False


# ── snapshot inclusion ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_includes_locks() -> None:
    s = ControlState()
    await s.lock_side("KX-T50", "bid", reason="hedge")
    snap = s.snapshot()
    assert "side_locks" in snap
    assert len(snap["side_locks"]) == 1
    entry = snap["side_locks"][0]
    assert entry["ticker"] == "KX-T50"
    assert entry["side"] == "bid"
    assert entry["mode"] == "lock"
    assert entry["reason"] == "hedge"
    assert entry["auto_unlock_at"] is None


@pytest.mark.asyncio
async def test_snapshot_locks_sorted_for_determinism() -> None:
    s = ControlState()
    await s.lock_side("KX-T75", "ask")
    await s.lock_side("KX-T50", "bid")
    await s.lock_side("KX-T50", "ask")
    snap = s.snapshot()
    keys = [(e["ticker"], e["side"]) for e in snap["side_locks"]]
    assert keys == sorted(keys)
