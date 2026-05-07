"""MaxNotionalPerSideGate — caps capital risk per fill at the limit price.

Notional is the worst-case dollar loss on a fill of the proposed quote:

  Bid (buying Yes at price P): cost = P × size cents = P × size / 100 dollars.
    Worst case is Yes settles No, payout 0, loss = cost.

  Ask (selling Yes at price P): max loss = (100 - P) × size cents.
    Worst case is Yes settles, payout 100, we received P, loss = 100 - P.

Both are dollar-bounded by the gate's `max_dollars`. Sides exceeding the
cap are vetoed; the bot can still quote the OTHER side at smaller size if
it fits.

Common operator setup: `MaxNotionalPerSideGate(max_dollars=2.00)`. Combined
with the strategy's per-dollar sizing (`dollars_per_side: 1.00`), this
defends against sizing bugs — a misconfigured strategy producing 1000c
quotes at 100 contracts would be vetoed instead of risking $1000 per side.
"""

from __future__ import annotations

from lipmm.risk.base import RiskContext, RiskVerdict


class MaxNotionalPerSideGate:
    name = "MaxNotionalPerSideGate"

    def __init__(self, max_dollars: float) -> None:
        if max_dollars <= 0:
            raise ValueError(f"max_dollars must be > 0, got {max_dollars}")
        self._max_dollars = float(max_dollars)

    async def check(self, context: RiskContext) -> RiskVerdict:
        decision = context.decision
        bid_allow = True
        ask_allow = True
        bid_reason = ""
        ask_reason = ""

        # Per-strike / per-event / global override (knob:
        # "max_notional_per_side_dollars"). Without this, an operator who
        # bumps `dollars_per_side` per strike higher than the gate's
        # static cap silently sees the bot stop trading on that strike —
        # the strategy sizes up, the gate vetoes, no signal in the UI.
        # Mirrors the override behaviour of the position / mid-delta /
        # cycle-throttle gates.
        effective_max = self._max_dollars
        if context.control_overrides is not None:
            ov = context.control_overrides.get("max_notional_per_side_dollars")
            if ov is not None:
                try:
                    effective_max = float(ov)
                except (TypeError, ValueError):
                    pass

        if not decision.bid.skip:
            # t1c × contracts / 1000 = dollars (10 t1c = 1¢, 100¢ = $1)
            bid_t1c = decision.bid.effective_t1c()
            bid_notional = bid_t1c * decision.bid.size / 1000.0
            if bid_notional > effective_max:
                bid_allow = False
                bid_reason = (
                    f"bid notional ${bid_notional:.2f} > max ${effective_max:.2f} "
                    f"(price={bid_t1c/10:.1f}¢ × size={decision.bid.size})"
                )

        if not decision.ask.skip:
            # max loss on ask = (1000 - price_t1c) × size / 1000 dollars
            ask_t1c = decision.ask.effective_t1c()
            ask_notional = (1000 - ask_t1c) * decision.ask.size / 1000.0
            if ask_notional > effective_max:
                ask_allow = False
                ask_reason = (
                    f"ask notional ${ask_notional:.2f} > max ${effective_max:.2f} "
                    f"(price={ask_t1c/10:.1f}¢ × size={decision.ask.size})"
                )

        return RiskVerdict(
            bid_allow=bid_allow, ask_allow=ask_allow,
            bid_reason=bid_reason, ask_reason=ask_reason,
        )
