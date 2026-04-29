# Audit F4 — Refactor Plan: Asymmetric Market-Making on Kalshi Commodity Monthlies

This file supersedes `audit_F3_refactor_plan_lip.md` (F3) for
sequencing purposes.

- **F1** (`audit_F_refactor_plan.md`) — 59-action edge-driven plan.
  Historical reference; F4 reuses F1's gap register and algorithmic
  detail.
- **F2** (`audit_F2_refactor_plan_mm_program.md`) — 45-action
  MM-Agreement plan. Superseded; formal MM Agreement was the wrong
  program.
- **F3** (`audit_F3_refactor_plan_lip.md`) — 44-action LIP-driven
  plan. Superseded; `KXSOYBEANW` is not LIP-eligible (Wave 0 gate
  NO-GO, 2026-04-27).
- **F4 (this file)** — the operative plan. Asymmetric market-making
  on Kalshi commodity **monthly** markets, priced against an empirical
  RND extracted from CME options, hedged on Interactive Brokers.

Read this file alongside `prompts/build/PREMISE.md` for the full
strategic context.

---

## 1. Executive summary

The F3 plan's economic premise — LIP pool share as primary income on
`KXSOYBEANW` — was empirically falsified on 2026-04-27 when live API
investigation confirmed that `KXSOYBEANW` is not a Liquidity Incentive
Program market (see `state/wave_0_gate.md`). The Wave 0 gate returned
NO-GO, triggering a strategic pivot.

**F4 pivots to asymmetric market-making on Kalshi commodity monthly
markets** (`KXSOYBEANMON` first, then `KXCORNMON`). The thesis: extract
an empirical risk-neutral density (RND) from CME ZS options via
Breeden-Litzenberger + SVI + Figlewski, convert it to bucket
Yes-prices under Kalshi's half-line decomposition, and quote two-sided
around model fair value — NOT around the Kalshi midpoint. Post tighter
on the side where the midpoint disagrees with the model (capturing
implied edge in addition to spread). Withdraw facing adverse taker flow
and during scheduled news windows (USDA WASDE, Crop Progress). Hedge
residual delta on CBOT ZS futures via IBKR.

Primary income is **spread capture net of fees and adverse selection**,
not LIP pool share. LIP scoring infrastructure from Wave 0 is retained
for optionality (if monthlies join LIP, it activates immediately) but
is not load-bearing.

The plan organizes 16 new actions (`F4-ACT-01` through `F4-ACT-16`)
into 3 waves, building on the 16 verified-complete Wave 0 actions.
Estimated scope: ~6,000-10,000 LoC of new code across the 3 waves.

---

## 2. Strategic frame (F4)

**Business model.** Earn spread on Kalshi commodity monthly markets
(`KXSOYBEANMON`, `KXCORNMON`, others per `PREMISE.md` priority table)
by quoting two-sided around an RND-derived fair value that is more
accurate than the Kalshi midpoint. Asymmetric: post tighter on the
edge side, wider on the consensus side. Edge = model fair value minus
Kalshi midpoint; spread capture = gross spread minus fees minus
adverse selection minus hedge cost.

**Target series (build priority order).**

| Priority | Series | Underlying | Hedge | Notes |
|---|---|---|---|---|
| 1 | `KXSOYBEANMON` | CBOT ZS | ZS via IBKR | Most developed CME options chain |
| 2 | `KXCORNMON` | CBOT ZC | ZC via IBKR | Same shape as soy |
| 3 | `KXSUGARMON` | ICE-EU sugar | None | Un-hedged or skip |
| 4 | `KXNICKELMON` | LME nickel | None | Un-hedged |
| 5 | `KXLITHIUMMON` | CME lithium | None | Thin liquidity |

**Market structure.** Each `KX*MON` Event contains half-line
"above-strike" markets at uniform 5c spacing. Bucket prices are
derived: `Yes_bucket(L_i, L_{i+1}) = Yes(>L_i) - Yes(>L_{i+1})`.
This is the structure ACT-13's corridor decomposition was built for.

**Operating cadence.** Unchanged from OD-31: periodic-quoting service
with 30-second baseline, sub-second event reflex, threshold-driven
hedge. Synchronous main loop; asyncio for I/O only.

**Settlement-gap risk — the binding constraint.** USDA WASDE prints
can move soybean futures 2-5% in 30 seconds. Mitigations: pre-window
pull-all, size-down ladder, wide-out widening, hedge tightening, hard
kill. See `PREMISE.md` for detail.

**Realistic economic target.** $20-35k/year net across 5 target
series, conditional on RND accuracy (M0 test), settlement-gap
management, and $30-50k capital deployment.

---

## 3. What carries forward from Wave 0

All 16 Wave 0 actions are verified-complete with ~637 tests passing.
Every one is product-family-agnostic infrastructure that carries
forward into F4 without reimplementation.

| Wave 0 action | F4 status | Adaptation needed for F4 |
|---|---|---|
| ACT-01 (forward-capture Phase 1a) | Carries forward | Point at `KXSOYBEANMON` tickers instead of `KXSOYBEANW` |
| ACT-02 (soy yaml) | Carries forward | Already covers ZS; add `KXSOYBEANMON` Kalshi block (F4-ACT-01) |
| ACT-03 (Kalshi REST client) | Carries forward | No change — client is ticker-agnostic |
| ACT-04 (ticker + bucket) | Carries forward | Parser already handles `KX*MON` ticker format; verify half-line stride for monthlies |
| ACT-05 (WS multiplex) | Carries forward | No change — channel subscriptions are ticker-parameterised |
| ACT-06 (order builder) | Carries forward | No change — order types are product-agnostic |
| ACT-07 (24/7 calendar) | Carries forward | Monthlies also trade 24/7; calendar logic unchanged |
| ACT-08 (settle resolver) | **Needs fix** | Roll rule is FND-15 BD, not FND-2 BD (digest finding). Fix in F4-ACT-01 |
| ACT-09 (positions) | Carries forward | No change — per-Event signed exposure is product-agnostic |
| ACT-10 (fees) | Carries forward | No change — fee formula is product-agnostic |
| ACT-11 (kill primitives) | Carries forward | No change |
| ACT-12 (risk gates) | Carries forward | No change — delta cap / per-Event / max-loss are product-agnostic |
| ACT-13 (corridor adapter) | Carries forward | Already implements half-line corridor decomposition; exactly right for monthlies |
| ACT-LIP-POOL (pool ingest) | Retained for optionality | Not load-bearing in F4; activates if monthlies join LIP |
| ACT-LIP-SCORE (score tracker) | Retained for optionality | Same |
| ACT-LIP-VIAB (viability) | Retained for optionality | Reusable on any product family |

