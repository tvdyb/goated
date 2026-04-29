"""Data classes for Kalshi REST capture snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class OrderbookLevel:
    price_cents: int
    size: int


@dataclass(frozen=True, slots=True)
class OrderbookSnapshot:
    ticker: str
    captured_at: datetime
    yes_levels: list[OrderbookLevel]
    no_levels: list[OrderbookLevel]


@dataclass(frozen=True, slots=True)
class Trade:
    ticker: str
    trade_id: str
    count: int
    yes_price_cents: int
    taker_side: str
    created_time: datetime


@dataclass(frozen=True, slots=True)
class MarketInfo:
    ticker: str
    event_ticker: str
    title: str
    status: str
    yes_bid_cents: int
    yes_ask_cents: int
    last_price_cents: int
    volume: int
    open_interest: int
    result: str
    floor_strike: float | None
    cap_strike: float | None
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class EventInfo:
    event_ticker: str
    series_ticker: str
    title: str
    status: str
    market_tickers: list[str]
    captured_at: datetime
