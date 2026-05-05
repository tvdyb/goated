"""Provider registry — routes Kalshi tickers to TheoProviders by series prefix.

The bot maintains one registry, registers all configured providers at startup,
and asks the registry for theo on each ticker. Routing is by the first
hyphen-delimited segment of the ticker (e.g. KXSOYBEANMON-26APR3017-T1186.99
routes to the provider registered under "KXSOYBEANMON").
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable

from lipmm.theo.base import TheoProvider, TheoResult

logger = logging.getLogger(__name__)


def _series_prefix_of(ticker: str) -> str:
    """Extract the series prefix from a Kalshi ticker.

    Convention: prefix is everything before the first hyphen. So
    'KXSOYBEANMON-26APR3017-T1186.99' → 'KXSOYBEANMON'.
    """
    return ticker.split("-", 1)[0] if "-" in ticker else ticker


class TheoRegistry:
    """Maps series prefix → TheoProvider, with lifecycle helpers."""

    def __init__(self) -> None:
        self._providers: dict[str, TheoProvider] = {}

    def register(self, provider: TheoProvider) -> None:
        """Register a provider for its declared series_prefix.

        Replaces any prior registration for that prefix (last-write-wins).
        """
        prefix = provider.series_prefix
        if not prefix:
            raise ValueError("provider must declare a non-empty series_prefix")
        if prefix in self._providers:
            logger.warning(
                "TheoRegistry: replacing existing provider for prefix %r", prefix,
            )
        self._providers[prefix] = provider
        logger.info(
            "TheoRegistry: registered provider for %r (%s)",
            prefix, type(provider).__name__,
        )

    def providers(self) -> Iterable[TheoProvider]:
        return self._providers.values()

    def get(self, ticker: str) -> TheoProvider | None:
        """Look up the provider for a given ticker.

        Routing precedence:
          1. Exact-prefix match (e.g. provider with prefix "KXISMPMI" wins
             for any KXISMPMI-* ticker)
          2. Wildcard match: a provider registered with prefix "*" serves
             every ticker that no specific-prefix provider claims. Useful
             when a single file/HTTP source feeds theos for many events.

        Returns None if neither matches.
        """
        exact = self._providers.get(_series_prefix_of(ticker))
        if exact is not None:
            return exact
        return self._providers.get("*")

    async def theo(self, ticker: str) -> TheoResult:
        """Compute theo for a ticker. Returns a zero-confidence result if no
        provider is registered for this series, so callers don't need to
        special-case unmatched tickers — the standard low-confidence behavior
        (skip quoting) handles them correctly."""
        provider = self.get(ticker)
        if provider is None:
            return TheoResult(
                yes_probability=0.5,
                confidence=0.0,
                computed_at=time.time(),
                source="registry:no-provider",
                extras={"ticker": ticker, "prefix": _series_prefix_of(ticker)},
            )
        return await provider.theo(ticker)

    async def warmup_all(self) -> None:
        """Run warmup() on every registered provider concurrently."""
        if not self._providers:
            logger.warning("TheoRegistry: no providers registered at warmup")
            return
        results = await asyncio.gather(
            *(p.warmup() for p in self._providers.values()),
            return_exceptions=True,
        )
        for prefix, result in zip(self._providers.keys(), results):
            if isinstance(result, Exception):
                logger.error("TheoRegistry: warmup failed for %s: %s", prefix, result)

    async def shutdown_all(self) -> None:
        """Run shutdown() on every provider, swallowing errors."""
        await asyncio.gather(
            *(p.shutdown() for p in self._providers.values()),
            return_exceptions=True,
        )
