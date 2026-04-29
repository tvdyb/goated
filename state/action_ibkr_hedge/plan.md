# Action: IBKR Hedge Leg — Implementation Plan

**Phase:** 70
**Status:** IN-PROGRESS
**Dependencies:** Phase 65 (quoter review PASS), OD-11 (IB confirmed)

## Scope

Build the `hedge/` package: IB Gateway client, delta aggregator,
futures sizer, and threshold-triggered hedge execution.

## Deliverables

| File | Purpose |
|---|---|
| `hedge/__init__.py` | Package init, re-exports |
| `hedge/ibkr_client.py` | IB Gateway async wrapper via `ib_insync` |
| `hedge/delta_aggregator.py` | Aggregate Kalshi book delta from PositionStore + BucketPrices |
| `hedge/sizer.py` | ZS/ZC futures contract sizer |
| `hedge/trigger.py` | Threshold-triggered hedge with cooldown + kill-switch integration |
| `tests/test_ibkr_hedge.py` | Full test suite (mocked IB, unit tests for all components) |

## Design decisions

1. **IB client is async-only** — `ib_insync` is inherently async. The hedge
   trigger fires from the synchronous main loop but dispatches the IB order
   via `asyncio.run_coroutine_threadsafe` or equivalent.

2. **Delta aggregator uses numerical derivative** — `d(P(S>K))/dS` is
   approximated from the BucketPrices survival curve via finite differences.
   This is NOT hot-path (runs once per hedge check, not per tick).

3. **Sizer rounds to nearest integer** — minimum 1 contract when hedge is
   triggered. `N_ZS = round(delta_port / (contract_size * price))`.

4. **Trigger integrates with kill switch** — if IB disconnected and
   `|delta_port| > threshold`, the trigger returns a TriggerResult that
   the KillSwitch can consume to cancel all Kalshi orders.

5. **Connection monitoring** — heartbeat every 5s, exponential backoff
   reconnect (1s, 2s, 4s, 8s, max 30s). HedgeConnectionError after
   configurable timeout (default 15s per OD-25).

## Constraints

- No pandas
- Fail-loud on connection failures
- `ib_insync` is the only IB dependency
- All public methods have type hints
