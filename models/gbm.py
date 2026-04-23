"""GBM / lognormal digital pricer.

    F  = spot * exp(basis_drift * tau)
    d2 = (ln(F/K) - 0.5 * sigma^2 * tau) / (sigma * sqrt(tau))
    P(S_T > K) = Phi(d2) = 0.5 * erfc(-d2 / sqrt(2))

The inner kernel is numba-njit'd for zero Python overhead per strike. The
wrapper validates inputs at the boundary and raises rather than producing a
wrong theo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
from numba import njit

from models.base import Theo, TheoInputs, TheoOutput

_INV_SQRT2 = 0.7071067811865476  # 1 / sqrt(2)


@njit(cache=True, fastmath=False)
def _gbm_prob_above(
    spot: float,
    strikes: np.ndarray,
    tau: float,
    sigma: float,
    basis_drift: float,
    out: np.ndarray,
) -> None:
    forward = spot * math.exp(basis_drift * tau)
    sigma_sqrt_tau = sigma * math.sqrt(tau)
    half_variance = 0.5 * sigma * sigma * tau
    n = strikes.shape[0]
    for i in range(n):
        k = strikes[i]
        d2 = (math.log(forward / k) - half_variance) / sigma_sqrt_tau
        out[i] = 0.5 * math.erfc(-d2 * _INV_SQRT2)


def gbm_prob_above(
    spot: float,
    strikes: np.ndarray,
    tau: float,
    sigma: float,
    basis_drift: float = 0.0,
) -> np.ndarray:
    """Pure-function entry point for benchmarks and tests. For the hot path
    prefer the in-place `_gbm_prob_above` kernel with a preallocated buffer."""
    strikes = np.ascontiguousarray(strikes, dtype=np.float64)
    out = np.empty_like(strikes)
    _gbm_prob_above(float(spot), strikes, float(tau), float(sigma), float(basis_drift), out)
    return out


@dataclass(frozen=True, slots=True)
class GBMTheo(Theo):
    """Stateless GBM pricer. All per-call params arrive on `TheoInputs`.
    `params_version` identifies the calibration vintage this instance was
    built against — carried through to `TheoOutput` for provenance."""

    params_version: str = "v0"
    model_name: ClassVar[str] = "gbm"

    def price(self, inputs: TheoInputs) -> TheoOutput:
        if not (inputs.tau > 0.0) or not math.isfinite(inputs.tau):
            raise ValueError(f"{inputs.commodity}: tau must be finite and > 0, got {inputs.tau}")
        if not (inputs.spot > 0.0) or not math.isfinite(inputs.spot):
            raise ValueError(f"{inputs.commodity}: spot must be finite and > 0, got {inputs.spot}")
        if not (inputs.sigma > 0.0) or not math.isfinite(inputs.sigma):
            raise ValueError(f"{inputs.commodity}: sigma must be finite and > 0, got {inputs.sigma}")
        if not math.isfinite(inputs.basis_drift):
            raise ValueError(f"{inputs.commodity}: basis_drift must be finite, got {inputs.basis_drift}")
        if inputs.strikes.ndim != 1:
            raise ValueError(
                f"{inputs.commodity}: strikes must be 1-D, got shape {inputs.strikes.shape}"
            )
        if inputs.strikes.size == 0:
            raise ValueError(f"{inputs.commodity}: strikes array is empty")
        if np.any(~np.isfinite(inputs.strikes)) or np.any(inputs.strikes <= 0.0):
            raise ValueError(f"{inputs.commodity}: all strikes must be finite and > 0")

        strikes = np.ascontiguousarray(inputs.strikes, dtype=np.float64)
        out = np.empty_like(strikes)
        _gbm_prob_above(
            float(inputs.spot),
            strikes,
            float(inputs.tau),
            float(inputs.sigma),
            float(inputs.basis_drift),
            out,
        )
        return TheoOutput(
            commodity=inputs.commodity,
            strikes=strikes,
            probabilities=out,
            as_of_ns=inputs.as_of_ns,
            source_tick_seq=inputs.source_tick_seq,
            model_name=self.model_name,
            params_version=self.params_version,
        )
