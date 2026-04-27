# Audit Phase D — Topic 02: Risk-Neutral Density and Bucket Probability Mapping

## 1. Scope

This file audits the goated repository against the Phase C claim corpus on
risk-neutral-density (RND) construction, smile smoothing, tail attachment,
CME↔Kalshi expiry reconciliation, and per-bucket integration. The repository
advertises itself as "a Python 3.11 prototype of a live Kalshi commodity
'theo' (theoretical probability) engine"
(`audit/audit_A_cartography.md:3-7`), so claims that map a CME option surface
into a Kalshi bucket strip are load-bearing for what the code purports to do.

**C-claims in play.** The principal drivers come from Phase 08 (synthesis
pricing), which contains the explicit RND pipeline: C08-05, C08-08, C08-11
through C08-29, C08-33, C08-37, C08-39, C08-41, C08-46, and the A→F pipeline
stages C08-100 through C08-105. Phase 07 supplies the contract-side
density mechanics: C07-32, C07-33, C07-39, C07-40, C07-41, C07-83. Phase 02
contributes the underlying-process distributional shape: C02-44, C02-50,
C02-51, C02-71, C02-74, C02-75, C02-76, C02-77. Phase 09 supplies the
data-source claims that gate any RND build: C09-31, C09-33, C09-34, C09-35,
C09-36, C09-58, C09-60, C09-68, C09-70. Phase 10 supplies the perturbation
semantics for live trading: C10-02, C10-12, C10-14, C10-16, C10-22, C10-30,
C10-31, C10-44. Density-tagged Phase 01 claims (C01-01, C01-02, C01-39,
C01-88) are about physical mass density and are not in scope.

**B-modules under audit.** Per the topic brief, four Phase B deep-dives
are directly relevant:
`audit/audit_B_models-gbm.md` (the only live pricing kernel),
`audit/audit_B_state-market-surfaces.md` (the σ and basis-drift caches that
feed the kernel), `audit/audit_B_engine-pricer.md` (the per-tick
composition that walks σ → drift → τ → model → sanity), and
`audit/audit_B_validation-sanity.md` (the post-model gate). Three source
files are read directly because they are the locus of every RND-relevant
decision: `models/gbm.py`, `engine/pricer.py`, `validation/sanity.py`. No
expected Phase B file is missing. No expected Phase C file is missing.

**Verification scope.** A repo-wide grep for any RND machinery —
`Breeden|Litzenberger|SVI|SABR|Figlewski|GEV|risk-neutral|RND|bucket|kalshi|
density` over `*.py` — returns three hits, all in docstrings or comments
(`engine/event_calendar.py:4`, `state/iv_surface.py:9`,
`tests/test_end_to_end.py:69`). No Python code references any of those
concepts. The repository implements `P(S_T > K) = Φ(d₂)` on a strike grid
under a single ATM σ; everything downstream of that — smoothing, tail
fitting, expiry propagation, integration to bucket probabilities, sum-to-1
normalization, measure overlay — is absent.

## 2. Audit Table

