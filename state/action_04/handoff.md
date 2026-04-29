# ACT-04 Handoff -- Ticker schema + bucket grid + Event puller

**Action.** ACT-04
**Status.** complete-pending-verify
**Wave.** 0
**Implementer.** Claude Opus 4.6
**Date.** 2026-04-27

---

## What was done

Implemented the Kalshi ticker schema parser, bucket grid builder, and async Event puller. This closes GAP-074, GAP-075, and GAP-079 from the gap register.

### Files created

| File | Purpose |
|---|---|
| `feeds/kalshi/ticker.py` | Ticker schema parser: series, event, and market ticker parsing with strict validation |
| `feeds/kalshi/events.py` | Bucket grid builder (MECE-validated) + EventPuller async class using KalshiClient |
| `tests/test_ticker.py` | 31 tests covering ticker parsing, round-trips, edge cases, malformed input |
| `tests/test_events.py` | 24 tests covering bucket grid construction, MECE validation, EventPuller with mocked client |
| `state/action_04/plan.md` | Implementation plan |

### Files modified

| File | Change |
|---|---|
| `state/dependency_graph.md` | ACT-04 -> complete-pending-verify; ACT-06/09/13 deps met; ready set updated |

---

## Gaps closed

| Gap | Description | How closed |
|---|---|---|
| GAP-074 | Series -> Event -> Market ticker schema and parser/formatter | `feeds/kalshi/ticker.py`: `parse_series_ticker`, `parse_event_ticker`, `parse_market_ticker` with frozen dataclass outputs |
| GAP-075 | Event endpoint bucket-grid ingest | `feeds/kalshi/events.py`: `EventPuller.pull_event()` calls `KalshiClient.get_event()`, reads `floor_strike`/`cap_strike` from each child market |
| GAP-079 | Bucket/corridor data structures with MECE check | `feeds/kalshi/events.py`: `Bucket`, `BucketGrid` (contiguity validation, tail handling), `build_bucket_grid()` |

---

## Key design decisions

1. **Ticker parsing is strict and fail-loud.** Malformed tickers, invalid dates, bad months all raise ValueError immediately. No silent fallbacks.

2. **Bucket tails use None for open-ended bounds.** Lower tail has `lower=None`, upper tail has `upper=None`. This avoids hardcoding infinity as a float and makes tail detection explicit via `is_lower_tail` / `is_upper_tail` properties.

3. **MECE validation is enforced at BucketGrid construction.** The `build_bucket_grid()` function validates: exactly one lower tail, exactly one upper tail, contiguous edges (bucket[i].upper == bucket[i+1].lower), and interior buckets have lower < upper. Any violation raises ValueError.

4. **EventPuller.pull_active_events() paginates and is fault-tolerant.** Individual event fetch failures are logged and skipped (the series-level query should not fail because one event has bad data). Results sorted by expiry date.

5. **Bucket boundary convention: [lower, upper).** Matches Phase 07 section 3: "bucket i with edges [l_i, u_i) pays Yes if l_i <= S_T < u_i". The `bucket_for_price()` method implements this.

---

## Test results

```
55 passed in 0.10s
```

All 55 tests pass (31 ticker + 24 events). No pre-existing tests broken.

---

## Downstream unblocked

| Action | Status change | Notes |
|---|---|---|
| ACT-06 (order builder) | deps met | Can now use parsed market tickers and bucket types |
| ACT-09 (positions) | deps met | Can now use Bucket/EventSnapshot for per-Event exposure |
| ACT-13 (corridor adapter) | deps met | ACT-04 + ACT-08 both done; can build corridor decomposition on BucketGrid |
| ACT-LIP-SCORE | partial | Still needs ACT-LIP-POOL |

---

## Verification checklist

- [ ] `pytest tests/test_ticker.py tests/test_events.py -v` -- 55 pass
- [ ] `feeds/kalshi/ticker.py` has type hints on all public functions
- [ ] `feeds/kalshi/events.py` has type hints on all public interfaces
- [ ] No pandas imported anywhere in the new modules
- [ ] Malformed tickers raise ValueError (not return None)
- [ ] BucketGrid rejects non-MECE input
- [ ] EventPuller uses KalshiClient async methods correctly

---

## Resumption pointer

If picking up downstream work:
- **ACT-06**: import `ParsedMarketTicker` and `Bucket` from this module for order building
- **ACT-09**: import `EventSnapshot` and `BucketGrid` for per-Event position tracking
- **ACT-13**: import `BucketGrid` and use `bucket.lower`/`bucket.upper` for corridor decomposition D(l) - D(u)
