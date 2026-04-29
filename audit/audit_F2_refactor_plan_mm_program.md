# Audit F2 — Refactor plan, low-frequency MM-Program edition

This file supersedes `audit_F_refactor_plan.md` for sequencing purposes.
F1 stands as the audit-aligned plan against the original Phase 02
edge-driven framing; F2 is the plan under the **operating posture
clarified 2026-04-27**: low frequency, rebate-driven, MM-Program-bound.
F1 should be read as the upper bound of work; F2 is what we actually
execute.

---

## 1. Strategic frame (the new spec)

**Business model.** Quote tight two-sided markets on Kalshi
`KXSOYBEANW` (and likely other `KX*` commodity products over time),
**under a Kalshi Market Maker Agreement**, in order to earn per-fill
liquidity rebates and/or fee waivers. Spread capture net of adverse
selection is *secondary* income, not primary; on a rebate-driven book,
gross spread P&L can be near-zero or slightly negative and the strategy
is still profitable.

**Operating cadence (OD-31, formal).** Periodic-quoting service:

- 30-second baseline reprice cadence.
- Sub-second reflex on USDA / weather / Kalshi-event releases.
- Threshold-driven hedge fire rate ~1–3/day.
- Provisioned for 5 trades/min peak across the strip (~100× observed
  actual rate of 2–3 trades/bucket/day).
- Synchronous main loop; `asyncio` only for I/O (Kalshi REST/WS, IB
  Gateway).
- Single-process layout, restart-on-crash, hourly state snapshot.
- No microsecond budgets, no FIX, no MBP/MBO, no hot-standby topology.

**Optimization target.** Maximise compliant fill volume (rebate
revenue) subject to: MM Agreement obligations (uptime, spread cap,
minimum size, two-sided quoting), inventory bound, capital cap, and
delta-neutral hedge. *Not* the A-S spread-capture-vs-inventory tradeoff.

**Hedging purpose.** Flatten residual delta from Kalshi accumulation
on CBOT ZS via Interactive Brokers. Hedging is risk-flattening, not
edge-locking. Hedge cost is a deductible against rebate income, not a
profit center.

---

## 2. What changes from F1

**The objective function changes.** A-S/CJ optimal-control framing is
the wrong frame. The right frame is closer to *constrained-optimization
of fill volume*: be on the wire, inside the MM-Agreement spread cap,
with at least the minimum size, on both sides, for at least the uptime
SLA, with hedge slippage low enough that rebate revenue dominates net
cost. GLFT closed-form spread, queue-reactive overlays, microstructure
modelling — all wrong objective.

**Latency budgets evaporate.** README's 50 µs / 60 ms targets are
HFT carryover. Replace with seconds.

**Microstructure work cuts.** ACT-30 (Glosten-Milgrom / Kyle / OFI),
ACT-34 (queue-reactive + trade-through probability), ACT-141, MBP/MBO
in ACT-16 — all cut. C10-KC-06 (queue-position edge irrelevant at
sub-50-deep books) is empirically true on `KXSOYBEANW`; queue-aware
quoting solves a problem you don't have.

**Vendor cost drops.** OD-06/OD-20 (Databento for ZS) collapses to
"Pyth Hermes for ZS L1 is sufficient." CME options chain via daily
REST/SFTP pull from CME or a low-cost vendor (~$50–100/mo) instead of
Databento. Total vendor savings: $200–500/mo.

**MM Program surface adds.** A whole layer the F1 plan did not have:
uptime tracker, spread-cap compliance monitor, minimum-size compliance,
two-sided-quoting enforcer, designated-market policy, rebate accountant,
monthly-reporting pipeline. Roughly five to seven new actions.

**One audit error to flag.** `GAP-094` (Rule 5.16 PAL / MM-program-
designation flag) was scored `minor / S effort` in the register
because the original audit framed the strategy as edge-driven, where
PAL would have been a nice-to-have scaling factor. Under F2 framing
**PAL is a foundational legal dependency** that gates the entire
business model. Severity should read `blocker / S effort (legal +
config) but XL effort (operationally, gating)`. Treated as such in F2.

---

