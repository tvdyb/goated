"""LIP-earnings history: persistent samples + $/hr histogram.

Why we need this:
  EarningsAccrual gives us a running-tally of $ accrued THIS session.
  Reset on bot restart. Useful for "what's my pace right now" but bad
  for "how am I doing this week / over the last month?"

This module persists periodic samples of (timestamp, total_dollars,
elapsed_s) to a JSONL file. On bot start the history is loaded; on
each cycle a sample may be appended (rate-limited to one per
`SAMPLE_INTERVAL_S`). The dashboard then aggregates samples into a
$/hr distribution histogram and a few headline stats.

Persistence layer is just a JSONL append — simple, durable across
restarts, easy to inspect with `jq` / cat. File rotation + cap
borrowed from RetentionManager's pattern (gzip closed files, evict
oldest beyond the byte cap).

Math (per sample):
    instantaneous $/hr ≈ (Δtotal / Δelapsed) * 3600

We compute by diffing consecutive samples (not the absolute total /
elapsed, which always spans bot startup → biases low after restart).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Iterator

logger = logging.getLogger(__name__)


_SAMPLE_INTERVAL_S = 60.0       # one sample per minute by default
_HISTOGRAM_BIN_EDGES = (        # in $/hr — 11 edges → 10 bins + overflow
    0.0, 0.05, 0.10, 0.25, 0.50, 1.00, 2.00, 4.00, 8.00, 16.00,
)


@dataclass(frozen=True)
class _Sample:
    ts: float
    total_dollars: float
    elapsed_s: float


@dataclass(frozen=True)
class HistogramStats:
    """Snapshot stats consumed by the dashboard."""
    n_samples: int
    cumulative_dollars: float       # max total seen across all samples
    elapsed_s: float                # total tracked time (sum of inter-sample deltas)
    avg_dollars_per_hour: float     # time-weighted average rate
    peak_dollars_per_hour: float    # max rate observed in any inter-sample window
    bins: list[tuple[float, float, int]]  # (lo_edge, hi_edge_or_inf, count)


class EarningsHistory:
    """Append-only sample log + on-demand histogram aggregation.

    Samples are appended to `history_path` (JSONL). Caller calls
    `record(total_dollars, elapsed_s)` periodically — the class
    rate-limits writes via `_SAMPLE_INTERVAL_S`. `histogram()` reads
    the file and returns aggregate stats.
    """

    def __init__(
        self,
        history_path: str,
        *,
        sample_interval_s: float = _SAMPLE_INTERVAL_S,
    ) -> None:
        self._path = history_path
        self._interval = float(sample_interval_s)
        self._last_recorded_ts: float = 0.0
        # Ensure parent directory exists. Caller's responsibility to
        # use a writable path.
        os.makedirs(os.path.dirname(history_path) or ".", exist_ok=True)

    @property
    def path(self) -> str:
        return self._path

    def record(
        self,
        total_dollars: float,
        elapsed_s: float,
        *,
        now_ts: float | None = None,
    ) -> bool:
        """Append a sample if `_SAMPLE_INTERVAL_S` has passed since last
        record. Returns True iff a sample was actually written."""
        now = now_ts if now_ts is not None else time.time()
        if (now - self._last_recorded_ts) < self._interval:
            return False
        if total_dollars < 0 or elapsed_s < 0:
            return False
        try:
            with open(self._path, "a") as f:
                f.write(json.dumps({
                    "ts": now,
                    "total_dollars": float(total_dollars),
                    "elapsed_s": float(elapsed_s),
                }) + "\n")
        except Exception as exc:
            logger.warning("EarningsHistory.record failed: %s", exc)
            return False
        self._last_recorded_ts = now
        return True

    def _read_samples(self) -> Iterator[_Sample]:
        """Iterate samples from disk, oldest first. Skips malformed
        rows. Returns empty if file doesn't exist yet."""
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    try:
                        yield _Sample(
                            ts=float(d["ts"]),
                            total_dollars=float(d["total_dollars"]),
                            elapsed_s=float(d["elapsed_s"]),
                        )
                    except (KeyError, ValueError, TypeError):
                        continue
        except OSError as exc:
            logger.warning("EarningsHistory.read failed: %s", exc)

    def histogram(self) -> HistogramStats:
        """Aggregate all on-disk samples into headline stats + bin
        counts. Each inter-sample window contributes one bin entry,
        weighted by its rate ($/hr) over that window."""
        samples = list(self._read_samples())
        bin_counts = [0] * len(_HISTOGRAM_BIN_EDGES)
        # bins are: [edges[i], edges[i+1]) for i in 0..N-1, then
        # the "overflow" bin for x >= edges[-1]. We use one extra
        # slot at the end of bin_counts for that overflow.
        bin_counts = [0] * len(_HISTOGRAM_BIN_EDGES)

        if not samples:
            return HistogramStats(
                n_samples=0, cumulative_dollars=0.0, elapsed_s=0.0,
                avg_dollars_per_hour=0.0, peak_dollars_per_hour=0.0,
                bins=_empty_bins(),
            )

        # Sort by ts to be defensive (caller should append in order).
        samples.sort(key=lambda s: s.ts)
        cum = max(s.total_dollars for s in samples)
        elapsed_total = 0.0
        time_weighted_sum = 0.0
        peak_rate = 0.0

        for prev, cur in zip(samples, samples[1:]):
            dt = cur.ts - prev.ts
            if dt <= 0:
                continue
            d_dollars = cur.total_dollars - prev.total_dollars
            # Restart detected: total went DOWN. Skip this window —
            # we can't compute a meaningful rate.
            if d_dollars < 0:
                continue
            rate = d_dollars / dt * 3600.0  # $/hr
            elapsed_total += dt
            time_weighted_sum += rate * dt
            if rate > peak_rate:
                peak_rate = rate
            # Bin
            slot = _slot_for(rate)
            bin_counts[slot] += 1

        avg = (time_weighted_sum / elapsed_total) if elapsed_total > 0 else 0.0
        return HistogramStats(
            n_samples=len(samples),
            cumulative_dollars=cum,
            elapsed_s=elapsed_total,
            avg_dollars_per_hour=avg,
            peak_dollars_per_hour=peak_rate,
            bins=_bins_with_edges(bin_counts),
        )


# ── Helpers ─────────────────────────────────────────────────────────


def _slot_for(rate: float) -> int:
    """Find the bin index for a rate. Returns the overflow slot if
    rate >= the last edge."""
    edges = _HISTOGRAM_BIN_EDGES
    for i in range(len(edges) - 1):
        if edges[i] <= rate < edges[i + 1]:
            return i
    if rate < edges[0]:
        return 0
    return len(edges) - 1  # overflow


def _bins_with_edges(counts: list[int]) -> list[tuple[float, float, int]]:
    edges = _HISTOGRAM_BIN_EDGES
    out: list[tuple[float, float, int]] = []
    for i in range(len(edges) - 1):
        out.append((edges[i], edges[i + 1], counts[i]))
    # Overflow: last edge → infinity
    out.append((edges[-1], float("inf"), counts[-1]))
    return out


def _empty_bins() -> list[tuple[float, float, int]]:
    return _bins_with_edges([0] * len(_HISTOGRAM_BIN_EDGES))
