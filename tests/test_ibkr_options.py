"""Tests for feeds/ibkr/options_chain.py — IBKR options chain puller.

All IB interactions are mocked via unittest.mock (no IB Gateway needed).
"""

from __future__ import annotations

import sys
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Mock ib_insync module so tests run without IB Gateway
# ---------------------------------------------------------------------------

def _mock_future(**kwargs):
    ns = SimpleNamespace(
        symbol=kwargs.get("symbol", "ZS"),
        exchange=kwargs.get("exchange", "CBOT"),
        secType=kwargs.get("secType", "FUT"),
        conId=kwargs.get("conId", 0),
        lastTradeDateOrContractMonth=kwargs.get("lastTradeDateOrContractMonth", ""),
    )
    return ns

def _mock_fop(**kwargs):
    ns = SimpleNamespace(
        symbol=kwargs.get("symbol", "ZS"),
        exchange=kwargs.get("exchange", "CBOT"),
        secType="FOP",
        conId=kwargs.get("conId", 0),
        lastTradeDateOrContractMonth=kwargs.get("lastTradeDateOrContractMonth", ""),
        strike=kwargs.get("strike", 0.0),
        right=kwargs.get("right", "C"),
    )
    return ns

_ib_insync_mock = SimpleNamespace(
    IB=MagicMock,
    Future=_mock_future,
    FuturesOption=_mock_fop,
)

# Install mock before importing the module under test
sys.modules.setdefault("ib_insync", _ib_insync_mock)

from feeds.cme.options_chain import OptionsChain  # noqa: E402
from feeds.ibkr.options_chain import (  # noqa: E402
    IBKRChainError,
    IBKROptionsChainPuller,
    _build_float_array,
    _build_int_array,
    _ChainCache,
    _extract_iv,
    _extract_price,
    _is_valid,
)

# ---------------------------------------------------------------------------
# Fixtures: mock IB objects
# ---------------------------------------------------------------------------

def _make_ticker(
    last: float | None = None,
    close: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    iv: float | None = None,
    volume: int | None = None,
    open_interest: int | None = None,
) -> SimpleNamespace:
    """Create a mock ib_insync Ticker."""
    greeks = None
    if iv is not None:
        greeks = SimpleNamespace(impliedVol=iv)
    t = SimpleNamespace(
        last=last,
        close=close,
        bid=bid,
        ask=ask,
        modelGreeks=greeks,
        volume=volume,
        openInterest=open_interest,
        contract=SimpleNamespace(conId=123),
    )
    return t


def _make_contract(
    symbol: str = "ZS", strike: float = 1000.0, right: str = "C", con_id: int = 1,
) -> SimpleNamespace:
    """Create a mock ib_insync contract."""
    return SimpleNamespace(
        symbol=symbol,
        exchange="CBOT",
        secType="FUT",
        conId=con_id,
        strike=strike,
        right=right,
    )


def _make_opt_params(
    exchange: str = "CBOT",
    expirations: list[str] | None = None,
    strikes: list[float] | None = None,
) -> SimpleNamespace:
    """Create a mock OptionParams object."""
    if expirations is None:
        expirations = ["20260601", "20260715", "20260815"]
    if strikes is None:
        strikes = [float(s) for s in range(900, 1200, 10)]
    return SimpleNamespace(
        exchange=exchange,
        expirations=expirations,
        strikes=strikes,
    )


# ---------------------------------------------------------------------------
# _extract_price tests
# ---------------------------------------------------------------------------


class TestExtractPrice:
    def test_last_price(self) -> None:
        t = _make_ticker(last=1050.0)
        assert _extract_price(t) == 1050.0

    def test_close_fallback(self) -> None:
        t = _make_ticker(last=float("nan"), close=1045.0)
        assert _extract_price(t) == 1045.0

    def test_midpoint_fallback(self) -> None:
        t = _make_ticker(last=float("nan"), close=float("nan"), bid=1040.0, ask=1060.0)
        assert _extract_price(t) == 1050.0

    def test_none_when_no_data(self) -> None:
        t = _make_ticker()
        assert _extract_price(t) is None

    def test_none_when_all_nan(self) -> None:
        t = _make_ticker(
            last=float("nan"), close=float("nan"),
            bid=float("nan"), ask=float("nan"),
        )
        assert _extract_price(t) is None


