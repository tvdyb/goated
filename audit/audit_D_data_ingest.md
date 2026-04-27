# Audit Phase D — Topic 3: Data Ingestion and Feeds

## 1. Scope

Phase D, topic 3 evaluates whether the code under `feeds/`,
`state/tick_store.py`, `engine/scheduler.py`, and the YAML config under
`config/` implements, partially implements, contradicts, or ignores the
`data-ingest` claims from Phase C. The research corpus describes a Kalshi
weekly soybean market-making stack (CBOT MDP 3.0 + USDA + weather + logistics
+ Kalshi REST/WS + EOD chains). The code implements one producer —
`PythHermesFeed` against Pyth's Hermes WebSocket for WTI crude — and a
per-commodity ring buffer reader. The audit focuses on the file-specific
questions in the prompt: per-stream latency vs. strategy horizon,
publication-time handling, holiday/session calendars per stream, stream- and
source-level redundancy, backfill on reconnect, and schema-drift tolerance.

Files in scope (verified against `audit/audit_A_cartography.md:215-227`):
`feeds/pyth_ws.py`, `feeds/__init__.py` (empty), `state/tick_store.py`,
`engine/scheduler.py` (skeleton), `config/pyth_feeds.yaml`,
`config/commodities.yaml`. All Phase C distillations
(`audit/audit_C_phase01..10*.md`) were filtered to `data-ingest` claims; Phase
B deep-dives in scope are `audit/audit_B_feeds-pyth.md`,
`audit/audit_B_state-tick-store.md`, `audit/audit_B_engine-scheduler.md`. No
expected Phase B file is missing. Gap classes: `missing`, `wrong`, `partial`,
`already-good`, `divergent-intentional`. Severity: `blocker`, `major`, `minor`,
`nice-to-have`.

A standing observation: the research targets the CBOT soybean complex
(`audit_C_phase06_data_streams.md:5, 105-119`); the only implemented feed
targets WTI via Pyth (`feeds/pyth_ws.py:46-58`, `config/pyth_feeds.yaml:11-16`).
Pyth is not named in any Phase C `data-ingest` claim. The single live feed is
therefore `divergent-intentional` from the research's primary subject, and
almost every soybean-stack claim is `missing` against a code base with no
soybean ingestion path at all.

## 2. Audit table

