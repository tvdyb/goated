"""Tests for engine.implied_vol — Kalshi-implied vol calibration."""

from __future__ import annotations

import math

import pytest
from scipy.special import ndtr

from engine.implied_vol import (
    DEFAULT_VOL,
    _implied_vol_bisect,
    _survival_prob,
    calibrate_vol,
    extract_strike_mids_from_orderbooks,
)


# -- Helpers ------------------------------------------------------------------

def _generate_market_mids(
    forward: float,
    sigma: float,
    tau: float,
    strikes: list[float],
) -> list[tuple[float, float]]:
    """Generate synthetic market mid-prices from a known vol."""
    result = []
    for k in strikes:
        prob = _survival_prob(forward, k, tau, sigma)
        result.append((k, prob))
    return result


# -- _survival_prob -----------------------------------------------------------

class TestSurvivalProb:
    def test_atm_near_50pct(self):
        # ATM strike should give ~50% survival (slightly above due to drift)
        prob = _survival_prob(10.0, 10.0, 1.0, 0.15)
        assert 0.45 < prob < 0.55

    def test_deep_itm(self):
        # Forward well above strike -> high survival
        prob = _survival_prob(12.0, 10.0, 0.01, 0.15)
        assert prob > 0.95

    def test_deep_otm(self):
        # Forward well below strike -> low survival
        prob = _survival_prob(8.0, 10.0, 0.01, 0.15)
        assert prob < 0.05

    def test_zero_vol(self):
        # With effectively zero vol, should be 1 if F > K, 0 otherwise
        assert _survival_prob(11.0, 10.0, 1.0, 1e-20) == 1.0
        assert _survival_prob(9.0, 10.0, 1.0, 1e-20) == 0.0


# -- _implied_vol_bisect ------------------------------------------------------

class TestImpliedVolBisect:
    def test_roundtrip_atm(self):
        """Bisection should recover the vol used to generate the price."""
        forward, tau, true_vol = 10.67, 2.0 / 365.0, 0.18
        strike = 10.67  # ATM
        market_prob = _survival_prob(forward, strike, tau, true_vol)
        recovered = _implied_vol_bisect(forward, strike, tau, market_prob)
        assert recovered is not None
        assert abs(recovered - true_vol) < 0.005

    def test_roundtrip_near_atm_itm(self):
        forward, tau, true_vol = 10.67, 5.0 / 365.0, 0.20
        strike = 10.60  # slightly ITM
        market_prob = _survival_prob(forward, strike, tau, true_vol)
        recovered = _implied_vol_bisect(forward, strike, tau, market_prob)
        assert recovered is not None
        assert abs(recovered - true_vol) < 0.005

    def test_roundtrip_near_atm_otm(self):
        forward, tau, true_vol = 10.67, 5.0 / 365.0, 0.20
        strike = 10.75  # slightly OTM
        market_prob = _survival_prob(forward, strike, tau, true_vol)
        recovered = _implied_vol_bisect(forward, strike, tau, market_prob)
        assert recovered is not None
        assert abs(recovered - true_vol) < 0.005

    def test_extreme_prob_returns_none(self):
        # Very extreme probabilities -> None
        assert _implied_vol_bisect(10.0, 10.0, 0.01, 0.001) is None
        assert _implied_vol_bisect(10.0, 10.0, 0.01, 0.999) is None

    def test_invalid_inputs_return_none(self):
        assert _implied_vol_bisect(0.0, 10.0, 0.01, 0.5) is None
        assert _implied_vol_bisect(10.0, 10.0, 0.0, 0.5) is None
        assert _implied_vol_bisect(10.0, 0.0, 0.01, 0.5) is None


# -- calibrate_vol -------------------------------------------------------------

