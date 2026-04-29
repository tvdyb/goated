"""CBOT options expiry calendar for ZS (soybean) and ZC (corn) futures options.

CBOT standard options on futures expire on the last Friday that precedes
the first notice day (FND) of the underlying futures contract by at least
2 business days.  FND for ZS/ZC is the last business day of the month
preceding the delivery month (per CBOT Chapter 11).

This module provides:
  - next_expiry(symbol, ref_date) -> date
  - expiry_schedule(symbol, year) -> list[date]
  - options_expiry(symbol, delivery_month, year) -> date

Uses the same CBOT holiday set from engine.event_calendar for consistency.
"""

from __future__ import annotations

from datetime import date, timedelta

from engine.event_calendar import _is_cbot_trading_day

# ---------------------------------------------------------------------------
# Contract month cycles
# ---------------------------------------------------------------------------

# ZS (soybean futures): F(Jan) H(Mar) K(May) N(Jul) Q(Aug) U(Sep) X(Nov)
_ZS_DELIVERY_MONTHS: list[int] = [1, 3, 5, 7, 8, 9, 11]

# ZC (corn futures): F(Jan) H(Mar) K(May) N(Jul) U(Sep) Z(Dec)
_ZC_DELIVERY_MONTHS: list[int] = [3, 5, 7, 9, 12]

_SYMBOL_CYCLES: dict[str, list[int]] = {
    "ZS": _ZS_DELIVERY_MONTHS,
    "ZC": _ZC_DELIVERY_MONTHS,
}


def _validate_symbol(symbol: str) -> list[int]:
    """Return the delivery-month cycle for a symbol, or raise."""
    cycle = _SYMBOL_CYCLES.get(symbol)
    if cycle is None:
        raise ValueError(
            f"expiry_calendar: unsupported symbol '{symbol}'. "
            f"Supported: {sorted(_SYMBOL_CYCLES)}"
        )
    return cycle


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of the given month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _prev_business_day(d: date) -> date:
    """Return the most recent CBOT trading day on or before d."""
    while not _is_cbot_trading_day(d):
        d -= timedelta(days=1)
    return d


def _subtract_business_days(d: date, n: int) -> date:
    """Subtract n business days from d."""
    current = _prev_business_day(d)
    for _ in range(n):
        current -= timedelta(days=1)
        current = _prev_business_day(current)
    return current


def _first_notice_date(delivery_month: int, year: int) -> date:
    """FND: last business day of the month preceding the delivery month."""
    if delivery_month == 1:
        preceding_year = year - 1
        preceding_month = 12
    else:
        preceding_year = year
        preceding_month = delivery_month - 1

    last_day = _last_day_of_month(preceding_year, preceding_month)
    return _prev_business_day(last_day)


# ---------------------------------------------------------------------------
# Options expiry computation
# ---------------------------------------------------------------------------

def options_expiry(symbol: str, delivery_month: int, year: int) -> date:
    """Compute the standard options expiry for a given futures contract.

    CBOT rule: options expire on the last Friday that precedes FND by at
    least 2 business days.

    Args:
        symbol: 'ZS' or 'ZC'.
        delivery_month: Delivery month of the underlying futures (1-12).
        year: Delivery year.

    Returns:
        The options expiry date.

    Raises:
        ValueError: If symbol is unsupported or no valid Friday is found.
    """
    _validate_symbol(symbol)

    fnd = _first_notice_date(delivery_month, year)
    # We need a Friday that is at least 2 business days before FND.
    # The cutoff: subtract 2 business days from FND.
    cutoff = _subtract_business_days(fnd, 2)

    # Walk backward from cutoff to find the most recent Friday (weekday 4).
    d = cutoff
    while d.weekday() != 4:  # 4 = Friday
        d -= timedelta(days=1)

    if d.year < year - 1:
        raise ValueError(
            f"options_expiry: could not find valid Friday for "
            f"{symbol} {delivery_month}/{year}"
        )

    return d


def expiry_schedule(symbol: str, year: int) -> list[date]:
    """Return all standard options expiry dates for a symbol in a given year.

    Returns expiries sorted chronologically. Only includes expiries where
    the underlying futures contract has a delivery month in the given year.

    Args:
        symbol: 'ZS' or 'ZC'.
        year: Calendar year.

    Returns:
        Sorted list of expiry dates.
    """
    cycle = _validate_symbol(symbol)
    expiries: list[date] = []
    for month in cycle:
        try:
            exp = options_expiry(symbol, month, year)
            expiries.append(exp)
        except ValueError:
            continue
    expiries.sort()
    return expiries


def next_expiry(symbol: str, ref_date: date) -> date:
    """Return the nearest options expiry on or after ref_date.

    Searches the current year and next year's schedules.

    Args:
        symbol: 'ZS' or 'ZC'.
        ref_date: Reference date.

    Returns:
        The nearest expiry date >= ref_date.

    Raises:
        ValueError: If no expiry is found within the search range.
    """
    for yr in (ref_date.year, ref_date.year + 1):
        for exp in expiry_schedule(symbol, yr):
            if exp >= ref_date:
                return exp

    raise ValueError(
        f"next_expiry: no {symbol} options expiry found on or after {ref_date}. "
        f"Extend the CBOT holiday range if needed."
    )
