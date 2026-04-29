"""Breeden-Litzenberger density extraction.

Extracts the risk-neutral density from call prices via the second derivative:

    f_T(K) = e^(rT) * d^2C / dK^2

Uses central finite differences on sorted (strike, call_price) arrays.

GAP-036: BL identity implementation.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit


class BLDensityError(RuntimeError):
    """Raised when BL density extraction fails."""


@njit(cache=True, fastmath=False)
def _bl_finite_diff(
    strikes: np.ndarray,
    call_prices: np.ndarray,
    discount_factor: float,
    out_strikes: np.ndarray,
    out_density: np.ndarray,
) -> None:
    """Compute BL density via central finite differences.

    For non-uniform strike spacing, uses the 3-point stencil:
        d^2C/dK^2 ≈ (C(K+h2) - C(K))/h2 - (C(K) - C(K-h1))/h1) / ((h1+h2)/2)

    Parameters
    ----------
    strikes : float64[N], sorted ascending
    call_prices : float64[N]
    discount_factor : exp(rT)
    out_strikes : float64[N-2], filled with interior strike values
    out_density : float64[N-2], filled with density values
    """
    n = strikes.shape[0]
    for i in range(1, n - 1):
        h_left = strikes[i] - strikes[i - 1]
        h_right = strikes[i + 1] - strikes[i]
        h_avg = (h_left + h_right) / 2.0

        d2c = (
            (call_prices[i + 1] - call_prices[i]) / h_right
            - (call_prices[i] - call_prices[i - 1]) / h_left
        ) / h_avg

        out_strikes[i - 1] = strikes[i]
        out_density[i - 1] = discount_factor * d2c


def bl_density(
    strikes: np.ndarray,
    call_prices: np.ndarray,
    risk_free_rate: float = 0.0,
    tau: float = 1.0,
    *,
    min_strikes: int = 5,
    allow_negative_clip: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract risk-neutral density via Breeden-Litzenberger.

    Parameters
    ----------
    strikes : 1-D float64 array, sorted ascending.
    call_prices : 1-D float64 array, same length as strikes.
    risk_free_rate : Annual risk-free rate.
    tau : Time to expiry in years.
    min_strikes : Minimum number of strikes required.
    allow_negative_clip : If True, clip negative density to zero (noise).
        If False (default), raise on any negative density value.

    Returns
    -------
    (density_strikes, density_values) : tuple of 1-D float64 arrays
        Interior strikes and corresponding density values.
        Length is len(strikes) - 2.

    Raises
    ------
    BLDensityError
        If insufficient strikes, negative density (when not clipping),
        or invalid inputs.
    """
    strikes = np.ascontiguousarray(strikes, dtype=np.float64)
    call_prices = np.ascontiguousarray(call_prices, dtype=np.float64)

    if strikes.ndim != 1 or call_prices.ndim != 1:
        raise BLDensityError("strikes and call_prices must be 1-D arrays")
    if strikes.shape[0] != call_prices.shape[0]:
        raise BLDensityError(
            f"strikes ({strikes.shape[0]}) and call_prices ({call_prices.shape[0]}) "
            f"must have the same length"
        )
    if strikes.shape[0] < min_strikes:
        raise BLDensityError(
            f"Insufficient strikes: {strikes.shape[0]} < {min_strikes} minimum"
        )
    if not np.all(np.isfinite(strikes)) or not np.all(np.isfinite(call_prices)):
        raise BLDensityError("strikes and call_prices must contain only finite values")
    if tau <= 0.0 or not math.isfinite(tau):
        raise BLDensityError(f"tau must be finite and > 0, got {tau}")
    if not math.isfinite(risk_free_rate):
        raise BLDensityError(f"risk_free_rate must be finite, got {risk_free_rate}")

    # Verify sorted ascending
    diffs = np.diff(strikes)
    if np.any(diffs <= 0):
        raise BLDensityError("strikes must be strictly ascending")

    discount_factor = math.exp(risk_free_rate * tau)
    n = strikes.shape[0]
    out_strikes = np.empty(n - 2, dtype=np.float64)
    out_density = np.empty(n - 2, dtype=np.float64)

    _bl_finite_diff(strikes, call_prices, discount_factor, out_strikes, out_density)

    # Check for negative density
    if np.any(out_density < 0):
        if allow_negative_clip:
            out_density = np.maximum(out_density, 0.0)
        else:
            neg_idx = int(np.argmin(out_density))
            raise BLDensityError(
                f"Negative density at strike {out_strikes[neg_idx]:.4f}: "
                f"{out_density[neg_idx]:.6e} (arbitrage violation). "
                f"Set allow_negative_clip=True to clip to zero."
            )

    return out_strikes, out_density