---

## 4. What is NOT carried forward from F3

F3 Wave 1+ actions that are dropped or substantially reframed under F4:

| F3 action | F4 disposition | Reason |
|---|---|---|
| ACT-14 (IV surface signature) | **Absorbed into F4-ACT-03** (RND pipeline) | The IV surface refactor is a pre-condition for the RND pipeline; folded into the same action |
| ACT-15 (TheoOutput shape) | **Absorbed into F4-ACT-03** | bid/ask + Greeks land as part of the RND pipeline output |
| ACT-16 (CME ingest) | **Reframed as F4-ACT-02** | Reduced scope: no MBP/MBO, no Databento. EOD options chain + L1 via low-cost vendor or CME direct |
| ACT-17 (RND pipeline) | **Reframed as F4-ACT-03** | Core of F4; absorbs ACT-14/15 prerequisites |
| ACT-18 (USDA event clock) | **Reframed as F4-ACT-06** | Narrower: event-window pull-and-repost only, not full multi-zone calendar |
| ACT-19 (quoting, LIP-reframed) | **Reframed as F4-ACT-04** | Asymmetric quoter, NOT distance-multiplier-preserving inside quoting. Model-edge-driven |
| ACT-20 (hedge leg) | **Reframed as F4-ACT-05** | Unchanged in substance; IB confirmed |
| ACT-21 (settlement) | **Deferred to F4 Wave 3** as F4-ACT-12 | Not on critical path for initial quoting |
| ACT-22 (order pipeline) | **Reframed as F4-ACT-07** | Unchanged in substance |
| ACT-23 (reconciliation) | **Deferred to F4 Wave 3** as F4-ACT-13 | Not needed until live trading |
| ACT-24 (kill switch e2e) | **Reframed as F4-ACT-08** | Simpler: structlog + file logging, no Prometheus/Grafana |
| ACT-25 (scenarios) | **Reframed as F4-ACT-10** | Settlement-gap scenario harness specifically |
| ACT-26 (backtest M0) | **Reframed as F4-ACT-09** | M0 backtest validator specifically for RND accuracy |
| ACT-LIP-PNL | **Reframed as F4-ACT-14** | Live PnL attribution (spread-centric, not LIP-pool-centric) |
| ACT-LIP-COMPETITOR | **Dropped** | Competition estimation was LIP-specific (score share); irrelevant for spread-capture framing |
| ACT-LIP-MULTI | **Dropped** | Multi-market LIP extension; irrelevant under F4 |
| ACT-LIP-RECON | **Dropped** | LIP reward reconciliation; irrelevant under F4 |
| ACT-27 (Heston SV) | **Deferred** | Not needed until RND pipeline empirically underprices tail buckets |
| ACT-29 (basis tracker) | **Deferred** | Hedge-leg basis tracker lands in F4 Wave 3 |
| ACT-32 (pre-event widening) | **Absorbed into F4-ACT-06** | Folded into USDA event-clock action |
| ACT-33 (measure overlay) | **Deferred** | Post-M0; only if RND shows systematic bias |
| ACT-35 (wash-trade) | **Deferred** | Lands when order volume justifies |
| ACT-37 (limit-day) | **Deferred** | Lands in F4 Wave 3 |
| All Wave 3 actions (ACT-41, ACT-32-EXT, ACT-LIP-MULTI) | **Dropped or deferred** | Signal alpha and capacity expansion are out of scope for F4 initial build |
| All Wave 4 actions (ACT-50, ACT-52, ACT-53, ACT-54, ACT-LIP-RECON) | **Deferred except ACT-54** | Hardening lands after live trading proves viable; ACT-54 (Pyth hardening) is a pre-existing bug fix, deferred |

---

## 5. F4 action set (16 actions, 3 waves)

### F4 Wave 1 — Foundation: M0 spike + Wave 0 adaptations + CME ingest

The minimum to answer the M0 question: "Does the RND from CME
soybean options meaningfully outpredict Kalshi's midpoint on monthly
commodity bucket markets?" Plus Wave 0 adaptations for the monthlies
pivot.

| ID | Summary | Type | Effort | Gaps closed | Deps (Wave 0) | Deps (F4) | Dependents |
|---|---|---|---|---|---|---|---|
| F4-ACT-01 | Wave 0 adaptations for monthlies: fix ACT-08 roll rule to FND-15 BD; add `KXSOYBEANMON` Kalshi block to `commodities.yaml`; verify ACT-04 ticker parser handles monthly ticker format; update ACT-01 capture target to `KXSOYBEANMON` tickers | refactor | S | new gap, not in F1 register (monthlies pivot) | ACT-02, ACT-04, ACT-08 | — | F4-ACT-02, F4-ACT-03, F4-ACT-09 |
| F4-ACT-02 | CME options chain ingest (ZS first): EOD options chain pull (low-cost vendor or CME DataMine) + put-call parity prune + chain-to-IV converter. No MBP/MBO, no Databento. L1 spot via Pyth (already exists) | feature | L | GAP-046, GAP-047, GAP-063 | ACT-02 | F4-ACT-01 | F4-ACT-03 |
| F4-ACT-03 | RND extractor pipeline: IV surface refactor `(commodity, strike, expiry)` + BL identity `f_T = e^(rT) * d^2C/dK^2` + SVI fitter `w(k) = a + b{rho(k-m) + sqrt((k-m)^2 + sigma^2)}` + butterfly/calendar arb constraints + Figlewski piecewise-GEV tail attachment + bucket integration `value_i = integral_l^u f_T dx` + sum-to-1 gate + variance rescaling for non-co-terminal expiries + `TheoOutput` shape change (bid/ask + per-bucket Greeks) | feature+refactor | XL | GAP-006, GAP-036, GAP-037, GAP-038, GAP-041, GAP-042, GAP-043, GAP-044, GAP-045, GAP-049, GAP-101, GAP-003 | ACT-13 | F4-ACT-01, F4-ACT-02 | F4-ACT-04, F4-ACT-05, F4-ACT-09, F4-ACT-10 |
| F4-ACT-15 | M0 spike notebook: Jupyter notebook (not production code) that pulls historical CME ZS options + Kalshi `KXSOYBEANMON` settled outcomes, runs the F4-ACT-03 RND pipeline offline, and scores RND-implied bucket prices against realized outcomes. Go/no-go on KC-F4-01 | research | M | new gap, not in F1 register (M0 validation) | ACT-01 | F4-ACT-01, F4-ACT-02, F4-ACT-03 | — (gate only) |

