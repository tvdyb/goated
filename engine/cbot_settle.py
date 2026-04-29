"""CBOT ZS settle resolver, front-month roll, FND calendar, reference-price-mode loader.

ACT-08 closes GAP-076, GAP-077, GAP-078.

This module answers three questions for the soybean theo engine:
  1. Which ZS contract is the current front month?  (``front_month``)
  2. When does the roll happen?  (``roll_date``, ``first_notice_date``)
  3. What reference-price mode does KXSOYBEANW use?  (``load_reference_price_mode``)

It does NOT fetch prices.  Actual price retrieval is a feeds-layer concern
(ACT-16 / GAP-063).  This module provides the contract identification and
calendar logic that the price fetcher needs.

ZS contract cycle: F(Jan) H(Mar) K(May) N(Jul) Q(Aug) U(Sep) X(Nov).
FND per CBOT Chapter 11: last business day of the month preceding delivery.
Roll rule: configurable business days before FND.
Default ``fnd_minus_15bd`` for monthlies, ``fnd_minus_2bd`` for legacy weeklies.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple

from engine.event_calendar import (
    _CBOT_HOLIDAYS,
    _HOLIDAY_RANGE_END,
    _HOLIDAY_RANGE_START,
    _is_cbot_trading_day,
)

# ---------------------------------------------------------------------------
# ZS contract month cycle
# ---------------------------------------------------------------------------

# Month code -> calendar month number (1-indexed).
_ZS_MONTH_CODES: dict[str, int] = {
    "F": 1,   # January
    "H": 3,   # March
    "K": 5,   # May
    "N": 7,   # July
    "Q": 8,   # August
    "U": 9,   # September
    "X": 11,  # November
}

# Ordered list of (month_code, delivery_month) sorted by delivery month.
_ZS_CYCLE: list[tuple[str, int]] = sorted(
    _ZS_MONTH_CODES.items(), key=lambda x: x[1]
)

# Reverse mapping: calendar month -> month code (only for ZS delivery months).
_MONTH_TO_CODE: dict[int, str] = {v: k for k, v in _ZS_MONTH_CODES.items()}


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

class ZSContract(NamedTuple):
    """Identifies a single ZS futures contract."""
    month_code: str   # e.g. "K"
    delivery_month: int  # 1..12
    year: int         # 4-digit year, e.g. 2026

    @property
    def ticker(self) -> str:
        """CME-style ticker, e.g. 'ZSK26'."""
        return f"ZS{self.month_code}{self.year % 100:02d}"


class RollInfo(NamedTuple):
    """Roll calendar entry for a ZS contract."""
    contract: ZSContract
    first_notice_date: date
    roll_date: date  # = FND - N business days (N configurable)


class ReferencePriceMode(NamedTuple):
    """Parsed reference-price-mode configuration."""
    mode: str            # "cbot_daily_settle" | "cbot_vwap" | "kalshi_snapshot"
    contract: ZSContract  # which ZS contract provides the reference


# ---------------------------------------------------------------------------
# Holiday-range guard
# ---------------------------------------------------------------------------

def _check_range(d: date, context: str) -> None:
    """Raise ValueError if d is outside the maintained CBOT holiday range."""
    if d < _HOLIDAY_RANGE_START or d > _HOLIDAY_RANGE_END:
        raise ValueError(
            f"{context}: {d} is outside maintained CBOT holiday range "
            f"[{_HOLIDAY_RANGE_START}, {_HOLIDAY_RANGE_END}]. "
            f"Extend _CBOT_HOLIDAYS in engine/event_calendar.py."
        )


# ---------------------------------------------------------------------------
# Business-day helpers
# ---------------------------------------------------------------------------

def _prev_business_day(d: date) -> date:
    """Return the most recent CBOT trading day on or before d."""
    _check_range(d, "_prev_business_day")
    while not _is_cbot_trading_day(d):
        d -= timedelta(days=1)
        _check_range(d, "_prev_business_day")
    return d


def _subtract_business_days(d: date, n: int) -> date:
    """Subtract n business days from d (d itself may or may not be a BD).

    Starts from the most recent trading day on or before d, then steps
    back n trading days.
    """
    _check_range(d, "_subtract_business_days")
    current = _prev_business_day(d)
    for _ in range(n):
        current -= timedelta(days=1)
        _check_range(current, "_subtract_business_days")
        current = _prev_business_day(current)
    return current


# ---------------------------------------------------------------------------
# Last day of month
# ---------------------------------------------------------------------------

def _last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of the given month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


# ---------------------------------------------------------------------------
# FND and roll date
# ---------------------------------------------------------------------------

def first_notice_date(contract: ZSContract) -> date:
    """First Notice Day for a ZS contract.

    Per CBOT Chapter 11: the last business day of the month preceding
    the delivery month.

    Raises ValueError if the date falls outside the maintained holiday range.
    """
    delivery_month = contract.delivery_month
    year = contract.year

    # Month preceding delivery month.
    if delivery_month == 1:
        preceding_year = year - 1
        preceding_month = 12
    else:
        preceding_year = year
        preceding_month = delivery_month - 1

    last_day = _last_day_of_month(preceding_year, preceding_month)
    _check_range(last_day, f"first_notice_date({contract.ticker})")
    return _prev_business_day(last_day)


# Default roll offset: 15 business days before FND for commodity monthlies.
# Legacy value was 2 for weeklies. Configurable via fnd_offset_bd parameter.
_DEFAULT_FND_OFFSET_BD = 15


def roll_date(contract: ZSContract, *, fnd_offset_bd: int = _DEFAULT_FND_OFFSET_BD) -> date:
    """Roll date for a ZS contract: N business days before FND.

    On and after this date, the front month should be the NEXT contract
    in the ZS cycle.

    Args:
        contract: The ZS contract.
        fnd_offset_bd: Number of business days before FND to roll.
            Default 15 for commodity monthlies.
    """
    if fnd_offset_bd < 0:
        raise ValueError(f"fnd_offset_bd must be >= 0, got {fnd_offset_bd}")
    fnd = first_notice_date(contract)
    return _subtract_business_days(fnd, fnd_offset_bd)


def roll_info(contract: ZSContract, *, fnd_offset_bd: int = _DEFAULT_FND_OFFSET_BD) -> RollInfo:
    """Convenience: compute FND and roll date together."""
    fnd = first_notice_date(contract)
    rd = _subtract_business_days(fnd, fnd_offset_bd)
    return RollInfo(contract=contract, first_notice_date=fnd, roll_date=rd)


# ---------------------------------------------------------------------------
# Contract enumeration
# ---------------------------------------------------------------------------

def _zs_contracts_for_year(year: int) -> list[ZSContract]:
    """Return all ZS contracts for a given calendar year, in cycle order."""
    return [
        ZSContract(month_code=code, delivery_month=month, year=year)
        for code, month in _ZS_CYCLE
    ]


def front_month(
    observation_date: date, *, fnd_offset_bd: int = _DEFAULT_FND_OFFSET_BD
) -> ZSContract:
    """Determine the front-month ZS contract for a given observation date.

    The front month is the nearest ZS contract whose roll date has NOT
    yet been reached.  On or after roll date, the front month advances
    to the next contract in the cycle.

    Args:
        observation_date: The date for which to determine front month.
        fnd_offset_bd: Business days before FND for the roll date.

    Raises ValueError if observation_date is outside the maintained range.
    """
    _check_range(observation_date, "front_month")

    # Search current year and next year (sufficient because the longest
    # gap between ZS months is Jan->Mar = 2 months, so we never need to
    # look more than ~14 months ahead).
    candidates: list[ZSContract] = (
        _zs_contracts_for_year(observation_date.year)
        + _zs_contracts_for_year(observation_date.year + 1)
    )

    for contract in candidates:
        try:
            rd = roll_date(contract, fnd_offset_bd=fnd_offset_bd)
        except ValueError:
            # Contract's FND is outside maintained range; skip.
            continue
        if observation_date < rd:
            return contract

    raise ValueError(
        f"front_month: no eligible ZS contract found for {observation_date}. "
        f"Extend _CBOT_HOLIDAYS range or check the observation date."
    )


# ---------------------------------------------------------------------------
# Reference-price-mode loader
# ---------------------------------------------------------------------------

# Supported modes.  Only cbot_daily_settle is fully wired; others raise
# NotImplementedError per fail-loud policy.
_SUPPORTED_MODES = frozenset({"cbot_daily_settle", "cbot_vwap", "kalshi_snapshot"})


def load_reference_price_mode(
    mode_str: str,
    observation_date: date,
) -> ReferencePriceMode:
    """Parse the reference-price-mode string from commodities.yaml and
    resolve the associated ZS contract.

    Args:
        mode_str: Value of ``soy.kalshi.reference_price_mode`` from config.
                  One of: ``cbot_daily_settle``, ``cbot_vwap``,
                  ``kalshi_snapshot``.
        observation_date: Current date, used to resolve the front-month
                          ZS contract.

    Returns:
        A ``ReferencePriceMode`` with the resolved mode and contract.

    Raises:
        ValueError: If ``mode_str`` is not recognised.
        NotImplementedError: If ``mode_str`` is recognised but not yet
                             implemented (``cbot_vwap``, ``kalshi_snapshot``).
    """
    if mode_str not in _SUPPORTED_MODES:
        raise ValueError(
            f"load_reference_price_mode: unknown mode '{mode_str}'. "
            f"Supported: {sorted(_SUPPORTED_MODES)}"
        )

    contract = front_month(observation_date)

    if mode_str == "cbot_daily_settle":
        return ReferencePriceMode(mode=mode_str, contract=contract)

    # Future modes -- fail loud until implemented.
    raise NotImplementedError(
        f"load_reference_price_mode: mode '{mode_str}' is recognised "
        f"but not yet implemented. Only 'cbot_daily_settle' is wired."
    )
