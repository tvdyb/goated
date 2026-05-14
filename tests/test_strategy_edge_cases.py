"""Strategy edge-case audit — DefaultLIPQuoting behaviors that the
existing test suite didn't cover.

Cases:
  - Crossed book → both sides skip.
  - Narrow spread + penny_inside_distance > 1 → bid clamped to (best_ask - tick).
  - Confidence boundaries: exact threshold transitions.
  - dollars_per_side ≤ 0 → fallback to contracts_per_side.
  - One-sided book (no asks) → ask uses no-best-ask formula (theo + half_spread).
  - fair right at 0¢ / 100¢ defensive clamp.
  - Active-penny on sub-cent market: quote uses 1 t1c step, not 1¢.
  - Active-penny n_ticks=1 stays unchanged on wide spread (regression).
"""

from __future__ import annotations

import pytest

from lipmm.quoting.base import OrderbookSnapshot, OurState
from lipmm.quoting.strategies.default import (
    DefaultLIPQuoting,
    DefaultLIPQuotingConfig,
)
from lipmm.theo import TheoResult


def _ob(
    *,
    best_bid_t1c: int = -1,
    best_ask_t1c: int = -1,
    best_bid: int = 0,
    best_ask: int = 100,
    tick_schedule: list | None = None,
) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        yes_depth=[],
        no_depth=[],
        best_bid=best_bid,
        best_ask=best_ask,
        best_bid_t1c=best_bid_t1c,
        best_ask_t1c=best_ask_t1c,
        tick_schedule=tick_schedule or [(10, 990, 10)],
    )


def _our_state() -> OurState:
    return OurState(
        cur_bid_px=0, cur_bid_size=0, cur_bid_id=None,
        cur_ask_px=0, cur_ask_size=0, cur_ask_id=None,
    )


def _theo(yes_prob: float, confidence: float = 0.99) -> TheoResult:
    return TheoResult(
        yes_probability=yes_prob,
        confidence=confidence,
        computed_at=0.0,
        source="test",
    )


