"""Tests for engine.seasonal_vol and seasonal integration in implied_vol."""

from __future__ import annotations

import pytest

from engine.seasonal_vol import (
    clamp_vol,
    get_seasonal_vol_bounds,
    get_seasonal_vol_midpoint,
)
from engine.implied_vol import _survival_prob, calibrate_vol


# -- Helpers ------------------------------------------------------------------

def _generate_market_mids(
    forward: float,
    sigma: float,
    tau: float,
    strikes: list[float],
) -> list[tuple[float, float]]:
    """Generate synthetic market mid-prices from a known vol."""
    return [(k, _survival_prob(forward, k, tau, sigma)) for k in strikes]


# -- get_seasonal_vol_bounds --------------------------------------------------

class TestGetSeasonalVolBounds:
    def test_all_months_valid(self):
        for m in range(1, 13):
            floor, ceiling = get_seasonal_vol_bounds(m)
            assert 0.0 < floor < ceiling < 1.0

    def test_summer_higher_than_winter(self):
        """Jun-Aug should have higher bounds than Nov-Dec."""
        for summer in (6, 7, 8):
            s_floor, s_ceil = get_seasonal_vol_bounds(summer)
            for winter in (11, 12):
                w_floor, w_ceil = get_seasonal_vol_bounds(winter)
                assert s_floor > w_floor, f"month {summer} floor should exceed month {winter}"
                assert s_ceil > w_ceil, f"month {summer} ceiling should exceed month {winter}"

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            get_seasonal_vol_bounds(0)
        with pytest.raises(ValueError):
            get_seasonal_vol_bounds(13)
        with pytest.raises(ValueError):
            get_seasonal_vol_bounds(-1)

    def test_specific_summer_bounds(self):
        floor, ceiling = get_seasonal_vol_bounds(7)  # July peak
        assert floor == pytest.approx(0.20)
        assert ceiling == pytest.approx(0.30)

    def test_specific_winter_bounds(self):
        floor, ceiling = get_seasonal_vol_bounds(11)
        assert floor == pytest.approx(0.12)
        assert ceiling == pytest.approx(0.16)


# -- get_seasonal_vol_midpoint ------------------------------------------------

class TestGetSeasonalVolMidpoint:
    def test_midpoint_between_bounds(self):
        for m in range(1, 13):
            floor, ceiling = get_seasonal_vol_bounds(m)
            mid = get_seasonal_vol_midpoint(m)
            assert mid == pytest.approx((floor + ceiling) / 2.0)

    def test_summer_midpoint_higher(self):
        july_mid = get_seasonal_vol_midpoint(7)
        dec_mid = get_seasonal_vol_midpoint(12)
        assert july_mid > dec_mid

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            get_seasonal_vol_midpoint(0)


# -- clamp_vol ----------------------------------------------------------------

class TestClampVol:
    def test_within_bounds_unchanged(self):
        assert clamp_vol(0.25, 7) == 0.25  # July: [0.20, 0.30]

    def test_below_floor_clamped(self):
        assert clamp_vol(0.10, 7) == pytest.approx(0.20)

    def test_above_ceiling_clamped(self):
        assert clamp_vol(0.40, 7) == pytest.approx(0.30)

    def test_at_floor_unchanged(self):
        assert clamp_vol(0.20, 7) == pytest.approx(0.20)

    def test_at_ceiling_unchanged(self):
        assert clamp_vol(0.30, 7) == pytest.approx(0.30)

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            clamp_vol(0.15, 0)


# -- calibrate_vol with seasonal integration ---------------------------------

class TestCalibrateVolSeasonal:
    """Tests for seasonal integration in calibrate_vol."""

    def test_fallback_uses_seasonal_midpoint(self):
        """When calibration fails with month set, fallback is seasonal midpoint."""
        # No strikes -> fallback
        result = calibrate_vol(10.67, [], 3.0 / 365.0, month=7)
        expected = get_seasonal_vol_midpoint(7)  # 0.25
        assert result == pytest.approx(expected)

    def test_fallback_without_month_uses_default(self):
        """Without month, fallback is the flat default."""
        result = calibrate_vol(10.67, [], 3.0 / 365.0, fallback=0.15)
        assert result == 0.15

    def test_calibrated_vol_clamped_to_floor(self):
        """If calibrated vol < seasonal floor, use floor."""
        forward = 10.67
        tau = 5.0 / 365.0
        true_vol = 0.08  # very low — below any seasonal floor
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        # Month=11 has floor=0.12 — but 0.08 is below _VOL_MIN=0.05? No, 0.08>0.05.
        # Actually 0.08 is within [_VOL_MIN, _VOL_MAX] but below Nov floor of 0.12
        result = calibrate_vol(forward, mids, tau, month=11)
        floor, _ = get_seasonal_vol_bounds(11)
        assert result == pytest.approx(floor, abs=0.005)

    def test_calibrated_vol_clamped_to_ceiling(self):
        """If calibrated vol > seasonal ceiling, use ceiling."""
        forward = 10.67
        tau = 5.0 / 365.0
        true_vol = 0.35  # above Nov ceiling of 0.16
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        result = calibrate_vol(forward, mids, tau, month=11)
        _, ceiling = get_seasonal_vol_bounds(11)
        assert result == pytest.approx(ceiling, abs=0.005)

    def test_calibrated_vol_within_bounds_unchanged(self):
        """Vol within seasonal bounds should pass through unclamped."""
        forward = 10.67
        tau = 5.0 / 365.0
        true_vol = 0.25  # within July [0.20, 0.30]
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        result = calibrate_vol(forward, mids, tau, month=7)
        assert abs(result - true_vol) < 0.01

    def test_backward_compat_no_month(self):
        """Without month param, behavior is unchanged from before."""
        forward = 10.67
        tau = 5.0 / 365.0
        true_vol = 0.20
        strikes = [10.57, 10.60, 10.63, 10.67, 10.70, 10.73, 10.77]
        mids = _generate_market_mids(forward, true_vol, tau, strikes)

        result = calibrate_vol(forward, mids, tau)
        assert abs(result - true_vol) < 0.01

    def test_invalid_inputs_use_seasonal_fallback(self):
        """Invalid forward/tau with month should use seasonal midpoint."""
        result = calibrate_vol(0.0, [], 0.01, month=6)
        assert result == pytest.approx(get_seasonal_vol_midpoint(6))

        result = calibrate_vol(10.67, [], 0.0, month=6)
        assert result == pytest.approx(get_seasonal_vol_midpoint(6))
