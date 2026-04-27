# Audit Phase B — `engine-calendar`

Cross-checked against `audit/audit_A_cartography.md:224`. The Phase A inventory
row for slug `engine-calendar` lists exactly one runtime file,
`engine/event_calendar.py`, at ~110 LoC. The file in scope matches; no
mismatch. The package itself is `engine/`, whose `engine/__init__.py` is a
zero-line marker (Phase A note at `audit/audit_A_cartography.md:209-211`),
i.e. the calendar module is reached only via the fully-qualified import
`engine.event_calendar`, not via package re-export.

---

## 1. Module identity

- **File**: `engine/event_calendar.py` (single-file module).
- **Total LoC**: 110 per Phase A; the file's last non-blank line is
  `engine/event_calendar.py:110` (`return commodity in self._handlers`).
- **One-paragraph summary**: A tiny, dependency-light module that converts
  `(commodity, now_ns, settle_ns)` triples into a trading-time τ in years.
  It owns three module-level constants — a fixed `America/New_York` ZoneInfo
  (`engine/event_calendar.py:25`), a 5,796-hour annual budget for WTI
  (`engine/event_calendar.py:26`), and a hand-rolled per-weekday WTI session
  table (`engine/event_calendar.py:30-38`) — plus two private helpers and
  one public class. The class, `TradingCalendar`, holds a per-commodity
  registry mapping a commodity name to a `(trading_seconds_fn,
  seconds_per_trading_year)` pair, and `tau_years` divides one by the
  other. As shipped, only `"wti"` is registered by default
  (`engine/event_calendar.py:76-79`); any other commodity triggers a
  `NotImplementedError` (`engine/event_calendar.py:97-100`). The module's
  premise, stated in its own docstring, is that calendar-time τ is biased
  for any market that closes overnight or weekends, and a biased τ biases
  every theo that consumes it (`engine/event_calendar.py:1-7`).

## 2. Responsibility

Inferred strictly from code behaviour, the module solves three tightly
coupled problems:

1. **Translate clock time to session time for τ.** A Kalshi-style theo
   needs the time-to-settle that the underlying actually trades for. The
   module exposes one public verb, `tau_years` (`engine/event_calendar.py:96-107`),
   that walks calendar days from `now_et` to `settle_et` and accumulates
   the seconds the market is actually open under that commodity's
   schedule. The conversion to years happens at line 107 by dividing the
   accumulated open seconds by the commodity's `seconds_per_trading_year`
   constant.
2. **Encode the WTI schedule explicitly.** The Sunday-evening-to-Friday-
   evening continuous electronic session, with a 17:00–18:00 ET daily
   maintenance halt on Mon–Thu, is hard-coded as a per-weekday window list
   at `engine/event_calendar.py:30-38`. The annual budget — 252 trading
   days × 23 hours × 3,600 seconds = 20,865,600 — is constant
   `_SECONDS_PER_TRADING_YEAR_WTI` at `engine/event_calendar.py:26`. The
   docstring spells out the same model in prose at
   `engine/event_calendar.py:13-17`.
3. **Refuse to fall back on calendar time.** The class registry mechanism
   (`engine/event_calendar.py:76-79, 96-100`) is positively defensive: if a
   commodity has no schedule registered, `tau_years` raises
   `NotImplementedError` rather than estimating τ in any way. The module
   docstring frames this explicitly: "If the calendar has no schedule for a
   commodity, `tau_years` raises rather than silently falling back to
   calendar time." (`engine/event_calendar.py:10-11`).

## 3. Public interface

The module has no `__all__`. Anything not prefixed with `_` is part of the
de facto public API. By that convention, the public surface is exactly:

- **`TradingCalendar`** — `engine/event_calendar.py:69-110`. A regular class
  (not a dataclass, not a singleton). Constructor takes no arguments and
  pre-populates `self._handlers` with a single entry for `"wti"`
  (`engine/event_calendar.py:76-79`). Mutable state is a `dict[str,
  tuple[Callable, float]]` keyed by commodity name.
- **`TradingCalendar.register_handler(commodity, trading_seconds_fn,
  seconds_per_trading_year) -> None`** — `engine/event_calendar.py:81-94`.
  Adds or replaces an entry. Validates that `seconds_per_trading_year >
  0.0` (`engine/event_calendar.py:90-93`) — this is the only argument
  validation; `commodity` and `trading_seconds_fn` are accepted as-is.
  The docstring states the intended callers: "later deliverables as
  brent/gold/copper/etc. calendars come online" plus the benchmarks book
  (`engine/event_calendar.py:87-89`).
