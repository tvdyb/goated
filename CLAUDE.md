# CLAUDE.md — goated

## Identity

Asymmetric market-making system on Kalshi commodity monthly markets (`KXSOYBEANMON` first), priced against a synthetic GBM (with IBKR-sourced RND pipeline as upgrade path), hedged on Interactive Brokers (when available). Operating under strategic frame **F4** (see `prompts/build/PREMISE.md`).

**Status: LIVE.** First deployment on KXSOYBEANMON completed 2026-04-28. Running with synthetic RND (no CME data yet), no hedge (no IBKR yet). IBKR account opened, pending market data subscription + IB Gateway setup.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install flask ib_insync
pytest                       # run all tests (~848)
ruff check .                 # lint (config in pyproject.toml)
```

## Running the bot

```bash
# Set API keys
export KALSHI_API_KEY="your-key"
export KALSHI_PRIVATE_KEY_PATH="/path/to/private_key.pem"

# Run market maker ($50 test config)
python -m deploy.main --config deploy/config_test.yaml

# Run dashboard (separate terminal, same env vars)
python -m deploy.dashboard
# Opens at http://localhost:5050
```

## Repo layout

```
deploy/        Live deployment: main loop, config, dashboard, runbook
deploy/main.py Main entry point — wires all components into 30s trading loop
deploy/dashboard.py Flask web dashboard (localhost:5050)
deploy/config.yaml Production config ($1000 cap)
deploy/config_test.yaml Test config ($50 cap, 3 contracts/strike)
attribution/   PnL attribution tracker (CSV output)
engine/        Quoter, RND pipeline, corridor, event calendar, CBOT settle, kill switch, risk gates
engine/rnd/    RND pipeline: Breeden-Litzenberger, SVI, Figlewski, bucket integrator
engine/quoter.py Adaptive spread-capture quoter (penny-inside incumbent spreads)
engine/settlement_gate.py USDA event calendar + pre-release pull-all
engine/taker_imbalance.py Rolling-window taker-imbalance detector
feeds/         Data ingestion — Pyth WS, Kalshi REST client, CME options chain
feeds/kalshi/  Kalshi REST client, RSA-PSS auth, rate limiter, WS, orders, ticker, events, capture
feeds/cme/     CME EOD options chain puller + expiry calendar (currently blocked by CME anti-scraping)
fees/          Kalshi fee model
hedge/         IBKR hedge leg: client, delta aggregator, sizer, trigger
models/        Pricing model contract (base.py), GBM pricer, YAML-driven registry
state/         In-memory state (positions) + .md state files for prompt stack
config/        commodities.yaml (per-commodity overrides), pyth_feeds.yaml
calibration/   Empty stub — future offline nightly jobs
validation/    Pre-publish sanity checks
analysis/      LIP viability analysis
audit/         Six-phase audit (A-F) — read-only references
prompts/       Prompt stack for cross-context-window execution
research/      Long-form research docs; not imported by code
tests/         pytest suite — 848 tests
mm-setup-main/ Friend's reference MM implementation
```

## Current state

- **Phase 80 complete**: live deployment wired and tested on real Kalshi API.
- **848 tests passing** across all modules.
- **First live run**: 2026-04-28 on KXSOYBEANMON-26APR3017. Got fills, positions tracked, kill switch fired correctly.
- **Pricing**: synthetic GBM (forward from Kalshi quotes, 15% vol). Upgrade to IBKR-sourced CME options chain pending.
- **Hedge**: not active (IBKR account opened, IB Gateway not yet configured).
- **LIP**: 0.5x liquidity incentives just launched for KXSOYBEANMON.
- **Key learning**: adverse selection is real without proper data source. Need real IV surface from IBKR.
- See `state/PROJECT_CONTEXT.md` for full history.
- See `state/action_live_deploy/handoff.md` for deployment details.

## Main loop (deploy/main.py)

Every 30 seconds:
1. Cancel all resting orders (pull fresh list from API)
2. Get active KXSOYBEANMON event + strike grid from Kalshi
3. Compute fair values via synthetic GBM (or RND pipeline when CME data available)
4. Pull orderbooks for all 20 strikes
5. Check settlement gate (USDA event calendar)
6. Check taker imbalance
7. Run quoter — adaptive penny-inside spreads
8. Place orders via Kalshi REST (post_only=True)
9. Process fills, update position store
10. Check hedge trigger (if IBKR connected)
11. Check kill switch (risk breach, PnL drawdown)
12. Log PnL attribution

## Kalshi API quirks (discovered during live deployment)

- **Ticker format**: `KXSOYBEANMON-26APR3017-T1186.99` (not the `SERIES-YYMONDD-INDEX` format from docs)
- **Event ticker field**: `event_ticker` (not `ticker`) in events response
- **Order creation**: do NOT send `time_in_force: "gtc"` — causes 400. Omit it (server defaults to GTC)
- **Orderbook**: response key is `orderbook_fp` with `yes_dollars` and `no_dollars` arrays of `[price_str, size_str]`
- **Prices**: dollars as strings (e.g. `"0.4500"`) in responses, cents as integers in order creation (`yes_price: 45`)
- **Positions**: `position_fp` is a float string (e.g. `"11.00"`), not integer
- **Batch cancel**: `DELETE /portfolio/orders/batch` returns 404 — endpoint may not exist. Use individual cancels.
- **Rate limiting**: hits 429 after ~22 rapid POST requests. 1s backoff resolves it.

## Key paths

| File | Purpose |
|---|---|
| `deploy/main.py` | Main entry point — run with `python -m deploy.main` |
| `deploy/config_test.yaml` | $50 test config (3 contracts/strike, no hedge) |
| `deploy/dashboard.py` | Live web dashboard at localhost:5050 |
| `deploy/README.md` | Operational runbook |
| `prompts/build/PREMISE.md` | Canonical F4 strategic premise |
| `state/PROJECT_CONTEXT.md` | Current state + resumption pointer |
| `state/action_live_deploy/handoff.md` | Phase 80 deployment details |
| `config/commodities.yaml` | Per-commodity config |
| `audit/audit_F4_refactor_plan_asymmetric_mm.md` | Full F4 plan |

## Module status

**Live (deployed, tested against real Kalshi API):**
- `deploy/main.py` — main trading loop, synthetic RND, order management
- `deploy/dashboard.py` — Flask web dashboard
- `attribution/pnl.py` — PnL attribution tracker
- `engine/quoter.py` — adaptive spread-capture quoter (penny-inside)
- `engine/settlement_gate.py` — USDA event calendar + gate
- `engine/taker_imbalance.py` — rolling-window taker-imbalance detector
- `engine/kill.py` — kill-switch with risk + PnL drawdown triggers
- `engine/risk.py` — risk gates (delta cap, per-Event, max-loss)
- `state/positions.py` — position store with fill dedup + reconciliation
- `feeds/kalshi/client.py` — REST client with RSA-PSS auth, rate limiter, retry
- `fees/kalshi_fees.py` — fee model
- `feeds/pyth/client.py` — Pyth Hermes REST client for real-time ZS futures price
- `feeds/pyth/forward.py` — forward price provider (polls Pyth, falls back to Kalshi-inferred)

**Built but not yet used in live (need IBKR):**
- `engine/rnd/pipeline.py` — full RND pipeline (BL -> SVI -> Figlewski -> bucket)
- `feeds/cme/options_chain.py` — CME EOD chain puller (blocked by CME anti-scraping; will use IBKR API instead)
- `hedge/ibkr_client.py` — IB Gateway async wrapper
- `hedge/delta_aggregator.py` — portfolio delta computation
- `hedge/sizer.py` — ZS futures hedge sizer
- `hedge/trigger.py` — threshold-triggered hedge with kill-switch integration

**Wave 0 infrastructure (verified, carried forward):**
- `feeds/kalshi/` — auth, rate_limiter, ws, orders, ticker, events, capture, lip_pool, lip_score
- `engine/event_calendar.py` — 24/7 calendar with Friday-holiday roll
- `engine/cbot_settle.py` — settle resolver + roll calendar
- `engine/corridor.py` — corridor decomposition
- `models/gbm.py` — numba-JITed GBM pricer
- `validation/sanity.py` — pre-publish invariant checker

**Stub / empty:**
- `calibration/` — future: vol calibration, IV strip from IBKR

## Next steps (priority order)

1. **IBKR IB Gateway setup** — connect, subscribe to CME ag data (~$10/mo), pull real ZS options chain
2. **Replace synthetic RND with IBKR-sourced pipeline** — real IV surface → accurate fair values
3. **Auto-calibrate vol from Kalshi quotes** — interim improvement before IBKR data flows
4. **Paper-trade hedge leg** — validate delta hedging on IBKR paper account
5. **Fix duplicate order accumulation** — resolved but needs monitoring
6. **Multi-series** — add KXCORNMON once soy is stable

## Kill criteria (F4)

- **KC-F4-01**: RND misses Kalshi-resolution by >3c on >50% of buckets across 4+ settled monthly Events.
- **KC-F4-02**: Settlement-gap losses exceed gross spread for 2 consecutive months.
- **KC-F4-03**: Annualized net P&L on deployed capital <5% for 6 consecutive months.
- **KC-F4-04**: Monthly IB commissions + slippage exceed monthly Kalshi spread capture on hedgeable series.
- **KC-F4-05**: Realized markout on filled quotes exceeds 60% of captured spread for 4 consecutive weeks.

## Non-negotiables

- No `pandas` in the hot path; no Python loops over markets/strikes.
- No Monte Carlo in the hot path; MC for offline validation only.
- No silent failures: stale data, out-of-bounds IV, feed dropouts -> raise, don't publish.
- `scipy.special.ndtr` over `scipy.stats.norm.cdf`.
- `numba.njit` on all hot-path math.
- Synchronous main loop; `asyncio` for I/O only.
- Every order placed is `post_only=True`. Crossing the spread negates any economic edge.
- The fail-safe pattern at `engine/pricer.py:62-75` and `validation/sanity.py:38-68` is the template every new module follows.

## Do not

- **Do not** import `pandas` in any module under `engine/`, `feeds/`, `models/`, `state/`, `validation/`. Use numpy.
- **Do not** use `scipy.stats.norm.cdf`. Use `scipy.special.ndtr`.
- **Do not** swallow exceptions or return default values on error. Raise explicitly.
- **Do not** use `asyncio` for computation. The main pricing loop is synchronous.
- **Do not** write Python-level `for` loops over strikes or markets in hot-path code.
- **Do not** place market orders or use `taker` side. All orders are `post_only=True`.
- **Do not** send `time_in_force` field in Kalshi order creation (causes 400).
- **Do not** use Kalshi batch cancel endpoint (returns 404). Cancel individually.
- **Do not** modify audit files (`audit/`). They are read-only references.
- **Do not** modify `prompts/build/PREMISE.md`. Only a strategic-pivot phase may change it.
