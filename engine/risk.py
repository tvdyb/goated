"""Risk gates: aggregate book-delta cap, per-Event cap, max-loss cap.

Pre-trade gate blocks orders that would breach any configured limit.
Post-trade check verifies positions after fills and produces kill-switch
trigger results on breach.

Gaps closed: GAP-118 (aggregate net-delta cap), GAP-119 (per-Event
dollar-exposure tracker), GAP-120 (risk-gating stage J).

Non-negotiables enforced:
  - Fail-loud: RiskBreachError on pre-trade breach (raise, don't silently reject)
  - No pandas
  - Type hints on all public interfaces
  - Thread-safe (delegates to PositionStore's internal lock)

References:
  - Phase 09 section 8 (risk and ops)
  - Phase 07 section 5 (Rule 5.19 max-loss dollars)
  - config/commodities.yaml soy.position_cap.max_loss_dollars
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engine.kill import TriggerResult
from feeds.kalshi.ticker import parse_market_ticker
from state.positions import EventExposure, MarketPosition, PositionStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RiskBreachError(Exception):
    """Raised when a proposed trade would breach a risk cap.

    Attributes:
        cap_name: Which cap was breached (aggregate_delta, per_event_delta,
            max_loss).
        detail: Human-readable detail string.
    """

    def __init__(self, cap_name: str, detail: str) -> None:
        self.cap_name = cap_name
        self.detail = detail
        super().__init__(f"Risk breach [{cap_name}]: {detail}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default limits — conservative starting point.
# max_loss_dollars=25000 from config/commodities.yaml soy.position_cap
_DEFAULT_AGGREGATE_DELTA_CAP: int = 500  # contracts across all events
_DEFAULT_PER_EVENT_DELTA_CAP: int = 200  # contracts per single event
_DEFAULT_MAX_LOSS_DOLLARS: int = 25_000  # worst-case loss cap in dollars


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Immutable risk limit configuration.

    Attributes:
        aggregate_delta_cap: Maximum absolute aggregate signed exposure
            across all events (in contracts).
        per_event_delta_cap: Maximum absolute signed exposure for any
            single event (in contracts).
        max_loss_cents: Maximum total worst-case loss across all
            positions (in cents).
    """

    aggregate_delta_cap: int
    per_event_delta_cap: int
    max_loss_cents: int

    def __post_init__(self) -> None:
        if self.aggregate_delta_cap <= 0:
            raise ValueError(
                f"aggregate_delta_cap must be positive, got {self.aggregate_delta_cap}"
            )
        if self.per_event_delta_cap <= 0:
            raise ValueError(
                f"per_event_delta_cap must be positive, got {self.per_event_delta_cap}"
            )
        if self.max_loss_cents <= 0:
            raise ValueError(
                f"max_loss_cents must be positive, got {self.max_loss_cents}"
            )


def load_risk_limits(
    config: dict[str, Any] | None = None,
    *,
    aggregate_delta_cap: int | None = None,
    per_event_delta_cap: int | None = None,
    max_loss_dollars: int | None = None,
) -> RiskLimits:
    """Load risk limits from config dict and/or explicit overrides.

    Priority: explicit keyword arg > config dict > module default.

    The config dict is expected to have the shape of the ``soy`` section
    from ``config/commodities.yaml``, e.g.::

        {"position_cap": {"max_loss_dollars": 25000}}

    Args:
        config: Commodity config dict (optional).
        aggregate_delta_cap: Override for aggregate delta cap.
        per_event_delta_cap: Override for per-event delta cap.
        max_loss_dollars: Override for max-loss cap in dollars.

    Returns:
        RiskLimits instance.
    """
    # Extract from config if provided
    cfg_max_loss: int | None = None
    if config is not None:
        pos_cap = config.get("position_cap")
        if isinstance(pos_cap, dict):
            raw = pos_cap.get("max_loss_dollars")
            if raw is not None:
                cfg_max_loss = int(raw)

    # Resolve with priority: explicit > config > default
    resolved_agg = aggregate_delta_cap or _DEFAULT_AGGREGATE_DELTA_CAP
    resolved_per = per_event_delta_cap or _DEFAULT_PER_EVENT_DELTA_CAP
    resolved_ml_dollars = max_loss_dollars or cfg_max_loss or _DEFAULT_MAX_LOSS_DOLLARS

    return RiskLimits(
        aggregate_delta_cap=resolved_agg,
        per_event_delta_cap=resolved_per,
        max_loss_cents=resolved_ml_dollars * 100,
    )


