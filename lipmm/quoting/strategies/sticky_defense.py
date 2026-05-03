"""StickyDefenseQuoting — wraps a base strategy with anti-drag stickiness.

Defends against LIP-pump-and-relax attacks where someone layers thin stacks
to ratchet our quote toward theo, then pulls. The wrapped state machine
(see `_sticky_machine.py`) tracks per-side state through 4 phases (NORMAL →
AGGRESSIVE → RELAXING / COOLDOWN), racing aggressively when pennied and
only relaxing after sustained 1.0x mult plus theo stability.

Composition pattern:

    sticky = StickyDefenseQuoting(base=DefaultLIPQuoting(), cfg=...)
    # OR convenience factory:
    sticky = default_sticky()

The base strategy provides the natural target each cycle; sticky decides
whether to override it. Sizing, anti-spoofing, and the no-cross guard all
delegate to the base — sticky only nudges the price by single cents and
preserves base's size/extras.

Three behaviors layered on top of the base:

  1. **Bypass gate** — when theo is in the deep wings (yes_cents <
     min_distance_from_theo or > 100 - min_distance_from_theo), sticky
     bypasses entirely and returns base_decision unchanged. Sticky's
     min_distance_from_theo invariant is incoherent at theo extremes;
     better to use the base's natural quoting there.

  2. **Confidence-aware widening** — when `theo.confidence < 1.0`, the
     effective bypass-gate boundary widens via:
         effective_min_dist = ceil(base_min_dist / max(0.1, confidence))
     Conf=1.0 → 15c (default). Conf=0.5 → 30c. Conf=0.1 → 150c (effectively
     bypass everything). The same effective_min_dist is also passed to the
     state machine via min_distance_from_theo_override, so AGGRESSIVE
     pricing widens its safe zone too.

  3. **COOLDOWN translates to skip=True** — when sticky's safety circuit
     breaker fires (AGGRESSIVE persisted past max-duration), the side
     emits a SideDecision(skip=True). The OrderManager already cancels the
     resting order and refrains from placing a new one on skip.

Composition notes (out of scope for this module):
  - Anti-churn (only reposition if multiplier dropped, or every 30s) is
    NOT included here. It belongs in a future composable wrapper that can
    layer over either DefaultLIPQuoting or StickyDefenseQuoting.
  - Sizing is delegated to the base's SideDecision.size. Sticky nudges
    price by single cents, so the size delta from re-computing is
    typically <10% — well within tolerance for LIP scoring.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from lipmm.quoting.base import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)
from lipmm.quoting.strategies._sticky_machine import StickyConfig, StickyQuoter
from lipmm.theo import TheoResult

logger = logging.getLogger(__name__)


@dataclass
class StickyDefenseConfig:
    sticky: StickyConfig = field(default_factory=StickyConfig)
    # Bypass-gate floor. Sticky only runs when min_dist <= theo <= 100 - min_dist.
    # Should be >= sticky.min_distance_from_theo so the bypass is at least as
    # wide as the safe zone; mismatch would let sticky run in regions where
    # its anti-spoof bound is degenerate.
    min_distance_from_theo: int = 15
    # When True, scale min_distance_from_theo by 1/max(0.1, theo.confidence).
    # Lower confidence widens the bypass and the machine's safe zone.
    confidence_widening: bool = True
    # When True, COOLDOWN skip's reason chains the base's reason for context.
    chain_cooldown_reason: bool = True


class StickyDefenseQuoting:
    """QuotingStrategy that wraps a base with anti-drag sticky overlays."""

    name = "sticky-defense"

    def __init__(
        self,
        base: QuotingStrategy,
        cfg: StickyDefenseConfig | None = None,
    ) -> None:
        self._base = base
        self._cfg = cfg or StickyDefenseConfig()
        self._sticky = StickyQuoter(self._cfg.sticky)

    async def warmup(self) -> None:
        await self._base.warmup()

    async def shutdown(self) -> None:
        await self._base.shutdown()

    async def quote(
        self,
        *,
        ticker: str,
        theo: TheoResult,
        orderbook: OrderbookSnapshot,
        our_state: OurState,
        now_ts: float,
        time_to_settle_s: float,
    ) -> QuotingDecision:
        # 1. Always run base first; we may end up returning it unchanged.
        base_decision = await self._base.quote(
            ticker=ticker, theo=theo, orderbook=orderbook,
            our_state=our_state, now_ts=now_ts,
            time_to_settle_s=time_to_settle_s,
        )

        eff_min = self._effective_min_dist(theo.confidence)

        # 2. Bypass gate: deep wings (where sticky's min_dist would be
        # incoherent) pass through to base unchanged.
        if theo.yes_cents < eff_min or theo.yes_cents > 100 - eff_min:
            return base_decision

        # 3. Apply sticky to each side.
        bid_final = self._adjust_side(
            "bid", base_decision.bid, theo, orderbook, our_state,
            now_ts, eff_min, ticker,
        )
        ask_final = self._adjust_side(
            "ask", base_decision.ask, theo, orderbook, our_state,
            now_ts, eff_min, ticker,
        )

        # 4. Post-override no-cross guard. Sticky's overrides may re-introduce
        # a cross even though base's guard ran already.
        bid_final, ask_final = self._no_cross(bid_final, ask_final, orderbook)

        # 5. Collect transitions tagged with side. Per-side adjust populates
        # base_decision-aware extras; transitions live in extras["transitions"]
        # so we don't need a separate accumulator.
        transitions = list(base_decision.transitions)
        for tr in bid_final.extras.get("_pending_transitions", []):
            transitions.append({"side": "bid", **tr})
        for tr in ask_final.extras.get("_pending_transitions", []):
            transitions.append({"side": "ask", **tr})

        # Strip the internal pending-transitions key from extras
        bid_clean = self._strip_pending(bid_final)
        ask_clean = self._strip_pending(ask_final)

        return QuotingDecision(
            bid=bid_clean, ask=ask_clean, transitions=transitions,
        )

    # ── helpers ──────────────────────────────────────────────────────

    def _effective_min_dist(self, confidence: float) -> int:
        """Confidence-aware widening of min_distance_from_theo.

        Conf=1.0 → base. Conf=0.5 → 2x. Conf=0.1 → 10x (capped).
        Confidence below 0.1 is treated as 0.1 to prevent unbounded
        widening — at that point the bypass gate effectively turns sticky
        off everywhere, which is the correct behavior for unreliable theo.
        """
        if not self._cfg.confidence_widening or confidence >= 1.0:
            return self._cfg.min_distance_from_theo
        scaled = self._cfg.min_distance_from_theo / max(0.1, confidence)
        return int(math.ceil(scaled))

    def _adjust_side(
        self,
        side: str,
        base_side: SideDecision,
        theo: TheoResult,
        orderbook: OrderbookSnapshot,
        our_state: OurState,
        now_ts: float,
        eff_min: int,
        ticker: str,
    ) -> SideDecision:
        """Apply sticky's per-side adjustment on top of base_side.

        Returns a SideDecision; if no override applies, returns base_side
        with sticky-state details merged into extras for observability.
        Stages a list at extras["_pending_transitions"] for the caller to
        promote into QuotingDecision.transitions.
        """
        # If base already vetoed, sticky has no opinion.
        if base_side.skip:
            return base_side

        if side == "bid":
            best_relevant = orderbook.best_bid
            our_current = our_state.cur_bid_px
        else:
            # For ask side: best_relevant is the lowest ask. When the book
            # is empty (best_ask=100) we pass 99 so the machine has a
            # sane "best" reference rather than the sentinel.
            best_relevant = orderbook.best_ask if orderbook.best_ask < 100 else 99
            our_current = our_state.cur_ask_px

        sticky_price, sticky_state, transitions = self._sticky.compute(
            ticker=ticker,
            side=side,
            natural_target=base_side.price,
            best_relevant=best_relevant,
            our_current=our_current,
            fair=float(theo.yes_cents),
            now=now_ts,
            min_distance_from_theo_override=eff_min,
        )

        # COOLDOWN signal: machine returns price=0 → strategy emits skip.
        if sticky_state == "COOLDOWN":
            chained = (
                f"sticky COOLDOWN (was: {base_side.reason})"
                if self._cfg.chain_cooldown_reason and base_side.reason
                else "sticky COOLDOWN"
            )
            return SideDecision(
                price=0, size=0, skip=True, reason=chained,
                extras={
                    **base_side.extras,
                    "sticky_state": sticky_state,
                    "natural_target": base_side.price,
                    "_pending_transitions": transitions,
                },
            )

        # Sticky agrees with base → return base unchanged but enrich extras
        # so downstream sees the state machine's view.
        if sticky_price == base_side.price:
            return SideDecision(
                price=base_side.price,
                size=base_side.size,
                skip=False,
                reason=base_side.reason,
                extras={
                    **base_side.extras,
                    "sticky_state": sticky_state,
                    "natural_target": base_side.price,
                    "_pending_transitions": transitions,
                },
            )

        # Sticky overrode the price. Preserve base's size — the price
        # nudge is small enough that re-sizing isn't worth the coupling.
        return SideDecision(
            price=sticky_price,
            size=base_side.size,
            skip=False,
            reason=(
                f"sticky {sticky_state}: {base_side.price}→{sticky_price} "
                f"(was: {base_side.reason})"
            ),
            extras={
                **base_side.extras,
                "sticky_state": sticky_state,
                "natural_target": base_side.price,
                "sticky_price": sticky_price,
                "_pending_transitions": transitions,
            },
        )

    @staticmethod
    def _no_cross(
        bid: SideDecision, ask: SideDecision, ob: OrderbookSnapshot,
    ) -> tuple[SideDecision, SideDecision]:
        """Re-apply no-cross guard after sticky overrides may have moved
        prices. Mirrors the base strategy's guard — kept here because we
        operate on the post-override prices, which the base never sees."""
        if (not bid.skip and not ask.skip
                and bid.price > 0 and ask.price > 0
                and bid.price >= ask.price):
            # The two sticky-adjusted prices crossed each other. Pull bid
            # back to ask - 1 (preserve ask, sacrifice the bid push).
            new_bid_price = max(1, ask.price - 1)
            bid = SideDecision(
                price=new_bid_price,
                size=bid.size,
                skip=False,
                reason=f"no-cross post-sticky: bid pulled to {new_bid_price} (ask {ask.price})",
                extras=bid.extras,
            )
        # Also guard against the live opposite-best (book may have moved
        # since base ran)
        if (not bid.skip and bid.price > 0
                and ob.best_ask < 100 and bid.price >= ob.best_ask):
            new_bid_price = max(1, ob.best_ask - 1)
            bid = SideDecision(
                price=new_bid_price,
                size=bid.size,
                skip=False,
                reason=f"no-cross post-sticky: bid pulled to {new_bid_price} (best_ask {ob.best_ask})",
                extras=bid.extras,
            )
        if (not ask.skip and ask.price > 0
                and ob.best_bid > 0 and ask.price <= ob.best_bid):
            new_ask_price = min(99, ob.best_bid + 1)
            ask = SideDecision(
                price=new_ask_price,
                size=ask.size,
                skip=False,
                reason=f"no-cross post-sticky: ask pulled to {new_ask_price} (best_bid {ob.best_bid})",
                extras=ask.extras,
            )
        return bid, ask

    @staticmethod
    def _strip_pending(side: SideDecision) -> SideDecision:
        """Remove the internal _pending_transitions key from extras before
        returning to the caller."""
        if "_pending_transitions" not in side.extras:
            return side
        clean_extras = {k: v for k, v in side.extras.items()
                        if k != "_pending_transitions"}
        return SideDecision(
            price=side.price, size=side.size, skip=side.skip,
            reason=side.reason, extras=clean_extras,
        )


def default_sticky(
    sticky_cfg: StickyConfig | None = None,
    default_cfg=None,
) -> StickyDefenseQuoting:
    """Convenience factory: StickyDefenseQuoting wrapping DefaultLIPQuoting.

    The most common composition. Pass either config to override defaults;
    pass neither for a "just give me sensible sticky on default quoting"
    setup.
    """
    from lipmm.quoting.strategies.default import DefaultLIPQuoting
    base = DefaultLIPQuoting(default_cfg) if default_cfg else DefaultLIPQuoting()
    cfg = StickyDefenseConfig(sticky=sticky_cfg or StickyConfig())
    return StickyDefenseQuoting(base=base, cfg=cfg)