- **`TradingCalendar.tau_years(commodity, now_ns, settle_ns) -> float`** —
  `engine/event_calendar.py:96-107`. The single hot-path entry point.
  Two early-exit branches (unsupported commodity at lines 97-100,
  non-positive interval at lines 101-102), then a fixed-shape conversion:
  `now_et = datetime.fromtimestamp(now_ns / 1e9, tz=_ET)` and the same for
  settle (lines 104-105), the registered counter call at line 106, and a
  scalar division at line 107. Returns a `float` ≥ 0.0.
- **`TradingCalendar.supports(commodity) -> bool`** — `engine/event_calendar.py:109-110`.
  Pure dictionary membership. **Not called from anywhere in the
  repository.** Confirmed by `grep` for `\.supports\(` returning zero
  matches.

The module additionally exposes three names that are nominally private (a
leading underscore declares intent under PEP 8) but are imported from
another module in the repo:

- `_ET = ZoneInfo("America/New_York")` — `engine/event_calendar.py:25`.
- `_SECONDS_PER_TRADING_YEAR_WTI` — `engine/event_calendar.py:26`. Imported
  by `benchmarks/harness.py:23`.
- `_wti_trading_seconds(start_et, end_et) -> float` —
  `engine/event_calendar.py:51-66`. Imported by
  `benchmarks/harness.py:23`.
- `_window_endpoints(day_et, w)` — `engine/event_calendar.py:41-48`. Internal
  to `_wti_trading_seconds`; not imported anywhere.

The cartography flagged the underscore-crossing import as red flag #4
(`audit/audit_A_cartography.md:250-253`).

## 4. Internal structure

The module is layered in three pieces, top-to-bottom:

**Constants and the schedule table.** `_ET` is a single `ZoneInfo`
instance (`engine/event_calendar.py:25`); every datetime the module
constructs is anchored to it. `_SECONDS_PER_TRADING_YEAR_WTI` is a literal
`252 * 23 * 3600` (`engine/event_calendar.py:26`). The schedule table is
`_WTI_WINDOWS: dict[int, list[tuple[int, int, int, int]]]`
(`engine/event_calendar.py:30-38`). Keys are weekday indices using
Python's `datetime.weekday()` convention (0=Mon … 6=Sun, called out
in the comment at line 29). Each value is a list of windows; each
window is `(start_hour, start_min, end_hour, end_min)`. The Mon–Thu
entries (lines 31-34) split each weekday into two windows separated by
the 17:00–18:00 ET halt. Friday (line 35) has only the morning/early-
evening session — closes at 17:00 ET, no evening reopen. Saturday
(line 36) is an empty list. Sunday (line 37) has only the evening
session, opening at 18:00 ET and running to midnight encoded as
`(18, 0, 24, 0)`.

**The two private helpers.** `_window_endpoints` at
`engine/event_calendar.py:41-48` resolves a window tuple against a calendar
day (`day_et`, expected to have hour/minute/second/microsecond all zero —
its sole caller normalizes that on line 55). The function specifically
encodes the "24:00 means midnight of next day" convention by branching on
`w[2] >= 24` (line 44) and constructing `day_et + timedelta(days=1)` at
midnight if so; otherwise it does a straight `replace(hour=w[2],
minute=w[3])` at line 47. Returns a `(start_et, end_et)` tuple of
tz-aware datetimes, both in ET.

`_wti_trading_seconds` at `engine/event_calendar.py:51-66` is the
accumulator. Bail-out: if `end_et <= start_et` it returns `0.0`
(line 52-53), so the function is well-defined for empty intervals. The
loop walks `day` forward from `start_et`'s midnight (line 55) one
calendar day at a time (`day = day + timedelta(days=1)` at line 65),
stopping the first day that is `>= stop` (line 58). For each day, it
iterates the windows for that weekday (line 59), resolves their
endpoints (line 60), clamps them to `[start_et, end_et)` via `lo =
max(win_start, start_et)` and `hi = min(win_end, stop)` (lines 61-62),
and adds `(hi - lo).total_seconds()` if `hi > lo` (lines 63-64). The
half-open convention is documented in the comment at line 56. The
result is a non-negative `float`.

