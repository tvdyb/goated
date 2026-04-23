"""Per-commodity trading-hours calendar.

`τ = tau_years(commodity, now_ns, settle_ns)` returns the time between
`now` and the Kalshi settle in trading-time years, per the commodity's
session schedule. Calendar time is wrong here — WTI closes weekends, gold
has a maintenance halt, ags have short electronic sessions — and a biased
τ biases every theo that uses it.

Deliverable 1 supports WTI only. Other commodities register as they come
online. If the calendar has no schedule for a commodity, `tau_years` raises
rather than silently falling back to calendar time.

WTI session model (deliverable 1):
  * Sunday 18:00 ET → Friday 17:00 ET continuous
  * 60-minute daily halt 17:00–18:00 ET on Mon, Tue, Wed, Thu
  * Closed Friday 17:00 ET → Sunday 18:00 ET
  * 5796 trading hours per year (252 × 23 h/day)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SECONDS_PER_TRADING_YEAR_WTI = 252 * 23 * 3600

# Per-weekday trading windows in ET, as (start_hour, start_min, end_hour, end_min).
# Weekdays are 0=Mon ... 6=Sun.
_WTI_WINDOWS: dict[int, list[tuple[int, int, int, int]]] = {
    0: [(0, 0, 17, 0), (18, 0, 24, 0)],    # Mon
    1: [(0, 0, 17, 0), (18, 0, 24, 0)],    # Tue
    2: [(0, 0, 17, 0), (18, 0, 24, 0)],    # Wed
    3: [(0, 0, 17, 0), (18, 0, 24, 0)],    # Thu
    4: [(0, 0, 17, 0)],                    # Fri: closes 17:00 ET, no evening session
    5: [],                                 # Sat: closed
    6: [(18, 0, 24, 0)],                   # Sun: opens 18:00 ET
}


def _window_endpoints(day_et: datetime, w: tuple[int, int, int, int]) -> tuple[datetime, datetime]:
    """Resolve a window tuple to (start_et, end_et) on the given calendar day."""
    start = day_et.replace(hour=w[0], minute=w[1], second=0, microsecond=0)
    if w[2] >= 24:
        end = day_et.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        end = day_et.replace(hour=w[2], minute=w[3], second=0, microsecond=0)
    return start, end


def _wti_trading_seconds(start_et: datetime, end_et: datetime) -> float:
    if end_et <= start_et:
        return 0.0
    total = 0.0
    day = start_et.replace(hour=0, minute=0, second=0, microsecond=0)
    stop = end_et  # half-open [start_et, end_et)
    # Walk calendar days until the day start overtakes end.
    while day < stop:
        for win in _WTI_WINDOWS[day.weekday()]:
            win_start, win_end = _window_endpoints(day, win)
            lo = max(win_start, start_et)
            hi = min(win_end, stop)
            if hi > lo:
                total += (hi - lo).total_seconds()
        day = day + timedelta(days=1)
    return total


class TradingCalendar:
    """Per-commodity trading-hour τ calculator.

    For deliverable 1, only `wti` has a schedule. Callers must ensure the
    commodity they ask about is registered; otherwise `tau_years` raises.
    """

    def __init__(self) -> None:
        self._handlers = {
            "wti": (_wti_trading_seconds, _SECONDS_PER_TRADING_YEAR_WTI),
        }

    def tau_years(self, commodity: str, now_ns: int, settle_ns: int) -> float:
        if commodity not in self._handlers:
            raise NotImplementedError(
                f"{commodity}: trading calendar not yet implemented"
            )
        if settle_ns <= now_ns:
            return 0.0
        fn, seconds_per_year = self._handlers[commodity]
        now_et = datetime.fromtimestamp(now_ns / 1e9, tz=_ET)
        settle_et = datetime.fromtimestamp(settle_ns / 1e9, tz=_ET)
        seconds = fn(now_et, settle_et)
        return seconds / seconds_per_year

    def supports(self, commodity: str) -> bool:
        return commodity in self._handlers
