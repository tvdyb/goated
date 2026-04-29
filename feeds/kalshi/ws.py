"""Kalshi multiplexed WebSocket client.

Subscribes to orderbook_delta, user_orders, and fill channels on a single
authenticated connection. Dispatches typed events to registered async handlers.

Non-negotiables enforced:
  - asyncio for I/O (this IS I/O code)
  - No silent failures: auth errors, unexpected message types -> raise
  - No pandas
  - Type hints on all public interfaces

Protocol reference:
  - Kalshi AsyncAPI spec: https://docs.kalshi.com/asyncapi.yaml
  - Phase 07 section 8; Phase 09 section 1.2

Channels:
  - orderbook_delta: initial orderbook_snapshot then incremental orderbook_delta
  - user_orders: order lifecycle (resting/canceled/executed)
  - fill: fill notifications
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

import websockets
import websockets.exceptions

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.errors import KalshiAPIError, KalshiAuthError

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

_PROD_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
_DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"

_BACKOFF_BASE_S = 1.0
_BACKOFF_MAX_S = 30.0
_IDLE_TIMEOUT_S = 30.0  # Force reconnect if no message in this window

# Kalshi WS error codes that should NOT be retried
_AUTH_ERROR_CODE = 9


# ── Event types ───────────────────────────────────────────────────────


class OrderSide(str, Enum):
    YES = "yes"
    NO = "no"


class OrderStatus(str, Enum):
    RESTING = "resting"
    CANCELED = "canceled"
    EXECUTED = "executed"


class FillAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class OrderbookLevel:
    """A single price level: (price_dollars, size as float)."""
    price_dollars: str
    size_fp: str


@dataclass(frozen=True, slots=True)
class OrderbookSnapshotEvent:
    """Initial full orderbook state after subscribing to orderbook_delta."""
    market_ticker: str
    market_id: str
    yes_levels: list[OrderbookLevel]
    no_levels: list[OrderbookLevel]
    sid: int
    seq: int


@dataclass(frozen=True, slots=True)
class OrderbookDeltaEvent:
    """Incremental orderbook update."""
    market_ticker: str
    market_id: str
    price_dollars: str
    delta_fp: str
    side: OrderSide
    ts_ms: int | None
    sid: int
    seq: int


@dataclass(frozen=True, slots=True)
class UserOrderEvent:
    """Order lifecycle event from user_orders channel."""
    order_id: str
    ticker: str
    status: OrderStatus
    side: OrderSide
    yes_price_dollars: str
    fill_count_fp: str
    remaining_count_fp: str
    initial_count_fp: str
    client_order_id: str | None
    created_ts_ms: int | None
    sid: int


@dataclass(frozen=True, slots=True)
class FillEvent:
    """Fill notification from fill channel."""
    trade_id: str
    order_id: str
    market_ticker: str
    side: OrderSide
    yes_price_dollars: str
    count_fp: str
    action: FillAction
    ts_ms: int | None
    post_position_fp: str | None
    sid: int


# ── Handler type aliases ──────────────────────────────────────────────

OrderbookSnapshotHandler = Callable[[OrderbookSnapshotEvent], Awaitable[None]]
OrderbookDeltaHandler = Callable[[OrderbookDeltaEvent], Awaitable[None]]
UserOrderHandler = Callable[[UserOrderEvent], Awaitable[None]]
FillHandler = Callable[[FillEvent], Awaitable[None]]


# ── Subscription tracking ─────────────────────────────────────────────


@dataclass
class _SubscriptionState:
    """Tracks a single channel subscription."""
    channel: str
    market_tickers: list[str]
    sid: int | None = None
    last_seq: int = 0


# ── WebSocket client ──────────────────────────────────────────────────


class KalshiWebSocket:
    """Multiplexed Kalshi WebSocket client with typed event dispatch.

    Usage::

        auth = KalshiAuth(api_key="...", private_key_pem=b"...")
        ws = KalshiWebSocket(auth=auth)
        ws.on_orderbook_snapshot(my_snapshot_handler)
        ws.on_orderbook_delta(my_delta_handler)
        ws.on_fill(my_fill_handler)
        ws.on_user_order(my_order_handler)

        await ws.connect()
        await ws.subscribe(
            channels=["orderbook_delta", "fill", "user_orders"],
            market_tickers=["KXSOYBEANW-26APR24-17"],
        )
        # ws.run() starts the message loop; or use run_forever() for auto-reconnect
        await ws.run_forever()
    """

    def __init__(
        self,
        *,
        auth: KalshiAuth,
        ws_url: str = _PROD_WS_URL,
        idle_timeout_s: float = _IDLE_TIMEOUT_S,
        backoff_base_s: float = _BACKOFF_BASE_S,
        backoff_max_s: float = _BACKOFF_MAX_S,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        self._auth = auth
        self._ws_url = ws_url
        self._idle_timeout_s = idle_timeout_s
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._max_reconnect_attempts = max_reconnect_attempts

        self._ws: Any = None
        self._cmd_id = 0
        self._running = False
        self._closed = False

        # Subscription state for resubscription on reconnect
        self._subscriptions: list[_SubscriptionState] = []
        # Map sid -> subscription for dispatch
        self._sid_map: dict[int, _SubscriptionState] = {}

        # Handlers
        self._on_orderbook_snapshot: list[OrderbookSnapshotHandler] = []
        self._on_orderbook_delta: list[OrderbookDeltaHandler] = []
        self._on_user_order: list[UserOrderHandler] = []
        self._on_fill: list[FillHandler] = []

    # ── Handler registration ──────────────────────────────────────

    def on_orderbook_snapshot(self, handler: OrderbookSnapshotHandler) -> None:
        """Register a handler for orderbook snapshot events."""
        self._on_orderbook_snapshot.append(handler)

    def on_orderbook_delta(self, handler: OrderbookDeltaHandler) -> None:
        """Register a handler for orderbook delta events."""
        self._on_orderbook_delta.append(handler)

    def on_user_order(self, handler: UserOrderHandler) -> None:
        """Register a handler for user order events."""
        self._on_user_order.append(handler)

    def on_fill(self, handler: FillHandler) -> None:
        """Register a handler for fill events."""
        self._on_fill.append(handler)

    # ── Connection ────────────────────────────────────────────────

    def _next_cmd_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    def _build_auth_headers(self) -> dict[str, str]:
        """Build auth headers for the WS handshake.

        Uses the same RSA-PSS signing as REST, with method GET and
        the WS path.
        """
        return self._auth.build_headers("GET", "/trade-api/ws/v2")

    async def connect(self) -> None:
        """Establish the WebSocket connection with authentication."""
        if self._closed:
            raise KalshiAPIError("WebSocket client has been closed")

        headers = self._build_auth_headers()
        try:
            self._ws = await websockets.connect(
                self._ws_url,
                additional_headers=headers,
                ping_interval=10,
                ping_timeout=20,
            )
        except Exception as exc:
            raise KalshiAPIError(f"WebSocket connection failed: {exc}") from exc

        logger.info("Kalshi WS connected to %s", self._ws_url)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._closed = True
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("Kalshi WS closed")

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.open

    # ── Subscribe / Unsubscribe ───────────────────────────────────

    async def subscribe(
        self,
        *,
        channels: list[str],
        market_tickers: list[str] | None = None,
        market_ticker: str | None = None,
    ) -> list[int]:
        """Subscribe to channels, optionally scoped to market ticker(s).

        Args:
            channels: List of channel names (orderbook_delta, user_orders, fill).
            market_tickers: List of market tickers to subscribe to.
            market_ticker: Single market ticker (convenience).

        Returns:
            List of assigned subscription IDs (sids).
        """
        if self._ws is None:
            raise KalshiAPIError("Not connected. Call connect() first.")

        tickers: list[str] = []
        if market_tickers:
            tickers = list(market_tickers)
        elif market_ticker:
            tickers = [market_ticker]

        sids: list[int] = []
        for channel in channels:
            cmd_id = self._next_cmd_id()
            cmd: dict[str, Any] = {
                "id": cmd_id,
                "cmd": "subscribe",
                "params": {
                    "channels": [channel],
                },
            }
            if len(tickers) == 1:
                cmd["params"]["market_ticker"] = tickers[0]
            elif len(tickers) > 1:
                cmd["params"]["market_tickers"] = tickers

            await self._ws.send(json.dumps(cmd))
            logger.debug("Sent subscribe cmd %d for channel=%s", cmd_id, channel)

            # Wait for subscription confirmation
            sid = await self._wait_for_subscribe_response(cmd_id, channel)

            sub = _SubscriptionState(
                channel=channel,
                market_tickers=tickers,
                sid=sid,
            )
            self._subscriptions.append(sub)
            self._sid_map[sid] = sub
            sids.append(sid)

            logger.info(
                "Subscribed to channel=%s sid=%d tickers=%s",
                channel, sid, tickers,
            )

        return sids

    async def _wait_for_subscribe_response(
        self, cmd_id: int, channel: str, timeout_s: float = 10.0
    ) -> int:
        """Wait for a subscription confirmation and return the assigned sid.

        Raises on error responses or timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            msg = _parse_message(raw)
            msg_type = msg.get("type", "")

            # Check for error on our command
            if msg_type == "error" and msg.get("id") == cmd_id:
                error_msg = msg.get("msg", {})
                code = error_msg.get("code", -1)
                text = error_msg.get("msg", "unknown error")
                if code == _AUTH_ERROR_CODE:
                    raise KalshiAuthError(
                        f"WS auth error subscribing to {channel}: {text}",
                    )
                raise KalshiAPIError(
                    f"WS subscribe error for {channel}: code={code} msg={text}",
                )

            # Subscription confirmed
            if msg_type == "subscribed" and msg.get("id") == cmd_id:
                return msg["msg"]["sid"]

            # Could be a data message from another subscription; queue it
            # For simplicity during subscribe, dispatch it
            await self._dispatch(msg)

        raise KalshiAPIError(
            f"Timed out waiting for subscribe confirmation on {channel}"
        )

    async def unsubscribe(self, sids: list[int]) -> None:
        """Unsubscribe from the given subscription IDs."""
        if self._ws is None:
            raise KalshiAPIError("Not connected.")

        cmd_id = self._next_cmd_id()
        cmd = {
            "id": cmd_id,
            "cmd": "unsubscribe",
            "params": {"sids": sids},
        }
        await self._ws.send(json.dumps(cmd))

        for sid in sids:
            self._sid_map.pop(sid, None)
            self._subscriptions = [
                s for s in self._subscriptions if s.sid != sid
            ]

        logger.info("Unsubscribed sids=%s", sids)

    async def _resubscribe_all(self) -> None:
        """Resubscribe all tracked channels after reconnect."""
        old_subs = list(self._subscriptions)
        self._subscriptions.clear()
        self._sid_map.clear()

        for sub in old_subs:
            await self.subscribe(
                channels=[sub.channel],
                market_tickers=sub.market_tickers if sub.market_tickers else None,
            )

    # ── Message loop ──────────────────────────────────────────────

    async def run(self) -> None:
        """Run the message receive loop until disconnection or close().

        Raises on unexpected errors. Returns on clean close or connection loss.
        """
        if self._ws is None:
            raise KalshiAPIError("Not connected. Call connect() first.")

        self._running = True
        try:
            while self._running:
                try:
                    raw = await asyncio.wait_for(
                        self._ws.recv(), timeout=self._idle_timeout_s
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "No WS message for %.0fs, treating as stale connection",
                        self._idle_timeout_s,
                    )
                    return
                except websockets.exceptions.ConnectionClosed as exc:
                    logger.warning("WS connection closed: %s", exc)
                    return

                msg = _parse_message(raw)
                await self._dispatch(msg)
        finally:
            self._running = False

    async def run_forever(self) -> None:
        """Run with automatic reconnection and backoff.

        Loops indefinitely, reconnecting on disconnect with exponential
        backoff. Stops only when close() is called or max_reconnect_attempts
        is exceeded.
        """
        attempt = 0
        while not self._closed:
            try:
                if not self.is_connected:
                    await self.connect()
                    await self._resubscribe_all()
                    attempt = 0  # Reset on successful connect

                await self.run()

                if self._closed:
                    return

            except KalshiAuthError:
                # Auth errors are fatal -- fail loud
                logger.error("WS auth failure; not retrying")
                raise
            except Exception as exc:
                if self._closed:
                    return
                logger.warning("WS error: %s", exc)

            # Reconnect with backoff
            attempt += 1
            if (
                self._max_reconnect_attempts is not None
                and attempt > self._max_reconnect_attempts
            ):
                raise KalshiAPIError(
                    f"Max reconnect attempts ({self._max_reconnect_attempts}) exceeded"
                )

            wait = min(
                self._backoff_base_s * (2 ** (attempt - 1)),
                self._backoff_max_s,
            )
            logger.info("Reconnecting in %.1fs (attempt %d)", wait, attempt)
            await asyncio.sleep(wait)

            # Reset connection state
            self._ws = None
            self._cmd_id = 0

    # ── Dispatch ──────────────────────────────────────────────────

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        """Route a parsed message to the appropriate handler(s)."""
        msg_type = msg.get("type", "")

        if msg_type == "orderbook_snapshot":
            event = _parse_orderbook_snapshot(msg)
            self._check_seq(event.sid, event.seq)
            for handler in self._on_orderbook_snapshot:
                await handler(event)

        elif msg_type == "orderbook_delta":
            event = _parse_orderbook_delta(msg)
            self._check_seq(event.sid, event.seq)
            for handler in self._on_orderbook_delta:
                await handler(event)

        elif msg_type == "user_order":
            event = _parse_user_order(msg)
            for handler in self._on_user_order:
                await handler(event)

        elif msg_type == "fill":
            event = _parse_fill(msg)
            for handler in self._on_fill:
                await handler(event)

        elif msg_type in ("subscribed", "unsubscribed", "ok"):
            # Control messages -- already handled in subscribe flow
            logger.debug("Control message: %s", msg_type)

        elif msg_type == "error":
            error_msg = msg.get("msg", {})
            code = error_msg.get("code", -1)
            text = error_msg.get("msg", "unknown")
            if code == _AUTH_ERROR_CODE:
                raise KalshiAuthError(f"WS auth error: {text}")
            raise KalshiAPIError(f"WS error: code={code} msg={text}")

        else:
            raise KalshiAPIError(f"Unexpected WS message type: {msg_type!r}")

    def _check_seq(self, sid: int, seq: int) -> None:
        """Check sequence continuity for orderbook channels.

        Logs a warning on gap; downstream must handle by requesting snapshot.
        """
        sub = self._sid_map.get(sid)
        if sub is None:
            return

        expected = sub.last_seq + 1
        if seq != expected and sub.last_seq != 0:
            logger.warning(
                "Sequence gap on sid=%d: expected=%d got=%d (channel=%s)",
                sid, expected, seq, sub.channel,
            )
        sub.last_seq = seq


