# ACT-LIP-VIAB Plan -- LIP Viability Analysis

**Action.** ACT-LIP-VIAB
**Wave.** 0 (wave gate)
**Status.** mid-flight
**Deps.** ACT-01 Phase 1a (verified-complete), ACT-LIP-POOL (verified-complete)

---

## Objective

Produce a viability analysis framework that answers the go/no-go question:
"Is the KXSOYBEANW LIP pool large enough, and competition sparse enough,
that full-presence quoting would earn >= $50/day net of fees and hedge cost?"

The module is code-complete and runnable against whatever captured data exists.
It does NOT require 2 weeks of live data to be deliverable; it requires the
data to produce a meaningful report when run.

---

## Deliverables

### 1. `analysis/lip_viability.py` -- Viability analysis module

Loads from DuckDB (CaptureStore + LIPPoolStore), computes:

1. **Daily pool totals** -- Sum of pool_size_usd across all active
   KXSOYBEANW markets, grouped by day.
2. **Competition density** -- Count of distinct price levels with resting
   orders per market per snapshot (proxy for distinct participants).
3. **Simulated our-score at full presence** -- Assume we rest at best
   bid/ask on both sides with 1.5x Target Size (OD-33' default), score
   using the linear distance multiplier from ACT-LIP-SCORE.
4. **Projected revenue** -- (our_share * pool) - maker_fees - hedge_cost.
5. **Go/no-go recommendation** -- $50/day threshold per KC-LIP-01.

### 2. `tests/test_lip_viability.py` -- Tests with synthetic DuckDB data

Covers: pool totals, competition density, score simulation, revenue
projection, fee deduction, go/no-go threshold, insufficient data guard.

### 3. `state/action_lip_viab/handoff.md` -- Handoff document

---

## Data sources

- `CaptureStore` (ACT-01): `orderbook_snapshots`, `trades`, `market_events`
- `LIPPoolStore` (ACT-LIP-POOL): `lip_reward_periods`
- `fees.kalshi_fees.maker_fee` (ACT-10): fee deduction

## Constraints

- No pandas (DuckDB SQL + dataclasses)
- Type hints throughout
- Fail-loud: < 3 days of captured data raises InsufficientDataError
- Configurable hedge cost placeholder (default $5/day)
- Configurable target size multiplier (default 1.5x)
- Structured output (ViabilityReport dataclass)

## Go/no-go criteria

- KC-LIP-01: projected net revenue < $50/day for KXSOYBEANW => NO-GO
- KC-LIP-02: projected share < 5% at full presence => NO-GO (competition)
