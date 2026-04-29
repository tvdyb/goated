# Dependency graph — runtime state

**Last updated.** 2026-04-27 (ACT-LIP-VIAB complete-pending-verify)
**Last audited.** 2026-04-27 by bootstrap (initial seed from F3 §8)

---

## Status legend

- `unstarted` — no `state/action_<XX>/handoff.md` exists.
- `mid-flight` — handoff exists with status `mid-flight`.
- `complete-pending-verify` — handoff complete; verify not yet PASS.
- `verified-complete` — latest verify is PASS, no subsequent code
  changes invalidate it.
- `verify-failed` — latest verify is FAIL; remediation pending.
- `blocked` — decision pending or external dep.

State transitions enforced by `prompts/08_DEPENDENCY_AUDIT.md`:

```
unstarted → mid-flight → complete-pending-verify → verified-complete
                              ↓                       ↑
                          verify-failed → mid-flight ─┘
```

---

## Wave 0 — LIP-ready quoting surface

| Action | Status | Deps (canonical) | Deps met? | Notes |
|---|---|---|---|---|
| ACT-01 (capture) | verified-complete | — | yes | Phase 1a verified 2026-04-27; Phase 1b deferred to post-ACT-03 |
| ACT-02 (soy yaml) | verified-complete | — | yes | verified 2026-04-27 |
| ACT-03 (Kalshi client) | verified-complete | ACT-02 | yes | XL effort; signing + rate limiter + REST client; verified 2026-04-27 |
| ACT-04 (ticker + bucket) | verified-complete | ACT-03 | yes | GAP-074+075+079 closed; 55 tests pass; verified 2026-04-27 |
| ACT-05 (WS multiplex, reduced) | verified-complete | ACT-03 | yes | GAP-131 closed; 41 tests pass; verified 2026-04-27 |
| ACT-06 (order builder) | verified-complete | ACT-04 | yes | GAP-080+081+082+122 closed; 57 tests pass; verified 2026-04-27 |
| ACT-07 (24/7 calendar) | verified-complete | — | yes | verified 2026-04-27; GAP-087+GAP-089 closed |
| ACT-08 (settle resolver) | verified-complete | ACT-02 | yes | GAP-076+077+078 closed; verified 2026-04-27 |
| ACT-09 (positions) | verified-complete | ACT-04 | yes | GAP-083+116+117+119+125 closed; 48 tests pass; verified 2026-04-27 |
| ACT-10 (fees) | verified-complete | ACT-02 | yes | verified 2026-04-27; GAP-007+GAP-152 closed |
| ACT-11 (kill primitives) | verified-complete | ACT-03 | yes | GAP-171 closed; verified 2026-04-27 |
| ACT-12 (risk gates) | verified-complete | ACT-09 | yes | GAP-118+119+120 closed; 36 tests pass; verified 2026-04-27 |
| ACT-13 (corridor adapter) | verified-complete | ACT-04, ACT-08 | yes | GAP-005 closed; 72 tests pass; verified 2026-04-27 |
| ACT-LIP-POOL | verified-complete | ACT-03 | yes | 29 tests pass; config+API dual source; verified 2026-04-27 |
| ACT-LIP-SCORE | verified-complete | ACT-04, ACT-LIP-POOL | yes | 59 tests pass; numba-jitted score computation; verified 2026-04-27 |
| ACT-LIP-VIAB | verified-complete | ACT-01 (Phase 1a), ACT-LIP-POOL | yes | 21 tests pass; verified 2026-04-27; Wave 0 gate code-complete |

---

## F4 Wave 1 — Foundation: M0 spike + Wave 0 adaptations + CME ingest

| Action | Status | Deps (canonical) | Deps met? | Notes |
|---|---|---|---|---|
| F4-ACT-01 (monthlies adapt) | unstarted | ACT-02, ACT-04, ACT-08 | yes | S effort |
| F4-ACT-02 (CME ingest) | complete-pending-verify | ACT-02, F4-ACT-01 | partial (F4-ACT-01 not started) | L effort; 37 tests pass; GAP-046+047+063 closed; OD-37 resolved |
| F4-ACT-03 (RND pipeline) | unstarted | ACT-13, F4-ACT-01, F4-ACT-02 | no | XL effort |
| F4-ACT-15 (M0 spike) | unstarted | ACT-01, F4-ACT-01, F4-ACT-02, F4-ACT-03 | no | M0 GO/NO-GO gate |

