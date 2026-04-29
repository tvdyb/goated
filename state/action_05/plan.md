# ACT-05 Plan -- Kalshi WebSocket Multiplex

**Action.** ACT-05
**Wave.** 0
**Effort.** M
**Gap.** GAP-131 (Kalshi WS multiplex consumer absent)
**Deps.** ACT-03 (complete-pending-verify) -- uses KalshiAuth signing for WS handshake

---

## Goal

Implement a multiplexed Kalshi WebSocket client that subscribes to
`orderbook_delta`, `user_orders`, and `fill` channels on a single
authenticated connection. This feeds:
- orderbook_delta: competitor estimation in ACT-LIP-COMPETITOR / ACT-LIP-SCORE
- user_orders: real-time order status for position store (ACT-09)
- fill: fill ingestion for markout and P&L (GAP-134)

---

## Design

### Module: `feeds/kalshi/ws.py`

**Connection:**
- Endpoint: `wss://api.elections.kalshi.com/trade-api/ws/v2`
  (demo: `wss://demo-api.kalshi.co/trade-api/ws/v2`)
- Auth: same RSA-PSS headers from ACT-03's KalshiAuth passed as
  extra headers during the websockets handshake

**Subscription protocol (per Kalshi AsyncAPI spec):**
- Send `{"id": N, "cmd": "subscribe", "params": {"channels": [...], "market_ticker": "..."}}` or `market_tickers` for batch
- Receive `{"id": N, "type": "subscribed", "msg": {"channel": "...", "sid": N}}`
- orderbook_delta: initial `orderbook_snapshot` then incremental `orderbook_delta` with `seq` for gap detection
- user_orders: `user_order` messages with status (resting/canceled/executed)
- fill: `fill` messages with trade_id, order_id, side, price, count, action

**Channels and typed events:**
- `OrderbookSnapshotEvent` -- initial full book
- `OrderbookDeltaEvent` -- incremental update with seq
- `UserOrderEvent` -- order lifecycle
- `FillEvent` -- fill notification

**Dispatch:**
- Callback-based: register async handlers per event type
- Handlers are typed: `Callable[[EventType], Awaitable[None]]`

**Reconnection:**
- Exponential backoff: 1s, 2s, 4s, 8s, capped at 30s
- Auto-resubscribe all channels on reconnect
- Fail-loud on auth errors (no retry on error code 9)

**Multiplexing:**
- Single connection for all channels
- subscribe/unsubscribe by market_ticker dynamically via update_subscription
- Sequence tracking per sid for orderbook_delta gap detection

**Heartbeat:**
- Kalshi sends ping frames every ~10s; websockets library auto-responds with pong
- If no message received for 30s, force reconnect

---

## Non-negotiables compliance

- asyncio for I/O: yes, this IS I/O code
- No pandas: no
- Fail-loud: auth failures raise immediately; unexpected message types raise
- Type hints: all public interfaces typed
- No hot-path concern: WS is I/O, not pricing math

---

## Test plan

- Connection + auth header generation
- Subscribe command format and response parsing
- Message parsing for all four event types (snapshot, delta, user_order, fill)
- Sequence gap detection on orderbook_delta
- Reconnection with backoff on disconnect
- Fail-loud on auth error (code 9)
- Fail-loud on unexpected message type

---

## Files

- `feeds/kalshi/ws.py` -- implementation
- `tests/test_kalshi_ws.py` -- tests
