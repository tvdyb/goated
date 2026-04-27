# Audit C — Phase 04: Discretionary Strategies (Pre-Indexing)

## 1. Source artifact summary

`research/phase_04_discretionary_strategies.md` catalogs the discretionary
playbooks named-source soybean traders use against the CBOT complex (ZS/ZM/ZL).
It is organized by strategy family — board-crush relative value, calendar
spreads, inter-market ratios (bean/corn, oilshare), report-driven trading
around the USDA calendar, weather-driven positioning (Northern-Hemisphere
pod-fill, ENSO, South-American summer), basis trading against river/rail
logistics, anticipating hedging flows (farmer harvest selling, crusher product
fixing, GSCI roll), CFTC Disaggregated COT positioning, rumor/headline trading,
and seasonal patterns. A consolidated decision-framework table maps each
family to entry trigger, sizing rule, invalidation, horizon, and expression.
The file then summarizes the public sizing rules of Brandt, Dennis/Turtles,
Parker, Raschke, Bielfeldt, and Klipp, and closes with three documented
blowup case studies (2012 drought, 2018 tariff gap and OptionSellers.com,
2022 Ukraine/Indonesia oil spike). It is not scope-limited to mechanics —
it asserts entry/exit thresholds and risk-budget rules — but the source
itself flags many of those as practitioner lore.

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C04-01 | Soybean physical conversion identity: one 60-lb bushel yields ~11 lb oil + 44 lb meal — the basis of the board crush. | §1.1 (line 13) | established | density; pricing-model |
| C04-02 | The CBOT exchange-listed crush package = 10:11:9 (10 ZM + 9 ZL − 11 ZS). | §1.1 (line 13) | established | contract; pricing-model |
| C04-03 | "Reverse crush" = long beans / short products, expressed when expecting processor margin compression. | §1.1 (line 13) | established | strategy; pricing-model |
| C04-04 | Practitioners distinguish "board crush" (hedging instrument) from gross processing margin (GPM) at the plant (operating reality). | §1.1 (line 15) | established | pricing-model; hedging |
| C04-05 | When physical GPM > ~$2/bu, crushers sell meal/oil forward and lock margin by buying the board crush. | §1.1 (line 15) | practitioner-lore | hedging; strategy; pricing-model |
| C04-06 | When board crush is cheap relative to GPM, specs put on long-crush / short-reverse-crush and are effectively paid for taking processor risk. | §1.1 (line 15) | practitioner-lore | strategy; pricing-model; hedging |
| C04-07 | The 2024–2026 renewable-diesel build-out has driven physical GPM to $2+/bu (StoneX, AgResource, Hightower flagged this regime). | §1.1 (line 15) | established | market-structure |
| C04-08 | Naïve crush mean-reversion is unprofitable after 1.5¢/bu transaction costs (Rechner & Poitras 1993, 1978–1991 sample). | §1.1 (line 17) | established | backtest; strategy; pricing-model |
| C04-09 | Adding a 3¢ entry filter raises expected profit per crush mean-reversion trade from −0.35¢/bu to +1.74¢/bu (Rechner & Poitras 1993). | §1.1 (line 17) | established | backtest; strategy |
| C04-10 | The reverse-crush spread exhibits hedging-pressure effects tied to processor short-positioning (Mou 2010). | §1.1 (line 17) | established | strategy; market-structure |
| C04-11 | The July–November soybean spread is the bellwether of old-crop / new-crop tightness. | §1.2 (line 21) | established | strategy; market-structure |
| C04-12 | When July > November (inversion), the market signals old-crop stocks are too tight to carry to new harvest. | §1.2 (line 21) | established | strategy; inventory; market-structure |
| C04-13 | When July < November (contango / "full carry"), the market signals abundance. | §1.2 (line 21) | established | strategy; inventory; market-structure |
| C04-14 | Practitioner rule: commercials fade deep carries when ending-stocks are at risk of tightening, and fade deep inverses when South America is on track for a record. | §1.2 (line 21) | practitioner-lore | strategy; hedging |
| C04-15 | The variable-storage-rate (VSR) regime caps how deep the carry can go before certificate holders find delivery and re-issuance more profitable than rolling (Irwin et al. 2009). | §1.2 (line 21) | established | market-structure; contract; inventory |
| C04-16 | Moore Research / Jake Bernstein composite studies show the July/November soybean spread tends to weaken into U.S. spring and strengthen into summer weather windows. | §1.2 (line 23) | debated | strategy |
| C04-17 | Farmdoc / Oklahoma Farm Report critique: in the last 15 years, soybean cash was higher at harvest than in spring in only 3 years (2015, 2019, 2024); only ~20% of years conform cleanly to the seasonal composite. | §1.2 (line 23) | debated | strategy |
| C04-18 | The bean/corn new-crop ratio = November ZS price ÷ December ZC price. | §1.3 (line 27) | established | pricing-model; strategy |
| C04-19 | Bean/corn ratio above ~2.5 favors soybean acreage; below ~2.2 favors corn (rule of thumb). | §1.3 (line 27) | practitioner-lore | strategy |
| C04-20 | Long-run average bean/corn ratio sits near 2.3–2.45. | §1.3 (line 27) | established | strategy; pricing-model |
| C04-21 | Discretionary specs fade the bean/corn ratio at extremes that, if sustained, would imply acreage shifts the USDA June Acreage report is unlikely to validate. | §1.3 (line 27) | practitioner-lore | strategy; data-ingest |
| C04-22 | Oilshare = ZL's share of combined product value; CME launched oilshare futures in 2024/25. | §1.3 (line 29) | established | contract; pricing-model |
| C04-23 | Pre-launch hedger expression of oilshare = 5-oil / 3-meal ratio. | §1.3 (line 29) | established | hedging; pricing-model |
| C04-24 | Oilshare has periodically punched through 45–50% on renewable-diesel demand. | §1.3 (line 29) | established | market-structure; pricing-model |
| C04-25 | RFS / biofuel policy is a first-order driver of oilshare direction ("long oilshare is long RFS"). | §1.3 (line 29) | practitioner-lore | strategy; market-structure |
| C04-26 | WASDE is monthly, releases at 12:00 ET. | §2 (line 35) | established | data-ingest |
| C04-27 | Crop Progress is weekly, Mondays at 16:00 ET, April–November. | §2 (line 35) | established | data-ingest |
| C04-28 | Weekly Export Sales releases Thursday at 08:30 ET. | §2 (line 35) | established | data-ingest |
| C04-29 | Quarterly Grain Stocks reports release on the last business day of January, March, June, and September, at 12:00 ET. | §2 (line 35) | established | data-ingest |
| C04-30 | Other key calendar events: March Prospective Plantings and June Acreage. | §2 (line 35) | established | data-ingest |
| C04-31 | The 48 hours before WASDE is a "flatten or fade" window — traders who can't stomach gap risk reduce gross exposure; those who can price both sides of consensus. | §2 (line 37) | practitioner-lore | strategy; oms |
| C04-32 | The WASDE consensus is sourced from the Reuters / Wall Street Journal analyst surveys. | §2 (line 37) | established | data-ingest |
| C04-33 | The WASDE "whisper" is what sell-side desks (StoneX, Hightower, AgResource) publish in the final hours; it frequently differs from the survey mean. | §2 (line 37) | established | data-ingest; strategy |
| C04-34 | USDA has a documented tendency to under-estimate early-season yields. | §2 (line 37) | established | data-ingest; strategy |
| C04-35 | WASDE typically reduces implied-vol uncertainty about 70% of the time (CME). | §2 (line 39) | established | strategy; market-structure |
| C04-36 | Canonical WASDE fade setup: post-report expansion stalls inside the first hour. | §2 (line 39) | practitioner-lore | strategy |
| C04-37 | Fades fail when the number is a genuine regime change rather than statistical noise (Sept 2025 Grain Stocks shock cited). | §2 (line 39) | established | strategy; backtest |
| C04-38 | Pro Farmer Crop Tour methodology: scouts count pods in a 3'×3' square from three plants per sampled field across seven states; published national estimate each August. | §2 (line 41) | established | data-ingest |
| C04-39 | Midwest June–August is the canonical pod-fill weather window for U.S. soybeans. | §3 (line 47) | established | strategy; data-ingest |
| C04-40 | CME papers document a seasonal vol-pump clustered around the U.S. ridge-pattern risk window ("Vol is High by the Fourth of July"). | §3 (line 47) | established | strategy |
| C04-41 | Discretionary weather play: overlay the 2-week GFS/ECMWF consensus against NASS state crop-condition ratings each Monday; size into forecasted heat ridges rather than holding through the whole window. | §3 (line 47) | practitioner-lore | strategy; data-ingest |
| C04-42 | La Niña correlates with dryness in southern Brazil and Argentina. | §3 (line 49) | established | strategy |
| C04-43 | El Niño typically benefits South American yields but can spoil U.S. conditions via Gulf-moisture surplus. | §3 (line 49) | established | strategy |
| C04-44 | The 2021–22 La Niña produced a ~$3/bu rally in soymeal off Argentine drought (cited as the blueprint when Argentina enters pod-fill in late January–February). | §3 (line 49) | established | strategy |
| C04-45 | January–February is the high-information window for Brazil's Center-West, Rio Grande do Sul, and Argentina. | §3 (line 51) | established | data-ingest; strategy |
| C04-46 | Practitioners watch CONAB, AgRural, IMEA, and Agroconsult crop-tour estimates against weekly private commentary in the SAm summer window. | §3 (line 51) | established | data-ingest |
| C04-47 | Country elevators take farmer flow, basis-trade short futures vs. long cash, and earn basis appreciation from harvest lows into the spring squeeze. | §4 (line 57) | established | strategy; market-structure |
| C04-48 | At harvest, heavy farmer selling compresses cash while futures hold up, so basis blows out. | §4 (line 57) | established | market-structure; strategy |
| C04-49 | Post-harvest, basis narrows as inventories draw and logistics constraints emerge. | §4 (line 57) | established | market-structure; inventory |
| C04-50 | Export basis at Gulf and PNW terminals tracks global demand against barge and rail logistics. | §4 (line 59) | established | market-structure |
| C04-51 | The 2022–2024 low-water episodes on the Mississippi and Illinois rivers pushed Memphis and St. Louis basis to their weakest levels since 2019. | §4 (line 59) | established | market-structure |
| C04-52 | A country-elevator basis trader reads USACE lock tonnage, the DTN river-levels feed, and Illinois Waterway status daily. | §4 (line 59) | practitioner-lore | data-ingest |
| C04-53 | ~75% of U.S. beans move through a country elevator before reaching barge or rail (Soy Transportation Coalition). | §4 (line 59) | established | market-structure |
| C04-54 | Basis playbook: long basis (buy cash, short futures) when barge freight is expected to fall (wet year, strong river). | §4 (line 59) | practitioner-lore | strategy; hedging |
| C04-55 | Basis playbook: short basis when freight is expected to rise (drought, low-water summer). | §4 (line 59) | practitioner-lore | strategy; hedging |
| C04-56 | Canonical farmer harvest pattern: combine-run beans sold October–November, compressing both outright price and basis. | §5 (line 65) | established | market-structure; strategy |
| C04-57 | National average basis reached 80.5 cents under November futures in September 2025. | §5 (line 65) | established | market-structure |
| C04-58 | Iowa State 5-year average basis benchmark = $0.76/bu under November futures. | §5 (line 65) | established | strategy; pricing-model |
| C04-59 | Speculator response: fade the harvest low once farmer flow slows. | §5 (line 65) | practitioner-lore | strategy |
| C04-60 | Crusher fixing — "when crush margins are fat, crushers sell meal/oil to the trade and bid beans hard" — visible as basis firming and crush spread pay-down. | §5 (line 67) | practitioner-lore | strategy; hedging |
| C04-61 | Goldman roll window = days 5 through 9 of the month preceding contract expiration. | §5 (line 69) | established | strategy; market-structure |
| C04-62 | ~20%/day of S&P GSCI-indexed open interest moves from front to next-out across the Goldman roll window. | §5 (line 69) | established | strategy; market-structure |
| C04-63 | The Goldman roll effect is smaller in soybeans than in crude but still tradeable around the five major roll months the GSCI prescribes. | §5 (line 69) | established | strategy; market-structure |
| C04-64 | Since 2009 the CFTC publishes the Disaggregated COT report alongside the Legacy report. | §6 (line 75) | established | data-ingest |
| C04-65 | Disaggregated COT splits Producer/Merchant/Processor/User (commercials), Swap Dealers, Managed Money, and Other Reportables. | §6 (line 75) | established | data-ingest |
| C04-66 | Extreme Managed Money net longs/shorts are typically contrarian signals when paired with stalling price action. | §6 (line 75) | practitioner-lore | strategy |
| C04-67 | COT inflections are more reliable when Managed Money flips net short → net long (or vice versa) coincident with a momentum signal on price. | §6 (line 77) | practitioner-lore | strategy |
| C04-68 | Absolute extreme MM longs (>200,000 contracts in ZS) preceded 2021 and 2025 tops; similar readings persisted for months in 2012 drought. | §6 (line 77) | debated | strategy |
| C04-69 | Commercials are structurally short, so "commercials are building length" is a more informative tape than "specs are long." | §6 (line 77) | practitioner-lore | strategy |
| C04-70 | USDA daily flash-sale reporting threshold = >100,000 MT to a single destination in a single day. | §7 (line 83) | established | data-ingest; contract |
| C04-71 | Modern reliable headline setup: "buy the rumor, sell the fact" on Chinese purchases (Oct/Nov 2025 framework deal and flash-sale sequence). | §7 (line 85) | established | strategy |
| C04-72 | Biofuel-policy trades follow the same pattern: 2023 RVO proposal and 2025/26 "Set 2" rule produced sharp oilshare rallies as positioning chased each leak. | §7 (line 85) | established | strategy |
| C04-73 | Most cited seasonal soybean patterns: February break, summer weather rally (June–July pop), harvest low (October–November). | §8 (line 91) | debated | strategy |
| C04-74 | Vol is reliably higher into July 4 and into March Prospective Plantings — a vol regime, not a directional signal. | §8 (line 93) | established | strategy |
| C04-75 | Seasonal composites are defensible as vol regimes but indefensible as standalone directional signals. | §8 (line 93) | debated | strategy |
| C04-76 | Brandt critique: "trade identification, or signaling, is far down the list of important aspects of market speculation." | §8 (line 93) | practitioner-lore | strategy |
| C04-77 | Board-crush relative-value entry trigger: board crush trades 50¢+ cheap vs. published plant GPM, or vs. stocks-implied fair value from WASDE. | §9 (line 103) | practitioner-lore | strategy; pricing-model |
| C04-78 | Board-crush sizing: processors risk-budget by plant-equivalent volume; specs size at fixed $/bp of crush. | §9 (line 103) | practitioner-lore | strategy; hedging |
| C04-79 | Board-crush invalidation: close through 20-day moving average on the spread; horizon 2 weeks – 3 months; expression = 10:11:9 package. | §9 (line 103) | practitioner-lore | strategy |
| C04-80 | July/Nov calendar entry: spread prints new inverted (or carry) extreme vs. prior-year Stocks ratio; sizing volatility-scaled to spread ATR; invalidation = break of trend-line; horizon 1–6 months; expression = legged calendar. | §9 (line 104) | practitioner-lore | strategy |
| C04-81 | Oilshare strategy entry: oilshare diverges from RFS/biodiesel RIN signal; sizing = short vega per 1 vol point of oilshare index; invalidation = policy rollback / rule reversal; horizon = months; expression = ZL–ZM ratio or oilshare futures. | §9 (line 105) | practitioner-lore | strategy; hedging |
| C04-82 | WASDE fade entry: post-release price pushes >1.5σ vs. pre-report range and stalls in first 15 minutes. | §9 (line 106) | practitioner-lore | strategy |
| C04-83 | WASDE fade sizing: 25–50 bp of NAV; stop at session extreme; invalidation = close through post-release extreme; horizon = intraday – 3 days. | §9 (line 106) | practitioner-lore | strategy; oms |
| C04-84 | Crop Progress / weather entry: ridge in the 6–10 day ECMWF/GFS overlays deteriorating conditions. | §9 (line 107) | practitioner-lore | strategy; data-ingest |
| C04-85 | Crop Progress / weather sizing: scale with forecast conviction; invalidation = forecast wet shift; horizon = days – 3 weeks; expression = long vol (strangle) or outright. | §9 (line 107) | practitioner-lore | strategy; hedging |
| C04-86 | La Niña Argentina entry: ONI index confirms La Niña + Argentine January soil-moisture deficit. | §9 (line 108) | practitioner-lore | strategy; data-ingest |
| C04-87 | La Niña Argentina sizing: 1–2% of NAV notional; invalidation = rains by late January; horizon = 4–8 weeks; expression = long ZM outright or ZM–ZL spread. | §9 (line 108) | practitioner-lore | strategy |
| C04-88 | Country-vs-export basis entry: basis reaches a seasonal extreme of ±2σ vs. a 5-yr range. | §9 (line 109) | practitioner-lore | strategy |
| C04-89 | Country-vs-export basis sizing: capped by elevator storage / freight capacity; invalidation = barge freight reverses; horizon = weeks – months; expression = cash-vs-futures (physical). | §9 (line 109) | practitioner-lore | strategy; inventory |
| C04-90 | Harvest hedge-pressure fade entry: national basis at or below 5-yr average −20¢ and farmer selling slows. | §9 (line 110) | practitioner-lore | strategy |
| C04-91 | Harvest hedge-pressure fade sizing: scale into gaps; invalidation = farmer re-engages; horizon = 2–8 weeks; expression = outright long or basis long. | §9 (line 110) | practitioner-lore | strategy |
| C04-92 | COT inflection entry: Managed Money flip + price momentum confirmation. | §9 (line 111) | practitioner-lore | strategy |
| C04-93 | COT inflection sizing: Kelly-scaled to positioning extreme; invalidation = price re-crosses signal level; horizon = 1–4 weeks; expression = outright or option spread. | §9 (line 111) | practitioner-lore | strategy |
| C04-94 | Rumor/headline entry: tape event (flash sale, tariff, RFS leak) moves >2σ in <15 min. | §9 (line 112) | practitioner-lore | strategy |
| C04-95 | Rumor/headline sizing: small initial, add on retrace; invalidation = gap fill; horizon = intraday – 1 week; expression = outright or short-dated option. | §9 (line 112) | practitioner-lore | strategy; oms |
| C04-96 | Seasonal entry: composite window aligns with current tape; sizing = small fixed-fraction; invalidation = composite contradicted by fundamentals; horizon = 4–12 weeks; expression = seasonal spread or outright. | §9 (line 113) | practitioner-lore | strategy |
| C04-97 | Brandt risk rule: ≤0.5–1% of nominal capital per trade; position sized from distance to "Last Day Rule" stop. | §9 (line 115) | practitioner-lore | strategy; oms |
| C04-98 | Brandt accepts a ~30% win rate because average winner / average loser is ~3:1. | §9 (line 115) | practitioner-lore | strategy |
| C04-99 | Turtle (Dennis) sizing: 1 unit = the notional dollar amount at which a 1×N move (where N ≈ 20-day ATR) equals 1% of equity. | §9 (line 115) | established | strategy; oms |
| C04-100 | Turtle pyramiding: capped at 4 units per market and 6 units per closely-correlated group. | §9 (line 115) | established | strategy; oms |
| C04-101 | Jerry Parker sizing: ATR-based with a minimum-ATR floor to prevent outsized positions when volatility compresses. | §9 (line 115) | practitioner-lore | strategy; oms |
| C04-102 | Jerry Parker allocation: 25% risk-budget slice to commodities within a four-asset-class framework. | §9 (line 115) | practitioner-lore | strategy |
| C04-103 | Linda Raschke sizes positions by risk-to-stop in ticks. | §9 (line 115) | practitioner-lore | strategy; oms |
| C04-104 | Raschke "Holy Grail" entry: ADX > 30 + pullback to 20-EMA. | §9 (line 115) | practitioner-lore | strategy |
| C04-105 | Raschke "Anti" entry: bull/bear flag after an impulse, with MACD 3-10-16 confirmation. | §9 (line 115) | practitioner-lore | strategy |
| C04-106 | Bielfeldt approach: refused diversification, concentrated in a single complex (corn → soy), sized up only after the trend had proved itself. | §9 (line 115) | practitioner-lore | strategy |
| C04-107 | Klipp discipline: a one-tick-exit floor rule encapsulated in "the first loss is the best loss." | §9 (line 115) | practitioner-lore | strategy; oms |
| C04-108 | 2012 drought: November soybeans rallied from $12.45 low (June 4, 2012) to a $17.89 all-time high (Sep 4, 2012). | §10 (line 121) | established | strategy; market-structure |
| C04-109 | 2012 follow: July 2013 contract peaked $3.85 above its June low on Sep 14, 2012. | §10 (line 121) | established | strategy |
| C04-110 | 2012 failure mode: traders fading the rally on the short-crop seasonal template were right on path but wrong on timing — many CTAs were stopped out before the September peak. | §10 (line 121) | established | strategy |
| C04-111 | 2018 tariff gap: April 4, 2018 China announced a 25% tariff list on U.S. soybeans; May ZS gapped ~40¢ lower intraday before partially recovering. | §10 (line 123) | established | strategy; market-structure |
| C04-112 | 2018 lesson: size that's fine in a data-driven tape becomes fatal in a headline-driven tape (basis-long positions without headline-risk hedges absorbed shock directly). | §10 (line 123) | established | strategy; hedging |
| C04-113 | 2018 OptionSellers.com: Cordier short-strangle fund blew up $150M on a November 2018 nat-gas spike — cautionary for grain short-gamma desks. | §10 (line 125) | established | strategy; hedging |
| C04-114 | Structural risk for grain short-gamma: combination of negative gamma, headline-sensitive market, and insufficient wing cover. | §10 (line 125) | established | strategy; hedging |
| C04-115 | 2022 Ukraine war vol: soybean oil averaged $1,957/t in March 2022 vs. $765/t in 2019. | §10 (line 127) | established | market-structure; pricing-model |
| C04-116 | Indonesia's April 2022 palm-oil export ban amplified the soybean-oil spike. | §10 (line 127) | established | market-structure |
| C04-117 | 2022 lesson: correlation breaks in tail events — soybean oil shifted from "feed oil" to "energy oil" pricing, and oilshare models calibrated to pre-war regimes blew through stops. | §10 (line 127) | established | strategy; pricing-model |

