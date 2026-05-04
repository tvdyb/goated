"""Tests for lipmm.control.state.ControlState.

Locks in the contract for pause-scope semantics, kill/arm flow, knob
override bounds, and the version counter.
"""

from __future__ import annotations

import pytest

from lipmm.control import ControlConfig, ControlState, KillState


# ── version counter ──────────────────────────────────────────────────


def test_initial_state() -> None:
    s = ControlState()
    assert s.version == 0
    assert s.kill_state() == KillState.OFF
    assert not s.is_global_paused()
    assert not s.is_killed()
    assert s.all_knobs() == {}


@pytest.mark.asyncio
async def test_every_mutation_bumps_version() -> None:
    s = ControlState()
    v0 = s.version
    await s.pause_global()
    assert s.version == v0 + 1
    await s.resume_global()
    assert s.version == v0 + 2
    await s.set_knob("min_theo_confidence", 0.5)
    assert s.version == v0 + 3
    await s.clear_knob("min_theo_confidence")
    assert s.version == v0 + 4


# ── pause scopes ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_global_pause_skips_cycle() -> None:
    s = ControlState()
    await s.pause_global()
    assert s.should_skip_cycle() is True
    assert s.should_skip_ticker("KX-T50") is True
    await s.resume_global()
    assert s.should_skip_cycle() is False


@pytest.mark.asyncio
async def test_ticker_pause_isolates_to_one_ticker() -> None:
    s = ControlState()
    await s.pause_ticker("KX-T50")
    assert s.should_skip_ticker("KX-T50") is True
    assert s.should_skip_ticker("KX-T75") is False
    await s.resume_ticker("KX-T50")
    assert s.should_skip_ticker("KX-T50") is False


@pytest.mark.asyncio
async def test_side_pause_isolates_to_one_side() -> None:
    s = ControlState()
    await s.pause_side("KX-T50", "bid")
    assert s.is_side_paused("KX-T50", "bid") is True
    assert s.is_side_paused("KX-T50", "ask") is False
    assert s.is_side_paused("KX-T75", "bid") is False
    # Ticker isn't paused — should_skip_ticker stays False
    assert s.should_skip_ticker("KX-T50") is False


@pytest.mark.asyncio
async def test_side_pause_rejects_invalid_side() -> None:
    s = ControlState()
    with pytest.raises(ValueError):
        await s.pause_side("KX-T50", "invalid")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resume_global_does_not_clear_ticker_pauses() -> None:
    """Operator pauses ticker X, then triggers global pause, then
    resumes global. Ticker X should still be paused."""
    s = ControlState()
    await s.pause_ticker("KX-T50")
    await s.pause_global()
    await s.resume_global()
    assert s.should_skip_ticker("KX-T50") is True


# ── kill / arm flow ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kill_implies_global_pause() -> None:
    s = ControlState()
    await s.kill()
    assert s.is_killed() is True
    assert s.should_skip_cycle() is True
    assert s.is_global_paused() is True


@pytest.mark.asyncio
async def test_arm_only_from_killed() -> None:
    s = ControlState()
    with pytest.raises(ValueError):
        await s.arm()  # not killed yet
    await s.kill()
    await s.arm()
    assert s.kill_state() == KillState.ARMED
    assert s.is_armed() is True
    assert s.is_killed() is False


@pytest.mark.asyncio
async def test_resume_after_kill_only_from_armed() -> None:
    s = ControlState()
    await s.kill()
    with pytest.raises(ValueError):
        await s.resume_after_kill()  # killed, not armed
    await s.arm()
    await s.resume_after_kill()
    assert s.kill_state() == KillState.OFF
    assert s.is_global_paused() is False


@pytest.mark.asyncio
async def test_full_kill_recovery_flow() -> None:
    s = ControlState()
    # Normal → kill → armed → resumed → normal
    assert s.kill_state() == KillState.OFF
    await s.kill()
    assert s.kill_state() == KillState.KILLED
    await s.arm()
    assert s.kill_state() == KillState.ARMED
    await s.resume_after_kill()
    assert s.kill_state() == KillState.OFF
    assert s.should_skip_cycle() is False


# ── knob overrides ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_knob_with_valid_value() -> None:
    s = ControlState()
    await s.set_knob("min_theo_confidence", 0.5)
    assert s.get_knob("min_theo_confidence") == 0.5


@pytest.mark.asyncio
async def test_set_knob_rejects_unknown_name() -> None:
    s = ControlState()
    with pytest.raises(ValueError):
        await s.set_knob("not_a_real_knob", 1.0)


@pytest.mark.asyncio
async def test_set_knob_rejects_out_of_bounds() -> None:
    s = ControlState()
    # min_theo_confidence bounds are [0, 1]
    with pytest.raises(ValueError):
        await s.set_knob("min_theo_confidence", 1.5)
    with pytest.raises(ValueError):
        await s.set_knob("min_theo_confidence", -0.1)


@pytest.mark.asyncio
async def test_clear_knob() -> None:
    s = ControlState()
    await s.set_knob("min_theo_confidence", 0.5)
    await s.clear_knob("min_theo_confidence")
    assert s.get_knob("min_theo_confidence") is None
    assert s.all_knobs() == {}


@pytest.mark.asyncio
async def test_control_overrides_for_strategy_returns_dict() -> None:
    s = ControlState()
    await s.set_knob("min_theo_confidence", 0.3)
    await s.set_knob("theo_tolerance_c", 5)
    overrides = s.control_overrides_for_strategy()
    assert overrides == {"min_theo_confidence": 0.3, "theo_tolerance_c": 5.0}


# ── snapshot ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_includes_all_state() -> None:
    s = ControlState()
    await s.pause_ticker("KX-T50")
    await s.pause_side("KX-T75", "ask")
    await s.set_knob("min_theo_confidence", 0.4)
    snap = s.snapshot()
    assert snap["version"] >= 3
    assert snap["kill_state"] == "off"
    assert "KX-T50" in snap["paused_tickers"]
    assert ["KX-T75", "ask"] in snap["paused_sides"]
    assert snap["knob_overrides"] == {"min_theo_confidence": 0.4}
