# ACT-12 Handoff -- Risk Gates

**Action:** ACT-12
**Status:** complete-pending-verify
**Implementer:** Claude agent
**Date:** 2026-04-27

---

## What was done

Implemented risk gates as `engine/risk.py` with three hard caps:

1. **Aggregate book-delta cap** -- total signed exposure across all events.
2. **Per-Event exposure cap** -- signed exposure for any single event.
3. **Max-loss cap** -- total worst-case loss across all positions (dollars, from config).

Two gate types:
- **Pre-trade gate** (`check_pre_trade`): raises `RiskBreachError` if a proposed order would breach any cap. Fail-loud, never silently rejects.
- **Post-trade check** (`check_post_trade`): returns `TriggerResult` for kill-switch integration. Callable via `make_kill_trigger()`.

Config loading via `load_risk_limits()` reads from `config/commodities.yaml` `position_cap.max_loss_dollars` with override support.

## Gaps closed

- GAP-118: Aggregate net-delta cap
- GAP-119: Per-Event signed dollar-exposure tracker
- GAP-120: Risk-gating stage J

## Files created/modified

- `engine/risk.py` -- risk gate module (new)
- `tests/test_risk.py` -- 36 tests (new)
- `state/action_12/plan.md` -- plan (new)
- `state/action_12/handoff.md` -- this file (new)

## Test results

36 tests, 36 passed, 0 failed, 0.05s.

## Dependencies used

- ACT-09: `state/positions.py` (PositionStore, Fill, MarketPosition, EventExposure)
- ACT-11: `engine/kill.py` (TriggerResult for kill-switch integration)
- ACT-04: `feeds/kalshi/ticker.py` (parse_market_ticker)

## Verification checklist

- [ ] `python -m pytest tests/test_risk.py -v` -- 36 pass
- [ ] Pre-trade gate raises RiskBreachError on breach (fail-loud)
- [ ] Post-trade check returns TriggerResult (kill-switch compatible)
- [ ] No pandas imports
- [ ] Full type hints
- [ ] Config loads from commodities.yaml shape
