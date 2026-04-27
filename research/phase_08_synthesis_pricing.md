# Phase 08 — Synthesis: Pricing a Kalshi Weekly Soybean Range Grid

## Abstract

The Kalshi `KXSOYBEANW` weekly complex replaces a continuous futures quoting problem with a discrete one: quote a vector of binary digital-corridor contracts tiling the Friday reference price, such that the vector of Yes prices is itself the market-implied distribution of that reference under the Kalshi pricing measure. The correct pricing-engine skeleton inherits, almost unchanged, two pillars from the prior research stack. First, the Breeden–Litzenberger (1978) identity says that the risk-neutral density of the terminal price is already embedded in the CME ZS option surface as the second strike-derivative of call prices; each Kalshi bucket is the definite integral of that density across its edges, with a bias correction for the measure change between Kalshi traders and CME options. Second, the Avellaneda–Stoikov / Guéant–Lehalle–Fernández-Tapia / Cartea–Jaimungal control machinery still governs how to skew quotes against per-bucket inventory and how to hedge aggregate delta in ZS futures. What fails to transfer cleanly is the Glosten–Milgrom intuition at bucket edges, where adverse selection is dominated by tail-jump information rather than continuous drift, and the Hanson LMSR / Othman–Pennock literature, which addresses a different market structure (automated market maker) than Kalshi's CLOB. This phase sets up the math, flags what is inherited versus newly reasoned, and lists the empirical questions.

---

## 1. Payoff as a function of terminal price

Phase 07 fixed the structural facts: each `KXSOYBEANW-YYMONDD-i` Market is a Kalshi "Yes" contract with one-dollar notional that pays $1 if the settlement reference $S_T$ lies in $[\ell_i, u_i)$ and zero otherwise. The bucket set $\{[\ell_i, u_i)\}_{i=1}^n$ partitions $[0, \infty)$ via two open-ended tail buckets and $n-2$ fixed-width interior buckets anchored on round numbers in cents per bushel. Phase 07 also noted that the exact identity of $S_T$ — whether it is the CBOT Rule 813 daily settlement on the front-month ZS contract (ZSK26 for the April 24, 2026 Event) or an alternate snapshot — is pending Appendix A confirmation, and must be carried as a configuration parameter.

Formally, for bucket $i$ the Yes-side terminal payoff is the indicator

$$
g_i(S_T) \;=\; \mathbf{1}\{\ell_i \le S_T < u_i\},
$$

and the time-$t$ Kalshi-fair Yes price under the pricing measure $\mathbb{Q}^K$ used by informed participants is

$$
\text{value}_i(t) \;=\; \mathbb{E}^{\mathbb{Q}^K}\!\left[g_i(S_T)\mid \mathcal{F}_t\right] \;=\; \mathbb{Q}^K(\ell_i \le S_T < u_i \mid \mathcal{F}_t).
$$

Because Kalshi positions are fully cash-collateralized with zero variation margin (Rule 6.1(b); Phase 07 §7), there is no discounting between trade and settlement — the Yes price *is* the probability, not the discounted probability, up to the collateral-yield adjustment discussed in §6. This is a difference versus the usual Breeden–Litzenberger digital derivation on standard options, where the digital price is $e^{-r(T-t)}\mathbb{Q}(\cdot)$.

Each bucket admits the canonical digital-corridor decomposition [1]:

$$
g_i(S_T) \;=\; \mathbf{1}\{S_T \ge \ell_i\} - \mathbf{1}\{S_T \ge u_i\},
$$

so the Yes price is the difference of two cash-or-nothing digital-call prices on the reference $S_T$ at strikes $\ell_i$ and $u_i$. Carr–Madan [10] and standard static-replication arguments show each digital is the limit of a narrow vertical call spread:

$$
\mathbf{1}\{S_T \ge K\} \;=\; \lim_{\varepsilon \downarrow 0}\, \frac{1}{\varepsilon}\!\left[\max(S_T - (K-\varepsilon), 0) - \max(S_T - K, 0)\right].
$$

This is the load-bearing identity for every subsequent pricing step: a Kalshi bucket is a tradable, finite-width call spread on the CME ZS reference, and so the Kalshi quote surface and the CME option surface are two discretizations of the same conditional distribution. (Inherited from Phase 07 §4; the decomposition framing is standard.)

## 2. Distribution construction from the ZS options surface

### 2.1 Breeden–Litzenberger identity

Breeden and Litzenberger (1978) [1] showed that for a European call $C(K, T)$ priced off a risk-neutral density $f_{T}$, the density is recoverable as the second strike-derivative:

$$
f_T(K) \;=\; e^{r(T-t)}\, \frac{\partial^2 C(K, T)}{\partial K^2}.
$$

