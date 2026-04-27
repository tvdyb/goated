# Audit F — Sequenced Refactor Plan (Phase F synthesis)

## 1. Executive summary

The Phase E gap register carries 185 distinct gaps (57 blocker, 83 major,
33 minor, 12 nice-to-have) sized over four effort tiers. Closing the
register turns the existing single-name GBM theo engine into a working
`KXSOYBEANW` market-maker with hedge, inventory, kill-switch, and
backtest. This plan groups those 185 gaps into 59 actions
(`ACT-01`–`ACT-59`) sequenced into five waves: Wave 0 (13 actions) is
the minimum tradeable surface — sign, throttle, send, capture, cap;
Wave 1 (13) brings structural correctness — IV-surface signature change,
CME chain ingest, BL/SVI/Figlewski RND pipeline, A–S/CJ control loop,
hedge-leg foundation, settlement, reconciliation, kill switch end-to-end,
scenario harness, and the M0 backtest pipeline; Wave 2 (12) lifts pricing
and quoting quality — Heston/Bates SV, per-bucket matrix skew, vertical
spread option-hedge, microstructure (G–M / Kyle / OFI), alpha overlays,
pre-event widening, measure tilt, queue-reactive quoting; Wave 3 (11)
adds signal and strategy alpha — weather, satellite, SAm, FX, COT,
crush/calendar/bean–corn, TSMOM/carry/momentum, event-driven signals,
per-trade indicators, oilshare/RFS, pricing overlays; Wave 4 (10)
hardens the system — observability, topology, calibration substrate,
backtest realism, Pyth hardening, forward-curve, cross-asset hedge,
Kalshi residuals, FIX, and operational extras. Every action cites at
least one C-id and one code location. Eight project-level kill criteria
from C10 plus eight audit-derived ones (`KC-AUD-NN`) close the document.

## 2. Methodology

**Wave assignment.** Wave 0 is the minimum set of blockers that, taken
together, lets the system place a quote on Kalshi and not catch fire —
not the full blocker backlog. A blocker that depends on Wave 0 work
being done first is demoted to Wave 1. Wave 1 carries the rest of the
blockers plus the structural majors that other waves depend on. Wave 2
carries pricing- and quoting-quality work that assumes a complete Wave-1
surface. Wave 3 is additive alpha — signals, universe expansion, new
ingest. Wave 4 is hardening — observability, topology, backtest realism.
Within a wave, dependencies between actions are explicit; everything not
on a dependency edge is parallelisable.

**Action grouping rule.** Gaps cluster into one action when (a) they
share a code location or (b) their remediation lands the same dataclass /
module / endpoint binding, and (c) the work cannot be sensibly split
across PRs. The threshold for splitting was: two gaps go in the same
action only if the second one is implementable in the same PR by the
same engineer; otherwise they are split. Aim was 25–60 actions across
5–12 per wave; result is 59 actions with waves of 13/13/12/11/10.

**Effort tiers.** S ≤ 1 ed (≲100 LoC); M 1–3 ed (~100–500); L 1–2 ew
(~500–2,000); XL > 2 ew (multi-module or new external integration).
Action effort is the worst gap effort within the action; bumped one
tier when the action spans more than five gaps (per brief).

**Type tags.** `refactor` for changes to existing module shapes /
contracts; `feature` for new modules or new external integrations;
`bugfix` for in-place corrections of incorrect behaviour. Many actions
mix types; the dominant type wins, with secondary type called out in
the prose.

**Citations.** Every action cites at least one C-id (representative,
not exhaustive — see the gap register for the full list) and at least
one code location (or `n/a — no module` with a cartography pointer).
Where this plan refers to "the register" it means
`audit/audit_E_gap_register.md`.

---

## 3. Wave 0 — Minimum tradeable surface

Goal: the engine can sign in to Kalshi, pull a bucket grid, place a quote
inside a hard delta cap, get killed if anything breaks, and forward-capture
every byte. Pricing remains the existing GBM density routed through a
corridor adapter — known to be wrong, but tradeable behind wide spreads
plus hard caps. The proper RND pipeline lands in Wave 1.

| ID | Summary | Type | Severity | Effort | Gaps closed | Deps | Dependents |
|---|---|---|---|---|---|---|---|
| ACT-01 | Forward-capture tape sinks (Kalshi WS+ticker+trade+fill, CME L1+EOD chain, fundamentals+weather) to S3+Parquet | feature | blocker | XL | GAP-148, GAP-173 | — | ACT-26 |
| ACT-02 | Soybean commodities.yaml fill-in (`cme_symbol`, Kalshi block, fees, position cap, bucket-grid source) | feature | blocker | S | GAP-100 | — | ACT-03, ACT-08, ACT-10 |
| ACT-03 | Kalshi REST client foundation: `httpx.AsyncClient` + RSA-PSS-SHA256 signing + tiered token-bucket pacer + 429 backoff | feature | blocker | XL | GAP-071, GAP-072, GAP-073 | ACT-02 | ACT-04, ACT-05, ACT-11, ACT-22 |
| ACT-04 | Series→Event→Market→Yes/No ticker schema, parser/formatter, `GET /events/{ticker}` puller, `Event`/`Bucket` data structures (MECE check, open-tail handling) | feature | blocker | M | GAP-074, GAP-075, GAP-079 | ACT-03 | ACT-06, ACT-09, ACT-13, ACT-21 |
| ACT-05 | Kalshi WS multiplex consumer (`orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`) | feature | blocker | L | GAP-131 | ACT-03 | ACT-22, ACT-23 |
| ACT-06 | Order builder + types/TIFs/flags (`limit/market`, `FOK/GTC/IOC`, `post_only/reduce_only/buy_max_cost/STP`) + `[$0.01,$0.99]` quote-band gate + `$0.01` tick rounding | feature | blocker | M | GAP-080, GAP-081, GAP-082 | ACT-04 | ACT-22 |
| ACT-07 | `KXSOYBEANW` 24/7 trading-session calendar + Friday-holiday Rule 7.2(b) roll | bugfix+feature | blocker | M | GAP-087, GAP-089 | — | ACT-18 |
| ACT-08 | CBOT settle resolver (Rule 813 ~1:20pm CT VWAP) + `ZSK26` roll calendar + soybean FND (T-2 BD) + `kalshi_reference_price_mode` config field | feature | blocker | M | GAP-076, GAP-077, GAP-078 | ACT-02 | ACT-13, ACT-21 |
| ACT-09 | `state/positions.py`: per-bucket inventory store + per-Event signed-dollar exposure + Rule 5.19 max-loss accounting | feature | blocker | L | GAP-116, GAP-119, GAP-083 | ACT-04 | ACT-12, ACT-19, ACT-23 |
| ACT-10 | Kalshi taker fee `⌈0.07·P(1−P)·100⌉/100` + 25% maker rate + round-trip cost subtraction | feature | blocker | M | GAP-007, GAP-152 | ACT-02 | ACT-19, ACT-26 |
| ACT-11 | Kill-switch primitives — `DELETE /orders/batch` + `POST /order-groups/{id}/trigger` endpoint bindings | feature | blocker | M | GAP-171 | ACT-03 | ACT-24 |
| ACT-12 | Aggregate book-delta cap + risk-gating stage J (block-on-breach) + Milestone-2 quoter contract (≥4¢ each side, amend-not-cancel) | feature | blocker | L | GAP-118, GAP-120, GAP-145 | ACT-09 | ACT-19, ACT-25 |
| ACT-13 | Bucket Yes-price vector via `D(ℓᵢ)−D(uᵢ)` corridor decomposition adapter on existing GBM `P(S_T>K)` + bucket integration `value_i = ∫_ℓ^u f_T dx` + sum-to-1 gate in `validation/sanity.py` | refactor+feature | blocker | M | GAP-005, GAP-043, GAP-044 | ACT-04, ACT-08 | ACT-17, ACT-19 |

**ACT-01.** Forward-only capture is the only Wave-0 item that has no
prerequisite and is the only one whose absence destroys an irreplaceable
asset (one Kalshi day uncaptured = one Kalshi day lost forever). Cited
C09-23/24/62/63; today nothing writes a Kalshi tape (`feeds/__init__.py`
is empty and the cartography records no S3 sink at lines 108-115).
Sequenced first so capture starts running while the rest of Wave 0 lands.

**ACT-02.** Cited C07-15/21/112 and C03-87. The `soy` block at
`config/commodities.yaml:58-60` is `stub: true` only and every consumer
keys off this. One config edit unblocks ACT-03, ACT-08, and ACT-10.

