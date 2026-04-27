# Audit Phase B — `validation-sanity`

Cross-checked against `audit/audit_A_cartography.md:225`. The Phase A
inventory row for slug `validation-sanity` lists exactly one runtime file,
`validation/sanity.py`, plus the package marker `validation/__init__.py`
that the inventory's "(excluding empty `__init__.py` files)" rule omits
from the LoC total. The file in scope matches; no mismatch.

---

## 1. Module identity

- **Files**:
  - `validation/sanity.py` — 68 lines (`wc -l`).
  - `validation/__init__.py` — 0 lines (empty file; confirmed by Read
    returning the "shorter than the provided offset (1)" warning and by
    `wc -l` reporting 0).
- **Total LoC**: 68 (matches `audit/audit_A_cartography.md:225`).
- **External Python deps**: `numpy` only (`validation/sanity.py:23`).
- **Intra-repo deps**: `models.base.TheoOutput`
  (`validation/sanity.py:25`).
- **Summary**: A single-class, single-method module
  (`SanityChecker.check`, `validation/sanity.py:38-68`) plus a thin
  `RuntimeError` subclass (`SanityError`, `validation/sanity.py:28-29`).
  `check` runs five vectorised gates over a `TheoOutput` — shape, size,
  finiteness, [0,1] range, and monotone-non-increasing-in-K — and raises
  `SanityError` on any failure. It owns no state beyond a single tolerance
  scalar (`_monotone_tol`, `validation/sanity.py:33-36`), performs no I/O,
  and is the last call inside `Pricer.reprice_market`
  (`engine/pricer.py:89`) before the theo is returned to the caller.

## 2. Responsibility

Inferred from the code, the module solves one problem: *guard the publish
boundary*. The module-level docstring at `validation/sanity.py:1-19`
states the contract — every probability finite, every probability in
[0,1], probabilities monotone non-increasing in K, strike and probability
arrays shape-matched. The same docstring at `validation/sanity.py:11-14`
explicitly delegates two related invariants elsewhere: digital put-call
parity is "automatic by construction" and tested in `tests/`, and
boundary behaviour (`theo → 1` as K → 0, `theo → 0` as K → ∞) is
"tested offline against analytical limits". So the live check is
narrower than the spec inferred from the docstring header — it does not
re-prove parity per call, and it does not check limit behaviour, only
"what's enforceable on the live strike grid"
(`validation/sanity.py:18`).

The placement at `engine/pricer.py:89` — after `model.price(inputs)` and
before the function `return` — is the only thing that gives the module
its meaning. There is no second call site that runs `check` against an
output produced anywhere else; if the pricer ever bypasses the sanity
step, no other path catches a malformed `TheoOutput`. The module is
purely a gate inserted on a single hot-path edge.

The same docstring at `validation/sanity.py:3` notes "Runs on the hot
path, so every check is O(n_strikes) and avoids Python loops." That
constraint is honoured at `validation/sanity.py:43-68` by using only
vectorised numpy primitives (`np.all`, `np.isfinite`, `.min()`, `.max()`,
`np.argsort`, `np.diff`, `np.argmax`) — no `for` loops, no per-element
Python predicate.

## 3. Public interface

The module exports two top-level symbols. There is no `__all__`, so
"public" here is read off the leading-underscore convention.

- **`class SanityError(RuntimeError)`** — `validation/sanity.py:28-29`.
  Empty-body subclass of `RuntimeError`. Used as the single error type
  the module raises (six raise sites: `validation/sanity.py:44, 46, 50,
  52, 54, 64`). One-line role: typed signal that the published-side
  invariants of a `TheoOutput` were violated.
