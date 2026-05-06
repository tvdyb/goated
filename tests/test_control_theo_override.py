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
    # Default mode is "fixed"
    assert entry["mode"] == "fixed"


@pytest.mark.asyncio
async def test_set_theo_override_mode_track_mid_persists() -> None:
    state = ControlState()
    await state.set_theo_override(
        "KX-T1", 0.50, confidence=0.7, reason="market-following on",
        actor="alice", mode="track_mid",
    )
    ov = state.get_theo_override("KX-T1")
    assert ov is not None
    assert ov.mode == "track_mid"
    snap_entry = state.snapshot()["theo_overrides"][0]
    assert snap_entry["mode"] == "track_mid"


@pytest.mark.asyncio
async def test_set_theo_override_rejects_invalid_mode() -> None:
    state = ControlState()
    with pytest.raises(ValueError, match="mode"):
        await state.set_theo_override(
            "KX-T1", 0.50, reason="x", mode="bogus",  # type: ignore[arg-type]
        )


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
    assert ov.mode == "fixed"


def test_post_set_theo_override_accepts_subcent() -> None:
    """Sub-cent precision (0.1¢) is accepted for sub-cent markets like
    PMI / election strikes where the orderbook carries 47.7¢ levels."""
    client, state, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1",
        "yes_cents": 47.7,
        "confidence": 0.95,
        "reason": "subcent override on 0.1¢ tick market",
        "request_id": "req-theo-subcent-1",
    }, headers=_h())
    assert r.status_code == 200, r.text
    ov = state.get_theo_override("KX-T1")
    assert ov is not None
    assert abs(ov.yes_probability - 0.477) < 1e-9
    # Snapshot exposes one-decimal precision for the dashboard chip.
    snap = state.snapshot()
    entries = {e["ticker"]: e for e in snap["theo_overrides"]}
    assert entries["KX-T1"]["yes_cents"] == 47.7


def test_post_set_theo_override_rejects_subcent_below_min() -> None:
    """Pydantic gate: yes_cents < 0.1 fails validation."""
    client, _, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1",
        "yes_cents": 0.05,
        "confidence": 0.9,
        "reason": "should reject",
        "request_id": "req-theo-low-1",
    }, headers=_h())
    assert r.status_code == 422


def test_post_set_theo_override_track_mid_mode() -> None:
    client, state, _ = _client()
    r = client.post("/control/set_theo_override", json={
        "ticker": "KX-T1",
        "yes_cents": 50,  # placeholder, ignored at quote time
        "confidence": 0.7,
        "reason": "market-following mode",
        "request_id": "req-theo-mid-1",
        "mode": "track_mid",
    }, headers=_h())
    assert r.status_code == 200
    ov = state.get_theo_override("KX-T1")
    assert ov is not None
    assert ov.mode == "track_mid"
    assert ov.confidence == 0.7


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
    captured_by_ticker: dict[str, TheoResult] = {}

    class _CapturingStrategy:
        name = "capturing"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            captured_theo.append(theo)
            captured_by_ticker[ticker] = theo
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
    # Strategy received the override theo for KX-T1 and the provider's
    # for KX-T2 (lookup by ticker since round-robin can rotate order)
    assert len(captured_theo) == 2
    t1 = captured_by_ticker["KX-T1"]
    t2 = captured_by_ticker["KX-T2"]
    assert t1.yes_probability == 0.77
    assert t1.confidence == 0.9
    assert t1.source.startswith("manual-override:")
    assert t1.extras.get("override_reason") == "manual estimate"
    assert t2.source == "STUB"


