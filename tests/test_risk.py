"""Tests for engine.risk — risk gates (ACT-12).

Covers:
  - Pre-trade gate: allowed orders pass, blocked orders raise RiskBreachError
  - Post-trade check: returns TriggerResult with fired=True on breach
  - Aggregate delta cap
  - Per-event delta cap
  - Max-loss cap
  - Kill trigger integration
  - Config loading (load_risk_limits)
  - Edge cases: zero delta, reducing positions, flipping positions
"""

from __future__ import annotations

import pytest

from engine.kill import TriggerResult
from engine.risk import (
    ProposedOrder,
    RiskBreachError,
    RiskGate,
    RiskLimits,
    load_risk_limits,
)
from state.positions import Fill, PositionStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> PositionStore:
    """Fresh position store."""
    return PositionStore()


@pytest.fixture
def default_limits() -> RiskLimits:
    """Permissive limits for basic tests."""
    return RiskLimits(
        aggregate_delta_cap=100,
        per_event_delta_cap=50,
        max_loss_cents=500_000,  # $5,000
    )


@pytest.fixture
def gate(store: PositionStore, default_limits: RiskLimits) -> RiskGate:
    return RiskGate(position_store=store, limits=default_limits)


def _fill(
    store: PositionStore,
    market: str,
    side: str,
    action: str,
    count: int,
    price: int,
    fill_id: str,
) -> None:
    """Helper to apply a fill to the store."""
    store.apply_fill(Fill(
        market_ticker=market,
        side=side,
        action=action,
        count=count,
        price_cents=price,
        fill_id=fill_id,
    ))


# ---------------------------------------------------------------------------
# RiskLimits validation
# ---------------------------------------------------------------------------


class TestRiskLimits:
    def test_valid_limits(self) -> None:
        lim = RiskLimits(
            aggregate_delta_cap=100,
            per_event_delta_cap=50,
            max_loss_cents=100_000,
        )
        assert lim.aggregate_delta_cap == 100

    def test_zero_aggregate_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="aggregate_delta_cap"):
            RiskLimits(aggregate_delta_cap=0, per_event_delta_cap=50, max_loss_cents=100)

    def test_negative_per_event_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="per_event_delta_cap"):
            RiskLimits(aggregate_delta_cap=50, per_event_delta_cap=-1, max_loss_cents=100)

    def test_negative_max_loss_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_loss_cents"):
            RiskLimits(aggregate_delta_cap=50, per_event_delta_cap=50, max_loss_cents=-1)


# ---------------------------------------------------------------------------
# load_risk_limits
# ---------------------------------------------------------------------------


class TestLoadRiskLimits:
    def test_defaults_only(self) -> None:
        lim = load_risk_limits()
        assert lim.aggregate_delta_cap == 500
        assert lim.per_event_delta_cap == 200
        assert lim.max_loss_cents == 25_000 * 100

    def test_config_override_max_loss(self) -> None:
        cfg = {"position_cap": {"max_loss_dollars": 10_000}}
        lim = load_risk_limits(cfg)
        assert lim.max_loss_cents == 10_000 * 100

    def test_explicit_overrides_config(self) -> None:
        cfg = {"position_cap": {"max_loss_dollars": 10_000}}
        lim = load_risk_limits(cfg, max_loss_dollars=5_000)
        assert lim.max_loss_cents == 5_000 * 100

    def test_explicit_overrides_all(self) -> None:
        lim = load_risk_limits(
            aggregate_delta_cap=42,
            per_event_delta_cap=21,
            max_loss_dollars=1_000,
        )
        assert lim.aggregate_delta_cap == 42
        assert lim.per_event_delta_cap == 21
        assert lim.max_loss_cents == 100_000

    def test_none_config_uses_defaults(self) -> None:
        lim = load_risk_limits(None)
        assert lim.max_loss_cents == 25_000 * 100

    def test_config_missing_position_cap(self) -> None:
        lim = load_risk_limits({"other_key": 123})
        assert lim.max_loss_cents == 25_000 * 100


# ---------------------------------------------------------------------------
# Pre-trade gate: allowed
# ---------------------------------------------------------------------------


class TestPreTradeAllowed:
    def test_empty_book_small_order(self, gate: RiskGate) -> None:
        """Small order into empty book should pass."""
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=10,
            cost_per_contract_cents=30,
        )
        gate.check_pre_trade(order)  # should not raise

    def test_existing_position_within_limits(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        """Order that keeps all caps within limits passes."""
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 20, 40, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=10,
            cost_per_contract_cents=40,
        )
        gate.check_pre_trade(order)

    def test_reducing_position_always_allowed(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        """Selling to reduce position should always pass."""
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 40, 50, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=-10,
            cost_per_contract_cents=50,
        )
        gate.check_pre_trade(order)

    def test_negative_delta_into_empty_book(self, gate: RiskGate) -> None:
        """Short order into empty book within caps passes."""
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=-10,
            cost_per_contract_cents=60,
        )
        gate.check_pre_trade(order)


