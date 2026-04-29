# Phase 80 — Live Small Deployment: Handoff

**Date:** 2026-04-28
**Action:** LIVE-DEPLOY
**Status:** COMPLETE

---

## What was delivered

### 1. `deploy/main.py` — Main entry point (520 LoC)
Wires all components into a single-process market maker:
- **Startup:** Connects Kalshi REST + IB Gateway, pulls initial CME chain, reconciles positions.
- **Main loop (30s cycle):** CME refresh -> RND pipeline -> orderbook pull -> settlement gate -> taker imbalance -> quoter -> order execution -> fill processing -> hedge check -> kill switch -> PnL logging.
- **Shutdown:** Cancels all resting orders, disconnects IB, writes PnL CSV.
- **Signal handling:** SIGINT/SIGTERM trigger graceful shutdown.
- **Configuration:** All parameters externalized via YAML + env vars.

### 2. `deploy/config.yaml` — Deployment configuration
- Series: KXSOYBEANMON (ZS, hedge_enabled=true)
- Capital cap: $1,000 max (risk.max_total_inventory_usd)
- Risk limits: 500 aggregate delta, 200 per-event, 5% PnL kill
- Quoter: 2c half-spread (4c total), 0.1 skew gamma
- Loop: 30s cycle, 15min CME refresh

### 3. `attribution/pnl.py` — PnL attribution (200 LoC)
- Per-fill tracking with spread_capture, adverse_selection, hedge_slippage, kalshi_fees, ib_fees.
- Hourly aggregation. Daily summary.
- CSV output to `output/pnl/`.

### 4. `deploy/README.md` — Operational runbook
Covers: prerequisites, start/stop, adding series, kill switch fired, daily PnL check, weekly reconciliation, config reference.

### 5. `tests/test_integration.py` — 30 integration tests
- Config loading (3 tests)
- Quoter integration with RND (3 tests)
- Capital cap enforcement (2 tests)
- Kill switch end-to-end (4 tests)
- Position tracking (5 tests)
- Settlement gate integration (2 tests)
- Taker imbalance (2 tests)
- PnL attribution (3 tests)
- MarketMaker init (4 tests)
- Full cycle simulation (2 tests)

### 6. `feeds/kalshi/client.py` — Added `get_orders()` method
New method to query resting orders (needed for open-order tracking).

---

## Test results

- **Integration tests:** 30/30 pass
- **Full suite:** 848/848 pass (up from 818 pre-Phase 80)
- **Lint:** clean (ruff)

---

## Architecture decisions

1. **Single-process, synchronous main loop** per non-negotiable. asyncio for I/O only.
2. **Config via YAML + env vars.** Secrets (API keys) via env vars only.
3. **Capital cap enforced at two levels:** risk gate (RiskLimits.max_loss_cents) + explicit check in cycle.
4. **Kill switch has 3 triggers:** risk breach, IB disconnect + delta, PnL drawdown.
5. **Order lifecycle:** cancel-and-replace each cycle (simple, no incremental updates).
6. **PnL to CSV** for first deployment (lightweight; DuckDB can be added later).

---

## Known limitations

1. **Single series:** Only the first series in config is active. Multi-series requires loop extension.
2. **No persistent position state:** Position store is in-memory. On restart, reconciles from Kalshi API.
3. **Orderbook parsing:** Market ticker construction assumes `{event_ticker}-{strike_int}` format — verify against live API response.
4. **No WS integration:** Uses REST polling (30s cycle). WS fill/orderbook updates would reduce latency.
5. **PnL attribution simplified:** Model fair not always available at fill time; spread capture is approximate.

---

## Pre-flight checklist (before going live)

- [ ] IB Gateway running with CME futures permission
- [ ] Kalshi production API keys configured
- [ ] Paper-trade for 1 week on KXSOYBEANMON
- [ ] Verify market ticker format against live Kalshi API
- [ ] Verify CME chain pull works with current date
- [ ] Set capital to $200 for first day, scale up over 2 weeks
- [ ] Monitor logs for kill switch triggers
- [ ] Daily PnL review for first 2 weeks

---

## Files changed

| File | Action |
|---|---|
| `deploy/__init__.py` | NEW |
| `deploy/main.py` | NEW |
| `deploy/config.yaml` | NEW |
| `deploy/README.md` | NEW |
| `attribution/__init__.py` | NEW |
| `attribution/pnl.py` | NEW |
| `tests/test_integration.py` | NEW |
| `state/action_live_deploy/plan.md` | NEW |
| `state/action_live_deploy/handoff.md` | NEW |
| `feeds/kalshi/client.py` | MODIFIED (added get_orders) |
