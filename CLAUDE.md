# CLAUDE.md — goated

## Identity

Reusable market-making framework (`lipmm/`) for Kalshi-style binary
markets, plus a server-rendered htmx + Jinja operator dashboard with
runtime control (pauses, kill, knobs, manual orders, theo overrides,
LIP-incentive surfacing). The framework is plugin-driven: a new market
is one TheoProvider implementation + one config + one CLI invocation
of `deploy/lipmm_run.py`.

Originally built around a soy commodity bot (`KXSOYBEANMON`, GBM theo,
Kalshi-implied vol, IBKR hedge upgrade path). Operating under
strategic frame **F4** (see `prompts/build/PREMISE.md`).

**Status: not running.** The soy bot is paused. The lipmm framework
is feature-complete (1552 tests passing repo-wide; ~430 lipmm-core)
and the deploy entry point (`python -m deploy.lipmm_run
--event-ticker ...`) has been partially smoked against
KXISMPMI-26MAY — the bot stands up, dashboard renders, theo
overrides + manual orders + LIP scoring all flow end-to-end. First
full live trading session is still pending.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install jinja2          # Phase 4 dep, may be missing locally
pytest                       # run all tests (~1552; lipmm core: ~430)
ruff check .                 # lint (config in pyproject.toml)
```

## Running the bot

The current entry point is `deploy/lipmm_run.py`. It wires the lipmm
framework against one Kalshi event and brings up the dashboard at
port 5050. Bot starts safe-by-default: `StubTheoProvider` returns
`confidence=0.0` for every strike, so the strategy quotes nothing
until the operator sets per-ticker theo overrides via the dashboard.

```bash
# 1. Kalshi credentials (existing names from soy days)
export KALSHI_API_KEY="..."
export KALSHI_PRIVATE_KEY_PATH="/path/to/private_key.pem"

# 2. Dashboard secret (one-time per deployment)
export LIPMM_CONTROL_SECRET="$(python -c 'import secrets; print(secrets.token_hex(16))')"
echo "$LIPMM_CONTROL_SECRET"   # save — paste on the dashboard login page

# 3. Run
python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY
```

Then open `http://<host>:5050`, paste the secret, set theo overrides
per strike via the "Theo overrides" panel.

CLI flags: `--cap-dollars` (default 100), `--strategy default|sticky`,
`--cycle-seconds` (default 3.0), `--port` (default 5050),
`--decision-log-dir`, `--retention-bytes` (default 2 GiB).

Full runbook: `deploy/README_quickstart.md`.

**Old soy entry points (`deploy/lip_mode.py`, `deploy/main.py`,
`deploy/dashboard.py`) are stale.** They predate the lipmm framework
and are not currently maintained. Do not start them without a refresh.

## Mac Mini deployment

Bot runs on Mac Mini via Tailscale. Access from anywhere:
- Dashboard: `http://100.95.127.115:5050`
- SSH: `ssh efloyal@100.95.127.115`
- Bot screen: `screen -r lipmm`
- Detach: Ctrl+A, release, D
- Private key on the Mac Mini at `~/Documents/soybeanProject.txt`

## Repo layout

```
lipmm/                 ← Framework (the current home for new code)
  theo/                Pluggable theo providers (TheoProvider Protocol)
  quoting/             Strategies (DefaultLIPQuoting, StickyDefenseQuoting)
  execution/           ExchangeClient Protocol + KalshiExchangeAdapter
  risk/                Pre-trade gates (notional, throttle, endgame)
  observability/       DecisionLogger (JSONL) + RetentionManager (gzip + cap)
  control/             Control plane (Phase 1-9):
    state.py           ControlState — pauses, kill, knobs, locks, theo overrides
    server.py          FastAPI app — JWT auth, all endpoints, WS
    broadcaster.py     WebSocket fan-out for multi-tab sync
    web/               htmx + Jinja dashboard (templates, static, renderer)
  incentives/          Kalshi /incentive_programs surface (Phase 8)
  runner/              LIPRunner — per-cycle orchestrator
  __init__.py          Public API surface

deploy/
  lipmm_run.py         CURRENT entry point — wires lipmm against any event
  _stub_theo.py        StubTheoProvider — safe-by-default for new markets
  README_quickstart.md 90-second deploy runbook
  lip_mode.py          STALE — old soy bot (predates lipmm)
  main.py              STALE — old spread-capture (predates lipmm)
  dashboard.py         STALE — old Flask dashboard (replaced by lipmm/control/web/)

feeds/kalshi/
  client.py            KalshiClient — REST, RSA-PSS auth, rate limiter,
                       get_incentive_programs (Phase 8)
  auth.py              KalshiAuth (reads env vars by default)
  lip_pool.py          LIP DuckDB store; healed in Phase 8 to use real API
  lip_score.py         LIP score tracker (legacy, soy-era)

engine/, feeds/{pyth,usda,weather,ibkr,cme}, hedge/, attribution/,
state/, fees/, models/, validation/, calibration/, analysis/, audit/,
prompts/, research/, mm-setup-main/  ← Soy-era; not used by lipmm
```

