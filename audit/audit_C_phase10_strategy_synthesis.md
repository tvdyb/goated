# Audit C — Phase 10 Strategy Synthesis: Claim Index

## 1. Source scope

`research/phase_10_strategy_synthesis.md` is a synthesis layer that asks which discretionary edges (Phase 4) and systematic edges (Phase 5) translate into edge on *quoting a terminal-distribution grid* on Kalshi `KXSOYBEANW`, versus those that only describe directional or relative-value alpha and are therefore the wrong primitive for a market-making book. The artifact reframes the problem as distribution quoting (perturbations to the implied risk-neutral density of the Friday CBOT settle) rather than direction prediction, catalogues a third class of edges that exist only because of the market-making activity itself (queue position, per-bucket adverse selection, cross-inventory skew, fee/rebate capture), specifies a hedging regime, enumerates contract-specific risks, lists open empirical questions, and pre-commits a four-milestone prototype roadmap with explicit kill criteria. Every empirical claim is flagged as hypothesis, not realized profit.

---

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C10-01 | Each Kalshi bucket is a digital-corridor option with a one-dollar notional, decomposable as the difference of two cash-or-nothing digital calls. | §1, line 11 | established | contract; pricing-model |
| C10-02 | The vector of Yes prices across an Event is the empirical risk-neutral density discretized to bucket-scale resolution under Breeden–Litzenberger (1978). | §1, line 11 | established | density; pricing-model |
| C10-03 | The "translation test" for any Phase 4 / Phase 5 edge is whether it can be expressed as a perturbation to the implied density (mean shift, variance shift, higher-moment shift, or localized re-weighting). | §1, line 13 | established | strategy; density |
| C10-04 | Directional "trend is up" maps on weekly horizon to a small positive mean-shift on a near-symmetric density; arbitrage value is small relative to fees unless the directional signal is large. | §1, line 13 | established | strategy; density |
| C10-05 | Market making requires two-sided edges; the relevant pricing question is "what density should I quote and how to lean against inventory and adverse selection," generalizing Avellaneda–Stoikov to the multi-asset bucket grid (Cartea–Jaimungal–Penalva). | §1, line 15 | established | pricing-model; inventory |
| C10-06 | Prediction-market literature reports a small but persistent favorite–longshot bias that strengthens as expiry approaches (Wolfers–Zitzewitz; Whelan 2025 across 300,000+ Kalshi contracts). | §1, line 17 | established | market-structure; pricing-model |
| C10-07 | A pricing engine that ignores the favorite–longshot overlay will systematically under-price low-probability tail buckets and over-price near-certainty interior buckets relative to where the marginal Kalshi taker clears. | §1, line 17 | established | pricing-model; density |
| C10-08 | A deteriorating 6–10-day GEFS ensemble during U.S. pod-fill should both shift the implied density mean upward and skew the upper tail (mechanism observed in 2012). | §2.1, line 25 | practitioner-lore | density; strategy |
| C10-09 | An unexpectedly wet shift compresses the upper tail and fattens the lower interior buckets. | §2.1, line 25 | practitioner-lore | density; strategy |
| C10-10 | GEFS and ECMWF are available at 4×/day cycles; ECMWF AIFS open-data feed runs at +2h latency since October 2025. | §2.1, line 27 | established | data-ingest |
| C10-11 | The Roberts–Schlenker 0.1 supply-elasticity bound implies a price multiplier of roughly 10 per unit yield deviation in tight-stocks regimes and near-zero in well-supplied years. | §2.1, line 27 | debated | pricing-model; density |
| C10-12 | The weather→density pipeline composes as: state-conditional yield-anomaly distribution → price distribution via stocks-to-use elasticity → SVI/Figlewski RND adjustment → bucket Yes mid re-mark. | §2.1, line 27 | established | pricing-model; density; data-ingest |
| C10-13 | CME analysis finds WASDE *reduces* implied volatility roughly 70% of the time. | §2.2, line 31 | established | density; strategy |
| C10-14 | WASDE-day grain-futures volatility traces a U-shape — elevated pre-release, spiking on release, declining post-release (Mosquera, Garcia & Etienne 2024). | §2.2, line 31 | established | density; strategy |
| C10-15 | Implied-vol curves of short-term equity options frequently turn concave prior to scheduled earnings — a fingerprint of bimodal RNDs and an ex-ante event-risk signal (RoF 2025); the same shape is plausible on grain options into WASDE windows. | §2.2, line 31 | debated | density; pricing-model |
| C10-16 | Pre-release rule: widen the SVI fit (or scale Bates-style jump variance), which fattens interior buckets and lifts tail-bucket probabilities. | §2.2, line 33 | practitioner-lore | pricing-model; density; strategy |
| C10-17 | On release: pull quotes 30–60 seconds before the 12:00 ET print, wait for the CME option surface to re-clear, refit the RND, and repost. | §2.2, line 33 | practitioner-lore | strategy; oms |
| C10-18 | Post-release: contract variance back toward the new mean — mechanically transfers probability mass from the tails to the bucket containing the new center. | §2.2, line 33 | practitioner-lore | density; strategy |
| C10-19 | The width edge into WASDE is cleaner than the directional edge and is independent of whether the operator has a directional view. | §2.2, line 35 | practitioner-lore | strategy; density |
| C10-20 | Directional seasonality in soybeans is statistically fragile (only 3 of last 15 years saw cash higher at harvest than spring per farmdoc). | §2.3, line 39 | debated | strategy |
| C10-21 | Vol-regime seasonality is more durable: a U.S. ridge-pattern-risk vol pump and a January–February South American window (CME). | §2.3, line 39 | established | density; strategy |
| C10-22 | In vol-elevated weeks, the implied density should be wider with more probability mass in tail buckets and less in the central bucket; in vol-quiet weeks, narrower. | §2.3, line 41 | established | density; strategy |
| C10-23 | A quoter that holds bucket widths fixed at a calendar average will systematically over-quote tails in quiet weeks and under-quote tails in vol windows — informed counterparties capture the per-bucket pricing error. | §2.3, line 41 | practitioner-lore | pricing-model; strategy |
| C10-24 | The board crush (10:11:9 ZS/ZM/ZL), oilshare, and bean–corn ratio do not translate to `KXSOYBEANW` — the Event references a single underlier with no second leg; the pure spread structure is unrepresentable. | §2.4, line 45 | established | strategy; market-structure; contract |
| C10-25 | Calendar / July–November old-crop / new-crop spreads have no representation in a single weekly bucket grid; only their effect on the *mean* of the implied density is tradable. | §2.4, line 47 | established | strategy; contract; density |
| C10-26 | Basis trades and farmer-hedge-pressure trades are cash-side / physical-market frameworks that cannot be expressed as Kalshi positions; useful only as inputs to a slow fair-value overlay (tightening basis is mildly bullish for nearby ZS). | §2.4, line 49 | established | strategy |
| C10-27 | COT positioning is released after the Friday Event settles and informs the *next* week's prior, not the current Event. | §2.4, line 51 | established | strategy; data-ingest |
| C10-28 | Rumor / headline trades translate to short-horizon mean-shift updates on the implied density and are subsumed by the microstructure / OFI logic of §3.1. | §2.4, line 51 | established | strategy |
| C10-29 | Cont–de Larrard and Huang–Lehalle–Rosenbaum queue-reactive logic transfers to Kalshi's Rule 5.9 FIFO order book, with the caveat that bucket queue depths are orders of magnitude smaller than ZS top-of-book. | §3.1, line 59 | debated | market-structure; pricing-model |
| C10-30 | Sustained CME-side OFI imbalance moves the ZS mid by a small amount that propagates to *every* Kalshi bucket via the bucket delta ∂m_i/∂S derived in Phase 8 §6.1. | §3.1, line 61 | established | pricing-model; density |
| C10-31 | ATM buckets carry the largest delta (gamma-like profile) and update fastest; tail buckets update slowly. | §3.1, line 61 | established | density; pricing-model |
| C10-32 | The CME-OFI / Kalshi lead-lag is arbitrageable, *not* directional alpha. | §3.1, line 61 | established | strategy |
| C10-33 | Even at Kalshi Premier-tier rate limits (1,000 writes/sec), refreshing 20 buckets each side at sub-second cadence saturates the budget; rate-limit headroom rather than co-location is the binding constraint. | §3.1, line 61 | established | market-structure; oms; tooling |
| C10-34 | Carry as a directional edge does not translate to a single-week single-underlier bucket market. | §3.2, line 65 | established | strategy |
| C10-35 | When the front-month ZS curve inverts (old crop tight), the conditional mean of the Friday settle shifts upward and the upper tail extends; when carry is full / contango, the mean drifts downward via roll-yield drag. | §3.2, line 65 | established | density; pricing-model |
| C10-36 | The carry effect on a single-week density is small / second-order but real and is the cleanest mechanical link from Phase 5 carry literature to the bucket grid. | §3.2, line 65 | established | density |
| C10-37 | When the Goldman roll falls inside a Kalshi week, predictable index-driven flow moves the front-month price in a direction that can be modeled ex ante and folded into the implied density's drift term. | §3.2, line 67 | established | strategy; density |
| C10-38 | A parsed-table WASDE delta against analyst consensus produces a deterministic mean shift on the implied density. | §3.3, line 71 | established | density; strategy |
| C10-39 | Historical sensitivity is approximately +18¢/bu per −1 million bushel ending-stocks surprise, with regime adjustments (farmdoc; Goyal et al. 2021). | §3.3, line 71 | established | pricing-model |
| C10-40 | Crop Progress and weekly Export Sales translate similarly to WASDE, with smaller per-release coefficients and higher cadence. | §3.3, line 71 | established | strategy; data-ingest |
| C10-41 | The first-correct refit of the implied density inside the post-release minute-bar wins not just the directional move but the bucket re-pricing. | §3.3, line 73 | established | strategy; oms |
| C10-42 | Cross-sectional commodity momentum requires ≥15-commodity universe with monthly rebalance; cannot be expressed on a single weekly soybean bucket grid. | §3.4, line 77 | established | strategy |
| C10-43 | Single-market trend on ZS has reported gross Sharpes of 0.2–0.5; on a weekly bucket grid this reduces to a small mean-shift bounded by typical week-over-week change in a 12-month TSMOM signal. | §3.4, line 79 | established | strategy; backtest |
| C10-44 | Trend should be run as a low-weight slow-prior input to the implied density mean, not as a quoting signal. | §3.4, line 79 | practitioner-lore | strategy; density |
| C10-45 | Pure stat-arb on the crush spread is multi-leg and does not project onto a single-underlying weekly bucket; useful only as input to the slow ZS fair-value layer. | §3.4, line 81 | established | strategy |
| C10-46 | Stocks-to-use econometrics (log-inverse Roberts–Schlenker) is a multi-month low-frequency model; use as a regime classifier (tight stocks → wider weekly density; loose → narrower) rather than a tactical signal. | §3.4, line 83 | established | strategy; density |
| C10-47 | Kalshi's price-time FIFO and the `GET /orders/{order_id}/queue_position` endpoint make queue position an observable, action-able quantity. | §4, line 91 | established | market-structure; oms; tooling |
| C10-48 | Latency races do not bind under Kalshi's structure; the market-making edge is in maintaining favorable queue position via the `amend` endpoint rather than cancel-and-replace, which preserves time priority on small mid adjustments. | §4, line 91 | established | oms; market-structure |
| C10-49 | Participant taxonomy on the bucket book: retail at round-number buckets, sharp arbitrageurs from CME-Kalshi spread, fundamental traders concentrating on one or two informed buckets around USDA releases, momentum chasers. | §4, line 93 | established | market-structure |
| C10-50 | The market-maker's edge is a per-bucket estimate of post-trade markout (1m, 5m, 30m); widen quotes on buckets where realized adverse selection has been high in recent windows. | §4, line 93 | established | observability; pricing-model |
| C10-51 | Per-bucket adverse-selection alpha must be calibrated live week-by-week — it is not backtestable without a stream of own fills. | §4, line 93 | established | observability; backtest |
| C10-52 | Cartea–Jaimungal cross-inventory reservation price: r_i = m_i − γ(T−t) Σ_j Σ_ij q_j, with Σ_ij derived from RND perturbation. | §4, line 95 | established | pricing-model; inventory |
| C10-53 | When the operator becomes long one bucket through a fill, the Kalshi mid for *all* adjacent buckets should be skewed in the direction that reduces aggregate exposure. | §4, line 95 | established | inventory; pricing-model |
| C10-54 | Most retail and many small-prop quoters skew only the bucket whose inventory changed; the cross-inventory term is a market-maker-specific edge against that population. | §4, line 95 | practitioner-lore | inventory; strategy |
| C10-55 | Kalshi base-fee schedule: ⌈0.07 · P(1−P) · 100⌉/100 taker, 25% of taker for makers. | §4, line 97 | established | contract; pricing-model |
| C10-56 | Kalshi Chapter 4 Market Maker Program offers reduced fees, position-limit exemptions, and 10× Position Accountability Levels in exchange for non-public quoting obligations. | §4, line 97 | established | contract; market-structure |
| C10-57 | A non-MM operator pays the base maker fee on every passive fill (~0.5¢ per contract at P = 0.50). | §4, line 97 | established | pricing-model; contract |
| C10-58 | The pure rebate-capture edge is unavailable until designation; design the quoting engine to be ready for the MM-Agreement transition. | §4, line 97 | established | strategy; tooling |
| C10-59 | Hedging discipline rule: hedge the fastest-changing, lowest-cost Greek first. | §5, line 105 | established | hedging |
| C10-60 | Aggregate net delta on the bucket book translates 1:1 into ZS-equivalent bushel exposure, hedged in CME ZS futures at ~$1/contract commission plus ~$0.0025 (¼ cent) tick spread on liquid front-month. | §5, line 105 | established | hedging; pricing-model |
| C10-61 | Delta-hedge threshold rule of thumb: hedge whenever aggregate Kalshi-equivalent delta exceeds one ZS contract (5,000 bushels) of unhedged exposure; below that, carry the residual. | §5, line 105 | practitioner-lore | hedging |
| C10-62 | A vertical spread in ZS options replicating a single Kalshi bucket costs the bid-ask of two strikes — typically 1–3¢ on liquid strikes, 5+¢ on wings. | §5, line 107 | established | hedging; pricing-model |
| C10-63 | On a $0.30-priced bucket with $1 notional, a 4¢ option-spread cost is ~13% of position value. | §5, line 107 | established | hedging |
| C10-64 | Option hedging is justified only when (i) single-bucket position is large enough that squared-error of carrying the gamma exceeds the option-spread cost, *and* (ii) a CBOT weekly or short-dated new-crop expiry co-terminates with the Kalshi Event. | §5, line 107 | established | hedging; contract |
| C10-65 | CBOT short-dated weekly options that co-terminate with the Kalshi Event are available February through August; outside that window, the hedge is mismatched in expiry and carries Brownian residual risk. | §5, line 107 | established | contract; hedging |
| C10-66 | Three further hedge frictions: Kalshi-snapshot vs CME-option-reference expiry basis; contract-month mismatch on roll-window weeks (the Kalshi "front month" rule per Appendix A is unconfirmed); Kalshi full cash collateralization makes the Kalshi leg more capital-intensive than the ZS option leg per dollar of notional. | §5, line 109 | established | hedging; contract |
| C10-67 | Recommended discipline: delta-only hedge by default, with an event-driven option-hedge overlay around scheduled USDA releases when bucket positions are concentrated near the strike where the release is likely to land. | §5, line 111 | practitioner-lore | hedging; strategy |
| C10-68 | Kalshi commodity weeklies launched April 2026 — per-bucket queues are likely small and per-bucket spreads can widen sharply in low-flow windows (overnight, weekend, off-hours when CBOT closed but Kalshi trades 24/7). | §6, line 117 | established | contract; market-structure |
| C10-69 | A book quoting through a Friday-afternoon settlement window may find no counterparty for an unwind and is forced to carry positions into resolution — a structural feature of new prediction markets. | §6, line 117 | practitioner-lore | market-structure |
| C10-70 | Empirical fingerprint of adverse selection from informed fundamental traders: a fat-tailed markout distribution on fills near WASDE / Export Sales / Crop Progress windows; sharper U-shape than CME ZS would imply selective hitting of un-re-marked Kalshi quotes. | §6, line 119 | established | observability |
| C10-71 | Reference-price basis (front-month settlement vs 2:20 p.m. CT close vs VWAP) is unread until Appendix A; the pricing engine should refuse to size up beyond a reference-confirmation bound until this is locked. | §6, line 121 | established | contract; tooling |
| C10-72 | CBOT ZS trades Sunday 19:00 CT through Friday 13:20 CT; Kalshi trades 24/7; a Kalshi position carried over a weekend faces no continuous CME reference-price discovery. | §6, line 123 | established | market-structure; contract |
| C10-73 | Practitioners should pull or radically widen quotes when CBOT is not open; the Sunday-evening reopen window is itself a known volatility regime that should expand quoted distribution width. | §6, line 123 | practitioner-lore | strategy; oms; density |
| C10-74 | CBOT soybean variable daily limits are ~7% of price; on a limit-locked Friday expiry, the settlement is the limit price (a discrete number that resolves all buckets) but the hedge leg is unwindable only at the limit and produces discrete-jump P&L — book must be stress-tested for this. | §6, line 125 | established | contract; market-structure; hedging; observability |
| C10-75 | Basic-tier rate limits (10 writes/sec) are tight for a 15–20-bucket strip; Advanced (300/300) is the realistic MVP ceiling; amend-vs-cancel-and-replace economics dominate. | §6, line 127 | established | market-structure; oms |
| C10-76 | A 429 during a fast-moving release window prevents pulling quotes and forces the operator to wear adverse selection until the leaky-bucket refills. | §6, line 127 | established | oms; observability |
| C10-77 | Milestone 0 (offline reproduction): pull historical CME ZS option chains via Databento Standard ($199/month) for any week with a known settled Kalshi `KXSOYBEANW`; fit SVI and Figlewski-tailed RND; compute model bucket probabilities; compare to settled outcomes; produce SVI residual report, RND-vs-realized hit-rate calibration, and bias estimate for the measure overlay. | §8, line 150 | established | backtest; data-ingest; pricing-model |
| C10-78 | Milestone 1 (paper-trading pricing engine, no quoting) requires the pipeline: Surface ingest → Smoothing → RND extraction → Bucket integration → Measure overlay → Reservation price → Adverse-selection skew → Spread sizing → Hedge sizer → Risk gating; log "would-quote" Yes prices at 1-second cadence per bucket with would-fill diagnostics; deliver mid-error distribution per bucket per Event, markout simulator, rate-limit headroom report. | §8, line 152 | established | pricing-model; tooling; observability |
| C10-79 | Milestone 2 (passive two-sided quoting) sandbox caps: $500 max loss per bucket; $5,000 aggregate Event; symmetric quotes around model mid with wide initial spread (≥4¢ each side); subscribe to `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`; amend-not-cancel for small mid moves; `DELETE /orders/batch` plus order-group-trigger kill switch. | §8, line 154 | established | oms; observability; tooling |
| C10-80 | Milestone 3 (CME hedge loop): use FCM API (Interactive Brokers / AMP / Tradovate); hedge net delta when |Δ| ≥ 1 ZS contract; optional weekly-option vertical-spread hedge for concentrated single-bucket positions during Feb–Aug short-dated window; reconcile Kalshi `GET /portfolio/positions` against FCM execution reports three times per session. | §8, line 156 | established | hedging; observability; tooling |
| C10-81 | Milestone 4 (risk and ops hardening): scenario-based caps (WASDE-day, weather-shock, expiry-day-liquidity-collapse); Grafana / Prometheus / PagerDuty; hot-standby quoter for failover; apply for Advanced or Premier rate-limit tier; begin Kalshi MM Program application package. | §8, line 158 | established | observability; tooling |
| C10-82 | Milestone gating discipline: a milestone is not declared complete until the next milestone's gating tests pass on the data produced by it (M0 must produce positive expected edge after fees on simulated mids before M1 starts; M1 must produce positive simulated P&L over four consecutive settled weeks before M2 begins; etc.). | §8, line 160 | established | backtest; observability |

