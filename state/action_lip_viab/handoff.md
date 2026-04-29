# Handoff -- ACT-LIP-VIAB

**Action.** ACT-LIP-VIAB (LIP viability analysis framework)
**Status.** complete-pending-verify
**Wave.** 0 (wave gate)
**Implementer.** Implementer J
**Date.** 2026-04-27

---

## What was done

Built the LIP viability analysis framework that loads captured orderbook
and pool data from DuckDB and produces a structured go/no-go recommendation
per KC-LIP-01 ($50/day net revenue threshold) and KC-LIP-02 (5% share
threshold).

### Files created

- `analysis/__init__.py` -- package init
- `analysis/lip_viability.py` -- core analysis module
- `tests/test_lip_viability.py` -- 21 tests with synthetic DuckDB data
- `state/action_lip_viab/plan.md` -- action plan
- `state/action_lip_viab/handoff.md` -- this file

### Module capabilities

The `LIPViabilityAnalyzer` loads from two DuckDB databases:

1. **CaptureStore** (ACT-01): orderbook_snapshots for competition density
   and visible score estimation.
2. **LIPPoolStore** (ACT-LIP-POOL): lip_reward_periods for daily pool
   totals.

Pipeline stages:
1. Data sufficiency check (fail-loud on < 3 days)
2. Daily pool totals across all active KXSOYBEANW markets
3. Competition density (distinct price levels as participant proxy)
4. Simulated our-score at full presence (1.5x Target Size at inside,
   both sides, distance multiplier = 1.0)
5. Revenue projection (pool share - maker fees - hedge cost)
6. Go/no-go recommendation

Output is a structured `ViabilityReport` dataclass.

### Test results

```
21 passed in 1.05s
```

Tests cover: level parsing, visible score computation, data sufficiency,
pool totals, competition estimates, score simulation, share monotonicity
in target size, revenue projection with fees/hedge, GO scenario, NO-GO
(KC-LIP-01), NO-GO (KC-LIP-02), insufficient data raises, and full
report structure validation.

---

## Non-negotiables compliance

- No pandas: all queries via DuckDB SQL, results in dataclasses
- Type hints: all public interfaces fully typed
- Fail-loud: InsufficientDataError raised on < 3 days of data
- Uses ACT-10 fee model (fees.kalshi_fees.maker_fee)
- Uses ACT-LIP-SCORE distance multiplier model (linear decay)

---

## Dependencies used

- ACT-01 Phase 1a (verified-complete): CaptureStore schema
- ACT-LIP-POOL (verified-complete): LIPPoolStore schema
- ACT-10 (verified-complete): maker_fee function
- ACT-LIP-SCORE (complete-pending-verify): distance multiplier model
  (reimplemented inline for independence; same linear decay formula)

---

## What remains

- Run against production captured data when 2+ weeks of KXSOYBEANW
  orderbook + pool data have accumulated
- The go/no-go result gates Wave 1 engineering
- If GO: proceed to Wave 1
- If NO-GO: pivot per F3 section 7 kill criteria

---

## Resumption pointer

To run the viability analysis against real data:

```python
from analysis.lip_viability import LIPViabilityAnalyzer, ViabilityConfig

analyzer = LIPViabilityAnalyzer(
    capture_db_path="data/capture/kalshi_capture.duckdb",
    pool_db_path="data/capture/lip_pools.duckdb",
)
report = analyzer.run()
print(report.recommendation)
analyzer.close()
```
