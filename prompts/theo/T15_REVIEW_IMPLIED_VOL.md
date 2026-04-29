# Phase T-15 — Review: Kalshi-Implied Vol

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-10 must be complete.

## Task
1. Run the bot and log calibrated vol each cycle for 30+ minutes.
2. Compare calibrated vol vs the hardcoded 15%.
3. Check: does vol change when the market moves?
4. Check: is vol in a reasonable range (10-30% for soybeans)?
5. Check: how does the theo change with calibrated vol vs 15%?
   For each LIP-eligible strike, log: theo_old (15% vol), theo_new (calibrated).
6. Check: does fallback work when ATM strikes are illiquid?
7. Run all tests.

## Verdict
- PASS: Calibrated vol is stable, reasonable, and changes the theo meaningfully.
- FAIL: Vol is unstable, calibration fails frequently, or theo doesn't improve.

## Output
- `state/review_theo_t15.md`
