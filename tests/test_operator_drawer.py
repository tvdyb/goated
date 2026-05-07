"""Tests for Phase 10c — operator drawer + expanded strike row.

Coverage:
  - GET /dashboard renders the operator drawer + FAB shell.
  - All 5 tabs (theos / pauses / knobs / locks / manual) are present.
  - Drawer reflects current state: theo override count, knob override
    count, side-lock count.
  - Active tab persisted in localStorage (verified by checking that
    the drawer contains the data-tab attributes JS uses).
  - Expanded strike row contains: depth ladder skeleton, resting order
    list with cancel button, LIP detail block, theo override form.
  - Yes/No price chips have data attributes for chip→manual seeding.
  - State change re-renders the drawer (kill_state into drawer text).
  - Old partials are gone (no template loading errors when nothing
    references them).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlState, build_app
from lipmm.control.auth import issue_token
from lipmm.execution import OrderManager
from lipmm.execution.base import Balance, Position
from lipmm.execution.order_manager import RestingOrder


SECRET = "0123456789abcdef0123456789abcdef"


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


def _client_full() -> tuple[TestClient, ControlState, Broadcaster]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    return TestClient(app), state, b


# ── Operator drawer shell ───────────────────────────────────────────


def test_dashboard_includes_operator_drawer_anchor() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    assert 'id="operator-drawer"' in body


def test_drawer_contains_all_five_tabs() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    for key in ("theos", "pauses", "knobs", "locks", "manual"):
        assert f'data-tab="{key}"' in body, f"missing tab: {key}"
        assert f'data-tab-panel="{key}"' in body, f"missing panel: {key}"


def test_drawer_fab_present_with_toggle_action() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    assert 'data-action="toggle-drawer"' in body
    # FAB has the "Operator" label
    assert "Operator" in body


def test_drawer_theos_tab_lists_active_overrides() -> None:
    client, state, _ = _client_full()
    asyncio.get_event_loop().run_until_complete(state.set_theo_override(
        "KX-T1", 0.55, reason="quick consensus est", actor="alice",
    ))
    body = client.get("/dashboard").text
    # Override appears in the theos tab
    assert "quick consensus est" in body
    assert "alice" in body
    # Active count appears next to "Theos" tab label
    assert ">1<" in body or "1\n" in body  # count pill


def test_drawer_pauses_tab_shows_running_state_by_default() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    assert "Running" in body  # Global state when not paused


def test_drawer_pauses_tab_shows_paused_state_after_global_pause() -> None:
    client, state, _ = _client_full()
    asyncio.get_event_loop().run_until_complete(state.pause_global())
    body = client.get("/dashboard").text
    assert "Paused" in body
    assert "Resume all" in body


def test_drawer_knobs_tab_lists_all_knob_names() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    for knob in ("min_theo_confidence", "theo_tolerance_c",
                 "max_distance_from_best", "dollars_per_side"):
        assert knob in body


def test_drawer_locks_tab_form_present() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    # Locks form has lock_side button text
    assert "Lock side" in body


def test_drawer_manual_tab_form_complete() -> None:
    client, _, _ = _client_full()
    body = client.get("/dashboard").text
    # Form fields by name
    for name in ("ticker", "side", "count", "limit_price_cents", "lock_after"):
        assert f'name="{name}"' in body
    # ⌘+Enter hint
    assert "⌘" in body or "Cmd" in body or "Submit" in body


# ── Expanded strike row ─────────────────────────────────────────────


def test_expanded_strike_row_includes_depth_ladder_resting_lip_theo() -> None:
    """Expanded panel for a strike with all 4 sub-blocks present."""
    client, state, b = _client_full()
    # Seed orderbook + override + a fake position via stub exchange
    asyncio.get_event_loop().run_until_complete(b.broadcast_orderbook({
        "strikes": [{
            "ticker": "KX-T1",
            "best_bid_c": 49, "best_ask_c": 52,
            "yes_levels": [{"price_cents": 49, "size": 5.0},
                          {"price_cents": 48, "size": 8.0}],
            "no_levels": [{"price_cents": 48, "size": 3.0}],
        }],
        "last_cycle_ts": 0.0,
    }))
    asyncio.get_event_loop().run_until_complete(state.set_theo_override(
        "KX-T1", 0.50, reason="centered on consensus",
    ))
    body = client.get("/dashboard").text
    # Hidden by default, but present in DOM
    assert 'id="expand-KX-T1"' in body
    # Sub-block headings
    assert "Order book" in body
    assert "Our resting" in body
    assert "LIP incentive" in body
    # Inline theo form (override exists → "update theo" button text)
    assert "update theo" in body


def test_expanded_strike_row_renders_theo_form_for_unfilled_strike() -> None:
    """Strike without override → "override theo" button."""
    client, _, b = _client_full()
    asyncio.get_event_loop().run_until_complete(b.broadcast_orderbook({
        "strikes": [{
            "ticker": "KX-T2", "best_bid_c": 30, "best_ask_c": 32,
            "yes_levels": [], "no_levels": [],
        }],
        "last_cycle_ts": 0.0,
    }))
    body = client.get("/dashboard").text
    assert "override theo" in body  # button text when no override


def test_expanded_strike_row_resting_has_cancel_button() -> None:
    """Per-resting cancel button on the expanded row's resting list."""
    state = ControlState()
    b = Broadcaster()
    om = OrderManager()
    om._resting[("KX-T1", "bid")] = RestingOrder("oid-A", 49, 5)  # noqa: SLF001

    class _StubEx:
        async def list_positions(self): return []
        async def get_balance(self): return Balance(0.0, 0.0)
        async def cancel_order(self, oid): return True
        async def list_resting_orders(self): return []
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_orders(self, ids): return {}

    app = build_app(
        state, secret=SECRET, broadcaster=b,
        order_manager=om, exchange=_StubEx(),
        mount_dashboard=True,
    )
    client = TestClient(app)
    body = client.get("/dashboard").text
    # Cancel button with the right payload
    assert 'data-call="/control/cancel_order"' in body
    assert '"order_id":"oid-A"' in body


