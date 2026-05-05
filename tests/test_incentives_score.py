"""Tests for the per-strike LIP score module
(`lipmm.incentives.score`) — faithful port of Kalshi's August 2025
LIP self-certification (rules09082530054.pdf, Appendix A).

Authoritative formula:
    Score(bid) = Discount Factor ^ (Reference Price - Price(bid)) * Size
    Normalized = Score / Σ scores on the side
    Snapshot LP Score(user) = Σ normalized yes + Σ normalized no
    Pool share ≈ snapshot_score / sides_with_qualifying

Critical rules verified here:
  - Reference Price = highest yes bid, IF it is < 99¢ (else side empty)
  - Qualifying walk-down: accumulate size from best down until ≥ target;
    bids below the threshold price do NOT qualify
  - Per-side normalization (each side sums to 1 across all users)
  - Pool share is in [0, 1] regardless of how many sides qualify
"""

from __future__ import annotations

import pytest

from lipmm.incentives import (
    RestingMultiplier,
    StrikeScore,
    compute_strike_score,
)


# ── Exponential multiplier (DF^N) ───────────────────────────────────


def test_at_best_full_credit() -> None:
    """An order at the Reference Price (distance 0) earns mult=1.0."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 10}],
        yes_levels=[{"price_cents": 50, "size": 10.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    m = s.multipliers[0]
    assert m.multiplier == pytest.approx(1.0)
    assert m.qualified is True


def test_distance_one_with_df25_is_quarter() -> None:
    """DF=0.25, distance 1 → mult = 0.25 (NOT 0.75 from the legacy
    linear formula, NOT 0.80 from the soy decay_ticks=5 fallback).
    This is the bug fix: the regulatory formula is exponential.

    Target is set high enough to force the walk-down past level 1 so
    the order at 49 qualifies."""
    s = compute_strike_score(
        our_orders=[{"order_id": "off1", "side": "bid",
                     "price_cents": 49, "size": 4}],
        yes_levels=[{"price_cents": 50, "size": 5.0},
                    {"price_cents": 49, "size": 4.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=9,
    )
    m = s.multipliers[0]
    assert m.multiplier == pytest.approx(0.25)
    assert m.qualified is True
    assert m.score_contribution == pytest.approx(1.0)  # 4 × 0.25


def test_distance_two_with_df25_is_one_sixteenth() -> None:
    """DF^2 = 0.0625 at distance 2."""
    s = compute_strike_score(
        our_orders=[{"order_id": "off2", "side": "bid",
                     "price_cents": 48, "size": 16}],
        yes_levels=[{"price_cents": 50, "size": 5.0},
                    {"price_cents": 48, "size": 16.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=20,
    )
    m = s.multipliers[0]
    assert m.multiplier == pytest.approx(0.0625)
    assert m.qualified is True
    assert m.score_contribution == pytest.approx(1.0)  # 16 × 0.0625


def test_df_50pct_geometric_decay() -> None:
    """DF=0.5 → 1.0, 0.5, 0.25, 0.125 ..."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "d0", "side": "bid", "price_cents": 50, "size": 1},
            {"order_id": "d1", "side": "bid", "price_cents": 49, "size": 1},
            {"order_id": "d2", "side": "bid", "price_cents": 48, "size": 1},
            {"order_id": "d3", "side": "bid", "price_cents": 47, "size": 1},
        ],
        yes_levels=[{"price_cents": p, "size": 1.0} for p in (50, 49, 48, 47)],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.5, target_size_contracts=4,
    )
    by_id = {m.order_id: m for m in s.multipliers}
    assert by_id["d0"].multiplier == pytest.approx(1.0)
    assert by_id["d1"].multiplier == pytest.approx(0.5)
    assert by_id["d2"].multiplier == pytest.approx(0.25)
    assert by_id["d3"].multiplier == pytest.approx(0.125)