## 3. What stays from F1

Most of the foundational engineering. Specifically:

- **The Kalshi client surface** — ACT-03/04/05/06/22 still ship as
  planned (with ACT-05 reduced — see §5).
- **The position store + risk gates** — ACT-09/12 unchanged.
- **The kill switch** — ACT-11/24 unchanged. Kill triggers are
  *more* important under MM Agreement because uncontrolled losses on
  a rebate-driven book vaporize months of rebate income in an hour.
- **The RND pipeline** — ACT-14/16 (reduced)/17. You still need to
  price each bucket reasonably even when rebates are the primary
  income, because being systematically wrong-priced means being
  systematically picked off, and adverse-selection losses can
  exceed rebate income. The RND just doesn't need to be *better*
  than Kalshi's quote, it needs to be *not catastrophically wrong*.
- **Hedge leg** — ACT-15 (Greeks)/20 (IB + ZS L1 + threshold-driven).
  Threshold widens (single ZS contract → 3–5 contracts) because
  hedging too aggressively at low fill rate is itself a slippage cost.
- **Settlement & reconciliation** — ACT-21/23 unchanged.
- **Forward-capture** — ACT-01 (both phases) unchanged.
- **Scenario harness** — ACT-25 unchanged.
- **Backtest M0 pipeline** — ACT-26 unchanged.
- **Event-window pricing** — ACT-18/32/47 *more* important because
  pre-event widening is what protects rebate income from getting
  vaporized in a 3-σ USDA gap.

---

## 4. F2 action set (~32 actions, was 59)

Five waves, more compact, MM-Program-aware. New actions are tagged
`NEW`; reduced-scope reuses of F1 actions keep their original ID with
`(R)`; cuts are listed separately in §6.

### Wave 0 — MM-Program-ready quoting surface

The minimum to be a credible MM-Program applicant: sign, quote
two-sided inside a configurable spread cap and minimum size, capture
tape, kill cleanly, account for rebates separately from fees.

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-01 | Forward-capture tape — Phase 1a (REST polling, M0-sufficient) + Phase 1b (WS forward-capture, M1+) | feature | XL | Unchanged from F1 amendment |
| ACT-02 | Soybean `commodities.yaml` fill-in | feature | S | Unchanged |
| ACT-03 | Kalshi REST client foundation (signing + rate limiter) | feature | XL | Unchanged |
| ACT-04 | Ticker schema + bucket grid + Event puller | feature | M | Unchanged |
| ACT-05 (R) | Kalshi WS — `user_orders` + `fill` only (no `orderbook_delta`/`ticker`/`trade` multiplex) | feature | M (was L) | Reduced to fill-listener; orderbook tracked via REST polling |
| ACT-06 | Order builder + types + tick rounding + `[$0.01,$0.99]` quote-band | feature | M | Unchanged |
| ACT-07 | 24/7 KXSOYBEANW calendar + Friday-holiday roll | feature | M | Unchanged |
| ACT-08 | CBOT settle resolver + roll + FND + reference-price-mode loader | feature | M | Unchanged |
| ACT-09 | Position store + per-Event signed exposure + max-loss accounting | feature | L | Unchanged |
| ACT-10 (R) | Kalshi taker/maker fee model + **rebate accounting (NEW input)** + round-trip cost | feature | M | Adds per-fill rebate posting alongside fee posting |
| ACT-11 | Kill-switch primitives (DELETE batch + group trigger) | feature | M | Unchanged |
| ACT-12 (R) | Risk gates: aggregate book-delta cap + per-Event cap + **MM-Agreement quote-policy gate (NEW)** | feature | L | Replaces the M2-quoter contract from F1 with the MM-Program quote contract: configurable spread cap, min size, two-sided enforcement, designated-market list |
| ACT-13 | Bucket Yes-price vector via corridor decomposition adapter on existing GBM + sum-to-1 gate | refactor+feature | M | Unchanged |
| **ACT-MM1 (NEW)** | **MM-Program compliance monitor: uptime tracker per market, spread-cap monitor, minimum-size monitor, two-sided-quoting tracker, near-breach alerter** | feature | M | **New action, no F1 equivalent.** Lives in `compliance/`. Drives quoter behavior at runtime; emits monthly-reporting events. |
| **ACT-MM2 (NEW)** | **MM-Agreement application + PAL acquisition (legal/ops, gates production wire-on)** | non-engineering | XL (calendar) | **New action.** Folds in `GAP-094` (Rule 5.16 PAL) reframed from minor to blocker. Submit application, negotiate terms, sign agreement. Engineers don't do this work but engineering depends on it. |

