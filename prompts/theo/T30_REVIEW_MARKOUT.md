# Phase T-30 — Review: Markout Analysis

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-25 complete. Bot has been running with markout tracking for at least 2 settled Events.

## Task
1. Pull markout data from at least 2 settled Events.
2. Per bucket: compute average markout at 1m, 5m, 30m.
3. Identify toxic buckets (where are we consistently adversely selected?).
4. Compare markout near ATM vs wings — is ATM more toxic?
5. Compare markout by time of day — is overnight more toxic than daytime?
6. Compute: total adverse selection cost vs total LIP revenue. Are we net positive?
7. Recommend: which strikes should we widen? Which are safe to tighten?

## Output
- `state/review_theo_t30.md` — markout analysis with per-bucket recommendations.
