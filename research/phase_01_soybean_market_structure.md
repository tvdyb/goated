# Phase 01 — Soybean Market Structure: A Physical and Financial Primer

## Abstract

Soybeans are a globally traded oilseed whose economics are best understood as a three-product complex: the raw bean (CME/CBOT symbol ZS), the protein meal produced by crushing (ZM), and the vegetable oil co-product (ZL). The three contracts are bound together by the physical crush and therefore by the "board crush" spread, which anchors the relative value of all three. Price discovery at the Chicago Board of Trade interacts with local cash markets via basis, with the USDA reporting calendar (WASDE, Crop Progress, Grain Stocks, Prospective Plantings, Crop Production) serving as the dominant scheduled information flow. Seasonality is bimodal — a Northern-Hemisphere "weather market" window from June through August, mirrored six months later by a South American growing season. This primer reviews contract specifications, delivery mechanics on the Illinois River, participants, the options surface, and the convenience-yield/storage-theory lens through which grain forward curves are typically interpreted. It is the foundation layer for downstream soybean research.

---

## 1. The soybean complex: beans, meal, oil (ZS / ZM / ZL)

A soybean is roughly 80% meal and 18–20% oil by weight after crushing, with the rest lost as hulls and moisture; the exchange-defined equivalence is 1 bushel (60 lb) → ~47.5 lb of 48%-protein soybean meal + ~11 lb of soybean oil. The three Chicago Board of Trade (CBOT) contracts — Soybeans (ZS), Soybean Meal (ZM), and Soybean Oil (ZL) — are designed around those physical yields, and the exchange publishes a "Soybean Crush Reference Guide" that uses those weights to translate prices between $/bu beans, $/short ton meal, and ¢/lb oil ([CME Soybean Crush Reference Guide](https://www.cmegroup.com/education/files/soybean-crush-reference-guide.pdf); [CME "Soybean Production, Use, and Transportation"](https://www.cmegroup.com/education/courses/introduction-to-agriculture/grains-oilseeds/soybean-production-use-and-transportation.html)).

On the demand side, soybean meal is overwhelmingly fed to livestock (poultry, swine, aquaculture, cattle), while soybean oil splits between edible-oil uses (frying, margarine, bottled oil) and, increasingly, biofuel feedstock (biodiesel and renewable diesel). USDA's Economic Research Service (ERS) notes that soybeans comprise more than 90% of U.S. oilseed production, and that crush has been rising as biofuel demand competes with exports for a share of the U.S. bean ([USDA ERS, "Oil Crops Sector at a Glance"](https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops/oil-crops-sector-at-a-glance); [USDA ERS "Soybeans and Oil Crops" topic page](https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops)). USDA's April 2026 WASDE forecasts U.S. MY2025/26 crush at a record 2.61 billion bushels against exports of 1.54 billion bushels, with ending stocks of 350 million bushels — the first year in recent memory in which domestic crush decisively exceeds exports ([USDA WASDE](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)).

The defining feature of the complex is that ZS, ZM, and ZL are not three independent commodities; they are one physical conversion expressed in three contracts, and the crush spread is the tether.

## 2. Contract specifications

### 2.1 Soybeans (ZS)

ZS is a physically delivered futures on 5,000 bushels of No. 2 yellow soybeans at par, with No. 1 yellow at +6¢/bu and No. 3 yellow at −6¢/bu subject to quality conditions. Price is quoted in cents and quarter-cents per bushel; the minimum tick is ¼¢/bu = $12.50 per contract. Listed contract months are January, March, May, July, August, September, and November, with November conventionally the "new crop" U.S. contract and July the pre-harvest "old crop" ([CME "Soybean Futures Contract Specs"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.contractSpecs.html); [CBOT Rulebook Chapter 11 — Soybean Futures](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)). Last trading day is the business day prior to the 15th of the contract month, and trading in the expiring contract closes at noon Central, with final settlement derived as a volume-weighted average price (VWAP) of trades in the settlement window ([CBOT Chapter 11](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)).

Delivery is by electronic shipping certificate issued by regular CBOT firms, not by warehouse receipt on a specific lot — the long taking delivery receives a certificate that promises loading of 5,000 bushels into a vessel on 7 days' notice. Chicago and Burns Harbor are par; Illinois River stations between river miles 304 and 170 deliver at a +2¢/bu premium, and the Peoria–Pekin zone (170–151) at +3¢/bu. St. Louis/Alton switching districts may deliver at a +24¢/bu premium ([CBOT Rulebook Chapter 7 — Delivery Facilities and Procedures](https://www.cmegroup.com/rulebook/CBOT/I/7.pdf); [U.S. Soy, "CBOT's Delivery Process Helps Get U.S. Soy to Buyers"](https://ussoy.org/cbots-delivery-process-helps-get-u-s-soy-to-buyers/)). Shipping certificates carry a monthly storage rate that is now adjustable: the 2008 CFTC-approved revision raised soybean storage to $0.05/bu/month, and the exchange separately adopted a variable storage rate rule for CBOT wheat that is instructive for the complex (see §8) ([Irwin, Garcia, Good, Kunda (2009), "Poor Convergence Performance of CBOT Corn, Soybean and Wheat Futures Contracts: Causes and Solutions"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1392380); [CFTC Subcommittee on Convergence Report](https://www.cftc.gov/sites/default/files/idc/groups/public/@aboutcftc/documents/file/reportofthesubcommitteeonconve.pdf)).

### 2.2 Soybean Meal (ZM)

ZM is 100 short tons (~91 metric tons) of 48%-protein soybean meal, quoted in $/short ton; the minimum tick is $0.10/ton = $10.00 per contract. Listed months are January, March, May, July, August, September, October, and December, with physical delivery at regular loading facilities. Final settlement of the expiring month is a VWAP between 12:00:00 and 12:01:00 CT on the last trading day ([CME "Soybean Meal Contract Specs"](https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-meal_contract_specifications.html); [CBOT Rulebook Chapter 13](https://www.cmegroup.com/rulebook/CBOT/II/13/13.pdf)).

### 2.3 Soybean Oil (ZL)

ZL is 60,000 pounds (~27 metric tons) of crude degummed soybean oil, quoted in cents and hundredths of a cent per pound; the minimum tick is 0.01¢/lb = $6.00 per contract. Listed months match the meal cycle: January, March, May, July, August, September, October, December. Delivery takes place via shipping certificates from regular oil processors and is cleared in a way structurally similar to the bean contract ([CME "Soybean Oil Contract Specs"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean-oil.contractSpecs.html); [CBOT Rulebook Chapter 12](https://www.cmegroup.com/rulebook/CBOT/II/12/12.pdf); [CME "CBOT Soybean Oil Futures — Delivery Mechanism"](https://www.cmegroup.com/articles/2021/cbot-soybean-oil-futures-delivery-mechanism.html)).

### 2.4 Price limits — dynamic / "variable" mechanism

Since 2014 CBOT grains and oilseeds have used a six-monthly variable price-limit reset, replacing the old fixed limits. Every May 1 and November 1 the initial daily limit is recomputed as 7% of the average settlement of the nearest July (or December) contract over the 45 days ending two business days before April 16 / October 16, rounded to the nearest 5¢/bu with a 50¢/bu floor for soybeans ([CME, "Price Limits: Ags, Energy, Metals, Equity Index"](https://www.cmegroup.com/trading/price-limits.html); [CME Group press release on variable limits](https://investor.cmegroup.com/news-releases/news-release-details/cme-group-receives-approval-changes-daily-price-limits-cbot)). The expanded limit is the initial limit × 1.5, rounded up. If any component of the soybean complex settles at its initial limit, limits on the other two components expand the next session — a hard-wired acknowledgement that the complex is jointly determined ([CME Price Limits](https://www.cmegroup.com/trading/price-limits.html)). Spot-month limits are suspended starting the second business day before the first day of the delivery month so that convergence can occur ([CBOT Chapter 11](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)).

### 2.5 Position limits

Soybeans are one of the nine "legacy" agricultural contracts for which the CFTC sets federal speculative position limits. Spot-month limits are calibrated to no more than 25% of estimated deliverable supply; non-spot-month limits are set at 10% of open interest for the first 50,000 contracts and 2.5% thereafter ([CFTC, "Speculative Limits"](https://www.cftc.gov/IndustryOversight/MarketSurveillance/SpeculativeLimits/speculativelimits.html)). The rewritten Part 150 limits took effect in March 2021 with full compliance in January 2022. Bona fide hedgers can be granted exemptions; positions still count toward exchange accountability thresholds.

## 3. Market hours and venue

ZS, ZM, and ZL trade electronically on CME Globex from Sunday 7:00 p.m. through Friday 7:45 a.m. CT, with a pre-open/maintenance gap and a "day" session from 8:30 a.m. to 1:20 p.m. CT Monday through Friday ([CME "Grain and Oilseed Fact Card"](https://www.cmegroup.com/markets/agriculture/grain-and-oilseed.html); [CME "Trading Hours"](https://www.cmegroup.com/trading-hours.html)). The 8:30 a.m. re-open is timed to coincide with major USDA report releases, which are embargoed until 11:00 a.m. ET (10:00 a.m. CT) for WASDE and Crop Production, and 11:00 a.m. CT for Grain Stocks ([CME, "Understanding Major USDA Reports"](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)).

Open outcry, the historical pit-trading method, effectively ended for CBOT agricultural contracts in mid-2015 when CME closed the grain futures pits after open-outcry share had fallen to roughly 1% of volume. CME permanently shuttered almost all remaining open-outcry trading pits in May 2021 after the COVID-era closures, leaving only the Eurodollar options pit open, and that too has since been retired ([CME Group press release, May 4, 2021, "CME Group to Permanently Close Most Open Outcry Trading Pits"](https://www.cmegroup.com/media-room/press-releases/2021/5/04/cme_group_to_permanentlyclosemostopenoutcrytradingpitseurodollar.html); [FIA MarketVoice, "End of an Era"](https://www.fia.org/marketvoice/articles/end-era)). The legacy pit "settlement" windows have been replaced by electronic VWAP settlement procedures defined in the rulebook ([CBOT Chapter 11](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)).

CBOT grains use price limits rather than the dynamic percentage circuit breakers that govern equity index futures: when the market reaches its daily limit, trading is not halted but is "locked" such that new transactions cannot print beyond the limit price for the remainder of the session ([CME, "Understanding Price Limits and Circuit Breakers"](https://www.cmegroup.com/education/articles-and-reports/understanding-price-limits-and-circuit-breakers)). Stop-logic functionality and velocity logic can still pause trading momentarily to prevent runaway cascades, but they are not the primary speed-bump in ags.

## 4. The crush spread

The soybean crush spread is the difference between the revenue from selling one bushel's worth of meal and oil and the cost of buying the bushel of beans. In $/bu terms the standard conversion is:

    Crush ($/bu) = (Meal price in $/short ton × 0.022) + (Oil price in ¢/lb × 0.11) − Soybean price ($/bu)

where 0.022 = 44 lb meal / 2,000 lb per short ton and 0.11 = 11 lb oil / 100 (to get ¢→$) ([CME Soybean Crush Reference Guide](https://www.cmegroup.com/education/files/soybean-crush-reference-guide.pdf); [CME, "Understanding Soybean Crush"](https://www.cmegroup.com/education/courses/introduction-to-agriculture/grains-oilseeds/understanding-soybean-crush)). In practice, because the ZS, ZM, and ZL contracts have different sizes, the exchange's "board crush" package is 10 long ZM + 9 long ZL − 11 short ZS (alternatively quoted as 11 soybean meal + 9 soybean oil − 10 soybean), matched to the weight of 50,000 bushels of beans. It can be entered as a single instrument on CME Globex, and the exchange lists it under its "Soybean Crush Spreads" product ([CME, "Soybean Crush Spreads"](https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-crush-spreads.html)).

The *board crush* (derived from futures) should be distinguished from the *gross processing margin* (GPM), which uses realized cash prices at the plant. A processor's GPM = (cash meal × yield) + (cash oil × yield) − cash bean cost − variable plant cost. Board crush is the hedging instrument; GPM is the operating reality. Crushers manage the gap — running the plant harder when GPM is fat and slowing when it is thin — and routinely put on the crush when board margins make forward production profitable, effectively locking in the physical margin via futures ([CME Crush Reference Guide](https://www.cmegroup.com/education/files/soybean-crush-reference-guide.pdf); [FarmProgress, "High crush margins drive rapid expansion"](https://www.farmprogress.com/soybean/high-crush-margins-drive-rapid-expansion)).

Because every dollar that would not equilibrate the three contracts is an arbitrage opportunity — physical crushers can buy the board crush when it trades cheaply and a long-oil / long-meal / short-bean position replicates the processor's cash flow — the crush spread is what keeps ZS, ZM, and ZL from drifting. Speculators trade the *reverse crush* (long beans, short products) when they expect margins to compress, and the *oilshare* (ZL value as a fraction of combined product value) to express a view on the meal-vs-oil mix without taking a directional bean bet ([CME, "An Introduction to Soybean Oilshare Futures and Options"](https://www.cmegroup.com/articles/2025/an-introduction-to-soybean-oilshare-futures-and-options.html)).

## 5. Related contracts in the broader grain complex

Corn (ZC) and Chicago Soft Red Winter Wheat (ZW) are the other two CBOT grain benchmarks. Both are 5,000-bushel physical-delivery contracts quoted in cents and quarter-cents per bushel with a ¼¢ = $12.50 tick. Corn delivers No. 2 yellow at par; wheat delivers No. 2 SRW at par with multiple alternate Northern Spring and Hard Red Winter classes at specified differentials ([CME Corn Contract Specs](https://www.cmegroup.com/markets/agriculture/grains/corn.contractSpecs.html); [CME Chicago SRW Wheat Contract Specs](https://www.cmegroup.com/markets/agriculture/grains/wheat.contractSpecs.html)).

Cross-commodity ratios matter because U.S. farmers in the I-states (Iowa, Illinois, Indiana) rotate corn and soybeans on the same acres. The most-watched signal is the *new-crop soybean-to-corn ratio* — November soybeans over December corn — which guides spring acreage decisions. A widely cited rule of thumb is that a ratio above 2.4 tilts acreage toward soybeans, below about 2.2 toward corn, with a long-run average around 2.3 ([FarmProgress, "Neutral price ratio guides 2026 crop choices"](https://www.farmprogress.com/crops/soybean-to-corn-price-ratio-offers-neutral-signal-for-2026-planting-decisions-across-midwest-farms); [Michigan State Extension, "Understanding the corn-soybean ratio"](https://www.canr.msu.edu/news/the-corn-soybean-ratio-and-its-potential-impact-on-farm-profits); [Iowa State Ag Decision Maker](https://www.extension.iastate.edu/agdm/crops/html/a2-40.html)). The ratio does real work in the March Prospective Plantings report and gets traded as a spread by both farmers hedging acreage risk and speculators betting on planted-acreage revisions.

A smaller set of related contracts — Kansas City Hard Red Winter Wheat (KE), MGEX Hard Red Spring Wheat (MWE), rough rice, and oats — fills out the grain complex. Globally, the Dalian Commodity Exchange in China trades soybean, meal, and oil contracts that have become increasingly informative about Chinese demand, and CME itself lists South American Soybean futures (settled on FOB Santos pricing) to address the growing importance of Brazilian supply ([CME "South American Soybean Futures at CME Group"](https://www.cmegroup.com/education/brochures-and-handbooks/south-american-soybean-futures-at-cme-group); [CME "CBOT Soybeans vs. DCE Soybean Meal and Soybean Oil — Crush Spread"](https://www.cmegroup.com/trading/agricultural/cbot-soybeans-vs-dce-soybean-meal-and-soybean-oil.html)).

## 6. Seasonality

### 6.1 The Northern Hemisphere cycle

U.S. soybean planting typically runs late April to early June, with emergence following within a week of planting. Flowering begins in late June to early July; *pod set* and *pod fill* — the critical yield-determining window — run through August. Harvest begins in mid-September and is effectively complete by early to mid-November across most of the Midwest ([USDA NASS, "National Crop Progress"](https://www.nass.usda.gov/Publications/National_Crop_Progress/); [USDA NASS Crop Progress & Condition charts](https://www.nass.usda.gov/Charts_and_Maps/Crop_Progress_&_Condition/)). The NASS Crop Progress report, released Mondays at 4:00 p.m. ET from April through November, drives the intraweek information cycle during the growing season by providing percent-planted, percent-emerged, percent-blooming, percent-setting-pods, percent-dropping-leaves, percent-harvested, and crop-condition readings state-by-state.

The practitioner term *weather market* refers to the window — typically late June through mid-August in a normal year — when supply outcomes are dominated by near-term Midwest weather and implied volatility is structurally elevated. A CME white paper finds that soybean 30-day implied volatility commonly reaches its annual peak around the July 4 holiday and remains high into pod-fill in August ([CME, "Vol is High by the Fourth of July"](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html); [CME, "Weather Markets in Grain Futures"](https://www.cmegroup.com/education/whitepapers/weather-markets-in-grain-futures.html)). Seasonal price patterns are less reliable than seasonal volatility patterns: the lore that soybean prices "peak on July 4 and bottom in early October" reflects historical averages in years when the U.S. crop comes in on trend, and is broken repeatedly by drought years (1988, 2012) and flood years ([CME, "Understanding Seasonality in Grains"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/understanding-seasonality-in-grains); [FarmProgress, "Volatility in the soybean market"](https://www.farmprogress.com/soybean/volatility-in-the-soybean-market)).

### 6.2 The South American cycle

Brazil and Argentina are mirror-image producers, sowing October to December and harvesting February to June. Mato Grosso, Brazil's largest state-level producer, begins planting after September 15 per the *vazio sanitário* (soybean-free window for Asian rust control) and generally finishes by January 7; Rio Grande do Sul starts October 1. Argentina plants November through January and harvests March to early June ([USDA FAS IPAD Brazil Crop Calendar](https://ipad.fas.usda.gov/rssiws/al/crop_calendar/br.aspx); [USDA FAS IPAD Southern South America Crop Calendar](https://ipad.fas.usda.gov/rssiws/al/crop_calendar/ssa.aspx); [Argus Media, "Brazil sets planting calendar for 2024-25 soybean crop"](https://www.argusmedia.com/en/news-and-insights/latest-market-news/2568730-brazil-sets-planting-calendar-for-2024-25-soybean-crop)). By March, the U.S. "old crop" (the July–September contracts) competes for export share with a fresh Brazilian harvest, which is often the dominant driver of the U.S. export book ([Farmdoc Daily, "Record Soybean Harvest in South America and Favorable Outlook for Exports"](https://farmdocdaily.illinois.edu/2025/03/record-soybean-harvest-in-south-america-and-favorable-outlook-for-exports.html)).

Seasonality also shows up in basis. Harvest basis widens (cash discount deepens) in October–November as elevators fill; it narrows into spring and early summer as inventories draw down and logistics constraints emerge. For meal, basis tightens into summer grilling season and the winter hog/poultry feeding peak; for oil, it reflects refinery throughput and renewable-diesel pull from the U.S. West Coast ([CME, "Learn About Basis: Grains"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/learn-about-basis-grains); [Alberta, "Basis — How cash grain prices are established"](https://www.alberta.ca/basis-how-cash-grain-prices-are-established)).

## 7. Participants and flow

The soybean complex moves through the hands of roughly eight archetypes, each with a distinct time horizon and hedging style:

*Farmers* sell physical beans at harvest or out of on-farm storage; they hedge with futures (short hedge), cash-forward contracts at elevators, put options, or min-price contracts. Horizon: months to a crop year.

*Country elevators* take delivery from farmers, basis-trade against futures (long cash / short futures), and re-sell into the logistics network. They earn the basis appreciation between harvest and spring plus storage rents when the forward curve is in carry ([Wisconsin Extension, "Understanding Basis in Grain Marketing"](https://farms.extension.wisc.edu/articles/understanding-basis-in-grain-marketing/); [StoneX, "Basics of Grain Basis Trading"](https://futures.stonex.com/blog/basics-of-grain-basis-trading-long-the-basis)).

*Terminal elevators* on the Illinois River, the Mississippi, and at Gulf and PNW export terminals aggregate country elevator flow, load barges and vessels, and issue CBOT shipping certificates as hedging instruments.

*Crushers* — led globally by the "ABCD" complex of ADM, Bunge, Cargill, and Louis Dreyfus Company, with CHS and several mid-sized U.S. cooperatives filling out the domestic roster — buy beans, sell meal and oil, and hedge by putting on the crush spread when forward margins are favorable. They typically hedge weeks to months forward and run the physical plant as a call option on crush margin ([Oxfam, "Cereal Secrets: The World's Largest Grain Traders and Global Agriculture"](https://www-cdn.oxfam.org/s3fs-public/file_attachments/rr-cereal-secrets-grain-traders-agriculture-30082012-en_4.pdf); [European Parliament, "The role of commodity traders in shaping agricultural markets"](https://www.europarl.europa.eu/RegData/etudes/STUD/2024/747276/IPOL_STU(2024)747276_EN.pdf)).

*Merchandisers and exporters* (often the same ABCD firms, plus Japanese trading houses, Chinese state buyers, and specialists like Viterra/Glencore Agriculture) move beans internationally and hedge transit-time price risk with futures, options, and basis contracts indexed to CBOT.

*Commercial hedgers* show up in the CFTC's Disaggregated Commitments of Traders (COT) under "Producer/Merchant/Processor/User." This bucket is structurally short futures in aggregate because the cash market is structurally long ([CFTC, "Disaggregated Explanatory Notes"](https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedExplanatoryNotes/index.htm); [CFTC, "Commitments of Traders"](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)).

*Swap dealers* intermediate commodity index exposure: they are long futures against short swap liabilities to pensions, insurers, and retail commodity funds.

*Managed money* (CFTC-registered CTAs, CPOs, and hedge funds) expresses trend, mean-reversion, and macro views on horizons from intraday to multi-quarter. CME data periodically put soybean futures average daily volume above 200,000 contracts with open interest peaks near 900,000 ([CME, "Soybean Overview"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.html); [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)).

*Commodity index investors* hold long-only exposure through benchmarks such as the S&P GSCI and the Bloomberg Commodity Index (BCOM). These benchmarks roll positions forward five to seven times per year, with agricultural roll windows concentrated in the "Goldman roll" (fifth through ninth business day of the month) and a January BCOM/GSCI re-weighting window. Index reconstitutions set the target weights for the following year ([S&P GSCI overview](https://en.wikipedia.org/wiki/S%26P_GSCI); [Bloomberg, "Bloomberg Commodity Index 2026 Target Weights Announced"](https://www.bloomberg.com/company/press/bloomberg-commodity-index-2026-target-weights-announced/); [CFTC staff research, "Commodity Index Investing and Commodity Futures Prices"](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_45_hsrw.pdf)).

*Discretionary specs and options market makers* round out the complex; the latter typically warehouse net short gamma into USDA reports and earn the implied-vol premium.

## 8. Price discovery

The CME/CBOT futures price is the anchor. Cash prices at any elevator, terminal, or export house are quoted as *basis* to a specific futures month (e.g., "−35 November" means 35¢ under the November ZS contract). Changes in basis reflect local supply–demand imbalances: tight basis means buyers need beans now and are bidding up the cash relative to futures; wide basis means grain is plentiful and elevators are discouraging deliveries ([CME, "Learn About Basis"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/learn-about-basis-grains); [Kansas State, "Basis: The Cash/Futures Price Relationship"](https://www.agmanager.info/sites/default/files/MF1003_Basis.pdf)).

The USDA reporting calendar is the scheduled arrival of information. The headline reports are:

**WASDE** (monthly, mid-month, 12:00 p.m. ET). Supply/demand balance sheets for U.S. and world oilseeds, including crush, exports, ending stocks, and mid-point price. The May release is the first to publish new-marketing-year balances; August is the first WASDE to incorporate survey-based new-crop yields ([USDA, "WASDE Report"](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)).

**Crop Production** (monthly, concurrent with WASDE through the growing season). Contains yield and production estimates.

**Crop Progress** (weekly, Mondays 4:00 p.m. ET, April–November). Percent-planted, percent-podding, condition ratings ([USDA NASS, National Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/)).

**Prospective Plantings** (last business day of March, 12:00 p.m. ET). First survey-based read on spring acreage intentions; historically the highest-impact scheduled release of the year ([USDA NASS Publications](https://www.nass.usda.gov/Publications/)).

**Grain Stocks** (quarterly — last business day of January, March, June, September, 11:00 a.m. CT). On-farm and off-farm inventories by state ([USDA NASS Grain Stocks survey page](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Off-Farm_Grain_Stocks/index.php)).

**Acreage** (end of June). Replaces the Prospective Plantings number with actual June survey data.

Research by USDA, CME, and independent academics consistently finds that these releases compress multiple weeks of price-discovery into a single minute; CME's own primer notes WASDE reduces uncertainty in corn and soybean markets around 70% of the time ([CME, "Understanding Major USDA Reports for Grains and Oilseed Markets"](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)). Information propagates across the complex almost instantaneously via the board crush: a bullish bean surprise that the market attributes to tight supply will tend to lift beans more than products (reverse crush squeezes processors); a bullish surprise driven by strong crush demand will widen the crush spread as products outrun beans.

**A note on forward-curve interpretation.** Two traditions explain grain forward curves. The *theory of storage* (Kaldor 1939; Working 1948, 1949; Brennan 1958) says the futures price equals the spot plus storage cost and interest, minus a *convenience yield* that reflects the benefit of holding physical inventory near stockouts. The *Hicks–Keynesian normal backwardation* tradition instead attributes forward discounts to a risk premium extracted by speculators from hedgers. Empirically both effects appear, and the modern consensus is a hybrid: storage-arbitrage pins the curve shape within a corridor, while risk premia determine where in that corridor the curve sits ([Kaldor/Working theory summary](https://en.wikipedia.org/wiki/Theory_of_storage); [NBER Working Paper 13249, Gorton and Rouwenhorst, "The Fundamentals of Commodity Futures Returns"](https://www.nber.org/system/files/working_papers/w13249/w13249.pdf); [Lautier summary notes](https://www.pims.math.ca/files/Convenienceyield_Lautier.pdf)). Practitioners often speak of backwardation as "tight stocks / high convenience yield," which is a storage-theory reading; academic papers that model the same phenomenon as a time-varying risk premium would disagree with that causal story even while fitting the same observed curve. This primer flags the tension and does not pick a side.

A second disagreement — less theoretical, more institutional — is the 2005–2010 non-convergence episode, in which CBOT wheat especially but also corn and soybeans settled at expiry with futures stubbornly above cash delivery value. Irwin et al. (2009) argue the cause was a structurally fixed storage rate on shipping certificates that was below the value of physical storage during a period of large inventories, effectively making the delivery instrument a cheap call on future storage. The exchange's response was a variable storage rate regime (imposed for wheat, storage-rate increases for soybeans and corn) that has largely restored convergence ([Irwin et al. (2009), SSRN 1392380](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1392380); [USDA ERS, "Recent Convergence Performance of Futures and Cash Prices"](https://ers.usda.gov/sites/default/files/_laserfiche/outlooks/36693/41742_fds-13l-01.pdf); [CFTC Convergence Subcommittee Report](https://www.cftc.gov/sites/default/files/idc/groups/public/@aboutcftc/documents/file/reportofthesubcommitteeonconve.pdf)). Some academic commentary emphasized speculative/index-fund distortion instead of storage mechanics; Irwin's view, now broadly accepted, pointed back to the contract design. Practitioner lore that "index funds broke CBOT wheat" is therefore a claim one should source carefully.

## 9. Options on soybean futures

CBOT soybean options are American-exercise options on ZS futures, with the standard monthly series listed against the corresponding futures month. The underlying is one 5,000-bushel ZS contract; premia are quoted in 1/8¢/bu increments ($6.25 per contract). Strikes are listed at 10¢ intervals near the money and 20¢ intervals further out, with new strikes added as the futures moves ([CME Soybean Options](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.contractSpecs.options.html)).

Beyond the standard options, CME lists short-dated new-crop (SDNC) options, which settle against the new-crop (November) future even when they expire in spring or early summer months, and a family of weekly options with Friday (and now daily) expirations. The SDNC product exists because hedgers want to buy weather insurance against the November contract without having to carry a full November option, which embeds months of pre-harvest carry the hedger may not need ([CME, "Agricultural Short-Term Options"](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)). Liquidity is concentrated in the front three monthly series and the near-the-money strikes; the July, November, and January contracts anchor the vol surface.

Common practitioner structures include: (i) *weather strangles* on the July or August contract bought in May/June to take a long-vol position into pod-fill; (ii) *new-crop November put spreads* bought by farmers in spring to lock in a floor while retaining upside; (iii) *crush-lock structures* using ZM calls and ZL calls together with ZS puts to hedge processing margins; and (iv) *calendar spreads* buying November vol and selling August vol in early spring to isolate U.S. growing-season risk. CME's CVOL index provides a standardized 30-day implied-vol read on ZS for surface-watching ([CME Soybean Overview](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.html)). The skew in soybeans tends to be *call-side* in the pre-harvest window (weather risk is mostly a supply shock, which is bullish) and can flip *put-side* once the crop is made.

## 10. Glossary of core terms

**ABCD** — The four dominant global grain traders: ADM, Bunge, Cargill, Louis Dreyfus Company.

**Basis** — Local cash price minus the nearby futures price. Positive basis means cash is over futures; negative means under. See [CME "Learn About Basis"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/learn-about-basis-grains).

**Board crush** — The futures-market soybean crush, constructed from the ZS, ZM, and ZL contracts.

**Bushel** — Volumetric grain measure standardized by weight: 60 lb for soybeans, 56 lb for corn, 60 lb for wheat.

**Carry (or contango)** — Forward price above spot; a storable commodity normally exhibits positive carry when stocks are plentiful.

**Cash-forward contract** — Over-the-counter agreement between farmer and elevator to deliver a specified quantity at a specified cash price at a specified date.

**CBOT** — Chicago Board of Trade; the exchange (now part of CME Group) where soybean complex futures trade.

**Convenience yield** — Benefit from holding physical inventory; in storage theory, the residual that equates the futures-price identity F = Se^((r+u−y)T).

**Convergence** — Forced equality between the futures price and the cash delivery value as the contract approaches expiry.

**Crush margin (GPM)** — Gross processing margin: cash revenue from meal and oil minus cash cost of beans and variable crushing cost.

**Deliverable grade** — The quality standard at which soybeans can be delivered against a futures contract without discount (No. 2 yellow at par).

**Disaggregated COT** — The CFTC Commitments of Traders report format that splits reportables into Producer/Merchant/Processor/User, Swap Dealers, Managed Money, and Other Reportables.

**Gross Processing Margin** — See *Crush margin*.

**Hedge** — Futures or options position taken to offset price risk in a physical inventory or planned transaction.

**Illinois River delivery system** — The set of shipping-certificate-issuing facilities along the Illinois Waterway on which the ZS contract is delivered (Chicago/Burns Harbor par; Lockport–Seneca, Ottawa–Chillicothe, Peoria–Pekin premiums).

**Managed money** — CFTC category for registered CTAs, CPOs, and hedge funds.

**New crop / old crop** — For U.S. soybeans, November is conventionally "new crop" and July the "old crop" bellwether.

**Normal backwardation** — Keynes/Hicks hypothesis that futures trade below expected spot because hedgers pay speculators a risk premium to bear price risk.

**Oilshare** — Share of the combined product value of meal and oil accounted for by oil: (ZL value) / (ZL value + ZM value).

**Open outcry** — The pit-trading voice-and-hand-signal method retired at CBOT in 2015 for grains and in 2021 across most CME contracts.

**Position limit** — CFTC-enforced cap on speculative net positions; spot-month is tighter than non-spot-month.

**Prospective Plantings** — USDA NASS March survey of farmer planting intentions.

**Reverse crush** — Long beans, short products; the opposite of what a physical crusher's margin looks like.

**Shipping certificate** — Electronic delivery instrument issued by a regular CBOT firm that promises loading of grain on notice. Delivery vehicle for ZS, ZM, and ZL futures.

**Short hedge** — Producer or inventory holder selling futures against physical length.

**Spread** — Price relationship between two contracts: calendar (July–November), inter-commodity (ZS/ZC), or inter-market (CBOT–DCE).

**Stocks-to-use ratio** — Ending stocks divided by annual use; a compact measure of tightness.

**Theory of storage** — Kaldor/Working/Brennan framework that explains forward curves via storage costs, interest, and convenience yield.

**Variable storage rate (VSR)** — Mechanism that adjusts storage fees on delivery certificates in response to spread behavior; implemented for CBOT wheat in 2010 to improve convergence.

**Vega** — Option-price sensitivity to a 1% change in implied volatility.

**WASDE** — USDA's World Agricultural Supply and Demand Estimates, released monthly.

**Weather market** — The summer window (roughly mid-June to mid-August for U.S. soybeans) when forecasted Midwest weather dominates price behavior and implied vol is structurally elevated.

## Key takeaways

- The soybean complex is three interlocking contracts (ZS, ZM, ZL), held together by the physical crush relationship and the exchange-listed board-crush spread at the 10:11:9 ratio.
- ZS is a 5,000-bushel physically-delivered contract with a ¼¢ tick ($12.50) and listed months Jan/Mar/May/Jul/Aug/Sep/Nov; ZM is 100 short tons; ZL is 60,000 lb. All three deliver via electronic shipping certificates.
- Daily price limits are variable, reset every six months, with an interlock that expands limits across the complex when any component locks.
- CBOT open outcry for grains ended in 2015; CME closed most remaining pits in 2021. Soybean complex trading is now effectively 100% electronic on CME Globex.
- Price discovery happens in futures and propagates into cash via basis; scheduled USDA reports (WASDE, Crop Progress, Grain Stocks, Prospective Plantings, Acreage, Crop Production) are the dominant information events.
- Seasonality is bimodal: U.S. plants April–June, pollinates/pod-fills July–August, harvests September–November; South America plants October–December, harvests February–May.
- Implied vol is structurally highest into U.S. pod-fill (July–August) and into the March Prospective Plantings release; short-dated new-crop options exist to let hedgers buy that vol cheaply.
- The "weather market" is real as a volatility regime; seasonal directional price patterns are less reliable and frequently broken by drought or flood years.
- The 2005–2010 non-convergence episode prompted variable storage rates and higher fixed storage rates on shipping certificates; modern convergence is generally well-behaved.
- The forward curve can be read through a storage/convenience-yield lens or a risk-premium (normal backwardation) lens; both get used in practice and the literature has not chosen definitively between them.
- The ABCD processors dominate physical flow globally, with U.S. crush now at record 2.49–2.61 billion bushels for MY2025/26 driven by biofuel demand.
- Position limits, COT reports, and the delivery mechanism constrain how big any one actor can get, and give the market a weekly lens on positioning.

## References

- [CME Group, "Soybean Futures Contract Specs"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.contractSpecs.html)
- [CME Group, "Soybean Meal Futures Contract Specs"](https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-meal_contract_specifications.html)
- [CME Group, "Soybean Oil Futures Contract Specs"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean-oil.contractSpecs.html)
- [CBOT Rulebook Chapter 11 — Soybean Futures](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)
- [CBOT Rulebook Chapter 12 — Soybean Oil Futures](https://www.cmegroup.com/rulebook/CBOT/II/12/12.pdf)
- [CBOT Rulebook Chapter 13 — Soybean Meal Futures](https://www.cmegroup.com/rulebook/CBOT/II/13/13.pdf)
- [CBOT Rulebook Chapter 7 — Delivery Facilities and Procedures](https://www.cmegroup.com/rulebook/CBOT/I/7.pdf)
- [CME Group, Soybean Crush Reference Guide (PDF)](https://www.cmegroup.com/education/files/soybean-crush-reference-guide.pdf)
- [CME Group, "Understanding Soybean Crush"](https://www.cmegroup.com/education/courses/introduction-to-agriculture/grains-oilseeds/understanding-soybean-crush)
- [CME Group, "Soybean Crush Spreads"](https://www.cmegroup.com/trading/agricultural/grain-and-oilseed/soybean-crush-spreads.html)
- [CME Group, "Price Limits: Ags, Energy, Metals, Equity Index"](https://www.cmegroup.com/trading/price-limits.html)
- [CME Group, "Understanding Price Limits and Circuit Breakers"](https://www.cmegroup.com/education/articles-and-reports/understanding-price-limits-and-circuit-breakers)
- [CME Group investor relations, "Approval for Changes to Daily Price Limits in CBOT Agricultural Futures and Options"](https://investor.cmegroup.com/news-releases/news-release-details/cme-group-receives-approval-changes-daily-price-limits-cbot)
- [CME Group press release, May 4, 2021, closing open-outcry pits](https://www.cmegroup.com/media-room/press-releases/2021/5/04/cme_group_to_permanentlyclosemostopenoutcrytradingpitseurodollar.html)
- [CME Group, "Weather Markets in Grain Futures"](https://www.cmegroup.com/education/whitepapers/weather-markets-in-grain-futures.html)
- [CME Group, "Vol is High by the Fourth of July"](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html)
- [CME Group, "Understanding Seasonality in Grains"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/understanding-seasonality-in-grains)
- [CME Group, "Learn About Basis: Grains"](https://www.cmegroup.com/education/courses/introduction-to-grains-and-oilseeds/learn-about-basis-grains)
- [CME Group, "Agricultural Short-Term Options"](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)
- [CME Group, "Understanding Major USDA Reports for Grains and Oilseed Markets"](https://www.cmegroup.com/articles/2024/understanding-major-usda-reports.html)
- [CME Group, "South American Soybean Futures at CME Group"](https://www.cmegroup.com/education/brochures-and-handbooks/south-american-soybean-futures-at-cme-group)
- [CME Group, "An Introduction to Soybean Oilshare Futures and Options"](https://www.cmegroup.com/articles/2025/an-introduction-to-soybean-oilshare-futures-and-options.html)
- [CME Group, "CBOT Soybean Oil Futures — Delivery Mechanism"](https://www.cmegroup.com/articles/2021/cbot-soybean-oil-futures-delivery-mechanism.html)
- [CME Group, "Soybean Overview"](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.html)
- [USDA NASS, National Crop Progress publications](https://www.nass.usda.gov/Publications/National_Crop_Progress/)
- [USDA NASS, Charts and Maps — Crop Progress & Condition](https://www.nass.usda.gov/Charts_and_Maps/Crop_Progress_&_Condition/)
- [USDA NASS, Grain Stocks survey](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Off-Farm_Grain_Stocks/index.php)
- [USDA NASS Publications index](https://www.nass.usda.gov/Publications/)
- [USDA, "WASDE Report"](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)
- [USDA ERS, "Soybeans and Oil Crops"](https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops)
- [USDA ERS, "Oil Crops Sector at a Glance"](https://www.ers.usda.gov/topics/crops/soybeans-and-oil-crops/oil-crops-sector-at-a-glance)
- [USDA ERS, "Recent Convergence Performance of Futures and Cash Prices"](https://ers.usda.gov/sites/default/files/_laserfiche/outlooks/36693/41742_fds-13l-01.pdf)
- [USDA FAS IPAD, Brazil Crop Calendar](https://ipad.fas.usda.gov/rssiws/al/crop_calendar/br.aspx)
- [USDA FAS IPAD, Southern South America Crop Calendar](https://ipad.fas.usda.gov/rssiws/al/crop_calendar/ssa.aspx)
- [CFTC, Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [CFTC, Disaggregated COT Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedExplanatoryNotes/index.htm)
- [CFTC, Speculative Limits overview](https://www.cftc.gov/IndustryOversight/MarketSurveillance/SpeculativeLimits/speculativelimits.html)
- [CFTC, Report of the Subcommittee on Convergence in Agricultural Markets](https://www.cftc.gov/sites/default/files/idc/groups/public/@aboutcftc/documents/file/reportofthesubcommitteeonconve.pdf)
- [CFTC staff research, "Commodity Index Investing and Commodity Futures Prices"](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_45_hsrw.pdf)
- [Irwin, Garcia, Good & Kunda (2009), "Poor Convergence Performance of CBOT Corn, Soybean and Wheat Futures Contracts: Causes and Solutions," SSRN 1392380](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1392380)
- [Gorton & Rouwenhorst (2007), "The Fundamentals of Commodity Futures Returns," NBER Working Paper 13249](https://www.nber.org/system/files/working_papers/w13249/w13249.pdf)
- [Lautier, "The Theory of Storage and the Convenience Yield" (PIMS summer-school notes)](https://www.pims.math.ca/files/Convenienceyield_Lautier.pdf)
- [Theory of Storage overview](https://en.wikipedia.org/wiki/Theory_of_storage)
- [Farmdoc Daily, "Record Soybean Harvest in South America and Favorable Outlook for Exports"](https://farmdocdaily.illinois.edu/2025/03/record-soybean-harvest-in-south-america-and-favorable-outlook-for-exports.html)
- [FarmProgress, "Neutral price ratio guides 2026 crop choices"](https://www.farmprogress.com/crops/soybean-to-corn-price-ratio-offers-neutral-signal-for-2026-planting-decisions-across-midwest-farms)
- [FarmProgress, "High crush margins drive rapid expansion"](https://www.farmprogress.com/soybean/high-crush-margins-drive-rapid-expansion)
- [FarmProgress, "Volatility in the soybean market"](https://www.farmprogress.com/soybean/volatility-in-the-soybean-market)
- [Michigan State Extension, "Understanding the corn-soybean ratio"](https://www.canr.msu.edu/news/the-corn-soybean-ratio-and-its-potential-impact-on-farm-profits)
- [Iowa State Ag Decision Maker, "Corn and Soybean Price Basis"](https://www.extension.iastate.edu/agdm/crops/html/a2-40.html)
- [Wisconsin Extension, "Understanding Basis in Grain Marketing"](https://farms.extension.wisc.edu/articles/understanding-basis-in-grain-marketing/)
- [Alberta government, "Basis — How cash grain prices are established"](https://www.alberta.ca/basis-how-cash-grain-prices-are-established)
- [Kansas State, "Basis: The Cash/Futures Price Relationship" (PDF)](https://www.agmanager.info/sites/default/files/MF1003_Basis.pdf)
- [StoneX, "Basics of Grain Basis Trading"](https://futures.stonex.com/blog/basics-of-grain-basis-trading-long-the-basis)
- [U.S. Soy, "CBOT's Delivery Process Helps Get U.S. Soy to Buyers"](https://ussoy.org/cbots-delivery-process-helps-get-u-s-soy-to-buyers/)
- [FIA MarketVoice, "End of an Era"](https://www.fia.org/marketvoice/articles/end-era)
- [Oxfam, "Cereal Secrets: The World's Largest Grain Traders and Global Agriculture"](https://www-cdn.oxfam.org/s3fs-public/file_attachments/rr-cereal-secrets-grain-traders-agriculture-30082012-en_4.pdf)
- [European Parliament, "The role of commodity traders in shaping agricultural markets"](https://www.europarl.europa.eu/RegData/etudes/STUD/2024/747276/IPOL_STU(2024)747276_EN.pdf)
- [S&P GSCI overview](https://en.wikipedia.org/wiki/S%26P_GSCI)
- [Bloomberg, "Bloomberg Commodity Index 2026 Target Weights Announced"](https://www.bloomberg.com/company/press/bloomberg-commodity-index-2026-target-weights-announced/)
- [Argus Media, "Brazil sets planting calendar for 2024-25 soybean crop"](https://www.argusmedia.com/en/news-and-insights/latest-market-news/2568730-brazil-sets-planting-calendar-for-2024-25-soybean-crop)
