"""ACT-01 Phase 1a — REST polling sentinel for KXSOYBEANW.

Polls public Kalshi REST endpoints (no auth) for:
  1. Orderbook snapshots per active market
  2. Public trade prints
  3. Event/market metadata and settlement status

Persists to DuckDB. Runs standalone via `python -m feeds.kalshi.capture`.

Endpoints used (all public, no auth):
  GET /trade-api/v2/events          — list events by series_ticker
  GET /trade-api/v2/markets/{ticker}/orderbook — orderbook snapshot
  GET /trade-api/v2/markets/trades  — public trade tape
  GET /trade-api/v2/markets/{ticker} — market metadata
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from feeds.kalshi.models import (
    EventInfo,
    MarketInfo,
    OrderbookLevel,
    OrderbookSnapshot,
    Trade,
)
from feeds.kalshi.store import CaptureStore

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elections.kalshi.com"
_API_PREFIX = "/trade-api/v2"

# Defaults
_DEFAULT_OB_INTERVAL_S = 60
_DEFAULT_EVENT_INTERVAL_S = 300
_DEFAULT_DB_PATH = "data/capture/kalshi_capture.duckdb"
_SERIES_TICKER = "KXSOYBEANW"
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 2.0
_HTTP_TIMEOUT_S = 10.0


def _cents(v: Any) -> int:
    """Convert a dollars string/float to integer cents."""
    if v is None or v == "":
        return 0
    return int(round(float(v) * 100.0))


def _fp_int(v: Any) -> int:
    """Convert a floating-point integer field to int."""
    if v is None or v == "":
        return 0
    return int(round(float(v)))


def _parse_iso(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


class KalshiCaptureSentinel:
    """Async REST polling sentinel for KXSOYBEANW capture.

    No authentication required — uses only public read-only endpoints.
    """

    def __init__(
        self,
        *,
        db_path: str | Path = _DEFAULT_DB_PATH,
        ob_interval_s: float = _DEFAULT_OB_INTERVAL_S,
        event_interval_s: float = _DEFAULT_EVENT_INTERVAL_S,
        series_ticker: str = _SERIES_TICKER,
    ) -> None:
        self._db_path = Path(db_path)
        self._ob_interval_s = ob_interval_s
        self._event_interval_s = event_interval_s
        self._series_ticker = series_ticker
        self._active_markets: list[str] = []
        self._active_events: dict[str, EventInfo] = {}
        self._store: CaptureStore | None = None
        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the capture loops."""
        if self._running:
            raise RuntimeError("sentinel already running")
        self._running = True
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = CaptureStore(str(self._db_path))
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=_HTTP_TIMEOUT_S,
            headers={"Accept": "application/json"},
        )
        # Initial event discovery before starting loops
        await self._refresh_events()
        logger.info(
            "capture sentinel started: series=%s, markets=%d, ob_interval=%ds",
            self._series_ticker,
            len(self._active_markets),
            self._ob_interval_s,
        )
        self._tasks = [
            asyncio.create_task(self._event_loop(), name="event_loop"),
            asyncio.create_task(self._orderbook_loop(), name="orderbook_loop"),
            asyncio.create_task(self._trades_loop(), name="trades_loop"),
        ]

    async def stop(self) -> None:
        """Gracefully stop all capture loops."""
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._store:
            self._store.close()
            self._store = None
        logger.info("capture sentinel stopped")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def active_markets(self) -> list[str]:
        return list(self._active_markets)

    # --- HTTP helpers ---

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with retry and 429 backoff."""
        assert self._client is not None
        url = _API_PREFIX + path
        for attempt in range(_MAX_RETRIES):
            try:
                r = await self._client.get(url, params=params)
                if r.status_code == 429:
                    wait = _BACKOFF_BASE_S * (2 ** attempt)
                    logger.warning("429 on %s, backing off %.1fs", path, wait)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                raise
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                wait = _BACKOFF_BASE_S * (2 ** attempt)
                logger.warning(
                    "request error on %s (attempt %d/%d): %s, retrying in %.1fs",
                    path, attempt + 1, _MAX_RETRIES, exc, wait,
                )
                await asyncio.sleep(wait)
        raise httpx.ConnectError(f"failed after {_MAX_RETRIES} retries: {path}")

    # --- Event discovery ---

    async def _refresh_events(self) -> None:
        """Discover active KXSOYBEANW events and their child markets."""
        try:
            data = await self._get(
                "/events",
                params={
                    "series_ticker": self._series_ticker,
                    "status": "open",
                    "limit": 50,
                },
            )
        except Exception:
            logger.exception("failed to refresh events")
            return

        now = datetime.now(timezone.utc)
        events = data.get("events") or []
        new_events: dict[str, EventInfo] = {}
        new_markets: list[str] = []

        for ev in events:
            event_ticker = ev.get("event_ticker", "")
            markets_raw = ev.get("markets") or []
            market_tickers = [m.get("ticker", "") for m in markets_raw if m.get("ticker")]
            info = EventInfo(
                event_ticker=event_ticker,
                series_ticker=ev.get("series_ticker", self._series_ticker),
                title=ev.get("title", ""),
                status=ev.get("status", ""),
                market_tickers=market_tickers,
                captured_at=now,
            )
            new_events[event_ticker] = info
            new_markets.extend(market_tickers)

            # Also capture market-level metadata
            for m in markets_raw:
                ticker = m.get("ticker", "")
                if not ticker:
                    continue
                market_info = self._parse_market(m, event_ticker, now)
                if self._store and market_info:
                    self._store.write_market(market_info)

        if new_markets != self._active_markets:
            added = set(new_markets) - set(self._active_markets)
            removed = set(self._active_markets) - set(new_markets)
            if added:
                logger.info("new markets discovered: %s", sorted(added))
            if removed:
                logger.info("markets removed: %s", sorted(removed))

        self._active_events = new_events
        self._active_markets = new_markets
        logger.debug("event refresh: %d events, %d markets", len(new_events), len(new_markets))

    def _parse_market(self, m: dict, event_ticker: str, now: datetime) -> MarketInfo | None:
        ticker = m.get("ticker", "")
        if not ticker:
            return None
        return MarketInfo(
            ticker=ticker,
            event_ticker=event_ticker,
            title=m.get("title", ""),
            status=m.get("status", ""),
            yes_bid_cents=_cents(m.get("yes_bid_dollars")),
            yes_ask_cents=_cents(m.get("yes_ask_dollars")),
            last_price_cents=_cents(m.get("last_price_dollars")),
            volume=_fp_int(m.get("volume_fp", 0)),
            open_interest=_fp_int(m.get("open_interest_fp", 0)),
            result=m.get("result", ""),
            floor_strike=_safe_float(m.get("floor_strike")),
            cap_strike=_safe_float(m.get("cap_strike")),
            captured_at=now,
        )

    # --- Polling loops ---

    async def _event_loop(self) -> None:
        """Refresh events and market metadata at event_interval_s cadence."""
        while self._running:
            try:
                await asyncio.sleep(self._event_interval_s)
                await self._refresh_events()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("error in event loop")

    async def _orderbook_loop(self) -> None:
        """Poll orderbooks for all active markets at ob_interval_s cadence."""
        while self._running:
            try:
                await asyncio.sleep(self._ob_interval_s)
                if not self._active_markets:
                    logger.debug("no active markets, skipping orderbook poll")
                    continue
                for ticker in self._active_markets:
                    if not self._running:
                        return
                    await self._capture_orderbook(ticker)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("error in orderbook loop")

    async def _trades_loop(self) -> None:
        """Poll public trades at ob_interval_s cadence."""
        last_cursor: str | None = None
        while self._running:
            try:
                await asyncio.sleep(self._ob_interval_s)
                last_cursor = await self._capture_trades(last_cursor)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("error in trades loop")

    async def _capture_orderbook(self, ticker: str) -> None:
        """Fetch and store one orderbook snapshot."""
        try:
            data = await self._get(f"/markets/{ticker}/orderbook")
        except Exception:
            logger.warning("failed to fetch orderbook for %s", ticker)
            return

        now = datetime.now(timezone.utc)
        ob_data = data.get("orderbook_fp") or data.get("orderbook") or {}
        yes_raw = ob_data.get("yes_dollars") or ob_data.get("yes") or []
        no_raw = ob_data.get("no_dollars") or ob_data.get("no") or []

        yes_levels = [OrderbookLevel(price_cents=_cents(p), size=_fp_int(s)) for p, s in yes_raw]
        no_levels = [OrderbookLevel(price_cents=_cents(p), size=_fp_int(s)) for p, s in no_raw]

        snapshot = OrderbookSnapshot(
            ticker=ticker,
            captured_at=now,
            yes_levels=yes_levels,
            no_levels=no_levels,
        )
        if self._store:
            self._store.write_orderbook(snapshot)

    async def _capture_trades(self, cursor: str | None) -> str | None:
        """Fetch and store new public trades across all KXSOYBEANW markets."""
        params: dict[str, Any] = {"limit": 200}
        if cursor:
            params["cursor"] = cursor

        # Poll trades for each active market
        new_cursor = cursor
        for ticker in self._active_markets:
            if not self._running:
                return new_cursor
            try:
                params_with_ticker = {**params, "ticker": ticker}
                data = await self._get("/markets/trades", params=params_with_ticker)
            except Exception:
                logger.warning("failed to fetch trades for %s", ticker)
                continue

            trades_raw = data.get("trades") or []
            resp_cursor = data.get("cursor")
            if resp_cursor:
                new_cursor = resp_cursor

            for t in trades_raw:
                trade = _parse_trade(t)
                if trade and self._store:
                    self._store.write_trade(trade)

        return new_cursor


def _parse_trade(t: dict) -> Trade | None:
    """Parse a single trade from the REST response."""
    ticker = t.get("ticker", "")
    trade_id = t.get("trade_id", "")
    if not ticker or not trade_id:
        return None
    return Trade(
        ticker=ticker,
        trade_id=trade_id,
        count=_fp_int(t.get("count", 0)),
        yes_price_cents=_cents(t.get("yes_price_dollars")),
        taker_side=t.get("taker_side", ""),
        created_time=_parse_iso(t.get("created_time")),
    )


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


async def run_sentinel(
    *,
    db_path: str = _DEFAULT_DB_PATH,
    ob_interval_s: float = _DEFAULT_OB_INTERVAL_S,
    event_interval_s: float = _DEFAULT_EVENT_INTERVAL_S,
    series_ticker: str = _SERIES_TICKER,
) -> None:
    """Run the capture sentinel until interrupted."""
    sentinel = KalshiCaptureSentinel(
        db_path=db_path,
        ob_interval_s=ob_interval_s,
        event_interval_s=event_interval_s,
        series_ticker=series_ticker,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    await sentinel.start()
    try:
        await stop_event.wait()
    finally:
        await sentinel.stop()
