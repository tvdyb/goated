# Audit D — Topic 10 of 10: Observability, Monitoring, and Kill-Switches

## 1. Scope

This file audits the `goated` repository against every Phase C claim tagged
`observability`, with priority weighting on Phase 09 (Kalshi stack) and
Phase 10 (strategy synthesis) per the audit prompt. The scope covers:
structured logging, metrics (counters, gauges, histograms), tracing /
provenance, alerting and dashboards, kill-switch plumbing on Kalshi (`DELETE
/orders/batch`, `POST /order-groups/{group_id}/trigger`) and on the CME
hedge leg, position reconciliation between Kalshi and the FCM, and
latency measurement at the points the research designates (tick→theo,
theo→quote, hedge round-trip).

The cartography (`audit/audit_A_cartography.md`) establishes the load-
bearing fact: only `feeds/pyth_ws.py` carries any logging surface
(`audit_A_cartography.md:215`, "External Deps … `logging`"), `structlog`
is declared in `pyproject.toml:20` but no Python file imports it
(`audit_A_cartography.md:246-249`, Red Flag 3), and there is no Kalshi
client, FCM client, scheduler producer, metrics emitter, or
reconciliation surface anywhere in the tree (`audit_A_cartography.md:
108-115, 244-245`). Phase B confirms the same shape for every observability-
adjacent module: `audit_B_engine-scheduler.md:190-192, 547-551` for the
priority queue, `audit_B_validation-sanity.md:474-480, 539-543` for the
empty `validation/` package, `audit_B_feeds-pyth.md:355-358, 460-463` for
the lone logger.

The audit therefore expects the dominant gap class to be `missing`. A
handful of claims map onto the partially-built logging surface in
`feeds/pyth_ws.py` and the latency harness in `benchmarks/`; those are
classified `partial` with code evidence rather than `missing`. No claim
is classified `already-good` because no Phase C observability claim has a
matching code-side implementation that meets the research description in
full.

All Phase C distillations (`audit_C_phase01..10_*.md`) and all Phase B
deep-dives present in the audit folder were read before writing this
file; no expected Phase C input is absent, so no halt was issued.

## 2. Audit table

