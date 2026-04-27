# Audit C — Phase 08 Synthesis: Pricing Kalshi Weekly Soybean Range Grid

## 1. Source artifact scope

`research/phase_08_synthesis_pricing.md` is a synthesis document that lays out
the mathematical and operational scaffolding for pricing the Kalshi
`KXSOYBEANW` weekly soybean range-grid contracts as digital-corridor
derivatives on the CBOT ZS reference. It assembles, from prior phases, a
pricing pipeline grounded in the Breeden–Litzenberger risk-neutral density,
SVI / cubic-spline IV smoothing, Figlewski-style GEV tails, and the
Avellaneda–Stoikov / Cartea–Jaimungal market-making control framework, while
explicitly flagging which prior literature transfers (continuous MM control,
RND extraction, queue models) and which does not (continuous Glosten–Milgrom
adverse selection at bucket edges; Hanson LMSR / cost-function AMM
literature). It specifies a per-bucket digital-corridor decomposition,
multi-asset cross-inventory skew, ZS-option vertical-spread hedging, scenario
risk caps, USDA-event-aware quote pulls, and an A→L module pipeline; it
closes with ten open empirical questions that gate calibration. The file
mixes inherited mathematical identities from peer-reviewed literature with
explicitly flagged "new reasoning" and "practitioner" rules-of-thumb.

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C08-01 | Each `KXSOYBEANW-YYMONDD-i` Market is a Kalshi "Yes" contract with one-dollar notional that pays $1 if the settlement reference $S_T$ lies in $[\ell_i, u_i)$ and zero otherwise. | §1, lines 9–11 | established | contract;pricing-model |
| C08-02 | The bucket set $\{[\ell_i, u_i)\}_{i=1}^n$ partitions $[0, \infty)$ via two open-ended tail buckets and $n-2$ fixed-width interior buckets anchored on round numbers in cents per bushel. | §1, line 11 | established | contract;market-structure |
| C08-03 | The exact identity of $S_T$ (CBOT Rule 813 daily settlement on the front-month ZS contract — ZSK26 for the April 24, 2026 Event — vs an alternate snapshot) is pending Appendix A confirmation and must be carried as a configuration parameter. | §1, line 11 | debated | contract;data-ingest |
| C08-04 | Yes-side terminal payoff is the indicator $g_i(S_T) = \mathbf{1}\{\ell_i \le S_T < u_i\}$. | §1, lines 13–17 | established | pricing-model |
| C08-05 | Time-$t$ Kalshi-fair Yes price under measure $\mathbb{Q}^K$ is $\text{value}_i(t) = \mathbb{E}^{\mathbb{Q}^K}[g_i(S_T)\mid \mathcal{F}_t] = \mathbb{Q}^K(\ell_i \le S_T < u_i \mid \mathcal{F}_t)$. | §1, lines 19–23 | established | pricing-model;density |
| C08-06 | Kalshi positions are fully cash-collateralized with zero variation margin (Rule 6.1(b)); there is no discounting between trade and settlement, so the Yes price is the probability (not the discounted probability) up to a collateral-yield adjustment. | §1, line 25 | established | contract;pricing-model |
| C08-07 | This zero-discounting property differs from the standard Breeden–Litzenberger digital derivation on standard options, where the digital price is $e^{-r(T-t)}\mathbb{Q}(\cdot)$. | §1, line 25 | established | pricing-model |
| C08-08 | Each bucket admits the digital-corridor decomposition $g_i(S_T) = \mathbf{1}\{S_T \ge \ell_i\} - \mathbf{1}\{S_T \ge u_i\}$, so the Yes price is the difference of two cash-or-nothing digital-call prices on $S_T$ at strikes $\ell_i$ and $u_i$. | §1, lines 27–33 | established | pricing-model |
| C08-09 | Each digital is the limit of a narrow vertical call spread: $\mathbf{1}\{S_T \ge K\} = \lim_{\varepsilon\downarrow 0} \frac{1}{\varepsilon}[\max(S_T-(K-\varepsilon),0)-\max(S_T-K,0)]$. | §1, lines 35–37 | established | pricing-model;hedging |
| C08-10 | A Kalshi bucket is a tradable, finite-width call spread on the CME ZS reference; the Kalshi quote surface and the CME option surface are two discretizations of the same conditional distribution. | §1, line 39 | established | pricing-model;density |
| C08-11 | Breeden–Litzenberger identity: $f_T(K) = e^{r(T-t)} \partial^2 C(K,T)/\partial K^2$. | §2.1, lines 47–49 | established | density;pricing-model |
| C08-12 | Digital-call price equals the negative first strike-derivative: $D(K,T) = -\partial C/\partial K$. | §2.1, line 51 | established | density;pricing-model |
| C08-13 | Kalshi bucket price equals the difference of digital prices, equal to the integrated density: $\text{value}_i = D(\ell_i,T) - D(u_i,T) = \int_{\ell_i}^{u_i} f_T(x)\,dx$. | §2.1, line 51 | established | density;pricing-model |
| C08-14 | The Breeden–Litzenberger formula is model-free — it does not require Black–Scholes. | §2.1, line 51 | established | density |
| C08-15 | Raw CME option prices for ZS are neither continuous in strike nor arbitrage-free; differentiating them twice produces catastrophic noise. | §2.2, line 55 | established | data-ingest;density |
| C08-16 | Standard practice smooths in implied-volatility space and re-prices, rather than differentiating raw prices. | §2.2, line 55 | established | density;pricing-model |
| C08-17 | Gatheral SVI parameterization: $w(k) = a + b\{\rho(k-m) + \sqrt{(k-m)^2 + \sigma^2}\}$ where $w$ is total implied variance and $k = \ln(K/F)$. | §2.2, line 57 | established | density;pricing-model |
| C08-18 | Gatheral–Jacquier (2014) identify the constraint set on SVI parameters that yields a static-arbitrage-free fit (non-negative density and monotone bucket prices). | §2.2, line 57 | established | density;pricing-model |
| C08-19 | SABR (Hagan–Kumar–Lesniewski–Woodward 2002) gives a closed-form implied-vol asymptotic with parameters $(\alpha, \beta, \rho, \nu)$. | §2.2, line 58 | established | density |
| C08-20 | The classic Hagan SABR expansion can be arbitrageable at deep-OTM strikes, exactly where Kalshi tail buckets live; an arbitrage-free SABR variant is required. | §2.2, line 58 | established | density;pricing-model |
| C08-21 | Bliss–Panigirtzoglou (2002) cubic splines on $(\Delta, \sigma_{\text{imp}})$ with vega-weighted knots are a standard alternative; cubic spline is the modern Fed/central-bank default; Shimko (1993) used a quadratic. | §2.2, line 59 | established | density |
| C08-22 | The Kalshi-weekly workhorse is an SVI slice calibrated to the CBOT weekly or short-dated option surface at the closest expiry. | §2.2, line 61 | practitioner-lore | density;pricing-model |
| C08-23 | On weeks without a co-terminal weekly option, fall back to a Malz-style (2014) cubic spline on the standard-option surface, re-clocked via forward-variance interpolation. | §2.2, line 61 | practitioner-lore | density;pricing-model |
| C08-24 | The Kalshi grid includes two open-ended tail buckets `<$X` and `≥$Y` whose density regions have few or no listed CME strikes. | §2.3, line 65 | established | contract;density |
| C08-25 | Relying on SVI/SABR extrapolation in the open-ended tail regions under-quotes true tail mass. | §2.3, line 65 | established | density;pricing-model |
| C08-26 | Figlewski (2010, 2019) GEV-tail attachment: piecewise density $f_T = f_{\text{GEV,lower}}$ for $x \le x_L$, $f_{\text{BL}}$ for $x_L < x < x_U$, $f_{\text{GEV,upper}}$ for $x \ge x_U$. | §2.3, lines 67–74 | established | density |
| C08-27 | GEV parameters are pinned by matching the density value and first derivative at the paste points $x_L, x_U$. | §2.3, line 76 | established | density |
| C08-28 | Bollinger–Melick–Thomas (2023) extend Figlewski with more principled paste-point selection. | §2.3, line 76 | established | density |
| C08-29 | The tail-paste procedure directly sets the Yes-price floor/cap on the open-ended end buckets. | §2.3, line 76 | established | density;pricing-model |
| C08-30 | Kalshi's weekly expiry is Friday at 1:20 p.m. CT (the CBOT settlement window). | §2.4, line 80 | established | contract;data-ingest |
| C08-31 | Listed CBOT standard options expire on the last Friday before contract month; weekly ZS options expire each Friday not already covered by a standard expiry. | §2.4, line 80 | established | contract;data-ingest |
| C08-32 | For the April 24, 2026 Event, the nearest ZS standard option (on ZSK26) also expires April 24, so expiries coincide. | §2.4, line 82 | established | contract |
| C08-33 | When Kalshi and CME-option expiries do not coincide, compute the density at the nearest CME expiry $T^{\text{opt}}$ and propagate to $T^K$ via Heston-style variance rescaling or a Gatheral calendar-arbitrage-constrained SVI re-fit across expiries. | §2.4, line 82 | established | density;pricing-model |
| C08-34 | Short-dated new-crop weekly options cover February through August. | §2.4, line 82 | established | data-ingest;market-structure |
| C08-35 | Near First Notice Day, the Kalshi "front-month" reference may differ from the richest option-surface contract; the pricing engine needs a contract-month configuration keyed to the Kalshi Event ticker. | §2.4, line 83 | debated | contract;data-ingest |
| C08-36 | Whether Kalshi rolls with CME's calendar or tracks most-active is pending Appendix A confirmation. | §2.4, line 83 | debated | contract |
| C08-37 | The ZS-option RND is the risk-neutral distribution for CME futures; the appropriate Kalshi measure is whatever makes Yes prices equal expected payoffs for the marginal Kalshi participant — these can differ. | §2.4, line 84 | debated | density;pricing-model |
| C08-38 | Prediction-market prices are empirically biased toward 50% on short-dated contracts (Wolfers–Zitzewitz). | §2.4, line 84; §5, line 150 | established | pricing-model;market-structure |
| C08-39 | A conservative engine starts from the risk-neutral RND and marks an explicit spread (measure overlay) on top, as a second calibration layer. | §2.4, line 84 | practitioner-lore | pricing-model;density |
| C08-40 | Per-bucket Avellaneda–Stoikov reservation price: $r_i(t) = m_i(t) - q_i \gamma_i \sigma_{m_i}^2 (T-t)$. | §3.1, lines 91–95 | established | pricing-model;inventory |
| C08-41 | $\sigma_{m_i}^2$ is the mid-price variance of the bucket *probability* (not the underlying futures variance); to leading order $\sigma_{m_i}^2 \approx \Delta_i^2 \cdot \text{Var}(\partial m_i/\partial S_t) \cdot \sigma_S^2$ with $\Delta_i = \partial m_i/\partial S$. | §3.1, line 96 | established | pricing-model;density |
| C08-42 | Avellaneda–Stoikov optimal half-spread sum: $\delta_i^a + \delta_i^b = \gamma_i \sigma_{m_i}^2 (T-t) + \frac{2}{\gamma_i}\ln(1 + \gamma_i/k_i)$. | §3.1, lines 97–101 | established | pricing-model;strategy |
| C08-43 | Order-arrival decay $k_i$ must be estimated empirically from Kalshi fills. | §3.1, line 102 | established | strategy;backtest |
| C08-44 | Kalshi's volume in any single bucket is orders of magnitude smaller than a liquid futures top-of-book, so the Poisson-intensity ansatz underlying $\lambda(\delta) = A e^{-k\delta}$ is noisy on Kalshi. | §3.1, line 102 | practitioner-lore | strategy;backtest;market-structure |
| C08-45 | Cartea–Jaimungal–Penalva multi-asset HJB: $V_t + \sum_i \mu_i V_{m_i} + \tfrac{1}{2}\sum_{i,j}\Sigma_{ij}V_{m_i m_j} + \sum_i \max_{\delta^{a,b}_i}\{\lambda^{a,b}_i(\delta)[V(\mathbf{q}\mp e_i)-V(\mathbf{q})\pm\delta^{a,b}_i]\} = 0$, with cross-bucket covariance $\Sigma_{ij}$. | §3.2, lines 107–111 | established | pricing-model;inventory |
| C08-46 | Kalshi bucket Yes prices are highly cross-correlated: a move in $S$ that pushes one bucket's probability up pushes an adjacent bucket's down. | §3.2, line 112 | established | density;pricing-model |
| C08-47 | Multi-asset reservation price is a matrix skew against inventory: $r_i(t) = m_i(t) - \gamma(T-t)\sum_j \Sigma_{ij} q_j$. | §3.2, lines 113–117 | established | pricing-model;inventory |
| C08-48 | A long position in bucket $i$ should lower both the bucket-$i$ quote (own-inventory) and adjacent bucket-$j$ quotes (cross-inventory via $\Sigma_{ij}$). | §3.2, line 118 | established | pricing-model;inventory |
| C08-49 | The matrix-skew formulation is the formal generalization of GLFT's hard-inventory-cap scheme to the multi-asset discrete case. | §3.2, line 118 | established | pricing-model;inventory |
| C08-50 | Kalshi runs price-time FIFO with five-level depth visibility. | §3.3, line 121 | established | market-structure;oms |
| C08-51 | Cont–de Larrard Markovian-queue and Huang–Lehalle–Rosenbaum queue-reactive models transfer structurally to Kalshi's CLOB. | §3.3, line 121 | established | strategy;market-structure |
| C08-52 | Probability that next book event is a trade-through at the Kalshi best ask: $P(\text{trade through at } p_i^a \mid q_i^a) = \mu_i/(\mu_i + \nu_i)$, with $\mu_i$ market-order intensity and $\nu_i$ cancellation intensity. | §3.3, lines 123–127 | established | strategy;oms |
| C08-53 | Kalshi bucket queue depths in hundreds or low thousands of contracts (vs ZS top-of-book in tens of thousands) make the Poisson-arrival assumption hold weakly with large model variance. | §3.3, line 128 | practitioner-lore | strategy;market-structure |
| C08-54 | DOES NOT TRANSFER: Continuous Glosten–Milgrom adverse-selection decomposition fails near Kalshi bucket edges because $g_i$ is discontinuous at $\ell_i, u_i$ and the informed gain is proportional to a cliff function rather than a smooth quote-shift. | §4.1, line 134 | established | pricing-model;strategy |
| C08-55 | Optimal protective spread near bucket edges has a jump-diffusion flavor rather than a linear-update flavor. | §4.1, line 134 | debated | pricing-model;strategy |
| C08-56 | A quoting engine needs an explicit edge-proximity term that widens the spread when $m_i$ is near 0.5 *and* $S_t$ is near $\ell_i$ or $u_i$. | §4.1, line 134 | debated | pricing-model;strategy |
| C08-57 | DOES NOT TRANSFER: Hanson LMSR / Othman–Pennock cost-function AMM literature does not apply to Kalshi because Kalshi is a price-time CLOB with resting limit orders (Rule 5.9), not an automated market maker. | §4.2, lines 137–144 | established | market-structure;pricing-model |
| C08-58 | LMSR price formula (for reference, not transferable): $p_\omega(\mathbf{q}) = \exp(q_\omega/b)/\sum_{\omega'} \exp(q_{\omega'}/b)$; worst-case subsidy $b\ln n$ for $n$ outcomes. | §4.2, lines 139–143 | established | pricing-model |
| C08-59 | DOES NOT TRANSFER: The LMSR property that outcome prices sum to 1 by construction does not hold on Kalshi; it is a no-arbitrage condition that emerges only when traders enforce it. | §4.2, line 146 | established | pricing-model;market-structure |
| C08-60 | Kalshi outcome-price-sum-to-1 condition is often violated intraweek by 2–5 cents of slack net of fees. | §4.2, line 146 | practitioner-lore | market-structure;backtest |
| C08-61 | DOES NOT TRANSFER: LMSR's two-sided-quote subsidy guarantee does not apply; a Kalshi quote book can deepen, thin, or be empty on both sides at MM discretion. | §4.2, line 146 | established | market-structure;oms |
| C08-62 | Polymarket runs a Polygon-backed CLOB and is structurally closer to Kalshi than to AMM prediction markets like Augur; LMSR comparisons should be made via structural analogy to AMM DEXes (Uniswap-style) rather than direct transfer. | §4.2, line 146 | established | market-structure |
| C08-63 | Practitioner taxonomy of Kalshi commodity-weekly flow: retail punters, sharp quants (Kalshi–CME arb), fundamental traders, momentum chasers. | §5, lines 150–152 | practitioner-lore | market-structure;strategy |
| C08-64 | Retail punters buy round-number buckets anchored on prevailing spot, pay wide spreads, and produce mean-reverting, essentially information-free order flow. | §5, line 152 | practitioner-lore | strategy;market-structure |
| C08-65 | Sharp quants hit quotes when the RND-implied bucket price diverges from the Yes quote by more than fees; they are aggressive at the cheap side. | §5, line 152 | practitioner-lore | strategy |
| C08-66 | Fundamental traders concentrate positions on one or two neighboring buckets and dominate adverse selection on WASDE and Export Sales days. | §5, line 152 | practitioner-lore | strategy |
| C08-67 | Momentum chasers follow the ZS tick stream; their flow is autocorrelated but information-free. | §5, line 152 | practitioner-lore | strategy |
| C08-68 | Adverse selection is lowest at out-of-the-money tails (little informed edge on a 2% tail event) and highest at at-the-money buckets where informed fundamentals discriminate. | §5, line 154 | debated | strategy;pricing-model |
| C08-69 | Early in the week, adverse selection is structural and reflects fundamental traders' persistent informational advantage; late in the week, it concentrates around USDA releases and the Friday snapshot — quotes must widen through those windows. | §5, line 154 | debated | strategy;pricing-model |
| C08-70 | Bucket delta with fixed edges ($\partial \ell_i/\partial S = \partial u_i/\partial S = 0$): $\Delta_i^K(S,t) = \int_{\ell_i}^{u_i}\partial f_T(x\mid S,t)/\partial S\, dx = \partial D(\ell_i,T)/\partial S - \partial D(u_i,T)/\partial S$. | §6.1, lines 159–163 | established | hedging;density |
| C08-71 | Under a Black–Scholes-style reference, digital delta is $\phi(d_2)/(S\sigma\sqrt{T-t})$. | §6.1, line 166 | established | hedging |
| C08-72 | Bucket deltas peak for ATM buckets and decay for tails — the same shape as a vanilla-call gamma. | §6.1, line 166 | established | hedging |
| C08-73 | Aggregate book delta: $\Delta^{\text{port}} = \sum_i q_i \Delta_i^K$; ZS-futures hedge is $-\Delta^{\text{port}}/N_{ZS}$ contracts, with $N_{ZS} = 5{,}000$ bushels per ZS futures contract. | §6.1, line 166 | established | hedging;inventory |
| C08-74 | Kalshi notional is $1 per contract, so $\Delta^{\text{port}}$ is in dollars per bushel and divides cleanly against ZS futures notional. | §6.1, line 166 | established | hedging;contract |
| C08-75 | Bucket gamma $\Gamma_i^K = \partial^2 m_i/\partial S^2$ is large and bi-polar near bucket edges and small in the interior. | §6.2, line 170 | established | hedging |
| C08-76 | Yes contracts near ATM carry substantial gamma that cannot be neutralized with futures alone. | §6.2, line 170 | established | hedging |
| C08-77 | A tight ZS-option vertical spread around each bucket edge replicates the digital-corridor structure exactly, neutralizing delta, gamma, and vega in one static construction (modulo §2.4 timing adjustment). | §6.2, line 170 | established | hedging |
| C08-78 | CME ZS option bid–ask is typically 1–3¢ on liquid strikes and 5+¢ on the wings — the binding cost of the static vertical-spread hedge. | §6.2, line 170 | practitioner-lore | hedging;market-structure |
| C08-79 | Practitioner rule: hedge gamma/vega with ZS options when (i) a single bucket's position is large enough that gamma-driven P&L variance on a typical weekly ZS move dominates the vertical-spread cost, AND (ii) surface liquidity avoids a feedback loop. | §6.2, line 172 | practitioner-lore | hedging;strategy |
| C08-80 | Small books delta-hedge in futures and carry residual gamma/vega. | §6.2, line 172 | practitioner-lore | hedging;strategy |
| C08-81 | Three residual basis risks: reference-price basis (Kalshi snapshot vs CME option reference — daily settle vs 2:20 p.m. CT close vs VWAP window — introduces $\sigma_{\text{snap}}\sqrt{\Delta t}$ of P&L noise per bucket); timing basis (Kalshi expiry on a non-CME-standard Friday); contract-month basis (roll-window weeks may force deferred-month options). | §6.3, line 176 | established | hedging;contract |
| C08-82 | Kalshi positions are fully cash-collateralized: $0.30 Yes costs $0.30 per contract. | §6.4, line 180 | established | contract;inventory |
| C08-83 | CME ZS futures SPAN-margin at ~5–8% of notional. | §6.4, line 180 | established | hedging;inventory |
| C08-84 | ZS option vertical spreads SPAN-margin on portfolio variance and are typically *cheaper* than their premium. | §6.4, line 180 | practitioner-lore | hedging;inventory |
| C08-85 | The Kalshi leg is the binding capital constraint in most hedged trades — an inversion of the usual options-desk intuition where option premium is small relative to futures margin. | §6.4, line 180 | debated | inventory;hedging |
| C08-86 | Under Kalshi Rule 5.19 (limits in dollars of max-loss), on a $0.30 Yes bucket the assumed $25,000 per-member cap translates to $\lfloor 25000/0.30 \rfloor = 83{,}333$ contracts on the Yes side. | §7, line 184 | debated | inventory;contract |
| C08-87 | Market-maker-program exemptions raise per-bucket caps by an order of magnitude (Chapter 4). | §7, line 184 | established | inventory;contract |
| C08-88 | The more binding constraint is a book-level aggregate net delta cap — a dollar-notional cap on unhedged $\Delta^{\text{port}}$ after the §6.1 synthetic-delta calculation. | §7, line 184 | practitioner-lore | inventory;hedging |
| C08-89 | Required scenario tests: (i) WASDE-day P&L under historical WASDE-day ZS moves, capped to worst-decile within risk-manager tolerance; (ii) weather-shock 3–5% gap with stochastic vol expansion (Bates-SVJ); (iii) expiry-day liquidity-collapse — Kalshi bucket cannot be unwound, marks to intrinsic. | §7, line 186 | practitioner-lore | inventory;backtest |
| C08-90 | Kalshi taker fee: $\lceil 0.07\,P(1-P)\,100\rceil/100$, peaking at 2¢ per contract at $P=0.50$. | §7, line 188 | established | contract;pricing-model |
| C08-91 | Round-trip maker-then-taker on a 50¢ bucket costs ~0.5¢ maker + 2¢ taker = 2.5¢ on $1 notional ≈ 250 bps. | §7, line 188 | established | pricing-model;backtest |
| C08-92 | CME options/futures hedges add CME exchange fees (~$1/contract) and FCM commissions (~$0.50/contract) plus ZS option bid–ask of 1–5¢ (≈0.02–0.1% of notional depending on strike). | §7, line 188 | practitioner-lore | hedging;pricing-model |
| C08-93 | Quoting decisions ignoring round-trip cost are systematically biased toward over-quoting inside the spread. | §7, line 188 | established | pricing-model;strategy |
| C08-94 | Scheduled USDA event calendar inside a typical April–August week: WASDE (monthly, mid-month, 12 p.m. ET), Crop Progress (weekly Mon 4 p.m. ET), Weekly Export Sales (Thu 8:30 a.m. ET), FGIS Grain Inspections (Mon afternoon), Grain Stocks (quarterly), Prospective Plantings (March 31), Acreage (June 30). | §8, line 192 | established | data-ingest;observability |
| C08-95 | Unscheduled drivers: weather-driven moves, GEFS/ECMWF forecast updates (four daily cycles), SMAP soil-moisture swings. | §8, line 192 | established | data-ingest;observability |
| C08-96 | Each scheduled event should move the *quoted distribution* in two ways: the mean of the implied distribution shifts, and the variance expands pre-release and contracts post-release (Mosquera et al. 2024 U-shape on WASDE days). | §8, line 194 | established | density;pricing-model |
| C08-97 | The quoting engine should maintain a deterministic event calendar with per-event parameters $(\kappa_t^{\text{spread}}, \kappa_t^{\text{width}})$ that multiplicatively widen bucket spreads and widen the implied variance of the RND in a window around the release. | §8, line 196 | practitioner-lore | strategy;observability;oms |
| C08-98 | Operational protocol: pull quotes 30–60 seconds before each scheduled release, wait for the CME option surface to re-calibrate, re-run the RND pipeline, then repost. | §8, line 196 | practitioner-lore | oms;strategy |
| C08-99 | Continuous weather-forecast cycles are slow fair-value updates handled through the §2.4 measure overlay; they do not trigger quote pulls but they shift $m_i$ deterministically. | §8, line 196 | practitioner-lore | strategy;density |
| C08-100 | Pipeline stage A — Surface ingest: stream CME MDP 3.0 tick-by-tick for ZS futures and ZS options (full chain including weekly and short-dated new-crop); accumulate mid-implied-volatility per strike per expiry; enforce put-call parity within $\varepsilon$ to prune outliers. | §9, line 202 | established | data-ingest;observability |
| C08-101 | Pipeline stage B — Surface smoothing: calibrate an SVI slice per relevant expiry under Gatheral–Jacquier butterfly and calendar no-arbitrage constraints; fall back to a Bliss–Panigirtzoglou cubic spline if SVI residuals exceed threshold. | §9, line 204 | established | density;pricing-model |
| C08-102 | Pipeline stage C — RND extraction: differentiate the smoothed call surface twice in strike for $f_T^{\text{opt}}$ at the CME expiry; paste GEV tails at the edges; propagate to the Kalshi expiry $T^K$ via forward-variance rescaling. | §9, line 206 | established | density;pricing-model |
| C08-103 | Pipeline stage D — Bucket probability: integrate $f_T$ over each bucket to obtain $\pi_i^0 = \mathbb{Q}(\ell_i \le S_T < u_i)$; normalize to enforce $\sum_i \pi_i^0 = 1$. | §9, line 208 | established | density;pricing-model |
| C08-104 | Pipeline stage E — Measure overlay: apply Kalshi-vs-risk-neutral tilt calibrated to historical Kalshi-settled vs ZS-option-implied prints; default to identity with flagged uncertainty. | §9, line 210 | debated | density;pricing-model |
| C08-105 | Pipeline stage F — Reservation price: compute $r_i = m_i - \gamma(T-t)\sum_j \Sigma_{ij} q_j$ with $\Sigma_{ij}$ derived by perturbing the RND under a unit move in $S$. | §9, line 212 | established | pricing-model;inventory |
| C08-106 | Pipeline stage G — Adverse-selection / queue skew: add the Cartea–Jaimungal–Ricci adverse-selection term keyed to short-horizon OFI on both Kalshi Yes-side and CME ZS trade flow. | §9, line 214 | debated | pricing-model;strategy |
| C08-107 | Pipeline stage H — Spread sizing: set $\delta_i^a + \delta_i^b$ via the GLFT closed-form with $\sigma^2 \to \sigma_{m_i}^2$ and empirically-calibrated $(A_i, k_i)$; floor at maker+taker fees plus required edge. | §9, line 216 | established | pricing-model;strategy |
| C08-108 | Pipeline stage I — Hedge: compute $\Delta^{\text{port}}$ plus the vertical-spread gamma hedge; send ZS futures and option orders to the CME gateway; reconcile each second. | §9, line 218 | practitioner-lore | hedging;oms |
| C08-109 | Pipeline stage J — Risk gating: enforce per-bucket and aggregate-delta caps; stress the book against WASDE / weather / liquidity-collapse scenarios; block quotes that would breach thresholds. | §9, line 220 | established | inventory;oms |
| C08-110 | Pipeline stage K — Quote/cancel-repost: post orders via Kalshi REST `/portfolio/orders` with `post_only`; subscribe to WebSocket `orderbook_delta`, `ticker`, `trade`, `fill`; re-quote on (ZS mid move, surface recalibration, inventory change post-fill, scheduled-event approach); respect rate limits with token-bucket scheduling and exponential backoff on 429. | §9, line 222 | established | oms;data-ingest |
| C08-111 | Pipeline stage L — Weekly P&L attribution across quoting edge, inventory MTM, hedge carry/slippage, and fee drag, fed back into $(A_i, k_i, \gamma)$ and the §2.4 measure overlay. | §9, line 224 | practitioner-lore | observability;backtest |
| C08-112 | Open empirical question: empirical bias and variance of Kalshi bucket Yes prices vs ZS-option-implied RND probabilities over the first 12–24 Kalshi-settled weeks, which sets the §2.4 measure overlay. | §10, line 230 | debated | density;pricing-model;backtest |
| C08-113 | Open empirical question: fill-intensity function $\lambda_i(\delta)$ on Kalshi bucket quotes and how it varies by bucket location (ATM vs tail), time-of-day (Kalshi trades 24/7, including weekends, unlike CME), and proximity to USDA releases. | §10, line 231 | debated | strategy;backtest |
| C08-114 | Open empirical question: empirical cross-bucket probability covariance $\Sigma_{ij}$ intraday and whether it matches the RND-implied covariance. | §10, line 232 | debated | density;backtest |
| C08-115 | Open empirical question: realized adverse-selection signature (post-trade mark-out at 1m, 5m, 30m) of Kalshi fills, and whether it spikes around WASDE/ESR/Crop Progress windows as Phase 02 §7.4 predicts. | §10, line 233 | debated | strategy;backtest |
| C08-116 | Open empirical question: basis between the Kalshi reference snapshot and the CME option reference expiry value, in cents, historically. | §10, line 234 | debated | hedging;contract |
| C08-117 | Open empirical question: which tail-fitting method (GEV vs mixed-lognormal vs Bollinger–Melick–Thomas) yields lowest calibration error on Kalshi open-ended tail buckets over the first settled year. | §10, line 235 | debated | density;backtest |
| C08-118 | Open empirical question: whether Kalshi bucket Yes prices sum to 1.00 across the grid in practice, or there is a persistent bid–ask arbitrage slack, and its size and persistence. | §10, line 236 | debated | market-structure;backtest |
| C08-119 | Open empirical question: regime-change in fill intensity and adverse selection around the front-month roll window, and whether Kalshi's reference-contract-month rule adds or subtracts basis volatility. | §10, line 237 | debated | strategy;contract;backtest |
| C08-120 | Open empirical question: Polymarket–Kalshi price differences on equivalent or near-equivalent commodity-event contracts — cointegrated at a wedge, or freely divergent — with cross-venue edge potentially dominating the RND-implied edge in some weeks. | §10, line 238 | debated | strategy;market-structure |
| C08-121 | Open empirical question: marginal economic value of the Figlewski tail-paste vs a crude lognormal extrapolation, measured as realized P&L on the open-ended end buckets. | §10, line 239 | debated | density;backtest |
| C08-122 | Key takeaway: a Kalshi weekly soybean bucket is a digital-corridor option on the CBOT reference price with one-dollar notional and a $0.01–$0.99 price band. | Key takeaways, line 245 | established | contract;pricing-model |
| C08-123 | Key takeaway: no claim is made that the math "works" — only that the math transfers from CME options/futures market-making to Kalshi weekly buckets, with the stated exceptions and caveats. | Key takeaways, line 254 | debated | pricing-model |

