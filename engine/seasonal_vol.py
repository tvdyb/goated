"""Seasonal volatility regime overlay for soybeans.

Soybean vol follows a well-documented seasonal pattern driven by
U.S. pod-fill weather risk (Jun-Aug peak) and South American growing
season (Jan-Feb). This module provides monthly (floor, ceiling) bounds
used to clamp Kalshi-implied vol calibration and as a fallback prior
when the orderbook is too thin to calibrate.

Reference: CME "Vol is High by the Fourth of July" seasonal pattern.
"""

from __future__ import annotations

# Monthly (floor, ceiling) annualized vol for soybeans.
# Key: month number (1=Jan, 12=Dec).
_SOYBEAN_VOL_REGIME: dict[int, tuple[float, float]] = {
    1:  (0.14, 0.18),  # moderate — South American watch begins
    2:  (0.15, 0.20),  # SA pod-fill window
    3:  (0.14, 0.18),  # moderate
    4:  (0.16, 0.20),  # rising — planting intentions
    5:  (0.16, 0.20),  # rising — planting underway
    6:  (0.20, 0.30),  # peak — U.S. pod-fill weather risk
    7:  (0.20, 0.30),  # peak
    8:  (0.20, 0.30),  # peak
    9:  (0.15, 0.20),  # declining post-harvest
    10: (0.15, 0.20),  # declining
    11: (0.12, 0.16),  # quiet
    12: (0.12, 0.16),  # quiet
}


def get_seasonal_vol_bounds(month: int) -> tuple[float, float]:
    """Return (vol_floor, vol_ceiling) for a given calendar month.

    Args:
        month: Calendar month (1-12).

    Returns:
        (floor, ceiling) annualized vol.

    Raises:
        ValueError: If month is not in 1-12.
    """
    if month < 1 or month > 12:
        raise ValueError(f"month must be 1-12, got {month}")
    return _SOYBEAN_VOL_REGIME[month]


def get_seasonal_vol_midpoint(month: int) -> float:
    """Return the midpoint of the seasonal vol regime for a given month.

    Used as the fallback vol when Kalshi calibration fails (replaces
    the flat 15% default).

    Args:
        month: Calendar month (1-12).

    Returns:
        Midpoint of (floor, ceiling) annualized vol.

    Raises:
        ValueError: If month is not in 1-12.
    """
    floor, ceiling = get_seasonal_vol_bounds(month)
    return (floor + ceiling) / 2.0


def clamp_vol(vol: float, month: int) -> float:
    """Clamp a calibrated vol to the seasonal regime bounds.

    Args:
        vol: Calibrated annualized vol.
        month: Calendar month (1-12).

    Returns:
        Vol clamped to [floor, ceiling] for the given month.

    Raises:
        ValueError: If month is not in 1-12.
    """
    floor, ceiling = get_seasonal_vol_bounds(month)
    if vol < floor:
        return floor
    if vol > ceiling:
        return ceiling
    return vol
