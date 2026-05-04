"""LIP Market Maker — reusable framework for Kalshi liquidity-incentive trading.

This package contains the market-agnostic infrastructure: how to compute theo
(`lipmm.theo`), how to compute quotes given theo (`lipmm.quoting`), and the
glue that ties them together. Market-specific code (soy WASDE overlays,
Trading Economics scrapers, Kalshi auth, dashboard) lives outside this
package, in the surrounding repo.

The framework is plugin-driven:

  - `lipmm.theo.TheoProvider` — one implementation per market type.
    Soy/corn/cattle use Black-76 commodity GBM. Sports use sportsbook
    aggregators. Politics use poll aggregators with Bayesian decay.

  - `lipmm.quoting.QuotingStrategy` — one implementation per LIP-farming
    style. The default penny-inside-best with anti-spoofing; alternatives
    can use stickiness, robust-best filters, mid-locking, etc.

A bot for a new market type wires together: a TheoProvider implementation,
a QuotingStrategy choice, market-specific data hooks, and runs the existing
order-placement / decision-logging / dashboard infrastructure unchanged.

Adding a new market is one file in `theo/providers/` and (optionally) one
file in `quoting/strategies/`. The framework doesn't change.
"""

from lipmm.execution import (
    Balance,
    ExchangeClient,
    Order,
    OrderbookLevels,
    OrderManager,
    PlaceOrderRequest,
    Position,
)
from lipmm.execution.adapters import KalshiExchangeAdapter
from lipmm.control import (
    Broadcaster,
    ControlConfig,
    ControlServer,
    ControlState,
    KillState,
    ManualOrderOutcome,
    PauseScope,
    SideLock,
    build_app,
    submit_manual_order,
)
from lipmm.observability import (
    DecisionLogger,
    SCHEMA_VERSION,
    build_operator_command_record,
    build_record,
)
from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    MaxOrdersPerCycleGate,
    RiskContext,
    RiskGate,
    RiskRegistry,
    RiskVerdict,
)
from lipmm.quoting.strategies import (
    DefaultLIPQuoting,
    DefaultLIPQuotingConfig,
    StickyDefenseConfig,
    StickyDefenseQuoting,
    default_sticky,
)
from lipmm.runner import LIPRunner, RunnerConfig, TickerSource
from lipmm.theo import TheoProvider, TheoRegistry, TheoResult

__all__ = [
    # theo layer
    "TheoProvider",
    "TheoRegistry",
    "TheoResult",
    # quoting layer
    "OrderbookSnapshot",
    "OurState",
    "QuotingDecision",
    "QuotingStrategy",
    "SideDecision",
    # execution layer
    "Balance",
    "ExchangeClient",
    "Order",
    "OrderbookLevels",
    "OrderManager",
    "PlaceOrderRequest",
    "Position",
    # runner
    "LIPRunner",
    "RunnerConfig",
    "TickerSource",
    # built-in strategies
    "DefaultLIPQuoting",
    "DefaultLIPQuotingConfig",
    "StickyDefenseConfig",
    "StickyDefenseQuoting",
    "default_sticky",
    # observability
    "DecisionLogger",
    "SCHEMA_VERSION",
    "build_record",
    # risk
    "RiskContext",
    "RiskGate",
    "RiskRegistry",
    "RiskVerdict",
    "EndgameGuardrailGate",
    "MaxNotionalPerSideGate",
    "MaxOrdersPerCycleGate",
    # exchange adapters
    "KalshiExchangeAdapter",
    # control plane
    "Broadcaster",
    "ControlConfig",
    "ControlServer",
    "ControlState",
    "KillState",
    "ManualOrderOutcome",
    "PauseScope",
    "SideLock",
    "build_app",
    "build_operator_command_record",
    "submit_manual_order",
]
