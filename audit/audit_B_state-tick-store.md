# Audit Phase B — `state-tick-store`

Cross-checked against `audit/audit_A_cartography.md:216`. The Phase A
inventory row for slug `state-tick-store` lists exactly one file,
`state/tick_store.py`, at ~92 LoC and `numpy` as the sole external
dependency. The file in scope matches; no mismatch. The package's
`state/__init__.py` is empty (one-byte / zero-effective-line file) and
contributes no surface area.

---

## 1. Module identity

- **Files**: `state/tick_store.py` (the only file in the module per
  cartography). The state package's `__init__.py` is present but empty.
- **Total LoC**: 92 lines of Python (matches Phase A inventory at
  `audit/audit_A_cartography.md:216`). The visible content runs from a
  module docstring at `state/tick_store.py:1-12` to the final method body
  at `state/tick_store.py:91-92`.
- **Summary**: A two-class, numpy-backed in-memory tick history. `TickRing`
  is a single-commodity, fixed-capacity ring buffer with O(1) push and
  O(1) latest-tick lookup, plus a monotonic sequence counter that survives
  ring wrap. `TickStore` is a thin per-commodity registry of `TickRing`
  instances keyed by commodity name. The module exposes a `LatestTick`
  dataclass for the read result, and raises `MissingStateError`
  (re-exported from `state/errors.py:11-12`) on every absence path. There
  is no read-history method on the public surface today; only `latest()`
  is wired to a caller. The header docstring at
  `state/tick_store.py:1-12` flags this gap explicitly: "deliverable 1
  only stores the latest tick on the hot path; the ring history is here
  for backtest and feature-computation callers."

## 2. Responsibility

Inferred from the code, the module solves four concrete problems:

1. **Decouple ingest from pricing on the hot path.** The Pyth WebSocket
   feed (`feeds/pyth_ws.py:117`) writes ticks via `TickStore.push`; the
   pricer (`engine/pricer.py:59`) reads them via `TickStore.latest`.
   Neither side holds a reference to the other; the store sits between
   them as the only shared mutable artefact for tick state. The
   end-to-end test confirms that wiring at `tests/test_end_to_end.py:34-48`,
   where the same `TickStore` is passed into the `Pricer` and is the
   target of every test's `tick_store.push("wti", …)` call (e.g.
   `tests/test_end_to_end.py:75, 96, 108, 120, 131, 155`).

2. **Preallocate so the hot path never grows arrays.** The constructor
   creates three fixed-size numpy arrays at register time
   (`state/tick_store.py:38-40`): `_ts_ns: int64`, `_price: float64`,
   `_n_publishers: int32`. Default capacity is one million slots
   (`state/tick_store.py:34, 70`). Push writes into a precomputed index
   and advances a wrap-around cursor (`state/tick_store.py:45-49`). The
   intent is to never allocate after registration so the ingest path
   doesn't trigger Python-level allocation churn. The cartography flags
   the per-commodity memory footprint at
   `audit/audit_A_cartography.md:276-280` (~20 MB / commodity at default
   capacity).

3. **Mint a stable, monotonic tick provenance ID that survives wrap.**
   `_seq` is incremented on every push (`state/tick_store.py:50`) and is
   distinct from the wraparound `_cursor`. The header docstring at
   `state/tick_store.py:4-7` is explicit about why both exist: "A
   monotonic `seq` counter (distinct from the wraparound cursor) is used
   as `source_tick_seq` on every published theo, so a theo can be traced
   to the exact tick that drove it even after the ring wraps." The pricer
   plumbs that seq into `TheoInputs.source_tick_seq` at
   `engine/pricer.py:85`.

4. **Refuse to fabricate a tick when none exists.** The two missing-state
   raises at `state/tick_store.py:59` (empty ring), `state/tick_store.py:82`
   (push to unregistered commodity), and `state/tick_store.py:88` (latest
   on unregistered commodity) replace any silent fallback. This matches
   the project's stated "missing data raises, never falls back" stance
   that `engine/pricer.py:1-13` calls out as the doctrine of the live
   pipeline.

## 3. Public interface

The module's public surface, in declaration order:

