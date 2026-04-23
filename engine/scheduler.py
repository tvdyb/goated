"""Asyncio priority-queue scheduler.

Ticks reprice immediately (priority 0). IV surface / basis / event-calendar
updates reprice at lower priority. The scheduler guarantees ordering by
priority, but is not used in the GBM inner math — see `engine/pricer.py`
for the hot path. No `time.sleep` here; everything is `await`.

Deliverable 1 ships the skeleton; the real coroutine wiring happens once
feeds/pyth_ws is implemented.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum


class Priority(IntEnum):
    TICK = 0
    IV_UPDATE = 10
    BASIS_UPDATE = 20
    EVENT_CAL = 30
    TIMER = 90


@dataclass(frozen=True, slots=True, order=True)
class _QueueItem:
    priority: int
    sequence: int
    payload: Callable[[], Awaitable[None]]


class Scheduler:
    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._running = False

    async def submit(self, priority: Priority, coro_factory: Callable[[], Awaitable[None]]) -> None:
        item = _QueueItem(priority=int(priority), sequence=next(self._seq), payload=coro_factory)
        await self._queue.put(item)

    async def run(self) -> None:
        self._running = True
        try:
            while self._running:
                item = await self._queue.get()
                try:
                    await item.payload()
                finally:
                    self._queue.task_done()
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
