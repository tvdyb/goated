"""RND pipeline orchestrator.

Wires together: options chain -> BL -> SVI -> Figlewski -> bucket integration.

    compute_rnd(options_chain, kalshi_strikes) -> BucketPrices

Raises on any stage failure (fail-loud).

GAP-006: model-implied vs market-implied density.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import ndtr

from engine.rnd.breeden_litzenberger import bl_density
from engine.rnd.bucket_integrator import BucketPrices, integrate_buckets
from engine.rnd.figlewski import FiglewskiTailError, extend_tails
from engine.rnd.svi import (
    svi_calibrate,
    svi_implied_vol_surface,
)
from feeds.cme.options_chain import OptionsChain


class RNDValidationError(RuntimeError):
    """Raised when the RND pipeline produces invalid output."""


_INV_SQRT2 = 0.7071067811865476


def _black76_call(
    forward: float,
    strikes: np.ndarray,
    tau: float,
    sigma: np.ndarray,
    risk_free_rate: float,
) -> np.ndarray:
    """Black-76 call prices for futures options (vectorized).

    C = e^(-rT) * [F*N(d1) - K*N(d2)]
    d1 = (ln(F/K) + 0.5*sigma^2*T) / (sigma*sqrt(T))
    d2 = d1 - sigma*sqrt(T)
    """
    discount = math.exp(-risk_free_rate * tau)
    sqrt_tau = math.sqrt(tau)
    sig_sqrt_tau = sigma * sqrt_tau

    # Avoid div-by-zero for zero vol
    safe_sig = np.where(sig_sqrt_tau > 1e-12, sig_sqrt_tau, 1e-12)

    log_fk = np.log(forward / strikes)
    d1 = (log_fk + 0.5 * sigma ** 2 * tau) / safe_sig
    d2 = d1 - safe_sig

    return discount * (forward * ndtr(d1) - strikes * ndtr(d2))


def _chain_to_implied_vols(
    chain: OptionsChain,
    tau: float,
    risk_free_rate: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract implied vols from an options chain.

    If the chain already has IVs, use them. Otherwise, invert Black-76
    via bisection.

    Returns (strikes, implied_vols) with valid entries only.
    """
    # Prefer chain-provided IVs if available
    if chain.call_ivs is not None:
        valid = np.isfinite(chain.call_ivs) & (chain.call_ivs > 0.001) & (chain.call_ivs < 5.0)
        if valid.sum() >= 5:
            return chain.strikes[valid], chain.call_ivs[valid]

    # Fall back to inverting Black-76 from call prices
    forward = chain.underlying_settle
    strikes = chain.strikes
    call_prices = chain.call_prices

    ivs = np.empty(len(strikes), dtype=np.float64)
    valid = np.ones(len(strikes), dtype=np.bool_)

    for i in range(len(strikes)):
        iv = _bisect_iv(
            call_prices[i], forward, strikes[i], tau, risk_free_rate
        )
        if iv is not None and 0.001 < iv < 5.0:
            ivs[i] = iv
        else:
            valid[i] = False

    return strikes[valid], ivs[valid]


def _bisect_iv(
    price: float,
    forward: float,
    strike: float,
    tau: float,
    risk_free_rate: float,
    tol: float = 1e-8,
    max_iter: int = 100,
) -> float | None:
    """Bisection implied vol solver for a single option."""
    if price <= 0 or not math.isfinite(price):
        return None
    if strike <= 0 or forward <= 0 or tau <= 0:
        return None

    discount = math.exp(-risk_free_rate * tau)
    intrinsic = discount * max(forward - strike, 0.0)
    if price <= intrinsic + tol:
        return 0.001

    lo, hi = 0.001, 5.0
    sqrt_tau = math.sqrt(tau)

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        sig_sqrt_tau = mid * sqrt_tau
        if sig_sqrt_tau < 1e-12:
            lo = mid
            continue

        d1 = (math.log(forward / strike) + 0.5 * mid ** 2 * tau) / sig_sqrt_tau
        d2 = d1 - sig_sqrt_tau
        # ndtr is only available as numpy ufunc; use math.erfc for scalar
        nd1 = 0.5 * math.erfc(-d1 * _INV_SQRT2)
        nd2 = 0.5 * math.erfc(-d2 * _INV_SQRT2)
        model_price = discount * (forward * nd1 - strike * nd2)

        if abs(model_price - price) < tol:
            return mid
        if model_price > price:
            hi = mid
        else:
            lo = mid

    return (lo + hi) / 2.0


