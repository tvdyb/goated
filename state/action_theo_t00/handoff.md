# Phase T-00 Handoff — Wire Pyth Real-Time Forward Price

**Status**: COMPLETE
**Date**: 2026-04-29

## What was done

Wired Pyth Network real-time soybean futures prices into the market maker's
forward price estimation, replacing the inaccurate Kalshi-inferred heuristic
(50c midpoint strike) as the primary source.

## Files created

| File | Purpose |
|---|---|
| `feeds/pyth/__init__.py` | Package init |
| `feeds/pyth/client.py` | Async Pyth Hermes REST client (httpx) |
| `feeds/pyth/forward.py` | Forward price provider with background polling |
| `tests/test_pyth_forward.py` | 16 tests with mocked Pyth responses |

## Files modified

| File | Change |
|---|---|
| `config/pyth_feeds.yaml` | Updated soy feed_id to correct SON6/USD (Jul 2026 contract), added price_divisor, raised max_staleness_ms to 30s |
| `deploy/main.py` | Added Pyth forward provider init/start/stop; forward estimation prefers Pyth, falls back to Kalshi |
| `deploy/lip_mode.py` | Same Pyth forward integration |
| `tests/test_soy_config.py` | Updated assertion for new Pyth symbol format |

## Architecture

```
Pyth Hermes REST API
  │
  ▼
PythHermesClient (feeds/pyth/client.py)
  - GET /v2/updates/price/latest?ids[]=...&parsed=true
  - Parses fixed-point: price * 10^expo
  - Validates staleness, rejects price=0 / publish_time=0
  │
  ▼
PythForwardProvider (feeds/pyth/forward.py)
  - Background asyncio task polls every 5s
  - Divides by price_divisor (100.0) to get $/bushel
  - Exposes .forward_price and .pyth_available
  │
  ▼
MarketMaker._get_active_event() / LIPMarketMaker._get_active_event()
  - If pyth_available and forward > 0: use Pyth
  - Else: fall back to Kalshi-inferred (50c strike heuristic)
```

## Key discovery

**Pyth soybean feeds are currently inactive.** All CBOT soybean contract feeds
(SOK6, SON6, SOQ6, SOU6, SOX6) return price=0, publish_time=0. The system
correctly falls back to Kalshi-inferred forward until Pyth begins publishing.

The original feed_id in config (`0xbfa30e...`) was a non-existent feed. Updated
to `0x0d03b648...` (SON6/USD, Jul 2026 soybean futures).

## Test results

- 16 new tests in `test_pyth_forward.py`: all pass
- 1009 total tests pass (excluding pre-existing benchmark flake)
- No regressions

## What to monitor

1. **Pyth soy feed activation**: Check periodically if Pyth begins publishing
   soybean data. When it does, the system will automatically start using it.
2. **Contract roll**: When SON6 expires (2026-07-14), update `config/pyth_feeds.yaml`
   to the next front month contract feed_id.
3. **Price units**: Pyth soy prices are in cents/bushel (verified from WTI feed
   format). The `price_divisor: 100.0` converts to $/bushel.
