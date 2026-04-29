"""Aggregate Kalshi book delta computation.

Computes the portfolio delta with respect to the underlying commodity
price from Kalshi binary option positions and the RND-derived bucket
prices.

For each position in market i:
    delta_contribution = quantity_i * d(P(S > K_i)) / dS

The derivative is approximated via finite differences on the survival
curve from BucketPrices.

This is NOT hot-path code (runs once per hedge check cycle, not per tick).

Non-negotiables: no pandas, fail-loud, type hints.
"""

from __future__ import annotations

import numpy as np

from engine.rnd.bucket_integrator import BucketPrices
from state.positions import PositionStore


def aggregate_delta(
    positions: PositionStore,
    bucket_prices: BucketPrices,
    event_ticker: str,
) -> float:
    """Compute aggregate portfolio delta for an event.

    The delta of a binary option P(S > K) with respect to S is
    approximately the RND density at K: f(K) = -dP(S>K)/dK.
    Since we want dP/dS (sensitivity to spot), and K is fixed,
    we use dP/dS ~ f(K) (the density value at the strike).

    For each market with strike K_i and signed position q_i:
        delta_i = q_i * f(K_i)

    Portfolio delta = sum(delta_i).

    The density is estimated from the survival curve via finite
    differences: f(K_i) ~ -(survival[i+1] - survival[i-1]) / (K[i+1] - K[i-1]).

    Args:
        positions: Kalshi position store.
        bucket_prices: RND-derived bucket prices with survival curve.
        event_ticker: Event ticker to filter positions by.

    Returns:
        Aggregate portfolio delta (positive = long underlying exposure).

    Raises:
        ValueError: If bucket_prices has insufficient strikes.
    """
    strikes = bucket_prices.kalshi_strikes
    survival = bucket_prices.survival

    if strikes.shape[0] < 2:
        raise ValueError(
            f"Need at least 2 strikes for delta computation, got {strikes.shape[0]}"
        )

    # Compute density at each strike via central finite differences
    density = _compute_density(strikes, survival)

    # Build strike -> density lookup
    strike_to_density: dict[float, float] = {}
    for i in range(len(strikes)):
        strike_to_density[float(strikes[i])] = density[i]

    # Sum delta contributions from all positions in this event
    snap = positions.snapshot()
    total_delta = 0.0

    for ticker, pos in snap.items():
        if pos.event_ticker != event_ticker:
            continue
        if pos.signed_qty == 0:
            continue

        # Extract strike from market ticker (last component after '-')
        strike = _extract_strike(ticker)
        if strike is None:
            continue

        # Find closest strike in the bucket grid
        d = strike_to_density.get(strike)
        if d is None:
            # Find nearest
            idx = int(np.argmin(np.abs(strikes - strike)))
            d = density[idx]

        total_delta += pos.signed_qty * d

    return total_delta


def _compute_density(
    strikes: np.ndarray,
    survival: np.ndarray,
) -> np.ndarray:
    """Compute density at each strike via finite differences.

    density[i] = -(survival[i+1] - survival[i-1]) / (strikes[i+1] - strikes[i-1])

    At boundaries, use one-sided differences.

    Returns:
        Array of density values, same length as strikes.
    """
    n = len(strikes)
    density = np.empty(n)

    # Forward difference at left boundary
    if n >= 2:
        density[0] = -(survival[1] - survival[0]) / (strikes[1] - strikes[0])

    # Central differences for interior points
    for i in range(1, n - 1):
        density[i] = -(survival[i + 1] - survival[i - 1]) / (strikes[i + 1] - strikes[i - 1])

    # Backward difference at right boundary
    if n >= 2:
        density[-1] = -(survival[-1] - survival[-2]) / (strikes[-1] - strikes[-2])

    # Density should be non-negative; clamp any small negatives from FP noise
    np.maximum(density, 0.0, out=density)

    return density


def _extract_strike(market_ticker: str) -> float | None:
    """Extract the numeric strike from a market ticker.

    E.g. "KXSOYBEANMON-26MAY01-1050" -> 10.50 (cents to dollars)
    or the strike is already in the expected units.

    Returns None if the ticker format is unexpected.
    """
    parts = market_ticker.rsplit("-", 1)
    if len(parts) != 2:
        return None
    try:
        return float(parts[1])
    except ValueError:
        return None
