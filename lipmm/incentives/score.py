"""Per-strike LIP score / projected-share computation.

Mirror of `feeds/kalshi/lip_score.py` (the deprecated soy bot's
scoring) but ported into lipmm/ so the dashboard can display it
without crossing the hermeticity boundary. Plain Python — this is
a render-time computation (8 strikes × 5+5 levels per cycle), not a
hot path. No numba.

Math (per Kalshi's LIP help center):

  Score(market, snapshot) = Σ_orders [ size × distance_multiplier(order) ]

  distance_multiplier(price, best_price, discount_factor)
      = max(0, 1 - |price - best_price| × discount_factor)

The PROGRAM's `discount_factor_bps` controls how steeply the
multiplier decays per tick. A 25% (=0.25) factor means each tick
of distance subtracts 0.25 from the multiplier, hitting 0 at 4
ticks. A 50% factor means 0.0 at 2 ticks. A 100% factor means
only the best price earns credit. Different programs ship
different factors — the dashboard reads the actual value from the
incentive program record rather than hardcoding it.

Fallback: when no discount factor is available (e.g. ticker has
no active LIP program), default to `decay_ticks=5` per soy-bot
convention. The score is then informational only since there's no
pool to earn from anyway.

A passive market-maker quoting 1 contract at the best bid earns
score = 1.0 × 1.0 = 1.0. Their share of the period's reward pool
is `our_score / total_score` averaged over the period — for the
dashboard we surface the instantaneous share, which is a good
enough proxy for "how am I doing right now".

Operator framing:
  - "mult" per resting order = the distance_multiplier value (0..1)
  - "share" per strike = our_score / total_score
  - "projected reward" = share × period_reward_dollars
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_DECAY_TICKS = 5
"""Fallback linear decay (cents) when no discount_factor is known —
matches the soy-bot's working default. Used for tickers with no
active LIP program (score is informational anyway)."""


def linear_multiplier(
    order_price_c: int,
    best_price_c: int,
    *,
    discount_factor: float | None = None,
    decay_ticks: int | None = None,
) -> float:
    """Multiplier per Kalshi's LIP scoring formula.

    Args:
      order_price_c:    our order's price in cents
      best_price_c:     the relevant best (bid for our bids, ask for asks)
      discount_factor:  PREFERRED — the program's discount factor in
                        [0, 1]. e.g. 0.25 means each tick of distance
                        subtracts 0.25 from the multiplier. When given,
                        formula = max(0, 1 - distance × discount_factor).
      decay_ticks:      Fallback — multiplier reaches 0 at this distance
                        in cents. Used only when discount_factor is None.

    Both are optional. With neither, decay_ticks defaults to
    DEFAULT_DECAY_TICKS (5). Explicit > implicit > default.
    """
    distance = abs(order_price_c - best_price_c)
    if distance == 0:
        return 1.0
    if discount_factor is not None:
        df = float(discount_factor)
        if df < 0:
            raise ValueError(f"discount_factor must be >= 0, got {df}")
        return max(0.0, 1.0 - distance * df)
    if decay_ticks is None:
        decay_ticks = DEFAULT_DECAY_TICKS
    if decay_ticks < 1:
        raise ValueError(f"decay_ticks must be >= 1, got {decay_ticks}")
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
    *,
    discount_factor: float | None,
    decay_ticks: int | None,
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
        out += sz * linear_multiplier(
            p, best_price_c,
            discount_factor=discount_factor,
            decay_ticks=decay_ticks,
        )
    return out


def compute_strike_score(
    *,
    our_orders: list[dict[str, Any]],
    yes_levels: list[dict[str, Any]],
    no_levels: list[dict[str, Any]],
    best_bid_c: int,
    best_ask_c: int,
    discount_factor: float | None = None,
    decay_ticks: int | None = None,
) -> StrikeScore:
    """Compute our score, total visible score, share, per-resting mults
    for one strike.

    Args:
      our_orders:      list of dicts with keys {order_id, side
                       ("bid"|"ask"), price_cents, size}.
      yes_levels:      Yes-side bids from the orderbook. Each dict has
                       price_cents + size.
      no_levels:       No-side bids from the orderbook (= Yes asks via
                       inversion: yes_ask_price = 100 - no_bid_price).
      best_bid_c:      Best Yes bid in cents.
      best_ask_c:      Best Yes ask in cents.
      discount_factor: Program's discount factor in [0, 1], from
                       Kalshi's `discount_factor_bps / 10000`.
                       PREFERRED — sets the per-tick decay rate.
      decay_ticks:     Fallback; used only when discount_factor is
                       None. Default 5 (soy-bot legacy).

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
        mult = linear_multiplier(
            p, ref,
            discount_factor=discount_factor,
            decay_ticks=decay_ticks,
        )
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
    yes_score = _score_levels(
        yes_levels, best_bid_c,
        discount_factor=discount_factor, decay_ticks=decay_ticks,
    )
    no_score = _score_levels(
        no_levels, no_best_bid,
        discount_factor=discount_factor, decay_ticks=decay_ticks,
    )
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