---

## 3. What this file does NOT claim

The synthesis explicitly carries every empirical proposition as hypothesis and disclaims realized profit. Specific absences:

It does not specify the Kalshi `KXSOYBEANW` reference-price construction (front-month settle vs 2:20 p.m. CT close vs VWAP) — this is flagged as the largest unresolved structural ambiguity (Appendix A unread).

It does not give per-bucket queue-depth numbers, trade-arrival rates, fill-intensity functions λ_i(δ), or empirical cross-bucket probability covariance Σ_ij; these are listed as open research questions.

It does not commit a numerical favorite–longshot bias parameter for `KXSOYBEANW` specifically — only that the cross-product Whelan (2025) result is the prior.

It does not give a calibrated SVI / Figlewski residual error bar or a published mid-error distribution; those are M0/M1 deliverables.

It does not specify a non-public Kalshi Market Maker Agreement's fee rebate, uptime, spread-cap, or minimum-size obligations — these are inferred-only and listed as research questions.

It does not provide a written WASDE-nowcaster, an OFI propagation function, or a regression-calibrated weather→yield→price→density model — only the structural pipeline.

It does not claim a tested Polymarket↔Kalshi cross-venue arbitrage size on ZS-referenced products; that is also an open research question.

---

## 4. Cross-links

Several claims here visibly depend on or reuse anchors from earlier phases (inferred from explicit citations in the file):

