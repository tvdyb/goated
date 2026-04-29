# 09 — WAVE GATE prompt

End-of-wave verification. Confirms every action in a wave is
verified-complete, runs wave-level integration checks, and produces a
**pass/fail decision** that gates entry into the next wave.

**Wave 0 is special:** the gate also evaluates ACT-LIP-VIAB's
two-week viability output. A no-go from ACT-LIP-VIAB stops the
project before Wave 1 starts.

## When to use
- After all actions in a wave are verified-complete (per
  `08_DEPENDENCY_AUDIT.md`).
- Mandatory before invoking `01_WAVE_PLANNER.md` for the next wave.

## Inputs
- `state/wave_<N>_status.md` (wave plan).
- `state/dependency_graph.md` (post-`08_DEPENDENCY_AUDIT.md`,
  expected: all wave actions verified-complete).
- For Wave 0: `state/action_<LIP-VIAB>/verify.md` and the underlying
  viability data.
- The operative plan's "Updated kill criteria" section for any KC-LIP
  / KC-AUD criteria that apply.

## Outputs
- `state/wave_<N>_gate.md` (append-only): PASS / FAIL with rationale.
- On PASS: `state/wave_<N>_digest.md` (the closure digest).
- On FAIL or NO-GO: an explicit recommendation back to the
  orchestrator (and human stakeholders).

---

## Prompt text

```
You are gating Wave <N> of the goated project. Your job: decide
whether the wave's exit criteria are met and whether the project
should advance to Wave <N+1>.

Step 1 — Confirm the audit is clean.

Run state/dependency_audit_<latest>.md. Confirm:
  - All actions in Wave <N> are 'verified-complete'.
  - No drift escalations are open.
  - No verify-failed actions are pending.

If the audit shows any open drift or failures, the gate is
**FAIL — wave incomplete**. Do not proceed.

Step 2 — Run wave-level integration tests.

  - cd to the workspace and run `pytest tests/` (full suite).
  - Capture pass / fail counts.
  - Also run any wave-specific scenario tests
    (e.g., scenario/wasde_day.py for Wave 1).
  - For Wave 0, additionally exercise ACT-LIP-POOL by polling Kalshi
    for one cycle and confirming pool data is captured.

Step 3 — Wave-specific gates.

**Wave 0:**
  - Confirm ACT-LIP-VIAB has produced an output. Read
    state/action_LIP_VIAB/handoff.md or its verify.md.
  - Read the viability output (typically a notebook or report at
    backtest/viability_report_<date>.md).
  - Apply the kill criteria from the operative plan §7:
    * KC-LIP-01 (pool < $50/day for 4 weeks): if true → NO-GO
    * KC-LIP-02 (our share < 5% projected): if true → NO-GO
    * KC-LIP-03 (distance multiplier too steep): if true → NO-GO
  - Two weeks of pool data is the minimum; if observation period
    is shorter, gate is FAIL — observation incomplete.
  - GO decision requires: at least 2 weeks of pool data, all
    KC-LIP criteria not triggered, projected daily net revenue at
    expected presence > $50/day (operating-cost floor).

**Wave 1:**
  - Confirm M0 backtest pipeline produces a result on at least one
    settled `KXSOYBEANW` Event.
  - Apply C10-KC-01 (M0 fails): if RND-implied probabilities miss
    realized outcomes by more than ~2¢ on >50% of buckets across
    12+ Events (or partial data if 12+ are not yet available, with
    extrapolation noted).
  - Confirm hedge-leg paper trade produces a closed round-trip with
    expected slippage in scenario/expiry_day.py.

**Wave 2:**
  - Confirm Heston SV calibration converges on at least one settled
    week's CME chain.
  - Confirm pre-event widening (ACT-32) fires correctly on a
    simulated USDA window.

**Wave 3:**
  - Confirm multi-product extension (ACT-LIP-MULTI) parametrises
    correctly for at least one non-`KXSOYBEANW` market via config-
    only changes (no code edits).

**Wave 4:**
  - Confirm structured logging is wired and a daily summary email
    can be generated end-to-end.
  - Confirm calibration loop runs inline and updates parameters
    within budget.

Step 4 — Write state/wave_<N>_gate.md.

  # Wave <N> gate — <date>

  **Wave goal.** <copy from wave_<N>_status.md>

  **Decision.** PASS / FAIL / NO-GO

  **Audit clean?** <yes/no>

  **Integration tests.** <pass/fail counts>

  **Wave-specific gate criteria.**
  | Criterion | Result |
  |---|---|

  **Kill criteria evaluated.**
  | KC | Triggered? | Notes |
  |---|---|---|

  **Recommendation.**
  - PASS: advance to Wave <N+1>; invoke 01_WAVE_PLANNER.md.
  - FAIL: remediate listed failures via re-invoking
    02_ACTION_IMPLEMENT.md on relevant actions; re-run gate.
  - NO-GO: stop project; convene human stakeholders; consider
    pivoting (per F-plan §7 reconsideration triggers).

  **Sign-off.** <agent-id; for NO-GO, a human signature is required
  before the project resumes.>

Step 5 — On PASS only, write state/wave_<N>_digest.md (per
04_HANDOFF.md's end-of-phase template).

DO NOT modify code. DO NOT auto-advance to Wave <N+1>; the
orchestrator (or human) reads the gate report and decides.

When done, return the gate report path and the decision.
```

---

## Special handling — Wave 0 NO-GO

If Wave 0's gate returns NO-GO from ACT-LIP-VIAB, the project's
economic premise is broken. The recommended next steps (in order):

1. **Verify the data.** Re-run ACT-LIP-VIAB with another two weeks
   of observation to rule out a sampling fluke.
2. **Consider product-family pivot.** ACT-LIP-MULTI is in Wave 3 by
   default; if `KXSOYBEANW` pools are too small, jump to extending
   the engine to a higher-pool `KX*` family that is LIP-eligible.
3. **Consider strategy pivot.** F1 (edge-driven framing) is still
   on disk; if the LIP economics don't work but RND quality is
   demonstrably better than Kalshi's quotes, the F1 plan re-becomes
   relevant.
4. **Consider exit.** If neither pool size nor edge differential
   support the operation, the project should be paused or wound
   down — a no-go isn't failure, it's the kill criterion working
   as designed.

NO-GO is **valuable information.** It saves months of engineering
that would have produced a working but unprofitable system.

---

## Notes

- The gate is **the ratchet** that protects later waves from
  building on bad foundations. Skipping the gate to advance "just
  this once" is the most common way long projects produce code that
  silently regresses.
- For PASS decisions, the digest is mandatory. It compresses the
  wave's lessons and prevents the next wave's planner from
  re-deriving things.
- For FAIL decisions, the gate explicitly does NOT auto-remediate —
  it lists the failures and routes back to the implementer.
- For NO-GO decisions on Wave 0 specifically, a human must sign off
  before any further engineering is done. The whole point of
  ACT-LIP-VIAB is to produce a kill signal that stops the train.
