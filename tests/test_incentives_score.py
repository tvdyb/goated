"""Tests for Phase 11 — per-strike LIP score (lipmm.incentives.score).

Mirror of `tests/test_lip_score.py` but for the lipmm-native port at
`lipmm/incentives/score.py`. The soy bot's lip_score has its own
suite + numba JIT path; this is the plain-Python copy used by the
dashboard, with a tighter scope (no rolling windows, no telemetry
callbacks — render-time only).

Covers:
  - linear_multiplier math (best=1.0, distance N → 1-N/decay, beyond=0)
  - compute_strike_score across our orders + orderbook depth
  - share computation degenerate cases
  - projected_reward_dollars math
  - bad order entries are skipped, not raised
  - decay_ticks customization
  - StrikeScore frozen dataclass invariants
"""

from __future__ import annotations

import pytest

from lipmm.incentives import (
    DEFAULT_DECAY_TICKS,
    RestingMultiplier,
    StrikeScore,
    compute_strike_score,
    linear_multiplier,
)


# ── linear_multiplier ────────────────────────────────────────────────


def test_multiplier_at_best_is_one() -> None:
    assert linear_multiplier(50, 50) == 1.0


def test_multiplier_decays_linearly_within_decay_ticks() -> None:
    # 5-tick default decay: 1c off → 0.8, 2c → 0.6, 3c → 0.4, 4c → 0.2
    assert linear_multiplier(49, 50) == pytest.approx(0.8)
    assert linear_multiplier(48, 50) == pytest.approx(0.6)
    assert linear_multiplier(47, 50) == pytest.approx(0.4)
    assert linear_multiplier(46, 50) == pytest.approx(0.2)


def test_multiplier_zero_at_decay_threshold() -> None:
    assert linear_multiplier(45, 50) == 0.0


def test_multiplier_zero_beyond_decay() -> None:
    assert linear_multiplier(40, 50) == 0.0
    assert linear_multiplier(99, 50) == 0.0


def test_multiplier_symmetric_around_best() -> None:
    """Multiplier depends on |distance|, so above and below are equal."""
    assert linear_multiplier(48, 50) == linear_multiplier(52, 50)


def test_multiplier_custom_decay_ticks() -> None:
    # decay=10 → 1c off → 0.9
    assert linear_multiplier(49, 50, decay_ticks=10) == pytest.approx(0.9)


def test_multiplier_rejects_invalid_decay() -> None:
    with pytest.raises(ValueError, match="decay_ticks"):
        linear_multiplier(50, 50, decay_ticks=0)


def test_default_decay_ticks_is_5() -> None:
    assert DEFAULT_DECAY_TICKS == 5


# ── compute_strike_score: our_score, total_score, share ─────────────


def test_compute_score_two_at_best_full_score() -> None:
    """Both our orders sit at best — each contributes size × 1.0.
    No competitors visible, so we own 100% of the score."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "a", "side": "bid", "price_cents": 49, "size": 8},
            {"order_id": "b", "side": "ask", "price_cents": 52, "size": 8},
        ],
        yes_levels=[{"price_cents": 49, "size": 8.0}],
        no_levels=[{"price_cents": 48, "size": 8.0}],
        best_bid_c=49, best_ask_c=52,
    )
    assert s.our_score == pytest.approx(16.0)
    assert s.total_score == pytest.approx(16.0)
    assert s.share == pytest.approx(1.0)
    assert s.share_pct == pytest.approx(100.0)


def test_compute_score_we_are_a_minority() -> None:
    """Two equal market-makers stacking at the same price: 5 ours
    out of 10 visible → 50% share."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "a", "side": "bid", "price_cents": 49, "size": 5},
        ],
        yes_levels=[{"price_cents": 49, "size": 10.0}],
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    assert s.our_score == pytest.approx(5.0)
    assert s.total_score == pytest.approx(10.0)
    assert s.share == pytest.approx(0.5)


def test_compute_score_off_best_contributes_partial() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "a", "side": "bid", "price_cents": 47, "size": 10},  # 2c off
        ],
        yes_levels=[{"price_cents": 47, "size": 10.0}],
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    # 10 × 0.6 = 6.0
    assert s.our_score == pytest.approx(6.0)


def test_compute_score_too_far_off_contributes_zero() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "a", "side": "bid", "price_cents": 40, "size": 100},
        ],
        yes_levels=[{"price_cents": 40, "size": 100.0}],
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    assert s.our_score == 0.0
    assert s.total_score == 0.0
    assert s.share == 0.0  # not NaN — degenerate case


