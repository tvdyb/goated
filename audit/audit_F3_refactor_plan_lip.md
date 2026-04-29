# Audit F3 — Refactor plan, Liquidity Incentive Program edition

This file supersedes both `audit_F_refactor_plan.md` (F1) and
`audit_F2_refactor_plan_mm_program.md` (F2) for sequencing purposes.

- **F1** is the audit-aligned plan against the original Phase 02
  edge-driven framing.
- **F2** was the first re-scoping under "low-frequency MM-Program-bound"
  framing. F2 assumed a formal Kalshi Market Maker Agreement, which was
  the wrong program.
- **F3 (this file)** is the operative plan after researching Kalshi's
  actual incentive programs. The strategy targets the **Liquidity
  Incentive Program (LIP)**, not a formal MM Agreement. LIP is
  auto-enrolled for U.S. Kalshi members, has no application or formal
  contract, and pays out a pro-rata share of a daily reward pool based
  on continuous resting-liquidity scoring. The MM-Agreement scaffolding
  in F2 (ACT-MM2 application, ACT-MM4 designated-market policy,
  ACT-MM6 monthly reporting) is removed because none of it applies.

Read F3 first. F1/F2 stand as historical reference.

---

## 1. Strategic frame (the new spec)

**Business model.** Earn a pro-rata share of Kalshi's daily Liquidity
Incentive Program reward pool on `KXSOYBEANW` weekly bucket markets,
by maintaining continuous resting two-sided liquidity at or near the
inside of each bucket's order book, in sufficient size to contribute
to the per-market Target Size threshold. Spread capture net of adverse
selection is a secondary income stream that may be neutral or
slightly negative; the LIP pool share is the primary income.

**LIP scoring mechanics (concrete).**

```
Score(market, snapshot) = Σ_orders [order_size × distance_multiplier(order)]

distance_multiplier ∈ [0.0, 1.0]
  (1.0 at best bid/ask; decays toward 0 with distance from inside)

Only orders contributing to the Target Size threshold per side count.
Target Size: 100–20,000 contracts (per-market, set by Kalshi).

Snapshot cadence: every 1 second during trading hours.

Reward(period) = (Σ snapshots of OurScore / Σ snapshots of TotalScore)
                 × Pool(market, period)

Pool: $10–$1,000 per day per active market.
Reward period: up to 31 days, with active periods flagged on
  Kalshi market pages.
Min payout: $1.00; rounded down to nearest cent.
```

**Operating cadence (OD-31, formal).** Periodic-quoting service:

- Continuous resting liquidity at the inside (refresh on tick + at
  ≤30s heartbeat).
- Sub-second reflex on USDA / weather releases.
- Threshold-driven hedge fire rate ~1–3/day on CBOT ZS via IB.
- Provisioned for 5 trades/min peak (~100× observed actual).
- Synchronous main loop; `asyncio` only for I/O (Kalshi REST/WS, IB
  Gateway).
- Single-process layout, restart-on-crash, hourly state snapshot.

**Optimization target.** Maximise expected pool share:

```
expected_share = E[Σ snapshots of (OurScore / TotalScore)]
                 × Pool(market, period)
              − fees − hedge slippage − adverse-selection loss
              − capital cost
```

In practice this means: **be at the inside, with sufficient size,
on as many active-LIP-pool markets as feasible, with enough
adverse-selection protection that fills don't compound into
hedge-cost losses larger than pool share.**

**Hedging purpose.** Flatten residual delta on CBOT ZS via IB. Hedging
is risk-flattening, not edge-locking. Hedge cost is deducted from
LIP pool share, not from spread capture.

**Eligibility.** LIP is auto-enrolled for U.S. Kalshi members. No
application, no agreement, no qualification. Disqualifications:
Kalshi affiliates/employees, members with formal MM Agreements (we
do not have or want one), IB/FCM customers transacting via the IB/FCM.
Since we are direct Kalshi members trading our own account, we
qualify.

---

## 2. What changes from F2

