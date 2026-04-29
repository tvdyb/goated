# Digest: Phase 30 -- F4 Wave 1 Plan

**Date.** 2026-04-27
**Phase.** 30 (Plan F4 Wave 1)
**Outputs.** `state/wave_1_status.md`, updated `state/PROJECT_CONTEXT.md`

---

## Summary

Phase 30 produced the execution plan for F4 Wave 1. Four actions across 2 parallel tracks, estimated ~3-5 weeks wall-clock.

## Prerequisite status

| Prerequisite | Required | Actual | OK? |
|---|---|---|---|
| Phase 05 (F4 plan) | exists | `audit/audit_F4_refactor_plan_asymmetric_mm.md` exists | YES |
| Phase 25 (Wave 0 review) | PASS | PASS (637 tests, 24/24 gaps verified) | YES |
| Phase 15 (M0 spike review) | PASS or INCONCLUSIVE (not REJECTED) | FAIL (technical bugs, NOT edge rejection) | CONDITIONAL |

**Phase 15 disposition:** The FAIL verdict is due to 3 notebook execution bugs (np.trapz numpy 2.x, API field name mismatches), not an edge-hypothesis rejection. The mathematical methodology (BL, SVI, Durrleman) was independently validated as correct. The edge hypothesis was never tested with real data -- it defaulted to synthetic noise. F4-ACT-15 supersedes the old notebook and will use the production RND pipeline with real CME data. Proceeding is justified because:
1. KC-F4-01 was not triggered (no REJECTED verdict).
2. The methodology is sound (6 INFO-level confirmations in Phase 15).
3. F4 Wave 1's purpose is precisely to get the real data and pipeline needed for a definitive M0 test.

## Wave 1 actions

| Action | Summary | Effort | Track |
|---|---|---|---|
| F4-ACT-01 | Monthlies adaptations: roll rule FND-15 BD, KXSOYBEANMON config, ticker verification | S | T1 |
| F4-ACT-02 | CME options chain ingest: ZS EOD chain, put-call parity prune, chain-to-IV | L | T2 |
| F4-ACT-03 | RND pipeline: IV surface + BL + SVI + Figlewski + bucket integration + TheoOutput | XL | T1 |
| F4-ACT-15 | M0 spike notebook: RND accuracy vs settled outcomes, GO/NO-GO on KC-F4-01 | M | T1 |

## Critical path

```
F4-ACT-01 (S, ~1d) -> [parallel: F4-ACT-02 (L) | F4-ACT-03 sub-1 (IV refactor)]
                    -> F4-ACT-03 sub-2-5 (BL+SVI+Figlewski+bucket, ~2w)
                    -> F4-ACT-15 (M, ~3d)
                    -> M0 GATE
```

## Key decisions for Wave 1

- **OD-37 (CME vendor):** IB API historical options (default). Resolve at F4-ACT-02 start.
- **OD-40 (M0 data depth):** 4 settled monthly Events. If <4 exist, INCONCLUSIVE verdict with re-eval at F4-ACT-09.
- **DG-01 (chain sanity):** After F4-ACT-02, verify chain data quality before BL integration.

## Risks

1. CME data source unavailable -> IB API free default, CME DataMine free delayed fallback.
2. M0 INCONCLUSIVE due to insufficient settled monthly data -> proceed to Wave 2 with re-eval gate.
3. F4-ACT-03 XL effort underestimated -> sub-stage decomposition allows incremental delivery.

## Next step

Execute F4-ACT-01 (monthlies adaptations, effort S). All dependencies met. Start immediately.

---

## Handoff

Phase 30 complete: Wave 1 planned. `state/wave_1_status.md` written. `state/PROJECT_CONTEXT.md` updated. Ready for execution.