- **`LatestTick`** — `state/tick_store.py:23-28`. A `@dataclass(slots=True)`
  with four fields: `ts_ns: int`, `price: float`, `n_publishers: int`,
  `seq: int`. Used as the return type of `TickRing.latest()` and
  `TickStore.latest()`. Not declared `frozen=True`, so the dataclass is
  technically mutable, but no caller mutates it. `slots=True` (line 23)
  forbids attribute addition and shrinks per-instance memory — relevant
  because a fresh instance is allocated on every read
  (`state/tick_store.py:61-66`), which the per-tick repricer goes
  through once per `reprice_market` call (`engine/pricer.py:59`).

- **`TickRing`** — `state/tick_store.py:31-66`. A `__slots__`-declared
  class (`state/tick_store.py:32`) holding the three numpy buffers, the
  cursor, the seq, and the capacity for one commodity. Not a dataclass;
  the constructor allocates the arrays directly. Behavioural surface:

  - `__init__(self, capacity: int = 1_000_000) -> None` —
    `state/tick_store.py:34-42`. Validates `capacity > 0` (`:35-36`) and
    allocates three parallel numpy arrays of that length plus the two
    integer counters `_cursor = 0` and `_seq = 0`.

  - `push(self, ts_ns: int, price: float, n_publishers: int) -> int`
    — `state/tick_store.py:44-51`. Writes the three values at
    `_cursor`, advances the cursor mod capacity, increments `_seq`,
    returns the new `_seq`. There is no validation of any input value;
    NaN or negative prices, zero or negative timestamps, and negative
    publisher counts all pass through unchecked. Compare with
    `state/iv_surface.py:31-34` and `state/basis.py:29-34`, which both
    raise on non-finite inputs and non-positive `ts_ns`.

  - `last_seq` — `state/tick_store.py:53-55`. A read-only property
    returning `_seq`. Currently has zero callers anywhere in the tree
    (Grep `\.last_seq` returns no hits outside this file).

  - `latest(self) -> LatestTick` — `state/tick_store.py:57-66`. Raises
    `MissingStateError("ring is empty")` if `_seq == 0`. Otherwise
    computes the just-written index as `(self._cursor - 1) % self.capacity`
    and reads the three arrays into a fresh `LatestTick` dataclass with
    explicit `int(...)`/`float(...)` casts that convert numpy scalars
    back to Python ints/floats (`:62-65`). The reported `seq` is
    `self._seq` (`:65`), i.e. the seq *as of the last push* — which the
    `engine-pricer` audit notes (`audit/audit_B_engine-pricer.md:285-288`)
    means the value reflects the latest push, not the seq at the moment
    of any reader's call.

- **`TickStore`** — `state/tick_store.py:69-92`. The per-commodity
  facade. Not slotted (no `__slots__` declaration on the class body)
  unlike `TickRing`. Behavioural surface:

  - `__init__(self, capacity_per_commodity: int = 1_000_000) -> None` —
    `state/tick_store.py:70-72`. Stores an empty `dict[str, TickRing]`
    and the per-ring capacity to use when registering. The capacity is
    not validated at this layer; the underlying `TickRing.__init__`
    will raise on `capacity <= 0`.

  - `register(self, commodity: str) -> TickRing` —
    `state/tick_store.py:74-77`. Idempotent (`:75` checks membership
    first). On first call, instantiates a new `TickRing` with the
    stored capacity and inserts it into `_rings`. On subsequent calls
    with the same commodity, returns the existing ring without
    replacement. Returns the ring object — but no caller currently
    captures that return value.

  - `push(self, commodity, ts_ns, price, n_publishers) -> int` —
    `state/tick_store.py:79-83`. Looks up the ring with `dict.get`;
    raises `MissingStateError` if not registered (`:81-82`). Otherwise
    delegates to `TickRing.push` and returns its monotonic seq.

  - `latest(self, commodity) -> LatestTick` —
    `state/tick_store.py:85-89`. Same dict lookup; raises
    `MissingStateError` on absence (`:87-88`). Otherwise delegates to
    `TickRing.latest`, which itself raises `MissingStateError` if the
    ring is empty.

  - `commodities(self) -> list[str]` —
    `state/tick_store.py:91-92`. Returns `sorted(self._rings)`. Has
    zero non-test callers (Grep for `tick_store.commodities` returns
    no hits anywhere; `Registry.commodities` is the only `commodities`
    call exercised by tests, e.g. `tests/test_end_to_end.py:55`).

