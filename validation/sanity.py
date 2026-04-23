"""Pre-publish sanity checks on every `TheoOutput`.

Runs on the hot path, so every check is O(n_strikes) and avoids Python loops.

Enforced invariants (per spec "Validation — must-have before any live trading"):
  * all probabilities are finite
  * all probabilities are in [0, 1]
  * probabilities are monotone non-increasing in K (with FP tolerance)
  * strike and probability arrays have matching shape

Put-call parity for digitals (`P(S_T > K) + P(S_T ≤ K) = 1`) is automatic by
construction — we compute `P(S_T > K)` directly and callers derive
`P(S_T ≤ K) = 1 - P(S_T > K)`. The invariant is tested in `tests/` against
the Black-Scholes reference rather than asserted per call.

Boundary behavior (theo → 1 as K → 0, theo → 0 as K → ∞) is tested offline
against analytical limits — sanity here only checks what's enforceable on
the live strike grid.
"""

from __future__ import annotations

import numpy as np

from models.base import TheoOutput


class SanityError(RuntimeError):
    pass


class SanityChecker:
    __slots__ = ("_monotone_tol",)

    def __init__(self, monotone_tol: float = 1e-12) -> None:
        self._monotone_tol = float(monotone_tol)

    def check(self, output: TheoOutput, *, spot: float) -> None:
        probs = output.probabilities
        strikes = output.strikes
        name = output.commodity

        if probs.ndim != 1:
            raise SanityError(f"{name}: probabilities must be 1-D, got shape {probs.shape}")
        if probs.shape != strikes.shape:
            raise SanityError(
                f"{name}: strike/prob shape mismatch ({strikes.shape} vs {probs.shape})"
            )
        if probs.size == 0:
            raise SanityError(f"{name}: empty output")
        if not np.all(np.isfinite(probs)):
            raise SanityError(f"{name}: non-finite probabilities")
        if probs.min() < 0.0 or probs.max() > 1.0:
            raise SanityError(
                f"{name}: probabilities out of [0,1] "
                f"(min={probs.min():.6g}, max={probs.max():.6g})"
            )

        order = np.argsort(strikes, kind="stable")
        probs_sorted = probs[order]
        diffs = np.diff(probs_sorted)
        if diffs.size and diffs.max() > self._monotone_tol:
            bad = int(np.argmax(diffs))
            raise SanityError(
                f"{name}: non-monotone theo at sorted index {bad}: "
                f"p[{bad + 1}] - p[{bad}] = {diffs[bad]:.3e} (tol {self._monotone_tol:.1e}); "
                f"spot={spot}, strike_pair=({strikes[order][bad]}, {strikes[order][bad + 1]})"
            )
