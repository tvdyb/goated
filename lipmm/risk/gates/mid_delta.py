"""MidDeltaGate — vetoes both sides on rapid mid moves.

Rationale: when a market mid moves abruptly (e.g., 19/21 → 33/35,
delta of 13¢), it usually means new information arrived that the
bot's theo doesn't yet reflect. Quoting through the move means
getting adversely selected on every fill. The gate detects the move
and pulls the bot until the next mid is observed (the next cycle's
"last mid" becomes the moved value, so the gate self-clears once
volatility settles).

The threshold is in cents (`mid_delta_threshold_c`). A value of 5
means: if the mid moved ≥ 5¢ since the last observed value, both
sides are vetoed for this cycle. Operator can tune via the
`mid_delta_threshold_c` knob (global, per-event, or per-strike).

Implementation: in-memory dict `last_mid_t1c[ticker]`. Updated on
each cycle regardless of veto outcome. Stale tickers are not pruned
(dict is bounded by the active-events × strikes count which is
finite). Resets on bot restart.
"""

from __future__ import annotations

from lipmm.risk.base import RiskContext, RiskVerdict


class MidDeltaGate:
    """Vetoes both sides if the orderbook mid moved by more than
    `mid_delta_threshold_c` cents since the last cycle for this
    strike."""

    name = "MidDeltaGate"

    def __init__(self, mid_delta_threshold_c: float = 5.0) -> None:
        if mid_delta_threshold_c < 0:
            raise ValueError(
                f"mid_delta_threshold_c must be >= 0, got {mid_delta_threshold_c}"
            )
        self._threshold_c = float(mid_delta_threshold_c)
        self._last_mid_c: dict[str, float] = {}

    async def check(self, context: RiskContext) -> RiskVerdict:
        # Read effective threshold from control_overrides if set.
        threshold_c = self._threshold_c
        try:
            ov = (context.control_overrides or {}).get("mid_delta_threshold_c")
            if ov is not None:
                threshold_c = max(0.0, float(ov))
        except (AttributeError, TypeError, ValueError):
            pass

        # Compute current mid in cents (integer + half-cent for sub-
        # cent markets via theo.extras when available).
        mid_c: float | None = None
        ex = context.theo.extras or {}
        if "mid_cents" in ex:
            try:
                mid_c = float(ex["mid_cents"])
            except (TypeError, ValueError):
                mid_c = None
        if mid_c is None:
            # Fallback: use theo's yes_cents as a proxy.
            mid_c = float(context.theo.yes_cents)

        # First sighting: store and allow.
        prev = self._last_mid_c.get(context.ticker)
        self._last_mid_c[context.ticker] = mid_c
        if prev is None:
            return RiskVerdict()

        delta = abs(mid_c - prev)
        # Threshold of 0 means "disabled" (no veto). Avoids surprising
        # operators who set it to 0 expecting "no constraint".
        if threshold_c <= 0 or delta < threshold_c:
            return RiskVerdict()

        reason = (
            f"mid moved {delta:.1f}¢ (from {prev:.1f}¢ to {mid_c:.1f}¢) "
            f">= threshold {threshold_c:.1f}¢ — vetoing both sides this cycle"
        )
        return RiskVerdict(
            bid_allow=False, ask_allow=False,
            bid_reason=reason, ask_reason=reason,
        )