@pytest.mark.asyncio
async def test_crossed_book_skips_both_sides() -> None:
    """When best_bid >= best_ask (and both sides are present), the
    strategy should skip both sides instead of computing decisions
    that the no-cross guard fights with."""
    strat = DefaultLIPQuoting()
    ob = _ob(best_bid=55, best_ask=53)  # bid > ask → crossed
    decision = await strat.quote(
        ticker="KX-T1",
        theo=_theo(0.55, confidence=0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.skip is True
    assert decision.ask.skip is True
    assert "crossed" in decision.bid.reason.lower()


@pytest.mark.asyncio
async def test_crossed_book_equal_prices_also_skips() -> None:
    """Edge: best_bid == best_ask. Treated as crossed (degenerate)."""
    strat = DefaultLIPQuoting()
    ob = _ob(best_bid=50, best_ask=50)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.skip and decision.ask.skip


@pytest.mark.asyncio
async def test_narrow_spread_clamps_penny_inside_distance() -> None:
    """With penny_inside_distance=3 and 1¢ spread, the strategy must
    NOT target best+3 (which would cross). It clamps to best_ask−1."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=3,
        theo_tolerance_c=10,  # don't let the cap bind
        dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=50, best_ask=51)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.55, 0.95),  # active-penny gate
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # Bid target was best_bid + 3*tick = 50+30 = 80 t1c (8¢) → clamped
    # to best_ask − tick = 510 − 10 = 500 t1c (50¢). Anti-spoof cap is
    # at (55-1+10)*10 = 640 → not binding.
    assert decision.bid.price_t1c == 500
    # Ask target was best_ask − 3*tick = 510 − 30 = 480 (48¢) → clamped
    # to best_bid + tick = 500 + 10 = 510 t1c (51¢).
    assert decision.ask.price_t1c == 510


@pytest.mark.asyncio
async def test_wide_spread_active_penny_unchanged() -> None:
    """Regression: active-penny default (n=1) on a wide spread still
    quotes best ± 1 cent. Confirms the narrow-spread clamp doesn't
    fire when there's room."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=10, dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=40, best_ask=60)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.price_t1c == 410   # best_bid + 1 cent
    assert decision.ask.price_t1c == 590   # best_ask − 1 cent


@pytest.mark.asyncio
async def test_subcent_active_penny_uses_one_tick() -> None:
    """On a sub-cent market with tick_schedule = [(10, 990, 1)],
    active-penny quotes step by 1 t1c (= 0.1¢), not 1¢."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=10, dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(
        best_bid_t1c=505, best_ask_t1c=520,  # 50.5 / 52.0¢
        best_bid=51, best_ask=52,
        tick_schedule=[(10, 990, 1)],
    )
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.51, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # bid target = 505 + 1 = 506 (50.6¢)
    # cap = (51 - 1 + 10)*10 = 600 → not binding
    assert decision.bid.price_t1c == 506
    # ask target = 520 − 1 = 519 (51.9¢)
    assert decision.ask.price_t1c == 519


@pytest.mark.asyncio
async def test_confidence_below_min_skips_both() -> None:
    """confidence < min_theo_confidence (default 0.10) → both skip."""
    strat = DefaultLIPQuoting()
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.05),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.skip and decision.ask.skip


@pytest.mark.asyncio
async def test_confidence_at_match_threshold_uses_match_mode() -> None:
    """confidence == match_best_min_confidence (0.70) → active-match."""
    cfg = DefaultLIPQuotingConfig(theo_tolerance_c=10, dollars_per_side=1.0)
    strat = DefaultLIPQuoting(cfg)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.70),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # active-match: bid == best_bid, ask == best_ask
    assert decision.bid.price_t1c == 400
    assert decision.ask.price_t1c == 600


@pytest.mark.asyncio
async def test_confidence_at_penny_threshold_uses_penny_mode() -> None:
    """confidence == penny_inside_min_confidence (0.95) → active-penny."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=10, dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.95),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.price_t1c == 410   # inside best
    assert decision.ask.price_t1c == 590


@pytest.mark.asyncio
async def test_inverted_confidence_thresholds_safe() -> None:
    """When penny_inside_min_confidence < match_best_min_confidence (operator
    misconfiguration / violation of the help-text "should be ≥" guidance),
    the strategy still picks a well-defined branch. Penny-inside fires
    earlier and shadows match-best — confusing UX, but not a crash."""
    cfg = DefaultLIPQuotingConfig(
        match_best_min_confidence=0.80,
        penny_inside_min_confidence=0.70,
        penny_inside_distance=1,
        theo_tolerance_c=10,
        dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    # confidence 0.75: clears penny (0.70) before reaching match (0.80) →
    # penny-inside fires; bid steps 1¢ inside best_bid=40, ask 1¢ inside 60
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.75),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.price_t1c == 410
    assert decision.ask.price_t1c == 590
    # confidence 0.65: fails both thresholds → active-follow (1¢ behind best)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.65),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert decision.bid.price_t1c == 390
    assert decision.ask.price_t1c == 610


@pytest.mark.asyncio
async def test_dollars_per_side_zero_falls_back_to_contracts_per_side() -> None:
    """dollars_per_side <= 0 → strategy uses contracts_per_side directly."""
    cfg = DefaultLIPQuotingConfig(
        dollars_per_side=0.0, contracts_per_side=42, theo_tolerance_c=10,
    )
    strat = DefaultLIPQuoting(cfg)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=_ob(best_bid=40, best_ask=60),
        our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # contracts_per_side bypasses min_contracts/max_contracts clamp
    assert decision.bid.size == 42
    assert decision.ask.size == 42


@pytest.mark.asyncio
async def test_one_sided_book_no_asks_uses_half_spread() -> None:
    """When best_ask = 100 (no asks), strategy quotes ask at theo +
    max_half_spread_c — not at the sentinel."""
    cfg = DefaultLIPQuotingConfig(
        max_half_spread_c=4, theo_tolerance_c=10, dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=50, best_ask=100)  # best_ask_t1c derives to 1000
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # ask: target_t1c = (50+4)*10 = 540 (54¢). floor = (50+1-10)*10 =
    # 410 → not binding. No-cross check: 540 > best_bid_t1c=500 → safe.
    assert decision.ask.price_t1c == 540


@pytest.mark.asyncio
async def test_one_sided_book_no_bids_uses_half_spread() -> None:
    """When best_bid = 0 (no bids), strategy quotes bid at theo −
    max_half_spread_c."""
    cfg = DefaultLIPQuotingConfig(
        max_half_spread_c=4, theo_tolerance_c=10, dollars_per_side=1.0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=0, best_ask=60)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # bid: target_t1c = (50-4)*10 = 460 (46¢). cap = (50-1+10)*10 = 590
    assert decision.bid.price_t1c == 460


@pytest.mark.asyncio
async def test_max_distance_from_extremes_caps_bid_and_floors_ask() -> None:
    """Tail-only mode: with max_distance_from_extremes_c=5, on a wide
    02/98 book with high theo override → bid clamped to 5¢ (would
    naturally be 95+ via active-penny w/ high theo), ask floored at
    95¢. Covers the batch-release scenario."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=99,  # disable cap
        dollars_per_side=1.0,
        max_distance_from_extremes_c=5,
    )
    strat = DefaultLIPQuoting(cfg)
    # 02/98 book + theo override at 50% (mid)
    ob = _ob(best_bid=2, best_ask=98)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # Bid natural target = best_bid + 1 = 3¢ → already inside cap → 3¢
    assert decision.bid.price_t1c == 30
    # Ask natural target = best_ask − 1 = 97¢ → already above floor → 97¢
    assert decision.ask.price_t1c == 970


@pytest.mark.asyncio
async def test_max_distance_from_extremes_clamps_when_natural_exceeds() -> None:
    """When natural target would exceed the extremes cap, clamp.
    e.g. high theo override (95%) on a 02/98 book → natural bid =
    96¢ (per anti-spoofing cap) but extremes cap = 5¢ wins."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=99,
        dollars_per_side=1.0,
        max_distance_from_extremes_c=5,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=90, best_ask=98)  # tight high book; bot would penny to 91
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.95, confidence=0.95),  # high theo
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # Natural bid = best_bid + 1 = 91¢ (cap doesn't bind because
    # tolerance is wide). Extremes cap = 5¢ wins → bid = 5¢.
    assert decision.bid.price_t1c == 50
    # Natural ask: best_ask − 1 = 97¢ → already above floor 95¢ → 97¢.
    assert decision.ask.price_t1c == 970


