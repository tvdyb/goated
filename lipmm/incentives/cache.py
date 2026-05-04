"""IncentiveCache — periodic snapshot + fault-tolerant lookup.

Wraps an `IncentiveProvider` with an asyncio refresh loop. Holds the
last successful snapshot so the dashboard never sees a blank panel
just because the provider transiently failed.

Design choices:

  - **Refresh in a background task**, not on every read. The dashboard
    polls reads at WS push cadence (every state change), and we don't
    want every render to block on a Kalshi call.
  - **Failure is sticky-recoverable**. A single fetch error logs a
    WARNING, leaves the prior snapshot in place, and the loop tries
    again at the next interval. Only the *very first* fetch raising
    propagates — that's a startup misconfiguration worth surfacing.
  - **Stop is graceful**. `stop()` signals the loop, waits with a
    bounded timeout, and falls back to cancel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from lipmm.incentives.base import IncentiveProgram, IncentiveProvider

logger = logging.getLogger(__name__)


class IncentiveCache:
    """Periodic snapshot of active incentive programs."""

    def __init__(
        self,
        provider: IncentiveProvider,
        *,
        refresh_s: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if refresh_s <= 0:
            raise ValueError(f"refresh_s must be > 0; got {refresh_s}")
        self._provider = provider
        self._refresh_s = float(refresh_s)
        self._clock = clock
        self._snapshot: list[IncentiveProgram] = []
        self._last_refresh_ts: float = 0.0
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        self._initial_fetched = False

    # ── Reads ──────────────────────────────────────────────────────

    def snapshot(self) -> list[IncentiveProgram]:
        """Last successfully-fetched list. Returns [] before first fetch."""
        return list(self._snapshot)

    def by_ticker(self) -> dict[str, list[IncentiveProgram]]:
        """Per-market index of the snapshot. One ticker may have multiple
        concurrent programs (rare but allowed by the API)."""
        out: dict[str, list[IncentiveProgram]] = {}
        for p in self._snapshot:
            out.setdefault(p.market_ticker, []).append(p)
        return out

    @property
    def last_refresh_ts(self) -> float:
        return self._last_refresh_ts

    @property
    def last_refresh_age_s(self) -> float | None:
        if self._last_refresh_ts == 0.0:
            return None
        return self._clock() - self._last_refresh_ts

    # ── Lifecycle ──────────────────────────────────────────────────

    async def refresh_once(self) -> list[IncentiveProgram]:
        """Pull a fresh snapshot. Raises on the very first call's failure
        (startup misconfiguration); subsequent failures are absorbed and
        the prior snapshot stays in place."""
        try:
            programs = await self._provider.list_active()
        except Exception as exc:
            if not self._initial_fetched:
                logger.error("initial incentive fetch failed: %s", exc)
                raise
            logger.warning(
                "incentive refresh failed (keeping last snapshot of %d): %s",
                len(self._snapshot), exc,
            )
            return self._snapshot
        self._snapshot = list(programs)
        self._last_refresh_ts = self._clock()
        self._initial_fetched = True
        return self._snapshot

    async def start(self) -> None:
        """Spawn the periodic refresh task. Idempotent.

        Performs ONE synchronous fetch first so the dashboard has data
        the moment it opens. If that initial fetch raises, propagate so
        the operator sees the misconfiguration.
        """
        if self._task is not None and not self._task.done():
            return
        await self.refresh_once()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        if self._stop is not None:
            self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        except Exception:
            pass
        self._task = None
        self._stop = None

    async def _loop(self) -> None:
        assert self._stop is not None
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self._refresh_s,
                    )
                    return  # stop requested
                except asyncio.TimeoutError:
                    pass
                try:
                    await self.refresh_once()
                except Exception as exc:
                    logger.warning("incentive cache loop tick failed: %s", exc)
        except asyncio.CancelledError:
            raise
