# 05 — PARALLEL MERGE prompt

When two or more parallel-track agents finish independent actions
that share an integration point (a module, a config file, a test
suite), this prompt **integrates their work** and verifies coherence.

## When to use
- After a sync point in `state/wave_<N>_status.md` where multiple
  tracks must converge.
- When two agents both edited the same file (rare, but happens).
- Before running `09_WAVE_GATE.md` if the wave had any parallel
  tracks.

## Inputs
- `state/wave_<N>_status.md` for sync-point definition.
- `state/action_<XX>/handoff.md` for each action being merged.
- `state/action_<XX>/verify.md` for each (must be PASS).
- The current code in the workspace folder.

## Outputs
- `state/merge_<N>_<sync_point_name>.md` — merge report.
- Possibly small integration code or test edits to reconcile.
- Updated `state/dependency_graph.md`.

---

## Prompt text

```
You are merging the outputs of <N> parallel tracks at sync point
'<sync_point_name>' in Wave <W>.

ACTIONS BEING MERGED: ACT-<XX>, ACT-<YY>, ACT-<ZZ>, ...

Step 1 — Confirm preconditions.
  - Each action's verify.md is PASS. If any is FAIL, stop and report.
  - Each action's handoff.md is complete.
  - state/dependency_graph.md shows each as 'verified-complete'.

Step 2 — Identify integration points.

For each pair of merged actions, check overlap:
  - Did they edit the same file? (git diff --name-only on each
    action's commit range, intersect.)
  - Did they touch the same module's public surface?
  - Did one emit an interface contract the other claimed to honour?
  - Did one add a test that exercises the other's code?

List integration points in the merge report.

Step 3 — Run integration tests.

  - cd to workspace, run `pytest tests/` (full suite, not just
    per-action tests).
  - Capture pass / fail counts. Any failure that didn't appear in
    individual verify reports is a merge regression.
  - For each merge regression, identify which action's change
    introduced the conflict. Often it's neither — it's the
    interaction.

Step 4 — Reconcile if needed.

If integration tests fail purely because of merge interaction
(not from a defect in either action's individual scope), make the
SMALLEST possible reconciling edit. Document it in the merge
report. If the reconciliation requires real new logic (not just
a wiring fix), STOP and treat it as a missed action — escalate
to the orchestrator and propose a small follow-up ACT-<MERGE-XX>.

Step 5 — Write state/merge_<W>_<sync_point_name>.md.

  # Merge report — Wave <W> sync point '<name>' — <date>

  **Actions merged.** ACT-<XX>, ACT-<YY>, ...

  **Preconditions met.** <yes/no with details>

  **Integration points.**
  | Action A | Action B | Overlap | Issue? |
  |---|---|---|---|

  **Integration test results.**
  - Total: <N>
  - Pass: <N>
  - Fail: <N>
  - Regressions vs individual verify reports: <N>

  **Reconciling edits made.**
  | File | Lines | Reason |
  |---|---|---|

  **Outstanding integration issues.**
  - <Issue 1, recommended remediation>

  **Status.** PASS or FAIL.

Step 6 — On PASS, update state/dependency_graph.md to mark the
sync point complete. On FAIL, leave the graph alone and emit a
recommendation for follow-up.

DO NOT add new features. DO NOT extend either action's scope. The
merge prompt is for integration only.

When done, return the path to the merge report and the status.
```

---

## Notes

- Merges are the second-most-likely place for bugs to appear (after
  the implementation itself). Treat the merge integration test as
  load-bearing.
- If the same sync point produces FAIL twice, escalate. Either the
  parallel decomposition was wrong (the actions weren't actually
  independent) or the interface contract was incomplete.
- Reconciling edits should be tiny — a missing import, a wiring
  detail, an updated config key. If the reconciliation is more than
  ~20 lines, it's probably a missing action and should be planned
  rather than smuggled in.
