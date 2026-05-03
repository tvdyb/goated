"""Tests for engine.sticky_quote — the LIP drag-defense state machine."""

from __future__ import annotations

import time

import pytest

from lipmm.quoting.strategies._sticky_machine import StickyConfig, StickyQuoter


def _cfg(**overrides):
    """Build a StickyConfig with sensible test defaults (faster timing)."""
    base = dict(
        desert_jump_cents=5,
        min_distance_from_theo=15,
        snapshots_at_1x_required=5,  # smaller for faster tests
        theo_stability_cents=2.0,
        theo_range_cents=3.0,
        relax_total_steps=10,
        max_aggressive_duration_seconds=60.0,
        cooldown_seconds=120.0,
    )
    base.update(overrides)
    return StickyConfig(**base)


def test_snapshot_contract_fresh_quoter():
    """Public snapshot() contract: every documented field present with correct type.

    This test is the contract. If SideState gains/loses/renames a field, this
    test forces a deliberate decision about whether the change is part of the
    public snapshot() contract.
    """
    sq = StickyQuoter(_cfg())
    snap = sq.snapshot("KXTEST", "ask")
    # Required fields and their default types (None acceptable where noted)
    required = {
        "state": (str,),
        "consecutive_1x_count": (int,),
        "current_price": (int,),
        "relax_step": (int,),
        "aggressive_entered_at": (float, type(None)),
        "theo_buffer": (list,),
        "cooldown_until": (float, type(None)),
    }
    for field, allowed_types in required.items():
        assert field in snap, f"missing field: {field}"
        assert isinstance(snap[field], allowed_types), (
            f"field {field}: expected one of {allowed_types}, got {type(snap[field])}"
        )
    # State default
    assert snap["state"] == "NORMAL"
    # theo_buffer must be a list (not deque) so it serializes cleanly
    assert type(snap["theo_buffer"]) is list


def test_snapshot_reflects_state_after_aggressive():
    """Snapshot updates as state progresses through compute()."""
    sq = StickyQuoter(_cfg())
    # First call sets up
    sq.compute(
        ticker="T1", side="ask", natural_target=74,
        best_relevant=75, our_current=0, fair=7.0, now=1000.0,
    )
    # Pennying drives AGGRESSIVE
    sq.compute(
        ticker="T1", side="ask", natural_target=71,
        best_relevant=72, our_current=74, fair=7.0, now=1003.0,
    )
    snap = sq.snapshot("T1", "ask")
    assert snap["state"] == "AGGRESSIVE"
    assert snap["aggressive_entered_at"] is not None
    assert isinstance(snap["aggressive_entered_at"], float)
    # current_price reflects post-compute state
    assert snap["current_price"] > 0
    # theo_buffer is a list copy (mutating it must not affect internal state)
    snap["theo_buffer"].append(999.0)
    assert 999.0 not in sq.snapshot("T1", "ask")["theo_buffer"]


def test_initial_state_normal_passes_through():
    sq = StickyQuoter(_cfg())
    price, state, _ = sq.compute(
        ticker="T1186", side="ask", natural_target=74,
        best_relevant=75, our_current=0, fair=7.0, now=1000.0,
    )
    assert price == 74
    assert state == "NORMAL"


