# Audit C — Phase 03: Tooling and Infrastructure (Claim Index)

## 1. Source artifact summary

`research/phase_03_tooling_and_infrastructure.md` inventories the technology
stack used by serious soybean-complex traders in 2026. It walks through
exchange-direct and consolidated market-data vendors (CME MDP 3.0, Exegy/Vela,
Databento, Bloomberg, LSEG Workspace, CQG, DTN ProphetX, Barchart, ICE
Connect), execution platforms and routing models (Trading Technologies, CQG,
Rithmic, DMA / sponsored access / broker-hosted, CME iLink, Aurora colo),
options analytics (Cboe Hanweck, LiveVol, OptionsCity), alt-data providers
(Planet, Maxar, Descartes Labs, Orbital Insight, Gro Intelligence, Kpler,
Vortexa, USDA AMS GTR), weather sources (ECMWF IFS, NOAA GFS, ERA5, NASA
POWER, DTN Weather, Maxar WeatherDesk, Atmospheric G2, StormGeo), scheduled
fundamentals pipelines (USDA WASDE / NASS / FAS, CONAB, BCBA / BCR, China
GACC, Sinograin), sell-side research (StoneX, Hightower, AgResource, Pro
Farmer, Allendale), and backtesting / data-distribution stacks (kdb+, OneTick,
QuantHouse, Deltix, ArcticDB, polars / DuckDB / pandas, Backtrader / Zipline /
VectorBT / QuantConnect Lean, Databento, dxFeed, Nasdaq Data Link, FRED,
CFTC COT). It closes with cost-tier exemplars (institutional prop, small
specialist shop, retail quant) and a list of structural gaps. The document
explicitly disclaims that pricing figures are illustrative and should be
re-confirmed against current vendor terms.

## 2. Claims table

