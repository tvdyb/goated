"""Tests for engine/goldman_roll.py — Goldman roll window detection."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.event_calendar import _CBOT_HOLIDAYS
from engine.goldman_roll import (
    _nth_business_day,
    is_in_roll_window,
    roll_drift_cents,
    roll_window,
)

# ---------------------------------------------------------------------------
# _nth_business_day
# ---------------------------------------------------------------------------


class TestNthBusinessDay:
    def test_first_business_day_jan_2026(self):
        # Jan 1 2026 is a CBOT holiday (New Year's), so 1st bday = Jan 2
        assert _nth_business_day(2026, 1, 1) == date(2026, 1, 2)

    def test_fifth_business_day_jan_2026(self):
        # Jan 2026: 1=holiday, 2=Fri(1), 3-4=weekend, 5=Mon(2), 6=Tue(3),
        # 7=Wed(4), 8=Thu(5)
        assert _nth_business_day(2026, 1, 5) == date(2026, 1, 8)

    def test_first_business_day_feb_2026(self):
        # Feb 1 2026 is Sunday, so 1st bday = Feb 2 (Mon)
        assert _nth_business_day(2026, 2, 1) == date(2026, 2, 2)

    def test_raises_outside_range(self):
        with pytest.raises(ValueError, match="outside maintained"):
            _nth_business_day(2025, 1, 1)


# ---------------------------------------------------------------------------
# roll_window
# ---------------------------------------------------------------------------


class TestRollWindow:
    def test_jan_2026(self):
        start, end = roll_window(2026, 1)
        assert start == date(2026, 1, 8)  # 5th bday
        assert end == date(2026, 1, 14)   # 9th bday

    def test_feb_2026(self):
        start, end = roll_window(2026, 2)
        # Feb 2026: 2=Mon(1), 3=Tue(2), 4=Wed(3), 5=Thu(4), 6=Fri(5)
        # 9=Mon(6), 10=Tue(7), 11=Wed(8), 12=Thu(9)
        assert start == date(2026, 2, 6)
        assert end == date(2026, 2, 12)

    def test_window_is_5_business_days(self):
        """Roll window spans exactly 5 business days (5th through 9th)."""
        start, end = roll_window(2026, 3)
        d = start
        count = 0
        while d <= end:
            if d.weekday() < 5 and d not in _CBOT_HOLIDAYS:
                count += 1
            d += timedelta(days=1)
        assert count == 5

    def test_start_before_end(self):
        for month in range(1, 13):
            try:
                start, end = roll_window(2026, month)
                assert start <= end
            except ValueError:
                pass  # some months may be outside range


# ---------------------------------------------------------------------------
# is_in_roll_window
# ---------------------------------------------------------------------------


class TestIsInRollWindow:
    def test_inside_window(self):
        start, end = roll_window(2026, 3)
        assert is_in_roll_window(start)
        assert is_in_roll_window(end)

    def test_outside_window_before(self):
        start, _ = roll_window(2026, 3)
        assert not is_in_roll_window(start - timedelta(days=1))

    def test_outside_window_after(self):
        _, end = roll_window(2026, 3)
        assert not is_in_roll_window(end + timedelta(days=1))

    def test_day_before_start(self):
        start, _ = roll_window(2026, 6)
        day_before = start - timedelta(days=1)
        assert not is_in_roll_window(day_before)

    def test_mid_window(self):
        start, end = roll_window(2026, 4)
        mid = start + timedelta(days=(end - start).days // 2)
        assert is_in_roll_window(mid)


# ---------------------------------------------------------------------------
# roll_drift_cents
# ---------------------------------------------------------------------------


class TestRollDriftCents:
    def test_zero_outside_window(self):
        # Jan 2 2026 is the 1st business day — well before the 5th
        assert roll_drift_cents(date(2026, 1, 2)) == 0.0

    def test_negative_inside_window(self):
        start, end = roll_window(2026, 3)
        drift = roll_drift_cents(start)
        assert drift < 0.0

    def test_range_2_to_5(self):
        """Drift should be between -5c (peak) and -2c (edge) inside window."""
        start, end = roll_window(2026, 3)
        d = start
        while d <= end:
            drift = roll_drift_cents(d)
            assert -5.0 <= drift <= -2.0, f"drift={drift} on {d}"
            d += timedelta(days=1)

    def test_peak_at_center(self):
        """Drift should be most negative near the center of the window."""
        start, end = roll_window(2026, 5)
        mid = start + timedelta(days=(end - start).days // 2)
        edge_drift = roll_drift_cents(start)
        center_drift = roll_drift_cents(mid)
        assert center_drift <= edge_drift  # more negative at center

    def test_edges_are_minus_2(self):
        start, end = roll_window(2026, 7)
        assert roll_drift_cents(start) == pytest.approx(-2.0)
        assert roll_drift_cents(end) == pytest.approx(-2.0)

    def test_symmetry(self):
        """Drift at symmetric positions from center should be equal."""
        start, end = roll_window(2026, 8)
        n = (end - start).days
        for i in range(n // 2 + 1):
            d1 = roll_drift_cents(start + timedelta(days=i))
            d2 = roll_drift_cents(end - timedelta(days=i))
            assert d1 == pytest.approx(d2, abs=1e-10), f"asymmetry at offset {i}"

    def test_zero_outside_after_window(self):
        _, end = roll_window(2026, 9)
        assert roll_drift_cents(end + timedelta(days=1)) == 0.0

    def test_multiple_months(self):
        """Roll drift works across multiple months."""
        for month in range(1, 13):
            try:
                start, _ = roll_window(2026, month)
                drift = roll_drift_cents(start)
                assert -5.0 <= drift <= -2.0
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Integration: no effect outside window
# ---------------------------------------------------------------------------


class TestNoEffectOutsideWindow:
    def test_first_day_of_month(self):
        assert roll_drift_cents(date(2026, 3, 2)) == 0.0  # Mon Mar 2

    def test_last_day_of_month(self):
        assert roll_drift_cents(date(2026, 3, 31)) == 0.0
