"""Tests for weather-driven distribution skew.

Success criteria (from Phase T-70):
  1. Weather skew activates during Jun-Aug and Jan-Feb only.
  2. A hot/dry forecast shifts density upward and widens.
  3. A cool/wet forecast narrows density.
  4. Outside growing season: no effect.
"""

from __future__ import annotations

import time
from datetime import date

import numpy as np
import pytest

from engine.weather_skew import (
    GrowingSeason,
    SkewParams,
    WeatherSkewResult,
    apply_weather_skew,
    compute_weather_skew,
    detect_growing_season,
)
from feeds.weather.gefs_client import (
    OutlookPeriod,
    WeatherOutlook,
    create_outlook_from_manual,
    normal_precip_in,
    normal_temp_f,
)
from models.gbm import gbm_prob_above

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _outlook(temp_f: float = 0.0, precip_pct: float = 0.0) -> WeatherOutlook:
    return WeatherOutlook(
        temp_anomaly_f=temp_f,
        precip_anomaly_pct=precip_pct,
        outlook_period=OutlookPeriod.DAY_6_10,
        fetched_at_ns=time.time_ns(),
    )


# ---------------------------------------------------------------------------
# Season detection
# ---------------------------------------------------------------------------


class TestGrowingSeasonDetection:
    @pytest.mark.parametrize("month", [6, 7, 8])
    def test_us_pod_fill(self, month: int) -> None:
        d = date(2026, month, 15)
        assert detect_growing_season(d) == GrowingSeason.US_POD_FILL

    @pytest.mark.parametrize("month", [1, 2])
    def test_sa_pod_fill(self, month: int) -> None:
        d = date(2026, month, 15)
        assert detect_growing_season(d) == GrowingSeason.SA_POD_FILL

    @pytest.mark.parametrize("month", [3, 4, 5, 9, 10, 11, 12])
    def test_off_season(self, month: int) -> None:
        d = date(2026, month, 15)
        assert detect_growing_season(d) == GrowingSeason.OFF_SEASON


# ---------------------------------------------------------------------------
# Off-season: no effect
# ---------------------------------------------------------------------------


class TestOffSeason:
    @pytest.mark.parametrize("month", [3, 4, 5, 9, 10, 11, 12])
    def test_off_season_returns_zero(self, month: int) -> None:
        outlook = _outlook(temp_f=5.0, precip_pct=-30.0)
        result = compute_weather_skew(outlook, as_of=date(2026, month, 15))
        assert result.mean_shift_cents == 0.0
        assert result.vol_adjustment_pct == 0.0

    def test_off_season_extreme_weather_still_zero(self) -> None:
        outlook = _outlook(temp_f=10.0, precip_pct=-60.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 10, 1))
        assert result == WeatherSkewResult(0.0, 0.0)


# ---------------------------------------------------------------------------
# Hot/dry → price UP + vol UP (tail widens)
# ---------------------------------------------------------------------------


