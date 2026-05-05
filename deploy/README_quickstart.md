# lipmm quickstart — deploy against any Kalshi event

The `deploy/lipmm_run.py` entry point wires the lipmm framework against
one Kalshi event and brings up the operator dashboard. From a fresh
shell to a working dashboard takes about 90 seconds.

> **Going beyond the dashboard?** See [`docs/API.md`](../docs/API.md)
> for the full HTTP + WebSocket reference, plugin Protocols, and
> recipes for plugging in your own theos (CSV / HTTP / Python).

## Prerequisites

- The repo cloned and the venv set up (`pip install -e .`).
- Kalshi API keys (the same ones you used for the soy bot).
- Network access to `api.elections.kalshi.com`.

## 90-second setup

```bash
# 1. SSH to wherever you want to run it (Mac Mini via Tailscale)
ssh efloyal@100.95.127.115
cd ~/Documents/GitHub/goated && git pull
source .venv/bin/activate

# 2. Set Kalshi credentials (you've done this before)
export KALSHI_API_KEY="..."
export KALSHI_PRIVATE_KEY_PATH="/path/to/private_key.pem"

# 3. Generate a dashboard secret (one-time per deployment)
export LIPMM_CONTROL_SECRET="$(python -c 'import secrets; print(secrets.token_hex(16))')"
echo "$LIPMM_CONTROL_SECRET"   # ← copy this; you'll paste it on the login page

# 4. Run inside a screen session so it survives logout
screen -S lipmm
python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY
# Ctrl+A, then D to detach
```

Open `http://<host>:5050` in your browser. Paste the secret. You're in.

## What you'll see on first paint

- **Kill button** top-right (always available).
- **State panel** showing version, kill-state, no pauses.
- **Positions / resting orders panels** populating within 5 s.
- **LIP incentives panel** at the bottom showing the active programs
  for the strikes under your event.
- **Theo overrides panel** — empty.
- **Decision feed** — empty until the runner cycle starts emitting.

The bot is **idle** at this point: the `StubTheoProvider` returns
`confidence=0.0` for every strike, and `DefaultLIPQuoting.min_theo_confidence`
is 0.10 by default, so every side is skipped with reason
`theo confidence too low`.

## Starting to quote

Two paths:

### Path A — manual theo per strike (recommended for v1)

For each strike you want to quote:

1. In the **Theo overrides** panel, fill in the form:
   - Ticker: e.g. `KXISMPMI-26MAY-T55`
   - Yes (cents): your fair-value estimate, e.g. `42`
   - Confidence: `1.0`
   - Reason: required, ≥4 chars
2. Submit. Two confirms appear:
   - First: a preview dialog showing all values
   - Second: prompts you to type the ticker name exactly
3. Within one cycle (≤ `--cycle-seconds`, default 3 s) the bot starts
   quoting that strike penny-inside the best.

Clear an override any time with its **Clear** button. Overrides are
**runtime-only** — bot restart wipes them, and you re-set after every
restart.

### Path B — write your own TheoProvider

When your algorithmic theo is ready:

1. Implement `TheoProvider` in `lipmm/theo/providers/<your_market>.py`.
2. In `deploy/lipmm_run.py`, swap `theo_registry.register(StubTheoProvider(...))`
   for `theo_registry.register(YourProvider(...))`.
3. Restart. Dashboard overrides still work as a manual override on top
   of your provider.

## Common operations

| Goal | Action |
|---|---|
| Stop everything immediately | Click **Kill** (top right) |
| Resume after kill | Click **Arm** → **Resume** |
| Pause one strike temporarily | State panel → "Paused tickers" form |
| Tune a strategy knob at runtime | Knob overrides panel (e.g. `min_theo_confidence`) |
| Cancel one specific resting order | Cancel button on its row |
| Place a one-off order | Manual order panel (with confirm) |
| Lock a side after a click-trade | `lock_after: yes` on the manual-order form |
| Check what's earning LIP | LIP incentives panel — green rows are tickers you have skin in |

## CLI reference

```
python -m deploy.lipmm_run \
    --event-ticker EVENT_TICKER     # required, e.g. KXISMPMI-26MAY
    [--cap-dollars 100.0]           # per-side notional cap
    [--strategy default|sticky]     # default
    [--cycle-seconds 3.0]
    [--host 0.0.0.0]                # or set LIPMM_DASHBOARD_HOST
    [--port 5050]                   # or set LIPMM_DASHBOARD_PORT
    [--decision-log-dir PATH]       # default logs/<event>_decisions/
    [--retention-bytes N]           # default 2 GiB
    [--log-level INFO|DEBUG|...]
```

## Troubleshooting

**"missing required env vars"** — set the three env vars listed in
section 2/3 above. The script tells you exactly what's missing.

**"Could not fetch event …"** — verify the event ticker spelling
(Kalshi uses formats like `KXISMPMI-26MAY`, `KXSOYBEANW-26APR27`). The
script aborts before starting any side effects if the lookup fails.

**Login page shows but dashboard is blank** — the JWT is in
`localStorage`. Open devtools → Application → Local Storage and
confirm `lipmm_jwt` is set. If not, check the browser console for
`/control/auth` errors.

**"connecting…" pill stuck on the dashboard** — the WebSocket failed
to upgrade. Check your reverse proxy (if any) supports WS, and that
the JWT in localStorage matches the `LIPMM_CONTROL_SECRET` the bot
was started with.

**Bot not quoting any strikes** — expected behavior with stub theo.
Set theo overrides via the dashboard.

**Bot quoting but you wanted it idle** — click **Kill** top-right;
or stop the script with Ctrl+C in screen.
