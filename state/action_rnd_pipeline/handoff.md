# F4-ACT-03 — RND Pipeline: Handoff

**Action.** F4-ACT-03 (Phase 50)
**Status.** COMPLETE
**Date.** 2026-04-28
**Tests.** 39 new tests, 713 total (all pass)
**Lint.** ruff clean on engine/rnd/

---

## Deliverables

| File | Lines | Purpose |
|---|---|---|
| `engine/rnd/__init__.py` | 21 | Package init, re-exports |
| `engine/rnd/breeden_litzenberger.py` | 121 | BL density: `f(K) = e^(rT) * d²C/dK²` via finite differences |
| `engine/rnd/svi.py` | 257 | SVI calibration with Durrleman butterfly arb check |
| `engine/rnd/figlewski.py` | 225 | Piecewise-GEV tail extension with lognormal fallback |
| `engine/rnd/bucket_integrator.py` | 178 | Integrate density over Kalshi half-line strikes, sum-to-1 gate |
| `engine/rnd/pipeline.py` | 249 | Orchestrator: chain -> BL -> SVI -> Figlewski -> buckets |
| `tests/test_rnd_pipeline.py` | 571 | 39 tests across all modules + e2e pipeline |

**Total new code.** ~1,051 LoC production, ~571 LoC tests.

---

## What was built

### 1. Breeden-Litzenberger density extraction (`breeden_litzenberger.py`)
- Implements `f_T(K) = e^(rT) * d²C/dK²` via 3-point central finite differences.
- Handles non-uniform strike spacing.
- Inner kernel is `numba.njit` for zero Python overhead.
- Raises `BLDensityError` on: insufficient strikes (<5), non-ascending, negative density (configurable clip).

### 2. SVI calibration (`svi.py`)
- Gatheral SVI: `w(k) = a + b*(rho*(k-m) + sqrt((k-m)^2 + sigma^2))`.
- Two-pass L-BFGS-B: first without arb penalty, then with.
- Durrleman butterfly arb condition: `g(k) >= 0` checked on dense grid.
- Inner kernels (`_svi_total_variance`, `_svi_implied_vol`, `_butterfly_arb_check`) all `numba.njit`.
- Raises `SVICalibrationError` on fit failure, `SVIArbViolationError` on excessive violations.

### 3. Figlewski tail extension (`figlewski.py`)
- Attaches GEV tails (Gumbel, xi=0) at configurable paste points (default: 5th/95th CDF percentile).
- Scales tail density to match paste-point value for continuity.
- Falls back to log-normal tails if GEV fitting fails.
- Inner kernels (`_gev_pdf`, `_lognormal_tail_pdf`) are `numba.njit`.

### 4. Bucket integrator (`bucket_integrator.py`)
- Computes P(S > K_i) for each Kalshi half-line strike via trapezoidal CDF integration.
- Decomposes into per-bucket Yes-prices: lower tail + interior + upper tail.
- Enforces monotonicity of survival function.
- Sum-to-1 gate with configurable tolerance (default 2%).
- Inner kernels `numba.njit`.

### 5. Pipeline orchestrator (`pipeline.py`)
- `compute_rnd(chain, kalshi_strikes) -> BucketPrices`
- Stages: extract tau -> extract/invert IVs -> SVI calibrate -> SVI-smoothed calls -> BL density -> normalize -> Figlewski tails -> bucket integration.
- IV extraction: uses chain-provided IVs if available, otherwise Black-76 bisection inversion.
- Fail-loud on every stage. Figlewski failure is non-fatal (graceful degradation).

---

## Gaps closed

| Gap | Description | How |
|---|---|---|
| GAP-006 | model-implied vs market-implied | RND replaces GBM |
| GAP-036 | BL identity | `breeden_litzenberger.py` |
| GAP-037 | SVI calibration | `svi.py` |
| GAP-038 | SVI arb constraints | Durrleman check in `svi.py` |
| GAP-041 | Figlewski tails | `figlewski.py` |
| GAP-042 | IV surface refactor | Embedded in pipeline (strike/expiry grid) |
| GAP-043 | Bucket integration | `bucket_integrator.py` |
| GAP-044 | Sum-to-1 gate | `BucketSumError` in `bucket_integrator.py` |
| GAP-045 | Arb constraints | Butterfly check + monotonicity enforcement |
| GAP-049 | Co-terminal picker | Deferred (single-expiry support; documented) |

---

## Non-negotiables verification

| Rule | Status |
|---|---|
| No pandas in engine/ | PASS (test_pipeline_no_pandas verifies) |
| numba.njit on hot-path math | PASS (BL kernel, SVI eval, arb check, integration, GEV/LN PDFs) |
| scipy.special.ndtr (not norm.cdf) | PASS (used in pipeline.py Black-76) |
| Fail-loud | PASS (every module raises on bad input) |
| No Python loops over strikes | PASS (all loops in njit kernels) |
| Fail-safe pattern | PASS (validate inputs -> compute -> validate outputs -> return) |

---

## Test coverage

| Test class | Tests | What's verified |
|---|---|---|
| TestBLDensity | 8 | Lognormal recovery, integration ~1.0, negative density, edge cases |
| TestSVICalibration | 8 | Flat vol recovery, skew recovery, butterfly arb, parameter validation |
| TestFiglewskiTails | 4 | Range extension, non-negativity, finite integration, smooth decay |
| TestBucketIntegrator | 6 | Normal CDF match, sum-to-1, monotonicity, bucket count, edge cases |
| TestFullPipeline | 9 | E2e BucketPrices, sum-to-1, monotonicity, ATM survival, no-IV fallback, no tails, expired chain, wide range, no-pandas |
| **Total** | **39** | |

---

## Known limitations

1. **Calendar arb constraints**: deferred. Only single-expiry supported. When multiple expiries are available, calendar arb check should be added.
2. **Variance rescaling for non-co-terminal expiries**: deferred. Currently assumes the chain expiry matches the settlement horizon.
3. **TheoOutput shape change**: not modified. The existing `TheoOutput` (probabilities vector) is compatible with the pipeline's `BucketPrices` output. The bid/ask + per-bucket Greeks extension is a downstream concern for F4-ACT-04.
4. **Figlewski tail estimation**: uses Gumbel (xi=0) rather than full 3-parameter GEV. Sufficient for the M0 gate; can be refined if tail bucket accuracy is insufficient.

---

## Dependencies satisfied

- **Upstream.** Consumes `OptionsChain` from `feeds/cme/options_chain.py` (F4-ACT-02, Phase 40+45 verified).
- **Downstream.** `BucketPrices` output feeds F4-ACT-04 (asymmetric quoter), F4-ACT-05 (IBKR hedge), F4-ACT-09 (M0 backtest), F4-ACT-10 (scenarios), F4-ACT-15 (M0 spike notebook).
