# Phase 05 — Systematic / Quantitative Strategies in Commodity Futures, with Focus on Grains and Soybeans

## Abstract

Systematic strategies in commodity futures rest on a small set of return drivers — trend, carry, momentum, mean reversion around physical constraints, fundamental imbalance, and micro-frictions — each of which has a published academic backbone and a practitioner implementation refined by the large managed-futures shops. This survey walks the canonical families as they apply to the grain and soybean complex. Trend-following, built on Donchian breakout and Moskowitz–Ooi–Pedersen time-series momentum with volatility scaling, remains the dominant managed-futures archetype (Dunn, Man AHL, Winton, Campbell, Chesapeake). Carry strategies — sorting contracts on the futures basis à la Erb–Harvey (2006) and Koijen–Moskowitz–Pedersen–Vrugt (2018) — earn compensation for bearing hedging imbalance. Cross-sectional momentum, seasonality, crush-spread cointegration, stocks-to-use econometrics, NDVI-driven yield nowcasts, and order-flow-imbalance signals each make a contribution, with performance that varies from robust (trend, carry) through fragile (seasonality) to capacity-constrained (microstructure). Post-publication decay (McLean–Pontiff 2016), capacity asymmetries between grains and energy, and transaction-cost sensitivity are the binding constraints that separate a research Sharpe from a live-money Sharpe. Citations span the Journal of Financial Economics, Journal of Finance, Management Science, Review of Financial Studies, Journal of Banking & Finance, Journal of Futures Markets, AQR / Man / Aspect / Campbell white papers, the NBER, farmdoc, and the CFTC.

---

## 1. Trend-following / CTA strategies

### 1.1 The signal family

Trend-following on grains comes in three closely related specifications, all of which reduce to "buy strength, sell weakness, size by volatility."

**Moving-average crossover.** Let $p_t$ be the settle, and define fast and slow simple moving averages $\mathrm{MA}_s(p,n)$ and $\mathrm{MA}_l(p,m)$ with $n<m$ (classically $n=10, m=50$ or $n=50, m=200$). The position sign is

$$
s_t=\operatorname{sign}\bigl(\mathrm{MA}_s(p_t,n)-\mathrm{MA}_l(p_t,m)\bigr).
$$

The moving-average framework traces directly to Richard Donchian's 1950s commentary on the futures markets and is the conceptual ancestor of every modern CTA book ([Donchian Channels background, LuxAlgo](https://www.luxalgo.com/blog/donchian-channels-breakout-and-trend-following-strategy/)).

**Donchian breakout.** Long the market if $p_t$ exceeds the prior $N$-day high; short if it breaks the prior $N$-day low:

$$
s_t=\begin{cases}+1 & p_t > \max(p_{t-1},\dots,p_{t-N})\\ -1 & p_t<\min(p_{t-1},\dots,p_{t-N})\end{cases}.
$$

Donchian's two canonical parameters are $N=20$ for the faster "system 1" and $N=55$ for "system 2" — the same parameters Richard Dennis and the Turtles adopted in the early 1980s ([Strike.money Donchian primer](https://www.strike.money/technical-analysis/donchian-channel); [TradingCode](https://www.tradingcode.net/tradingview/donchian-channel-breakout/)).

**Time-series momentum (TSMOM).** Moskowitz, Ooi, and Pedersen (2012) formalize the trend premium in 58 liquid futures and forwards. The signal is the sign of excess return over a lookback — typically twelve months — scaled by inverse realized volatility to equalize contribution across assets:

$$
w_t^i=\frac{c\cdot \operatorname{sign}(r^i_{t-12,t})}{\sigma^i_t},\qquad R^{\text{TSMOM}}_{t+1}=\sum_i w_t^i\,r^i_{t+1}.
$$

