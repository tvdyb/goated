# ACT-LIP-POOL — Handoff

**Action.** LIP pool data ingest
**Status.** complete-pending-verify
**Wave.** 0
**Implementer.** Claude agent
**Date.** 2026-04-27

---

## What was done

Implemented the LIP (Liquidity Incentive Program) pool data ingest module.
This module pulls active LIP reward periods and pool sizes per KXSOYBEANW
market, persists them to DuckDB, and supports daily refresh.

### Files created

- `feeds/kalshi/lip_pool.py` -- Main module containing:
  - `LIPRewardPeriod` dataclass (frozen, slotted, validated)
  - `LIPPoolError` / `LIPPoolDataError` exceptions (fail-loud)
  - `LIPPoolStore` -- DuckDB-backed persistence (upsert, query active/per-market/all, mark_expired, total_active_pool_usd, export_parquet)
  - `load_config_pools()` -- YAML config loader (fallback data source)
  - `parse_api_lip_data()` -- Kalshi REST API response parser (probes multiple plausible field names)
  - `refresh_lip_pools()` -- async orchestrator (config + API + upsert + expire)
- `tests/test_lip_pool.py` -- 29 tests covering all listed test plan items
- `state/action_lip_pool/plan.md` -- Implementation plan

### Data model

```
LIPRewardPeriod(
    market_ticker: str,       # e.g. "KXSOYBEANW-26APR27-17"
    pool_size_usd: float,     # e.g. 250.00
    start_date: date,
    end_date: date,
    active: bool,
    source: str,              # "api" | "config" | "manual"
    captured_at: datetime,
)
```

### DuckDB table

```sql
lip_reward_periods (
    market_ticker  VARCHAR NOT NULL,
    pool_size_usd  DOUBLE NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    active         BOOLEAN NOT NULL,
    source         VARCHAR NOT NULL,
    captured_at    TIMESTAMP NOT NULL,
    UNIQUE (market_ticker, start_date, end_date)
)
```

### Data source strategy

1. **Config-first**: `config/lip_pools.yaml` overrides API data. This is the
   initial operational mode since Kalshi may not expose LIP pool info via API.
2. **API probe**: Checks `GET /markets/{ticker}` for LIP-related fields
   (`liquidity_incentive`, `lip`, `reward_pool`, `pool_size`, etc.).
3. Config and API are composable -- config takes precedence on conflicts.

### Design decisions

- DuckDB TIMESTAMP (naive UTC) used instead of TIMESTAMPTZ to avoid pytz
  dependency in DuckDB fetch path.
- Upsert via DELETE + INSERT (DuckDB ON CONFLICT support varies by version).
- `mark_expired()` uses count-before-update pattern (DuckDB has no `changes()` scalar).
- YAML chosen for config format (consistent with existing `commodities.yaml`).

---

## Test results

29/29 tests pass. Full project suite: 343 passed, 1 pre-existing failure
(unrelated `test_kalshi_ws.py::TestRunLoop::test_run_forever_reconnects`).

Test coverage:
- Data model validation (empty ticker, negative pool, end < start, invalid source, frozen)
- DuckDB write/read roundtrip, upsert update, multi-market, active filter, per-market query
- Mark expired logic
- File-backed persistence (open, close, reopen)
- Config YAML loading (valid, missing, malformed, missing fields, non-list)
- API response parsing (no LIP data, nested field, top-level fields, malformed, non-dict)
- Refresh orchestrator (config source, fail-loud on empty, existing store OK, expire on refresh)

---

## Non-negotiables compliance

- No pandas: DuckDB direct throughout.
- Type hints: all public interfaces typed.
- Fail-loud: `LIPPoolDataError` on missing/corrupted data; `ValueError` on invalid model fields.
- asyncio for I/O only: `refresh_lip_pools` is async; DuckDB ops are sync.
- No silent failures: empty store + no data sources raises immediately.

---

## Downstream unblocked

- **ACT-LIP-SCORE** (needs ACT-04 + ACT-LIP-POOL): ACT-LIP-POOL dep now met; still blocked on ACT-04.
- **ACT-LIP-VIAB** (needs ACT-01 Ph1a + ACT-LIP-POOL): ACT-LIP-POOL dep now met; ACT-01 Ph1a verified. Both deps met.
- **ACT-LIP-MULTI** (Wave 3, needs ACT-LIP-POOL): ACT-LIP-POOL dep now met.

---

## Verify checklist

- [ ] `pytest tests/test_lip_pool.py -v` -- 29/29 pass
- [ ] Full suite `pytest` -- no regressions from this change
- [ ] `feeds/kalshi/lip_pool.py` imports cleanly
- [ ] `LIPPoolStore(":memory:")` instantiates without error
- [ ] Manual: create `config/lip_pools.yaml` with sample data, run refresh, verify DuckDB content

---

## Open items for downstream

- The Kalshi REST API LIP field names in `parse_api_lip_data` are speculative.
  When ACT-03 is verified and real API calls are made, the field names should
  be confirmed and updated if needed.
- `config/lip_pools.yaml` does not exist yet. The operator should create it
  from Kalshi market pages before running `refresh_lip_pools` in production.
