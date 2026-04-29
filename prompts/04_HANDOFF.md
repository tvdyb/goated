# 04 — HANDOFF prompt

Used when the current agent's context is approaching capacity (or an
action's scope is too large for one session) and work needs to
**resume in a fresh context**. Produces a structured handoff packet
that lets a fresh agent pick up cleanly.

## When to use
- Mid-action when context utilisation crosses ~60%.
- At the end of a wave to summarise what closed.
- After resolving a tricky decision, to capture the rationale.

## Inputs
- Whatever the current agent has been doing.
- Existing `state/action_<XX>/handoff.md` (if updating mid-action).
- `state/PROJECT_CONTEXT.md`.

## Outputs
- Updated `state/action_<XX>/handoff.md` (if mid-action) **or**
- New `state/digest_<phase>.md` (if end of wave / phase).
- Updated `state/PROJECT_CONTEXT.md` with the resumption pointer.

## Tool access
- Read, Write (only to `state/` and existing action's handoff).
- **No** Edit on production code (the handoff agent should not
  change behaviour).

---

## Prompt text

```
You are writing a handoff packet so that a fresh agent in a fresh
context can resume your work without re-discovering everything.

Decide which kind of handoff:
  - MID-ACTION: you are inside an ACT-<XX> implementation and need to
    stop. Update state/action_<XX>/handoff.md.
  - END-OF-PHASE: a wave or major phase just closed. Write
    state/digest_<phase>.md.
  - DECISION-CAPTURE: you just resolved an OD; ensure
    state/decisions_log.md has a complete entry; possibly write a
    digest of the chain of reasoning.

For MID-ACTION handoff, produce or update state/action_<XX>/handoff.md
with the FULL template from 02_ACTION_IMPLEMENT.md, paying special
attention to:

  **Status.** mid-flight context-capacity

  **What's done.** Explicit list of completed sub-tasks. Be precise
  enough that a fresh agent doesn't redo them.

  **What's left.** Explicit list of remaining sub-tasks, in order
  they should be tackled, with effort estimate per item.

  **Files in flight.** Files that have been edited but might be in
  an inconsistent state. For each, note: "consistent / partial /
  uncommitted / staged".

  **Test state.** Which tests pass right now, which fail, which are
  not yet written. If any tests fail, indicate whether the failure
  is expected (in-progress refactor) or a regression (needs fixing).

  **Mental model.** A 5-10 line paragraph capturing the design
  decisions you made and the tradeoffs you considered. This is the
  single most valuable section — it saves the next agent from
  re-deriving choices you already settled.

  **Gotchas / traps.** Specific things that bit you and might bite
  the next agent. E.g., "The numba JIT silently miscompiles if you
  pass numpy arrays of different dtypes into _gbm_prob_above; cast
  before calling."

  **Resumption command.** The literal first thing the next agent
  should do, e.g.: "Run pytest tests/test_act_19.py::test_inventory_
  bound first to confirm baseline; then continue with the γ-skew
  branch in models/quoter.py:78 onward."

For END-OF-PHASE digest, write state/digest_<phase>.md. The phase is
typically a wave (e.g., wave_0, wave_1) but could be a sub-phase if
a chunk of related actions closed together.

Structure:

  # Digest — <phase name> — <date>

  ## What closed
  - ACT-<XX>: <one-line summary, link to handoff>
  - ...

  ## Decisions resolved during this phase
  - OD-<NN>: <one-line summary, link to decisions_log entry>
  - ...

  ## Interfaces frozen during this phase
  - <interface_name>: <one-line summary>

  ## Lessons (carry forward)
  - <Lesson 1: what we tried, what worked or didn't, what to do
    differently>
  - <Lesson 2: ...>

  ## Open issues for next phase
  - <Issue: where it lives, who can address it>

  ## Stats
  - Action count: <N>
  - LoC delta: +<X> / -<Y>
  - Test count delta: +<N>
  - Calendar duration: <wall-clock days>

For DECISION-CAPTURE, ensure state/decisions_log.md has an entry
following the template in prompts/state/templates/decisions_log.md.
template. Then optionally write a state/digest_decision_<OD>.md if
the reasoning was complex enough that future agents will want to
revisit it.

UPDATE state/PROJECT_CONTEXT.md to set:
  - For MID-ACTION: 'in_flight' includes ACT-<XX> with status
    'mid-flight context-capacity', resumption_pointer:
    state/action_<XX>/handoff.md.
  - For END-OF-PHASE: 'completed_phases' appends the phase name and
    digest path.

DO NOT introduce new behaviour or write production code. The handoff
prompt is observation + serialisation only.

Compress aggressively. The handoff is a working note, not a paper.
The 'mental model' section deserves care; everything else should be
factual and terse.

When done, return the path to the updated handoff or digest file.
```

---

## Notes

- The handoff is the *single most important* artifact for cross-
  context-window operation. A bad handoff = the next agent re-derives
  things and burns context. A good handoff = the next agent picks up
  in 5 minutes.
- "Compress aggressively" is a direct quote from
  [Anthropic's harness research](https://www.anthropic.com/engineering/harness-design-long-running-apps):
  "you don't need to save everything — you need to save just enough
  for the next process to make good decisions quickly."
- The mental-model section is the only narrative section; everything
  else should be enumerative or factual.
- For very small actions that finish in a single context, no handoff
  is needed beyond the standard `handoff.md` produced by
  `02_ACTION_IMPLEMENT.md`'s Step 5.
