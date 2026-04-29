# Handoff -- ACT-LIP-SCORE (LIP Score Tracker)

**Action.** ACT-LIP-SCORE
**Status.** complete-pending-verify
**Wave.** 0
**Implementer.** Claude Opus 4.6
**Date.** 2026-04-27

---

## What was done

1. **Plan** written at `state/action_lip_score/plan.md`.

2. **Implementation** at `feeds/kalshi/lip_score.py`:
   - `distance_multiplier()` -- linear decay over configurable ticks (default 5, OD-34' working default), numba `@njit` accelerated.
   - `_compute_score_array()` -- numba-jitted inner loop computing `SUM(size * mult)` over price/size arrays.
   - `OrderbookSide` / `MarketOrderbook` -- maintained orderbook state with incremental delta application, best-price derivation, numpy export.
   - `LIPScoreTracker` -- per-market tracker: computes our score, total visible score, projected share; maintains 1h and 1d rolling windows; emits `ScoreSnapshot` telemetry via callbacks.
   - `RollingScoreWindow` -- deque-backed rolling stats with numpy mean/std, automatic eviction.
   - `ScoreSnapshot` dataclass -- structured telemetry for ACT-LIP-PNL attribution layer.
   - Target Size threshold check (`below_target_size()`).

3. **Tests** at `tests/test_lip_score.py`: 59 tests, all passing.
   - Distance multiplier: at-best, off-best, boundary, beyond, symmetry, invalid decay.
   - Score computation: single order, multiple orders, all-outside-decay, empty.
   - OrderbookSide: levels, deltas, clearing, array export.
   - MarketOrderbook: best bid/ask derivation, fail-loud on empty.
   - LIPScoreTracker: our score, total score, projected share, both sides, zero-total.
   - Target Size: below, at, above, snapshot flags.
   - Rolling window: empty, single, multiple, eviction, zero-total exclusion, std.
   - Projected reward: from rolling window, empty.
   - Telemetry callbacks: single and multiple.
   - Edge cases: empty orderbook, no competitors (full share), orders outside decay, missing orderbook raises.

4. **Dependency graph** updated: ACT-LIP-SCORE -> complete-pending-verify.

---

## Non-negotiables compliance

- No pandas: numpy + numba only.
- Type hints: all public interfaces typed.
- Fail-loud: `MarketOrderbookError` raised on missing data, `ValueError` on invalid config.
- numba `@njit(cache=True)` on hot-path score array computation.
- No silent failures.

---

## Downstream impact

- ACT-LIP-PNL (Wave 1) depends on ACT-LIP-SCORE for `ScoreSnapshot` telemetry.
- ACT-LIP-COMPETITOR (Wave 2) depends on ACT-LIP-SCORE.
- ACT-LIP-RECON (Wave 4) depends on ACT-LIP-SCORE.
- ACT-LIP-VIAB does NOT depend on ACT-LIP-SCORE (confirmed from dep graph).

---

## Verify checklist

- [ ] `pytest tests/test_lip_score.py -v` -- 59 pass
- [ ] Module imports cleanly: `python -c "from feeds.kalshi.lip_score import LIPScoreTracker"`
- [ ] No pandas imports anywhere in module
- [ ] numba jit compiles without error on first call
- [ ] Type hints present on all public functions/classes
