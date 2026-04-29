# ACT-01 handoff (Phase 1a only)

**Status.** complete (Phase 1a only; Phase 1b deferred to post-ACT-03)

**Files written or edited.**

| Path | Lines added | Lines removed | Purpose |
|---|---|---|---|
| `feeds/kalshi/__init__.py` | 0 | 0 | Package init |
| `feeds/kalshi/models.py` | ~55 | 0 | Data classes: OrderbookSnapshot, Trade, MarketInfo, EventInfo |
| `feeds/kalshi/capture.py` | ~280 | 0 | KalshiCaptureSentinel: async REST polling loop for orderbook, trades, events |
| `feeds/kalshi/store.py` | ~115 | 0 | CaptureStore: DuckDB backend with three tables |
| `feeds/kalshi/__main__.py` | ~40 | 0 | CLI entry point: `python -m feeds.kalshi.capture` |
| `pyproject.toml` | 1 | 0 | Added `duckdb>=1.0` dependency |
| `.gitignore` | 1 | 0 | Added `data/` to gitignore |

**Tests added.**

| Path | Test count | Pass | Fail |
|---|---|---|---|
| `tests/test_capture.py` | 21 | 21 | 0 |

**Gaps closed (with rationale).**

- GAP-148 (partial): Forward-capture tape Phase 1a implemented. REST polling sentinel captures orderbook snapshots, trade prints, and market metadata for all active KXSOYBEANW markets. Phase 1b (WS forward-capture) deferred until ACT-03 lands.
- GAP-173 (partial): Forward-capture asset recording begins with Phase 1a. Every day from deploy onward is preserved in DuckDB. Sufficient for M0 backtest.

**Frozen interfaces honoured.** None applicable.

**New interfaces emitted.** None. The capture module is a leaf — it produces data, consumed downstream by ACT-LIP-VIAB and ACT-26.

**Decisions encountered and resolved.** None new.

**Decisions encountered and deferred.** None.

**Open issues for verifier.**

- The `__main__` entry point uses signal handlers that only work on Unix. Windows compatibility is not a requirement but worth noting.
- The sentinel polls all markets sequentially within each interval. For large market counts this could compress the polling window. Not an issue for KXSOYBEANW (typically 10-15 markets per event).
- DuckDB `INSERT OR IGNORE` is used for trade deduplication by trade_id.

**Done-when checklist.**

- [x] `feeds/kalshi/capture.py` polls orderbook, trades, and settlement status for all active KXSOYBEANW markets
- [x] Data persists to DuckDB with schema matching the three streams
- [x] Configurable polling interval (default 60s for orderbook/trades, 300s for events)
- [x] 429 and network-error backoff with logging
- [x] Clean start/stop lifecycle
- [x] `python -m feeds.kalshi.capture` runs standalone
- [x] Tests pass with mocked HTTP responses (21/21)
- [x] No auth required (public endpoints only)
- [x] pyproject.toml updated with duckdb dependency

**Resumption notes.** Phase 1a is complete. Phase 1b (WebSocket forward-capture) is deferred until ACT-03 (Kalshi REST client with auth) is verified-complete — ACT-03 provides the signing and rate-limiting foundation that Phase 1b needs.