| C-id | Claim (short) | What code does | Gap class | Severity | Code citation(s) | Notes |
|---|---|---|---|---|---|---|
| C03-01 (`audit_C_phase03_tooling.md:39`) | Soybean-complex feed must support ZS/ZM/ZL on MDP 3.0. | No feed handler for ZS/ZM/ZL exists; soy stub is parse-only. | missing | blocker | `feeds/pyth_ws.py:1-145` (only producer); `config/commodities.yaml:58-60` (`soy: stub: true`) | Belongs in `feeds/` next to `pyth_ws.py`; soy entry has no `pyth_feed_id`, no `cme_symbol`. |
| C03-02 (`audit_C_phase03_tooling.md:40`) | Direct ingest must implement SBE/FIX 5.0 SP2 decoding or rely on a vendor. | No SBE decoder, no FIX parser, no vendor wrapper. | missing | blocker | `feeds/pyth_ws.py:22-29` (imports only `asyncio, json, logging, dataclasses`); `pyproject.toml:14-19` (no SBE/FIX deps) | Repo has no MDP 3.0 ingest of any form. |
| C03-03 (`audit_C_phase03_tooling.md:41`) | Downstream books must distinguish MBP vs MBO state machines. | No order-book reconstruction at any granularity. | missing | major | `state/tick_store.py:31-66` (only stores last aggregate price + n_publishers); no `*book*.py` file in repo | Tick ring stores one price per push; no bid/ask/depth fields. |
| C03-04 (`audit_C_phase03_tooling.md:42`) | Full-depth book reconstruction requires MDP Premium or vendor depth. | No depth book at all. | missing | major | `state/tick_store.py:23-28` (`LatestTick` carries only `ts_ns, price, n_publishers, seq`) | The ring schema cannot represent MBO. |
| C03-08 (`audit_C_phase03_tooling.md:46`) | Databento `GLBX.MDP3` is the default prosumer route. | No Databento client. | missing | blocker | `pyproject.toml:14-19` (no `databento` dep); `feeds/__init__.py:1` (empty package) | C09-29 reiterates this for the Kalshi MVS; same gap. |
| C03-44 (`audit_C_phase03_tooling.md:82`) | USDA AMS GTR weekly CSV is the free U.S. logistics baseline. | No GTR ingester. | missing | minor | repository-wide: no `gtr*` or `transportation*` source file (`feeds/` contains only `pyth_ws.py`, `__init__.py`) | Weekly cadence; not on the millisecond hot path but C09-51 lists it as MVS. |
| C03-46-C03-49 (`audit_C_phase03_tooling.md:84-87`) | ECMWF IFS / GFS / ERA5 / NASA POWER fill the NWP layer. | No NWP ingester. | missing | major | `feeds/__init__.py:1`; no `weather*.py` anywhere; `pyproject.toml:14-19` (no GRIB2/`xarray`/`cfgrib`/`herbie` deps) | Phase 6 §7 (C06-40-C06-48) restates this for the soybean window. |
| C03-53 (`audit_C_phase03_tooling.md:91`) | WASDE monthly 12:00 ET event-clock encoding required. | No WASDE clock; only `EIA_crude` Wednesday hard-coded for WTI. | missing | major | `config/commodities.yaml:24-28` (only one event entry, oil); `engine/event_calendar.py:30-38` (WTI session only — see `audit_A_cartography.md:298-301`) | Soy has no `event_calendar` block at all (`config/commodities.yaml:58-60`). |
| C03-54 (`audit_C_phase03_tooling.md:92`) | NASS Crop Progress weekly Mon 16:00 ET windows must align. | No Crop Progress windowing. | missing | major | `config/commodities.yaml:58-60` (soy stub, no calendar); no `nass*.py`, no `crop_progress*` source | Same code-location gap as C03-53. |
| C03-55 (`audit_C_phase03_tooling.md:93`) | FAS Weekly Export Sales Thursday 08:30 ET — pre-release risk gate. | No risk-gate around the slot. | missing | blocker | `engine/event_calendar.py:1-110` (only τ math, no pre-release gate); no `risk*.py`, no `release*.py` in repo | C06-27 makes the "widen-or-pull at the 30-second window" practitioner rule explicit. |
| C03-56 (`audit_C_phase03_tooling.md:94`) | NASS Quick Stats / FAS GAIN / FOIA bulk are the three USDA ingest paths. | None of the three are implemented. | missing | major | `pyproject.toml:14-19` (no `httpx`/`requests` actually used — `httpx` is declared but cartography red flag #3 at `audit_A_cartography.md:246-249` notes zero importers); `feeds/__init__.py:1` (empty) | `httpx` declared but unused → would have to be wired. |
| C03-57 (`audit_C_phase03_tooling.md:95`) | CONAB monthly state-level S&D as SAm WASDE-parallel. | No CONAB ingester. | missing | minor | `feeds/__init__.py:1`; no `conab*.py` | Monthly cadence; misses the SAm-window ingest. |
| C03-58 (`audit_C_phase03_tooling.md:96`) | BCBA/BCR Argentine weekly + daily Rosario/Paraná cash quotes. | None. | missing | minor | `feeds/__init__.py:1` | C06-31, C06-32 echo this. |
| C03-59 (`audit_C_phase03_tooling.md:97`) | GACC monthly Chinese imports by HS code. | None. | missing | minor | `feeds/__init__.py:1` | C06-34 echoes. |
| C03-79 (`audit_C_phase03_tooling.md:117`) | CFTC COT Friday 15:30 ET — slot must be encoded. | No COT slot. | missing | minor | `config/commodities.yaml:24-28` (no COT entry); `engine/event_calendar.py:30-38` (no COT) | C06-64 reiterates; C10-27 reiterates. |
| C03-87 (`audit_C_phase03_tooling.md:125`) | Retail-quant baseline = Barchart delayed + Databento PAYG + NASS + CONAB + BCR + ECMWF/GFS + pandas/polars/DuckDB/Backtrader. | Of the eight named sources only "pandas/numpy" exists in the actual stack; ingest sources are all absent. | missing | major | `pyproject.toml:9-20` (numpy, scipy, numba, pyyaml, websockets, httpx, structlog, dateutil, pytz — but per `audit_A_cartography.md:246-249`, httpx/structlog/dateutil/pytz are declared and never imported) | The compute deps exist; the data deps do not. |
| C06-01 (`audit_C_phase06_data_streams.md:11`) | CME MDP 3.0 (`GLBX.MDP3`) — UDP multicast or vendor redistribution. | None. | missing | blocker | `feeds/pyth_ws.py:120-145` (sole network producer is the Pyth Hermes WebSocket) | The repo's "feed" surface is a single TCP/WSS, not UDP. |
| C06-07 (`audit_C_phase06_data_streams.md:17`) | ZS/ZM/ZL options on MDP — needed for the RND. | None. | missing | blocker | `state/iv_surface.py` (cited at `audit_A_cartography.md:217`) holds an *ATM IV scalar*, not a chain | The whole option surface is a single number; no strike axis exists. |
| C06-08 (`audit_C_phase06_data_streams.md:18`) | Greeks/IV surface are not exchange-published; compute or buy. | The IV "surface" is a single ATM value gated by staleness. | partial | major | `state/iv_surface.py:21-48` (per-commodity `(sigma, ts_ns)`); `engine/pricer.py` (consumes σ scalar per `audit_B_engine-pricer.md:285-288`) | Has the staleness gate; lacks chain ingest, lacks SVI/Figlewski (Phase 8 / C09-70). |
| C06-09 (`audit_C_phase06_data_streams.md:19`) | CVOL EOD benchmark + intraday DataMine stream. | None. | missing | minor | `feeds/__init__.py:1` (no `cvol*.py`) | `vol_source: implied_weekly_atm` (`config/commodities.yaml:15`) implies a chain that does not arrive. |
| C06-10/11/12 (`audit_C_phase06_data_streams.md:20-22`) | Rule 813 settlement; Daily Bulletin preliminary 12:00 a.m. CT, final 10:00 a.m. CT next BD. | No settle / bulletin ingester. | missing | blocker | `config/commodities.yaml:1-85` (no settlement field); no `bulletin*.py` | Settlement reference is the contract resolution per C09-54; absence is contract-level. |
| C06-13 (`audit_C_phase06_data_streams.md:23`) | Soybean daily volume 200k+, OI ~900k. | Not encoded; no liquidity model. | missing | nice-to-have | repo grep returns no `volume`/`open_interest` constants outside research/ | Out of scope of pure ingest but observed on the inventory layer. |
| C06-14-C06-23 (`audit_C_phase06_data_streams.md:24-33`) | WASDE / Crop Progress / FAS ESR / FGIS / Prospective Plantings / Acreage / Grain Stocks publication grid. | None of the publication times are encoded. | missing | major | `config/commodities.yaml:24-28` (only `EIA_crude` Wed 10:30 ET on WTI); `engine/event_calendar.py:30-38` (only WTI hours, see `audit_A_cartography.md:298-301`) | A USDA publication grid is the file-specific audit question (publication-time handling). |
| C06-24/25 (`audit_C_phase06_data_streams.md:34-35`) | NASS Quick Stats REST + 50k row cap + discovery endpoints. | None. | missing | minor | `feeds/__init__.py:1` | API key plumbing absent. |
| C06-27 (`audit_C_phase06_data_streams.md:37`) | A book widens or pulls through the 30-second pre-release window. | No release-window risk gate; pricer never widens. | missing | blocker | `engine/pricer.py:55-89` (synchronous reprice with no event-clock branch — see `audit_B_engine-pricer.md:140-158`); no `widen*` or `pull*` symbol in repo | The "publication-time handling" file-specific audit question. |
| C06-31/32/33 (`audit_C_phase06_data_streams.md:41-43`) | BCBA Thursdays 15:00 ART, BCR weekly, "SAm beats US Nov-Jun". | None of those streams or that calendar partition are present. | missing | minor | `config/commodities.yaml:24-28` (no SAm calendar) | Calendar partition is the holiday/session-per-stream audit question. |
| C06-39 (`audit_C_phase06_data_streams.md:49`) | The informative GACC signal is the residual vs. AIS-inferred cargo. | No GACC, no AIS, no residual. | missing | nice-to-have | `feeds/__init__.py:1` | Derived signal; depends on two missing primitives. |
| C06-40-C06-48 (`audit_C_phase06_data_streams.md:50-58`) | NOAA CPC, GEFS v12 (4×/day, 35-day on 00 UTC), ECMWF IFS open data on AWS/Azure/GCP, AIFS, ENS, ERA5. | None. | missing | major | `pyproject.toml:14-19` (no `xarray`, `cfgrib`, `herbie`, `eccodes`, `boto3`); no `weather*.py` | Holiday/session per-stream: weather streams have UTC cycle calendars not encoded. |
| C06-51 (`audit_C_phase06_data_streams.md:61`) | Sentinel-2 L2A 10–20 m at 5-day revisit, free. | None. | missing | nice-to-have | `feeds/__init__.py:1` | Satellite ingest absent. |
| C06-52/53 (`audit_C_phase06_data_streams.md:62-63`) | NASA SMAP L3/L4 soil moisture; Earthdata Login required. | None. | missing | nice-to-have | `feeds/__init__.py:1` | Auth surface absent. |
| C06-54 (`audit_C_phase06_data_streams.md:64`) | U.S. Drought Monitor Thursdays 08:30 ET as GeoJSON/TopoJSON. | None. | missing | nice-to-have | `feeds/__init__.py:1` | |
| C06-55-C06-58 (`audit_C_phase06_data_streams.md:65-68`) | GTR weekly Thursdays; LPMS 30-min cadence; NDC archive; Baltic BPI/BSI EOD. | None. | missing | minor | `feeds/__init__.py:1` | LPMS 30-min is highest-cadence among these. |
| C06-61/62 (`audit_C_phase06_data_streams.md:71-72`) | Kpler/MarineTraffic AIS REST/GraphQL; soy-tagged cargo. | None. | missing | nice-to-have | `feeds/__init__.py:1` | |
| C06-64-C06-69 (`audit_C_phase06_data_streams.md:74-79`) | CFTC COT Fridays 15:30 ET, Disaggregated since 2006, CSV/XML/RDF/TSV/RSS/HTML; Bank Participation monthly. | None. | missing | minor | `config/commodities.yaml:24-28` (no COT or BPR slots) | Three-day-stale weekly positioning. |
| C06-70/71 (`audit_C_phase06_data_streams.md:80-81`) | DXY, USD/BRL, USD/ARS, USD/CNY, WTI/Brent/ULSD as cross-asset coefficients at tick. | None. | missing | major | `feeds/__init__.py:1`; no `fx*.py` | The ingest side; the model `vol_fallback: ewma_30d` (`config/commodities.yaml:16`) implies cross-asset features that do not arrive. |
| C06-79/80 (`audit_C_phase06_data_streams.md:89-90`) | Barchart `getGrainBids` / DTN ProphetX cash-bid REST. | None. | missing | minor | `feeds/__init__.py:1` | Cash-bid feed is the Phase 03 retail-quant lever (C03-87). |
| C06-82 (`audit_C_phase06_data_streams.md:92`) | CME EOD Settlements (ZS/ZM/ZL) preliminary 12:00 a.m. CT, final 10:00 a.m. CT. | None. | missing | blocker | `config/commodities.yaml:1-85` (no settlement-pull field) | Required to validate Kalshi settlement reference (C09-54). |
| C06-84 (`audit_C_phase06_data_streams.md:94`) | Microstructure category — latency *is* the value. | Hot-path measured at p99 ~18 µs (`README.md:13-19`) is the *math*, not the ingest. The ingest has a 2 s staleness budget (`config/commodities.yaml:9`); per-message ingest latency is unmeasured. | partial | major | `engine/pricer.py:60-65` (staleness gate cited via `audit_B_engine-pricer.md`); `config/commodities.yaml:9` (`pyth_max_staleness_ms: 2000`); `feeds/pyth_ws.py:120-145` (no per-frame timestamp probe) | Per-stream-latency audit question: code expresses a *bound*, not a measurement. |
| C06-88 (`audit_C_phase06_data_streams.md:98`) | Minimum complete pipeline = MDP 3.0 + USDA parsers + SECEX/BCBA/BCR + ECMWF/GEFS + Baltic + AIS + COT + cash-bid API. | One-of-eight is partial: there is a streaming aggregate price feed (Pyth, not MDP 3.0) for one commodity (WTI, not ZS/ZM/ZL). The other seven are absent. | partial | blocker | `feeds/pyth_ws.py:1-145` (the only ingest); `feeds/__init__.py:1` (no siblings) | The architectural roll-up: all-but-one of the C06-88 layers are missing. |
| C06-89 (`audit_C_phase06_data_streams.md:99`) | All catalog entries cite a primary publisher URL. | Only `hermes_endpoint` and `hermes_http` are present in config. | missing | nice-to-have | `config/pyth_feeds.yaml:7-8` | No registry of source URLs for any other stream. |
| C07-07 (`audit_C_phase07_kalshi_contract.md:17`) | `GET /events/{ticker}` for `floor_strike`, `cap_strike`, `strike_type` per child market. | No Kalshi REST client. | missing | blocker | `feeds/__init__.py:1`; `pyproject.toml:14-19` (no Kalshi/RSA-PSS deps in any importer); `audit_A_cartography.md:99-100` (cartography records "no Kalshi-specific code") | Bucket grid is the contract enumeration. |
| C07-87/89/90/91/93/94 (`audit_C_phase07_kalshi_contract.md:97-104`) | Kalshi REST base URL; markets/events/historical/orderbook/candlesticks; WS multiplex; subscribe by `market_ticker`. | None of these endpoints are touched. | missing | blocker | `feeds/__init__.py:1`; no `kalshi*.py` in repo | Same gap as C07-07. |
| C07-62 (`audit_C_phase07_kalshi_contract.md:72`) | Rule 5.13 — top-5 levels of book depth visible to members. | No book reconstruction at any depth. | missing | major | `state/tick_store.py:23-28` (no level/depth fields) | |
| C08-15 (`audit_C_phase08_synthesis_pricing.md:40`) | Raw CME option prices need careful smoothing — naive twice-diff is catastrophic. | No raw option ingest of any form. | missing | blocker | `state/iv_surface.py` (per cartography `audit_A_cartography.md:217`, ATM scalar only); `models/gbm.py` (single-strike GBM, no chain math) | Pre-condition (raw chain) does not exist; the smoothing question is moot. |
| C08-94/95 (`audit_C_phase08_synthesis_pricing.md:119-120`) | Scheduled USDA event grid + unscheduled GEFS/ECMWF/SMAP drivers. | One scheduled WTI event (`EIA_crude`) is encoded; nothing for soy. | missing | major | `config/commodities.yaml:24-28` (WTI entry); soy stub at `:58-60` has no `event_calendar` block | |
| C08-100 (`audit_C_phase08_synthesis_pricing.md:125`) | Pipeline stage A — surface ingest streams MDP 3.0 ZS futures + options, accumulates per-strike mid IV, enforces put-call parity. | None of stage A is present. | missing | blocker | `feeds/pyth_ws.py:60-118` (single-aggregate-price parser); no `parity*` or `arbfree*` symbol in repo | |
| C08-110 (`audit_C_phase08_synthesis_pricing.md:135`) | Pipeline stage K — Kalshi REST `/portfolio/orders` post-only + WS `orderbook_delta/ticker/trade/fill` + token bucket + 429 backoff. | No Kalshi REST, no Kalshi WS, no token bucket, no 429 handler. | missing | blocker | `feeds/pyth_ws.py:138-145` (the only retry is a linear OS-error reconnect on Hermes; cf. `audit_B_feeds-pyth.md:140-145`) | The 429-backoff question maps to C09-18. |
| C09-01-C09-05 (`audit_C_phase09_kalshi_stack.md:11-15`) | Kalshi prod/demo URLs, WS URL, RSA-PSS-signed headers (key/timestamp/signature). | None. | missing | blocker | `pyproject.toml:14-19` (no `cryptography` dep); `feeds/__init__.py:1` | RSA-PSS signing requires `cryptography` or equivalent — no such importer exists. |
| C09-13/14 (`audit_C_phase09_kalshi_stack.md:23-24`) | Kalshi WS multiplex carries `orderbook_delta/ticker/trade/fill/...`; subscribe by `market_ticker`. | None. | missing | blocker | `feeds/pyth_ws.py:130` (only one WS subscribe, on Pyth `{type:"subscribe", ids:[...]}`) | |
| C09-15-C09-18 (`audit_C_phase09_kalshi_stack.md:25-28`) | Tiered tokens-per-second, 10-token default cost, no `Retry-After` on 429 — local backoff required. | No token bucket; the only retry path is linear OS-error reconnect. | missing | blocker | `feeds/pyth_ws.py:138-145` (`reconnect_backoff_s * attempt`, no token bucket; cf. `audit_B_feeds-pyth.md:144-145`) | The "stream-level redundancy / 429 handling" file question. |
| C09-22-C09-24 (`audit_C_phase09_kalshi_stack.md:32-34`) | Kalshi historical cutoff; no public bulk depth backfill; tape captured forward from first subscribe. | No Kalshi ingest at all; the Pyth client also has no backfill on reconnect. | missing | blocker | `feeds/pyth_ws.py:120-145` (reconnect re-issues `subscribe` — no historical backfill, no SSE pull from `hermes_http` at `config/pyth_feeds.yaml:8`) | The "backfill behaviour on reconnect" file question. The Pyth client's behaviour matches the Kalshi rule by accident: reconnect ignores the gap. |
| C09-28-C09-30 (`audit_C_phase09_kalshi_stack.md:38-40`) | Cheapest CME L1 = via FCM; Databento Standard for history; live → FCM, history → Databento. | None. | missing | blocker | `feeds/__init__.py:1` (no FCM client, no Databento client) | |
| C09-31-C09-36 (`audit_C_phase09_kalshi_stack.md:41-46`) | RND requires CBOT option chain at every reprice; CME DataMine EOD chains adequate weekly; CVOL is regime filter. | No chain ingest of any form. | missing | blocker | `state/iv_surface.py` (ATM scalar only per `audit_A_cartography.md:217`); `engine/pricer.py:55-89` (consumes σ scalar per `audit_B_engine-pricer.md`) | Pre-condition for Phase 8 RND. |
| C09-39-C09-44 (`audit_C_phase09_kalshi_stack.md:49-54`) | Weekly U.S. fundamentals: NASS Crop Progress Mon 16:00 ET, FAS ESR Thu 08:30 ET, FGIS Mon afternoon; WASDE 2nd Tue 12:00 ET; SAm BCBA Thu 15:00 ART; NASS Quick Stats / FAS ESRQS / FGIS Socrata are free. | None. | missing | major | `feeds/__init__.py:1`; no `usda*.py`, no `nass*.py`, no `fas*.py`; `config/commodities.yaml:58-60` (soy stub, no calendar) | Cadence calendar is the publication-time + holiday/session audit question. |
| C09-45-C09-50 (`audit_C_phase09_kalshi_stack.md:55-60`) | Weather: GEFS 4×/day; ECMWF IFS CC-BY-4.0 since late 2025, +2 h on AWS/Azure/GCP; HRRR 3 km nowcast; CPC 6–10 / 8–14 daily; SMAP daily / 3-hourly; Drought Monitor Thu 08:30 ET. | None. | missing | major | `pyproject.toml:14-19` (no GRIB2/`xarray`/`cfgrib`/`pygrib` deps); no `weather*.py` | Per-stream cycle calendars (00/06/12/18 UTC) are not encoded. |
| C09-51-C09-53 (`audit_C_phase09_kalshi_stack.md:61-63`) | 5-day-relevant logistics: GTR Thu free, USACE LPMS 30-min free, CFTC COT Fri 15:30 ET free; Barchart cash bids low-3-fig. | None. | missing | minor | `feeds/__init__.py:1`; no `lpms*.py`, no `cot*.py`, no `barchart*.py` | LPMS 30-min cadence is the highest among these. |
| C09-58 (`audit_C_phase09_kalshi_stack.md:68`) | Tick-to-quote 40–60 ms budget. | The compute path is p99 ≈ 18 µs (per `README.md:13-19`); the *ingest+amend* leg is unmeasured because no Kalshi amend exists. | partial | major | `engine/pricer.py:55-89` (synchronous reprice; per `audit_B_engine-pricer.md:140-158` no async `amend` is wired) | The compute headroom exists; the I/O leg is missing. Per-stream-latency vs. strategy-horizon question. |
| C09-62/63 (`audit_C_phase09_kalshi_stack.md:72-73`) | Three tapes must be stored: Kalshi WS, CME ZS/ZM/ZL L1+EOD chain, fundamentals/weather. Kalshi is critical because no backfill. | No tape capture for any of the three. The tick ring is in-memory and forward-only. | missing | blocker | `state/tick_store.py:31-66` (in-memory ring, default capacity 1,000,000, no disk sink — see `audit_B_state-tick-store.md:177-190, 327-329`); no `tape*`, no `s3*`, no `parquet*` source | The Pyth path is "store-as-you-go in RAM"; nothing persists across process restart. |
| C09-64/65 (`audit_C_phase09_kalshi_stack.md:74-75`) | DuckDB + Parquet on S3 with `httpfs`, per-day per-feed partitions. | No DuckDB import, no Parquet writer, no S3 client. | missing | major | `pyproject.toml:9-20` (no `duckdb`, no `pyarrow`, no `boto3`); no `parquet*` source | |
| C09-68 (`audit_C_phase09_kalshi_stack.md:78`) | EOD CME options stored as Parquet partitioned by trade-date and expiry. | No EOD chain, no Parquet. | missing | major | `pyproject.toml:9-20` (no `pyarrow`); no `chain*` source | |
| C10-10 (`audit_C_phase10_strategy_synthesis.md:22`) | GEFS / ECMWF 4×/day; AIFS +2 h since Oct 2025. | None. | missing | major | `pyproject.toml:14-19` (no GRIB2 deps); no `weather*.py` | C06-41-C06-45 echo. |
| C10-27 (`audit_C_phase10_strategy_synthesis.md:39`) | COT released after Friday Event settles → informs *next* week's prior. | No COT ingester; no "next-week prior" hook. | missing | minor | `engine/event_calendar.py:30-38` (no COT slot) | Coupled to C06-64. |
| C10-77 (`audit_C_phase10_strategy_synthesis.md:89`) | Milestone 0 — pull historical CME option chains via Databento Standard for any settled week, fit SVI/Figlewski, compute bucket probs. | No chain pull; calibration package is empty. | missing | major | `calibration/__init__.py` (per `audit_A_cartography.md:62-63, 230` — package is empty, `.gitkeep` only); no Databento client | |
| C01-33 / C01-51 / C01-69-C01-73 / C01-87 / C04-26-C04-30 / C04-32 / C04-70 / C04-84 / C04-86 (`audit_C_phase01_market_structure.md:59, 77, 95-99, 113`; `audit_C_phase04_discretionary.md:51-55, 57, 95, 109, 111`) | Restatements of the soybean USDA publication grid (08:30 CT re-open vs 11:00 ET embargo, Crop Progress Mon, WASDE / Plantings / Stocks / Acreage / CVOL / flash sales / NWP overlays / ONI). | Same code-side gap as C06-14-C06-23 / C03-53. | missing | major (minor for C01-87, C04-32, C04-70, C04-84/86) | `config/commodities.yaml:24-28, 58-60`; `engine/event_calendar.py:30-38` (WTI-only, per `audit_A_cartography.md:298-301`); `feeds/__init__.py:1` | Strict subset of C06-14-C06-23 / C06-40-C06-48. |
| C05-44 (`audit_C_phase05_systematic.md:68`) | Balance-sheet nowcaster ingests ESR weekly + NOPA monthly + Census crush + rail/barge + FGIS + satellite. | None of the six. | missing | major | `feeds/__init__.py:1` | |
| C05-50 / C05-52 (`audit_C_phase05_systematic.md:74, 76`) | NDVI = (ρ_NIR-ρ_RED)/(ρ_NIR+ρ_RED); GDD with T_base ≈ 50 °F for soy. | No NDVI / GDD compute. | missing | nice-to-have | `models/__init__.py` (per cartography); no `ndvi*` / `gdd*` source | |
| C05-55/56 (`audit_C_phase05_systematic.md:79-80`) | WASDE PDF/XLSX 12:00 ET; NLP pipeline parses balance sheet. | No PDF parser, no XLSX parser. | missing | major | `pyproject.toml:9-20` (no `pdfplumber`, `pypdf`, `openpyxl`) | |
| C05-60 (`audit_C_phase05_systematic.md:84`) | Point-in-time DB mandatory — USDA revises. | No PIT semantics anywhere. | missing | major | `state/tick_store.py:31-66` (overwrite-on-push ring; no version field, see `audit_B_state-tick-store.md:316-329`) | The ring is "current value", not "as-of value". |
| C02-37 / C02-41 (`audit_C_phase02_pricing_models.md:47, 51`) | Cont-Kukanov-Stoikov OFI per book update; OFI computable from MDP MBO/MBP top-3. | No OFI; no MBO/MBP feed. | missing | major | `state/tick_store.py:23-28` (no bid/ask fields); `feeds/__init__.py:1` (no MDP feed) | |
| (no C-id) | Pyth Hermes WebSocket implementation as the sole producer of WTI ticks. | Implemented; per-frame parser raises on schema violations; reconnects up to 5× linearly; never silently swallows. | divergent-intentional | major | `feeds/pyth_ws.py:60-118, 120-145` (parser + run loop); `audit_B_feeds-pyth.md:54-69` (failure-mode contract) | The research corpus does not name Pyth as a soybean source. The chosen source is divergent from research scope; the implementation itself is well-formed. |
| (no C-id, file question: schema drift) | Parser fail-loud on unknown fields. | Mostly fail-loud: every missing field in the documented Hermes shape raises `MalformedPythMessageError` — except `num_publishers`, which silently defaults to 0 and shifts the gate to the pricer. | partial | major | `feeds/pyth_ws.py:79-115` (raise-on-missing); `feeds/pyth_ws.py:112-115` (silent default); `audit_B_feeds-pyth.md:266-275` (red-flag #8 trace) | The "schema drift tolerance" file question. Mostly fail-loud, one fail-silent crack. |
| (no C-id, file question: backfill on reconnect) | On reconnect the gap is ignored. | Reconnect re-sends the `subscribe` frame; no SSE/REST pull for the gap window. | already-good (matches C09-23 by accident) | minor | `feeds/pyth_ws.py:128-130, 138-145` (re-subscribe; no historical fetch); `config/pyth_feeds.yaml:8` (`hermes_http` declared but no Python importer) | "Already-good" only if the policy intent matches Kalshi's "no backfill" rule (C09-23). For Pyth the SSE fallback exists in config but is never used. |
| (no C-id, file question: source/stream redundancy) | Single-source per commodity; no failover. | One feed per commodity; one endpoint per feed; no second WS, no second vendor; `hermes_http` in YAML is dead config. | missing | major | `config/pyth_feeds.yaml:7-8` (two URLs); `feeds/pyth_ws.py:48` (single `endpoint` field, only `hermes_endpoint` consumed) | The "stream- and source-level redundancy" file question. |
| (no C-id, file question: holiday/session calendars per stream) | Per-stream calendars per source. | Only one trading-hour calendar exists (WTI); no holiday handling, no per-stream publication calendar. | missing | major | `engine/event_calendar.py:30-38, 76-79` (single-commodity registration; per `audit_A_cartography.md:298-301` other commodities raise `NotImplementedError`); `config/commodities.yaml:24-28` (one event row, WTI-only) | The "holiday and session calendars per stream" file question. |
| (no C-id, file question: per-stream latency vs. strategy horizon) | Latency budget per stream matches the consumer's horizon. | The Pyth ingest has a 2 s staleness budget enforced *at consumer*, not measured at ingest; the compute path is p99 ≈ 18 µs; nothing in between is instrumented. | partial | major | `config/commodities.yaml:9` (`pyth_max_staleness_ms: 2000`); `engine/pricer.py:60-65` (staleness gate per `audit_B_engine-pricer.md`); `feeds/pyth_ws.py:120-145` (no per-frame ingest-latency probe); `engine/scheduler.py:36-59` (skeleton — `audit_B_engine-scheduler.md:191-217` confirms zero inbound importers) | The latency assertion is a *bound*, not a *measurement*. |

## 3. Narrative discussion of blockers and majors

The dominant fact across the table is that the implementation has one feed
(Pyth Hermes WebSocket for WTI crude) and the research describes a Kalshi
weekly soybean stack (`audit_C_phase06_data_streams.md:5`). Every soybean-stack
ingestion claim therefore lands in `missing`. The only claims that resolve to
`partial`, `divergent-intentional`, or `already-good` are the three file-specific
audit questions where the Pyth implementation makes a defensible engineering
choice that happens to align with a Phase C principle.

**Blocker tier — Kalshi pricing path absence.** A Kalshi `KXSOYBEANW` market
maker needs a CBOT options chain (C09-31, C08-100), a CBOT futures L1 stream
(C09-28), a Kalshi WebSocket with RSA-PSS-signed handshake (C09-01, C09-04), a
Kalshi REST surface for `/orders/*` (C08-110, C09-09), a token-bucket local
backoff because Kalshi 429 carries no `Retry-After` (C09-18), and a CBOT EOD
settlement reference (C09-54, C06-82). All six are absent. `feeds/__init__.py:1`
is empty; `pyproject.toml:14-19` declares `websockets`, `httpx`, `structlog`,
`python-dateutil`, `pytz` but per `audit_A_cartography.md:246-249` only
`websockets` is actually imported. The compute libraries (numpy, scipy, numba)
ship without the data libraries that would feed them: no `cryptography` for
RSA-PSS, no `databento`, no GRIB2 reader, no S3 client, no DuckDB, no PyArrow.

**Blocker tier — USDA / event-clock absence.** Multiple Phase C files restate
the soybean publication grid (C06-14-C06-23, C09-39-C09-44, C01-69-C01-73,
C04-26-C04-30, C08-94). The code expresses one event slot, `EIA_crude`
Wednesday 10:30 ET on WTI (`config/commodities.yaml:24-28`). The
`event_calendar` block is absent for the soy stub
(`config/commodities.yaml:58-60`), and `engine/event_calendar.py:30-38`
hard-codes WTI session hours only (`audit_A_cartography.md:298-301` records
that other commodities raise `NotImplementedError`). The highest-weight Phase C
blocker is C06-27 — books must widen or pull through the 30-second pre-release
window — and the pricer (`engine/pricer.py:55-89`, per
`audit_B_engine-pricer.md:140-158`) is a synchronous compose-and-return with no
event-clock branch. Even if USDA ingest existed, there is no widen-or-pull
hook to trip.

**Blocker tier — backfill and tape capture.** C09-23 / C09-24 / C09-62 / C09-63
collectively assert that Kalshi tape must be captured forward from first
subscribe because no backfill exists, and that three tapes must be persisted.
The code's only persistence is the in-memory tick ring
(`state/tick_store.py:31-66`); per `audit_B_state-tick-store.md:316-329` the
module owns no disk path. On process restart the state is gone. The Pyth client
re-issues the `subscribe` frame on reconnect (`feeds/pyth_ws.py:128-130`); the
SSE fallback `hermes_http` (`config/pyth_feeds.yaml:8`) has no Python importer
(`audit_B_feeds-pyth.md:493-496`). For Pyth this "reconnect ignores the gap"
behaviour matches C09-23 by accident — it is `already-good` only if the project
intends the same trade-off, which the code does not document.

**Major tier — schema-drift tolerance.** The Pyth parser is mostly fail-loud:
`feeds/pyth_ws.py:79-108` raises on a non-dict message, missing `price_feed`,
missing string `id`, missing `price` block, and parse failures on
`price`/`expo`/`publish_time`; `:96-97` raises `UnknownFeedError` on a
`price_update` for an unsubscribed id. This honors the docstring promise
(`feeds/pyth_ws.py:13-16`). The one crack is `num_publishers`, which
`:112-115` silently defaults to 0. Per `audit_B_feeds-pyth.md:266-275`
(cartography red flag #8) the WTI floor of 5 (`config/commodities.yaml:8`) then
rejects every such message at the Pricer. The fail-silent ingest path quietly
hands the Pricer a tick that will fail the publisher gate at every reprice in
production. Classification: `partial`, `major`.

**Major tier — per-stream latency vs. strategy horizon.** C06-84 names
microstructure as the only category where latency *is* the value. The code
expresses a per-stream staleness *bound* (`config/commodities.yaml:9`,
`pyth_max_staleness_ms: 2000`) enforced at the consumer
(`engine/pricer.py:60-65`). The compute leg is measured at p99 ≈ 18 µs
(`README.md:13-19`). The ingest leg — Hermes `publish_time` to
`ingest_message` — is not measured: `feeds/pyth_ws.py:120-145` has no per-frame
timestamp probe. The 2 s budget is liberal vs. the C09-58 40–60 ms tick-to-quote
window; whether the budget is set that loose because Pyth runs that hot or
because nobody measured is not visible from the code. Classification: `partial`,
`major`.

**Major tier — single-source-per-commodity.** The redundancy audit question is
answered by `config/pyth_feeds.yaml:7-8` (two URLs declared) and
`feeds/pyth_ws.py:48` (one endpoint field consumed). The HTTP/SSE fallback is
dead config (`audit_B_feeds-pyth.md:493-496`). There is no second WebSocket, no
second vendor, no failover, no circuit breaker. Reconnect exhausts after 5
linear attempts and raises `PythFeedError` (`feeds/pyth_ws.py:139-143`); per
`audit_A_cartography.md:98-100` no module supervises the producer
(`engine/scheduler.py` is the would-be supervisor but
`audit_B_engine-scheduler.md:191-217` confirms zero inbound importers).
Classification: `missing`, `major`.

**Major tier — holiday and session calendars per stream.** C06-31 (BCBA
Thursdays 15:00 ART) and C06-33 (SAm beats US Nov–Jun) imply per-stream
publication calendars in distinct time zones. The code has one trading-hour
calendar (WTI, `engine/event_calendar.py:30-38`,
`audit_A_cartography.md:298-301`). The single ART/ET/CT/UTC clock that would
let a release calendar render on the same axis as the Hermes `publish_time`
does not exist.

**Minor tier — observable but lower-cost gaps.** The minor entries (C03-44
GTR; C03-57 CONAB; C03-58 BCBA/BCR; C03-59 GACC; C03-79 / C06-64-C06-69 COT;
C06-31-C06-33 SAm calendar; C06-55-C06-58 GTR/LPMS/Baltic) are weekly-or-slower
streams whose absence costs information value but does not prevent trading,
because the Phase 8 RND path (C09-31) does not consume them on the hot loop
and Phase 6 §11 (C06-93) treats them as "research-desk-first, quoting-input-second."

## 4. Ambiguities

- **`num_publishers` policy at the feed boundary.** `feeds/pyth_ws.py:112-115`
  defaults to 0 with the comment "Hermes currently surfaces publisher count
  inconsistently"; the WTI floor of 5 (`config/commodities.yaml:8`) then
  rejects every such message at the Pricer
  (`audit_B_feeds-pyth.md:266-275`, red flag #8). Two readings: (i) placeholder
  pending a Pythnet/Solana RPC publisher source named in
  `feeds/pyth_ws.py:8-11` (table classification: `partial`/`major`); or
  (ii) deliberate fail-closed (would re-classify as `already-good`).
- **`hermes_http` SSE fallback intent.** `config/pyth_feeds.yaml:8` declares
  the URL with the comment "(never) the hot path" (`config/pyth_feeds.yaml:5`).
  No Python file references it (`audit_B_feeds-pyth.md:493-496`). Two readings:
  (i) planned redundancy not yet wired — `missing`; or (ii) smoke-test-only
  declaration matching the comment — `divergent-intentional`. The table treats
  source/stream redundancy as `missing` because no failover code exists at
  all, but the YAML comment is evidence the hot-path absence is intentional.
- **Backfill on reconnect.** The Pyth client's no-backfill behaviour matches
  Kalshi's C09-23 rule. Whether the match is intentional or coincidental is
  not in the code; the table classifies this as `already-good` *only* if the
  project intends the no-backfill stance.
- **`engine/scheduler.py` intent.** The `Priority.TICK = 0` lane
  (`engine/scheduler.py:22`) names a hot-path priority for a tick coroutine
  but `audit_B_engine-scheduler.md:191-217` confirms zero importers. Two
  readings: dead code, or staged for a future wiring step. Either reading
  leaves the source/stream-redundancy gap unaddressed: the scheduler holds no
  failover primitive even when read most charitably.
- **`vol_source: implied_weekly_atm` config field.** `config/commodities.yaml:15`
  names a vol source whose chain ingest is absent; `vol_fallback: ewma_30d`
  (`:16`) names a fallback whose realized-vol reader is not wired
  (`state/tick_store.py:9-11`; `audit_B_state-tick-store.md:546-552`). The
  string is configuration without implementation; forward declaration vs.
  placeholder is unclear.
- **Whether soy stubs are intended to resolve.** `config/commodities.yaml:58-60`
  marks `soy: stub: true`. The research targets the soybean complex; whether
  the soy stub is "next deliverable" or "out of scope" is not in the YAML or
  the README.

## 5. Open questions for maintainers

1. Is the soybean complex (ZS / ZM / ZL) intended to ship through Pyth Hermes
   or through CME MDP 3.0 + Databento per C03-08 / C09-29? The stub at
   `config/commodities.yaml:58-60` implies Pyth; research at
   `audit_C_phase06_data_streams.md:11` and `audit_C_phase09_kalshi_stack.md:38-40`
   prescribes MDP 3.0. The choice changes the entire feeds/ surface.
2. If Kalshi `KXSOYBEANW` is the trading venue (Phase 7, Phase 9), is the
   missing Kalshi REST/WS/RSA-PSS surface (C09-01-C09-18) deferred or is the
   project not building toward Kalshi? The cartography at
   `audit_A_cartography.md:243-245` records "no Kalshi code"; `README.md:3`
   calls itself a "Live Kalshi commodity theo engine."
3. How is the ingest-side latency between Hermes `publish_time` and the
   parser's first touch supposed to be measured? `feeds/pyth_ws.py:120-145`
   has no probe; the 2 s staleness budget at `config/commodities.yaml:9`
   bounds it but does not measure it.
4. What is the intended USDA event-clock plumbing? C06-27 prescribes a
   widen-or-pull risk gate; the codebase has no quote to widen. If USDA
   ingest comes online before the Kalshi quote layer, what does the gate
   hook into?
5. Is the no-backfill behaviour on Pyth reconnect a deliberate choice or an
   oversight? If deliberate, should `config/pyth_feeds.yaml:8`'s `hermes_http`
   line be removed to avoid implying a fallback that does not exist?
6. Is `num_publishers` defaulting to 0 (`feeds/pyth_ws.py:112-115`) intended
   as fail-closed or as a placeholder pending the Pythnet/Solana RPC publisher
   source named in `feeds/pyth_ws.py:8-11`?
7. Is `engine/scheduler.py` a forward declaration matching the docstring at
   `engine/scheduler.py:8-9`, or has the synchronous Pricer at
   `engine/pricer.py:55-89` (p99 ≈ 18 µs per `README.md:13-19`) made it
   obsolete?
8. Are weather (C03-46-C03-49, C09-45-C09-50, C10-10) and logistics
   (C09-51-C09-53) part of the MVS for this codebase or deferred beyond the
   Kalshi MVS budget? The ECMWF / GEFS open-data path is free (C03-47,
   C09-46), yet no GRIB2 reader is in `pyproject.toml:9-20`.
9. Is per-stream point-in-time semantics (C05-60) on the roadmap? The current
   ring (`state/tick_store.py:44-51`) overwrites on push and has no version
   field; USDA revisions (the C05-60 motivator) would need a different shape.
10. The `feeds/` directory contains exactly one producer; the README at
    `README.md:39` (per `audit_A_cartography.md:240-241`) lists "Pyth, CME,
    options, Kalshi, macro" as planned. Is the README aspirational, or is
    the directory expected to grow before the next review?

Sources:
[audit_A_cartography.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_A_cartography.md)
[audit_B_feeds-pyth.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_B_feeds-pyth.md)
[audit_B_state-tick-store.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_B_state-tick-store.md)
[audit_B_engine-scheduler.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_B_engine-scheduler.md)
[audit_C_phase01_market_structure.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase01_market_structure.md)
[audit_C_phase02_pricing_models.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase02_pricing_models.md)
[audit_C_phase03_tooling.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase03_tooling.md)
[audit_C_phase04_discretionary.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase04_discretionary.md)
[audit_C_phase05_systematic.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase05_systematic.md)
[audit_C_phase06_data_streams.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase06_data_streams.md)
[audit_C_phase07_kalshi_contract.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase07_kalshi_contract.md)
[audit_C_phase08_synthesis_pricing.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase08_synthesis_pricing.md)
[audit_C_phase09_kalshi_stack.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase09_kalshi_stack.md)
[audit_C_phase10_strategy_synthesis.md](computer:///Users/felipeleal/Documents/GitHub/goated/audit/audit_C_phase10_strategy_synthesis.md)
[feeds/pyth_ws.py](computer:///Users/felipeleal/Documents/GitHub/goated/feeds/pyth_ws.py)
[state/tick_store.py](computer:///Users/felipeleal/Documents/GitHub/goated/state/tick_store.py)
[engine/scheduler.py](computer:///Users/felipeleal/Documents/GitHub/goated/engine/scheduler.py)
[config/pyth_feeds.yaml](computer:///Users/felipeleal/Documents/GitHub/goated/config/pyth_feeds.yaml)
[config/commodities.yaml](computer:///Users/felipeleal/Documents/GitHub/goated/config/commodities.yaml)