**ACT-03.** Cited C07-07/87/92/93/95-101 and C09-01-C09-18. Cartography
Red Flag 2 (`audit_A_cartography.md:243-245`) and Red Flag 3 (the
declared-but-unused `httpx`/`structlog`/`python-dateutil`/`pytz`) point
straight at this gap. Tier choice (per Appendix B.7.5) folds in here as
a note: assume Standard tier (default 10 tokens / s, cancel discounted
to 2) until a Premier+ contract exists.

**ACT-04.** Cited C07-01/02/03/05/06/07/25-31/35/36/38 plus C08-100.
Bucket grid has no producer today; the parser is a clean greenfield.
Edge-inclusivity rule (Appendix B.2.7) folds in here: adopt `[ℓ, u)` per
C07-32 and document.

**ACT-05.** Cited C07-93, C09-13, C08-110. The repo's only WS consumer
is `feeds/pyth_ws.py:1-145`; this action duplicates that pattern under
Kalshi-specific frame schemas. Sequenced before Wave-1 ACT-22 because
`user_orders` and `fill` frames are needed to drive the order pipeline.

**ACT-06.** Cited C07-37/44/45/49-52/67, C09-09. `validation/sanity.py:
53-57` clamps `[0,1]` (correct for probability, wrong for venue quote);
this action lifts the gate to `[0.01, 0.99]` and adds tick rounding.
Quote-band ownership question (Appendix B.4.4) is resolved here: keep
the gate in `validation/sanity.py` next to the existing clamp, parametrised
by a contract-keyed venue lookup.

**ACT-07.** Cited C07-108/81/22. Currently `engine/event_calendar.py:30-
38` registers WTI only (Sun 18:00 ET → Fri 17:00 ET) — explicitly *wrong*
for a 24/7 product. Sequenced separately from ACT-18 because USDA event
clock (ACT-18) builds on top.

**ACT-08.** Cited C07-14/15/16/17/18/19/20/21/24/112. The "single largest
pricing unknown" per Phase 7 is the Appendix-A reference-price mode;
this action lands the loader interface even if the Appendix value is
TBD. Note: `ZSK26` does not appear anywhere in the repo today.

**ACT-09.** Cited C02-03/07, C09-76, C07-53/54. Foundational state
surface; everything inventory-side hangs off it. New module per
cartography pointer at `audit_A_cartography.md:213-231`.

**ACT-10.** Cited C08-90/91/93, C04-08/09. One closed-form formula plus
a config block; folds into the existing pricer signature with no shape
change. Wave-0 because every gross-edge number overstates by ≥250 bps
without it.

**ACT-11.** Cited C09-71/72, C10-79. Just two endpoint bindings on top
of ACT-03. Full kill-switch (four triggers + transport + producers) is
ACT-24 in Wave 1.

**ACT-12.** Cited C08-88/109, C02-91, C10-79. Lands the `validation/
portfolio.py` module the Appendix B.5.9 question is asking about
(answer: new module, not an extension of `sanity.py`). The Milestone-2
quoter contract from C10-79 lands here because without it the surface
isn't a recognisable market-maker.

**ACT-13.** Cited C08-04/08/13/103, C07-32/39/40, C10-01. Lets the
existing `models/gbm.py` price emit a Yes-price-per-bucket vector via
two `D(K)` calls subtracted. Provides the *minimal* tradeable pricing
surface — known to be wrong (theoretical density not market-implied —
GAP-006) but sufficient for sandbox bring-up. Sum-to-1 gate question
(Appendix B.2.10) is resolved here as soft-then-hard: log+widen during
M0–M2, raise once Milestone-3 lands.

**Alternative ordering.** ACT-17 (proper RND pipeline) could plausibly
sit in Wave 0 to land the right pricing surface before any quote goes
out. Not chosen because (a) ACT-17 depends on ACT-16 (CME chain ingest,
XL effort) and (b) Wave 0's purpose is the minimum tradeable surface,
not the right one. Wide-spread quoting on a corridor adapter inside
hard caps is a defensible interim posture; the kill-switch absorbs the
risk.

---

## 4. Wave 1 — Structural correctness

Goal: every remaining blocker plus the structural majors that other waves
depend on. After this wave the system has the right RND, the right
control loop, a working hedge leg, settlement, full reconciliation,
end-to-end kill switch, scenario harness, and the M0 backtest pipeline.

| ID | Summary | Type | Severity | Effort | Gaps closed | Deps | Dependents |
|---|---|---|---|---|---|---|---|
| ACT-14 | `state/iv_surface.py` signature change to `(commodity, strike, expiry) → IV` grid | refactor | blocker | L | GAP-042 | — | ACT-16, ACT-17, ACT-27 |
| ACT-15 | `TheoOutput` shape change: add `bid/ask/spread`, per-bucket Greeks (Δ, Γ, vega) | refactor | blocker | M | GAP-003, GAP-101 | — | ACT-19, ACT-20 |
| ACT-16 | CME ingest stack: MDP 3.0 / Databento client + ZS option-chain pull + EOD settle pull + put-call parity prune + MBP/MBO order-book reconstruction | feature | blocker | XL | GAP-046, GAP-047, GAP-051, GAP-052, GAP-063 | ACT-14 | ACT-17, ACT-30, ACT-45, ACT-46 |
| ACT-17 | BL identity `f_T = e^(rT)·∂²C/∂K²` + SVI fitter + butterfly/calendar arb constraints + Figlewski piecewise-GEV tails + variance rescaling for non-co-terminal weeks + CBOT weekly/SDNC expiry table | refactor+feature | blocker | XL | GAP-006, GAP-036, GAP-037, GAP-038, GAP-041, GAP-045, GAP-049 | ACT-13, ACT-14, ACT-16 | ACT-19, ACT-26, ACT-27, ACT-28, ACT-29, ACT-32, ACT-33, ACT-36 |
| ACT-18 | USDA WASDE/Crop Progress/FAS ESR/FGIS/Plantings/Acreage/Grain Stocks event-clock + multi-zone holiday/session calendars (CT/ET/ART/UTC) | feature | blocker | L | GAP-053, GAP-067 | ACT-07 | ACT-32, ACT-34, ACT-41, ACT-42, ACT-47 |
| ACT-19 | Avellaneda–Stoikov / Cartea–Jaimungal control loop: `r = S − γσ²(T−t)q` reservation price + GLFT asymptotic ask/bid + `q ∈ [−Q, +Q]` hard inventory bound + practitioner truncating risk layer | feature | blocker | XL | GAP-001, GAP-002, GAP-022, GAP-023, GAP-029 | ACT-09, ACT-10, ACT-15, ACT-17 | ACT-25, ACT-27, ACT-28, ACT-31, ACT-32, ACT-45, ACT-49, ACT-52, ACT-55 |
| ACT-20 | Hedge-leg foundation: aggregate book delta `Δ^port = Σᵢ qᵢΔᵢᴷ` + ZS-futures sizer (N_ZS=5,000) + `\|Δ^port\|≥1` threshold trigger + FCM client (IB/AMP/Tradovate) + CME L1 second feed | feature | blocker | XL | GAP-102, GAP-103, GAP-104, GAP-108 | ACT-15 | ACT-25, ACT-29, ACT-56 |
| ACT-21 | Settlement & lifecycle: settlement reconciler + Klear DCO interaction + Rule 13.1(d) outcome poller + Rule 7.2(a)/(b) listener + bucket-grid week-stable vs intraweek-recentre listener + CBOT 7%-of-price daily limit + lock-day handling | feature | blocker | XL | GAP-086, GAP-088, GAP-090, GAP-091, GAP-099 | ACT-04, ACT-08, ACT-22 | ACT-37, ACT-57 |
| ACT-22 | Order pipeline: `POST /portfolio/orders` + `DELETE /portfolio/orders/{id}` + amend/decrease/batch + idempotency (client-order-ID dedupe) + amend-not-cancel queue-priority preservation + local resting-book mirror + queue-position cache | feature | blocker | L | GAP-132, GAP-133, GAP-137, GAP-138 | ACT-06 | ACT-21, ACT-23, ACT-34, ACT-35, ACT-38, ACT-58 |
| ACT-23 | Reconciliation pipeline: 3x-per-session reconciler (open / intraday / EOD) + single recon table keyed `(event_ticker, ts, side)` + DuckDB+Parquet persistent store + fill ingestion + `dX = (S+δᵃ)dNᵃ − (S−δᵇ)dNᵇ`, `dq = dNᵇ − dNᵃ` cash-and-inventory dynamics + per-bucket post-trade markout (1m/5m/30m) | feature | blocker | L | GAP-117, GAP-134, GAP-135, GAP-136 | ACT-09, ACT-22 | ACT-24, ACT-30, ACT-34, ACT-50, ACT-52, ACT-59 |
| ACT-24 | Kill switch end-to-end: four triggers (signed-delta breach, intraweek PnL drawdown, CME hedge-heartbeat fail N s, Kalshi WS reconnects > K/min) + windowed reconnect counter + scheduler producer wiring (`risk_kill`/`quote_cancel` priorities) + structured logging via `structlog` + `SanityError` publish-boundary policy | feature+bugfix | blocker | L | GAP-172, GAP-174, GAP-178, GAP-179, GAP-180 | ACT-11, ACT-23 | ACT-50, ACT-51 |
| ACT-25 | Scenario harness: WASDE-day P&L scenario + weather-shock 3-5% gap (Bates-SVJ) + expiry-day liquidity-collapse mark-to-intrinsic + limit-locked Friday hedge-leg unwind (discrete-jump P&L) + CBOT-closed regime detector | feature | blocker | L | GAP-112, GAP-113, GAP-121 | ACT-12, ACT-19, ACT-20 | ACT-53 |
| ACT-26 | Backtest M0 pipeline: backtest harness (replay engine, fill simulator, walk-forward runner, attribution) + Milestone-0 historical CME chain → SVI → Figlewski → score-vs-settled-Kalshi-week + sandbox demo + paper-trading layer + DuckDB+Parquet substrate adoption | feature | blocker | XL | GAP-146, GAP-147, GAP-149, GAP-150 | ACT-01, ACT-10, ACT-17 | ACT-53 |

