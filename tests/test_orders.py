"""Tests for feeds.kalshi.orders — order builder, tick rounding, quote-band.

Covers: GAP-080 (quote-band), GAP-081 (tick rounding), GAP-082 (order types),
GAP-122 (buy_max_cost).
"""

from __future__ import annotations

import pytest

from feeds.kalshi.orders import (
    MIN_PRICE_CENTS,
    MAX_PRICE_CENTS,
    Action,
    OrderSpec,
    OrderType,
    SelfTradePreventionType,
    Side,
    TimeInForce,
    build_limit_order,
    build_two_sided_quote,
    round_to_tick,
    validate_price_cents,
)

TICKER = "KXSOYBEANW-26APR24-17"


# ── Tick rounding ────────────────────────────────────────────────────


class TestRoundToTick:
    """Tick rounding with $0.01 and $0.02 tick sizes."""

    def test_exact_tick_no_change(self) -> None:
        assert round_to_tick(50) == 50

    def test_edge_min(self) -> None:
        assert round_to_tick(1) == 1

    def test_edge_max(self) -> None:
        assert round_to_tick(99) == 99

    def test_two_cent_tick_round_up(self) -> None:
        # 51 is not on a 2-cent tick: nearest are 50 and 52; 51 rounds up to 52
        assert round_to_tick(51, tick_size_cents=2) == 52

    def test_two_cent_tick_exact(self) -> None:
        assert round_to_tick(50, tick_size_cents=2) == 50

    def test_two_cent_tick_round_down(self) -> None:
        # 52 is on tick; 53 rounds to 54 (remainder 1, half of 2 -> round up)
        assert round_to_tick(52, tick_size_cents=2) == 52

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="outside quote-band"):
            round_to_tick(0)

    def test_rejects_100(self) -> None:
        with pytest.raises(ValueError, match="outside quote-band"):
            round_to_tick(100)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="outside quote-band"):
            round_to_tick(-5)

    def test_rejects_above_99(self) -> None:
        with pytest.raises(ValueError, match="outside quote-band"):
            round_to_tick(150)

    def test_rejects_non_int(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            round_to_tick(50.5)  # type: ignore[arg-type]

    def test_rejects_zero_tick_size(self) -> None:
        with pytest.raises(ValueError, match="tick_size_cents must be >= 1"):
            round_to_tick(50, tick_size_cents=0)


# ── Quote-band validation ────────────────────────────────────────────


class TestValidatePriceCents:
    """Validate prices against the [$0.01, $0.99] quote-band."""

    def test_valid_min(self) -> None:
        validate_price_cents(1)  # should not raise

    def test_valid_max(self) -> None:
        validate_price_cents(99)  # should not raise

    def test_valid_mid(self) -> None:
        validate_price_cents(50)  # should not raise

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="below minimum"):
            validate_price_cents(0)

    def test_rejects_100(self) -> None:
        with pytest.raises(ValueError, match="above maximum"):
            validate_price_cents(100)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="below minimum"):
            validate_price_cents(-1)

    def test_rejects_101(self) -> None:
        with pytest.raises(ValueError, match="above maximum"):
            validate_price_cents(101)

    def test_rejects_non_int(self) -> None:
        with pytest.raises(TypeError, match="must be int"):
            validate_price_cents(50.0)  # type: ignore[arg-type]

    def test_two_cent_tick_on_tick(self) -> None:
        validate_price_cents(50, tick_size_cents=2)  # should not raise

    def test_two_cent_tick_off_tick(self) -> None:
        with pytest.raises(ValueError, match="not on a 2-cent tick"):
            validate_price_cents(51, tick_size_cents=2)


# ── OrderSpec construction ───────────────────────────────────────────


