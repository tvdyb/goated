# ACT-07 implementation plan

## Scope
- Gaps closed:
  - GAP-087: Register 24/7 KXSOYBEANW trading session (currently wrong: WTI calendar treats weekends as closed for a 24/7 product)
  - GAP-089: Add CBOT holiday set + Friday-holiday Rule 7.2(b) settlement roll logic
- Code locations to touch:
  - `engine/event_calendar.py:30-38, 76-79` — add soybean 24/7 session handler + holiday roll
- New modules to create: none (extend existing `engine/event_calendar.py`)
- Tests to add: extend `tests/test_trading_calendar.py`

## Approach

**24/7 session (GAP-087).** Kalshi's commodities hub trades 24/7 including weekends (C07-108, launched Apr 15 2026). For `KXSOYBEANW`, every second is a trading second. The soybean session handler is trivial: `trading_seconds(start, end) = (end - start).total_seconds()`. The annualization denominator is `365.25 * 24 * 3600` (all calendar seconds in a year). Register this as the `"soy"` commodity handler in `TradingCalendar.__init__`.

**Friday-holiday roll (GAP-089).** Per Rule 7.2(b) (C07-81), when the settlement Friday is a CBOT holiday, settlement rolls to the next CBOT trading day. Implementation:
1. Maintain a static set of known CBOT holidays (US federal holidays that fall on weekdays, plus Good Friday which CBOT observes). Use `datetime.date` objects.
2. Add a `settle_date_roll(nominal_date: date) -> date` function: if the nominal settlement date (a Friday) is a CBOT holiday, advance to the next weekday that is not a holiday.
3. The holiday set is finite and must be explicitly maintained — we load a list of known holidays and raise if asked about a date beyond the maintained range. This follows the fail-loud non-negotiable.

The 24/7 session and the holiday roll are orthogonal: the session determines how tau is computed (all seconds count), while the holiday roll adjusts the *settlement date* that tau targets.

## Dependencies on frozen interfaces
None — no frozen interface contracts exist yet in `state/interfaces/`.

## Risks
- Holiday list maintenance: requires annual update. Mitigated by raising on unmaintained date ranges.
- CBOT holiday calendar may shift. Mitigated by sourcing from official CME Group holiday schedule.

## Done-when
- [ ] `TradingCalendar` supports `"soy"` commodity with 24/7 session
- [ ] `tau_years("soy", ...)` returns calendar-time tau (all seconds count)
- [ ] `settle_date_roll()` rolls Friday holidays to next CBOT trading day
- [ ] CBOT holiday set covers 2026-2027 (minimum operational range)
- [ ] Tests pass for: 24/7 weekend trading, holiday roll, non-holiday passthrough, out-of-range raise
- [ ] No non-negotiable violations