def test_compute_score_attaches_per_resting_multipliers() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "best", "side": "bid", "price_cents": 49, "size": 5},
            {"order_id": "off",  "side": "bid", "price_cents": 47, "size": 5},
            {"order_id": "ask",  "side": "ask", "price_cents": 52, "size": 5},
        ],
        yes_levels=[{"price_cents": 49, "size": 5}, {"price_cents": 47, "size": 5}],
        no_levels=[{"price_cents": 48, "size": 5}],
        best_bid_c=49, best_ask_c=52,
    )
    by_id = {m.order_id: m for m in s.multipliers}
    assert by_id["best"].multiplier == 1.0
    assert by_id["off"].multiplier == pytest.approx(0.6)
    assert by_id["ask"].multiplier == 1.0
    assert by_id["best"].score_contribution == pytest.approx(5.0)
    assert by_id["off"].score_contribution == pytest.approx(3.0)


def test_compute_score_skips_malformed_entries() -> None:
    """Bad data shouldn't crash — a bad row is dropped, others still
    contribute."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "good", "side": "bid", "price_cents": 49, "size": 5},
            {},  # missing fields
            {"order_id": "bad", "side": "bid", "price_cents": "x", "size": 5},
            {"order_id": "neg", "side": "bid", "price_cents": 49, "size": -1},
        ],
        yes_levels=[
            {"price_cents": 49, "size": 5.0},
            {"price_cents": "?", "size": 5.0},  # malformed
        ],
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    assert s.our_score == pytest.approx(5.0)
    assert len(s.multipliers) == 1
    assert s.multipliers[0].order_id == "good"


def test_compute_score_unknown_side_skipped() -> None:
    s = compute_strike_score(
        our_orders=[
            {"order_id": "ok", "side": "bid", "price_cents": 49, "size": 5},
            {"order_id": "weird", "side": "yolo", "price_cents": 49, "size": 5},
        ],
        yes_levels=[{"price_cents": 49, "size": 10.0}],
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    assert len(s.multipliers) == 1
    assert s.multipliers[0].order_id == "ok"


# ── projected_reward_dollars ─────────────────────────────────────────


def test_projected_reward_scales_with_share_and_pool() -> None:
    s = StrikeScore(our_score=5.0, total_score=10.0, share=0.5, multipliers=[])
    assert s.projected_reward_dollars(125.0) == pytest.approx(62.5)
    assert s.projected_reward_dollars(0) == 0.0
    assert s.projected_reward_dollars(None) == 0.0


def test_share_pct_property() -> None:
    s = StrikeScore(our_score=5.0, total_score=10.0, share=0.5, multipliers=[])
    assert s.share_pct == 50.0


# ── Frozen dataclass invariants ─────────────────────────────────────


def test_strike_score_is_immutable() -> None:
    s = StrikeScore(our_score=1.0, total_score=2.0, share=0.5, multipliers=[])
    with pytest.raises(Exception):
        s.our_score = 999  # type: ignore[misc]


def test_resting_multiplier_is_immutable() -> None:
    m = RestingMultiplier(
        order_id="a", side="bid", price_c=49, size=5,
        multiplier=1.0, score_contribution=5.0,
    )
    with pytest.raises(Exception):
        m.multiplier = 0.0  # type: ignore[misc]


# ── Share capped at 100% ────────────────────────────────────────────


def test_share_capped_at_one() -> None:
    """Edge case: if our orders dominate but total_score numerically
    drifts below our_score (rare, e.g. our orders count twice), share
    is capped at 1.0 to avoid >100% display."""
    s = compute_strike_score(
        our_orders=[
            {"order_id": "a", "side": "bid", "price_cents": 49, "size": 100},
        ],
        yes_levels=[{"price_cents": 49, "size": 10.0}],  # claims only 10
        no_levels=[],
        best_bid_c=49, best_ask_c=52,
    )
    assert s.share == 1.0
    assert s.share_pct == 100.0


# ── Renderer integration: lip_score appears in joined strike data ───


def test_join_strike_data_attaches_lip_score_when_orderbook_present() -> None:
    from lipmm.control.web.renderer import join_strike_data
    runtime = {
        "positions": [],
        "resting_orders": [
            {"ticker": "KX-T1", "order_id": "a", "side": "bid",
             "price_cents": 49, "size": 5},
        ],
    }
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 49, "best_ask_c": 52,
        "yes_levels": [{"price_cents": 49, "size": 10.0}],
        "no_levels": [],
    }]}
    strikes = join_strike_data({}, runtime, {}, orderbooks)
    s = strikes[0]
    assert s["lip_score"] is not None
    assert s["lip_score"].our_score == pytest.approx(5.0)
    assert s["lip_score"].share == pytest.approx(0.5)


def test_join_strike_data_lip_score_is_none_without_orderbook() -> None:
    from lipmm.control.web.renderer import join_strike_data
    runtime = {
        "positions": [{"ticker": "KX-T1", "quantity": 5, "avg_cost_cents": 50}],
        "resting_orders": [],
    }
    strikes = join_strike_data({}, runtime, {}, {})
    s = strikes[0]
    assert s["lip_score"] is None
