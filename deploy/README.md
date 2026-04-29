# Operational Runbook: Goated Market Maker

## Prerequisites

1. **Python 3.11+** with venv:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Kalshi production API keys:**
   - Generate RSA key pair and register at Kalshi.
   - Set environment variables:
     ```bash
     export KALSHI_API_KEY="your-api-key-id"
     export KALSHI_PRIVATE_KEY_PATH="/path/to/kalshi_private_key.pem"
     ```

3. **IB Gateway** running locally:
   - Download IB Gateway from Interactive Brokers.
   - Configure for paper trading (port 4002) or live (port 4001).
   - Ensure CME futures permissions are active.
   - Override defaults if needed:
     ```bash
     export IB_GATEWAY_HOST="127.0.0.1"
     export IB_GATEWAY_PORT="4001"
     ```

4. **Capital allocation:** $1,000 max for first 2 weeks (enforced in config).

---

## Starting the system

```bash
source .venv/bin/activate
python -m deploy.main --config deploy/config.yaml --log-level INFO
```

The system will:
1. Connect to Kalshi REST API.
2. Connect to IB Gateway (if hedge_enabled).
3. Pull initial CME options chain.
4. Reconcile positions against Kalshi portfolio API.
5. Enter the main loop (30-second cycle).

---

## Stopping the system

**Graceful shutdown:** Press `Ctrl+C` or send `SIGTERM`.

The shutdown sequence:
1. Cancels all resting Kalshi orders.
2. Disconnects from IB Gateway (positions remain; no auto-flatten).
3. Writes PnL summary CSV to `output/pnl/`.
4. Exits cleanly.

**Emergency stop:** Send `SIGKILL` (kill -9). Orders will NOT be cancelled.
After an emergency stop, manually cancel orders via Kalshi web UI or:
```bash
python -c "
import asyncio
from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from pathlib import Path
import os

async def cancel_all():
    auth = KalshiAuth(
        api_key=os.environ['KALSHI_API_KEY'],
        private_key_pem=Path(os.environ['KALSHI_PRIVATE_KEY_PATH']).read_bytes(),
    )
    async with KalshiClient(auth=auth) as client:
        resp = await client.get_orders(status='resting', limit=100)
        for o in resp.get('orders', []):
            await client.cancel_order(o['order_id'])
            print(f'Cancelled {o[\"order_id\"]}')

asyncio.run(cancel_all())
"
```

---

## Adding a series

1. Edit `deploy/config.yaml` — add a new entry under `series:`:
   ```yaml
   - ticker_prefix: KXCORNMON
     cme_symbol: ZC
     hedge_enabled: true
     max_inventory_usd: 500
     ...
   ```
2. Restart the system. Currently only the first series in the list is active.
   Multi-series support requires extending the main loop (Phase 85+).

---

## Kill switch fired

When the kill switch fires, the system:
1. Cancels ALL resting Kalshi orders.
2. Logs the trigger name and detail.
3. Continues running but with no open orders until the trigger clears.

**What to check:**
1. Check logs for `KILL SWITCH FIRED` — note the trigger:
   - `risk_aggregate_delta_breach` — position too large
   - `risk_per_event_delta_breach` — concentrated in one event
   - `risk_max_loss_breach` — max-loss cap hit
   - `hedge_ib_disconnect` — IB Gateway down + delta above threshold
   - `pnl_drawdown` — unrealized loss too high
2. Check Kalshi positions: `GET /portfolio/positions`
3. Check IB positions: via TWS or IB Gateway
4. If the trigger was IB disconnect: restart IB Gateway, then the system
   will auto-reconnect on next cycle.
5. If the trigger was risk breach: reduce positions manually before
   restarting quoting.

---

## Daily PnL check

PnL files are written to `output/pnl/` on shutdown.

```bash
# View latest PnL summary
cat output/pnl/pnl_*.csv | column -t -s,

# View fills
cat output/pnl/fills_*.csv | column -t -s,
```

Key metrics:
- `spread_capture_cents` — gross revenue from maker fills
- `adverse_selection_cents` — loss from model fair moving against fills
- `kalshi_fees_cents` — maker fees paid
- `ib_fees_cents` — hedge commissions
- `net_pnl_cents` — spread_capture - adverse - fees

Target: net positive each day. If negative for 3+ consecutive days,
review model accuracy and spread settings.

---

## Weekly reconciliation

1. **Kalshi positions:**
   ```bash
   # Compare local position store vs API
   python -c "
   # ... reconciliation script similar to startup
   "
   ```

2. **IB positions:**
   - Check IB account statement vs expected hedge positions.
   - Ensure futures positions match the sum of hedge trades.

3. **PnL vs account balance:**
   - Compare cumulative PnL from CSV to Kalshi balance change.
   - Check for missing fills or reconciliation errors.

4. **Risk parameter review:**
   - Are spreads too wide/tight? Check fill rate.
   - Is the kill switch firing too often? Review thresholds.
   - Is adverse selection growing? Review taker-imbalance settings.

---

## Configuration reference

| Parameter | Location | Default | Notes |
|---|---|---|---|
| `series[].max_inventory_usd` | config.yaml | 1000 | Per-series capital cap |
| `risk.max_total_inventory_usd` | config.yaml | 1000 | Global capital cap |
| `risk.kill_switch_pnl_threshold_pct` | config.yaml | 5 | Kill at 5% drawdown |
| `quoter.min_half_spread_cents` | config.yaml | 2 | 4c total spread |
| `hedge.threshold_contracts` | config.yaml | 3.0 | Hedge when |delta| > 3 |
| `loop.cycle_seconds` | config.yaml | 30 | Main loop period |
| `KALSHI_API_KEY` | env var | (required) | Kalshi API key ID |
| `KALSHI_PRIVATE_KEY_PATH` | env var | (required) | Path to RSA private key |
| `IB_GATEWAY_HOST` | env var | 127.0.0.1 | IB Gateway host |
| `IB_GATEWAY_PORT` | env var | 4001 | IB Gateway port |
