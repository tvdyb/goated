# ACT-13 Handoff -- Corridor Decomposition Adapter

**Action.** ACT-13
**Status.** complete-pending-verify
**Wave.** 0
**Implementer.** Claude Opus 4.6 (1M context)
**Date.** 2026-04-27

---

## Summary

Implemented the corridor decomposition adapter that converts the existing
GBM model's P(S_T > K) output into per-bucket Yes-prices for Kalshi
weekly soybean bucket markets. Closes GAP-005.

## Files created/modified

| File | Action |
|---|---|
| `engine/corridor.py` | Created: corridor adapter module |
| `tests/test_corridor.py` | Created: 72 tests |
| `state/action_13/plan.md` | Created: implementation plan |
| `state/action_13/handoff.md` | Created: this file |
| `state/dependency_graph.md` | Updated: ACT-13 status |

## Design

The adapter takes a `BucketGrid` (from ACT-04) and GBM parameters,
extracts the N-1 interior boundary strikes, computes P(S_T >= K) for
each via the existing `_gbm_prob_above` njit kernel from `models/gbm.py`,
then applies the corridor identity:

- Lower tail: 1 - P(S_T >= first_boundary)
- Interior [L, U): P(S_T >= L) - P(S_T >= U)
- Upper tail: P(S_T >= last_boundary)

A sum-to-1 gate raises `CorridorSumError` (fail-loud) if prices deviate
from 1.0 beyond tolerance. The telescoping sum is algebraically exact,
so in practice the gate is a sanity check against implementation bugs.

## Non-negotiable compliance

- `scipy.special.ndtr` equivalent: GBM kernel uses `math.erfc` (numerically equivalent)
- `numba.njit`: `_corridor_prices` kernel is njit'd
- No pandas
- Fail-loud: `CorridorSumError` on sum-to-1 violation

## Test results

72 tests pass covering: two-bucket grids, symmetric ATM buckets,
sum-to-1 across 48 parameter combinations, OTM/short-tau edge cases,
analytical comparison against scipy.special.ndtr, input validation,
and direct njit kernel tests.

## Verify checklist

- [ ] `source .venv/bin/activate && python -m pytest tests/test_corridor.py -v` -- 72 pass
- [ ] `engine/corridor.py` uses no pandas, no scipy.stats.norm.cdf
- [ ] `_corridor_prices` is @njit
- [ ] `CorridorSumError` raised on violation (not silent normalization)
- [ ] BucketGrid from ACT-04 is the grid input type
