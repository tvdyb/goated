"""MaxOrdersPerCycleGate — circuit breaker on quote actions per cycle.

Vetoes proposed quotes once a cumulative count of non-skip sides for the
current cycle hits the configured limit. Each call to check() that
includes a non-skip side burns budget; once exhausted, subsequent sides
this cycle get vetoed.

Designed as a runaway-strategy safety net: if a strategy bug causes it to
churn out hundreds of repositioned quotes per cycle, this gate caps the
damage to `max_orders` exchange API calls per cycle.

Counts non-skip sides as a proxy for orders-that-might-be-placed. The
actual exchange-API count depends on whether OrderManager amends, places
new, or no-changes — but at the gate evaluation point that hasn't been
decided yet. Conservative over-counting is preferred; the alternative is
allowing churn.

State: per-instance, resets when cycle_id advances. So the gate works
correctly across the runner's serial ticker iteration within a cycle, and
naturally resets when the next cycle begins.
"""

from __future__ import annotations

from lipmm.risk.base import RiskContext, RiskVerdict


class MaxOrdersPerCycleGate:
    name = "MaxOrdersPerCycleGate"

    def __init__(self, max_orders: int) -> None:
        if max_orders < 0:
            raise ValueError(f"max_orders must be >= 0, got {max_orders}")
        self._max_orders = int(max_orders)
        self._last_cycle_id: int | None = None
        self._count_in_cycle: int = 0

    async def check(self, context: RiskContext) -> RiskVerdict:
        # Reset counter on cycle transition
        if context.cycle_id != self._last_cycle_id:
            self._last_cycle_id = context.cycle_id
            self._count_in_cycle = 0

        # Allow runtime override via control_overrides (set via dashboard
        # Knobs tab). Lets the operator raise the cap without restart
        # when they're managing a lot of strikes per cycle.
        effective_max = self._max_orders
        try:
            ov = (context.control_overrides or {}).get("max_orders_per_cycle")
            if ov is not None:
                effective_max = max(0, int(ov))
        except (AttributeError, TypeError, ValueError):
            pass

        decision = context.decision
        bid_allow = True
        ask_allow = True
        bid_reason = ""
        ask_reason = ""

        # Process bid first, then ask. If bid would push us over the limit,
        # veto bid only — ask might still fit. Same for ask.
        if not decision.bid.skip:
            if self._count_in_cycle + 1 > effective_max:
                bid_allow = False
                bid_reason = (
                    f"cycle quota exhausted: {self._count_in_cycle} "
                    f"orders already this cycle, max={effective_max}"
                )
            else:
                self._count_in_cycle += 1

        if not decision.ask.skip:
            if self._count_in_cycle + 1 > effective_max:
                ask_allow = False
                ask_reason = (
                    f"cycle quota exhausted: {self._count_in_cycle} "
                    f"orders already this cycle, max={effective_max}"
                )
            else:
                self._count_in_cycle += 1

        return RiskVerdict(
            bid_allow=bid_allow, ask_allow=ask_allow,
            bid_reason=bid_reason, ask_reason=ask_reason,
        )
