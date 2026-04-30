# CLAUDE.md — goated

## Identity

Asymmetric market-making system on Kalshi commodity monthly markets (`KXSOYBEANMON` first), priced against a synthetic GBM (with IBKR-sourced RND pipeline as upgrade path), hedged on Interactive Brokers (when available). Operating under strategic frame **F4** (see `prompts/build/PREMISE.md`).

**Status: LIVE on Mac Mini.** LIP-optimized mode running on KXSOYBEANMON since 2026-04-28. Forward from yfinance (ZSK26.CBT), vol from Kalshi-implied calibration with 16.29% fallback. Theo stack 13/18 phases complete. IBKR account opened, pending IB Gateway + CME data subscription.

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

# Run LIP-optimized mode (primary)
python -m deploy.lip_mode --config deploy/config_lip.yaml

# Run spread-capture mode (alternative)
python -m deploy.main --config deploy/config_test.yaml

# Run dashboard (separate terminal, same env vars)
python -m deploy.dashboard
# Opens at http://localhost:5050
```

## Mac Mini deployment (production)

Bot runs on Mac Mini via Tailscale. Access from anywhere:
- Dashboard: `http://100.95.127.115:5050`
- SSH: `ssh efloyal@100.95.127.115`
- Bot screen: `screen -r bot`
- Dashboard screen: `screen -r dash`
- Detach: Ctrl+A, release, D

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

- **Phase 80 complete + theo stack 13/18 phases done.**
- **1053 tests passing** across all modules.
- **LIP mode LIVE** on Mac Mini since 2026-04-28. Earning ~$13-26/day estimated LIP revenue.
- **Pricing**: synthetic GBM with yfinance forward (ZSK26.CBT, auto-updates every 60s) + Kalshi-implied vol calibration (16.29% fallback). Settlement time override for correct tau.
- **Theo stack built**: Pyth (dead for soy), implied vol, seasonal vol, markout tracker, WASDE density, weather skew, Goldman roll, IBKR chain puller (not connected).
- **Hedge**: not active (IBKR account opened, IB Gateway not yet configured).
- **LIP**: 0.5x liquidity incentives active on 7 KXSOYBEANMON strikes. Competitive — other bots penny war.
- **Key learnings**: Kalshi settles against front-month ZS (May ZSK26, NOT July ZSN26). Settlement time ≠ expiration time. Anti-spoofing must always be on. Desert markets need special handling.
- See `state/PROJECT_CONTEXT.md` for full history.
- See `prompts/theo/README.md` for theo stack status.

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
- **Rate limiting**: Basic tier = 200 read tokens/sec, 100 write tokens/sec (10 tokens/request). 20 reads/sec, 10 writes/sec effective.
- **Amend endpoint**: `POST /portfolio/orders/{id}/amend` returns 400. Fallback to cancel+place.
- **Settlement vs expiration**: `expiration_time` in market data is NOT settlement time. Settlement is earlier (e.g., April 30 5pm EDT vs May 7 expiration). Must use settlement override.
- **Front month**: Kalshi KXSOYBEANMON settles against the front-month ZS contract (currently ZSK26 May), NOT the next month (ZSN26 July). 14c spread between them.

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

**Live (deployed on Mac Mini):**
- `deploy/lip_mode.py` — LIP-optimized market maker with desert/active modes, anti-spoofing, anti-churn, size jitter, yfinance forward, rotational processing
- `deploy/main.py` — spread-capture market maker with full theo stack wired
- `deploy/dashboard.py` — Flask LIP dashboard with per-bucket positioning, markout, expandable orderbooks
- `engine/quoter.py` — adaptive spread-capture quoter (penny-inside)
- `engine/implied_vol.py` — Kalshi-implied vol calibration from ATM bid/ask
- `engine/markout.py` — per-bucket fill markout tracker (1m/5m/30m adverse selection)
- `engine/seasonal_vol.py` — monthly vol regime overlay
- `engine/settlement_gate.py` — USDA event calendar + gate
- `engine/taker_imbalance.py` — rolling-window taker-imbalance detector
- `engine/wasde_density.py` — post-WASDE density mean-shift (sensitivity 1.5c/Mbu)
- `engine/weather_skew.py` — GEFS weather → distribution skew (growing season only)
- `engine/goldman_roll.py` — Goldman roll window detection + drift
- `engine/kill.py` — kill-switch with risk + PnL drawdown triggers
- `engine/risk.py` — risk gates (delta cap, per-Event, max-loss)
- `state/positions.py` — position store with fill dedup + reconciliation
- `feeds/kalshi/client.py` — REST client with RSA-PSS auth, rate limiter, retry, amend
- `feeds/pyth/forward.py` — Pyth forward provider (soy feeds dead, WTI works)
- `feeds/usda/wasde_parser.py` — WASDE PDF/JSON parser
- `feeds/weather/gefs_client.py` — NOAA GEFS weather data client
- `feeds/ibkr/options_chain.py` — IBKR options chain puller (needs IB Gateway)
- `fees/kalshi_fees.py` — fee model
- `attribution/pnl.py` — PnL attribution tracker
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

1. **IBKR IB Gateway setup** — connect, subscribe to CME ag data (~$10/mo), pull real ZS options chain (T-45)
2. **Wire IBKR options chain → full RND pipeline** — real IV surface → accurate fair values (T-50)
3. **Validate RND vs synthetic on live fills** — prove RND reduces adverse selection (T-55)
4. **Update config for new contract** — when current KXSOYBEANMON settles, update `settlement_time`, `eligible_strikes`, `yf_ticker` (if month rolls)
5. **Merge LIP + spread-capture modes** — unified system that does MM normally and switches to LIP-optimized when incentives are active
6. **Explore other commodity markets** — KXCORNMON, expand LIP farming across more markets
7. **Full orderbook depth on dashboard** — expandable per-strike view (partially done)
8. **Theo stack integration test** (T-90) — validate all components work together

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
