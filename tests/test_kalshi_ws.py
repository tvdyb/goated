"""Tests for the Kalshi WebSocket multiplex client (ACT-05).

Covers:
  - Auth header generation for WS handshake
  - Subscribe command format and response parsing
  - Message parsing for all event types (snapshot, delta, user_order, fill)
  - Sequence gap detection on orderbook_delta
  - Reconnection with backoff on disconnect
  - Fail-loud on auth errors
  - Fail-loud on unexpected message types
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.kalshi.auth import KalshiAuth, generate_test_key_pair
from feeds.kalshi.errors import KalshiAPIError, KalshiAuthError
from feeds.kalshi.ws import (
    FillAction,
    FillEvent,
    KalshiWebSocket,
    OrderbookDeltaEvent,
    OrderbookSnapshotEvent,
    OrderSide,
    OrderStatus,
    UserOrderEvent,
    _parse_fill,
    _parse_message,
    _parse_orderbook_delta,
    _parse_orderbook_snapshot,
    _parse_user_order,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def rsa_key_pair():
    """Generate a fresh RSA key pair for testing."""
    private_key, pem_bytes = generate_test_key_pair()
    return private_key, pem_bytes


@pytest.fixture()
def auth(rsa_key_pair):
    """KalshiAuth instance with test key."""
    _, pem_bytes = rsa_key_pair
    return KalshiAuth(api_key="test-api-key-uuid", private_key_pem=pem_bytes)


@pytest.fixture()
def ws_client(auth):
    """KalshiWebSocket instance with test auth."""
    return KalshiWebSocket(
        auth=auth,
        ws_url="wss://test.example.com/trade-api/ws/v2",
        idle_timeout_s=5.0,
        backoff_base_s=0.01,
        backoff_max_s=0.05,
        max_reconnect_attempts=3,
    )


# ── Sample messages ──────────────────────────────────────────────────

SUBSCRIBE_RESPONSE = json.dumps({
    "id": 1,
    "type": "subscribed",
    "msg": {"channel": "orderbook_delta", "sid": 42},
})

ORDERBOOK_SNAPSHOT_MSG = {
    "type": "orderbook_snapshot",
    "sid": 42,
    "seq": 1,
    "msg": {
        "market_ticker": "KXSOYBEANW-26APR24-17",
        "market_id": "9b0f6b43-5b68-4f9f-9f02-9a2d1b8ac1a1",
        "yes_dollars_fp": [["0.0800", "300.00"], ["0.2200", "333.00"]],
        "no_dollars_fp": [["0.5400", "20.00"]],
    },
}

ORDERBOOK_DELTA_MSG = {
    "type": "orderbook_delta",
    "sid": 42,
    "seq": 2,
    "msg": {
        "market_ticker": "KXSOYBEANW-26APR24-17",
        "market_id": "9b0f6b43-5b68-4f9f-9f02-9a2d1b8ac1a1",
        "price_dollars": "0.9600",
        "delta_fp": "-54.00",
        "side": "yes",
        "ts_ms": 1669149841000,
    },
}

USER_ORDER_MSG = {
    "type": "user_order",
    "sid": 55,
    "msg": {
        "order_id": "ee587a1c-8b87-4dcf-b721-9f6f790619fa",
        "ticker": "KXSOYBEANW-26APR24-17",
        "status": "resting",
        "side": "yes",
        "yes_price_dollars": "0.3500",
        "fill_count_fp": "10.00",
        "remaining_count_fp": "10.00",
        "initial_count_fp": "10.00",
        "client_order_id": "my-order-1",
        "created_ts_ms": 1733047200000,
    },
}

FILL_MSG = {
    "type": "fill",
    "sid": 66,
    "msg": {
        "trade_id": "aabb1122-ccdd-eeff-0011-223344556677",
        "order_id": "ee587a1c-8b87-4dcf-b721-9f6f790619fa",
        "market_ticker": "KXSOYBEANW-26APR24-17",
        "side": "yes",
        "yes_price_dollars": "0.3500",
        "count_fp": "5.00",
        "action": "buy",
        "ts_ms": 1733047201000,
        "post_position_fp": "15.00",
    },
}


# ── Test: _parse_message ─────────────────────────────────────────────


class TestParseMessage:
    def test_valid_json_dict(self):
        raw = json.dumps({"type": "test", "data": 123})
        result = _parse_message(raw)
        assert result == {"type": "test", "data": 123}

    def test_bytes_input(self):
        raw = json.dumps({"type": "test"}).encode("utf-8")
        result = _parse_message(raw)
        assert result["type"] == "test"

    def test_invalid_json_raises(self):
        with pytest.raises(KalshiAPIError, match="Malformed WS JSON"):
            _parse_message("not json {{{")

    def test_non_dict_json_raises(self):
        with pytest.raises(KalshiAPIError, match="Expected JSON object"):
            _parse_message(json.dumps([1, 2, 3]))


# ── Test: orderbook snapshot parsing ─────────────────────────────────


class TestParseOrderbookSnapshot:
    def test_parses_all_fields(self):
        event = _parse_orderbook_snapshot(ORDERBOOK_SNAPSHOT_MSG)
        assert isinstance(event, OrderbookSnapshotEvent)
        assert event.market_ticker == "KXSOYBEANW-26APR24-17"
        assert event.market_id == "9b0f6b43-5b68-4f9f-9f02-9a2d1b8ac1a1"
        assert len(event.yes_levels) == 2
        assert event.yes_levels[0].price_dollars == "0.0800"
        assert event.yes_levels[0].size_fp == "300.00"
        assert event.yes_levels[1].price_dollars == "0.2200"
        assert len(event.no_levels) == 1
        assert event.no_levels[0].price_dollars == "0.5400"
        assert event.sid == 42
        assert event.seq == 1

    def test_empty_levels(self):
        msg = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {
                "market_ticker": "TEST-01",
                "market_id": "abc-123",
            },
        }
        event = _parse_orderbook_snapshot(msg)
        assert event.yes_levels == []
        assert event.no_levels == []


# ── Test: orderbook delta parsing ────────────────────────────────────


class TestParseOrderbookDelta:
    def test_parses_all_fields(self):
        event = _parse_orderbook_delta(ORDERBOOK_DELTA_MSG)
        assert isinstance(event, OrderbookDeltaEvent)
        assert event.market_ticker == "KXSOYBEANW-26APR24-17"
        assert event.price_dollars == "0.9600"
        assert event.delta_fp == "-54.00"
        assert event.side == OrderSide.YES
        assert event.ts_ms == 1669149841000
        assert event.sid == 42
        assert event.seq == 2

    def test_no_side(self):
        msg = dict(ORDERBOOK_DELTA_MSG)
        msg["msg"] = dict(msg["msg"], side="no")
        event = _parse_orderbook_delta(msg)
        assert event.side == OrderSide.NO


# ── Test: user_order parsing ─────────────────────────────────────────


class TestParseUserOrder:
    def test_parses_all_fields(self):
        event = _parse_user_order(USER_ORDER_MSG)
        assert isinstance(event, UserOrderEvent)
        assert event.order_id == "ee587a1c-8b87-4dcf-b721-9f6f790619fa"
        assert event.ticker == "KXSOYBEANW-26APR24-17"
        assert event.status == OrderStatus.RESTING
        assert event.side == OrderSide.YES
        assert event.yes_price_dollars == "0.3500"
        assert event.fill_count_fp == "10.00"
        assert event.remaining_count_fp == "10.00"
        assert event.initial_count_fp == "10.00"
        assert event.client_order_id == "my-order-1"
        assert event.created_ts_ms == 1733047200000
        assert event.sid == 55

    def test_canceled_status(self):
        msg = dict(USER_ORDER_MSG)
        msg["msg"] = dict(msg["msg"], status="canceled")
        event = _parse_user_order(msg)
        assert event.status == OrderStatus.CANCELED

    def test_executed_status(self):
        msg = dict(USER_ORDER_MSG)
        msg["msg"] = dict(msg["msg"], status="executed")
        event = _parse_user_order(msg)
        assert event.status == OrderStatus.EXECUTED


# ── Test: fill parsing ───────────────────────────────────────────────


class TestParseFill:
    def test_parses_all_fields(self):
        event = _parse_fill(FILL_MSG)
        assert isinstance(event, FillEvent)
        assert event.trade_id == "aabb1122-ccdd-eeff-0011-223344556677"
        assert event.order_id == "ee587a1c-8b87-4dcf-b721-9f6f790619fa"
        assert event.market_ticker == "KXSOYBEANW-26APR24-17"
        assert event.side == OrderSide.YES
        assert event.yes_price_dollars == "0.3500"
        assert event.count_fp == "5.00"
        assert event.action == FillAction.BUY
        assert event.ts_ms == 1733047201000
        assert event.post_position_fp == "15.00"
        assert event.sid == 66

    def test_sell_action(self):
        msg = dict(FILL_MSG)
        msg["msg"] = dict(msg["msg"], action="sell")
        event = _parse_fill(msg)
        assert event.action == FillAction.SELL

    def test_optional_fields_absent(self):
        msg = dict(FILL_MSG)
        body = dict(msg["msg"])
        del body["ts_ms"]
        del body["post_position_fp"]
        msg["msg"] = body
        event = _parse_fill(msg)
        assert event.ts_ms is None
        assert event.post_position_fp is None


# ── Test: auth header generation ─────────────────────────────────────


class TestAuthHeaders:
    def test_build_auth_headers(self, ws_client):
        headers = ws_client._build_auth_headers()
        assert "KALSHI-ACCESS-KEY" in headers
        assert headers["KALSHI-ACCESS-KEY"] == "test-api-key-uuid"
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers

    def test_auth_headers_sign_ws_path(self, auth):
        """Verify the auth signs with the WS path, not a REST path."""
        headers = auth.build_headers("GET", "/trade-api/ws/v2")
        assert headers["KALSHI-ACCESS-KEY"] == "test-api-key-uuid"
        # Signature should be non-empty
        assert len(headers["KALSHI-ACCESS-SIGNATURE"]) > 0


# ── Test: subscribe command format ───────────────────────────────────


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_sends_correct_command(self, ws_client):
        """Test that subscribe sends the right JSON command and parses response."""
        mock_ws = AsyncMock()
        sent_msgs: list[str] = []

        async def mock_send(msg: str) -> None:
            sent_msgs.append(msg)

        async def mock_recv() -> str:
            # Return subscription confirmation
            cmd = json.loads(sent_msgs[-1])
            return json.dumps({
                "id": cmd["id"],
                "type": "subscribed",
                "msg": {"channel": cmd["params"]["channels"][0], "sid": 100},
            })

        mock_ws.send = mock_send
        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        sids = await ws_client.subscribe(
            channels=["orderbook_delta"],
            market_ticker="KXSOYBEANW-26APR24-17",
        )

        assert sids == [100]
        cmd = json.loads(sent_msgs[0])
        assert cmd["cmd"] == "subscribe"
        assert cmd["params"]["channels"] == ["orderbook_delta"]
        assert cmd["params"]["market_ticker"] == "KXSOYBEANW-26APR24-17"

    @pytest.mark.asyncio
    async def test_subscribe_multiple_tickers(self, ws_client):
        """Test subscription with multiple market tickers."""
        mock_ws = AsyncMock()
        sent_msgs: list[str] = []

        async def mock_send(msg: str) -> None:
            sent_msgs.append(msg)

        async def mock_recv() -> str:
            cmd = json.loads(sent_msgs[-1])
            return json.dumps({
                "id": cmd["id"],
                "type": "subscribed",
                "msg": {"channel": cmd["params"]["channels"][0], "sid": 200},
            })

        mock_ws.send = mock_send
        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        sids = await ws_client.subscribe(
            channels=["fill"],
            market_tickers=["TICKER-A", "TICKER-B"],
        )

        cmd = json.loads(sent_msgs[0])
        assert cmd["params"]["market_tickers"] == ["TICKER-A", "TICKER-B"]
        assert "market_ticker" not in cmd["params"]

    @pytest.mark.asyncio
    async def test_subscribe_multiple_channels(self, ws_client):
        """Test subscribing to multiple channels in one call."""
        mock_ws = AsyncMock()
        sent_msgs: list[str] = []
        sid_counter = [0]

        async def mock_send(msg: str) -> None:
            sent_msgs.append(msg)

        async def mock_recv() -> str:
            sid_counter[0] += 1
            cmd = json.loads(sent_msgs[-1])
            return json.dumps({
                "id": cmd["id"],
                "type": "subscribed",
                "msg": {"channel": cmd["params"]["channels"][0], "sid": sid_counter[0]},
            })

        mock_ws.send = mock_send
        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        sids = await ws_client.subscribe(
            channels=["orderbook_delta", "fill", "user_orders"],
            market_ticker="TEST-01",
        )

        assert len(sids) == 3
        assert sids == [1, 2, 3]
        # Each channel gets its own subscribe command
        assert len(sent_msgs) == 3

    @pytest.mark.asyncio
    async def test_subscribe_auth_error_raises(self, ws_client):
        """Test that auth error during subscribe raises KalshiAuthError."""
        mock_ws = AsyncMock()
        sent_msgs: list[str] = []

        async def mock_send(msg: str) -> None:
            sent_msgs.append(msg)

        async def mock_recv() -> str:
            cmd = json.loads(sent_msgs[-1])
            return json.dumps({
                "id": cmd["id"],
                "type": "error",
                "msg": {"code": 9, "msg": "Unauthenticated connection"},
            })

        mock_ws.send = mock_send
        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        with pytest.raises(KalshiAuthError, match="auth error"):
            await ws_client.subscribe(
                channels=["orderbook_delta"],
                market_ticker="TEST-01",
            )

    @pytest.mark.asyncio
    async def test_subscribe_not_connected_raises(self, ws_client):
        """Test that subscribing without connection raises."""
        with pytest.raises(KalshiAPIError, match="Not connected"):
            await ws_client.subscribe(channels=["fill"])


# ── Test: dispatch and handlers ──────────────────────────────────────


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_orderbook_snapshot(self, ws_client):
        """Test that snapshot events are dispatched to registered handlers."""
        received: list[OrderbookSnapshotEvent] = []

        async def handler(event: OrderbookSnapshotEvent) -> None:
            received.append(event)

        ws_client.on_orderbook_snapshot(handler)
        # Set up sid mapping
        from feeds.kalshi.ws import _SubscriptionState
        sub = _SubscriptionState(channel="orderbook_delta", market_tickers=[], sid=42)
        ws_client._sid_map[42] = sub

        await ws_client._dispatch(ORDERBOOK_SNAPSHOT_MSG)

        assert len(received) == 1
        assert received[0].market_ticker == "KXSOYBEANW-26APR24-17"
        assert len(received[0].yes_levels) == 2

    @pytest.mark.asyncio
    async def test_dispatch_orderbook_delta(self, ws_client):
        """Test that delta events are dispatched."""
        received: list[OrderbookDeltaEvent] = []

        async def handler(event: OrderbookDeltaEvent) -> None:
            received.append(event)

        ws_client.on_orderbook_delta(handler)
        from feeds.kalshi.ws import _SubscriptionState
        sub = _SubscriptionState(channel="orderbook_delta", market_tickers=[], sid=42, last_seq=1)
        ws_client._sid_map[42] = sub

        await ws_client._dispatch(ORDERBOOK_DELTA_MSG)

        assert len(received) == 1
        assert received[0].delta_fp == "-54.00"
        assert received[0].side == OrderSide.YES

    @pytest.mark.asyncio
    async def test_dispatch_user_order(self, ws_client):
        """Test that user order events are dispatched."""
        received: list[UserOrderEvent] = []

        async def handler(event: UserOrderEvent) -> None:
            received.append(event)

        ws_client.on_user_order(handler)
        await ws_client._dispatch(USER_ORDER_MSG)

        assert len(received) == 1
        assert received[0].status == OrderStatus.RESTING

    @pytest.mark.asyncio
    async def test_dispatch_fill(self, ws_client):
        """Test that fill events are dispatched."""
        received: list[FillEvent] = []

        async def handler(event: FillEvent) -> None:
            received.append(event)

        ws_client.on_fill(handler)
        await ws_client._dispatch(FILL_MSG)

        assert len(received) == 1
        assert received[0].action == FillAction.BUY

    @pytest.mark.asyncio
    async def test_dispatch_unexpected_type_raises(self, ws_client):
        """Test fail-loud on unknown message types."""
        with pytest.raises(KalshiAPIError, match="Unexpected WS message type"):
            await ws_client._dispatch({"type": "alien_invasion"})

    @pytest.mark.asyncio
    async def test_dispatch_error_type_raises(self, ws_client):
        """Test that error messages raise."""
        with pytest.raises(KalshiAPIError, match="WS error"):
            await ws_client._dispatch({
                "type": "error",
                "msg": {"code": 17, "msg": "Server error"},
            })

    @pytest.mark.asyncio
    async def test_dispatch_auth_error_raises_specific(self, ws_client):
        """Test that auth error messages raise KalshiAuthError specifically."""
        with pytest.raises(KalshiAuthError, match="WS auth error"):
            await ws_client._dispatch({
                "type": "error",
                "msg": {"code": 9, "msg": "Unauthenticated"},
            })

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, ws_client):
        """Test that multiple handlers for the same event all fire."""
        count = [0, 0]

        async def handler_a(event: FillEvent) -> None:
            count[0] += 1

        async def handler_b(event: FillEvent) -> None:
            count[1] += 1

        ws_client.on_fill(handler_a)
        ws_client.on_fill(handler_b)
        await ws_client._dispatch(FILL_MSG)

        assert count == [1, 1]


# ── Test: sequence gap detection ─────────────────────────────────────


class TestSequenceGap:
    def test_no_gap(self, ws_client):
        """No warning when sequence is contiguous."""
        from feeds.kalshi.ws import _SubscriptionState
        sub = _SubscriptionState(channel="orderbook_delta", market_tickers=[], sid=1, last_seq=4)
        ws_client._sid_map[1] = sub

        ws_client._check_seq(1, 5)
        assert sub.last_seq == 5

    def test_gap_detected(self, ws_client, caplog):
        """Warning logged on sequence gap."""
        from feeds.kalshi.ws import _SubscriptionState
        sub = _SubscriptionState(channel="orderbook_delta", market_tickers=[], sid=1, last_seq=4)
        ws_client._sid_map[1] = sub

        import logging
        with caplog.at_level(logging.WARNING):
            ws_client._check_seq(1, 7)

        assert "Sequence gap" in caplog.text
        assert sub.last_seq == 7

    def test_first_message_no_warning(self, ws_client, caplog):
        """First message (last_seq=0) should not trigger gap warning."""
        from feeds.kalshi.ws import _SubscriptionState
        sub = _SubscriptionState(channel="orderbook_delta", market_tickers=[], sid=1, last_seq=0)
        ws_client._sid_map[1] = sub

        import logging
        with caplog.at_level(logging.WARNING):
            ws_client._check_seq(1, 1)

        assert "Sequence gap" not in caplog.text
        assert sub.last_seq == 1


# ── Test: run loop and reconnection ──────────────────────────────────


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_run_dispatches_messages(self, ws_client):
        """Test that run() receives and dispatches messages."""
        messages = [
            json.dumps(FILL_MSG),
        ]
        msg_iter = iter(messages)
        received: list[FillEvent] = []

        async def handler(event: FillEvent) -> None:
            received.append(event)
            ws_client._running = False  # Stop after first message

        ws_client.on_fill(handler)

        mock_ws = AsyncMock()

        async def mock_recv() -> str:
            try:
                return next(msg_iter)
            except StopIteration:
                # Simulate connection close
                import websockets.exceptions
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        await ws_client.run()

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_run_returns_on_idle_timeout(self, ws_client):
        """Test that run() returns when idle timeout is exceeded."""
        mock_ws = AsyncMock()

        async def mock_recv() -> str:
            # Never returns -- simulates idle
            await asyncio.sleep(100)
            return ""

        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws
        ws_client._idle_timeout_s = 0.05

        # Should return without hanging
        await asyncio.wait_for(ws_client.run(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_run_returns_on_connection_close(self, ws_client):
        """Test that run() returns on connection close."""
        import websockets.exceptions

        mock_ws = AsyncMock()

        async def mock_recv() -> str:
            raise websockets.exceptions.ConnectionClosed(None, None)

        mock_ws.recv = mock_recv
        mock_ws.open = True
        ws_client._ws = mock_ws

        await ws_client.run()
        # Should return cleanly

    @pytest.mark.asyncio
    async def test_run_forever_reconnects(self, ws_client):
        """Test that run_forever reconnects after disconnect."""
        connect_count = [0]
        run_count = [0]
        # Track whether we're "connected" -- reset after each run
        connected = [False]

        async def mock_connect() -> None:
            connect_count[0] += 1
            connected[0] = True
            if connect_count[0] >= 3:
                ws_client._closed = True

        async def mock_run() -> None:
            run_count[0] += 1
            # Simulate disconnect: connection lost after run
            connected[0] = False
            ws_client._ws = None

        async def mock_resubscribe() -> None:
            pass

        ws_client.connect = mock_connect
        ws_client.run = mock_run
        ws_client._resubscribe_all = mock_resubscribe
        ws_client._max_reconnect_attempts = None  # Unlimited for this test

        # Patch is_connected to track our mock state
        original_is_connected = type(ws_client).is_connected
        type(ws_client).is_connected = property(lambda self: connected[0])

        try:
            await ws_client.run_forever()
        finally:
            type(ws_client).is_connected = original_is_connected

        # Should have connected multiple times (reconnection happened)
        assert connect_count[0] == 3
        assert run_count[0] >= 2

    @pytest.mark.asyncio
    async def test_run_forever_auth_error_not_retried(self, ws_client):
        """Test that auth errors in run_forever are fatal (fail-loud)."""
        async def mock_connect() -> None:
            raise KalshiAuthError("Bad auth")

        ws_client.connect = mock_connect

        with pytest.raises(KalshiAuthError, match="Bad auth"):
            await ws_client.run_forever()

    @pytest.mark.asyncio
    async def test_run_forever_max_attempts_exceeded(self, ws_client):
        """Test that exceeding max reconnect attempts raises."""
        ws_client._max_reconnect_attempts = 2

        async def mock_connect() -> None:
            raise KalshiAPIError("Connection refused")

        ws_client.connect = mock_connect

        with pytest.raises(KalshiAPIError, match="Max reconnect attempts"):
            await ws_client.run_forever()


# ── Test: close and state management ─────────────────────────────────


class TestCloseState:
    @pytest.mark.asyncio
    async def test_close_sets_closed_flag(self, ws_client):
        assert not ws_client._closed
        await ws_client.close()
        assert ws_client._closed

    @pytest.mark.asyncio
    async def test_connect_after_close_raises(self, ws_client):
        await ws_client.close()
        with pytest.raises(KalshiAPIError, match="has been closed"):
            await ws_client.connect()

    def test_is_connected_false_initially(self, ws_client):
        assert not ws_client.is_connected
