# CLAUDE.md — goated

> **External API reference**: [`docs/API.md`](docs/API.md) is the
> hand-curated wiki for HTTP / WebSocket endpoints, plugin Protocols,
> and TheoProvider integration recipes. The auto-generated Swagger UI
> at `/docs` (and `/openapi.json`) on the running bot has the full
> field-level schemas.

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
- **~1730 tests passing repo-wide; lipmm-core continues to grow.**
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
- **Accessible TheoProvider integrations.** Three first-class paths
  for plugging external theos in without editing source:
  - `FilePollTheoProvider` (`lipmm/theo/providers/file.py`) — polls a
    CSV or JSON file every N seconds. Any tool that can write a file
    can feed theos. Wire via `--theo-csv PATH[:PREFIX[:REFRESH_S]]`
    or `--theo-json …`. Repeatable.
  - `HttpPollTheoProvider` (`http.py`) — polls a JSON URL. Optional
    `Authorization: Bearer` header. Wire via `--theo-http
    URL[:PREFIX[:REFRESH_S]]`. Repeatable.
  - `function_provider` decorator (`_function.py`) — wraps an async
    function into a Protocol-compliant provider. Sugar over the
    boilerplate class for in-process Python.
  Both pollers default to a 3× refresh-interval **staleness threshold**:
  if the source goes silent, returned confidence drops to 0 → strategy
  skips. Pass `staleness_threshold_s=None` to opt out.
  `TheoRegistry` accepts `series_prefix="*"` as a wildcard fallback —
  one provider can serve all events. Specific-prefix providers always
  win over wildcard. Payload schema (CSV columns or JSON keys):
  `ticker, yes_cents (1-99), confidence (0-1), reason`. Out-of-range
  rows are dropped with a warning, last good snapshot stays valid on
  parse / network error.
- **Multi-event dashboard.** `--event-ticker` is now optional and
  accepts comma-separated values (`A,B,C`). The bot's active-events
  set lives in `ControlState._active_events`; operator manages it
  via the dashboard's events strip (top of grid) — chips per active
  event with × to remove, plus an inline "+ add event" button.
  `_MultiEventTickerSource` reads from state each cycle and unions
  markets across events. `POST /control/add_event` validates against
  Kalshi (rejects events with 0 tradable markets) before adding;
  `POST /control/remove_event` accepts `cancel_resting=true` to
  bulk-cancel any resting orders on that event's strikes atomically.
  Strike grid groups strikes by event with per-group section headers
  (event ticker · count · LIP). Empty-event groups appear immediately
  on add even before the next runner cycle so the operator gets
  visual feedback.
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
- **Sub-cent quoting (t1c).** Internal price representation is
  **tenths-of-a-cent** (`int t1c`; 1¢ = 10 t1c). The Kalshi adapter's
  `_parse_depth` returns levels in t1c and `_infer_tick_schedule`
  detects per-band granularity (some markets are sub-cent only at
  edges, e.g. `[(10, 100, 1), (100, 900, 10), (900, 990, 1)]`). The
  strategy adds/subtracts `tick_at(schedule, price)` instead of `1`,
  so on a sub-cent market a "penny inside" is 0.1¢. Place-order
  routes through Kalshi's fractional `yes_price_dollars="0.978"`
  endpoint when the price isn't a whole-cent multiple, with a
  one-shot fallback to integer-cent if Kalshi 4xx's. The runner
  logs each sub-cent ticker exactly once at startup
  (`subcent_market: ...`); displayed prices on the dashboard show one
  decimal when sub-cent (the `%g` Jinja filter strips trailing zeros).
- **Sub-cent theo override input.** The dashboard form's `Yes (¢)`
  field accepts `0.1..99.9` with `step="0.1"`. `SetTheoOverrideRequest`
  Pydantic field is `yes_cents: float`. Stored on `TheoOverride` as
  `yes_probability` (the float carries the 0.1¢ precision).