# ---------------------------------------------------------------------------
# Pre-trade gate: blocked — aggregate delta
# ---------------------------------------------------------------------------


class TestPreTradeAggregateDelta:
    def test_single_order_exceeds_aggregate_cap(self, gate: RiskGate) -> None:
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=101,  # cap is 100
            cost_per_contract_cents=10,
        )
        with pytest.raises(RiskBreachError, match="aggregate_delta"):
            gate.check_pre_trade(order)

    def test_accumulated_breaches_aggregate_cap(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 90, 30, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-18",
            signed_delta_qty=11,  # 90+11=101 > 100
            cost_per_contract_cents=30,
        )
        with pytest.raises(RiskBreachError, match="aggregate_delta"):
            gate.check_pre_trade(order)

    def test_negative_aggregate_breach(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        """Short side breach."""
        _fill(store, "KXSOYBEANW-26APR24-17", "no", "buy", 95, 60, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-18",
            signed_delta_qty=-6,  # -95-6=-101
            cost_per_contract_cents=60,
        )
        with pytest.raises(RiskBreachError, match="aggregate_delta"):
            gate.check_pre_trade(order)

    def test_at_exact_cap_allowed(self, store: PositionStore) -> None:
        """Exactly at aggregate cap should pass (per-event cap large enough)."""
        limits = RiskLimits(
            aggregate_delta_cap=100,
            per_event_delta_cap=100,
            max_loss_cents=500_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 90, 30, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-18",
            signed_delta_qty=10,  # 90+10=100 == cap
            cost_per_contract_cents=30,
        )
        gate.check_pre_trade(order)  # should not raise


# ---------------------------------------------------------------------------
# Pre-trade gate: blocked — per-Event delta
# ---------------------------------------------------------------------------


class TestPreTradePerEventDelta:
    def test_single_event_breach(self, gate: RiskGate) -> None:
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=51,  # cap is 50
            cost_per_contract_cents=20,
        )
        with pytest.raises(RiskBreachError, match="per_event_delta"):
            gate.check_pre_trade(order)

    def test_accumulated_within_event(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 45, 30, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-18",  # same event
            signed_delta_qty=6,  # 45+6=51 > 50
            cost_per_contract_cents=30,
        )
        with pytest.raises(RiskBreachError, match="per_event_delta"):
            gate.check_pre_trade(order)

    def test_different_events_independent(
        self, store: PositionStore, gate: RiskGate,
    ) -> None:
        """Event cap is per-event; different events don't interfere."""
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 45, 30, "f1")
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR25-17",  # different event
            signed_delta_qty=45,
            cost_per_contract_cents=30,
        )
        gate.check_pre_trade(order)  # should not raise


# ---------------------------------------------------------------------------
# Pre-trade gate: blocked — max-loss
# ---------------------------------------------------------------------------


class TestPreTradeMaxLoss:
    def test_single_order_exceeds_max_loss(self) -> None:
        """Order whose cost exceeds max-loss cap."""
        store = PositionStore()
        limits = RiskLimits(
            aggregate_delta_cap=1000,
            per_event_delta_cap=1000,
            max_loss_cents=1000,  # $10 cap
        )
        gate = RiskGate(position_store=store, limits=limits)
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=20,
            cost_per_contract_cents=60,  # 20*60=1200 > 1000
        )
        with pytest.raises(RiskBreachError, match="max_loss"):
            gate.check_pre_trade(order)

    def test_accumulated_max_loss_breach(self) -> None:
        store = PositionStore()
        limits = RiskLimits(
            aggregate_delta_cap=1000,
            per_event_delta_cap=1000,
            max_loss_cents=2000,  # $20 cap
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 10, 50, "f1")
        # Current max-loss = 10*50 = 500
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-18",
            signed_delta_qty=30,
            cost_per_contract_cents=55,  # 30*55=1650; total=500+1650=2150 > 2000
        )
        with pytest.raises(RiskBreachError, match="max_loss"):
            gate.check_pre_trade(order)

    def test_short_order_max_loss(self) -> None:
        """Short order max-loss = count * (100 - price)."""
        store = PositionStore()
        limits = RiskLimits(
            aggregate_delta_cap=1000,
            per_event_delta_cap=1000,
            max_loss_cents=500,
        )
        gate = RiskGate(position_store=store, limits=limits)
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=-10,
            cost_per_contract_cents=30,  # max-loss = 10*(100-30)=700 > 500
        )
        with pytest.raises(RiskBreachError, match="max_loss"):
            gate.check_pre_trade(order)