| C-id | claim (one-line summary) | what code does | gap class | severity | code citation(s) | notes |
|---|---|---|---|---|---|---|
| C09-11 | Portfolio reconciliation uses `GET /portfolio/{positions,fills,balance,settlements}` (`audit_C_phase09_kalshi_stack.md:21`). | No Kalshi REST client exists; no module references `/portfolio/*` or any Kalshi endpoint. | missing | blocker | `audit_A_cartography.md:108-115, 244-245`; `grep -rn kalshi --include='*.py'` returns only docstring mentions in `state/iv_surface.py:9` and `engine/event_calendar.py:4`. | Reconciliation is the only integrity check between books; absence is foundational for the trading product, not just observability. |
| C09-24 | Tick history is captured forward from first subscribe — single largest data gap to plan around (`audit_C_phase09_kalshi_stack.md:34`). | No Kalshi WebSocket subscriber exists; only Pyth Hermes (`feeds/pyth_ws.py:128-145`) is implemented. The TickStore ring (`state/tick_store.py:31-66`) is keyed per-commodity and accepts only Pyth aggregate-price ticks. | missing | major | `audit_A_cartography.md:215` (only `feeds-pyth` module); `audit_B_feeds-pyth.md:487-492` (no Kalshi WS path). | The tick-store schema (`int64 ts_ns`, `float64 price`, `int32 n_publishers`) does not even carry an `event_ticker` / `floor_strike` / `cap_strike` shape; capturing Kalshi `orderbook_delta` requires a different storage surface. |
| C09-40 | WASDE second-Tuesday 12 p.m. ET window: quotes should widen or pull (`audit_C_phase09_kalshi_stack.md:50`). | `engine/event_calendar.py` registers only WTI session windows (`audit_A_cartography.md:298-301`, Red Flag 14); no per-commodity event calendar with WASDE entries is wired into the pricer hot path. `config/commodities.yaml:6-30` exposes a `event_calendar[]` field but `models/registry.py` reads only `model` and `stub` keys. | missing | major | `engine/event_calendar.py:30-38, 76-79`; `engine/pricer.py:55-89` (no event-window branch); `audit_B_engine-calendar.md` confirms only WTI weekday-session arithmetic. | The data is in YAML; no Python consumer of `event_calendar[].vol_adjustment`. |
| C09-56 | AWS `us-east-1` placement next to Kalshi (`audit_C_phase09_kalshi_stack.md:66`). | Repo has no deployment artefact: no `Dockerfile`, no Terraform/CDK, no `cloudformation/`, no CI manifest (`audit_A_cartography.md:84-85, 186-188`). The runtime is "no `main` binary, CLI, or systemd/launchd unit" (`audit_A_cartography.md:98-100`). | missing | minor | `audit_A_cartography.md:84-85` (no top-level deploy/docker dirs); `audit_A_cartography.md:98-100` (no service entry). | Severity minor because deployment placement is exogenous to repo content; flag is for the "where do we run this" question. |
| C09-58 | Tick-to-quote budget 40-60 ms broken into WS delta / density refresh / amend / ack (`audit_C_phase09_kalshi_stack.md:68`). | `benchmarks/run.py:68-70` measures `time.perf_counter_ns()` around a synthetic reprice loop; budgets are asserted via `tests/test_benchmarks.py` at `pytest`-time only. Hot path (`engine/pricer.py:42-89`) emits no per-stage timing. There is no amend, no ack, no quote leg measured because no Kalshi client exists. | partial | major | `benchmarks/run.py:13, 68-70, 204-205`; `engine/pricer.py:50-89`; `audit_A_cartography.md:294-296` (Red Flag 13: README latency numbers are a snapshot, not a build artefact). | Repo measures one of five legs (model compute) only, and only offline. Budget enforcement is a developer's pytest run, not a runtime gate. |
| C09-61 | Three-instance compute (quoter / hedge / capture); under $500/mo with monitoring and redundancy (`audit_C_phase09_kalshi_stack.md:71`). | One process model is not even drawn: there is no `main.py`, no entry-point script, no `if __name__ == "__main__"` block in any non-test module (`audit_A_cartography.md:98-100`). | missing | minor | `audit_A_cartography.md:98-100`; `pyproject.toml` has no `[project.scripts]` table. | Minor because architectural; the monitoring overlay the claim names is not a runtime concern of this code, only an ops-deployment one. |
| C09-63 | Kalshi does not backfill OB depth — every missed day is permanently lost (`audit_C_phase09_kalshi_stack.md:73`). | No Kalshi capture process exists; `state/tick_store.py:34, 70` defaults to a 1 000 000-slot ring per commodity but is wraparound (`audit_B_state-tick-store.md` cartography ref). The "capture forward" promise has no producer, no S3 sink, no Parquet writer. | missing | blocker | `audit_A_cartography.md:108-115`; `state/tick_store.py:31-66` (in-memory ring, no persistence); `grep -rn 's3\|parquet\|duckdb' --include='*.py'` returns zero hits. | The data permanence loss is irreversible day-by-day; this is the only research claim where inaction costs an asset that cannot be reconstituted. |
| C09-71 | Kill-switch primitive `DELETE /orders/batch` (`audit_C_phase09_kalshi_stack.md:81`). | No Kalshi REST client; no `httpx.AsyncClient`, no signing logic for `KALSHI-ACCESS-SIGNATURE` (the dependency `httpx >= 0.27` declared at `pyproject.toml:18` is unused per `audit_A_cartography.md:246-249`, Red Flag 3). | missing | blocker | `audit_A_cartography.md:246-249`; `grep -rn 'httpx\|requests\|urllib' --include='*.py'` returns zero hits in source. | Without an order-management layer, the kill-switch primitive is an API the code does not call; severity blocker because the claim is the load-bearing safety primitive of the strategy. |
| C09-72 | Secondary kill primitive `POST /order-groups/{group_id}/trigger` (`audit_C_phase09_kalshi_stack.md:82`). | Same as C09-71: no Kalshi client, no order-group state. | missing | major | `audit_A_cartography.md:108-115`. | Major rather than blocker only because C09-71 already covers the primary kill path; the order-group trigger is the recommended-but-not-only secondary lever. |
| C09-73 | Four kill triggers: signed-delta bound; intraweek PnL drawdown; CME heartbeat fail (N s); Kalshi WS reconnects > K/min (`audit_C_phase09_kalshi_stack.md:83`). | (i) No signed-delta accounting — no inventory module; (ii) no PnL accounting; (iii) no CME heartbeat — no FCM client; (iv) Kalshi WS does not exist; the Pyth WS counter at `feeds/pyth_ws.py:138-145` increments only on transient errors and never feeds a kill-switch — the reconnect counter resets at `feeds/pyth_ws.py:129` "immediately after `async with` enters" per `audit_B_feeds-pyth.md:469-473`. | missing | blocker | `audit_A_cartography.md:108-115`; `feeds/pyth_ws.py:138-145`; `audit_B_feeds-pyth.md:469-473`. | Even the closest analogue (Pyth reconnect budget) lacks a publish path: `feeds/pyth_ws.py:140-143` raises `PythFeedError` to the caller but no caller catches it, so the runtime behaviour is process exit, not a kill-switch fire. |
| C09-79 | Reconciliation runs three times per session: open / intraday / EOD (`audit_C_phase09_kalshi_stack.md:89`). | `validation/` package contains only `sanity.py` (pre-publish invariant checker); README claims "Backtest, Pyth↔CME reconciliation, pre-publish sanity checks" — only the third exists per `audit_B_validation-sanity.md:474-480`. | missing | blocker | `validation/sanity.py:1-68`; `audit_A_cartography.md:81-83` ("README implies more lives here … it does not"); `audit_B_validation-sanity.md:539-543`. | Reconciliation is what catches bookkeeping errors before they become fund-recovery problems; classifying as blocker. |
| C09-80 | Single reconciliation table keyed by `(event_ticker, timestamp, side)` (`audit_C_phase09_kalshi_stack.md:90`). | No persistent store, no DuckDB / Parquet / SQL anywhere; no schema for `event_ticker` because no Kalshi market types are defined. | missing | major | `audit_A_cartography.md:113-115` ("No database (SQL, Redis, kdb, Arctic, etc.)"); `state/tick_store.py:31-66` (only data structure). | The schema absence is a consequence of C09-79's missingness. |
| C09-81 | Recommended: Kalshi FIX Drop Copy as institutional-grade reconciliation channel (`audit_C_phase09_kalshi_stack.md:91`). | No FIX engine, no QuickFIX-Python or simplefix import; no FIX session config. | missing | nice-to-have | `audit_A_cartography.md:108-115`; `grep -rn 'fix\|quickfix\|simplefix' --include='*.py'` returns no hits. | Severity nice-to-have because the file itself flags Drop Copy as RECOMMENDED, not MVS. |
| C10-50 | Edge is a per-bucket post-trade markout estimate at 1m / 5m / 30m; widen quotes on adverse-selection-heavy buckets (`audit_C_phase10_strategy_synthesis.md:62`). | No fill stream consumer, no markout computation, no per-bucket alpha store; the registry has no per-bucket parameter shape. | missing | major | `audit_A_cartography.md:108-115`; `models/registry.py:32-38` (entry maps `commodity → model`, no bucket-aware per-strike alpha state). | The claim describes a live, fill-driven feedback loop the code has no pipeline for. |
| C10-51 | Per-bucket adverse-selection alpha must be calibrated live, week-by-week — not backtestable without own fills (`audit_C_phase10_strategy_synthesis.md:63`). | No fill ingestion → no calibration loop → no `calibration/` artefact (the package is empty per `audit_A_cartography.md:60-63, 122-125`); `.gitignore:21-22` excludes `calibration/params/*.json` but no producer ever writes one. | missing | major | `audit_A_cartography.md:60-63, 122-125, 289-292` (Red Flag 12); empty `calibration/__init__.py`. | Compounded with C10-50: both halves of the live-feedback loop are absent. |
| C10-70 | Adverse-selection fingerprint: fat-tailed markout near WASDE / Export Sales / Crop Progress (`audit_C_phase10_strategy_synthesis.md:82`). | No release-window indicator and no markout stream; the trading calendar (`engine/event_calendar.py`) carries no USDA event schedule beyond the WTI weekday session. | missing | minor | `engine/event_calendar.py:30-38, 76-79`; `audit_A_cartography.md:298-301` (Red Flag 14). | Severity minor because the claim is diagnostic, not a runtime gate; observability artefact rather than safety primitive. |
| C10-74 | Limit-locked Friday expiry produces discrete-jump P&L; book must be stress-tested (`audit_C_phase10_strategy_synthesis.md:86`). | No stress-test harness, no scenario generator, no expiry-day branch in any pricer or sanity check (`engine/pricer.py:42-89`; `validation/sanity.py:32-68`). | missing | major | `engine/pricer.py:42-89`; `validation/sanity.py:32-68`; cartography lists no scenario module (`audit_A_cartography.md:54-85`). | The 7%-of-price daily limit is not encoded anywhere in the repo. |
| C10-76 | A 429 during a release window prevents pulling quotes; operator wears adverse selection until leaky-bucket refills (`audit_C_phase10_strategy_synthesis.md:88`). | No HTTP client, no 429 handler, no token-bucket pacer. The Pyth WS reconnect logic at `feeds/pyth_ws.py:138-145` is for `OSError`/`asyncio.TimeoutError` only and does not generalise to HTTP 429 semantics. | missing | major | `audit_A_cartography.md:108-115`; `feeds/pyth_ws.py:138-145`. | The claim is operationally critical for the 12 p.m. ET WASDE window. |
| C10-78 | Milestone 1 (paper-trade pricing engine): pipeline ingest→smoothing→RND→bucket→overlay→reservation→skew→spread→hedge→risk; log "would-quote" Yes prices at 1 s cadence per bucket; deliver mid-error distribution, markout simulator, rate-limit headroom report (`audit_C_phase10_strategy_synthesis.md:90`). | The pipeline as described is absent: no smoothing, no RND extraction, no bucket integration, no overlay, no reservation-price formula, no spread sizer, no hedge sizer, no risk gate. The single live model is GBM (`models/gbm.py`) producing `P(S_T > K)` for one strike vector; nothing logs would-quote prices anywhere. | missing | blocker | `models/registry.py:32-38` (only `gbm` builder live); `models/gbm.py:1-105`; `audit_A_cartography.md:213-228` (module inventory: no smoother / RND / overlay / spread / hedge module). | Milestone-1 deliverables are a precondition for any subsequent milestone per C10-82's gating discipline. |
| C10-79 | Milestone 2 (passive two-sided quoting): caps $500/bucket and $5 000/Event; symmetric quotes ≥4¢ each side; subscribe `orderbook_delta`/`ticker`/`trade`/`fill`/`user_orders`; amend-not-cancel; `DELETE /orders/batch` plus order-group trigger as kill switch (`audit_C_phase10_strategy_synthesis.md:91`). | None of the bucket caps, channel subscriptions, amend logic, or kill-switch wiring exists; the Pyth WS subscribe message at `feeds/pyth_ws.py:130` only handles `{"type": "subscribe", "ids": [...]}` — a Pyth-Hermes shape, not a Kalshi shape. | missing | blocker | `feeds/pyth_ws.py:130`; `audit_A_cartography.md:108-115`. | The claim doubles up on C09-71 / C09-72 kill-switch primitives. |
| C10-80 | Milestone 3 (CME hedge loop): FCM API; hedge net Δ ≥ 1 ZS; reconcile Kalshi `GET /portfolio/positions` against FCM execution reports three times per session (`audit_C_phase10_strategy_synthesis.md:92`). | No FCM client (no Interactive Brokers / AMP / Tradovate import), no delta tracker, no reconciliation; `state/basis.py:1-48` carries an annualised Pyth↔CME drift only and does not represent a position. | missing | blocker | `audit_A_cartography.md:108-115`; `state/basis.py:19-48`. | The claim requires a hedging engine the cartography reports as wholly absent. |
| C10-81 | Milestone 4: scenario caps; Grafana / Prometheus / PagerDuty; hot-standby quoter; Advanced/Premier rate-limit tier; Kalshi MM Program application (`audit_C_phase10_strategy_synthesis.md:93`). | No Prometheus client (`prometheus_client` not in `pyproject.toml:9-20`); no Grafana provisioning; no PagerDuty integration; no `metrics/` module; no failover topology. | missing | major | `pyproject.toml:9-20`; `audit_A_cartography.md:18-29` (full runtime dep list, no metrics dependency). | Severity major (not blocker) because milestone 4 is an "ops hardening" milestone and prerequisite milestones M0–M3 are themselves missing — the metrics/alerting layer is downstream of work the code has not yet started. |
| C10-82 | Milestone gating discipline: M_n is not declared complete until M_{n+1}'s gating tests pass on the data produced by M_n (`audit_C_phase10_strategy_synthesis.md:94`). | No milestone gating in code, no test marker, no benchmark threshold tied to milestone IDs; `tests/test_benchmarks.py` asserts only static budgets per `audit_A_cartography.md:184-188`. | missing | major | `audit_A_cartography.md:184-188`; `pyproject.toml:35-38` (pytest config has no markers beyond `asyncio_mode`). | Discipline is a process artefact more than a code artefact, but the claim is explicitly that prior-milestone data must drive next-milestone tests. |
| C02-84 | Practitioners measure adverse selection via rolling realised spreads / post-trade markout at 1s, 5s, 60s rather than PIN/VPIN (`audit_C_phase02_pricing_models.md:94`). | Same gap as C10-50: no fill stream → no realised spread → no markout. The pricer never sees fills. | missing | major | `engine/pricer.py:42-89`; `audit_A_cartography.md:213-228`. | Co-located with C10-50; cited separately because Phase 02 frames it as a research-corpus invariant predating the Kalshi-specific synthesis. |
| C05-66 | VPIN as a liquidity-withdrawal trigger around USDA-report releases (`audit_C_phase05_systematic.md:90`). | No VPIN, no flow-toxicity computation, no quote-pull trigger; `engine/event_calendar.py` carries no USDA windows for soybean. | missing | minor | `engine/event_calendar.py:30-38, 76-79`. | Minor because the research claim is a "pull-off" heuristic; the absence is bounded by the broader missing event-window surface (C09-40 / C10-70). |
| C06-86 | The CME Daily Bulletin is a reconciliation/calibration input (unreported blocks, EFPs, OI deltas) rather than a quoting input (`audit_C_phase06_data_streams.md:96`). | No Daily Bulletin parser, no `cme/`, no FTP/HTTP client for CME publications. | missing | minor | `audit_A_cartography.md:108-115`. | Calibration use; bound by the empty `calibration/` package. |
| C07-99 | Kalshi tiered leaky-bucket rate limits Basic 200/100 → Prime 4 000/4 000 (`audit_C_phase07_kalshi_contract.md:109`). | No rate-limit pacer, no token bucket, no per-tier configuration; YAML config has no `rate_limit_tier` field (`config/commodities.yaml`, `config/pyth_feeds.yaml`). | missing | blocker | `audit_A_cartography.md:108-115`; `config/commodities.yaml:6-30`; `config/pyth_feeds.yaml:1-16`. | Without a pacer, even Phase-1 paper trading on the live demo would stall on 429s during a release window (per C10-76). |
| C07-101 | Over-quota: HTTP 429 with no `Retry-After`; clients must implement exponential backoff (`audit_C_phase07_kalshi_contract.md:111`). | The only backoff in the repo is the linear `reconnect_backoff_s * attempt` at `feeds/pyth_ws.py:144-145` — linear, not exponential, and tied to the Pyth WS, not Kalshi REST. | missing | major | `feeds/pyth_ws.py:140-145`. | A linear-not-exponential backoff against a leaky-bucket-without-Retry-After would not even satisfy the Pyth path under sustained pressure. |
| C08-97 | Quoting engine maintains a deterministic event calendar with per-event multiplicative spread/width parameters $(\kappa_t^{\text{spread}}, \kappa_t^{\text{width}})$ (`audit_C_phase08_synthesis_pricing.md:122`). | `config/commodities.yaml:6-30` exposes `event_calendar[].vol_adjustment` per commodity, but no Python module reads that field. The registry (`models/registry.py`) reads `model` and `stub` only; the pricer (`engine/pricer.py`) does not branch on event windows. | partial | major | `config/commodities.yaml:6-30`; `models/registry.py:48-65`; `engine/pricer.py:50-89`. | Schema exists in YAML, no consumer in code → "partial" by virtue of declared shape, "missing" by virtue of behaviour. |
| C08-100 | Pipeline stage A — stream CME MDP 3.0 tick-by-tick for ZS futures and ZS options; PCP-prune outliers (`audit_C_phase08_synthesis_pricing.md:125`). | No MDP 3.0 ingest, no Databento client, no put-call-parity check; only Pyth Hermes WebSocket is implemented (`feeds/pyth_ws.py:128-145`). | missing | major | `audit_A_cartography.md:104-112` (single external service: Pyth Hermes). | The CME-side feed is what feeds the RND construction; without it, the entire downstream pipeline is starved. |
| C08-111 | Pipeline stage L — weekly P&L attribution across quoting edge / inventory MTM / hedge carry-slippage / fee drag, fed back into $(A_i, k_i, \gamma)$ (`audit_C_phase08_synthesis_pricing.md:136`). | No P&L module, no inventory MTM, no fee accounting, no calibration target for $(A_i, k_i, \gamma)$ — `models/registry.py:32-38` only ever instantiates `GBMTheo` and never reads such parameters. | missing | major | `audit_A_cartography.md:60-63`; `models/registry.py:32-38, 48-65`. | The feedback loop closure is what turns observability into a parameter-update signal; without P&L attribution, the observability layer would be read-only. |

