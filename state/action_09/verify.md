# ACT-09 Verification -- Position store + per-Event signed exposure + max-loss accounting

**Action.** ACT-09
**Verdict.** PASS
**Verifier.** Claude agent (read-only)
**Date.** 2026-04-27

---

## Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Per-market signed quantity (+long, -short) | PASS | `MarketPosition.signed_qty` tracks signed qty; buy-yes=+, sell-yes=-, buy-no=-, sell-no=+; verified in TestBuyYes, TestSellYes, TestBuyNo, TestSellNo |
| 2 | Per-Event aggregated signed exposure | PASS | `PositionStore.get_event_exposure()` sums signed_qty across markets sharing event_ticker; `get_all_event_exposures()` covers all events; verified in TestEventExposure (5 tests) |
| 3 | Max-loss accounting (Kalshi binary payoff) | PASS | Long: max_loss = total_cost_cents; Short: max_loss = abs(qty)*100 - abs(total_cost_cents); Flat: 0. Per-market, per-event, and total aggregation. Verified in TestMarketPositionMaxLoss (3 tests), TestBuyYes, TestSellYes, TestBuyNo, TestTotalMaxLoss |
| 4 | Fill dedup | PASS | `_seen_fill_ids` set; duplicate fill_id silently ignored (idempotent); verified in TestFillDedup |
| 5 | Reconciliation against Kalshi REST portfolio | PASS | `reconcile()` compares local signed_qty vs API `market_exposure`; checks both directions (local not in API, API not local); raises `PositionReconciliationError` on mismatch; validates malformed API input. 8 reconciliation tests pass |
| 6 | Thread safety | PASS | `threading.Lock` acquired in every public method (apply_fill, get_position, get_event_exposure, get_all_event_exposures, max_loss_cents, event_max_loss_cents, total_max_loss_cents, snapshot, clear, reconcile). Concurrent fill test (8 threads x 100 fills) passes |
| 7 | Fail-loud on inconsistent state | PASS | Fill validation raises ValueError for invalid side/action/count/price/fill_id/ticker. Reconciliation mismatch raises PositionReconciliationError. No silent swallowing |
| 8 | No pandas | PASS | No pandas import in state/positions.py |
| 9 | No bare excepts | PASS | No `except:` in state/positions.py |
| 10 | Type hints throughout | PASS | All public methods, dataclass fields, and helper functions have type annotations |
| 11 | Tests pass | PASS | `pytest tests/test_positions.py -v` -- 48 passed in 0.04s |

## Gaps closed

- GAP-083: Position-limit accounting (max-loss aggregation present; $25k cap enforcement deferred to ACT-12 risk gates)
- GAP-116: Per-bucket inventory store (MarketPosition keyed by market_ticker, event_ticker derived)
- GAP-117: Cash and inventory dynamics from fills (apply_fill with cost-basis and realized PnL)
- GAP-119: Per-Event signed dollar-exposure tracker (get_event_exposure)
- GAP-125: Full-cash-collateralisation accounting (cost_per_contract in cents, total_cost_cents tracks capital at risk)

## Note on GAP-130

GAP-130 (configurable sandbox caps $500/bucket, $5,000/Event) is referenced in the positions.py docstring but not implemented here. This is correct -- GAP-130 is a config-driven cap *interface* that belongs in ACT-12 (risk gates), which consumes the max-loss primitives provided by ACT-09. Not a deficiency.

## Additional observations

- Cost-basis accounting correctly handles partial close, full close, and position flip scenarios with realized PnL tracking.
- `snapshot()` and `get_position()` return copies to prevent mutation outside the lock.
- `clear()` resets both positions and fill dedup state.
- All four fill types (buy/sell x yes/no) properly converted to Yes-equivalent signed deltas.

## Downstream

ACT-12 (risk gates) depends only on ACT-09. With ACT-09 now verified-complete, ACT-12 deps are fully met and it is ready to start.
