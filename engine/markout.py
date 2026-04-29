"""Per-bucket fill markout tracker.

Measures adverse selection by tracking how fair value moves after each fill.
Markout = theo_now - theo_at_fill (for buys; negated for sells).

Positive markout = good fill (price moved in our favor).
Negative markout = adverse selection (informed trader picked us off).

Horizons: 1m, 5m, 30m.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

HORIZON_1M = 60.0
HORIZON_5M = 300.0
HORIZON_30M = 1800.0
_HORIZONS = (HORIZON_1M, HORIZON_5M, HORIZON_30M)

# A fill's markout is "finalized" once all horizons have been snapshotted.
_MAX_HORIZON = HORIZON_30M

# Rolling window for per-bucket average markout (seconds).
ROLLING_WINDOW_S = 3600.0  # 1 hour

# Threshold (cents) below which a strike is considered toxic.
TOXIC_THRESHOLD_CENTS = -2.0


@dataclass(slots=True)
class FillMarkout:
    """A single fill being tracked for markout."""

    timestamp: float
    market_ticker: str
    side: str  # "buy" or "sell"
    fill_price_cents: int
    theo_at_fill_cents: float
    # Markout snapshots: horizon_seconds -> markout_cents (None = not yet snapped)
    snapshots: dict[float, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.snapshots:
            self.snapshots = {h: None for h in _HORIZONS}

    @property
    def is_complete(self) -> bool:
        return all(v is not None for v in self.snapshots.values())


@dataclass(frozen=True, slots=True)
class BucketMarkout:
    """Aggregate markout stats for one market ticker (bucket)."""

    market_ticker: str
    avg_1m: float
    avg_5m: float
    avg_30m: float
    n_fills: int


class MarkoutTracker:
    """Tracks fill markouts across all buckets.

    Usage:
        tracker = MarkoutTracker()

        # On each fill:
        tracker.record_fill(timestamp, market_ticker, side, fill_price_cents, theo_cents)

        # On each cycle:
        tracker.update(now, theo_by_ticker)

        # Query:
        toxic = tracker.get_toxic_strikes()
        stats = tracker.bucket_stats()
    """

    def __init__(
        self,
        rolling_window_s: float = ROLLING_WINDOW_S,
        toxic_threshold_cents: float = TOXIC_THRESHOLD_CENTS,
    ) -> None:
        self._rolling_window_s = rolling_window_s
        self._toxic_threshold_cents = toxic_threshold_cents
        # Active fills being tracked (not yet fully snapshotted)
        self._active: list[FillMarkout] = []
        # Completed fills (all horizons snapshotted) within rolling window
        self._completed: list[FillMarkout] = []

    def record_fill(
        self,
        timestamp: float,
        market_ticker: str,
        side: str,
        fill_price_cents: int,
        theo_at_fill_cents: float,
    ) -> None:
        """Record a new fill for markout tracking."""
        fm = FillMarkout(
            timestamp=timestamp,
            market_ticker=market_ticker,
            side=side,
            fill_price_cents=fill_price_cents,
            theo_at_fill_cents=theo_at_fill_cents,
        )
        self._active.append(fm)

    def update(self, now: float, theo_by_ticker: dict[str, float]) -> None:
        """Update markout snapshots for all active fills.

        Call once per cycle with current theo values (in cents) per market ticker.
        """
        still_active: list[FillMarkout] = []

        for fm in self._active:
            theo_now = theo_by_ticker.get(fm.market_ticker)
            if theo_now is None:
                still_active.append(fm)
                continue

            elapsed = now - fm.timestamp

            for horizon in _HORIZONS:
                if fm.snapshots[horizon] is not None:
                    continue
                if elapsed >= horizon:
                    raw = theo_now - fm.theo_at_fill_cents
                    # For sells, adverse selection is theo going UP after we sold
                    if fm.side == "sell":
                        raw = -raw
                    fm.snapshots[horizon] = raw

            if fm.is_complete:
                self._completed.append(fm)
            else:
                still_active.append(fm)

        self._active = still_active

        # Prune completed fills outside rolling window
        cutoff = now - self._rolling_window_s
        self._completed = [f for f in self._completed if f.timestamp >= cutoff]

    def get_toxic_strikes(self) -> list[str]:
        """Return market tickers where avg 5m markout < toxic threshold."""
        stats = self.bucket_stats()
        return [
            bs.market_ticker
            for bs in stats
            if bs.n_fills >= 2 and bs.avg_5m < self._toxic_threshold_cents
        ]

    def bucket_stats(self) -> list[BucketMarkout]:
        """Compute per-bucket average markout across all horizons."""
        # Group completed fills by market_ticker
        by_ticker: dict[str, list[FillMarkout]] = defaultdict(list)
        for fm in self._completed:
            by_ticker[fm.market_ticker].append(fm)

        result: list[BucketMarkout] = []
        for ticker, fills in sorted(by_ticker.items()):
            n = len(fills)
            if n == 0:
                continue
            avg_1m = sum(f.snapshots[HORIZON_1M] for f in fills) / n  # type: ignore[arg-type]
            avg_5m = sum(f.snapshots[HORIZON_5M] for f in fills) / n  # type: ignore[arg-type]
            avg_30m = sum(f.snapshots[HORIZON_30M] for f in fills) / n  # type: ignore[arg-type]
            result.append(BucketMarkout(
                market_ticker=ticker,
                avg_1m=avg_1m,
                avg_5m=avg_5m,
                avg_30m=avg_30m,
                n_fills=n,
            ))
        return result

    def active_count(self) -> int:
        """Number of fills still being tracked (not yet fully snapshotted)."""
        return len(self._active)

    def completed_count(self) -> int:
        """Number of completed fills in the rolling window."""
        return len(self._completed)
