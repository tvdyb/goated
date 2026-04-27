# Audit Phase B — `engine-scheduler`

Cross-checked against `audit/audit_A_cartography.md:223`. The Phase A
inventory row for slug `engine-scheduler` lists exactly one file,
`engine/scheduler.py`, at ~59 LoC, with external dependencies limited to
stdlib `asyncio` and `itertools`. The file in scope matches; no mismatch.
Cartography also flags this module at `audit/audit_A_cartography.md:254-257`
as Red Flag #5: "defines a `Scheduler` class but no producer submits to it.
No module imports `Scheduler` … The scheduler skeleton is unused at rest."
That observation is the central fact this Phase B deep-dive expands and
substantiates from the code.

---

## 1. Module identity

- **Files**: `engine/scheduler.py` (the only file in the module —
  `engine/__init__.py` exists but is empty per the cartography note at
  `audit/audit_A_cartography.md:209-211`, confirmed by direct read).
- **Total LoC**: 59. The file's last non-empty line is the closing
  `self._running = False` at `engine/scheduler.py:59`.
- **Summary**: A single-class skeleton of an asyncio priority-queue
  dispatcher. The module declares (a) a five-value `Priority` IntEnum
  describing the intended hot-path lane assignments
  (`engine/scheduler.py:21-26`); (b) a frozen, slotted, ordered
  `_QueueItem` dataclass that pairs an integer priority with a monotonic
  sequence id and a coroutine factory (`engine/scheduler.py:29-33`); and
  (c) a `Scheduler` class with three methods — `submit`, `run`, and
  `stop` — that wraps an `asyncio.PriorityQueue` and dispatches items in
  a single-consumer loop (`engine/scheduler.py:36-59`). The module does
  no math, holds no business state, opens no I/O, and is not imported
  anywhere outside its own file. The module-level docstring at
  `engine/scheduler.py:1-10` itself describes the file as "Deliverable 1
  ships the skeleton; the real coroutine wiring happens once
  `feeds/pyth_ws` is implemented." — a wiring step that, as documented
  in §5 below, has still not occurred even though `feeds/pyth_ws` does
  now exist.

## 2. Responsibility

Inferred from the code as written, this module solves three problems —
each only at the level of mechanism, never of policy:

1. **Provide a typed priority taxonomy for hot-path events.** The
   `Priority` IntEnum at `engine/scheduler.py:21-26` enumerates five
   named priorities — `TICK = 0`, `IV_UPDATE = 10`, `BASIS_UPDATE = 20`,
   `EVENT_CAL = 30`, `TIMER = 90` — with deliberately spaced numeric
   values (gaps of 10–60). The naming directly mirrors the four state
   sources the pricer composes per call (`engine/pricer.py:55-89`: tick,
   IV, basis, calendar) plus a generic `TIMER` lane, so the enum is the
   intended shared vocabulary between the producer side (feeds, surface
   updaters, timed jobs) and the dispatcher side. The numeric gaps
   leave room for sub-priorities (e.g. a hypothetical TICK_FAST=1)
   without renumbering existing entries; the gaps are a fact of the
   declaration, not an explicit comment.
2. **Order asynchronous repricing work strictly by priority, with
   FIFO tie-breaking.** The `_QueueItem` dataclass
   (`engine/scheduler.py:29-33`) declares `priority` first and
   `sequence` second; combined with `order=True`, dataclass-generated
   `__lt__`/`__le__` etc. compare those fields lexicographically. Since
   `submit` assigns each new item the next value from
   `itertools.count()` (`engine/scheduler.py:39, 43`), the sequence is
   monotonic and unique, so two items at the same priority always
   compare via `sequence` (lower = earlier), giving FIFO order within
   a priority. The module-level docstring's claim that the scheduler
   "guarantees ordering by priority" (`engine/scheduler.py:4-5`) is
   thereby implemented by the ordering of the first dataclass field;
   FIFO is implicit and uncommented but follows from the second.
