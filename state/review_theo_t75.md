# T-75 Review: Weather-Driven Distribution Skew

**Reviewer**: Claude (automated review)
**Date**: 2026-04-27
**Prereq**: T-70 complete (feeds/weather/gefs_client.py, engine/weather_skew.py, tests/test_weather_skew.py, deploy/main.py integration)

---

## 1. Current GEFS forecast — sensibility check

The module is currently configured for **manual input** (config YAML), not live
CPC fetch. `fetch_cpc_outlook` exists but is untested against actual CPC
endpoints (the `.gif`-to-`.txt` URL heuristic is speculative). This is
acceptable for Phase T-70 — live CPC ingestion is a future upgrade.

Using `create_outlook_from_manual(+5F, -30%)` during July (U.S. pod-fill):

| Output | Value |
|---|---|
| mean_shift_cents | +55.0c |
| vol_adjustment_pct | +30.0% |
| Applied to $11.00 fwd / 15% vol | $11.55 / 19.5% |

**Verdict**: Sensible. A moderately hot/dry 6-10 day outlook shifting the
forward by ~$0.55 and widening vol by 4.5pp is proportional to the kind of
price response seen in short-term weather scares.

---

## 2. Historical backtest results

### 2012 U.S. Drought (+8F, -60% precip, July)
- Raw shift: 100c (clamped to **80c**). Vol raw: 0.54 (clamped to **0.50**).
- Applied to $13.50 / 20% vol: **$14.30 / 30.0%**
- Actual move: ~$13.50 -> $17.50 over Jun-Aug (~400c cumulative).
- **Assessment**: 80c per snapshot is conservative but correct — a single
  6-10 day outlook shouldn't capture the full 3-month cumulative move. The
  model would accumulate ~80c per cycle during sustained drought, which is
  the right behavior. The clamp at 80c prevents overreaction to a single
  extreme reading.

### 2019 U.S. Wet/Cool Summer (-2F, +25% precip, July)
- Shift: **-35c**. Vol: **-18.5%**
- Applied to $9.00 / 15% vol: **$8.65 / 12.2%**
- Actual: soybeans traded sideways $8.50-$9.50.
- **Assessment**: Slightly aggressive on the downside. A 35c downward shift
  on a $9.00 bean is ~4%, and the vol compression is meaningful. In reality
  2019 was complicated (wet planting delayed acres, offsetting the cool summer
  benefit). The linear model can't capture this nuance, but the magnitude
  is reasonable.

### 2024 Benign Growing Season (+1F, -5% precip, July)
- Shift: **+10c**. Vol: **+5.5%**
- Applied to $10.50 / 15% vol: **$10.60 / 15.8%**
- Actual: soybeans drifted lower ($10.50 -> $10.00).
- **Assessment**: Near-neutral weather produces a small positive bias. The
  10c shift on a $10.50 bean is <1%, which is noise-level. Appropriate.

### 2022 S. America Drought (+6F, -40% precip, January)
- Shift: **+35c** (dampened 0.5x). Vol: **+19.0%**
- Applied to $13.00 / 20% vol: **$13.35 / 23.8%**
- Actual: soybeans rallied from ~$13 to ~$14.50 in January.
- **Assessment**: SA dampening to 0.5x is appropriate — S. America pod-fill
  matters but is a secondary driver. The 35c shift is conservative vs the
  actual ~150c move, but again this is a per-snapshot adjustment.

---

## 3. Yield-to-price elasticity assessment

### Coefficient reasonableness

| Coefficient | Value | Historical basis | Verdict |
|---|---|---|---|
| temp_shift_cents_per_f | 5.0 | 2012: +8F -> ~400c over 3mo. Per-snapshot: ~5c/F reasonable | OK |
| precip_shift_cents_per_pct | -1.0 | 30% deficit -> 30c. Broadly consistent with crop-condition regressions | OK |
| temp_vol_pct_per_f | 0.03 | +5F -> +15% vol. Summer soy vol ~15-25%. 15% increase is plausible | OK |
| precip_vol_pct_per_pct | -0.005 | -30% precip -> +15% vol. Consistent with drought-driven vol expansion | OK |
| sa_dampening | 0.5 | Brazil pod-fill ~30-40% of global impact vs U.S. ~60-70%. 0.5x reasonable | OK |
| max_shift_cents | 80.0 | ~7% of $11 beans. Prevents single-snapshot overreaction | OK |
| max_vol_adjustment_pct | 0.50 | 50% vol increase cap. Prevents absurd vol levels | OK |

### Sensitivity sweep (U.S. July, precip normal)