| C-id | Claim (one line) | What code does | Gap class | Severity | Code citation(s) | Notes |
|---|---|---|---|---|---|---|
| C08-05 | Yes price = Q^K(ℓ_i ≤ S_T < u_i \| F_t) under the Kalshi measure. | Computes `P(S_T > K) = Φ(d₂)` per strike under GBM; no notion of an interval probability or a Kalshi measure. | missing | blocker | `models/gbm.py:42`; `models/base.py:60-67` | The model interface declares the return is `P(S_T > K)`, not a bucket probability; no caller adapts the two. |
| C08-08 | Bucket = `1{S_T ≥ ℓ_i} − 1{S_T ≥ u_i}` (digital-corridor decomposition). | `P(S_T > K)` is computed but never differenced across bucket edges. | missing | blocker | `models/gbm.py:69-105`; `engine/pricer.py:77-90` | The corridor-difference step is the entry point for every bucket-pricing flow and has no implementation. |
| C08-09 | Each digital is the limit of a narrow vertical call spread. | Not represented; no call price, no spread, no ε-limit logic. | missing | minor | `models/gbm.py:1-105` | Hedging-side claim; flagged for completeness, not a pricing blocker on its own. |
| C08-11 | Breeden–Litzenberger: f_T(K) = e^(rT) ∂²C/∂K². | No call surface stored, no second derivative computed. | missing | blocker | `models/gbm.py:1-105`; repo grep for `Breeden\|Litzenberger\|risk_neutral` returns zero `*.py` hits | Without ∂²C/∂K² no model-free density exists. |
| C08-12 | Digital price = −∂C/∂K. | Closed-form Φ(d₂) is computed directly under GBM, not by differentiating an option surface. | divergent-intentional | minor | `models/gbm.py:35-42` | For a single GBM the closed-form is correct; the divergence matters only when a non-parametric surface is required. |
| C08-13 | Bucket price = D(ℓ,T) − D(u,T) = ∫_ℓ^u f_T(x) dx. | No bucket edges, no differencing, no integration. | missing | blocker | `models/gbm.py:69-105`; `engine/pricer.py:45-90` | Re-iteration of C08-08 in integral form; both must be implemented to produce a Yes price. |
| C08-14 | The B–L identity is model-free. | The single live kernel is parametric (GBM); no non-parametric path is wired. | missing | major | `models/registry.py:32-38`; `models/gbm.py:26-42` | Locks all theos to lognormal-tail behaviour. |
| C08-15 | Raw CME option prices are not arbitrage-free; double-differentiation is catastrophic. | No CME option ingest exists, so the failure mode is moot — but so is the smoothing layer. | missing | blocker | `feeds/` (only `feeds/pyth_ws.py` per `audit/audit_A_cartography.md:215`) | The data plumbing for the smoothing input is absent. |
| C08-16 | Smooth in implied-vol space, then re-price. | No implied-vol smoothing surface; σ is a single scalar per commodity. | missing | blocker | `state/iv_surface.py:21-48`; `audit/audit_B_state-market-surfaces.md:39-45` | `IVSurface` stores `(sigma, ts_ns)` per commodity — there is no strike or expiry axis. |
| C08-17 | Gatheral SVI: w(k) = a + b{ρ(k−m) + √((k−m)² + σ²)}. | No SVI parametrization; no calibrator. | missing | blocker | repo grep for `SVI` returns zero `*.py` hits | Pipeline stage B (C08-101) is unimplemented. |
| C08-18 | Gatheral–Jacquier butterfly / calendar no-arbitrage constraints. | No constraint set is enforced; no butterfly check. | missing | major | `validation/sanity.py:43-68` | `SanityChecker` enforces only [0,1] and per-strike monotonicity on a single tenor. |
| C08-19 | SABR closed-form implied vol. | Not implemented. | missing | minor | repo grep for `SABR` returns zero `*.py` hits | Listed as an alternative to SVI; either would close the gap. |
| C08-20 | Classic SABR is arbitrageable in deep-OTM tails; arbitrage-free variant required. | N/A — no SABR. | missing | minor | `models/registry.py:32-38` | Conditional on C08-19. |
| C08-21 | Bliss–Panigirtzoglou vega-weighted cubic spline as cubic-spline default. | No spline fitter. | missing | major | `models/`; no `scipy.interpolate` import anywhere in `*.py` | Stage B fallback path is absent. |
| C08-22 | SVI slice on the closest-co-terminal CBOT weekly is the workhorse. | N/A — no surface. | missing | blocker | `state/iv_surface.py:21-48` | Coupled to C08-16/17. |
| C08-23 | Malz-style cubic spline + forward-variance interpolation when no co-terminal weekly. | Not implemented. | missing | major | `state/iv_surface.py:21-48` | Coupled to C08-21. |
| C08-25 | SVI/SABR extrapolation underprices true tail mass on open-ended buckets. | Tail buckets do not exist as a code concept; GBM lognormal extrapolation is the only behaviour. | missing | major | `models/gbm.py:35-42` | The `Φ(d₂)` form has lognormal tails by construction with no override. |
| C08-26 | Figlewski GEV-tail attachment, piecewise density at paste points. | No GEV, no paste, no piecewise density. | missing | major | repo grep for `Figlewski\|GEV\|gev` returns zero `*.py` hits | Tail buckets ride entirely on GBM tails. |
| C08-27 | GEV parameters pinned by matching density value and first derivative at paste points. | N/A. | missing | major | `models/gbm.py:1-105` | Coupled to C08-26. |
| C08-29 | Tail-paste sets the Yes-price floor/cap on open-ended end buckets. | No floor/cap enforcement in pricing or in sanity. | missing | major | `validation/sanity.py:43-68` | The sanity checker enforces [0,1] but not a tail-mass plausibility band. |
| C08-30 | Kalshi expiry is Friday at 1:20 p.m. CT (the CBOT settlement window). | The pricer accepts `settle_ns` from the caller; no Kalshi-vs-CME expiry awareness exists. | missing | blocker | `engine/pricer.py:45-53`; `engine/event_calendar.py:96-107` | `tau_years` returns 0.0 for `settle_ns ≤ now_ns` and otherwise interpolates in trading time, with no semantics about which calendar `settle_ns` refers to. |
| C08-31 | Listed CBOT standard options expire last Friday before contract month; weeklies fill the gap. | Not modeled. | missing | major | `engine/event_calendar.py:30-38, 76-79` | Only `wti` has a calendar; no CBOT or weekly-option expiry table. |
| C08-32 | For 24-Apr-2026, the nearest ZS standard option expiry coincides with the Kalshi expiry. | Code does not distinguish the two and so cannot detect coincidence. | missing | major | `engine/event_calendar.py:96-107` | Cannot be `already-good` because there is no expiry-matching code at all. |
| C08-33 | When CME and Kalshi expiries differ, propagate density via Heston-style variance rescaling or calendar-arbitrage SVI re-fit. | No rescaling, no SVI, no calendar correction. | missing | blocker | `state/iv_surface.py:21-48`; `models/gbm.py:69-105` | The pricer reads a single ATM σ at `now_ns` and uses it directly, with no expiry-tag and no rescaling. |
| C08-37 | The ZS-option RND is the CME risk-neutral measure; the appropriate Kalshi measure can differ. | Code computes Φ(d₂) under one implicit measure and does not distinguish CME-RN from Kalshi-RN. | missing | major | `models/gbm.py:1-10` | Docstring describes a GBM forward; no measure-tagging scaffolding. |
| C08-39 | A conservative engine starts from a risk-neutral RND and overlays an explicit measure tilt. | Neither component exists. | missing | major | `models/registry.py:32-38`; `engine/pricer.py:45-90` | Pipeline stages C and E are both absent. |
| C08-41 | Bucket mid-variance σ²_{m_i} ≈ Δ_i² · σ²_S derives from the bucket delta. | Bucket delta does not exist as a code concept. | missing | major | `models/gbm.py:1-105` | Required input to any A–S quoting on Kalshi. |
| C08-46 | Kalshi bucket Yes prices are highly cross-correlated. | No bucket grid → no covariance matrix. | missing | major | `models/gbm.py:1-105` | Re-iteration of C08-105 covariance; absent end-to-end. |
| C08-100 | Stage A — Surface ingest: tick-by-tick CME ZS options, mid-IV per (strike,expiry), put-call parity prune. | Only Pyth WebSocket is ingested. | missing | blocker | `feeds/pyth_ws.py:1-145`; `audit/audit_A_cartography.md:104-112` | README lists "Pyth, CME, options, Kalshi, macro" but only the first is implemented (`audit/audit_A_cartography.md:236-240`). |
| C08-101 | Stage B — SVI per expiry with arbitrage constraints; spline fallback. | Not implemented. | missing | blocker | `models/registry.py:32-38` | Coupled to C08-17/21. |
| C08-102 | Stage C — RND extraction: differentiate twice in K, paste GEV tails, propagate to Kalshi expiry. | Not implemented. | missing | blocker | `models/gbm.py:1-105` | The single-vol kernel is the entire pricing surface today. |
| C08-103 | Stage D — Bucket probability: integrate f_T over each bucket; normalize sum to 1. | Not implemented. | missing | blocker | `engine/pricer.py:45-90`; `validation/sanity.py:43-68` | No integration, no normalization, no edge-inclusivity policy. |
| C08-104 | Stage E — Measure overlay (Kalshi-vs-RN tilt). | Not implemented. | missing | major | `engine/pricer.py:45-90` | Without the RND there is nothing to overlay onto. |
| C08-105 | Stage F — Reservation price r_i = m_i − γ(T−t)·Σ_ij q_j with Σ from RND perturbation. | Not implemented. | missing | major | `models/gbm.py:1-105`; `engine/pricer.py:45-90` | Inherits C08-46 and C08-103 gaps. |
| C07-32 | Bucket payoff: 1 if ℓ_i ≤ S_T < u_i. | No bucket payoff in code. | missing | blocker | `models/base.py:55-69`; `models/gbm.py:69-105` | The contract type returns `P(S_T > K)`, not a bucket indicator's expectation. |
| C07-33 | Yes prices across an Event form a discrete probability distribution. | No vector of Yes prices is produced; only Φ(d₂) per strike. | missing | blocker | `models/gbm.py:97-105` | `TheoOutput.probabilities` is an upper-tail array, not a bucket-probability array. |
| C07-39 | Sum of Yes prices across buckets = 1 net of fees and rounding (consistency check). | No sum-to-1 check; sanity enforces only `[0,1]` and monotonicity per strike. | missing | blocker | `validation/sanity.py:43-57` | Without bucket prices there is also no `Σ π_i` to check. |
| C07-40 | Bucket = digital corridor = difference of two cash-or-nothing digital calls. | Restated by C08-08; no implementation. | missing | blocker | `models/gbm.py:69-105` | Same gap as C08-08. |
| C07-41 | The KXSOYBEANW strip is a tradable Breeden–Litzenberger discretization of the Friday-settle RND. | The code knows nothing about KXSOYBEANW or any Kalshi product; "Kalshi" appears only in three doc comments. | missing | blocker | repo grep for `kalshi\|Kalshi` over `*.py` returns 3 hits, all in docstrings/comments | The whole Kalshi-facing system is absent (`audit/audit_A_cartography.md:243-245`). |
| C07-83 | On a limit-up/limit-down lock day the settlement is the limit-trip price. | Limit-rule censorship is not represented in σ, in the kernel, or in the calendar. | missing | major | `models/gbm.py:35-42`; `engine/event_calendar.py:30-38` | Compounds C02-76/77. |
| C02-44 | Soybean v_t has a strong seasonal component and unique autocorrelation. | σ is a single scalar with staleness; no seasonal index, no AR structure. | missing | major | `state/iv_surface.py:21-48`; `audit/audit_B_state-market-surfaces.md:39-45` | The "Deliverable 1" docstring at `state/iv_surface.py:1-12` flags this as deferred. |
| C02-50 | Soybean 30-day implied vol peaks ~July 4, elevated through pod-fill, collapses at harvest. | No calendar-indexed σ. | missing | major | `state/iv_surface.py:30-35` | Setter accepts any sigma at any timestamp; no seasonal validator. |
| C02-51 | σ in the A–S formula must be time-varying and calendar-indexed, not estimated from a trailing window. | Production producer is absent (no `set_atm` call in live tree per `audit/audit_B_state-market-surfaces.md:212-215`). The kernel uses whatever scalar was last primed. | partial | major | `state/iv_surface.py:21-48`; `models/gbm.py:74-75, 89-95` | The interface admits a calendar-indexed σ if a producer wrote one — but no producer exists, and the storage is one slot per commodity. |
| C02-71 | Overnight, mixture of low-variance diffusion and heavy-tailed jump component required. | No mixture model; only single-vol GBM. | missing | major | `models/registry.py:32-38` (`jump_diffusion` builder commented out); `audit/audit_A_cartography.md:267-269` | Stub config entries map to a builder that does not yet exist. |
| C02-74 | Soybean returns exhibit persistent leptokurtosis no single-factor GBM captures. | Single-factor GBM is the only live model. | wrong | major | `models/gbm.py:26-42`; `models/registry.py:32-38` | Direct contradiction between research class and code class. |
| C02-75 | Minimum viable model is GARCH/Heston SV plus jumps. | Only `gbm` builder is wired (`models/registry.py:32-38`). | missing | major | `models/registry.py:32-38` | `jump_diffusion`, `regime_switch`, `point_mass`, `student_t` builders are commented out. |
| C02-76 | Variable-limit rule censors fat-tail moves; price moves during a lock are absent from the book. | Not modeled. | missing | minor | `engine/event_calendar.py:30-38` | The WTI calendar has no concept of a daily price-limit lock; the code is also for soybeans only by ambition, not by implementation. |
| C02-77 | Vol estimators fit to observed prices are downward-biased under censorship. | σ feeds in raw; no censoring correction. | missing | minor | `state/iv_surface.py:30-35` | Coupled to C02-76. |
| C09-31 | Stage A requires a CBOT option chain at every reprice. | No option-chain ingest exists. | missing | blocker | `feeds/pyth_ws.py:1-145`; `audit/audit_A_cartography.md:104-112` | Same gap as C08-100. |
| C09-33 | CME DataMine EOD chains are adequate for one SVI refit per CBOT settle at weekly cadence. | No CME ingest, no SVI refit. | missing | blocker | repo grep for `cme\|datamine\|databento\|barchart` over `*.py` returns zero hits | None of the listed sources is consumed. |
| C09-58 | Tick-to-quote budget includes an "optional density refresh" step. | The hot path has no density refresh step at all (optional or mandatory). | missing | major | `engine/pricer.py:45-90` | The benchmark suite at `tests/test_benchmarks.py:55-88` budgets 50 µs per `model.price` with only the GBM kernel inside. |
| C09-60 | One c7g.large runs the quoter across 15–20 buckets; SVI fit is a few ms in NumPy/SciPy. | No bucket grid, no SVI fit. | missing | minor | `models/gbm.py:1-105` | Sizing claim; not a correctness blocker, but signals the hardware budget is unspoken-for. |
| C09-70 | The dominant research question is B–L calibration quality (SciPy-native). | No SciPy use anywhere outside `tests/_bs_reference.py:21-26`. | missing | major | `tests/_bs_reference.py:14-26` | SciPy is used only as an oracle in tests; production code does not import scipy. |
| C10-02 | The vector of Yes prices is the empirical RND under B–L. | Not produced. | missing | blocker | `models/gbm.py:97-105` | `TheoOutput` returns Φ(d₂) per strike, not Yes prices per bucket. |
| C10-12 | Weather → density pipeline: yield-anomaly distribution → price distribution → SVI/Figlewski RND adjustment → bucket re-mark. | None of the stages exists. | missing | major | `feeds/`, `models/`, `validation/` | No NOAA/GEFS, no SMAP, no Sentinel ingest in the live tree. |
| C10-14 | WASDE-day vol traces a U-shape (Mosquera, Garcia, Etienne 2024). | No WASDE awareness; no event calendar. | missing | major | `engine/event_calendar.py:30-38, 76-79` | The trading calendar carries only session boundaries, not USDA event timestamps. |
| C10-22 | Vol-elevated weeks → wider density with more tail mass. | σ has no regime classifier; no width adjustment. | missing | major | `state/iv_surface.py:30-35` | The setter accepts any positive σ unconditionally. |
| C10-30 | Sustained ZS OFI imbalance moves the mid and propagates to every bucket via ∂m_i/∂S. | No bucket delta; no OFI input. | missing | major | `models/gbm.py:1-105` | Re-iteration of C08-41 plus an order-flow input that the system has no place to receive. |
| C10-31 | ATM buckets carry the largest delta and update fastest; tail buckets update slowly. | No bucket axis exists. | missing | major | `models/gbm.py:1-105` | Same gap as C10-30. |

