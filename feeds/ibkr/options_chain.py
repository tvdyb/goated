"""ZS options chain puller via IBKR IB Gateway (ib_insync).

Replaces the CME public endpoint (blocked by anti-scraping) with the
same data sourced from Interactive Brokers' API.

Returns an OptionsChain dataclass compatible with engine/rnd/pipeline.compute_rnd().

ib_insync imports are deferred so CI environments without IB Gateway still work.

Non-negotiables: no pandas, fail-loud, asyncio for I/O only.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import date, datetime
from typing import Any

import numpy as np

from feeds.cme.errors import CMEChainError
from feeds.cme.options_chain import OptionsChain

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class IBKRChainError(CMEChainError):
    """Options chain pull via IBKR failed."""


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class _ChainCache:
    """Simple in-memory TTL cache for an OptionsChain."""

    __slots__ = ("_chain", "_timestamp", "_ttl_s")

    def __init__(self, ttl_s: float = 900.0) -> None:
        self._chain: OptionsChain | None = None
        self._timestamp: float = 0.0
        self._ttl_s = ttl_s

    def get(self, symbol: str, expiry: date) -> OptionsChain | None:
        if self._chain is None:
            return None
        if time.monotonic() - self._timestamp > self._ttl_s:
            self._chain = None
            return None
        if self._chain.symbol != symbol or self._chain.expiry != expiry:
            return None
        return self._chain

    def put(self, chain: OptionsChain) -> None:
        self._chain = chain
        self._timestamp = time.monotonic()

    def invalidate(self) -> None:
        self._chain = None
        self._timestamp = 0.0


# ---------------------------------------------------------------------------
# IBKROptionsChainPuller
# ---------------------------------------------------------------------------


class IBKROptionsChainPuller:
    """Pull ZS (or ZC) options chain from IB Gateway via ib_insync.

    Usage::

        puller = IBKROptionsChainPuller()
        await puller.connect()
        chain = await puller.pull("ZS")
        await puller.disconnect()
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 10,
        cache_ttl_s: float = 900.0,
        request_timeout_s: float = 30.0,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._cache = _ChainCache(ttl_s=cache_ttl_s)
        self._request_timeout_s = request_timeout_s
        self._ib: Any = None  # ib_insync.IB
        self._connected: bool = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to IB Gateway."""
        try:
            from ib_insync import IB  # noqa: PLC0415
        except ImportError as exc:
            raise IBKRChainError(
                "ib_insync not installed. Install with: pip install ib_insync",
                source="ibkr_options_chain",
            ) from exc

        ib = IB()
        try:
            await ib.connectAsync(
                self._host, self._port, clientId=self._client_id
            )
        except Exception as exc:
            raise IBKRChainError(
                f"Failed to connect to IB Gateway at "
                f"{self._host}:{self._port}: {exc}",
                source="ibkr_options_chain",
            ) from exc

        self._ib = ib
        self._connected = True
        logger.info(
            "IBKR chain: connected to %s:%d (client_id=%d)",
            self._host, self._port, self._client_id,
        )

    async def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        if self._ib is not None:
            self._ib.disconnect()
            self._ib = None
        self._connected = False
        logger.info("IBKR chain: disconnected")

    async def pull(
        self,
        symbol: str = "ZS",
        expiry: date | None = None,
    ) -> OptionsChain:
        """Pull the front-month options chain for a futures symbol.

        Args:
            symbol: Futures symbol ("ZS" for soybeans, "ZC" for corn).
            expiry: Specific expiry date. If None, uses front-month.

        Returns:
            OptionsChain compatible with engine/rnd/pipeline.compute_rnd().

        Raises:
            IBKRChainError: On connection, data, or parsing errors.
        """
        if not self._connected or self._ib is None:
            raise IBKRChainError(
                "Not connected to IB Gateway",
                source="ibkr_options_chain",
            )

        # Check cache
        if expiry is not None:
            cached = self._cache.get(symbol, expiry)
            if cached is not None:
                logger.debug("IBKR chain: cache hit for %s %s", symbol, expiry)
                return cached

        try:
            chain = await asyncio.wait_for(
                self._pull_chain(symbol, expiry),
                timeout=self._request_timeout_s,
            )
        except TimeoutError as exc:
            raise IBKRChainError(
                f"Timeout ({self._request_timeout_s}s) pulling {symbol} "
                f"options chain from IBKR",
                source="ibkr_options_chain",
            ) from exc

        self._cache.put(chain)
        return chain

    async def _pull_chain(
        self,
        symbol: str,
        target_expiry: date | None,
    ) -> OptionsChain:
        """Internal: pull and parse options chain."""
        ib = self._ib

        # 1. Qualify underlying + get price
        underlying = await self._qualify_underlying(ib, symbol)
        underlying_price = await self._get_underlying_price(ib, underlying)

        # 2. Get option params and resolve expiry
        params = await self._get_opt_params(ib, underlying, symbol)
        expiry_str, target_expiry = self._resolve_expiry(
            params, symbol, target_expiry
        )

        # 3. Filter strikes and build/qualify option contracts
        strikes = _filter_strikes(params.strikes, underlying_price)
        valid_calls, valid_puts = await self._build_and_qualify_contracts(
            ib, symbol, expiry_str, strikes, params.exchange
        )

        # 4. Request market data and parse into OptionsChain
        return await self._request_and_build_chain(
            ib, symbol, target_expiry, underlying_price,
            valid_calls, valid_puts,
        )

    async def _qualify_underlying(
        self, ib: Any, symbol: str
    ) -> Any:
        """Qualify the underlying futures contract on CBOT."""
        from ib_insync import Future  # noqa: PLC0415

        underlying = Future(symbol=symbol, exchange="CBOT")
        try:
            qualified = await ib.qualifyContractsAsync(underlying)
            if not qualified:
                raise IBKRChainError(
                    f"Could not qualify underlying contract {symbol} on CBOT",
                    source="ibkr_options_chain",
                )
            return qualified[0]
        except IBKRChainError:
            raise
        except Exception as exc:
            raise IBKRChainError(
                f"Failed to qualify underlying {symbol}: {exc}",
                source="ibkr_options_chain",
            ) from exc

    async def _get_opt_params(
        self, ib: Any, underlying: Any, symbol: str
    ) -> Any:
        """Fetch option definition params and find CBOT exchange."""
        try:
            opt_params_list = await ib.reqSecDefOptParamsAsync(
                underlying.symbol,
                "",
                underlying.secType,
                underlying.conId,
            )
        except Exception as exc:
            raise IBKRChainError(
                f"Failed to get option params for {symbol}: {exc}",
                source="ibkr_options_chain",
            ) from exc

        if not opt_params_list:
            raise IBKRChainError(
                f"No option parameters returned for {symbol}",
                source="ibkr_options_chain",
            )

        for p in opt_params_list:
            if p.exchange in ("CBOT", "ECBOT", "SMART"):
                return p
        return opt_params_list[0]

    def _resolve_expiry(
        self,
        params: Any,
        symbol: str,
        target_expiry: date | None,
    ) -> tuple[str, date]:
        """Select expiry string and date from available expirations."""
        expirations = sorted(params.expirations)
        if not expirations:
            raise IBKRChainError(
                f"No expirations available for {symbol} options",
                source="ibkr_options_chain",
            )

        if target_expiry is not None:
            expiry_str = target_expiry.strftime("%Y%m%d")
            if expiry_str not in expirations:
                raise IBKRChainError(
                    f"Requested expiry {target_expiry} not available. "
                    f"Available: {expirations[:5]}...",
                    source="ibkr_options_chain",
                )
            return expiry_str, target_expiry

        today_str = date.today().strftime("%Y%m%d")
        future_exps = [e for e in expirations if e >= today_str]
        if not future_exps:
            raise IBKRChainError(
                f"No future expirations for {symbol} options",
                source="ibkr_options_chain",
            )
        expiry_str = future_exps[0]
        return expiry_str, datetime.strptime(expiry_str, "%Y%m%d").date()

    async def _build_and_qualify_contracts(
        self,
        ib: Any,
        symbol: str,
        expiry_str: str,
        strikes: list[float],
        exchange: str,
    ) -> tuple[list[Any], list[Any]]:
        """Build FuturesOption contracts, qualify, return valid pairs."""
        from ib_insync import FuturesOption  # noqa: PLC0415

        call_contracts = [
            FuturesOption(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry_str,
                strike=s, right="C", exchange=exchange,
            )
            for s in strikes
        ]
        put_contracts = [
            FuturesOption(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiry_str,
                strike=s, right="P", exchange=exchange,
            )
            for s in strikes
        ]

        all_contracts = call_contracts + put_contracts
        try:
            await ib.qualifyContractsAsync(*all_contracts)
        except Exception as exc:
            raise IBKRChainError(
                f"Failed to qualify option contracts: {exc}",
                source="ibkr_options_chain",
            ) from exc

        n = len(strikes)
        valid_calls: list[Any] = []
        valid_puts: list[Any] = []
        for i in range(n):
            c = all_contracts[i]
            p = all_contracts[n + i]
            if c.conId and p.conId:
                valid_calls.append(c)
                valid_puts.append(p)

        if len(valid_calls) < 5:
            raise IBKRChainError(
                f"Only {len(valid_calls)} strikes qualified (need >= 5)",
                source="ibkr_options_chain",
            )
        return valid_calls, valid_puts

    async def _request_and_build_chain(
        self,
        ib: Any,
        symbol: str,
        target_expiry: date,
        underlying_price: float,
        valid_calls: list[Any],
        valid_puts: list[Any],
    ) -> OptionsChain:
        """Request market data for option contracts and build OptionsChain."""
        call_tickers = [
            ib.reqMktData(c, genericTickList="", snapshot=True)
            for c in valid_calls
        ]
        put_tickers = [
            ib.reqMktData(p, genericTickList="", snapshot=True)
            for p in valid_puts
        ]

        await asyncio.sleep(2.0)
        await ib.sleep(0.1)

        parsed = _parse_ticker_data(valid_calls, call_tickers, put_tickers)

        # Cancel subscriptions
        for t in call_tickers + put_tickers:
            ib.cancelMktData(t.contract)

        if len(parsed.strikes) < 5:
            raise IBKRChainError(
                f"Only {len(parsed.strikes)} strikes with valid prices "
                f"(need >= 5). Check market data subscription.",
                source="ibkr_options_chain",
            )

        strikes_arr = np.array(parsed.strikes, dtype=np.float64)
        order = np.argsort(strikes_arr, kind="stable")
        strikes_arr = strikes_arr[order]
        call_prices_arr = np.array(parsed.call_prices, dtype=np.float64)[order]
        put_prices_arr = np.array(parsed.put_prices, dtype=np.float64)[order]

        chain = OptionsChain(
            symbol=symbol,
            expiry=target_expiry,
            as_of=date.today(),
            underlying_settle=underlying_price,
            strikes=strikes_arr,
            call_prices=call_prices_arr,
            put_prices=put_prices_arr,
            call_ivs=_build_float_array(parsed.call_ivs, order),
            put_ivs=_build_float_array(parsed.put_ivs, order),
            call_oi=_build_int_array(parsed.call_oi, order),
            put_oi=_build_int_array(parsed.put_oi, order),
            call_volume=_build_int_array(parsed.call_volume, order),
            put_volume=_build_int_array(parsed.put_volume, order),
        )

        logger.info(
            "IBKR chain: pulled %s expiry=%s — %d strikes, "
            "underlying=%.2f, price range=[%.2f, %.2f]",
            symbol, target_expiry, len(parsed.strikes),
            underlying_price, strikes_arr[0], strikes_arr[-1],
        )
        return chain

    async def _get_underlying_price(self, ib: Any, contract: Any) -> float:
        """Get last/close price for the underlying futures contract."""
        try:
            ticker = ib.reqMktData(contract, genericTickList="", snapshot=True)
            await asyncio.sleep(1.0)
            await ib.sleep(0.1)

            price = _extract_price(ticker)
            ib.cancelMktData(contract)

            if price is None or price <= 0:
                raise IBKRChainError(
                    f"No price data for underlying {contract.symbol}. "
                    f"Check market data subscription.",
                    source="ibkr_options_chain",
                )
            return price
        except IBKRChainError:
            raise
        except Exception as exc:
            raise IBKRChainError(
                f"Failed to get underlying price for {contract.symbol}: {exc}",
                source="ibkr_options_chain",
            ) from exc


# ---------------------------------------------------------------------------
# Ticker data extraction helpers
# ---------------------------------------------------------------------------


def _filter_strikes(
    all_strikes_raw: list[float], underlying_price: float
) -> list[float]:
    """Filter strikes to a reasonable range around the money."""
    all_strikes = sorted(all_strikes_raw)
    if not all_strikes:
        raise IBKRChainError(
            "No strikes available for options",
            source="ibkr_options_chain",
        )
    lo = underlying_price * 0.7
    hi = underlying_price * 1.3
    strikes = [s for s in all_strikes if lo <= s <= hi]
    if len(strikes) < 5:
        strikes = sorted(
            all_strikes,
            key=lambda s: abs(s - underlying_price),
        )[:60]
        strikes.sort()
    return strikes


class _ParsedTickerData:
    """Container for parsed ticker data arrays."""

    __slots__ = (
        "strikes", "call_prices", "put_prices",
        "call_ivs", "put_ivs",
        "call_oi", "put_oi",
        "call_volume", "put_volume",
    )

    def __init__(self) -> None:
        self.strikes: list[float] = []
        self.call_prices: list[float] = []
        self.put_prices: list[float] = []
        self.call_ivs: list[float | None] = []
        self.put_ivs: list[float | None] = []
        self.call_oi: list[int | None] = []
        self.put_oi: list[int | None] = []
        self.call_volume: list[int | None] = []
        self.put_volume: list[int | None] = []


def _parse_ticker_data(
    valid_calls: list[Any],
    call_tickers: list[Any],
    put_tickers: list[Any],
) -> _ParsedTickerData:
    """Parse ticker snapshots into structured data."""
    parsed = _ParsedTickerData()
    for i in range(len(valid_calls)):
        ct = call_tickers[i]
        pt = put_tickers[i]

        c_price = _extract_price(ct)
        p_price = _extract_price(pt)
        if c_price is None or p_price is None:
            continue
        if c_price <= 0 or p_price <= 0:
            continue

        parsed.strikes.append(valid_calls[i].strike)
        parsed.call_prices.append(c_price)
        parsed.put_prices.append(p_price)
        parsed.call_ivs.append(_extract_iv(ct))
        parsed.put_ivs.append(_extract_iv(pt))
        parsed.call_oi.append(_extract_int(ct, "openInterest"))
        parsed.put_oi.append(_extract_int(pt, "openInterest"))
        parsed.call_volume.append(_extract_int(ct, "volume"))
        parsed.put_volume.append(_extract_int(pt, "volume"))
    return parsed


def _extract_price(ticker: Any) -> float | None:
    """Extract best available price from an ib_insync Ticker."""
    # Prefer last price, then close, then mid of bid/ask
    if _is_valid(ticker.last):
        return float(ticker.last)
    if _is_valid(ticker.close):
        return float(ticker.close)
    bid = ticker.bid if _is_valid(ticker.bid) else None
    ask = ticker.ask if _is_valid(ticker.ask) else None
    if bid is not None and ask is not None:
        return (float(bid) + float(ask)) / 2.0
    return None


def _extract_iv(ticker: Any) -> float | None:
    """Extract model IV from ticker if available."""
    if hasattr(ticker, "modelGreeks") and ticker.modelGreeks is not None:
        iv = ticker.modelGreeks.impliedVol
        if _is_valid(iv) and 0.001 < iv < 5.0:
            return float(iv)
    return None


def _extract_int(ticker: Any, field: str) -> int | None:
    """Extract an integer field (volume, openInterest) from ticker."""
    val = getattr(ticker, field, None)
    if val is not None and _is_valid(val):
        return int(val)
    return None


def _is_valid(val: Any) -> bool:
    """Check if a numeric value is valid (not NaN, not None, not -1)."""
    if val is None:
        return False
    try:
        return math.isfinite(float(val)) and float(val) > -1
    except (ValueError, TypeError):
        return False


def _build_float_array(
    lst: list[float | None], order: np.ndarray
) -> np.ndarray | None:
    """Build a sorted float64 array, or None if all entries are None."""
    if all(v is None for v in lst):
        return None
    arr = np.array(
        [v if v is not None else np.nan for v in lst], dtype=np.float64
    )
    return arr[order]


def _build_int_array(
    lst: list[int | None], order: np.ndarray
) -> np.ndarray | None:
    """Build a sorted int64 array, or None if all entries are None."""
    if all(v is None for v in lst):
        return None
    arr = np.array(
        [v if v is not None else 0 for v in lst], dtype=np.int64
    )
    return arr[order]


# ---------------------------------------------------------------------------
# Convenience: one-shot pull
# ---------------------------------------------------------------------------


async def pull_ibkr_options_chain(
    symbol: str = "ZS",
    expiry: date | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 4002,
    client_id: int = 10,
    cache_ttl_s: float = 900.0,
) -> OptionsChain:
    """One-shot convenience: connect, pull, disconnect.

    For repeated use, prefer IBKROptionsChainPuller with a persistent
    connection (avoids reconnect overhead each cycle).
    """
    puller = IBKROptionsChainPuller(
        host=host, port=port, client_id=client_id, cache_ttl_s=cache_ttl_s
    )
    await puller.connect()
    try:
        return await puller.pull(symbol, expiry)
    finally:
        await puller.disconnect()