def test_df_100pct_flat() -> None:
    """At DF=1.0, mult is 1.0 at every distance (1^N = 1)."""
    s = compute_strike_score(
        our_orders=[{"order_id": "off", "side": "bid",
                     "price_cents": 49, "size": 1}],
        yes_levels=[{"price_cents": 50, "size": 1.0},
                    {"price_cents": 49, "size": 1.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=1.0, target_size_contracts=2,
    )
    assert s.multipliers[0].multiplier == pytest.approx(1.0)


# ── Reference Price gating: best bid must be < 99 ───────────────────


def test_ref_price_at_99_disqualifies_side() -> None:
    """Per Appendix A: 'If the highest yes bid price exists and is less
    than the highest possible price, it is assigned to the Reference
    Yes Price.' A best bid of 99¢ has no qualifying bids."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 99, "size": 5}],
        yes_levels=[{"price_cents": 99, "size": 5.0}],
        no_levels=[],
        best_bid_c=99, best_ask_c=100,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.yes_qualifying is False
    assert s.our_yes_score == 0.0
    assert s.yes_total_score == 0.0
    assert s.multipliers[0].qualified is False


def test_ref_price_at_98_qualifies() -> None:
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 98, "size": 5}],
        yes_levels=[{"price_cents": 98, "size": 5.0}],
        no_levels=[],
        best_bid_c=98, best_ask_c=100,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.yes_qualifying is True
    assert s.our_yes_score == pytest.approx(5.0)


# ── Qualifying walk-down (target size) ──────────────────────────────


def test_walkdown_stops_when_target_reached() -> None:
    """Target size = 10. Best level has 6 contracts → keep walking.
    Next level adds 5 → cumulative 11 ≥ 10 → STOP. Both levels
    qualify but no deeper levels do."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "deep", "side": "bid",
             "price_cents": 47, "size": 100},
            {"order_id": "qual", "side": "bid",
             "price_cents": 49, "size": 5},
        ],
        yes_levels=[
            {"price_cents": 50, "size": 6.0},
            {"price_cents": 49, "size": 5.0},
            {"price_cents": 47, "size": 100.0},  # well below threshold
        ],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=10,
    )
    by_id = {m.order_id: m for m in s.multipliers}
    # Deep bid is below the threshold (which is 49) — does NOT qualify
    assert by_id["deep"].qualified is False
    assert by_id["deep"].score_contribution == 0.0
    # Order at 49 qualifies — distance 1, mult 0.25
    assert by_id["qual"].qualified is True
    assert by_id["qual"].multiplier == pytest.approx(0.25)
    # Total = 6×1.0 + 5×0.25 = 7.25
    assert s.yes_total_score == pytest.approx(7.25)


def test_walkdown_target_unreached_no_qualifying() -> None:
    """Cumulative size never reaches target → side has no qualifying
    bids, our score = 0."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 1}],
        yes_levels=[{"price_cents": 50, "size": 1.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1000,
    )
    assert s.yes_qualifying is False
    assert s.yes_total_score == 0.0
    assert s.our_yes_score == 0.0


def test_walkdown_target_exactly_reached_at_first_level() -> None:
    """If level 1 has size ≥ target, we stop immediately. Threshold =
    reference price. Bids below don't qualify."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "best", "side": "bid",
             "price_cents": 50, "size": 10},
            {"order_id": "below", "side": "bid",
             "price_cents": 49, "size": 5},
        ],
        yes_levels=[
            {"price_cents": 50, "size": 10.0},
            {"price_cents": 49, "size": 5.0},
        ],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=10,
    )
    by_id = {m.order_id: m for m in s.multipliers}
    assert by_id["best"].qualified is True
    assert by_id["below"].qualified is False
    assert s.yes_total_score == pytest.approx(10.0)


# ── Per-side normalization + snapshot/pool-share ────────────────────


