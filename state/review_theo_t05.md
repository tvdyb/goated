# Phase T-05 Review — Pyth Forward Price

**Verdict: CONDITIONAL PASS**
**Date: 2026-04-29**
**Reviewer: automated (Phase T-05)**

## Summary

The Pyth forward integration is **well-engineered code that cannot deliver its
primary value** because Pyth Network does not publish soybean futures data. All
5 CBOT soybean contract month feeds (SOK6 through SOX6) return `price=0,
publish_time=0`. The system correctly falls back to the Kalshi-inferred forward
on every cycle.

The code passes review on all quality criteria. The verdict is CONDITIONAL
because the Pyth feed being dead means we have zero live validation of price
accuracy, update frequency, or the price_divisor assumption.

---

## Check 1: Pyth feed availability

**FAIL — feed is structurally inactive.**

| Feed | Contract | Price | Status |
|------|----------|-------|--------|
| SOK6 | May 2026 | 0 | INACTIVE |
| SON6 | Jul 2026 (configured) | 0 | INACTIVE |
| SOQ6 | Aug 2026 | 0 | INACTIVE |
| SOU6 | Sep 2026 | 0 | INACTIVE |
| SOX6 | Nov 2026 | 0 | INACTIVE |
| WTI (reference) | — | 75326 | ACTIVE (age=2s) |

All soybean feeds have `publish_time=0`, meaning they have **never** published
data. The WTI feed is active and updating every ~1s, confirming the Hermes API
works fine — Pyth simply doesn't have soybean publishers.

## Check 2: Does Pyth price update every 5 seconds?

**N/A — feed is inactive.**

Cannot be tested. The background polling loop does run and calls `poll_once()`
every 5s, but every call raises `PythUnavailableError` and returns `None`.

## Check 3: Is staleness rejection working?

**PASS — verified with live WTI feed.**

```
Test: get_latest_price(WTI, max_staleness_ms=1)
Result: PythStaleError raised correctly
        "Feed 0xe62... is 1697ms old (threshold=1ms)"
```

Staleness logic is correct. The `age_ms = now_ms - (publish_time * 1000)`
calculation works. For the soy feed with `publish_time=0`, the zero-price
check fires before staleness is even evaluated — also correct.

## Check 4: Does fallback to Kalshi-inferred work?

**PASS — verified in 6 integration tests.**

| Test | Result |
|------|--------|
| poll_once with inactive soy feed | Returns None, pyth_available=False |
| poll_once with active WTI feed | Returns $75444.09, pyth_available=True |
| Staleness rejection (1ms threshold) | PythStaleError raised |
| Forward persistence across failure | forward_price holds last good value |
| Deploy wiring: pyth_available=False | Falls through to Kalshi-inferred path |
| Deploy wiring: pyth_available=True | Uses Pyth forward directly |

The deploy integration (`deploy/main.py:761-786`, `deploy/lip_mode.py:466-482`)
correctly checks `pyth_provider.pyth_available` before using `forward_price`.

## Check 5: Pyth price vs actual ZS quote

**FAIL — cannot compare (feed inactive).**

Barchart ZSN26 (Jul 2026 soybeans): **$11.965/bu** at 12:08 PM CDT.
Pyth SON6: **$0.00** (never published).

Additionally, the `price_divisor=100.0` assumption (that Pyth reports soy in
cents/bushel) is **unverified**. The WTI reference feed reports `75326` for a
commodity trading at ~$107/bbl on Barchart, which shows Pyth commodity price
units may not follow CME conventions.

## Check 6: Test suite

**PASS — 1009 tests pass.**

- 16 new tests in `test_pyth_forward.py`: all pass
- Full suite: 1009 passed in 38.84s (excluding pre-existing benchmark flake)
- No regressions

## Code quality review

**PASS — meets all non-negotiables.**

| Criterion | Status |
|-----------|--------|
| No pandas | PASS |
| asyncio for I/O only | PASS |
| Fail-loud (no silent defaults) | PASS — raises typed exceptions |
| Type hints on public interfaces | PASS |
| No scipy.stats.norm.cdf | N/A (no stats math) |

Code is clean:
- `PythHermesClient` correctly parses fixed-point `price * 10^expo`
- Error hierarchy: `PythClientError > PythStaleError, PythUnavailableError`
- `PythForwardProvider` properly separates polling from consumption
- Deploy integration is minimal and non-invasive (additive only)
- Config loaded from `pyth_feeds.yaml`, not hardcoded

Minor observation: the `_poll_loop` background task will log a WARNING every 5s
while the soy feed is inactive. Over hours, this creates log noise. Not a
blocker, but consider reducing to DEBUG after N consecutive failures.

## Risks

1. **price_divisor unverified**: The `100.0` divisor assumes cents/bushel. When
   the feed activates (if ever), the first price could produce a wildly wrong
   forward ($11.96 vs $1196 vs $0.1196) depending on actual units.
   **Mitigation**: Add a sanity check — if Pyth forward is outside [5.0, 25.0]
   $/bushel, reject it.

2. **Feed may never activate**: Pyth may never publish CBOT soybean data. The
   system will run on Kalshi-inferred forward indefinitely — which was the
   original behavior before T-00.

3. **Log spam**: Every 5s, a WARNING is logged for the inactive feed. Over a
   24-hour run, that's ~17,280 warnings.

## Verdict justification

**CONDITIONAL PASS** because:
- The code is correct, well-tested, and non-invasive
- Fallback to Kalshi-inferred forward works perfectly
- No regressions in the existing test suite
- The system is no worse than before T-00

The condition: when the Pyth soy feed activates, the `price_divisor` must be
validated against a known ZS quote before the forward is trusted for live
trading.

## Recommended follow-ups

1. **PRIORITY: Wire IBKR API for real-time ZS forward.** Pyth soy feeds are
   structurally dead — IBKR is the only viable path to a real futures price.
   IBKR account is already opened; next step is IB Gateway setup + market data
   subscription (~$10/mo for CME ag). This should be the next phase, not a
   backlog item.
2. Add a forward sanity bound (e.g. 5.0 < forward < 25.0 $/bu) in
   `_get_active_event` to catch price_divisor misconfiguration.
3. Reduce poll_once WARNING to DEBUG after 10 consecutive failures.