- **`class SanityChecker`** — `validation/sanity.py:32-68`. The full
  shape:
  - `__slots__ = ("_monotone_tol",)` — `validation/sanity.py:33`.
  - `__init__(self, monotone_tol: float = 1e-12) -> None` —
    `validation/sanity.py:35-36`. Coerces the argument with `float(...)`
    and stores it.
  - `check(self, output: TheoOutput, *, spot: float) -> None` —
    `validation/sanity.py:38`. The only public method. Returns `None`
    on success; raises `SanityError` on any failed gate. `spot` is
    keyword-only and used only inside the monotone-failure error
    message (`validation/sanity.py:67`); it is never compared, used to
    re-derive a value, or otherwise consumed.

The package marker `validation/__init__.py` is empty (zero bytes,
confirmed via Read and `wc -l`), so importers reach symbols through the
fully qualified `from validation.sanity import ...` form. Every observed
import does exactly that (`engine/pricer.py:29`,
`benchmarks/harness.py:30`, `tests/test_end_to_end.py:26`).

The `models/base.py:55-69` docstring on the abstract `Theo.price`
contract states the model "MUST […] return probabilities in [0, 1]" and
"be monotone non-increasing in strike (enforced by validation/sanity)"
(`models/base.py:63-64`). That is the only documented cross-reference
naming this module by file path.

## 4. Internal structure

`SanityChecker` is a sealed class via `__slots__` (`validation/sanity.py:33`)
holding exactly one float, `_monotone_tol`. There are no other instance
attributes, no class attributes beyond the slot tuple, and no
`__init_subclass__` / `__post_init__` machinery.

The data flow inside `check` is a fixed-order linear cascade
(`validation/sanity.py:39-68`):

1. **Local rebind.** `probs = output.probabilities`, `strikes =
   output.strikes`, `name = output.commodity` (`validation/sanity.py:39-41`).
   Reading from a frozen dataclass (`models/base.py:44-52`) so this is a
   pure pointer copy; no allocation.
2. **Probability-array dimensionality.**
   `if probs.ndim != 1: raise SanityError(...)`
   (`validation/sanity.py:43-44`).
3. **Cross-array shape match.** `if probs.shape != strikes.shape: raise
   SanityError(...)` (`validation/sanity.py:45-48`). Note this compares
   `tuple(int)` shapes, not just lengths; if one were 1-D and the other
   2-D both the prior `ndim` check and this would fire — `ndim` first.
4. **Non-empty.** `if probs.size == 0: raise SanityError(...)`
   (`validation/sanity.py:49-50`).
5. **Finiteness.** `if not np.all(np.isfinite(probs)): raise
   SanityError(...)` (`validation/sanity.py:51-52`). `np.isfinite`
   excludes `+inf`, `-inf`, and `NaN`.
6. **Range.** `if probs.min() < 0.0 or probs.max() > 1.0: raise
   SanityError(...)` (`validation/sanity.py:53-57`). Runs only after
   step 5 has guaranteed finite probs, so `.min()` and `.max()` cannot
   propagate NaN.
7. **Monotone non-increasing in K (with FP tolerance).**
   `validation/sanity.py:59-68`:
   - `order = np.argsort(strikes, kind="stable")` —
     `validation/sanity.py:59`.
   - `probs_sorted = probs[order]` — `validation/sanity.py:60`.
   - `diffs = np.diff(probs_sorted)` — `validation/sanity.py:61`. Length
     `n - 1` for `n = strikes.size`.
   - `if diffs.size and diffs.max() > self._monotone_tol: raise
     SanityError(...)` — `validation/sanity.py:62-68`. The short-circuit
     `diffs.size` guards the `n == 1` case (where `np.diff` returns an
     empty array and `.max()` on an empty array would raise
     `ValueError`).
   - The error message reconstructs both indices into the *sorted*
     view using `bad = int(np.argmax(diffs))` and reports the strike
     pair at `strikes[order][bad], strikes[order][bad + 1]`
     (`validation/sanity.py:63-67`). The pair shown is in
     ascending-strike order; the comparison being asserted is that
     `probs[order]` is non-increasing (so any positive `diff` is a
     violation).

