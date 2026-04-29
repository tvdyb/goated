# Phase T-30 Review -- Markout Analysis

**Verdict: BLOCKED -- PREREQUISITES NOT MET**
**Date: 2026-04-29**
**Reviewer: automated (Phase T-30)**

## Summary

T-30 requires markout data from at least 2 settled Events. We have **zero settled
Events** and **zero persisted markout data**. The bot has been live for ~1 day
(2026-04-28) on a single Event (KXSOYBEANMON-26APR3017) that has not yet settled.

The markout tracking infrastructure (`engine/markout.py`, wired into
`deploy/lip_mode.py`) is correctly implemented but has two structural gaps that
prevent post-hoc analysis:

1. **In-memory only**: `MarkoutTracker` uses a 1-hour rolling window and stores
   no data to disk. When the bot restarts, all markout history is lost.
2. **No `model_fair_cents` in PnL fills**: `deploy/main.py:1020-1028` records
   fills to PnL with `model_fair_cents=0` (default), so all PnL CSVs show
   `spread_capture_cents=0` and `adverse_selection_cents=0`. The data exists
   but is useless for adverse-selection analysis.

---

## What data exists

### PnL CSVs (9 files, 2026-04-28)

All from a single ~6-hour session on KXSOYBEANMON-26APR3017.

| Session | Hours covered | Total fills | Total fees (c) | Spread capture | Adverse selection |
|---|---|---|---|---|---|
| Early runs (7 short) | ~1h fragmented | 667 | 1,404 | 0 | 0 |
| Long run #1 | 4h (15:00-19:00 CDT) | 738 | 1,669 | 0 | 0 |
| Long run #2 | 2h (19:00-21:00 CDT) | 612 | 1,440 | 0 | 0 |

**Key finding**: `spread_capture=0` across all sessions means the `FillRecord`
was never populated with `model_fair_cents`. The PnL tracker cannot distinguish
spread capture from adverse selection without this field. All economics are
recorded as pure fee drag.

### Markout JSON

`state/markout.json` does not exist. The `_write_markout_file()` method in
`deploy/lip_mode.py:676` writes this file, but it is only called in LIP mode.
The main 2026-04-28 session ran via `deploy/main.py`, which does not integrate
the `MarkoutTracker`.

### Fill-level CSVs

None. `PnLTracker.write_fills()` was never called during the live session.

---

## Per-bucket analysis (NOT POSSIBLE)

Without per-fill markout data or `model_fair_cents` in PnL records, we cannot
compute:

- Average markout at 1m, 5m, 30m per bucket
- ATM vs wing toxicity
- Time-of-day patterns
- Total adverse selection cost vs LIP revenue

---

## Structural issues to fix before T-30 can pass

### Issue 1 (CRITICAL): `model_fair_cents` not passed to PnL tracker

`deploy/main.py:1020-1028` creates `FillRecord` without `model_fair_cents`.
The model fair value IS computed earlier in the cycle (stored in
`self._bucket_prices` or equivalent), but is not threaded through to fill
recording.

**Fix**: When processing fills, look up `model_fair_cents` from the most recent
theo computation and pass it to `FillRecord`. This is the single most impactful
fix for future analysis.

### Issue 2 (CRITICAL): `MarkoutTracker` not wired into `deploy/main.py`

The markout tracker is only integrated in `deploy/lip_mode.py`. The main deploy
loop (`deploy/main.py`) does not import or use it. Since the first live session
ran via `main.py`, no markout data was collected.

**Fix**: Add `MarkoutTracker` to `deploy/main.py` with the same wiring pattern
as `lip_mode.py:117-122, 221-230, 454-491`.

### Issue 3 (HIGH): Markout data is in-memory only

`MarkoutTracker` keeps a 1-hour rolling window in memory. Completed markouts
older than 1 hour are pruned. No data is persisted to disk. Even in LIP mode
where the tracker IS wired, a bot restart loses all history.