## 3. What this file does NOT claim

The artifact does not produce a quantitative edge estimate (Sharpe, hit-rate,
expectancy) for any of the discretionary playbooks except the Rechner & Poitras
crush mean-reversion result (C04-08, C04-09). It does not specify a code-level
data schema for the USDA report calendar — it gives release times and cadences
but not field layouts or parser specs. It does not define the exact threshold
for a "deep" carry or "deep" inverse on the July/November spread; the deep-carry
fade is given as practitioner heuristic without a numeric trigger. It does not
specify how processors compute their "stocks-implied fair value from WASDE" for
the board-crush trigger (C04-77) — only that they do. It does not estimate
slippage or transaction costs for any strategy other than Rechner & Poitras.
It does not benchmark COT-extreme thresholds beyond the loose ">200,000
contracts in ZS" reference (C04-68), and even there flags it as
condition-dependent. It does not specify the 5-yr window or detrending
methodology for the "±2σ of 5-yr range" basis trigger (C04-88). It does not
discuss order-routing, latency, or microstructure — there is no claim about
where to execute the 10:11:9 leg or how to handle leg-risk. It does not name
specific data vendors for ECMWF/GFS, nor specify the resolution or the
ridge-detection algorithm. It does not commit to a single risk model for
sizing — Brandt, Turtle, Parker, and Raschke rules are listed as alternatives,
not synthesized into one rule. It does not address tax, regulatory, or
position-limit constraints on any strategy.

