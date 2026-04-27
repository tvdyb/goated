# Phase 10 — Strategy Synthesis: Which Soybean Edges Survive Translation to Kalshi Bucket Market Making

## Abstract

Phases 1–9 inventoried the soybean complex, the academic and practitioner literature on directional and relative-value alpha, the data and tooling stack needed to consume it, and the specific structural facts of Kalshi's `KXSOYBEANW` weekly digital-corridor product. This phase asks the load-bearing question: of the discretionary edges from Phase 4 and the systematic edges from Phase 5, which translate into edge on *quoting a terminal-distribution grid* — and which only describe an edge on *direction*, the wrong primitive for a market-making book? The translation succeeds when an edge can be expressed as a *change to the implied risk-neutral density* of the Friday CBOT settle: weather skew, WASDE-day variance dynamics, seasonal vol regime, microstructure flow, and term-structure shifts all qualify. It fails when the edge is fundamentally a long/short bet on a basket of correlated underliers, a relative-value spread with no scalar projection onto a single weekly underlier, or a low-frequency rebalance against position limits the venue does not have. A second class of edges arises *only* from making markets — queue position, per-bucket adverse-selection estimation, inventory-driven cross-bucket skew, and rebate capture under a future Kalshi Market Maker Agreement — and these have no analogue in the Phase 4 / Phase 5 literature. Everything below is hypothesis to be tested, not profit to be claimed.

---

## 1. Reframing: distribution quoting, not direction prediction

