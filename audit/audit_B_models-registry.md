# Audit Phase B — `models-registry`

Module slug: `models-registry`. The Phase A inventory pins this module to a
single Python file plus the YAML it parses (`audit/audit_A_cartography.md:221`,
`audit/audit_A_cartography.md:227`). The cartography record carries through:
this dive examined `models/registry.py` directly and all of its observed
inbound and outbound edges, and confirmed there are no other Python files in
the `models/` package that participate in the registry contract — `models/`
contains only `__init__.py` (1 byte / 1 line, empty), `models/base.py`,
`models/gbm.py`, and `models/registry.py`, and the registry only imports the
first two.

---

## 1. Module identity

Files in scope:

- `models/registry.py` — 94 lines (`audit/audit_A_cartography.md:221`).
- `models/__init__.py` — 0 lines, an empty package marker.
- `config/commodities.yaml` — 84 lines, 14 commodity blocks; the only file
  the registry ever opens, opened by absolute / `pathlib.Path` argument from
  callers (`models/registry.py:42-50`).

Total module Python LoC: 94 (the empty `__init__.py` carries no logic). The
registry is the smallest non-trivial module in the runtime by line count
after `state/errors.py`.

One-paragraph summary: `models/registry.py` is the parser-and-instantiator
layer between the on-disk YAML config (`config/commodities.yaml`) and every
caller that wants a pricing model for a named commodity. On construction it
reads the YAML once, builds an immutable `CommodityConfig` dataclass per
commodity, decides whether the entry is a stub or a fully-configured market,
and — if fully configured — uses a string-keyed builder dispatch
(`_MODEL_BUILDERS`) to instantiate one `Theo` instance per commodity. After
that, three accessors (`get`, `config`, `commodities`) serve readers. There
is no reload, no hot-swap, no late binding, no caching layer between the
YAML and the dispatch table; the dispatch table itself currently has exactly
one entry, `"gbm"` (`models/registry.py:32-38`).

## 2. Responsibility (inferred from code behaviour)

The registry solves three concrete problems, all visible in code paths:

1. **Translate a YAML mapping into typed Python.** `_load`
   (`models/registry.py:47-75`) walks the top-level mapping, type-checks each
   value as `dict`, requires a non-falsy `model` key, and packages everything
   else into a frozen `CommodityConfig` (`models/registry.py:24-29`).
2. **Bind a `model` string to a builder callable that produces a `Theo`.**
   The dispatch is a plain dict, `_MODEL_BUILDERS`
   (`models/registry.py:32-38`), keyed by the YAML's `model` field; the
   `"gbm"` builder takes the `CommodityConfig` and constructs `GBMTheo`
   with a `params_version` taken from `cfg.raw.get("params_version", "v0")`
   (`models/registry.py:33`).
3. **Refuse to silently degrade.** Stubs (`stub: true`) are kept in the
   config map but never instantiated (`models/registry.py:67-68`); a
   subsequent `get()` for a stub raises `NotImplementedError` rather than
   falling back to a default model (`models/registry.py:80-83`). An unknown
   `model` string in a non-stub block raises `ValueError` at load time
   (`models/registry.py:69-74`). A missing commodity raises `KeyError`
   (`models/registry.py:84`, `models/registry.py:88`). The module's docstring
   states this contract explicitly: "Stub entries (those tagged `stub: true`)
   are recorded so `get()` can raise a clear 'not yet configured' error
   instead of silently falling back" (`models/registry.py:1-7`).

That triad — parse, dispatch, refuse — is the entirety of what the module
does. No other behaviour appears in the file.

## 3. Public interface

The module exposes four public symbols. No `__all__` is declared; the
underscore-prefixed `_MODEL_BUILDERS` (`models/registry.py:32`) is the only
private one by convention.

- `class CommodityConfig` (`models/registry.py:24-29`). Frozen, slotted
  dataclass with `commodity: str`, `model_name: str`,
  `raw: dict[str, Any] = field(default_factory=dict)`, `is_stub: bool = False`.
  Carries the YAML node verbatim under `raw`, which downstream callers use
  to read out arbitrary per-commodity settings (`engine/pricer.py:55-57`,
  `benchmarks/run.py:145-148`).
