"""Tests for engine/cbot_settle.py — ACT-08.

Covers:
  - ZS contract cycle and ticker formatting
  - First Notice Date computation
  - Roll date (FND - 2 BD)
  - Front-month identification across the full 2026-2027 maintained range
  - Reference-price-mode loader (success + fail-loud paths)
  - Out-of-range date guards
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.cbot_settle import (
    ReferencePriceMode,
    RollInfo,
    ZSContract,
    _ZS_CYCLE,
    _last_day_of_month,
    first_notice_date,
    front_month,
    load_reference_price_mode,
    roll_date,
    roll_info,
)
from engine.event_calendar import _is_cbot_trading_day


# ---------------------------------------------------------------------------
# ZSContract basics
# ---------------------------------------------------------------------------

class TestZSContract:
    def test_ticker_format(self) -> None:
        c = ZSContract(month_code="K", delivery_month=5, year=2026)
        assert c.ticker == "ZSK26"

    def test_ticker_two_digit_year(self) -> None:
        c = ZSContract(month_code="F", delivery_month=1, year=2027)
        assert c.ticker == "ZSF27"

    def test_cycle_has_seven_months(self) -> None:
        assert len(_ZS_CYCLE) == 7

    def test_cycle_order(self) -> None:
        months = [m for _, m in _ZS_CYCLE]
        assert months == [1, 3, 5, 7, 8, 9, 11]


# ---------------------------------------------------------------------------
# FND
# ---------------------------------------------------------------------------

class TestFirstNoticeDate:
    def test_may_2026(self) -> None:
        """ZSK26 (May 2026): FND = last BD of April 2026.
        April 30, 2026 is Thursday -> that's a BD and not a CBOT holiday.
        """
        c = ZSContract("K", 5, 2026)
        fnd = first_notice_date(c)
        assert fnd == date(2026, 4, 30)
        assert _is_cbot_trading_day(fnd)

    def test_jul_2026(self) -> None:
        """ZSN26 (Jul 2026): FND = last BD of June 2026.
        June 30, 2026 is Tuesday. June 19 (Fri) is Juneteenth holiday.
        June 30 itself is a Tuesday, should be a valid BD.
        """
        c = ZSContract("N", 7, 2026)
        fnd = first_notice_date(c)
        assert fnd == date(2026, 6, 30)
        assert _is_cbot_trading_day(fnd)

    def test_jan_2027(self) -> None:
        """ZSF27 (Jan 2027): FND = last BD of December 2026.
        Dec 31, 2026 is Thursday. Dec 25 is Christmas (Friday).
        Dec 31 is not a CBOT holiday -> FND = Dec 31.
        """
        c = ZSContract("F", 1, 2027)
        fnd = first_notice_date(c)
        assert fnd == date(2026, 12, 31)
        assert _is_cbot_trading_day(fnd)

    def test_fnd_skips_weekend(self) -> None:
        """ZSQ26 (Aug 2026): FND = last BD of July 2026.
        Jul 31, 2026 is Friday. Jul 3 is Independence Day observed.
        Jul 31 is not a holiday -> FND = Jul 31.
        """
        c = ZSContract("Q", 8, 2026)
        fnd = first_notice_date(c)
        assert fnd == date(2026, 7, 31)
        assert _is_cbot_trading_day(fnd)

    def test_fnd_skips_holiday(self) -> None:
        """ZSF27 (Jan 2027): FND = last BD of Dec 2026.
        Dec 25, 2026 is Christmas (Friday, CBOT holiday).
        Dec 31 is Thursday and not a holiday.
        """
        c = ZSContract("F", 1, 2027)
        fnd = first_notice_date(c)
        # Dec 31 is Thursday, a trading day
        assert fnd == date(2026, 12, 31)

    def test_nov_2026(self) -> None:
        """ZSX26 (Nov 2026): FND = last BD of October 2026.
        Oct 30, 2026 is Friday -> valid trading day.
        """
        c = ZSContract("X", 11, 2026)
        fnd = first_notice_date(c)
        assert fnd == date(2026, 10, 30)
        assert _is_cbot_trading_day(fnd)


# ---------------------------------------------------------------------------
# Roll date
# ---------------------------------------------------------------------------

class TestRollDate:
    def test_may_2026_roll_15bd(self) -> None:
        """ZSK26 FND = Apr 30 (Thu). Roll = FND - 15 BD = Apr 9 (Thu)."""
        c = ZSContract("K", 5, 2026)
        rd = roll_date(c)  # default 15 BD
        assert rd == date(2026, 4, 9)
        assert _is_cbot_trading_day(rd)

    def test_may_2026_roll_2bd_legacy(self) -> None:
        """Legacy 2BD offset: ZSK26 FND = Apr 30, Roll = Apr 28."""
        c = ZSContract("K", 5, 2026)
        rd = roll_date(c, fnd_offset_bd=2)
        assert rd == date(2026, 4, 28)
        assert _is_cbot_trading_day(rd)

    def test_roll_before_fnd(self) -> None:
        """Roll date must always be strictly before FND."""
        c = ZSContract("K", 5, 2026)
        fnd = first_notice_date(c)
        rd = roll_date(c)
        assert rd < fnd

    def test_roll_offset_configurable(self) -> None:
        """Roll offset should be configurable."""
        c = ZSContract("N", 7, 2026)
        rd2 = roll_date(c, fnd_offset_bd=2)
        rd15 = roll_date(c, fnd_offset_bd=15)
        assert rd15 < rd2  # 15BD is earlier

    def test_roll_info_consistency(self) -> None:
        c = ZSContract("N", 7, 2026)
        ri = roll_info(c)
        assert isinstance(ri, RollInfo)
        assert ri.contract == c
        assert ri.first_notice_date == first_notice_date(c)
        assert ri.roll_date == roll_date(c)


# ---------------------------------------------------------------------------
# Front month
# ---------------------------------------------------------------------------

class TestFrontMonth:
    def test_early_2026(self) -> None:
        """Jan 5, 2026: should be before ZSH26 (Mar) roll, so front = ZSH26.
        ZSF26 (Jan 2026) FND = last BD of Dec 2025, which is outside range,
        so if observation_date is Jan 5, we should get the earliest contract
        whose roll date hasn't passed.
        """
        fm = front_month(date(2026, 1, 5))
        # ZSF26 FND would be in Dec 2025 (out of range), so ZSH26 is first viable
        assert fm.month_code == "H"
        assert fm.year == 2026

    def test_apr_8_2026(self) -> None:
        """Apr 8, 2026: ZSK26 roll (15BD) = Apr 9. Apr 8 < Apr 9, so front = ZSK26."""
        fm = front_month(date(2026, 4, 8))
        assert fm.ticker == "ZSK26"

    def test_apr_9_2026(self) -> None:
        """Apr 9, 2026: ZSK26 roll (15BD) = Apr 9. On roll date, front advances to ZSN26."""
        fm = front_month(date(2026, 4, 9))
        assert fm.ticker == "ZSN26"

    def test_front_month_legacy_offset(self) -> None:
        """With legacy 2BD offset, Apr 27 should still be ZSK26."""
        fm = front_month(date(2026, 4, 27), fnd_offset_bd=2)
        assert fm.ticker == "ZSK26"
        fm2 = front_month(date(2026, 4, 28), fnd_offset_bd=2)
        assert fm2.ticker == "ZSN26"

    def test_progression(self) -> None:
        """Front month should never go backwards across the year."""
        prev_month = 0
        prev_year = 0
        # Sample dates across 2026
        for month in range(1, 13):
            for day in (1, 15):
                try:
                    d = date(2026, month, day)
                except ValueError:
                    continue
                fm = front_month(d)
                current = fm.year * 100 + fm.delivery_month
                assert current >= prev_year * 100 + prev_month, (
                    f"Front month went backwards at {d}: {fm.ticker}"
                )
                prev_month = fm.delivery_month
                prev_year = fm.year


# ---------------------------------------------------------------------------
# Reference-price-mode loader
# ---------------------------------------------------------------------------

class TestReferencePriceMode:
    def test_cbot_daily_settle(self) -> None:
        # With 15BD default, Apr 27 is past ZSK26 roll (Apr 9), so front = ZSN26
        rpm = load_reference_price_mode("cbot_daily_settle", date(2026, 4, 27))
        assert isinstance(rpm, ReferencePriceMode)
        assert rpm.mode == "cbot_daily_settle"
        assert rpm.contract.ticker == "ZSN26"

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown mode"):
            load_reference_price_mode("made_up_mode", date(2026, 6, 1))

    def test_cbot_vwap_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            load_reference_price_mode("cbot_vwap", date(2026, 6, 1))

    def test_kalshi_snapshot_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            load_reference_price_mode("kalshi_snapshot", date(2026, 6, 1))


# ---------------------------------------------------------------------------
# Fail-loud: out-of-range dates
# ---------------------------------------------------------------------------

class TestFailLoud:
    def test_front_month_before_range(self) -> None:
        with pytest.raises(ValueError, match="outside maintained"):
            front_month(date(2025, 6, 1))

    def test_front_month_after_range(self) -> None:
        with pytest.raises(ValueError, match="outside maintained|no eligible"):
            front_month(date(2028, 6, 1))

    def test_fnd_outside_range(self) -> None:
        """ZS contract whose FND computation hits out-of-range."""
        c = ZSContract("F", 1, 2029)
        with pytest.raises(ValueError, match="outside maintained"):
            first_notice_date(c)


# ---------------------------------------------------------------------------
# Helper: _last_day_of_month
# ---------------------------------------------------------------------------

class TestLastDayOfMonth:
    def test_february_non_leap(self) -> None:
        assert _last_day_of_month(2026, 2) == date(2026, 2, 28)

    def test_february_leap(self) -> None:
        assert _last_day_of_month(2028, 2) == date(2028, 2, 29)

    def test_december(self) -> None:
        assert _last_day_of_month(2026, 12) == date(2026, 12, 31)

    def test_april(self) -> None:
        assert _last_day_of_month(2026, 4) == date(2026, 4, 30)
