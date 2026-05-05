"""Tests for the Phase 6 runtime panel — GET /control/runtime,
POST /control/cancel_order, and the periodic broadcast loop."""

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
from lipmm.execution import Balance, OrderManager, Position
from lipmm.execution.order_manager import RestingOrder


SECRET = "0123456789abcdef0123456789abcdef"


# ── Stubs ───────────────────────────────────────────────────────────


class _StubExchange:
    """Minimal ExchangeClient impl for runtime tests. Records every cancel
    call. Each method can be patched to raise to exercise partial-failure."""

    def __init__(self) -> None:
        self.positions: list[Position] = []
        self.balance: Balance = Balance(cash_dollars=100.0, portfolio_value_dollars=110.0)
        self.cancel_calls: list[str] = []
        self.cancel_returns: bool = True
        self.list_positions_raises: Exception | None = None
        self.get_balance_raises: Exception | None = None
        self.cancel_raises: Exception | None = None

    async def list_positions(self) -> list[Position]:
        if self.list_positions_raises:
            raise self.list_positions_raises
        return list(self.positions)

    async def get_balance(self) -> Balance:
        if self.get_balance_raises:
            raise self.get_balance_raises
        return self.balance

    async def cancel_order(self, order_id: str) -> bool:
        self.cancel_calls.append(order_id)
        if self.cancel_raises:
            raise self.cancel_raises
        return self.cancel_returns

    # Methods unused by the runtime endpoint — present to satisfy the
    # protocol if it were checked. The tests never call them.
    async def place_order(self, *a, **k): ...
    async def amend_order(self, *a, **k): ...
    async def cancel_orders(self, *a, **k): ...
    async def get_orderbook(self, *a, **k): ...
    async def list_resting_orders(self): return []


def _populated_om() -> OrderManager:
    om = OrderManager()
    om._resting[("KX-A", "bid")] = RestingOrder("oid-1", 42, 10)  # noqa: SLF001
    om._resting[("KX-A", "ask")] = RestingOrder("oid-2", 58, 10)  # noqa: SLF001
    om._resting[("KX-B", "bid")] = RestingOrder("oid-3", 30, 5)   # noqa: SLF001
    return om


def _client(
    *,
    exchange: _StubExchange | None = None,
    order_manager: OrderManager | None = None,
) -> tuple[TestClient, _StubExchange | None, OrderManager | None]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        exchange=exchange, order_manager=order_manager,
    )
    return TestClient(app), exchange, order_manager


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


# ── GET /control/runtime ────────────────────────────────────────────


def test_runtime_503_when_neither_exchange_nor_om() -> None:
    client, _, _ = _client()
    r = client.get("/control/runtime", headers=_h())
    assert r.status_code == 503


