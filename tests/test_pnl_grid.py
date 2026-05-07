"""Tests for the per-position PnL grid renderer."""

from __future__ import annotations

import pytest

from lipmm.control.web.renderer import _pnl_rows, render_pnl_grid


def test_empty_when_no_positions() -> None:
    rows, totals = _pnl_rows({}, {}, {})
    assert rows == []
    assert totals["total_cost"] == 0.0


def test_zero_quantity_positions_skipped() -> None:
    runtime = {"positions": [{"ticker": "KX-T1", "quantity": 0, "avg_cost_cents": 50}]}
    rows, _ = _pnl_rows(runtime, {}, {})
    assert rows == []


def test_long_yes_position_unrealized_with_higher_mark() -> None:
    """Bought 10 yes at 40¢; mark (best yes-bid) is now 55¢ → +$1.50 unrealized."""
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
        "realized_pnl_dollars": 0.0, "fees_paid_dollars": 0.0,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 55, "best_ask_c": 60,
    }]}
    rows, totals = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    assert r["qty"] == 10
    assert r["side_label"] == "Y"
    assert r["mtm_mark_c"] == 55  # best yes-bid (where we'd close)
    assert r["total_cost"] == pytest.approx(4.0)   # 10 × 0.40
    assert r["mtm_value"] == pytest.approx(5.5)    # 10 × 0.55
    assert r["unrealized"] == pytest.approx(1.5)
    assert totals["unrealized"] == pytest.approx(1.5)


def test_long_no_position_unrealized_with_lower_yes_ask() -> None:
    """Short Yes (long No) 5 at avg 40¢ — i.e., we paid 60¢ on No
    side. To close, we'd buy yes back at best ask."""
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": -5, "avg_cost_cents": 40,
        "realized_pnl_dollars": 0.0, "fees_paid_dollars": 0.0,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 35, "best_ask_c": 38,
    }]}
    rows, totals = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    assert r["qty"] == -5
    assert r["side_label"] == "N"
    assert r["mtm_mark_c"] == 38   # best yes-ask (where we'd close)
    # cost = 5 × 0.40 (the cost basis stored as yes-cents avg)
    assert r["total_cost"] == pytest.approx(2.0)
    # mtm = 5 × (1 - 0.38) = 3.10 (equivalent No price = 100−38 = 62¢)
    assert r["mtm_value"] == pytest.approx(3.10)
    assert r["unrealized"] == pytest.approx(1.10)


def test_theo_override_takes_priority_over_provider() -> None:
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 50, "best_ask_c": 52,
        "theo": {"yes_cents": 51, "confidence": 0.9, "source": "TruEV", "source_kind": "provider"},
    }]}
    snapshot = {"theo_overrides": [{"ticker": "KX-T1", "yes_cents": 80}]}
    rows, _ = _pnl_rows(runtime, orderbooks, snapshot)
    r = rows[0]
    assert r["theo_yes_c"] == 80.0   # override wins
    assert r["theo_source"] == "manual"


def test_provider_theo_used_when_no_override() -> None:
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 50, "best_ask_c": 52,
        "theo": {"yes_cents": 51, "confidence": 0.9, "source": "TruEV", "source_kind": "provider"},
    }]}
    rows, _ = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    assert r["theo_yes_c"] == 51.0
    assert r["theo_source"] == "TruEV"


def test_zero_confidence_provider_theo_treated_as_missing() -> None:
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 50, "best_ask_c": 52,
        "theo": {"yes_cents": 51, "confidence": 0.0, "source": "TruEV"},
    }]}
    rows, _ = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    assert r["theo_yes_c"] is None
    assert r["theo_source"] == "—"
    assert r["expected_settle"] is None


def test_expected_settle_with_long_yes_and_high_theo() -> None:
    """Bought 10 Yes at 40¢; theo says 70¢ → expected settle = $7.00."""
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 50, "best_ask_c": 60,
        "theo": {"yes_cents": 70, "confidence": 0.8, "source": "test"},
    }]}
    rows, _ = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    assert r["expected_settle"] == pytest.approx(7.0)
    # edge = (held side theo - cost) per contract = 70 - 40 = 30¢
    assert r["edge_per_c"] == pytest.approx(30.0)


def test_expected_settle_for_long_no_uses_inverted_theo() -> None:
    """Short Yes 5 at 40¢; theo Yes=30¢ → No=70¢ → expected = 5×0.70."""
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": -5, "avg_cost_cents": 40,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 25, "best_ask_c": 30,
        "theo": {"yes_cents": 30, "confidence": 0.8, "source": "test"},
    }]}
    rows, _ = _pnl_rows(runtime, orderbooks, {})
    r = rows[0]
    # held side = No; theo No = 100 - 30 = 70¢; expected = 5 × 0.70
    assert r["expected_settle"] == pytest.approx(3.5)


def test_resting_orders_count_attached() -> None:
    runtime = {
        "positions": [{"ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40}],
        "resting_orders": [
            {"ticker": "KX-T1", "side": "bid", "order_id": "o1", "price_cents": 41, "size": 5},
            {"ticker": "KX-T1", "side": "ask", "order_id": "o2", "price_cents": 60, "size": 5},
        ],
    }
    rows, _ = _pnl_rows(runtime, {}, {})
    assert rows[0]["resting_count"] == 2


def test_render_pnl_grid_produces_html_with_total() -> None:
    runtime = {"positions": [{
        "ticker": "KX-T1", "quantity": 10, "avg_cost_cents": 40,
        "realized_pnl_dollars": 0.5, "fees_paid_dollars": 0.05,
    }]}
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 55, "best_ask_c": 60,
    }]}
    html = render_pnl_grid(runtime, orderbooks, {})
    assert "TOTAL" in html
    assert "KX-T1" in html
    # Cost = 10 × 0.40 = $4.00
    assert "4.00" in html
    # Unrealized = +$1.50
    assert "+1.50" in html
