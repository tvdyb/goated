"""Unit tests for deploy.truev_backtest helpers — date parsing,
strike-boundary resolution, implied σ. No live data."""

from __future__ import annotations

import math
from datetime import date

import pytest

from deploy.truev_backtest import (
    _compute_implied_sigma,
    _date_from_event_ticker,
    _implied_actual_value,
    _strike_threshold_from_market,
)


# ── Date parsing ────────────────────────────────────────────────


def test_date_parses_kxtruev_format() -> None:
    assert _date_from_event_ticker("KXTRUEV-26MAY07") == date(2026, 5, 7)


def test_date_handles_two_digit_year() -> None:
    assert _date_from_event_ticker("KXTRUEV-25DEC31") == date(2025, 12, 31)


def test_date_returns_none_on_unknown_month() -> None:
    assert _date_from_event_ticker("KXTRUEV-26ZZZ07") is None


def test_date_returns_none_on_short_tail() -> None:
    assert _date_from_event_ticker("KXTRUEV-26") is None


def test_date_returns_none_on_no_dash() -> None:
    assert _date_from_event_ticker("KXTRUEV") is None


# ── Strike threshold extraction ────────────────────────────────


def test_threshold_from_floor_strike() -> None:
    assert _strike_threshold_from_market({"floor_strike": 1290.5}) == 1290.5


def test_threshold_from_cap_strike_when_no_floor() -> None:
    assert _strike_threshold_from_market({"cap_strike": 1300.0}) == 1300.0


def test_threshold_from_ticker_t_segment_when_no_strike_field() -> None:
    m = {"ticker": "KXTRUEV-26MAY07-T1290.40"}
    assert _strike_threshold_from_market(m) == 1290.40


def test_threshold_returns_none_on_no_match() -> None:
    assert _strike_threshold_from_market({"ticker": "FOO-BAR-NOTSTRIKE"}) is None


# ── Boundary resolution ────────────────────────────────────────


def _mk(ticker: str, threshold: float, result: str) -> dict:
    return {
        "ticker": ticker, "floor_strike": threshold, "result": result,
    }


def test_boundary_clean_yes_then_no_returns_midpoint() -> None:
    """Strikes at 1280, 1290, 1300, 1310. YES YES NO NO. Actual is
    between 1290 and 1300 → midpoint 1295."""
    markets = [
        _mk("a", 1280.0, "yes"),
        _mk("b", 1290.0, "yes"),
        _mk("c", 1300.0, "no"),
        _mk("d", 1310.0, "no"),
    ]
    assert _implied_actual_value(markets) == pytest.approx(1295.0)


def test_boundary_with_inverted_convention() -> None:
    """If event is 'below K' (NO NO YES YES), resolve same way."""
    markets = [
        _mk("a", 1280.0, "no"),
        _mk("b", 1290.0, "no"),
        _mk("c", 1300.0, "yes"),
        _mk("d", 1310.0, "yes"),
    ]
    # Actual is between 1290 and 1300 → 1295
    assert _implied_actual_value(markets) == pytest.approx(1295.0)


def test_boundary_all_yes_estimates_above_highest() -> None:
    markets = [
        _mk("a", 1280.0, "yes"),
        _mk("b", 1290.0, "yes"),
    ]
    res = _implied_actual_value(markets)
    assert res is not None
    assert res > 1290.0


def test_boundary_all_no_estimates_below_lowest() -> None:
    markets = [
        _mk("a", 1280.0, "no"),
        _mk("b", 1290.0, "no"),
    ]
    res = _implied_actual_value(markets)
    assert res is not None
    assert res < 1280.0


def test_boundary_returns_none_on_unsettled() -> None:
    markets = [
        _mk("a", 1280.0, ""),
        _mk("b", 1290.0, "active"),
    ]
    assert _implied_actual_value(markets) is None


def test_boundary_returns_none_on_messy_pattern() -> None:
    """YES NO YES NO — not a clean sweep. Bail."""
    markets = [
        _mk("a", 1280.0, "yes"),
        _mk("b", 1290.0, "no"),
        _mk("c", 1300.0, "yes"),
        _mk("d", 1310.0, "no"),
    ]
    assert _implied_actual_value(markets) is None


# ── Implied σ from log returns ─────────────────────────────────


def test_sigma_zero_on_flat_series() -> None:
    """Constant index value → no return variance → σ=0."""
    actuals = {
        date(2026, 5, 1): 1290.0,
        date(2026, 5, 2): 1290.0,
        date(2026, 5, 3): 1290.0,
    }
    sigma_d, sigma_a, n = _compute_implied_sigma(actuals)
    assert sigma_d == pytest.approx(0.0)
    assert sigma_a == pytest.approx(0.0)
    assert n == 2


def test_sigma_recovers_known_volatility() -> None:
    """Manually-constructed log-return series with known stdev."""
    # log returns: +0.01, -0.01, +0.01, -0.01 → pstdev = 0.01
    base = 1000.0
    series = [base]
    for r in (0.01, -0.01, 0.01, -0.01):
        series.append(series[-1] * math.exp(r))
    actuals = {
        date(2026, 5, i): v for i, v in enumerate(series, start=1)
    }
    sigma_d, sigma_a, n = _compute_implied_sigma(actuals)
    assert sigma_d == pytest.approx(0.01, abs=1e-9)
    assert sigma_a == pytest.approx(0.01 * math.sqrt(252), abs=1e-9)
    assert n == 4


def test_sigma_returns_zero_on_too_few_points() -> None:
    actuals = {date(2026, 5, 1): 1290.0}
    sigma_d, sigma_a, n = _compute_implied_sigma(actuals)
    assert (sigma_d, sigma_a, n) == (0.0, 0.0, 0)
