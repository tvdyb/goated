# Wave 0 status

**Created.** 2026-04-27
**Last updated.** 2026-04-27
**Operative plan.** `audit/audit_F3_refactor_plan_lip.md` §3 (Wave 0)

---

## Goal

LIP-ready quoting surface — sign, quote two-sided continuously at the inside, capture tape, kill cleanly, attribute pool share. Ends with ACT-LIP-VIAB go/no-go gate before committing Wave 1 engineering.

---

## Action count

16

---

## Critical path

ACT-02 → ACT-03 → ACT-04 → ACT-09 → ACT-12 → (merge with ACT-LIP-POOL) → ACT-LIP-SCORE → (merge with ACT-01 Phase 1a) → ACT-LIP-VIAB (wave gate)

| Action | Effort | Cumulative ew | Notes |
|---|---|---|---|
| ACT-02 (soy yaml) | S | 0.25 | |
| ACT-03 (Kalshi client) | XL | 3.25 | longest single item |
| ACT-04 (ticker + bucket) | M | 3.75 | |
| ACT-09 (positions) | L | 4.75 | |
| ACT-12 (risk gates) | M | 5.25 | |
| ACT-LIP-POOL | M | (parallel, off critical path via ACT-03) | |
| ACT-LIP-SCORE | L | 6.25 | needs ACT-04 + ACT-LIP-POOL |
| ACT-LIP-VIAB | M | 6.75 | needs ACT-01 Ph1a + ACT-LIP-POOL + 2wk data |

**Estimated wave-floor wall-clock.** ~7 engineer-weeks of critical path
with 3 parallel agents. Real wall-clock dominated by the 2-week LIP
pool data accumulation window for ACT-LIP-VIAB — engineering finishes
before data matures.

Effort key: S = 0.25ew, M = 0.5ew, L = 1.0ew, XL = 3.0ew.

---

## Track assignments

| Track | Actions (in order) | Type | Dependencies |
|---|---|---|---|
| T1 (Kalshi core) | ACT-02 → ACT-03 → ACT-04 → ACT-06 → ACT-09 → ACT-12 | serial | Critical path; ACT-03 is the XL bottleneck |
| T2 (Capture + calendar) | ACT-01 (Phase 1a), ACT-07 | parallel within track | Both no-prereq; start day-zero |
| T3 (Post-ACT-03 fan-out) | ACT-05, ACT-11, ACT-LIP-POOL | parallel within track | All three unblock when ACT-03 completes |

**Post-fan-out serial tails (assigned after sync points):**

| Track | Actions (in order) | Type | Dependencies |
|---|---|---|---|
| T1 (continued) | ACT-13 | serial | needs ACT-04 (T1) + ACT-08 |
| T4 (post-ACT-02) | ACT-08, ACT-10 | parallel within track | Both need ACT-02 only; can start as soon as ACT-02 completes |
| T5 (LIP surface) | ACT-LIP-SCORE → ACT-LIP-VIAB | serial | ACT-LIP-SCORE needs ACT-04 (T1) + ACT-LIP-POOL (T3); ACT-LIP-VIAB needs ACT-LIP-SCORE + ACT-01 Phase 1a (T2) + 2 weeks of pool data |

---

## Execution windows (with N=3 parallel agents)

**Window 1 (day-zero).** Start three independent roots simultaneously:
- Agent A: ACT-01 (Phase 1a REST polling capture) — deploy and leave running
- Agent B: ACT-02 (soy yaml) — S effort, completes quickly
- Agent C: ACT-07 (24/7 calendar) — M effort

**Window 2 (post-ACT-02).** Agent B moves to:
- Agent B: ACT-03 (Kalshi REST client) — XL effort, the bottleneck
- Agent A (if ACT-01 Ph1a deployed): ACT-08 (settle resolver, needs ACT-02)
- Agent C (if ACT-07 done): ACT-10 (fees, needs ACT-02)

**Window 3 (post-ACT-03).** Fan-out: three actions unblock simultaneously:
- Agent A: ACT-05 (WS multiplex)
- Agent B: ACT-04 (ticker + bucket) — on critical path
- Agent C: ACT-11 (kill primitives) or ACT-LIP-POOL

