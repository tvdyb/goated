"""Tests for the three default risk gates."""

from __future__ import annotations

import time

import pytest

from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    SideDecision,
)
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    MaxOrdersPerCycleGate,
    RiskContext,
)
from lipmm.theo import TheoResult


def _ctx(
    *,
    bid_price: int = 44, bid_size: int = 10, bid_skip: bool = False,
    ask_price: int = 56, ask_size: int = 10, ask_skip: bool = False,
    theo_yes_prob: float = 0.50,
    cycle_id: int = 1, time_to_settle_s: float = 3600.0,
) -> RiskContext:
    decision = QuotingDecision(
        bid=SideDecision(price=bid_price, size=bid_size, skip=bid_skip,
                         reason="strategy-bid"),
        ask=SideDecision(price=ask_price, size=ask_size, skip=ask_skip,
                         reason="strategy-ask"),
    )
    return RiskContext(
        ticker="KX-T50.00",
        cycle_id=cycle_id,
        decision=decision,
        theo=TheoResult(
            yes_probability=theo_yes_prob, confidence=1.0,
            computed_at=time.time(), source="test",
        ),
        our_state=OurState(
            cur_bid_px=0, cur_bid_size=0, cur_bid_id=None,
            cur_ask_px=0, cur_ask_size=0, cur_ask_id=None,
        ),
        time_to_settle_s=time_to_settle_s,
        now_ts=time.time(),
        all_resting_count=0,
        all_resting_notional=0.0,
    )


# ── MaxNotionalPerSideGate ────────────────────────────────────────────


def test_notional_gate_constructor_validates_positive_max() -> None:
    with pytest.raises(ValueError):
        MaxNotionalPerSideGate(max_dollars=0)
    with pytest.raises(ValueError):
        MaxNotionalPerSideGate(max_dollars=-1)


@pytest.mark.asyncio
async def test_notional_gate_under_cap_allows_both_sides() -> None:
    gate = MaxNotionalPerSideGate(max_dollars=10.0)
    # bid: 44c × 10 = $4.40. ask: (100-56)c × 10 = $4.40. Both under cap.
    ctx = _ctx(bid_price=44, bid_size=10, ask_price=56, ask_size=10)
    v = await gate.check(ctx)
    assert v.bid_allow is True
    assert v.ask_allow is True


@pytest.mark.asyncio
async def test_notional_gate_vetoes_oversized_bid() -> None:
    gate = MaxNotionalPerSideGate(max_dollars=2.0)
    # bid: 50c × 10 = $5 > $2 cap → veto bid only
    ctx = _ctx(bid_price=50, bid_size=10, ask_price=85, ask_size=10)
    # ask: (100-85)c × 10 = $1.50 → allow
    v = await gate.check(ctx)
    assert v.bid_allow is False
    assert v.ask_allow is True
    assert "$5.00" in v.bid_reason
    assert "$2.00" in v.bid_reason


@pytest.mark.asyncio
async def test_notional_gate_vetoes_oversized_ask() -> None:
    gate = MaxNotionalPerSideGate(max_dollars=2.0)
    # ask at 50c × 10 = $5 max-loss → veto. bid 15c × 10 = $1.50 → allow.
    ctx = _ctx(bid_price=15, bid_size=10, ask_price=50, ask_size=10)
    v = await gate.check(ctx)
    assert v.bid_allow is True
    assert v.ask_allow is False
    assert "$5.00" in v.ask_reason


@pytest.mark.asyncio
async def test_notional_gate_skips_already_skipped_side() -> None:
    """A side that's already skip=True isn't checked (no-op for that side)."""
    gate = MaxNotionalPerSideGate(max_dollars=0.50)  # tight cap
    ctx = _ctx(bid_skip=True, ask_price=50, ask_size=10)
    v = await gate.check(ctx)
    # Bid is already skipped — gate doesn't add a veto on the bid side
    assert v.bid_allow is True  # gate's own verdict
    # Ask side still evaluated, vetoed
    assert v.ask_allow is False


# ── EndgameGuardrailGate ──────────────────────────────────────────────


def test_endgame_gate_constructor_validates_thresholds() -> None:
    with pytest.raises(ValueError):
        EndgameGuardrailGate(min_seconds_to_settle=3600,
                             deep_otm_threshold=20, deep_itm_threshold=10)
    with pytest.raises(ValueError):
        EndgameGuardrailGate(min_seconds_to_settle=3600,
                             deep_otm_threshold=-1, deep_itm_threshold=90)


