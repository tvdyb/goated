# Audit D — Topic 9: Strategy Logic and Signals

## 1. Scope

This audit asks, of every research-corpus claim tagged `strategy`, which
are implemented, which are contradicted, which are partially expressed,
which are ignored. Priority sources per the task brief are Phase C
phase04 (discretionary), phase05 (systematic), and phase10 (synthesis);
`strategy`-tagged claims in phases 01, 02, 03, 06, 08, and 09 are
treated as supporting context and sampled where they bear directly on
quoting, signal selection, hedging, or regime gating.

There is **no Phase B file in scope**. The cartography
(`audit_A_cartography.md §9`) inventories every Python module
(`feeds-pyth`, `state-tick-store`, `state-market-surfaces`,
`state-errors`, `models-interface`, `models-gbm`, `models-registry`,
`engine-pricer`, `engine-scheduler` (unwired per red-flag #5),
`engine-calendar` (WTI-only per red-flag #14), `validation-sanity`,
`benchmarks`, `config`, `tests`). None has a signals / alpha / strategy
/ regime / events / positioning / OFI / inventory / skew / hedge /
quoter / Kalshi / bucket / RND responsibility line. Red-flag #2 states
"the whole Kalshi-facing side of the system is absent." The brief
expected the Phase B set to be empty, and it is.

All Phase C files in scope (phase04, phase05, phase10) plus
`audit_A_cartography.md` are present; no expected file is missing.

For `missing` rows the code citation is the cartography pointer
demonstrating absence (`audit_A_cartography.md §9` / §10). For
`partial`, `divergent-intentional`, or `already-good` rows a specific
file/line range is cited.

## 2. Audit table

| C-id | claim (one-line) | what code does | gap class | severity | code citation(s) | notes |
|---|---|---|---|---|---|---|
| C04-03 / C04-05 / C04-06 | Crush expressions: reverse crush long beans / short products; crushers buy crush when GPM>$2; specs long-crush when board cheap vs GPM | nothing — no ZS/ZM/ZL symbols, no spread book, no GPM | missing | blocker (C04-03) / major | `audit_A_cartography.md §9`; `config/commodities.yaml:58-60` (`soy: stub: true`) | Underlier set restricted to `wti` |
| C04-08 / C04-09 / C04-10 | Crush MR economics: unfiltered loses post-cost (Rechner-Poitras 1993); 3¢ filter lifts profit; reverse-crush hedging pressure (Mou 2010) | not represented | missing | major | `audit_A_cartography.md §9` | No filtered MR signal; no COT |
| C04-11 | July/November is bellwether of old/new-crop tightness | not represented | missing | major | `audit_A_cartography.md §9` | No calendar-spread universe |
| C04-12 / C04-13 / C04-14 / C04-16 / C04-17 | July/Nov spread state (inverse=tight, contango=abundance); commercials fade deep extremes; Moore composite + Farmdoc 3-of-15 counter | not represented | missing | major (C04-12/13) / minor | `audit_A_cartography.md §9` | No spread-state classifier or seasonal composite |
| C04-18 / C04-19 / C04-20 / C04-21 | Bean/corn ratio (ZSN/ZCN) cluster: definition; >2.5 favors soy, <2.2 corn; long-run ~2.3-2.45; fade extremes vs USDA Acreage | not represented | missing | major | `audit_A_cartography.md §9` | No cross-symbol ratio signal, no USDA parser |
| C04-25 / C04-71 / C04-72 | "Long oilshare = long RFS"; "buy rumor sell fact" Chinese flash-sales; RFS/RVO leaks → oilshare rallies | not represented | missing | minor | `audit_A_cartography.md §9` | No policy / oilshare / flash-sale tape |
| C04-31 / C04-33 / C04-34 / C04-35 / C04-36 / C04-37 | WASDE cluster: 48h flatten-or-fade; whisper-vs-survey; USDA early-yield bias; reduces IV ~70%; canonical fade post-release stall; fade fails on regime-change surprise | not represented | missing | major (C04-31/35/36) / minor | `audit_A_cartography.md §9`; `engine/scheduler.py:21-26` declares `EVENT_CAL` enum, no consumer; `state/iv_surface.py:21-48` (scalar σ) | No WASDE clock, no event-aware IV, no surprise classifier |
| C04-39 / C04-40 / C04-41 | Weather window: Jun-Aug pod-fill; "vol is high by July 4"; overlay 2-wk GFS/ECMWF vs NASS, size into ridges | not represented | missing | major | `audit_A_cartography.md §9` | No NWP / NASS reader / vol-pump model |
| C04-42 / C04-43 / C04-44 / C04-45 / C04-86 / C04-87 / C04-88 / C04-89 / C04-90 / C04-91 | ENSO + basis-extreme cluster: La Niña→SAm dryness; El Niño→SAm benefit; 2021-22 ZM rally; Jan-Feb high-info window; ONI + Jan soil-moisture entry; sizing 1-2% NAV; ±2σ vs 5-yr basis entry; capacity-capped sizing; harvest fade entry/sizing | not represented | missing | minor | `audit_A_cartography.md §9` | No ENSO / soil-moisture / 5-yr basis state |
| C04-47 / C04-48 / C04-54 / C04-55 / C04-56 / C04-58 / C04-59 / C04-60 | Basis-trade cluster: elevators short futures vs long cash; harvest blows out basis; freight-conditional basis; Iowa-State 5-yr $0.76 benchmark; crusher fixing | not represented | missing | minor | `audit_A_cartography.md §9` | No basis-trade book, no freight or NOPA ingest |
| C04-61 / C04-62 / C04-63 | Goldman roll: days 5–9 / month before expiry; ~20%/day OI front→next-out; smaller in soy than crude but tradeable | not represented | missing | major | `audit_A_cartography.md §9`; `config/commodities.yaml:11` has `cme_roll_rule: "20th_of_month"` (WTI contract-roll, not GSCI) | No OI ingest, no GSCI-roll consumer |
| C04-66 / C04-67 / C04-68 / C04-69 / C04-92 / C04-93 | COT/positioning cluster: MM net-long contrarian; MM-flip+momentum; >200k MM longs preceded 2021/25 tops; commercials-length informative; COT inflection entry; Kelly-scaled sizing | not represented | missing | minor | `audit_A_cartography.md §9` | No COT ingest, no Kelly logic |
| C04-73 / C04-74 / C04-75 | Soy seasonals (Feb break, summer rally, Oct-Nov harvest low); vol higher into July 4 + March Plantings; seasonal composites = vol regimes | not represented | missing | major (C04-74) / minor | `audit_A_cartography.md §9` | No seasonal / event-vol composite |
| C04-77 / C04-78 / C04-79 / C04-80 / C04-81 | Per-strategy entry/sizing/invalidation cluster: board-crush 50¢+ cheap, $/bp sizing, 20-day-MA invalidation; calendar entry/sizing; oilshare vs RFS/RIN | not represented | missing | major (C04-77) / minor | `audit_A_cartography.md §9` | No spread-fair-value model, no MA state, no RIN ingest |
| C04-82 / C04-83 / C04-84 / C04-85 | WASDE fade entry (post-release >1.5σ + 15-min stall) + sizing 25-50bp NAV; Crop-Progress/weather entry (6-10d ridge + deteriorating conditions) + sizing | not represented | missing | major (C04-82/83) / minor | `audit_A_cartography.md §9` | No release-window detector, no σ overlay, no NAV, no NWP / NASS reader |
| C04-94 | Rumor/headline entry: tape moves >2σ in <15 min | not represented | missing | major | `audit_A_cartography.md §9`; `engine/pricer.py:45-90` reprices on every tick with no fast-event branch | No tape-event detector |
| C04-95 / C04-96 / C04-97 / C04-98 / C04-99 / C04-100 / C04-101 / C04-102 / C04-103 / C04-104 / C04-105 / C04-106 / C04-107 | Sizing/risk cluster: rumor-headline initial + add; seasonal composite-aligned; Brandt 0.5-1% per trade + 30% win rate + 3:1 winners; Turtle 1-unit ATR + pyramiding caps; Parker ATR-floor + 25% commodity slice; Raschke risk-to-stop, Holy Grail (ADX + 20-EMA), Anti (flag + MACD); Bielfeldt single-complex; Klipp one-tick exit | not represented | missing | major (C04-97/99) / minor / nice-to-have | `audit_A_cartography.md §9`; cartography red flag #9 (TickRing history unread) | No ATR / ADX / EMA / MACD / position / portfolio / risk-budget state |
| C04-108 / C04-109 / C04-110 / C04-111 / C04-112 / C04-113 / C04-114 / C04-117 | Case-study cluster: 2012 drought + fade failures; 2018 tariff gap + OptionSellers blowup; 2022 oilshare regime break | not represented | missing | nice-to-have | `audit_A_cartography.md §9` | Historical lessons; no in-code reference |
| C05-01 / C05-02 / C05-03 / C05-05 / C05-06 / C05-08 | Trend-family cluster: MA crossover; Donchian N=20/55; TSMOM w_t = c·sign(r12)/σ; inverse-vol parity / vol target; vol-target neutral on L/S commodities; AHL ag-allocation 15-25%, soy 3-6% | not represented | missing | major (C05-01/02/03/05) / minor / nice-to-have | `audit_A_cartography.md §9`; `state/tick_store.py:57-66` `latest()`-only | TickRing keeps history but no MA / Donchian / 12-mo return reader |
| C05-14 / C05-17 / C05-18 | Carry / term-structure cluster: Erb-Harvey 10-12% gross top-vs-bottom; soy second-vs-front cleaner; Fuertes-Miffre-Rallis combined momentum × term-structure 21% pre-cost | not represented | missing | major | `audit_A_cartography.md §9` | No carry signal, no multi-commodity sort |
| C05-20 / C05-21 / C05-22 / C05-23 / C05-25 | Seasonal cluster: de-meaned daily log return composite; Moore 80%+ filter; ZS Oct low / June peak; Farmdoc 3-of-15 counter; momentum filter halves drawdown | not represented | missing | minor | `audit_A_cartography.md §9` | No calendar-day aggregation, no Moore composite, no momentum overlay |
| C05-26 / C05-29 / C05-30 / C05-31 | Cross-sectional cluster: rank N futures by past J-mo; ≥15-commodity monthly rebalance; Bakshi-Gao-Rossi 3-factor; Boons-Prado basis-momentum | not represented | missing | major | `audit_A_cartography.md §9`; `config/commodities.yaml` 1 live + 13 stubs | Universe shape wrong, not just formulas missing |
| C05-38 / C05-41 | Rechner-Poitras filtered crush MR; bean/corn acreage signal as MR overlay | not represented | missing | minor | `audit_A_cartography.md §9` | Duplicates of C04-09 / C04-19 |
| C05-45 / C05-46 / C05-56 | WASDE pipeline cluster: nowcaster targets USDA's number; crushes IV ~70% (capture when consensus aligns); NLP parse PDF/XLSX, deltas vs survey, sensitivity coeffs | not represented | missing | major | `audit_A_cartography.md §9`; `state/iv_surface.py:21-48` (scalar σ) | No PDF parser / NLP / event-vol model |
| C05-58 / C05-59 / C05-61 | ML baseline cluster: XGBoost/LightGBM/CatBoost on fundamentals beat linear by 2-5pp R²; 100+ inputs vs ~480 rows is overparameterized | not represented | missing | minor | `audit_A_cartography.md §9` | No ML model |
| C05-72 / C05-73 / C05-74 | Capacity & turnover cluster: <5% ADV ok, >20% edge-eaten; combined-mom+TS ~0.7%/yr drag; trend 2-5x, x-sec higher, stat-arb 50-100x | not represented | missing | minor | `audit_A_cartography.md §9` | No execution / turnover model |
| C10-03 | Translation test: every Phase 4/5 edge expresses as RND perturbation | not represented | missing | blocker | `audit_A_cartography.md §9`; `models/gbm.py:26-42` `Φ(d2)` with no perturbation hook | Engine emits probability vector, nothing overlays it |
| C10-04 / C10-05 | Trend = small mean-shift on near-symmetric density; MM via A-S / Cartea-Jaimungal-Penalva on bucket grid | not represented | missing | major (C10-04) / blocker (C10-05) | `audit_A_cartography.md §9`; `engine/pricer.py:72` (drift = `BasisModel` only) | No drift overlay; no quoting layer |
| C10-08 / C10-09 | Weather→density: deteriorating GEFS shifts mean up + skews upper tail; wet shift compresses upper / fattens lower interior | not represented | missing | major | `audit_A_cartography.md §9` | No GEFS ingest |
| C10-13 / C10-14 / C10-18 / C10-19 | WASDE vol regime: reduces IV ~70%; U-shape pre/on/post; post-release variance contracts back to mean; width edge cleaner than directional | not represented | missing | major | `audit_A_cartography.md §9`; `state/iv_surface.py:21-48` | Single σ scalar; no event-conditioned vol path |
| C10-16 / C10-17 | Pre-WASDE: widen SVI / scale Bates jump variance. On release: pull 30-60s before, refit, repost | not represented | missing | blocker | `audit_A_cartography.md §9`; `engine/scheduler.py:21-26` declares `EVENT_CAL` enum, no producer | No SVI / Bates path; no quote-pull |
| C10-20 / C10-21 / C10-22 / C10-23 | Directional seasonality fragile; vol seasonality (U.S. ridge + SAm Jan-Feb) durable; vol-elevated → wider density; fixed bucket widths over-/under-quote tails | not represented | missing | major | `audit_A_cartography.md §9` | No regime-conditional density / bucket-width concept |
| C10-24 / C10-25 / C10-34 / C10-42 | Self-disclaimed non-translation set (crush/oilshare/bean-corn; calendar spreads; carry; cross-sectional momentum) — only mean-shift effect ever tradable | not represented | divergent-intentional | nice-to-have | `audit_A_cartography.md §9` | Research itself flags these as unrepresentable on a single-week single-underlier grid |
| C10-26 / C10-27 / C10-28 | Cash basis / farmer-hedge as slow fair-value; COT informs next-week prior; rumor/headline subsumed by OFI | not represented | missing | minor (C10-26/27), major (C10-28) | `audit_A_cartography.md §9` | No fair-value overlay, no prior store, no OFI |
| C10-32 / C10-37 / C10-38 / C10-40 / C10-41 | Mean-shift signals on RND: CME-OFI lead-lag (arb not alpha); Goldman roll inside Kalshi week; parsed WASDE delta; Crop Progress / ESR; first-correct refit wins | not represented | missing | major | `audit_A_cartography.md §9` | No OFI, no roll detector, no WASDE parser, no release-aware refit |
| C10-43 / C10-44 / C10-45 / C10-46 | TSMOM ZS Sharpe 0.2-0.5 as small mean-shift; trend as slow-prior; crush stat-arb as fair-value overlay; stocks-to-use as regime classifier | not represented | missing | minor / major | `audit_A_cartography.md §9` | No TSMOM, no fair-value overlay, no stocks/use ingest |
| C10-54 | Cross-inventory bucket-skew is the MM-specific edge | not represented | missing | blocker | `audit_A_cartography.md §9`; `engine/pricer.py:36-43` is stateless on inventory | No inventory state |
| C10-67 / C10-73 / C10-58 | Hedge default = delta + event-driven option overlay; pull/widen when CBOT closed; rebate-capture unavailable without MM Agreement | not represented | missing | major / minor | `audit_A_cartography.md §9`; `engine/pricer.py:61-65` raises on stale but does not widen | No hedge engine, no off-hours regime, no quoter |
| C10-77 | Milestone 0: SVI / Figlewski RND vs settled outcomes | not represented | missing | blocker | `audit_A_cartography.md §9`; `calibration/` empty per cartography §9 | No M0 deliverable |
| C10-78 | Milestone 1: paper-trading pricing engine pipeline | partial | partial | major | `engine/pricer.py:45-90` + `validation/sanity.py:38-68` cover ~5 of 10 stages | M1 wants surface ingest → smoothing → RND extraction → bucket integration → measure overlay → reservation price → AS skew → spread sizing → hedge sizer → risk gating; engine implements ingest → vol → drift → density only |
| C10-79 / C10-80 / C10-81 | Milestones M2 (passive two-sided quoter w/ amend-not-cancel) / M3 (CME hedge loop via FCM API) / M4 (scenario caps, Grafana, Premier tier, MM Program) | not represented | missing | blocker | `audit_A_cartography.md §9` | No quoter, no FCM client, no observability layer |
| C01-11 / C01-42 / C01-44 / C01-45 | November/July contract-month bellwether; reverse crush + oilshare spec expressions; bean/corn ratio definition + thresholds | not represented | missing | minor | `audit_A_cartography.md §9`; `config/commodities.yaml:54-60` (`soy`/`corn` stub) | No contract-month or cross-symbol state (duplicates of C04-03/18/19) |
| C01-52 / C01-53 / C01-54 / C01-59 / C01-60 | Vol window (Jun-mid-Aug, July-4 peak); seasonal basis (Oct-Nov widen, spring narrow); meal/oil basis | not represented | missing | minor | `audit_A_cartography.md §9` | No IV term structure / seasonal vol / basis-seasonality |
| C01-66 / C01-67 / C01-75 / C01-84 / C01-85 / C01-86 | Goldman roll; options MM short-gamma into USDA; reverse-crush squeeze on bean surprise; options-liquidity concentration; common option structures; skew flip pre/post-harvest | not represented | missing | minor | `audit_A_cartography.md §9` | No options book / spread tape |
| C02-31 / C02-32 | Cartea-Jaimungal-Ricci & Cartea-Wang: alpha-proportional / asymmetric optimal quote | not represented | missing | major | `audit_A_cartography.md §9` | No quoting layer |
| C02-57 | Forward-curve shape signals carry direction | not represented | missing | minor | `state/basis.py:19-48` carries one annualized scalar, not a curve | See ambiguity §4 |
| C02-58 / C02-59 / C02-62 | Goldman roll mechanics + calendar-spread front-running + lower AS for index flow | not represented | missing | minor | `audit_A_cartography.md §9` | Duplicates of C04-61/62 |
| C02-65 / C02-81 | Regime-switch κ_t spread widener around scheduled events | not represented | missing | major | `audit_A_cartography.md §9` | No κ_t state, no spread; see narrative §3(a) |
| C02-72 / C02-73 / C02-78 / C02-83 | MMs widen/withdraw overnight; GLFT off-hours is warning not policy; short-horizon OFI + dozens of drift alphas | not represented | missing | major | `audit_A_cartography.md §9`; `engine/pricer.py:72` drift = `basis_drift` only | No quoting, no alpha aggregator |
| C02-89 | Pricing models do not specify capital deployment | research disclaims, code conforms | already-good | nice-to-have | `engine/pricer.py:45-90` returns a theo only | Scope match |
| C02-91 | Pricing models do not say when to stop quoting | engine raises on stale / low-publisher | already-good | minor | `engine/pricer.py:61-69` raises `StaleDataError` / `InsufficientPublishersError` | Most-restrictive upstream choice; see ambiguity §4 |
| C03-10 / C03-36 / C03-62 / C03-64 | External benchmarks/priors: Bloomberg Ag Subindex; Descartes Labs yield; StoneX bean-yield; Pro Farmer Aug crop tour | not represented | missing | nice-to-have | `audit_A_cartography.md §9` | No external benchmark / yield-forecast ingest |
| C06-04 / C06-27 | CBOT FIFO + implied spreads need order-ID for queue position; MM book widens/pulls 30s window around release | not represented | missing | major | `audit_A_cartography.md §9` | No order-book reader; same as C02-65/C10-17 |
| C06-16 / C06-17 / C06-20 / C06-21 / C06-22 / C06-23 / C06-40 | USDA + NOAA event-clock cluster: Crop Progress Mon 4pm, ESR Thu 8:30, FGIS, Plantings, Acreage, Grain Stocks, NOAA CPC 6-10/8-14d daily | not represented | missing | major | `audit_A_cartography.md §9`; only event in YAML is `EIA_crude` (`config/commodities.yaml:24-28`) | No USDA / NOAA event clock |
| C06-29 / C06-30 / C06-31 / C06-32 / C06-33 / C06-34 / C06-37 / C06-39 | International ingest cluster: SECEX/IMEA/Deral/Abiove/BCBA/BCR + SAm beats US Nov-Jun + GACC China + Sinograin + AIS residual | not represented | missing | minor | `audit_A_cartography.md §9` | No SAm/China/AIS layer |
| C06-69 / C06-72 / C06-74 | COT unusual-weeks; GSCI/BCOM weights; DXY cross-asset coefficient | not represented | missing | minor | `audit_A_cartography.md §9` | No COT, no index, no macro overlay |
| C06-84 | Microstructure: only category where latency is the value | engine asserts ≤2000 ms staleness | partial | minor | `engine/pricer.py:61-65`; `config/commodities.yaml:9` | Tick-level OK; no quote consumer |
| C06-87 / C06-91 / C06-92 / C06-93 | Weather rate-of-change → vol widen; logistics slow input; alt-data normal-vs-stress weighting | not represented | missing | minor | `audit_A_cartography.md §9` | No upstream feeds |
| C06-88 | Minimum complete pipeline (MDP-3.0 + USDA PDF + SECEX + NWP + Baltic + AIS + COT + cash-bid) | not represented | missing | blocker | `audit_A_cartography.md §9` | Repo has Pyth Hermes only |
| C08-42 / C08-43 / C08-107 | Avellaneda-Stoikov optimal half-spread + GLFT spread sizing floored at fees+edge; k_i calibrated from Kalshi fills | not represented | missing | blocker | `audit_A_cartography.md §9`; `calibration/` empty per cartography §9 | No spread, no fills, no calibrator |
| C08-51 / C08-54 / C08-56 | Cont-de Larrard / HLR queue-reactive transfer; Glosten-Milgrom fails at edges; edge-proximity widener | not represented | missing | major | `audit_A_cartography.md §9` | No queue / bucket model |
| C08-65 / C08-66 | Sharp quants hit RND-Yes divergence > fees; fundamentals dominate AS on report days | not represented | missing | major | `audit_A_cartography.md §9` | No RND-vs-Yes comparator |
| C08-79 / C08-80 / C08-93 | Hedge γ/v with options on large bucket; small books delta-hedge; quoting w/o round-trip cost over-quotes | not represented | missing | major | `audit_A_cartography.md §9` | No hedge engine, no fee/cost concept |
| C08-97 / C08-98 / C08-99 / C08-106 | Deterministic event calendar (κ^spread, κ^width); 30-60s pull/refit/repost; weather → slow measure overlay; AS-skew via OFI | not represented | missing | major | `audit_A_cartography.md §9`; `config/commodities.yaml:24-28` declares `vol_adjustment` field but no consumer | Dead config; no measure overlay |
| C09-20 / C09-21 / C09-49 / C09-52 | 15-bucket 1Hz saturates Advanced tier; amend-first / cancel only when pulling; ERA5 reanalysis bias-correction; COT lands after Event → next-week prior | not represented | missing | minor | `audit_A_cartography.md §9` | No quoter, no order client, no reanalysis or COT |
| C09-39 / C09-40 / C09-41 / C09-42 | Weekly fundamentals + WASDE 2nd-Tue + Grain Stocks/Plantings/Acreage + SAm BCBA/BCR/CONAB (in-window quote-pull) | not represented | missing | major | `audit_A_cartography.md §9` | Duplicates of C06-16/17/20/21/22/23 |
| C09-59 | At 40–60 ms tick-to-quote Rule 5.9 FIFO won by price | tick → theo budget exists | partial | minor | `engine/pricer.py:45-90`; `benchmarks/run.py:82-179` | "Won by price" half unrepresented (no quote) |

## 3. Narrative discussion of blockers and majors

The codebase is not a strategy or market-making engine; it is a per-tick
repricer for one symbol (`wti`), and every strategy-tagged claim that
requires behavior beyond "given σ, basis, and τ, return P(S_T > K) for
a strike grid" is unrepresented. The cartography
(`audit/audit_A_cartography.md §9`) inventories every Python module and
none has a strategy-shaped responsibility line; red-flag #2 states
"the whole Kalshi-facing side of the system is absent." Every Phase 10
claim — framed in terms of quoting a Kalshi bucket grid — therefore
lands `missing` at the file level even when the mechanic could in
principle bolt onto the existing `models/gbm.py` output.

The `blocker`-class gaps are structural. C10-03's "translation test" —
every Phase 4 / 5 edge has to map to a density perturbation — has no
host: `models/gbm.py:26-42` returns `Φ(d2)` with no measure-overlay
hook. C10-05 (A-S / Cartea-Jaimungal-Penalva on the bucket grid) and
C10-79–C10-81 (M2/M3/M4: passive quoter, FCM hedge loop, observability
stack) have no quoting layer at all. C08-42 and C08-107 (A-S optimal
half-spread; GLFT spread sizing floored at fees + edge) require a bid
and ask that do not exist. C10-54 (Cartea-Jaimungal cross-inventory
bucket-skew — the Phase 10 thesis on what makes the MM edge MM-specific)
requires inventory state: `engine/pricer.py:36-43` keeps no position
dataclass; `Pricer` is stateless. C10-77 (M0: SVI / Figlewski RND vs
settled outcomes) has no historical chain ingest, no SVI fitter, no
Figlewski tail extrapolation, and no calibration pipeline (cartography
§9 confirms `calibration/` contains only `__init__.py` and `.gitkeep`).
C06-88 (minimum complete data pipeline = MDP-3.0 + USDA PDF + SECEX +
NWP + Baltic + AIS + COT + cash-bid) is replaced by Pyth Hermes for one
price stream; every other ingest is missing.

The `major`-class set clusters around three families.

(a) Event-aware vol regime. C04-31 (48h flatten-or-fade), C04-35 /
C05-46 / C10-13 (WASDE crushes IV ~70%), C04-74 / C10-21 (seasonal vol
into July 4 and SAm January), C10-14 (WASDE U-shape), C10-16 / C10-22 /
C10-23 (widen density into events / seasonal vol), C02-65 / C02-81 (κ_t
regime-switch around scheduled events), C06-27 (30 s widen window),
C08-97 (event calendar with per-event (κ^spread, κ^width)), C08-98 /
C10-17 (pull 30–60 s before, refit, repost) all describe the same shape:
event clock + multiplicative variance widener + "pull quotes" line. The
codebase has one skeleton: `engine/scheduler.py:21-26` declares
`Priority.EVENT_CAL = 30` but red flag #5 confirms no producer submits.
`config/commodities.yaml:24-28` declares one event for WTI (`EIA_crude`
Wed 10:30 ET with `vol_adjustment: "strip_event_vol_if_after"`) but no
Python file consumes the block — dead config. `state/iv_surface.py:21-48`
is a per-commodity scalar `(sigma, ts_ns)`; no term structure, no
event-conditioned σ, no κ_t. Every event-overlay claim lands `missing` /
`major` because (i) the research is unanimous on these being first
order, and (ii) the partial scaffolding (the `EVENT_CAL` enum, the YAML
block) is the wrong kind of partial — intent without behavior.

(b) Cross-symbol and cross-sectional signals. C04-11/12/13 (July/Nov
old-vs-new-crop), C04-18/19 (bean/corn ratio), C04-61/62/C02-58 (Goldman
roll), C05-01 (MA crossover), C05-02 (Donchian), C05-03 (TSMOM), C05-14
(Erb-Harvey carry quintile), C05-18 (Fuertes-Miffre-Rallis), C05-26/29
(cross-sectional momentum with ≥15-commodity universe), C05-30
(Bakshi-Gao-Rossi 3-factor), C05-31 (Boons-Prado basis-momentum) all
assume a multi-symbol universe and multiple deferred contracts. The repo
has one live commodity (`config/commodities.yaml:6-30`, `wti`) and 13
stubs that — per red flag #14 — would raise `NotImplementedError` the
moment the pricer asked for their τ. There is no deferred-contract
concept: `TickStore` keys by commodity string only
(`state/tick_store.py:31-66`); `TheoInputs` carries `spot` as a single
scalar (`models/base.py:32-41`). The cluster is uniformly `missing`
and `major` because the universe shape is wrong, not because the
formulas are missing.

(c) Inventory and adverse selection. C02-31/32 (Cartea-Jaimungal-Ricci /
Cartea-Wang alpha-proportional quotes), C02-78/83 (dozens of drift
alphas), C08-43 (k_i from Kalshi fills), C08-51 (Cont–de Larrard /
Huang-Lehalle-Rosenbaum queue-reactive), C08-65/66 (sharp-quant /
fundamental AS), C08-80 (small books delta-hedge, carry γ/vega), C08-93
(round-trip cost), C08-106 (AS skew via OFI), C10-67 (delta-hedge +
event option overlay) all assume the operator owns inventory, has fills,
and runs an order book. The codebase has none of those: `Pricer` is
stateless on inventory; no order client, no fill tape, no markout, no
hedge submitter. Red-flag #2 makes this a structural gap, not a
missing-formula gap.

`partial` and `already-good` calls. C10-78 (M1 paper-trading pipeline)
is `partial`: research demands ten stages (surface ingest → smoothing →
RND extraction → bucket integration → measure overlay → reservation
price → AS skew → spread sizing → hedge sizer → risk gating);
`engine/pricer.py:45-90` plus `validation/sanity.py:38-68` cover only
the first ~5. Everything downstream of the raw probability vector is
absent. C02-89 / C02-91 ("pricing models do not specify capital
deployment / when to stop quoting") are `already-good`: engine scope is
narrow at "produce a theo or raise"; the staleness and publisher-floor
gates at `engine/pricer.py:61-69` are the closest analogue to a
"stop quoting on circuit-breaker" rule. C06-84 and C09-59 are `partial`:
the tick-to-theo latency budget is honored
(`engine/pricer.py:61-65` enforces `pyth_max_staleness_ms`) and the
benchmark harness measures it, but no quoter consumes the budget. The
single `divergent-intentional` cluster (C10-24 / C10-25 / C10-34 /
C10-42) is the set of edges Phase 10 itself flags as unrepresentable on
a single-week single-underlier grid; the codebase's silence on them is
consistent with the research's own scope acknowledgment.

## 4. Ambiguities

The `event_calendar` YAML block (`config/commodities.yaml:24-30`) and
the `Priority.EVENT_CAL = 30` enum (`engine/scheduler.py:21-26`) could
each be read as `partial` (data structure exists, consumer missing) or
`missing` (no behavior). Classified `missing` because every audit row
asks about behavior, and red flag #5 plus the absence of any YAML
parser argue against `partial`.

The codebase prices WTI; the research targets soybeans / `KXSOYBEANW`.
The audit classified per-mechanism (crush missing because no spread
book exists), not per-symbol (soy missing because no soy is wired). A
reader who prefers per-symbol slicing should treat every Phase 4/5/10
claim as additionally missing because soy is a stub
(`config/commodities.yaml:58-60`).

C04-94 and C04-82 (tape moves >2σ in <15 min triggers) want a
window-conditioned event detector. The repo has a per-tick reprice loop
(`engine/pricer.py:45-90`) but no rolling window. Classified `missing`
because the per-tick path is the wrong primitive; a reader who treats
the per-tick reprice as the substrate on which a window classifier
would later run may prefer `partial`.

C02-57 (forward-curve shape) is `missing` even though
`state/basis.py:19-48` carries a per-commodity scalar; the scalar is
not a curve. C02-91 ("when to stop quoting") classified `already-good`
is the most generous call: `engine/pricer.py:61-69` raises rather than
publishing a wrong theo, but with no quoter "stop quoting" is not a
behavior the engine could exhibit even in principle. A strict reader
will re-class C02-91 to `missing` and C02-57 to `partial`.

## 5. Open questions for maintainers

1. Is the `engine/scheduler.py` `EVENT_CAL` priority slot intended as a
   forward-looking placeholder for WASDE / EIA / Crop-Progress
   release-window logic (C04-31, C04-82, C06-27, C08-97, C10-17,
   C10-41), or only for the existing `event_calendar` YAML block? If
   the former, what is the planned producer module (none exists today
   per red flag #5)?

2. `config/commodities.yaml:24-30` lists
   `vol_adjustment: "strip_event_vol_if_after"` for WTI EIA. No code
   parses this string. Is it intended to feed a future κ_t multiplier
   (C02-65, C08-97) on `IVSurface`? What is the planned coupling
   between the event calendar and `IVSurface.atm()`?

3. The research targets `KXSOYBEANW` and soybeans; the code is WTI-only
   with zero Kalshi wiring (red flag #2). Is the WTI focus intentional
   early-deliverable scoping, or a divergence from the synthesis target?

4. `models/registry.py:32-38` has commented-out slots for
   `jump_diffusion`, `regime_switch`, `point_mass`, `student_t`.
   Synthesis claims C10-16 (Bates-style jump variance) and C10-46
   (tight-stocks density widening) need them. Which is meant to host
   the measure overlay (C10-12), on what schedule?

5. `validation/sanity.py:32-68` enforces [0,1] and monotone-decreasing
   but not "bucket-sum consistent" (C10-OQ-07). Is the bucket-sum
   invariant intentionally deferred to a Kalshi-integration layer, or a
   gap the sanity layer should close?

6. Red flag #8: `feeds/pyth_ws.py:112-115` defaults `num_publishers = 0`
   when Hermes omits the field, and `engine/pricer.py:66-69` rejects
   any tick below the floor (5 for WTI). In production this would
   suppress every theo for messages that intermittently lack publisher
   count. Is rejection-on-zero the intended hard SLA gate, or is the
   `0` fallback meant to be replaced with carry-forward before live?
   This bears on every event-window claim that needs continuous theo
   through a release minute.

7. Is the plan to extend `benchmarks/harness.py` and
   `benchmarks/run.py` to measure end-to-end
   tick → theo → would-quote → would-fill (the M0/M1 deliverables in
   C10-77/C10-78), or to stand up a separate strategy evaluation
   pipeline?

8. Several practitioner-lore claims (C04-69, C04-104, C04-106, C04-107)
   are incompatible as global rules. Is the corpus a buffet (pick
   edges that translate to RND perturbation per C10-03) or a complete
   recipe? The audit assumed the buffet reading.

9. The C10-78 measure-overlay stage + favorite-longshot bias
   (C10-06/07, C10-OQ-02) suggest a one-parameter shrinkage. Is the
   planned overlay a single shrinkage, a per-bucket correction, or
   something else? `models/gbm.py:69-105` has no extension point for
   any of those.

10. `state/basis.py:19-48` is a per-commodity scalar. Claims C02-57,
    C04-13, C05-12, C05-19, C10-35, C10-36 all want a curve. Is the
    upgrade path to extend `BasisModel` or to introduce a separate
    `ForwardCurve` state class?

## 6. Source citations

Research citations (Phase C distillations; each C-id points at the
original `research/` artifact via the Phase C citation column):
(1) C04-31 — WASDE flatten-or-fade; (2) C04-35 — WASDE crushes IV ~70%;
(3) C04-61 — Goldman roll days 5–9; (4) C04-82 — WASDE fade
post-release >1.5σ stall; (5) C04-99 — Turtle 1-unit ATR sizing;
(6) C05-01 — MA crossover; (7) C05-03 — TSMOM w_t = c·sign(r12)/σ;
(8) C05-26 — cross-sectional momentum; (9) C05-46 — WASDE IV crush (CME);
(10) C05-56 — WASDE NLP pipeline; (11) C10-03 — translation test;
(12) C10-05 — Avellaneda-Stoikov / Cartea-Jaimungal-Penalva on bucket grid;
(13) C10-13 — WASDE reduces IV ~70%; (14) C10-17 — pull 30–60s before
WASDE, refit, repost; (15) C10-77/78/79/80/81 — milestone roadmap
M0–M4; (16) C02-65 — regime-switch κ_t overlay; (17) C02-83 — dozens
of alpha signals in drift; (18) C06-88 — minimum complete pipeline;
(19) C08-42 + C08-107 — A-S half-spread + GLFT sizing; (20) C09-39/40 —
weekly fundamentals + WASDE in-window pull. Source files (all in
`audit/`): `audit_C_phase04_discretionary.md`,
`audit_C_phase05_systematic.md`, `audit_C_phase10_strategy_synthesis.md`,
`audit_C_phase02_pricing_models.md`, `audit_C_phase06_data_streams.md`,
`audit_C_phase08_synthesis_pricing.md`, `audit_C_phase09_kalshi_stack.md`.

Code anchors: `audit_A_cartography.md §9` (module inventory, absence
reference for every `missing` row) and §10 red flags #2/#5/#9/#14;
`engine/pricer.py:45-90` and `:61-69`; `engine/scheduler.py:21-26`;
`engine/event_calendar.py:69-110`; `models/gbm.py:26-42`;
`models/registry.py:32-38`; `models/base.py:32-41`;
`state/iv_surface.py:21-48`; `state/basis.py:19-48`;
`state/tick_store.py:31-66`; `validation/sanity.py:32-68`;
`config/commodities.yaml:6-30` (WTI; dead `event_calendar` /
`vol_adjustment` / `jump` fields); `:34-85` (13 stubs).
