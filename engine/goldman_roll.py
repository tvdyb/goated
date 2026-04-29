"""Goldman Sachs Commodity Index (GSCI) roll window detection.

The GSCI roll occurs on the 5th through 9th business day of each month.
During this window, index-tracking funds sell front-month futures and buy
deferred contracts, creating predictable downward pressure on the front
month (ZS for soybeans).

When the roll window overlaps a Kalshi settlement window, the density
mean should be adjusted for the expected roll-driven drift.

Business days are NYSE/CBOT business days (weekdays excluding CBOT
holidays). The roll window is deterministic and requires no external API.
"""

from __future__ import annotations

from datetime import date, timedelta

from engine.event_calendar import _CBOT_HOLIDAYS, _HOLIDAY_RANGE_END, _HOLIDAY_RANGE_START


def _nth_business_day(year: int, month: int, n: int) -> date:
    """Return the nth CBOT business day of the given month (1-indexed).

    Raises ValueError if the date is outside the maintained holiday range
    or if n exceeds the number of business days in the month.
    """
    d = date(year, month, 1)
    if d < _HOLIDAY_RANGE_START or d > _HOLIDAY_RANGE_END:
        raise ValueError(
            f"_nth_business_day: {year}-{month:02d} is outside maintained "
            f"holiday range [{_HOLIDAY_RANGE_START}, {_HOLIDAY_RANGE_END}]. "
            f"Update _CBOT_HOLIDAYS to extend coverage."
        )
    count = 0
    while True:
        if d.weekday() < 5 and d not in _CBOT_HOLIDAYS:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)
        if d.month != month:
            raise ValueError(
                f"Month {year}-{month:02d} has fewer than {n} business days"
            )


def roll_window(year: int, month: int) -> tuple[date, date]:
    """Return (start, end) inclusive dates of the Goldman roll window.

    The roll window spans the 5th through 9th CBOT business day of the
    given month.
    """
    return _nth_business_day(year, month, 5), _nth_business_day(year, month, 9)


def is_in_roll_window(d: date) -> bool:
    """Return True if the given date falls within the Goldman roll window.

    Raises ValueError if the date is outside the maintained holiday range.
    """
    start, end = roll_window(d.year, d.month)
    return start <= d <= end


def roll_drift_cents(d: date) -> float:
    """Expected downward pressure in cents during the Goldman roll.

    Returns a negative value (sell pressure on front month) during the
    roll window, tapering from -2c at the edges to -5c at the midpoint.
    Returns 0.0 outside the window.

    The profile is a simple triangular ramp: drift peaks at the center
    of the 5-day window and tapers linearly toward the edges.
    """
    start, end = roll_window(d.year, d.month)
    if d < start or d > end:
        return 0.0

    # Triangular profile: peak at midpoint
    total_days = (end - start).days
    if total_days == 0:
        return -3.5  # degenerate case: single-day window

    progress = (d - start).days / total_days  # 0.0 at start, 1.0 at end
    # Triangle: 0->1->0 mapped to -2 -> -5 -> -2
    triangle = 1.0 - abs(2.0 * progress - 1.0)  # 0 at edges, 1 at center
    return -2.0 - 3.0 * triangle  # -2c at edges, -5c at center
