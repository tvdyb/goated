# Audit C — Phase 09: Kalshi Weekly Soybean Stack — Pre-Indexing

## 1. Source artifact summary

`research/phase_09_kalshi_stack.md` filters the wide tooling inventory of Phase 3 and the wide data catalog of Phase 6 down to a Minimum Viable Stack (MVS) and a Recommended upgrade for a retail-to-small-prop operator running a market-making book on Kalshi's `KXSOYBEANW` weekly soybean grid. It inherits the Kalshi-as-CFTC-DCM facts from Phase 7 (REST + WebSocket, RSA-PSS signing, leaky-bucket rate limits, full cash collateralization, CBOT-settle reference) and the Breeden–Litzenberger CME-options pricing engine from Phase 8. The artifact tiers each layer of the stack — Kalshi API access and tier choice, CME L1 and options-chain data for the risk-neutral density and hedge legs, weekly-cadence fundamentals and weather feeds, compute/latency placement, storage and backtesting, risk-and-ops kill-switch and reconciliation, and two consolidated budget tables. The recurring theme: the bottleneck is reliable CME options data and forward-captured Kalshi tick history, not latency or tick-store size, and a solo operator can stand up the MVS for ~$400–700/month plus commissions.

## 2. Claims table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C09-01 | [MVS] Production REST base URL is `https://api.elections.kalshi.com/trade-api/v2`. | §1.1 (line 13) | established | data-ingest;tooling |
| C09-02 | [MVS] Demo/sandbox base URL is `https://demo-api.kalshi.co/trade-api/v2`. | §1.1 (line 13) | established | data-ingest;tooling |
| C09-03 | [MVS] WebSocket URL is `wss://api.elections.kalshi.com/trade-api/ws/v2` and authenticates on the handshake using the same scheme as REST. | §1.1 (line 13) | established | data-ingest |
| C09-04 | [MVS] Every authenticated request carries `KALSHI-ACCESS-KEY` (UUID), `KALSHI-ACCESS-TIMESTAMP` (ms since epoch), and `KALSHI-ACCESS-SIGNATURE` (base64 RSA-PSS over SHA-256). | §1.1 (line 13) | established | tooling |
| C09-05 | [MVS] The signed message is timestamp + HTTP method + path **without query parameters**. | §1.1 (line 13) | established | tooling |
| C09-06 | [RECOMMENDED] FIX 5.0 SP2 session endpoint exposes Order Entry, Drop Copy, and Listener roles for institutional participants. | §1.1 (line 13); §8 (line 136); Table 2 (line 168) | established | oms;tooling |
| C09-07 | [MVS] Market-data fast-path REST endpoints are `GET /markets/{ticker}/orderbook`, `GET /markets/trades`, and their batch variants. | §1.2 (line 17) | established | data-ingest;market-structure |
| C09-08 | [MVS] `GET /events/{ticker}` returns the bucket grid with `floor_strike`, `cap_strike`, and per-child Yes/No quotes. | §1.2 (line 17) | established | market-structure;data-ingest |
| C09-09 | [MVS] Order-lifecycle endpoints are `POST /orders`, `DELETE /orders/{order_id}`, `POST /orders/{order_id}/amend`, `POST /orders/{order_id}/decrease`, plus batch variants. | §1.2 (line 17) | established | oms |
| C09-10 | [MVS] Queue-position endpoints `GET /orders/{order_id}/queue_position` and `GET /orders/queue_positions` make FIFO-aware quoting first-class. | §1.2 (line 17) | established | oms;market-structure |
| C09-11 | [MVS] Portfolio reconciliation uses `GET /portfolio/{positions,fills,balance,settlements}`. | §1.2 (line 17); §8 (line 136) | established | oms;observability |
| C09-12 | [RECOMMENDED] RFQ submission via `POST /communications/rfq` is capped at 100 open RFQs per account. | §1.2 (line 17) | established | contract;oms |
| C09-13 | [MVS] A single WebSocket multiplex carries `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`, `market_positions`, `order_group_updates`, `communications`, and `market_lifecycle_v2`. | §1.2 (line 19) | established | data-ingest;oms |
| C09-14 | [MVS] WebSocket subscriptions are by `market_ticker` or `market_tickers`; event-level subscribe is not supported, so the quoter enumerates child markets and subscribes to the list. | §1.2 (line 19) | established | data-ingest;market-structure |
| C09-15 | Tiered tokens-per-second (read/write): Basic 200/100, Advanced 300/300, Premier 1,000/1,000, Paragon 2,000/2,000, Prime 4,000/4,000. | §1.3 (line 23) | established | tooling;oms |
| C09-16 | [MVS] Default operations cost 10 tokens, so Basic delivers ≤10 order mutations per second across the full bucket strip. | §1.3 (line 23); Key takeaways (line 187) | established | oms |
| C09-17 | Cancels, single-order reads, and quote create/cancel are discounted; batch submits are not (a 25-order batch costs 25× a single). | §1.3 (line 23) | established | oms |
| C09-18 | Over-quota responses are HTTP 429 with body `{"error": "too many requests"}` and **no `Retry-After` header**, so backoff must be local. | §1.3 (line 23) | established | tooling;oms |
| C09-19 | Basic tier is self-service on signup; Advanced is via form; Premier+ is unpublished. | §1.3 (line 23) | established | tooling |
| C09-20 | [RECOMMENDED] A 15-bucket quoter amending each side once per second already requires Advanced; tick-level repricing requires Premier or Prime. | §1.3 (line 23); Key takeaways (line 187) | practitioner-lore | oms;strategy |
| C09-21 | Because `amend` is first-class, the rate-efficient quoter amends resting orders for small mid-adjustments and only cancels when pulling a bucket entirely. | §1.3 (line 23); Key takeaways (line 188) | practitioner-lore | oms;strategy |
| C09-22 | `GET /historical/cutoff-timestamps` demarcates live vs. historical, and markets settled before the cutoff are only accessible under `/historical/*`. | §1.4 (line 27) | established | data-ingest |
| C09-23 | No public bulk-download or FIX Drop-Copy archive covers past order-book depth below candlestick granularity; backfill is via 1-min/60-min/1-day candlesticks or per-trade prints from `GET /markets/trades`. | §1.4 (line 27) | established | data-ingest;backtest |
| C09-24 | [MVS] Tick history is captured forward from first subscribe — the single largest data gap to plan around. | §1.4 (line 27); Key takeaways (line 189) | established | data-ingest;observability |
| C09-25 | The demo environment validates signing, rate-limit headers, WebSocket handshake, and order lifecycle but does not reproduce production flow; a separate paper-trading layer at the quoter level is still required. | §1.5 (line 31) | established | tooling;backtest |
| C09-26 | Rulebook v1.18 Chapter 4 (Rules 4.1–4.5) defines designated Market Makers with reduced fees, a Rule 5.19 position-limit exemption, 10× non-MM Position Accountability Levels (Rule 4.5(a)), and bespoke quoting obligations in a non-public Market Maker Agreement. | §1.6 (line 35) | established | contract;market-structure |
| C09-27 | A retail-to-small-prop operator is not an MM on day one and operates on the base taker/maker fee schedule (Phase 7 §6). | §1.6 (line 35) | established | contract |
| C09-28 | [MVS] The cheapest viable path to real-time L1 on ZS/ZM/ZL is via the FCM that carries the hedge account; retail FCMs bundle CME Globex L1 for non-professional status at $1–$20/month per exchange. | §2.1 (line 45); Table 1 (line 150); Key takeaways (line 190) | established | data-ingest;hedging |
| C09-29 | [MVS] Databento `GLBX.MDP3` Standard at $199/month covers 12 months of L1 history plus pay-as-you-go; live streaming requires Plus at $1,399/month. | §2.1 (line 47); Table 1 (line 151); Table 2 (line 169) | established | data-ingest |
| C09-30 | [MVS] Use FCM L1 for live and Databento Standard for historical calibration; reserve Databento Plus for when live MBP depth drives the quoting loop. | §2.1 (line 47) | practitioner-lore | data-ingest;strategy |
| C09-31 | The Phase 8 §2 RND construction requires a CBOT soybean option chain at every reprice. | §2.2 (line 51) | established | pricing-model;density |
| C09-32 | CME lists standard monthly, short-dated new-crop (SDNC), and weekly Friday expiries from February through August on CBOT soybean options. | §2.2 (line 51) | established | market-structure |
| C09-33 | [MVS] CME DataMine EOD settlement-price chains (~low-three-figures/month) support one SVI refit per CBOT settle and are adequate at weekly cadence when intraweek updates are driven by futures moves and a vol-regime filter. | §2.2 (line 53); Table 1 (line 152); Key takeaways (line 190) | established | density;pricing-model;data-ingest |
| C09-34 | [RECOMMENDED] Barchart cmdty API (free tier to low-four-figures/month) is consolidated-vendor quality, not exchange-tick, but is sufficient for a weekly Breeden–Litzenberger fit. | §2.2 (line 54); Table 2 (line 171) | established | data-ingest;density |
| C09-35 | [RECOMMENDED] Databento Plus ($1,399/month) is the natural step up when intraweek RND drives PnL. | §2.2 (line 55); Table 2 (line 169) | practitioner-lore | data-ingest;density |
| C09-36 | CME CVOL is a 30-day implied-vol index on ZS, ZM, and ZL (EOD free; intraday via DataMine) and serves as a regime filter, not a substitute for the chain. | §2.2 (line 56); Table 1 (line 153) | established | density;strategy |
| C09-37 | Cboe Hanweck, Bloomberg OVML, and CQG options analytics are institutionally priced and add no agriculture-specific value at this horizon. | §2.2 (line 58) | practitioner-lore | tooling |
| C09-38 | A `KXSOYBEANW` Event opens Friday and settles the following Friday. | §3 (line 64) | established | contract |
| C09-39 | [MVS] Weekly-relevant U.S. fundamentals reduce to NASS Crop Progress (Mondays 4:00 p.m. ET, April–November), USDA FAS Weekly Export Sales (Thursdays 8:30 a.m. ET), and USDA AMS FGIS Grain Inspections (Mondays afternoon ET) as a physical cross-check on FAS. | §3 (line 66); Key takeaways (line 191) | established | data-ingest;strategy |
| C09-40 | WASDE lands monthly on the second Tuesday at 12:00 p.m. ET; when in-window for `KXSOYBEANW`, quotes should widen or pull through the release window. | §3 (line 66) | practitioner-lore | strategy;observability |
| C09-41 | Grain Stocks (quarterly), Prospective Plantings (March 31), and Acreage (June 30) each apply to a single week per year and receive WASDE-equivalent treatment when in-window. | §3 (line 66) | established | strategy;data-ingest |
| C09-42 | [MVS] South American weeklies (Nov–Jun) are BCBA Panorama Agrícola Semanal (Thursdays 3 p.m. ART) and BCR Informativo Semanal; CONAB Levantamento is monthly and treated like WASDE in-window. | §3 (line 68) | established | data-ingest;strategy |
| C09-43 | Long-cycle inputs (GACC imports with 3-week lag, MARA CASDE monthly, FAS GAIN attaché reports) are slow fair-value inputs cached daily, not intraweek quoting signals. | §3 (line 70) | practitioner-lore | data-ingest;strategy |
| C09-44 | NASS Quick Stats REST, FAS ESRQS, and FGIS Socrata are machine-readable and free. | §3 (line 70); Table 1 (line 154) | established | data-ingest |
| C09-45 | [MVS] At the 5-day horizon, weather collapses to NOAA GEFS (4×/day, ~35-day ensemble with skill in days 1–10, via NOMADS and AWS S3 mirrors) as the primary short-range model. | §4 (line 78); Table 1 (line 155) | established | data-ingest |
| C09-46 | [MVS] ECMWF IFS open data has been CC-BY-4.0 since late 2025 and is +2 h vs. real-time on AWS/Azure/GCP/ECMWF. | §4 (line 78) | established | data-ingest |
| C09-47 | [MVS] NOAA HRRR supplies the 3 km convective nowcast, and NOAA CPC 6–10-day and 8–14-day outlooks (daily) bridge to the next Event. | §4 (line 78) | established | data-ingest |
| C09-48 | [MVS] NASA SMAP provides root-zone soil moisture (L3 daily / L4 3-hourly); the U.S. Drought Monitor publishes Thursdays 8:30 a.m. ET in GeoJSON/TopoJSON. | §4 (line 78) | established | data-ingest |
| C09-49 | A statistical bias correction fit against ERA5/ERA5-Land reanalysis covers the 5-day window at zero marginal cost. | §4 (line 80) | practitioner-lore | data-ingest;strategy |
| C09-50 | [RECOMMENDED] DTN Weather, optionally bundled with a ProphetX subscription, is the upgrade and also delivers the country-elevator cash-bid tape for basis reads. | §4 (line 80); Table 2 (line 173) | practitioner-lore | data-ingest |
| C09-51 | [MVS] The five-day-relevant logistics survivors are USDA AMS Grain Transportation Report (weekly Thursdays, free), USACE LPMS Lock Performance (30-minute, free), and CFTC COT (Fridays 3:30 p.m. ET, free). | §5 (lines 88–90); Table 1 (line 156) | established | data-ingest |
| C09-52 | CFTC COT lands after Event expiry and informs the *next* week's positioning-aware fair value. | §5 (line 90) | established | strategy |
| C09-53 | [RECOMMENDED] Add Barchart cmdty cash bids (daily, low-three-figure tier) for the basis read; leave AIS/satellite (Kpler, Vortexa, Planet, Descartes, Gro) for later. | §5 (line 92); Table 2 (line 171) | practitioner-lore | data-ingest |
| C09-54 | Co-location is unnecessary because (i) Kalshi REST rate limits bind well before microsecond routing matters, (ii) the CBOT Rule 813 settlement reference resolves on a daily-settle window with no tick-by-tick race, and (iii) full cash collateralization makes PnL insensitive to microsecond hedge slippage. | §6.1 (line 100); Key takeaways (line 187) | practitioner-lore | market-structure;hedging |
| C09-55 | The hedge lag that matters is tens of milliseconds to a few seconds. | §6.1 (line 100) | practitioner-lore | hedging;oms |
| C09-56 | [MVS] Correct cloud placement is AWS `us-east-1` (Virginia), where Kalshi's own infrastructure runs (inferred from DNS); a `t4g.small` or `c7g.medium` sees single-digit-ms REST round-trip. | §6.1 (line 102); Table 1 (line 157); Key takeaways (line 187) | practitioner-lore | tooling;observability |
| C09-57 | The CME hedge leg is in Aurora, IL; the broker API adds a hop budget regardless of region. | §6.1 (line 102) | established | hedging |
| C09-58 | Tick-to-quote budget: WebSocket delta (~10–20 ms) → optional density refresh → reservation-price compute (<1 ms) → amend call (~5–10 ms) → ack (~5–10 ms) — 40–60 ms inclusive. | §6.1 (line 102) | practitioner-lore | oms;observability |
| C09-59 | At a 40–60 ms tick-to-quote budget, Rule 5.9 FIFO is won by price, not speed. | §6.1 (line 102) | practitioner-lore | market-structure;strategy |
| C09-60 | [MVS] One `c7g.large` (2 vCPU, 4 GB) runs the quoter across 15–20 buckets with headroom; SVI fit costs a few ms in NumPy/SciPy and the loop is I/O-bound. | §6.2 (line 106) | practitioner-lore | tooling;density |
| C09-61 | [MVS] A second instance runs the CME hedge connector and a third low-spec instance captures ticks to S3; total compute is under $150/month MVP and under $500/month with monitoring and redundancy. | §6.2 (line 106); Table 1 (line 157); Table 2 (line 175) | practitioner-lore | tooling;hedging;observability |
| C09-62 | [MVS] Three tapes must be stored: (i) Kalshi `orderbook_delta` + `ticker` + `trade` + `fill` per bucket per Event from subscribe; (ii) CME ZS/ZM/ZL L1 plus EOD options chain; (iii) fundamentals and weather pulls. | §7.1 (line 114) | established | data-ingest;backtest |
| C09-63 | Kalshi capture is critical because Kalshi does not backfill full order-book history — every missed day is permanently missed. | §7.1 (line 114); Key takeaways (line 189) | established | data-ingest;observability |
| C09-64 | [MVS] DuckDB + Parquet on S3 with `httpfs` and per-day per-feed partitions is both MVP and a serviceable recommended choice. | §7.2 (line 118); Table 1 (line 158); Key takeaways (line 193) | established | tooling;backtest |
| C09-65 | A week of `orderbook_delta` across a 20-bucket strip is tens of MB compressed; a year is single-digit GB; S3 Standard cost is under $1/month. | §7.2 (line 118); Table 1 (line 158) | practitioner-lore | data-ingest |
| C09-66 | [RECOMMENDED] ArcticDB (open-core, free OSS tier) is the upgrade for tick workloads where Parquet partition overhead starts to hurt. | §7.2 (line 118); Table 2 (line 176) | practitioner-lore | tooling;backtest |
| C09-67 | kdb+, OneTick, and Deltix are six-figure-licensed and off-budget. | §7.2 (line 118); Key takeaways (line 193) | established | tooling |
| C09-68 | CME options EOD is stored as Parquet partitioned by trade-date and expiry, one row per (underlying, expiry, strike, type); a decade of CBOT ag option chains is low-single-digit GB. | §7.2 (line 120) | practitioner-lore | data-ingest;density |
| C09-69 | The pandas/numpy/scipy/statsmodels + polars + DuckDB open-source stack is adequate for backtesting; Vectorbt, Backtrader, and QuantConnect Lean are available but not load-bearing. | §7.3 (line 124) | practitioner-lore | backtest;tooling |
| C09-70 | The dominant research question is Breeden–Litzenberger calibration quality (Phase 8 §2), which is SciPy-native. | §7.3 (line 124) | practitioner-lore | density;pricing-model;backtest |
| C09-71 | [MVS] Kill-switch primitive: `DELETE /orders/batch` cancels a list of order IDs in one call, allowing a quoter that tracks its own resting book to flush every open order in a single request. | §8 (line 132); Key takeaways (line 194) | established | oms;observability |
| C09-72 | [MVS] Secondary kill-switch primitive: `POST /order-groups/{group_id}/trigger` cancels every order in a pre-declared group. | §8 (line 132) | established | oms;observability |
| C09-73 | The kill-switch fires on four triggers: (i) aggregate signed delta across the bucket strip exceeds a configured ZS-equivalent-bushel bound; (ii) absolute intraweek PnL drawdown crosses a hard stop; (iii) CME hedge connectivity fails heartbeat for N seconds; (iv) Kalshi WebSocket reconnects more than K times in a minute. | §8 (line 132) | practitioner-lore | observability;hedging;inventory |
| C09-74 | A `reduce_only` retry layer reopens quotes only after a cold-start check. | §8 (line 132) | practitioner-lore | oms;inventory |
| C09-75 | Rule 5.19 expresses Kalshi position limits in dollars of max loss, not contract count, with a default $25,000 per member until Appendix A confirms otherwise. | §8 (line 134) | established | contract;inventory |
| C09-76 | The pricing engine tracks per-bucket and per-Event signed exposure in dollars and compares against the Appendix-A-defined limit. | §8 (line 134) | practitioner-lore | inventory;pricing-model |
| C09-77 | A `buy_max_cost` dollar cap on every `POST /orders` call provides a per-request second-layer limit. | §8 (line 134) | established | oms;inventory |
| C09-78 | The CME hedge leg carries broker-imposed initial and maintenance margin and daily loss tripwires of its own. | §8 (line 134) | established | hedging;inventory |
| C09-79 | Reconciliation runs three times per session: open (`GET /portfolio/positions` vs. broker leg), intraday (WebSocket `fill` vs. `GET /portfolio/fills` vs. broker execution reports), and end-of-session (`GET /portfolio/settlements` vs. CME EOD settlement statement from the FCM). | §8 (line 136) | practitioner-lore | observability;oms;hedging |
| C09-80 | A single reconciliation table keyed by `(event_ticker, timestamp, side)` joins Kalshi and CME rows and flags deltas. | §8 (line 136) | practitioner-lore | observability |
| C09-81 | [RECOMMENDED] Kalshi FIX Drop Copy (Premier+) surfaces every fill and is the institutional-grade reconciliation channel. | §8 (line 136); Table 2 (line 168) | established | observability;oms |
| C09-82 | [MVS] Indicative MVS total is ~$400–700/month plus commissions; [RECOMMENDED] indicative recommended-stack total is ~$2,500–4,500/month plus commissions. | Table 1 (line 161); Table 2 (line 179); Key takeaways (line 195) | practitioner-lore | tooling |
| C09-83 | The third tier above "recommended" — Databento Unlimited at $3,500/month, an Exegy/Vela appliance, kdb+, and Kpler — is what separates a small prop shop from a market-making franchise and is unnecessary for `KXSOYBEANW` alone. | §9 (line 181) | practitioner-lore | tooling;market-structure |