**F4 Wave 1 total: 4 actions.**

Wave 1 ends with the M0 spike notebook producing a go/no-go on
KC-F4-01 (RND accuracy). If NO-GO, the project halts — RND does not
outpredict the midpoint. If GO, Wave 2 proceeds.

### F4 Wave 2 — Core trading: Asymmetric quoter + hedge + risk

Build the actual trading engine: quote around model fair value, manage
risk, hedge on IBKR, handle USDA events.

| ID | Summary | Type | Effort | Gaps closed | Deps (Wave 0) | Deps (F4) | Dependents |
|---|---|---|---|---|---|---|---|
| F4-ACT-04 | Asymmetric quoter: quote two-sided around RND fair value (NOT Kalshi midpoint); post tighter on the edge side where midpoint disagrees with model; `post_only=True` always; inventory-aware gamma-skew when `\|q\| > threshold`; min spread floor 4c each side; configurable widening on event reflex | feature | L | GAP-001 (partial: no A-S/CJ HJB, just reservation-price skew), GAP-002, GAP-022 (partial: simplified GLFT asymptotic), GAP-023, GAP-029, GAP-145 | ACT-06, ACT-09, ACT-10, ACT-12 | F4-ACT-03 | F4-ACT-08, F4-ACT-09, F4-ACT-10, F4-ACT-14 |
| F4-ACT-05 | IBKR hedge leg: aggregate book delta `Delta^port = sum_i q_i * Delta_i^K` + ZS-futures sizer (N_ZS=5,000 bu) + `\|Delta^port\| >= 1` threshold trigger + IB Gateway + `ib_insync` + ZS L1 via Pyth | feature | L | GAP-102, GAP-103, GAP-104, GAP-108 | ACT-09, ACT-12 | F4-ACT-03 | F4-ACT-08, F4-ACT-10, F4-ACT-14 |
| F4-ACT-06 | USDA event clock + pre-event protocol: event calendar for WASDE/Crop Progress/Plantings/Acreage/Stocks; pre-window pull-all (30-60s before); size-down ladder in 24h run-up; spread widening during window; post-event refit + repost | feature | M | GAP-053, GAP-067 (partial: soybean-only, not multi-zone), GAP-019 (partial: kappa consumer for soybean), new gap (settlement-gap pre-event protocol, not in F1 register) | ACT-07 | — | F4-ACT-04, F4-ACT-10 |
| F4-ACT-07 | Order pipeline: `POST /portfolio/orders` + `DELETE /portfolio/orders/{id}` + amend/decrease/batch + idempotency (client-order-ID) + amend-not-cancel queue-priority preservation | feature | M | GAP-132, GAP-133, GAP-137, GAP-138 | ACT-06, ACT-05 | — | F4-ACT-04, F4-ACT-08, F4-ACT-12 |
| F4-ACT-08 | Kill switch end-to-end: four triggers (signed-delta breach, PnL drawdown, hedge heartbeat fail, Kalshi WS reconnect storm) + windowed reconnect counter + structured logging via `structlog` + `SanityError` policy (quote_drop default, consecutive -> market_suspend) | feature+bugfix | M | GAP-172, GAP-174, GAP-178, GAP-179, GAP-180 | ACT-11 | F4-ACT-04, F4-ACT-05, F4-ACT-07 | F4-ACT-14 |
| F4-ACT-16 | Taker-imbalance detector: from orderbook_delta + fill stream, detect adverse taker flow direction; when detected, withdraw the side facing the flow; re-enter after configurable cooldown | feature | M | new gap, not in F1 register (F4-specific asymmetric defense) | ACT-05 | F4-ACT-04, F4-ACT-07 | F4-ACT-14 |

**F4 Wave 2 total: 6 actions.**

### F4 Wave 3 — Validation and operations: Backtest + settlement + PnL

Validate the system's economics, add settlement handling, and build
the PnL attribution dashboard.

| ID | Summary | Type | Effort | Gaps closed | Deps (Wave 0) | Deps (F4) | Dependents |
|---|---|---|---|---|---|---|---|
| F4-ACT-09 | M0 backtest validator: replay engine over captured `KXSOYBEANMON` data + simulated quoting with the asymmetric quoter + DuckDB+Parquet substrate + walk-forward scoring against settled outcomes | feature | XL | GAP-146, GAP-147, GAP-149, GAP-150 | ACT-01, ACT-10 | F4-ACT-01, F4-ACT-03, F4-ACT-04 | F4-ACT-14 |
| F4-ACT-10 | Settlement-gap scenario harness: WASDE-day P&L scenario, weather-shock 3-5% gap, expiry-day liquidity collapse, CBOT-closed regime detector | feature | L | GAP-112, GAP-113, GAP-121 | ACT-12 | F4-ACT-03, F4-ACT-04, F4-ACT-05, F4-ACT-06 | — |
| F4-ACT-11 | Settlement-gap risk gate: configurable per-event max-loss threshold that auto-widens or auto-pulls in the run-up to settlement; integrates with ACT-12 risk gates + F4-ACT-08 kill switch | feature | M | new gap, not in F1 register (F4-specific settlement-gap protection) | ACT-12 | F4-ACT-04, F4-ACT-08 | — |
| F4-ACT-12 | Settlement reconciler: settled-outcome poller + bucket-grid lifecycle + Rule 13.1(d) outcome ingest + roll-day handling | feature | L | GAP-086, GAP-088, GAP-090, GAP-091, GAP-099 | ACT-04, ACT-08 | F4-ACT-01, F4-ACT-07 | F4-ACT-13 |
| F4-ACT-13 | Reconciliation pipeline: 3x recon (open/intraday/EOD) + fill ingest + per-bucket markout (1m/5m/30m) + DuckDB+Parquet store | feature | L | GAP-117, GAP-134, GAP-135, GAP-136 | ACT-09 | F4-ACT-07, F4-ACT-12 | F4-ACT-14 |
| F4-ACT-14 | Live PnL attribution: spread P&L + model-edge P&L + hedge slippage + fees + adverse-selection loss + capital cost. Daily, weekly, per-market. Per-bucket markout analysis | feature | M | GAP-151, new gap (F4-specific PnL decomposition) | — | F4-ACT-04, F4-ACT-05, F4-ACT-08, F4-ACT-09, F4-ACT-13, F4-ACT-16 | — |

