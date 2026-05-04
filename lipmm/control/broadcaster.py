"""WebSocket broadcaster for control-plane state push.

A `Broadcaster` is the fan-out layer between server-side state changes
and connected dashboard tabs. Connections are registered with a unique
tab_id (so the dashboard can show "N tabs connected" badges) and receive
a stream of structured events:

  - state_change: every ControlState mutation rebroadcasts the new snapshot
  - decision:     decision-log records as the runner emits them
  - operator_event: command ack with audit fields (matches DecisionLogger
                    record shape so analyst tooling can be unified)
  - tab_connected / tab_disconnected: presence updates
  - heartbeat:    periodic timestamp + version (so dashboards detect stale
                  connections and surface "bot disconnected" warnings)

Design choices:

  - **Per-connection error tolerance**: if a send fails (slow client,
    closed socket), that connection is dropped without affecting the
    rest. No bounded queues / backpressure in v1 — accept that very
    slow clients miss events; the next state_change re-syncs them.
  - **Locks scoped tightly**: `_connections` mutations hold the async
    lock, but sends happen outside the lock so a slow client can't
    block other broadcasts.
  - **No persistence**: events are ephemeral. Dashboards reconnecting
    after a network blip get a fresh snapshot and pick up live events
    going forward, but don't see what they missed.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

    from lipmm.control.state import ControlState

logger = logging.getLogger(__name__)


# Send timeout per connection. Slow client → connection dropped, not
# stalled broadcast.
DEFAULT_SEND_TIMEOUT_S = 1.0
DEFAULT_HEARTBEAT_INTERVAL_S = 10.0


class Broadcaster:
    """Async fan-out manager for connected control-plane WebSocket tabs."""

    def __init__(
        self,
        *,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        send_timeout_s: float = DEFAULT_SEND_TIMEOUT_S,
    ) -> None:
        self._connections: dict[str, "WebSocket"] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_interval_s = heartbeat_interval_s
        self._send_timeout_s = send_timeout_s
        self._state: "ControlState | None" = None

    def attach_state(self, state: "ControlState") -> None:
        """Optional: wire a ControlState reference so heartbeats include
        the current state version. Without this, heartbeats omit version."""
        self._state = state

    @property
    def tab_count(self) -> int:
        return len(self._connections)

    def presence(self) -> list[str]:
        """Snapshot of current tab_ids — sorted for determinism."""
        return sorted(self._connections.keys())

    async def register(self, websocket: "WebSocket") -> str:
        """Add this WS to the broadcast pool and assign a tab_id.

        Silent: does NOT broadcast tab_connected. The endpoint should
        immediately send an `initial` frame directly to the new tab and
        THEN call `notify_join(tab_id)` to inform the other tabs.

        This split avoids two ordering issues:
          - The new tab would otherwise receive tab_connected before
            initial (confusing).
          - total_tabs count would race the registration vs broadcast.
        """
        tab_id = secrets.token_urlsafe(8)
        async with self._lock:
            self._connections[tab_id] = websocket
        return tab_id

    async def notify_join(self, joining_tab_id: str) -> None:
        """Broadcast `tab_connected` to every tab EXCEPT the one joining.
        Call after `register(...)` and after sending the new tab its
        initial frame."""
        event = {
            "event_type": "tab_connected",
            "tab_id": joining_tab_id,
            "total_tabs": self.tab_count,
            "presence": self.presence(),
            "ts": time.time(),
        }
        await self._broadcast_event_excluding(joining_tab_id, event)

    async def unregister(self, tab_id: str) -> None:
        """Remove a connection. Broadcasts tab_disconnected to remaining
        tabs. Idempotent."""
        async with self._lock:
            removed = self._connections.pop(tab_id, None)
        if removed is None:
            return
        await self._broadcast_event({
            "event_type": "tab_disconnected",
            "tab_id": tab_id,
            "total_tabs": self.tab_count,
            "presence": self.presence(),
            "ts": time.time(),
        })

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Public broadcast entry point. Caller adds `event_type` and
        whatever payload fields are appropriate."""
        await self._broadcast_event(event)

    async def broadcast_state_change(
        self, command_type: str, snapshot: dict[str, Any],
        *, request_id: str | None = None, actor: str | None = None,
    ) -> None:
        """Convenience: emit a state_change event with the new snapshot
        plus the command that caused it. Wired into command handlers
        after every successful mutation."""
        await self._broadcast_event({
            "event_type": "state_change",
            "command_type": command_type,
            "snapshot": snapshot,
            "request_id": request_id,
            "actor": actor,
            "ts": time.time(),
        })

    async def broadcast_incentives(self, snapshot: dict[str, Any]) -> None:
        """Push an incentive-programs snapshot as `incentives_snapshot`.
        The renderer's HTML adapter recognizes this event type and
        OOB-swaps the incentives panel."""
        await self._broadcast_event({
            "event_type": "incentives_snapshot",
            "snapshot": snapshot,
            "ts": time.time(),
        })

    async def broadcast_runtime(self, snapshot: dict[str, Any]) -> None:
        """Push a runtime snapshot (positions + resting orders + balance)
        as a `runtime_snapshot` event. Pre-shaped for the htmx renderer
        to OOB-swap the positions / resting-orders / balance panels."""
        await self._broadcast_event({
            "event_type": "runtime_snapshot",
            "snapshot": snapshot,
            "ts": time.time(),
        })

    async def broadcast_decision(self, record: dict[str, Any]) -> None:
        """Wrap a decision-log record in an event envelope and push to
        all subscribers. The record itself is the same shape the
        DecisionLogger writes — frontends can render it directly."""
        await self._broadcast_event({
            "event_type": "decision",
            "record": record,
            "ts": time.time(),
        })

    def as_decision_recorder(self, file_logger: Any | None = None) -> Callable[[dict], Awaitable[None]]:
        """Build a decision_recorder that does both: (a) writes to the
        file logger if provided, (b) broadcasts to all WS tabs.

        Use as the runner's decision_recorder hook:

            recorder = broadcaster.as_decision_recorder(file_logger=logger)
            runner = LIPRunner(..., decision_recorder=recorder)

        Either side failing doesn't break the other — file write errors
        are logged and the broadcast still happens; broadcast errors
        don't stop the file write."""
        async def recorder(record: dict) -> None:
            if file_logger is not None:
                try:
                    file_logger.log(record)
                except Exception as exc:
                    logger.warning("file_logger.log raised: %s", exc)
            try:
                await self.broadcast_decision(record)
            except Exception as exc:
                logger.warning("broadcast_decision raised: %s", exc)
        return recorder

    async def start_heartbeat(self) -> None:
        """Spawn the periodic heartbeat task. Idempotent."""
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None

    async def close_all(self) -> None:
        """Close every connection. Used on server shutdown."""
        async with self._lock:
            connections = list(self._connections.items())
            self._connections.clear()
        for tab_id, ws in connections:
            try:
                await ws.close()
            except Exception:
                pass

    # ── internal ─────────────────────────────────────────────────────

    async def _broadcast_event(self, event: dict[str, Any]) -> None:
        """Send to every connection. Drop connections that error."""
        await self._broadcast_event_excluding(None, event)

    async def _broadcast_event_excluding(
        self, exclude_tab_id: str | None, event: dict[str, Any],
    ) -> None:
        """Send to every connection except the one with `exclude_tab_id`."""
        async with self._lock:
            connections = [
                (tid, ws) for tid, ws in self._connections.items()
                if tid != exclude_tab_id
            ]
        if not connections:
            return
        dead: list[str] = []
        for tab_id, ws in connections:
            try:
                await asyncio.wait_for(
                    ws.send_json(event), timeout=self._send_timeout_s,
                )
            except Exception as exc:
                logger.info(
                    "broadcaster: dropping tab_id=%s due to send error: %s",
                    tab_id, exc,
                )
                dead.append(tab_id)
        if dead:
            async with self._lock:
                for tab_id in dead:
                    self._connections.pop(tab_id, None)

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval_s)
                await self._broadcast_event({
                    "event_type": "heartbeat",
                    "ts": time.time(),
                    "version": (
                        self._state.version if self._state is not None else None
                    ),
                    "connected_tabs": self.tab_count,
                })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("heartbeat loop crashed: %s", exc)
