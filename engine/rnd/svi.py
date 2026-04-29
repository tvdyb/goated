"""SVI (Stochastic Volatility Inspired) calibration.

Gatheral's SVI parameterization of the implied variance smile:

    w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

where k = ln(K/F) is log-moneyness, w = IV^2 * T is total implied variance.

Butterfly arbitrage constraint per Gatheral (2004) / Durrleman:
    g(k) = (1 - k*w'/(2*w))^2 - w'^2/4*(1/w + 1/4) + w''/2 >= 0

GAP-037: SVI calibration.
GAP-038: Butterfly arb constraints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.optimize import minimize


class SVICalibrationError(RuntimeError):
    """Raised when SVI calibration fails."""


class SVIArbViolationError(RuntimeError):
    """Raised when SVI fit violates butterfly arbitrage constraints."""


@dataclass(frozen=True, slots=True)
class SVIParams:
    """Fitted SVI parameters."""

    a: float
    b: float
    rho: float
    m: float
    sigma: float
    tau: float
    forward: float
    residual: float
    butterfly_violations: int


@njit(cache=True, fastmath=False)
def _svi_total_variance(k: np.ndarray, a: float, b: float, rho: float, m: float, sigma: float) -> np.ndarray:
    """Evaluate SVI total variance w(k) at an array of log-moneyness values."""
    n = k.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        diff = k[i] - m
        out[i] = a + b * (rho * diff + math.sqrt(diff * diff + sigma * sigma))
    return out


@njit(cache=True, fastmath=False)
def _svi_total_variance_scalar(k: float, a: float, b: float, rho: float, m: float, sigma: float) -> float:
    """Evaluate SVI total variance w(k) at a single log-moneyness value."""
    diff = k - m
    return a + b * (rho * diff + math.sqrt(diff * diff + sigma * sigma))


@njit(cache=True, fastmath=False)
def _svi_implied_vol(
    k: np.ndarray,
    a: float,
    b: float,
    rho: float,
    m: float,
    sigma: float,
    tau: float,
) -> np.ndarray:
    """Compute implied vol from SVI parameters: IV = sqrt(w(k) / T)."""
    n = k.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        diff = k[i] - m
        w = a + b * (rho * diff + math.sqrt(diff * diff + sigma * sigma))
        if w < 0.0:
            out[i] = 0.0
        else:
            out[i] = math.sqrt(w / tau)
    return out


@njit(cache=True, fastmath=False)
def _butterfly_arb_check(
    k_grid: np.ndarray,
    a: float,
    b: float,
    rho: float,
    m: float,
    sigma: float,
) -> int:
    """Count butterfly arbitrage violations on a dense k grid.

    Durrleman condition:
        g(k) = (1 - k*w'/(2*w))^2 - w'^2/4*(1/w + 1/4) + w''/2 >= 0

    w'(k)  = b * (rho + (k-m) / sqrt((k-m)^2 + sigma^2))
    w''(k) = b * sigma^2 / ((k-m)^2 + sigma^2)^(3/2)
    """
    n = k_grid.shape[0]
    violations = 0
    tol = -1e-8

    for i in range(n):
        diff = k_grid[i] - m
        denom = math.sqrt(diff * diff + sigma * sigma)
        w = a + b * (rho * diff + denom)
        if w <= 0.0:
            violations += 1
            continue

        w_prime = b * (rho + diff / denom)
        w_dprime = b * sigma * sigma / (denom * denom * denom)

        term1 = 1.0 - k_grid[i] * w_prime / (2.0 * w)
        g = term1 * term1 - w_prime * w_prime / 4.0 * (1.0 / w + 0.25) + w_dprime / 2.0

        if g < tol:
            violations += 1

    return violations


def _svi_objective(
    params: np.ndarray,
    k: np.ndarray,
    w_market: np.ndarray,
    arb_penalty_weight: float,
) -> float:
    """Weighted least squares + arb penalty."""
    a, b, rho, m, sigma_p = params[0], params[1], params[2], params[3], params[4]

    w_model = _svi_total_variance(k, a, b, rho, m, sigma_p)

    # Residual
    residual = float(np.sum((w_model - w_market) ** 2))

    # Penalize negative total variance
    neg_mask = w_model < 0
    if np.any(neg_mask):
        residual += 1000.0 * float(np.sum(w_model[neg_mask] ** 2))

    # Butterfly arb penalty
    if arb_penalty_weight > 0:
        k_dense = np.linspace(k.min() - 0.1, k.max() + 0.1, 200)
        n_violations = _butterfly_arb_check(k_dense, a, b, rho, m, sigma_p)
        residual += arb_penalty_weight * n_violations

    return residual


def svi_calibrate(
    strikes: np.ndarray,
    implied_vols: np.ndarray,
    forward: float,
    tau: float,
    *,
    arb_penalty_weight: float = 10.0,
    max_butterfly_violations: int = 0,
    arb_check_points: int = 500,
) -> SVIParams:
    """Calibrate SVI to market implied volatilities.

    Parameters
    ----------
    strikes : 1-D float64, sorted ascending.
    implied_vols : 1-D float64, implied volatilities at each strike.
    forward : Forward price (futures settle).
    tau : Time to expiry in years.
    arb_penalty_weight : Weight for butterfly arb penalty in objective.
    max_butterfly_violations : Maximum allowed violations after fit.
    arb_check_points : Number of points for dense arb check.

    Returns
    -------
    SVIParams with fitted parameters.

    Raises
    ------
    SVICalibrationError on fit failure.
    SVIArbViolationError if butterfly violations exceed max_butterfly_violations.
    """
    if len(strikes) < 5:
        raise SVICalibrationError(f"Need >= 5 strikes for SVI fit, got {len(strikes)}")
    if tau <= 0.0 or not math.isfinite(tau):
        raise SVICalibrationError(f"tau must be finite and > 0, got {tau}")
    if forward <= 0.0 or not math.isfinite(forward):
        raise SVICalibrationError(f"forward must be finite and > 0, got {forward}")

    strikes = np.ascontiguousarray(strikes, dtype=np.float64)
    implied_vols = np.ascontiguousarray(implied_vols, dtype=np.float64)

    # Filter valid IVs
    valid = (implied_vols > 0.001) & (implied_vols < 5.0) & np.isfinite(implied_vols)
    if valid.sum() < 5:
        raise SVICalibrationError(
            f"Need >= 5 valid IV points, got {valid.sum()} "
            f"(total {len(implied_vols)}, filtered by (0.001, 5.0))"
        )
    k = np.log(strikes[valid] / forward)
    w_market = implied_vols[valid] ** 2 * tau

    # Initial guess
    a0 = float(np.mean(w_market))
    b0 = 0.1
    rho0 = -0.3
    m0 = 0.0
    sigma0 = 0.1

    bounds = [
        (1e-6, 2.0),     # a > 0
        (1e-6, 5.0),     # b > 0
        (-0.999, 0.999), # |rho| < 1
        (-1.0, 1.0),     # m
        (1e-4, 2.0),     # sigma > 0
    ]

    # Two-pass: first without arb penalty, then with
    result1 = minimize(
        _svi_objective,
        np.array([a0, b0, rho0, m0, sigma0]),
        args=(k, w_market, 0.0),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 5000, "ftol": 1e-15},
    )

    # Second pass with arb penalty starting from first result
    result2 = minimize(
        _svi_objective,
        result1.x,
        args=(k, w_market, arb_penalty_weight),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 5000, "ftol": 1e-15},
    )

    best = result2 if result2.success or result2.fun <= result1.fun else result1
    a, b, rho, m_fit, sigma_fit = best.x

    # Final butterfly arb check
    k_check = np.linspace(
        float(k.min()) - 0.2, float(k.max()) + 0.2, arb_check_points
    )
    n_violations = _butterfly_arb_check(k_check, a, b, rho, m_fit, sigma_fit)

    if n_violations > max_butterfly_violations:
        raise SVIArbViolationError(
            f"SVI fit has {n_violations}/{arb_check_points} butterfly arb violations "
            f"(max allowed: {max_butterfly_violations}). "
            f"Params: a={a:.6f}, b={b:.6f}, rho={rho:.4f}, m={m_fit:.6f}, sigma={sigma_fit:.6f}"
        )

    return SVIParams(
        a=a,
        b=b,
        rho=rho,
        m=m_fit,
        sigma=sigma_fit,
        tau=tau,
        forward=forward,
        residual=float(best.fun),
        butterfly_violations=n_violations,
    )


def svi_implied_vol_surface(
    params: SVIParams,
    strikes: np.ndarray,
) -> np.ndarray:
    """Compute implied vols from fitted SVI params at given strikes.

    Returns 1-D float64 array of implied volatilities.
    """
    strikes = np.ascontiguousarray(strikes, dtype=np.float64)
    k = np.log(strikes / params.forward)
    return _svi_implied_vol(k, params.a, params.b, params.rho, params.m, params.sigma, params.tau)
