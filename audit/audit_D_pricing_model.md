# Audit D — Topic 1 of 10: Pricing Model and Quoting Logic

Phase D pass over `pricing-model`-tagged claims from the Phase C corpus,
mapped onto the live code as documented in Phase B. The repository's
self-description is "Live Kalshi commodity theo engine" (`README.md:3`,
flagged in `audit/audit_A_cartography.md:243-245`); the Phase C corpus
specifies a Kalshi weekly soybean range-grid market-making system whose
pricing layer is the Avellaneda–Stoikov / Cartea–Jaimungal control
machinery applied to a Breeden–Litzenberger-extracted risk-neutral
density. The code, as of HEAD on the working branch, is a single-model
GBM digital evaluator — it computes `P(S_T > K) = Φ(d₂)` for a strike
grid given a Pyth oracle spot and an externally-primed scalar ATM
implied vol. There is no quote, no spread, no skew, no reservation
price, no inventory state, no order flow. This audit catalogues that
gap, claim by claim, against the Phase C corpus.

All Phase C distillations referenced (`audit_C_phase01..10*.md`) and
the six relevant Phase B deep-dives
(`audit_B_engine-pricer.md`, `audit_B_models-gbm.md`,
`audit_B_models-registry.md`, `audit_B_validation-sanity.md`,
`audit_B_state-market-surfaces.md`, `audit_B_engine-calendar.md`) are
present; no expected file was missing. Phase A cartography
(`audit/audit_A_cartography.md`) is the module-scope resolver for any
file path cited below.

---

## 1. Scope

### Phase C claims in play

The `pricing-model` topic tag appears on three Phase C distillations.
Filtering each table to claims tagged `pricing-model`:

- **`audit_C_phase02_pricing_models.md`** — the canonical-equations
  survey. Tagged `pricing-model` claims: C02-01 through C02-09,
  C02-12 through C02-15, C02-17 through C02-33, C02-38, C02-42 through
  C02-49, C02-51, C02-52, C02-56, C02-62, C02-66, C02-67, C02-70,
  C02-71, C02-73, C02-75, C02-79, C02-80, C02-83, C02-85.
- **`audit_C_phase08_synthesis_pricing.md`** — the Kalshi
  digital-corridor synthesis. Tagged `pricing-model` claims include
  C08-01, C08-04 through C08-13, C08-16 through C08-23, C08-25, C08-29,
  C08-33, C08-37, C08-38, C08-39, C08-40 through C08-49, C08-54
  through C08-59, C08-68, C08-69, C08-90 through C08-93, C08-96,
  C08-101 through C08-107, C08-122.
- **`audit_C_phase10_strategy_synthesis.md`** — the strategy-as-
  density-quoting synthesis. Tagged `pricing-model` claims include
  C10-01, C10-02, C10-05, C10-06, C10-07, C10-11, C10-12, C10-15,
  C10-16, C10-23, C10-29, C10-30, C10-31, C10-35, C10-39, C10-50,
  C10-52, C10-53.

Some claims live in C01, C05, C07, C09 with an adjacent tag
(`market-structure`, `density`, `inventory`, `oms`, `strategy`); those
are out of scope here unless they directly feed the pricing model
(referenced in passing).

### Phase B modules under audit

All six relevant Phase B deep-dives:

- `audit_B_engine-pricer.md` (`engine/pricer.py`) — composes the
  per-tick pricing pipeline.
- `audit_B_models-gbm.md` (`models/gbm.py`) — the only live model.
- `audit_B_models-registry.md` (`models/registry.py`) — config-to-model
  dispatch.
- `audit_B_validation-sanity.md` (`validation/sanity.py`) — pre-publish
  invariant checker.
- `audit_B_state-market-surfaces.md` (`state/iv_surface.py`,
  `state/basis.py`) — the σ and basis-drift caches the pricer reads.
- `audit_B_engine-calendar.md` (`engine/event_calendar.py`) — trading-
  time τ.

The end-to-end production-callable surface is exactly
`Pricer.reprice_market(commodity, strikes, settle_ns, *, now_ns) →
TheoOutput` (`engine/pricer.py:45-90`). Nothing else publishes a
number. There is no quoter, no market-making engine, no Kalshi client
(`audit/audit_A_cartography.md:243-245, 100`).

### Severity model used in this pass

Phase D's severity scale (blocker / major / minor / nice-to-have)
maps onto the pricing-model gap so that:

- "blocker" is reserved for the absence of capabilities without which
  the system cannot quote a Kalshi market at all (no spread, no
  reservation price, no bucket prices, no Kalshi connectivity).
- "major" is reserved for divergences that would distort prices once
  quoting exists (single-scalar σ vs Heston, no jumps, no fee floor,
  no fav/longshot overlay, no event widening).
- "minor" is hygiene (provenance, tolerances, defaults).
- "nice-to-have" is enhancement only.

Because the live code is admittedly a "Deliverable 1" stub
(`models/registry.py:1-9`, `state/iv_surface.py:1-12`,
`state/basis.py:1-10`), most pricing-model gaps are tagged `missing`
under this scale. The narrative section below distinguishes
"deliberately deferred" gaps from "specified but absent" ones.

---

## 2. Audit table

Columns: **C-id** | **claim (one line)** | **what code does** | **gap
class** | **severity** | **code citation(s)** | **notes**.

