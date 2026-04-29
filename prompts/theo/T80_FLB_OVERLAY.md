# Phase T-80 — Favorite-Longshot Bias Overlay

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Context
Research synthesis §1: prediction markets exhibit a favorite-longshot bias —
low-probability events are systematically overpriced, high-probability events
are underpriced. Whelan (2025) documented this on 300,000+ Kalshi contracts.

For our quoter: if we know the bias exists, we can adjust our theo to NOT
underprice tail buckets (where Yes is 5-15c) and NOT overprice interior
buckets (where Yes is 85-95c).

## Outputs
- `engine/flb_overlay.py`:
  - Takes raw model probabilities (survival curve from RND or synthetic).
  - Applies a bias correction: shrink extreme probabilities toward 50%.
  - Parameterized by a single shrinkage factor (calibrated from settled data).
  - Default shrinkage: 0.02 (move each probability 2% toward 50%).
- `engine/flb_calibrator.py`:
  - Collects settled Event outcomes over time.
  - Per-bucket: tracks (quoted_probability, did_it_settle_yes).
  - After 10+ settled Events: recalibrate the shrinkage parameter.
- Updated density computation: apply FLB overlay after base density.
- `tests/test_flb_overlay.py`

## Data needed
- Historical Kalshi settlement outcomes for KXSOYBEANMON.
- Start collecting from T-25 (markout tracker already logs fills + outcomes).
- Initially use the Whelan (2025) estimate as default.

## Success criteria
- FLB overlay shifts tail probabilities up and interior probabilities down.
- Shrinkage parameter is reasonable (0.01 - 0.05).
- After 10+ Events, calibrator updates the parameter from real data.
