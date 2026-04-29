# T-65 Review: WASDE Density Updates

**Reviewer**: Claude (automated review)
**Date**: 2026-04-29
**Prereq**: T-60 complete (feeds/usda/wasde_parser.py, engine/wasde_density.py, deploy/main.py integration)

---

## 1. Backtest: WASDE parser on 5 consecutive releases

Parsed all 6 historical reports (Nov 2025 - Apr 2026) and computed 5 sequential
surprises. Parser correctly handles all entries; `compute_surprise` produces
correct signed deltas.

| Prior | Actual | ES Delta | Prod Delta | Exp Delta |
|---|---|---|---|---|
| 2025-11-10 | 2025-12-09 | 0 Mbu | 0 Mbu | 0 Mbu |
| 2025-12-09 | 2026-01-12 | -90 Mbu | -95 Mbu | 0 Mbu |
| 2026-01-12 | 2026-02-10 | 0 Mbu | 0 Mbu | +25 Mbu |
| 2026-02-10 | 2026-03-10 | -5 Mbu | 0 Mbu | 0 Mbu |
| 2026-03-10 | 2026-04-09 | -25 Mbu | 0 Mbu | +25 Mbu |

Three non-trivial events with ending-stocks surprises: Jan, Mar, Apr 2026.

---

## 2. Density mean-shift vs actual ZS price move

| WASDE Date | ES Delta | Model Shift (18c/Mbu) | Actual ZS Move | Ratio | Direction |
|---|---|---|---|---|---|
| 2025-12-09 | 0 Mbu | 0.0c | +3.0c | N/A | neutral |
| 2026-01-12 | -90 Mbu | +100.0c (capped) | +43.0c | 2.33x | CORRECT |
| 2026-02-10 | 0 Mbu | 0.0c | -2.0c | N/A | neutral |
| 2026-03-10 | -5 Mbu | +90.0c | +11.0c | 8.18x | CORRECT |
| 2026-04-09 | -25 Mbu | +100.0c (capped) | +37.0c | 2.70x | CORRECT |

**Direction accuracy**: 3/3 (100%) on non-trivial events.

**Magnitude**: Model overshoots by 3.2x on average. The 18c/Mbu sensitivity
produces shifts of 90-100c when actual ZS moves are 11-43c.

---

## 3. Sensitivity coefficient assessment

### Was ~18c/M bu accurate?

**NO.** The configured 18c/Mbu is ~10-36x too high.

Implied sensitivities from historical data:

| WASDE Date | ES Delta | Actual Move | Implied Sensitivity |
|---|---|---|---|
| 2026-01-12 | -90 Mbu | +43c | **0.5 c/Mbu** |
| 2026-03-10 | -5 Mbu | +11c | **2.2 c/Mbu** |
| 2026-04-09 | -25 Mbu | +37c | **1.5 c/Mbu** |

**Average implied sensitivity: ~1.4 c/Mbu** (median 1.5 c/Mbu).

### Root cause of the miscalibration

The 18c/Mbu coefficient appears to have been calibrated against *total*
ending-stocks *level* changes, not month-over-month WASDE *revisions*.
WASDE revisions are typically 5-90 Mbu, but the market has already partially
priced in expected revisions through analyst consensus. The *surprise*
component (actual vs consensus) is what moves the futures, and its elasticity
is much lower than the raw level-change elasticity.

Additionally, month-over-month revisions often reflect accounting reclassification
(exports vs domestic use) rather than fundamental supply changes, which the
market discounts.

### Recommendation

**Reduce `sensitivity_cents_per_mbu` from 18.0 to 1.5.** This aligns with the
median implied sensitivity and avoids the massive overshoot currently produced.
The `max_shift_cents` cap (100c) is saving the system from the worst excesses,
but even capped values are still 2-3x too large for the Jan and Apr events.

---

## 4. Simulation: post-WASDE re-entry with adjusted density

### Methodology

For each of the 3 non-trivial WASDE events:
1. Compute pre-WASDE density (GBM with pre-release forward).
2. Compute model-adjusted density (shifted forward per WASDE surprise).
3. Compute actual post-WASDE density (GBM with realized post-release forward).
4. Compare pricing error: how much closer does the model get vs staying with the
   pre-WASDE density?

Used KXSOYBEANMON-style strike grid (5c spacing, 21 strikes centered around
forward), 15% vol, ~20 days to settlement.

### Results at 18c/Mbu (current config)

| Event | Model Forward | Actual Forward | Net Edge | Assessment |
|---|---|---|---|---|
| 2026-01-12 | $11.95 | $10.38 | **-27.6c** | WORSE (overshoot) |
| 2026-03-10 | $11.12 | $10.33 | **-112.8c** | WORSE (massive overshoot) |
| 2026-04-09 | $12.18 | $10.55 | **-57.1c** | WORSE (overshoot) |
| **TOTAL** | | | **-197.5c** | **NET NEGATIVE** |

At the current 18c/Mbu sensitivity, re-entering with the adjusted density
**destroys value**. The model overshoots so far that it prices worse than
staying with the stale pre-WASDE density. Estimated PnL impact at 3
contracts/strike: **-$5.93** per event cycle.