A directional edge is a signed function of expected future price: "ZS will close higher than today" produces a long futures position. A bucket-distribution edge is a function of the *probability mass* the market is currently assigning to each interval of the Friday settle: "the market is over-pricing the [\$10.40, \$10.60) bucket relative to my estimate of $\Pr(\ell_i \le S_T < u_i)$" produces a short Yes on that bucket. Phase 8 §1 fixed the formal correspondence — each Kalshi bucket is a digital-corridor option with one-dollar notional, decomposable as the difference of two cash-or-nothing digital calls, and the vector of Yes prices across an Event is the empirical risk-neutral density discretized to bucket-scale resolution under the [Breeden & Litzenberger (1978)](https://faculty.baruch.cuny.edu/lwu/890/BreedenLitzenberger78.pdf) identity.

Three consequences follow once this reframing is accepted. First, the "translation test" for any Phase 4 / Phase 5 edge is whether the edge can be expressed as a perturbation to the implied density — a shift in mean (skew), a shift in variance (width), a shift in higher moments (tail, bimodality), or a localized re-weighting of one bucket against its neighbors. An edge that affects only the *sign* of expected return — e.g., "trend is up" — must be re-expressed as a density shift; on a weekly horizon, "trend is up" maps to a small positive mean-shift on a near-symmetric density, which is a small probability transfer from the lower interior buckets to the upper interior buckets. The arbitrage value is small relative to fees unless the directional signal is large.

Second, market-making requires *two-sided* edges. A bucket can be over- or under-priced; a quoter wins on either side. The relevant pricing question is not "what will the settle be" but "what density should I quote, and how much should I lean against my own inventory and against my estimate of adverse selection." This is a generalization of [Avellaneda & Stoikov (2008)](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf) to the multi-asset bucket grid, formalized by [Cartea, Jaimungal & Penalva (2015)](https://assets.cambridge.org/97811070/91146/frontmatter/9781107091146_frontmatter.pdf) with cross-asset inventory penalties.

Third, prediction-market structure introduces a Kalshi-specific measure shift between the CME risk-neutral density and the price at which Kalshi traders clear. The empirical literature on prediction markets — [Wolfers & Zitzewitz (2004, 2006)](https://www.aeaweb.org/articles?id=10.1257/0895330041371321) and the recent 300,000-contract Kalshi study by [Whelan (2025)](https://www.ucd.ie/economics/t4media/WP2025_19.pdf) — reports a small but persistent favorite–longshot bias that strengthens as expiry approaches. A pricing engine that ignores this overlay will systematically under-price low-probability tail buckets and over-price near-certainty interior buckets relative to where the marginal Kalshi taker is willing to trade.

---

## 2. Discretionary edges from Phase 4 — what translates

### 2.1 Weather-driven distribution skew

Phase 4 §3 documented the AgResource / Hightower / StoneX practitioner overlay of GFS/ECMWF ensembles against NASS Crop Progress through the U.S. June–August pod-fill window and the South American January–February pod-fill window, with sizing scaled to forecasted ridge-pattern risk. As a directional bet ("size into ridges, fade rains"), this is a single-sign overlay on ZS. As a *distribution* edge it has more structure: a deteriorating 6–10-day GEFS ensemble for the central Corn Belt during pod-fill should both shift the mean of the Kalshi implied density upward *and* skew the upper tail — the same physical mechanism that produced the limit-up sequences of 2012 ([Farmdoc Daily, "Corn and Soybean Prices Continue to Retrace 2012 Drought Rally"](https://farmdocdaily.illinois.edu/2013/05/corn-soybean-prices-retrace-2012-rally.html)). On the price-down side, an unexpectedly wet shift compresses the upper tail and fattens the lower interior buckets.

The translation is direct and tradeable. The quoting engine reads the 4×/day GEFS and ECMWF cycles (Phase 6 §7) — and the ECMWF AIFS open-data feed at +2h latency since October 2025 — into a state-conditional yield-anomaly distribution; the yield distribution maps to a price distribution via a stocks-to-use elasticity (the Roberts–Schlenker 0.1 supply-elasticity bound from Phase 5 §6.3 implies a price multiplier of roughly 10 per unit yield deviation in tight-stocks regimes, near-zero in well-supplied years); the price distribution adjusts the SVI/Figlewski RND from the CME ZS option surface ([Figlewski 2018](https://pages.stern.nyu.edu/~sfiglews/documents/RND%20Review%20ver4.pdf), Phase 8 §2.3); and the bucket Yes mids re-mark accordingly. The hard step is calibrating the elasticity in regime; the rest is mechanical.

### 2.2 Pre-WASDE distribution widening, post-release re-calibration

Phase 4 §2 catalogued the practitioner "flatten or fade" pattern in the 48 hours before a WASDE release, citing AgWeb tape. Phase 5 §6.2 added the published CME finding that WASDE *reduces* implied volatility roughly 70% of the time ([CME, "Understanding Major USDA Reports"](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)) and the [Mosquera, Garcia & Etienne (2024)](https://www.tandfonline.com/doi/full/10.1080/13504851.2024.2373337) result that WASDE-day grain-futures volatility traces a U-shape — elevated pre-release, spiking on release, declining post-release. A 2025 *Review of Finance* paper documents that implied-vol curves of short-term equity options frequently turn *concave* prior to scheduled earnings — a fingerprint of bimodal risk-neutral distributions — and that concavity is an ex-ante signal for event risk ([Pricing event risk: evidence from concave implied volatility curves, RoF 2025](https://academic.oup.com/rof/article/29/4/963/8079062)); the same shape is plausible on grain options into WASDE windows.

For a Kalshi quoter, all three observations translate into deterministic *width* dynamics on the implied density. Pre-release: widen the SVI fit (or scale the variance of the Bates-style jump component), which fattens the interior buckets and lifts tail-bucket probabilities. On release: pull quotes 30–60 seconds before the 12:00 ET print, wait for the CME option surface to re-clear (Phase 8 §8), refit the RND, and repost. Post-release: contract the variance back toward the new mean, which mechanically transfers probability mass from the tails to the bucket containing the new center.

The directional edge — being long or short going into the release — does not translate well unless the operator is running an explicit WASDE-nowcaster ahead of consensus. The *width* edge is the cleaner one and is independent of whether the operator has a directional view.

### 2.3 Seasonal vol patterns affecting bucket width in probability space

Phase 4 §8 and Phase 5 §3 each documented the practitioner-academic dispute over directional seasonality: the [farmdoc critique](https://farmdocdaily.illinois.edu/2020/06/seasonal-price-rally-in-soybeans.html) is that only three of the last fifteen years saw soybean cash higher at harvest than in spring, so directional seasonality is statistically fragile. The same artifacts agree, however, that vol-regime seasonality is more durable: the [CME "Vol is High by the Fourth of July"](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html) and "Weather Markets in Grain Futures" white papers document a reliable seasonal vol-pump centered on the U.S. ridge-pattern risk window, and a corresponding January–February South American window.

The translation to the bucket grid is again clean: in vol-elevated weeks, the implied density should be wider, with more probability mass in the tail buckets and less in the central bucket. In vol-quiet weeks (October harvest after the autumn lows print, or May after Brazilian crop is in), the density should be narrower. A quoter that holds bucket *widths* fixed at a calendar average will systematically over-quote tails in quiet weeks and under-quote tails in vol windows — the seasonal vol-pump becomes a per-bucket pricing error that informed counterparties capture.

### 2.4 Discretionary frameworks that do not translate

**Board crush, oilshare, and inter-market ratio trades.** Phase 4 §1 made the case for the board crush (10:11:9 ZS/ZM/ZL package), oilshare, and bean–corn ratio as the first-order relative-value primitives in the soybean complex. None translate directly to the `KXSOYBEANW` bucket grid: the Kalshi Event references a single underlying (Phase 7 §2), there is no second leg to spread against, and the cross-product economics (RFS-driven oilshare moves, processor margin compression) are projected onto the ZS price only via the residual after meal and oil settle. In principle, a long-crush view could be expressed by buying buckets above the spot-implied center and selling buckets below — but the projection is so lossy that the resulting "directional" position is just a bet on ZS, not on the crush. The pure spread structure is unrepresentable.

**Calendar spread / July–November old-crop / new-crop trades.** Same problem. Kalshi prices a single Friday-of-the-week settlement on the front-month CBOT contract; the July–November term-structure spread has no representation in a single weekly bucket grid. A roll-period view can affect the *mean* of the implied density (see §3.2 below), but the spread itself is not tradable.

**Basis trades and farmer hedge-pressure trades.** Phase 4 §§4, 5 are cash-side / physical-market frameworks: country-elevator basis, river logistics, harvest-low fade. None can be expressed as a Kalshi position — the underlying is a *futures* settlement, not the cash basis. They remain useful as inputs to a slow fair-value overlay (a tightening basis is mildly bullish for nearby ZS) but they are not first-order quoting signals.

**COT positioning and rumor / headline trades.** COT inflections (Phase 4 §6) are weekly signals released *after* the Friday Event settles; they inform the *next* week's prior, not the current Event. Rumor / headline trades (Phase 4 §7) translate to short-horizon mean-shift updates on the implied density and are subsumed by the microstructure / OFI logic of §3.1; they are not a separate framework.

---

## 3. Systematic edges from Phase 5 — what translates

### 3.1 Short-horizon microstructure → terminal-distribution nudges

Phase 5 §9 catalogued order-flow imbalance, queue dynamics, and VPIN ([Easley, López de Prado & O'Hara, RFS 2012](https://academic.oup.com/rfs/article-abstract/25/5/1457/1569929)) on the CME ZS book; Phase 8 §3.3 noted that Cont–de Larrard and Huang–Lehalle–Rosenbaum queue-reactive logic transfers to Kalshi's Rule 5.9 FIFO order book ([KalshiEX Rulebook v1.18](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)) with the caveat that bucket queue depths are orders of magnitude smaller than ZS top-of-book.

The translation is: a sustained CME-side OFI imbalance moves the ZS mid by a small amount, which propagates to *every* Kalshi bucket via the bucket delta $\partial m_i/\partial S$ derived in Phase 8 §6.1. ATM buckets carry the largest delta (gamma-like profile) and so update fastest; tail buckets update slowly. A market maker who reads CME ZS OFI in real time will lean into Kalshi quotes ahead of the slower retail flow that updates from explicit ZS-tick reads — this is an arbitrageable lead-lag relationship, *not* a directional alpha. Capacity is bounded by Kalshi rate limits ([Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)) — even at the Premier tier (1,000 writes/sec), refreshing 20 buckets each side at sub-second cadence saturates the budget. Co-location is unnecessary (Phase 9 §6), but rate-limit headroom is.

### 3.2 Term-structure shifts and front-week density

Phase 5 §2 surveyed [Erb & Harvey (2006)](https://www.tandfonline.com/doi/abs/10.2469/faj.v62.n2.4084), [Koijen, Moskowitz, Pedersen & Vrugt (2018)](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf), and the storage-theory backbone (Working / Brennan) for the term-structure family. Carry as a directional edge — buying high-roll-yield commodities, shorting low — does not translate to a single-week single-underlier bucket market. But carry as a *density input* does: when the front-month ZS futures curve inverts (old crop tight), the conditional mean of the Friday settle shifts upward and the upper tail extends; when carry is full, the curve is in contango and the mean drifts downward via roll-yield drag. The effect on a single-week density is small — second-order — but real, and is the cleanest mechanical link from the Phase 5 carry literature to the bucket grid.

The Goldman roll window (Phase 5 §9.4, citing [Mou 2011](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1716841)) is a separate term-structure phenomenon. In months when the Goldman roll falls inside a Kalshi week, predictable index-driven flow moves the front-month price in a direction that can be modeled ex ante and folded into the implied density's drift term. This is a true, bucket-level translatable edge with a narrow time window.

### 3.3 NLP on WASDE and Export Sales → density updates

Phase 5 §8 and Phase 4 §2 both put WASDE-nowcasting at the center of the systematic-fundamentals stack. The translation is direct: a parsed-table delta against the analyst consensus produces a deterministic mean shift on the implied density (the historical sensitivity coefficients — ~+18¢/bu per −1 million bushel ending-stocks surprise, with regime adjustments — are well-documented in farmdoc and the [Goyal et al. (2021)](https://agecon.uga.edu/content/dam/caes-subsite/ag-econ/documents/Goyal_Adjemian_Glauber_Meyer_NCCC-134_2021.pdf) decomposition). Crop Progress and weekly Export Sales translate similarly, with smaller per-release coefficients and a higher cadence (Phase 9 §3).

The key advantage on a Kalshi weekly is *speed*: the operator who has the first-correct refit of the implied density inside the post-release minute-bar wins not just the directional move but the bucket re-pricing. Quoting engine logic mirrors §2.2: pull quotes ahead of the release, refit, repost.

### 3.4 Systematic frameworks that do not translate

**Cross-sectional commodity momentum.** Phase 5 §4 surveyed Miffre–Rallis, Asness–Moskowitz–Pedersen, and Bakshi–Gao–Rossi cross-sectional sorts. The strategy requires a universe of at least 15 commodity futures with monthly rebalance; a single weekly soybean bucket grid has no cross-sectional dimension and no rebalance frequency that aligns with the literature. Cross-sectional momentum on commodities may inform a multi-week ZS prior but cannot be expressed as a Kalshi position.

**Trend-following on ZS alone.** Phase 5 §1 reported single-market trend Sharpes of 0.2–0.5 gross on ZS ([Moskowitz, Ooi & Pedersen, JFE 2012](https://www.sciencedirect.com/science/article/pii/S0304405X11002613); [Hurst, Ooi & Pedersen, AQR 2012](https://openaccess.city.ac.uk/id/eprint/18554/7/SSRN-id2520075.pdf)). On a weekly bucket grid, trend reduces to "small mean-shift on the implied density," with the magnitude bounded by the typical week-over-week change in a 12-month TSMOM signal. The signal exists but is small relative to fees and to the §3.1 microstructure / §3.3 NLP edges that move price by larger amounts on shorter horizons. Run trend as a low-weight slow-prior input to the implied density mean, not as a quoting signal.

**Pure stat-arb on the crush spread.** Phase 5 §5 covered Engle–Granger / Johansen / VECM cointegration on (ZS, ZM, ZL). The relationship is real but multi-leg; it does not project onto a single-underlying weekly bucket. Useful only as an input to the slow ZS fair-value layer, like the basis case in §2.4.

**Stocks-to-use econometric pricing.** Phase 5 §6 documented the log-inverse Roberts–Schlenker pricing relation. This is a multi-month, low-frequency model — ill-suited to a weekly bucket whose density is dominated by short-horizon weather, microstructure, and event flow. Use it as a regime classifier (tight-stocks weeks → wider weekly density; loose-stocks weeks → narrower) rather than a tactical signal.

---

## 4. Market-making-specific edges independent of directional alpha

These are edges that exist *only* because the operator is making markets. They have no analogue in Phase 4 or Phase 5 — those phases studied directional and relative-value alpha, not quoting alpha.

**Queue-position capture.** Kalshi's price-time FIFO and the first-class `GET /orders/{order_id}/queue_position` endpoint (Phase 9 §1.2) make queue capture an observable, action-able quantity. A resting Yes order at the prevailing bid that is first in queue earns the half-spread on every fill at that price; one that is fifth in queue at the same price has the same theoretical edge but a much lower fill probability, and an *adverse-selection* problem because by the time the queue reaches the resting order, the mid has plausibly moved against it. The market-making edge is not in winning races — Phase 9 §6.1 established that latency races do not bind under Kalshi's structure — but in maintaining favorable queue position via the `amend` endpoint rather than cancel-and-replace, which preserves time priority on small mid adjustments.

**Per-bucket adverse-selection estimation.** Phase 8 §5 sketched the participant taxonomy: retail punters at round-number buckets, sharp arbitrageurs from CME-Kalshi spread, fundamental traders concentrating on one or two informed buckets around USDA releases, and momentum chasers. The market-maker's edge is to maintain a per-bucket estimate of post-trade markout (1m, 5m, 30m) and widen quotes on buckets where realized adverse selection has been high in recent windows. This is not an alpha that can be backtested without a stream of own fills — it has to be calibrated live, week by week. The [Whelan (2025) Kalshi study](https://www.ucd.ie/economics/t4media/WP2025_19.pdf) of 300,000+ contracts is the only published systematic look at the maker–taker economics; it confirms the favorite–longshot bias and the closing-window accuracy improvement, both of which constrain the markout-curve shape that a per-bucket model should expect.

**Inventory-driven cross-bucket skew.** Phase 8 §3.2 derived the Cartea–Jaimungal cross-inventory reservation-price formula, $r_i = m_i - \gamma(T-t)\sum_j \Sigma_{ij} q_j$, with $\Sigma_{ij}$ derived from RND perturbation. The edge is mechanical: if the operator becomes long one bucket through a fill, the Kalshi mid for *all* adjacent buckets should be skewed in the direction that reduces aggregate exposure. Most retail and many small-prop quoters skew only the bucket whose inventory changed; the cross-inventory term is a market-maker-specific edge against that population.

**Rebate / fee-tier capture and Market Maker Agreement.** The Kalshi base-fee schedule (Phase 7 §6) is $\lceil 0.07\,P(1-P)\,100\rceil/100$ taker, 25% of taker for makers. The Chapter 4 Market Maker Program ([Kalshi Help — How to Become a Market Maker](https://help.kalshi.com/en/articles/13823819-how-to-become-a-market-maker-on-kalshi)) offers reduced fees, position-limit exemptions, and 10× Position Accountability Levels in exchange for non-public quoting obligations. A non-MM operator pays the base maker fee on every passive fill (~0.5¢ per contract at $P=0.50$); an MM-designated operator with a fee rebate flips the round-trip economics. Until the operator is designated, the pure rebate-capture edge is *not* available — but designing the quoting engine to be ready for the transition is a meaningful structural choice.

---

## 5. Hedging strategy synthesis

Phase 8 §6 derived the per-bucket synthetic delta and gamma; Phase 9 §2 covered the data-feed cost of supporting a CME hedge. The synthesis question is *when* to hedge in *what* instrument at *what* cost threshold.

The framing rule is: hedge the fastest-changing, lowest-cost Greek first. Aggregate net delta on the bucket book translates 1:1 into a ZS-equivalent bushel exposure that hedges in CME ZS futures at ~$1/contract commission plus a ~$0.0025 (¼ cent) tick spread on a liquid front-month — material relative to a $1 Kalshi notional only when the position is large. Rule of thumb: hedge delta whenever the aggregate Kalshi-equivalent delta exceeds one ZS contract (5,000 bushels) of unhedged exposure; below that, carry the residual.

Gamma and vega hedges are categorically more expensive. A vertical spread in ZS options that exactly replicates a single Kalshi bucket costs the bid-ask of two strikes — typically 1–3¢ on liquid strikes, 5+¢ on wings. On a $0.30-priced bucket with a $1 notional, a 4¢ option-spread cost is ~13% of position value. The threshold for option hedging is therefore: only when (i) the operator's position in a single bucket is large enough that the squared-error of carrying the gamma exceeds the option-spread cost, *and* (ii) there is a CBOT weekly or short-dated new-crop expiry that co-terminates with the Kalshi Event ([CME — Agricultural Short-Term (Weekly) Options](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)). The latter is true February through August (Phase 6 §2.2); outside that window, the hedge is mismatched in expiry and carries Brownian residual risk.

Three further frictions: the basis between Kalshi snapshot and CME option-reference expiry (Phase 8 §6.3); the contract-month mismatch on roll-window weeks (the Kalshi "front month" rule per Appendix A is unconfirmed — Phase 7 §10 ambiguity); and Kalshi's full cash collateralization, which inverts the usual capital constraint (the Kalshi leg is more capital-intensive than the ZS option leg per dollar of notional, Phase 8 §6.4).

The recommended discipline is a delta-only hedge by default, with an event-driven option-hedge overlay around scheduled USDA releases when bucket positions are concentrated near the strike where the release is likely to land.

---

## 6. Risks specific to this contract

**Liquidity cliffs.** Kalshi commodity weeklies are new (April 2026 launch; [Kalshi News, "Commodities Hub launch"](https://news.kalshi.com/p/kalshi-launches-commodities-hub-new-markets)). Per-bucket queues are likely small, and per-bucket spreads can widen sharply in low-flow windows (overnight, weekend, off-hours when CBOT is closed but Kalshi trades 24/7). A book that quotes through a Friday-afternoon settlement window may find no counterparty for an unwind and is forced to carry positions into resolution. This is a structural feature of new prediction markets and is independent of strategy.

**Adverse selection from informed fundamental traders.** Phase 8 §5 made the case; the empirical fingerprint should be a fat-tailed markout distribution on fills near WASDE / Export Sales / Crop Progress windows. The Mosquera et al. WASDE U-shape on ZS is the prior; if Kalshi shows a sharper U, informed flow is selectively hitting Kalshi quotes that have not yet re-marked. The Whelan (2025) 300,000-contract analysis is the closest published cross-market evidence; per-contract, per-week analysis on `KXSOYBEANW` specifically does not yet exist.

**Basis risk in the reference price.** Phase 7 §2 listed this as the largest unresolved structural ambiguity. Until the operator reads the per-contract Appendix A and confirms the reference (front-month settlement vs. a 2:20 p.m. CT close vs. a VWAP), every position carries an irreducible reference-price basis. A pricing engine should refuse to size up beyond a reference-confirmation bound until this is locked.

**Weekend and off-hours settlement risk on ZS.** CBOT ZS trades Sunday 19:00 CT through Friday 13:20 CT. Kalshi trades 24/7. A Kalshi position carried over a weekend during which the CME is closed faces no continuous reference-price discovery — a Sunday-evening Kalshi mid against a Friday-afternoon ZS reference can drift by an unknown amount. Practitioners should pull or radically widen quotes when CBOT is not open. The Sunday-evening reopen window is itself a known volatility regime that should expand quoted distribution width.

**Limit-move days.** CBOT soybean has variable daily limits (~7% of price). If the May 2026 contract locks limit on the Friday expiry, the settlement is the limit price — a single, discrete number that crisply resolves every bucket but may not reflect a continuous-trading equivalent. The Kalshi engine handles this correctly under the daily-settle reference, but the *hedge* leg can be unwindable only at the limit and produces a discrete-jump P&L. Stress-test the book against this scenario.

**Rate-limit-induced quote staleness.** Phase 9 §1.3 noted that Basic-tier rate limits (10 writes/sec) are tight for a 15–20-bucket strip; Advanced (300/300) is the realistic MVP ceiling and amend-vs-cancel-and-replace economics dominate. If the operator hits a 429 during a fast-moving release window and cannot pull quotes, they are forced to wear adverse selection until the leaky-bucket refills.

---

## 7. Open research questions

1. **Empirically estimate the correlation between ZS front-month risk-neutral density (from CME options) and Kalshi bucket implied probabilities at various times to expiry.** Daily snapshots of both surfaces over the first 12–24 settled `KXSOYBEANW` Events; per-bucket residuals; correlation as a function of moneyness and time-to-expiry. Sets the §2.4 measure-overlay calibration in Phase 8.
2. **Quantify the favorite–longshot bias on `KXSOYBEANW` specifically and compare to the Whelan (2025) cross-product Kalshi result.** Bucket-by-bucket realized-vs-quoted hit rate on the first 24 settled Events; if the bias is monotonic in quoted Yes price, the measure-overlay is a single-parameter shrinkage.
3. **Estimate the empirical fill-intensity function $\lambda_i(\delta)$ on Kalshi bucket quotes by bucket location (ATM vs tail), time-of-day (24/7 including weekends, unlike CME), and proximity to a USDA release.** The Avellaneda–Stoikov / GLFT spread formulas need this to size $\delta$.
4. **Measure realized post-trade markout (1m, 5m, 30m) on Kalshi fills around scheduled events (WASDE, ESR, Crop Progress) versus quiet windows.** Confirms or refutes the Phase 8 §5 adverse-selection prediction.
5. **Compute the empirical cross-bucket probability covariance $\Sigma_{ij}$ intraday and compare to the RND-perturbation-implied covariance.** If the empirical $\Sigma$ diverges substantially from the model $\Sigma$, the Cartea–Jaimungal cross-inventory term is mis-specified.
6. **Measure the Kalshi-vs-CME-options reference-price basis in cents historically, conditional on the Appendix A specification.** Until Appendix A is in hand, propagate as a configuration uncertainty; once known, calibrate.
7. **Test whether bucket Yes prices sum to 1.00 in practice, or whether persistent intraweek arbitrage slack exists; if so, characterize its size and persistence.** A direct measure of LMSR-like consistency under a CLOB.
8. **Compare Polymarket and Kalshi prices on equivalent commodity contracts where overlap exists.** [Public arbitrage guides](https://newyorkcityservers.com/blog/prediction-market-making-guide) report 12–20% monthly returns on cross-venue spreads in liquid contracts; whether the same applies to ZS-referenced products is empirically open.
9. **Calibrate the price-vs-yield elasticity in the §2.1 weather-distribution-skew pipeline at different stocks-to-use regimes** (tight-stocks vs loose-stocks). Roberts–Schlenker provides the asymptotic 0.1; in-sample calibration should refine.
10. **Quantify the marginal economic value of Figlewski GEV tails versus a crude lognormal tail extrapolation on the Kalshi open-ended end buckets**, measured by realized P&L on tail-bucket trades over a settled-year window.
11. **Profile the seasonality of Kalshi bucket-grid width**: do tail buckets carry more probability mass in the U.S. June–August window and the South American January–February window than in October–November (Phase 4 §3)?
12. **Characterize the Kalshi Market Maker Program quoting obligations** — uptime, spread cap, minimum size — by direct application or by inference from observed bid-ask behavior of likely MMs in the strip; estimate the rebate value at typical fill volumes.

---

## 8. Prototype roadmap

**Milestone 0 — Offline reproduction.** Pull historical CME ZS option chains (Databento Standard at $199/month; Phase 9 §2.2) for any week with a known Kalshi `KXSOYBEANW` settlement. Fit SVI and Figlewski-tailed RND per Phase 8 §2. Compute model bucket probabilities; compare to Kalshi bucket settled outcomes in aggregate and to recorded mid prints where available. Deliverables: SVI residual report, RND-vs-realized hit-rate calibration, bias estimate for the §2.4 measure overlay.

**Milestone 1 — Paper-trading pricing engine, no quoting.** Stand up the Phase 8 §9 pipeline (Surface ingest → Smoothing → RND extraction → Bucket integration → Measure overlay → Reservation price → Adverse-selection skew → Spread sizing → Hedge sizer → Risk gating). Run live against the Kalshi WebSocket capture and the CME live feed. Log "would-quote" Yes prices at 1-second cadence per bucket, with would-fill diagnostics against actual `trade` and `orderbook_delta` events. No real orders. Deliverables: mid-error distribution per bucket per Event; markout simulator; rate-limit headroom report.

**Milestone 2 — Passive two-sided quoting in a capped capital sandbox.** Begin posting `post_only` orders via Kalshi REST `POST /orders` on a single Event with a tight per-bucket dollar cap (e.g., $500 max loss per bucket; $5,000 aggregate Event). Quote symmetrically around the model mid with a wide initial spread (≥ 4¢ each side) to avoid adverse selection while calibrating fill-intensity. Subscribe to WebSocket `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`. Implement amend-not-cancel for small mid moves to preserve queue position. Use `DELETE /orders/batch` and an order-group-trigger kill switch (Phase 9 §8). Deliverables: realized fills, markout distribution, per-bucket P&L attribution.

**Milestone 3 — Hedging loop into CME ZS.** Add the CME hedge connector via the FCM API (Interactive Brokers / AMP / Tradovate; Phase 9 §2.1). Hedge aggregate net delta in ZS futures whenever |Δ| ≥ 1 ZS contract; run an optional weekly-option vertical-spread hedge for concentrated single-bucket positions during the Feb–Aug short-dated window. Reconcile Kalshi `GET /portfolio/positions` against the FCM execution reports three times per session (open / intraday / close). Deliverables: residual Greeks logs, hedge-slippage attribution, basis-P&L logs broken down by snapshot, contract-month, and timing.

**Milestone 4 — Risk and ops hardening.** Implement scenario-based risk caps (WASDE-day, weather-shock, expiry-day-liquidity-collapse; Phase 8 §7). Add monitoring (Grafana / Prometheus / PagerDuty; Phase 9 §9 Recommended stack). Stand up a hot-standby quoter for failover. Apply for Advanced or Premier rate-limit tier ([Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)). Begin documentation toward a Kalshi Market Maker Program application (Chapter 4; non-public Market Maker Agreement). Begin running the §7 open-research questions as a standing data-product backlog. Deliverables: failover runbook, scenario-stress P&L surface, MM-application package.

A milestone is not declared complete until the next milestone's gating tests pass on the data produced by it. Milestone 0 must produce a positive expected edge after fees on simulated Kalshi mids before Milestone 1 is started; Milestone 1 must produce positive simulated P&L over four consecutive settled weeks before Milestone 2 begins; and so on.

---

## 9. Kill criteria

Effort should be abandoned if any of the following empirical results is observed.

- *Milestone 0 fails*: SVI / Figlewski RND-implied bucket probabilities, after a measure overlay calibrated on Whelan-style favorite-longshot assumptions, miss the realized Kalshi outcomes by more than the ~2¢ round-trip fee on more than 50% of buckets across 12+ settled Events. This means the CME option surface does not, on the relevant horizon, contain enough information to price the Kalshi grid better than fees, and no quoting strategy can profit.
- *Milestone 1 fails*: simulated would-quote P&L is not consistently positive (median weekly P&L < 0 over four settled weeks) at the realistic fee schedule, or rate-limit saturation prevents the would-quote engine from re-pricing during release windows. Either fact eliminates the structural opportunity.
- *Milestone 2 fails*: realized markout on actual fills exceeds the estimated edge net of fees on the majority of buckets — informed counterparties are routinely picking off quotes faster than the quoting engine can defend. Without a Market Maker Agreement (which would not be available to a new participant), this is fatal.
- *Milestone 3 fails*: hedge slippage plus basis P&L plus snapshot-timing P&L exceeds the gross quoting edge produced by Milestone 2, leaving net negative P&L. The CME hedge cannot be made cheap enough to support the Kalshi book.
- *Structural failure*: Kalshi Appendix A reveals a reference specification (e.g., a non-CME source, a VWAP that cannot be replicated from public CBOT data, a roll rule that discards short-dated weekly options) that breaks the Breeden–Litzenberger pipeline at its root.
- *Liquidity failure*: per-bucket queue depth and trade arrival on `KXSOYBEANW` over four consecutive Events remain below a level at which queue-position-aware quoting matters (e.g., sub-50 contracts top-of-book on most buckets), making the FIFO microstructure edge irrelevant.
- *Regulatory failure*: a CFTC action, exchange rule change, or fee surcharge (Phase 7 §10 ambiguity 4) materially alters the Phase 7 / Phase 8 / Phase 9 cost structure.

---

## Key takeaways

- Market making the `KXSOYBEANW` grid is *distribution quoting*, not *direction prediction*; every Phase 4 / Phase 5 edge must be re-expressed as a perturbation to the implied risk-neutral density of the Friday CBOT settle, or it does not translate.
- Discretionary edges that translate cleanly: weather-driven distribution skew (mean-shift + tail expansion), pre-WASDE width expansion and post-release re-calibration, seasonal vol-regime overlay on bucket width. Discretionary edges that do not: board-crush, oilshare, calendar-spread, basis, COT, rumor — all are multi-leg or cash-side and have no scalar projection onto a single weekly underlier.
- Systematic edges that translate: short-horizon CME-side OFI as a lead-lag input to bucket mids (capacity-bounded by Kalshi rate limits, not by latency), term-structure-implied drift on the front-week density, Goldman-roll-window flow when in-window, and NLP-driven WASDE / Export Sales density updates. Systematic edges that do not: cross-sectional commodity momentum, single-market trend (signal too small relative to fees on weekly horizon), pure crush stat-arb, low-frequency stocks-to-use econometrics — these inform slow priors at most.
- A separate class of market-making edges exists with no Phase 4 / Phase 5 analogue: queue-position management via `amend`, per-bucket adverse-selection markout monitoring, Cartea–Jaimungal cross-inventory skew, and fee/rebate capture under a future Kalshi MM Agreement.
- Hedging discipline: delta-only by default in CME ZS futures whenever aggregate exposure exceeds ~1 ZS contract; option-spread overlay only on concentrated single-bucket positions during Feb–Aug short-dated weekly window; never over a CBOT closure when reference-price basis cannot be discovered.
- The contract carries irreducible risks the literature does not yet measure: liquidity cliffs in a 6-month-old market, adverse selection from informed fundamental traders, reference-price basis until Appendix A is read, weekend / off-hours risk on ZS, limit-move-day discreteness, and rate-limit-induced quote staleness.
- Every empirical claim in this synthesis is hypothesis; the prototype roadmap is built around producing the data that would falsify it. The kill criteria are explicit and pre-committed.

---

## References

- [Kalshi Help Center — How to Become a Market Maker on Kalshi](https://help.kalshi.com/en/articles/13823819-how-to-become-a-market-maker-on-kalshi)
- [Kalshi News — Commodities Hub launch (April 2026)](https://news.kalshi.com/p/kalshi-launches-commodities-hub-new-markets)
- [Kalshi API — Rate Limits (tiered leaky-bucket)](https://docs.kalshi.com/getting_started/rate_limits)
- [KalshiEX LLC Rulebook v1.18 (CFTC filing 2025)](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)
- [Whelan, K. (2025). The Economics of the Kalshi Prediction Market Contract. UCD WP2025_19.](https://www.ucd.ie/economics/t4media/WP2025_19.pdf) — favorite-longshot bias on 300,000+ Kalshi contracts; closing-window accuracy improvement.
- [Pricing event risk: evidence from concave implied volatility curves. *Review of Finance* 2025, 29(4), 963–.](https://academic.oup.com/rof/article/29/4/963/8079062) — bimodal risk-neutral distributions ahead of scheduled events.
- [Wolfers, J. & Zitzewitz, E. (2004). Prediction markets. *Journal of Economic Perspectives*, 18(2), 107–126.](https://www.aeaweb.org/articles?id=10.1257/0895330041371321)
- [Mosquera, S., Garcia, P. & Etienne, X. (2024). Exploring calendar effects: The impact of WASDE releases on grain futures market volatility. *Applied Economics Letters*.](https://www.tandfonline.com/doi/full/10.1080/13504851.2024.2373337)
- [Breeden, D. T. & Litzenberger, R. H. (1978). Prices of state-contingent claims implicit in option prices. *Journal of Business*, 51(4), 621–651.](https://faculty.baruch.cuny.edu/lwu/890/BreedenLitzenberger78.pdf)
- [Avellaneda, M. & Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance*, 8(3), 217–224.](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf)
- [Cartea, Á., Jaimungal, S. & Penalva, J. (2015). *Algorithmic and High-Frequency Trading*. Cambridge University Press.](https://assets.cambridge.org/97811070/91146/frontmatter/9781107091146_frontmatter.pdf)
- [Figlewski, S. (2018). Risk-neutral densities: A review. *Annual Review of Financial Economics*, 10, 329–359.](https://pages.stern.nyu.edu/~sfiglews/documents/RND%20Review%20ver4.pdf)
- [Easley, D., López de Prado, M. & O'Hara, M. (2012). Flow toxicity and liquidity in a high-frequency world. *RFS*, 25(5), 1457–1493.](https://academic.oup.com/rfs/article-abstract/25/5/1457/1569929)
- [Moskowitz, T. J., Ooi, Y. H. & Pedersen, L. H. (2012). Time series momentum. *JFE*, 104(2), 228–250.](https://www.sciencedirect.com/science/article/pii/S0304405X11002613)
- [Hurst, B., Ooi, Y. H. & Pedersen, L. H. (2012). A century of evidence on trend-following investing. AQR.](https://openaccess.city.ac.uk/id/eprint/18554/7/SSRN-id2520075.pdf)
- [Erb, C. B. & Harvey, C. R. (2006). The strategic and tactical value of commodity futures. *FAJ*, 62(2), 69–97.](https://www.tandfonline.com/doi/abs/10.2469/faj.v62.n2.4084)
- [Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H. & Vrugt, E. B. (2018). Carry. *JFE*, 127(2), 197–225.](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf)
- [Mou, Y. (2011). Limits to arbitrage and commodity index investment: Front-running the Goldman Roll. SSRN 1716841.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1716841)
- [Goyal, R., Adjemian, M. K., Glauber, J. & Meyer, S. (2021). Decomposing USDA ending stocks forecast errors. NCCC-134.](https://agecon.uga.edu/content/dam/caes-subsite/ag-econ/documents/Goyal_Adjemian_Glauber_Meyer_NCCC-134_2021.pdf)
- [CME Group — Understanding Major USDA Reports.](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)
- [CME Group — Vol is High by the Fourth of July.](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html)
- [CME Group — Agricultural Short-Term (Weekly) Options.](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)
- [Farmdoc Daily — Seasonal Price Rally in Soybeans.](https://farmdocdaily.illinois.edu/2020/06/seasonal-price-rally-in-soybeans.html)
- [Farmdoc Daily — Corn and Soybean Prices Continue to Retrace 2012 Drought Rally.](https://farmdocdaily.illinois.edu/2013/05/corn-soybean-prices-retrace-2012-rally.html)
- [Market Making on Prediction Markets: Complete 2026 Guide — cross-venue arbitrage primer (secondary).](https://newyorkcityservers.com/blog/prediction-market-making-guide)
- Phase 04 — Discretionary Strategies: How Expert Traders Work the Soybean Complex. `./research/phase_04_discretionary_strategies.md`.
- Phase 05 — Systematic / Quantitative Strategies in Commodity Futures. `./research/phase_05_systematic_strategies.md`.
- Phase 06 — Data Streams for Pricing the Soybean Complex. `./research/phase_06_data_streams.md`.
- Phase 07 — Kalshi Weekly Soybean Price-Range Contract: Structural Dissection. `./research/phase_07_kalshi_contract_structure.md`.
- Phase 08 — Synthesis: Pricing a Kalshi Weekly Soybean Range Grid. `./research/phase_08_synthesis_pricing.md`.
- Phase 09 — Kalshi Weekly Soybean: Minimum Viable and Recommended Stack. `./research/phase_09_kalshi_stack.md`.