**The `TradingCalendar` class.** A thin orchestration layer.
`__init__` (`engine/event_calendar.py:76-79`) takes no arguments and
populates `self._handlers` with a single seed entry binding `"wti"` to
the pair `(_wti_trading_seconds, _SECONDS_PER_TRADING_YEAR_WTI)`. The
shape `(callable, float)` is enforced only by the unpacking at
`engine/event_calendar.py:103` — no type guards. `register_handler`
(`engine/event_calendar.py:81-94`) is the only mutator; it validates
`seconds_per_trading_year > 0.0` (lines 90-93) and otherwise overwrites
without warning.

`tau_years` (`engine/event_calendar.py:96-107`) is the dispatch site:

1. Membership check on `self._handlers` (line 97-100).
2. Non-positive interval guard (line 101-102) — note this fires even when
   `settle_ns == now_ns`, returning `0.0` rather than raising.
3. Pair lookup (line 103).
4. Float-second epoch → tz-aware datetime conversion (lines 104-105) using
   `datetime.fromtimestamp(ns / 1e9, tz=_ET)`. Float division by 1e9 is
   the only place ns precision is lost; downstream resolution is
   microseconds.
5. Counter call (line 106) and division (line 107).

Data flow within the module on the hot path: `tau_years → _wti_trading_seconds →
(loop over days) → _window_endpoints → datetime arithmetic → total seconds
→ /seconds_per_trading_year`. Every state read is local; nothing is
cached across calls.

## 5. Dependencies inbound

`Grep` for `event_calendar`, `TradingCalendar`, `tau_years`,
`_wti_trading_seconds`, `_SECONDS_PER_TRADING_YEAR_WTI` resolves to four
import sites:

- **`engine/pricer.py:22`** — `from engine.event_calendar import
  TradingCalendar`. The `Pricer` dataclass declares
  `calendar: TradingCalendar` at `engine/pricer.py:42`. The single
  invocation is `tau = self.calendar.tau_years(commodity, now_ns,
  settle_ns)` at `engine/pricer.py:73`. The pricer immediately follows
  with its own non-positive-τ guard at `engine/pricer.py:74-75`, raising
  `ValueError` — meaning the calendar's `0.0` early return at
  `engine/event_calendar.py:101-102` is never observed by the pricer's
  caller; it is converted to a `ValueError` upstream. (Cross-check:
  `audit/audit_B_engine-pricer.md:281-283, 472-474` already documents the
  overlap.)
- **`benchmarks/harness.py:23`** — `from engine.event_calendar import
  TradingCalendar, _SECONDS_PER_TRADING_YEAR_WTI, _wti_trading_seconds`.
  The harness imports both the public class and the two private
  symbols, crossing the underscore boundary. The harness instantiates a
  `TradingCalendar` at `benchmarks/harness.py:78` and then loops over
  every synthetic commodity calling
  `calendar.register_handler(c, _wti_trading_seconds,
  _SECONDS_PER_TRADING_YEAR_WTI)` at `benchmarks/harness.py:93` — i.e.
  every benchmark commodity is given the WTI session verbatim. This is
  what the harness docstring at `benchmarks/harness.py:1-7` calls "all
  share WTI's trading-session schedule".
- **`tests/test_trading_calendar.py:10`** — `from engine.event_calendar
  import TradingCalendar`. The test file constructs a fresh
  `TradingCalendar` per test (lines 20, 28, 38, 46, 51) and exercises
  `tau_years` directly. No private symbol use.
- **`tests/test_end_to_end.py:17`** — `from engine.event_calendar import
  TradingCalendar`. Used in `_build_pricer` at lines 32-48 to wire a
  pricer for the happy-path test, and in `test_end_to_end_wti_matches_bs_analytical`
  at lines 66-87 where `calendar.tau_years("wti", now_ns, settle_ns)` is
  called once at line 82 to obtain the τ that the BS reference is then
  computed against.

No other call sites. `Grep` finds no reference in `feeds/`, `state/`,
`models/`, `validation/`, `engine/scheduler.py`, or any of the
`research/` documents. The string `EVENT_CAL` appears at
`engine/scheduler.py:25` (a `Priority` enum value), but that is only
nominal — the scheduler imports nothing from `engine.event_calendar`
and is itself unused per Phase A red flag #5
(`audit/audit_A_cartography.md:254-257`).

