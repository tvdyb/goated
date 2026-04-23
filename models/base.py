"""Abstract pricing interface.

Every per-commodity model implements `Theo.price(TheoInputs) -> TheoOutput`.
The contract: given an immutable snapshot (commodity, spot, strikes, tau,
sigma, basis_drift, tick provenance), return `P(S_T > K)` for each strike,
along with enough provenance to reconstruct the calculation later.

Design notes
------------
`sigma` and `basis_drift` live on `TheoInputs` (not on the model instance)
because the spec draws them from per-call state (IV surface, basis model)
that updates faster than calibration. Calibration-time params that DO live
on the model (jump intensity, regime vols, point-mass distribution) will
be added on model-specific subclasses when those families are implemented.

Hot-path constraints the interface enforces:
  * strikes arrive as a numpy array — callers must not loop in Python
  * TheoInputs is frozen so the same snapshot can't be mutated mid-repricing
  * TheoOutput carries `source_tick_seq` and `params_version` so every
    published theo is traceable to its driving tick and calibration vintage
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

import numpy as np


@dataclass(frozen=True, slots=True)
class TheoInputs:
    commodity: str
    spot: float
    strikes: np.ndarray
    tau: float
    sigma: float
    basis_drift: float = 0.0
    as_of_ns: int = 0
    source_tick_seq: int = -1


@dataclass(frozen=True, slots=True)
class TheoOutput:
    commodity: str
    strikes: np.ndarray
    probabilities: np.ndarray
    as_of_ns: int
    source_tick_seq: int
    model_name: str
    params_version: str


class Theo(ABC):
    model_name: ClassVar[str]

    @abstractmethod
    def price(self, inputs: TheoInputs) -> TheoOutput:
        """Return `P(S_T > K)` for each strike.

        Implementations MUST:
          * return probabilities in [0, 1]
          * be monotone non-increasing in strike (enforced by validation/sanity)
          * satisfy `P(S_T > K) + P(S_T <= K) = 1` exactly
          * raise on invalid inputs (tau<=0, spot<=0, non-positive strikes,
            sigma<=0, stale state, etc.) rather than return a wrong theo
        """
        raise NotImplementedError
