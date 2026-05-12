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

from lipmm.execution.base import tick_at as _tick_at
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
    match_best_min_confidence: float = 0.70
    """At confidence ≥ this AND below `penny_inside_min_confidence`,
    the strategy MATCHES the best on each side (bid = best_bid,
    ask = best_ask) — sits at the LIP reference price without
    pennying inside. Default 0.70 = framework's "trust within ~3c"
    calibration. Below this threshold, the strategy reverts to
    active-follow (1¢ behind best)."""
    penny_inside_min_confidence: float = 0.95
    """At theo.confidence ≥ this threshold the strategy goes
    `active-penny` (N cents INSIDE best) — i.e. trusts theo enough to
    take the spot inside the LIP reference price, accepting whatever
    fills come. Default 0.95 = "near-certain" theo. Should be ≥
    `match_best_min_confidence`."""
    penny_inside_distance: int = 1
    """In active-penny mode, how many cents INSIDE best to quote.
    Default 1 (penny inside). Higher values are more aggressive: at
    distance=3, bid = best_bid + 3 / ask = best_ask − 3. The bot
    still respects the no-cross guard (won't quote at or beyond the
    opposite best) and the anti-spoofing cap (won't quote above
    `theo - 1 + theo_tolerance_c`). To go meaningfully aggressive
    you typically also raise `theo_tolerance_c` so the cap doesn't
    bind."""
    max_distance_from_extremes_c: int = 0
    """**Tail-only mode.** When > 0, hard-caps the bid at this many
    cents above 0 and the ask at the same many cents below 100. So
    `max_distance_from_extremes_c=5` forces bid ∈ [1, 5¢] and ask ∈
    [95, 99¢] regardless of theo, best bid/ask, or strategy mode.
    Default 0 = disabled.

    Use case: batch-released markets with very wide spreads (02/98
    book) where the middle is untrusted and a naive penny-inside
    could leave us at 95¢ exposed to a spoof-and-hit. Turning this
    on for the duration of the launch keeps the bot at the
    statistical tails (where most binary outcomes settle) and lets
    it earn LIP rebates safely until the book normalizes."""


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
        bid_overrides: dict | None = None,
        ask_overrides: dict | None = None,
    ) -> QuotingDecision:
        # Build an effective config for this call from base + control overrides.
        # Overrides documented for this strategy:
        #   "min_theo_confidence" → DefaultLIPQuotingConfig.min_theo_confidence
        #   "theo_tolerance_c"    → DefaultLIPQuotingConfig.theo_tolerance_c
        #   "max_distance_from_best" → DefaultLIPQuotingConfig.max_distance_from_best
        #   "dollars_per_side"    → DefaultLIPQuotingConfig.dollars_per_side
        #
        # Per-side overrides: when `bid_overrides` / `ask_overrides` are
        # passed, each side gets its own effective config. Used to
        # support operator-set asymmetric knobs (different
        # `theo_tolerance_c` on bid vs ask, etc). Falls back to the
        # both-side `control_overrides` dict when per-side dicts aren't
        # provided. The confidence-gate / crossed-book pre-checks use
        # the both-side config since they're inherently symmetric.
        cfg = self._effective_cfg(control_overrides)
        bid_cfg = self._effective_cfg(bid_overrides) if bid_overrides is not None else cfg
        ask_cfg = self._effective_cfg(ask_overrides) if ask_overrides is not None else cfg
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

            # Crossed-book guard: when best_bid >= best_ask (with both
            # sides present), the orderbook is in an inconsistent state
            # — usually a transient mid-snapshot artifact. Quoting
            # through it produces side decisions that fight each other
            # via the no-cross guard. Skip both sides; next cycle will
            # see a clean book.
            best_bid_t1c = orderbook.best_bid_t1c
            best_ask_t1c = orderbook.best_ask_t1c
            if (best_bid_t1c > 0 and best_ask_t1c < 1000
                    and best_bid_t1c >= best_ask_t1c):
                reason = (
                    f"crossed book: bid_t1c={best_bid_t1c} >= "
                    f"ask_t1c={best_ask_t1c}"
                )
                return QuotingDecision(
                    bid=SideDecision(price=0, size=0, skip=True, reason=reason),
                    ask=SideDecision(price=0, size=0, skip=True, reason=reason),
                )

            fair = theo.yes_cents
            # Compute each side under its own cfg by swapping in/out.
            self._cfg = bid_cfg
            bid_decision = self._compute_bid(fair, orderbook, theo.confidence)
            self._cfg = ask_cfg
            ask_decision = self._compute_ask(fair, orderbook, theo.confidence)

            # No-cross guard in t1c so sub-cent quotes pull back by one
            # tick (not a full cent). post_only would reject crossing.
            # (best_bid_t1c / best_ask_t1c already read above.)
            if (bid_decision.effective_t1c() > 0 and best_ask_t1c < 1000
                    and bid_decision.effective_t1c() >= best_ask_t1c):
                tick = _tick_at(orderbook.tick_schedule, best_ask_t1c)
                pulled_t1c = max(1, best_ask_t1c - tick)
                self._cfg = bid_cfg
                bid_decision = SideDecision(
                    price=max(1, (pulled_t1c + 5) // 10),
                    price_t1c=pulled_t1c,
                    size=self._size_for_quote_t1c(pulled_t1c, "bid"),
                    skip=False,
                    reason=f"no-cross: bid pulled to {pulled_t1c}t1c ({pulled_t1c/10:.1f}¢)",
                    extras=bid_decision.extras,
                )
            if (ask_decision.effective_t1c() > 0 and best_bid_t1c > 0
                    and ask_decision.effective_t1c() <= best_bid_t1c):
                tick = _tick_at(orderbook.tick_schedule, best_bid_t1c)
                pulled_t1c = min(989, best_bid_t1c + tick)
                self._cfg = ask_cfg
                ask_decision = SideDecision(
                    price=min(99, (pulled_t1c + 5) // 10),
                    price_t1c=pulled_t1c,
                    size=self._size_for_quote_t1c(pulled_t1c, "ask"),
                    skip=False,
                    reason=f"no-cross: ask pulled to {pulled_t1c}t1c ({pulled_t1c/10:.1f}¢)",
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
            "match_best_min_confidence": float(overrides.get(
                "match_best_min_confidence", base.match_best_min_confidence,
            )),
            "penny_inside_min_confidence": float(overrides.get(
                "penny_inside_min_confidence", base.penny_inside_min_confidence,
            )),
            "penny_inside_distance": int(overrides.get(
                "penny_inside_distance", base.penny_inside_distance,
            )),
            "max_distance_from_extremes_c": int(overrides.get(
                "max_distance_from_extremes_c", base.max_distance_from_extremes_c,
            )),
        }
        return DefaultLIPQuotingConfig(**kwargs)

    # ── per-side computation ──────────────────────────────────────────

    def _compute_bid(
        self, fair: int, ob: OrderbookSnapshot, confidence: float = 0.0,
    ) -> SideDecision:
        """Compute bid price in t1c (tenths-of-a-cent) for sub-cent
        precision. Tick size is looked up per-band so on a mixed-tick
        market each price lands on a quotable tick.

        All arithmetic in t1c. Anti-spoofing cap and clamps converted
        to t1c. Final SideDecision carries both cents (rounded) and
        price_t1c (precise) — adapter routes through Kalshi's
        fractional path when price_t1c isn't a whole-cent multiple.
        """
        cfg = self._cfg
        best_bid_t1c = ob.best_bid_t1c
        best_bid_c = best_bid_t1c // 10  # for desert/deep-itm checks (cents semantics)
        # Tick size that applies near the best bid. For active modes
        # this is the increment we add/subtract to step inside or
        # behind the best.
        tick = _tick_at(ob.tick_schedule, max(10, best_bid_t1c))

        if best_bid_t1c <= 0:
            # Empty bid side — quote at theo - max_half_spread (cents)
            target_t1c = (fair - cfg.max_half_spread_c) * 10
            mode = "no-best-bid"
        elif self._is_desert(fair, best_bid_c):
            # Desert: penny inside best (one tick)
            target_t1c = best_bid_t1c + tick
            mode = "desert-penny"
        elif fair >= 97:
            # Deep ITM: match best
            target_t1c = best_bid_t1c
            mode = "deep-itm-match"
        elif confidence >= cfg.penny_inside_min_confidence:
            # Highest-confidence: N ticks INSIDE the best. Clamp the
            # step so the target stays strictly below the opposite
            # best — on a 1¢ spread with N=3, target=best+3¢ would
            # cross the ask and the no-cross guard would over-pull.
            n_ticks = max(1, cfg.penny_inside_distance)
            best_ask_t1c = ob.best_ask_t1c
            if best_ask_t1c < 1000 and best_ask_t1c > best_bid_t1c:
                max_inside_t1c = best_ask_t1c - tick
                target_t1c = min(best_bid_t1c + n_ticks * tick, max_inside_t1c)
            else:
                target_t1c = best_bid_t1c + n_ticks * tick
            mode = "active-penny"
        elif confidence >= cfg.match_best_min_confidence:
            # Mid-confidence: MATCH the best
            target_t1c = best_bid_t1c
            mode = "active-match"
        else:
            # Low-confidence: stay max_distance_from_best ticks behind best
            target_t1c = best_bid_t1c - cfg.max_distance_from_best * tick
            mode = "active-follow"

        # Anti-spoofing cap: never bid above (theo - 1¢ + tolerance¢) — in t1c
        cap_t1c = (fair - 1 + cfg.theo_tolerance_c) * 10
        bound_target_t1c = min(target_t1c, cap_t1c)

        # Tail-only cap: bid ≤ max_distance_from_extremes_c cents.
        # Operator-controlled (default 0 = disabled). Independent of
        # theo and orderbook — useful on freshly-launched, low-info
        # books where the middle is untrusted.
        if cfg.max_distance_from_extremes_c > 0:
            extremes_cap_t1c = cfg.max_distance_from_extremes_c * 10
            bound_target_t1c = min(bound_target_t1c, extremes_cap_t1c)

        # Clamp to valid range [1, 989] t1c (= 0.1¢ to 98.9¢)
        final_t1c = max(1, min(989, bound_target_t1c))
        # Snap to a quotable tick at the final price.
        final_tick = _tick_at(ob.tick_schedule, final_t1c)
        if final_tick > 1:
            final_t1c = (final_t1c // final_tick) * final_tick
        final_cents = max(1, min(99, (final_t1c + 5) // 10))  # display-rounded
        size = self._size_for_quote_t1c(final_t1c, "bid")

        return SideDecision(
            price=final_cents,
            price_t1c=final_t1c,
            size=size,
            skip=False,
            reason=(
                f"bid {mode}: best_t1c={best_bid_t1c}, target_t1c={target_t1c}, "
                f"capped@{cap_t1c} → {final_t1c}t1c ({final_t1c/10:.1f}¢) × {size}"
            ),
            extras={
                "mode": mode, "best_bid_t1c": best_bid_t1c,
                "fair": fair, "cap_t1c": cap_t1c, "tick": tick,
            },
        )

    def _compute_ask(
        self, fair: int, ob: OrderbookSnapshot, confidence: float = 0.0,
    ) -> SideDecision:
        cfg = self._cfg
        best_ask_t1c = ob.best_ask_t1c
        best_ask_c = best_ask_t1c // 10
        tick = _tick_at(ob.tick_schedule, min(989, best_ask_t1c))

        if best_ask_t1c >= 1000:
            target_t1c = (fair + cfg.max_half_spread_c) * 10
            mode = "no-best-ask"
        elif self._is_desert(100 - fair, 100 - best_ask_c):
            target_t1c = best_ask_t1c - tick
            mode = "desert-penny"
        elif fair <= 3:
            target_t1c = best_ask_t1c
            mode = "deep-otm-match"
        elif fair >= 97:
            target_t1c = best_ask_t1c
            mode = "deep-itm-match"
        elif confidence >= cfg.penny_inside_min_confidence:
            # Highest-confidence: N ticks INSIDE the best, clamped so
            # the target stays strictly above the opposite best (the
            # mirror of the bid-side narrow-spread guard).
            n_ticks = max(1, cfg.penny_inside_distance)
            best_bid_t1c = ob.best_bid_t1c
            if best_bid_t1c > 0 and best_bid_t1c < best_ask_t1c:
                min_inside_t1c = best_bid_t1c + tick
                target_t1c = max(best_ask_t1c - n_ticks * tick, min_inside_t1c)
            else:
                target_t1c = best_ask_t1c - n_ticks * tick
            mode = "active-penny"
        elif confidence >= cfg.match_best_min_confidence:
            target_t1c = best_ask_t1c
            mode = "active-match"
        else:
            target_t1c = best_ask_t1c + cfg.max_distance_from_best * tick
            mode = "active-follow"

        floor_t1c = (fair + 1 - cfg.theo_tolerance_c) * 10
        bound_target_t1c = max(target_t1c, floor_t1c)

        # Tail-only floor: ask ≥ (100 − max_distance_from_extremes_c) cents.
        # Mirror of the bid-side extremes cap.
        if cfg.max_distance_from_extremes_c > 0:
            extremes_floor_t1c = (100 - cfg.max_distance_from_extremes_c) * 10
            bound_target_t1c = max(bound_target_t1c, extremes_floor_t1c)

        final_t1c = max(1, min(989, bound_target_t1c))
        final_tick = _tick_at(ob.tick_schedule, final_t1c)
        if final_tick > 1:
            # Round UP to next tick on ask (don't sell cheaper than tick allows)
            rem = final_t1c % final_tick
            if rem != 0:
                final_t1c = final_t1c + (final_tick - rem)
        final_cents = max(1, min(99, (final_t1c + 5) // 10))
        size = self._size_for_quote_t1c(final_t1c, "ask")

        return SideDecision(
            price=final_cents,
            price_t1c=final_t1c,
            size=size,
            skip=False,
            reason=(
                f"ask {mode}: best_t1c={best_ask_t1c}, target_t1c={target_t1c}, "
                f"floored@{floor_t1c} → {final_t1c}t1c ({final_t1c/10:.1f}¢) × {size}"
            ),
            extras={
                "mode": mode, "best_ask_t1c": best_ask_t1c,
                "fair": fair, "floor_t1c": floor_t1c, "tick": tick,
            },
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
        # Cents shim so callers using the legacy entry point keep working.
        return self._size_for_quote_t1c(quote_cents * 10, side)

    def _size_for_quote_t1c(self, quote_t1c: int, side: str) -> int:
        """Compute order size from `dollars_per_side` and the quote
        price. All math in t1c so sub-cent prices size correctly.

        cost_t1c is "tenths-of-cent we lose if filled at this quote":
          - bid: equal to quote_t1c (we pay quote_t1c per contract)
          - ask: equal to (1000 - quote_t1c) (max loss = full Yes payout)
        Contracts = dollars_per_side × 1000 / cost_t1c (since 1000 t1c
        = $1).
        """
        cfg = self._cfg
        if cfg.dollars_per_side <= 0:
            return cfg.contracts_per_side
        if quote_t1c < 1 or quote_t1c > 989:
            return cfg.min_contracts
        if side == "bid":
            cost_t1c = quote_t1c
        elif side == "ask":
            cost_t1c = max(1, 1000 - quote_t1c)
        else:
            return cfg.min_contracts
        raw = int(cfg.dollars_per_side * 1000 / cost_t1c)
        return max(cfg.min_contracts, min(cfg.max_contracts, raw))
