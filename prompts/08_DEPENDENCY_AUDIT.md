# 08 — DEPENDENCY AUDIT prompt

Periodically reconciles `state/dependency_graph.md` against the
operative plan's stated DAG (F3 §8 inherits F1 §8). Catches drift
where the runtime state file has diverged from reality.

## When to use
- End of each wave, mandatory.
- When `01_WAVE_PLANNER.md` hits an inconsistency.
- When `05_PARALLEL_MERGE.md` discovers an action that "shouldn't"
  have started yet.
- On a weekly heartbeat during long-running waves.

## Inputs
- The operative plan file (dependency-graph section).
- `state/dependency_graph.md` (current runtime state).
- Each `state/action_<XX>/handoff.md` (claims of completion).
- Each `state/action_<XX>/verify.md` (verifier verdicts).
- `state/decisions_log.md` (any OD that changed dependencies).

## Outputs
- `state/dependency_audit_<date>.md` (audit report, append-only).
- Possibly an updated `state/dependency_graph.md` if drift is fixable
  in-place.
- For un-fixable drift: a recommendation back to the orchestrator.

## Tool access
- Read, Grep, Bash (for `git log` etc.).
- Write to `state/`.
- **No** code edits.

---

## Prompt text

```
You are auditing the runtime dependency graph against the operative
plan.

Step 1 — Build the canonical DAG from the operative plan.

Read the operative plan file's dependency-graph section. Extract a
list of edges (A → B) for every action. This is the canonical DAG.

Step 2 — Build the runtime DAG from state.

For each ACT-<XX> mentioned in the plan or in state/, look up:
  - state/dependency_graph.md (claimed status).
  - state/action_<XX>/handoff.md (existence + status).
  - state/action_<XX>/verify.md (latest verdict).

Compute each action's actual status:
  - 'unstarted' (no handoff.md exists)
  - 'mid-flight' (handoff exists, status: mid-flight)
  - 'complete-pending-verify' (handoff complete, no verify or latest
    verify is older than the latest commit on touched files)
  - 'verified-complete' (latest verify is PASS and no subsequent
    code changes invalidate it)
  - 'verify-failed' (latest verify is FAIL; remediation pending)
  - 'blocked' (decision pending or external dep)

Step 3 — Detect drift.

For each action, compare canonical-dependency-met against runtime
status:
  a. **Status drift.** state/dependency_graph.md claims
     'verified-complete' but verify.md is FAIL or absent.
  b. **Dependency violation.** Action B is mid-flight or complete
     but a canonical predecessor A is not verified-complete.
  c. **Orphaned actions.** Actions exist in state/ that are not in
     the operative plan (suggests scope creep).
  d. **Missing actions.** Operative plan lists an action that has no
     state at all in the project — and the wave is supposedly active.
  e. **Stale verify.** verify.md exists but predates a code change to
     a file the action touched (need re-verify).

Step 4 — Write state/dependency_audit_<date>.md.

  # Dependency audit — <date>

  **Operative plan.** <file path>

  **Audit scope.** <list of waves audited>

  **Canonical DAG edges.** <count>

  **Runtime statuses.**
  | ACT | Canonical deps met? | Runtime status | Drift? |
  |---|---|---|---|

  **Drift findings.**
  - Drift type A (status drift): <list>
  - Drift type B (dependency violation): <list>
  - Drift type C (orphaned): <list>
  - Drift type D (missing): <list>
  - Drift type E (stale verify): <list>

  **Auto-corrected drift.**
  | Type | Action | Fix applied | Notes |
  |---|---|---|---|

  **Drift requiring escalation.**
  | Type | Action | Recommendation | Severity |
  |---|---|---|---|

Step 5 — Auto-correct what's safe.

Safe corrections:
  - Demote 'verified-complete' → 'complete-pending-verify' when
    verify.md is FAIL or absent.
  - Mark 'complete-pending-verify' → 'verified-complete' when latest
    verify is PASS and no code changes have invalidated it.
  - Flag stale verifies for re-run (do not re-run yourself).

Unsafe corrections (escalate):
  - Dependency violations (action ran before its prereq was
    verified). Probably indicates an orchestrator mistake; needs
    human or wave-planner review.
  - Orphaned actions in state/ that aren't in the plan. Could be
    a hand-rolled experiment that needs to be folded into the plan
    or discarded.
  - Missing actions in an active wave. Could indicate the wave plan
    was never invoked.

Step 6 — Update state/dependency_graph.md only with auto-corrections.
For escalations, leave the graph alone and flag in the audit report.

DO NOT edit code. DO NOT modify the operative plan. DO NOT spawn
implementing or verifying agents.

When done, return the audit report path and one of: 'CLEAN' (no
drift), 'AUTO-CORRECTED' (drift fixed in place, no human attention
needed), 'ESCALATE' (drift requires human or wave-planner attention).
```

---

## Notes

- The audit is a *check*, not an *action*. It identifies drift but
  does not fix problems beyond updating the runtime status file.
- Run frequency: end of every wave is mandatory; weekly heartbeat is
  cheap insurance during long-running waves.
- Status types should be treated as a state machine. The audit
  enforces legal transitions:
  ```
  unstarted → mid-flight → complete-pending-verify → verified-complete
                                  ↓                       ↑
                              verify-failed → mid-flight ─┘
  ```
- The most common drift in practice is "stale verify" — a verifier
  passed three weeks ago, but later actions touched the same files,
  and nobody re-verified. The audit catches this.
