# ACT-03 implementation plan -- Kalshi REST client foundation (signing + rate limiter)

## Scope

- **Gaps closed:**
  - GAP-071 (partial): Kalshi REST client foundation -- async httpx client with signing, rate limiting, retry/backoff, and core REST methods. WS multiplex deferred to ACT-05.
  - GAP-072 (full): RSA-PSS-SHA256 signing module + key loader + header builder.
  - GAP-073 (full): Tiered token-bucket pacer + per-endpoint cost table + 429 exponential backoff.
  - GAP-171 (partial): Kill-switch primitives wired at REST layer (DELETE batch + order-group trigger endpoints exposed). End-to-end trigger logic is ACT-11.

- **Code locations to touch:**
  - `feeds/kalshi/` -- existing package from ACT-01.

- **New modules to create:**
  - `feeds/kalshi/auth.py` -- RSA-PSS SHA-256 signing, key loading from file/env, header construction.
  - `feeds/kalshi/rate_limiter.py` -- Token-bucket rate limiter with per-tier config and read/write separation.
  - `feeds/kalshi/client.py` -- Async REST client: GET/POST/DELETE for markets, events, orders, portfolio. Retry/backoff on 429 and 5xx.
  - `feeds/kalshi/errors.py` -- Error types: KalshiAPIError, KalshiAuthError, KalshiRateLimitError, KalshiResponseError.

- **Tests to add:**
  - `tests/test_kalshi_client.py` -- Signing correctness, rate limiter behaviour, REST method happy/error paths, auth credential loading.

## Approach

The client is the foundation for all Kalshi-side operations. It provides:

1. **Auth (auth.py):** RSA-PSS signing per Kalshi v3 spec. Message = `{timestamp_ms}{METHOD}{path}`. Uses `cryptography` library's RSA-PSS with SHA-256, MGF1(SHA-256), salt_length=32. Key loaded from PEM file (path via env `KALSHI_PRIVATE_KEY_PATH` or constructor arg). API key UUID from env `KALSHI_API_KEY` or constructor arg.

2. **Rate limiter (rate_limiter.py):** Token-bucket with separate read/write buckets. Configurable per tier (Basic: 200/100, Advanced: 300/300, Premier: 1000/1000). Default request cost: 10 tokens. Cancel cost: 2 tokens. Async `acquire()` that sleeps until tokens available. No silent drops -- caller awaits until permitted.

3. **Client (client.py):** `KalshiClient` wrapping `httpx.AsyncClient`. Methods:
   - `get_events(series_ticker, ...)` -- GET /events
   - `get_event(event_ticker)` -- GET /events/{ticker}
   - `get_market(ticker)` -- GET /markets/{ticker}
   - `get_orderbook(ticker)` -- GET /markets/{ticker}/orderbook
   - `get_trades(ticker, ...)` -- GET /markets/trades
   - `create_order(...)` -- POST /portfolio/orders
   - `cancel_order(order_id)` -- DELETE /portfolio/orders/{id}
   - `batch_cancel_orders(order_ids)` -- DELETE /portfolio/orders/batch
   - `trigger_order_group(group_id)` -- POST /order-groups/{group_id}/trigger
   - `get_positions()` -- GET /portfolio/positions
   - `get_fills(...)` -- GET /portfolio/fills
   - `get_balance()` -- GET /portfolio/balance
   - `get_settlements(...)` -- GET /portfolio/settlements

   All methods: type-hinted args and returns, raise on non-2xx (except 429 which retries), fail-loud on malformed JSON.

4. **Errors (errors.py):** Typed exception hierarchy. `KalshiAPIError` base, with `KalshiAuthError` (401/403), `KalshiRateLimitError` (429 after max retries), `KalshiResponseError` (unexpected status or malformed body).

Design decisions:
- OD-31 (low-frequency cadence): Rate limiter is conservative -- Basic tier (10 writes/sec) is the default. No need for aggressive token consumption.
- OD-15 (Standard tier): Rate limiter defaults to Basic/Standard limits.
- asyncio for I/O only: Client is async; callers await results. No async business logic.
- No pandas.

## Dependencies on frozen interfaces

- `feeds/kalshi/models.py` (from ACT-01): Read-only. No changes needed.
- `pyproject.toml`: `cryptography>=42.0` and `httpx>=0.27` already listed.

## Risks

- RSA-PSS signing correctness cannot be validated against production without live credentials. Mitigated by test vector (known message + known key -> known signature) using `cryptography` library.
- Rate limiter token-bucket precision depends on asyncio event loop timing. Mitigated by conservative budgets and burst allowance.
- Kalshi API may have undocumented response shapes. Mitigated by fail-loud parsing + defensive field access.

## Done-when

- [ ] `feeds/kalshi/auth.py` signs requests per Kalshi RSA-PSS spec (timestamp + method + path)
- [ ] `feeds/kalshi/rate_limiter.py` implements token-bucket with read/write separation and tier config
- [ ] `feeds/kalshi/client.py` exposes typed async methods for all core REST endpoints
- [ ] `feeds/kalshi/errors.py` defines error hierarchy
- [ ] Retry with exponential backoff on 429 and 5xx
- [ ] Fail-loud on unexpected status codes and malformed responses
- [ ] No silent failures anywhere
- [ ] Auth credentials loadable from env vars or constructor args
- [ ] Tests cover signing, rate limiter, all REST methods (happy + error), auth loading
- [ ] All tests pass
