"""Fill markout tracker — adverse-selection diagnostic.

What is markout?
  For each fill, record the trade price and re-poll the orderbook mid
  at fixed time horizons (1m and 5m) after the fill. The signed
  delta is the "markout":

    markout_long_yes  = (mid_after − fill_price) × qty
    markout_long_no   = (fill_price − mid_after) × qty   (we got 1−p
                                                           equivalent)

  Negative markout = the price moved against us right after the fill,
  i.e. we were probably picked off by someone with information. Toxic
  fills aggregated across many trades surface adverse-selection
  patterns the operator can't see from raw P&L.

Detection model:
  We don't have a per-fill push from Kalshi today. Instead, the runner
  refreshes positions once per cycle. We diff this cycle's positions
  vs last cycle's; any quantity change → infer a fill at the cycle's
  mid (best bid/ask average) — coarse but usable.

  Future enhancement: switch to /portfolio/fills polling for exact
  fill prices and timestamps. The tracker's interface is shaped to
  accept either — `record_fill(...)` is the entry point.

Async sampling:
  When a fill is recorded, an asyncio task is spawned to wake up at
  +1m and +5m, pull the orderbook mid via the supplied async fetch
  hook, and append the markout sample. State is in-memory; resets on
  bot restart.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

logger = logging.getLogger(__name__)


# Hook the tracker calls to fetch the current mid (in cents) for a
# ticker. Returns None when no orderbook / one-sided / no mid.
MidFetchHook = Callable[[str], Awaitable[float | None]]


SideLabel = Literal["bid", "ask"]


@dataclass
class _Fill:
    """One inferred fill, before its samples are populated."""
    ticker: str
    side: SideLabel             # "bid" = we bought yes, "ask" = we sold yes
    qty: int                    # positive
    fill_price_c: float         # the inferred trade price in cents
    fill_ts: float              # unix ts
    sample_1m_c: float | None = None
    sample_5m_c: float | None = None

    def markout_1m_c(self) -> float | None:
        """Signed cents delta at +1m, in OUR favor.
        Bid (we bought yes): mid − price.
        Ask (we sold yes):    price − mid."""
        if self.sample_1m_c is None:
            return None
        return (self.sample_1m_c - self.fill_price_c) if self.side == "bid" \
            else (self.fill_price_c - self.sample_1m_c)

    def markout_5m_c(self) -> float | None:
        if self.sample_5m_c is None:
            return None
        return (self.sample_5m_c - self.fill_price_c) if self.side == "bid" \
            else (self.fill_price_c - self.sample_5m_c)


@dataclass
class TickerStats:
    """Aggregated markout for one ticker."""
    ticker: str
    n_fills: int = 0
    mean_1m_c: float = 0.0
    mean_5m_c: float = 0.0
    n_with_5m: int = 0
    toxic: bool = False              # True iff mean_5m_c < -2.0 and n_with_5m >= 2


class MarkoutTracker:
    """Per-ticker markout aggregator.

    Hot path:
      - `observe_position_delta(ticker, prev_qty, cur_qty, mid_c, ts)`:
        called once per cycle by the runner with the position delta.
      - On a non-zero delta, records a fill and schedules samples.

    Cold path:
      - `snapshot()` returns a list of TickerStats for the dashboard.
    """

    def __init__(
        self,
        mid_fetch_hook: MidFetchHook,
        *,
        sample_horizons_s: tuple[float, float] = (60.0, 300.0),
    ) -> None:
        self._fetch = mid_fetch_hook
        self._horizons = sample_horizons_s
        self._fills: list[_Fill] = []
        self._tasks: list[asyncio.Task] = []

    def all_fills(self) -> list[_Fill]:
        return list(self._fills)

    async def observe_position_delta(
        self,
        ticker: str,
        prev_qty: int,
        cur_qty: int,
        mid_c: float | None,
        ts: float | None = None,
    ) -> _Fill | None:
        """Detect a fill from a position change. Returns the recorded
        fill or None if no fill is inferred.

        Heuristic: any qty change is a fill at `mid_c`. We don't try to
        distinguish multi-fill cycles — operator should be running with
        a short cycle (≤5s) so real fills are typically one per cycle.
        """
        delta = cur_qty - prev_qty
        if delta == 0:
            return None
        if mid_c is None:
            # Can't record a meaningful price. Skip silently.
            return None
        side: SideLabel = "bid" if delta > 0 else "ask"
        qty = abs(delta)
        return await self.record_fill(
            ticker=ticker, side=side, qty=qty,
            fill_price_c=float(mid_c),
            fill_ts=ts if ts is not None else time.time(),
        )

    async def record_fill(
        self, *, ticker: str, side: SideLabel, qty: int,
        fill_price_c: float, fill_ts: float,
    ) -> _Fill:
        """Public entry point: register a fill and schedule samples."""
        fill = _Fill(
            ticker=ticker, side=side, qty=qty,
            fill_price_c=fill_price_c, fill_ts=fill_ts,
        )
        self._fills.append(fill)
        # Spawn a sampler task. We don't await — it runs in the
        # background until the longest horizon elapses.
        task = asyncio.create_task(self._sample_loop(fill))
        self._tasks.append(task)
        # Garbage-collect completed tasks to bound memory.
        self._tasks = [t for t in self._tasks if not t.done()]
        return fill

    async def _sample_loop(self, fill: _Fill) -> None:
        """Sleep, fetch mid, record sample. Two horizons: 1m, 5m."""
        h1, h2 = self._horizons
        try:
            await asyncio.sleep(h1)
            try:
                mid = await self._fetch(fill.ticker)
                if mid is not None:
                    fill.sample_1m_c = float(mid)
            except Exception as exc:
                logger.info("markout %s 1m fetch failed: %s", fill.ticker, exc)

            await asyncio.sleep(max(0.0, h2 - h1))
            try:
                mid = await self._fetch(fill.ticker)
                if mid is not None:
                    fill.sample_5m_c = float(mid)
            except Exception as exc:
                logger.info("markout %s 5m fetch failed: %s", fill.ticker, exc)
        except asyncio.CancelledError:
            raise

    def snapshot(self) -> list[TickerStats]:
        """Aggregate per-ticker stats. Skips fills with no samples yet."""
        per_ticker: dict[str, list[_Fill]] = {}
        for f in self._fills:
            per_ticker.setdefault(f.ticker, []).append(f)
        out: list[TickerStats] = []
        for ticker, fills in per_ticker.items():
            mo_1m = [f.markout_1m_c() for f in fills]
            mo_1m = [x for x in mo_1m if x is not None]
            mo_5m = [f.markout_5m_c() for f in fills]
            mo_5m = [x for x in mo_5m if x is not None]
            n = len(fills)
            mean_1m = (sum(mo_1m) / len(mo_1m)) if mo_1m else 0.0
            mean_5m = (sum(mo_5m) / len(mo_5m)) if mo_5m else 0.0
            toxic = (mean_5m < -2.0 and len(mo_5m) >= 2)
            out.append(TickerStats(
                ticker=ticker, n_fills=n,
                mean_1m_c=mean_1m, mean_5m_c=mean_5m,
                n_with_5m=len(mo_5m), toxic=toxic,
            ))
        # Sort: toxic first (most adverse), then by fill count desc
        out.sort(key=lambda s: (not s.toxic, -s.n_fills))
        return out

    async def shutdown(self) -> None:
        """Cancel all in-flight sampling tasks. Called at bot stop."""
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
