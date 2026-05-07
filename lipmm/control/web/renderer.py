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
from lipmm.incentives import compute_strike_score

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
    # Per-(ticker, side) lock map. Used by the resting-orders panel to
    # render a "lift lock" affordance after the operator cancels an order
    # (the cancel endpoint auto-locks so the runner doesn't immediately
    # re-place).
    locks: dict[tuple[str, str], dict] = {}
    for entry in state_snapshot.get("side_locks", []) or []:
        try:
            locks[(entry["ticker"], entry["side"])] = entry
        except (KeyError, TypeError):
            continue
    positions = {p["ticker"]: p for p in runtime.get("positions", [])}
    resting: dict[str, list[dict]] = {}
    for r in runtime.get("resting_orders", []):
        resting.setdefault(r["ticker"], []).append(r)
    incs: dict[str, list[dict]] = {}
    for ip in incentives.get("programs", []):
        incs.setdefault(ip["market_ticker"], []).append(ip)
    obs = {ob["ticker"]: ob for ob in orderbooks.get("strikes", [])}

    # Strike universe = strikes the bot has skin in OR is actively
    # tracking. Incentives are an ATTRIBUTE attached to a strike, not
    # a reason to add a strike (otherwise we'd render every LIP-active
    # ticker on Kalshi as a "strike", flooding the grid).
    # Strike universe = strikes the bot has skin in OR is actively
    # tracking. Incentives are an ATTRIBUTE attached to a strike, not
    # a reason to add a strike (otherwise we'd render every LIP-active
    # ticker on Kalshi as a "strike", flooding the grid).
    universe = (
        set(obs) | set(positions) | set(resting) | set(overrides)
        | {ticker for (ticker, _side) in locks}
    )
    out: list[dict[str, Any]] = []
    for ticker in sorted(universe):
        ob = obs.get(ticker, {})
        best_bid = int(ob.get("best_bid_c", 0))
        best_ask = int(ob.get("best_ask_c", 100))
        label, threshold = _ticker_label(ticker)
        ticker_resting = resting.get(ticker, [])
        # Per-strike LIP score — only meaningful when we have an
        # orderbook to score against. Without orderbook, total_score
        # would be 0 and the share calculation degenerate.
        lip_score = None
        ob_present = bool(ob)
        # Use the LIP program's discount factor (per Kalshi's formula)
        # if there's an active program on this ticker. Falls back to
        # the soy-bot default decay_ticks=5 for tickers without a
        # program (where the score is informational anyway).
        ticker_lip = (incs.get(ticker) or [None])[0]
        df: float | None = None
        target: float | None = None
        period_duration_s: float = 0.0
        if ticker_lip:
            if ticker_lip.get("discount_factor_bps") is not None:
                try:
                    df = float(ticker_lip["discount_factor_bps"]) / 10000.0
                except (TypeError, ValueError):
                    df = None
            if ticker_lip.get("target_size_contracts") is not None:
                try:
                    target = float(ticker_lip["target_size_contracts"])
                except (TypeError, ValueError):
                    target = None
            try:
                period_duration_s = max(
                    0.0,
                    float(ticker_lip.get("end_date_ts") or 0)
                    - float(ticker_lip.get("start_date_ts") or 0),
                )
            except (TypeError, ValueError):
                period_duration_s = 0.0
        if ob_present:
            try:
                lip_score = compute_strike_score(
                    our_orders=ticker_resting,
                    yes_levels=ob.get("yes_levels", []),
                    no_levels=ob.get("no_levels", []),
                    best_bid_c=best_bid,
                    best_ask_c=best_ask,
                    discount_factor=df,
                    target_size_contracts=target,
                )
            except Exception:
                lip_score = None
        # Provider/override theo snapshot piped from the runner via the
        # orderbook broadcast. None when no theo was computed this cycle
        # (e.g. confidence-gate skip). Source-kind distinguishes
        # override vs provider for color coding in the strike row.
        provider_theo = ob.get("theo")

        # LIP queue headroom per side: how many cents we'd need to move
        # our quote to reach the qualifying threshold. Useful for the
        # operator to see at a glance whether we're in the LIP pool.
        # Derived from the StrikeScore's per-side ref/threshold prices.
        yes_cutoff_distance_c = None
        no_cutoff_distance_c = None
        if lip_score is not None:
            ref_yes = getattr(lip_score, "yes_ref_price_c", None)
            # threshold is on the StrikeScore; we expose it via a helper.
            # Fall back to ref price when threshold isn't tracked.
            if ref_yes is not None:
                # Distance from best_bid to the cutoff. Positive = below
                # cutoff (need to raise bid); 0 = at cutoff.
                yes_cutoff_distance_c = max(0, ref_yes - best_bid)
            ref_no = getattr(lip_score, "no_ref_price_c", None)
            if ref_no is not None:
                # No-side ref is in no-cents; convert our ask side
                # equivalence: our yes-ask equates to no-bid at 100-ask.
                our_no_bid_c = max(0, 100 - best_ask)
                no_cutoff_distance_c = max(0, ref_no - our_no_bid_c)

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
            "ob_present": ob_present,
            "override": overrides.get(ticker),
            "provider_theo": provider_theo,
            "yes_cutoff_distance_c": yes_cutoff_distance_c,
            "no_cutoff_distance_c": no_cutoff_distance_c,
            "position": positions.get(ticker),
            "resting": ticker_resting,
            "lip": ticker_lip,
            "lip_score": lip_score,
            "lip_period_duration_s": period_duration_s,
            "side_lock_bid": locks.get((ticker, "bid")),
            "side_lock_ask": locks.get((ticker, "ask")),
            "has_subcent_ticks": bool(ob.get("has_subcent_ticks", False)),
            # Per-event + per-strike knob overrides (operator-set,
            # layered between global and individual strikes). The
            # template surfaces them in the expanded strike row so the
            # operator can see what's active per-scope.
            "event_knob_overrides": (
                state_snapshot.get("event_knob_overrides") or {}
            ).get(_event_ticker_of(ticker), {}),
            "strike_knob_overrides": (
                state_snapshot.get("strike_knob_overrides") or {}
            ).get(ticker, {}),
        })
    return out