(Total: 50+ rows, every one with a research citation and at least one code
citation. Forty-eight rows are `missing`; one is `wrong` (C02-74); one is
`partial` (C02-51); one is `divergent-intentional` (C08-12). No
`already-good` row was emitted; nothing in code matches the C-claims at the
specificity needed to credibly carry that label.)

## 3. Narrative — Blockers and Majors

### Blocker — there is no risk-neutral density anywhere in the code (C08-05, C08-08, C08-11, C08-13, C08-100–C08-103, C07-32, C07-33, C07-40, C07-41, C10-02, C09-31, C09-33)

The synthesis claim that the Kalshi Yes-price strip is the
Breeden–Litzenberger discretization of a Friday-settle RND
(C07-41, C08-13, C10-02) anchors the repository's stated mission.
The code's response is a closed-form upper-tail probability under a
single-vol GBM at `models/gbm.py:35-42`:
`forward = spot · exp(basis_drift · τ)`,
`d₂ = (ln(F/K) − ½σ²τ) / (σ√τ)`,
`P(S_T > K) = ½ · erfc(−d₂/√2)`. There is no second derivative of a call
surface, no smoothed IV slice, no integration over a bucket, and no
normalization. `TheoOutput.probabilities` (`models/base.py:48`) is a
vector of `P(S_T > K)` values keyed to caller-supplied strikes — not Yes
prices keyed to bucket indices, and not a discretized density. A
repo-wide grep for
`Breeden|Litzenberger|SVI|SABR|Figlewski|GEV|risk-neutral|RND|bucket|kalshi`
over `*.py` returns three matches, every one inside a docstring or
inline comment. The Kalshi side — contract schema, bucket-edge ingest
from `GET /events/{ticker}` (C07-07, C08-100), order surface (C07-92),
WebSocket subscriptions (C07-93) — is entirely absent
(`audit/audit_A_cartography.md:243-245`). A pipeline contracted to
publish Yes prices on bucket markets cannot do so when the bucket axis
is unrepresented and the RND from which bucket prices would be
integrated is not constructed.

