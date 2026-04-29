# ACT-07 handoff

**Status.** complete

**Files written or edited.**
| Path | Lines added | Lines removed | Purpose |
|---|---|---|---|
| engine/event_calendar.py | ~75 | 0 | 24/7 soy session handler, CBOT holiday set (2026-2027), settle_date_roll() |
| tests/test_trading_calendar.py | ~95 | 3 | 19 new tests for soy 24/7 + settlement roll; updated imports/docstring |

**Tests added.**
| Path | Test count | Pass | Fail |
|---|---|---|---|
| tests/test_trading_calendar.py | 24 (5 existing + 19 new) | 24 | 0 |

**Gaps closed (with rationale).**
- GAP-087: `_soy_trading_seconds()` registered in `TradingCalendar.__init__` as `"soy"` handler. Returns pure calendar-time delta (every second counts as trading time). Annualized with `365.25 * 24 * 3600`. Tests confirm weekend hours count, full week matches 168h, and soy diverges from WTI on weekends.
- GAP-089: `settle_date_roll(nominal: date) -> date` implements Rule 7.2(b). Maintains a `_CBOT_HOLIDAYS` frozenset covering 2026-2027 (10 holidays per year). Rolls forward past weekends and holidays. Raises `ValueError` on dates outside the maintained range (fail-loud). Tests cover: Good Friday, Juneteenth, Independence Day observed, Christmas, New Year's, MLK Monday, weekend rollover, out-of-range.

**Frozen interfaces honoured.** None applicable (no frozen contracts exist yet).

**New interfaces emitted.** None. The `settle_date_roll` function is a public export from `engine/event_calendar.py` — downstream consumers (ACT-08 settle resolver, ACT-18 USDA event clock) can import it directly.

**Decisions encountered and resolved.** None.

**Decisions encountered and deferred.** None.

**Open issues for verifier.**
- Holiday set covers 2026-2027 only. Beyond 2027, callers get a `ValueError`. This is by design (fail-loud) and should be extended annually. Verifier should confirm this is acceptable for the operational window.
- The `"soy"` commodity key matches the existing `config/commodities.yaml` entry. ACT-02 (soy yaml fill-in) will populate the full config; this action only registers the session handler.

**Done-when checklist.**
- [x] `TradingCalendar` supports `"soy"` commodity with 24/7 session
- [x] `tau_years("soy", ...)` returns calendar-time tau (all seconds count)
- [x] `settle_date_roll()` rolls Friday holidays to next CBOT trading day
- [x] CBOT holiday set covers 2026-2027 (minimum operational range)
- [x] Tests pass for: 24/7 weekend trading, holiday roll, non-holiday passthrough, out-of-range raise
- [x] No non-negotiable violations
