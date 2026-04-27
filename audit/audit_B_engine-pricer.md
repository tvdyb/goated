# Audit Phase B — `engine-pricer`

Cross-checked against `audit/audit_A_cartography.md:222`. The Phase A
inventory row for slug `engine-pricer` lists exactly one file, `engine/pricer.py`,
at ~90 LoC. The file in scope matches; no mismatch.

---

## 1. Module identity

- **Files**: `engine/pricer.py`
- **Total LoC**: 90 (final blank line excluded; the file ends at
  `engine/pricer.py:90`).
- **Summary**: A single-class orchestration module. `Pricer.reprice_market`
  is the synchronous composition point that turns a tick + sigma + basis
  drift + τ into a `TheoOutput`. It owns no calculation of its own; every
  numeric step is delegated. The module's contribution is the *order* of
  the gate checks, the *validation* it imposes between each step, and the
  *provenance* it stitches into `TheoInputs` for the downstream model.
  Comment header at `engine/pricer.py:1-13` calls out the discipline
  explicitly: "A wrong theo trades; a missing theo doesn't." Every
  observable behaviour in the module is consistent with that policy:
  failures raise; nothing falls back.

## 2. Responsibility

Inferred from the code, the module solves three problems on the hot path:

1. **Compose the per-tick pricing pipeline in a fixed order.**
   `engine/pricer.py:55-89` walks five state reads (config → tick → IV →
   basis → τ), assembles them into a frozen `TheoInputs` snapshot, hands
   that snapshot to a per-commodity model, and runs the result through a
   sanity check before returning. The order is hard-coded; there is no
   plan/optimizer step.
2. **Stamp the freshness contract.** Each external state has its own
   staleness budget. The pricer enforces the *Pyth tick* budget itself
   (`engine/pricer.py:60-65`) by reading `now_ns - tick.ts_ns` against
   `pyth_max_staleness_ms` from config, and delegates the IV and basis
   staleness checks to those subsystems by passing `now_ns` through
   (`engine/pricer.py:71-72`). It also enforces a non-positive-τ guard
   inline (`engine/pricer.py:74-75`).
3. **Stitch provenance.** `TheoInputs.as_of_ns` and `source_tick_seq`
   come from the pricer (`engine/pricer.py:84-85`) and ride downstream
   through `TheoOutput` (see `models/base.py:44-52` for the carrier
   shape). No other site produces these two fields.

The module is the only place in the live tree where these five state
reads are all colocated.

## 3. Public interface

The module's public surface, in declaration order:

- **`InsufficientPublishersError(RuntimeError)`** — `engine/pricer.py:32-33`.
  Sentinel exception raised when the latest tick's `n_publishers` is
  below the configured floor. Distinct from `StaleDataError`/
  `MissingStateError` so callers can route publisher-floor breaches
  separately from staleness or absence. No constructor logic; the only
  call site is the raise at `engine/pricer.py:67-69`.
- **`Pricer`** — `engine/pricer.py:36-90`. A `@dataclass(slots=True)` with
  six required attributes: `registry: Registry`, `tick_store: TickStore`,
  `iv_surface: IVSurface`, `basis_model: BasisModel`,
  `calendar: TradingCalendar`, `sanity: SanityChecker`. Construction is
  pure assignment (no `__post_init__`); the dataclass form means callers
  must supply all six positionally or by keyword. `slots=True` (line 36)
  makes the class non-monkey-patchable and slightly cheaper per
  attribute access — relevant on the hot path.
- **`Pricer.reprice_market(commodity, strikes, settle_ns, *, now_ns=None) -> TheoOutput`**
  — `engine/pricer.py:45-90`. The single entry point. Keyword-only
  `now_ns` allows deterministic time injection for tests and
  benchmarks; otherwise it captures `time.time_ns()` once at line 53
  and reuses that value across every downstream staleness check inside
  the call.

There is no `__all__` and no `__init__.py` re-export (`engine/__init__.py`
is empty per cartography note at `audit/audit_A_cartography.md:209-211`).
Anything not prefixed with `_` is therefore part of the de facto public
API; the three names above (the dataclass, its method, and the error
class) are the entire surface.

## 4. Internal structure

The class is a six-attribute dataclass with one method. There are no
helpers, no private methods, no module-level constants beyond the imports.
The data flow inside `reprice_market` is strictly linear, branchless
except for the four error gates:

```
now_ns ─┬─► registry.config(commodity)         → cfg
        │     │
        │     └─► cfg.raw["pyth_max_staleness_ms"], ["pyth_min_publishers"]
        │
        ├─► tick_store.latest(commodity)       → tick
        │     │
        │     ├─ gate: (now_ns - tick.ts_ns)/1e6 ≤ max_staleness_ms
        │     └─ gate: tick.n_publishers ≥ min_publishers
        │
        ├─► iv_surface.atm(commodity, now_ns=) → sigma   (raises if missing/stale)
        ├─► basis_model.get(commodity, now_ns=)→ basis_drift (raises if missing/stale)
        ├─► calendar.tau_years(commodity, now_ns, settle_ns) → tau
        │     └─ gate: tau > 0.0
        │
        ├─► TheoInputs(commodity, spot=tick.price, strikes=ascontiguousarray,
        │              tau, sigma, basis_drift,
        │              as_of_ns=now_ns, source_tick_seq=tick.seq)
        │
        ├─► registry.get(commodity).price(inputs) → TheoOutput
        └─► sanity.check(output, spot=tick.price)
```

Two structural choices stand out:

1. **`now_ns` is captured once.** `engine/pricer.py:53` reads
   `time.time_ns()` exactly once per call when the caller did not
   supply one. Every downstream staleness comparison
   (`engine/pricer.py:60`, the `now_ns=` kwargs at lines 71 and 72, the
   `now_ns` passed to the calendar at line 73, and the
   `as_of_ns=now_ns` provenance stamp at line 84) uses that same
   integer. There is no second clock read.
2. **Strikes are coerced exactly once at the boundary.** Line 80 calls
   `np.ascontiguousarray(strikes, dtype=np.float64)` before handing the
   array into `TheoInputs`. The downstream model also coerces
   (`models/gbm.py:87`), making this a redundant safety pass — but the
   array stored on `TheoInputs` is the coerced one, so the snapshot is
   guaranteed contiguous-float64 even if the model is later swapped out
   for one that does not re-coerce.

There are no loops in the pricer itself; all per-strike work happens
inside the model's numba kernel (`models/gbm.py:26-42`).

## 5. Dependencies inbound

`grep` for `from engine.pricer | engine\.pricer | InsufficientPublishersError`
returns five hit clusters; tests are excluded per the section spec and
covered in §10. The non-test inbound surface is:

- **`benchmarks/harness.py:24`** — `from engine.pricer import Pricer`. The
  harness instantiates a `Pricer` at `benchmarks/harness.py:97-104` with
  a synthetic 50-market registry, a fresh `TickStore`, a 60-second-budget
  `IVSurface`, a 60-second-budget `BasisModel`, a `TradingCalendar` whose
  WTI handler is reused across every synthetic commodity
  (`benchmarks/harness.py:93`), and a default-constructed `SanityChecker`.
  The harness packages the resulting pricer into a `BenchContext`
  dataclass (`benchmarks/harness.py:36-47`).
- **`benchmarks/run.py`** transitively. `benchmarks/run.py:24` imports
  the `BenchContext` from the harness and reaches the pricer via
  `ctx.pricer`. Three benchmark functions invoke
  `ctx.pricer.reprice_market` in tight loops:
  `benchmarks/run.py:121-124` (single-market, 5,000 iterations, 200µs
  budget), `benchmarks/run.py:130-140` (full-book over all
  commodities, 500 iterations, 200ms budget), and
  `benchmarks/run.py:170-172` (tick→theo, paired with a
  `feed.ingest_message`, 5,000 iterations, 250µs budget).
- The `main()` entry point at `benchmarks/run.py:182-187` calls
  `ctx.pricer.reprice_market(...)` once per commodity to "warm the
  pricer path" before timing — relevant because the first call into
  any commodity is the one that triggers numba JIT for the GBM kernel
  via `models/gbm.py:26`.