@pytest.mark.asyncio
async def test_endgame_outside_window_allows_everything() -> None:
    gate = EndgameGuardrailGate(
        min_seconds_to_settle=3600, deep_otm_threshold=10, deep_itm_threshold=90,
    )
    # 2 hours to settle, deep OTM theo — outside window so allow
    ctx = _ctx(theo_yes_prob=0.05, time_to_settle_s=7200)
    v = await gate.check(ctx)
    assert v.bid_allow is True
    assert v.ask_allow is True


@pytest.mark.asyncio
async def test_endgame_deep_otm_inside_window_vetoes_bid() -> None:
    """Lottery-ticket buying near settle → bid vetoed."""
    gate = EndgameGuardrailGate(
        min_seconds_to_settle=3600, deep_otm_threshold=10, deep_itm_threshold=90,
    )
    ctx = _ctx(theo_yes_prob=0.05, time_to_settle_s=1800)  # 30 min, deep OTM
    v = await gate.check(ctx)
    assert v.bid_allow is False
    assert v.ask_allow is True
    assert "deep OTM" in v.bid_reason


@pytest.mark.asyncio
async def test_endgame_deep_itm_inside_window_vetoes_ask() -> None:
    """Selling near-certain Yes near settle → ask vetoed."""
    gate = EndgameGuardrailGate(
        min_seconds_to_settle=3600, deep_otm_threshold=10, deep_itm_threshold=90,
    )
    ctx = _ctx(theo_yes_prob=0.96, time_to_settle_s=1800)  # 30 min, deep ITM
    v = await gate.check(ctx)
    assert v.bid_allow is True
    assert v.ask_allow is False
    assert "deep ITM" in v.ask_reason


@pytest.mark.asyncio
async def test_endgame_mid_range_inside_window_allows_both() -> None:
    """Mid-theo strikes don't have asymmetric pickoff risk → allowed even
    inside the endgame window."""
    gate = EndgameGuardrailGate(
        min_seconds_to_settle=3600, deep_otm_threshold=10, deep_itm_threshold=90,
    )
    ctx = _ctx(theo_yes_prob=0.50, time_to_settle_s=1800)
    v = await gate.check(ctx)
    assert v.bid_allow is True
    assert v.ask_allow is True


# ── MaxOrdersPerCycleGate ─────────────────────────────────────────────


def test_cycle_throttle_constructor_validates() -> None:
    with pytest.raises(ValueError):
        MaxOrdersPerCycleGate(max_orders=-1)
    # Zero is allowed (silences the bot entirely)
    MaxOrdersPerCycleGate(max_orders=0)


@pytest.mark.asyncio
async def test_cycle_throttle_under_quota_allows() -> None:
    gate = MaxOrdersPerCycleGate(max_orders=10)
    ctx = _ctx(cycle_id=1)
    v = await gate.check(ctx)
    # 2 sides proposed, both allowed
    assert v.bid_allow is True
    assert v.ask_allow is True


@pytest.mark.asyncio
async def test_cycle_throttle_exhausts_quota_within_cycle() -> None:
    gate = MaxOrdersPerCycleGate(max_orders=3)
    # Cycle 1: ticker 1 (bid+ask) → count 0→2. ticker 2 (bid+ask) → bid pushes
    # 2→3 (allowed), ask would push 3→4 (vetoed).
    v1 = await gate.check(_ctx(cycle_id=1))
    assert v1.bid_allow and v1.ask_allow
    v2 = await gate.check(_ctx(cycle_id=1))
    assert v2.bid_allow is True   # 2→3 fits
    assert v2.ask_allow is False  # 3→4 over quota


@pytest.mark.asyncio
async def test_cycle_throttle_resets_on_cycle_advance() -> None:
    gate = MaxOrdersPerCycleGate(max_orders=2)
    # Cycle 1: 2 sides used the budget
    await gate.check(_ctx(cycle_id=1))
    v = await gate.check(_ctx(cycle_id=1))
    assert v.bid_allow is False  # quota exhausted
    # Cycle 2: counter reset, fresh budget
    v2 = await gate.check(_ctx(cycle_id=2))
    assert v2.bid_allow is True
    assert v2.ask_allow is True


@pytest.mark.asyncio
async def test_cycle_throttle_skipped_sides_dont_count() -> None:
    """A side that's already skip=True doesn't burn budget."""
    gate = MaxOrdersPerCycleGate(max_orders=1)
    # ticker 1: bid_skip=True, ask=active. Only ask counts → 0→1.
    v1 = await gate.check(_ctx(bid_skip=True, cycle_id=5))
    assert v1.bid_allow is True   # not consuming
    assert v1.ask_allow is True   # 0→1 fits
    # ticker 2: bid+ask. bid 1→2 over quota, vetoed.
    v2 = await gate.check(_ctx(cycle_id=5))
    assert v2.bid_allow is False
    assert v2.ask_allow is False  # also over