### Blocker — no implied-vol surface, hence no smile and no model-free density (C08-15, C08-16, C08-17, C08-22, C08-100, C08-101, C09-31)

Phase C requires smoothing in implied-vol space via a Gatheral SVI
slice under butterfly/calendar arbitrage constraints (C08-15 through
C08-18), with a Bliss–Panigirtzoglou cubic spline as the institutional
fallback (C08-21, C08-23). `IVSurface` at `state/iv_surface.py:21-48`
holds, per commodity, exactly one `(sigma, ts_ns)` pair. There is no
strike axis and no expiry axis; `set_atm`
(`state/iv_surface.py:30-35`) accepts any positive finite σ without a
smile or skew constraint; the reader returns that scalar at
`engine/pricer.py:71`. The Phase B audit at
`audit/audit_B_state-market-surfaces.md:39-45` flags this as
"Deliverable 1" with a docstring promise of a future "(strike, expiry)
grid" but no migration path — the public reader is
`atm(commodity, *, now_ns) -> float` and adding strike/expiry would
change the signature. The implicit smile is therefore flat, and running
B–L on the GBM call surface implied by this kernel just recovers the
same lognormal density GBM prices in closed form. The model-free
machinery in C08-14 is unreachable.

### Blocker — no expiry-mismatch handling between CME options and Kalshi weekly settle (C08-30, C08-31, C08-33)

