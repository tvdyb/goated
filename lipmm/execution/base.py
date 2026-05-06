"""ExchangeClient protocol + dataclasses describing exchange concepts.

The framework defines what it NEEDS from an exchange (place order, cancel
order, fetch orderbook, etc.) without committing to a specific API shape.
Adapters wrap concrete clients (Kalshi REST, Polymarket, etc.) into this
protocol.

Why this matters:
  - Integration tests can use a `MockExchangeClient` instead of hitting
    Kalshi production.
  - Future exchange support is a single adapter file, not a framework rewrite.
  - The `OrderManager` and bot loop depend only on the protocol — they
    don't know what exchange is underneath.

What's deliberately NOT in this protocol:
  - Authentication mechanics (each exchange has its own; adapter handles it)
  - Rate limiting (adapter handles; framework just calls and assumes the
    adapter throttles correctly)
  - Series/event listing (separate concern from order execution; would live
    in a future `MarketCatalog` protocol)
  - Settlement / fills history (decision logger pulls from exchange directly
    in current design; could be unified later if needed)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable


# ── Order lifecycle dataclasses ────────────────────────────────────────


Side = Literal["yes", "no"]
Action = Literal["buy", "sell"]


@dataclass(frozen=True)
class PlaceOrderRequest:
    """Inputs to `place_order`.

    Two unit views:
      - `limit_price_cents: int` (1..99) — operator/legacy facing
      - `limit_price_t1c: int | None` — tenths-of-a-cent (10..990 for
        whole-cent, e.g. 977 for 97.7¢). When set, the adapter routes
        through Kalshi's fractional path on subcent markets. When
        None, derived from cents × 10.
    """
    ticker: str
    action: Action          # "buy" or "sell"
    side: Side              # "yes" or "no"
    count: int              # contracts
    limit_price_cents: int  # 1..99
    post_only: bool = True  # never cross the spread
    limit_price_t1c: int | None = None
    """Optional fine-grained price in tenths-of-a-cent (10 = 1¢).
    When set, the adapter prefers it over `limit_price_cents` and
    decides whether to send Kalshi an integer (whole cent) or a
    fractional `yes_price_dollars` (sub-cent)."""

    def effective_t1c(self) -> int:
        """Return the price in t1c, derived from cents if t1c is None."""
        return self.limit_price_t1c if self.limit_price_t1c is not None else self.limit_price_cents * 10


@dataclass(frozen=True)
class Order:
    """An order's exchange-side state. Adapters fill what they have."""
    order_id: str
    ticker: str
    action: Action
    side: Side
    limit_price_cents: int
    remaining_count: int
    status: str             # "resting", "executed", "cancelled", etc.
    limit_price_t1c: int | None = None
    """Fine-grained price (t1c) when known. None for orders parsed
    from non-subcent markets (cents is sufficient there)."""


TickSchedule = list[tuple[int, int, int]]
"""A market's tick schedule. Each entry is `(min_t1c, max_t1c, tick_t1c)`
specifying that prices in `[min_t1c, max_t1c)` quote at `tick_t1c`
granularity. Ranges must be contiguous and cover [10, 990] (1¢..99¢).

Examples:
  - All whole-cent (default):
        [(10, 990, 10)]
  - All sub-cent:
        [(10, 990, 1)]
  - U-shape (Kalshi's edge-sub-cent markets):
        [(10, 100, 1), (100, 900, 10), (900, 990, 1)]
"""


def tick_at(schedule: TickSchedule, price_t1c: int) -> int:
    """Look up the tick size in t1c that applies at `price_t1c`.
    Falls back to 10 (1¢) if no range matches — defensive."""
    for lo, hi, tick in schedule:
        if lo <= price_t1c < hi:
            return tick
    return 10


def schedule_has_subcent(schedule: TickSchedule) -> bool:
    """True iff any range in the schedule has sub-cent granularity."""
    return any(tick < 10 for (_lo, _hi, tick) in schedule)