**The objective function changes again.** F2 framed this as
"compliant fill volume under MM-Agreement obligations." Under LIP,
*there are no obligations*. The score is purely a function of (a)
how much resting size you keep at the inside and (b) how
continuously you do so. Your competitors' scores reduce your share
proportionally, so market selection (low-competition markets) is a
strategy lever.

**MM-Agreement-specific actions cut.** ACT-MM2 (formal application),
ACT-MM4 (designated-market policy), ACT-MM6 (monthly reporting) all
cut — the formal MM Agreement isn't the program we're using and
`KXSOYBEANW` isn't on Kalshi's published designated-product list
anyway.

**ACT-MM1 reframed.** What was a compliance monitor becomes a **LIP
Score Tracker** that continuously estimates our own snapshot score,
estimates total visible market score from public order-book data,
and projects expected pool share. Different mechanic, similar shape.

**Two new LIP-specific actions added.** ACT-LIP-POOL (pool-data
ingest) and ACT-LIP-VIAB (early viability check before committing
deep engineering).

**ACT-19 reframed structurally.** F2's "inventory-aware quoting"
optimised for spread capture under inventory risk. F3 replaces the
objective with **distance-multiplier-preserving inside quoting**:
the right quote is at-or-just-inside the current best bid/ask
(maximising distance multiplier), in sufficient size to clear the
Target Size threshold (maximising score contribution), with γ-skew
on inventory only when inventory passes a configurable threshold.
"Optimal spread" becomes "thinnest-justifiable spread that survives
adverse selection net of pool share" — a different math than the
A-S/CJ closed-form.

**ACT-32 reframed.** Pre-event widening *costs* LIP score (because
distance multiplier decays). The trade-off is now "widen enough to
avoid catastrophic adverse selection during USDA windows but not
so much you forfeit the pool for that window." Empirical
calibration target.

**Two new outstanding decisions added** about market selection and
target sizing under LIP. Several F2 decisions invalidated by the
LIP framing.

---

## 3. F3 action set (~33 actions, was 45 in F2 / 59 in F1)

### Wave 0 — LIP-ready quoting surface

The minimum to be a credible LIP participant on `KXSOYBEANW`: sign,
quote two-sided continuously at the inside, capture tape, kill
cleanly, attribute pool share. **Plus a viability check before
committing Wave 1** — confirm pool sizes and competition density are
favourable enough to justify the engineering investment.

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-01 | Forward-capture tape — Phase 1a (REST polling, M0-sufficient) + Phase 1b (WS forward-capture, M1+) | feature | XL | Unchanged from F1/F2 |
| ACT-02 | Soybean `commodities.yaml` fill-in | feature | S | Unchanged |
| ACT-03 | Kalshi REST client foundation (signing + rate limiter) | feature | XL | Unchanged |
| ACT-04 | Ticker schema + bucket grid + Event puller | feature | M | Unchanged |
| ACT-05 (R) | Kalshi WS — `user_orders` + `fill` + `orderbook_delta` (delta needed for competitor estimation) | feature | M | Re-expanded slightly from F2; we DO need orderbook deltas for Score tracking |
| ACT-06 | Order builder + types + tick rounding + `[$0.01,$0.99]` quote-band | feature | M | Unchanged |
| ACT-07 | 24/7 KXSOYBEANW calendar + Friday-holiday roll | feature | M | Unchanged |
| ACT-08 | CBOT settle resolver + roll + FND + reference-price-mode loader | feature | M | Unchanged |
| ACT-09 | Position store + per-Event signed exposure + max-loss accounting | feature | L | Unchanged |
| ACT-10 (R) | Kalshi taker/maker fee model + round-trip cost subtraction (LIP pool share posted by ACT-LIP-PNL, not here) | feature | M | Reduced — fee accounting is fee-only; LIP rewards posted by attribution layer |
| ACT-11 | Kill-switch primitives (DELETE batch + group trigger) | feature | M | Unchanged |
| ACT-12 (R) | Risk gates: aggregate book-delta cap + per-Event cap (no MM-Agreement quote-policy gate) | feature | M | Reduced: no formal compliance gate; just risk gates |
| ACT-13 | Bucket Yes-price vector via corridor decomposition adapter on existing GBM + sum-to-1 gate | refactor+feature | M | Unchanged |
| **ACT-LIP-POOL (NEW)** | **LIP pool data ingest: pull active LIP reward periods + pool sizes per `KXSOYBEANW` market from Kalshi market pages / regulatory notices feed; persist to DuckDB; refresh daily** | feature | M | Required to know what pool we're playing for in each market |
| **ACT-LIP-SCORE (NEW)** | **LIP Score Tracker: compute our own snapshot Score continuously (per market, per side, per snapshot); estimate visible competitor Score from public orderbook; project rolling expected pool share; emit telemetry to attribution layer** | feature | L | Replaces F2's ACT-MM1 with a different mechanic: scoring, not compliance |
| **ACT-LIP-VIAB (NEW)** | **Viability check: 2 weeks of LIP pool data on `KXSOYBEANW` + observed competition density + simulated our-share at full presence → go/no-go gate before committing Wave 1 engineering** | feature+analysis | M | The economic kill-criterion check. Cheap because it only needs ACT-01 Phase 1a + ACT-LIP-POOL + a notebook |