The notable algorithmic choice is the unconditional sort. `np.argsort`
is called every invocation, regardless of whether the strikes are
already sorted (which, for the live caller, they will normally be — the
strike grid handed to `Pricer.reprice_market` at `engine/pricer.py:80`
is unmodified by the model and stamped onto the output at
`models/gbm.py:97-99`). The sort is the only super-linear step; the
rest is O(n). At the live grid size (n_strikes ≤ 20 for the benchmark
fixture, `benchmarks/harness.py:95`) this is a few hundred comparisons.
The cartography flags this as a fact at
`audit/audit_A_cartography.md:281-284`.

The use of `kind="stable"` (`validation/sanity.py:59`) means the
strike-tie tie-break is by original index; equal strikes therefore land
adjacent in `probs_sorted`, and any positive `diff` between them — i.e.
a model that priced a tie inconsistently — would still be caught. The
choice of `1e-12` as default tolerance (`validation/sanity.py:35`) is
not justified by an inline comment; the spec is silent on its origin.

## 5. Dependencies inbound

Three call sites import this module today.

- **`engine/pricer.py:29`** imports `SanityChecker`.
  `Pricer` declares it as a required field at
  `engine/pricer.py:43` (`sanity: SanityChecker` on a `@dataclass(slots=True)`),
  and invokes it as the last step of `reprice_market` at
  `engine/pricer.py:89`: `self.sanity.check(output, spot=tick.price)`.
  The `spot` passed is the latest Pyth tick price (`tick.price` from
  `engine/pricer.py:59`, the `TickRing.latest()` result), which is also
  the spot fed into `TheoInputs` at `engine/pricer.py:79`. So the
  diagnostic spot in the error message and the spot used to compute the
  output are the same object.