## 3. What this file does NOT claim

The synthesis is deliberately silent on several topics that a code-actionable
audit might expect:

- It does not specify a numerical value for the Kalshi-vs-risk-neutral
  measure tilt — only that one likely exists and must be calibrated post-hoc
  (C08-104, C08-112).
- It does not commit to a single tail-fitting method for code; GEV vs
  mixed-lognormal vs Bollinger–Melick–Thomas is left as an open empirical
  question (C08-117). A code path must therefore be pluggable, not
  hard-coded.
- It does not specify the bucket-grid edge values, count, or interior width
  for any specific Event week — those facts are deferred to Phase 07 and the
  pending Appendix A.
- It does not specify the value of the risk-aversion coefficient $\gamma$
  (or per-bucket $\gamma_i$) used in the Avellaneda–Stoikov / Cartea–Jaimungal
  formulas; calibration is implicitly left to live-data empirics.
- It does not commit to fees on the maker side beyond a "~0.5¢" round-figure;
  no formula is given.
- It does not commit to the actual reference price $S_T$ (CBOT settlement vs
  alternate snapshot) — flagged as an explicit open configuration question
  (C08-03).
- It does not specify how to compute the cross-bucket covariance matrix
  $\Sigma_{ij}$ in code beyond "perturb the RND under a unit move in $S$"
  (C08-105) — the perturbation size, kernel, and covariance estimator are
  unspecified.
