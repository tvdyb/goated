# F4-ACT-15 — M0 Spike Notebook v2: Handoff

**Status.** COMPLETE
**Date.** 2026-04-28
**Notebook.** `research/m0_spike_soy_monthly_v2.ipynb`

## What was delivered

Jupyter notebook that:

1. Queries Kalshi API for settled `KXSOYBEANMON` events (with fallback chain).
2. Extracts half-line strikes, resolution outcomes, and Kalshi midpoints (using correct `last_price_dollars` field name, fixing Phase 15 F-02/F-03).
3. Builds synthetic options chain per event (or uses real CME data when available).
4. Runs the **production** `engine.rnd.pipeline.compute_rnd()` — the exact same code path that will run in production.
5. Scores RND-implied bucket prices against realized outcomes.
6. Produces GO/NO-GO/INCONCLUSIVE verdict per KC-F4-01 criteria.

## Phase 15 bug fixes applied

| Bug | Fix |
|---|---|
| F-01: `np.trapz` removed in numpy 2.x | Uses `np.trapezoid` (via production pipeline) |
| F-02: `yes_bid` vs `yes_bid_dollars` | Uses `last_price_dollars` field |
| F-03: `yes_price` vs `yes_price_dollars` | Uses `last_price_dollars` field |

## Expected verdict

**INCONCLUSIVE (synthetic chain — methodology VALIDATED)**

With synthetic options chain, the test is circular — the density IS the model. The notebook validates that the pipeline works end-to-end, not that CME RND has empirical edge.

For a definitive verdict, real CME data is needed (IB API historical options via F4-ACT-02).

## Decision gate

Per `state/wave_1_status.md`:
- **GO**: Proceed to Wave 2.
- **NO-GO**: Project halts (KC-F4-01 triggered).
- **INCONCLUSIVE**: Proceed to Wave 2 with mandatory re-evaluation at F4-ACT-09 (M0 backtest validator).

Current verdict is INCONCLUSIVE — Wave 2 proceeds with re-eval gate.