Equivalently, the digital-call (cash-or-nothing at strike $K$) price is the negative first strike-derivative, $D(K, T) = -\partial C/\partial K$, and the Kalshi bucket price is the *difference*, $\text{value}_i = D(\ell_i, T) - D(u_i, T) = \int_{\ell_i}^{u_i} f_T(x)\, dx$. The formula is model-free — it does not require Black–Scholes — and is the operational reason a sufficiently rich ZS option surface implies every Kalshi Yes price up to the measure shift in §2.3. (Transfer from the RND literature; Phase 02 did not use this result.)

### 2.2 Practical smoothing: SVI, SABR, and cubic splines on implied volatility

Raw CME option prices for ZS are neither continuous in strike nor arbitrage-free; differentiating them twice produces catastrophic noise. Standard practice smooths *in implied-volatility space* and re-prices. Three canonical parameterizations are used:

- **Gatheral's SVI surface [2]** parameterizes total implied variance $w(k) = \sigma^2(k,T) T$ as a five-parameter hyperbola in log-moneyness $k=\ln(K/F)$:  $w(k) = a + b\{\rho(k-m) + \sqrt{(k-m)^2 + \sigma^2}\}$. Gatheral–Jacquier (2014) [2] identify the constraint set that yields a *static-arbitrage-free* fit — the condition that makes the implied density non-negative and bucket prices monotone.
- **SABR [3]** (Hagan–Kumar–Lesniewski–Woodward, 2002) gives a closed-form implied-vol asymptotic with interpretable $(\alpha, \beta, \rho, \nu)$ parameters. The classic Hagan expansion can be arbitrageable at deep-OTM strikes — exactly where Kalshi tail buckets live — so an arbitrage-free SABR variant is required.
- **Cubic splines in $(\Delta, \sigma_{\text{imp}})$**, per Bliss–Panigirtzoglou (2002) [4], with vega-weighted knots. Shimko (1993) [5] used a quadratic; the cubic spline is the modern Fed/central-bank default [6].

For Kalshi's weekly horizon, the workhorse is an SVI slice calibrated to the CBOT weekly or short-dated option surface at the closest expiry; on weeks without a co-terminal weekly option, a Malz-style (2014) [6] cubic spline on the standard-option surface re-clocked via forward-variance interpolation.

### 2.3 Tail fitting and Figlewski GEV

The Kalshi grid includes two open-ended tail buckets `<$X` and `≥$Y`. These price the integrated density in regions where the ZS option surface has few or no listed strikes; relying on SVI/SABR extrapolation there under-quotes the true tail mass. Figlewski (2010, 2019) [7][8] proposed attaching Generalized Extreme Value (GEV) tails to the interior density recovered from Breeden–Litzenberger:

$$
f_T(x) \;=\;
\begin{cases}
f_{\text{GEV, lower}}(x), & x \le x_L, \\
f_{\text{BL}}(x), & x_L < x < x_U, \\
f_{\text{GEV, upper}}(x), & x \ge x_U,
\end{cases}
$$

with the GEV parameters pinned by matching the density value and first derivative at the paste points $x_L, x_U$. Bollinger, Melick and Thomas (2023) [9] extend this with more principled paste-point selection. For a Kalshi market maker, the tail-paste procedure directly sets the Yes-price floor/cap on the open-ended end buckets.

### 2.4 Reference-timing mismatch and measure adjustment

Kalshi's weekly expiry is Friday at 1:20 p.m. CT (the CBOT settlement window). Listed CBOT standard options expire on the last Friday before contract month; weekly ZS options expire each Friday not already covered by a standard expiry [22]. Three adjustments apply:

1. **Horizon mismatch.** For the April 24, 2026 Event, the nearest ZS standard option (on ZSK26) also expires April 24, so expiries coincide. When they do not, compute the density at the nearest CME expiry $T^{\text{opt}}$ and propagate to $T^{K}$ via Heston-style variance rescaling (Phase 02 §6) or a Gatheral calendar-arbitrage-constrained SVI re-fit across expiries. Short-dated new-crop weeklies cover February through August (Phase 06 §2.2).
2. **Reference-contract mismatch.** Near First Notice Day, the Kalshi "front-month" reference may differ from the richest option-surface contract. Appendix A (pending) must specify whether Kalshi rolls with CME's calendar or tracks most-active; the pricing engine needs a contract-month configuration keyed to the Kalshi Event ticker.
3. **Measure adjustment (Kalshi vs risk-neutral).** The ZS option RND is the risk-neutral distribution for the CME futures; the appropriate Kalshi measure is whatever makes Yes prices equal expected payoffs for the marginal Kalshi participant. Prediction-market prices are empirically biased toward 50% on short-dated contracts [15][16]. A physical-measure overlay is a second calibration layer; a conservative engine starts from the risk-neutral RND and marks an explicit spread on top. (New reasoning.)

## 3. Pricing models that transfer cleanly

### 3.1 Avellaneda–Stoikov per bucket