# ---------------------------------------------------------------------------
# Post-trade check
# ---------------------------------------------------------------------------


class TestPostTradeCheck:
    def test_clean_book_ok(self, gate: RiskGate) -> None:
        result = gate.check_post_trade()
        assert not result.fired
        assert result.name == "risk_post_trade_ok"

    def test_aggregate_breach_detected(self, store: PositionStore) -> None:
        limits = RiskLimits(
            aggregate_delta_cap=10,
            per_event_delta_cap=100,
            max_loss_cents=1_000_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        # Push past the cap by applying fills directly
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 11, 30, "f1")
        result = gate.check_post_trade()
        assert result.fired
        assert result.name == "risk_aggregate_delta_breach"

    def test_per_event_breach_detected(self, store: PositionStore) -> None:
        limits = RiskLimits(
            aggregate_delta_cap=1000,
            per_event_delta_cap=10,
            max_loss_cents=1_000_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 11, 30, "f1")
        result = gate.check_post_trade()
        assert result.fired
        assert result.name == "risk_per_event_delta_breach"

    def test_max_loss_breach_detected(self, store: PositionStore) -> None:
        limits = RiskLimits(
            aggregate_delta_cap=1000,
            per_event_delta_cap=1000,
            max_loss_cents=100,  # $1
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 5, 30, "f1")
        # max-loss = 5*30 = 150 > 100
        result = gate.check_post_trade()
        assert result.fired
        assert result.name == "risk_max_loss_breach"

    def test_returns_trigger_result_type(self, gate: RiskGate) -> None:
        result = gate.check_post_trade()
        assert isinstance(result, TriggerResult)


# ---------------------------------------------------------------------------
# Kill trigger integration
# ---------------------------------------------------------------------------


class TestKillTriggerIntegration:
    def test_make_kill_trigger_callable(self, gate: RiskGate) -> None:
        trigger = gate.make_kill_trigger()
        assert callable(trigger)

    def test_trigger_returns_ok_when_clean(self, gate: RiskGate) -> None:
        trigger = gate.make_kill_trigger()
        result = trigger()
        assert not result.fired

    def test_trigger_fires_on_breach(self, store: PositionStore) -> None:
        limits = RiskLimits(
            aggregate_delta_cap=5,
            per_event_delta_cap=100,
            max_loss_cents=1_000_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        trigger = gate.make_kill_trigger()

        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 6, 30, "f1")
        result = trigger()
        assert result.fired
        assert "aggregate" in result.name


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_delta_order_passes(self, gate: RiskGate) -> None:
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR24-17",
            signed_delta_qty=0,
            cost_per_contract_cents=50,
        )
        gate.check_pre_trade(order)

    def test_multiple_events_aggregate(self, store: PositionStore) -> None:
        """Aggregate sums across different events."""
        limits = RiskLimits(
            aggregate_delta_cap=100,
            per_event_delta_cap=80,
            max_loss_cents=1_000_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 60, 30, "f1")
        _fill(store, "KXSOYBEANW-26APR25-17", "yes", "buy", 30, 30, "f2")
        # agg = 90, adding 11 -> 101 > 100
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR26-17",
            signed_delta_qty=11,
            cost_per_contract_cents=30,
        )
        with pytest.raises(RiskBreachError, match="aggregate_delta"):
            gate.check_pre_trade(order)

    def test_opposite_sides_offset_aggregate(self, store: PositionStore) -> None:
        """Long in one event, short in another: net aggregate is small."""
        limits = RiskLimits(
            aggregate_delta_cap=100,
            per_event_delta_cap=80,
            max_loss_cents=1_000_000,
        )
        gate = RiskGate(position_store=store, limits=limits)
        _fill(store, "KXSOYBEANW-26APR24-17", "yes", "buy", 70, 30, "f1")
        _fill(store, "KXSOYBEANW-26APR25-17", "no", "buy", 60, 70, "f2")
        # agg = 70 - 60 = 10; adding 80 -> 90 < 100 OK
        # But per-event for the new event would be 80 == per_event_delta_cap(80)
        order = ProposedOrder(
            market_ticker="KXSOYBEANW-26APR26-17",
            signed_delta_qty=80,
            cost_per_contract_cents=30,
        )
        gate.check_pre_trade(order)  # should pass

    def test_risk_breach_error_attributes(self) -> None:
        err = RiskBreachError("test_cap", "some detail")
        assert err.cap_name == "test_cap"
        assert err.detail == "some detail"
        assert "test_cap" in str(err)
