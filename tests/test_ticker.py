"""Tests for feeds.kalshi.ticker -- Kalshi ticker schema parser.

Covers GAP-074: Series -> Event -> Market -> Yes/No ticker schema.
"""

from __future__ import annotations

from datetime import date

import pytest

from feeds.kalshi.ticker import (
    ParsedEventTicker,
    ParsedMarketTicker,
    ParsedSeriesTicker,
    parse_event_ticker,
    parse_market_ticker,
    parse_series_ticker,
)


# ── Series ticker ─────────────────────────────────────────────────────


class TestParseSeriesTicker:
    def test_valid_kxsoybeanw(self) -> None:
        result = parse_series_ticker("KXSOYBEANW")
        assert result == ParsedSeriesTicker(series="KXSOYBEANW")

    def test_valid_kxwtiw(self) -> None:
        result = parse_series_ticker("KXWTIW")
        assert result.series == "KXWTIW"

    def test_valid_kxgold(self) -> None:
        result = parse_series_ticker("KXGOLD")
        assert result.series == "KXGOLD"

    def test_format_roundtrip(self) -> None:
        result = parse_series_ticker("KXSOYBEANW")
        assert result.format() == "KXSOYBEANW"

    def test_strips_whitespace(self) -> None:
        result = parse_series_ticker("  KXSOYBEANW  ")
        assert result.series == "KXSOYBEANW"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Malformed series ticker"):
            parse_series_ticker("")

    def test_rejects_lowercase(self) -> None:
        with pytest.raises(ValueError, match="Malformed series ticker"):
            parse_series_ticker("kxsoybeanw")

    def test_rejects_single_char(self) -> None:
        with pytest.raises(ValueError, match="Malformed series ticker"):
            parse_series_ticker("K")

    def test_rejects_hyphenated(self) -> None:
        with pytest.raises(ValueError, match="Malformed series ticker"):
            parse_series_ticker("KX-SOYBEANW")

    def test_rejects_with_digits_first(self) -> None:
        with pytest.raises(ValueError, match="Malformed series ticker"):
            parse_series_ticker("1KXSOY")


# ── Event ticker ──────────────────────────────────────────────────────


class TestParseEventTicker:
    def test_valid_soybean(self) -> None:
        result = parse_event_ticker("KXSOYBEANW-26APR24")
        assert result.series == "KXSOYBEANW"
        assert result.expiry_date == date(2026, 4, 24)

    def test_valid_jan(self) -> None:
        result = parse_event_ticker("KXWTIW-25JAN10")
        assert result.series == "KXWTIW"
        assert result.expiry_date == date(2025, 1, 10)

    def test_valid_dec(self) -> None:
        result = parse_event_ticker("KXGOLD-27DEC31")
        assert result.series == "KXGOLD"
        assert result.expiry_date == date(2027, 12, 31)

    def test_format_roundtrip(self) -> None:
        result = parse_event_ticker("KXSOYBEANW-26APR24")
        assert result.format() == "KXSOYBEANW-26APR24"

    def test_case_insensitive_input(self) -> None:
        result = parse_event_ticker("kxsoybeanw-26apr24")
        assert result.series == "KXSOYBEANW"
        assert result.expiry_date == date(2026, 4, 24)

    def test_rejects_missing_date(self) -> None:
        with pytest.raises(ValueError, match="Malformed event ticker"):
            parse_event_ticker("KXSOYBEANW")

    def test_rejects_bad_month(self) -> None:
        with pytest.raises(ValueError, match="Invalid month"):
            parse_event_ticker("KXSOYBEANW-26XYZ24")

    def test_rejects_invalid_day(self) -> None:
        with pytest.raises(ValueError, match="Invalid date"):
            parse_event_ticker("KXSOYBEANW-26FEB30")

    def test_rejects_extra_segment(self) -> None:
        with pytest.raises(ValueError, match="Malformed event ticker"):
            parse_event_ticker("KXSOYBEANW-26APR24-17")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Malformed event ticker"):
            parse_event_ticker("")


