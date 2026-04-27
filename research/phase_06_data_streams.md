# Phase 06 — Data Streams for Pricing the Soybean Complex

## Abstract

A soybean market-making book consumes data on three clocks: microseconds (exchange microstructure), seconds-to-minutes (scheduled fundamentals and weather bulletins), and days-to-weeks (logistics, satellite, positioning). This catalog documents every materially useful stream for pricing ZS/ZM/ZL on intraday through multi-week horizons, naming the publisher, exact product, native format, access method, publication latency, update cadence, cost tier, and — crucially — the distinction between a feed that drives continuous quoting decisions and one that drives slower fair-value updates. The backbone is CME MDP 3.0 for the order book, the USDA release calendar (WASDE, Crop Progress, Export Sales, Grain Stocks, Prospective Plantings, Acreage, Grain Inspections) for U.S. fundamentals, CONAB/SECEX/BCBA/BCR for South America, China's GACC and MARA CASDE for demand, NOAA/ECMWF/NASA/Copernicus for weather and vegetation, USDA-AMS Grain Transportation Report and USACE LPMS for logistics, the CFTC COT suite for positioning, and a commercial alt-data layer (Kpler, MarineTraffic, Descartes, Gro, Planet, Barchart, DTN) layered on top. All citations are primary-source where available.

---

## 1. Master catalog

The streams below appear in the order discussed through the rest of this document. "Cost tier" is normalized as Free / Low (<$500/mo equivalent) / Mid ($500–$5,000/mo) / High (institutional five-figure/month and up).

| Name | Publisher | Access | Frequency | Latency | Cost Tier | Primary Use |
|---|---|---|---|---|---|---|
| CME MDP 3.0 (GLBX.MDP3) — ZS/ZM/ZL L1/L2 book, trades, amendments | CME Group | UDP multicast (colo); vendor re-distribution (Databento, Exegy, vendors) | tick-by-tick | microseconds | High (direct); Mid (via Databento) | Quote fair value, order-flow imbalance, MM inventory signal |
| CME Options on ZS/ZM/ZL — quotes, trades, Greeks surface | CME Group / QuikStrike / DataMine | Globex tick; EOD QuikStrike | tick-by-tick; EOD | microsecond; next-day | High / Mid | Vol surface, gamma management, event hedging |
| CME CVOL — 30-day implied volatility index, soybeans | CME Group | DataMine live streaming + EOD benchmark files | live + EOD | real-time | Mid (DataMine) | Vol regime filter, event premium tracking |
| CME End-of-Day Settlements & Reference Prices (ZS/ZM/ZL) | CME Group | Daily Bulletin PDF/CSV, datamine | daily | ~12:00 a.m. CT preliminary; 10 a.m. CT final next day | Free (PDF); Mid (datamine) | Margin, MtM, session carry |
| CME Daily Bulletin — volume, OI, block trades, EFPs | CME Group | cmegroup.com/dailybulletin PDFs | daily | preliminary EOD, final next business day | Free | Positioning, liquidity planning |
| WASDE | USDA WAOB | PDF / XML / Excel / CSV (historical) | monthly | 12:00 p.m. ET | Free | Scheduled-event pricing, S/D reset |
| Crop Progress | USDA NASS | PDF / CSV via Quick Stats; ESMIS | weekly Mon (Apr–Nov) | 4:00 p.m. ET | Free | Growing-season condition tracking |
| Weekly Export Sales (ESR) | USDA FAS | ESRQS web + API | weekly Thu | 8:30 a.m. ET | Free | Weekly demand surprise |
| Grain Inspections (FGIS) | USDA AMS/FGIS | FGIS online PDFs + AgTransport Socrata | weekly Mon | afternoon ET | Free | Real-time export flow validation |
| Prospective Plantings | USDA NASS | PDF / Quick Stats | annual last business day March | 12:00 p.m. ET | Free | New-crop acreage shock |
| Acreage | USDA NASS | PDF / Quick Stats | annual last business day June | 12:00 p.m. ET | Free | June-end acreage revision |
| Grain Stocks | USDA NASS | PDF / Quick Stats | quarterly (Jan/Mar/Jun/Sep) | 12:00 p.m. ET | Free | Old-crop stock surprise |
| NASS Quick Stats API | USDA NASS | REST / JSON-XML-CSV | continuous | n/a | Free (key) | Historical series access |
| CONAB Levantamento | CONAB (Brazil) | PDF + Excel | monthly | mid-month | Free | Brazil production track |
| SECEX / ComexStat | MDIC Brazil | Web portal + bulk download | weekly + monthly | 1–3 day | Free | Brazilian export volume |
| BCBA Panorama Agrícola Semanal | Bolsa de Cereales (Arg.) | PDF / web | weekly Thu 3 p.m. ART | same-day | Free | Argentine crop condition |
| BCR Informativo Semanal | Bolsa Comercio Rosario | PDF / web | weekly | same-day | Free | Argentine export line-up |
| China GACC monthly imports | GACC | Web release + FAS rebroadcast | monthly | ~3 weeks | Free | Chinese demand confirmation |
| MARA CASDE | China MARA | PDF | monthly ~10th | afternoon CST | Free | China S/D view |
| USDA FAS GAIN reports | USDA FAS | PDF via newgainapi | as-filed | 1–2 day | Free | Country attaché narrative |
| NOAA CPC 6–10 / 8–14 day outlook | NOAA CPC | GRIB / GIS / text | daily 3–4 p.m. ET | same-day | Free | Weather risk premium |
| GEFS ensemble | NOAA EMC / NOMADS | GRIB2 via NOMADS, S3 | 4×/day (00/06/12/18 UTC) | ~5 h post-cycle | Free | Probabilistic weather |
| ECMWF IFS / AIFS open data | ECMWF | GRIB2 via AWS/Azure/GCP/ECMWF | 4×/day | +2 h vs real-time | Free (open from Oct 2025) | Higher-skill medium-range |
| MODIS NDVI/EVI (MOD13Q1, MYD13Q1) | NASA LPDAAC / USDA IPAD | HDF5 / GeoTIFF | 16-day composite | 2–7 day | Free | Crop health anomaly |
| Copernicus Sentinel-2 L2A | ESA / Copernicus | SAFE / JPEG2000 | 5-day revisit | 1–3 day | Free | Field-level vegetation |
| NASA SMAP L3/L4 soil moisture | NASA NSIDC DAAC | HDF5 on Earthdata | daily / 3-hourly | 1–3 day (L3), hours (L4) | Free | Root-zone moisture state |
| U.S. Drought Monitor | NDMC / USDA / NOAA | GeoJSON / TopoJSON | weekly Thu | 8:30 a.m. ET | Free | Drought stress overlay |
| USDA Grain Transportation Report | USDA AMS | PDF / data download | weekly Thu | afternoon | Free | Barge, rail, ocean rates |
| USACE LPMS Lock Performance | USACE Institute for Water Resources | Web app, exports | near real time (30-min) | 30-min | Free | Mississippi/Illinois barge queue |
| Baltic Panamax / Supramax indices | Baltic Exchange | Member terminal / licensed redistribution | daily 13:00 London | same-day | Mid–High (license) | Freight cost for FOB/CIF |
| Kpler seaborne trade & AIS | Kpler | Web + GraphQL API | continuous AIS + daily cargo | minutes (AIS); 1 day (cargo) | High | Cargo flows, port queues |
| MarineTraffic AIS API | Kpler / MarineTraffic | REST | continuous | seconds-minutes | Low–Mid | Vessel positions, ETAs |
| CFTC Legacy + Disaggregated COT | CFTC | CSV/XML/RSS (publicreporting.cftc.gov) | weekly Fri 3:30 p.m. ET, Tue-as-of | 3 day | Free | Speculative positioning |
| CFTC Bank Participation Report | CFTC | PDF + CSV | monthly, first Fri after 3:30 p.m. ET | same-day | Free | Bank futures positioning |
| Barchart cmdty cash grain bids | Barchart | REST API (getGrainBids) | intraday | intraday | Low–Mid | Basis tape |
| DTN ProphetX / Markets Grain Bids REST | DTN | REST API | intraday | intraday | Mid | Elevator bid tape |
| Gro Intelligence crop models | Gro | Web + API | daily updates | hours | Mid–High | Yield nowcast |
| Descartes Labs yield forecast | Descartes Labs | Web + API | weekly (Tue) | 1 day | Mid–High | Yield nowcast |
| Planet PlanetScope imagery | Planet Labs | API | daily revisit | hours | High | 3 m field imagery |
| FX: DXY, USD/BRL, USD/ARS, USD/CNY | Vendors (Refinitiv/Bloomberg/ICE) | Terminal / API | tick-level | seconds | Mid–High | Cross-asset fair value |
| WTI / Brent / gasoil | CME/ICE | Tick data | continuous | ms | Mid–High | Soyoil/biofuel link |

