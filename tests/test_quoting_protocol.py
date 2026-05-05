"""Tests for lipmm.quoting protocol + default strategy."""

from __future__ import annotations

import time

import pytest

from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)
from lipmm.quoting.strategies.default import DefaultLIPQuoting, DefaultLIPQuotingConfig
from lipmm.theo import TheoResult


def _empty_state() -> OurState:
    return OurState(
        cur_bid_px=0, cur_bid_size=0, cur_bid_id=None,
        cur_ask_px=0, cur_ask_size=0, cur_ask_id=None,
    )


def _theo(yes_prob: float, confidence: float = 1.0) -> TheoResult:
    return TheoResult(
        yes_probability=yes_prob,
        confidence=confidence,
        computed_at=time.time(),
        source="test",
    )


# ── Protocol shape ────────────────────────────────────────────────────


def test_default_strategy_satisfies_protocol() -> None:
    s = DefaultLIPQuoting()
    assert isinstance(s, QuotingStrategy)
    assert s.name == "default-lip-quoting"


def test_quoting_decision_immutability() -> None:
    """SideDecision and QuotingDecision are frozen dataclasses."""
    d = SideDecision(price=42, size=10, skip=False, reason="test")
    with pytest.raises(Exception):
        d.price = 50  # type: ignore


# ── Confidence gating ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_confidence_skips_both_sides() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(min_theo_confidence=0.5))
    ob = OrderbookSnapshot(
        yes_depth=[(40, 100)], no_depth=[(50, 100)],
        best_bid=40, best_ask=50,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.45, confidence=0.3),  # below 0.5 gate
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.bid.skip is True
    assert decision.ask.skip is True
    assert "confidence" in decision.bid.reason


# ── Mid-strike active mode ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_active_mode_pennies_behind_best_at_low_confidence() -> None:
    """theo near best, low confidence → not desert → active-follow:
    stay max_distance behind best on each side."""
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(max_distance_from_best=1))
    ob = OrderbookSnapshot(
        yes_depth=[(45, 100)], no_depth=[(45, 100)],
        best_bid=45, best_ask=55,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50, confidence=0.5),  # below penny-inside threshold (0.7)
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # Active-follow: bid = best_bid - 1, ask = best_ask + 1
    assert decision.bid.price == 44
    assert decision.ask.price == 56
    assert decision.bid.extras["mode"] == "active-follow"
    assert decision.ask.extras["mode"] == "active-follow"


@pytest.mark.asyncio
async def test_active_mode_pennies_inside_at_high_confidence() -> None:
    """theo near best, confidence ≥ penny_inside_min_confidence → trust theo
    enough to take the LIP-1.0× spot at best+1 / best-1."""
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(
        max_distance_from_best=1, penny_inside_min_confidence=0.7,
    ))
    ob = OrderbookSnapshot(
        yes_depth=[(45, 100)], no_depth=[(45, 100)],
        best_bid=45, best_ask=55,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50, confidence=0.9),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.bid.price == 46
    assert decision.ask.price == 54
    assert decision.bid.extras["mode"] == "active-penny"
    assert decision.ask.extras["mode"] == "active-penny"


# ── Desert mode (penny inside) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_desert_mode_pennies_inside() -> None:
    """When best is far from theo, penny inside (more aggressive)."""
    s = DefaultLIPQuoting()
    ob = OrderbookSnapshot(
        yes_depth=[(20, 100)], no_depth=[(20, 100)],
        best_bid=20, best_ask=80,
    )
    # theo 50, best_bid 20 → 30c gap = desert
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # Anti-spoofing cap: bid <= theo + 1 = 51. Desert wants 21. 21 < 51 → 21.
    assert decision.bid.price == 21
    # Anti-spoofing floor: ask >= theo - 1 = 49. Desert wants 79. 79 > 49 → 79.
    assert decision.ask.price == 79


