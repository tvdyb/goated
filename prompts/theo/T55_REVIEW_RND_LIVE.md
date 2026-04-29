# Phase T-55 — Review: RND Pipeline Live Performance

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-50 complete. Bot running with RND for at least 2 settled Events.

## Task
1. Compare fills under RND theo vs fills under synthetic theo.
2. Compute markout for RND-era fills. Is adverse selection reduced?
3. Per-bucket: compare RND theo vs synthetic theo vs settlement outcome.
4. Which was more accurate?
5. Compute: net PnL under RND vs estimated PnL under synthetic for same period.
6. Kill criteria check: does RND miss settlement by > 3c on > 50% of buckets? (KC-F4-01)

## Verdict
- PASS: RND reduces adverse selection and/or improves PnL vs synthetic.
- FAIL: RND is worse or no better than synthetic. Investigate calibration.
- KC-F4-01 TRIGGERED: if RND misses by > 3c on > 50% of buckets across 4+ Events, halt.

## Output
- `state/review_theo_t55.md`