class TestOrderSpec:
    """OrderSpec dataclass validation."""

    def test_valid_limit_order_yes_price(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.LIMIT,
            count=10,
            yes_price_cents=30,
        )
        assert spec.ticker == TICKER
        assert spec.yes_price_cents == 30

    def test_valid_limit_order_no_price(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.NO,
            order_type=OrderType.LIMIT,
            count=5,
            no_price_cents=70,
        )
        assert spec.no_price_cents == 70

    def test_valid_market_order(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.MARKET,
            count=1,
        )
        assert spec.order_type == OrderType.MARKET

    def test_rejects_limit_without_price(self) -> None:
        with pytest.raises(ValueError, match="must specify at least one"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=1,
            )

    def test_rejects_market_with_price(self) -> None:
        with pytest.raises(ValueError, match="must not specify"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.MARKET,
                count=1,
                yes_price_cents=50,
            )

    def test_rejects_zero_count(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=0,
                yes_price_cents=50,
            )

    def test_rejects_negative_count(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=-1,
                yes_price_cents=50,
            )

    def test_rejects_empty_ticker(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            OrderSpec(
                ticker="",
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=1,
                yes_price_cents=50,
            )

    def test_rejects_price_outside_band(self) -> None:
        with pytest.raises(ValueError, match="below minimum"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=1,
                yes_price_cents=0,
            )

    def test_rejects_price_100(self) -> None:
        with pytest.raises(ValueError, match="above maximum"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=1,
                yes_price_cents=100,
            )

    def test_buy_max_cost_valid(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.LIMIT,
            count=10,
            yes_price_cents=30,
            buy_max_cost_cents=500,
        )
        assert spec.buy_max_cost_cents == 500

    def test_buy_max_cost_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="buy_max_cost_cents must be a positive"):
            OrderSpec(
                ticker=TICKER,
                action=Action.BUY,
                side=Side.YES,
                order_type=OrderType.LIMIT,
                count=10,
                yes_price_cents=30,
                buy_max_cost_cents=0,
            )

    def test_frozen(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.LIMIT,
            count=1,
            yes_price_cents=50,
        )
        with pytest.raises(AttributeError):
            spec.count = 99  # type: ignore[misc]


# ── Payload serialization ────────────────────────────────────────────


class TestToPayload:
    """Verify to_payload() produces correct dict for KalshiClient."""

    def test_basic_limit_payload(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.LIMIT,
            count=10,
            yes_price_cents=30,
            post_only=True,
        )
        payload = spec.to_payload()
        assert payload == {
            "ticker": TICKER,
            "action": "buy",
            "side": "yes",
            "order_type": "limit",
            "count": 10,
            "yes_price": 30,
            "time_in_force": "gtc",
            "post_only": True,
        }

    def test_full_payload(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.SELL,
            side=Side.NO,
            order_type=OrderType.LIMIT,
            count=5,
            no_price_cents=70,
            time_in_force=TimeInForce.IOC,
            client_order_id="test-123",
            buy_max_cost_cents=1000,
            post_only=True,
            reduce_only=True,
            self_trade_prevention=SelfTradePreventionType.TAKER_AT_CROSS,
        )
        payload = spec.to_payload()
        assert payload["action"] == "sell"
        assert payload["side"] == "no"
        assert payload["no_price"] == 70
        assert payload["time_in_force"] == "ioc"
        assert payload["client_order_id"] == "test-123"
        assert payload["buy_max_cost"] == 1000
        assert payload["post_only"] is True
        assert payload["reduce_only"] is True
        assert payload["self_trade_prevention_type"] == "taker_at_cross"

    def test_market_order_no_price_in_payload(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.MARKET,
            count=1,
        )
        payload = spec.to_payload()
        assert "yes_price" not in payload
        assert "no_price" not in payload
        assert payload["order_type"] == "market"

    def test_omits_none_optional_fields(self) -> None:
        spec = OrderSpec(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            order_type=OrderType.LIMIT,
            count=1,
            yes_price_cents=50,
        )
        payload = spec.to_payload()
        assert "no_price" not in payload
        assert "client_order_id" not in payload
        assert "buy_max_cost" not in payload
        assert "post_only" not in payload  # False -> omitted
        assert "reduce_only" not in payload
        assert "self_trade_prevention_type" not in payload


# ── build_limit_order ────────────────────────────────────────────────


