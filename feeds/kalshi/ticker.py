"""Kalshi ticker schema parser.

Decodes the four-level Kalshi hierarchy:
  Series  ->  KXSOYBEANW
  Event   ->  KXSOYBEANW-26APR24
  Market  ->  KXSOYBEANW-26APR24-17

Fail-loud: malformed tickers raise ValueError immediately.

References:
  - Phase 07 section 1 (contract identification)
  - Kalshi API docs (market ticker conventions)
  - GAP-074 in audit_E_gap_register.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Month abbreviation mapping (Kalshi uses uppercase 3-letter months)
_MONTH_MAP: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_MONTH_REVERSE: dict[int, str] = {v: k for k, v in _MONTH_MAP.items()}

# Patterns for the three ticker levels.
# Series: one or more uppercase alphanumeric characters (e.g. KXSOYBEANW, KXWTIW)
_SERIES_RE = re.compile(r"^[A-Z][A-Z0-9]+$")

# Event: {SERIES}-{YY}{MON}{DD} or {SERIES}-{YY}{MON}{DD}{NN}
# e.g. KXSOYBEANW-26APR24 means year=2026, month=APR, day=24
# e.g. KXSOYBEANMON-26APR3017 means year=2026, month=APR, day=30, suffix=17
_EVENT_RE = re.compile(
    r"^([A-Z][A-Z0-9]+)-(\d{2})([A-Z]{3})(\d{2,4})$"
)

# Market: {EVENT}-{SUFFIX} where suffix can be a bucket index or T-prefixed strike
# e.g. KXSOYBEANW-26APR24-17
# e.g. KXSOYBEANMON-26APR3017-T1186.99
_MARKET_RE = re.compile(
    r"^([A-Z][A-Z0-9]+)-(\d{2})([A-Z]{3})(\d{2,4})-(.+)$"
)


@dataclass(frozen=True, slots=True)
class ParsedSeriesTicker:
    """Parsed series-level ticker (e.g. KXSOYBEANW)."""

    series: str

    def format(self) -> str:
        """Return the canonical series ticker string."""
        return self.series


@dataclass(frozen=True, slots=True)
class ParsedEventTicker:
    """Parsed event-level ticker (e.g. KXSOYBEANW-26APR24)."""

    series: str
    expiry_date: date

    def format(self) -> str:
        """Return the canonical event ticker string."""
        yy = self.expiry_date.year % 100
        mon = _MONTH_REVERSE[self.expiry_date.month]
        dd = self.expiry_date.day
        return f"{self.series}-{yy:02d}{mon}{dd:02d}"


@dataclass(frozen=True, slots=True)
class ParsedMarketTicker:
    """Parsed market-level ticker (e.g. KXSOYBEANW-26APR24-17)."""

    series: str
    expiry_date: date
    bucket_index: int
    _raw_event: str = ""

    @property
    def event_ticker(self) -> str:
        """Return the parent event ticker string."""
        if self._raw_event:
            return self._raw_event
        yy = self.expiry_date.year % 100
        mon = _MONTH_REVERSE[self.expiry_date.month]
        dd = self.expiry_date.day
        return f"{self.series}-{yy:02d}{mon}{dd:02d}"

    def format(self) -> str:
        """Return the canonical market ticker string."""
        return f"{self.event_ticker}-{self.bucket_index}"


def parse_series_ticker(ticker: str) -> ParsedSeriesTicker:
    """Parse a series ticker like 'KXSOYBEANW'.

    Args:
        ticker: Series ticker string (uppercase).

    Returns:
        ParsedSeriesTicker with the series name.

    Raises:
        ValueError: If the ticker is malformed.
    """
    ticker = ticker.strip()
    if not _SERIES_RE.match(ticker):
        raise ValueError(
            f"Malformed series ticker: {ticker!r}. "
            f"Expected uppercase alphanumeric (e.g. KXSOYBEANW)."
        )
    return ParsedSeriesTicker(series=ticker)


def parse_event_ticker(ticker: str) -> ParsedEventTicker:
    """Parse an event ticker like 'KXSOYBEANW-26APR24'.

    Args:
        ticker: Event ticker string.

    Returns:
        ParsedEventTicker with series and expiry date.

    Raises:
        ValueError: If the ticker is malformed or contains an invalid date.
    """
    ticker = ticker.strip().upper()
    m = _EVENT_RE.match(ticker)
    if m is None:
        raise ValueError(
            f"Malformed event ticker: {ticker!r}. "
            f"Expected format SERIES-YYMONDD (e.g. KXSOYBEANW-26APR24)."
        )

    series = m.group(1)
    yy = int(m.group(2))
    mon_str = m.group(3)
    dd_str = m.group(4)
    # dd_str can be "24" (2-digit day) or "3017" (day 30 + suffix 17)
    dd = int(dd_str[:2])

    if mon_str not in _MONTH_MAP:
        raise ValueError(
            f"Invalid month in event ticker: {mon_str!r}. "
            f"Expected one of {sorted(_MONTH_MAP.keys())}."
        )

    month = _MONTH_MAP[mon_str]
    year = 2000 + yy  # Kalshi uses 2-digit year; all in 2000s

    try:
        expiry = date(year, month, dd)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date in event ticker {ticker!r}: year={year}, "
            f"month={month}, day={dd}."
        ) from exc

    return ParsedEventTicker(series=series, expiry_date=expiry)


def parse_market_ticker(ticker: str) -> ParsedMarketTicker:
    """Parse a market ticker like 'KXSOYBEANW-26APR24-17'.

    The trailing integer is an ordinal bucket index, not a price.

    Args:
        ticker: Market ticker string.

    Returns:
        ParsedMarketTicker with series, expiry date, and bucket index.

    Raises:
        ValueError: If the ticker is malformed or contains an invalid date.
    """
    ticker = ticker.strip().upper()
    m = _MARKET_RE.match(ticker)
    if m is None:
        raise ValueError(
            f"Malformed market ticker: {ticker!r}. "
            f"Expected format SERIES-YYMONDD-INDEX (e.g. KXSOYBEANW-26APR24-17)."
        )

    series = m.group(1)
    yy = int(m.group(2))
    mon_str = m.group(3)
    dd_str = m.group(4)
    dd = int(dd_str[:2])
    suffix = m.group(5)
    # suffix can be "17" (bucket index) or "T1186.99" (strike)
    try:
        bucket_index = int(suffix)
    except ValueError:
        bucket_index = 0  # non-numeric suffix (e.g. T1186.99)

    if mon_str not in _MONTH_MAP:
        raise ValueError(
            f"Invalid month in market ticker: {mon_str!r}. "
            f"Expected one of {sorted(_MONTH_MAP.keys())}."
        )

    month = _MONTH_MAP[mon_str]
    year = 2000 + yy

    try:
        expiry = date(year, month, dd)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date in market ticker {ticker!r}: year={year}, "
            f"month={month}, day={dd}."
        ) from exc

    if bucket_index < 0:
        raise ValueError(
            f"Negative bucket index in market ticker {ticker!r}: {bucket_index}."
        )

    # Reconstruct the raw event ticker (everything before the last dash + suffix)
    last_dash = ticker.rfind("-")
    raw_event = ticker[:last_dash] if last_dash > 0 else ""

    return ParsedMarketTicker(
        series=series,
        expiry_date=expiry,
        bucket_index=bucket_index,
        _raw_event=raw_event,
    )
