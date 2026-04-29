# Phase 60 — Handoff

**Date:** 2026-04-27
**Status:** COMPLETE
**Tests:** 51/51 passing

---

## What was built

### 1. `engine/quoter.py` — Spread-Capture Quoter (F4-ACT-04)

Core function `compute_quotes()` that:
- Posts two-sided quotes around RND fair value (survival probability)
- Targets 3-4c spread (tighter than incumbent 6-8c)
- Applies inventory skew via gamma parameter
- Respects [1, 99] quote band, tick rounding
- Never crosses the spread (bid < best_ask, ask > best_bid)
- Fee-aware: skips posting when spread < round-trip maker fee
- Anti-arb: enforces monotonicity of bids/asks across strikes
- Integrates settlement gate (size_mult, spread_mult)
- Integrates taker-imbalance (withdraw_side)
- Integrates risk gates (risk_ok flag)
- All orders are post_only=True

Key insight from Phase 55: edge is spread capture, not model-vs-mid disagreement.
The quoter posts symmetric tight spreads, with asymmetry from inventory skew,
taker imbalance, and event gates.

### 2. `engine/taker_imbalance.py` — Taker-Imbalance Detector (F4-ACT-16)

- Rolling deque of (timestamp, side) trade classifications
- Trade classification: price vs midpoint (above=buy, below=sell, at=skip)
- Imbalance ratio: |buys - sells| / (buys + sells)
- Configurable: window (60s), threshold (0.7), cooldown (120s), min_trades (5)
- Signal: withdraw_side ("bid" or "ask"), ratio, expires_at
- Signal persists through cooldown even after imbalance drops

### 3. `engine/settlement_gate.py` — Settlement-Gap Risk Gate (F4-ACT-11 + F4-ACT-06 partial)

USDA event schedule + gate state machine:
- Static 2026 calendar: 12 WASDE, ~35 Crop Progress, 4 Grain Stocks, Plantings, Acreage
- Size-down ladder: 75% at 24h, 50% at 18h, 25% at 12h
- Widened zone: 6h before, spread doubles, size at 25%
- Pull-all: 60s before to 15min after release
- Normal: resume after post-window

Gate output: `GateAction(state, size_mult, spread_mult, next_event_name, time_to_event_seconds)`

---

## Test coverage

| File | Tests | Status |
|---|---|---|
| tests/test_quoter.py | 18 | PASS |
| tests/test_taker_imbalance.py | 13 | PASS |
| tests/test_settlement_gate.py | 20 | PASS |
| **Total** | **51** | **ALL PASS** |

---

## Outstanding decisions

- **OD-38 (edge threshold):** Not used. Phase 55 showed model-vs-mid disagreement
  is <2c near ATM on short-dated contracts. Quoter is spread-capture, not edge-capture.
- **OD-39 (taker-imbalance cooldown):** Default 120s. Tunable via ImbalanceConfig.

## Dependencies satisfied

- RND pipeline (engine/rnd/pipeline.py) provides BucketPrices.survival
- Order builder (feeds/kalshi/orders.py) provides round_to_tick, quote band constants
- Fee model (fees/kalshi_fees.py) provides maker_fee
- Risk gates (engine/risk.py) provides RiskGate.check_post_trade
- Kill primitives (engine/kill.py) provides batch cancel

## What's next

- F4-ACT-07 (order pipeline): wire quoter output to REST order submission
- F4-ACT-08 (kill switch e2e): integrate settlement gate hard-kill
- F4-ACT-05 (IBKR hedge): delta aggregation from position store
