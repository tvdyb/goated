# Phase T-45 — Review: IBKR Options Chain Data

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-40 complete. IB Gateway running.

## Task
1. Pull a live ZS options chain via the new IBKR ingest.
2. Validate: number of strikes, price ranges, IV surface shape.
3. Compare IBKR IVs to the Kalshi-implied vol from T-10. How different?
4. Feed the IBKR chain into `engine/rnd/pipeline.compute_rnd()`. Does it work?
5. Compare RND bucket prices vs synthetic GBM bucket prices for the current Event.
6. Quantify the difference per strike in cents.

## Output
- `state/review_theo_t45.md` — IBKR data quality report, RND vs synthetic comparison.
