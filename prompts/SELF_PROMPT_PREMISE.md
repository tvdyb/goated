# Strategic premise — F4 — `goated`

This is the canonical strategic premise for the project as of
2026-04-27, post-Wave-0-NO-GO and post-pivot. It supersedes F1
(edge-driven A-S/CJ MM on soybean weeklies) and F3 (LIP-pool-share
farming). The build-stack constructor and every downstream
execution / review prompt must read this file on entry and apply
its non-negotiables.

---

## What the project is now building (F4)

**Asymmetric market-making on Kalshi commodity monthly markets,
priced against an empirical risk-neutral density (RND) extracted
from CME options on the underlying futures, hedged on Interactive
Brokers where a hedge instrument exists.**

Quote two-sided around model-derived fair value, NOT around Kalshi's
midpoint. Skew quote tighter on the side where Kalshi's midpoint
disagrees with model fair value (capturing implied edge in addition
to spread). Withdraw the side facing adverse taker flow within
seconds. Withdraw the entire book during scheduled news windows
(USDA WASDE, Crop Progress, Quarterly Stocks, Acreage, Plantings).
Hedge residual delta on CBOT futures via IBKR for series where an
IB-accessible hedge exists.

The strategy is NOT:
- Pure LIP rebate farming (the friend's `mm-setup-main` strategy —
  excluded because we want a model-edge play, not a pool-share
  harvester).
- Pure A-S / CJ optimal control (overengineered for the trade
  frequency).
- High-frequency with microsecond budgets (irrelevant at observed
  trade rates).
- Multi-account / FIX 4.4 / hot-standby topology (out of scope).
- Full alpha layer (no crush spread, no calendar spread, no
  cross-sectional momentum, no weather signals beyond pre-event
  widening).
- Soybean weeklies (`KXSOYBEANW` is not LIP-eligible AND has thin
  monthly-grade liquidity; the audit-era target was wrong).

---

## Target series, in build priority order

Each target is a Kalshi `KX*MON` (monthly) market series with
half-line "above-strike" markets at uniform 5¢ spacing.

| Priority | Series | Hedge instrument | Status |
|---|---|---|---|
| 1 | `KXSOYBEANMON` | CBOT ZS futures via IBKR | Build first; cleanest infrastructure alignment. |
| 2 | `KXCORNMON` | CBOT ZC futures via IBKR | Same shape as soy; second target. |
| 3 | `KXSUGARMON` | ICE-EU sugar; not IB-accessible by default | Run un-hedged or skip. |
| 4 | `KXNICKELMON` | LME nickel; not IB-accessible | Run un-hedged. |
| 5 | `KXLITHIUMMON` | CME lithium hydroxide (thin) | Probably un-hedged. |

Series excluded:
- Weeklies (`KXSOYBEANW`, `KXCORNW`, `KXLITHIUMW`, `KXNICKELW`,
  `KXCOCOAW`): too thin, near-zero or zero trades/7d.
- `KXCOFFEEMON`: existing tight quotes (1¢ spread); someone is
  already MMing tight, no room to compete.
- `KXWHEATW`, `KXCORNW`: thin spreads with low flow.

Once the soy + corn pipeline works, additional series are config-
only additions (CME options chain ingest + per-series fair-value
calibration) at marginal engineering cost.

---

## Realistic economic target

**$20-35k/year net** for a focused operation across the 5 target
series, conditional on:

1. The CME-implied RND being meaningfully more accurate than
   Kalshi's quoted midpoints (the M0 test).
2. Settlement-gap losses being managed (the binding constraint —
   USDA prints can vaporize 42¢ spreads in a minute).
3. Capital deployment of $30-50k tied up in inventory + IB margin.

Per-series gross expectation:
- Soy monthly: ~$8-10k/year gross at 1 round-trip/bucket/day,
  ~50% spread capture, 10 strikes per Event, 12 Events/year.
- Corn monthly: similar, ~$7-9k/year gross.
- Sugar monthly: smaller, ~$3-5k/year (un-hedged risk premium
  reduces realized edge).
- Nickel + lithium monthly: ~$2-4k/year each; thin.