Topic-tag vocabulary: `pricing-model`, `density`, `data-ingest`, `contract`,
`hedging`, `inventory`, `oms`, `backtest`, `strategy`, `observability`,
`market-structure`, `tooling`. Certainty preserves source flags; where the
source asserts a fact without hedging, it is `established`. Where the source
uses qualifiers ("regarded as", "treated as", "reputed", "trade view") I tag
`practitioner-lore`. Where the source frames an open or contested area
("debated", "active frontier", "remain rare"), I tag `debated`. Each claim is
written to translate "tool X has property Y" into a code-actionable form:
either the system uses X to obtain Y, or it must independently provide Y.

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C03-01 | The CBOT grain/oilseed contracts disseminated through CME MDP 3.0 are ZS, ZM, ZL, ZC, ZW; any soybean-complex feed handler must support these symbols (or upstream equivalents). | §1.1 ¶1 | established | data-ingest; market-structure |
| C03-02 | CME MDP 3.0 is a dual-feed UDP multicast service encoded with Simple Binary Encoding against the FIX 5.0 SP2 schema; any direct ingest must implement SBE/FIX 5.0 SP2 decoding or rely on a vendor that does. | §1.1 ¶1 | established | data-ingest; market-structure; tooling |
| C03-03 | MDP 3.0 carries bid, ask, trade, security-definition, and statistics messages and supports both Market By Price (MBP) and Market By Order (MBO) book views; downstream books must distinguish MBP vs. MBO state machines. | §1.1 ¶1 | established | data-ingest; market-structure |
| C03-04 | MDP Premium layers Market By Order Full Depth on top of MDP 3.0; full-depth book reconstruction requires MDP Premium (or equivalent vendor-rebuilt depth). | §1.1 ¶1 | established | data-ingest; market-structure |
| C03-05 | Raw MDP consumption requires Aurora-data-center colocation or cross-connect, a licensed feed handler, and a CME distributor license; absence of any of these forces use of an authorized redistributor. | §1.1 ¶1 | established | data-ingest; market-structure; contract |
| C03-06 | MDP update cadence is event-driven microseconds at institutional 5–6 figure/month cost with effectively zero retail access; any low-cost path must accept higher-latency / consolidated alternatives. | §1.1 ¶1 | established | pricing-model; data-ingest |
| C03-07 | Exegy SMDS normalizes 300+ venues into one API and ships as managed software or hardware-accelerated appliances (nxFeed, XTP) at nanosecond latency; using SMDS substitutes an FPGA team in-house. | §1.1 ¶2 | established | data-ingest; tooling |
| C03-08 | Databento resells CME MDP 3.0 as cloud-native API GLBX.MDP3 with pay-as-you-go pricing down to MBO granularity, live and historical, across the full grain complex; this is the default route for smaller quant shops needing exchange-grade fidelity. | §1.1 ¶3 | established | data-ingest; pricing-model; tooling |
| C03-09 | Bloomberg Terminal 2026 list pricing is ~$31,980/year single-seat and $28,320/seat multi-seat with two-year commitment; budget models must reflect this seat math. | §1.2 ¶1 | established (source flags as illustrative) | pricing-model; tooling |
| C03-10 | The Bloomberg Agriculture Subindex is treated as a de facto commodity-overlay benchmark; any benchmarking module either references it or must define an explicit replacement. | §1.2 ¶1 | practitioner-lore | strategy; market-structure |
| C03-11 | LSEG Workspace named-user pricing sits at $1,500–$3,000/user/month plus $500–$2,000/user/month data add-ons; cost rollups must allow base plus add-on tiering. | §1.2 ¶2 | established (illustrative) | pricing-model; tooling |
| C03-12 | CQG aggregates 85+ data sources across 45 exchanges and provides DOMTrader, Spreadsheet Trader, and spread/options workflows; an in-house equivalent must replicate spread/options laddering or rely on CQG. | §1.2 ¶3 | established | data-ingest; oms; tooling |
| C03-13 | CQG institutional workstation runs low-four-figures/month; CQG QTrader (FCM-rebadged retail) runs $50–$100/month. | §1.2 ¶3 | established (illustrative) | pricing-model; tooling |
| C03-14 | DTN ProphetX combines CBOT futures, 4,200+ North American daily cash grain bids, 20-year cash history, DTN meteorologist commentary, and an Excel add-in; a basis-driven system either subscribes to ProphetX or must collect ~4k cash bid sources independently. | §1.2 ¶4 | established | data-ingest; tooling; inventory |
| C03-15 | DTN ProphetX cost: prosumer mid-three to institutional low-four figures/month. | §1.2 ¶4 | established (illustrative) | pricing-model; tooling |
| C03-16 | Barchart cmdty publishes local-basis indices, continuous and EOD county-level cash grain pricing back to 2014, crop-production forecasts, and the cmdty National Soybean Basis Index; basis-aware code can use ZSBAUS.CM or rebuild a comparable index from raw cash bids. | §1.2 ¶5 | established | data-ingest; pricing-model; tooling; inventory |
| C03-17 | Barchart cost is low-3 to low-4 figure/month with a permissive free tier; Barchart is the most retail-accessible serious vendor. | §1.2 ¶5 | established (illustrative) | pricing-model; tooling |
| C03-18 | ICE Connect ag package covers meals, grains, wheat, oilseeds, and vegetable oils and absorbs S&P Global Commodity Insights (ex-Platts) benchmarks (energy-tilted); any cross-asset desk replication needs Platts/CI benchmark coverage. | §1.2 ¶6 | established | data-ingest; tooling |
| C03-19 | Cboe Hanweck produces real-time implied vols and Greeks across equity/ETF/index/futures options via the Volera engine, but grain/oilseed depth is limited versus equities; an in-house grain-options vol surface cannot rely on Hanweck alone. | §1.3 ¶1 | established | tooling; observability |
| C03-20 | Cboe LiveVol is equities-native with time-and-sales back to 2011 and ~$380/month for LiveVol Pro; it is not a CBOT-grain tool in practice. | §1.3 ¶1 | established (illustrative) | pricing-model; tooling |
| C03-21 | OptionsCity was rolled into Trading Technologies in 2018; serious grain-options desks now get analytics from TT or build in-house — Pricing Partners' MX serves OTC commodity derivatives more than CBOT futures-options. | §1.3 ¶1 | established | tooling; market-structure |
| C03-22 | Trading Technologies includes MD Trader ladder (canonical grain execution UI), Autospreader (board-crush, legged execution), ADL algorithmic development, TT Order Book (OMS), TT Score (surveillance), and TT Fundamental Analytics; an in-house OMS must replicate these surfaces or integrate TT. | §2 ¶1 | established | oms; tooling; observability |
| C03-23 | TT cost is low-to-mid three figures per user per month plus exchange data pass-throughs. | §2 ¶1 | established (illustrative) | pricing-model; oms; tooling |
| C03-24 | CQG Trader/Desktop/One overlaps with TT in execution, with stronger reputation among Chicago-grain floor descendants and chart-driven discretionary spread traders; charting fidelity is a decisive advantage. | §2 ¶2 | practitioner-lore | oms; tooling; market-structure |
| C03-25 | Rithmic is broker- and FCM-neutral, colocated in Aurora, engineered for sub-100ms routing, exposed via R|Trader Pro with full CBOT/CME/COMEX/NYMEX/MGEX coverage. | §2 ¶3 | established | oms; market-structure; tooling |
| C03-26 | Rithmic user cost is $20–$100/month via the FCM. | §2 ¶3 | established (illustrative) | pricing-model; oms |
| C03-27 | TT + CQG dominate the multi-user merchandiser/prop tier; Rithmic + broker front-ends dominate the lower tier — execution-platform support assumptions should match this segmentation. | §2 ¶4 | practitioner-lore | market-structure; oms |
| C03-28 | Under DMA the customer uses the member's infrastructure but routes orders directly, and the member retains pre-trade-risk responsibility; a DMA path must surface member pre-trade risk hooks. | §2 ¶5 | established | market-structure; oms; contract |
| C03-29 | Under sponsored access the customer uses the member's MPID but bypasses the member's infrastructure; "naked" sponsored access is now universally pre-trade-risk filtered per SEC 15c3-5 and analogs. | §2 ¶5 | established | market-structure; oms; contract |
| C03-30 | Broker-hosted routing passes orders through the broker's OMS/risk layer — slower but with fewer operational surprises; an OMS design choice between DMA / sponsored / broker-hosted is a latency-vs-risk-ownership trade-off. | §2 ¶5 | established | oms; market-structure |
| C03-31 | CME iLink is the Globex order-entry protocol with MSGW (dedicated) and CGW (multi-segment) gateways; an order entry path must select MSGW vs. CGW. | §2 ¶6 | established | oms; market-structure; data-ingest |
| C03-32 | CME Globex Hub — Aurora provides Equinix-adjacent colocation access; deterministic latency requires Aurora-resident or cross-connected presence. | §2 ¶6 | established | market-structure; oms |
| C03-33 | Proximity-hosted access via Beeks or Equinix NY5 is the norm for shops too small for own rack space; cost models should permit a managed-colo line item. | §2 ¶6 | established | market-structure; oms |
| C03-34 | Planet Labs operates the largest EO cubesat constellation, sells near-daily 3.7-m imagery globally via API/web/GIS, with farm-scale integrations citing ~$1.25/acre/year as a retail reference. | §3.1 ¶1 | established (illustrative) | data-ingest; pricing-model |
| C03-35 | Maxar Intelligence supplies sub-meter imagery (defense-weighted) used in WeatherDesk for ag yield verification and logistics checks. | §3.1 ¶2 | established | data-ingest |
| C03-36 | Descartes Labs U.S. corn/soy yield-forecast models ingest MODIS/VIIRS/Landsat/Sentinel plus weather and crop progress; its 11-year backtest reportedly beats USDA mid-cycle estimates at every growing-season step for U.S. corn. | §3.1 ¶3 | established (vendor-reported backtest) | backtest; data-ingest; strategy |
| C03-37 | Descartes Labs paid subscribers receive every-two-day forecast updates versus public weekly cadence — a deliberate information-asymmetry feature. | §3.1 ¶3 | established | data-ingest; pricing-model |
| C03-38 | Orbital Insight was acquired by Privateer Space (Wozniak) in May 2024 after a commercial rough patch — vendor continuity for OI signals is unsettled. | §3.1 ¶4 | established | market-structure |
| C03-39 | Gro Intelligence aggregates 170,000+ datasets and runs a county-level U.S. Soybean Yield Forecast Model; mid-2024 funding difficulties pushed many practitioners to rebuild Gro-style pipelines in-house from public ERA5 / NDVI / USDA inputs. | §3.1 ¶5 | established (vendor risk flagged) | data-ingest; backtest; market-structure |
| C03-40 | Free indices MODIS MOD13, Sentinel-2 NDVI, ESA Soil Moisture CCI sit beneath commercial products; Copernicus Land Monitoring and EarthDaily add validated layers; research practitioners mostly consume raw Sentinel Hub or Google Earth Engine. | §3.1 ¶6 | established | data-ingest; tooling |
| C03-41 | Kpler tracks 350,000+ vessels daily over a proprietary 13,000+ AIS-receiver network with explicit grains/oilseeds coverage (corn, wheat, barley, soybean, sunflower, rapeseed, meals) and vegetable oils. | §3.2 ¶1 | established | data-ingest; tooling |
| C03-42 | For soybeans Kpler's value concentrates in Brazilian ports (Santos, Paranaguá), the U.S. Gulf, and Chinese discharge terminals, tracking 120+ million tons/year of seaborne flow weeks before customs publication. | §3.2 ¶1 | established | data-ingest; market-structure |
| C03-43 | Vortexa tracks $3.4 trillion of waterborne trade annually (crude/products/LNG-strongest); its freight, fleet-utilization, and port-congestion metrics read across to soy via Panama Canal, dry-bulk rates, and Brazilian port queues. | §3.2 ¶2 | established | data-ingest |
| C03-44 | The USDA AMS Grain Transportation Report publishes weekly Illinois River barge rates, Lower Mississippi lock-by-lock tonnage, corn-belt-to-Gulf/PNW rail tariffs, and ocean freight benchmarks, with CSV-downloadable datasets — a free baseline for U.S. logistics. | §3.3 ¶1 | established | data-ingest |
| C03-45 | Higher-frequency commercial AIS (MarineTraffic, now Kpler-owned) replaces the GTR's weekly lock counts with near-real-time barge positions; high-frequency river logistics requires commercial AIS. | §3.3 ¶1 | established | data-ingest; market-structure |
| C03-46 | ECMWF IFS is generally considered the most accurate global medium-range NWP model, with NOAA GFS slightly behind. | §4 ¶1 | established | data-ingest |
| C03-47 | ECMWF IFS runs twice daily at ~9 km resolution with 15-day ensembles and SEAS5 sub-seasonal/seasonal; ECMWF publishes a free CC-BY-4.0 open-data subset — license-compatible code can rely on the open subset. | §4 ¶1 | established | data-ingest; contract |
| C03-48 | ERA5 / ERA5-Land are the gold-standard hourly reanalyses back to 1940 and the dominant input for backtested weather–yield models. | §4 ¶1 | established | data-ingest; backtest |
| C03-49 | NOAA GFS / NAM / HRRR and NASA POWER fill the free U.S./global NWP layer at varying resolutions and cadences. | §4 ¶1 | established | data-ingest |
| C03-50 | DTN Weather (consolidated from Telvent DTN, MDA Information Systems, MDA Weather Services) is the most entrenched U.S. ag-desk weather provider, with meteorologist commentary feeding ProphetX. | §4 ¶2 | established | data-ingest; tooling |
| C03-51 | Atmospheric G2 (merged MDA / WSI / WDT) is the weather-risk analytics standard for energy, commodity, and weather-derivatives work. | §4 ¶2 | practitioner-lore | data-ingest |
| C03-52 | Commercial weather pricing is institutional low-four to mid-five figures per month. | §4 ¶2 | established (illustrative) | pricing-model |
| C03-53 | WASDE releases monthly at 12:00 PM ET around the 10th–12th (2026 spans Jan 12 through Dec 10) and sets the soybean balance sheet that anchors price; any event-clock or release-window logic must encode this schedule. | §5 ¶1 | established | data-ingest; market-structure; contract |
| C03-54 | NASS Crop Progress runs weekly at 4 PM ET Mondays April through November, with county-level gridded layers; ingestion windows must align to this cadence. | §5 ¶1 | established | data-ingest |
| C03-55 | FAS Weekly Export Sales publishes Thursdays at 8:30 AM ET on a Friday-through-Thursday reporting window and is highly market-moving; pre-release risk gates should reference this slot. | §5 ¶1 | established | data-ingest; market-structure; hedging |
| C03-56 | USDA data is free; machine consumption is via NASS Quick Stats API, FAS GAIN attaché reports, and FOIA bulk downloads — three distinct ingest paths. | §5 ¶1 | established | data-ingest |
| C03-57 | Brazil's CONAB publishes monthly state-level S&D as the South-American parallel to WASDE — a Brazil-coverage system either ingests CONAB or accepts a one-month staleness gap. | §5 ¶2 | established | data-ingest |
| C03-58 | Argentina's BCBA and BCR (Rosario) publish weekly crop monitors and daily Rosario/Paraná cash quotations; the Rosario region handles 90%+ of Argentine soy exports. | §5 ¶2 | established | data-ingest; market-structure; inventory |
| C03-59 | China's GACC publishes monthly import volumes/values by HS code; 2025 soybean imports hit 111.8 million tons. | §5 ¶3 | established | data-ingest; market-structure |
| C03-60 | GACC enforces export-origin registration, demonstrated in the 2018 and 2025 shipment suspensions — code modelling shipment risk must allow for origin-registration revocation events. | §5 ¶3 | established | contract; market-structure |
| C03-61 | Sinograin state-reserve auction disclosures are episodic and translated via USDA FAS attachés or specialist consultancies (JCI, Sitonia); a Chinese-reserve view must accept lagged, non-machine-readable inputs. | §5 ¶3 | practitioner-lore | data-ingest; market-structure |
| C03-62 | StoneX U.S. bean-yield surveys are treated as a parallel read on NASS — strategy code may reference StoneX as an independent prior. | §6 ¶1 | practitioner-lore | data-ingest; strategy |
| C03-63 | Hightower Report produces twice-daily Grain & Livestock Commentary at 8:15 AM and 3:45 PM CT plus daily Tech Summaries — fixed publishing slots if scraped/integrated. | §6 ¶2 | established | data-ingest |
| C03-64 | Pro Farmer's August crop tour final yield estimate is the primary private-sector precursor to the August/September WASDE — strategy and risk windows around WASDE should account for the prior crop-tour print. | §6 ¶2 | practitioner-lore | data-ingest; market-structure; strategy |
| C03-65 | Allendale issues its Advisory Report four times daily with technical, fundamental, and COT commentary. | §6 ¶2 | established | data-ingest |
| C03-66 | Sell-side prosumer pricing is $500–$3,000/year for Hightower, Allendale, Pro Farmer, AgResource; StoneX Market Intelligence is bundled with FCM relationships. | §6 ¶3 | established (illustrative) | pricing-model |
| C03-67 | kdb+/q (KX Systems) is the canonical HFT tick store — columnar in-memory time-series DB with vector language q — used by tier-one banks, HFT MMs, and systematic hedge funds; grain-futures use is niche but present in option market-making shops. | §7.1 ¶1 | established | backtest; tooling |
| C03-68 | kdb+ cost is institutional mid-six-figure licensing — small-shop budgets cannot assume kdb access. | §7.1 ¶1 | established (illustrative) | pricing-model; tooling |
| C03-69 | OneTick (OneMarketData) is the second-most-common institutional tick DB and reputed to be easier to integrate than kdb. | §7.1 ¶1 | practitioner-lore | backtest; tooling |
| C03-70 | QuantHouse HOD provides 15+ years of normalized tick history across 145+ exchanges including commodities. | §7.1 ¶1 | established | backtest; data-ingest |
| C03-71 | The modern practitioner stack is overwhelmingly Python — pandas, numpy, statsmodels, scikit-learn — any deliverable code is expected to plug into this base. | §7.2 ¶1 | established | tooling; backtest |
| C03-72 | Backtesters split into event-driven (Backtrader, legacy Zipline) and vectorized (VectorBT, Numba-compiled, suited to parameter sweeps); a backtest framework choice must declare which camp it belongs to. | §7.2 ¶1 | established | backtest; tooling |
| C03-73 | QuantConnect Lean is C#-core with a Python API and integrated brokers — a hosted live/backtest path. | §7.2 ¶1 | established | backtest; oms; tooling |
| C03-74 | For larger-than-memory work, polars, DuckDB, and ArcticDB are the emerging trio — code targeting >RAM tick/feature stores should pick from these. | §7.2 ¶1 | established | backtest; tooling |
| C03-75 | ArcticDB is Man Group's time-series DB and a descendant of the 2015 open-sourced Arctic-on-MongoDB. | §7.2 ¶1 | established | tooling; backtest |
| C03-76 | Databento sells CME-direct data on a pay-as-you-go model — research-grade ingest can be cost-controlled per pull. | §7.3 ¶1 | established | data-ingest; pricing-model |
| C03-77 | dxFeed serves Level-1 and full-depth futures including softs — an alternative to Databento for futures depth. | §7.3 ¶1 | established | data-ingest |
| C03-78 | Polygon.io is equities-biased; Nasdaq Data Link (ex-Quandl) aggregates commodity indices, CFTC COT, and macro series; FRED is the free canonical U.S. macro source. | §7.3 ¶1 | established | data-ingest |
| C03-79 | The CFTC publishes COT every Friday at 3:30 PM ET — positioning-aware code should encode this slot. | §7.3 ¶1 | established | data-ingest; market-structure |
| C03-80 | A well-capitalized prop firm running a grain desk spends mid-six to low-seven figures/year on infrastructure and data alone, pre-headcount. | §8 ¶1 | established (illustrative) | pricing-model |
| C03-81 | CME direct market data plus iLink connectivity is roughly $10–50k/month in data plus $10–30k/month in colo/circuit. | §8 ¶1 | established (illustrative) | pricing-model; data-ingest; market-structure |
| C03-82 | Bloomberg or LSEG seats run $25–35k/year × 5–20 seats at the prop tier. | §8 ¶1 | established (illustrative) | pricing-model |
| C03-83 | TT or CQG execution costs $300–$1,000/user/month × 10–50 users at the prop tier. | §8 ¶1 | established (illustrative) | pricing-model; oms |
| C03-84 | Kpler cargo subscriptions cost $50–150k/year. | §8 ¶1 | established (illustrative) | pricing-model |
| C03-85 | Commercial weather subscriptions cost $30–100k/year. | §8 ¶1 | established (illustrative) | pricing-model |
| C03-86 | A small (2–5 person) grain specialist shop's annual infrastructure spend is ~$100k–$300k. | §8 ¶2 | established (illustrative) | pricing-model |
| C03-87 | A retail quant runs almost entirely on public data (delayed Barchart, pay-as-you-go Databento, NASS Quick Stats, CONAB/BCR PDFs, ECMWF/GFS open APIs, pandas/polars/DuckDB/Backtrader) at single- to low-four-figures/year. | §8 ¶3 | established (illustrative) | pricing-model; data-ingest; tooling |
| C03-88 | The retail-quant deficit versus institutional desks is commercial-flow color — Kpler, Gro, Descartes, Maxar, professional chat networks — not raw price/macro data. | §8 ¶3 | practitioner-lore | data-ingest |
| C03-89 | Independent, well-documented, real-time South American production indices remain rare; CONAB and BCR are monthly and proprietary satellite models close the gap. | §9 | debated | data-ingest |
| C03-90 | A standardized, machine-readable feed of Chinese reserve flows and plant-level crush margins does not exist; an equivalent of USDA's Grain Transportation Report for China is missing. | §9 | debated | data-ingest; market-structure |
| C03-91 | River-barge AIS analytics for the Illinois River and Mississippi remain patchy versus commoditized ocean AIS — high-frequency river logistics is a known gap. | §9 | debated | data-ingest |
| C03-92 | Retail-accessible full-depth historical CBOT-grain options tapes at research-grade quality are still thin; Databento's growing options coverage and CME DataMine offer a partial path. | §9 | debated | data-ingest; pricing-model; backtest |
| C03-93 | Open-source ag-specific feature pipelines combining NDVI, ERA5, soil maps, CDL (Cropland Data Layer), and NASS are reassembled from scratch at each shop — a known gap that any feature-store design will have to fill. | §9 | debated | data-ingest; tooling |
| C03-94 | ML-driven weather event-risk pricing is an active frontier — academic and open-source workflows are only recently absorbing neural weather models (GraphCast, AIFS, Pangu-Weather) for commodity-risk productionization. | §9 | debated | pricing-model; data-ingest |

