# F4-ACT-03 — RND Extractor Pipeline: Implementation Plan

**Action.** F4-ACT-03 (Phase 50)
**Type.** feature | **Effort.** XL
**Gaps closed.** GAP-006, GAP-036, GAP-037, GAP-038, GAP-041, GAP-042, GAP-043, GAP-044, GAP-045, GAP-049, GAP-101, GAP-003

---

## Deliverables

| File | Purpose |
|---|---|
| `engine/rnd/__init__.py` | Package init, re-exports |
| `engine/rnd/breeden_litzenberger.py` | BL density: `f(K) = e^(rT) * d^2C/dK^2` |
| `engine/rnd/svi.py` | SVI calibration with butterfly arb constraints |
| `engine/rnd/figlewski.py` | Piecewise-GEV tail extension |
| `engine/rnd/bucket_integrator.py` | Integrate density over Kalshi half-line strikes |
| `engine/rnd/pipeline.py` | Orchestrator: chain -> BL -> SVI -> Figlewski -> buckets |
| `tests/test_rnd_pipeline.py` | Full test suite |

## Architecture

```
OptionsChain (feeds/cme/options_chain.py)
    |
    v
BreedenLitzenberger  -- raw density via finite differences on call prices
    |
    v
SVI calibration      -- smooth IV surface, butterfly arb check
    |
    v
SVI-smoothed density -- BL applied to SVI-smoothed call prices
    |
    v
Figlewski tails      -- GEV extension beyond observed strikes
    |
    v
BucketIntegrator     -- P(S>K) for each Kalshi half-line strike
    |
    v
BucketPrices         -- per-bucket Yes-prices, sum-to-1 validated
```

## Non-negotiables enforced

- No pandas. All arrays are numpy.
- `numba.njit` on SVI evaluation kernel and integration kernel.
- `scipy.special.ndtr` (not `scipy.stats.norm.cdf`).
- Fail-loud: raise on negative density, arb violations, sum-to-1 failure.
- No Python loops over strikes in hot-path code.

## Implementation order

1. BL density extraction (standalone, testable with synthetic BS data)
2. SVI calibration (standalone, testable with synthetic smile)
3. Figlewski tail extension (depends on SVI density)
4. Bucket integrator (depends on density function)
5. Pipeline orchestrator (wires 1-4 together)
6. Tests
7. Handoff

## Data flow types

- Input: `OptionsChain` from `feeds/cme/options_chain.py`
- Internal: numpy arrays for strikes, densities, IVs
- Output: `BucketPrices` dataclass with strikes, yes_prices, metadata
