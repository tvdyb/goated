# ACT-01 implementation plan (Phase 1a only)

## Scope

- **Gaps closed:**
  - GAP-148 (partial): Forward-capture tape — Phase 1a REST polling only (orderbook snapshots + trades + settled outcomes). Phase 1b (full WS) deferred to ACT-03 landing.
  - GAP-173 (partial): Forward-capture asset recording begins — every day captured from deploy onward is preserved.

- **Code locations to touch:**
  - `feeds/__init__.py` (currently empty) — leave as-is; new module lives under `feeds/kalshi/`.

- **New modules to create:**
  - `feeds/kalshi/__init__.py` — package init
  - `feeds/kalshi/capture.py` — REST polling sentinel: async loop that polls Kalshi public REST endpoints and writes to DuckDB
  - `feeds/kalshi/models.py` — data classes for captured snapshots (orderbook, trades, market metadata, settled outcomes)

- **Tests to add:**
  - `tests/test_capture.py` — mock httpx responses, verify DuckDB writes, test error handling, test polling lifecycle

## Approach

Phase 1a is a REST polling sentinel that hits **public read-only** Kalshi endpoints (no auth required) and persists snapshots to DuckDB + Parquet. The three data streams:

1. **Orderbook snapshots.** `GET /markets/{ticker}/orderbook` for each active KXSOYBEANW market, every 30-60 seconds. Stores full depth (yes levels, no levels) with timestamps. This is the primary data for M0 scoring.

2. **Trades.** `GET /markets/trades` filtered by ticker prefix KXSOYBEANW. Captures public trade prints (price, count, timestamp). Polled at same cadence as orderbook.

3. **Settled outcomes.** `GET /events/{event_ticker}` to detect market settlement status. Polled less frequently (every 5 minutes). Records final settlement prices and outcomes.

The sentinel discovers active KXSOYBEANW events by calling `GET /events` with a series_ticker filter, then enumerates child markets. It refreshes the event/market list periodically (every 5 minutes) to pick up new events as they open.

**Storage:** DuckDB database at a configurable path (default: `data/capture/kalshi_capture.duckdb`). Three tables: `orderbook_snapshots`, `trades`, `market_events`. DuckDB chosen per GAP-150 recommendation and because it supports Parquet export natively.

**Error handling:** Network errors, 429s, and malformed responses are logged and retried with exponential backoff. The sentinel never crashes on transient failures — it logs and continues. Stale-data conditions (no update for >5 minutes) are logged as warnings.

**Lifecycle:** The sentinel runs as an async task. It exposes `start()` and `stop()` for clean lifecycle management. A `__main__` entry point allows standalone execution via `python -m feeds.kalshi.capture`.

## Dependencies on frozen interfaces

None. ACT-01 Phase 1a has no upstream dependencies and produces no interfaces consumed by in-flight actions yet.

## Risks

- Kalshi public REST may 429 under aggressive polling. Mitigated by configurable interval (default 60s) and 429 backoff.
- Kalshi API response schema may differ from docs. Mitigated by defensive parsing with clear error messages.
- DuckDB dependency not yet in pyproject.toml. Will be added.

## Done-when

- [ ] `feeds/kalshi/capture.py` polls orderbook, trades, and settlement status for all active KXSOYBEANW markets
- [ ] Data persists to DuckDB with schema matching the three streams
- [ ] Configurable polling interval (default 60s for orderbook/trades, 300s for events)
- [ ] 429 and network-error backoff with logging
- [ ] Clean start/stop lifecycle
- [ ] `python -m feeds.kalshi.capture` runs standalone
- [ ] Tests pass with mocked HTTP responses
- [ ] No auth required (public endpoints only)
- [ ] pyproject.toml updated with duckdb dependency
