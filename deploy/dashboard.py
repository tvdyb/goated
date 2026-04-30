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
from scipy.special import ndtr as _ndtr, ndtri as _ndtri

LIP_ELIGIBLE = {1136.99, 1146.99, 1156.99, 1166.99, 1176.99, 1186.99, 1196.99}
LIP_POOL_PER_MARKET = 15.0  # $/day
LIP_TARGET = 300
LIP_DISCOUNT = 0.5

# Theo parameters
_THEO_VOL_FALLBACK = 0.1629  # used only if bot hasn't written theo_state yet
_YF_TICKER = "ZSK26.CBT"
_SETTLE_TIME = "2026-04-30T17:00:00-04:00"

_MARKOUT_FILE = "state/markout.json"
_LIP_HISTORY_FILE = "state/lip_history.json"
_THEO_STATE_FILE = "state/theo_state.json"

# Bin edges for the $/hr histogram. Bin i covers [edges[i], edges[i+1]); the
# final bin captures everything >= the last edge.
_LIP_BIN_EDGES = [0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 2.50, 3.00, 4.00]
_LIP_N_BINS = len(_LIP_BIN_EDGES)  # last edge is the overflow boundary

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


def _kalshi_implied_forward(lip_analysis: list[dict], vol: float, days_to_settle: float) -> float:
    """Back out forward from Kalshi orderbook Yes mids.

    For each strike with reasonable mid (5%-95%) and spread (<30c), invert
    Black-76 to solve for F given the supplied vol. Return median across strikes.

    Returns 0.0 if no valid strikes.
    """
    if vol <= 0 or days_to_settle <= 0:
        return 0.0
    tau = max(0.001, days_to_settle) / 365.0
    sig_sqrt_t = max(vol * math.sqrt(tau), 1e-12)

    forwards: list[float] = []
    for a in lip_analysis:
        best_bid = a.get("best_bid", 0)
        best_ask = a.get("best_ask", 100)
        strike = a.get("strike", 0)
        if strike <= 0 or best_bid <= 0 or best_ask >= 100 or best_bid >= best_ask:
            continue
        if (best_ask - best_bid) > 30:
            continue
        yes_mid_prob = (best_bid + best_ask) / 200.0  # 0..1
        if not (0.05 <= yes_mid_prob <= 0.95):
            continue
        try:
            d2 = float(_ndtri(yes_mid_prob))
        except Exception:
            continue
        strike_dollars = strike / 100.0
        F = strike_dollars * math.exp(d2 * sig_sqrt_t + 0.5 * vol * vol * tau)
        if 5.0 < F < 30.0:  # sanity bound for soybeans ($5-$30/bu)
            forwards.append(F)

    if not forwards:
        return 0.0
    forwards.sort()
    return forwards[len(forwards) // 2]


def _compute_theo(
    strike_cents: float,
    days_to_settle: float,
    vol: float | None = None,
    forward_dollars: float | None = None,
) -> int:
    """Compute theo in cents for a strike.

    Uses bot's calibrated vol and bot's forward when provided. Falls back to
    yfinance + hardcoded vol only when bot data is stale/missing.
    """
    if forward_dollars is not None and forward_dollars > 0:
        forward = forward_dollars
    else:
        fwd_cents = _get_yf_forward()
        if fwd_cents <= 0:
            return 0
        forward = fwd_cents / 100.0
    sigma = vol if (vol is not None and vol > 0) else _THEO_VOL_FALLBACK
    k = strike_cents / 100.0
    tau = max(0.1, days_to_settle) / 365.0
    sig_sqrt_t = max(sigma * math.sqrt(tau), 1e-12)
    d2 = (math.log(forward / k) - 0.5 * sigma ** 2 * tau) / sig_sqrt_t
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
    "theo_state": {},
    "last_refresh": "",
    "error": "",
    "total_est_hourly": 0.0,
}
_lock = threading.Lock()


