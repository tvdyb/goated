"""Trading calendar — sessional τ calculation + settlement roll."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from engine.event_calendar import TradingCalendar, settle_date_roll

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


# ===================================================================
# Soybean / KXSOYBEANW 24/7 calendar (GAP-087)
# ===================================================================


class TestSoy247:
    """Soybean session: 24/7 including weekends (C07-108)."""

    def test_soy_registered(self):
        cal = TradingCalendar()
        assert cal.supports("soy")

    def test_soy_weekend_counts_full(self):
        """Weekend hours count as trading time for 24/7 product."""
        cal = TradingCalendar()
        # Friday 18:00 ET to Sunday 18:00 ET = exactly 48 hours
        start = _ns(datetime(2026, 4, 24, 18, 0, tzinfo=ET))
        end = _ns(datetime(2026, 4, 26, 18, 0, tzinfo=ET))
        tau = cal.tau_years("soy", start, end)
        expected = 48.0 * 3600.0 / (365.25 * 24 * 3600)
        assert tau == pytest.approx(expected, rel=1e-9)

    def test_soy_full_week(self):
        """Full 7-day week = 168 hours of trading time."""
        cal = TradingCalendar()
        start = _ns(datetime(2026, 4, 20, 0, 0, tzinfo=ET))  # Mon
        end = _ns(datetime(2026, 4, 27, 0, 0, tzinfo=ET))    # Next Mon
        tau = cal.tau_years("soy", start, end)
        expected = 7.0 * 24.0 * 3600.0 / (365.25 * 24 * 3600)
        assert tau == pytest.approx(expected, rel=1e-9)

    def test_soy_one_hour(self):
        cal = TradingCalendar()
        start = _ns(datetime(2026, 4, 25, 12, 0, tzinfo=ET))  # Sat noon
        end = _ns(datetime(2026, 4, 25, 13, 0, tzinfo=ET))
        tau = cal.tau_years("soy", start, end)
        expected = 3600.0 / (365.25 * 24 * 3600)
        assert tau == pytest.approx(expected, rel=1e-9)

    def test_soy_settle_before_now_zero(self):
        cal = TradingCalendar()
        assert cal.tau_years("soy", 2_000_000_000_000_000_000, 1_000_000_000_000_000_000) == 0.0

    def test_soy_wti_weekend_divergence(self):
        """WTI should count 0 for weekend, soy should count positive."""
        cal = TradingCalendar()
        # Saturday 00:00 to Saturday 12:00
        start = _ns(datetime(2026, 4, 25, 0, 0, tzinfo=ET))
        end = _ns(datetime(2026, 4, 25, 12, 0, tzinfo=ET))
        assert cal.tau_years("wti", start, end) == 0.0
        assert cal.tau_years("soy", start, end) > 0.0


# ===================================================================
# Friday-holiday Rule 7.2(b) settlement roll (GAP-089)
# ===================================================================


class TestSettleDateRoll:
    """Rule 7.2(b): Friday holiday rolls settlement to next trading day."""

    def test_non_holiday_friday_passthrough(self):
        """A normal Friday returns unchanged."""
        assert settle_date_roll(date(2026, 4, 24)) == date(2026, 4, 24)

    def test_good_friday_2026_rolls_to_monday(self):
        """Good Friday 2026-04-03 is a CBOT holiday; rolls to Mon 2026-04-06."""
        assert settle_date_roll(date(2026, 4, 3)) == date(2026, 4, 6)

    def test_juneteenth_friday_2026_rolls_to_monday(self):
        """Juneteenth 2026-06-19 is a Friday CBOT holiday; rolls to Mon."""
        assert settle_date_roll(date(2026, 6, 19)) == date(2026, 6, 22)

    def test_independence_day_observed_2026_rolls(self):
        """Jul 4 2026 is Sat, observed Fri Jul 3; rolls to Mon Jul 6."""
        assert settle_date_roll(date(2026, 7, 3)) == date(2026, 7, 6)

    def test_christmas_friday_2026(self):
        """Christmas 2026-12-25 is a Friday; rolls to Mon 2026-12-28."""
        assert settle_date_roll(date(2026, 12, 25)) == date(2026, 12, 28)

    def test_new_years_2027_friday(self):
        """New Year's 2027-01-01 is a Friday; rolls to Mon 2027-01-04."""
        assert settle_date_roll(date(2027, 1, 1)) == date(2027, 1, 4)

    def test_good_friday_2027(self):
        """Good Friday 2027-03-26; rolls to Mon 2027-03-29."""
        assert settle_date_roll(date(2027, 3, 26)) == date(2027, 3, 29)

    def test_christmas_observed_2027_friday(self):
        """Christmas 2027 observed Fri Dec 24; rolls to Mon Dec 27."""
        assert settle_date_roll(date(2027, 12, 24)) == date(2027, 12, 27)

    def test_weekday_non_holiday_passthrough(self):
        """A regular Wednesday returns unchanged."""
        assert settle_date_roll(date(2026, 4, 22)) == date(2026, 4, 22)

    def test_saturday_rolls_to_monday(self):
        """Saturday (not a trading day) rolls to Monday."""
        assert settle_date_roll(date(2026, 4, 25)) == date(2026, 4, 27)

    def test_sunday_rolls_to_monday(self):
        """Sunday rolls to Monday."""
        assert settle_date_roll(date(2026, 4, 26)) == date(2026, 4, 27)

    def test_monday_holiday_rolls_to_tuesday(self):
        """MLK Day 2026-01-19 (Mon) rolls to Tue 2026-01-20."""
        assert settle_date_roll(date(2026, 1, 19)) == date(2026, 1, 20)

    def test_out_of_range_raises(self):
        """Dates outside maintained range must raise ValueError."""
        with pytest.raises(ValueError, match="outside maintained holiday range"):
            settle_date_roll(date(2025, 12, 31))
        with pytest.raises(ValueError, match="outside maintained holiday range"):
            settle_date_roll(date(2028, 1, 1))
