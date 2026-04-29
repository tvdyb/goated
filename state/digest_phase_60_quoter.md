# Digest: Phase 60 — Asymmetric Quoter + Taker-Imbalance + Settlement Gate

**Date:** 2026-04-27
**Status:** COMPLETE (51/51 tests passing)

---

## Deliverables

| File | Purpose | Tests |
|---|---|---|
| `engine/quoter.py` | Spread-capture quoter around RND fair value | 18 |
| `engine/taker_imbalance.py` | Rolling-window taker-imbalance detector | 13 |
| `engine/settlement_gate.py` | USDA event calendar + settlement-gap gate | 20 |
| `state/action_quoter/plan.md` | Implementation plan | - |
| `state/action_quoter/handoff.md` | Handoff documentation | - |

## Key Design Decision

Per Phase 55 finding: the quoter is **spread-capture**, not edge-capture.
Model fair value and Kalshi midpoint agree within 1-2c on short-dated
KXSOYBEANMON contracts. The edge is posting 3-4c spreads where incumbents
post 6-8c. "Asymmetric" = inventory skew + taker-imbalance withdrawal +
USDA event gates, not model-vs-mid disagreement.

## Architecture

```
RND Pipeline -> BucketPrices.survival[i] = P(S > K_i)
                    |
                    v
              compute_quotes()  <-- EventBook (orderbook state)
                    |            <-- inventory (PositionStore)
                    |            <-- risk_ok (RiskGate)
                    |            <-- gate_size_mult, gate_spread_mult (SettlementGate)
                    |            <-- imbalance_withdraw_side (TakerImbalanceDetector)
                    v
              list[QuoteAction]  --> Order pipeline (F4-ACT-07, future)
```

## Forward references

- Phase 65: wire to order pipeline (REST submission)
- Phase 70: IBKR hedge integration
- Phase 75: backtest validation (M0)
