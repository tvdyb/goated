# ACT-08 Handoff -- CBOT settle resolver + roll + FND + reference-price-mode loader

**Date.** 2026-04-27
**Implementer.** Implementer D
**Status.** complete-pending-verify

---

## What was done

Implemented `engine/cbot_settle.py` which provides:

1. **ZS contract cycle** -- 7-month CBOT soybean futures cycle (F/H/K/N/Q/U/X) with ticker formatting (e.g. `ZSK26`).

2. **First Notice Date (FND)** -- Per CBOT Chapter 11: last business day of the month preceding the delivery month. Reuses `_CBOT_HOLIDAYS` and `_is_cbot_trading_day` from ACT-07's `engine/event_calendar.py`.

3. **Roll logic** -- Roll date = FND minus 2 business days, matching `cme_roll_rule: fnd_minus_2bd` from `config/commodities.yaml`. On/after roll date, `front_month()` advances to the next contract in cycle.

4. **Front-month resolver** -- `front_month(observation_date)` returns the active `ZSContract` for any date in the maintained 2026-2027 range.

5. **Reference-price-mode loader** -- `load_reference_price_mode("cbot_daily_settle", date)` resolves the config value from `soy.kalshi.reference_price_mode` to a `ReferencePriceMode` containing the mode and the associated front-month contract. `cbot_vwap` and `kalshi_snapshot` are recognized but raise `NotImplementedError` per fail-loud policy.

---

## Gaps closed

| Gap | Status |
|---|---|
| GAP-076 (reference-price-mode loader) | closed |
| GAP-077 (CBOT daily-settle resolver + front-month roll) | closed |
| GAP-078 (FND logic + roll-window resolver) | closed |
| GAP-063 (daily settle puller config hook) | partial -- contract identification done; actual price fetching deferred to ACT-16 |

---

## Files added/modified

| File | Change |
|---|---|
| `engine/cbot_settle.py` | **NEW** -- main module |
| `tests/test_cbot_settle.py` | **NEW** -- 28 tests |
| `state/action_08/plan.md` | **NEW** -- plan document |
| `state/action_08/handoff.md` | **NEW** -- this file |

---

## Test results

```
tests/test_cbot_settle.py ............................  28 passed
```

All 28 tests pass. Existing tests unaffected (73 total pass across test_cbot_settle + test_trading_calendar + test_capture).

---

## Non-negotiables compliance

- No pandas: module uses only stdlib (`datetime`, `typing`) + project imports.
- Type hints: all public functions and data structures are fully typed.
- Fail-loud: `ValueError` on out-of-range dates, unknown reference-price modes, unmapped contract months. `NotImplementedError` on recognized-but-unwired modes.
- No numba: not hot-path math; pure Python is appropriate.
- No silent fallbacks: every edge case raises with a descriptive message.

---

## Integration points

- **ACT-07 dependency** (verified): imports `_CBOT_HOLIDAYS`, `_is_cbot_trading_day`, `_HOLIDAY_RANGE_START`, `_HOLIDAY_RANGE_END` from `engine/event_calendar.py`.
- **ACT-02 dependency** (verified): `config/commodities.yaml` provides `soy.kalshi.reference_price_mode: cbot_daily_settle` and `soy.cme_roll_rule: fnd_minus_2bd`.
- **Downstream consumer**: ACT-13 (corridor adapter) will use `front_month()` to identify which ZS contract anchors the theo.

---

## Open items for downstream actions

- ACT-16 (CME ingest): will use `front_month()` to know WHICH contract ticker to subscribe to for daily settlement prices.
- ACT-13 (corridor adapter): will call `load_reference_price_mode()` + `front_month()` to resolve the reference contract.
- GAP-063 completion: actual CBOT settlement price fetching (REST or feed) is a feeds-layer concern, not wired here.

---

## Verify checklist

- [ ] `pytest tests/test_cbot_settle.py` -- 28 pass
- [ ] `front_month(date(2026, 4, 27))` returns `ZSK26`
- [ ] `front_month(date(2026, 4, 28))` returns `ZSN26` (roll day)
- [ ] `first_notice_date(ZSContract("K", 5, 2026))` returns `2026-04-30`
- [ ] `load_reference_price_mode("cbot_daily_settle", date(2026, 4, 27))` returns mode with `ZSK26`
- [ ] Out-of-range dates raise `ValueError`
- [ ] Unknown mode strings raise `ValueError`
- [ ] `cbot_vwap` / `kalshi_snapshot` raise `NotImplementedError`
