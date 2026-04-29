# Phase T-20 — Seasonal Vol Regime Overlay

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-15 must show PASS.

## Context
Soybean vol follows a seasonal pattern (CME "Vol is High by the Fourth of July"):
- Jan-Mar: moderate (14-18%)
- Apr-May: rising (16-20%)
- Jun-Aug: peak — U.S. pod-fill weather risk (20-30%+)
- Sep-Oct: declining post-harvest (15-20%)
- Nov-Dec: quiet (12-16%)
- Jan-Feb: South American pod-fill window (15-20%)

The Kalshi-implied vol (T-10) captures current market pricing. The seasonal
overlay serves as a prior / floor — if the Kalshi book is thin and implied vol
calibration fails, the seasonal regime gives a better fallback than flat 15%.

## Outputs
- `engine/seasonal_vol.py` — lookup table of monthly vol regime.
  - Returns (vol_floor, vol_ceiling) for a given month.
  - Used as bounds on the Kalshi-implied vol calibration.
  - If calibrated vol < floor, use floor. If > ceiling, use ceiling.
- Updated `engine/implied_vol.py` — seasonal bounds applied.
- `tests/test_seasonal_vol.py`

## Success criteria
- Summer months (Jun-Aug) have higher vol bounds than winter.
- Calibrated vol is bounded by seasonal regime.
- Fallback uses seasonal midpoint instead of flat 15%.
