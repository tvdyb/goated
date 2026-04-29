"""Tests for WASDE parser and density adjuster.

Covers:
- JSON parsing of WASDE data
- Surprise computation (actual vs consensus/prior)
- Density mean-shift from surprise
- Exponential decay of adjustment
- BucketPrices mean-shift application
- Historical data parsing
- Error handling (missing fields, invalid data)
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pytest

from engine.rnd.bucket_integrator import BucketPrices
from engine.wasde_density import (
    WASDEAdjustment,
    WASDEDensityConfig,
    WASDEDensityError,
    apply_wasde_shift,
    compute_mean_shift,
    create_adjustment,
)
from feeds.usda.wasde_parser import (
    WASDEConsensus,
    WASDEParseError,
    WASDEReport,
    WASDESurprise,
    compute_surprise,
    get_historical_reports,
    get_prior_report,
    parse_wasde_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_wasde_json() -> dict:
    return {
        "report_date": "2026-04-09",
        "marketing_year": "2025/26",
        "soybeans": {
            "ending_stocks": 350,
            "production": 4366,
            "exports": 1875,
            "total_supply": 4766,
            "total_use": 4416,
        },
    }


@pytest.fixture
def prior_wasde_json() -> dict:
    return {
        "report_date": "2026-03-10",
        "marketing_year": "2025/26",
        "soybeans": {
            "ending_stocks": 375,
            "production": 4366,
            "exports": 1850,
            "total_supply": 4766,
            "total_use": 4391,
        },
    }


@pytest.fixture
def sample_report(sample_wasde_json: dict) -> WASDEReport:
    return parse_wasde_json(sample_wasde_json)


@pytest.fixture
def prior_report(prior_wasde_json: dict) -> WASDEReport:
    return parse_wasde_json(prior_wasde_json)


@pytest.fixture
def sample_bucket_prices() -> BucketPrices:
    """Create a simple BucketPrices for testing density shifts."""
    strikes = np.array([9.50, 10.00, 10.50, 11.00, 11.50], dtype=np.float64)
    survival = np.array([0.95, 0.70, 0.40, 0.15, 0.03], dtype=np.float64)
    n_buckets = len(strikes) + 1
    bucket_yes = np.zeros(n_buckets, dtype=np.float64)
    bucket_yes[0] = 1.0 - survival[0]
    for i in range(1, len(survival)):
        bucket_yes[i] = survival[i - 1] - survival[i]
    bucket_yes[-1] = survival[-1]
    return BucketPrices(
        kalshi_strikes=strikes,
        survival=survival,
        bucket_yes=bucket_yes,
        bucket_sum=float(bucket_yes.sum()),
        n_buckets=n_buckets,
    )


# ---------------------------------------------------------------------------
# WASDE Parser Tests
# ---------------------------------------------------------------------------


class TestParseWasdeJson:
    def test_basic_parse(self, sample_wasde_json: dict) -> None:
        report = parse_wasde_json(sample_wasde_json)
        assert report.ending_stocks == 350
        assert report.production == 4366
        assert report.exports == 1875
        assert report.marketing_year == "2025/26"
        assert report.report_date.year == 2026
        assert report.report_date.month == 4

    def test_missing_report_date(self) -> None:
        soy = {"ending_stocks": 350, "production": 4366, "exports": 1875}
        data = {"marketing_year": "2025/26", "soybeans": soy}
        with pytest.raises(WASDEParseError, match="Missing report_date"):
            parse_wasde_json(data)

    def test_missing_marketing_year(self) -> None:
        soy = {"ending_stocks": 350, "production": 4366, "exports": 1875}
        data = {"report_date": "2026-04-09", "soybeans": soy}
        with pytest.raises(WASDEParseError, match="Missing marketing_year"):
            parse_wasde_json(data)

    def test_missing_commodity(self) -> None:
        data = {"report_date": "2026-04-09", "marketing_year": "2025/26", "corn": {"ending_stocks": 100}}
        with pytest.raises(WASDEParseError, match="No soybeans data"):
            parse_wasde_json(data)

    def test_missing_required_field(self) -> None:
        data = {"report_date": "2026-04-09", "marketing_year": "2025/26", "soybeans": {"ending_stocks": 350}}
        with pytest.raises(WASDEParseError, match="Missing production"):
            parse_wasde_json(data)

    def test_invalid_date_format(self) -> None:
        soy = {"ending_stocks": 350, "production": 4366, "exports": 1875}
        data = {
            "report_date": "04/09/2026",
            "marketing_year": "2025/26",
            "soybeans": soy,
        }
        with pytest.raises(WASDEParseError, match="Invalid report_date"):
            parse_wasde_json(data)

    def test_custom_commodity(self) -> None:
        data = {
            "report_date": "2026-04-09",
            "marketing_year": "2025/26",
            "corn": {"ending_stocks": 1500, "production": 15000, "exports": 2400},
        }
        report = parse_wasde_json(data, commodity="corn")
        assert report.ending_stocks == 1500

    def test_optional_fields_default_zero(self) -> None:
        data = {
            "report_date": "2026-04-09",
            "marketing_year": "2025/26",
            "soybeans": {"ending_stocks": 350, "production": 4366, "exports": 1875},
        }
        report = parse_wasde_json(data)
        assert report.total_supply == 0
        assert report.total_use == 0


# ---------------------------------------------------------------------------
# Surprise Computation Tests
# ---------------------------------------------------------------------------


class TestComputeSurprise:
    def test_surprise_vs_prior(self, sample_report: WASDEReport, prior_report: WASDEReport) -> None:
        surprise = compute_surprise(sample_report, prior=prior_report)
        # ending_stocks: 350 - 375 = -25 (tighter than prior)
        assert surprise.ending_stocks_delta == pytest.approx(-25.0)
        # production: 4366 - 4366 = 0
        assert surprise.production_delta == pytest.approx(0.0)
        # exports: 1875 - 1850 = 25 (more exports)
        assert surprise.exports_delta == pytest.approx(25.0)

    def test_surprise_vs_consensus(self, sample_report: WASDEReport) -> None:
        consensus = WASDEConsensus(ending_stocks=360, production=4366, exports=1875)
        surprise = compute_surprise(sample_report, consensus=consensus)
        # 350 - 360 = -10
        assert surprise.ending_stocks_delta == pytest.approx(-10.0)

    def test_surprise_consensus_report(self, sample_report: WASDEReport, prior_report: WASDEReport) -> None:
        surprise = compute_surprise(sample_report, consensus=prior_report)
        assert surprise.ending_stocks_delta == pytest.approx(-25.0)

    def test_surprise_no_baseline_raises(self, sample_report: WASDEReport) -> None:
        with pytest.raises(WASDEParseError, match="requires either consensus or prior"):
            compute_surprise(sample_report)

    def test_surprise_partial_consensus(self, sample_report: WASDEReport) -> None:
        # Only ending_stocks set in consensus; others default to actual
        consensus = WASDEConsensus(ending_stocks=400)
        surprise = compute_surprise(sample_report, consensus=consensus)
        assert surprise.ending_stocks_delta == pytest.approx(-50.0)
        assert surprise.production_delta == pytest.approx(0.0)  # None -> uses actual
        assert surprise.exports_delta == pytest.approx(0.0)  # None -> uses actual


# ---------------------------------------------------------------------------
# Mean Shift Tests
# ---------------------------------------------------------------------------


class TestComputeMeanShift:
    def test_bearish_surprise(self) -> None:
        """Positive ending_stocks_delta (more stocks than expected) = bearish = negative shift."""
        surprise = WASDESurprise(
            ending_stocks_delta=10.0,  # 10M bu more than expected
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        shift = compute_mean_shift(surprise)
        # -10 * 18 = -180, but capped at -100
        assert shift == pytest.approx(-100.0)  # capped

    def test_bullish_surprise(self) -> None:
        """Negative ending_stocks_delta (fewer stocks) = bullish = positive shift."""
        surprise = WASDESurprise(
            ending_stocks_delta=-5.0,  # 5M bu fewer than expected
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        shift = compute_mean_shift(surprise)
        # -(-5) * 18 = 90c
        assert shift == pytest.approx(90.0)

    def test_no_surprise(self) -> None:
        surprise = WASDESurprise(
            ending_stocks_delta=0.0,
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        shift = compute_mean_shift(surprise)
        assert shift == pytest.approx(0.0)

    def test_custom_sensitivity(self) -> None:
        surprise = WASDESurprise(
            ending_stocks_delta=-2.0,
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        config = WASDEDensityConfig(sensitivity_cents_per_mbu=25.0)
        shift = compute_mean_shift(surprise, config)
        assert shift == pytest.approx(50.0)

    def test_max_shift_cap(self) -> None:
        surprise = WASDESurprise(
            ending_stocks_delta=-20.0,  # huge surprise
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        config = WASDEDensityConfig(max_shift_cents=50.0)
        shift = compute_mean_shift(surprise, config)
        assert shift == pytest.approx(50.0)

    def test_production_signal(self) -> None:
        surprise = WASDESurprise(
            ending_stocks_delta=0.0,
            production_delta=-10.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        config = WASDEDensityConfig(
            use_production_signal=True,
            production_weight=0.3,
        )
        shift = compute_mean_shift(surprise, config)
        # -(-10) * 18 * 0.3 = 54c
        assert shift == pytest.approx(54.0)


# ---------------------------------------------------------------------------
# Adjustment Decay Tests
# ---------------------------------------------------------------------------


class TestWASDEAdjustment:
    def test_no_decay_at_release(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=90.0,
            release_timestamp=1000.0,
            decay_half_life_s=6 * 3600,
            surprise=_dummy_surprise(),
        )
        assert adj.current_shift_cents(1000.0) == pytest.approx(90.0)

    def test_half_life_decay(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=90.0,
            release_timestamp=1000.0,
            decay_half_life_s=6 * 3600,
            surprise=_dummy_surprise(),
        )
        # After 6 hours: shift should be ~45c
        t_6h = 1000.0 + 6 * 3600
        assert adj.current_shift_cents(t_6h) == pytest.approx(45.0)

    def test_two_half_lives(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=100.0,
            release_timestamp=0.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        # After 2 half-lives: 100 * 0.25 = 25c
        assert adj.current_shift_cents(7200.0) == pytest.approx(25.0)

    def test_24h_decay(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=90.0,
            release_timestamp=0.0,
            decay_half_life_s=6 * 3600,
            surprise=_dummy_surprise(),
        )
        # After 24h = 4 half-lives: 90 * (0.5^4) = 5.625c
        assert adj.current_shift_cents(24 * 3600) == pytest.approx(5.625)

    def test_expired(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=10.0,
            release_timestamp=0.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        # After many half-lives, should be expired
        assert adj.is_expired(100000.0, threshold=0.5)

    def test_not_expired(self) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=90.0,
            release_timestamp=0.0,
            decay_half_life_s=6 * 3600,
            surprise=_dummy_surprise(),
        )
        assert not adj.is_expired(0.0, threshold=0.5)

    def test_negative_elapsed_clamped(self) -> None:
        """Future timestamp should not cause issues."""
        adj = WASDEAdjustment(
            mean_shift_cents=50.0,
            release_timestamp=1000.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        # now < release: elapsed clamped to 0
        assert adj.current_shift_cents(500.0) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# create_adjustment Tests
# ---------------------------------------------------------------------------


class TestCreateAdjustment:
    def test_creates_from_surprise(self) -> None:
        surprise = WASDESurprise(
            ending_stocks_delta=-5.0,
            production_delta=0.0,
            exports_delta=0.0,
            report=_dummy_report(),
            consensus=_dummy_report(),
        )
        adj = create_adjustment(surprise, release_timestamp=1000.0)
        assert adj.mean_shift_cents == pytest.approx(90.0)
        assert adj.release_timestamp == 1000.0


# ---------------------------------------------------------------------------
# apply_wasde_shift Tests
# ---------------------------------------------------------------------------


class TestApplyWasdeShift:
    # Use 30-day tau so Black-76 density spans the strike range
    _TAU = 30.0 / 365.0
    _SIGMA = 0.15
    _FWD = 10.50

    def test_bullish_shift_moves_density_right(
        self, sample_bucket_prices: BucketPrices
    ) -> None:
        """A bullish (positive) shift should increase survival at each strike."""
        adj = WASDEAdjustment(
            mean_shift_cents=50.0,
            release_timestamp=0.0,
            decay_half_life_s=6 * 3600,
            surprise=_dummy_surprise(),
        )
        original = apply_wasde_shift(
            sample_bucket_prices,
            WASDEAdjustment(mean_shift_cents=0.01, release_timestamp=0.0,
                            decay_half_life_s=6 * 3600, surprise=_dummy_surprise()),
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        shifted = apply_wasde_shift(
            sample_bucket_prices,
            adj,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        # Survival at each strike should be higher (more mass above)
        assert np.all(shifted.survival >= original.survival - 1e-10)
        assert shifted.bucket_sum == pytest.approx(1.0, abs=0.01)

    def test_bearish_shift_lowers_survival(
        self, sample_bucket_prices: BucketPrices
    ) -> None:
        adj_base = WASDEAdjustment(
            mean_shift_cents=0.01, release_timestamp=0.0,
            decay_half_life_s=6 * 3600, surprise=_dummy_surprise(),
        )
        adj_bear = WASDEAdjustment(
            mean_shift_cents=-50.0, release_timestamp=0.0,
            decay_half_life_s=6 * 3600, surprise=_dummy_surprise(),
        )
        original = apply_wasde_shift(
            sample_bucket_prices, adj_base,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        shifted = apply_wasde_shift(
            sample_bucket_prices, adj_bear,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        # Survival at each strike should be lower (less mass above)
        assert np.all(shifted.survival <= original.survival + 1e-10)

    def test_zero_shift_returns_original(
        self, sample_bucket_prices: BucketPrices
    ) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=0.0,
            release_timestamp=0.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        result = apply_wasde_shift(
            sample_bucket_prices, adj,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        # Should return original (no change)
        np.testing.assert_array_equal(
            result.bucket_yes, sample_bucket_prices.bucket_yes
        )

    def test_decayed_shift_is_smaller(
        self, sample_bucket_prices: BucketPrices
    ) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=50.0,
            release_timestamp=0.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        # Compute "unshifted" baseline using same Black-76 for fair comparison
        adj_zero = WASDEAdjustment(
            mean_shift_cents=0.01, release_timestamp=0.0,
            decay_half_life_s=3600, surprise=_dummy_surprise(),
        )
        baseline = apply_wasde_shift(
            sample_bucket_prices, adj_zero,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        # At release: full shift
        shifted_0 = apply_wasde_shift(
            sample_bucket_prices, adj,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
        )
        # After 1 half-life: half shift
        shifted_1h = apply_wasde_shift(
            sample_bucket_prices, adj,
            forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=3600.0,
        )
        diff_0 = np.abs(shifted_0.survival - baseline.survival).sum()
        diff_1h = np.abs(shifted_1h.survival - baseline.survival).sum()
        assert diff_1h < diff_0

    def test_negative_forward_raises(self, sample_bucket_prices: BucketPrices) -> None:
        adj = WASDEAdjustment(
            mean_shift_cents=-2000.0,
            release_timestamp=0.0,
            decay_half_life_s=3600,
            surprise=_dummy_surprise(),
        )
        with pytest.raises(WASDEDensityError, match="negative forward"):
            apply_wasde_shift(
                sample_bucket_prices, adj,
                forward=self._FWD, sigma=self._SIGMA, tau=self._TAU, now=0.0,
            )


# ---------------------------------------------------------------------------
# Historical Data Tests
# ---------------------------------------------------------------------------


class TestHistoricalData:
    def test_get_historical_reports(self) -> None:
        reports = get_historical_reports()
        assert len(reports) >= 4
        for r in reports:
            assert r.ending_stocks > 0
            assert r.production > 0
            assert r.exports > 0

    def test_get_prior_report(self) -> None:
        prior = get_prior_report(datetime(2026, 4, 9))
        assert prior is not None
        assert prior.report_date < datetime(2026, 4, 9)

    def test_prior_before_all_returns_none(self) -> None:
        prior = get_prior_report(datetime(2020, 1, 1))
        assert prior is None

    def test_sequential_surprise(self) -> None:
        """Compute surprise between consecutive historical reports."""
        reports = get_historical_reports()
        for i in range(1, len(reports)):
            surprise = compute_surprise(reports[i], prior=reports[i - 1])
            # Deltas should be finite
            assert math.isfinite(surprise.ending_stocks_delta)
            assert math.isfinite(surprise.production_delta)


# ---------------------------------------------------------------------------
# End-to-end: parse -> surprise -> shift -> density
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_historical_to_density(self, sample_bucket_prices: BucketPrices) -> None:
        """Full pipeline: parse historical -> surprise -> adjustment -> density."""
        reports = get_historical_reports()
        # Use last two reports
        prior = reports[-2]
        actual = reports[-1]

        surprise = compute_surprise(actual, prior=prior)
        adj = create_adjustment(surprise, release_timestamp=0.0)

        # If there's a non-zero surprise, the density should shift
        if surprise.ending_stocks_delta != 0:
            shifted = apply_wasde_shift(
                sample_bucket_prices, adj, forward=10.50, sigma=0.15,
                tau=2.0 / 365.0, now=0.0,
            )
            assert shifted.bucket_sum == pytest.approx(1.0, abs=0.01)
            # Should be different from original
            assert not np.allclose(shifted.bucket_yes, sample_bucket_prices.bucket_yes)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_report() -> WASDEReport:
    return WASDEReport(
        report_date=datetime(2026, 4, 9),
        marketing_year="2025/26",
        ending_stocks=350,
        production=4366,
        exports=1875,
        total_supply=4766,
        total_use=4416,
        raw={},
    )


def _dummy_surprise() -> WASDESurprise:
    return WASDESurprise(
        ending_stocks_delta=-5.0,
        production_delta=0.0,
        exports_delta=0.0,
        report=_dummy_report(),
        consensus=_dummy_report(),
    )