- **`benchmarks/harness.py:30`** imports `SanityChecker`. The
  benchmark fixture default-constructs it at `benchmarks/harness.py:79`
  (`sanity = SanityChecker()`), passes it into a `Pricer` at
  `benchmarks/harness.py:97-104`, and that `Pricer` is then exercised
  by every benchmark in `benchmarks/run.py:118-179`. `benchmarks/run.py`
  itself does not import `SanityChecker` directly (`grep` confirms;
  `benchmarks/run.py` shows only the indirect string "validation +
  alloc" inside a label at `benchmarks/run.py:111`).
- **`tests/test_end_to_end.py:26`** imports `SanityChecker`.
  `_build_pricer` at `tests/test_end_to_end.py:32-48` instantiates it
  with default tolerance at `tests/test_end_to_end.py:39` and threads
  it into a `Pricer`. The end-to-end happy path at
  `tests/test_end_to_end.py:66-88` then runs the full pipeline with the
  comment "monotonic, in [0,1], matching shape — sanity checker ran
  without raising" at `tests/test_end_to_end.py:88` documenting that
  the absence of an exception in this test is the indirect coverage of
  the sanity gate.

`grep -rn "SanityError"` under the repo returns only the six raise
sites inside `validation/sanity.py` (lines 28, 44, 46, 50, 52, 54, 64).
No external module catches `SanityError` by name; no external module
references the `RuntimeError`/`SanityError` type (the only test that
prevents the pricer from raising it does so by feeding a known-good GBM
output into the chain, not by intercepting). This means a `SanityError`
raised in production propagates with no in-tree handler.

## 6. Dependencies outbound

The module has a small, fixed outbound footprint.

- **`numpy`** — `validation/sanity.py:23`. Used for `np.all`,
  `np.isfinite`, `np.argsort`, `np.diff`, `np.argmax` and the dunder
  methods `.shape`, `.ndim`, `.size`, `.min`, `.max`. The import is
  eager (top-level `import numpy as np`); there is no lazy/optional
  branch.
- **`models.base.TheoOutput`** — `validation/sanity.py:25`. Used as a
  type annotation on `check` (`validation/sanity.py:38`) and as the
  carrier whose attributes (`probabilities`, `strikes`, `commodity`)
  are read at `validation/sanity.py:39-41`. The `TheoOutput`
  declaration at `models/base.py:44-52` is `@dataclass(frozen=True,
  slots=True)`, so the local rebinds in `check` are reads against an
  immutable record.
- **`__future__.annotations`** — `validation/sanity.py:21`. Standard
  3.11-compatible deferred-annotation import; it has no runtime
  consequence beyond making the type hint at line 38 non-evaluating
  at function definition time.

The module makes no calls to the standard library beyond the import
machinery, no network calls, no filesystem access, and no logging.
There is no `print`, no `logger`, no `structlog` reference (consistent
with `audit/audit_A_cartography.md:248` which notes `structlog` is
declared in `pyproject.toml:18` but unused everywhere in the code).

## 7. State and side effects

In-process state is one float per `SanityChecker` instance:
`_monotone_tol`, set in `__init__` and never mutated thereafter
(`validation/sanity.py:33-36`). The class is sealed via `__slots__`
(`validation/sanity.py:33`), so attaching new attributes at runtime
would raise `AttributeError`. There is no class-level mutable state
and no module-level mutable state.

Side effects:

- **Disk I/O**: none.
- **Network I/O**: none.
- **Global mutation**: none.
- **Logging**: none.
- **Process exit / signal handling**: none.
- **Threading / asyncio primitives**: none. `check` is synchronous and
  has no `await`.

Ordering assumptions inside `check` are explicit in the gate ordering
described in §4. Two are load-bearing:

1. The `np.all(np.isfinite(probs))` test at
   `validation/sanity.py:51-52` runs *before* the `.min()/.max()` test
   at `validation/sanity.py:53-57`. Without that ordering, a NaN in
   `probs` would propagate through `.min()` (returning NaN), which
   would then short-circuit the `< 0.0` comparison to `False` (NaN
   comparisons are always False), and the range gate would silently
   pass on a NaN array. The current order makes that path
   unreachable.
2. The shape gates at `validation/sanity.py:43-50` run before the
   value gates at `validation/sanity.py:51-68`. Reordering would
   cause `np.isfinite` to operate on a possibly multi-dimensional
   array, which is still well-defined, but the *error message*
   produced would be the value-space message rather than the
   shape-space one — degrading diagnosability for what is properly a
   shape bug.

The module is re-entrant — there is no instance state mutation in
`check` — but no external caller exploits that today. The
`benchmarks/harness.py:79` and `tests/test_end_to_end.py:39` instances
are each single-threaded and held by exactly one `Pricer`.

## 8. Invariants

Invariants the code visibly relies on, each with a citation. These are
behaviours the file enforces or assumes, not behaviours derived from
external prose.

1. **`output.probabilities` and `output.strikes` are numpy arrays with
   `.ndim`, `.shape`, `.size`, `.min`, `.max`, and indexable by
   `np.ndarray[int]`.** The file reads `probs.ndim`
   (`validation/sanity.py:43`), `probs.shape` and `strikes.shape`
   (`validation/sanity.py:44, 45, 47`), `probs.size`
   (`validation/sanity.py:49`), `probs.min()` / `probs.max()`
   (`validation/sanity.py:53, 56`), and `probs[order]` and
   `strikes[order]` (`validation/sanity.py:60, 67`). Anything that
   isn't an ndarray-like would raise `AttributeError` rather than
   `SanityError`. Upstream, `models/gbm.py:97-105` constructs
   `TheoOutput` with `np.empty_like(strikes)` for `probabilities` and
   the strike array stamped into the input
   (`models/gbm.py:87, 99`), so this assumption holds for the only
   live model.
2. **`output.probabilities` is dtype-comparable to `0.0` and `1.0`.**
   The range check at `validation/sanity.py:53` uses Python
   floats; for any numeric numpy dtype this works. The kernel writes
   into a `np.empty_like(strikes)` buffer
   (`models/gbm.py:88`) where `strikes` is forced to `float64` by
   `np.ascontiguousarray(..., dtype=np.float64)` at
   `models/gbm.py:87`, so probabilities are `float64` in practice.
3. **Probabilities of two equal strikes are equal up to FP noise.**
   The stable sort at `validation/sanity.py:59` plus the tolerance at
   `validation/sanity.py:62` together imply that the model is allowed
   to differ by `≤ 1e-12` between equal-strike entries; anything
   larger is reported as non-monotone. There is no comment explaining
   why `1e-12` is the right tolerance for a `float64` probability;
   the GBM kernel's analytical-parity test asserts much tighter than
   that (`tests/test_gbm_analytical.py:50` requires `max_abs_err <
   1e-9` across 1000 random cases) — so the tolerance is loose
   relative to GBM's observed precision, but the file does not
   document the slack.
4. **`spot` (the keyword-only argument) is irrelevant to correctness
   and is used only for diagnostics.** Read from
   `validation/sanity.py:38` (declaration) and `validation/sanity.py:67`
   (single use in an f-string). No other branch references it; no
   comparison is made between `spot` and any element of `strikes` or
   `probs`. So the gate is purely a property of the `TheoOutput`,
   not a relationship between `TheoOutput` and the spot used to
   produce it.
5. **`output.commodity` is a string-like usable in an f-string.**
   `validation/sanity.py:41` rebinds it to `name`; every error message
   embeds `f"{name}: ..."` (`validation/sanity.py:44, 47, 50, 52, 54,
   65`). `models/base.py:46` declares `commodity: str` on the dataclass.
6. **The model has already validated *input* strikes for finiteness
   and positivity.** The sanity check never re-tests
   `np.isfinite(strikes)` or `strikes > 0`, which means it relies on
   `models/gbm.py:84` (`if np.any(~np.isfinite(inputs.strikes)) or
   np.any(inputs.strikes <= 0.0)`) running first. If a future model
   fails to enforce the same input gate, a NaN in `strikes` would
   be passed to `np.argsort` at `validation/sanity.py:59`, and
   numpy's argsort behaviour on NaN is implementation-defined (NaNs
   sort to the end, but the resulting `diffs` would still pass through
   without re-raising here). The sanity check has no defence for
   that case.
