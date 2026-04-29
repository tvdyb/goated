"""Position store with per-Event signed exposure and max-loss accounting.

Tracks per-market signed positions, aggregates exposure per Event, and
computes worst-case loss under Kalshi binary payoff rules.

Thread-safe: all reads and writes acquire a per-instance lock.

Fail-loud: reconciliation mismatches raise PositionReconciliationError.
Invalid fills raise ValueError.

No pandas. No silent failures.

References:
  - Phase 09 section 8 (position and loss limits)
  - Phase 07 section 5 (Rule 5.19 max-loss dollars)
  - GAP-083, GAP-116, GAP-117, GAP-119, GAP-125, GAP-130
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from feeds.kalshi.ticker import parse_market_ticker


# ── Errors ────────────────────────────────────────────────────────────


class PositionReconciliationError(RuntimeError):
    """Raised when local positions diverge from the exchange."""

    def __init__(self, discrepancies: list[str]) -> None:
        self.discrepancies = discrepancies
        super().__init__(
            f"Position reconciliation failed with {len(discrepancies)} "
            f"discrepancy(ies):\n" + "\n".join(discrepancies)
        )


# ── Data types ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Fill:
    """A single fill event from the exchange or WebSocket.

    Attributes:
        market_ticker: Market ticker (e.g. KXSOYBEANW-26APR24-17).
        side: ``"yes"`` or ``"no"``.
        action: ``"buy"`` or ``"sell"``.
        count: Number of contracts filled (must be > 0).
        price_cents: Fill price in cents (1..99 for binary contracts).
        fill_id: Unique fill identifier for dedup.
    """

    market_ticker: str
    side: str
    action: str
    count: int
    price_cents: int
    fill_id: str

    def __post_init__(self) -> None:
        if self.side not in ("yes", "no"):
            raise ValueError(
                f"Fill side must be 'yes' or 'no', got {self.side!r}."
            )
        if self.action not in ("buy", "sell"):
            raise ValueError(
                f"Fill action must be 'buy' or 'sell', got {self.action!r}."
            )
        if self.count <= 0:
            raise ValueError(
                f"Fill count must be positive, got {self.count}."
            )
        if not (1 <= self.price_cents <= 99):
            raise ValueError(
                f"Fill price_cents must be in [1, 99], got {self.price_cents}."
            )
        if not self.fill_id:
            raise ValueError("Fill fill_id must be non-empty.")
        if not self.market_ticker:
            raise ValueError("Fill market_ticker must be non-empty.")


@dataclass(slots=True)
class MarketPosition:
    """Mutable position state for a single Kalshi market.

    Attributes:
        market_ticker: Market ticker string.
        event_ticker: Parent event ticker (derived from market ticker).
        signed_qty: Signed quantity in Yes contracts. +long, -short.
        total_cost_cents: Total cents paid to acquire the current position
            (used for max-loss on long side).
        realized_pnl_cents: Accumulated realized PnL in cents from
            position reductions.
    """

    market_ticker: str
    event_ticker: str
    signed_qty: int = 0
    total_cost_cents: int = 0
    realized_pnl_cents: int = 0

    @property
    def max_loss_cents(self) -> int:
        """Worst-case loss in cents for this position.

        Kalshi binary payoff:
        - Long (signed_qty > 0): max loss = total_cost_cents
          (contracts become worthless).
        - Short (signed_qty < 0): max loss = |signed_qty| * 100 - |total_cost_cents|
          (contracts settle at $1.00; we received total_cost_cents when selling).
        - Flat: 0.
        """
        if self.signed_qty > 0:
            return self.total_cost_cents
        elif self.signed_qty < 0:
            return abs(self.signed_qty) * 100 - abs(self.total_cost_cents)
        return 0


@dataclass(frozen=True, slots=True)
class EventExposure:
    """Aggregated exposure for a single Kalshi Event.

    Attributes:
        event_ticker: Event ticker (e.g. KXSOYBEANW-26APR24).
        signed_exposure: Sum of signed_qty across all markets in the event.
        max_loss_cents: Sum of per-market max-loss across the event.
        n_markets: Number of markets with non-zero positions.
    """

    event_ticker: str
    signed_exposure: int
    max_loss_cents: int
    n_markets: int


# ── Position store ────────────────────────────────────────────────────


class PositionStore:
    """Thread-safe in-process position store for Kalshi markets.

    Tracks per-market positions, computes per-Event exposure, and
    enforces max-loss accounting under Kalshi binary payoff rules.

    Usage::

        store = PositionStore()
        store.apply_fill(Fill(
            market_ticker="KXSOYBEANW-26APR24-17",
            side="yes", action="buy", count=10,
            price_cents=30, fill_id="f1",
        ))
        pos = store.get_position("KXSOYBEANW-26APR24-17")
        exp = store.get_event_exposure("KXSOYBEANW-26APR24")
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._positions: dict[str, MarketPosition] = {}
        self._seen_fill_ids: set[str] = set()

    # ── Fill application ──────────────────────────────────────────

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill to update the position for the given market.

        Converts all fills into a Yes-contract-equivalent signed quantity
        change:
        - buy yes  -> +count at price_cents cost per contract
        - sell yes -> -count, receiving price_cents per contract
        - buy no   -> -count (equivalent to selling yes), cost = (100 - price_cents) per contract
        - sell no  -> +count (equivalent to buying yes), receiving (100 - price_cents) per contract

        Deduplicates by fill_id. Duplicate fills are silently ignored
        (idempotent).

        Args:
            fill: The fill to apply.

        Raises:
            ValueError: If fill data is invalid (enforced by Fill.__post_init__).
        """
        # Convert to Yes-equivalent delta and cost
        if fill.side == "yes" and fill.action == "buy":
            delta_qty = fill.count
            cost_per_contract = fill.price_cents
        elif fill.side == "yes" and fill.action == "sell":
            delta_qty = -fill.count
            cost_per_contract = fill.price_cents
        elif fill.side == "no" and fill.action == "buy":
            # Buying No = selling Yes equivalent
            delta_qty = -fill.count
            cost_per_contract = 100 - fill.price_cents
        else:
            # sell no = buying Yes equivalent
            delta_qty = fill.count
            cost_per_contract = 100 - fill.price_cents

        with self._lock:
            # Dedup
            if fill.fill_id in self._seen_fill_ids:
                return
            self._seen_fill_ids.add(fill.fill_id)

            pos = self._positions.get(fill.market_ticker)
            if pos is None:
                parsed = parse_market_ticker(fill.market_ticker)
                pos = MarketPosition(
                    market_ticker=fill.market_ticker,
                    event_ticker=parsed.event_ticker,
                )
                self._positions[fill.market_ticker] = pos

            _apply_delta(pos, delta_qty, cost_per_contract)

    # ── Queries ───────────────────────────────────────────────────

    def get_position(self, market_ticker: str) -> MarketPosition:
        """Return the position for a specific market.

        Returns a zero-position MarketPosition if no fills have been
        recorded for this market.
        """
        with self._lock:
            pos = self._positions.get(market_ticker)
            if pos is None:
                parsed = parse_market_ticker(market_ticker)
                return MarketPosition(
                    market_ticker=market_ticker,
                    event_ticker=parsed.event_ticker,
                )
            # Return a copy to avoid mutation outside the lock
            return MarketPosition(
                market_ticker=pos.market_ticker,
                event_ticker=pos.event_ticker,
                signed_qty=pos.signed_qty,
                total_cost_cents=pos.total_cost_cents,
                realized_pnl_cents=pos.realized_pnl_cents,
            )

    def get_event_exposure(self, event_ticker: str) -> EventExposure:
        """Compute aggregated exposure for a single Event.

        Sums signed_qty and max_loss_cents across all markets whose
        event_ticker matches.

        Returns an EventExposure with zeros if no positions exist for
        this event.
        """
        with self._lock:
            return self._compute_event_exposure(event_ticker)

    def get_all_event_exposures(self) -> dict[str, EventExposure]:
        """Return exposure for every Event that has at least one position."""
        with self._lock:
            events: dict[str, list[MarketPosition]] = defaultdict(list)
            for pos in self._positions.values():
                if pos.signed_qty != 0:
                    events[pos.event_ticker].append(pos)

            result: dict[str, EventExposure] = {}
            for et in events:
                result[et] = self._compute_event_exposure(et)
            return result

    def max_loss_cents(self, market_ticker: str) -> int:
        """Return worst-case loss in cents for a single market."""
        with self._lock:
            pos = self._positions.get(market_ticker)
            if pos is None:
                return 0
            return pos.max_loss_cents

    def event_max_loss_cents(self, event_ticker: str) -> int:
        """Return worst-case loss in cents for an entire Event."""
        with self._lock:
            return self._compute_event_exposure(event_ticker).max_loss_cents

    def total_max_loss_cents(self) -> int:
        """Return total worst-case loss in cents across all positions."""
        with self._lock:
            total = 0
            for pos in self._positions.values():
                total += pos.max_loss_cents
            return total

    def snapshot(self) -> dict[str, MarketPosition]:
        """Return a dict of all non-zero positions (copies)."""
        with self._lock:
            result: dict[str, MarketPosition] = {}
            for ticker, pos in self._positions.items():
                if pos.signed_qty != 0:
                    result[ticker] = MarketPosition(
                        market_ticker=pos.market_ticker,
                        event_ticker=pos.event_ticker,
                        signed_qty=pos.signed_qty,
                        total_cost_cents=pos.total_cost_cents,
                        realized_pnl_cents=pos.realized_pnl_cents,
                    )
            return result

    def clear(self) -> None:
        """Reset all positions and fill dedup state.

        Intended for testing or full reconciliation resets.
        """
        with self._lock:
            self._positions.clear()
            self._seen_fill_ids.clear()

    # ── Reconciliation ────────────────────────────────────────────

    def reconcile(self, api_positions: list[dict[str, Any]]) -> list[str]:
        """Reconcile local positions against Kalshi REST API response.

        Compares each position from ``GET /portfolio/positions`` against
        the local store. Reports discrepancies and raises
        ``PositionReconciliationError`` if any are found.

        The API response positions are expected to have at minimum:
        - ``ticker`` (str): market ticker
        - ``market_exposure`` (int): signed quantity (positive=long yes)

        Some API responses may also provide ``total_traded``, ``resting_orders_count``,
        etc. -- these are ignored for position reconciliation.

        Args:
            api_positions: List of position dicts from the API.

        Returns:
            Empty list if all positions match.

        Raises:
            PositionReconciliationError: If any discrepancy is found.
            ValueError: If api_positions contain malformed entries.
        """
        discrepancies: list[str] = []

        with self._lock:
            api_tickers: set[str] = set()

            for api_pos in api_positions:
                ticker = api_pos.get("ticker")
                if not isinstance(ticker, str) or not ticker:
                    raise ValueError(
                        f"API position missing 'ticker': {api_pos!r}"
                    )
                api_tickers.add(ticker)

                api_qty = api_pos.get("market_exposure")
                if api_qty is None:
                    raise ValueError(
                        f"API position for {ticker} missing 'market_exposure': "
                        f"{api_pos!r}"
                    )
                api_qty = int(api_qty)

                local_pos = self._positions.get(ticker)
                local_qty = local_pos.signed_qty if local_pos else 0

                if local_qty != api_qty:
                    discrepancies.append(
                        f"{ticker}: local={local_qty}, api={api_qty}"
                    )

            # Check for local positions not in API (possible if API
            # doesn't return zero-qty markets)
            for ticker, pos in self._positions.items():
                if pos.signed_qty != 0 and ticker not in api_tickers:
                    discrepancies.append(
                        f"{ticker}: local={pos.signed_qty}, api=0 (not in API response)"
                    )

        if discrepancies:
            raise PositionReconciliationError(discrepancies)

        return discrepancies

    # ── Internal helpers ──────────────────────────────────────────

    def _compute_event_exposure(self, event_ticker: str) -> EventExposure:
        """Compute exposure for an event. Must be called under lock."""
        signed_exposure = 0
        max_loss = 0
        n_markets = 0

        for pos in self._positions.values():
            if pos.event_ticker == event_ticker and pos.signed_qty != 0:
                signed_exposure += pos.signed_qty
                max_loss += pos.max_loss_cents
                n_markets += 1

        return EventExposure(
            event_ticker=event_ticker,
            signed_exposure=signed_exposure,
            max_loss_cents=max_loss,
            n_markets=n_markets,
        )


# ── Position delta application ────────────────────────────────────────


def _apply_delta(
    pos: MarketPosition,
    delta_qty: int,
    cost_per_contract: int,
) -> None:
    """Apply a signed quantity delta to a MarketPosition.

    Handles position increases, decreases, and flips with proper
    cost-basis and realized PnL accounting.

    Args:
        pos: The position to mutate (must be called under lock).
        delta_qty: Signed quantity change (+long, -short).
        cost_per_contract: Cost per contract in cents for the fill.
    """
    if delta_qty == 0:
        return

    old_qty = pos.signed_qty
    new_qty = old_qty + delta_qty

    if old_qty == 0:
        # Opening a new position
        pos.signed_qty = new_qty
        pos.total_cost_cents = abs(delta_qty) * cost_per_contract
        return

    # Same direction: position increase
    if (old_qty > 0 and delta_qty > 0) or (old_qty < 0 and delta_qty < 0):
        pos.signed_qty = new_qty
        pos.total_cost_cents += abs(delta_qty) * cost_per_contract
        return

    # Opposite direction: position reduction or flip
    abs_old = abs(old_qty)
    abs_delta = abs(delta_qty)

    if abs_delta <= abs_old:
        # Partial or full close
        # Realize PnL on the closed portion
        avg_cost = pos.total_cost_cents / abs_old if abs_old > 0 else 0
        closed_cost = int(round(avg_cost * abs_delta))

        if old_qty > 0:
            # Was long, selling: receive cost_per_contract per contract
            realized = abs_delta * cost_per_contract - closed_cost
        else:
            # Was short, buying: pay cost_per_contract per contract
            realized = closed_cost - abs_delta * cost_per_contract

        pos.realized_pnl_cents += realized
        pos.total_cost_cents -= closed_cost
        pos.signed_qty = new_qty

        # Clean up rounding on full close
        if new_qty == 0:
            pos.total_cost_cents = 0
    else:
        # Flip through zero: close old position fully, then open new
        # First close the old position
        if old_qty > 0:
            realized = abs_old * cost_per_contract - pos.total_cost_cents
        else:
            realized = pos.total_cost_cents - abs_old * cost_per_contract

        pos.realized_pnl_cents += realized

        # Then open the remainder on the other side
        remainder = abs_delta - abs_old
        pos.signed_qty = new_qty
        pos.total_cost_cents = remainder * cost_per_contract
