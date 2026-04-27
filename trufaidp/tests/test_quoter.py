from __future__ import annotations

from trufaidp.kalshi import Side
from trufaidp.mm.quoter import QuoterConfig, StrikeBook, decide_quotes


def _book(theo=50, byb=40, bnb=40, pos=0, ticker="K") -> StrikeBook:
    return StrikeBook(ticker=ticker, theo_cents=theo, best_yes_bid=byb, best_no_bid=bnb, yes_position=pos)


def test_quotes_both_sides_with_target_improvement():
    quotes = decide_quotes(_book(theo=50, byb=40, bnb=40), aggregate_abs_position=0)
    by_side = {q.side: q for q in quotes}
    assert Side.YES_BUY in by_side and Side.NO_BUY in by_side
    assert by_side[Side.YES_BUY].price_cents == 42  # 40 + 2 (target improvement)
    assert by_side[Side.NO_BUY].price_cents == 42   # 40 + 2 (target improvement)
    assert by_side[Side.YES_BUY].qty == 5
    assert by_side[Side.NO_BUY].qty == 5


def test_falls_back_to_min_improvement_with_smaller_size():
    # theo=44, best_yes_bid=42 → target (44) clipped by edge_ceiling 43; min (43) ok with half size
    quotes = decide_quotes(_book(theo=44, byb=42, bnb=10), aggregate_abs_position=0)
    yes = next(q for q in quotes if q.side is Side.YES_BUY)
    assert yes.price_cents == 43
    assert yes.qty == 2  # half_size


def test_no_quote_when_no_edge():
    # theo=42, best_yes_bid=42 → even +1 (43) > theo-1 (41), no quote
    quotes = decide_quotes(_book(theo=42, byb=42, bnb=10), aggregate_abs_position=0)
    assert not any(q.side is Side.YES_BUY for q in quotes)


def test_inventory_skew_lowers_yes_bid_when_long():
    # net long 30 yes → skew = 30 // 10 = 3, capped at 5 → yes_bid lowers by 3
    quotes = decide_quotes(_book(theo=50, byb=40, bnb=40, pos=30), aggregate_abs_position=30)
    yes = next(q for q in quotes if q.side is Side.YES_BUY)
    no = next(q for q in quotes if q.side is Side.NO_BUY)
    assert yes.price_cents == 40 + 2 - 3  # 39
    assert no.price_cents == 40 + 2 + 3   # 45 — more aggressive on offload side


def test_per_strike_position_limit_blocks_adding_side():
    quotes = decide_quotes(_book(theo=50, byb=40, bnb=40, pos=50), aggregate_abs_position=50)
    assert not any(q.side is Side.YES_BUY for q in quotes)
    assert any(q.side is Side.NO_BUY for q in quotes)


def test_aggregate_cap_blocks_adding_to_same_direction():
    # Aggregate at 300, this strike net long → block YES_BUY (would add long), allow NO_BUY (offsets)
    quotes = decide_quotes(_book(theo=50, byb=40, bnb=40, pos=10), aggregate_abs_position=300)
    sides = {q.side for q in quotes}
    assert Side.YES_BUY not in sides
    assert Side.NO_BUY in sides


def test_post_only_non_crossing():
    # best_no_bid=58 → yes_ask=42; our target yes-bid would be 41+2=43, but ceiling = 42-1 = 41
    quotes = decide_quotes(_book(theo=50, byb=41, bnb=58), aggregate_abs_position=0)
    yes = next((q for q in quotes if q.side is Side.YES_BUY), None)
    if yes is not None:
        assert yes.price_cents <= 41


def test_clamps_to_one_cent_floor_with_empty_book():
    quotes = decide_quotes(_book(theo=50, byb=0, bnb=0), aggregate_abs_position=0)
    for q in quotes:
        assert 1 <= q.price_cents <= 99
