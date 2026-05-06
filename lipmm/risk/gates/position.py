"""MaxPositionPerSideGate — caps directional exposure per strike.

Rationale: in adverse-selection-heavy markets, the bot's bid keeps
filling on the way down and the ask keeps filling on the way up. The
operator wants a hard ceiling on how lopsided we get. This gate
checks the live Yes-side position (from the runner's runtime cache)
and vetoes the side that would grow it further once a configurable
threshold is hit.

Convention: `position_quantity` is in Yes contracts. Positive = net
long Yes (we paid for those Yes shares). Negative = net short Yes
(equivalent to net long No).

  - Veto BID when `position_quantity >= max`. Buying more Yes would
    deepen our long position past the cap.
  - Veto ASK when `position_quantity <= -max`. Selling more Yes
    (short) would deepen our short position past the cap.

Both sides STAY allowed when we're inside [-max, +max], even if one
side would push us past the cap on a single fill. The gate is a
soft brake, not a hard one — order sizing already limits per-fill
exposure.

The threshold is operator-tunable via the `max_position_per_side`
knob (per-strike or per-event override supported via the standard
control_overrides dict).
"""

from __future__ import annotations

from lipmm.risk.base import RiskContext, RiskVerdict


class MaxPositionPerSideGate:
    """Caps how lopsided one strike's net position can grow."""

    name = "MaxPositionPerSideGate"

    def __init__(self, max_position: int = 100) -> None:
        if max_position < 0:
            raise ValueError(f"max_position must be >= 0, got {max_position}")
        self._max_position = int(max_position)

    async def check(self, context: RiskContext) -> RiskVerdict:
        # Allow runtime override via control_overrides (knob:
        # max_position_per_side). Operator can also set it per-strike
        # or per-event via the layered knob mechanism.
        effective_max = self._max_position
        try:
            ov = (context.control_overrides or {}).get("max_position_per_side")
            if ov is not None:
                effective_max = max(0, int(ov))
        except (AttributeError, TypeError, ValueError):
            pass

        decision = context.decision
        position = context.position_quantity
        bid_allow = True
        ask_allow = True
        bid_reason = ""
        ask_reason = ""

        if not decision.bid.skip and position >= effective_max:
            bid_allow = False
            bid_reason = (
                f"bid blocked: already long Yes {position} ≥ "
                f"max_position_per_side {effective_max} on {context.ticker}"
            )
        if not decision.ask.skip and position <= -effective_max:
            ask_allow = False
            ask_reason = (
                f"ask blocked: already short Yes {position} ≤ "
                f"-max_position_per_side {effective_max} on {context.ticker}"
            )
        return RiskVerdict(
            bid_allow=bid_allow, ask_allow=ask_allow,
            bid_reason=bid_reason, ask_reason=ask_reason,
        )
