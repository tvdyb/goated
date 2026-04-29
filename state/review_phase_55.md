# Phase 55 — Review: RND Pipeline Validation

**Reviewer date:** 2026-04-28
**Handoff reviewed:** `state/action_rnd_pipeline/handoff.md`
**Premise read:** `prompts/build/PREMISE.md` — confirmed.
**Review discipline read:** `prompts/build/REVIEW_DISCIPLINE.md` — applied.

---

## 1. Test Results

### RND pipeline tests
```
tests/test_rnd_pipeline.py: 39 passed in 1.21s
```

### Full suite
```
tests/: 722 passed in 24.71s
```

**Finding:** Tests pass. Handoff claim "713 total" is stale (now 722 after other work), but the 39 RND tests match exactly. No regressions.

---

## 2. BL Computation Verification

Independently computed BL density via manual 3-point finite difference at 3 strikes against a flat-vol Black-76 surface (F=1050, sigma=0.22, T=30/365.25):

| Strike | Manual density | Pipeline density | Deviation |
|--------|---------------|-----------------|-----------|
| 990    | 0.00422765    | 0.00422765      | 0.0000%   |
| 1050   | 0.00592346    | 0.00592346      | 0.0000%   |
| 1110   | 0.00375777    | 0.00375777      | 0.0000%   |

**Finding (INFO):** BL computation is mathematically correct. Zero deviation at all 3 test strikes.

---

## 3. SVI Butterfly Arb Verification

Calibrated SVI on skewed synthetic smile (skew=-0.1), then independently evaluated Durrleman condition at 10 moneyness points in [-0.3, 0.3]:

- SVI params: a=0.003958, b=0.000252, rho=-0.2981, m=-0.035518, sigma=0.037692
- Pipeline butterfly violations: 0
- Manual independent check: 0/10 violations
- All g(k) values non-negative

**Finding (INFO):** SVI arb constraints work correctly. No butterfly violations on reasonable data.

---

## 4. Sum-to-1 Gate

Pipeline output on synthetic chain (F=1050, 30 strikes from 900 to 1200):

- `bucket_sum = 1.00000000`
- Within [0.98, 1.02]: **YES**
- Algebraic identity confirmed (telescoping sum of survival differences)

**Finding (INFO):** Sum-to-1 gate works correctly. The sum is exactly 1.0 by construction (algebraic identity), not by numerical accident.

---

## 5. Figlewski Tail Properties

On a Gaussian density (mu=1050, sigma=50):

| Property | Result |
|----------|--------|
| All density >= 0 | YES (min = 1.35e-109) |
| Max jump at paste points | 8.22e-05 (< 0.001 threshold) |
| Tails decay toward zero | YES (both ends small relative to peak) |
| Extended range wider than original | YES |
| Extended area finite & positive | YES (1.946) |

**Finding (INFO):** Figlewski tails produce positive, continuous, smoothly decaying density. Paste-point discontinuity is negligible (8e-05).

---

## 6. Non-Negotiable Compliance

| Rule | Status | Evidence |
|------|--------|----------|
| No pandas in engine/ | PASS | Automated source scan + test_pipeline_no_pandas |
| numba.njit on hot-path math | PASS | BL:1, SVI:4, bucket:2, figlewski:2 = 9 total @njit |
| scipy.special.ndtr (not norm.cdf) | PASS | pipeline.py imports ndtr; bisection uses math.erfc (equivalent scalar) |
| Fail-loud | PASS | Every module raises on bad input (BLDensityError, SVICalibrationError, SVIArbViolationError, FiglewskiTailError, BucketSumError, RNDValidationError) |
| No Python loops over strikes in hot path | PASS | All loops in @njit kernels |
| Fail-safe pattern | PASS | validate inputs -> compute -> validate outputs -> return |

---

## 7. Scoring on Settled Events

**Status: INCOMPLETE-DATA**

The M0 spike notebook (`research/m0_spike_soy_monthly.ipynb`) was unable to pull live CME options data (free APIs don't serve ZS futures options). It constructed a **synthetic** chain and explicitly declared verdict "INCONCLUSIVE (synthetic chain)".

The production pipeline cannot be scored against settled Events in this review because:
1. No cached CME options chain data exists for any settled `KXSOYBEANMON` Event.
2. The CME ingest module (`feeds/cme/options_chain.py`) requires a live HTTP pull.
3. Without real market data, any comparison is circular (model recovering its own inputs).

**Finding (WARN):** Cannot validate KC-F4-01 hypothesis (model outperforms Kalshi mid on >50% of strikes). This is a data availability limitation, not a code defect. Production scoring requires:
- IB API or CME EOD data for the matching expiry
- At least 1 settled `KXSOYBEANMON` Event with captured Kalshi midpoints

---

## 8. Cross-Reference with M0 Spike Notebook

The notebook implements the same methodology (BL -> SVI -> density -> bucket integration) but as standalone code without the productionized modules. The pipeline in `engine/rnd/` is a cleaner, JIT-compiled, better-validated implementation of the same algorithm.

Key differences:
- Notebook uses `np.gradient` for BL; pipeline uses explicit 3-point stencil in @njit kernel (more accurate for non-uniform spacing)
- Notebook uses single-pass SVI fit; pipeline uses two-pass (first without penalty, then with)
- Notebook skips Figlewski tails if not needed; pipeline always attempts extension with graceful degradation
- Pipeline adds explicit normalization check after each stage

**Finding (INFO):** Pipeline is a strict improvement over the notebook methodology. No contradictions.

---

## 9. Architecture Assessment

The pipeline is well-structured:
- Clear stage separation (IV extraction -> SVI -> BL -> normalize -> tails -> buckets)
- Each stage fails independently with a typed exception
- `compute_rnd()` is the single entry point; all internals are testable in isolation
- `BucketPrices` dataclass provides a clean output contract for downstream consumers

**Finding (INFO):** Code quality is high. 1,051 LoC production / 571 LoC tests = 0.54 test-to-code ratio. All modules have multiple error paths exercised.

---

## Findings Summary

| # | Severity | Description | File:Line |
|---|----------|-------------|-----------|
| F1 | INFO | BL math correct (0% deviation at 3 strikes) | engine/rnd/breeden_litzenberger.py:24-57 |
| F2 | INFO | SVI arb check correct (0/10 violations on valid surface) | engine/rnd/svi.py:90-128 |
| F3 | INFO | Sum-to-1 algebraically exact (telescoping identity) | engine/rnd/bucket_integrator.py:104-127 |
| F4 | INFO | Figlewski paste-point continuity < 0.001 | engine/rnd/figlewski.py:107-135 |
| F5 | INFO | All 6 non-negotiables satisfied | engine/rnd/*.py |
| F6 | WARN | Cannot score on settled Events — no live CME data available | N/A (data dependency) |
| F7 | INFO | Pipeline is strict improvement over M0 notebook methodology | engine/rnd/pipeline.py |

---

## Verdict

**PASS**

Rationale:
- All tests pass (39 RND + 722 total, zero failures).
- BL computation mathematically verified correct.
- SVI butterfly arb constraints verified correct.
- Sum-to-1 within [0.98, 1.02] (exactly 1.0).
- No negative density values.
- No non-negotiable violations.
- Figlewski tails are positive, continuous at paste points, decay smoothly.

**WARNING (F6):** Model cannot yet be scored against settled Events due to absence of real CME options data. KC-F4-01 monitoring flag is set but does not block the pipeline. The next phase that provides real CME data (via IB API or CME delayed data) should re-run this scoring step.