**Wave 0 total: 15 actions** (vs. 13 in F1; net +2 because ACT-MM1 and
ACT-MM2 are added even though some reductions land here).

### Wave 1 — Structural correctness, low-frequency edition

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-14 | `state/iv_surface.py` signature change to `(commodity, strike, expiry)` | refactor | L | Unchanged |
| ACT-15 | `TheoOutput` shape change: bid/ask + per-bucket Greeks | refactor | M | Unchanged |
| ACT-16 (R) | CME ingest: ZS L1 (Pyth-sufficient) + EOD options chain (low-cost vendor or CME direct) + put-call parity prune | feature | L (was XL) | MBP/MBO and MDP 3.0 / Databento components cut |
| ACT-17 | BL + SVI + Figlewski + butterfly/calendar arb constraints + bucket integration + variance rescaling + co-terminal picker | feature+refactor | XL | Unchanged. Now runs synchronous inline (OD-04 resolves to sync) |
| ACT-18 | USDA event-clock + multi-zone holiday/session calendars | feature | L | Unchanged |
| ACT-19 (R) | Inventory-aware quoting: reservation price `r = S − γσ²(T−t)q` + hard inventory bound `q ∈ [−Q,+Q]` + γ-skew on quote midprice | feature | L (was XL) | **GLFT closed-form spread cut. Practitioner truncating layer kept (as risk gate, in ACT-12). A-S/CJ "control loop" framing dropped — quote = fair value ± (configured spread floor + γ·skew + event widening). Spread floor comes from MM-Agreement obligation, not optimization.** |
| ACT-20 (R) | Hedge leg: aggregate book delta + ZS sizer + threshold trigger (3–5 ZS contracts, not 1) + IB Gateway + `ib_insync` client + ZS L1 via Pyth | feature | L (was XL) | FCM = IB confirmed; CME L1 via Pyth (no separate Databento feed); threshold widened |
| ACT-21 | Settlement reconciler + Klear DCO + Rule 13.1(d) outcome poller + Rule 7.2 listener + bucket-grid lifecycle + lock-day | feature | L | Unchanged |
| ACT-22 | Order pipeline: REST endpoints + amend/decrease/batch + idempotency + queue-priority preservation | feature | M | `state/book.py` queue-position cache cut (queue position not load-bearing at low frequency) |
| ACT-23 | Reconciliation: 3x recon + DuckDB+Parquet + fill ingest + per-bucket markout (1m/5m/30m) | feature | L | Unchanged |
| ACT-24 (R) | Kill switch end-to-end: 4 triggers + windowed reconnect counter + scheduler wiring + structured logging + SanityError policy | feature+bugfix | M (was L) | Simpler because no Prometheus/Grafana stack to wire into; `structlog` to file + daily summary email |
| ACT-25 | Scenario harness (WASDE-day, weather-shock, expiry-day, lock-day, CBOT-closed regime) | feature | L | Unchanged |
| ACT-26 | Backtest M0 pipeline + paper-trading + DuckDB substrate + Milestone-0 historical scoring | feature | XL | Unchanged |
| **ACT-MM3 (NEW)** | **Rebate-aware P&L attribution: rebate income / spread P&L / hedge slippage / fees / adverse-selection loss / capital cost — daily and monthly** | feature | M | **New action.** Lives in `attribution/`. The economic dashboard for an MM-Agreement business |

**Wave 1 total: 14 actions** (vs. 13 in F1; net +1 from ACT-MM3).

### Wave 2 — Quoting refinements aligned to rebate optimization

