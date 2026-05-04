"""Unit tests for Broadcaster — fan-out, presence, slow-client tolerance."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lipmm.control import Broadcaster, ControlState


class _FakeWebSocket:
    """Minimal WS stand-in for unit tests. Records every event sent."""

    def __init__(self, *, fail_after: int | None = None,
                 hang_after: int | None = None) -> None:
        self.received: list[dict] = []
        self._fail_after = fail_after
        self._hang_after = hang_after
        self.closed = False

    async def send_json(self, event: dict) -> None:
        if self._fail_after is not None and len(self.received) >= self._fail_after:
            raise RuntimeError("simulated send failure")
        if self._hang_after is not None and len(self.received) >= self._hang_after:
            await asyncio.sleep(10.0)  # Forces broadcaster's send timeout
        self.received.append(event)

    async def close(self) -> None:
        self.closed = True


# ── Basic fan-out ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_assigns_tab_id() -> None:
    b = Broadcaster()
    ws = _FakeWebSocket()
    tab_id = await b.register(ws)
    assert isinstance(tab_id, str)
    assert len(tab_id) > 0
    assert b.tab_count == 1
    assert tab_id in b.presence()


@pytest.mark.asyncio
async def test_unregister_removes_connection() -> None:
    b = Broadcaster()
    ws = _FakeWebSocket()
    tab_id = await b.register(ws)
    await b.unregister(tab_id)
    assert b.tab_count == 0
    assert tab_id not in b.presence()


@pytest.mark.asyncio
async def test_broadcast_reaches_all_subscribers() -> None:
    b = Broadcaster()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()
    await b.register(ws1)
    await b.register(ws2)
    # Each register fires a presence event → ws1 sees its own + ws2's
    received_before = (len(ws1.received), len(ws2.received))

    await b.broadcast({"event_type": "test", "payload": "hello"})

    # Both got the broadcast
    assert any(e["event_type"] == "test" for e in ws1.received)
    assert any(e["event_type"] == "test" for e in ws2.received)


@pytest.mark.asyncio
async def test_broadcast_with_no_subscribers_is_noop() -> None:
    b = Broadcaster()
    # Should not raise
    await b.broadcast({"event_type": "test"})


# ── Presence updates ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_is_silent() -> None:
    """register() does NOT broadcast — endpoint sends initial first then
    calls notify_join() to inform other tabs."""
    b = Broadcaster()
    ws1 = _FakeWebSocket()
    await b.register(ws1)
    # No events sent to ws1 (it would normally get notified about itself
    # but that creates ordering issues, so it's silent).
    assert ws1.received == []


@pytest.mark.asyncio
async def test_notify_join_broadcasts_to_others_only() -> None:
    """notify_join sends tab_connected to OTHER tabs but not the joiner."""
    b = Broadcaster()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()
    tab1 = await b.register(ws1)
    tab2 = await b.register(ws2)
    # No events yet on either side
    assert ws1.received == []
    assert ws2.received == []
    # Notify ws2's join → ws1 receives, ws2 doesn't
    await b.notify_join(tab2)
    assert len(ws1.received) == 1
    assert ws1.received[0]["event_type"] == "tab_connected"
    assert ws1.received[0]["tab_id"] == tab2
    assert ws2.received == []


@pytest.mark.asyncio
async def test_unregister_emits_tab_disconnected_to_others() -> None:
    b = Broadcaster()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()
    tab1 = await b.register(ws1)
    await b.register(ws2)
    ws2.received.clear()
    await b.unregister(tab1)
    disconnects = [e for e in ws2.received if e["event_type"] == "tab_disconnected"]
    assert len(disconnects) == 1
    assert disconnects[0]["tab_id"] == tab1
    assert disconnects[0]["total_tabs"] == 1


# ── Slow / dead client tolerance ────────────────────────────────────


@pytest.mark.asyncio
async def test_failed_send_drops_connection() -> None:
    """A WS that errors on send is removed; other subscribers unaffected."""
    b = Broadcaster()
    healthy = _FakeWebSocket()
    # fail_after=0 → broken raises on first send (the test broadcast).
    broken = _FakeWebSocket(fail_after=0)
    await b.register(healthy)
    await b.register(broken)
    await b.broadcast({"event_type": "test"})
    # Broken dropped; healthy survives.
    assert b.tab_count == 1
    assert any(e["event_type"] == "test" for e in healthy.received)


@pytest.mark.asyncio
async def test_slow_send_times_out_and_drops() -> None:
    """A WS that hangs forever on send hits the timeout and gets dropped."""
    b = Broadcaster(send_timeout_s=0.05)
    healthy = _FakeWebSocket()
    # hang_after=0 → first send hangs (register is silent now, so
    # the test broadcast is the slow client's first send).
    slow = _FakeWebSocket(hang_after=0)
    await b.register(healthy)
    await b.register(slow)
    await b.broadcast({"event_type": "test"})
    # Slow client dropped within the timeout
    assert b.tab_count == 1


# ── State change broadcasts ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_state_change_envelope() -> None:
    b = Broadcaster()
    ws = _FakeWebSocket()
    await b.register(ws)
    ws.received.clear()
    await b.broadcast_state_change(
        "pause", {"version": 5, "global_paused": True},
        request_id="req-001", actor="alice",
    )
    msg = ws.received[0]
    assert msg["event_type"] == "state_change"
    assert msg["command_type"] == "pause"
    assert msg["snapshot"]["version"] == 5
    assert msg["request_id"] == "req-001"
    assert msg["actor"] == "alice"


# ── Decision-recorder tee ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_as_decision_recorder_tees_to_logger_and_broadcast() -> None:
    """The recorder writes to the file logger AND broadcasts."""
    b = Broadcaster()
    ws = _FakeWebSocket()
    await b.register(ws)
    ws.received.clear()

    written_records = []
    class _Logger:
        def log(self, rec): written_records.append(rec)
        def close(self): pass

    recorder = b.as_decision_recorder(_Logger())
    rec = {"record_type": "quoting_decision", "ticker": "X", "ts": 0}
    await recorder(rec)

    # File got it
    assert len(written_records) == 1
    assert written_records[0]["ticker"] == "X"
    # Broadcast got it
    decision_events = [e for e in ws.received if e["event_type"] == "decision"]
    assert len(decision_events) == 1
    assert decision_events[0]["record"]["ticker"] == "X"


@pytest.mark.asyncio
async def test_as_decision_recorder_tolerates_logger_failure() -> None:
    """If the file logger raises, the broadcast still happens."""
    b = Broadcaster()
    ws = _FakeWebSocket()
    await b.register(ws)
    ws.received.clear()

    class _BrokenLogger:
        def log(self, rec): raise RuntimeError("disk full")
        def close(self): pass

    recorder = b.as_decision_recorder(_BrokenLogger())
    await recorder({"ticker": "X"})

    # Broadcast happened despite logger failure
    decision_events = [e for e in ws.received if e["event_type"] == "decision"]
    assert len(decision_events) == 1


# ── Heartbeat ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_emits_periodically() -> None:
    state = ControlState()
    b = Broadcaster(heartbeat_interval_s=0.05)
    b.attach_state(state)
    ws = _FakeWebSocket()
    await b.register(ws)
    ws.received.clear()

    await b.start_heartbeat()
    await asyncio.sleep(0.15)  # Wait for ~3 heartbeats
    await b.stop_heartbeat()

    heartbeats = [e for e in ws.received if e["event_type"] == "heartbeat"]
    assert len(heartbeats) >= 2
    # Heartbeat carries the state version
    assert heartbeats[0]["version"] == 0
    assert "ts" in heartbeats[0]
    assert "connected_tabs" in heartbeats[0]


@pytest.mark.asyncio
async def test_stop_heartbeat_idempotent() -> None:
    b = Broadcaster()
    await b.stop_heartbeat()  # Stop without start — no error
    await b.start_heartbeat()
    await b.stop_heartbeat()
    await b.stop_heartbeat()  # Stop twice — no error


# ── close_all ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_all_drops_all_connections() -> None:
    b = Broadcaster()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()
    await b.register(ws1)
    await b.register(ws2)
    await b.close_all()
    assert b.tab_count == 0
    assert ws1.closed is True
    assert ws2.closed is True
