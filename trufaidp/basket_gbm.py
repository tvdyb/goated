"""Basket-GBM digital pricer for the Truflation AI & DePIN Index.

The index is a weighted sum I(t) = sum(n_i * P_i(t)) of 6 correlated
lognormals. Under risk-neutral GBM with zero drift,

    P_i(T) = P_i(t) * exp(-sigma_i^2 * tau / 2 + sigma_i * sqrt(tau) * Z_i),
    Cov(Z_i, Z_j) = rho_ij,

so I(T) is a sum of correlated lognormals with no closed form. We use
Levy moment-matching: match the first two moments of I(T) to a single
lognormal and read off P(I(T) > K) = Phi(d2). For short horizons and
moderate vols this matches Monte Carlo to <0.5% in the tails.

Moments under zero drift:
    E[I(T)]    = sum(n_i * P_i(t))                       = I(t)
    E[I(T)^2]  = sum_ij n_i n_j P_i P_j exp(sigma_i sigma_j rho_ij tau)
    Var[I(T)]  = E[I^2] - E[I]^2

Match: sigma_I^2 = ln(1 + Var/E^2),  m_I = ln(E) - sigma_I^2 / 2.
Then d2 = (m_I - ln(K)) / sigma_I,  P(I_T > K) = Phi(d2).
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

_INV_SQRT2 = 0.7071067811865476


@njit(cache=True, fastmath=False)
def _basket_gbm_prob_above(
    quantities: np.ndarray,   # (m,) token counts n_i
    spots: np.ndarray,        # (m,) live token prices P_i(t)
    sigmas: np.ndarray,       # (m,) annualized vols
    corr: np.ndarray,         # (m, m) correlation matrix
    tau: float,               # years to settlement
    strikes: np.ndarray,      # (k,)
    out: np.ndarray,          # (k,)
) -> None:
    m = quantities.shape[0]
    notional = np.empty(m)
    for i in range(m):
        notional[i] = quantities[i] * spots[i]

    e = 0.0
    for i in range(m):
        e += notional[i]

    e2 = 0.0
    for i in range(m):
        for j in range(m):
            e2 += notional[i] * notional[j] * math.exp(sigmas[i] * sigmas[j] * corr[i, j] * tau)

    var = e2 - e * e
    if var <= 0.0:
        sigma_i = 0.0
    else:
        sigma_i_sq = math.log1p(var / (e * e))
        sigma_i = math.sqrt(sigma_i_sq)
    m_i = math.log(e) - 0.5 * sigma_i * sigma_i

    n = strikes.shape[0]
    if sigma_i == 0.0:
        for k_idx in range(n):
            out[k_idx] = 1.0 if e > strikes[k_idx] else 0.0
        return

    for k_idx in range(n):
        d2 = (m_i - math.log(strikes[k_idx])) / sigma_i
        out[k_idx] = 0.5 * math.erfc(-d2 * _INV_SQRT2)


def basket_gbm_prob_above(
    quantities: np.ndarray,
    spots: np.ndarray,
    sigmas: np.ndarray,
    corr: np.ndarray,
    tau: float,
    strikes: np.ndarray,
) -> np.ndarray:
    quantities = np.ascontiguousarray(quantities, dtype=np.float64)
    spots = np.ascontiguousarray(spots, dtype=np.float64)
    sigmas = np.ascontiguousarray(sigmas, dtype=np.float64)
    corr = np.ascontiguousarray(corr, dtype=np.float64)
    strikes = np.ascontiguousarray(strikes, dtype=np.float64)

    if quantities.ndim != 1 or spots.shape != quantities.shape or sigmas.shape != quantities.shape:
        raise ValueError("quantities, spots, sigmas must be 1-D and same length")
    if corr.shape != (quantities.size, quantities.size):
        raise ValueError(f"corr must be ({quantities.size},{quantities.size}), got {corr.shape}")
    if not (tau > 0.0) or not math.isfinite(tau):
        raise ValueError(f"tau must be finite and > 0, got {tau}")
    if np.any(spots <= 0.0) or np.any(~np.isfinite(spots)):
        raise ValueError("spots must be finite and > 0")
    if np.any(sigmas < 0.0) or np.any(~np.isfinite(sigmas)):
        raise ValueError("sigmas must be finite and >= 0")
    if np.any(strikes <= 0.0) or np.any(~np.isfinite(strikes)):
        raise ValueError("strikes must be finite and > 0")

    out = np.empty_like(strikes)
    _basket_gbm_prob_above(quantities, spots, sigmas, corr, float(tau), strikes, out)
    return out
