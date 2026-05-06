"""OrderManager — applies a SideDecision to one strike-side via the exchange.

This is the layer that knows about resting state, amend-vs-cancel-vs-place
decisions, and idempotent-on-error behavior. The bot's main loop:

    decision = await strategy.quote(...)
    bid_outcome = await order_manager.apply(
        ticker, "bid", decision.bid, exchange,
    )
    ask_outcome = await order_manager.apply(
        ticker, "ask", decision.ask, exchange,
    )

The OrderManager:
  - Tracks currently-resting orders per (ticker, side) in memory.
  - Decides whether to `place / amend / cancel-and-replace / cancel / no-op`.
  - Falls back gracefully when amend isn't supported (returns None).
  - Records latency for observability.
  - Idempotent against transient errors: if an exception is raised mid-flow,
    next cycle's call recovers the resting state from `exchange.list_resting_orders`.

What the OrderManager DOES NOT do:
  - Decide what to quote (that's QuotingStrategy)
  - Compute size (that's strategy + sizing layer)
  - Track fills, P&L, markout (separate observability layer)
  - Apply risk gates (separate RiskGate layer wraps OrderManager calls)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

from lipmm.execution.base import ExchangeClient, PlaceOrderRequest
from lipmm.quoting.base import SideDecision

logger = logging.getLogger(__name__)


SideName = Literal["bid", "ask"]


@dataclass
class RestingOrder:
    """OrderManager's view of an order it has placed."""
    order_id: str
    price_cents: int
    size: int


@dataclass
class SideExecution:
    """Result of applying one SideDecision. Surfaced to decision-log layer."""
    action: Literal[
        "no_change", "place_new", "amend", "cancel_and_replace",
        "cancel", "skipped", "place_failed",
    ]
    reason: str
    order_id: str | None = None
    price_cents: int | None = None
    size: int | None = None
    latency_ms: int = 0