Twenty-eight of the streams in this table link to a primary publisher URL in the References section at the end.

---

## 2. Market microstructure data

### 2.1 ZS / ZM / ZL Level 1 and Level 2, trades, amendments

The disseminated order book for CBOT soybean complex futures is the CME Market Data Platform 3.0 (MDP 3.0). MDP 3.0 is a dual-channel UDP multicast feed encoded with Simple Binary Encoding (SBE) against the FIX 5.0 SP2 schema. Every quote change, order add/amend/cancel, trade, security-definition, and statistics message is individually sequenced; a downstream consumer subscribes to the "Market By Price" (MBP, aggregated depth) channel for top-of-book through book depth, or the "Market By Order" (MBO, full granularity with order IDs) channel for queue-position tracking ([CME Group — Market Data Platform](https://www.cmegroup.com/market-data/distributor/market-data-platform.html)). MDP Premium layers full-depth MBO on top of MBP. The feed arrives in Aurora (CME's Chicago data center) with microsecond latency; raw consumption requires a cross-connect, a distributor license, and a conformant feed handler. Direct MDP access sits in the institutional five-to-six-figure monthly tier; Databento's re-distribution of the same feed as `GLBX.MDP3` is the standard prosumer alternative ([CME Group — Databento](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html)).

For a market-making engine the top-of-book feed and the incremental depth feed are not optional — these are the inputs to quote sign, inventory control, and queue-position estimation. Venue-native granularity matters because the CBOT grain matching engine implements FIFO with implied spread pricing; a quoter that cannot see order IDs cannot reason about its own queue position for outright bean/meal/oil trades against the implied crush.

### 2.2 Options chain, Greeks, and implied volatility surface

Options on ZS, ZM, and ZL — standard monthly, short-dated new-crop (SDNC), and weekly Friday expiries from February through August on the new crop — disseminate through the same MDP channels, with a separate options product complex. Weekly options on the front futures month exist where a standard option does not already expire that week ([CME — Agricultural Short-Term Options](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)). Greeks and the full implied-vol surface are not exchange-published as a standalone feed; practitioners compute them off raw option prices, or subscribe to CME's QuikStrike / DataMine for EOD vol surfaces, or consume a vendor (Cboe Hanweck, Bloomberg OVML, CQG options analytics). The CME Group Volatility Index family (CVOL) publishes a 30-day implied-volatility benchmark for ZS, ZM, and ZL, derived from a deep OTM-weighted formula against CBOT option prices; it is disseminated both as an end-of-day benchmark file and as an intraday streaming value via CME DataMine ([CME — CME Group Volatility Indexes (CVOL)](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html)).

### 2.3 End-of-day settlements and reference prices

CME settlement prices are computed under Rule 813 (VWAP of a defined settlement window), posted to the CME Settlements page immediately after close, and included in the Preliminary Daily Bulletin that updates at ~12:00 a.m. CT the next calendar day; the Final Daily Bulletin — the canonical source for cleared open interest and post-trade adjustments — updates at 10:00 a.m. CT the following business day ([CME — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html); [CME — Soybean Futures Settlements](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.settlements.html)).

### Latency vs. value for market making

Microstructure data is the only category where latency is the value. A quoter cannot lean on a book view that is 100 ms stale without donating spread to faster counterparties. Settlements are scheduled events — their information value is compressed into the settlement window itself and spills into overnight gap risk; by 10 a.m. CT the next day they are stale for quoting and useful only for risk and margin.

---

## 3. Exchange reference and reports

The CME **Daily Bulletin** (`cmegroup.com/dailybulletin`) publishes, by exchange and by product group, the session's opening range, high, low, settlement, change, volume (Globex/ClearPort/Open Outcry split), and open interest by expiry, including block trades, EFPs, and exchange-of-futures-for-risk ([CME — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html); [CME — Volume & Open Interest Reports](https://www.cmegroup.com/market-data/volume-open-interest.html); [2026 Section 03 Agricultural Futures Daily Bulletin PDF](https://www.cmegroup.com/daily_bulletin/current/Section03_Agricultural_Futures.pdf)). The preliminary Volume & Open Interest report updates end-of-day with final figures the following morning — typical soybean daily volume runs 200,000+ contracts with peaks in open interest near 900,000. These reports are free but PDF-first; serious consumers license the machine-readable datamine equivalents or pull from a vendor.

### Latency vs. value for market making

The Daily Bulletin is a reconciliation input, not a quoting input. Its value is in calibration — spotting unreported blocks or EFPs that printed "off-feed," and reconciling OI changes against the market-maker's own flow to estimate whether the street was a net buyer or net seller of contracts that day.

---

## 4. USDA fundamentals (US-centric)

USDA's release calendar is the scheduled information backbone of the U.S. complex.

**WASDE.** The World Agricultural Supply and Demand Estimates publishes monthly at 12:00 p.m. ET, typically mid-month. It delivers supply-and-use balance sheets for U.S. and world wheat, rice, coarse grains, oilseeds, and cotton; formats include PDF, XML, Excel, plus a historical-release consolidated CSV updated the day after release. Subscribers receive a GovDelivery alert keyed to the WAOB distribution list ([USDA — WASDE Report](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)).

**Crop Progress.** Released weekly by NASS on Mondays at 4:00 p.m. ET from April through November, it reports percent-planted, percent-emerged, percent-blooming, percent-setting-pods, percent-dropping-leaves, percent-harvested, and state-level condition ratings for soybeans, corn, cotton, wheat, and other major crops ([USDA NASS — National Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/)). Condition ratings are available historically through Quick Stats.

**Weekly Export Sales (ESR).** USDA FAS releases the weekly Export Sales Report every Thursday at 8:30 a.m. ET, reflecting the Friday-through-Thursday reporting week ending the prior Thursday; exporters report by 11:59 p.m. ET the Monday after the week closes. Commodities covered include wheat, corn, grain sorghum, barley, oats, rye, rice, soybeans, soybean cake and meal, soybean oil, cotton and cotton products, cattle hides, beef, and pork. FAS operates the Export Sales Reporting Query System (ESRQS) that provides a public REST API for the weekly data without registration ([USDA FAS — Export Sales Reporting Program](https://www.fas.usda.gov/programs/export-sales-reporting-program); [USDA FAS — ESR query app](https://apps.fas.usda.gov/export-sales/esrd1.html)).

**Grain Inspections.** USDA AMS's Federal Grain Inspection Service (FGIS) publishes weekly totals of grain inspected or weighed for export on Mondays, by port region and destination country; it is considered the "near real time" check on the ESR since inspection equals physical loading ([USDA AMS — FGIS Data and Statistics](https://www.ams.usda.gov/resources/fgis-data-and-statistics); [FGIS Export Grain Report portal](https://fgisonline.ams.usda.gov/exportgrainreport/)).

**Prospective Plantings.** NASS releases on the last business day of March at 12:00 p.m. ET. The 2026 release (March 31) included planting intentions from a survey of ~74,000 operators during the first two weeks of March ([USDA NASS — 2026 Prospective Plantings release](https://www.nass.usda.gov/Newsroom/2026/03-31-2026.php); [Prospective Plantings 03/31/2026 PDF](https://release.nass.usda.gov/reports/pspl0326.pdf)).

**Acreage.** The last-business-day-of-June release at 12:00 p.m. ET updates intentions with surveyed planted acreage ([Acreage 06/30/2025 PDF](https://release.nass.usda.gov/reports/acrg0625.pdf)).

**Grain Stocks.** Quarterly, last business day of January, March, June, and September, released at 12:00 p.m. ET, with reference dates of December 1, March 1, June 1, September 1. State- and position-level breakdown (on-farm vs. off-farm) for soybeans, corn, wheat, sorghum, oats, barley, flaxseed, canola, rapeseed, rye, sunflower, safflower, and mustard ([USDA NASS — Grain Stocks survey](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Off-Farm_Grain_Stocks/index.php); [Grain Stocks 01/2026 PDF](https://esmis.nal.usda.gov/sites/default/release-files/795726/grst0126.pdf)).

**NASS Quick Stats API.** The programmatic back-door into virtually every NASS series. The REST endpoint at `quickstats.nass.usda.gov/api` supports JSON, XML, and CSV; an email-registered API key is required; the single-request hard cap is 50,000 rows. The discovery endpoints `/get_param_values/` and `/get_counts/` let a client enumerate parameter values and pre-check row counts before issuing the main query ([NASS Quick Stats API](https://quickstats.nass.usda.gov/api)). **What it doesn't cover:** near-real-time WASDE balance-sheet numbers (those come from WAOB, not NASS), ESR (FAS publishes), CFTC COT, and export vessel line-ups.

### Latency vs. value for market making

All of the above are scheduled events. The value-per-second of these data products is ~∞ at the release minute and rapidly decays. A market-making book typically widens spreads or pulls quotes through the 30-second window around release time, then tightens within seconds after the print propagates. Away from release windows, these datasets are slow inputs into fair value, not quoting signals.

---

## 5. South American fundamentals

**Brazil — CONAB.** The Companhia Nacional de Abastecimento publishes monthly *Levantamento* crop survey reports, usually between the 8th and 15th of each month, covering planted area, expected yield, and production for soybeans, corn, wheat, cotton, rice, and other Brazilian crops. Reports are free, distributed as Portuguese-language PDF plus accompanying Excel tables. A January 15, 2026 release was followed by February 12 and March 13 ([CONAB reporting schedule as summarized in Brownfield Ag News, March 2026](https://www.brownfieldagnews.com/news/not-many-changes-to-brazil-corn-soybean-estimates-by-conab/)).

**Brazil — SECEX / ComexStat.** The Secretaria de Comércio Exterior (SECEX) within the Ministério do Desenvolvimento, Indústria, Comércio e Serviços publishes customs-based export data at [comexstat.mdic.gov.br](http://comexstat.mdic.gov.br/en/home), with soybean and soymeal shipment volumes broken down by destination and port. A weekly "parcial" preview is published, and monthly consolidated tables are finalized around the 3rd of the following month. Latency on the weekly is ~1–3 days.

**Brazil — state-level ag bureaus.** IMEA (Mato Grosso), Deral (Paraná), and Abiove (crushers' association) publish state-level and processor-level statistics more granular than CONAB; they are the practitioner's preferred inputs for short-run planting-progress and crushing-margin calls.

**Argentina — BCBA Panorama Agrícola Semanal (PAS).** Published every Thursday at 3 p.m. Argentina time (ART) as a free PDF, the *Panorama Agrícola Semanal* from the Bolsa de Cereales in Buenos Aires tracks weekly sowing and harvest progress, crop condition (% óptimo/bueno), and estimated area for the full Argentine campaign ([Bolsa de Cereales — Estimaciones Agrícolas](https://www.bolsadecereales.com/estimaciones-agricolas)).

**Argentina — Bolsa de Comercio de Rosario (BCR).** The Rosario Board publishes a weekly "Informativo Semanal" covering soybean complex price commentary, an export-line-up survey for the Up-River ports (Timbúes, Rosario, San Lorenzo), and seasonal campaign estimates; its sister property GEA publishes monthly production forecasts ([BCR — Informativo Semanal weekly news index](https://www.bcr.com.ar/en)).

### Latency vs. value for market making

From roughly November through June, South American data beats U.S. fundamentals in marginal information value — a drought scare in Rio Grande do Sul in January is the single largest event-risk input to ZS quotes that month. BCBA Thursdays and BCR weeklies operate on a cadence similar to USDA Crop Progress and can be treated symmetrically: widen at release, mean-revert post-release.

---

## 6. Chinese demand indicators

**GACC monthly customs imports.** The General Administration of Customs of the People's Republic of China publishes monthly import volumes for HS-code-level categories including soybeans (HS 1201), soymeal (1208), and soy oil (1507) approximately three weeks after month-end. Breakdowns by country of origin follow in a second release. USDA FAS frequently rebroadcasts GACC data in GAIN-Oilseeds reports, shortening the practitioner lag ([USDA FAS — China GACC suspension of soybean shipments announcement](https://www.fas.usda.gov/data/china-gacc-announces-suspension-soybean-shipments-three-us-entities)).

**MARA CASDE.** The China Agriculture Supply and Demand Estimate is published monthly around the 10th by the Ministry of Agriculture and Rural Affairs, Chinese analogue to WASDE, with Chinese soybean area, yield, production, crush, imports, and ending stocks. Released as a Chinese-language PDF plus English summary; typical latency less than one day after the release window.

**State-reserve auctions.** Sinograin's periodic soybean reserve sales and purchases are announced via Chinese-language press releases, typically two-to-seven days ahead of the auction date; auction results are posted the following day. They are the key marginal-tonnage signal for state-controlled demand.

**USDA FAS GAIN — China Oilseeds and Products.** FAS's Beijing Attaché publishes a twice-annual Oilseeds and Products *Annual* and a semi-annual *Update*, with PSD tables and narrative. The reports are available via the FAS GAIN report portal and are often the most timely public source for GACC reconciliation and CASDE summary ([USDA FAS GAIN — Oilseeds and Products Annual, China, Beijing, CH2025-0055](https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Oilseeds+and+Products+Annual_Beijing_China+-+People%27s+Republic+of_CH2025-0055)).

### Latency vs. value for market making

China releases are lower-frequency than USDA but move the complex meaningfully. The multi-week lag on GACC imports is the binding constraint on their value for quoting: by release, the market already knows the print approximately from barge-observation alt-data (Kpler/MarineTraffic). The *residual* — the GACC number minus the AIS-inferred cargo count — is the informative signal.

---

## 7. Weather

### 7.1 NOAA — CPC short-to-medium range

The NOAA Climate Prediction Center issues the 6–10 day and 8–14 day outlooks daily between 3 and 4 p.m. ET as temperature-probability and precipitation-probability maps, a lines-only textual representation, GIS shapefiles, and a prognostic discussion ([NOAA CPC — 6–10 day outlook page](https://www.cpc.ncep.noaa.gov/products/predictions/610day/)). Corresponding week-3-and-4 outlooks are issued weekly.

### 7.2 NOAA — GEFS ensemble

The Global Ensemble Forecast System v12 runs four times a day (00, 06, 12, 18 UTC) with 31 members (1 control, 30 perturbed) at ~25 km horizontal resolution, 64 vertical levels, forecasts to 16 days on 06/12/18 UTC cycles and to 35 days on the 00 UTC cycle ([NOAA EMC — GEFS](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gefs.php); [NCEP NOMADS GEFS product inventory](https://www.nco.ncep.noaa.gov/pmb/products/gens/); [NOAA Open Data on AWS — GEFS](https://registry.opendata.aws/noaa-gefs/)). Free via NOMADS and AWS S3 in GRIB2.

### 7.3 ECMWF — IFS, AIFS, and ENS

As of 1 October 2025, ECMWF made its entire real-time forecast catalogue open at 0.25° resolution under CC-BY-4.0, with 9 km high-resolution output to follow at a 2-hour latency. The deterministic IFS runs four times daily, with the first 90 forecast hours at hourly, 3-hourly to 144 h, then 6-hourly. Open-data is replicated to AWS, Azure, and GCP for low-friction retrieval; AIFS (AI-driven) data release with no additional latency relative to production ([ECMWF — Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data); [ECMWF Confluence — Open data: real-time forecasts from IFS and AIFS](https://confluence.ecmwf.int/display/DAC/ECMWF+open+data%3A+real-time+forecasts+from+IFS+and+AIFS); [ECMWF news, 2025 — entire real-time catalogue open](https://www.ecmwf.int/en/about/media-centre/news/2025/ecmwf-makes-its-entire-real-time-catalogue-open-all); [AWS Open Data — ECMWF real-time forecasts](https://registry.opendata.aws/ecmwf-forecasts/)). ECMWF ENS, the 51-member ensemble, and ERA5 reanalysis are also part of the open bundle.

### 7.4 Vegetation indices — NDVI / EVI

**MODIS MOD13Q1 / MYD13Q1** — 16-day composite NDVI and EVI at 250 m resolution from the Terra (MOD) and Aqua (MYD) platforms, phased eight days apart to yield an effective 8-day time step. Data are stored as HDF5 and GeoTIFF and distributed through the NASA LP DAAC; USDA's IPAD Crop Explorer re-packages the same data with masks tuned to crop-region polygons ([NASA Earthdata — MOD13Q1 v061](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061); [USDA FAS IPAD — Crop Explorer](https://ipad.fas.usda.gov/glam.aspx)).

**Copernicus Sentinel-2 L2A** — ESA's 10–20 m optical imagery with a 5-day revisit (both A+B operational) provides field-scale NDVI. Free and open under Copernicus licensing; accessible via the Copernicus Data Space Ecosystem ([ESA — Plant health](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Plant_health)).

### 7.5 Soil moisture

**NASA SMAP L3/L4** — L3 products are daily 36 km or enhanced 9 km composites of radiometer-retrieved surface soil moisture in EASE-Grid 2.0, distributed as HDF5 through the NSIDC DAAC; L4 products assimilate L3 into a land-surface model to produce 3-hourly root-zone estimates at 9 km. Earthdata Login required. Latency from acquisition to product availability is a few days for L3 and within hours for L4 ([NSIDC — SPL3SMP Radiometer Global Daily 36 km, v9](https://nsidc.org/data/spl3smp/versions/9); [NSIDC — SPL4SMGP L4 Global 3-hourly 9 km, v6](https://nsidc.org/data/spl4smgp/versions/6)).

**USDA / NDMC / NOAA — U.S. Drought Monitor** — issued Thursdays at 8:30 a.m. ET, gridded data files on drought.gov in GeoJSON and TopoJSON; overlays by county and by crop are published through the Drought and Agriculture topic page ([Drought.gov — Gridded USDM](https://www.drought.gov/data-maps-tools/gridded-us-drought-monitor-usdm); [USDM current map](https://droughtmonitor.unl.edu/)).

### Latency vs. value for market making

Weather is the highest-impact fundamental continuously during the U.S. growing season (June–August) and South American one (November–March). Unlike scheduled USDA reports, weather updates arrive four times a day and change fair value between releases. GEFS and ECMWF ensemble members are the inputs to yield-sensitive scenario modeling; the CPC outlooks compress the ensemble into a set of probability contours that traders read as a sentiment signal. SMAP and drought-monitor data shift weekly; NDVI shifts every 8–16 days. For a market-making quoter, the useful derivative is the rate of change of weather-driven fair value, not the raw forecast fields — a rapid deterioration in the 6–10 day precipitation outlook during pod-fill justifies widening the quoted volatility by realized sigma × empirical-beta.

---

## 8. Logistics and physical flow

**USDA AMS Grain Transportation Report.** Published weekly by the USDA Agricultural Marketing Service on Thursdays, the GTR compiles barge rates (by St. Louis, Mid-Mississippi, and Illinois River tariff benchmarks), railroad grain carloadings, secondary railcar auction market, and ocean freight for dry-bulk grain movements ([USDA AMS — Grain Transportation Report hub](https://www.ams.usda.gov/services/transportation-analysis/gtr); the April 17, 2025 sample issue published on the weekly cycle confirms Thursday delivery).

**USACE Lock Performance Monitoring System.** The Lock Performance Monitoring System, maintained by the Institute for Water Resources, publishes lock-by-lock vessel transit, tonnage, and delay data for Corps-operated locks. The public LPMS web portal (corpslocks.usace.army.mil) updates at 30-minute cadence; NDC maintains the historical archive. Tonnage rollups are reported by commodity including grain; lock closure announcements and delay times are the practitioner's direct window into Illinois/Mississippi River bottleneck conditions that drive Gulf basis ([USACE — Corps Locks LPMS web portal](https://corpslocks.usace.army.mil/lpwb/f?p=121); [USACE IWR — NDC Locks](https://www.iwr.usace.army.mil/About/Technical-Centers/NDC-Navigation-and-Civil-Works-Decision-Support/NDC-Locks/); [Data.gov — Corps Locks dataset](https://catalog.data.gov/dataset/corps-locks/resource/1cd34216-2824-46d8-8a06-abe46cbc1159)).

**Baltic Exchange dry indices.** The Baltic Panamax Index (BPI) and Baltic Supramax Index (BSI) are published once per London business day (~13:00 BST) by the Baltic Exchange and weight professional shipbroker panel assessments across route baskets. The BPI is composed of five Panamax routes weighted by a 82,500 DWT vessel reference; the BSI weights 11 Supramax routes on a 58,000 DWT reference ([Baltic Exchange — Dry Services](https://www.balticexchange.com/en/data-services/market-information0/dry-services.html); [Baltic Exchange — Indices](https://www.balticexchange.com/en/data-services/market-information0/indices.html)). Redistribution requires license; end-of-day snapshots flow to Bloomberg, LSEG Workspace, and specialist shipping desks.

**AIS-derived port queue data.** Kpler and MarineTraffic (both now part of Kpler) operate global AIS ingestion from a network of 13,000+ terrestrial + satellite receivers covering 350,000+ vessels, exposed via REST or GraphQL APIs for positions, historical tracks, port events, predictive ETAs, and — for Kpler specifically — commodity-tagged cargo lines for soybeans, soymeal, and soy oil with loading/discharge port assignment ([Kpler — KplerAIS coverage overview](https://www.kpler.com/product/maritime/kplerais); [MarineTraffic — API services](https://support.marinetraffic.com/en/articles/9552659-api-services); [MarineTraffic — AIS API documentation](https://servicedocs.marinetraffic.com/)). Panamax and Supramax queue buildups off Paranaguá, Santos, Rosario, and the Lower Mississippi feed directly into basis models.

### Latency vs. value for market making

Logistics data is a slow input to a fair-value model and a fast input to basis-trade models. The GTR is weekly, which is appropriate for tracking transportation-cost cycles; USACE LPMS is near-real-time, which is appropriate for reacting to lock closures; Baltic rates are daily and drive the FOB/CIF arbitrage that sets the U.S. vs Brazilian export-basis relationship; AIS is continuous and drives the 1-to-3-day-ahead cargo nowcast of GACC imports. For a CBOT quoter, none of this is microsecond-critical, but it is the primary input to intraday basis moves that show up as spread-contract pressure.

---

## 9. Positioning

**CFTC Commitments of Traders — Legacy and Disaggregated.** Released every Friday at 3:30 p.m. ET with data as of the prior Tuesday's close. Legacy format splits reportables into non-commercial, commercial, and non-reportable; Disaggregated (since June 2006) separates Producer/Merchant/Processor/User, Swap Dealers, Managed Money, and Other Reportables. Formats include CSV, XML, RDF, TSV, RSS, and HTML through the CFTC's Public Reporting Environment ([CFTC — Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm); [CFTC — Disaggregated Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedExplanatoryNotes/index.htm); [CFTC — Ag Disaggregated Futures Short Report](https://www.cftc.gov/dea/futures/ag_sf.htm)). Catch-up schedules are issued when federal holidays push the release.

**CFTC Bank Participation Report.** Monthly, first Friday after 3:30 p.m. ET, data as of the first Tuesday of each month (adjusted for federal holidays). Separate futures-participation and options-participation datasets by bank type ([CFTC — Bank Participation Reports](https://www.cftc.gov/MarketReports/BankParticipationReports/index.htm)).

### Latency vs. value for market making

The COT is a three-day-delayed snapshot — it is useful for a weekly positioning view and for calibrating how "stretched" managed-money length is relative to historical distribution, not for quoting decisions. Its highest marginal value is in unusual weeks (post-WASDE extremes, weather-shock reversals) where it confirms or disconfirms the market-maker's inferred counterparty population.

---

## 10. Macro cross-asset

A soybean market-maker consumes a set of cross-asset feeds through the same Bloomberg/LSEG/ICE terminals that price the complex.

**FX.** DXY (dollar index) and USD/BRL are the two biggest fair-value knobs — a stronger USD makes U.S. soy more expensive in local currency to Chinese buyers and cheapens Brazilian soy in dollar terms. USD/ARS (official and "blue") is chronically volatile and captures Argentine producer-selling behavior. USD/CNY is the pass-through for Chinese buying power. FX is tick-level via interbank or vendor feeds.

**Energy.** WTI and Brent (NYMEX CL, ICE Brent), ULSD / gasoil, and biodiesel tags drive soyoil via the biodiesel feedstock link. The oil-share of processor margin is tied to the spread between soybean oil and heating oil (and increasingly renewable-diesel tags). Energy tick data is institutional-tier and flows through the same MDP-equivalent feeds on NYMEX/ICE.

**Commodity index benchmarks.** S&P GSCI and Bloomberg Commodity Index weights are disclosed annually; roll windows ("Goldman roll," BCOM roll) run the 5th through 9th business day of each roll month. Index weight disclosures and roll schedules are published by S&P DJI and Bloomberg Indices and consumed through the terminal ([Bloomberg — BCOM 2026 Target Weights](https://www.bloomberg.com/company/press/bloomberg-commodity-index-2026-target-weights-announced/); see Phase 01 references).

**Ag-ETF flows.** SOYB, DBA, and CORN flow data (creations/redemptions) is disclosed daily by the fund sponsors (Teucrium, Invesco) and aggregated by fund-flow vendors; these are a proxy for retail commodity interest.

### Latency vs. value for market making

Macro cross-asset is a continuous input to fair value but at a smaller beta than USDA / weather / positioning. DXY is the biggest single cross-asset coefficient. In quiet windows, macro moves dominate; in U.S. weather markets, macro beta collapses to near zero.

---

## 11. Alternative data

**Satellite crop health aggregators.** Gro Intelligence produces yield-model nowcasts for country-crop pairs including US soybeans and Argentine soybeans with daily model updates and a data platform + API surface. Descartes Labs updates its U.S. soybean yield forecast weekly on Tuesdays during the growing season, combining satellite, weather, and machine-learning ingredients over a multi-petabyte archive ([Descartes Labs — Advancing the science of soy forecasting](https://medium.com/descarteslabs-team/advancing-the-science-of-soy-forecasting-f399bae42b78); [Planet — Start the Growing Season Off Strong with Satellite Data](https://www.planet.com/pulse/start-the-growing-season-off-strong-with-satellite-data/); [Planet — CornCaster yield forecasting](https://www.planet.com/pulse/corncaster-how-planets-yield-forecasting-solution-is-helping-agriculturists-and-economists-get-ahead-of-this-years-harvest/)). Planet Labs' PlanetScope constellation delivers 3 m daily revisit globally, ingested by Descartes and others as a high-resolution input.

**Truck and rail traffic proxies.** The U.S. AAR weekly rail carloadings release (Thursdays) includes the "Grain" commodity category. State-level trucking indices (Mato Grosso IMEA, Rosario BCR surveys on truck arrivals at Up-River terminals) round out the coverage.

**Scraped processor / elevator bids.** Barchart's `getGrainBids` API exposes intraday cash grain bids by ZIP code, county, FIPS, and commodity (including ZS — all kinds of soybeans) with elevator name, bid type (Export / Processor / River / Terminal / Barge Loading), and Unix timestamp for when the basis was last updated ([Barchart OnDemand — Cash Grain Bid API](https://www.barchart.com/ondemand/api/getGrainBids)). DTN's Markets Grain Bids REST API covers elevator, FIPS region, and USDA region detail ([DTN Content Services — Markets Grain Bids REST API](https://cs-docs.dtn.com/api/rest-api-for-markets-grain-bids)). Both are Mid-tier priced and are the market-maker's input to basis-aware quoting — a cash bid that widens sharply ahead of a futures move is often informative about upcoming pit flow.

### Latency vs. value for market making

Alt-data is a "texture" layer that surfaces information the official feeds cannot. In a normal week, its marginal value is low; in a stress week (a port closure, a drought call, a rail embargo), it is where the market learns a move is coming before the official print. Because alt-data is expensive, it is usually consumed at the research desk and signal-distilled before being wired into the quoting engine.

---

## Key takeaways

- Microstructure data (CME MDP 3.0) is the only stream where microsecond latency is the value; it is consumed continuously. Everything else is a scheduled or episodic input to fair value that matters most at release and decays quickly thereafter.
- USDA owns the scheduled U.S. information calendar. WASDE (monthly), Crop Progress (weekly Mon 4 p.m. ET), ESR (weekly Thu 8:30 a.m. ET), Grain Inspections (weekly Mon), Grain Stocks (quarterly, 12 p.m. ET), Prospective Plantings (Mar 31 noon ET), and Acreage (Jun 30 noon ET) are free, structured, and available via PDF, Quick Stats API, or ESRQS API.
- South America has its own equally disciplined calendar: CONAB mid-month, SECEX weekly parcial + monthly final, BCBA Thursdays 3 p.m. ART, BCR weekly. Between November and June the South American cycle often supplies the binding weather signal.
- Chinese demand data (GACC imports, MARA CASDE, FAS GAIN-Oilseeds) lags roughly three weeks. AIS-based cargo tracking (Kpler, MarineTraffic) is the faster analog practitioners use to get ahead of the official release.
- Weather is the single largest continuous fundamental input during U.S. and South American growing seasons. NOAA CPC, GEFS, ECMWF IFS/AIFS/ENS, MODIS NDVI, Sentinel-2, SMAP, and the U.S. Drought Monitor are all free with varying latency and resolution; ECMWF's October 2025 open-data transition materially lowered the cost of high-skill medium-range inputs.
- Logistics and physical flow (AMS GTR, USACE LPMS, Baltic indices, Kpler) are the primary drivers of basis and the export-parity calculations that anchor CBOT-vs-FOB Santos / FOB Up-River price relationships.
- CFTC COT is useful for weekly positioning calibration, not real-time quoting. COT + Bank Participation together reveal bank and managed-money exposure trends at a 3-day delay.
- Macro cross-asset (DXY, USD/BRL, WTI/Brent, BCOM/GSCI index flows) sets the slow background; its beta rises outside U.S. weather-market windows and collapses during them.
- Alt-data (Gro, Descartes, Planet, Barchart, DTN) is a research-desk input first, quoting input second. It earns its cost when it provides early warning that then shows up in the official data.
- The practical pipeline architecture that Phase 03 described — MDP-3.0 feed handler + daily USDA PDF parsers + weekly SECEX/BCBA/BCR + 6-hourly ECMWF/GEFS + daily Baltic + continuous AIS + weekly COT + intraday cash-bid API — is the minimum complete set for a soybean market-making desk.

---

## References

- [CME Group — Market Data Platform](https://www.cmegroup.com/market-data/distributor/market-data-platform.html)
- [CME Group — Databento integration](https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/databento.html)
- [CME Group — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html)
- [CME Group — Volume & Open Interest Reports](https://www.cmegroup.com/market-data/volume-open-interest.html)
- [CME Group — Soybean Futures Settlements](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.settlements.html)
- [CME Group — Agricultural Short-Term Options](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)
- [CME Group — CME Group Volatility Indexes (CVOL)](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html)
- [CME Group — Daily Bulletin Section 03 Agricultural Futures (PDF)](https://www.cmegroup.com/daily_bulletin/current/Section03_Agricultural_Futures.pdf)
- [USDA — WASDE Report](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)
- [USDA NASS — National Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/)
- [USDA NASS — Grain Stocks survey](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Off-Farm_Grain_Stocks/index.php)
- [USDA NASS — Grain Stocks January 2026 PDF](https://esmis.nal.usda.gov/sites/default/release-files/795726/grst0126.pdf)
- [USDA NASS — Prospective Plantings 03/31/2026](https://release.nass.usda.gov/reports/pspl0326.pdf)
- [USDA NASS — 2026 Prospective Plantings press release](https://www.nass.usda.gov/Newsroom/2026/03-31-2026.php)
- [USDA NASS — Acreage 06/30/2025 PDF](https://release.nass.usda.gov/reports/acrg0625.pdf)
- [USDA NASS — Publications index](https://www.nass.usda.gov/Publications/)
- [USDA NASS — Quick Stats API](https://quickstats.nass.usda.gov/api)
- [USDA FAS — Export Sales Reporting Program](https://www.fas.usda.gov/programs/export-sales-reporting-program)
- [USDA FAS — ESR query app](https://apps.fas.usda.gov/export-sales/esrd1.html)
- [USDA FAS — GAIN Oilseeds & Products Annual, China 2025](https://apps.fas.usda.gov/newgainapi/api/Report/DownloadReportByFileName?fileName=Oilseeds+and+Products+Annual_Beijing_China+-+People%27s+Republic+of_CH2025-0055)
- [USDA FAS — China GACC soybean shipments announcement](https://www.fas.usda.gov/data/china-gacc-announces-suspension-soybean-shipments-three-us-entities)
- [USDA FAS IPAD — Crop Explorer](https://ipad.fas.usda.gov/glam.aspx)
- [USDA AMS — FGIS Data and Statistics](https://www.ams.usda.gov/resources/fgis-data-and-statistics)
- [USDA AMS — Federal Grain Inspection Service](https://www.ams.usda.gov/about-ams/programs-offices/federal-grain-inspection-service)
- [USDA AMS FGIS — Export Grain Report portal](https://fgisonline.ams.usda.gov/exportgrainreport/)
- [USDA AMS — Grain Transportation Report hub](https://www.ams.usda.gov/services/transportation-analysis/gtr)
- [NOAA CPC — 6–10 day outlook](https://www.cpc.ncep.noaa.gov/products/predictions/610day/)
- [NOAA EMC — GEFS](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gefs.php)
- [NCEP NOMADS — GEFS product inventory](https://www.nco.ncep.noaa.gov/pmb/products/gens/)
- [AWS Open Data — NOAA GEFS](https://registry.opendata.aws/noaa-gefs/)
- [ECMWF — Open data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [ECMWF Confluence — Open data: real-time forecasts from IFS and AIFS](https://confluence.ecmwf.int/display/DAC/ECMWF+open+data%3A+real-time+forecasts+from+IFS+and+AIFS)
- [ECMWF news — entire real-time catalogue open (2025)](https://www.ecmwf.int/en/about/media-centre/news/2025/ecmwf-makes-its-entire-real-time-catalogue-open-all)
- [AWS Open Data — ECMWF real-time forecasts](https://registry.opendata.aws/ecmwf-forecasts/)
- [NASA Earthdata — MOD13Q1 v061](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061)
- [NASA MODIS — Vegetation Index Products (NDVI/EVI)](https://modis.gsfc.nasa.gov/data/dataprod/mod13.php)
- [ESA — Sentinel-2 Plant Health](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Plant_health)
- [Copernicus — Sentinel-2 for Agriculture](https://www.copernicus.eu/en/sentinel-2-agriculture)
- [NSIDC — SMAP L3 Radiometer Global Daily 36 km v9](https://nsidc.org/data/spl3smp/versions/9)
- [NSIDC — SMAP L4 Global 3-hourly 9 km v6](https://nsidc.org/data/spl4smgp/versions/6)
- [Drought.gov — Gridded USDM](https://www.drought.gov/data-maps-tools/gridded-us-drought-monitor-usdm)
- [U.S. Drought Monitor current map](https://droughtmonitor.unl.edu/)
- [USACE — Corps Locks LPMS web portal](https://corpslocks.usace.army.mil/lpwb/f?p=121)
- [USACE Institute for Water Resources — NDC Locks](https://www.iwr.usace.army.mil/About/Technical-Centers/NDC-Navigation-and-Civil-Works-Decision-Support/NDC-Locks/)
- [Data.gov — Corps Locks dataset](https://catalog.data.gov/dataset/corps-locks/resource/1cd34216-2824-46d8-8a06-abe46cbc1159)
- [Baltic Exchange — Dry Services](https://www.balticexchange.com/en/data-services/market-information0/dry-services.html)
- [Baltic Exchange — Indices](https://www.balticexchange.com/en/data-services/market-information0/indices.html)
- [Kpler — KplerAIS coverage overview](https://www.kpler.com/product/maritime/kplerais)
- [MarineTraffic — API services](https://support.marinetraffic.com/en/articles/9552659-api-services)
- [MarineTraffic — AIS API documentation](https://servicedocs.marinetraffic.com/)
- [CFTC — Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [CFTC — Disaggregated Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/DisaggregatedExplanatoryNotes/index.htm)
- [CFTC — Ag Disaggregated Futures Short Report](https://www.cftc.gov/dea/futures/ag_sf.htm)
- [CFTC — Bank Participation Reports](https://www.cftc.gov/MarketReports/BankParticipationReports/index.htm)
- [Bolsa de Cereales (Argentina) — Estimaciones Agrícolas](https://www.bolsadecereales.com/estimaciones-agricolas)
- [Bolsa de Comercio de Rosario (BCR) — English landing](https://www.bcr.com.ar/en)
- [Barchart OnDemand — Cash Grain Bid API](https://www.barchart.com/ondemand/api/getGrainBids)
- [Barchart OnDemand — USDA Grain Prices API](https://www.barchart.com/ondemand/api/getUSDAGrainPrices)
- [DTN Content Services — Markets Grain Bids REST API](https://cs-docs.dtn.com/api/rest-api-for-markets-grain-bids)
- [Planet — CornCaster yield forecasting](https://www.planet.com/pulse/corncaster-how-planets-yield-forecasting-solution-is-helping-agriculturists-and-economists-get-ahead-of-this-years-harvest/)
- [Descartes Labs — Advancing the science of soy forecasting](https://medium.com/descarteslabs-team/advancing-the-science-of-soy-forecasting-f399bae42b78)
- [Bloomberg — BCOM 2026 Target Weights](https://www.bloomberg.com/company/press/bloomberg-commodity-index-2026-target-weights-announced/)
