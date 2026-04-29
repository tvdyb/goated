# Phase 80 — Live Small Deployment: Implementation Plan

**Date:** 2026-04-28
**Action:** LIVE-DEPLOY
**Effort:** XL
**Prerequisites:** Phase 55 PASS, Phase 65 PASS, Phase 75 PASS

---

## Objective

Wire all Phase 50-75 components into a single-process deployment that runs the
full trading loop: CME ingest -> RND pipeline -> quoter -> Kalshi order
submission -> position tracking -> risk monitoring -> hedge trigger -> IB hedge.

Capital cap: $1,000 max for first 2 weeks. KXSOYBEANMON only.

---

## Components to wire

| Component | Module | Status |
|---|---|---|
| CME options chain ingest | `feeds/cme/options_chain.py` | verified (Phase 45) |
| RND pipeline | `engine/rnd/pipeline.py` | verified (Phase 55) |
| Quoter | `engine/quoter.py` | verified (Phase 65) |
| Settlement gate | `engine/settlement_gate.py` | verified (Phase 65) |
| Taker-imbalance detector | `engine/taker_imbalance.py` | verified (Phase 65) |
| Kill switch | `engine/kill.py` | verified (Wave 0) |
| Risk gates | `engine/risk.py` | verified (Wave 0) |
| Position store | `state/positions.py` | verified (Wave 0) |
| Kalshi client | `feeds/kalshi/client.py` | verified (Wave 0) |
| IBKR hedge client | `hedge/ibkr_client.py` | verified (Phase 75) |
| Delta aggregator | `hedge/delta_aggregator.py` | verified (Phase 75) |
| Hedge trigger | `hedge/trigger.py` | verified (Phase 75) |
| Hedge sizer | `hedge/sizer.py` | verified (Phase 75) |
| Fee model | `fees/kalshi_fees.py` | verified (Wave 0) |

---

## Deliverables

1. `deploy/config.yaml` — externalized configuration
2. `deploy/main.py` — main entry point wiring everything
3. `attribution/pnl.py` — live PnL attribution
4. `deploy/README.md` — operational runbook
5. `tests/test_integration.py` — integration tests

---

## Main loop design (30-second cycle)

```
every 30 seconds:
  1. Pull CME options chain (cached, refresh every 15 min)
  2. Run RND pipeline -> model fair values (BucketPrices)
  3. Pull Kalshi orderbook snapshots for all active strikes
  4. Check settlement gate -> if PULL_ALL, cancel all and skip
  5. Check taker imbalance -> mark adverse sides
  6. Run quoter -> compute quote actions per strike
  7. Execute quote actions via Kalshi REST
  8. Update position store from fills
  9. Compute aggregate delta
 10. Check hedge trigger -> if threshold exceeded, hedge via IB
 11. Check risk gates -> if breached, fire kill switch
 12. Log PnL attribution
```

---

## Risk controls

- Capital cap: max_loss_cents <= 100_000 ($1,000)
- Per-event cap: $500
- Kill switch triggers: risk breach, IB disconnect + delta, PnL drawdown
- Settlement gate: USDA event calendar
- All orders: post_only=True

---

## Success criteria

- All components wired end-to-end
- Configuration externalized (env vars for secrets)
- Capital cap enforced ($1,000)
- Kill switch works in integration test
- Operational runbook covers start/stop/kill/PnL/reconciliation
- All tests pass