**ACT-14.** The public reader `state/iv_surface.py:atm(commodity, *,
now_ns) -> float` cannot grow strike or expiry parameters without a
signature change. Cited C02-51, C06-08, C08-16. Sequenced first in
Wave 1 because ACT-16, ACT-17, and the SV models in ACT-27 all bind
to its new shape.

**ACT-15.** Cited C02-02/05/25/26, C08-42, C08-71/72/75/76. `models/
base.py:44-52` defines `TheoOutput(strikes, probabilities, as_of_ns,
source_tick_seq, model_name, params_version)` — no bid/ask, no Greeks.
Resolves Appendix B.5.4: Greeks live in `TheoOutput`, not in a parallel
`engine/greeks.py`. Sequenced parallel to ACT-14 because the changes
are at different module boundaries.

**ACT-16.** Cited C03-01/02/08, C06-01/10/11/12/82, C08-15, C08-50,
C09-29/54. The cartography records no `feeds/cme/` and no Databento
client. XL because of the SBE/FIX or vendor-redistribution work.
Question of Pyth-vs-Databento ingest source for ZS (Appendix B.3.1)
folds in here as a noted decision: assume CME MDP 3.0 via Databento
because Pyth Hermes does not surface MBP/MBO depth.

**ACT-17.** Cited C08-05/11/17/18/22/26-33/101, C10-02. Closes the
"market-implied vs model-implied" epistemology gap (theme 3.2 of the
register) plus the no-RND-pipeline cluster. Bumped to XL because it
spans seven gaps and has integration overhead (BL → SVI → constraints
→ Figlewski → bucket integration → variance rescaling → expiry table).
Note (Appendix B.2.6 / B.2.9): density refresh runs asynchronously in
a separate task with the pricer reading a cached RND, to keep
`pricer.reprice_market` inside its 50-µs budget.

**ACT-18.** Cited C03-53/54/55, C06-14-C06-23, C08-94/95, C09-39-C09-44,
C01-69-C01-73, C06-31/33, C07-81, C10-72/73. Only WTI session is
registered today; soy block has no `event_calendar[]`. Multi-zone
calendar work is the L tier; per-event `vol_adjustment` reader is
deferred to ACT-32 in Wave 2.

**ACT-19.** Cited C02-01/04/06/21-26/28-30/79/80/82, C08-40, C10-05.
The single biggest piece of pricing-side new code. XL because (a)
five gaps in scope, (b) introduces γ as a calibrated parameter with no
existing surface, (c) GLFT closed-form depends on the kₐ/kᵦ intensity
estimates that ACT-23 produces but does not require them at first
fit (placeholder values ship). Note: λᵢ(δ) calibration source
(Appendix B.1.7) ships as a stub here and is replaced by the
fill-driven calibrator in ACT-52.

**ACT-20.** Cited C08-71-76, C08-108, C09-28, C10-60-67, C10-80. XL
because of FCM client (IB/AMP/Tradovate). Vendor choice (Appendix
B.5.5) is open; assume IB to start because of broadest coverage,
parametrise the client behind an interface to allow the swap.

**ACT-21.** Cited C07-12/13/22/23/36/38/77/78/82/83/84/85/110/113,
C10-74. Bumped to XL by the ≥5-gap rule. CBOT lock detection
(Appendix B.7.8) lives here on the CME-L1 side because that is where
the limit price is observable; Pyth-derived lock detection is a
fallback diagnostic only.

**ACT-22.** Cited C07-44/45/52/67/92, C09-09/10/21/47, C10-47. Lands
the order-side wiring. Idempotency via client-order-ID resolves
Appendix B.7.6.

**ACT-23.** Cited C02-03/84, C08-43/52, C09-11/79/80, C10-50/79/80.
DuckDB+Parquet substrate (Appendix B.10.4 / B.8.9 answer) lands here.
Reconciliation cadence question (Appendix B.7.3) is resolved as
in-process scheduler-driven for open/intraday triggers, out-of-process
cron for the EOD reconciler.

**ACT-24.** Cited C09-73, C02-91, ambiguity A1 in `audit_D_observability.
md`. Resolves Appendix B.5.7 and B.7.7: kill switch is an in-process
supervisor task that calls Kalshi `DELETE /orders/batch` plus broker
IOC-cancel; not a separate watchdog process. Threshold values N
(hedge-heartbeat) and K (Kalshi WS reconnect/min) are
config-parametrised; defaults of N=15s and K=5/min ship as starting
points. SanityError fan-out (Appendix B.10.7): policy is `quote_drop`
default, with `market_suspend` after three consecutive errors on the
same Event.

**ACT-25.** Cited C08-89/109, C10-72/73/74. Three named scenarios live
in a new `scenario/` package (resolves Appendix B.8.8). Coupled to
ACT-21 (lock-day handler) for the limit-locked Friday scenario.

**ACT-26.** Cited C09-25/64/65/66/68, C10-77/78/82, C10-OQ-01/10. The
strategic gating milestone. XL because four hard prerequisites
(harness, M0 pipeline, paper-trading, DuckDB substrate) all need to
land together for any of them to be useful. M0 milestone tracker
(Appendix B.8.1) is a project-management item, not engineering.

---

## 5. Wave 2 — Quoting and pricing quality

Goal: pricing-model improvements that assume Wave 0+1 are done. Heston
SV / Bates SVJ replace constant-σ GBM; per-bucket matrix skew lands
once the Σᵢⱼ estimator is chosen; vertical-spread option hedge replaces
the futures-only delta hedge; microstructure (G–M, Kyle, OFI) feeds the
adverse-selection skew; alpha overlays land on top of A–S. After this
wave the engine quotes on the right model, with the right hedges, with
the right skew, around the right windows.