## Current state

- **lipmm framework feature-complete.** 11 phases shipped:
  state + JWT auth + pause/kill/knobs (1), manual orders + side locks
  (2), WebSocket fan-out + multi-tab + optimistic concurrency (3),
  htmx+Jinja dashboard (4), disk retention manager (5), positions/
  orders panel + surgical cancel (6), manual theo overrides via
  dashboard (7), Kalshi /incentive_programs surface (8), single-
  command deploy entry point (9), full dashboard redesign +
  per-strike grid + operator drawer (10), runner ticker bug + per-
  strike LIP scoring per the **CFTC-filed Appendix A formula** (11).
- **1552 tests passing repo-wide; ~430 lipmm-core.**
- **Soy bot paused.** The new entry point `deploy/lipmm_run.py`
  replaces `deploy/lip_mode.py` etc.
- **Dashboard surface available**: kill/arm flow, pause global/ticker/side,
  knob overrides, side locks, manual orders with confirm + risk-gate
  routing, theo overrides with two-step confirm + confidence-scale
  explainer, positions panel (qty + Yes/No badge + realized PnL
  coloring), resting-orders panel (per-row cancel button), balance
  pill + total-PnL pill, decision feed, LIP incentives panel with
  countdown + per-strike pool share, projected payout, per-hour and
  per-day reward rates, per-resting multiplier (with `·off` flag for
  bids below the qualifying threshold), presence pill (multi-tab),
  optimistic concurrency on every mutation.
- **Strategy: 3-tier confidence brackets.** `DefaultLIPQuoting` has
  three active-mode branches gated by `theo.confidence`:
  - `active-penny`: conf ≥ `penny_inside_min_confidence` (default
    **0.95**). Quotes `best_bid + 1` / `best_ask − 1` — INSIDE best.
  - `active-match`: `match_best_min_confidence` ≤ conf <
    `penny_inside_min_confidence` (default 0.70). Quotes
    `best_bid` / `best_ask` — AT best (sits at LIP reference price).
  - `active-follow`: conf < `match_best_min_confidence` (and ≥
    `min_theo_confidence` 0.10). Quotes `best_bid −
    max_distance_from_best` / `best_ask + max_distance_from_best` —
    1¢ BEHIND best by default.
  Below 0.10 → both sides skip. Anti-spoofing cap
  (`theo_tolerance_c`) binds in all branches.
- **Ctrl+C bulk-cancels.** `deploy/lipmm_run.py` shutdown path now
  awaits `runner.cancel_all_resting()` (15s timeout) before closing
  the Kalshi client, so SIGINT leaves zero naked quotes on the book.
- **Cancel-from-dashboard auto-locks the side.** `POST
  /control/cancel_order` engages a `side_lock` on (ticker, side)
  after a successful cancel by default (`auto_lock=true`). The
  runner skips locked sides next cycle, so the bot doesn't
  immediately re-place the cancelled order. The expanded strike's
  "Our resting" panel surfaces a "lift lock" button per side so the
  operator can manually resume quoting. Pass `auto_lock: false` in
  the request body to opt out.
- **Market-following theo mode.** `TheoOverride` carries a `mode:
  "fixed" | "track_mid"` field. `mode="track_mid"` makes the runner
  recompute theo each cycle as the orderbook mid `(best_bid +
  best_ask) / 2`, with `confidence` still operator-controlled (so
  the 3-tier strategy modes still apply). Degenerate books (one-
  sided / crossed / 99¢ best) force confidence to 0 → strategy
  skips that strike that cycle. The dashboard's theo override form
  has a "Mode" select (fixed cents / market mid); activation
  requires the operator to type the ticker (same 2-step confirm
  pattern as fixed overrides). Strike chip shows "mid" badge in
  market-following mode and the Theo column displays the live mid.
