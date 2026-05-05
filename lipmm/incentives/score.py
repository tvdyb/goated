"""Per-strike LIP score / projected-share computation.

Mirror of `feeds/kalshi/lip_score.py` (the deprecated soy bot's
scoring) but ported into lipmm/ so the dashboard can display it
without crossing the hermeticity boundary. Plain Python — this is
a render-time computation (8 strikes × 5+5 levels per cycle), not a
hot path. No numba.

Math (Kalshi's published LIP scoring formula):

  Score(market, snapshot) = Σ_orders [ size × distance_multiplier(order) ]

  distance_multiplier(price, best_price) = max(0, 1 - |price - best| / decay_ticks)

A passive market-maker quoting 1 contract at the best bid earns
score = 1.0 × 1.0 = 1.0. Quoting at best - 5c earns 0. Their share
of the period's reward pool is `our_score / total_score` averaged
over the period — for the dashboard we surface the instantaneous
share, which is a good enough proxy for "how am I doing right now".

Operator framing:
  - "mult" per resting order = the distance_multiplier value (0..1)
  - "share" per strike = our_score / total_score
  - "projected reward" = share × period_reward_dollars
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_DECAY_TICKS = 5
"""Linear decay over 5 cents — Kalshi's published default."""


def linear_multiplier(
    order_price_c: int,
    best_price_c: int,
    decay_ticks: int = DEFAULT_DECAY_TICKS,
) -> float:
    """Multiplier for a single order. 1.0 at best_price, decays
    linearly to 0 over `decay_ticks`. Beyond decay → 0."""
    if decay_ticks < 1:
        raise ValueError(f"decay_ticks must be >= 1, got {decay_ticks}")
    distance = abs(order_price_c - best_price_c)
    if distance == 0:
        return 1.0
    if distance >= decay_ticks:
        return 0.0
    return 1.0 - distance / float(decay_ticks)


@dataclass(frozen=True)
class RestingMultiplier:
    """One resting order's contribution to our LIP score."""
    order_id: str
    side: str               # "bid" or "ask" (in Yes-side terms)
    price_c: int
    size: float
    multiplier: float       # 0..1
    score_contribution: float


@dataclass(frozen=True)
class StrikeScore:
    """Per-strike LIP score snapshot."""
    our_score: float
    total_score: float
    share: float            # 0..1; 0 if total_score == 0
    multipliers: list[RestingMultiplier] = field(default_factory=list)

    @property
    def share_pct(self) -> float:
        return self.share * 100.0

    def projected_reward_dollars(self, period_reward_dollars: float) -> float:
        """Approximate: instantaneous share × pool size. Real LIP
        rewards average score share over the program period; this is
        the best-current-rate estimate."""
        return self.share * float(period_reward_dollars or 0)


# ── Compute ─────────────────────────────────────────────────────────


def _score_levels(
    levels: list[dict[str, Any]],
    best_price_c: int,
    decay_ticks: int,
) -> float:
    """Total score across an orderbook side. `levels` items have
    `price_cents` and `size` keys (matching the broadcaster's wire
    shape)."""
    out = 0.0
    for lvl in levels:
        try:
            p = int(lvl["price_cents"])
            sz = float(lvl["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if sz <= 0:
            continue
        out += sz * linear_multiplier(p, best_price_c, decay_ticks)
    return out


def compute_strike_score(
    *,
    our_orders: list[dict[str, Any]],
    yes_levels: list[dict[str, Any]],
    no_levels: list[dict[str, Any]],
    best_bid_c: int,
    best_ask_c: int,
    decay_ticks: int = DEFAULT_DECAY_TICKS,
) -> StrikeScore:
    """Compute our score, total visible score, share, per-resting mults
    for one strike.

    Args:
      our_orders:  list of dicts with keys {order_id, side ("bid"|"ask"),
                   price_cents, size}. Yes-side terms — bid means buying
                   Yes, ask means selling Yes (which is buying No).
      yes_levels:  Yes-side bids from the orderbook. Each dict has
                   price_cents + size.
      no_levels:   No-side bids from the orderbook (= Yes asks via
                   inversion: yes_ask_price = 100 - no_bid_price).
      best_bid_c:  Best Yes bid in cents (computed by the runner,
                   excluding our own orders).
      best_ask_c:  Best Yes ask in cents.
      decay_ticks: Multiplier decay (default 5).

    Returns: StrikeScore with our + total + share + multipliers.
    """
    # Our score per side
    our_score = 0.0
    mults: list[RestingMultiplier] = []
    for o in our_orders:
        try:
            order_id = str(o["order_id"])
            side = str(o["side"])
            p = int(o["price_cents"])
            sz = float(o["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if sz <= 0:
            continue
        if side == "bid":
            # Bid is on Yes side; reference is best Yes bid.
            ref = best_bid_c
        elif side == "ask":
            # Ask is on Yes side at price p, equivalently a No bid at
            # (100 - p). The reference best is best Yes ask.
            ref = best_ask_c
        else:
            continue
        mult = linear_multiplier(p, ref, decay_ticks)
        contrib = sz * mult
        our_score += contrib
        mults.append(RestingMultiplier(
            order_id=order_id, side=side, price_c=p,
            size=sz, multiplier=mult, score_contribution=contrib,
        ))

    # Total score = sum across both sides of the visible orderbook.
    # Score the Yes-side bids against best_bid_c, and No-side bids
    # against the No-side best (= 100 - best_ask_c).
    no_best_bid = max(0, 100 - best_ask_c)
    yes_score = _score_levels(yes_levels, best_bid_c, decay_ticks)
    no_score = _score_levels(no_levels, no_best_bid, decay_ticks)
    total_score = yes_score + no_score

    if total_score > 0:
        share = our_score / total_score
        # Cap at 1.0 in case our orders drove total but our_score >
        # total_score numerically due to dedup edge cases.
        share = min(1.0, share)
    else:
        share = 0.0

    return StrikeScore(
        our_score=our_score,
        total_score=total_score,
        share=share,
        multipliers=mults,
    )
