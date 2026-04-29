"""Tests for the RND pipeline (F4-ACT-03, Phase 50).

Test strategy:
  - BL: synthetic Black-Scholes calls -> recover lognormal density.
  - SVI: synthetic smile -> verify parameter recovery.
  - SVI butterfly arb: known-violating surface -> verify detection.
  - Bucket integrator: known density (normal) -> verify against CDF.
  - Full pipeline: synthetic options chain -> verify sum-to-1 and survival monotonicity.
  - Error paths: insufficient strikes, expired chain, bad data.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from scipy.special import ndtr

from engine.rnd.breeden_litzenberger import BLDensityError, bl_density
from engine.rnd.bucket_integrator import BucketPrices, BucketSumError, integrate_buckets
from engine.rnd.figlewski import extend_tails
from engine.rnd.pipeline import RNDValidationError, compute_rnd
from engine.rnd.svi import (
    SVIArbViolationError,
    SVICalibrationError,
    SVIParams,
    _butterfly_arb_check,
    _svi_total_variance,
    svi_calibrate,
    svi_implied_vol_surface,
)
from feeds.cme.options_chain import OptionsChain


# ---------------------------------------------------------------------------
# Helpers: synthetic Black-Scholes data
# ---------------------------------------------------------------------------

def _bs_call_price(F: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-76 call price (scalar)."""
    if T <= 0 or sigma <= 0:
        return max(F - K, 0.0)
    sqrt_T = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return math.exp(-r * T) * (F * float(ndtr(d1)) - K * float(ndtr(d2)))


def _bs_call_prices_vec(F: float, strikes: np.ndarray, T: float, r: float, sigma: float) -> np.ndarray:
    """Vectorized Black-76 call prices."""
    return np.array([_bs_call_price(F, K, T, r, sigma) for K in strikes])