## 3. What this file does NOT claim

The artifact is a tooling/infrastructure survey and is silent on several
adjacent areas that downstream phases would have to supply.

It does not specify CBOT soybean-complex contract specifications: tick size,
contract size in bushels, point value, last-trading-day rules, delivery
mechanics, or option strike intervals. It mentions ZS / ZM / ZL only as
ticker symbols carried on MDP 3.0; nothing about margin formulas, SPAN
parameters, or maintenance-vs-initial margin numerics is asserted.

It does not specify any pricing model for soybean futures, options, or the
crush spread itself — no Black-76 calibration, no skew/term-structure model,
no historical-vol estimator. Hanweck and LiveVol are only mentioned as
analytics vendors.

It does not specify hedging policies, hedge ratios, or board-crush
construction beyond noting that TT Autospreader supports legged execution.
There is no claim about commercial inventory accounting, basis-accrual rules,
or futures-vs-cash mark-to-market mechanics.

It does not specify density / yield-per-acre / weight conversion constants.
Yield-forecast vendors (Descartes, Gro) are mentioned as ingest sources but
the bushels-per-acre or bushels-to-metric-ton conversion is not stated.

It does not recommend specific products. The repeated framing is "without
recommending specific products"; comparative statements are practitioner
reputation, not buy-decisions.

