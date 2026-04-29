# Phase 70 — IBKR Hedge Leg — Digest

**Date:** 2026-04-28
**Status:** COMPLETE

## Summary

Implemented the `hedge/` package for IBKR hedge integration. The package
provides four components:

1. **IBKRClient** (`hedge/ibkr_client.py`) — Async wrapper around IB Gateway
   via `ib_insync`. Connects, places market orders on ZS/ZC futures, queries
   positions and market data. Heartbeat monitoring with exponential backoff
   reconnect. HedgeConnectionError triggers kill switch.

2. **aggregate_delta** (`hedge/delta_aggregator.py`) — Computes portfolio
   delta from Kalshi PositionStore + RND BucketPrices. Uses finite-difference
   density estimation on the survival curve. Filters by event ticker.

3. **compute_hedge_size** (`hedge/sizer.py`) — Converts dollar-delta to
   number of CBOT futures contracts. ZS = 5,000 bushels/contract. Returns
   signed quantity (positive=buy, negative=sell) to offset portfolio delta.

4. **HedgeTrigger** (`hedge/trigger.py`) — Threshold-triggered hedge with
   configurable cooldown (default 60s). Integrates with kill switch: if IB
   disconnected and |delta| > threshold, fires TriggerResult to cancel all
   Kalshi orders.

## Test coverage

- 45 tests in `tests/test_ibkr_hedge.py`
- All IB interactions mocked (no live IB Gateway needed)
- Covers: sizer math, delta aggregation, trigger logic, kill-switch
  integration, client connection/disconnection, error handling

## Non-negotiables verified

- No pandas anywhere in `hedge/`
- Fail-loud: HedgeConnectionError on all connection failures
- Type hints on all public interfaces
- asyncio for I/O only (IBKRClient methods are async)
- `ib_insync` is the only IB dependency (no direct TWS API)

## Files created/modified

- Created: `hedge/__init__.py`, `hedge/ibkr_client.py`,
  `hedge/delta_aggregator.py`, `hedge/sizer.py`, `hedge/trigger.py`
- Created: `tests/test_ibkr_hedge.py`
- Created: `state/action_ibkr_hedge/plan.md`, `state/action_ibkr_hedge/handoff.md`
- Modified: `pyproject.toml` (added `ib_insync` dep + `hedge*` package)
