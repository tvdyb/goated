# Audit Phase B — `state-market-surfaces`

Cross-checked against `audit/audit_A_cartography.md:217`. The Phase A
inventory row for slug `state-market-surfaces` lists exactly two files,
`state/iv_surface.py` and `state/basis.py`, at ~96 LoC. Both files exist;
the actual line counts are 49 + 49 = 98 lines, which matches the "approx
LoC" in the cartography within rounding. `state/errors.py` is touched by
both files via import but is owned by a separate slug (`state-errors`,
`audit/audit_A_cartography.md:218`) and is therefore reviewed only as an
outbound dependency here, not as an in-module file.

---

## 1. Module identity

- **Files**: `state/iv_surface.py`, `state/basis.py`. The package marker
  `state/__init__.py` is a 0-byte file (the `Read` tool reports the file
  is "shorter than the provided offset (1)" when reading from line 1) and
  is not part of the audit surface.
- **Total LoC**: 98. `state/iv_surface.py` ends at line 49 (`return sigma`)
  with no trailing newline that adds a counted line; `state/basis.py`
  similarly ends at line 49 (`return drift`).
- **Summary**: Two near-identical scalar caches that map a commodity name
  to a `(value, last_update_ts_ns)` pair, with a per-instance staleness
  budget and three failure modes — invalid input, never-primed
  commodity, primed-but-stale commodity. Each class is one constructor,
  one setter, and one reader, with the entire body of meaningful logic
  living inside the reader's two-branch staleness check
  (`state/iv_surface.py:37-48`, `state/basis.py:37-48`). Neither file
  performs any I/O, holds any process-wide state, or imports anything
  beyond `math` and `state.errors`. The module's role on the hot path is
  to be the place where "do we have a usable σ / basis_drift right now?"
  is decided, and the place where "no, and here's why" is raised.

## 2. Responsibility

Inferred from code, the module owns three concerns:

1. **Hold the most recently observed scalar value of σ (annualized ATM
   implied vol) and basis drift (annualized Pyth↔CME drift), per
   commodity.** The storage is a Python `dict[str, tuple[float, int]]`
   inside each instance (`state/iv_surface.py:27`, `state/basis.py:25`).
   There is no history, no interpolation grid, no quantile, and no
   per-strike or per-expiry slicing — just one float and one nanosecond
   timestamp per (commodity, surface) pair.
2. **Enforce a per-instance freshness budget.** The constructors take a
   single positive integer `max_staleness_ms`
   (`state/iv_surface.py:24-28`, `state/basis.py:22-26`); the readers
   compute `(now_ns - ts_ns) / 1e6` and raise `StaleDataError` if that
   exceeds the budget (`state/iv_surface.py:42-47`,
   `state/basis.py:42-47`). The budget is a property of the surface
   instance, not of the commodity — there is no per-commodity override.