3. **Defer coroutine creation until dispatch time.** Items carry a
   `Callable[[], Awaitable[None]]` payload — a *factory*, not an
   already-awaited coroutine
   (`engine/scheduler.py:33, 42`). `run()` invokes the factory at
   dispatch time (`engine/scheduler.py:52`: `await item.payload()`), so
   the coroutine object is constructed only when its turn comes. This
   shape sidesteps the "coroutine awaited twice" runtime error and
   means the producer can submit work synchronously without paying for
   coroutine setup at submission time.

The module is therefore a *mechanism* for prioritised dispatch; the
*policy* (which producer submits which event at which priority, and how
back-pressure or cancellation is handled) is not encoded here.

## 3. Public interface

There is no `__all__` and no `engine/__init__.py` re-export. By the
underscore-prefix convention, every name without a leading `_` is part
of the de facto public surface. In declaration order:

- **`Priority(IntEnum)`** — `engine/scheduler.py:21-26`. Members:
  `TICK=0`, `IV_UPDATE=10`, `BASIS_UPDATE=20`, `EVENT_CAL=30`,
  `TIMER=90`. As an `IntEnum`, members compare equal to their integer
  values and sort consistently against raw ints, which matters because
  `_QueueItem.priority` is typed as plain `int`
  (`engine/scheduler.py:31`) and `submit` casts the enum to `int` at
  insertion (`engine/scheduler.py:43`). No instance methods,
  no docstrings on members.
- **`Scheduler`** — `engine/scheduler.py:36-59`. Plain class (not a
  dataclass), no slots, no inheritance. Three instance attributes set
  by `__init__` (`engine/scheduler.py:37-40`):
  `_queue: asyncio.PriorityQueue[_QueueItem]`, `_seq: itertools.count`,
  and `_running: bool` initialised to `False`.
- **`Scheduler.submit(priority, coro_factory) -> None`** —
  `engine/scheduler.py:42-44`. Async method. Builds a `_QueueItem` with
  `int(priority)`, the next value of `self._seq`, and the supplied
  factory, then awaits `self._queue.put(item)`. The signature types
  `priority` as `Priority` and `coro_factory` as
  `Callable[[], Awaitable[None]]`, but Python's runtime does not
  enforce these annotations — any int-castable value would pass through
  the `int(...)` coercion at line 43.
- **`Scheduler.run() -> None`** — `engine/scheduler.py:46-56`. The
  consumer loop. Sets `self._running = True`, then in a `try/finally`
  loops while the flag is true: `await self._queue.get()`, then in a
  nested `try/finally` `await item.payload()` followed by
  `self._queue.task_done()`. The outer `finally` resets `_running` to
  `False` when the loop exits.
- **`Scheduler.stop() -> None`** — `engine/scheduler.py:58-59`.
  Synchronous. Sets `self._running = False`. There is no signal,
  cancellation, or sentinel pushed into the queue; see §7 for the
  behavioural consequence.

The internal type **`_QueueItem`** (`engine/scheduler.py:29-33`) is
prefixed with `_`, so by convention it is private; nothing imports it
outside the file (a `grep` for `_QueueItem` returns only the four
self-references inside `engine/scheduler.py`).

## 4. Internal structure

The file is essentially three blocks: imports (`engine/scheduler.py:12-18`),
the `Priority` enum (`engine/scheduler.py:21-26`), and the
`_QueueItem` + `Scheduler` pair (`engine/scheduler.py:29-59`). There are
no module-level constants beyond the enum, no helper functions, no
context managers, and no fixtures.

`_QueueItem` is the load-bearing data structure. Its decorator chain
`@dataclass(frozen=True, slots=True, order=True)`
(`engine/scheduler.py:29`) does four things:

1. **`frozen=True`** — fields cannot be reassigned after construction.
   Combined with `slots=True`, also makes instances hashable (the
   dataclass generates `__hash__` only when frozen). This matters
   because `asyncio.PriorityQueue` uses a heap and may re-insert items
   on contention; immutability prevents an attacker (or a buggy
   producer) from mutating priority mid-queue.
2. **`slots=True`** — generates `__slots__` from the field names
   (`priority`, `sequence`, `payload`), removing `__dict__` and shaving
   memory per item. Relevant if the queue ever grows large; not
   measurable today because the queue is empty.