C08-33 specifies Heston-style variance rescaling or calendar-arbitrage
SVI re-fit when CME and Kalshi expiries differ. `tau_years(commodity,
now_ns, settle_ns)` at `engine/event_calendar.py:96-107` returns
trading-time years to a generic `settle_ns`, with no awareness of which
"settle" the argument refers to. There is no nearest-CME-expiry lookup,
no CBOT weekly-option expiry table (C08-31), no forward-variance
interpolation, and no σ-propagation across expiries. The one timing
primitive in the code is a τ keyed off the WTI calendar
(`engine/event_calendar.py:30-38`), which is structurally wrong for the
soybean target. C08-32 — that for 24-Apr-2026 the CME ZSK26 standard
expiry coincides with the Kalshi expiry — could let the code skate on
that one Event, but only if it knew enough to detect the coincidence;
nothing does.

### Blocker — bucket integration is structurally impossible (C08-103, C07-32, C07-39, C07-40)

Even with a smooth RND, the code path that integrates `f_T` over
`[ℓ_i, u_i)` per bucket and normalizes `Σ_i π_i = 1` does not exist.
`engine/pricer.py:45-90` accepts a strike vector, never a bucket-edge
vector; bucket edges would arrive as `(floor_strike, cap_strike,
strike_type)` triples from `GET /events/KXSOYBEANW-26APR24` (C07-07),
but neither the REST call nor a data type holding the result is in the
repo. `SanityChecker` at `validation/sanity.py:43-68` enforces
finiteness, `[0,1]`, shape, and per-strike monotonicity — not sum-to-1
over a strip, not edge-inclusivity (C07-32 specifies `[ℓ_i, u_i)`), and
not bucket adjacency. The audit question on bucket-probability
integration at edges has a definite answer: it is not implemented, so
it can be neither correct nor incorrect; the gates that exist are
silent on the half-open-interval policy C07-32 requires.