It does not quantify SLAs for any of the listed vendors (uptime, mean
time-to-recovery, support tiering); cost ranges are flagged as illustrative.

It does not state any explicit regulatory rule beyond pointing at SEC 15c3-5
and CME iLink protocol naming; jurisdictional variants are not enumerated.

It does not assert anything about post-trade clearing, FCM segregation rules,
margin financing, or CME ClearPort flows.

## 4. Cross-links

The following claims plausibly depend on or interact with claims that would
appear in adjacent research files (inferred from context only).

C03-01 through C03-06 (CME MDP 3.0 mechanics) couple to a phase on
exchange-rules / contract-specs: any audit of an in-house tick capture must
reconcile MDP message types with the contract definitions used by a pricing
or margin module.

C03-14 and C03-16 (DTN ProphetX cash bids; Barchart cmdty National Soybean
Basis Index) feed a basis / inventory phase: the existence of 4,200+ daily
cash bids and a continuous national basis index implies an upstream choice
about how cash basis is normalized, which a basis-modelling claim would
have to resolve.

C03-22, C03-23, C03-30 (TT Order Book OMS, broker-hosted risk-layer routing)
will collide with any OMS / order-flow phase that asserts in-house pre-trade
risk: those phases must either inherit TT's pre-trade risk surface or
reconstruct it.