- `class Registry` (`models/registry.py:41`). The single stateful object.
  Constructor signature: `Registry(config_path: str | Path) -> None`
  (`models/registry.py:42`).
  - `Registry.get(commodity: str) -> Theo` (`models/registry.py:77-84`):
    return the cached instance for `commodity`, or raise — `NotImplementedError`
    if it is registered as a stub, `KeyError` if it is not in the registry
    at all.
  - `Registry.config(commodity: str) -> CommodityConfig`
    (`models/registry.py:86-89`): return the parsed config or raise `KeyError`.
    Works for stubs and non-stubs alike, because `_configs` is populated
    before the stub-skip branch (`models/registry.py:65-68`).
  - `Registry.commodities(*, configured_only: bool = False) -> list[str]`
    (`models/registry.py:91-94`): sorted list of all commodity names; with
    `configured_only=True`, just those for which a `Theo` was instantiated.
- `_MODEL_BUILDERS: dict[str, Any]` (`models/registry.py:32-38`). A
  module-level dict mapping `model` strings to one-argument lambdas. Today
  it has a single live entry (`"gbm"`, `models/registry.py:33`). Four further
  entries — `"jump_diffusion"`, `"regime_switch"`, `"point_mass"`,
  `"student_t"` — are commented out at `models/registry.py:34-37` with
  `# deliverable N` markers. `Registry._load` reads it via `.get(model_name)`
  rather than indexing (`models/registry.py:69`), so unknown keys produce a
  `ValueError` with the sorted list of registered builders included in the
  message (`models/registry.py:71-74`).

There are no module-level functions, no factory helpers, no `from_dict`
classmethods, and no `__repr__` overrides.

## 4. Internal structure

`Registry` keeps two parallel dicts as instance state, both initialised in
`__init__` (`models/registry.py:43-44`):

- `self._configs: dict[str, CommodityConfig]` — every commodity in the YAML,
  including stubs.
- `self._instances: dict[str, Theo]` — only commodities for which a builder
  was found and ran successfully.

Data flow through `_load` (`models/registry.py:47-75`):

1. **Existence check.** `if not path.exists(): raise FileNotFoundError`
   (`models/registry.py:48-49`). Does not call `path.is_file()`, so a
   directory path that exists would proceed to `path.open()` and raise
   `IsADirectoryError` from the stdlib instead.
2. **Load.** `with path.open() as f: doc = yaml.safe_load(f)`
   (`models/registry.py:50-51`). Uses `safe_load`, so PyYAML will refuse
   custom Python tags and emit only built-in types.
3. **Top-level shape check.** `if not isinstance(doc, dict): raise ValueError`
   (`models/registry.py:52-53`). An empty file (PyYAML returns `None`)
   therefore raises here as `ValueError("…: expected top-level mapping, got
   NoneType")`.
4. **Per-commodity loop** (`models/registry.py:55-75`). For each
   `(commodity, raw)` pair:
   - `raw` must be a `dict` (`models/registry.py:56-57`).
   - `raw["model"]` must be present and truthy
     (`models/registry.py:58-60`). The literal check is `if not model_name`,
     so empty string and `None` both raise.
   - `is_stub = bool(raw.get("stub", False))` (`models/registry.py:61`). Any
     truthy value works; the YAML uses `stub: true` consistently
     (`config/commodities.yaml:36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76,
     80, 84`).
   - The `CommodityConfig` is built and stored in `_configs` *before* the
     stub branch is evaluated (`models/registry.py:62-65`), which is what
     lets `Registry.config("brent")` succeed even though `Registry.get("brent")`
     raises.
   - Stubs `continue` (`models/registry.py:67-68`).
   - Non-stubs go through `_MODEL_BUILDERS.get(model_name)`; a `None` result
     raises `ValueError` (`models/registry.py:69-74`); otherwise the lambda
     is invoked with the `CommodityConfig` and the result is stored in
     `_instances` (`models/registry.py:75`).

`get` searches `_instances` first, then falls back to checking `_configs`
for the stub case (`models/registry.py:78-84`). The ordering is what makes
"`KeyError: not in registry`" the correct error for a totally unknown
commodity — a stub goes through `NotImplementedError` first.

