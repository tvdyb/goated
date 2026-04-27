# Audit E — Gap Register (Phase E synthesis)

## 1. Framing

This file is the merge of the ten Phase D topic audits
(`audit/audit_D_pricing_model.md`, `audit_D_density.md`,
`audit_D_data_ingest.md`, `audit_D_contract.md`, `audit_D_hedging.md`,
`audit_D_inventory.md`, `audit_D_oms.md`, `audit_D_backtest.md`,
`audit_D_strategy.md`, `audit_D_observability.md`) into a single
deduplicated register. Every Phase D row that was tagged anything
other than `already-good` is carried forward; `already-good` rows
were dropped per the brief. No re-auditing is performed here — when a
D-file is silent on something, it is silent here too. No prioritisation
is done here either; sequencing is Phase F's job.

### How to read the register

The register is split into two tables keyed by GAP-id. The **primary
table** (§2.1) carries the one-sentence summary, the primary topic, the
severity, the effort tier, and the gap class — the columns most useful
to a triage reader. The **detail table** (§2.2) carries everything else:
all topic tags (primary first, then any topics from which the row was
deduplicated), the C-id citations, the code-location citations, the
blast radius (modules touched if remediated), a one-phrase justification
for the effort tier, and any row-specific notes carried forward from D.
Both tables are GAP-id-keyed so a reader can join them by row.

GAP-ids are sequential within this file (`GAP-001` through `GAP-185`)
and are assigned in topic order. The topic order matches the audit
prompt: pricing-model → density → data-ingest → contract → hedging →
inventory → oms → backtest → strategy → observability. Within each
topic block the rows are ordered by severity (blocker → major → minor →
nice-to-have), then by deduplication weight (rows that absorbed more
D-rows ahead of singletons), then by C-id for stability.

When a deduplicated gap straddles topics, the row sits under the topic
where its severity was highest in D (with ties broken by where the
deepest code citation lives). That topic is the *primary* topic; the
others appear in the topic-tag column.

### Severity scale (carried forward from D)

The four-level scale and its meaning are as set in the D-files:

- **blocker** — the absence of capability without which the *system
  mission* (quoting a Kalshi `KXSOYBEANW` market) cannot operate at
  all. Also used for items that, if missed, cause irreversible asset
  loss (e.g., forward-only Kalshi tape).
- **major** — divergences that would distort prices, fills, P&L, or
  risk control once the blocker chain is closed. These are the things
  that make a working system *wrong*, as distinct from *absent*.
- **minor** — hygiene, provenance, schema gaps, diagnostic-only
  signals; visible in audits but not load-bearing on day-one.
- **nice-to-have** — enhancement-only or research-only items that the
  D-files explicitly flagged as low-priority.

Where two D-files disagreed on severity for what dedup determined is
the same gap, the **worst** severity is taken. Where two D-files
disagreed on gap class, the **more-accurate-of-present** is taken in
the order of preference `partial > wrong > missing > divergent-
intentional`. The justification: a `partial` reading is empirically
strongest evidence (something is in code), `wrong` is the second-most
specific (something is in code and contradicts the spec), `missing`
is the weakest concrete claim, and `divergent-intentional` is a scope
acknowledgement that should not override evidence of partial code.

### Effort tiers (anchors)

The brief defines four tiers; this file uses them literally:

- **S** — ≤ 1 engineer-day, ≲ 100 LoC of new code. Typical: a
  one-formula closed-form addition to a kernel that already exists, a
  single config-key reader, a YAML schema extension that propagates to
  one consumer.
- **M** — 1–3 engineer-days, ~100–500 LoC. Typical: a small new module
  alongside existing infrastructure, a new dataclass plus its
  consumers, a non-trivial gate inside an existing validator.
- **L** — 1–2 engineer-weeks, ~500–2,000 LoC, or a new module. Typical:
  a new state surface (e.g., `state/positions.py`), a new ingest
  producer of moderate complexity, a calibration job with one external
  data source.
- **XL** — > 2 engineer-weeks, multi-module, or a new external
  integration. Typical: the whole Kalshi REST/WS client (signing, rate
  limiting, order builder, fill ingest), the FCM/CME hedge connector,
  the SVI/Figlewski RND extraction pipeline.

Each row carries a one-phrase justification of the chosen tier. Where
remediation is genuinely greenfield (no module exists), the tier
reflects the *minimal* viable implementation, not a full Phase C
build-out.

### Deduplication rule used

The brief gave two paths to deduplication: (a) overlapping Phase C
ids combined with compatible gap classes, or (b) the same code
location (`path:lo-hi` or "no module") with the same gap class.
Both paths were applied. Most cross-topic merges came from path (a):
the same C-id (e.g., C09-73 kill-switch, C08-89 scenario tests, C08-97
event-calendar κ multipliers, C08-100 stage A surface ingest) appears
in multiple D-files and resolves to one underlying gap with a single
remediation. Path (b) merges showed up when several D-files cited the
same "no module exists" cartography pointer (`audit_A_cartography.md:
213-231`) for closely-adjacent mechanics — for example the hedging
audit and the inventory audit both pointed there for the absence of a
position store, and the contract audit and the OMS audit both pointed
there for the absence of a Kalshi REST client.

The dedup is conservative: when a row could plausibly stand alone
(e.g., the digital-delta closed-form `φ(d₂)/(Sσ√τ)` from the hedging
audit is *adjacent* to but not the same gap as the GBM-only modelling
choice from the pricing audit), it was kept separate. The merged-row
count by topic appears in the §4.1 summary table.

### What is *not* in the register

Three categories of D-row were intentionally excluded.

First, `already-good` rows: per the brief, they are not gaps. Phase D
emitted only six (C08-07, C08-09, C08-57, C08-58, C09-54, C02-88,
C02-89, C02-91 across all topics) and the count is reported in §4 for
completeness only.

Second, items the C10 distillation flagged as research open questions
(`C10-OQ-NN`) or kill criteria (`C10-KC-NN`). These are not audit gaps
— they are open-empirical questions whose resolution is a
research-desk activity, not an engineering one. They are reproduced
verbatim in **Appendix A**.