- **Deploy partially smoked.** Bot stands up against KXISMPMI-26MAY,
  dashboard renders, manual orders + theo overrides + LIP scoring
  all work. First full live trading session still pending.
- **Theo stack stays soy-specific.** `lipmm/theo/providers/` only
  ships `GBMCommodityProvider` (used by soy). New markets need their
  own provider; until then, `StubTheoProvider` + dashboard overrides
  is the path.
- See `prompts/theo/README.md` for legacy soy theo stack status.

## Main loop (lipmm cycle, default 3s)

For each cycle, for each ticker yielded by the `TickerSource`:
1. **Control gate**: skip cycle if killed or globally paused; skip
   ticker if paused; force `skip=True` on side if side-paused or
   side-locked.
2. **Theo**: check `ControlState.get_theo_override(ticker)` first; if
   present, build `TheoResult(source="manual-override:...")`. Else
   call the registered `TheoProvider.theo(ticker)`.
3. **Orderbook**: `exchange.get_orderbook(ticker)`; compute best
   bid/ask **excluding our own resting** orders.
4. **Strategy**: `strategy.quote(ticker, theo, orderbook, our_state,
   now_ts, time_to_settle_s, control_overrides=...)` returns a
   `QuotingDecision` with bid/ask SideDecisions.
5. **Risk**: `RiskRegistry.evaluate(context)` may veto sides
   (turning them into `skip=True`).
6. **Apply**: `OrderManager.apply()` for each side — decides
   place / amend / cancel-and-replace / cancel / no-op against
   the exchange.
7. **Decision log + broadcast**: `decision_recorder` writes JSONL
   AND broadcasts to dashboard tabs.

The dashboard's runtime panel polls positions/orders/balance every
5 s; the LIP incentives panel refreshes hourly.

## Kalshi API quirks (still load-bearing — discovered during soy live)

- **Ticker format**: `KXSOYBEANMON-26APR3017-T1186.99` (not `SERIES-YYMONDD-INDEX`).
- **Event ticker field**: `event_ticker` (not `ticker`) in events response.
- **Order creation**: do NOT send `time_in_force: "gtc"` — causes 400. Omit it.
- **Orderbook**: response key is `orderbook_fp` with `yes_dollars` and `no_dollars` arrays of `[price_str, size_str]`.
- **Prices**: dollars as strings (`"0.4500"`) in responses, cents as integers in order creation (`yes_price: 45`).
- **Positions**: `position_fp` is a float string (`"11.00"`), not integer.
- **Batch cancel**: `DELETE /portfolio/orders/batch` returns 404; use individual cancels (or `/portfolio/orders/batched` per the lipmm adapter).
- **Rate limiting**: Basic tier = 200 read tokens/sec, 100 write tokens/sec (10 tokens/request). 20 reads/sec, 10 writes/sec effective.
- **Amend endpoint**: `POST /portfolio/orders/{id}/amend` returns 400; fallback to cancel+place.
- **Settlement vs expiration**: `expiration_time` is NOT settlement time; settlement is earlier.
- **/incentive_programs is unauthenticated.** No auth header needed; pagination via `next_cursor`. `period_reward` is in centi-cents.
- **LIP score formula is EXPONENTIAL** per Kalshi's Aug-2025 CFTC self-cert (Appendix A in `Downloads/rules09082530054.pdf`): `Score(bid) = DiscountFactor^(RefPrice − Price) × Size`. With DF=0.25 → distance 0=1.00, 1=0.25, 2=0.0625, 3=0.0156. NOT linear `1 − distance × DF`. (See "LIP scoring" section below.)
- **`with_nested_markets=true`** on `/events/{ticker}` to get markets in the response. Default false → `markets: []`. Code reads BOTH `event.markets` and the sibling top-level `markets` field defensively.
- **Market status filter is a deny-list, not allow-list**. Kalshi uses `"active"` (not `"open"`); `_EventTickerSource` skips `{settled, finalized, closed, unopened, deactivated}` and treats anything else as tradable.

## LIP scoring (Kalshi Aug-2025 CFTC self-cert, Appendix A)