# ---------------------------------------------------------------------------
# _extract_iv tests
# ---------------------------------------------------------------------------


class TestExtractIV:
    def test_valid_iv(self) -> None:
        t = _make_ticker(iv=0.25)
        assert _extract_iv(t) == 0.25

    def test_no_greeks(self) -> None:
        t = _make_ticker()
        assert _extract_iv(t) is None

    def test_nan_iv(self) -> None:
        t = _make_ticker(iv=float("nan"))
        assert _extract_iv(t) is None

    def test_zero_iv(self) -> None:
        t = _make_ticker(iv=0.0)
        assert _extract_iv(t) is None

    def test_extreme_iv(self) -> None:
        t = _make_ticker(iv=6.0)
        assert _extract_iv(t) is None


# ---------------------------------------------------------------------------
# _is_valid tests
# ---------------------------------------------------------------------------


class TestIsValid:
    def test_valid(self) -> None:
        assert _is_valid(1.0) is True
        assert _is_valid(0.0) is True
        assert _is_valid(100) is True

    def test_none(self) -> None:
        assert _is_valid(None) is False

    def test_nan(self) -> None:
        assert _is_valid(float("nan")) is False

    def test_inf(self) -> None:
        assert _is_valid(float("inf")) is False

    def test_negative_one(self) -> None:
        assert _is_valid(-1) is False


# ---------------------------------------------------------------------------
# _build_float_array / _build_int_array tests
# ---------------------------------------------------------------------------


class TestBuildArrays:
    def test_float_array(self) -> None:
        order = np.array([2, 0, 1])
        result = _build_float_array([0.3, 0.2, 0.1], order)
        assert result is not None
        np.testing.assert_allclose(result, [0.1, 0.3, 0.2])

    def test_float_array_all_none(self) -> None:
        order = np.array([0, 1])
        assert _build_float_array([None, None], order) is None

    def test_int_array(self) -> None:
        order = np.array([1, 0])
        result = _build_int_array([100, 200], order)
        assert result is not None
        np.testing.assert_array_equal(result, [200, 100])

    def test_int_array_all_none(self) -> None:
        order = np.array([0])
        assert _build_int_array([None], order) is None


# ---------------------------------------------------------------------------
# _ChainCache tests
# ---------------------------------------------------------------------------


class TestChainCache:
    def _make_chain(self, symbol: str = "ZS", expiry: date | None = None) -> OptionsChain:
        if expiry is None:
            expiry = date(2026, 6, 1)
        n = 10
        return OptionsChain(
            symbol=symbol,
            expiry=expiry,
            as_of=date.today(),
            underlying_settle=1050.0,
            strikes=np.arange(1000, 1000 + n * 10, 10, dtype=np.float64),
            call_prices=np.full(n, 50.0),
            put_prices=np.full(n, 50.0),
            call_ivs=None,
            put_ivs=None,
            call_oi=None,
            put_oi=None,
            call_volume=None,
            put_volume=None,
        )

    def test_cache_miss_empty(self) -> None:
        cache = _ChainCache(ttl_s=60.0)
        assert cache.get("ZS", date(2026, 6, 1)) is None

    def test_cache_hit(self) -> None:
        cache = _ChainCache(ttl_s=60.0)
        chain = self._make_chain()
        cache.put(chain)
        assert cache.get("ZS", date(2026, 6, 1)) is chain

    def test_cache_miss_wrong_symbol(self) -> None:
        cache = _ChainCache(ttl_s=60.0)
        cache.put(self._make_chain(symbol="ZS"))
        assert cache.get("ZC", date(2026, 6, 1)) is None

    def test_cache_miss_wrong_expiry(self) -> None:
        cache = _ChainCache(ttl_s=60.0)
        cache.put(self._make_chain())
        assert cache.get("ZS", date(2026, 7, 1)) is None

    def test_cache_invalidate(self) -> None:
        cache = _ChainCache(ttl_s=60.0)
        cache.put(self._make_chain())
        cache.invalidate()
        assert cache.get("ZS", date(2026, 6, 1)) is None

    def test_cache_expiry(self) -> None:
        cache = _ChainCache(ttl_s=0.01)  # 10ms TTL
        cache.put(self._make_chain())
        time.sleep(0.02)
        assert cache.get("ZS", date(2026, 6, 1)) is None


