"""DefaultLIPQuoting — penny-inside-best with anti-spoofing.

The reference quoting strategy. Sensible defaults for a generic Kalshi
LIP-incentive market: penny inside the best on each side, bound by an
anti-spoofing tolerance around theo, sized by a per-dollar capital budget,
and skip entirely when theo confidence is too low.

This strategy DOES NOT include the sticky state machine or anti-churn
logic. Those live in separate strategy implementations (see
`StickyDefenseQuoting` if/when ported) and can be selected per-market.

If you want sticky behavior, use a different strategy. If you want simple
robust market-making with no drag-attack defense, this is what you want.

Config (all in cents unless noted):
  desert_threshold_c:    >this gap from theo to best → desert mode
  max_half_spread_c:     half-width when one side is empty (best_bid=0 or
                         best_ask=100) — quote at theo ± this many cents
  max_distance_from_best:active-mode follow distance (1 = penny inside)
  theo_tolerance_c:      anti-spoofing window. bid ≤ theo+tolerance,
                         ask ≥ theo-tolerance. Set lower for tighter trust.
  dollars_per_side:      capital budget per fill. 0 → fall back to
                         contracts_per_side. >0 → contracts =
                         dollars_per_side × 100 / cost_per_contract.
  contracts_per_side:    legacy fallback when dollars_per_side ≤ 0
  min_contracts:         floor on computed size
  max_contracts:         cap on computed size (LIP top-300 ceiling)
  min_theo_confidence:   below this confidence, skip the strike entirely
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from lipmm.quoting.base import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)
from lipmm.theo import TheoResult

logger = logging.getLogger(__name__)


@dataclass
class DefaultLIPQuotingConfig:
    desert_threshold_c: int = 10
    desert_relative_pct: float = 0.30
    max_half_spread_c: int = 4
    max_distance_from_best: int = 1
    theo_tolerance_c: int = 2
    dollars_per_side: float = 1.00
    contracts_per_side: int = 12
    min_contracts: int = 5
    max_contracts: int = 300
    min_theo_confidence: float = 0.10
    penny_inside_min_confidence: float = 0.70
    """At theo.confidence ≥ this threshold the strategy switches from
    `active-follow` (1c BEHIND best) to `active-penny` (1c INSIDE
    best) — i.e. trusts theo enough to take the LIP-multiplier-1.0
    spot at best+1 / best-1, accepting whatever fills come. Default
    0.70 = framework's "trust within ~3c" calibration."""


