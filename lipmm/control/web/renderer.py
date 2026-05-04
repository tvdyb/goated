"""Render broadcaster events to HTML partials for htmx-ws OOB swaps.

The Broadcaster speaks JSON: it calls `ws.send_json(event_dict)` on
every registered connection. For the htmx dashboard we wrap each browser
WebSocket in `HtmlWebSocketAdapter` whose `send_json()` translates the
event into HTML via Jinja partials and sends it as text.

Output shape: each event becomes one or more `<div id="..."
hx-swap-oob="true">…</div>` blocks. htmx-ws receives the message and
matches each top-level element by id, swapping it into the DOM. So a
single `state_change` event produces a multi-fragment HTML string that
updates the state panel, knob panel, lock panel, presence pill, and
kill panel atomically.

A small bounded deque per connection keeps the last N decision records
so the feed re-renders with history rather than just the latest one.
"""

from __future__ import annotations

import collections
import json
import logging
from collections import deque
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lipmm.control.web import _paths

logger = logging.getLogger(__name__)

DECISION_FEED_SIZE = 50


_env = Environment(
    loader=FileSystemLoader(_paths.TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _summarize_record(rec: dict[str, Any]) -> str:
    """Pull a one-line description out of a decision-log record. Records
    are heterogeneous; we surface a sensible default and fall back to a
    truncated JSON dump."""
    if "command_type" in rec:
        outcome = "ok" if rec.get("succeeded") else f"FAIL: {rec.get('error', '')}"
        return f"{rec['command_type']} by {rec.get('actor', '?')} — {outcome}"
    if "ticker" in rec:
        return f"{rec.get('record_type', 'decision')} {rec['ticker']}"
    return json.dumps({k: v for k, v in rec.items() if k != "schema_version"})[:160]


def render_initial(
    snapshot: dict[str, Any],
    *,
    presence: list[str],
    total_tabs: int,
    records: list[dict[str, Any]] | None = None,
    runtime: dict[str, Any] | None = None,
    incentives: dict[str, Any] | None = None,
) -> str:
    """Render every panel as a single HTML blob — used both by GET
    /dashboard's first-paint and by the WS `initial` event."""
    records = records or []
    parts = [
        _env.get_template("partials/state_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/kill_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/knob_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/lock_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/theo_overrides_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/manual_order_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/decision_feed.html").render(records=records),
        _env.get_template("partials/presence.html").render(
            presence=presence, total_tabs=total_tabs,
        ),
        _env.get_template("partials/positions_panel.html").render(runtime=runtime),
        _env.get_template("partials/resting_orders_panel.html").render(runtime=runtime),
        _env.get_template("partials/balance_strip.html").render(runtime=runtime),
        _env.get_template("partials/pnl_pill.html").render(runtime=runtime),
        _env.get_template("partials/incentives_panel.html").render(
            incentives=incentives, runtime=runtime,
        ),
    ]
    return "\n".join(parts)


def render_incentives(
    incentives: dict[str, Any] | None,
    runtime: dict[str, Any] | None = None,
) -> str:
    """Re-render the incentives panel on `incentives_snapshot` events.
    `runtime` is optional; when present, rows for tickers we have
    skin in are highlighted."""
    return _env.get_template("partials/incentives_panel.html").render(
        incentives=incentives, runtime=runtime,
    )


def render_state(snapshot: dict[str, Any]) -> str:
    """Re-render every panel that derives from the snapshot. Each panel
    is its own OOB block, so the swap is atomic from htmx's POV."""
    return "\n".join([
        _env.get_template("partials/state_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/kill_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/knob_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/lock_panel.html").render(snapshot=snapshot),
        _env.get_template("partials/theo_overrides_panel.html").render(snapshot=snapshot),
    ])


def render_runtime(runtime: dict[str, Any] | None) -> str:
    """Re-render the four runtime-derived blocks (positions, resting
    orders, balance, PnL pill) on every `runtime_snapshot` event."""
    return "\n".join([
        _env.get_template("partials/positions_panel.html").render(runtime=runtime),
        _env.get_template("partials/resting_orders_panel.html").render(runtime=runtime),
        _env.get_template("partials/balance_strip.html").render(runtime=runtime),
        _env.get_template("partials/pnl_pill.html").render(runtime=runtime),
    ])


def render_presence(presence: list[str], total_tabs: int) -> str:
    return _env.get_template("partials/presence.html").render(
        presence=presence, total_tabs=total_tabs,
    )


def render_decision_feed(records: list[dict[str, Any]]) -> str:
    return _env.get_template("partials/decision_feed.html").render(records=records)


class HtmlWebSocketAdapter:
    """Adapter so a browser WebSocket can be registered with the JSON
    `Broadcaster`. `send_json(event)` translates each event into an HTML
    fragment for htmx-ws to OOB-swap.

    Stateful: maintains a bounded deque of recent decisions so the feed
    panel re-renders with full history every time. Per-tab state is
    fine — the deque is small (50 entries) and stays in this object's
    lifetime.
    """

    def __init__(self, websocket: Any) -> None:
        self._ws = websocket
        self._records: deque[dict[str, Any]] = deque(maxlen=DECISION_FEED_SIZE)
        # Last-known runtime + incentives snapshots so cross-event
        # renders (e.g. incentives panel highlighting tickers we have
        # positions on) have the right context.
        self._last_runtime: dict[str, Any] | None = None
        self._last_incentives: dict[str, Any] | None = None

    async def send_json(self, event: dict[str, Any]) -> None:
        try:
            html = self._render(event)
        except Exception:
            logger.exception("html renderer failed on event=%s", event.get("event_type"))
            return
        if html:
            await self._ws.send_text(html)

    async def send_text(self, text: str) -> None:
        await self._ws.send_text(text)

    async def close(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass

    def push_record(self, record: dict[str, Any]) -> None:
        """Used by the WS endpoint to seed a freshly opened tab with the
        same history we'd otherwise miss."""
        self._records.append(self._normalize(record))

    def _normalize(self, rec: dict[str, Any]) -> dict[str, Any]:
        out = dict(rec)
        out.setdefault("ts", 0.0)
        out["summary"] = _summarize_record(rec)
        return out

    def _render(self, event: dict[str, Any]) -> str:
        et = event.get("event_type")
        if et == "initial":
            return render_initial(
                event["snapshot"],
                presence=event.get("presence", []),
                total_tabs=event.get("total_tabs", 1),
                records=list(self._records),
            )
        if et == "state_change":
            return render_state(event["snapshot"])
        if et in ("tab_connected", "tab_disconnected"):
            return render_presence(
                event.get("presence", []), event.get("total_tabs", 1),
            )
        if et == "decision":
            self._records.append(self._normalize(event.get("record", {})))
            return render_decision_feed(list(self._records))
        if et == "runtime_snapshot":
            self._last_runtime = event.get("snapshot")
            return render_runtime(event.get("snapshot"))
        if et == "incentives_snapshot":
            self._last_incentives = event.get("snapshot")
            return render_incentives(
                event.get("snapshot"), self._last_runtime,
            )
        if et == "heartbeat":
            # Keep the feed silent on heartbeats; presence stays in sync.
            return ""
        # Unknown event — render as a JSON line in the feed for debugging.
        self._records.append({
            "ts": event.get("ts", 0.0),
            "record_type": et or "unknown",
            "summary": json.dumps(event)[:160],
        })
        return render_decision_feed(list(self._records))
