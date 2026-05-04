"""Phase 2 server tests — manual_order, lock_side, unlock_side, locks endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from lipmm.control import ControlState, build_app
from lipmm.control.auth import issue_token
from lipmm.execution import (
    Balance, ExchangeClient, Order, OrderbookLevels, OrderManager,
    PlaceOrderRequest, Position,
)
from lipmm.risk import MaxNotionalPerSideGate, RiskRegistry


SECRET = "0123456789abcdef0123456789abcdef"


class _CapturingLogger:
    def __init__(self) -> None:
        self.records: list[dict] = []
    def log(self, record: dict) -> None:
        self.records.append(record)
    def close(self) -> None:
        pass


class _MockExchange:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.next_id = 1

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        oid = f"o-{self.next_id}"
        self.next_id += 1
        self.orders[oid] = Order(
            order_id=oid, ticker=request.ticker, action=request.action,
            side=request.side, limit_price_cents=request.limit_price_cents,
            remaining_count=request.count, status="resting",
        )
        return self.orders[oid]

    async def amend_order(self, order_id, **kwargs):
        return self.orders.get(order_id)

    async def cancel_order(self, order_id: str) -> bool:
        return self.orders.pop(order_id, None) is not None

    async def cancel_orders(self, order_ids):
        return {oid: await self.cancel_order(oid) for oid in order_ids}

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        return OrderbookLevels(ticker=ticker, yes_levels=[], no_levels=[])

    async def list_resting_orders(self) -> list[Order]:
        return list(self.orders.values())

    async def list_positions(self) -> list[Position]:
        return []

    async def get_balance(self) -> Balance:
        return Balance(cash_dollars=100.0, portfolio_value_dollars=0.0)


def _client(
    *,
    risk_registry: RiskRegistry | None = None,
    om: OrderManager | None = None,
    ex: _MockExchange | None = None,
) -> tuple[TestClient, dict]:
    state = ControlState()
    logger = _CapturingLogger()
    om = om or OrderManager()
    ex = ex or _MockExchange()
    app = build_app(
        state, decision_logger=logger, secret=SECRET,  # type: ignore[arg-type]
        order_manager=om, exchange=ex, risk_registry=risk_registry,
    )
    return TestClient(app), {
        "state": state, "logger": logger, "om": om, "ex": ex,
    }


def _client_no_om() -> tuple[TestClient, dict]:
    """Server built without order_manager/exchange — manual orders should 503."""
    state = ControlState()
    logger = _CapturingLogger()
    app = build_app(state, decision_logger=logger, secret=SECRET)  # type: ignore[arg-type]
    return TestClient(app), {"state": state, "logger": logger}


def _h(actor: str = "operator") -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET, actor=actor)}"}


# ── manual_order endpoint ────────────────────────────────────────────


def test_manual_order_happy_path() -> None:
    client, fx = _client()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "request_id": "req-mo-001",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["succeeded"] is True
    assert body["risk_vetoed"] is False
    assert body["action"] == "place_new"
    assert body["price_cents"] == 44
    assert body["size"] == 10
    assert body["lock_applied"] is False
    # Order landed on exchange
    assert len(fx["ex"].orders) == 1


def test_manual_order_with_lock_after() -> None:
    client, fx = _client()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "lock_after": True,
        "request_id": "req-mo-lock-1",
    }, headers=_h())
    assert r.status_code == 200
    assert r.json()["lock_applied"] is True
    assert fx["state"].is_side_locked("KX-T50", "bid") is True


def test_manual_order_lock_with_ttl() -> None:
    client, fx = _client()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "lock_after": True, "lock_auto_unlock_seconds": 60,
        "request_id": "req-mo-ttl-1",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["lock_applied"] is True
    assert body["lock_auto_unlock_at"] is not None
    lock = fx["state"].get_side_lock("KX-T50", "bid")
    assert lock.auto_unlock_at is not None


def test_manual_order_risk_vetoed() -> None:
    risk = RiskRegistry([MaxNotionalPerSideGate(max_dollars=0.50)])
    client, fx = _client(risk_registry=risk)
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 50,  # $5 notional > $0.50 cap
        "lock_after": True,  # would lock if it succeeded
        "request_id": "req-veto-1",
    }, headers=_h())
    assert r.status_code == 200  # 200 — endpoint succeeded; veto in body
    body = r.json()
    assert body["succeeded"] is False
    assert body["risk_vetoed"] is True
    assert body["action"] == "skipped"
    assert body["lock_applied"] is False  # no lock on veto
    assert len(body["risk_audit"]) >= 1
    assert len(fx["ex"].orders) == 0


def test_manual_order_when_killed_returns_409() -> None:
    client, fx = _client()
    # Kill the bot first
    client.post("/control/kill", json={
        "request_id": "req-kill-1", "reason": "test",
    }, headers=_h())
    # Now try a manual order
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "request_id": "req-mo-killed-1",
    }, headers=_h())
    assert r.status_code == 409
    assert "KILLED" in r.json()["detail"]


def test_manual_order_503_when_no_om_wired() -> None:
    """Server built without order_manager/exchange returns 503."""
    client, _ = _client_no_om()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "request_id": "req-mo-no-om-1",
    }, headers=_h())
    assert r.status_code == 503


def test_manual_order_validation_invalid_price() -> None:
    client, _ = _client()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 100,  # > 99
        "request_id": "req-mo-bad-px-1",
    }, headers=_h())
    assert r.status_code == 422


def test_manual_order_requires_auth() -> None:
    client, _ = _client()
    r = client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "request_id": "req-no-auth-1",
    })
    assert r.status_code == 401


# ── lock_side / unlock_side / locks endpoints ───────────────────────


def test_lock_side_endpoint() -> None:
    client, fx = _client()
    r = client.post("/control/lock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "reason": "manual hold",
        "request_id": "req-lock-001",
    }, headers=_h())
    assert r.status_code == 200
    assert fx["state"].is_side_locked("KX-T50", "bid") is True


def test_lock_side_with_ttl() -> None:
    client, fx = _client()
    r = client.post("/control/lock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "auto_unlock_seconds": 3600,
        "request_id": "req-lock-ttl-1",
    }, headers=_h())
    assert r.status_code == 200
    lock = fx["state"].get_side_lock("KX-T50", "bid")
    assert lock.auto_unlock_at is not None


def test_unlock_side_endpoint() -> None:
    client, fx = _client()
    client.post("/control/lock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "request_id": "req-lock-1",
    }, headers=_h())
    r = client.post("/control/unlock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "request_id": "req-unlock-1",
    }, headers=_h())
    assert r.status_code == 200
    assert fx["state"].is_side_locked("KX-T50", "bid") is False


def test_locks_endpoint() -> None:
    client, _ = _client()
    client.post("/control/lock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "reason": "test reason",
        "request_id": "req-lock-list-1",
    }, headers=_h())
    r = client.get("/control/locks", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert len(body["locks"]) == 1
    entry = body["locks"][0]
    assert entry["ticker"] == "KX-T50"
    assert entry["side"] == "bid"
    assert entry["reason"] == "test reason"


def test_locks_endpoint_empty() -> None:
    client, _ = _client()
    r = client.get("/control/locks", headers=_h())
    assert r.status_code == 200
    assert r.json()["locks"] == []


# ── audit emission ────────────────────────────────────────────────


def test_manual_order_emits_audit() -> None:
    client, fx = _client()
    client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 44,
        "request_id": "req-audit-mo-1",
    }, headers=_h())
    audits = [r for r in fx["logger"].records
              if r.get("command_type") == "manual_order"]
    assert len(audits) == 1
    assert audits[0]["succeeded"] is True
    assert audits[0]["side_effect_summary"]["action"] == "place_new"
    assert audits[0]["side_effect_summary"]["order_id"] is not None


def test_risk_vetoed_manual_order_audit_includes_risk_info() -> None:
    risk = RiskRegistry([MaxNotionalPerSideGate(max_dollars=0.50)])
    client, fx = _client(risk_registry=risk)
    client.post("/control/manual_order", json={
        "ticker": "KX-T50", "side": "bid",
        "count": 10, "limit_price_cents": 50,
        "request_id": "req-audit-veto-1",
    }, headers=_h())
    audits = [r for r in fx["logger"].records
              if r.get("command_type") == "manual_order"]
    assert len(audits) == 1
    assert audits[0]["succeeded"] is False
    summary = audits[0]["side_effect_summary"]
    assert summary["risk_vetoed"] is True
    assert len(summary["risk_audit"]) >= 1


def test_lock_side_emits_audit() -> None:
    client, fx = _client()
    client.post("/control/lock_side", json={
        "ticker": "KX-T50", "side": "bid",
        "reason": "test",
        "request_id": "req-audit-lock-1",
    }, headers=_h())
    audits = [r for r in fx["logger"].records
              if r.get("command_type") == "lock_side"]
    assert len(audits) == 1
    assert audits[0]["succeeded"] is True
