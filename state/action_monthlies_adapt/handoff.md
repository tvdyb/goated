# F4-ACT-01 — Wave 0 Adaptations for Monthlies: Handoff

**Status.** COMPLETE
**Date.** 2026-04-28
**Tests.** 9 new/updated tests, 722 total pass

## Changes

1. **cbot_settle.py**: Roll offset now configurable via `fnd_offset_bd` parameter. Default changed from 2 to 15 business days (FND-15 BD for commodity monthlies). Legacy 2BD offset available via `fnd_offset_bd=2`.

2. **commodities.yaml**: Added `kalshi_monthly` block under `soy` with `KXSOYBEANMON` series, 5c strike spacing. Updated `cme_roll_rule` from `fnd_minus_2bd` to `fnd_minus_15bd`.

3. **Ticker parser**: Verified — `KXSOYBEANMON` already works with existing regex patterns. 6 new tests confirm series, event, and market parsing for `KXSOYBEANMON` and `KXCORNMON`.

4. **Capture target**: `KalshiCaptureSentinel` already accepts `series_ticker` as constructor param. Pass `"KXSOYBEANMON"` at instantiation.

## Tests added/updated

- `test_cbot_settle.py`: Updated roll date assertions for 15BD default, added legacy 2BD test, offset configurability test
- `test_ticker.py`: 6 new tests for KXSOYBEANMON/KXCORNMON parsing
