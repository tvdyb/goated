# Phase T-05 — Review: Pyth Forward Price

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-00 must be complete.

## Task
Validate that the Pyth forward price is accurate and reliable.

1. Run the bot for 5 minutes with Pyth forward enabled. Capture logs.
2. Compare Pyth forward vs the Kalshi-inferred forward from previous runs.
3. Check: does the Pyth price update every 5 seconds?
4. Check: is the staleness rejection working?
5. Check: does fallback to Kalshi-inferred work when Pyth is mocked as down?
6. Compare Pyth price to the actual ZS quote on any free source (Barchart page, etc.).
7. Run all tests.

## Verdict criteria
- PASS: Pyth forward updates reliably, matches ZS within 1c, staleness works, fallback works.
- FAIL: Pyth feed is unreliable, prices are stale, or doesn't match ZS.

## Output
- `state/review_theo_t05.md` — verdict + findings.