There is no `__all__` and no re-export from `state/__init__.py`. The
de facto public API is everything above plus the `MissingStateError`
import at `state/tick_store.py:20`, which makes the error class
reachable as `state.tick_store.MissingStateError` even though its
canonical home is `state/errors.py:11-12`.

## 4. Internal structure

**Key types.** Two classes plus one dataclass:

- `LatestTick` (`state/tick_store.py:23-28`) — the read-side value
  object. Carries the seq alongside the fields so a reader gets the
  provenance ID without a second call.
- `TickRing` (`state/tick_store.py:31-66`) — the per-commodity buffer.
- `TickStore` (`state/tick_store.py:69-92`) — the per-commodity router.

**Memory layout.** Per `TickRing` the storage is three parallel,
contiguous numpy arrays plus three Python ints:

| Field | Type | Per-slot bytes | At capacity 1,000,000 |
|---|---|---|---|
| `_ts_ns` (`:38`) | `int64` | 8 | 8 MB |
| `_price` (`:39`) | `float64` | 8 | 8 MB |
| `_n_publishers` (`:40`) | `int32` | 4 | 4 MB |
| `_cursor` (`:41`) | Python `int` | n/a | scalar |
| `_seq` (`:42`) | Python `int` | n/a | scalar |
| `capacity` (`:37`) | Python `int` | n/a | scalar |

That gives 20 MB per registered commodity at default capacity, which
matches the cartography's red-flag note at
`audit/audit_A_cartography.md:276-280`.

**Data flow within the module.**

```
TickStore.register(c)                       (state/tick_store.py:74-77)
   └─► self._rings[c] = TickRing(capacity)  (:76)

TickStore.push(c, ts_ns, price, np)         (state/tick_store.py:79-83)
   └─► ring = self._rings.get(c)            (:80)
       └─► ring.push(ts_ns, price, np)      (:83)
           ├─► self._ts_ns[i] = ts_ns       (:46)
           ├─► self._price[i] = price       (:47)
           ├─► self._n_publishers[i] = np   (:48)
           ├─► self._cursor = (i+1)%cap     (:49)
           └─► self._seq += 1               (:50)

TickStore.latest(c)                         (state/tick_store.py:85-89)
   └─► ring = self._rings.get(c)            (:86)
       └─► ring.latest()                    (:89)
           ├─► if self._seq == 0: raise     (:58-59)
           ├─► idx = (cursor-1)%cap         (:60)
           └─► return LatestTick(...)       (:61-66)
```

**Notable algorithmic details.**

- The push index is *the cursor's current value* (`i = self._cursor` on
  line 45), and the cursor is advanced *after* the write (line 49).
  The latest read therefore reconstructs the just-written index by
  *subtracting one* from the cursor under the same modulo
  (`state/tick_store.py:60`).
- `latest()` casts each numpy scalar back to a native Python type
  (`int(self._ts_ns[idx])`, `float(self._price[idx])`,
  `int(self._n_publishers[idx])` at `state/tick_store.py:62-64`). The
  cast is deliberate: `LatestTick` advertises `int`/`float` typed
  fields, and downstream code in `engine/pricer.py:60-69, 85` does
  arithmetic and a comparison on them where mixing numpy and Python
  scalars is possible but irregular.
- Wrap-around safety relies on `(self._cursor - 1) % self.capacity`
  (`:60`). When `_cursor == 0` and `_seq > 0`, the modulo correctly
  resolves to `capacity - 1`, pointing at the last-written slot before
  the wrap. The empty-ring guard (`if self._seq == 0: raise` at
  `:58-59`) is what ensures this expression isn't reached before any
  push, where it would otherwise resolve to `capacity - 1` and read a
  zero-initialized slot.

## 5. Dependencies inbound — who calls this module

Live (non-test) callers, all confirmed by Grep of `TickStore`,
`TickRing`, `LatestTick`, `tick_store`:

- **`feeds/pyth_ws.py`** — the only ingest producer.
  - Imports `TickStore` at `feeds/pyth_ws.py:29`.
  - Holds it as a dataclass field at `feeds/pyth_ws.py:50`.
  - Calls `register(commodity)` once per configured feed in its
    `__post_init__` at `feeds/pyth_ws.py:55-58`.
  - Calls `push(commodity, ts_ns, price, num_publishers)` per parsed
    Hermes `price_update` at `feeds/pyth_ws.py:117`. Captures the
    returned seq into the `(commodity, seq)` tuple it hands back to
    the caller.