C10-01, C10-02, C10-30, C10-52 explicitly reuse Phase 8's Breeden–Litzenberger pipeline, bucket delta ∂m_i/∂S, and Cartea–Jaimungal cross-inventory reservation-price formula. Any divergence from the Phase 8 derivation would propagate.

C10-10, C10-12 depend on Phase 6's GEFS/ECMWF/AIFS feed catalogue; C10-77 depends on Phase 9's Databento Standard pricing.

C10-11 (Roberts–Schlenker 0.1 elasticity) depends on Phase 5 §6.3; C10-20 cites Phase 4 §8 and Phase 5 §3 in tension on directional vs vol-regime seasonality.

C10-29, C10-33, C10-47, C10-48, C10-55, C10-56, C10-75, C10-76 depend on Phase 7 (rulebook, fee schedule, MM program) and Phase 9 (rate-limit ladder, queue endpoint, amend semantics). C10-71 explicitly contradicts itself if Appendix A specifies a non-CME reference (this is also kill criterion C10-KC-05).

C10-65 (Feb–Aug short-dated weekly availability) depends on Phase 6 §2.2; C10-66's "Kalshi front-month rule unconfirmed" is the same Phase 7 §10 ambiguity called out in C10-71.

C10-43 (TSMOM gross Sharpes 0.2–0.5 on ZS) depends on Phase 5 §1; C10-50, C10-51 depend on the Phase 8 §5 participant taxonomy.

