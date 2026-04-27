"""Index reconstruction for the Truflation AI & DePIN Index.

Truflation publishes the index level periodically. We need its live
value between publishes, so we hold token quantities `n_i` such that

    I(t) = sum_i n_i * P_i(t)

and recompute on every price tick. The quantities are calibrated once
from a known anchor (timestamp t0, published index level I0, prices
P_i(t0), target weights w_i):

    n_i = w_i * I0 / P_i(t0)

so that at the anchor sum(n_i * P_i(t0)) == I0 exactly. Caps on the
target weights (Truflation caps any single name at 25%) are enforced
upstream when w_i are chosen — this module only does the arithmetic.
"""

from __future__ import annotations

import numpy as np


def calibrate_quantities(
    index_value: float,
    prices: dict[str, float],
    target_weights: dict[str, float],
) -> dict[str, float]:
    if index_value <= 0:
        raise ValueError(f"index_value must be > 0, got {index_value}")
    missing = set(target_weights) - set(prices)
    if missing:
        raise ValueError(f"missing prices for: {sorted(missing)}")
    w_sum = sum(target_weights.values())
    if not (0.999 < w_sum < 1.001):
        raise ValueError(f"target_weights must sum to 1.0, got {w_sum:.6f}")
    return {sym: w * index_value / prices[sym] for sym, w in target_weights.items()}


def reconstruct(
    quantities: dict[str, float],
    prices: dict[str, float],
) -> float:
    missing = set(quantities) - set(prices)
    if missing:
        raise ValueError(f"missing prices for: {sorted(missing)}")
    return sum(quantities[sym] * prices[sym] for sym in quantities)


def stack_arrays(
    symbols: list[str],
    quantities: dict[str, float],
    prices: dict[str, float],
    sigmas: dict[str, float],
    correlation: list[list[float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pack per-symbol dicts into arrays in the canonical `symbols` order
    so the basket-GBM kernel can consume them without per-call dict lookups."""
    n = len(symbols)
    q = np.array([quantities[s] for s in symbols], dtype=np.float64)
    p = np.array([prices[s] for s in symbols], dtype=np.float64)
    s = np.array([sigmas[s] for s in symbols], dtype=np.float64)
    c = np.asarray(correlation, dtype=np.float64)
    if c.shape != (n, n):
        raise ValueError(f"correlation must be {n}x{n}, got {c.shape}")
    return q, p, s, c