**Fix**: Add a `write_markout_csv()` method that persists completed markouts
to `output/markout/markout_{timestamp}.csv` before pruning. Include fields:
`timestamp, market_ticker, side, fill_price_cents, theo_at_fill_cents,
markout_1m, markout_5m, markout_30m`. This enables post-hoc T-30 analysis.

### Issue 4 (MEDIUM): No fill-level CSV persistence

`PnLTracker.write_fills()` exists but is never called. The method writes
per-fill data that would enable markout reconstruction.

**Fix**: Call `write_fills()` alongside `write_summary()` at session end
(or periodically, e.g., hourly).

---

## Adversse selection estimate from available data

While we cannot do per-bucket markout analysis, we can estimate total economics
from the PnL data:

**Longest continuous session** (pnl_1777438348.csv, ~4 hours):
- 738 fills across 4 hours
- Kalshi fees: 1,669c ($16.69)
- Spread capture: 0c (not measured -- see Issue 1)
- Net PnL: -1,669c (-$16.69)

**Key observation**: With `min_half_spread_cents=2` (config_test.yaml) and
`max_contracts_per_strike=3`, each filled order should capture ~2-4c of spread
per contract. Across 738 fills, that's potentially 1,476-2,952c ($14.76-$29.52)
of gross spread. If spread capture is roughly 2,200c (midpoint estimate):

| Component | Estimate |
|---|---|
| Gross spread capture | ~2,200c |
| Kalshi fees | -1,669c |
| **Net before adverse selection** | **~531c** |

This means the system needs adverse selection to be **less than ~531c across
738 fills (~0.7c per fill)** to be net positive on spread economics alone.
Without actual markout measurements, we cannot determine if this threshold is
met.

From the CLAUDE.md kill criteria: **KC-F4-05** fires if markout exceeds 60% of
captured spread for 4 consecutive weeks. We have zero data points toward this
metric.

---

## LIP revenue comparison (NOT POSSIBLE)

LIP 0.5x incentive scoring depends on:
- Time-weighted presence at BBO
- Spread width vs minimum required
- Number of markets quoted

Without markout data, we cannot compare adverse selection cost to LIP revenue.
The LIP program just launched -- data will accumulate over the coming weeks.

---

## Recommendations (priority order)

### Before next live session (blocking T-30 re-run):

1. **Wire `model_fair_cents` into `FillRecord`** in `deploy/main.py`. This is
   a ~5-line change that unlocks all PnL attribution analysis.

2. **Add `MarkoutTracker` to `deploy/main.py`** with the same pattern as
   `lip_mode.py`. Record fills with theo at fill time, update each cycle.

3. **Persist markout data to CSV** -- add `write_markout_csv()` to
   `MarkoutTracker` and call it periodically (hourly or at session end).

4. **Call `write_fills()` at session end** to preserve per-fill data for
   post-hoc analysis.

### After 2+ settled Events with markout data:

5. **Re-run T-30** with actual markout CSVs. The analysis framework (per-bucket
   avg at 1m/5m/30m, ATM vs wings, time-of-day, toxic strike detection) is
   already built in `engine/markout.py` and just needs data.

6. **Compare markout by moneyness**: ATM strikes (within 10c of forward) are
   likely more toxic than wings because informed traders target the most liquid
   strikes. Expect to widen ATM spreads.

7. **Compare markout by time of day**: Pre-market (before 8:30 CT) and
   around USDA release windows are likely more toxic. The settlement gate
   already handles scheduled events, but unscheduled news flow may need a
   wider default spread during overnight hours.

---

## Verdict justification

**BLOCKED** because:
- Zero settled Events (need 2+)
- Zero persisted markout data
- PnL attribution is non-functional (`model_fair_cents=0`)
- The markout tracker is not wired into the main deploy path

The infrastructure is correctly designed (`engine/markout.py` is well-tested
with 19 passing tests). The gap is purely in data collection plumbing. Fixes
1-4 above are straightforward (~30 lines of code total) and should be applied
before the next live session.

**T-30 should be re-run after the bot has operated through at least 2 complete
Event settlement cycles with markout persistence enabled.**