- It does not give Kalshi rate-limit numbers for the REST/WebSocket APIs;
  only mentions token-bucket scheduling and 429 backoff (C08-110).
- It does not commit to a specific stochastic-vol model behind the
  variance-rescaling propagation (Heston-style is mentioned but not
  parameterized) (C08-33).
- It does not address transaction-cost analysis methodology beyond a P&L
  attribution at weekly cadence (C08-111); intraday slippage measurement is
  not specified.
- It does not address what to do when CME and Kalshi are simultaneously
  closed/open mismatch (Kalshi 24/7 vs CME hours) for spread maintenance
  beyond the open empirical question (C08-113).
- It does not give a concrete latency budget for the A→L pipeline.

## 4. Cross-links (inferable from context)

- C08-03, C08-35, C08-36: depend on Phase 07's `Appendix A` (reference price
  and front-month rule); their resolution is a precondition for the
  pricing-engine config schema.
- C08-30, C08-31, C08-34, C08-94, C08-95: data-ingest claims that depend on
  Phase 06's data-stream catalogue (CME MDP 3.0, weekly options coverage,
  USDA event calendar). C08-100 explicitly references Phase 06 §2.
- C08-40, C08-42, C08-45, C08-49: inherit the Avellaneda–Stoikov and
  Cartea–Jaimungal control machinery from Phase 02 §4.1 and Phase 02 ref. 3;
  the file explicitly flags these as "Inherited from Phase 02".
