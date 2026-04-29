# 06 — DECISION RESOLVE prompt

Closes an outstanding decision (`OD-XX`) with **a recorded rationale**
that future agents and humans can audit. Decisions are append-only —
once logged they are never silently changed.

## When to use
- Mid-action when an OD blocks progress (e.g., the F3 default for
  OD-22 says PIT, but the implementer finds USDA's PIT API is
  unavailable).
- Pre-wave when an OD's resolution affects wave shape.
- Whenever a stakeholder explicitly resolves a pending decision.

## Inputs
- The OD's row in the operative plan (or in F1/F2 if the OD is
  inherited).
- `state/decisions_log.md` (existing log).
- Whatever evidence informed the resolution.

## Outputs
- Appended entry in `state/decisions_log.md`.
- Possibly a minimal config update in the codebase to operationalise
  the decision.
- If the decision changes wave scope, a flag back to the orchestrator.

---

## Prompt text

```
You are resolving an outstanding decision.

DECISION ID: OD-<NN>

Step 1 — Read the decision.
  1. Find OD-<NN> in the operative plan's section 11 (Outstanding
     decisions). Note the question, the working default, and the
     downstream actions affected.
  2. Read state/decisions_log.md. If OD-<NN> already has an entry,
     stop and report — decisions are append-only and not re-resolvable
     without the orchestrator's explicit instruction.
  3. Read any prior digest_decision_<OD>.md if present.

Step 2 — Gather evidence.

For governance / scope decisions: the user/stakeholder is the
authority; this prompt is just capturing their answer.

For vendor / integration decisions: external constraints (cost,
availability, contract terms) drive the answer; this prompt
records what was true at decision time.

For parameter / policy decisions: empirical observation or
literature is the authority; this prompt records the source.

For decisions blocked on Kalshi-side or broker-side info: explicitly
note 'blocked on <party>' and use the working default until they
respond. Do not invent.

Step 3 — Form the resolution.

Decide one of:
  - RESOLVED <answer>: definitive answer, including the rationale.
  - DEFERRED-DEFAULT: keep the operative-plan working default, with
    a note about when to revisit.
  - INVALIDATED: the decision is moot under current framing
    (e.g., OD-32 was invalidated when F3 replaced F2).
  - BLOCKED <party>: cannot resolve without external input; document
    the question and where it was sent.

Step 4 — Append to state/decisions_log.md.

Use this exact entry format (template lives in
prompts/state/templates/decisions_log.md.template):

  ---

  ## OD-<NN> — <one-line decision title> — RESOLVED / DEFERRED-DEFAULT / INVALIDATED / BLOCKED

  **Date.** <YYYY-MM-DD>
  **Resolver.** <agent-id, human-name, or 'orchestrator'>
  **Question.** <the OD's original question, paraphrased to ≤50 words>
  **Resolution.** <the answer in one paragraph>
  **Rationale.**
  - <bullet 1: what evidence drove this>
  - <bullet 2: what alternatives were considered>
  - <bullet 3: what tradeoff was accepted>
  **Affected actions.** <list of ACT-<XX> downstream of this decision>
  **Reconsideration trigger.** <empirical observation that should
  cause us to revisit, e.g., 'if M0 backtest shows X, revisit'>
  **Source / authority.** <citation: web URL, F-plan section, human
  decision, etc.>

  ---

Step 5 — If the decision affects in-flight or queued actions:
  - For RESOLVED with a non-default answer: flag the affected actions
    in state/dependency_graph.md (annotate column 'note' with 'OD-<NN>
    resolved <date>; review impact on action scope').
  - For BLOCKED: ensure the affected actions are aware of the working
    default and the blocked status.

Step 6 — Optionally, write a minimal config change.

If the resolution is a small parameter (e.g., 'Kalshi rate-limit tier:
Standard'), update the relevant config file with the value. Keep edits
to literally the value being set; do not refactor.

DO NOT modify operative-plan files. The plan can be amended in a
later F-version (F4, F5...) but not in-line.

When done, return the path to decisions_log.md and a 2-line summary.
```

---

## Notes

- **Decisions are append-only.** If a prior decision was wrong, the
  remedy is a NEW decision entry that supersedes the prior one,
  citing it explicitly. Never edit the prior entry.
- The "Reconsideration trigger" field is critical. Without it,
  decisions accumulate forever and nobody knows when to revisit.
- For governance decisions (OD-01 scope, OD-23 WTI vs soybean), the
  resolver is necessarily the project lead; this prompt just captures
  their answer cleanly.
- For BLOCKED decisions on external parties (Kalshi support, IB
  account approval, FCM legal), include the literal text or summary
  of what was sent and to whom, plus the date sent. This is your
  audit trail when something later turns out to depend on a delayed
  response.