For each bucket $i$, treat the Yes contract as an instrument with midpoint $m_i(t) = \text{value}_i(t)$ derived from the RND procedure of §2. Let $q_i$ be the MM's inventory in Yes contracts on bucket $i$. The Avellaneda–Stoikov reservation price [Phase 02 §4.1] becomes

$$
r_i(t) \;=\; m_i(t) \;-\; q_i \gamma_i\, \sigma_{m_i}^2\, (T - t),
$$

where $\sigma_{m_i}^2$ is the mid-price variance *of the bucket probability*, not the underlying futures variance. That variance is computable from the RND: $\sigma_{m_i}^2 \approx \Delta_i^2 \cdot \text{Var}(\partial m_i / \partial S_t) \cdot \sigma_{S}^2$ to leading order, where $\Delta_i = \partial m_i / \partial S$ is the bucket's "delta" with respect to the underlying (§6.1). The Avellaneda–Stoikov optimal-spread formula [17],

$$
\delta_i^a + \delta_i^b \;=\; \gamma_i \sigma_{m_i}^2 (T-t) + \frac{2}{\gamma_i}\ln\!\left(1 + \frac{\gamma_i}{k_i}\right),
$$

with order-arrival decay $k_i$ estimated from Kalshi fills, transfers with the caveat that the fill-intensity calibration is empirical and thin: Kalshi's volume in any single bucket is orders of magnitude smaller than a liquid futures top-of-book, and the Poisson-intensity ansatz is therefore noisy. (Inherited from Phase 02 §4.1; the application to per-bucket binaries is newly specified.)

### 3.2 Cartea–Jaimungal for discrete payoff grids

Cartea, Jaimungal and Penalva (2015) [Phase 02 ref. 3] develop the multi-asset stochastic-control framework with cross-inventory penalties that is the natural home for Kalshi's bucket grid. Writing the joint state $\mathbf{q} = (q_1, \ldots, q_n)$, the HJB value function $V(t, \mathbf{q}, \mathbf{m})$ satisfies

$$
V_t + \sum_i \mu_i V_{m_i} + \tfrac{1}{2}\sum_{i,j}\Sigma_{ij}\, V_{m_i m_j} + \sum_i \max_{\delta_i^{a,b}}\!\left\{\lambda_i^{a,b}(\delta)\,\big[V(\mathbf{q}\mp e_i) - V(\mathbf{q}) \pm \delta_i^{a,b}\big]\right\} = 0,
$$

with the cross-bucket covariance $\Sigma_{ij}$ — crucial, because bucket Yes prices are *highly* cross-correlated: a move in $S$ that pushes one bucket's probability up pushes an adjacent bucket's down. In practice, the reservation price becomes a *matrix* skew against inventory,

$$
r_i(t) \;=\; m_i(t) \;-\; \gamma\,(T-t)\,\sum_j \Sigma_{ij} q_j,
$$

so a long position in bucket $i$ lowers *both* the bucket-$i$ quote (own-inventory) and the adjacent bucket-$j$ quotes (cross-inventory via $\Sigma_{ij}$). This is the formal generalization of GLFT's [Phase 02 ref. 15] hard-inventory-cap scheme to the multi-asset discrete case. (Inherited framework; specific soybean-grid application new.)

### 3.3 Queue-position modeling on Kalshi's CLOB

Kalshi runs price-time FIFO with five-level depth visibility (Phase 07 §5); Cont and de Larrard's Markovian-queue model [Phase 02 ref. 7] and Huang–Lehalle–Rosenbaum's queue-reactive model [Phase 02 ref. 20] both transfer structurally. The estimated probability that the next book event is a trade-through at the Kalshi best,

$$
P(\text{trade through at } p_i^{a}\mid q^a_i) \;=\; \frac{\mu_i}{\mu_i + \nu_i},
$$

with $\mu_i$ the market-order intensity into the ask and $\nu_i$ the cancellation intensity, is the right quantity to govern when a resting Yes ask is likely to be filled versus walked. The caveat is liquidity: a liquid ZS top-of-book queue depth of tens-of-thousands of contracts shrinks to Kalshi bucket queue depths measured in hundreds or low thousands of contracts, at which regime the Poisson-arrival assumption holds weakly and the model's variance is large. (Transfer from Phase 02; liquidity caveat new.)

## 4. Pricing models that do not transfer cleanly

### 4.1 Continuous Glosten–Milgrom at bucket edges

Glosten and Milgrom (1985) [Phase 02 ref. 12] derive adverse-selection-driven spreads from Bayesian updating on trade signs under a *continuous* value $V \in \{V_L, V_H\}$ whose expected value shifts smoothly with trade flow. On a Kalshi bucket, the payoff function $g_i$ is discontinuous exactly at the strike edges $\ell_i$ and $u_i$. Near those edges the informed-trader's expected gain from hitting a stale quote is no longer proportional to the quote-shift; it is proportional to the *probability of crossing the edge*, which is itself a cliff function of $S_T$. The continuous-quote adverse-selection decomposition breaks: the optimal protective spread has a jump-diffusion flavor rather than a linear-update flavor. Operationally, a quoting engine needs an explicit edge-proximity term that widens the spread when $m_i$ is near 0.5 *and* $S_t$ is near $\ell_i$ or $u_i$. (New reasoning; not treated in Phase 02.)