def test_pennying_triggers_aggressive_with_jump():
    """Attacker drops best from 75c to 72c. Bot should jump to 67c (best - jump)."""
    sq = StickyQuoter(_cfg(desert_jump_cents=5, min_distance_from_theo=15))
    # Initial: at 74c, natural was 74 (best=75 - 1 from desert)
    sq.compute(ticker="T1186", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    # Attacker drops best to 72. natural target moved from 74 to 71.
    # We were at 74, natural=71 → more aggressive direction → AGGRESSIVE
    price, state, _ = sq.compute(
        ticker="T1186", side="ask", natural_target=71,
        best_relevant=72, our_current=74, fair=7.0, now=1003.0,
    )
    # Aggressive: best - desert_jump = 72 - 5 = 67 (clamped by theo+15=22 floor)
    assert state == "AGGRESSIVE"
    assert price == 67


def test_aggressive_clamped_by_theo_floor():
    """Attacker drives best deep into theo. Bot stops at min_distance_from_theo."""
    sq = StickyQuoter(_cfg(desert_jump_cents=5, min_distance_from_theo=15))
    sq.compute(ticker="T1186", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    # Attacker drives best to 18c (theo+11 area). jump_target=13, floor=22 → 22 wins.
    price, state, _ = sq.compute(
        ticker="T1186", side="ask", natural_target=17,
        best_relevant=18, our_current=74, fair=7.0, now=1003.0,
    )
    assert state == "AGGRESSIVE"
    assert price == 22  # theo (7) + min_distance (15)


def test_aggressive_to_relaxing_after_consecutive_1x():
    """After N cycles at 1.0x with stable theo, bot enters RELAXING."""
    sq = StickyQuoter(_cfg(snapshots_at_1x_required=3))
    # Trigger AGGRESSIVE: posts at 67c
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    sq.compute(ticker="T1", side="ask", natural_target=71,
               best_relevant=72, our_current=74, fair=7.0, now=1003.0)
    # Now in AGGRESSIVE at 67. Attacker pulled, best back to 75. natural=74.
    # 3 consecutive cycles where our_current=67 == best=67 (we're best alone)
    for i in range(3):
        price, state, _ = sq.compute(
            ticker="T1", side="ask", natural_target=74,
            best_relevant=67,  # we're alone at 67, so we ARE best
            our_current=67, fair=7.0, now=1006.0 + i * 3,
        )
    # 3rd at-1x cycle should trigger RELAXING
    assert state == "RELAXING"
    # First relax step should move us up but not by much (gap=7, 10 steps)
    assert price > 67
    assert price < 74


def test_relaxing_walks_to_natural_over_steps():
    """Once in RELAXING, walk back gradually to natural target."""
    cfg = _cfg(snapshots_at_1x_required=2, relax_total_steps=5)
    sq = StickyQuoter(cfg)
    # Set up: AGGRESSIVE at 60c, natural=74, gap=14
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # Build up at-1x to trigger RELAXING
    for i in range(2):
        sq.compute(ticker="T1", side="ask", natural_target=74,
                   best_relevant=55, our_current=55, fair=7.0, now=1006.0 + i * 3)
    # Now in RELAXING with start_price=55, target=74, gap=19, 5 steps
    prices = []
    for i in range(6):
        p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=74,
                          best_relevant=55, our_current=p if i > 0 else 55,
                          fair=7.0, now=1010.0 + i * 3)
        prices.append((p, s))
    # Last entry should be NORMAL at 74
    assert prices[-1][1] == "NORMAL"
    assert prices[-1][0] == 74
    # Should be monotonically increasing
    p_seq = [p for p, _ in prices]
    assert all(p_seq[i] <= p_seq[i + 1] for i in range(len(p_seq) - 1))


def test_relaxing_to_aggressive_on_repenny():
    """If pennied while RELAXING, snap back to AGGRESSIVE."""
    cfg = _cfg(snapshots_at_1x_required=2, relax_total_steps=10)
    sq = StickyQuoter(cfg)
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # Build up at-1x
    for i in range(2):
        sq.compute(ticker="T1", side="ask", natural_target=74,
                   best_relevant=55, our_current=55, fair=7.0, now=1006.0 + i * 3)
    # We're in RELAXING. Now attacker re-pennies.
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=49,
                      best_relevant=50, our_current=56, fair=7.0, now=1015.0)
    assert s == "AGGRESSIVE"
    assert p < 50  # should be aggressive_price = best - jump or theo floor


def test_theo_drift_blocks_relax():
    """If theo drifts more than stability cents during AGGRESSIVE, no relax."""
    cfg = _cfg(snapshots_at_1x_required=3, theo_stability_cents=2.0)
    sq = StickyQuoter(cfg)
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # 3 at-1x cycles BUT theo drifts +5c (above 2c stability gate)
    for i in range(3):
        p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=74,
                          best_relevant=55, our_current=55,
                          fair=7.0 + (i + 1) * 2.0,  # drift up
                          now=1006.0 + i * 3)
    # Should still be AGGRESSIVE — theo drifted too much
    assert s == "AGGRESSIVE"