## 3. Narrative discussion of blockers and majors

### 3.1 The empty side of the wire

Every blocker in the table reduces to one structural fact: the repository
implements the *upstream* data-acquisition leg for one venue (Pyth
Hermes) and has no code at all on the *downstream* execution-and-control
leg (Kalshi REST + WebSocket; FCM API for the CME hedge). The
cartography records this directly: "**CME / options chains / Kalshi API
/ macro feeds** — referenced in the `README.md:39` layout text and in
`research/` but not implemented anywhere in the code"
(`audit_A_cartography.md:110-112`). Phase 09 organises its kill-switch,
reconciliation, and rate-limit-headroom claims around endpoint paths
(`DELETE /orders/batch`, `POST /order-groups/{group_id}/trigger`,
`GET /portfolio/{positions,fills,balance,settlements}`) the codebase
never calls. The HTTP client for those endpoints (`httpx >= 0.27`) is
declared as a pinned runtime dependency at `pyproject.toml:18` but the
cartography's Red Flag 3 (`audit_A_cartography.md:246-249`) confirms it
is unused; the same is true of `structlog` (`pyproject.toml:20`,
declared but no importer), so the *signal* "we have a JSON-structured
logging stack" is a `pyproject` artefact, not a runtime artefact.

This is the single largest concentration of `missing`-classed
observability claims in the audit. C09-71, C09-72, C09-79, C09-80,
C09-81, C10-79, C10-80, C07-99, C07-101 all collapse to one engineering
gap: there is no Kalshi REST client. C10-78 collapses to the same gap
on the *modelling* side (no smoother, no RND extractor, no spread
sizer, no risk gate); C10-80 collapses to the same gap on the *hedge*
side (no FCM client). Until at least one of those clients exists, every
observability primitive layered on top of them — heartbeat-fail kill
trigger, three-times-per-session reconciliation, tick-to-quote latency
histogram — has no foothold.

