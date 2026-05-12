"""Unit tests for TruEV index reconstruction math.

Pure numerical tests — no I/O, no live data."""

from __future__ import annotations

import math

import pytest

from lipmm.theo.providers._truev_index import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_Q4_2025,
    TruEvAnchor,
    TruEvWeights,
    reconstruct_index,
)


# ── TruEvAnchor validation ──────────────────────────────────────────


def test_anchor_rejects_zero_index_value() -> None:
    with pytest.raises(ValueError, match="anchor_index_value"):
        TruEvAnchor(
            anchor_date="2026-04-22",
            anchor_index_value=0.0,
            anchor_prices={"HG=F": 4.5},
        )


def test_anchor_rejects_negative_anchor_price() -> None:
    with pytest.raises(ValueError, match="anchor price"):
        TruEvAnchor(
            anchor_date="2026-04-22",
            anchor_index_value=1290.0,
            anchor_prices={"HG=F": -1.0},
        )


# ── TruEvWeights validation ─────────────────────────────────────────


def test_weights_rejects_non_unity_sum() -> None:
    with pytest.raises(ValueError, match="must sum to 1.0"):
        TruEvWeights(
            quarter_start_iso="2025-10-01",
            weights={"HG=F": 0.5, "LTH=F": 0.4},  # sums to 0.9
        )


def test_weights_rejects_out_of_range_weight() -> None:
    with pytest.raises(ValueError, match="must be in"):
        TruEvWeights(
            quarter_start_iso="2025-10-01",
            weights={"HG=F": 1.5, "LTH=F": -0.5},  # sums to 1.0 but out-of-range
        )


def test_weights_accepts_valid_distribution() -> None:
    w = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 0.5, "LTH=F": 0.5},
    )
    assert sum(w.weights.values()) == pytest.approx(1.0)


# ── reconstruct_index core math ─────────────────────────────────────


def test_reconstruct_index_unchanged_when_prices_at_anchor() -> None:
    """If today's prices equal the anchor prices, index = anchor value."""
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1290.40,
        anchor_prices={"HG=F": 4.50, "LTH=F": 4.20},
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 0.6, "LTH=F": 0.4},
    )
    today = {"HG=F": 4.50, "LTH=F": 4.20}
    result = reconstruct_index(today, weights, anchor)
    assert result == pytest.approx(1290.40)


def test_reconstruct_index_doubling_one_component() -> None:
    """Symbol with weight 1.0; doubling its price doubles the index."""
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1000.0,
        anchor_prices={"HG=F": 5.0},
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 1.0},
    )
    today = {"HG=F": 10.0}
    result = reconstruct_index(today, weights, anchor)
    assert result == pytest.approx(2000.0)


def test_reconstruct_index_weighted_basket_average() -> None:
    """Two components, each with their own price ratio. Index is the
    weighted average of returns × anchor."""
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1000.0,
        anchor_prices={"HG=F": 4.0, "LTH=F": 5.0},
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 0.7, "LTH=F": 0.3},
    )
    today = {"HG=F": 4.40, "LTH=F": 4.50}  # +10% Cu, -10% Li
    # basket_return = 0.7 * 1.10 + 0.3 * 0.90 = 0.77 + 0.27 = 1.04
    result = reconstruct_index(today, weights, anchor)
    assert result == pytest.approx(1040.0)


def test_reconstruct_index_raises_on_missing_today_symbol() -> None:
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1000.0,
        anchor_prices={"HG=F": 4.0, "LTH=F": 5.0},
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 0.7, "LTH=F": 0.3},
    )
    today = {"HG=F": 4.40}  # missing LTH=F
    with pytest.raises(ValueError, match="current_prices missing"):
        reconstruct_index(today, weights, anchor)


def test_reconstruct_index_raises_on_missing_anchor_symbol() -> None:
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1000.0,
        anchor_prices={"HG=F": 4.0},  # missing LTH=F
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 0.7, "LTH=F": 0.3},
    )
    today = {"HG=F": 4.40, "LTH=F": 4.50}
    with pytest.raises(ValueError, match="anchor.anchor_prices missing"):
        reconstruct_index(today, weights, anchor)


def test_reconstruct_index_raises_on_zero_today_price() -> None:
    anchor = TruEvAnchor(
        anchor_date="2026-04-22",
        anchor_index_value=1000.0,
        anchor_prices={"HG=F": 4.0},
    )
    weights = TruEvWeights(
        quarter_start_iso="2025-10-01",
        weights={"HG=F": 1.0},
    )
    today = {"HG=F": 0.0}
    with pytest.raises(ValueError, match="must be > 0"):
        reconstruct_index(today, weights, anchor)


# ── Default Phase-1 weights ─────────────────────────────────────────


def test_default_weights_sum_to_one() -> None:
    assert sum(DEFAULT_WEIGHTS_Q4_2025.weights.values()) == pytest.approx(1.0)


def test_default_weights_cover_six_components() -> None:
    # LIVE basket: TE-scraped lithium replaces the LIT equity proxy.
    # Backtest path keeps LIT (see DEFAULT_WEIGHTS_BACKTEST) since TE
    # has no historicals.
    expected = {"HG=F", "LITHIUM_TE", "NICK.L", "COBALT_TE", "PA=F", "PL=F"}
    assert set(DEFAULT_WEIGHTS_Q4_2025.weights.keys()) == expected


def test_default_weights_renormalization_preserves_ratios() -> None:
    """After renormalization, copper/lithium ratio equals raw ratio."""
    raw_cu = 0.3865
    raw_li = 0.3354
    w = DEFAULT_WEIGHTS_Q4_2025.weights
    assert (w["HG=F"] / w["LITHIUM_TE"]) == pytest.approx(raw_cu / raw_li)


def test_default_anchor_at_anchor_returns_anchor_value() -> None:
    """Sanity: feeding the placeholder anchor's prices produces the
    placeholder anchor value (round-trip)."""
    result = reconstruct_index(
        dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices),
        DEFAULT_WEIGHTS_Q4_2025,
        DEFAULT_ANCHOR_PLACEHOLDER,
    )
    assert result == pytest.approx(DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value)


def test_uniform_basket_return_scales_anchor() -> None:
    """If every component appreciates by 5%, the index moves by 5%."""
    today = {
        sym: p * 1.05
        for sym, p in DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices.items()
    }
    result = reconstruct_index(
        today, DEFAULT_WEIGHTS_Q4_2025, DEFAULT_ANCHOR_PLACEHOLDER,
    )
    assert result == pytest.approx(
        DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value * 1.05,
    )