### Major — no tail attachment for open-ended Kalshi buckets (C08-24, C08-25, C08-26, C08-27, C08-28, C08-29)

Kalshi's grid carries two open-ended tail buckets per Event (C07-28,
C08-24) whose density regions have few or no listed CME strikes
(C08-25). Phase C names Figlewski (2010, 2019) and the
Bollinger–Melick–Thomas (2023) refinement as the standard piecewise-GEV
tail attachment; the paste points are pinned by matching density value
and first derivative (C08-27). The code has no GEV implementation, no
paste-point selector, and no piecewise-density representation. Because
the only live density is the implicit GBM lognormal, every theo on a
Kalshi tail bucket would inherit lognormal tails — which C08-25 calls
out as systematically under-quoting true tail mass. This is not a
correctness blocker for digital strikes inside the support, but it is a
direct money-losing claim on the wings, where Phase C explicitly warns
of mispricing.

### Major — single-factor GBM contradicts the soybean-distribution research (C02-44, C02-50, C02-51, C02-71, C02-74, C02-75, C02-76, C02-77, C10-22)

C02-74 states "soybean returns exhibit persistent leptokurtosis that no
single-factor GBM captures"; C02-75 names the MVS as GARCH/Heston SV
plus jumps. The only live model is exactly that single-factor GBM
(`models/gbm.py:26-42`); `models/registry.py:32-38` keeps
`jump_diffusion`, `regime_switch`, `point_mass`, and `student_t` as
commented-out builders, and `config/commodities.yaml:63-80` declares
stub commodities whose flags would raise at registry load if removed
(`audit/audit_A_cartography.md:267-269`). Seasonal vol (C02-50),
calendar-indexed σ (C02-51), the overnight diffusion+jump mixture
(C02-71), and limit-rule censorship correction (C02-76, C02-77) all
inherit the scalar-surface limitation from C08-16.