class OrderManager:
    """Per-strike-side order state machine driven by SideDecisions.

    Internal state is `dict[(ticker, side), RestingOrder | None]`. On bot
    startup the bot should call `reconcile(exchange)` once to populate
    state from the exchange's view of resting orders. After that, every
    `apply()` call updates state in-step with the exchange.
    """

    def __init__(self) -> None:
        self._resting: dict[tuple[str, SideName], RestingOrder | None] = {}
        # Per-(ticker, side) lock guards apply() against concurrent calls
        # from different tasks (e.g. runner cycle vs manual-order endpoint
        # both touching the same key in flight). Lazy-allocated.
        self._locks: dict[tuple[str, SideName], asyncio.Lock] = {}
        # Cached available cash for balance-aware sizing. Pushed in by the
        # runner once per cycle from exchange.get_balance(). When None,
        # the collateral check is disabled (legacy behavior).
        self._available_cash_cents: float | None = None
        # Safety factor against the cached balance — Kalshi's collateral
        # accounting can lag our local view, so we hold back 10%.
        self._collateral_safety_factor: float = 0.9

    def _lock_for(self, key: tuple[str, SideName]) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    # ── public API ───────────────────────────────────────────────────

    def get_resting(self, ticker: str, side: SideName) -> RestingOrder | None:
        return self._resting.get((ticker, side))

    def all_resting(self) -> dict[tuple[str, SideName], RestingOrder]:
        return {
            k: v for k, v in self._resting.items() if v is not None
        }

    def find_by_order_id(
        self, order_id: str,
    ) -> tuple[str, SideName, RestingOrder] | None:
        """Locate a resting order by its exchange-side `order_id`. Used by
        the surgical cancel endpoint so the operator can target a single
        order without supplying (ticker, side) explicitly."""
        for (ticker, side), ro in self._resting.items():
            if ro is not None and ro.order_id == order_id:
                return (ticker, side, ro)
        return None

    def set_available_cash_cents(self, cents: float | None) -> None:
        """Cache available cash from exchange.get_balance() for the
        collateral-aware skip in _place_new. Pass None to disable the
        check (back-compat for tests / callers that don't poll balance).
        """
        self._available_cash_cents = cents

    def _committed_cents(self) -> float:
        """Sum of cents committed to existing resting orders. For each
        bid: price × size. For each ask: (100 - price) × size (since a
        Yes ask at P translates to a No bid at 100−P on Kalshi)."""
        total = 0.0
        for (_, side), ro in self._resting.items():
            if ro is None:
                continue
            cost_per = ro.price_cents if side == "bid" else max(0, 100 - ro.price_cents)
            total += cost_per * ro.size
        return total

    def forget(self, ticker: str, side: SideName) -> RestingOrder | None:
        """Drop the (ticker, side) entry from internal state without
        touching the exchange. Used after a successful out-of-band cancel
        (e.g., the dashboard's surgical cancel-by-order-id path) so the
        next `apply()` cycle doesn't think the order is still resting."""
        return self._resting.pop((ticker, side), None)

    async def reconcile(self, exchange: ExchangeClient) -> None:
        """Populate internal state from the exchange's truth.

        Call once at bot startup, and optionally after maintenance windows
        or on suspected state drift. Wipes prior in-memory state.
        """
        try:
            orders = await exchange.list_resting_orders()
        except Exception as exc:
            logger.warning("OrderManager.reconcile failed: %s", exc)
            return

        self._resting.clear()
        for o in orders:
            # action="buy" + side="yes" = bid; action="sell" + side="yes" = ask
            if o.action == "buy" and o.side == "yes":
                key: tuple[str, SideName] = (o.ticker, "bid")
            elif o.action == "sell" and o.side == "yes":
                key = (o.ticker, "ask")
            else:
                # No-side trades; treat by inversion. Adapter convention:
                # we only quote Yes-side, so this branch is rarely hit.
                continue
            # If multiple orders exist for the same key (shouldn't normally
            # happen but defensively handle), keep the most recent.
            self._resting[key] = RestingOrder(
                order_id=o.order_id,
                price_cents=o.limit_price_cents,
                size=o.remaining_count,
            )
        logger.info("OrderManager: reconciled %d resting orders", len(self._resting))

    async def apply(
        self,
        ticker: str,
        side: SideName,
        decision: SideDecision,
        exchange: ExchangeClient,
    ) -> SideExecution:
        """Apply one strike-side decision. Returns a SideExecution summary
        suitable for decision-log records.

        Holds a per-(ticker, side) async lock so concurrent calls (e.g.
        runner cycle vs manual-order endpoint) on the same key serialize
        correctly. Calls on different keys remain parallel.
        """
        key = (ticker, side)
        async with self._lock_for(key):
            return await self._apply_locked(key, ticker, side, decision, exchange)

    async def _apply_locked(
        self,
        key: tuple[str, SideName],
        ticker: str,
        side: SideName,
        decision: SideDecision,
        exchange: ExchangeClient,
    ) -> SideExecution:
        cur = self._resting.get(key)

        # Skip path: cancel any resting order, place nothing.
        if decision.skip:
            if cur is None:
                return SideExecution(
                    action="skipped", reason=f"skip+no-resting: {decision.reason}",
                )
            t0 = time.time()
            try:
                ok = await exchange.cancel_order(cur.order_id)
            except Exception as exc:
                logger.warning(
                    "OrderManager %s %s: skip-cancel failed for %s: %s",
                    ticker, side, cur.order_id[:8], exc,
                )
                # Don't clear state — next reconcile will sort it out
                return SideExecution(
                    action="cancel", reason=f"skip+cancel-error: {exc}",
                    order_id=cur.order_id,
                    latency_ms=int((time.time() - t0) * 1000),
                )
            self._resting[key] = None
            return SideExecution(
                action="cancel",
                reason=f"skip+cancelled (exchange ack={ok}): {decision.reason}",
                order_id=cur.order_id,
                latency_ms=int((time.time() - t0) * 1000),
            )

        # No-change path: existing order matches the decision.
        if cur is not None and cur.price_cents == decision.price and cur.size == decision.size:
            return SideExecution(
                action="no_change",
                reason=f"current order matches target ({decision.price}c × {decision.size})",
                order_id=cur.order_id,
                price_cents=cur.price_cents,
                size=cur.size,
            )

        # Update path: existing order needs change → try amend, fall back.
        if cur is not None:
            t0 = time.time()
            try:
                result = await exchange.amend_order(
                    cur.order_id,
                    new_limit_price_cents=decision.price,
                    new_count=decision.size,
                )
            except Exception as exc:
                logger.warning(
                    "OrderManager %s %s: amend exception for %s: %s",
                    ticker, side, cur.order_id[:8], exc,
                )
                result = None
            latency_ms = int((time.time() - t0) * 1000)

            if result is not None:
                # Amend succeeded
                self._resting[key] = RestingOrder(
                    order_id=result.order_id,
                    price_cents=result.limit_price_cents,
                    size=result.remaining_count,
                )
                return SideExecution(
                    action="amend",
                    reason=f"amend {cur.price_cents}→{decision.price} × {decision.size}: {decision.reason}",
                    order_id=result.order_id,
                    price_cents=result.limit_price_cents,
                    size=result.remaining_count,
                    latency_ms=latency_ms,
                )

            # Amend failed → cancel + place
            try:
                await exchange.cancel_order(cur.order_id)
            except Exception:
                pass  # cancel may fail if order already gone; place anyway
            self._resting[key] = None
            placed = await self._place_new(ticker, side, decision, exchange)
            return SideExecution(
                action="cancel_and_replace",
                reason=f"amend rejected, cancel+place at {decision.price} × {decision.size}: {decision.reason}",
                order_id=placed.order_id if placed else None,
                price_cents=decision.price if placed else None,
                size=decision.size if placed else None,
                latency_ms=int((time.time() - t0) * 1000),
            )

        # Place-new path: no existing order.
        t0 = time.time()
        placed = await self._place_new(ticker, side, decision, exchange)
        latency_ms = int((time.time() - t0) * 1000)
        if placed is None:
            return SideExecution(
                action="place_failed",
                reason=f"place rejected at {decision.price} × {decision.size}: {decision.reason}",
                latency_ms=latency_ms,
            )
        return SideExecution(
            action="place_new",
            reason=f"new order at {decision.price}c × {decision.size}: {decision.reason}",
            order_id=placed.order_id,
            price_cents=decision.price,
            size=decision.size,
            latency_ms=latency_ms,
        )

    # ── helpers ──────────────────────────────────────────────────────

    async def _place_new(
        self,
        ticker: str,
        side: SideName,
        decision: SideDecision,
        exchange: ExchangeClient,
    ) -> RestingOrder | None:
        """Place a new order for one strike-side. Updates internal state on
        success. Returns the RestingOrder or None on rejection."""
        key = (ticker, side)
        action: Literal["buy", "sell"] = "buy" if side == "bid" else "sell"
        # Collateral-aware skip. If we know the cash balance, refuse to
        # fire a doomed placement that would push committed past the
        # safety threshold. Kalshi auto-cancels these and the operator
        # gets push-notification spam.
        if self._available_cash_cents is not None:
            cost_per = decision.price if side == "bid" else max(0, 100 - decision.price)
            new_cents = cost_per * decision.size
            committed = self._committed_cents()
            budget = self._available_cash_cents * self._collateral_safety_factor
            if committed + new_cents > budget:
                logger.info(
                    "OrderManager %s %s: skipping place at %dc × %d "
                    "— would commit ¢%.0f on top of ¢%.0f committed; "
                    "budget ¢%.0f (cash ¢%.0f × %.2f)",
                    ticker, side, decision.price, decision.size,
                    new_cents, committed, budget,
                    self._available_cash_cents,
                    self._collateral_safety_factor,
                )
                return None
        try:
            order = await exchange.place_order(PlaceOrderRequest(
                ticker=ticker,
                action=action,
                side="yes",
                count=decision.size,
                limit_price_cents=decision.price,
                post_only=True,
                # Pass through the strategy's precise t1c price so the
                # adapter can route through Kalshi's fractional path on
                # sub-cent markets. Defaults to None on legacy callers
                # (which means "derive from cents × 10").
                limit_price_t1c=decision.price_t1c,
            ))
        except Exception as exc:
            logger.warning(
                "OrderManager %s %s: place exception at %dc × %d: %s",
                ticker, side, decision.price, decision.size, exc,
            )
            return None

        if order is None:
            return None

        resting = RestingOrder(
            order_id=order.order_id,
            price_cents=order.limit_price_cents,
            size=order.remaining_count,
        )
        self._resting[key] = resting
        return resting
