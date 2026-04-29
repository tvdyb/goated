"""Tests for feeds/cme/ — F4-ACT-02 (CME options chain + futures settle ingest).

Covers:
  - OptionsChain dataclass validation
  - Put-call parity check (GAP-047): passes on clean data, fires on bad data
  - Expiry calendar: known ZS/ZC expiry dates for 2026-2027
  - Futures settle puller: mock HTTP response parsing + error handling
  - Options chain puller: mock HTTP response parsing + error handling
  - CMEIngestError hierarchy
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest

from feeds.cme.errors import CMEChainError, CMEIngestError, CMEParityError, CMESettleError
from feeds.cme.expiry_calendar import (
    _first_notice_date,
    expiry_schedule,
    next_expiry,
    options_expiry,
)
from feeds.cme.futures_settle import _extract_front_month_settle, pull_settle
from feeds.cme.options_chain import (
    OptionsChain,
    _parse_options_response,
    _parse_settle_price,
    check_put_call_parity,
    pull_options_chain,
)

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_cme_ingest_error_is_base(self) -> None:
        assert issubclass(CMEChainError, CMEIngestError)
        assert issubclass(CMESettleError, CMEIngestError)
        assert issubclass(CMEParityError, CMEIngestError)

    def test_error_has_source(self) -> None:
        err = CMEChainError("test", source="options_chain")
        assert err.source == "options_chain"
        assert "test" in str(err)


# ---------------------------------------------------------------------------
# OptionsChain dataclass
# ---------------------------------------------------------------------------


def _make_chain(
    n: int = 10,
    *,
    symbol: str = "ZS",
    underlying: float = 1050.0,
    base_strike: float = 1000.0,
    strike_step: float = 10.0,
) -> OptionsChain:
    """Build a synthetic options chain for testing."""
    strikes = np.arange(base_strike, base_strike + n * strike_step, strike_step)
    # Synthetic call/put prices: intrinsic + some time value.
    call_prices = np.maximum(underlying - strikes, 0.0) + 5.0
    put_prices = np.maximum(strikes - underlying, 0.0) + 5.0
    return OptionsChain(
        symbol=symbol,
        expiry=date(2026, 7, 24),
        as_of=date(2026, 6, 1),
        underlying_settle=underlying,
        strikes=strikes,
        call_prices=call_prices,
        put_prices=put_prices,
        call_ivs=None,
        put_ivs=None,
        call_oi=None,
        put_oi=None,
        call_volume=None,
        put_volume=None,
    )


class TestOptionsChain:
    def test_valid_chain(self) -> None:
        chain = _make_chain(10)
        assert len(chain.strikes) == 10
        assert chain.symbol == "ZS"
        assert chain.underlying_settle == 1050.0

    def test_empty_chain_raises(self) -> None:
        with pytest.raises(CMEChainError, match="Empty options chain"):
            OptionsChain(
                symbol="ZS",
                expiry=date(2026, 7, 24),
                as_of=date(2026, 6, 1),
                underlying_settle=1050.0,
                strikes=np.array([], dtype=np.float64),
                call_prices=np.array([], dtype=np.float64),
                put_prices=np.array([], dtype=np.float64),
                call_ivs=None,
                put_ivs=None,
                call_oi=None,
                put_oi=None,
                call_volume=None,
                put_volume=None,
            )

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(CMEChainError, match="Array length mismatch"):
            OptionsChain(
                symbol="ZS",
                expiry=date(2026, 7, 24),
                as_of=date(2026, 6, 1),
                underlying_settle=1050.0,
                strikes=np.array([1000.0, 1010.0]),
                call_prices=np.array([50.0]),
                put_prices=np.array([5.0, 15.0]),
                call_ivs=None,
                put_ivs=None,
                call_oi=None,
                put_oi=None,
                call_volume=None,
                put_volume=None,
            )


# ---------------------------------------------------------------------------
# Put-call parity (GAP-047)
# ---------------------------------------------------------------------------


class TestPutCallParity:
    def test_parity_passes_on_clean_data(self) -> None:
        """Synthetic chain with exact parity should have zero violations."""
        fwd = 1050.0
        strikes = np.arange(980.0, 1120.0, 10.0)
        tau = 53 / 365.25
        r = 0.05
        discount = np.exp(-r * tau)

        # Set prices to satisfy put-call parity exactly.
        call_prices = np.maximum(fwd - strikes, 0.0) + 10.0
        put_prices = call_prices - (fwd - strikes) * discount

        chain = OptionsChain(
            symbol="ZS",
            expiry=date(2026, 7, 24),
            as_of=date(2026, 6, 1),
            underlying_settle=fwd,
            strikes=strikes,
            call_prices=call_prices,
            put_prices=put_prices,
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )

        violations = check_put_call_parity(chain, risk_free_rate=r)
        assert len(violations) == 0

    def test_parity_fires_on_bad_data(self) -> None:
        """Chain with large parity violations should raise CMEParityError."""
        fwd = 1050.0
        strikes = np.arange(980.0, 1120.0, 10.0)

        # Deliberately wrong: put prices way too high.
        call_prices = np.maximum(fwd - strikes, 0.0) + 10.0
        put_prices = call_prices + 100.0  # massive parity violation

        chain = OptionsChain(
            symbol="ZS",
            expiry=date(2026, 7, 24),
            as_of=date(2026, 6, 1),
            underlying_settle=fwd,
            strikes=strikes,
            call_prices=call_prices,
            put_prices=put_prices,
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )

        with pytest.raises(CMEParityError, match="Put-call parity"):
            check_put_call_parity(chain)

    def test_parity_returns_violation_indices(self) -> None:
        """A few violations below threshold should return indices, not raise."""
        fwd = 1050.0
        n = 20
        strikes = np.arange(980.0, 980.0 + n * 10.0, 10.0)
        tau = 53 / 365.25
        r = 0.05
        discount = np.exp(-r * tau)

        call_prices = np.maximum(fwd - strikes, 0.0) + 10.0
        put_prices = call_prices - (fwd - strikes) * discount

        # Introduce 2 violations (10% < 25% threshold).
        put_prices[0] += 100.0
        put_prices[1] += 100.0

        chain = OptionsChain(
            symbol="ZS",
            expiry=date(2026, 7, 24),
            as_of=date(2026, 6, 1),
            underlying_settle=fwd,
            strikes=strikes,
            call_prices=call_prices,
            put_prices=put_prices,
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )

        violations = check_put_call_parity(chain, risk_free_rate=r)
        assert len(violations) >= 2
        assert 0 in violations
        assert 1 in violations

    def test_parity_skips_expired(self) -> None:
        """Expired chain (expiry <= as_of) should return empty violations."""
        chain = OptionsChain(
            symbol="ZS",
            expiry=date(2026, 6, 1),
            as_of=date(2026, 6, 1),
            underlying_settle=1050.0,
            strikes=np.array([1000.0, 1050.0, 1100.0]),
            call_prices=np.array([50.0, 10.0, 1.0]),
            put_prices=np.array([1.0, 10.0, 50.0]),
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )
        violations = check_put_call_parity(chain)
        assert violations == []


# ---------------------------------------------------------------------------
# Expiry calendar
# ---------------------------------------------------------------------------


class TestExpiryCalendar:
    def test_zs_fnd_known_dates(self) -> None:
        """FND for ZS July 2026 (N26): last BD of June 2026."""
        fnd = _first_notice_date(delivery_month=7, year=2026)
        # June 30, 2026 is a Tuesday -> that's the last BD.
        assert fnd == date(2026, 6, 30)

    def test_zs_options_expiry_july_2026(self) -> None:
        """ZS N26 options expiry: last Friday >= 2 BD before FND."""
        exp = options_expiry("ZS", delivery_month=7, year=2026)
        # FND = 2026-06-30 (Tue). 2 BD back = 2026-06-26 (Fri).
        # 2026-06-26 is a Friday, so that's the answer.
        assert exp == date(2026, 6, 26)
        assert exp.weekday() == 4  # Friday

    def test_zs_options_expiry_is_friday(self) -> None:
        """All options expiries should be Fridays."""
        for month in [1, 3, 5, 7, 8, 9, 11]:
            exp = options_expiry("ZS", month, 2026)
            assert exp.weekday() == 4, f"ZS {month}/2026 expiry {exp} is not Friday"

    def test_zc_options_expiry_is_friday(self) -> None:
        for month in [3, 5, 7, 9, 12]:
            exp = options_expiry("ZC", month, 2026)
            assert exp.weekday() == 4, f"ZC {month}/2026 expiry {exp} is not Friday"

    def test_expiry_schedule_zs_2026(self) -> None:
        sched = expiry_schedule("ZS", 2026)
        assert len(sched) == 7  # 7 delivery months for ZS
        # All should be in chronological order.
        for i in range(1, len(sched)):
            assert sched[i] > sched[i - 1]
        # All should be Fridays.
        for d in sched:
            assert d.weekday() == 4

    def test_expiry_schedule_zc_2026(self) -> None:
        sched = expiry_schedule("ZC", 2026)
        assert len(sched) == 5  # 5 delivery months for ZC
        for d in sched:
            assert d.weekday() == 4

    def test_next_expiry_basic(self) -> None:
        exp = next_expiry("ZS", date(2026, 6, 1))
        assert exp >= date(2026, 6, 1)
        assert exp.weekday() == 4

    def test_next_expiry_on_expiry_day(self) -> None:
        """On expiry day itself, next_expiry should return that day."""
        sched = expiry_schedule("ZS", 2026)
        exp_day = sched[0]
        result = next_expiry("ZS", exp_day)
        assert result == exp_day

    def test_next_expiry_after_last_in_year(self) -> None:
        """After last ZS expiry in 2026, should find 2027 expiry."""
        sched_2026 = expiry_schedule("ZS", 2026)
        after_last = date(sched_2026[-1].year, sched_2026[-1].month, sched_2026[-1].day + 1)
        exp = next_expiry("ZS", after_last)
        assert exp >= after_last

    def test_unsupported_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported symbol"):
            options_expiry("ES", 7, 2026)

    def test_options_expiry_before_fnd(self) -> None:
        """Options expiry must be before FND."""
        for month in [1, 3, 5, 7, 8, 9, 11]:
            exp = options_expiry("ZS", month, 2026)
            fnd = _first_notice_date(month, 2026)
            assert exp < fnd, (
                f"ZS {month}/2026: expiry {exp} >= FND {fnd}"
            )


# ---------------------------------------------------------------------------
# Futures settle puller (mock HTTP)
# ---------------------------------------------------------------------------


class TestFuturesSettle:
    def test_extract_valid_settle(self) -> None:
        data = {
            "settlements": [
                {"month": "JUL 2026", "settle": "1048.25"},
                {"month": "AUG 2026", "settle": "1055.50"},
            ]
        }
        price = _extract_front_month_settle(data, "ZS", date(2026, 6, 15))
        assert price == 1048.25

    def test_extract_skips_empty(self) -> None:
        data = {
            "settlements": [
                {"month": "", "settle": ""},
                {"month": "JUL 2026", "settle": "1048.25"},
            ]
        }
        price = _extract_front_month_settle(data, "ZS", date(2026, 6, 15))
        assert price == 1048.25

    def test_extract_skips_dashes(self) -> None:
        data = {
            "settlements": [
                {"month": "SPREAD", "settle": "-"},
                {"month": "JUL 2026", "settle": "1048.25"},
            ]
        }
        price = _extract_front_month_settle(data, "ZS", date(2026, 6, 15))
        assert price == 1048.25

    def test_extract_no_data_raises(self) -> None:
        data = {"settlements": []}
        with pytest.raises(CMESettleError, match="No settlement records"):
            _extract_front_month_settle(data, "ZS", date(2026, 6, 15))

    def test_extract_all_invalid_raises(self) -> None:
        data = {
            "settlements": [
                {"month": "SPREAD", "settle": "-"},
                {"month": "", "settle": ""},
            ]
        }
        with pytest.raises(CMESettleError, match="No valid settlement"):
            _extract_front_month_settle(data, "ZS", date(2026, 6, 15))

    def test_extract_negative_price_raises(self) -> None:
        data = {
            "settlements": [
                {"month": "JUL 2026", "settle": "-50.0"},
            ]
        }
        with pytest.raises(CMESettleError, match="Invalid settlement"):
            _extract_front_month_settle(data, "ZS", date(2026, 6, 15))

    @pytest.mark.asyncio
    async def test_pull_settle_unsupported_symbol(self) -> None:
        with pytest.raises(CMESettleError, match="Unsupported symbol"):
            await pull_settle("ES", date(2026, 6, 15))

    @pytest.mark.asyncio
    async def test_pull_settle_http_error(self) -> None:
        """Connection failure should raise CMESettleError."""
        with patch("feeds.cme.futures_settle.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value = mock_client

            with pytest.raises(CMESettleError):
                await pull_settle("ZS", date(2026, 6, 15))


# ---------------------------------------------------------------------------
# Options chain puller (mock HTTP)
# ---------------------------------------------------------------------------


class TestOptionsChainPuller:
    def test_parse_settle_price_valid(self) -> None:
        assert _parse_settle_price("1048.25") == 1048.25
        assert _parse_settle_price("1,048.25") == 1048.25

    def test_parse_settle_price_missing(self) -> None:
        assert _parse_settle_price("") is None
        assert _parse_settle_price("-") is None
        assert _parse_settle_price("UNCH") is None

    def test_parse_options_response_valid(self) -> None:
        data = {
            "settlements": [
                {
                    "strike": "1000",
                    "call": "60.5",
                    "put": "10.5",
                    "callIV": "0.25",
                    "putIV": "0.26",
                    "callOI": "1500",
                    "putOI": "800",
                    "callVol": "200",
                    "putVol": "150",
                },
                {
                    "strike": "1050",
                    "call": "30.0",
                    "put": "30.0",
                    "callIV": "0.22",
                    "putIV": "0.23",
                    "callOI": "2000",
                    "putOI": "1800",
                    "callVol": "350",
                    "putVol": "300",
                },
                {
                    "strike": "1100",
                    "call": "10.0",
                    "put": "60.0",
                    "callIV": "0.28",
                    "putIV": "0.29",
                    "callOI": "500",
                    "putOI": "400",
                    "callVol": "100",
                    "putVol": "80",
                },
            ]
        }
        chain = _parse_options_response(
            data, "ZS", date(2026, 7, 24), date(2026, 6, 1), 1050.0
        )
        assert chain.symbol == "ZS"
        assert len(chain.strikes) == 3
        assert chain.strikes[0] == 1000.0
        assert chain.strikes[1] == 1050.0
        assert chain.strikes[2] == 1100.0
        assert chain.call_prices[0] == 60.5
        assert chain.put_prices[2] == 60.0
        assert chain.call_ivs is not None
        assert chain.call_ivs[0] == 0.25
        assert chain.call_oi is not None
        assert chain.call_oi[0] == 1500
        assert chain.underlying_settle == 1050.0

    def test_parse_options_response_empty_raises(self) -> None:
        data = {"settlements": []}
        with pytest.raises(CMEChainError, match="No settlement records"):
            _parse_options_response(
                data, "ZS", date(2026, 7, 24), date(2026, 6, 1), 1050.0
            )

    def test_parse_options_response_no_valid_strikes_raises(self) -> None:
        data = {
            "settlements": [
                {"strike": "-", "call": "10", "put": "10"},
                {"strike": "0", "call": "10", "put": "10"},
            ]
        }
        with pytest.raises(CMEChainError, match="No valid strike data"):
            _parse_options_response(
                data, "ZS", date(2026, 7, 24), date(2026, 6, 1), 1050.0
            )

    def test_parse_options_infers_underlying(self) -> None:
        """When underlying_settle is None, infer from mid-strike parity."""
        data = {
            "settlements": [
                {"strike": "1000", "call": "55.0", "put": "5.0"},
                {"strike": "1050", "call": "25.0", "put": "25.0"},
                {"strike": "1100", "call": "5.0", "put": "55.0"},
            ]
        }
        chain = _parse_options_response(
            data, "ZS", date(2026, 7, 24), date(2026, 6, 1), None
        )
        # At mid-strike (1050): F ~ C - P + K = 25 - 25 + 1050 = 1050
        assert chain.underlying_settle == 1050.0

    @pytest.mark.asyncio
    async def test_pull_chain_unsupported_symbol(self) -> None:
        with pytest.raises(CMEChainError, match="Unsupported symbol"):
            await pull_options_chain("ES", date(2026, 7, 24))

    @pytest.mark.asyncio
    async def test_pull_chain_http_error(self) -> None:
        """Connection failure should raise CMEChainError."""
        with patch("feeds.cme.options_chain.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("timeout")
            mock_client_cls.return_value = mock_client

            with pytest.raises(CMEChainError):
                await pull_options_chain("ZS", date(2026, 7, 24))


# ---------------------------------------------------------------------------
# Sorted output guarantee
# ---------------------------------------------------------------------------


class TestChainSorting:
    def test_parse_sorts_by_strike(self) -> None:
        """Strikes should be sorted ascending regardless of input order."""
        data = {
            "settlements": [
                {"strike": "1100", "call": "5.0", "put": "55.0"},
                {"strike": "1000", "call": "55.0", "put": "5.0"},
                {"strike": "1050", "call": "25.0", "put": "25.0"},
            ]
        }
        chain = _parse_options_response(
            data, "ZS", date(2026, 7, 24), date(2026, 6, 1), 1050.0
        )
        assert np.all(np.diff(chain.strikes) > 0)
        assert chain.strikes[0] == 1000.0
        assert chain.call_prices[0] == 55.0  # 1000-strike call