### 3.2 The single live observability surface: `feeds/pyth_ws.py`

The repository's lone observability surface is the module-level logger
in `feeds/pyth_ws.py`. The audit's Phase B deep-dive isolates the
calls: `log.info("pyth.connected endpoint=%s feeds=%d", …)` at
`feeds/pyth_ws.py:131` and `log.warning("pyth.reconnect attempt=%d
err=%s", …)` at `feeds/pyth_ws.py:144`
(`audit_B_feeds-pyth.md:355-358`). The logger name is hardcoded as
`logging.getLogger("goated.feeds.pyth")` at `feeds/pyth_ws.py:31`
rather than `__name__` (`audit_B_feeds-pyth.md:460-463`). Format is
`%`-style printf, not structured JSON; `structlog` is not in scope
even though `pyproject.toml:20` requires it. There is no log handler
configuration anywhere in the repo, so under any Python default the
two log calls go to `stderr` with the root-logger format — useful
in tests, opaque in production.

That two-call surface produces no metric. The `attempt` counter at
`feeds/pyth_ws.py:138-145` is a local variable that resets to zero
every successful `async with websockets.connect(…)`
(`feeds/pyth_ws.py:129`); per `audit_B_feeds-pyth.md:469-473`, the
counter resets immediately after the `async with` enters, so a brief
open-then-close that lands a subscribe but no data still resets the
budget. Even if a future kill-switch consumed the counter, the reset
semantics would defeat the C09-73 reconnect-rate kill trigger
("WebSocket reconnects more than K times in a minute"): the counter
resets per connection, not per minute, and is not surfaced past the
log line. This makes the Pyth WS the closest analogue to any kill-
switch input the repo has, and it does not satisfy C09-73 even on
its own venue, let alone the missing Kalshi venue.

