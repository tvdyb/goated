"""Black-Scholes P(S_T > K) reference for parity tests.

Intentionally uses a different code path than the numba kernel under test:
numpy log/sqrt + `scipy.special.ndtr` vs the kernel's math.log/math.sqrt +
math.erfc. If both match to 1e-6 the kernel is trusted.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr


def bs_prob_above(
    spot: float,
    strikes: np.ndarray,
    tau: float,
    sigma: float,
    basis_drift: float = 0.0,
) -> np.ndarray:
    strikes = np.asarray(strikes, dtype=np.float64)
    forward = spot * np.exp(basis_drift * tau)
    sigma_sqrt_tau = sigma * np.sqrt(tau)
    half_variance = 0.5 * sigma * sigma * tau
    d2 = (np.log(forward / strikes) - half_variance) / sigma_sqrt_tau
    return ndtr(d2)
