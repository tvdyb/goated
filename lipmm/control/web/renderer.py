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


# ── Phase 10 strike-data join ───────────────────────────────────────


def _ticker_slug(ticker: str) -> str:
    """Sanitize a Kalshi ticker for use as an HTML element id /
    data attribute. Replaces non-alphanumerics with `-`."""
    out = []
    for ch in ticker:
        out.append(ch if ch.isalnum() else "-")
    return "".join(out)


def _ticker_label(ticker: str) -> tuple[str, int | None]:
    """Best-effort human label + threshold from a Kalshi ticker.

    For binary-threshold markets (KXISMPMI-26MAY-51 etc.) the trailing
    integer is the threshold; we render "At least N". Falls back to the
    raw suffix for non-binary markets.
    """
    if "-" not in ticker:
        return ticker, None
    suffix = ticker.rsplit("-", 1)[-1]
    # Strip "T" prefix some series use (e.g. KXSOYBEANMON-26APR3017-T1186.99)
    raw = suffix[1:] if suffix.startswith("T") and len(suffix) > 1 else suffix
    try:
        # Integer thresholds: "At least 51"
        n = int(raw)
        return f"At least {n}", n
    except ValueError:
        try:
            # Float thresholds: leave as raw text, no human label
            float(raw)
            return suffix, None
        except ValueError:
            return suffix, None