## 6. Dependencies outbound

The module imports only:

- `from __future__ import annotations` (`engine/event_calendar.py:20`).
- `from datetime import datetime, timedelta` (`engine/event_calendar.py:22`).
- `from zoneinfo import ZoneInfo` (`engine/event_calendar.py:23`).

No third-party imports. No imports from `numpy`, `numba`, `pyyaml`,
`scipy`, or any of the other `pyproject.toml:9-20` dependencies. No
imports from any other intra-repo module. The cartography table column
"External Deps" already shows this: `stdlib datetime, zoneinfo`
(`audit/audit_A_cartography.md:224`).

The module also does **not** read from `config/commodities.yaml`. The
YAML has a `trading_hours` block with `session: "sun_17_fri_17_et"` and
`hours_per_day: 23.0` for WTI (`config/commodities.yaml:19-23`) and an
`event_calendar` list with one entry for the EIA crude release
(`config/commodities.yaml:24-29`). A repo-wide grep for
`trading_hours|event_calendar|hours_per_day|session` in `*.py` shows
no Python reader; the YAML's only consumer is `models/registry.py`,
which does not touch those keys (the only field the registry validates
is `model`, with `stub: true` as a bypass). The YAML comment at
`config/commodities.yaml:21` explicitly notes the approximation lives
"in `engine/event_calendar.py`", confirming the YAML is human-readable
documentation rather than a config source for this module.

## 7. State and side effects

- **In-process state.** A single `dict`, `self._handlers`, owned per
  `TradingCalendar` instance (`engine/event_calendar.py:77-79`). Mutated
  only by `__init__` (seed) and `register_handler` (overwrite). Nothing
  in the module synchronises access; there is no lock, no `asyncio.Lock`,
  no thread-local. A `_handlers` write concurrent with a `tau_years`
  read would be a data race; the code is implicitly single-threaded.
- **Module-level state.** `_ET`, `_SECONDS_PER_TRADING_YEAR_WTI`, and
  `_WTI_WINDOWS` (`engine/event_calendar.py:25, 26, 30-38`) are
  effectively immutable globals — created once at import time, never
  reassigned, never mutated. `_WTI_WINDOWS` is a mutable `dict` despite
  its data-class-of-tuples shape; nothing in the module mutates it after
  import.
- **Disk I/O.** None. The module never opens a file.
- **Network I/O.** None.
- **Global mutation.** None outside the per-instance `_handlers` dict.
- **Ordering assumptions.** The constructor seeds `"wti"` before any
  caller can invoke `register_handler` or `tau_years`, so the seed is
  visible to the first call. Beyond that, calls to `register_handler`
  must precede the first `tau_years` call for that commodity, but the
  module enforces this only by raising `NotImplementedError` if the
  caller misorders (`engine/event_calendar.py:97-100`).

## 8. Invariants

Each invariant below is what the code, as written, appears to rely on,
with the citation that demonstrates the reliance.

- **Inputs are nanosecond integers from the Unix epoch.** `tau_years`
  treats `now_ns` and `settle_ns` as integers and divides by `1e9` to
  get fractional seconds before passing to `datetime.fromtimestamp`
  (`engine/event_calendar.py:104-105`). No type assertion. A fractional
  input would silently work; a non-numeric input would raise downstream.
- **Inputs in the same epoch frame.** The non-positive guard
  `if settle_ns <= now_ns` at `engine/event_calendar.py:101-102` makes
  sense only if the two are comparable on the same monotonically-
  increasing axis. The pricer feeds both from the same `time.time_ns()`
  source via `engine/pricer.py:53, 73`.
- **`now_ns / 1e9` fits a Python float.** Implicit in line 104. Float64
  has 53 bits of mantissa, so any current-era ns timestamp fits, but the
  conversion erodes resolution to ~µs.
- **`day = day + timedelta(days=1)` advances exactly one calendar day in
  ET.** Line 65 walks day-by-day in tz-aware datetimes. Adding a
  `timedelta` to a `ZoneInfo`-aware datetime advances UTC seconds; the
  resulting wall-clock ET hour can shift by ±1 across DST transitions.
  The code does not use `fold=` and does not normalise after the add.
  This is a behavioural detail, not an explicit assumption — flagged
  here as a fact for later phases.
