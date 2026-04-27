# Audit C — Phase 01: Soybean Market Structure (Pre-Indexing)

## 1. Source artifact summary

`research/phase_01_soybean_market_structure.md` is the foundational primer on the
CBOT soybean complex. It treats soybeans as three jointly-determined contracts
(ZS beans, ZM meal, ZL oil), enumerates contract specifications (size, tick,
listed months, settlement, delivery), defines the variable price-limit and
federal position-limit regimes, lays out the trading venue and hours, derives
the board crush spread and gross processing margin, surveys related grain
contracts (corn ZC, Chicago SRW wheat ZW, KC wheat KE, MGEX MWE, plus DCE and
South American CME instruments), describes Northern- and Southern-Hemisphere
seasonality and the USDA reporting calendar (WASDE, Crop Progress, Prospective
Plantings, Grain Stocks, Acreage, Crop Production), categorizes participants
(farmers, country and terminal elevators, ABCD crushers, merchandisers,
swap dealers, managed money, index investors, options market makers), and
discusses options structure plus two unresolved theoretical lenses on the
forward curve (storage/convenience-yield vs. normal-backwardation/risk-premium)
along with the 2005–2010 non-convergence episode. It is scope-limited to
structure and mechanics; it does not estimate prices, recommend strategies, or
benchmark code.

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C01-01 | A soybean is roughly 80% meal and 18–20% oil by weight after crushing, with the remainder lost as hulls and moisture. | §1 (line 11) | established | density |
| C01-02 | Exchange-defined equivalence: 1 bushel (60 lb) → ~47.5 lb of 48%-protein soybean meal + ~11 lb of soybean oil. | §1 (line 11) | established | density; pricing-model |
| C01-03 | The CBOT soybean complex consists of three contracts: Soybeans (ZS), Soybean Meal (ZM), and Soybean Oil (ZL), designed around the physical crush yields. | §1 (lines 11, 15) | established | contract |
| C01-04 | USDA April 2026 WASDE forecasts U.S. MY2025/26 crush at a record 2.61 billion bushels, exports 1.54 billion bushels, ending stocks 350 million bushels — first year domestic crush decisively exceeds exports. | §1 (line 13) | established | data-ingest; inventory |
| C01-05 | USDA ERS reports soybeans comprise more than 90% of U.S. oilseed production. | §1 (line 13) | established | market-structure |
| C01-06 | Key Takeaways summary states U.S. crush at "record 2.49–2.61 billion bushels for MY2025/26"; main text §1 cites 2.61B specifically. (Internal range vs. point-estimate tension.) | Key Takeaways (line 217) vs. §1 (line 13) | debated (internal inconsistency) | inventory; data-ingest |
| C01-07 | ZS is a physically delivered futures on 5,000 bushels of No. 2 yellow soybeans at par. | §2.1 (line 21) | established | contract |
| C01-08 | ZS grade differentials: No. 1 yellow at +6¢/bu and No. 3 yellow at −6¢/bu (subject to quality conditions). | §2.1 (line 21) | established | contract; pricing-model |
| C01-09 | ZS minimum tick is ¼¢/bu = $12.50 per contract; quoted in cents and quarter-cents per bushel. | §2.1 (line 21) | established | contract; pricing-model |
| C01-10 | ZS listed months: January, March, May, July, August, September, November. | §2.1 (line 21) | established | contract |
| C01-11 | November is conventionally the U.S. "new crop" contract; July is the pre-harvest "old crop" bellwether. | §2.1 (line 21); Glossary (line 173) | established | contract; strategy |
| C01-12 | ZS last trading day = business day prior to the 15th of the contract month; trading in expiring contract closes at noon Central. | §2.1 (line 21) | established | contract |
| C01-13 | ZS final settlement = VWAP of trades in the settlement window. | §2.1 (line 21) | established | contract; pricing-model |
| C01-14 | ZS delivery is by electronic shipping certificate from regular CBOT firms (not warehouse receipt); long taking delivery receives a certificate promising loading of 5,000 bushels into a vessel on 7 days' notice. | §2.1 (line 23) | established | contract |
| C01-15 | ZS delivery location premiums: Chicago and Burns Harbor at par; Illinois River miles 304–170 at +2¢/bu; Peoria–Pekin zone (170–151) at +3¢/bu; St. Louis/Alton switching districts at +24¢/bu. | §2.1 (line 23) | established | contract; pricing-model |
| C01-16 | Soybean shipping certificate monthly storage rate raised to $0.05/bu/month following 2008 CFTC-approved revision. | §2.1 (line 23) | established | contract; pricing-model; inventory |
| C01-17 | ZM contract = 100 short tons (~91 metric tons) of 48%-protein soybean meal; quoted in $/short ton; minimum tick $0.10/ton = $10.00 per contract. | §2.2 (line 27) | established | contract; pricing-model |
| C01-18 | ZM listed months: January, March, May, July, August, September, October, December; physical delivery at regular loading facilities. | §2.2 (line 27) | established | contract |
| C01-19 | ZM final settlement = VWAP between 12:00:00 and 12:01:00 CT on last trading day. | §2.2 (line 27) | established | contract; pricing-model |
| C01-20 | ZL contract = 60,000 lb (~27 metric tons) of crude degummed soybean oil; quoted in cents and hundredths of a cent per pound; minimum tick 0.01¢/lb = $6.00 per contract. | §2.3 (line 31) | established | contract; pricing-model |
| C01-21 | ZL listed months match meal cycle: January, March, May, July, August, September, October, December. | §2.3 (line 31) | established | contract |
| C01-22 | ZL delivery via shipping certificates from regular oil processors; cleared structurally similar to bean contract. | §2.3 (line 31) | established | contract |
| C01-23 | Since 2014 CBOT grains/oilseeds use a six-monthly variable price-limit reset, replacing fixed limits. Reset every May 1 and November 1. | §2.4 (line 35) | established | market-structure; oms |
| C01-24 | Variable initial daily limit formula: 7% of average settlement of the nearest July (or December) contract over the 45 days ending two business days before April 16 / October 16, rounded to nearest 5¢/bu, with a 50¢/bu floor for soybeans. | §2.4 (line 35) | established | oms; pricing-model |
| C01-25 | Expanded daily limit = initial limit × 1.5, rounded up. | §2.4 (line 35) | established | oms; pricing-model |
| C01-26 | Complex limit interlock: if any component of the soybean complex settles at its initial limit, limits on the other two components expand the next session. | §2.4 (line 35) | established | oms; market-structure |
| C01-27 | Spot-month limits suspended starting the second business day before the first day of the delivery month (to permit convergence). | §2.4 (line 35) | established | oms; contract |
| C01-28 | Soybeans are one of nine "legacy" agricultural contracts subject to CFTC federal speculative position limits. | §2.5 (line 39) | established | oms; market-structure |
| C01-29 | Spot-month position limits calibrated to ≤25% of estimated deliverable supply. | §2.5 (line 39) | established | oms |
| C01-30 | Non-spot-month limits: 10% of OI for first 50,000 contracts, 2.5% thereafter. | §2.5 (line 39) | established | oms |
| C01-31 | Rewritten Part 150 limits effective March 2021, full compliance January 2022; bona fide hedger exemptions available; positions still count toward exchange accountability thresholds. | §2.5 (line 39) | established | oms |
| C01-32 | ZS, ZM, ZL trade on CME Globex from Sunday 7:00 p.m. through Friday 7:45 a.m. CT, with day session 8:30 a.m. to 1:20 p.m. CT Monday–Friday. | §3 (line 43) | established | market-structure |
| C01-33 | The 8:30 a.m. CT re-open coincides with major USDA report releases. WASDE and Crop Production embargoed until 11:00 a.m. ET (10:00 a.m. CT); Grain Stocks embargoed until 11:00 a.m. CT. | §3 (line 43) | established | market-structure; data-ingest |
| C01-34 | Open outcry for CBOT grain ag contracts effectively ended mid-2015 after share fell to ~1% of volume. | §3 (line 45) | established | market-structure |
| C01-35 | CME permanently shuttered most remaining open-outcry pits in May 2021 (Eurodollar options pit later retired). | §3 (line 45) | established | market-structure |
| C01-36 | CBOT grains use price limits (lock rather than halt): when daily limit hit, trading is "locked" — new transactions cannot print beyond limit price for the remainder of the session. | §3 (line 47) | established | market-structure; oms |
| C01-37 | Stop-logic and velocity-logic functionality can pause trading momentarily but are not the primary speed-bump in ags. | §3 (line 47) | established | market-structure; oms |
| C01-38 | Soybean crush formula: Crush ($/bu) = (Meal price in $/short ton × 0.022) + (Oil price in ¢/lb × 0.11) − Soybean price ($/bu). | §4 (line 53) | established | pricing-model; hedging |
| C01-39 | Crush formula constants: 0.022 = 44 lb meal / 2,000 lb per short ton; 0.11 = 11 lb oil / 100 (¢→$). (Note: meal yield in formula is 44 lb, vs. ~47.5 lb stated in §1 — internal inconsistency in source.) | §4 (line 55) vs. §1 (line 11) | debated (internal inconsistency) | pricing-model; density |
| C01-40 | Exchange "board crush" package: 10 long ZM + 9 long ZL − 11 short ZS (alternatively 11 meal + 9 oil − 10 bean), matched to weight of 50,000 bushels of beans; tradeable as single instrument on CME Globex. | §4 (line 55) | established | hedging; contract |
| C01-41 | Board crush is the hedging instrument; gross processing margin (GPM) is the operating reality. GPM = (cash meal × yield) + (cash oil × yield) − cash bean cost − variable plant cost. | §4 (line 57) | established | hedging; pricing-model |
| C01-42 | Reverse crush (long beans, short products) and oilshare (ZL value / combined product value) are common spec expressions of view. | §4 (line 59); Glossary (lines 177, 185) | established | strategy; hedging |
| C01-43 | Corn (ZC) and Chicago SRW Wheat (ZW) are 5,000-bushel physical-delivery contracts; ¼¢ = $12.50 tick; ZC delivers No. 2 yellow at par; ZW delivers No. 2 SRW at par with alternate Northern Spring and Hard Red Winter classes at specified differentials. | §5 (line 63) | established | contract |
| C01-44 | New-crop soybean-to-corn ratio = November soybeans / December corn; guides spring acreage decisions. | §5 (line 65) | established | pricing-model; strategy |
| C01-45 | Soybean-to-corn ratio rule of thumb: >2.4 tilts acreage toward soybeans, <~2.2 toward corn; long-run average ~2.3. | §5 (line 65) | practitioner-lore | strategy |
| C01-46 | CME lists South American Soybean futures settled on FOB Santos pricing. | §5 (line 67) | established | contract; market-structure |
| C01-47 | Dalian Commodity Exchange (DCE) trades soybean, meal, and oil contracts that have become increasingly informative about Chinese demand; CME publishes a CBOT-vs-DCE crush spread reference. | §5 (line 67) | established | market-structure |
| C01-48 | U.S. soybean planting typically runs late April to early June; emergence within a week of planting. | §6.1 (line 73) | established | strategy; data-ingest |
| C01-49 | Flowering begins late June to early July; pod set and pod fill (critical yield window) run through August. | §6.1 (line 73) | established | strategy |
| C01-50 | U.S. harvest begins mid-September, effectively complete by early-to-mid November across most Midwest. | §6.1 (line 73) | established | strategy |
| C01-51 | NASS Crop Progress released Mondays 4:00 p.m. ET, April through November; provides percent-planted/emerged/blooming/podding/harvested and condition by state. | §6.1 (line 73); §8 (line 117) | established | data-ingest |
| C01-52 | "Weather market" window: typically late June through mid-August in a normal year; supply outcomes dominated by near-term Midwest weather; implied vol structurally elevated. | §6.1 (line 75); Glossary (line 203) | practitioner-lore | strategy |
| C01-53 | CME white paper finds soybean 30-day implied volatility commonly reaches its annual peak around the July 4 holiday and remains high into pod-fill in August. | §6.1 (line 75) | established | strategy; backtest |
| C01-54 | Lore that soybean prices "peak on July 4 and bottom in early October" reflects historical averages on-trend years; broken in drought years (1988, 2012) and flood years. Seasonal price patterns less reliable than seasonal vol patterns. | §6.1 (line 75) | practitioner-lore | strategy; backtest |
| C01-55 | Brazil and Argentina sow October–December and harvest February–June (Southern-Hemisphere mirror cycle). | §6.2 (line 79) | established | strategy; data-ingest |
| C01-56 | Mato Grosso begins planting after September 15 per the *vazio sanitário* (Asian rust control window); finishes generally by January 7. Rio Grande do Sul starts October 1. | §6.2 (line 79) | established | data-ingest |
| C01-57 | Argentina plants November through January; harvests March to early June. | §6.2 (line 79) | established | data-ingest |
| C01-58 | By March, U.S. "old crop" (July–September contracts) competes for export share with fresh Brazilian harvest. | §6.2 (line 79) | established | strategy; market-structure |
| C01-59 | Harvest basis widens (cash discount deepens) October–November as elevators fill; narrows into spring/early summer as inventory draws and logistics constraints emerge. | §6.2 (line 81) | established | strategy; inventory |
| C01-60 | Meal basis tightens into summer grilling season and the winter hog/poultry feeding peak; oil basis reflects refinery throughput and renewable-diesel pull from U.S. West Coast. | §6.2 (line 81) | practitioner-lore | strategy |
| C01-61 | "ABCD" complex: ADM, Bunge, Cargill, Louis Dreyfus Company — globally dominant crushers and merchandisers; CHS and mid-sized U.S. cooperatives fill out the domestic roster. | §7 (line 93); Glossary (line 141) | established | market-structure |
| C01-62 | Crushers run the physical plant as a call option on crush margin; typically hedge weeks-to-months forward; put on the crush when board margins make forward production profitable. | §7 (line 93); §4 (line 57) | established | hedging; strategy |
| C01-63 | CFTC Disaggregated COT bucket "Producer/Merchant/Processor/User" is structurally short futures in aggregate (cash market is structurally long). | §7 (line 97) | established | market-structure; data-ingest |
| C01-64 | Swap dealers intermediate commodity index exposure: long futures against short swap liabilities to pensions, insurers, and retail commodity funds. | §7 (line 99) | established | market-structure |
| C01-65 | Soybean futures average daily volume "above 200,000 contracts" per CME data with open interest peaks "near 900,000". | §7 (line 101) | established | market-structure |
| C01-66 | Commodity index ("Goldman roll") concentrated 5th–9th business day of the month; January BCOM/GSCI re-weighting window; reconstitutions set following-year target weights. | §7 (line 103) | established | market-structure; strategy |
| C01-67 | Options market makers typically warehouse net short gamma into USDA reports and earn the implied-vol premium. | §7 (line 105) | practitioner-lore | strategy; market-structure |
| C01-68 | Cash prices quoted as basis to a specific futures month (e.g., "−35 November" = 35¢ under November ZS); tight basis = local demand pulling cash above futures; wide basis = grain plentiful. | §8 (line 109); Glossary (line 143) | established | pricing-model; data-ingest |
| C01-69 | WASDE released monthly, mid-month, 12:00 p.m. ET. May release first publishes new-marketing-year balances; August is first WASDE to incorporate survey-based new-crop yields. | §8 (lines 113); Glossary (line 201) | established | data-ingest |
| C01-70 | Crop Production released monthly, concurrent with WASDE through the growing season; contains yield and production estimates. | §8 (line 115) | established | data-ingest |
| C01-71 | Prospective Plantings: last business day of March, 12:00 p.m. ET; "historically the highest-impact scheduled release of the year." | §8 (line 119) | established | data-ingest |
| C01-72 | Grain Stocks: quarterly — last business day of January, March, June, September, 11:00 a.m. CT; on-farm and off-farm by state. | §8 (line 121) | established | data-ingest; inventory |
| C01-73 | Acreage report at end of June replaces Prospective Plantings number with actual June survey data. | §8 (line 123) | established | data-ingest |
| C01-74 | CME's primer notes WASDE "reduces uncertainty in corn and soybean markets around 70% of the time." | §8 (line 125) | established | data-ingest; backtest |
| C01-75 | Information propagation across the complex via board crush: bullish bean surprise attributed to tight supply lifts beans more than products (reverse crush squeezes processors); bullish surprise from strong crush demand widens the crush spread. | §8 (line 125) | practitioner-lore | strategy; hedging |
| C01-76 | Two competing forward-curve frameworks: theory of storage (Kaldor 1939; Working 1948/49; Brennan 1958) — futures = spot + storage + interest − convenience yield — vs. Hicks–Keynesian normal backwardation (futures discount = risk premium). Source explicitly does not pick a side; modern consensus is hybrid. | §8 (line 127); Glossary (lines 155, 175, 195) | debated | pricing-model; market-structure |
| C01-77 | 2005–2010 non-convergence episode: CBOT wheat (and corn, soybeans) settled at expiry with futures stubbornly above cash delivery value. | §8 (line 129) | established | market-structure; contract |
| C01-78 | Irwin et al. (2009) attribute non-convergence to a structurally fixed storage rate on shipping certificates below the value of physical storage during large inventories — the delivery instrument became a cheap call on future storage. | §8 (line 129) | debated (Irwin's view "now broadly accepted") | contract; market-structure |
| C01-79 | Exchange response: variable storage rate (VSR) regime imposed for wheat in 2010, plus storage-rate increases for soybeans and corn — has largely restored convergence. | §8 (line 129); Glossary (line 197) | established | contract; pricing-model |
| C01-80 | Some academic commentary attributed non-convergence to speculative/index-fund distortion instead of storage mechanics. Practitioner lore that "index funds broke CBOT wheat" should be sourced carefully. | §8 (line 129) | practitioner-lore (flagged as needing care) | market-structure |
| C01-81 | CBOT soybean options are American-exercise on ZS futures; standard monthly series listed against corresponding futures month; underlying = one 5,000-bushel ZS contract. | §9 (line 133) | established | contract |
| C01-82 | Options premia quoted in 1/8¢/bu = $6.25 per contract; strikes at 10¢ intervals near the money and 20¢ further out, with new strikes added as futures moves. | §9 (line 133) | established | contract; pricing-model |
| C01-83 | Short-Dated New-Crop (SDNC) options settle against new-crop (November) futures even when expiring in spring/early summer; weekly options with Friday and now daily expirations also listed. | §9 (line 135) | established | contract; hedging |
| C01-84 | Options liquidity concentrated in front three monthly series and near-the-money strikes; July, November, and January contracts anchor the vol surface. | §9 (line 135) | established | market-structure; strategy |
| C01-85 | Common practitioner option structures: weather strangles on July/August bought May/June; new-crop November put spreads bought by farmers in spring; crush-lock structures (ZM calls + ZL calls + ZS puts); calendar spreads buying November vol vs. selling August vol in early spring. | §9 (line 137) | practitioner-lore | strategy; hedging |
| C01-86 | Soybean skew tends to be call-side in pre-harvest window (weather risk = supply shock = bullish); can flip put-side once crop is made. | §9 (line 137) | practitioner-lore | strategy |
| C01-87 | CME CVOL index provides standardized 30-day implied-vol read on ZS for surface-watching. | §9 (line 137) | established | observability; data-ingest |
| C01-88 | Bushel = volumetric grain measure standardized by weight: 60 lb soybeans, 56 lb corn, 60 lb wheat. | Glossary (line 147) | established | density; pricing-model |
| C01-89 | Convenience-yield identity: F = S·e^((r+u−y)T) where r = interest, u = storage cost, y = convenience yield. | Glossary (line 155) | established | pricing-model |
| C01-90 | Convergence = forced equality between futures price and cash delivery value as contract approaches expiry. | Glossary (line 157) | established | contract; market-structure |
| C01-91 | Bona fide hedger positions can be granted exemptions from federal speculative position limits. | §2.5 (line 39) | established | oms; hedging |
| C01-92 | Complex is jointly determined: 80% meal + 18–20% oil yields anchor ZS/ZM/ZL relative pricing — every dollar that fails to equilibrate the three contracts is an arbitrage opportunity. | §1 (line 15); §4 (line 59) | established | pricing-model; hedging; market-structure |

## 3. What this file does NOT claim

The primer is scope-limited. Notable absences relative to what a downstream
code/audit pass might want:

- No specific intraday market microstructure details: no quoted spread targets,
  order-book depth, lot-size statistics, message-rate limits, or matching-engine
  behavior beyond "VWAP settlement window" and "stop-logic exists."
- No backtest evidence for the soybean-to-corn ratio thresholds (2.2 / 2.4) — they
  are presented as practitioner lore, not as estimated.
- No quantification of basis distributions: no mean/variance for harvest vs.
  spring basis at named locations.
- No specific Brazilian/Argentine production volume figures or export-share
  numbers beyond the qualitative "competes with U.S. old crop in March."
- No explicit specification of CME CVOL methodology, weights, or update cadence
  (only that it exists).
- No DCE contract specifications (size, tick, currency, hours) despite
  introducing the DCE soybean/meal/oil contracts.
- No explicit numerical position-limit values for current ZS/ZM/ZL — only the
  formulas (25% of deliverable supply, 10%/2.5% of OI tiers).
- No discussion of margin requirements, exchange fees, clearing arrangements, or
  give-up procedures.
- No options-pricing model recommendation (Black-76 vs. local-vol vs. SABR) —
  surface conventions only.
- No data-vendor or feed catalogue: which provider supplies WASDE machine-readable
  drops, NASS PDF parsing, or futures tick data is not specified.
- No guidance on time-zone handling, holiday calendars (Sunday opens, USDA
  release embargo coordination), or settlement-window code conventions.
- No treatment of FX exposure on Brazilian/Argentine crops (BRL, ARS) or freight
  spreads (Gulf vs. PNW vs. Santos).
- No discussion of CME Globex spread routing for the listed board-crush
  instrument (only that it exists).
- No mention of biofuel-policy specifics (RIN values, RVO mandates, RD vs. BD)
  even though biofuel demand is invoked as a crush driver.

## 4. Cross-links (inferred, not file-opened)

These are anticipated dependencies/contradictions with sibling research files in
this phase, inferred only from internal references in `phase_01`:

- **Crush economics (C01-04, C01-38, C01-40, C01-41, C01-62)** — likely fed by a
  separate file on crusher economics, biofuel demand, or RD/BD policy; the
  present file flags rising biofuel demand as the crush driver but does not
  quantify it.
- **Storage/convenience-yield framework (C01-76, C01-79, C01-89)** — likely
  cross-references a file on forward-curve modeling or hedging strategy where
  one of the two frameworks is operationalized for code; the source explicitly
  declines to pick a side, so any downstream file that *does* pick a side
  introduces a contradiction-by-omission with this primer.
- **Non-convergence / VSR (C01-77 through C01-80)** — likely cross-references a
  file on contract-design risk or convergence monitoring; Irwin's storage-rate
  diagnosis and the index-fund counter-narrative will both reappear there.
- **Seasonality + weather market (C01-48 through C01-54)** — likely
  cross-references a weather-data ingestion or vol-regime file. The "broken in
  1988, 2012" caveat is the seed of any backtest carve-out logic in that file.
- **Position limits and COT (C01-28 through C01-31, C01-63)** — likely
  cross-references an OMS/risk file that operationalizes the limits and a
  positioning-flow file that ingests COT.
- **Goldman roll (C01-66)** — likely cross-references an index-roll
  exploitation strategy file.
- **South American calendar (C01-55 through C01-57)** — likely cross-references
  a global supply / South-American specifically file; the *vazio sanitário* date
  is a hard data dependency.
- **Internal ZS contract weight inconsistency (C01-02 vs. C01-39)** — the
  ~47.5 lb vs. 44 lb meal yield discrepancy in the same primer is a flag for
  any downstream pricing-model code that needs to choose one constant; standard
  CME board-crush convention uses 44 lb and is the formula constant.
- **Internal MY2025/26 crush figure (C01-06)** — the 2.49–2.61 range in Key
  Takeaways vs. 2.61 point estimate in §1 needs reconciliation by any downstream
  fundamentals/balance-sheet file.