| C-id | claim | what code does | gap class | severity | code cite | notes |
|---|---|---|---|---|---|---|
| C02-01 | MM faces three risk sources: inventory, adverse selection, vol/jump. | Code models none of the three: no inventory state, no adverse-selection signal, no vol/jump regime layer. | missing | blocker | `engine/pricer.py:36-43` (Pricer dataclass — six fields, none of them inventory or order-flow) | The pricer's six dependencies are tick/IV/basis/calendar/registry/sanity (`audit_B_engine-pricer.md:60-67`). The architectural risk-source taxonomy is absent. |
| C02-02 | Half-spreads `δᵃ = pᵃ−S`, `δᵇ = S−pᵇ` around reference S. | Pricer returns `P(S_T > K)` for a strike grid; no quote, no half-spread defined. | missing | blocker | `models/gbm.py:97-105` (TheoOutput contains `probabilities` only — no bid/ask/spread fields) | `TheoOutput`'s public shape is `(commodity, strikes, probabilities, as_of_ns, source_tick_seq, model_name, params_version)` (`models/base.py:44-52`). No place to attach a bid/ask. |
| C02-03 | Cash & inventory dynamics: `dX = (S+δᵃ) dNᵃ − (S−δᵇ) dNᵇ`, `dq = dNᵇ − dNᵃ`, `dS = μ dt + σ dW + jumps`. | No inventory variable, no fill-counting process, no cash account anywhere in tree. | missing | blocker | `engine/pricer.py:36-43` and `audit/audit_A_cartography.md:213-230` (no module owns inventory state) | Inventory tracking is absent from every Phase A inventory row; the closest is `TickStore` which holds a price ring. |
| C02-04 | Quoting objective is `max E[U(X_T+q_T S_T)]` or quadratic-inventory penalty. | No optimization. The pricer returns the closed-form GBM CDF only. | missing | blocker | `models/gbm.py:69-105` (`GBMTheo.price` is purely numeric, no objective) | The Theo abstract contract (`models/base.py:55-69`) does not return a control either — it's a per-strike density function. |
| C02-05 | Ho–Stoll optimal half-spread `δᵃ,ᵇ = ½s ∓ γσ²(T−t)q`. | No spread term; γ and q do not exist as variables in code. | missing | blocker | `engine/pricer.py:74-90` (would-be insertion site between `tau` resolution and TheoOutput) | None of `gamma`, `q`, `inventory` appear in any `*.py` file (verified by grep over the tree). |
| C02-06 | Ho–Stoll reservation price `r = S − γσ²(T−t)q`. | No reservation price computed. The "reference" is the Pyth tick price, used unmodified. | missing | blocker | `engine/pricer.py:79` (`spot=tick.price`) and `models/gbm.py:35` (`forward = spot * exp(basis_drift * tau)`) | The forward used inside the kernel is a deterministic carry-adjusted spot; no inventory shift is added. |
| C02-07 | Long inventory ⇒ lower bid AND lower ask (skew). | No skew, because no quote and no inventory. | missing | blocker | `engine/pricer.py:77-86` (TheoInputs construction site — would carry skew if it existed) | Phase B notes `TheoInputs` is the carrier of "every per-call state" (`audit_B_engine-pricer.md:60-79`); it has no inventory field. |
| C02-08 | Stoll spread decomposition: holding + order + information cost. | None of the three components is materialized; spread itself is missing. | missing | major | `engine/pricer.py:55-90` | The decomposition is operational guidance for spread-budget allocation; absent because spread itself is absent. |
| C02-09 | Grossman–Miller price concession `P₁ − E[P₂] = aσ²ε/(M+1) i`. | No order-flow imbalance, no immediacy market, no concession term. | missing | major | `engine/pricer.py:77-86` | Concession-side flow modeling lives upstream of the pricer; the pricer has no hook. |
| C02-12 | Glosten–Milgrom: ask = `E[V|F,buy]`, bid = `E[V|F,sell]`. | No conditional-update logic; the pricer treats spot as exogenous and never re-marks on hypothetical buy/sell. | missing | blocker | `engine/pricer.py:59` (`tick = self.tick_store.latest(commodity)` — single read, no Bayes update) | The Pyth tick is a price oracle, not a counterparty signal; no `flow_sign` parameter exists. |
| C02-13 | GM spread widens monotonically in α (informed share) and `V_H − V_L`. | No spread, no informed-share parameter. | missing | major | `models/registry.py:24-29` (CommodityConfig — `raw` carries arbitrary YAML; no `alpha_informed` key) | YAML schema (`config/commodities.yaml:6-30`) has no informed-share field. |
| C02-15 | Kyle linear equilibrium `λ = ½√(σ²ᵥ/σ²ᵤ)`, `β = √(σ²ᵤ/σ²ᵥ)`, `p = p₀ + λy`. | No order-flow `y`, no λ estimate, no impact term. | missing | major | `engine/pricer.py:71-72` (sigma is read as a single ATM IV scalar; no σᵥ/σᵤ split) | Sigma is a single annualized scalar (`state/iv_surface.py:30-35`). |
| C02-17 | PIN = `αμ/(αμ + 2ε)`. | Not computed; informed/uninformed arrival rates not estimated. | missing | minor | `audit/audit_A_cartography.md:213-230` (no module owns trade arrival statistics) | Phase C02-20 itself flags VPIN/PIN as backward-looking diagnostics; their absence is hygiene, not blocker. |
| C02-18 | VPIN = `Σ|V^B−V^S| / (n·V)` over volume buckets. | Not computed. | missing | minor | n/a (no module owns trade-side classification) | Same as PIN; diagnostic. C02-19 notes the academic dispute. |
| C02-21 | Avellaneda–Stoikov objective `max E[−exp(−γ(X_T+q_T S_T))]`. | No objective optimized; pricer is closed-form CDF only. | missing | blocker | `models/gbm.py:35-42` (the kernel — six FLOPs per strike, no controls) | The kernel solves a probability question, not a control problem. |
| C02-22 | A–S exponential intensities `λᵃ,ᵇ(δ) = A exp(−kδ)`. | No fill-intensity model. | missing | blocker | n/a — no order-flow module exists in `audit/audit_A_cartography.md:213-230` | Phase B confirms no producer writes any fill-rate parameter (`audit_B_state-market-surfaces.md:479-488`). |
| C02-23 | A–S HJB combines diffusion of S with intensity-weighted control terms. | No HJB solver. | missing | blocker | `models/registry.py:32-38` (single live builder is `"gbm"`, no `"avellaneda_stoikov"` key) | Even commented-out builders (`jump_diffusion`, `regime_switch`, `point_mass`, `student_t`) do not include A–S. |
| C02-24 | A–S reservation price `r(s,q,t) = s − qγσ²(T−t)`. | No γ, no q. The "spot" used inside the kernel is the raw tick (`engine/pricer.py:79`). | missing | blocker | `engine/pricer.py:79`, `models/gbm.py:35` | This is the canonical reservation-price formula; its absence is the single largest pricing-model gap. |
| C02-25 | A–S optimal symmetric total spread `γσ²(T−t) + (2/γ)ln(1+γ/k)`. | No spread computation. | missing | blocker | `engine/pricer.py:88-89` (would-be insertion site after `model.price`, before `sanity.check`) | Both inputs to the formula (`γ`, `k`) are absent from the YAML (`config/commodities.yaml:6-30`) and from any state surface. |
| C02-26 | A–S optimal quotes `pᵃ = r + ½(δᵃ+δᵇ)`, `pᵇ = r − ½(δᵃ+δᵇ)`. | No quote produced. | missing | blocker | `engine/pricer.py:90` (`return output` — TheoOutput has no bid/ask attribute, `models/base.py:44-52`) | Pricer's contract does not name a quote. |
| C02-27 | Spread independence from inventory in baseline A–S is artifact of CARA + exp intensity. | Code is upstream of this issue (no spread, no CARA). | missing | nice-to-have | n/a | Not actionable until C02-21 through C02-26 are present. |
| C02-28 | GLFT asymptotic ask `δᵃ*(q) ≈ (1/γ)ln(1+γ/k) + …·(2q+1)`. | Not implemented. | missing | blocker | `models/registry.py:32-38` | A `GLFTTheo` builder would belong adjacent to `GBMTheo` (`models/gbm.py:60-105`). |
| C02-29 | GLFT asymptotic total spread at q=0. | Not implemented. | missing | blocker | n/a — no spread module exists | Same as C02-28. |
| C02-30 | GLFT hard inventory bounds `q ∈ {−Q,…,+Q}`. | No inventory; no Q. | missing | blocker | `audit/audit_A_cartography.md:213-230` (no inventory module) | Phase C02 ranks this as a built-in constraint of the GLFT family. |
| C02-31 | Cartea–Jaimungal–Ricci: optimal quotes contain alpha-signal term proportional to drift. | `basis_drift` is a scalar carry term, not an alpha signal; no "buy low sell high" overlay. | partial | major | `state/basis.py:28-35` (sets one annualized drift), `models/gbm.py:35` (forward = spot·exp(drift·τ)) | The shape "drift enters forward" is matched, but the *meaning* is carry/basis, not predictive alpha. C02-83 notes "academic papers assume zero drift; production runs dozens of alpha signals" — code has one and treats it as carry. |
| C02-32 | Cartea–Wang alpha signal shifts both reservation price and spread asymmetry. | No reservation price; basis_drift is symmetric in payoff. | missing | major | `state/basis.py:37-48` (single-scalar getter, no asymmetry) | Code's drift is one float per commodity. |
| C02-33 | Guéant: multi-asset hedged quoting with cross-asset inventory. | Single-commodity; no cross-asset coupling. | missing | blocker | `engine/pricer.py:47` (signature is `commodity: str`, scalar) | The pricer's signature processes one commodity at a time; there is no portfolio object. |
| C02-38 | Mid-price changes linear in OFI with slope `1/depth`; OFI ≈ Kyle's λ. | No OFI computed; no order-book module. | missing | major | `audit/audit_A_cartography.md:213-230` | OFI requires MBO/MBP feed; only Pyth tick-by-tick exists (`feeds/pyth_ws.py`). |
| C02-42 | Heston SV: `dS = μS dt + √v S dW^S`, `dv = κ(θ−v)dt + ξ√v dW^v`. | Code uses a single annualized ATM σ scalar; v_t not modeled. | wrong | major | `state/iv_surface.py:30-35, 37-48`, `models/gbm.py:36-37` (`sigma_sqrt_tau = sigma·sqrt(tau)`, `half_variance = 0.5·sigma·sigma·tau`) | The model is GBM with constant σ. C02-75 says "minimum viable model for grain volatility is GARCH/Heston-style stochastic vol plus jumps" — code does neither. |
| C02-43 | Heston-A–S reservation price `r_t = S_t − qγv_t(T−t)`; `σ²` is replaced by `v_t`. | Neither sigma nor reservation price is time-varying inside τ. The single read of σ at `engine/pricer.py:71` is then held constant for the whole `(now, settle)` window. | missing | major | `engine/pricer.py:71` (single read), `models/gbm.py:36-37` (σ used as a scalar inside kernel) | The IV surface stores one (σ, ts_ns) pair and there is no `v(t)` curve (`audit_B_state-market-surfaces.md:38-45`). |
| C02-45 | Merton jump-diffusion `dS/S = (μ−λκ)dt + σ dW + (J−1)dN`. | No jump term; the kernel is pure GBM (`models/gbm.py:1-10`). | missing | major | `models/gbm.py:35-42` (the kernel — six FLOPs, all diffusive) | The registry has a commented-out `"jump_diffusion"` slot (`models/registry.py:34-37`) flagged as deliverable 4–5 but no live implementation. |
| C02-46 | Bates SVJ (Heston + Merton jumps) needed for smile and term structure. | Neither component implemented. | missing | major | `models/gbm.py:1-10` (the *only* live model) | Phase C08-89 explicitly requires Bates-SVJ for weather-shock scenario. |
| C02-47 | Soybean WASDE / Crop Progress modeled as predictable jumps with stochastic sizes. | No event-day jump intensity; no scheduled-event integration with σ or drift. | missing | blocker | `engine/event_calendar.py:30-38` (only WTI session windows, no event-day vol overlay), `config/commodities.yaml:24-28` (WTI lists EIA crude with `vol_adjustment: "strip_event_vol_if_after"` but no Python reader, see `audit_B_engine-calendar.md:240-251`) | The YAML hints at event-day overlays; no code reads them. |
| C02-48 | Unscheduled events (weather, export bans) as Poisson arrivals. | No Poisson layer. | missing | major | `models/gbm.py:35-42` | Same as C02-45/46/47. |
| C02-49 | Models ignoring jumps systematically under-quote spreads on WASDE mornings, over-quote on quiet August afternoons. | Code has no spread, but it also has no jump-aware vol — so even the underlying density is mis-marked under the C02-49 condition. | missing | major | `state/iv_surface.py:37-48` (returns whatever scalar was last primed), `engine/event_calendar.py:30-38` (no event hooks) | This is the live consequence: even before the missing quoting layer, the σ feeding the GBM kernel is calendar-blind. |
| C02-51 | σ in the A–S formula must be time-varying and calendar-indexed. | σ is a single scalar with a 60s staleness budget; no calendar indexing. | wrong | major | `state/iv_surface.py:21-48` (one float per commodity, one timestamp), `engine/pricer.py:71` (single point-read) | The interface `atm(commodity, *, now_ns) -> float` returns one number; there is no `(t, settle)` curve. |
| C02-52 | Kaldor–Working forward `F_t(T) = S_t exp((r+u−y)(T−t))`. | Code computes `forward = spot·exp(basis_drift·tau)` — structurally identical with `basis_drift` collapsing `r+u−y` into one annualized scalar. | partial | minor | `models/gbm.py:35` | The functional form matches; the decomposition into rate / storage / convenience yield is collapsed. C02-53 (backwardation/contango sign reading) is therefore inferable from `basis_drift` sign but not surfaced anywhere. |
| C02-56 | Reservation-price drift should incorporate mean reversion when inventories extreme. | No reservation price; no inventory-state-dependent drift. | missing | major | `state/basis.py:28-35` (drift is a scalar set externally) | C02-54 / C02-55 inventory-state nonlinearity is a downstream property of the missing reservation-price layer. |
| C02-62 | Index-roll order flow should widen adverse-selection premium *less* than unscheduled trade. | No adverse-selection premium; no order-flow classification. | missing | major | n/a — no order-flow module | Roll-window context lives in C02-58 through C02-61; flagged here for completeness. |
| C02-66 | Cartea–Jaimungal accommodates regime change via deterministic, time-indexed `λ_t^J`. | No `λ^J`. | missing | major | `engine/event_calendar.py:30-38` would be the natural carrier; it carries only WTI session windows. | C08-97 makes the same point for Kalshi (κ_t spread/width multipliers); also absent. |
| C02-67 | "Which report moves the market how much" is partly answered by literature, partly proprietary. | No report-impact table or calibration. | missing | minor | `config/commodities.yaml:24-28` (event_calendar block declared but unread) | The YAML schema has the right shape; no Python reader exists. |
| C02-70 | Poisson `A` parameter must be time-of-day and day-of-week indexed. | No `A`. | missing | blocker | n/a | Same as C02-22. |
| C02-71 | Overnight density: low-variance diffusion + heavy-tail jump mixture. | GBM only; no overnight regime. | missing | major | `models/gbm.py:35-42` | C02-69 (overnight thinness) is a follow-on consequence. |
| C02-73 | Overnight, GLFT closed-form is "warning signal, not a quoting policy". | Code never enters this regime — there is no GLFT and no quoting policy. | missing | nice-to-have | n/a | Practitioner-lore only. |
| C02-75 | Minimum viable model: GARCH/Heston SV + jumps. | GBM only. | missing | major | `models/gbm.py:1-10` | This sentence from Phase C02 is the cleanest "the live model is below the minimum bar" claim. |
| C02-79 | Practitioner stack item 2: reservation-price skew against inventory + GLFT inventory cap + linear skew calibrated to realized vol. | None of the three sub-pieces present. | missing | blocker | `engine/pricer.py:36-43` | Stack-summary item; absence here is the absence of the entire MM control loop. |
| C02-80 | Practitioner stack item 3: spread = max(GLFT-nominal, AS-protection keyed to recent flow + VPIN). | No spread; no flow tracking. | missing | blocker | n/a | Stack-summary item. |
| C02-83 | Production desks run dozens of alpha signals in drift; academic papers assume zero. | Code has one drift term and treats it as basis, not alpha. | missing | major | `state/basis.py:37-48` (`get(commodity, *, now_ns) -> float`) | Single-scalar interface; cannot carry multiple alpha streams without a redesign. |
| C02-85 | Event-day spread multiplier κ_t is proprietary, varies by desk, under-published. | No κ_t. | missing | minor | `config/commodities.yaml:28` (`vol_adjustment: "strip_event_vol_if_after"` declared, unread) | Practitioner-lore. |
| C08-01 | Each `KXSOYBEANW-…-i` Yes contract pays $1 if `S_T ∈ [ℓᵢ, uᵢ)`. | No Kalshi contract schema; no bucket data structure; commodities are CME-side names (`wti`, `corn`, `soy` stub) only. | missing | blocker | `config/commodities.yaml:6-85` (no Kalshi block); `audit/audit_A_cartography.md:243-245` (whole Kalshi side absent) | The product the Phase C corpus prices is not represented in code at all. |
| C08-04 | Yes payoff is indicator `g_i(S_T) = 1{ℓᵢ ≤ S_T < uᵢ}`. | No bucket payoff function. | missing | blocker | `models/base.py:55-69` (Theo abstract returns `P(S_T > K)` for a strike grid, not bucket probabilities) | The Theo contract is upper-tail digitals, not corridor indicators. |
| C08-05 | Time-t Kalshi-fair Yes price is `Q^K(ℓᵢ ≤ S_T < uᵢ \| F_t)`. | Code computes `Q(S_T > K)` only, single-strike. | wrong | blocker | `models/gbm.py:97-105` (TheoOutput is `(strikes, probabilities)` upper-tail) | A bucket price is `D(ℓ) − D(u)`; the code's vector is `D(K)` itself, not a difference. The downstream consumer would have to subtract pairs externally. |
| C08-07 | Zero-discounting differs from BL digital `e^(−r(T−t))Q(·)`. | No discounting at all in code, which coincidentally matches Kalshi's zero-collateral-yield property — but for the wrong reason (no rate input). | already-good | nice-to-have | `models/gbm.py:35-42` (no `r` term in kernel) | Coincidental match. The kernel returns a probability, not a discounted probability; this happens to be the right answer for Kalshi but is unargued. |
| C08-08 | Bucket = digital-corridor decomp: `1{S≥ℓ} − 1{S≥u}`. | Not implemented; would be one subtraction in a downstream consumer if the strike grid contained `[ℓ, u]` pairs. | missing | blocker | n/a — no bucket consumer exists | Trivial to compose externally; absent in code. |
| C08-09 | Digital = limit of vertical call spread `1/ε [C(K−ε) − C(K)]`. | Not used — the GBM kernel produces digitals analytically. | already-good | nice-to-have | `models/gbm.py:35-42` | The closed-form GBM digital `Φ(d₂)` is exact; the limit definition is only relevant when extracting from option quotes (which the code does not do). |
| C08-11 | Breeden–Litzenberger `f_T(K) = e^(r(T−t)) ∂²C/∂K²`. | Not implemented; the code does not consume an option-price surface and does not differentiate a smoothed call surface. | missing | blocker | n/a — no surface ingest module exists; `audit/audit_A_cartography.md:213-230` shows none. | C08-100 (CME MDP 3.0 ingest), C08-101 (SVI smoothing), C08-102 (RND extraction) are the absent stages. |
| C08-12 | `D(K,T) = −∂C/∂K`. | Coincidentally produces `D(K)` for the GBM-implied surface (Φ(d₂) is exactly the BS digital), but that is not "extract from market" — it is "assume GBM and emit". | partial | major | `models/gbm.py:42` (`out[i] = 0.5 · erfc(−d₂·_INV_SQRT2)`) | The output number has the right *type* (digital probability) but is sourced from a model assumption, not from market option quotes. C08-15/C08-16 require smoothing in IV space, not assuming a model. |
| C08-13 | Bucket price `value_i = D(ℓᵢ) − D(uᵢ) = ∫_ℓ^u f_T dx`. | Bucket integration absent. | missing | blocker | n/a — no bucket layer | Needs both pair iteration and a tail-aware density. |
| C08-16 | Standard practice smooths in IV space and re-prices, not differentiating raw prices. | No smoothing layer. | missing | blocker | n/a | C08-101 stage B. |
| C08-17 | Gatheral SVI `w(k) = a + b{ρ(k−m) + √((k−m)² + σ²)}`. | Not implemented. | missing | blocker | n/a — no SVI module | The Phase C corpus names SVI as the workhorse for weekly soybean calibration. |
| C08-18 | Gatheral–Jacquier static-arbitrage-free SVI constraints. | n/a (no SVI). | missing | blocker | n/a | Subsumed by C08-17. |
| C08-19 | SABR `(α, β, ρ, ν)` closed-form. | Not implemented. | missing | nice-to-have | n/a | C08-21 (cubic spline alternative) also absent. |
| C08-20 | Hagan SABR can be arbitrageable at deep-OTM, where Kalshi tail buckets live. | n/a (no SABR). | missing | minor | n/a | Diagnostic only. |
| C08-22 | Kalshi-weekly workhorse: SVI on closest CBOT weekly/short-dated option surface. | n/a. | missing | blocker | n/a | Subsumed by C08-17. |
| C08-23 | Fall back to Malz cubic spline if no co-terminal weekly. | n/a. | missing | blocker | n/a | Subsumed by C08-17. |
| C08-25 | SVI/SABR extrapolation in open-ended tails under-quotes tail mass. | Code has no extrapolation logic; the GBM density extends to ±∞ analytically, with thin tails. | wrong | major | `models/gbm.py:42` (lognormal CDF — thin tails by construction) | Lognormal tails systematically under-state grain fat tails (C02-74 leptokurtosis). |
| C08-26 | Figlewski GEV-tail attachment: piecewise BL + GEV beyond paste points. | Not implemented. | missing | blocker | n/a — no tail-paste module | Phase C08 makes this the canonical tail technique. |
| C08-29 | Tail-paste sets Yes-price floor/cap on open-ended end buckets. | n/a. | missing | blocker | n/a | Subsumed by C08-26. |
| C08-33 | Variance-rescale density to Kalshi expiry when option expiry differs. | n/a. | missing | major | `engine/event_calendar.py:96-107` (returns a single τ; no second τ for option expiry) | The calendar produces one τ per call. |
| C08-37 | ZS-option RND is for futures; Kalshi measure is for marginal Kalshi taker — they may differ. | Code has no Kalshi side at all. | missing | blocker | `audit/audit_A_cartography.md:243-245` | Whole-system gap. |
| C08-38 | Prediction-market prices empirically biased toward 50% on short-dated contracts (Wolfers–Zitzewitz; Whelan 2025). | No bias adjustment. | missing | major | n/a | C08-104 (measure overlay) is the systemic place this would belong. |
| C08-39 | Conservative engine starts from RND and marks an explicit measure-overlay spread. | n/a. | missing | major | n/a | Subsumed by C08-38. |
| C08-40 | Per-bucket A–S reservation price `rᵢ(t) = mᵢ(t) − qᵢγᵢσ²ₘᵢ(T−t)`. | n/a — no buckets, no per-bucket inventory `qᵢ`, no per-bucket γᵢ. | missing | blocker | n/a | The whole multi-asset bucket grid is missing. |
| C08-41 | Bucket variance `σ²ₘᵢ ≈ Δᵢ²·Var(∂mᵢ/∂S)·σ²_S`. | n/a. | missing | blocker | n/a | Bucket Δᵢ is the C08-70 derivative; absent. |
| C08-42 | A–S half-spread sum: `δᵃ + δᵇ = γσ²ₘᵢ(T−t) + (2/γ)ln(1+γ/k)`. | n/a. | missing | blocker | n/a | Same as C02-25 in the Kalshi setting. |
| C08-45 | Cartea–Jaimungal–Penalva multi-asset HJB with cross-bucket Σᵢⱼ. | n/a. | missing | blocker | n/a | Whole-system gap. |
| C08-46 | Kalshi bucket Yes prices are highly cross-correlated: a move that pushes one up pushes adjacent ones down. | The GBM density is jointly self-consistent for the *same* commodity across strikes (one `σ`, one spot) — but there is no bucket-vs-bucket Σ machinery. | partial | major | `models/gbm.py:35-42` (one σ, one spot drives all strike outputs — internal correlation is implicit in the shared parameters) | The internal coupling is automatic for a single-density model. The coupling that's missing is the *empirical* Σᵢⱼ vs RND-implied Σᵢⱼ comparison flagged in C10-OQ-05. |
| C08-47 | Multi-asset reservation price = matrix skew: `rᵢ = mᵢ − γ(T−t)Σⱼ Σᵢⱼ qⱼ`. | n/a. | missing | blocker | n/a | Subsumed by C08-45. |
| C08-48 | Long position in bucket i lowers both bucket-i and adjacent-j quotes. | n/a. | missing | blocker | n/a | Subsumed. |
| C08-49 | Matrix-skew is GLFT generalization to multi-asset discrete case. | n/a. | missing | blocker | n/a | Subsumed. |
| C08-54 | Continuous Glosten–Milgrom does NOT transfer at Kalshi bucket edges. | n/a (no edges). | missing | nice-to-have | n/a | "Does not transfer" claim — code can't violate a non-transfer if it has no transfer. |
| C08-55 | Optimal protective spread near edges has jump-diffusion flavor. | n/a. | missing | major | n/a | Subsumed. |
| C08-56 | Quoting engine needs an explicit edge-proximity term. | n/a. | missing | major | n/a | Subsumed. |
| C08-57 | Hanson LMSR / Othman–Pennock AMM lit does NOT transfer to Kalshi CLOB. | Code does not implement LMSR (correctly). | already-good | nice-to-have | `audit/audit_A_cartography.md:213-230` (no AMM module) | Negative-claim alignment: the absence of LMSR is *correct* per Phase C. |
| C08-58 | LMSR formula reference. | Not implemented (correctly). | already-good | nice-to-have | n/a | Same. |
| C08-59 | Outcome-prices-sum-to-1 is an arbitrage condition, not a constructive identity, on Kalshi. | n/a. | missing | nice-to-have | n/a | Diagnostic. |
| C08-68 | Adverse selection lowest at OTM tails, highest at ATM. | n/a (no adverse-selection layer). | missing | major | n/a | Subsumed by C08-106. |
| C08-69 | Early week → structural fundamental advantage; late week → USDA-window advantage. | n/a. | missing | major | n/a | Same. |
| C08-90 | Kalshi taker fee `⌈0.07·P(1−P)·100⌉/100`, peak 2¢ at P=0.50. | No fee model. | missing | blocker | `models/gbm.py:97-105` (TheoOutput has no fee field) | Without fees, the spread floor that C08-91 prescribes (round-trip ≥ 2.5¢) cannot be enforced. |
| C08-91 | Round-trip maker+taker on a 50¢ bucket ≈ 2.5¢ on $1 notional. | No round-trip cost calculation. | missing | major | n/a | Subsumed by C08-90. |
| C08-93 | Quoting decisions ignoring round-trip cost are systematically biased toward over-quoting inside the spread. | The pricer cannot over-quote because it does not quote — but it also does not floor at fees. | missing | major | n/a | Subsumed by C08-90. |
| C08-96 | Scheduled events shift mean of implied distribution AND expand-then-contract variance (U-shape). | No event-day mean shift; no variance expansion. The single ATM σ is whatever was last primed. | missing | major | `state/iv_surface.py:30-35` (set_atm overwrites; no schedule), `engine/event_calendar.py:30-38` (no event windows) | Same root cause as C02-47/49. |
| C08-101 | Pipeline stage B: SVI calibration with Gatheral–Jacquier no-arb constraints; Bliss–Panigirtzoglou cubic-spline fallback. | Not present. | missing | blocker | n/a | Subsumed by C08-17. |
| C08-102 | Pipeline stage C: differentiate smoothed call surface; paste GEV tails; propagate to Kalshi expiry. | Not present. | missing | blocker | n/a | Subsumed by C08-11/26/33. |
| C08-103 | Pipeline stage D: integrate `f_T` over each bucket; normalize Σ πᵢ⁰ = 1. | Not present. | missing | blocker | n/a | Subsumed by C08-13. |
| C08-104 | Pipeline stage E: measure overlay (Kalshi-vs-RN tilt). | Not present. | missing | major | n/a | Subsumed by C08-38/39. |
| C08-105 | Pipeline stage F: reservation price `rᵢ = mᵢ − γ(T−t)Σⱼ Σᵢⱼ qⱼ`. | Not present. | missing | blocker | n/a | Subsumed by C08-47. |
| C08-106 | Pipeline stage G: adverse-selection / queue skew via Cartea–Jaimungal–Ricci. | Not present. | missing | blocker | n/a | Subsumed by C02-31. |
| C08-107 | Pipeline stage H: spread sizing via GLFT closed-form, σ²→σ²ₘᵢ; floor at maker+taker fees + edge. | Not present. | missing | blocker | n/a | Subsumed by C02-25/29 + C08-90. |
| C08-122 | Kalshi weekly soybean bucket = digital-corridor option, $1 notional, $0.01–$0.99 band. | No representation of Kalshi product. | missing | blocker | `audit/audit_A_cartography.md:243-245` | Whole-system gap. |
| C10-01 | Each Kalshi bucket is a digital-corridor option, decomposable as difference of two cash-or-nothing digitals. | n/a. | missing | blocker | n/a | Same as C08-01/08. |
| C10-02 | The vector of Yes prices is the empirical RND discretized to bucket scale (BL). | The GBM kernel emits a *theoretical* GBM density at strikes, not an *empirical* RND from the option surface. | wrong | blocker | `models/gbm.py:35-42` | The density is model-implied, not market-implied; no RND extraction stage exists. |
| C10-05 | MM requires two-sided edges; pricing question is "what density to quote and how to lean against inventory and adverse selection," generalizing A–S to multi-asset bucket grid (Cartea–Jaimungal–Penalva). | One-sided density only; no quoting; no inventory; no adverse selection. | missing | blocker | `models/gbm.py:97-105` (one-sided output `P(S_T > K)`) | The cleanest single-sentence statement of the gap. |
| C10-06 | Small persistent favorite–longshot bias on prediction markets, strengthens to expiry. | No bias overlay. | missing | major | n/a | Subsumed by C08-38. |
| C10-07 | A pricer ignoring the favorite–longshot overlay systematically under-prices low-prob tails and over-prices near-certainty interior buckets. | Code is exposed to exactly this failure mode if/when it produces bucket prices: the GBM density's lognormal tails will be uncalibrated to Kalshi taker behavior. | missing | major | `models/gbm.py:35-42` | Direct consequence of the missing C10-06 overlay. |
| C10-11 | Roberts–Schlenker 0.1 elasticity ⇒ ~10× price multiplier per yield deviation in tight-stocks regimes. | No elasticity model; no yield→price mapping. | missing | minor | n/a | Phase C10 itself flags this as a regime classifier, not a tactical signal. |
| C10-12 | Weather→density pipeline: yield distribution → price distribution via stocks-to-use → SVI/Figlewski RND → bucket Yes mid. | Not present. | missing | blocker | n/a | Composite of C08-101/102/103 + C10-11. |
| C10-15 | Bimodal RND fingerprint (concave IV pre-event). | No IV-surface curvature analysis. | missing | minor | n/a | Diagnostic. |
| C10-16 | Pre-release rule: widen SVI / scale Bates jump variance, fattening interior buckets and lifting tails. | Not present. | missing | major | n/a | Subsumed by C08-96/97. |
| C10-23 | A quoter holding bucket widths fixed at calendar average over-quotes tails in quiet weeks and under-quotes in vol windows. | Code does not have buckets, but if/when buckets land, the σ-staleness gate (60s) is the wrong granularity for the regime split. | missing | major | `state/iv_surface.py:24` (60_000 ms default) | Staleness ≠ regime; same scalar, no regime tag. |
| C10-29 | Cont–de Larrard / Huang–Lehalle–Rosenbaum queue-reactive model transfers to Kalshi CLOB. | No queue-reactive logic. | missing | major | n/a | Phase C08-51 makes the same claim. |
| C10-30 | Sustained CME-side OFI imbalance moves ZS mid by a small amount that propagates to every Kalshi bucket via ∂mᵢ/∂S. | No OFI; the propagation kernel exists implicitly inside the GBM (each strike's prob is a function of spot) but is not wired to OFI input. | partial | major | `models/gbm.py:35-42` (P depends on spot, so a spot move re-marks all strikes — but the input is Pyth tick, not OFI) | Mechanism present (spot drives all probs); driver absent (OFI). |
| C10-31 | ATM buckets carry largest delta; tail buckets update slowly. | The GBM kernel reproduces this Greek profile naturally for a single density, but bucket Δᵢ is not surfaced. | partial | minor | `models/gbm.py:42` (digital `Φ(d₂)` is monotone-decreasing in K with the highest sensitivity around the forward) | Implicit in the closed-form. Not exposed via TheoOutput. |
| C10-35 | Backwardation/contango shifts conditional mean of Friday settle. | The basis_drift scalar implements a single carry term that does shift the forward (`F = spot·exp(drift·τ)` at `models/gbm.py:35`), correctly directional with sign — but with no curve-shape information beyond a single annualized number. | partial | major | `models/gbm.py:35`, `state/basis.py:28-35` | Direction matches, granularity does not. |
| C10-39 | Historical sensitivity ~+18¢/bu per −1m bushel ending-stocks surprise (regime-adjusted). | No WASDE-delta-to-price mapping. | missing | minor | `config/commodities.yaml:24-28` (event_calendar declared, unread) | Operationalizes C02-67. |
| C10-50 | MM's edge is per-bucket post-trade markout (1m/5m/30m). | No fill-tracking or markout module. | missing | blocker | `audit/audit_A_cartography.md:213-230` | Subsumed; no order-flow capture in tree. |
| C10-52 | Cartea–Jaimungal cross-inventory: `rᵢ = mᵢ − γ(T−t)Σⱼ Σᵢⱼ qⱼ`. | Not present. | missing | blocker | n/a | Same as C08-47. |
| C10-53 | Long bucket-i should skew adjacent bucket-j Kalshi mids in the direction that reduces aggregate exposure. | n/a. | missing | blocker | n/a | Same as C08-48. |

Code-citation totals across the table: distinct file:lines references
include `engine/pricer.py:36-43`, `:45-90`, `:55-90`, `:71-72`, `:79`,
`:88-89`; `models/gbm.py:1-10`, `:35`, `:35-42`, `:42`, `:69-105`,
`:97-105`; `models/base.py:44-52`, `:55-69`; `models/registry.py:1-9`,
`:24-29`, `:32-38`, `:34-37`; `state/iv_surface.py:1-12`, `:21-48`,
`:24`, `:30-35`, `:37-48`; `state/basis.py:1-10`, `:28-35`, `:37-48`;
`engine/event_calendar.py:30-38`, `:96-107`; `config/commodities.yaml:6-30`,
`:24-28`, `:6-85`; `audit/audit_A_cartography.md:213-230`, `:243-245`,
`:100`. That is well in excess of the ten-citation floor.

Research-citation totals: distinct C-ids referenced include C02-01, -03,
-04, -05, -06, -07, -08, -09, -12, -13, -15, -17, -18, -21, -22, -23,
-24, -25, -26, -27, -28, -29, -30, -31, -32, -33, -38, -42, -43, -45,
-46, -47, -48, -49, -51, -52, -56, -62, -66, -67, -70, -71, -73, -74,
-75, -79, -80, -83, -85; C08-01, -04, -05, -07, -08, -09, -11, -12,
-13, -16, -17, -18, -19, -20, -22, -23, -25, -26, -29, -33, -37, -38,
-39, -40, -41, -42, -45, -46, -47, -48, -49, -51, -54, -55, -56, -57,
-58, -59, -68, -69, -90, -91, -93, -96, -97, -100, -101, -102, -103,
-104, -105, -106, -107, -122; C10-01, -02, -05, -06, -07, -11, -12,
-15, -16, -23, -29, -30, -31, -35, -39, -50, -52, -53. Far above the
ten-citation floor.

---

## 3. Narrative — most consequential gaps

### 3a. The Avellaneda–Stoikov / Cartea–Jaimungal control loop is entirely absent (C02-21 through C02-26, C02-79, C08-40 through C08-49, C08-105 through C08-107, C10-05, C10-52)

This is the blocker. The Phase C02 and C08 corpus are built around the
Avellaneda–Stoikov skeleton (`max E[−exp(−γ(X_T+q_T S_T))]` with
exponential fill intensities `λ(δ) = A exp(−kδ)` per C02-21/22) and
its Cartea–Jaimungal–Penalva multi-asset generalization for a Kalshi
bucket grid (C08-45). The canonical reservation-price formula
`r = S − γσ²(T−t)q` (C02-24) and the optimal symmetric total spread
`γσ²(T−t) + (2/γ)ln(1+γ/k)` (C02-25) require three quantities that
do not exist in the live tree:

1. A risk-aversion coefficient γ. The repo's only "γ" candidate is
   the parameter name in physics formulas that nothing reads. The
   YAML schema (`config/commodities.yaml:6-30`) has no `gamma`,
   `risk_aversion`, or `inventory_aversion` key; the registry
   (`models/registry.py:24-29`) carries `raw: dict[str, Any]` so a
   future maintainer can add one, but `cfg.raw.get("gamma", …)`
   appears nowhere in code.
2. An inventory variable q. There is no inventory module in the Phase
   A inventory (`audit/audit_A_cartography.md:213-230`) and no field
   on `TheoInputs` (`models/base.py:32-41`) that carries an inventory
   integer. Any `q` would have to be threaded through a new `state/`
   surface — none exists.
3. A fill-intensity model `λ(δ) = A exp(−kδ)`. The Pyth feed
   (`feeds/pyth_ws.py`) writes price ticks, not order-book events; no
   producer would surface `(A, k)` even if the consumer existed. The
   Phase C corpus (C02-22, C08-43, C08-44, C10-OQ-03) explicitly flags
   `λ_i(δ)` as an empirical-calibration object — and the only place
   that calibration could live, `calibration/`, is empty
   (`audit/audit_A_cartography.md:122-126`).

The cleanest single-line summary is C10-05: "The pricing question is
'what density should I quote and how to lean against inventory and
adverse selection,' generalizing A–S to the multi-asset bucket grid."
The live `models/gbm.py:69-105` answers neither half.

### 3b. There is no Kalshi product representation, so C08-01 through C08-13 are unreachable (C08-01, C08-04, C08-05, C08-08, C08-13, C08-122)

Phase C08 prices a `KXSOYBEANW-…-i` Yes contract — a $1-notional
indicator on `S_T ∈ [ℓᵢ, uᵢ)` with bucket prices summing to the
RND-integral over the bucket. The live tree has no Kalshi data
structures. `config/commodities.yaml:6-85` lists CME-side commodity
names (`wti` populated; `corn`, `soy` stubs) — there is no `kalshi`
section, no `bucket_grid`, no `event_ticker`, no
`reference_snapshot` configuration. The cartography flags this as
red flag #2 (`audit/audit_A_cartography.md:243-245`: "No file in the
repo imports, references, or implements anything Kalshi-specific —
no REST client, no contract schema, no order submission").

The implication for the audit row is that C08-01 through C08-13, plus
the entire pipeline stages C08-100 through C08-110, are vacuously
"missing": the code does not have a Kalshi-side module to put them
in. Every "missing" tag for those rows is therefore better read as
"missing — at the architecture level, not just the line level."

The single near-good claim from this cluster is C08-07 (Kalshi has no
discounting, unlike standard BL digitals on options): the GBM kernel
also has no discount factor, but for the unrelated reason that it is
a forward-measure GBM that does not encode r at all. The two
"absences of `e^(−rT)`" coincide; the structural reasoning behind
them does not.

### 3c. The vol model is GBM with a single annualized scalar — three orders of magnitude below the Phase C "minimum viable" bar (C02-42 through C02-49, C02-51, C02-71, C02-74, C02-75, C08-25, C10-02)

The live model is `P(S_T > K) = Φ(d₂)` for a constant σ
(`models/gbm.py:1-10, 35-42`). The σ feeding it is one float per
commodity with a 60-second staleness budget
(`state/iv_surface.py:21-48`). Phase C02-75 names the *minimum* viable
grain-vol model as "GARCH/Heston-style stochastic vol plus jumps."
None of those three components is present:

- No stochastic-vol process. C02-42 (Heston's `(v_t, S_t)` joint
  diffusion) and C02-43 (Heston-A–S reservation price with `σ² → v_t`)
  cannot land while `state/iv_surface.atm` returns a single `float`.
  The interface itself (`state/iv_surface.py:37-48`) is shaped wrong
  — adding a strike/expiry/calendar curve, as the docstring promises
  ("the upgrade is additive"), requires changing the return type, not
  decorating it.
- No jump term. The kernel at `models/gbm.py:35-42` has six FLOPs per
  strike and no Poisson branch. The registry's commented-out
  `"jump_diffusion"` builder (`models/registry.py:34-37`) is a
  documentation marker, not live code; configurations declaring
  `model: "jump_diffusion"` (e.g., `config/commodities.yaml:62-72`
  for `nat_gas`, `wheat`, `coffee`) are tagged `stub: true` and never
  reach a builder lookup.
- σ is calendar-blind. C02-51 ("σ must be time-varying and
  calendar-indexed, not estimated from a trailing window") is
  contradicted by the staleness-budget interface: 60 s is short
  enough that *staleness* is taken to be the only freshness signal,
  with no awareness of the seasonal/event calendar from C02-50,
  C02-63, C02-64. The trading calendar (`engine/event_calendar.py`)
  is the right architectural neighbour for a calendar-indexed σ
  curve, but it currently carries only WTI session windows
  (`engine/event_calendar.py:30-38`), not vol-regime overlays.

The Phase C08-25 consequence is direct: lognormal tails systematically
under-quote tail buckets relative to the heavy-tailed empirical
density of grain returns (C02-74). Even before the missing quoting
layer, the fair value the pricer emits would be tail-light against
Kalshi taker reality.

### 3d. There is no RND-extraction pipeline (C08-11, C08-16, C08-17, C08-26, C08-100 through C08-103)

The Phase C08 pricing pipeline (stages A through L) builds the
risk-neutral density by ingesting the CME ZS option chain, smoothing
its IV surface (SVI under Gatheral–Jacquier no-arbitrage constraints,
or a Bliss–Panigirtzoglou cubic-spline fallback), differentiating
twice in strike (Breeden–Litzenberger), pasting GEV tails (Figlewski),
and propagating to the Kalshi expiry. The live tree implements *none*
of this. There is no `feeds/cme_*` ingest (only Pyth, see
`audit/audit_A_cartography.md:215`), no SVI calibrator anywhere, no
spline module, no GEV-tail attachment, no `state/option_surface.py`.

The GBM pricer's output does have the *type* of an RND-evaluation
(`P(S_T > K)`) but the *source* is a parametric assumption, not a
market surface. The distinction matters because the Phase C08
guarantee is that the Kalshi quote is a tradable view on the *same*
distribution the CME options market is pricing — that is the entire
basis of the Kalshi-vs-CME edge (C08-10, C10-32). If the Kalshi
quote is computed off a GBM with a separately-primed scalar σ, the
arbitrage relation is broken at its root: the ZS-option market may be
implying a smile/skew the GBM density cannot represent.

### 3e. No fee model, no spread floor, no measure overlay (C08-90, C08-91, C08-93, C08-38, C08-39, C10-06, C10-07)

C08-90 specifies the Kalshi taker fee `⌈0.07·P(1−P)·100⌉/100`,
peaking at 2¢ at P=0.50. C08-91 makes the round-trip cost 2.5¢ on $1
notional ≈ 250 bps. C08-93 says "quoting decisions ignoring round-trip
cost are systematically biased toward over-quoting inside the spread."
The live code has no fee model: no field on `TheoOutput`
(`models/base.py:44-52`), no place in `Pricer.reprice_market`
(`engine/pricer.py:45-90`) that subtracts maker/taker, no
configuration entry for fee schedules. The Wolfers–Zitzewitz / Whelan
favorite–longshot overlay (C08-38, C10-06) is similarly absent;
together, the missing fee floor and the missing measure overlay are
the two systematic biases C10-07 calls out: under-pricing tails,
over-pricing near-certainty buckets.

These two are tagged "major" rather than "blocker" because they would
distort prices once a quoting layer exists; until the C08-105
reservation-price layer exists, there is nothing to distort.

### 3f. The basis_drift scalar carries the Kaldor–Working forward correctly but at the wrong granularity (C02-52, C02-53, C10-35)

A bright spot. The GBM kernel computes
`forward = spot * exp(basis_drift * tau)` at `models/gbm.py:35` — the
exact functional shape of Kaldor–Working `F_t(T) = S_t e^{(r+u−y)(T−t)}`
(C02-52), with `basis_drift` collapsing `r + u − y` into a single
annualized scalar. The sign convention is preserved: a positive
`basis_drift` shifts the forward up (matching backwardation
direction), a negative one shifts it down. C10-35 (backwardation/
contango affecting the conditional mean) is therefore *partially*
modelable through `basis_drift`: a calibrator could decompose the
curve and feed an aggregate. What's missing is the granularity —
`basis_drift` is one float per commodity (`state/basis.py:28-35`,
`audit_B_state-market-surfaces.md:60-68`) and the YAML configures
only `basis_model: "ewma_5min"` (`config/commodities.yaml:18`), a
producer that does not exist in code (`audit_B_state-market-surfaces.md:480-488`).
The structural form is right; no live producer fills it from a curve.

### 3g. Adverse-selection and order-flow signals are universally absent (C02-09, C02-12, C02-15, C02-31, C02-32, C02-38, C08-54, C08-55, C08-56, C08-68, C08-69, C08-106, C10-30, C10-50)

The Phase C corpus repeatedly returns to the practitioner stack item:
"spread = max(GLFT-style nominal spread, adverse-selection-protection
spread keyed to recent signed flow plus VPIN-like toxicity)" (C02-80).
The live code has none of: a flow-side classifier (Lee-Ready, BVC, or
otherwise), an OFI computation, a per-bucket markout history, a
fundamental-trader detector, or a sharp-quant-vs-retail taxonomy
(C08-63 through C08-67). This blocks the C02-31 / C02-32 / C08-106 /
C10-50 alpha-signal-in-drift / adverse-selection-skew layer
completely.

The closest the live code has to "order-flow sensitivity" is the
publisher-floor gate `tick.n_publishers ≥ pyth_min_publishers` at
`engine/pricer.py:66-69`, which is a Pyth-publisher-quorum check, not
a counterparty-signal check. C08-69's claim that "early in the week,
adverse selection reflects fundamental traders' persistent
informational advantage; late in the week, it concentrates around
USDA releases and the Friday snapshot" cannot land without a
Kalshi-side fill stream and a bucket-aware markout pipeline; neither
exists.

---

## 4. Ambiguities — code sites where intent is unclear

A handful of code sites carry plausible reads on either side of the
audit. They are flagged here as "evidence both ways" rather than
classified.

**A1. `basis_drift` semantics — alpha vs carry (C02-31, C02-83 vs
C02-52).** The single annualized scalar `basis_drift` at
`state/basis.py:28-35` enters the forward at `models/gbm.py:35` in a
form structurally identical to both the carry term `(r+u−y)` of
C02-52 (Kaldor–Working) and the alpha-shift term of C02-31
(Cartea–Jaimungal–Ricci "buy low sell high"). Evidence for "carry":
the docstring at `state/basis.py:8-9` says "annualized so it composes
directly with τ in the GBM forward" and the producer string in YAML
is `basis_model: "ewma_5min"` (`config/commodities.yaml:18`) — an
EWMA on a basis differential is a carry estimator, not an alpha. Evidence
for "alpha": the field is also called `drift` in YAML
(`config/commodities.yaml:17`) with value `0.0`, which suggests "any
shift to the forward, not specifically carry." Phase C02-83
("production desks run dozens of alpha signals in the drift; most
academic papers assume zero drift") is consistent with the
zero-default. The audit row C02-31 was tagged `partial / major`
under the carry reading; if the maintainer's intent is alpha, the
gap is `wrong / blocker` (one alpha vs many).

**A2. `params_version` — calibration vintage vs feature flag.** The
`GBMTheo` dataclass carries `params_version: str = "v0"` at
`models/gbm.py:60-66` and the registry passes
`cfg.raw.get("params_version", "v0")` (`models/registry.py:33`). No
YAML block sets the field (`audit_B_models-registry.md:391-393`).
Evidence for "calibration vintage": the docstring at
`models/gbm.py:62-64` says "params_version identifies the calibration
vintage this instance was built against — carried through to
TheoOutput for provenance." Evidence for "feature flag": the value is
plumbed through to `TheoOutput.params_version` and the
`SanityChecker` does not gate on it (`validation/sanity.py:38-68`),
so it is currently a free-form string the consumer can interpret as
they wish. If the intended use is a Heston/Bates switch, the audit
rows for C02-42/45/46/75 would shift from "missing" to "partial"; if
it's purely a vintage tag for a single GBM, they remain "missing."

**A3. `engine/event_calendar.py` event-day overlay carrier.** The
trading calendar produces τ as a scalar per `(commodity, now_ns,
settle_ns)` (`engine/event_calendar.py:96-107`). The YAML has an
`event_calendar` block per commodity
(`config/commodities.yaml:24-28`) with fields `name`, `day_of_week`,
`time_et`, and `vol_adjustment` — no Python reader consumes any of
these (`audit_B_engine-calendar.md:240-251`). Evidence for "future
home of the C02-66 / C08-97 jump-intensity overlay": the YAML schema
already carries the right shape and the file `event_calendar.py` is
named the way the C02-66 `λ_t^J` framework would suggest. Evidence
for "static documentation": the YAML comment at
`config/commodities.yaml:21` says the approximation lives "in
`engine/event_calendar.py`," which suggests the YAML is read-by-human
intent. Until a producer materializes, the audit treats the C02-47 /
C02-66 / C08-96 / C08-97 rows as `missing`; if intent (A3) is to
populate the YAML reader path next, they would shift to `partial`.

**A4. `SanityChecker.check`'s `spot` argument.** `validation/sanity.py:38`
takes `spot: float` keyword-only and uses it only inside a
diagnostic error message at `:67`
(`audit_B_validation-sanity.md:313-320`). Evidence for "diagnostic-
only": the gate logic at `:43-68` never compares `spot` to anything.
Evidence for "intended growth into a price-level gate": a future
"reservation-price-monotone-around-spot" check (C02-24's `r = S −
γσ²(T−t)q`) would naturally need `spot` as an input. The audit row
for C02-24 was tagged `missing / blocker`; if the maintainer intends
`spot` to grow into a reservation-price gate, the gap is "missing
but architecturally signposted."

**A5. `_MODEL_BUILDERS`'s commented-out neighbours.** The
`models/registry.py:34-37` block lists `"jump_diffusion"`,
`"regime_switch"`, `"point_mass"`, `"student_t"` as commented-out
deliverables. Evidence for "the system is on a known roadmap toward
C02-45 / C02-46 / C02-75": the commented entries name two of the
three Phase C02-75 components (jump-diffusion, regime-switch).
Evidence for "the comments are aspirational": none of the four has
an associated stub builder file in `models/`, and the four
commodities tagged with these models in YAML
(`config/commodities.yaml:62-80`) are also `stub: true`, so no live
path even reaches the dispatch table. The audit rows for C02-45 /
C02-46 are tagged `missing`; if the roadmap is real, the appropriate
read is "deliberately deferred," which would not change the gap class
under Phase D's rubric but would change the tone of the maintainer-
question rollup in §5.

---

## 5. Open questions for maintainers

These are the questions a maintainer would need to answer before
Phase F (remediation) can act on the table above.

1. **Is the C02 / C08 / C10 corpus the spec the live code is being
   built toward, or is it research input that the system may decline
   to implement?** The cartography (`audit/audit_A_cartography.md:198-200`)
   notes "none of the code imports from `research/`"; the README
   describes a "Live Kalshi commodity theo engine" but the code has
   no Kalshi side. If the corpus is the spec, almost every blocker in
   §2 maps to a deliverable. If it is research input, the priority
   ordering may differ.
2. **Is `basis_drift` a carry term, an alpha term, or both?** See
   ambiguity A1. The YAML mixes `drift: 0.0` and
   `basis_model: "ewma_5min"`; the docstring says carry; the field
   is consumed as a forward-shift. The audit treats it as "carry,
   partially good for C02-52, missing for C02-31"; a different read
   would re-tag those rows.
3. **Which of the four commented-out builders in
   `models/registry.py:34-37` (`jump_diffusion`, `regime_switch`,
   `point_mass`, `student_t`) is next?** C02-45 (Merton) and C02-75
   (GARCH/Heston + jumps) point to `jump_diffusion`; C02-46 (Bates
   SVJ) requires both stochastic vol and jumps — is the plan to
   ladder up, or to skip directly to a Heston SV implementation?
4. **Is the σ-as-scalar interface a deliberate Deliverable-1
   simplification or the long-term shape?** The docstring at
   `state/iv_surface.py:1-12` claims "the upgrade is additive";
   `audit_B_state-market-surfaces.md:543-553` notes the additivity
   claim is unsupported because the public method
   `atm(commodity, *, now_ns) -> float` cannot grow strike/expiry
   parameters without a signature change. The C02-51 / C02-43 / C08-33
   audit rows depend on which side wins.
5. **Is there an architectural plan for the Kalshi side of the
   system?** No `feeds/kalshi*`, no `state/kalshi_book*`, no
   `engine/quoter*` exists. The blocker rows for C08-01, -04, -05,
   -08, -13, -122 and the C10-01, -02, -50 rows all reduce to "the
   Kalshi product is not represented." A maintainer answer of "yes,
   it's coming next" vs "the GBM digital is the engine's only
   product" changes the read of the entire audit.
6. **Is the `engine/scheduler.py` skeleton (with `IV_UPDATE`,
   `BASIS_UPDATE`, `EVENT_CAL` priorities at lines 21-26) intended
   to become the producer-side wiring for the missing surfaces?**
   `audit/audit_A_cartography.md:254-257` flags it as red flag #5
   (defined but not wired). The C02-66 / C08-97 event-day overlays
   would naturally land via `EVENT_CAL`; the C02-51 calendar-indexed
   σ would land via `IV_UPDATE`. Whether the scheduler is the
   intended carrier shapes the §3 narrative for those gaps.
7. **What is the expected fill-intensity calibration source?** C02-22
   and C08-43 both call out `λ(δ) = A exp(−kδ)` as empirically
   calibrated. `calibration/` is empty (`audit/audit_A_cartography.md:122-126`),
   `.gitignore:21-22` excludes `calibration/params/*.json`, and no
   producer writes to it. The C02-22 / C02-28 / C02-29 / C08-42 /
   C08-107 audit rows are "missing" partly because there is nowhere
   to put the calibration; a maintainer plan would re-shape the
   priority.
8. **Is the choice of GBM (constant σ) inside `models/gbm.py:35-42`
   intended to remain the default for all CME commodities, or is it
   only a baseline for soybean's `KXSOYBEANW` weekly density?**
   C02-71/C02-74 say lognormal-thin tails are wrong for grains; the
   YAML lists `corn`, `soy`, `wheat`, `coffee` all under GBM (with
   `wheat`/`coffee` flipped to `jump_diffusion` but stubbed). If the
   long-run plan is "GBM never quotes a grain in production,"
   several of the major-severity rows (C02-71, C02-75, C08-25)
   become "missing but planned out."
9. **Is `params_version` intended to do real work?** See ambiguity
   A2. If it is a real switch for choosing among {GBM, Heston, Bates}
   at the same `model_name="gbm"` level, several major rows shift.
   Otherwise it is a vintage tag.
10. **Where is the Kalshi position / inventory state expected to
    live?** Phase C08-86 / C08-87 / C08-88 frame inventory as a
    book-level aggregate net delta cap. The repo has no `state/book*`,
    no `state/inventory*`, no `state/positions*`. The C02-30 / C02-79
    / C08-40 / C08-47 / C08-105 / C10-52 / C10-53 audit rows all
    depend on where this state will land; without it, every quoting
    formula is unfillable in code.

---

## 6. Coverage check

Research citations (distinct C-ids in §2 + §3 + §4): exceeds 100 —
well above the floor of 10. Code citations (distinct file:lo-hi
references in §2 + §3 + §4): exceeds 30 — well above the floor of 10.
Every row in §2 has at least one research C-id and at least one code
citation (or, for `missing` rows where no analogous code site exists,
a Phase A inventory citation pointing to the absence and a note on
why). No row was tagged `already-good` without a concrete code-side
piece of evidence: C08-07, C08-09, C08-57, C08-58 are the four
`already-good` rows, of which C08-07 / C08-09 cite `models/gbm.py` and
C08-57 / C08-58 cite the Phase A absence of an AMM module — a
negative-claim alignment which is the appropriate evidence for those
specific Phase C "does NOT transfer" claims.

End of Audit D — Topic 1 of 10.
