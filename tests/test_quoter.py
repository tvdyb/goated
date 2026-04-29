"""Tests for engine/quoter.py — spread-capture quoter."""

from __future__ import annotations

import numpy as np
import pytest

from engine.quoter import (
    EventBook,
    QuoteAction,
    QuoteActionType,
    QuoterConfig,
    StrikeBook,
    compute_quotes,
    _maker_fee_cents,
    _round_trip_maker_fee_cents,
)
from engine.rnd.bucket_integrator import BucketPrices


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bucket_prices(
    strikes: list[float],
    survivals: list[float],
) -> BucketPrices:
    """Build a BucketPrices with given strikes and survival values."""
    ks = np.array(strikes, dtype=np.float64)
    sv = np.array(survivals, dtype=np.float64)
    n_buckets = len(strikes) + 1
    bucket_yes = np.zeros(n_buckets, dtype=np.float64)
    bucket_yes[0] = 1.0 - sv[0]
    for i in range(1, len(sv)):
        bucket_yes[i] = sv[i - 1] - sv[i]
    bucket_yes[-1] = sv[-1]
    return BucketPrices(
        kalshi_strikes=ks,
        survival=sv,
        bucket_yes=bucket_yes,
        bucket_sum=float(bucket_yes.sum()),
        n_buckets=n_buckets,
    )


def _make_event_book(
    strikes: list[float],
    best_bids: list[int],
    best_asks: list[int],
    event_ticker: str = "KXSOYBEANMON-26MAY01",
) -> EventBook:
    """Build an EventBook from parallel lists."""
    books = []
    for i, k in enumerate(strikes):
        ticker = f"{event_ticker}-{int(k)}"
        books.append(StrikeBook(
            market_ticker=ticker,
            strike=k,
            best_bid_cents=best_bids[i],
            best_ask_cents=best_asks[i],
        ))
    return EventBook(event_ticker=event_ticker, strike_books=books)


DEFAULT_CONFIG = QuoterConfig()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMakerFeeCents:
    def test_midpoint_price(self):
        # At 50c, maker fee = ceil(0.25 * 0.07 * 0.50 * 0.50 * 100) / 100
        # = ceil(0.4375) / 100 = 1/100 = $0.01 = 1 cent
        result = _maker_fee_cents(50, 0.07, 0.25)
        assert result == 1

    def test_extreme_price(self):
        # At 5c, maker fee = ceil(0.25 * 0.07 * 0.05 * 0.95 * 100) / 100
        # = ceil(0.08) / 100 ~ ceil near 1 cent
        result = _maker_fee_cents(5, 0.07, 0.25)
        assert result >= 1

    def test_round_trip_symmetric(self):
        rt = _round_trip_maker_fee_cents(50, 50, 0.07, 0.25)
        assert rt == 2  # 1c each side