C03-28 and C03-29 (DMA / sponsored access pre-trade risk obligation under
SEC 15c3-5) cross-link to any contract / regulation phase: a different
research file may make claims about who owns the pre-trade-risk surface, and
those claims must be consistent with the member-MPID rule here.

C03-36 and C03-39 (Descartes Labs' 11-year corn-forecast backtest beating
USDA mid-cycle, Gro's county-level soy yield model) interact with any
strategy / backtest phase claiming a soy-yield signal: those phases either
ride a vendor signal or rebuild it from ERA5 / NDVI / USDA — the same fork
named in C03-39.

C03-46 through C03-49 (ECMWF IFS / NOAA GFS / ERA5 / NASA POWER) cross-link
to weather-driven pricing phases: any weather-yield model named elsewhere
must declare which NWP source and which reanalysis it is calibrated against,
and the licensing flag in C03-47 (CC-BY-4.0) constrains redistribution.

C03-53, C03-54, C03-55, C03-79 (WASDE / Crop Progress / FAS Export Sales /
COT publication slots) cross-link to any strategy or hedging phase that
claims event-driven trading windows: those phases inherit the calendar
asserted here. A hedging phase claiming "hold no position into WASDE" maps
directly to C03-53.

C03-58 and C03-59 (BCR/BCBA Argentine cash quotes; GACC import data;
Argentine 90% Rosario concentration; 2025 China imports 111.8 mt) cross-link
to any global-flow / supply-demand phase: such a phase must reconcile
seaborne flow numbers with these government totals.

C03-60 (GACC export-origin registration / 2018 + 2025 suspensions) cross-links
to any contract-risk or scenario phase modelling discrete trade-policy events.

C03-67 through C03-75 (kdb+ / OneTick / QuantHouse / pandas / polars /
DuckDB / ArcticDB / Backtrader / VectorBT / Lean) cross-link to any
backtest phase that names a specific framework: tooling assumptions in that
phase must select from the camps defined here.

C03-89 through C03-94 (the gap list) negatively cross-link to any phase that
asserts a turnkey solution exists in those areas (real-time SA yields,
Chinese reserves, river-barge AIS, retail-grade options tapes, open-source
ag-feature pipelines, neural-weather pricing) — such an assertion would
contradict this file's "remain rare / does not exist / patchy / thin /
reassembled from scratch / active frontier" framing.

---

*Pre-indexing only. No code audited; no vendor recommendations made.
Pricing tiers carried forward with the source's "illustrative" disclaimer
intact.*