def join_strike_data(
    state_snapshot: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    incentives: dict[str, Any] | None,
    orderbooks: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build per-strike views by joining state + runtime + incentives +
    orderbooks. Returns a list of dicts ready to feed `strike_row.html`.

    Price convention (matches Kalshi UI, NOT the comp's mock):

      - `yesC` (chip)   = `best_ask_c`        — what you'd PAY to buy Yes
      - `noC`  (chip)   = 100 - best_bid_c    — what you'd PAY to buy No
      - `chance`        = best_bid_c          — implied probability of Yes
      - `spread`        = best_ask_c - best_bid_c

    Universe of strikes = orderbook tickers (most current). When the
    runner hasn't pushed yet we fall back to runtime+incentive tickers.
    """
    state_snapshot = state_snapshot or {}
    runtime = runtime or {}
    incentives = incentives or {}
    orderbooks = orderbooks or {}

    overrides = {ov["ticker"]: ov for ov in state_snapshot.get("theo_overrides", [])}
    positions = {p["ticker"]: p for p in runtime.get("positions", [])}
    resting: dict[str, list[dict]] = {}
    for r in runtime.get("resting_orders", []):
        resting.setdefault(r["ticker"], []).append(r)
    incs: dict[str, list[dict]] = {}
    for ip in incentives.get("programs", []):
        incs.setdefault(ip["market_ticker"], []).append(ip)
    obs = {ob["ticker"]: ob for ob in orderbooks.get("strikes", [])}

    universe = set(obs) | set(positions) | set(resting) | set(incs) | set(overrides)
    out: list[dict[str, Any]] = []
    for ticker in sorted(universe):
        ob = obs.get(ticker, {})
        best_bid = int(ob.get("best_bid_c", 0))
        best_ask = int(ob.get("best_ask_c", 100))
        label, threshold = _ticker_label(ticker)
        out.append({
            "ticker": ticker,
            "slug": _ticker_slug(ticker),
            "label": label,
            "threshold": threshold,
            "best_bid_c": best_bid,
            "best_ask_c": best_ask,
            "yesC": best_ask,
            "noC": max(0, 100 - best_bid),
            "chance": best_bid,
            "spread": max(0, best_ask - best_bid),
            "yes_levels": ob.get("yes_levels", []),
            "no_levels": ob.get("no_levels", []),
            "ob_present": bool(ob),
            "override": overrides.get(ticker),
            "position": positions.get(ticker),
            "resting": resting.get(ticker, []),
            "lip": (incs.get(ticker) or [None])[0],
        })
    return out


def event_meta_from_strikes(
    strikes: list[dict[str, Any]],
    fallback_event: str | None = None,
) -> dict[str, Any]:
    """Derive event-header metadata from the joined strikes list.

    Picks the event ticker by stripping the trailing strike segment off
    the first ticker (e.g. KXISMPMI-26MAY-51 → KXISMPMI-26MAY). Counts
    `quoting` as strikes with an active theo override (the only thing
    that lifts confidence above the strategy's default skip threshold
    when StubTheoProvider is in use). Sums LIP rewards across strikes.
    """
    if not strikes:
        return {
            "event_ticker": fallback_event or "—",
            "strike_count": 0,
            "quoting_count": 0,
            "lip_total_dollars": 0.0,
        }
    first = strikes[0]["ticker"]
    event_ticker = first.rsplit("-", 1)[0] if "-" in first else first
    quoting = sum(1 for s in strikes if s["override"] is not None)
    lip_total = sum(
        (s["lip"] or {}).get("period_reward_dollars", 0.0) for s in strikes
    )
    return {
        "event_ticker": event_ticker,
        "strike_count": len(strikes),
        "quoting_count": quoting,
        "lip_total_dollars": lip_total,
    }


# ── existing helpers ──────────────────────────────────────────────


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
    orderbooks: dict[str, Any] | None = None,
) -> str:
    """Render the full first-paint HTML — status bar, event header,
    strike grid, decision feed. Joined data per strike; one blob.
    Used both by GET /dashboard and the WS `initial` frame."""
    records = records or []
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    event = event_meta_from_strikes(strikes)
    pnl_total = (runtime or {}).get("total_realized_pnl_dollars", 0.0)
    balance = (runtime or {}).get("balance") or {}
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot, presence=presence, total_tabs=total_tabs,
            pnl_total=pnl_total, balance=balance,
        ),
        _env.get_template("partials/event_header.html").render(event=event),
        _env.get_template("partials/strike_grid.html").render(
            strikes=strikes, event=event,
        ),
        _env.get_template("partials/decision_feed.html").render(records=records),
        _env.get_template("partials/operator_drawer.html").render(snapshot=snapshot),
    ])


def render_state(
    snapshot: dict[str, Any],
    *,
    presence: list[str] | None = None,
    total_tabs: int | None = None,
    runtime: dict[str, Any] | None = None,
    incentives: dict[str, Any] | None = None,
    orderbooks: dict[str, Any] | None = None,
    pnl_total: float = 0.0,
) -> str:
    """Re-render after a `state_change` event. Status bar (kill_state
    lives there) + strike grid (theo overrides change row borders)."""
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    event = event_meta_from_strikes(strikes)
    balance = (runtime or {}).get("balance") or {}
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot,
            presence=presence or [],
            total_tabs=total_tabs or 1,
            pnl_total=pnl_total,
            balance=balance,
        ),
        _env.get_template("partials/event_header.html").render(event=event),
        _env.get_template("partials/strike_grid.html").render(
            strikes=strikes, event=event,
        ),
        # The drawer's tab counts + per-tab content all derive from
        # `state_snapshot`, so re-render it on every state_change.
        _env.get_template("partials/operator_drawer.html").render(
            snapshot=snapshot,
        ),
    ])


def render_runtime(
    runtime: dict[str, Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
    incentives: dict[str, Any] | None = None,
    orderbooks: dict[str, Any] | None = None,
    presence: list[str] | None = None,
    total_tabs: int | None = None,
) -> str:
    """Re-render after a `runtime_snapshot` event. Status bar (PnL/
    cash/port) + strike grid (positions + resting per row)."""
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    event = event_meta_from_strikes(strikes)
    pnl_total = (runtime or {}).get("total_realized_pnl_dollars", 0.0)
    balance = (runtime or {}).get("balance") or {}
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot or {},
            presence=presence or [],
            total_tabs=total_tabs or 1,
            pnl_total=pnl_total,
            balance=balance,
        ),
        _env.get_template("partials/event_header.html").render(event=event),
        _env.get_template("partials/strike_grid.html").render(
            strikes=strikes, event=event,
        ),
    ])


def render_orderbooks(
    orderbooks: dict[str, Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    incentives: dict[str, Any] | None = None,
) -> str:
    """Re-render after an `orderbook_snapshot` event. Just the strike
    grid; status bar isn't affected by orderbook updates."""
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    event = event_meta_from_strikes(strikes)
    return "\n".join([
        _env.get_template("partials/event_header.html").render(event=event),
        _env.get_template("partials/strike_grid.html").render(
            strikes=strikes, event=event,
        ),
    ])


def render_incentives(
    incentives: dict[str, Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    orderbooks: dict[str, Any] | None = None,
) -> str:
    """Re-render after an `incentives_snapshot` event. The grid pulls
    LIP $/period per strike, so we re-render the whole grid."""
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    event = event_meta_from_strikes(strikes)
    return "\n".join([
        _env.get_template("partials/event_header.html").render(event=event),
        _env.get_template("partials/strike_grid.html").render(
            strikes=strikes, event=event,
        ),
    ])


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
        # Last-known snapshots so cross-event renders have the right
        # context. Phase 10: state + runtime + incentives + orderbooks
        # all feed into the joined strike grid; any event re-renders
        # the grid using the most recent value of every input.
        self._last_state: dict[str, Any] | None = None
        self._last_runtime: dict[str, Any] | None = None
        self._last_incentives: dict[str, Any] | None = None
        self._last_orderbooks: dict[str, Any] | None = None
        self._last_presence: list[str] = []
        self._last_total_tabs: int = 1

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
            self._last_state = event.get("snapshot")
            self._last_presence = event.get("presence", [])
            self._last_total_tabs = event.get("total_tabs", 1)
            return render_initial(
                self._last_state or {},
                presence=self._last_presence,
                total_tabs=self._last_total_tabs,
                records=list(self._records),
                runtime=self._last_runtime,
                incentives=self._last_incentives,
                orderbooks=self._last_orderbooks,
            )
        if et == "state_change":
            self._last_state = event.get("snapshot")
            pnl = (self._last_runtime or {}).get(
                "total_realized_pnl_dollars", 0.0,
            )
            return render_state(
                self._last_state or {},
                presence=self._last_presence,
                total_tabs=self._last_total_tabs,
                runtime=self._last_runtime,
                incentives=self._last_incentives,
                orderbooks=self._last_orderbooks,
                pnl_total=pnl,
            )
        if et in ("tab_connected", "tab_disconnected"):
            self._last_presence = event.get("presence", [])
            self._last_total_tabs = event.get("total_tabs", 1)
            # Re-render status bar to refresh the tab count pill.
            pnl = (self._last_runtime or {}).get(
                "total_realized_pnl_dollars", 0.0,
            )
            balance = (self._last_runtime or {}).get("balance") or {}
            return _env.get_template("partials/status_bar.html").render(
                snapshot=self._last_state or {},
                presence=self._last_presence,
                total_tabs=self._last_total_tabs,
                pnl_total=pnl,
                balance=balance,
            )
        if et == "decision":
            self._records.append(self._normalize(event.get("record", {})))
            return render_decision_feed(list(self._records))
        if et == "runtime_snapshot":
            self._last_runtime = event.get("snapshot")
            return render_runtime(
                self._last_runtime,
                snapshot=self._last_state,
                incentives=self._last_incentives,
                orderbooks=self._last_orderbooks,
                presence=self._last_presence,
                total_tabs=self._last_total_tabs,
            )
        if et == "orderbook_snapshot":
            self._last_orderbooks = event.get("snapshot")
            return render_orderbooks(
                self._last_orderbooks,
                snapshot=self._last_state,
                runtime=self._last_runtime,
                incentives=self._last_incentives,
            )
        if et == "incentives_snapshot":
            self._last_incentives = event.get("snapshot")
            return render_incentives(
                self._last_incentives,
                snapshot=self._last_state,
                runtime=self._last_runtime,
                orderbooks=self._last_orderbooks,
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
