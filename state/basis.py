"""Pyth ↔ CME basis model.

Deliverable 1 implements a primitive version: a per-commodity annualized
basis drift with staleness tracking. Deliverables 3+ replace this with the
AR(1)-fit model specified in calibration/; the interface here is designed
so that upgrade is additive — callers only see `get(commodity, now_ns)`.

`basis_drift` is annualized so it composes directly with `tau` (years) in
the GBM forward: `F = spot * exp(basis_drift * tau)`.
"""

from __future__ import annotations

import math

from state.errors import MissingStateError, StaleDataError


class BasisModel:
    __slots__ = ("_basis", "_max_staleness_ms")

    def __init__(self, max_staleness_ms: int = 30_000) -> None:
        if max_staleness_ms <= 0:
            raise ValueError(f"max_staleness_ms must be > 0, got {max_staleness_ms}")
        self._basis: dict[str, tuple[float, int]] = {}
        self._max_staleness_ms = max_staleness_ms

    def set(self, commodity: str, basis_drift_annualized: float, ts_ns: int) -> None:
        if not math.isfinite(basis_drift_annualized):
            raise ValueError(
                f"{commodity}: basis_drift must be finite, got {basis_drift_annualized}"
            )
        if ts_ns <= 0:
            raise ValueError(f"{commodity}: ts_ns must be > 0, got {ts_ns}")
        self._basis[commodity] = (basis_drift_annualized, ts_ns)

    def get(self, commodity: str, *, now_ns: int) -> float:
        entry = self._basis.get(commodity)
        if entry is None:
            raise MissingStateError(f"{commodity}: no basis primed")
        drift, ts_ns = entry
        staleness_ms = (now_ns - ts_ns) / 1e6
        if staleness_ms > self._max_staleness_ms:
            raise StaleDataError(
                f"{commodity}: basis stale by {staleness_ms:.0f}ms "
                f"(budget {self._max_staleness_ms}ms)"
            )
        return drift