| ID | Summary | Type | Severity | Effort | Gaps closed | Deps | Dependents |
|---|---|---|---|---|---|---|---|
| ACT-27 | Heston-A–S kernel `rₜ = Sₜ − qγvₜ(T−t)` + Bates SVJ (Heston + Merton) + Merton jump-diffusion `dS/S = (μ−λκ)dt + σdW + (J−1)dN` + GARCH/Heston SV layer with calibrator + Student-t / heavy-tail branch | feature | major | XL | GAP-008, GAP-009, GAP-010, GAP-011, GAP-012 | ACT-14, ACT-17, ACT-19 | ACT-25, ACT-30 |
| ACT-28 | Per-bucket A–S reservation `rᵢ = mᵢ − qᵢγᵢσ²ₘᵢ(T−t)` + matrix-skew `rᵢ = mᵢ − γ(T−t)Σⱼ Σᵢⱼ qⱼ` + cross-bucket Σᵢⱼ from RND perturbation + multi-asset HJB + adjacent-bucket inventory penalty | feature | blocker | XL | GAP-004, GAP-021, GAP-050, GAP-123, GAP-124 | ACT-17, ACT-19 | — |
| ACT-29 | Vertical-spread option-hedge builder + hedge-leg basis tracker (Kalshi-snap vs CME-option-reference) + SPAN/FCM margin model + capital allocator (Kalshi vs CME margin) + Kalshi cash-collateral utilisation | feature+refactor | major | L | GAP-105, GAP-106, GAP-107, GAP-125, GAP-129 | ACT-17, ACT-20 | ACT-56 |
| ACT-30 | Microstructure: Glosten–Milgrom Bayes order-flow update + Kyle linear λ / OFI mid-price impact + Cartea–Jaimungal–Ricci adverse-selection skew | feature | major | L | GAP-013, GAP-014, GAP-024 | ACT-16, ACT-23 | — |
| ACT-31 | Alpha-drift overlays: Cartea–Jaimungal–Ricci alpha-proportional drift + Cartea–Wang asymmetric reservation/spread skew + mean-reverting drift at extreme inventory | feature | major | L | GAP-015, GAP-016, GAP-027 | ACT-19 | — |
| ACT-32 | Pre-event widening: SVI widening / Bates jump-variance scaling around USDA windows + event-day κ_t spread/width multipliers + edge-proximity widener for Kalshi bucket edges + bucket-variance σ²ₘᵢ ≈ Δᵢ²·σ²_S derivation | feature | major | M | GAP-018, GAP-019, GAP-020, GAP-026 | ACT-18, ACT-19 | — |
| ACT-33 | Measure overlay: favorite/longshot (Wolfers–Zitzewitz / Whelan 2025 bias) + Kalshi-vs-CME-RN parametric shrinkage on the two-measure tilt | feature | major | M | GAP-017, GAP-048 | ACT-17 | — |
| ACT-34 | USDA window pull-and-refit protocol (pull 30-60s before, refit, repost) + trade-through probability `μᵢ/(μᵢ+νᵢ)` + Cont-de Larrard / Huang-Lehalle-Rosenbaum queue-reactive overlay | feature | major | L | GAP-139, GAP-140, GAP-141 | ACT-18, ACT-22, ACT-23 | — |
| ACT-35 | Wash-trade prevention (Rule 5.15) + STP modes (`taker_at_cross`, `maker`) + $0.20 No-Cancellation Range / 15-min trade-bust review window + RFQ submission (`POST /communications/rfq`, 100 cap) | feature | major | M | GAP-084, GAP-085, GAP-092 | ACT-22 | — |
| ACT-36 | Density refinements: SABR closed-form + Bliss-Panigirtzoglou vega-weighted cubic-spline fallback | feature | major | M | GAP-039, GAP-040 | ACT-17 | — |
| ACT-37 | Limit-day censorship correction (CBOT 7% lock → biased σ): lock detection on settle stream, σ uncorrected → corrected | bugfix+feature | major | M | GAP-028 | ACT-21 | — |
| ACT-38 | Member/role/DMM concept + FCM pre-trade-risk hook (Robinhood Derivatives etc.) + Rule 5.16 PAL flag and scaling | feature | minor | M | GAP-093, GAP-094 | ACT-22 | — |

**ACT-27.** Cited C02-42/45/46/71/74/75, C08-25/89, C10-02. The "minimum
viable" pricing model bar from C02-75. Bates SVJ specifically required
for the C08-89 weather-shock scenario. Resolves Appendix B.1.3
(commented-out builders): all four — `jump_diffusion`, `regime_switch`,
`point_mass`, `student_t` — are not equivalent; this action lands
`heston`, `bates`, `jump_diffusion`, and `student_t`. `regime_switch`
and `point_mass` remain commented-out.

**ACT-28.** Cited C08-40/45/47/48/49/105, C02-33, C10-52/53/54. The
multi-asset-HJB cross-bucket Σᵢⱼ work; XL because the Σ estimator
choice is C10-OQ-05 research-open. Note: Appendix B.6.6 question
(perturbation estimator vs honest stub) resolves here as
perturbation-from-RND with a stub-identity fallback when the
perturbation budget is blown.

**ACT-29.** Cited C08-77/78/81-85, C10-62-67, C07-110, C09-78. The
hedge-leg basis tracker is a *new* module (`state/basis_hedge.py`),
not an extension of `state/basis.py` (which carries Pyth↔CME drift
inside the GBM forward — different mechanic, theme 3.5). Capital
allocator and cash-collateral utilisation land here because they need
both legs' margin models to compare.

**ACT-30.** Cited C02-12/13/15/38, C03-03/04, C07-62, C08-50/106. Folds
in MBP/MBO order-book reconstruction (GAP-052) as an absolutely-required
input for OFI; the Wave-1 ACT-16 only delivered the L1 surface.

**ACT-31.** Cited C02-31/32/56/83. `state/basis.py` interface change to
admit multiple drivers (carry + alpha + mean-reversion) — resolves
Appendix B.1.2 (`basis_drift` is *both* carry and alpha, with a
multi-component aggregator rather than a single scalar).

**ACT-32.** Cited C02-65/66/81, C08-41/54/55/56/97, C09-40, C10-13/14/
16/21/22/23. The `event_calendar[].vol_adjustment` YAML field
(`config/commodities.yaml:24-28`) finally gets a consumer here.
Resolves Appendix B.10.6: vol_adjustment feeds *both* κᵂᶦᵈᵗʰ and
κˢᵖʳᵉᵃᵈ, parametrised per-event.

**ACT-33.** Cited C08-37-39/104, C10-06/07. Resolves Appendix B.2.6 /
B.9.9: measure overlay is a parametric function of bucket midprice
(monotone shrinkage), not a per-commodity or per-bucket scalar.

**ACT-34.** Cited C08-43/51/52/98, C10-17/29/47/50. Coupled to ACT-32
on the pre-event side. The queue-reactive overlay is the C10-29 lift
once trade-through probability is calibrated.

**ACT-35.** Cited C07-44/52/60/61/63/64/86, C09-09/12. STP default
(Appendix B.7.4) resolves to `maker` because the engine's posting model
is queue-priority-aware and `taker_at_cross` would erode the queue
edge.

**ACT-36.** Cited C08-19-23. Two density-fitter alternatives (SABR,
BP cubic spline) ship as fallbacks when SVI fails butterfly arb or
when no co-terminal exists.

**ACT-37.** Cited C02-76/77, C07-83. Resolves Appendix B.2.5: limit-day
censorship is a *separate adjustment layer*, not a fold-into-σ
correction. Lives next to ACT-21's lock-day handler.

**ACT-38.** Cited C07-57/58/59/102/115, C09-26. Lower-priority Rule
5.16 PAL flag plus member-role concept and FCM pre-trade-risk hook.

---

## 6. Wave 3 — Signals and strategy

Goal: additive alpha. Universe expansion to the soybean complex (ZS/ZM/
ZL), weather and satellite ingest, SAm fundamentals, COT, FX, and the
strategy book that consumes them. None of this is required for Milestone
2 quoting; all of it is required to translate the M2 quoter into a book
that survives K-criteria 04 (hedge slippage > gross edge).

| ID | Summary | Type | Severity | Effort | Gaps closed | Deps | Dependents |
|---|---|---|---|---|---|---|---|
| ACT-39 | NWP weather + satellite + soil-moisture ingest stack: ECMWF IFS / GFS / GEFS / AIFS / HRRR / ENS / ERA5 + NASA SMAP + Sentinel-2 NDVI + Drought Monitor | feature | major | XL | GAP-055, GAP-056 | — | ACT-47 |
| ACT-40 | SAm fundamentals (CONAB monthly / BCBA Thursday weekly / BCR weekly / Rosario/Paraná cash) + GACC monthly Chinese imports + AIS-residual cargo signal + logistics (USDA AMS GTR weekly / USACE LPMS 30-min / Baltic indices) | feature | minor | L | GAP-057, GAP-058, GAP-060 | — | — |
| ACT-41 | USDA REST ingest: NASS Quick Stats + FAS GAIN + FOIA bulk USDA REST | feature | major | L | GAP-054 | ACT-18 | ACT-47 |
| ACT-42 | COT (Disaggregated since 2006, Friday 15:30 ET) ingest + COT-based signals (MM-net-long contrarian, MM-flip+momentum, commercial inflection) + Goldman-roll detector / GSCI-roll consumer + index-roll lower-A/S premium | feature | minor | M | GAP-033, GAP-059, GAP-162, GAP-163 | ACT-18 | — |
| ACT-43 | Cash-bid feeds (Barchart `getGrainBids`, DTN ProphetX) + cash-basis fair-value overlay + farmer-hedge slow-prior | feature | minor | M | GAP-061, GAP-169 | — | — |
| ACT-44 | FX cross-asset feeds (DXY, USD/BRL, USD/ARS, USD/CNY) + WTI/Brent/ULSD ingest | feature | major | L | GAP-062 | — | — |
| ACT-45 | Soybean complex universe: crush-spread book (board crush, reverse crush, GPM, Rechner-Poitras filtered MR, 3¢ entry filter) + calendar-spread book (Jul/Nov old-vs-new-crop, contango/backwardation, Moore composite, Farmdoc 3-of-15) + bean/corn ratio (ZSN/ZCN; >2.5/<2.2/USDA Acreage gate) | feature | major | L | GAP-156, GAP-157, GAP-158 | ACT-16, ACT-19 | — |
| ACT-46 | Trend / cross-section: TSMOM/Donchian/MA-crossover signals on ZS + carry/term-structure cross-sectional sort (Erb-Harvey, Fuertes-Miffre-Rallis combined) + cross-sectional momentum on ≥15-commodity universe | feature | major | L | GAP-159, GAP-160, GAP-161 | ACT-16 | ACT-48 |
| ACT-47 | Event-driven signals: tape-event detector (>2σ in <15 min headline) + WASDE fade rule (>1.5σ + 15-min stall, 25-50 bp NAV) + stocks-to-use regime classifier (tight vs loose) + ENSO + 5-yr basis state + soil-moisture entry + harvest-fade entry | feature | major | L | GAP-164, GAP-166, GAP-167, GAP-168 | ACT-39, ACT-41 | — |
| ACT-48 | Per-trade ATR/ADX/EMA/MACD/Donchian indicators + sizing rules (Brandt 0.5–1%, Turtle 1-unit ATR, Parker, Raschke, Holy Grail, Anti) | feature | minor | L | GAP-165 | ACT-46 | — |
| ACT-49 | Oilshare + RFS-RVO/RIN ingest and signals + WASDE-delta-to-price (~+18¢/bu per −1m bushel) + Roberts-Schlenker price-vs-yield elasticity + bimodal-RND fingerprint (concave IV pre-event) + practitioner spread decomposition + Grossman-Miller price concession | feature | minor | L | GAP-030, GAP-031, GAP-032, GAP-034, GAP-035, GAP-170 | ACT-19 | — |

