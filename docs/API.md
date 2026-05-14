# lipmm API wiki

External integration reference for the lipmm control plane. Hand-curated
companion to FastAPI's auto-generated `/docs` (Swagger UI) and
`/openapi.json` — this wiki explains the *why*, surfaces conceptual
notes, and shows worked examples.

> If you only want the JSON schema for one endpoint, hit `GET /openapi.json`
> on the running bot or open `http://<host>:<port>/docs` in a browser.
> This wiki points at those for full field-level details.

---

## Table of contents

- [At a glance](#at-a-glance)
- [Quick start](#quick-start)
- [Authentication](#authentication)
- [Conventions (cross-cutting)](#conventions-cross-cutting)
- [HTTP API reference](#http-api-reference)
  - [Read endpoints](#read-endpoints)
  - [Mutating endpoints](#mutating-endpoints)
- [WebSocket API](#websocket-api)
- [Plugin protocols](#plugin-protocols)
- [TheoProvider integration recipes](#theoprovider-integration-recipes)
- [Errors](#errors)
- [End-to-end Python examples](#end-to-end-python-examples)
- [Versioning & stability](#versioning--stability)

---

## At a glance

**lipmm** is a market-making framework for Kalshi-style binary markets.
It exposes a control plane: an HTTP + WebSocket surface that lets
operators (and external scripts) read state, push theos, run / pause /
kill quoting, and manage events at runtime — all without restarting the
bot.

```
┌────────────────────────────────────────────────────────────────────┐
│                       External clients                             │
│  curl │ Python httpx │ dashboard browser │ model server cron       │
└──────┬─────────────────────────────────────────────────────────────┘
       │ HTTP+WS  (JWT bearer for mutations)
       ▼
┌────────────────────────────────────────────────────────────────────┐
│                  ControlServer (FastAPI)                           │
│  /control/*  endpoints  ·  /control/stream  WS  ·  /dashboard      │
└──────┬─────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────────────┐
│                  ControlState (in-memory, mutable)                 │
│  pauses · kill_state · knob_overrides · side_locks · theo_overrides│
│  active_events                                                     │
└──────┬─────────────────────────────────────────────────────────────┘
       │ consulted each cycle
       ▼
┌────────────────────────────────────────────────────────────────────┐
│             LIPRunner (per-cycle orchestrator)                     │
│  TickerSource → TheoProvider → ExchangeClient → QuotingStrategy    │
│              → RiskRegistry → OrderManager.apply                   │
└────────────────────────────────────────────────────────────────────┘
```

| You want | Look here |
|---|---|
| Field-level JSON schema for one endpoint | `/openapi.json#/paths/...` or `/docs` |
| Conceptual overview, examples, recipes | This wiki |
| Source of truth (Pydantic models) | `lipmm/control/commands.py` |
| Source of truth (plugin Protocols) | `lipmm/{theo,quoting,execution,risk,runner,incentives}/base.py` |

---

## Quick start

Spin up a bot, mint a JWT, push a theo:

```python
import asyncio, httpx, secrets, os

BASE = "http://localhost:5050"
SECRET = os.environ["LIPMM_CONTROL_SECRET"]   # 32-hex; same one you paste at /login

async def main():
    async with httpx.AsyncClient(base_url=BASE) as c:
        # 1. Mint JWT (24h TTL)
        r = await c.post("/control/auth", json={
            "secret": SECRET, "actor": "my-script",
        })
        r.raise_for_status()
        token = r.json()["token"]
        H = {"Authorization": f"Bearer {token}"}

        # 2. Read current state
        s = (await c.get("/control/state", headers=H)).json()
        print("version:", s["version"], "kill:", s["kill_state"])

        # 3. Push a theo for one strike
        r = await c.post("/control/set_theo_override", json={
            "ticker": "KXISMPMI-26MAY-50",
            "yes_cents": 82,
            "confidence": 0.85,
            "reason": "consensus prior + my regional-Fed model",
            "request_id": secrets.token_hex(8),
        }, headers=H)
        print(r.json())

asyncio.run(main())
```

---

## Authentication

**Model**: shared deployment secret (`LIPMM_CONTROL_SECRET`, 32 hex chars
recommended) → exchange for a JWT via `POST /control/auth` → put JWT in
the `Authorization: Bearer` header on every mutation.

- **Token TTL**: 24 hours (issued time + 86400s).
- **No CSRF protection.** Single-trusted-user model; safe over
  Tailscale / VPN / localhost only. Don't expose to the public internet.
- **HTML pages are unauthenticated shells.** `GET /login`, `/dashboard`,
  `/static/*` return without a token; the dashboard JS hydrates the JWT
  from localStorage and uses it for every API call.
- **Read endpoints** (e.g. `GET /control/state`) require the bearer
  header for state inspection. `GET /control/health` and the OpenAPI
  endpoints (`/docs`, `/openapi.json`) do NOT require auth.
- **WebSocket auth**: `?token=<jwt>` query param at connection time.

### `POST /control/auth`

```json
// request
{ "secret": "0123456789abcdef0123456789abcdef", "actor": "my-script" }

// response
{ "token": "eyJ…", "expires_in_seconds": 86400, "actor": "my-script" }
```

Wrong secret → `401`. Missing fields → `422` (Pydantic validation).

---

## Conventions (cross-cutting)

Every mutating endpoint follows the same envelope:

| Field | Type | Purpose |
|---|---|---|
| `request_id` | str (≥8 chars) | **Required.** Idempotency key, recorded in the audit log. Generate a fresh UUID-ish per call. |
| `if_version` | int (optional) | Optimistic concurrency. If set, the server's current `state.version` must match exactly or the call returns `409`. Pass `null` for last-write-wins. |
| (response) `new_version` | int | The state version *after* this command applied. Cache it for your next `if_version`. |
| (response) `actor` | str | The actor name from the JWT (set in `/control/auth`). |

Common status codes:

| Code | Meaning |
|---|---|
| 200 | Command accepted; `new_version` reflects the post-mutation state. |
| 400 | Malformed input (bad ticker shape, out-of-range value, missing required field). |
| 401 | Missing or invalid JWT. |
| 403 | (reserved — not currently used) |
| 404 | Target not found (e.g. `cancel_order` order_id not in OrderManager). |
| 409 | Optimistic concurrency mismatch. Re-fetch state and retry. |
| 422 | Pydantic validation error (wrong types). |
| 500 | Exchange / internal error. Body has the error message. |
| 503 | Required collaborator not wired (e.g. manual-order endpoint without an OrderManager). |

---

## HTTP API reference

All paths are under `/control`. Schemas reference Pydantic models in
[`lipmm/control/commands.py`](../lipmm/control/commands.py).

### Read endpoints

#### `GET /control/health`

Liveness check; no auth required.

```json
{ "ok": true, "state_version": 17 }
```

#### `GET /control/state` *(requires Bearer)*

Full snapshot of `ControlState`. Mirrors the dashboard's drawer.

```jsonc
{
  "version": 17,
  "kill_state": "off",                // "off" | "killed" | "armed"
  "global_paused": false,
  "paused_tickers": ["KXISMPMI-26MAY-50"],
  "paused_sides": [["KXISMPMI-26MAY-51", "ask"]],
  "knob_overrides": {"min_theo_confidence": 0.5},
  "event_knob_overrides": {
    "KXISMPMI-26MAY": {"theo_tolerance_c": 1.0}
  },
  "strike_knob_overrides": {
    "KXISMPMI-26MAY-50": {"dollars_per_side": 3.0}
  },
  "strike_side_knob_overrides": {     // shipped 2026-05; layered ON TOP
    "KXISMPMI-26MAY-50": {            // of strike_knob_overrides
      "bid": {"theo_tolerance_c": -3.0},
      "ask": {"theo_tolerance_c":  2.0}
    }
  },
  "side_locks": [
    {"ticker": "...", "side": "bid", "mode": "lock", "reason": "...",
     "locked_at": 1.7e9, "auto_unlock_at": null}
  ],
  "theo_overrides": [
    {"ticker": "...", "yes_probability": 0.82, "yes_cents": 82,
     "confidence": 0.85, "reason": "...", "set_at": 1.7e9,
     "actor": "alice", "mode": "fixed"}
  ],
  "active_events": ["KXISMPMI-26MAY"]
}
```

Schema: `StateResponse`. See `commands.py:433`.

#### `GET /control/runtime` *(requires Bearer; 503 if no exchange wired)*

Live positions + resting orders + balance, fetched from Kalshi at
read-time. Tolerates partial failure (one of three async calls
raising → that field empty + `errors` enumerates).

```jsonc
{
  "positions": [
    {"ticker": "...", "quantity": 5, "avg_cost_cents": 50,
     "realized_pnl_dollars": 1.20, "fees_paid_dollars": 0.08}
  ],
  "resting_orders": [
    {"ticker": "...", "side": "bid", "order_id": "ord-…",
     "price_cents": 79, "size": 5}
  ],
  "balance": {"cash_dollars": 84.20, "portfolio_value_dollars": 100.00},
  "total_realized_pnl_dollars": 1.20,
  "total_fees_paid_dollars": 0.08,
  "errors": [],
  "ts": 1.7e9
}
```

Schema: `RuntimeSnapshotResponse`. Pulled every 5s by the runtime
broadcast loop (configurable via `runtime_refresh_s`).

> **Position field derivation caveats** (relevant for downstream
> calculators):
> - `avg_cost_cents` is derived from Kalshi's `market_exposure / |position|`,
>   NOT the (non-existent) `average_cost_cents` field. Kalshi's v2 API
>   doesn't return an explicit avg-cost field.
> - `realized_pnl_dollars` reads Kalshi's `realized_pnl` (cents) and
>   converts. Same for `fees_paid_dollars` ← `fees_paid` (cents).
> - For short YES positions (`quantity < 0`), `avg_cost_cents` is the
>   YES price the short was opened at — to interpret as a "long NO at
>   X¢ price", compute `100 - avg_cost_cents`.

#### `GET /control/orderbooks` *(requires Bearer)*

Last per-strike L2 depth snapshot the runner pushed. Includes
`best_bid_c`/`best_ask_c` excluding our own resting orders, plus up to
50 levels per side (the **scorer needs full depth** to walk down to
target size; the dashboard ladder slices to top 5 at render time).

Schema: `OrderbookSnapshotResponse`.

#### `GET /control/incentives` *(requires Bearer)*

Last cached `/incentive_programs` snapshot from Kalshi. Operator-friendly
fields (period reward in dollars, time remaining in seconds).

Schema: `IncentiveSnapshotResponse`.

#### `GET /control/locks` *(requires Bearer)*

Convenience subset of `GET /control/state` — just the side locks list.
Schema: `LocksResponse`.

#### `GET /control/pnl_grid` *(requires Bearer)*

**Returns HTML fragment** (not JSON). Per-position PnL grid rendered
server-side from the most-recent runtime + orderbook snapshots in
the broadcaster cache. Each row: `ticker, qty (signed), avg_cost,
mtm_mark, mtm_value, unrealized, theo, expected_settle, edge_per_c,
realized, fees`. Totals row at the bottom.

Used by the dashboard's "PnL" header tab via `hx-get` + `hx-target`.
Refresh cadence is operator-controlled (template polls every 10s).

#### `GET /control/earnings_history` *(requires Bearer)*

**Returns HTML fragment.** $/hr histogram of LIP earnings rate over
the bot's lifetime, computed from a persistent JSONL log
(`logs/<event>_decisions/earnings_history.jsonl`). Sampled once per
minute by the runner. Bins: $0-0.05, $0.05-0.10, $0.10-0.25, $0.25-
0.50, $0.50-1.00, $1-2, $2-4, $4-8, $8-16, $16+. Time-weighted mean
+ peak rate displayed.

Used by the dashboard's "Earnings $/hr" header tab.

#### `GET /control/markout` *(requires Bearer)*

**Returns HTML fragment.** Per-fill +1m/+5m mid-drift table from the
in-memory `MarkoutTracker`. Fills detected via per-cycle position
delta; mids sampled async. Toxic flag fires when 5m markout < −2¢
across ≥ 2 fills.

Used by the dashboard's "Markout" header tab.

---

### Mutating endpoints

All mutations require `Authorization: Bearer <jwt>` and follow the
[conventions](#conventions-cross-cutting) (`request_id`, `if_version`).

#### `POST /control/pause` / `POST /control/resume`

Halt or resume quoting. Three scopes:

| `scope` | `ticker` required? | `side` required? | Effect |
|---|---|---|---|
| `"global"` | no | no | Whole bot |
| `"ticker"` | yes | no | One ticker (both sides) |
| `"side"` | yes | yes (`"bid"`/`"ask"`) | One side of one ticker |

```bash
curl -XPOST http://host:5050/control/pause -H "Authorization: Bearer $T" \
     -d '{"scope":"global","request_id":"req-pause-1"}'
```

Schemas: `PauseRequest`, `ResumeRequest`. Returns `CommandResponse`.

> **pause vs side_lock:** `pause` is "halt + cancel existing"; `lock_side`
> is "halt new orders, leave existing alone". See [Locks](#post-controllock_side---post-controlunlock_side).

#### `POST /control/kill`

Engage the kill switch. Cancels every resting order, sets
`kill_state="killed"`. Bot can't quote until `arm` → `resume`.

```json
{"request_id": "req-kill-1", "reason": "circuit breaker"}
```

#### `POST /control/arm`

After kill, transition `killed → armed`. Required step before `resume`
to prevent accidental restart.

#### `POST /control/set_knob` / `POST /control/clear_knob`

Override a strategy or risk knob at runtime. Names are deployment-
configurable; for `DefaultLIPQuoting` see the dashboard's Knobs tab
(`tab_knobs.html`) for the canonical list.

```json
{
  "name": "max_distance_from_best",
  "value": 1.0,
  "request_id": "req-knob-1"
}
```

Active knobs (DefaultLIPQuoting v0.3):

| Name | Default | Range | What it does |
|---|---|---|---|
| `min_theo_confidence` | 0.10 | [0, 1] | Below this confidence, both sides skip |
| `match_best_min_confidence` | 0.70 | [0, 1] | At ≥, strategy MATCHES best (active-match mode) |
| `penny_inside_min_confidence` | 0.95 | [0, 1] | At ≥, strategy goes 1¢ INSIDE best (active-penny) |
| `penny_inside_distance` | 1 | [1, 10] | How many ticks inside best in active-penny mode |
| `theo_tolerance_c` | 2.0 | **[-50, 50]** | Anti-spoofing tolerance. **Negative values REPEL from theo on both sides** (e.g. `-3` → bid ≤ theo-4, ask ≥ theo+4). |
| `max_distance_from_best` | 1.0 | [0, 50] | Active-follow gap (cents behind best) |
| `desert_threshold_c` | 10.0 | [0, 50] | Gap that triggers desert mode |
| `dollars_per_side` | 1.00 | [0, 100] | Notional per cycle per side |
| `max_notional_per_side_dollars` | (from `--cap-dollars`) | [0, 1000] | Per-side hard ceiling enforced by `MaxNotionalPerSideGate`. Also auto-lifted when `dollars_per_side` is bumped per-strike. |
| `max_orders_per_cycle` | 100 | [1, 1000] | Cycle-wide cap on placements |
| `max_position_per_side` | 200 | [0, 100k] | Per-strike absolute position cap |
| `mid_delta_threshold_c` | 8 | [0, 100] | Vetoes both sides if mid jumped ≥ this since last cycle |
| `max_distance_from_extremes_c` | 0 | **[0, 99]** | Tail-only mode. At N: bid capped at N¢, ask floored at (100-N)¢. **Range bumped from 50 → 99** for one-sided deep-ITM/OTM LIP farming. |
| `truev_model_rmse_pts` | 0 | [0, 50] | **⚠️ TRUEV-ONLY, mostly deprecated.** Inflates lognormal σ by RMSE in quadrature. Causes deep-OTM probabilities to spike toward 50% (boundary distortion); for asymmetric distrust use `theo_tolerance_c` negative instead. |
| `sticky_min_distance_from_theo` | 3.0 | [0, 50] | StickyDefenseQuoting only |
| `sticky_desert_jump_cents` | 5.0 | [0, 50] | StickyDefenseQuoting only |

#### `POST /control/set_event_knob` / `POST /control/clear_event_knob`

Per-event knob override. Layered between global knobs and per-strike
knobs. Useful when one event has very different liquidity/volatility
than others (e.g. tail-only mode for a batch-released event).

```json
{
  "event_ticker": "KXTRUEV-26MAY11",
  "name": "max_distance_from_extremes_c",
  "value": 5.0,
  "request_id": "req-event-knob-1"
}
```

#### `POST /control/set_strike_knob` / `POST /control/clear_strike_knob`

Per-strike knob override. Highest precedence in the both-side path.
**Per-side overrides** (introduced 2026-05) layer ON TOP via the
`side` field:

```json
{
  "ticker": "KXTRUEV-26MAY11-T1290.90",
  "name": "theo_tolerance_c",
  "value": -3.0,
  "side": "bid",          // "both" (default) | "bid" | "ask"
  "request_id": "req-strike-knob-1"
}
```

Precedence (highest first):
```
strike-side ("bid"|"ask")  >  strike (both)  >  event  >  global  >  config default
```

**Worked example.** Operator wants `theo_tolerance_c = 2` everywhere
(default), `theo_tolerance_c = 1` on a particular event, and
`theo_tolerance_c = -3` on JUST the bid side of one strike in that
event. Submit:

```
POST /control/set_event_knob   {event_ticker, theo_tolerance_c=1}
POST /control/set_strike_knob  {ticker, theo_tolerance_c=-3, side="bid"}
```

The bid side of that strike sees `-3`; ask side sees `1` (event-level
fallback); other strikes in the event see `1`; other events see `2`.

#### `POST /control/lock_side` / `POST /control/unlock_side`

Per-(ticker, side) lock. Locked side is force-skipped each cycle;
existing resting orders are NOT cancelled (use `pause` for that, or
`cancel_order` per-order).

```json
{
  "ticker": "KXISMPMI-26MAY-50", "side": "bid",
  "reason": "model recalibrating",
  "auto_unlock_seconds": 600,
  "request_id": "req-lock-1"
}
```

> **Cancel-order auto-locks.** `POST /control/cancel_order` engages a
> side-lock by default (`auto_lock=true`) so the runner doesn't
> immediately re-place. Operator must `unlock_side` to resume. See
> [`POST /control/cancel_order`](#post-controlcancel_order) below.

#### `POST /control/add_event` / `POST /control/remove_event`

Manage the bot's active-events set at runtime. The runner's
`MultiEventTickerSource` reads this set each cycle.

`add_event` validates the ticker against Kalshi (must exist with ≥1
tradable market) before accepting.

```json
// POST /control/add_event
{"event_ticker": "KXISMPMI-26MAY", "request_id": "req-add-1"}

// 200 response
{"new_version": 5, "request_id": "...", "actor": "alice",
 "event_ticker": "KXISMPMI-26MAY", "market_count": 8}
```

`remove_event` accepts `cancel_resting=true` to bulk-cancel any resting
orders on the event's strikes atomically with removal.

```json
{
  "event_ticker": "KXISMPMI-26MAY",
  "cancel_resting": true,
  "request_id": "req-rm-1"
}
```

#### `POST /control/set_theo_override` / `POST /control/clear_theo_override`

Plug a manual theo for one strike. Two modes:

- `mode="fixed"` *(default)*: `yes_cents` is taken literally; theo is static.
- `mode="track_mid"`: theo recomputes from orderbook mid each cycle;
  `yes_cents` is a placeholder (still required for shape, ignored at
  quote time).

```json
{
  "ticker": "KXISMPMI-26MAY-50",
  "yes_cents": 82,
  "confidence": 0.85,
  "reason": "model output, prior-weighted",
  "request_id": "req-theo-1",
  "mode": "fixed"
}
```

Confidence drives strategy mode (DefaultLIPQuoting):

| `confidence` | mode | bid | ask |
|---|---|---|---|
| ≥ 0.95 | active-penny | best+1 | best−1 |
| 0.70 – 0.94 | active-match | best | best |
| 0.10 – 0.69 | active-follow | best − max_distance | best + max_distance |
| < 0.10 | skip | — | — |

Override clears on bot restart (runtime-only state). For permanent
sources, write a [TheoProvider](#plugin-protocols).

#### `POST /control/manual_order` *(503 if no OrderManager+exchange)*

Place one order out-of-band of the strategy.

```jsonc
{
  "ticker": "KXISMPMI-26MAY-50",
  "side": "bid",                       // "bid" | "ask" — Yes-side wire convention
  "count": 10,
  "limit_price_cents": 49,
  "lock_after": true,                  // recommended: prevent runner from cancelling
  "lock_auto_unlock_seconds": 300,
  "reason": "operator backup",
  "request_id": "req-manual-1"
}
```

Routed through the same `RiskRegistry` as strategy decisions. Response
distinguishes `succeeded` / `risk_vetoed` / `exchange_rejected`:

```jsonc
{
  "succeeded": true,
  "risk_vetoed": false,
  "action": "place",
  "reason": "ok",
  "order_id": "ord-…", "price_cents": 49, "size": 10,
  "latency_ms": 142,
  "risk_audit": [...],
  "lock_applied": true, "lock_auto_unlock_at": 1.7e9,
  "new_version": 18, "request_id": "...", "actor": "alice"
}
```

> **Yes/No semantics.** The framework places only **buy-Yes / sell-Yes**
> orders. To buy No at price X, place a **sell-Yes at (100−X)**. The
> dashboard's manual-order form translates 4-option semantic sides
> (Buy Yes / Sell Yes / Buy No / Sell No) into the wire shape; raw API
> callers do the translation themselves.

Schemas: `ManualOrderRequest`, `ManualOrderResponse`.

#### `POST /control/cancel_order`

Cancel one resting order by exchange `order_id`. Default behavior
auto-locks the (ticker, side) so the runner won't immediately re-place.

```json
{
  "order_id": "ord-…",
  "reason": "operator pull",
  "auto_lock": true,
  "request_id": "req-cancel-1"
}
```

| Status | When |
|---|---|
| 200 | Order cancelled (or already gone — exchange returned False; we still drop from our state) |
| 404 | `order_id` not in OrderManager |
| 500 | Exchange raised |
| 503 | No exchange + order_manager wired |

Pass `auto_lock: false` if you specifically want the runner to be free
to re-place on the next cycle.

#### `POST /control/swap_strategy` *(501 — deferred)*

Hot-swap the active strategy. Currently returns `501 Not Implemented`;
the payload validates but no swap occurs. Will be wired in a later
phase if/when needed.

---

## WebSocket API

Two endpoints, same broadcaster fan-out:

| URL | Format | Use |
|---|---|---|
| `WS /control/stream` | JSON | External clients (scripts, dashboards) |
| `WS /control/stream/html` | HTML fragments (htmx OOB) | The bundled dashboard only |

**Connect**: `wss://host/control/stream?token=<jwt>`. Wrong/missing
token → 1008 close.

**Frame shape**: each message is one JSON object with `event_type` and
event-specific fields. The first frame after connect is always
`event_type="initial"` carrying a full `state` snapshot so a fresh
client doesn't need a separate REST round-trip.

### Event types

| `event_type` | Source | Payload |
|---|---|---|
| `initial` | broadcaster | `{state, presence, total_tabs}` |
| `state_change` | every mutation endpoint | `{state, request_id, command_type, actor}` |
| `runtime_snapshot` | periodic (5s default) | `RuntimeSnapshotResponse` shape |
| `orderbook_snapshot` | every runner cycle | `{strikes, last_cycle_ts, ts}` |
| `incentives_snapshot` | hourly | `IncentiveSnapshotResponse` shape |
| `decision` | every strategy decision | the decision-log record |
| **`fill`** | per-cycle position-delta detection | `{ticker, delta, prev_qty, cur_qty, price_c, ts}` |
| `tab_connected` | new connection | `{tab_id, total_tabs, presence}` |
| `tab_disconnected` | close | `{tab_id, total_tabs, presence}` |
| `heartbeat` | optional periodic | (silent in HTML adapter) |

#### `orderbook_snapshot` — per-strike `theo` payload

Each strike entry in the `strikes` array carries a `theo` dict
(shipped 2026-05) summarizing the active theo for the strike:

```json
{
  "ticker": "KXTRUEV-26MAY11-T1290.90",
  "best_bid_c": 88,
  "best_ask_c": 96,
  "yes_levels": [{"price_cents": 88, "price_t1c": 880, "size": 100}, ...],
  "no_levels":  [...],
  "theo": {
    "yes_cents": 87.5,
    "yes_cents_raw": 99.0,        // present only when RMSE inflation active
    "model_rmse_pts": 8.0,        // present only when RMSE inflation active
    "confidence": 0.95,
    "source": "TruEV",
    "source_kind": "provider"     // or "override" (manual)
  }
}
```

`yes_cents_raw` and `model_rmse_pts` are only attached when the
provider exposes them (TruEV does; generic providers don't). When
present, the dashboard renders both raw and inflated values
side-by-side in the strike row's Theo column.

#### `fill` — per-cycle position-delta detection

```json
{
  "event_type": "fill",
  "ticker": "KXTRUEV-26MAY11-T1290.90",
  "delta": 5,                    // signed; +5 = bought 5 YES
  "prev_qty": 0,
  "cur_qty": 5,
  "price_c": 47.5,               // mid proxy (NOT exact fill price)
  "ts": 1715432123.4
}
```

Emitted by the runner once per cycle when any strike's position
changed. `price_c` is the cycle's mid; exact per-fill prices require
Kalshi's `/portfolio/fills` endpoint which we don't currently
plumb. Dashboard's HTML adapter renders this as an OOB swap into
`<div id="fill-events">`, where `dashboard.js` observes the addition
and triggers a browser Notification + audio beep.

Subscription model: every connected tab receives every event. No
per-event filtering today.

### Minimal Python client

```python
import asyncio, json, os, websockets

BASE = "ws://localhost:5050"
TOKEN = "<jwt>"

async def main():
    async with websockets.connect(f"{BASE}/control/stream?token={TOKEN}") as ws:
        async for msg in ws:
            evt = json.loads(msg)
            if evt["event_type"] == "decision":
                print("decision:", evt["record"]["ticker"], evt["record"].get("decision_action"))

asyncio.run(main())
```

---

## Plugin protocols

The framework is plugin-driven. Implement one of these Protocols and
register it. All Protocols live under `lipmm/<area>/base.py`.

### TheoProvider — [`lipmm/theo/base.py:68`](../lipmm/theo/base.py)

Produces `TheoResult` per ticker. Routed by `series_prefix`; pass `"*"`
for wildcard.

```python
class TheoProvider(Protocol):
    series_prefix: str                            # e.g. "KXISMPMI" or "*"
    async def warmup(self) -> None: ...           # one-time init at bot start
    async def shutdown(self) -> None: ...         # one-time cleanup
    async def theo(self, ticker: str) -> TheoResult: ...  # called per cycle
```

**Contract**: `theo()` is on the hot path. MUST be fast (cached
lookup, small computation). MUST NOT raise — return
`TheoResult(confidence=0.0, source="...:reason")` instead.

See [TheoProvider integration recipes](#theoprovider-integration-recipes)
for the four supported integration paths.

### ExchangeClient — [`lipmm/execution/base.py:90`](../lipmm/execution/base.py)

Venue abstraction. The bundled `KalshiExchangeAdapter` implements this;
to support another venue (Polymarket, Robinhood) write a new adapter.

```python
class ExchangeClient(Protocol):
    async def place_order(self, request: PlaceOrderRequest) -> Order | None: ...
    async def amend_order(self, order_id: str, *,
                          new_limit_price_cents: int | None = None,
                          new_count: int | None = None) -> Order | None: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def cancel_orders(self, order_ids: list[str]) -> dict[str, bool]: ...
    async def get_orderbook(self, ticker: str) -> OrderbookLevels: ...
    async def list_resting_orders(self) -> list[Order]: ...
    async def list_positions(self) -> list[Position]: ...
    async def get_balance(self) -> Balance: ...
```

**Contract**: translate exchange-specific errors into `None`/empty for
"not found", a known exception for "exchange error / retry later", or
`ValueError` for "request was malformed". Callers expect `cancel_order`
on a stale id to return `False`, not raise.

### QuotingStrategy — [`lipmm/quoting/base.py:105`](../lipmm/quoting/base.py)

Pure decision function over `(ticker, theo, orderbook, our_state)` →
`QuotingDecision`. No I/O.

```python
class QuotingStrategy(Protocol):
    name: str
    async def warmup(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def quote(self, *, ticker, theo, orderbook, our_state,
                    now_ts, time_to_settle_s,
                    control_overrides=None) -> QuotingDecision: ...
```

**Contract**: pure function (state survives across calls; no exchange
calls inside). `control_overrides` is the dict from
`ControlState.knob_overrides`; strategies that don't read overrides
ignore the kwarg. Built-ins: `DefaultLIPQuoting`, `StickyDefenseQuoting`.

### RiskGate — [`lipmm/risk/base.py:53`](../lipmm/risk/base.py)

Composable pre-trade veto.

```python
class RiskGate(Protocol):
    name: str
    async def check(self, context: RiskContext) -> RiskVerdict: ...
```

Compose via `RiskRegistry`; verdicts are additive (any veto wins). The
audit trail collects every gate's verdict. Built-ins:
`MaxNotionalPerSideGate`, `MaxOrdersPerCycleGate`,
`EndgameGuardrailGate`.

### TickerSource — [`lipmm/runner/runner.py:60`](../lipmm/runner/runner.py)

Resolves the set of tickers to iterate this cycle.

```python
class TickerSource(Protocol):
    async def list_active_tickers(self, exchange: ExchangeClient) -> list[str]: ...
```

The deploy ships `_MultiEventTickerSource` reading from
`ControlState.active_events` so adds/removes via the dashboard take
effect on the next cycle. Roll your own if you want a different
selection policy (config-driven, all-open-events globally, etc.).

### IncentiveProvider — [`lipmm/incentives/base.py:147`](../lipmm/incentives/base.py)

Surfaces LIP program metadata for the dashboard.

```python
class IncentiveProvider(Protocol):
    async def list_active(self) -> list[IncentiveProgram]: ...
```

The bundled `KalshiIncentiveProvider` hits the unauthenticated
`/incentive_programs` endpoint; cached hourly via `IncentiveCache`.

---

## TheoProvider integration recipes

The most-used extension point. Four paths in priority of
simplicity:

### A. CSV file (most accessible)

Operator points the bot at a CSV file; any external tool that can
write a file feeds theos. CLI flag is repeatable.

```bash
python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY \
    --theo-csv ./pmi_theos.csv
```

Schema (`ticker,yes_cents,confidence,reason`):

```csv
ticker,yes_cents,confidence,reason
KXISMPMI-26MAY-50,82,0.85,pmi-bayes-v1
KXISMPMI-26MAY-51,75,0.80,pmi-bayes-v1
```

Spec form: `--theo-csv PATH[:PREFIX[:REFRESH_S]]`. `PREFIX` defaults
to `*` (wildcard). `REFRESH_S` defaults to 5.

### B. JSON file

Same idea, JSON shape (dict or list):

```bash
python -m deploy.lipmm_run --event-ticker A,B \
    --theo-json ./theos.json
```

```jsonc
{
  "KXISMPMI-26MAY-50": {"yes_cents": 82, "confidence": 0.85, "reason": "..."},
  "KXISMPMI-26MAY-51": {"yes_cents": 75, "confidence": 0.80}
}
```

### C. HTTP poll

For when the model lives behind a service. Same JSON payload as
the file variant; optional bearer header.

```bash
python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY \
    --theo-http http://localhost:8001/theos
```

In Python:

```python
from lipmm.theo.providers import HttpPollTheoProvider
prov = HttpPollTheoProvider(
    "http://localhost:8001/theos",
    series_prefix="*",
    refresh_s=5.0,
    bearer="my-secret-token",       # optional
    staleness_threshold_s=15.0,     # default 3× refresh; None to disable
)
theo_registry.register(prov)
```

### D. function_provider decorator

For in-process Python with no warmup state:

```python
from lipmm.theo import TheoResult
from lipmm.theo.providers import function_provider

@function_provider(series_prefix="KXISMPMI", source="pmi-bayes-v1")
async def pmi_theo(ticker: str) -> TheoResult:
    prob = await my_model.predict(ticker)
    return TheoResult(yes_probability=prob, confidence=0.85,
                      computed_at=time.time(), source="pmi-bayes-v1")

theo_registry.register(pmi_theo)
```

### E. Custom class (when warmup/state is needed)

For everything else — stateful providers, background refresh tasks,
external SDK integration. Implement the `TheoProvider` protocol
directly. See `lipmm/theo/providers/gbm_commodity.py` for the soy
reference, or `lipmm/theo/providers/truev.py` (documented below) for
a more complex case with anchored multi-component basket math.

### F. TruEVTheoProvider — KXTRUEV-* daily binaries

A first-class provider that ships with lipmm. Models a Truflation
EV Commodity Index daily binary as a multi-component lognormal:

**Architecture:**

- **Forward source**: `TruEvForwardSource` in
  `feeds/truflation/forward.py` polls 6 commodity prices every 60s
  (5 yfinance + 1 TradingEconomics scrape).
- **Basket math**: `_truev_index.py` reconstructs the index as
  `V_today = V_anchor × Σ wᵢ × (priceᵢ_today / priceᵢ_anchor)`.
- **Lognormal binary**: `P(YES > K) = Φ(d2)` where
  `d2 = (ln(S/K) - 0.5σ²τ) / (σ√τ)`.
- **Confidence**: `forward_freshness × tau_factor`, capped at
  `max_confidence` (default 0.7; CLI flag `--truev-max-confidence`).

**Component sources (live):**

| Metal | Symbol | Source | Notes |
|---|---|---|---|
| Cu | `HG=F` | yfinance Comex futures | Same exchange Truflation uses |
| Pa | `PA=F` | yfinance NYMEX futures | Same exchange |
| Pt | `PL=F` | yfinance NYMEX futures | Same exchange |
| Co | `COBALT_TE` | TradingEconomics scrape (LME spot) | Same exchange |
| Ni | `NICK.L` | yfinance LSE ETC × GBPUSD/100 | **FX-stripped to USD**; basis vs MCX (Truflation's source) |
| Li | `LITHIUM_TE` | TradingEconomics scrape (China lithium hydroxide spot) | Basis vs Shanghai SE futures |

**Q1 2026 fitted weights** (NNLS regression on 118 days of
operator-supplied basket+actuals; in-sample R²=0.985, walk-forward
RMSE 5.1 pts):

| Metal | Weight |
|---|---|
| Cu  (HG=F) | 57.23% |
| Ni  (NICK.L) | 21.84% |
| Co  (COBALT_TE) |  7.72% |
| Pa  (PA=F) |  7.50% |
| Li  (LITHIUM_TE) |  4.93% |
| Pt  (PL=F) |  0.77% |

Quarterly rebalance happens Jan/Apr/Jul/Oct 1; operator re-fits
weights via `deploy/truev_fit_weights.py` after each rebalance.

**Anchor management.** Anchor MUST be a real `(date, V, prices)`
triple from a recent EOD. Refreshed each morning via
`deploy/truev_reanchor.py` which:
1. Pulls yesterday's yfinance closes for Cu/Pa/Pt/NICK.L/GBPUSD
2. Scrapes current TE spots for cobalt + lithium (proxy for EOD)
3. Prompts operator for yesterday's Truflation print
4. Prints a ready-to-paste anchor block

**Settlement time auto-detection.** `deploy/lipmm_run.py` reads
Kalshi's `close_time` field from the event metadata for KXTRUEV
events at startup, so `--truev-settlement-iso` is no longer
required. The CLI flag is still accepted as an override.

**RMSE knob (deprecated).** `truev_model_rmse_pts` inflates the
lognormal σ to absorb model uncertainty. Default 0; symmetric
widening causes harmful boundary distortion (deep-OTM probabilities
pulled toward 50%). For asymmetric distrust use
`theo_tolerance_c` with a negative value instead.

**Backtest harnesses:**

- `deploy/truev_backtest_csv.py` — walk-forward backtest against an
  operator-supplied `(date, index, components)` CSV. Reports RMSE,
  worst-day errors, and realized σ_annual.
- `deploy/truev_fit_weights.py` — NNLS fit to recover basket
  weights after a Truflation rebalance.
- `deploy/truev_smoke.py` — quick sanity check vs the live Kalshi book.

### Staleness semantics

File and HTTP pollers default to a **3× refresh-interval** staleness
threshold: when the source goes silent (file mtime not changing,
HTTP failing), returned confidence drops to 0 for every ticker →
strategy skips. This prevents the bot from quoting off a frozen
model.

Pass `staleness_threshold_s=None` to opt out; pass an explicit
number to override.

### Manual override > registered provider

Operator-set theo overrides (from the dashboard / `set_theo_override`
endpoint) **always win** over a registered provider. The runner checks
`ControlState.theo_overrides[ticker]` first; if present, the provider
is skipped entirely. This is the operator's safety valve when the
model is misbehaving.

---

## Errors

| Endpoint | 400 | 401 | 404 | 409 | 500 | 503 |
|---|---|---|---|---|---|---|
| `/control/auth` | wrong secret | — | — | — | — | — |
| `/control/state` | — | bad/missing JWT | — | — | — | — |
| `/control/runtime` | — | bad JWT | — | — | exchange call raised | no exchange wired |
| `/control/pause`, `/resume` | bad scope/missing extras | bad JWT | — | version mismatch | — | — |
| `/control/kill`, `/arm` | — | bad JWT | — | version mismatch | kill_handler raised | — |
| `/control/set_knob`, `/clear_knob` | unknown knob, out of bounds | bad JWT | — | version mismatch | — | — |
| `/control/lock_side`, `/unlock_side` | bad side | bad JWT | — | version mismatch | — | — |
| `/control/add_event` | event has 0 markets, or validator raised | bad JWT | — | version mismatch | — | — |
| `/control/remove_event` | bad input | bad JWT | — | version mismatch | — | — |
| `/control/set_theo_override` | range, mode, reason validation | bad JWT | — | version mismatch | — | — |
| `/control/manual_order` | range/shape | bad JWT | — | version mismatch | exchange raised | no OM+exchange |
| `/control/cancel_order` | — | bad JWT | order_id unknown | version mismatch | exchange raised | no OM+exchange |
| `/control/swap_strategy` | — | bad JWT | — | — | — | — (returns 501) |

`422` is FastAPI's default for Pydantic validation failures (wrong
types, missing required fields). Most "bad input" errors above are
422 in practice; we use 400 for semantic violations the model can't
catch (e.g., out-of-bounds knob value).

---

## End-to-end Python examples

Six runnable snippets covering the most-used flows. All assume:

```python
import asyncio, httpx, secrets, os, time

BASE = "http://localhost:5050"
SECRET = os.environ["LIPMM_CONTROL_SECRET"]
```

### 1. Mint JWT and read state

```python
async def auth_and_read():
    async with httpx.AsyncClient(base_url=BASE) as c:
        r = await c.post("/control/auth", json={"secret": SECRET, "actor": "demo"})
        token = r.json()["token"]
        H = {"Authorization": f"Bearer {token}"}
        s = (await c.get("/control/state", headers=H)).json()
        print("active events:", s["active_events"])
        print("theo overrides:", len(s["theo_overrides"]))
        print("kill_state:", s["kill_state"])

asyncio.run(auth_and_read())
```

### 2. Push a fixed theo override

```python
async def push_theo(token: str, ticker: str, yes_cents: int, conf: float):
    async with httpx.AsyncClient(base_url=BASE) as c:
        r = await c.post("/control/set_theo_override", json={
            "ticker": ticker,
            "yes_cents": yes_cents,
            "confidence": conf,
            "reason": "scripted push",
            "request_id": secrets.token_hex(8),
            "mode": "fixed",
        }, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
```

### 3. Push a market-following theo

```python
# yes_cents is required by Pydantic but ignored at quote time when mode=track_mid
await c.post("/control/set_theo_override", json={
    "ticker": "KXISMPMI-26MAY-50",
    "yes_cents": 50,             # placeholder
    "confidence": 0.7,           # picks active-match mode
    "reason": "follow-the-tape",
    "request_id": secrets.token_hex(8),
    "mode": "track_mid",
}, headers=H)
```

### 4. Cancel a resting order

```python
# Get current resting orders
runtime = (await c.get("/control/runtime", headers=H)).json()
for o in runtime["resting_orders"]:
    if o["ticker"] == "KXISMPMI-26MAY-50" and o["side"] == "ask":
        await c.post("/control/cancel_order", json={
            "order_id": o["order_id"],
            "reason": "model recalibrating",
            "auto_lock": True,             # default; runner won't re-place
            "request_id": secrets.token_hex(8),
        }, headers=H)
        break
```

### 5. Add an event

```python
r = await c.post("/control/add_event", json={
    "event_ticker": "KXISMPMI-26MAY",
    "request_id": secrets.token_hex(8),
}, headers=H)
print(r.json())  # {market_count: 8, new_version: ..., ...}
```

### 6. Subscribe to the WebSocket stream

```python
import json, websockets

async def watch():
    url = f"{BASE.replace('http', 'ws')}/control/stream?token={token}"
    async with websockets.connect(url) as ws:
        async for msg in ws:
            evt = json.loads(msg)
            t = evt["event_type"]
            if t == "decision":
                rec = evt["record"]
                print(f"  {rec.get('ticker', '?')}: {rec.get('record_type', '?')}")
            elif t == "state_change":
                print(f"  state v{evt['snapshot']['version']} ({evt.get('command_type', '?')})")
            elif t == "runtime_snapshot":
                bal = evt["snapshot"].get("balance") or {}
                print(f"  balance: ${bal.get('cash_dollars', 0):.2f} cash / ${bal.get('portfolio_value_dollars', 0):.2f} port")

asyncio.run(watch())
```

---

## Versioning & stability

API version is **0.2.0** (FastAPI app version). The control plane is
not yet a stable public contract:

- Endpoint paths and request/response shapes may change between
  minor versions.
- Plugin Protocols are more stable but reserve the right to add
  optional kwargs (current pattern: defaulted kwargs are added,
  callers ignoring them keep working).
- The auto-generated `/openapi.json` is the canonical schema for
  any given commit.

Pin to a specific commit if you're integrating externally and need
stability — there's no formal LTS branch.

---

## See also

- [`CLAUDE.md`](../CLAUDE.md) — project notes (LLM-oriented but
  surfaces architectural decisions and recent changes)
- [`deploy/README_quickstart.md`](../deploy/README_quickstart.md) —
  90-second first-run guide
- `/docs` (Swagger UI on the running bot) — interactive endpoint
  explorer with request/response schemas
- `/openapi.json` — machine-readable schema dump
- [`lipmm/control/commands.py`](../lipmm/control/commands.py) —
  source of truth for all Pydantic models
- [`tests/test_theo_providers.py`](../tests/test_theo_providers.py),
  [`tests/test_multi_event.py`](../tests/test_multi_event.py),
  [`tests/test_control_theo_override.py`](../tests/test_control_theo_override.py)
  — runnable usage examples
