"""Spread-capture quoter for Kalshi commodity monthly half-line markets.

Posts two-sided quotes around RND-derived fair value with:
- Configurable spread (target 3-4c, tighter than incumbent 6-8c)
- Inventory skew (widen the side where inventory is growing)
- Fee-aware gating (skip if spread < round-trip fee)
- Risk gate integration (ACT-12)
- Settlement gate integration (Phase 60)
- Taker-imbalance withdrawal (Phase 60)
- post_only=True on every order
- Anti-arb check across strikes within the same event
- Never crosses the spread

The edge is spread capture, NOT model-vs-midpoint disagreement (Phase 55).

Closes gaps: GAP-001 (partial), GAP-002, GAP-022 (partial), GAP-023,
GAP-029, GAP-145.

Non-negotiables: no pandas, fail-loud, synchronous, type hints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np

from engine.rnd.bucket_integrator import BucketPrices
from feeds.kalshi.orders import (
    MAX_PRICE_CENTS,
    MIN_PRICE_CENTS,
    round_to_tick,
)
from fees.kalshi_fees import maker_fee

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QuoterConfig:
    """Quoter tuning parameters.

    Attributes:
        min_half_spread_cents: Minimum half-spread in cents (each side).
            Default 2c -> 4c total spread.
        max_half_spread_cents: Maximum half-spread. Default 4c -> 8c total.
        inventory_skew_gamma: Gamma parameter for inventory skew.
            Higher = more aggressive widening on inventory side.
            Units: cents per contract of signed inventory.
        max_contracts_per_strike: Maximum contracts to post per strike side.
        fee_threshold_cents: Minimum spread required above round-trip
            maker fee (in cents) to post. Default 1c.
        taker_rate: Kalshi taker fee rate (for fee calculation).
        maker_fraction: Maker fee as fraction of taker fee.
        settlement_gate_enabled: Whether settlement gate affects quoting.
        taker_imbalance_enabled: Whether taker-imbalance signal withdraws sides.
        atm_range_cents: Range around forward to consider "near ATM" for
            preferential quoting. Default 60c.
    """

    min_half_spread_cents: int = 2
    max_half_spread_cents: int = 4
    inventory_skew_gamma: float = 0.1
    max_contracts_per_strike: int = 50
    fee_threshold_cents: int = 1
    taker_rate: float = 0.07
    maker_fraction: float = 0.25
    settlement_gate_enabled: bool = True
    taker_imbalance_enabled: bool = True
    atm_range_cents: float = 60.0


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class QuoteActionType(Enum):
    PLACE_BID = auto()
    PLACE_ASK = auto()
    CANCEL = auto()
    NO_ACTION = auto()


@dataclass(frozen=True, slots=True)
class QuoteAction:
    """A single quoting decision for one strike + side.

    Attributes:
        action_type: What to do.
        market_ticker: Kalshi market ticker.
        strike: Strike value in the underlying unit.
        price_cents: Quote price in cents (for PLACE_BID/PLACE_ASK).
        size: Number of contracts (for PLACE_BID/PLACE_ASK).
        reason: Human-readable reason for this action.
    """

    action_type: QuoteActionType
    market_ticker: str
    strike: float
    price_cents: int = 0
    size: int = 0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class OrderbookLevel:
    """Single price level from the Kalshi orderbook."""

    price_cents: int
    size: int


@dataclass(frozen=True, slots=True)
class StrikeBook:
    """Orderbook state for a single Kalshi half-line market.

    Attributes:
        market_ticker: Kalshi market ticker.
        strike: Strike value (e.g. 1190 for "above 1190c").
        best_bid_cents: Best resting bid (0 if empty).
        best_ask_cents: Best resting ask (100 if empty).
    """

    market_ticker: str
    strike: float
    best_bid_cents: int
    best_ask_cents: int


@dataclass(frozen=True, slots=True)
class EventBook:
    """Aggregated orderbook state for an entire Kalshi event (all strikes).

    Attributes:
        event_ticker: Event ticker (e.g. KXSOYBEANMON-26MAY01).
        strike_books: Per-strike orderbook snapshots, ordered by strike.
    """

    event_ticker: str
    strike_books: list[StrikeBook]


# ---------------------------------------------------------------------------
# Core quoter
# ---------------------------------------------------------------------------


def _maker_fee_cents(price_cents: int, taker_rate: float, maker_fraction: float) -> int:
    """Compute maker fee in cents (ceiling) for a given price."""
    price_dollars = price_cents / 100.0
    fee_dollars = maker_fee(price_dollars, taker_rate=taker_rate, maker_fraction=maker_fraction)
    return int(fee_dollars * 100 + 0.999)  # ceiling


def _round_trip_maker_fee_cents(
    bid_cents: int,
    ask_cents: int,
    taker_rate: float,
    maker_fraction: float,
) -> int:
    """Round-trip maker fee in cents for a bid+ask pair."""
    return (
        _maker_fee_cents(bid_cents, taker_rate, maker_fraction)
        + _maker_fee_cents(ask_cents, taker_rate, maker_fraction)
    )


def compute_quotes(
    rnd_prices: BucketPrices,
    event_book: EventBook,
    inventory: dict[str, int],
    risk_ok: bool,
    gate_size_mult: float,
    gate_spread_mult: float,
    imbalance_withdraw_side: str | None,
    config: QuoterConfig,
) -> list[QuoteAction]:
    """Compute quote actions for all strikes in an event.

    Parameters
    ----------
    rnd_prices : BucketPrices
        From the RND pipeline. survival[i] = P(S > K_i) = Yes-price for
        the half-line market at strike K_i.
    event_book : EventBook
        Current orderbook state for each strike.
    inventory : dict[str, int]
        Mapping of market_ticker -> signed_qty (from PositionStore).
        Positive = long yes, negative = short yes.
    risk_ok : bool
        False if risk gates are breached (cancel everything).
    gate_size_mult : float
        Size multiplier from settlement gate. 1.0 = normal, 0.5 = half, 0.0 = pull all.
    gate_spread_mult : float
        Spread multiplier from settlement gate. 1.0 = normal, 2.0 = doubled.
    imbalance_withdraw_side : str | None
        "bid" or "ask" if taker-imbalance detector signals withdrawal,
        None if normal.
    config : QuoterConfig
        Tuning parameters.

    Returns
    -------
    list[QuoteAction]
        One or more actions per strike.
    """
    actions: list[QuoteAction] = []

    if not risk_ok:
        for sb in event_book.strike_books:
            actions.append(QuoteAction(
                action_type=QuoteActionType.CANCEL,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="risk_gate_breach",
            ))
        return actions

    if gate_size_mult <= 0.0:
        for sb in event_book.strike_books:
            actions.append(QuoteAction(
                action_type=QuoteActionType.CANCEL,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="settlement_gate_pull_all",
            ))
        return actions

    # Build a list of (strike_index, strike_book) aligned with RND survival
    # rnd_prices.kalshi_strikes[i] corresponds to survival[i]
    strike_to_survival: dict[float, float] = {}
    for i, k in enumerate(rnd_prices.kalshi_strikes):
        strike_to_survival[float(k)] = float(rnd_prices.survival[i])

    # Track bids placed this cycle for anti-arb check
    # For half-line markets: if we bid Yes at K_i (price p_i) and
    # bid Yes at K_j where K_j > K_i (price p_j), we need p_i >= p_j
    # (monotonicity). Also: no sum > 100c across complementary legs.
    placed_bids: list[tuple[float, int]] = []  # (strike, bid_cents)
    placed_asks: list[tuple[float, int]] = []  # (strike, ask_cents)

    for sb in event_book.strike_books:
        fair_cents = strike_to_survival.get(sb.strike)
        if fair_cents is None:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="strike_not_in_rnd",
            ))
            continue

        # Convert survival probability to cents
        fair_price_cents = int(round(fair_cents * 100.0))

        # Clamp fair to valid range
        if fair_price_cents < MIN_PRICE_CENTS or fair_price_cents > MAX_PRICE_CENTS:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason=f"fair_price_out_of_band_{fair_price_cents}",
            ))
            continue

        # Compute half-spread bounds
        min_hs = max(
            config.min_half_spread_cents,
            int(round(config.min_half_spread_cents * gate_spread_mult)),
        )
        max_hs = config.max_half_spread_cents

        # Inventory skew
        inv = inventory.get(sb.market_ticker, 0)
        skew_cents = int(round(config.inventory_skew_gamma * inv))

        # Adaptive spread: penny inside the current best, capped by max_half_spread.
        # If book is empty (bid=0, ask=100), fall back to min half-spread.
        if sb.best_bid_cents > 0 and sb.best_ask_cents < 100:
            # Real book exists — post 1c inside the current best
            adaptive_bid = sb.best_bid_cents + 1
            adaptive_ask = sb.best_ask_cents - 1
            # But don't go closer to fair than min_half_spread
            raw_bid = min(adaptive_bid, fair_price_cents - min_hs)
            raw_ask = max(adaptive_ask, fair_price_cents + min_hs)
            # And don't go further from fair than max_half_spread
            raw_bid = max(raw_bid, fair_price_cents - max_hs)
            raw_ask = min(raw_ask, fair_price_cents + max_hs)
        else:
            # Empty book — use minimum half-spread
            raw_bid = fair_price_cents - min_hs
            raw_ask = fair_price_cents + min_hs

        # Apply inventory skew
        raw_bid -= skew_cents
        raw_ask -= skew_cents

        # Clamp to quote band
        bid_cents = max(MIN_PRICE_CENTS, min(MAX_PRICE_CENTS, raw_bid))
        ask_cents = max(MIN_PRICE_CENTS, min(MAX_PRICE_CENTS, raw_ask))

        # Ensure positive spread
        if bid_cents >= ask_cents:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason=f"no_spread_after_skew_bid{bid_cents}_ask{ask_cents}",
            ))
            continue

        # Round to tick
        try:
            bid_cents = round_to_tick(bid_cents)
            ask_cents = round_to_tick(ask_cents)
        except ValueError:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="tick_rounding_out_of_band",
            ))
            continue

        if bid_cents >= ask_cents:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="no_spread_after_tick_round",
            ))
            continue

        # Never cross the book
        if sb.best_ask_cents > 0 and bid_cents >= sb.best_ask_cents:
            bid_cents = sb.best_ask_cents - 1
        if sb.best_bid_cents > 0 and ask_cents <= sb.best_bid_cents:
            ask_cents = sb.best_bid_cents + 1

        # Re-validate after cross check
        if bid_cents < MIN_PRICE_CENTS or ask_cents > MAX_PRICE_CENTS:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="out_of_band_after_cross_check",
            ))
            continue

        if bid_cents >= ask_cents:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="no_spread_after_cross_check",
            ))
            continue

        # Fee threshold check
        spread_cents = ask_cents - bid_cents
        rt_fee = _round_trip_maker_fee_cents(
            bid_cents, ask_cents,
            config.taker_rate, config.maker_fraction,
        )
        if spread_cents <= rt_fee + config.fee_threshold_cents:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason=f"spread_{spread_cents}c_below_fee_{rt_fee}c",
            ))
            continue

        # Anti-arb check (monotonicity for half-line survival quotes)
        # For YES half-line bids: bid at higher strike must be <= bid at lower strike
        arb_violation = False
        for prev_strike, prev_bid in placed_bids:
            if sb.strike > prev_strike and bid_cents > prev_bid:
                bid_cents = prev_bid
            elif sb.strike < prev_strike and bid_cents < prev_bid:
                # Don't adjust — the previous one was already placed
                pass
        for prev_strike, prev_ask in placed_asks:
            if sb.strike > prev_strike and ask_cents > prev_ask:
                ask_cents = prev_ask
            elif sb.strike < prev_strike and ask_cents < prev_ask:
                pass

        if bid_cents >= ask_cents or bid_cents < MIN_PRICE_CENTS or ask_cents > MAX_PRICE_CENTS:
            actions.append(QuoteAction(
                action_type=QuoteActionType.NO_ACTION,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="arb_adjustment_killed_spread",
            ))
            continue

        # Compute size
        base_size = config.max_contracts_per_strike
        size = max(1, int(round(base_size * gate_size_mult)))

        # Emit bid (unless taker-imbalance withdraws it)
        if imbalance_withdraw_side != "bid":
            actions.append(QuoteAction(
                action_type=QuoteActionType.PLACE_BID,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                price_cents=bid_cents,
                size=size,
                reason=f"fair={fair_price_cents}c spread={spread_cents}c inv={inv}",
            ))
        else:
            actions.append(QuoteAction(
                action_type=QuoteActionType.CANCEL,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="taker_imbalance_withdraw_bid",
            ))

        # Emit ask (unless taker-imbalance withdraws it)
        if imbalance_withdraw_side != "ask":
            actions.append(QuoteAction(
                action_type=QuoteActionType.PLACE_ASK,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                price_cents=ask_cents,
                size=size,
                reason=f"fair={fair_price_cents}c spread={spread_cents}c inv={inv}",
            ))
        else:
            actions.append(QuoteAction(
                action_type=QuoteActionType.CANCEL,
                market_ticker=sb.market_ticker,
                strike=sb.strike,
                reason="taker_imbalance_withdraw_ask",
            ))

        placed_bids.append((sb.strike, bid_cents))
        placed_asks.append((sb.strike, ask_cents))

    return actions