def test_runtime_returns_resting_orders_only_without_exchange() -> None:
    om = _populated_om()
    client, _, _ = _client(order_manager=om)
    r = client.get("/control/runtime", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert len(body["resting_orders"]) == 3
    assert body["positions"] == []
    assert body["balance"] is None
    assert body["errors"] == []


def test_runtime_aggregates_positions_resting_balance() -> None:
    ex = _StubExchange()
    ex.positions = [
        Position("KX-A", quantity=5, avg_cost_cents=42,
                 realized_pnl_dollars=1.20, fees_paid_dollars=0.05),
        Position("KX-B", quantity=-3, avg_cost_cents=30,
                 realized_pnl_dollars=-0.50, fees_paid_dollars=0.02),
    ]
    ex.balance = Balance(cash_dollars=98.30, portfolio_value_dollars=99.85)
    om = _populated_om()
    client, _, _ = _client(exchange=ex, order_manager=om)

    r = client.get("/control/runtime", headers=_h())
    assert r.status_code == 200
    body = r.json()

    assert len(body["positions"]) == 2
    assert body["positions"][0]["ticker"] == "KX-A"
    assert body["positions"][0]["quantity"] == 5
    assert len(body["resting_orders"]) == 3
    assert body["balance"]["cash_dollars"] == 98.30
    assert body["balance"]["portfolio_value_dollars"] == 99.85
    # Totals are aggregated from positions
    assert body["total_realized_pnl_dollars"] == pytest.approx(0.70)
    assert body["total_fees_paid_dollars"] == pytest.approx(0.07)
    assert body["errors"] == []


def test_runtime_tolerates_positions_failure() -> None:
    """If list_positions raises, we still return resting_orders + balance
    plus an error message — operator sees what we have."""
    ex = _StubExchange()
    ex.list_positions_raises = RuntimeError("kalshi rate-limited")
    ex.balance = Balance(cash_dollars=10.0, portfolio_value_dollars=10.0)
    om = _populated_om()
    client, _, _ = _client(exchange=ex, order_manager=om)

    r = client.get("/control/runtime", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["positions"] == []
    assert body["balance"] is not None
    assert len(body["resting_orders"]) == 3
    assert any("list_positions" in e for e in body["errors"])


def test_runtime_tolerates_balance_failure() -> None:
    ex = _StubExchange()
    ex.get_balance_raises = RuntimeError("kalshi 503")
    ex.positions = [
        Position("KX-A", 1, 42, 0.0, 0.0),
    ]
    client, _, _ = _client(exchange=ex, order_manager=OrderManager())

    r = client.get("/control/runtime", headers=_h())
    body = r.json()
    assert body["balance"] is None
    assert len(body["positions"]) == 1
    assert any("get_balance" in e for e in body["errors"])


def test_runtime_requires_auth() -> None:
    om = _populated_om()
    client, _, _ = _client(order_manager=om)
    r = client.get("/control/runtime")
    assert r.status_code == 401


# ── POST /control/cancel_order ─────────────────────────────────────


def test_cancel_order_503_without_om_or_exchange() -> None:
    client, _, _ = _client()
    r = client.post("/control/cancel_order", json={
        "order_id": "oid-1", "request_id": "req-cancel-001",
    }, headers=_h())
    assert r.status_code == 503


def test_cancel_order_404_for_unknown_id() -> None:
    om = _populated_om()
    ex = _StubExchange()
    client, _, _ = _client(exchange=ex, order_manager=om)
    r = client.post("/control/cancel_order", json={
        "order_id": "nope", "request_id": "req-cancel-002",
    }, headers=_h())
    assert r.status_code == 404
    # Exchange should not have been touched
    assert ex.cancel_calls == []


def test_cancel_order_calls_exchange_and_drops_state() -> None:
    om = _populated_om()
    ex = _StubExchange()
    client, _, _ = _client(exchange=ex, order_manager=om)

    r = client.post("/control/cancel_order", json={
        "order_id": "oid-2", "request_id": "req-cancel-003",
        "reason": "overpriced",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["cancelled"] is True
    assert body["ticker"] == "KX-A"
    assert body["side"] == "ask"
    assert body["new_version"] == 1
    assert ex.cancel_calls == ["oid-2"]
    # OrderManager forgets the entry
    assert om.find_by_order_id("oid-2") is None
    assert ("KX-A", "ask") not in om.all_resting()
    # The other entries survive
    assert ("KX-A", "bid") in om.all_resting()


def test_cancel_order_500_when_exchange_raises() -> None:
    om = _populated_om()
    ex = _StubExchange()
    ex.cancel_raises = RuntimeError("network timeout")
    client, _, _ = _client(exchange=ex, order_manager=om)

    r = client.post("/control/cancel_order", json={
        "order_id": "oid-1", "request_id": "req-cancel-004",
    }, headers=_h())
    assert r.status_code == 500
    # Order still in OM since cancel didn't confirm
    assert om.find_by_order_id("oid-1") is not None


def test_cancel_order_drops_state_even_if_exchange_returns_false() -> None:
    """If the exchange says 'already gone' (False), our cached view is
    stale anyway — drop it so the next cycle doesn't try to amend a
    ghost."""
    om = _populated_om()
    ex = _StubExchange()
    ex.cancel_returns = False
    client, _, _ = _client(exchange=ex, order_manager=om)

    r = client.post("/control/cancel_order", json={
        "order_id": "oid-3", "request_id": "req-cancel-005",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["cancelled"] is False
    assert om.find_by_order_id("oid-3") is None


def test_cancel_order_if_version_mismatch_returns_409() -> None:
    om = _populated_om()
    ex = _StubExchange()
    client, _, _ = _client(exchange=ex, order_manager=om)
    r = client.post("/control/cancel_order", json={
        "order_id": "oid-1", "request_id": "req-cancel-006",
        "if_version": 99,
    }, headers=_h())
    assert r.status_code == 409


# ── WebSocket runtime push ─────────────────────────────────────────


def test_html_ws_receives_runtime_snapshot_html() -> None:
    """Calling broadcaster.broadcast_runtime should produce an HTML push
    on the html WS containing the runtime panels."""
    state = ControlState()
    b = Broadcaster()
    om = _populated_om()
    ex = _StubExchange()
    ex.positions = [Position("KX-A", 5, 42, 1.50, 0.10)]
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        exchange=ex, order_manager=om,
        mount_dashboard=True,
    )
    client = TestClient(app)
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial frame
        # Synthesize a runtime broadcast directly
        async def push() -> None:
            collect = app.state.collect_runtime
            snap = await collect()
            await b.broadcast_runtime(snap)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(push())
        finally:
            loop.close()
        html = ws.receive_text()
        # Phase 10: runtime data is folded into the status bar (PnL +
        # cash + port pills) and the strike grid (per-row position +
        # resting). A single OOB push updates both.
        assert 'id="status-bar"' in html
        assert 'id="strike-grid"' in html
        assert "KX-A" in html


def test_dashboard_first_paint_includes_runtime_when_wired() -> None:
    state = ControlState()
    b = Broadcaster()
    om = _populated_om()
    ex = _StubExchange()
    ex.positions = [Position("KX-A", 7, 42, 0.0, 0.0)]
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        exchange=ex, order_manager=om,
        mount_dashboard=True,
    )
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    # Phase 10 strike grid replaces the separate positions/resting panels.
    assert 'id="strike-grid"' in body
    assert "KX-A" in body
    # Position rendered inline in the strike row (e.g. "+7 Y")
    assert "+7 Y" in body
    # Resting orders rendered as "B 41¢ × 10" / "A 58¢ × 10" inline
    assert "B 41¢" in body or "A 58¢" in body


def test_dashboard_first_paint_renders_empty_when_unwired() -> None:
    """Without an exchange or order_manager wired, the dashboard still
    renders cleanly — the strike grid just shows 'no strikes yet'."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    assert 'id="strike-grid"' in body
    assert "no strikes yet" in body or "waiting for runner cycle" in body


# ── Periodic loop on ControlServer ─────────────────────────────────


@pytest.mark.asyncio
async def test_periodic_runtime_loop_broadcasts() -> None:
    """ControlServer's runtime loop should fire at the configured
    interval and push runtime snapshots through the broadcaster."""
    om = _populated_om()
    ex = _StubExchange()
    ex.positions = [Position("KX-A", 1, 42, 0.0, 0.0)]
    server = ControlServer(
        ControlState(),
        secret=SECRET,
        order_manager=om, exchange=ex,
        runtime_refresh_s=0.05,
    )
    # Replace the FastAPI server with a stub so we don't actually bind a port.
    captured: list[dict] = []
    orig_broadcast = server.broadcaster.broadcast_runtime

    async def capture(snap: dict) -> None:
        captured.append(snap)
        await orig_broadcast(snap)

    server.broadcaster.broadcast_runtime = capture  # type: ignore[assignment]

    # Manually drive the loop without uvicorn (we just want the periodic task).
    server._runtime_stop = asyncio.Event()  # noqa: SLF001
    task = asyncio.create_task(server._runtime_loop())  # noqa: SLF001
    await asyncio.sleep(0.18)  # ~3 ticks
    server._runtime_stop.set()  # noqa: SLF001
    await asyncio.wait_for(task, timeout=1.0)

    assert len(captured) >= 2
    assert all("positions" in s for s in captured)


@pytest.mark.asyncio
async def test_runtime_loop_can_be_disabled() -> None:
    server = ControlServer(
        ControlState(), secret=SECRET, runtime_refresh_s=None,
    )
    # No collect_runtime wiring + no loop spawned → stop is a no-op
    assert server._runtime_task is None  # noqa: SLF001
