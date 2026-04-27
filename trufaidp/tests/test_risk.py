from __future__ import annotations

import time

from trufaidp.mm.risk import RiskConfig, RiskGate, RiskState


def _gate(**overrides) -> RiskGate:
    cfg = RiskConfig(**overrides) if overrides else RiskConfig()
    return RiskGate(cfg=cfg)


def test_ok_when_within_limits():
    gate = _gate()
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 10, "B": -5},
        theos_by_strike={"A": 50, "B": 50},
    )
    assert state is RiskState.OK


def test_pull_all_near_settlement():
    gate = _gate()
    state = gate.check(
        seconds_to_settlement=10.0,  # < 5 minutes
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 50},
    )
    assert state is RiskState.PULL_ALL


def test_passive_when_aggregate_cap_breached():
    gate = _gate()
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 200, "B": 100},  # agg=300
        theos_by_strike={"A": 50, "B": 50},
    )
    assert state is RiskState.PASSIVE_ONLY


def test_passive_when_per_strike_cap_breached():
    gate = _gate()
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 50, "B": 0},
        theos_by_strike={"A": 50, "B": 50},
    )
    assert state is RiskState.PASSIVE_ONLY


def test_pull_on_theo_jump_then_cooldown_sticky():
    gate = _gate(cooldown_seconds=60.0)
    gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 50},
    )
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 60},  # +10c jump
    )
    assert state is RiskState.PULL_ALL

    # Within cooldown, still pulled even if theo stable.
    state2 = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 60},
    )
    assert state2 is RiskState.PULL_ALL


def test_error_burst_pulls():
    gate = _gate(error_kill_threshold=3, cooldown_seconds=60.0)
    for _ in range(3):
        gate.record_error()
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 50},
    )
    assert state is RiskState.PULL_ALL


def test_error_window_expires():
    gate = _gate(error_kill_threshold=3, cooldown_seconds=0.01)
    for _ in range(3):
        gate.record_error()
    # Manually expire by reaching into the deque (test-only).
    gate._error_times.clear()
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 50},
    )
    # Cooldown may still be active from the previous check; sleep past it.
    time.sleep(0.02)
    state = gate.check(
        seconds_to_settlement=3600.0,
        positions_by_strike={"A": 0},
        theos_by_strike={"A": 50},
    )
    assert state is RiskState.OK
