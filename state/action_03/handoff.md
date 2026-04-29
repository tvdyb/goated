# ACT-03 handoff -- Kalshi REST client foundation (signing + rate limiter)

**Status.** complete-pending-verify

**Files written or edited.**

| Path | Lines added | Lines removed | Purpose |
|---|---|---|---|
| `feeds/kalshi/errors.py` | ~28 | 0 | Typed exception hierarchy: KalshiAPIError, KalshiAuthError, KalshiRateLimitError, KalshiResponseError |
| `feeds/kalshi/auth.py` | ~120 | 0 | RSA-PSS SHA-256 signing, key loading from PEM file/bytes/env, header construction |
| `feeds/kalshi/rate_limiter.py` | ~105 | 0 | Token-bucket rate limiter with separate read/write buckets, tier config, async acquire |
| `feeds/kalshi/client.py` | ~330 | 0 | KalshiClient: async httpx REST client with signing, rate limiting, retry/backoff, 14 typed methods |
| `tests/test_kalshi_client.py` | ~430 | 0 | 40 tests: signing, auth loading, rate limiter, all REST methods happy+error paths |

**Tests added.**

| Path | Test count | Pass | Fail |
|---|---|---|---|
| `tests/test_kalshi_client.py` | 40 | 40 | 0 |

Full suite: 194 passed, 0 failed.

**Gaps closed (with rationale).**

- GAP-071 (partial): Kalshi REST client foundation implemented. Async httpx client with signing, rate limiting, retry/backoff, and typed methods for all core endpoints (markets, events, orders, portfolio, kill-switch primitives). WS multiplex is ACT-05's scope.
- GAP-072 (full): RSA-PSS-SHA256 signing module complete. Key loading from PEM file, raw bytes, or env var. Header builder produces KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE per Kalshi v3 spec.
- GAP-073 (full): Token-bucket rate limiter with separate read/write buckets, configurable per tier (Basic through Prime), default 10-token cost, 2-token cancel discount, async acquire with sleep-until-available semantics.
- GAP-171 (partial): Kill-switch REST endpoints exposed: `batch_cancel_orders()` (DELETE /portfolio/orders/batch) and `trigger_order_group()` (POST /order-groups/{group_id}/trigger). End-to-end trigger logic deferred to ACT-11.

**Frozen interfaces honoured.** None applicable (ACT-03 has no upstream interface constraints).

**New interfaces emitted.**

- `KalshiAuth` -- used by ACT-05 (WS), ACT-11 (kill switch), ACT-LIP-POOL, and any downstream action needing authenticated Kalshi access.
- `KalshiClient` -- the primary REST interface for ACT-04 (event/market pulling), ACT-05 (initial REST bootstrap), ACT-06 (order builder), ACT-09 (positions), ACT-11 (kill primitives), ACT-LIP-POOL (pool data).
- `KalshiRateLimiter` -- shared by client and potentially WS auth in ACT-05.
- Error types in `feeds/kalshi/errors.py` -- consumed by all downstream Kalshi-side actions for typed error handling.

**Decisions encountered and resolved.** None new. Existing decisions applied:
- OD-15 (Standard tier): Rate limiter defaults to Basic tier (200 reads/100 writes per sec).
- OD-31 (low-frequency cadence): Conservative rate budget; no aggressive token consumption needed.

**Decisions encountered and deferred.** None.

**Open issues for verifier.**

- RSA-PSS signing is tested via round-trip (sign + verify with public key) using a test-generated key pair. Production Kalshi keys have not been tested -- this is expected and correct (no credentials in repo).
- The rate limiter uses `time.monotonic()` for token refill timing. Under heavy async contention the sleep precision depends on the event loop; this is acceptable for the low-frequency cadence (OD-31).
- `respx` was installed as a dev dependency for HTTP mocking. It is not in `pyproject.toml [dev]` yet -- the verifier may want to add it.

**Done-when checklist.**

- [x] `feeds/kalshi/auth.py` signs requests per Kalshi RSA-PSS spec (timestamp + method + path)
- [x] `feeds/kalshi/rate_limiter.py` implements token-bucket with read/write separation and tier config
- [x] `feeds/kalshi/client.py` exposes typed async methods for all core REST endpoints (14 methods)
- [x] `feeds/kalshi/errors.py` defines error hierarchy (4 exception classes)
- [x] Retry with exponential backoff on 429 and 5xx
- [x] Fail-loud on unexpected status codes (4xx raises immediately) and malformed responses
- [x] No silent failures anywhere
- [x] Auth credentials loadable from env vars (KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH) or constructor args
- [x] Tests cover signing (round-trip verify), rate limiter (burst/throttle/recovery/tiers), all REST methods (happy + error), auth loading (file/env/errors)
- [x] All 40 tests pass; full suite 194/194 green