Much smaller than F1's Wave 2. Most pricing-quality work either stays
foundational (already in W1) or cuts (microstructure, queue-reactive).

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-27 (R) | Heston SV kernel (drop Bates SVJ, drop Merton JD, drop Student-t at first iteration) | feature | L (was XL) | One SV variant covers the soybean weather-shock case; Bates/JD added later only if Heston empirically underprices tail buckets |
| ACT-29 (R) | Hedge-leg basis tracker (`state/basis_hedge.py`) + Kalshi cash-collateral utilisation | feature | M (was L) | Vertical-spread option hedge cut from Wave 2 (becomes Wave 4 nice-to-have); SPAN margin model deferred to Wave 4 |
| ACT-32 | Pre-event widening: SVI widening / κ-multipliers / edge-proximity widener | feature | M | Unchanged. **More important under F2** because pre-event compliance breaches (spread cap blowing out around USDA) are MM-Agreement-relevant |
| ACT-33 | Measure overlay: fav/longshot + Kalshi-vs-RN parametric shrinkage | feature | M | Unchanged |
| ACT-37 | Limit-day censorship correction (CBOT 7% lock) | bugfix+feature | M | Unchanged |
| ACT-35 (R) | Wash-trade prevention + STP modes (NCR window deferred to Wave 4; RFQ deferred or cut) | feature | S (was M) | Reduced |
| **ACT-MM4 (NEW)** | **Designated-market quoting policy: enforce two-sided quote presence in MM-designated markets, even when uneconomic, with policy override on extreme conditions** | feature | M | **New action.** Required by most MM Agreements; not in F1 because F1 framing assumed always-economic quoting |

**Wave 2 total: 7 actions** (vs. 12 in F1; net −5 because microstructure
/ matrix-skew / alpha-overlays / SABR-BP / per-trade-indicators / member-
role / GLFT-spread-residuals all cut or deferred).

### Wave 3 — Capacity and resilience (was: signals & strategy)

The original Wave 3 was 11 actions of additive alpha (weather, COT,
soybean complex, TSMOM, etc.). Under F2 framing, alpha is largely
irrelevant — rebate is the alpha. What you actually need in this
position is **more rebate-eligible markets to MM in** (capacity) and
**better hedging in non-ZS commodity markets** if/when MM extends to
other Kalshi `KX*` products.

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-41 | USDA REST ingest (NASS Quick Stats + FAS GAIN minimum) | feature | M (was L) | Reduced to event-clock-relevant feeds only |
| ACT-44 | FX (DXY + USD/BRL minimum) — only if MM extends to FX-sensitive Kalshi products | feature | M (was L) | Reduced |
| **ACT-MM5 (NEW)** | **Multi-product MM extension: parametrize the full stack to operate on >1 Kalshi `KX*` Event family in parallel (capacity, not just ZS)** | refactor+feature | L | **New action.** Universe-shape upgrade focused on additional rebate-eligible markets, not signal alpha |
| ACT-32 expansion | Stocks-to-use regime classifier as input to event widening | feature | M | Folds C10-44/45/46 (Phase 10 stocks-to-use gate) into pre-event widening rather than as standalone signal |
| ACT-CME-EOD | CBOT EOD settlement pull (Rule 813) — already in ACT-08 dep, formalize standalone if not | feature | S | May already be subsumed |

**Wave 3 total: 4 actions** (vs. 11 in F1; net −7 because crush-spread,
calendar-spread, bean-corn, TSMOM, carry, cross-sectional momentum,
COT signals, weather-strategy signals, satellite, SAm fundamentals,
logistics, cash-bids, oilshare/RFS — all cut as irrelevant to a
rebate-driven book).

### Wave 4 — Operational hardening for MM-Agreement reporting