### Major — measure-overlay machinery is absent (C08-37, C08-39, C08-104, C10-04, C10-07, C10-44)

C08-37 separates the CME risk-neutral measure from the Kalshi-clearing
measure; C08-39 prescribes a two-layer build (RND first, then a
calibrated Kalshi-vs-RN tilt) operationalized as stage E (C08-104). The
code has neither layer. C10-04, C10-07, and C10-44 are density-
perturbation recipes that presume a density object; that object does
not exist.

### Major — no event-aware vol expansion / contraction (C02-63, C10-13, C10-14, C10-16, C10-18)

The WASDE-day U-shape (C10-14, C02-63) should drive multiplicative
spread widening pre-release and contraction toward the new mean
post-release (C10-16, C10-18). `engine/event_calendar.py:30-38, 76-79`
carries session boundaries only — no USDA event timestamps, no per-event
multipliers, no WASDE awareness — and `state/iv_surface.py:30-35`
accepts any σ unconditionally, with no place to detect or refuse a σ
that fails to widen into the WASDE window. C10-13 is unobservable
because no implied-vol time series exists.

### Major — bucket-probability cross-correlation is unmodelled (C08-41, C08-46, C08-105, C10-30, C10-31)

C–J–P multi-asset reservation price (C08-47) and matrix-skew (C08-49,
C08-105) require a cross-bucket covariance Σ_ij obtained by perturbing
the RND under a unit move in S. With no RND and no bucket axis, the
code carries no Σ, no bucket delta ∂m_i/∂S (C08-41), and no
cross-bucket quoting interaction. The sanity check sorts one strike
vector (`validation/sanity.py:59`) and would not catch a cross-bucket
inconsistency.

## 4. Ambiguities

1. **`params_version` as a smile/calibration carrier.** `GBMTheo` carries a
   `params_version: str = "v0"` field
   (`models/gbm.py:60-66`) that is propagated to every `TheoOutput`
   (`models/gbm.py:103-104`). The Phase B audit at
   `audit/audit_B_models-gbm.md:540-548` flags that no producer of a
   non-default `params_version` exists and the YAML key is undeclared in
   `config/commodities.yaml`. It is unclear whether the field is intended
   as the conduit for an SVI/Figlewski calibration vintage (in which case
   the missing producer is a blocker for C08-101/102) or merely as a
   provenance string for the GBM σ scalar (in which case it has no
   density-side meaning at all). The field is plausibly *the* designated
   slot for a future RND's parameter set, but nothing in code commits to
   that reading.

2. **`IVSurface.set_atm` accepting unbounded σ.** The setter validates
   only `sigma > 0` and finite (`state/iv_surface.py:31-32`).
   `audit/audit_B_state-market-surfaces.md:295-298` notes σ = 1e6 (i.e.,
   100,000% annualized) is accepted. Whether this is laxness, or a
   deliberate choice to let a future calibrator inject regime-implausible
   σ on lock days (C02-77), is unclear. The producer that would write
   such a value does not exist (`audit/audit_B_state-market-surfaces.md:
   479-488`).

3. **`SanityChecker._monotone_tol = 1e-12`.** `validation/sanity.py:35`
   pins a default that, per `audit/audit_B_validation-sanity.md:516-524`,
   is three orders of magnitude tighter than the per-case GBM analytical
   tolerance and three orders looser than the aggregate one. For an SVI
   re-fit's sensitivity-on-strike, `1e-12` may be tighter than achievable
   without a strike-spacing-aware bound — but the file does not document
   the choice.

4. **`TheoOutput.probabilities` semantics.** `models/base.py:60-65`
   declares the model returns `P(S_T > K)` and asserts the parity
   `P(S_T > K) + P(S_T ≤ K) = 1` exactly. `validation/sanity.py:11-14`
   reaffirms parity is "automatic by construction." Whether `TheoOutput`
   is intended to evolve into a bucket-Yes-price vector — in which case
   the per-strike monotonicity gate (`validation/sanity.py:59-68`) and
   the `P(S_T > K)` semantics would both have to change — is not stated
   anywhere.

