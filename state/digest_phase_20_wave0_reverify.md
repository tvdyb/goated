# Digest -- Phase 20: Verify Wave 0 Integrity Under F4

**Date.** 2026-04-27
**Phase.** 20
**Verdict.** ADAPTATIONS-NEEDED (2 findings, both already scoped into F4-ACT-01)

---

## Summary

Phase 20 re-verified all 16 Wave 0 actions under the F4 strategic frame
(asymmetric MM on commodity monthlies). Result: Wave 0 code is intact and
high-quality, but two configuration/logic items need remediation before
F4 Wave 1 proceeds.

## Test results

- **637 passed, 0 failed** (pytest tests/, 24.37s). Matches wave_0_gate.md claim exactly.

## Verify.md audit

All 16 verify.md files exist, all show PASS, all dated 2026-04-27.
Consistent with dependency_graph.md.

## Findings

1. **FND-01 (WARN):** `engine/cbot_settle.py:165-172` uses FND - 2 BD
   roll rule. Kalshi's actual rule is FND - 15 BD. Must fix in F4-ACT-01.

2. **FND-02 (WARN):** `config/commodities.yaml:72-77` has only
   `KXSOYBEANW`. Must add `KXSOYBEANMON` entry in F4-ACT-01.

3. **FND-03 (INFO):** All other 14 Wave 0 actions are natively
   F4-compatible with zero code changes. Production code was designed
   series-agnostic.

## Key confirmation

The F4 plan's "What carries forward" table (section 3 of
`audit/audit_F4_refactor_plan_asymmetric_mm.md`) is accurate. No
discrepancies found between the plan's claims and the actual code state.

## Output

- `state/wave_0_f4_reverify.md` -- full re-verification report

## Next

F4-ACT-01 (Wave 0 adaptations for monthlies, effort S) can proceed
immediately. All Wave 0 deps are met.
