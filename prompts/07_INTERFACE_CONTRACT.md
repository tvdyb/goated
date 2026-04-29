# 07 — INTERFACE CONTRACT prompt

When **two or more actions in the same wave** will independently
modify or extend the same module's public surface (a function
signature, a dataclass shape, an HTTP endpoint, a config schema), this
prompt **freezes the contract** before either action starts coding.
Without this, parallel work produces conflicting interfaces that
`05_PARALLEL_MERGE.md` cannot reconcile cleanly.

## When to use
- Wave 1 ACT-15 (`TheoOutput` shape change) intersects with everything
  pricing-side — define the shape contract first.
- Wave 1 ACT-14 (IV surface signature change) intersects with ACT-16
  (CME ingest) and ACT-17 (RND pipeline) — define the surface query
  contract first.
- Wave 1 ACT-22 (order pipeline) intersects with ACT-23
  (reconciliation) on the fill-event shape.
- Wave 0 ACT-04 (bucket grid) intersects with ACT-13 (corridor
  adapter) on the `Bucket` data structure.
- Any time two parallel actions would otherwise both write the same
  dataclass, function, or table schema.

## Inputs
- The operative plan rows for the actions involved.
- The relevant gap-register detail rows for context on the original
  design intent.
- Existing code at the cited locations.

## Outputs
- `state/interfaces/<contract_name>.md` (frozen contract).
- A possibly-empty stub commit that lands the new types/signatures
  in the codebase before either implementing action begins.

## Tool access
- Read, Grep, Bash.
- Write to `state/interfaces/`.
- Edit / Write to the codebase **only for stub creation** — no real
  logic.

---

## Prompt text

```
You are freezing an interface contract for module / function /
data-shape '<contract_name>' that will be touched by parallel
actions <ACT-XX> and <ACT-YY> (and possibly more).

Step 1 — Read context.
  1. The operative plan rows for each affected action.
  2. The gap-register detail rows for any GAP-id those actions cite
     that pertains to this interface.
  3. The existing code at cited locations (read with Read; do not
     edit).
  4. README.md non-negotiables (no pandas hot path, fail-loud, etc.).

Step 2 — Decide the contract shape.

Choose:
  - For dataclasses: field names, dtypes, optional vs required,
    immutability (frozen=True for hot-path).
  - For function signatures: positional vs keyword args, type hints,
    return type, raise contract.
  - For HTTP / WS endpoints: URL pattern, request schema, response
    schema, error semantics.
  - For config schemas: YAML keys, types, defaults, validation rules.

Apply project-specific conventions:
  - TheoOutput-style dataclasses are frozen and carry provenance
    (as_of_ns, source_tick_seq, model_name, params_version).
  - Hot-path numerical types use numpy arrays of explicit dtype, not
    Python lists.
  - All "missing input" cases raise (StaleDataError /
    MissingStateError / SanityError); never return None or a default.
  - Public methods are kw-only past the first 1-2 positional args.

Step 3 — Write state/interfaces/<contract_name>.md.

Format:

  # Interface contract — <contract_name>

  **Frozen.** <date>
  **Frozen by.** <agent-id or human-name>
  **Affected actions.** ACT-<XX>, ACT-<YY>, ...

  ## Type / signature

  ```python
  # Concrete signature, copy-paste-ready.
  ```

  ## Semantics

  - <Bullet 1: when this is called, what it must return>
  - <Bullet 2: what error to raise on what failure mode>
  - <Bullet 3: any invariants the caller must satisfy>

  ## Provenance fields

  <if applicable: as_of_ns, source_tick_seq, etc.>

  ## Tests required

  - <Test 1: contract case to verify>
  - <Test 2: ...>

  ## Versioning

  - **Version.** v1
  - **Breaking-change policy.** New version (v2) lives alongside v1
    until all callers migrate. v1 raises DeprecationWarning during
    migration. No silent shape changes.

  ## Examples

  ```python
  # Concrete usage example.
  ```

Step 4 — Land the stub.

If the affected module doesn't yet have the new shape, create a
stub commit:
  - Add the dataclass / function signature with the new shape.
  - Implement only `raise NotImplementedError("ACT-<XX>")` in the
    body, with the action-id pointing at the implementing action.
  - Add a test that asserts the type / signature exists with the
    expected shape — this becomes a regression test for the contract.

DO NOT implement real behaviour. The stub is the bare minimum that
makes the contract observable to downstream code.

Step 5 — Notify both action plans.

If state/action_<XX>/plan.md already exists, append a line:
'Honours frozen interface state/interfaces/<contract_name>.md v1.'
Same for ACT-<YY>.

When done, return the path to the interface file and the stub commit
hash.
```

---

## Notes

- A frozen contract is **a single source of truth**. If during
  implementation an action realises the contract is wrong, it does
  NOT silently change it — it pauses, runs `06_DECISION_RESOLVE.md`
  on a synthesised OD ("interface `<name>` v1 needs revision"),
  produces a v2 contract, and only then resumes.
- Stub commits sound like overhead but they are the cheapest way to
  prevent merge conflicts. The cost of a stub is ~5 minutes; the cost
  of an unreconciled merge is hours of debugging.
- The "Tests required" section in the contract becomes the verifier's
  shopping list when checking whether honouring actions actually
  honoured the contract.
