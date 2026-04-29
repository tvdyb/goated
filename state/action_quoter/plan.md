# Phase 60 — Asymmetric Quoter + Taker-Imbalance + Settlement Gate

## Implementation Plan

**Date:** 2026-04-27
**Actions:** F4-ACT-04 (quoter), F4-ACT-16 (taker-imbalance), F4-ACT-11 (settlement gate)

---

## Key Design Insight (from Phase 55)

The edge is **spread capture**, not model-vs-mid disagreement. On short-dated
KXSOYBEANMON contracts (1-3 days), the RND agrees with Kalshi mid within 1-2c.
Incumbent spreads are 6-8c. We post 3-4c spreads around fair value, becoming
the tightest quote on the book.

"Asymmetric" means:
1. Withdraw the side facing adverse taker flow
2. Widen during USDA event windows
3. Reduce size as settlement approaches
4. Post tighter on strikes where incumbent spread is widest

It does NOT mean "post tighter where model disagrees with Kalshi mid."

---

## Deliverables

### 1. `engine/quoter.py` — Spread-Capture Quoter

**Core function:** `compute_quotes(rnd_prices, kalshi_book, positions, risk_limits, fee_schedule, config) -> list[QuoteAction]`

Per-strike logic:
- a. `model_fair = rnd_prices.survival[i]` (Yes-price for half-line >K_i)
- b. Compute bid/ask as `fair - half_spread` / `fair + half_spread`
- c. Half-spread = max(config.min_half_spread, fee_floor + 1c)
- d. Clamp to quote-band [1, 99]
- e. Never cross: bid < best_ask, ask > best_bid
- f. Apply inventory skew: widen the side where inventory is growing
- g. Apply settlement gate multiplier (from settlement_gate)
- h. Apply taker-imbalance withdrawal (from taker_imbalance)
- i. Check risk gates (ACT-12). If breached, emit CancelOrder
- j. Check fee threshold: spread < round_trip_fee -> skip
- k. Every order: post_only=True
- l. Anti-arb check across strikes

**Config dataclass:** `QuoterConfig` with min_half_spread, max_half_spread,
inventory_skew_gamma, fee_threshold_cents, max_contracts_per_strike.

### 2. `engine/taker_imbalance.py` — Taker-Imbalance Detector

- Rolling deque of (timestamp, side) tuples
- Classify trades: price > mid = buy-initiated, price < mid = sell-initiated
- `imbalance_ratio = |buys - sells| / (buys + sells)`
- When ratio > threshold (default 0.7): signal withdrawal of adverse side
- Signal decays after cooldown (default 120s)

### 3. `engine/settlement_gate.py` — Settlement-Gap Gate

- Reads USDA event calendar (static dates for 2026)
- `gate_state(now) -> GateAction` enum: NORMAL, SIZE_DOWN_75, SIZE_DOWN_50,
  SIZE_DOWN_25, PULL_ALL, WIDENED
- Size-down ladder: 24h run-up, 50% per 6h block
- Pre-window pull: 60s before release -> PULL_ALL
- Wide-out: doubles spread in volatile window
- Post-window: 15min after release -> NORMAL
- Hard kill integration: unrealized PnL exceeds threshold -> kill

### 4. USDA Event Schedule (extend event_calendar.py or new module)

Static calendar for 2026: WASDE monthly, Crop Progress weekly Mon 16:00 ET
(Apr-Nov), Quarterly Stocks, Acreage, Plantings.

---

## Dependencies (all verified-complete)

- ACT-05 WS client (feeds/kalshi/ws.py)
- ACT-06 order builder (feeds/kalshi/orders.py)
- ACT-09 positions (state/positions.py)
- ACT-10 fees (fees/kalshi_fees.py)
- ACT-11 kill primitives (engine/kill.py)
- ACT-12 risk gates (engine/risk.py)
- ACT-13 corridor adapter (engine/corridor.py)
- Phase 50 RND pipeline (engine/rnd/pipeline.py)

## Non-negotiables

- No pandas in hot path
- numba.njit on hot-path math
- Fail-loud (raise, never return defaults)
- asyncio for I/O only; synchronous main loop
- post_only=True on every order
- scipy.special.ndtr over scipy.stats.norm.cdf