def _event_ticker_of(strike_ticker: str) -> str:
    """KXISMPMI-26MAY-51 → KXISMPMI-26MAY. Falls back to the input
    when there's no '-'."""
    return strike_ticker.rsplit("-", 1)[0] if "-" in strike_ticker else strike_ticker


def _stats_for_strikes(
    strikes: list[dict[str, Any]], event_ticker: str,
) -> dict[str, Any]:
    quoting = sum(1 for s in strikes if s["override"] is not None)
    lip_total = sum(
        (s["lip"] or {}).get("period_reward_dollars", 0.0) for s in strikes
    )
    # Latest LIP end_date across the event's strikes — used as the
    # "time left until this event/program ends" countdown on the event
    # header. Falls back to 0 (= unknown) when no strike has a program.
    end_ts_max = 0.0
    for s in strikes:
        lip = s.get("lip") or {}
        ed = lip.get("end_date_ts") or 0.0
        if ed and ed > end_ts_max:
            end_ts_max = float(ed)
    # Hourly / daily / per-minute LIP rate aggregated across this
    # event's strikes — sum of share × reward × {3600, 86400, 60} /
    # period_duration_s. Strikes with no LIP score / no period
    # contribute 0.
    hourly = 0.0
    daily = 0.0
    per_minute = 0.0
    projected_period = 0.0
    for s in strikes:
        ls = s.get("lip_score")
        lip = s.get("lip") or {}
        period_s = float(s.get("lip_period_duration_s") or 0)
        if ls is None or not period_s:
            continue
        reward = float(lip.get("period_reward_dollars") or 0)
        if reward <= 0:
            continue
        share = float(getattr(ls, "pool_share", 0) or 0)
        full = share * reward
        projected_period += full
        per_minute += full * 60.0 / period_s
        hourly += full * 3600.0 / period_s
        daily += full * 86400.0 / period_s
    return {
        "event_ticker": event_ticker,
        "strike_count": len(strikes),
        "quoting_count": quoting,
        "lip_total_dollars": lip_total,
        "end_ts_max": end_ts_max,
        "lip_rate_per_minute": per_minute,
        "lip_rate_hourly": hourly,
        "lip_rate_daily": daily,
        "lip_projected_period": projected_period,
    }