---

## F3 Wave 1 — Structural correctness (superseded by F4, kept for reference)

| Action | Status | Deps (canonical) | Deps met? | Notes |
|---|---|---|---|---|
| ACT-14 (IV signature) | unstarted | — | yes | within-Wave-1 root |
| ACT-15 (TheoOutput shape) | unstarted | — | yes | within-Wave-1 root |
| ACT-16 (CME ingest, reduced) | unstarted | ACT-14 | no | |
| ACT-17 (RND pipeline) | unstarted | ACT-13, ACT-14, ACT-16 | no | XL |
| ACT-18 (USDA event clock) | unstarted | ACT-07 | yes | ACT-07 verified-complete 2026-04-27 |
| ACT-19 (quoting, reframed) | unstarted | ACT-09, ACT-15, ACT-17 | no | |
| ACT-20 (hedge leg) | unstarted | ACT-15 | no | needs IB account |
| ACT-21 (settlement) | unstarted | ACT-04, ACT-22 | no | |
| ACT-22 (order pipeline) | unstarted | ACT-06 | yes | ACT-06 verified-complete |
| ACT-23 (reconciliation) | unstarted | ACT-09, ACT-22 | no | |
| ACT-24 (kill switch) | unstarted | ACT-11, ACT-23 | no | |
| ACT-25 (scenarios) | unstarted | ACT-12, ACT-19, ACT-20 | no | |
| ACT-26 (backtest M0) | unstarted | ACT-01, ACT-10, ACT-17 | no | XL |
| ACT-LIP-PNL | unstarted | ACT-23, ACT-LIP-SCORE | no | |

---

## Wave 2 — Quoting refinements

| Action | Status | Deps (canonical) | Deps met? |
|---|---|---|---|
| ACT-27 (Heston SV, reduced) | unstarted | ACT-14, ACT-17, ACT-19 | no |
| ACT-29 (basis tracker, reduced) | unstarted | ACT-17, ACT-20 | no |
| ACT-32 (event widening, reframed) | unstarted | ACT-18, ACT-19 | no |
| ACT-33 (measure overlay) | unstarted | ACT-17 | no |
| ACT-37 (limit-day censorship) | unstarted | ACT-21 | no |
| ACT-35 (wash-trade, reduced) | unstarted | ACT-22 | no |
| ACT-LIP-COMPETITOR | unstarted | ACT-LIP-SCORE, ACT-23 | no |

---

## Wave 3 — Capacity

| Action | Status | Deps (canonical) | Deps met? |
|---|---|---|---|
| ACT-LIP-MULTI | unstarted | ACT-LIP-POOL | yes | ACT-LIP-POOL verified-complete |
| ACT-41 (USDA REST, reduced) | unstarted | ACT-18 | no |
| ACT-32-EXT (stocks-to-use) | unstarted | ACT-32 | no |

---

## Wave 4 — Operational hardening

| Action | Status | Deps (canonical) | Deps met? |
|---|---|---|---|
| ACT-50 (logging + summary, reduced) | unstarted | ACT-24 | no |
| ACT-52 (calibration loop, reduced) | unstarted | ACT-19, ACT-23 | no |
| ACT-53 (backtest realism, reduced) | unstarted | ACT-26 | no |
| ACT-54 (Pyth hardening) | unstarted | — | yes |
| ACT-LIP-RECON | unstarted | ACT-23, ACT-LIP-SCORE | no |

---

## Ready set (deps met, status `unstarted`)

Computed at last audit. Pick from this set to start the next action.

- ACT-14, ACT-15, ACT-18, ACT-54
  (ACT-14/15/18/54 not yet in scope until their wave activates)

