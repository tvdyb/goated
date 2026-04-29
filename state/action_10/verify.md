# ACT-10 Verification Report

**Action.** ACT-10 -- Kalshi taker/maker fee model + round-trip cost subtraction
**Wave.** 0
**Verifier.** Claude agent
**Date.** 2026-04-27
**Verdict.** PASS

---

## 1. Gap closure

### GAP-007 (Kalshi taker/maker fee formula not modelled) -- CLOSED

- Taker fee formula implemented in `fees/kalshi_fees.py:taker_fee()`:
  `ceil(0.07 * P * (1 - P) * 100) / 100` -- matches Kalshi published structure.
- Maker fee formula: `ceil(0.25 * 0.07 * P * (1 - P) * 100) / 100` -- 25% of taker, matches `config/commodities.yaml` soy.fees.maker_fraction.
- Configurable taker_rate, maker_fraction, and surcharge parameters.

### GAP-152 (Round-trip cost subtraction absent) -- CLOSED

- `round_trip_cost()` implemented covering all four role combinations:
  taker/taker, maker/taker, taker/maker, maker/maker.
- FeeSchedule class provides config-backed `.round_trip_cost()` method.

### GAP-142 (Cancel-vs-amend fee economics) -- PARTIALLY ADDRESSED

- Fee lookup functions available for OMS to use; cancel-vs-fill decision
  logic deferred to OMS as documented.

---

## 2. Code review

### fees/kalshi_fees.py

- Taker fee formula: correct. `math.ceil(taker_rate * price * (1.0 - price) * 100.0) / 100.0`
- Maker fee formula: correct. `math.ceil(maker_fraction * taker_rate * price * (1.0 - price) * 100.0) / 100.0`
- Price validation: `ValueError` raised for price outside [0.01, 0.99].
- Role validation: `ValueError` raised for unknown buy_role/sell_role.
- FeeSchedule class: loads from commodity config dict, validates all required fields (kalshi block, series match, fees block, taker_formula, maker_fraction). Fail-loud on any missing field.
- `_parse_taker_rate()`: regex extraction of rate from formula string -- robust, raises ValueError on parse failure.

### fees/__init__.py

- Re-exports `taker_fee`, `maker_fee`, `round_trip_cost`, `FeeSchedule` in `__all__`.

### config/commodities.yaml

- soy.fees block present with `taker_formula: "ceil(0.07 * P * (1 - P) * 100) / 100"`, `maker_fraction: 0.25`, `surcharge: null`.

---

## 3. Non-negotiables

| Check | Result |
|---|---|
| No `import pandas` in fees/ | PASS -- no matches |
| No bare `except:` or swallowing `except Exception:` | PASS -- no matches |
| No `return 0` fallback patterns | PASS -- no matches |
| Fail-loud on invalid price | PASS -- ValueError raised |
| Fail-loud on missing config | PASS -- ValueError raised for missing kalshi block, fees block, taker_formula, maker_fraction, series mismatch |
| Type hints on public API | PASS -- all public functions and class methods have type hints |
| Pure math.ceil, no numba/pandas | PASS |

---

## 4. Test results

```
42 passed in 0.03s
```

Breakdown:
- TestTakerFee: 10 tests (midpoint, P=0.22, P=0.10, P=0.90, min/max price, symmetry over full grid, fee-never-zero, peaks-at-midpoint, surcharge)
- TestMakerFee: 6 tests (midpoint, P=0.22, min/max price, maker<=taker invariant over full grid, symmetry)
- TestRoundTripCost: 6 tests (all four role combos at midpoint, edge prices, surcharge on both legs)
- TestValidation: 7 tests (price=0, price=1, negative, above-one, invalid buy_role, invalid sell_role, maker_fee at price=0)
- TestFeeSchedule: 13 tests (load from config, taker/maker/round-trip via class, series mismatch, missing kalshi/fees/taker_formula/maker_fraction blocks, surcharge config, repr, custom taker rate)

Coverage: fee calculations at key prices, symmetry, maker<=taker invariant, all round-trip combos, fail-loud validation, config loading -- all confirmed.

---

## 5. Git status

- `fees/` directory exists on disk as untracked (not yet committed to git).
- `state/action_10/` files (plan.md, handoff.md) also present.
- This is expected for complete-pending-verify status; commit happens after verification.

---

## 6. Handoff completeness

- Files listed: all present and verified.
- Public API: matches plan.
- Gaps closed: GAP-007 and GAP-152 confirmed closed; GAP-142 partially addressed.
- Integration notes: downstream consumers (ACT-26, ACT-LIP-PNL, OMS) documented.
- Risks: rate verification against PDF flagged -- appropriate.

---

## Verdict: PASS

All success criteria met. ACT-10 is verified-complete.