@dataclass(frozen=True)
class OrderbookLevels:
    """Snapshot of one market's book. Each list is sorted highest-first.
    `yes_levels` are bids on Yes (descending price); `no_levels` are bids
    on No (= asks on Yes when inverted).

    **Unit**: `(price_t1c, size)` where `t1c` is **tenths-of-a-cent**
    (10 t1c = 1¢, 1 t1c = 0.1¢). On normal whole-cent markets, every
    `price_t1c` is a multiple of 10 (e.g., 450 = 45¢). On subcent
    markets, levels can be anything (e.g., 977 = 97.7¢).

    `tick_schedule` is the per-range tick granularity. Some Kalshi
    markets use a "U-shape" schedule with 0.1¢ ticks at the edges
    (0-10¢ and 90-100¢) and 1¢ ticks in the middle (10-90¢). The
    strategy queries `tick_at(schedule, price)` to find the adjacent
    quotable price. Default `[(10, 990, 10)]` is whole-cent
    everywhere.

    `has_subcent_ticks` is True iff the schedule contains any
    sub-cent range — convenience flag for dashboards. The adapter
    routes through Kalshi's fractional path on subcent prices with
    graceful fallback to integer cents on rejection."""
    ticker: str
    yes_levels: list[tuple[int, float]]   # [(price_t1c, size), ...]
    no_levels: list[tuple[int, float]]
    has_subcent_ticks: bool = False
    tick_schedule: TickSchedule = ()  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Default schedule = whole-cent everywhere. Done in __post_init__
        # because dataclass(frozen=True) can't have mutable defaults.
        if not self.tick_schedule:
            object.__setattr__(self, "tick_schedule", [(10, 990, 10)])

    def tick_at(self, price_t1c: int) -> int:
        return tick_at(self.tick_schedule, price_t1c)


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: int            # positive = long Yes, negative = long No
    avg_cost_cents: int
    realized_pnl_dollars: float
    fees_paid_dollars: float


@dataclass(frozen=True)
class Balance:
    cash_dollars: float
    portfolio_value_dollars: float


# ── The protocol ───────────────────────────────────────────────────────


@runtime_checkable
class ExchangeClient(Protocol):
    """The minimum interface for executing LIP-style market making.

    All methods are async because exchange APIs are network-bound.
    Adapters MUST translate exchange-specific errors into one of:
      - return `None` / empty container for "not found"
      - raise a known exception class for "exchange error / retry later"
      - raise `ValueError` for "request was malformed"
    """

    async def place_order(
        self, request: PlaceOrderRequest,
    ) -> Order | None:
        """Place a new order. Returns the resulting Order on success,
        None if the exchange rejected (e.g., insufficient funds, post-only
        cross). Adapter is responsible for distinguishing rejection from
        transient error (the latter should raise)."""
        ...

    async def amend_order(
        self, order_id: str, *,
        new_limit_price_cents: int | None = None,
        new_count: int | None = None,
    ) -> Order | None:
        """Modify an existing order. Returns updated Order on success,
        None if amend is rejected (some exchanges don't support amend at
        all — adapter returns None). The framework is expected to fall
        back to cancel+place when amend returns None."""
        ...

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order. Returns True if the exchange confirmed the
        cancel, False if order was already gone (already filled / cancelled).
        Idempotent: calling with a stale id should NOT raise."""
        ...

    async def cancel_orders(self, order_ids: list[str]) -> dict[str, bool]:
        """Batch cancel. Returns {order_id: success_bool}. Adapters that
        don't support batch should loop over `cancel_order` internally."""
        ...

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        """Snapshot the orderbook for one ticker."""
        ...

    async def list_resting_orders(self) -> list[Order]:
        """All currently-resting orders for the authenticated account."""
        ...

    async def list_positions(self) -> list[Position]:
        """All non-zero positions for the authenticated account."""
        ...

    async def get_balance(self) -> Balance:
        """Account balance + portfolio value."""
        ...
