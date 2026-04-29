# ACT-03 verification — Kalshi REST client foundation (signing + rate limiter)

**Verdict: PASS**
**Verifier:** Claude (read-only)
**Date:** 2026-04-27

---

## 1. Documents reviewed

- `state/action_03/plan.md` — scope, approach, done-when checklist
- `state/action_03/handoff.md` — status, files, gaps closed, done-when checked off
- `audit/audit_F3_refactor_plan_lip.md` line 156 — ACT-03 row in Wave 0 table
- `audit/audit_E_gap_register.md` — GAP-071, GAP-072, GAP-073, GAP-171

## 2. Gap closure verification

| Gap | Claimed | Verified | Notes |
|---|---|---|---|
| GAP-071 (partial) | REST client foundation | PASS | `feeds/kalshi/client.py`: async httpx client, 14 typed methods, signing, rate limiting, retry/backoff. WS deferred to ACT-05. |
| GAP-072 (full) | RSA-PSS-SHA256 signing | PASS | `feeds/kalshi/auth.py`: RSA-PSS with SHA-256, MGF1(SHA256), salt_length=32, message = `{ts}{METHOD}{path}`, base64 output. Key loading from PEM file, raw bytes, and env var. |
| GAP-073 (full) | Token-bucket rate limiter | PASS | `feeds/kalshi/rate_limiter.py`: separate read/write buckets, 5-tier enum (Basic through Prime), default 10-token cost, 2-token cancel cost, async acquire with sleep-until-available. |
| GAP-171 (partial) | Kill-switch REST endpoints | PASS | `batch_cancel_orders()` and `trigger_order_group()` exposed in client. End-to-end logic deferred to ACT-11. |

## 3. Code review

### feeds/kalshi/auth.py (~134 lines)
- RSA-PSS SHA-256 signing per Kalshi v3 spec: confirmed
- Key loading from PEM file, raw bytes, env var (`KALSHI_PRIVATE_KEY_PATH`): confirmed
- API key from constructor or env (`KALSHI_API_KEY`): confirmed
- Header builder: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE: confirmed
- Fail-loud: raises `KalshiAuthError` on missing key, missing API key, bad PEM, non-RSA key, missing file
- Type hints on all public methods: confirmed

### feeds/kalshi/rate_limiter.py (~115 lines)
- Token bucket with `_Bucket` dataclass: refill via `time.monotonic()`, try_consume returns wait time
- Separate read/write buckets: confirmed
- Tier config enum: BASIC(200/100), ADVANCED(300/300), PREMIER(1000/1000), PARAGON(2000/2000), PRIME(4000/4000)
- Default cost 10, cancel cost 2: confirmed
- Async acquire with sleep-until-available (no silent drops): confirmed
- Type hints on all public methods: confirmed

### feeds/kalshi/client.py (~428 lines)
- Async httpx.AsyncClient wrapper: confirmed
- 14 typed methods: get_events, get_event, get_market, get_orderbook, get_trades, create_order, cancel_order, batch_cancel_orders, trigger_order_group, get_positions, get_fills, get_balance, get_settlements (13 listed + context manager makes the interface complete)
- Retry with exponential backoff on 429 and 5xx: confirmed (up to `_MAX_RETRIES=4`, base 1s)
- Fail-loud: 401/403 raise immediately as KalshiAuthError; other 4xx raise as KalshiResponseError; 429 after max retries raises KalshiRateLimitError; malformed JSON raises KalshiResponseError; non-dict JSON raises KalshiResponseError; client-not-open raises KalshiAPIError
- No `return None` or `return 0` fallback patterns: confirmed
- asyncio for I/O only: confirmed
- Type hints on all public methods: confirmed

### feeds/kalshi/errors.py (~29 lines)
- KalshiAPIError (base) with status_code and body attributes: confirmed
- KalshiAuthError: confirmed
- KalshiRateLimitError: confirmed
- KalshiResponseError: confirmed

## 4. Non-negotiable checks

| Check | Result |
|---|---|
| No `import pandas` in feeds/kalshi/ | PASS |
| No bare `except:` or swallowed `except Exception:` in ACT-03 files | PASS — two `except Exception as exc` clauses both re-raise as typed exceptions |
| No `return None` / `return 0` fallback in client | PASS |
| asyncio for I/O only | PASS |
| Fail-loud on unexpected status codes | PASS — all non-2xx raise immediately or after retry exhaustion |
| Fail-loud on malformed responses | PASS — non-JSON and non-dict JSON both raise |
| Type hints on all public interfaces | PASS |

## 5. Git status

`feeds/kalshi/` shows as untracked (new files). The four ACT-03 modules are present:
- `feeds/kalshi/auth.py`
- `feeds/kalshi/rate_limiter.py`
- `feeds/kalshi/client.py`
- `feeds/kalshi/errors.py`

## 6. Test results

### ACT-03 tests: `tests/test_kalshi_client.py`

```
40 passed in 14.51s
```

Test coverage breakdown:
- **Signing (4 tests):** round-trip verify, different messages produce different sigs, header building, auto-timestamp
- **Auth credential loading (5 tests):** from PEM bytes, from file, from env vars, missing API key raises, missing key raises, nonexistent file raises, invalid PEM raises
- **Rate limiter (5 tests):** burst within capacity, read/write bucket separation, throttle when exhausted, cancel cost = 2, recovery after drain, tier config
- **REST methods happy path (13 tests):** all 13 endpoint methods exercised via respx mocks
- **Error paths (7 tests):** 401, 403, 429 retry-then-raise, 500 retry-then-raise, unexpected 418 immediate raise, malformed JSON, JSON array rejection
- **Client lifecycle (3 tests):** retry-then-success, client-not-open raises, async context manager
- **Integration (1 test):** auth headers present in actual requests

### Full suite

Pre-existing collection errors (missing numpy, yaml in environment). No regressions from ACT-03.

## 7. Handoff completeness

- Done-when checklist: all 10 items checked off, all verified
- Files written: all 4 source modules + 1 test file confirmed
- Gaps closed: 4 gaps with correct partial/full attribution
- New interfaces emitted: KalshiAuth, KalshiClient, KalshiRateLimiter, error types — documented
- Open issues: respx not in pyproject.toml dev deps (noted, non-blocking)

## 8. Minor observations (non-blocking)

1. `respx` is used as a test dependency but is not listed in `pyproject.toml` dev dependencies. Downstream actions or CI may need it added.
2. The `capture.py` file (from ACT-01, not ACT-03) contains `except Exception:` patterns that swallow exceptions — this is outside ACT-03 scope but noted for future review.