- **`engine/pricer.py`** — the only reader on the hot path.
  - Imports `TickStore` at `engine/pricer.py:28`.
  - Holds it as a dataclass field at `engine/pricer.py:39`.
  - Calls `latest(commodity)` once per `reprice_market` invocation at
    `engine/pricer.py:59`. The returned `LatestTick` supplies
    `tick.ts_ns` (staleness check, `:60-65`), `tick.n_publishers`
    (publisher floor, `:66-69`), `tick.price` (spot, `:79`), and
    `tick.seq` (provenance, `:85`).

- **`benchmarks/harness.py`** — the latency harness.
  - Imports `TickStore` at `benchmarks/harness.py:29`.
  - Constructs a fresh `TickStore()` at `benchmarks/harness.py:75`.
  - Registers each synthetic commodity (`benchmarks/harness.py:89`) and
    seeds it with one pre-staleness-budget tick
    (`benchmarks/harness.py:90`) before running the pricer.

- **`benchmarks/run.py`** — drives the latency harness.
  - Does not import `TickStore` directly, but at
    `benchmarks/run.py:149` passes the bench context's `tick_store`
    field into a `PythHermesFeed` so the tick→theo benchmark exercises
    the real ingest → store → pricer chain.

Test-side callers:

- **`tests/test_pyth_ws.py`** — imports `TickStore` at
  `tests/test_pyth_ws.py:12`, instantiates one in `_make_feed` at
  `:18`, and asserts on `store.latest("wti")` at `:47, 111`. Every
  test in the file routes through `TickStore.push` indirectly via
  `feed.ingest_message`.
- **`tests/test_end_to_end.py`** — imports at
  `tests/test_end_to_end.py:24`, builds a fresh store at `:34`, and
  drives `register`, `push`, and (via the pricer) `latest` across
  every test. Concrete pushes at `:75, 96, 108, 120, 131, 155`;
  registers at `:35, 153`.

The module has zero callers in `models/`, `validation/`,
`engine/scheduler.py`, `engine/event_calendar.py`, or `calibration/`.
The benchmark and test directories are the only callers outside of
`feeds/pyth_ws.py` and `engine/pricer.py`.

## 6. Dependencies outbound — what this module calls

All outbound dependencies are declared at the top of the file:

- `from __future__ import annotations` (`state/tick_store.py:14`) —
  PEP 563 deferred annotations.
- `from dataclasses import dataclass` (`state/tick_store.py:16`).
- `import numpy as np` (`state/tick_store.py:18`) — used for
  `np.zeros`, `np.int64`, `np.float64`, `np.int32` at
  `state/tick_store.py:38-40`. Numpy is the module's only third-party
  dependency, matching `audit/audit_A_cartography.md:216`.
- `from state.errors import MissingStateError` (`state/tick_store.py:20`).
  The intra-package error class defined at `state/errors.py:11-12` as a
  `LookupError` subclass.

There are no other imports, no I/O calls, no logging (the module does
not import `logging`), and no calls to time, math, asyncio, or yaml.

## 7. State and side effects

**In-process state.** All state lives on instance attributes:

- `TickRing._ts_ns`, `_price`, `_n_publishers` — preallocated numpy
  arrays mutated in place by `push` (`state/tick_store.py:46-48`).
- `TickRing._cursor` — wrap-around write index, mutated by `push`
  (`state/tick_store.py:49`).
- `TickRing._seq` — monotonically increasing tick counter, mutated by
  `push` (`state/tick_store.py:50`).
- `TickRing.capacity` — set once in `__init__` (`state/tick_store.py:37`)
  and never mutated afterwards.
- `TickStore._rings` — `dict[str, TickRing]`, mutated only by `register`
  (`state/tick_store.py:76`); never deleted from.
- `TickStore._capacity` — set once in `__init__` (`state/tick_store.py:72`)
  and read on each `register` call.

**Disk I/O.** None. The module never opens a file, never imports `os`
or `pathlib`. Captures from `audit/audit_A_cartography.md:127-137`
agree: tick state is purely in-memory.

**Network I/O.** None.

**Global mutation.** None. There are no module-level mutable globals;
the only module-level binding besides the imports and class definitions
is the docstring.