3. **Refuse to fall back.** The contract is spelled out in the
   `IVSurface` docstring at `state/iv_surface.py:8-11`: "Raises
   `MissingStateError` if no IV has been primed; raises `StaleDataError`
   if the last prime is older than `max_staleness_ms`. Never returns a
   fallback." The `BasisModel` docstring (`state/basis.py:1-10`) does
   not state this rule explicitly, but the implementation mirrors
   `IVSurface` exactly: there is no `or default`, no `try / except`, no
   silent zero. Combined with `README.md:63` ("No silent failures:
   stale Pyth publishers, out-of-bounds IV, feed dropouts → raise,
   don't publish") the policy is consistent across the module and the
   project rule.

The two docstrings (`state/iv_surface.py:1-12`, `state/basis.py:1-10`)
also frame the present implementation as deliberately minimal — both
explicitly call themselves a "Deliverable 1" placeholder for richer
later versions ("(strike, expiry) grid interpolated from CME options
chains" / "AR(1)-fit model specified in calibration/"), with the public
interface designed so the upgrade is "additive". That intent is asserted
in the comments only; it is not enforced in code, and there is no
version-flag or feature-flag plumbing that would make the upgrade
literal.

## 3. Public interface

There is no `__all__` and no re-export from `state/__init__.py` (which
is empty, see §1). Anything not prefixed with `_` is therefore public.
The full surface, in declaration order:

- **`IVSurface`** — `state/iv_surface.py:21-48`. A class declared with
  `__slots__ = ("_atm", "_max_staleness_ms")` (`state/iv_surface.py:22`),
  which means instances expose exactly those two attributes and no
  `__dict__`. No metaclass, no inheritance, no `__init_subclass__`.
- **`IVSurface.__init__(self, max_staleness_ms: int = 60_000) -> None`** —
  `state/iv_surface.py:24-28`. Validates `max_staleness_ms > 0`
  (line 25-26) and stores both fields. Default budget is 60 seconds.
- **`IVSurface.set_atm(self, commodity: str, sigma: float, ts_ns: int) -> None`** —
  `state/iv_surface.py:30-35`. Validates `sigma` is finite and > 0
  (line 31-32) and `ts_ns > 0` (line 33-34). Overwrites any prior entry
  for `commodity`. No upper bound on sigma; no normalization (e.g. no
  rejection of `sigma > 5.0`).
- **`IVSurface.atm(self, commodity: str, *, now_ns: int) -> float`** —
  `state/iv_surface.py:37-48`. Keyword-only `now_ns`. Returns the stored
  σ if present and fresh; raises `MissingStateError` if the commodity
  has never been `set_atm`'d, `StaleDataError` if the stored timestamp
  is older than the budget.
- **`BasisModel`** — `state/basis.py:19-48`. Same slot pattern:
  `__slots__ = ("_basis", "_max_staleness_ms")` (`state/basis.py:20`).
- **`BasisModel.__init__(self, max_staleness_ms: int = 30_000) -> None`** —
  `state/basis.py:22-26`. Same validation as `IVSurface`. **Default
  budget is 30 seconds**, half of `IVSurface`'s 60 s default — see §8
  for invariant ambiguity, §12 for the open question.
- **`BasisModel.set(self, commodity: str, basis_drift_annualized: float, ts_ns: int) -> None`** —
  `state/basis.py:28-35`. Validates `basis_drift_annualized` is finite
  (line 29-32) — note the absence of any sign or magnitude bound,
  which differs from `IVSurface.set_atm` (which requires `> 0`). Also
  validates `ts_ns > 0` (line 33-34).
- **`BasisModel.get(self, commodity: str, *, now_ns: int) -> float`** —
  `state/basis.py:37-48`. Same shape and behavior as `IVSurface.atm`,
  with the message strings adjusted ("ATM IV" → "basis").

The naming asymmetry (`set_atm` / `atm` versus `set` / `get`) is the
only externally visible difference between the two readers besides the
default staleness and the input-validation rule. Both readers take
`now_ns` keyword-only — callers cannot accidentally pass it positionally.

## 4. Internal structure

The two classes are structurally identical and can be described once.
The internal state is a Python dict keyed by commodity string, with
values being `(float_value, int_ns_timestamp)` tuples
(`state/iv_surface.py:27`, `state/basis.py:25`). The setter overwrites
unconditionally (`state/iv_surface.py:35`, `state/basis.py:35`); the
reader does a single dict lookup
(`state/iv_surface.py:38`, `state/basis.py:38`), unpacks the tuple, and
runs an arithmetic comparison.

The staleness arithmetic is identical in both files
(`state/iv_surface.py:42`, `state/basis.py:42`):

    staleness_ms = (now_ns - ts_ns) / 1e6

The result is a Python `float` (because `1e6` is a float literal); the
comparison on the next line (`> self._max_staleness_ms`) coerces the
budget int to float. There is no rounding or `int()` cast before
comparison. The check is strict-greater, so a value that is exactly
`max_staleness_ms` old (down to the float epsilon) is still returned;
the boundary itself is included in "fresh".

Notable design choices visible in the code:

- **`__slots__`** on both classes (`state/iv_surface.py:22`,
  `state/basis.py:20`) prevent attribute monkey-patching and shave per-
  instance memory. There are only two attributes per instance, so the
  saving is small in absolute terms; the more interesting effect is
  that `iv.foo = 1` would raise.
- **`from __future__ import annotations`** (`state/iv_surface.py:14`,
  `state/basis.py:12`) defers evaluation of annotations, which means
  the `dict[str, tuple[float, int]]` syntax in the `__init__` bodies
  works on Python 3.10 — though `pyproject.toml:48` (`target-version =
  "py311"`) makes that moot.
- **Keyword-only `now_ns`** on both readers
  (`state/iv_surface.py:37`, `state/basis.py:37`). The `*` separator
  forces callers to write `now_ns=…`, which is the convention used at
  every call site (`engine/pricer.py:71-72`,
  `tests/test_end_to_end.py` calls all go through the pricer).

There are no helper functions, no module-level state, no decorators,
and no class methods or static methods. Each file is one class, three
methods. The two classes do not share an inheritance base — the
duplication is literal copy-paste at the source level.

## 5. Dependencies inbound

A `Grep` for `from state.iv_surface` and `from state.basis` across the
repo (filtered to `*.py`) yields exactly six lines, in three files:

- `engine/pricer.py:25` `from state.basis import BasisModel`
- `engine/pricer.py:27` `from state.iv_surface import IVSurface`
- `benchmarks/harness.py:27` `from state.basis import BasisModel`
- `benchmarks/harness.py:28` `from state.iv_surface import IVSurface`
- `tests/test_end_to_end.py:21` `from state.basis import BasisModel`
- `tests/test_end_to_end.py:23` `from state.iv_surface import IVSurface`

Concrete call-site behavior, by caller:

- **`engine.pricer.Pricer`** — the only production consumer.
  `engine/pricer.py:40-41` declares `iv_surface: IVSurface` and
  `basis_model: BasisModel` as required dataclass fields (no defaults).
  `engine/pricer.py:71-72` reads them on every `reprice_market` call,
  in fixed order — IV first, then basis — passing the same `now_ns`
  that was either supplied by the caller or captured at
  `engine/pricer.py:53`. The pricer never writes; it only reads.
  Because `Pricer` is a `@dataclass(slots=True)` (`engine/pricer.py:36`),
  the field types are checked only at type-check time; no runtime
  isinstance gate exists.
- **`benchmarks.harness.build_full_book_pricer`** — constructs a fresh
  `IVSurface(max_staleness_ms=60_000)` and `BasisModel(max_staleness_ms=
  60_000)` (`benchmarks/harness.py:76-77`) — note both surfaces use the
  same 60 s budget here, overriding `BasisModel`'s 30 s default. Then
  primes every synthetic commodity with `iv_surface.set_atm(c,
  sigma=0.35, ts_ns=now_ns)` and `basis_model.set(c,
  basis_drift_annualized=0.0, ts_ns=now_ns)` in a single loop
  (`benchmarks/harness.py:88-93`). The `BenchContext` dataclass exposes
  both surfaces as public fields (`benchmarks/harness.py:39-40`),
  making them reachable from `benchmarks/run.py`, although a `Grep`
  confirms `run.py` only touches them indirectly via `ctx.pricer`.
- **`tests.test_end_to_end._build_pricer`** — constructs both surfaces
  with `max_staleness_ms=60_000` (`tests/test_end_to_end.py:36-37`) and
  hands them to a `Pricer`. Each test case then primes whichever
  surfaces it needs and lets the pricer raise on the missing ones —
  e.g. `test_missing_iv_raises` (`tests/test_end_to_end.py:117-125`)
  primes only the basis, expecting `MissingStateError`.

No other module imports either class. `engine/scheduler.py:21-26`
defines `Priority.IV_UPDATE = 10` and `Priority.BASIS_UPDATE = 20`,
which is a nominal acknowledgement that the surfaces exist as event
sources, but the scheduler does not import or call them and (per
`audit/audit_A_cartography.md:254-257`) is itself unused. There is no
producer in the live tree that would call `set_atm` or `set` outside
of tests and the bench harness — the README's mention of CME options
chains as the IV source (`README.md:39`) and the `vol_source` /
`basis_model` keys in `config/commodities.yaml:15,18` describe an
intended source that does not exist in code.

## 6. Dependencies outbound

The two files together have exactly two import statements that escape
the module:

- `import math` (`state/iv_surface.py:16`, `state/basis.py:14`) — used
  only for `math.isfinite` (`state/iv_surface.py:31`, `state/basis.py:29`).
- `from state.errors import MissingStateError, StaleDataError`
  (`state/iv_surface.py:18`, `state/basis.py:16`) — used to raise the
  two distinct failure types from the readers
  (`state/iv_surface.py:40, 44-47`, `state/basis.py:40, 44-47`).
  `state/errors.py:11-16` makes `MissingStateError` a `LookupError`
  subclass and `StaleDataError` a `RuntimeError` subclass; this matters
  for callers that might catch them broadly.

Beyond these, the module has no direct dependencies — no `numpy`, no
`scipy`, no `numba`, no `time`, no `logging`. It does not call into
`state.tick_store`, `engine.event_calendar`, `models.*`, or anything
under `feeds/`. It does not read configuration files (`Registry` and
`Pricer` read `config/commodities.yaml`, but neither surface reads
configuration directly). It does no DNS, no socket, no file I/O.

## 7. State and side effects

In-process state per instance is exactly two attributes
(`state/iv_surface.py:22`, `state/basis.py:20`):

- `_atm` / `_basis`: a `dict[str, tuple[float, int]]` initialized empty
  in `__init__` (`state/iv_surface.py:27`, `state/basis.py:25`) and
  mutated only by the setter (`state/iv_surface.py:35`,
  `state/basis.py:35`).
- `_max_staleness_ms`: an int, set once in `__init__` and never
  re-assigned anywhere (`state/iv_surface.py:28`, `state/basis.py:26`).

There is no module-level state, no class-level mutable attribute, no
caching, no logging, and no side-effect propagation. There are no disk
or network operations. There are no callbacks or observers — a setter
write is invisible to any subscriber; the next reader call will see it
because the dict was mutated, but no event fires.

**Thread safety**: there are no locks, no atomics, and no
`threading`/`multiprocessing` imports. A concurrent `set_atm` and
`atm` on the same `commodity` is a race — Python's GIL makes the dict
operation atomic, so reads will see either the old or the new tuple
intact, but the staleness check uses both elements of the tuple
together, so there is no torn-read risk on the value alone. Whether
this is "thread-safe enough" is a property of the caller — the module
itself does not declare a safety class. The only call sites
(`engine/pricer.py:71-72`, the test fixtures, the bench harness) are
all single-threaded today.

**Ordering assumptions**:

- The setter trusts the caller's `ts_ns`. There is no monotonic check —
  a setter call with a `ts_ns` *older* than the previous one will
  silently downgrade the freshness of the surface. Compare with
  `state/tick_store.py`, which (per `audit/audit_A_cartography.md:216`)
  issues its own monotonic `seq` for provenance; this module does not.
- The reader trusts the caller's `now_ns`. If `now_ns < ts_ns` (clock
  skew, replay, or a tick from the future), `staleness_ms` is negative
  and the strict-greater comparison
  (`state/iv_surface.py:43`, `state/basis.py:43`) will pass — the value
  is returned despite the timestamp being unphysical. There is no
  defensive lower bound.
- The boundary on the staleness check is strict-greater
  (`state/iv_surface.py:43`, `state/basis.py:43`); a value exactly at
  budget age is still returned.

## 8. Invariants

Each invariant below is one the code actively enforces or quietly
relies on. Citations are to the specific guard or to the code path
that depends on the assumption.

1. **`max_staleness_ms > 0`** at construction. Enforced at
   `state/iv_surface.py:25-26` and `state/basis.py:23-24`. A budget of
   zero would make every fresh entry stale on read, and a negative
   budget would invert the comparison; both are rejected with
   `ValueError`.
2. **σ is finite and strictly positive**. Enforced at
   `state/iv_surface.py:31-32`. NaN, ±∞, 0, and negatives all raise.
   No upper bound is imposed; `set_atm("wti", 1e6, now_ns)` is
   accepted.
3. **basis drift is finite, sign-unconstrained**. Enforced at
   `state/basis.py:29-32`. NaN and ±∞ raise; negative drift is
   accepted, which is consistent with the docstring at
   `state/basis.py:8-9` ("`basis_drift` is annualized so it composes
   directly with `tau` (years) in the GBM forward: `F = spot *
   exp(basis_drift * tau)`") — a contango/backwardation flip would
   correspond to a sign change, and no caller could express that if
   sign were forbidden.
4. **`ts_ns > 0`** at write. Enforced identically at
   `state/iv_surface.py:33-34` and `state/basis.py:33-34`. Note the
   comparison is `<= 0`, which rejects zero. The unit (nanoseconds
   since some epoch) is implied by the variable name; no scale check
   is performed — `ts_ns = 1` would pass.
5. **`now_ns >= ts_ns` for any value the reader expects to return**.
   Implicit in the staleness arithmetic; the strict-greater check
   (`state/iv_surface.py:43`, `state/basis.py:43`) means a negative
   "staleness" would slip through. Cited as a relied-upon invariant
   without a guard — the caller is trusted to pass a `now_ns` from
   the same wall clock as `ts_ns`.
6. **Each commodity has at most one entry per surface, the most recent
   write**. Implicit in the unconditional dict overwrite at
   `state/iv_surface.py:35` and `state/basis.py:35`. There is no
   history; the previous tuple is dropped on every write.
7. **The two surfaces are independent — IV and basis can be primed in
   either order, and the pricer does not require them to share `ts_ns`**.
   Each is queried separately at `engine/pricer.py:71-72`; each
   maintains its own `_max_staleness_ms`. `tests/test_end_to_end.py:117-125`
   and `tests/test_end_to_end.py:128-136` confirm that the pricer
   raises `MissingStateError` from whichever surface is unprimed,
   without any cross-check between the two.
8. **The staleness budget is a property of the surface, not of the
   commodity**. Set once in `__init__`
   (`state/iv_surface.py:24-28`, `state/basis.py:22-26`); never
   per-key. Two commodities sharing one `IVSurface` instance share its
   budget; per-commodity overrides would require multiple instances.
9. **The default IV budget (60 s) is twice the default basis budget
   (30 s)**. Visible in the constructor signatures at
   `state/iv_surface.py:24` and `state/basis.py:22`. Both production
   callers (`benchmarks/harness.py:76-77`,
   `tests/test_end_to_end.py:36-37`) pass `60_000` for *both* surfaces,
   so the asymmetric defaults are never actually used by live code —
   they exist only as a contract embedded in the constructor signatures.

## 9. Error handling

The module raises three exception types and catches none.

- **`ValueError`** — raised inline by all three input validators on each
  class:
  - `IVSurface.__init__` if `max_staleness_ms <= 0`
    (`state/iv_surface.py:25-26`).
  - `IVSurface.set_atm` if `sigma` is not finite or `<= 0`
    (`state/iv_surface.py:31-32`), or `ts_ns <= 0`
    (`state/iv_surface.py:33-34`).
  - `BasisModel.__init__` if `max_staleness_ms <= 0`
    (`state/basis.py:23-24`).
  - `BasisModel.set` if `basis_drift_annualized` is not finite
    (`state/basis.py:29-32`), or `ts_ns <= 0`
    (`state/basis.py:33-34`).
  Every error message includes the offending value via f-string and,
  for setter errors, the commodity name.
- **`MissingStateError`** (defined at `state/errors.py:11-12` as a
  `LookupError` subclass) — raised by the readers when the dict lookup
  returns `None` (`state/iv_surface.py:39-40`, `state/basis.py:39-40`).
  The message includes the commodity name.
- **`StaleDataError`** (defined at `state/errors.py:15-16` as a
  `RuntimeError` subclass) — raised by the readers when the staleness
  exceeds the budget (`state/iv_surface.py:43-47`,
  `state/basis.py:43-47`). The message includes the actual age in ms
  (rounded to whole milliseconds via the `.0f` format spec) and the
  budget for comparison.

The two staleness errors propagate up through `engine/pricer.py` (no
catch in `engine/pricer.py:71-72`) and out to the caller. The pricer
docstring at `engine/pricer.py:12` states the policy: "A wrong theo
trades; a missing theo doesn't." `README.md:63` states the same as a
project non-negotiable. The module's behavior is consistent with both:
no fallback path is wired, no alternate value is returned, no warning
is logged.

## 10. Test coverage

There is no dedicated unit test file for either class. A `Glob` for
`test_iv*` and `test_basis*` returns no matches; the module has no
test of its own. Coverage is entirely indirect, via
`tests/test_end_to_end.py`:

- **Happy-path read**: `test_end_to_end_wti_matches_bs_analytical`
  (`tests/test_end_to_end.py:66-87`) primes both surfaces at
  `tests/test_end_to_end.py:76-77` and indirectly validates the
  reader by relying on the pricer producing an output that matches
  the analytical Black-Scholes reference. A failure of either reader
  would surface as a raise inside `Pricer.reprice_market`.
- **Missing IV**: `test_missing_iv_raises`
  (`tests/test_end_to_end.py:117-125`) primes only the basis; the
  expected raise is `MissingStateError`, propagated from
  `state/iv_surface.py:40` through `engine/pricer.py:71`.
- **Missing basis**: `test_missing_basis_raises`
  (`tests/test_end_to_end.py:128-136`) primes only the IV; the
  expected raise is `MissingStateError` from `state/basis.py:40`
  through `engine/pricer.py:72`.

What is **not** tested:

- **Stale IV**: no test primes IV with a `ts_ns` older than the budget
  and asserts `StaleDataError`. The closest analog is
  `test_stale_pyth_tick_raises` (`tests/test_end_to_end.py:91-102`),
  which tests the *tick store's* staleness — the IV staleness path in
  `state/iv_surface.py:43-47` has no direct test.
- **Stale basis**: same gap; no test for `state/basis.py:43-47`.
- **Constructor `max_staleness_ms <= 0`**: no test exercises
  `state/iv_surface.py:25-26` or `state/basis.py:23-24`.
- **Setter with NaN / ±∞ sigma or basis**: no test exercises
  `state/iv_surface.py:31-32` or `state/basis.py:29-32`.
- **Setter with `ts_ns <= 0`**: no test exercises
  `state/iv_surface.py:33-34` or `state/basis.py:33-34`.
- **`now_ns < ts_ns` (negative staleness)**: no test characterizes
  the behavior at the boundary or below it.
- **Boundary at exactly `max_staleness_ms`**: no test asserts whether
  the strict-greater comparison
  (`state/iv_surface.py:43`, `state/basis.py:43`) is intended.

There is no mocking of the surfaces — the tests use real instances.
There are no `pytest.fixture`s for either class; each test
re-constructs them via `_build_pricer` (`tests/test_end_to_end.py:32-48`).

## 11. TODOs, bugs, and smells

A `Grep` for `TODO|FIXME|XXX` against `state/` returns no matches —
neither file carries a literal marker. The smells below are structural,
each with citation.

1. **Duplicated implementation, no shared base.** The two files are
   essentially the same class with renamed methods and a different
   default budget. Compare `state/iv_surface.py:21-48` and
   `state/basis.py:19-48` line-by-line: the constructors, the
   staleness arithmetic, the strict-greater comparison, and the
   raise-shape are identical. Any change to the contract has to be
   made in two places.
2. **Asymmetric API surface for the same shape.** `IVSurface` exposes
   `set_atm` / `atm` (`state/iv_surface.py:30, 37`); `BasisModel`
   exposes `set` / `get` (`state/basis.py:28, 37`). Neither file
   explains the asymmetry; the `IVSurface` docstring at
   `state/iv_surface.py:8` mentions "the weekly expiry closest to the
   Kalshi settle", which suggests `atm` is descriptive of *which*
   point on a future surface is being read — but there is no surface
   to choose from yet, so the verb-noun asymmetry is decorative.
3. **Asymmetric input validation.** `set_atm` requires `sigma > 0`
   (`state/iv_surface.py:31`); `set` only requires
   `basis_drift_annualized` to be finite (`state/basis.py:29`).
   Negative basis drift is intentional (see invariant 3 in §8); the
   absence of an upper bound on either is unstated.
4. **Asymmetric default staleness budget.** 60 s on `IVSurface`
   (`state/iv_surface.py:24`), 30 s on `BasisModel`
   (`state/basis.py:22`). The two production callers
   (`benchmarks/harness.py:76-77`, `tests/test_end_to_end.py:36-37`)
   both pass 60 000 for both surfaces, so the asymmetric defaults are
   never used in practice and exist only as a signal in the
   constructor signature.
5. **Negative staleness slips through.** The reader compares
   `(now_ns - ts_ns) / 1e6 > self._max_staleness_ms`
   (`state/iv_surface.py:42-43`, `state/basis.py:42-43`). If
   `now_ns < ts_ns` — clock rewind, replay, future-dated tick — the
   left-hand side is negative and the comparison passes. There is no
   `abs()` and no `now_ns >= ts_ns` guard.
6. **Boundary inclusive of budget.** The strict-greater comparison
   means a value at exactly `max_staleness_ms` of age is "fresh" and
   returned. The inline error message at
   `state/iv_surface.py:46` and `state/basis.py:46` is constructed
   with the same `.0f` formatting that drops sub-millisecond
   precision — error messages cannot tell the user how close they
   were to the budget.
7. **No registration step.** Unlike `TickStore` (per
   `audit/audit_A_cartography.md:216`, which has a per-commodity
   `register`), the surfaces have no `register(commodity)` — a
   commodity becomes "known" the first time `set_atm` / `set` is
   called for it. There is no way to enumerate the commodities
   currently primed, no way to clear stale entries explicitly, and
   no way to drop a commodity once primed.
8. **No producer in the live tree.** `Grep` confirms only
   `benchmarks/harness.py:91-92` and `tests/test_end_to_end.py:76-157`
   ever call `set_atm` or `set`. There is no feed in `feeds/` that
   pushes into either surface; `feeds/pyth_ws.py` writes to
   `TickStore` but not to `IVSurface` or `BasisModel`. The hot path
   in `engine/pricer.py:71-72` reads from surfaces that, in
   production, no producer would have written. Compare against the
   `vol_source: "implied_weekly_atm"` and `basis_model: "ewma_5min"`
   strings in `config/commodities.yaml:15,18` — the configuration
   names producers that the code does not implement.
9. **Implicit time-unit contract.** The setter takes `ts_ns: int` and
   the reader takes `now_ns: int`; both are nanoseconds since some
   epoch by convention. Neither file documents which epoch (Unix?
   monotonic? `time.time_ns()` vs `time.perf_counter_ns()`?). The
   pricer at `engine/pricer.py:53` uses `time.time_ns()` (Unix
   epoch), and `tests/test_end_to_end.py:72-73` uses
   `int(datetime.timestamp() * 1_000_000_000)` (also Unix), so the
   convention is *Unix* — but the surfaces will silently produce
   garbage if a caller mixes monotonic and wall-clock timestamps.
10. **Docstring/implementation drift on intent.** Both module
    docstrings (`state/iv_surface.py:1-12`, `state/basis.py:1-10`)
    describe the present implementation as the "Deliverable 1"
    placeholder for a richer surface (a `(strike, expiry)` grid for
    IV, an AR(1)-fit model for basis). The current implementation has
    none of that machinery and no version flag distinguishing
    "current" from "planned" — the only signal is in the prose.
11. **`__slots__` declared but not enforced for the inner dict.** Both
    classes use `__slots__` (`state/iv_surface.py:22`,
    `state/basis.py:20`) which prevents new attributes — but the dict
    they hold is mutable and any caller with a reference to the
    instance can perturb it via, e.g., `iv._atm["wti"] = (-1.0, 0)`.
    The leading underscore is the only barrier; no name-mangling
    (double underscore) is used.
12. **Allocation per call.** `(now_ns - ts_ns) / 1e6` allocates a
    Python `float` per call (`state/iv_surface.py:42`,
    `state/basis.py:42`), and the f-string error messages in
    `state/iv_surface.py:44-47` and `state/basis.py:44-47` build a
    string only when the path raises. The hot path is two dict
    lookups, two tuple unpacks, two subtractions, two divides, and
    two compares per `reprice_market` — small, but not zero. The
    measured pricer p50 of ~17 µs (`README.md:17`) absorbs this
    without strain.

## 12. Open questions

These are items the code does not reveal and that would need a
maintainer to answer.

1. Why is the default staleness budget 60 s on `IVSurface`
   (`state/iv_surface.py:24`) but 30 s on `BasisModel`
   (`state/basis.py:22`)? Both production callers pass 60 000 to
   both. Are the defaults intended to encode different update
   cadences, or is one of them a typo from the other?
2. What is the intended sign convention of `basis_drift_annualized`?
   The docstring at `state/basis.py:8-9` gives the formula
   `F = spot * exp(basis_drift * tau)` but does not say whether
   `basis_drift` is `(CME - Pyth)`, `(Pyth - CME)`, the funding
   rate of one against the other, or something else entirely.
3. Should the surfaces have an upper bound on σ? `set_atm` accepts
   any positive finite value (`state/iv_surface.py:31`), including
   physically implausible ones (e.g., σ = 5,000% annualized).
4. Are these classes intended to be safe under concurrent
   `set_atm` / `atm` from different threads or asyncio tasks?
   `engine/scheduler.py:21-26` defines `IV_UPDATE` and
   `BASIS_UPDATE` priorities suggesting an async producer pattern,
   but the surfaces have no locks and the docstrings do not
   declare a thread-safety class.
5. What is the migration path from the current scalar surface to
   the "(strike, expiry) grid" mentioned in
   `state/iv_surface.py:3-7`? The docstring asserts the upgrade
   will be "additive" but the public interface is `atm(commodity,
   *, now_ns) -> float` — adding strike/expiry parameters cannot
   be done without changing the signature. Is the plan to add a
   second method (e.g. `iv(commodity, strike, expiry, *, now_ns)`)
   alongside `atm`, or to overload the return type?
6. Is the absence of a `register(commodity)` step (cf. `TickStore`)
   intentional? A `register` step would let the surface enumerate
   the configured commodities at startup and surface the "never
   primed" condition more loudly than the first read.
7. Is there a contract about the unit of `ts_ns`? The pricer uses
   wall-clock `time.time_ns()` (`engine/pricer.py:53`), which is
   what makes the staleness arithmetic meaningful. Should the
   surfaces validate that `ts_ns` is plausibly in Unix nanoseconds
   (e.g. `> 1e18`), or is the trust-the-caller stance deliberate?
8. Should the staleness boundary be inclusive (`>=`) or exclusive
   (`>`)? The current code is exclusive
   (`state/iv_surface.py:43`, `state/basis.py:43`); the difference
   is sub-millisecond and probably immaterial, but it is a contract
   decision that nothing documents.