class TestCalibrateVol:
    def test_recovers_known_vol(self):
        """Calibration should recover the vol used to generate prices."""
        forward = 10.67
        tau = 3.0 / 365.0
        true_vol = 0.20
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        calibrated = calibrate_vol(forward, mids, tau)
        assert abs(calibrated - true_vol) < 0.01

    def test_different_vols(self):
        """Calibration produces different vols for different market prices."""
        forward = 10.67
        tau = 5.0 / 365.0
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]

        mids_low = _generate_market_mids(forward, 0.12, tau, strikes)
        mids_high = _generate_market_mids(forward, 0.25, tau, strikes)

        vol_low = calibrate_vol(forward, mids_low, tau)
        vol_high = calibrate_vol(forward, mids_high, tau)

        assert vol_low < vol_high
        assert abs(vol_low - 0.12) < 0.01
        assert abs(vol_high - 0.25) < 0.01

    def test_fallback_too_few_strikes(self):
        """Should fall back when < 3 near-ATM strikes."""
        forward = 10.67
        tau = 3.0 / 365.0
        # Only 2 strikes near ATM
        mids = [(10.67, 0.50), (10.70, 0.42)]
        result = calibrate_vol(forward, mids, tau, fallback=0.15)
        assert result == 0.15

    def test_fallback_no_strikes(self):
        result = calibrate_vol(10.67, [], 3.0 / 365.0, fallback=0.15)
        assert result == 0.15

    def test_fallback_far_from_atm(self):
        """Strikes far from forward should not be used."""
        forward = 10.67
        tau = 3.0 / 365.0
        # All strikes > 10c from forward
        mids = [(10.20, 0.95), (10.30, 0.90), (10.40, 0.85), (11.00, 0.15)]
        result = calibrate_vol(forward, mids, tau, fallback=0.15)
        assert result == 0.15

    def test_fallback_invalid_forward(self):
        result = calibrate_vol(0.0, [(10.67, 0.50)], 0.01, fallback=0.15)
        assert result == 0.15

    def test_fallback_invalid_tau(self):
        result = calibrate_vol(10.67, [(10.67, 0.50)], 0.0, fallback=0.15)
        assert result == 0.15

    def test_soybean_typical_range(self):
        """Calibrated vol for soybeans should be in typical 12-25% range."""
        forward = 10.67
        tau = 2.0 / 365.0
        true_vol = 0.18  # typical nearby soybean vol
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        calibrated = calibrate_vol(forward, mids, tau)
        assert 0.12 <= calibrated <= 0.25

    def test_custom_fallback(self):
        result = calibrate_vol(10.67, [], 3.0 / 365.0, fallback=0.22)
        assert result == 0.22


# -- extract_strike_mids_from_orderbooks ---------------------------------------

class TestExtractStrikeMids:
    def test_basic_extraction(self):
        strikes = [10.60, 10.67, 10.73]
        tickers = {10.60: "T-A", 10.67: "T-B", 10.73: "T-C"}
        orderbooks = {
            "T-A": {"best_bid": 60, "best_ask": 65},
            "T-B": {"best_bid": 48, "best_ask": 52},
            "T-C": {"best_bid": 35, "best_ask": 40},
        }

        result = extract_strike_mids_from_orderbooks(strikes, tickers, orderbooks)
        assert len(result) == 3
        assert result[0] == (10.60, 0.625)   # (60+65)/200
        assert result[1] == (10.67, 0.50)    # (48+52)/200
        assert result[2] == (10.73, 0.375)   # (35+40)/200

    def test_skips_illiquid(self):
        strikes = [10.60, 10.67]
        tickers = {10.60: "T-A", 10.67: "T-B"}
        orderbooks = {
            "T-A": {"best_bid": 0, "best_ask": 100},  # no liquidity
            "T-B": {"best_bid": 48, "best_ask": 52},
        }
        result = extract_strike_mids_from_orderbooks(strikes, tickers, orderbooks)
        assert len(result) == 1
        assert result[0][0] == 10.67

    def test_skips_crossed_book(self):
        strikes = [10.67]
        tickers = {10.67: "T-A"}
        orderbooks = {"T-A": {"best_bid": 55, "best_ask": 50}}
        result = extract_strike_mids_from_orderbooks(strikes, tickers, orderbooks)
        assert len(result) == 0

    def test_missing_ticker(self):
        strikes = [10.60, 10.67]
        tickers = {10.67: "T-B"}  # 10.60 has no ticker
        orderbooks = {"T-B": {"best_bid": 48, "best_ask": 52}}
        result = extract_strike_mids_from_orderbooks(strikes, tickers, orderbooks)
        assert len(result) == 1

    def test_empty_inputs(self):
        assert extract_strike_mids_from_orderbooks([], {}, {}) == []