---

## 5. Open research questions and kill criteria

### Open research questions

| id | question |
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

### Kill criteria

| id | criterion |
|---|---|
| C10-KC-01 | *Milestone 0 fails*: SVI / Figlewski RND-implied bucket probabilities, after a measure overlay calibrated on Whelan-style favorite-longshot assumptions, miss the realized Kalshi outcomes by more than the ~2¢ round-trip fee on more than 50% of buckets across 12+ settled Events. The CME option surface does not contain enough information to price the Kalshi grid better than fees, and no quoting strategy can profit. |
| C10-KC-02 | *Milestone 1 fails*: simulated would-quote P&L is not consistently positive (median weekly P&L < 0 over four settled weeks) at the realistic fee schedule, or rate-limit saturation prevents the would-quote engine from re-pricing during release windows. Either fact eliminates the structural opportunity. |
| C10-KC-03 | *Milestone 2 fails*: realized markout on actual fills exceeds the estimated edge net of fees on the majority of buckets — informed counterparties are routinely picking off quotes faster than the engine can defend. Without an MM Agreement (unavailable to a new participant), this is fatal. |
| C10-KC-04 | *Milestone 3 fails*: hedge slippage plus basis P&L plus snapshot-timing P&L exceeds the gross quoting edge produced by Milestone 2, leaving net negative P&L. The CME hedge cannot be made cheap enough to support the Kalshi book. |
| C10-KC-05 | *Structural failure*: Kalshi Appendix A reveals a reference specification (e.g., a non-CME source, a VWAP that cannot be replicated from public CBOT data, a roll rule that discards short-dated weekly options) that breaks the Breeden–Litzenberger pipeline at its root. |
| C10-KC-06 | *Liquidity failure*: per-bucket queue depth and trade arrival on `KXSOYBEANW` over four consecutive Events remain below a level at which queue-position-aware quoting matters (e.g., sub-50 contracts top-of-book on most buckets), making the FIFO microstructure edge irrelevant. |
| C10-KC-07 | *Regulatory failure*: a CFTC action, exchange rule change, or fee surcharge materially alters the Phase 7 / Phase 8 / Phase 9 cost structure. |