class TestHotDry:
    def test_hot_dry_us_pod_fill_shifts_up(self) -> None:
        outlook = _outlook(temp_f=5.0, precip_pct=-30.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents > 0.0, "hot/dry should shift price UP"
        assert result.vol_adjustment_pct > 0.0, "hot/dry should widen tails"

    def test_extreme_drought_2012_analog(self) -> None:
        """2012-like: +8F temp, -60% precip during July pod-fill."""
        outlook = _outlook(temp_f=8.0, precip_pct=-60.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents > 50.0, "extreme drought -> large upward shift"
        assert result.vol_adjustment_pct > 0.20, "extreme drought -> big vol expansion"

    def test_moderate_heat_june(self) -> None:
        outlook = _outlook(temp_f=3.0, precip_pct=-10.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 6, 1))
        assert result.mean_shift_cents > 0.0
        assert result.vol_adjustment_pct > 0.0

    def test_hot_dry_sa_pod_fill_dampened(self) -> None:
        """S. America pod-fill should have dampened effect."""
        outlook = _outlook(temp_f=5.0, precip_pct=-30.0)
        us_result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        sa_result = compute_weather_skew(outlook, as_of=date(2026, 1, 15))
        # SA dampened by 0.5x
        assert sa_result.mean_shift_cents == pytest.approx(
            us_result.mean_shift_cents * 0.5
        )
        assert sa_result.vol_adjustment_pct == pytest.approx(
            us_result.vol_adjustment_pct * 0.5
        )


# ---------------------------------------------------------------------------
# Cool/wet → price DOWN + vol DOWN (tails narrow)
# ---------------------------------------------------------------------------


class TestCoolWet:
    def test_cool_wet_us_pod_fill_shifts_down(self) -> None:
        outlook = _outlook(temp_f=-3.0, precip_pct=20.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents < 0.0, "cool/wet should shift price DOWN"
        assert result.vol_adjustment_pct < 0.0, "cool/wet should narrow tails"

    def test_ideal_growing_conditions(self) -> None:
        outlook = _outlook(temp_f=-2.0, precip_pct=15.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 8, 1))
        assert result.mean_shift_cents < 0.0
        assert result.vol_adjustment_pct < 0.0


# ---------------------------------------------------------------------------
# Neutral weather → near-zero effect
# ---------------------------------------------------------------------------


class TestNeutral:
    def test_neutral_weather_minimal_effect(self) -> None:
        outlook = _outlook(temp_f=0.0, precip_pct=0.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents == 0.0
        assert result.vol_adjustment_pct == 0.0

    def test_slight_anomaly(self) -> None:
        outlook = _outlook(temp_f=1.0, precip_pct=-5.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        # Small but nonzero
        assert 0.0 < result.mean_shift_cents < 20.0
        assert 0.0 < result.vol_adjustment_pct < 0.10


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


class TestClamping:
    def test_extreme_shift_clamped(self) -> None:
        outlook = _outlook(temp_f=20.0, precip_pct=-100.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents <= 80.0
        assert result.vol_adjustment_pct <= 0.50

    def test_extreme_negative_clamped(self) -> None:
        outlook = _outlook(temp_f=-20.0, precip_pct=100.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        assert result.mean_shift_cents >= -80.0
        assert result.vol_adjustment_pct >= -0.50


# ---------------------------------------------------------------------------
# apply_weather_skew
# ---------------------------------------------------------------------------


class TestApplySkew:
    def test_no_skew_passthrough(self) -> None:
        fwd, sig = apply_weather_skew(1200.0, 0.15, WeatherSkewResult(0.0, 0.0))
        assert fwd == 1200.0
        assert sig == 0.15

    def test_positive_shift(self) -> None:
        fwd, sig = apply_weather_skew(1200.0, 0.15, WeatherSkewResult(25.0, 0.10))
        assert fwd == 1225.0
        assert sig == pytest.approx(0.165)

    def test_negative_shift(self) -> None:
        fwd, sig = apply_weather_skew(1200.0, 0.15, WeatherSkewResult(-15.0, -0.05))
        assert fwd == 1185.0
        assert sig == pytest.approx(0.1425)

    def test_reject_nonpositive_forward(self) -> None:
        with pytest.raises(ValueError, match="non-positive forward"):
            apply_weather_skew(10.0, 0.15, WeatherSkewResult(-20.0, 0.0))

    def test_reject_nonpositive_sigma(self) -> None:
        with pytest.raises(ValueError, match="non-positive vol"):
            apply_weather_skew(1200.0, 0.10, WeatherSkewResult(0.0, -1.5))

    def test_reject_bad_forward(self) -> None:
        with pytest.raises(ValueError):
            apply_weather_skew(-1.0, 0.15, WeatherSkewResult(0.0, 0.0))

    def test_reject_bad_sigma(self) -> None:
        with pytest.raises(ValueError):
            apply_weather_skew(1200.0, 0.0, WeatherSkewResult(0.0, 0.0))


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_reject_nan_temp(self) -> None:
        outlook = _outlook(temp_f=float("nan"), precip_pct=0.0)
        with pytest.raises(ValueError, match="temp_anomaly_f"):
            compute_weather_skew(outlook, as_of=date(2026, 7, 15))

    def test_reject_inf_precip(self) -> None:
        outlook = _outlook(temp_f=0.0, precip_pct=float("inf"))
        with pytest.raises(ValueError, match="precip_anomaly_pct"):
            compute_weather_skew(outlook, as_of=date(2026, 7, 15))


# ---------------------------------------------------------------------------
# Custom params
# ---------------------------------------------------------------------------


class TestCustomParams:
    def test_custom_sensitivity(self) -> None:
        params = SkewParams(
            temp_shift_cents_per_f=10.0,  # 2x default
            precip_shift_cents_per_pct=-2.0,  # 2x default
            temp_vol_pct_per_f=0.06,  # 2x default
            precip_vol_pct_per_pct=-0.01,  # 2x default
        )
        outlook = _outlook(temp_f=5.0, precip_pct=-30.0)
        default_result = compute_weather_skew(outlook, as_of=date(2026, 7, 15))
        custom_result = compute_weather_skew(
            outlook, as_of=date(2026, 7, 15), params=params
        )
        assert custom_result.mean_shift_cents > default_result.mean_shift_cents
        assert custom_result.vol_adjustment_pct > default_result.vol_adjustment_pct


# ---------------------------------------------------------------------------
# Climate normals
# ---------------------------------------------------------------------------


class TestClimateNormals:
    def test_normal_temp_range(self) -> None:
        for m in range(1, 13):
            t = normal_temp_f(m)
            assert 10.0 < t < 90.0, f"Month {m} temp {t}F out of range"

    def test_normal_precip_range(self) -> None:
        for m in range(1, 13):
            p = normal_precip_in(m)
            assert 0.5 < p < 6.0, f"Month {m} precip {p}in out of range"

    def test_invalid_month(self) -> None:
        with pytest.raises(ValueError):
            normal_temp_f(0)
        with pytest.raises(ValueError):
            normal_precip_in(13)

    def test_july_is_hottest(self) -> None:
        july = normal_temp_f(7)
        for m in range(1, 13):
            assert july >= normal_temp_f(m) - 1.0  # July or Aug within 1F


# ---------------------------------------------------------------------------
# Manual outlook creation
# ---------------------------------------------------------------------------


class TestManualOutlook:
    def test_create(self) -> None:
        o = create_outlook_from_manual(3.0, -15.0)
        assert o.temp_anomaly_f == 3.0
        assert o.precip_anomaly_pct == -15.0
        assert o.outlook_period == OutlookPeriod.DAY_6_10

    def test_reject_nan(self) -> None:
        with pytest.raises(ValueError):
            create_outlook_from_manual(float("nan"), 0.0)

    def test_reject_inf(self) -> None:
        with pytest.raises(ValueError):
            create_outlook_from_manual(0.0, float("inf"))


# ---------------------------------------------------------------------------
# Integration: weather skew applied to GBM density
# ---------------------------------------------------------------------------


class TestDensityIntegration:
    """Verify that weather skew shifts the effective density."""

    def test_hot_dry_shifts_density_right(self) -> None:
        """With hot/dry weather, the adjusted forward is higher,
        so more probability mass is at higher prices."""
        strikes = np.linspace(1100, 1300, 20)
        forward = 1200.0
        sigma = 0.15
        tau = 30.0 / 365.0

        # Base density
        base_probs = gbm_prob_above(forward, strikes, tau, sigma)

        # Hot/dry skew
        skew = WeatherSkewResult(mean_shift_cents=30.0, vol_adjustment_pct=0.15)
        adj_fwd, adj_sig = apply_weather_skew(forward, sigma, skew)
        skewed_probs = gbm_prob_above(adj_fwd, strikes, tau, adj_sig)

        # Higher strikes should have higher survival probability (density shifted right)
        high_strike_idx = -5  # near top of grid
        assert skewed_probs[high_strike_idx] > base_probs[high_strike_idx], (
            "Hot/dry weather should increase P(S_T > K) at high strikes"
        )

    def test_cool_wet_narrows_density(self) -> None:
        """With cool/wet weather, lower vol narrows the distribution."""
        strikes = np.linspace(1100, 1300, 20)
        forward = 1200.0
        sigma = 0.15
        tau = 30.0 / 365.0

        base_probs = gbm_prob_above(forward, strikes, tau, sigma)

        # Cool/wet skew
        skew = WeatherSkewResult(mean_shift_cents=-10.0, vol_adjustment_pct=-0.10)
        adj_fwd, adj_sig = apply_weather_skew(forward, sigma, skew)
        skewed_probs = gbm_prob_above(adj_fwd, strikes, tau, adj_sig)

        # At far tails, narrower vol means LESS probability
        assert skewed_probs[-1] < base_probs[-1], (
            "Cool/wet should reduce upper tail probability"
        )

    def test_off_season_density_unchanged(self) -> None:
        """Off-season weather should not change density at all."""
        forward = 1200.0
        sigma = 0.15

        outlook = _outlook(temp_f=8.0, precip_pct=-50.0)
        result = compute_weather_skew(outlook, as_of=date(2026, 10, 15))

        adj_fwd, adj_sig = apply_weather_skew(forward, sigma, result)
        assert adj_fwd == forward
        assert adj_sig == sigma
