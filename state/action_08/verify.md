# ACT-08 Verification Report

**Date.** 2026-04-27
**Verifier.** Claude Opus 4.6 (read-only)
**Verdict.** PASS

---

## Gaps verified

| Gap | Requirement | Status | Evidence |
|---|---|---|---|
| GAP-076 | Appendix-A reference-price-mode loader (CBOT settle / VWAP / Kalshi snap) | CLOSED | `load_reference_price_mode()` in `engine/cbot_settle.py:237-274`; reads mode string, resolves front-month contract; `cbot_daily_settle` wired, `cbot_vwap`/`kalshi_snapshot` raise `NotImplementedError` per fail-loud. Config field `soy.kalshi.reference_price_mode: cbot_daily_settle` present at `config/commodities.yaml:77`. |
| GAP-077 | CBOT Rule 813 daily-settle resolver + front-month roll calendar | CLOSED | `front_month()` at line 194; 7-month ZS cycle (F/H/K/N/Q/U/X) at line 36; `roll_date()` at line 165; ticker formatting via `ZSContract.ticker` property. |
| GAP-078 | Soybean FND logic (T-2 BD before delivery month) + roll-window resolver | CLOSED | `first_notice_date()` at line 141: last business day of month preceding delivery month per CBOT Chapter 11. `roll_date()` = FND minus 2 business days, matching `cme_roll_rule: fnd_minus_2bd` from `config/commodities.yaml:64`. |

---

## Code review: engine/cbot_settle.py

- **ZS contract cycle**: 7 months correctly mapped (lines 36-44). Ordered cycle built via sorted() (line 47-49).
- **FND**: Correctly computes last business day of preceding month. Handles January delivery (wraps to prior year December). Reuses `_is_cbot_trading_day` from ACT-07.
- **Roll logic**: FND minus 2 business days via `_subtract_business_days`. `front_month()` returns first contract whose roll date has not been reached.
- **Reference-price-mode loader**: Validates against `_SUPPORTED_MODES` frozenset. Unknown modes raise `ValueError`. Known-but-unwired modes raise `NotImplementedError`. Only `cbot_daily_settle` returns a result.
- **Integration with ACT-07**: Imports `_CBOT_HOLIDAYS`, `_is_cbot_trading_day`, `_HOLIDAY_RANGE_START`, `_HOLIDAY_RANGE_END` from `engine/event_calendar.py`.
- **Range guard**: `_check_range()` raises `ValueError` for dates outside maintained CBOT holiday range.

---

## Non-negotiables

| Check | Result |
|---|---|
| No `import pandas` | PASS -- no matches |
| No bare `except:` or swallowed `except Exception:` | PASS -- no matches. One `except ValueError: continue` in `front_month()` is intentional (skips out-of-range contracts; raises if no contract found). |
| No `return 0` / `return None` silent fallbacks | PASS -- no matches |
| Fail-loud on invalid inputs | PASS -- `ValueError` on out-of-range dates, unknown modes; `NotImplementedError` on unwired modes |
| Type hints on public API | PASS -- all public functions and NamedTuples fully typed |
| No numba required | PASS -- not hot-path math |

---

## Tests: tests/test_cbot_settle.py

```
28 passed in 0.03s
```

Coverage summary:
- **ZSContract basics**: ticker format, cycle length, cycle order (4 tests)
- **FND**: May 2026, Jul 2026, Jan 2027, Aug 2026 (weekend skip), holiday skip, Nov 2026 (6 tests)
- **Roll date**: May 2026 roll = Apr 28, roll < FND assertion, roll_info consistency (3 tests)
- **Front month**: early 2026, Apr 27 (pre-roll = ZSK26), Apr 28 (roll day = ZSN26), monotonic progression across year (4 tests)
- **Reference-price-mode**: cbot_daily_settle success, unknown mode ValueError, cbot_vwap NotImplementedError, kalshi_snapshot NotImplementedError (4 tests)
- **Fail-loud**: before range, after range, FND outside range (3 tests)
- **Helper**: _last_day_of_month for Feb non-leap, Feb leap, December, April (4 tests)

Edge cases covered: month boundaries, year boundaries (Jan 2027 -> Dec 2026), holiday handling, roll-day boundary (Apr 27 vs Apr 28).

---

## Git status

`engine/cbot_settle.py` is untracked (not yet committed). `tests/test_cbot_settle.py` is also untracked. This is acceptable for verification -- the code exists and tests pass. Committing is the implementer's responsibility.

---

## Config integration

`config/commodities.yaml` contains:
- Line 64: `cme_roll_rule: "fnd_minus_2bd"`
- Line 77: `reference_price_mode: "cbot_daily_settle"`

Both match the implementation's expectations.

---

## Downstream impact

- ACT-13 (corridor adapter) depends on ACT-04 + ACT-08. ACT-08 is now verified-complete; ACT-04 remains unstarted. ACT-13 stays blocked.
- ACT-16 (CME ingest) will consume `front_month()` for contract identification.

---

## Verdict: PASS

All three gaps (GAP-076, GAP-077, GAP-078) are closed. Non-negotiables satisfied. 28/28 tests pass. Fail-loud behavior confirmed.