**ACT-39.** Cited C03-46-49, C06-40-48/51-54, C09-45-50, C10-08/09/10.
XL because GRIB2/`xarray`/`cfgrib`/`herbie` add a new dep block plus
per-stream cycle calendars across six NWP sources. Appendix B.3.8
question (weather as MVS or deferred) folds in here as: Wave 3, not
Wave 1, because none of the Wave-2 alpha overlays consume weather
signals directly; the WASDE κ_t multiplier in ACT-32 only consumes
calendar timing.

**ACT-40.** Cited C03-44/56-59/79/87, C06-31-34/39/55-58/61/62, C09-44/
51/53. Three new feed packages (`feeds/sam/`, `feeds/china/`, `feeds/
ais/`, `feeds/logistics/`). Lower-priority because nothing in the
Milestone-3 P&L attribution consumes these directly.

**ACT-41.** Cited C03-56, C06-24/25. Three USDA REST clients on top of
the event-clock plumbing from ACT-18.

**ACT-42.** Cited C03-79, C04-61-63/66-69/92/93, C06-64-69, C09-51/52,
C10-27, C02-58/59. Goldman-roll detector replaces the WTI-only
`cme_roll_rule`.

**ACT-43.** Cited C04-47-48/54-60, C06-79/80, C03-87, C09-53, C10-26.
The cash-basis layer the soybean spec needs.

**ACT-44.** Cited C06-70-72/74. Multi-pair tick subscriber.

**ACT-45.** Cited C04-03/05/06/08/09/11-14/16-21/77, C05-38. The biggest
universe-shape lift; depends on ACT-16 because every signal needs a
ZM/ZL CME tick and on ACT-19 because the GPM sizing is A–S-frame.

**ACT-46.** Cited C05-01-05/14/17/18/26/29-31/72-74, C10-43. `TickStore`
already has history (`state/tick_store.py:31-66`) but no reader; this
action lands the reader plus the signals plus the universe-shape
upgrade (TheoInputs.spot from scalar to vector).

**ACT-47.** Cited C04-31/33-35/37/42-45/82-91/94, C10-44-46. The
release-window detector + WASDE fade + stocks-to-use regime classifier
are required gates for the §2.1 weather→density pipeline.

**ACT-48.** Cited C04-95-107. The practitioner indicator + sizing
library; Appendix B.9.8 question (corpus buffet vs recipe) resolves
here as buffet — claims are loaded into a registry with explicit
config-keyed selection per strategy.

**ACT-49.** Cited C02-08/09/62/67, C04-25/71/72, C10-11/15/39, C10-OQ-09.
Mixed bag of pricing-research overlays plus oilshare/RIN ingest, all
nice-to-have, all low-effort, batched here because they share calibration
infrastructure.

---

## 7. Wave 4 — Hardening

Goal: observability, topology, calibration substrate, backtest realism,
and the operational long-tail. Nothing in Wave 4 is on the critical path
to a tradeable surface; everything in Wave 4 is on the critical path to
a *durable* one.

