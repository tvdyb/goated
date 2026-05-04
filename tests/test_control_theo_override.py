"""Tests for Phase 7 — manual theo overrides via dashboard.

Coverage:
  - ControlState mutations (set/clear, bounds, snapshot field)
  - HTTP endpoints (/control/set_theo_override, /control/clear_theo_override,
    auth, audit, broadcast, optimistic concurrency)
  - LIPRunner: override skips the registered TheoProvider
  - Dashboard: theo-overrides panel rendering + first-paint
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from lipmm.control import (
    Broadcaster,
    ControlState,
    TheoOverride,
    build_app,
)
from lipmm.control.auth import issue_token


SECRET = "0123456789abcdef0123456789abcdef"


def _client() -> tuple[TestClient, ControlState, Broadcaster]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)
    return TestClient(app), state, b


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET, actor='alice')}"}


# ── ControlState mutations ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_theo_override_records_value() -> None:
    state = ControlState()
    v = await state.set_theo_override(
        "KX-T1", yes_probability=0.55, reason="initial est",
    )
    assert v == 1
    ov = state.get_theo_override("KX-T1")
    assert ov is not None
    assert ov.yes_probability == 0.55
    assert ov.confidence == 1.0  # default
    assert ov.reason == "initial est"


@pytest.mark.asyncio
async def test_set_theo_override_validates_bounds() -> None:
    state = ControlState()
    with pytest.raises(ValueError, match="yes_probability"):
        await state.set_theo_override("KX-T1", yes_probability=1.5, reason="x")
    with pytest.raises(ValueError, match="confidence"):
        await state.set_theo_override(
            "KX-T1", yes_probability=0.5, confidence=-0.1, reason="x",
        )
    with pytest.raises(ValueError, match="reason"):
        await state.set_theo_override("KX-T1", yes_probability=0.5, reason="")


@pytest.mark.asyncio
async def test_clear_theo_override_removes_entry() -> None:
    state = ControlState()
    await state.set_theo_override("KX-T1", 0.5, reason="x")
    v = await state.clear_theo_override("KX-T1")
    assert v == 2
    assert state.get_theo_override("KX-T1") is None


@pytest.mark.asyncio
async def test_clear_theo_override_idempotent() -> None:
    """Clearing a non-existent override still bumps version (so dashboards
    re-render and the operator sees the action took effect)."""
    state = ControlState()
    v = await state.clear_theo_override("KX-NEVER")
    assert v == 1


@pytest.mark.asyncio
async def test_snapshot_includes_theo_overrides() -> None:
    state = ControlState()
    await state.set_theo_override(
        "KX-T1", 0.42, confidence=0.8, reason="bayesian guess", actor="alice",
    )
    snap = state.snapshot()
    assert "theo_overrides" in snap
    assert len(snap["theo_overrides"]) == 1
    entry = snap["theo_overrides"][0]
    assert entry["ticker"] == "KX-T1"
    assert entry["yes_probability"] == 0.42
    assert entry["yes_cents"] == 42
    assert entry["confidence"] == 0.8
    assert entry["reason"] == "bayesian guess"
    assert entry["actor"] == "alice"


# ── HTTP endpoints ──────────────────────────────────────────────────


def test_post_set_theo_override_updates_state() -> None:
    client, state, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1",
        "yes_cents": 55,
        "confidence": 0.9,
        "reason": "consensus says 51, my prior says higher",
        "request_id": "req-theo-set-1",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["new_version"] == 1
    assert body["actor"] == "alice"
    ov = state.get_theo_override("KX-T1")
    assert ov is not None
    assert ov.yes_probability == 0.55
    assert ov.confidence == 0.9
    assert ov.actor == "alice"


def test_post_set_theo_override_requires_auth() -> None:
    client, _, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1", "yes_cents": 55,
        "reason": "abcd", "request_id": "req-noauth-1",
    })
    assert r.status_code == 401


def test_post_set_theo_override_rejects_short_reason() -> None:
    client, _, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1", "yes_cents": 55,
        "reason": "x",  # too short
        "request_id": "req-shortreason-1",
    }, headers=_h())
    assert r.status_code == 422  # pydantic min_length


def test_post_set_theo_override_rejects_out_of_range_cents() -> None:
    client, _, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1", "yes_cents": 100,  # max is 99
        "reason": "abcd", "request_id": "req-rangecents-1",
    }, headers=_h())
    assert r.status_code == 422


def test_post_set_theo_override_if_version_mismatch_returns_409() -> None:
    client, state, _ = _client()
    # Bump version first
    asyncio.get_event_loop().run_until_complete(state.pause_global())
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1", "yes_cents": 55, "reason": "abcd",
        "request_id": "req-stale-ifv-1",
        "if_version": 0,  # state is at v1 now
    }, headers=_h())
    assert r.status_code == 409


def test_post_clear_theo_override_works() -> None:
    client, state, _ = _client()
    asyncio.get_event_loop().run_until_complete(
        state.set_theo_override("KX-T1", 0.5, reason="abcd")
    )
    r = client.post("/control/clear_theo_override", json={
        "ticker": "KX-T1", "request_id": "req-theo-clear-1",
    }, headers=_h())
    assert r.status_code == 200
    assert state.get_theo_override("KX-T1") is None


def test_get_state_lists_theo_overrides() -> None:
    client, state, _ = _client()
    asyncio.get_event_loop().run_until_complete(
        state.set_theo_override(
            "KX-T1", 0.55, confidence=0.8,
            reason="my best guess", actor="alice",
        )
    )
    r = client.get("/control/state", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert "theo_overrides" in body
    assert len(body["theo_overrides"]) == 1
    assert body["theo_overrides"][0]["ticker"] == "KX-T1"
    assert body["theo_overrides"][0]["yes_cents"] == 55


def test_set_theo_override_broadcasts_state_change() -> None:
    """Setting an override should push a state_change event to WS subscribers
    so all dashboard tabs converge."""
    client, _, b = _client()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream?token={token}") as ws:
        ws.receive_json()  # initial
        r = client.post("/control/set_theo_override", json={
            "ticker": "KX-T1", "yes_cents": 60,
            "reason": "survey is bullish",
            "request_id": "req-broadcast-1",
        }, headers=_h())
        assert r.status_code == 200
        evt = ws.receive_json()
        assert evt["event_type"] == "state_change"
        assert evt["command_type"] == "set_theo_override"
        # Snapshot in the broadcast contains the new override
        ovs = evt["snapshot"]["theo_overrides"]
        assert any(ov["ticker"] == "KX-T1" for ov in ovs)


# ── Runner integration ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_uses_theo_override_when_set(monkeypatch) -> None:
    """When an override is set for a ticker, the LIPRunner skips the
    registered TheoProvider entirely and feeds the strategy a TheoResult
    derived from the override."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult, TheoProvider
    from lipmm.execution import OrderManager
    from lipmm.execution.base import OrderbookLevels, Position, Balance, Order

    provider_calls: list[str] = []

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def theo(self, ticker: str) -> TheoResult:
            provider_calls.append(ticker)
            return TheoResult(
                yes_probability=0.50, confidence=1.0,
                computed_at=0.0, source="STUB",
            )

    captured_theo: list[TheoResult] = []

    class _CapturingStrategy:
        name = "capturing"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            captured_theo.append(theo)
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="test"),
                ask=SideDecision(price=0, size=0, skip=True, reason="test"),
            )

    class _StubExchange:
        async def get_orderbook(self, ticker):
            return OrderbookLevels(ticker=ticker, yes_levels=[], no_levels=[])
        async def list_resting_orders(self): return []
        async def list_positions(self): return []
        async def get_balance(self):
            return Balance(0.0, 0.0)
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_order(self, *a, **k): return True
        async def cancel_orders(self, ids):
            return {i: True for i in ids}

    class _Source:
        async def list_active_tickers(self, exchange): return ["KX-T1", "KX-T2"]

    state = ControlState()
    # Override KX-T1 only — KX-T2 should still hit the provider
    await state.set_theo_override(
        "KX-T1", yes_probability=0.77, confidence=0.9,
        reason="manual estimate", actor="alice",
    )
    registry = TheoRegistry()
    registry.register(_StubProvider())
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=registry,
        strategy=_CapturingStrategy(),
        order_manager=OrderManager(),
        exchange=_StubExchange(),
        ticker_source=_Source(),
        control_state=state,
    )

    # Run one cycle by hand (rather than runner.run() which loops forever)
    await runner._theo.warmup_all()  # noqa: SLF001
    await runner._strategy.warmup()  # noqa: SLF001
    await runner._cycle()  # noqa: SLF001

    # Provider was called for KX-T2 only
    assert provider_calls == ["KX-T2"]
    # Strategy received the override theo for KX-T1 and the provider's for KX-T2
    assert len(captured_theo) == 2
    t1 = captured_theo[0]
    t2 = captured_theo[1]
    assert t1.yes_probability == 0.77
    assert t1.confidence == 0.9
    assert t1.source.startswith("manual-override:")
    assert t1.extras.get("override_reason") == "manual estimate"
    assert t2.source == "STUB"


# ── Dashboard rendering ────────────────────────────────────────────


def test_dashboard_renders_theo_overrides_panel() -> None:
    state = ControlState()
    asyncio.get_event_loop().run_until_complete(
        state.set_theo_override(
            "KX-T1", 0.55, confidence=0.8,
            reason="dashboard render test", actor="alice",
        )
    )
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    assert 'id="theo-overrides-panel"' in body
    assert "KX-T1" in body
    assert "55c" in body
    assert "dashboard render test" in body


def test_dashboard_empty_theo_overrides_shows_placeholder() -> None:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    body = r.text
    assert 'id="theo-overrides-panel"' in body
    assert "no overrides" in body
