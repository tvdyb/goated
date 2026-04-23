"""Implied-vol surface.

Deliverable 1 implements a minimal variant: a static per-commodity ATM IV
with staleness tracking. Deliverables 3+ replace this with a (strike,
expiry) grid interpolated from CME options chains; the public interface
here is designed so that upgrade is additive.

Contract: `atm(commodity, now_ns)` returns the current ATM IV for the
weekly expiry closest to the Kalshi settle. Raises `MissingStateError` if
no IV has been primed; raises `StaleDataError` if the last prime is older
than `max_staleness_ms`. Never returns a fallback.
"""

from __future__ import annotations

import math

from state.errors import MissingStateError, StaleDataError


class IVSurface:
    __slots__ = ("_atm", "_max_staleness_ms")

    def __init__(self, max_staleness_ms: int = 60_000) -> None:
        if max_staleness_ms <= 0:
            raise ValueError(f"max_staleness_ms must be > 0, got {max_staleness_ms}")
        self._atm: dict[str, tuple[float, int]] = {}
        self._max_staleness_ms = max_staleness_ms

    def set_atm(self, commodity: str, sigma: float, ts_ns: int) -> None:
        if not math.isfinite(sigma) or sigma <= 0.0:
            raise ValueError(f"{commodity}: sigma must be finite and > 0, got {sigma}")
        if ts_ns <= 0:
            raise ValueError(f"{commodity}: ts_ns must be > 0, got {ts_ns}")
        self._atm[commodity] = (sigma, ts_ns)

    def atm(self, commodity: str, *, now_ns: int) -> float:
        entry = self._atm.get(commodity)
        if entry is None:
            raise MissingStateError(f"{commodity}: no ATM IV primed")
        sigma, ts_ns = entry
        staleness_ms = (now_ns - ts_ns) / 1e6
        if staleness_ms > self._max_staleness_ms:
            raise StaleDataError(
                f"{commodity}: ATM IV stale by {staleness_ms:.0f}ms "
                f"(budget {self._max_staleness_ms}ms)"
            )
        return sigma
