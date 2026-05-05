"""Tests for the multi-event dashboard restructure.

Covers:
  - ControlState.add_event / remove_event / all_events / snapshot field
  - POST /control/add_event endpoint (validation, missing-event, version)
  - POST /control/remove_event endpoint (cancel_resting flag)
  - Renderer's group_strikes_by_event + multi_event_summary helpers
  - Empty-event "ghost" group surfaced when an event has no strikes yet
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlState, build_app
from lipmm.control.auth import issue_token
from lipmm.control.web.renderer import (
    group_strikes_by_event,
    multi_event_summary,
)


SECRET = "0123456789abcdef0123456789abcdef"


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET, actor='alice')}"}


# ── ControlState ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_event_persists_in_state() -> None:
    state = ControlState()
    v = await state.add_event("KXISMPMI-26MAY")
    assert v == 1
    assert "KXISMPMI-26MAY" in state.all_events()


@pytest.mark.asyncio
async def test_add_event_normalizes_to_uppercase() -> None:
    state = ControlState()
    await state.add_event("kxismpmi-26may")
    assert state.all_events() == {"KXISMPMI-26MAY"}


@pytest.mark.asyncio
async def test_add_event_idempotent_but_bumps_version() -> None:
    state = ControlState()
    v1 = await state.add_event("KX-A")
    v2 = await state.add_event("KX-A")
    assert v1 == 1
    assert v2 == 2  # version still bumps so dashboards re-render
    assert state.all_events() == {"KX-A"}


@pytest.mark.asyncio
async def test_remove_event_drops_from_set() -> None:
    state = ControlState()
    await state.add_event("KX-A")
    await state.add_event("KX-B")
    await state.remove_event("KX-A")
    assert state.all_events() == {"KX-B"}


@pytest.mark.asyncio
async def test_remove_event_idempotent() -> None:
    state = ControlState()
    v = await state.remove_event("NEVER-ADDED")
    assert v == 1  # bumps even on no-op
    assert state.all_events() == set()


@pytest.mark.asyncio
async def test_add_event_rejects_empty() -> None:
    state = ControlState()
    with pytest.raises(ValueError):
        await state.add_event("")
    with pytest.raises(ValueError):
        await state.add_event("   ")


@pytest.mark.asyncio
async def test_snapshot_includes_active_events_sorted() -> None:
    state = ControlState()
    await state.add_event("KX-Z")
    await state.add_event("KX-A")
    await state.add_event("KX-M")
    snap = state.snapshot()
    assert snap["active_events"] == ["KX-A", "KX-M", "KX-Z"]


# ── Renderer grouping ─────────────────────────────────────────────


def _strike(ticker: str, **kw: object) -> dict:
    """Minimal joined strike dict for renderer tests."""
    base = {
        "ticker": ticker, "override": None, "lip": None,
    }
    base.update(kw)
    return base


def test_group_strikes_by_event_partitions_by_prefix() -> None:
    strikes = [
        _strike("KX-A-T1"),
        _strike("KX-A-T2"),
        _strike("KX-B-T1"),
    ]
    groups = group_strikes_by_event(strikes)
    assert [g["event_ticker"] for g in groups] == ["KX-A", "KX-B"]
    assert groups[0]["strike_count"] == 2
    assert groups[1]["strike_count"] == 1


def test_group_strikes_by_event_emits_empty_groups_for_active_events() -> None:
    """Just-added events have no strikes until next runner cycle. The
    chip should still appear in the grid so the operator gets immediate
    feedback. group_strikes_by_event emits a 0-strike group entry."""
    strikes = [_strike("KX-A-T1")]
    groups = group_strikes_by_event(strikes, active_events=["KX-A", "KX-NEW"])
    by_ev = {g["event_ticker"]: g for g in groups}
    assert by_ev["KX-A"]["strike_count"] == 1
    assert by_ev["KX-NEW"]["strike_count"] == 0
    assert by_ev["KX-NEW"]["strikes"] == []


def test_multi_event_summary_aggregates_across_groups() -> None:
    strikes = [
        _strike("KX-A-T1", override={"actor": "x"},
                lip={"period_reward_dollars": 100.0}),
        _strike("KX-A-T2", lip={"period_reward_dollars": 50.0}),
        _strike("KX-B-T1"),
    ]
    groups = group_strikes_by_event(strikes)
    summary = multi_event_summary(groups)
    assert summary["event_count"] == 2
    assert summary["strike_count"] == 3
    assert summary["quoting_count"] == 1
    assert summary["lip_total_dollars"] == 150.0
    assert summary["events"] == ["KX-A", "KX-B"]


# ── HTTP endpoints ────────────────────────────────────────────────


def _client_with_validator(validator=None):
    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        event_validator=validator,
    )
    return TestClient(app), state


def test_add_event_endpoint_with_validator_success() -> None:
    seen: list[str] = []
    async def _v(ev: str) -> dict:
        seen.append(ev)
        return {"market_count": 8, "status": "active"}

    client, state = _client_with_validator(_v)
    r = client.post("/control/add_event", json={
        "event_ticker": "KXISMPMI-26MAY",
        "request_id": "req-add-1",
    }, headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert body["event_ticker"] == "KXISMPMI-26MAY"
    assert body["market_count"] == 8
    assert seen == ["KXISMPMI-26MAY"]
    assert state.all_events() == {"KXISMPMI-26MAY"}


def test_add_event_endpoint_rejects_zero_market_event() -> None:
    async def _v(ev: str) -> dict:
        return {"market_count": 0, "status": "settled"}

    client, state = _client_with_validator(_v)
    r = client.post("/control/add_event", json={
        "event_ticker": "KX-DEAD",
        "request_id": "req-add-2",
    }, headers=_h())
    assert r.status_code == 400
    assert "0 tradable markets" in r.text
    assert state.all_events() == set()


def test_add_event_endpoint_propagates_validator_failure() -> None:
    async def _v(ev: str) -> dict:
        raise RuntimeError("kalshi 404")

    client, state = _client_with_validator(_v)
    r = client.post("/control/add_event", json={
        "event_ticker": "KX-NOPE",
        "request_id": "req-add-3",
    }, headers=_h())
    assert r.status_code == 400
    assert "not found" in r.text or "unreachable" in r.text


def test_add_event_endpoint_works_without_validator() -> None:
    """In tests / minimal deploys, no event_validator is wired. The
    endpoint trusts the operator and just adds."""
    client, state = _client_with_validator(None)
    r = client.post("/control/add_event", json={
        "event_ticker": "KX-A",
        "request_id": "req-add-4",
    }, headers=_h())
    assert r.status_code == 200
    assert state.all_events() == {"KX-A"}


def test_remove_event_endpoint_basic() -> None:
    client, state = _client_with_validator(None)
    client.post("/control/add_event", json={
        "event_ticker": "KX-A", "request_id": "req-x",
    }, headers=_h())
    r = client.post("/control/remove_event", json={
        "event_ticker": "KX-A", "request_id": "req-rm-1",
    }, headers=_h())
    assert r.status_code == 200
    assert r.json()["cancelled_orders"] == 0
    assert state.all_events() == set()


def test_remove_event_normalizes_input() -> None:
    """Input is uppercased so 'kxismpmi-26may' matches the stored value."""
    client, state = _client_with_validator(None)
    client.post("/control/add_event", json={
        "event_ticker": "KXISMPMI-26MAY", "request_id": "req-x",
    }, headers=_h())
    r = client.post("/control/remove_event", json={
        "event_ticker": "kxismpmi-26may",
        "request_id": "req-rm-2",
    }, headers=_h())
    assert r.status_code == 200
    assert state.all_events() == set()