Authoritative spec: `~/Downloads/rules09082530054.pdf`. The framework
implementation lives in `lipmm/incentives/score.py`.

Per-snapshot procedure (rerun every 1s during a Time Period):

1. **Reference Yes Price** = highest yes bid IF strictly < 99¢. A 99¢
   best bid disqualifies the side that snapshot.
2. **Qualifying walk-down**: from the Reference Price, walk down
   accumulating size; ALL bids at each visited level qualify until
   cumulative ≥ Target Size. Bids below the resulting threshold
   price do NOT qualify, no matter how big.
3. `Score(bid) = DF^(RefPrice − Price(bid)) × Size`. Exponential.
4. `NormalizedScore(bid) = Score / Σ scores on the side`. Each side's
   normalized scores sum to 1.0 across all users.
5. `SnapshotLPScore(user) = Σ user's yes-normalized + Σ user's
   no-normalized`. Range [0, 2].
6. Σ all users' SnapshotLPScores ≈ (1 if yes side has any qualifying
   bids) + (1 if no side has any).
7. `TimePeriodLPScore(user) = Σ_snapshots user / Σ_snapshots all`.
   We approximate instantaneously as `snapshot / total_snapshot`.
8. `Payout(user) ≈ TimePeriodLPScore × TimePeriodReward`.

### Eligibility (who can earn)

Eligible Participants = all Kalshi members EXCEPT:

- (i) affiliates of Kalshi
- (ii) members with a signed Market Maker Agreement
- (iii) Introducing Brokers, FCMs, and customers transacting via an
  IB or FCM

Personal accounts are eligible. Members under an MMA earn through a
separate program; LIP is for everyone else.

### Time Period mechanics

A **Liquidity Incentive Schedule** = a sequence of one or more
**Time Periods**. Each Period has its own (Target Size, Discount
Factor, Time Period Reward). Periods may overlap and may straddle
trading sessions; boundaries are at non-fractional seconds.

Per-Period maximums (Appendix A bounds):

| variable | max |
|---|---|
| Time Period | ≤ 31 days |
| Target Size | 100 < target < 20,000 contracts |
| Discount Factor | ≤ 1.00 |
| Time Period Reward | $10 ≤ reward ≤ $1,000 **per calendar day encompassed in the Period** |

Sanity check: KXISMPMI-26MAY $125 over a ~5-day Period = $25/day,
well within the $10–$1,000/day band.

### Snapshot timing (anti-gaming)

Snapshots happen **once per second**, but the exact time within the
second is drawn from a **uniform random distribution**. This kills
"requote 100ms before the second tick" gaming. Practically: the
strategy must be consistently resting at the right price across
*every* moment of the second, not at chosen instants. Cancel/
replace cycles need to be tight (3-second cycles are the floor we
operate at; sub-cycle drift is unavoidable).

### Yes-ask ↔ No-bid symmetry

For scoring purposes, a yes ask at price `p` is treated as a no bid
at `100 − p`. Both sides are scored symmetrically, and a single
user can earn from both sides simultaneously. The
`SnapshotLPScore` range is [0, 2] precisely because it sums two
per-side normalized scores that each cap at 1.

### Payment threshold and rounding

`Payout(user) = TimePeriodLPScore × TimePeriodReward`, rounded
**DOWN to the nearest cent**, AND only paid out if **≥ $1.00**.
Sub-dollar earnings forfeit. Implication: on small-pool / low-share
programs, marginal-share work is worthless until cumulative payout
crosses $1.

### Dashboard surface

Per strike, the LIP detail block shows: pool share %, projected
(full period), per-hour and per-day reward rates, per-side
normalized score breakdown (yes / no), and per-resting multiplier
with a `·off` flag for orders below the qualifying threshold.

### Common surprises

- **Low-target market is HARSH.** A market with target 1000
  contracts and a thick best level (e.g. 5,000 at the best price)
  qualifies *only* the best level. Every off-best resting earns 0,
  even though the multiplier display reads non-zero (the multiplier
  shown for disqualified orders is informational — distance from
  reference; the actual contribution is 0).
- **A 99¢ best bid disqualifies the side.** If somebody parks a
  trivial bid at the highest possible price, your side earns
  nothing that snapshot. Cancel any of our resting orders that drag
  the best bid to 99¢.
