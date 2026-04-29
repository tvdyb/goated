# Phase 55 Digest — M0 Spike Notebook v2 (F4-ACT-15)

**Phase.** 55
**Action.** F4-ACT-15
**Date.** 2026-04-28
**Verdict.** INCONCLUSIVE (synthetic chain — methodology validated)

---

## Summary

Created `research/m0_spike_soy_monthly_v2.ipynb` — a Jupyter notebook that runs the production `engine.rnd.pipeline.compute_rnd()` offline against Kalshi settled event data and scores RND-implied bucket prices against realized outcomes.

## M0 gate result

**INCONCLUSIVE** — synthetic options chain makes the test circular. The density IS the model, so the comparison only validates that the pipeline works, not that CME-implied RND outpredicts Kalshi midpoints.

Per `state/wave_1_status.md`, INCONCLUSIVE means: **Wave 2 proceeds with mandatory re-evaluation gate at F4-ACT-09** (M0 backtest validator).

## Phase 15 bug fixes applied

| Bug | Fix |
|---|---|
| F-01: `np.trapz` removed in numpy 2.x | Production pipeline uses `np.trapezoid` |
| F-02: API field `yes_bid` vs `yes_bid_dollars` | Notebook uses `last_price_dollars` |
| F-03: API field `yes_price` vs `yes_price_dollars` | Notebook uses `last_price_dollars` |

## What the notebook validates

1. Production `compute_rnd()` runs end-to-end without error
2. BucketPrices output has valid survival function (monotone, [0,1])
3. Bucket sum-to-1 gate passes
4. Scoring framework correctly compares model vs Kalshi vs realized

## What it does NOT validate (requires real CME data)

1. Whether CME-implied RND is empirically more accurate than Kalshi midpoints
2. Whether the model has actual economic edge (KC-F4-01)
3. Tail bucket accuracy with real volatility surfaces

## For definitive GO/NO-GO

1. Deploy F4-ACT-02 CME ingest with real IB API historical options
2. Accumulate 4+ settled KXSOYBEANMON events
3. Re-run notebook with real chain data
4. If still insufficient data, F4-ACT-09 (Wave 3) backtest harness will accumulate more

## Decisions

No new ODs resolved. OD-40 (M0 historical data depth: 4 settled events minimum) remains pending — fewer than 4 settled KXSOYBEANMON events likely exist at this date.
