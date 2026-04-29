# Phase 40 digest — CME Options Chain + Futures Ingest

**Date.** 2026-04-27
**Action.** F4-ACT-02 (CME ingest)
**Status.** complete-pending-verify

## What was delivered

New `feeds/cme/` package with 4 modules implementing CME options chain and futures settlement data ingest for ZS (soybean) and ZC (corn).

### Modules

| Module | Purpose | Lines |
|---|---|---|
| `feeds/cme/errors.py` | Error hierarchy: `CMEIngestError` > `CMEChainError`, `CMESettleError`, `CMEParityError` | ~30 |
| `feeds/cme/expiry_calendar.py` | CBOT options expiry calendar (ZS 7 months, ZC 5 months) | ~160 |
| `feeds/cme/futures_settle.py` | Daily settlement price puller (async, CME public API) | ~180 |
| `feeds/cme/options_chain.py` | EOD options chain puller with put-call parity check (async) | ~370 |

### Key design decisions

1. **Data source (OD-37 resolved):** CME Group public delayed settlement data via `cmegroup.com/CmeWS/mvc/Settlements/` endpoints. Free, no API key, structured JSON.
2. **Put-call parity (GAP-047):** Vectorized numpy check. Configurable threshold (default 2% of underlying). Raises `CMEParityError` if >25% of strikes violate. Returns violation indices for minor violations.
3. **Expiry calendar:** Uses existing `engine.event_calendar._is_cbot_trading_day` for CBOT holiday awareness. Follows CBOT rule: options expire on the last Friday >= 2 BD before FND.

## Gaps closed

| Gap | Description |
|---|---|
| GAP-046 | CME ZS option-chain ingest |
| GAP-047 | Put-call parity arbitrage prune |
| GAP-063 | CME EOD settlements pull |

## Tests

37 new tests in `tests/test_cme_ingest.py`:
- Error hierarchy (2)
- OptionsChain dataclass validation (3)
- Put-call parity: clean data, bad data, partial violations, expired chain (4)
- Expiry calendar: known dates, schedule, next_expiry, Friday guarantee, before-FND (10)
- Futures settle: parsing, edge cases, error handling (7)
- Options chain: parsing, sorting, inference, error handling (7)
- HTTP error handling (4)

Total test suite: 674 passed (637 existing + 37 new).

## What's next

F4-ACT-02 needs verification. Then:
- F4-ACT-01 (monthlies adaptations, S effort) — unblocked, can start now
- F4-ACT-03 (RND pipeline, XL effort) — blocked on F4-ACT-01 + F4-ACT-02 verification