### 3.3 Latency: harness, not runtime

Phase 09's tick-to-quote budget (40-60 ms across five legs, C09-58) is
the most quantitative observability claim in the corpus. The repository
*does* measure latency, but only in `benchmarks/run.py:68-70` via
`time.perf_counter_ns()` around a synthetic 50-market full-book builder
(`audit_A_cartography.md:226`). The output is asserted against static
budgets in `tests/test_benchmarks.py` (`audit_A_cartography.md:184-188`)
and reported in prose in `README.md:10-20`. The cartography's Red Flag
13 records the consequence: "no automation re-computes and updates the
README; it is a snapshot, not a build artefact"
(`audit_A_cartography.md:294-296`). There is no histogram emitter, no
`prometheus_client.Histogram`, no per-stage timer in the hot path
`engine/pricer.py:42-89`. C09-58 enumerates five legs (WebSocket
delta, density refresh, reservation-price compute, amend call, ack);
the code measures one (model compute) and only at offline-pytest time.
That mapping is `partial`, severity `major`: the leg the harness
covers is the one the research treats as cheapest (≪1 ms),
and the four legs the research treats as expensive (10-20 ms each)
are uncovered.

### 3.4 Kill-switch: no consumer, no producer, no transport

C09-73's four-trigger taxonomy was the most aggressive observability
specification in the audit. Trigger-by-trigger: (i) "aggregate signed
delta across the bucket strip" — there is no inventory module and no
delta accountant in the repo, the closest module being `state/basis.py`
which represents an annualised Pyth↔CME drift, not a position
(`state/basis.py:19-48`); (ii) "absolute intraweek PnL drawdown" — no
P&L module, no fill stream, the registry only ever instantiates
`GBMTheo` (`models/registry.py:32-38`); (iii) "CME hedge connectivity
fails heartbeat for N seconds" — no FCM client, no heartbeat,
N is undefined per the research itself
(`audit_C_phase09_kalshi_stack.md:100`); (iv) "Kalshi WebSocket
reconnects more than K times in a minute" — no Kalshi WebSocket and
no time-windowed counter; the Pyth-side analogue is a per-connection
local int that resets at `feeds/pyth_ws.py:129`. The kill-switch
*action* layer is also empty: C09-71 (`DELETE /orders/batch`) is the
specified way to flush every open order in a single request, and the
repo has no HTTP client to issue it.

