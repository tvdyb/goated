# Audit Phase A — Cartography

Repository: `goated` — a Python 3.11 prototype of a live Kalshi commodity "theo"
(theoretical probability) engine. This document maps the repository as of commit
HEAD on the working branch. It is a map, not a judgement: later phases will
consume the module inventory at the bottom of the file to decide where to
deep-dive.

All path references are repo-relative.

---

## 1. Languages, frameworks, and package manifests

Single-language repo. Everything executable is Python ≥ 3.11; everything else
is YAML config, Markdown research, or a Markdown README.

`pyproject.toml:9-20` pins the runtime dependency set:

    numpy >= 1.26
    scipy >= 1.11
    numba >= 0.59
    pyyaml >= 6.0
    websockets >= 12.0
    httpx >= 0.27
    structlog >= 24.1
    python-dateutil >= 2.9
    pytz >= 2024.1

And dev extras at `pyproject.toml:22-29`:

    pytest >= 8.0
    pytest-asyncio >= 0.23
    pytest-benchmark >= 4.0
    hypothesis >= 6.100
    ruff >= 0.4

The build backend is `setuptools.build_meta` (`pyproject.toml:2-3`). Package
discovery (`pyproject.toml:31-33`) includes `feeds*`, `state*`, `models*`,
`engine*`, `calibration*`, `validation*`; it explicitly excludes `tests*` and
`benchmarks*`. `pytest` is configured with `asyncio_mode = "auto"` and
`testpaths = ["tests"]` (`pyproject.toml:35-38`). Ruff line length is 110 with
rule set `E, F, W, I, N, UP, B, SIM, PL` and ignore `PLR0913, PLR2004`
(`pyproject.toml:40-46`).

No `setup.py`, no `requirements*.txt`, no lockfile (no `poetry.lock`,
`pdm.lock`, `uv.lock`, or `pip-tools` output). Python version floor is 3.11;
`tool.ruff.target-version` is `py311`.

Total Python source excluding empty `__init__.py` files is **1,829 lines**
across 19 files (run: `wc -l $(find . -name "*.py")`). Config YAML totals
100 lines. Research Markdown totals 2,982 lines across ten phase documents.

## 2. Repository layout

Top-level, `ls` output for `.` excluding hidden files:

- `README.md` (66 lines) — project status, latency numbers, dev setup.
- `pyproject.toml` (46 lines) — build + dependencies + tooling.
- `benchmarks/` — latency harness + standalone `python -m benchmarks.run`.
- `calibration/` — empty package. Contains `__init__.py` and
  `calibration/params/.gitkeep` only. `.gitignore:21-22` excludes
  `calibration/params/*.json`.
- `config/` — `commodities.yaml` and `pyth_feeds.yaml`.
- `engine/` — the repricer (`pricer.py`), an asyncio priority queue skeleton
  (`scheduler.py`), and a per-commodity trading-hour calendar
  (`event_calendar.py`).
- `feeds/` — ingestion. Contains `pyth_ws.py` only; README lists "Pyth, CME,
  options, Kalshi, macro" but only Pyth is implemented.
- `models/` — the pricing-model contract (`base.py`), the one live model
  (`gbm.py`), and a YAML-driven registry (`registry.py`).
- `research/` — ten long Markdown documents (~300–620 lines each) covering
  soybean market structure, market-making theory, Kalshi contract structure,
  and strategy synthesis. Non-runtime.
- `state/` — shared in-memory state: tick ring buffer (`tick_store.py`), ATM
  IV surface (`iv_surface.py`), Pyth↔CME basis (`basis.py`), shared errors
  (`errors.py`).
- `tests/` — pytest suite: analytical parity, ingestion parsing, trading
  calendar, benchmarks (budget-asserting), and an end-to-end happy path +
  failure matrix.
- `validation/` — `sanity.py` (pre-publish invariant checker) only. README
  implies more lives here ("backtest, Pyth↔CME reconciliation"); it does not.

No top-level `src/`, `scripts/`, `docker/`, `deploy/`, or `docs/`. No `Makefile`,
`Dockerfile`, `.env.example`, or `docker-compose.yml`.

