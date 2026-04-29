# ACT-10 Handoff -- Kalshi taker/maker fee model + round-trip cost subtraction

**Action.** ACT-10
**Wave.** 0
**Status.** complete-pending-verify
**Implementer.** Claude agent
**Date.** 2026-04-27

---

## What was done

Implemented the Kalshi fee model as a standalone `fees/` package per OD-19.

### Files created

| File | Purpose |
|---|---|
| `fees/__init__.py` | Package init; re-exports public API |
| `fees/kalshi_fees.py` | Fee formulas + `FeeSchedule` class |
| `tests/test_kalshi_fees.py` | 42 tests covering all fee scenarios |
| `state/action_10/plan.md` | Implementation plan |
| `state/action_10/handoff.md` | This file |

### Public API

Three pure functions (stateless, no config dependency):
- `taker_fee(price, *, taker_rate=0.07, surcharge=0.0) -> float`
- `maker_fee(price, *, taker_rate=0.07, maker_fraction=0.25, surcharge=0.0) -> float`
- `round_trip_cost(price, buy_role, sell_role, **kwargs) -> float`

One config-backed class:
- `FeeSchedule(series, commodity_config)` -- loads fee parameters from
  the `fees` block of a commodity config dict (as in `config/commodities.yaml`).
  Methods: `.taker_fee()`, `.maker_fee()`, `.round_trip_cost()`.

### Fee formulas implemented

- **Taker:** `ceil(0.07 * P * (1-P) * 100) / 100` (per Phase 07 section 6)
- **Maker:** `ceil(0.25 * 0.07 * P * (1-P) * 100) / 100` (25% of taker)
- **Round-trip:** sum of buy-leg + sell-leg fees for any taker/maker combination
- **Surcharge:** configurable, defaults to 0.0 (null confirmed for KXSOYBEANW)

### Gaps closed

| Gap | Description | Status |
|---|---|---|
| GAP-007 | Kalshi taker/maker fee formula not modelled | Closed |
| GAP-152 | Round-trip cost subtraction absent | Closed |
| GAP-142 | Cancel-vs-amend fee economics | Partially addressed (fee lookup available; cancel-vs-fill decision logic deferred to OMS) |

### Non-negotiables compliance

- Fail-loud: `ValueError` on price outside [0.01, 0.99], unknown series, missing config fields
- No pandas
- Type hints on all public functions and class
- Pure `math.ceil` arithmetic; no numba (not hot-path)

---

## Test results

```
42 passed in 0.05s
```

Test coverage: taker fee (9 tests), maker fee (6 tests), round-trip cost
(6 tests), input validation (7 tests), FeeSchedule config loading (14 tests).

---

## Verify checklist

For the verifier:

- [ ] `python -m pytest tests/test_kalshi_fees.py -v` -- 42 pass
- [ ] `from fees import taker_fee; taker_fee(0.50)` returns `0.02`
- [ ] `from fees import maker_fee; maker_fee(0.50)` returns `0.01`
- [ ] `from fees import FeeSchedule` loads from soy config without error
- [ ] `taker_fee(0.00)` raises `ValueError` (fail-loud)
- [ ] No pandas import anywhere in `fees/`
- [ ] Fee formulas match Phase 07 section 6 and `config/commodities.yaml` soy.fees

---

## Integration notes for downstream actions

- **ACT-26 (backtest M0):** import `FeeSchedule` and call `.round_trip_cost()`
  to subtract fees from gross edge.
- **ACT-LIP-PNL:** LIP reward attribution is NOT in this module. This module
  provides fee deduction only. LIP rewards are posted by the attribution layer.
- **OMS (ACT-06, ACT-22):** Can use `taker_fee()`/`maker_fee()` to compute
  expected fill cost before order submission.
- **Config extension:** To add fee schedules for new series (KXWTIW, KXGOLD,
  etc.), add a `fees` block to that commodity's entry in `config/commodities.yaml`
  following the soy pattern.

---

## Decisions taken

None new. OD-19 (fee table location in `fees/` package) confirmed by implementation.

---

## Risks / open items

- The canonical `kalshi-fee-schedule.pdf` was not fetchable during research.
  The 0.07 taker rate and 0.25 maker fraction should be verified against the
  PDF before go-live (flagged in Phase 07 section 10, item 4).
- Commodity-specific surcharge is null for KXSOYBEANW but should be checked
  per-series for future expansions.
