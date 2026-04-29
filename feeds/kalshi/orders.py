"""Kalshi order builder, types, tick rounding, and quote-band enforcement.

Provides typed, validated order construction for the Kalshi REST API.
All prices are integer cents in the quote-band [1, 99]. Orders that
violate tick rounding, quote-band, or invariant constraints raise
ValueError immediately (fail-loud).

Closes gaps: GAP-080 (quote-band), GAP-081 (tick rounding),
GAP-082 (order types/TIF/flags), GAP-122 (buy_max_cost).

Non-negotiables enforced:
  - No pandas
  - Type hints on all public interfaces
  - Fail-loud on invalid prices, quantities, sides

References:
  - Phase 07 section 5 (order types, tick size, price bands)
  - Phase 07 section 6 (fees -- buy_max_cost as cost cap)
  - Kalshi API: POST /portfolio/orders payload schema
  - Rule 13.1(c): $0.01 tick, optional $0.02 override
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ── Quote-band constants ─────────────────────────────────────────────

MIN_PRICE_CENTS: int = 1    # $0.01 -- minimum valid quote price
MAX_PRICE_CENTS: int = 99   # $0.99 -- maximum valid quote price
DEFAULT_TICK_SIZE_CENTS: int = 1  # $0.01 per Rule 13.1(c)


# ── Enums ────────────────────────────────────────────────────────────


class Side(str, Enum):
    """Order side: yes or no."""
    YES = "yes"
    NO = "no"


class Action(str, Enum):
    """Order action: buy or sell."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(str, Enum):
    """Time-in-force policy."""
    GTC = "gtc"            # good till canceled
    IOC = "ioc"            # immediate or cancel
    FOK = "fok"            # fill or kill


class SelfTradePreventionType(str, Enum):
    """Self-trade prevention mode per Rule 5.15."""
    TAKER_AT_CROSS = "taker_at_cross"
    MAKER = "maker"


# ── Tick rounding ────────────────────────────────────────────────────


def round_to_tick(price_cents: int, tick_size_cents: int = DEFAULT_TICK_SIZE_CENTS) -> int:
    """Round a price in cents to the nearest valid tick.

    Args:
        price_cents: Price in cents (must be a positive integer).
        tick_size_cents: Tick size in cents (default 1, may be 2 per Rule 13.1(c)).

    Returns:
        The nearest valid tick value in cents, clamped to [MIN_PRICE_CENTS, MAX_PRICE_CENTS].

    Raises:
        ValueError: If tick_size_cents is not positive, or if the rounded
            result falls outside the quote-band [1, 99].
    """
    if tick_size_cents < 1:
        raise ValueError(f"tick_size_cents must be >= 1, got {tick_size_cents}")
    if not isinstance(price_cents, int):
        raise TypeError(f"price_cents must be int, got {type(price_cents).__name__}")

    # Round to nearest tick
    remainder = price_cents % tick_size_cents
    if remainder == 0:
        rounded = price_cents
    elif remainder >= tick_size_cents / 2:
        rounded = price_cents + (tick_size_cents - remainder)
    else:
        rounded = price_cents - remainder

    # Enforce quote-band
    if rounded < MIN_PRICE_CENTS or rounded > MAX_PRICE_CENTS:
        raise ValueError(
            f"Rounded price {rounded} cents is outside quote-band "
            f"[{MIN_PRICE_CENTS}, {MAX_PRICE_CENTS}]."
        )

    return rounded


def validate_price_cents(price_cents: int, tick_size_cents: int = DEFAULT_TICK_SIZE_CENTS) -> None:
    """Validate that a price is within the quote-band and on a valid tick.

    Args:
        price_cents: Price in integer cents.
        tick_size_cents: Tick size in cents.

    Raises:
        ValueError: If price is outside [1, 99] or not on a valid tick.
        TypeError: If price is not an int.
    """
    if not isinstance(price_cents, int):
        raise TypeError(f"price_cents must be int, got {type(price_cents).__name__}")
    if price_cents < MIN_PRICE_CENTS:
        raise ValueError(
            f"Price {price_cents} cents is below minimum quote-band "
            f"({MIN_PRICE_CENTS} cents = $0.01)."
        )
    if price_cents > MAX_PRICE_CENTS:
        raise ValueError(
            f"Price {price_cents} cents is above maximum quote-band "
            f"({MAX_PRICE_CENTS} cents = $0.99)."
        )
    if price_cents % tick_size_cents != 0:
        raise ValueError(
            f"Price {price_cents} cents is not on a {tick_size_cents}-cent tick."
        )


