"""Quote-decision logic for the trufaidp market maker.

Kalshi prices yes contracts in 1c ticks. The unified book has two
sides — yes (bids to buy yes) and no (bids to buy no). A yes-ask is
expressed as a no-bid at price `100 - ask`. The quoter provides
liquidity on BOTH sides by placing one yes-bid (Side.YES_BUY) and one
no-bid (Side.NO_BUY) per strike, each `improvement_cents` better than
the prevailing best on its respective side.

Liquidity-Incentive scoring (per Kalshi LIP): score = size *
distance_multiplier; best level on each side gets multiplier 1.0,
deeper levels decay. Stepping ahead by even 1c moves us to a fresh
best level (we are alone there → we capture 100% of that level's
size-weighted reward, while the previous best is pushed deeper and
its multiplier drops). Stepping ahead by 2c puts a tick of empty
space between us and the next quote — the user's preference: low AS
risk, full reward weight.

Adverse selection guardrails:
  * `min_edge_cents` from theo on both sides — never improve so far
    that we'd be inside theo.
  * Inventory skew lowers the bid + raises the no-bid (= lowers yes-
    ask) when we are net-long yes; symmetric when short. Aggressive
    on offload, per the user's "avoid fills, offload portfolio" rule.
  * Hard caps: per-strike abs(yes-equivalent position), aggregate abs
    yes-equivalent across all strikes.
"""

from __future__ import annotations

from dataclasses import dataclass

from trufaidp.kalshi import Side


@dataclass(frozen=True, slots=True)
class QuoterConfig:
    target_improvement_cents: int = 2  # quote this far ahead of next-best
    min_improvement_cents: int = 1     # fallback if target infeasible
    min_edge_cents: int = 1            # never closer than this to theo on either side
    full_size: int = 5                 # contracts when target improvement feasible
    half_size: int = 2                 # contracts when only min improvement feasible
    skew_divisor: int = 10             # 1c skew per N yes-equivalent contracts
    max_skew_cents: int = 5            # cap inventory skew at +/- this
    per_strike_position_limit: int = 50
    aggregate_position_limit: int = 300  # abs sum of yes-equivalent across strikes


@dataclass(frozen=True, slots=True)
class StrikeBook:
    ticker: str
    theo_cents: int           # round(theo_prob * 100), in [1, 99]
    best_yes_bid: int         # 0 if empty
    best_no_bid: int          # 0 if empty
    yes_position: int         # signed: + long yes, - short via no
                              # encode as net yes-equivalent contracts


@dataclass(frozen=True, slots=True)
class Quote:
    ticker: str
    side: Side
    price_cents: int
    qty: int


def _improvement(best: int, improvement: int) -> int:
    return best + improvement if best > 0 else max(1, improvement)


def _quote_for_side(
    *,
    is_yes: bool,
    best_same: int,
    best_opposite: int,
    fair_cents: int,
    skew_cents: int,
    cfg: QuoterConfig,
) -> tuple[int, int] | None:
    """Compute (price, qty) for one side. fair_cents is the side's fair
    (theo for yes-buy, 100-theo for no-buy). best_same is the best
    resting price on this side; best_opposite is the best on the other
    side (used to enforce non-crossing post-only).
    Inventory skew flips by side: subtract from yes-bid, add to no-bid
    when long yes.
    """
    side_skew = -skew_cents if is_yes else +skew_cents

    target_price = _improvement(best_same, cfg.target_improvement_cents) + side_skew
    min_price = _improvement(best_same, cfg.min_improvement_cents) + side_skew

    edge_ceiling = fair_cents - cfg.min_edge_cents
    cross_ceiling = (100 - best_opposite) - 1 if best_opposite > 0 else 99

    ceiling = min(edge_ceiling, cross_ceiling, 99)

    if target_price <= ceiling and target_price >= 1:
        return target_price, cfg.full_size
    if min_price <= ceiling and min_price >= 1:
        return min_price, cfg.half_size
    return None


def decide_quotes(
    book: StrikeBook,
    aggregate_abs_position: int,
    cfg: QuoterConfig = QuoterConfig(),
) -> list[Quote]:
    quotes: list[Quote] = []

    raw_skew = book.yes_position // cfg.skew_divisor
    skew_cents = max(-cfg.max_skew_cents, min(cfg.max_skew_cents, raw_skew))

    over_per_strike = abs(book.yes_position) >= cfg.per_strike_position_limit
    over_aggregate = aggregate_abs_position >= cfg.aggregate_position_limit

    # Yes-bid (buying yes increases yes_position).
    suppress_yes_buy = (
        book.yes_position >= cfg.per_strike_position_limit
        or (over_aggregate and book.yes_position >= 0)
    )
    if not suppress_yes_buy:
        result = _quote_for_side(
            is_yes=True,
            best_same=book.best_yes_bid,
            best_opposite=book.best_no_bid,
            fair_cents=book.theo_cents,
            skew_cents=skew_cents,
            cfg=cfg,
        )
        if result is not None:
            price, qty = result
            qty = min(qty, cfg.per_strike_position_limit - max(0, book.yes_position))
            if qty >= 1:
                quotes.append(Quote(book.ticker, Side.YES_BUY, price, qty))

    # No-bid (buying no decreases yes_position via offset).
    suppress_no_buy = (
        -book.yes_position >= cfg.per_strike_position_limit
        or (over_aggregate and book.yes_position <= 0)
    )
    if not suppress_no_buy:
        result = _quote_for_side(
            is_yes=False,
            best_same=book.best_no_bid,
            best_opposite=book.best_yes_bid,
            fair_cents=100 - book.theo_cents,
            skew_cents=skew_cents,
            cfg=cfg,
        )
        if result is not None:
            price, qty = result
            qty = min(qty, cfg.per_strike_position_limit - max(0, -book.yes_position))
            if qty >= 1:
                quotes.append(Quote(book.ticker, Side.NO_BUY, price, qty))

    if over_per_strike:
        # Allow only the side that reduces |position|.
        if book.yes_position > 0:
            quotes = [q for q in quotes if q.side is Side.NO_BUY]
        elif book.yes_position < 0:
            quotes = [q for q in quotes if q.side is Side.YES_BUY]

    return quotes
