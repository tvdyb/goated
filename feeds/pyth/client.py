"""Async Pyth Hermes REST client for latest price fetches.

Pulls the latest price from Pyth Hermes ``/v2/updates/price/latest``
endpoint. Parses the fixed-point price format (price * 10^expo) into a
float. Validates staleness against a configurable threshold.

Non-negotiables:
  - asyncio for I/O only
  - Fail-loud on malformed responses (raise, never return defaults)
  - No pandas
  - Type hints on all public interfaces
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("feeds.pyth.client")


class PythClientError(RuntimeError):
    """Base error for Pyth client issues."""


class PythStaleError(PythClientError):
    """Price is older than the staleness threshold."""


class PythUnavailableError(PythClientError):
    """Hermes endpoint is unreachable or returned an error."""


@dataclass(frozen=True)
class PythPrice:
    """Parsed Pyth price tick."""

    price: float  # in natural units (e.g. $/bushel for soy)
    conf: float  # confidence interval in same units
    publish_time: int  # unix seconds
    feed_id: str


class PythHermesClient:
    """Async REST client for Pyth Hermes price API."""

    def __init__(
        self,
        base_url: str = "https://hermes.pyth.network",
        timeout_s: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_latest_price(
        self,
        feed_id: str,
        max_staleness_ms: int = 2000,
    ) -> PythPrice:
        """Fetch the latest price for a single feed.

        Args:
            feed_id: Hex feed ID (with or without 0x prefix).
            max_staleness_ms: Maximum age in milliseconds before raising
                PythStaleError.

        Returns:
            PythPrice with the parsed price.

        Raises:
            PythStaleError: Price is older than max_staleness_ms.
            PythUnavailableError: Network or API error.
            PythClientError: Malformed response.
        """
        if self._client is None:
            raise PythClientError("Client not opened. Call open() first.")

        normalized = feed_id if feed_id.startswith("0x") else f"0x{feed_id}"

        url = f"{self._base_url}/v2/updates/price/latest"
        params = {"ids[]": normalized, "parsed": "true"}

        try:
            resp = await self._client.get(url, params=params)
        except (httpx.HTTPError, OSError) as exc:
            raise PythUnavailableError(f"Hermes request failed: {exc}") from exc

        if resp.status_code != 200:
            raise PythUnavailableError(
                f"Hermes returned {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise PythClientError(f"Non-JSON response: {exc}") from exc

        parsed = data.get("parsed")
        if not parsed or not isinstance(parsed, list) or len(parsed) == 0:
            raise PythClientError(f"No parsed data in response for {normalized}")

        entry = parsed[0]
        price_block = entry.get("price")
        if not isinstance(price_block, dict):
            raise PythClientError(f"Missing price block for {normalized}")

        try:
            raw_price = int(price_block["price"])
            expo = int(price_block["expo"])
            publish_time = int(price_block["publish_time"])
            raw_conf = int(price_block["conf"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PythClientError(
                f"Malformed price fields for {normalized}: {exc}"
            ) from exc

        if publish_time == 0 or raw_price == 0:
            raise PythUnavailableError(
                f"Feed {normalized} not publishing (price={raw_price}, "
                f"publish_time={publish_time})"
            )

        price = raw_price * (10.0 ** expo)
        conf = raw_conf * (10.0 ** expo)

        # Staleness check
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - (publish_time * 1000)
        if age_ms > max_staleness_ms:
            raise PythStaleError(
                f"Feed {normalized} is {age_ms}ms old "
                f"(threshold={max_staleness_ms}ms)"
            )

        return PythPrice(
            price=price,
            conf=conf,
            publish_time=publish_time,
            feed_id=entry.get("id", normalized),
        )