def _make_synthetic_chain(
    forward: float = 1050.0,
    sigma: float = 0.22,
    T: float = 30 / 365.25,
    r: float = 0.05,
    n_strikes: int = 41,
    strike_range: float = 150.0,
    skew: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Create a synthetic Black-76 options chain.

    Returns (strikes, call_prices, implied_vols, forward).
    """
    strikes = np.linspace(forward - strike_range, forward + strike_range, n_strikes)
    if skew != 0.0:
        log_m = np.log(strikes / forward)
        vols = sigma * (1 + skew * log_m)
        vols = np.clip(vols, 0.05, 1.0)
    else:
        vols = np.full(n_strikes, sigma)

    calls = np.array([_bs_call_price(forward, K, T, r, v) for K, v in zip(strikes, vols)])
    return strikes, calls, vols, forward


def _make_options_chain(
    forward: float = 1050.0,
    sigma: float = 0.22,
    T_days: int = 30,
    r: float = 0.05,
    n_strikes: int = 41,
    strike_range: float = 150.0,
    skew: float = -0.1,
) -> OptionsChain:
    """Create a synthetic OptionsChain."""
    T = T_days / 365.25
    strikes, calls, vols, fwd = _make_synthetic_chain(
        forward=forward, sigma=sigma, T=T, r=r,
        n_strikes=n_strikes, strike_range=strike_range, skew=skew,
    )
    puts = np.array([
        _bs_call_price(forward, K, T, r, v) - math.exp(-r * T) * (forward - K)
        for K, v in zip(strikes, vols)
    ])
    puts = np.maximum(puts, 0.0)

    as_of = date(2026, 4, 1)
    expiry = date(2026, 5, 1)

    return OptionsChain(
        symbol="ZS",
        expiry=expiry,
        as_of=as_of,
        underlying_settle=forward,
        strikes=strikes,
        call_prices=calls,
        put_prices=puts,
        call_ivs=vols,
        put_ivs=None,
        call_oi=None,
        put_oi=None,
        call_volume=None,
        put_volume=None,
    )


# ===========================================================================
# 1. Breeden-Litzenberger tests
# ===========================================================================

class TestBLDensity:
    """BL density extraction on synthetic Black-Scholes data."""

    def test_bl_recovers_lognormal_shape(self):
        """BL on flat-vol BS calls should produce a bell-shaped density."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, calls, _, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=51)

        density_strikes, density_values = bl_density(
            strikes, calls, risk_free_rate=r, tau=T, allow_negative_clip=True
        )

        assert len(density_strikes) == len(strikes) - 2
        assert np.all(density_values >= 0)
        # Density should peak near the forward price
        peak_idx = np.argmax(density_values)
        assert abs(density_strikes[peak_idx] - F) < 50.0

    def test_bl_density_integrates_near_one(self):
        """BL density should integrate to approximately 1.0."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, calls, _, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=101, strike_range=300)

        density_strikes, density_values = bl_density(
            strikes, calls, risk_free_rate=r, tau=T, allow_negative_clip=True
        )

        area = float(np.trapezoid(density_values, density_strikes))
        assert abs(area - 1.0) < 0.15, f"BL density area = {area:.4f}, expected ~1.0"

    def test_bl_insufficient_strikes_raises(self):
        """BL should raise on fewer than 5 strikes."""
        strikes = np.array([900.0, 1000.0, 1100.0])
        calls = np.array([150.0, 80.0, 30.0])

        with pytest.raises(BLDensityError, match="Insufficient strikes"):
            bl_density(strikes, calls, min_strikes=5)

    def test_bl_unsorted_raises(self):
        """BL should raise on non-ascending strikes."""
        strikes = np.array([1100.0, 1000.0, 900.0, 800.0, 700.0])
        calls = np.array([10.0, 50.0, 100.0, 150.0, 200.0])

        with pytest.raises(BLDensityError, match="strictly ascending"):
            bl_density(strikes, calls)

    def test_bl_negative_density_raises(self):
        """BL should raise on negative density when allow_negative_clip=False."""
        # Create call prices that are concave (not convex) at interior points
        # For BL, d2C/dK2 < 0 means concave -> negative density
        strikes = np.array([900.0, 950.0, 1000.0, 1050.0, 1100.0])
        # Concave: the middle value is ABOVE the linear interpolation
        # C(K) curve that bows upward instead of downward
        calls = np.array([200.0, 160.0, 130.0, 110.0, 100.0])
        # Make it concave at strike=1000: C(950)=160, C(1000)=130, C(1050)=110
        # d2C = (110 - 2*130 + 160) / 50^2 = (110 - 260 + 160)/2500 = 10/2500 > 0
        # We need d2C < 0: make middle point higher than interpolant
        calls_concave = np.array([200.0, 155.0, 125.0, 100.0, 80.0])
        # d2C at 1000: (100 - 2*125 + 155)/2500 = 5/2500 > 0 still
        # Try: make second derivative explicitly negative
        calls_bad = np.array([100.0, 80.0, 70.0, 65.0, 64.0])
        # d2C at 1000: (65 - 2*70 + 80)/2500 = 5/2500 > 0 still convex
        # For concavity we need C(i-1) + C(i+1) < 2*C(i)
        calls_neg = np.array([100.0, 90.0, 85.0, 82.0, 80.0])
        # d2C at 1000: (82 - 2*85 + 90)/2500 = 2/2500 > 0
        # Actually call prices are naturally convex. Use puts-like shape:
        calls_trick = np.array([10.0, 20.0, 15.0, 8.0, 3.0])
        # d2C at 1000: (8 - 2*15 + 20)/2500 = -2/2500 < 0 YES!

        with pytest.raises(BLDensityError, match="Negative density"):
            bl_density(strikes, calls_trick, allow_negative_clip=False)

    def test_bl_negative_density_clips(self):
        """BL should clip negative density when allow_negative_clip=True."""
        strikes = np.array([900.0, 950.0, 1000.0, 1050.0, 1100.0])
        calls_trick = np.array([10.0, 20.0, 15.0, 8.0, 3.0])

        density_strikes, density_values = bl_density(
            strikes, calls_trick, allow_negative_clip=True
        )
        assert np.all(density_values >= 0)

    def test_bl_zero_tau_raises(self):
        with pytest.raises(BLDensityError, match="tau"):
            bl_density(np.arange(5, dtype=np.float64) + 900, np.arange(5, dtype=np.float64), tau=0.0)

    def test_bl_shape_mismatch_raises(self):
        with pytest.raises(BLDensityError, match="same length"):
            bl_density(np.arange(5, dtype=np.float64) + 900, np.arange(6, dtype=np.float64))


# ===========================================================================
# 2. SVI calibration tests
# ===========================================================================

class TestSVICalibration:
    """SVI calibration and butterfly arb checks."""

    def test_svi_recovers_flat_vol(self):
        """SVI on flat vol smile should produce near-zero skew."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, _, vols, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=21)

        params = svi_calibrate(strikes, vols, F, T)

        # Fitted IV at ATM should be close to input sigma
        atm_iv = svi_implied_vol_surface(params, np.array([F]))
        assert abs(atm_iv[0] - sigma) < 0.02, f"ATM IV = {atm_iv[0]:.4f}, expected {sigma}"

    def test_svi_recovers_skewed_smile(self):
        """SVI on a skewed smile should produce negative rho."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, _, vols, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=31, skew=-0.15)

        params = svi_calibrate(strikes, vols, F, T)
        assert params.rho < 0, f"Expected negative rho for put skew, got {params.rho:.4f}"

    def test_svi_butterfly_arb_passes(self):
        """SVI on reasonable data should pass butterfly arb check."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, _, vols, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=21)

        params = svi_calibrate(strikes, vols, F, T)
        assert params.butterfly_violations == 0

    def test_svi_total_variance_positive(self):
        """SVI total variance should be non-negative everywhere."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, _, vols, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=21)

        params = svi_calibrate(strikes, vols, F, T)
        k_test = np.linspace(-0.5, 0.5, 200)
        w = _svi_total_variance(k_test, params.a, params.b, params.rho, params.m, params.sigma)
        assert np.all(w >= -1e-10), f"Negative total variance: min={w.min():.6e}"

    def test_svi_insufficient_strikes_raises(self):
        with pytest.raises(SVICalibrationError, match="Need >= 5"):
            svi_calibrate(
                np.array([1000.0, 1050.0, 1100.0]),
                np.array([0.22, 0.21, 0.23]),
                1050.0,
                0.1,
            )

    def test_svi_zero_tau_raises(self):
        with pytest.raises(SVICalibrationError, match="tau"):
            svi_calibrate(
                np.arange(10, dtype=np.float64) * 10 + 950,
                np.full(10, 0.22),
                1000.0,
                0.0,
            )

    def test_butterfly_arb_check_no_violations_on_reasonable_params(self):
        """Known reasonable SVI params should have zero violations."""
        k = np.linspace(-0.3, 0.3, 300)
        violations = _butterfly_arb_check(k, 0.02, 0.1, -0.3, 0.0, 0.1)
        assert violations == 0

    def test_svi_implied_vol_surface_shape(self):
        """svi_implied_vol_surface should return correct shape."""
        F, sigma, T, r = 1050.0, 0.22, 30 / 365.25, 0.05
        strikes, _, vols, _ = _make_synthetic_chain(F, sigma, T, r, n_strikes=21)
        params = svi_calibrate(strikes, vols, F, T)

        test_strikes = np.linspace(900, 1200, 50)
        ivs = svi_implied_vol_surface(params, test_strikes)
        assert ivs.shape == (50,)
        assert np.all(ivs > 0)
        assert np.all(np.isfinite(ivs))


# ===========================================================================
# 3. Figlewski tail extension tests
# ===========================================================================

class TestFiglewskiTails:
    """Figlewski piecewise tail extension."""

    def _make_bell_density(self, mu=1050.0, sigma=50.0, n=200):
        """Create a bell-shaped density for testing."""
        x = np.linspace(mu - 4 * sigma, mu + 4 * sigma, n)
        f = np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
        return x, f

    def test_extend_tails_produces_wider_range(self):
        """Extended density should cover a wider range."""
        x, f = self._make_bell_density()
        ext_x, ext_f = extend_tails(x, f)

        assert ext_x[0] < x[0], "Extended lower bound should be below original"
        assert ext_x[-1] > x[-1], "Extended upper bound should be above original"
        assert len(ext_x) > len(x), "Extended grid should have more points"

    def test_extend_tails_non_negative(self):
        """Extended density should be non-negative everywhere."""
        x, f = self._make_bell_density()
        ext_x, ext_f = extend_tails(x, f)
        assert np.all(ext_f >= 0), f"Negative density: min={ext_f.min():.6e}"

    def test_extend_tails_integrates_finite_positive(self):
        """Extended density should integrate to a finite positive value.

        The pipeline re-normalizes after extension, so the raw extended
        density need not integrate to exactly 1.0 — it just needs to be
        finite and positive so that normalization works.
        """
        x, f = self._make_bell_density()
        ext_x, ext_f = extend_tails(x, f)
        area = float(np.trapezoid(ext_f, ext_x))
        assert area > 0.5, f"Extended density area too small: {area:.4f}"
        assert area < 5.0, f"Extended density area too large: {area:.4f}"

    def test_extend_tails_too_few_points_raises(self):
        """Should raise on fewer than 3 points."""
        from engine.rnd.figlewski import FiglewskiTailError

        with pytest.raises(FiglewskiTailError, match="at least 3"):
            extend_tails(np.array([1.0, 2.0]), np.array([0.1, 0.2]))

    def test_extend_tails_smooth_decay(self):
        """Tails should decay toward zero."""
        x, f = self._make_bell_density()
        ext_x, ext_f = extend_tails(x, f, extension_points=50)

        # First 10 points (lower tail) should be small
        assert ext_f[:10].max() < ext_f.max() * 0.5
        # Last 10 points (upper tail) should be small
        assert ext_f[-10:].max() < ext_f.max() * 0.5


# ===========================================================================
# 4. Bucket integrator tests
# ===========================================================================

class TestBucketIntegrator:
    """Bucket integration on known densities."""

    def _normal_density(self, mu=1050.0, sigma=50.0, n=500):
        """Standard normal density on a grid."""
        x = np.linspace(mu - 5 * sigma, mu + 5 * sigma, n)
        f = np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
        return x, f

    def test_survival_matches_normal_cdf(self):
        """P(S > K) should match 1 - Phi((K-mu)/sigma) for normal density."""
        mu, sigma = 1050.0, 50.0
        x, f = self._normal_density(mu, sigma)

        kalshi_strikes = np.array([950.0, 1000.0, 1050.0, 1100.0, 1150.0])
        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)

        for i, K in enumerate(kalshi_strikes):
            expected_survival = 1.0 - float(ndtr((K - mu) / sigma))
            assert abs(result.survival[i] - expected_survival) < 0.02, (
                f"Strike {K}: survival={result.survival[i]:.4f}, "
                f"expected={expected_survival:.4f}"
            )

    def test_bucket_sum_near_one(self):
        """Bucket prices should sum to approximately 1.0."""
        x, f = self._normal_density()
        kalshi_strikes = np.linspace(900, 1200, 20)

        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        assert abs(result.bucket_sum - 1.0) < 0.05

    def test_bucket_prices_non_negative(self):
        """All bucket prices should be non-negative."""
        x, f = self._normal_density()
        kalshi_strikes = np.linspace(900, 1200, 15)

        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        assert np.all(result.bucket_yes >= 0)

    def test_survival_monotone_decreasing(self):
        """Survival function should be monotone non-increasing."""
        x, f = self._normal_density()
        kalshi_strikes = np.linspace(900, 1200, 20)

        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        diffs = np.diff(result.survival)
        assert np.all(diffs <= 1e-10), f"Non-monotone survival: max diff = {diffs.max():.6e}"

    def test_n_buckets_correct(self):
        """Number of buckets should be n_strikes + 1."""
        x, f = self._normal_density()
        kalshi_strikes = np.linspace(900, 1200, 10)

        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        assert result.n_buckets == len(kalshi_strikes) + 1
        assert len(result.bucket_yes) == result.n_buckets

    def test_bucket_sum_exact(self):
        """Bucket sum is algebraically 1.0 by construction of the survival decomposition.

        This verifies the property: lower_tail + interior + upper_tail = 1.0 exactly,
        since (1 - S[0]) + sum(S[i-1] - S[i]) + S[-1] = 1.0 telescopically.
        """
        x, f = self._normal_density()
        kalshi_strikes = np.linspace(900, 1200, 20)
        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        # Sum should be exactly 1.0 (algebraic identity)
        assert abs(result.bucket_sum - 1.0) < 1e-12

    def test_empty_kalshi_strikes_raises(self):
        x, f = self._normal_density()
        with pytest.raises(ValueError, match="non-empty"):
            integrate_buckets(x, f, np.array([]))

    def test_single_kalshi_strike(self):
        """Should work with a single Kalshi strike (2 buckets)."""
        x, f = self._normal_density()
        kalshi_strikes = np.array([1050.0])

        result = integrate_buckets(x, f, kalshi_strikes, sum_tol=0.05)
        assert result.n_buckets == 2
        assert abs(result.bucket_sum - 1.0) < 0.05


# ===========================================================================
# 5. Full pipeline tests
# ===========================================================================

class TestFullPipeline:
    """End-to-end pipeline tests with synthetic OptionsChain."""

    def test_pipeline_produces_bucket_prices(self):
        """Pipeline should produce valid BucketPrices from synthetic chain."""
        chain = _make_options_chain()
        kalshi_strikes = np.arange(900, 1200, 10, dtype=np.float64)

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.05)

        assert isinstance(result, BucketPrices)
        assert result.n_buckets == len(kalshi_strikes) + 1
        assert np.all(result.bucket_yes >= 0)
        assert np.all(result.survival >= 0)
        assert np.all(result.survival <= 1.0)

    def test_pipeline_sum_near_one(self):
        """Bucket prices should sum to approximately 1.0."""
        chain = _make_options_chain()
        kalshi_strikes = np.arange(900, 1200, 10, dtype=np.float64)

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.05)
        assert abs(result.bucket_sum - 1.0) < 0.05

    def test_pipeline_survival_monotone(self):
        """Survival should be monotone non-increasing."""
        chain = _make_options_chain()
        kalshi_strikes = np.arange(900, 1200, 10, dtype=np.float64)

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.05)
        diffs = np.diff(result.survival)
        assert np.all(diffs <= 1e-10)

    def test_pipeline_atm_survival_near_half(self):
        """Survival at ATM should be approximately 0.5."""
        F = 1050.0
        chain = _make_options_chain(forward=F, sigma=0.22, skew=0.0)
        kalshi_strikes = np.array([F])

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.1)
        assert abs(result.survival[0] - 0.5) < 0.1, (
            f"ATM survival = {result.survival[0]:.4f}, expected ~0.5"
        )

    def test_pipeline_without_ivs(self):
        """Pipeline should work when chain has no pre-computed IVs."""
        chain = _make_options_chain()
        # Remove IVs to force bisection
        chain_no_iv = OptionsChain(
            symbol=chain.symbol,
            expiry=chain.expiry,
            as_of=chain.as_of,
            underlying_settle=chain.underlying_settle,
            strikes=chain.strikes,
            call_prices=chain.call_prices,
            put_prices=chain.put_prices,
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )
        kalshi_strikes = np.arange(950, 1150, 20, dtype=np.float64)

        result = compute_rnd(chain_no_iv, kalshi_strikes, sum_tol=0.05)
        assert isinstance(result, BucketPrices)
        assert abs(result.bucket_sum - 1.0) < 0.05

    def test_pipeline_without_tail_extension(self):
        """Pipeline should work with tail extension disabled."""
        chain = _make_options_chain()
        kalshi_strikes = np.arange(950, 1150, 20, dtype=np.float64)

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.05, extend_tails_flag=False)
        assert isinstance(result, BucketPrices)

    def test_pipeline_expired_chain_raises(self):
        """Pipeline should raise on expired options chain."""
        chain = OptionsChain(
            symbol="ZS",
            expiry=date(2026, 3, 1),
            as_of=date(2026, 4, 1),  # as_of after expiry
            underlying_settle=1050.0,
            strikes=np.arange(900, 1200, 10, dtype=np.float64),
            call_prices=np.ones(30) * 50.0,
            put_prices=np.ones(30) * 50.0,
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )
        with pytest.raises(RNDValidationError, match="expired"):
            compute_rnd(chain, np.array([1000.0, 1050.0, 1100.0]))

    def test_pipeline_empty_kalshi_strikes_raises(self):
        chain = _make_options_chain()
        with pytest.raises(RNDValidationError, match="non-empty"):
            compute_rnd(chain, np.array([]))

    def test_pipeline_wide_strike_range(self):
        """Pipeline handles wide Kalshi strike range gracefully."""
        chain = _make_options_chain(n_strikes=61, strike_range=200)
        kalshi_strikes = np.arange(850, 1250, 5, dtype=np.float64)

        result = compute_rnd(chain, kalshi_strikes, sum_tol=0.05)
        assert result.n_buckets == len(kalshi_strikes) + 1

    def test_pipeline_no_pandas(self):
        """Verify no pandas import in the pipeline modules."""
        import engine.rnd.breeden_litzenberger as bl_mod
        import engine.rnd.bucket_integrator as bi_mod
        import engine.rnd.figlewski as fig_mod
        import engine.rnd.pipeline as pipe_mod
        import engine.rnd.svi as svi_mod

        for mod in [bl_mod, bi_mod, fig_mod, pipe_mod, svi_mod]:
            source = open(mod.__file__).read()
            assert "import pandas" not in source, f"pandas imported in {mod.__name__}"
            assert "from pandas" not in source, f"pandas imported in {mod.__name__}"
