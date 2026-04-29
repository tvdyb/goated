# ACT-08 Plan -- CBOT settle resolver + roll + FND + reference-price-mode loader

**Date.** 2026-04-27
**Author.** Implementer D
**Status.** planned

---

## Gaps closed

- GAP-076: Appendix-A reference-price-mode loader (CBOT settle / VWAP / Kalshi snap)
- GAP-077: CBOT Rule 813 daily-settle resolver + front-month roll calendar
- GAP-078: Soybean FND logic (T-2 BD before delivery month) + roll-window resolver
- GAP-063 (partial): daily settle puller config hook

---

## Design

### 1. ZS contract month cycle

ZS lists: F(Jan), H(Mar), K(May), N(Jul), Q(Aug), U(Sep), X(Nov).
Stored as a module-level constant mapping month-code to delivery month number.

### 2. Front-month identification

Given an observation date, the "front month" is the nearest ZS contract month
whose First Notice Date (FND) has not yet triggered the roll. The roll trigger
is **2 business days before FND** (per `cme_roll_rule: fnd_minus_2bd` in
commodities.yaml).

### 3. First Notice Date (FND)

Per CBOT Chapter 11, First Notice Day for soybeans is the **last business day
of the month preceding the delivery month**. E.g., for the May (K) contract,
FND is the last business day of April. Business day = not weekend, not CBOT
holiday (reusing `_CBOT_HOLIDAYS` and `_is_cbot_trading_day` from
`engine/event_calendar.py`).

### 4. Roll logic

Roll date = FND minus 2 business days. On and after the roll date, the front
month flips to the next contract in the cycle. This matches
`cme_roll_rule: fnd_minus_2bd`.

### 5. ZS contract ticker

Format: `ZS` + month-code + 2-digit year. E.g., `ZSK26` for May 2026.

### 6. CBOT daily settlement price resolver

Per CBOT Rule 813, the daily settlement for ZS is determined around 1:14-1:15 PM CT
(end of day session) as a VWAP in the settlement window. This module does NOT
fetch prices -- it identifies WHICH contract to look up and provides the
reference-price-mode configuration. Actual price fetching is a feeds-layer
concern (ACT-16 / GAP-063).

### 7. Reference-price-mode loader

Reads `soy.kalshi.reference_price_mode` from commodities.yaml. Supported modes:
- `cbot_daily_settle` (default) -- use the CBOT daily settlement of the front-month ZS
- `cbot_vwap` -- use a custom VWAP window (future extension)
- `kalshi_snapshot` -- use the Kalshi reference snapshot (future extension)

Only `cbot_daily_settle` is fully implemented. Others raise NotImplementedError
with a clear message per fail-loud policy.

### 8. Integration with ACT-07

- Imports `_CBOT_HOLIDAYS`, `_is_cbot_trading_day`, `_HOLIDAY_RANGE_START`,
  `_HOLIDAY_RANGE_END` from `engine/event_calendar.py`.
- `settle_date_roll()` from ACT-07 is used for Friday-holiday adjustment on
  the Kalshi settlement date; this module handles the CBOT-side contract
  calendar which is a related but distinct concern.

### 9. Module location

`engine/cbot_settle.py` -- keeps CBOT-specific logic separate from the
general trading calendar.

### 10. Non-negotiables compliance

- No pandas
- Type hints on all public functions
- Fail-loud: ValueError on dates outside maintained range, on unknown
  reference-price modes, on unmapped contract months
- Not hot-path math, so no numba required