# ---------------------------------------------------------------------------
# IBKROptionsChainPuller tests (mocked IB)
# ---------------------------------------------------------------------------


class TestIBKROptionsChainPuller:
    """Tests with fully mocked ib_insync."""

    def _setup_mock_ib(self) -> MagicMock:
        """Create a mock IB instance with standard responses."""
        ib = MagicMock()

        # connectAsync
        ib.connectAsync = AsyncMock()

        # qualifyContractsAsync — returns contracts with conId set
        async def _qualify(*contracts):
            result = []
            for c in contracts:
                c.conId = 12345
                result.append(c)
            return result

        ib.qualifyContractsAsync = AsyncMock(side_effect=_qualify)

        # reqSecDefOptParamsAsync
        ib.reqSecDefOptParamsAsync = AsyncMock(return_value=[
            _make_opt_params()
        ])

        # reqMktData — returns a ticker with prices
        def _req_mkt_data(contract, genericTickList="", snapshot=False):  # noqa: N803
            strike = getattr(contract, "strike", 1050.0)
            right = getattr(contract, "right", None)
            if right == "C":
                price = max(0.1, 1050.0 - strike + 20.0)
            elif right == "P":
                price = max(0.1, strike - 1050.0 + 20.0)
            else:
                price = 1050.0  # underlying
            return _make_ticker(last=price, iv=0.20, volume=100, open_interest=5000)

        ib.reqMktData = MagicMock(side_effect=_req_mkt_data)
        ib.cancelMktData = MagicMock()

        # sleep
        ib.sleep = AsyncMock()

        # disconnect
        ib.disconnect = MagicMock()

        return ib

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        self._setup_mock_ib()

        with patch("feeds.ibkr.options_chain.IBKROptionsChainPuller.connect") as mock_connect:
            mock_connect.return_value = None
            puller = IBKROptionsChainPuller()
            await puller.connect()
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_pull_not_connected(self) -> None:
        puller = IBKROptionsChainPuller()
        with pytest.raises(IBKRChainError, match="Not connected"):
            await puller.pull("ZS")

    @pytest.mark.asyncio
    async def test_pull_returns_options_chain(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        chain = await puller.pull("ZS", expiry=date(2026, 6, 1))

        assert isinstance(chain, OptionsChain)
        assert chain.symbol == "ZS"
        assert chain.expiry == date(2026, 6, 1)
        assert len(chain.strikes) >= 5
        assert chain.underlying_settle > 0
        assert len(chain.call_prices) == len(chain.strikes)
        assert len(chain.put_prices) == len(chain.strikes)

    @pytest.mark.asyncio
    async def test_pull_strikes_sorted(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        chain = await puller.pull("ZS", expiry=date(2026, 6, 1))
        # Strikes must be sorted ascending
        assert np.all(np.diff(chain.strikes) >= 0)

    @pytest.mark.asyncio
    async def test_pull_caches_result(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller(cache_ttl_s=60.0)
        puller._ib = mock_ib
        puller._connected = True

        chain1 = await puller.pull("ZS", expiry=date(2026, 6, 1))
        chain2 = await puller.pull("ZS", expiry=date(2026, 6, 1))

        # Second call should return cached result
        assert chain2 is chain1

    @pytest.mark.asyncio
    async def test_pull_no_expiry_uses_front_month(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        chain = await puller.pull("ZS")
        assert isinstance(chain, OptionsChain)
        assert chain.expiry >= date.today()

    @pytest.mark.asyncio
    async def test_pull_invalid_expiry_raises(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        with pytest.raises(IBKRChainError, match="not available"):
            await puller.pull("ZS", expiry=date(2099, 1, 1))

    @pytest.mark.asyncio
    async def test_pull_no_opt_params_raises(self) -> None:
        mock_ib = self._setup_mock_ib()
        mock_ib.reqSecDefOptParamsAsync = AsyncMock(return_value=[])
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        with pytest.raises(IBKRChainError, match="No option parameters"):
            await puller.pull("ZS", expiry=date(2026, 6, 1))

    @pytest.mark.asyncio
    async def test_pull_qualify_fails_raises(self) -> None:
        mock_ib = self._setup_mock_ib()
        mock_ib.qualifyContractsAsync = AsyncMock(return_value=[])
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        with pytest.raises(IBKRChainError, match="Could not qualify"):
            await puller.pull("ZS", expiry=date(2026, 6, 1))

    @pytest.mark.asyncio
    async def test_pull_no_price_data_raises(self) -> None:
        mock_ib = self._setup_mock_ib()
        # Return tickers with no valid prices
        mock_ib.reqMktData = MagicMock(
            return_value=_make_ticker()  # all None
        )
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        with pytest.raises(IBKRChainError):
            await puller.pull("ZS", expiry=date(2026, 6, 1))

    @pytest.mark.asyncio
    async def test_chain_compatible_with_rnd_pipeline(self) -> None:
        """Verify the returned chain has the right structure for compute_rnd."""
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        chain = await puller.pull("ZS", expiry=date(2026, 6, 1))

        # OptionsChain fields required by pipeline.compute_rnd
        assert hasattr(chain, "symbol")
        assert hasattr(chain, "expiry")
        assert hasattr(chain, "as_of")
        assert hasattr(chain, "underlying_settle")
        assert hasattr(chain, "strikes")
        assert hasattr(chain, "call_prices")
        assert hasattr(chain, "put_prices")
        assert hasattr(chain, "call_ivs")
        assert hasattr(chain, "put_ivs")

        # Numpy arrays
        assert isinstance(chain.strikes, np.ndarray)
        assert isinstance(chain.call_prices, np.ndarray)
        assert isinstance(chain.put_prices, np.ndarray)
        assert chain.strikes.dtype == np.float64
        assert chain.call_prices.dtype == np.float64

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        mock_ib = self._setup_mock_ib()
        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        await puller.disconnect()

        assert puller._connected is False
        assert puller._ib is None
        mock_ib.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_underlying_price_no_data_raises(self) -> None:
        mock_ib = self._setup_mock_ib()

        # First call (underlying) returns no price, subsequent calls return prices
        call_count = 0
        def _req_mkt_no_underlying(contract, genericTickList="", snapshot=False):  # noqa: N803
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_ticker()  # No price for underlying
            return _make_ticker(last=50.0, iv=0.2)

        mock_ib.reqMktData = MagicMock(side_effect=_req_mkt_no_underlying)

        puller = IBKROptionsChainPuller()
        puller._ib = mock_ib
        puller._connected = True

        with pytest.raises(IBKRChainError, match="No price data"):
            await puller.pull("ZS", expiry=date(2026, 6, 1))


# ---------------------------------------------------------------------------
# IBKRChainError tests
# ---------------------------------------------------------------------------


class TestIBKRChainError:
    def test_inherits_from_cme_chain_error(self) -> None:
        from feeds.cme.errors import CMEChainError  # noqa: PLC0415
        err = IBKRChainError("test", source="test")
        assert isinstance(err, CMEChainError)

    def test_source_attribute(self) -> None:
        err = IBKRChainError("detail", source="ibkr")
        assert err.source == "ibkr"
        assert "detail" in str(err)
