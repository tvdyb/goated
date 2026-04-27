# Audit Phase B — `feeds-pyth`

Module slug per Phase A inventory: `feeds-pyth` (`audit/audit_A_cartography.md:215`). The
Phase A row lists this module's files as `feeds/pyth_ws.py` and `feeds/__init__.py`
(`audit/audit_A_cartography.md:215`); both files exist and are the entire module
boundary on disk. The companion config `config/pyth_feeds.yaml` is owned by the
`config` module per Phase A (`audit/audit_A_cartography.md:227`) and is treated
here as configuration the feed expects to be handed, not as part of the module.

This document describes only what the code does today.

---

## 1. Module identity

Files in scope:

- `feeds/pyth_ws.py` — 145 lines (final newline at line 145, last code line at 145
  is `await asyncio.sleep(self.reconnect_backoff_s * attempt)`,
  `feeds/pyth_ws.py:145`).
- `feeds/__init__.py` — 1 line (the file exists but reads as empty per the Read
  tool's "shorter than the provided offset" response when offset 1 is requested).

Total module LoC ≈ 145, matching the Phase A row
(`audit/audit_A_cartography.md:215`, "Approx LoC 145"). The Phase A row
under-states the file count because it counts `__init__.py` as part of the
module without adding lines for it.

One-paragraph summary. The `feeds-pyth` module is a single-file asynchronous
WebSocket client for Pyth's Hermes streaming endpoint
(`feeds/pyth_ws.py:1-20`). It defines a `PythHermesFeed` dataclass that owns a
subscription set and a `TickStore` reference, parses Hermes `price_update`
JSON messages into `(ts_ns, price, num_publishers)` triples, and pushes those
triples into the per-commodity tick ring buffer
(`feeds/pyth_ws.py:46-118`). It also defines an `async def run()` loop that
opens a WebSocket, sends a JSON `subscribe` frame, and dispatches every inbound
JSON frame through the same parser, with a bounded reconnect budget
(`feeds/pyth_ws.py:120-145`). Three module-local exceptions
(`PythFeedError`, `UnknownFeedError`, `MalformedPythMessageError`) carry every
failure surface (`feeds/pyth_ws.py:34-43`). The package's `feeds/__init__.py`
is empty, so import is via the submodule path `feeds.pyth_ws`.

## 2. Responsibility

Inferred from code behaviour, the module's job is to be the only producer of
Pyth ticks in the system. It accepts a configured map from Hermes feed ID
(hex string) to internal commodity name (`feeds/pyth_ws.py:48-49`), registers
each commodity with the `TickStore` at construction time
(`feeds/pyth_ws.py:55-58`), and from then on it is responsible for translating
every wire-format `price_update` into a tick that downstream consumers see via
`TickStore.latest()` and via the monotonically-increasing `seq` integer the
ring returns (`feeds/pyth_ws.py:117`, `state/tick_store.py:44-51`).

The docstring states three failure modes explicitly:

> Failure modes the feed raises on (never silently swallows):
>
>   * connection failure after retry budget
>   * subscribed-feed message for an unknown feed id
>   * malformed message (missing price or publish_time)
> (`feeds/pyth_ws.py:13-16`)

The code matches that contract: each branch in `ingest_message` either pushes a
tick, returns `None` for non-`price_update` frames, or raises
(`feeds/pyth_ws.py:79-118`). There is no path that drops a `price_update`
silently. The docstring also explicitly notes that per-publisher gaming detection
"lives at the Pythnet/Solana RPC level, not Hermes" and is out of scope for this
deliverable; the feed exposes only the aggregate publisher count
(`feeds/pyth_ws.py:8-11`).

## 3. Public interface

Module-level public symbols (as importable from `feeds.pyth_ws`):

- `PythFeedError(RuntimeError)` — base class for every feed failure.
  Signature: zero-arg subclass of `RuntimeError`. (`feeds/pyth_ws.py:34-35`)
- `UnknownFeedError(PythFeedError)` — raised when a `price_update` arrives
  with a `price_feed.id` that is not in the subscription table.
  (`feeds/pyth_ws.py:38-39`, raised at `feeds/pyth_ws.py:97`)
- `MalformedPythMessageError(PythFeedError)` — raised on non-dict messages,
  missing `price_feed`, missing string `id`, missing `price` block, or any
  parse failure on `price`/`expo`/`publish_time`. Also raised by `run()` on
  non-JSON frames. (`feeds/pyth_ws.py:42-43`, raised at `:80, :86, :89, :101,
  :108, :136`)
- `PythHermesFeed` — the dataclass entry point. Fields:
  `endpoint: str`, `feed_id_to_commodity: dict[str, str]`,
  `tick_store: TickStore`, `reconnect_backoff_s: float = 1.0`,
  `max_reconnects: int = 5`, plus a private `_subscribed: list[str]`
  initialised in `__post_init__` (`feeds/pyth_ws.py:46-58`).
  Methods:
    - `ingest_message(self, msg: dict) -> tuple[str, int] | None` — parse one
      message and (on a `price_update`) push one tick; returns
      `(commodity, seq)` on success, `None` for any non-`price_update` frame.
      Raises `MalformedPythMessageError` or `UnknownFeedError` per the
      docstring (`feeds/pyth_ws.py:60-118`).
    - `async run(self) -> None` — connect, subscribe, dispatch, reconnect up
      to `max_reconnects` times before raising `PythFeedError`
      (`feeds/pyth_ws.py:120-145`).

There are no other module-level constants, factories, or functions.
`feeds/__init__.py` is empty, so the package re-exports nothing.

## 4. Internal structure

Data flow through `ingest_message`, top to bottom (`feeds/pyth_ws.py:60-118`):

1. Type guard on the incoming `msg`; non-dict raises
   `MalformedPythMessageError` (`:79-80`).
2. Type filter: any non-`price_update` returns `None` without error
   (`:81-82`). This is the only branch that returns `None`.
3. Extract `price_feed` block; non-dict raises (`:84-86`).
4. Extract feed id; non-string raises (`:87-89`).
5. Normalise feed id by prefixing `0x` if missing (`:91-92`). Then look up
   the normalised id first, then the raw id, in the subscription map
   (`:93-95`). Unknown id raises `UnknownFeedError` (`:96-97`).
6. Extract `price` block; non-dict raises with the resolved commodity in the
   message (`:99-101`).
7. Parse the three integers (`price`, `expo`, `publish_time`) inside a
   `try`/`except (KeyError, TypeError, ValueError)` that re-raises as
   `MalformedPythMessageError` with `from exc` chaining (`:103-108`).
8. Convert: `price = raw_price * (10.0 ** expo)` and
   `ts_ns = publish_time * 1_000_000_000` (`:110-111`).
9. Read `num_publishers` with a fallback default of `0` and an inline comment
   noting the field is "surfaced inconsistently" by Hermes (`:112-115`).
10. Push to the ring and return `(commodity, seq)` (`:117-118`).

`run()` is structurally simple (`feeds/pyth_ws.py:120-145`):

- Imports `websockets` at function scope so unit tests do not need the
  dependency installed (`:123`, see also `feeds/pyth_ws.py:18-19` and
  cartography red flag #15 at `audit/audit_A_cartography.md:302-306`).
- Opens an outer `while True` loop containing a `try` whose body opens an
  `async with websockets.connect(self.endpoint)` context, resets `attempt = 0`
  inside the connect (`:128-129`), sends the subscribe frame (`:130`), logs at
  `info` level (`:131`), and iterates `async for raw in ws` decoding each
  frame as JSON (`:132-137`).
- Non-JSON frames raise `MalformedPythMessageError` from inside the loop —
  this propagates out of the `async with` and out of the `try`, so the
  reconnect block does **not** catch it (the `except` clause filters on
  `OSError, asyncio.TimeoutError`, `:138`). The message-parse error is
  therefore terminal for `run()`.
- On `OSError` or `asyncio.TimeoutError`, increments `attempt`, raises
  `PythFeedError` once `attempt > self.max_reconnects` (`:139-143`), else
  logs and sleeps `reconnect_backoff_s * attempt` (`:144-145`). Backoff is
  linear, not exponential.

Notable algorithmic facts:

- The subscribe-frame id list is sorted at construction
  (`feeds/pyth_ws.py:55-58`: `self._subscribed = sorted(self.feed_id_to_commodity)`).
  The sort is over the keys of `feed_id_to_commodity`, i.e. the hex feed ids
  exactly as the caller passed them — no `0x` normalisation is applied to the
  outbound subscription frame.
- The `0x` normalisation in the parse path tries the prefixed key first, then
  the bare key (`feeds/pyth_ws.py:92-95`). A `tests/test_pyth_ws.py:93-111`
  case exercises the bare-id path explicitly.
- The push call returns the post-increment `seq` from `TickRing.push`
  (`state/tick_store.py:44-51`), which is the value `ingest_message` returns
  to its caller. This is the same integer that ends up in `TheoOutput`'s
  `source_tick_seq` provenance field downstream (`engine/pricer.py:85`).

## 5. Dependencies inbound

Search for every importer of the module
(`Grep "feeds.pyth_ws|from feeds|PythHermesFeed|UnknownFeedError|MalformedPythMessageError|PythFeedError|ingest_message|pyth_ws"` over the repo,
results captured during this audit):

- `tests/test_pyth_ws.py:7-11` — imports `MalformedPythMessageError`,
  `PythHermesFeed`, `UnknownFeedError`. Constructs a feed with
  `endpoint="wss://test.invalid"` (`tests/test_pyth_ws.py:19-23`) and exercises
  `ingest_message` directly.
- `benchmarks/run.py:25` — imports `PythHermesFeed`. Constructs one with
  `endpoint="wss://unused.invalid"` and a single-commodity map built from the
  registry's `pyth_feed_id` field (`benchmarks/run.py:146-150`). Calls
  `feed.ingest_message(tmpl)` inside the timed loop (`benchmarks/run.py:169`).

That is the complete set of inbound importers in the source tree. In
particular:

- No production runtime entry point imports `PythHermesFeed`. There is no
  `main`, no CLI, no service module that wires the feed to the `Pricer`.
  Cartography corroborates this at `audit/audit_A_cartography.md:98-100`.
- `engine/scheduler.py:9` mentions `feeds/pyth_ws` in a comment ("the real
  coroutine wiring happens once feeds/pyth_ws is implemented"), but the
  scheduler does not import the feed and is itself unused
  (`audit/audit_A_cartography.md:254-257`).
- The Phase B engine-pricer audit notes that `bench_tick_to_theo` "pairs
  `feed.ingest_message` with `pricer.reprice_market`"
  (`audit/audit_B_engine-pricer.md:419`); that pairing is the only place the
  two modules are composed in the same call path.

## 6. Dependencies outbound

Imports at the top of `feeds/pyth_ws.py:22-29`:

- Stdlib: `asyncio` (used by `run()` for `asyncio.TimeoutError`,
  `asyncio.sleep`, `feeds/pyth_ws.py:138, 145`); `json` (used for both
  encoding the subscribe frame and decoding inbound frames,
  `feeds/pyth_ws.py:130, 134`); `logging` (a module-level logger named
  `goated.feeds.pyth`, `feeds/pyth_ws.py:31`); `dataclasses.dataclass` and
  `dataclasses.field` (the `PythHermesFeed` dataclass and its private list
  field, `feeds/pyth_ws.py:46-53`).
- Intra-repo: `from state.tick_store import TickStore`
  (`feeds/pyth_ws.py:29`). The feed touches only `tick_store.register(...)`
  (`feeds/pyth_ws.py:58`, see `state/tick_store.py:74-77`) and
  `tick_store.push(...)` (`feeds/pyth_ws.py:117`, see
  `state/tick_store.py:79-83`). It never reads from the store.
- Lazy import: `import websockets` inside `run()`
  (`feeds/pyth_ws.py:123`). The package is declared as a hard runtime
  dependency at `pyproject.toml:15` ("websockets >= 12.0", paraphrased from
  `audit/audit_A_cartography.md:21`), and the inline comment explains why
  the import is lazy: "imported lazily so tests don't need the dep"
  (`feeds/pyth_ws.py:123`).

External services contacted:

- Pyth Hermes WebSocket. The module never hard-codes a URL — it receives the
  `endpoint` string at construction (`feeds/pyth_ws.py:48`). The deployed
  endpoint comes from `config/pyth_feeds.yaml:7`
  (`hermes_endpoint: "wss://hermes.pyth.network/ws"`). The HTTP/SSE fallback
  at `config/pyth_feeds.yaml:8` is never read by this module — there is no
  `httpx`/`requests`/`urllib` import here (Grep confirms: no `httpx` import in
  the repo at all; cartography red flag #3 at
  `audit/audit_A_cartography.md:246-249`).
- Subscription payload shape: `{"type": "subscribe", "ids": [...]}` at
  `feeds/pyth_ws.py:130`.
- Inbound message type consumed: `price_update` at `feeds/pyth_ws.py:81`. Any
  other `type` returns `None` (no `heartbeat` handling, no `pong`). Hermes'
  documented `price_update` shape is mirrored inline in the docstring at
  `feeds/pyth_ws.py:64-77`.

## 7. State and side effects

In-process state owned by the module:

- The `_subscribed: list[str]` field on `PythHermesFeed`, populated once in
  `__post_init__` from the sorted dict keys (`feeds/pyth_ws.py:53, 56`). It
  is read only inside `run()` (`feeds/pyth_ws.py:130-131`).

State the module mutates that lives elsewhere:

- `TickStore`. The feed calls `tick_store.register(commodity)` once per
  configured commodity in `__post_init__` (`feeds/pyth_ws.py:57-58`) — this
  creates the per-commodity `TickRing` if absent (`state/tick_store.py:74-77`).
  On every `price_update`, the feed calls `tick_store.push(...)`, which writes
  three numpy slots, advances the ring's `_cursor`, and increments `_seq`
  (`feeds/pyth_ws.py:117`, `state/tick_store.py:44-51`). The cursor wraps at
  `capacity` (default 1,000,000, `state/tick_store.py:34`). `_seq` is
  monotonic with no wrap (Python `int`).

Disk I/O: none. The module does not open or read any file. The only files
present in the package directory are `feeds/pyth_ws.py` itself and
`feeds/__init__.py`.

Network I/O: only via `websockets.connect(self.endpoint)` inside `run()`
(`feeds/pyth_ws.py:128`). `ingest_message` does no I/O.

Global mutation: none beyond the module-level logger
(`feeds/pyth_ws.py:31`). No top-level mutable state, no class-level mutable
defaults; the dataclass uses `field(default_factory=list)` for the only
mutable default (`feeds/pyth_ws.py:53`).

Ordering assumptions: the feed assumes Hermes delivers `price_update`
messages in time order per feed id, but never enforces or asserts this. The
`ts_ns` from `publish_time` is written into the ring unmodified
(`feeds/pyth_ws.py:111, 117`); the staleness check (`engine/pricer.py:60-65`)
is the only place a backwards-in-time tick would be detected, and only against
`time.time_ns()`, not against the previous tick. The ring itself does not
order-check on `push` (`state/tick_store.py:44-51`).

## 8. Invariants

Every load-bearing assumption the code is making, with the citation it can be
inferred from:

1. **Every commodity that can show up on the wire has been registered.** The
   feed registers all commodities in its map at construction
   (`feeds/pyth_ws.py:57-58`), and `tick_store.push` raises `MissingStateError`
   if asked for an unregistered commodity (`state/tick_store.py:80-82`). So
   `ingest_message` only ever pushes for ids in `feed_id_to_commodity`, and
   the `UnknownFeedError` branch (`feeds/pyth_ws.py:96-97`) makes that
   one-to-one.
2. **Hermes' `price` integer fits in Python `int`.** The `int(price_block["price"])`
   call (`feeds/pyth_ws.py:104`) accepts arbitrary precision but
   `raw_price * (10.0 ** expo)` casts to `float64` (`:110`). Beyond about
   `1e15` raw the conversion silently loses precision; the code does not check
   the magnitude.
3. **`expo` is integer-valued and within float64 range.** `int(price_block["expo"])`
   (`feeds/pyth_ws.py:105`) followed by `10.0 ** expo` (`:110`). `expo` of
   `-308` or below underflows to 0; `+308` or above overflows to `inf`. Not
   guarded.
4. **`publish_time` is in seconds.** The conversion `publish_time * 1_000_000_000`
   (`feeds/pyth_ws.py:111`) only makes sense if the Hermes field is in unix
   seconds; the docstring asserts this (`feeds/pyth_ws.py:73`,
   "publish_time: <unix seconds>"). If Hermes ever sent ms or µs, the ring
   timestamp would be off by a factor of 1e3 or 1e6 and the staleness check
   (`engine/pricer.py:60-65`) would either always pass or always fail.
5. **Hermes feed ids are hex strings, optionally with `0x` prefix.** The
   normalisation logic at `feeds/pyth_ws.py:91-95` only handles the `0x`-vs-bare
   case. A subscription map keyed on a `0x`-prefixed id and a Hermes message
   carrying a bare id (or vice versa) both work; mixed casing is not
   normalised. The bare-id path is covered by
   `tests/test_pyth_ws.py:93-111`.
6. **`price_feed.id` is the only routing key.** No `topic`, `channel`, or
   `subscription_id` is consulted. (`feeds/pyth_ws.py:87-95`.)
7. **`num_publishers` of zero is acceptable to the feed.** The feed defaults
   to `0` if Hermes omits the field (`feeds/pyth_ws.py:112-115`). The
   downstream `Pricer` enforces `tick.n_publishers < min_publishers`
   (`engine/pricer.py:66-69`), so zero violates WTI's floor of 5
   (`config/commodities.yaml:8`); cartography red flag #8 at
   `audit/audit_A_cartography.md:270-275` is the same observation. The feed
   itself never rejects on publisher count.
8. **Reconnect budget is per uninterrupted attempt, not lifetime.** `attempt`
   is reset to 0 on every successful `await ws.send` inside the
   `async with websockets.connect(...)` (`feeds/pyth_ws.py:128-129`). A
   connection that flaps repeatedly past the success of `send` will keep
   resetting the counter; only consecutive pre-send failures accrue.
9. **Backoff is linear in `attempt`.** `await asyncio.sleep(self.reconnect_backoff_s * attempt)`
   (`feeds/pyth_ws.py:145`). After 5 failures the longest sleep is
   `5 × reconnect_backoff_s` (default 5 seconds).
10. **Non-JSON frames are terminal.** The `MalformedPythMessageError`
    raised at `feeds/pyth_ws.py:135-136` is not caught by the
    `except (OSError, asyncio.TimeoutError)` clause at `:138`, so it
    propagates out of `run()`.
11. **The `tick_store` is single-writer per commodity.** The feed mutates
    `TickRing` from inside whatever event loop runs `run()`; the ring has no
    locks (`state/tick_store.py:31-66`). The current call graph never has
    two writers because there is only one feed instance in any test or
    benchmark.

## 9. Error handling

Failure surfaces, mapped:

- Bad input to `ingest_message`: every branch that does not match the
  documented Hermes shape raises `MalformedPythMessageError` or
  `UnknownFeedError`. None of these are caught inside the module
  (`feeds/pyth_ws.py:79-108`).
- Network failure: only `OSError` and `asyncio.TimeoutError` are caught for
  reconnect (`feeds/pyth_ws.py:138`). `websockets.exceptions.ConnectionClosedError`
  is a subclass of `OSError` in `websockets >= 11`, so it is covered; older
  versions are not pinned out (`pyproject.toml:15` requires `>= 12.0`).
  `asyncio.CancelledError` is not in the tuple, so cancellation propagates as
  designed.
- Reconnect exhaustion: raises `PythFeedError` with the original exception
  chained via `from exc` (`feeds/pyth_ws.py:140-143`).
- Non-JSON frame: raises `MalformedPythMessageError` from inside the
  `async for` (`feeds/pyth_ws.py:135-136`); this terminates `run()` because
  it is not caught by the surrounding `except` clause.
- Successful parse but `tick_store.push` raises (e.g. unregistered
  commodity, which cannot happen given `__post_init__` registers everything):
  the exception propagates uncaught from `feeds/pyth_ws.py:117` out of
  `ingest_message` and out of `run()`.

The module never logs an error and continues. The only `log` call is the
informational connect message at `feeds/pyth_ws.py:131` and the warning during
reconnect at `feeds/pyth_ws.py:144`. No `try`/`except: pass`, no `if … else log`
swallowing pattern. The docstring's "never silently swallows" promise
(`feeds/pyth_ws.py:13`) is honoured by the implementation.

## 10. Test coverage

Single test file: `tests/test_pyth_ws.py` (111 lines per Phase A inventory at
`audit/audit_A_cartography.md:181`).

What's tested (`tests/test_pyth_ws.py`):

- `test_ingest_price_update_pushes_tick` (`tests/test_pyth_ws.py:27-50`) —
  end-to-end push: builds a synthetic Hermes payload with `expo=-8` and
  `publish_time=1_745_000_000`, ingests it, asserts `(commodity, seq)` is
  `("wti", 1)`, asserts `store.latest("wti")` returns the expected price,
  publisher count, and `ts_ns`.
- `test_ingest_non_price_update_returns_none` (`tests/test_pyth_ws.py:53-55`)
  — covers the `type != "price_update"` branch (`feeds/pyth_ws.py:81-82`).
- `test_ingest_unknown_feed_raises` (`tests/test_pyth_ws.py:58-68`) —
  covers `UnknownFeedError` (`feeds/pyth_ws.py:96-97`).
- `test_ingest_missing_price_block_raises` (`tests/test_pyth_ws.py:71-76`) —
  covers the missing-`price` branch (`feeds/pyth_ws.py:99-101`).
- `test_ingest_malformed_price_fields_raise` (`tests/test_pyth_ws.py:79-90`)
  — covers the `int()` parse failure (`feeds/pyth_ws.py:103-108`); uses
  `"price": "not_a_number"`.
- `test_ingest_bare_hex_id_without_0x_prefix_normalizes`
  (`tests/test_pyth_ws.py:93-111`) — covers the `0x` normalisation
  (`feeds/pyth_ws.py:91-95`).

All tests construct a real `TickStore` (`tests/test_pyth_ws.py:18`,
`state/tick_store.py:69-92`); nothing is mocked.

What is **not** tested:

- `run()`. There is no test that opens a socket, sends a subscribe frame,
  reconnects, or exhausts the reconnect budget. The `websockets` import path
  (`feeds/pyth_ws.py:123`) is never executed under `pytest`. Cartography red
  flag #15 (`audit/audit_A_cartography.md:302-306`) is consistent with this:
  the lazy import exists precisely so tests do not need the dep.
- The non-dict-input branch (`feeds/pyth_ws.py:79-80`). No test passes a
  non-dict to `ingest_message`.
- The non-string-id branch (`feeds/pyth_ws.py:87-89`). No test passes
  `price_feed: {"id": 123}`.
- The `num_publishers` defaulting branch (`feeds/pyth_ws.py:112-115`). The
  parsing test at `tests/test_pyth_ws.py:71-76` and the bare-id test at
  `tests/test_pyth_ws.py:93-111` both omit `num_publishers`, so the path is
  exercised, but no assertion is made on the resulting `n_publishers == 0`.
- Reconnect-budget exhaustion (`feeds/pyth_ws.py:139-143`).
- Non-JSON-frame handling (`feeds/pyth_ws.py:135-136`).

Indirect coverage from `benchmarks/run.py:143-179`. The `bench_tick_to_theo`
benchmark constructs a `PythHermesFeed` with `endpoint="wss://unused.invalid"`
and calls `feed.ingest_message(tmpl)` 5,000 times in the timed loop. This
exercises `ingest_message` under load but is not run under `pytest` by default
(`benchmarks/test_benchmarks.py` per Phase A only checks per-call budgets via
its own harness, not this top-level script). The Phase B engine-pricer audit
notes the same composition at
`audit/audit_B_engine-pricer.md:153, 419`.

## 11. TODOs, bugs, and smells

Literal markers: `Grep "TODO|FIXME|XXX|HACK"` in `feeds/` returns no matches.
There are no TODO/FIXME comments, no commented-out code blocks, no `XXX`
markers in the module.

Structural observations, each cited:

- **`num_publishers` defaults silently to zero.** `feeds/pyth_ws.py:112-115`.
  The inline comment names the cause ("Hermes currently surfaces publisher
  count inconsistently") and pushes the policy decision to the pricer's
  `pyth_min_publishers` gate. With WTI's floor of 5
  (`config/commodities.yaml:8`), every Hermes message that omits the field
  would be rejected downstream — but the rejection happens at `Pricer`, not
  in the feed. Cartography records this as red flag #8
  (`audit/audit_A_cartography.md:270-275`).
- **Subscription frame uses raw map keys.** `feeds/pyth_ws.py:55-58` sorts
  the keys directly into `_subscribed`; `:130` sends them as the `ids` list.
  The parse path normalises `0x`-vs-bare on inbound (`:91-95`) but the
  outbound subscribe uses whatever case/prefix the caller supplied. Whether
  Hermes accepts either form is not checked here.
- **Linear, not exponential, reconnect backoff.**
  `feeds/pyth_ws.py:144-145`: `await asyncio.sleep(self.reconnect_backoff_s * attempt)`.
  Default `reconnect_backoff_s = 1.0` and `max_reconnects = 5`
  (`feeds/pyth_ws.py:51-52`) yields sleeps of 1s, 2s, 3s, 4s, 5s totaling 15
  seconds before a `PythFeedError` is raised. Whether 15 seconds is enough
  for transient Hermes outages is a policy question the code does not
  answer.
- **Reconnect counter resets only after `ws.send` succeeds, not after the
  socket opens.** `feeds/pyth_ws.py:127-129`. The reset is at `:129`, after
  the `async with websockets.connect`; a failure inside
  `await ws.send(...)` itself (`:130`) would not reset because `attempt = 0`
  ran before send. Net effect is conservative.
- **Non-JSON frame is fatal to `run()`.** `feeds/pyth_ws.py:135-136`.
  Hermes is not expected to send non-JSON in practice but the code's
  reaction is to terminate the connect loop, not reconnect.
- **Empty `feeds/__init__.py`.** The package re-exports nothing and has no
  `__all__`. Every importer must use the submodule path (`feeds.pyth_ws`),
  as `tests/test_pyth_ws.py:7` and `benchmarks/run.py:25` both do.
- **Lazy `websockets` import inside `run()`.** `feeds/pyth_ws.py:123`.
  The dependency is declared as required at `pyproject.toml:15`
  (`audit/audit_A_cartography.md:21, 302-306`), so the lazy form serves
  only test-time convenience; under any production install the import is
  always resolvable.
- **Logger name is fixed.** `feeds/pyth_ws.py:31` uses
  `logging.getLogger("goated.feeds.pyth")` directly instead of
  `logging.getLogger(__name__)`. The string is consistent with module
  namespace but is not derived from it.

## 12. Open questions

Things the code does not reveal and would have to be asked of a maintainer:

1. **Is the reconnect counter intended to reset on successful frame receive
   rather than on successful subscribe?** Today it resets at
   `feeds/pyth_ws.py:129`, immediately after `async with` enters. A brief
   open-then-close cycle that lands a subscribe but no data still resets
   the budget.
2. **What is the policy when Hermes sends a `price_update` for an id the
   feed didn't subscribe to?** Today this raises `UnknownFeedError`
   (`feeds/pyth_ws.py:96-97`) and propagates out of `run()` (since the
   `except` clause filters only `OSError`/`asyncio.TimeoutError`,
   `feeds/pyth_ws.py:138`). It is unclear whether terminal-on-stray-id is
   intentional or whether the intent was log-and-skip.
3. **What is the intended `num_publishers` default when Hermes omits it?**
   The inline comment at `feeds/pyth_ws.py:112-115` documents the
   inconsistency but the chosen fallback (`0`) means every such tick is
   rejected by the pricer (`engine/pricer.py:66-69`,
   `config/commodities.yaml:8`). Whether this is the desired semantics or a
   placeholder pending a Pythnet/Solana-RPC publisher source
   (`feeds/pyth_ws.py:8-11`) is not stated in the code.
4. **What is the wiring path from `run()` to the production `Pricer`?**
   No file imports `PythHermesFeed.run` (Grep confirms; the only importers
   are tests and benchmarks). The cartography also flags this at
   `audit/audit_A_cartography.md:98-100, 254-257`. The intended composition
   point — whether via `engine/scheduler.py`, a future `main`, or something
   else — is not visible in the code today.
5. **Is the `hermes_http` fallback at `config/pyth_feeds.yaml:8` ever meant
   to be used by this module, or by a sibling module that does not yet
   exist?** No Python file references `hermes_http`
   (Grep `"hermes_http"` returns only the YAML and audit file matches).
6. **Should `__post_init__` register commodities in a deterministic order?**
   It iterates `self.feed_id_to_commodity.values()` (`feeds/pyth_ws.py:57`),
   which is insertion-ordered in CPython 3.7+ but relies on caller behaviour.
   `_subscribed` is sorted, but `tick_store.register(...)` is not.
7. **Is there an intended ceiling on per-id message rate?** `ingest_message`
   has no rate limiter, and `TickRing.push` is unconditional
   (`state/tick_store.py:44-51`). At Hermes' burst rates, the 1 M-slot ring
   wraps in roughly 1 M / msg-per-sec seconds; whether that is acceptable
   depends on consumer expectations the feed cannot see.