There is no notable algorithm; the module is straight dict-builder code.
The one design choice worth naming: the registry is **eagerly instantiated**
at construction time. Every model with a fully-configured entry is built
once during `_load`; later `get()` calls are pure dict reads. There is no
lazy-instantiation path.

## 5. Dependencies inbound (call sites)

Three modules import from `models.registry`. Verified with
`grep -rn "models.registry\|from models.registry\|import.*Registry\|import.*CommodityConfig" --include="*.py"`:

- `engine/pricer.py:24` — `from models.registry import Registry`. The
  `Pricer` dataclass holds a `registry: Registry` field
  (`engine/pricer.py:38`); the hot path reads `self.registry.config(commodity)`
  (`engine/pricer.py:55`) for staleness/publisher thresholds, then
  `self.registry.get(commodity)` (`engine/pricer.py:87`) to obtain the model
  to invoke. Both calls happen *every* `reprice_market` invocation.
- `benchmarks/harness.py:26` — `from models.registry import Registry`.
  `BenchContext` holds the registry (`benchmarks/harness.py:42`) and
  `build_full_book_pricer` constructs one from a synthetic YAML written to
  a temp dir (`benchmarks/harness.py:69-73`). The synthetic config is a
  dict comprehension over a single template (`benchmarks/harness.py:58-66`),
  and notably contains only `pyth_feed_id`, `pyth_min_publishers`,
  `pyth_max_staleness_ms`, and `model: "gbm"` — no `stub`, no
  `params_version`, no calendar fields.
- `benchmarks/run.py:145` — `cfg = ctx.registry.config(commodity)`. Used to
  read `cfg.raw["pyth_feed_id"]` for the synthetic Pyth message template
  (`benchmarks/run.py:148, 157`).
- `tests/test_end_to_end.py:20` — `from models.registry import Registry`.
  Three direct registry tests live there: `test_registry_loads_wti_as_gbm`
  (`tests/test_end_to_end.py:51-57`), `test_stub_commodity_raises_on_get`
  (`tests/test_end_to_end.py:60-63`), and `test_stub_commodity_refuses_to_price`
  (`tests/test_end_to_end.py:150-163`). Five further tests construct a
  registry indirectly via `_build_pricer` (`tests/test_end_to_end.py:32-48`).

No other module references `Registry`, `CommodityConfig`, or
`_MODEL_BUILDERS`. The `feeds/`, `state/`, `validation/`, and
`engine/event_calendar.py` files do not touch the registry; they take the
data they need directly from their callers.

## 6. Dependencies outbound

Imports at `models/registry.py:12-21`:

- `__future__.annotations` — PEP 563 deferred evaluation of annotations
  (`models/registry.py:12`).
- `dataclasses.dataclass`, `dataclasses.field` — for `CommodityConfig`
  (`models/registry.py:14`).
- `pathlib.Path` — for the YAML existence check and `open()`
  (`models/registry.py:15`).
- `typing.Any` — used in `dict[str, Any]` annotations
  (`models/registry.py:16`).
- `yaml` (PyYAML) — `yaml.safe_load(f)` only (`models/registry.py:18`,
  `models/registry.py:51`). Pinned at `pyyaml >= 6.0` in
  `pyproject.toml:13`.
- `models.base.Theo` (`models/registry.py:20`) — used as the return type of
  `get()` and as the value type of `_instances`
  (`models/registry.py:44, 77`).
- `models.gbm.GBMTheo` (`models/registry.py:21`) — instantiated by the
  `"gbm"` builder lambda (`models/registry.py:33`).

The registry does not import `numpy`, `numba`, `httpx`, `websockets`,
`structlog`, `asyncio`, `time`, or `logging`. There is no logging at all in
this module — `_load` either returns silently or raises with a message; it
prints nothing.

Outbound services: none. The registry never calls a network endpoint, never
forks a subprocess, never spawns a thread. Its only outbound side effects
are file I/O (one `open()`, one `read()` via `yaml.safe_load`) and importing
`models.gbm.GBMTheo`, which transitively imports `numba` and triggers
numba's import-time setup but not its JIT compile (the `@njit` decorator on
`_gbm_prob_above` is lazy until first call — `models/gbm.py:26-42`).

