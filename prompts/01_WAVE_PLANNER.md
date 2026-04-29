# 01 — WAVE PLANNER prompt

Use at the **start of each wave** to decompose the wave into parallel
and serial tracks, assign actions to track slots, and produce a
deterministic execution plan.

## When to use
- Beginning of Wave 0, 1, 2, 3, or 4.
- After a wave gate passes and the next wave is about to begin.
- When mid-wave drift has accumulated and re-planning is needed.

## Inputs (all read-only)
- The operative plan file (per `state/PROJECT_CONTEXT.md`)
- `state/dependency_graph.md` (current completion state)
- `state/decisions_log.md` (resolved decisions affecting wave scope)
- The previous wave's `state/wave_<N-1>_digest.md` (lessons learned)

## Outputs
- `state/wave_<N>_status.md` (track assignments, dependency-aware
  execution order, escalation rules)
- Updated `state/PROJECT_CONTEXT.md` with active wave bumped

## Success criteria
- Every action in the wave is assigned to exactly one track.
- Every dependency edge crossing into the wave from earlier waves is
  verified complete in `dependency_graph.md`.
- Every internal-to-wave dependency is honoured (no track has an
  action whose deps live in a later track of the same wave without an
  explicit serialisation note).
- Tracks are sized for 1–N parallel agents (N = max parallelism the
  orchestrator can sustain).
- Wave 0 plan must include the ACT-LIP-VIAB tripwire as the wave gate.

---

## Prompt text

```
You are planning Wave <N> of the goated project. The operative plan
file (per state/PROJECT_CONTEXT.md) lists the actions in this wave.

Your job: produce a deterministic, parallelism-aware execution plan
for the wave. Do not start any implementation. Plan only.

INPUTS to read:
1. The operative plan file's section on Wave <N> (table of actions
   plus per-action prose).
2. The operative plan's dependency graph section (F1 §8 / F3 §8 inherits
   F1 §8). Note edges crossing into Wave <N> from earlier waves.
3. state/dependency_graph.md — verify earlier-wave deps are complete.
4. state/decisions_log.md — note any decisions affecting wave scope
   (e.g., a vendor choice resolved that changes effort).
5. state/wave_<N-1>_digest.md if it exists — lessons from the prior
   wave (delays, dependency mistakes, parallelism that didn't pan out).

PRODUCE state/wave_<N>_status.md in this structure:

  # Wave <N> status

  **Goal.** <one-line wave goal from the operative plan>

  **Action count.** <N>

  **Critical path.** <ACT-A → ACT-B → ACT-C → ...> with effort
  estimate per action and total wave-floor estimate.

  **Track assignments.**

  | Track | Actions | Type | Notes |
  |---|---|---|---|
  | T1 | ACT-XX → ACT-YY → ACT-ZZ | serial | Depends on... |
  | T2 | ACT-AA, ACT-BB | parallel | Independent of T1 |
  | T3 | ACT-CC | parallel | ... |

  **Cross-track sync points.** Where two or more tracks must converge
  before another action can start (call out which 05_PARALLEL_MERGE.md
  invocation handles each).

  **External dependencies.** Anything outside engineering that must
  happen during this wave (e.g., IB account approval landing for
  ACT-20; LIP pool data accumulation for ACT-LIP-VIAB).

  **Wave-end gate.** What 09_WAVE_GATE.md will check at the end
  (default: all actions verified-complete; Wave 0 also gates on
  ACT-LIP-VIAB go decision).

  **Risks and escalations.**
  - <risk 1> → escalate to <prompt or human>
  - <risk 2> → ...

  **Estimated wall-clock.** With <N_orchestrator> parallel agents,
  approximately <X> engineer-weeks of critical path.

UPDATE state/PROJECT_CONTEXT.md to set:
  - active_wave: <N>
  - active_wave_status_file: state/wave_<N>_status.md

Do not write any code. Do not modify the plan. If you find a
contradiction in the plan or in deps, surface it as a risk; do not
silently fix.

When done, return only the path to wave_<N>_status.md and a 3-line
summary of the wave's shape (action count, critical-path length,
notable parallelism). The orchestrator will read the file directly.
```

---

## Wave-specific notes (for the planner agent to honour)

**Wave 0** is the most parallelism-sensitive. ACT-01, ACT-02, ACT-07
have no prereqs and start day-zero. ACT-03 (XL) is the longest single
item and gates four downstream actions. ACT-LIP-VIAB is the wave gate
and must be sequenced at the end with ACT-LIP-POOL data behind it.

**Wave 1** has ACT-17 (RND pipeline, XL) as the gating long pole.
ACT-14 and ACT-15 (refactors) start parallel-from-zero. ACT-22 (order
pipeline) starts immediately given Wave-0 ACT-06 done.

**Wave 2** is heavily parallel — most actions depend only on Wave-1
outputs.

**Wave 3** is small (3 actions); plan for one or two parallel tracks.

**Wave 4** is leaves; full parallelism achievable.

---

## Notes

- The planner is **not** an implementer. It must not modify code.
- A planner that finds the deps inconsistent with the plan should flag
  this to the orchestrator (and probably trigger
  `08_DEPENDENCY_AUDIT.md`) rather than self-resolve.
- Wave plans are working state — they can be re-emitted mid-wave if
  drift accumulates. The most recent file is authoritative.