**Wave 0 total: 16 actions.** Ordering note: ACT-LIP-VIAB lands as the
**last item of Wave 0** and gates Wave 1 — if pool sizes are
insufficient or competition is too dense, the project pivots before
sinking weeks into Wave 1 RND work. This is a deliberate tripwire.

### Wave 1 — Structural correctness, LIP-aware

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-14 | `state/iv_surface.py` signature change to `(commodity, strike, expiry)` | refactor | L | Unchanged |
| ACT-15 | `TheoOutput` shape change: bid/ask + per-bucket Greeks | refactor | M | Unchanged |
| ACT-16 (R) | CME ingest: ZS L1 (Pyth-sufficient) + EOD options chain (low-cost vendor or CME direct) + put-call parity prune | feature | L | MBP/MBO and Databento cut |
| ACT-17 | BL + SVI + Figlewski + butterfly/calendar arb constraints + bucket integration + variance rescaling + co-terminal picker | feature+refactor | XL | Unchanged. Sync inline (OD-04 resolved) |
| ACT-18 | USDA event-clock + multi-zone holiday/session calendars | feature | L | Unchanged |
| **ACT-19 (R+)** | **Distance-multiplier-preserving inside quoting: post at-or-just-inside best bid/ask in sufficient size to clear Target Size threshold; γ-skew applied only when inventory exceeds configured threshold; widening only on event reflex** | feature | M (was L, was XL in F1) | Heavily reduced. Quote = clamp(fair_value ± min_spread_floor + inventory_skew + event_widening, [best_bid+ε, best_ask−ε]). No A-S/CJ optimal control, no GLFT closed-form |
| ACT-20 (R) | Hedge leg: aggregate book delta + ZS sizer + threshold trigger (3–5 ZS contracts) + IB Gateway + `ib_insync` + ZS L1 via Pyth | feature | L | IB confirmed; threshold widened; Pyth ZS L1 (no Databento) |
| ACT-21 | Settlement reconciler + Klear DCO + Rule 13.1(d) outcome poller + Rule 7.2 listener + bucket-grid lifecycle + lock-day | feature | L | Unchanged |
| ACT-22 | Order pipeline: REST endpoints + amend/decrease/batch + idempotency + queue-priority preservation | feature | M | Unchanged |
| ACT-23 | Reconciliation: 3x recon + DuckDB+Parquet + fill ingest + per-bucket markout (1m/5m/30m) | feature | L | Unchanged |
| ACT-24 (R) | Kill switch end-to-end: 4 triggers + windowed reconnect counter + scheduler wiring + structured logging + SanityError policy | feature+bugfix | M | Simpler — `structlog` to file + daily summary email |
| ACT-25 | Scenario harness (WASDE-day, weather-shock, expiry-day, lock-day, CBOT-closed regime) | feature | L | Unchanged |
| ACT-26 | Backtest M0 pipeline + paper-trading + DuckDB substrate + Milestone-0 historical scoring | feature | XL | Unchanged. M0 success criterion now: our LIP-policy quoter, simulated against captured data, produces positive expected pool-share net of fees/hedge |
| **ACT-LIP-PNL (NEW)** | **LIP-aware P&L attribution: pool share earned / spread P&L (often near-zero) / hedge slippage / fees / adverse-selection loss / capital cost — daily, weekly, per-market** | feature | M | Replaces F2's ACT-MM3 with the LIP-pool-share metric in place of formal-rebate metric |

