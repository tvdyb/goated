# ACT-05 Handoff -- Kalshi WebSocket Multiplex

**Action.** ACT-05
**Wave.** 0
**Status.** complete-pending-verify
**Implementer.** Claude agent
**Date.** 2026-04-27

---

## What was done

Implemented a multiplexed Kalshi WebSocket client that subscribes to
`orderbook_delta`, `user_orders`, and `fill` channels on a single
authenticated connection, with typed event dispatch, reconnection logic,
and sequence gap detection.

---

## Files created

| File | Purpose |
|---|---|
| `feeds/kalshi/ws.py` | WebSocket client implementation |
| `tests/test_kalshi_ws.py` | 41 tests covering all requirements |
| `state/action_05/plan.md` | Implementation plan |
| `state/action_05/handoff.md` | This file |

---

## Files modified

None. No existing files were changed.

---

## Design decisions

1. **Single subscribe per channel**: The Kalshi WS API assigns one `sid` per
   subscribe command. We send one subscribe per channel (not one per channel+ticker
   batch) for clarity and to get distinct sids for sequence tracking.

2. **Callback-based dispatch**: Handlers are registered per event type via
   `on_orderbook_snapshot()`, `on_orderbook_delta()`, `on_user_order()`,
   `on_fill()`. Multiple handlers per type are supported.

3. **Sequence gap detection**: The `orderbook_delta` channel carries a `seq`
   field for snapshot/delta consistency. The client tracks `last_seq` per sid
   and logs warnings on gaps. Downstream consumers (not yet implemented) should
   request a fresh snapshot on gap.

4. **Auth via handshake headers**: Uses ACT-03's `KalshiAuth.build_headers()`
   with method `GET` and path `/trade-api/ws/v2` during the WebSocket
   handshake, consistent with how Kalshi authenticates WS connections.

5. **Fail-loud**: Auth errors (code 9) raise `KalshiAuthError` immediately
   and are not retried. Unknown message types raise `KalshiAPIError`.
   Malformed JSON raises. No silent swallowing.

6. **Reconnection**: `run_forever()` provides exponential backoff
   (1s, 2s, 4s... capped at 30s) with automatic resubscription of all
   tracked channels. Auth errors are fatal and not retried.

---

## Gaps closed

| Gap | Status |
|---|---|
| GAP-131 (Kalshi WS multiplex consumer) | Closed -- orderbook_delta, user_orders, fill channels implemented |

---

## Dependencies provided to downstream

- **ACT-LIP-SCORE / ACT-LIP-COMPETITOR**: `OrderbookDeltaEvent` and `OrderbookSnapshotEvent` provide the orderbook feed for competitor estimation
- **ACT-09 (positions)**: `UserOrderEvent` provides real-time order status
- **GAP-134 (fill ingestion)**: `FillEvent` provides fill stream for markout and P&L

---

## Test results

```
41 passed in 6.24s
```

Full suite: 344 passed, 0 failed.

Test coverage areas:
- Message parsing: snapshot, delta, user_order, fill (all fields, edge cases)
- Auth header generation for WS handshake
- Subscribe command format (single ticker, multiple tickers, multiple channels)
- Subscribe error handling (auth error, not connected)
- Dispatch to handlers (all event types, multiple handlers, error types)
- Sequence gap detection (contiguous, gap, first message)
- Run loop (message dispatch, idle timeout, connection close)
- Reconnection (multiple reconnects, auth error fatal, max attempts)
- Close state management

---

## Verification checklist

- [ ] `feeds/kalshi/ws.py` imports cleanly
- [ ] `python -m pytest tests/test_kalshi_ws.py -v` -- 41 passed
- [ ] `python -m pytest tests/ -v` -- 344 passed, no regressions
- [ ] No pandas, no hot-path concern (this is I/O code)
- [ ] All public interfaces have type hints
- [ ] Fail-loud on auth errors (code 9) and unexpected message types
- [ ] asyncio for I/O only (appropriate for WS client)

---

## Risks / known limitations

1. **No integration test against live Kalshi WS**: All tests use mocked WebSocket.
   First live connection will be during ACT-LIP-POOL or capture Phase 1b work.

2. **Sequence gap recovery not implemented**: Gap is detected and logged, but
   automatic snapshot re-request is not yet implemented. This is downstream
   responsibility (likely ACT-LIP-SCORE's book mirror).

3. **`ticker` and `trade` channels not subscribed**: ACT-05 scope is
   `orderbook_delta` + `user_orders` + `fill` per the plan. The `trade` channel
   for forward-capture (Phase 1b of ACT-01) can be added trivially by
   subscribing to the `trade` channel and adding a `TradeEvent` type.

---

## Resumption pointer

If picking up downstream work:
- To use the WS feed, instantiate `KalshiWebSocket(auth=auth)`, register
  handlers, call `connect()`, `subscribe(channels=[...], market_tickers=[...])`,
  then `run_forever()`.
- For book reconstruction, consume `OrderbookSnapshotEvent` for initial state
  and apply `OrderbookDeltaEvent` incrementally, checking `seq` continuity.
