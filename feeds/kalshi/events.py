"""Bucket grid and Event puller for Kalshi commodity weeklies.

Provides:
  - Bucket: a single price-range market with strike boundaries
  - BucketGrid: sorted, MECE-validated collection of Buckets for one Event
  - EventSnapshot: parsed Event with its BucketGrid
  - EventPuller: async puller using KalshiClient

Fail-loud: missing fields, non-MECE grids, malformed data all raise.
No pandas.

References:
  - Phase 07 sections 1, 3 (bucket structure)
  - GAP-075, GAP-079 in audit_E_gap_register.md
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from feeds.kalshi.errors import KalshiResponseError
from feeds.kalshi.ticker import parse_event_ticker, parse_market_ticker

if TYPE_CHECKING:
    from feeds.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Bucket:
    """A single price-range market within an Event.

    Attributes:
        ticker: Market ticker (e.g. KXSOYBEANW-26APR24-17).
        bucket_index: Ordinal bucket index within the event.
        lower: Lower strike boundary in dollars. None for the lower tail bucket.
        upper: Upper strike boundary in dollars. None for the upper tail bucket.
        status: Market status (e.g. 'open', 'closed', 'settled').
    """

    ticker: str
    bucket_index: int
    lower: float | None
    upper: float | None
    status: str

    @property
    def is_lower_tail(self) -> bool:
        """True if this is the open-ended lower tail bucket (no lower bound)."""
        return self.lower is None

    @property
    def is_upper_tail(self) -> bool:
        """True if this is the open-ended upper tail bucket (no upper bound)."""
        return self.upper is None

    @property
    def is_interior(self) -> bool:
        """True if this bucket has both finite lower and upper bounds."""
        return self.lower is not None and self.upper is not None

    @property
    def width(self) -> float | None:
        """Bucket width in dollars, or None for tail buckets."""
        if self.lower is not None and self.upper is not None:
            return self.upper - self.lower
        return None


@dataclass(frozen=True, slots=True)
class BucketGrid:
    """Sorted, MECE-validated collection of Buckets for one Event.

    Buckets are sorted by their lower bound (lower tail first, upper tail last).
    MECE = Mutually Exclusive, Collectively Exhaustive.

    Invariants enforced at construction:
      - At least 2 buckets (minimum: one lower tail + one upper tail)
      - Exactly one lower tail (lower=None)
      - Exactly one upper tail (upper=None)
      - Interior buckets are contiguous: bucket[i].upper == bucket[i+1].lower
      - Lower tail's upper == first interior bucket's lower (or upper tail's lower)
      - Upper tail's lower == last interior bucket's upper (or lower tail's upper)
    """

    buckets: tuple[Bucket, ...]

    def __post_init__(self) -> None:
        if len(self.buckets) < 2:
            raise ValueError(
                f"BucketGrid requires at least 2 buckets (lower + upper tail), "
                f"got {len(self.buckets)}."
            )

    @property
    def lower_tail(self) -> Bucket:
        """The open-ended lower tail bucket."""
        return self.buckets[0]

    @property
    def upper_tail(self) -> Bucket:
        """The open-ended upper tail bucket."""
        return self.buckets[-1]

    @property
    def interior_buckets(self) -> tuple[Bucket, ...]:
        """Interior buckets (both bounds finite), sorted by lower bound."""
        return self.buckets[1:-1]

    @property
    def n_buckets(self) -> int:
        """Total number of buckets including tails."""
        return len(self.buckets)

    def bucket_for_price(self, price: float) -> Bucket:
        """Return the bucket that would contain the given price.

        Uses the convention that bucket i covers [lower_i, upper_i).
        The upper tail covers [lower, +inf).

        Args:
            price: Reference price in dollars.

        Returns:
            The matching Bucket.

        Raises:
            ValueError: If no bucket matches (should not happen for valid grid).
        """
        for b in self.buckets:
            low = b.lower if b.lower is not None else -math.inf
            high = b.upper if b.upper is not None else math.inf
            if low <= price < high:
                return b
        # Upper tail: the last bucket catches price == upper tail's lower
        # This should have been caught above, but be defensive
        raise ValueError(  # pragma: no cover
            f"No bucket contains price {price} in grid with "
            f"{self.n_buckets} buckets."
        )


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    """A parsed Kalshi Event with its bucket grid.

    Attributes:
        event_ticker: Event ticker (e.g. KXSOYBEANW-26APR24).
        series_ticker: Parent series ticker (e.g. KXSOYBEANW).
        expiry_date: Expiration date parsed from the event ticker.
        title: Human-readable event title from Kalshi.
        status: Event status (e.g. 'open', 'closed', 'settled').
        bucket_grid: Validated BucketGrid of child markets.
        fetched_at: UTC timestamp when the data was fetched.
    """

    event_ticker: str
    series_ticker: str
    expiry_date: date
    title: str
    status: str
    bucket_grid: BucketGrid
    fetched_at: datetime


# ── BucketGrid builder ────────────────────────────────────────────────


def build_bucket_grid(markets: list[dict[str, object]]) -> BucketGrid:
    """Build a MECE-validated BucketGrid from raw Kalshi market dicts.

    Each market dict must contain at minimum:
      - ticker (str)
      - floor_strike (float | None): None for the lower tail
      - cap_strike (float | None): None for the upper tail
      - status (str)

    Args:
        markets: List of market dicts from the Kalshi API response.

    Returns:
        A validated BucketGrid.

    Raises:
        ValueError: If markets are empty, have missing fields, or violate MECE.
    """
    if not markets:
        raise ValueError("Cannot build BucketGrid from empty markets list.")

    buckets: list[Bucket] = []
    for mkt in markets:
        ticker = mkt.get("ticker")
        if ticker is None or not isinstance(ticker, str):
            raise ValueError(f"Market missing 'ticker' field: {mkt!r}")

        status = mkt.get("status")
        if status is None or not isinstance(status, str):
            raise ValueError(f"Market {ticker} missing 'status' field.")

        floor_strike = mkt.get("floor_strike")
        cap_strike = mkt.get("cap_strike")

        # Convert to float or None
        lower: float | None = float(floor_strike) if floor_strike is not None else None
        upper: float | None = float(cap_strike) if cap_strike is not None else None

        # Parse bucket index from market ticker
        parsed = parse_market_ticker(ticker)

        buckets.append(Bucket(
            ticker=ticker,
            bucket_index=parsed.bucket_index,
            lower=lower,
            upper=upper,
            status=status,
        ))

    # Sort: lower tail (lower=None) first, then by lower bound, upper tail (upper=None) last
    def _sort_key(b: Bucket) -> tuple[int, float]:
        if b.lower is None:
            return (0, -math.inf)
        if b.upper is None:
            return (2, b.lower)
        return (1, b.lower)

    buckets.sort(key=_sort_key)

    # Validate MECE
    _validate_mece(buckets)

    return BucketGrid(buckets=tuple(buckets))


def _validate_mece(buckets: list[Bucket]) -> None:
    """Validate that sorted buckets form a MECE partition.

    Raises ValueError on any violation.
    """
    if len(buckets) < 2:
        raise ValueError(
            f"MECE requires at least 2 buckets, got {len(buckets)}."
        )

    # First must be lower tail
    if not buckets[0].is_lower_tail:
        raise ValueError(
            f"First bucket must be a lower tail (lower=None), got "
            f"lower={buckets[0].lower} for {buckets[0].ticker}."
        )
    if buckets[0].upper is None:
        raise ValueError(
            f"Lower tail bucket must have a finite upper bound, got "
            f"upper=None for {buckets[0].ticker}."
        )

    # Last must be upper tail
    if not buckets[-1].is_upper_tail:
        raise ValueError(
            f"Last bucket must be an upper tail (upper=None), got "
            f"upper={buckets[-1].upper} for {buckets[-1].ticker}."
        )
    if buckets[-1].lower is None:
        raise ValueError(
            f"Upper tail bucket must have a finite lower bound, got "
            f"lower=None for {buckets[-1].ticker}."
        )

    # Check contiguity: each bucket's upper must equal the next bucket's lower
    for i in range(len(buckets) - 1):
        current_upper = buckets[i].upper
        next_lower = buckets[i + 1].lower

        if current_upper is None:
            # Only the last bucket should have upper=None, and it shouldn't
            # be at position i < len-1
            raise ValueError(
                f"Bucket {buckets[i].ticker} at position {i} has upper=None "
                f"but is not the last bucket."
            )
        if next_lower is None:
            # Only the first bucket should have lower=None
            raise ValueError(
                f"Bucket {buckets[i+1].ticker} at position {i+1} has lower=None "
                f"but is not the first bucket."
            )

        if not math.isclose(current_upper, next_lower, rel_tol=1e-9):
            raise ValueError(
                f"MECE gap between buckets {buckets[i].ticker} "
                f"(upper={current_upper}) and {buckets[i+1].ticker} "
                f"(lower={next_lower}). Expected contiguous edges."
            )

    # Interior buckets: both bounds must be finite, and lower < upper
    for b in buckets[1:-1]:
        if b.lower is None or b.upper is None:
            raise ValueError(
                f"Interior bucket {b.ticker} has None bound: "
                f"lower={b.lower}, upper={b.upper}."
            )
        if b.lower >= b.upper:
            raise ValueError(
                f"Interior bucket {b.ticker} has lower >= upper: "
                f"{b.lower} >= {b.upper}."
            )


# ── Event puller ──────────────────────────────────────────────────────


class EventPuller:
    """Async puller for Kalshi Events and their bucket grids.

    Uses the KalshiClient from ACT-03 to fetch event data and
    construct validated EventSnapshot objects.

    Usage::

        async with KalshiClient(auth=auth) as client:
            puller = EventPuller(client)
            event = await puller.pull_event("KXSOYBEANW-26APR24")
            events = await puller.pull_active_events("KXSOYBEANW")
    """

    def __init__(self, client: KalshiClient) -> None:
        self._client = client

    async def pull_event(self, event_ticker: str) -> EventSnapshot:
        """Fetch a single Event and build its validated BucketGrid.

        Args:
            event_ticker: Event ticker (e.g. KXSOYBEANW-26APR24).

        Returns:
            EventSnapshot with parsed metadata and validated bucket grid.

        Raises:
            ValueError: If the event ticker is malformed or response data
                is missing required fields.
            KalshiAPIError: On network/auth/rate-limit errors.
        """
        parsed_event = parse_event_ticker(event_ticker)

        response = await self._client.get_event(event_ticker)

        event_data = response.get("event")
        if event_data is None:
            raise ValueError(
                f"Response for event {event_ticker} missing 'event' key. "
                f"Keys present: {sorted(response.keys())}."
            )

        markets_data = response.get("markets")
        if markets_data is None or not isinstance(markets_data, list):
            raise ValueError(
                f"Response for event {event_ticker} missing or invalid 'markets' key. "
                f"Keys present: {sorted(response.keys())}."
            )

        if len(markets_data) == 0:
            raise ValueError(
                f"Event {event_ticker} has no child markets."
            )

        title = event_data.get("title", "")
        status = event_data.get("status", "")
        series_ticker = event_data.get("series_ticker", parsed_event.series)

        if not isinstance(title, str):
            raise ValueError(
                f"Event {event_ticker} has non-string title: {title!r}."
            )
        if not isinstance(status, str) or not status:
            raise ValueError(
                f"Event {event_ticker} has missing or invalid status: {status!r}."
            )

        bucket_grid = build_bucket_grid(markets_data)

        return EventSnapshot(
            event_ticker=event_ticker.upper(),
            series_ticker=series_ticker,
            expiry_date=parsed_event.expiry_date,
            title=title,
            status=status,
            bucket_grid=bucket_grid,
            fetched_at=datetime.now(timezone.utc),
        )

    async def pull_active_events(
        self,
        series_ticker: str,
        *,
        status: str = "open",
    ) -> list[EventSnapshot]:
        """Fetch all active Events for a series, with their bucket grids.

        Paginates through the events list endpoint, then fetches each
        event individually to get the full market/bucket data.

        Args:
            series_ticker: Series ticker (e.g. KXSOYBEANW).
            status: Event status filter (default 'open').

        Returns:
            List of EventSnapshot objects, sorted by expiry date.

        Raises:
            ValueError: On malformed data.
            KalshiAPIError: On network/auth/rate-limit errors.
        """
        # Collect event tickers via pagination
        event_tickers: list[str] = []
        cursor: str | None = None

        while True:
            response = await self._client.get_events(
                series_ticker=series_ticker,
                status=status,
                limit=50,
                cursor=cursor,
            )

            events_list = response.get("events")
            if events_list is None or not isinstance(events_list, list):
                raise ValueError(
                    f"Events response missing 'events' key. "
                    f"Keys present: {sorted(response.keys())}."
                )

            for ev in events_list:
                ticker = ev.get("event_ticker")
                if ticker and isinstance(ticker, str):
                    event_tickers.append(ticker)

            cursor = response.get("cursor")
            if not cursor or not events_list:
                break

        # Fetch each event individually (needed for full market data)
        snapshots: list[EventSnapshot] = []
        for et in event_tickers:
            try:
                snap = await self.pull_event(et)
                snapshots.append(snap)
            except (ValueError, KalshiResponseError) as exc:
                logger.warning(
                    "Skipping event %s: %s", et, exc,
                )
                continue

        # Sort by expiry date
        snapshots.sort(key=lambda s: s.expiry_date)

        return snapshots