def _default_lip_history() -> dict:
    return {
        "start_ts": time.time(),
        "last_ts": 0.0,
        "total_dollars": 0.0,
        "total_runtime_s": 0.0,
        "n_samples": 0,
        "max_hourly": 0.0,
        "bins": [0] * _LIP_N_BINS,
    }


def _load_lip_history() -> dict:
    try:
        with open(_LIP_HISTORY_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_lip_history()

    defaults = _default_lip_history()
    for k, v in defaults.items():
        data.setdefault(k, v)
    if len(data.get("bins", [])) != _LIP_N_BINS:
        data["bins"] = [0] * _LIP_N_BINS
    return data


def _save_lip_history(h: dict) -> None:
    Path("state").mkdir(exist_ok=True)
    try:
        with open(_LIP_HISTORY_FILE, "w") as f:
            json.dump(h, f)
    except Exception:
        pass


_lip_history: dict = _load_lip_history()
_lip_lock = threading.Lock()


def _bin_index_for(hourly: float) -> int:
    """Return the bin index for a $/hr value. Last bin is the overflow."""
    for i in range(_LIP_N_BINS - 1):
        if _LIP_BIN_EDGES[i] <= hourly < _LIP_BIN_EDGES[i + 1]:
            return i
    return _LIP_N_BINS - 1  # overflow


def _update_lip_history(hourly: float) -> None:
    """Accrue runtime + dollars + histogram bin for this sample.

    Caps inter-sample dt at 60s so a paused dashboard doesn't inflate totals.
    """
    if hourly < 0 or not math.isfinite(hourly):
        return
    now = time.time()
    with _lip_lock:
        last = _lip_history.get("last_ts", 0.0) or 0.0
        if last > 0:
            dt = now - last
            if 0 < dt < 60:
                _lip_history["total_dollars"] += hourly * (dt / 3600.0)
                _lip_history["total_runtime_s"] += dt
        _lip_history["last_ts"] = now
        _lip_history["n_samples"] = int(_lip_history.get("n_samples", 0)) + 1
        if hourly > _lip_history.get("max_hourly", 0.0):
            _lip_history["max_hourly"] = hourly
        idx = _bin_index_for(hourly)
        _lip_history["bins"][idx] += 1
        _save_lip_history(_lip_history)


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
        "yes_depth": yes_depth,  # full orderbook depth
        "no_depth": no_depth,
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

        # Read theo state from shared file (written by lip_mode)
        theo_state: dict = {}
        try:
            with open(_THEO_STATE_FILE) as tf:
                theo_state = json.load(tf)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Backfill theo using bot's live vol + forward (when fresh)
        bot_age = time.time() - theo_state.get("ts", 0) if theo_state else 1e9
        live_vol = None
        live_fwd = None
        if theo_state and bot_age < 120:
            v = theo_state.get("vol_calibrated")
            if v and v > 0:
                live_vol = v
            f = theo_state.get("forward_dollars")
            if f and f > 0:
                live_fwd = f
        for analysis in lip_analysis:
            # analysis["strike"] is already in Kalshi cents-as-float (e.g. 1186.99)
            analysis["theo"] = _compute_theo(
                analysis["strike"], _get_days_to_settle(),
                vol=live_vol, forward_dollars=live_fwd,
            )

        total_est_daily = sum(a["est_daily"] for a in lip_analysis)
        total_est_hourly = total_est_daily / 24 if total_est_daily > 0 else 0.0

        return {
            "balance": balance,
            "orders": orders_resp.get("orders", []),
            "positions": positions_resp.get("market_positions", []),
            "event": events[0] if events else {},
            "markets": markets,
            "lip_analysis": lip_analysis,
            "markout": markout_data,
            "theo_state": theo_state,
            "last_refresh": datetime.now(_ET).strftime("%H:%M:%S"),
            "error": "",
            "total_est_hourly": total_est_hourly,
        }


def _bg_refresh() -> None:
    global _state
    while True:
        try:
            result = asyncio.run(_refresh())
            with _lock:
                _state = result
            # Only accrue LIP history when the bot is actively trading.
            # Skip if (a) bot in maintenance mode (cancelled orders, idle), or
            # (b) bot heartbeat stale >2min (process down or unresponsive).
            ts = result.get("theo_state", {})
            bot_age = time.time() - ts.get("ts", 0) if ts else 1e9
            in_maintenance = ts.get("maintenance_active", False)
            if not in_maintenance and bot_age < 120:
                _update_lip_history(result.get("total_est_hourly", 0.0))
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
    # Top header price: prefer bot's live forward (Trading Economics primary),
    # fall back to yfinance if bot heartbeat stale.
    _ts_top = s.get("theo_state", {})
    _ts_age_top = time.time() - _ts_top.get("ts", 0) if _ts_top else 1e9
    _bot_fwd_dollars = _ts_top.get("forward_dollars", 0.0) if _ts_age_top < 120 else 0.0
    if _bot_fwd_dollars and _bot_fwd_dollars > 0:
        _bot_fwd_cents = _bot_fwd_dollars * 100
        _bot_fwd_src = _ts_top.get("forward_source", "bot")
        yf_fwd_str = f"{_bot_fwd_cents:.2f}c (${_bot_fwd_dollars:.4f})"
        yf_fwd_label = f"Soybean ({_bot_fwd_src})"
    else:
        yf_fwd = _get_yf_forward()
        yf_fwd_str = f"{yf_fwd:.1f}c (${yf_fwd/100:.4f})" if yf_fwd > 0 else "N/A"
        yf_fwd_label = "ZSK26 (yfinance, bot down)"
    days_to_settle = _get_days_to_settle()
    hours_to_settle = days_to_settle * 24

    error_html = ""
    if s["error"]:
        error_html = f'<div style="background:#991b1b;padding:8px;border-radius:4px;margin-bottom:16px">{s["error"]}</div>'

    # Maintenance banner (Kalshi weekly 3-5 AM ET)
    maintenance_html = ""
    if s.get("theo_state", {}).get("maintenance_active"):
        maintenance_html = (
            '<div style="background:#854d0e;padding:12px;border-radius:4px;margin-bottom:16px;'
            'font-weight:bold;color:#fde68a">'
            '⏸ KALSHI MAINTENANCE WINDOW (3–5 AM ET) — bot has cancelled orders and is idling. '
            'Will resume automatically after 5 AM ET.'
            '</div>'
        )

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

        # Build orderbook depth HTML
        yes_depth = a.get("yes_depth", [])
        no_depth = a.get("no_depth", [])
        our_bid = a["our_bid"]
        our_ask = a["our_ask"]

        depth_rows = ""
        # Combine yes (bids) and no (asks) into a unified view
        # Left side: Yes bids (highest first)
        # Right side: No bids = Yes asks (highest No bid = lowest Yes ask first)
        max_depth = max(len(yes_depth), len(no_depth), 1)
        for i in range(min(max_depth, 12)):  # cap at 12 levels
            # Yes bid level
            if i < len(yes_depth):
                ypx, ysz = yes_depth[i]
                ycolor = "#60a5fa" if ypx == our_bid else "#e2e8f0"
                ybold = "font-weight:bold;" if ypx == our_bid else ""
                ytag = " ◄" if ypx == our_bid else ""
                ycell = f'<td style="text-align:right;color:{ycolor};{ybold}">{ypx}c{ytag}</td><td style="text-align:right;color:{ycolor}">{ysz:.0f}</td>'
            else:
                ycell = '<td></td><td></td>'

            # No bid level (= Yes ask)
            if i < len(no_depth):
                npx, nsz = no_depth[i]
                yes_ask_equiv = 100 - npx
                ncolor = "#f59e0b" if yes_ask_equiv == our_ask else "#e2e8f0"
                nbold = "font-weight:bold;" if yes_ask_equiv == our_ask else ""
                ntag = " ►" if yes_ask_equiv == our_ask else ""
                ncell = f'<td style="text-align:left;color:{ncolor};{nbold}">{nsz:.0f}</td><td style="text-align:left;color:{ncolor};{nbold}">{npx}c No ({yes_ask_equiv}c Yes){ntag}</td>'
            else:
                ncell = '<td></td><td></td>'

            depth_rows += f'<tr style="font-size:11px">{ycell}<td style="width:10px"></td>{ncell}</tr>'

        lip_rows += f"""
        <tr>
            <td style="font-family:monospace;font-size:12px">
                <details><summary style="cursor:pointer">{strike_label}</summary>
                <table style="margin:4px 0;background:#0f172a;border:1px solid #334155;width:100%">
                    <tr style="font-size:10px;color:#64748b">
                        <th>Bid</th><th>Size</th><th></th><th>Size</th><th>Ask (No)</th>
                    </tr>
                    {depth_rows}
                </table>
                </details>
            </td>
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

    # --- LIP history (since inception) ---
    with _lip_lock:
        h = dict(_lip_history)
        h_bins = list(h.get("bins", [0] * _LIP_N_BINS))
    runtime_s = h.get("total_runtime_s", 0.0)
    runtime_hr = runtime_s / 3600.0
    total_dollars = h.get("total_dollars", 0.0)
    avg_hourly_inception = (total_dollars / runtime_hr) if runtime_hr > 0 else 0.0
    max_hourly_inception = h.get("max_hourly", 0.0)
    n_samples = h.get("n_samples", 0)

    if runtime_hr >= 1:
        runtime_label = f"{runtime_hr:.1f}h"
    elif runtime_s >= 60:
        runtime_label = f"{runtime_s/60:.0f}m"
    else:
        runtime_label = f"{runtime_s:.0f}s"

    max_bin_count = max(h_bins) if h_bins and max(h_bins) > 0 else 1
    hist_rows = ""
    for i, count in enumerate(h_bins):
        lo = _LIP_BIN_EDGES[i]
        if i + 1 < _LIP_N_BINS:
            hi = _LIP_BIN_EDGES[i + 1]
            label = f"${lo:.2f}–${hi:.2f}"
        else:
            label = f"${lo:.2f}+"
        bar_w = int(round(count / max_bin_count * 240)) if max_bin_count > 0 else 0
        pct = (count / n_samples * 100) if n_samples > 0 else 0
        hist_rows += f"""
        <tr>
            <td style="font-family:monospace;font-size:11px;color:#94a3b8;width:90px">{label}</td>
            <td style="width:260px"><div style="background:#4ade80;height:14px;width:{bar_w}px;border-radius:2px"></div></td>
            <td style="text-align:right;font-size:11px;color:#94a3b8;width:80px">{count} ({pct:.1f}%)</td>
        </tr>"""

    history_section = f"""
    <h2>Estimated LIP Earnings — Since Inception</h2>
    <div class="stats">
        <div class="stat">
            <div class="stat-label">Runtime</div>
            <div class="stat-value">{runtime_label}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Total Earned (est)</div>
            <div class="stat-value green">${total_dollars:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Avg $/hr (time-wt)</div>
            <div class="stat-value green">${avg_hourly_inception:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Peak $/hr</div>
            <div class="stat-value">${max_hourly_inception:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Samples</div>
            <div class="stat-value">{n_samples}</div>
        </div>
    </div>
    <table style="margin-top:8px">
        <tr><th style="text-align:left">$/hr Bucket</th><th style="text-align:left">Distribution</th><th style="text-align:right">Count</th></tr>
        {hist_rows}
    </table>
    """

    # --- Theo inputs (live from bot) ---
    ts = s.get("theo_state", {})
    if ts:
        bot_age_s = time.time() - ts.get("ts", 0)
        bot_age_color = "#4ade80" if bot_age_s < 30 else "#f59e0b" if bot_age_s < 120 else "#f87171"
        bot_age_label = f"{bot_age_s:.0f}s ago" if bot_age_s < 60 else f"{bot_age_s/60:.1f}m ago"

        vol_cal = ts.get("vol_calibrated", 0.0)
        vol_fb = ts.get("vol_fallback", 0.0)
        vol_delta = vol_cal - vol_fb
        vol_delta_str = f"{vol_delta*100:+.2f}pp"
        vol_delta_color = "#4ade80" if abs(vol_delta) < 0.02 else "#f59e0b" if abs(vol_delta) < 0.05 else "#f87171"

        fwd = ts.get("forward_dollars", 0.0)
        fwd_src = ts.get("forward_source", "?")
        days = ts.get("days_to_settlement", 0.0)
        size_base = ts.get("size_base", 0)
        size_jit = ts.get("size_jitter", 0)
        size_last = ts.get("size_last", 0)

        # Sanity check: derive forward from Kalshi orderbook
        kalshi_fwd = _kalshi_implied_forward(lip, vol_cal, days)
        fwd_diff_c = (fwd - kalshi_fwd) * 100 if kalshi_fwd > 0 else 0.0
        fwd_diff_color = "#4ade80" if abs(fwd_diff_c) < 3 else "#f59e0b" if abs(fwd_diff_c) < 8 else "#f87171"
        if kalshi_fwd > 0:
            kalshi_fwd_card = f"""
            <div class="stat" style="background:{'#3a1e1e' if abs(fwd_diff_c) >= 8 else '#1e293b'}">
                <div class="stat-label">Kalshi-implied fwd</div>
                <div class="stat-value" style="color:#a78bfa">${kalshi_fwd:.4f}</div>
                <div style="font-size:10px;color:#94a3b8;margin-top:2px">yf vs Kalshi: <span style="color:{fwd_diff_color};font-weight:bold">{fwd_diff_c:+.1f}c</span></div>
            </div>"""
        else:
            kalshi_fwd_card = """
            <div class="stat">
                <div class="stat-label">Kalshi-implied fwd</div>
                <div class="stat-value" style="color:#64748b">N/A</div>
                <div style="font-size:10px;color:#94a3b8;margin-top:2px">no usable strikes</div>
            </div>"""

        wasde = ts.get("wasde", {})
        if wasde.get("active"):
            shift = wasde.get("current_shift_cents", 0.0)
            shift_color = "#4ade80" if shift > 0 else "#f87171"
            init_shift = wasde.get("initial_shift_cents", 0.0)
            elapsed_h = wasde.get("elapsed_hours", 0.0)
            half_life_h = wasde.get("half_life_hours", 6.0)
            decay_pct = (1 - abs(shift) / abs(init_shift)) * 100 if init_shift else 0
            wasde_card = f"""
            <div class="stat" style="background:#3a2a1e">
                <div class="stat-label">WASDE shift</div>
                <div class="stat-value" style="color:{shift_color}">{shift:+.1f}c</div>
                <div style="font-size:10px;color:#94a3b8;margin-top:2px">init {init_shift:+.1f}c &bull; {elapsed_h:.1f}h elapsed &bull; t½ {half_life_h:.1f}h &bull; decayed {decay_pct:.0f}%</div>
            </div>"""
        else:
            wasde_card = """
            <div class="stat">
                <div class="stat-label">WASDE shift</div>
                <div class="stat-value" style="color:#64748b">inactive</div>
            </div>"""

        theo_inputs_section = f"""
    <h2>Theo Inputs (live from bot)</h2>
    <div class="stats">
        <div class="stat">
            <div class="stat-label">Bot heartbeat</div>
            <div class="stat-value" style="color:{bot_age_color}">{bot_age_label}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Calibrated vol</div>
            <div class="stat-value" style="color:#60a5fa">{vol_cal*100:.2f}%</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">fb {vol_fb*100:.2f}% &bull; <span style="color:{vol_delta_color}">{vol_delta_str}</span></div>
        </div>
        <div class="stat">
            <div class="stat-label">Forward (bot)</div>
            <div class="stat-value" style="color:#60a5fa">${fwd:.4f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">{fwd_src}</div>
        </div>
        {kalshi_fwd_card}
        <div class="stat">
            <div class="stat-label">τ to settlement</div>
            <div class="stat-value">{days*24:.1f}h</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">{days:.3f}d</div>
        </div>
        <div class="stat">
            <div class="stat-label">Size jitter</div>
            <div class="stat-value">{size_last}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">base {size_base} ±{size_jit}</div>
        </div>
        {wasde_card}
    </div>
        """
    else:
        theo_inputs_section = """
    <h2>Theo Inputs (live from bot)</h2>
    <div style="background:#1e293b;padding:12px;border-radius:8px;color:#64748b">
        Waiting for bot to write state/theo_state.json — start lip_mode and refresh.
    </div>"""

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

    # --- PnL aggregation ---
    # Build lookup: ticker -> (theo_yes_cents, best_yes_bid, best_no_bid)
    market_lookup: dict[str, tuple[int, int, int]] = {}
    for a in lip:
        ticker = a.get("ticker", "")
        if not ticker:
            continue
        no_depth = a.get("no_depth", [])
        best_no_bid = no_depth[0][0] if no_depth else 0
        best_yes_bid = a.get("best_bid", 0)
        market_lookup[ticker] = (a.get("theo", 50), best_yes_bid, best_no_bid)

    total_realized = 0.0
    total_unrealized = 0.0
    total_expected_settle = 0.0
    total_fees = 0.0
    total_exposure = 0.0
    pos_rows = ""

    for p in s.get("positions", []):
        ticker = p.get("ticker", "")
        try:
            qty = float(p.get("position_fp", "0"))
        except (TypeError, ValueError):
            qty = 0.0
        try:
            exposure = float(p.get("market_exposure_dollars", "0"))
        except (TypeError, ValueError):
            exposure = 0.0
        try:
            realized = float(p.get("realized_pnl_dollars", "0"))
        except (TypeError, ValueError):
            realized = 0.0
        try:
            fees = float(p.get("fees_paid_dollars", "0"))
        except (TypeError, ValueError):
            fees = 0.0

        total_realized += realized
        total_fees += fees

        if qty == 0:
            continue

        total_exposure += exposure

        theo_yes_c, best_yes_bid_c, best_no_bid_c = market_lookup.get(ticker, (50, 0, 0))

        # Mark-to-market: sell into the bid for the side you hold.
        # Kalshi convention: positive qty = long YES, negative qty = long NO.
        if qty > 0:
            mtm_dollars = qty * (best_yes_bid_c / 100.0)
            theo_payoff_dollars = qty * (theo_yes_c / 100.0)
            side_label = "Yes"
            mtm_px = best_yes_bid_c
            theo_held_side = theo_yes_c
        else:
            mtm_dollars = abs(qty) * (best_no_bid_c / 100.0)
            theo_payoff_dollars = abs(qty) * ((100 - theo_yes_c) / 100.0)
            side_label = "No"
            mtm_px = best_no_bid_c
            theo_held_side = 100 - theo_yes_c

        avg_cost_c = (exposure / abs(qty)) * 100.0 if abs(qty) > 0 else 0.0
        edge_per_contract_c = theo_held_side - avg_cost_c

        unrealized = mtm_dollars - exposure
        expected_settle = theo_payoff_dollars - exposure
        total_unrealized += unrealized
        total_expected_settle += expected_settle

        pnl_color = "#4ade80" if realized >= 0 else "#f87171"
        unr_color = "#4ade80" if unrealized >= 0 else "#f87171"
        exp_color = "#4ade80" if expected_settle >= 0 else "#f87171"
        edge_color = "#4ade80" if edge_per_contract_c > 0 else "#f87171"
        strike_label = ticker.split("-")[-1] if ticker else ticker
        pos_rows += f"""
            <tr>
                <td style="font-family:monospace;font-size:12px">{strike_label}</td>
                <td style="text-align:right">{abs(qty):.0f} {side_label}</td>
                <td style="text-align:right">${exposure:.2f}</td>
                <td style="text-align:right">{avg_cost_c:.1f}c</td>
                <td style="text-align:right;color:#60a5fa">{theo_held_side}c</td>
                <td style="text-align:right;color:{edge_color};font-weight:bold">{edge_per_contract_c:+.1f}c</td>
                <td style="text-align:right">{mtm_px}c</td>
                <td style="text-align:right">${mtm_dollars:.2f}</td>
                <td style="text-align:right;color:{unr_color}">${unrealized:+.2f}</td>
                <td style="text-align:right;color:{exp_color}">${expected_settle:+.2f}</td>
                <td style="text-align:right;color:{pnl_color}">${realized:.2f}</td>
                <td style="text-align:right">${fees:.2f}</td>
            </tr>"""

    net_now = total_realized + total_unrealized - total_fees
    net_expected = total_realized + total_expected_settle - total_fees
    net_with_lip = net_now + total_dollars  # total_dollars is LIP earnings since inception

    realized_color = "#4ade80" if total_realized >= 0 else "#f87171"
    unrealized_color = "#4ade80" if total_unrealized >= 0 else "#f87171"
    expected_color = "#4ade80" if total_expected_settle >= 0 else "#f87171"
    net_now_color = "#4ade80" if net_now >= 0 else "#f87171"
    net_exp_color = "#4ade80" if net_expected >= 0 else "#f87171"
    net_lip_color = "#4ade80" if net_with_lip >= 0 else "#f87171"

    pnl_summary_section = f"""
    <h2>PnL Summary</h2>
    <div class="stats">
        <div class="stat">
            <div class="stat-label">Realized PnL</div>
            <div class="stat-value" style="color:{realized_color}">${total_realized:+.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Unrealized (MTM)</div>
            <div class="stat-value" style="color:{unrealized_color}">${total_unrealized:+.2f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">at current best bid</div>
        </div>
        <div class="stat">
            <div class="stat-label">Expected @ Settle</div>
            <div class="stat-value" style="color:{expected_color}">${total_expected_settle:+.2f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">qty × theo − cost</div>
        </div>
        <div class="stat">
            <div class="stat-label">Fees</div>
            <div class="stat-value" style="color:#f87171">−${total_fees:.2f}</div>
        </div>
        <div class="stat">
            <div class="stat-label">Open Exposure</div>
            <div class="stat-value">${total_exposure:.2f}</div>
        </div>
        <div class="stat" style="background:#1e3a2f">
            <div class="stat-label">Net Now (MTM)</div>
            <div class="stat-value" style="color:{net_now_color}">${net_now:+.2f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">realized + unrealized − fees</div>
        </div>
        <div class="stat" style="background:#1e3a2f">
            <div class="stat-label">Net @ Settle (est)</div>
            <div class="stat-value" style="color:{net_exp_color}">${net_expected:+.2f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">realized + expected − fees</div>
        </div>
        <div class="stat" style="background:#1a2744">
            <div class="stat-label">Net + LIP earned</div>
            <div class="stat-value" style="color:{net_lip_color}">${net_with_lip:+.2f}</div>
            <div style="font-size:10px;color:#94a3b8;margin-top:2px">net now + LIP since inception</div>
        </div>
    </div>
    """

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
        details summary {{ color: #60a5fa; }}
        details summary:hover {{ color: #93c5fd; }}
        details[open] summary {{ color: #4ade80; }}
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
    {maintenance_html}

    <div class="stats">
        <div class="stat">
            <div class="stat-label">{yf_fwd_label}</div>
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

    {theo_inputs_section}

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

    {history_section}

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

    {pnl_summary_section}

    <h2>Positions</h2>
    <table>
        <tr>
            <th>Market</th>
            <th style="text-align:right">Qty</th>
            <th style="text-align:right">Total Cost</th>
            <th style="text-align:right">Avg Cost</th>
            <th style="text-align:right">Theo (held)</th>
            <th style="text-align:right">Edge/contract</th>
            <th style="text-align:right">Mark</th>
            <th style="text-align:right">MTM Value</th>
            <th style="text-align:right">Unrealized</th>
            <th style="text-align:right">Expected @ Settle</th>
            <th style="text-align:right">Realized</th>
            <th style="text-align:right">Fees</th>
        </tr>
        {pos_rows if pos_rows else "<tr><td colspan=12 style='color:#64748b;text-align:center'>No open positions</td></tr>"}
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
