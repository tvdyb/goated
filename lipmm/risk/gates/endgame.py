"""EndgameGuardrailGate — pulls deep-wing quotes near settlement.

Real-world incident this guards against:

  Soy bot, settlement day, 2 hours to settle. Theo on T1196.99 was 0c
  (deep OTM) and on T1136.99 was 100c (deep ITM). Bot was LIP-farming
  both: bidding 1c on T1196.99 Yes (lottery ticket) and asking 99c on
  T1136.99 Yes (sell near-certain Yes). Position-clearing sellers and
  buyers picked off both sides as the market consensus hardened.
  Result: ~$6 of asymmetric pickoff loss in one afternoon.

The endgame guardrail vetoes the SIDE that creates this asymmetric risk:

  - When theo.yes_cents <= deep_otm_threshold (very unlikely Yes):
    veto BID. Don't keep buying lottery tickets in the final hours when
    sellers are clearing.

  - When theo.yes_cents >= deep_itm_threshold (very likely Yes):
    veto ASK. Don't keep selling near-certain Yes for cheap when buyers
    are picking off.

Active only inside the time window (`time_to_settle_s < min_seconds`).
Outside the window, allows everything — long-tail LIP earnings on these
strikes are valuable when there's still time for the book to recover from
adverse fills.

Mid-range theos (between deep_otm and deep_itm thresholds) are unaffected
even inside the time window — those positions don't have the asymmetric
pickoff property.
"""

from __future__ import annotations

from lipmm.risk.base import RiskContext, RiskVerdict


class EndgameGuardrailGate:
    name = "EndgameGuardrailGate"

    def __init__(
        self,
        min_seconds_to_settle: float,
        deep_otm_threshold: int,
        deep_itm_threshold: int,
    ) -> None:
        if not (0 <= deep_otm_threshold < deep_itm_threshold <= 100):
            raise ValueError(
                f"thresholds must satisfy 0 <= otm({deep_otm_threshold}) "
                f"< itm({deep_itm_threshold}) <= 100"
            )
        self._min_s = float(min_seconds_to_settle)
        self._deep_otm = int(deep_otm_threshold)
        self._deep_itm = int(deep_itm_threshold)

    async def check(self, context: RiskContext) -> RiskVerdict:
        # Outside the window, allow everything
        if context.time_to_settle_s >= self._min_s:
            return RiskVerdict()

        theo_yes = context.theo.yes_cents
        bid_allow = True
        ask_allow = True
        bid_reason = ""
        ask_reason = ""

        if theo_yes <= self._deep_otm:
            # Very unlikely Yes — don't buy lottery tickets near settle
            bid_allow = False
            bid_reason = (
                f"deep OTM (theo Yes={theo_yes}c <= {self._deep_otm}c) and "
                f"{context.time_to_settle_s:.0f}s to settle (< {self._min_s:.0f}s) "
                f"— pulling bid to avoid pickoff"
            )

        if theo_yes >= self._deep_itm:
            # Very likely Yes — don't sell near-certain Yes for cheap
            ask_allow = False
            ask_reason = (
                f"deep ITM (theo Yes={theo_yes}c >= {self._deep_itm}c) and "
                f"{context.time_to_settle_s:.0f}s to settle (< {self._min_s:.0f}s) "
                f"— pulling ask to avoid pickoff"
            )

        return RiskVerdict(
            bid_allow=bid_allow, ask_allow=ask_allow,
            bid_reason=bid_reason, ask_reason=ask_reason,
        )
