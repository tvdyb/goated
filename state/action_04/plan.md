# ACT-04 Plan -- Ticker schema + bucket grid + Event puller

**Action.** ACT-04
**Wave.** 0
**Effort.** M
**Critical path.** Yes -- ACT-06, ACT-09, ACT-13, ACT-LIP-SCORE depend on this.

---

## Gaps addressed

| Gap | Summary |
|---|---|
| GAP-074 | Series -> Event -> Market -> Yes/No four-level ticker schema and parser/formatter |
| GAP-075 | Event endpoint reading floor_strike/cap_strike/strike_type; bucket-grid ingest |
| GAP-079 | Bucket/corridor data structures (Event, Bucket, MECE check, open-ended tail handling) |

---

## Module layout

### `feeds/kalshi/ticker.py` -- Ticker schema parser

- Parse series ticker (e.g. `KXSOYBEANW`)
- Parse event ticker (e.g. `KXSOYBEANW-26APR24`) into (series, expiry_date)
- Parse market ticker (e.g. `KXSOYBEANW-26APR24-17`) into (series, expiry_date, bucket_index)
- Format functions for reverse direction
- Strict validation: malformed tickers raise ValueError (fail-loud)
- `ParsedSeriesTicker`, `ParsedEventTicker`, `ParsedMarketTicker` frozen dataclasses

### `feeds/kalshi/events.py` -- Bucket grid + Event puller

- Data types: `Bucket` (lower, upper, ticker, is_lower_tail, is_upper_tail)
- Data types: `BucketGrid` wrapping a sorted list of Buckets with MECE validation
- `EventSnapshot`: event_ticker, series_ticker, expiry_date, status, bucket_grid, fetched_at
- `EventPuller`: async class using KalshiClient to:
  - `pull_event(event_ticker)` -> EventSnapshot
  - `pull_active_events(series_ticker)` -> list[EventSnapshot]
- MECE check: validate buckets are contiguous and exhaustive (lower tail + interior + upper tail)
- Sum-to-one not enforced here (that is pricing-layer, ACT-13 / GAP-044)
- Open-ended tails: lower tail has lower=None (or -inf), upper tail has upper=None (or +inf)

### Integration

- Uses `KalshiClient.get_event()` and `KalshiClient.get_events()` from ACT-03
- Uses existing `feeds/kalshi/models.py` EventInfo/MarketInfo as raw layer; this module adds parsed/validated layer on top

---

## Non-negotiables

- No pandas
- Type hints on all public interfaces
- Fail-loud: malformed tickers, missing fields, non-MECE grids raise immediately
- No silent failures

---

## Test plan

- `tests/test_ticker.py`: valid/invalid ticker parsing, round-trip format
- `tests/test_events.py`: bucket grid construction, MECE validation, event puller with mocked client