class TestBuildLimitOrder:
    """Builder function with tick rounding."""

    def test_basic_build(self) -> None:
        spec = build_limit_order(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            count=10,
            yes_price_cents=30,
        )
        assert spec.yes_price_cents == 30
        assert spec.post_only is True  # default for LIP

    def test_tick_rounding_applied(self) -> None:
        # 51 on 2-cent tick rounds to 52
        spec = build_limit_order(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            count=1,
            yes_price_cents=51,
            tick_size_cents=2,
        )
        assert spec.yes_price_cents == 52

    def test_post_only_default_true(self) -> None:
        spec = build_limit_order(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            count=1,
            yes_price_cents=50,
        )
        assert spec.post_only is True

    def test_post_only_override_false(self) -> None:
        spec = build_limit_order(
            ticker=TICKER,
            action=Action.BUY,
            side=Side.YES,
            count=1,
            yes_price_cents=50,
            post_only=False,
        )
        assert spec.post_only is False


# ── build_two_sided_quote ────────────────────────────────────────────


class TestBuildTwoSidedQuote:
    """Two-sided quote builder for market making."""

    def test_basic_yes_quote(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=29,
            ask_price_cents=31,
            bid_count=10,
            ask_count=10,
        )
        assert bid.action == Action.BUY
        assert bid.yes_price_cents == 29
        assert ask.action == Action.SELL
        assert ask.yes_price_cents == 31

    def test_basic_no_quote(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.NO,
            bid_price_cents=40,
            ask_price_cents=42,
            bid_count=5,
            ask_count=5,
        )
        assert bid.no_price_cents == 40
        assert bid.yes_price_cents is None
        assert ask.no_price_cents == 42
        assert ask.yes_price_cents is None

    def test_rejects_bid_equals_ask(self) -> None:
        with pytest.raises(ValueError, match="strictly less than"):
            build_two_sided_quote(
                ticker=TICKER,
                side=Side.YES,
                bid_price_cents=50,
                ask_price_cents=50,
                bid_count=10,
                ask_count=10,
            )

    def test_rejects_bid_above_ask(self) -> None:
        with pytest.raises(ValueError, match="strictly less than"):
            build_two_sided_quote(
                ticker=TICKER,
                side=Side.YES,
                bid_price_cents=55,
                ask_price_cents=50,
                bid_count=10,
                ask_count=10,
            )

    def test_client_order_id_prefix(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=29,
            ask_price_cents=31,
            bid_count=10,
            ask_count=10,
            client_order_id_prefix="q-001",
        )
        assert bid.client_order_id == "q-001-bid"
        assert ask.client_order_id == "q-001-ask"

    def test_edge_prices_1_and_99(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=1,
            ask_price_cents=99,
            bid_count=1,
            ask_count=1,
        )
        assert bid.yes_price_cents == 1
        assert ask.yes_price_cents == 99

    def test_minimum_spread_1_cent(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=49,
            ask_price_cents=50,
            bid_count=1,
            ask_count=1,
        )
        assert ask.yes_price_cents - bid.yes_price_cents == 1  # type: ignore[operator]

    def test_post_only_defaults_true(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=29,
            ask_price_cents=31,
            bid_count=1,
            ask_count=1,
        )
        assert bid.post_only is True
        assert ask.post_only is True

    def test_buy_max_cost_on_bid_only(self) -> None:
        bid, ask = build_two_sided_quote(
            ticker=TICKER,
            side=Side.YES,
            bid_price_cents=29,
            ask_price_cents=31,
            bid_count=10,
            ask_count=10,
            buy_max_cost_cents=500,
        )
        assert bid.buy_max_cost_cents == 500
        assert ask.buy_max_cost_cents is None  # ask is sell, no max cost


# ── Enum values ──────────────────────────────────────────────────────


class TestEnums:
    """Verify enum string values match Kalshi API expectations."""

    def test_side_values(self) -> None:
        assert Side.YES.value == "yes"
        assert Side.NO.value == "no"

    def test_action_values(self) -> None:
        assert Action.BUY.value == "buy"
        assert Action.SELL.value == "sell"

    def test_order_type_values(self) -> None:
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.MARKET.value == "market"

    def test_tif_values(self) -> None:
        assert TimeInForce.GTC.value == "gtc"
        assert TimeInForce.IOC.value == "ioc"
        assert TimeInForce.FOK.value == "fok"

    def test_stp_values(self) -> None:
        assert SelfTradePreventionType.TAKER_AT_CROSS.value == "taker_at_cross"
        assert SelfTradePreventionType.MAKER.value == "maker"