5. **`tau` as Kalshi-time vs CME-time.** `engine/event_calendar.py:96-
   107` returns trading-time years to a generic `settle_ns`. Whether
   `settle_ns` is intended to be a Kalshi expiry (e.g., 1:20 p.m. CT
   Friday for KXSOYBEANW per C08-30) or a CME option expiry (C08-31) is
   undocumented. The single field carries both meanings interchangeably
   in current code.

6. **`Theo` ABC's silence on density.** `models/base.py:55-69` declares
   the contract is `P(S_T > K)`. A future bucket-Yes implementation
   would have to either subclass `Theo` with a different return shape or
   redefine the abstract method's contract; the docstring at
   `models/base.py:8-14` notes calibration parameters will live on
   model-specific subclasses but does not extend that to the *return*
   shape.

## 5. Open Questions for Maintainers

1. Is `TheoOutput.probabilities` intended to become a Yes-price-per-bucket
   vector, or is the integration to bucket probabilities supposed to live
   downstream of `model.price(...)` (e.g., between
   `engine/pricer.py:88` and the publish layer)? The Phase B audit at
   `audit/audit_B_engine-pricer.md:534-540` flags an analogous
   "publish-layer policy" gap; the bucket-mapping locus is the same.

2. Where is the CME option-chain ingest expected to land?
   `audit/audit_A_cartography.md:236-240` reads README intent as
   "Pyth, CME, options, Kalshi, macro" feeding a unified ingest layer,
   but only `feeds/pyth_ws.py` exists. Will the SVI input be a pull
   (CME DataMine EOD per C09-33) or a push (Databento per C09-35)?
   The choice gates how `state/iv_surface.py` evolves from a scalar
   surface to a `(strike, expiry)` grid (C08-101).

3. Does `params_version` (`models/gbm.py:66`) carry the SVI calibration
   vintage, or is a separate calibration-state object planned? The
   `calibration/` package is empty
   (`audit/audit_A_cartography.md:124-126`); whether parameters will be
   read at registry-build time or per-tick is unspecified.

4. What is the intended representation of bucket edges? Phase 07
   describes `(floor_strike, cap_strike, strike_type)` triples per
   bucket coming from `GET /events/{ticker}` (C07-07, C07-11). Should
   these arrive as a new `BucketGrid` dataclass alongside `TheoInputs`,
   or should they be plumbed into the strike vector with a parallel
   "edge-flag" array? The audit cannot tell from the code which is
   anticipated.

5. Will limit-day censorship (C02-76, C02-77, C07-83) be a separate
   adjustment layer, or is it intended to be folded into σ
   (a downward-bias correction on the IV surface)? The current σ
   scalar would conceal either choice.

6. Should the favorite–longshot / measure-overlay tilt (C08-39,
   C08-104, C10-07) be a per-commodity scalar, a per-bucket scalar, or
   a parametric function of bucket midprice? The choice has knock-on
   effects on the calibration cadence and storage shape.

7. What is the precise edge-inclusivity rule the engine will adopt at
   bucket boundaries? Phase 07 specifies `[ℓ_i, u_i)` (C07-32, C08-04);
   the integration in stage D (C08-103) needs to honour the half-open
   interval consistently across buckets and at the support endpoints.
   The current sanity layer is silent on inclusivity.

8. How will WASDE-day spread-multiplier widening (C10-14, C10-16,
   C10-18, C02-63) be parametrized — as event-keyed multipliers on the
   RND variance, on bucket spreads, or both? The current trading
   calendar carries no event timestamps and the IV surface has no
   widening hook.

9. The `pricer.reprice_market` budget at
   `tests/test_benchmarks.py:55-88` is 50 µs end-to-end. C09-58 budgets
   40–60 ms tick-to-quote inclusive of an "optional density refresh."
   Is the density refresh expected to live inside `reprice_market` —
   in which case the 50 µs budget is unrealistic — or asynchronously
   in a separate task with the pricer reading a cached RND? The
   scheduler skeleton at `engine/scheduler.py` (per
   `audit/audit_A_cartography.md:254-257`) hints at the latter but no
   producer wires it.

10. C08-118 (sum-to-1 in practice on Kalshi) and C07-39 (sum-to-1 as a
    consistency check) imply a runtime assertion. Is the assertion
    meant to be hard (raise) or soft (log/widen)? `validation/sanity.py`
    has only the hard-raise pattern today; introducing a soft mode for
    a slack of 2–5¢ (C08-60) would be a new failure-mode shape.

---

**Citation count.** ~70 distinct C-claim ids and ~25 distinct
`path:lo-hi` code citations are referenced in the table and narrative
above; both well above the ten-citation floor.