**Wave 1 total: 13 actions.**

### Wave 2 — Quoting refinements aligned to score optimization

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-27 (R) | Heston SV kernel (drop Bates SVJ, drop Merton JD, drop Student-t at first iteration) | feature | L | One SV variant; Bates/JD only if Heston empirically underprices tail buckets |
| ACT-29 (R) | Hedge-leg basis tracker (`state/basis_hedge.py`) + Kalshi cash-collateral utilisation | feature | M | Vertical-spread option hedge cut to nice-to-have |
| **ACT-32 (R+)** | **Pre-event widening trade-off: widen enough to avoid catastrophic adverse selection during USDA windows but not so much you forfeit the pool for that window. Empirical calibration target.** | feature | M | Reframed objective: not "model variance widening" but "score-optimal widening" |
| ACT-33 | Measure overlay: fav/longshot + Kalshi-vs-RN parametric shrinkage | feature | M | Unchanged |
| ACT-37 | Limit-day censorship correction (CBOT 7% lock) | bugfix+feature | M | Unchanged |
| ACT-35 (R) | Wash-trade prevention + STP modes | feature | S | Reduced |
| **ACT-LIP-COMPETITOR (NEW)** | **Competitor presence estimator: from `orderbook_delta` history, attribute resting size at each level to non-self participants; estimate their Score contribution; flag when our share of total score drops below configured threshold** | feature | M | Drives market-selection policy and quote-tightening decisions |

**Wave 2 total: 7 actions** (was 7 in F2; net 0, but ACT-MM4 cut and
ACT-LIP-COMPETITOR added).

### Wave 3 — Capacity (more LIP-eligible markets)

Strategy: with LIP, every additional market is an additional pool to
share in. Capacity expansion is direct economic upside, capped only
by capital and operational complexity.

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| **ACT-LIP-MULTI (NEW)** | **Multi-market LIP extension: parametrize the full stack to operate on multiple `KX*` Event families concurrently. Priority: other commodity weeklies (ZC corn, ZW wheat) first, then macro tickers (`KXCPI`, `KXFED`) if pools justify, then deferred** | refactor+feature | L | Replaces F2's ACT-MM5. Priority within this action is governed by ACT-LIP-POOL data |
| ACT-41 | USDA REST ingest (NASS Quick Stats + FAS GAIN minimum) | feature | M | Reduced to event-clock-relevant feeds |
| ACT-32-EXT | Stocks-to-use regime classifier as input to event widening | feature | M | Folds C10-44/45/46 into pre-event widening |

**Wave 3 total: 3 actions** (was 4 in F2; FX cut).

### Wave 4 — Operational hardening

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-50 (R) | Structured logging + daily P&L+pool-share+score summary email | feature | S | Heavily reduced; no Prometheus/Grafana |
| ACT-52 (R) | Inline calibration loop (5-min cadence, runs in main process) + simple param-version registry | feature | M | Heavily reduced |
| ACT-53 (R) | Backtest realism: PIT for USDA + capacity / turnover penaliser + survivorship + monthly attribution | feature | L | Reduced |
| ACT-54 | Pyth hardening: per-stream latency probe + redundancy + num_publishers fail-loud + backfill on reconnect | bugfix+feature | M | Unchanged |
| **ACT-LIP-RECON (NEW)** | **Reconcile LIP rewards posted by Kalshi against our own ACT-LIP-SCORE projections; flag delta beyond tolerance** | feature | S | When Kalshi disburses LIP rewards (cadence TBD — likely weekly or per-period), reconcile against our model. Replaces F2's ACT-MM6 |