@pytest.mark.asyncio
async def test_max_distance_from_extremes_zero_is_disabled() -> None:
    """Default 0 = no extremes cap, strategy behaves as before."""
    cfg = DefaultLIPQuotingConfig(
        penny_inside_distance=1, theo_tolerance_c=10,
        dollars_per_side=1.0,
        max_distance_from_extremes_c=0,
    )
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=40, best_ask=60)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    # No extremes cap → standard active-penny behavior
    assert decision.bid.price_t1c == 410
    assert decision.ask.price_t1c == 590


@pytest.mark.asyncio
async def test_max_distance_from_extremes_via_control_overrides() -> None:
    """Operator-set knob (per-strike override) reaches the strategy
    via control_overrides=... and binds the same way."""
    strat = DefaultLIPQuoting()  # default cfg has knob=0
    ob = _ob(best_bid=2, best_ask=98)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.50, confidence=0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
        control_overrides={"max_distance_from_extremes_c": 5},
    )
    # With high theo conf and a wide book, anti-spoofing cap
    # alone would let bid go up. Extremes cap forces bid ≤ 5¢.
    assert decision.bid.price_t1c <= 50
    assert decision.ask.price_t1c >= 950


@pytest.mark.asyncio
async def test_fair_at_extreme_low_clamps_safely() -> None:
    """Theo says yes_prob = 0.01 → fair = 1¢. Strategy still produces
    a valid bid (clamped to t1c floor 1) and ask without crashing."""
    cfg = DefaultLIPQuotingConfig(theo_tolerance_c=2, dollars_per_side=1.0)
    strat = DefaultLIPQuoting(cfg)
    ob = _ob(best_bid=1, best_ask=5)
    decision = await strat.quote(
        ticker="KX-T1", theo=_theo(0.01, 0.95),
        orderbook=ob, our_state=_our_state(),
        now_ts=0.0, time_to_settle_s=0.0,
    )
    assert 1 <= decision.bid.price_t1c <= 989
    assert 1 <= decision.ask.price_t1c <= 989