def test_strike_row_yes_no_chips_have_seed_attributes() -> None:
    """Phase 10c: clicking a chip seeds the manual-order form."""
    client, _, b = _client_full()
    asyncio.get_event_loop().run_until_complete(b.broadcast_orderbook({
        "strikes": [{
            "ticker": "KX-T1", "best_bid_c": 49, "best_ask_c": 52,
            "yes_levels": [], "no_levels": [],
        }],
        "last_cycle_ts": 0.0,
    }))
    body = client.get("/dashboard").text
    assert 'data-action="seed-manual"' in body
    assert 'data-side="yes"' in body
    assert 'data-side="no"' in body
    assert 'data-ticker="KX-T1"' in body


# ── State_change re-renders the drawer ──────────────────────────────


def test_state_change_pushes_drawer_html_via_ws() -> None:
    """Setting a theo override should produce a re-rendered drawer in
    the WS push."""
    client, _, _ = _client_full()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial frame
        r = client.post("/control/set_theo_override", json={
            "ticker": "KX-T1", "yes_cents": 55, "confidence": 1.0,
            "reason": "alpha test", "request_id": "req-drawer-1",
        }, headers=_h())
        assert r.status_code == 200
        html = ws.receive_text()
        assert 'id="operator-drawer"' in html
        # The override appears in the theos tab
        assert "alpha test" in html


# ── Old partials are gone ───────────────────────────────────────────


def test_old_partials_are_deleted() -> None:
    """Sanity: 12 stale Phase 4–8 partials are gone from disk."""
    base = Path(__file__).parent.parent / "lipmm/control/web/templates/partials"
    deleted = [
        "state_panel.html", "kill_panel.html", "knob_panel.html",
        "lock_panel.html", "manual_order_panel.html",
        "theo_overrides_panel.html", "positions_panel.html",
        "resting_orders_panel.html", "balance_strip.html",
        "pnl_pill.html", "presence.html", "incentives_panel.html",
    ]
    for fname in deleted:
        assert not (base / fname).exists(), f"{fname} should have been deleted"


def test_only_phase10_partials_remain() -> None:
    base = Path(__file__).parent.parent / "lipmm/control/web/templates/partials"
    expected = {
        "decision_feed.html",
        "event_header.html",
        "events_strip.html",  # multi-event: chips + add button
        "operator_drawer.html",
        "status_bar.html",
        "strike_grid.html",
        "strike_row.html",
        "tab_knobs.html",
        "tab_locks.html",
        "tab_manual.html",
        "tab_pauses.html",
        "tab_theos.html",
        # Wave 2 dashboard parity tabs (PnL grid, earnings histogram,
        # fill markout). Each has an outer shell that HTMX-fetches an
        # _inner partial from the matching /control/* endpoint.
        "tab_earnings.html",
        "tab_earnings_inner.html",
        "tab_markout.html",
        "tab_markout_inner.html",
        "tab_pnl.html",
        "tab_pnl_inner.html",
    }
    actual = {f.name for f in base.iterdir() if f.suffix == ".html"}
    assert actual == expected, f"unexpected partials: {actual ^ expected}"
