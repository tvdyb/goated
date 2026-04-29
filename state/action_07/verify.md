# Verify pass 1 — 2026-04-27

**Verifier verdict.** PASS

**Gaps verified closed.**
| GAP-id | Closed? | Evidence | Notes |
|---|---|---|---|
| GAP-087 (wrong: 24/7 calendar not registered) | Yes | `_soy_trading_seconds()` at engine/event_calendar.py:84-88; registered as `"soy"` handler in `TradingCalendar.__init__` line 164 with `_SECONDS_PER_CALENDAR_YEAR = 365.25 * 24 * 3600`. Regression test `test_soy_wti_weekend_divergence` exercises the previously-wrong path (WTI=0, soy>0 on weekend). | Closure standard for 'wrong' gap met: correct behaviour + regression test. |
| GAP-089 (missing: Friday-holiday roll) | Yes | `settle_date_roll()` at engine/event_calendar.py:136-151; `_CBOT_HOLIDAYS` frozenset at lines 101-124 covering 2026-2027 (10 holidays/year, all day-of-week values verified correct). Fail-loud `ValueError` on out-of-range at lines 142-147. 13 tests exercise holiday roll, passthrough, weekend roll, and out-of-range raise. | Closure standard for 'missing' gap met. |

**Code locations verified touched.**
| Path:lines | Touched? | Notes |
|---|---|---|
| engine/event_calendar.py:30-38, 76-79 (gap register cite) | Yes | File has +88 lines uncommitted diff vs HEAD. Lines 80-197 are new ACT-07 code (soy handler, CBOT holidays, settle_date_roll, updated TradingCalendar.__init__). Note: changes are uncommitted — no dedicated ACT-07 commit exists yet. This is acceptable as the code is present and functional. |
| tests/test_trading_calendar.py | Yes | +123 lines uncommitted diff vs HEAD. 19 new tests covering both gaps. |

**Non-negotiable checks.**
| Check | Pass/Fail | Findings |
|---|---|---|
| No `import pandas` in engine/ | Pass | No hits in engine/event_calendar.py |
| No `scipy.stats.norm.cdf` | Pass | No hits in engine/event_calendar.py |
| No bare `except:` or swallowed `except Exception:` | Pass | No hits in engine/event_calendar.py |
| No default-fallback `return 0` on missing fields | Pass | No silent defaults; `ValueError` raised on out-of-range, `NotImplementedError` on unknown commodity |
| numba.njit on tight loops | N/A | Calendar math is not hot-path pricing; `settle_date_roll` is called once per settlement cycle, not per tick. No njit needed. |
| Fail-loud pattern | Pass | `settle_date_roll` raises `ValueError` with descriptive message on dates outside [2026-01-01, 2027-12-31]. `tau_years` raises `NotImplementedError` on unregistered commodity. |

**Test results.**
- Total: 24
- Pass: 24
- Fail: 0
- Skip: 0
- Coverage of gap closures: GAP-087 covered by TestSoy247 (6 tests: registration, weekend full, full week, 1-hour Saturday, settle-before-now, WTI divergence). GAP-089 covered by TestSettleDateRoll (13 tests: non-holiday passthrough, Good Friday 2026/2027, Juneteenth, Independence Day observed, Christmas 2026/2027, New Year's 2027, weekday passthrough, Saturday/Sunday roll, Monday holiday roll, out-of-range raise).

**Interface contracts.**
| Contract | Honoured? | Notes |
|---|---|---|
| (none applicable) | N/A | No frozen interface contracts exist yet in state/interfaces/. |

**Handoff completeness.**
All required sections per 02_ACTION_IMPLEMENT.md template are present in handoff.md: Status, Files written or edited, Tests added, Gaps closed (with rationale), Frozen interfaces honoured, New interfaces emitted, Decisions encountered and resolved, Decisions encountered and deferred, Open issues for verifier, Done-when checklist (all items checked).

**Findings (FAIL items only).**
- None.

**Observation (non-blocking).**
- Changes to engine/event_calendar.py and tests/test_trading_calendar.py are uncommitted (no ACT-07-specific commit in git log). The implementer should commit these changes. This does not block verification as the code is present and all tests pass.

**Recommendation.**
- PASS: action is verified-complete. Update state/dependency_graph.md to flip ACT-07 to `verified-complete`. ACT-18 (USDA event clock, depends on ACT-07) now has its sole dependency met.
