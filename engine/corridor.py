"""Corridor decomposition adapter: BucketGrid -> Yes-price vector.

Converts the existing GBM model's P(S_T > K) digital-call output into
per-bucket Yes-prices using the identity:

    Yes_price(bucket_i) = P(S_T >= L_i) - P(S_T >= U_i)

with tail-bucket handling:
    Lower tail [0, L):   1 - P(S_T >= L)
    Upper tail [U, inf):  P(S_T >= U)

Sum-to-1 gate: raises CorridorSumError if bucket prices do not sum to 1.0
within tolerance.  No silent normalization (fail-loud per non-negotiables).

ACT-13 closes GAP-005.

References:
    - Phase 08 section 1 (digital-corridor decomposition)
    - models/gbm.py (_gbm_prob_above kernel)
    - feeds/kalshi/events.py (BucketGrid, Bucket)
"""

from __future__ import annotations

import numpy as np
from numba import njit

from feeds.kalshi.events import BucketGrid
from models.gbm import _gbm_prob_above


class CorridorSumError(RuntimeError):
    """Raised when bucket Yes-prices fail the sum-to-1 gate."""

    pass


@njit(cache=True, fastmath=False)
def _corridor_prices(prob_above: np.ndarray, n_buckets: int, out: np.ndarray) -> None:
    """Compute bucket Yes-prices from P(S_T >= boundary_i) values.

    Parameters
    ----------
    prob_above : float64[n_boundaries]
        P(S_T >= K) for each of the (n_buckets - 1) interior boundaries,
        ordered by increasing strike.  len == n_buckets - 1.
    n_buckets : int
        Total number of buckets (including lower and upper tail).
    out : float64[n_buckets]
        Output array, filled in-place with Yes-prices.

    Layout (n_buckets = N, n_boundaries = N-1):
        out[0]       = 1 - prob_above[0]           (lower tail)
        out[i]       = prob_above[i-1] - prob_above[i]  for 1 <= i < N-1
        out[N-1]     = prob_above[N-2]              (upper tail)
    """
    n_boundaries = n_buckets - 1

    # Lower tail: P(S_T < first_boundary) = 1 - P(S_T >= first_boundary)
    out[0] = 1.0 - prob_above[0]

    # Interior buckets
    for i in range(1, n_boundaries):
        out[i] = prob_above[i - 1] - prob_above[i]

    # Upper tail: P(S_T >= last_boundary)
    out[n_buckets - 1] = prob_above[n_boundaries - 1]


def _extract_boundaries(grid: BucketGrid) -> np.ndarray:
    """Extract sorted interior boundary strikes from a BucketGrid.

    For N buckets there are exactly N-1 interior boundaries.
    The lower tail's upper bound is the first boundary;
    each subsequent bucket's lower bound adds boundaries;
    the upper tail's lower bound is the last boundary.

    Returns a contiguous float64 array of length (n_buckets - 1).
    """
    n = grid.n_buckets
    boundaries = np.empty(n - 1, dtype=np.float64)

    # The first boundary is the lower tail's upper edge
    first_upper = grid.lower_tail.upper
    assert first_upper is not None  # enforced by BucketGrid MECE validation
    boundaries[0] = first_upper

    # Interior buckets contribute their upper edge (which equals the next bucket's lower edge)
    for i, bucket in enumerate(grid.interior_buckets):
        assert bucket.upper is not None
        boundaries[i + 1] = bucket.upper

    # Sanity: last boundary should equal the upper tail's lower edge
    assert grid.upper_tail.lower is not None
    # The last entry was already set by the last interior bucket's upper,
    # which should equal upper_tail.lower (MECE guarantees this).
    # If there are no interior buckets, boundaries has only 1 element (set above).

    return boundaries


def bucket_prices(
    grid: BucketGrid,
    spot: float,
    tau: float,
    sigma: float,
    basis_drift: float = 0.0,
    *,
    sum_tol: float = 1e-9,
) -> np.ndarray:
    """Compute Yes-price vector for a BucketGrid via corridor decomposition.

    Parameters
    ----------
    grid : BucketGrid
        MECE-validated bucket grid from ACT-04.
    spot : float
        Current spot price (Pyth oracle).
    tau : float
        Time to expiry in years (must be > 0).
    sigma : float
        Annualized volatility (must be > 0).
    basis_drift : float
        Basis drift rate (default 0.0).
    sum_tol : float
        Tolerance for the sum-to-1 gate (default 1e-9).

    Returns
    -------
    np.ndarray
        float64[n_buckets] Yes-prices, one per bucket in grid order.

    Raises
    ------
    ValueError
        If spot, tau, or sigma are non-positive or non-finite.
    CorridorSumError
        If bucket Yes-prices do not sum to 1.0 within sum_tol.
    """
    import math

    if not (spot > 0.0) or not math.isfinite(spot):
        raise ValueError(f"spot must be finite and > 0, got {spot}")
    if not (tau > 0.0) or not math.isfinite(tau):
        raise ValueError(f"tau must be finite and > 0, got {tau}")
    if not (sigma > 0.0) or not math.isfinite(sigma):
        raise ValueError(f"sigma must be finite and > 0, got {sigma}")
    if not math.isfinite(basis_drift):
        raise ValueError(f"basis_drift must be finite, got {basis_drift}")

    boundaries = _extract_boundaries(grid)

    # Compute P(S_T >= K) for each boundary using existing GBM kernel
    prob_above = np.empty_like(boundaries)
    _gbm_prob_above(
        float(spot),
        boundaries,
        float(tau),
        float(sigma),
        float(basis_drift),
        prob_above,
    )

    # Compute corridor prices
    n = grid.n_buckets
    out = np.empty(n, dtype=np.float64)
    _corridor_prices(prob_above, n, out)

    # Sum-to-1 gate (fail-loud)
    total = out.sum()
    if abs(total - 1.0) > sum_tol:
        raise CorridorSumError(
            f"Bucket Yes-prices sum to {total:.15e}, expected 1.0 "
            f"(tolerance {sum_tol:.1e}). "
            f"n_buckets={n}, spot={spot}, tau={tau}, sigma={sigma}, "
            f"basis_drift={basis_drift}"
        )

    return out
