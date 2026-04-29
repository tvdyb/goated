# Phase T-90 — Full Theo Stack Integration Test

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- ALL prior T-phases complete (or explicitly skipped with justification).

## Context
This phase validates that all theo components work together without
conflicts. The full theo computation should be:

1. **Forward:** Pyth real-time ZS price (T-00).
2. **Vol:** Kalshi-implied vol, bounded by seasonal regime (T-10, T-20).
3. **Base density:** Full RND from IBKR options chain if available,
   else synthetic GBM with calibrated forward + vol (T-40, T-50).
4. **Overlays applied in order:**
   a. WASDE mean-shift (if post-release window) (T-60).
   b. Weather skew (if growing season) (T-70).
   c. Goldman roll drift (if in roll window) (T-85).
   d. Favorite-longshot bias correction (T-80).
5. **Result:** final survival curve → bucket prices → quoter.

## Outputs
- `engine/theo.py` — unified theo computation that chains all components:
  - `compute_theo(forward, vol, chain, overlays) -> BucketPrices`
  - Each overlay is optional (disabled if not configured or data unavailable).
  - Logging: which overlays are active, what adjustments they made.
- Updated `deploy/main.py` and `deploy/lip_mode.py` — use `compute_theo()`.
- Updated `deploy/dashboard.py`:
  - Show active overlays per cycle.
  - Show theo breakdown: base + each overlay's contribution.
- `tests/test_theo_integration.py`:
  - Test full chain with all overlays active.
  - Test graceful degradation (each overlay disabled individually).
  - Test fallback cascade: IBKR → synthetic+calibrated_vol → synthetic+15%.
- Run full test suite. All 848+ tests must pass.

## Success criteria
- All overlays compose correctly without conflicts.
- Theo degrades gracefully when components are unavailable.
- Dashboard shows active pricing source and overlay status.
- PnL attribution can separate: base theo P&L vs overlay contributions.
- The system is strictly better than the original hardcoded synthetic.

## Handoff
- Update `CLAUDE.md` with complete theo stack status.
- Update `state/PROJECT_CONTEXT.md`.
- Write `state/digest_theo_stack.md` — summary of all theo components.
