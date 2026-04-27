"""Minimal Kalshi REST client for the trufaidp 15-strike market maker.

Live base: https://api.elections.kalshi.com/trade-api/v2
Live WS:   wss://api.elections.kalshi.com/trade-api/ws/v2  (same auth headers).

Auth headers on every request:
    KALSHI-ACCESS-KEY        UUID api key id
    KALSHI-ACCESS-TIMESTAMP  ms-since-epoch as string
    KALSHI-ACCESS-SIGNATURE  base64(RSA-PSS-SHA256, MGF1-SHA256, salt=DIGEST_LENGTH)
Signed message is `timestamp + method + path` with the path stripped of any
query string. PKCS1v15 is rejected. Ref docs.kalshi.com/getting_started/api_keys.

Liquidity Incentive Program (active through 2026-09-01,
help.kalshi.com/en/articles/13823851): per-second order-book snapshots score
`size * distance_multiplier` per resting order; reward share =
score / total_score * daily_pool ($10..$1,000 per market per day). Best
bid/ask gets multiplier 1.0; deeper levels decay via a per-market Discount
Factor. Target size 100..20,000 contracts. Fills do *not* score — only
*resting* size at snapshot time. There is no documented "post_only required"
gate, but `post_only=true` is the safe MM default. Open: the user-mentioned
"top 300 contracts per side count" cap is not verbatim in the public LIP
page — treat as an internal cap, not an API rule.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_BASE_URL = "https://api.elections.kalshi.com"
_API_PREFIX = "/trade-api/v2"


class Side(str, Enum):
    YES_BUY = "yes_buy"
    YES_SELL = "yes_sell"
    NO_BUY = "no_buy"
    NO_SELL = "no_sell"


@dataclass(frozen=True, slots=True)
class OrderId:
    value: str


@dataclass(frozen=True, slots=True)
class Market:
    ticker: str
    yes_bid: int
    yes_ask: int
    yes_bid_size: int
    yes_ask_size: int
    last_price: int


@dataclass(frozen=True, slots=True)
class OrderBook:
    ticker: str
    yes: list[tuple[int, int]]
    no: list[tuple[int, int]]


@dataclass(frozen=True, slots=True)
class Position:
    ticker: str
    position: int
    avg_cost_cents: int


@dataclass(frozen=True, slots=True)
class Fill:
    ticker: str
    side: Side
    qty: int
    price_cents: int
    ts_ns: int


def _dollars_to_cents(v: Any) -> int:
    if v is None or v == "":
        raise ValueError(f"missing dollars field: {v!r}")
    return int(round(float(v) * 100.0))


def _fp_to_int(v: Any) -> int:
    if v is None or v == "":
        raise ValueError(f"missing fp field: {v!r}")
    return int(round(float(v)))


def _iso_to_ns(s: str) -> int:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return int(datetime.fromisoformat(s).timestamp() * 1_000_000_000)


class KalshiClient:
    def __init__(self, timeout: float = 5.0) -> None:
        key_id = os.environ["KALSHI_API_KEY_ID"]
        key_path = os.environ["KALSHI_API_PRIVATE_KEY_PATH"]
        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError(f"private key at {key_path} is not RSA")
        self._key_id = key_id
        self._key = key
        self._http = httpx.Client(base_url=_BASE_URL, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _sign(self, method: str, path: str) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        msg = (ts + method + path).encode("utf-8")
        sig = self._key.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("ascii"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, *,
                 params: dict | None = None, json: dict | None = None) -> dict:
        url_path = _API_PREFIX + path
        headers = self._sign(method, url_path)
        r = self._http.request(method, url_path, params=params, json=json, headers=headers)
        r.raise_for_status()
        return r.json()

    def get_market(self, ticker: str) -> Market:
        data = self._request("GET", f"/markets/{ticker}")
        m = data["market"]
        return Market(
            ticker=m["ticker"],
            yes_bid=_dollars_to_cents(m["yes_bid_dollars"]),
            yes_ask=_dollars_to_cents(m["yes_ask_dollars"]),
            yes_bid_size=_fp_to_int(m.get("yes_bid_size_fp", 0)),
            yes_ask_size=_fp_to_int(m.get("yes_ask_size_fp", 0)),
            last_price=_dollars_to_cents(m.get("last_price_dollars", "0")),
        )

    def get_orderbook(self, ticker: str) -> OrderBook:
        data = self._request("GET", f"/markets/{ticker}/orderbook")
        ob = data["orderbook_fp"]
        yes_raw = ob.get("yes_dollars") or []
        no_raw = ob.get("no_dollars") or []
        yes = [(_dollars_to_cents(p), _fp_to_int(c)) for p, c in yes_raw]
        no = [(_dollars_to_cents(p), _fp_to_int(c)) for p, c in no_raw]
        return OrderBook(ticker=ticker, yes=yes, no=no)

    def get_positions(self) -> list[Position]:
        data = self._request("GET", "/portfolio/positions",
                             params={"limit": 1000, "count_filter": "position"})
        out: list[Position] = []
        for p in data.get("market_positions") or []:
            qty = _fp_to_int(p["position_fp"])
            if qty == 0:
                exposure_cents = 0
            else:
                exposure_cents = _dollars_to_cents(p["market_exposure_dollars"])
            avg = exposure_cents // abs(qty) if qty else 0
            out.append(Position(ticker=p["ticker"], position=qty, avg_cost_cents=avg))
        return out

    def place_order(self, ticker: str, side: Side, qty: int, price_cents: int,
                    client_order_id: str, *, post_only: bool = True,
                    time_in_force: str = "good_till_canceled") -> OrderId:
        if not 1 <= price_cents <= 99:
            raise ValueError(f"price_cents must be in [1,99], got {price_cents}")
        if qty < 1:
            raise ValueError(f"qty must be >=1, got {qty}")
        if side in (Side.YES_BUY, Side.YES_SELL):
            yes_side, action = "yes", ("buy" if side is Side.YES_BUY else "sell")
            price_field = {"yes_price": price_cents}
        else:
            yes_side, action = "no", ("buy" if side is Side.NO_BUY else "sell")
            price_field = {"no_price": price_cents}
        body = {
            "ticker": ticker,
            "side": yes_side,
            "action": action,
            "count": qty,
            "type": "limit",
            "client_order_id": client_order_id,
            "post_only": post_only,
            "time_in_force": time_in_force,
            **price_field,
        }
        data = self._request("POST", "/portfolio/orders", json=body)
        order = data["order"]
        oid = order.get("order_id")
        if not isinstance(oid, str):
            raise ValueError(f"unexpected create-order response shape: {data!r}")
        return OrderId(oid)

    def cancel_order(self, order_id: OrderId | str) -> None:
        oid = order_id.value if isinstance(order_id, OrderId) else order_id
        self._request("DELETE", f"/portfolio/orders/{oid}")

    def get_fills(self, ticker: str, since_ts: int | None = None) -> list[Fill]:
        params: dict[str, Any] = {"ticker": ticker, "limit": 1000}
        if since_ts is not None:
            params["min_ts"] = since_ts
        data = self._request("GET", "/portfolio/fills", params=params)
        out: list[Fill] = []
        for f in data.get("fills") or []:
            action = f["action"]
            yn = f["side"]
            if yn == "yes":
                side = Side.YES_BUY if action == "buy" else Side.YES_SELL
                price = _dollars_to_cents(f["yes_price_dollars"])
            elif yn == "no":
                side = Side.NO_BUY if action == "buy" else Side.NO_SELL
                price = _dollars_to_cents(f["no_price_dollars"])
            else:
                raise ValueError(f"unexpected fill side: {yn!r}")
            ts_raw = f.get("created_time") or f.get("ts")
            if isinstance(ts_raw, str):
                ts_ns = _iso_to_ns(ts_raw)
            elif isinstance(ts_raw, int):
                ts_ns = ts_raw * 1_000_000
            else:
                raise ValueError(f"missing fill timestamp in {f!r}")
            out.append(Fill(
                ticker=f["ticker"],
                side=side,
                qty=_fp_to_int(f["count_fp"]),
                price_cents=price,
                ts_ns=ts_ns,
            ))
        return out