**F4 Wave 3 total: 6 actions.**

**F4 grand total: 16 actions** across 3 waves.

---

## 6. Dependency graph

Every edge `A -> B` means "B cannot start until A has landed." Wave 0
actions are shown as prerequisites where relevant.

```
Wave 0 (all verified-complete, shown as roots)
  ACT-01 (capture)
  ACT-02 (soy yaml)
  ACT-04 (ticker+bucket)
  ACT-05 (WS multiplex)
  ACT-06 (order builder)
  ACT-07 (24/7 calendar)
  ACT-08 (settle resolver)
  ACT-09 (positions)
  ACT-10 (fees)
  ACT-11 (kill primitives)
  ACT-12 (risk gates)
  ACT-13 (corridor adapter)

F4 Wave 1
  F4-ACT-01 (monthlies adapt) ──> F4-ACT-02, F4-ACT-03, F4-ACT-09
  F4-ACT-02 (CME ingest)      ──> F4-ACT-03
  F4-ACT-03 (RND pipeline)    ──> F4-ACT-04, F4-ACT-05, F4-ACT-09, F4-ACT-10, F4-ACT-15
  F4-ACT-15 (M0 spike)        ──> (gate: GO/NO-GO on KC-F4-01)

F4 Wave 2
  F4-ACT-04 (asym quoter)     ──> F4-ACT-08, F4-ACT-09, F4-ACT-10, F4-ACT-14, F4-ACT-16
  F4-ACT-05 (IBKR hedge)      ──> F4-ACT-08, F4-ACT-10, F4-ACT-14
  F4-ACT-06 (USDA events)     ──> F4-ACT-04, F4-ACT-10
  F4-ACT-07 (order pipeline)  ──> F4-ACT-04, F4-ACT-08, F4-ACT-12, F4-ACT-16
  F4-ACT-08 (kill switch e2e) ──> F4-ACT-11, F4-ACT-14
  F4-ACT-16 (taker-imbalance) ──> F4-ACT-14

F4 Wave 3
  F4-ACT-09 (M0 backtest)     ──> F4-ACT-14
  F4-ACT-10 (scenarios)       ──> (leaf)
  F4-ACT-11 (settle-gap gate) ──> (leaf)
  F4-ACT-12 (settlement)      ──> F4-ACT-13
  F4-ACT-13 (reconciliation)  ──> F4-ACT-14
  F4-ACT-14 (PnL attribution) ──> (leaf)
```

### Full dependency listing per action

| F4 action | Depends on (Wave 0) | Depends on (F4) |
|---|---|---|
| F4-ACT-01 | ACT-02, ACT-04, ACT-08 | — |
| F4-ACT-02 | ACT-02 | F4-ACT-01 |
| F4-ACT-03 | ACT-13 | F4-ACT-01, F4-ACT-02 |
| F4-ACT-15 | ACT-01 | F4-ACT-01, F4-ACT-02, F4-ACT-03 |
| F4-ACT-04 | ACT-06, ACT-09, ACT-10, ACT-12 | F4-ACT-03 |
| F4-ACT-05 | ACT-09, ACT-12 | F4-ACT-03 |
| F4-ACT-06 | ACT-07 | — |
| F4-ACT-07 | ACT-06, ACT-05 | — |
| F4-ACT-08 | ACT-11 | F4-ACT-04, F4-ACT-05, F4-ACT-07 |
| F4-ACT-16 | ACT-05 | F4-ACT-04, F4-ACT-07 |
| F4-ACT-09 | ACT-01, ACT-10 | F4-ACT-01, F4-ACT-03, F4-ACT-04 |
| F4-ACT-10 | ACT-12 | F4-ACT-03, F4-ACT-04, F4-ACT-05, F4-ACT-06 |
| F4-ACT-11 | ACT-12 | F4-ACT-04, F4-ACT-08 |
| F4-ACT-12 | ACT-04, ACT-08 | F4-ACT-01, F4-ACT-07 |
| F4-ACT-13 | ACT-09 | F4-ACT-07, F4-ACT-12 |
| F4-ACT-14 | — | F4-ACT-04, F4-ACT-05, F4-ACT-08, F4-ACT-09, F4-ACT-13, F4-ACT-16 |

---

## 7. Parallelism analysis, by wave

### F4 Wave 1

F4-ACT-01 (monthlies adapt, S effort) starts immediately — all Wave 0
deps are met. After F4-ACT-01 lands, F4-ACT-02 (CME ingest, L effort)
unblocks. After F4-ACT-02 lands, F4-ACT-03 (RND pipeline, XL effort)
unblocks. F4-ACT-15 (M0 spike) needs all three.

Wave 1 is **mostly serial**: F4-ACT-01 -> F4-ACT-02 -> F4-ACT-03 ->
F4-ACT-15. However, F4-ACT-02 and F4-ACT-03 can overlap if F4-ACT-03
starts the IV surface refactor and SVI fitter while F4-ACT-02 completes
the CME chain ingest — the BL + bucket integration step of F4-ACT-03
waits on F4-ACT-02, but the IV signature change does not.

Critical path: F4-ACT-01 (S ~1d) + F4-ACT-02 (L ~1-2w) + F4-ACT-03
(XL ~2-3w) + F4-ACT-15 (M ~2-3d) = ~4-6 weeks.

