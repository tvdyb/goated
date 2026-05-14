# lipmm Dashboard wiki

Operator reference for the htmx + Jinja dashboard mounted by
`deploy/lipmm_run.py` (and any other deployer that wires
`mount_dashboard=True` on the `ControlServer`).

> **Companion docs:** [API.md](API.md) for the HTTP / WebSocket
> surface that drives the dashboard. This file covers the visible
> surface — what each panel means, what each button does, and how
> the layout maps to control-plane state.

---

## Table of contents

- [Login flow](#login-flow)
- [Top-level layout](#top-level-layout)
- [Status bar](#status-bar)
- [Header panels (PnL · $/hr · Markout)](#header-panels)
- [Events strip](#events-strip)
- [Strike grid](#strike-grid)
  - [Event group header](#event-group-header)
  - [Strike row (collapsed)](#strike-row-collapsed)
  - [Strike row (expanded drawer)](#strike-row-expanded-drawer)
- [Operator drawer](#operator-drawer)
  - [Theos tab](#theos-tab)
  - [Pauses tab](#pauses-tab)
  - [Knobs tab](#knobs-tab)
  - [Locks tab](#locks-tab)
  - [Manual tab](#manual-tab)
- [Decision feed](#decision-feed)
- [Fill notifications](#fill-notifications)
- [Persisted UI state](#persisted-ui-state)
- [Common operator flows](#common-operator-flows)
- [Troubleshooting](#troubleshooting)

---

## Login flow

1. Browser hits `http://<host>:<port>/` → redirects to `/login`.
2. Operator pastes the shared secret (set via `LIPMM_CONTROL_SECRET`
   env var on the bot host).
3. POST `/control/auth` returns a 24-hour JWT.
4. JWT stored in `localStorage["lipmm_jwt"]`.
5. Redirect to `/dashboard`.

> **Auth listener timing.** Dashboard scripts attach the JWT header
> to every htmx request via a `htmx:configRequest` listener
> registered AT IIFE EXECUTION TIME (before `DOMContentLoaded`), not
> inside it. This is required because htmx loads synchronously and
> scans the DOM during its own DOMContentLoaded; if our listener
> attached later, the first batch of `hx-trigger="load"` requests
> would fire unauthenticated, get 401s, and bounce the user back to
> /login. If you hit a "login → bounce" loop, hard-refresh; the
> deferred script ordering can mismatch under certain caches.

---

## Top-level layout

```
┌─────────────────────────────────────────────────────────────────┐
│ status bar (balance · PnL · events strip · presence · session) │
├─────────────────────────────────────────────────────────────────┤
│ header panels    [PnL] [Earnings $/hr] [Markout]         ▾    │
│   ─ active panel renders here ─                                │
├─────────────────────────────────────────────────────────────────┤
│ events strip (chip per active event + "add event" inline)       │
├─────────────────────────────────────────────────────────────────┤
│ event group header (KXTRUEV-26MAY11 · 15 strikes · $480 LIP …) │
│ ┌─ strike row (collapsed) ─────────────────────────────────┐   │
│ │ T1244.04  93%  [YES 99¢] [NO 1¢]  +5Y@3¢  …  TruEV 99¢ ▸│   │
│ ├─ strike row (collapsed) ─────────────────────────────────┤   │
│ │ T1254.04  …                                              ▸│   │
│ └──────────────────────────────────────────────────────────┘   │
│ decision feed (most recent quoting decisions, JSONL tail)       │
├─────────────────────────────────────────────────────────────────┤
│ [⚙ Operator] FAB (when drawer closed) → opens 380px right-side │
│ drawer with the 5 mutator tabs (Theos / Pauses / Knobs / Locks │
│ / Manual)                                                       │
└─────────────────────────────────────────────────────────────────┘
```

The whole page lives in `lipmm/control/web/templates/dashboard.html`.
Each visual block is its own partial under
`lipmm/control/web/templates/partials/`. The scrollable region is
`<main id="ws-mount">` (NOT the window).

---

## Status bar

`partials/status_bar.html` — pinned at the top, always visible.

| Cell | Source | Color rules |
|---|---|---|
| Connection pill | WebSocket state (live/connecting/disconnected/error) | green/amber/red |
| Balance | `runtime.balance.cash_dollars` | dim text |
| Total PnL | sum of `position.realized_pnl_dollars` across positions | green > 0, red < 0 |
| Tab presence | `broadcaster.presence()` + tab count | dim |
| Actor | JWT `sub` claim | dim |
| Kill state | `state.kill_state` | red if killed |

The connection pill is the operator's first signal that something is
wrong. If it goes red, all OOB swaps stop arriving — the dashboard is
showing stale data. The pill is set in `dashboard.js::openWebSocket`.

---

## Header panels

`partials/header_panels.html` — three tabs at the top of the
scrollable area, BELOW the status bar but above the strike grid.
Promoted from the operator drawer to top-of-page so they're visible
without opening the drawer.

Tabs (one visible at a time, persisted across reloads):

### PnL

Per-position grid populated by `GET /control/pnl_grid` (HTMX,
polls every 10s). Columns:

```
ticker | qty (Y/N) | resting | avg | total $ | MTM @ mark | unrealized
       | theo (provider/manual) | exp@settle | edge¢ | realized | fees
```

Totals row at the bottom: total exposure, MTM, unrealized, expected
settlement payout.

> **Caveat on short YES positions.** For `qty < 0` (= we're long NO),
> `avg_cost` is the YES price we OPENED the short at. To interpret
> as a long-NO position, the NO cost basis = `100 − avg_cost`. The
> grid's `unrealized` correctly handles this; reading individual
> columns out of context can be misleading.

### Earnings $/hr

Histogram of LIP $/hr earning rate sampled once per minute over
the bot's lifetime (`logs/<event>_decisions/earnings_history.jsonl`).
Bins: 0, 0.05, 0.10, 0.25, 0.50, 1.00, 2.00, 4.00, 8.00, 16.00 $/hr.

Refreshes every 60s. Shows time-weighted mean and peak rate.

### Markout

Per-fill +1m/+5m mid-drift table from in-memory `MarkoutTracker`.
Fills detected via cycle-over-cycle position delta; mids sampled
async at +1m and +5m horizons. Toxic flag fires when 5m markout <
−2¢ across ≥ 2 fills.

> **Why this matters.** If markouts are persistently negative, your
> fills are adversely selected — you're being picked off by faster
> or better-informed counterparties. The toxic flag is your "shut
> the strategy down" signal. Negative markouts < −3¢ over many
> fills means the model or proxies are stale or basis-blowing.

---

## Events strip

`partials/events_strip.html` — horizontal row of chips for each
active event the bot is trading. Chip layout:

```
[KXTRUEV-26MAY11 · 15 · $480/h ×]  [+ add event]
```

- **Click ×**: removes event via `POST /control/remove_event`.
  Optional `cancel_resting=true` bulk-cancels any open orders.
- **+ add event**: inline form posts `/control/add_event`.
  Validates the event ticker against Kalshi at submit time (rejects
  if 0 tradable markets).

The bot's "active events" set lives in `ControlState._active_events`.
The runner's `_MultiEventTickerSource` reads it each cycle.

---

## Strike grid

`partials/strike_grid.html` — the operational center of the dashboard.
Updates via OOB swap on every runner cycle (~3s).

### Event group header

Per-event header above each event's strikes:

```
KXTRUEV-26MAY11 · 15 strikes · 3 quoting · $480 LIP · $34.26 capital
   · $5.20 proj-rem · 8.5% avg-share (12 strikes)
   · $0.0456/m · $2.735/h · $65.64/d · expires in 5h 47m
```

Chip definitions:

| Chip | Source | Meaning |
|---|---|---|
| `N strikes` | strike count | total in event |
| `N quoting` | count where override is set | NOT the count where we have resting orders — that's `quoting_strike_count` |
| `$X LIP` | sum of `lip.period_reward_dollars` | total LIP pool for this event's strikes |
| `$X capital` | resting collateral + position cost basis | how much of your wallet is committed here |
| `$X proj-rem` | per-strike pool_share × period_reward × (remaining/period) summed | forward-looking projected LIP from now to period end |
| `X% avg-share (N strikes)` | mean pool_share across strikes where we have resting | "of the strikes I'm playing, how big a slice am I getting" |
| `$X/m · $X/h · $X/d` | per-strike share × reward time-normalized | live earning rate |
| `expires in Xh Ym` | countdown to LIP period end | yellow < 1h, red post-expire |

### Strike row (collapsed)

Grid columns: `name | % chance | spread | Yes | No | position | resting | LIP | Theo | ▸`

```
T1244.04        93%    7¢   YES   NO    +5 Y    B 88¢×100   $60   99¢ TruEV  ▸
…Y11-T1244.04                88¢   95¢   @3¢                                  
```

- **% chance**: Kalshi orderbook mid (NOT our theo). Blue bar gauge.
- **spread**: `best_ask − best_bid`. Tighter = healthier book.
- **YES / NO**: best bid (YES) and 100−best_bid (NO badge view).
- **position**: signed qty + Y/N letter + avg cost cents. Green Y if
  long YES, red N if short YES (= long NO).
- **resting**: top 5 of our orders. Multi-row when both sides active.
- **LIP**: per-strike LIP reward in dollars (from `incentive_programs`).
- **Theo**: our model's view. **Color rules**:
  - `var(--info)` (cyan) = TruEV provider output
  - `var(--lip)` (yellow) = operator manual override
  - `var(--ink-dim)` (gray) = no theo
  - When RMSE inflation is active and raw ≠ adjusted, shows BOTH:
    `raw 0.4¢` (dim teal, smaller) above `27¢ TruEV` (cyan, larger)
- **▸ chevron**: expands the strike for detail.

### Strike row (expanded drawer)

Click the chevron to expand. Shows:

1. **Orderbook L2 ladder** (top 12 levels per side, expandable to 50).
   Greyed-out rows = our orders (so we can see the depth without us).
2. **Our resting orders** panel — per-row [cancel] button. Cancel
   auto-locks the side (default).
3. **LIP incentive detail**:
   - `reward $X.XX target Nct discount N% type liquidity`
   - `time left Xh Ym` countdown
   - `pool share X.XX% projected (period) $X.XX`
   - `projected (remaining) $X.XX` ← from NOW to period end
   - `per hour $X · per day $X`
   - `yes / no normalized` — our raw scores
   - `our score / total (yes+no)`
   - `PER-RESTING MULT (DF^N)` — per-order multiplier, with `·off`
     flag if BELOW the qualifying threshold (= zero LIP earnings)
   - `LIP queue headroom` — cents distance from current best to the
     qualifying threshold per side
4. **Theo override form** (mode select + cents input + confidence +
   reason + optional auto-clear). Two-step confirm: type the ticker
   to confirm, then click "override theo".
5. **Confidence-scale explainer** — table mapping confidence to
   strategy mode (active-penny / match / follow / skip).
6. **Per-strike knob overrides** (chips for active overrides + "set
   strike" / "set event" form):
   - Knob dropdown lists every permitted name
   - Side selector (`both` / `bid (yes)` / `ask (no)`) — per-side
     overrides layer ON TOP of "both" overrides
   - Set strike button → POST `/control/set_strike_knob`
   - Set event button → POST `/control/set_event_knob`

---

## Operator drawer

Right-side panel sliding in from a floating action button (FAB) at
the bottom-right. Five tabs (drawer state + active tab persist in
`localStorage`).

### Theos tab

Lists all active theo overrides with timestamp and actor. Clear
button per row.

### Pauses tab

Three pause scopes: global, per-ticker, per-(ticker, side). Each row
has a clear button.

### Knobs tab

Master list of every permitted runtime knob. Each row shows:

- **Current value** (with override pill if active)
- **Slider + numeric input** spanning the bounds
- **Set / Clear** buttons (POST `/control/set_knob`)
- **Description** explaining what the knob does and recommended values

> Knobs listed here are global. For per-event or per-strike (or
> per-strike-per-side) scopes, use the strike row's expanded drawer
> form. Precedence: strike-side > strike (both) > event > global >
> default.

### Locks tab

Lists every (ticker, side) lock with reason, locked-at timestamp, and
optional auto-unlock time. Form to set a new lock.

### Manual tab

Standalone manual-order form. Two-step confirm (ticker re-type)
before submission. Routes through the same risk-gate stack as
strategy-placed orders.

---

## Decision feed

`partials/decision_feed.html` — append-only stream of the last 50
quoting decisions. Filtered by:

- **All** (default)
- **Only-quotes** (skips degenerate-no-theo events)
- **Only-fills** (events where a fill was detected)

Each entry shows ticker, cycle, decision (bid/ask price + size +
mode), strategy reason, risk-gate outcome.

The full log is at `logs/<event>_decisions/decisions_YYYY-MM-DD.jsonl`
(JSONL, rotated daily, gzipped + capped at 2GB by `RetentionManager`).

---

## Fill notifications

When the runner detects a position delta in a cycle, it emits a `fill`
WS event. The dashboard's HTML adapter renders this as an
invisible-but-discoverable `<div class="fill-event">` swapped into
`<div id="fill-events">` (hidden container at the page root).

`dashboard.js` observes that mount via `MutationObserver`. On new
child:

1. **Sound**: two-tone beep. Ascending (440→659 Hz) for buys, descending
   for sells. Requires AudioContext unlock — happens automatically
   on the first user click on the page.
2. **Browser Notification**: title `BUY 60 @ ~41¢`, body with ticker.
   Requires Notification permission grant (prompt fires once per
   browser+host on first dashboard load).
3. **Toggle**: `localStorage["lipmm_fill_notify"] = "0"` disables.
   Default on.

Price shown is the cycle's mid as a proxy; exact per-fill price
requires `/portfolio/fills` from Kalshi which isn't plumbed.

---

## Persisted UI state

The following preferences are stored in `localStorage` and survive
page reloads:

| Key | Purpose |
|---|---|
| `lipmm_jwt` | Auth token |
| `lipmm_actor` | Display name |
| `lipmm_drawer_open` | Drawer collapsed/expanded |
| `lipmm_active_tab` | Last viewed drawer tab |
| `lipmm_htab` | Last viewed header-panel tab |
| `lipmm_htab_collapsed` | Header panels collapsed |
| `lipmm_expanded_strikes` | Set of strike slugs the user expanded |
| `lipmm_theo_drafts` | In-progress theo override values (per strike) |
| `lipmm_knob_drafts` | In-progress knob input values (per strike) |
| `lipmm_fill_notify` | Fill notification toggle |

Drafts get preserved across OOB swaps via `hx-preserve` on the
forms, plus `applyTheoDrafts` / `applyKnobDrafts` on every
swap-completion event. Without these, the user can't type into a
form because the 3s OOB swap would destroy their input mid-keystroke.

---

## Common operator flows

### Set up a new event from scratch

1. Status bar `+ add event` → type event ticker, hit enter.
2. Wait for first cycle to render strikes in the grid.
3. Open drawer → Knobs tab → set `dollars_per_side = 5` (or
   whatever your cap allows). Set `min_theo_confidence = 0.10`.
4. For TruEV markets: anchor must already be set in
   `_truev_index.py`. Provider auto-registers, theos appear in
   cyan within seconds.
5. For non-TruEV markets: open the strike's expanded drawer, set
   a manual theo override with a confidence level. Bot starts
   quoting next cycle.

### Hedge an unexpected fill (without panicking)

1. Click the filled strike's expand chevron.
2. In "Our resting" panel, click `cancel` on any same-side orders
   (auto-locks the side; bot won't re-place).
3. Use Manual tab to place an opposite-side order at a price you
   choose. Routes through risk-gate stack.
4. Once flat, lift the side-lock from the Locks tab.

### Distrust the model temporarily (asymmetric)

The cleanest way to express "I don't want to fill near theo" without
muting the bot entirely:

- Strike row expanded → knob form → name `theo_tolerance_c` →
  value `-3` → side `both` → "set strike".

The bot continues quoting, but quotes stay 3¢ further from theo on
both sides. To disable on bid only (and let ask quote tight): same
form, set `side = bid` (per-side override layers on top).

### Trade with explicit risk caps

CLI: `--cap-dollars 20` → `MaxNotionalPerSideGate(max_dollars=10)`.

Per-strike override: `dollars_per_side = 3` on the strike row form.

Combined: gate auto-lifts to whichever is bigger (operator's
explicit `dollars_per_side` wins over gate's constructor value).

### Kill switch

Status bar → kill button (red). Two-step: kill puts the bot in
`killed` state, cancels all resting orders. To resume:

1. Click "arm" → state goes `killed → armed`
2. Click "resume" → state goes `armed → off`, bot resumes quoting

The arm step exists so a single accidental click doesn't restart
quoting after a kill.

---

## Troubleshooting

### "I log in but bounce back to /login immediately"

Likely a JWT race condition where htmx fires `hx-trigger="load"`
requests before `dashboard.js` attached the auth listener. Hard-
refresh the page (Cmd+Shift+R). If persistent, check
`LIPMM_CONTROL_SECRET` env var matches the secret you're pasting.

### "Strike grid shows 0% on everything"

Either:
- TruEV provider not getting fresh commodity data (`forward_age_s`
  > threshold). Check the bot's stderr for yfinance / TE errors.
- Anchor is wrong / stale. Re-run `deploy/truev_reanchor.py`.
- All strikes are deep ITM/OTM and the gauge is showing market mids
  (not our theo). Check the Theo column for cyan values.

### "Bot isn't quoting anywhere"

Most common cause is `min_theo_confidence` gate failing. Check the
decision feed for "theo confidence X < gate Y" reasons. Options:
- Lower `min_theo_confidence` knob to e.g. 0.05
- Set per-strike theo overrides with confidence 1.0
- For TruEV near settle: `tau_factor` decay can crush confidence
  in the final ~hour. Set `min_theo_confidence` very low for the
  last stretch.

### "Bot got filled at a bad price"

Check the strike's expanded drawer:
1. Markout tab — was this a one-off or persistent?
2. Decision-feed reason for the cycle of the fill
3. Anti-spoofing cap — was `theo_tolerance_c` set high enough that
   bot was bidding above your believed fair?
4. Desert mode — is the strike triggering desert (`gap > 10¢`)?
   Desert bypasses the confidence cascade.

### "Scroll keeps jumping when updates arrive"

Earlier versions of `dashboard.js` read `window.scrollY` for scroll
preservation, but the scrollable region is `#ws-mount`, not the
window. Verify you're on the latest `dashboard.js` build — log
message at startup should read
`[lipmm] dashboard.js loaded — knob-drafts+scroll-preserve build`.

### "I set a knob but the bot ignores it"

Check the JWT first (mutations require Bearer auth). Then verify
the knob name is in the permitted list (`state.py::knob_bounds`).
Then check precedence — if the strike has a per-strike override,
your global knob change won't take effect on that strike. The
strike row's "active overrides" chips show what's currently
binding.
