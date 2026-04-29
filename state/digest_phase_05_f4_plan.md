# Digest — Phase 05: F4 plan formalized

**Date.** 2026-04-27
**Author.** orchestrator (Phase 05 execution)

---

## Summary

Phase 05 formalized the F4 refactor plan at
`audit/audit_F4_refactor_plan_asymmetric_mm.md`.

- **16 actions** organized into **3 waves**.
- **~50 F1 gaps closed** (out of 185 in the gap register).
- **5 kill criteria** from PREMISE.md + 5 audit-derived criteria
  carried forward.
- **4 new outstanding decisions** introduced (OD-37 through OD-40).
- **4 LIP-specific decisions invalidated** (OD-32', OD-33', OD-34',
  OD-36).

---

## Wave structure

| Wave | Goal | Actions | Critical-path effort |
|---|---|---|---|
| F4 Wave 1 | Foundation: M0 spike + monthlies adaptations + CME ingest + RND pipeline | 4 (F4-ACT-01, 02, 03, 15) | ~4 weeks (dominated by F4-ACT-03 XL) |
| F4 Wave 2 | Core trading: asymmetric quoter + IBKR hedge + USDA events + order pipeline + kill switch + taker-imbalance | 6 (F4-ACT-04, 05, 06, 07, 08, 16) | ~4 weeks |
| F4 Wave 3 | Validation: M0 backtest + scenarios + settlement + reconciliation + PnL attribution | 6 (F4-ACT-09, 10, 11, 12, 13, 14) | ~4 weeks (dominated by F4-ACT-09 XL) |

---

## Key structural decisions

1. **F4 is spread-capture, not LIP pool-share.** The primary income
   stream is asymmetric spread capture based on RND edge vs Kalshi
   midpoint. LIP infrastructure retained for optionality only.

2. **M0 gate at end of Wave 1.** F4-ACT-15 (M0 spike notebook) is a
   hard GO/NO-GO on KC-F4-01 before Wave 2 engineering begins.

3. **No A-S/CJ HJB control loop.** The quoter (F4-ACT-04) uses a
   simplified reservation-price + asymmetric edge posting, not the
   full optimal-control framework. Appropriate for ~2-3
   trades/bucket/day.

4. **CME ingest via IB API, not Databento.** EOD options chain
   sufficient for RND extraction. No MBP/MBO depth reconstruction
   needed.

5. **Taker-imbalance detector is new (F4-ACT-16).** Not in any prior
   plan. Implements the "withdraw the side facing adverse taker flow"
   defense from PREMISE.md.

6. **Settlement-gap risk gate is new (F4-ACT-11).** Engineered
   mitigation for the binding constraint (USDA gap risk).

---

## What carries forward from Wave 0

All 16 Wave 0 actions carry forward. Only ACT-08 (settle resolver)
needs a code fix (roll rule: FND-15 BD, not FND-2 BD). All other
actions are product-family-agnostic and work unchanged for monthlies.

---

## State file updates

- `state/PROJECT_CONTEXT.md`: operative plan updated to F4; resumption
  pointer updated; Phase 05 noted as complete.
- `state/decisions_log.md`: OD-32'/33'/34'/36 invalidated; OD-06/20
  updated with F4 CME ingest source.
- Operative plan: `audit/audit_F4_refactor_plan_asymmetric_mm.md`.
