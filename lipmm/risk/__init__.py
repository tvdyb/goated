"""Composable risk gates that sit between strategy and execution.

The bot's main loop in `LIPRunner`:

    decision = await strategy.quote(...)
    decision, audit = await risk_registry.evaluate(context)  # NEW
    bid_outcome = await order_manager.apply(ticker, "bid", decision.bid, exchange)
    ask_outcome = await order_manager.apply(ticker, "ask", decision.ask, exchange)

A `RiskRegistry` wraps a list of `RiskGate` instances. Each gate can veto
the bid side, the ask side, both, or neither. Vetoed sides get
`SideDecision(skip=True, reason=<gate_reason>)`, which the OrderManager
already handles correctly (cancels existing order, places nothing).

Designed for safety-by-default:
  - Empty registry passes every decision through unchanged.
  - Vetoes are additive — any gate can veto a side, no gate can un-veto.
  - Audit trail captures which gates fired and why, for decision-log
    analysis after the fact.

Why this lives outside QuotingStrategy:
  - Strategies are about market opinions ("where to quote"). Risk gates are
    about operator-defined safety constraints ("never more than $N at risk
    per side"). Mixing them couples strategy authors to operator policy.
  - Operators want to swap strategies without rewriting risk policy, and
    swap risk policy without rewriting strategies. Composition wins.

Three default gates ship with the framework. Operators add custom gates
by subclassing `RiskGate` (just implement `name` + `check`).
"""

from lipmm.risk.base import (
    RiskContext,
    RiskGate,
    RiskRegistry,
    RiskVerdict,
)
from lipmm.risk.gates.cycle_throttle import MaxOrdersPerCycleGate
from lipmm.risk.gates.endgame import EndgameGuardrailGate
from lipmm.risk.gates.mid_delta import MidDeltaGate
from lipmm.risk.gates.notional import MaxNotionalPerSideGate
from lipmm.risk.gates.position import MaxPositionPerSideGate

__all__ = [
    # protocol + dataclasses
    "RiskContext",
    "RiskGate",
    "RiskRegistry",
    "RiskVerdict",
    # default gates
    "EndgameGuardrailGate",
    "MaxNotionalPerSideGate",
    "MaxOrdersPerCycleGate",
    "MaxPositionPerSideGate",
    "MidDeltaGate",
]
