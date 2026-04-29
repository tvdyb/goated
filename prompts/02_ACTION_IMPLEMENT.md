# 02 — ACTION IMPLEMENT prompt

The workhorse. Use to implement a single action (`ACT-XX`) end-to-end.
Designed to be invoked **per action**, including in parallel for
independent actions.

## When to use
- Whenever an action is "ready" (deps met, not started) and is the
  next thing in flight.
- Re-invoked if `03_ACTION_VERIFY.md` fails (with verifier report
  attached).

## Inputs
- Bedrock files (operative plan, gap register, cartography).
- `state/PROJECT_CONTEXT.md`, `state/dependency_graph.md`.
- The action's row in the operative plan (cited C-ids and code
  locations).
- The matching gap rows in `audit/audit_E_gap_register.md` (use
  GAP-id citations from the action's "Gaps closed" column).
- Any frozen interface contracts in `state/interfaces/` that this
  action's output must conform to.
- Any prior `state/action_<XX>/handoff.md` if resuming.
- Any prior `state/action_<XX>/verify.md` if remediating after a
  failed verify.

## Outputs
- Code: new files / edits per the action scope. Saved to the workspace
  folder (`/Users/felipeleal/Documents/GitHub/goated/`), not the
  outputs directory.
- Tests: matching tests under `tests/`. Required for any action
  producing executable code.
- `state/action_<XX>/plan.md`: the implementation plan written before
  coding (one-shot, may be iterated).
- `state/action_<XX>/handoff.md`: a digest produced at the end (or
  mid-work if context capacity is hit).

## Success criteria (for the verifier)
- Every gap cited in the action is closed (or has a documented partial
  closure with rationale).
- Every code location cited in the action is touched (or noted as
  no-touch with rationale).
- Repository non-negotiables are honoured (no pandas hot path,
  numba-jitted hot path math, fail-loud on bad inputs, no MC in hot
  path, etc.).
- Tests pass locally.
- No interface contract is violated.
- The handoff packet is complete.

---

## Prompt text

```
You are implementing action ACT-<XX> for the goated project.

ACTION ID: ACT-<XX>
WAVE: <N>

Step 1 — Read context, in this order. Stop if any is missing and
flag it:

  1. state/PROJECT_CONTEXT.md (operative plan pointer, active wave).
  2. The operative plan file's row for ACT-<XX> in the Wave <N> table,
     plus the per-action prose paragraph immediately below the table.
  3. The "Gaps closed" cell for ACT-<XX>; for each GAP-id listed,
     read its row in audit/audit_E_gap_register.md §2.1 (primary)
     and §2.2 (detail).
  4. For each code location cited in the gap detail rows, open and
     read the file at the cited line range. If a citation says
     "n/a — no module", read the cartography pointer instead
     (audit/audit_A_cartography.md, typically §9 or §10).
  5. state/interfaces/*.md — any frozen contracts that may apply.
  6. state/decisions_log.md — any resolved decisions affecting this
     action.
  7. README.md — non-negotiables.

Step 2 — Plan. Write state/action_<XX>/plan.md with:

  # ACT-<XX> implementation plan

  ## Scope
  - Gaps closed: <list with GAP-id and one-line summary each>
  - Code locations to touch: <list>
  - New modules to create: <list with paths>
  - Tests to add: <list with paths>

  ## Approach
  <2-5 paragraphs of how you'll build this. Be concrete about
  algorithms, data shapes, and module boundaries.>

  ## Dependencies on frozen interfaces
  <list interface contracts honoured>

  ## Risks
  <list anything that could break>

  ## Done-when
  <bullet criteria for completion>

Step 3 — Implement. Make all edits. Follow the non-negotiables:
  - No pandas in the hot path (numpy + numba only on tight loops).
  - No silent failures: stale data, out-of-bounds inputs, missing
    fields → raise, do not return defaults.
  - No Monte Carlo in the hot path.
  - scipy.special.ndtr over scipy.stats.norm.cdf.
  - numba.njit on hot-path math.
  - For the operative low-frequency framing: synchronous main loop,
    asyncio for I/O only, no microsecond budgets.
  - Theo is P(Pyth_at_T > K) when WTI-shaped; for soybean, theo is
    bucket Yes-price under the Kalshi corridor (per ACT-13).

Step 4 — Test. Run pytest on the new tests. Capture pass/fail.
Do not skip failing tests.

Step 5 — Handoff. Write state/action_<XX>/handoff.md with:

  # ACT-<XX> handoff

  **Status.** <one of: complete, mid-flight context-capacity, blocked-on-X>

  **Files written or edited.**
  | Path | Lines added | Lines removed | Purpose |
  |---|---|---|---|

  **Tests added.**
  | Path | Test count | Pass | Fail |
  |---|---|---|---|

  **Gaps closed (with rationale).**
  - GAP-XXX: <how it was closed and where>
  - ...

  **Frozen interfaces honoured.** <list>

  **New interfaces emitted.** <list with state/interfaces/ pointers>

  **Decisions encountered and resolved.** <list with OD references and
  rationales appended to decisions_log.md>

  **Decisions encountered and deferred.** <list — these need
  06_DECISION_RESOLVE.md before action is verifiable>

  **Open issues for verifier.** <anything you want the verifier to
  scrutinise specifically>

  **Done-when checklist.** <copy from plan.md, mark each item>

  **Resumption notes (if status is mid-flight).** <what's left, where
  you stopped, what trap to avoid>

Step 6 — Update state/dependency_graph.md.
  - Mark ACT-<XX> as 'complete-pending-verify' if all done.
  - Or 'mid-flight' / 'blocked' as applicable.

DO NOT mark as 'verified-complete' yourself — that's the verifier's
job. DO NOT modify any other action's status. DO NOT modify the plan.

CONTEXT CAPACITY DISCIPLINE. Monitor your own progress. If you cross
60% of context capacity before the action is complete, stop
productive work and run prompts/04_HANDOFF.md instead, treating the
in-progress action as the subject. Do not push through to 90% — that
risks dropping work mid-edit.

When done (or handed off), return the path to action_<XX>/handoff.md
and a 3-line summary. The orchestrator will trigger the verifier.
```

---

## Notes

- The implementer is responsible for following non-negotiables. The
  verifier will catch violations but it's faster to honour them
  the first time.
- "60% of context" is a defensive threshold. If your action is small
  (S effort), you'll likely never approach it. If it's L or XL, expect
  to do it in 2–4 fresh-context passes with handoffs between.
- For XL actions like ACT-03 (Kalshi client) or ACT-17 (RND pipeline),
  it's wise to *plan the handoff structure upfront* — split the
  implementation into named sub-pieces and write each in a separate
  invocation.
- For actions citing many GAP-ids (e.g., ACT-19 cites 5 gaps; ACT-21
  cites 5; ACT-23 cites 4), the gap-register read is non-trivial.
  Prioritise reading the primary table for breadth, then read detail
  rows only for the gaps whose remediation isn't obvious.
- If you're remediating after a failed verify, read the verifier's
  `state/action_<XX>/verify.md` first and address each finding
  explicitly in the new plan.md.
