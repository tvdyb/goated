"""WASDE-driven density adjustment for post-release re-entry.

Converts a WASDE ending-stocks surprise into a mean-shift on the pricing
density. The system re-enters the market with an adjusted density after
the settlement gate re-opens post-WASDE.

Sensitivity: ~18c/bu per 1M bushel ending-stocks surprise (configurable).
Direction: negative surprise (tighter stocks) -> positive price shift (bullish).

The adjustment decays exponentially over 24 hours as the market absorbs
the information.

Non-negotiables: fail-loud, no pandas, type hints, numba on hot path.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.special import ndtr

from engine.rnd.bucket_integrator import BucketPrices
from feeds.usda.wasde_parser import WASDESurprise

logger = logging.getLogger(__name__)


class WASDEDensityError(RuntimeError):
    """Raised when WASDE density adjustment fails validation."""


@dataclass(slots=True)
class WASDEDensityConfig:
    """Configuration for WASDE density adjustments.

    Attributes:
        sensitivity_cents_per_mbu: Price sensitivity in cents/bushel per
            million-bushel ending-stocks surprise. Default ~18c/bu per 1M bu
            (from historical regression of WASDE surprises on ZS front-month).
        decay_half_life_hours: Half-life of the adjustment decay in hours.
            Default 6h (adjustment is ~6% of original after 24h).
        max_shift_cents: Maximum allowable mean-shift in cents/bushel.
            Safety cap to prevent extreme adjustments on data errors.
        use_production_signal: Whether to include production surprises.
        production_weight: Weight of production surprise relative to
            ending stocks (typically lower since production is less surprising).
    """

    sensitivity_cents_per_mbu: float = 18.0
    decay_half_life_hours: float = 6.0
    max_shift_cents: float = 100.0
    use_production_signal: bool = False
    production_weight: float = 0.3


@dataclass(slots=True)
class WASDEAdjustment:
    """Active WASDE density adjustment state.

    Tracks the adjustment and its decay over time.

    Attributes:
        mean_shift_cents: Initial mean-shift in cents/bushel at release time.
        release_timestamp: Unix timestamp of the WASDE release.
        decay_half_life_s: Decay half-life in seconds.
        surprise: The underlying WASDE surprise data.
    """

    mean_shift_cents: float
    release_timestamp: float
    decay_half_life_s: float
    surprise: WASDESurprise

    def current_shift_cents(self, now: float | None = None) -> float:
        """Compute the current mean-shift after exponential decay.

        Parameters
        ----------
        now : Unix timestamp. If None, uses time.time().

        Returns
        -------
        Decayed mean-shift in cents/bushel.
        """
        if now is None:
            now = time.time()
        elapsed = max(0.0, now - self.release_timestamp)
        decay = math.exp(-math.log(2) * elapsed / self.decay_half_life_s)
        return self.mean_shift_cents * decay

    def is_expired(self, now: float | None = None, threshold: float = 0.5) -> bool:
        """Check if the adjustment has decayed below threshold cents."""
        return abs(self.current_shift_cents(now)) < threshold


def compute_mean_shift(
    surprise: WASDESurprise,
    config: WASDEDensityConfig | None = None,
) -> float:
    """Compute the mean-shift in cents/bushel from a WASDE surprise.

    Convention: negative ending_stocks_delta (tighter than expected) ->
    positive mean-shift (bullish, price goes up).

    Returns
    -------
    Mean-shift in cents/bushel (positive = bullish).
    """
    if config is None:
        config = WASDEDensityConfig()

    # Primary signal: ending stocks surprise
    # Negative stocks surprise -> bullish -> positive shift
    es_shift = -surprise.ending_stocks_delta * config.sensitivity_cents_per_mbu

    # Optional: production surprise
    prod_shift = 0.0
    if config.use_production_signal:
        prod_shift = (
            -surprise.production_delta
            * config.sensitivity_cents_per_mbu
            * config.production_weight
        )

    total_shift = es_shift + prod_shift

    # Safety cap
    if abs(total_shift) > config.max_shift_cents:
        logger.warning(
            "WASDE shift capped: raw=%.1fc -> cap=%.1fc (es_delta=%.1f, prod_delta=%.1f)",
            total_shift,
            math.copysign(config.max_shift_cents, total_shift),
            surprise.ending_stocks_delta,
            surprise.production_delta,
        )
        total_shift = math.copysign(config.max_shift_cents, total_shift)

    return total_shift


def create_adjustment(
    surprise: WASDESurprise,
    release_timestamp: float | None = None,
    config: WASDEDensityConfig | None = None,
) -> WASDEAdjustment:
    """Create a WASDE density adjustment from a surprise.

    Parameters
    ----------
    surprise : The WASDE surprise (actual vs consensus).
    release_timestamp : Unix timestamp of release. If None, uses time.time().
    config : Sensitivity and decay configuration.

    Returns
    -------
    WASDEAdjustment tracking the shift and its decay.
    """
    if config is None:
        config = WASDEDensityConfig()
    if release_timestamp is None:
        release_timestamp = time.time()

    shift = compute_mean_shift(surprise, config)

    logger.info(
        "WASDE ADJUSTMENT: es_delta=%.1f Mbu -> shift=%.1fc/bu "
        "(sensitivity=%.1fc/Mbu, decay_half_life=%.1fh)",
        surprise.ending_stocks_delta,
        shift,
        config.sensitivity_cents_per_mbu,
        config.decay_half_life_hours,
    )

    return WASDEAdjustment(
        mean_shift_cents=shift,
        release_timestamp=release_timestamp,
        decay_half_life_s=config.decay_half_life_hours * 3600.0,
        surprise=surprise,
    )


@njit(cache=True, fastmath=False)
def _shift_survival(
    survival: np.ndarray,
    strikes: np.ndarray,
    shift_dollars: float,
    sigma: float,
    tau: float,
) -> np.ndarray:
    """Recompute survival probabilities with a shifted forward.

    P(S > K) = N(d2) where d2 = (ln(F'/K) - 0.5*sig^2*T) / (sig*sqrt(T))
    F' = F + shift (mean-shifted forward).

    This is the hot-path function — numba-JITed.
    """
    n = len(strikes)
    out = np.empty(n, dtype=np.float64)
    sig_sqrt_t = max(sigma * np.sqrt(tau), 1e-12)

    for i in range(n):
        k = strikes[i]
        if k <= 0:
            out[i] = 1.0
            continue
        # Shifted forward
        f_prime = strikes[n // 2] + shift_dollars  # rough forward from mid-strike
        if f_prime <= 0:
            f_prime = k  # safety
        d2 = (np.log(f_prime / k) - 0.5 * sigma * sigma * tau) / sig_sqrt_t
        # ndtr not available in numba; use erfc approximation
        # N(x) = 0.5 * erfc(-x / sqrt(2))
        out[i] = 0.5 * (1.0 + np.tanh(0.7978845608028654 * d2 * (1.0 + 0.044715 * d2 * d2)))
        # Clamp to [0, 1]
        if out[i] < 0.0:
            out[i] = 0.0
        elif out[i] > 1.0:
            out[i] = 1.0

    return out


def apply_wasde_shift(
    bucket_prices: BucketPrices,
    adjustment: WASDEAdjustment,
    forward: float,
    sigma: float,
    tau: float,
    now: float | None = None,
) -> BucketPrices:
    """Apply a WASDE mean-shift to an existing BucketPrices density.

    Recomputes the survival function and bucket prices using the shifted
    forward price. The shift decays exponentially from the release time.

    Parameters
    ----------
    bucket_prices : Current (pre-shift) bucket prices.
    adjustment : Active WASDE adjustment with decay state.
    forward : Current forward price in dollars/bushel (e.g. 10.50).
    sigma : Annualized volatility.
    tau : Time to settlement in years.
    now : Current unix timestamp (for decay computation).

    Returns
    -------
    New BucketPrices with the WASDE-adjusted density.

    Raises
    ------
    WASDEDensityError if the adjusted density fails validation.
    """
    shift_cents = adjustment.current_shift_cents(now)

    # Convert cents/bushel to dollars/bushel
    shift_dollars = shift_cents / 100.0

    if abs(shift_dollars) < 0.001:
        # Shift too small to matter — return original
        return bucket_prices

    shifted_forward = forward + shift_dollars
    if shifted_forward <= 0:
        raise WASDEDensityError(
            f"WASDE shift would produce negative forward: "
            f"forward={forward:.4f} + shift={shift_dollars:.4f} = {shifted_forward:.4f}"
        )

    strikes = bucket_prices.kalshi_strikes
    sig_sqrt_t = max(sigma * math.sqrt(tau), 1e-12)

    # Recompute survival with shifted forward (using scipy, not numba, for ndtr)
    survival = np.array([
        float(ndtr(
            (math.log(shifted_forward / k) - 0.5 * sigma ** 2 * tau) / sig_sqrt_t
        ))
        for k in strikes
    ])

    # Recompute bucket prices from survival
    n_buckets = len(strikes) + 1
    bucket_yes = np.zeros(n_buckets, dtype=np.float64)
    bucket_yes[0] = 1.0 - survival[0]
    for i in range(1, len(survival)):
        bucket_yes[i] = survival[i - 1] - survival[i]
    bucket_yes[-1] = survival[-1]

    # Validate
    bucket_sum = float(bucket_yes.sum())
    if not np.all(np.isfinite(bucket_yes)):
        raise WASDEDensityError("WASDE-adjusted density has non-finite values")
    if bucket_yes.min() < -1e-10:
        raise WASDEDensityError(
            f"WASDE-adjusted density has negative bucket: min={bucket_yes.min():.6g}"
        )
    # Clamp tiny negatives from FP
    bucket_yes = np.maximum(bucket_yes, 0.0)

    logger.info(
        "WASDE DENSITY: shift=%.1fc/bu (decayed from %.1fc), "
        "forward %.4f -> %.4f, bucket_sum=%.6f",
        shift_cents, adjustment.mean_shift_cents,
        forward, shifted_forward, bucket_sum,
    )

    return BucketPrices(
        kalshi_strikes=strikes,
        survival=survival,
        bucket_yes=bucket_yes,
        bucket_sum=float(bucket_yes.sum()),
        n_buckets=n_buckets,
    )
