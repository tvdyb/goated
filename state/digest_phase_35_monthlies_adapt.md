# Phase 35 Digest — Wave 0 Adaptations for Monthlies (F4-ACT-01)

**Phase.** 35
**Action.** F4-ACT-01
**Date.** 2026-04-28
**Verdict.** COMPLETE

---

## Summary

Adapted Wave 0 infrastructure for the F4 pivot from weeklies (KXSOYBEANW) to commodity monthlies (KXSOYBEANMON).

## Changes

1. **cbot_settle.py**: Roll offset now configurable via `fnd_offset_bd` parameter on `roll_date()`, `roll_info()`, and `front_month()`. Default changed from 2 to 15 business days per live API finding in `state/digest_kalshi_research_2026-04-27.md`.

2. **commodities.yaml**: Added `kalshi_monthly` block under `soy` with series `KXSOYBEANMON`, 5c uniform half-line strike spacing, `cbot_daily_settle` reference price mode. Updated `cme_roll_rule` from `fnd_minus_2bd` to `fnd_minus_15bd`.

3. **Ticker parser**: Verified — existing regex `[A-Z][A-Z0-9]+` already handles `KXSOYBEANMON` and `KXCORNMON`. No code change needed, 6 new tests confirm.

4. **Capture target**: `KalshiCaptureSentinel` already parameterized via `series_ticker` constructor arg. Pass `"KXSOYBEANMON"` at instantiation.

## Tests

- 3 updated/new in `test_cbot_settle.py` (15BD default, legacy 2BD, offset configurability)
- 6 new in `test_ticker.py` (KXSOYBEANMON series/event/market parsing, KXCORNMON)
- 722 total tests pass

## Findings from Phase 20/25 resolved

| Finding | Severity | Resolution |
|---|---|---|
| FND-25-01: ACT-08 roll rule FND-2 BD | warn | Changed to FND-15 BD (configurable) |
| FND-25-02: commodities.yaml lacks KXSOYBEANMON | warn | Added kalshi_monthly block |
| FND-25-03: capture.py default is KXSOYBEANW | info | Already parameterized; pass KXSOYBEANMON |
