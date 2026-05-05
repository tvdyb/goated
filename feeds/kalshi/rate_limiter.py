"""Token-bucket rate limiter for Kalshi API.

Kalshi uses a tiered leaky-bucket scheme with separate read/write budgets.
Default request cost: 10 tokens.  Cancel cost: 2 tokens.  No batch discount.
Over-quota returns HTTP 429 with no Retry-After header.

Reference: https://docs.kalshi.com/getting_started/rate_limits
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum


class KalshiTier(Enum):
    """Kalshi API tier with (read_tokens_per_sec, write_tokens_per_sec)."""

    BASIC = (200, 100)
    ADVANCED = (300, 300)
    PREMIER = (1000, 1000)
    PARAGON = (2000, 2000)
    PRIME = (4000, 4000)


# Default token costs per the Kalshi docs
DEFAULT_REQUEST_COST = 10
CANCEL_REQUEST_COST = 2


@dataclass
class _Bucket:
    """Single token bucket with refill."""

    capacity: float
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: float  # time.monotonic()

    def refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def try_consume(self, cost: float) -> float:
        """Try to consume tokens.  Returns wait time (0.0 if immediately available)."""
        self.refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return 0.0
        deficit = cost - self.tokens
        return deficit / self.refill_rate


class KalshiRateLimiter:
    """Async token-bucket rate limiter with separate read/write buckets.

    Usage::

        limiter = KalshiRateLimiter(tier=KalshiTier.BASIC)
        await limiter.acquire_read()   # default 10-token read
        await limiter.acquire_write()  # default 10-token write
        await limiter.acquire_write(cost=CANCEL_REQUEST_COST)  # 2-token cancel
    """

    def __init__(self, tier: KalshiTier = KalshiTier.BASIC) -> None:
        read_rate, write_rate = tier.value
        now = time.monotonic()
        self._read_bucket = _Bucket(
            capacity=float(read_rate),
            tokens=float(read_rate),
            refill_rate=float(read_rate),
            last_refill=now,
        )
        self._write_bucket = _Bucket(
            capacity=float(write_rate),
            tokens=float(write_rate),
            refill_rate=float(write_rate),
            last_refill=now,
        )
        self._lock = asyncio.Lock()
        # Diagnostic counters surfaced by the dashboard so the operator
        # can see whether they're getting rate-limited.
        self._total_429s: int = 0
        self._last_429_ts: float = 0.0
        self._total_throttle_waits: int = 0
        self._total_throttle_wait_s: float = 0.0

    def note_429(self) -> None:
        """KalshiClient calls this on each observed 429 response."""
        self._total_429s += 1
        self._last_429_ts = time.time()

    def stats(self) -> dict:
        """Snapshot of rate-limiter state for diagnostics."""
        return {
            "read_tokens_available": self.read_tokens_available,
            "read_capacity": self._read_bucket.capacity,
            "write_tokens_available": self.write_tokens_available,
            "write_capacity": self._write_bucket.capacity,
            "total_429s": self._total_429s,
            "last_429_ts": self._last_429_ts,
            "total_throttle_waits": self._total_throttle_waits,
            "total_throttle_wait_s": self._total_throttle_wait_s,
        }

    async def acquire_read(self, cost: float = DEFAULT_REQUEST_COST) -> None:
        """Wait until ``cost`` read tokens are available, then consume them."""
        await self._acquire(self._read_bucket, cost)

    async def acquire_write(self, cost: float = DEFAULT_REQUEST_COST) -> None:
        """Wait until ``cost`` write tokens are available, then consume them."""
        await self._acquire(self._write_bucket, cost)

    async def _acquire(self, bucket: _Bucket, cost: float) -> None:
        while True:
            async with self._lock:
                wait = bucket.try_consume(cost)
                if wait == 0.0:
                    return
            # Sleep outside the lock so other callers can proceed
            self._total_throttle_waits += 1
            self._total_throttle_wait_s += wait
            await asyncio.sleep(wait)

    @property
    def read_tokens_available(self) -> float:
        """Current read tokens (approximate, for diagnostics)."""
        self._read_bucket.refill()
        return self._read_bucket.tokens

    @property
    def write_tokens_available(self) -> float:
        """Current write tokens (approximate, for diagnostics)."""
        self._write_bucket.refill()
        return self._write_bucket.tokens