- **`_WTI_WINDOWS` keys cover every weekday 0–6.** The lookup
  `_WTI_WINDOWS[day.weekday()]` at line 59 is a raw `dict` index; a
  missing key would `KeyError`. Lines 30-38 list keys 0 through 6
  inclusive.
- **A registered `trading_seconds_fn` returns a non-negative float.**
  `tau_years` divides directly without clamping (line 107).
  `_wti_trading_seconds` itself is non-negative by construction (the
  `hi > lo` guard at line 63 admits only positive contributions; the
  `end_et <= start_et` early return at lines 52-53 zeros the empty case).
- **`seconds_per_trading_year > 0.0`.** Enforced at registration in
  `register_handler` (`engine/event_calendar.py:90-93`); the seed
  constant is `252 * 23 * 3600 = 20_865_600 > 0`
  (`engine/event_calendar.py:26, 78`). Note that `NaN <= 0.0` is `False`,
  so a NaN denominator would slip past the validation; division at line
  107 would then yield NaN.
- **Day-loop windows for a single weekday do not overlap.** Lines 31-38
  encode disjoint windows per weekday; the accumulator at lines 59-64 sums
  them without dedup, so overlapping windows would double-count.
- **`day` initialisation (`start_et.replace(hour=0, …)`) at line 55
  always produces an existing ET datetime.** Midnight ET on a DST
  spring-forward day is 00:00 ET, which exists; the code does not pass
  `fold`. This is implicit.
- **Subsequent `day_et.replace(hour=…)` calls in `_window_endpoints`
  produce existing ET datetimes.** The session boundaries used (00:00,
  17:00, 18:00, 24:00) are all outside the US DST transition windows
  (which fire at 02:00 ET), so this is not exercised in practice — but
  the code does not document the assumption.

## 9. Error handling

The module raises in three places, all from `TradingCalendar`:

- **`NotImplementedError`** at `engine/event_calendar.py:98-100` when
  `commodity` is not a registered key. Message is
  `f"{commodity}: trading calendar not yet implemented"`. The pricer
  does not catch it, so it propagates to the pricer's caller verbatim.
- **`ValueError`** at `engine/event_calendar.py:91-93` when
  `register_handler` is called with `seconds_per_trading_year <= 0.0`.
  Message is
  `f"{commodity}: seconds_per_trading_year must be > 0, got {…}"`.
  Only caller in the repo is `benchmarks/harness.py:93`, which always
  passes the WTI constant, so this raise is unreachable at rest.
- **`KeyError`** is implicit: a `_handlers[commodity]` lookup at
  `engine/event_calendar.py:103` happens after the membership check on
  line 97, so it is unreachable on the public path. A misuse of
  `_WTI_WINDOWS[day.weekday()]` at line 59 with a non-0..6 key would
  also `KeyError`, but `datetime.weekday()` only returns 0–6.