## 7. State and side effects

In-process state held by a `Registry` instance:

- `self._configs` (dict, populated once in `_load`, read-only thereafter via
  `config()` and `commodities()`) (`models/registry.py:43`).
- `self._instances` (dict of `Theo`s, populated once in `_load`, read-only
  via `get()` and `commodities(configured_only=True)`)
  (`models/registry.py:44`).

Neither dict is exposed; all access goes through methods. There are no
setters, no `add_commodity`, no `register_model`, no `reload`. The module
is logically immutable after construction, though the underlying dicts are
not frozen — a caller with access to internals could mutate them, but no
caller does (verified by the inbound grep above).

Module-level state: `_MODEL_BUILDERS` is a single mutable dict at module
scope (`models/registry.py:32-38`). No code in the repo mutates it after
import.

Side effects on construction:

- Disk read of the YAML path (`models/registry.py:50-51`). One `open()`,
  one `read()`. The handle is closed by the `with` block.
- Eager construction of `GBMTheo()` instances for every non-stub commodity.
  Today that's just `wti` (`config/commodities.yaml:6-30` is the only
  non-stub block). `GBMTheo` is a frozen dataclass with no `__init__` side
  effects (`models/gbm.py:60-68`); it does not warm numba.

There is no global mutation. No environment variables are read (verified
against the cartography note that `os.environ`/`getenv` returns no matches
across the repo, `audit/audit_A_cartography.md:157-158`). Construction
order matters only in one sense: the YAML is fully consumed before any
caller sees the registry, so `get()` either has the entry or doesn't —
there is no race window.

## 8. Invariants

Invariants the code relies on, each grounded in evidence:

- **The YAML's top-level shape is `Mapping[str, Mapping[str, Any]]`.**
  Enforced explicitly: top-level dict check at `models/registry.py:52-53`,
  per-commodity dict check at `models/registry.py:56-57`. The repo's only
  YAML conforms (`config/commodities.yaml:6-85`).
- **Every commodity has a `model` key with a truthy value.** Enforced at
  `models/registry.py:58-60`. All 14 commodity blocks in
  `config/commodities.yaml` provide this (the smallest stub blocks still
  include `model: "gbm"` or `model: "jump_diffusion"` etc., e.g.
  `config/commodities.yaml:35-36`, `config/commodities.yaml:63-64`).
- **Every non-stub commodity's `model` string has a `_MODEL_BUILDERS`
  entry.** Enforced at `models/registry.py:69-74` with a `ValueError` carrying
  the sorted list of registered names. Today's table only registers `"gbm"`
  (`models/registry.py:33`); the protection works *because* every non-`gbm`
  entry in the YAML carries `stub: true` — `nat_gas`, `wheat`, `coffee`
  (jump_diffusion, `config/commodities.yaml:62-72`), `nickel`
  (regime_switch, `config/commodities.yaml:74-76`), and `lithium` (point_mass,
  `config/commodities.yaml:78-80`) all bypass the dispatch via the stub
  branch (`models/registry.py:67-68`). The module docstring marks this as
  expected: "Other model families register their class here as they come
  online" (`models/registry.py:8-9`).
- **The builder always returns a `Theo` (not `None`) and does not raise.**
  Implicit. The only registered builder is the `"gbm"` lambda at
  `models/registry.py:33`, and `GBMTheo()` with no required args succeeds
  (`models/gbm.py:60-67` makes `params_version` optional with default
  `"v0"`).
- **A commodity name is unique across the YAML.** PyYAML's default loader
  silently overwrites duplicate keys; the registry inherits whatever PyYAML
  hands it. `config/commodities.yaml:6-85` has unique top-level keys, but
  `models/registry.py` itself never checks.
- **`raw["pyth_max_staleness_ms"]` and `raw["pyth_min_publishers"]` are set
  for any commodity that reaches `Pricer.reprice_market`.** Not enforced in
  the registry; `engine/pricer.py:56-57` defaults via `cfg.raw.get(...)`
  with hardcoded fallbacks (`2000`, `5`). The registry passes the raw dict
  through; the runtime requirement lives on the consumer side.
