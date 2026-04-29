"""Tests for ACT-01 Phase 1a — Kalshi REST capture sentinel.

Uses mock httpx responses and an in-memory DuckDB to verify:
  - Event discovery and market enumeration
  - Orderbook snapshot capture and storage
  - Trade capture and deduplication
  - Market metadata capture
  - Error handling (429, network errors)
  - Sentinel lifecycle (start/stop)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from feeds.kalshi.capture import KalshiCaptureSentinel, _cents, _fp_int, _parse_trade
from feeds.kalshi.models import OrderbookLevel, OrderbookSnapshot, Trade
from feeds.kalshi.store import CaptureStore


# --- Unit tests for helpers ---


class TestHelpers:
    def test_cents_from_string(self):
        assert _cents("0.55") == 55

    def test_cents_from_float(self):
        assert _cents(0.55) == 55

    def test_cents_none(self):
        assert _cents(None) == 0

    def test_cents_empty(self):
        assert _cents("") == 0

    def test_fp_int(self):
        assert _fp_int("100.0") == 100

    def test_fp_int_none(self):
        assert _fp_int(None) == 0

    def test_parse_trade_valid(self):
        raw = {
            "ticker": "KXSOYBEANW-26APR27-B1050",
            "trade_id": "abc-123",
            "count": 5,
            "yes_price_dollars": "0.45",
            "taker_side": "yes",
            "created_time": "2026-04-27T10:00:00Z",
        }
        trade = _parse_trade(raw)
        assert trade is not None
        assert trade.ticker == "KXSOYBEANW-26APR27-B1050"
        assert trade.trade_id == "abc-123"
        assert trade.count == 5
        assert trade.yes_price_cents == 45
        assert trade.taker_side == "yes"

    def test_parse_trade_missing_ticker(self):
        raw = {"trade_id": "abc", "count": 1}
        assert _parse_trade(raw) is None

    def test_parse_trade_missing_trade_id(self):
        raw = {"ticker": "KXSOYBEANW-26APR27-B1050", "count": 1}
        assert _parse_trade(raw) is None


# --- CaptureStore tests ---


class TestCaptureStore:
    def test_schema_creation(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        assert store.count("orderbook_snapshots") == 0
        assert store.count("trades") == 0
        assert store.count("market_events") == 0
        store.close()

    def test_write_orderbook(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        now = datetime.now(timezone.utc)
        snapshot = OrderbookSnapshot(
            ticker="KXSOYBEANW-26APR27-B1050",
            captured_at=now,
            yes_levels=[OrderbookLevel(price_cents=45, size=100)],
            no_levels=[OrderbookLevel(price_cents=55, size=200)],
        )
        store.write_orderbook(snapshot)
        assert store.count("orderbook_snapshots") == 1
        store.close()

    def test_write_trade(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        trade = Trade(
            ticker="KXSOYBEANW-26APR27-B1050",
            trade_id="trade-001",
            count=10,
            yes_price_cents=42,
            taker_side="yes",
            created_time=datetime.now(timezone.utc),
        )
        store.write_trade(trade)
        assert store.count("trades") == 1
        store.close()

    def test_trade_dedup(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        trade = Trade(
            ticker="KXSOYBEANW-26APR27-B1050",
            trade_id="trade-001",
            count=10,
            yes_price_cents=42,
            taker_side="yes",
            created_time=datetime.now(timezone.utc),
        )
        store.write_trade(trade)
        store.write_trade(trade)  # duplicate
        assert store.count("trades") == 1
        store.close()

    def test_write_market(self, tmp_path):
        from feeds.kalshi.models import MarketInfo

        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        market = MarketInfo(
            ticker="KXSOYBEANW-26APR27-B1050",
            event_ticker="KXSOYBEANW-26APR27",
            title="Soybeans $10.50-$10.60",
            status="open",
            yes_bid_cents=45,
            yes_ask_cents=55,
            last_price_cents=50,
            volume=100,
            open_interest=500,
            result="",
            floor_strike=10.50,
            cap_strike=10.60,
            captured_at=datetime.now(timezone.utc),
        )
        store.write_market(market)
        assert store.count("market_events") == 1
        store.close()

    def test_export_parquet(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        store = CaptureStore(db_path)
        now = datetime.now(timezone.utc)
        snapshot = OrderbookSnapshot(
            ticker="KXSOYBEANW-26APR27-B1050",
            captured_at=now,
            yes_levels=[OrderbookLevel(price_cents=45, size=100)],
            no_levels=[],
        )
        store.write_orderbook(snapshot)
        parquet_path = str(tmp_path / "ob.parquet")
        store.export_parquet("orderbook_snapshots", parquet_path)
        import os
        assert os.path.exists(parquet_path)
        store.close()


# --- Sentinel integration tests ---


def _mock_events_response():
    return {
        "events": [
            {
                "event_ticker": "KXSOYBEANW-26APR27",
                "series_ticker": "KXSOYBEANW",
                "title": "Soybeans Weekly 26 Apr 2027",
                "status": "open",
                "markets": [
                    {
                        "ticker": "KXSOYBEANW-26APR27-B1050",
                        "title": "$10.50-$10.60",
                        "status": "open",
                        "yes_bid_dollars": "0.45",
                        "yes_ask_dollars": "0.55",
                        "last_price_dollars": "0.50",
                        "volume_fp": "100",
                        "open_interest_fp": "500",
                        "result": "",
                        "floor_strike": "10.50",
                        "cap_strike": "10.60",
                    },
                    {
                        "ticker": "KXSOYBEANW-26APR27-B1060",
                        "title": "$10.60-$10.70",
                        "status": "open",
                        "yes_bid_dollars": "0.30",
                        "yes_ask_dollars": "0.40",
                        "last_price_dollars": "0.35",
                        "volume_fp": "50",
                        "open_interest_fp": "200",
                        "result": "",
                        "floor_strike": "10.60",
                        "cap_strike": "10.70",
                    },
                ],
            }
        ],
        "cursor": None,
    }


def _mock_orderbook_response(ticker: str):
    return {
        "orderbook_fp": {
            "yes_dollars": [["0.45", "100"], ["0.44", "200"]],
            "no_dollars": [["0.55", "150"]],
        }
    }


def _mock_trades_response():
    return {
        "trades": [
            {
                "ticker": "KXSOYBEANW-26APR27-B1050",
                "trade_id": "t-001",
                "count": 5,
                "yes_price_dollars": "0.45",
                "taker_side": "yes",
                "created_time": "2026-04-27T10:00:00Z",
            }
        ],
        "cursor": None,
    }


class TestSentinelLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, tmp_path):
        sentinel = KalshiCaptureSentinel(
            db_path=str(tmp_path / "test.duckdb"),
            ob_interval_s=1.0,
            event_interval_s=5.0,
        )

        async def mock_get(path, params=None):
            """Mock HTTP GET that returns appropriate responses."""
            if "/events" in path:
                return _mock_events_response()
            if "/orderbook" in path:
                return _mock_orderbook_response("")
            if "/trades" in path:
                return _mock_trades_response()
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            await sentinel.start()
            assert sentinel.running
            assert len(sentinel.active_markets) == 2
            await sentinel.stop()
            assert not sentinel.running

    @pytest.mark.asyncio
    async def test_double_start_raises(self, tmp_path):
        sentinel = KalshiCaptureSentinel(
            db_path=str(tmp_path / "test.duckdb"),
        )

        async def mock_get(path, params=None):
            if "/events" in path:
                return _mock_events_response()
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            await sentinel.start()
            with pytest.raises(RuntimeError, match="already running"):
                await sentinel.start()
            await sentinel.stop()

    @pytest.mark.asyncio
    async def test_captures_orderbook(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        sentinel = KalshiCaptureSentinel(
            db_path=db_path,
            ob_interval_s=0.1,
            event_interval_s=60.0,
        )

        call_count = 0

        async def mock_get(path, params=None):
            nonlocal call_count
            if "/events" in path:
                return _mock_events_response()
            if "/orderbook" in path:
                call_count += 1
                return _mock_orderbook_response("")
            if "/trades" in path:
                return _mock_trades_response()
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            await sentinel.start()
            # Let it poll once
            await asyncio.sleep(0.3)
            await sentinel.stop()

        # Verify data was written
        store = CaptureStore(db_path)
        assert store.count("orderbook_snapshots") > 0
        assert store.count("market_events") > 0
        store.close()

    @pytest.mark.asyncio
    async def test_captures_trades(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        sentinel = KalshiCaptureSentinel(
            db_path=db_path,
            ob_interval_s=0.1,
            event_interval_s=60.0,
        )

        async def mock_get(path, params=None):
            if "/events" in path:
                return _mock_events_response()
            if "/orderbook" in path:
                return _mock_orderbook_response("")
            if "/trades" in path:
                return _mock_trades_response()
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            await sentinel.start()
            await asyncio.sleep(0.3)
            await sentinel.stop()

        store = CaptureStore(db_path)
        assert store.count("trades") > 0
        store.close()

    @pytest.mark.asyncio
    async def test_handles_empty_events(self, tmp_path):
        sentinel = KalshiCaptureSentinel(
            db_path=str(tmp_path / "test.duckdb"),
        )

        async def mock_get(path, params=None):
            if "/events" in path:
                return {"events": [], "cursor": None}
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            await sentinel.start()
            assert len(sentinel.active_markets) == 0
            await sentinel.stop()

    @pytest.mark.asyncio
    async def test_handles_event_refresh_failure(self, tmp_path):
        sentinel = KalshiCaptureSentinel(
            db_path=str(tmp_path / "test.duckdb"),
        )

        call_count = 0

        async def mock_get(path, params=None):
            nonlocal call_count
            if "/events" in path:
                call_count += 1
                if call_count == 1:
                    raise Exception("network error")
                return _mock_events_response()
            return {}

        with patch.object(sentinel, "_get", side_effect=mock_get):
            # First call fails, but sentinel should not crash
            await sentinel.start()
            assert len(sentinel.active_markets) == 0
            await sentinel.stop()