### 4.2 LMSR vs CLOB — why the prediction-market AMM literature does not apply

Hanson's Logarithmic Market Scoring Rule [11] and its variants (Othman–Pennock–Reeves–Sandholm liquidity-sensitive automated market maker [12]; Chen–Pennock survey [13]) are mechanisms for an *automated market maker* to quote a full distribution subject to a bounded worst-case loss. The LMSR sets the price of outcome $\omega$ as

$$
p_\omega(\mathbf{q}) \;=\; \frac{\exp(q_\omega/b)}{\sum_{\omega'} \exp(q_{\omega'}/b)},
$$

where $q_\omega$ is the net outstanding quantity on outcome $\omega$ and $b$ is the liquidity parameter; the worst-case subsidy is $b \ln n$ for $n$ outcomes. Kalshi is *not* an LMSR — Phase 07 established that Kalshi is a price-time CLOB with resting limit orders (Rule 5.9). There is no cost-function AMM, no automatic subsidized liquidity, and no bounded-loss guarantee to the venue.

The practical consequences: (i) the LMSR property that the sum of outcome prices exactly equals one at all times *by construction* does not hold on Kalshi — it is a no-arbitrage condition that emerges only when traders enforce it, and is often violated intraweek by 2–5 cents of slack net of fees. (ii) The LMSR subsidy that guarantees a two-sided quote at all prices does not apply; a Kalshi quote book can deepen or thin at the MM's discretion, and can be empty on both sides if no one is resting. (iii) Polymarket, though a prediction market, runs a Polygon-backed CLOB and is structurally closer to Kalshi than to an AMM prediction market like Augur; comparisons to LMSR literature should be made via structural analogy to AMM DEXes (Uniswap-style) rather than via direct transfer [14]. (New reasoning; literature cited for completeness.)

## 5. Adverse selection on a prediction market

Wolfers and Zitzewitz (2004, 2006) [15][16] frame prediction-market prices as probability estimators biased toward 50% on short-dated contracts — a fingerprint of risk-neutral-ish retail flow plus a long tail of informed participants. For Kalshi commodity weeklies the mix is plausibly:

*Retail punters* buy round-number buckets anchored on prevailing spot; they pay wide spreads and produce mean-reverting, essentially information-free order flow. *Sharp quants* running Kalshi–CME arbitrage (this project) hit quotes when the RND-implied bucket price diverges from the Yes quote by more than fees; they are aggressive at the cheap side. *Fundamental traders* — an agronomist with a weather-ensemble view, a basis desk with private export-demand info — concentrate positions on one or two neighboring buckets and dominate adverse selection on WASDE and Export Sales days. *Momentum chasers* follow the ZS tick stream; their flow is auto-correlated but information-free.

Two structural asymmetries matter. *Near-spot vs far-from-spot*: adverse selection is lowest at out-of-the-money tails (little informed edge on a 2% tail event in a given week) and highest at at-the-money buckets where informed fundamentals discriminate among candidate outcomes. *Near vs far from expiry*: early in the week, adverse selection is structural and reflects fundamental traders' persistent informational advantage; late in the week, it concentrates around USDA releases and the Friday snapshot, and quotes must widen through those windows (Phase 02 §7.4). (New reasoning; builds on Phase 02 §§3, 7.)

## 6. Hedging

### 6.1 Synthetic delta from bucket positions

For fixed bucket edges $\partial \ell_i/\partial S = \partial u_i/\partial S = 0$, the bucket delta is the difference of the deltas of the two bracketing digital calls:

$$
\Delta_i^{K}(S,t) \;=\; \int_{\ell_i}^{u_i}\!\frac{\partial f_T(x\mid S,t)}{\partial S}\, dx \;=\; \frac{\partial D(\ell_i,T)}{\partial S} - \frac{\partial D(u_i,T)}{\partial S}.
$$

Under a Black–Scholes-style reference, the digital delta is $\phi(d_2)/(S\sigma\sqrt{T-t})$ [17][18], so bucket deltas peak for ATM buckets and decay for tails — the same shape as a vanilla-call gamma. For a book $\{q_i\}$, the aggregate is $\Delta^{\text{port}} = \sum_i q_i \Delta_i^K$, and the ZS-futures hedge is $-\Delta^{\text{port}}/N_{ZS}$ contracts, with $N_{ZS} = 5{,}000$ bushels per ZS (Phase 01). Kalshi notional is $1 per contract, so $\Delta^{\text{port}}$ is in dollars per bushel and divides cleanly. (New calculation; Phase 02 §4 framework.)