## 4. Cross-links

The board-crush identity (C04-01) and the 10:11:9 package (C04-02) both
depend on contract specifications that should already be established in
Phase 01 (CBOT contract sizes, tick increments, listed months). Phase 04's
abbreviated treatment of the variable-storage-rate logic (C04-15)
explicitly defers to Phase 01 ("disciplines how deep the carry can go"
references the Phase 01 VSR discussion). The USDA reporting-calendar
release times (C04-26 through C04-30) overlap with Phase 01's calendar
description; a discrepancy in either direction would be a cross-file
audit flag. The bean/corn ratio (C04-18 through C04-21) implicitly uses
Phase 01's November ZS and December ZC contract definitions. The oilshare
futures launch (C04-22) is a Phase 01 contract-spec datum that Phase 04
treats as given. The 2008 CFTC-approved storage-rate revision implied by
the VSR discussion is canonically a Phase 01 fact. The country-elevator
flow share (C04-53) and river-logistics basis claims (C04-50 through
C04-55) likely depend on a separate phase covering the physical supply
chain — Phase 04 cites the Soy Transportation Coalition figure as
established but treats logistics infrastructure as exogenous. The
Disaggregated COT taxonomy (C04-65) belongs to a market-structure /
participants section likely covered in Phase 01 as well; Phase 04 only
uses the labels to define positioning signals. The CME 2024/25 oilshare
futures launch (C04-22) and the renewable-diesel-driven GPM regime
(C04-07) are economic facts whose origin and policy mechanics may be
expanded in a separate biofuels-policy or demand-side phase; Phase 04
treats the policy binary ("long oilshare is long RFS," C04-25) as the
operative input rather than deriving it.
