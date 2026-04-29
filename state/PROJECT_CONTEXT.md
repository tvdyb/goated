# PROJECT_CONTEXT -- `goated`

**Last updated.** 2026-04-28 (Phase 80 COMPLETE; live deployment wired)
**Updated by.** Phase 80 implementation

---

## Operative plan

**Plan file.** `audit/audit_F4_refactor_plan_asymmetric_mm.md`
**Framing.** Asymmetric market-making on Kalshi commodity monthlies, RND-driven.
**Supersedes.** F1 (`audit/audit_F_refactor_plan.md`),
F2 (`audit/audit_F2_refactor_plan_mm_program.md`),
F3 (`audit/audit_F3_refactor_plan_lip.md`).

---

## Active wave

**Wave.** F4 Wave 1 (PLANNING COMPLETE -- ready for execution)
**Wave status file.** `state/wave_1_status.md`
**Wave goal (one line).** Deliver RND pipeline (CME options -> BL -> SVI -> Figlewski -> bucket integration) and validate RND accuracy against settled Kalshi monthly outcomes (M0 gate on KC-F4-01).

**Actions in wave.**

| Action | Summary | Effort | Track | Status |
|---|---|---|---|---|
| F4-ACT-01 | Monthlies adaptations (roll rule fix, KXSOYBEANMON config) | S | T1 | complete |
| F4-ACT-02 | CME options chain ingest (ZS EOD chain + put-call parity prune) | L | T2 | verified (Phase 45) |
| F4-ACT-03 | RND extractor pipeline (IV surface + BL + SVI + Figlewski + bucket) | XL | T1 | complete (Phase 50) |
| F4-ACT-15 | M0 spike notebook (GO/NO-GO on KC-F4-01) | M | T1 | complete — INCONCLUSIVE (synthetic chain) |

**Critical path.** F4-ACT-01 -> F4-ACT-02 -> F4-ACT-03 -> F4-ACT-15
**Estimated wall-clock.** ~3-5 weeks with 2 parallel tracks.
**Wave-end gate.** M0 verdict: GO (proceed to Wave 2) / NO-GO (halt) / INCONCLUSIVE (proceed with re-eval gate at F4-ACT-09).

---

## In flight

Actions currently being implemented:

| Action | Status | Implementer | Resumption pointer |
|---|---|---|---|
| (none currently in-flight) | | | |

---

## Verified complete

| Action | Wave | Verified date |
|---|---|---|
| ACT-01 (capture Ph1a) | 0 | 2026-04-27 |
| ACT-02 (soy yaml) | 0 | 2026-04-27 |
| ACT-03 (Kalshi client) | 0 | 2026-04-27 |
| ACT-04 (ticker + bucket) | 0 | 2026-04-27 |
| ACT-05 (WS multiplex) | 0 | 2026-04-27 |
| ACT-06 (order builder) | 0 | 2026-04-27 |
| ACT-07 (24/7 calendar) | 0 | 2026-04-27 |
| ACT-08 (settle resolver) | 0 | 2026-04-27 |
| ACT-09 (positions) | 0 | 2026-04-27 |
| ACT-10 (fees) | 0 | 2026-04-27 |
| ACT-11 (kill primitives) | 0 | 2026-04-27 |
| ACT-12 (risk gates) | 0 | 2026-04-27 |
| ACT-13 (corridor adapter) | 0 | 2026-04-27 |
| ACT-LIP-POOL (pool ingest) | 0 | 2026-04-27 |
| ACT-LIP-SCORE (score tracker) | 0 | 2026-04-27 |
| ACT-LIP-VIAB (viability) | 0 | 2026-04-27 |
| F4-ACT-01 (monthlies adapt) | F4 W1 | 2026-04-28 |
| F4-ACT-02 (CME ingest) | F4 W1 | 2026-04-27 |
| F4-ACT-03 (RND pipeline) | F4 W1 | 2026-04-28 |
| F4-ACT-15 (M0 spike) | F4 W1 | 2026-04-28 |
| F4-ACT-05 (IBKR hedge) | F4 W2 | 2026-04-28 |

---

## Ready (deps met, not started)

| Action | Wave | Effort | Notes |
|---|---|---|---|
| F4-ACT-06 (USDA events) | F4 W2 | M | Wave 0 deps met. Can start immediately. |
| F4-ACT-07 (order pipeline) | F4 W2 | M | Wave 0 deps met. Can start immediately. |
| ~~F4-ACT-05 (IBKR hedge)~~ | F4 W2 | L | **COMPLETE** (Phase 70). |

---

## Blocked

| Action | Blocking factor | ETA |
|---|---|---|
| F4-ACT-04 (asym quoter) | F4-ACT-06 + F4-ACT-07 | mid Wave 2 |
| F4-ACT-08 (kill switch) | F4-ACT-04 + F4-ACT-05 + F4-ACT-07 | late Wave 2 |
| F4-ACT-16 (taker-imbal) | F4-ACT-04 + F4-ACT-07 | late Wave 2 |

---

## Completed phases