With two engineers: one takes F4-ACT-01 then F4-ACT-03 (starting with
the IV refactor that doesn't need CME data); the other takes F4-ACT-02.
They converge at the BL + bucket integration step. F4-ACT-15 lands
last. Estimated: ~3-4 weeks.

### F4 Wave 2

F4-ACT-06 (USDA events) and F4-ACT-07 (order pipeline) start at
Wave 2 t=0 — their only deps are Wave 0 actions (already met).
F4-ACT-04 (asymmetric quoter) needs F4-ACT-03 (Wave 1) + F4-ACT-06
(event protocol integration) + F4-ACT-07 (order submission).
F4-ACT-05 (IBKR hedge) needs F4-ACT-03 only — can start at Wave 2 t=0.
F4-ACT-08 (kill switch) needs F4-ACT-04 + F4-ACT-05 + F4-ACT-07 — mid-wave.
F4-ACT-16 (taker-imbalance) needs F4-ACT-04 + F4-ACT-07 — mid-wave.

Parallel tracks:
- Track A: F4-ACT-06 (M) + F4-ACT-04 (L) -> F4-ACT-16 (M)
- Track B: F4-ACT-05 (L) -> merge into F4-ACT-08 (M)
- Track C: F4-ACT-07 (M) -> feeds F4-ACT-04, F4-ACT-08, F4-ACT-16

With two engineers, critical path: F4-ACT-06/07 (M ~3d, parallel) +
F4-ACT-04 (L ~1-2w) + F4-ACT-08 (M ~3d) = ~3-4 weeks. F4-ACT-05
runs in parallel on the second engineer.

### F4 Wave 3

Heavily parallel. F4-ACT-09, F4-ACT-10, F4-ACT-11, F4-ACT-12 can
all start at Wave 3 t=0 (all deps met from Wave 2). F4-ACT-13 needs
F4-ACT-12. F4-ACT-14 needs almost everything else — it is the final
leaf.

Parallel tracks:
- Track A: F4-ACT-09 (XL) -> F4-ACT-14 (M)
- Track B: F4-ACT-12 (L) -> F4-ACT-13 (L) -> F4-ACT-14
- Track C: F4-ACT-10 (L) — leaf
- Track D: F4-ACT-11 (M) — leaf

With two engineers, critical path is max(Track A, Track B). Track A:
F4-ACT-09 (XL ~2-3w). Track B: F4-ACT-12 (L ~1-2w) + F4-ACT-13
(L ~1-2w) = ~2-4w. F4-ACT-14 (M ~3d) is the tail.

Estimated: ~3-5 weeks.

### Total estimated critical path

Wave 1 (~4w) + M0 gate (~1w evaluation) + Wave 2 (~4w) + Wave 3
(~4w) = ~13 weeks with 2 engineers, contingent on M0 GO.

---

## 8. Kill criteria

### F4-specific (from PREMISE.md)

- **KC-F4-01. M0 fails.** RND-implied bucket prices miss realized
  Kalshi-resolution outcomes by >3c on >50% of buckets across 4+
  settled monthly Events on `KXSOYBEANMON`. Strategy dead. Evaluated
  at F4-ACT-15 gate.

- **KC-F4-02. Settlement-gap losses exceed gross spread.** Realized
  P&L from gap events exceeds cumulative spread for two consecutive
  months. Risk control insufficient.

- **KC-F4-03. Capital efficiency below opportunity cost.** Annualized
  net P&L on deployed capital <5% for six consecutive months. Not
  worth operational risk.

- **KC-F4-04. Hedge-leg drag.** Monthly IB commissions + ZS/ZC
  slippage exceed monthly Kalshi spread capture on hedgeable series.

- **KC-F4-05. Adverse-selection dominance.** Realized markout on
  filled quotes exceeds 60% of captured spread for four consecutive
  weeks. Model edge is illusory.

### Audit-derived (still applicable from F1)

- **KC-AUD-01. Forward-capture loss.** Kalshi tape empty or
  unreplayable for >5 consecutive trading days in first 3 months.

- **KC-AUD-03. SVI arbitrage failure.** SVI fits violate butterfly or
  calendar arb on >25% of co-terminal weeks across first four settled
  Events.

- **KC-AUD-05. Weekend MM impractical.** `StaleDataError` pulls
  quotes for >30% of the weekend window.

- **KC-AUD-06. Reconciliation divergence.** WS `fill` frames disagree
  with `GET /portfolio/fills` on >1% of fills.

- **KC-AUD-07. Hedge-attribution failure.** Hedge slippage dominates
  gross edge for >50% of trading days.

### Audit-derived kill criteria NOT carried forward

- **KC-AUD-02** (Kalshi client never lands): Wave 0 ACT-03
  verified-complete. Moot.
- **KC-AUD-04** (inventory unbounded): replaced by KC-F4-05 which
  tests the same phenomenon with realized data rather than synthetic.
- **KC-AUD-08** (latency budget unachievable): invalidated under F3;
  stays invalidated.
- **KC-AUD-09** (calibration cadence): deferred; no nightly
  calibration in F4 initial build.

---

## 9. Outstanding decisions

### Resolved by F4 framing

- **OD-32' (market-selection policy under LIP)** -> invalidated. F4
  targets specific `KX*MON` series, not LIP-eligible markets.
- **OD-33' (target-size posting under LIP)** -> invalidated.
- **OD-34' (distance-multiplier calibration)** -> invalidated.
- **OD-36 (event-window policy under LIP)** -> reframed as
  settlement-gap risk mitigation (F4-ACT-06). No LIP score trade-off.

### Carried forward from F3 with F4 adjustments

- **OD-04 (density refresh sync/async)** -> sync inline. RND refresh
  cadence: every 5 minutes from EOD chain data, or sub-second from
  L1 tick updates when available. Resolved.
- **OD-06/OD-20 (CME ingest source)** -> **Reframed under F4.** Pyth
  for L1 spot (already live). CME options chain via low-cost vendor or
  CME DataMine (NOT Databento). Resolved.
- **OD-13 (reconciliation cadence)** -> in-process for open/intraday,
  cron for EOD. Carried forward.
- **OD-14 (STP policy)** -> `maker`. Carried forward.
- **OD-15 (Kalshi rate-limit tier)** -> Standard. Carried forward.
- **OD-16 (kill-switch authorization)** -> in-process. Carried forward.
- **OD-19 (fee table location)** -> `fees/` package (already built,
  ACT-10). Resolved.
- **OD-25 (kill-switch N, K thresholds)** -> N=15s, K=5/min defaults;
  refine after paper-trade. Carried forward.
- **OD-26 (vol_adjustment semantics)** -> both kappa-width and
  kappa-spread. Carried forward.
- **OD-27 (SanityError fan-out)** -> quote_drop default;
  consecutive -> market_suspend. Carried forward.
- **OD-28 (buy_max_cost enforcement)** -> client wrapper per-request,
  risk layer per-Event. Carried forward.
- **OD-35 (capital deployment split)** -> 70/30 Kalshi/CBOT default.
  Carried forward.

### New under F4

- **OD-37 (CME options chain vendor).** Which vendor for the ZS
  options chain? Options: (a) CME DataMine (free delayed EOD, paid
  real-time), (b) Quandl/Nasdaq Data Link, (c) IB API historical
  options data (free with account), (d) other. Default: IB API
  historical options (cheapest, already have account under OD-11).
  Decision gate: F4-ACT-02.

- **OD-38 (asymmetric quoter edge threshold).** How much model-vs-
  midpoint disagreement (in cents) justifies tighter posting on the
  edge side? Default: 2c. Decision gate: F4-ACT-04.

- **OD-39 (taker-imbalance cooldown).** After withdrawing a side due
  to detected adverse flow, how long before re-entering? Default: 30s.
  Decision gate: F4-ACT-16.

- **OD-40 (M0 historical data depth).** How many settled monthly
  Events are needed for M0 to be conclusive? Default: 4 Events
  (~4 months of data). Decision gate: F4-ACT-15.

---

## 10. F4 action detail

### F4-ACT-01 — Wave 0 adaptations for monthlies

**Type.** refactor | **Effort.** S | **Gaps.** new (monthlies pivot)

Fix ACT-08 settle resolver roll rule from FND-2 BD to FND-15 BD (per
live API finding in `state/digest_kalshi_research_2026-04-27.md`). Add
`KXSOYBEANMON` Kalshi block to `config/commodities.yaml` alongside the
existing `KXSOYBEANW` block. Verify ACT-04 ticker parser handles the
`KXSOYBEANMON-YYMMM` ticker format. Update ACT-01 capture target
configuration to include `KXSOYBEANMON` tickers.

**Code locations.** `engine/cbot_settle.py` (roll rule),
`config/commodities.yaml` (product config), `feeds/kalshi/ticker.py`
(parser verification), `feeds/kalshi/capture.py` (capture target).

**Tests.** Update `tests/test_cbot_settle.py` roll-rule assertions;
add `KXSOYBEANMON` ticker parsing tests; verify corridor adapter works
with monthly-spaced strikes.

### F4-ACT-02 — CME options chain ingest

**Type.** feature | **Effort.** L | **Gaps.** GAP-046, GAP-047, GAP-063

New module `feeds/cme/options_chain.py`. Pulls ZS soybean options
chain (calls + puts, all listed strikes, front 3 expiries) from the
chosen vendor (OD-37). Stores in-memory as structured arrays. Runs
put-call parity prune (GAP-047) to discard arbitrage-violating quotes.
Includes EOD settle pull for CBOT daily settlement prices.

**Code locations.** `feeds/cme/` (new package), `config/commodities.yaml`
(vendor config fields).

**Tests.** Chain pull with synthetic data; put-call parity prune
correctness; settle pull format validation.

### F4-ACT-03 — RND extractor pipeline

**Type.** feature+refactor | **Effort.** XL | **Gaps.** GAP-006,
GAP-036, GAP-037, GAP-038, GAP-041, GAP-042, GAP-043, GAP-044,
GAP-045, GAP-049, GAP-101, GAP-003

The core pricing deliverable. Five sub-stages:

1. **IV surface refactor** (GAP-042): change `state/iv_surface.py`
   signature from `atm(commodity) -> float` to
   `(commodity, strike, expiry) -> IV` grid. Absorbs F3 ACT-14.

2. **BL density extraction** (GAP-036): implement
   `f_T(K) = e^(rT) * d^2C/dK^2` on the smoothed IV surface.

3. **SVI fitter** (GAP-037, GAP-038): Gatheral SVI calibration per
   expiry with butterfly/calendar arb constraints.

4. **Figlewski tails** (GAP-041): piecewise-GEV tail attachment
   beyond the observed strike range.

5. **Bucket integration** (GAP-043, GAP-044, GAP-045): integrate the
   density over each Kalshi bucket `[l_i, u_i)`, normalize to sum-to-1,
   variance-rescale for non-co-terminal expiries. Output: per-bucket
   Yes-price vector with Greeks (GAP-101, GAP-003).

**Code locations.** `state/iv_surface.py` (refactor),
`models/rnd_pipeline.py` (new), `models/svi.py` (new),
`models/figlewski.py` (new), `models/base.py` (TheoOutput shape),
`validation/sanity.py` (sum-to-1 gate).

**Tests.** Analytical parity: BL on Black-Scholes call surface
recovers lognormal density. SVI fit reproduces known smile. Figlewski
tails integrate to expected probability mass. Bucket sum-to-1 within
tolerance. Non-co-terminal rescaling preserves total probability.

### F4-ACT-04 — Asymmetric quoter

**Type.** feature | **Effort.** L | **Gaps.** GAP-001 (partial),
GAP-002, GAP-022 (partial), GAP-023, GAP-029, GAP-145

New module `engine/quoter.py`. Implements:

- Reservation price: `r_i = model_fair_value_i - gamma * sigma^2 * (T-t) * q_i`
- Asymmetric posting: when `model_fair_value > kalshi_midpoint + edge_threshold`, tighten bid (buy cheap); when `model_fair_value < kalshi_midpoint - edge_threshold`, tighten ask (sell rich)
- Hard inventory bound `q in [-Q, +Q]`
- Min spread floor 4c each side (C10-79)
- Event-window widening integration with F4-ACT-06
- `post_only=True` always

This is NOT the full A-S/CJ HJB control loop from F1 ACT-19. It is
a simplified reservation-price quoter with asymmetric edge posting —
appropriate for the ~2-3 trades/bucket/day observed rate.

**Code locations.** `engine/quoter.py` (new), integrates with
`engine/pricer.py`, `state/positions.py`, `validation/sanity.py`.

### F4-ACT-05 — IBKR hedge leg

**Type.** feature | **Effort.** L | **Gaps.** GAP-102, GAP-103,
GAP-104, GAP-108

New module `hedge/ibkr.py`. Implements:

- Aggregate book delta: `Delta^port = sum_i q_i * Delta_i^K`
- ZS futures sizer: `N_ZS = -round(Delta^port / 5000)` (5000 bu/contract)
- Threshold trigger: fire hedge when `|Delta^port| >= 1` ZS contract equivalent
- IB Gateway connection via `ib_insync`
- ZS L1 price feed via Pyth (reuses existing Pyth infrastructure)
- Threshold-driven fire rate ~1-3/day

**Prerequisites.** IB account with CME futures permission (OD-11,
resolved). Paper-trading account for development.

### F4-ACT-06 — USDA event clock + pre-event protocol

**Type.** feature | **Effort.** M | **Gaps.** GAP-053, GAP-067 (partial),
GAP-019 (partial), new gap (settlement-gap protocol)

New module `engine/event_clock.py`. Implements:

- Static event calendar for soybean: WASDE (~12th of month),
  Crop Progress (Mon 4pm ET, Apr-Nov), Plantings (late Mar),
  Acreage (late Jun), Grain Stocks (quarterly)
- Pre-window pull-all: 30-60s before scheduled release, cancel all
  resting orders on affected series
- Size-down ladder: in 24h run-up, reduce posted size by 50% per
  6-hour block
- Post-event refit: after window closes, re-run RND pipeline on
  updated CME data, repost quotes

Consumes the `event_calendar[].vol_adjustment` YAML field that has
existed since the original config but never had a reader (theme 3.3
from gap register).

### F4-ACT-07 — Order pipeline

**Type.** feature | **Effort.** M | **Gaps.** GAP-132, GAP-133,
GAP-137, GAP-138

Extends `feeds/kalshi/orders.py` (already has order builder from
ACT-06) with REST endpoint bindings:

- `POST /portfolio/orders` (submit)
- `DELETE /portfolio/orders/{id}` (cancel)
- `PUT /portfolio/orders/{id}/amend` (amend price/size)
- `PUT /portfolio/orders/{id}/decrease` (reduce size)
- `POST /portfolio/orders/batch` (batch submit/cancel)
- Client-order-ID idempotency layer
- Amend-not-cancel for queue-priority preservation
- Local resting-book mirror

### F4-ACT-08 — Kill switch end-to-end

**Type.** feature+bugfix | **Effort.** M | **Gaps.** GAP-172,
GAP-174, GAP-178, GAP-179, GAP-180

Builds on Wave 0 ACT-11 kill-switch primitives. Implements:

1. Signed-delta breach trigger (from ACT-12 risk gates)
2. PnL drawdown trigger (from position store)
3. Hedge heartbeat fail (N=15s default)
4. Kalshi WS reconnect storm (K=5/min default; fixes GAP-180
   windowed counter bug)

Plus: structured logging via `structlog` (GAP-174); `SanityError`
policy (quote_drop default, consecutive -> market_suspend, GAP-179);
scheduler wiring for `risk_kill` / `quote_cancel` priorities (GAP-178).

### F4-ACT-09 — M0 backtest validator

**Type.** feature | **Effort.** XL | **Gaps.** GAP-146, GAP-147,
GAP-149, GAP-150

Backtest harness for validating the asymmetric quoter against
historical data. Includes:

- Replay engine: reads captured `KXSOYBEANMON` orderbook snapshots
  and trade prints from ACT-01 Phase 1a
- Fill simulator: simulates fills against the asymmetric quoter's
  resting orders
- Walk-forward runner: rolls through settled Events scoring
  model-implied prices against realized outcomes
- DuckDB+Parquet substrate for persistent storage
- Paper-trading adapter for sandbox testing on Kalshi demo API

M0 success criterion: the asymmetric quoter, simulated against
captured data, produces positive net P&L (spread capture minus fees
minus simulated hedge cost minus adverse selection) across 4+
settled monthly Events.

### F4-ACT-10 — Settlement-gap scenario harness

**Type.** feature | **Effort.** L | **Gaps.** GAP-112, GAP-113,
GAP-121

Scenario testing framework in `scenario/`. Named scenarios:

1. **WASDE-day**: simulated 3% gap on soybean futures within 30s of
   WASDE release. Validates F4-ACT-06 pre-event pull, measures P&L
   impact if quotes are not pulled in time.
2. **Weather-shock**: 5% gap from unexpected freeze/drought headline.
   Tests kill-switch trigger timing.
3. **Expiry-day**: liquidity collapse as Event approaches settlement.
   Tests mark-to-intrinsic behavior.
4. **CBOT-closed**: Friday 13:20 CT -> Sunday 19:00 CT regime.
   Tests StaleDataError handling and quote-pull behavior.

### F4-ACT-11 — Settlement-gap risk gate

**Type.** feature | **Effort.** M | **Gaps.** new (F4-specific)

Configurable per-Event risk gate that:

- Auto-widens spread in the run-up to settlement (wider than normal,
  proportional to time-to-settlement)
- Auto-reduces posted size as settlement approaches
- Auto-pulls all quotes if unrealized loss on the Event exceeds a
  configurable threshold
- Integrates with ACT-12 risk gates and F4-ACT-08 kill switch

This is the engineered mitigation for the settlement-gap risk
identified as the binding constraint in PREMISE.md.

### F4-ACT-12 — Settlement reconciler

**Type.** feature | **Effort.** L | **Gaps.** GAP-086, GAP-088,
GAP-090, GAP-091, GAP-099

Settlement lifecycle management:

- Settled-outcome poller: `GET /events/{ticker}` for resolved status
- Bucket-grid lifecycle: detect Event creation, activation, suspension, settlement
- Rule 13.1(d) outcome ingest: 11:59pm ET determination-day deadline
- CBOT lock-day handling: 7% limit-lock detection from settle stream
- Roll-day coordination with F4-ACT-01's updated roll calendar

### F4-ACT-13 — Reconciliation pipeline

**Type.** feature | **Effort.** L | **Gaps.** GAP-117, GAP-134,
GAP-135, GAP-136

Three-times-per-session reconciliation:

- Open recon: verify starting positions match EOD snapshot
- Intraday recon: verify fills against local book mirror
- EOD recon: full position/fill/balance/settlement comparison
- Fill ingestion from WS `fill` frames
- Per-bucket post-trade markout (1m/5m/30m) for adverse-selection
  measurement
- DuckDB+Parquet persistent store

### F4-ACT-14 — Live PnL attribution

**Type.** feature | **Effort.** M | **Gaps.** GAP-151, new
(F4-specific PnL decomposition)

Daily/weekly P&L dashboard decomposed into:

- **Spread P&L**: gross spread captured on round-trip fills
- **Model-edge P&L**: P&L attributable to model-vs-midpoint
  disagreement (the asymmetric edge)
- **Hedge slippage**: realized cost of delta-hedge trades on IBKR
- **Fees**: Kalshi maker/taker fees + IB commissions
- **Adverse selection**: markout-based measurement of informed flow
- **Capital cost**: opportunity cost of deployed capital

Per-market and aggregate. Feeds into kill-criteria monitoring
(KC-F4-02 through KC-F4-05).

### F4-ACT-15 — M0 spike notebook

**Type.** research | **Effort.** M | **Gaps.** new (M0 validation)

Jupyter notebook (NOT production code) that:

1. Pulls historical CME ZS options chain (front 3 expiries, EOD)
2. Pulls historical `KXSOYBEANMON` settled outcomes from ACT-01
   capture
3. Runs the F4-ACT-03 RND pipeline offline
4. For each settled Event, computes RND-implied bucket Yes-prices
5. Compares against realized resolution outcomes
6. Outputs: per-bucket accuracy table, aggregate miss rate, GO/NO-GO
   recommendation on KC-F4-01

This is the M0 gate. If RND-implied prices miss by >3c on >50% of
buckets across 4+ Events, the project halts.

### F4-ACT-16 — Taker-imbalance detector

**Type.** feature | **Effort.** M | **Gaps.** new (F4-specific
asymmetric defense)

From the `orderbook_delta` and `fill` WebSocket streams (ACT-05),
detect when adverse taker flow is hitting one side of the book
disproportionately. When detected:

1. Withdraw the side facing the flow (cancel resting orders on that
   side)
2. Re-enter after a configurable cooldown (OD-39, default 30s)
3. Log the event for post-trade adverse-selection analysis

Detection method: rolling window of signed fill volume (buys minus
sells). When the signed volume exceeds a configurable threshold
(default: 2 standard deviations from rolling mean), trigger
withdrawal on the receiving side.

---

## 11. F1 gap coverage analysis

How F4 actions map to the F1 gap register
(`audit_E_gap_register.md`):

### Gaps closed by F4

| Gap range | Topic | Closed by |
|---|---|---|
| GAP-001 (partial), GAP-002, GAP-003 | pricing-model | F4-ACT-04 (simplified, no HJB) |
| GAP-006 | pricing-model | F4-ACT-03 (RND replaces GBM) |
| GAP-019 (partial) | pricing-model | F4-ACT-06 (kappa consumer) |
| GAP-022 (partial), GAP-023, GAP-029 | pricing-model | F4-ACT-04 |
| GAP-036, GAP-037, GAP-038, GAP-041 | density | F4-ACT-03 |
| GAP-042, GAP-043, GAP-044, GAP-045 | density | F4-ACT-03 |
| GAP-046, GAP-047, GAP-049 | density/data-ingest | F4-ACT-02 |
| GAP-053 (partial), GAP-067 (partial) | data-ingest | F4-ACT-06 |
| GAP-063 | data-ingest | F4-ACT-02 |
| GAP-086, GAP-088, GAP-090, GAP-091, GAP-099 | contract | F4-ACT-12 |
| GAP-101 | hedging | F4-ACT-03 (Greeks in TheoOutput) |
| GAP-102, GAP-103, GAP-104, GAP-108 | hedging | F4-ACT-05 |
| GAP-112, GAP-113, GAP-121 | hedging/inventory | F4-ACT-10 |
| GAP-117, GAP-134, GAP-135, GAP-136 | oms | F4-ACT-13 |
| GAP-132, GAP-133, GAP-137, GAP-138 | oms | F4-ACT-07 |
| GAP-145 | oms | F4-ACT-04 (spread floor) |
| GAP-146, GAP-147, GAP-149, GAP-150 | backtest | F4-ACT-09 |
| GAP-151 | backtest | F4-ACT-14 |
| GAP-172, GAP-174, GAP-178, GAP-179, GAP-180 | observability | F4-ACT-08 |

**Total: ~50 F1 gaps closed** (out of 185), focused on the blocker
and high-major items that are essential for a working trading system.

### Gaps explicitly deferred beyond F4

| Gap range | Topic | Reason |
|---|---|---|
| GAP-004, GAP-021, GAP-050 | pricing-model, density | Multi-asset HJB / cross-bucket covariance — overengineered for F4 trade frequency |
| GAP-008-012 | pricing-model | Heston/Bates/JD — deferred until RND empirically underprices tails |
| GAP-013-016, GAP-024-027, GAP-030-035 | pricing-model | Microstructure, alpha overlays, practitioner signals — Wave 2+ in future plan |
| GAP-017, GAP-048 | density | Measure overlay — post-M0, only if systematic bias detected |
| GAP-039, GAP-040 | density | SABR/BP fallback — only if SVI fails on >25% of fits |
| GAP-051, GAP-052 | data-ingest | CME MDP 3.0 / MBP-MBO — not needed; EOD chain sufficient |
| GAP-054-062, GAP-064-070 | data-ingest | Weather, SAm, COT, FX, cash bids, Pyth hardening — signal alpha, deferred |
| GAP-084-085, GAP-092-098, GAP-100 | contract | Wash-trade, RFQ, member/role, Kalshi residuals — post-live |
| GAP-105-107, GAP-109-111, GAP-114-115 | hedging | Option hedge, SPAN, topology, cross-asset — not needed for ZS futures hedge |
| GAP-116, GAP-118-120, GAP-122-130 | inventory | Already closed by Wave 0 (ACT-09, ACT-12) or deferred (capital allocator, forward curve) |
| GAP-131 | oms | Already closed by Wave 0 (ACT-05) |
| GAP-139-144 | oms | Queue-reactive, FIX, open-order cap — post-live |
| GAP-152-155 | backtest | Already closed by Wave 0 (ACT-10, fees) or deferred (survivorship, turnover) |
| GAP-156-170 | strategy | All signal/strategy alpha — deferred beyond F4 |
| GAP-171, GAP-173 | observability | Already closed by Wave 0 (ACT-11, ACT-01) |
| GAP-175-177, GAP-181-185 | observability | Prometheus/Grafana, topology, calibration — post-live |

---

## 12. Effort summary

| Wave | Actions | S | M | L | XL | Total effort |
|---|---|---|---|---|---|---|
| F4 Wave 1 | 4 | 1 | 1 | 1 | 1 | ~S+M+L+XL |
| F4 Wave 2 | 6 | 0 | 3 | 2 | 0 | ~3M+2L |
| F4 Wave 3 | 6 | 0 | 2 | 3 | 1 | ~2M+3L+XL |
| **Total** | **16** | **1** | **6** | **6** | **2** | |

The critical path runs through F4-ACT-03 (RND pipeline, XL) in Wave 1
and F4-ACT-09 (M0 backtest, XL) in Wave 3. These two actions are the
largest and most complex pieces of new code.

---

*End of `audit_F4_refactor_plan_asymmetric_mm.md`.*
