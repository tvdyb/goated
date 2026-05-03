"""Concrete `ExchangeClient` adapters.

Each adapter wraps a venue-specific client and exposes the lipmm
`ExchangeClient` protocol. This is the ONE place in lipmm where we
deliberately depend on packages outside the framework — `feeds/kalshi/`
for KalshiExchangeAdapter, `feeds/<venue>/` for future venues.

**Architectural exception**: lipmm core (`theo`, `quoting`, `execution.base`,
`runner`, `risk`, `observability`) remains hermetic — zero imports from
`engine/`, `deploy/`, or `feeds/`. Adapters under `lipmm/execution/adapters/`
are the documented exception. They MAY import from per-venue feed packages
because their job IS to translate venue-specific clients into the protocol.

If you're adding support for a new venue, drop a new file in this
directory and register the class in this __init__.py.
"""

from lipmm.execution.adapters.kalshi import KalshiExchangeAdapter

__all__ = ["KalshiExchangeAdapter"]