| ID | Summary | Type | Effort | Notes |
|---|---|---|---|---|
| ACT-50 (R) | Structured logging + daily P&L+rebate+compliance summary email — no Prometheus, no Grafana, no PagerDuty | feature | S (was L) | Heavily reduced |
| ACT-52 (R) | Inline calibration loop (5-min cadence, runs in main process) + simple param-version registry | feature | M | Heavily reduced from F1 nightly-job framework |
| ACT-53 (R) | Backtest realism: PIT for USDA + capacity / turnover penaliser + survivorship + monthly P&L attribution | feature | L (was XL) | P&L attribution moved up to ACT-MM3 in Wave 1; this is the backtest-side realism only |
| ACT-54 | Pyth hardening: per-stream latency probe + redundancy + num_publishers fail-loud + backfill on reconnect | bugfix+feature | M | Unchanged |
| **ACT-MM6 (NEW)** | **Monthly MM-Agreement reporting pipeline: uptime per market, spread-cap breach counts, min-size breach counts, designated-market presence percent, position-flat-by-EOD compliance** | feature | M | **New action.** The reporting-side counterpart to ACT-MM1's runtime monitor |

**Wave 4 total: 5 actions** (vs. 10 in F1; net −5 from cuts to FIX,
hot-standby, full Prometheus/Grafana/PagerDuty, forward-curve
enrichments, cross-asset hedge selection, Kalshi residuals, PIN/VPIN,
operational extras).

**F2 grand total: 45 actions** (vs. 59 in F1; net −14, ~24% reduction
in scope; critical-path effort reduction is larger because the cuts
concentrate in the XL-tier microstructure / topology / FIX / queue-
reactive work).

---

## 5. Cuts from F1, full list (with reason)

| F1 ID | Description | Reason for cut under F2 |
|---|---|---|
| ACT-28 | Per-bucket A-S matrix skew + Σᵢⱼ + multi-asset HJB | Wrong objective function under rebate-driven economics; cross-bucket optimization gain is small relative to MM-rebate income |
| ACT-30 | Microstructure (Glosten-Milgrom + Kyle + OFI) + MBP/MBO | Trade rate too low to drive Bayes update; depth not available; queue irrelevant |
| ACT-31 | Alpha-drift overlays (CJR alpha + CW skew + mean-reverting drift) | Not load-bearing when rebate is the alpha |
| ACT-34 | USDA pull-refit + trade-through probability + queue-reactive overlay | Pull-refit kept implicitly via ACT-32 event widening; trade-through probability + queue-reactive cut |
| ACT-36 | SABR + Bliss-Panigirtzoglou fallbacks | SVI sufficient for soy weeklies; alternative density fitters deferred to nice-to-have |
| ACT-38 | Member/role/DMM concept + FCM pre-trade-risk hook + Rule 5.16 PAL flag | Subsumed by ACT-MM1/ACT-MM2; PAL is now a Wave-0 blocker, not a Wave-2 minor |
| ACT-39 | NWP weather + satellite + soil-moisture ingest stack | Alpha layer; cut |
| ACT-40 | SAm + GACC + China + logistics ingest | Alpha layer; cut |
| ACT-42 | COT + Goldman-roll + index-roll signals | Alpha layer; cut |
| ACT-43 | Cash bids + DTN + cash-basis fair-value + farmer-hedge prior | Alpha layer; cut |
| ACT-45 | Soybean complex universe (crush + calendar + bean/corn) | Alpha layer; cut. Capacity expansion handled by ACT-MM5 instead |
| ACT-46 | Trend / cross-section (TSMOM + carry + momentum) | Alpha layer; cut |
| ACT-47 | Event-driven signals (tape-event + WASDE fade + ENSO + harvest-fade) | Most cut; stocks-to-use regime gate kept under ACT-32 expansion |
| ACT-48 | Per-trade indicators + sizing rules | Alpha layer; cut |
| ACT-49 | Oilshare/RFS + pricing overlays | Alpha layer; cut |
| ACT-51 | Topology hardening (hot-standby + 3-instance + region pin + per-leg observability + hedge fees) | Single-process layout adequate; hedge fees kept inline in ACT-10 rebate accounting |
| ACT-55 | Forward-curve carry + Routledge-Seppi-Spatt + Deaton-Laroque | Macro inventory models; not load-bearing |
| ACT-56 | Cross-asset hedge selection + intensity calibration | Folded into ACT-MM5 if/when MM extends to ZC/ZM/ZL |
| ACT-57 | Misc Kalshi residuals (URL slug + letter-prefix + DCM + interest model) | Pure long-tail; defer indefinitely |
| ACT-58 | FIX 5.0 SP2 + 200K cap + cancel-vs-amend fees | Premier+ tier; out of scope |
| ACT-59 | Operational extras (PIN/VPIN + Daily Bulletin + buy_max_cost + sandbox cap + CVOL) | Mostly diagnostic; defer |

