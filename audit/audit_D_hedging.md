# Audit Phase D — Topic 5/10: Hedging into CME ZS

## 1. Scope

This audit covers the `hedging` claim set drawn from Phase C distillations,
filtered to the rows tagged `hedging` and prioritised by Phases 08, 09, and 10
per the brief. The topic is neutralising the residual market risk that a
Kalshi `KXSOYBEANW` market-maker accumulates from its bucket book by trading
the underlying CBOT soybean reference — primarily the front-month CME ZS
futures contract (5,000 bushels notional), with an optional ZS weekly-option
vertical-spread overlay around concentrated positions or USDA event windows.

The repository under audit (`goated`, `HEAD` on the working branch) is a
Python 3.11 prototype of a Kalshi commodity *theo* engine. Per
`audit_A_cartography.md` §9 (lines 213–231) the module inventory contains
fifteen entries. Filtering that inventory against the brief's responsibilities
— hedging, delta computation, futures order routing, broker connections,
margin, collateral — returns the empty set: no module computes a Kalshi-bucket
delta or basket-wide aggregate delta (`engine/pricer.py` emits `TheoOutput`
Yes prices and has no `Greek` interface, `audit_A_cartography.md:222`); no
module submits orders to CME, an FCM, or any broker (cartography §4
lines 103–115: Pyth Hermes is the only external service implemented); no
module models margin, SPAN, daily loss tripwires, or collateral-yield
economics on either leg. The one file carrying "basis" in its name is
`state/basis.py`, which tracks a per-commodity *Pyth↔CME annualised drift*
used to compute the GBM forward `F = spot * exp(basis_drift * tau)`
(`state/basis.py:1-9`) — not a hedge-leg basis tracker.

The brief instructs: "If no Phase B file applies, confirm via cartography
and proceed — most rows will be `missing`." A `grep` of `audit/audit_B_*.md`
for `hedge`, `delta hedging`, `futures`, `broker`, `FCM`, `margin`,
`collateral`, or `order routing` returns no matches across all nine files
(engine-pricer, engine-calendar, engine-scheduler, feeds-pyth, models-gbm,
models-registry, state-tick-store, state-market-surfaces, validation-sanity).
The expected-empty Phase B set is confirmed empty.

The expected Phase C inputs are all present (phase01..phase10). No halt is
required.

Because the audited surface is "no hedging module exists," each row below
carries `missing` unless an adjacent piece of state infrastructure (e.g.
`state/basis.py`, `state/iv_surface.py`) accidentally bears on the claim,
in which case the row carries `partial` (the adjacent code does part of
what the claim requires) or `wrong` (the adjacent code is structurally at
odds with what the claim requires). For all `missing` rows the code-side
citation falls back to the cartography pointer `audit_A_cartography.md:215-231`
as the brief permits.

## 2. Audit Table

