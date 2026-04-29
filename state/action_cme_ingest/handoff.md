# F4-ACT-02 — CME Options Chain Ingest — Handoff

**Status.** complete-pending-verify
**Date.** 2026-04-27

## What was built

New `feeds/cme/` package with 4 modules:

### `feeds/cme/errors.py`
- `CMEIngestError` (base) with `source` attribute
- `CMEChainError` — options chain pull failures
- `CMESettleError` — settlement price pull failures
- `CMEParityError` — put-call parity violation threshold exceeded

### `feeds/cme/expiry_calendar.py`
- `options_expiry(symbol, delivery_month, year)` — computes standard options expiry per CBOT rules (last Friday >= 2 BD before FND)
- `expiry_schedule(symbol, year)` — all expiries for a year
- `next_expiry(symbol, ref_date)` — nearest expiry on or after ref_date
- Supports ZS (7 delivery months) and ZC (5 delivery months)
- Uses existing `engine.event_calendar._is_cbot_trading_day` for holiday awareness

### `feeds/cme/futures_settle.py`
- `pull_settle(symbol, settle_date)` — async function pulling daily settlement from CME Group public API
- Parses CME JSON settlement response, extracts front-month settle price
- Optional file-based cache
- Raises `CMESettleError` on any failure

### `feeds/cme/options_chain.py`
- `OptionsChain` frozen dataclass: symbol, expiry, as_of, underlying_settle, strikes, call_prices, put_prices, call_ivs, put_ivs, call_oi, put_oi, call_volume, put_volume
- `pull_options_chain(symbol, expiry)` — async function pulling EOD options chain from CME Group public API
- `check_put_call_parity(chain)` — vectorized put-call parity check per GAP-047
  - Raises `CMEParityError` if >25% of strikes violate (configurable)
  - Returns list of violation indices for minor violations
- Parses CME JSON, sorts by strike, builds numpy arrays
- Optional npz-based cache

## Gaps closed
- **GAP-046**: CME ZS option-chain ingest implemented
- **GAP-047**: Put-call parity arbitrage prune implemented
- **GAP-063**: CME EOD settlements pull implemented

## Decision resolved
- **OD-37**: CME Group public delayed settlement data (free). See `state/action_cme_ingest/plan.md`.

## Tests
- 37 new tests in `tests/test_cme_ingest.py`
- All 674 tests pass (637 existing + 37 new)
- Ruff lint clean

## Dependencies unblocked
- **F4-ACT-03** (RND pipeline): can now consume `OptionsChain` data for BL density extraction, SVI fitting, and bucket integration

## Known limitations
- CME Group's public API may change format without notice — the parser handles the current JSON structure
- No real-time options data (EOD only, by design per F4 plan)
- American exercise premium not accounted for in put-call parity check (approximate, sufficient for data quality gate)
- Cache format is simple (npz/text); production may want a more structured store

## Files changed
- `feeds/cme/__init__.py` (new)
- `feeds/cme/errors.py` (new)
- `feeds/cme/expiry_calendar.py` (new)
- `feeds/cme/futures_settle.py` (new)
- `feeds/cme/options_chain.py` (new)
- `tests/test_cme_ingest.py` (new)