`grep` returns no other call sites: no service entry point, no CLI, no
async producer wires the pricer into a feed. Cartography flags this
explicitly at `audit/audit_A_cartography.md:98-100` ("There is no `main`
binary, CLI, or systemd/launchd unit"). The pricer is exercised today
exclusively via tests and benchmarks.

## 6. Dependencies outbound

Standard library and third-party:

- `time` for the wall-clock fallback at `engine/pricer.py:17, 53`.
- `dataclasses.dataclass` for the `Pricer` class shape at
  `engine/pricer.py:18, 36`.
- `numpy as np` for `np.ascontiguousarray` and the typing of the
  strikes ndarray (`engine/pricer.py:20, 48, 80`).

Intra-repo:

- `engine.event_calendar.TradingCalendar` (`engine/pricer.py:22`,
  invoked at line 73). The calendar's `tau_years` raises
  `NotImplementedError` for any commodity not registered
  (`engine/event_calendar.py:96-100`); only `wti` is registered by
  default at `engine/event_calendar.py:76-79`.
- `models.base.TheoInputs, TheoOutput` (`engine/pricer.py:23`,
  constructed at lines 77-86 and returned at line 90 respectively). Both
  are frozen, slotted dataclasses (`models/base.py:32-52`).
- `models.registry.Registry` (`engine/pricer.py:24`). Pricer reaches it
  twice per call: once for `config(commodity)` at line 55, once for
  `get(commodity)` at line 87. `Registry.get` raises `NotImplementedError`
  for stub commodities (`models/registry.py:80-83`) and `KeyError` for
  unknown ones (`models/registry.py:84`).
- `state.basis.BasisModel` (`engine/pricer.py:25`, called at line 72).
  Raises `MissingStateError` if not primed (`state/basis.py:39-40`),
  `StaleDataError` past its 30s default budget (`state/basis.py:43-47`).
- `state.errors.StaleDataError` (`engine/pricer.py:26`, raised at
  lines 62-65). The pricer raises this directly only for the Pyth tick
  branch; the equivalent staleness errors from `IVSurface` and
  `BasisModel` originate in those modules and propagate through.
- `state.iv_surface.IVSurface` (`engine/pricer.py:27`, called at line
  71). Raises `MissingStateError`/`StaleDataError` per
  `state/iv_surface.py:39-47`.
- `state.tick_store.TickStore` (`engine/pricer.py:28`, called at line
  59). `latest()` raises `MissingStateError` if the commodity isn't
  registered or the ring is empty (`state/tick_store.py:85-89`,
  `state/tick_store.py:57-59`).
- `validation.sanity.SanityChecker` (`engine/pricer.py:29`, called at
  line 89). Raises `SanityError` (subclass of `RuntimeError`) on any
  invariant breach (`validation/sanity.py:28-29, 43-68`).

No network I/O. No filesystem reads or writes. No subprocesses.

## 7. State and side effects

The `Pricer` instance carries six references and nothing else
(`engine/pricer.py:36-43`). It does not mutate any of those references
during a `reprice_market` call:

- `tick_store.latest(...)` is a read (`state/tick_store.py:57-66`).
- `iv_surface.atm(...)` is a read (`state/iv_surface.py:37-48`).
- `basis_model.get(...)` is a read (`state/basis.py:37-48`).
- `calendar.tau_years(...)` is a read (`engine/event_calendar.py:96-107`).
- `registry.config(...)` and `registry.get(...)` are reads
  (`models/registry.py:77-89`).
- `sanity.check(...)` raises or returns `None`; no mutation
  (`validation/sanity.py:38-68`).

Per-call allocations: one `LatestTick` dataclass via `tick_store.latest`
(`state/tick_store.py:61-66`), one numpy array from `np.ascontiguousarray`
at `engine/pricer.py:80` (a copy when the caller's array is not already
contiguous-float64), one `TheoInputs` at lines 77-86, and whatever the
model and sanity checker allocate downstream (the GBM model allocates a
second contiguous-float64 strikes copy at `models/gbm.py:87` and an
`out` buffer at `models/gbm.py:88`). The `argsort` inside the sanity
checker (`validation/sanity.py:59`) is one more allocation per call, on
each output.

Ordering assumptions:

- The pricer presumes `now_ns` ≥ `tick.ts_ns` so that
  `(now_ns - tick.ts_ns) / 1e6` is non-negative. There is no defensive
  check at `engine/pricer.py:60`; a `now_ns` earlier than the tick
  would yield a negative `staleness_ms` and silently pass the budget
  check at line 61.
- The pricer presumes `cfg.raw` is a `dict`-like object with `.get`
  (`engine/pricer.py:56-57`). `Registry._load` enforces this when it
  rejects non-mapping commodity entries (`models/registry.py:56-57`).
- The pricer presumes the registry's commodity is also registered with
  the tick store and the calendar. The dataclass construction does not
  cross-reference these. The end-to-end test at
  `tests/test_end_to_end.py:33-48` registers the commodity in the
  tick store explicitly (`tests/test_end_to_end.py:35`), and the
  benchmark harness does the same in a loop
  (`benchmarks/harness.py:88-93`). If the tick store has not been
  registered for `commodity`, `tick_store.latest` raises
  `MissingStateError` at `state/tick_store.py:88` before any other
  state is consulted.

## 8. Invariants

Each of the following is a property the code as written relies on, with
the citation that establishes it.

1. **`now_ns` is captured exactly once per call and reused.**
   `engine/pricer.py:53` → reused at lines 60, 71, 72, 73, 84. The
   pricer's per-call view of "now" is therefore monotonic *within* a
   call; staleness comparisons across the four staleness gates are
   consistent.
2. **Pyth tick staleness is enforced before publisher count.**
   `engine/pricer.py:60-69` runs the staleness branch first; a stale
   tick raises `StaleDataError` before the publisher count is
   inspected. Order is observable by tests because the two errors are
   distinct types.
3. **Both the Pyth-tick staleness budget and the publisher floor are
   resolved from per-commodity config.** Line 56 reads
   `pyth_max_staleness_ms` (default 2000), line 57 reads
   `pyth_min_publishers` (default 5). For WTI those values are 2000
   and 5 (`config/commodities.yaml:8-9`). The defaults match the WTI
   values, so an absent field for WTI behaves the same as the
   declared field — but other commodities silently inherit the WTI
   floor if their config omits the keys.
4. **τ must be strictly positive.** `engine/pricer.py:74-75` raises
   `ValueError` when `tau <= 0.0`. The calendar already returns `0.0`
   for `settle_ns <= now_ns` (`engine/event_calendar.py:101-102`), so
   the pricer's gate primarily catches that branch; it also catches a
   future calendar that returns negative τ.
5. **`source_tick_seq` is the post-push monotonic counter.**
   `engine/pricer.py:85` writes `tick.seq` into the snapshot. `tick.seq`
   comes from `TickRing.latest()` at `state/tick_store.py:65`, which
   reflects `self._seq` *as of the last push* (`state/tick_store.py:50-51`).
   This couples provenance to the push counter, not to a per-read
   counter.
6. **Strikes are passed as contiguous float64 to the model.**
   `engine/pricer.py:80` enforces this on the snapshot; the GBM model
   then re-coerces (`models/gbm.py:87`). The numba kernel at
   `models/gbm.py:26-42` requires contiguity (it uses raw indexing);
   the pricer's coercion makes the requirement satisfied at the
   snapshot boundary even if the model is replaced.
7. **`TheoInputs` is frozen.** Established by `models/base.py:32` (the
   `frozen=True, slots=True` dataclass decorator). The pricer relies on
   this to guarantee the snapshot handed to `model.price()` cannot be
   mutated mid-call by another thread or by the model itself.
8. **Sanity check runs after every successful `model.price()`.**
   `engine/pricer.py:88-89` is unconditional. There is no skip flag;
   the only ways to bypass `sanity.check` are an exception raised by
   `model.price()` or a Python-level error before that line.
9. **The pricer raises rather than returning a degraded theo.** The
   in-file docstring at `engine/pricer.py:12` ("A wrong theo trades; a
   missing theo doesn't") is matched by code: every gate uses `raise`,
   not a fallback value, and the only `return` is at line 90 after
   sanity passes.
10. **Spot is the tick price.** `engine/pricer.py:79` writes
    `spot=tick.price`. The same `tick.price` is also passed to
    `sanity.check(output, spot=tick.price)` at line 89 — the same
    `LatestTick` reference is reused. No mid-call refresh.
11. **`sigma` and `basis_drift` come from the surfaces, not the model
    instance.** Lines 71-72 fetch them per call, line 82-83 stamp them
    on `TheoInputs`. The model receives them as inputs, not as
    instance state. This matches `models/base.py:8-14` design notes.

## 9. Error handling

The pricer catches nothing. Every failure surfaces as a raised
exception. By call-site:

- **`registry.config(commodity)`** at `engine/pricer.py:55` —
  `KeyError` if the commodity is unknown (`models/registry.py:87-88`).
  Not caught.
- **`tick_store.latest(commodity)`** at `engine/pricer.py:59` —
  `MissingStateError` (subclass of `LookupError`, see
  `state/errors.py:11-12`) if the commodity isn't registered or the
  ring is empty. Not caught.
- **Stale Pyth tick** — pricer raises `StaleDataError` directly at
  `engine/pricer.py:62-65`. The message embeds the actual staleness in
  ms and the configured budget.
- **Insufficient publishers** — pricer raises
  `InsufficientPublishersError` at `engine/pricer.py:67-69`. The
  message embeds the count and the floor.
- **`iv_surface.atm(...)`** at `engine/pricer.py:71` —
  `MissingStateError` or `StaleDataError` from
  `state/iv_surface.py:39-47`. Propagated.
- **`basis_model.get(...)`** at `engine/pricer.py:72` — same two
  exceptions from `state/basis.py:39-47`. Propagated.
- **`calendar.tau_years(...)`** at `engine/pricer.py:73` —
  `NotImplementedError` for unregistered commodities
  (`engine/event_calendar.py:97-100`). Propagated.
- **Non-positive τ** — `ValueError` at `engine/pricer.py:74-75`. The
  message embeds both `settle_ns` and `now_ns`.
- **`registry.get(commodity)`** at `engine/pricer.py:87` —
  `NotImplementedError` for stub commodities
  (`models/registry.py:80-83`); `KeyError` for unknowns
  (`models/registry.py:84`). Propagated.
- **`model.price(...)`** at `engine/pricer.py:88` — for the GBM model,
  `ValueError` for any of: non-finite/non-positive τ, spot, sigma;
  non-finite basis drift; non-1-D, empty, or non-positive strikes
  (`models/gbm.py:70-85`). Propagated.
- **`sanity.check(...)`** at `engine/pricer.py:89` — `SanityError`
  (subclass of `RuntimeError`) for shape mismatches, NaN,
  out-of-[0,1], or non-monotone outputs (`validation/sanity.py:43-68`).
  Propagated.

The pricer itself owns two of these eleven failure modes
(`StaleDataError` for Pyth, `InsufficientPublishersError`, and the τ
guard); the other eight come from its callees and pass through
unchanged.

## 10. Test coverage

Two test files exercise the pricer.

**`tests/test_end_to_end.py`** — tests the full happy path and the
exhaustive failure matrix against a real `Registry` loaded from
`config/commodities.yaml`, real `TickStore`/`IVSurface`/`BasisModel`/
`TradingCalendar`/`SanityChecker` instances, and a real `GBMTheo`
(no mocks):

- `_build_pricer()` (`tests/test_end_to_end.py:32-48`) constructs a
  pricer with a 60-second IV staleness budget and a 60-second basis
  staleness budget — wider than production's 30s default for basis
  (`state/basis.py:22`) — so tests don't accidentally fail on the
  staleness floor when injecting a `now_ns` that exactly matches the
  prime time.
- `test_end_to_end_wti_matches_bs_analytical`
  (`tests/test_end_to_end.py:66-87`) — primes a tick at `now`, sets
  IV at 0.35, basis at 0.0, settle 2 hours later in the same WTI
  session. Asserts numerical parity with the BS reference at five
  strikes (atol 1e-9) and asserts `out.source_tick_seq == 1`,
  pinning the provenance contract.
- `test_stale_pyth_tick_raises` (`tests/test_end_to_end.py:91-102`) —
  covers the staleness branch at `engine/pricer.py:60-65`. Tick is
  10s old vs WTI's 2s budget.
- `test_insufficient_publishers_raises`
  (`tests/test_end_to_end.py:105-114`) — covers the publisher
  branch at `engine/pricer.py:66-69`. Tick has 3 publishers vs
  floor of 5.
- `test_missing_iv_raises` (`tests/test_end_to_end.py:117-125`),
  `test_missing_basis_raises` (`tests/test_end_to_end.py:128-136`),
  `test_missing_tick_raises` (`tests/test_end_to_end.py:139-147`) —
  cover the three `MissingStateError` propagations from the IV,
  basis, and tick callees.
- `test_stub_commodity_refuses_to_price`
  (`tests/test_end_to_end.py:150-163`) — primes state for `brent`
  (a stub) and asserts `(NotImplementedError, KeyError)` either from
  the calendar (no Brent handler) or from
  `Registry.get` (Brent is `stub: true`). The test explicitly notes
  uncertainty about which raises first
  (`tests/test_end_to_end.py:159-160`); ordering on a real run is
  determined by the call sequence in `engine/pricer.py:71-87`,
  where `calendar.tau_years` at line 73 fires before
  `registry.get` at line 87, so `NotImplementedError` from the
  calendar is the expected branch.

**`tests/test_benchmarks.py`** — budget-asserting latency tests:

- `test_pricer_single_market_under_200us`
  (`tests/test_benchmarks.py:64-70`) — runs `bench_pricer_single_market`
  (`benchmarks/run.py:118-127`) and asserts p99 < 200µs.
- `test_full_book_under_200ms` (`tests/test_benchmarks.py:73-79`) —
  exercises 50 markets via `bench_full_book` (`benchmarks/run.py:130-140`).
- `test_tick_to_theo_under_250us` (`tests/test_benchmarks.py:82-88`) —
  pairs `feed.ingest_message` with `pricer.reprice_market`.
- A primed-context fixture (`tests/test_benchmarks.py:47-52`) calls
  `reprice_market` once per commodity to warm caches and trigger
  numba compilation before timing.

What is **not** tested:

- The `tau <= 0.0` `ValueError` path at `engine/pricer.py:74-75` is
  not exercised. The calendar returns 0.0 for `settle_ns <= now_ns`
  (`engine/event_calendar.py:101-102`), so this branch is reachable
  via a settle-in-the-past, but no test sets that up against the
  pricer.
- The two `cfg.raw.get(...)` defaults at `engine/pricer.py:56-57`
  (max_staleness_ms = 2000, min_publishers = 5) are never hit because
  WTI's config explicitly sets both fields
  (`config/commodities.yaml:8-9`) and the benchmark harness's
  synthetic config also sets both (`benchmarks/harness.py:60-65`).
- The non-1-D / empty / non-positive strikes branches inside
  `GBMTheo.price` (`models/gbm.py:78-85`) are exercised in
  `tests/test_gbm_analytical.py` (per cartography
  `audit/audit_A_cartography.md:177-178`) at the model layer, not
  through the pricer.
- The `SanityChecker` failure paths are tested indirectly by GBM
  parity tests but no test injects a deliberately-broken model into
  the pricer to verify the sanity gate raises end-to-end.
- Nothing is mocked. All tests run the full real stack; the only
  thing tests substitute is `now_ns` (via the keyword) and the
  staleness budgets passed to `IVSurface`/`BasisModel` constructors.

## 11. TODOs, bugs, and smells

Literal markers: `grep` for `TODO|FIXME|XXX|HACK` against
`engine/pricer.py` returns no matches. There are no commented-out
blocks.

Structural observations, each with citation:

- `engine/pricer.py:56-57` — defaults of 2000 ms and 5 publishers are
  hard-coded as `int(...)` fallbacks inside the hot path. They match
  WTI's declared values (`config/commodities.yaml:8-9`), so for WTI
  the defaults are dead. For any commodity whose config omits these
  keys, the pricer silently inherits WTI's numbers. The cartography
  flags an adjacent fact at `audit/audit_A_cartography.md:270-275`:
  `feeds/pyth_ws.py:112-115` defaults `num_publishers` to `0` when
  Hermes omits the field, which interacts with the floor check at
  `engine/pricer.py:66-69` — every floor-failing tick from such a
  message would raise `InsufficientPublishersError` at runtime.
- `engine/pricer.py:60` — `(now_ns - tick.ts_ns) / 1e6` is unguarded
  against negative time deltas. A `now_ns < tick.ts_ns` (clock skew,
  test timing, intentional injection) yields a negative
  `staleness_ms` that silently passes the comparison at line 61.
- `engine/pricer.py:74-75` — the τ guard accepts `tau == 0.0` as
  failure (because of `tau <= 0.0`). The calendar's
  `settle_ns <= now_ns` branch returns exactly `0.0`
  (`engine/event_calendar.py:101-102`), so the two guards overlap;
  the calendar's branch is silently swallowed and the pricer's
  `ValueError` is the one users see.
- `engine/pricer.py:80` and `models/gbm.py:87` — `np.ascontiguousarray`
  is invoked twice on the same input on the WTI hot path. For
  already-contiguous-float64 arrays, both calls are no-ops; for
  non-conforming arrays the first allocates a copy and the second
  is a no-op. Not a bug per se; it is a redundant safety pass at
  the pricer/model boundary.
- `engine/pricer.py:36-43` — the dataclass takes six concrete
  collaborators by name. There is no protocol/abstract typing; swap-in
  test doubles would have to duck-type the methods. The tests do not
  exploit this (they pass real instances).
- The pricer reaches into `cfg.raw` at `engine/pricer.py:56-57`
  rather than through typed accessors on `CommodityConfig`. The
  registry's `CommodityConfig` (`models/registry.py:24-29`) is a
  frozen dataclass with `commodity`, `model_name`, `raw`, `is_stub`;
  the keyed-lookup pattern means the pricer is implicitly part of
  the YAML schema's contract, even though the registry is the only
  place declared to own that contract.
- `engine/pricer.py:71-72` — IV and basis lookups are sequential.
  Either could raise `MissingStateError` or `StaleDataError`; the
  pricer therefore has a fixed surfacing order (IV first, then
  basis). Tests rely on this ordering implicitly when they prime
  one but not the other (`tests/test_end_to_end.py:117-125` and
  `:128-136`).
- `engine/pricer.py:32-33` — `InsufficientPublishersError` extends
  `RuntimeError`, while `StaleDataError` also extends `RuntimeError`
  (`state/errors.py:15-16`) and `MissingStateError` extends
  `LookupError` (`state/errors.py:11-12`). The taxonomy is
  inconsistent: two of three pricer-related failures are
  `RuntimeError`s and one is a `LookupError`; a blanket
  `except RuntimeError` would catch publisher and stale-tick errors
  but miss missing-state errors.

## 12. Open questions

Things the code does not reveal that would need to be confirmed by a
maintainer:

1. **Is `Pricer` intended to be reused across threads?** The dataclass
   has no locks. State callees (`TickStore`, `IVSurface`, `BasisModel`)
   also have no synchronization. The hot path is single-threaded under
   the current benchmark harness but the design assumption is not
   stated.
2. **Is there a contract for `now_ns` ≥ `tick.ts_ns`?** The pricer
   does not enforce it (`engine/pricer.py:60`); the tests always
   inject a `now_ns` ≥ `tick.ts_ns`. Whether negative staleness should
   be a hard error, or whether wall-clock skew across hosts is
   considered out of scope, is not documented in the file.
3. **Is `pyth_min_publishers = 0` a legitimate config?** The fallback
   in `int(cfg.raw.get("pyth_min_publishers", 5))` (`engine/pricer.py:57`)
   silently coerces the YAML value; a `0` would disable the gate. The
   only deployed config value is 5 (`config/commodities.yaml:8`); no
   comment describes whether 0 is valid.
4. **Should `tau == 0.0` be distinguishable from negative τ?** Both
   raise the same `ValueError` via `engine/pricer.py:74-75`. The
   underlying causes differ (settle-already-past vs. true negative).
   No comment expresses whether callers care to tell them apart.
5. **Is `SanityError` allowed to propagate to the publish layer?** The
   pricer does not catch it, so today it bubbles to whatever calls
   `reprice_market`. There is no published policy for what consumers
   do on a `SanityError` vs. a `StaleDataError`; the file's
   "missing theo doesn't trade" doctrine
   (`engine/pricer.py:12`) implies both are equivalent, but no caller
   exists to confirm.
6. **What is the lifetime of a `Pricer` instance?** Tests build one
   per test (`tests/test_end_to_end.py:40-47`); the benchmark
   harness builds one per run (`benchmarks/harness.py:97-104`). No
   long-running owner exists today, so reuse semantics (cache
   invalidation, config reload) are unobserved.
7. **Why is `SanityChecker` injected rather than constructed
   internally?** Every observed call site builds a default-constructed
   `SanityChecker()` (`tests/test_end_to_end.py:39`,
   `benchmarks/harness.py:79`). The injection point exists at
   `engine/pricer.py:43` but the optionality is unused; whether this
   anticipates per-commodity tolerances or alternative checker
   implementations is not documented.