- Wave -1 (audit): complete; digests in `audit/audit_*.md`.
- Wave 0: all 16 actions verified-complete; gate: NO-GO (KXSOYBEANW not LIP-eligible).
- Phase 00 complete: `CLAUDE.md` created.
- Phase 05 complete: F4 plan formalized (`audit/audit_F4_refactor_plan_asymmetric_mm.md`).
- Phase 10 complete: M0 spike notebook (`research/m0_spike_soy_monthly.ipynb`). Verdict: INCONCLUSIVE (synthetic chain).
- Phase 15 complete: M0 spike review. Verdict: FAIL (3 technical bugs; methodology validated; not an edge rejection).
- Phase 20 complete: Wave 0 F4 re-verification. Verdict: ADAPTATIONS-NEEDED (2 findings scoped to F4-ACT-01).
- Phase 25 complete: Wave 0 integrity audit. Verdict: PASS (all 24 gaps verified closed, 637 tests pass).
- Phase 30 complete: Wave 1 planned. 4 actions, 2 tracks, ~3-5 weeks estimated.
- Phase 40 complete: F4-ACT-02 (CME ingest) implemented. 37 tests, GAP-046+047+063 closed, OD-37 resolved.
- Phase 45 complete: CME ingest review. Verdict: PASS (conditional on F-01 Christmas expiry fix).
- Phase 50 complete: F4-ACT-03 (RND pipeline) implemented. 39 tests, GAP-006+036+037+038+041+042+043+044+045 closed. 713 total tests pass.
- F4-ACT-01 complete: Roll rule -> FND-15 BD (configurable). KXSOYBEANMON added to commodities.yaml. 722 total tests pass.
- F4-ACT-15 complete: M0 spike v2 notebook. Verdict: INCONCLUSIVE (synthetic chain — methodology validated). Wave 2 proceeds with re-eval gate at F4-ACT-09.
- **F4 Wave 1: COMPLETE** (4/4 actions). M0 gate: INCONCLUSIVE -> proceed to Wave 2.
- Phase 55 complete: RND pipeline review. Verdict: PASS. Real CME ZSN26 data validated pipeline. **Key finding: edge is spread capture (6-8c incumbent spreads), NOT model-vs-mid disagreement.** See `state/digest_phase_55_cme_comparison.md`.
- Phase 70 complete: IBKR hedge leg implemented. `hedge/` package: IBKRClient, delta aggregator, sizer, trigger. 45 tests, 818 total. See `state/digest_phase_70_ibkr_hedge.md`.
- **Phase 80 complete:** Live deployment wired. `deploy/main.py` orchestrates full loop: CME -> RND -> quoter -> Kalshi orders -> positions -> risk -> hedge -> kill switch. `attribution/pnl.py` for PnL tracking. `deploy/README.md` operational runbook. 30 integration tests, 848 total. See `state/digest_phase_80_live_deploy.md`.

---

## Critical context for Phase 60+

**READ `state/digest_phase_55_cme_comparison.md` BEFORE starting Phase 60.**

Kalshi soybean monthlies are 1-3 day contracts. Model agrees with Kalshi mid within 1-2c. The edge is tightening the 6-8c incumbent spread, not directional alpha. The quoter should post symmetric tight spreads around fair value and withdraw on adverse flow.

---

## Decisions

**Resolved.** See `state/decisions_log.md` for full entries.
- OD-01 (scope): research is the spec
- OD-04 (density refresh): sync inline
- OD-06/OD-20 (CME ingest source): Pyth L1 + low-cost vendor (NOT Databento)
- OD-11 (FCM): Interactive Brokers
- OD-18 (capture): tiered REST + WS
- OD-31 (cadence): low-frequency periodic-quoting
- OD-32'/OD-33'/OD-34'/OD-36: invalidated by F4 pivot

**Pending (Wave 1).**
- OD-37 (CME options chain vendor): RESOLVED — CME Group public delayed settlement data (free).
- OD-40 (M0 historical data depth): 4 settled monthly Events minimum. Resolve at F4-ACT-15.

**Pending (Wave 2+).**
- OD-38 (asymmetric quoter edge threshold): 2c default. Resolve at F4-ACT-04.
- OD-39 (taker-imbalance cooldown): 30s default. Resolve at F4-ACT-16.
- OD-13, OD-14, OD-15, OD-16, OD-25, OD-26, OD-27, OD-28, OD-35: working defaults; design-review at relevant action.

---

## Non-negotiables in force

- No pandas in hot path; no Python loops over markets/strikes.
- No Monte Carlo in hot path; offline-validation only.
- No silent failures: stale Pyth, out-of-bounds IV, dropouts -> raise.
- `scipy.special.ndtr` over `scipy.stats.norm.cdf`.
- `numba.njit` on all hot-path math.
- Synchronous main loop; `asyncio` for I/O only.
- Theo for commodity monthlies is bucket Yes-price via corridor decomposition under half-line structure.
- Every order `post_only=True`.

---

## External dependencies

- IB account with CME futures permission (~1-2 weeks lead time; application in progress).
- CME options chain data source (OD-37 pending; IB API default).
- Forward-capture tape (ACT-01 Phase 1a should be deployed and running on KXSOYBEANMON after F4-ACT-01).

---

## Resumption pointer

If you are picking up this project mid-flight, your starting move is:

1. Read `prompts/build/PREMISE.md` and `state/digest_phase_55_cme_comparison.md`.
2. Read `audit/audit_F4_refactor_plan_asymmetric_mm.md`.
3. **Phase 80 is COMPLETE** (live deployment wired). See `state/digest_phase_80_live_deploy.md`.
4. **Critical insight:** The edge is spread capture on wide (6-8c) Kalshi markets, NOT model-vs-mid directional disagreement.
5. Next step: **Paper-trade for 1 week** on KXSOYBEANMON before deploying real capital. See `state/action_live_deploy/handoff.md` for pre-flight checklist.
