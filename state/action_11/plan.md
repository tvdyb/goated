# ACT-11 Plan -- Kill-switch primitives (DELETE batch + group trigger)

**Action.** ACT-11
**Wave.** 0
**Effort.** M
**Deps.** ACT-03 (complete-pending-verify -- code exists)
**Gaps closed.** GAP-171 (wire two endpoints + group trigger)

---

## Scope

ACT-11 delivers the **building blocks** for the kill switch. The full
four-trigger kill switch (aggregate delta breach, PnL drawdown, hedge
heartbeat, WS reconnect storm) is ACT-24 in Wave 1. ACT-11 provides
only the cancellation primitives and a composable group-trigger
mechanism.

---

## Module: `engine/kill.py`

### 1. Batch cancel

- `batch_cancel_all(client, order_ids)` -- cancel every open order
  globally. Accepts a list of order IDs (caller is responsible for
  fetching the open-order list). Uses `KalshiClient.batch_cancel_orders`.
- `batch_cancel_by_event(client, order_ids, event_ticker)` -- cancel
  all orders whose ticker starts with the given event prefix.
- `batch_cancel_by_market(client, order_ids, market_ticker)` -- cancel
  orders for a specific market ticker.

### 2. Atomic semantics / retry

If a batch cancel partially fails (some IDs rejected, API error on
subset), the module:
1. Identifies which order IDs were NOT successfully cancelled.
2. Retries the remaining IDs up to `max_retries` times (default 3).
3. If any IDs remain uncancelled after exhausting retries, raises
   `KillSwitchError` with the list of failed IDs.
4. Logs every attempt and every failure (fail-loud).

### 3. Group trigger

- `KillSwitch` class: holds a `KalshiClient` reference and a list of
  `TriggerCondition` callables (each returns `bool`).
- `check_triggers()` method: evaluates all conditions; if ANY fires,
  executes the batch cancel and logs the triggering condition.
- This is a synchronous check (called from the main loop per
  non-negotiable). The batch cancel itself is async (I/O).

### 4. Logging

All kill actions logged via stdlib `logging` at WARNING+ level:
- Trigger condition that fired (name + details)
- Order IDs submitted for cancellation
- Success/failure per batch attempt
- Final outcome (all cancelled vs partial failure)

---

## Non-negotiables compliance

- No pandas
- Type hints on all public interfaces
- Fail-loud: partial cancel failure raises, never silently continues
- asyncio for I/O only (batch cancel is async; trigger check is sync)

---

## Test plan

File: `tests/test_kill.py`

1. Batch cancel all orders -- mock client, verify all IDs submitted
2. Batch cancel per-event -- verify filtering by event prefix
3. Batch cancel per-market -- verify filtering by market ticker
4. Partial failure + retry -- mock first call failing for subset,
   verify retry with remaining IDs
5. Exhausted retries raises `KillSwitchError`
6. Group trigger fires on condition -- one of N conditions returns True
7. Group trigger does not fire when all conditions False
8. Logging assertions on kill actions
