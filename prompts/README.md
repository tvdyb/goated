# Prompt Stack — `goated`

This directory is the operational prompt stack for implementing the
goated project end-to-end. It's designed for **cross-context-window
execution with parallel agents** — each prompt is self-contained,
artifact-driven, and assumes the executing agent has no prior
conversation history.

If you're new, read this file first, then `00_BOOT.md`.

---

## 1. Architectural principles

The stack applies six principles from the 2026 long-running-agent
literature ([Anthropic harness research](https://www.anthropic.com/engineering/harness-design-long-running-apps),
[LangGraph state-delta pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs),
[Claude Code subagents](https://code.claude.com/docs/en/sub-agents)):

1. **Artifacts are state, transcripts are not.** Every prompt produces
   durable files; nothing relies on conversation memory. A fresh agent
   in a fresh context can pick up any phase by reading the artifacts.

2. **Context resets > compaction.** When a context window approaches
   capacity, the agent writes a *handoff packet* and a new agent starts
   fresh. Compaction is a last resort, not a primary strategy.

3. **Three storage layers.**
   - **Working state** (volatile, overwritten each session) —
     `state/PROJECT_CONTEXT.md`, `state/wave_<N>_status.md`.
   - **Episodic memory** (append-only, what happened) —
     `state/digest_<phase>.md` per completed phase, plus
     `state/decisions_log.md`.
   - **Spec / persistent** (read-only, defines what's true) — the
     audit files (`audit/audit_F3_refactor_plan_lip.md`,
     `audit/audit_E_gap_register.md`, `audit/audit_A_cartography.md`)
     and `ONBOARDING.md`.

4. **Interface contracts before parallel work.** Two agents implementing
   independent actions need a frozen contract (data shape, function
   signature, file path) before either starts coding. Section
   `07_INTERFACE_CONTRACT.md` formalises this.

5. **Verification gates between phases.** No phase is "done" until a
   *separate* verification agent checks output against criteria. The
   verifier has read-only tool access — it cannot fix what it finds, only
   report.

6. **Minimum-privilege tool access per agent.** Boot agent: read +
   web. Implementing agent: read + write + bash + code. Verifying agent:
   read + bash only. Handoff agent: read + write to `state/` only.

---

## 2. Prompt taxonomy

| File | Purpose | Triggered by | Output |
|---|---|---|---|
| `00_BOOT.md` | Cold-start any agent picking up the project. Reads bedrock context + current state. | New session, no prior history. | Working knowledge of project state; no files written. |
| `01_WAVE_PLANNER.md` | At the start of a wave, decompose into parallel/serial tracks; assign actions to agents. | Beginning of Wave 0/1/2/3/4. | `state/wave_<N>_status.md` with track assignments + dependency graph. |
| `02_ACTION_IMPLEMENT.md` | Template for implementing one ACT-XX. Cites F3 / E / A as inputs. | Per-action; one agent or per-track parallel agents. | Code in repo + `state/action_<XX>_handoff.md` digest. |
| `03_ACTION_VERIFY.md` | Verifies an ACT-XX output against success criteria. Read-only tools. | After each action implementation. | Pass/fail in `state/action_<XX>_verify.md`; no code changes. |
| `04_HANDOFF.md` | Writes a structured handoff packet before context reset. | When current agent's context approaches 60–70% capacity. | Updated `state/PROJECT_CONTEXT.md` + `state/digest_<phase>.md`. |
| `05_PARALLEL_MERGE.md` | Combines outputs from parallel-track agents into a coherent state. | After parallel tracks within a wave converge. | Updated `state/wave_<N>_status.md` + integration test output. |
| `06_DECISION_RESOLVE.md` | Closes an outstanding decision (OD-XX) with recorded rationale. | When a decision needs to be made (governance / vendor / parameter). | Appended entry in `state/decisions_log.md`. |
| `07_INTERFACE_CONTRACT.md` | Freezes a module/function/data interface before parallel work. | Before two or more agents touch interfaces of the same module. | `state/interfaces/<contract_name>.md`. |
| `08_DEPENDENCY_AUDIT.md` | Periodically verifies the runtime DAG state is consistent with the F3 plan. | End of each wave or on suspected drift. | `state/dependency_audit_<date>.md` with discrepancies. |
| `09_WAVE_GATE.md` | End-of-wave verification. Special-cased for ACT-LIP-VIAB go/no-go. | End of each wave; mandatory at end of Wave 0. | Pass/fail decision in `state/wave_<N>_gate.md`. |

Plus state-file templates in `state/templates/`:

- `PROJECT_CONTEXT.md.template`
- `wave_status.md.template`
- `action_handoff.md.template`
- `decisions_log.md.template`
- `digest.md.template`
- `interface.md.template`
- `verify_report.md.template`
- `wave_gate.md.template`

---

## 3. Bedrock files (read-only context for every prompt)

Any prompt in this stack can assume these exist and are
authoritative:

- `ONBOARDING.md` — project orientation, decisions resolved so far.
- `audit/audit_F3_refactor_plan_lip.md` — the operative action plan
  (F3, LIP-driven).
- `audit/audit_E_gap_register.md` — every gap with C-id citations and
  code-location pointers.
- `audit/audit_A_cartography.md` — module inventory, red flags,
  external deps.
- `README.md` — non-negotiables (no pandas hot path, fail-loud, etc.).

If F3 is superseded later (e.g., by an F4), the bedrock pointer
updates and prompts read the new file. Prompts cite *the plan currently
in force*, not a fixed file path; one indirection in
`state/PROJECT_CONTEXT.md` lets the bedrock evolve.

---

## 4. State directory layout

```
state/
├── PROJECT_CONTEXT.md            # working: current operative plan, current wave, current actions in flight
├── decisions_log.md              # episodic: append-only OD resolutions
├── dependency_graph.md           # working: ACT-XX completion + dependency status
├── wave_0_status.md              # working: per-wave track assignments & status
├── wave_0_gate.md                # episodic: end-of-wave gate pass/fail
├── wave_0_digest.md              # episodic: compressed memory after wave closes
├── wave_1_status.md              # ... (created when Wave 1 starts)
├── action_<XX>/
│   ├── plan.md                   # working: implementation plan for this action
│   ├── handoff.md                # working: digest for next agent picking this up
│   ├── verify.md                 # episodic: verification report
│   └── interface.md              # working: any interface contracts this action freezes
├── interfaces/
│   ├── theo_output.md            # frozen contracts that span actions
│   ├── kalshi_client.md
│   └── ...
└── templates/
    └── (the .template files)
```

Volatile vs. append-only:

- **Volatile** (overwritten freely): `PROJECT_CONTEXT.md`,
  `wave_<N>_status.md`, `dependency_graph.md`,
  `action_<XX>/{plan,handoff,interface}.md`.
- **Append-only** (never edit prior entries): `decisions_log.md`,
  `wave_<N>_gate.md`, `wave_<N>_digest.md`,
  `action_<XX>/verify.md`.

---

## 5. Operational protocols

### 5.1 Cold start
- Run `00_BOOT.md` in a fresh agent. Output is working knowledge, no files.
- Boot agent reads bedrock + current state and confirms it can articulate (a) which wave is active, (b) which actions are in flight, (c) which decisions are pending.

### 5.2 Starting a wave
- Run `01_WAVE_PLANNER.md`. Inputs: bedrock + completed-waves digests. Output: `state/wave_<N>_status.md` with track assignments.
- Wave plan must explicitly mark each action as `serial`, `parallel-track-A`, `parallel-track-B`, etc.

### 5.3 Implementing an action
- For each action: spawn an implementing agent with `02_ACTION_IMPLEMENT.md` parameterised on the action ID.
- Independent actions in the same wave run in **parallel agent invocations** (Claude Code subagent / Task tool / external orchestrator).
- Each implementing agent is responsible for writing its own `state/action_<XX>/handoff.md` before returning.

### 5.4 Verifying an action
- After each `02_ACTION_IMPLEMENT.md` returns, immediately spawn a verification agent with `03_ACTION_VERIFY.md` parameterised on the same action.
- Verifier has read-only tool access (cannot modify code).
- If verification fails, route back to a remediation invocation of `02_ACTION_IMPLEMENT.md` with the verifier's report attached.

### 5.5 Handing off mid-action
- Implementing agent monitors its own context utilisation. When it crosses a threshold (~60% of context), it stops productive work and runs `04_HANDOFF.md` instead.
- Handoff produces an updated `action_<XX>/handoff.md` with: what's done, what remains, what gotchas exist, what files were touched, what tests pass/fail.
- Next agent picks up via `00_BOOT.md` + reading the handoff packet.

### 5.6 Merging parallel work
- When parallel tracks in a wave converge, run `05_PARALLEL_MERGE.md`. Output: integration test pass + updated wave-status file.

### 5.7 Resolving a decision
- When code work hits an OD that needs resolution (e.g., "the F3 default for OD-22 says PIT, but the USDA endpoint we found doesn't support PIT — what now?"), pause implementation and run `06_DECISION_RESOLVE.md` first. Append to `decisions_log.md` before returning to implementation.

### 5.8 Freezing an interface
- When two or more actions in the same wave touch the same module's public surface, run `07_INTERFACE_CONTRACT.md` *before* either action starts. Both implementing agents reference the frozen contract.

### 5.9 Auditing the DAG
- At the end of each wave (and on suspicion of drift), run `08_DEPENDENCY_AUDIT.md`. Catches issues like "ACT-19 says it depends on ACT-17 but ACT-17 isn't actually marked complete in `dependency_graph.md`."

### 5.10 Ending a wave
- When all actions in a wave are verified-complete, run `09_WAVE_GATE.md`. Wave 0 is special: ACT-LIP-VIAB gates Wave 1 and may produce a no-go decision.

---

## 6. Parallelism map (which actions can run concurrently)

Per F3 §8 (dependency graph, inherited from F1 §8). At any moment, the
runtime DAG in `state/dependency_graph.md` shows which actions are
"ready" (all deps met, not yet started). Within that ready set, an
orchestrator can dispatch up to N parallel agents.

Wave-by-wave parallelism, with N=3 engineers/agents as a baseline:

**Wave 0 (16 actions).** Heavy parallelism early; bottleneck is ACT-03
(XL Kalshi client). Three parallel tracks at start: (a) ACT-01 capture,
(b) ACT-02→ACT-03 (Kalshi client), (c) ACT-07 calendar. Once ACT-03
lands, ACT-04/ACT-05/ACT-11/ACT-LIP-POOL all unblock simultaneously.
Critical path: ACT-02 → ACT-03 → ACT-04 → ACT-09 → ACT-12 → (Wave
gate at ACT-LIP-VIAB).

**Wave 1 (13 actions).** ACT-14 and ACT-15 (refactors of existing
modules) can run parallel from t=0. ACT-22 (order pipeline) can start
immediately given ACT-06. ACT-17 RND pipeline is the longest item;
gates ACT-19 and many Wave-2 items. ACT-26 backtest M0 needs ACT-01
+ ACT-17.

**Wave 2 (7 actions).** Heavily parallel — most actions depend only on
Wave-1 outputs and can all start at t=0 of the wave. Critical path is
the longest single action (ACT-27 Heston SV at L effort).

**Wave 3 (3 actions).** Mostly independent; ACT-LIP-MULTI is the
biggest.

**Wave 4 (5 actions).** Almost all leaves; parallel.

`08_DEPENDENCY_AUDIT.md` walks the graph to compute ready-set; an
orchestrator (you, or a meta-agent) reads that and dispatches the
next batch.

---

## 7. Quick-start cheat sheet

You're picking up the project for the first time:

```
1. Read prompts/00_BOOT.md and execute it as your context.
2. Read state/PROJECT_CONTEXT.md (or create it from template if missing).
3. Read state/dependency_graph.md to find ready actions.
4. Pick a ready action; spawn an agent with prompts/02_ACTION_IMPLEMENT.md
   parameterised on that action ID.
5. After agent returns, spawn a verifier with prompts/03_ACTION_VERIFY.md.
6. If verifier passes, mark action complete in state/dependency_graph.md.
   Repeat from step 3.
7. When wave's actions are all verified, run prompts/09_WAVE_GATE.md.
   On pass, advance to next wave via prompts/01_WAVE_PLANNER.md.
```

You're hitting context capacity mid-action:

```
1. Stop productive work.
2. Run prompts/04_HANDOFF.md.
3. End the session.
4. Start a fresh session, run prompts/00_BOOT.md, read the handoff
   packet, resume.
```

You need to make a decision:

```
1. Pause whatever action triggered it.
2. Run prompts/06_DECISION_RESOLVE.md with the OD ID.
3. Append to state/decisions_log.md.
4. Resume the paused action with the decision now resolved.
```

---

## 8. Failure-mode handling

Common failure patterns and which prompt addresses them:

| Failure | Prompt to run |
|---|---|
| Agent hits context cap mid-work | `04_HANDOFF.md` |
| Action verifier fails | Re-run `02_ACTION_IMPLEMENT.md` with verifier report attached |
| Two parallel agents produced conflicting outputs | `05_PARALLEL_MERGE.md` with conflict analysis |
| DAG state looks inconsistent | `08_DEPENDENCY_AUDIT.md` |
| Wave gate fails (esp. Wave 0 ACT-LIP-VIAB) | Convene human review; do not auto-advance |
| New decision encountered mid-action | `06_DECISION_RESOLVE.md` then resume |
| Two agents need to touch same module | `07_INTERFACE_CONTRACT.md` first |

---

## 9. What this stack does NOT do

- It does not replace human judgment on go/no-go gates (especially
  Wave 0's ACT-LIP-VIAB).
- It does not handle non-engineering work (IB account application,
  Kalshi support inquiries, capital decisions). Those route to humans.
- It does not validate financial correctness — only software
  correctness against the spec. Financial validation is a human
  responsibility (in particular, kill-criteria evaluation).

---

## 10. Maintenance

When the bedrock evolves (F4 supersedes F3, new audit phase lands,
etc.):

1. Update `state/PROJECT_CONTEXT.md`'s "operative plan" pointer.
2. Run `08_DEPENDENCY_AUDIT.md` to re-validate the DAG against the new
   plan.
3. Append a `state/digest_bedrock_update_<date>.md` capturing what
   changed.

The prompts themselves should remain stable — they cite "the operative
plan in PROJECT_CONTEXT.md" rather than hard-coded file names. If
prompt revisions are needed, version them (`02_ACTION_IMPLEMENT_v2.md`)
rather than overwriting.

Sources for the patterns used:
- [Anthropic — Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Claude Code — Subagents docs](https://code.claude.com/docs/en/sub-agents)
- [LangChain — Multi-agent handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs)
- [Persistence patterns for AI agents that survive restarts](https://dev.to/aureus_c_b3ba7f87cc34d74d49/persistence-patterns-for-ai-agents-that-survive-restarts-59ck)
