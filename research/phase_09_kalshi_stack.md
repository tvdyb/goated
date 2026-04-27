# Phase 09 — Kalshi Weekly Soybean: Minimum Viable and Recommended Stack

## Abstract

Market-making the Kalshi `KXSOYBEANW` weekly soybean grid does not require an institutional trading stack, but it does require a specific subset of one. This phase filters the wide Phase 3 tooling inventory and the wide Phase 6 data catalog down to the minimum a realistic retail-to-small-prop operator needs to stand up a quoting book, plus a recommended upgrade path that stays under five-figure monthly run-rate. Central facts are inherited from Phase 7 — Kalshi is a CFTC DCM whose API is REST-plus-WebSocket, RSA-PSS signed, leaky-bucket throttled, fully cash-collateralized, and referenced to the CBOT settle — and from Phase 8, whose pricing engine is a Breeden–Litzenberger density fit to the CME ZS option surface. The bottleneck is neither latency nor tick-store size; it is reliable CME options data for the risk-neutral density, and clean timestamped Kalshi tick history for inventory and queue-position reasoning.

---

## 1. Kalshi API

### 1.1 Auth and connectivity

Production REST is `https://api.elections.kalshi.com/trade-api/v2`; demo is `https://demo-api.kalshi.co/trade-api/v2`; the WebSocket is `wss://api.elections.kalshi.com/trade-api/ws/v2` and authenticates on the handshake using the same scheme as REST ([Kalshi API Reference](https://docs.kalshi.com/api-reference); [Kalshi WebSocket — Market Ticker](https://docs.kalshi.com/websockets/market-ticker)). Every authenticated request carries `KALSHI-ACCESS-KEY` (UUID), `KALSHI-ACCESS-TIMESTAMP` (ms since epoch), and `KALSHI-ACCESS-SIGNATURE` (base64 RSA-PSS over SHA-256), where the signed message is timestamp + HTTP method + path *without query parameters* ([Kalshi API Keys](https://docs.kalshi.com/getting_started/api_keys)). A FIX 5.0 SP2 session endpoint with Order Entry, Drop Copy, and Listener roles is documented alongside REST — new versus Phase 7 — giving larger participants an institutional on-ramp ([Kalshi Endpoint Index — llms.txt](https://docs.kalshi.com/llms.txt)).

### 1.2 Endpoints that matter for a market maker

The full catalog is in Phase 7 §8; the fast path is narrower. Market data: `GET /markets/{ticker}/orderbook`, `GET /markets/trades`, and the batch variants. Event enumeration on the bucket grid: `GET /events/{ticker}`, returning `floor_strike`, `cap_strike`, and per-child Yes/No quotes. Order lifecycle: `POST /orders`, `DELETE /orders/{order_id}`, `POST /orders/{order_id}/amend`, `POST /orders/{order_id}/decrease`, and the batch variants. Queue position — a first-class endpoint for FIFO-aware quoting — is at `GET /orders/{order_id}/queue_position` and `GET /orders/queue_positions` ([Kalshi Endpoint Index — llms.txt](https://docs.kalshi.com/llms.txt)). Portfolio reconciliation: `GET /portfolio/{positions,fills,balance,settlements}`. RFQ: `POST /communications/rfq` (capped at 100 open) plus quote accept/confirm (Rule 5.3(b); Phase 7 §5).

The WebSocket multiplex carries `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`, `market_positions`, `order_group_updates`, `communications`, and `market_lifecycle_v2` on a single socket subscribed by `market_ticker` or `market_tickers` ([Kalshi WebSocket — Market Ticker](https://docs.kalshi.com/websockets/market-ticker)). Event-level subscribe is not supported; the quoter enumerates child markets once and subscribes to the list.

### 1.3 Rate limits

Tiered tokens per second, read / write: Basic 200/100, Advanced 300/300, Premier 1,000/1,000, Paragon 2,000/2,000, Prime 4,000/4,000 ([Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)). Most operations cost the default 10 tokens — so Basic delivers 10 writes/sec — with discounts on cancels, single-order reads, and quote create/cancel, and no discount on batch submits (a 25-order batch costs 25× a single). Over-quota returns `HTTP 429` with body `{"error": "too many requests"}` and no `Retry-After` header. Basic is self-service on signup, Advanced via form, Premier+ unpublished. The practical implication: an MVP operator on Basic sustains ≤10 order mutations per second across the whole bucket strip. A 15-bucket quoter amending each side once per second already needs Advanced; a tick-level repricer needs Premier or Prime. Because `amend` is first-class, the rate-efficient quoter amends resting orders for small mid-adjustments and cancels only when pulling a bucket entirely.

### 1.4 Historical data availability and gaps

`GET /historical/cutoff-timestamps` demarcates live vs. historical; markets settled before the cutoff — and their candlesticks, orders, fills, trades — are only accessible under `/historical/*` ([Kalshi API Reference](https://docs.kalshi.com/api-reference); [Kalshi Endpoint Index — llms.txt](https://docs.kalshi.com/llms.txt)). No public bulk-download or FIX Drop-Copy archive covers past order-book depth below candlestick granularity. For any week preceding the operator's own WebSocket capture, full L1/L2 reconstruction from Kalshi's servers is not supported; backfill is via 1-minute/60-minute/1-day candlesticks or per-trade prints from `GET /markets/trades`. **Tick history is captured forward from first subscribe — this is the single largest data gap to plan around.**

### 1.5 Sandbox

The demo environment mirrors production endpoints with separate keys ([Kalshi API Reference](https://docs.kalshi.com/api-reference)). It validates signing, rate-limit headers, WebSocket handshake, and order lifecycle, but does not reproduce production flow; a separate paper-trading layer at the quoter level is still required.

### 1.6 Market-maker program

Rulebook Chapter 4 (Rules 4.1–4.5, v1.18) designates Market Makers with reduced fees, a Rule 5.19 position-limit exemption, 10× non-MM Position Accountability Levels (Rule 4.5(a)), and bespoke quoting obligations in a non-public Market Maker Agreement ([KalshiEX Rulebook v1.18](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)). No public roster; designation is discretionary. A retail-to-small-prop operator is not an MM on day one and operates on the Phase 7 §6 base taker/maker schedule.

---

## 2. CME-side data for hedging and signal

The Kalshi bucket strip is priced off a CME ZS reference (Phase 7 §2) and hedged with ZS futures and options on ZS (Phase 8 §6). Two distinct data products are needed.

### 2.1 L1 ZS/ZM/ZL for hedge legs

The cheapest viable path to real-time Level-1 on ZS/ZM/ZL is **via the FCM carrying the hedge account**. A retail-tier futures broker (Interactive Brokers, NinjaTrader, AMP, Tradovate, TradeStation) bundles CME Globex Level 1 for non-professional status at $1–$20/month per exchange, and the broker API doubles as the hedge-order path. This is materially cheaper than any cloud data API for pure L1 and is already required for the hedge. Phase 3 §1.1 covers the institutional alternative (direct CME MDP 3.0, Exegy).

For venue-native book granularity, **Databento's `GLBX.MDP3` dataset** resells CME MDP 3.0; the Standard plan at $199/month covers 12 months of L1 history plus pay-as-you-go, but live streaming requires Plus at $1,399/month ([Databento — Pricing](https://databento.com/pricing); [Databento — GLBX.MDP3 dataset](https://databento.com/datasets/GLBX.MDP3)). MVP uses FCM L1 for live and Databento Standard for historical calibration; the Plus step-up is reserved for when live MBP depth drives the quoting loop.

### 2.2 Options on ZS — the expensive piece

The Phase 8 §2 RND construction needs a CBOT soybean option chain at each reprice. CME lists standard monthly, short-dated new-crop (SDNC), and weekly Friday expiries February through August ([CME — Agricultural Short-Term Options](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)). Cheapest adequate sources in ascending cost/liveness:

1. **CME DataMine EOD files** (low-three-figures/month). Settlement-price chains next morning — enough for one SVI refit per CBOT settle, adequate at weekly cadence when intraweek updates are driven by futures moves and a vol-regime filter ([CME — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html); Phase 3 §1.1).
2. **Barchart cmdty API** (free tier to low-four-figures/month). Consolidated-vendor quality, not exchange-tick, but the dominant retail-accessible option-chain source (Phase 3 §1.2). Sufficient for a weekly Breeden–Litzenberger fit.
3. **Databento Plus** ($1,399/month). Real-time option chain on GLBX.MDP3; the natural step up when intraweek RND matters for PnL.
4. **CME CVOL** (EOD free; intraday via DataMine). 30-day implied-vol index on ZS, ZM, ZL ([CME — CME Group Volatility Indexes](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html); Phase 6 §2.2). A regime filter in front of the quoter, not a substitute for the chain.

Cboe Hanweck, Bloomberg OVML, and CQG options analytics are priced institutionally and add no agriculture-specific value here (Phase 3 §1.3).

---

## 3. Fundamentals pipelines pared for a 5-day horizon

A `KXSOYBEANW` Event opens Friday and settles the following Friday; most of the Phase 6 catalog operates on a longer clock. The filter is which releases land inside a 5-day window often enough, with enough impact, to matter for quoting.

The weekly-relevant U.S. government set reduces to three: **NASS Crop Progress** (Mondays 4:00 p.m. ET, April–November); **USDA FAS Weekly Export Sales** (Thursdays 8:30 a.m. ET); **USDA AMS FGIS Grain Inspections** (Mondays afternoon ET) as the physical cross-check on FAS ([USDA — WASDE Report](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report); [USDA NASS — National Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/); [USDA FAS — Export Sales Reporting](https://www.fas.usda.gov/programs/export-sales-reporting-program)). **WASDE** lands monthly, second Tuesday 12:00 p.m. ET; when it falls inside a `KXSOYBEANW` week it dominates, and quotes should widen or pull through the release window (Phase 6 §4). **Grain Stocks** (quarterly), **Prospective Plantings** (March 31), and **Acreage** (June 30) each apply to a single week per year with the same treatment.

South American weeklies matter November through June: **BCBA Panorama Agrícola Semanal** (Thursdays 3 p.m. ART) and **BCR Informativo Semanal** are the Argentine parallels to Crop Progress (Phase 6 §5). **CONAB** Levantamento is monthly, treated like WASDE when in-window.

Everything longer-cycle — Chinese GACC imports (3-week lag), MARA CASDE monthly, FAS GAIN attaché reports — is slow fair-value input refreshed daily and cached, not an intraweek quoting signal (Phase 6 §6). Delivery mechanics for all of the above are machine-readable and already catalogued (NASS Quick Stats REST, FAS ESRQS, FGIS Socrata; all free).

---

## 4. Weather feeds pared for a 5-day horizon

For a five-day lifecycle the weather stack collapses to a nowcast, short-range models, and one drought overlay — all free.

**NOAA GEFS** (4×/day, ~35-day ensemble with useful skill in days 1–10, via NOMADS and AWS S3 mirrors; Phase 6 §7) is the primary short-range model. **ECMWF IFS open data** (CC-BY-4.0 since late 2025, +2 h versus real-time on AWS/Azure/GCP/ECMWF) is the higher-skill reference ([ECMWF — Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data); Phase 3 §4). **NOAA HRRR** supplies the 3 km convective nowcast; **NOAA CPC 6–10-day and 8–14-day outlooks** (daily) bridge to the next Event. **NASA SMAP** (root-zone moisture, L3 daily / L4 3-hourly) and the **U.S. Drought Monitor** (Thursdays 8:30 a.m. ET, GeoJSON/TopoJSON) cover Midwest growing-season state (Phase 6 §8).

Commercial weather — DTN, Maxar/Vaisala Xweather WeatherDesk, Atmospheric G2 — is institutional-priced (Phase 3 §4) and unnecessary at this horizon. A statistical bias correction fit against ERA5/ERA5-Land reanalysis covers the window at zero marginal cost. Recommended upgrade, if PnL later justifies it: DTN Weather bundled with a ProphetX subscription, which also delivers the country-elevator cash-bid tape for basis reads (Phase 3 §1.2).

---

## 5. Logistics and flow

At this horizon the logistics category is almost entirely pared. Kpler, Vortexa, MarineTraffic, Baltic indices — all built for multi-week flow resolution (Phase 6 §9). Inside five days, the survivors are:

- **USDA AMS Grain Transportation Report** (weekly Thursdays, free). Barge rates, rail tariffs, ocean freight; the release can move basis and indirectly ZS.
- **USACE LPMS Lock Performance** (30-minute, free). Upper Mississippi and Illinois River queues. Relevant on weeks with an active shock (ice, high water, lock outage); otherwise low-priority.
- **CFTC COT** (Fridays 3:30 p.m. ET, free). Lands after Event expiry and informs the *next* week's positioning-aware fair value ([CFTC — Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm); Phase 6 §10).

Everything else in Phase 6 §9 — Kpler AIS, Vortexa, Planet, Descartes, Gro — is either institutionally priced or slower-cadence than the Event resolves. Not MVP. The recommended stack adds Barchart cmdty cash bids (daily, low-three-figure tier) for the basis read and leaves AIS/satellite for later.

---

## 6. Compute and latency budget

### 6.1 Co-location is unnecessary

Three facts make colocation superfluous. First, Kalshi's REST rate limits bind well before microsecond routing matters — at Basic, the 10 writes/sec ceiling is the constraint, not wire latency. Second, the CBOT Rule 813 settlement reference resolves on a daily-settle window, not a Kalshi-tick-by-tick mid; there is no information race to front-run a continuous reference. Third, Kalshi positions are fully cash-collateralized with no variation margin (Phase 7 §7), so PnL is insensitive to microsecond hedge slippage — the hedge lag that matters is tens of milliseconds to a few seconds.

The correct placement is **AWS `us-east-1` (Virginia)**, where Kalshi's own infrastructure runs (inferred from DNS). A quoter on a `t4g.small` or `c7g.medium` sees single-digit-ms REST round-trip. The CME hedge leg is in Aurora, IL; the broker API already adds a hop budget regardless of region. Tick-to-quote budget: WebSocket delta (~10–20 ms) → optional density refresh → reservation-price compute (<1 ms) → amend call (~5–10 ms) → ack (~5–10 ms) — **40–60 ms inclusive**, well inside the regime where Rule 5.9 FIFO is won by price, not speed.

### 6.2 Sizing

One `c7g.large` (2 vCPU, 4 GB) runs the quoter across 15–20 buckets with headroom — the SVI fit costs a few milliseconds in NumPy/SciPy and the loop is I/O-bound. A second instance runs the CME hedge connector; a third, low-spec, captures ticks to S3. Total compute: under $150/month for the MVP, under $500/month tripled out with monitoring and redundancy.

---

## 7. Storage and backtesting

### 7.1 What needs storing

Three tapes: (i) Kalshi `orderbook_delta` + `ticker` + `trade` + `fill` per bucket per Event, forward from subscribe; (ii) CME ZS/ZM/ZL L1 plus EOD options chain from Databento Standard or FCM-side capture; (iii) fundamentals and weather pulls from §3–§4. The Kalshi capture is critical because Kalshi does not backfill full order-book history (§1.4) — every missed day is permanently missed.

### 7.2 Practical choices

**DuckDB + Parquet on S3** is the MVP and a serviceable recommended stack. DuckDB reads Parquet out of S3 via `httpfs` with per-day per-feed partitions ([DuckDB documentation](https://duckdb.org/docs/)). A week of `orderbook_delta` across a 20-bucket strip is tens of megabytes compressed; a year is single-digit gigabytes. S3 Standard cost: under $1/month. **ArcticDB** is the upgrade for tick workloads where Parquet partition overhead starts to hurt — open-core, free OSS tier, descended from Man Group's Arctic-on-MongoDB ([ArcticDB](https://arcticdb.io/); Phase 3 §7.1). **kdb+**, **OneTick**, and **Deltix** are six-figure-licensed and off-budget (Phase 3 §7.1).

CME options EOD lands as Parquet partitioned by trade-date and expiry, one row per (underlying, expiry, strike, type). A decade of CBOT ag options chains is low-single-digit gigabytes. Fundamentals and weather history share the same lake.

### 7.3 Backtesting

The Phase 3 §7.2 open-source stack — pandas/numpy/scipy/statsmodels with polars and DuckDB for OOM work — is adequate. The dominant research question is Breeden–Litzenberger calibration quality (Phase 8 §2), which is SciPy-native. Vectorbt, Backtrader, and QuantConnect Lean are available but not load-bearing here.

---

## 8. Risk and ops

Three controls are load-bearing for running `KXSOYBEANW` against a CME hedge.

**Kill-switch.** The REST `DELETE /orders/batch` endpoint cancels a provided list of order IDs in one call; a quoter tracking its own resting book can flush every open order in a single request. A secondary mechanism is `POST /order-groups/{group_id}/trigger`, which cancels every order in a pre-declared group — the order-group API exists precisely for this use ([Kalshi Endpoint Index — llms.txt](https://docs.kalshi.com/llms.txt)). The kill-switch runs on four triggers: (i) aggregate signed delta across the bucket strip exceeds a configured bound in ZS-equivalent bushels; (ii) absolute intraweek PnL drawdown crosses a hard stop; (iii) CME hedge connectivity fails heartbeat for N seconds; (iv) Kalshi WebSocket reconnects more than K times in a minute. A `reduce_only` retry layer reopens quotes only after a cold-start check.

**Position and loss limits.** Rule 5.19 expresses Kalshi position limits in dollars of max loss rather than contract count (Phase 7 §5). The pricing engine tracks per-bucket and per-Event signed exposure *in dollars*, and compares against the Appendix-A-defined limit (default $25,000 per member until Appendix A confirms otherwise). A `buy_max_cost` dollar cap on every `POST /orders` call is a second layer, scoped per request (Phase 7 §5). The CME hedge leg carries its own broker-imposed initial and maintenance margin and daily loss tripwires.

**Reconciliation.** Because Kalshi is fully cash-collateralized and settles by batch credit on Friday, reconciliation between the Kalshi book and the CME hedge happens three times per session: open (reconcile positions read from `GET /portfolio/positions` vs. the broker leg); intraday (compare ongoing fills from WebSocket `fill` vs. `GET /portfolio/fills` snapshot vs. broker execution reports); end-of-session (confirm expected settlement flow from `GET /portfolio/settlements` and reconcile against the CME futures/options EOD settlement statement from the FCM). A single reconciliation table keyed by `(event_ticker, timestamp, side)` joins Kalshi and CME rows and flags deltas. Phase 7 §8 notes that Kalshi's FIX Drop Copy session surfaces every fill and is the institutional-grade reconciliation channel for participants past the Premier tier.

---

## 9. Budget sketches

Two reference stacks. Minimum viable is the configuration to go live with a quoting book and a CME hedge under a few thousand dollars per month; recommended adds live CME option chain, a higher Kalshi rate-limit tier, and richer logistics/weather data while remaining well under five-figure monthly run-rate.

### Table 1 — Minimum viable stack

| Layer | Choice | Cost | Notes |
|---|---|---|---|
| Kalshi API tier | Basic (200 reads / 100 writes per sec) | Free | Self-service on signup ([Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)) |
| Kalshi tick capture | Self-hosted WebSocket recorder | compute only | Captures `orderbook_delta` forward from subscribe |
| CME L1 (ZS/ZM/ZL) | FCM-bundled non-professional feed | $1–$20/mo/exchange | Via broker account used for hedge legs |
| CME options history | Databento Standard + PAYG on GLBX.MDP3 | $199/mo + usage | 12 months L1 included; options via PAYG ([Databento Pricing](https://databento.com/pricing)) |
| CME option chain (live) | EOD DataMine settlement files | ~$100–300/mo | One SVI refit per CBOT settle ([CME Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html)) |
| Vol regime filter | CME CVOL on ZS, ZM, ZL | $0 EOD benchmark | Via CME site; intraday via DataMine ([CME CVOL](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html)) |
| Fundamentals | WASDE, NASS Quick Stats, FAS ESR, FGIS, BCBA, BCR | Free | Machine-readable APIs and PDFs (Phase 6 §4–5) |
| Weather | NOAA GEFS + ECMWF IFS open data + NOAA CPC outlooks + Drought Monitor | Free | Via NOMADS, AWS, ECMWF ([ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)) |
| Logistics | USDA GTR, USACE LPMS, CFTC COT | Free | Weekly cadence sufficient (Phase 6 §9–10) |
| Compute | 1×`c7g.large` quoter + 1×`c7g.medium` capture in AWS `us-east-1` | ~$80–120/mo | Regional to Kalshi |
| Storage | S3 Standard + DuckDB + Parquet | <$5/mo for first year | Query via Python/DuckDB ([DuckDB docs](https://duckdb.org/docs/)) |
| Research notebook | Python + pandas + scipy + polars | Free | Phase 3 §7.2 stack |
| Hedge execution | Retail FCM (Interactive Brokers / AMP / Tradovate) | per-contract commission | Doubles as L1 source |
| **Indicative total** | | **~$400–700/mo** plus commissions | Feasible for a solo operator |

### Table 2 — Recommended stack

| Layer | Choice | Cost | Notes |
|---|---|---|---|
| Kalshi API tier | Advanced (300/300) or Premier (1,000/1,000) | Free on application | Unlocks tick-level amend cadence ([Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)) |
| Kalshi trading protocol | REST + WebSocket + FIX Drop Copy | included in tier | Drop Copy for fills reconciliation ([Kalshi llms.txt](https://docs.kalshi.com/llms.txt)) |
| CME L1 + options (live) | Databento Plus on GLBX.MDP3 | $1,399/mo | Live streaming; intraday RND refresh ([Databento Pricing](https://databento.com/pricing)) |
| CME option analytics | In-house SVI/Figlewski-GEV, CVOL overlay | compute only | Phase 8 §2 pipeline |
| Basis tape | Barchart cmdty REST (paid tier) | ~$300–800/mo | Cash-grain bids (Phase 3 §1.2) |
| Fundamentals | Same free feeds + FAS GAIN attaché archive | Free | Historical GAIN PDFs indexed (Phase 6 §6) |
| Weather | Same free NWP + optional DTN Weather | $0 or low-$1k/mo | DTN upgrade when PnL justifies (Phase 3 §4) |
| Logistics | Add AIS read via MarineTraffic API | low-$300/mo | Barge-flow overlay on GTR (Phase 6 §9) |
| Compute | 2× quoter instances (hot/standby) + capture + research box | ~$400–600/mo | Multi-AZ redundancy |
| Storage | S3 + DuckDB + ArcticDB (OSS tier) | <$20/mo | ArcticDB for tick workloads ([ArcticDB](https://arcticdb.io/)) |
| Monitoring | Grafana Cloud free / Prometheus + PagerDuty | free–low-$100/mo | Quote-rate, fill-rate, rate-limit headroom |
| Hedge execution | Same FCM + optional TT or CQG seat | $250–$1,000/mo TT | TT Autospreader if board-crush hedge matters (Phase 3 §2) |
| **Indicative total** | | **~$2,500–4,500/mo** plus commissions | Under small-prop run-rate |

A third tier above "recommended" — full CBOT MBO depth via Databento Unlimited at $3,500/month, an Exegy or Vela appliance for CME tick normalization, a kdb+ backtester, and Kpler for cargo tracking — is what separates a small prop shop from a market-making franchise. Nothing in the `KXSOYBEANW` product demands it; the decision to step up is about breadth across other Kalshi commodity Events and deeper ZS microstructure work, not about winning quote time on this specific strip.

---

## Key takeaways

- The Kalshi `KXSOYBEANW` quoter is bottlenecked by **rate limits**, not wire latency. Basic tier gives 10 writes/sec; Advanced is the realistic MVP starting point; Premier is the tick-quoting tier. Co-location is unnecessary; AWS `us-east-1` is the correct placement.
- The API surface is complete and machine-friendly: RSA-PSS authenticated REST plus a single multiplexed WebSocket, a documented sandbox at `demo-api.kalshi.co`, and a FIX 5.0 SP2 option (including Drop Copy) for the recommended-tier operator. First-class `amend`, `decrease`, and `queue_position` endpoints support FIFO-aware quoting without cancel-and-replace.
- Kalshi **does not backfill full order-book history** — capture begins when subscription begins. This is the single largest data gap; tick capture must be stood up before any serious quoting.
- The cheapest viable CME-side live feed is the **FCM-bundled non-professional L1** already required for the hedge; CME options data for the RN density is the genuinely expensive item, with an adequate MVP at CME DataMine EOD and a recommended step-up at Databento Plus ($1,399/month).
- Weekly-relevant fundamentals collapse to **Crop Progress, Weekly Export Sales, Grain Inspections, and in-window WASDE/Grain Stocks** on the U.S. side, plus **BCBA and BCR** in the Argentine campaign. Everything else (Phase 6) is a slow-moving fair-value input, not a quoting signal.
- Weather collapses to free **GEFS + IFS open data + HRRR + CPC outlooks + Drought Monitor**; commercial weather is unnecessary at this horizon.
- Storage is **DuckDB + Parquet on S3** at MVP and **ArcticDB OSS** at recommended; kdb+ is categorically off-budget and unnecessary.
- Kill-switch implementation uses `DELETE /orders/batch` plus the order-group trigger endpoint; reconciliation joins Kalshi portfolio/fills/settlements with the FCM hedge statements. Kalshi's full cash collateralization means no variation margin to reconcile.
- MVP total cost is **~$400–700/month** ex-commissions; recommended is **~$2,500–4,500/month** ex-commissions. Both stay well inside realistic retail-to-small-prop budgets.

## References

- [Kalshi API Reference](https://docs.kalshi.com/api-reference)
- [Kalshi API Endpoint Index — llms.txt](https://docs.kalshi.com/llms.txt)
- [Kalshi API Keys (RSA-PSS SHA-256 signing)](https://docs.kalshi.com/getting_started/api_keys)
- [Kalshi Rate Limits (tiered leaky-bucket)](https://docs.kalshi.com/getting_started/rate_limits)
- [Kalshi WebSocket — Market Ticker](https://docs.kalshi.com/websockets/market-ticker)
- [KalshiEX LLC Rulebook v1.18 (2025, CFTC filing)](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)
- [Databento — Pricing plans](https://databento.com/pricing)
- [Databento — GLBX.MDP3 dataset](https://databento.com/datasets/GLBX.MDP3)
- [CME Group — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html)
- [CME Group — CME Group Volatility Indexes (CVOL)](https://www.cmegroup.com/market-data/cme-group-benchmark-administration/cme-group-volatility-indexes.html)
- [CME Group — Agricultural Short-Term (Weekly) Options](https://www.cmegroup.com/markets/agriculture/new-crop-weekly-options.html)
- [USDA — WASDE Report](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)
- [USDA NASS — National Crop Progress](https://www.nass.usda.gov/Publications/National_Crop_Progress/)
- [USDA NASS — Quick Stats API](https://quickstats.nass.usda.gov/api)
- [USDA FAS — Export Sales Reporting Program](https://www.fas.usda.gov/programs/export-sales-reporting-program)
- [USDA AMS — FGIS Data and Statistics](https://www.ams.usda.gov/resources/fgis-data-and-statistics)
- [ECMWF — Open Data (CC-BY-4.0)](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [NOAA — Global Ensemble Forecast System (GEFS)](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gefs.php)
- [NOAA Climate Prediction Center — 6–10 and 8–14 Day Outlooks](https://www.cpc.ncep.noaa.gov/products/predictions/)
- [U.S. Drought Monitor](https://droughtmonitor.unl.edu/)
- [USDA AMS — Grain Transportation Report](https://www.ams.usda.gov/services/transportation-analysis)
- [USACE — Lock Performance Monitoring System (LPMS)](https://corpslocks.usace.army.mil/)
- [CFTC — Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [DuckDB — Documentation](https://duckdb.org/docs/)
- [ArcticDB](https://arcticdb.io/)
- Phase 03 — Tooling and Infrastructure (this project, `./phase_03_tooling_and_infrastructure.md`)
- Phase 06 — Data Streams for Pricing the Soybean Complex (`./phase_06_data_streams.md`)
- Phase 07 — Kalshi Weekly Soybean Price-Range Contract: Structural Dissection (`./phase_07_kalshi_contract_structure.md`)
- Phase 08 — Synthesis: Pricing a Kalshi Weekly Soybean Range Grid (`./phase_08_synthesis_pricing.md`)