The Phase B audit on `engine/scheduler.py` (the closest thing to a
runtime control plane) makes the gap explicit: "The `Priority` enum at
`engine/scheduler.py:21-26` has no entries for
`tick_publisher_floor_breach`, `quote_cancel`, `risk_kill`, or similar
safety-class events"
(`audit_B_engine-scheduler.md:539-546`). The scheduler has no producer
either — "No producer pushes to the queue and no consumer task wraps
`run()`. The module is dead code at the import graph level"
(`audit_B_engine-scheduler.md:214-217`). A kill-switch with no event
type, no producer, no consumer, no transport, and no destination
endpoint is missing, not partial; classifying the cluster as blocker.

### 3.5 Reconciliation: README promise versus filesystem reality

C09-79 and C10-80 both prescribe three-times-per-session reconciliation
between Kalshi `/portfolio/*` and the FCM execution reports.
`audit_B_validation-sanity.md:474-480` quotes the README claim
(`README.md:44`) — "validation/ — Backtest, Pyth↔CME reconciliation,
pre-publish sanity checks" — and observes that "Only the third exists
in code today; the cartography notes the same gap at
`audit/audit_A_cartography.md:81-83`". The `validation/__init__.py` is
empty (`audit_B_validation-sanity.md:479-480`). There is no `recon/`,
no `reconcile.py`, no `state/positions.py`, no Kalshi position object,
no FCM execution-report parser. C09-80's reconciliation table schema
keyed by `(event_ticker, timestamp, side)` has no place to land
because the repo has no persistent store: "No database (SQL, Redis,
kdb, Arctic, etc.)" (`audit_A_cartography.md:113-115`). DuckDB +
Parquet on S3 is what Phase 09 §7.2 recommends (C09-64), but
`grep -rn 's3\|parquet\|duckdb' --include='*.py'` returns zero hits
in the source tree. Severity blocker on C09-79; major on C09-80
because the table's schema absence is a consequence of the
reconciliation-loop absence rather than an independent concern.