There is **no** `try` / `except` anywhere in the file. Errors from
`zoneinfo.ZoneInfo("America/New_York")` (e.g. on a system without the
tz database) would surface at import time. Errors from
`datetime.fromtimestamp` (e.g. an out-of-range epoch ns) would surface
inside `tau_years` and propagate. The module's policy, consistent with
the docstring at `engine/event_calendar.py:1-11` and with the rest of
the engine (compare `engine/pricer.py:1-13`'s "wrong theo trades; a
missing theo doesn't"), is that gaps raise rather than fall back.

## 10. Test coverage

Direct tests live in `tests/test_trading_calendar.py` (53 lines). Five
cases:

- `test_weekend_contributes_zero_hours` (`tests/test_trading_calendar.py:19-24`)
  — Friday 18:00 ET → Sunday 17:30 ET, asserts τ == 0.0. Exercises both
  the Friday post-close and Sunday pre-open empty regions plus the
  empty Saturday list (`engine/event_calendar.py:35-37`).
- `test_full_weekday_counts_23_hours` (`tests/test_trading_calendar.py:27-34`)
  — Monday 00:00 ET → Tuesday 00:00 ET, expected
  `23.0 * 3600.0 / (252 * 23 * 3600)` to relative-tolerance `1e-12`.
  Exercises both Monday windows plus the day-rollover into Tuesday's
  midnight (line 36-37 logic in `_window_endpoints`).
- `test_daily_halt_removed` (`tests/test_trading_calendar.py:37-42`) —
  Monday 17:00–18:00 ET, asserts τ == 0.0. Exercises the halt gap
  between the two Mon windows.
- `test_settle_before_now_is_zero` (`tests/test_trading_calendar.py:45-47`)
  — `tau_years("wti", 2e18, 1e18)`, asserts 0.0. Hits the
  `settle_ns <= now_ns` early return at line 101-102.
- `test_unsupported_commodity_raises` (`tests/test_trading_calendar.py:50-53`)
  — `tau_years("brent", 1e18, 2e18)`, expects `NotImplementedError`.
  Hits line 97-100.

Indirect coverage in `tests/test_end_to_end.py`:

- `test_end_to_end_wti_matches_bs_analytical` at lines 66-87 calls
  `calendar.tau_years("wti", now_ns, settle_ns)` once at line 82 with a
  Mon 12:00 → Mon 14:00 interval (line 70-71), entirely inside the
  morning window. The result feeds directly into the BS reference at
  line 83, so any error in the τ for that interval would surface as a
  pricing mismatch. The test asserts `np.testing.assert_allclose(...,
  atol=1e-9)` at line 84.
- `test_stub_commodity_refuses_to_price` at lines 150-163 wires the pricer
  for `"brent"` and expects either `NotImplementedError` (from the
  calendar at `engine/event_calendar.py:97-100`) or `KeyError` (from the
  registry). The comment at lines 159-160 names both possibilities.

What is **not** tested:

- The DST-boundary behaviour of the day-walk (no test case crosses
  March-spring-forward or November-fall-back).
- The `register_handler` validation path (no test sends
  `seconds_per_trading_year <= 0`).
- The `supports` method (zero references in any test).
- Any commodity besides `"wti"` and `"brent"` (`"brent"` is asserted to
  raise; the rest go untouched).
- Multi-day intervals that include a weekend boundary. The closest
  case is `test_weekend_contributes_zero_hours`, but its endpoints are
  on the same closed segment.
- Intervals that span a settle exactly on a window boundary (e.g.
  17:00:00.000 ET).
- The benchmark harness path that registers the WTI calendar against
  many synthetic commodities; `benchmarks/harness.py:93` is exercised
  only when benchmarks are run, not under `pytest`.

Mocks: none. All tests use real `TradingCalendar` instances and real
`zoneinfo.ZoneInfo("America/New_York")` lookups.

## 11. TODOs, bugs, and smells

Literal `TODO` / `FIXME` / `XXX` markers in the file: **none**. `Grep`
for `TODO|FIXME|XXX|HACK|NOTE` in `engine/event_calendar.py` returns no
matches.

Structural observations, each cited:

- **Hard-coded WTI windows live at module scope, not behind config.**
  `_WTI_WINDOWS` is declared at `engine/event_calendar.py:30-38` and
  referenced inside the file-private `_wti_trading_seconds` at line 59.
  The companion `config/commodities.yaml:19-29` has `trading_hours` and
  `event_calendar` blocks that no Python code reads. Cartography
  flagged the same divergence as red flag #14
  (`audit/audit_A_cartography.md:297-301`).
- **Underscore-prefixed symbols imported across module boundaries.**
  `benchmarks/harness.py:23` pulls `_SECONDS_PER_TRADING_YEAR_WTI` and
  `_wti_trading_seconds` directly. The leading underscore declares them
  as module-private; the harness ignores that convention to recycle
  WTI's table for synthetic benchmark commodities at lines 88-93.
  Cartography flagged this as red flag #4
  (`audit/audit_A_cartography.md:250-253`).
- **Default registration is a single-line literal that pretends to be a
  registry.** `engine/event_calendar.py:76-79` populates `self._handlers`
  inline; there is no separate "default schedules" table. Adding a
  second commodity requires either editing the `__init__` or relying on
  callers to invoke `register_handler` after construction — and the
  module has no enforcement that they do.
- **Calendar-time fall-back-by-bug is structurally avoided but not
  documented.** Compare the docstring at `engine/event_calendar.py:10-11`
  ("raises rather than silently falling back to calendar time") with the
  raise at `engine/event_calendar.py:97-100`. They line up; the smell
  is that the module's *only* defence is the membership check — there
  is no per-commodity asserts, no second guard.
- **`supports` is dead code by call-graph.** Defined at lines 109-110,
  zero callers across the repo. Could be a planned dispatch helper or
  an unused convenience.
- **`tau_years` returns 0.0 for `settle_ns == now_ns`.** Line 101 reads
  `if settle_ns <= now_ns`. The pricer immediately rejects τ ≤ 0
  (`engine/pricer.py:74-75`), so the calendar's zero is reinterpreted
  as a `ValueError`. Two layers redundantly enforce the same boundary
  — see `audit/audit_B_engine-pricer.md:281-283`.
- **`NaN` denominator slips past `register_handler` validation.** Line
  90's `if seconds_per_trading_year <= 0.0` evaluates `False` for NaN,
  so a NaN would be admitted. Division at line 107 would propagate the
  NaN downstream. The pricer's only check is `tau <= 0.0` at
  `engine/pricer.py:74`, which is `False` for NaN as well. No test
  covers this path.
- **Day-by-day Python loop on the hot path.** `_wti_trading_seconds` at
  `engine/event_calendar.py:51-66` builds new `datetime` objects per
  window per day. For a 2-hour intra-session τ this is one iteration;
  for a multi-week τ it scales linearly with calendar days. The pricer
  invokes this once per `reprice_market` (`engine/pricer.py:73`). No
  caching across calls.

## 12. Open questions

Questions a maintainer would have to answer; the code does not.

1. **Why is the WTI annual budget 252 × 23 hours rather than the
   nominal 252 × 24?** `engine/event_calendar.py:26` uses 23, and the
   docstring at line 17 confirms "5796 trading hours per year (252 ×
   23 h/day)". The 23-hour figure assumes exactly one hour of halt per
   trading day; whether that aligns with CME's published session model
   for WTI (and whether the Friday-no-evening reduction should adjust
   the divisor) is not derivable from the file.