## 3. Build, run, and test entry points

From `README.md:50-57` and inspection of the code:

- **Dev install**: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.
- **Test**: `pytest` (configured via `pyproject.toml`; `tests/conftest.py`
  also sys-path-hacks the repo root, so tests run without the editable install
  too — see red flag #12).
- **Benchmark run**: `python -m benchmarks.run` (`benchmarks/run.py:207-209`).
  Returns exit code 1 if any budget is exceeded (`benchmarks/run.py:204-205`).
- **Lint**: `ruff` (configured in `pyproject.toml:40-46`), invoked manually.
- **Live run / service entry point**: none. `feeds/pyth_ws.py:120-145` has an
  async `run()` that connects to Hermes and streams, but nothing wires it to
  the `Pricer`. There is no `main` binary, CLI, or systemd/launchd unit.

## 4. External services

- **Pyth Hermes WebSocket** — `wss://hermes.pyth.network/ws`
  (`config/pyth_feeds.yaml:7`). Subscription message shape:
  `{"type": "subscribe", "ids": [...]}` at `feeds/pyth_ws.py:130`. Message
  type consumed: `price_update` (`feeds/pyth_ws.py:81, 60-118`).
- **Pyth Hermes HTTP/SSE fallback** — `https://hermes.pyth.network`
  (`config/pyth_feeds.yaml:8`). Referenced in YAML only; no Python caller.
- **CME / options chains / Kalshi API / macro feeds** — referenced in the
  `README.md:39` layout text and in `research/` but not implemented anywhere
  in the code.

No database (SQL, Redis, kdb, Arctic, etc.). No cloud SDK imports (boto, gcloud,
azure). No message queue (Kafka, NATS, RabbitMQ). No cron. No scheduler daemon.

## 5. Data sources and formats

On-disk data:

- `config/*.yaml` — the only on-disk configuration (see §6).
- `calibration/params/` — intended persistence directory for nightly
  calibration outputs (jump MLE, HMM fit, IV strip). Currently empty;
  tracked via `.gitkeep`. `.gitignore:21-22` excludes `*.json` from it, so
  even if populated, artifacts would not be committed.

In-memory data:

- `state/tick_store.py:31-66` — per-commodity `TickRing`: three parallel
  numpy arrays (`int64 ts_ns`, `float64 price`, `int32 n_publishers`) plus a
  monotonic `seq` counter and a wraparound `cursor`. Default capacity is
  1,000,000 ticks per commodity (`state/tick_store.py:34`).
- `state/iv_surface.py:21-48` — `{commodity: (sigma, ts_ns)}` dict with
  staleness gating.
- `state/basis.py:19-48` — `{commodity: (annualized_drift, ts_ns)}` dict with
  staleness gating.

Schemas for the Pyth Hermes wire format are documented inline at
`feeds/pyth_ws.py:64-77` (the `price_update` shape).

## 6. Configuration

Files:

- `config/commodities.yaml` (84 lines). Per-commodity block fields (WTI is
  the only fully-populated entry, lines 6-30): `pyth_feed_id`,
  `pyth_min_publishers`, `pyth_max_staleness_ms`, `cme_symbol`,
  `cme_roll_rule`, `options_symbol`, `options_expiry`, `model`, `vol_source`,
  `vol_fallback`, `drift`, `basis_model`, `trading_hours.{session,
  hours_per_day}`, `event_calendar[].{name, day_of_week, time_et,
  vol_adjustment}`, `jump`, `notes`. Stub entries (lines 34-85) carry only
  `{model, stub: true}`.
- `config/pyth_feeds.yaml` (16 lines). Top-level `hermes_endpoint`,
  `hermes_http`, and a `feeds.{commodity}` block with `feed_id`, `symbol`,
  `description`, `expected_publishers_floor`, `max_staleness_ms`.

Environment variables: none. `grep -rn "os.environ\|getenv" --include="*.py"`
returns no matches. `.gitignore:15-17` ignores `.env` and `.env.*`, but no
`.env.example` is present.

Feature flags: the only flag-like toggle is `stub: true` inside
`config/commodities.yaml` (see `models/registry.py:61`), which marks a
commodity as parse-only / not instantiable.

## 7. Testing and CI

Framework: pytest + pytest-asyncio + pytest-benchmark + hypothesis
(`pyproject.toml:23-28`). No coverage tooling configured (`.gitignore:9-10`
mentions `.coverage` / `htmlcov/` but no coverage run is invoked).

Test files (all under `tests/`):

- `conftest.py` (9 lines) — adds repo root to `sys.path`.
- `_bs_reference.py` (26 lines) — a Black-Scholes `P(S_T > K)` reference
  implementation using `scipy.special.ndtr`, used as a parity oracle.
- `test_gbm_analytical.py` (109 lines) — 1,000 random-case parity test
  against the BS reference, monotonicity, boundary limits, put-call parity
  for digitals, invalid-input raises.
- `test_end_to_end.py` (163 lines) — tick → pricer → theo end-to-end, plus
  the full "raises on missing/stale state" matrix.
- `test_pyth_ws.py` (111 lines) — Hermes message parsing without network I/O.
- `test_trading_calendar.py` (53 lines) — weekend, full weekday, daily halt,
  settle-before-now, unsupported-commodity.
- `test_benchmarks.py` (88 lines) — budget-asserting latency tests.

CI: none. No `.github/`, `.gitlab-ci.yml`, `circle.yml`, `azure-pipelines.yml`,
`Jenkinsfile`, or `buildkite/` directory. Benchmark budgets are enforced only
if a developer runs `pytest` or `python -m benchmarks.run` locally.

## 8. Documentation in the repo

- `README.md` — project description, status, latency numbers, layout map,
  dev setup, and a "non-negotiables" bullet list.
- `research/phase_01..10_*.md` — ten long research documents (281–620 lines
  each, 2,982 lines total). Topics: soybean market structure, market-making
  models, tooling/infrastructure, discretionary and systematic strategies,
  data streams, Kalshi contract structure, synthesis pricing, Kalshi stack,
  strategy synthesis. These are authored prose; none of the code imports
  from `research/` (it is not a Python package).
- Inline module docstrings exist on every non-trivial module (`feeds/pyth_ws.py:1-20`,
  `state/tick_store.py:1-12`, `engine/event_calendar.py:1-18`, etc.). These
  are the primary contract documentation alongside the README.

No `CHANGELOG.md`, no `CONTRIBUTING.md`, no `docs/` directory, no API
reference generation (Sphinx / mkdocs / pdoc).

## 9. Module Inventory

LoC counts are from `wc -l` on the files listed, excluding empty
`__init__.py` files (which all weigh 0 lines). "External Deps" lists only
third-party imports; intra-repo imports are omitted.

| Module | Slug | Files (paths) | Approx LoC | Responsibility (one sentence) | External Deps |
|---|---|---|---|---|---|
| Pyth Hermes Feed | `feeds-pyth` | `feeds/pyth_ws.py`, `feeds/__init__.py` | 145 | Async WebSocket client that subscribes to Hermes, parses `price_update` frames, and pushes ticks into `TickStore`. | `websockets` (lazy), stdlib `asyncio`, `json`, `logging`, `dataclasses` |
| Tick Ring Store | `state-tick-store` | `state/tick_store.py` | 92 | Preallocated per-commodity numpy ring buffer with O(1) push and O(1) `latest()`; issues a monotonic `seq` for provenance. | `numpy` |
| IV & Basis Surfaces | `state-market-surfaces` | `state/iv_surface.py`, `state/basis.py` | 96 | Per-commodity ATM IV and annualized Pyth↔CME basis drift with staleness gating; raise on missing or stale data. | stdlib `math` |
| State Errors | `state-errors` | `state/errors.py` | 16 | Two shared exception classes (`MissingStateError`, `StaleDataError`) used across state and pricing. | stdlib only |
| Theo Interface | `models-interface` | `models/base.py` | 69 | Frozen `TheoInputs` / `TheoOutput` dataclasses and the abstract `Theo` base class defining the per-model `price()` contract. | `numpy` |
| GBM Pricer | `models-gbm` | `models/gbm.py` | 105 | Numba-JITed `P(S_T > K) = Φ(d₂)` kernel plus a `GBMTheo` wrapper that validates inputs and stamps provenance; currently the only live model. | `numba`, `numpy`, stdlib `math` |
| Commodity Registry | `models-registry` | `models/registry.py` | 94 | Loads `config/commodities.yaml`, maps `model` strings to model builders, exposes `get(commodity)`; raises on stubs or unknown model names. | `pyyaml` |
| Repricer | `engine-pricer` | `engine/pricer.py` | 90 | Orchestrates tick → IV → basis → τ → model → sanity check; the sole hot-path composition point; raises on any missing/stale input. | `numpy` |
| Async Scheduler (skeleton) | `engine-scheduler` | `engine/scheduler.py` | 59 | Priority-queue async task scheduler with `TICK`/`IV_UPDATE`/`BASIS_UPDATE`/`EVENT_CAL`/`TIMER` priorities; declared but not wired to any producer. | stdlib `asyncio`, `itertools` |
| Trading Calendar | `engine-calendar` | `engine/event_calendar.py` | 110 | Per-commodity trading-hour τ calculator; WTI session is the only one implemented (Sun 18:00 ET → Fri 17:00 ET, 23 h/day, 5,796 hrs/yr). | stdlib `datetime`, `zoneinfo` |
| Pre-Publish Sanity | `validation-sanity` | `validation/sanity.py` | 68 | Asserts every `TheoOutput` is finite, in [0,1], monotone-decreasing in strike, and shape-consistent before the theo is returned. | `numpy` |
| Benchmark Harness | `benchmarks` | `benchmarks/harness.py`, `benchmarks/run.py` | 326 | Standalone latency harness (warmup, percentiles, budget checks) and a 50-market synthetic full-book builder. | `numpy`, `pyyaml` |
| Configuration | `config` | `config/commodities.yaml`, `config/pyth_feeds.yaml` | 100 | YAML declarations of per-commodity pricing params, Pyth feed IDs, staleness/publisher thresholds, trading hours, and event calendar. | n/a |
| Test Suite | `tests` | `tests/conftest.py`, `tests/_bs_reference.py`, `tests/test_gbm_analytical.py`, `tests/test_end_to_end.py`, `tests/test_pyth_ws.py`, `tests/test_trading_calendar.py`, `tests/test_benchmarks.py` | 559 | Analytical parity vs Black-Scholes, ingestion parsing, trading calendar arithmetic, end-to-end happy path + failure matrix, and budget-asserting latency tests. | `pytest`, `numpy`, `scipy` |
| Calibration (empty stub) | `calibration` | `calibration/__init__.py`, `calibration/params/.gitkeep` | 0 | Placeholder package declared in README as "offline nightly jobs (vol, jump MLE, HMM fit, IV event strip)"; no code yet. | n/a |
| Research Corpus | `research-docs` | `research/phase_01..10_*.md` | 2,982 (Markdown) | Ten long-form research documents on soybean market structure, Kalshi contract structure, and market-making strategy. Not imported by any code. | n/a |

## 10. Red flags

Listed as observations with file + line anchors. No remediation here.

1. `README.md:36-48` enumerates a `feeds/` directory that "ingests Pyth, CME,
   options, Kalshi, macro" and a `calibration/` that runs "offline nightly
   jobs (vol, jump MLE, HMM fit, IV event strip)". The filesystem shows only
   `feeds/pyth_ws.py` and an empty `calibration/` package containing one
   `__init__.py` and a `.gitkeep`. README promises a wider surface than the
   code delivers.
2. `README.md:3` describes a "Live Kalshi commodity theo engine." No file in
   the repo imports, references, or implements anything Kalshi-specific —
   no REST client, no contract schema, no order submission. The whole
   Kalshi-facing side of the system is absent.
3. `pyproject.toml:16-19` pins `httpx >= 0.27`, `structlog >= 24.1`,
   `python-dateutil >= 2.9`, and `pytz >= 2024.1` as runtime deps.
   `grep -rn "import httpx|from httpx|dateutil|pytz|structlog" --include="*.py"`
   returns zero matches. These four declared dependencies are not used.
4. `benchmarks/harness.py:23` imports private, underscore-prefixed symbols
   (`_SECONDS_PER_TRADING_YEAR_WTI`, `_wti_trading_seconds`) out of
   `engine.event_calendar`, crossing a module boundary that the leading
   underscore explicitly marks as internal.
5. `engine/scheduler.py:36-56` defines a `Scheduler` class but no producer
   submits to it. No module imports `Scheduler`; a `grep` for
   `from engine.scheduler|import.*Scheduler` returns zero external hits.
   The scheduler skeleton is unused at rest.
6. There is no CI configuration (`ls -la .github` returns no such path, and
   no `.gitlab-ci.yml`/`Jenkinsfile`/similar exists). The benchmark
   suite in `tests/test_benchmarks.py` is defined as regression-detecting
   but is not automatically run on push/PR.
7. `models/registry.py:32-38` maps only `"gbm"` to a live builder; entries
   for `jump_diffusion`, `regime_switch`, `point_mass`, and `student_t` are
   commented out. `config/commodities.yaml:63-80` declares `nat_gas`,
   `wheat`, `coffee` as `jump_diffusion`, `nickel` as `regime_switch`, and
   `lithium` as `point_mass`, but every one of those is also tagged
   `stub: true` — so today they bypass the builder lookup via
   `models/registry.py:67-68`. If the `stub` flag is ever removed without a
   corresponding `_MODEL_BUILDERS` entry, the registry raises at load.
8. `feeds/pyth_ws.py:112-115` hard-codes a `num_publishers` default of `0`
   when Hermes omits the field, with the inline comment "Hermes currently
   surfaces publisher count inconsistently". The `pyth_min_publishers`
   gate in `engine/pricer.py:66-69` would therefore reject every such
   message in production (min floor is 5 for WTI at
   `config/commodities.yaml:8`).
9. `state/tick_store.py:34, 70` defaults `capacity = 1_000_000` per
   commodity, preallocating three numpy arrays (8B + 8B + 4B per slot =
   20 MB per ring). The hot path only ever calls `latest()`
   (`state/tick_store.py:57-66`) — no history reader is wired anywhere.
   `engine/pricer.py:59` uses only `latest()`.
10. `validation/sanity.py:59-60` calls `np.argsort(strikes, kind="stable")`
    on every `check()` invocation — O(n log n) per hot-path call, invoked
    inside `engine/pricer.py:89` after every reprice. The cost is trivial at
    n = 20 strikes but is listed here as a fact for later phases.
11. `tests/conftest.py:7-9` mutates `sys.path` to make the repo root
    importable. This lets tests run without the editable install described
    in `README.md:55`. Tests and `pip install -e .` reach the same imports
    via two different mechanisms.
12. `.gitignore:21-22` ignores `calibration/params/*.json` with a
    `!calibration/params/.gitkeep` negation. No JSON has ever been committed;
    the intended artifact format is implied by `.gitignore` rather than by
    any producer code.
13. `README.md:10-20` reports measured latency numbers in prose. The
    benchmark harness at `benchmarks/run.py:82-179` can reproduce these
    numbers, but no automation re-computes and updates the README; it is a
    snapshot, not a build artifact.
14. `engine/event_calendar.py:30-38` hard-codes WTI trading windows as a
    module-level dict. `TradingCalendar.__init__` (lines 76-79) registers
    only `"wti"`; every other commodity in `config/commodities.yaml` will
    raise `NotImplementedError` at `engine/event_calendar.py:98` the moment
    the pricer asks for its τ — even the ones with `stub: true`.
15. `feeds/pyth_ws.py:123` imports `websockets` lazily inside `run()` so
    that unit tests do not need the dependency installed — yet
    `pyproject.toml:15` declares `websockets >= 12.0` as a hard runtime
    dependency, making the lazy-import work unnecessary under the declared
    install but useful under partial installs.
