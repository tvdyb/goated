"""Tests for lipmm.risk: RiskGate protocol + RiskRegistry behavior."""

from __future__ import annotations

import time
from typing import Any

import pytest

from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    SideDecision,
)
from lipmm.risk import (
    RiskContext,
    RiskGate,
    RiskRegistry,
    RiskVerdict,
)
from lipmm.theo import TheoResult


# ── helpers ────────────────────────────────────────────────────────────


def _ctx(
    *,
    bid_price: int = 44, bid_size: int = 10, bid_skip: bool = False,
    ask_price: int = 56, ask_size: int = 10, ask_skip: bool = False,
    theo_yes_prob: float = 0.50, confidence: float = 1.0,
    cycle_id: int = 1, time_to_settle_s: float = 3600.0,
    all_resting_count: int = 0, all_resting_notional: float = 0.0,
) -> RiskContext:
    decision = QuotingDecision(
        bid=SideDecision(price=bid_price, size=bid_size, skip=bid_skip,
                         reason="strategy-bid"),
        ask=SideDecision(price=ask_price, size=ask_size, skip=ask_skip,
                         reason="strategy-ask"),
    )
    return RiskContext(
        ticker="KX-T50.00",
        cycle_id=cycle_id,
        decision=decision,
        theo=TheoResult(
            yes_probability=theo_yes_prob, confidence=confidence,
            computed_at=time.time(), source="test",
        ),
        our_state=OurState(
            cur_bid_px=0, cur_bid_size=0, cur_bid_id=None,
            cur_ask_px=0, cur_ask_size=0, cur_ask_id=None,
        ),
        time_to_settle_s=time_to_settle_s,
        now_ts=time.time(),
        all_resting_count=all_resting_count,
        all_resting_notional=all_resting_notional,
    )


class _AllowGate:
    name = "AllowAll"
    async def check(self, context: RiskContext) -> RiskVerdict:
        return RiskVerdict()


class _VetoBidGate:
    name = "VetoBid"
    async def check(self, context: RiskContext) -> RiskVerdict:
        return RiskVerdict(bid_allow=False, bid_reason="bid vetoed by test")


class _VetoAskGate:
    name = "VetoAsk"
    async def check(self, context: RiskContext) -> RiskVerdict:
        return RiskVerdict(ask_allow=False, ask_reason="ask vetoed by test")


class _ExceptionGate:
    name = "Boom"
    async def check(self, context: RiskContext) -> RiskVerdict:
        raise RuntimeError("simulated gate error")


# ── 1. Protocol shape ─────────────────────────────────────────────────


def test_allow_gate_satisfies_protocol() -> None:
    assert isinstance(_AllowGate(), RiskGate)


def test_risk_verdict_default_allows_everything() -> None:
    v = RiskVerdict()
    assert v.bid_allow is True
    assert v.ask_allow is True
    assert v.vetoes_anything is False


def test_risk_verdict_veto_one_side() -> None:
    v = RiskVerdict(bid_allow=False, bid_reason="x")
    assert v.vetoes_anything is True
    assert v.ask_allow is True


# ── 2. Empty registry passes through ──────────────────────────────────


@pytest.mark.asyncio
async def test_empty_registry_passes_decision_unchanged() -> None:
    reg = RiskRegistry()
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision is ctx.decision
    assert audit == []


# ── 3. Single gate veto propagates ────────────────────────────────────


@pytest.mark.asyncio
async def test_single_veto_bid_applies_skip() -> None:
    reg = RiskRegistry([_VetoBidGate()])
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision.bid.skip is True
    assert "VetoBid" in decision.bid.reason
    assert decision.ask.skip is False
    assert len(audit) == 1
    assert audit[0]["gate"] == "VetoBid"
    assert audit[0]["bid"] == "veto"
    assert audit[0]["ask"] == "allow"


@pytest.mark.asyncio
async def test_single_veto_ask_applies_skip() -> None:
    reg = RiskRegistry([_VetoAskGate()])
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision.ask.skip is True
    assert decision.bid.skip is False


# ── 4. Multiple gates: any-veto-wins ──────────────────────────────────


@pytest.mark.asyncio
async def test_any_veto_wins_per_side() -> None:
    """Allow + Veto for same side → veto wins. Allow + Allow → allow."""
    reg = RiskRegistry([_AllowGate(), _VetoBidGate(), _AllowGate()])
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision.bid.skip is True
    assert decision.ask.skip is False
    # All 3 gates' verdicts in audit
    assert len(audit) == 3
    gates = [a["gate"] for a in audit]
    assert gates == ["AllowAll", "VetoBid", "AllowAll"]


@pytest.mark.asyncio
async def test_two_gates_veto_different_sides() -> None:
    """One vetoes bid, one vetoes ask → both sides skipped."""
    reg = RiskRegistry([_VetoBidGate(), _VetoAskGate()])
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision.bid.skip is True
    assert decision.ask.skip is True
    assert "VetoBid" in decision.bid.reason
    assert "VetoAsk" in decision.ask.reason


# ── 5. Audit trail captures every gate's verdict ──────────────────────


@pytest.mark.asyncio
async def test_audit_trail_includes_allowing_gates() -> None:
    """Audit isn't just vetoes — every gate's verdict is recorded."""
    reg = RiskRegistry([_AllowGate(), _AllowGate()])
    ctx = _ctx()
    _, audit = await reg.evaluate(ctx)
    assert len(audit) == 2
    for entry in audit:
        assert entry["bid"] == "allow"
        assert entry["ask"] == "allow"


# ── 6. Already-skipped sides aren't re-vetoed ─────────────────────────


@pytest.mark.asyncio
async def test_already_skipped_side_unchanged() -> None:
    """If strategy already returned skip=True, registry leaves it alone
    even if a gate vetoes (skip is already 'maximally restrictive')."""
    reg = RiskRegistry([_VetoBidGate()])
    ctx = _ctx(bid_skip=True)
    decision, _ = await reg.evaluate(ctx)
    # Strategy's skip reason preserved, not overwritten by registry
    assert decision.bid.skip is True
    assert decision.bid.reason == "strategy-bid"


# ── 7. Gate exceptions don't crash evaluation (fail open) ─────────────


@pytest.mark.asyncio
async def test_gate_exception_is_audited_but_does_not_crash() -> None:
    reg = RiskRegistry([_AllowGate(), _ExceptionGate(), _VetoBidGate()])
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    # Subsequent gates still run
    assert decision.bid.skip is True  # VetoBid took effect
    # Audit captures the exception
    assert len(audit) == 3
    boom = next(a for a in audit if a["gate"] == "Boom")
    assert "error" in boom
    assert "RuntimeError" in boom["error"]


# ── 8. register() adds gates incrementally ────────────────────────────


@pytest.mark.asyncio
async def test_register_method_appends_gate() -> None:
    reg = RiskRegistry()
    assert len(reg.gates) == 0
    reg.register(_AllowGate())
    reg.register(_VetoBidGate())
    assert len(reg.gates) == 2
    ctx = _ctx()
    decision, audit = await reg.evaluate(ctx)
    assert decision.bid.skip is True
    assert len(audit) == 2