Third, the "open questions for maintainers" sections at the end of
each Phase D file. These are clarifying questions whose answers will
re-shape the gap register itself (e.g., "is the Kalshi side
deferred?", "is `params_version` a Heston/Bates switch?"). They are
also Phase F input but are not gaps in the audit-evidence sense, and
they are gathered verbatim in **Appendix B**, grouped by D-topic with
source-file pointers.

### Cartography pointer convention

For `missing` rows where no module exists yet, the brief asks for
the literal string `n/a — no module` in the code-location column,
with a cartography pointer in the notes. Phase D's most-cited
cartography anchors are `audit_A_cartography.md:213-231` (the module
inventory — the canonical "no module exists" pointer),
`audit_A_cartography.md:243-245` (Red Flag 2: the whole Kalshi side is
absent), `audit_A_cartography.md:108-115` (no CME / options chain /
Kalshi API / macro feed implemented), `audit_A_cartography.md:246-249`
(Red Flag 3: declared-but-unused deps `httpx`, `structlog`,
`python-dateutil`, `pytz`), and `audit_A_cartography.md:254-257`
(Red Flag 5: `engine/scheduler.py` declared but unwired). Where a
detail-table note refers to "cartography" without further qualification
it means the appropriate one of these.

---

## 2. Gap register

### 2.1 Primary table

| GAP-id | Summary | Primary topic | Severity | Effort | Gap class |
|---|---|---|---|---|---|
| GAP-001 | Avellaneda–Stoikov / Cartea–Jaimungal control loop is entirely absent (no γ, no q, no λ(δ), no objective, no HJB). | pricing-model | blocker | XL | missing |
| GAP-002 | Reservation price `r = S − γσ²(T−t)q` is not computed; pricer uses raw Pyth tick as spot. | pricing-model | blocker | M | missing |
| GAP-003 | Optimal half-spreads / quotes (Ho–Stoll, A–S, GLFT) are not produced; `TheoOutput` has no bid/ask field. | pricing-model | blocker | L | missing |
| GAP-004 | Per-bucket A–S reservation price `rᵢ = mᵢ − qᵢγᵢσ²ₘᵢ(T−t)` and matrix-skew `rᵢ = mᵢ − γ(T−t)Σⱼ Σᵢⱼ qⱼ` not implemented. | pricing-model | blocker | XL | missing |
| GAP-005 | Bucket payoff `1{ℓᵢ ≤ S_T < uᵢ}` and bucket-corridor decomposition `D(ℓ) − D(u)` not implemented; pricer emits half-line `P(S_T > K)` only. | pricing-model | blocker | M | missing |
| GAP-006 | Yes-price = Q^K(ℓᵢ ≤ S_T < uᵢ) under the Kalshi measure not produced; the GBM density is model-implied not market-implied (RND). | pricing-model | blocker | XL | wrong |
| GAP-007 | Kalshi taker fee `⌈0.07·P(1−P)·100⌉/100` and 25% maker rate not modelled; no fee floor on spread; round-trip cost ~250 bps unaccounted. | pricing-model | blocker | M | missing |
| GAP-008 | Single-factor GBM with constant scalar σ contradicts the C02-75 minimum bar (GARCH/Heston SV + jumps). | pricing-model | major | XL | wrong |
| GAP-009 | Lognormal tails systematically under-quote grain fat tails (C02-74 leptokurtosis); GBM kernel has no jump or heavy-tail branch. | pricing-model | major | L | wrong |
| GAP-010 | Heston-A–S reservation price `rₜ = Sₜ − qγvₜ(T−t)` (σ² → vₜ) absent; σ is calendar-blind scalar. | pricing-model | major | L | missing |
| GAP-011 | Merton jump-diffusion `dS/S = (μ−λκ)dt + σdW + (J−1)dN` not implemented; `jump_diffusion` registry slot commented out. | pricing-model | major | M | missing |
| GAP-012 | Bates SVJ (Heston + Merton) not implemented; required for smile/term-structure (C02-46, C08-89 weather-shock). | pricing-model | major | L | missing |
| GAP-013 | Glosten–Milgrom Bayes update on order flow not implemented; pricer treats spot as exogenous and never re-marks on hypothetical buy/sell. | pricing-model | major | L | missing |
| GAP-014 | Kyle linear λ / OFI mid-price impact absent; sigma is one ATM scalar with no σᵥ/σᵤ split. | pricing-model | major | L | missing |
| GAP-015 | Cartea–Jaimungal–Ricci alpha-proportional drift overlay missing; `basis_drift` is one carry scalar, not a per-signal alpha aggregator. | pricing-model | major | L | partial |
| GAP-016 | Cartea–Wang asymmetric reservation/spread skew on alpha signal absent. | pricing-model | major | M | missing |
| GAP-017 | Fav/longshot measure overlay (Wolfers–Zitzewitz / Whelan 2025 bias) not implemented; no Kalshi-vs-RN tilt. | pricing-model | major | M | missing |
| GAP-018 | Pre-event SVI widening / Bates jump-variance scaling around USDA windows absent. | pricing-model | major | M | missing |
| GAP-019 | Event-day κ_t spread/width multipliers absent; YAML carries `event_calendar[].vol_adjustment` but no Python reader. | pricing-model | major | M | partial |
| GAP-020 | Bucket-variance σ²ₘᵢ ≈ Δᵢ²·σ²_S derivation absent (no bucket delta surface). | pricing-model | major | M | missing |
| GAP-021 | Multi-asset HJB / cross-bucket Σᵢⱼ via RND perturbation not implemented. | pricing-model | major | XL | missing |
| GAP-022 | GLFT asymptotic ask/bid `δ*(q) ≈ (1/γ)ln(1+γ/k) + …·(2q+1)` absent; no inventory-state-dependent skew. | pricing-model | blocker | L | missing |
| GAP-023 | GLFT hard inventory bound `q ∈ {−Q,…,+Q}` absent (no q, no Q). | pricing-model | blocker | M | missing |
| GAP-024 | Adverse-selection skew via OFI / Cartea–Jaimungal–Ricci absent (no fill stream, no markout). | pricing-model | major | L | missing |
| GAP-025 | PIN / VPIN flow-toxicity diagnostics absent (no trade-side classification). | pricing-model | minor | M | missing |
| GAP-026 | Edge-proximity widener for Kalshi bucket edges (jump-flavour optimal spread) not implemented. | pricing-model | major | M | missing |
| GAP-027 | Mean-reverting reservation-price drift at extreme inventory absent; `basis_drift` is a constant scalar. | pricing-model | major | M | missing |
| GAP-028 | Limit-day censorship correction (CBOT 7% lock → biased σ) absent; lock not detected, σ uncorrected. | pricing-model | major | M | missing |
| GAP-029 | Practitioner stack item 5 (notional/delta/gamma hard limits supersede pricing) — the truncating risk layer absent. | pricing-model | blocker | L | missing |
| GAP-030 | Roberts–Schlenker price-vs-yield elasticity layer absent; no yield→price mapping for stocks-to-use regime classifier. | pricing-model | minor | M | missing |
| GAP-031 | WASDE-delta-to-price sensitivity (~+18¢/bu per −1m bushel ending-stocks) not encoded. | pricing-model | minor | S | missing |
| GAP-032 | Bimodal-RND fingerprint detection (concave IV pre-event) absent; no IV-curvature analysis. | pricing-model | minor | M | missing |
| GAP-033 | Index-roll lower-AS premium for scheduled flow not modelled. | pricing-model | minor | S | missing |
| GAP-034 | Practitioner spread decomposition (holding + order + information cost) not materialized. | pricing-model | minor | S | missing |
| GAP-035 | Grossman–Miller price concession `aσ²ε/(M+1)·i` absent (no order-flow imbalance signal). | pricing-model | minor | M | missing |
| GAP-036 | Breeden–Litzenberger `f_T(K) = e^(rT)·∂²C/∂K²` not implemented; no call surface, no second derivative. | density | blocker | L | missing |
| GAP-037 | Gatheral SVI calibration `w(k) = a + b{ρ(k−m) + √((k−m)² + σ²)}` not implemented; no per-expiry IV fitter. | density | blocker | L | missing |
| GAP-038 | Gatheral–Jacquier butterfly/calendar no-arb constraints not enforced; no SVI consistency gate. | density | major | M | missing |
| GAP-039 | Bliss–Panigirtzoglou vega-weighted cubic-spline fallback absent. | density | major | M | missing |
| GAP-040 | SABR closed-form implied vol not implemented (alternative to SVI). | density | minor | M | missing |
| GAP-041 | Figlewski / Bollinger–Melick–Thomas piecewise-GEV tail attachment not implemented; no paste-point selector. | density | major | L | missing |
| GAP-042 | IV surface stores one (σ, ts_ns) per commodity — no strike axis, no expiry axis; cannot host a smile or a vertical spread. | density | blocker | L | partial |
| GAP-043 | Bucket integration `value_i = ∫_ℓ^u f_T dx` and sum-to-one normalization not implemented. | density | blocker | M | missing |
| GAP-044 | Sum-of-Yes-prices = 1 consistency check (C07-39) absent in `validation/sanity.py`; only per-strike monotone gate exists. | density | major | S | missing |
| GAP-045 | Heston-style variance rescaling / calendar-arb SVI re-fit when CME and Kalshi expiries differ not implemented. | density | blocker | M | missing |
| GAP-046 | CME ZS option-chain ingest (Stage A C08-100) not implemented — required source for any RND. | density | blocker | XL | missing |
| GAP-047 | Put-call-parity arbitrage prune for raw option prices not implemented. | density | major | S | missing |
| GAP-048 | Kalshi vs CME-RN measure overlay (Stage E) not implemented; no parametric shrinkage on the two-measure tilt. | density | major | M | missing |
| GAP-049 | CBOT weekly / SDNC / standard option expiry table absent; no "nearest co-terminal" picker. | density | major | M | missing |
| GAP-050 | Density-perturbation pipeline (Stage C → bucket Σᵢⱼ) absent; required for cross-bucket reservation price. | density | major | L | missing |
| GAP-051 | CME MDP 3.0 (`GLBX.MDP3`) ingest absent; no SBE/FIX decoder, no Databento client. | data-ingest | blocker | XL | missing |
| GAP-052 | MBP / MBO order-book reconstruction absent; tick ring stores aggregate price only (no bid/ask/depth). | data-ingest | major | L | missing |
| GAP-053 | USDA WASDE / Crop Progress / FAS ESR / FGIS / Plantings / Acreage / Grain Stocks event-clock absent for soybean; soy block has no `event_calendar[]`. | data-ingest | blocker | M | missing |
| GAP-054 | NASS Quick Stats / FAS GAIN / FOIA-bulk USDA REST ingest absent. | data-ingest | major | L | missing |
| GAP-055 | NWP ingest (ECMWF IFS / GFS / GEFS / AIFS / HRRR / ENS / ERA5) absent; no GRIB2/`xarray`/`cfgrib`/`herbie` deps. | data-ingest | major | XL | missing |
| GAP-056 | NASA SMAP soil-moisture, Sentinel-2 NDVI, Drought Monitor ingest absent. | data-ingest | nice-to-have | L | missing |
| GAP-057 | SAm fundamentals (CONAB monthly, BCBA Thursday weekly, BCR weekly, Rosario/Paraná cash) ingest absent. | data-ingest | minor | L | missing |
| GAP-058 | GACC monthly Chinese imports / AIS-residual cargo signal absent. | data-ingest | nice-to-have | L | missing |
| GAP-059 | CFTC COT (Friday 15:30 ET, Disaggregated since 2006) ingest absent. | data-ingest | minor | M | missing |
| GAP-060 | Logistics — USDA AMS GTR weekly, USACE LPMS 30-min, Baltic indices — ingest absent. | data-ingest | minor | M | missing |
| GAP-061 | Cash-bid feeds (Barchart `getGrainBids`, DTN ProphetX) ingest absent. | data-ingest | minor | M | missing |
| GAP-062 | FX cross-asset feeds (DXY, USD/BRL, USD/ARS, USD/CNY, WTI/Brent/ULSD) ingest absent. | data-ingest | major | L | missing |
| GAP-063 | CME EOD Settlements pull (Rule 813 12:00am CT preliminary, 10:00am CT final) absent. | data-ingest | blocker | M | missing |
| GAP-064 | Per-stream ingest-latency probe (Hermes `publish_time` → first parser touch) absent; only consumer-side staleness budget exists. | data-ingest | major | S | partial |
| GAP-065 | Source/stream-level redundancy absent; single endpoint per feed; `hermes_http` SSE fallback declared in YAML but unused. | data-ingest | major | M | missing |
| GAP-066 | Pyth `num_publishers` defaults to 0 silently when Hermes omits the field — fail-silent crack in an otherwise fail-loud parser. | data-ingest | major | S | partial |
| GAP-067 | Holiday and per-stream session calendars (CT/ET/ART/UTC publication clocks) absent; only WTI session registered. | data-ingest | major | L | missing |
| GAP-068 | Backfill on Pyth reconnect not implemented (re-subscribe only); SSE fallback dead. | data-ingest | minor | M | missing |
| GAP-069 | Point-in-time DB semantics for USDA revisions absent; tick ring is overwrite-on-push. | data-ingest | major | L | missing |
| GAP-070 | CVOL benchmark intraday/EOD ingest absent. | data-ingest | nice-to-have | M | missing |
| GAP-071 | Kalshi REST/WS client entirely absent — no `httpx.AsyncClient`, no signing, no endpoint binding (declared `httpx` is unused). | contract | blocker | XL | missing |
| GAP-072 | RSA-PSS-SHA256 signing module / key loader / header builder absent; no `cryptography` dep imported. | contract | blocker | M | missing |
| GAP-073 | Tiered token-bucket pacer / per-endpoint cost table / 429-without-`Retry-After` exponential backoff absent. | contract | blocker | M | missing |
| GAP-074 | Series → Event → Market → Yes/No four-level ticker schema and parser/formatter (`KXSOYBEANW`, `KXSOYBEANW-26APR24`, `…-17`) absent. | contract | blocker | M | missing |
| GAP-075 | Event endpoint `GET /events/{ticker}` reading `floor_strike`/`cap_strike`/`strike_type` not consumed; no bucket-grid ingest. | contract | blocker | M | missing |
| GAP-076 | Appendix-A reference-price-mode loader (CBOT settle / VWAP / Kalshi snap) absent; no `kalshi_reference_price_mode` config field. | contract | blocker | S | missing |
| GAP-077 | CBOT Rule 813 daily-settle resolver (~1:20 p.m. CT VWAP) and front-month roll calendar (Jan/Mar/May/Jul/Aug/Sep/Nov) absent; no `ZSK26` literal anywhere. | contract | blocker | M | missing |
| GAP-078 | Soybean FND logic (T-2 BD before delivery month) and roll-window resolver absent. | contract | blocker | M | missing |
| GAP-079 | Bucket / corridor data structures (`Event`, `Bucket(floor, cap)`, MECE check, open-ended tail handling) absent. | contract | blocker | M | missing |
| GAP-080 | Kalshi `[$0.01, $0.99]` quote-band gate absent; `validation/sanity.py` clamps `[0,1]` (correct for prob, wrong for venue quote). | contract | blocker | S | wrong |
| GAP-081 | $0.01 tick rounding (with optional $0.02 override per Rule 13.1(c)) on quotes absent. | contract | blocker | S | missing |
| GAP-082 | Order types (`limit`, `market`), TIFs (`fill_or_kill`, `good_till_canceled`, `immediate_or_cancel`), and flags (`post_only`, `reduce_only`, `buy_max_cost`, `self_trade_prevention_type`) not encoded. | contract | blocker | M | missing |
| GAP-083 | Position-limit accounting (Rule 5.19 max-loss dollars, default $25k/member, MM-Program 10× exemption) absent. | contract | blocker | M | missing |
| GAP-084 | Rule 5.15 wash-trade prevention and self-trade-prevention modes (`taker_at_cross`, `maker`) absent. | contract | major | M | missing |
| GAP-085 | $0.20 No-Cancellation Range / 15-minute trade-bust review window absent. | contract | major | S | missing |
| GAP-086 | Settlement / clearing surface (Klear DCO; Rule 6.3(d); $1×ITM crediting) and post-settle reconciliation absent. | contract | blocker | L | missing |
| GAP-087 | `KXSOYBEANW` 24/7 (incl. weekends) trading calendar not registered; only WTI session is wired and treats weekends as closed. | contract | blocker | M | wrong |
| GAP-088 | CBOT soybean ~7%-of-price daily limit and limit-lock-day handling (settle = limit-trip price; tail bucket point-mass) absent. | contract | major | M | missing |
| GAP-089 | Friday-holiday Rule 7.2(b) roll-to-next-trading-day logic absent; calendar carries no holiday set. | contract | blocker | M | missing |
| GAP-090 | Outcome-publication windows (Rule 13.1(d) 11:59pm ET on determination day; Rule 7.1 review extension) not consumed. | contract | major | M | missing |
| GAP-091 | Rule 7.2(a)/(b) exchange-adjustment listener (Source Agency / Underlying changes; data-disruption expiry roll) absent. | contract | major | M | missing |
| GAP-092 | RFQ submission (`POST /communications/rfq`, 100 open RFQs cap) absent. | contract | major | M | missing |
| GAP-093 | Member/role/DMM concept and FCM pre-trade-risk hook (Robinhood Derivatives etc.) absent. | contract | minor | M | missing |
| GAP-094 | Rulebook chapter 4 MM-designation flag / Rule 5.16 PAL not modelled. | contract | minor | S | missing |
| GAP-095 | URL slug builder `/markets/{series}/{slug}/{market}` absent. | contract | minor | S | missing |
| GAP-096 | Letter-prefixed strike-suffix products (vs integer index) handler absent. | contract | nice-to-have | S | missing |
| GAP-097 | DCM / 17 CFR Parts 38/40 / 40.2(a) regulatory metadata absent. | contract | nice-to-have | S | missing |
| GAP-098 | Rule 8.1 idle-collateral interest model absent (treasury layer). | contract | nice-to-have | M | missing |
| GAP-099 | Bucket-grid week-stable vs intraweek-recentre listener (`market_lifecycle_v2`) absent. | contract | major | M | missing |
| GAP-100 | Soybean-block (`config/commodities.yaml:58-60`) has `stub: true` only — no `cme_symbol`, no Kalshi block, no fee schedule, no position-cap fields, no bucket-grid source. | contract | blocker | S | missing |
| GAP-101 | Per-bucket and per-asset Greek surface (Δᵢᴷ, Γᵢᴷ, vega) absent; `TheoOutput` carries no Greeks. | hedging | blocker | M | missing |
| GAP-102 | Aggregate book delta `Δ^port = Σᵢ qᵢΔᵢᴷ` and ZS-futures sizer `−Δ^port/N_ZS` (N_ZS=5,000) absent. | hedging | blocker | M | missing |
| GAP-103 | Delta-hedge threshold trigger (|Δ^port| ≥ 1 ZS contract) absent; no threshold check. | hedging | blocker | S | missing |
| GAP-104 | FCM API client (Interactive Brokers / AMP / Tradovate) absent — no broker REST, no order routing, no ack ingest. | hedging | blocker | XL | missing |
| GAP-105 | Vertical-spread option-hedge builder (replicates corridor digital, neutralises Δ/Γ/vega) absent. | hedging | major | L | missing |
| GAP-106 | Hedge-side basis tracker (Kalshi-snapshot vs CME-option-reference: reference-price, timing, contract-month) absent; `state/basis.py` covers a different basis (Pyth↔CME drift). | hedging | major | M | wrong |
| GAP-107 | SPAN / FCM margin model (5–8% futures notional; option-spread variance margin; broker initial+maintenance + daily loss tripwires) absent. | hedging | major | L | missing |
| GAP-108 | CME ZS L1 feed via FCM / Databento absent; no second `feeds/` producer. | hedging | major | L | missing |
| GAP-109 | Hedge round-trip latency budget / per-leg observability absent; only model compute is timed. | hedging | minor | S | missing |
| GAP-110 | Three-instance compute topology (quoter / hedge / capture) with region pinning (`us-east-1`) absent; no `main`, no entry-point, no Dockerfile. | hedging | minor | M | missing |
| GAP-111 | Hedge-leg fee model ($1/contract exchange + $0.50 FCM commission + 1–5¢ option BA) absent. | hedging | minor | S | missing |
| GAP-112 | CBOT-closed regime detector (Fri 13:20 CT → Sun 19:00 CT) and Sunday-reopen vol regime absent; no quote-pull primitive on (also absent) order layer. | hedging | major | M | missing |
| GAP-113 | Limit-locked Friday hedge-leg unwind model (discrete-jump P&L) and stress harness absent. | hedging | major | M | missing |
| GAP-114 | Cross-asset hedge selection (ZC / ZM / ZL / MATIF rapeseed / Dalian) absent; single-feed ingest. | hedging | nice-to-have | L | missing |
| GAP-115 | Cross-asset intensity calibration (`calibration/` is empty) absent. | hedging | nice-to-have | M | missing |
| GAP-116 | Per-bucket inventory store / position registry (`state/positions.py` or equivalent) absent. | inventory | blocker | L | missing |
| GAP-117 | Cash and inventory dynamics `dX = (S+δᵃ)dNᵃ − (S−δᵇ)dNᵇ`, `dq = dNᵇ − dNᵃ` not modelled (no fill events). | inventory | blocker | M | missing |
| GAP-118 | Aggregate net-delta cap on unhedged Δ^port (book-level binding constraint) absent. | inventory | blocker | M | missing |
| GAP-119 | Per-bucket / per-Event signed dollar-exposure tracker vs Appendix-A limit absent. | inventory | blocker | M | missing |
| GAP-120 | Risk-gating stage J — block quotes that breach per-bucket / aggregate-delta / scenario thresholds — absent. | inventory | blocker | L | missing |
| GAP-121 | Required scenarios (WASDE-day P&L; weather-shock 3–5% gap with Bates-SVJ; expiry-day liquidity-collapse marks-to-intrinsic) and harness absent. | inventory | blocker | L | missing |
| GAP-122 | `buy_max_cost` per-request dollar cap as second-layer limit absent (no order builder yet). | inventory | major | S | missing |
| GAP-123 | Multi-asset cross-bucket inventory penalty (Guéant 2017) absent. | inventory | major | L | missing |
| GAP-124 | Long-bucket-i should skew adjacent-bucket-j (matrix-skew C08-48 / C10-53) absent. | inventory | major | L | missing |
| GAP-125 | Kalshi full-cash-collateralisation accounting ($0.30 Yes costs $0.30) absent; no collateral utilisation. | inventory | major | M | missing |
| GAP-126 | Forward-curve carry direction signal (C02-57) absent; `state/basis.py` carries one annualized scalar, not a curve. | inventory | minor | M | missing |
| GAP-127 | Routledge–Seppi–Spatt endogenous convenience yield as inventory-state function absent. | inventory | nice-to-have | L | missing |
| GAP-128 | Deaton–Laroque non-negativity-of-stockpile inventory model absent. | inventory | nice-to-have | L | missing |
| GAP-129 | Capital allocator that trades off Kalshi-leg vs CME-hedge-leg margin absent (no margin model on either leg). | inventory | major | M | missing |
| GAP-130 | C10-79 milestone-2 sandbox caps ($500/bucket, $5,000/Event) absent as configurable interface. | inventory | major | S | missing |
| GAP-131 | Kalshi WebSocket multiplex (`orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`) consumer absent; only Pyth Hermes WS exists. | oms | blocker | L | missing |
| GAP-132 | `POST /portfolio/orders`, `DELETE /portfolio/orders/{id}`, amend, decrease, batch endpoints not bound. | oms | blocker | M | missing |
| GAP-133 | Local resting-book mirror / queue-position cache (`GET /orders/{id}/queue_position`, `/queue_positions`) absent. | oms | major | M | missing |
| GAP-134 | Fill ingestion and per-bucket post-trade markout (1m/5m/30m) absent. | oms | major | M | missing |
| GAP-135 | Three-times-per-session reconciliation (open / intraday / EOD) of `GET /portfolio/{positions,fills,balance,settlements}` vs FCM execution reports absent. | oms | blocker | L | missing |
| GAP-136 | Single reconciliation table keyed `(event_ticker, timestamp, side)` and persistent store absent (no DB anywhere). | oms | major | M | missing |
| GAP-137 | Idempotency / client-order-ID dedupe layer on retried sends absent. | oms | major | S | missing |
| GAP-138 | Amend-not-cancel queue-priority preservation rule absent (no amend, no cancel). | oms | major | S | missing |
| GAP-139 | Pull-and-refit protocol around USDA windows (pull 30–60s before, refit, repost) absent. | oms | major | M | missing |
| GAP-140 | Trade-through probability `μᵢ/(μᵢ+νᵢ)` from market-order vs cancel intensity absent (no historical fill/cancel store). | oms | major | M | missing |
| GAP-141 | Cont–de Larrard / Huang–Lehalle–Rosenbaum queue-reactive transfer absent. | oms | major | L | missing |
| GAP-142 | Cancel-vs-amend fee economics absent (no fee model). | oms | minor | S | missing |
| GAP-143 | FIX 5.0 SP2 Order Entry / Drop Copy / Listener (Premier+) and FIX Drop Copy reconciliation absent. | oms | nice-to-have | XL | missing |
| GAP-144 | 200,000 open-order cap per member tracking absent. | oms | nice-to-have | S | missing |
| GAP-145 | C10-79 spread floor (≥ 4¢ each side) and Milestone-2 quoter contract absent end-to-end. | oms | blocker | M | missing |
| GAP-146 | Backtest harness / historical replay engine entirely absent (no `backtest/`, no fill simulator, no walk-forward runner, no P&L attribution). | backtest | blocker | XL | missing |
| GAP-147 | Milestone-0 historical CME ZS option chain pull → SVI → Figlewski → score-against-settled-Kalshi-week pipeline absent. | backtest | blocker | XL | missing |
| GAP-148 | Three forward-captured tapes (Kalshi `orderbook_delta+ticker+trade+fill`; CME L1 + EOD options chain; fundamentals + weather) not being captured. | backtest | blocker | L | missing |
| GAP-149 | Historical/sandbox demo paper-trading layer at the quoter level absent (C09-25 dispensation cannot land). | backtest | major | L | missing |
| GAP-150 | DuckDB + Parquet on S3 (`httpfs`) tape storage substrate not adopted; `pyproject.toml` lacks DuckDB / pyarrow / boto3. | backtest | major | M | missing |
| GAP-151 | Weekly P&L attribution stage L (edge / inventory MTM / hedge slippage / fees) feedback into (Aᵢ, kᵢ, γ) absent. | backtest | major | L | missing |
| GAP-152 | Maker/taker fee model and round-trip cost subtraction absent — every gross-edge number would overstate by ≥ 250 bps. | backtest | blocker | S | missing |
| GAP-153 | Look-ahead-safe PIT store for USDA features absent (revisions discipline). | backtest | major | M | missing |
| GAP-154 | Survivorship-aware contract universe absent; forward-only capture has no dead-contract record. | backtest | minor | M | missing |
| GAP-155 | Turnover counter, capacity / market-impact penaliser, Sharpe-discount factors (×0.6–0.7) for live-money planning absent. | backtest | minor | M | missing |
| GAP-156 | Crush-spread book (board crush, reverse crush, GPM signal, Rechner-Poitras filtered MR, 3¢ entry filter) absent — no ZS/ZM/ZL universe. | strategy | major | L | missing |
| GAP-157 | Calendar-spread book (July/November old-vs-new-crop, contango/backwardation classifier, Moore composite, Farmdoc 3-of-15) absent. | strategy | major | L | missing |
| GAP-158 | Bean/corn ratio (ZSN/ZCN) cluster (>2.5 favour soy, <2.2 favour corn, fade extremes vs USDA Acreage) absent. | strategy | major | M | missing |
| GAP-159 | TSMOM / Donchian / MA-crossover trend signals on ZS absent (history exists in TickRing but no reader). | strategy | major | M | missing |
| GAP-160 | Carry / term-structure cross-sectional sort (Erb-Harvey, Fuertes-Miffre-Rallis combined) absent (universe shape: 1 live + 13 stubs). | strategy | major | L | missing |
| GAP-161 | Cross-sectional momentum on ≥15-commodity universe absent; `TickStore` keys by single commodity, `TheoInputs.spot` is scalar. | strategy | major | L | missing |
| GAP-162 | Goldman-roll detector / GSCI-roll consumer absent; `cme_roll_rule` is WTI-only. | strategy | minor | M | missing |
| GAP-163 | COT positioning signals (MM-net-long contrarian, MM-flip+momentum, commercial inflection) absent. | strategy | minor | M | missing |
| GAP-164 | ENSO + 5-yr basis state, soil-moisture entry, harvest-fade entry signals absent. | strategy | minor | L | missing |
| GAP-165 | Per-trade ATR/ADX/EMA/MACD/Donchian state and sizing (Brandt 0.5–1%, Turtle 1-unit ATR, Parker, Raschke, Holy Grail, Anti) absent. | strategy | minor | L | missing |
| GAP-166 | Tape-event detector (>2σ in <15 min headline) absent; per-tick reprice has no rolling-window classifier. | strategy | major | M | missing |
| GAP-167 | WASDE fade rule (>1.5σ + 15-min stall, sized 25–50 bp NAV) and Crop-Progress / weather entry rules absent. | strategy | major | M | missing |
| GAP-168 | Stocks-to-use regime classifier (tight vs loose) absent; required gate for §2.1 weather→density. | strategy | major | M | missing |
| GAP-169 | Cash-basis fair-value overlay and farmer-hedge slow-prior absent. | strategy | minor | M | missing |
| GAP-170 | Oilshare / RFS-RVO / RIN ingest and signals absent. | strategy | minor | M | missing |
| GAP-171 | Kill-switch primitives — `DELETE /orders/batch` and `POST /order-groups/{id}/trigger` — absent (no Kalshi REST client to call them). | observability | blocker | M | missing |
| GAP-172 | Four kill triggers — aggregate signed delta breach, intraweek PnL drawdown, CME hedge heartbeat fail (N s), Kalshi WS reconnects > K/min — absent end-to-end (no producer, no consumer, no transport). | observability | blocker | L | missing |
| GAP-173 | Forward-capture asset (Kalshi tape, CME L1+EOD chain, fundamentals+weather) not being recorded — every missed day permanently lost. | observability | blocker | L | missing |
| GAP-174 | Structured logging surface absent — `structlog` declared in `pyproject.toml:20` but unused; only two stdlib log calls exist in `feeds/pyth_ws.py`. | observability | major | M | missing |
| GAP-175 | Metrics emitters (Prometheus counters / gauges / histograms) absent; `prometheus_client` not in deps. | observability | major | M | missing |
| GAP-176 | Tick-to-quote latency histogram (5-leg breakdown) absent; only model-compute leg is measured, only at offline-pytest time. | observability | major | M | partial |
| GAP-177 | Grafana / Prometheus / PagerDuty integration (M4 ops hardening) absent. | observability | major | L | missing |
| GAP-178 | `engine/scheduler.py` priority queue is unwired (Red Flag 5); no `risk_kill` / `quote_cancel` / safety-class entries in the `Priority` enum. | observability | major | M | partial |
| GAP-179 | `SanityError` publish-time policy undefined — quote-drop / market-suspend / page / restart-model not chosen. | observability | major | S | missing |
| GAP-180 | Pyth WS reconnect counter resets per connection (not per minute), defeating any rate-windowed kill trigger. | observability | minor | S | wrong |
| GAP-181 | Hot-standby quoter / failover topology absent (single-process layout). | observability | minor | L | missing |
| GAP-182 | Milestone gating discipline (M_n complete only when M_{n+1}'s tests pass on M_n data) not encoded as test markers. | observability | major | S | missing |
| GAP-183 | VPIN-as-USDA-window-withdrawal trigger absent; no flow-toxicity computation. | observability | minor | M | missing |
| GAP-184 | CME Daily Bulletin (unreported blocks, EFPs, OI deltas) reconciliation/calibration ingest absent. | observability | minor | M | missing |
| GAP-185 | `.gitignore`-implied `calibration/params/*.json` artefact format has no producer; intended consumer of nightly calibration JSON unwritten. | observability | major | M | missing |

### 2.2 Detail table

| GAP-id | All topic tags | C-id citations (representative) | Code locations | Blast radius | Effort justification | Notes |
|---|---|---|---|---|---|---|
| GAP-001 | pricing-model, oms, strategy, inventory | C02-01, C02-04, C02-21, C02-22, C02-23, C02-79, C02-80, C10-05 | n/a — no module | engine/pricer.py, models/, models/registry.py, calibration/, state/positions.py (new), config/commodities.yaml | XL — multi-module new control loop with calibration substrate | The cleanest single-line summary in C10-05; absorbs every A–S/CJ row. No γ in YAML, no q in any state object, no λ(δ) producer. |
| GAP-002 | pricing-model, inventory | C02-06, C02-24, C08-40 | engine/pricer.py:79, models/gbm.py:35 | engine/pricer.py, models/, state/positions.py (new) | M — closed-form formula plus an inventory carrier | Reservation-price formula is canonical; absence depends on GAP-001 + GAP-116. |
| GAP-003 | pricing-model, oms | C02-02, C02-05, C02-25, C02-26, C08-42 | n/a — no module | engine/pricer.py, models/base.py (TheoOutput shape), engine/quoter.py (new) | L — new quoter module with shape-changing TheoOutput | TheoOutput has no bid/ask/spread fields; downstream wiring needed. |
| GAP-004 | pricing-model, density, inventory | C08-40, C08-45, C08-47, C08-49, C08-105, C10-52, C10-53 | n/a — no module | engine/pricer.py, models/, state/positions.py, density pipeline | XL — multi-asset HJB plus per-bucket reservation price | Depends on GAP-001 plus GAP-021 covariance. |
| GAP-005 | pricing-model, density, contract | C08-04, C08-08, C08-13, C07-32, C07-40, C10-01 | models/base.py:55-69, models/gbm.py:69-105, engine/pricer.py:77-86 | models/, engine/pricer.py, validation/sanity.py | M — adapter layer subtracting two `D(K)` outputs | Once bucket grid arrives the corridor decomposition is one subtraction per pair. |
| GAP-006 | pricing-model, density | C08-05, C10-02 | models/gbm.py:35-42, models/gbm.py:97-105 | models/, density pipeline | XL — replace model-implied with market-implied RND | Strictly worse than GAP-008: not just wrong dynamics but wrong epistemology. Source: assumed GBM vs extracted RND. |
| GAP-007 | pricing-model, contract, oms, backtest | C08-90, C08-91, C08-93, C07-65, C07-66, C07-67 | n/a — no module | models/base.py (TheoOutput), engine/pricer.py, config/commodities.yaml, oms/ (new) | M — closed-form fee plus a config block | `ceil(0.07·P(1−P)·100)/100`; one-liner per leg, no maker-vs-taker state machine until OMS exists. |
| GAP-008 | pricing-model, density | C02-42, C02-46, C02-75, C10-02 | models/gbm.py:1-10, models/registry.py:32-38 | models/, state/iv_surface.py (signature change) | XL — full Heston/Bates SV layer with calibrator | C02-75 is "minimum viable"; this is *the* MVP-bar gap. |
| GAP-009 | pricing-model, density | C02-71, C02-74, C08-25 | models/gbm.py:35-42 | models/, models/registry.py | L — new model variant with thicker tails | Lognormal tails are structural; needs Student-t or jump branch. |
| GAP-010 | pricing-model | C02-43 | engine/pricer.py:71, models/gbm.py:36-37 | state/iv_surface.py, models/, engine/pricer.py | L — vₜ curve plus Heston-A–S kernel | Depends on GAP-008. |
| GAP-011 | pricing-model | C02-45 | models/gbm.py:35-42, models/registry.py:34-37 | models/jump_diffusion.py (new), models/registry.py | M — single-builder unstubbed in registry | Commented-out slot exists; uncommenting requires actual builder. |
| GAP-012 | pricing-model | C02-46, C08-89 | models/gbm.py:1-10 | models/bates.py (new), state/iv_surface.py | L — combine SV + jumps | Required for C08-89 weather-shock scenario. |
| GAP-013 | pricing-model | C02-12, C02-13 | engine/pricer.py:59 | engine/pricer.py, models/, oms/ | L — flow-classifier plus Bayes update | Needs Lee-Ready/BVC classifier first. |
| GAP-014 | pricing-model, data-ingest | C02-15, C02-38 | engine/pricer.py:71-72 | feeds/, state/, engine/pricer.py | L — OFI computation off MBO/MBP feed | Depends on GAP-052 (MBO/MBP). |
| GAP-015 | pricing-model | C02-31, C02-83 | state/basis.py:28-35, models/gbm.py:35 | state/basis.py, calibration/ | L — multi-signal aggregator | One-scalar interface must change to admit multiple drivers. |
| GAP-016 | pricing-model | C02-32 | state/basis.py:37-48 | state/basis.py, engine/pricer.py | M — asymmetric-drift wiring | Depends on GAP-015. |
| GAP-017 | pricing-model, density | C08-38, C08-39, C10-06, C10-07 | n/a — no module | calibration/, engine/pricer.py | M — single-parameter shrinkage | One-parameter overlay on RND-implied Yes prices. |
| GAP-018 | pricing-model, density | C10-16 | n/a — no module | calibration/, state/iv_surface.py | M — pre-event scaler | Coupled to GAP-019. |
| GAP-019 | pricing-model, oms, observability, strategy | C02-65, C02-66, C02-81, C08-97, C09-40, C10-13, C10-14, C10-21, C10-22, C10-23 | engine/event_calendar.py:30-38, config/commodities.yaml:24-28 | engine/event_calendar.py, models/registry.py, engine/pricer.py | M — YAML reader plus consumer in pricer | Schema present, no consumer (Red Flag 14). |
| GAP-020 | pricing-model, hedging | C08-41 | n/a — no module | models/, engine/pricer.py | M — derivative + bucket integration | Depends on GAP-005, GAP-101. |
| GAP-021 | pricing-model, density, inventory, hedging | C08-45, C08-105, C10-52 | n/a — no module | density pipeline, state/, engine/pricer.py | XL — perturbation-based Σᵢⱼ estimator | Phase C labels as research-open (C10-OQ-05). |
| GAP-022 | pricing-model, inventory | C02-28, C02-29 | n/a — no module | models/glft.py (new), engine/quoter.py | L — closed-form plus inventory state | GLFT formula is closed-form once q exists. |
| GAP-023 | pricing-model, inventory | C02-30 | n/a — no module | engine/quoter.py, state/positions.py | M — bound checker | Trivial once q exists. |
| GAP-024 | pricing-model, oms | C08-106 | n/a — no module | engine/quoter.py, calibration/ | L — depends on fill ingest | Coupled to GAP-134. |
| GAP-025 | pricing-model | C02-17, C02-18 | n/a — no module | calibration/ | M — diagnostic computation | Backward-looking only; not blocker. |
| GAP-026 | pricing-model | C08-54, C08-55, C08-56 | n/a — no module | engine/quoter.py, models/ | M — closed-form widener | Edge proximity is a function of bucket geometry. |
| GAP-027 | pricing-model | C02-56 | state/basis.py:28-35 | state/basis.py, engine/pricer.py | M — extreme-regime branch | Depends on GAP-116. |
| GAP-028 | pricing-model, contract | C02-76, C02-77, C07-83 | engine/event_calendar.py, state/iv_surface.py:30-35 | state/iv_surface.py, engine/event_calendar.py | M — limit-detector + bias correction | Couples to GAP-088. |
| GAP-029 | pricing-model, inventory | C02-82 | n/a — no module | validation/, engine/quoter.py | L — risk-manager truncation layer | The "supersedes optimiser output" rule. |
| GAP-030 | pricing-model, strategy | C10-11, C10-OQ-09 | n/a — no module | calibration/ | M — two-regime calibrator | Phase C: research-open at the calibration level. |
| GAP-031 | pricing-model, strategy | C10-39, C02-67 | config/commodities.yaml:24-28 | calibration/, config/ | S — table lookup | Operationalizes C02-67. |
| GAP-032 | pricing-model | C10-15 | n/a — no module | density pipeline, observability | M — IV-curvature analyser | Diagnostic. |
| GAP-033 | pricing-model | C02-62 | n/a — no module | engine/quoter.py | S — single coefficient | Roll-window context. |
| GAP-034 | pricing-model | C02-08 | n/a — no module | engine/quoter.py | S — three-component decomposition | Operational guidance only. |
| GAP-035 | pricing-model | C02-09 | n/a — no module | engine/quoter.py, calibration/ | M — concession term | Theory-side; depends on flow data. |
| GAP-036 | density | C08-11 | n/a — no module | density pipeline | L — SciPy second-derivative on smoothed surface | Required source for any model-free density. |
| GAP-037 | density | C08-17, C08-22, C08-101 | n/a — no module | density pipeline, calibration/ | L — SVI calibrator (a, b, ρ, m, σ) per expiry | Workhorse for weekly soybean. |
| GAP-038 | density | C08-18 | n/a — no module | density pipeline, validation/ | M — constraint set on SVI fit | Coupled to GAP-037. |
| GAP-039 | density | C08-21, C08-23 | n/a — no module | density pipeline | M — vega-weighted spline | Fallback when no co-terminal. |
| GAP-040 | density | C08-19, C08-20 | n/a — no module | density pipeline | M — SABR (α, β, ρ, ν) | Alternative to SVI; arbitrageable in deep-OTM. |
| GAP-041 | density | C08-26, C08-27, C08-28, C08-29 | n/a — no module | density pipeline | L — Figlewski piecewise GEV with paste-points | Bollinger-Melick-Thomas refinement. |
| GAP-042 | density, pricing-model, hedging | C02-51, C06-08, C08-16 | state/iv_surface.py:21-48, state/iv_surface.py:30-35 | state/iv_surface.py | L — signature change to (strike, expiry) grid | Public method `atm(commodity, *, now_ns) -> float` cannot grow without breaking. |
| GAP-043 | density, pricing-model | C08-13, C08-103, C07-39 | n/a — no module | density pipeline, validation/sanity.py | M — integrate plus normalize | Edge-inclusivity policy `[ℓ, u)` per C07-32. |
| GAP-044 | density, contract | C07-39, C08-118 | validation/sanity.py:43-67 | validation/sanity.py | S — extension to existing checker | One step beyond per-strike monotone. |
| GAP-045 | density | C08-30, C08-31, C08-32, C08-33 | engine/event_calendar.py:96-107 | engine/event_calendar.py, state/iv_surface.py | M — variance rescaling + co-terminal detector | C08-32 lets code skate on Apr 24 if it knows. |
| GAP-046 | density, data-ingest | C08-100, C09-31, C09-33 | feeds/__init__.py, feeds/ | feeds/cme/ (new), state/iv_surface.py | XL — new feed module with smoothing input | Pre-condition for the smoothing stage. |
| GAP-047 | density, data-ingest | C08-15 | n/a — no module | density pipeline, feeds/cme/ | S — one-pass arb prune | Catastrophic if skipped per C08-15. |
| GAP-048 | density, pricing-model | C08-37, C08-104, C08-39 | n/a — no module | density pipeline, calibration/ | M — measure-overlay parametric layer | Couples to GAP-017. |
| GAP-049 | density, contract | C08-31, C10-65 | engine/event_calendar.py:30-38 | engine/event_calendar.py, config/ | M — table loader plus picker | Feb–Aug weeklies needed for option hedge co-terminal. |
| GAP-050 | density, pricing-model, hedging | C08-46, C08-105 | n/a — no module | density pipeline, state/ | L — Σᵢⱼ from RND perturbation | Depends on GAP-021 estimator choice. |
| GAP-051 | data-ingest, density | C03-01, C03-02, C03-08, C06-01, C09-29 | feeds/__init__.py, pyproject.toml:14-19 | feeds/cme/ (new), pyproject.toml | XL — full SBE/FIX or Databento prosumer | UDP multicast or vendor redistribution. |
| GAP-052 | data-ingest, oms, pricing-model | C03-03, C03-04, C07-62, C08-50 | state/tick_store.py:23-28 | state/, feeds/cme/ | L — depth-book reconstruction | LatestTick has no bid/ask/depth shape. |
| GAP-053 | data-ingest, strategy, pricing-model, observability | C03-53, C03-54, C03-55, C06-14-C06-23, C08-94, C08-95, C09-39-C09-44, C01-69-C01-73 | config/commodities.yaml:58-60, engine/event_calendar.py:30-38 | config/commodities.yaml, engine/event_calendar.py, feeds/usda/ (new) | M — YAML reader plus event registration | Highest-density restatement: WASDE / Crop Progress / FAS ESR / FGIS / Plantings / Acreage / Grain Stocks. |
| GAP-054 | data-ingest | C03-56, C06-24, C06-25 | feeds/__init__.py | feeds/usda/ (new) | L — three USDA REST clients | API-key plumbing absent. |
| GAP-055 | data-ingest, strategy | C03-46-C03-49, C06-40-C06-48, C09-45-C09-50, C10-08, C10-09, C10-10 | feeds/__init__.py, pyproject.toml:14-19 | feeds/weather/ (new), pyproject.toml | XL — GRIB2 readers plus per-stream cycle calendars | ECMWF / GFS / GEFS / AIFS / HRRR / ENS / ERA5. |
| GAP-056 | data-ingest, strategy | C06-51, C06-52, C06-53, C06-54 | feeds/__init__.py | feeds/satellite/ (new) | L — Sentinel-2, SMAP, Drought Monitor | Earthdata Login auth. |
| GAP-057 | data-ingest, strategy | C03-57, C03-58, C06-31, C06-32, C06-33, C06-34, C09-44 | feeds/__init__.py | feeds/sam/ (new) | L — CONAB/BCBA/BCR/Rosario/Paraná | SAm-clock partition. |
| GAP-058 | data-ingest | C03-59, C06-39, C06-61, C06-62 | feeds/__init__.py | feeds/china/ (new), feeds/ais/ (new) | L — GACC + AIS-residual | Derived signal. |
| GAP-059 | data-ingest, strategy, observability | C03-79, C06-64-C06-69, C09-51, C09-52, C10-27 | config/commodities.yaml:24-28, engine/event_calendar.py:30-38 | feeds/cot/ (new), config/, engine/event_calendar.py | M — Friday 15:30 ET puller plus parser | Disaggregated since 2006; CSV/XML/RDF/TSV/RSS/HTML. |
| GAP-060 | data-ingest | C03-44, C06-55-C06-58, C09-51, C09-53 | feeds/__init__.py | feeds/logistics/ (new) | M — GTR/LPMS/Baltic/NDC | LPMS 30-min cadence highest. |
| GAP-061 | data-ingest, strategy | C06-79, C06-80, C03-87, C09-53 | feeds/__init__.py | feeds/cashbids/ (new) | M — Barchart `getGrainBids` / DTN | Phase 03 retail-quant lever. |
| GAP-062 | data-ingest, pricing-model | C06-70, C06-71, C06-72, C06-74 | feeds/__init__.py | feeds/fx/ (new) | L — multi-pair tick subscriber | DXY, USD/BRL, USD/ARS, USD/CNY plus oil. |
| GAP-063 | data-ingest, contract | C06-10, C06-11, C06-12, C06-82, C09-54 | config/commodities.yaml | feeds/cme/, config/ | M — daily settle puller | Settlement reference is the contract resolution per C09-54. |
| GAP-064 | data-ingest, observability | C06-84, C09-58 | feeds/pyth_ws.py:120-145, config/commodities.yaml:9, engine/pricer.py:60-65 | feeds/pyth_ws.py, observability | S — per-frame timestamp probe | Latency assertion is a *bound*, not a *measurement*. |
| GAP-065 | data-ingest | (file question: redundancy) | config/pyth_feeds.yaml:7-8, feeds/pyth_ws.py:48 | feeds/, config/ | M — second endpoint plus failover | `hermes_http` in YAML is dead config. |
| GAP-066 | data-ingest | (file question: schema drift) | feeds/pyth_ws.py:112-115 | feeds/pyth_ws.py | S — fail-loud raise on missing field | Cartography Red Flag 8: silent default → pricer rejects all such ticks. |
| GAP-067 | data-ingest, contract, oms | C06-31, C06-33, C07-81, C10-72, C10-73 | engine/event_calendar.py:30-38, 76-79 | engine/event_calendar.py, config/ | L — multi-zone calendar | Only WTI session is registered; ART/ET/CT/UTC unimplemented. |
| GAP-068 | data-ingest | (file question: backfill on reconnect) | feeds/pyth_ws.py:128-130, 138-145, config/pyth_feeds.yaml:8 | feeds/pyth_ws.py | M — SSE/REST gap-fill on reconnect | Currently re-subscribes only; SSE fallback unused. |
| GAP-069 | data-ingest, backtest | C05-60 | state/tick_store.py:31-66 | state/tick_store.py, feeds/usda/ | L — versioned PIT store | Overwrite-on-push ring conceals revisions. |
| GAP-070 | data-ingest | C06-09 | feeds/__init__.py | feeds/cvol/ (new) | M — EOD + intraday CVOL | Implied by `vol_source: implied_weekly_atm`. |
| GAP-071 | contract, oms, observability, hedging, data-ingest | C07-07, C07-87, C07-92, C07-93, C09-01-C09-14, C08-110 | pyproject.toml:16, audit_A_cartography.md:248-249, feeds/__init__.py | feeds/kalshi/ (new), oms/ (new) | XL — full client (REST + WS + signing + rate limiter + order builder + fill ingest) | The single foundational blocker; everything Kalshi-side hangs off it. |
| GAP-072 | contract, oms, observability | C07-95, C07-96, C07-97, C09-04 | pyproject.toml:14-19, feeds/ | feeds/kalshi/auth.py (new), pyproject.toml | M — RSA-PSS signing module | Without these, every REST call returns 401. |
| GAP-073 | contract, oms, observability, data-ingest | C07-99, C07-100, C07-101, C09-15-C09-18, C10-33, C10-75, C10-76 | engine/scheduler.py:21-59, feeds/pyth_ws.py:138-145 | feeds/kalshi/ratelimiter.py (new), oms/ | M — token-bucket pacer + 429 backoff handler | Tier table; default 10 tokens, cancel discounted to 2; no Retry-After. |
| GAP-074 | contract | C07-01, C07-02, C07-03, C07-05, C07-06 | n/a — no module | feeds/kalshi/, models/ | M — schema/parser/formatter | Series → Event → Market → Yes/No. |
| GAP-075 | contract, density | C07-07, C08-100 | n/a — no module | feeds/kalshi/, state/bucket_grid.py (new) | M — per-Event REST puller plus parser | Bucket enumeration source. |
| GAP-076 | contract, pricing-model | C07-14, C07-17, C07-24, C07-112 | config/commodities.yaml:6-85, engine/pricer.py:79 | config/, engine/pricer.py | S — config field plus reader | "Single largest pricing unknown" per Phase 7. |
| GAP-077 | contract, hedging | C07-15, C07-16, C07-18 | config/commodities.yaml:13 | config/, engine/event_calendar.py | M — settle resolver + cycle table | No `ZSK26` literal anywhere. |
| GAP-078 | contract | C07-19, C07-20, C07-21 | n/a — no module | engine/event_calendar.py, config/ | M — FND-aware calendar | Apr 24 < May FND (Apr 30) needed for roll detection. |
| GAP-079 | contract, pricing-model, density | C07-25, C07-26, C07-27, C07-28, C07-29, C07-30, C07-31, C07-35, C07-36, C07-38 | n/a — no module | state/bucket_grid.py, models/ | M — bucket data structures | MECE check, open-ended tail handling, payoff function. |
| GAP-080 | contract, oms | C07-37, C07-51 | validation/sanity.py:53-57 | validation/, oms/ | S — additional clamp gate | `[0, 1]` admits 0/1 which exchange disallows pre-settle. |
| GAP-081 | contract, oms | C07-49, C07-50 | n/a — no module | oms/, validation/ | S — rounding step plus override per contract | Tick-size lookup keyed on contract; $0.01 default, $0.02 override possible. |
| GAP-082 | contract, oms | C07-44, C07-45, C07-52, C07-67, C09-09 | n/a — no module | oms/orders.py (new) | M — Order dataclass + TIF enum + flag set | post_only / reduce_only / buy_max_cost / STP. |
| GAP-083 | contract, inventory | C07-53, C07-54, C07-55, C07-56, C07-58, C07-59, C09-75, C08-86, C08-87 | n/a — no module | state/positions.py, validation/ | M — max-loss aggregator + MM exemption flag | $25k default working assumption. |
| GAP-084 | contract, oms | C07-60, C07-61 | n/a — no module | oms/, validation/ | M — STP modes + wash-trade guard | `taker_at_cross` / `maker`; Rule 5.15. |
| GAP-085 | contract | C07-63, C07-64, C07-86 | n/a — no module | oms/, observability | S — bust review timer | $0.20 No Cancellation Range; 15-minute window. |
| GAP-086 | contract, observability | C07-36, C07-38, C07-77, C07-78, C07-84, C07-85, C07-110 | n/a — no module | settlement/ (new), state/ | L — settlement reconciler + DCO interaction | No DB to write to (cartography). |
| GAP-087 | contract, oms, data-ingest | C07-108 | engine/event_calendar.py:30-38, 76-79 | engine/event_calendar.py | M — register 24/7 soybean session | Currently *wrong*: WTI calendar treats weekends as closed for a 24/7 product. |
| GAP-088 | contract, hedging, pricing-model | C07-82, C07-83, C10-74 | n/a — no module | engine/event_calendar.py, validation/ | M — limit detector + lock-day handler | ~7%-of-price daily limit, semi-annual reset; lock = limit-trip price. |
| GAP-089 | contract, oms | C07-81, C07-22 | engine/event_calendar.py | engine/event_calendar.py | M — holiday set + roll logic | Friday holiday → Rule 7.2(b). |
| GAP-090 | contract | C07-77, C07-78 | n/a — no module | observability, settlement/ | M — outcome poller + review extension | Rule 13.1(d) 11:59 pm ET. |
| GAP-091 | contract | C07-22, C07-23 | n/a — no module | feeds/kalshi/, config/ | M — listener + schema-update path | Rule 7.2 exchange-side adjustments. |
| GAP-092 | contract, oms | C09-12 | n/a — no module | oms/rfq.py (new) | M — RFQ submitter + 100 cap | `POST /communications/rfq`. |
| GAP-093 | contract | C07-115, C07-58, C07-102 | n/a — no module | oms/, config/ | M — broker-routing layer | FCM pre-trade caps; DMM exemption. |
| GAP-094 | contract | C07-57, C07-59, C09-26 | n/a — no module | config/, observability | S — flag + scaling factor | Rule 5.16 PAL. |
| GAP-095 | contract | C07-04 | n/a — no module | feeds/kalshi/ | S — slug builder | Cosmetic. |
| GAP-096 | contract | C07-06 | n/a — no module | feeds/kalshi/ | S — strike-suffix branch | Some products use letter prefixes. |
| GAP-097 | contract | C07-104, C07-105, C07-106, C07-109 | n/a — no module | config/ | S — metadata constants | DCM designation date, 17 CFR Parts. |
| GAP-098 | contract | C07-114 | n/a — no module | settlement/, treasury/ (new) | M — interest accrual on idle cash | Rule 8.1 silent. |
| GAP-099 | contract | C07-12, C07-13, C07-113 | n/a — no module | feeds/kalshi/, state/bucket_grid.py | M — `market_lifecycle_v2` listener | Rule 40.2(a) clarifications. |
| GAP-100 | contract, data-ingest, strategy | C07-15, C07-21, C07-112, C03-87 | config/commodities.yaml:58-60 | config/commodities.yaml, models/registry.py | S — schema fill-in | Soy is `stub: true` only. |
| GAP-101 | hedging, pricing-model | C08-71, C08-72, C08-75, C08-76 | models/gbm.py, models/base.py:44-52 | models/, engine/pricer.py | M — closed-form Δ/Γ/vega adders to TheoOutput | `φ(d₂)/(Sσ√τ)` is one numba-jitted line away. |
| GAP-102 | hedging, inventory | C08-73, C10-60 | n/a — no module | engine/quoter.py, state/positions.py, hedge/ (new) | M — aggregator over bucket positions | Σᵢ qᵢ Δᵢᴷ / N_ZS. |
| GAP-103 | hedging, inventory | C10-61, C10-67 | n/a — no module | hedge/ | S — single threshold | `\|Δ^port\| ≥ 1` ZS. |
| GAP-104 | hedging, oms | C08-108, C09-28, C10-80 | feeds/__init__.py | feeds/fcm/ (new), oms/ | XL — FCM client (IB / AMP / Tradovate) | The Milestone-3 deliverable. |
| GAP-105 | hedging | C08-77, C08-78, C10-62, C10-63, C10-64, C10-65 | state/iv_surface.py | hedge/, density pipeline | L — vertical-spread builder + surface query | Depends on GAP-042 (strike axis). |
| GAP-106 | hedging | C08-81, C10-66 | state/basis.py:1-49 | state/basis_hedge.py (new) or state/basis.py extension | M — three-component basis tracker | Same name `basis` collides with Pyth↔CME drift. |
| GAP-107 | hedging | C08-83, C08-84, C08-85, C09-78 | n/a — no module | hedge/, state/ | L — SPAN model + tripwires | C08-85 says Kalshi leg is binding capital constraint. |
| GAP-108 | hedging, data-ingest | C09-28 | feeds/pyth_ws.py:1-145 | feeds/cme/ (new) | L — second feeds/ module | FCM bundles CME Globex L1. |
| GAP-109 | hedging, observability | C09-55, C09-57 | n/a — no module | observability, hedge/ | S — round-trip timer + region pin | Tens-of-ms to a few seconds. |
| GAP-110 | hedging, observability | C09-56, C09-61 | audit_A_cartography.md:84-85, 98-100 | deploy/ (new) | M — process topology spec | Three instances under $500/mo target. |
| GAP-111 | hedging, backtest | C08-92 | n/a — no module | hedge/, backtest/ | S — fee table | Affects backtest fidelity. |
| GAP-112 | hedging, oms, strategy | C10-72, C10-73 | engine/event_calendar.py:30-38, 76-79 | engine/event_calendar.py, oms/, hedge/ | M — closed-detector + quote-pull | Fri 13:20 CT → Sun 19:00 CT. |
| GAP-113 | hedging, inventory | C10-74 | n/a — no module | hedge/, scenario/ (new) | M — scenario harness | Compounded with GAP-088. |
| GAP-114 | hedging | C02-86 | n/a — no module | feeds/, hedge/ | L — cross-asset feed + selector | ZC/ZM/ZL/MATIF/Dalian. |
| GAP-115 | hedging | C02-87 | calibration/__init__.py | calibration/ | M — empirical hedge-ratio estimator | `calibration/` empty per cartography. |
| GAP-116 | inventory, hedging, oms, pricing-model | C02-03, C02-07, C09-76 | n/a — no module | state/positions.py (new) | L — new state surface keyed by (event_ticker, bucket) | Foundational; everything inventory-side hangs off it. |
| GAP-117 | inventory, oms | C02-03 | n/a — no module | state/positions.py, oms/ | M — fill events + cash account | dq, dX dynamics. |
| GAP-118 | inventory, hedging, observability | C08-88, C08-109 | validation/sanity.py | validation/portfolio.py (new), engine/quoter.py | M — book-level cap | The single binding risk constraint. |
| GAP-119 | inventory, contract | C09-76, C07-53, C07-54 | n/a — no module | state/positions.py, validation/ | M — per-bucket signed-exposure tracker | $-denominated vs Appendix-A limit. |
| GAP-120 | inventory, oms, observability | C08-109, C02-91 | validation/sanity.py | validation/portfolio.py, engine/quoter.py | L — multi-input gate (caps + scenarios) | Pipeline stage J. |
| GAP-121 | inventory, backtest, observability | C08-89, C10-74 | n/a — no module | scenario/ (new), backtest/ | L — three named scenarios + harness | WASDE-day, weather-shock, expiry-day. |
| GAP-122 | inventory, oms | C09-77 | n/a — no module | oms/orders.py | S — per-request cap | Order-builder field. |
| GAP-123 | inventory, pricing-model | C02-33 | models/gbm.py, models/registry.py | models/, state/ | L — multi-asset HJB | Theoretical underpinning of GAP-004. |
| GAP-124 | inventory, pricing-model | C08-47, C08-48, C10-53, C10-54 | n/a — no module | engine/quoter.py, state/ | L — adjacent-bucket skew propagation | Cross-inventory edge. |
| GAP-125 | inventory, contract | C08-82, C07-110 | n/a — no module | state/positions.py | M — collateral utilisation accounting | Kalshi cash-collateral model. |
| GAP-126 | inventory, pricing-model | C02-57, C04-13, C05-12, C05-19, C10-35, C10-36 | state/basis.py:19-48 | state/basis.py or state/forward_curve.py (new) | M — curve upgrade | Currently a per-commodity scalar. |
| GAP-127 | inventory | C02-55 | n/a — no module | calibration/, models/ | L — convenience-yield model | Macro inventory; nice-to-have. |
| GAP-128 | inventory | C02-54 | n/a — no module | calibration/, models/ | L — Deaton–Laroque non-negativity | Macro inventory; nice-to-have. |
| GAP-129 | inventory, hedging | C08-85 | n/a — no module | hedge/, state/ | M — capital allocator | Capital comparison Kalshi vs CME hedge. |
| GAP-130 | inventory, observability | C10-79 | n/a — no module | config/, validation/ | S — config-driven cap interface | $500/$5k Milestone-2 sandbox values. |
| GAP-131 | oms, observability, data-ingest | C07-93, C09-13, C08-110 | feeds/pyth_ws.py:1-20, 130 | feeds/kalshi/ws.py (new) | L — multiplexed WS consumer | `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`. |
| GAP-132 | oms, contract | C07-92, C09-09, C09-21 | pyproject.toml:16, audit_A_cartography.md:248-249 | feeds/kalshi/, oms/ | M — endpoint binding | POST/DELETE/amend/decrease/batch. |
| GAP-133 | oms | C09-10, C10-47 | n/a — no module | state/book.py (new), oms/ | M — local resting book + queue cache | Required to act on queue position. |
| GAP-134 | oms, pricing-model | C08-43, C10-50, C02-84 | n/a — no module | oms/, calibration/ | M — fill stream consumer + markout calc | Live calibration of (Aᵢ, kᵢ). |
| GAP-135 | oms, observability, hedging | C09-11, C09-79, C10-80 | validation/__init__.py, audit_A_cartography.md:81-83 | recon/ (new), state/, feeds/fcm/ | L — three-times-per-session reconciler | Open / intraday / EOD. |
| GAP-136 | oms, observability | C09-80 | audit_A_cartography.md:113-115 | recon/, state/ | M — single reconciliation table + persistent store | DuckDB + Parquet per C09-64. |
| GAP-137 | oms | (file question: idempotency) | n/a — no module | oms/orders.py | S — client-order-ID dedupe | Not addressed in research as a tagged claim. |
| GAP-138 | oms | C09-21, C10-48 | n/a — no module | oms/orders.py | S — amend path | Cancel-and-replace race avoidance. |
| GAP-139 | oms, pricing-model | C08-98, C10-17 | engine/pricer.py:45-90 | oms/, engine/quoter.py | M — pull-wait-refit-repost protocol | 30–60s before release. |
| GAP-140 | oms | C08-52 | n/a — no module | calibration/, oms/ | M — μᵢ/(μᵢ+νᵢ) intensities | Required for queue-aware quoting policy. |
| GAP-141 | oms | C08-51, C10-29 | n/a — no module | engine/quoter.py | L — queue-reactive overlay | Cont–de Larrard / HLR transfer. |
| GAP-142 | oms | C07-67 | n/a — no module | oms/, fees/ (new) | S — cancel-vs-fill economics | Couples to GAP-007. |
| GAP-143 | oms | C09-06, C09-81 | pyproject.toml:9-20 | feeds/kalshi/fix.py (new) | XL — FIX engine + sessions | Premier+ tier; nice-to-have. |
| GAP-144 | oms | C07-46 | n/a — no module | oms/orders.py, observability | S — count tracker | Only matters once quoter is wired. |
| GAP-145 | oms, inventory, observability | C10-79 | n/a — no module | engine/quoter.py, validation/ | M — Milestone-2 contract | ≥4¢ each side; amend-not-cancel; kill-switch. |
| GAP-146 | backtest | C10-77, C10-78, C10-82 | grep -rn -i backtest --include="*.py" returns one docstring at state/tick_store.py:10 | backtest/ (new) | XL — full backtest harness | The strategic gating milestone. |
| GAP-147 | backtest, density, pricing-model | C10-77, C10-OQ-01, C10-OQ-10 | calibration/, audit_A_cartography.md:213-231 | backtest/, calibration/, density pipeline | XL — historical chain pull + SVI + Figlewski + score loop | Milestone 0; the gating milestone of Phase 10. |
| GAP-148 | backtest, observability, data-ingest | C09-62, C09-63, C09-23, C09-24 | state/tick_store.py:31-66, audit_A_cartography.md:108-115 | backtest/tape/ (new), feeds/, S3 sink | L — three forward-only capture writers | Permanent loss of every uncaptured day. |
| GAP-149 | backtest, oms | C09-25 | feeds/__init__.py | backtest/paper/ (new), oms/ | L — sandbox demo + paper-trading layer | Demo validates signing only. |
| GAP-150 | backtest | C09-64, C09-65, C09-66, C09-68 | pyproject.toml:9-20 | pyproject.toml, backtest/, recon/ | M — pin DuckDB + pyarrow + httpfs | Recommended substrate not adopted. |
| GAP-151 | backtest, observability | C08-111 | engine/event_calendar.py:1-110 | backtest/attribution.py (new), recon/ | L — weekly P&L attribution | Edge / inventory / hedge / fees → (Aᵢ, kᵢ, γ). |
| GAP-152 | backtest, pricing-model, contract, oms | C08-91, C04-08, C04-09, C05-38 | n/a — no module | backtest/, fees/, models/ | S — fee table plus subtraction | Without fees every gross number overstates by ≥250 bps. |
| GAP-153 | backtest, data-ingest | C05-60 | state/tick_store.py:31-66 | feeds/usda/, state/ | M — PIT discipline on USDA features | Default look-ahead trap. |
| GAP-154 | backtest | C05-24, C09-23 | n/a — no module | backtest/, observability | M — survivorship-aware universe | Forward-only capture. |
| GAP-155 | backtest | C05-33, C05-70, C05-72, C05-73, C05-75 | n/a — no module | backtest/ | M — turnover counter + capacity penalty + Sharpe discount | Discount for live-money planning. |
| GAP-156 | strategy | C04-03, C04-05, C04-06, C04-08, C04-09, C04-77, C05-38 | config/commodities.yaml:58-60, audit_A_cartography.md:213-231 | feeds/cme/, models/, calibration/ | L — ZS/ZM/ZL universe + GPM signal + filter | Underlier set restricted to WTI. |
| GAP-157 | strategy | C04-11, C04-12, C04-13, C04-14, C04-16, C04-17 | n/a — no module | feeds/cme/, calibration/ | L — calendar-spread universe + state classifier | Old-vs-new-crop bellwether. |
| GAP-158 | strategy | C04-18, C04-19, C04-20, C04-21 | n/a — no module | feeds/cme/, calibration/ | M — cross-symbol ratio + USDA Acreage gate | ZSN/ZCN. |
| GAP-159 | strategy | C05-01, C05-02, C05-03, C05-04, C05-05, C10-43 | state/tick_store.py:57-66 | state/tick_store.py (history reader), strategy/ (new) | M — MA/Donchian/TSMOM signals on existing ring | TickRing has history but no reader. |
| GAP-160 | strategy | C05-14, C05-17, C05-18 | config/commodities.yaml:6-30 | feeds/, strategy/ | L — multi-commodity sort | Erb-Harvey / Fuertes-Miffre-Rallis. |
| GAP-161 | strategy | C05-26, C05-29, C05-30, C05-31, C05-72, C05-73, C05-74 | config/commodities.yaml, state/tick_store.py:31-66, models/base.py:32-41 | feeds/, state/, models/, strategy/ | L — universe shape change | TickStore keys by single commodity; TheoInputs.spot is scalar. |
| GAP-162 | strategy | C04-61, C04-62, C04-63, C02-58, C02-59 | config/commodities.yaml:11 | calibration/, strategy/ | M — OI ingest + roll detector | `cme_roll_rule` is WTI-only. |
| GAP-163 | strategy | C04-66-C04-69, C04-92, C04-93 | n/a — no module | feeds/cot/, strategy/, calibration/ | M — COT-based signals + Kelly sizing | Couples to GAP-059. |
| GAP-164 | strategy | C04-42-C04-45, C04-86-C04-91 | n/a — no module | feeds/weather/, feeds/sam/, strategy/ | L — ENSO + soil-moisture + 5-yr basis state | Couples to GAP-055/057. |
| GAP-165 | strategy | C04-95-C04-107 | n/a — no module | strategy/, observability | L — per-trade indicators + sizing rules | ATR/ADX/EMA/MACD; Brandt/Turtle/Parker/Raschke. |
| GAP-166 | strategy, oms | C04-94, C04-82 | engine/pricer.py:45-90 | strategy/, observability | M — rolling-window event detector | Per-tick reprice has wrong primitive. |
| GAP-167 | strategy | C04-31, C04-33, C04-34, C04-35, C04-37, C04-82, C04-83, C04-84, C04-85 | n/a — no module | strategy/, calibration/ | M — release-window detector + σ overlay + NAV sizing | WASDE 48h fade rule. |
| GAP-168 | strategy, pricing-model | C10-44, C10-45, C10-46 | n/a — no module | calibration/, strategy/ | M — stocks-to-use regime classifier | Required gate for §2.1 weather→density. |
| GAP-169 | strategy | C04-47, C04-48, C04-54-C04-60, C10-26 | state/basis.py | state/, strategy/ | M — fair-value overlay + farmer-hedge prior | Cash basis layer. |
| GAP-170 | strategy | C04-25, C04-71, C04-72 | n/a — no module | feeds/, strategy/ | M — RFS/RVO/RIN ingest + oilshare signal | Policy/news layer. |
| GAP-171 | observability, contract | C09-71, C09-72, C10-79 | audit_A_cartography.md:108-115, 246-249 | feeds/kalshi/, oms/, observability | M — wire two endpoints + group trigger | Depends on GAP-071. |
| GAP-172 | observability, inventory, oms, hedging | C09-73 | engine/scheduler.py:21-26, 36-56, feeds/pyth_ws.py:138-145, audit_B_engine-scheduler.md:539-546 | observability, engine/scheduler.py, state/positions.py, feeds/ | L — four-trigger watchdog + transport | No producer, no consumer, no transport, no destination endpoint. |
| GAP-173 | observability, data-ingest, backtest | C09-24, C09-63, C09-62 | state/tick_store.py:31-66 | tape/ (new), feeds/, S3 sink | L — Kalshi+CME+fundamentals capture | Unique among gaps: irreversible asset loss per day uncaptured. |
| GAP-174 | observability | (no specific C-id; pyproject.toml red flag) | pyproject.toml:20, audit_A_cartography.md:246-249, feeds/pyth_ws.py:31, 131, 144 | observability, feeds/, every consumer | M — swap stdlib for structlog `BoundLogger`; configure handlers | `structlog` declared but unused; only two stdlib log calls exist. |
| GAP-175 | observability | C10-81 | pyproject.toml:9-20 | pyproject.toml, observability, every consumer | M — `prometheus_client` + per-stage histograms/counters | M4 ops hardening. |
| GAP-176 | observability, hedging | C09-58, C09-59 | benchmarks/run.py:13, 68-70, 204-205, engine/pricer.py:42-89, audit_A_cartography.md:294-296 | engine/pricer.py, observability | M — per-stage timer + histogram emitter | Five-leg budget; one leg measured today, only at offline-pytest time. |
| GAP-177 | observability | C10-81 | pyproject.toml | deploy/ (new), observability | L — Grafana dashboards + alert routing | M4 ops hardening. |
| GAP-178 | observability, oms | (Red Flag 5) C09-79 | engine/scheduler.py:21-26, 36-59, audit_B_engine-scheduler.md:191-217, 547-551 | engine/scheduler.py, every producer | M — wire producers + add safety priorities | Dead at the import-graph level. |
| GAP-179 | observability, oms | C02-91; ambiguity A1 in audit_D_observability.md | validation/sanity.py:32-67, engine/pricer.py:89, audit_B_validation-sanity.md:509-515 | validation/, engine/quoter.py | S — policy decision + emitter | Quote-drop / market-suspend / page / restart-model are mutually exclusive. |
| GAP-180 | observability | C09-73(iv) | feeds/pyth_ws.py:138-145, audit_B_feeds-pyth.md:469-473 | feeds/pyth_ws.py | S — windowed counter | Resets per connection, not per minute. |
| GAP-181 | observability | C10-81 | audit_A_cartography.md:96-100 | deploy/, observability | L — failover topology | Single-process layout. |
| GAP-182 | observability | C10-82 | tests/test_benchmarks.py, pyproject.toml:35-38 | tests/, backtest/ | S — pytest markers + threshold loader | Discipline more than code. |
| GAP-183 | observability, strategy | C05-66 | engine/event_calendar.py:30-38 | calibration/, observability | M — VPIN + USDA-window withdrawal trigger | Diagnostic trigger. |
| GAP-184 | observability | C06-86 | audit_A_cartography.md:108-115 | feeds/cme/ (new), recon/ | M — CME Daily Bulletin parser | Reconciliation/calibration input. |
| GAP-185 | observability | C10-51, ambiguity A4 in audit_D_observability.md | calibration/__init__.py, .gitignore:21-22, audit_A_cartography.md:289-292 | calibration/ | M — producer + schema + freezing semantics | Format implied by `.gitignore`, not by any producer. |

---

## 3. Cross-cutting themes

Five themes span the topics. Each is a pattern visible across multiple
D-files; together they explain why the register has the shape it has.

### 3.1 The Kalshi-side surface is the foundational blocker

Roughly a third of the register's blocker rows trace back to a single
absence: there is no Kalshi REST/WS client. GAP-071 (the client),
GAP-072 (RSA-PSS signing), GAP-073 (rate-limit pacer), GAP-074 (ticker
schema), GAP-075 (bucket-grid ingest), GAP-082 (order types and TIFs),
GAP-086 (settlement), GAP-131 (WS multiplex), GAP-132 (REST endpoints),
GAP-135 (reconciliation), GAP-148/173 (tape capture), and GAP-171/172
(kill switch) all hang off it. Cartography Red Flag 2
(`audit_A_cartography.md:243-245`) names it directly. The four
declared-but-unused deps (`httpx`, `structlog`, `python-dateutil`,
`pytz`, Red Flag 3) suggest in-repo intent. Until at least the
read-side of this surface exists, every observability primitive layered
on top of it (heartbeat-fail kill, three-times-per-session
reconciliation, tick-to-quote latency histogram) has no foothold; and
until at least one tape sink exists (S3 + Parquet), every uncaptured
day costs an asset that cannot be reconstituted (GAP-173).

### 3.2 The pricing layer is built around the wrong epistemology

The live model emits `P(S_T > K) = Φ(d₂)` under a single-name GBM with
an externally-primed scalar σ — a *theoretical* density at strikes,
not an *empirical* RND from a CME option surface. GAP-006 captures
this shift: the gap is not just "constant σ is too thin" (that is
GAP-008/GAP-009), it is "model-implied vs market-implied" — a kind
mismatch. Every downstream Kalshi-side claim presumes the latter
(GAP-036 BL identity, GAP-037 SVI, GAP-041 Figlewski tails, GAP-042
strike-axis IV surface, GAP-043 bucket integration, GAP-046 CME chain
ingest). The pricer's TheoOutput shape (`(strikes, probabilities,
as_of_ns, source_tick_seq, model_name, params_version)` at
`models/base.py:44-52`) was designed for the upper-tail-digitals
contract; growing it into a Yes-price-per-bucket vector requires either
a subclass or a contract redefinition.

### 3.3 The "schema declared, no consumer" pattern is concentrated in events and calibration

The repository carries multiple YAML/code declarations whose consumers
have not been written. The most consequential cluster is the event
calendar: `config/commodities.yaml:24-28` declares
`event_calendar[].{name, day_of_week, time_et, vol_adjustment}`, and
`engine/scheduler.py:21-26` declares `Priority.EVENT_CAL = 30`, and
neither has a consumer (GAP-019, GAP-053, GAP-178). The same shape
appears in `calibration/`: `.gitignore:21-22` excludes
`calibration/params/*.json`, the package is otherwise empty, and the
intended consumer of nightly calibration JSON is unwritten (GAP-185,
GAP-115, GAP-134). And again at the IV surface: the docstring at
`state/iv_surface.py:1-12` claims "the upgrade is additive" but the
public reader `atm(commodity, *, now_ns) -> float` cannot grow strike
or expiry parameters without a signature change (GAP-042). These are
not "we forgot to write the producer" cases — they are "the schema
shape is right, the consumer commitment is not yet made" cases. They
land mostly as `partial`/`major` in the register and they would
collapse to `S`-effort wiring tasks if the producer side existed.

### 3.4 Universe shape is wrong: WTI-only where soybeans are the target

`README.md:3` describes a "Live Kalshi commodity theo engine"; the
research targets a Kalshi `KXSOYBEANW` market on the CBOT soybean
complex; the live code is WTI Pyth-only with thirteen stub commodities
(`config/commodities.yaml:34-85`). Red Flag 14 records that any
non-WTI commodity raises `NotImplementedError` at
`engine/event_calendar.py:98` the moment the pricer asks for its τ.
The misalignment compounds: `TickStore` keys per single commodity,
`TheoInputs.spot` is a single scalar, `engine/pricer.py:47` signature
is `commodity: str` scalar — there is no portfolio object. GAP-100
captures the soy-stub itself; GAP-156 / GAP-157 / GAP-158 / GAP-160 /
GAP-161 capture the strategy-side consequences (no crush spread, no
calendar-spread book, no bean/corn ratio, no carry sort, no
cross-sectional momentum). The universe shape is not a bug to patch
in the engine — it is a deliberate Deliverable-1 scoping that has not
yet flipped over to the research target.

### 3.5 "Same word, different mechanic" name collisions hide gaps

Three significant name collisions show up across the register and each
hid a gap during the audit. First, `state/basis.py` (Pyth↔CME
annualised drift used inside the GBM forward) is *not* the
hedge-leg basis the C08-81 / C10-66 cluster names (Kalshi-snapshot vs
CME-option-reference): same word, different object — GAP-106 is
classed `wrong` for that reason rather than `partial`. Second,
`engine/event_calendar.py` is a τ-years calculator on trading-hour
sessions; the C08-97 / C10-17 event calendar wants per-release κ
multipliers. Same noun, different artifact (GAP-019, GAP-049, GAP-053).
Third, `validation/sanity.py:53-57` clamps `[0, 1]` (correct for a
probability output, wrong for a Kalshi quote which lives in
`[0.01, 0.99]` pre-settlement): same gate, different domain (GAP-080).
A reader skimming the cartography for "basis" or "event_calendar" or
"sanity" would conclude these mechanics exist; they do not, and the
collision is a meaningful audit observation in its own right.

### 3.6 The fail-safe pattern is partial and theo-scoped, not book-scoped

The pricer raises `StaleDataError` / `InsufficientPublishersError` /
`SanityError` rather than publishing a wrong number — a real fail-safe
discipline (`engine/pricer.py:62-75`, `validation/sanity.py:38-68`,
`README.md:63`). The pattern is correct as far as it goes. But it is
*theo-correctness* fail-safe, not *book-risk* fail-safe: it kills one
quote, not the engine; it operates on input invariants, not on book
exposure or hedge connectivity. The C09-73 four-trigger kill-switch
(GAP-172) — aggregate signed-delta breach, intraweek PnL drawdown,
CME hedge heartbeat fail, Kalshi WS reconnect storm — is a different
mechanism layered on top. The existing fail-safe is the right
*pattern* for the future kill-switch to reuse, but the gap (no global
state, no re-arm protocol, no consumer for `SanityError` at the
publish boundary, GAP-179) is real.

---

## 4. Counts and summary statistics

### 4.1 Gaps by topic and severity

| Topic | blocker | major | minor | nice-to-have | Total |
|---|---|---|---|---|---|
| pricing-model | 10 | 18 | 7 | 0 | 35 |
| density | 6 | 8 | 1 | 0 | 15 |
| data-ingest | 3 | 9 | 5 | 3 | 20 |
| contract | 17 | 7 | 3 | 3 | 30 |
| hedging | 4 | 6 | 3 | 2 | 15 |
| inventory | 6 | 6 | 1 | 2 | 15 |
| oms | 4 | 8 | 1 | 2 | 15 |
| backtest | 4 | 4 | 2 | 0 | 10 |
| strategy | 0 | 9 | 6 | 0 | 15 |
| observability | 3 | 8 | 4 | 0 | 15 |
| **Total** | **57** | **83** | **33** | **12** | **185** |

### 4.2 Gaps by topic and effort tier

| Topic | S | M | L | XL | Total |
|---|---|---|---|---|---|
| pricing-model | 3 | 17 | 10 | 5 | 35 |
| density | 2 | 7 | 5 | 1 | 15 |
| data-ingest | 2 | 8 | 8 | 2 | 20 |
| contract | 9 | 19 | 1 | 1 | 30 |
| hedging | 3 | 7 | 4 | 1 | 15 |
| inventory | 2 | 6 | 7 | 0 | 15 |
| oms | 4 | 7 | 3 | 1 | 15 |
| backtest | 1 | 4 | 3 | 2 | 10 |
| strategy | 0 | 9 | 6 | 0 | 15 |
| observability | 3 | 8 | 4 | 0 | 15 |
| **Total** | **29** | **92** | **51** | **13** | **185** |

### 4.3 Gap-class distribution

| Gap class | Count |
|---|---|
| missing | 167 |
| partial | 9 |
| wrong | 8 |
| divergent-intentional | 1 |
| **Total** | **185** |

(The dominant `missing` count reflects that the codebase is correctly
described by Phase D as a "pricing engine, not a market-making
system": every Kalshi-side mechanic, hedging mechanic, inventory
mechanic, and observability mechanic is a greenfield gap rather than
a wrong-implementation gap. The `partial` rows concentrate on the
schema-declared-no-consumer pattern (theme 3.3); the `wrong` rows on
the name-collision pattern (theme 3.5).)

### 4.4 D-file `already-good` rows (informational, not in register)

Carried for completeness, *not* added as gaps. C08-07 (Kalshi has no
discounting — incidental match), C08-09 (digital as call-spread limit
— code uses closed-form correctly), C08-57/C08-58 (LMSR does not
transfer — correctly absent), C09-54 (no co-location needed —
vacuously satisfied), C02-88 (pricing/hedging separation — correctly
respected), C02-89 (pricing models do not specify capital deployment —
correct scope match), C02-91 (when to stop quoting — fail-safe
pattern adjacent). Across all ten D-files the total is eight
already-good rows and they were the only D-rows excluded.

---

## 5. Appendix A — Open research questions and kill criteria (from C10)

Reproduced verbatim from `audit_C_phase10_strategy_synthesis.md`.
These are not audit gaps; they are open empirical questions and
project-level kill criteria carried through as Phase F input.
Original IDs preserved.

### A.1 Open research questions (`C10-OQ-NN`)

| ID | Question |
|---|---|
| C10-OQ-01 | Empirically estimate the correlation between the ZS front-month risk-neutral density (from CME options) and Kalshi bucket implied probabilities at various times to expiry; daily snapshots over the first 12–24 settled `KXSOYBEANW` Events; per-bucket residuals; correlation as a function of moneyness and time-to-expiry. Sets the §2.4 measure-overlay calibration. |
| C10-OQ-02 | Quantify the favorite–longshot bias on `KXSOYBEANW` specifically and compare to Whelan (2025); bucket-by-bucket realized-vs-quoted hit rate on the first 24 settled Events; if monotonic in quoted Yes price, the measure overlay is a single-parameter shrinkage. |
| C10-OQ-03 | Estimate the empirical fill-intensity function λ_i(δ) on Kalshi bucket quotes by bucket location (ATM vs tail), time-of-day (24/7 including weekends), and proximity to a USDA release. The Avellaneda–Stoikov / GLFT spread formulas need this to size δ. |
| C10-OQ-04 | Measure realized post-trade markout (1m, 5m, 30m) on Kalshi fills around scheduled events (WASDE, ESR, Crop Progress) versus quiet windows. Confirms or refutes the §5 adverse-selection prediction. |
| C10-OQ-05 | Compute the empirical cross-bucket probability covariance Σ_ij intraday and compare to the RND-perturbation-implied covariance. If empirical Σ diverges substantially from model Σ, the Cartea–Jaimungal cross-inventory term is mis-specified. |
| C10-OQ-06 | Measure the Kalshi-vs-CME-options reference-price basis in cents historically, conditional on the Appendix A specification. Until Appendix A is in hand, propagate as a configuration uncertainty. |
| C10-OQ-07 | Test whether bucket Yes prices sum to 1.00 in practice or whether persistent intraweek arbitrage slack exists; if so, characterize size and persistence. A direct measure of LMSR-like consistency under a CLOB. |
| C10-OQ-08 | Compare Polymarket and Kalshi prices on equivalent commodity contracts where overlap exists; whether the 12–20% monthly cross-venue arbitrage rate cited in public guides applies to ZS-referenced products is empirically open. |
| C10-OQ-09 | Calibrate the price-vs-yield elasticity in the §2.1 weather pipeline at different stocks-to-use regimes (tight vs loose); Roberts–Schlenker provides the asymptotic 0.1; in-sample calibration should refine. |
| C10-OQ-10 | Quantify the marginal economic value of Figlewski GEV tails versus a crude lognormal tail extrapolation on the Kalshi open-ended end buckets, measured by realized P&L on tail-bucket trades over a settled-year window. |
| C10-OQ-11 | Profile the seasonality of Kalshi bucket-grid width: do tail buckets carry more probability mass in the U.S. June–August window and the South American January–February window than in October–November? |
| C10-OQ-12 | Characterize the Kalshi Market Maker Program quoting obligations (uptime, spread cap, minimum size) by direct application or by inference from observed bid-ask of likely MMs in the strip; estimate rebate value at typical fill volumes. |

### A.2 Kill criteria (`C10-KC-NN`)

| ID | Criterion |
|---|---|
| C10-KC-01 | *Milestone 0 fails*: SVI / Figlewski RND-implied bucket probabilities, after a measure overlay calibrated on Whelan-style favorite-longshot assumptions, miss the realized Kalshi outcomes by more than the ~2¢ round-trip fee on more than 50% of buckets across 12+ settled Events. The CME option surface does not contain enough information to price the Kalshi grid better than fees, and no quoting strategy can profit. |
| C10-KC-02 | *Milestone 1 fails*: simulated would-quote P&L is not consistently positive (median weekly P&L < 0 over four settled weeks) at the realistic fee schedule, or rate-limit saturation prevents the would-quote engine from re-pricing during release windows. Either fact eliminates the structural opportunity. |
| C10-KC-03 | *Milestone 2 fails*: realized markout on actual fills exceeds the estimated edge net of fees on the majority of buckets — informed counterparties are routinely picking off quotes faster than the engine can defend. Without an MM Agreement (unavailable to a new participant), this is fatal. |
| C10-KC-04 | *Milestone 3 fails*: hedge slippage plus basis P&L plus snapshot-timing P&L exceeds the gross quoting edge produced by Milestone 2, leaving net negative P&L. The CME hedge cannot be made cheap enough to support the Kalshi book. |
| C10-KC-05 | *Structural failure*: Kalshi Appendix A reveals a reference specification (e.g., a non-CME source, a VWAP that cannot be replicated from public CBOT data, a roll rule that discards short-dated weekly options) that breaks the Breeden–Litzenberger pipeline at its root. |
| C10-KC-06 | *Liquidity failure*: per-bucket queue depth and trade arrival on `KXSOYBEANW` over four consecutive Events remain below a level at which queue-position-aware quoting matters (e.g., sub-50 contracts top-of-book on most buckets), making the FIFO microstructure edge irrelevant. |
| C10-KC-07 | *Regulatory failure*: a CFTC action, exchange rule change, or fee surcharge materially alters the Phase 7 / Phase 8 / Phase 9 cost structure. |

---

## 6. Appendix B — Open questions for maintainers, by D-topic

The following are reproduced verbatim from each Phase D file's "Open
questions for maintainers" section, with the source-file path
preserved so a Phase F reader can return to context. Items are
not gaps and carry no GAP-id.

### B.1 Pricing-model — source `audit/audit_D_pricing_model.md` §5

1. Is the C02 / C08 / C10 corpus the spec the live code is being built toward, or is it research input that the system may decline to implement?
2. Is `basis_drift` a carry term, an alpha term, or both?
3. Which of the four commented-out builders in `models/registry.py:34-37` (`jump_diffusion`, `regime_switch`, `point_mass`, `student_t`) is next?
4. Is the σ-as-scalar interface a deliberate Deliverable-1 simplification or the long-term shape?
5. Is there an architectural plan for the Kalshi side of the system?
6. Is the `engine/scheduler.py` skeleton (with `IV_UPDATE`, `BASIS_UPDATE`, `EVENT_CAL` priorities at lines 21-26) intended to become the producer-side wiring for the missing surfaces?
7. What is the expected fill-intensity calibration source?
8. Is the choice of GBM (constant σ) inside `models/gbm.py:35-42` intended to remain the default for all CME commodities, or is it only a baseline for soybean's `KXSOYBEANW` weekly density?
9. Is `params_version` intended to do real work?
10. Where is the Kalshi position / inventory state expected to live?

### B.2 Density — source `audit/audit_D_density.md` §5

1. Is `TheoOutput.probabilities` intended to become a Yes-price-per-bucket vector, or is the integration to bucket probabilities supposed to live downstream of `model.price(...)`?
2. Where is the CME option-chain ingest expected to land?
3. Does `params_version` carry the SVI calibration vintage, or is a separate calibration-state object planned?
4. What is the intended representation of bucket edges?
5. Will limit-day censorship (C02-76, C02-77, C07-83) be a separate adjustment layer, or is it intended to be folded into σ (a downward-bias correction on the IV surface)?
6. Should the favorite–longshot / measure-overlay tilt (C08-39, C08-104, C10-07) be a per-commodity scalar, a per-bucket scalar, or a parametric function of bucket midprice?
7. What is the precise edge-inclusivity rule the engine will adopt at bucket boundaries?
8. How will WASDE-day spread-multiplier widening (C10-14, C10-16, C10-18, C02-63) be parametrized — as event-keyed multipliers on the RND variance, on bucket spreads, or both?
9. The `pricer.reprice_market` budget at `tests/test_benchmarks.py:55-88` is 50 µs end-to-end. C09-58 budgets 40–60 ms tick-to-quote inclusive of an "optional density refresh." Is the density refresh expected to live inside `reprice_market`, or asynchronously in a separate task with the pricer reading a cached RND?
10. C08-118 (sum-to-1 in practice on Kalshi) and C07-39 (sum-to-1 as a consistency check) imply a runtime assertion. Is the assertion meant to be hard (raise) or soft (log/widen)?

### B.3 Data-ingest — source `audit/audit_D_data_ingest.md` §5

1. Is the soybean complex (ZS / ZM / ZL) intended to ship through Pyth Hermes or through CME MDP 3.0 + Databento per C03-08 / C09-29?
2. If Kalshi `KXSOYBEANW` is the trading venue, is the missing Kalshi REST/WS/RSA-PSS surface (C09-01-C09-18) deferred or is the project not building toward Kalshi?
3. How is the ingest-side latency between Hermes `publish_time` and the parser's first touch supposed to be measured?
4. What is the intended USDA event-clock plumbing? C06-27 prescribes a widen-or-pull risk gate; the codebase has no quote to widen.
5. Is the no-backfill behaviour on Pyth reconnect a deliberate choice or an oversight? If deliberate, should `config/pyth_feeds.yaml:8`'s `hermes_http` line be removed?
6. Is `num_publishers` defaulting to 0 (`feeds/pyth_ws.py:112-115`) intended as fail-closed or as a placeholder?
7. Is `engine/scheduler.py` a forward declaration matching the docstring at `engine/scheduler.py:8-9`, or has the synchronous Pricer made it obsolete?
8. Are weather (C03-46-C03-49, C09-45-C09-50, C10-10) and logistics (C09-51-C09-53) part of the MVS for this codebase or deferred beyond the Kalshi MVS budget?
9. Is per-stream point-in-time semantics (C05-60) on the roadmap?
10. The `feeds/` directory contains exactly one producer; the README at `README.md:39` lists "Pyth, CME, options, Kalshi, macro" as planned. Is the README aspirational, or is the directory expected to grow before the next review?

### B.4 Contract — source `audit/audit_D_contract.md` §5

1. Where does the Kalshi side live? Is it intentionally deferred to a downstream service, or is it a missing in-repo deliverable?
2. Who produces `settle_ns`?
3. Who picks the IV strip?
4. Where does the Kalshi quote-band gate live? Should `validation/sanity.py` host the `[0.01, 0.99]` and tick-size gates?
5. Corridor primitive — model layer or orchestrator? Should the bucket digital `P(ℓ ≤ S_T < u)` be computed in one numba kernel per Event, or composed at the pricer from two half-line calls?
6. What flips the `stub` flag for `soy`?
7. Soybean trading-hours schedule — 24/7 or CBOT-aligned?
8. Where does the fee module live? `engine/`, a new `kalshi/` package, or a future `oms/` layer?
9. Does the unused scheduler set the event vocabulary?
10. Pre-ship acceptance test? Cartography records no CI; given contract handling is presumptively blocker-grade, is there a planned paper-trade test against Kalshi demo with venue-rejection counts as the pass/fail signal?

### B.5 Hedging — source `audit/audit_D_hedging.md` §6

1. Is the absence of a hedging layer intentional, scoped-out for Deliverable 1, or a known gap?
2. Where will per-bucket inventory live — a new `state/positions.py`, inside `engine/pricer.py`, or imported from a Kalshi REST client when one exists?
3. Is `state/basis.py` intended to grow into a multi-component basis tracker, or will the Kalshi-snapshot↔CME-option-reference basis live in a new module?
4. Is `TheoOutput` intended to grow Greeks fields (`delta`, `gamma`, `vega`), or will Greeks live in a parallel `engine/greeks.py`?
5. What is the planned hedge-side connector — Interactive Brokers, AMP, Tradovate?
6. Will `engine/event_calendar.py` be extended to express CBOT soybean sessions, or is the WTI hard-code intentional?
7. Will the C09-73 kill-switch be implemented as four watchdogs on the `engine.scheduler` priority queue, as a single supervisor process, or as Kalshi `DELETE /orders/batch` plus broker IOC-cancel calls?
8. What is the planned reconciliation-table schema (C09-79, C09-80)?
9. Will the C08-88 aggregate-delta cap live in `validation/sanity.py` or in a new `validation/portfolio.py`?
10. Is `calibration/` the intended home for empirical fill-intensity / cross-asset-intensity / Σ-perturbation work?

### B.6 Inventory — source `audit/audit_D_inventory.md` §5

1. Is the "Live Kalshi commodity theo engine" framing on `README.md:3` a forward-looking aspiration or a current-state description?
2. Is the `calibration/` empty package intended to host risk primitives, or only the four jobs the README lists?
3. Will the `event_calendar` YAML's `vol_adjustment` field be wired into a regime-switching spread multiplier, or is it dead config?
4. Is the per-quote raise discipline at `engine/pricer.py:62-75` and `validation/sanity.py:38-68` intended to remain *theo-only*, or will it be promoted to a book-level kill-switch?
5. If a future order client lands, will `buy_max_cost` be enforced at the client wrapper or at a separate risk-gating layer?
6. Should the eventual reservation-price layer ship with a perturbation-based estimator (per C08-105) or a stub identity matrix that is honest about the modelling debt?
7. Phase 10 milestone M2 (C10-79 sandbox caps) defines numerical risk-limit values that would go into a hypothetical risk-gating module. Is the intent to load these from `config/` or to wire them into a Python literal?

### B.7 OMS — source `audit/audit_D_oms.md` §5

1. OMS module ownership — where will the Kalshi REST/WS client live? `feeds/`, alongside `pyth_ws.py`, or a new `oms/` package?
2. `event_calendar` semantics — will the per-release κ-spread / κ-width shaping (C08-97) extend `engine/event_calendar.py`?
3. Reconciliation cadence — will it be driven by `engine/scheduler.py` priorities or by an out-of-process job?
4. STP policy default — `taker_at_cross` or `maker` (C07-60)?
5. Tier choice — which Kalshi rate-limit tier does the design assume?
6. Idempotency contract — will retries on `POST /portfolio/orders` carry a client-order-ID?
7. Kill-switch authorization — in-process scheduler or separate watchdog process?
8. CBOT lock detection ownership — ingest CME L1 or rely on a derived signal from Pyth?
9. Calibration → OMS handshake — where do κ multipliers, trade-through intensities, and queue-arrival models live?
10. FCM vs. self-clear — C07-115 is open in research; the decision constrains pre-trade-risk hooks and the order-size cap surface.

### B.8 Backtest — source `audit/audit_D_backtest.md` §5

1. Milestone-tracker for M0 (C10-77) — is there an external tracker for the Databento → SVI → Figlewski → settled-Kalshi-week pipeline?
2. Private branches — does a separate branch carry `backtest/`, a Kalshi client, or a fee model?
3. Forward-capture status — has the project begun writing the Kalshi tape anywhere external to the repo?
4. Fee table source-of-truth — where will the Kalshi maker/taker schedule live?
5. CME options-chain vendor commitment — is Databento committed?
6. Survivorship strategy on Kalshi — accept forward-only, backfill via per-trade prints, or treat survivorship as out-of-scope?
7. Look-ahead policy on USDA features — PIT API or latest-revision endpoint?
8. Scenario-test home — `benchmarks/`, a new `scenarios/`, `validation/`, or integration tests under `tests/`?
9. P&L attribution stack — pandas, polars, or DuckDB?
10. Validation surface for sum-to-1 — extend `validation/sanity.py`, or live in a separate Kalshi-specific module?

### B.9 Strategy — source `audit/audit_D_strategy.md` §5

1. Is the `engine/scheduler.py` `EVENT_CAL` priority slot intended as a forward-looking placeholder for WASDE / EIA / Crop-Progress release-window logic?
2. `config/commodities.yaml:24-30` lists `vol_adjustment: "strip_event_vol_if_after"` for WTI EIA. Is it intended to feed a future κ_t multiplier?
3. The research targets `KXSOYBEANW` and soybeans; the code is WTI-only. Is the WTI focus intentional early-deliverable scoping, or a divergence?
4. `models/registry.py:32-38` has commented-out slots for `jump_diffusion`, `regime_switch`, `point_mass`, `student_t`. Which is meant to host the measure overlay (C10-12)?
5. Is the bucket-sum invariant (C10-OQ-07) intentionally deferred to a Kalshi-integration layer, or a gap the sanity layer should close?
6. Red flag #8: `feeds/pyth_ws.py:112-115` defaults `num_publishers = 0`; rejection-on-zero — intended hard SLA gate, or placeholder pending replacement?
7. Is the plan to extend `benchmarks/harness.py` and `benchmarks/run.py` to measure end-to-end tick → theo → would-quote → would-fill, or to stand up a separate strategy evaluation pipeline?
8. Several practitioner-lore claims (C04-69, C04-104, C04-106, C04-107) are incompatible as global rules. Is the corpus a buffet or a complete recipe?
9. Is the planned overlay (C10-78 measure-overlay + favorite-longshot bias) a single shrinkage, a per-bucket correction, or something else?
10. `state/basis.py` is a per-commodity scalar; claims C02-57, C04-13, C05-12, C05-19, C10-35, C10-36 all want a curve. Is the upgrade path to extend `BasisModel` or to introduce a separate `ForwardCurve` state class?

### B.10 Observability — source `audit/audit_D_observability.md` §5

1. What is the expected publish destination for the two existing log calls at `feeds/pyth_ws.py:131, 144` in production?
2. Is the `validation/` package intended to host "backtest, Pyth↔CME reconciliation" alongside `sanity.py` per the README, or has the scope been narrowed?
3. What is the intended lifecycle for `engine/scheduler.py`?
4. What is the intended persistent-store substrate for forward-captured Kalshi ticks (C09-24, C09-63) and the reconciliation table (C09-80)?
5. What N (hedge-heartbeat seconds) and K (Kalshi WS reconnects/minute) thresholds are intended for the C09-73 kill-switch?
6. Is `event_calendar[].vol_adjustment` meant to satisfy C08-97's $\kappa^{\text{width}}$, $\kappa^{\text{spread}}$, both, or neither?
7. What is the intended fan-out path for `SanityError` at the publish boundary that does not yet exist?
8. Are the unused dependencies at `pyproject.toml:18-20` (`httpx`, `structlog`, `python-dateutil`, `pytz`) reserved for a near-term Kalshi/REST-client work item, or are they vestiges?

---

*End of `audit_E_gap_register.md`.*