- C08-51, C08-52: inherit Cont–de Larrard / Huang–Lehalle–Rosenbaum queue
  models from Phase 02 refs 7 and 20.
- C08-54, C08-55, C08-56: explicitly contradict the unmodified application
  of Phase 02's continuous-quote Glosten–Milgrom adverse-selection
  decomposition (Phase 02 ref. 12) — the file calls out "not treated in
  Phase 02".
- C08-57, C08-59, C08-61: explicitly rule out direct application of Hanson
  LMSR / Othman–Pennock literature to the Kalshi CLOB (Phase 07 §5 / Rule
  5.9) — these contradict any prior phase that may have framed Kalshi as an
  AMM-style prediction market.
- C08-86, C08-87: depend on Phase 07 §5 (Kalshi position-limit framework,
  Rule 5.19, Chapter 4 MM exemptions).
- C08-89, C08-96: depend on Phase 02 §7.4 (Mosquera et al. 2024 WASDE-day
  U-shape) and Phase 02 §6 (Bates-SVJ stochastic-vol-jump intuition).
- C08-90, C08-91: depend on Phase 07 §6 (Kalshi taker-fee formula).
- C08-100, C08-110: depend on Phase 06 §2 (CME MDP 3.0 stream) and Phase 07
  Kalshi REST/WebSocket schema (the `/portfolio/orders`, `post_only`,
  `orderbook_delta`, `ticker`, `trade`, `fill` references).
- C08-83: standard SPAN-margin figure; potentially cross-checkable against
  any phase that catalogues CME margin assumptions.
- C08-118, C08-120: claims about Kalshi/Polymarket structural similarity
  (C08-62) connect to whatever phase handles cross-venue analysis; the file
  flags this as a research thread, not a settled empirical fact.
- C08-38: Wolfers–Zitzewitz 50%-bias result is cited twice in this file
  (§2.4 and §5) and underpins the conservative measure-overlay default
  (C08-39, C08-104) — any other phase that estimates a different prediction-
  market bias would contradict this default.