## 3. What this file does NOT claim

- It does not specify Appendix-A-defined per-product position limits in dollars beyond the placeholder default of $25,000; the actual Appendix-A figures for `KXSOYBEANW` are deferred (C09-75).
- It does not give a precise Premier-tier or Paragon-tier price (those tiers are described as unpublished; C09-19).
- It does not quantify the discount factors on cancels, single-order reads, or quote create/cancel — only that they exist and that batch submits are uncapped (C09-17).
- It does not specify N (hedge-heartbeat seconds) or K (WebSocket reconnect/minute) for the kill-switch, leaving these as caller-configurable thresholds (C09-73).
- It does not commit to a specific SVI versus Figlewski-GEV implementation for the option-surface fit; both are alluded to but not chosen.
- It does not give a numeric tick-to-quote latency requirement for the Recommended stack, only the MVS budget of 40–60 ms (C09-58).
- It does not propose a schema for the reconciliation table beyond its key columns (C09-80).
- It does not specify volume thresholds at which intraday RND refresh becomes PnL-justified (the trigger for stepping up to Databento Plus is qualitative; C09-35).
- It does not enumerate which order-group semantics (TTL, idempotency, max members) apply to `POST /order-groups/{group_id}/trigger` (C09-72).
- It does not address authentication-key rotation cadence or hardware-security-module storage policy for the RSA-PSS private key.

