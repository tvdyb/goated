# Action: IBKR Hedge Leg — Handoff

**Phase:** 70
**Status:** COMPLETE
**Date:** 2026-04-28

## What was built

The `hedge/` package providing IBKR hedge integration for Kalshi commodity
monthly market-making:

| File | Purpose |
|---|---|
| `hedge/__init__.py` | Package init, re-exports |
| `hedge/ibkr_client.py` | IB Gateway async wrapper via `ib_insync` |
| `hedge/delta_aggregator.py` | Aggregate Kalshi book delta from PositionStore + BucketPrices |
| `hedge/sizer.py` | ZS/ZC futures contract sizer |
| `hedge/trigger.py` | Threshold-triggered hedge with cooldown + kill-switch integration |

## Test results

- `tests/test_ibkr_hedge.py`: **45 tests passing**
- Full suite: **818 tests passing** (0 regressions)
- Lint: all checks passing (`ruff check hedge/ tests/test_ibkr_hedge.py`)

## Key design decisions

1. **Deferred `ib_insync` imports** — The package may not be installed in CI
   or dev environments without IB Gateway. All `ib_insync` imports are inside
   methods with ImportError -> HedgeConnectionError fallback.

2. **Delta aggregator uses finite-difference density** — Survival curve from
   BucketPrices is differentiated numerically to get f(K), then
   delta_i = q_i * f(K_i). Not hot-path.

3. **Sizer returns signed contracts** — Positive = buy, negative = sell.
   Direction offsets the portfolio delta. Minimum 1 contract.

4. **Kill-switch integration** — HedgeTrigger.make_kill_trigger() returns
   a callable that fires when IB is disconnected AND |delta| > threshold.
   Plugs directly into KillSwitch.add_trigger().

5. **Connection monitoring** — Heartbeat every 5s, exponential backoff
   reconnect (1s -> 30s max), HedgeConnectionError after 15s timeout (OD-25).

## Dependencies added

- `ib_insync >= 0.9.86` added to `pyproject.toml` runtime dependencies
- `hedge*` added to setuptools package discovery

## Gaps closed

- GAP-102: IBKR hedge client
- GAP-103: Delta aggregation from Kalshi positions
- GAP-104: Futures sizer
- GAP-108: Kill-switch integration for hedge disconnection

## What's next

- Phase 75: Review this implementation (independent reviewer)
- F4-ACT-08 (kill switch composition) can now integrate the hedge trigger
- Live testing requires IB Gateway running with CME futures permission