| C-id | Claim (one-line) | What the code does | Gap class | Severity | Code citation | Notes |
|---|---|---|---|---|---|---|
| C08-09 | Each digital is the limit of a narrow vertical call spread; this is the hedge primitive for a Kalshi bucket. | absent — no vertical-spread builder, no option chain consumer. | missing | major | no module (cartography `audit_A_cartography.md:215-231`) | Hedge primitive is the foundational identity that the rest of the §6 chain needs. Every downstream hedge mechanic (C08-77, C10-62, C10-80) presumes this is implementable. |
| C08-70 | Bucket delta with fixed edges: $\Delta_i^K = \int_{\ell_i}^{u_i}\partial f_T/\partial S\,dx$. | absent — `TheoOutput` (`models/base.py`) has no delta field; pricer (`engine/pricer.py`) does not differentiate $f_T$ in $S$. | missing | blocker | no module (`audit_A_cartography.md:219, 222`) | Without per-bucket delta, no aggregate hedge can be computed. The `TheoOutput` dataclass is the natural carrier and is unextended. |
| C08-71 | Under a Black–Scholes-style reference, digital delta is $\phi(d_2)/(S\sigma\sqrt{T-t})$. | absent — `models/gbm.py` computes $\Phi(d_2)$ but never $\phi(d_2)/(S\sigma\sqrt{T-t})$. | missing | major | `models/gbm.py:1-105` ($\Phi$ only) | The closed-form $\phi$ companion is one numba-jitted line away; the absence is structural rather than algorithmic. |
| C08-72 | Bucket deltas peak for ATM buckets and decay for tails. | absent — no per-bucket delta surface to peak. | missing | major | no module (`audit_A_cartography.md:215-231`) | Used downstream to size cross-bucket Σ for the matrix-skew reservation price (C08-105) too, so the absence cascades. |
| C08-73 | Aggregate book delta $\Delta^{\text{port}} = \sum_i q_i\Delta_i^K$; ZS futures hedge is $-\Delta^{\text{port}}/N_{ZS}$ contracts ($N_{ZS}=5{,}000$). | absent — no bucket-position registry, no aggregator, and no $N_{ZS}$ constant in the codebase. | missing | blocker | no module (`audit_A_cartography.md:215-231`) | This is the single most explicit hedging operation in the corpus. There is no inventory store the aggregator could read from. |
| C08-74 | Kalshi notional is \$1/contract, so $\Delta^{\text{port}}$ is in \$/bushel and divides cleanly against ZS notional. | absent. | missing | minor | no module | Implicit unit-system convention; once C08-73 is implemented this falls out. |
| C08-75 | Bucket gamma $\Gamma_i^K=\partial^2 m_i/\partial S^2$ is large and bipolar near edges. | absent. | missing | major | no module | Required for the §6.2 vertical-spread sizing decision. |
| C08-76 | Yes contracts near ATM carry substantial gamma not neutralisable with futures alone. | absent — no gamma surface, no option-spread pathway. | missing | major | no module | Becomes blocker-level if/when book is sized into ATM concentrations. |
| C08-77 | A tight ZS-option vertical spread around each bucket edge replicates the digital exactly, neutralising delta, gamma, vega in one static construction. | absent — there is no option chain in state, no IV surface in strike (only ATM IV per `state/iv_surface.py`), and no spread builder. | missing | major | `state/iv_surface.py:1-48` (ATM-only) | Even the data substrate (per-strike IV) for a vertical spread is not staged. |
| C08-78 | ZS option bid–ask is 1–3¢ on liquid strikes, 5+¢ on wings — the binding cost of static vertical hedge. | absent — no option-chain ingest, no bid/ask state. | missing | minor | no module | Required to make C10-63 / C10-64 economic decisions; absent because the option chain is absent. |
| C08-79 | Practitioner rule: hedge gamma/vega in options when (i) gamma P&L variance dominates spread cost AND (ii) surface liquidity is sufficient. | absent — no rule engine, no gamma estimator. | missing | major | no module | Naturally a `validation/sanity.py`-adjacent gating check; not implemented. |
| C08-80 | Small books delta-hedge in futures and carry residual gamma/vega. | absent — even the default delta-only path is not implemented. | missing | blocker | no module | This is the simplest possible policy and would be the MVP. Its absence means *no* policy exists in code. |
| C08-81 | Three residual basis risks: reference-price (snapshot vs settle vs VWAP) basis, timing basis (non-CME-standard Friday), contract-month basis (roll-week deferred-month options). | absent — `state/basis.py` only models the *Pyth↔CME* drift, not the Kalshi↔CME-option reference basis. | wrong | major | `state/basis.py:1-49` | The codebase has *a* file called `basis.py` but it solves a different problem; this is a divergent name collision rather than a partial implementation. Classified `wrong` per scale, not `partial`, because the existing object would mislead a reader looking for hedge basis. |
| C08-83 | CME ZS futures SPAN-margin at ~5–8% of notional. | absent — no SPAN model, no margin store. | missing | major | no module (`audit_A_cartography.md:215-231`) | Affects capital deployment per C08-85 inversion. |
| C08-84 | ZS-option vertical spreads SPAN-margin on portfolio variance and are typically cheaper than premium. | absent. | missing | minor | no module | Drives the §6.4 capital comparison; conditional on C08-83 being staged. |
| C08-85 | The Kalshi leg is the binding capital constraint in most hedged trades. | absent — no capital model on either leg. | missing | major | no module | Underpins C08-88 risk gating; without margin models the capital allocator cannot exist. |
| C08-88 | The more binding constraint is a book-level aggregate net delta cap on unhedged $\Delta^{\text{port}}$. | absent — no aggregate-delta computation, no cap, no risk gate beyond per-tick sanity. | missing | blocker | `validation/sanity.py:1-68` does per-`TheoOutput` finiteness/monotonicity only | The closest thing in code is `validation/sanity.py` which gates Yes-price *outputs*, not portfolio-level delta. |
| C08-92 | CME hedge fees: ~\$1/contract exchange + ~\$0.50/contract FCM commission + ZS option BA 1–5¢. | absent — no fee model on the hedge leg. | missing | minor | no module | Affects backtest fidelity; not a runtime blocker. |
| C08-108 | Pipeline stage I — Hedge: compute $\Delta^{\text{port}}$ + vertical-spread gamma hedge; send ZS futures and option orders to CME gateway; reconcile each second. | absent — pipeline ends at the `TheoOutput` from `engine/pricer.py`; there is no stage I, no CME gateway, no per-second reconciler. | missing | blocker | `engine/pricer.py:1-90` (pipeline ends at theo) | The cartography (`audit_A_cartography.md:222`) calls `engine/pricer.py` "the sole hot-path composition point" — there is no downstream composition. |
| C08-116 | Open question: empirical Kalshi-snapshot vs CME-option-reference basis in cents historically. | absent — no historical-basis collector, no Kalshi reference-snapshot ingest. | missing | minor | no module | Open empirical claim; not a code requirement. |
| C09-28 | The cheapest viable real-time L1 on ZS/ZM/ZL is via the FCM that carries the hedge account; retail FCMs bundle CME Globex L1. | absent — no FCM client; the only feed implemented is Pyth Hermes (`feeds/pyth_ws.py`). | missing | major | `feeds/pyth_ws.py:1-145` (Pyth only) | A second feed module under `feeds/` would house this; the `feeds/` package contains only `pyth_ws.py` (`audit_A_cartography.md:68-69`). |
| C09-54 | Co-location is unnecessary because Kalshi REST limits, Rule 813 settle window, and full collateralisation make microsecond hedge slippage immaterial. | n/a — the design rationale is consistent with the absence of any latency-engineering scaffolding. | already-good | nice-to-have | no module | Classed `already-good` only because the *negative* claim ("don't co-locate") is trivially satisfied by a system that has no hedge stack at all. Evidence: cartography §9, no co-location-relevant module exists. |
| C09-55 | Hedge lag that matters is tens of ms to a few seconds. | absent — no hedge loop, no latency budget assigned to the hedge leg. | missing | minor | no module | Latency budgets are concentrated on `engine/pricer.py` and `feeds/pyth_ws.py`; nothing for a hedge round-trip. |
| C09-57 | The CME hedge leg is in Aurora, IL; the broker API adds a hop budget regardless of region. | absent — no broker API, no region-aware deployment config. | missing | nice-to-have | no module | Deployment config is absent at the file level (`audit_A_cartography.md:84-85`: no `deploy/`, `Dockerfile`, etc.). |
| C09-61 | A second instance runs the CME hedge connector and a third low-spec instance captures ticks. | absent — single-process layout. | missing | minor | no module (`audit_A_cartography.md:96-100` "no main binary, CLI, or systemd/launchd unit") | Process topology is unspecified in code; this is a deploy-spec gap rather than a coding gap. |
| C09-73 | Kill-switch fires on (i) aggregate delta breach, (ii) PnL drawdown, (iii) CME hedge connectivity heartbeat fail, (iv) Kalshi WS reconnect storm. | absent — `engine/scheduler.py` declares a Scheduler skeleton but is unwired (`audit_A_cartography.md:255-257` red flag #5); no kill-switch primitive. | missing | blocker | `engine/scheduler.py:36-56` (skeleton, unused) | The scheduler is the closest place such a watchdog would attach; cartography flags it as orphan. |
| C09-78 | The CME hedge leg carries broker-imposed initial and maintenance margin and daily loss tripwires of its own. | absent. | missing | major | no module | Direct counterpart to C08-83 / C08-85; no margin model anywhere. |
| C09-79 | Reconciliation runs three times per session: open, intraday, end-of-session — Kalshi `/portfolio/positions` vs broker leg. | absent — no `/portfolio/*` consumer; no broker-side fetch; no reconciliation runner. | missing | major | no module | The Kalshi REST surface (`audit_A_cartography.md:103-115`) is entirely unimplemented. |
| C10-59 | Hedge the fastest-changing, lowest-cost Greek first (delta). | absent — no Greek prioritisation logic, no Greek surface. | missing | major | no module | Encodes a heuristic that presumes a delta computation exists. |
| C10-60 | Aggregate net delta on the bucket book translates 1:1 into ZS-equivalent bushel exposure, hedged in CME ZS futures at ~\$1/contract commission plus ~\$0.0025 (¼¢) tick spread. | absent — no aggregate delta, no ZS futures order pipeline. | missing | blocker | no module | The most direct hedging instruction in C-phase 10. |
| C10-61 | Delta-hedge threshold rule of thumb: hedge whenever aggregate Kalshi-equivalent delta exceeds one ZS contract (5,000 bushels). | absent — no threshold check, no `5000` literal in any hedging context (only WTI-related module-level constants exist; `audit_A_cartography.md:298-301`). | missing | blocker | no module (cartography confirms only WTI session is wired) | This is the explicit trigger asked about in the brief's question 2; it does not exist in code. |
| C10-62 | Vertical spread in ZS options replicating a single Kalshi bucket costs ~1–3¢ on liquid strikes, 5+¢ on wings. | absent — no option-chain ingest, no spread builder. | missing | major | no module | Mirror of C08-78 from the Phase 10 angle. |
| C10-63 | On a \$0.30-priced bucket, a 4¢ option-spread cost is ~13% of position value. | absent — no economic gating logic that knows option-spread cost vs bucket value. | missing | minor | no module | Classed minor because the rule is illustrative; the gate is C10-64. |
| C10-64 | Option hedging is justified only when (i) single-bucket position is large enough that gamma squared-error exceeds option-spread cost AND (ii) a CBOT weekly or short-dated new-crop expiry co-terminates with the Kalshi Event. | absent — neither precondition is computed. | missing | major | no module | This is the explicit "cost threshold" question in the brief; *the codebase does not encode any cost threshold*. |
| C10-65 | CBOT short-dated weekly options that co-terminate with the Kalshi Event are available February through August; outside that window the hedge is mismatched in expiry. | absent — `engine/event_calendar.py` registers only WTI session (`audit_A_cartography.md:298-301`); no soybean or weekly-option-window calendar. | missing | major | `engine/event_calendar.py:30-79` (WTI-only) | The repository's calendar machinery is structurally able to express this once a soybean session is registered, but no soybean session exists. |
| C10-66 | Three further hedge frictions: Kalshi-snapshot vs CME-option-reference expiry basis; contract-month mismatch on roll-window weeks (Appendix A unconfirmed); Kalshi full collateralisation makes Kalshi leg more capital-intensive per dollar of notional than ZS option. | absent on all three. `state/basis.py` covers a different basis (Pyth↔CME drift, not Kalshi↔CME reference). | wrong | major | `state/basis.py:1-49` | Same name-collision finding as C08-81; the code has a `basis` object but it is not the `basis` the claim names. |
| C10-67 | Recommended discipline: delta-only hedge by default; event-driven option-hedge overlay around scheduled USDA releases when bucket positions concentrate near the strike where the release lands. | absent — neither a delta hedge nor an event overlay is implemented. The `event_calendar` field in `config/commodities.yaml` exists for WTI but no soybean entry has it (`audit_A_cartography.md:148-151`). | missing | major | `config/commodities.yaml:34-85` (soybean is `stub: true`) | Both halves of the discipline are unimplemented; the config substrate exists for one half. |
| C10-74 | CBOT soybean ~7% daily limits; on a limit-locked Friday the settlement is the limit price (resolves all buckets) but the hedge leg is unwindable only at the limit and produces discrete-jump P&L — book must be stress-tested. | absent — no scenario engine, no limit-lock handler, no PnL stress harness for hedge leg. | missing | major | no module | `validation/sanity.py` validates per-output invariants only; no scenario stress. |
| C10-80 | Milestone 3 (CME hedge loop): FCM API (Interactive Brokers / AMP / Tradovate); hedge net delta when abs-delta ≥ 1 ZS contract; optional weekly-option vertical-spread hedge for concentrated single-bucket positions during Feb–Aug; reconcile Kalshi `GET /portfolio/positions` vs FCM execution reports three times per session. | absent — no FCM client, no Δ aggregator, no reconciliation runner. The repo is at "Milestone 0/1-fragments" by this rubric. | missing | blocker | no module (`audit_A_cartography.md:103-115`) | The most directly actionable hedging spec in the corpus; nothing implements it. |
| C02-33 | Guéant (2017) generalises Avellaneda–Stoikov to non-exponential intensities and multi-asset hedged quoting with cross-asset inventory penalties. | absent — `models/gbm.py` is single-asset GBM; no multi-asset state; no cross-asset inventory penalty. | missing | minor | `models/gbm.py:1-105`, `models/registry.py:1-94` | Theoretical underpinning; not directly actionable in code without C08-73 / C10-60 first. |
| C02-86 | A commodity MM quoting ZS may hedge in real time with ZC, ZM, ZL, MATIF rapeseed, or the Dalian complex. | absent — single-feed (Pyth) ingest; no cross-asset hedge selection. | missing | nice-to-have | `feeds/pyth_ws.py:1-145`; `config/commodities.yaml` (per-commodity blocks but soybean stubs) | Cross-asset hedging is far downstream of even the base ZS-only hedge. |
| C02-87 | Cross-asset intensities are estimated empirically from trade and quote data; optimal hedge ratios rebalance more frequently than any stochastic-control model prescribes due to TC and basis risk. | absent — `calibration/` is the empty-stub package per `audit_A_cartography.md:62-63, 229`. | missing | nice-to-have | `calibration/__init__.py` (empty) | Calibration package exists by name only. |
| C02-88 | Pricing models do not specify how to hedge; hedging is a separate optimisation layer. | This is the *organising principle* of the absent layer. The repo separates pricing (implemented) from hedging (absent), which is consistent with the claim. | already-good | nice-to-have | `engine/pricer.py:1-90` (pricer ends at theo, nothing imports `Pricer` for hedging downstream) | Classed `already-good` only in the structural-separation sense — the pricer does not muddle hedging logic. Evidence: pricer interface emits Yes prices and Greeks-free `TheoOutput`s; `models/base.py:1-69` defines the contract. |
| C06-06 | CME options on ZS include standard monthly, SDNC, and weekly Friday expiries Feb–Aug. | absent — no option-chain consumer; `config/commodities.yaml` has no option-expiry calendar for soybean (only stub entry, `audit_A_cartography.md:151-152`). | missing | minor | `config/commodities.yaml:34-85` (soybean stubs) | Required to make C10-65 enforceable. |
| C06-08 | Greeks and full IV surface for ZS options are not exchange-published; practitioners compute them off raw prices or vendor. | absent — no IV-surface-from-chain code; `state/iv_surface.py` carries ATM-only IV with staleness gating, not a strike surface (`state/iv_surface.py:1-48`). | partial | major | `state/iv_surface.py:1-48` | Partial because the *existence* of an IV surface object is staged but it is degenerate (one σ per commodity, no strike axis). The hedge claim needs a strike-by-expiry surface. |
| C06-09 | CVOL is a 30-day IV index on ZS, EOD free / intraday via DataMine; serves as regime filter not chain substitute. | absent — no CVOL consumer. | missing | nice-to-have | no module | Useful as filter not as hedger; lowest-priority item in this audit. |
| C06-82 | CME EOD settlements & reference prices are available daily and are used for margin / MtM / session carry. | absent — no settlement-file consumer. | missing | minor | no module | Required for end-of-session reconciliation per C09-79. |
| C07-15 | For the week of April 20–24, 2026, the front-month CBOT soybean contract is `ZSK26`. | absent — no front-month resolution code; no `ZSK26` literal anywhere in the codebase; `cme_symbol` field exists in YAML schema but soybean is stub-only. | missing | major | `config/commodities.yaml:13` (`cme_symbol` only on WTI block) | The very identity of the hedge instrument for the documented Event week is unbound in code. |
| C07-21 | On a Friday inside a rolling window, Kalshi must specify whether it follows CME roll calendar or tracks Most-Active; pinned in Appendix A. | absent — no roll-rule resolver. `config/commodities.yaml` has a `cme_roll_rule` field (per cartography §6 line 148) but it is populated only for WTI. | missing | minor | `config/commodities.yaml` (WTI-only roll rule field) | The schema has a slot; soybean has no value. |
| C07-82 | CBOT soybean variable daily limits ~7% of price, reset semi-annually. | absent — no daily-limit handler, no limit-lock detection on the hedge leg (counterpart of C10-74). | missing | minor | no module | Required for the C10-74 stress test; both are missing together. |

Row count: 50 rows above. Research-citation count: 50 distinct C-ids
referenced (well above the 10 minimum required by the brief). Gap-class
distribution: 45 `missing`, 2 `wrong` (C08-81, C10-66), 1 `partial`
(C06-08), 2 `already-good` (C09-54, C02-88 — each with explicit evidence
in the row), 0 `divergent-intentional` (no intentional design divergence
is documented in the code or in `README.md`).

## 3. Narrative — blockers and majors

### 3.1 Blockers

Nine rows carry `blocker` severity (C08-70, C08-73, C08-80, C08-88,
C08-108, C09-73, C10-60, C10-61, C10-80). They share a single causal
chain: **no inventory store → no per-bucket delta → no aggregate delta
→ no hedge sizer → no hedge order → no kill-switch on the hedge
connection.**

The aggregate-delta-sizing claims (C08-70, C08-73, C10-60, C10-61, C10-80,
C08-108) share the same code-side reality: no inventory store, and no
module imports `engine.pricer.Pricer` for downstream composition.
Cartography §9 line 222 calls `engine/pricer.py` "the sole hot-path
composition point", and that composition stops at the `TheoOutput`. The
cartography red-flag list (§10 item 5, lines 254–257) explicitly notes
that `engine/scheduler.py` declares a `Scheduler` class "but no producer
submits to it" — the natural wiring point for a hedge loop is also
unwired.

C08-80 (small books delta-hedge in futures, carry residual gamma) is a
blocker because it is the *minimum-viable hedge policy*; its absence means
there is no hedge policy at all, not even the simplest one. C08-88 (book-
level aggregate net delta cap) is a blocker because it is the binding
risk gate, and `validation/sanity.py:1-68` validates each `TheoOutput`
per cartography §9 line 226 — per-quote, never per-book. C09-73 (kill-
switch on aggregate delta / PnL drawdown / CME-hedge connectivity /
Kalshi WS reconnect storm) is a blocker because it is the only safety
net the corpus specifies, and none of its four trigger inputs exists.

The blocker set is not "hard to implement once you have the spec" — the
spec is in Phase 08/09/10 — but none of the prerequisites exists, so the
hedge layer cannot be incrementally added: it has to be greenfield. That
is consistent with cartography §10 item 2 which observes that `README.md`
describes a "Live Kalshi commodity theo engine" while no file in the repo
references anything Kalshi-specific.

### 3.2 Majors

The `major`-severity rows fall into four clusters.

**(a) Greeks substrate** (C08-71, C08-72, C08-75, C08-76, C08-77, C08-79,
C10-59): `models/gbm.py` computes only $\Phi(d_2)$, never its derivatives
in $S$. The natural extension is to add `delta` and `gamma` fields to
`TheoOutput` (`models/base.py:1-69`) and populate them via closed form;
neither is staged.

**(b) Option-chain ingest and IV-surface-by-strike** (C06-08, `partial`):
`state/iv_surface.py` is "per-commodity ATM IV" per cartography §9
line 217 — one σ per commodity. Hedging claims (C08-77, C10-62, C10-64,
C10-65) require a full strike-by-expiry surface so a vertical spread can
be priced at any $(\ell_i, u_i)$ pair.

**(c) Basis-risk accounting** (C08-81, C10-66): the corpus describes a
*Kalshi-snapshot vs CME-option-reference* basis with three components
(reference-price, timing, contract-month). The repository's `state/basis.py`
is a different object — the drift used in the GBM forward `F = spot *
exp(drift * τ)`. Same word, different mechanic. Classified `wrong` rather
than `partial` because the existing object would not, when extended,
become the missing object.

**(d) FCM connection / order routing / reconciliation** (C09-28, C09-78,
C09-79, C10-62, C10-65, C10-67, C10-74): cartography §4 (lines 103–115)
states "CME / options chains / Kalshi API / macro feeds — referenced in
`README.md:39` and in `research/` but not implemented anywhere in the
code." Both source and sink sides of the hedging stack are absent.

### 3.3 Non-`missing` findings

Three rows escape the `missing` label. **C06-08 (`partial`)**:
`state/iv_surface.py:1-48` carries an IV object but it is ATM-only — the
hedge claims (vertical-spread sizing) need a strike axis. **C02-88
(`already-good`)**: the corpus says pricing and hedging should be
separate layers, and the `Theo` interface in `models/base.py:1-69` emits
Yes prices only with no Greeks pollution per cartography §9 line 219, so
the principle is implemented-by-omission with evidence. **C09-54
(`already-good`)**: the corpus argues against co-location, and the repo
does not co-locate (no `deploy/`, `Dockerfile`, or region pinning per
cartography §2 line 84) — vacuously consistent because there is no
system, hence severity `nice-to-have`.

No row is classed `divergent-intentional`. No comment, README section, or
design doc in the repository justifies omitting the hedge layer;
cartography §10 item 2 (lines 243–245) treats the absence as a red flag.

## 4. File-specific audit-question answers

The brief asks six pointed questions; each is answered against the code.

**(1) How is basket-wide delta computed from bucket positions?** It is
not. There is no bucket-position registry in the code (cartography §9
lines 215–231 lists no inventory module). `engine/pricer.py:1-90` emits a
per-quote `TheoOutput` and stops; no aggregator reads it. The corpus
formula (C08-73: $\sum_i q_i \Delta_i^K$, divided by $N_{ZS}=5{,}000$)
is not present.

**(2) What triggers a hedge — threshold, schedule, event?** Nothing
triggers a hedge because no hedge runner exists. The corpus prescribes a
delta-magnitude threshold (C10-61: one-ZS-contract equivalent), an
event-driven option overlay (C10-67), and Milestone-3 reconciliation
three times per session (C10-80). None exist in code. The
`engine/scheduler.py:36-56` priority-queue skeleton — the natural trigger
substrate — is unwired (cartography red flag #5).

**(3) Which instrument is used (ZS future, ZS option, basket)?** None.
The corpus prescribes ZS futures by default (C10-60) with an optional
short-dated-weekly-option vertical-spread overlay (C08-77, C10-62,
C10-80). The codebase contains no instrument-selection enum, no
`cme_symbol`-resolved soybean entry (`cme_symbol` is populated only for
WTI per `config/commodities.yaml`), and no order builder. The string
`ZSK26` (the corpus-named hedge instrument for the April 24, 2026 Event
per C07-15) does not appear anywhere in the codebase.

**(4) What is the cost threshold (don't hedge below N USD)?** None. The
corpus prescribes two thresholds: a delta-magnitude floor of one ZS
contract (C10-61) and an option-spread breakeven (C10-63 / C10-64). The
codebase encodes neither. The closest configured numeric threshold is the
per-tick staleness gate in `state/basis.py:22` (30,000 ms) and the per-
commodity `pyth_max_staleness_ms` in `config/commodities.yaml:7-9`,
neither of which is a hedge cost.

**(5) How is basis risk between Pyth/CME/Kalshi accounted for?** Only
the *Pyth↔CME annualized drift* is modelled (`state/basis.py:1-49`), and
only as forward drift inside GBM. The corpus specifies three additional
*hedge-specific* basis components (C08-81, C10-66) — reference-price
basis (Kalshi snapshot vs CME settle/close/VWAP), timing basis (non-CME-
standard Friday), and contract-month basis (roll-week deferred-month
options). None is in code. The shared name `basis` is overloaded: same
word, different object — this is the `wrong` classification.

**(6) What happens when CME is closed but Kalshi is open (and vice
versa)?** The corpus (C10-72, C10-73) says practitioners pull or
radically widen quotes when CBOT is closed (Fri 13:20 CT through Sun
19:00 CT), and the Sunday-evening reopen is itself a known volatility
regime. The code's `engine/event_calendar.py` implements *only* the WTI
session (cartography §9 line 224, red flag #14): every non-WTI commodity
raises `NotImplementedError` at `engine/event_calendar.py:98` the moment
the pricer asks for its τ. There is no soybean session, no CBOT-closed
handler, and no quote-pull primitive on the (also absent) order layer.
CME-closed/Kalshi-open behaviour is undefined.

## 5. Ambiguities

- **Intent of `state/basis.py`.** The file's docstring (lines 1–10) calls
  itself a "primitive version" of a basis model "designed so that upgrade
  is additive — callers only see `get(commodity, now_ns)`." It is silent on
  whether the upgrade direction is towards (a) an AR(1)-fit *Pyth↔CME*
  drift refinement (referenced at line 4: "Deliverables 3+ replace this
  with the AR(1)-fit model specified in calibration/"), or (b) a multi-leg
  *Kalshi↔CME-option-reference* basis as in C08-81 / C10-66. Reading the
  docstring narrowly, the intent is (a). Reading the file name in the
  context of a hedging audit, a maintainer could infer (b). I have
  classified this as `wrong` for the hedge-basis claim; the row could
  instead be classified `divergent-intentional` if a maintainer confirms
  intent (a) was a deliberate scope choice. Evidence both ways:
  - For (a): the docstring at `state/basis.py:1-10`, the cartography
    description at §9 line 217 ("annualized Pyth↔CME basis drift").
  - For (b): no evidence in code; the `README.md` does not name basis
    risk as in or out of scope.

- **`models/gbm.py` and digital delta.** GBM emits $\Phi(d_2)$ in
  `gbm.py:1-105` per cartography §9 line 220. The closed-form companion
  $\phi(d_2)/(S\sigma\sqrt{T-t})$ for digital delta (C08-71) is one
  numba-jitted statement away. Whether the omission is "we plan to add
  this once a hedge consumer exists" or "we plan never to add this" is
  not signalled in the code. There is no `# TODO` comment naming a
  hedge consumer.

- **`engine/scheduler.py` and the absent producer.** The Scheduler defines
  five priority enum values (`TICK`, `IV_UPDATE`, `BASIS_UPDATE`,
  `EVENT_CAL`, `TIMER`) at `engine/scheduler.py:36-56` per cartography §9
  line 223. None is named "HEDGE" or "ORDER". A hedge producer would
  conventionally enqueue at a separate priority, suggesting the design
  did not foresee a hedge integration; alternatively, a hedge event
  could be encoded as `TIMER`. This is not resolved in code.

- **`config/commodities.yaml` soybean stub.** Per cartography §6 line 152
  and §10 item 7 lines 264–270, soybean (and several other commodities)
  carry `stub: true` and bypass model instantiation in
  `models/registry.py:67-68`. Whether soybean is "intentionally
  out-of-scope today" or "will be filled in later" is not resolvable from
  the YAML alone. The README does not disambiguate.

## 6. Open questions for maintainers

1. Is the absence of a hedging layer intentional, scoped-out for
   Deliverable 1, or a known gap (the docstring of `state/basis.py:4-6`
   references a "Deliverable 3+" upgrade, but only for the AR(1) basis-
   drift model)? A scope statement in `README.md` would resolve C08-108 /
   C10-80 immediately.

2. Where will per-bucket inventory live — a new `state/positions.py`,
   inside `engine/pricer.py`, or imported from a Kalshi REST client when
   one exists? C08-73 / C10-60 need a canonical position store before
   any hedge sizer can be written.

3. Is `state/basis.py` intended to grow into a multi-component basis
   tracker (Pyth↔CME drift *plus* Kalshi-snapshot↔CME-option reference
   basis), or will the latter live in a new module? If shared, the
   `BasisModel` interface needs a key beyond `commodity`.

4. Is `TheoOutput` (`models/base.py:1-69`) intended to grow Greeks fields
   (`delta`, `gamma`, `vega`), or will Greeks live in a parallel
   `engine/greeks.py`? This sets the mount point for C08-71 / C08-75.

5. What is the planned hedge-side connector? The corpus lists Interactive
   Brokers, AMP, and Tradovate (C10-80). The repo declares
   `httpx >= 0.27` and `structlog >= 24.1` (cartography §10 item 3) which
   are unused today; were these reserved for the broker REST client?

6. Will `engine/event_calendar.py` be extended to express CBOT soybean
   sessions, or is the WTI hard-code (cartography §10 item 14)
   intentional? C10-65 and C10-72 / C10-73 both need a soybean-aware
   calendar.

7. Will the C09-73 kill-switch be implemented as four watchdogs on the
   `engine.scheduler` priority queue, as a single supervisor process, or
   as Kalshi `DELETE /orders/batch` plus broker IOC-cancel calls? The
   choice determines whether `engine/scheduler.py` needs a new priority
   value or whether the kill-switch lives outside the scheduler entirely.

8. What is the planned reconciliation-table schema (C09-79, C09-80)?
   `audit_C_phase09_kalshi_stack.md:103` flags that the corpus does not
   propose one.

9. Will the C08-88 aggregate-delta cap live in `validation/sanity.py`
   (currently per-`TheoOutput` per cartography §9 line 226) or in a new
   `validation/portfolio.py`?

10. Is `calibration/` (cartography §9 line 229: empty stub) the intended
    home for empirical fill-intensity / cross-asset-intensity /
    Σ-perturbation work that hedging-adjacent claims (C02-87, C08-105)
    require?