# ── Anti-spoofing binding ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anti_spoofing_caps_bid() -> None:
    """If best_bid is above theo+tolerance, bot's bid pinned at the cap."""
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(theo_tolerance_c=2))
    ob = OrderbookSnapshot(
        yes_depth=[(95, 100)], no_depth=[(2, 100)],
        best_bid=95, best_ask=98,
    )
    # theo Yes=10, but best bid is 95 (someone bidding way above theo).
    # |10-95| = 85 > 10 → desert. Desert bid = 95+1 = 96.
    # Anti-spoof cap: 10 - 1 + 2 = 11. min(96, 11) = 11.
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.10),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.bid.price == 11


# ── Empty side handling ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_bid_side_quotes_at_theo_minus_half_spread() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(max_half_spread_c=4))
    ob = OrderbookSnapshot(
        yes_depth=[], no_depth=[(50, 100)],
        best_bid=0, best_ask=50,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # Empty bid: bid = theo - max_half_spread = 50 - 4 = 46
    assert decision.bid.price == 46


@pytest.mark.asyncio
async def test_empty_ask_side_quotes_at_theo_plus_half_spread() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(max_half_spread_c=4))
    ob = OrderbookSnapshot(
        yes_depth=[(50, 100)], no_depth=[],
        best_bid=50, best_ask=100,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.ask.price == 54


# ── No-cross guard ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_cross_guard_pulls_ask_above_best_bid() -> None:
    """T1176.99-style scenario: theo=89, best_bid=97 (above theo),
    best_ask=98. Without no-cross guard, we'd ask at 97c and get 400."""
    s = DefaultLIPQuoting()
    ob = OrderbookSnapshot(
        yes_depth=[(97, 100)], no_depth=[(2, 100)],
        best_bid=97, best_ask=98,
    )
    decision = await s.quote(
        ticker="KX-X-T1176",
        theo=_theo(0.89),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # Whatever the natural target, no-cross guard ensures ask > best_bid (97)
    assert decision.ask.price > 97
    assert "no-cross" in decision.ask.reason or decision.ask.price >= 98


# ── Sizing ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_dollar_sizing_scales_inversely_with_cost() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(
        dollars_per_side=1.0, min_contracts=1, max_contracts=300,
    ))
    # theo=50, mid market — bid quote will land around theo
    ob = OrderbookSnapshot(
        yes_depth=[(45, 100)], no_depth=[(45, 100)],
        best_bid=45, best_ask=55,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # bid at 44c: $1 / 0.44 = 2 contracts
    assert decision.bid.size == 2
    # ask at 56c: cost = 44c, $1 / 0.44 = 2 contracts
    assert decision.ask.size == 2


@pytest.mark.asyncio
async def test_per_dollar_sizing_floors_below_min() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(
        dollars_per_side=0.20, min_contracts=10, max_contracts=300,
    ))
    ob = OrderbookSnapshot(
        yes_depth=[(45, 100)], no_depth=[(45, 100)],
        best_bid=45, best_ask=55,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    # bid at 44c: $0.20 / 0.44 = 0.45 contracts → floor 10
    assert decision.bid.size == 10


@pytest.mark.asyncio
async def test_per_dollar_sizing_caps_at_max() -> None:
    s = DefaultLIPQuoting(DefaultLIPQuotingConfig(
        dollars_per_side=10.0, min_contracts=5, max_contracts=300,
    ))
    # 1c quote: $10 / 0.01 = 1000 contracts → capped at 300
    ob = OrderbookSnapshot(
        yes_depth=[(1, 1000)], no_depth=[(99, 1000)],
        best_bid=1, best_ask=1,  # extreme case
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.01),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.bid.size <= 300
    assert decision.ask.size <= 300


# ── Decision shape ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decision_carries_reasons_and_extras() -> None:
    """Decision-log analysis depends on reasons and extras being populated."""
    s = DefaultLIPQuoting()
    ob = OrderbookSnapshot(
        yes_depth=[(45, 100)], no_depth=[(45, 100)],
        best_bid=45, best_ask=55,
    )
    decision = await s.quote(
        ticker="KX-X-T50.00",
        theo=_theo(0.50),
        orderbook=ob, our_state=_empty_state(),
        now_ts=time.time(), time_to_settle_s=3600,
    )
    assert decision.bid.reason  # non-empty
    assert decision.ask.reason
    assert "mode" in decision.bid.extras
    assert "mode" in decision.ask.extras
    assert decision.transitions == []  # default strategy is stateless
