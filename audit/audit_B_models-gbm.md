# Audit Phase B — `models-gbm`

Cross-checked against `audit/audit_A_cartography.md:220`. The Phase A
inventory row for slug `models-gbm` lists exactly one file —
`models/gbm.py`, ~105 LoC — and tags the module as the "Numba-JITed
`P(S_T > K) = Φ(d₂)` kernel plus a `GBMTheo` wrapper that validates
inputs and stamps provenance; currently the only live model." The file
in scope matches; no mismatch.

The module name on disk (`models/gbm.py`) and the Phase A slug
(`models-gbm`) imply the boundary is "the GBM pricing implementation
itself, including both its raw kernel function and its `Theo` adapter."
Other files inside `models/` (`base.py`, `registry.py`) are scoped to
their own Phase A entries (`models-interface` at line 219 and
`models-registry` at line 221) and are therefore treated here as
upstream/downstream callers, not as part of the module.

`models/__init__.py` is the empty placeholder referenced by
`audit/audit_A_cartography.md:209-211` ("excluding empty `__init__.py`
files"); it contributes 0 lines and re-exports nothing.

---

## 1. Module identity

- **Files**: `models/gbm.py` (the only Python file in scope).
- **Total LoC**: 105 (file ends at `models/gbm.py:105`; trailing blank
  line at 106 not counted).
- **Summary**: A two-symbol arithmetic module. The first symbol
  (`_gbm_prob_above` at `models/gbm.py:26-42`) is a numba-JIT'd kernel
  that computes the closed-form lognormal upper-tail probability
  `Φ(d₂)` for a numpy array of strikes, writing into a caller-allocated
  output buffer. The second symbol (`GBMTheo` at `models/gbm.py:60-105`)
  is a frozen dataclass that adapts that kernel to the abstract `Theo`
  contract: it validates every input on the boundary, allocates a
  contiguous float64 output buffer, dispatches to the kernel, and
  packages the result into a `TheoOutput` with provenance. A small
  pure-function adapter (`gbm_prob_above` at `models/gbm.py:45-57`)
  exists for benchmarks and tests that want to skip the validation
  overhead of `GBMTheo.price` but still get a heap-allocated result
  array. The module declares no module-level state beyond a precomputed
  `_INV_SQRT2 = 0.7071067811865476` constant at `models/gbm.py:23`.

## 2. Responsibility

Inferred from the code, the module solves three problems on the hot
path:

1. **Compute the GBM upper-tail probability for a strike grid.**
   The arithmetic at `models/gbm.py:35-42` is a direct transcription of
   the formulas in the docstring header (`models/gbm.py:1-10`):
   `F = spot * exp(basis_drift * tau)`,
   `d₂ = (ln(F/K) − ½σ²τ) / (σ√τ)`,
   `P(S_T > K) = Φ(d₂) = ½ · erfc(−d₂/√2)`. The kernel performs no
   table lookup, no series expansion, and no fallback path — every
   strike runs the same six floating-point operations.
2. **Hold the validation boundary so the hot path can stay
   numerics-only.** `GBMTheo.price` at `models/gbm.py:69-86` runs six
   distinct argument checks (positive finite τ, positive finite spot,
   positive finite σ, finite drift, 1-D strikes, non-empty strikes,
   strikes finite and positive) before any arithmetic. The numba kernel
   itself has no defensive checks; it trusts that everything reaching
   it has been gate-validated.
3. **Stamp provenance onto the output.** `models/gbm.py:97-105`
   propagates `commodity`, `as_of_ns`, `source_tick_seq` (set upstream
   by the pricer) and adds `model_name` and `params_version` (owned by
   the model instance). This is the only place that `model_name="gbm"`
   gets stitched into a `TheoOutput`, and the only place
   `params_version` (whose default is `"v0"` per `models/gbm.py:66`)
   travels off the model instance into a record the caller sees.

The module owns no I/O, no scheduling, no state, and no orchestration —
those concerns live in `engine/pricer.py` and the `state/` modules.
What lives here is the closed-form math plus a thin adapter that meets
the `Theo` contract.

## 3. Public interface

The module exposes three names (no `__all__`, so any non-underscore
identifier is publicly reachable; the leading-underscore kernel is
nonetheless imported and used by other modules — see §5):

- **`_gbm_prob_above(spot, strikes, tau, sigma, basis_drift, out) -> None`**
  — `models/gbm.py:26-42`. The numba `@njit(cache=True, fastmath=False)`
  kernel. Writes `n_strikes` probabilities into the caller-supplied
  `out` array and returns `None`. `cache=True` persists the compiled
  binary across processes; `fastmath=False` preserves IEEE 754
  semantics, matching the `scipy.special.ndtr` reference path used by
  the parity test (`tests/_bs_reference.py:21-26`). Accessing this
  symbol from outside the module is intentional in benchmarks
  (`benchmarks/harness.py:25`, `benchmarks/run.py:27`,
  `tests/test_benchmarks.py:29`); the leading underscore signals
  "kernel — bring your own buffer," not "private."
- **`gbm_prob_above(spot, strikes, tau, sigma, basis_drift=0.0) -> np.ndarray`**
  — `models/gbm.py:45-57`. Pure-function wrapper. Coerces strikes to a
  contiguous float64 array (`models/gbm.py:54`), allocates an output
  buffer of the same shape (`models/gbm.py:55`), and calls the kernel.
  Used by the BS parity tests (`tests/test_gbm_analytical.py:35,57,66,
  70,76,86`) and by benchmark warm-up (`benchmarks/harness.py:55`).
  Docstring at lines 52-53 explicitly calls out: "For the hot path
  prefer the in-place `_gbm_prob_above` kernel with a preallocated
  buffer."
- **`GBMTheo(params_version: str = "v0")`** — `models/gbm.py:60-66`.
  A `@dataclass(frozen=True, slots=True)` subclass of `Theo`
  (`models/base.py:55-69`). The `frozen=True` flag forbids attribute
  reassignment after construction; `slots=True` forbids adding new
  attributes and slightly reduces per-attribute access cost. The class
  carries one field — `params_version: str = "v0"` — plus the class
  variable `model_name: ClassVar[str] = "gbm"` at line 67 (which
  satisfies the `Theo.model_name: ClassVar[str]` declaration in
  `models/base.py:56`).
- **`GBMTheo.price(self, inputs: TheoInputs) -> TheoOutput`** —
  `models/gbm.py:69-105`. The abstract method from
  `models/base.py:58-69`. Validates `inputs`, dispatches to
  `_gbm_prob_above` with a freshly allocated output buffer, and
  returns a `TheoOutput`. Raises `ValueError` (never any other
  exception type) on every invalid-input path.

The constant `_INV_SQRT2` at `models/gbm.py:23` is module-private and
referenced only by the kernel at line 42; it is precomputed once so the
kernel does not call `math.sqrt(2.0)` per strike. No other constants,
helpers, or classes are defined in the file.

## 4. Internal structure

The data flow inside `GBMTheo.price` is strictly linear:

```
inputs ──► validate (6 gates)  ──► coerce strikes to contig float64
                                ──► allocate `out` buffer
                                ──► _gbm_prob_above(spot, strikes, tau,
                                                    sigma, basis_drift, out)
                                ──► TheoOutput(commodity, strikes, out, ...)
```

The validation gates at `models/gbm.py:70-85` execute in fixed order
and short-circuit on the first failure. They are written using
`if not (x > 0.0) or not math.isfinite(x)` rather than the more obvious
`if x <= 0.0 or not math.isfinite(x)`; the bracketed-positive form
correctly rejects `nan` (where both `x > 0.0` and `x <= 0.0` are
`False`), so the two halves of each guard are not redundant.

The kernel at `models/gbm.py:35-42` hoists three quantities outside the
per-strike loop: `forward = spot * exp(basis_drift * tau)` at line 35,
`sigma_sqrt_tau = sigma * sqrt(tau)` at line 36, and
`half_variance = 0.5 * sigma * sigma * tau` at line 37. Inside the
loop, only one log, one division, one multiplication, and one
`math.erfc` per strike happen — five FLOPs per strike on the hot loop.
The loop uses `range(n)` over `strikes.shape[0]` (line 38) and indexes
strikes one at a time (`k = strikes[i]` at line 40) rather than
operating on the array as a whole; this is exactly the pattern numba
specializes for tight scalar loops on contiguous arrays.

`GBMTheo.price` re-coerces `inputs.strikes` via
`np.ascontiguousarray(inputs.strikes, dtype=np.float64)` at
`models/gbm.py:87`, even though `engine/pricer.py:80` already coerces
the same array before constructing the `TheoInputs`. Both calls are
present; the model does not assume the upstream coercion.
`audit_B_engine-pricer.md:292-294` flags this re-coercion as a fact for
later phases; from this side, the explicit re-coerce is defensive — the
kernel's pointer-arithmetic indexing requires contiguous memory, and
the model does not trust callers to honour that.

The output allocation at `models/gbm.py:88` (`np.empty_like(strikes)`)
returns a fresh buffer per `price()` call. There is no buffer reuse
across calls; the `Theo` interface offers no place to thread in a
caller-owned `out` array, so every call allocates two arrays (the
re-coerced strikes copy at line 87 and the result buffer at line 88).
This is consistent with the docstring at lines 52-53 which steers the
hot path *away* from `GBMTheo.price` and toward the in-place kernel.

The `gbm_prob_above` adapter at `models/gbm.py:45-57` performs the
same coercion + allocation pair as `GBMTheo.price` but skips the six
validation gates. It exists to give tests and benchmarks an
allocation-friendly API without paying for input checks that the test
inputs already satisfy.

## 5. Dependencies inbound — who calls this module

A grep over the repository (`gbm|GBM|GBMTheo|gbm_prob_above|_gbm_prob_above`)
returns the following call sites that resolve to symbols defined here.

- **Registry builder** — `models/registry.py:21` imports `GBMTheo`,
  and `models/registry.py:33` registers a builder
  `lambda cfg: GBMTheo(params_version=cfg.raw.get("params_version", "v0"))`
  in the `_MODEL_BUILDERS` dispatch table for the model name `"gbm"`.
  This is the only path through which production code constructs a
  `GBMTheo`. The builder reads `params_version` from the per-commodity
  YAML; `config/commodities.yaml` does not currently declare that key
  for any commodity, so every commodity registered as `"gbm"` ends up
  with `params_version="v0"` (the default at `models/gbm.py:66`).
- **Hot-path pricer** — `engine/pricer.py:87-88` calls
  `self.registry.get(commodity)` and then `model.price(inputs)`. The
  upstream `Pricer.reprice_market` is the only production caller of
  `GBMTheo.price`. `engine/pricer.py:23` imports `TheoInputs,
  TheoOutput` (the contract types this module returns and consumes),
  but does not import the `GBMTheo` class directly — dispatch is
  registry-mediated.
- **End-to-end tests** — `tests/test_end_to_end.py:19` imports
  `GBMTheo`, `tests/test_end_to_end.py:53`
  asserts `isinstance(registry.get("wti"), GBMTheo)`, and
  `tests/test_end_to_end.py:86` asserts the returned
  `out.model_name == "gbm"`. These tests do not call `GBMTheo`
  directly; they exercise the registry → pricer → model path and
  introspect the result.
- **Analytical parity tests** — `tests/test_gbm_analytical.py:16`
  imports `gbm_prob_above` and `tests/test_gbm_analytical.py:95`
  imports `GBMTheo`. The five exported tests (lines 20, 53, 64, 74,
  82, 93) all reach into the kernel via the pure-function adapter,
  except `test_gbm_invalid_inputs_raise` (line 93) which uses the
  validating wrapper.
- **Benchmark harness** — `benchmarks/harness.py:25` imports
  `_gbm_prob_above` and `gbm_prob_above`; `benchmarks/harness.py:50-55`
  defines `warm_kernel()` that calls both to force numba JIT
  compilation before any timing. The synthetic config at
  `benchmarks/harness.py:60-66` declares `"model": "gbm"` for every
  synthetic market, so the registry path also exercises the GBM
  builder during benchmark setup.
- **Benchmark runner** — `benchmarks/run.py:27` imports
  `GBMTheo, _gbm_prob_above`; `benchmarks/run.py:89` calls the kernel
  inside `bench_kernel_varying_strikes`, and `benchmarks/run.py:99-115`
  constructs a fresh `GBMTheo()` (no `params_version` override) and
  times `model.price(inputs)` against a 50µs budget at line 114.
- **Benchmark budget tests** — `tests/test_benchmarks.py:29` imports
  `_gbm_prob_above`; `tests/test_benchmarks.py:38` times the kernel at
  20 strikes against a 10µs budget at line 40. The companion test at
  line 55 (`test_gbm_price_under_50us_per_market`) routes through
  `bench_model_price_api` from the runner and re-asserts the 50µs
  budget on `GBMTheo.price`.

No other live module references either `GBMTheo` or the kernel. The
README references at lines 13-16, 30, and 41 are documentation
artifacts of the published latency snapshot and the model-family roster
and do not run code.

## 6. Dependencies outbound — what this module calls

- **Standard library** —
  `from __future__ import annotations` (`models/gbm.py:12`),
  `math` (`models/gbm.py:14`, used at lines 35, 36, 42, 70, 72, 74, 76),
  `dataclasses.dataclass` (`models/gbm.py:15`), and
  `typing.ClassVar` (`models/gbm.py:16`). Inside the numba kernel
  (`models/gbm.py:35-42`) the `math` calls are: `math.exp`, `math.sqrt`,
  `math.log`, and `math.erfc`. Numba lowers these to LLVM intrinsics —
  the kernel does not actually call into CPython at runtime.
- **`numpy`** — imported at `models/gbm.py:18`, used at lines 29, 33
  (type hints in the kernel signature; numba reads the annotations to
  infer the JIT signature), 47, 54, 55, 84, 87, 88. The only numpy
  surface area touched is `np.ascontiguousarray`, `np.empty_like`,
  `np.any`, `np.isfinite`, and `np.ndarray` as a type. There are no
  vectorized numpy operations in the kernel itself; the per-strike
  loop is an explicit `for i in range(n)`.
- **`numba.njit`** — imported at `models/gbm.py:19`, applied at line 26
  with `cache=True, fastmath=False`. Numba is a hard import (no
  try/except, no lazy import), so the module fails to load on a
  partial install where numba is missing. `pyproject.toml:11`
  (per `audit/audit_A_cartography.md:18-29`) declares
  `numba >= 0.59` as a runtime dependency.
- **`models.base`** — `models/gbm.py:21` imports `Theo, TheoInputs,
  TheoOutput`. `Theo` is the ABC that `GBMTheo` subclasses (line 61);
  `TheoInputs` is the immutable input snapshot the model consumes
  (line 69 signature); `TheoOutput` is the immutable output record the
  model returns (line 97). The contract those three types impose is
  documented in the `models/base.py:1-21` docstring.

The module touches no I/O subsystems (no file read/write, no network,
no logging, no `time`-related calls), no global state, no environment
variables, no on-disk config, and no clock. Everything that flows
through it is on the call stack.

## 7. State and side effects

- **Process-level state introduced by the module**: the numba JIT
  cache. `@njit(cache=True)` at `models/gbm.py:26` instructs numba to
  persist the compiled binary to disk under `__pycache__/` next to the
  source file. After first compilation, subsequent process starts
  reuse the cached object. There is no in-memory state owned by the
  module: no module-level mutable dict, list, or counter. The only
  module-level value, `_INV_SQRT2` at line 23, is a `float` literal.
- **Disk I/O**: only the implicit numba JIT-cache write on first
  compile under `__pycache__/`. No reads, no writes from the
  `models/gbm.py` module itself.
- **Network I/O**: none.
- **Per-call state**: `GBMTheo.price` allocates two heap arrays per
  invocation — the contiguous strikes copy at `models/gbm.py:87` and
  the output buffer at `models/gbm.py:88`. Both arrays escape into the
  returned `TheoOutput` (the strikes copy is the value bound to
  `TheoOutput.strikes` at line 99; the `out` buffer becomes
  `TheoOutput.probabilities` at line 100). Once returned, the model
  retains no reference.
- **Mutation of inputs**: none. `TheoInputs` is `frozen=True` at
  `models/base.py:32` so attempting mutation would raise
  `FrozenInstanceError`. The model treats `inputs.strikes` as read-only
  and never writes through the original reference; the work happens
  on the contiguous copy at line 87.
- **Ordering assumptions**: the validation gates at `models/gbm.py:70-85`
  fire in source order. Every gate is independent; there is no gate
  whose check assumes a previous gate's value. The kernel's three
  precomputed quantities at lines 35-37 must be computed before the
  per-strike loop at lines 38-42, which is the file's only intra-call
  ordering invariant.

## 8. Invariants

Each invariant below is paired with a citation to the code that
enforces or relies on it.

1. **`tau > 0` and finite, `spot > 0` and finite, `sigma > 0` and
   finite, `basis_drift` finite.** Enforced explicitly at
   `models/gbm.py:70-77`. The kernel at lines 35-37 would silently
   produce `inf`/`nan` for `tau ≤ 0` (sqrt of non-positive) or `sigma
   == 0` (division by zero in `d2`); the boundary check makes that
   unreachable.
2. **Strikes are 1-D, non-empty, finite, and strictly positive.**
   Enforced at `models/gbm.py:78-85`. The `math.log(forward / k)` term
   at line 41 requires `k > 0` for a finite result, and the kernel's
   indexing pattern (`strikes[i]` at line 40) requires 1-D contiguous
   memory. Multidimensional or zero-length arrays are rejected before
   the kernel sees them.
3. **`GBMTheo` instances are immutable.** Enforced by
   `@dataclass(frozen=True, slots=True)` at `models/gbm.py:60`.
   `params_version` (the only instance attribute) cannot be reassigned
   after construction, and no new attributes can be added.
4. **`model_name == "gbm"`.** Declared as a `ClassVar` at
   `models/gbm.py:67`. Required by the abstract base
   (`models/base.py:56`) and asserted by `tests/test_end_to_end.py:86`
   on the live output.
5. **The kernel writes exactly `strikes.shape[0]` values to `out`.**
   Implicit: the loop at `models/gbm.py:38-42` uses
   `n = strikes.shape[0]` and `for i in range(n): out[i] = ...`. The
   caller is responsible for sizing `out` accordingly; both internal
   call sites (`models/gbm.py:55, 88`) use `np.empty_like(strikes)`
   which guarantees a matching shape. External call sites that build
   their own buffer (e.g. `benchmarks/run.py:86-89`,
   `benchmarks/harness.py:53-54`) all use the same `np.empty_like`
   pattern.
6. **Output is monotone non-increasing in K.** Implicit: `Φ(d₂)` is
   monotone in `d₂`, and `d₂` is monotone-decreasing in `K` because
   `d₂` contains `−ln K` at `models/gbm.py:41`. Tested explicitly by
   `tests/test_gbm_analytical.py:53-61`.
7. **Output lies in [0, 1].** Implicit: `0.5 * erfc(x) ∈ [0, 1]` for
   all real `x`; the formula at `models/gbm.py:42` is the standard CDF
   identity. Tested implicitly via the put-call-parity assertion at
   `tests/test_gbm_analytical.py:74-79` (which checks
   `probs + (1 - probs) == 1.0` exactly, requiring `probs ∈ [0, 1]`),
   and enforced post-hoc by the `SanityChecker` at
   `validation/sanity.py:53-57`.
8. **Numba kernel uses IEEE 754 semantics.** Enforced by
   `fastmath=False` in the `@njit` decorator at `models/gbm.py:26`.
   Without this, numba may reorder floating-point operations or assume
   no `nan`/`inf`, breaking parity with `scipy.special.ndtr` used by
   the reference at `tests/_bs_reference.py:21-26`.
9. **Numba JIT cache enabled.** `cache=True` at `models/gbm.py:26`.
   This ensures cold-start latency is paid once per machine, not once
   per process — relied on by the benchmark suite, which would
   otherwise see the JIT cost masquerade as kernel latency on the first
   call (`benchmarks/harness.py:50-55` warms the kernel anyway, but the
   cache makes that warm-up nearly free on second and later runs).
10. **Provenance fields ride through unchanged.** `as_of_ns,
    source_tick_seq` are copied verbatim from `inputs` to `output` at
    `models/gbm.py:101-102`. `model_name` and `params_version` are
    stamped from the model instance at lines 103-104. The model
    introduces no time stamp of its own; downstream consumers can
    therefore tie the output back to the exact tick that produced it.

## 9. Error handling

Every failure path in this module raises `ValueError` directly from
`GBMTheo.price`. There are no `try`/`except` blocks, no fallback paths,
and no `warnings.warn` calls. All six validation messages embed both
the commodity name and the offending value, which is consistent with
the policy stated in `engine/pricer.py:1-13` ("a wrong theo trades; a
missing theo doesn't") — the module reflects that policy by refusing
to produce a `TheoOutput` whenever the inputs would yield meaningless
arithmetic.

Specifically:

- Non-positive or non-finite `tau`: `models/gbm.py:70-71`.
- Non-positive or non-finite `spot`: `models/gbm.py:72-73`.
- Non-positive or non-finite `sigma`: `models/gbm.py:74-75`.
- Non-finite `basis_drift`: `models/gbm.py:76-77`.
- Strikes not 1-D: `models/gbm.py:78-81`.
- Empty strikes: `models/gbm.py:82-83`.
- Strikes containing `nan`/`inf` or non-positive values:
  `models/gbm.py:84-85`.

The numba kernel itself raises nothing (numba would translate any raw
arithmetic exception into a process-level error rather than a Python
exception) — by the time the kernel runs, the validation guarantees no
arithmetic violation can occur for finite inputs in the declared
ranges. The pure-function adapter `gbm_prob_above` is silent on
invalid inputs: it forwards whatever the caller supplies straight into
the kernel, which is acceptable because every call site of the
adapter is in tests or benchmarks where the inputs are constructed
from known-good ranges.

`tests/test_gbm_analytical.py:93-109` explicitly exercises six of the
seven validation paths via `pytest.raises(ValueError)`: spot=0, tau<0,
sigma=0, strike=0, strike=nan, and strikes shape (2,2). The
`basis_drift` finiteness check at `models/gbm.py:76-77` is not
covered by an explicit test in this module's primary test file.

## 10. Test coverage

The Phase A inventory at `audit/audit_A_cartography.md:176-178` lists
`tests/test_gbm_analytical.py` as the dedicated test file, plus the
end-to-end and benchmark suites that cover GBM in passing.

Direct tests (file: `tests/test_gbm_analytical.py`):

- `test_gbm_matches_bs_analytical_1000_random_cases` (lines 20-50):
  builds 1,000 random `(spot, sigma, tau, basis_drift, strikes)`
  tuples with a fixed seed `0xDEADBEEF` (line 21) and asserts every
  per-strike absolute error vs `bs_prob_above`
  (`tests/_bs_reference.py:14-26`) is below `1e-6` (line 44). It also
  tracks the worst-case across all 1,000 trials and asserts it stays
  below `1e-9` (line 50). The reference uses `numpy` + `scipy.ndtr`,
  so passing this test means the numba kernel matches a different
  numerical path on every random input.
- `test_gbm_monotone_decreasing_in_strike` (lines 53-61): checks
  `np.diff(probs) ≤ 1e-15` over a 400-point linear grid for four
  sigmas and three taus.
- `test_gbm_boundary_limits` (lines 64-71): asserts `theo == 1.0`
  exactly at `K = 1e-12` and `theo == 0.0` exactly at `K = 1e20` for
  spot 100, σ 0.3, τ 0.25.
- `test_gbm_put_call_parity_exact` (lines 74-79): asserts
  `probs + (1 - probs) == 1.0` with no FP slack.
- `test_gbm_atm_forward_theo_near_half` (lines 82-90): with `K = F`
  exactly, asserts the kernel matches the closed form
  `0.5·erfc(½σ√τ · 1/√2)` to within `1e-12`.
- `test_gbm_invalid_inputs_raise` (lines 93-109): exercises six
  validation paths via `pytest.raises(ValueError)`.

Indirect tests (other files exercise the module):

- `tests/test_end_to_end.py:51-87` constructs a real `Registry` from
  the on-disk `config/commodities.yaml`, asserts the WTI entry yields
  a `GBMTheo` (line 53), then routes a real tick through the full
  pricer and compares the result to `bs_prob_above` to `1e-9`
  (line 84). It also asserts the output's `model_name == "gbm"` and
  `source_tick_seq == 1` (lines 86-87). The five failure tests at
  lines 91-147 reach the model only when their preceding gates are
  satisfied; they primarily exercise the pricer's gates rather than
  the model itself.
- `tests/test_benchmarks.py:32-44` budgets the kernel at <10µs for
  20 strikes; `tests/test_benchmarks.py:55-61` budgets `GBMTheo.price`
  at <50µs for 20 strikes. Both run real, un-mocked code.
- `benchmarks/run.py:82-95, 98-115, 130-140` exercise the same
  surfaces under heavier iteration counts when invoked via
  `python -m benchmarks.run`.

Nothing about the module is mocked anywhere in the repository. The
only "fixture" used is the BS reference at `tests/_bs_reference.py`,
which is an independent oracle, not a stand-in for the module under
test. Numba is not stubbed: the JIT compiler runs at test time.

What is not tested:

- The `basis_drift` finiteness gate at `models/gbm.py:76-77` has no
  direct test (the parameter list at
  `tests/test_gbm_analytical.py:99-109` covers spot, tau, sigma,
  strike-zero, strike-nan, strike-shape; not basis_drift).
- The `gbm_prob_above` adapter's behaviour on `inf`/`nan` strikes is
  not exercised — its only callers pass finite arrays. The kernel
  would produce `nan` outputs in that case but not raise.
- `params_version != "v0"` is not exercised. The registry path always
  reads `cfg.raw.get("params_version", "v0")` at
  `models/registry.py:33`, and no entry in `config/commodities.yaml`
  declares the key, so every constructed `GBMTheo` in the test suite
  has `params_version == "v0"`.

## 11. TODOs, bugs, and smells

Literal markers in `models/gbm.py`: a grep for `TODO|FIXME|XXX|HACK`
returns zero matches. The file is comment-light; the only multi-line
prose is the docstring at lines 1-10 and the brief `GBMTheo` note at
lines 62-64.

Structural observations (factual, no recommendations):

- **Underscore-prefixed kernel imported across module boundaries.**
  `_gbm_prob_above` (`models/gbm.py:26`) is imported by
  `benchmarks/harness.py:25`, `benchmarks/run.py:27`, and
  `tests/test_benchmarks.py:29`. The leading underscore is
  conventionally a "private" marker; the actual usage pattern is
  "public, but bring your own buffer." This crosses the same kind of
  boundary as red flag #4 in the cartography
  (`audit/audit_A_cartography.md:251-253`), which calls out the
  benchmarks importing private symbols out of `engine/event_calendar`.
- **Per-call double allocation in `GBMTheo.price`.** Lines 87 and 88
  allocate a contiguous strikes copy and an output buffer on every
  call; there is no buffer pool or caller-supplied `out` channel on
  the `Theo.price` contract (`models/base.py:55-69`). The hot path
  through `engine/pricer.py:88` therefore allocates twice per
  reprice. The benchmark snapshot at `README.md:16` reports
  `GBMTheo.price` p99 ≈ 5µs at 20 strikes; the allocation cost is
  inside that envelope.
- **Re-coercion at the model boundary.** `engine/pricer.py:80`
  produces a contiguous float64 strikes array; `models/gbm.py:87`
  re-coerces. When the strikes array is already contiguous and float64
  (the production case), `np.ascontiguousarray` returns the same
  object, so the second call is cheap — but it is invoked on every
  reprice. The cost is documented in the engine-pricer audit at
  `audit/audit_B_engine-pricer.md:476`.
- **No per-instance `params_version` validation.** The dataclass at
  `models/gbm.py:60-66` accepts any string for `params_version`. The
  registry passes whatever YAML returns from
  `cfg.raw.get("params_version", "v0")` (`models/registry.py:33`).
  An empty string, whitespace, or a non-string YAML value would all
  pass through to `TheoOutput.params_version` without complaint.
- **`Theo` ABC enforces only `model_name` and `price`.** From
  `models/base.py:55-69`. There is no `params_version` slot on the
  base, so other future model families could store calibration
  vintages under a different name without static enforcement. The
  current single-model registry at `models/registry.py:32-38` works
  around this by wiring `params_version` only inside the `"gbm"`
  builder.
- **Numba `@njit(cache=True)` on a function with array arguments.**
  `models/gbm.py:26` enables disk caching, but the cache key includes
  the JIT signature inferred from the first call. The signature at
  the kernel call sites is `(float64, array(float64,1d), float64,
  float64, float64, array(float64,1d)) -> None`. Any caller passing a
  non-`float64` strikes array would trigger a recompile; the four
  internal call sites all coerce to `np.float64` first
  (`models/gbm.py:54, 87`; `benchmarks/run.py:85`;
  `benchmarks/harness.py:52`), so this is invariant in practice but
  not enforced at the kernel boundary.
- **Magic number for `1/√2`.** `_INV_SQRT2 = 0.7071067811865476` at
  `models/gbm.py:23` is a 16-digit literal. The same constant is
  re-used inside `tests/test_gbm_analytical.py:89` as another literal,
  rather than imported from the module. A drift between the two
  literals would silently break the parity test at line 90 (which
  tolerates `1e-12`); the repository currently has them matching
  exactly.

## 12. Open questions

Things the code does not reveal, and which would need a maintainer to
answer before further work on this module:

1. **What populates `params_version` in production?** The registry
   reads `cfg.raw.get("params_version", "v0")` at
   `models/registry.py:33`, but `config/commodities.yaml` declares no
   such key for any commodity. Is `params_version` intended to be set
   from the YAML, from a calibration artifact written into the
   `calibration/params/` folder noted in
   `audit/audit_A_cartography.md:124-126`, or from somewhere else?
2. **Why expose `_gbm_prob_above` (with leading underscore) for
   external use rather than promoting it to a public name?** The
   contract in the docstring at `models/gbm.py:52-53` ("for the hot
   path prefer the in-place `_gbm_prob_above` kernel") is at odds with
   the underscore prefix; the underscore appears to discourage exactly
   the use the docstring recommends.
3. **Is the per-call double allocation in `GBMTheo.price` (lines 87,
   88) considered acceptable for the live path, given the spec
   budget?** The 50µs budget at `tests/test_benchmarks.py:55-61` is
   currently met with ~5µs of headroom (per `README.md:16`), so
   allocation cost is masked, but the `Theo.price` interface offers
   no scratch-buffer hook. Whether this is intentional ("never share
   buffers across reprices, ever") or an unfilled optimisation is not
   evident from the code.
4. **What does the `Theo` interface intend for sigma/drift that is
   stale but not absent?** The model raises immediately on missing
   sigma at the upstream gate (`engine/pricer.py:71`), but if a
   downstream model family wanted to accept stale sigma with a
   degraded vintage tag, the `params_version` mechanism in this
   module is the only available channel. Whether it is meant to carry
   that meaning is unstated.
5. **Why two kernel-level entry points (`_gbm_prob_above` and
   `gbm_prob_above`) instead of one?** Both go through the same numba
   kernel, but the wrapper at lines 45-57 allocates internally while
   the kernel takes a caller `out` buffer. The split looks like a
   deliberate ergonomics decision (test-friendliness vs. hot-path
   friendliness), but no comment makes that intent explicit.
6. **Is `fastmath=False` (line 26) a permanent constraint or an
   interim setting?** The decorator choice currently anchors the
   parity test to `1e-9` worst-case (line 50), but commodity-options
   pricing rarely needs more than `1e-6`. A flip to `fastmath=True`
   would give numba more freedom but would silently break the parity
   guarantee — the code does not record whether the trade was
   considered.
7. **Does `params_version` need to participate in equality / hashing
   for caching downstream?** The dataclass is `frozen=True` (line 60)
   so it is hashable, and `params_version` is the only field, so two
   `GBMTheo("v0")` instances compare equal. Whether downstream
   consumers (e.g. a future per-version theo cache) rely on that is
   not stated.