# ---------------------------------------------------------------------------
# Proposed order description
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    """Description of a proposed order for pre-trade risk check.

    Attributes:
        market_ticker: Target market (e.g. KXSOYBEANW-26APR24-17).
        signed_delta_qty: Signed quantity change in Yes-equivalent
            contracts. Positive = buying yes / selling no.
            Negative = selling yes / buying no.
        cost_per_contract_cents: Cost per contract in cents (1-99).
    """

    market_ticker: str
    signed_delta_qty: int
    cost_per_contract_cents: int


# ---------------------------------------------------------------------------
# Risk gate
# ---------------------------------------------------------------------------


class RiskGate:
    """Pre-trade and post-trade risk gate.

    Checks three caps:
    1. Aggregate book-delta cap (total signed exposure across all events)
    2. Per-Event exposure cap (signed exposure for any single event)
    3. Max-loss cap (total worst-case loss across all positions)

    Usage::

        gate = RiskGate(position_store=store, limits=limits)

        # Pre-trade: raises RiskBreachError if blocked
        gate.check_pre_trade(proposed_order)

        # Post-trade: returns TriggerResult for kill-switch integration
        result = gate.check_post_trade()
        if result.fired:
            # trigger kill switch
            ...
    """

    def __init__(
        self,
        position_store: PositionStore,
        limits: RiskLimits,
    ) -> None:
        self._store = position_store
        self._limits = limits

    @property
    def limits(self) -> RiskLimits:
        """Return the current risk limits."""
        return self._limits

    # ── Pre-trade gate ─────────────────────────────────────────────

    def check_pre_trade(self, order: ProposedOrder) -> None:
        """Check whether a proposed order would breach any risk cap.

        Simulates the resulting position state and validates against
        all three caps. This is a synchronous, fail-loud gate.

        Args:
            order: The proposed order to check.

        Raises:
            RiskBreachError: If the order would breach any cap.
        """
        parsed = parse_market_ticker(order.market_ticker)
        event_ticker = parsed.event_ticker

        # --- 1. Aggregate delta cap ---
        # Current aggregate = sum of signed_qty across all positions
        all_exposures = self._store.get_all_event_exposures()
        current_agg = sum(e.signed_exposure for e in all_exposures.values())
        proposed_agg = current_agg + order.signed_delta_qty

        if abs(proposed_agg) > self._limits.aggregate_delta_cap:
            raise RiskBreachError(
                "aggregate_delta",
                f"Proposed aggregate delta {proposed_agg} would exceed cap "
                f"{self._limits.aggregate_delta_cap}. "
                f"Current={current_agg}, order_delta={order.signed_delta_qty}.",
            )

        # --- 2. Per-Event delta cap ---
        current_event = self._store.get_event_exposure(event_ticker)
        proposed_event_delta = current_event.signed_exposure + order.signed_delta_qty

        if abs(proposed_event_delta) > self._limits.per_event_delta_cap:
            raise RiskBreachError(
                "per_event_delta",
                f"Proposed event delta for {event_ticker} is "
                f"{proposed_event_delta}, exceeding cap "
                f"{self._limits.per_event_delta_cap}. "
                f"Current={current_event.signed_exposure}, "
                f"order_delta={order.signed_delta_qty}.",
            )

        # --- 3. Max-loss cap ---
        # Simulate the worst-case cost of the proposed order
        current_total_loss = self._store.total_max_loss_cents()
        proposed_additional_loss = _estimate_additional_max_loss(
            current_pos=self._store.get_position(order.market_ticker),
            signed_delta_qty=order.signed_delta_qty,
            cost_per_contract_cents=order.cost_per_contract_cents,
        )
        proposed_total_loss = current_total_loss + proposed_additional_loss

        if proposed_total_loss > self._limits.max_loss_cents:
            raise RiskBreachError(
                "max_loss",
                f"Proposed total max-loss {proposed_total_loss} cents "
                f"(${proposed_total_loss / 100:.2f}) would exceed cap "
                f"{self._limits.max_loss_cents} cents "
                f"(${self._limits.max_loss_cents / 100:.2f}). "
                f"Current={current_total_loss}, "
                f"additional={proposed_additional_loss}.",
            )

        logger.debug(
            "Risk pre-trade PASS: market=%s delta=%d agg=%d/%d event=%d/%d "
            "loss=%d/%d",
            order.market_ticker, order.signed_delta_qty,
            proposed_agg, self._limits.aggregate_delta_cap,
            proposed_event_delta, self._limits.per_event_delta_cap,
            proposed_total_loss, self._limits.max_loss_cents,
        )

    # ── Post-trade check ───────────────────────────────────────────

    def check_post_trade(self) -> TriggerResult:
        """Verify that all risk caps are respected after a fill.

        This does not raise; it returns a TriggerResult suitable for
        registration as a kill-switch trigger condition.

        Returns:
            TriggerResult with fired=True if any cap is breached.
        """
        # Aggregate delta
        all_exposures = self._store.get_all_event_exposures()
        current_agg = sum(e.signed_exposure for e in all_exposures.values())

        if abs(current_agg) > self._limits.aggregate_delta_cap:
            detail = (
                f"Aggregate delta {current_agg} exceeds cap "
                f"{self._limits.aggregate_delta_cap}"
            )
            logger.warning("RISK POST-TRADE BREACH: %s", detail)
            return TriggerResult(
                fired=True,
                name="risk_aggregate_delta_breach",
                detail=detail,
            )

        # Per-Event delta
        for et, exp in all_exposures.items():
            if abs(exp.signed_exposure) > self._limits.per_event_delta_cap:
                detail = (
                    f"Event {et} delta {exp.signed_exposure} exceeds cap "
                    f"{self._limits.per_event_delta_cap}"
                )
                logger.warning("RISK POST-TRADE BREACH: %s", detail)
                return TriggerResult(
                    fired=True,
                    name="risk_per_event_delta_breach",
                    detail=detail,
                )

        # Max-loss
        total_loss = self._store.total_max_loss_cents()
        if total_loss > self._limits.max_loss_cents:
            detail = (
                f"Total max-loss {total_loss} cents "
                f"(${total_loss / 100:.2f}) exceeds cap "
                f"{self._limits.max_loss_cents} cents "
                f"(${self._limits.max_loss_cents / 100:.2f})"
            )
            logger.warning("RISK POST-TRADE BREACH: %s", detail)
            return TriggerResult(
                fired=True,
                name="risk_max_loss_breach",
                detail=detail,
            )

        return TriggerResult(
            fired=False,
            name="risk_post_trade_ok",
        )

    def make_kill_trigger(self) -> "callable":
        """Return a zero-arg callable suitable as a KillSwitch trigger.

        Returns:
            A callable that returns TriggerResult from check_post_trade().
        """
        return self.check_post_trade


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_additional_max_loss(
    current_pos: MarketPosition,
    signed_delta_qty: int,
    cost_per_contract_cents: int,
) -> int:
    """Estimate the change in max-loss from a proposed order.

    This is a conservative estimate: it computes the max-loss of the
    resulting position minus the max-loss of the current position.

    For increasing positions, the additional max-loss is the cost of
    the new contracts (long) or (100 - cost) per contract (short).

    For reducing positions, the additional max-loss is negative (risk
    decreases), so we return 0 as a floor -- we never *increase* the
    budget by trading.

    Args:
        current_pos: Current position in this market.
        signed_delta_qty: Proposed signed delta.
        cost_per_contract_cents: Cost per contract in cents.

    Returns:
        Estimated additional max-loss in cents (non-negative).
    """
    old_qty = current_pos.signed_qty
    new_qty = old_qty + signed_delta_qty

    # Compute new position's max-loss
    old_cost = current_pos.total_cost_cents
    abs_delta = abs(signed_delta_qty)

    if old_qty == 0:
        # Opening fresh
        if new_qty > 0:
            new_max_loss = abs_delta * cost_per_contract_cents
        elif new_qty < 0:
            new_max_loss = abs_delta * (100 - cost_per_contract_cents)
        else:
            new_max_loss = 0
        return max(0, new_max_loss - current_pos.max_loss_cents)

    # Same direction: increasing position
    if (old_qty > 0 and signed_delta_qty > 0):
        additional_cost = abs_delta * cost_per_contract_cents
        new_max_loss = old_cost + additional_cost
        return max(0, new_max_loss - current_pos.max_loss_cents)

    if (old_qty < 0 and signed_delta_qty < 0):
        additional_cost = abs_delta * (100 - cost_per_contract_cents)
        new_total_cost = old_cost + additional_cost
        new_max_loss = abs(new_qty) * 100 - new_total_cost
        return max(0, new_max_loss - current_pos.max_loss_cents)

    # Opposite direction: reducing or flipping
    # Reduction always decreases risk; floor at 0
    return 0
