"""IB Gateway async wrapper via ib_insync.

Provides IBKRClient for connecting to IB Gateway, placing hedge orders
on CBOT futures (ZS, ZC), querying positions, and monitoring connectivity.

Connection monitoring: heartbeat every 5s. If no response for N seconds
(configurable, default 15s per OD-25), raises HedgeConnectionError which
triggers the kill switch on the Kalshi side.

Reconnect logic: exponential backoff (1s, 2s, 4s, 8s, max 30s).

Non-negotiables: no pandas, fail-loud, type hints, asyncio for I/O only.

Note: ib_insync imports are deferred because the package may not be
installed in all environments (CI, dev without IB Gateway).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class HedgeConnectionError(RuntimeError):
    """Raised when IB Gateway connection is lost beyond the timeout."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"IB connection failure: {detail}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_HEARTBEAT_INTERVAL_S: float = 5.0
_DEFAULT_DISCONNECT_TIMEOUT_S: float = 15.0
_MAX_RECONNECT_BACKOFF_S: float = 30.0


# ---------------------------------------------------------------------------
# IBKRClient
# ---------------------------------------------------------------------------


class IBKRClient:
    """Async wrapper around IB Gateway via ib_insync.

    Usage::

        client = IBKRClient()
        await client.connect("127.0.0.1", 4002, client_id=1)
        await client.place_hedge("ZS", quantity=2, side="sell")
        await client.disconnect()
    """

    def __init__(
        self,
        *,
        heartbeat_interval_s: float = _DEFAULT_HEARTBEAT_INTERVAL_S,
        disconnect_timeout_s: float = _DEFAULT_DISCONNECT_TIMEOUT_S,
    ) -> None:
        self._heartbeat_interval_s = heartbeat_interval_s
        self._disconnect_timeout_s = disconnect_timeout_s
        self._ib: object | None = None  # ib_insync.IB instance
        self._connected: bool = False
        self._last_heartbeat: float = 0.0
        self._heartbeat_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._host: str = ""
        self._port: int = 0
        self._client_id: int = 0

    @property
    def connected(self) -> bool:
        """Whether the client is currently connected to IB Gateway."""
        return self._connected

    async def connect(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
    ) -> None:
        """Connect to IB Gateway.

        Args:
            host: IB Gateway host.
            port: IB Gateway port (4001=live, 4002=paper).
            client_id: TWS API client ID.

        Raises:
            HedgeConnectionError: If connection fails.
        """
        try:
            from ib_insync import IB  # noqa: PLC0415
        except ImportError as exc:
            raise HedgeConnectionError(
                "ib_insync not installed. Install with: pip install ib_insync"
            ) from exc

        self._host = host
        self._port = port
        self._client_id = client_id

        ib = IB()
        try:
            await ib.connectAsync(host, port, clientId=client_id)
        except Exception as exc:
            raise HedgeConnectionError(
                f"Failed to connect to IB Gateway at {host}:{port}: {exc}"
            ) from exc

        self._ib = ib
        self._connected = True
        self._last_heartbeat = time.monotonic()

        # Start heartbeat monitor
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

        logger.info(
            "IBKR: connected to %s:%d (client_id=%d)", host, port, client_id
        )

    async def place_hedge(
        self,
        symbol: str,
        quantity: int,
        side: str,
    ) -> dict:
        """Place a hedge order on CBOT futures.

        Args:
            symbol: Futures symbol (e.g. "ZS", "ZC").
            quantity: Number of contracts (positive).
            side: "buy" or "sell".

        Returns:
            Trade result dict with order details.

        Raises:
            HedgeConnectionError: If not connected.
            ValueError: If side is invalid or quantity <= 0.
        """
        if not self._connected or self._ib is None:
            raise HedgeConnectionError("Not connected to IB Gateway")
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")

        from ib_insync import Future, MarketOrder  # noqa: PLC0415

        contract = Future(symbol=symbol, exchange="CBOT")
        action = "BUY" if side == "buy" else "SELL"
        order = MarketOrder(action, quantity)

        logger.warning(
            "IBKR: placing hedge — %s %d %s", action, quantity, symbol
        )

        try:
            trade = self._ib.placeOrder(contract, order)
            # Wait briefly for fill acknowledgement
            await asyncio.sleep(0.1)
            return {
                "order_id": trade.order.orderId,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "status": trade.orderStatus.status if trade.orderStatus else "Submitted",
            }
        except Exception as exc:
            raise HedgeConnectionError(
                f"Failed to place hedge order: {exc}"
            ) from exc

    async def get_position(self, symbol: str) -> int:
        """Get current IB position for a symbol.

        Args:
            symbol: Futures symbol (e.g. "ZS").

        Returns:
            Signed position (positive=long, negative=short).

        Raises:
            HedgeConnectionError: If not connected.
        """
        if not self._connected or self._ib is None:
            raise HedgeConnectionError("Not connected to IB Gateway")

        positions = self._ib.positions()
        for pos in positions:
            if pos.contract.symbol == symbol:
                return int(pos.position)
        return 0

    async def get_market_data(self, symbol: str) -> float:
        """Get last price for a futures symbol.

        Args:
            symbol: Futures symbol (e.g. "ZS").

        Returns:
            Last traded price.

        Raises:
            HedgeConnectionError: If not connected or no data available.
        """
        if not self._connected or self._ib is None:
            raise HedgeConnectionError("Not connected to IB Gateway")

        from ib_insync import Future  # noqa: PLC0415

        contract = Future(symbol=symbol, exchange="CBOT")
        try:
            [contract] = await self._ib.qualifyContractsAsync(contract)
            ticker = self._ib.reqMktData(contract)
            await asyncio.sleep(0.5)
            if ticker.last is not None and ticker.last > 0:
                price = float(ticker.last)
            elif ticker.close is not None and ticker.close > 0:
                price = float(ticker.close)
            else:
                raise HedgeConnectionError(
                    f"No market data available for {symbol}"
                )
            self._ib.cancelMktData(contract)
            return price
        except HedgeConnectionError:
            raise
        except Exception as exc:
            raise HedgeConnectionError(
                f"Failed to get market data for {symbol}: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        if self._ib is not None:
            self._ib.disconnect()
            self._ib = None

        self._connected = False
        logger.info("IBKR: disconnected")

    # ── Reconnection ───────────────────────────────────────────────

    async def _reconnect(self) -> None:
        """Attempt reconnection with exponential backoff."""
        backoff = 1.0
        while not self._connected:
            logger.warning(
                "IBKR: reconnecting to %s:%d (backoff=%.1fs)",
                self._host, self._port, backoff,
            )
            try:
                from ib_insync import IB  # noqa: PLC0415
                ib = IB()
                await ib.connectAsync(
                    self._host, self._port, clientId=self._client_id
                )
                self._ib = ib
                self._connected = True
                self._last_heartbeat = time.monotonic()
                logger.info("IBKR: reconnected successfully")
                return
            except Exception as exc:
                logger.warning("IBKR: reconnect failed: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_RECONNECT_BACKOFF_S)

    # ── Heartbeat ──────────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Monitor connection health via periodic heartbeat."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval_s)

                if self._ib is None:
                    self._connected = False
                    raise HedgeConnectionError("IB instance is None")

                if not self._ib.isConnected():
                    elapsed = time.monotonic() - self._last_heartbeat
                    self._connected = False
                    if elapsed > self._disconnect_timeout_s:
                        raise HedgeConnectionError(
                            f"IB disconnected for {elapsed:.1f}s "
                            f"(timeout={self._disconnect_timeout_s}s)"
                        )
                    # Try reconnect
                    await self._reconnect()
                else:
                    self._last_heartbeat = time.monotonic()

            except HedgeConnectionError:
                raise
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("IBKR: heartbeat error: %s", exc)
