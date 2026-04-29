# Verify -- ACT-LIP-VIAB

**Action.** ACT-LIP-VIAB (LIP viability analysis framework)
**Verdict.** PASS
**Verifier.** Claude Opus 4.6 (read-only)
**Date.** 2026-04-27

---

## Checklist

### 1. Data loading from DuckDB

- [x] Loads orderbook snapshots from CaptureStore (ACT-01 schema: `orderbook_snapshots` table with `ticker`, `captured_at`, `yes_levels`, `no_levels`)
- [x] Loads pool data from LIPPoolStore (ACT-LIP-POOL schema: `lip_reward_periods` table with `market_ticker`, `pool_size_usd`, `start_date`, `end_date`)
- [x] Both connections opened read-only

### 2. Pipeline stages

- [x] **Data sufficiency check:** raises `InsufficientDataError` on < 3 days (configurable via `min_days`). Tested with 0 days (empty DB) and 2 days.
- [x] **Daily pool totals:** sums `pool_size_usd` across all `KXSOYBEANW%` markets grouped by `start_date`. Returns `list[DailyPoolTotal]`.
- [x] **Competition density:** parses JSON yes/no levels from orderbook snapshots, counts distinct price levels as participant proxy. Returns `list[CompetitionEstimate]`.
- [x] **Score simulation at full presence:** computes `our_score = 2 * target_size * multiplier` (both sides, at inside, distance multiplier = 1.0 per OD-33'). Adds to visible score; computes projected share. Linear distance multiplier decay implemented correctly in `_compute_visible_score`.
- [x] **Revenue projection:** `(share * pool) - maker_fees - hedge_cost`. Uses `fees.kalshi_fees.maker_fee` (ACT-10). Placeholder hedge cost configurable (default $5/day).
- [x] **Go/no-go:** gated on KC-LIP-01 ($50/day net revenue threshold) and KC-LIP-02 (5% share threshold). Both configurable. Produces structured `ViabilityReport` with `go: bool`, `kill_criteria_triggered: list[str]`, and `recommendation: str`.

### 3. Kill criteria

- [x] KC-LIP-01: triggered when `daily_net_usd < revenue_threshold_per_day_usd` (default $50). Confirmed in test `test_nogo_pool_too_small`.
- [x] KC-LIP-02: triggered when `avg_share < share_threshold_pct` (default 5%). Confirmed in test `test_nogo_competition_too_dense`.

### 4. Non-negotiables

- [x] **No pandas:** zero pandas imports; all queries via DuckDB SQL, results in dataclasses.
- [x] **Fail-loud:** `InsufficientDataError` raised on < 3 days. No silent extrapolation. Tested explicitly.
- [x] **Type hints:** all public interfaces fully typed (`-> ViabilityReport`, `-> list[DailyPoolTotal]`, etc.). Frozen dataclasses with `slots=True`.

### 5. Tests

- [x] 21 tests pass in 0.94s
- [x] Coverage: level parsing (4 tests), visible score computation (4 tests), data sufficiency (3 tests), pool totals (1 test), competition estimates (1 test), score simulation (2 tests including monotonicity in target size), revenue projection (1 test), go/no-go scenarios (GO, NO-GO KC-LIP-01, NO-GO KC-LIP-02, insufficient data raises), full report structure (1 test).
- [x] Tests use synthetic DuckDB data with realistic schemas matching ACT-01 and ACT-LIP-POOL.

### 6. Fee integration

- [x] Uses `fees.kalshi_fees.maker_fee(price, taker_rate=..., maker_fraction=...)` -- signature matches ACT-10's verified implementation exactly.

### 7. Output structure

- [x] `ViabilityReport` dataclass contains all required fields: observation window, daily pool totals, competition estimates, score simulations, revenue projection, go/no-go flag, kill criteria list, and recommendation string.

---

## Result

**PASS.** All success criteria met. No failures found.