# ── OrderSpec ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """Immutable, fully validated order specification.

    All invariants are enforced at construction time. An OrderSpec that
    exists is guaranteed to produce a valid payload for
    KalshiClient.create_order().

    Attributes:
        ticker: Market ticker (e.g. KXSOYBEANW-26APR24-17).
        action: Buy or sell.
        side: Yes or no.
        order_type: Limit or market.
        count: Number of contracts (must be >= 1).
        yes_price_cents: Yes price in cents [1, 99] for limit orders; None for market.
        no_price_cents: No price in cents [1, 99]; None if not specified.
        time_in_force: GTC, IOC, or FOK.
        client_order_id: Optional idempotency key.
        buy_max_cost_cents: Optional max cost in cents (second-layer limit, GAP-122).
        post_only: If True, reject if would immediately fill.
        reduce_only: If True, only reduce existing position.
        self_trade_prevention: Optional self-trade prevention mode.
        tick_size_cents: Tick size used for validation (default 1).
    """

    ticker: str
    action: Action
    side: Side
    order_type: OrderType
    count: int
    yes_price_cents: int | None = None
    no_price_cents: int | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: str | None = None
    buy_max_cost_cents: int | None = None
    post_only: bool = False
    reduce_only: bool = False
    self_trade_prevention: SelfTradePreventionType | None = None
    tick_size_cents: int = DEFAULT_TICK_SIZE_CENTS

    def __post_init__(self) -> None:
        """Validate all invariants at construction time."""
        # Ticker
        if not self.ticker or not isinstance(self.ticker, str):
            raise ValueError(f"ticker must be a non-empty string, got {self.ticker!r}")

        # Action and side type checks
        if not isinstance(self.action, Action):
            raise ValueError(f"action must be Action enum, got {self.action!r}")
        if not isinstance(self.side, Side):
            raise ValueError(f"side must be Side enum, got {self.side!r}")
        if not isinstance(self.order_type, OrderType):
            raise ValueError(f"order_type must be OrderType enum, got {self.order_type!r}")

        # Count
        if not isinstance(self.count, int) or self.count < 1:
            raise ValueError(f"count must be a positive integer, got {self.count!r}")

        # Price validation for limit orders
        if self.order_type == OrderType.LIMIT:
            if self.yes_price_cents is None and self.no_price_cents is None:
                raise ValueError(
                    "Limit orders must specify at least one of yes_price_cents "
                    "or no_price_cents."
                )
            if self.yes_price_cents is not None:
                validate_price_cents(self.yes_price_cents, self.tick_size_cents)
            if self.no_price_cents is not None:
                validate_price_cents(self.no_price_cents, self.tick_size_cents)

        # Market orders should not have prices
        if self.order_type == OrderType.MARKET:
            if self.yes_price_cents is not None or self.no_price_cents is not None:
                raise ValueError(
                    "Market orders must not specify yes_price_cents or no_price_cents."
                )

        # buy_max_cost validation
        if self.buy_max_cost_cents is not None:
            if not isinstance(self.buy_max_cost_cents, int) or self.buy_max_cost_cents < 1:
                raise ValueError(
                    f"buy_max_cost_cents must be a positive integer, "
                    f"got {self.buy_max_cost_cents!r}"
                )

        # TimeInForce
        if not isinstance(self.time_in_force, TimeInForce):
            raise ValueError(
                f"time_in_force must be TimeInForce enum, got {self.time_in_force!r}"
            )

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the dict expected by KalshiClient.create_order().

        Returns:
            Keyword arguments dict matching create_order's signature.
        """
        payload: dict[str, Any] = {
            "ticker": self.ticker,
            "action": self.action.value,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "count": self.count,
            "time_in_force": self.time_in_force.value,
        }
        if self.yes_price_cents is not None:
            payload["yes_price"] = self.yes_price_cents
        if self.no_price_cents is not None:
            payload["no_price"] = self.no_price_cents
        if self.client_order_id is not None:
            payload["client_order_id"] = self.client_order_id
        if self.buy_max_cost_cents is not None:
            payload["buy_max_cost"] = self.buy_max_cost_cents
        if self.post_only:
            payload["post_only"] = True
        if self.reduce_only:
            payload["reduce_only"] = True
        if self.self_trade_prevention is not None:
            payload["self_trade_prevention_type"] = self.self_trade_prevention.value
        return payload


# ── Builder functions ────────────────────────────────────────────────