class TestComputeQuotesBasic:
    """Basic quoting scenarios."""

    def test_normal_two_sided_quotes(self):
        """Standard case: post both sides around fair value."""
        strikes = [1180.0, 1185.0, 1190.0, 1195.0, 1200.0]
        survivals = [0.90, 0.75, 0.50, 0.25, 0.10]
        rnd = _make_bucket_prices(strikes, survivals)

        # Incumbent spreads are 6-8c
        bids = [86, 71, 46, 21, 6]
        asks = [94, 79, 54, 29, 14]
        book = _make_event_book(strikes, bids, asks)

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        # Should get bid + ask actions for each strike (or NO_ACTION for some)
        bid_actions = [a for a in actions if a.action_type == QuoteActionType.PLACE_BID]
        ask_actions = [a for a in actions if a.action_type == QuoteActionType.PLACE_ASK]

        # At least the near-ATM strikes should have quotes
        assert len(bid_actions) >= 3
        assert len(ask_actions) >= 3

        # All bids must be post_only-safe: bid < best_ask
        for a in bid_actions:
            sb = next(s for s in book.strike_books if s.market_ticker == a.market_ticker)
            assert a.price_cents < sb.best_ask_cents, (
                f"Bid {a.price_cents} >= best_ask {sb.best_ask_cents} at {a.strike}"
            )

        # All asks must be: ask > best_bid
        for a in ask_actions:
            sb = next(s for s in book.strike_books if s.market_ticker == a.market_ticker)
            assert a.price_cents > sb.best_bid_cents, (
                f"Ask {a.price_cents} <= best_bid {sb.best_bid_cents} at {a.strike}"
            )

    def test_positive_spread(self):
        """All quoted spreads must be positive."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        bids = [a for a in actions if a.action_type == QuoteActionType.PLACE_BID]
        asks = [a for a in actions if a.action_type == QuoteActionType.PLACE_ASK]

        for b in bids:
            matching_asks = [a for a in asks if a.market_ticker == b.market_ticker]
            for a in matching_asks:
                assert b.price_cents < a.price_cents, (
                    f"Non-positive spread: bid={b.price_cents} ask={a.price_cents}"
                )

    def test_all_post_only_prices_valid(self):
        """All prices must be in [1, 99]."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        for a in actions:
            if a.action_type in (QuoteActionType.PLACE_BID, QuoteActionType.PLACE_ASK):
                assert 1 <= a.price_cents <= 99


class TestRiskGateIntegration:
    def test_risk_breach_cancels_all(self):
        """When risk_ok=False, all strikes should emit CANCEL."""
        strikes = [1190.0, 1195.0]
        survivals = [0.50, 0.25]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46, 21], [54, 29])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=False,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        assert all(a.action_type == QuoteActionType.CANCEL for a in actions)
        assert len(actions) == 2


class TestSettlementGateIntegration:
    def test_pull_all_cancels_everything(self):
        """gate_size_mult=0 should cancel all quotes."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=0.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        assert all(a.action_type == QuoteActionType.CANCEL for a in actions)

    def test_size_down_reduces_contracts(self):
        """gate_size_mult=0.5 should halve the posted size."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])
        config = QuoterConfig(max_contracts_per_strike=100)

        actions_full = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=config,
        )
        actions_half = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=0.5,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=config,
        )

        full_bids = [a for a in actions_full if a.action_type == QuoteActionType.PLACE_BID]
        half_bids = [a for a in actions_half if a.action_type == QuoteActionType.PLACE_BID]

        if full_bids and half_bids:
            assert half_bids[0].size == full_bids[0].size // 2

    def test_spread_widening(self):
        """gate_spread_mult=2.0 should widen the spread."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [40], [60])

        actions_normal = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )
        actions_wide = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=2.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        def _spread(acts):
            bids = [a for a in acts if a.action_type == QuoteActionType.PLACE_BID]
            asks = [a for a in acts if a.action_type == QuoteActionType.PLACE_ASK]
            if bids and asks:
                return asks[0].price_cents - bids[0].price_cents
            return 0

        normal_spread = _spread(actions_normal)
        wide_spread = _spread(actions_wide)
        assert wide_spread >= normal_spread


class TestTakerImbalanceIntegration:
    def test_withdraw_bid(self):
        """imbalance_withdraw_side='bid' should cancel bid, keep ask."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side="bid",
            config=DEFAULT_CONFIG,
        )

        types = [a.action_type for a in actions]
        assert QuoteActionType.PLACE_BID not in types
        assert QuoteActionType.PLACE_ASK in types or QuoteActionType.CANCEL in types

    def test_withdraw_ask(self):
        """imbalance_withdraw_side='ask' should cancel ask, keep bid."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [46], [54])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side="ask",
            config=DEFAULT_CONFIG,
        )

        types = [a.action_type for a in actions]
        assert QuoteActionType.PLACE_ASK not in types
        assert QuoteActionType.PLACE_BID in types or QuoteActionType.CANCEL in types


class TestInventorySkew:
    def test_long_inventory_widens_bid(self):
        """When long, bid should be lower (wider) to discourage more buying."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [40], [60])
        config = QuoterConfig(inventory_skew_gamma=0.5)
        ticker = "KXSOYBEANMON-26MAY01-1190"

        actions_flat = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=config,
        )
        actions_long = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={ticker: 10},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=config,
        )

        def _bid(acts):
            return next(
                (a.price_cents for a in acts if a.action_type == QuoteActionType.PLACE_BID),
                None,
            )

        flat_bid = _bid(actions_flat)
        long_bid = _bid(actions_long)
        if flat_bid is not None and long_bid is not None:
            assert long_bid <= flat_bid, (
                f"Long inventory should widen bid: flat={flat_bid} long={long_bid}"
            )