7. **`models/base.py:60-67` is the only contract for what `price`
   returns.** Specifically, `models/base.py:64` ("be monotone
   non-increasing in strike (enforced by validation/sanity)") names
   this module as the enforcer. `models/base.py:65` ("satisfy
   `P(S_T > K) + P(S_T <= K) = 1` exactly") is *not* enforced here —
   it is "automatic by construction" per
   `validation/sanity.py:11-14`.

## 9. Error handling

Every failure path raises; no path catches.

- **Type of error raised**: `SanityError` only
  (`validation/sanity.py:44, 46, 50, 52, 54, 64`). `SanityError` extends
  `RuntimeError` (`validation/sanity.py:28-29`).
- **What `check` catches**: nothing. There is no `try`/`except` in the
  file.
- **Caller-side handling**: the only live caller, `engine/pricer.py:89`,
  invokes `self.sanity.check(output, spot=tick.price)` outside any
  `try`/`except` block. So `SanityError` propagates out of
  `Pricer.reprice_market` to whoever called the pricer. No call site
  in the repo intercepts it.
- **Failure-mode shapes (verbatim from `validation/sanity.py:43-68`)**:
  - 1-D check fail: `f"{name}: probabilities must be 1-D, got shape
    {probs.shape}"` (`validation/sanity.py:44`).
  - shape mismatch: `f"{name}: strike/prob shape mismatch
    ({strikes.shape} vs {probs.shape})"` (`validation/sanity.py:46-48`).
  - empty: `f"{name}: empty output"` (`validation/sanity.py:50`).
  - non-finite: `f"{name}: non-finite probabilities"`
    (`validation/sanity.py:52`).
  - out-of-range: `f"{name}: probabilities out of [0,1]
    (min={probs.min():.6g}, max={probs.max():.6g})"`
    (`validation/sanity.py:54-57`).
  - non-monotone: `f"{name}: non-monotone theo at sorted index {bad}:
    p[{bad+1}] - p[{bad}] = {diffs[bad]:.3e} (tol
    {self._monotone_tol:.1e}); spot={spot},
    strike_pair=({strikes[order][bad]}, {strikes[order][bad + 1]})"`
    (`validation/sanity.py:64-68`).
- **No wrapping / chaining**: every raise is a fresh `SanityError(...)`
  with no `from` clause; the file contains no nested raise that would
  shadow a different exception class.

The audit document for the pricer notes the same propagation observation
at `audit/audit_B_engine-pricer.md:355` and flags the policy ambiguity at
`audit/audit_B_engine-pricer.md:532-535` (whether `SanityError` should be
allowed to propagate to the publish layer is unanswered by the code).

## 10. Test coverage

There is no `tests/test_sanity.py`, `tests/test_validation.py`, or any
file that imports `SanityError` (`Glob` for `tests/test_*sanity*` and
`tests/test_validation*` returns no matches; `grep -rn "SanityError"`
across the tree returns only the raise sites inside the module itself).

What exists today:

- **Indirect happy-path coverage** — `tests/test_end_to_end.py:66-88`.
  The end-to-end test builds a real `Pricer` with a default-constructed
  `SanityChecker` (`tests/test_end_to_end.py:39`), drives a single
  reprice through the live GBM kernel, and asserts the probability
  vector matches the analytical Black-Scholes reference at
  `tests/test_end_to_end.py:84`. The trailing comment at
  `tests/test_end_to_end.py:88` ("monotonic, in [0,1], matching shape —
  sanity checker ran without raising") is the only in-tree statement of
  intent for what the sanity step proved. The test cannot distinguish
  "sanity ran and approved" from "sanity ran and skipped silently"
  beyond noting that the test reaches the post-`reprice_market`
  assertions; if `SanityChecker.check` were a no-op, this test would
  still pass.
- **Indirect failure-matrix coverage** — `tests/test_end_to_end.py:91-163`
  exercises stale-tick (`StaleDataError`), insufficient-publishers,
  missing-IV, missing-basis, missing-tick, and stub-commodity paths.
  None of these are sanity-side failures; they all raise *before*
  `model.price` is called.
- **Boundary / monotonicity coverage at the model level** —
  `tests/test_gbm_analytical.py:53-71` directly asserts GBM is monotone
  non-increasing and hits the limits `K → 0 ⇒ 1` and `K → ∞ ⇒ 0`. The
  sanity module's docstring at `validation/sanity.py:14-18` defers to
  this test by name as the carrier of those invariants.
- **Indirect benchmark exercise** — `benchmarks/run.py:118-179` and
  `tests/test_benchmarks.py:55-88` route through `Pricer.reprice_market`
  and therefore through `sanity.check`. The benchmark label at
  `benchmarks/run.py:111` ("validation + alloc") is an aggregate cost
  measurement; the module itself is not isolated.

What is **not** tested anywhere in the repo:

- The five raise paths individually (`validation/sanity.py:44, 46, 50,
  52, 54, 64`). No test feeds a hand-crafted `TheoOutput` with `probs >
  1`, `probs < 0`, NaN, mismatched shape, empty, or non-monotone arrays
  to `SanityChecker.check`. The default tolerance `1e-12`
  (`validation/sanity.py:35`) is therefore not covered by any
  edge-case test.
- The `monotone_tol` argument to `__init__` (`validation/sanity.py:35`).
  No test instantiates `SanityChecker(monotone_tol=...)` with a
  non-default value; only `SanityChecker()` is observed
  (`tests/test_end_to_end.py:39`, `benchmarks/harness.py:79`).
- The `n == 1` short-circuit at `validation/sanity.py:62`
  (`if diffs.size and ...`). The only single-strike call path,
  `tests/test_end_to_end.py:91-147`, all raise *before* reaching
  `sanity.check`, so the live single-strike sanity-pass path is not
  observed end-to-end either. The benchmark fixture pins `n_strikes=20`
  (`benchmarks/harness.py:69, 95`).
- The stable-sort tie path: no test feeds repeated strikes.

Mocks: none. The module has no I/O, so there is nothing to mock; tests
either hand it real arrays via the pricer or do not exercise it at all.

## 11. TODOs, bugs, and smells

Literal `TODO`, `FIXME`, `XXX`, `HACK` markers in `validation/`:
`grep -rn "TODO|FIXME|XXX|HACK"` returns no matches under the
`validation/` directory. The same `grep` returns no matches across all
`*.py` files in the repo. So there are no source-level open-marker
comments to cite.

Commented-out blocks: none in `validation/sanity.py`. Every line in the
file is either docstring, import, definition, or active code.

Structural observations the file itself surfaces (each cited in code):

1. **Per-call sort regardless of input order** — `validation/sanity.py:59`
   does `np.argsort(strikes, kind="stable")` on every invocation. The
   strike grid passed by the pricer is the array the caller supplied at
   `engine/pricer.py:80`, stamped onto the output at `models/gbm.py:97-99`;
   it is never re-ordered or mutated upstream. So if the caller already
   passed strikes sorted, the sort is unconditional work.
   `audit/audit_A_cartography.md:281-284` lists the same observation.
2. **`spot` argument unused except in error string** —
   `validation/sanity.py:38` declares `spot: float` keyword-only;
   `validation/sanity.py:67` is the only use. There is no inline
   comment noting the diagnostic-only role; a future reader reading
   only the signature could plausibly assume `spot` is part of the
   gate logic.
3. **Tolerance value undocumented** — `validation/sanity.py:35` defaults
   `monotone_tol=1e-12` with no inline justification, no spec citation,
   and no test that pins the choice.
4. **Module name `validation` is broader than the file** —
   `pyproject.toml:32` includes the package as `validation*`, and the
   README at `README.md:44` describes `validation/` as "Backtest,
   Pyth↔CME reconciliation, pre-publish sanity checks". Only the third
   exists in code today; the cartography notes the same gap at
   `audit/audit_A_cartography.md:81-83` ("README implies more lives
   here … it does not"). The package's `__init__.py` is empty (0
   lines, confirmed via Read warning and `wc -l`).
5. **Shape-message ordering** — `validation/sanity.py:43-48` reports
   "probabilities must be 1-D" before "shape mismatch". A `(n, 1)`
   probs vs `(n,)` strikes pair triggers the 1-D message rather than
   the more informative shape-mismatch message. Not a bug — both are
   valid SanityError signals — but a future reader debugging a 2-D
   bug would never see the cross-array shape line.
6. **No defence against NaN in `strikes`** — `validation/sanity.py:51`
   tests finiteness on `probs` only. If a future model contract
   forwards a NaN strike from upstream, `np.argsort`
   (`validation/sanity.py:59`) places NaNs at the end and the monotone
   check still proceeds; the NaN never raises here. The current GBM
   model rejects this upstream at `models/gbm.py:84`, so the gap is
   latent.
7. **Single failure-mode error type** — `SanityError`
   (`validation/sanity.py:28-29`) is one type for six distinct
   failure shapes. Callers cannot programmatically distinguish
   "shape bug" from "non-monotone" from "out of range" without
   parsing the message string.
8. **Missing `__all__` and empty `validation/__init__.py`** — symbols
   are exported only by virtue of leaving them unprefixed
   (`validation/sanity.py:28, 32`); the package marker contributes
   nothing.

## 12. Open questions

Things the code does not reveal and that would require asking a
maintainer:

1. **What is the intended publish-time policy on `SanityError`?**
   `engine/pricer.py:89` lets it propagate; nothing catches it
   anywhere in the repo. Whether the publish layer (which does not
   exist in code) is expected to drop a quote, suspend a market,
   page someone, or restart the model is not specified. The
   `audit_B_engine-pricer.md:532-535` audit lists the same
   ambiguity.
2. **Why `1e-12` for `monotone_tol`?** `validation/sanity.py:35` does
   not justify it. The GBM analytical-parity test asserts `max_abs_err
   < 1e-9` across 1000 random cases (`tests/test_gbm_analytical.py:50`)
   and the per-case threshold is `1e-6`
   (`tests/test_gbm_analytical.py:44`). The sanity tolerance is three
   orders of magnitude tighter than the per-case GBM tolerance and
   three orders looser than the aggregate GBM tolerance — neither is
   directly the right comparator, and there is no spec citation in
   the file linking the choice to the model's known precision.
3. **Is the `spot` argument intended to grow into a gate condition?**
   It is keyword-only (`validation/sanity.py:38`) and used only in a
   diagnostic message (`validation/sanity.py:67`). A keyword-only
   argument with a single in-file use is a slightly heavyweight
   signature for a pure-diagnostic field; whether the maintainer
   intended a future check (e.g., "ITM strike has prob ≥ 0.5"
   inequality) is unclear.
4. **Should the module also validate `strikes`?** Today the module
   reads `strikes` only to sort it (`validation/sanity.py:59`) and
   to slice it for the error message
   (`validation/sanity.py:67`). There is no `np.isfinite(strikes)`
   or `strikes > 0` test. Whether the maintainer relies on the model
   to have done that, or whether the sanity layer is the canonical
   defence-in-depth tier, is not documented in the file.
5. **Was the `validation/` package intended to host more than this
   file?** `README.md:44` lists three responsibilities; only "pre-publish
   sanity checks" exists in code. Whether "Backtest" and "Pyth↔CME
   reconciliation" were removed, deferred, or are housed elsewhere is
   not derivable from the source.
6. **Is the empty `validation/__init__.py` deliberate, or was an
   `__all__` re-export intended?** The module exports `SanityChecker`
   and `SanityError` only via the fully qualified path. There is no
   single-line "facade" import that would let `from validation import
   SanityChecker` work; every observed import uses `from
   validation.sanity import ...`.
7. **Is the per-call sort considered acceptable for the latency
   budget at scale?** The cartography surfaces it at
   `audit/audit_A_cartography.md:281-284` as a fact for later phases.
   The benchmark suite covers `n_strikes=20`
   (`benchmarks/harness.py:95`) but does not stress the sort in
   isolation, and `tests/test_benchmarks.py:55-88` budgets the whole
   pipeline rather than the sanity step. Whether the maintainer has a
   number in mind for the sanity step's individual budget is not
   visible.
8. **What is the contract under repeated strikes?** The stable-sort
   choice (`validation/sanity.py:59`) suggests duplicates are
   permitted, and the tolerance (`validation/sanity.py:62`) gives
   them slack to differ slightly. But no test or comment confirms
   that the live caller may pass duplicate strikes.

---

**Citations summary** (≥ 10 required, this document contains 60+
distinct `path:line(-line)` references). The load-bearing ones:
`validation/sanity.py:1-19, 21, 23, 25, 28-29, 32-36, 38, 39-41, 43-44,
45-48, 49-50, 51-52, 53-57, 59-68`; `models/base.py:44-52, 55-69`;
`engine/pricer.py:29, 43, 89`; `benchmarks/harness.py:30, 79`;
`tests/test_end_to_end.py:26, 39, 88`; `tests/test_gbm_analytical.py:44,
50, 53-71`; `tests/test_benchmarks.py:55-88`; `models/gbm.py:84, 87,
88, 97-105`; `pyproject.toml:32`; `README.md:44`;
`audit/audit_A_cartography.md:81-83, 225, 281-284`;
`audit/audit_B_engine-pricer.md:355, 532-535`.