**Window 4 (post-ACT-04).** Further fan-out:
- Agent A: ACT-06 (order builder)
- Agent B: ACT-09 (positions) — on critical path
- Agent C: ACT-LIP-POOL (if not started) or ACT-13 (needs ACT-04 + ACT-08)

**Window 5 (convergence).**
- ACT-12 (risk gates, needs ACT-09)
- ACT-13 (corridor adapter, needs ACT-04 + ACT-08)
- ACT-LIP-SCORE (needs ACT-04 + ACT-LIP-POOL)

**Window 6 (wave gate).**
- ACT-LIP-VIAB (needs ACT-01 Phase 1a running + ACT-LIP-POOL + 2 weeks data)

---

## Cross-track sync points

| Sync point | Tracks | Trigger | Merge prompt |
|---|---|---|---|
| post-ACT-03 | T1 → T3 | ACT-03 verified-complete | `prompts/05_PARALLEL_MERGE.md` (light — T3 actions are independent) |
| post-ACT-04 + ACT-LIP-POOL | T1 + T3 → T5 | Both ACT-04 and ACT-LIP-POOL verified-complete | `prompts/05_PARALLEL_MERGE.md` (ACT-LIP-SCORE needs both) |
| pre-ACT-13 | T1 + T4 | ACT-04 (T1) + ACT-08 (T4) both complete | Serial merge — ACT-13 uses outputs of both |
| pre-ACT-LIP-VIAB | T2 + T5 | ACT-01 Phase 1a deployed + ACT-LIP-POOL data matured + ACT-LIP-SCORE complete | Wave gate checkpoint |

---

## External dependencies

- **LIP pool data accumulation:** ACT-LIP-VIAB requires ~2 weeks of captured pool data on `KXSOYBEANW`. ACT-01 Phase 1a and ACT-LIP-POOL must be deployed and running continuously during this period. This is the true wall-clock bottleneck.
- **IB account application:** Not needed for Wave 0 (only ACT-20 in Wave 1). Should be initiated during Wave 0 to avoid blocking Wave 1.

---

## Wave-end gate

Run `prompts/09_WAVE_GATE.md` when:
- All 16 actions in Wave 0 are `verified-complete` per
  `state/dependency_graph.md`.
- `prompts/08_DEPENDENCY_AUDIT.md` returns CLEAN.
- **ACT-LIP-VIAB go/no-go decision is recorded.** This is the
  deliberate tripwire: if projected LIP pool-share revenue is below
  $50/day net of fees for `KXSOYBEANW`, the project pivots before
  sinking engineering into Waves 1+.

---

## Risks and escalations

- **ACT-03 (Kalshi client) is XL and gates half the wave.** If it slips, the entire critical path shifts. Escalation: break ACT-03 into sub-deliverables (signing → rate limiter → REST wrapper → integration tests) and track each independently. Consider two agents pair-programming.
- **LIP pool data may be sparse or volatile.** If `KXSOYBEANW` has no active LIP reward periods during the observation window, ACT-LIP-VIAB cannot produce a meaningful go/no-go. Escalation: extend observation window or pivot to a different `KX*` product family.
- **Kalshi API changes or rate-limit surprises.** REST client (ACT-03) is built against public docs; undocumented behaviour may surface. Escalation: open Kalshi support ticket + adapt.
- **ACT-LIP-VIAB no-go outcome.** Not a failure — it's a designed pivot point. If no-go: evaluate other `KX*` product families (corn, wheat, macro tickers) via the same pipeline, or pivot to the F1 edge-driven framing.

---

## Notes

- ACT-01 Phase 1a should be deployed as early as possible and left running — it needs to accumulate data for both ACT-LIP-VIAB and the eventual M0 backtest (ACT-26 in Wave 1). Every day of delay is a day of lost capture.
- ACT-08 and ACT-10 are off the critical path but should be started as soon as ACT-02 completes — they're quick wins that free future windows.
- IB account application should be submitted during Wave 0 even though ACT-20 is Wave 1 — the 1-2 week approval time should overlap with Wave 0 engineering.