# ── Message parsing ───────────────────────────────────────────────────


def _parse_message(raw: str | bytes) -> dict[str, Any]:
    """Parse a raw WebSocket message into a dict. Fail loud on bad JSON."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KalshiAPIError(f"Malformed WS JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise KalshiAPIError(f"Expected JSON object, got {type(data).__name__}")
    return data


def _parse_orderbook_snapshot(msg: dict[str, Any]) -> OrderbookSnapshotEvent:
    """Parse an orderbook_snapshot message into a typed event."""
    body = msg["msg"]
    yes_levels = [
        OrderbookLevel(price_dollars=lv[0], size_fp=lv[1])
        for lv in body.get("yes_dollars_fp", [])
    ]
    no_levels = [
        OrderbookLevel(price_dollars=lv[0], size_fp=lv[1])
        for lv in body.get("no_dollars_fp", [])
    ]
    return OrderbookSnapshotEvent(
        market_ticker=body["market_ticker"],
        market_id=body["market_id"],
        yes_levels=yes_levels,
        no_levels=no_levels,
        sid=msg["sid"],
        seq=msg["seq"],
    )


def _parse_orderbook_delta(msg: dict[str, Any]) -> OrderbookDeltaEvent:
    """Parse an orderbook_delta message into a typed event."""
    body = msg["msg"]
    return OrderbookDeltaEvent(
        market_ticker=body["market_ticker"],
        market_id=body["market_id"],
        price_dollars=body["price_dollars"],
        delta_fp=body["delta_fp"],
        side=OrderSide(body["side"]),
        ts_ms=body.get("ts_ms"),
        sid=msg["sid"],
        seq=msg["seq"],
    )


def _parse_user_order(msg: dict[str, Any]) -> UserOrderEvent:
    """Parse a user_order message into a typed event."""
    body = msg["msg"]
    return UserOrderEvent(
        order_id=body["order_id"],
        ticker=body["ticker"],
        status=OrderStatus(body["status"]),
        side=OrderSide(body["side"]),
        yes_price_dollars=body["yes_price_dollars"],
        fill_count_fp=body["fill_count_fp"],
        remaining_count_fp=body["remaining_count_fp"],
        initial_count_fp=body.get("initial_count_fp", "0.00"),
        client_order_id=body.get("client_order_id"),
        created_ts_ms=body.get("created_ts_ms"),
        sid=msg["sid"],
    )


def _parse_fill(msg: dict[str, Any]) -> FillEvent:
    """Parse a fill message into a typed event."""
    body = msg["msg"]
    return FillEvent(
        trade_id=body["trade_id"],
        order_id=body["order_id"],
        market_ticker=body["market_ticker"],
        side=OrderSide(body["side"]),
        yes_price_dollars=body["yes_price_dollars"],
        count_fp=body["count_fp"],
        action=FillAction(body["action"]),
        ts_ms=body.get("ts_ms"),
        post_position_fp=body.get("post_position_fp"),
        sid=msg["sid"],
    )