| ID | Summary | Type | Severity | Effort | Gaps closed | Deps | Dependents |
|---|---|---|---|---|---|---|---|
| ACT-50 | Observability stack: Prometheus counters/gauges/histograms + Grafana dashboards + PagerDuty alert routing + tick-to-quote 5-leg latency histogram (replace today's offline-pytest-only model-leg measurement) | feature | major | L | GAP-175, GAP-176, GAP-177 | ACT-23 | — |
| ACT-51 | Topology hardening: hot-standby quoter / failover topology + 3-instance compute topology (quoter / hedge / capture) with `us-east-1` region pin + hedge round-trip latency budget / per-leg observability + hedge-leg fee model ($1/contract exchange + $0.50 FCM + 1-5¢ option BA) | feature | minor | L | GAP-109, GAP-110, GAP-111, GAP-181 | ACT-24 | — |
| ACT-52 | Calibration substrate: `calibration/params/*.json` producer + nightly job framework + freezing semantics + milestone gating discipline (M_n complete only when M_{n+1}'s tests pass on M_n data, encoded as pytest markers) | feature | major | M | GAP-182, GAP-185 | ACT-19, ACT-23 | — |
| ACT-53 | Backtest realism: turnover counter + capacity / market-impact penaliser + Sharpe-discount factors (×0.6-0.7) for live-money planning + survivorship-aware contract universe + look-ahead-safe PIT store for USDA features + weekly P&L attribution stage L (edge / inventory MTM / hedge slippage / fees) → (Aᵢ, kᵢ, γ) feedback + per-stream PIT semantics (USDA revisions) | feature | major | XL | GAP-069, GAP-151, GAP-153, GAP-154, GAP-155 | ACT-26 | — |
| ACT-54 | Pyth hardening: per-stream ingest-latency probe (Hermes `publish_time` → first parser touch) + source/stream redundancy (second endpoint plus failover) + `num_publishers` fail-loud raise on missing field + backfill on Pyth reconnect (SSE/REST gap-fill) | bugfix+feature | major | M | GAP-064, GAP-065, GAP-066, GAP-068 | — | — |
| ACT-55 | Forward-curve carry direction signal + Routledge–Seppi–Spatt endogenous convenience yield + Deaton–Laroque non-negativity-of-stockpile inventory model | feature | minor | L | GAP-126, GAP-127, GAP-128 | ACT-19 | — |
| ACT-56 | Cross-asset hedge selection (ZC / ZM / ZL / MATIF rapeseed / Dalian) + cross-asset intensity calibration | feature | nice-to-have | L | GAP-114, GAP-115 | ACT-29 | — |
| ACT-57 | Misc Kalshi residuals: URL slug builder `/markets/{series}/{slug}/{market}` + letter-prefixed strike-suffix products + DCM / 17 CFR Parts 38/40 / 40.2(a) regulatory metadata + Rule 8.1 idle-collateral interest model | feature | nice-to-have | M | GAP-095, GAP-096, GAP-097, GAP-098 | ACT-21 | — |
| ACT-58 | FIX 5.0 SP2 Order Entry / Drop Copy / Listener (Premier+) + 200K open-order cap tracking + cancel-vs-amend fee economics | feature | nice-to-have | XL | GAP-142, GAP-143, GAP-144 | ACT-22 | — |
| ACT-59 | Operational extras: PIN/VPIN flow-toxicity diagnostics + VPIN-as-USDA-window-withdrawal trigger + CME Daily Bulletin (unreported blocks, EFPs, OI deltas) reconciliation/calibration ingest + `buy_max_cost` per-request dollar cap + C10-79 Milestone-2 sandbox cap config interface ($500/bucket, $5,000/Event) + CVOL benchmark intraday/EOD ingest | feature | minor | L | GAP-025, GAP-070, GAP-122, GAP-130, GAP-183, GAP-184 | ACT-23 | — |

**ACT-50.** Cited C09-58/59, C10-81. Today only `models.gbm.price`
itself is timed and only at offline-pytest time (`benchmarks/run.py:13,
68-70, 204-205`); the five-leg tick-to-quote budget has no producer in
production. Lands `prometheus_client` + `structlog`-driven histograms.

**ACT-51.** Cited C09-55-57/61, C10-81. Three-instance topology under
the $500/mo target; co-location not needed (per C09-54 already-good).

**ACT-52.** Cited C10-51/82, ambiguity A4 in `audit_D_observability.md`.
Closes the schema-declared-no-consumer cluster (theme 3.3 of the
register) on the calibration side. The calibration→pricer handshake
(Appendix B.7.9) lives here.

**ACT-53.** Cited C05-24/33/60/70/72/73/75, C08-111, C09-23. XL because
five gaps span four sub-systems (turnover, capacity, survivorship,
PIT, attribution). USDA look-ahead policy (Appendix B.8.7) resolves to
PIT API rather than latest-revision endpoint.

**ACT-54.** Cited Red Flag 8 plus file-question rows for redundancy,
backfill, num_publishers. Bugfix-dominated. Resolves Appendix B.3.5
(`hermes_http` line either gets a producer here or is removed) and
Appendix B.3.6 (fail-loud, not fail-closed).

**ACT-55.** Cited C02-54-57, C04-13, C05-12/19, C10-35/36. Resolves
Appendix B.9.10: the upgrade path is a *new* `state/forward_curve.py`
state class, not an extension of `BasisModel`. The two carry-vs-alpha
mechanics stay separated.

**ACT-56.** Cited C02-86/87. Coupled to ACT-29 because cross-asset
hedge selection needs the SPAN margin per asset to compare.

**ACT-57.** Cited C07-04/06/104-106/109/114. Pure long-tail Kalshi
contract residuals. Several S-tier items batched.

**ACT-58.** Cited C07-46/67, C09-06/81. Premier+ tier work; only
attempted once daily fill volume justifies the FIX-engine investment.

**ACT-59.** Cited C02-17/18, C05-66, C06-09/86, C09-77, C10-79.
Resolves Appendix B.6.5 (`buy_max_cost` lives in the order builder
client wrapper, with the risk-gating layer enforcing the per-Event
sum) and Appendix B.6.7 (M2 sandbox caps load from `config/`).

---

## 8. Dependency graph

The full ACT-xx DAG. Every edge `A → B` means "B cannot start until A
has landed." Actions with no incoming edges are roots; actions with no
outgoing edges are leaves.

```
Wave 0
  ACT-01 (capture) ──────────────────────────────────────► ACT-26
  ACT-02 (soy yaml) ──► ACT-03, ACT-08, ACT-10
  ACT-03 (Kalshi client) ──► ACT-04, ACT-05, ACT-11, ACT-22
  ACT-04 (ticker+bucket) ──► ACT-06, ACT-09, ACT-13, ACT-21
  ACT-05 (WS multiplex) ──► ACT-22, ACT-23
  ACT-06 (order builder) ──► ACT-22
  ACT-07 (24/7 calendar) ──► ACT-18
  ACT-08 (settle/roll/FND) ──► ACT-13, ACT-21
  ACT-09 (positions) ──► ACT-12, ACT-19, ACT-23
  ACT-10 (fees) ──► ACT-19, ACT-26
  ACT-11 (kill primitives) ──► ACT-24
  ACT-12 (delta cap+M2) ──► ACT-19, ACT-25
  ACT-13 (corridor adapter) ──► ACT-17, ACT-19

Wave 1
  ACT-14 (IV signature) ──► ACT-16, ACT-17, ACT-27
  ACT-15 (TheoOutput) ──► ACT-19, ACT-20
  ACT-16 (CME ingest) ──► ACT-17, ACT-30, ACT-45, ACT-46
  ACT-17 (RND pipeline) ──► ACT-19, ACT-26, ACT-27, ACT-28, ACT-29, ACT-32, ACT-33, ACT-36
  ACT-18 (USDA event clock) ──► ACT-32, ACT-34, ACT-41, ACT-42, ACT-47
  ACT-19 (A-S/CJ control) ──► ACT-25, ACT-27, ACT-28, ACT-31, ACT-32, ACT-45, ACT-49, ACT-52, ACT-55
  ACT-20 (hedge foundation) ──► ACT-25, ACT-29, ACT-56
  ACT-21 (settlement) ──► ACT-37, ACT-57
  ACT-22 (order pipeline) ──► ACT-21, ACT-23, ACT-34, ACT-35, ACT-38, ACT-58
  ACT-23 (reconciliation) ──► ACT-24, ACT-30, ACT-34, ACT-50, ACT-52, ACT-59
  ACT-24 (kill switch e2e) ──► ACT-50, ACT-51
  ACT-25 (scenarios) ──► ACT-53
  ACT-26 (backtest M0) ──► ACT-53

Wave 2
  ACT-27 (Heston/Bates/JD) ──► (leaf: feeds ACT-25 forward, no Wave 3+ deps)
  ACT-28 (matrix skew) ──► (leaf)
  ACT-29 (option hedge) ──► ACT-56
  ACT-30 (microstructure) ──► (leaf)
  ACT-31 (alpha overlays) ──► (leaf)
  ACT-32 (pre-event widening) ──► (leaf)
  ACT-33 (measure overlay) ──► (leaf)
  ACT-34 (pull-refit/queue) ──► (leaf)
  ACT-35 (wash/STP/RFQ) ──► (leaf)
  ACT-36 (SABR/BP) ──► (leaf)
  ACT-37 (limit-day censorship) ──► (leaf)
  ACT-38 (member/role/PAL) ──► (leaf)

Wave 3
  ACT-39 (weather) ──► ACT-47
  ACT-40 (SAm/logistics) ──► (leaf)
  ACT-41 (USDA REST) ──► ACT-47
  ACT-42 (COT/Goldman-roll) ──► (leaf)
  ACT-43 (cash bids) ──► (leaf)
  ACT-44 (FX) ──► (leaf)
  ACT-45 (soy complex) ──► (leaf)
  ACT-46 (TSMOM/carry) ──► ACT-48
  ACT-47 (event signals) ──► (leaf)
  ACT-48 (per-trade indicators) ──► (leaf)
  ACT-49 (oilshare/overlays) ──► (leaf)

Wave 4
  ACT-50 (observability) ──► (leaf)
  ACT-51 (topology) ──► (leaf)
  ACT-52 (calibration) ──► (leaf)
  ACT-53 (backtest realism) ──► (leaf)
  ACT-54 (Pyth hardening) ──► (leaf)
  ACT-55 (forward curve) ──► (leaf)
  ACT-56 (cross-asset hedge) ──► (leaf)
  ACT-57 (Kalshi residuals) ──► (leaf)
  ACT-58 (FIX) ──► (leaf)
  ACT-59 (operational extras) ──► (leaf)
```

The graph has a clear shape: Wave 0 has dense intra-wave plus
out-of-wave fan-out (ACT-03 alone fans to four others); Wave 1 fans
heavily into Wave 2 and Wave 3 (ACT-19 alone is a prerequisite of nine
later actions); Waves 2/3/4 are mostly leaves. This matches the
heuristic that early-wave structural work has high reach.

---

## 9. Parallelisable vs. serial work, by wave

A derived view of section 8 — same dependency edges, regrouped per
wave to show what can run concurrently.

**Wave 0.** ACT-01 (capture), ACT-02 (soy yaml), and ACT-07 (24/7
calendar) start at t=0 (no deps). After ACT-02 lands, ACT-03, ACT-08,
and ACT-10 unblock and can run concurrently. After ACT-03 lands,
ACT-04, ACT-05, and ACT-11 unblock concurrently. After ACT-04 lands,
ACT-06 and ACT-09 unblock concurrently. ACT-12 needs ACT-09; ACT-13
needs ACT-04+ACT-08. So Wave 0 is roughly four serial layers (ACT-02
→ ACT-03 → ACT-04 → ACT-09 → ACT-12) with three parallel side-tracks
(ACT-01, ACT-07, ACT-08+ACT-10). With three engineers Wave 0 can land
in roughly the time of its longest critical path (ACT-02 + ACT-03 +
ACT-04 + ACT-09 + ACT-12 ≈ S+XL+M+L+L ≈ 5 ew, dominated by ACT-03 XL
+ ACT-09 L).

**Wave 1.** ACT-14 (IV signature) and ACT-15 (TheoOutput) start at t=0
in Wave 1 (no Wave-1 deps inside the wave; both are pure refactors of
existing modules). After ACT-14 lands, ACT-16 can start (it also
depends on ACT-15 only insofar as the L1 reader populates `TheoInputs`,
which is non-blocking for ACT-14's signature change). ACT-17 needs
ACT-14, ACT-16, plus Wave-0 ACT-13 — mid-wave gate. ACT-18 needs only
Wave-0 ACT-07 and runs in parallel. ACT-19 (A-S/CJ control) needs
Wave-0 ACT-09+ACT-10+ACT-12 plus ACT-15+ACT-17 — late-wave gate.
ACT-20 (hedge foundation) needs only ACT-15 — early. ACT-21
(settlement) needs ACT-04+ACT-22 — mid-wave. ACT-22 (order pipeline)
needs only Wave-0 ACT-06 — early. ACT-23 (reconciliation) needs
ACT-09+ACT-22 — mid-wave. ACT-24 (kill switch) needs ACT-11+ACT-23 —
late. ACT-25 (scenarios) needs ACT-12+ACT-19+ACT-20 — late. ACT-26
(backtest M0) needs ACT-01+ACT-10+ACT-17 — late, dominated by ACT-17.
With three engineers, the parallel paths are: (1) ACT-14 → ACT-16 →
ACT-17 → ACT-19 → ACT-25 → ACT-26; (2) ACT-15 → ACT-20; (3) ACT-22 →
ACT-21 / ACT-23 → ACT-24. Critical path is path (1).

**Wave 2.** Mostly parallel. ACT-27 needs ACT-14+ACT-17+ACT-19;
ACT-28 needs ACT-17+ACT-19; ACT-29 needs ACT-17+ACT-20; ACT-30 needs
ACT-16+ACT-23; ACT-31 needs ACT-19; ACT-32 needs ACT-18+ACT-19;
ACT-33 needs ACT-17; ACT-34 needs ACT-18+ACT-22+ACT-23; ACT-35 needs
ACT-22; ACT-36 needs ACT-17; ACT-37 needs ACT-21; ACT-38 needs
ACT-22. All twelve can start the moment Wave 1 closes. With four
engineers all twelve land in roughly the time of the longest action
(ACT-27 XL ≈ 3 ew).

**Wave 3.** Heavily parallel. ACT-39 / ACT-40 / ACT-41 / ACT-43 /
ACT-44 are independent ingest streams (different data sources, different
parsers); ACT-42 needs only ACT-18 from Wave 1. ACT-45 / ACT-46 need
ACT-16 / ACT-19 from Wave 1. ACT-47 needs ACT-39+ACT-41 — mid-wave.
ACT-48 needs ACT-46. ACT-49 needs ACT-19 only. With three engineers
the wave fans out fully and the critical path is ACT-39 → ACT-47 (≈ 3
ew + 1 ew).

**Wave 4.** Almost entirely parallel; every action is a leaf. ACT-50
needs ACT-23 from Wave 1; ACT-51 needs ACT-24 from Wave 1; ACT-52
needs ACT-19+ACT-23 from Wave 1; ACT-53 needs ACT-26 from Wave 1; the
rest have only earlier-wave dependencies. ACT-54 has zero deps and
can land any time after Wave 0 (technically a Wave-0-eligible bug
fix; deferred to Wave 4 because of the redundancy + per-stream-latency
work that ships alongside the bug fix). With three engineers Wave 4
takes the time of ACT-53 (XL) or ACT-58 (XL FIX engine).

---

## 10. Structural refactors vs. additive features vs. bug fixes

A second view over the action set, categorised by dominant change type.

**Structural refactors (4 actions).** These change existing module
contracts; they are intra-repo, low LoC, but high risk because every
consumer breaks.

- ACT-13 — adapter on existing GBM kernel (refactor + feature).
- ACT-14 — `state/iv_surface.py` signature change.
- ACT-15 — `TheoOutput` shape change.
- ACT-29 — `state/basis.py` lineage split into hedge-leg basis tracker
  (refactor + feature).

**Bug fixes (3 actions; one mixed).** These fix in-place wrong
behaviour.

- ACT-07 — `engine/event_calendar.py` 24/7 soybean session (currently
  WTI-shaped; weekends wrongly closed — bugfix + feature for the new
  calendar).
- ACT-37 — limit-day censorship correction (CBOT 7% lock biases σ
  downward today; bugfix on the σ surface plus feature for the lock
  detector).
- ACT-54 — Pyth `num_publishers` fail-loud, reconnect counter window
  (bugfixes), per-stream latency probe + redundancy + backfill
  (features). ACT-24 also includes a related bugfix (reconnect-counter
  reset bug, GAP-180) folded into the kill-switch landing.

**Additive features (52 actions).** Everything else. Two
characteristics dominate: (a) new modules and packages — `feeds/cme/`,
`feeds/kalshi/`, `feeds/usda/`, `feeds/weather/`, `feeds/satellite/`,
`feeds/sam/`, `feeds/china/`, `feeds/ais/`, `feeds/logistics/`,
`feeds/cashbids/`, `feeds/fx/`, `feeds/cot/`, `feeds/cvol/`,
`feeds/fcm/`, `oms/`, `state/positions.py`, `state/bucket_grid.py`,
`state/book.py`, `state/basis_hedge.py`, `state/forward_curve.py`,
`hedge/`, `scenario/`, `recon/`, `settlement/`, `treasury/`,
`backtest/`, `backtest/tape/`, `backtest/paper/`, `validation/portfolio.
py`, `strategy/`, `models/heston.py`, `models/bates.py`,
`models/jump_diffusion.py`, `models/glft.py`, `deploy/`, `fees/`,
`tape/`, density-pipeline package; (b) new external integrations —
Kalshi REST/WS, FCM (IB/AMP/Tradovate), CME MDP 3.0/Databento, USDA
REST trio, six NWP weather sources, Sentinel-2 / SMAP / Drought
Monitor, Barchart/DTN, FX feeds, COT, GACC + AIS, GTR/LPMS/Baltic,
RFS/RVO/RIN, CVOL, S3, DuckDB+Parquet, Prometheus, Grafana, PagerDuty.

The dominant `feature` count reflects the register's `missing` count
(167/185); the rare `refactor` and `bugfix` actions sit at the
foundational layer where existing module contracts must change before
anything else can land on top.

---

## 11. Outstanding decisions

The following are folded into action notes wherever resolvable, and
listed here as governance / scope / vendor / parameter decisions that
require a maintainer choice before the relevant action can land. ID
prefix is `OD-NN`; the originating Appendix B item is in parentheses.

- **OD-01.** *Project scope.* Is the C02/C08/C10 corpus the spec the
  live code is being built toward, or is it research input the system
  may decline to implement? (Appendix B.1.1) — gates the entire plan;
  this document assumes the former.
- **OD-02.** *GBM scalar σ default.* Is `models/gbm.py:35-42`'s
  constant σ intended as the default for all CME commodities, or only
  a baseline for soybean weekly density? (Appendix B.1.8) — affects
  ACT-27 scope; this document assumes baseline-only.
- **OD-03.** *`params_version` semantics.* Does it carry SVI calibration
  vintage, Heston/Bates switch, or something else? (Appendix B.1.9 /
  B.2.3) — affects ACT-17 and ACT-27.
- **OD-04.** *Density refresh placement.* Lives inside
  `pricer.reprice_market` (50-µs budget), or asynchronously in a
  separate task with cached RND? (Appendix B.2.9) — this document
  assumes async; revisit if cached-RND staleness inside USDA windows
  bites.
- **OD-05.** *Sum-to-1 assertion.* Hard (raise) or soft (log/widen)?
  (Appendix B.2.10) — this document assumes soft during M0–M2, hard at
  M3.
- **OD-06.** *Soybean ingest source.* Pyth Hermes or CME MDP 3.0 +
  Databento? (Appendix B.3.1) — this document assumes Databento for ZS
  because Hermes does not surface MBP/MBO depth.
- **OD-07.** *`hermes_http` SSE fallback.* Add a producer or remove the
  YAML line? (Appendix B.3.5) — folds into ACT-54.
- **OD-08.** *MVS scope for weather/logistics.* Are NWP, satellite,
  SAm, logistics part of the Kalshi MVS? (Appendix B.3.8) — this
  document defers to Wave 3.
- **OD-09.** *Corridor primitive placement.* One numba kernel per
  Event, or composed at the pricer from two half-line calls? (Appendix
  B.4.5) — this document assumes the latter (ACT-13).
- **OD-10.** *Pre-ship acceptance test.* Is there a planned paper-trade
  test against Kalshi demo with venue-rejection counts as the pass/fail
  signal? (Appendix B.4.10) — required before any production wire-on.
- **OD-11.** *FCM vendor.* IB, AMP, or Tradovate? (Appendix B.5.5 /
  B.7.10) — this document assumes IB; gates ACT-20 effort and timing.
- **OD-12.** *FCM vs self-clear.* Constrains pre-trade-risk hooks and
  order-size cap surface (Appendix B.7.10) — coupled to OD-11.
- **OD-13.** *Reconciliation cadence ownership.* Scheduler-driven or
  out-of-process job? (Appendix B.7.3) — this document assumes
  scheduler for open/intraday, cron for EOD.
- **OD-14.** *STP policy default.* `taker_at_cross` or `maker`?
  (Appendix B.7.4) — this document assumes `maker`.
- **OD-15.** *Kalshi rate-limit tier.* Standard / Premier / Premier+?
  (Appendix B.7.5) — this document assumes Standard.
- **OD-16.** *Kill-switch authorization.* In-process supervisor or
  separate watchdog process? (Appendix B.7.7) — this document assumes
  in-process.
- **OD-17.** *CBOT lock detection ownership.* CME L1 ingest (in ACT-21)
  or derived from Pyth? (Appendix B.7.8) — this document assumes CME
  L1 with Pyth fallback.
- **OD-18.** *Forward-capture status today.* Has any private branch /
  external service started writing the Kalshi tape? (Appendix B.8.3) —
  if yes, ACT-01 reduces to picking up the existing sink; if no,
  ACT-01 is the day-zero priority.
- **OD-19.** *Fee table source-of-truth.* Lives in `fees/` package,
  `config/`, or hardcoded in the order client? (Appendix B.8.4) — this
  document assumes new `fees/` package called from both pricer and
  order builder.
- **OD-20.** *CME options-chain vendor commitment.* Databento committed,
  or alternative? (Appendix B.8.5) — assumed Databento.
- **OD-21.** *Survivorship strategy on Kalshi.* Forward-only,
  per-trade-print backfill, or out-of-scope? (Appendix B.8.6) — this
  document assumes forward-only with per-trade-print augmentation in
  ACT-53.
- **OD-22.** *USDA look-ahead policy.* PIT API or latest-revision
  endpoint? (Appendix B.8.7) — this document assumes PIT (ACT-53).
- **OD-23.** *WTI focus intentional?* Is the WTI-only shape an
  early-deliverable scoping or an unacknowledged divergence? (Appendix
  B.9.3) — this document assumes scoping; resolved by ACT-02 + ACT-07.
- **OD-24.** *Measure-overlay form.* Single shrinkage, per-bucket
  correction, or parametric function? (Appendix B.9.9) — this document
  assumes parametric monotone in midprice.
- **OD-25.** *N and K kill-switch thresholds.* Hedge-heartbeat seconds
  and Kalshi WS reconnects/min thresholds (Appendix B.10.5) — this
  document assumes N=15s, K=5/min as starting defaults; final values
  decided after a week of paper-trade observation.
- **OD-26.** *vol_adjustment semantics.* Feeds κᵂᶦᵈᵗʰ, κˢᵖʳᵉᵃᵈ, both,
  or neither? (Appendix B.10.6) — this document assumes both.
- **OD-27.** *SanityError fan-out.* `quote_drop` / `market_suspend` /
  `page` / `restart_model`? (Appendix B.10.7) — this document assumes
  `quote_drop` default with consecutive-error escalation to
  `market_suspend`.
- **OD-28.** *`buy_max_cost` enforcement.* Client wrapper or risk-
  gating layer? (Appendix B.6.5) — this document assumes client
  wrapper for the per-request value, risk-gating layer for the per-
  Event sum.
- **OD-29.** *Σᵢⱼ estimator choice.* Perturbation-from-RND or honest
  stub identity? (Appendix B.6.6) — coupled to C10-OQ-05.
- **OD-30.** *Practitioner corpus selection.* Buffet (registry-driven)
  or recipe (single combined strategy)? (Appendix B.9.8) — this
  document assumes buffet.

Items not folded into actions and not listed here (e.g. README
aspirational status, validation/ scope) are treated as documentation
hygiene and tracked outside this plan.

---

## 12. Appendix: kill criteria

Empirical observations that would justify pausing or pivoting the
effort. C10-derived items keep their original IDs; audit-derived items
are labelled `KC-AUD-NN`.

1. **C10-KC-01** *Milestone 0 fails.* SVI / Figlewski RND-implied bucket
   probabilities, after a measure overlay calibrated on Whelan-style
   favorite-longshot assumptions, miss the realised Kalshi outcomes by
   more than the ~2¢ round-trip fee on more than 50% of buckets across
   12+ settled Events.
2. **C10-KC-02** *Milestone 1 fails.* Simulated would-quote P&L is not
   consistently positive (median weekly P&L < 0 over four settled
   weeks) at the realistic fee schedule, or rate-limit saturation
   prevents the would-quote engine from re-pricing during release
   windows.
3. **C10-KC-03** *Milestone 2 fails.* Realised markout on actual fills
   exceeds the estimated edge net of fees on the majority of buckets —
   informed counterparties are routinely picking off quotes faster than
   the engine can defend.
4. **C10-KC-04** *Milestone 3 fails.* Hedge slippage plus basis P&L
   plus snapshot-timing P&L exceeds the gross quoting edge produced by
   Milestone 2.
5. **C10-KC-05** *Structural failure.* Kalshi Appendix A reveals a
   reference specification (e.g. a non-CME source, a VWAP that cannot
   be replicated from public CBOT data, a roll rule that discards
   short-dated weekly options) that breaks the Breeden–Litzenberger
   pipeline at its root.
6. **C10-KC-06** *Liquidity failure.* Per-bucket queue depth and trade
   arrival on `KXSOYBEANW` over four consecutive Events remain below a
   level at which queue-position-aware quoting matters (e.g. sub-50
   contracts top-of-book on most buckets), making the FIFO
   microstructure edge irrelevant.
7. **C10-KC-07** *Regulatory failure.* A CFTC action, exchange rule
   change, or fee surcharge materially alters the Phase 7 / Phase 8 /
   Phase 9 cost structure.
8. **KC-AUD-01** *Forward-capture loss.* The Kalshi tape captured by
   ACT-01 is empty, partial, or unreplayable for more than five
   consecutive trading days inside the first three months — the M0
   backtest pipeline (ACT-26 / ACT-29) has no settled-Kalshi-week to
   score against and Phase-10 Milestone 0 cannot be evaluated.
9. **KC-AUD-02** *Kalshi client never lands.* After Wave 0 nominal
   completion, `grep -rn "import httpx|from httpx" --include="*.py"`
   still returns zero matches; the project is not Kalshi-bound in
   practice.
10. **KC-AUD-03** *SVI arbitrage failure.* After ACT-17 lands, SVI
    fits violate butterfly or calendar arbitrage on more than 25% of
    co-terminal weeks across the first four settled Events (ACT-36's
    SABR/BP fallback would in principle catch these, but a 25%+ rate
    means SVI is not the right baseline).
11. **KC-AUD-04** *Inventory unbounded.* On a synthetic GBM tape
    inside the ACT-25 scenario harness, ACT-19's reservation-price
    drift produces inventory `|q|` that exceeds the GLFT bound `Q`
    within 60 minutes of simulated quoting, indicating a γ
    miscalibration that no parameter sweep recovers.
12. **KC-AUD-05** *Weekend market-making impractical.* The 24/7 calendar
    (ACT-07) plus M2 quoter on Sat–Sun stretches accumulates
    `StaleDataError` raises (CBOT closed Fri 13:20 CT → Sun 19:00 CT)
    that pull quotes for more than 30% of the weekend window — the
    Kalshi-side weekend liquidity is not capturable without a separate
    weekend pricing model.
13. **KC-AUD-06** *Reconciliation tape divergence.* WS-derived `fill`
    frames disagree with `GET /portfolio/fills` on more than 1% of fills
    in any open / intraday / EOD reconciliation pass after ACT-23 lands —
    one of the two surfaces is unreliable enough that downstream P&L
    attribution cannot be trusted.
14. **KC-AUD-07** *Hedge-attribution failure.* ACT-53 weekly P&L
    attribution shows hedge-slippage component dominating gross-edge
    component for more than 50% of trading days across the M3 paper-
    trade harness — a directionally specific version of C10-KC-04 that
    points the finger at the FCM execution, not the modelling.
15. **KC-AUD-08** *Latency budget unachievable.* After ACT-50 wires the
    five-leg tick-to-quote latency histogram, p95 latency exceeds the
    C09-58 60-ms budget on a non-event day with no identifiable
    bottleneck stage — the architecture cannot meet the budget without
    a re-platforming exercise of Wave-0 magnitude.
16. **KC-AUD-09** *Calibration cadence too slow.* ACT-52's nightly
    calibration job, run on a representative weekday, takes more than
    six hours wall-clock to fit (Aᵢ, kᵢ, γ) from the previous day's fill
    tape — the (Aᵢ, kᵢ, γ) feedback loop into the next session's
    quoting (ACT-31, ACT-33, ACT-34) cannot land before market open.

*End of `audit_F_refactor_plan.md`.*