2. **Are 252 trading days the intended divisor for a session that runs
   five days a week including Sunday-evening?** The literal at line 26
   uses 252; whether Sunday's three-hour partial session counts toward
   that 252 or is folded into Monday is not stated.
3. **Is DST handling intentionally elided, or simply not yet
   exercised?** The day-walk at `engine/event_calendar.py:65` uses
   `timedelta(days=1)`, which advances UTC seconds, not wall-clock days.
   Since session boundaries (17:00/18:00 ET) sit far from the 02:00 ET
   DST jump, there's no behavioural defect at WTI's current schedule;
   the question is whether that is by design.
4. **What was `supports` intended to gate?** Defined at
   `engine/event_calendar.py:109-110`, never called. Could be an early-
   exit hook for an as-yet-unwritten dispatcher; could be a refactor
   leftover.
5. **Is the YAML `trading_hours` / `event_calendar` block at
   `config/commodities.yaml:19-29` meant to feed this module?** A reader
   would need to know whether the eventual plan is to lift the table
   out of `_WTI_WINDOWS` into config, or vice versa. The YAML's
   comment at line 21 referencing this file suggests the YAML is the
   intended source-of-truth; the code does not read it.
6. **What is the contract for `trading_seconds_fn` arguments?**
   `register_handler` accepts any callable (`engine/event_calendar.py:81-94`)
   without typed signature. The seed entry expects `(datetime, datetime)
   → float`. Whether benchmark callers may register a Numba-compiled
   function operating on epoch ns directly is not stated; the only
   existing caller (`benchmarks/harness.py:93`) re-uses the WTI
   `(datetime, datetime) → float` shape.
7. **Why is the `Sun: (18, 0, 24, 0)` window expressed with `24`
   instead of as two same-day windows?** `_window_endpoints` line 44
   special-cases `w[2] >= 24` to roll into the next day at midnight.
   A Sunday window ending at midnight is by construction equivalent to
   `(18, 0, 23, 59, 59.999…)` plus a Monday `(0, 0, 0, 0)` no-op; the
   24-hour encoding presumably exists to keep "session ends at the
   day boundary" expressible. But Monday's first window is
   `(0, 0, 17, 0)` which already covers the immediate post-midnight
   span, so the Sunday `24` and the Monday `0` adjoin without overlap
   at the half-open boundary 00:00 — a reader would have to convince
   themselves of that.
8. **Is the `register_handler` overwrite-without-warning intentional?**
   Line 94 unconditionally writes to `self._handlers[commodity]`. A
   benchmark could register `"wti"` and silently shadow the seed entry
   from `__init__`. No test exercises this.

---

End of Phase B for `engine-calendar`.
