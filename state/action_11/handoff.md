# ACT-11 Handoff -- Kill-switch primitives (DELETE batch + group trigger)

**Action.** ACT-11
**Wave.** 0
**Status.** complete-pending-verify
**Implementer.** Claude agent
**Date.** 2026-04-27

---

## What was done

Implemented kill-switch primitives in `engine/kill.py` that provide the
building blocks for the full kill switch (ACT-24, Wave 1).

### Module: `engine/kill.py`

**Batch cancel functions:**
- `batch_cancel_all(client, order_ids)` -- cancel all provided order IDs
  with chunking (100 per batch), retry on partial failure, and fail-loud
  semantics via `KillSwitchError`.
- `batch_cancel_by_event(client, orders_with_tickers, event_ticker)` --
  filter by event prefix, then batch cancel.
- `batch_cancel_by_market(client, orders_with_tickers, market_ticker)` --
  filter by exact market ticker, then batch cancel.
- `filter_orders_by_event()` / `filter_orders_by_market()` -- pure
  filtering helpers (no I/O).

**Atomic retry semantics:**
- On batch API failure, falls back to individual `cancel_order` calls
  to isolate which specific orders failed.
- Only failed IDs are retried on subsequent rounds (configurable
  `max_retries`, default 3).
- Exponential backoff between retry rounds.
- If any IDs remain uncancelled after all retries, raises
  `KillSwitchError` with the list of failed IDs.

**Group trigger (`KillSwitch` class):**
- Holds a `CancelClient` protocol reference and a list of
  `TriggerCondition` callables (each returns `TriggerResult`).
- `check_triggers()` -- synchronous evaluation of all conditions;
  returns the first fired trigger or `None`.
- `check_and_fire(order_ids)` -- sync trigger check + async batch
  cancel; returns `KillSwitchFireResult`.
- Arm/disarm support for cold-start and maintenance.

**Logging:**
- All kill actions logged at WARNING+ via stdlib `logging`.
- Trigger name and detail logged on fire.
- Every cancel attempt and failure logged.

### Gaps closed

- **GAP-171** (observability, contract): Wire `DELETE /orders/batch` and
  `POST /order-groups/{group_id}/trigger` endpoints -- the primitives
  are now implemented and composable. The actual order-group trigger
  endpoint is available via `KalshiClient.trigger_order_group()` from
  ACT-03; this module adds the batch-cancel-with-retry and
  group-trigger composition layer on top.

### Tests: `tests/test_kill.py`

25 tests, all passing:
- Batch cancel: empty list, single order, multiple orders, chunk splitting
- Per-event and per-market filtering and cancellation
- Partial failure: retry succeeds, batch fallback to individual, exhausted retries raises
- KillSwitch trigger: no fire, single fire, first-wins priority, disarm/re-arm
- Synchronous `check_triggers()` path
- Logging assertions (WARNING-level on invoke, trigger fire, and failure)

---

## Files created

| File | Purpose |
|---|---|
| `engine/kill.py` | Kill-switch primitives module |
| `tests/test_kill.py` | Tests (25 cases, all passing) |
| `state/action_11/plan.md` | Implementation plan |
| `state/action_11/handoff.md` | This file |

---

## Files modified

None. No existing files were edited.

---

## Dependencies used

- `feeds.kalshi.client.KalshiClient` (from ACT-03): provides
  `cancel_order()`, `batch_cancel_orders()`, and
  `trigger_order_group()` endpoints.
- `feeds.kalshi.errors.KalshiAPIError`: for typed exception handling
  in fallback path.

---

## Decisions made

None. No open decisions required resolution.

---

## Non-negotiables compliance

- No pandas: confirmed.
- Type hints: all public interfaces typed.
- Fail-loud: `KillSwitchError` raised on partial cancel failure;
  no silent continuation.
- asyncio for I/O only: trigger evaluation is synchronous;
  cancel calls are async.
- No Python loops over markets/strikes in hot path: N/A (this module
  is an emergency path, not the pricing hot path).

---

## What is NOT included (deferred to ACT-24)

- The four trigger conditions themselves (aggregate delta breach,
  PnL drawdown, CME hedge heartbeat, WS reconnect storm) -- GAP-172.
- Windowed reconnect counter -- GAP-180.
- `reduce_only` retry layer for quote reopening.
- Integration with `engine/scheduler.py` priority queue (GAP-178).
- `SanityError` publish-boundary consumer (GAP-179).

---

## Verification checklist

- [ ] `pytest tests/test_kill.py -v` -- 25/25 pass
- [ ] `engine/kill.py` imports cleanly: `python -c "from engine.kill import KillSwitch"`
- [ ] No pandas import anywhere in module
- [ ] All public functions have type hints
- [ ] `KillSwitchError` raised on exhausted retries (fail-loud)