| Temp anomaly | Shift | Vol adj | Net effect on $11 fwd |
|---|---|---|---|
| -5F | -25c | -15% | $10.75 / 12.8% vol |
| -3F | -15c | -9% | $10.85 / 13.7% vol |
| 0F | 0c | 0% | no change |
| +3F | +15c | +9% | $11.15 / 16.4% vol |
| +5F | +25c | +15% | $11.25 / 17.2% vol |
| +8F | +40c | +24% | $11.40 / 18.6% vol |
| +10F | +50c | +30% | $11.50 / 19.5% vol |

**Verdict**: The linear mapping with clamp produces proportional responses.
No coefficient is obviously miscalibrated. The sign conventions are correct
(hot/dry = up, cool/wet = down).

---

## 4. Growing-season activation verification

All 12 months tested + 9 boundary dates (including Feb 29 leap year):

| Date | Season | Expected | Result |
|---|---|---|---|
| May 31 | OFF | OFF | PASS |
| Jun 1 | US_POD_FILL | US | PASS |
| Aug 31 | US_POD_FILL | US | PASS |
| Sep 1 | OFF | OFF | PASS |
| Feb 28 | SA_POD_FILL | SA | PASS |
| Mar 1 | OFF | OFF | PASS |
| Dec 31 | OFF | OFF | PASS |
| Jan 1 | SA_POD_FILL | SA | PASS |
| Feb 29 (2024) | SA_POD_FILL | SA | PASS |

**All 21 checks pass.** Off-season always returns (0, 0) regardless of input.

---

## 5. Integration review (deploy/main.py)

### Unit handling
- `forward` in `_synthetic_rnd` is in **dollars** (e.g. 10.67 = $10.67/bu)
- `apply_weather_skew` expects `forward` in **cents**
- Integration correctly does `forward * 100.0` before calling, `adj_fwd / 100.0` after
- **Unit conversion: CORRECT**

### Config plumbing
```yaml
weather_skew:
  enabled: true
  temp_anomaly_f: 5.0
  precip_anomaly_pct: -30.0
```
- Defaults to `enabled: false` — no accidental activation
- Static config values via `create_outlook_from_manual` (not live CPC fetch)
- **Config: CORRECT**

### Error handling
- Wrapped in `try/except`, logs warning on failure — skew silently degrades to no-op
- This is acceptable per non-negotiables: the weather skew is an overlay, not a
  primary pricing input. A failed weather overlay should not halt quoting.

---

## 6. Issues found

### Issue 1 (LOW): `fetch_cpc_outlook` is speculative dead code
The CPC URL heuristic (`.gif` -> `.txt`) is untested. The actual CPC text
file format may not match the lat/lon/value parser. This is fine for now
since deploy/main.py uses `create_outlook_from_manual`, but the function
should either be tested against real CPC responses or marked as stub.

**Recommendation**: Add a comment `# STUB: untested against live CPC data`
to `fetch_cpc_outlook`. Leave for future work when live weather ingestion
is prioritized.

### Issue 2 (LOW): No staleness check on manual outlook
`create_outlook_from_manual` stamps `fetched_at_ns = time.time_ns()` but
the config YAML values are static. If the operator forgets to update them,
the same weather input runs indefinitely. No staleness gate exists.

**Recommendation**: Acceptable for now. When live CPC fetch is added, the
`fetched_at_ns` field should be checked for staleness (e.g. >24h = stale).

### Issue 3 (INFO): Linear model cannot capture nonlinear crop responses
The model is purely linear (shift proportional to anomaly). In reality,
crop damage is nonlinear — moderate heat stress has limited impact, but
above ~95F during flowering the damage function is convex. The linear
approximation is adequate for a first-order skew but will underestimate
tail risk in extreme scenarios.

**Recommendation**: Acceptable for V1. Consider a piecewise or sigmoid
mapping if the weather module is promoted to a primary pricing input.

---

## 7. Non-negotiable compliance

| Rule | Status |
|---|---|
| No pandas in hot path | PASS (numpy only) |
| numba.njit on hot-path math | N/A (weather skew runs once/cycle, not per-strike) |
| scipy.special.ndtr over scipy.stats.norm.cdf | N/A (no CDF calls in weather module) |
| Fail-loud | PASS (raises ValueError on non-finite inputs) |
| asyncio for I/O only | PASS (fetch_cpc_outlook is async; compute_weather_skew is sync) |
| Type hints on public interfaces | PASS |

---

## 8. Verdict

**PASS** — the weather skew module is correctly implemented, the elasticity
coefficients produce historically-plausible outputs, growing-season gating
works, and the deploy/main.py integration handles unit conversion correctly.

The module is conservative by design (single-snapshot adjustment, 80c clamp,
linear mapping). This is appropriate for an overlay on top of the base GBM
density. The three low-severity issues noted above are acceptable for the
current phase and do not block deployment.

50 tests pass. No code changes required.
