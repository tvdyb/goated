"""Order execution layer.

Two pieces:
  - `ExchangeClient`: protocol the bot's order manager depends on. The actual
    Kalshi REST client adapts to it; future exchanges (Polymarket, Manifold,
    custom prediction markets) implement the same protocol and the rest of
    the framework works unchanged.
  - `OrderManager`: state-aware order lifecycle for one strike-side
    (place / amend / cancel-and-replace / track resting state). Idempotent
    against transient API errors. Doesn't know what to quote — that's the
    QuotingStrategy's job. It just executes a SideDecision faithfully.
"""

from lipmm.execution.base import (
    Balance,
    ExchangeClient,
    Order,
    OrderbookLevels,
    Position,
    PlaceOrderRequest,
)
from lipmm.execution.order_manager import OrderManager, RestingOrder, SideExecution

__all__ = [
    "Balance",
    "ExchangeClient",
    "Order",
    "OrderbookLevels",
    "OrderManager",
    "PlaceOrderRequest",
    "Position",
    "RestingOrder",
    "SideExecution",
]
