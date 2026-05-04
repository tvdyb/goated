"""Manual order submission — synthesize → risk-check → execute.

Operator clicks "buy 10 Yes at 45c on T1186.99" in the dashboard. The
endpoint calls `submit_manual_order(...)` which:

  1. Synthesizes a SideDecision matching the operator's request.
  2. Wraps it in a QuotingDecision (so the risk-gate path is identical
     to a strategy-issued decision).
  3. If a RiskRegistry is wired, runs `evaluate()` — the operator's
     configured `MaxNotionalPerSideGate` etc. veto manual orders the
     same way they'd veto strategy orders. Misclick from the phone gets
     stopped before it hits the exchange.
  4. If risk-OK, calls `OrderManager.apply()` directly. The OM's
     per-(ticker, side) async lock serializes against any concurrent
     runner-cycle apply on the same key — no torn state.
  5. Optionally locks the side after success (the user-requested
     "freeze direction after click-trade" semantics).

Returns a ManualOrderOutcome that the endpoint translates into the HTTP
response. Outcome.succeeded distinguishes "exchange placed it" from
"risk-vetoed" from "exchange rejected" — operator sees specifically why.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from lipmm.control.state import ControlState, SideName
from lipmm.execution import ExchangeClient, OrderManager
from lipmm.execution.order_manager import SideExecution
from lipmm.quoting.base import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    SideDecision,
)
from lipmm.risk import RiskContext, RiskRegistry
from lipmm.theo import TheoResult

logger = logging.getLogger(__name__)


@dataclass
class ManualOrderOutcome:
    """Structured result from a manual order attempt.

    Three terminal states:
      - succeeded=True, execution.action ∈ {place_new, amend}
        → exchange accepted, order is resting
      - succeeded=False, risk_vetoed=True
        → a RiskGate vetoed the order; never hit the exchange
      - succeeded=False, risk_vetoed=False
        → exchange rejected (post-only cross, insufficient funds, 4xx)
        → execution.action == "place_failed"
    """
    succeeded: bool
    risk_vetoed: bool
    execution: SideExecution
    risk_audit: list[dict[str, Any]] = field(default_factory=list)
    lock_applied: bool = False
    lock_auto_unlock_at: float | None = None


async def submit_manual_order(
    *,
    state: ControlState,
    order_manager: OrderManager,
    exchange: ExchangeClient,
    risk_registry: RiskRegistry | None,
    ticker: str,
    side: SideName,                       # "bid" or "ask"
    count: int,
    limit_price_cents: int,
    cycle_id_hint: int = 0,
    lock_after: bool = False,
    lock_auto_unlock_seconds: float | None = None,
    reason: str = "manual order",
) -> ManualOrderOutcome:
    """Submit a manual order. Synthesizes, risk-checks, executes, optionally locks.

    Caller (the FastAPI endpoint) is responsible for auth + audit emission.
    This function focuses on the bot-side mechanics and returns a structured
    outcome the endpoint translates to HTTP response shape.
    """
    if side not in ("bid", "ask"):
        raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
    if count <= 0:
        raise ValueError(f"count must be > 0, got {count}")
    if not (1 <= limit_price_cents <= 99):
        raise ValueError(
            f"limit_price_cents must be in [1, 99], got {limit_price_cents}"
        )

    # 1. Synthesize the SideDecision representing the operator's intent.
    side_decision = SideDecision(
        price=limit_price_cents,
        size=count,
        skip=False,
        reason=f"manual: {reason}",
        extras={"origin": "manual"},
    )

    # The opposing side defaults to skip — manual orders are per-side.
    opp_side: SideName = "ask" if side == "bid" else "bid"
    opp_decision = SideDecision(
        price=0, size=0, skip=True,
        reason="manual order targets only the opposite side; this side untouched",
        extras={"origin": "manual_no_op"},
    )
    bid_decision = side_decision if side == "bid" else opp_decision
    ask_decision = side_decision if side == "ask" else opp_decision
    quoting_decision = QuotingDecision(bid=bid_decision, ask=ask_decision)

    # 2. Risk gates. Synthesize a RiskContext mirroring what the runner
    # would build. Theo unavailable here (no fresh quote), so use a
    # neutral sentinel that won't accidentally trigger theo-aware gates
    # like EndgameGuardrailGate. Operators using endgame-style protection
    # on manual orders should configure a separate gate.
    risk_audit: list[dict[str, Any]] = []
    if risk_registry is not None:
        cur_bid = order_manager.get_resting(ticker, "bid")
        cur_ask = order_manager.get_resting(ticker, "ask")
        our_state = OurState(
            cur_bid_px=cur_bid.price_cents if cur_bid else 0,
            cur_bid_size=cur_bid.size if cur_bid else 0,
            cur_bid_id=cur_bid.order_id if cur_bid else None,
            cur_ask_px=cur_ask.price_cents if cur_ask else 0,
            cur_ask_size=cur_ask.size if cur_ask else 0,
            cur_ask_id=cur_ask.order_id if cur_ask else None,
        )
        empty_book = OrderbookSnapshot(
            yes_depth=[], no_depth=[],
            best_bid=0, best_ask=100,
        )
        # Neutral theo: yes_prob=0.5, but confidence=0 so any
        # confidence-aware gate explicitly skips manual orders.
        # MaxNotionalPerSideGate (the most important) doesn't read theo.
        neutral_theo = TheoResult(
            yes_probability=0.5, confidence=0.0,
            computed_at=time.time(),
            source="manual-order:neutral",
            extras={"manual_order": True},
        )
        resting = order_manager.all_resting()
        agg_count = len(resting)
        agg_notional = sum(
            ro.price_cents * ro.size / 100.0 for ro in resting.values()
        )
        risk_ctx = RiskContext(
            ticker=ticker,
            cycle_id=cycle_id_hint,
            decision=quoting_decision,
            theo=neutral_theo,
            our_state=our_state,
            time_to_settle_s=0.0,
            now_ts=time.time(),
            all_resting_count=agg_count,
            all_resting_notional=agg_notional,
        )
        quoting_decision, risk_audit = await risk_registry.evaluate(risk_ctx)

        # If risk vetoed our side, we're done — return without touching exchange.
        target_after = (
            quoting_decision.bid if side == "bid" else quoting_decision.ask
        )
        if target_after.skip:
            veto_exec = SideExecution(
                action="skipped",
                reason=f"risk vetoed manual order: {target_after.reason}",
                latency_ms=0,
            )
            return ManualOrderOutcome(
                succeeded=False, risk_vetoed=True,
                execution=veto_exec, risk_audit=risk_audit,
            )

    # 3. Place via OrderManager. The per-key lock prevents race against
    # the runner cycle's concurrent apply().
    target = bid_decision if side == "bid" else ask_decision
    execution = await order_manager.apply(ticker, side, target, exchange)

    succeeded = execution.action in ("place_new", "amend", "cancel_and_replace")

    # 4. Optionally lock the side. Only on success — failed/rejected
    # orders don't justify a lock (operator may want to retry).
    lock_applied = False
    lock_auto_unlock_at: float | None = None
    if succeeded and lock_after:
        if lock_auto_unlock_seconds and lock_auto_unlock_seconds > 0:
            lock_auto_unlock_at = time.time() + lock_auto_unlock_seconds
        await state.lock_side(
            ticker, side,
            reason=f"auto-locked by manual order: {reason}",
            auto_unlock_at=lock_auto_unlock_at,
        )
        lock_applied = True

    return ManualOrderOutcome(
        succeeded=succeeded,
        risk_vetoed=False,
        execution=execution,
        risk_audit=risk_audit,
        lock_applied=lock_applied,
        lock_auto_unlock_at=lock_auto_unlock_at,
    )