@pytest.mark.asyncio
async def test_runner_track_mid_builds_theo_from_orderbook_mid() -> None:
    """When override.mode == 'track_mid', the runner ignores
    yes_probability and computes theo = (best_bid + best_ask) / 200
    each cycle from the live orderbook."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult
    from lipmm.execution import OrderManager
    from lipmm.execution.base import OrderbookLevels, Balance

    captured: list[TheoResult] = []

    class _CapturingStrategy:
        name = "capturing"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            captured.append(theo)
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="t"),
                ask=SideDecision(price=0, size=0, skip=True, reason="t"),
            )

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def theo(self, t):
            raise AssertionError("provider should not be called when override is set")

    class _StubExchange:
        def __init__(self, ticker, yes_levels, no_levels):
            self._ticker, self._y, self._n = ticker, yes_levels, no_levels
        async def get_orderbook(self, t):
            return OrderbookLevels(ticker=t, yes_levels=self._y, no_levels=self._n)
        async def list_resting_orders(self): return []
        async def list_positions(self): return []
        async def get_balance(self): return Balance(0.0, 0.0)
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_order(self, *a, **k): return True
        async def cancel_orders(self, ids): return {i: True for i in ids}

    class _Source:
        async def list_active_tickers(self, exchange): return ["KX-T1"]

    # Best yes bid 80, best yes ask 84 → mid = 82
    # Levels in t1c: 800 t1c = 80¢, 160 t1c = 16¢ (= yes ask 84¢)
    yes_levels = [(800, 100.0)]
    no_levels = [(160, 100.0)]

    state = ControlState()
    await state.set_theo_override(
        "KX-T1", yes_probability=0.50, confidence=0.7,
        reason="market-following", actor="alice", mode="track_mid",
    )
    registry = TheoRegistry()
    registry.register(_StubProvider())
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=registry,
        strategy=_CapturingStrategy(),
        order_manager=OrderManager(),
        exchange=_StubExchange("KX-T1", yes_levels, no_levels),
        ticker_source=_Source(),
        control_state=state,
    )
    await runner._theo.warmup_all()  # noqa: SLF001
    await runner._strategy.warmup()  # noqa: SLF001
    await runner._cycle()  # noqa: SLF001

    assert len(captured) == 1
    theo = captured[0]
    assert theo.yes_probability == 0.82          # mid in [0,1]
    assert theo.yes_cents == 82                  # mid in cents
    assert theo.confidence == 0.7                # operator-set
    assert theo.source.startswith("manual-override-mid:")
    assert theo.extras["mid_cents"] == 82.0
    assert theo.extras["best_bid_c"] == 80
    assert theo.extras["best_ask_c"] == 84


@pytest.mark.asyncio
async def test_runner_track_mid_skips_on_degenerate_book() -> None:
    """One-sided / crossed books → confidence forced to 0 so the
    strategy skips the strike that cycle."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult
    from lipmm.execution import OrderManager
    from lipmm.execution.base import OrderbookLevels, Balance

    captured: list[TheoResult] = []

    class _CapturingStrategy:
        name = "capturing"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            captured.append(theo)
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="t"),
                ask=SideDecision(price=0, size=0, skip=True, reason="t"),
            )

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def theo(self, t): raise AssertionError("not used")

    class _StubExchange:
        async def get_orderbook(self, t):
            # Empty book — best_bid=0, best_ask=100 (the runner's
            # "no best" defaults) → degenerate
            return OrderbookLevels(ticker=t, yes_levels=[], no_levels=[])
        async def list_resting_orders(self): return []
        async def list_positions(self): return []
        async def get_balance(self): return Balance(0.0, 0.0)
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_order(self, *a, **k): return True
        async def cancel_orders(self, ids): return {i: True for i in ids}

    class _Source:
        async def list_active_tickers(self, exchange): return ["KX-T1"]

    state = ControlState()
    await state.set_theo_override(
        "KX-T1", yes_probability=0.50, confidence=0.9,
        reason="market-following", actor="alice", mode="track_mid",
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
    await runner._theo.warmup_all()  # noqa: SLF001
    await runner._strategy.warmup()  # noqa: SLF001
    await runner._cycle()  # noqa: SLF001

    assert len(captured) == 1
    theo = captured[0]
    # Confidence forced to 0 → strategy will skip both sides
    assert theo.confidence == 0.0
    assert theo.source.startswith("manual-override-mid:")
    assert "skip_reason" in theo.extras


@pytest.mark.asyncio
async def test_runner_track_mid_one_sided_book_falls_back_to_yes_cents() -> None:
    """When the book is one-sided (only asks, no bids), track-mid
    falls back to the operator's `yes_cents` from the override so
    the bot can still provide liquidity. This is exactly the
    scenario where LIP MM is most valuable (be the only quoter on
    a fresh market with one side empty)."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult
    from lipmm.execution import OrderManager
    from lipmm.execution.base import OrderbookLevels, Balance

    captured: list[TheoResult] = []

    class _CapturingStrategy:
        name = "capturing"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            captured.append(theo)
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="t"),
                ask=SideDecision(price=0, size=0, skip=True, reason="t"),
            )

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self) -> None: pass
        async def shutdown(self) -> None: pass
        async def theo(self, t): raise AssertionError("not used")

    class _AsksOnlyExchange:
        async def get_orderbook(self, t):
            # Only asks — best_bid_t1c=0, best_ask=98¢ (980 t1c).
            # No-side bid at 02 → yes-ask at 98.
            return OrderbookLevels(
                ticker=t, yes_levels=[], no_levels=[(20, 100.0)],
            )
        async def list_resting_orders(self): return []
        async def list_positions(self): return []
        async def get_balance(self): return Balance(0.0, 0.0)
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_order(self, *a, **k): return True
        async def cancel_orders(self, ids): return {i: True for i in ids}

    class _Source:
        async def list_active_tickers(self, exchange): return ["KX-T1"]

    state = ControlState()
    # Operator sets track-mid with yes_cents=30 (= yes_probability 0.30)
    # as the explicit fallback estimate for one-sided books.
    await state.set_theo_override(
        "KX-T1", yes_probability=0.30, confidence=0.95,
        reason="track-mid with explicit fallback estimate",
        actor="alice", mode="track_mid",
    )
    registry = TheoRegistry()
    registry.register(_StubProvider())
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=registry,
        strategy=_CapturingStrategy(),
        order_manager=OrderManager(),
        exchange=_AsksOnlyExchange(),
        ticker_source=_Source(),
        control_state=state,
    )
    await runner._theo.warmup_all()  # noqa: SLF001
    await runner._strategy.warmup()  # noqa: SLF001
    await runner._cycle()  # noqa: SLF001

    assert len(captured) == 1
    theo = captured[0]
    # Fallback used the operator's yes_probability (0.30), NOT 0
    assert theo.yes_probability == pytest.approx(0.30)
    assert theo.confidence == 0.95
    assert theo.source == "manual-override-mid-fallback:alice"
    assert "fallback_reason" in theo.extras
    assert "one-sided" in theo.extras["fallback_reason"]


# ── Dashboard rendering ────────────────────────────────────────────


def test_dashboard_renders_theo_override_in_strike_row() -> None:
    """Phase 10: theo overrides are surfaced inline in the strike grid
    (gold left-border, "manual" pill, override cents in the Theo column),
    NOT a separate panel."""
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
    assert 'id="strike-grid"' in body
    assert "KX-T1" in body
    # Override cents shown in the Theo column (55¢)
    assert "55¢" in body
    # "manual" pill on the row indicates override is active
    assert "manual" in body


def test_dashboard_empty_theo_overrides_renders_strike_grid_anyway() -> None:
    """Phase 10: the dashboard renders cleanly with no overrides; the
    strike grid just shows no rows yet (waiting for runner cycle)."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    body = r.text
    assert 'id="strike-grid"' in body
    assert (
        "no strikes yet" in body
        or "waiting for runner cycle" in body
        or "no events active" in body
    )