Active-wave ready set (Wave 0):
- (none -- all Wave 0 actions are complete-pending-verify or verified-complete)

---

## Audit history

Maintain a short list of when audits ran:

| Date | Auditor | Result | Notes |
|---|---|---|---|
| 2026-04-27 | bootstrap | initial | seed graph from F3 §3 + §8 |
| 2026-04-27 | ACT-03 impl | updated | ACT-03 complete-pending-verify; ACT-04/05/11/LIP-POOL unblocked |
| 2026-04-27 | ACT-03 verify | updated | ACT-03 verified-complete |
| 2026-04-27 | ACT-11 impl | updated | ACT-11 complete-pending-verify; GAP-171 closed |
| 2026-04-27 | ACT-04 impl | updated | ACT-04 complete-pending-verify; ACT-06/09/13 unblocked |
| 2026-04-27 | ACT-11 verify | updated | ACT-11 verified-complete |
| 2026-04-27 | ACT-LIP-POOL impl | updated | ACT-LIP-POOL complete-pending-verify; ACT-LIP-SCORE/VIAB/MULTI unblocked |
| 2026-04-27 | ACT-04 verify | updated | ACT-04 verified-complete |
| 2026-04-27 | ACT-05 impl | updated | ACT-05 complete-pending-verify; GAP-131 closed |
| 2026-04-27 | ACT-LIP-POOL verify | updated | ACT-LIP-POOL verified-complete; ACT-LIP-SCORE/VIAB/MULTI deps confirmed |
| 2026-04-27 | ACT-13 impl | updated | ACT-13 complete-pending-verify; GAP-005 closed; 72 tests pass |
| 2026-04-27 | ACT-05 verify | updated | ACT-05 verified-complete |
| 2026-04-27 | ACT-06 impl | updated | ACT-06 complete-pending-verify; GAP-080+081+082+122 closed; 57 tests pass |
| 2026-04-27 | ACT-09 impl | updated | ACT-09 complete-pending-verify; GAP-083+116+117+119+125 closed; 48 tests; ACT-12 unblocked |
| 2026-04-27 | ACT-13 verify | updated | ACT-13 verified-complete; GAP-005 confirmed closed |
| 2026-04-27 | ACT-09 verify | updated | ACT-09 verified-complete; GAP-083+116+117+119+125 confirmed closed; ACT-12 deps fully met |
| 2026-04-27 | ACT-06 verify | updated | ACT-06 verified-complete; GAP-080+081+082+122 confirmed closed; ACT-22 deps met |
| 2026-04-27 | ACT-12 impl | updated | ACT-12 complete-pending-verify; GAP-118+119+120 closed; 36 tests pass |
| 2026-04-27 | ACT-12 verify | updated | ACT-12 verified-complete; GAP-118+119+120 confirmed closed |
| 2026-04-27 | ACT-LIP-SCORE impl | updated | ACT-LIP-SCORE complete-pending-verify; 59 tests pass; numba-jitted score computation |
| 2026-04-27 | ACT-LIP-VIAB impl | updated | ACT-LIP-VIAB complete-pending-verify; 21 tests pass; Wave 0 gate code-complete |
| 2026-04-27 | ACT-LIP-SCORE verify | updated | ACT-LIP-SCORE verified-complete; 59 tests pass; all criteria PASS |
| 2026-04-27 | ACT-LIP-VIAB verify | updated | ACT-LIP-VIAB verified-complete; 21 tests pass; Wave 0 gate PASS |
| 2026-04-27 | F4-ACT-02 impl | updated | F4-ACT-02 complete-pending-verify; GAP-046+047+063 closed; 37 tests pass; OD-37 resolved (CME public data); F4 Wave 1 section added |

---

## Maintenance notes

- Edit this file on every action's status transition.
- Run `prompts/08_DEPENDENCY_AUDIT.md` at the end of each wave (and
  weekly during long-running waves) to catch drift.
- The graph is sourced from F3 §8 (which inherits F1 §8). When F3 is
  superseded, regenerate the graph from the new operative plan.