def build_limit_order(
    *,
    ticker: str,
    action: Action,
    side: Side,
    count: int,
    yes_price_cents: int | None = None,
    no_price_cents: int | None = None,
    time_in_force: TimeInForce = TimeInForce.GTC,
    client_order_id: str | None = None,
    buy_max_cost_cents: int | None = None,
    post_only: bool = True,
    reduce_only: bool = False,
    self_trade_prevention: SelfTradePreventionType | None = None,
    tick_size_cents: int = DEFAULT_TICK_SIZE_CENTS,
) -> OrderSpec:
    """Build a validated limit order specification.

    All prices are rounded to the nearest tick before validation.
    Defaults to post_only=True (suitable for maker/LIP quoting).

    Args:
        ticker: Market ticker.
        action: Buy or sell.
        side: Yes or no.
        count: Number of contracts (>= 1).
        yes_price_cents: Yes price in cents, will be tick-rounded.
        no_price_cents: No price in cents, will be tick-rounded.
        time_in_force: Order duration policy (default GTC).
        client_order_id: Optional idempotency key.
        buy_max_cost_cents: Optional max cost cap in cents.
        post_only: Default True for maker quotes.
        reduce_only: Default False.
        self_trade_prevention: Optional STP mode.
        tick_size_cents: Tick size in cents (default 1).

    Returns:
        Validated OrderSpec.

    Raises:
        ValueError: On any invalid input.
    """
    # Round prices to tick if provided
    rounded_yes: int | None = None
    rounded_no: int | None = None
    if yes_price_cents is not None:
        rounded_yes = round_to_tick(yes_price_cents, tick_size_cents)
    if no_price_cents is not None:
        rounded_no = round_to_tick(no_price_cents, tick_size_cents)

    return OrderSpec(
        ticker=ticker,
        action=action,
        side=side,
        order_type=OrderType.LIMIT,
        count=count,
        yes_price_cents=rounded_yes,
        no_price_cents=rounded_no,
        time_in_force=time_in_force,
        client_order_id=client_order_id,
        buy_max_cost_cents=buy_max_cost_cents,
        post_only=post_only,
        reduce_only=reduce_only,
        self_trade_prevention=self_trade_prevention,
        tick_size_cents=tick_size_cents,
    )


def build_two_sided_quote(
    *,
    ticker: str,
    side: Side,
    bid_price_cents: int,
    ask_price_cents: int,
    bid_count: int,
    ask_count: int,
    time_in_force: TimeInForce = TimeInForce.GTC,
    client_order_id_prefix: str | None = None,
    buy_max_cost_cents: int | None = None,
    post_only: bool = True,
    self_trade_prevention: SelfTradePreventionType | None = None,
    tick_size_cents: int = DEFAULT_TICK_SIZE_CENTS,
) -> tuple[OrderSpec, OrderSpec]:
    """Build a two-sided quote (bid + ask) for a single market.

    The bid is a buy-side limit order at bid_price_cents.
    The ask is a sell-side limit order at ask_price_cents.
    Both are on the same Side (yes or no).

    For a Yes-side quote: bid buys Yes at bid_price, ask sells Yes at ask_price.
    bid_price_cents must be strictly less than ask_price_cents (positive spread).

    Args:
        ticker: Market ticker.
        side: Yes or no (both legs quote the same side).
        bid_price_cents: Bid (buy) price in cents.
        ask_price_cents: Ask (sell) price in cents.
        bid_count: Number of contracts on bid side.
        ask_count: Number of contracts on ask side.
        time_in_force: Default GTC.
        client_order_id_prefix: If set, appends '-bid'/'-ask' for idempotency.
        buy_max_cost_cents: Optional max cost cap on bid leg.
        post_only: Default True (maker quotes for LIP).
        self_trade_prevention: Optional STP mode.
        tick_size_cents: Tick size in cents.

    Returns:
        Tuple of (bid_order, ask_order) as validated OrderSpec objects.

    Raises:
        ValueError: If bid >= ask, or any other invariant violation.
    """
    # Round prices first
    rounded_bid = round_to_tick(bid_price_cents, tick_size_cents)
    rounded_ask = round_to_tick(ask_price_cents, tick_size_cents)

    if rounded_bid >= rounded_ask:
        raise ValueError(
            f"Bid price ({rounded_bid} cents) must be strictly less than "
            f"ask price ({rounded_ask} cents). Spread must be positive."
        )

    bid_client_id: str | None = None
    ask_client_id: str | None = None
    if client_order_id_prefix is not None:
        bid_client_id = f"{client_order_id_prefix}-bid"
        ask_client_id = f"{client_order_id_prefix}-ask"

    # Determine price field based on side
    if side == Side.YES:
        bid_yes: int | None = rounded_bid
        bid_no: int | None = None
        ask_yes: int | None = rounded_ask
        ask_no: int | None = None
    else:
        # For No-side quotes, use no_price_cents
        bid_yes = None
        bid_no = rounded_bid
        ask_yes = None
        ask_no = rounded_ask

    bid_order = OrderSpec(
        ticker=ticker,
        action=Action.BUY,
        side=side,
        order_type=OrderType.LIMIT,
        count=bid_count,
        yes_price_cents=bid_yes,
        no_price_cents=bid_no,
        time_in_force=time_in_force,
        client_order_id=bid_client_id,
        buy_max_cost_cents=buy_max_cost_cents,
        post_only=post_only,
        self_trade_prevention=self_trade_prevention,
        tick_size_cents=tick_size_cents,
    )

    ask_order = OrderSpec(
        ticker=ticker,
        action=Action.SELL,
        side=side,
        order_type=OrderType.LIMIT,
        count=ask_count,
        yes_price_cents=ask_yes,
        no_price_cents=ask_no,
        time_in_force=time_in_force,
        client_order_id=ask_client_id,
        post_only=post_only,
        self_trade_prevention=self_trade_prevention,
        tick_size_cents=tick_size_cents,
    )

    return bid_order, ask_order