**Total cuts: 21 F1 actions.**
**Total adds: 6 MM-related actions (ACT-MM1 through ACT-MM6).**
**Net change: −15 actions.** (F2 also has six R-suffixed reductions in
scope of retained actions, which don't show up in the headcount but
materially reduce effort.)

---

## 6. New work introduced by F2 (the MM-Program surface)

These six actions have no F1 equivalent and represent the work the F1
plan would have produced if the audit had known the strategy was
rebate-driven from the start.

**ACT-MM1 — Compliance runtime monitor.** Tracks per-market uptime,
spread-cap state, minimum-size state, two-sided-quoting state.
Continuously. Drives quoter behavior in real time (e.g., quote
two-sided even when one-sided would be more economic, because the
agreement requires it). Emits events that ACT-MM6 consumes for monthly
reporting. Lives in a new `compliance/` package. M effort.

**ACT-MM2 — MM Agreement application + PAL acquisition.** Not
engineering. Submit application to Kalshi, negotiate terms (rebate
schedule, designated markets, obligations), sign Provisional Approval
Letter or full Agreement. Engineering can proceed in paper-trading mode
without this, but production wire-on is gated on it. Folds in `GAP-094`
re-framed from minor to blocker. Calendar-XL (months); engineering-S
(config wiring once obtained).

