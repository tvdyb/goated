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
    """Inputs to `place_order`. All-prices-in-cents convention."""
    ticker: str
    action: Action          # "buy" or "sell"
    side: Side              # "yes" or "no"
    count: int              # contracts
    limit_price_cents: int  # 1..99
    post_only: bool = True  # never cross the spread


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


@dataclass(frozen=True)
class OrderbookLevels:
    """Snapshot of one market's book. Each list is sorted highest-first.
    `yes_levels` are bids on Yes (descending price); `no_levels` are bids
    on No (= asks on Yes when inverted).

    `has_subcent_ticks` is set True when the source orderbook contained
    any price level at a fractional-cent granularity (e.g., $0.4510 =
    45.1¢). Kalshi's order-placement API is integer-cents-only, so the
    bot cannot quote competitively in such markets — the runner skips
    them with a warning. Operator-visible flag so they know which
    markets are blocked."""
    ticker: str
    yes_levels: list[tuple[int, float]]   # [(price_cents, size), ...]
    no_levels: list[tuple[int, float]]
    has_subcent_ticks: bool = False


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