**The numbers above are estimates, not promises.** The M0 spike
will be the first numerical reality check. If M0 returns
no-edge-found on soy, the entire F4 thesis is invalidated and the
project pivots or shuts down.

---

## Settlement-gap risk — the binding constraint

A 42¢ Kalshi monthly spread is real edge IF you can avoid being
caught with adverse inventory when the underlying moves. The
dominant risk events:

- **USDA WASDE** (monthly, ~12:00 ET on release day). Soybean and
  corn futures can move 2-5% in 30 seconds.
- **Crop Progress** (Mondays 16:00 ET during growing season).
- **Quarterly Stocks** / **Acreage** / **Plantings**. Lower-frequency
  but high-impact.
- **Weather** (unscheduled). Drought / freeze / flood news.
- **Shipping events** (Mississippi River close, Panama Canal
  restriction).

Engineered mitigations:
- **Pre-window pull-all**: 30-60 seconds before any scheduled
  release on the calendar, cancel every resting order on every
  affected series. Hold withdrawn for the duration of the volatile
  window (typically 5-15 minutes post-release).
- **Size-down ladder**: in the 24-hour run-up to a scheduled
  release, reduce posted size by 50% per 6-hour block.
- **Wide-out widening**: spread cap doubles inside the window.
- **Hedge tightening**: on the IB side, reduce hedge threshold so
  even small Kalshi inventory triggers immediate ZS / ZC futures
  hedging during volatile periods.
- **Hard kill**: if any single Kalshi position's unrealized P&L
  exceeds X% of capital (configurable, default 5%), kill switch
  fires and cancels everything across all series.

The settlement-gap gate is the single most important non-negotiable
risk control in F4.

---

## Kill criteria (project-level)

- **KC-F4-01.** *M0 fails.* RND-implied bucket prices, after a
  measure overlay, miss realized Kalshi-resolution outcomes by
  more than ~3¢ on >50% of buckets across 4+ settled monthly
  Events on `KXSOYBEANMON`. Strategy is dead; pivot or exit.
- **KC-F4-02.** *Settlement-gap losses exceed gross spread.* If
  realized P&L from settlement-gap events exceeds the cumulative
  spread captured between events for two consecutive months, the
  risk control is insufficient and the strategy is uneconomic.
- **KC-F4-03.** *Capital efficiency below opportunity cost.*
  Annualized net P&L on deployed capital below 5% for six
  consecutive months. Strategy is not worth the operational risk.
- **KC-F4-04.** *Hedge-leg drag.* Monthly IB commissions plus ZS /
  ZC slippage exceed monthly Kalshi spread capture on hedgeable
  series. Hedge configuration needs to widen or strategy is mis-
  specified.
- **KC-F4-05.** *Adverse-selection dominance.* Realized markout on
  filled quotes (averaged weekly) exceeds 60% of the captured
  spread for four consecutive weeks. Quote logic is mis-specified
  or the model edge is illusory.

---

## Non-negotiables (inherited from `README.md`)

- No `pandas` in the hot path; no Python loops over markets or
  strikes.
- No Monte Carlo in the hot path; MC is for offline validation only.
- No silent failures: stale Pyth publishers, out-of-bounds IV, feed
  dropouts → raise, don't publish.
- `scipy.special.ndtr` over `scipy.stats.norm.cdf`.
- `numba.njit` on all hot-path math.
- Theo for `KXSOYBEANMON` is bucket Yes-price under the Kalshi
  half-line decomposition (per ACT-13).
- Synchronous main loop; `asyncio` for I/O only.
- Every order placed is `post_only=True`. Crossing the spread
  negates any economic edge.
- The fail-safe pattern at `engine/pricer.py:62-75` and
  `validation/sanity.py:38-68` is the template every new module
  follows.

---

## What's already built (Wave 0 — verified-complete)

All 16 actions verified-complete with ~611 tests passing as of
2026-04-27. Specifically:

- ACT-01 forward-capture tape sentinel (Phase 1a; Phase 1b deferred)
- ACT-02 commodities.yaml fill-in
- ACT-03 Kalshi REST client + RSA-PSS signing + rate limiter
- ACT-04 ticker schema + bucket grid + Event puller
- ACT-05 Kalshi WS multiplex (orderbook delta + fill + user orders)
- ACT-06 order builder + tick rounding + quote-band gate
- ACT-07 24/7 calendar + Friday-holiday roll
- ACT-08 settle resolver + roll calendar + FND
- ACT-09 position store + per-Event signed exposure
- ACT-10 fee model + round-trip cost
- ACT-11 kill-switch primitives (DELETE batch + group trigger)
- ACT-12 risk gates (delta cap + per-Event + max-loss)
- ACT-13 corridor adapter (corridor decomposition on existing GBM)
- ACT-LIP-POOL pool data ingest (will be repurposed in F4 to ingest
  CME settle data instead — adapter only)
- ACT-LIP-SCORE score tracker (not used in F4; kept for optionality)
- ACT-LIP-VIAB viability framework (not used in F4)

All Wave 0 actions are tagged `verified-complete` in
`state/dependency_graph.md` and gated through `09_WAVE_GATE.md`.
The Wave 0 gate produced a NO-GO decision for the F3 (LIP) thesis;
F4 thesis is the response.

---

## What still needs to be built for F4

In rough order:

1. **CLAUDE.md** for the codebase (operator-facing reference).
2. **F4 plan** formalized as `audit/audit_F4_refactor_plan_asymmetric_mm.md`.
3. **M0 spike notebook** validating RND-vs-Kalshi edge on one
   settled `KXSOYBEANMON` Event. Pure research.
4. **CME options chain ingest** for ZS, ZC. Daily EOD pull.
5. **RND extractor** (Breeden-Litzenberger → SVI calibration with
   butterfly + calendar arb constraints → Figlewski piecewise-GEV
   tails → bucket integrator on Kalshi half-line strike grid).
6. **Asymmetric quoter**: post on the side where model fair
   diverges from Kalshi mid by more than fee + buffer. Skip the
   side where model agrees with Kalshi.
7. **Taker-imbalance detector**: rolling-window classification of
   WS `trade` channel to detect directional flow. Triggers
   one-sided withdrawal.
8. **Settlement-gap risk gate**: pre-window pull-all + size-down
   ladder + hard kill. Wired into ACT-11 / ACT-12 / ACT-24.
9. **IBKR hedge leg**: IB Gateway + `ib_insync` + ZS / ZC futures
   client. Threshold-driven hedge fire (3-5 contracts of net delta).
10. **Settlement-gap scenario harness**: replay USDA-day events
    against the system to validate the gate.
11. **M0 backtest validator**: live system scored against settled-
    week outcomes. Continuous validation, not one-shot.
12. **Live PnL attribution**: per series, per market, per hour.
    LIP-aware → CME-edge-aware (rebate component is zero in F4;
    spread + implied-edge components dominate).

---

## Relationship to existing artifacts

- **F1 plan** (`audit/audit_F_refactor_plan.md`) — reference for
  the original 59-action ambitious build. F4 is a focused subset
  (~12-15 actions on top of Wave 0). When in doubt about
  algorithmic detail (e.g., SVI calibration parameters, Figlewski
  paste-points), F1's gap register cites the relevant research.
- **F3 plan** (`audit/audit_F3_refactor_plan_lip.md`) — superseded.
  The infrastructure built under F3's Wave 0 carries forward; the
  Wave-1+ design does not.
- **Friend's `mm-setup-main`** — reference for: RSA-PSS signing
  pattern (already in ACT-03), anti-arb logic (worth porting if
  we ever do cross-strike YES + NO posting; not the F4 default
  posture), cancel-zero-reward sweeper pattern (useful as a
  general hygiene tool).
- **Wave 0 state files** in `state/` — the canonical record of
  what's actually built. Trust these over any plan document.
- **Audit cartography** (`audit/audit_A_cartography.md`) — module
  inventory and red flags. Reference for understanding the
  pre-Wave-0 codebase shape.

---

*This file is updated only by the build-stack constructor and by
any future strategic-pivot phase. Execution prompts and review
prompts read it but do not modify it.*
