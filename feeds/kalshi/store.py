"""DuckDB storage backend for Kalshi REST capture.

Three tables:
  - orderbook_snapshots: per-market, per-timestamp full-depth orderbook
  - trades: public trade prints
  - market_events: market metadata + settlement status
"""

from __future__ import annotations

import json
import logging

import duckdb

from feeds.kalshi.models import MarketInfo, OrderbookSnapshot, Trade

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    ticker         VARCHAR NOT NULL,
    captured_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    yes_levels     VARCHAR NOT NULL,
    no_levels      VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    ticker          VARCHAR NOT NULL,
    trade_id        VARCHAR NOT NULL,
    count           INTEGER NOT NULL,
    yes_price_cents INTEGER NOT NULL,
    taker_side      VARCHAR NOT NULL,
    created_time    TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (trade_id)
);

CREATE TABLE IF NOT EXISTS market_events (
    ticker          VARCHAR NOT NULL,
    event_ticker    VARCHAR NOT NULL,
    title           VARCHAR,
    status          VARCHAR NOT NULL,
    yes_bid_cents   INTEGER,
    yes_ask_cents   INTEGER,
    last_price_cents INTEGER,
    volume          INTEGER,
    open_interest   INTEGER,
    result          VARCHAR,
    floor_strike    DOUBLE,
    cap_strike      DOUBLE,
    captured_at     TIMESTAMP WITH TIME ZONE NOT NULL
);
"""


class CaptureStore:
    """DuckDB-backed store for captured Kalshi data."""

    def __init__(self, db_path: str) -> None:
        self._conn = duckdb.connect(db_path)
        self._conn.execute("SET TimeZone='UTC'")
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)

    def write_orderbook(self, snapshot: OrderbookSnapshot) -> None:
        yes_json = json.dumps(
            [[lv.price_cents, lv.size] for lv in snapshot.yes_levels]
        )
        no_json = json.dumps(
            [[lv.price_cents, lv.size] for lv in snapshot.no_levels]
        )
        self._conn.execute(
            "INSERT INTO orderbook_snapshots (ticker, captured_at, yes_levels, no_levels) "
            "VALUES (?, ?, ?, ?)",
            [snapshot.ticker, snapshot.captured_at, yes_json, no_json],
        )

    def write_trade(self, trade: Trade) -> None:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO trades "
                "(ticker, trade_id, count, yes_price_cents, taker_side, created_time) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    trade.ticker,
                    trade.trade_id,
                    trade.count,
                    trade.yes_price_cents,
                    trade.taker_side,
                    trade.created_time,
                ],
            )
        except duckdb.ConstraintException:
            pass  # duplicate trade_id, already captured

    def write_market(self, market: MarketInfo) -> None:
        self._conn.execute(
            "INSERT INTO market_events "
            "(ticker, event_ticker, title, status, yes_bid_cents, yes_ask_cents, "
            "last_price_cents, volume, open_interest, result, floor_strike, "
            "cap_strike, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                market.ticker,
                market.event_ticker,
                market.title,
                market.status,
                market.yes_bid_cents,
                market.yes_ask_cents,
                market.last_price_cents,
                market.volume,
                market.open_interest,
                market.result,
                market.floor_strike,
                market.cap_strike,
                market.captured_at,
            ],
        )

    def count(self, table: str) -> int:
        result = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return result[0] if result else 0

    def close(self) -> None:
        self._conn.close()

    def export_parquet(self, table: str, path: str) -> None:
        self._conn.execute(f"COPY {table} TO '{path}' (FORMAT PARQUET)")
