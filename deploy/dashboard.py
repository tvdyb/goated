# ruff: noqa: E501
"""Live LIP dashboard for the market maker.

Run alongside deploy/lip_mode.py:
    python -m deploy.dashboard

Opens at http://localhost:5050
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, Response

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient

app = Flask(__name__)

_ET = ZoneInfo("America/New_York")

import math
from scipy.special import ndtr as _ndtr

LIP_ELIGIBLE = {1136.99, 1146.99, 1156.99, 1166.99, 1176.99, 1186.99, 1196.99}
LIP_POOL_PER_MARKET = 15.0  # $/day
LIP_TARGET = 300
LIP_DISCOUNT = 0.5

# Theo parameters
_THEO_VOL = 0.1629
_YF_TICKER = "ZSK26.CBT"
_SETTLE_TIME = "2026-04-30T17:00:00-04:00"

_MARKOUT_FILE = "state/markout.json"

# yfinance cache
_yf_price: float = 0.0
_yf_last_pull: float = 0.0


def _get_yf_forward() -> float:
    """Get ZSK26 price from yfinance, cached 60s."""
    global _yf_price, _yf_last_pull
    now = time.time()
    if _yf_price > 0 and (now - _yf_last_pull) < 60:
        return _yf_price
    try:
        import yfinance as yf
        tk = yf.Ticker(_YF_TICKER)
        hist = tk.history(period="1d")
        if not hist.empty:
            _yf_price = float(hist["Close"].iloc[-1])
            _yf_last_pull = now
    except Exception:
        pass
    return _yf_price


def _get_days_to_settle() -> float:
    """Compute days to settlement."""
    try:
        settle = datetime.fromisoformat(_SETTLE_TIME)
        now = datetime.now(settle.tzinfo)
        return max(0.1, (settle - now).total_seconds() / 86400)
    except Exception:
        return 1.0


def _compute_theo(strike_cents: float, days_to_settle: float) -> int:
    """Compute theo in cents for a strike."""
    fwd_cents = _get_yf_forward()
    if fwd_cents <= 0:
        return 0
    forward = fwd_cents / 100.0
    k = strike_cents / 100.0
    tau = max(0.1, days_to_settle) / 365.0
    sig_sqrt_t = max(_THEO_VOL * math.sqrt(tau), 1e-12)
    d2 = (math.log(forward / k) - 0.5 * _THEO_VOL ** 2 * tau) / sig_sqrt_t
    return int(round(float(_ndtr(d2)) * 100))

_state: dict = {
    "balance": {},
    "orders": [],
    "positions": [],
    "event": {},
    "markets": [],
    "orderbooks": {},
    "lip_analysis": [],
    "markout": [],
    "last_refresh": "",
    "error": "",
}
_lock = threading.Lock()


def _get_client() -> tuple[KalshiAuth, str]:
    api_key = os.environ.get("KALSHI_API_KEY", "")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    if not api_key or not key_path:
        raise RuntimeError("Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH")
    pem = Path(key_path).read_bytes()
    return KalshiAuth(api_key=api_key, private_key_pem=pem), "https://api.elections.kalshi.com"


def _analyze_lip(
    ticker: str,
    strike: float,
    yes_depth: list[tuple[int, float]],
    no_depth: list[tuple[int, float]],
    our_orders: list[dict],
) -> dict[str, Any]:
    """Analyze LIP positioning for one market."""
    # Find our bid and ask from orders
    our_bid_px = 0
    our_ask_px = 0
    our_bid_sz = 0
    our_ask_sz = 0
    for o in our_orders:
        px_str = o.get("yes_price_dollars", "0")
        px_cents = int(round(float(px_str) * 100)) if px_str else 0
        sz = float(o.get("remaining_count_fp", "0"))
        if o.get("action") == "buy":
            our_bid_px = px_cents
            our_bid_sz = sz
        elif o.get("action") == "sell":
            our_ask_px = px_cents
            our_ask_sz = sz

    # Best bid/ask
    best_bid = yes_depth[0][0] if yes_depth else 0
    best_ask = (100 - no_depth[0][0]) if no_depth else 100

    # --- BID SIDE analysis ---
    # Count contracts ahead of us (more aggressive = higher bid)
    bid_ahead = 0
    for px, sz in yes_depth:
        if px > our_bid_px:
            bid_ahead += sz
        elif px == our_bid_px:
            # Others at same level (subtract our size)
            bid_ahead += max(0, sz - our_bid_sz)

    # Find LIP cutoff bid (lowest bid that still qualifies)
    lip_cutoff_bid = 1  # default: anywhere works
    cumulative = 0
    for px, sz in yes_depth:
        if px == our_bid_px:
            sz = max(0, sz - our_bid_sz)
        cumulative += sz
        if cumulative + our_bid_sz > LIP_TARGET:
            lip_cutoff_bid = px  # must be at or above this
            break
    # If never exceeded, any price works
    if cumulative + our_bid_sz <= LIP_TARGET:
        lip_cutoff_bid = 1

    bid_headroom = our_bid_px - lip_cutoff_bid if our_bid_px > 0 else 0
    bid_dist_from_best = best_bid - our_bid_px if best_bid > 0 and our_bid_px > 0 else 0
    bid_multiplier = LIP_DISCOUNT ** max(0, bid_dist_from_best)

    # --- ASK SIDE analysis ---
    our_no_px = 100 - our_ask_px if our_ask_px > 0 else 0
    ask_ahead = 0
    for px, sz in no_depth:
        if px > our_no_px:
            ask_ahead += sz
        elif px == our_no_px:
            ask_ahead += max(0, sz - our_ask_sz)

    lip_cutoff_ask = 99
    cumulative = 0
    for px, sz in no_depth:
        if px == our_no_px:
            sz = max(0, sz - our_ask_sz)
        cumulative += sz
        if cumulative + our_ask_sz > LIP_TARGET:
            lip_cutoff_ask = 100 - px
            break
    if cumulative + our_ask_sz <= LIP_TARGET:
        lip_cutoff_ask = 99

    ask_headroom = lip_cutoff_ask - our_ask_px if our_ask_px > 0 else 0
    ask_dist_from_best = our_ask_px - best_ask if our_ask_px > 0 and best_ask < 100 else 0
    ask_multiplier = LIP_DISCOUNT ** max(0, ask_dist_from_best)

    # --- Score estimation ---
    bid_score = our_bid_sz * bid_multiplier if our_bid_px > 0 else 0
    ask_score = our_ask_sz * ask_multiplier if our_ask_px > 0 else 0
    our_total_score = bid_score + ask_score

    # Estimate total score from all participants
    total_bid_score = sum(
        sz * (LIP_DISCOUNT ** max(0, best_bid - px))
        for px, sz in yes_depth
    )
    total_ask_score = sum(
        sz * (LIP_DISCOUNT ** max(0, no_depth[0][0] - px if no_depth else 0))
        for px, sz in no_depth
    )
    total_score = total_bid_score + total_ask_score

    share_pct = (our_total_score / total_score * 100) if total_score > 0 else 0
    est_daily = share_pct / 100 * LIP_POOL_PER_MARKET
    est_hourly = est_daily / 24

    bid_in_top300 = bid_ahead + our_bid_sz <= LIP_TARGET if our_bid_px > 0 else False
    ask_in_top300 = ask_ahead + our_ask_sz <= LIP_TARGET if our_ask_px > 0 else False

    return {
        "ticker": ticker,
        "strike": strike,
        "is_lip": strike in LIP_ELIGIBLE,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "our_bid": our_bid_px,
        "our_ask": our_ask_px,
        "our_bid_sz": our_bid_sz,
        "our_ask_sz": our_ask_sz,
        "lip_cutoff_bid": lip_cutoff_bid,
        "lip_cutoff_ask": lip_cutoff_ask,
        "bid_headroom": bid_headroom,
        "ask_headroom": ask_headroom,
        "bid_ahead": bid_ahead,
        "ask_ahead": ask_ahead,
        "bid_in_top300": bid_in_top300,
        "ask_in_top300": ask_in_top300,
        "bid_multiplier": bid_multiplier,
        "ask_multiplier": ask_multiplier,
        "bid_score": bid_score,
        "ask_score": ask_score,
        "our_score": our_total_score,
        "total_score": total_score,
        "share_pct": share_pct,
        "est_daily": est_daily,
        "est_hourly": est_hourly,
        "spread": our_ask_px - our_bid_px if our_bid_px > 0 and our_ask_px > 0 else 0,
        "theo": 0,  # populated by caller
    }


async def _refresh() -> dict:
    auth, base = _get_client()
    async with KalshiClient(auth=auth, base_url=base) as c:
        balance = await c.get_balance()
        orders_resp = await c.get_orders(status="resting", limit=200)
        positions_resp = await c.get_positions(limit=100)
        events_resp = await c.get_events(series_ticker="KXSOYBEANMON", status="open", limit=3)

        events = events_resp.get("events", [])
        markets: list[dict] = []
        lip_analysis: list[dict] = []

        if events:
            detail = await c.get_event(events[0]["event_ticker"])
            markets = detail.get("markets", [])

            orders = orders_resp.get("orders", [])
            orders_by_ticker: dict[str, list] = {}
            for o in orders:
                t = o.get("ticker", "")
                orders_by_ticker.setdefault(t, []).append(o)

            for m in markets:
                ticker = m.get("ticker", "")
                strike = float(m.get("floor_strike", 0))

                if strike not in LIP_ELIGIBLE:
                    continue

                try:
                    ob = await c.get_orderbook(ticker)
                    ob_fp = ob.get("orderbook_fp", {})
                    yes_lvls = ob_fp.get("yes_dollars", [])
                    no_lvls = ob_fp.get("no_dollars", [])

                    yes_depth = sorted(
                        [(int(round(float(lv[0]) * 100)), float(lv[1])) for lv in yes_lvls],
                        key=lambda x: -x[0],
                    )
                    no_depth = sorted(
                        [(int(round(float(lv[0]) * 100)), float(lv[1])) for lv in no_lvls],
                        key=lambda x: -x[0],
                    )

                    analysis = _analyze_lip(
                        ticker, strike, yes_depth, no_depth,
                        orders_by_ticker.get(ticker, []),
                    )
                    # Compute theo using settlement override + yfinance forward
                    analysis["theo"] = _compute_theo(strike, _get_days_to_settle())
                    lip_analysis.append(analysis)
                except Exception:
                    pass

        # Read markout data from shared file (written by lip_mode)
        markout_data: list[dict] = []
        try:
            with open(_MARKOUT_FILE) as mf:
                markout_data = json.load(mf)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return {
            "balance": balance,
            "orders": orders_resp.get("orders", []),
            "positions": positions_resp.get("market_positions", []),
            "event": events[0] if events else {},
            "markets": markets,
            "lip_analysis": lip_analysis,
            "markout": markout_data,
            "last_refresh": datetime.now(_ET).strftime("%H:%M:%S"),
            "error": "",
        }


def _bg_refresh() -> None:
    global _state
    while True:
        try:
            result = asyncio.run(_refresh())
            with _lock:
                _state = result
        except Exception as exc:
            with _lock:
                _state["error"] = str(exc)
                _state["last_refresh"] = datetime.now(_ET).strftime("%H:%M:%S")
        time.sleep(5)


@app.route("/")
def index() -> str:
    with _lock:
        s = dict(_state)

    balance_cents = s["balance"].get("balance", 0)
    portfolio_cents = s["balance"].get("portfolio_value", 0)
    total_cents = balance_cents + portfolio_cents
    lip = s.get("lip_analysis", [])

    # Aggregate LIP stats
    total_est_daily = sum(a["est_daily"] for a in lip)
    total_est_hourly = total_est_daily / 24 if total_est_daily > 0 else 0
    total_pool_daily = len(lip) * LIP_POOL_PER_MARKET
    total_pool_hourly = total_pool_daily / 24
    avg_share = (sum(a["share_pct"] for a in lip) / len(lip)) if lip else 0
    markets_qualifying = sum(
        1 for a in lip if a["bid_in_top300"] or a["ask_in_top300"]
    )
    avg_headroom = (
        sum(min(a["bid_headroom"], a["ask_headroom"]) for a in lip) / len(lip)
    ) if lip else 0

    # Forward and settlement info
    yf_fwd = _get_yf_forward()
    yf_fwd_str = f"{yf_fwd:.1f}c (${yf_fwd/100:.4f})" if yf_fwd > 0 else "N/A"
    days_to_settle = _get_days_to_settle()
    hours_to_settle = days_to_settle * 24

    error_html = ""
    if s["error"]:
        error_html = f'<div style="background:#991b1b;padding:8px;border-radius:4px;margin-bottom:16px">{s["error"]}</div>'

    event_ticker = s["event"].get("event_ticker", "none")

    # --- LIP per-bucket rows ---
    lip_rows = ""
    for a in sorted(lip, key=lambda x: x["strike"]):
        bid_status = "ok" if a["bid_in_top300"] else "OUT"
        ask_status = "ok" if a["ask_in_top300"] else "OUT"
        bid_color = "#4ade80" if a["bid_in_top300"] else "#f87171"
        ask_color = "#4ade80" if a["ask_in_top300"] else "#f87171"
        headroom_bid_color = "#4ade80" if a["bid_headroom"] > 3 else "#f59e0b" if a["bid_headroom"] > 0 else "#f87171"
        headroom_ask_color = "#4ade80" if a["ask_headroom"] > 3 else "#f59e0b" if a["ask_headroom"] > 0 else "#f87171"

        strike_label = f"{a['strike']:.2f}"

        theo = a.get("theo", 0)
        theo_color = "#60a5fa"

        lip_rows += f"""
        <tr>
            <td style="font-family:monospace;font-size:12px">{strike_label}</td>
            <td style="text-align:center">{a['best_bid']}c</td>
            <td style="text-align:center;font-weight:bold">{a['our_bid']}c</td>
            <td style="text-align:center">{a['lip_cutoff_bid']}c</td>
            <td style="text-align:center;color:{headroom_bid_color};font-weight:bold">{a['bid_headroom']}c</td>
            <td style="text-align:center;color:{bid_color}">{a['bid_ahead']:.0f}/{LIP_TARGET} {bid_status}</td>
            <td style="text-align:center">{a['bid_multiplier']:.2f}x</td>
            <td style="background:#1e293b;text-align:center;font-weight:bold;color:{theo_color}">{theo}c</td>
            <td style="background:#334155;text-align:center;font-weight:bold;color:#94a3b8">{a['spread']}c</td>
            <td style="text-align:center">{a['ask_multiplier']:.2f}x</td>
            <td style="text-align:center;color:{ask_color}">{a['ask_ahead']:.0f}/{LIP_TARGET} {ask_status}</td>
            <td style="text-align:center;color:{headroom_ask_color};font-weight:bold">{a['ask_headroom']}c</td>
            <td style="text-align:center">{a['lip_cutoff_ask']}c</td>
            <td style="text-align:center;font-weight:bold">{a['our_ask']}c</td>
            <td style="text-align:center">{a['best_ask']}c</td>
            <td style="text-align:right">{a['share_pct']:.1f}%</td>
            <td style="text-align:right;color:#4ade80">${a['est_daily']:.2f}</td>
        </tr>"""

    # --- Markout rows ---
    markout_rows = ""
    markout_data = s.get("markout", [])
    for m in markout_data:
        ticker = m.get("market_ticker", "")
        strike_label = ticker.split("-")[-1] if ticker else "?"
        n = m.get("n_fills", 0)
        avg_1m = m.get("avg_1m", 0.0)
        avg_5m = m.get("avg_5m", 0.0)
        avg_30m = m.get("avg_30m", 0.0)
        c1 = "#4ade80" if avg_1m >= 0 else "#f87171"
        c5 = "#4ade80" if avg_5m >= 0 else "#f87171"
        c30 = "#4ade80" if avg_30m >= 0 else "#f87171"
        toxic = avg_5m < -2.0 and n >= 2
        toxic_tag = '<span style="color:#f87171;font-weight:bold"> TOXIC</span>' if toxic else ""
        markout_rows += f"""
        <tr>
            <td style="font-family:monospace;font-size:12px">{strike_label}{toxic_tag}</td>
            <td style="text-align:right">{n}</td>
            <td style="text-align:right;color:{c1}">{avg_1m:+.1f}c</td>
            <td style="text-align:right;color:{c5}">{avg_5m:+.1f}c</td>
            <td style="text-align:right;color:{c30}">{avg_30m:+.1f}c</td>
        </tr>"""

    # --- Positions rows ---
    pos_rows = ""
    for p in s.get("positions", []):
        ticker = p.get("ticker", "")
        qty = p.get("position_fp", "0")
        pnl = p.get("realized_pnl_dollars", "0")
        exposure = p.get("market_exposure_dollars", "0")
        fees = p.get("fees_paid_dollars", "0")
        if float(qty) != 0:
            pnl_color = "#4ade80" if float(pnl) >= 0 else "#f87171"
            pos_rows += f"""
            <tr>
                <td style="font-family:monospace;font-size:12px">{ticker}</td>
                <td style="text-align:right">{qty}</td>
                <td style="text-align:right">${exposure}</td>
                <td style="text-align:right;color:{pnl_color}">${pnl}</td>
                <td style="text-align:right">${fees}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Goated LIP Dashboard</title>
    <meta http-equiv="refresh" content="5">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0f172a; color: #e2e8f0; font-family: -apple-system, system-ui, sans-serif; padding: 20px; }}
        h1 {{ font-size: 20px; margin-bottom: 4px; }}
        h2 {{ font-size: 14px; color: #94a3b8; margin: 20px 0 8px 0; text-transform: uppercase; letter-spacing: 1px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .stats {{ display: flex; gap: 16px; flex-wrap: wrap; }}
        .stat {{ background: #1e293b; padding: 12px 20px; border-radius: 8px; min-width: 140px; }}
        .stat-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; }}
        .stat-value {{ font-size: 22px; font-weight: bold; margin-top: 2px; }}
        .stat-value.green {{ color: #4ade80; }}
        .stat-value.yellow {{ color: #f59e0b; }}
        .stat-value.red {{ color: #f87171; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
        th {{ background: #334155; padding: 6px 8px; text-align: center; font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
        td {{ padding: 5px 8px; border-bottom: 1px solid #334155; font-size: 13px; }}
        tr:hover {{ background: #334155; }}
        .refresh {{ color: #64748b; font-size: 12px; }}
        .live {{ background: #16a34a; color: white; font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: bold; }}
        .section-header {{ display: flex; align-items: center; gap: 8px; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Goated LIP Dashboard <span class="live">LIVE</span></h1>
            <span class="refresh">Refresh: {s["last_refresh"]} ET &bull; {event_ticker}</span>
        </div>
    </div>

    {error_html}

    <div class="stats">
        <div class="stat">
            <div class="stat-label">ZSK26 (May Soy)</div>
            <div class="stat-value" style="color:#60a5fa">{yf_fwd_str}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Settlement In</div>
            <div class="stat-value {'red' if hours_to_settle < 2 else 'yellow' if hours_to_settle < 6 else ''}">{hours_to_settle:.1f}h</div>
        </div>
        <div class="stat">
            <div class="stat-label">Est. LIP $/hr</div>
            <div class="stat-value green">${total_est_hourly:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Est. LIP $/day</div>
            <div class="stat-value green">${total_est_daily:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Avg Pool Share</div>
            <div class="stat-value {'green' if avg_share > 10 else 'yellow' if avg_share > 3 else 'red'}">{avg_share:.1f}%</div>
        </div>
        <div class="stat">
            <div class="stat-label">Pool Total $/hr</div>
            <div class="stat-value">${total_pool_hourly:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Qualifying</div>
            <div class="stat-value {'green' if markets_qualifying == len(lip) else 'yellow'}">{markets_qualifying}/{len(lip)}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Avg Headroom</div>
            <div class="stat-value {'green' if avg_headroom > 3 else 'yellow' if avg_headroom > 0 else 'red'}">{avg_headroom:.0f}c</div>
        </div>
        <div class="stat">
            <div class="stat-label">Cash</div>
            <div class="stat-value">${balance_cents / 100:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Portfolio</div>
            <div class="stat-value">${portfolio_cents / 100:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Total</div>
            <div class="stat-value">${total_cents / 100:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Resting Orders</div>
            <div class="stat-value">{len(s.get("orders", []))}</div>
        </div>
    </div>

    <h2>LIP Positioning (per bucket)</h2>
    <table>
        <tr>
            <th>Strike</th>
            <th colspan="6" style="background:#1e3a2f">BID (Buy Yes) &larr; wider is safer</th>
            <th>Theo</th>
            <th>Spread</th>
            <th colspan="6" style="background:#3a1e1e">ASK (Sell Yes) &rarr; wider is safer</th>
            <th>Share</th>
            <th>$/day</th>
        </tr>
        <tr>
            <th></th>
            <th style="background:#1e3a2f">Best</th>
            <th style="background:#1e3a2f">Ours</th>
            <th style="background:#1e3a2f">LIP Limit</th>
            <th style="background:#1e3a2f">Headroom</th>
            <th style="background:#1e3a2f">Queue</th>
            <th style="background:#1e3a2f">Mult</th>
            <th style="background:#1a2744">Fair</th>
            <th></th>
            <th style="background:#3a1e1e">Mult</th>
            <th style="background:#3a1e1e">Queue</th>
            <th style="background:#3a1e1e">Headroom</th>
            <th style="background:#3a1e1e">LIP Limit</th>
            <th style="background:#3a1e1e">Ours</th>
            <th style="background:#3a1e1e">Best</th>
            <th></th>
            <th></th>
        </tr>
        {lip_rows if lip_rows else "<tr><td colspan=16 style='color:#64748b;text-align:center'>No LIP data</td></tr>"}
    </table>

    <h2>Fill Markout (adverse selection)</h2>
    <table>
        <tr>
            <th>Strike</th>
            <th>Fills</th>
            <th>1m</th>
            <th>5m</th>
            <th>30m</th>
        </tr>
        {markout_rows if markout_rows else "<tr><td colspan=5 style='color:#64748b;text-align:center'>No markout data (waiting for fills)</td></tr>"}
    </table>

    <h2>Positions</h2>
    <table>
        <tr><th>Market</th><th>Qty</th><th>Exposure</th><th>Realized PnL</th><th>Fees</th></tr>
        {pos_rows if pos_rows else "<tr><td colspan=5 style='color:#64748b;text-align:center'>No open positions</td></tr>"}
    </table>
</body>
</html>"""
    return html


@app.route("/api/state")
def api_state() -> Response:
    with _lock:
        return Response(json.dumps(_state, default=str), mimetype="application/json")


def main() -> None:
    t = threading.Thread(target=_bg_refresh, daemon=True)
    t.start()

    print("Dashboard at http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)


if __name__ == "__main__":
    main()
