"""WTI trading calendar — sessional τ calculation."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from engine.event_calendar import TradingCalendar

ET = ZoneInfo("America/New_York")


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def test_weekend_contributes_zero_hours():
    cal = TradingCalendar()
    # Friday 18:00 ET (post-close) to Sunday 17:30 ET — entirely closed
    start = _ns(datetime(2026, 4, 24, 18, 0, tzinfo=ET))  # Fri
    end = _ns(datetime(2026, 4, 26, 17, 30, tzinfo=ET))   # Sun 17:30 (pre-18:00 open)
    assert cal.tau_years("wti", start, end) == 0.0


def test_full_weekday_counts_23_hours():
    cal = TradingCalendar()
    # Monday 00:00 ET to Tuesday 00:00 ET: one full weekday = 23 hrs
    start = _ns(datetime(2026, 4, 20, 0, 0, tzinfo=ET))
    end = _ns(datetime(2026, 4, 21, 0, 0, tzinfo=ET))
    tau = cal.tau_years("wti", start, end)
    expected = 23.0 * 3600.0 / (252.0 * 23.0 * 3600.0)
    assert tau == pytest.approx(expected, rel=1e-12)


def test_daily_halt_removed():
    cal = TradingCalendar()
    # Monday 17:00 ET to Monday 18:00 ET: daily halt, 0 hrs
    start = _ns(datetime(2026, 4, 20, 17, 0, tzinfo=ET))
    end = _ns(datetime(2026, 4, 20, 18, 0, tzinfo=ET))
    assert cal.tau_years("wti", start, end) == 0.0


def test_settle_before_now_is_zero():
    cal = TradingCalendar()
    assert cal.tau_years("wti", 2_000_000_000_000_000_000, 1_000_000_000_000_000_000) == 0.0


def test_unsupported_commodity_raises():
    cal = TradingCalendar()
    with pytest.raises(NotImplementedError):
        cal.tau_years("brent", 1_000_000_000_000_000_000, 2_000_000_000_000_000_000)
