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

Soybean / KXSOYBEANW session model (ACT-07):
  * 24/7 including weekends (Kalshi commodities hub, launched Apr 15 2026)
  * τ = pure calendar time; every second counts
  * 365.25 × 24 × 3600 seconds per trading year

Friday-holiday Rule 7.2(b) (ACT-07):
  * When settlement Friday is a CBOT holiday, settlement rolls to the
    next CBOT trading day (next non-weekend, non-holiday weekday).
  * Holiday set must be explicitly maintained; raises on unmaintained range.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_SECONDS_PER_TRADING_YEAR_WTI = 252 * 23 * 3600
_SECONDS_PER_CALENDAR_YEAR = 365.25 * 24 * 3600  # 24/7 products

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


# ---------------------------------------------------------------------------
# Soybean / KXSOYBEANW — 24/7 session (GAP-087)
# ---------------------------------------------------------------------------

def _soy_trading_seconds(start_et: datetime, end_et: datetime) -> float:
    """24/7 session: every calendar second is a trading second."""
    if end_et <= start_et:
        return 0.0
    return (end_et - start_et).total_seconds()


# ---------------------------------------------------------------------------
# CBOT holidays + Rule 7.2(b) Friday-holiday settlement roll (GAP-089)
# ---------------------------------------------------------------------------

# CBOT observed holidays for maintained years. Sourced from CME Group
# holiday schedule. Includes: New Year's Day, MLK Day, Presidents' Day,
# Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day,
# Thanksgiving Day, Christmas Day.
# When a holiday falls on Saturday it is observed on the preceding Friday;
# when it falls on Sunday it is observed on the following Monday.
_CBOT_HOLIDAYS: frozenset[date] = frozenset([
    # --- 2026 ---
    date(2026, 1, 1),   # New Year's Day (Thu)
    date(2026, 1, 19),  # MLK Day (Mon)
    date(2026, 2, 16),  # Presidents' Day (Mon)
    date(2026, 4, 3),   # Good Friday (Fri)
    date(2026, 5, 25),  # Memorial Day (Mon)
    date(2026, 6, 19),  # Juneteenth (Fri)
    date(2026, 7, 3),   # Independence Day observed (Fri; Jul 4 is Sat)
    date(2026, 9, 7),   # Labor Day (Mon)
    date(2026, 11, 26), # Thanksgiving (Thu)
    date(2026, 12, 25), # Christmas (Fri)
    # --- 2027 ---
    date(2027, 1, 1),   # New Year's Day (Fri)
    date(2027, 1, 18),  # MLK Day (Mon)
    date(2027, 2, 15),  # Presidents' Day (Mon)
    date(2027, 3, 26),  # Good Friday (Fri)
    date(2027, 5, 31),  # Memorial Day (Mon)
    date(2027, 6, 18),  # Juneteenth observed (Fri; Jun 19 is Sat)
    date(2027, 7, 5),   # Independence Day observed (Mon; Jul 4 is Sun)
    date(2027, 9, 6),   # Labor Day (Mon)
    date(2027, 11, 25), # Thanksgiving (Thu)
    date(2027, 12, 24), # Christmas observed (Fri; Dec 25 is Sat)
])

# Maintained range: raise on queries outside this range (fail-loud).
_HOLIDAY_RANGE_START = date(2026, 1, 1)
_HOLIDAY_RANGE_END = date(2027, 12, 31)


def _is_cbot_trading_day(d: date) -> bool:
    """True if d is a CBOT trading day (weekday and not a CBOT holiday)."""
    return d.weekday() < 5 and d not in _CBOT_HOLIDAYS


def settle_date_roll(nominal: date) -> date:
    """Apply Rule 7.2(b): if the nominal settlement date (typically a Friday)
    falls on a CBOT holiday, roll forward to the next CBOT trading day.

    Raises ValueError if the date is outside the maintained holiday range.
    """
    if nominal < _HOLIDAY_RANGE_START or nominal > _HOLIDAY_RANGE_END:
        raise ValueError(
            f"settle_date_roll: {nominal} is outside maintained holiday range "
            f"[{_HOLIDAY_RANGE_START}, {_HOLIDAY_RANGE_END}]. "
            f"Update _CBOT_HOLIDAYS to extend coverage."
        )
    rolled = nominal
    while not _is_cbot_trading_day(rolled):
        rolled += timedelta(days=1)
    return rolled


class TradingCalendar:
    """Per-commodity trading-hour τ calculator.

    For deliverable 1, only `wti` has a schedule. Callers must ensure the
    commodity they ask about is registered; otherwise `tau_years` raises.
    """

    def __init__(self) -> None:
        self._handlers = {
            "wti": (_wti_trading_seconds, _SECONDS_PER_TRADING_YEAR_WTI),
            "soy": (_soy_trading_seconds, _SECONDS_PER_CALENDAR_YEAR),
        }

    def register_handler(
        self,
        commodity: str,
        trading_seconds_fn,
        seconds_per_trading_year: float,
    ) -> None:
        """Add a commodity's session schedule. Called by later deliverables as
        brent/gold/copper/etc. calendars come online. Also used by benchmarks
        to stand up a 50-market synthetic book."""
        if seconds_per_trading_year <= 0.0:
            raise ValueError(
                f"{commodity}: seconds_per_trading_year must be > 0, got {seconds_per_trading_year}"
            )
        self._handlers[commodity] = (trading_seconds_fn, seconds_per_trading_year)

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
