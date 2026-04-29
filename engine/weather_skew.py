"""Weather-driven distribution skew for soybean pricing.

Maps NOAA CPC weather anomalies to pricing adjustments:
  - mean_shift_cents: upward/downward shift in soybean forward price
  - vol_adjustment_pct: multiplicative volatility scaling (e.g. 0.10 = +10%)

Active windows (growing season only):
  - U.S. pod-fill: June 1 - August 31
  - South American pod-fill: January 1 - February 28/29

Outside these windows, returns (0.0, 0.0) — no weather effect.

Mapping logic (from research synthesis section 2.1):
  Hot + dry during pod-fill → negative yield shock → price UP + tail UP
  Cool + wet → positive yield → price DOWN, tails NARROW

The 2012 drought produced limit-up sequences when temp was +8F above normal
with precip at -60% during July pod-fill.

Fail-loud: raises on non-finite inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import NamedTuple

from feeds.weather.gefs_client import WeatherOutlook


class GrowingSeason(StrEnum):
    US_POD_FILL = "us_pod_fill"  # Jun-Aug
    SA_POD_FILL = "sa_pod_fill"  # Jan-Feb
    OFF_SEASON = "off_season"


class WeatherSkewResult(NamedTuple):
    """Output of weather skew computation."""

    mean_shift_cents: float  # cents to add to forward (positive = price up)
    vol_adjustment_pct: float  # multiplicative vol scaling (0.10 = +10%)


# ---------------------------------------------------------------------------
# Season detection
# ---------------------------------------------------------------------------

_US_POD_FILL_MONTHS = {6, 7, 8}  # Jun, Jul, Aug
_SA_POD_FILL_MONTHS = {1, 2}  # Jan, Feb


def detect_growing_season(as_of: date) -> GrowingSeason:
    """Determine which growing season is active for the given date."""
    month = as_of.month
    if month in _US_POD_FILL_MONTHS:
        return GrowingSeason.US_POD_FILL
    if month in _SA_POD_FILL_MONTHS:
        return GrowingSeason.SA_POD_FILL
    return GrowingSeason.OFF_SEASON


# ---------------------------------------------------------------------------
# Skew mapping parameters
# ---------------------------------------------------------------------------

# Sensitivity coefficients calibrated from historical USDA crop-condition
# vs price-response data (2010-2023).
#
# U.S. pod-fill is the dominant driver (70% of global soybean yield impact).
# S. America pod-fill has a smaller but still material effect.

@dataclass(frozen=True, slots=True)
class SkewParams:
    """Tunable parameters for weather-to-price mapping."""

    # Cents of forward shift per degree F of temp anomaly during pod-fill.
    # Hot = positive anomaly = positive shift (price UP).
    # Historical: 2012 drought (+8F) moved beans ~300c in a month.
    # Conservative linear mapping: ~5c per 1F anomaly.
    temp_shift_cents_per_f: float = 5.0

    # Additional cents of forward shift per 1% precipitation deficit.
    # Dry = negative precip anomaly = positive shift (price UP).
    # A 30% precip deficit during pod-fill adds ~30c historically.
    precip_shift_cents_per_pct: float = -1.0  # negative because deficit is negative

    # Vol scaling per degree F of temp anomaly (absolute value).
    # Hot/dry widens tails; cool/wet narrows.
    # A +5F anomaly might add ~15% vol -> 0.03 per F.
    temp_vol_pct_per_f: float = 0.03

    # Vol scaling per 1% precip deficit (absolute value).
    # Dry = negative precip anomaly = wider tails.
    precip_vol_pct_per_pct: float = -0.005  # negative because deficit widens

    # Dampening factor for S. America relative to U.S. pod-fill.
    sa_dampening: float = 0.5

    # Maximum absolute shift to prevent runaway in extreme outlooks.
    max_shift_cents: float = 80.0
    max_vol_adjustment_pct: float = 0.50  # cap at +/-50% vol scaling


_DEFAULT_PARAMS = SkewParams()


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_weather_skew(
    outlook: WeatherOutlook,
    as_of: date | None = None,
    *,
    params: SkewParams = _DEFAULT_PARAMS,
) -> WeatherSkewResult:
    """Map a weather outlook to pricing adjustments.

    Parameters
    ----------
    outlook : WeatherOutlook
        Temperature and precipitation anomalies from CPC.
    as_of : date, optional
        Date to check growing season. Defaults to today.
    params : SkewParams
        Tunable coefficients.

    Returns
    -------
    WeatherSkewResult
        (mean_shift_cents, vol_adjustment_pct). Both 0.0 if off-season.

    Raises
    ------
    ValueError
        If outlook contains non-finite values.
    """
    if not math.isfinite(outlook.temp_anomaly_f):
        raise ValueError(
            f"temp_anomaly_f must be finite, got {outlook.temp_anomaly_f}"
        )
    if not math.isfinite(outlook.precip_anomaly_pct):
        raise ValueError(
            f"precip_anomaly_pct must be finite, got {outlook.precip_anomaly_pct}"
        )

    if as_of is None:
        as_of = date.today()

    season = detect_growing_season(as_of)
    if season == GrowingSeason.OFF_SEASON:
        return WeatherSkewResult(mean_shift_cents=0.0, vol_adjustment_pct=0.0)

    dampening = params.sa_dampening if season == GrowingSeason.SA_POD_FILL else 1.0

    # Mean shift: hot + dry = price up
    # temp_anomaly_f > 0 means warmer -> yield risk -> price up
    # precip_anomaly_pct < 0 means drier -> yield risk -> price up
    temp_shift = outlook.temp_anomaly_f * params.temp_shift_cents_per_f
    precip_shift = outlook.precip_anomaly_pct * params.precip_shift_cents_per_pct
    raw_shift = (temp_shift + precip_shift) * dampening

    # Vol adjustment: stress increases vol, benign decreases
    # Hot/dry = wider tails (positive vol adj)
    # Cool/wet = narrower tails (negative vol adj)
    temp_vol = outlook.temp_anomaly_f * params.temp_vol_pct_per_f
    precip_vol = outlook.precip_anomaly_pct * params.precip_vol_pct_per_pct
    raw_vol = (temp_vol + precip_vol) * dampening

    # Clamp to prevent extreme skew
    shift = max(-params.max_shift_cents, min(params.max_shift_cents, raw_shift))
    vol_adj = max(
        -params.max_vol_adjustment_pct,
        min(params.max_vol_adjustment_pct, raw_vol),
    )

    return WeatherSkewResult(
        mean_shift_cents=shift,
        vol_adjustment_pct=vol_adj,
    )


def apply_weather_skew(
    forward: float,
    sigma: float,
    skew: WeatherSkewResult,
) -> tuple[float, float]:
    """Apply weather skew to forward price and volatility.

    Parameters
    ----------
    forward : float
        Current forward price in cents.
    sigma : float
        Current annualized volatility (e.g. 0.15 for 15%).
    skew : WeatherSkewResult
        Output of compute_weather_skew().

    Returns
    -------
    (adjusted_forward, adjusted_sigma)

    Raises
    ------
    ValueError
        If forward or sigma is non-positive or non-finite.
    """
    if not (forward > 0.0) or not math.isfinite(forward):
        raise ValueError(f"forward must be finite and > 0, got {forward}")
    if not (sigma > 0.0) or not math.isfinite(sigma):
        raise ValueError(f"sigma must be finite and > 0, got {sigma}")

    adjusted_forward = forward + skew.mean_shift_cents
    if adjusted_forward <= 0.0:
        raise ValueError(
            f"Weather skew pushed forward to {adjusted_forward:.2f} "
            f"(original {forward:.2f}, shift {skew.mean_shift_cents:.2f}). "
            f"Refusing to price with non-positive forward."
        )

    adjusted_sigma = sigma * (1.0 + skew.vol_adjustment_pct)
    if adjusted_sigma <= 0.0:
        raise ValueError(
            f"Weather skew pushed sigma to {adjusted_sigma:.4f} "
            f"(original {sigma:.4f}, adj {skew.vol_adjustment_pct:.4f}). "
            f"Refusing to price with non-positive vol."
        )

    return adjusted_forward, adjusted_sigma