- **`_MODEL_BUILDERS` is read but never written after import.** Implicit.
  The grep across the codebase finds no assignment to it outside its
  defining literal at `models/registry.py:32-38`.
- **YAML file size is small enough to load synchronously.** Implicit.
  `config/commodities.yaml` is 84 lines; `_load` blocks the calling thread
  during parsing (`models/registry.py:50-51`). There is no async path.
- **Construction is single-shot.** No method ever re-runs `_load`. A new
  YAML state requires a new `Registry` instance.

## 9. Error handling

Errors raised by the registry, classified by surface:

- `FileNotFoundError("commodities config not found: …")` —
  `models/registry.py:48-49`. The check is explicit; without it, `path.open()`
  would raise the same exception with a less informative message.
- `ValueError("…: expected top-level mapping, got …")` —
  `models/registry.py:52-53`. Triggers on empty YAML, on a YAML containing a
  list, or on YAML containing a single scalar at the top.
- `ValueError("…: commodity X must be a mapping")` —
  `models/registry.py:56-57`. Triggers if a commodity's value is not a dict.
- `ValueError("…: commodity X missing 'model' field")` —
  `models/registry.py:58-60`.
- `ValueError("X: model 'Y' has no builder registered (expected one of [...])")` —
  `models/registry.py:69-74`. Includes a sorted listing of valid names for
  diagnosis.
- `NotImplementedError("X: registered as stub, not yet configured for pricing")` —
  `models/registry.py:80-83`. Raised lazily by `get()` only; the load itself
  swallows stubs silently.
- `KeyError("X: not in registry")` — `models/registry.py:84`,
  `models/registry.py:88`. Used both by `get()` (for entirely unknown names)
  and `config()`.
- Inherited exceptions from the YAML and filesystem layers (e.g.
  `yaml.YAMLError`, `PermissionError`, `IsADirectoryError`) propagate
  unchanged; nothing is wrapped in a try/except in this file.

There are no `try/except` blocks in `models/registry.py`. There is no
logging. Errors propagate to the caller with the original Python type.

## 10. Test coverage

The registry is exercised primarily through `tests/test_end_to_end.py`. No
file in `tests/` imports `models/registry.py` standalone, and there is no
dedicated `test_registry.py`.

Direct tests:

- `test_registry_loads_wti_as_gbm` (`tests/test_end_to_end.py:51-57`):
  loads the real `config/commodities.yaml` from `CONFIG`
  (`tests/test_end_to_end.py:29`); asserts `registry.get("wti")` is a
  `GBMTheo`; asserts `"brent"` is in `commodities()` but not in
  `commodities(configured_only=True)`. This covers (a) successful load,
  (b) builder dispatch for `"gbm"`, (c) the both-views shape of
  `commodities()`.
- `test_stub_commodity_raises_on_get` (`tests/test_end_to_end.py:60-63`):
  asserts `registry.get("brent")` raises `NotImplementedError`. Covers the
  `is_stub` branch in `get()` (`models/registry.py:80-83`).
- `test_stub_commodity_refuses_to_price`
  (`tests/test_end_to_end.py:150-163`): primes tick/IV/basis state for
  `brent`, then calls `pricer.reprice_market`. Asserts
  `(NotImplementedError, KeyError)` is raised, with the explicit comment
  that "brent trading calendar isn't implemented either; NotImplementedError
  from calendar or registry, whichever triggers first"
  (`tests/test_end_to_end.py:159-160`). The test admits ambiguity about
  *which* layer raised — calendar or registry.

Indirect tests via `_build_pricer` (`tests/test_end_to_end.py:32-48`):
`test_end_to_end_wti_matches_bs_analytical`, `test_stale_pyth_tick_raises`,
`test_insufficient_publishers_raises`, `test_missing_iv_raises`,
`test_missing_basis_raises`, `test_missing_tick_raises`. These all
construct a real `Registry` against `config/commodities.yaml` but do not
exercise its error paths.