## 4. Cross-links

- C09-04 / C09-05 (RSA-PSS auth, no query in signed message) and C09-15 (rate-limit tiers) inherit from Phase 7 §1; any Phase-7 audit revisiting auth or rate-limit numbers must be kept consistent here.
- C09-26 (Rule 4.1–4.5 MM designation, 10× Position Accountability Levels) and C09-75 (Rule 5.19 dollar-denominated limits) are restatements of Phase 7 §5 and §6; Phase 7 audit is the authoritative source if there is any conflict.
- C09-31, C09-33, C09-34, C09-35, C09-70 (Breeden–Litzenberger / SVI / Figlewski-GEV chain requirements) all depend on Phase 8 §2's RND construction; if Phase 8 changes the calibration target or cadence, the data-cost tiering here must be re-derived.
- C09-39 through C09-44 (U.S. and South American weekly fundamentals) are a strict pruning of Phase 6 §4–§6; any expansion of the in-window release set in Phase 6 propagates to the MVS here.
- C09-45 through C09-50 (weather feeds) prune Phase 6 §7–§8 and Phase 3 §4; C09-50's DTN/ProphetX recommendation depends on Phase 3 §1.2 still listing ProphetX as the cash-bid carrier.
- C09-51, C09-53 (logistics: GTR, LPMS, COT survive; AIS/Kpler deferred) prune Phase 6 §9–§10; if Phase 6 raises the cadence-relevance bar for any of these, the MVS table changes.
- C09-54 (no-colocation argument) leans on Phase 7 §7 (full cash collateralization) and on the CBOT Rule 813 settlement-window claim; an inconsistency in Phase 7 §7 invalidates this conclusion.
- C09-67 (kdb+/OneTick/Deltix off-budget) and C09-66 (ArcticDB recommended) restate Phase 3 §7.1's tooling-cost tier.
- C09-83 (third-tier Databento Unlimited / Exegy / Kpler) inherits cost figures from Phase 3 §1.1 and §7.1.
- C09-29 (Databento Standard/Plus pricing) and C09-33 (DataMine EOD) restate Phase 3 §1.1; price drift in Phase 3 propagates here.
