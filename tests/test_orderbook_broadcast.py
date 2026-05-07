"""Tests for Phase 10a — per-strike orderbook broadcast.

Coverage:
  - Broadcaster.broadcast_orderbook caches as last_orderbook + emits event
  - GET /control/orderbooks returns the cached snapshot (empty when none)
  - LIPRunner.run_cycle aggregates per-strike orderbook entries and
    emits one broadcast per cycle via the injected broadcaster
  - WS /control/stream/html receives an `orderbook_snapshot` HTML push
    when broadcast_orderbook fires (HTML adapter handles the event type)
  - base.html exposes the design tokens as CSS custom properties
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from lipmm.control import (
    Broadcaster,
    ControlServer,
    ControlState,
    build_app,
)
from lipmm.control.auth import issue_token
from lipmm.execution import OrderManager
from lipmm.execution.base import OrderbookLevels


SECRET = "0123456789abcdef0123456789abcdef"


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


# ── Broadcaster ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_orderbook_caches_last_snapshot() -> None:
    b = Broadcaster()
    assert b.last_orderbook is None
    snap = {"strikes": [{"ticker": "KX-T1", "best_bid_c": 49}], "last_cycle_ts": 1.0}
    await b.broadcast_orderbook(snap)
    assert b.last_orderbook == snap


@pytest.mark.asyncio
async def test_broadcast_orderbook_emits_to_subscribers() -> None:
    b = Broadcaster()

    received: list[dict] = []

    class _Stub:
        async def send_json(self, event: dict) -> None:
            received.append(event)
        async def close(self) -> None: ...

    await b.register(_Stub())
    await b.broadcast_orderbook({"strikes": [], "last_cycle_ts": 0.0})
    assert any(e["event_type"] == "orderbook_snapshot" for e in received)


# ── GET /control/orderbooks ─────────────────────────────────────


def test_get_orderbooks_empty_before_first_broadcast() -> None:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)
    client = TestClient(app)
    r = client.get("/control/orderbooks", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["strikes"] == []
    assert body["last_cycle_ts"] == 0.0


def test_get_orderbooks_returns_cached_after_broadcast() -> None:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)
    client = TestClient(app)

    snap = {
        "strikes": [
            {
                "ticker": "KXISMPMI-26MAY-51",
                "best_bid_c": 49,
                "best_ask_c": 52,
                "yes_levels": [{"price_cents": 49, "size": 5.0}],
                "no_levels": [{"price_cents": 48, "size": 8.0}],
                "ts": 12345.6,
            },
        ],
        "last_cycle_ts": 12345.6,
    }
    asyncio.get_event_loop().run_until_complete(b.broadcast_orderbook(snap))

    r = client.get("/control/orderbooks", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert len(body["strikes"]) == 1
    assert body["strikes"][0]["ticker"] == "KXISMPMI-26MAY-51"
    assert body["strikes"][0]["best_bid_c"] == 49
    assert body["last_cycle_ts"] == 12345.6


def test_get_orderbooks_requires_auth() -> None:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)
    client = TestClient(app)
    r = client.get("/control/orderbooks")
    assert r.status_code == 401


# ── LIPRunner aggregation + broadcast ────────────────────────────


@pytest.mark.asyncio
async def test_runner_aggregates_orderbooks_per_cycle_and_broadcasts() -> None:
    """One cycle, two tickers — broadcaster receives one snapshot with
    both strikes, top-5 levels each side."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult
    from lipmm.execution.base import Balance, Position

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self): pass
        async def shutdown(self): pass
        async def theo(self, ticker):
            return TheoResult(0.5, 1.0, 0.0, "stub")

    class _StubStrategy:
        name = "stub"
        async def warmup(self): pass
        async def shutdown(self): pass
        async def quote(self, *, ticker, theo, orderbook, our_state,
                        now_ts, time_to_settle_s, control_overrides=None):
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason="stub"),
                ask=SideDecision(price=0, size=0, skip=True, reason="stub"),
            )

    class _StubExchange:
        async def get_orderbook(self, ticker):
            # 7 yes-levels descending; 3 no-levels descending
            return OrderbookLevels(
                ticker=ticker,
                yes_levels=[(50, 10.0), (49, 8.0), (48, 6.0), (47, 4.0),
                            (46, 3.0), (45, 2.0), (44, 1.0)],
                no_levels=[(52, 5.0), (53, 3.0), (54, 1.0)],
            )
        async def list_resting_orders(self): return []
        async def list_positions(self): return []
        async def get_balance(self): return Balance(0.0, 0.0)
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_order(self, *a, **k): return True
        async def cancel_orders(self, ids): return {i: True for i in ids}

    class _Source:
        async def list_active_tickers(self, exchange):
            return ["KX-T1", "KX-T2"]

    captured: list[dict] = []

    class _CapturingBroadcaster:
        def __init__(self) -> None:
            self._last = None
        @property
        def last_orderbook(self):
            return self._last
        async def broadcast_orderbook(self, snap):
            captured.append(snap)
            self._last = snap

    b = _CapturingBroadcaster()
    registry = TheoRegistry()
    registry.register(_StubProvider())
    runner = LIPRunner(
        config=RunnerConfig(cycle_seconds=0.05),
        theo_registry=registry,
        strategy=_StubStrategy(),
        order_manager=OrderManager(),
        exchange=_StubExchange(),
        ticker_source=_Source(),
        broadcaster=b,
    )

    await runner._theo.warmup_all()  # noqa: SLF001
    await runner._strategy.warmup()  # noqa: SLF001
    await runner._cycle()  # noqa: SLF001

    assert len(captured) == 1
    snap = captured[0]
    assert "strikes" in snap
    assert "last_cycle_ts" in snap
    assert len(snap["strikes"]) == 2
    # Defensive 50-level cap on yes_levels (the LIP scorer needs full
    # depth to walk down to Target Size; the depth-ladder UI slices to
    # top 5 at render time).
    assert all(len(s["yes_levels"]) <= 50 for s in snap["strikes"])
    # First strike has 7 yes levels in source → all 7 preserved (under cap)
    s1 = snap["strikes"][0]
    assert len(s1["yes_levels"]) == 7
    # And 3 no-levels → all 3 preserved
    assert len(s1["no_levels"]) == 3
    # Best bid/ask present
    assert s1["best_bid_c"] >= 0
    assert s1["best_ask_c"] <= 100
    # Theo payload is piped through for dashboard rendering. The stub
    # provider returns confidence=1.0, source="stub" — runner wraps as
    # a provider-kind payload.
    assert s1["theo"] is not None
    assert s1["theo"]["yes_cents"] == 50.0
    assert s1["theo"]["confidence"] == 1.0
    assert s1["theo"]["source"] == "stub"
    assert s1["theo"]["source_kind"] == "provider"


