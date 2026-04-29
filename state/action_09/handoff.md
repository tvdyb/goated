# ACT-09 Handoff -- Position store + per-Event signed exposure + max-loss accounting

**Action.** ACT-09
**Status.** complete-pending-verify
**Wave.** 0
**Implementer.** Claude agent
**Date.** 2026-04-27

---

## What was built

`state/positions.py` -- thread-safe in-process position store for Kalshi
binary markets. The module provides:

1. **Per-market position tracking** via `MarketPosition` -- signed quantity
   (+long, -short) in Yes-contract equivalents, with cost-basis and
   realized PnL tracking.

2. **Fill application** via `PositionStore.apply_fill(Fill)` -- converts
   all fill types (buy/sell yes/no) into Yes-equivalent signed deltas.
   Handles position increases, partial closes, full closes, and position
   flips with proper cost-basis accounting. Deduplicates by fill_id.

3. **Per-Event aggregated signed exposure** via `get_event_exposure()` --
   sums signed_qty and max_loss across all markets in an event.

4. **Max-loss accounting** -- worst-case loss under Kalshi binary payoff:
   - Long: max loss = total cost paid (contracts become worthless)
   - Short: max loss = |qty| * $1.00 - cost received (settle at $1)

5. **Reconciliation** via `reconcile()` -- compares local state against
   `GET /portfolio/positions` API response. Raises
   `PositionReconciliationError` on any discrepancy (fail-loud).

6. **Thread safety** -- all reads and writes acquire a per-instance
   `threading.Lock`.

## Gaps closed

- GAP-083: Position-limit accounting (Rule 5.19 max-loss dollars)
- GAP-116: Per-bucket inventory store
- GAP-117: Cash and inventory dynamics from fills
- GAP-119: Per-Event signed dollar-exposure tracker
- GAP-125: Full-cash-collateralisation accounting

## Files

- `state/positions.py` -- implementation (350 LoC)
- `tests/test_positions.py` -- 48 tests covering fills, exposure,
  max-loss, reconciliation, thread safety, edge cases
- `state/action_09/plan.md` -- plan
- `state/action_09/handoff.md` -- this file

## Test results

```
48 passed in 0.07s
```

## Dependencies

- **Uses:** `feeds.kalshi.ticker.parse_market_ticker` (ACT-04)
- **Blocks:** ACT-12 (risk gates)

## Verify checklist

- [ ] `pytest tests/test_positions.py -v` passes
- [ ] `state/positions.py` has no pandas import
- [ ] All public methods have type hints
- [ ] Reconciliation mismatch raises (fail-loud)
- [ ] Thread-safe lock on all mutations and reads