3. **`order=True`** — generates `__lt__`, `__le__`, `__gt__`, `__ge__`
   from the field tuple `(priority, sequence, payload)` in declaration
   order. This is the mechanism that makes the priority-queue work:
   `asyncio.PriorityQueue` heap-sorts items by their natural ordering,
   which here means "lower priority value first, then lower sequence
   first." The `payload` field is also part of the comparison tuple,
   but Python only reaches it if the first two fields tie — which
   they cannot, because `sequence` is sourced from
   `itertools.count()` and is therefore unique per queue. The payload's
   default object equality is therefore never exercised by the heap.
4. **default `eq=True`** (implied by `order=True`) — generates `__eq__`
   from the same field tuple. Two `_QueueItem`s are equal only when all
   three fields are equal; sequence uniqueness again means equality is
   only possible against the same instance.

The data flow inside `Scheduler` is:

```
external producer
   └─► await scheduler.submit(priority, coro_factory)
        └─ _QueueItem(int(priority), next(self._seq), coro_factory)
             └─ await self._queue.put(item)

scheduler.run()  (own asyncio task)
   loop while self._running:
        item = await self._queue.get()       # blocks if empty
        try:
            await item.payload()              # runs the user coroutine
        finally:
            self._queue.task_done()           # always marks completion
```

The notable algorithmic choice is that `submit` is `async` even though
its body is a one-liner around a non-blocking put. `asyncio.PriorityQueue`
becomes blocking only when a `maxsize` is set; the queue here is
constructed with no argument (`engine/scheduler.py:38`), so its default
maxsize of 0 (i.e. unbounded) means `put` never blocks. The `await`
keyword therefore yields control to the event loop opportunistically
but never suspends on capacity. There is no observable evidence in the
file that this was an intentional design choice or simply mirroring the
PriorityQueue API.

There are no loops outside `run()`, no retries, no batching, no
back-pressure, and no observability hooks (no logging, no metrics, no
counters). The module is purely a queue + dispatcher.

## 5. Dependencies inbound

Searches:

- `Grep "from engine.scheduler|engine\.scheduler|import scheduler"` over
  the repo returns one hit, in
  `audit/audit_A_cartography.md:256` — the cartography itself
  describing the absence. No Python file imports anything from
  `engine.scheduler`.
- `Grep "Scheduler|Priority"` over `*.py` returns hits only inside
  `engine/scheduler.py` itself; the `Priority`/`Scheduler` symbols are
  unused elsewhere in the source tree (other `priority` matches are in
  Markdown research docs and unrelated to the type).
- `Grep "scheduler|Scheduler"` over `tests/` returns no matches; over
  `benchmarks/` returns no matches.
- `submit|TICK|IV_UPDATE|BASIS_UPDATE|EVENT_CAL|TIMER|_QueueItem`
  references are confined to `engine/scheduler.py` (and to two
  tangential mentions in research Markdown that have nothing to do
  with this module).

The inbound surface is therefore **empty**. No producer pushes to the
queue and no consumer task wraps `run()`. The module is dead code at
the import graph level. This corroborates the cartography flag at
`audit/audit_A_cartography.md:254-257`.

The textual dependents of the file's *intent* are:

- The module docstring at `engine/scheduler.py:8-9` references
  `feeds/pyth_ws` as the producer-to-be: "the real coroutine wiring
  happens once `feeds/pyth_ws` is implemented." `feeds/pyth_ws.py`
  exists and is implemented today (`feeds/pyth_ws.py:1-145`), but its
  ingestion path goes directly to the tick store
  (`feeds/pyth_ws.py:117`: `seq = self.tick_store.push(...)`), bypassing
  the scheduler entirely. The doc-string's stated precondition has been
  met without the corresponding wiring step ever taking place.