# ── Market ticker ─────────────────────────────────────────────────────


class TestParseMarketTicker:
    def test_valid_soybean_bucket_17(self) -> None:
        result = parse_market_ticker("KXSOYBEANW-26APR24-17")
        assert result.series == "KXSOYBEANW"
        assert result.expiry_date == date(2026, 4, 24)
        assert result.bucket_index == 17

    def test_valid_bucket_0(self) -> None:
        result = parse_market_ticker("KXSOYBEANW-26APR24-0")
        assert result.bucket_index == 0

    def test_valid_large_bucket_index(self) -> None:
        result = parse_market_ticker("KXWTIW-25JAN10-123")
        assert result.bucket_index == 123

    def test_format_roundtrip(self) -> None:
        result = parse_market_ticker("KXSOYBEANW-26APR24-17")
        assert result.format() == "KXSOYBEANW-26APR24-17"

    def test_event_ticker_property(self) -> None:
        result = parse_market_ticker("KXSOYBEANW-26APR24-17")
        assert result.event_ticker == "KXSOYBEANW-26APR24"

    def test_case_insensitive(self) -> None:
        result = parse_market_ticker("kxsoybeanw-26apr24-17")
        assert result.series == "KXSOYBEANW"
        assert result.bucket_index == 17

    def test_rejects_missing_index(self) -> None:
        with pytest.raises(ValueError, match="Malformed market ticker"):
            parse_market_ticker("KXSOYBEANW-26APR24-")

    def test_rejects_no_index(self) -> None:
        # This is an event ticker, not a market ticker
        with pytest.raises(ValueError, match="Malformed market ticker"):
            parse_market_ticker("KXSOYBEANW-26APR24")

    def test_rejects_bad_month(self) -> None:
        with pytest.raises(ValueError, match="Invalid month"):
            parse_market_ticker("KXSOYBEANW-26XYZ24-17")

    def test_rejects_invalid_date(self) -> None:
        with pytest.raises(ValueError, match="Invalid date"):
            parse_market_ticker("KXSOYBEANW-26FEB30-17")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Malformed market ticker"):
            parse_market_ticker("")


# ── KXSOYBEANMON (F4 monthly) ticker tests ───────────────────────────


class TestKXSOYBEANMONTickers:
    """Verify that the parser handles KXSOYBEANMON monthly tickers."""

    def test_series_kxsoybeanmon(self) -> None:
        result = parse_series_ticker("KXSOYBEANMON")
        assert result.series == "KXSOYBEANMON"

    def test_event_kxsoybeanmon(self) -> None:
        result = parse_event_ticker("KXSOYBEANMON-26MAY30")
        assert result.series == "KXSOYBEANMON"
        assert result.expiry_date == date(2026, 5, 30)

    def test_event_kxsoybeanmon_roundtrip(self) -> None:
        result = parse_event_ticker("KXSOYBEANMON-26MAY30")
        assert result.format() == "KXSOYBEANMON-26MAY30"

    def test_market_kxsoybeanmon(self) -> None:
        result = parse_market_ticker("KXSOYBEANMON-26MAY30-5")
        assert result.series == "KXSOYBEANMON"
        assert result.expiry_date == date(2026, 5, 30)
        assert result.bucket_index == 5

    def test_market_kxsoybeanmon_event_ticker(self) -> None:
        result = parse_market_ticker("KXSOYBEANMON-26MAY30-5")
        assert result.event_ticker == "KXSOYBEANMON-26MAY30"

    def test_kxcornmon(self) -> None:
        """Also verify KXCORNMON (second F4 target)."""
        result = parse_event_ticker("KXCORNMON-26JUN28")
        assert result.series == "KXCORNMON"
        assert result.expiry_date == date(2026, 6, 28)
