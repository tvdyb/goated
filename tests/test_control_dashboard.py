"""Tests for the Phase 4 htmx + Jinja dashboard surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlState, build_app
from lipmm.control.auth import issue_token


SECRET = "0123456789abcdef0123456789abcdef"


def _client_with_dashboard() -> tuple[TestClient, Broadcaster, ControlState]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    return TestClient(app), b, state


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


# ── Page rendering ──────────────────────────────────────────────────


def test_root_redirects_to_dashboard() -> None:
    client, _, _ = _client_with_dashboard()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/dashboard"


def test_login_page_renders() -> None:
    client, _, _ = _client_with_dashboard()
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text
    assert "<form" in body
    assert 'id="secret"' in body
    assert "/static/dashboard.js" in body


def test_dashboard_page_renders_panel_shell() -> None:
    client, _, _ = _client_with_dashboard()
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    # Each panel anchor present so OOB swaps from the WS land somewhere
    for anchor in (
        'id="state-panel"',
        'id="kill-panel"',
        'id="knob-panel"',
        'id="lock-panel"',
        'id="manual-order-panel"',
        'id="decision-feed"',
        'id="presence-pill"',
        'id="ws-mount"',
    ):
        assert anchor in body, f"missing anchor: {anchor}"


def test_dashboard_renders_initial_snapshot() -> None:
    """First-paint should show v0 + kill_state=off so there's no flash
    of empty UI before the WS opens."""
    client, _, _ = _client_with_dashboard()
    r = client.get("/dashboard")
    body = r.text
    assert "v0" in body
    assert "off" in body  # kill state pill


def test_static_js_served() -> None:
    client, _, _ = _client_with_dashboard()
    r = client.get("/static/dashboard.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript") or \
           "javascript" in r.headers["content-type"]
    assert "configRequest" in r.text
    assert "ws-connect" in r.text


# ── Opt-in behavior ─────────────────────────────────────────────────


def test_dashboard_not_mounted_by_default() -> None:
    """Existing test suite shouldn't see /dashboard appear."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b)  # mount_dashboard omitted
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 404
    r = client.get("/login")
    assert r.status_code == 404


def test_mount_dashboard_requires_broadcaster() -> None:
    state = ControlState()
    with pytest.raises(ValueError, match="broadcaster"):
        build_app(state, secret=SECRET, mount_dashboard=True)


# ── HTML WebSocket ──────────────────────────────────────────────────


def test_html_ws_rejects_missing_token() -> None:
    client, _, _ = _client_with_dashboard()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/control/stream/html") as ws:
            ws.receive_text()


def test_html_ws_rejects_invalid_token() -> None:
    client, _, _ = _client_with_dashboard()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/control/stream/html?token=bad") as ws:
            ws.receive_text()


def test_html_ws_initial_frame_contains_panels() -> None:
    client, _, state = _client_with_dashboard()
    token = issue_token(SECRET, actor="alice")
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        html = ws.receive_text()
        # All OOB panel containers present in the first frame
        for anchor in (
            'id="state-panel"',
            'id="kill-panel"',
            'id="knob-panel"',
            'id="lock-panel"',
            'id="manual-order-panel"',
            'id="decision-feed"',
            'id="presence-pill"',
        ):
            assert anchor in html, f"missing anchor: {anchor}"
        assert "v0" in html


def test_html_ws_pushes_partial_after_pause() -> None:
    """A POST /control/pause should push an HTML state-change to the
    open html WS so the dashboard can OOB-swap without a full reload."""
    client, _, _ = _client_with_dashboard()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial
        r = client.post("/control/pause", json={
            "scope": "global", "request_id": "req-dash-pause-1",
        }, headers=_h())
        assert r.status_code == 200
        html = ws.receive_text()
        # The state_change render covers state/kill/knob/lock panels
        assert 'id="state-panel"' in html
        assert 'id="kill-panel"' in html
        assert "v1" in html
        assert "paused" in html


def test_html_ws_pushes_decision_feed_update() -> None:
    """A decision broadcast should produce a feed-only HTML push."""
    client, broadcaster, _ = _client_with_dashboard()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial
        # Synthesize a decision broadcast
        import asyncio
        async def push():
            await broadcaster.broadcast_decision({
                "record_type": "quoting_decision",
                "ticker": "KX-TEST",
                "ts": 1234.5,
            })
        asyncio.get_event_loop().run_until_complete(push())
        html = ws.receive_text()
        assert 'id="decision-feed"' in html
        assert "KX-TEST" in html


def test_html_ws_presence_updates_with_second_tab() -> None:
    client, _, _ = _client_with_dashboard()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws1:
        ws1.receive_text()  # initial
        with client.websocket_connect(f"/control/stream/html?token={token}") as ws2:
            ws2.receive_text()  # initial for ws2
            html = ws1.receive_text()
            assert 'id="presence-pill"' in html
            assert "2 tab" in html
