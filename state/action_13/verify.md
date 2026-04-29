# ACT-13 Verification — Corridor Decomposition Adapter

**Action.** ACT-13
**Verdict.** PASS
**Verifier.** Claude Opus 4.6 (1M context)
**Date.** 2026-04-27

---

## Checklist

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Corridor decomposition math correct | PASS | Yes(i) = P(S_T >= L_i) - P(S_T >= U_i); lower tail = 1 - P(S_T >= L); upper tail = P(S_T >= U). Telescoping sum is algebraically exact. |
| 2 | GBM d2 formula correct | PASS | d2 = (ln(F/K) - 0.5*sigma^2*tau) / (sigma*sqrt(tau)) with F = spot*exp(drift*tau). Verified in models/gbm.py:41. |
| 3 | scipy.special.ndtr equivalent (not scipy.stats.norm.cdf) | PASS | GBM kernel uses math.erfc via identity Phi(x) = 0.5*erfc(-x/sqrt(2)). No scipy.stats.norm.cdf anywhere. |
| 4 | numba.njit on hot-path kernel | PASS | `_corridor_prices` decorated with `@njit(cache=True, fastmath=False)`. `_gbm_prob_above` in gbm.py also njit'd. |
| 5 | No pandas | PASS | No pandas import in engine/corridor.py or tests/test_corridor.py. |
| 6 | Fail-loud CorridorSumError (not silent normalization) | PASS | CorridorSumError(RuntimeError) raised when abs(total - 1.0) > sum_tol. No normalization fallback. |
| 7 | Type hints | PASS | All public and private functions have full type annotations. |
| 8 | Integration with BucketGrid from ACT-04 | PASS | Imports BucketGrid from feeds.kalshi.events; uses .lower_tail, .upper_tail, .interior_buckets, .n_buckets properties. |
| 9 | Input validation (spot, tau, sigma, basis_drift) | PASS | ValueError raised for non-positive or non-finite inputs. 8 validation tests confirm. |
| 10 | Tests pass | PASS | 72/72 tests pass (pytest -v, 1.05s). |
| 11 | Test coverage adequate | PASS | Covers: two-bucket grids, symmetric ATM, sum-to-1 across 48 param combos (3 spot x 4 sigma x 4 tau), OTM tails, short tau, high vol, analytical comparison vs ndtr, CorridorSumError type, input validation, direct njit kernel tests. |
| 12 | GAP-005 closed | PASS | Bucket payoff corridor decomposition D(L) - D(U) now implemented. |

---

## Math verification detail

The GBM kernel in `models/gbm.py` computes:

```
P(S_T >= K) = 0.5 * erfc(-d2 / sqrt(2))
```

where `d2 = (ln(F/K) - 0.5*sigma^2*tau) / (sigma*sqrt(tau))` and `F = spot * exp(basis_drift * tau)`.

This is numerically identical to `ndtr(d2)` via the identity `Phi(x) = 0.5 * erfc(-x / sqrt(2))`.

The corridor kernel `_corridor_prices` computes:
- `out[0] = 1.0 - prob_above[0]` (lower tail)
- `out[i] = prob_above[i-1] - prob_above[i]` for interior buckets
- `out[N-1] = prob_above[N-2]` (upper tail)

Telescoping sum: `(1 - p0) + (p0 - p1) + ... + (p_{N-2} - p_{N-1}) + p_{N-1} = 1.0` exactly.

The test suite confirms analytical parity: interior, lower-tail, and upper-tail prices each match direct `ndtr`-based computation to < 1e-12.

---

## Files reviewed

- `/Users/felipeleal/Documents/GitHub/goated/engine/corridor.py` (implementation)
- `/Users/felipeleal/Documents/GitHub/goated/tests/test_corridor.py` (72 tests)
- `/Users/felipeleal/Documents/GitHub/goated/models/gbm.py` (_gbm_prob_above kernel)
- `/Users/felipeleal/Documents/GitHub/goated/feeds/kalshi/events.py` (BucketGrid type)
- `/Users/felipeleal/Documents/GitHub/goated/state/action_13/plan.md`
- `/Users/felipeleal/Documents/GitHub/goated/state/action_13/handoff.md`
- `/Users/felipeleal/Documents/GitHub/goated/audit/audit_F3_refactor_plan_lip.md` (line 166)
- `/Users/felipeleal/Documents/GitHub/goated/audit/audit_E_gap_register.md` (GAP-005)
