"""Per-commodity tick ring buffer, numpy-backed.

Each commodity gets a preallocated ring of `capacity` ticks storing
(timestamp_ns, price, n_publishers). Push is O(1), last-tick lookup is O(1).
A monotonic `seq` counter (distinct from the wraparound cursor) is used as
`source_tick_seq` on every published theo, so a theo can be traced to the
exact tick that drove it even after the ring wraps.

Scope: deliverable 1 only stores the latest tick on the hot path; the ring
history is here for backtest and feature-computation callers. No history
reads on the repricing path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from state.errors import MissingStateError


@dataclass(slots=True)
class LatestTick:
    ts_ns: int
    price: float
    n_publishers: int
    seq: int


class TickRing:
    __slots__ = ("_ts_ns", "_price", "_n_publishers", "_cursor", "_seq", "capacity")

    def __init__(self, capacity: int = 1_000_000) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self.capacity = capacity
        self._ts_ns = np.zeros(capacity, dtype=np.int64)
        self._price = np.zeros(capacity, dtype=np.float64)
        self._n_publishers = np.zeros(capacity, dtype=np.int32)
        self._cursor = 0
        self._seq = 0

    def push(self, ts_ns: int, price: float, n_publishers: int) -> int:
        i = self._cursor
        self._ts_ns[i] = ts_ns
        self._price[i] = price
        self._n_publishers[i] = n_publishers
        self._cursor = (i + 1) % self.capacity
        self._seq += 1
        return self._seq

    @property
    def last_seq(self) -> int:
        return self._seq

    def latest(self) -> LatestTick:
        if self._seq == 0:
            raise MissingStateError("ring is empty")
        idx = (self._cursor - 1) % self.capacity
        return LatestTick(
            ts_ns=int(self._ts_ns[idx]),
            price=float(self._price[idx]),
            n_publishers=int(self._n_publishers[idx]),
            seq=self._seq,
        )


class TickStore:
    def __init__(self, capacity_per_commodity: int = 1_000_000) -> None:
        self._rings: dict[str, TickRing] = {}
        self._capacity = capacity_per_commodity

    def register(self, commodity: str) -> TickRing:
        if commodity not in self._rings:
            self._rings[commodity] = TickRing(self._capacity)
        return self._rings[commodity]

    def push(self, commodity: str, ts_ns: int, price: float, n_publishers: int) -> int:
        ring = self._rings.get(commodity)
        if ring is None:
            raise MissingStateError(f"{commodity}: commodity not registered in tick store")
        return ring.push(ts_ns, price, n_publishers)

    def latest(self, commodity: str) -> LatestTick:
        ring = self._rings.get(commodity)
        if ring is None:
            raise MissingStateError(f"{commodity}: commodity not registered in tick store")
        return ring.latest()

    def commodities(self) -> list[str]:
        return sorted(self._rings)