The benchmarks also indirectly cover the happy-path load path
(`benchmarks/harness.py:69-73` builds a synthetic registry from a temp
file).

What is **not** tested by any test in the repo:

- Missing-file path (`models/registry.py:48-49`).
- Top-level non-mapping YAML (`models/registry.py:52-53`).
- Commodity value that is not a dict (`models/registry.py:56-57`).
- Missing/empty `model` field (`models/registry.py:58-60`).
- Unknown `model` string in a non-stub (`models/registry.py:69-74`).
- `KeyError` from `get()` for a totally unregistered name
  (`models/registry.py:84`).
- `KeyError` from `config()` (`models/registry.py:86-89`).
- The `params_version` override path
  (`models/registry.py:33`); `config/commodities.yaml` does not set it on
  any block, so the `"v0"` default is the only branch ever taken in tests.

Mocking: none. Tests construct real `Registry` objects against either the
real YAML or a temp file (in benchmarks). There is no mock of `yaml.safe_load`,
no fake `Theo`, no fixture indirection beyond `tests/conftest.py:7-9`'s
`sys.path` hack.

## 11. TODOs, bugs, and smells

Literal markers: `grep -n "TODO\|FIXME\|XXX\|HACK" models/registry.py` returns
no matches. The module carries no inline TODOs; the four
deliverable-deferred lines (`models/registry.py:34-37`) are commented
builders rather than TODO comments, but they encode the same meaning.

Structural observations (descriptive, not prescriptive):

- **Single-entry dispatch, four commented neighbours.**
  `_MODEL_BUILDERS` (`models/registry.py:32-38`) lists `"gbm"` as the only
  live builder; `"jump_diffusion"`, `"regime_switch"`, `"point_mass"`, and
  `"student_t"` are commented out with `# deliverable 4` and
  `# deliverable 5` markers. The registry's invariant ("every non-stub
  `model` has a builder") is currently load-bearing only because every
  YAML entry naming those models also carries `stub: true`
  (`config/commodities.yaml:62-80`). This exact coupling is flagged as red
  flag #7 in the cartography (`audit/audit_A_cartography.md:264-269`).
- **Eager instantiation regardless of intended use.** `_load` constructs a
  `GBMTheo` for every non-stub at registry creation
  (`models/registry.py:75`). `GBMTheo()` has no expensive constructor
  (`models/gbm.py:60-68`), so the cost today is negligible; the pattern
  could become more meaningful once builders run real calibrations.
- **`raw: dict[str, Any]` leaks the YAML wholesale.** `CommodityConfig.raw`
  (`models/registry.py:28`) is the YAML node verbatim, including any keys
  the registry never inspects. Consumers reach into it freely:
  `engine/pricer.py:56-57` for `pyth_max_staleness_ms` /
  `pyth_min_publishers`, `benchmarks/run.py:148, 157` for `pyth_feed_id`.
  The registry imposes no schema beyond `model` and `stub`.
- **Stub bypass relies on order of operations.** `_configs[commodity] = cfg`
  is set before the stub-skip (`models/registry.py:65-68`), so
  `Registry.config("brent")` returns a config but `Registry.get("brent")`
  raises. Anyone reading the methods in isolation might expect them to
  fail symmetrically.
- **No reload, no observation hooks.** A long-running process picks up
  changes to `commodities.yaml` only on restart. No watcher, no version
  field exposed by the registry. The cartography notes the absence of any
  daemon process anyway (`audit/audit_A_cartography.md:97-100`).
- **Type annotation looseness.** `_MODEL_BUILDERS: dict[str, Any]`
  (`models/registry.py:32`) loses the lambda return type. A more precise
  `Callable[[CommodityConfig], Theo]` would be expressible but is not used.
  Listed as a fact, not a recommendation.
- **`bool(raw.get("stub", False))` accepts any truthy value.**
  `models/registry.py:61`. The YAML uses `true` consistently
  (`config/commodities.yaml:36-84`), but `stub: 1`, `stub: "yes"`, or
  `stub: []` would all parse and behave; the truthiness funnel is
  permissive.
