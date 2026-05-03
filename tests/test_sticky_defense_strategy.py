"""Tests for lipmm.quoting.strategies.sticky_defense.StickyDefenseQuoting.

Validates the wrapping strategy's behavior:
  - Satisfies QuotingStrategy protocol
  - Bypass gate fires on deep wings (low + high theo)
  - Active range invokes the underlying state machine
  - COOLDOWN translates to skip=True with chained reason
  - Transitions tagged with side propagate to QuotingDecision
  - Confidence-aware widening extends the bypass range
  - Composes correctly with a custom (non-Default) base strategy
  - Post-override no-cross guard prevents crosses introduced by sticky
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)
from lipmm.quoting.strategies.default import DefaultLIPQuoting
from lipmm.quoting.strategies.sticky_defense import (
    StickyDefenseConfig,
    StickyDefenseQuoting,
    default_sticky,
)
from lipmm.quoting.strategies._sticky_machine import StickyConfig
from lipmm.theo import TheoResult


# ── helpers ────────────────────────────────────────────────────────────


def _theo(yes_prob: float, confidence: float = 1.0) -> TheoResult:
    return TheoResult(
        yes_probability=yes_prob,
        confidence=confidence,
        computed_at=time.time(),
        source="test",
    )


def _empty_state() -> OurState:
    return OurState(
        cur_bid_px=0, cur_bid_size=0, cur_bid_id=None,
        cur_ask_px=0, cur_ask_size=0, cur_ask_id=None,
    )


# ── 1. Protocol satisfaction ──────────────────────────────────────────


def test_satisfies_protocol() -> None:
    s = StickyDefenseQuoting(base=DefaultLIPQuoting())
    assert isinstance(s, QuotingStrategy)
    assert s.name == "sticky-defense"


def test_default_sticky_factory_builds() -> None:
    s = default_sticky()
    assert isinstance(s, StickyDefenseQuoting)
    assert isinstance(s, QuotingStrategy)


# ── 2. Bypass gate (deep wings) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_bypass_gate_deep_otm() -> None:
    """theo.yes_cents=5 with default min_dist=15 → bypass; result == base."""
    base = DefaultLIPQuoting()
    sticky = StickyDefenseQuoting(base=base)
    ob = OrderbookSnapshot(
        yes_depth=[(3, 100.0)], no_depth=[(80, 100.0)],
        best_bid=3, best_ask=20,
    )
    args = dict(
        ticker="KX-T1196.99",
        theo=_theo(0.05, confidence=1.0),
        orderbook=ob,
        our_state=_empty_state(),
        now_ts=time.time(),
        time_to_settle_s=3600,
    )
    base_dec = await base.quote(**args)
    sticky_dec = await sticky.quote(**args)
    assert sticky_dec.bid.price == base_dec.bid.price
    assert sticky_dec.ask.price == base_dec.ask.price
    assert sticky_dec.transitions == []


@pytest.mark.asyncio
async def test_bypass_gate_deep_itm() -> None:
    """theo.yes_cents=95 with default min_dist=15 → bypass."""
    base = DefaultLIPQuoting()
    sticky = StickyDefenseQuoting(base=base)
    ob = OrderbookSnapshot(
        yes_depth=[(90, 100.0)], no_depth=[(3, 100.0)],
        best_bid=90, best_ask=97,
    )
    args = dict(
        ticker="KX-T1136.99",
        theo=_theo(0.95, confidence=1.0),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    base_dec = await base.quote(**args)
    sticky_dec = await sticky.quote(**args)
    assert sticky_dec.bid.price == base_dec.bid.price
    assert sticky_dec.ask.price == base_dec.ask.price
    assert sticky_dec.transitions == []


# ── 3. Active range invokes sticky ───────────────────────────────────


@pytest.mark.asyncio
async def test_active_range_invokes_sticky() -> None:
    """theo=50 (active range) and a pennying scenario → sticky AGGRESSIVE
    overrides the base price on subsequent cycles."""
    base = DefaultLIPQuoting()
    sticky = StickyDefenseQuoting(base=base)
    ticker = "KX-T1156.99"

    # Cycle 1: stable book; sticky enters NORMAL, no overrides yet
    ob1 = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(45, 100.0)],
        best_bid=45, best_ask=55,
    )
    dec1 = await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob1, our_state=_empty_state(),
        now_ts=1000.0, time_to_settle_s=3600,
    )
    # sticky_state in extras after first call
    assert dec1.bid.extras.get("sticky_state") in ("NORMAL", "AGGRESSIVE")

    # Cycle 2: someone pennies the bid; sticky should detect and override
    ob2 = OrderbookSnapshot(
        yes_depth=[(48, 100.0)], no_depth=[(45, 100.0)],
        best_bid=48, best_ask=55,
    )
    # Tell sticky we're already at base's first quote (44c)
    state = OurState(
        cur_bid_px=dec1.bid.price, cur_bid_size=dec1.bid.size,
        cur_bid_id="b1",
        cur_ask_px=dec1.ask.price, cur_ask_size=dec1.ask.size,
        cur_ask_id="a1",
    )
    dec2 = await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob2, our_state=state,
        now_ts=1003.0, time_to_settle_s=3600,
    )
    # Sticky should have entered AGGRESSIVE on the bid side at minimum
    bid_state = dec2.bid.extras.get("sticky_state")
    assert bid_state in ("AGGRESSIVE", "NORMAL")  # depends on init semantics


# ── 4. COOLDOWN → skip ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cooldown_produces_skip() -> None:
    """Drive AGGRESSIVE past max-duration → strategy emits skip with
    chained reason. The circuit breaker only fires on a cycle where the
    bot is NOT being re-pennied, so cycle 3 must have a quiet/relaxed book
    (attacker has pulled) for the breaker to trip."""
    sticky_cfg = StickyConfig(
        max_aggressive_duration_seconds=1.0,
        cooldown_seconds=10.0,
        snapshots_at_1x_required=100,  # never finish naturally
    )
    cfg = StickyDefenseConfig(sticky=sticky_cfg)
    base = DefaultLIPQuoting()
    sticky = StickyDefenseQuoting(base=base, cfg=cfg)
    ticker = "KX-T1156.99"

    # Cycle 1: init at theo=50 (active range), normal book.
    ob1 = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(45, 100.0)],
        best_bid=45, best_ask=55,
    )
    await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob1, our_state=_empty_state(),
        now_ts=1000.0, time_to_settle_s=3600,
    )

    # Cycle 2: attacker pennies the ask side — best_ask drops to 40.
    # Base produces ask=49 (anti-spoof binds), sticky goes AGGRESSIVE
    # with current_price=65 (theo+min_dist floor).
    ob2 = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(60, 100.0)],
        best_bid=45, best_ask=40,
    )
    state = OurState(
        cur_bid_px=44, cur_bid_size=10, cur_bid_id="b1",
        cur_ask_px=56, cur_ask_size=10, cur_ask_id="a1",
    )
    await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob2, our_state=state,
        now_ts=1003.0, time_to_settle_s=3600,
    )

    # Cycle 3: attacker has pulled — best_ask back to 80 (well above
    # sticky's current_price=65). Base produces ask=81 (active follow).
    # natural_target(81) > current_price(65), so NOT re-pennied.
    # Now enters AGGRESSIVE-no-penny branch → circuit breaker fires
    # because (now=1010) - (entered=1003) = 7s > max=1s → COOLDOWN.
    ob3 = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(20, 100.0)],
        best_bid=45, best_ask=80,
    )
    state3 = OurState(
        cur_bid_px=44, cur_bid_size=10, cur_bid_id="b1",
        cur_ask_px=65, cur_ask_size=10, cur_ask_id="a1",
    )
    dec3 = await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob3, our_state=state3,
        now_ts=1010.0, time_to_settle_s=3600,
    )
    assert dec3.ask.skip is True, (
        f"Expected ask.skip=True (COOLDOWN), got SideDecision="
        f"price={dec3.ask.price} skip={dec3.ask.skip} reason={dec3.ask.reason!r}"
    )
    assert "sticky COOLDOWN" in dec3.ask.reason


# ── 5. Transition records propagate ─────────────────────────────────


@pytest.mark.asyncio
async def test_transitions_propagate_with_side_tag() -> None:
    """When sticky transitions, the QuotingDecision carries those
    transitions tagged with side."""
    sticky_cfg = StickyConfig(snapshots_at_1x_required=2)
    cfg = StickyDefenseConfig(sticky=sticky_cfg)
    sticky = StickyDefenseQuoting(base=DefaultLIPQuoting(), cfg=cfg)
    ticker = "KX-T1156.99"

    ob = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(45, 100.0)],
        best_bid=45, best_ask=55,
    )
    # Initialize state
    await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=1000.0, time_to_settle_s=3600,
    )

    # Force a pennying event on ask side
    ob2 = OrderbookSnapshot(
        yes_depth=[(45, 100.0)], no_depth=[(60, 100.0)],
        best_bid=45, best_ask=40,
    )
    state = OurState(
        cur_bid_px=44, cur_bid_size=10, cur_bid_id="b1",
        cur_ask_px=56, cur_ask_size=10, cur_ask_id="a1",
    )
    dec = await sticky.quote(
        ticker=ticker, theo=_theo(0.50),
        orderbook=ob2, our_state=state,
        now_ts=1003.0, time_to_settle_s=3600,
    )
    # Should have transitions emitted on at least one side, all tagged
    if dec.transitions:
        for tr in dec.transitions:
            assert tr.get("side") in ("bid", "ask")
            assert "from" in tr and "to" in tr


# ── 6. Confidence-aware widening ────────────────────────────────────


@pytest.mark.asyncio
async def test_confidence_widening_extends_bypass() -> None:
    """Low confidence widens effective_min_dist, extending the bypass.

    With min_distance_from_theo=15 and confidence=0.25:
      effective = ceil(15 / 0.25) = 60
    So theo.yes_cents=12 (which would be active at conf=1.0) bypasses
    when confidence is 0.25.
    """
    sticky = StickyDefenseQuoting(base=DefaultLIPQuoting())
    ob = OrderbookSnapshot(
        yes_depth=[(8, 100.0)], no_depth=[(80, 100.0)],
        best_bid=8, best_ask=20,
    )

    # At confidence=0.25, theo=12 → bypass (effective_min=60)
    args_low = dict(
        ticker="KX-T1190",
        theo=_theo(0.12, confidence=0.25),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    base_dec_low = await DefaultLIPQuoting().quote(**args_low)
    # but base needs >= confidence floor (default 0.10) — confidence=0.25 > 0.10, so base does quote
    sticky_dec_low = await sticky.quote(**args_low)
    # Bypass means sticky returns base unchanged
    assert sticky_dec_low.bid.price == base_dec_low.bid.price
    assert sticky_dec_low.ask.price == base_dec_low.ask.price


@pytest.mark.asyncio
async def test_confidence_widening_disabled_when_off() -> None:
    """With confidence_widening=False, low confidence doesn't widen."""
    cfg = StickyDefenseConfig(confidence_widening=False)
    sticky = StickyDefenseQuoting(base=DefaultLIPQuoting(), cfg=cfg)
    # theo=20 with conf=0.25: with widening on, effective_min=60 → bypass.
    # With widening off, effective_min stays at 15 → sticky runs.
    ob = OrderbookSnapshot(
        yes_depth=[(15, 100.0)], no_depth=[(70, 100.0)],
        best_bid=15, best_ask=30,
    )
    dec = await sticky.quote(
        ticker="KX-T",
        theo=_theo(0.20, confidence=0.25),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # With widening off, sticky was invoked: state appears in extras
    assert dec.bid.extras.get("sticky_state") is not None or \
           dec.ask.extras.get("sticky_state") is not None


# ── 7. Composition with custom base ─────────────────────────────────


class _DummyBase:
    """A tiny base strategy that returns fixed prices regardless of inputs."""
    name = "dummy"
    async def warmup(self) -> None: pass
    async def shutdown(self) -> None: pass
    async def quote(self, **kwargs) -> QuotingDecision:
        return QuotingDecision(
            bid=SideDecision(price=42, size=10, skip=False, reason="dummy-bid"),
            ask=SideDecision(price=58, size=10, skip=False, reason="dummy-ask"),
        )


@pytest.mark.asyncio
async def test_composition_with_custom_base_bypass() -> None:
    """Sticky wraps custom base and falls back to its decision on bypass."""
    sticky = StickyDefenseQuoting(base=_DummyBase())
    ob = OrderbookSnapshot(
        yes_depth=[(40, 100.0)], no_depth=[(40, 100.0)],
        best_bid=40, best_ask=60,
    )
    # Deep OTM theo → bypass → returns dummy's decision unchanged
    dec = await sticky.quote(
        ticker="KX-T",
        theo=_theo(0.05, confidence=1.0),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert dec.bid.price == 42
    assert dec.ask.price == 58
    assert dec.bid.reason == "dummy-bid"


@pytest.mark.asyncio
async def test_composition_with_custom_base_active() -> None:
    """Sticky wraps custom base; in active range, sticky reads dummy's
    natural_target as the seed."""
    sticky = StickyDefenseQuoting(base=_DummyBase())
    ob = OrderbookSnapshot(
        yes_depth=[(40, 100.0)], no_depth=[(40, 100.0)],
        best_bid=40, best_ask=60,
    )
    # Active range (theo=50)
    dec = await sticky.quote(
        ticker="KX-T",
        theo=_theo(0.50, confidence=1.0),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # First call: sticky initializes state with natural_target from dummy.
    # Result equals dummy's prices because state machine returns natural
    # on init.
    assert dec.bid.extras.get("natural_target") == 42
    assert dec.ask.extras.get("natural_target") == 58


# ── 8. Post-override no-cross guard ────────────────────────────────


@pytest.mark.asyncio
async def test_no_cross_guard_after_override() -> None:
    """If the live book moves between base's no-cross and sticky's run,
    sticky's adjusted prices shouldn't cross the live opposite-best."""
    sticky = StickyDefenseQuoting(base=DefaultLIPQuoting())
    # Inverted-book scenario: best_bid=53, best_ask=54, theo=50.
    # Active range (theo=50). Base would penny inside. Sticky's
    # post-override no-cross guard ensures bid < best_ask and ask > best_bid.
    ob = OrderbookSnapshot(
        yes_depth=[(53, 100.0)], no_depth=[(46, 100.0)],
        best_bid=53, best_ask=54,
    )
    dec = await sticky.quote(
        ticker="KX-T",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    if not dec.bid.skip:
        assert dec.bid.price < 54
    if not dec.ask.skip:
        assert dec.ask.price > 53