def test_circuit_breaker_to_cooldown():
    """If AGGRESSIVE persists past max_aggressive_duration, enter COOLDOWN."""
    cfg = _cfg(max_aggressive_duration_seconds=10.0, snapshots_at_1x_required=100)
    sq = StickyQuoter(cfg)
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    # Enter AGGRESSIVE at t=1003
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # Stay aggressive until past the deadline (t=1003 + 10 = 1013)
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=74,
                      best_relevant=55, our_current=55, fair=7.0, now=1015.0)
    assert s == "COOLDOWN"
    assert p == 0  # signal to not post


def test_cooldown_recovers_after_duration():
    cfg = _cfg(max_aggressive_duration_seconds=5.0, cooldown_seconds=10.0,
               snapshots_at_1x_required=100)
    sq = StickyQuoter(cfg)
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # Trigger cooldown
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=55, our_current=55, fair=7.0, now=1010.0)
    assert sq.state_of("T1", "ask") == "COOLDOWN"
    # Still in cooldown 5s later
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=74,
                      best_relevant=75, our_current=0, fair=7.0, now=1015.0)
    assert s == "COOLDOWN"
    # After cooldown ends (10s after entry at t=1010 → t=1020)
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=74,
                      best_relevant=75, our_current=0, fair=7.0, now=1021.0)
    assert s == "NORMAL"
    assert p == 74


def test_per_side_independent():
    """Bid and ask states are tracked separately."""
    sq = StickyQuoter(_cfg())
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    # Trigger AGGRESSIVE on ask
    sq.compute(ticker="T1", side="ask", natural_target=59,
               best_relevant=60, our_current=74, fair=7.0, now=1003.0)
    # Bid side should still be NORMAL — never touched
    assert sq.state_of("T1", "ask") == "AGGRESSIVE"
    assert sq.state_of("T1", "bid") == "NORMAL"


def test_bid_side_inverts_correctly():
    """Bid: pennied = best rises. Aggressive = bid up to best+jump bounded by theo-min_dist."""
    sq = StickyQuoter(_cfg(desert_jump_cents=5, min_distance_from_theo=15))
    # Initial bid at 5c, natural=5 (best=4 + 1)
    sq.compute(ticker="T1", side="bid", natural_target=5,
               best_relevant=4, our_current=0, fair=20.0, now=1000.0)
    # Attacker bids 8 (drives best up to 8). natural target now 9.
    p, s, _ = sq.compute(ticker="T1", side="bid", natural_target=9,
                      best_relevant=8, our_current=5, fair=20.0, now=1003.0)
    # Aggressive: best + jump = 8 + 5 = 13. Theo ceiling: 20 - 15 = 5.
    # min(13, 5) = 5. Capped by theo proximity.
    assert s == "AGGRESSIVE"
    assert p == 5


def test_pennying_detection_uses_natural_vs_current():
    """We're 'pennied' when natural_target moves more aggressive than our quote."""
    sq = StickyQuoter(_cfg())
    # Posted at 74c
    sq.compute(ticker="T1", side="ask", natural_target=74,
               best_relevant=75, our_current=0, fair=7.0, now=1000.0)
    # Best drops to 70 — natural target now 69 — more aggressive than 74 → pennied
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=69,
                      best_relevant=70, our_current=74, fair=7.0, now=1003.0)
    assert s == "AGGRESSIVE"
    # Best rises back to 80 — natural now 79 — LESS aggressive than current → not pennied
    p, s, _ = sq.compute(ticker="T1", side="ask", natural_target=79,
                      best_relevant=80, our_current=p, fair=7.0, now=1006.0)
    # Not pennied this cycle, stays in AGGRESSIVE accumulating
    assert s == "AGGRESSIVE"