def test_we_own_yes_side_no_one_else() -> None:
    """We are the only resting order on the yes side → our normalized
    yes share = 1.0. No-side has another participant. Pool share =
    (1.0 + 0.0) / 2 = 0.5."""
    s = compute_strike_score(
        our_orders=[{"order_id": "ours", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 5.0}],   # only us on yes
        no_levels=[{"price_cents": 30, "size": 5.0}],    # someone else on no
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.our_yes_normalized == pytest.approx(1.0)
    assert s.our_no_normalized == pytest.approx(0.0)
    assert s.snapshot_score == pytest.approx(1.0)
    assert s.pool_share == pytest.approx(0.5)
    assert s.share_pct == pytest.approx(50.0)


def test_we_own_both_sides() -> None:
    """We have all the resting on both sides → 100% of pool."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "y", "side": "bid",
             "price_cents": 50, "size": 5},
            {"order_id": "n", "side": "ask",
             "price_cents": 70, "size": 5},
        ],
        yes_levels=[{"price_cents": 50, "size": 5.0}],
        no_levels=[{"price_cents": 30, "size": 5.0}],   # = ask 70
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.pool_share == pytest.approx(1.0)
    assert s.share_pct == pytest.approx(100.0)


def test_only_yes_side_has_qualifying_pool_share_uses_one_side() -> None:
    """No-side has 0 levels → only yes side counts → sides_active=1 →
    pool_share = our_yes_normalized."""
    s = compute_strike_score(
        our_orders=[{"order_id": "ours", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 10.0}],  # 5 ours, 5 theirs
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.our_yes_normalized == pytest.approx(0.5)
    assert s.no_qualifying is False
    assert s.pool_share == pytest.approx(0.5)


def test_neither_side_qualifies_share_is_zero() -> None:
    """Both sides empty / both unable to reach target → 0 share."""
    s = compute_strike_score(
        our_orders=[],
        yes_levels=[],
        no_levels=[],
        best_bid_c=0, best_ask_c=100,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.pool_share == 0.0
    assert s.snapshot_score == 0.0


# ── No-side via Yes-ask inversion ───────────────────────────────────


def test_yes_ask_at_p_scored_as_no_bid_at_100_minus_p() -> None:
    """Our Yes ask at 70 ⇔ No bid at 30. With no_levels having a No bid
    at 30 (best), our distance-from-no-ref = 0 → mult 1.0."""
    s = compute_strike_score(
        our_orders=[{"order_id": "ask", "side": "ask",
                     "price_cents": 70, "size": 5}],
        yes_levels=[],
        no_levels=[{"price_cents": 30, "size": 5.0}],   # = ask at 70
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    m = s.multipliers[0]
    assert m.multiplier == pytest.approx(1.0)
    assert m.qualified is True
    assert s.our_no_score == pytest.approx(5.0)


def test_yes_ask_one_off_best_no_bid() -> None:
    """Best No bid = 30 (= best Yes ask 70). Our ask at 71 ⇔ No bid at 29
    → distance 1 → mult 0.25. Target high enough to walk past first
    level."""
    s = compute_strike_score(
        our_orders=[{"order_id": "ask", "side": "ask",
                     "price_cents": 71, "size": 4}],
        yes_levels=[],
        no_levels=[
            {"price_cents": 30, "size": 5.0},
            {"price_cents": 29, "size": 4.0},
        ],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=9,
    )
    m = s.multipliers[0]
    assert m.multiplier == pytest.approx(0.25)
    assert m.qualified is True
    assert m.score_contribution == pytest.approx(1.0)


# ── Projected / hourly / daily reward ───────────────────────────────


def test_projected_reward_full_period() -> None:
    """Holding our share constant for the period: payout = share × pool."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 10.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.pool_share == pytest.approx(0.5)
    # only yes qualifies → sides_active=1 → pool_share=0.5; full pool=$10 → $5
    assert s.projected_reward_dollars(10.0) == pytest.approx(5.0)
    assert s.projected_reward_dollars(0) == 0.0
    assert s.projected_reward_dollars(None) == 0.0


def test_hourly_and_daily_rates() -> None:
    """A 24-hour period with $24 reward and 50% share → $12 projected,
    $0.50/h, $12/day."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 10.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    period_s = 24 * 3600
    assert s.projected_reward_dollars(24.0) == pytest.approx(12.0)
    assert s.hourly_reward_dollars(24.0, period_s) == pytest.approx(0.5)
    assert s.daily_reward_dollars(24.0, period_s) == pytest.approx(12.0)


def test_hourly_zero_when_no_period_duration() -> None:
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 5.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert s.hourly_reward_dollars(10.0, 0) == 0.0
    assert s.daily_reward_dollars(10.0, 0) == 0.0
    assert s.hourly_reward_dollars(10.0, -1) == 0.0


# ── Degenerate / no-program / robustness ────────────────────────────


def test_no_discount_factor_returns_zero_score() -> None:
    """Without an active LIP program the strike has no scoring."""
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 5.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=None, target_size_contracts=10,
    )
    assert s.pool_share == 0.0
    assert s.our_yes_score == 0.0


def test_no_target_size_returns_zero_score() -> None:
    s = compute_strike_score(
        our_orders=[{"order_id": "a", "side": "bid",
                     "price_cents": 50, "size": 5}],
        yes_levels=[{"price_cents": 50, "size": 5.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=None,
    )
    assert s.pool_share == 0.0


def test_compute_score_skips_malformed_entries() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "good", "side": "bid",
             "price_cents": 50, "size": 5},
            {},  # missing fields
            {"order_id": "bad", "side": "bid",
             "price_cents": "x", "size": 5},
            {"order_id": "neg", "side": "bid",
             "price_cents": 50, "size": -1},
        ],
        yes_levels=[
            {"price_cents": 50, "size": 5.0},
            {"price_cents": "?", "size": 5.0},  # malformed level
        ],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    # Only "good" should be in mults, contributing 5 × 1.0 = 5.0
    assert len(s.multipliers) == 1
    assert s.multipliers[0].order_id == "good"
    assert s.our_yes_score == pytest.approx(5.0)


def test_unknown_side_skipped() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "ok", "side": "bid",
             "price_cents": 50, "size": 5},
            {"order_id": "weird", "side": "yolo",
             "price_cents": 50, "size": 5},
        ],
        yes_levels=[{"price_cents": 50, "size": 5.0}],
        no_levels=[],
        best_bid_c=50, best_ask_c=70,
        discount_factor=0.25, target_size_contracts=1,
    )
    assert len(s.multipliers) == 1
    assert s.multipliers[0].order_id == "ok"


# ── Frozen dataclass invariants ─────────────────────────────────────


def test_strike_score_is_immutable() -> None:
    s = StrikeScore(
        our_yes_score=1.0, yes_total_score=2.0,
        our_no_score=0.0, no_total_score=0.0,
        our_yes_normalized=0.5, our_no_normalized=0.0,
        yes_qualifying=True, no_qualifying=False,
        yes_ref_price_c=50, no_ref_price_c=None,
        snapshot_score=0.5, pool_share=0.5,
        multipliers=[],
    )
    with pytest.raises(Exception):
        s.our_yes_score = 999  # type: ignore[misc]


def test_resting_multiplier_is_immutable() -> None:
    m = RestingMultiplier(
        order_id="a", side="bid", price_c=50, size=5,
        multiplier=1.0, score_contribution=5.0, qualified=True,
    )
    with pytest.raises(Exception):
        m.multiplier = 0.0  # type: ignore[misc]


# ── Renderer integration ────────────────────────────────────────────


def test_join_strike_data_attaches_lip_score_when_orderbook_present() -> None:
    from lipmm.control.web.renderer import join_strike_data
    runtime = {
        "positions": [],
        "resting_orders": [
            {"ticker": "KX-T1", "order_id": "a", "side": "bid",
             "price_cents": 50, "size": 5},
        ],
    }
    incentives = {"programs": [{
        "market_ticker": "KX-T1",
        "discount_factor_bps": 2500,
        "target_size_contracts": 1.0,
        "period_reward_dollars": 100.0,
        "start_date_ts": 0.0, "end_date_ts": 86400.0,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 50, "best_ask_c": 70,
        "yes_levels": [{"price_cents": 50, "size": 10.0}],
        "no_levels": [],
    }]}
    strikes = join_strike_data({}, runtime, incentives, orderbooks)
    s = strikes[0]
    assert s["lip_score"] is not None
    # 5 ours / 10 total on yes → 0.5 normalized; only yes qualifies → 0.5 pool
    assert s["lip_score"].pool_share == pytest.approx(0.5)


def test_join_strike_data_lip_score_is_none_without_orderbook() -> None:
    from lipmm.control.web.renderer import join_strike_data
    runtime = {
        "positions": [{"ticker": "KX-T1", "quantity": 5,
                       "avg_cost_cents": 50}],
        "resting_orders": [],
    }
    strikes = join_strike_data({}, runtime, {}, {})
    s = strikes[0]
    assert s["lip_score"] is None
