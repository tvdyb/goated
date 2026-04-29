"""Forward price provider backed by Pyth Hermes.

Polls Pyth Hermes REST API every N seconds for the latest ZS soybean
futures price. Falls back to a caller-supplied Kalshi-inferred forward
when Pyth is unavailable or stale.

Non-negotiables:
  - asyncio for I/O only
  - Fail-loud on misconfiguration (raise, never silently default)
  - No pandas
  - Type hints on all public interfaces

Usage::

    provider = PythForwardProvider(pyth_cfg)
    await provider.start()        # begins background polling
    fwd = provider.forward_price  # latest forward or None
    await provider.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from feeds.pyth.client import (
    PythClientError,
    PythHermesClient,
    PythPrice,
    PythStaleError,
    PythUnavailableError,
)

logger = logging.getLogger("feeds.pyth.forward")


@dataclass
class PythForwardConfig:
    """Configuration for the Pyth forward price provider."""

    feed_id: str
    hermes_base_url: str = "https://hermes.pyth.network"
    poll_interval_s: float = 5.0
    max_staleness_ms: int = 2000
    # Pyth soy prices are in cents/bushel (e.g. 1177.5 = $11.775/bu).
    # Set divisor to convert to $/bushel as needed.
    price_divisor: float = 100.0


def load_pyth_forward_config(pyth_cfg: dict[str, Any]) -> PythForwardConfig:
    """Build PythForwardConfig from pyth_feeds.yaml structure.

    Expected structure::

        hermes_http: "https://hermes.pyth.network"
        feeds:
          soy:
            feed_id: "0x..."
            max_staleness_ms: 2000
    """
    soy = pyth_cfg.get("feeds", {}).get("soy", {})
    feed_id = soy.get("feed_id", "")
    if not feed_id:
        raise ValueError("pyth_feeds.yaml: feeds.soy.feed_id is required")

    return PythForwardConfig(
        feed_id=feed_id,
        hermes_base_url=pyth_cfg.get(
            "hermes_http", "https://hermes.pyth.network"
        ),
        max_staleness_ms=soy.get("max_staleness_ms", 2000),
        price_divisor=soy.get("price_divisor", 100.0),
    )


@dataclass
class PythForwardProvider:
    """Polls Pyth Hermes for real-time forward price.

    Attributes:
        forward_price: Latest forward price in $/bushel, or None if
            Pyth is unavailable. Thread-safe read.
        last_update_time: Unix timestamp of the last successful update.
        pyth_available: Whether Pyth is currently providing data.
    """

    config: PythForwardConfig
    forward_price: float | None = field(default=None, init=False)
    last_update_time: float = field(default=0.0, init=False)
    pyth_available: bool = field(default=False, init=False)
    _client: PythHermesClient = field(init=False, repr=False)
    _task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False
    )
    _running: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._client = PythHermesClient(
            base_url=self.config.hermes_base_url,
        )

    async def start(self) -> None:
        """Open the HTTP client and begin background polling."""
        await self._client.open()
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Pyth forward provider started (feed=%s, poll=%.1fs)",
            self.config.feed_id[:16] + "...",
            self.config.poll_interval_s,
        )

    async def stop(self) -> None:
        """Stop polling and close the HTTP client."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.close()
        logger.info("Pyth forward provider stopped")

    async def poll_once(self) -> float | None:
        """Fetch the latest price once. Returns $/bushel or None.

        Exposed for use in synchronous main loops that want to control
        poll timing themselves (instead of using start/stop background
        task).
        """
        try:
            pyth_price = await self._client.get_latest_price(
                feed_id=self.config.feed_id,
                max_staleness_ms=self.config.max_staleness_ms,
            )
            forward = pyth_price.price / self.config.price_divisor
            self.forward_price = forward
            self.last_update_time = time.time()
            self.pyth_available = True
            logger.debug(
                "Pyth forward: $%.4f/bu (conf=%.4f, age=%ds)",
                forward,
                pyth_price.conf / self.config.price_divisor,
                int(time.time()) - pyth_price.publish_time,
            )
            return forward
        except (PythStaleError, PythUnavailableError) as exc:
            self.pyth_available = False
            logger.warning("Pyth forward unavailable: %s", exc)
            return None
        except PythClientError as exc:
            self.pyth_available = False
            logger.error("Pyth client error: %s", exc)
            return None

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._running:
            await self.poll_once()
            try:
                await asyncio.sleep(self.config.poll_interval_s)
            except asyncio.CancelledError:
                break
