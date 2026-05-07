"""TruEvForwardSource — async polling cache for the EV-basket commodities.

Two backends:
  - **yfinance**: dense daily history; used for HG=F (copper), LIT
    (lithium ETF proxy), NICK.L (WisdomTree Nickel ETC), PA=F
    (palladium), PL=F (platinum). Synchronous library — wrapped in
    `asyncio.to_thread()`.
  - **TradingEconomics scrape** (`feeds.tradingeconomics.spot`): live
    spot only (no historicals). Used for cobalt (`COBALT_TE`) which has
    no clean yfinance ticker.

Mirrors the pattern of `feeds/pyth/forward.py`:
  - `start()` spawns an internal asyncio task running `_poll_loop()`
  - `stop()` cancels it
  - `latest_prices()` returns a copy of the in-memory cache

Cache keys are the source-specific symbol (yfinance ticker OR TE
sentinel like "COBALT_TE"). The basket-weights table in
`_truev_index.py` uses the same keys, so the index reconstruction
plumbing doesn't care which backend produced any given price.
"""

from __future__ import annotations

import asyncio
import logging
import time

import yfinance as yf

from feeds.tradingeconomics.spot import (
    TE_COBALT,
    get_te_spot,
)

logger = logging.getLogger(__name__)


# ── Symbol constants ────────────────────────────────────────────────
#
# yfinance-clean tickers:
#   HG=F     Copper (Comex)
#   LIT      Global X Lithium & Battery Tech ETF — proxy (CME LTH=F is
#            too illiquid for daily backtest).
#   NICK.L   WisdomTree Nickel ETC (LSE) — direct nickel exposure that
#            tracks LME 3-month nickel.
#   PA=F     Palladium (NYMEX)
#   PL=F     Platinum (NYMEX)
#
# TradingEconomics scrape sentinel:
#   COBALT_TE  Cobalt LME — TE has spot only (no historicals); LIVE
#              theo only. Backtest leaves cobalt unmodeled and
#              renormalizes the other 5 weights to 1.0.
COBALT_TE = "COBALT_TE"

TRUEV_PHASE1_SYMBOLS: tuple[str, ...] = (
    "HG=F", "LIT", "NICK.L", "PA=F", "PL=F", COBALT_TE,
)

# Subset that yfinance can serve (used by backtest helpers)
TRUEV_YFINANCE_SYMBOLS: tuple[str, ...] = (
    "HG=F", "LIT", "NICK.L", "PA=F", "PL=F",
)


class TruEvForwardSource:
    """Polls live commodity prices from yfinance and TE on a schedule.

    Args:
      symbols: list to track. Defaults to all 6 (5 yfinance + 1 TE
        cobalt). Backtest scenarios that don't need live cobalt can
        pass `TRUEV_YFINANCE_SYMBOLS`.
      poll_interval_s: time between polls (default 60).
      sanity_bounds: per-symbol (lo, hi) plausibility checks. Out-of-
        range values are dropped (kept stale) with a WARNING log.
    """

    DEFAULT_SANITY_BOUNDS: dict[str, tuple[float, float]] = {
        "HG=F": (1.0, 15.0),       # Copper $/lb
        "LIT": (10.0, 200.0),      # Global X Lithium ETF $/share
        "NICK.L": (1.0, 100.0),    # WisdomTree Nickel ETC $/share
        "PA=F": (200.0, 5000.0),   # Palladium $/oz
        "PL=F": (200.0, 5000.0),   # Platinum $/oz
        COBALT_TE: (10_000.0, 200_000.0),  # Cobalt $/tonne via TE
    }

    def __init__(
        self,
        *,
        symbols: tuple[str, ...] = TRUEV_PHASE1_SYMBOLS,
        poll_interval_s: float = 60.0,
        sanity_bounds: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._symbols = tuple(symbols)
        self._poll_interval_s = float(poll_interval_s)
        self._bounds = dict(sanity_bounds or self.DEFAULT_SANITY_BOUNDS)
        self._prices: dict[str, tuple[float, float]] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._symbols

    def latest_prices(self) -> dict[str, tuple[float, float]]:
        """Return a copy of the cache: {symbol: (price, fetched_at_ts)}.
        Empty dict until the first successful poll completes."""
        return dict(self._prices)

    def oldest_age_seconds(self, *, now: float | None = None) -> float:
        """Age of the OLDEST symbol in the cache. Returns infinity if
        any symbol is missing entirely (no successful poll yet)."""
        if len(self._prices) < len(self._symbols):
            return float("inf")
        ts_now = now if now is not None else time.time()
        return max(ts_now - ts for (_p, ts) in self._prices.values())

    async def start(self) -> None:
        """Kick off the background poll loop. Runs one poll immediately
        so callers don't have to wait for the first interval to
        elapse."""
        if self._running:
            return
        self._running = True
        await self._poll_once()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "TruEvForwardSource started (symbols=%s, interval=%.1fs)",
            self._symbols, self._poll_interval_s,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.info("TruEvForwardSource task ended: %s", exc)
            self._task = None

    async def _poll_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._poll_interval_s)
                if not self._running:
                    break
                await self._poll_once()
        except asyncio.CancelledError:
            raise

    async def _poll_once(self) -> None:
        try:
            new_prices = await asyncio.to_thread(self._fetch_sync)
        except Exception as exc:
            logger.warning("TruEvForwardSource poll failed: %s", exc)
            return

        now = time.time()
        for sym, price in new_prices.items():
            lo, hi = self._bounds.get(sym, (None, None))
            if lo is not None and hi is not None and not (lo <= price <= hi):
                logger.warning(
                    "TruEvForwardSource: %s price %.4f outside sanity bounds "
                    "[%.2f, %.2f] — dropping",
                    sym, price, lo, hi,
                )
                continue
            self._prices[sym] = (price, now)

    def _fetch_sync(self) -> dict[str, float]:
        """Synchronous fetch for all symbols. Routes per source:
        yfinance for normal tickers, TE scrape for sentinel symbols.
        """
        out: dict[str, float] = {}
        yf_syms = [s for s in self._symbols if s != COBALT_TE]
        if yf_syms:
            try:
                handle = yf.Tickers(" ".join(yf_syms))
            except Exception as exc:
                logger.warning("yf.Tickers init failed: %s", exc)
                handle = None
            for sym in yf_syms:
                try:
                    tk = handle.tickers.get(sym) if handle is not None else None
                    if tk is None:
                        tk = yf.Ticker(sym)
                    hist = tk.history(period="1d")
                    if hist.empty:
                        logger.info("yfinance: no 1d data for %s", sym)
                        continue
                    close = float(hist["Close"].iloc[-1])
                    if close <= 0:
                        logger.info("yfinance: %s close %.4f ≤ 0", sym, close)
                        continue
                    out[sym] = close
                except Exception as exc:
                    logger.warning("yfinance fetch failed for %s: %s", sym, exc)

        # TE scrapes (synchronous httpx). One commodity per sentinel.
        if COBALT_TE in self._symbols:
            price = get_te_spot(TE_COBALT)
            if price is not None and price > 0:
                out[COBALT_TE] = price
        return out