Here $c$ is a vol-target constant (e.g. 40%), and $\sigma^i_t$ is an ex-ante volatility forecast (exponentially weighted or GARCH). The paper reports a diversified Sharpe near 1.6 gross of costs over 1985–2009 on the 58-market universe and shows speculator profits from TSMOM come at the expense of hedgers ([Moskowitz, Ooi & Pedersen, "Time Series Momentum," JFE 2012](https://www.sciencedirect.com/science/article/pii/S0304405X11002613); [Pedersen working paper](http://docs.lhpedersen.com/TimeSeriesMomentum.pdf)).

**Volatility scaling / parity.** CTAs virtually never hold a constant notional. Either each contract is sized to inverse ex-ante volatility (vol parity) or the whole book is leveraged to a target portfolio volatility (vol targeting). Concretum Group and Rattray–van Hemert document that vol targeting improves the Sharpe of risk-asset portfolios but has a near-neutral effect on commodities once the strategy is already long-short ([Rattray & van Hemert, "The Impact of Volatility Targeting"](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf); [Concretum Group, "Position Sizing in Trend-Following"](https://concretumgroup.com/position-sizing-in-trend-following-comparing-volatility-targeting-volatility-parity-and-pyramiding/)).

### 1.2 A century of evidence and the crisis-alpha claim

Hurst, Ooi, and Pedersen extend TSMOM back to 1880 across 67 markets and report a gross Sharpe near 1.0 on the 1-3-12 equal-weighted trend basket, with statistically significant alpha in every sub-decade except the 1930s and 2010s ([Hurst, Ooi & Pedersen, "A Century of Evidence on Trend-Following Investing," AQR 2012](https://openaccess.city.ac.uk/id/eprint/18554/7/SSRN-id2520075.pdf)). The durability result is what underwrites managed-futures fee structures: trend is a diversifier that has paid positive returns in most equity bear markets, the "crisis alpha" thesis ([Kaminski, "Trend Following with Managed Futures"](https://rpc.cfainstitute.org/research/financial-analysts-journal/2015/trend-following-with-managed-futures); [Campbell, "Trend Following from a Multi-Asset Perspective"](https://www.riverweycapital.com/wp-content/uploads/2018/02/Crisis-Alpha-Everywhere-Campbell-Company.pdf)).

### 1.3 Named-fund archetypes

- **Dunn Capital** (founded 1974 by Bill Dunn): the WMA (World Monetary and Agriculture) program is 100% systematic long-term trend-following trading around 60 markets, with a composite track record that has compounded in the high-teens since inception ([IASG profile](https://www.iasg.com/groups/dunn-capital-management); [Top Traders Unplugged, "Half a Century of Trend Following Experience"](https://www.toptradersunplugged.com/half-a-century-of-trend-following-experience/); [Hedgeweek 2024 profile](https://www.hedgeweek.com/dunn-capital-management-llc-best-cta/)). Note: the 19% CAGR is a pre-fee/composite claim — documented windows and drawdowns vary; 2001–2008 and 2019–2022 are the positive decades, 2009–2013 and 2015–2017 were materially negative.
- **Man AHL** (founded 1987): runs Diversified, Evolution, and Alpha — hundreds of models across 400–800 markets. The 2022 Man paper "Gaining Momentum" and the 2018 "Equity and Bond Crisis Alpha" make the diversified-trend case ([Man AHL, "Trend Following and Drawdowns"](https://www.man.com/insights/is-this-time-different); [Hedge Fund Journal, "Man AHL Marks 30 Years"](https://thehedgefundjournal.com/man-ahl-marks-30-years/)).
- **Winton** (founded 1997 by David Harding, ex-AHL): historically pure trend, then diversified into non-trend quant after 2014 as trend Sharpe compressed. Harding publicly de-emphasized pure trend around 2018 ([Risk.net, "Harding on turning away from trend following"](https://www.risk.net/asset-management/5788876/wintons-david-harding-on-turning-away-from-trend-following)).
- **Campbell & Company** (founded 1972): published white papers on rate-regime independence and skew taming ([CME / Campbell, "Prospects for CTAs in a Rising Rate Environment"](https://www.cmegroup.com/education/files/prospects-for-ctas-in-a-rising-interest-rate-environment.pdf); [Kaminski, "Quantifying CTA Risk Management"](https://caia.org/sites/default/files/AIAR_Q1_2016_04_Kaminsky_CTARiskManagement.pdf)).
- **Chesapeake Capital** (Jerry Parker, Turtle alumnus): long-horizon Donchian plus breakout variants, multi-decade track record.
- **Aspect Capital** (Martin Lueck, ex-AHL) documents the drawdown reality — March 2016 to September 2021 was Aspect's longest underwater period, underscoring that published Sharpes of 0.6–1.0 come with 5-plus-year flat or losing stretches ([Aspect, "Living with Trend Following"](https://aspectcapital.s3.amazonaws.com/documents/Aspect_Capital_Insight_-_Living_With_Trend_Following_History__Lessons_From_the_8LAzOwQ.pdf); [Hedge Fund Journal, "Aspect Capital"](https://thehedgefundjournal.com/aspect-capital-resurgence-in-trend-following-performance/)).

### 1.4 Performance caveats on grains specifically

Grains are a smaller contributor to CTA P&L than rates, FX, and equity indices — AHL-style portfolios run roughly 15–25% weight in agricultural commodities as a group and 3–6% specifically in soybeans complex markets. The canonical Moskowitz et al. TSMOM result reports Sharpe near 1.6 on the 58-market portfolio but individual-market Sharpes are in the 0.2–0.5 range ([Moskowitz et al.](https://www.sciencedirect.com/science/article/pii/S0304405X11002613)), consistent with diversification carrying most of the weight. On single-market grain trend — ZS alone, 1985–2015, 1-month/3-month/12-month TSMOM — published back-tests (e.g. Clare et al., Miffre co-authored studies) report gross Sharpes of 0.25–0.45 before costs. After a realistic 3–5 ticks round-trip and roll slippage, that falls to 0.15–0.3; the uplift over the raw number comes from combining ZS with ZC, ZW, ZM, ZL and financials, not from ZS alone.

---

## 2. Carry / term-structure strategies

### 2.1 Definition

With futures prices $F_t^{T_1}$ (near) and $F_t^{T_2}$ (deferred, $T_2>T_1$), the annualized carry (Koijen et al. definition) is

$$
C_t=\frac{F_t^{T_1}-F_t^{T_2}}{F_t^{T_2}}\cdot\frac{1}{T_2-T_1}.
$$

Backwardation means $C_t>0$ (long-carry); contango means $C_t<0$ (negative carry). A fully collateralized long position, absent spot price change, earns approximately $C_t$ per unit time from roll alone.

### 2.2 Erb–Harvey's central finding

Erb and Harvey (2006) build an equal-weighted fully collateralized portfolio of twelve commodity futures 1982–2004 and show that although the average individual commodity futures excess return is near zero, the *rebalanced* portfolio earns an equity-like Sharpe, and the cross-section of historical returns is explained almost entirely by the futures basis: ranking commodities by roll return explains roughly 91% of the cross-sectional variance in performance ([Erb & Harvey, "The Strategic and Tactical Value of Commodity Futures," FAJ 2006](https://www.tandfonline.com/doi/abs/10.2469/faj.v62.n2.4084); [SSRN version](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=650923); [full-text PDF](https://static.twentyoverten.com/593e8a9e7299b471eaecf644/rkr4DL67G/The-Strategic-and-Tactical-Value-of-Commodity-Futures.pdf)). The construction sorts the universe into long-high-carry / short-low-carry quintiles and reports ~10–12% gross annualized spread return over the 1982–2004 window before costs.

### 2.3 The global-carry synthesis

Koijen, Moskowitz, Pedersen, and Vrugt (JFE 2018) generalize carry to equities, bonds, currencies, options, and credit, showing carry predicts both time-series and cross-sectional returns after controlling for known predictors. Their diversified carry portfolio delivers Sharpe above 0.8 gross over 1983–2012 ([Koijen, Moskowitz, Pedersen & Vrugt, "Carry," JFE 2018](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf); [Wharton PDF](https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2014/06/Carry.pdf); [CME, "An Introduction to Global Carry"](https://www.cmegroup.com/education/files/an-introduction-to-global-carry.pdf)). Baltas (2017) extends to multi-asset optimization and reports gross carry Sharpes ranging from 0.19 for commodities alone to 0.85 for government bonds, with multi-asset diversification producing a combined carry book with Sharpe above 1.0 ([Baltas, "Optimising Cross-Asset Carry" SSRN 2968677](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2968677)).

### 2.4 Practical construction on grains

On the soy complex, carry strategies typically use the second-month vs. front-month basis, with the *deferred* pair (e.g., July vs. November for old-crop/new-crop soybeans) as a seasonally cleaner signal. Fuertes, Miffre, and Rallis (2010) run the double-sort — momentum × term structure — across a broad commodity universe and report an annualized 21% alpha pre-cost for the combined strategy over 1979–2007, decomposed into roughly 10% from momentum alone and 12% from term structure alone ([Fuertes, Miffre & Rallis, "Tactical Allocation in Commodity Futures Markets," JBF 2010](https://www.sciencedirect.com/science/article/abs/pii/S0378426610001354); [SSRN 1127213](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1127213)).

### 2.5 Theoretical foundations: normal backwardation vs. storage

Keynes (1930) and Hicks (1939) postulated normal backwardation — producer hedging pressure forces futures below expected spot, creating a compensation for speculators. Cootner (1960) provided early empirical support on agricultural contracts. Bessembinder (1992) and Carter–Rausser–Schmitz (1983) show commercial positioning correlates with risk premium, though Gorton–Hayashi–Rouwenhorst (2012) argue the effect is really about inventories not hedgers ([Gorton, Hayashi & Rouwenhorst, "The Fundamentals of Commodity Futures Returns," NBER WP 13249](https://www.nber.org/system/files/working_papers/w13249/w13249.pdf)). In the soybean complex, the Working (1949) / Brennan (1958) storage curve is observable: when inventories are low (late summer before new-crop harvest), spreads are inverted and roll yield is positive; at the November / January new-crop flush the curve is in carry and the roll yield turns negative — textbook motivation for seasonal overlays on the pure carry signal ([Wikipedia, "Theory of Storage"](https://en.wikipedia.org/wiki/Theory_of_storage); [Garcia, Irwin & Smith, "Commodity Storage under Backwardation: Does the Working Curve Still Work?"](https://legacy.farmdoc.illinois.edu/irwin/research/commoditystorage2013.pdf)).

---

## 3. Seasonality systems

### 3.1 The signal

Let $r_t^{\text{ex}}=r_t-\bar r$ be the de-meaned daily log return, where $\bar r$ is the estimated long-run drift. Aggregate by calendar day $d(t)$ across the panel to form the seasonal component

$$
\hat s_d=\frac{1}{K}\sum_{k=1}^{K}r_{t(d,k)}^{\text{ex}}.
$$

A seasonal strategy sizes $w_t\propto \hat s_{d(t+h)}$ for horizon $h$. Practical strategies truncate to "long the strongest month, short the weakest" or apply a threshold.

### 3.2 Canonical grain seasonals

Moore Research Center publishes composites that require 80%+ of prior 15 years to align, with minimum holding window and minimum average profit — an explicit in-sample filter ([CME-hosted Moore Soybean Report](https://www.cmegroup.com/education/interactive/moore-report/pdf/AC-167_MooreSoybeanFinal.pdf)). Jake Bernstein popularized calendar composites on July/November soybean spreads in his *Seasonal Futures Spreads* (1990). The two most cited composites on ZS: a seasonal low in October harvest and a spring/summer peak around late June — mean reversion from harvest pressure and pricing-in of weather risk respectively.

### 3.3 Statistical significance and overfitting

Farmdoc's critique cuts hard. Over the last fifteen years the soybean cash price has been higher at harvest than in spring in only three years (2015, 2019, 2024), and only about 20% of years conform cleanly to the composite path ([Farmdoc Daily, "Seasonal Price Rally in Soybeans"](https://farmdocdaily.illinois.edu/2020/06/seasonal-price-rally-in-soybeans.html); [Oklahoma Farm Report, "Price Seasonality"](https://www.oklahomafarmreport.com/2026/02/04/price-seasonality-what-the-pattern-shows/)). The fundamental problem: with only ~40–50 years of clean CBOT data and 12 months, there are effectively ~40 independent observations per month. Pattern matching with that sample size and the usual multiple-testing practice (search across start date, hold length, contract) produces a standard multiple-comparisons false-discovery rate. Harvey–Liu–Zhu (2016) make the general point that factor-mining inflates $t$-statistics relative to nominal levels ([Harvey, Liu & Zhu, "…and the Cross-Section of Expected Returns," RFS 2016](https://academic.oup.com/rfs/article-abstract/29/1/5/1844077)).

Moore-style composites survive only if (i) a structural story supports the pattern (harvest pressure, weather-vol pricing, Goldman-roll index flow, crusher hedging calendar), (ii) the strategy is implemented with an ex-ante signal — not a historical pattern re-fit each year — and (iii) a walk-forward holdout confirms persistence. Industry studies report that adding a momentum filter ("take the seasonal only if the market is also trending that way") roughly halves the drawdown without reducing gross expectancy; this is the Quant-composite hybrid that commodity CTAs run rather than pure seasonals.

---

## 4. Cross-sectional commodity momentum

### 4.1 Construction

At month end, rank $N$ commodity futures by past $J$-month excess return, long the top quintile and short the bottom (equal or inverse-volatility weighted), hold for $K$ months. The canonical Miffre–Rallis (2007) implementation spans 31 futures over 1979–2004 with $J,K\in\{1,3,6,12\}$ and reports a best-case 9.4% annualized return across 13 winning $(J,K)$ combinations ([Miffre & Rallis, "Momentum strategies in commodity futures markets," JBF 2007](https://www.sciencedirect.com/science/article/abs/pii/S037842660700026X); [SSRN 702281](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=702281)). Szymanowska et al. (2014) decompose commodity returns into spot and term premia and show that basis, past return, and volatility sorts generate spot premia of 5–14% annualized and term premia of 1–3% over 1970s–2008 samples ([Szymanowska et al., "An Anatomy of Commodity Futures Risk Premia," JF 2014](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12096)).

### 4.2 Universe selection and rebalancing

The cross-sectional universe must be broad enough to diversify (at least 15 futures) and narrow enough that the "worst" contract really is representative. Asness, Moskowitz, and Pedersen (2013) report the diversified global value-and-momentum-everywhere portfolio has Sharpe above 1 gross, with commodities a smaller but positive contribution ([Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere," JF 2013](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12021)). Rebalancing at monthly frequency is standard; weekly overlaps the signal with microstructure noise, and quarterly smooths over the useful signal decay that happens at the 30–60-day horizon in grains.

### 4.3 Factor structure and post-publication persistence

Bakshi, Gao, and Rossi (2019, Management Science) find a parsimonious three-factor model — average, carry, momentum — describes the cross-section of commodity returns, and momentum is priced ([Bakshi, Gao & Rossi, "Understanding the Sources of Risk Underlying the Cross Section of Commodity Returns," MS 2019](https://pubsonline.informs.org/doi/10.1287/mnsc.2017.2840)). Boons and Prado (2019, JF) introduce *basis-momentum* — the difference between twelve-month momentum on the front and second-deferred contracts — and show it subsumes carry and momentum in cross-sectional tests and earns a Sharpe near 1 over 1959–2014 ([Boons & Prado, "Basis-Momentum," JF 2019](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12738); [SSRN 2587784](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2587784)). McLean and Pontiff (2016) show that in equities, cross-sectional predictor alpha drops roughly 58% post-publication; commodity cross-sectional momentum, by virtue of position limits and a smaller population of arbitrageurs, appears to have decayed less (Qian et al. 2025, *JFM*), but realistic expectations are 30–40% below in-sample Sharpe ([McLean & Pontiff, "Does Academic Research Destroy Stock Return Predictability," JF 2016](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365); [Qian et al., "Factor Momentum in Commodity Futures," JFM 2025](https://onlinelibrary.wiley.com/doi/10.1002/fut.70022?af=R)).

---

## 5. Statistical arbitrage across related contracts

### 5.1 The crush-spread spec

Define the board crush in cents per bushel:

$$
\text{Crush}_t=\underbrace{0.022\cdot P^{\text{ZM}}_t}_{\text{meal, \$/ton}\to\text{¢/bu}}+\underbrace{11\cdot P^{\text{ZL}}_t}_{\text{oil, ¢/lb}\to\text{¢/bu}}-P^{\text{ZS}}_t,
$$

where the weights reflect the physical conversion of one bushel of soybeans into approximately 44 lb of 48%-protein meal and 11 lb of oil. The exchange's listed package is 10 ZM + 9 ZL − 11 ZS, an approximation that normalizes the trade to whole contract counts ([CME, "Understanding Soybean Crush"](https://www.cmegroup.com/education/courses/introduction-to-agriculture/grains-oilseeds/understanding-soybean-crush)).

### 5.2 Cointegration evidence

Simon (1999) applies Engle–Granger to the three-price vector $(P^{ZS},P^{ZM},P^{ZL})$ and rejects the no-cointegration null, identifying a single cointegrating relation closely aligned with the physical crush coefficients ([Simon (2010), "Soybean Futures Crush Spread Arbitrage," *Journal of Risk and Financial Management*](https://www.mdpi.com/1911-8074/3/1/63)). Adrangi et al. (2006) run bivariate Johansen on (ZS, ZM) and (ZS, ZL) and find one cointegrating vector in each. Rechner and Poitras (1993) simulate a mean-reversion rule on the crush: the unfiltered trade loses after 1.5¢/bu costs, but a 3¢ entry filter lifts expected profit per trade from −0.35¢ to +1.74¢/bu ([Rechner & Poitras, "Putting on the Crush"](https://www.sfu.ca/~poitras/soy.pdf)). A recent 2025 *Modern Finance* paper extends the set and reports positive simulated returns on a cointegration-plus-5-day-filter rule ([*Modern Finance*, "Returns and volatility linkages in the US soybean industry"](https://mf-journal.com/article/view/355/320)).

### 5.3 Johansen, VECM, and Kalman dynamics

With $p_t=[\ln P^{ZS}_t,\ln P^{ZM}_t,\ln P^{ZL}_t]'$ and VECM

$$
\Delta p_t=\alpha\beta'p_{t-1}+\sum_{j=1}^{k-1}\Gamma_j\Delta p_{t-j}+\varepsilon_t,
$$

Johansen's likelihood-ratio test gives the rank of $\beta$ and identifies the long-run weights ([Wikipedia, "Johansen test"](https://en.wikipedia.org/wiki/Johansen_test)). Static $\beta$ is the simplest implementation; the Kalman filter treats $\beta_t$ as a latent state to allow slow structural drift — useful in soy because meal share of the complex has moved materially since the renewable-diesel expansion of 2022–2026 ([HudsonThames cointegration primer](https://hudsonthames.org/an-introduction-to-cointegration/); [Kalman-filter pairs trading](https://kalman-filter.com/pairs-trading/)).

### 5.4 Bean–corn ratio and inter-crop spreads

The November ZS ÷ December ZC ratio is watched for acreage signaling (ratio > 2.5 favors soy, < 2.2 favors corn). The cointegration is weaker than for the crush because acreage substitution is a slow, annual process and the series undergoes structural breaks at ethanol policy changes. Most desks run it as a mean-reversion overlay with regime filter rather than a pure stat-arb. Bayesian dynamic cointegration has been explored on soy ([Imperial working paper, "Bayesian Inference for Dynamic Cointegration Models"](https://www.ma.imperial.ac.uk/~nkantas/paper_soybean.pdf)).

---

## 6. Supply-demand balance-sheet models

### 6.1 Stocks-to-use and the Roberts–Schlenker functional form

The simplest econometric pricing relation for soybeans is the log-inverse stocks-to-use model:

$$
\ln P_t=\alpha+\beta\cdot\ln(S_t/U_t)+\gamma Z_t+\varepsilon_t,
$$

where $S_t/U_t$ is the USDA WASDE ending-stocks-to-use ratio and $Z_t$ are controls (real energy price, dollar index, freight). Pre-2006, soybean price-to-ending-stocks is approximately linear; the post-biofuel era added a strong nonlinearity at low stocks — Farmdoc documents that a stocks-to-use ratio of given magnitude is associated with a materially higher price in the post-2006 era because of the rightward demand shift ([Farmdoc Daily, "Relationship between Stocks-to-Use and Soybean Prices Revisited"](https://farmdocdaily.illinois.edu/2015/05/relationship-between-stock-to-use-and-soybean-prices.html); [AgManager.info, "U.S. Soybean Price vs. Ending Stocks"](https://www.agmanager.info/grain-marketing/grain-supply-and-demand-wasde/us-soybean-price-vs-ending-stocks-total-usage)).

### 6.2 WASDE-nowcasting and ending-stocks sensitivity

Because WASDE is released monthly and contains mostly updates to existing supply-demand line items rather than brand-new information, a balance-sheet nowcaster ingests: USDA Export Sales weekly data, NOPA crush (monthly, 15th), Census Bureau crush (monthly), rail and barge grain loading reports, FGIS inspections, and satellite yield signals, and produces a rolling estimate of ending stocks before each WASDE. The practitioner target is to forecast the USDA's own number (which in turn moves price) rather than "truth," because the market reaction function is anchored to WASDE. Goyal, Adjemian, Glauber, and Meyer (2021) decompose USDA ending-stocks forecast errors using weighted machine-learning boosting, and show significant information content in early-season yield and pace-of-use data ([Goyal et al., "Decomposing USDA Ending Stocks Forecast Errors," NCCC-134](https://agecon.uga.edu/content/dam/caes-subsite/ag-econ/documents/Goyal_Adjemian_Glauber_Meyer_NCCC-134_2021.pdf); [Isengildina et al., "How Accurate and Reliable are USDA Production Forecasts?"](https://aaec.vt.edu/content/dam/aaec_vt_edu/faculty-research/NCGA%20Report_Final.pdf)).

CME's own research notes that WASDE *reduces* implied volatility around 70% of the time (1985–2002 sample) — implying that systematic traders running a nowcast can also monetize the implied-vol crush when their forecast agrees with consensus ([CME, "Understanding Major USDA Reports"](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)). McKenzie's "Was the Missing 2013 WASDE Missed?" paper quantifies the information loss from the 2013 government shutdown as a natural experiment ([McKenzie, *AEPP*, 2018](https://onlinelibrary.wiley.com/doi/10.1093/aepp/ppx049)).

### 6.3 Elasticities, acreage response, and multi-year models

Roberts and Schlenker (2013 *AER*) estimate food-commodity supply and demand elasticities around 0.1 — extremely inelastic — which mechanically amplifies price responses to supply shocks and explains why a 5% WASDE yield revision can trigger 15–25% price moves in a short supply year. Acreage elasticity of soybeans with respect to the ZS/ZC ratio is in the 0.1–0.3 range from Michigan State, Iowa State, and Farm Progress working estimates ([Michigan State Extension](https://www.canr.msu.edu/news/the-corn-soybean-ratio-and-its-potential-impact-on-farm-profits); [Iowa State Ag Decision Maker](https://www.extension.iastate.edu/agdm/crops/html/a2-40.html)). These modest elasticities constrain how much the market can smooth a balance-sheet shock within a crop year and are the theoretical underpinning of the "tight stocks → high vol-of-vol" behavior traders see at 6–8% ending-stocks-to-use ratios.

---

## 7. Weather-derivative-style yield models

### 7.1 NDVI and vegetation-index regressions

The Normalized Difference Vegetation Index is computed from red and NIR reflectance bands as

$$
\mathrm{NDVI}=\frac{\rho_{\text{NIR}}-\rho_{\text{RED}}}{\rho_{\text{NIR}}+\rho_{\text{RED}}}\in[-1,1].
$$

NASS-style yield models regress final yield on accumulated or peak NDVI over the growing window. Anyamba et al. (2021, *Remote Sensing*) document that for corn, peak NDVI methods achieve an $R^2$ of 0.88 with 3.5% CV; accumulated-NDVI methods with optimized thresholds improve to 0.93 and 2.7% CV. For soybeans, peak NDVI yields $R^2=0.62$ and accumulated-NDVI 0.73 with CVs of 6.8% and 5.7% ([Anyamba et al., "USA Crop Yield Estimation with MODIS NDVI"](https://www.mdpi.com/2072-4292/13/21/4227)). Deep-learning extensions (Nature 2021) report improvements using transfer learning from corn to soybean ([Nature, "Simultaneous corn and soybean yield prediction"](https://www.nature.com/articles/s41598-021-89779-z)).

### 7.2 Growing-degree-days

The GDD for a day with max $T_h$ and min $T_l$ is

$$
\mathrm{GDD}_t=\max\!\bigl(0,\tfrac{T_h+T_l}{2}-T_{\text{base}}\bigr),
$$

with $T_{\text{base}}\approx 50^\circ$F for soy. Season-long $\sum \mathrm{GDD}_t$ together with phenology markers (emergence, R1 flowering, R5 pod fill) constrains expected yield. Multiple regressions of yield on (accumulated GDD, accumulated NDVI, stress-degree-days, July precipitation) provide the working quantitative-yield model behind several commercial products (Gro Intelligence, Descartes Labs, Maxar) and the NASS yield nowcaster ([NASS-USDA, "Operational Prediction of Crop Yields using MODIS Data"](https://www.nass.usda.gov/Education_and_Outreach/Reports,_Presentations_and_Conferences/Presentations/Beard_Stresa06_CropYield.pdf)).

### 7.3 Bayesian updating across the growing season

A Bayesian yield nowcast writes

$$
p(Y\mid D_t)\propto p(D_t\mid Y)\,p(Y\mid D_{t-1}),
$$

where $D_t$ is the date-$t$ data panel (NDVI, GDD, NASS crop conditions, WASDE) and the prior comes from the previous week's posterior. Concretely, practitioners initialize the prior from trend yield plus a La Niña / El Niño adjustment (farmdoc documents average soybean yield effects of −1 to −4 bu/ac for La Niña in Argentina, −2 to −5 bu/ac in southern Brazil; [Farmdoc, "Third Consecutive La Niña?"](https://farmdocdaily.illinois.edu/2022/05/third-consecutive-la-nina-what-to-expect-from-soybean-yields-in-the-united-states-brazil-and-argentina.html)) and narrow the posterior weekly as mid-season data arrives. The price-relevant output is a cumulative yield distribution, not a point estimate — which is why the Gro / Descartes Labs products ship with ensemble ranges.

---

## 8. NLP and ML on fundamentals

### 8.1 Parsing WASDE and Export Sales

WASDE is released as fixed-format PDF and Excel at 12:00 ET. The practitioner NLP pipeline: (i) parse the PDF/XLSX tables directly into a balance-sheet schema (U.S. and world line items — acres, yield, beginning stocks, production, imports, feed use, exports, crush, ending stocks, season-average price); (ii) compute deltas vs. the prior report and vs. the Reuters / WSJ / Bloomberg analyst survey; (iii) map each line-item surprise to a pre-trained sensitivity coefficient (e.g. −1 million bushel ending-stocks surprise ≈ +18¢/bu, historical average). The USDA Export Sales weekly file is released Thursdays 08:30 ET and parsed analogously against trade expectations.

### 8.2 Text sentiment on newswires and tweets

FinBERT and related transformer models fine-tuned on financial text produce sentence-level positive/negative scores that feed directional trades. Recent academic work documents that fusing news sentiment with tabular price features improves out-of-sample directional accuracy across eleven commodities ([SSRN, "Does Sentiment Analysis Bring More Responsive and Comprehensive Commodity Price Forecasting"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5344493); [*Journal of Forecasting*, "Comprehensive commodity price forecasting framework using text mining methods"](https://onlinelibrary.wiley.com/doi/abs/10.1002/for.2985); [arXiv, "Forecasting Commodity Price Shocks Using Temporal and Semantic Fusion"](https://arxiv.org/html/2508.06497v1)). The grain-relevant feeds are DTN, Reuters-Agri, Bloomberg-Ag, AgriCensus, plus USDA attache reports.

### 8.3 Gradient boosting on tabular fundamentals

The consensus ML baseline on structured macro/micro tabular data is gradient-boosted trees — XGBoost, LightGBM, CatBoost — configured with a rolling time-series split and early stopping on an out-of-sample holdout. Bianchi, Büchner, and Tamoni (2021, RFS) apply extreme trees and neural nets to the bond-risk premium problem and document economically significant gains over Cochrane–Piazzesi and Ludvigson–Ng benchmarks ([Bianchi, Büchner & Tamoni, "Bond Risk Premiums with Machine Learning," RFS 2021](https://academic.oup.com/rfs/article-abstract/34/2/1046/5843806)). Analogous studies on corn and soybean — ingesting the WASDE balance sheet, weekly Export Sales, NOPA crush, precipitation/GDD anomalies, Brazilian real, dollar index, oilshare — consistently find $R^2$ gains of 2–5 percentage points on monthly price-change prediction over linear baselines, with feature importance concentrated in stocks-to-use deltas, Brazilian FX, and crude/ZL relations.

### 8.4 Limitations

Data hygiene is the binding constraint. USDA frequently revises earlier estimates (benchmark revisions once per year, monthly small revisions) so naive in-sample fits use data that was not actually known at the time — a point-in-time database is mandatory. Machine-learning models with 100+ inputs and 40 years of monthly data (~480 rows) are chronically overparameterized and require aggressive regularization.

---

## 9. Microstructure / short-horizon systematic

### 9.1 Order-flow imbalance

Define signed trade volume $q_t$ (+1 for buyer-initiated, −1 for seller-initiated) at the tick level; the one-second order flow imbalance is $\mathrm{OFI}_t=\sum q$ over the window. Cont's linear price-impact model predicts $\Delta p_{t+1}\approx \lambda\cdot \mathrm{OFI}_t$ with $\lambda$ inversely related to top-of-book depth ([arXiv, "The Price Impact of Generalized Order Flow Imbalance"](https://arxiv.org/pdf/2112.02947)). In soybeans, Zhou, Bagnarosa, Gohin, Pennings, and Debie (2022) document a theoretical cointegration framework applied to high-frequency soy-complex prices and link speed of reversion to realized and latent liquidity ([Zhou et al., "Microstructure and High-Frequency Price Discovery in the Soybean Complex"](https://farmdoc.illinois.edu/assets/meetings/nccc134/conf_2022/pdf/Zhou_Bagnarosa_Gohin_Pennings_Debie_NCCC-134_2022.pdf); [Science­Direct version](https://www.sciencedirect.com/science/article/pii/S2405851323000041)).

### 9.2 Queue position and maker/taker dynamics

Because CME ZS trades in a price-time FIFO book, the value of an order depends on queue position. Resting orders filled early — by short queue or by queue-jumping via implied liquidity — capture the half-spread at low adverse selection. Peng et al. (2024, *JFM*) study a maximum-order-size rule change on CME spread markets and document substantial depth improvement (2–4x) without any meaningful change in realized volatility, consistent with the hypothesis that display-size caps reduce passive-resting front-running while leaving true informational content of orders intact ([Peng, "Maximum order size and market quality," JFM 2024](https://onlinelibrary.wiley.com/doi/10.1002/fut.22494)). Irwin-lab dissertations document a $0.05–$0.10 round-trip cost range for ZS outright vs. $0.25+ for calendar spreads, with the spread books materially benefiting from changes like implied-order permissions after 2014 ([University of Illinois IDEALS, "Three Essays on Agricultural Futures Market Liquidity"](https://www.ideals.illinois.edu/items/125196/bitstreams/411120/data.pdf)).

### 9.3 VPIN and informed-flow monitoring

Easley, López de Prado, and O'Hara introduced Volume-Synchronized Probability of Informed Trading (VPIN) as a real-time flow-toxicity estimate that flagged elevated adverse selection before the 2010 flash crash ([Easley, López de Prado & O'Hara, "Flow Toxicity and Liquidity," RFS 2012](https://academic.oup.com/rfs/article-abstract/25/5/1457/1569929); [NYU PDF](https://www.stern.nyu.edu/sites/default/files/assets/documents/con_035928.pdf)). In grains it is used less as a price-prediction signal and more as a liquidity-withdrawal trigger for market-making strategies around USDA-report release windows.

### 9.4 Roll-period liquidity effects

The Goldman roll window (5th–9th business day of the month preceding expiry) moves 20%/day of S&P GSCI-indexed open interest from the front to the next-out. Mou (2011) documents Sharpe-as-high-as-4.4 on pre-positioning strategies that front-run this predictable flow, noting that profitability depends on net index-investment size vs. arbitrage capital ([Mou, "Limits to Arbitrage and Commodity Index Investment: Front-Running the Goldman Roll"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1716841); [CFTC posted copy](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_33_yu.pdf)). Irwin, Sanders, and Yan (2022) update the result and document an order-flow cost of index rolling of ~0.3% per year on the GSCI portfolio, with grains a smaller share than energies ([Irwin, Sanders & Yan, "The Order Flow Cost of Index Rolling in Commodity Futures Markets"](https://scotthirwin.com/wp-content/uploads/2022/02/Irwin_Sanders_Yan_AEPP_All.pdf)).

---

## 10. Performance realism

### 10.1 Post-publication decay

McLean and Pontiff's 58% post-publication drop in stock cross-section alpha is the reference number. For commodity carry, basis-momentum, and cross-section momentum, there is no equivalent large-sample post-publication study, but Qian et al. (2025) and subsequent JFM literature report that commodity factor strategies have held up better than equity factors — plausibly because commodity arbitrageurs are constrained by margin, position limits, and regulatory capital in ways equity quants are not ([Qian et al., "Factor Momentum in Commodity Futures," JFM 2025](https://onlinelibrary.wiley.com/doi/10.1002/fut.70022?af=R)). Realistic expectations: back-tested Sharpe ratios published 2000–2015 should be multiplied by 0.6–0.7 for live-money planning.

### 10.2 Capacity: grains vs. energy vs. metals

Grains liquidity, in notional terms, is roughly 10–15% of WTI crude and 30–50% of gold. CME-ZS average daily volume is around 200,000 contracts on ZS outright (~$10bn notional/day) with top-of-book depth of 20–50 lots typical during 24-hour session but 100+ at the U.S. open ([CME ZS quotes](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.quotes.html)). Strategies running position sizes under ~5% of daily volume can execute without moving the market meaningfully; strategies running over ~20% of ADV will eat most of the published edge in slippage, particularly on the crush-calendar legs (ZM spreads are materially thinner).

### 10.3 Transaction-cost sensitivity

From Fuertes-Miffre-Rallis (2010), annual turnover for a combined momentum-plus-term-structure portfolio is about 10x, and with average round-trip cost of 0.069% per trade the annual drag is ~0.7%. This scales roughly linearly: a 24x-turnover weekly-rebalanced strategy bleeds ~1.7%. On a signal with published gross Sharpe of 0.6, realistic net Sharpe after costs and capacity is 0.3–0.4. Systematic trend-followers run turnover of 2–5x annually and so are less cost-constrained than cross-sectional momentum; stat-arb strategies (crush cointegration, bean-corn spreads) are typically 50–100x/year and are brutal to cost assumptions.

### 10.4 Risk premium vs. strategy

A useful discipline: every "strategy" above is really a proxy for a risk or a frictional imbalance. Trend-following is compensation for holding convex, sometimes crisis-alpha exposure that hedgers dislike. Carry is compensation for hedging-pressure / storage risk. Cross-sectional momentum is partially behavioral, partially a limited-arbitrage proxy. Crush stat-arb earns the processor's risk premium. WASDE nowcasting earns compensation for spending 5x the research budget of the marginal WASDE-naïve speculator. NDVI-yield models earn the elasticity rent created by the ~0.1 supply elasticity in row crops. Microstructure signals earn a toll at the top of the book. When a live strategy's Sharpe ratio diverges sharply from the risk-premium economics that justify it — either above or below — that divergence is usually a signal that the strategy has become a leveraged proxy for something else (Brazilian real, S&P implied vol, crude, or regulatory beta to USDA acreage policy) rather than a true autonomous edge.

---

## Key takeaways

Trend-following is the most durable systematic commodity strategy, with published Sharpe ratios of ~0.8–1.2 on diversified multi-asset books over 1900–2020 and materially lower (0.2–0.45 gross single-market, 0.15–0.3 net) on ZS alone. Carry, whether expressed as the slope of the futures curve or as cross-sectional quintile sorts on the basis, explains the bulk of cross-sectional variation in commodity returns and delivers 10–12% gross annualized on a long-short quintile book before costs. Cross-sectional momentum and basis-momentum survive and appear less post-publication-degraded in commodities than in equities, but turnover costs bite hard without filters. Seasonality looks reliable in composite charts and rarely in a walk-forward evaluation; survive only if paired with a fundamental story and a momentum confirmation. Crush spread cointegration is a real, tested phenomenon but only profitable with transaction-cost filters. Balance-sheet, NDVI, and ML-on-fundamentals strategies are fundamentals proxies that pay in tight-stocks regimes and nearly nothing in well-supplied years — the asymmetric payoff profile of the inelastic-supply agricultural complex. Microstructure / order-flow strategies are real but capacity-constrained to a handful of players. Across every family, the gap between in-sample Sharpe and live-money Sharpe runs 30–50%; the honest researcher discounts every published number by that margin before sizing a position.

---

## References

### Peer-reviewed papers

1. Asness, C. S., Moskowitz, T. J., & Pedersen, L. H. (2013). Value and Momentum Everywhere. *Journal of Finance*, 68(3), 929–985. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12021
2. Bakshi, G., Gao, X., & Rossi, A. G. (2019). Understanding the Sources of Risk Underlying the Cross Section of Commodity Returns. *Management Science*, 65(2), 619–641. https://pubsonline.informs.org/doi/10.1287/mnsc.2017.2840
3. Bianchi, D., Büchner, M., & Tamoni, A. (2021). Bond Risk Premiums with Machine Learning. *Review of Financial Studies*, 34(2), 1046–1089. https://academic.oup.com/rfs/article-abstract/34/2/1046/5843806
4. Boons, M., & Porras Prado, M. (2019). Basis-Momentum. *Journal of Finance*, 74(1), 239–279. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12738
5. Easley, D., López de Prado, M., & O'Hara, M. (2012). Flow Toxicity and Liquidity in a High-Frequency World. *Review of Financial Studies*, 25(5), 1457–1493. https://academic.oup.com/rfs/article-abstract/25/5/1457/1569929
6. Erb, C. B., & Harvey, C. R. (2006). The Strategic and Tactical Value of Commodity Futures. *Financial Analysts Journal*, 62(2), 69–97. https://www.tandfonline.com/doi/abs/10.2469/faj.v62.n2.4084
7. Fuertes, A.-M., Miffre, J., & Rallis, G. (2010). Tactical Allocation in Commodity Futures Markets: Combining Momentum and Term Structure Signals. *Journal of Banking & Finance*, 34(10), 2530–2548. https://www.sciencedirect.com/science/article/abs/pii/S0378426610001354
8. Gorton, G. B., Hayashi, F., & Rouwenhorst, K. G. (2013). The Fundamentals of Commodity Futures Returns. *Review of Finance*, 17(1), 35–105. NBER WP 13249. https://www.nber.org/system/files/working_papers/w13249/w13249.pdf
9. Gorton, G. B., & Rouwenhorst, K. G. (2006). Facts and Fantasies about Commodity Futures. *Financial Analysts Journal*, 62(2), 47–68. https://www.tandfonline.com/doi/abs/10.2469/faj.v62.n2.4083
10. Harvey, C. R., Liu, Y., & Zhu, H. (2016). …and the Cross-Section of Expected Returns. *Review of Financial Studies*, 29(1), 5–68. https://academic.oup.com/rfs/article-abstract/29/1/5/1844077
11. Hong, H., & Yogo, M. (2012). What Does Futures Market Interest Tell Us about the Macroeconomy and Asset Prices? *Journal of Financial Economics*, 105(3), 473–490. https://ideas.repec.org/a/eee/jfinec/v105y2012i3p473-490.html
12. Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H., & Vrugt, E. B. (2018). Carry. *Journal of Financial Economics*, 127(2), 197–225. https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2019/04/Carry.pdf
13. McLean, R. D., & Pontiff, J. (2016). Does Academic Research Destroy Stock Return Predictability? *Journal of Finance*, 71(1), 5–32. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365
14. McKenzie, A. M. (2018). Was the Missing 2013 WASDE Missed? *Applied Economic Perspectives and Policy*, 40(4), 667–682. https://onlinelibrary.wiley.com/doi/10.1093/aepp/ppx049
15. Miffre, J., & Rallis, G. (2007). Momentum Strategies in Commodity Futures Markets. *Journal of Banking & Finance*, 31(6), 1863–1886. https://www.sciencedirect.com/science/article/abs/pii/S037842660700026X
16. Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H. (2012). Time Series Momentum. *Journal of Financial Economics*, 104(2), 228–250. https://www.sciencedirect.com/science/article/pii/S0304405X11002613
17. Peng, Z. (2024). Maximum Order Size and Market Quality: Evidence from a Natural Experiment in Commodity Futures Markets. *Journal of Futures Markets*, 44(6). https://onlinelibrary.wiley.com/doi/10.1002/fut.22494
18. Qian, E., et al. (2025). Factor Momentum in Commodity Futures Markets. *Journal of Futures Markets*. https://onlinelibrary.wiley.com/doi/10.1002/fut.70022
19. Simon, D. P. (2010). Soybean Futures Crush Spread Arbitrage: Trading Strategies and Market Efficiency. *Journal of Risk and Financial Management*, 3(1), 63–96. https://www.mdpi.com/1911-8074/3/1/63
20. Szymanowska, M., de Roon, F., Nijman, T., & van den Goorbergh, R. (2014). An Anatomy of Commodity Futures Risk Premia. *Journal of Finance*, 69(1), 453–482. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12096

### Named-fund white papers and academic working papers

21. Aspect Capital. "Living with Trend Following: History & Lessons." https://aspectcapital.s3.amazonaws.com/documents/Aspect_Capital_Insight_-_Living_With_Trend_Following_History__Lessons_From_the_8LAzOwQ.pdf
22. Baltas, N. (2017). Optimising Cross-Asset Carry. SSRN 2968677. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2968677
23. Campbell & Company. "Prospects for CTAs in a Rising Rate Environment." https://www.cmegroup.com/education/files/prospects-for-ctas-in-a-rising-interest-rate-environment.pdf
24. CME Group. "An Introduction to Global Carry." https://www.cmegroup.com/education/files/an-introduction-to-global-carry.pdf
25. CME Group. "Understanding Major USDA Reports." https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html
26. Hurst, B., Ooi, Y. H., & Pedersen, L. H. (2012). A Century of Evidence on Trend-Following Investing. AQR working paper. https://openaccess.city.ac.uk/id/eprint/18554/7/SSRN-id2520075.pdf
27. Kaminski, K. M. (2016). Quantifying CTA Risk Management. *Alternative Investment Analyst Review*. https://caia.org/sites/default/files/AIAR_Q1_2016_04_Kaminsky_CTARiskManagement.pdf
28. Man AHL. "Trend Following and Drawdowns: Is This Time Different?" https://www.man.com/insights/is-this-time-different
29. Mou, Y. (2011). Limits to Arbitrage and Commodity Index Investment: Front-Running the Goldman Roll. SSRN 1716841. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1716841
30. Rattray, S., & van Hemert, O. (2018). The Impact of Volatility Targeting. SSRN working paper. https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
31. Irwin, S. H., Sanders, D. R., & Yan, L. (2022). The Order Flow Cost of Index Rolling in Commodity Futures Markets. *Applied Economic Perspectives and Policy*. https://scotthirwin.com/wp-content/uploads/2022/02/Irwin_Sanders_Yan_AEPP_All.pdf
32. Goyal, R., Adjemian, M. K., Glauber, J., & Meyer, S. (2021). Decomposing USDA Ending Stocks Forecast Errors. NCCC-134 Conference. https://agecon.uga.edu/content/dam/caes-subsite/ag-econ/documents/Goyal_Adjemian_Glauber_Meyer_NCCC-134_2021.pdf
33. Zhou, M., Bagnarosa, G., Gohin, A., Pennings, J. M. E., & Debie, P. (2023). Microstructure and High-Frequency Price Discovery in the Soybean Complex. *Journal of Commodity Markets*. https://www.sciencedirect.com/science/article/pii/S2405851323000041

### Practitioner and applied sources

34. Anyamba, A., et al. (2021). USA Crop Yield Estimation with MODIS NDVI. *Remote Sensing*, 13(21), 4227. https://www.mdpi.com/2072-4292/13/21/4227
35. CME Group. "Understanding Soybean Crush." https://www.cmegroup.com/education/courses/introduction-to-agriculture/grains-oilseeds/understanding-soybean-crush
36. Farmdoc Daily. "Relationship between Stocks-to-Use and Soybean Prices Revisited." https://farmdocdaily.illinois.edu/2015/05/relationship-between-stock-to-use-and-soybean-prices.html
37. Farmdoc Daily. "Seasonal Price Rally in Soybeans." https://farmdocdaily.illinois.edu/2020/06/seasonal-price-rally-in-soybeans.html
38. Garcia, P., Irwin, S. H., & Smith, A. (2013). Commodity Storage under Backwardation: Does the Working Curve Still Work? https://legacy.farmdoc.illinois.edu/irwin/research/commoditystorage2013.pdf
39. Isengildina-Massa, O., et al. "How Accurate and Reliable are USDA Production Forecasts?" https://aaec.vt.edu/content/dam/aaec_vt_edu/faculty-research/NCGA%20Report_Final.pdf
40. Pro Farmer. "Crop Tour Methodology." https://www.profarmer.com/crop-tour-methodology
41. Moore Research Center. 2008 Soybean Seasonality Report (CME-hosted). https://www.cmegroup.com/education/interactive/moore-report/pdf/AC-167_MooreSoybeanFinal.pdf
42. University of Illinois IDEALS. "Three Essays on Agricultural Futures Market Liquidity." https://www.ideals.illinois.edu/items/125196/bitstreams/411120/data.pdf
43. An, Y., et al. (2023). Comprehensive Commodity Price Forecasting Framework Using Text Mining Methods. *Journal of Forecasting*, 42(5). https://onlinelibrary.wiley.com/doi/abs/10.1002/for.2985
44. Wikipedia. "Theory of Storage." https://en.wikipedia.org/wiki/Theory_of_storage
45. Wikipedia. "Johansen Test." https://en.wikipedia.org/wiki/Johansen_test