- **Strategy edge-case guards.** `DefaultLIPQuoting.quote` skips
  both sides on a **crossed book** (`best_bid_t1c >= best_ask_t1c`)
  with reason `"crossed book: …"`. In active-penny mode, `n_ticks`
  is clamped per-side so the target stays strictly inside the
  opposite best (prevents narrow-spread sabotage where high
  `penny_inside_distance` would otherwise cross and trigger the
  no-cross guard's pull-back).
- **Tail-only mode (`max_distance_from_extremes_c`).** Operator-
  controlled knob (default 0 = off). When > 0, hard-caps bid at N¢
  and floors ask at (100 − N)¢ regardless of theo or book. Designed
  for batch-released markets with wide spreads (02/98) where the
  middle is untrusted: turn on at e.g. 5 → bot only quotes 1..5¢ on
  bid and 95..99¢ on ask, harvesting LIP rebates safely at the
  statistical tails until the book normalizes. Configurable global,
  per-event, or per-strike via the dashboard.
- **Balance-aware sizing.** Runner caches `Balance.cash_dollars × 100`
  once per cycle and pushes to `OrderManager.set_available_cash_cents`.
  `_place_new` skips placement (logs at INFO) when
  `committed_cents + new_cents > available × 0.9`. Stops Kalshi
  insufficient-collateral push-spam.
- **Startup zombie sweep.** `deploy/lipmm_run.py` lists +
  `cancel_orders` every resting order on the account before runner
  starts. Frees collateral that the OrderManager doesn't have
  in-memory state for (prior session zombies, manual orders, etc.).
- **Adverse-selection gates.**
  - `MaxPositionPerSideGate` (`lipmm/risk/gates/position.py`): vetoes
    bid when `position_quantity >= max_position_per_side`, vetoes ask
    when `<= -max_position_per_side`. Per-strike position from the
    runner's once-per-cycle `list_positions()` cache.
  - `MidDeltaGate` (`lipmm/risk/gates/mid_delta.py`): tracks last
    seen mid per ticker; vetoes both sides if delta ≥
    `mid_delta_threshold_c` (cents). Self-clears next cycle.
- **Layered knob overrides — including per-side.** Precedence:
  strike-side ("bid" or "ask") > strike (both) > event > global >
  config default. Operator sets via the strike row's expanded drawer
  (form `data-form="strike-knob-set"` with a side selector
  `both / bid (yes) / ask (no)`). `ControlState.effective_knobs_for(
  ticker, side=...)` does the merge; the runner builds separate
  `bid_overrides` / `ask_overrides` dicts and passes them to
  `strategy.quote(...)` so the bid and ask sides see independent
  configs (different `theo_tolerance_c`, `dollars_per_side`, etc.).
  Risk gates still see the both-side merged dict.
- **`theo_tolerance_c` accepts negative values.** Bound widened to
  `[-50, 50]`. Negative tolerance REPELS the bot away from theo
  (cap = `theo − 1 + tol`; with `tol = −3`, cap = `theo − 4`). Use
  case: when you don't trust theo and don't want to fill near it.
- **`max_distance_from_extremes_c` bound widened to `[0, 99]`.** Was
  `[0, 50]`; bumped so operators can use it for one-sided LIP
  farming on deep-ITM/OTM strikes (e.g. cap bid at 80¢ on a deeply
  ITM strike to track close to LIP reference without crossing into
  uncertain mid-zone exposure).

### TruEV theo provider — KXTRUEV-* daily binaries

- **Status**: live and calibrated. Provider is
  `lipmm/theo/providers/truev.py`; basket math in `_truev_index.py`;
  forward source in `feeds/truflation/forward.py`.
- **Methodology recap (per Truflation v2.0, Feb 5, 2026)**: index
  is a Laspeyres basket of six battery metals — Cu, Li, Ni, Co, Pa,
  Pt — with per-vehicle metal intensities × EV-type production
  share as the weights. **Methodology PDF says annual rebalance**
  ("Index is rebalanced annually"), but the version history table
  on page 17 shows methodology updates labeled "Rebalance Update"
  at v1.4 (Jul 2025), v1.41 (Oct 2025), v2.0 (Feb 2026) — so the
  documented annual schedule and actual practice diverge. **Last
  rebalance: 2025-12-31** (effective Q1 2026), set the
  production-share mix to: HEV 53.99%, BEV 27.97%, PHEV 18.01%,
  FCEV 0.03%. Operator confirmed 2026-05-11: no rebalance since.
  Official Q1 2026 weights per methodology Exhibit 6: Cu 41.6%,
  Li 30.5%, Ni 13.2%, Co 8.9%, Pa 4.7%, Pt 1.1%.
- **Component sources Truflation actually uses (per their public
  TruEV product page; the methodology PDF v2.0 is intentionally
  vague — Section 5 only says "global commodity pricing organizations"
  and names no exchanges per metal)**: their site lists exactly
  **four data providers — GFEX, CME, NYMEX, SMM** — which map by
  elimination as:
    - Cu: **CME** (COMEX HG futures)
    - Pt, Pa: **NYMEX** futures
    - Li: **GFEX** (Guangzhou Futures Exchange) lithium carbonate
          futures — NOT Shanghai SE (some Truflation copy implies
          SSE, but their data-provider list says GFEX)
    - Co: **SMM** (Shanghai Metals Market) — specifically
          `SMM-CO-CM-001` China Cobalt Metal ≥99.8%, USD/T. NOT LME
          despite an earlier-version of their per-metal display
          page also referencing LME.
    - Ni: **SMM** Ni 1# refined cathode ≥99.90%, CNY/T. NOT MCX
          India (which their marketing copy "Multi Commodities
          Exchange" can read as either MCX-India or LME-generic;
          their data-provider list disambiguates → SMM).
- **Component sources WE use (live)** — three exact matches and
  three structural mismatches:
    - `HG=F`     copper (yfinance COMEX) — matches CME ✓
    - `PA=F`     palladium (yfinance NYMEX) — matches ✓
    - `PL=F`     platinum (yfinance NYMEX) — matches ✓
    - `COBALT_TE` cobalt (TradingEconomics scrape of LME `LCO1:COM`)
                  — MISMATCH (Truflation uses SMM). Tested
                  empirically; LME-spot tracks reasonably.
    - `NICK.L`   WisdomTree Nickel ETC on LSE (GBp, FX-stripped via
                 GBPUSD before caching) — MISMATCH (Truflation uses
                 SMM Ni 1#). Tested vs MCX India nickel; NICK.L
                 wins by ~1.8pt walk-forward RMSE.
    - `LITHIUM_TE` TE scrape of China lithium carbonate spot — used
                   to be `LIT` (Global X Lithium ETF) but that was
                   an equity proxy with ~0.6 beta to Russell 2000.
                   Possibly MISMATCH on contract type (Truflation
                   uses GFEX futures) but empirically TE-spot is
                   the best lithium series we have access to.
- **Source-mismatch investigation (2026-05-11) — three findings**:
    1. **GFEX LC2609 tested, rejected.** Pulled 82 days of LC2609
       (Sep 2026 contract) settles from gfex.com.cn, converted
       CNY→USD via `cny_usd.csv`. Daily-return correlation with
       Truflation's published index: **TE-Li +0.391** vs **LC2609
       +0.350**. NNLS-fitted weight: LC2609 gets **1.7%** (down
       from TE-Li's 3.4% — opposite of expected if GFEX were right).
       Walk-forward RMSE under Truflation's *official* weights:
       LC2609 13.31 pts vs TE-Li 8.19 pts — GFEX is WORSE under
       official weights, not better. Conclusion: stop trying to
       find the "right" lithium source; the published 30.5% weight
       is structurally unrecoverable from any retail lithium data.
    2. **MCX India nickel tested, rejected.** 89 days of MCX nickel
       (INR-denominated, converted via `inr_usd.csv`). Forced into
       the regression as the sole nickel source: walk-forward RMSE
       **4.88 pts** vs **3.09 pts** for the TE-LME-via-NICK.L
       proxy. Strong evidence Truflation doesn't actually use MCX
       despite their marketing copy mentioning it.
    3. **Kitchen-sink NNLS (9 candidates: 3 lithium sources + 2
       nickel sources + the 4 unambiguous metals).** NNLS *zero'd
       out LC2609 entirely*, picked TE-Li + TE-Nickel as the
       best-fit pair, gave platinum 8.7% (Pa-Pt collinearity
       absorbing missing lithium signal). 47 obs / 9 params = ~5
       obs/param → solidly overfit, don't use as production
       weights. But the diagnostic is clear: among all retail
       sources we have, our current LITHIUM_TE + NICK.L proxies
       are NNLS's preferred picks.
- **FX conversion does NOT help anchor-ratio reconstruction.**
  Multiplicative anchored reconstruction (`V_t = V_anchor × Σ
  w_i × p_i_t/p_i_anchor`) is invariant to slow monotonic FX
  drift because the ratios cancel the constant unit conversion.
  Tested CNY→USD conversion of LC2609 and CNY: regression
  weights changed by <0.1pp. Lesson: when adding a new
  CNY-denominated source, the unit doesn't matter for the
  reconstruction, only the *daily-return profile* does.
- **The published 30.5% lithium weight is structurally
  unrecoverable.** Implied effective weight (from corr × σ-ratio):
  TE-Li ≈ 18%, LC2609 ≈ 11%. Both far from Truflation's 30.5%.
  Either: (a) Truflation smooths/lags lithium internally; (b)
  they use an inaccessible source (paid SMM feed, GFEX internal
  spot index); or (c) the methodology PDF doesn't match what they
  actually compute. We trade against the index they publish, not
  the methodology — so this is a feature, not a bug. **Don't
  re-investigate.** Three serious lithium candidates (LIT, TE,
  LC2609) plus two cobalt and two nickel candidates have all been
  empirically tested. Diminishing returns from further search.
- **GFEX product list** (full roster as of 2026): lithium
  carbonate (LC), industrial silicon (SI), polysilicon. **No
  palladium, no nickel, no cobalt, no copper.** If a future user
  hands you a "GFEX palladium" PDF, suspect it's actually
  polysilicon or a different exchange's product.
- **Weights**: `DEFAULT_WEIGHTS_LIVE` aliases `DEFAULT_WEIGHTS_Q1_2026`
  in `_truev_index.py`. Q1 2026 weights were **fitted via NNLS
  regression** against the operator-supplied `indexAndBasket.csv`
  (118 days of actuals + all 6 components, Jan 1 → Apr 28, 2026):
    - Cu  57.2%   (was 38.7% in stale Q4 hardcode)
    - Ni  21.9%   (was 12.3%)
    - Co   7.7%   (was  8.2%)
    - Pa   7.5%   (was  6.1%)
    - Li   4.9%   (was 33.5% — collapsed because no retail lithium
                 source we have access to matches Truflation's
                 actual lithium signal; see "source-mismatch
                 investigation" above. Empirically tested vs three
                 candidates incl. GFEX LC2609 — none recover the
                 30.5% Laspeyres weight Truflation publishes.)
    - Pt   0.8%   (was  1.2%; unstable due to Pa-Pt collinearity)
  In-sample fit RMSE = 4.46 pts (0.37%). Walk-forward (daily
  re-anchor, mirrors live bot) RMSE = 5.12 pts (0.43%). The old Q4
  weights had walk-forward RMSE = 8.70 pts (0.73%); proper Q1
  weights are a 41% improvement.
- **Calibration & overfit honesty**:
    - Bias ≈ 0.13 pts (essentially unbiased).
    - **Pa-Pt collinearity = 0.92** in component-price returns over
      the period → NNLS can't reliably split their 8.3% combined
      weight. Pt's bootstrap CoV is 87% — could really be 0% or 4%.
      Treat Pa+Pt combined (~8.3%) as the meaningful unit, not the
      individual splits. Doesn't bite in practice because Pa and
      Pt move together.
    - Cu and Ni weights are bootstrap-stable (CoV 2.6% and 7.9%).
    - Sample size 19.7 obs/param — comfortable but more would help.
    - **Don't fit on smaller samples.** A 9-candidate kitchen-sink
      NNLS on 47 days got walk-forward RMSE 2.95 pts (vs 5.12 on
      6 candidates × 118 days) but at 5.2 obs/param — solidly
      overfit. The 6-source × 118-day fit is the operational
      baseline.
- **σ_annual = 15.0%** — calibrated from log returns of the actual
  index over the full backtest period. Wire via `--truev-vol 0.15`.
- **Anchor discipline**: `DEFAULT_ANCHOR_PLACEHOLDER` in
  `_truev_index.py` MUST be (date, published_value, same-day component
  closes). Re-anchor each morning via `deploy/truev_reanchor.py` (now
  TE-aware: pulls TE lithium + cobalt spots in addition to yfinance
  closes for Cu/Ni/Pa/Pt). **Latent staleness pattern to watch**:
  TE-only commodities (Li, Co) have no historicals, so anchoring uses
  current spot as a proxy for yesterday's close. If TE has drifted
  between truflation's EOD print and your anchor refresh, the
  day-over-day signal for that metal gets zeroed. Mitigation: anchor
  as close to the EOD print as possible.
- **Backtest harnesses**:
    - `deploy/truev_backtest_csv.py` — walk-forward backtest against
      the operator's CSV. Computes realized σ, RMSE, worst days.
    - `deploy/truev_fit_weights.py` — NNLS weight-fitter (the script
      that produced the current `_Q1_2026_FITTED_RAW`).
    - `deploy/truev_reanchor.py` — daily anchor refresh ritual.
    - `deploy/truev_smoke.py` — quick sanity check vs Kalshi book.
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
- **Prices**: dollars as strings (`"0.4500"`) in responses, cents as integers in order creation (`yes_price: 45`). For sub-cent markets the adapter sends `yes_price_dollars: "0.477"` instead — the dollars-string field accepts 0.1¢ precision; falls back to integer cents on Kalshi 4xx.
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
| `lipmm/theo/providers/truev.py` | TruEVTheoProvider — KXTRUEV daily binaries |
| `lipmm/theo/providers/_truev_index.py` | Basket math + Q1 2026 fitted weights + anchor placeholder |
| `feeds/truflation/forward.py` | TruEvForwardSource — yfinance + TE polling |
| `feeds/tradingeconomics/spot.py` | TE scraper (cobalt + lithium spot) |
| `deploy/truev_backtest_csv.py` | CSV-driven walk-forward backtest |
| `deploy/truev_fit_weights.py` | NNLS weight fitter |
| `deploy/truev_reanchor.py` | Daily anchor refresh ritual |
| `prompts/build/PREMISE.md` | Canonical F4 strategic premise |
| `state/PROJECT_CONTEXT.md` | Soy-era state file |

## Module status

**lipmm framework (current, tested, deployable):**
- `lipmm/theo/` — TheoProvider Protocol + GBMCommodityProvider (soy)
  + TruEVTheoProvider (KXTRUEV daily binaries, NNLS-fitted Q1 2026
  weights, ~5 pt RMSE)
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