**ACT-MM3 — Rebate-aware P&L attribution.** Per-day and per-month
breakdown: rebate income, spread P&L (often near-zero or slightly
negative on a rebate book — that's expected), hedge slippage, fees,
adverse-selection loss, capital cost. Lives in `attribution/`. The
economic dashboard for the business; without it you cannot tell
whether you're profitable. M effort.

**ACT-MM4 — Designated-market quoting policy.** Most MM Agreements
designate specific markets in which you must maintain two-sided quotes
even when economically suboptimal (e.g., a deep-OTM bucket two days
before settlement). The policy needs a config-driven enforcer with
override conditions for extreme cases (kill-switch fires, position
breach, etc.). M effort.

**ACT-MM5 — Multi-product MM extension.** Parametrize the entire stack
(commodities config, RND pipeline, hedge sizer, position store) to
operate concurrently on multiple `KX*` Event families. If MM Agreement
covers `KXSOYBEANW` only, this is deferrable; if it covers a
suite, this becomes Wave 1 priority. Universe-shape change rather than
signal alpha. L effort.

**ACT-MM6 — Monthly MM-Agreement reporting.** Pipeline that consumes
ACT-MM1's runtime events plus reconciliation data and produces the
monthly compliance report Kalshi requires (uptime per market,
breach counts, designated-market presence, position-flat-by-EOD
compliance). Format depends on Kalshi's actual MM-program template
(unknown until ACT-MM2 closes). M effort.

---

## 7. Outstanding decisions, F2 update

The original F1 had 30 ODs; F2 collapses or invalidates several and
adds new ones.

**Resolved by F2 framing:**

- OD-04 (density refresh sync vs async) → **sync, inline.** Resolved.
- OD-06/OD-20 (Pyth vs Databento) → **Pyth for ZS L1, low-cost vendor
  for CME options chain.** Resolved.
- OD-15 (Kalshi rate-limit tier) → **Standard tier sufficient.**
  Resolved.
- OD-25 (kill-switch N and K thresholds) → **defer to first month of
  paper trade observation.** Posture-resolved.
- OD-29 (Σᵢⱼ estimator) → **moot — matrix skew cut.** Invalidated.
- OD-30 (practitioner corpus buffet vs recipe) → **moot — practitioner
  signals cut from plan.** Invalidated.

**Newly required by F2:**

- **OD-31 — operating cadence.** As stated in §1. Treat as resolved.
- **OD-32 — MM-Agreement scope.** Single-product (`KXSOYBEANW` only)
  vs multi-product (`KXSOYBEANW` + adjacent `KX*` markets) at
  agreement time? Affects ACT-MM5 priority. Open until ACT-MM2 closes.
- **OD-33 — rebate schedule and obligations.** Specific terms unknown
  until ACT-MM2 closes; engineering has to assume reasonable defaults
  (95% uptime, 4¢ max spread, 10-contract min size, two-sided
  quoting) until actual terms land.
- **OD-34 — designated-market list.** Subset of `KXSOYBEANW` markets
  where two-sided quoting is contractually required. Drives ACT-MM4
  config. Unknown until ACT-MM2 closes.
- **OD-35 — capital deployment.** Total capital allocation across
  Kalshi-side margin vs CBOT hedge-side margin. ACT-29 capital
  allocator design depends on this; default for now is 70/30
  Kalshi/CBOT.

**Still open from F1:**

- OD-13 (recon cadence) — keep working default (scheduler in-process /
  cron EOD).
- OD-19 (fee table location) — `fees/` package, called from pricer +
  order builder + ACT-MM3 attribution.
- OD-21 (survivorship) — forward-only with per-trade-print
  augmentation.
- OD-22 (USDA look-ahead) — PIT.
- OD-24 (measure-overlay form) — parametric monotone in midprice.
- OD-26 (vol_adjustment semantics) — both κ-width and κ-spread.
- OD-27 (SanityError fan-out) — `quote_drop` default; consecutive
  errors → `market_suspend`.
- OD-28 (`buy_max_cost` enforcement layer) — client wrapper for
  per-request, risk layer for per-Event sum.

---

## 8. Updated kill criteria

Five new ones replace or supplement the F1 set:

- **KC-MM-01.** *MM Agreement not granted.* Kalshi declines or
  indefinitely defers the application; without it, rebate income is
  zero and the strategy as framed is non-viable. The strategy can fall
  back to F1 edge-driven framing only if RND quality on M0 is
  sufficient, which C10-KC-01 already gates.
- **KC-MM-02.** *Compliance breaches generate net negative income.* If
  spread-cap or uptime breaches incur penalties or rebate forfeiture
  at a rate that exceeds gross rebate income for two consecutive
  months, the engine cannot meet the agreement.
- **KC-MM-03.** *Adverse selection > rebate revenue.* Even compliant
  quoting is unprofitable: realized markout on filled quotes (averaged
  weekly) exceeds per-fill rebate plus capture spread for four
  consecutive Events. The RND model is too inaccurate for the
  agreement spread cap.
- **KC-MM-04.** *Hedge cost > rebate revenue.* Monthly hedge slippage
  + IB commissions + CME fees exceed monthly rebate income. The
  hedge configuration cannot support the Kalshi book.
- **KC-MM-05.** *Capital efficiency too low.* Annualized rebate net
  P&L on deployed capital is below opportunity cost (e.g., < 5%) for
  six consecutive months. Strategy is not worth the risk for the
  return.

The original C10-KC-01 through C10-KC-07 still apply; KC-AUD-01 through
KC-AUD-09 still apply except KC-AUD-08 (latency budget unachievable),
which is invalidated under F2 because F2 has no microsecond budget.

---

## 9. Summary

F2 converts the project from "build a quantitative market-making
research-grade pricing engine" into "build a periodic-quoting service
that qualifies for and operates within Kalshi's MM Program." Engineering
volume drops ~24% by action count and meaningfully more by effort
because the cuts concentrate in XL items (microstructure, FIX, hot-
standby topology, full alpha layer, Databento). Six new MM-specific
actions are added covering compliance runtime, MM Agreement
acquisition, rebate-aware attribution, designated-market policy,
multi-product extension, and monthly reporting. The biggest shift is
not the cut count but the **objective function**: F1 optimised
edge-net-of-adverse-selection; F2 optimises compliant-fill-volume
subject to MM-Agreement obligations. They produce different code
in the same modules.

Read F2 alongside F1, not as a replacement: F1 is the upper bound and
the audit-aligned reference; F2 is what we actually do.

*End of `audit_F2_refactor_plan_mm_program.md`.*