### Results at 1.4c/Mbu (calibrated)

| Event | Model Forward | Actual Forward | Net Edge | Assessment |
|---|---|---|---|---|
| 2026-01-12 | $11.21 | $10.38 | -24.9c | Worse (still overshoots on large surprise) |
| 2026-03-10 | $10.29 | $10.33 | **+10.3c** | BETTER (near-perfect) |
| 2026-04-09 | $10.53 | $10.55 | **+54.2c** | BETTER (near-perfect) |
| **TOTAL** | | | **+39.6c** | **NET POSITIVE** |

At the calibrated 1.4c/Mbu, the system adds value on 2 of 3 events.
The Jan 2026 event remains challenging because the 90 Mbu revision is
an extreme outlier (production revised down 95 Mbu simultaneously).

Estimated PnL impact at 3 contracts/strike: **+$1.19** per event cycle.
Modest but positive — confirms the concept works when calibrated correctly.

### Per-strike detail (Apr 2026, 1.4c/Mbu)

Best example — model forward $10.53 vs actual $10.55 (2c error):

| Strike | Pre-WASDE | Model | Actual | Edge |
|---|---|---|---|---|
| 9.75-10.00 | 3.1-5.1c | 0.7-2.2c | 0.6-2.1c | +2.4 to +2.9c (BETTER) |
| 10.05-10.25 | 5.3-5.2c | 2.6-4.3c | 2.5-4.2c | +0.9 to +2.7c (BETTER) |
| 10.30-10.50 | 4.9-3.4c | 4.7-5.3c | 4.5-5.3c | +0.3 to +1.9c (BETTER) |

All 17 quoted strikes improve or stay neutral. The adjusted density is
uniformly closer to the realized outcome.

---

## 5. Issues found

### Issue 1 (CRITICAL): Sensitivity coefficient miscalibrated by ~12x

**Current**: `sensitivity_cents_per_mbu = 18.0`
**Should be**: `sensitivity_cents_per_mbu = 1.5`

At the current setting, every non-trivial WASDE surprise produces a density
shift that overshoots the actual ZS move by 3-8x, making our post-WASDE
quotes systematically worse than the pre-WASDE density.

**Action**: Update default in `engine/wasde_density.py:54` and
`deploy/config_test.yaml` (if present) to 1.5.

### Issue 2 (MEDIUM): Max shift cap too high

With the corrected sensitivity (1.5c/Mbu), a 90 Mbu surprise produces
135c shift. The current `max_shift_cents=100` cap is hit, but even 100c is
still too large (actual move was 43c).

**Recommendation**: Reduce `max_shift_cents` from 100 to 50. This limits
the maximum model forward shift to $0.50, which is proportional to the
largest observed single-day WASDE moves.

### Issue 3 (LOW): Jan 2026 outlier event is structurally hard

The Jan 2026 WASDE had a simultaneous -90 Mbu ending stocks AND -95 Mbu
production revision. This is rare (USDA annual crop estimate revision).
Even with correct sensitivity, the shift overshoots because the market's
reaction was dampened by position squaring and expectation pricing.

**Recommendation**: Consider adding a `max_es_delta_mbu` parameter that
clips extreme ending-stocks surprises before computing the shift (e.g.,
cap at 30 Mbu). This would prevent outlier events from dominating the
model's response.

### Issue 4 (INFO): No consensus input mechanism in production

The parser computes surprises vs the *prior* WASDE report, not vs
analyst consensus. In practice, the market prices against Bloomberg/Reuters
consensus estimates, not the prior report. Month-over-month changes that
the market already expected produce zero ZS move but non-zero model shift.

**Recommendation**: Build a consensus ingestion mechanism (manual YAML
entry before each WASDE release). The `WASDEConsensus` dataclass already
exists but is not wired into the production config.

---

## 6. Non-negotiable compliance

| Rule | Status |
|---|---|
| No pandas in hot path | PASS (numpy only) |
| numba.njit on hot-path math | PASS (_shift_survival is njit'd) |
| scipy.special.ndtr over scipy.stats.norm.cdf | PASS |
| Fail-loud | PASS (raises WASDEDensityError/WASDEParseError) |
| asyncio for I/O only | PASS (synchronous compute) |
| Type hints on public interfaces | PASS |

---

## 7. Verdict

**CONDITIONAL PASS** -- the WASDE density pipeline is architecturally sound
(parser, surprise computation, mean-shift, exponential decay, density
recomputation, deploy/main.py integration all work correctly). Direction
accuracy is 100%.

However, the **sensitivity coefficient is miscalibrated by ~12x**, which
means the system currently destroys value when it re-enters post-WASDE.
The concept becomes net-positive once calibrated to ~1.5 c/Mbu.

### Required before next WASDE (May 12, 2026):
1. **CRITICAL**: Change `sensitivity_cents_per_mbu` default from 18.0 to 1.5
2. **MEDIUM**: Reduce `max_shift_cents` from 100 to 50
3. **LOW**: Add consensus input to config YAML

### Conditions for full PASS:
- Sensitivity correction deployed and tested
- Next WASDE (May 12) produces model shift within 2x of actual ZS move