- **DF=0.25 punishes off-best HARD.** distance 0 → 1.00,
  distance 1 → 0.25, distance 2 → 0.0625. At DF=0.25 the only
  resting that meaningfully scores is sitting AT the reference
  price.

## Key paths

| File | Purpose |
|---|---|
| `deploy/lipmm_run.py` | Entry point — `python -m deploy.lipmm_run --event-ticker ...` |
| `deploy/_stub_theo.py` | StubTheoProvider — safe-by-default theo for new markets |
| `deploy/README_quickstart.md` | 90-second runbook |
| `lipmm/__init__.py` | Public API surface — single import for everything |
| `lipmm/runner/runner.py` | LIPRunner — main loop orchestrator |
| `lipmm/control/server.py` | ControlServer + FastAPI app |
| `lipmm/control/state.py` | ControlState — pauses, kill, knobs, locks, theo overrides |
| `lipmm/control/web/` | Dashboard (templates, static, renderer) |
| `lipmm/incentives/kalshi.py` | KalshiIncentiveProvider (unauth httpx) |
| `lipmm/incentives/score.py` | Per-strike LIP score per CFTC Appendix A |
| `lipmm/quoting/strategies/default.py` | DefaultLIPQuoting (active-penny / active-follow / desert / deep-itm/otm) |
| `lipmm/observability/retention.py` | RetentionManager (2 GiB cap, gzip) |
| `lipmm/execution/adapters/kalshi.py` | KalshiExchangeAdapter |
| `prompts/build/PREMISE.md` | Canonical F4 strategic premise |
| `state/PROJECT_CONTEXT.md` | Soy-era state file |

## Module status

**lipmm framework (current, tested, deployable):**
- `lipmm/theo/` — TheoProvider Protocol + GBMCommodityProvider (soy only)
- `lipmm/quoting/` — DefaultLIPQuoting (with active-penny branch at high theo confidence), StickyDefenseQuoting
- `lipmm/execution/` — OrderManager + ExchangeClient Protocol + KalshiExchangeAdapter
- `lipmm/risk/` — MaxNotionalPerSideGate, MaxOrdersPerCycleGate, EndgameGuardrailGate
- `lipmm/observability/` — DecisionLogger (JSONL, daily rotation, sub-rotate at 500MB), RetentionManager (gzip closed files, evict oldest, hourly)
- `lipmm/control/` — Phases 1-9 of the control plane (see Current state)
- `lipmm/incentives/` — IncentiveProgram, KalshiIncentiveProvider, IncentiveCache (hourly refresh, fault-tolerant); `compute_strike_score`, `StrikeScore`, `RestingMultiplier` for per-strike pool-share / projected payout per CFTC Appendix A
- `lipmm/runner/` — LIPRunner with control_state hook, kill_handler hook, decision_recorder hook

**Soy-era (paused, retained for reference):**
- `engine/{quoter,implied_vol,markout,seasonal_vol,settlement_gate,taker_imbalance,wasde_density,weather_skew,goldman_roll,kill,risk}.py` — soy components, pre-lipmm
- `state/positions.py` — soy position store
- `feeds/{pyth,usda,weather,ibkr,cme}/` — soy data sources
- `feeds/kalshi/lip_pool.py` — healed in Phase 8 to consume real API; DuckDB persistence still useful
- `attribution/pnl.py` — PnL attribution tracker
- `hedge/` — IBKR hedge layer (account opened, gateway unconfigured)
- `engine/rnd/` — RND pipeline (blocked on IBKR)

**Stub / empty:** `calibration/`

## Known issues / not-yet-fixed

_(none open at the moment — fixed: knob defaults, `desert_threshold_c`
+ `penny_inside_min_confidence` exposed)._

## Next steps (priority order)