### 6.2 Gamma and vega — hedging with ZS options

Bucket gamma $\Gamma_i^K = \partial^2 m_i/\partial S^2$ is large and bi-polar near bucket edges and small in the interior [17]. Yes contracts near ATM therefore carry substantial gamma that cannot be neutralized with futures. The clean hedge is a tight ZS-option vertical spread around each bucket edge: it exactly replicates the digital-corridor structure (§1), neutralizing delta, gamma, and vega in one static construction [10][19][20], modulo the §2.4 timing adjustment. The binding cost is the CME ZS option bid–ask, typically 1–3¢ on liquid strikes and 5+¢ on the wings.

Rule of thumb: hedge gamma/vega with ZS options when (i) a single bucket's position is large enough that gamma-driven P&L variance on a typical weekly ZS move dominates the vertical-spread cost, and (ii) surface liquidity avoids a feedback loop. Small books delta-hedge in futures and carry the residual gamma/vega.

### 6.3 Basis risk

Three residual basis risks: *reference-price basis* (Kalshi snapshot vs CME option reference — daily settle vs 2:20 p.m. CT close vs VWAP window introduces $\sigma_{\text{snap}}\sqrt{\Delta t}$ of P&L noise per bucket); *timing basis* (Kalshi expiry on a non-CME-standard Friday forces the vertical-spread hedge to be held past Kalshi settlement, carrying Brownian ZS variance that is not in the Kalshi position); *contract-month basis* (roll-window weeks may force use of deferred-month options at a liquidity cost).

### 6.4 Capital efficiency

Kalshi positions are fully cash-collateralized: $0.30 Yes costs $0.30 per contract (Phase 07 §4). CME ZS futures SPAN-margin at ~5–8% of notional; ZS option vertical spreads SPAN-margin on portfolio variance and are typically *cheaper* than their premium. The Kalshi leg is therefore the binding capital constraint in most hedged trades — an inversion of the usual options-desk intuition where option premium is small relative to futures margin. (New reasoning.)

## 7. Inventory and risk limits

Per-bucket inventory caps are straightforward under Kalshi's position-limit framework (Phase 07 §5): Rule 5.19 expresses limits in dollars of max-loss, so on a $0.30 Yes bucket the per-member cap of $25{,}000$ (assumed default) translates to $\lfloor 25000/0.30 \rfloor = 83{,}333$ contracts on the Yes side. Market-maker-program exemptions raise this by an order of magnitude (Chapter 4). The more binding constraint is the *book*-level aggregate net delta cap, which for a hedged book means a dollar-notional cap on unhedged $\Delta^{\text{port}}$ after the §6.1 synthetic-delta calculation.

Scenario-based risk limits layer on top. Concretely: (i) a *WASDE-day* scenario computes the P&L of the current book under a set of historical WASDE-day ZS moves (Phase 02 §7.4; Mosquera et al. 2024), and caps notional such that the worst-decile move produces a loss within risk-manager tolerance. (ii) A *weather-shock* scenario stress-tests against a sudden 3–5% gap, with stochastic vol expansion, reflecting the Phase 02 Bates-SVJ intuition [Phase 02 §6]. (iii) An *expiry-day liquidity collapse* scenario assumes the Kalshi bucket cannot be unwound at any price during the Friday settlement window and marks to intrinsic — the book must survive that scenario even if the MM pulls quotes. (New application; risk framework inherited from Phase 02 §§7.1, 7.4.)

Transaction costs and fees are non-trivial and must sit inside the inventory-limit formula. Phase 07 §6 quotes the Kalshi taker fee as $\lceil 0.07\, P(1-P)\,100\rceil/100$, peaking at 2¢ per contract at $P=0.50$. A round-trip maker-then-taker trade on a 50¢ bucket costs ~0.5¢ maker + 2¢ taker = 2.5¢ on $1 notional = 250 bps. CME options and futures hedges add CME exchange fees (~$1/contract) and FCM commissions (~$0.50/contract) plus the ZS option bid–ask (1–5¢ = 0.02–0.1% of notional depending on strike). Any quoting decision that ignores round-trip cost is systematically biased toward over-quoting inside-the-spread.

## 8. Information events inside the weekly expiry window

Phase 06 §4 catalogued the scheduled events inside a typical April-through-August week: WASDE (monthly, mid-month, 12 p.m. ET), Crop Progress (weekly Mon 4 p.m. ET), Weekly Export Sales (Thu 8:30 a.m. ET), FGIS Grain Inspections (Mon afternoon), Grain Stocks (quarterly), Prospective Plantings (March 31) and Acreage (June 30). Additional unscheduled events include weather-driven moves, GEFS/ECMWF forecast updates (four daily cycles), and SMAP soil-moisture swings.