**Wave 4 total: 5 actions.**

**F3 grand total: 44 actions** (vs. 45 in F2 / 59 in F1; very small
headcount change vs. F2 because the MM-specific actions are roughly
1:1 swapped for LIP-specific actions, but the *content* and *effort*
of those actions is meaningfully different).

---

## 4. Cuts from F2 to F3

| F2 ID | Description | Reason |
|---|---|---|
| ACT-MM2 | MM Agreement application + PAL acquisition | Wrong program; LIP requires no application |
| ACT-MM4 | Designated-market quoting policy | LIP has no designated markets; we choose where to participate |
| ACT-MM6 | Monthly MM-Agreement reporting | LIP has no formal reporting; rewards are computed by Kalshi automatically |
| ACT-44 | FX cross-asset feeds | Only relevant if we MM in FX-sensitive `KX*` products; deferred behind ACT-LIP-POOL data |

**Adds from F2 to F3:**

- ACT-LIP-POOL (Wave 0) — pool data ingest
- ACT-LIP-SCORE (Wave 0) — score tracker (replaces ACT-MM1 with different mechanic)
- ACT-LIP-VIAB (Wave 0) — early viability check (NEW gating concept)
- ACT-LIP-COMPETITOR (Wave 2) — competitor presence estimator (NEW)
- ACT-LIP-RECON (Wave 4) — pool-reward reconciliation (replaces ACT-MM6)
- ACT-LIP-MULTI (Wave 3) — multi-market LIP extension (replaces ACT-MM5)
- ACT-LIP-PNL (Wave 1) — LIP P&L attribution (replaces ACT-MM3)

Net change F2 → F3: −4 cuts, +7 adds (with three of those adds being
1:1 replacements). Effort decrease meaningful because ACT-MM2 was
calendar-XL (months of legal/ops) and is gone.

---

## 5. New work introduced by F3 (the LIP surface)

**ACT-LIP-POOL.** Kalshi publishes active LIP reward periods per
market. We need a service that polls these (likely via the same
public Kalshi endpoints used by ACT-01 Phase 1a, possibly with light
HTML parsing if pool data is only on the market UI page) and
persists pool sizes plus active-period dates per market. Refreshes
daily. Lives in `feeds/kalshi/lip_pool.py`. Without this we don't
know what we're playing for.

**ACT-LIP-SCORE.** The runtime score tracker. For each `KXSOYBEANW`
market we participate in, every second:

```
our_score(market, t) = Σ orders_in_book(self, market, t)
                       [order.size × dist_mult(order, best_bid_ask(t))]
visible_total_score(market, t) = same sum over all visible orders
projected_share(market, period) = mean over snapshots
                                  [our_score / visible_total_score]
projected_reward(market, period) = projected_share × pool(market, period)
```

The distance multiplier curve is not publicly disclosed beyond "1.0
at best bid/ask, decays toward 0." We will calibrate empirically by
posting at varying distances from inside and observing realised
reward share, OR by direct Kalshi-support inquiry (cheap; do this).

**ACT-LIP-VIAB.** Before committing engineering to Waves 1+ we run a
two-week observation: ACT-01 Phase 1a + ACT-LIP-POOL on production
Kalshi data, computing what our share *would have been* under
several quoting policies, against the actually-observed pool sizes
and competition density. Outputs:

- Total LIP pool across all live `KXSOYBEANW` markets per day.
- Number of distinct other participants visible.
- Estimated our share at "full presence" (continuous resting at
  inside, sufficient size).
- Projected daily / weekly / monthly pool-share revenue net of fees
  and a placeholder hedge cost.

**Go/no-go gate.** If projected revenue is below an opportunity-cost
threshold (suggested: $50/day net of fees, ~$15k/yr — well below the
$500/mo target infrastructure cost mentioned in cartography), the
project pivots: either to a different `KX*` market family with
larger pools, or to the F1 edge-driven framing if RND quality is
demonstrably differentiated (M0 test). This is cheap to run; expensive
not to.

