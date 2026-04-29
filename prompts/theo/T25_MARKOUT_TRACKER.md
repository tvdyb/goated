# Phase T-25 — Per-Bucket Fill Markout Tracker

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-15 must show PASS (need calibrated theo to compute markout).

## Context
We're getting adversely selected — filled on one side, then the price moves
against us. We need to measure this systematically. Markout = the change in
fair value after a fill, measured at 1m, 5m, and 30m.

If markout is consistently negative on a strike, that strike is "toxic" —
informed traders are picking us off there. We should widen or withdraw.

## Outputs
- `engine/markout.py` — markout tracker:
  - On each fill: record (timestamp, market_ticker, side, fill_price, theo_at_fill).
  - On each subsequent cycle: update markout = theo_now - theo_at_fill for open fills.
  - After 1m, 5m, 30m: snapshot the markout and store.
  - Compute per-bucket average markout over a rolling window.
  - Expose: `get_toxic_strikes()` → list of strikes where avg markout < -2c.
- Updated `deploy/lip_mode.py`:
  - Record fills into markout tracker.
  - If a strike is toxic, either widen spread or skip it.
- Updated `deploy/dashboard.py`:
  - Show per-bucket markout (1m, 5m, 30m) in a new section.
  - Color code: green (positive markout = good fills), red (negative = adverse selection).
- `tests/test_markout.py`

## Success criteria
- Markout is computed correctly (positive = we got a good fill, negative = adverse).
- Toxic strikes are identified within 30 minutes of running.
- Dashboard shows markout per bucket.
- Toxic strikes trigger wider spreads (not complete withdrawal — still want LIP).