- The `engine/pricer.py` hot path
  (`engine/pricer.py:45-90`) is synchronous (no `async def`) and is
  invoked directly by tests and benchmarks
  (`audit/audit_B_engine-pricer.md:140-158` lists every call site). The
  pricer is therefore not dispatched through the scheduler today;
  whether a future wiring step would call `pricer.reprice_market` from
  inside a coroutine submitted at `Priority.TICK` is implied by the
  module docstring at `engine/scheduler.py:3-4` ("Ticks reprice
  immediately (priority 0)") but not demonstrated by code.

## 6. Dependencies outbound

The module imports (`engine/scheduler.py:12-18`) only from the standard
library:

- **`asyncio`** (line 14) — `asyncio.PriorityQueue` is the only
  attribute used (`engine/scheduler.py:38`). No `asyncio.Lock`, `Event`,
  `Task`, `Future`, or `gather` appears anywhere in the file.
- **`itertools`** (line 15) — used solely for `itertools.count()` at
  `engine/scheduler.py:39, 43`. The counter's default start (0) and
  step (1) are accepted; no arguments are passed.
- **`collections.abc.Awaitable, Callable`** (line 16) — typing-only;
  `Awaitable` and `Callable` appear only in the `_QueueItem.payload`
  annotation at line 33 and the `submit` parameter annotation at
  line 42.
- **`dataclasses.dataclass`** (line 17) — applied to `_QueueItem`
  (`engine/scheduler.py:29`).
- **`enum.IntEnum`** (line 18) — base class for `Priority`
  (`engine/scheduler.py:21`).
- **`__future__.annotations`** (line 12) — defers annotation
  evaluation. The forward reference inside
  `asyncio.PriorityQueue[_QueueItem]` (`engine/scheduler.py:38`) is
  parsed-but-not-evaluated as a result; without this import, the
  subscripted generic on a runtime class would still work in Python
  3.11 but the file's annotation style would be inconsistent with the
  rest of the repo (`engine/pricer.py:15`, `feeds/pyth_ws.py:22` etc.
  also use the `from __future__ import annotations` pragma).

There are **no third-party imports** in this file. There are **no
intra-repo imports**. There is no network I/O, no filesystem I/O, no
subprocesses, no logging, no environment variable access, and no
configuration reads. The module's outward surface is purely the stdlib
asyncio dispatch primitives.

## 7. State and side effects

Per-instance state on a `Scheduler` (`engine/scheduler.py:37-40`):

- `_queue: asyncio.PriorityQueue[_QueueItem]` — heap-backed unbounded
  queue. Mutated by `submit` (put, line 44) and `run` (get, line 50;
  task_done, line 54).
- `_seq: itertools.count` — monotonic counter consumed only by `submit`
  (`engine/scheduler.py:43`). Each `next()` call is O(1) and
  thread-unsafe — but `asyncio` is single-threaded by default, so
  thread-safety is irrelevant under the standard event loop.
- `_running: bool` — flips True on entry to `run`
  (`engine/scheduler.py:47`), back to False on exit
  (`engine/scheduler.py:56`), and synchronously to False inside
  `stop()` (`engine/scheduler.py:59`).

There is **no module-level mutable state**. There is no global
mutation, no class-level singleton, no caches, no metrics counters.

In-process side effects per call:

- `submit`: one `_QueueItem` allocation
  (`engine/scheduler.py:43`), one heap-push inside the asyncio
  PriorityQueue, and one `next()` advance on `_seq`. No I/O.
- `run`: one heap-pop per iteration, then whatever the user's `payload`
  coroutine itself does — which is the boundary at which any real I/O
  would happen, none of which is owned by this module.
- `stop`: one boolean assignment.

Ordering assumptions implicit in the design:

- The `run()` loop relies on `self._running` reflecting the desired
  consume/stop state *between* iterations
  (`engine/scheduler.py:49`). When `run()` is currently blocked on
  `await self._queue.get()` (line 50), a synchronous `stop()` call
  sets `_running = False`, but the consumer does not re-check the
  flag until *after* `get()` returns — i.e. until at least one more
  item is delivered. The behaviour at "stop while idle" is therefore
  "stop takes effect on the next item, not immediately." There is no
  cancellation token, no sentinel push, and no `_queue.put_nowait(...)`
  inside `stop()` to unblock the get. The code does not document this;
  the behaviour is observable only from the structure.
- `task_done()` is called inside a `finally` block
  (`engine/scheduler.py:51-54`), so it runs even when the user
  coroutine raises. The exception, however, is **not** caught — it
  propagates out of `run()` and the outer `finally` then sets
  `_running = False` (`engine/scheduler.py:55-56`). The class therefore
  treats any payload exception as fatal to the consumer; there is no
  retry, no error log, no isolation between items.
- The dispatcher is single-consumer by construction. Nothing in the
  file prevents a caller from running two `run()` coroutines on the
  same instance, but doing so would have both consumers racing on the
  same queue, with the shared `_running` flag oscillating
  unpredictably. There are no asserts or guards against this.

There are no ordering assumptions about producer/consumer startup
sequencing. `submit` works whether or not a consumer is running; items
simply queue. If `run()` is never awaited, items pile up indefinitely
in `self._queue` until the process exits.

## 8. Invariants

Each item below is a property the code as written depends on, with the
citation that establishes it.

1. **Priority sort key is the IntEnum's integer value.** `_QueueItem`
   stores `priority: int` (`engine/scheduler.py:31`) and `submit`
   coerces with `int(priority)` (`engine/scheduler.py:43`). The
   `IntEnum` base (`engine/scheduler.py:21`) guarantees that
   `int(Priority.TICK) == 0` and so on. The heap therefore orders by
   the enum's numeric value, not by enum-member-name or insertion
   order.
2. **Ties on priority always break by sequence.** With
   `dataclass(order=True)` at `engine/scheduler.py:29`, comparison
   goes through the field tuple `(priority, sequence, payload)`.
   Because `sequence = next(self._seq)` (line 43) draws from
   `itertools.count()` (line 39) and is unique per `submit` call, two
   items with the same `priority` always differ in `sequence`, so the
   `payload` field is never compared. The "FIFO within priority"
   property follows from the monotonicity of the counter.
3. **Items are immutable after construction.** `frozen=True` at
   `engine/scheduler.py:29` means a producer cannot post-construction
   re-aim a `_QueueItem` at a different coroutine factory or change
   its priority. The heap's invariant is preserved.
4. **The priority queue is unbounded.** `asyncio.PriorityQueue()` is
   constructed without `maxsize` at `engine/scheduler.py:38`, so
   `put` never blocks on capacity. `submit` (`engine/scheduler.py:42-44`)
   relies on this — its `await self._queue.put(item)` would otherwise
   become a back-pressure point.
5. **`task_done()` is called once per item, even on payload failure.**
   The inner `try/finally` at `engine/scheduler.py:51-54` runs
   `task_done()` whether `payload()` returns or raises. Any consumer
   doing `await self._queue.join()` (none today) would therefore
   complete on payload failures as well.
6. **`run()` is not re-entrant safe.** The flag `_running` is a single
   boolean (`engine/scheduler.py:40`). If two `run()` coroutines were
   started concurrently on the same instance, the second would set the
   flag to `True` again immediately, but neither would observe the
   other's state. The design assumes a single consumer task; this is
   not asserted but is the only state model under which `_running`'s
   semantics are coherent.
7. **`stop()` is advisory, not preemptive.** The flag is checked only
   between `get()` and the next iteration's `await get()` — see
   `engine/scheduler.py:49-50`. A `stop()` call while the consumer is
   blocked on `get()` does not unblock it. The module relies on the
   producer to push a sentinel item or for the event loop to be torn
   down externally if a stop must take effect immediately.
8. **`submit` is callable from any coroutine on the same loop.**
   `asyncio.PriorityQueue.put` requires that all access happen on the
   same event loop where the queue was constructed. The class does not
   bind a specific loop; it relies on Python's "current running loop"
   resolution at the time the method is awaited. No comment documents
   this; it is a property of the underlying `asyncio.Queue` family.
9. **Coroutines are constructed lazily.** The payload field is typed
   `Callable[[], Awaitable[None]]` (`engine/scheduler.py:33`), and
   `run()` invokes it as `await item.payload()`
   (`engine/scheduler.py:52`). The producer therefore submits
   *factories*, not pre-awaited coroutine objects, so re-submission
   (or never-awaiting) does not produce an "awaited twice" or
   "coroutine never awaited" warning at the queue level.
10. **Priority values fit in a CPython small-int range.** The largest
    declared value is `TIMER = 90` (`engine/scheduler.py:26`); cast to
    `int` at submission, the value is well within the standard heap
    comparator's regime. No invariant on numeric range is asserted —
    callers could submit `Priority(-1)` or any int — but the declared
    enum confines the contract to non-negative small integers.
11. **No coroutine leaks on `stop()`.** Because `stop()` only flips a
    flag (`engine/scheduler.py:58-59`) and does not drain the queue,
    items remaining in `_queue` after `run()` exits are never
    dispatched. Their `payload` callables are dropped along with the
    `Scheduler` instance when garbage-collected. None of these are
    ever-awaited coroutine objects (see invariant 9), so no "coroutine
    was never awaited" RuntimeWarning fires.

## 9. Error handling

The module catches **nothing**. There is no `except` clause anywhere in
`engine/scheduler.py`; `try/finally` is used twice
(`engine/scheduler.py:48-56`, `engine/scheduler.py:51-54`) but only to
guarantee state cleanup, not to suppress exceptions.

By call site:

- **`submit`** (`engine/scheduler.py:42-44`) — the body has three
  failure surfaces. (a) `int(priority)` raises `TypeError` if a
  non-int-castable value is supplied; the type hint declares
  `Priority`, but Python does not enforce it at runtime. (b)
  `next(self._seq)` is infallible. (c)
  `await self._queue.put(item)` is non-blocking on an unbounded queue
  but can raise `RuntimeError` if no event loop is running. None of
  these are caught.
- **`run`** (`engine/scheduler.py:46-56`) — three failure surfaces.
  (a) `await self._queue.get()` raises `asyncio.CancelledError` if the
  consumer task is cancelled; the loop has no special handling for
  this, so cancellation propagates through both `finally` blocks
  (resetting `_running` to `False`) and out of `run()`. (b)
  `await item.payload()` may raise anything the user coroutine
  raises. The inner `finally` still calls `task_done()` before the
  exception propagates. (c) `task_done()` itself raises `ValueError`
  if called more times than items were `get`-ed; that cannot happen on
  this code path because each iteration matches one get with one
  task_done.
- **`stop`** (`engine/scheduler.py:58-59`) — infallible.

The net policy is: payload exceptions are fatal to the consumer
(`run()` returns to its caller with the exception unwrapped), but
queue-level invariants (`task_done()` accounting, `_running` reset) are
preserved via `finally`. There is no logging of the exception, no
quarantine of the offending item (it is already removed from the queue
by the `get`), and no mechanism to restart `run()` automatically.

There is also no signalling for the empty-queue case. `await
self._queue.get()` blocks forever on an empty queue, regardless of
`_running`'s state; this is the source of the "stop is advisory"
behaviour noted in invariant 7.

## 10. Test coverage

`Grep "scheduler|Scheduler"` over `tests/` returns **zero matches**.
There is no `tests/test_scheduler.py`, no fixture, no parametric test,
no property-based hypothesis test against this module. The Phase A
cartography enumerates the test files at
`audit/audit_A_cartography.md:171-184`; none of them target
`engine/scheduler.py`.

Indirect coverage through other modules is also absent:

- `tests/test_end_to_end.py` constructs a `Pricer` and exercises
  `reprice_market` synchronously (per `audit/audit_B_engine-pricer.md:365-410`).
  No `Scheduler` is instantiated; no `submit`/`run` invocation
  occurs.
- `tests/test_benchmarks.py` runs the same `reprice_market` path
  through `benchmarks/run.py`. The harness at
  `benchmarks/harness.py:97-104` (per the cartography summary at
  `audit/audit_A_cartography.md:226`) builds a `Pricer` directly; it
  does not use the scheduler.
- `tests/test_pyth_ws.py` exercises Hermes message parsing without
  network I/O; the feed pushes to `tick_store` directly
  (`feeds/pyth_ws.py:117`) and never touches the scheduler.

Nothing is mocked because nothing is tested. The module is unverified
behaviourally; the only validation it has received is whatever
`ruff`/`mypy` static checks the project runs (the `pyproject.toml`
ruff config at `audit/audit_A_cartography.md:42-44` lists an `E,F,W,I,N,UP,B,SIM,PL`
rule set). There is no coverage tooling configured per
`audit/audit_A_cartography.md:168-170`.

## 11. TODOs, bugs, and smells

`Grep "TODO|FIXME|XXX|HACK"` against `engine/scheduler.py` returns no
literal markers. The module-level docstring at
`engine/scheduler.py:8-9` *is* a deferred-work flag in prose form —
"Deliverable 1 ships the skeleton; the real coroutine wiring happens
once `feeds/pyth_ws` is implemented." — without a TODO tag. As of the
audited tree, `feeds/pyth_ws.py` is implemented
(`feeds/pyth_ws.py:1-145`) but the wiring step the docstring promised
remains undone; the file's stated "next step" has not happened.

Structural observations, each with citation:

- `engine/scheduler.py:5-6` — the module docstring concedes "is not
  used in the GBM inner math — see `engine/pricer.py` for the hot
  path." Combined with the inbound-search results in §5, this is
  consistent with the module being entirely off the live pricing path
  today.
- `engine/scheduler.py:36-59` — the `Scheduler` class is not a
  dataclass and does not declare `__slots__`. Every other class in the
  module under audit uses one or the other (the related
  `_QueueItem` does both at line 29; the pricer uses
  `dataclass(slots=True)` at `engine/pricer.py:36`). The inconsistency
  means `Scheduler` instances carry a `__dict__` and are
  monkey-patchable, which is at odds with the stylistic convention
  elsewhere.
- `engine/scheduler.py:42-44` — `submit` is `async def` but its body
  is a single `await` on an unbounded queue's `put`. On an
  `asyncio.PriorityQueue` constructed without `maxsize`
  (`engine/scheduler.py:38`), `put` is non-blocking; the `await`
  yields the event loop opportunistically but never suspends. The
  function could be a regular `def submit(...): self._queue.put_nowait(...)`
  and behave identically; the `async`-ness is overhead. This is a
  smell, not a bug.
- `engine/scheduler.py:43` — `int(priority)` strips the IntEnum
  identity at insertion. Anything ordered correctly by integer
  comparison passes; an exotic `Priority` subclass could be silently
  flattened. There are no IntEnum subclasses defined in the codebase,
  so this is theoretical today.
- `engine/scheduler.py:46-56` — `run()` has no graceful-shutdown
  pathway. With `stop()` flipping a flag that is only checked between
  iterations (`engine/scheduler.py:49`), and no sentinel push or
  cancellation in `stop()` (`engine/scheduler.py:58-59`), an idle
  consumer awaiting `get()` will not exit until at least one more
  item is pushed. A maintainer who reads only `stop()`'s name would
  reasonably expect immediate termination; the code does not deliver
  that.
- `engine/scheduler.py:46-56` — `run()` does not catch payload
  exceptions. Any user coroutine that raises kills the consumer loop.
  Without logging or supervisor logic, the operator has no diagnostic
  trail beyond the unhandled traceback. Compare to
  `feeds/pyth_ws.py:138-145` where the equivalent reconnect loop logs
  and retries.
- `engine/scheduler.py:38` — `_queue` is unbounded. There is no
  `maxsize` argument and no back-pressure at the producer side. A
  pathologically slow consumer (or a stopped consumer that never
  drains) accepts items indefinitely until process memory is
  exhausted. Today there is no producer, so the practical risk is
  zero; structurally, the property is worth flagging.
- The `Priority` enum at `engine/scheduler.py:21-26` has no entries
  for `tick_publisher_floor_breach`, `quote_cancel`, `risk_kill`, or
  similar safety-class events the README's "non-negotiables"
  (`README.md:59-66`) imply will exist. The enum's five entries are a
  shape, not a complete taxonomy; this is a Phase D question, but
  worth noting that the enum is sized to the named state surfaces
  enumerated in the pricer (`engine/pricer.py:55-89`) and nothing
  more.
- The file has no logging, no metrics, no observability hooks. The
  rest of the runtime tree at least imports `logging` (e.g.
  `feeds/pyth_ws.py:26, 31`); `engine/scheduler.py` does not. A
  production scheduler would conventionally emit per-item dispatch
  latency, queue depth, and exception traces. None are present.
- The module is dead at the import graph, per §5. Cartography raises
  this as Red Flag #5 (`audit/audit_A_cartography.md:254-257`); the
  Phase B verification confirms zero inbound imports beyond the
  cartography document itself.

## 12. Open questions

Things the code does not reveal that would need to be confirmed by a
maintainer:

1. **Is the scheduler intended to dispatch a synchronous `Pricer`?**
   `Pricer.reprice_market` is synchronous
   (`audit/audit_B_engine-pricer.md:50-79`), but the queue stores
   `Awaitable[None]` factories
   (`engine/scheduler.py:33`). The intended adapter pattern — a
   coroutine that wraps a sync call, perhaps via
   `asyncio.to_thread` — is not present anywhere in the repo. The
   docstring at `engine/scheduler.py:3-4` says ticks reprice
   "immediately (priority 0)," but the call shape is unspecified.
2. **Is `stop()`'s advisory semantics deliberate or oversight?** The
   `stop`-while-idle behaviour (consumer remains blocked on `get()`
   until the next push) is a structural fact
   (`engine/scheduler.py:46-59`) but uncommented. A maintainer might
   intend (a) preemptive cancellation via the consumer task, (b) a
   sentinel-push pattern, or (c) accept that "stop" is best-effort.
3. **What is the expected concurrency model for `submit`?** The class
   does not bind to a specific event loop and assumes a single-loop
   asyncio model. Whether producers from threads
   (e.g. a synchronous Pyth callback bridging into asyncio via
   `loop.call_soon_threadsafe`) are expected to use
   `submit` is unclear — and `submit` is `async`, which would
   require those producers to schedule the coroutine onto the loop
   themselves.
4. **Are `Priority` numeric gaps reserved, and what for?** The enum
   spaces values at 0/10/20/30/90
   (`engine/scheduler.py:21-26`). The gaps suggest planned
   intermediate priorities (e.g. a `TICK_AGGREGATOR=5` between TICK
   and IV_UPDATE), but no comment specifies the reservation policy.
5. **What should happen when a payload raises?** Today it kills the
   consumer (`engine/scheduler.py:46-56`). The README's
   "non-negotiables" list at `README.md:59-66` explicitly endorses
   "no silent failures," which is consistent with letting the
   exception propagate — but a real dispatcher typically isolates
   per-item failures so one bad coroutine does not stop all theo
   updates. Whether the current "fatal to consumer" is the desired
   policy or a placeholder is not in the file.
6. **Is the queue meant to be drained on `stop()`?** Items left in
   `_queue` after `stop()` are silently dropped along with the
   `Scheduler` instance (see invariant 11). A maintainer might intend
   draining behaviour; the code does not implement it.
7. **Why was the wiring step deferred — and indefinitely?** The
   docstring at `engine/scheduler.py:8-9` ties the wiring to
   `feeds/pyth_ws` being implemented. That dependency is now satisfied
   (`feeds/pyth_ws.py:1-145`), yet `feeds/pyth_ws.py:117` pushes
   directly to the tick store rather than scheduling a tick coroutine.
   Whether the scheduler is now redundant by intent (the synchronous
   pricer is fast enough — see latency table at `README.md:13-19`,
   p99 around 18 µs) or simply waiting for the next deliverable is a
   maintainer question.
8. **Is there a contract for back-pressure?** With an unbounded queue
   (`engine/scheduler.py:38`) and a single consumer
   (`engine/scheduler.py:46-56`), the system has no back-pressure.
   Whether producers are expected to self-throttle (drop on coalesce,
   for example, when many TICKs land back-to-back) or whether
   unbounded queueing is acceptable at design time is undocumented.