**ACT-LIP-COMPETITOR.** Builds on the Score Tracker. Attributes resting
size at each level to non-self participants by subtracting our own
known orders from observed orderbook deltas. Estimates competitor
Score and our share of total. Drives two policies: (a) market
selection (pull out of markets where we're <X% of total score), (b)
quote-tightening (if a competitor quotes inside us, we have to match
or fall to lower distance multiplier).

**ACT-LIP-PNL.** The economic dashboard, parameterised for LIP. Daily
breakdown: pool share earned / spread P&L (often near-zero, flagged
when meaningfully negative) / hedge slippage / fees / adverse-selection
loss / capital cost. Per-market and aggregate. Lives in
`attribution/lip.py`.

**ACT-LIP-RECON.** When Kalshi disburses LIP rewards (likely weekly or
end-of-period), reconcile actual disbursement against ACT-LIP-SCORE's
projection. Large deltas flag either a model bug (distance multiplier
miscalibrated) or a data bug (we missed visibility on a competitor).

**ACT-LIP-MULTI.** Once the single-product `KXSOYBEANW` operation is
profitable, extending to other `KX*` products is mostly a config and
universe-shape change. Bucket grids, RND pipelines, hedge instruments
all parametrise per product family. Priority within this action is
data-driven by ACT-LIP-POOL: largest-pool, lowest-competition markets
get added first.

---

## 6. Outstanding decisions, F3 update

**Resolved by F3 framing:**

- OD-04 (sync vs async density refresh) → sync, inline. Resolved.
- OD-06/OD-20 (Pyth vs Databento for ZS) → Pyth + low-cost CME chain
  vendor. Resolved.
- OD-15 (Kalshi rate-limit tier) → Standard sufficient. Resolved.
- OD-25 (kill-switch N, K thresholds) → defer to first month of paper
  trade. Posture-resolved.
- OD-29 (Σᵢⱼ estimator) → moot (matrix skew cut). Invalidated.
- OD-30 (practitioner corpus) → moot (signal alpha cut). Invalidated.
- OD-32 (MM Agreement scope) → **invalidated; we're on LIP not formal
  MM.**
- OD-33 (rebate schedule) → **invalidated; LIP terms are public and
  pool-based.**
- OD-34 (designated-market list) → **invalidated; LIP has no
  designated markets.**

**New under F3:**

- **OD-32′ — Market-selection policy.** Which `KXSOYBEANW` markets to
  participate in? All active-pool markets, top-N by pool size, or
  competition-ranked? Default: top-by-pool-net-of-competition, with a
  minimum-pool floor.
- **OD-33′ — Target-size posting policy.** Post just-above-Target-Size
  threshold for capital efficiency, or substantially above for
  competition deterrence? Default: 1.5× threshold, revisit after
  ACT-LIP-VIAB.
- **OD-34′ — Distance-multiplier calibration source.** Empirical
  (post-and-observe) or direct Kalshi-support inquiry? Default: ask
  Kalshi support first (cheap, fast); fall back to empirical
  calibration if undisclosed.
- **OD-36 — Event-window policy under LIP.** During USDA windows,
  widen (lose score) or stay tight (risk adverse selection)? Default:
  stay tight on majority buckets, widen on tail buckets where
  adverse-selection loss could exceed pool share. Empirical
  calibration target.

**Still open from F1/F2:**

- OD-13 (recon cadence) — scheduler in-process / cron EOD.
- OD-19 (fee table location) — `fees/` package.
- OD-21 (survivorship) — forward-only with per-trade-print
  augmentation.
- OD-22 (USDA look-ahead) — PIT.
- OD-24 (measure-overlay form) — parametric monotone in midprice.
- OD-26 (vol_adjustment semantics) — both κ-width and κ-spread.
- OD-27 (SanityError fan-out) — `quote_drop` default; consecutive →
  `market_suspend`.
- OD-28 (`buy_max_cost` enforcement) — client wrapper for per-request,
  risk layer for per-Event sum.
- OD-35 (capital deployment Kalshi vs CBOT) — default 70/30, revisit
  after ACT-LIP-VIAB.

---

## 7. Updated kill criteria

The five MM-Agreement-specific kill criteria (KC-MM-01 through
KC-MM-05) are replaced by LIP-specific ones. C10-KC-01 through 07 and
the audit-derived KC-AUD-01 through 09 still apply where relevant.

- **KC-LIP-01 — Pool sizes too small.** Observed daily LIP pool across
  all live `KXSOYBEANW` markets, summed, is below $50/day for four
  consecutive weeks during active reward periods. The product family
  doesn't host enough incentive to fund the operation.
- **KC-LIP-02 — Competition too dense.** Our projected pool share at
  full presence (continuous resting at inside, sufficient size) is
  below 5% across `KXSOYBEANW` for two consecutive reward periods.
  We are systematically out-competed; market-selection pivot or
  product-family pivot required.
- **KC-LIP-03 — Distance-multiplier curve too aggressive.** Empirical
  calibration shows being 1¢ off the inside drops score by >50%. With
  $0.01 tick size and a $0.20 No-Cancellation Range, this means
  near-zero tolerance for being undercut, which combined with KC-LIP-02
  is fatal.
- **KC-LIP-04 — Adverse selection on inside-quoting exceeds pool
  share.** Realised markout on filled quotes (averaged weekly) exceeds
  per-market pool share for four consecutive Events. The RND model
  isn't accurate enough to support inside-quoting.
- **KC-LIP-05 — Hedge cost exceeds pool share.** Monthly hedge slippage
  + IB commissions + CME fees exceed monthly pool-share income. Hedge
  strategy or threshold needs to widen, or product family needs to be
  one with cheaper hedge instrument.
- **KC-LIP-06 — LIP program ended or terms changed unfavourably.**
  Kalshi terminates LIP at program end (Sep 1, 2026) without renewal,
  or modifies pool sizes / scoring formula unfavourably mid-stream.
  Triggers a re-evaluation of whether a non-LIP edge-driven strategy
  (F1 framing) is viable, or whether we exit.

The original C10-KC and KC-AUD remain except KC-AUD-08 (latency budget
unachievable) which stays invalidated, and KC-MM-01 through KC-MM-05
which are moot under F3.

---

## 8. Summary

F3 swaps F2's MM-Agreement framing for the actually-applicable
Liquidity Incentive Program framing. Six F2 actions (ACT-MM1, ACT-MM2,
ACT-MM3, ACT-MM4, ACT-MM5, ACT-MM6) are replaced by seven LIP-specific
actions (ACT-LIP-POOL, ACT-LIP-SCORE, ACT-LIP-VIAB, ACT-LIP-COMPETITOR,
ACT-LIP-PNL, ACT-LIP-RECON, ACT-LIP-MULTI). The shape is similar but
the content is materially different — pool-share scoring instead of
contractual compliance, no application or formal agreement, no
designated-market list, no monthly reporting.

The biggest practical changes:

1. **No application work.** ACT-MM2's calendar-XL legal/ops effort
   (months) collapses entirely. Engineering can wire on to production
   the moment the code is ready.
2. **A new viability gate at the end of Wave 0.** ACT-LIP-VIAB. Two
   weeks of pool data + competition observation + simulated quoting
   policy answers "is this worth Wave 1?" Cheap to run, prevents
   sinking weeks into engineering against an unprofitable economic
   structure.
3. **A new objective function in the quoter.** ACT-19 reframed:
   distance-multiplier-preserving inside quoting, not A-S/CJ optimal
   control. Substantially less complex code, materially different
   behaviour.
4. **The 30-second baseline cadence becomes more aggressive.** Under
   LIP, every second you're not on the wire is a missed snapshot.
   Quote refresh on tick + heartbeat at ≤30s; aim for sub-second
   recovery on disconnect.

F3 should be read as superseding F1 and F2. F2 stays as historical
reference for the MM-Agreement framing in case Kalshi later opens that
program for `KXSOYBEANW` and we want to switch. F1 stays as the
edge-driven upper bound in case LIP is terminated and we need to
pivot.

*End of `audit_F3_refactor_plan_lip.md`.*