**Thread / concurrency assumptions.** The module is unsynchronised:
no `threading.Lock`, no `asyncio.Lock`, no use of `multiprocessing`
primitives, no atomic counters. `_seq += 1` (`state/tick_store.py:50`)
is not protected. The numpy buffer writes at `:46-48` are independent
of `_cursor` and `_seq` advances at `:49-50`. In a single-writer,
single-reader asyncio context (which is the only context the live
caller graph creates — `feeds/pyth_ws.py:120-145` is the sole writer
inside one event loop, and `engine/pricer.py:45-90` is the sole reader
called from the same loop) this is sufficient. The module makes no
defensive accommodations beyond that. The cartography records the
absence of locks indirectly at `audit/audit_A_cartography.md:127-137`
("In-memory data") with no concurrency guarantees declared.

**Ordering assumptions.** Two are observable:

1. `register` *must* precede `push` and `latest` for a given
   commodity. The two `MissingStateError` raises at
   `state/tick_store.py:81-82, 87-88` enforce this at runtime.
2. `push` *must* precede `latest` for `latest` to succeed. The
   `_seq == 0` guard at `state/tick_store.py:58-59` enforces this. The
   end-to-end tests rely on it: `tests/test_end_to_end.py:139-147`
   ("test_missing_tick_raises") registers no tick before calling the
   pricer and expects a `MissingStateError`, and the pricer's
   `tick_store.latest(commodity)` at `engine/pricer.py:59` is the call
   that surfaces it.

## 8. Invariants

Each invariant is paired with the line(s) of evidence in the code:

- **Capacity is strictly positive.** The constructor raises on
  `capacity <= 0` (`state/tick_store.py:35-36`). Downstream arithmetic
  — `(i + 1) % self.capacity` (`:49`) and `(self._cursor - 1) % self.capacity`
  (`:60`) — would divide by zero or produce nonsensical indices if
  this were violated.
- **`_seq` is strictly monotonic across the lifetime of a `TickRing`.**
  Mutated only by `push` (`state/tick_store.py:50`), only by `+= 1`,
  and never reset. The header docstring at `state/tick_store.py:4-7`
  states this as the contract: a theo's `source_tick_seq` "can be
  traced to the exact tick that drove it even after the ring wraps."
- **`_cursor` always lies in `[0, capacity)`.** Set to `0` at init
  (`state/tick_store.py:41`) and updated only by
  `(i + 1) % self.capacity` (`:49`). Modulo by capacity preserves the
  bound.
- **`latest()` is only called when at least one push has occurred.**
  Encoded by the `_seq == 0` guard at `state/tick_store.py:58-59`.
  Without that guard, the cursor-1 modulo at `:60` would happily index
  the zero-initialized slot at `capacity - 1` and return a
  `(ts_ns=0, price=0.0, n_publishers=0, seq=0)` `LatestTick` — which
  would propagate into `engine/pricer.py:60` (`now_ns - tick.ts_ns`
  becomes huge) and trigger a `StaleDataError` rather than a
  `MissingStateError`. The guard preserves the "missing vs stale"
  distinction relied on by `state/errors.py:1-7`.
- **Commodities are added but never removed.** `register`
  (`state/tick_store.py:74-77`) is the only write path for `_rings`;
  there is no `unregister`, `clear`, or `pop`. The dict grows
  monotonically.
- **The latest-write index is `(cursor - 1) mod capacity`.** Implicit
  from the asymmetry between `i = self._cursor` *before* mutation
  (`state/tick_store.py:45`) and `self._cursor = (i + 1) % self.capacity`
  *after* (`:49`); the read path inverts this at `:60`.
- **`LatestTick.seq` reflects the most recent push, not the slot's
  seq.** `state/tick_store.py:65` reads `seq=self._seq` (current
  counter), not a per-slot stored seq. There is no per-slot seq
  storage. This is observable behaviour: a reader who only invokes
  `latest()` *after* a push and treats the returned `seq` as the
  identity of the just-read tick is correct under the single-writer
  ordering assumption from §7.
