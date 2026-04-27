# Audit Phase D — Topic 6 of 10: Inventory Tracking and Risk Limits

## 1. Scope

Phase D Topic 6 audits the codebase against research claims tagged `inventory`
in the Phase C distillations, restricted by the topic statement to
*inventory tracking and risk limits* (per-bucket caps, aggregate net delta,
gamma/vega caps, scenario stresses, kill-switch triggers, and the feedback
of inventory state into quoting — skew or widening). Per the audit prompt,
the prioritised research sources are Phase 02 (pricing models / inventory),
Phase 08 (Kalshi pricing synthesis), and Phase 10 (strategy synthesis); to
satisfy the "Filter to claims tagged `inventory`" instruction, all
`inventory`-tagged rows from Phase C are eligible, but I exclude commodity-
stockpile / fundamentals rows whose `inventory` tag refers to soybean
*physical* stockpiles rather than the trading book (those are listed in §4
Ambiguities so the bookkeeping is auditable).

The Phase A cartography (`audit/audit_A_cartography.md:213-230`) lists
sixteen modules. None has a responsibility that touches inventory tracking,
position limits, risk engines, loss limits, or margin utilisation: the
runtime modules are a Pyth feed (`feeds-pyth`), tick / IV / basis state
stores (`state-tick-store`, `state-market-surfaces`, `state-errors`), a
pricing-model interface and one live model
(`models-interface`, `models-gbm`, `models-registry`), a repricer
(`engine-pricer`), a (unwired) async scheduler (`engine-scheduler`), a
trading-hour calendar (`engine-calendar`), a pre-publish sanity invariant
checker (`validation-sanity`), a benchmark harness, configuration, tests,
and an empty `calibration` package. Cross-checking the Phase B deep-dive
set (`audit/audit_B_*.md`) confirms no Phase B file's "responsibility"
section discusses inventory, position limits, risk gating, kill switches,
or margin: every reference to "inventory" inside Phase B files refers to
the *Phase A module inventory* (a table of the codebase's modules), not to
trading-book inventory. The expected-empty Phase B deep-dive set for this
topic is therefore confirmed empty; no Phase B file applies. All Phase C
files referenced below are present in `./audit/`; no halt condition fires.

The relevant code surface for this topic is therefore *the cartography
itself*: there is no `state/positions.py`, no `state/risk.py`, no
`engine/risk.py`, no `engine/quoter.py`, no `engine/kill_switch.py`, no
`feeds/kalshi*.py`, no `oms/` package, and no module named anything close.
A `grep` for `inventory|position|risk|kill|loss|margin|reservation|skew|gamma|vega|delta|cap|limit|hedge`
over `*.py` produces only (a) `state/tick_store.py:34, 70`'s ring-buffer
`capacity`, (b) `validation/sanity.py:17`'s comment about "analytical
limits" of the GBM theo, and (c) `tests/test_gbm_analytical.py:64`'s
`test_gbm_boundary_limits` — none of which is a position / risk concept.
The repository self-describes (`README.md:3`) as a "Live Kalshi commodity
theo engine," which is a *pricing* engine that emits `P(S_T > K)`; it does
not own a book, does not place orders, and does not size hedges. Accordingly,
nearly every inventory-tagged claim in Phase C maps to a `missing` gap
class with a cartography pointer rather than a code-line citation, in the
"no-module-exists case" allowed by the audit prompt.

## 2. Audit Table

| C-id | Claim (1-line) | What code does | Gap class | Severity | Code citation(s) | Notes |
|---|---|---|---|---|---|---|
| C02-01 | A market maker faces three risk sources: inventory, adverse selection, volatility/jump. | None of the three is represented in code; only volatility enters the pricer (as $\sigma$). | missing | major | `audit_A_cartography.md:213-230` (no risk module); `engine/pricer.py:71` (sigma only) | Adverse-selection and inventory risk sources are absent at every layer. |
| C02-03 | Cash/inventory dynamics $dX_t = (S+\delta^a)dN^a-(S-\delta^b)dN^b$, $dq_t = dN^b-dN^a$. | No $X_t$, no $q_t$, no $\delta^{a,b}$, no fill events. | missing | blocker | `audit_A_cartography.md:213-230` | Fundamental state variables of any market-making system are not tracked. |
| C02-04 | Quoting objective: max $U(X_T+q_TS_T)$ or expected P&L less quadratic inventory penalty. | No optimisation, no objective function, no P&L. | missing | major | `audit_A_cartography.md:213-230` | Engine is a pricing engine, not a control engine. |
| C02-05 | Ho–Stoll optimal half-spread $\delta^{a,b} = \tfrac{1}{2}s \mp \gamma\sigma^2(T-t)q$. | No spread is computed; output is a probability vector. | missing | major | `models/gbm.py` (theo only); `audit_A_cartography.md:220` | No quoter exists to consume a half-spread. |
| C02-06 | Ho–Stoll reservation price $r = S - \gamma\sigma^2(T-t)q$. | No reservation price is computed. | missing | major | `audit_A_cartography.md:213-230` | A canonical inventory-skew formula has no host. |
| C02-07 | A long-inventory dealer quotes lower bid and lower ask (skew against inventory). | No dealer state, no quoting, no skew. | missing | blocker | `audit_A_cartography.md:213-230` | Direct file-specific audit question on skew → not answerable, because there is no quote. |
| C02-09 | Grossman–Miller concession $P_1 - E[P_2] = a\sigma^2_\epsilon i/(M+1)$. | No concession term anywhere. | missing | nice-to-have | `audit_A_cartography.md:213-230` | Theory-side claim; downstream of having a quoter. |
| C02-10 | Supply of immediacy is endogenous; effective $M$ falls with volatility. | No notion of $M$ or immediacy supply. | missing | nice-to-have | `audit_A_cartography.md:213-230` | Would only matter once a quoter exists. |
| C02-11 | Post-WASDE LOB depth collapses, widening Grossman–Miller concession. | No WASDE detection, no depth model, no concession. | missing | major | `config/commodities.yaml:18-29` (event_calendar declared but stub for WTI only); `audit_A_cartography.md:223` (event_calendar.py is a τ calculator, not a regime engine) | WASDE-day event calendar exists in YAML but is not wired to any spread/concession logic. |
| C02-24 | A–S reservation price $r = S - q\gamma\sigma^2(T-t)$. | Same as C02-06: no reservation price. | missing | major | `audit_A_cartography.md:213-230` | A–S formula has no implementation site. |
| C02-27 | Spread independence from inventory in baseline A–S is a CARA + exp-intensity artefact; relax for inventory-dependent spreads. | No spread, no intensity model, no CARA utility. | missing | minor | `audit_A_cartography.md:213-230` | Subsumed by C02-04, C02-05. |
| C02-28 | GLFT asymptotic ask $\delta^{a*}(q) \approx \tfrac{1}{\gamma}\ln(1+\gamma/k) + \sqrt{\sigma^2\gamma/(2kA)\cdot g}\cdot(2q+1)$. | No GLFT machinery. | missing | major | `audit_A_cartography.md:213-230` | Phase 02 §8 names this as practitioner-stack item 2. |
| C02-30 | GLFT imposes hard inventory bounds $q\in\{-Q,\dots,+Q\}$. | No $q$, no $Q$, no bound. | missing | blocker | `audit_A_cartography.md:213-230` | This is the canonical per-bucket position cap construct in the literature. |
| C02-33 | Guéant multi-asset cross-asset inventory penalty. | No multi-asset book, no cross-asset penalty. | missing | major | `audit_A_cartography.md:213-230` | Foundational for the cross-bucket-skew claims (C08-47 et seq., C10-52). |
| C02-43 | Under Heston, A–S reservation price is $r_t = S_t - q_t\gamma v_t(T-t)$. | No Heston, no $v_t$ as state, no reservation price. | missing | minor | `audit_A_cartography.md:213-230` | Models registry currently has only `gbm` live (`models/registry.py:32-38`). |
| C02-54 | Deaton–Laroque non-negativity-of-inventory induces non-linear AR with stockout explosions. | No fundamentals model. | missing | nice-to-have | `audit_A_cartography.md:213-230` | Macro inventory; only indirectly relevant to book-side caps. |
| C02-55 | Routledge–Seppi–Spatt: convenience yield is endogenous, function of inventory state. | No convenience yield, no curve model. | missing | nice-to-have | `audit_A_cartography.md:213-230` | Same scope note as C02-54. |
| C02-56 | Reservation-price drift should mean-revert when inventories are extreme. | No drift-augmenting term. | missing | minor | `audit_A_cartography.md:213-230` | Only `basis_drift` exists as a constant in the GBM input (`engine/pricer.py:72, 83`). |
| C02-79 | Practitioner stack item 2: skew $r$ against inventory à la Ho–Stoll/A–S, with hard GLFT cap. | No skew, no cap. | missing | blocker | `audit_A_cartography.md:213-230` | Synthesises the per-bucket cap and skew questions in one row. |
| C02-82 | Practitioner stack item 5: risk-manager hard limits (notional, delta, gamma) supersede optimiser output. | No risk manager, no hard limits, no optimiser. | missing | blocker | `audit_A_cartography.md:213-230` | Direct file-specific audit question on per-bucket caps + delta/gamma caps → not answerable. |
| C02-90 | Pricing models do not set risk limits (inventory caps, loss-per-day, liquidity covenants); these are exogenous and truncate the policy. | The pricing layer indeed sets no risk limits — but no exogenous truncation layer exists either, so the policy itself is undefined. | missing | major | `engine/pricer.py:1-91`; `audit_A_cartography.md:213-230` | Letter-of-claim is satisfied (the pricer sets no risk limits); spirit-of-claim (an exogenous limit layer exists outside the pricer) is not. |
| C08-40 | Per-bucket A–S reservation $r_i(t) = m_i(t) - q_i\gamma_i\sigma_{m_i}^2(T-t)$. | No bucket model, no $q_i$, no $r_i$. | missing | blocker | `audit_A_cartography.md:213-230` | Kalshi bucket structure absent. |
| C08-45 | Cartea–Jaimungal–Penalva multi-asset HJB with cross-bucket covariance $\Sigma_{ij}$. | No HJB, no covariance, no buckets. | missing | major | `audit_A_cartography.md:213-230` | Subsumes C08-47/48/49. |
| C08-47 | Multi-asset matrix-skew reservation $r_i = m_i - \gamma(T-t)\sum_j\Sigma_{ij}q_j$. | No matrix skew, no $\Sigma$. | missing | major | `audit_A_cartography.md:213-230` | The cross-inventory skew claim. |
| C08-48 | Long bucket $i$ should lower bucket $i$'s quote *and* adjacent $j$'s via $\Sigma_{ij}$. | No quoting, no adjacency. | missing | major | `audit_A_cartography.md:213-230` | Direct file-specific audit question on inventory feedback into quoting → unanswerable. |
| C08-49 | Matrix-skew = formal generalisation of GLFT's hard-inventory-cap to multi-asset discrete case. | No GLFT, no per-bucket cap, no matrix. | missing | major | `audit_A_cartography.md:213-230` | Same code surface absent. |
| C08-73 | Aggregate book delta $\Delta^{\text{port}} = \sum_i q_i\Delta_i^K$; ZS-futures hedge is $-\Delta^{\text{port}}/N_{ZS}$. | No book delta, no hedge sizer, no ZS leg. | missing | blocker | `audit_A_cartography.md:213-230` | Direct audit question on aggregate net delta cap → answer is "no aggregator exists." |
| C08-82 | Kalshi positions are fully cash-collateralised: $0.30 Yes costs $0.30. | No collateral accounting, no positions. | missing | major | `audit_A_cartography.md:213-230` | Capital-utilisation claim. |
| C08-83 | CME ZS futures SPAN-margin at ~5–8% of notional. | No CME side, no margin model. | missing | minor | `audit_A_cartography.md:213-230` | Hedge-side margin. |
| C08-84 | ZS option vertical spreads SPAN-margin on portfolio variance. | No options side. | missing | minor | `audit_A_cartography.md:213-230` | Hedge-side margin. |
| C08-85 | Kalshi leg is the binding capital constraint in most hedged trades. | No capital model. | missing | minor | `audit_A_cartography.md:213-230` | Margin utilisation file-specific question → unanswerable. |
| C08-86 | Rule 5.19 max-loss cap → 83 333 contracts on a $0.30 Yes (per assumed $25 k cap). | No Kalshi limits engine. | missing | major | `audit_A_cartography.md:213-230` | Direct per-bucket position cap question. |
| C08-87 | MM-Program raises per-bucket caps ~10×. | No MM-Program flag, no caps. | missing | minor | `audit_A_cartography.md:213-230` | Conditional on C08-86. |
| C08-88 | The binding constraint is a book-level aggregate net delta cap on unhedged $\Delta^{\text{port}}$. | No aggregate cap. | missing | blocker | `audit_A_cartography.md:213-230` | Direct file-specific audit question. |
| C08-89 | Required scenario tests: (i) WASDE-day P&L; (ii) weather-shock 3–5 % gap with Bates-SVJ; (iii) expiry-day liquidity-collapse marks-to-intrinsic. | No scenarios run anywhere. | missing | blocker | `audit_A_cartography.md:213-230` | Direct file-specific audit question on scenario-based limits. |
| C08-105 | Pipeline stage F — reservation price using $\Sigma_{ij}$ from RND perturbation. | Pipeline stage F is unimplemented. | missing | major | `audit_A_cartography.md:213-230` | The whole A→L pipeline is absent. |
| C08-109 | Pipeline stage J — risk gating: enforce per-bucket and aggregate-delta caps; stress-test; block quotes. | No risk gating. | missing | blocker | `audit_A_cartography.md:213-230` | Direct file-specific audit question on every cap and on kill-switch behaviour at the gate. |
| C09-73 | Kill-switch fires on (i) aggregate signed delta breach; (ii) intraweek P&L drawdown stop; (iii) hedge heartbeat fail; (iv) WS reconnect storm. | The pricer raises on missing/stale state per market (`engine/pricer.py:62-69, 75`); this is *not* a kill-switch — it kills one quote, not the engine, and operates on input invariants, not on book risk. No global kill-switch exists. | missing | blocker | `engine/pricer.py:62-75`; `audit_A_cartography.md:213-230` | Direct file-specific audit question on kill-switch triggers (loss thresholds, error thresholds). The "raise rather than publish" stance covers (a single subset of) error thresholds at the *theo* layer, not the *book* layer. |
| C09-74 | A `reduce_only` retry layer reopens quotes only after a cold-start check. | No retry layer, no orders. | missing | minor | `audit_A_cartography.md:213-230` | Conditional on having an OMS. |
| C09-75 | Rule 5.19 expresses Kalshi position limits in dollars of max loss, default $25 k/member. | No representation of the rule. | missing | major | `audit_A_cartography.md:213-230` | Same surface as C08-86. |
| C09-76 | Engine tracks per-bucket and per-Event signed exposure in dollars vs. Appendix-A limit. | No exposure tracker. | missing | blocker | `audit_A_cartography.md:213-230` | Restates the per-bucket-cap question in $\$$ terms. |
| C09-77 | A `buy_max_cost` dollar cap on every `POST /orders` call provides a per-request second-layer limit. | No order-submission code. | missing | major | `audit_A_cartography.md:213-230` | Per-request limit is a layered defence. |
| C09-78 | The CME hedge leg carries broker-imposed initial / maintenance margin and daily loss tripwires. | No CME side. | missing | minor | `audit_A_cartography.md:213-230` | Hedge-side risk plumbing. |
| C10-05 | Multi-asset bucket grid quoting with A–S / Cartea–Jaimungal–Penalva. | No bucket quoter. | missing | blocker | `audit_A_cartography.md:213-230` | Restates C08-45/47 from the strategy angle. |
| C10-52 | Cross-inventory reservation $r_i = m_i - \gamma(T-t)\sum_j\Sigma_{ij}q_j$ with $\Sigma_{ij}$ from RND perturbation. | No matrix skew. | missing | major | `audit_A_cartography.md:213-230` | Phase-08 / Phase-10 alignment claim. |
| C10-53 | When the operator becomes long bucket $i$, all adjacent buckets' mids are skewed to reduce aggregate exposure. | No quoting state propagation. | missing | major | `audit_A_cartography.md:213-230` | Direct file-specific audit question on inventory→quote feedback. |
| C10-54 | Cross-inventory term is a market-maker-specific edge against retail / small-prop counterparties who skew only the filled bucket. | No edge claim implementable absent quoter. | missing | minor | `audit_A_cartography.md:213-230` | Strategy framing of C08-48. |

The 46 rows above all carry a Phase C research citation (the `C##-##`
identifier) and either an explicit code citation
(`engine/pricer.py:62-75`, `engine/pricer.py:1-91`, `engine/pricer.py:71-72,
83`, `models/gbm.py`, `models/registry.py:32-38`, `validation/sanity.py:17`,
`config/commodities.yaml:18-29`, `state/tick_store.py:34, 70`) or a
cartography pointer (`audit_A_cartography.md:213-230`) for the
no-module-exists case explicitly permitted by the audit instructions. Total
distinct research citations span Phase 02 (sixteen claims), Phase 08
(thirteen), Phase 09 (six), and Phase 10 (four), comfortably above the
ten-citation minimum.

## 3. Narrative — blockers and majors

The dominant pattern is a single structural finding: *the codebase is a
theo (probability) engine, not a market-making system, and inventory
tracking and risk limits are entirely outside its current scope.* That
pattern produces every blocker and most majors in the table above; rather
than narrate each row, this section groups them under the file-specific
audit questions the prompt enumerated, summarises what evidence I found,
and explains why the gap class is `missing` even where partial primitives
exist that look superficially related.

**Per-bucket position caps (C02-30 GLFT; C02-79 practitioner stack item 2;
C08-86 Rule 5.19 dollar-loss cap; C08-87 MM-Program 10× exemption; C09-75
Rule 5.19 default $25 k; C09-76 per-bucket / per-Event signed-exposure
tracker).** None of these is represented in code. The repository contains
no `state/positions.py`, no Kalshi-side ingest from
`/portfolio/positions`, and no module that records signed exposure per
ticker. The only `cap` literal in the Python sources is
`state/tick_store.py:34` and `state/tick_store.py:70`'s
`capacity = 1_000_000` ring-buffer size, which is a tick-history cap, not
a position cap. The `models/registry.py` keyed by commodity (lines 32–38)
maps a commodity *name* to a pricing-model builder, not to a position
schema. There is no Kalshi `KXSOYBEANW` market identifier anywhere in the
codebase (`grep -i kalshi` finds three references — all in comments or
docstrings: `engine/event_calendar.py:4`, `state/iv_surface.py:9`, and
`tests/test_end_to_end.py:69`). The `KXSOYBEANW` bucket grid required by
C08-86 is therefore not a data structure that the pricing engine could
*populate* with position counts even hypothetically. The rows are
classified as `missing` rather than `partial`; severity is `blocker` for
C02-30, C02-79, C08-86, and C09-76 because per-bucket caps are the
load-bearing primitive that any quoter must own before placing an order.

**Aggregate net delta cap (C08-73 $\Delta^{\text{port}}$ definition;
C08-88 binding constraint claim; C08-109 risk-gating stage J; C09-73
trigger (i)).** Bucket delta $\Delta_i^K = \partial m_i/\partial S$ is a
quantity that the codebase could in principle compute (it would require
finite-differencing the model's `price()` output across a perturbed spot
and integrating per-bucket), but no such code path exists. The pricer
returns the model's raw `P(S_T > K)` vector and routes it through
`SanityChecker.check()` (`validation/sanity.py:38-68`) which validates
finiteness, $[0,1]$ range, monotonicity, and shape consistency — not
deltas, not aggregates, not exposures. The aggregate-delta cap is the
single biggest "what could plausibly be retrofitted onto this engine"
question in the audit, and the answer is: nothing of it exists today.
Severity is `blocker` for C08-73, C08-88, C08-109, and C09-73 because
without an aggregator, no caps over $\Delta^{\text{port}}$ can be evaluated
or enforced.

**Gamma and vega caps.** No claim in the Phase C inventory-tagged corpus
explicitly demands a gamma cap or a vega cap as a free-standing primitive
— C02-82's "(notional inventory, delta, gamma)" is the closest. C08-75
(bucket gamma is large near edges, small in the interior) and C08-76 (ATM
Yes contracts carry substantial gamma not neutralisable with futures) are
tagged `hedging`, not `inventory`, so they are out-of-topic for this
audit. The audit prompt's file-specific question on gamma / vega caps is
therefore answered by C02-82's blocker row plus the absence of any
gamma / vega aggregator: code-side, neither $\Gamma_i^K = \partial^2
m_i/\partial S^2$ nor a vega field is computed, stored, or capped. The
GBM kernel (`models/gbm.py`) returns a probability vector only; there is
no Greeks API on `TheoOutput` (`models/base.py`).

**Scenario-based limits (C08-89 WASDE-day / weather-shock / expiry-day
liquidity-collapse).** `config/commodities.yaml:18-29` declares an
`event_calendar[]` for WTI with named events, day-of-week, time, and a
`vol_adjustment` multiplier; `engine/event_calendar.py` is named after this
and would be a plausible host, but inspection shows it is purely a
*trading-hour τ calculator* (per its docstring at lines 1–18; per the
Phase A inventory at `audit_A_cartography.md:223`). It does not stress-test
P&L under WASDE moves (the engine has no P&L), it does not parameterise a
weather-shock gap, and it does not model expiry-day liquidity collapse.
The `vol_adjustment` field declared in YAML for WASDE / Crop Progress /
Daily Halt has no code reader (a `grep` for `vol_adjustment` returns the
YAML alone). Severity is `blocker` for C08-89 because scenario stress is
the explicit gating step in the recommended pipeline (stage J).

**Kill-switch triggers — loss thresholds and error thresholds (C09-73
four-trigger spec; C09-74 reduce-only retry).** This is the one area
where a partial primitive *could* be argued to exist, and where I want to
be explicit about why I still classify the rows as `missing` rather than
`partial`. The pricer raises `StaleDataError` if the Pyth tick is older
than `pyth_max_staleness_ms`, raises `InsufficientPublishersError` if
`tick.n_publishers < min_publishers`, and raises `ValueError` if
$\tau \le 0$ (`engine/pricer.py:62-75`); the `SanityChecker` raises
`SanityError` on invariant failure (`validation/sanity.py:38-68`). The
README enshrines this as a non-negotiable: "stale Pyth publishers,
out-of-bounds IV, feed dropouts → raise, don't publish" (`README.md:63`)
and the docstring of the pricer says "A wrong theo trades; a missing theo
doesn't" (`engine/pricer.py:12`). This *is* a fail-safe pattern, but
classifying it as a partial implementation of C09-73 would be wrong on
two counts: (a) C09-73 is a kill-switch over the *book* (delta breach,
P&L drawdown, hedge heartbeat, WS reconnect storms), not over a single
quote's input invariants; (b) the pricer's raise kills *that one
reprice*, propagates to the caller, and (in the current repo) is not
caught anywhere — there is no global "stop quoting" state, because there
is no quoting state to stop. Trigger (iii) (CME hedge connectivity
heartbeat) is impossible to implement absent any CME connectivity.
Trigger (iv) (Kalshi WS reconnect storm) is impossible absent any Kalshi
WebSocket. Severity is `blocker` for C09-73; the partial fail-safe at
the theo layer is real and worth preserving but does not reduce the gap
class.

**How does inventory feed back into quoting? (C02-07 skew against
inventory; C08-47 / C08-48 matrix skew across adjacent buckets; C10-52 /
C10-53 cross-inventory reservation price).** The codebase does not quote.
There is no quote object, no `BidAsk` dataclass, no
`engine/quoter.py`, no `feeds/kalshi*.py` for posting orders. The
research's central claim — that a long position in bucket $i$ should
lower bucket $i$'s mid (own-inventory) and lower adjacent buckets'
mids (cross-inventory via $\Sigma_{ij}$) — has no code surface to live
in. Severity ranges from `major` to `blocker` depending on whether the
claim is the bare-minimum skew (Ho–Stoll, single-asset, blocker per the
practitioner stack) or the multi-asset matrix-skew refinement (major,
because it is conditional on the prior claim being implemented first).

**Fail-safes worth flagging that *are* present.** Two patterns deserve
mention even though they do not change any gap classification: the
"raise rather than publish" stance at `engine/pricer.py:62-75` and the
post-compute invariant suite at `validation/sanity.py:38-68`. Neither is
a risk-limits primitive — they are *theo-correctness* primitives — but
they are the only "block before publishing" surfaces in the repository,
and any future risk-gating stage (the J-stage of C08-109) would
plausibly hang off the same `raise → don't publish` discipline. They
are not classified as `already-good` for any C-row because no inventory-
tagged claim asserts that an engine should raise on theo invariant
violations: the closest claim, C09-73 trigger-set, is about book risk,
not theo correctness, so the existing primitive is adjacent rather than
implementing.

## 4. Ambiguities

The `inventory` tag in Phase C is overloaded. It is applied to (a)
trading-book inventory (e.g. C02-04, C08-40, C09-76) — the topic of this
audit; (b) commodity-stockpile / fundamentals state (e.g. C01-04 USDA
ending stocks, C01-72 Grain Stocks report, C04-12 calendar-spread
inversion as a stocks-tightness signal, C05-19 Working/Brennan storage
curve); and (c) data-vendor catalogue items that touch stockpile
fundamentals (C03-14 DTN ProphetX, C03-16 Barchart cmdty, C06-64 COT,
C06-86 CME Daily Bulletin). The audit prompt's file-specific questions
are unambiguous about the (a) sense, but a strict reading of "claims
tagged `inventory`" includes (b) and (c). I have excluded the (b) and (c)
rows from the audit table on the topic-statement reading; if a stricter
filter were applied, every (b) / (c) row would also be `missing` because
the codebase has no fundamentals ingest, no stockpile representation,
and no COT reader, and would carry the same cartography pointer.

A second ambiguity concerns the boundary between "pricing engine sets no
risk limits because that is correctly out of scope (C02-90)" and
"pricing engine sets no risk limits because the truncating layer is
absent." C02-90 says risk limits are exogenous and truncate the policy.
The prototype here is closer to the first reading: the pricing layer
holds itself to its narrow scope (theo correctness, fail-on-staleness),
and the absent risk layer is acknowledged in the "Status" line of the
README (`README.md:6-8` — "Deliverable 2: benchmark harness + budget
tests"). A reader could argue this is `divergent-intentional`, not
`missing`. I have classified it `missing` because no risk-gating module
is *named* anywhere as the next deliverable; the README's roadmap stops
at benchmarking, and the empty `calibration/` package is the only
explicit "to be filled" placeholder.

A third ambiguity: C08-87 (MM-Program 10× cap exemption) and C08-86
(default $25 k cap) depend on Phase 07 Appendix A, which Phase 08 itself
flags as unread (cross-link in `audit_C_phase08_synthesis_pricing.md:225`
via C08-86 and C08-36). The codebase cannot implement a cap whose
numeric value is a research open-question, but it could implement a
configurable-cap *interface* — and that interface is also missing. I
have classified C08-86 as `missing` (interface absent) rather than
`partial` (interface present but unconfigured), but a maintainer who
intends to ship the interface stub before resolving Appendix A would
read the row as conditional.

A fourth ambiguity: the four `inventory` rows in Phase 02 §7.2 (C02-54
Deaton–Laroque, C02-55 Routledge–Seppi–Spatt, C02-56 reservation-price
mean-reversion at extreme inventories, and C02-57 forward-curve carry)
are about commodity-stockpile macroeconomics, but their pricing-model
implications (mean reversion in $r$) live closer to the trading-book
side of the line. I have included C02-56 as a book-side claim
(reservation-price drift is a book-side primitive) and C02-54 / C02-55
as borderline; severity `nice-to-have` reflects that book-side caps
should be implemented before macro stockpile drivers tilt the
reservation price.

## 5. Open questions for maintainers

1. Is the "Live Kalshi commodity theo engine" framing on `README.md:3`
   a forward-looking aspiration or a current-state description? The
   repository today has zero Kalshi-side code (no order client, no
   `/portfolio/positions` reader, no rate-limit queue, no fill ingest);
   if Kalshi connectivity is on the near-term roadmap, the per-bucket
   cap and aggregate-delta cap interfaces should land before any order
   client does, so that posting an order without a populated cap is
   unrepresentable. If Kalshi connectivity is *not* on the near-term
   roadmap, the README line should be tightened to "theo engine for
   Kalshi commodity markets" (no quoting promised) so that the absence
   of a risk-gating module is not read as a missing roadmap deliverable.

2. Is the `calibration/` empty package
   (`audit_A_cartography.md:62-63, 229`) intended to host risk
   primitives (per-bucket caps, scenario stress generators, kill-switch
   thresholds) or only the four jobs the README lists ("vol, jump MLE,
   HMM fit, IV event strip", `README.md:43`)? The Phase D Topic 6 audit
   has nowhere obvious to point a future contributor.

3. Will the `event_calendar` YAML's `vol_adjustment` field
   (`config/commodities.yaml:18-29`) be wired into a regime-switching
   spread multiplier (Phase 02 §7.4 best-practice; C02-65 not in the
   inventory tag-set but adjacent), or is it dead config? The same
   field is the natural input to scenario stress (C08-89 WASDE-day P&L)
   and to the kill-switch loss-threshold computation (C09-73 trigger
   ii) — a single decision on this field affects three otherwise-
   independent risk-limits questions.

4. Is the per-quote raise discipline at `engine/pricer.py:62-75` and
   `validation/sanity.py:38-68` intended to remain *theo-only*, or will
   it be promoted to a book-level kill-switch that also halts on book
   exposure / hedge / connectivity events (C09-73)? If the latter, the
   pattern needs a global state object (currently there is none) and a
   re-arm protocol (currently there is none) — both would be net new
   primitives, not extensions of existing code.

5. Phase 09 §8 (C09-77, `buy_max_cost`) describes a per-request dollar
   cap as a layered defence over the per-bucket cap. If a future order
   client lands in `feeds/`, will `buy_max_cost` be enforced at the
   client wrapper or at a separate risk-gating layer? The audit prompt
   distinguishes per-bucket caps from kill-switch triggers and from
   skew/widening; `buy_max_cost` straddles all three (it is a per-
   bucket cap implemented at request time, gated by a kill-switch
   condition, that effectively widens or pulls a quote). Maintainer
   intent on whether this is one module or three would resolve a
   non-trivial layering question now, before anyone writes the order
   client.

6. The cross-bucket covariance $\Sigma_{ij}$ (C08-45, C08-47, C08-105,
   C10-52) is research-open even before a code path exists (C10-OQ-05).
   Should the eventual reservation-price layer ship with a perturbation-
   based estimator (per C08-105) or a stub identity matrix that is
   honest about the modelling debt? The audit identified no preferred
   answer in research; maintainer judgment is the gating input.

7. Phase 10 milestone M2 (C10-79 sandbox caps: $500 max-loss per bucket,
   $5 000 aggregate Event) defines numerical risk-limit values that
   would go into a hypothetical risk-gating module. Is the intent to
   load these from `config/` (mirroring `commodities.yaml`'s
   per-commodity overrides) or to wire them into a Python literal?
   Either is implementable; the question is which one is the codebase's
   convention, and no precedent exists.
