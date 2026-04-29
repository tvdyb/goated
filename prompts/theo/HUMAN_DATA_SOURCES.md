# Data Sources Checklist — For the Human Operator

Before running the theo prompt stack, you need the following accounts
and data sources. Items marked FREE require no payment. Items marked
PAID have a recurring cost.

---

## Required before T-00 (Pyth Forward)

Nothing new needed. Pyth Hermes API is free and unauthenticated.
Already configured in `config/pyth_feeds.yaml`.

---

## Required before T-40 (IBKR Options Chain)

### 1. IBKR Margin Account
- **Status:** You have this.
- **Action:** Ensure it's funded with at least $2,000 (minimum to keep active).
- **Cost:** Free (no monthly fee if balance > $2k).

### 2. CME Agricultural Market Data Subscription
- **Where:** IBKR Account Management → Settings → Market Data Subscriptions.
- **What to subscribe:** "CME Real-Time — Agricultural" or similar.
  Look for the package that includes ZS (soybeans) options.
- **Cost:** ~$10/month. PAID.
- **Why:** Without this, `ib.reqMktData()` returns delayed/empty data for ZS options.

### 3. IB Gateway
- **Download:** interactivebrokers.com → Technology → IB Gateway.
- **Install** on the machine running the bot.
- **Configure:**
  - Log in with IBKR credentials.
  - Select "Paper Trading" mode initially.
  - Settings → API → check "Enable ActiveX and Socket Clients".
  - Note the port: 4002 (paper) or 4001 (live).
  - Uncheck "Read-Only API" if you want to paper-trade the hedge leg.
- **Run:** IB Gateway must be running whenever the bot uses IBKR data.

---

## Required before T-60 (WASDE NLP)

### 4. USDA ERS API (optional)
- **URL:** https://api.ers.usda.gov/
- **Cost:** FREE. No API key needed for public data.
- **Alternative:** The prompt can scrape WASDE PDFs directly from
  https://usda.library.cornell.edu/concern/publications/3t945q76s
- **Action:** None — the T-60 prompt will figure out the best access method.

---

## Required before T-70 (Weather Skew)

### 5. NOAA GEFS Ensemble Forecasts
- **URL:** https://nomads.ncep.noaa.gov/
- **Cost:** FREE. No account needed.
- **What:** GFS/GEFS ensemble mean + spread for temperature and precipitation
  over the U.S. Corn Belt (Iowa, Illinois, Indiana, Ohio).

### 6. NOAA CPC Outlooks (optional, easier than raw GEFS)
- **URL:** https://www.cpc.ncep.noaa.gov/products/predictions/
- **Cost:** FREE.
- **What:** 6-10 day and 8-14 day temperature/precipitation outlooks.
  Pre-processed anomaly maps — much easier to parse than raw GEFS.

### 7. ECMWF AIFS Open Data (optional)
- **URL:** https://aifs.ecmwf.int/
- **Cost:** FREE (open data since Oct 2025). +2h latency vs operational.
- **Why:** Second opinion on weather — diversity of forecast sources improves
  the signal.

---

## No account needed (built from code/config only)

These phases need NO external data sources:

| Phase | What it uses |
|---|---|
| T-10 (Kalshi-implied vol) | Kalshi orderbook data (already pulling) |
| T-20 (Seasonal vol) | Hardcoded monthly lookup table |
| T-25 (Markout tracker) | Own fill data + subsequent theo updates |
| T-35 (Queue amend) | Kalshi API amend endpoint |
| T-80 (FLB overlay) | Own settlement history (collected over time) |
| T-85 (Goldman roll) | Public calendar (deterministic dates) |

---

## Summary

| Item | Cost | When needed |
|---|---|---|
| Pyth Hermes API | FREE | T-00 |
| IBKR margin account | FREE (have it) | T-40 |
| CME ag market data | ~$10/mo | T-40 |
| IB Gateway software | FREE | T-40 |
| USDA data | FREE | T-60 |
| NOAA weather data | FREE | T-70 |
| ECMWF AIFS | FREE | T-70 (optional) |
| **Total recurring cost** | **~$10/mo** | |

The only paid item is the $10/month CME data subscription on IBKR.
Everything else is free.
