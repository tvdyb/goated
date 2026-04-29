# ACT-LIP-POOL — Plan

**Action.** LIP pool data ingest
**Wave.** 0
**Effort.** M
**Deps.** ACT-03 (complete-pending-verify)

---

## Goal

Pull active LIP reward periods and pool sizes per KXSOYBEANW market from
Kalshi; persist to DuckDB; refresh daily. Without this data we cannot
compute expected pool share or run ACT-LIP-VIAB.

---

## Design

### Data model

```
LIPRewardPeriod:
    market_ticker: str          # e.g. "KXSOYBEANW-26APR27-17"
    pool_size_usd: float        # e.g. 250.00
    start_date: date            # reward period start
    end_date: date              # reward period end
    active: bool                # True while period is live
    source: str                 # "api", "config", or "manual"
    captured_at: datetime       # when we ingested this record
```

### Data source strategy

1. **Primary: Kalshi REST API market metadata.** The `GET /markets/{ticker}`
   endpoint returns market metadata. If Kalshi includes LIP pool info in the
   response (e.g. `liquidity_incentive` field), we parse it directly.

2. **Fallback: YAML config file.** Kalshi may not expose LIP pool data via
   API. In that case, the operator manually enters pool data from Kalshi
   market pages into `config/lip_pools.yaml`. The fetcher reads from config
   instead.

3. The module always checks config first (overrides), then API. This allows
   manual corrections even when API data exists.

### Persistence

DuckDB table `lip_reward_periods` following the CaptureStore pattern from
ACT-01. Schema:

```sql
CREATE TABLE IF NOT EXISTS lip_reward_periods (
    market_ticker  VARCHAR NOT NULL,
    pool_size_usd  DOUBLE NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    active         BOOLEAN NOT NULL,
    source         VARCHAR NOT NULL,
    captured_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (market_ticker, start_date, end_date)
);
```

Upsert semantics: on conflict (same market + period dates), update
pool_size_usd, active, source, captured_at.

### Refresh logic

- `refresh()` is called daily (or on-demand).
- Loads config overrides from `config/lip_pools.yaml` if present.
- For each KXSOYBEANW market, checks API for LIP metadata.
- Inserts new periods, updates existing ones, marks expired periods inactive.
- Fail-loud on corrupted/missing required data.

### Module location

`feeds/kalshi/lip_pool.py`

### Downstream consumers

- ACT-LIP-SCORE: reads pool sizes to project expected reward.
- ACT-LIP-VIAB: reads pool history for viability analysis.
- ACT-LIP-MULTI: reads pool data to prioritize market expansion.

---

## Non-negotiables

- No pandas. DuckDB direct.
- Type hints everywhere.
- Fail-loud on missing/corrupted data.
- asyncio for I/O (Kalshi API calls).
- Synchronous DuckDB persistence (DuckDB is not async).

---

## Test plan

1. Data model creation + validation (required fields, types).
2. DuckDB persistence: write + read back.
3. Upsert: new period inserted, existing period updated.
4. Expired period detection: periods past end_date marked inactive.
5. Config-based fallback: load from YAML when API unavailable.
6. Missing data: fail-loud on None pool_size, missing dates.