def event_meta_from_strikes(
    strikes: list[dict[str, Any]],
    fallback_event: str | None = None,
) -> dict[str, Any]:
    """Derive a SINGLE-event-header summary (legacy single-event view).

    Picks the event ticker from the first strike's prefix. Sums across
    all strikes. For multi-event grids, prefer
    `group_strikes_by_event` + `multi_event_summary` instead.
    """
    if not strikes:
        return {
            "event_ticker": fallback_event or "—",
            "strike_count": 0,
            "quoting_count": 0,
            "lip_total_dollars": 0.0,
        }
    event_ticker = _event_ticker_of(strikes[0]["ticker"])
    return _stats_for_strikes(strikes, event_ticker)


def group_strikes_by_event(
    strikes: list[dict[str, Any]],
    *,
    active_events: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Group joined strike dicts by their event prefix.

    Returns: ordered list of `{event_ticker, strikes, strike_count,
    quoting_count, lip_total_dollars}`, sorted by event_ticker.

    `active_events`: when provided, also emits empty groups for events
    that have no strikes yet (e.g. just-added events whose markets
    haven't been broadcast). Operator sees the chip in the strip
    immediately rather than nothing until the next runner cycle.
    """
    by_event: dict[str, list[dict[str, Any]]] = {}
    for s in strikes:
        ev = _event_ticker_of(s["ticker"])
        by_event.setdefault(ev, []).append(s)
    # Add empty entries for active events with no strikes yet
    for ev in (active_events or []):
        by_event.setdefault(ev, [])
    out: list[dict[str, Any]] = []
    for ev in sorted(by_event):
        group = by_event[ev]
        stats = _stats_for_strikes(group, ev)
        out.append({**stats, "strikes": group})
    return out


def multi_event_summary(
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Top-level header summary across all event groups."""
    return {
        "event_count": len(groups),
        "strike_count": sum(g["strike_count"] for g in groups),
        "quoting_count": sum(g["quoting_count"] for g in groups),
        "lip_total_dollars": sum(g["lip_total_dollars"] for g in groups),
        "events": [g["event_ticker"] for g in groups],
        # Aggregated LIP earning rate across every active strike. Lets
        # the operator see at a glance "I'm earning $X/min, $Y/hour"
        # in real time. Computed from per-snapshot pool share × period
        # reward, normalized to time units.
        "lip_rate_per_minute": sum(
            g.get("lip_rate_per_minute", 0.0) for g in groups
        ),
        "lip_rate_hourly": sum(
            g.get("lip_rate_hourly", 0.0) for g in groups
        ),
        "lip_rate_daily": sum(
            g.get("lip_rate_daily", 0.0) for g in groups
        ),
        "lip_projected_period": sum(
            g.get("lip_projected_period", 0.0) for g in groups
        ),
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


def _build_grid_context(
    snapshot: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    incentives: dict[str, Any] | None,
    orderbooks: dict[str, Any] | None,
) -> dict[str, Any]:
    """Common precompute for every render path: joined strikes, grouped
    by event, plus the top-level summary."""
    strikes = join_strike_data(snapshot, runtime, incentives, orderbooks)
    active_events = (snapshot or {}).get("active_events") or []
    groups = group_strikes_by_event(strikes, active_events=active_events)
    summary = multi_event_summary(groups)
    return {
        "strikes": strikes,
        "groups": groups,
        "summary": summary,
        # legacy single-event metadata (first group / fallback) for any
        # template that hasn't been migrated yet
        "event": event_meta_from_strikes(strikes),
    }


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
    ctx = _build_grid_context(snapshot, runtime, incentives, orderbooks)
    pnl_total = (runtime or {}).get("total_realized_pnl_dollars", 0.0)
    balance = (runtime or {}).get("balance") or {}
    rate_limit = (runtime or {}).get("rate_limit")
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot, presence=presence, total_tabs=total_tabs,
            pnl_total=pnl_total, balance=balance, rate_limit=rate_limit,
        ),
        _env.get_template("partials/event_header.html").render(
            event=ctx["event"], summary=ctx["summary"], groups=ctx["groups"],
        ),
        _env.get_template("partials/strike_grid.html").render(
            strikes=ctx["strikes"], event=ctx["event"],
            groups=ctx["groups"], summary=ctx["summary"],
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
    ctx = _build_grid_context(snapshot, runtime, incentives, orderbooks)
    balance = (runtime or {}).get("balance") or {}
    rate_limit = (runtime or {}).get("rate_limit")
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot,
            presence=presence or [],
            total_tabs=total_tabs or 1,
            pnl_total=pnl_total,
            balance=balance,
            rate_limit=rate_limit,
        ),
        _env.get_template("partials/event_header.html").render(
            event=ctx["event"], summary=ctx["summary"], groups=ctx["groups"],
        ),
        _env.get_template("partials/strike_grid.html").render(
            strikes=ctx["strikes"], event=ctx["event"],
            groups=ctx["groups"], summary=ctx["summary"],
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
    ctx = _build_grid_context(snapshot, runtime, incentives, orderbooks)
    pnl_total = (runtime or {}).get("total_realized_pnl_dollars", 0.0)
    balance = (runtime or {}).get("balance") or {}
    rate_limit = (runtime or {}).get("rate_limit")
    return "\n".join([
        _env.get_template("partials/status_bar.html").render(
            snapshot=snapshot or {},
            presence=presence or [],
            total_tabs=total_tabs or 1,
            pnl_total=pnl_total,
            balance=balance,
            rate_limit=rate_limit,
        ),
        _env.get_template("partials/event_header.html").render(
            event=ctx["event"], summary=ctx["summary"], groups=ctx["groups"],
        ),
        _env.get_template("partials/strike_grid.html").render(
            strikes=ctx["strikes"], event=ctx["event"],
            groups=ctx["groups"], summary=ctx["summary"],
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
    ctx = _build_grid_context(snapshot, runtime, incentives, orderbooks)
    return "\n".join([
        _env.get_template("partials/event_header.html").render(
            event=ctx["event"], summary=ctx["summary"], groups=ctx["groups"],
        ),
        _env.get_template("partials/strike_grid.html").render(
            strikes=ctx["strikes"], event=ctx["event"],
            groups=ctx["groups"], summary=ctx["summary"],
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
    ctx = _build_grid_context(snapshot, runtime, incentives, orderbooks)
    return "\n".join([
        _env.get_template("partials/event_header.html").render(
            event=ctx["event"], summary=ctx["summary"], groups=ctx["groups"],
        ),
        _env.get_template("partials/strike_grid.html").render(
            strikes=ctx["strikes"], event=ctx["event"],
            groups=ctx["groups"], summary=ctx["summary"],
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
            rate_limit = (self._last_runtime or {}).get("rate_limit")
            return _env.get_template("partials/status_bar.html").render(
                snapshot=self._last_state or {},
                presence=self._last_presence,
                total_tabs=self._last_total_tabs,
                pnl_total=pnl,
                balance=balance,
                rate_limit=rate_limit,
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