1. **First full live deploy** — run `python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY` for an actual trading session. The bot has been smoked but not run continuously through fills.
2. **Write a real PMI TheoProvider** — replace StubTheoProvider with consensus-based or Bayesian-from-regional-Feds math. Drop into `lipmm/theo/providers/ism_pmi.py` and swap the `theo_registry.register(...)` line in `deploy/lipmm_run.py`.
3. **Verify settlement-time handling for new markets** — `RunnerConfig.settlement_time_ts` is currently None in `lipmm_run.py`. Add a `--settlement-time-utc` flag if the endgame guardrail needs to bite.
4. **Resume soy** if/when desired — needs reconnect of `lipmm_run.py` to GBMCommodityProvider + a working forward source.
5. **IBKR IB Gateway** — connect, subscribe to CME ag data, pull real ZS options chain (T-45). Soy-side prereq for the RND pipeline.
6. **Polymarket / Robinhood / other exchange adapters** — implement `ExchangeClient` Protocol; the rest of the framework already abstracts away venue.
7. **Strategy hot-swap** — Phase 1 `swap_strategy` endpoint is still 501; deferred until clearly needed.
8. **Auto-derive knob defaults from the dataclass** — prevent drift between `DefaultLIPQuotingConfig` defaults and the dashboard's knob-row tuples. Today they're independently authored; a render-time helper that reads `dataclasses.fields(DefaultLIPQuotingConfig)` would prevent the kind of drift we just fixed.

## Kill criteria (F4, soy-specific)

- **KC-F4-01**: RND misses Kalshi-resolution by >3c on >50% of buckets across 4+ settled monthly Events.
- **KC-F4-02**: Settlement-gap losses exceed gross spread for 2 consecutive months.
- **KC-F4-03**: Annualized net P&L on deployed capital <5% for 6 consecutive months.
- **KC-F4-04**: Monthly IB commissions + slippage exceed monthly Kalshi spread capture on hedgeable series.
- **KC-F4-05**: Realized markout on filled quotes exceeds 60% of captured spread for 4 consecutive weeks.

## Non-negotiables

- **lipmm hermeticity**: the `lipmm/` package may import from `feeds/kalshi/` (the auth + client live there) but **not** from `engine/`, `state/`, `attribution/`, `deploy/`. Keep the framework decoupled from soy-era code.
- No `pandas` in the hot path; no Python loops over markets/strikes in soy-era engine code.
- No Monte Carlo in the hot path; MC for offline validation only.
- No silent failures: stale data, out-of-bounds IV, feed dropouts → raise, don't publish.
- `scipy.special.ndtr` over `scipy.stats.norm.cdf`.
- `numba.njit` on all hot-path math.
- Synchronous main loop in soy-era code; `asyncio` for I/O only.
- Every order placed is `post_only=True`. Crossing the spread negates any economic edge.
- The fail-safe pattern at `engine/pricer.py:62-75` and `validation/sanity.py:38-68` is the template every new soy-era module follows.
- **lipmm has its own conventions**: dataclass-based, asyncio-first (because it's I/O-bound by design), Pydantic only at the HTTP boundary (`lipmm/control/commands.py`).
- **Dashboard mutations are auth'd** (JWT bearer); HTML pages are unauth'd shells (JS hydrates the JWT). Don't add session middleware — the localStorage + Authorization-header model is deliberate.
- **Theo overrides + knobs are runtime-only** (cleared on restart). If you change that, you also need to think about replay safety.

## Do not

- **Do not** import `pandas` in any module under `engine/`, `feeds/`, `models/`, `state/`, `validation/`, `lipmm/`. Use numpy.
- **Do not** import from `engine/`, `state/`, `attribution/`, `deploy/` inside `lipmm/`. Hermeticity is one-directional.
- **Do not** use `scipy.stats.norm.cdf`. Use `scipy.special.ndtr`.
- **Do not** swallow exceptions or return default values on error in framework code. Raise explicitly. (Control-plane endpoints translate to HTTP errors at the boundary.)
- **Do not** use `asyncio` for hot-path computation in soy-era code. The pricing loop is synchronous.
- **Do not** write Python-level `for` loops over strikes or markets in soy-era hot-path code.
- **Do not** place market orders or use `taker` side. All orders are `post_only=True`.
- **Do not** send `time_in_force` field in Kalshi order creation (causes 400).
- **Do not** use Kalshi batch cancel endpoint (`/portfolio/orders/batch`); use the lipmm adapter's path or individual cancels.
- **Do not** start the old soy entry points (`deploy/lip_mode.py`, `deploy/main.py`, `deploy/dashboard.py`) without first refreshing them — they predate the lipmm framework.
- **Do not** add new top-level packages without re-exporting through `lipmm/__init__.py` if they belong to the framework.
- **Do not** modify audit files (`audit/`). They are read-only references.
- **Do not** modify `prompts/build/PREMISE.md`. Only a strategic-pivot phase may change it.
