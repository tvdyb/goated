# ACT-13 Plan -- Corridor Decomposition Adapter

**Action.** ACT-13 (Wave 0)
**Summary.** Bucket Yes-price vector via corridor decomposition adapter on existing GBM + sum-to-1 gate.
**Deps.** ACT-04 (complete-pending-verify), ACT-08 (verified-complete).
**Closes.** GAP-005.

---

## Design

### Core identity

A Kalshi bucket [L, U) has Yes-price = P(L <= S_T < U).

Using the existing GBM model's P(S_T > K) (digital call) output:

- Interior bucket [L, U): yes_price = P(S_T >= L) - P(S_T >= U)
- Lower tail [0, L): yes_price = 1 - P(S_T >= L)
  (equivalently: P(S_T < L))
- Upper tail [U, inf): yes_price = P(S_T >= U)

This is the "digital-corridor decomposition" from Phase 08 section 1.

### Sum-to-1 gate

All bucket Yes-prices must sum to 1.0 within tolerance (1e-9).
If violated: raise CorridorSumError (fail-loud, no silent normalization).

### Module: `engine/corridor.py`

**Public API:**

```python
def bucket_prices(
    grid: BucketGrid,
    spot: float,
    tau: float,
    sigma: float,
    basis_drift: float = 0.0,
    *,
    sum_tol: float = 1e-9,
) -> np.ndarray:
```

Returns a 1-D float64 array of Yes-prices, one per bucket in grid order.

**Implementation:**

1. Extract strike boundaries from BucketGrid into a numpy array of
   unique interior boundaries (the finite edges between buckets).
2. Compute P(S_T >= K) for each boundary using the existing
   `_gbm_prob_above` njit kernel from `models/gbm.py`.
3. Compute corridor differences via an njit kernel:
   - Lower tail: 1 - P(S_T >= first_boundary)
   - Interior: P(S_T >= L_i) - P(S_T >= U_i)
   - Upper tail: P(S_T >= last_boundary)
4. Assert sum-to-1 within tolerance.

### Non-negotiable compliance

- scipy.special.ndtr: the GBM kernel already uses erfc (equivalent); no new scipy.stats.norm.cdf calls.
- numba.njit: the corridor difference kernel is njit'd.
- No pandas.
- Fail-loud: CorridorSumError on violation.

### Integration with ACT-04

Uses `BucketGrid` from `feeds/kalshi/events.py`. The grid's MECE
validation (already enforced by ACT-04) guarantees contiguous boundaries
which ensures the corridor decomposition is exact.

---

## Test plan

1. Single degenerate bucket [0, inf) -- Yes-price = 1.0
2. Two buckets (lower + upper tail) -- sum to 1.0
3. Symmetric buckets around ATM -- middle bucket has highest price
4. Sum-to-1 across varied GBM params (spot, sigma, tau, drift)
5. Edge: very OTM tail buckets (near-zero prices)
6. Edge: very short tau (near-expiry)
7. Comparison against analytical P(L <= S_T < U) from scipy.special.ndtr
8. CorridorSumError raised on forced violation (mock)