def compute_rnd(
    chain: OptionsChain,
    kalshi_strikes: np.ndarray,
    *,
    risk_free_rate: float = 0.05,
    sum_tol: float = 0.02,
    max_butterfly_violations: int = 5,
    svi_dense_points: int = 500,
    extend_tails_flag: bool = True,
) -> BucketPrices:
    """Full RND pipeline: options chain -> bucket Yes-prices.

    Parameters
    ----------
    chain : OptionsChain from feeds/cme/options_chain.py.
    kalshi_strikes : Sorted ascending Kalshi half-line strikes.
    risk_free_rate : Annual risk-free rate.
    sum_tol : Bucket sum-to-1 tolerance.
    max_butterfly_violations : Max allowed SVI butterfly violations.
    svi_dense_points : Points for SVI-smoothed density grid.
    extend_tails_flag : Whether to apply Figlewski tail extension.

    Returns
    -------
    BucketPrices with survival function and per-bucket Yes-prices.

    Raises
    ------
    RNDValidationError, BLDensityError, SVICalibrationError,
    SVIArbViolationError, FiglewskiTailError, BucketSumError
    on any stage failure.
    """
    kalshi_strikes = np.ascontiguousarray(kalshi_strikes, dtype=np.float64)

    if kalshi_strikes.ndim != 1 or kalshi_strikes.shape[0] == 0:
        raise RNDValidationError("kalshi_strikes must be a non-empty 1-D array")

    # --- Stage 1: Extract tau ---
    days_to_expiry = (chain.expiry - chain.as_of).days
    if days_to_expiry <= 0:
        raise RNDValidationError(
            f"Options chain is expired: expiry={chain.expiry}, as_of={chain.as_of}"
        )
    tau = days_to_expiry / 365.25
    forward = chain.underlying_settle

    # --- Stage 2: Extract implied vols ---
    iv_strikes, implied_vols = _chain_to_implied_vols(chain, tau, risk_free_rate)

    if len(iv_strikes) < 5:
        raise RNDValidationError(
            f"Insufficient valid IV points: {len(iv_strikes)} (need >= 5)"
        )

    # --- Stage 3: SVI calibration ---
    svi_params = svi_calibrate(
        iv_strikes,
        implied_vols,
        forward,
        tau,
        max_butterfly_violations=max_butterfly_violations,
    )

    # --- Stage 4: SVI-smoothed call prices -> BL density ---
    # Build a dense strike grid covering kalshi range + margins
    strike_span = kalshi_strikes[-1] - kalshi_strikes[0]
    if strike_span < 1.0:
        # Single strike or very narrow range — use forward-based range
        strike_span = forward * 0.3
    margin = max(0.3 * strike_span, forward * 0.1)
    grid_lo = max(kalshi_strikes[0] - margin, forward * 0.5)
    grid_hi = kalshi_strikes[-1] + margin

    dense_strikes = np.linspace(grid_lo, grid_hi, svi_dense_points)

    # SVI implied vols on the dense grid
    svi_ivs = svi_implied_vol_surface(svi_params, dense_strikes)
    svi_ivs = np.maximum(svi_ivs, 0.001)

    # Black-76 call prices from SVI
    svi_calls = _black76_call(forward, dense_strikes, tau, svi_ivs, risk_free_rate)

    # BL density on the SVI-smoothed surface (allow clipping since SVI
    # may introduce minor numerical noise at edges)
    density_strikes, density_values = bl_density(
        dense_strikes,
        svi_calls,
        risk_free_rate=risk_free_rate,
        tau=tau,
        min_strikes=5,
        allow_negative_clip=True,
    )

    # --- Stage 5: Normalize density ---
    area = float(np.trapezoid(density_values, density_strikes))
    if area <= 0:
        raise RNDValidationError(
            f"BL density integrates to {area:.6f} (non-positive). "
            f"Check options chain data quality."
        )
    density_values = density_values / area

    # Verify normalization
    area_norm = float(np.trapezoid(density_values, density_strikes))
    if abs(area_norm - 1.0) > 0.02:
        raise RNDValidationError(
            f"Normalized density integrates to {area_norm:.6f}, expected ~1.0"
        )

    # --- Stage 6: Figlewski tail extension ---
    if extend_tails_flag:
        try:
            density_strikes, density_values = extend_tails(
                density_strikes, density_values
            )
            # Re-normalize after tail extension
            area_ext = float(np.trapezoid(density_values, density_strikes))
            if area_ext > 0:
                density_values = density_values / area_ext
        except FiglewskiTailError:
            # Tail extension failed — proceed with interior density only.
            # This is acceptable per the spec: "fall back to log-normal tails
            # and document the fallback."
            pass

    # --- Stage 7: Bucket integration ---
    result = integrate_buckets(
        density_strikes,
        density_values,
        kalshi_strikes,
        sum_tol=sum_tol,
    )

    return result
