# Phase 03 — Tooling and Infrastructure: What Serious Grain Traders Actually Run

## Abstract

Serious grain trading is not executed on a single terminal. It is executed on a stack — exchange-direct market data at one end, an execution venue in the middle, a fundamentals and weather pipeline flowing sideways into a research notebook, and an increasingly alternative-data-heavy satellite and cargo layer bolted on top. This survey inventories that stack for the soybean complex, working through market data vendors (CME MDP 3.0, Bloomberg, LSEG Workspace, CQG, DTN ProphetX, Barchart, ICE Connect), execution platforms (Trading Technologies, CQG, Rithmic, Exegy-Vela), alt-data (Planet, Maxar, Descartes Labs, Orbital Insight, Gro Intelligence, Kpler, Vortexa), weather (Maxar WeatherDesk, Atmospheric G2, ECMWF IFS, NOAA GFS), government pipelines (USDA WASDE/NASS/FAS, CONAB, BCR/BCBA, China GACC), sell-side research (StoneX, Hightower, AgResource, Pro Farmer, Allendale), and backtesting stacks (kdb+, OneTick, ArcticDB, QuantConnect Lean, polars/DuckDB). For each category the discussion covers update cadence, cost tier, retail accessibility, and practitioner reputation — without recommending specific products.

---

## 1. Market data: futures, options, cash, and basis

Commodity traders consume market data at three tiers of latency and fidelity: exchange-direct feeds, consolidated vendor platforms, and retail/research-grade delayed feeds.

### 1.1 Exchange-direct: CME Market Data Platform (MDP 3.0)

