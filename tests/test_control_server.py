"""Tests for lipmm.control.server — FastAPI endpoints + auth + audit emit.

Uses FastAPI's TestClient against a fresh app per test. Stub kill_handler
counts invocations. Stub decision_recorder captures audit records for
assertion.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from lipmm.control import ControlState, build_app
from lipmm.control.auth import issue_token


SECRET = "0123456789abcdef0123456789abcdef"


class _CapturingLogger:
    """Stand-in for DecisionLogger that captures records to a list."""
    def __init__(self) -> None:
        self.records: list[dict] = []
    def log(self, record: dict) -> None:
        self.records.append(record)
    def close(self) -> None:
        pass


class _StubKillHandler:
    def __init__(self) -> None:
        self.invocations = 0
        self.cancelled_count = 14
    async def __call__(self) -> int:
        self.invocations += 1
        return self.cancelled_count


def _client(state: ControlState | None = None,
            logger: _CapturingLogger | None = None,
            kill: _StubKillHandler | None = None) -> tuple[TestClient, dict]:
    """Build a TestClient + dict of fixtures for assertion."""
    state = state or ControlState()
    logger = logger or _CapturingLogger()
    kill = kill or _StubKillHandler()
    app = build_app(state, decision_logger=logger,  # type: ignore[arg-type]
                    kill_handler=kill, secret=SECRET)
    return TestClient(app), {"state": state, "logger": logger, "kill": kill}


def _auth_headers(actor: str = "operator") -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET, actor=actor)}"}


# ── unprotected endpoints ────────────────────────────────────────────


def test_health_unauthenticated() -> None:
    client, _ = _client()
    r = client.get("/control/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auth_returns_jwt() -> None:
    client, _ = _client()
    r = client.post("/control/auth", json={"secret": SECRET, "actor": "alice"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["actor"] == "alice"
    assert body["expires_in_seconds"] > 0


def test_auth_rejects_wrong_secret() -> None:
    client, _ = _client()
    r = client.post("/control/auth", json={
        "secret": "wrong-secret-also-32-chars-long-x",
        "actor": "alice",
    })
    assert r.status_code == 401


# ── auth required ────────────────────────────────────────────────────


def test_state_requires_auth() -> None:
    client, _ = _client()
    r = client.get("/control/state")
    assert r.status_code == 401


def test_pause_requires_auth() -> None:
    client, _ = _client()
    r = client.post("/control/pause", json={
        "scope": "global", "request_id": "req-12345678",
    })
    assert r.status_code == 401


def test_state_with_auth() -> None:
    client, _ = _client()
    r = client.get("/control/state", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 0
    assert body["kill_state"] == "off"
    assert body["global_paused"] is False


# ── pause / resume ───────────────────────────────────────────────────


def test_pause_global_then_resume() -> None:
    client, fx = _client()
    r = client.post("/control/pause",
                    json={"scope": "global", "request_id": "req-pause-001"},
                    headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["new_version"] == 1
    assert fx["state"].is_global_paused() is True
    r = client.post("/control/resume",
                    json={"scope": "global", "request_id": "req-resume-001"},
                    headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].is_global_paused() is False


def test_pause_ticker() -> None:
    client, fx = _client()
    r = client.post("/control/pause", json={
        "scope": "ticker", "ticker": "KX-T50",
        "request_id": "req-pause-tk-1",
    }, headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].is_ticker_paused("KX-T50") is True


def test_pause_side() -> None:
    client, fx = _client()
    r = client.post("/control/pause", json={
        "scope": "side", "ticker": "KX-T50", "side": "bid",
        "request_id": "req-pause-side-1",
    }, headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].is_side_paused("KX-T50", "bid") is True


def test_pause_validation_rejects_missing_ticker() -> None:
    client, _ = _client()
    r = client.post("/control/pause", json={
        "scope": "ticker", "request_id": "req-bad-1",
    }, headers=_auth_headers())
    assert r.status_code == 422


def test_pause_validation_rejects_missing_side() -> None:
    client, _ = _client()
    r = client.post("/control/pause", json={
        "scope": "side", "ticker": "KX-T50", "request_id": "req-bad-2",
    }, headers=_auth_headers())
    assert r.status_code == 422


# ── kill / arm flow ──────────────────────────────────────────────────


def test_kill_invokes_handler_and_audits() -> None:
    client, fx = _client()
    r = client.post("/control/kill", json={
        "request_id": "req-kill-1",
        "reason": "test scenario",
    }, headers=_auth_headers())
    assert r.status_code == 200
    assert fx["kill"].invocations == 1
    assert fx["state"].is_killed() is True
    # Audit record emitted
    audit = [r for r in fx["logger"].records if r.get("command_type") == "kill"]
    assert len(audit) == 1
    assert audit[0]["succeeded"] is True
    assert audit[0]["side_effect_summary"]["orders_cancelled"] == 14
    assert audit[0]["actor"] == "operator"


def test_resume_global_after_kill_requires_arm_first() -> None:
    client, fx = _client()
    client.post("/control/kill", json={"request_id": "req-kill-001", "reason": ""},
                headers=_auth_headers())
    # Try to resume directly — should 409
    r = client.post("/control/resume",
                    json={"scope": "global", "request_id": "req-resume-001"},
                    headers=_auth_headers())
    assert r.status_code == 409
    # Arm first, then resume
    r = client.post("/control/arm", json={"request_id": "req-arm-001"},
                    headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].is_armed() is True
    r = client.post("/control/resume",
                    json={"scope": "global", "request_id": "req-resume-002"},
                    headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].is_killed() is False
    assert fx["state"].is_global_paused() is False


def test_arm_when_not_killed_returns_409() -> None:
    client, _ = _client()
    r = client.post("/control/arm", json={"request_id": "req-bad-arm-1"},
                    headers=_auth_headers())
    assert r.status_code == 409


# ── knob updates ─────────────────────────────────────────────────────


def test_set_knob_with_valid_value() -> None:
    client, fx = _client()
    r = client.post("/control/set_knob", json={
        "name": "min_theo_confidence", "value": 0.5,
        "request_id": "req-knob-1",
    }, headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].get_knob("min_theo_confidence") == 0.5


def test_set_knob_rejects_unknown_knob() -> None:
    client, _ = _client()
    r = client.post("/control/set_knob", json={
        "name": "not_a_knob", "value": 1.0,
        "request_id": "req-knob-bad-1",
    }, headers=_auth_headers())
    assert r.status_code == 400


def test_set_knob_rejects_out_of_bounds() -> None:
    client, _ = _client()
    r = client.post("/control/set_knob", json={
        "name": "min_theo_confidence", "value": 1.5,
        "request_id": "req-knob-bad-2",
    }, headers=_auth_headers())
    assert r.status_code == 400


def test_clear_knob() -> None:
    client, fx = _client()
    client.post("/control/set_knob", json={
        "name": "min_theo_confidence", "value": 0.3,
        "request_id": "req-set-001",
    }, headers=_auth_headers())
    r = client.post("/control/clear_knob", json={
        "name": "min_theo_confidence", "request_id": "req-clr-001",
    }, headers=_auth_headers())
    assert r.status_code == 200
    assert fx["state"].get_knob("min_theo_confidence") is None


# ── audit emission ───────────────────────────────────────────────────


def test_every_command_emits_audit_record() -> None:
    """Successful commands write one operator_command record each."""
    client, fx = _client()
    client.post("/control/pause", json={
        "scope": "global", "request_id": "req-12345001",
    }, headers=_auth_headers())
    client.post("/control/resume", json={
        "scope": "global", "request_id": "req-12345002",
    }, headers=_auth_headers())
    client.post("/control/set_knob", json={
        "name": "min_theo_confidence", "value": 0.4, "request_id": "req-12345003",
    }, headers=_auth_headers())
    audits = [r for r in fx["logger"].records
              if r.get("record_type") == "operator_command"]
    assert len(audits) == 3
    cmd_types = [a["command_type"] for a in audits]
    assert cmd_types == ["pause", "resume", "set_knob"]
    # All succeeded
    for a in audits:
        assert a["succeeded"] is True


def test_failed_command_also_emits_audit() -> None:
    """Operator misclicks (out-of-bounds knob) leave a 'succeeded: false'
    audit trail. Operators can post-mortem from logs."""
    client, fx = _client()
    client.post("/control/set_knob", json={
        "name": "min_theo_confidence", "value": 99.0, "request_id": "req-bad-001",
    }, headers=_auth_headers())
    audits = [r for r in fx["logger"].records
              if r.get("command_type") == "set_knob"]
    assert len(audits) == 1
    assert audits[0]["succeeded"] is False
    assert audits[0]["error"] is not None


# ── strategy swap (deferred to Phase 2) ──────────────────────────────


def test_swap_strategy_returns_501() -> None:
    client, _ = _client()
    r = client.post("/control/swap_strategy", json={
        "strategy_name": "sticky-defense", "request_id": "req-swap",
    }, headers=_auth_headers())
    assert r.status_code == 501
