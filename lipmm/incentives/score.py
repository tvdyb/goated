"""Per-strike LIP score / projected-payout computation.

Faithful port of Kalshi's August 2025 Liquidity Incentive Program
self-certification (Appendix A) — see `rules09082530054.pdf`. The
authoritative formula:

    Score(bid) = Discount Factor ^ (Reference Price − Price(bid)) × Size

So with DF=0.25 (the soy/PMI default):
    distance 0 → 1.00
    distance 1 → 0.25
    distance 2 → 0.0625
    distance 3 → 0.015625

Per-snapshot procedure, repeated each second of every Time Period:

  1. Find the **Reference Yes Price** = the highest yes bid, IF it
     exists AND is strictly less than the highest possible price (99¢
     on a binary market). Otherwise the Yes side has no qualifying
     bids that snapshot.
  2. Walk down levels accumulating size; include every bid at each
     level until cumulative size ≥ **Target Size**. If we exhaust
     levels without reaching the target, the Yes side has no
     qualifying bids that snapshot.
  3. For each Qualifying Yes Bid, Score = DF^(RefPrice − price) × size.
     Normalized score = score / Σ scores on this side. The Σ over a
     side equals 1.0 by definition.
  4. Repeat for the No side (a Yes ask at price p ↔ a No bid at 100−p;
     `no_levels` already comes in No-side cents, so the math is
     symmetric).
  5. Snapshot LP Score (user) = Σ normalized yes-side + Σ normalized
     no-side. Range [0, 2].
  6. Σ all users' Snapshot LP Scores ≈ (1 if yes side has any
     qualifying bids) + (1 if no side has any qualifying bids).
  7. Time Period LP Score (user) ≈ user_snapshot / total_snapshot
     (instantaneous estimate; the rules average across all snapshots
     in the period — we use the current snapshot as the rate).
  8. Payout (user) ≈ Time Period Score × Time Period Reward.

This module renders dashboard-side, not in the hot path — plain
Python, no numba.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MAX_PRICE_CENTS = 99
"""Highest possible bid price on a Kalshi binary market. The rules
gate qualifying bids on `Reference Price < highest possible price`,
i.e. a 99¢ best bid disqualifies the side from earning that
snapshot."""


# ── Per-resting / per-strike result types ───────────────────────────


@dataclass(frozen=True)
class RestingMultiplier:
    """One resting order's contribution to our LIP score.

    `qualified` = True iff this order's price is at or above the
    side's qualifying-threshold price (i.e. it falls inside the
    walk-down qualifying set). Disqualified orders earn nothing
    that snapshot regardless of multiplier value.
    """
    order_id: str
    side: str               # "bid" (Yes side) or "ask" (No side, via inversion)
    price_c: int
    size: float
    multiplier: float       # DF^distance, 0..1
    score_contribution: float  # multiplier × size, only if qualified
    qualified: bool


@dataclass(frozen=True)
class StrikeScore:
    """Per-strike LIP score snapshot."""
    # Per-side scores (raw, pre-normalization, qualifying bids only)
    our_yes_score: float
    yes_total_score: float
    our_no_score: float
    no_total_score: float

    # Per-side normalized (each in [0, 1]; sum to 1 across all users
    # on that side when the side has any qualifying bids)
    our_yes_normalized: float
    our_no_normalized: float

    # Whether each side had qualifying bids this snapshot
    yes_qualifying: bool
    no_qualifying: bool

    # Reference prices that snapshot (None if side had no qualifying bids)
    yes_ref_price_c: int | None
    no_ref_price_c: int | None

    # Composite (Snapshot LP Score, in [0, 2])
    snapshot_score: float

    # Pool share = snapshot_score / sides_with_qualifying ∈ [0, 1]
    # This is our instantaneous fraction of the Time Period Reward.
    pool_share: float

    # Per-resting-order contributions for the dashboard mults table
    multipliers: list[RestingMultiplier] = field(default_factory=list)

    @property
    def share_pct(self) -> float:
        return self.pool_share * 100.0

    # Backwards-compat with the old StrikeScore API ──────────────────
    # Some callers still read `our_score`, `total_score`, `share` —
    # keep those resolving to sensible analogues so the migration is
    # surgical. (Renderer + template will move to the precise fields.)

    @property
    def our_score(self) -> float:
        return self.our_yes_score + self.our_no_score

    @property
    def total_score(self) -> float:
        return self.yes_total_score + self.no_total_score

    @property
    def share(self) -> float:
        return self.pool_share

    def projected_reward_dollars(self, period_reward_dollars: float) -> float:
        """Full-period payout estimate. Holds our_share constant for the
        remainder of the period (which it isn't, but it's the natural
        "rate × period" headline number)."""
        return self.pool_share * float(period_reward_dollars or 0)

    def hourly_reward_dollars(
        self, period_reward_dollars: float, period_duration_s: float,
    ) -> float:
        """Earnings rate per hour at the current pool share."""
        if not period_duration_s or period_duration_s <= 0:
            return 0.0
        return (
            self.pool_share * float(period_reward_dollars or 0)
            * 3600.0 / float(period_duration_s)
        )

    def daily_reward_dollars(
        self, period_reward_dollars: float, period_duration_s: float,
    ) -> float:
        """Earnings rate per 24h at the current pool share."""
        if not period_duration_s or period_duration_s <= 0:
            return 0.0
        return (
            self.pool_share * float(period_reward_dollars or 0)
            * 86400.0 / float(period_duration_s)
        )


# ── Internal helpers ────────────────────────────────────────────────


def _coerce_levels(levels: list[Any]) -> list[tuple[int, float]]:
    """Coerce wire `[{price_cents, size}, ...]` or `[(price, size), ...]`
    into a list of (price_c, size) tuples, dropping malformed entries
    and zero/negative sizes. Sorted descending by price."""
    out: list[tuple[int, float]] = []
    for lvl in levels or []:
        try:
            if isinstance(lvl, dict):
                p = int(lvl["price_cents"])
                sz = float(lvl["size"])
            else:
                p, sz = int(lvl[0]), float(lvl[1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if sz <= 0:
            continue
        out.append((p, sz))
    out.sort(key=lambda x: -x[0])
    # Coalesce same-price entries (defensive — Kalshi already pre-aggregates)
    merged: list[tuple[int, float]] = []
    for p, sz in out:
        if merged and merged[-1][0] == p:
            merged[-1] = (p, merged[-1][1] + sz)
        else:
            merged.append((p, sz))
    return merged


def _qualifying_walkdown(
    levels_desc: list[tuple[int, float]],
    target_size: float,
    *,
    max_price: int = MAX_PRICE_CENTS,
) -> tuple[int, int] | None:
    """Walk down `levels_desc` (sorted highest-price-first) accumulating
    size until cumulative ≥ `target_size`. Returns (reference_price,
    threshold_price) — both in cents — where threshold_price is the
    lowest price in the qualifying set. Returns None if:

      - levels is empty
      - the highest price is NOT strictly less than max_price (99)
      - cumulative size never reaches target_size

    Per Appendix A: bids strictly below the threshold price do NOT
    qualify, even though they sit on the book."""
    if not levels_desc:
        return None
    ref_price = levels_desc[0][0]
    if ref_price >= max_price:
        return None
    cumulative = 0.0
    threshold = ref_price
    for p, sz in levels_desc:
        cumulative += sz
        threshold = p
        if cumulative >= target_size:
            return ref_price, threshold
    # Exhausted without reaching target → no qualifying bids
    return None


def _side_score_total(
    levels_desc: list[tuple[int, float]],
    ref_price: int,
    threshold: int,
    discount_factor: float,
) -> float:
    """Σ over qualifying bids of DF^(ref - price) × size. Bids below
    `threshold` are excluded."""
    total = 0.0
    for p, sz in levels_desc:
        if p < threshold:
            break  # levels are sorted descending; rest are below threshold
        distance = ref_price - p
        total += (discount_factor ** distance) * sz
    return total


# ── Public API ──────────────────────────────────────────────────────


def compute_strike_score(
    *,
    our_orders: list[dict[str, Any]],
    yes_levels: list[Any],
    no_levels: list[Any],
    best_bid_c: int,
    best_ask_c: int,
    discount_factor: float | None = None,
    target_size_contracts: float | None = None,
) -> StrikeScore:
    """Compute the snapshot LIP score for one strike per Appendix A.

    Args:
      our_orders:            our resting orders as dicts with
                             {order_id, side ("bid"|"ask"), price_cents,
                             size}.
      yes_levels:            Yes-side bids from the orderbook
                             (`price_cents`, `size`), highest-first or
                             arbitrary order — we re-sort.
      no_levels:             No-side bids from the orderbook (already in
                             No-cents = 100 − Yes ask).
      best_bid_c:            Best Yes bid in cents (used for the "ours"
                             distance accounting; redundant with
                             yes_levels[0] when yes_levels is the full
                             top-of-book).
      best_ask_c:            Best Yes ask in cents.
      discount_factor:       Program's DF in [0, 1] (e.g. 0.25). Required
                             for a meaningful score; pass None to get
                             a zero StrikeScore (no LIP program active).
      target_size_contracts: Program's Target Size in contracts.
                             Required; without it we can't run the
                             walk-down. Pass None for zero StrikeScore.

    The returned `StrikeScore` exposes per-side raw + normalized scores,
    ref/threshold prices, the snapshot composite, and a `pool_share`
    estimate suitable for projected-payout displays.
    """
    # Degenerate: no program → no scoring.
    zero = StrikeScore(
        our_yes_score=0.0, yes_total_score=0.0,
        our_no_score=0.0, no_total_score=0.0,
        our_yes_normalized=0.0, our_no_normalized=0.0,
        yes_qualifying=False, no_qualifying=False,
        yes_ref_price_c=None, no_ref_price_c=None,
        snapshot_score=0.0, pool_share=0.0,
        multipliers=[],
    )
    if discount_factor is None or target_size_contracts is None:
        return zero
    df = float(discount_factor)
    if df < 0 or df > 1:
        return zero
    target = float(target_size_contracts)
    if target <= 0:
        return zero

    yes = _coerce_levels(yes_levels)
    no = _coerce_levels(no_levels)

    yes_walk = _qualifying_walkdown(yes, target)
    no_walk = _qualifying_walkdown(no, target)

    yes_ref, yes_thresh = yes_walk if yes_walk else (None, None)
    no_ref, no_thresh = no_walk if no_walk else (None, None)

    yes_total = (
        _side_score_total(yes, yes_ref, yes_thresh, df)
        if yes_walk else 0.0
    )
    no_total = (
        _side_score_total(no, no_ref, no_thresh, df)
        if no_walk else 0.0
    )

    # Now score each of our orders.
    our_yes_score = 0.0
    our_no_score = 0.0
    mults: list[RestingMultiplier] = []
    for o in our_orders or []:
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
            # Yes-bid at price p. Reference is yes_ref. Qualifies iff
            # the Yes side has qualifying bids AND p ≥ yes_thresh.
            if yes_walk and p >= yes_thresh:
                distance = yes_ref - p
                mult = df ** distance if distance >= 0 else 0.0
                contrib = mult * sz
                our_yes_score += contrib
                qualified = True
            else:
                # Compute mult informationally (relative to best yes bid)
                # so the operator sees how far off they are; contribution = 0
                ref_for_display = yes_ref if yes_ref is not None else best_bid_c
                distance = max(0, ref_for_display - p)
                mult = df ** distance
                contrib = 0.0
                qualified = False
            mults.append(RestingMultiplier(
                order_id=order_id, side=side, price_c=p, size=sz,
                multiplier=mult, score_contribution=contrib,
                qualified=qualified,
            ))
        elif side == "ask":
            # Yes-ask at price p ⇔ No-bid at price (100 - p).
            no_price = MAX_PRICE_CENTS + 1 - p  # i.e. 100 - p (since prices are 1..99)
            # The "max possible price" symmetry: a yes-ask at 1¢ = no-bid at 99¢.
            # Use 100 - p directly, NOT MAX_PRICE_CENTS+1-p, to keep math clean.
            no_price = 100 - p
            if no_walk and no_price >= no_thresh:
                distance = no_ref - no_price
                mult = df ** distance if distance >= 0 else 0.0
                contrib = mult * sz
                our_no_score += contrib
                qualified = True
            else:
                ref_for_display = (
                    no_ref if no_ref is not None
                    else max(0, 100 - best_ask_c)
                )
                distance = max(0, ref_for_display - no_price)
                mult = df ** distance
                contrib = 0.0
                qualified = False
            mults.append(RestingMultiplier(
                order_id=order_id, side=side, price_c=p, size=sz,
                multiplier=mult, score_contribution=contrib,
                qualified=qualified,
            ))
        # other side strings are ignored

    # Per-side normalization (each side's normalized total = 1.0 across
    # all users; ours is our share of that side).
    our_yes_norm = our_yes_score / yes_total if yes_total > 0 else 0.0
    our_no_norm = our_no_score / no_total if no_total > 0 else 0.0
    # Cap defensively (numerical guards).
    our_yes_norm = min(1.0, max(0.0, our_yes_norm))
    our_no_norm = min(1.0, max(0.0, our_no_norm))

    snapshot_score = our_yes_norm + our_no_norm
    sides_active = (1 if yes_walk else 0) + (1 if no_walk else 0)
    pool_share = snapshot_score / sides_active if sides_active > 0 else 0.0

    return StrikeScore(
        our_yes_score=our_yes_score,
        yes_total_score=yes_total,
        our_no_score=our_no_score,
        no_total_score=no_total,
        our_yes_normalized=our_yes_norm,
        our_no_normalized=our_no_norm,
        yes_qualifying=bool(yes_walk),
        no_qualifying=bool(no_walk),
        yes_ref_price_c=yes_ref,
        no_ref_price_c=no_ref,
        snapshot_score=snapshot_score,
        pool_share=pool_share,
        multipliers=mults,
    )
