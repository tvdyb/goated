"""Tests for Phase 10b — strike grid + status bar.

Coverage of the renderer's join logic + the new template anchors:

  - join_strike_data unions tickers across orderbooks/positions/
    resting/incentives/overrides
  - Per-strike convention: yesC = best_ask, noC = 100 - best_bid,
    chance = best_bid (matches Kalshi UI)
  - _ticker_label parses "At least N" from binary-threshold tickers,
    falls back to suffix for non-binary
  - event_meta_from_strikes derives event ticker, counts, LIP total
  - render_initial / render_state / render_runtime / render_orderbooks /
    render_incentives all emit the expected anchors
  - Strike row tints by position sign + left-borders by state cue
  - Empty-state rendering (no strikes, no runtime, no incentives)
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlState, build_app
from lipmm.control.auth import issue_token
from lipmm.control.web.renderer import (
    _ticker_label,
    _ticker_slug,
    event_meta_from_strikes,
    join_strike_data,
    render_initial,
    render_orderbooks,
    render_runtime,
    render_state,
)


SECRET = "0123456789abcdef0123456789abcdef"


# ── Helpers ─────────────────────────────────────────────────────────


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


# ── _ticker_label / _ticker_slug ────────────────────────────────────


def test_ticker_label_binary_threshold() -> None:
    assert _ticker_label("KXISMPMI-26MAY-51") == ("At least 51", 51)


def test_ticker_label_t_prefix_threshold() -> None:
    """Some series prefix the threshold with 'T' (e.g. KXSOYBEANMON)."""
    label, n = _ticker_label("KXSOYBEANMON-26APR3017-T1186")
    assert n == 1186
    assert "1186" in label


def test_ticker_label_non_integer_suffix() -> None:
    label, n = _ticker_label("KXSOMETHING-26MAY-T1186.99")
    assert n is None
    assert label == "T1186.99"


def test_ticker_label_no_dash() -> None:
    assert _ticker_label("PLAIN") == ("PLAIN", None)


def test_ticker_slug_sanitizes() -> None:
    assert _ticker_slug("KX-T1.5") == "KX-T1-5"
    assert _ticker_slug("KX_TEST") == "KX-TEST"


# ── join_strike_data ────────────────────────────────────────────────


def test_join_universe_unions_all_sources() -> None:
    """Every strike that appears in ANY source is in the output."""
    state = {"theo_overrides": [{"ticker": "KX-OVERRIDE-ONLY"}]}
    runtime = {
        "positions": [{"ticker": "KX-POS-ONLY", "quantity": 1, "avg_cost_cents": 50}],
        "resting_orders": [{"ticker": "KX-RESTING-ONLY", "side": "bid", "price_cents": 49, "size": 1}],
    }
    incentives = {"programs": [{"market_ticker": "KX-LIP-ONLY", "period_reward_dollars": 1.0}]}
    orderbooks = {"strikes": [{"ticker": "KX-OB-ONLY", "best_bid_c": 5, "best_ask_c": 6,
                               "yes_levels": [], "no_levels": []}]}
    strikes = join_strike_data(state, runtime, incentives, orderbooks)
    tickers = {s["ticker"] for s in strikes}
    assert tickers == {
        "KX-OVERRIDE-ONLY", "KX-POS-ONLY", "KX-RESTING-ONLY",
        "KX-LIP-ONLY", "KX-OB-ONLY",
    }


def test_join_yes_no_chance_convention_matches_kalshi_ui() -> None:
    """yesC = best_ask (buy-Yes price), noC = 100-best_bid, chance = best_bid."""
    orderbooks = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 49, "best_ask_c": 50,
        "yes_levels": [], "no_levels": [],
    }]}
    strikes = join_strike_data({}, {}, {}, orderbooks)
    s = strikes[0]
    assert s["chance"] == 49      # best_bid
    assert s["yesC"] == 50        # best_ask
    assert s["noC"] == 51         # 100 - best_bid
    assert s["spread"] == 1


def test_join_handles_missing_orderbook() -> None:
    """When no orderbook for a ticker, fields default to safe values."""
    runtime = {"positions": [{"ticker": "KX-LONELY", "quantity": 1, "avg_cost_cents": 50}]}
    strikes = join_strike_data({}, runtime, {}, {})
    s = strikes[0]
    assert s["best_bid_c"] == 0
    assert s["best_ask_c"] == 100
    assert s["ob_present"] is False


def test_join_attaches_override_position_resting_lip() -> None:
    state = {"theo_overrides": [{"ticker": "KX-T1", "yes_cents": 55, "actor": "alice"}]}
    runtime = {
        "positions": [{"ticker": "KX-T1", "quantity": 5, "avg_cost_cents": 49}],
        "resting_orders": [
            {"ticker": "KX-T1", "side": "bid", "order_id": "o1", "price_cents": 48, "size": 5},
            {"ticker": "KX-T1", "side": "ask", "order_id": "o2", "price_cents": 51, "size": 5},
            {"ticker": "KX-OTHER", "side": "bid", "order_id": "o3", "price_cents": 30, "size": 1},
        ],
    }
    incentives = {"programs": [
        {"market_ticker": "KX-T1", "period_reward_dollars": 125.0,
         "incentive_type": "liquidity"},
    ]}
    strikes = join_strike_data(state, runtime, incentives, {})
    by = {s["ticker"]: s for s in strikes}
    s1 = by["KX-T1"]
    assert s1["override"]["yes_cents"] == 55
    assert s1["position"]["quantity"] == 5
    assert len(s1["resting"]) == 2
    assert s1["lip"]["period_reward_dollars"] == 125.0


def test_join_sorts_by_ticker() -> None:
    """Stable order makes the rendered grid deterministic."""
    runtime = {"positions": [
        {"ticker": "KX-Z", "quantity": 1, "avg_cost_cents": 50},
        {"ticker": "KX-A", "quantity": 1, "avg_cost_cents": 50},
        {"ticker": "KX-M", "quantity": 1, "avg_cost_cents": 50},
    ]}
    strikes = join_strike_data({}, runtime, {}, {})
    assert [s["ticker"] for s in strikes] == ["KX-A", "KX-M", "KX-Z"]


# ── event_meta_from_strikes ─────────────────────────────────────────


def test_event_meta_derives_event_ticker_from_first_strike() -> None:
    strikes = [
        {"ticker": "KXISMPMI-26MAY-49", "override": None,
         "lip": {"period_reward_dollars": 125.0}},
        {"ticker": "KXISMPMI-26MAY-50", "override": None,
         "lip": {"period_reward_dollars": 125.0}},
    ]
    meta = event_meta_from_strikes(strikes)
    assert meta["event_ticker"] == "KXISMPMI-26MAY"
    assert meta["strike_count"] == 2
    assert meta["lip_total_dollars"] == 250.0


def test_event_meta_counts_quoting_as_strikes_with_override() -> None:
    strikes = [
        {"ticker": "KX-T1", "override": {"yes_cents": 50}, "lip": None},
        {"ticker": "KX-T2", "override": None, "lip": None},
        {"ticker": "KX-T3", "override": {"yes_cents": 30}, "lip": None},
    ]
    meta = event_meta_from_strikes(strikes)
    assert meta["quoting_count"] == 2


def test_event_meta_empty_strikes_safe() -> None:
    meta = event_meta_from_strikes([])
    assert meta["strike_count"] == 0
    assert meta["quoting_count"] == 0
    assert meta["lip_total_dollars"] == 0.0


def test_event_meta_fallback_event_when_no_strikes() -> None:
    meta = event_meta_from_strikes([], fallback_event="KX-FALLBACK")
    assert meta["event_ticker"] == "KX-FALLBACK"


# ── render_initial / render_state / render_runtime / etc. ───────────


def test_render_initial_emits_all_zone_anchors() -> None:
    html = render_initial(
        {"version": 0, "kill_state": "off"},
        presence=[],
        total_tabs=1,
        records=[],
        runtime=None,
        incentives=None,
        orderbooks=None,
    )
    for anchor in ('id="status-bar"', 'id="event-header"',
                   'id="strike-grid"', 'id="decision-feed"',
                   'id="presence-pill"', 'id="pnl-pill"'):
        assert anchor in html, f"missing anchor: {anchor}"


def test_render_state_includes_status_bar_and_grid() -> None:
    html = render_state({"version": 5, "kill_state": "off"}, total_tabs=2)
    assert 'id="status-bar"' in html
    assert 'id="strike-grid"' in html
    assert "v5" in html


def test_render_runtime_renders_grid_with_positions() -> None:
    runtime = {
        "positions": [{"ticker": "KX-T1", "quantity": 7, "avg_cost_cents": 49}],
        "resting_orders": [],
        "balance": {"cash_dollars": 100.0, "portfolio_value_dollars": 110.0},
        "total_realized_pnl_dollars": 5.50,
    }
    html = render_runtime(runtime, snapshot={"version": 0})
    assert 'id="strike-grid"' in html
    assert "+7 Y" in html
    assert "$5.50" in html  # PnL pill


def test_render_orderbooks_renders_yes_no_chips() -> None:
    obs = {"strikes": [{
        "ticker": "KX-T1", "best_bid_c": 49, "best_ask_c": 50,
        "yes_levels": [], "no_levels": [],
    }]}
    html = render_orderbooks(obs)
    assert 'id="strike-grid"' in html
    assert "50¢" in html  # yesC = best_ask
    assert "51¢" in html  # noC = 100 - best_bid
    assert "49%" in html  # chance = best_bid


# ── Live dashboard render via TestClient ────────────────────────────


def _client_with_dashboard() -> tuple[TestClient, ControlState, Broadcaster]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    return TestClient(app), state, b


def test_dashboard_first_paint_includes_orderbook_data() -> None:
    """When the broadcaster has cached an orderbook snapshot, the
    first-paint strike grid renders with Yes/No prices populated."""
    client, _, b = _client_with_dashboard()
    asyncio.get_event_loop().run_until_complete(b.broadcast_orderbook({
        "strikes": [{
            "ticker": "KXISMPMI-26MAY-51",
            "best_bid_c": 49, "best_ask_c": 52,
            "yes_levels": [], "no_levels": [],
        }],
        "last_cycle_ts": 0.0,
    }))
    r = client.get("/dashboard")
    body = r.text
    assert 'id="strike-grid"' in body
    assert "KXISMPMI-26MAY-51" in body
    assert "At least 51" in body
    assert "52¢" in body  # yesC
    assert "51¢" in body  # noC = 100 - 49
    assert "49%" in body  # chance


def test_dashboard_strike_grid_status_change_after_pause() -> None:
    """A pause/resume changes the snapshot.version; the status bar
    re-renders with the new version on the next state_change push."""
    client, state, b = _client_with_dashboard()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial frame
        r = client.post("/control/pause", json={
            "scope": "global", "request_id": "req-grid-pause-1",
        }, headers=_h())
        assert r.status_code == 200
        html = ws.receive_text()
        assert 'id="status-bar"' in html
        assert "v1" in html  # version bumped


def test_strike_row_left_border_for_override() -> None:
    """Theo override → gold left border on the strike row."""
    state = ControlState()
    asyncio.get_event_loop().run_until_complete(state.set_theo_override(
        "KX-T1", 0.55, reason="test override",
    ))
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    body = r.text
    # 'manual' pill on the row + override cents in Theo column
    assert "manual" in body
    assert "55¢" in body
    # Gold left border
    assert "var(--lip)" in body


def test_strike_row_position_tint_by_sign() -> None:
    """Long position → green tint; short position → rose tint."""
    from lipmm.execution import OrderManager
    from lipmm.execution.base import Balance, Position

    class _StubEx:
        async def list_positions(self): return [
            Position("KX-LONG", 5, 49, 0.0, 0.0),
            Position("KX-SHORT", -3, 13, 0.0, 0.0),
        ]
        async def get_balance(self): return Balance(0.0, 0.0)
        async def cancel_order(self, oid): return True
        async def list_resting_orders(self): return []
        async def place_order(self, *a, **k): return None
        async def amend_order(self, *a, **k): return None
        async def cancel_orders(self, ids): return {}

    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        exchange=_StubEx(), order_manager=OrderManager(),
        mount_dashboard=True,
    )
    client = TestClient(app)
    body = client.get("/dashboard").text
    # Long row: green tint rgba; short row: rose tint rgba
    assert "rgba(61, 220, 151, 0.04)" in body  # long tint
    assert "rgba(255, 122, 138, 0.04)" in body  # short tint


# ── HTML WS receives orderbook_snapshot and renders the grid ────────


def test_html_ws_receives_orderbook_renders_strike_grid() -> None:
    """Phase 10b: orderbook_snapshot triggers a strike-grid re-render
    with the new prices."""
    client, _, b = _client_with_dashboard()
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial frame
        async def push():
            await b.broadcast_orderbook({
                "strikes": [{"ticker": "KX-T1", "best_bid_c": 30,
                             "best_ask_c": 31, "yes_levels": [], "no_levels": []}],
                "last_cycle_ts": 0.0,
            })
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(push())
        finally:
            loop.close()
        html = ws.receive_text()
        assert 'id="strike-grid"' in html
        assert "30%" in html      # chance
        assert "31¢" in html      # yesC
        assert "70¢" in html      # noC = 100 - 30