Each event should move the *quoted distribution* — not just the mid — in two ways. First, the *mean* of the implied distribution shifts: a bullish WASDE or Export Sales number pushes probability mass toward higher buckets; a drought-shock forecast pushes it toward higher buckets and *widens* the distribution. Second, the *variance* expands pre-release and contracts post-release: the Mosquera et al. (2024) [Phase 02 ref. 33] U-shape on WASDE days is exactly what the spread profile should mirror.

Operationally, the quoting engine should maintain a deterministic event calendar with per-event parameters $(\kappa_t^{\text{spread}}, \kappa_t^{\text{width}})$ that multiplicatively widen bucket spreads and widen the implied variance of the RND in a window around the release. Cartea–Jaimungal's deterministic-jump-intensity extension [Phase 02 ref. 3] handles this formally; practically, the MM pulls quotes 30–60 seconds before each scheduled release, waits for the CME option surface to re-calibrate, re-runs the RND pipeline, and reposts. Outside scheduled windows, continuous weather-forecast cycles are slow fair-value updates handled through the §2.4 measure overlay; they do not trigger quote pulls but they do shift $m_i$ deterministically. (Transfer from Phase 02 §§6, 7.4, with Phase 06 event calendar.)

## 9. Prototype pricing pipeline

The architecture below maps Phase 06 data streams into pricing stages. No code; module decomposition only.

*A — Surface ingest.* Stream CME MDP 3.0 tick-by-tick for ZS futures and ZS options (full chain, including weekly and short-dated new-crop) [Phase 06 §2]. Accumulate mid-implied-volatility per strike per expiry; enforce put-call parity within $\varepsilon$ to prune outliers.

*B — Surface smoothing.* Calibrate an SVI slice [2] per relevant expiry under Gatheral–Jacquier butterfly and calendar no-arbitrage constraints. Fall back to a Bliss–Panigirtzoglou cubic spline [4] if SVI residuals exceed threshold.

*C — RND extraction.* Differentiate the smoothed call surface twice in strike for $f_T^{\text{opt}}$ at the CME expiry (Breeden–Litzenberger [1]). Paste GEV tails at the edges [7][9]. Propagate to the Kalshi expiry $T^K$ via forward-variance rescaling.

*D — Bucket probability.* Integrate $f_T$ over each bucket to obtain $\pi_i^0 = \mathbb{Q}(\ell_i \le S_T < u_i)$; normalize to enforce $\sum_i \pi_i^0 = 1$.

*E — Measure overlay.* Apply the Kalshi-vs-risk-neutral tilt (§2.4) calibrated to historical Kalshi-settled vs ZS-option-implied prints; default to identity with flagged uncertainty.

*F — Reservation price.* Compute $r_i = m_i - \gamma(T-t)\sum_j \Sigma_{ij} q_j$ (§3.2), with $\Sigma_{ij}$ derived by perturbing the RND under a unit move in $S$.

*G — Adverse-selection / queue skew.* Add the Cartea–Jaimungal–Ricci adverse-selection term keyed to short-horizon OFI on both Kalshi Yes-side *and* CME ZS trade flow.

*H — Spread sizing.* Set $\delta_i^a + \delta_i^b$ via the GLFT closed-form with $\sigma^2 \to \sigma_{m_i}^2$ and empirically-calibrated $(A_i, k_i)$. Floor at maker+taker fees plus required edge.

*I — Hedge.* Compute $\Delta^{\text{port}}$ plus the vertical-spread gamma hedge (§6); send ZS futures and option orders to the CME gateway; reconcile each second.

*J — Risk gating.* Enforce per-bucket and aggregate-delta caps; stress the book against WASDE/weather/liquidity-collapse scenarios (§7); block quotes that would breach thresholds.

*K — Quote/cancel-repost.* Post orders via Kalshi REST `/portfolio/orders` with `post_only`; subscribe to WebSocket `orderbook_delta`, `ticker`, `trade`, `fill`. Re-quote on: ZS mid move, surface recalibration, inventory change post-fill, scheduled-event approach. Respect rate limits with token-bucket scheduling and exponential backoff on 429.

*L — P&L attribution.* Weekly, attribute realized P&L across quoting edge, inventory MTM, hedge carry/slippage, and fee drag; feed back into $(A_i, k_i, \gamma)$ and the §2.4 overlay. (New architecture; components across Phases 02, 06, 07.)

## 10. Open modeling questions

The pipeline above has calibration-heavy components that cannot be pinned down without live data. The open empirical questions are:

1. *What is the empirical bias and variance of Kalshi bucket Yes prices vs ZS-option-implied RND probabilities, over the first 12–24 Kalshi-settled weeks?* This sets the §2.4 measure overlay.
2. *What is the fill-intensity function $\lambda_i(\delta)$ on Kalshi bucket quotes, and how does it vary by bucket location (ATM vs tail), time-of-day (Kalshi trades 24/7, including weekends, unlike CME), and proximity to a USDA release?*
3. *What is the empirical cross-bucket probability covariance $\Sigma_{ij}$ intraday, and does it match the RND-implied covariance?*
4. *What is the realized adverse-selection signature (post-trade mark-out at 1m, 5m, 30m) of Kalshi fills, and does it spike around WASDE/ESR/Crop Progress windows in the way Phase 02 §7.4 predicts?*
5. *What is the basis between the Kalshi reference snapshot and the CME option reference expiry value, in cents, historically?*
6. *What tail-fitting method (GEV vs mixed-lognormal vs Bollinger–Melick–Thomas) gives the lowest calibration error on the Kalshi open-ended tail buckets over the first settled year?*
7. *Do Kalshi bucket Yes prices sum to 1.00 across the grid in practice, or is there a persistent bid–ask arbitrage slack? If so, what is its size and persistence?*
8. *What is the regime-change in fill intensity and adverse-selection around the known front-month roll window, and does Kalshi's reference-contract-month rule add or subtract basis volatility?*
9. *How does the Polymarket–Kalshi price difference on equivalent (or near-equivalent) commodity-event contracts behave — cointegrated at a wedge, or freely divergent? A cross-venue edge may dominate the RND-implied edge in some weeks.*
10. *What is the marginal economic value of the §2.3 Figlewski tail-paste vs a crude lognormal extrapolation, measured as realized P&L on the open-ended end buckets?*

---

## Key takeaways

- A Kalshi weekly soybean bucket is a digital-corridor option on the CBOT reference price with one-dollar notional and a $0.01–$0.99 price band; the Yes price of each bucket is the measure-$\mathbb{Q}^K$ probability of the reference falling in the bucket's edges, undiscounted by virtue of full cash collateralization.
- The CME ZS option surface, smoothed via SVI or cubic-spline-in-IV and differentiated twice in strike, gives the risk-neutral density that prices each bucket as a definite integral (Breeden–Litzenberger). Figlewski-style GEV tails cover the open-ended end buckets.
- Avellaneda–Stoikov reservation-price and GLFT spread logic transfer to the per-bucket problem with $\sigma^2$ replaced by the bucket-probability variance. Cartea–Jaimungal multi-asset cross-inventory penalties are the correct generalization for a grid with high bucket-to-bucket correlation.
- Continuous-quote Glosten–Milgrom intuition breaks at bucket strike edges: the adverse-selection premium inherits a digital cliff that requires an explicit edge-proximity widening term.
- Kalshi's CLOB is structurally different from the LMSR / cost-function AMM literature (Hanson; Othman–Pennock). That literature applies to Augur-style prediction markets, not Kalshi or Polymarket, and should only be cited as structural analogy.
- Aggregate bucket-book delta hedges cleanly in ZS futures; gamma and vega hedge via tight vertical spreads in ZS options, which replicate the bucket digital-corridor exactly. Basis risks remain across snapshot timing, reference-contract roll, and Kalshi-vs-option expiry.
- Fees and transaction costs are material and must sit inside the quoting formula: Kalshi's $\lceil 0.07\,P(1-P)\rceil$ taker fee peaks at 2¢ per contract at $P=0.50$, and a round-trip maker-then-taker on a 50¢ bucket is 250 bps of notional before CME hedge costs.
- Scheduled USDA information events (WASDE, Export Sales, Crop Progress, etc.) drive deterministic spread-widening and quote-pull logic; unscheduled weather forecast cycles drive slow fair-value updates to the implied distribution.
- The pipeline has ten-plus calibration-heavy components whose values cannot be pinned down without live Kalshi data; an empirical research program on Kalshi-settled outcomes is the binding prerequisite to productionizing any pricing engine.
- No claim is made here that the math "works" — only that the math transfers from CME options and futures market-making to Kalshi weekly buckets, with the exceptions and caveats above.

---

## References