- **Path argument types.** `__init__` accepts `str | Path`
  (`models/registry.py:42`) and immediately wraps in `Path(...)`
  (`models/registry.py:45`). Tests pass a `pathlib.Path` from the repo root
  (`tests/test_end_to_end.py:29`); benchmarks pass a `Path` returned by
  `tempfile.mkdtemp` (`benchmarks/harness.py:71`). The string branch is
  reachable via documentation only.
- **Sort cost is paid per call.** `commodities()` (`models/registry.py:91-94`)
  re-sorts on every invocation. Not on the hot path; the pricer never calls
  it at runtime — only tests and benchmarks do
  (`tests/test_end_to_end.py:55-57`, `benchmarks/harness.py:87`).
- **No idempotent re-load guard.** Calling `_load` twice on the same
  instance would re-overwrite `_configs` and `_instances`. `_load` is
  named with a leading underscore (`models/registry.py:47`) and is invoked
  only from `__init__` (`models/registry.py:45`); no one in the repo calls
  it twice, but nothing prevents it.

## 12. Open questions (not answerable from code alone)

- **What does `params_version` resolve to in production?** The builder
  honours `cfg.raw.get("params_version", "v0")` (`models/registry.py:33`),
  and `config/commodities.yaml:14` does not set it. Whether the eventual
  calibration pipeline writes this field into the YAML, or whether the
  registry is meant to read it from `calibration/params/` (currently empty,
  `audit/audit_A_cartography.md:62-63`) is not derivable from the code.
- **Why is `_MODEL_BUILDERS` a module-level dict rather than a class
  attribute or a registry method?** The chosen pattern works but offers no
  extension point that doesn't involve editing `models/registry.py`. The
  comments at `models/registry.py:34-37` suggest editing this file is the
  intended workflow, but no contributor doc spells it out.
- **Are stubs expected to load every other field of a real config?**
  `config/commodities.yaml:35-36` is minimal (`model` + `stub` only), and
  the registry accepts that. Whether downstream code (e.g. `Pricer`,
  `TradingCalendar`) is expected to coexist with such minimal stubs, or
  whether stubs are expected to fully populate fields ahead of being
  flipped to non-stub, is not visible.
- **Is the eager-instantiation choice deliberate vs accidental?** Could be
  load-time validation of the builder dispatch ("fail fast on import"); could
  be coincidence ("a `GBMTheo()` is cheap, so why not"). Code does not
  comment on the decision (`models/registry.py:62-75`).
- **What is the lifecycle for adding a non-`gbm` model?** Comments at
  `models/registry.py:34-37` imply: (a) add the import, (b) add the dict
  entry, (c) flip `stub: true` off in the YAML. Whether tests are expected
  to be added at the same time, and whether the absence of an unknown-model
  test is an oversight or a "we'll add it when the second model lands"
  decision, is not stated anywhere in the file or the surrounding tests.
- **Is the registry expected to be thread-safe?** Construction is single-shot
  and the dicts are read-only post-load, which makes concurrent reads safe;
  but nothing in the file or its docstring affirms that property
  (`models/registry.py:1-10`). Given the absence of any threading or async
  code in the repo's runtime path
  (`audit/audit_A_cartography.md:97-100, 254-256`), the question may be
  moot today.

---

Citations summary (line ranges to `models/registry.py` unless otherwise
noted): 1-7, 8-9, 12-21, 24-29, 32-38, 41, 42-50, 47-75, 48-49, 50-51,
52-53, 56-57, 58-60, 61, 62-65, 65-68, 67-68, 69-74, 75, 77-84, 78-84,
80-83, 84, 86-89, 91-94. Cross-module citations: `engine/pricer.py:24, 38,
55-57, 87`; `benchmarks/harness.py:26, 42, 58-66, 69-73`; `benchmarks/run.py:145-148,
157`; `tests/test_end_to_end.py:20, 29, 32-48, 51-57, 60-63, 150-163,
159-160`; `models/gbm.py:26-42, 60-68`; `config/commodities.yaml:6-30,
35-36, 36-84, 62-72, 74-76, 78-80`; `audit/audit_A_cartography.md:62-63,
97-100, 157-158, 221, 227, 254-256, 264-269`.