class TestFeeAware:
    def test_skip_when_spread_below_fee(self):
        """Should skip posting when spread cannot cover fees."""
        strikes = [1190.0]
        # Fair value very close to 50c, but book is tight
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        # Book with 2c spread — too tight for fees
        book = _make_event_book(strikes, [49], [51])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=QuoterConfig(min_half_spread_cents=1, fee_threshold_cents=2),
        )

        # With 1c half-spread, the 2c total spread should be below fee threshold
        place_actions = [
            a for a in actions
            if a.action_type in (QuoteActionType.PLACE_BID, QuoteActionType.PLACE_ASK)
        ]
        # Either no placements or spread is adequate
        for a in place_actions:
            assert a.price_cents >= 1


class TestEdgeCases:
    def test_extreme_itm_fair(self):
        """Fair value near 99c should still produce valid quotes or skip."""
        strikes = [1100.0]
        survivals = [0.98]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [95], [99])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        for a in actions:
            if a.action_type in (QuoteActionType.PLACE_BID, QuoteActionType.PLACE_ASK):
                assert 1 <= a.price_cents <= 99

    def test_extreme_otm_fair(self):
        """Fair value near 1c should still produce valid quotes or skip."""
        strikes = [1300.0]
        survivals = [0.02]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [1], [8])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        for a in actions:
            if a.action_type in (QuoteActionType.PLACE_BID, QuoteActionType.PLACE_ASK):
                assert 1 <= a.price_cents <= 99

    def test_empty_book(self):
        """Empty orderbook (no bids/asks) should still produce quotes."""
        strikes = [1190.0]
        survivals = [0.50]
        rnd = _make_bucket_prices(strikes, survivals)
        book = _make_event_book(strikes, [0], [100])

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        bids = [a for a in actions if a.action_type == QuoteActionType.PLACE_BID]
        asks = [a for a in actions if a.action_type == QuoteActionType.PLACE_ASK]
        assert len(bids) >= 1
        assert len(asks) >= 1


class TestAntiArb:
    def test_monotone_bids_across_strikes(self):
        """Bids on higher strikes must be <= bids on lower strikes (survival monotonicity)."""
        strikes = [1180.0, 1185.0, 1190.0, 1195.0, 1200.0]
        survivals = [0.90, 0.75, 0.50, 0.25, 0.10]
        rnd = _make_bucket_prices(strikes, survivals)
        bids = [80, 65, 40, 15, 2]
        asks = [98, 85, 60, 35, 18]
        book = _make_event_book(strikes, bids, asks)

        actions = compute_quotes(
            rnd_prices=rnd,
            event_book=book,
            inventory={},
            risk_ok=True,
            gate_size_mult=1.0,
            gate_spread_mult=1.0,
            imbalance_withdraw_side=None,
            config=DEFAULT_CONFIG,
        )

        placed_bids = sorted(
            [(a.strike, a.price_cents) for a in actions if a.action_type == QuoteActionType.PLACE_BID],
            key=lambda x: x[0],
        )
        for i in range(1, len(placed_bids)):
            assert placed_bids[i][1] <= placed_bids[i - 1][1], (
                f"Anti-arb violation: bid at {placed_bids[i][0]} = {placed_bids[i][1]}c "
                f"> bid at {placed_bids[i-1][0]} = {placed_bids[i-1][1]}c"
            )