### 3.6 Event-window observability: schema present, no consumer

C09-40 (WASDE widening), C08-97 (event-day κ multipliers), C10-70
(WASDE-window adverse-selection markout fingerprint), and C05-66
(VPIN as USDA-window withdrawal trigger) all rely on the engine being
*aware* that a release window is in progress. The
`config/commodities.yaml` schema does carry an `event_calendar[]` field
per `audit_A_cartography.md:148-152`: name, day_of_week, time_et,
vol_adjustment. No Python module reads it. `models/registry.py:48-65`
reads only `model` and (per Red Flag 7 at
`audit_A_cartography.md:264-269`) the `stub` flag. `engine/pricer.py:50-89`
reads `pyth_max_staleness_ms` and `pyth_min_publishers` from
`cfg.raw` and nothing else. `engine/event_calendar.py:30-38, 76-79`
hardcodes WTI session windows and has no per-commodity event schedule
(Red Flag 14 at `audit_A_cartography.md:298-301`: "every other
commodity in `config/commodities.yaml` will raise `NotImplementedError`
… even the ones with `stub: true`"). C08-97 is therefore classed
`partial`: schema exists, behaviour absent. C09-40, C10-70, C05-66 are
classed `missing` because each requires a different secondary surface
(quote-widening multipliers, markout fingerprints, VPIN) on top of the
not-yet-consumed event-calendar shape.

### 3.7 The forward-capture asset

C09-24 and C09-63 deserve their own paragraph because the research
explicitly flags "every missed day is permanently missed"
(`audit_C_phase09_kalshi_stack.md:73`). Capture is the one
observability primitive whose absence causes irreversible asset loss:
unlike a missing alert (which can be added later) or a missing kill-
switch (which can be retro-fitted before live trading), missing
order-book history is gone forever. The repository has no Kalshi
WebSocket client, no S3 sink, no Parquet writer, no DuckDB consumer,
no per-bucket archive. The cartography (`audit_A_cartography.md:108-115`)
and Phase B (`audit_B_state-tick-store.md` per cross-reference) confirm
the absence. Severity blocker on C09-63 because the asymmetric cost
(immediate, irrecoverable) is the highest in the audit. The research's
Milestone 0 (offline reproduction, C10-77) requires *historical CBOT
option chains*, which is buyable via Databento Standard at $199/month;
Milestone 1+ require *Kalshi tick history*, which is not buyable at
any price and must be captured forward. The repo today captures
neither.

### 3.8 Why no claim is `already-good`

No row in the audit table carries the `already-good` class because no
Phase C observability claim has a matching code-side implementation
that meets the research description. The two existing `feeds/pyth_ws.py`
log calls are infrastructure-event lines that no Phase C claim
specifically requests; the `source_tick_seq` provenance counter at
`models/base.py:20` and `state/tick_store.py:5-6` is good practice but
unmatched by any named research claim; the staleness-gating mechanism
in `state/iv_surface.py:43-46`, `state/basis.py:43-46`, and
`engine/pricer.py:55-65` is similarly unmatched. Per the audit prompt's
"Do NOT classify a gap as `already-good` without evidence", the
absence of a research-claim-to-code-call match precludes that class
for any row.

## 4. Ambiguities

**A1 — Where does `SanityError` go?** `validation/sanity.py:32-67` raises
`SanityError` for any invariant violation; `engine/pricer.py:89` calls
`self.sanity.check(output, …)` and propagates. `audit_B_validation-
sanity.md:509-515` records the open question: "What is the intended
publish-time policy on `SanityError`?" The publish layer does not exist,
so whether a sanity violation is meant to drop a quote, suspend a
market, page someone, or restart the model is unspecified. This sits
adjacent to the kill-switch gap (C09-71 / C09-73): a `SanityError` is
the closest thing to a "pull-quotes" trigger the repo has, and its
catch-and-act side is undefined.

**A2 — Is the `attempt` counter at `feeds/pyth_ws.py:138-145` a kill-
switch input or a diagnostic?** The Phase 09 claim C09-73 (iv) wants a
"Kalshi WS reconnects > K/min" trigger; the Pyth-side counter is the
nearest analogue but resets per connection (`audit_B_feeds-pyth.md:469-
473`). Whether the maintainer intended this counter to feed a future
control-plane is unclear, and the reset semantics would have to change
to support the research's per-minute-windowed semantics.

**A3 — Does `event_calendar[].vol_adjustment` in
`config/commodities.yaml` represent C08-97's `κ_t^width`?** The schema
key carries one numeric field per event; C08-97 names two parameters
($\kappa_t^{\text{spread}}, \kappa_t^{\text{width}}$). Whether the YAML
field is a single multiplier on both legs, a width-only multiplier with
a separate spread multiplier elsewhere, or a placeholder pending
schema evolution is not derivable from code.

**A4 — Is the `calibration/params/*.json` artefact format C10-51's
"per-bucket alpha" persistence target?** `.gitignore:21-22` excludes
`*.json` from `calibration/params/`; `audit_A_cartography.md:289-292`
records that "the intended artifact format is implied by `.gitignore`
rather than by any producer code." The reader cannot tell whether this
slot is for jump-MLE outputs, HMM transition matrices, IV strips, or
per-bucket adverse-selection alphas — all four are named in the README
and one is implied by C10-51, but no producer code or schema disambiguates.

**A5 — Does `source_tick_seq` count as the trace-level provenance for
C09-80's reconciliation table?** `models/base.py:20` and
`state/tick_store.py:5-6` describe the field as "so a theo can be traced
to the driving tick." C09-80 keys reconciliation by
`(event_ticker, timestamp, side)`. The two are different keys — the
first is a per-process monotonic counter, the second is a venue-level
identity. Whether the maintainer plans to map `source_tick_seq` into
the reconciliation key, ignore it, or carry both is unclear.

## 5. Open questions for maintainers

**Q1.** What is the expected publish destination for the two existing
log calls at `feeds/pyth_ws.py:131, 144` in production? `structlog`
is declared in `pyproject.toml:20` but unused; is the intent to swap
the stdlib logger for a structlog `BoundLogger` before any kill-switch
or reconciliation logic lands, or are the two info/warn lines
considered the steady-state observability surface for the feed?

**Q2.** Is the `validation/` package intended to host
"backtest, Pyth↔CME reconciliation" alongside `sanity.py` per the
README, or has the scope been narrowed since the README was written?
`audit_B_validation-sanity.md:539-543` raises this; the answer affects
whether C09-79 and C09-80 are short-term work or out-of-scope-for-
goated.

**Q3.** What is the intended lifecycle for `engine/scheduler.py`?
It is dead at the import graph level
(`audit_B_engine-scheduler.md:214-217`); the docstring at
`engine/scheduler.py:8-9` references `feeds/pyth_ws` as the producer-
to-be (now implemented but bypassing the scheduler per
`audit_B_engine-scheduler.md:222-228`). If the scheduler is to host
kill-switch fan-out (C09-73 → producer; C09-71 / C09-72 → consumer),
the `Priority` enum at `engine/scheduler.py:21-26` would need entries
for `risk_kill` / `quote_cancel` / similar; if not, where is the
control-plane host module expected to live?

**Q4.** What is the intended persistent-store substrate for
forward-captured Kalshi ticks (C09-24, C09-63) and the reconciliation
table (C09-80)? The cartography records no SQL/Parquet/Arctic
dependency; Phase 09 §7.2 (C09-64) recommends DuckDB + Parquet on S3.
Has a substrate decision been made, or is it pending Milestone-1
delivery?

**Q5.** What N (hedge-heartbeat seconds) and K (Kalshi WS
reconnects/minute) thresholds are intended for the C09-73 kill-switch?
The research itself defers these as "caller-configurable"
(`audit_C_phase09_kalshi_stack.md:100`); a target-config draft would
unblock the kill-switch implementation work.

**Q6.** Is `event_calendar[].vol_adjustment` meant to satisfy C08-97's
$\kappa^{\text{width}}$, $\kappa^{\text{spread}}$, both, or neither?
A schema clarification on the YAML field would let the consumer in
`engine/pricer.py:50-89` be drafted against a specified shape rather
than guessed.

**Q7.** What is the intended fan-out path for `SanityError`
(`validation/sanity.py:32-67`) at the publish boundary that does not
yet exist? Quote-drop, market-suspend, page, or restart-model are
mutually exclusive choices and each implies a different control-plane
shape; the answer constrains the kill-switch design (C09-71 / C09-73).

**Q8.** Are the unused dependencies at `pyproject.toml:18-20`
(`httpx`, `structlog`, `python-dateutil`, `pytz`) reserved for a
near-term Kalshi/REST-client work item, or are they vestiges? The
answer informs whether the gap on C07-99 / C07-101 / C09-71 is
weeks-out or unscoped.

---

*End of audit_D_observability.md.*