class DefaultLIPQuoting:
    """Penny-inside-best LIP quoting with anti-spoofing and confidence gating."""

    name = "default-lip-quoting"

    def __init__(self, cfg: DefaultLIPQuotingConfig | None = None) -> None:
        self._cfg = cfg or DefaultLIPQuotingConfig()

    async def warmup(self) -> None:
        return

    async def shutdown(self) -> None:
        return

    async def quote(
        self,
        *,
        ticker: str,
        theo: TheoResult,
        orderbook: OrderbookSnapshot,
        our_state: OurState,
        now_ts: float,
        time_to_settle_s: float,
        control_overrides: dict | None = None,
    ) -> QuotingDecision:
        # Build an effective config for this call from base + control overrides.
        # Overrides documented for this strategy:
        #   "min_theo_confidence" → DefaultLIPQuotingConfig.min_theo_confidence
        #   "theo_tolerance_c"    → DefaultLIPQuotingConfig.theo_tolerance_c
        #   "max_distance_from_best" → DefaultLIPQuotingConfig.max_distance_from_best
        #   "dollars_per_side"    → DefaultLIPQuotingConfig.dollars_per_side
        cfg = self._effective_cfg(control_overrides)
        # Use cfg locally instead of self._cfg so per-call helpers see overrides.
        # Helpers (_compute_bid, _compute_ask, _size_for_quote) read self._cfg
        # directly; we temporarily swap it for the duration of this call to
        # avoid threading cfg through every helper signature. Swap is safe
        # because quote() is not re-entrant on the same instance per asyncio's
        # cooperative scheduling — but we restore in a finally to be defensive.
        original_cfg = self._cfg
        self._cfg = cfg
        try:
            # Confidence gate: skip both sides if theo unreliable
            if theo.confidence < cfg.min_theo_confidence:
                reason = (
                    f"theo confidence {theo.confidence:.2f} < gate "
                    f"{cfg.min_theo_confidence}; theo source={theo.source}"
                )
                return QuotingDecision(
                    bid=SideDecision(price=0, size=0, skip=True, reason=reason),
                    ask=SideDecision(price=0, size=0, skip=True, reason=reason),
                )

            fair = theo.yes_cents
            bid_decision = self._compute_bid(fair, orderbook, theo.confidence)
            ask_decision = self._compute_ask(fair, orderbook, theo.confidence)

            # No-cross guard: if our proposed quotes would cross the opposite
            # best, post_only would reject. Pull back by 1c.
            if (bid_decision.price > 0 and orderbook.best_ask < 100
                    and bid_decision.price >= orderbook.best_ask):
                bid_decision = SideDecision(
                    price=orderbook.best_ask - 1,
                    size=self._size_for_quote(orderbook.best_ask - 1, "bid"),
                    skip=False,
                    reason=f"no-cross: bid pulled to {orderbook.best_ask - 1} (best_ask {orderbook.best_ask})",
                    extras=bid_decision.extras,
                )
            if (ask_decision.price > 0 and orderbook.best_bid > 0
                    and ask_decision.price <= orderbook.best_bid):
                ask_decision = SideDecision(
                    price=orderbook.best_bid + 1,
                    size=self._size_for_quote(orderbook.best_bid + 1, "ask"),
                    skip=False,
                    reason=f"no-cross: ask pulled to {orderbook.best_bid + 1} (best_bid {orderbook.best_bid})",
                    extras=ask_decision.extras,
                )

            return QuotingDecision(bid=bid_decision, ask=ask_decision)
        finally:
            # Restore base config so concurrent / future calls see defaults
            self._cfg = original_cfg

    def _effective_cfg(self, overrides: dict | None) -> "DefaultLIPQuotingConfig":
        """Build a per-call config dataclass with control overrides applied.
        Returns base cfg unchanged if no relevant overrides are set."""
        if not overrides:
            return self._cfg
        base = self._cfg
        kwargs = {
            "desert_threshold_c": int(overrides.get(
                "desert_threshold_c", base.desert_threshold_c,
            )),
            "desert_relative_pct": base.desert_relative_pct,
            "max_half_spread_c": base.max_half_spread_c,
            "max_distance_from_best": int(overrides.get(
                "max_distance_from_best", base.max_distance_from_best,
            )),
            "theo_tolerance_c": int(overrides.get(
                "theo_tolerance_c", base.theo_tolerance_c,
            )),
            "dollars_per_side": float(overrides.get(
                "dollars_per_side", base.dollars_per_side,
            )),
            "contracts_per_side": base.contracts_per_side,
            "min_contracts": base.min_contracts,
            "max_contracts": base.max_contracts,
            "min_theo_confidence": float(overrides.get(
                "min_theo_confidence", base.min_theo_confidence,
            )),
            "penny_inside_min_confidence": float(overrides.get(
                "penny_inside_min_confidence", base.penny_inside_min_confidence,
            )),
        }
        return DefaultLIPQuotingConfig(**kwargs)

    # ── per-side computation ──────────────────────────────────────────

    def _compute_bid(
        self, fair: int, ob: OrderbookSnapshot, confidence: float = 0.0,
    ) -> SideDecision:
        cfg = self._cfg
        best_bid = ob.best_bid

        if best_bid <= 0:
            # Empty bid side — quote at theo - max_half_spread
            target = fair - cfg.max_half_spread_c
            mode = "no-best-bid"
        elif self._is_desert(fair, best_bid):
            # Desert: penny inside best
            target = best_bid + 1
            mode = "desert-penny"
        elif fair >= 97:
            # Deep ITM: match best (no pennying — too risky on near-certain Yes)
            target = best_bid
            mode = "deep-itm-match"
        elif confidence >= cfg.penny_inside_min_confidence:
            # High-confidence active mode: penny INSIDE the best to take
            # the LIP-multiplier-1.0 spot at best+1. Anti-spoofing cap
            # below still binds, so we won't chase fake quotes above theo.
            target = best_bid + 1
            mode = "active-penny"
        else:
            # Active mode: stay max_distance_from_best behind best
            target = best_bid - cfg.max_distance_from_best
            mode = "active-follow"

        # Anti-spoofing cap: never bid above theo + tolerance
        cap = fair - 1 + cfg.theo_tolerance_c
        bound_target = min(target, cap)

        # Clamp to valid Kalshi price range
        final = max(1, min(99, bound_target))
        size = self._size_for_quote(final, "bid")

        return SideDecision(
            price=final,
            size=size,
            skip=False,
            reason=f"bid {mode}: best={best_bid}, target={target}, capped@{cap} → {final}c × {size}",
            extras={"mode": mode, "best_bid": best_bid, "fair": fair, "cap": cap},
        )

    def _compute_ask(
        self, fair: int, ob: OrderbookSnapshot, confidence: float = 0.0,
    ) -> SideDecision:
        cfg = self._cfg
        best_ask = ob.best_ask

        if best_ask >= 100:
            target = fair + cfg.max_half_spread_c
            mode = "no-best-ask"
        elif self._is_desert(100 - fair, 100 - best_ask):
            # Symmetric desert check (No-side perspective)
            target = best_ask - 1
            mode = "desert-penny"
        elif fair <= 3:
            target = best_ask
            mode = "deep-otm-match"
        elif fair >= 97:
            target = best_ask
            mode = "deep-itm-match"
        elif confidence >= cfg.penny_inside_min_confidence:
            target = best_ask - 1
            mode = "active-penny"
        else:
            target = best_ask + cfg.max_distance_from_best
            mode = "active-follow"

        # Anti-spoofing floor: never ask below theo - tolerance
        floor = fair + 1 - cfg.theo_tolerance_c
        bound_target = max(target, floor)
        final = max(1, min(99, bound_target))
        size = self._size_for_quote(final, "ask")

        return SideDecision(
            price=final,
            size=size,
            skip=False,
            reason=f"ask {mode}: best={best_ask}, target={target}, floored@{floor} → {final}c × {size}",
            extras={"mode": mode, "best_ask": best_ask, "fair": fair, "floor": floor},
        )

    def _is_desert(self, fair: int, best: int) -> bool:
        """A side is desert if best is far from theo absolutely OR in
        proportion to the room theo has on that side. The proportional
        clause catches deep-OTM where 6c gap is huge relative to a 2c theo."""
        cfg = self._cfg
        gap = abs(best - fair)
        if gap > cfg.desert_threshold_c:
            return True
        denom = max(1, fair) if fair > 0 else 1
        return gap / denom > cfg.desert_relative_pct

    # ── sizing ───────────────────────────────────────────────────────

    def _size_for_quote(self, quote_cents: int, side: str) -> int:
        cfg = self._cfg
        if cfg.dollars_per_side <= 0:
            return cfg.contracts_per_side
        if quote_cents < 1 or quote_cents > 99:
            return cfg.min_contracts
        if side == "bid":
            cost = quote_cents
        elif side == "ask":
            cost = max(1, 100 - quote_cents)
        else:
            return cfg.min_contracts
        raw = int(cfg.dollars_per_side * 100 / cost)
        return max(cfg.min_contracts, min(cfg.max_contracts, raw))
