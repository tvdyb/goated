# 00 — BOOT prompt

Use this prompt at the **start of any session** where the agent has no
prior context. It establishes working knowledge without writing files.

## When to use
- Cold-start of a new context window.
- After a `04_HANDOFF.md` produced a fresh-context resume.
- When an existing session feels confused about project state.

## Inputs (all read-only)
- `prompts/README.md` (architecture)
- `ONBOARDING.md` (project orientation)
- `state/PROJECT_CONTEXT.md` (current operative plan + active wave)
- The operative plan file (cited in PROJECT_CONTEXT.md; currently
  `audit/audit_F3_refactor_plan_lip.md`)
- `state/decisions_log.md` (resolved decisions)
- `state/dependency_graph.md` (action completion state)

## Outputs
None. Boot is a context-establishment step. Working knowledge only.

## Success criteria
After running, the agent can answer in one or two sentences each:
1. What is this project's mission?
2. What is the current operative plan? (file name + framing)
3. Which wave is active?
4. Which actions are in flight, ready, or blocked?
5. Which decisions are resolved vs. pending?
6. What constraints (non-negotiables) apply to any code written?

If the agent cannot answer any of these from the artifacts, it should
flag the missing artifact rather than guess.

---

## Prompt text

```
You are picking up the goated project mid-flight. You have no prior
context. Establish working knowledge by reading the bedrock and
state files, in this order:

1. prompts/README.md — for architectural context on how this project
   is organised and how prompts handoff state.
2. ONBOARDING.md — for project mission, current state, and decisions
   resolved so far.
3. state/PROJECT_CONTEXT.md — for the current operative plan
   pointer, active wave, and actions in flight. If this file does
   not exist, read prompts/state/templates/PROJECT_CONTEXT.md.template
   and create state/PROJECT_CONTEXT.md from it; mark it as bootstrap
   state and surface that to me.
4. The operative plan file referenced in PROJECT_CONTEXT.md (currently
   expected to be audit/audit_F3_refactor_plan_lip.md). Read sections
   1, 3, and 4 — strategic frame, action set, and cuts. Skip the rest
   on first pass.
5. state/decisions_log.md — for resolved decisions. If absent, note
   that no decisions have been formally logged yet.
6. state/dependency_graph.md — for action-completion state. If absent,
   compute the initial graph from the plan file's dependency section.

Do NOT write any files during boot beyond bootstrapping a missing
PROJECT_CONTEXT.md from template. Do NOT start implementation work.
Do NOT run code or shell commands.

After reading, produce a STATUS BRIEF as your final response, in
this exact structure:

  ## Status brief

  **Mission.** <one sentence>

  **Operative plan.** <file name and one-line framing>

  **Active wave.** Wave <N> — <one-line goal>

  **In flight.** <list of ACT-XX currently being implemented, or "none">

  **Ready (deps met, not started).** <list of ACT-XX from the ready set,
  or "none">

  **Blocked (waiting on deps or decisions).** <list with what they're
  waiting on>

  **Decisions resolved.** <count + ID list, or "none formally logged">

  **Decisions pending.** <count + ID list>

  **Non-negotiables in force.** <2-4 bullet points from README.md
  pre-publish discipline, fail-loud, hot-path constraints, etc.>

  **Next reasonable action.** <one of: pick a ready ACT-XX and run
  02_ACTION_IMPLEMENT.md; resolve a pending OD with 06_DECISION_RESOLVE
  .md; verify a recently-completed ACT-XX with 03_ACTION_VERIFY.md; run
  09_WAVE_GATE.md if all actions in the wave are verified; etc.>

After producing the brief, stop. Do not propose code, do not start
work. Wait for the orchestrator (or human) to direct you to a
specific prompt.
```

---

## Notes

- The boot prompt deliberately avoids reading every audit file. F1, F2,
  the ten Phase-D files, and the Phase-C claim registers are *not*
  required for boot. They are lookup references for action prompts.
- If `PROJECT_CONTEXT.md` is missing, the boot agent creates it from
  template *before* attempting to compute status — otherwise the next
  agent picking up will hit the same missing-file condition.
- The status brief is the boot agent's single deliverable. Anything
  else it does is exceeding scope.
- A boot agent should fit comfortably inside 30-50% of a context
  window, leaving room for the next prompt to do real work.