- **Push input domain is unenforced.** `push` (`state/tick_store.py:44-51`)
  performs no validation on `ts_ns`, `price`, or `n_publishers`. The
  comparable functions in sister modules — `IVSurface.set_atm`
  (`state/iv_surface.py:31-34`) and `BasisModel.set`
  (`state/basis.py:29-34`) — both raise on non-finite inputs and
  non-positive `ts_ns`. The tick store, by contrast, trusts upstream.
  The only place a caller validates is `feeds/pyth_ws.py:103-115`,
  where the parser raises on malformed Pyth fields before reaching
  `tick_store.push`.

## 9. Error handling

The module raises three error types and catches none.

- `ValueError` — `state/tick_store.py:35-36`. Constructor rejects
  non-positive capacity. The message includes the bad value
  (`f"capacity must be > 0, got {capacity}"`).
- `MissingStateError` (subclass of `LookupError`, see
  `state/errors.py:11-12`) — three sites, one in `TickRing` and two in
  `TickStore`:
  - `state/tick_store.py:58-59` ("ring is empty") on `latest()` with
    `_seq == 0`.
  - `state/tick_store.py:81-82` ("`{commodity}: commodity not registered
    in tick store`") on `push` to an unregistered commodity.
  - `state/tick_store.py:87-88` (same string) on `latest` for an
    unregistered commodity.

There are no `try`/`except` blocks anywhere in the file. Every error
propagates to the caller. The pricer relies on this directly: the
catch-or-not analysis in `audit/audit_B_engine-pricer.md:325-340`
records that `MissingStateError` from `tick_store.latest` propagates
unchanged out of `Pricer.reprice_market` (it is not caught at
`engine/pricer.py:59`). The end-to-end test
`tests/test_end_to_end.py:139-147` asserts that exact propagation by
expecting `MissingStateError` at the pricer's API boundary when no
`tick_store.push` has occurred.

The module never logs. Failures are pure exceptions; no
`logging.getLogger` or `print` is referenced.

## 10. Test coverage

There is **no dedicated test file** for the module. A search for
`test_tick_store.py` returns nothing (`Glob tests/test_tick*` matches
zero files). Coverage is incidental to other tests:

- **`tests/test_pyth_ws.py`** — every test instantiates a real
  `TickStore` via the `_make_feed` helper at
  `tests/test_pyth_ws.py:17-24`. The tests that drive a tick to land
  in the store are:
  - `test_ingest_price_update_pushes_tick` (`:27-50`) — asserts
    `store.latest("wti")` returns the just-pushed tick with
    `seq == 1`, `n_publishers == 7`, and `ts_ns ==
    publish_time * 1_000_000_000`. This is the closest the suite
    comes to a direct unit test of `TickStore.push` and
    `TickStore.latest`.
  - `test_ingest_bare_hex_id_without_0x_prefix_normalizes` (`:93-112`)
    — also exercises `store.latest("wti")` and reads `.price`.
  - The other tests in the file exercise the parser's failure modes
    (`UnknownFeedError`, `MalformedPythMessageError`); none of them
    push to the store, so `TickStore.push` is not invoked when those
    raises trigger.
- **`tests/test_end_to_end.py`** — every test in the file constructs a
  fresh `TickStore` at `tests/test_end_to_end.py:34` and exercises a
  meaningful slice of the surface:
  - `test_end_to_end_wti_matches_bs_analytical` (`:66-88`) — the
    happy-path push-and-price; asserts `out.source_tick_seq == 1` at
    `:87`, which proves `TickRing._seq` reaches the pricer's
    provenance field.
  - `test_stale_pyth_tick_raises` (`:91-102`) — pushes a 10-second-old
    tick and expects `StaleDataError` from the pricer's staleness
    check at `engine/pricer.py:60-65`. The store's role here is just
    storing the stale `ts_ns` faithfully.
  - `test_insufficient_publishers_raises` (`:105-114`) — pushes
    `n_publishers=3` and expects `InsufficientPublishersError`. The
    store stores and returns the value verbatim; no validation kicks
    in.
  - `test_missing_tick_raises` (`:139-147`) — registers nothing, calls
    the pricer, expects `MissingStateError`. This is the only test
    that exercises the `_seq == 0` guard at `state/tick_store.py:58-59`
    via the public API (the registered-but-unprimed path; the
    unregistered-commodity raise at `:88` is *not* hit because the
    pricer registers nothing implicitly and the test does not call
    `tick_store.register` either — wait: the test does *not* call
    `tick_store.register("wti")` here. Re-reading the helper at
    `tests/test_end_to_end.py:32-48`: `_build_pricer` calls
    `tick_store.register("wti")` at line 35, so by the time
    `test_missing_tick_raises` runs the commodity *is* registered but
    the ring is empty. So the raise this test exercises is the
    `_seq == 0` branch at `state/tick_store.py:58-59`, not the
    unregistered branch at `:87-88`).
  - `test_stub_commodity_refuses_to_price` (`:150-163`) — explicitly
    calls `tick_store.register("brent")` at `:153` and pushes at
    `:155`. This exercises the late-`register` path on a commodity
    not pre-registered by the helper.
- **`tests/test_benchmarks.py`** — the budget-asserting variants of
  the latency harness. `_primed_ctx` at
  `tests/test_benchmarks.py:47-52` uses `build_full_book_pricer`,
  which constructs a `TickStore` and pushes once per synthetic market
  at `benchmarks/harness.py:89-90`. These tests measure latency
  through the store; they do not assert correctness of its data
  directly.

What is **not** tested:

- The `ValueError` raise at `state/tick_store.py:35-36` for
  `capacity <= 0`. No test instantiates `TickRing(capacity=0)` or a
  negative value.
- The `MissingStateError` raise on `push` to an unregistered commodity
  at `state/tick_store.py:81-82`. Every test calls `register` (either
  directly via `tick_store.register(...)` or implicitly through
  `PythHermesFeed.__post_init__` at `feeds/pyth_ws.py:55-58`) before
  calling `push`. The same goes for `latest` on an unregistered
  commodity at `:87-88`: every test path either pre-registers or
  drives `push` first.
- Wrap-around behaviour at the ring boundary. No test pushes more than
  the default 1,000,000 slots; `_cursor`'s modulo and the
  `(self._cursor - 1) % self.capacity` read at line 60 are never
  exercised in the wrap regime.
- The `last_seq` property at `state/tick_store.py:53-55`. No test
  reads it.
- The `commodities()` method at `state/tick_store.py:91-92`. No test
  calls it.
- The idempotency of `register` (re-registering the same commodity).
  No test calls `register` twice on the same commodity.
- Behaviour under custom (non-default) capacity. Every test relies on
  the 1,000,000 default.

**Mocking.** None. Every test uses real `TickStore` and `TickRing`
instances. There is no `unittest.mock` import in any test file that
touches the module.

## 11. TODOs, bugs, and smells

**Literal TODO/FIXME/XXX/HACK markers.** None. Grep for
`TODO|FIXME|XXX|HACK` over `state/` returns no matches.

**Structural smells, each citation-anchored.**

- **Hot-path memory is provisioned for a backtest path that doesn't
  exist.** `state/tick_store.py:34, 70` defaults capacity to one
  million ticks per commodity. The header docstring at
  `state/tick_store.py:9-11` states the rationale: "the ring history
  is here for backtest and feature-computation callers." A Grep for
  any history-reading method or attribute (`._ts_ns[`, `._price[`,
  iteration over `range(capacity)`, etc.) returns no live caller; only
  `latest()` is reached. The cartography records this independently
  at `audit/audit_A_cartography.md:276-280`.
- **Two methods are dead code today.** `TickRing.last_seq`
  (`state/tick_store.py:53-55`) and `TickStore.commodities`
  (`state/tick_store.py:91-92`) have zero callers in the live tree
  and zero tests. They are part of the public surface but unused.
- **Push input is unvalidated, in contrast with sister state
  modules.** `state/tick_store.py:44-51` accepts any `ts_ns`, any
  `price`, any `n_publishers`. `IVSurface.set_atm`
  (`state/iv_surface.py:31-34`) and `BasisModel.set`
  (`state/basis.py:29-34`) validate finiteness and positive `ts_ns`.
  Whether this is intentional (trust the upstream parser at
  `feeds/pyth_ws.py:103-115`) or an oversight is not documented in
  the module.
- **No locking despite the explicit comment about `_seq` ordering.**
  The header docstring at `state/tick_store.py:4-7` calls out the
  invariant that the seq survives ring wrap to identify the exact
  tick. The current implementation is safe only under the
  single-writer / single-reader asyncio assumption (§7). The module
  itself does not encode that assumption defensively or document it
  as a precondition for callers.
- **`LatestTick` is not frozen.** `state/tick_store.py:23` declares
  `@dataclass(slots=True)` but not `frozen=True`. Returned instances
  are mutable. No caller mutates them, but the type does not advertise
  immutability the way `TheoInputs` does (the cross-module value
  object at `models/base.py` carries `frozen=True` per the
  `engine-pricer` audit's discussion of provenance at
  `audit/audit_B_engine-pricer.md:42-45`).
- **`TickStore` has no `__slots__`, breaking symmetry with
  `TickRing`.** `state/tick_store.py:32` slots `TickRing`, but
  `state/tick_store.py:69` declares `TickStore` without slots. There
  are only two attributes (`_rings`, `_capacity`); the asymmetry is
  cosmetic but inconsistent.
- **The first push to a freshly-registered commodity always lands at
  index 0.** `_cursor = 0` at `state/tick_store.py:41`. After the first
  push, `_cursor` is 1. The empty-ring guard at line 58-59 cleanly
  separates "no push yet" from "wrapped around to index 0 again," but
  there is no per-slot timestamp guard; the slot at index 0 is
  zero-valued (timestamp 0) until written, and the only thing that
  prevents `latest()` from returning zeros is the seq-zero check.
- **`register` returns the ring object but no caller takes the
  return value.** `state/tick_store.py:74-77` types its return as
  `TickRing`. Every caller in the live tree
  (`feeds/pyth_ws.py:58`, `benchmarks/harness.py:89`,
  `tests/test_end_to_end.py:35, 153`) discards it. The return value
  is part of the public type signature but not part of any current
  contract.
- **Default ring capacity differs from the staleness budget by
  several orders of magnitude.** WTI's `pyth_max_staleness_ms = 2000`
  (`config/commodities.yaml:9`) means any tick older than two seconds
  is rejected at the pricer. The hot-path reader `latest()` only ever
  sees the most recent tick, and the pricer rejects anything older
  than 2 s; the remaining 999,999 historical ticks are unreachable
  through the public surface.
- **There is no way to deregister a commodity.** `_rings` is
  append-only (§7). For long-lived processes that occasionally swap
  a commodity in or out, the per-commodity 20 MB allocation is
  permanent for the lifetime of the `TickStore`.

## 12. Open questions

These are points the code does not reveal and that would need to be
clarified by a maintainer:

- **Is the ring history intended to be read?** The header docstring at
  `state/tick_store.py:9-11` advertises the ring as backtest-and-
  feature-computation storage, but no public method exposes a slice
  read or an iterator. Either the public API is incomplete or the
  default capacity should drop. The module does not say which.
- **Why does `TickRing` expose `last_seq` as a property when callers
  receive `seq` inside `LatestTick`?** It might exist for a future
  consumer that wants the seq without paying the `LatestTick`
  allocation cost. Today it has no caller.
- **What is the planned synchronisation story?** The module makes no
  thread-safety claim. The current callers are asyncio-coroutines
  inside one event loop, but `engine/scheduler.py` (cartography red
  flag #5) suggests a multi-task design that may eventually share the
  store across tasks. No code in `state/tick_store.py` records a
  decision about which synchronisation model is target.
- **Is the absence of input validation in `push` deliberate?** Sister
  modules validate; this one trusts. Whether the invariant "all
  pushes come from a parser that has already validated" is part of
  the contract or a happy accident is not stated.
- **Should `register` be idempotent or strict?** Today
  `state/tick_store.py:74-77` is idempotent: a second call with the
  same commodity returns the existing ring. That makes
  `feeds/pyth_ws.py:55-58` safe to call alongside an explicit
  pre-registration in benchmarks/tests, but it also silently masks a
  programmer error (e.g. registering the same commodity through two
  paths with different intended capacities — the second call is a
  no-op). The code does not say which behaviour is canonical.
- **What is the intended lifecycle of a `TickStore`?** Construction is
  cheap; destruction is implicit. There is no `close`, `flush`, or
  `reset`. Whether stores are meant to outlive a process restart, be
  recreated per session, or be shared across markets is not encoded.
- **Where is the test suite for this module supposed to live?** No
  `tests/test_tick_store.py` exists. The only direct assertions on
  `TickStore.latest` live inside `tests/test_pyth_ws.py:47, 111`,
  which conflates parser tests with state-store tests. Whether this
  is by design (the store is so thin it doesn't merit a dedicated
  file) or an oversight is not documented.
