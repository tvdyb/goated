"""Bucket integrator: density -> P(S > K_i) for Kalshi half-line strikes.

Integrates the RND over each Kalshi half-line market to produce per-bucket
Yes-prices, with a sum-to-1 gate.

GAP-043: Bucket integration.
GAP-044: Sum-to-1 normalization gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit


class BucketSumError(RuntimeError):
    """Raised when bucket Yes-prices fail the sum-to-1 gate."""


@dataclass(frozen=True, slots=True)
class BucketPrices:
    """Result of bucket integration over Kalshi half-line strikes.

    Attributes
    ----------
    kalshi_strikes : Sorted ascending Kalshi half-line strikes.
    survival : P(S_T > K_i) for each strike (survival function).
    bucket_yes : Yes-price for each bucket.
        bucket_yes[i] = P(K_i < S_T <= K_{i+1}) for interior buckets.
        bucket_yes[0] = P(S_T <= K_0) (lower tail).
        bucket_yes[-1] = P(S_T > K_{n-1}) (upper tail).
    bucket_sum : Sum of bucket_yes (should be ~1.0).
    n_buckets : Number of buckets (len(kalshi_strikes) + 1).
    """

    kalshi_strikes: np.ndarray
    survival: np.ndarray
    bucket_yes: np.ndarray
    bucket_sum: float
    n_buckets: int


@njit(cache=True, fastmath=False)
def _compute_survival(
    density_strikes: np.ndarray,
    density_values: np.ndarray,
    query_strikes: np.ndarray,
    out: np.ndarray,
) -> None:
    """Compute P(S > K) for each query strike via trapezoidal integration.

    P(S > K) = integral from K to +inf of f(s) ds

    We compute the CDF first, then survival = 1 - CDF.
    """
    n_density = density_strikes.shape[0]
    n_query = query_strikes.shape[0]

    # Compute full CDF via trapezoidal rule
    total_area = 0.0
    for i in range(n_density - 1):
        dx = density_strikes[i + 1] - density_strikes[i]
        total_area += 0.5 * (density_values[i] + density_values[i + 1]) * dx

    for q in range(n_query):
        k_val = query_strikes[q]

        if density_strikes[0] >= k_val:
            out[q] = 1.0
            continue
        if density_strikes[n_density - 1] <= k_val:
            out[q] = 0.0
            continue

        # CDF(k_val) = integral from -inf to k_val
        cdf = 0.0
        for i in range(n_density - 1):
            x0 = density_strikes[i]
            x1 = density_strikes[i + 1]
            f0 = density_values[i]
            f1 = density_values[i + 1]

            if x1 <= k_val:
                # Entire interval below k_val
                cdf += 0.5 * (f0 + f1) * (x1 - x0)
            elif x0 >= k_val:
                # Entire interval above k_val
                break
            else:
                # k_val falls within this interval — interpolate
                frac = (k_val - x0) / (x1 - x0)
                f_at_k = f0 + frac * (f1 - f0)
                cdf += 0.5 * (f0 + f_at_k) * (k_val - x0)
                break

        if total_area > 0.0:
            out[q] = 1.0 - cdf / total_area
        else:
            out[q] = 0.0


@njit(cache=True, fastmath=False)
def _compute_bucket_prices(
    survival: np.ndarray,
    n_strikes: int,
    out: np.ndarray,
) -> None:
    """Compute bucket Yes-prices from survival function values.

    n_buckets = n_strikes + 1

    out[0]          = 1 - survival[0]           (lower tail: P(S <= K_0))
    out[i]          = survival[i-1] - survival[i]  for 1 <= i < n_strikes
    out[n_strikes]  = survival[n_strikes - 1]   (upper tail: P(S > K_last))
    """
    # Lower tail
    out[0] = 1.0 - survival[0]

    # Interior buckets
    for i in range(1, n_strikes):
        out[i] = survival[i - 1] - survival[i]

    # Upper tail
    out[n_strikes] = survival[n_strikes - 1]


def integrate_buckets(
    density_strikes: np.ndarray,
    density_values: np.ndarray,
    kalshi_strikes: np.ndarray,
    *,
    sum_tol: float = 0.02,
) -> BucketPrices:
    """Integrate density over Kalshi half-line strikes.

    Parameters
    ----------
    density_strikes : 1-D float64, sorted ascending. The x-grid of the density.
    density_values : 1-D float64, density values at each strike.
    kalshi_strikes : 1-D float64, sorted ascending. Kalshi half-line strike grid.
    sum_tol : Tolerance for the sum-to-1 gate.

    Returns
    -------
    BucketPrices with survival function and per-bucket Yes-prices.

    Raises
    ------
    BucketSumError if bucket prices don't sum to ~1.0 within sum_tol.
    ValueError on invalid inputs.
    """
    density_strikes = np.ascontiguousarray(density_strikes, dtype=np.float64)
    density_values = np.ascontiguousarray(density_values, dtype=np.float64)
    kalshi_strikes = np.ascontiguousarray(kalshi_strikes, dtype=np.float64)

    if density_strikes.ndim != 1 or density_values.ndim != 1:
        raise ValueError("density_strikes and density_values must be 1-D")
    if density_strikes.shape[0] != density_values.shape[0]:
        raise ValueError("density_strikes and density_values must have same length")
    if density_strikes.shape[0] < 3:
        raise ValueError(f"Need at least 3 density points, got {density_strikes.shape[0]}")
    if kalshi_strikes.ndim != 1 or kalshi_strikes.shape[0] == 0:
        raise ValueError("kalshi_strikes must be a non-empty 1-D array")

    n_strikes = kalshi_strikes.shape[0]

    # Compute survival function at each Kalshi strike
    survival = np.empty(n_strikes, dtype=np.float64)
    _compute_survival(density_strikes, density_values, kalshi_strikes, survival)

    # Clip survival to [0, 1] and ensure monotone non-increasing
    survival = np.clip(survival, 0.0, 1.0)
    for i in range(1, n_strikes):
        survival[i] = min(survival[i], survival[i - 1])

    # Compute bucket prices
    n_buckets = n_strikes + 1
    bucket_yes = np.empty(n_buckets, dtype=np.float64)
    _compute_bucket_prices(survival, n_strikes, bucket_yes)

    bucket_sum = float(bucket_yes.sum())
    if abs(bucket_sum - 1.0) > sum_tol:
        raise BucketSumError(
            f"Bucket Yes-prices sum to {bucket_sum:.6f}, expected ~1.0 "
            f"(tolerance {sum_tol:.4f}). "
            f"n_strikes={n_strikes}, density_range="
            f"[{density_strikes[0]:.2f}, {density_strikes[-1]:.2f}]"
        )

    return BucketPrices(
        kalshi_strikes=kalshi_strikes,
        survival=survival,
        bucket_yes=bucket_yes,
        bucket_sum=bucket_sum,
        n_buckets=n_buckets,
    )
