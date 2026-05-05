"""RiskGate protocol + RiskContext + RiskVerdict + RiskRegistry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lipmm.quoting.base import OurState, QuotingDecision, SideDecision
from lipmm.theo.base import TheoResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskContext:
    """Inputs every risk gate sees on each evaluate() call.

    Built by `LIPRunner` after strategy.quote() returns and before
    OrderManager.apply() runs.
    """
    ticker: str
    cycle_id: int                     # for per-cycle stateful gates
    decision: QuotingDecision         # what the strategy proposed
    theo: TheoResult
    our_state: OurState
    time_to_settle_s: float
    now_ts: float
    # Aggregate views from OrderManager.all_resting():
    all_resting_count: int            # total resting orders across all tickers
    all_resting_notional: float       # rough sum of price × size, in dollars
    # Knob overrides from ControlState (e.g. max_orders_per_cycle).
    # Optional; gates check for keys they care about and ignore others.
    control_overrides: dict | None = None


@dataclass(frozen=True)
class RiskVerdict:
    """A gate's verdict for one strike-side decision.

    bid_allow / ask_allow: True allows that side; False vetoes it.
    The corresponding reason is included in the audit trail so analysts
    can see WHY a side was vetoed when reading decision logs.
    """
    bid_allow: bool = True
    ask_allow: bool = True
    bid_reason: str = ""
    ask_reason: str = ""

    @property
    def vetoes_anything(self) -> bool:
        return not (self.bid_allow and self.ask_allow)


@runtime_checkable
class RiskGate(Protocol):
    """A composable risk constraint.

    Implementations must:
      - Set `name` (used in audit trail and logs)
      - Implement async `check(context) -> RiskVerdict`

    Async even when not strictly needed; keeps the protocol uniform with
    QuotingStrategy / TheoProvider and lets gates query external systems
    (account state poller, rate-limit tokens, etc.) in the future.

    Stateful gates (e.g. `MaxOrdersPerCycleGate`) hold instance state
    that survives across check() calls. State must be reset on
    cycle_id transitions if it's per-cycle.
    """

    name: str

    async def check(self, context: RiskContext) -> RiskVerdict:
        ...


class RiskRegistry:
    """Composes a list of `RiskGate` instances into a single evaluation.

    Verdict combination: any gate vetoing a side wins (additive vetoes).
    Audit trail collects every gate's verdict (allow or veto) so consumers
    see the full picture, not just the first veto.
    """

    def __init__(self, gates: list[RiskGate] | None = None) -> None:
        self._gates: list[RiskGate] = list(gates) if gates else []

    def register(self, gate: RiskGate) -> None:
        """Add a gate to the registry. Order matters only for audit-trail
        ordering; veto semantics are commutative."""
        self._gates.append(gate)

    @property
    def gates(self) -> list[RiskGate]:
        return list(self._gates)

    async def evaluate(
        self, context: RiskContext,
    ) -> tuple[QuotingDecision, list[dict[str, Any]]]:
        """Run all gates, combine verdicts, return modified decision + audit.

        Returns:
            (modified_decision, audit_trail) where:
              - modified_decision has skip=True applied to vetoed sides
              - audit_trail is a list of dicts, one per gate, with shape:
                {gate, bid: "allow"|"veto", ask: "allow"|"veto",
                 bid_reason, ask_reason}
        """
        decision = context.decision
        if not self._gates:
            return decision, []

        # Track combined veto state across gates
        bid_vetoed = False
        ask_vetoed = False
        bid_reasons: list[str] = []
        ask_reasons: list[str] = []
        audit: list[dict[str, Any]] = []

        for gate in self._gates:
            try:
                verdict = await gate.check(context)
            except Exception as exc:
                logger.warning("RiskGate %s.check raised: %s", gate.name, exc)
                # Fail open — a gate exception shouldn't pause trading.
                # Operators see the warning in logs and can decide whether
                # to swap to a safer config.
                audit.append({
                    "gate": gate.name,
                    "bid": "allow", "ask": "allow",
                    "bid_reason": "", "ask_reason": "",
                    "error": repr(exc),
                })
                continue

            audit.append({
                "gate": gate.name,
                "bid": "allow" if verdict.bid_allow else "veto",
                "ask": "allow" if verdict.ask_allow else "veto",
                "bid_reason": verdict.bid_reason,
                "ask_reason": verdict.ask_reason,
            })

            if not verdict.bid_allow:
                bid_vetoed = True
                if verdict.bid_reason:
                    bid_reasons.append(f"{gate.name}: {verdict.bid_reason}")
            if not verdict.ask_allow:
                ask_vetoed = True
                if verdict.ask_reason:
                    ask_reasons.append(f"{gate.name}: {verdict.ask_reason}")

        # Apply combined vetoes to the decision
        new_bid = decision.bid
        new_ask = decision.ask
        if bid_vetoed and not decision.bid.skip:
            new_bid = SideDecision(
                price=0, size=0, skip=True,
                reason="risk vetoed: " + "; ".join(bid_reasons) if bid_reasons else "risk vetoed",
                extras=decision.bid.extras,
            )
        if ask_vetoed and not decision.ask.skip:
            new_ask = SideDecision(
                price=0, size=0, skip=True,
                reason="risk vetoed: " + "; ".join(ask_reasons) if ask_reasons else "risk vetoed",
                extras=decision.ask.extras,
            )

        if new_bid is decision.bid and new_ask is decision.ask:
            return decision, audit

        return QuotingDecision(
            bid=new_bid, ask=new_ask,
            transitions=list(decision.transitions),
        ), audit