@pytest.mark.asyncio
async def test_runner_no_broadcast_when_skipped_cycle() -> None:
    """If the cycle is gated (kill or global pause), no orderbook
    broadcast fires — and _cycle_orderbooks stays empty so the next
    real cycle starts fresh."""
    from lipmm.runner import LIPRunner, RunnerConfig
    from lipmm.theo import TheoRegistry, TheoResult

    class _StubProvider:
        series_prefix = "KX"
        async def warmup(self): pass
        async def shutdown(self): pass
        async def theo(self, ticker):
            return TheoResult(0.5, 1.0, 0.0, "stub")

    class _NopStrategy:
        name = "nop"
        async def warmup(self): pass
        async def shutdown(self): pass
        async def quote(self, **k):
            from lipmm.quoting import QuotingDecision, SideDecision
            return QuotingDecision(
                bid=SideDecision(price=0, size=0, skip=True, reason=""),
                ask=SideDecision(price=0, size=0, skip=True, reason=""),
            )

    class _StubEx:
        async def get_orderbook(self, t): return OrderbookLevels(t, [], [])
        async def list_resting_orders(self): return []

    class _Src:
        async def list_active_tickers(self, e): return []

    captured = []
    class _Bcast:
        @property
        def last_orderbook(self): return None
        async def broadcast_orderbook(self, s): captured.append(s)

    state = ControlState()
    await state.kill()  # bot is now KILLED, cycles are skipped

    runner = LIPRunner(
        config=RunnerConfig(),
        theo_registry=TheoRegistry(),
        strategy=_NopStrategy(),
        order_manager=OrderManager(),
        exchange=_StubEx(),
        ticker_source=_Src(),
        control_state=state,
        broadcaster=_Bcast(),
    )
    await runner._cycle()  # noqa: SLF001
    assert captured == []


# ── HTML WebSocket renders the new event ─────────────────────────


def test_html_ws_receives_orderbook_snapshot() -> None:
    """When the broadcaster emits an orderbook_snapshot, the HTML
    adapter does NOT crash and emits something (either an empty fallback
    or whatever the renderer currently dispatches). Concrete UI tests
    land in 10b once the strike grid template exists."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # drain initial frame
        async def push():
            await b.broadcast_orderbook({
                "strikes": [{"ticker": "KX-T1", "best_bid_c": 49, "best_ask_c": 52,
                             "yes_levels": [], "no_levels": [], "ts": 0.0}],
                "last_cycle_ts": 0.0,
            })
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(push())
        finally:
            loop.close()
        # Adapter dispatches "unknown" event types into the decision feed
        # as a JSON-stringified line; we just verify the WS didn't crash.
        html = ws.receive_text()
        assert isinstance(html, str)


# ── base.html tokens ────────────────────────────────────────────


def test_base_html_exposes_design_tokens() -> None:
    """Phase 10 design tokens must be present as CSS custom properties
    in the rendered HTML so partials can use them via var(--*)."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    body = r.text
    # A representative sample of the 23 tokens
    for token in ("--bg-base", "--ink-hi", "--yes:", "--no:", "--info:",
                  "--warn:", "--lip:", "--danger:", "--surface:",
                  "--border:", "--ink-lo:"):
        assert token in body, f"missing token: {token}"
    # Fonts are loaded
    assert "Inter" in body
    assert "JetBrains+Mono" in body
