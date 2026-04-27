# Audit C — Phase 05 Systematic Strategies (Claim Index)

## 1. Source artifact summary

`research/phase_05_systematic_strategies.md` surveys the canonical systematic
strategy families applicable to the grain and soybean futures complex —
trend-following / CTA, carry / term-structure, seasonality, cross-sectional
momentum, statistical arbitrage (crush, bean–corn), supply-demand balance-sheet
econometrics (stocks-to-use, WASDE-nowcasting), weather-derivative-style yield
models (NDVI, GDD, Bayesian nowcasts), NLP / ML on fundamentals, and
microstructure / order-flow signals. For each family it gives the standard
construction (with formula and rebalancing cadence), cites the academic
backbone (JFE, JF, RFS, MS, JBF, JFM, AQR / Man / Aspect / Campbell white
papers, NBER, farmdoc, CFTC), names representative practitioner shops where
relevant, and closes with a "performance realism" section on post-publication
decay, capacity, transaction-cost sensitivity, and the risk-premium economics
underlying each strategy. The file's analytical posture is conservative:
back-tested numbers are paired with realistic net-of-cost expectations and the
30–50% gap between in-sample and live-money Sharpe is repeatedly stressed.

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C05-01 | Moving-average crossover sign signal s_t = sign(MA_s(p,n) − MA_l(p,m)) with classical fast/slow pairs (n=10, m=50) or (n=50, m=200). | §1.1 lines 15–21 | established | strategy |
| C05-02 | Donchian breakout: long if p_t > prior N-day high, short if p_t < prior N-day low; canonical parameters N=20 (system 1) and N=55 (system 2), as adopted by Dennis/Turtles. | §1.1 lines 23–29 | established | strategy |
| C05-03 | TSMOM weight w_t^i = c · sign(r^i_{t−12,t}) / σ^i_t with typical 12-month lookback, c a vol-target constant (e.g. 40%), σ^i_t an ex-ante vol forecast (EWMA or GARCH). | §1.1 lines 31–37 | established | strategy;pricing-model |
| C05-04 | Moskowitz–Ooi–Pedersen (JFE 2012) report a TSMOM diversified Sharpe near 1.6 gross of costs over 1985–2009 on a 58-market futures/forwards universe. | §1.1 line 37 | established | backtest |
| C05-05 | CTAs size by inverse ex-ante volatility (vol parity) per contract or lever the whole book to a target portfolio volatility (vol targeting); they virtually never hold constant notional. | §1.1 lines 39 | established | strategy |
| C05-06 | Vol targeting improves the Sharpe of risk-asset portfolios but has a near-neutral effect on commodities once the strategy is already long-short (Rattray–van Hemert; Concretum). | §1.1 line 39 | debated | strategy;backtest |
| C05-07 | Hurst–Ooi–Pedersen extend TSMOM back to 1880 across 67 markets; report gross Sharpe ~1.0 on the 1-3-12 equal-weighted trend basket with statistically significant alpha in every sub-decade except the 1930s and 2010s. | §1.2 line 43 | established | backtest |
| C05-08 | AHL-style diversified CTA portfolios run roughly 15–25% weight in agricultural commodities and 3–6% specifically in the soybean complex. | §1.4 line 56 | practitioner-lore | strategy |
| C05-09 | Individual-market TSMOM Sharpes are in the 0.2–0.5 range; diversification carries most of the weight of the 1.6 multi-market headline. | §1.4 line 56 | established | backtest |
| C05-10 | ZS-alone 1-month / 3-month / 12-month TSMOM gross Sharpe 0.25–0.45 (1985–2015); after 3–5 ticks round-trip + roll slippage, net Sharpe 0.15–0.3. | §1.4 line 56 | established | backtest |
| C05-11 | Aspect Capital's longest underwater period was March 2016 → September 2021; published trend Sharpes of 0.6–1.0 come with 5+-year flat or losing stretches. | §1.3 line 52 | established | backtest |
| C05-12 | Annualized carry definition C_t = (F^{T1}_t − F^{T2}_t)/F^{T2}_t · 1/(T2−T1); backwardation ↔ C>0, contango ↔ C<0; fully collateralized long earns ≈ C per unit time absent spot change. | §2.1 lines 64–70 | established | pricing-model |
| C05-13 | Erb–Harvey (FAJ 2006): equal-weighted 12-commodity fully-collateralized portfolio 1982–2004; ranking commodities by roll return explains ~91% of cross-sectional return variance. | §2.2 line 74 | established | backtest |
| C05-14 | Long-high-carry / short-low-carry quintile sort returns ~10–12% gross annualized over 1982–2004 before costs (Erb–Harvey). | §2.2 line 74 | established | strategy;backtest |
| C05-15 | Koijen–Moskowitz–Pedersen–Vrugt (JFE 2018) diversified multi-asset carry portfolio delivers Sharpe > 0.8 gross over 1983–2012. | §2.3 line 78 | established | backtest |
| C05-16 | Baltas (2017): gross carry Sharpes range from 0.19 (commodities only) to 0.85 (government bonds); multi-asset diversified carry book Sharpe > 1.0. | §2.3 line 78 | established | backtest |
| C05-17 | On the soy complex, carry strategies typically use the second-month vs. front-month basis; the deferred pair (e.g. July vs. November old-crop/new-crop) is a seasonally cleaner signal. | §2.4 line 82 | practitioner-lore | strategy |
| C05-18 | Fuertes–Miffre–Rallis (JBF 2010): combined momentum × term-structure double-sort, 1979–2007, ~21% annualized alpha pre-cost (~10% momentum, ~12% term structure). | §2.4 line 82 | established | backtest;strategy |
| C05-19 | In the soy complex the Working/Brennan storage curve is observable: low inventories (late summer pre-harvest) → inverted spreads, positive roll yield; new-crop flush (Nov/Jan) → curve in carry, negative roll yield. | §2.5 line 86 | practitioner-lore | inventory;pricing-model |
| C05-20 | Seasonal signal: ŝ_d = (1/K) Σ r^ex_{t(d,k)} (de-meaned daily log returns aggregated by calendar day across panel); strategy sizes w_t ∝ ŝ_{d(t+h)} for horizon h, often truncated to "long strongest month, short weakest" or threshold. | §3.1 lines 94–100 | established | strategy |
| C05-21 | Moore Research seasonal composites use an in-sample filter: require 80%+ of prior 15 years to align, plus minimum holding window and minimum average profit. | §3.2 line 104 | established | strategy |
| C05-22 | Canonical ZS seasonals: seasonal low at October harvest; spring/summer peak around late June. | §3.2 line 104 | practitioner-lore | strategy |
| C05-23 | Over the last fifteen years, soybean cash price has been higher at harvest than in spring in only three years (2015, 2019, 2024); only ~20% of years conform cleanly to the composite path (farmdoc). | §3.3 line 108 | debated | strategy |
| C05-24 | With ~40–50 years of clean CBOT data and 12 calendar months, there are effectively ~40 independent observations per month, exposing seasonal mining to a multiple-comparisons false-discovery problem. | §3.3 line 108 | established | backtest |
| C05-25 | Adding a momentum filter ("take the seasonal only if the market is also trending that way") roughly halves drawdown without reducing gross expectancy on Moore-style composites. | §3.3 line 110 | practitioner-lore | strategy |
| C05-26 | Cross-sectional momentum construction: at month-end, rank N futures by past J-month excess return, long top quintile / short bottom (equal- or inverse-volatility weighted), hold for K months. | §4.1 line 118 | established | strategy |
| C05-27 | Miffre–Rallis (JBF 2007): 31 futures 1979–2004, J,K ∈ {1,3,6,12}; best-case 9.4% annualized return across 13 winning (J,K) combinations. | §4.1 line 118 | established | backtest |
| C05-28 | Szymanowska et al. (JF 2014): basis, past return, and volatility sorts generate spot premia of 5–14% annualized and term premia of 1–3% across 1970s–2008 samples. | §4.1 line 118 | established | backtest |
| C05-29 | Cross-sectional commodity universe should be ≥ 15 futures for diversification; rebalance monthly (weekly = microstructure noise; quarterly smooths over 30–60-day grain signal decay). | §4.2 line 122 | practitioner-lore | strategy |
| C05-30 | Bakshi–Gao–Rossi (MS 2019): three-factor model {average, carry, momentum} describes the cross-section of commodity returns; momentum is priced. | §4.3 line 126 | established | strategy;pricing-model |
| C05-31 | Boons–Prado (JF 2019) basis-momentum = difference between 12-month momentum on the front and second-deferred contracts; subsumes carry and momentum cross-sectionally; Sharpe ≈ 1 over 1959–2014. | §4.3 line 126 | established | strategy;backtest |
| C05-32 | McLean–Pontiff (JF 2016): cross-sectional equity predictor alpha drops ~58% post-publication. | §4.3 line 126 | established | backtest |
| C05-33 | Realistic commodity factor expectation: 30–40% below in-sample Sharpe (less decayed than equities owing to position limits, margin, and a smaller arbitrageur pool). | §4.3 line 126 | practitioner-lore | backtest |
| C05-34 | Board crush (cents/bushel): Crush_t = 0.022 · P^ZM_t + 11 · P^ZL_t − P^ZS_t, weights reflecting 1 bushel soy → ~44 lb 48%-protein meal + 11 lb oil. | §5.1 lines 134–140 | established | pricing-model |
| C05-35 | CME-listed crush package is 10 ZM + 9 ZL − 11 ZS (whole-contract approximation of physical crush). | §5.1 line 140 | established | contract |
| C05-36 | Simon (1999/2010) Engle–Granger on (P^ZS, P^ZM, P^ZL) rejects no-cointegration; one cointegrating relation closely aligned with physical crush coefficients. | §5.2 line 144 | established | pricing-model |
| C05-37 | Adrangi et al. (2006) bivariate Johansen on (ZS,ZM) and (ZS,ZL) finds one cointegrating vector each. | §5.2 line 144 | established | pricing-model |
| C05-38 | Rechner–Poitras: unfiltered crush mean-reversion loses after 1.5¢/bu costs; a 3¢ entry filter lifts expected profit per trade from −0.35¢ to +1.74¢/bu. | §5.2 line 144 | established | backtest;strategy |
| C05-39 | VECM specification Δp_t = αβ′p_{t−1} + Σ Γ_j Δp_{t−j} + ε_t with p_t = [ln P^ZS, ln P^ZM, ln P^ZL]'; Johansen LR test gives the rank of β. | §5.3 lines 148–154 | established | pricing-model |
| C05-40 | Static β is the simplest implementation; Kalman filter treats β_t as a latent state to allow slow structural drift — relevant on soy because meal share has moved materially since the renewable-diesel expansion of 2022–2026. | §5.3 line 154 | practitioner-lore | pricing-model |
| C05-41 | November ZS / December ZC ratio is an acreage-signaling indicator: ratio > 2.5 favors soy, < 2.2 favors corn; cointegration weaker than crush; typically run as mean-reversion overlay with regime filter. | §5.4 line 158 | practitioner-lore | strategy |
| C05-42 | Stocks-to-use pricing model: ln P_t = α + β · ln(S_t/U_t) + γ Z_t + ε_t with S_t/U_t the USDA WASDE ending-stocks-to-use ratio, Z_t = real energy price, dollar index, freight. | §6.1 lines 168–172 | established | pricing-model |
| C05-43 | Pre-2006 soybean price-to-ending-stocks is approximately linear; post-2006 (biofuel era) adds strong nonlinearity at low stocks (rightward demand shift). | §6.1 line 172 | established | pricing-model |
| C05-44 | Balance-sheet nowcaster ingests USDA Export Sales (weekly), NOPA crush (monthly, 15th), Census Bureau crush (monthly), rail/barge grain loadings, FGIS inspections, satellite yield signals. | §6.2 line 176 | established | data-ingest;inventory |
| C05-45 | Practitioner WASDE-nowcast target is to forecast the USDA's number (which is what moves price), not "truth" — anchored to the WASDE reaction function. | §6.2 line 176 | practitioner-lore | strategy |
| C05-46 | CME research finds WASDE reduces implied volatility ~70% of the time on the 1985–2002 sample, implying systematic traders can monetize implied-vol crush when their forecast agrees with consensus. | §6.2 line 178 | established | strategy;pricing-model |
| C05-47 | Roberts–Schlenker (AER 2013) estimate food-commodity supply and demand elasticities ~0.1; mechanically a 5% WASDE yield revision can trigger 15–25% price moves in a tight-supply year. | §6.3 line 182 | established | pricing-model |
| C05-48 | Soybean acreage elasticity wrt the ZS/ZC ratio is in the 0.1–0.3 range (Michigan State, Iowa State, Farm Progress). | §6.3 line 182 | debated | pricing-model |
| C05-49 | Tight-stocks → high vol-of-vol regime begins around 6–8% ending-stocks-to-use ratio in row crops. | §6.3 line 182 | practitioner-lore | pricing-model |
| C05-50 | NDVI = (ρ_NIR − ρ_RED) / (ρ_NIR + ρ_RED) ∈ [−1, 1]; NASS-style yield models regress final yield on accumulated or peak NDVI over the growing window. | §7.1 lines 190–196 | established | pricing-model;data-ingest |
| C05-51 | Anyamba et al. (2021) — corn: peak-NDVI R²=0.88 (CV 3.5%); accumulated-NDVI with optimized thresholds R²=0.93 (CV 2.7%). Soybeans: peak-NDVI R²=0.62 (CV 6.8%); accumulated-NDVI R²=0.73 (CV 5.7%). | §7.1 line 196 | established | pricing-model;backtest |
| C05-52 | GDD_t = max(0, (T_h + T_l)/2 − T_base) with T_base ≈ 50 °F for soy; phenology markers emergence, R1 flowering, R5 pod fill constrain expected yield. | §7.2 lines 200–206 | established | pricing-model;data-ingest |
| C05-53 | Bayesian yield nowcast: p(Y | D_t) ∝ p(D_t | Y) · p(Y | D_{t−1}); prior initialised from trend yield + La Niña / El Niño adjustment, posterior narrowed weekly as mid-season data arrives; output is a cumulative yield distribution, not a point estimate. | §7.3 lines 210–216 | established | pricing-model;data-ingest |
| C05-54 | Average soybean yield effects of La Niña: −1 to −4 bu/ac in Argentina, −2 to −5 bu/ac in southern Brazil (farmdoc). | §7.3 line 216 | practitioner-lore | pricing-model |
| C05-55 | WASDE is released as fixed-format PDF and Excel at 12:00 ET; USDA Export Sales weekly file is released Thursdays 08:30 ET. | §8.1 line 224 | established | data-ingest |
| C05-56 | WASDE NLP pipeline: parse PDF/XLSX into balance-sheet schema (US + world line items: acres, yield, beginning stocks, production, imports, feed use, exports, crush, ending stocks, season-average price); compute deltas vs prior report and vs Reuters/WSJ/Bloomberg analyst survey; map each line-item surprise to a pre-trained sensitivity coefficient. | §8.1 line 224 | established | data-ingest;strategy |
| C05-57 | Historical-average sensitivity: −1 million-bushel ending-stocks surprise ≈ +18¢/bu price reaction. | §8.1 line 224 | practitioner-lore | pricing-model |
| C05-58 | ML baseline for grain price prediction: gradient-boosted trees (XGBoost / LightGBM / CatBoost) with rolling time-series split and early stopping on out-of-sample holdout. | §8.3 line 232 | established | strategy;tooling |
| C05-59 | On corn/soy, gradient-boosting on tabular fundamentals (WASDE balance sheet, weekly Export Sales, NOPA crush, precip / GDD anomalies, Brazilian real, dollar index, oilshare) consistently delivers R² gains of 2–5pp on monthly price-change prediction over linear baselines; feature importance concentrated in stocks-to-use deltas, Brazilian FX, and crude/ZL relations. | §8.3 line 232 | practitioner-lore | backtest;data-ingest |
| C05-60 | Point-in-time database is mandatory for any USDA-data backtest because USDA frequently revises (annual benchmarks + small monthly revisions); naive in-sample fits leak future data. | §8.4 line 236 | established | data-ingest;backtest |
| C05-61 | ML models with 100+ inputs and ~480 monthly rows of CBOT data are chronically overparameterized and require aggressive regularization. | §8.4 line 236 | practitioner-lore | strategy |
| C05-62 | Order-flow imbalance: OFI_t = Σ q over a window with signed trade volume q_t (+1 buyer-initiated, −1 seller-initiated); Cont's linear price-impact model Δp_{t+1} ≈ λ · OFI_t with λ inversely related to top-of-book depth. | §9.1 lines 242–244 | established | pricing-model;market-structure |
| C05-63 | CME ZS trades in a price-time FIFO book; queue position determines the value of a resting order (early-filled orders capture the half-spread at low adverse selection). | §9.2 line 248 | established | market-structure |
| C05-64 | Peng (JFM 2024): a maximum-order-size rule change on CME spread markets produced 2–4× depth improvement with no meaningful change in realized volatility. | §9.2 line 248 | established | market-structure |
| C05-65 | Round-trip cost: ~$0.05–$0.10 for ZS outright vs. $0.25+ for calendar spreads (Irwin-lab IDEALS dissertation); spread books materially benefited from implied-order permissions after 2014. | §9.2 line 248 | established | market-structure |
| C05-66 | VPIN (Easley–López de Prado–O'Hara, RFS 2012) is a real-time flow-toxicity estimate; in grains used less as a price-prediction signal and more as a liquidity-withdrawal trigger for market-making strategies around USDA-report releases. | §9.3 line 252 | practitioner-lore | observability;market-structure |
| C05-67 | Goldman roll window = 5th–9th business day of the month preceding expiry; moves ~20%/day of S&P GSCI-indexed open interest from front to next-out. | §9.4 line 256 | established | market-structure |
| C05-68 | Mou (2011): pre-positioning strategies front-running the Goldman roll deliver Sharpe as high as 4.4, with profitability dependent on net index-investment size vs. arbitrage capital. | §9.4 line 256 | established | backtest;strategy |
| C05-69 | Irwin–Sanders–Yan (AEPP 2022): order-flow cost of index rolling on the GSCI portfolio is ~0.3% per year, with grains a smaller share than energies. | §9.4 line 256 | established | market-structure |
| C05-70 | Realistic discount on backtested Sharpes: multiply 2000–2015 published Sharpe ratios by 0.6–0.7 for live-money planning. | §10.1 line 264 | practitioner-lore | backtest |
| C05-71 | Grain liquidity ≈ 10–15% of WTI crude and 30–50% of gold notionally; CME ZS ADV ~200,000 contracts (~$10bn notional/day); top-of-book depth 20–50 lots typical 24-hour, 100+ at U.S. open. | §10.2 line 268 | established | market-structure |
| C05-72 | Position size <5% of daily volume: minimal market impact; >20% of ADV: most published edge eaten by slippage, especially on crush-calendar legs (ZM spreads materially thinner). | §10.2 line 268 | practitioner-lore | market-structure;strategy |
| C05-73 | Fuertes–Miffre–Rallis combined momentum + term-structure portfolio: ~10× annual turnover; at 0.069% average round-trip cost → ~0.7% annual drag; scales linearly (24× turnover ≈ 1.7% drag). | §10.3 line 272 | established | backtest |
| C05-74 | Turnover by strategy family: trend-followers 2–5×/yr; cross-sectional momentum higher; stat-arb (crush, bean-corn) 50–100×/yr (cost-brutal). | §10.3 line 272 | practitioner-lore | strategy |
| C05-75 | A net Sharpe of 0.3–0.4 is realistic for a strategy with published gross Sharpe of 0.6 after costs and capacity constraints. | §10.3 line 272 | practitioner-lore | backtest |

## 3. What this file does NOT claim

- No specific contract-spec details: tick sizes, multipliers, first-notice
  dates, last-trade-date mechanics, expiry calendars, or delivery procedures
  for ZS / ZM / ZL / ZC / ZW are not given (only the 10/9/11 crush-package
  ratio and qualitative ADV / depth figures).
- No initial / maintenance margin numbers and no SPAN methodology details.
- No detail on broker / FCM APIs, order-routing, or OMS implementation
  (queue-position economics are noted but not wired to a specific OMS).
- No cash-market / hedger workflow integration (basis trading, elevator
  hedging, processor crush margin lock-in protocols are absent).
- No specific data-vendor schemas or connector contracts (DTN, Reuters-Agri,
  Bloomberg-Ag, AgriCensus, USDA attache feeds are listed but not specified).
- No options-strategy specifications (vol-surface, skew, calendar, vertical,
  fly construction) beyond the WASDE implied-vol-crush observation.
- No specific risk-limit / drawdown-trigger rules, no Kelly-sizing or other
  bet-sizing formulas, and no explicit portfolio-construction optimizer
  (mean-variance, risk-parity, HRP) recipe.
- No backtest-engine architecture, walk-forward harness, or
  point-in-time-database schema is specified — only the requirement that one
  exists.
- No explicit treatment of cross-currency (BRL, CNY) hedging mechanics for
  Brazilian-soy plays, despite Brazilian FX appearing as a top ML feature.

## 4. Cross-links

- C05-34, C05-35 (crush coefficients and the 10/9/11 exchange package) and
  C05-67 (Goldman roll window) likely depend on a contract-specs / calendar
  research file in another phase that should pin down ZS/ZM/ZL contract
  multipliers, tick sizes, and expiry mechanics.
- C05-44, C05-55, C05-56 (WASDE / Export Sales / NOPA / FGIS data ingest) is
  likely a binding dependency on a data-pipeline / data-ingest research file
  documenting feed schedules, SLAs, and parser contracts.
- C05-60 (point-in-time database mandate) crosses directly into any
  data-architecture file — backtests in this file's strategies cannot be
  trusted without the upstream PIT store.
- C05-19, C05-22, C05-49 (storage curve seasonality, ZS October low / June
  peak, 6–8% stocks-to-use vol regime) interlock with any
  inventory / fundamentals research file; potential contradiction with
  C05-23's farmdoc finding that only 3 of 15 years showed harvest-to-spring
  rally is a known internal tension flagged in the source.
- C05-46 (WASDE implied-vol crush 70% of the time) and C05-66 (VPIN as
  liquidity-withdrawal trigger around USDA releases) both depend on an
  options / vol-surface or microstructure research file for monetization
  detail not specified here.
- C05-63, C05-64, C05-65, C05-71, C05-72 (FIFO queue, max-order-size, ZS
  outright vs. spread costs, ADV / depth) connect to an OMS / market-structure
  research file; the cost numbers here are used as inputs by C05-10, C05-38,
  C05-73 and would propagate to any net-Sharpe estimate elsewhere.
- C05-33, C05-70, C05-75 (post-publication decay haircuts) constrain *every*
  back-tested Sharpe in this file and in any other phase's strategy file —
  they should be applied as a global derating factor in cross-phase audit.
