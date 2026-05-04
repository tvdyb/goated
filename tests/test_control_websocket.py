"""Tests for WS /control/stream endpoint + optimistic concurrency."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlState, build_app
from lipmm.control.auth import issue_token


SECRET = "0123456789abcdef0123456789abcdef"


def _client(broadcaster: Broadcaster | None = None) -> tuple[TestClient, dict]:
    state = ControlState()
    b = broadcaster or Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)
    return TestClient(app), {"state": state, "broadcaster": b}


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


# ── WS auth + initial frame ─────────────────────────────────────────


def test_ws_rejects_missing_token() -> None:
    client, _ = _client()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/control/stream") as ws:
            ws.receive_text()


def test_ws_rejects_invalid_token() -> None:
    client, _ = _client()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/control/stream?token=garbage") as ws:
            ws.receive_text()


def test_ws_accepts_valid_token_and_sends_initial_snapshot() -> None:
    client, fx = _client()
    token = issue_token(SECRET, actor="alice")
    with client.websocket_connect(f"/control/stream?token={token}") as ws:
        # First frame is the initial snapshot
        msg = ws.receive_json()
        assert msg["event_type"] == "initial"
        assert msg["actor"] == "alice"
        assert "tab_id" in msg
        assert msg["snapshot"]["version"] == 0
        assert msg["total_tabs"] == 1


def test_ws_503_when_no_broadcaster_wired() -> None:
    """When the app is built without a broadcaster, /control/stream
    refuses connections with a clean close (1011)."""
    state = ControlState()
    app = build_app(state, secret=SECRET)  # no broadcaster
    client = TestClient(app)
    token = issue_token(SECRET)
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/control/stream?token={token}") as ws:
            ws.receive_text()


# ── State change broadcasts ─────────────────────────────────────────


def test_command_triggers_state_change_broadcast() -> None:
    """Issue a /control/pause via HTTP, verify all WS tabs receive a
    state_change event with the new snapshot."""
    client, fx = _client()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream?token={token}") as ws:
        # Drain the initial frame
        ws.receive_json()
        # Issue a pause via HTTP
        r = client.post("/control/pause", json={
            "scope": "global", "request_id": "req-ws-pause-1",
        }, headers=_h())
        assert r.status_code == 200
        # Next WS frame should be the state_change broadcast
        msg = ws.receive_json()
        assert msg["event_type"] == "state_change"
        assert msg["command_type"] == "pause"
        assert msg["snapshot"]["global_paused"] is True


def test_two_tabs_both_receive_state_change() -> None:
    """Multi-tab fan-out: both connected tabs see the same state_change."""
    client, fx = _client()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream?token={token}") as ws1, \
         client.websocket_connect(f"/control/stream?token={token}") as ws2:
        # Drain initial + presence frames on both
        ws1.receive_json()      # initial
        ws1.receive_json()      # tab_connected (for ws2)
        ws2.receive_json()      # initial
        # Trigger state change
        client.post("/control/pause", json={
            "scope": "global", "request_id": "req-multitab-1",
        }, headers=_h())
        # Both tabs see the state_change
        m1 = ws1.receive_json()
        m2 = ws2.receive_json()
        assert m1["event_type"] == "state_change"
        assert m2["event_type"] == "state_change"
        assert m1["snapshot"]["global_paused"] is True
        assert m2["snapshot"]["global_paused"] is True


# ── Presence (multi-tab) ────────────────────────────────────────────


def test_second_tab_connect_broadcasts_presence_to_first() -> None:
    client, _ = _client()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream?token={token}") as ws1:
        # Drain initial
        initial = ws1.receive_json()
        first_tab_id = initial["tab_id"]
        with client.websocket_connect(f"/control/stream?token={token}") as ws2:
            # First tab sees the second's tab_connected event
            msg = ws1.receive_json()
            assert msg["event_type"] == "tab_connected"
            assert msg["total_tabs"] == 2
            # New tab's id is in the presence list and is NOT the first tab's id
            assert msg["tab_id"] != first_tab_id


def test_tab_disconnect_broadcasts_presence_to_remaining() -> None:
    client, _ = _client()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream?token={token}") as ws1:
        ws1.receive_json()  # initial
        with client.websocket_connect(f"/control/stream?token={token}") as ws2:
            ws1.receive_json()      # tab_connected for ws2
            ws2.receive_json()      # initial for ws2
        # ws2 now closed → ws1 should see tab_disconnected
        msg = ws1.receive_json()
        assert msg["event_type"] == "tab_disconnected"
        assert msg["total_tabs"] == 1


# ── Optimistic concurrency (if_version) ────────────────────────────


def test_if_version_match_succeeds() -> None:
    client, fx = _client()
    # Initial state version is 0
    r = client.post("/control/pause", json={
        "scope": "global",
        "request_id": "req-if-match-1",
        "if_version": 0,
    }, headers=_h())
    assert r.status_code == 200
    assert r.json()["new_version"] == 1


def test_if_version_mismatch_returns_409() -> None:
    """Two tabs race: tab A pauses (v0→v1), tab B tries to pause with
    if_version=0 (stale) → 409 with current snapshot."""
    client, fx = _client()
    # Tab A's command — succeeds
    r = client.post("/control/pause", json={
        "scope": "global", "request_id": "req-tabA-1",
    }, headers=_h())
    assert r.status_code == 200
    # Tab B's command — stale if_version → 409
    r = client.post("/control/pause", json={
        "scope": "ticker", "ticker": "KX-T50",
        "request_id": "req-tabB-1",
        "if_version": 0,  # tab B saw v0 before tab A's mutation
    }, headers=_h())
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["error"] == "version_mismatch"
    assert body["client_if_version"] == 0
    assert body["server_version"] == 1
    # Server includes current snapshot so client can re-render
    assert body["snapshot"]["version"] == 1


def test_if_version_omitted_skips_check() -> None:
    """No if_version → last-write-wins semantics, never rejects."""
    client, _ = _client()
    # Mutate a few times to bump version above 0
    for i in range(3):
        client.post("/control/pause", json={
            "scope": "global", "request_id": f"req-bump-{i:03d}",
        }, headers=_h())
        client.post("/control/resume", json={
            "scope": "global", "request_id": f"req-resume-{i:03d}",
        }, headers=_h())
    # Now post without if_version — succeeds despite version drift
    r = client.post("/control/pause", json={
        "scope": "global", "request_id": "req-no-ifv-1",
    }, headers=_h())
    assert r.status_code == 200


# ── State snapshot in command response ─────────────────────────────


def test_state_snapshot_includes_side_locks_phase2_compat() -> None:
    """Sanity: state snapshot still has all Phase 1+2 fields after WS additions."""
    client, _ = _client()
    r = client.get("/control/state", headers=_h())
    assert r.status_code == 200
    body = r.json()
    for key in (
        "version", "kill_state", "global_paused",
        "paused_tickers", "paused_sides", "knob_overrides",
        "side_locks",
    ):
        assert key in body, f"missing key: {key}"
