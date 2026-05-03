"""TheoProvider protocol and TheoResult dataclass.

The protocol is intentionally minimal: every market-type plugin must
implement just three async methods (`warmup`, `theo`, `shutdown`) plus
expose a `series_prefix` attribute for registry routing.

`TheoResult.confidence` is a CALIBRATED scale, not a free-form number:
  - 1.0  trust the theo within ±1c on a 100c scale; sticky quotes tightly
  - 0.5  trust within ±5c; sticky widens spreads proportionally
  - 0.1  unreliable; sticky bypasses, bot quotes at conservative defaults
  - 0.0  no theo available; bot refuses to quote (skip this strike)

If providers don't agree on this scale, downstream sticky/markout/risk
gates can't generalize across markets. Confidence calibration is a
contract every provider commits to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TheoResult:
    """Result of a theo computation for a single ticker.

    Always-present fields:
      yes_probability: P(Yes resolves), in [0.0, 1.0]
      confidence:      calibrated scale, see module docstring
      computed_at:     unix timestamp of the underlying data driving this result
                       (NOT the time the result was produced — what matters is
                       data freshness for downstream staleness gates)
      source:          short human-readable identifier of the provider, e.g.
                       "GBM-commodity" or "sportsbook-aggregator/v2"
      extras:          provider-specific structured detail (forward, vol, line
                       dispersion, poll counts, etc.) for debugging and
                       decision-log analysis. Schema is provider-defined.
    """

    yes_probability: float
    confidence: float
    computed_at: float
    source: str
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.yes_probability <= 1.0):
            raise ValueError(
                f"yes_probability must be in [0,1]; got {self.yes_probability}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0,1]; got {self.confidence}"
            )

    @property
    def yes_cents(self) -> int:
        """Yes probability rounded to the nearest cent (Kalshi quote scale)."""
        return int(round(self.yes_probability * 100))

    @property
    def no_cents(self) -> int:
        return 100 - self.yes_cents


@runtime_checkable
class TheoProvider(Protocol):
    """Protocol every theo plugin implements.

    A provider is responsible for:
      - Knowing what `series_prefix` it serves (e.g. "KXSOYBEANMON")
      - Fetching whatever upstream data it needs (TE scrape, sportsbook API,
        poll aggregator, etc.)
      - Caching that data appropriately for hot-path performance
      - Computing TheoResult per ticker on demand
      - Calibrating its `confidence` to the documented contract

    The bot's hot loop calls `theo(ticker)` once per strike per cycle. Providers
    MUST cache upstream data internally; theo() should be effectively O(1) — a
    cached lookup, a small computation, and a return. Providers that need to
    refresh data on a schedule should spawn an internal asyncio task in
    `warmup()` and tear it down in `shutdown()`.
    """

    series_prefix: str

    async def warmup(self) -> None:
        """Called once at bot startup. Initialize data sources, kick off
        background refresh tasks, populate caches. Bot won't start quoting
        until warmup completes for all registered providers."""
        ...

    async def shutdown(self) -> None:
        """Called once at bot shutdown. Cancel background tasks, flush state."""
        ...

    async def theo(self, ticker: str) -> TheoResult:
        """Return current theo for the given Kalshi ticker.

        MUST be fast (no upstream fetches in the hot path — use cached data
        from warmup()/background tasks). MUST return a TheoResult, never raise
        — providers that can't compute should return TheoResult with
        confidence=0.0 and an explanatory `source` like "GBM:no-forward-data".
        """
        ...
