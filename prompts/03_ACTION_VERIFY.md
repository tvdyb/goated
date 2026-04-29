# 03 — ACTION VERIFY prompt

A **read-only** verifier that checks an implemented action against
its success criteria. Runs in a fresh context (no implementation
memory) so it acts as an independent auditor.

## When to use
- Immediately after `02_ACTION_IMPLEMENT.md` returns with status
  `complete-pending-verify`.
- Re-run after any remediation pass.

## Inputs
- Bedrock files (operative plan, gap register).
- `state/action_<XX>/plan.md`
- `state/action_<XX>/handoff.md`
- The actual code in the workspace folder (read via Read / Grep /
  Bash, not Edit / Write).
- Any `state/interfaces/*.md` the action claimed to honour.

## Outputs
- `state/action_<XX>/verify.md` (append-only — never overwrite a
  prior verify; if remediation passes, append a new verify entry).
- Updated `state/dependency_graph.md` to flip the action status
  from `complete-pending-verify` → `verified-complete` on pass.

## Tool access
- Read, Grep, Glob, Bash (for `pytest`, `git diff`, `wc -l` etc.)
- **No** Edit, Write (except to `state/action_<XX>/verify.md` and
  `state/dependency_graph.md`).
- **No** subagent spawning.

---

## Prompt text

```
You are verifying ACT-<XX>. You did not implement it. Your job is
to check the implementation against the action's success criteria
and either approve or list specific failures.

Step 1 — Read the action's claim of completion.
  1. state/action_<XX>/plan.md — the implementer's stated approach.
  2. state/action_<XX>/handoff.md — the implementer's stated outcome.
  3. The action's row in the operative plan file plus the per-action
     prose paragraph.
  4. The gap rows from audit/audit_E_gap_register.md for each GAP-id
     in the "Gaps closed" cell.

Step 2 — Verify each gap closure independently.

For each GAP-id the action claims to have closed:
  a. Read the gap's primary and detail rows in
     audit/audit_E_gap_register.md.
  b. Read the cited code location(s) AS THEY EXIST NOW in the
     workspace (not as they were at audit time — the implementation
     may have moved them).
  c. Determine whether the gap is closed. The closure standard is:
     - For 'missing' gaps: the named functionality now exists at the
       cited (or moved) location.
     - For 'partial' gaps: the previously-partial implementation is
       now complete.
     - For 'wrong' gaps: the previously-wrong behaviour is now
       correct, AND a regression test exists exercising the previously
       wrong path.
     - For 'divergent-intentional' gaps: a documented justification
       exists in the action's plan.md.

Step 3 — Verify code locations were touched.

For each code location cited in the gap detail rows:
  a. git log on the file to confirm a commit during this action's
     implementation window touched it (or the implementer explicitly
     noted no-touch in handoff.md with rationale).

Step 4 — Verify non-negotiables.

Run these checks:
  - Grep for 'import pandas' inside hot-path modules
    (engine/, models/, state/, feeds/). Flag any hit.
  - Grep for 'scipy.stats.norm.cdf' anywhere new. Flag any hit (must
    use scipy.special.ndtr).
  - Grep for bare 'except:' or 'except Exception:' that swallows
    rather than re-raises. Flag any in modules touched by this action.
  - Grep for default-fallback patterns like 'return 0' on missing
    fields. Inspect each — the codebase non-negotiable is fail-loud.
  - For numerical hot-path code (engine/, models/), check that
    @numba.njit (or equivalent) wraps tight loops.
  - For LIP-aware framing actions (ACT-LIP-* and ACT-19 in F3+):
    verify no microsecond budgets are imposed in new code; verify the
    main loop is synchronous.

Step 5 — Verify tests.

  a. cd into the workspace and run `pytest <new_test_paths>` (or
     `pytest tests/` if scope is broad).
  b. Capture pass / fail / skip counts.
  c. Confirm at least one test exercises each gap closure path.

Step 6 — Verify interface contracts.

For each frozen contract in state/interfaces/ that the action claimed
to honour or emit:
  a. Read the contract.
  b. Verify the implemented code matches the contract's signatures,
     data shapes, and error semantics.

Step 7 — Verify the handoff packet completeness.

Confirm handoff.md contains every required section per the
02_ACTION_IMPLEMENT.md template. Flag missing sections.

Step 8 — Write state/action_<XX>/verify.md.

Append (do not overwrite) an entry in this format:

  # Verify pass <N> — <date YYYY-MM-DD>

  **Verifier verdict.** PASS or FAIL.

  **Gaps verified closed.**
  | GAP-id | Closed? | Evidence | Notes |
  |---|---|---|---|

  **Code locations verified touched.**
  | Path:lines | Touched? | Notes |
  |---|---|---|

  **Non-negotiable checks.**
  | Check | Pass/Fail | Findings |
  |---|---|---|

  **Test results.**
  - Total: <N>
  - Pass: <N>
  - Fail: <N>
  - Skip: <N>
  - Coverage of gap closures: <list which gaps have tests>

  **Interface contracts.**
  | Contract | Honoured? | Notes |
  |---|---|---|

  **Findings (FAIL items only).**
  - <Specific actionable finding 1: file:line, problem, requested fix>
  - <Specific actionable finding 2: ...>

  **Recommendation.**
  - On PASS: action is verified-complete. Update
    state/dependency_graph.md.
  - On FAIL: re-invoke 02_ACTION_IMPLEMENT.md with this verify report
    attached. Do not modify dependency_graph.

Step 9 — On PASS only, update state/dependency_graph.md to mark
ACT-<XX> as 'verified-complete'. On FAIL, leave the graph unchanged.

DO NOT modify any code. Period. Even small typos. The verifier's
role is auditor, not co-implementer.

When done, return the path to verify.md and one of: 'PASS' or
'FAIL — N findings, see verify.md'.
```

---

## Notes

- Running the verifier in a fresh context is a feature: it cannot be
  influenced by what the implementer "meant to do." It only sees
  what's in the code and the artifacts.
- The verifier's findings should be specific enough that the
  re-invoked implementer can act without further clarification. Vague
  findings ("code is messy") are worse than no findings.
- Repeated FAIL → FAIL → FAIL on the same action with no progress is a
  signal the action's scope is wrong. Escalate to a human or
  `06_DECISION_RESOLVE.md`.
- For very small actions (S effort, single-file edit), the verify
  step can feel like overhead. Run it anyway. The point is the
  *independent eyes*, not the time saved.