1. [Breeden, D. T. & Litzenberger, R. H. (1978). Prices of state-contingent claims implicit in option prices. *Journal of Business*, 51(4), 621–651.](https://faculty.baruch.cuny.edu/lwu/890/BreedenLitzenberger78.pdf)
2. [Gatheral, J. & Jacquier, A. (2014). Arbitrage-free SVI volatility surfaces. *Quantitative Finance*, 14(1), 59–71.](https://arxiv.org/abs/1204.0646)
3. [Hagan, P. S., Kumar, D., Lesniewski, A. S. & Woodward, D. E. (2002). Managing smile risk. *Wilmott Magazine*, September 2002, 84–108.](http://www.deriscope.com/docs/Hagan_2002.pdf)
4. [Bliss, R. R. & Panigirtzoglou, N. (2002). Testing the stability of implied probability density functions. *Journal of Banking & Finance*, 26(2–3), 381–422.](https://pages.stern.nyu.edu/~dbackus/Disasters/BlissPanigirtzoglou%20JF%2004.pdf)
5. [Shimko, D. (1993). Bounds of probability. *Risk*, 6(4), 33–37.](https://www.researchgate.net/publication/306151578_Bounds_of_probability)
6. [Malz, A. M. (2014). A simple and reliable way to compute option-based risk-neutral distributions. Federal Reserve Bank of New York, Staff Reports No. 677.](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr677.pdf)
7. [Figlewski, S. (2010). Estimating the implied risk-neutral density for the U.S. market portfolio. In *Volatility and Time Series Econometrics: Essays in Honor of Robert Engle*, Oxford University Press.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1256783)
8. [Figlewski, S. (2018). Risk-neutral densities: A review. *Annual Review of Financial Economics*, 10, 329–359.](https://pages.stern.nyu.edu/~sfiglews/documents/RND%20Review%20ver4.pdf)
9. [Bollinger, T., Melick, W. R. & Thomas, C. P. (2023). Principled pasting: Attaching tails to risk-neutral probability density functions recovered from option prices.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4673540)
10. [Carr, P. & Madan, D. (1998). Towards a theory of volatility trading. In *Volatility: New Estimation Techniques for Pricing Derivatives*, Risk Books, 417–427.](https://engineering.nyu.edu/sites/default/files/2019-03/Carr-static-hedging-of-exotic-options.pdf)
11. [Hanson, R. (2003). Combinatorial information market design. *Information Systems Frontiers*, 5(1), 107–119; Hanson, R. (2007). Logarithmic market scoring rules for modular combinatorial information aggregation.](https://mason.gmu.edu/~rhanson/mktscore.pdf)
12. [Othman, A., Pennock, D. M., Reeves, D. M. & Sandholm, T. (2013). A practical liquidity-sensitive automated market maker. *ACM Transactions on Economics and Computation*, 1(3), 14.](https://www.cs.cmu.edu/~sandholm/www/liquidity-sensitive%20automated%20market%20maker.teac.pdf)
13. [Chen, Y. & Pennock, D. M. (2010). Designing markets for prediction. *AI Magazine*, 31(4), 42–52.](https://onlinelibrary.wiley.com/doi/abs/10.1609/aimag.v31i4.2313)
14. [Polymarket CLOB vs Kalshi CLOB — structural comparison. Polymarket Analytics / Tradealgo.](https://polymarketanalytics.com/polymarket-vs-kalshi)
15. [Wolfers, J. & Zitzewitz, E. (2004). Prediction markets. *Journal of Economic Perspectives*, 18(2), 107–126.](https://www.aeaweb.org/articles?id=10.1257/0895330041371321)
16. [Wolfers, J. & Zitzewitz, E. (2006). Interpreting prediction market prices as probabilities. NBER Working Paper 12200.](https://www.nber.org/system/files/working_papers/w12200/w12200.pdf)
17. [Avellaneda, M. & Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance*, 8(3), 217–224. (Phase 02 ref. 1.)](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf)
18. [Quantpie — Cash-or-nothing digital Greeks (delta, gamma) under Black–Scholes.](https://www.quantpie.co.uk/bsm_bin_c_formula/bs_bin_c_summary.php)
19. [Carr, P. & Wu, L. (2002). Static hedging of standard options.](https://engineering.nyu.edu/sites/default/files/2019-01/CarrStandardOptionsJuly2002-a.pdf)
20. [Derman, E., Ergener, D. & Kani, I. (1994). Static options replication. Goldman Sachs Quantitative Strategies Research Notes.](https://emanuelderman.com/wp-content/uploads/1994/04/static_options_replication.pdf)
21. [Federal Reserve Bank of New York — NYU Stern Conference on Risk Neutral Densities (2008).](https://www.stern.nyu.edu/sites/default/files/assets/documents/con_044169.pdf)
22. [CME Group — CBOT Agricultural Short-Term Options.](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)
23. [CME Group — Short-Term Options in Commodities: Potential Benefits and Applications (2024).](https://www.cmegroup.com/articles/2024/short-term-options-in-commodities-potential-benefits-and-applications.html)
24. [Cboe Volatility Index Mathematics Methodology (for the variance-swap replication weighting underlying CVOL-style indices).](https://cdn.cboe.com/resources/indices/Cboe_Volatility_Index_Mathematics_Methodology.pdf)
25. [Cartea, Á., Jaimungal, S. & Penalva, J. (2015). *Algorithmic and High-Frequency Trading*. Cambridge University Press. (Phase 02 ref. 3.)](https://assets.cambridge.org/97811070/91146/frontmatter/9781107091146_frontmatter.pdf)

Cross-phase references (internal):

26. Phase 02 — Market Making Pricing Models: From Ho–Stoll to Commodity-Specific Adaptations. `./research/phase_02_market_making_pricing_models.md`.
27. Phase 06 — Data Streams for Pricing the Soybean Complex. `./research/phase_06_data_streams.md`.
28. Phase 07 — Kalshi Weekly Soybean Price-Range Contract: Structural Dissection. `./research/phase_07_kalshi_contract_structure.md`.
