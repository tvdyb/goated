"""TruEvForwardSource — async yfinance polling cache for the 4 modeled
EV-basket commodities.

Mirrors the pattern of `feeds/pyth/forward.py`:
  - `start()` spawns an internal asyncio task running `_poll_loop()`
  - `stop()` cancels it
  - `latest_prices()` returns a copy of the in-memory cache (price + ts)
  - readers check timestamps for staleness; the source itself only
    serves what it has.

yfinance is synchronous, so each poll wraps the call in
`asyncio.to_thread()` to avoid blocking the event loop. One call
batches all symbols via `yf.Tickers(...)`.
"""

from __future__ import annotations

import asyncio
import logging
import time

import yfinance as yf

logger = logging.getLogger(__name__)


# Phase 1 symbols. We use LIT (Global X Lithium & Battery Tech ETF) as
# a proxy for lithium because:
#   - LTH=F (CME Lithium Hydroxide CIF CJK futures) is too illiquid on
#     yfinance — only sporadic daily prints, can't backtest.
#   - LIT has dense daily history and tracks lithium moves with
#     ~0.7–0.85 correlation. Imperfect but tradeable.
# Phase 2 should add a real lithium fix (Fastmarkets / Argus / paid TE
# API) for proper accuracy.
TRUEV_PHASE1_SYMBOLS: tuple[str, ...] = ("HG=F", "LIT", "PA=F", "PL=F")


class TruEvForwardSource:
    """Polls yfinance for EV-basket commodity prices on a schedule.

    Cache shape: `_prices: dict[symbol, (price, fetched_at_unix_ts)]`.
    Readers call `latest_prices()` and check ages themselves.

    Args:
      symbols: yfinance tickers to poll. Defaults to TRUEV_PHASE1_SYMBOLS.
      poll_interval_s: time between polls (default 60).
      sanity_bounds: per-symbol (lo, hi) plausibility checks. Returned
        values outside the bounds are dropped (kept stale) with a
        WARNING log — guards against bad yfinance prints.
    """

    # Plausibility bounds per Apr 2026 levels — wide enough to allow
    # 50% moves either direction. If a yfinance print is way off, we
    # log and refuse to update that symbol.
    DEFAULT_SANITY_BOUNDS: dict[str, tuple[float, float]] = {
        "HG=F": (1.0, 15.0),     # Copper $/lb
        "LIT": (10.0, 200.0),    # Global X Lithium ETF $/share
        "PA=F": (200.0, 5000.0), # Palladium $/oz
        "PL=F": (200.0, 5000.0), # Platinum $/oz
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
        """Kick off the background poll loop. Returns after spawning
        the task; the first successful refresh may not have happened yet
        — call `prime()` to await the first poll synchronously."""
        if self._running:
            return
        self._running = True
        # Run one poll immediately so callers don't have to wait for the
        # first interval to elapse.
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
        """Synchronous yfinance fetch. Called via asyncio.to_thread().
        Returns {symbol: price} for symbols that returned a valid
        latest close. Missing symbols are simply absent."""
        out: dict[str, float] = {}
        # `yf.Tickers` lets us batch the request; iterate per-symbol
        # for fault isolation (one bad symbol shouldn't blank the rest).
        try:
            handle = yf.Tickers(" ".join(self._symbols))
        except Exception as exc:
            logger.warning("yf.Tickers init failed: %s", exc)
            return out
        for sym in self._symbols:
            try:
                tk = handle.tickers.get(sym)
                if tk is None:
                    # yfinance sometimes uppercases / mangles keys
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
        return out