The CBOT grain and oilseed contracts — ZS, ZM, ZL, ZC, ZW — disseminate through the CME Market Data Platform, currently at version 3.0. MDP 3.0 is a dual-feed UDP multicast service encoded with Simple Binary Encoding against the FIX 5.0 SP2 schema; it delivers bid, ask, trade, security-definition, and statistics messages, supports Market By Price (MBP) and Market By Order (MBO) book views, and layers MDP Premium on top for Market By Order Full Depth ([CME Group Client Systems Wiki, "CME MDP 3.0"](https://cmegroupclientsite.atlassian.net/wiki/display/EPICSANDBOX/CME+MDP+3.0+Market+Data); [CME Group, "Data Directly from the Market Data Platform"](https://www.cmegroup.com/market-data/distributor/market-data-platform.html); [OnixS, "CME MDP Premium SDK"](https://www.onixs.biz/cme-mdp-premium-market-data-handler.html)). Raw MDP consumption requires Aurora-data-center colocation or a cross-connect, a licensed feed handler, and a CME distributor license. Update cadence is event-driven microseconds; cost tier is institutional five-to-six figures per month; retail access is effectively zero.

A step below raw MDP is a managed, colocated feed handler. Exegy's SMDS — product of the 2021 Exegy/Vela merger — normalizes 300+ venues into one API and ships as managed software or hardware-accelerated appliances (nxFeed, XTP) at nanosecond latency ([Exegy, "Exegy and Vela Join Forces"](https://www.exegy.com/exegy-and-vela-join-forces/); [Exegy, "SMDS"](https://www.exegy.com/products/smds/); [Exegy, "XTP"](https://www.exegy.com/products/exegy-ticker-plant/)). It is the standard for shops that want raw-adjacent latency without building FPGA teams in-house.

Databento resells CME MDP 3.0 as a cloud-native API (GLBX.MDP3) with pay-as-you-go pricing down to MBO granularity, live and historical, across the full grain complex ([Databento, "GLBX.MDP3 feed specs"](https://databento.com/docs/venues-and-datasets/glbx-mdp3); [Databento, "GLBX.MDP3 dataset"](https://databento.com/datasets/GLBX.MDP3); [CME Group, "Databento"](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html)). It has become the default route for smaller quant shops and academic users needing exchange-grade fidelity without exchange-grade operational cost.

### 1.2 Consolidated vendors

**Bloomberg Terminal** is the reference installation on commercial hedging desks and sell-side research. Its ag coverage bundles real-time CBOT prices, news, pre-trade analytics, USDA data, and IB/CHAT collaboration; the Bloomberg Agriculture Subindex is a de facto commodity-overlay benchmark ([Bloomberg, "Agriculture"](https://www.bloomberg.com/markets/commodities/futures/agriculture); [Bloomberg, "Commodities Solutions"](https://www.bloomberg.com/professional/solutions/corporations/commodities/); [Bloomberg, "Ag Representative Index Methodology"](https://assets.bbhub.io/professional/sites/27/Bloomberg-Agriculture-Representative-Index-Methodology.pdf)). 2026 list pricing is ~$31,980/year single-seat, $28,320/seat multi-seat, two-year commitment, with enterprise discounts ([Costbench](https://costbench.com/software/financial-data-terminals/bloomberg-terminal/); [NeuGroup](https://www.neugroup.com/bloomberg-terminals-how-much-more-youll-pay-next-year/)). Retail rarely subscribes directly.

**LSEG Workspace** (formerly Refinitiv Eikon) is Bloomberg's main competitor, especially in European-rooted physical-commodity shops. Its ag package augments fundamentals with alt-data, weather, satellite imagery, and Reuters correspondent coverage; named-user base licensing sits in the $1,500–$3,000/user/month range plus $500–$2,000/user/month data add-ons ([LSEG Dev Portal, "Commodities"](https://developers.lseg.com/en/use-cases-catalog/commodities); [LSEG Workspace service overview](https://www.lseg.com/content/dam/data-analytics/en_us/documents/support/workspace/service-description.pdf); [Vendr, "LSEG pricing"](https://www.vendr.com/buyer-guides/refinitiv)).

**CQG** is arguably the most deeply embedded tool in Midwestern grain merchandising. It aggregates 85+ data sources across 45 exchanges, with DOMTrader, Spreadsheet Trader, and strong spread/options workflows; its chart quality is regarded in the trade as the gold standard ([CQG, "Market Data"](https://www.cqg.com/solutions/market-data); [CQG Desktop](https://www.cqg.com/products/cqg-desktop); [CQG One](https://www.cqg.com/products/cqg-one)). Institutional workstation: low-four-figures/month. CQG QTrader (FCM-rebadged): $50–$100/month retail.

**DTN ProphetX** is the screen most often found at country elevators, crushers, and cash-grain merchandisers. It combines CBOT futures, 4,200+ North American daily cash grain bids, 20-year cash history, DTN meteorologist commentary, and an Excel add-in ([DTN ProphetX](https://www.dtn.com/agriculture/agribusiness/prophetx/); [DTN ProphetX Commodity Edition](https://www.dtn.com/financial-analytics/commodity-trading/dtn-prophetx-commodity-edition/); [AMP Futures review](https://www.ampfutures.com/trading-platform/dtn-prophetx)). Cost: prosumer mid-three to institutional low-four-figures/month.

**Barchart cmdty** occupies the middle band. Its cmdtyView platform and REST API offer local-basis indices, continuous and EOD county-level cash grain pricing back to 2014, crop-production forecasts, and the widely cited cmdty National Soybean Basis Index ([Barchart ag hub](https://www.barchart.com/cmdty/markets/agriculture); [cmdty National Soybean Basis Idx](https://www.barchart.com/futures/quotes/ZSBAUS.CM/interactive-chart); [Barchart yield forecast](https://www.barchart.com/cmdty/indexes/yield-forecast)). Low-3 to low-4 figure/month, with a permissive free tier — the most retail-accessible serious vendor.

**ICE Connect** is ICE's cross-asset desktop/web; its ag package covers meals, grains, wheat, oilseeds, and vegetable oils, absorbing S&P Global Commodity Insights (ex-Platts) benchmarks in energy ([ICE Connect](https://www.ice.com/fixed-income-data-services/access-and-delivery/desktop-web-platforms/ice-connect); [ICE Connect — Real-time Data](https://www.ice.com/market-data/desktop-solutions/ice-connect)). Energy- and softs-weighted but a peer for mixed commodity/ag desks.

### 1.3 Options analytics

Equities-first options analytics vendors reach into agricultural options unevenly. **Cboe Hanweck** (acquired 2020) produces real-time implied vols and Greeks off its Volera engine across equity/ETF/index/futures options, but grain and oilseed depth is limited versus equities ([Cboe Hanweck](https://www.cboe.com/services/analytics/hanweck/); [PR Newswire, Cboe acquires Hanweck/FT Options](https://www.prnewswire.com/news-releases/cboe-global-markets-acquires-data-analytics-companies-hanweck-and-ft-options-300998333.html); [Cboe Hanweck content overview](https://cdn.cboe.com/resources/indices/documents/Cboe_Hanweck_Options-Analytics_Content-Overview-v1.4.pdf)). **Cboe LiveVol** is even more equities-native (time-and-sales back to 2011, ~$380/month for LiveVol Pro) and is not a CBOT-grain tool in practice ([LiveVol Pro](https://datashop.cboe.com/livevol-pro); [LiveVol](https://www.livevol.com/)). **OptionsCity** was rolled into Trading Technologies in 2018, so serious grain-options desks get analytics from TT or in-house. Pricing Partners' MX serves OTC commodity derivatives more than CBOT futures-options.

### 1.4 Market data — comparison

| Vendor | Update cadence | Cost tier | Retail access | Grain depth |
|---|---|---|---|---|
| CME MDP 3.0 (direct) | microseconds, multicast | institutional 5–6 figure/month | none | deepest |
| Exegy SMDS / XTP | microseconds, managed | institutional 5 figure/month | none | deep |
| Databento GLBX.MDP3 | live/historical API | pay-as-you-go; prosumer-friendly | yes | deep |
| Bloomberg Terminal | sub-second consolidated | institutional; ~$32k/yr/seat | via library only | broad |
| LSEG Workspace | sub-second consolidated | institutional; $1.5k–$3k/mo/seat | via library only | broad |
| CQG Integrated Client | sub-second consolidated | institutional; $1k–$2k/mo | via FCM (CQG QTrader) | deep |
| DTN ProphetX | real-time + cash bids | mid-3 to low-4 figure/month | limited | deepest ag-cash |
| Barchart cmdty | real-time + EOD basis | low-3 to low-4 figure/month | yes, free tier | wide ag |
| ICE Connect | sub-second consolidated | institutional | none | energy-first |

---

## 2. Execution platforms and OMS/EMS

Grain futures execution splits into two separable questions: which front-end a trader uses, and how orders reach CME's matching engine.

**Trading Technologies (TT)** is the largest third-party execution vendor for listed futures. The SaaS TT platform includes the MD Trader ladder (canonical grain execution interface), Autospreader for board-crush and other legged execution, ADL algorithmic development, TT Order Book (OMS), TT Score (surveillance), and TT Fundamental Analytics merging fundamentals with price ([TT platform](https://tradingtechnologies.com/trading/tt-platform/); [TT home](https://tradingtechnologies.com/); [MarketsWiki TT](https://www.marketswiki.com/wiki/Trading_Technologies_International)). Client base: Tier-1 banks, CTAs, prop shops, commercial hedgers, algorithmic traders. Options-on-futures are integrated via the Options Trade Monitor. Cost: low-to-mid three figures per user per month plus exchange data pass-throughs.

**CQG Trader / Desktop / One** overlaps heavily with TT in execution but is more deeply loved among traditional Chicago-grain floor descendants. DOMTrader, Order Ticket, Order Desk, and Spreadsheet Trader route across aggregated exchanges ([CQG Desktop](https://www.cqg.com/products/cqg-desktop); [Cannon Trading, CQG](https://www.cannontrading.com/tools/support-resistance-levels/cqg-futures-platform/); [CQG Wikipedia](https://en.wikipedia.org/wiki/CQG)). CQG's data-feed quality is a decisive advantage for chart-driven discretionary spread traders.

**Rithmic** is the infrastructure layer underneath many smaller FCMs and prop shops. Broker- and FCM-neutral, colocated in Aurora, engineered for sub-100-ms routing, exposed through broker-rebadged R|Trader Pro ([Rithmic](https://www.rithmic.com/); [Rithmic IBs](https://www.rithmic.com/introducingbrokers); [R|Trader Pro](https://optimusfutures.com/Platforms/Rithmic-RTrader-Pro.php)). Full CBOT/CME/COMEX/NYMEX/MGEX coverage. User cost: $20–$100/month via the FCM.

**Stellar**, legacy **X_Trader** (retired 2021), **Pats**, and other niche front-ends persist on specific desks. The 2026 market share reality: TT + CQG dominate multi-user merchandiser/prop tier; Rithmic + broker front-ends dominate lower down.

**DMA vs. sponsored access vs. broker-hosted.** Models differ by risk ownership and whose MPID the order carries. Under **DMA**, the customer uses the member's infrastructure but routes orders directly; the member retains pre-trade-risk responsibility ([Wikipedia, DMA](https://en.wikipedia.org/wiki/Direct_market_access); [Databento, DMA](https://databento.com/microstructure/dma); [FIA DMA guidance](https://www.fia.org/sites/default/files/2019-05/DMA-guidance-Note-Final.pdf)). Under **sponsored access**, the customer uses the member's MPID but bypasses its infrastructure — faster but, in "naked" form, now universally filtered by pre-trade risk rules required by SEC 15c3-5 and analogs ([CounselStack](https://blog.counselstack.com/market-access-direct-market-access-sponsored-access-compliance/); [SGX Rulebook 4.2](https://rulebook.sgx.com/rulebook/42-direct-market-access-and-sponsored-access)). **Broker-hosted** routes pass through the broker's OMS/risk layer — slower, fewer operational surprises.

CME specifics: **iLink** is the Globex order-entry protocol with MSGW (dedicated) and CGW (multi-segment) gateways; **CME Globex Hub — Aurora** provides Equinix-adjacent colocation access ([CME connectivity options](https://www.cmegroup.com/solutions/market-access/globex/connectivity-options.html); [CME Globex](https://www.cmegroup.com/solutions/market-access/globex.html); [CME Aurora Hub](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457088573/CME+Globex+Hub+-+Aurora); [OnixS iLink 3 BOE SDK](https://www.onixs.biz/cme.html)). Proximity-hosted access via Beeks or Equinix NY5 is the norm for shops too small for own rack space.

### 2.1 Execution platforms — comparison

| Platform | Primary users | Cost tier | Options workflow | Grain reputation |
|---|---|---|---|---|
| Trading Technologies | banks, CTAs, prop, commercials | institutional $250–$1,000/user/mo | Options Trade Monitor, MD Trader | dominant |
| CQG Integrated Client | merchandisers, spread traders | institutional $1k–$2k/mo | native | gold standard for charts |
| CQG QTrader (retail) | retail futures | $50–$100/mo via FCM | basic | strong |
| Rithmic (broker-hosted) | retail to mid-tier prop | $20–$100/mo via FCM | limited | ubiquitous |
| Exegy/Vela execution | HFT / market makers | institutional | FPGA-accel | HFT-focused |
| Proprietary sell-side OMS/EMS | large commercials (ADM, Bunge, Cargill, Dreyfus) | in-house build cost | deeply customized | highest internally |

---

## 3. Alternative data — agriculture-relevant

The alt-data stack for grains breaks into three families: satellite-derived crop observation, shipping/flow tracking, and surface transportation.

### 3.1 Satellite imagery and crop monitoring

**Planet Labs** operates the largest earth-observation cubesat constellation and sells near-daily 3.7-m imagery over all landmass via API/web/GIS. Its ag positioning is in-season crop health, pest/disease early warning, and biomass/soil-moisture proxies for yield models ([Planet Monitoring](https://www.planet.com/products/satellite-monitoring/); [Planet Agriculture](https://www.planet.com/industries/agriculture/); [Planet Pricing](https://www.planet.com/pricing/)). Pricing is seat/area-based, firmly institutional; farm-scale integrations cite ~$1.25/acre/year as a retail reference point.

**Maxar** (weather-line now Vaisala Xweather; Intelligence still Maxar) provides sub-meter imagery, historically defense-weighted; ag uses it for yield verification and logistics checks layered into WeatherDesk ([Maxar WeatherDesk](https://www.maxar.com/products/weatherdesk); [Maxar Intelligence WeatherDesk](https://www.maxar.com/maxar-intelligence/products/weatherdesk)).

**Descartes Labs** industrialized AI-on-satellite for crops. Its U.S. corn/soy yield-forecast models ingest MODIS/VIIRS/Landsat/Sentinel plus weather and crop progress; 11-year backtests show its U.S. corn forecasts beat USDA's mid-cycle estimates at every growing-season step ([Descartes, "Corn Forecasting"](https://medium.com/descarteslabs-team/advancing-the-science-of-corn-forecasting-350603e3c57f); [Descartes, "Soy Forecasting"](https://blog.descarteslabs.com/advancing-the-science-of-soy-forecasting); [AgFunderNews, Cargill invests](https://agfundernews.com/descartes-raise); [HBS D3 case](https://d3.harvard.edu/platform-rctom/submission/descartes-labs-predicting-farmers-fortunes-from-space/)). Subscribers get every-two-day forecast updates versus public weekly — a deliberate information-asymmetry trade.

**Orbital Insight** was an early mover in satellite-derived commodity signals (oil-storage lid heights, corn/soy yield, vessel counts) but had a commercial rough patch and was acquired by Privateer Space (Wozniak) in May 2024 ([Orbital Insight](https://www.orbitalinsight.com/); [Wikipedia](https://en.wikipedia.org/wiki/Orbital_Insight); [Fortune](https://fortune.com/2017/12/16/satellites-commodity-trading-world/); [Nanalyze](https://www.nanalyze.com/2017/01/orbital-insight-artificial-intelligence/)).

**Gro Intelligence** aggregates 170,000+ datasets into one ag-climate database; its U.S. Soybean Yield Forecast Model runs county-level through the growing season, alongside crush, trade-flow, and stocks-to-use models ([Gro US Soy Yield Model](https://gro-intelligence.com/models/us-soybean-yield-forecast-model); [Gro Agriculture](https://gro-intelligence.com/agriculture); [Inc. profile](https://www.inc.com/magazine/202011/kevin-j-ryan/sara-menker-gro-intelligence-female-founders-2020.html); [Columbia Magazine](https://magazine.columbia.edu/article/how-gro-intelligence-fighting-world-hunger-tech)). Mid-2024 funding difficulties pushed many practitioners to rebuild Gro-style pipelines in-house from public ERA5/NDVI/USDA inputs.

**NDVI and soil-moisture platforms.** Free indices — MODIS MOD13, Sentinel-2 NDVI, ESA Soil Moisture CCI — sit underneath commercial products. Copernicus Land Monitoring and EarthDaily add validated layers; research practitioners mostly work from raw Sentinel Hub or Google Earth Engine ([Copernicus soil moisture](https://land.copernicus.eu/en/products/soil-moisture); [HESS assessment paper](https://hess.copernicus.org/articles/27/1173/2023/hess-27-1173-2023.pdf)).

### 3.2 Shipping and cargo flow

**Kpler** dominates waterborne-commodity tracking: 350,000+ vessels daily over a proprietary 13,000+ AIS-receiver network, with explicit coverage of grains/oilseeds (corn, wheat, barley, soybean, sunflower, rapeseed, meals) and vegetable oils ([Kpler Commodities](https://www.kpler.com/product/commodities); [Kpler Ag & Biofuels](https://www.kpler.com/market/agricultural-commodities-and-biofuels); [Kpler Supply & Demand](https://www.kpler.com/product/commodities/supply-demand); [Kpler via ICE](https://developer.ice.com/fixed-income-data-services/catalog/kpler)). For soy, value is concentrated in Brazilian ports (Santos, Paranaguá), U.S. Gulf, and Chinese discharge terminals — tracking 120+ million tons/year of seaborne flow weeks before customs.

**Vortexa** tracks $3.4 trillion of waterborne trade annually, strongest in crude/products/LNG, but its freight, fleet-utilization, and port-congestion metrics read across to soy cargo — Panama Canal, dry-bulk rates, Brazilian port queues ([Vortexa](https://www.vortexa.com/); [Vortexa cargo tracking](https://www.vortexa.com/feature/cargo-vessel-tracking-maps)).

### 3.3 Surface transport — trucking, rail, river

The USDA AMS **Grain Transportation Report** publishes weekly Illinois River barge rates, Lower Mississippi lock-by-lock tonnage, corn-belt-to-Gulf/PNW rail tariffs, and ocean freight benchmarks, with datasets downloadable as CSV ([USDA AMS GTR datasets](https://www.ams.usda.gov/services/transportation-analysis/gtr-datasets); [USDA AMS Transportation](https://www.ams.usda.gov/services/transportation-analysis); [GTR 09-25-2025 issue](https://www.ams.usda.gov/sites/default/files/media/GTR09252025.pdf)). For higher-frequency data, commercial AIS (MarineTraffic, now Kpler-owned) replaces weekly lock counts with near-real-time barge positions.

### 3.4 Alternative data — comparison

| Provider | Data type | Cadence | Cost tier | Retail | Soybean relevance |
|---|---|---|---|---|---|
| Planet Labs | 3.7m optical imagery | near-daily | institutional | limited self-serve | in-season crop monitoring |
| Maxar (Intelligence / WeatherDesk) | sub-meter + weather | daily+ | institutional | no | spot-check, logistics, weather |
| Descartes Labs | ML crop forecasts | every 2 days (sub)/weekly (free) | institutional | historical free | direct soy yield |
| Orbital Insight | ML object counts, storage, crop | weekly+ | institutional | no | soy + logistics |
| Gro Intelligence | aggregated ag/climate database + models | continuous | institutional | limited | soy-native |
| Kpler | AIS + cargo flows | real-time | institutional | no | seaborne soy flows |
| Vortexa | AIS, energy cargo | real-time | institutional | no | freight read-across |
| USDA Grain Transportation Report | barge/rail/truck rates | weekly | free | yes | U.S. logistics |

---

## 4. Weather data

Commodity weather data splits between (i) free raw NWP model outputs and (ii) paid forecast-aggregation/interpretation platforms.

**ECMWF's IFS** is generally considered the most accurate global medium-range model, with **NOAA GFS** slightly behind. IFS runs twice daily at ~9 km resolution with 15-day ensembles and SEAS5 sub-seasonal/seasonal forecasts; ECMWF publishes a free CC-BY-4.0 open-data subset ([Wikipedia IFS](https://en.wikipedia.org/wiki/Integrated_Forecast_System); [ECMWF IFS](https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model); [ECMWF open data](https://www.ecmwf.int/en/forecasts/datasets/open-data)). **ERA5 / ERA5-Land** are the gold-standard hourly reanalyses back to 1940 and the dominant input for backtested weather–yield models ([ECMWF ERA5-Land](https://www.ecmwf.int/en/era5-land); [ESSD ERA5-Land paper](https://essd.copernicus.org/articles/13/4349/2021/)). **NOAA GFS/NAM/HRRR** and **NASA POWER** fill the free U.S./global layer at varying resolutions.

Commercial platforms: **DTN Weather** (having absorbed Telvent DTN and the former MDA Information Systems / MDA Weather Services) is the most entrenched provider in U.S. ag desks, with meteorologist commentary feeding ProphetX directly ([DTN ProphetX](https://www.dtn.com/agriculture/agribusiness/prophetx/)). **Maxar WeatherDesk** (now Vaisala Xweather) markets "faster-than-NWS" global forecasts, 30-day sub-seasonal outlooks, and bespoke energy/ag impact analytics ([WeatherDesk Faster Forecasting](https://explore.maxar.com/faster-forecasts.html); [WeatherDesk analytics](https://explore.maxar.com/Powering-Advanced-Analytics-With-WeatherDesk); [AWS HPC blog](https://aws.amazon.com/blogs/hpc/how-maxar-builds-short-duration-bursty-hpc-workloads-on-aws-at-scale/)). **Atmospheric G2** (merged MDA/WSI/WDT) is the weather-risk analytics standard for energy, commodity, and weather-derivatives work ([Atmospheric G2](https://atmosphericg2.com/)). **StormGeo** is similar, more shipping/energy-weighted. Commercial weather pricing is institutional low-four to mid-five figures per month.

### 4.1 Weather data — comparison

| Source | Type | Cadence | Cost tier | Practitioner view |
|---|---|---|---|---|
| ECMWF IFS (open data) | global NWP | 2×/day | free (CC-BY-4.0) | benchmark accuracy |
| NOAA GFS | global NWP | 4×/day | free | primary U.S. reference |
| ERA5 / ERA5-Land | reanalysis | hourly history | free | gold-standard backtest input |
| NASA POWER | ag climatology API | daily | free | common in academic models |
| DTN Weather | commercial forecast + commentary | sub-hourly | institutional low-4 figure/mo | ag-desk standard |
| Maxar WeatherDesk | commercial global NWP | sub-hourly | institutional | trader-focused |
| Atmospheric G2 | probabilistic weather risk | daily + event | institutional | weather-derivatives standard |
| StormGeo | commercial | daily | institutional | shipping/energy weighted |

---

## 5. Fundamentals and government data pipelines

USDA is the scheduled-information backbone of the U.S. soybean complex. **WASDE** releases monthly at 12:00 p.m. ET around the 10th–12th (2026 dates span January 12 through December 10) and sets the balance sheet that anchors price ([WASDE](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report); [AGSIST Calendar](https://agsist.com/usda-calendar); [CME USDA Reports 2026](https://www.cmegroup.com/articles/2026/understanding-major-usda-reports-in-2026.html)). **NASS Crop Progress** runs weekly at 4 p.m. ET Mondays April through November, with county-level gridded layers released synthetically ([NASS Quick Stats](https://www.nass.usda.gov/Quick_Stats/); [NASS Developers](https://www.nass.usda.gov/developer/index.php); [Data.gov Quick Stats API](https://catalog.data.gov/dataset/quick-stats-agricultural-database-api)). **FAS Weekly Export Sales** publishes Thursdays at 8:30 a.m. ET — a highly market-moving release on the Friday-through-Thursday reporting window ([FAS weekly catch-up schedule](https://www.fas.usda.gov/programs/export-sales-reporting-program/weekly-export-sales-catch-schedule); [FAS reporting schedule notice](https://www.fas.usda.gov/newsroom/stakeholder-notice-daily-and-weekly-export-sales-reporting-schedule); [FAS U.S. Export Sales](https://apps.fas.usda.gov/export-sales/esrd1.html)). All free; machine consumption via NASS Quick Stats API, FAS GAIN attaché reports, and FOIA bulk downloads.

**Brazil's CONAB** publishes monthly S&D by state and is the market's South-American parallel to WASDE ([Global-Agriculture CONAB 177.6mt](https://www.global-agriculture.com/latam-agriculture/conab-estimating-2025-26-brazil-soybean-production-at-177-6-mt/); [Brownfield CONAB record](https://www.brownfieldagnews.com/news/brazils-conab-forecasts-record-soybean-output-higher-exports/); [OCJ CONAB 166mt](https://ocj.com/2024/12/conab-maintains-estimate-of-166-million-tons-for-brazilian-soybeans/)). **Argentina's BCBA** (Buenos Aires) and **BCR** (Rosario) publish competing weekly crop monitors and daily Rosario/Paraná cash quotations — the region handles 90%+ of Argentine soy exports ([BCR](https://www.bcr.com.ar/en); [Rosario Board of Trade](https://en.wikipedia.org/wiki/Rosario_Board_of_Trade); [BCR Mercado de Granos](https://www.bcr.com.ar/es/mercados/boletin-diario/mercado-de-granos)).

**China** is the demand-side black box. **GACC** publishes monthly import volumes/values by HS code — 2025 soybean imports hit 111.8 million tons — and enforces export-origin registration, shown in the 2018 and 2025 shipment suspensions ([Global Times 2025 imports](https://www.globaltimes.cn/page/202601/1353178.shtml); [USDA FAS GAIN GACC suspension](https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=GACC+Announces+Suspension+of+Soybean+Shipments+from+Three+US+Entities_Beijing_China+-+People's+Republic+of_CH2025-0046.pdf); [China Customs](http://english.customs.gov.cn/)). **Sinograin** state-reserve auction disclosures are episodic, translated via USDA FAS attachés or specialist consultancies like JCI and Sitonia ([FAS China Oilseeds Annual](https://www.fas.usda.gov/data/china-oilseeds-and-products-annual-9); [farmdoc daily on China soy demand](https://farmdocdaily.illinois.edu/2025/12/can-china-reduce-soybean-import-demand-evaluating-soybean-meal-reduction-efforts.html)).

---

## 6. Research platforms and sell-side analytics

Sell-side research in grains concentrates in a handful of independent advisories plus FCM-embedded desks.

**StoneX** (formerly INTL FCStone) is the largest non-bank commodity intermediary with a dedicated Market Intelligence franchise publishing soy weekly reports, global outlooks, crop surveys, and twice-daily commentary from Chief Commodities Economist Arlan Suderman; its U.S. bean-yield surveys are treated as a parallel read on NASS ([StoneX Ag reports](https://www.stonex.com/en/market-intelligence/agriculture-reports/); [Grains Q3 2025 outlook](https://www.stonex.com/en/thought-leadership/global-outlook-for-soybeans-corn-wheat-and-vegetable-oils-q3-2025/); [US Crop Surveys](https://www.stonex.com/en/thought-leadership/08-06-2025-us-crop-surveys-signal-pressure-on-wheat-and-soybean-markets/)).

**The Hightower Report** (independent since 1990) produces twice-daily Grain & Livestock Commentary (8:15 a.m. and 3:45 p.m. CT), daily Tech Summaries, and USDA-event coverage; it is a near-ubiquitous desk read ([Hightower](https://www.hightowerreport.com); [Futures-research subscribe](https://www.futures-research.com/)). **AgResource** (founded by Dan Basse) is the long-standing global grain advisory; daily research, weekly S&D revisions, and "Farm Marketing" service target producers, merchants, and funds ([AgResource subscription](https://agresource.com/subscription/); [RealAgriculture — Grainfox partnership](https://www.realagriculture.com/2024/03/grainfox-partners-with-agresource-in-u-s-market-expansion/)). **Pro Farmer** (Farm Journal) runs the most-watched August crop tour across the I-states; its final yield estimate is the primary private-sector precursor to the August/September WASDE ([Pro Farmer](https://www.profarmer.com/); [MarketScreener — Crop Tour](https://www.marketscreener.com/news/futures-fall-as-crop-tour-finds-healthy-fields-daily-grain-highlights-ce7c51dddc81fe23)). **Allendale** (McHenry, IL, since 1984) issues its Advisory Report four times daily with technical, fundamental, and COT commentary ([MarketsWiki Allendale](https://www.marketswiki.com/wiki/Allendale,_Inc.); [CME Find a Broker — Allendale](https://www.cmegroup.com/tools-information/find-a-broker/allendale-inc.html)). The **RJO Grain Report** sits alongside these, while ADM, Bunge, Cargill, and Louis Dreyfus publish analogous internal research consumed by clients via relationship sales.

Pricing is prosumer — $500–$3,000/year for Hightower, Allendale, Pro Farmer, AgResource; StoneX Market Intelligence is bundled with FCM relationships.

---

## 7. Backtesting and analytics stacks

### 7.1 Commercial tick stores

**kdb+/q** (KX Systems) is the canonical HFT tick-store — a columnar in-memory time-series database with its own vector language (q) used by essentially every tier-one bank, HFT market maker, and systematic hedge fund; grain-futures use is niche but present in option market-making shops ([Wikipedia "Kdb+"](https://en.wikipedia.org/wiki/Kdb+); [timestored.com](https://www.timestored.com/kdb-guides/who-uses-kdb); [Medium — hedge funds and kdb+](https://medium.com/@tzjy/comprehensive-guide-how-hedge-funds-use-kdb-in-quantitative-trading-9638ef43bb86)). Cost: institutional mid-six-figure licensing. **OneTick** (OneMarketData) is the second-most-common institutional tick DB, with a reputation for easier integration than kdb ([OneTick](https://www.onetick.com/); [OneTick Cloud](https://www.onetick.com/market-data)). **Deltix** (EPAM) provides a QuantOffice/QuantServer IDE unifying research, backtesting, and live trading. **QuantHouse** (Iress) provides 15+ years of normalized tick history across 145+ exchanges including commodities ([QuantHouse HOD](https://quanthouse.com/hod/)).

### 7.2 Open-source Python stack

The modern practitioner stack is overwhelmingly Python — **pandas**, **numpy**, **statsmodels**, **scikit-learn**. Backtesters split into event-driven (**Backtrader**, legacy **Zipline**) and vectorized (**VectorBT**, Numba-compiled, suited to parameter sweeps) camps. **QuantConnect Lean** is C#-core with Python API and integrated brokers ([Medium, backtester comparison](https://medium.com/@trading.dude/battle-tested-backtesters-comparing-vectorbt-zipline-and-backtrader-for-financial-strategy-dee33d33a9e0); [QuantVPS](https://www.quantvps.com/blog/best-python-backtesting-libraries-for-trading); [QuantRocket](https://www.quantrocket.com/blog/backtest-speed-comparison); [Pytrade.org](https://github.com/PFund-Software-Ltd/pytrade.org)). For larger-than-memory work, **polars** (Rust DataFrames), **DuckDB** (in-process OLAP), and **ArcticDB** (Man Group's time-series DB, descendant of the 2015 open-sourced Arctic-on-MongoDB) are the emerging trio ([ArcticDB](https://arcticdb.io/); [Man Group Arctic](https://www.man.com/technology/arctic-datascience-database); [HN discussion](https://news.ycombinator.com/item?id=41309997); [GitHub man-group/arctic](https://github.com/man-group/arctic); [MongoDB press release](https://www.mongodb.com/company/newsroom/press-releases/man-ahl-arctic-open-source); [Medium — DuckDB + Polars](https://medium.com/quant-factory/trading-data-analytics-part-2-top-momentum-using-duckdb-and-polars-39586d8a4cdb)).

### 7.3 Data distribution for quants

Below prices and fundamentals sit data-distribution APIs. **Databento** sells CME-direct pay-as-you-go. **dxFeed** serves Level-1 and full-depth futures including softs ([dxFeed futures](https://dxfeed.com/market-data/futures/)). **Polygon.io** is equities-biased. **Nasdaq Data Link** (ex-Quandl) aggregates commodity indices, CFTC COT, and macro series. **FRED** is the free canonical U.S. macro source. **CFTC** publishes COT every Friday at 3:30 p.m. ET.

### 7.4 Analytics stacks — comparison

| Tool | Category | Cost tier | Retail | Grain use |
|---|---|---|---|---|
| kdb+/q | tick DB, analytics | institutional 6-figure | no | HFT / option-MM |
| OneTick | tick DB + analytics | institutional | no | institutional |
| Deltix QuantOffice | IDE, tick, exec | institutional | no | emerging |
| QuantHouse HOD | 15yr tick history | institutional | no | institutional |
| ArcticDB | open-core time-series | free-to-use core | yes | growing in quant shops |
| polars / DuckDB | analytics engines | free | yes | universal |
| pandas / numpy / statsmodels | analytics | free | yes | universal |
| Backtrader / Zipline / VectorBT | Python backtesters | free | yes | yes |
| QuantConnect Lean | hosted quant platform | free–low-3-figure/mo | yes | yes |
| Databento | API data distribution | pay-as-you-go | yes | yes |
| Nasdaq Data Link | aggregator | free–prosumer | yes | yes |
| FRED | macro data | free | yes | yes |

---

## 8. Cost and access tiering

A well-capitalized prop firm running a grain desk typically spends mid-six to low-seven figures/year on infrastructure and data alone, pre-headcount: CME direct market data and iLink connectivity ($10–50k/mo in data plus $10–30k/mo colo/circuit), Bloomberg or LSEG seats ($25–35k/year × 5–20), TT or CQG execution ($300–1,000/user/mo × 10–50), Rithmic backup, Planet/Maxar subscriptions, Kpler cargo ($50–150k/yr), a commercial weather provider ($30–100k/yr), and kdb+/OneTick or a custom ArcticDB/polars stack. StoneX, Hightower, AgResource typically come bundled with FCM relationships.

A small shop (two-to-five-person grain specialist) trades fidelity for cost: a shared Bloomberg seat, CQG or DTN ProphetX, Databento or Barchart for historical/research, one sell-side subscription, NASS/FAS/FRED for government data, free weather plus a narrow commercial overlay, and in-house Python. Annual infrastructure: ~$100k–$300k.

A retail quant runs almost entirely on public data: delayed quotes via Barchart, pay-as-you-go Databento tick pulls, NASS Quick Stats for WASDE/Crop Progress, CONAB/BCR PDFs, ECMWF/GFS open APIs, pandas/polars/DuckDB/Backtrader. Total: single- to low-four-figures per year. The disadvantage is less data than commercial-flow color — Kpler, Gro, Descartes, Maxar, and professional chat networks — that institutional desks get routinely.

---

## 9. Gaps and emerging tools

Several areas of the grain-data stack remain structurally underserved.

*Real-time South American yield data.* CONAB and BCR publish monthly; proprietary satellite models (Descartes, Gro, in-house builds at ABCD crushers) close the gap, but independent, well-documented, real-time South American production indices remain rare.

*Chinese crush-margin and reserve-flow transparency.* Sinograin auction disclosures and GACC import data are lagged and selectively translated. There is room for a standardized, machine-readable feed of Chinese reserve flows and plant-level crush margins; specialist consultancies serve large commercials, but a transparent equivalent of USDA's Grain Transportation Report for China does not exist.

*Barge AIS analytics for Illinois River and Mississippi.* While ocean AIS (Kpler, Vortexa) is now commoditized, river-barge equivalents remain patchy — an area where proprietary AIS feeds could supplement the USDA Grain Transportation Report's weekly cadence.

*Cheap, high-fidelity historical options tapes for CBOT grains.* kdb+-class tick stores carry this data at institutional cost, and LiveVol/Hanweck are equities-weighted. Databento's growing options coverage and CME's own DataMine offer a partial path, but retail-accessible full-depth soybean options tapes at research-grade quality are still thin.

*Open-source ag-specific feature pipelines.* Research-grade yield modelling requires combining NDVI, ERA5, soil maps, CDL (Cropland Data Layer), and NASS — a task currently reassembled from scratch at each shop. Gro Intelligence's dataset catalogue was the closest commercial product; its operational trajectory has left a gap that an open-source ag-ML pipeline could fill.

*ML-driven weather event-risk pricing.* Commercial providers (Atmospheric G2, Maxar WeatherDesk) do this, but the academic and open-source side is only recently absorbing neural weather models (GraphCast, AIFS, Pangu-Weather); productionizing these for commodity risk is an active frontier.

---

## Key takeaways

Serious grain trading runs on a layered stack, not a monolithic terminal. Exchange-direct feeds (CME MDP 3.0) and managed alternatives (Exegy, Databento) supply raw data; consolidated vendors (Bloomberg, LSEG, CQG, DTN ProphetX, Barchart, ICE Connect) add news, analytics, and cash-market integration; execution is dominated by TT and CQG at the top and Rithmic-backed broker front-ends at retail, with DMA, sponsored access, and broker-hosted routing spanning a latency-vs-risk-ownership spectrum.

Alt-data — satellite (Planet, Maxar, Descartes, Orbital Insight, Gro), cargo (Kpler, Vortexa), and logistics (USDA GTR + commercial AIS) — is now table-stakes for serious commercials; weather layers commercial services (DTN, Maxar WeatherDesk, Atmospheric G2) over free NWP (ECMWF IFS, NOAA GFS, ERA5). USDA, CONAB, BCR/BCBA, and GACC form the scheduled-fundamentals core; StoneX, Hightower, AgResource, Pro Farmer, and Allendale lead independent sell-side research.

Research infrastructure bifurcates: kdb+, OneTick, and QuantHouse hold the institutional tier, while pandas/polars/DuckDB/ArcticDB plus Backtrader/VectorBT/Lean power a rapidly converging retail stack. Annual cost spans ~$1,000 for a retail quant to mid-seven figures for a well-equipped prop desk. Gaps persist around real-time South American yields, Chinese reserve transparency, river-barge analytics, retail-accessible CBOT options tapes, and open-source ag-ML pipelines — the likely frontier for the next wave of vendors.

---

## References

Market data and exchange infrastructure:
- [CME MDP 3.0](https://cmegroupclientsite.atlassian.net/wiki/display/EPICSANDBOX/CME+MDP+3.0+Market+Data); [Market Data Platform](https://www.cmegroup.com/market-data/distributor/market-data-platform.html); [Connectivity Options](https://www.cmegroup.com/solutions/market-access/globex/connectivity-options.html); [Globex](https://www.cmegroup.com/solutions/market-access/globex.html); [Globex Hub Aurora](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457088573/CME+Globex+Hub+-+Aurora); [Databento Vendor Page](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html); [2026 USDA Reports](https://www.cmegroup.com/articles/2026/understanding-major-usda-reports-in-2026.html)
- [OnixS MDP Premium SDK](https://www.onixs.biz/cme-mdp-premium-market-data-handler.html); [OnixS iLink 3 BOE](https://www.onixs.biz/cme.html)
- [Exegy–Vela merger](https://www.exegy.com/exegy-and-vela-join-forces/); [SMDS](https://www.exegy.com/products/smds/); [XTP](https://www.exegy.com/products/exegy-ticker-plant/)
- [Databento GLBX.MDP3 specs](https://databento.com/docs/venues-and-datasets/glbx-mdp3); [API](https://databento.com/datasets/GLBX.MDP3); [DMA guide](https://databento.com/microstructure/dma)

Consolidated vendors and execution:
- Bloomberg: [Agriculture](https://www.bloomberg.com/markets/commodities/futures/agriculture); [Commodities](https://www.bloomberg.com/professional/solutions/corporations/commodities/); [Ag Index Methodology](https://assets.bbhub.io/professional/sites/27/Bloomberg-Agriculture-Representative-Index-Methodology.pdf); [Costbench 2026](https://costbench.com/software/financial-data-terminals/bloomberg-terminal/); [NeuGroup pricing](https://www.neugroup.com/bloomberg-terminals-how-much-more-youll-pay-next-year/)
- LSEG: [Commodities](https://developers.lseg.com/en/use-cases-catalog/commodities); [Workspace overview](https://www.lseg.com/content/dam/data-analytics/en_us/documents/support/workspace/service-description.pdf); [Vendr pricing](https://www.vendr.com/buyer-guides/refinitiv)
- CQG: [Market Data](https://www.cqg.com/solutions/market-data); [Desktop](https://www.cqg.com/products/cqg-desktop); [CQG One](https://www.cqg.com/products/cqg-one); [Wikipedia](https://en.wikipedia.org/wiki/CQG); [Cannon Trading](https://www.cannontrading.com/tools/support-resistance-levels/cqg-futures-platform/)
- DTN: [ProphetX Agribusiness](https://www.dtn.com/agriculture/agribusiness/prophetx/); [Commodity Edition](https://www.dtn.com/financial-analytics/commodity-trading/dtn-prophetx-commodity-edition/); [AMP Futures review](https://www.ampfutures.com/trading-platform/dtn-prophetx)
- Barchart: [Agriculture](https://www.barchart.com/cmdty/markets/agriculture); [Soybean Basis Idx](https://www.barchart.com/futures/quotes/ZSBAUS.CM/interactive-chart); [Yield Forecasts](https://www.barchart.com/cmdty/indexes/yield-forecast)
- ICE: [Connect](https://www.ice.com/fixed-income-data-services/access-and-delivery/desktop-web-platforms/ice-connect); [Real-time Data](https://www.ice.com/market-data/desktop-solutions/ice-connect)
- Trading Technologies: [Platform](https://tradingtechnologies.com/trading/tt-platform/); [MarketsWiki](https://www.marketswiki.com/wiki/Trading_Technologies_International)
- Rithmic: [home](https://www.rithmic.com/); [Introducing Brokers](https://www.rithmic.com/introducingbrokers); [R|Trader Pro](https://optimusfutures.com/Platforms/Rithmic-RTrader-Pro.php)
- Options analytics: [Cboe Hanweck](https://www.cboe.com/services/analytics/hanweck/); [Hanweck acquisition PR](https://www.prnewswire.com/news-releases/cboe-global-markets-acquires-data-analytics-companies-hanweck-and-ft-options-300998333.html); [Hanweck Overview](https://cdn.cboe.com/resources/indices/documents/Cboe_Hanweck_Options-Analytics_Content-Overview-v1.4.pdf); [LiveVol Pro](https://datashop.cboe.com/livevol-pro)
- DMA/Sponsored Access: [Wikipedia DMA](https://en.wikipedia.org/wiki/Direct_market_access); [CounselStack](https://blog.counselstack.com/market-access-direct-market-access-sponsored-access-compliance/); [SGX Rulebook 4.2](https://rulebook.sgx.com/rulebook/42-direct-market-access-and-sponsored-access); [FIA DMA guidance](https://www.fia.org/sites/default/files/2019-05/DMA-guidance-Note-Final.pdf)

Alternative data, cargo, and weather:
- Planet: [Monitoring](https://www.planet.com/products/satellite-monitoring/); [Agriculture](https://www.planet.com/industries/agriculture/); [Pricing](https://www.planet.com/pricing/)
- Descartes Labs: [Soy forecasting](https://blog.descarteslabs.com/advancing-the-science-of-soy-forecasting); [Corn forecasting](https://medium.com/descarteslabs-team/advancing-the-science-of-corn-forecasting-350603e3c57f); [AgFunderNews](https://agfundernews.com/descartes-raise); [HBS D3 case](https://d3.harvard.edu/platform-rctom/submission/descartes-labs-predicting-farmers-fortunes-from-space/)
- Orbital Insight: [home](https://www.orbitalinsight.com/); [Wikipedia](https://en.wikipedia.org/wiki/Orbital_Insight); [Fortune](https://fortune.com/2017/12/16/satellites-commodity-trading-world/); [Nanalyze](https://www.nanalyze.com/2017/01/orbital-insight-artificial-intelligence/)
- Gro Intelligence: [US Soy Yield Model](https://gro-intelligence.com/models/us-soybean-yield-forecast-model); [Agriculture](https://gro-intelligence.com/agriculture); [Inc. profile](https://www.inc.com/magazine/202011/kevin-j-ryan/sara-menker-gro-intelligence-female-founders-2020.html); [Columbia Magazine](https://magazine.columbia.edu/article/how-gro-intelligence-fighting-world-hunger-tech)
- Kpler: [Commodities](https://www.kpler.com/product/commodities); [Ag & Biofuels](https://www.kpler.com/market/agricultural-commodities-and-biofuels); [Supply & Demand](https://www.kpler.com/product/commodities/supply-demand)
- Vortexa: [home](https://www.vortexa.com/); [Cargo tracking](https://www.vortexa.com/feature/cargo-vessel-tracking-maps)
- USDA AMS Grain Transportation Report: [Datasets](https://www.ams.usda.gov/services/transportation-analysis/gtr-datasets); [Research](https://www.ams.usda.gov/services/transportation-analysis); [09-25-2025 issue](https://www.ams.usda.gov/sites/default/files/media/GTR09252025.pdf)
- Weather: [ECMWF IFS Wikipedia](https://en.wikipedia.org/wiki/Integrated_Forecast_System); [ECMWF model changes](https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model); [Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data); [ERA5-Land](https://www.ecmwf.int/en/era5-land); [ESSD paper](https://essd.copernicus.org/articles/13/4349/2021/); [Copernicus Soil Moisture](https://land.copernicus.eu/en/products/soil-moisture); [HESS paper](https://hess.copernicus.org/articles/27/1173/2023/hess-27-1173-2023.pdf); [Maxar WeatherDesk](https://www.maxar.com/products/weatherdesk); [Maxar Intelligence WeatherDesk](https://www.maxar.com/maxar-intelligence/products/weatherdesk); [Faster Forecasting](https://explore.maxar.com/faster-forecasts.html); [AWS HPC blog](https://aws.amazon.com/blogs/hpc/how-maxar-builds-short-duration-bursty-hpc-workloads-on-aws-at-scale/); [Atmospheric G2](https://atmosphericg2.com/)

Government and sell-side research:
- USDA: [WASDE](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report); [2026 Calendar](https://agsist.com/usda-calendar); [NASS Quick Stats](https://www.nass.usda.gov/Quick_Stats/); [NASS API](https://www.nass.usda.gov/developer/index.php); [Data.gov API](https://catalog.data.gov/dataset/quick-stats-agricultural-database-api); [FAS Weekly Export Sales catch-up](https://www.fas.usda.gov/programs/export-sales-reporting-program/weekly-export-sales-catch-schedule); [FAS Reporting Schedule](https://www.fas.usda.gov/newsroom/stakeholder-notice-daily-and-weekly-export-sales-reporting-schedule); [U.S. Export Sales](https://apps.fas.usda.gov/export-sales/esrd1.html); [China Oilseeds Annual](https://www.fas.usda.gov/data/china-oilseeds-and-products-annual-9); [GAIN GACC Suspension](https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=GACC+Announces+Suspension+of+Soybean+Shipments+from+Three+US+Entities_Beijing_China+-+People's+Republic+of_CH2025-0046.pdf)
- Brazil/Argentina: [CONAB 177.6 mt](https://www.global-agriculture.com/latam-agriculture/conab-estimating-2025-26-brazil-soybean-production-at-177-6-mt/); [CONAB record](https://www.brownfieldagnews.com/news/brazils-conab-forecasts-record-soybean-output-higher-exports/); [CONAB 166 mt](https://ocj.com/2024/12/conab-maintains-estimate-of-166-million-tons-for-brazilian-soybeans/); [BCR](https://www.bcr.com.ar/en); [BCR Mercado de Granos](https://www.bcr.com.ar/es/mercados/boletin-diario/mercado-de-granos); [Rosario Board of Trade](https://en.wikipedia.org/wiki/Rosario_Board_of_Trade)
- China: [Global Times 2025 imports](https://www.globaltimes.cn/page/202601/1353178.shtml); [China Customs](http://english.customs.gov.cn/); [Farmdoc Daily on China demand](https://farmdocdaily.illinois.edu/2025/12/can-china-reduce-soybean-import-demand-evaluating-soybean-meal-reduction-efforts.html)
- Sell-side: [StoneX Ag Reports](https://www.stonex.com/en/market-intelligence/agriculture-reports/); [StoneX Q3 2025 Outlook](https://www.stonex.com/en/thought-leadership/global-outlook-for-soybeans-corn-wheat-and-vegetable-oils-q3-2025/); [StoneX US Crop Surveys](https://www.stonex.com/en/thought-leadership/08-06-2025-us-crop-surveys-signal-pressure-on-wheat-and-soybean-markets/); [Hightower Report](https://www.hightowerreport.com); [Futures Research](https://www.futures-research.com/); [AgResource subscription](https://agresource.com/subscription/); [RealAgriculture — Grainfox/AgResource](https://www.realagriculture.com/2024/03/grainfox-partners-with-agresource-in-u-s-market-expansion/); [Pro Farmer](https://www.profarmer.com/); [MarketScreener — Crop Tour](https://www.marketscreener.com/news/futures-fall-as-crop-tour-finds-healthy-fields-daily-grain-highlights-ce7c51dddc81fe23); [MarketsWiki Allendale](https://www.marketswiki.com/wiki/Allendale,_Inc.); [CME Allendale](https://www.cmegroup.com/tools-information/find-a-broker/allendale-inc.html)

Quant stacks and tick stores:
- Tick DBs: [Wikipedia Kdb+](https://en.wikipedia.org/wiki/Kdb+); [timestored](https://www.timestored.com/kdb-guides/who-uses-kdb); [Medium kdb+ guide](https://medium.com/@tzjy/comprehensive-guide-how-hedge-funds-use-kdb-in-quantitative-trading-9638ef43bb86); [OneTick](https://www.onetick.com/); [OneTick Market Data](https://www.onetick.com/market-data); [QuantHouse HOD](https://quanthouse.com/hod/); [dxFeed futures](https://dxfeed.com/market-data/futures/)
- Backtesters/OSS: [Medium backtester comparison](https://medium.com/@trading.dude/battle-tested-backtesters-comparing-vectorbt-zipline-and-backtrader-for-financial-strategy-dee33d33a9e0); [QuantVPS](https://www.quantvps.com/blog/best-python-backtesting-libraries-for-trading); [QuantRocket](https://www.quantrocket.com/blog/backtest-speed-comparison); [Pytrade.org](https://github.com/PFund-Software-Ltd/pytrade.org); [ArcticDB](https://arcticdb.io/); [Man Group Arctic](https://www.man.com/technology/arctic-datascience-database); [HN ArcticDB](https://news.ycombinator.com/item?id=41309997); [man-group/arctic](https://github.com/man-group/arctic); [MongoDB Arctic PR](https://www.mongodb.com/company/newsroom/press-releases/man-ahl-arctic-open-source); [Medium DuckDB+Polars](https://medium.com/quant-factory/trading-data-analytics-part-2-top-momentum-using-duckdb-and-polars-39586d8a4cdb)

*Document timestamp: April 2026. Pricing estimates and vendor coverage current as of this date; all numeric figures should be treated as illustrative and confirmed against current vendor terms before use.*
