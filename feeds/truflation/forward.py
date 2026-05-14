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
    TE_LITHIUM,
    TE_NICKEL,
    get_te_spot,
)

logger = logging.getLogger(__name__)


# ── Symbol constants ────────────────────────────────────────────────
#
# Per Truflation's official website (verified 2026-05-11), the TruEV
# index actually uses these data providers:
#
#   Copper      CME (= COMEX HG futures)         ← we match via yfinance HG=F
#   Palladium   NYMEX                            ← we match via yfinance PA=F
#   Platinum    NYMEX                            ← we match via yfinance PL=F
#   Lithium     GFEX (Guangzhou Futures Exchange) lithium carbonate
#               futures                          ← MISMATCH — we proxy via TE
#   Cobalt      SMM (Shanghai Metals Market) China-domestic
#               cobalt 99.8% price               ← MISMATCH — we proxy via TE LME
#   Nickel      SMM (Shanghai Metals Market) China-domestic Ni 1#
#               refined nickel price             ← MISMATCH — we proxy via NICK.L (LSE ETC tracking LME)
#
# **Our current proxies and their mismatches:**
#
# yfinance tickers (THREE EXACT MATCHES with Truflation's actual feeds):
#   HG=F     COMEX copper futures — matches CME ✓
#   PA=F     NYMEX palladium futures — matches NYMEX ✓
#   PL=F     NYMEX platinum futures — matches NYMEX ✓
#
# Proxies that DON'T match Truflation (three of six basket components):
#   NICK.L   WisdomTree Nickel ETC on LSE, FX-stripped to USD via
#            GBPUSD. Tracks LME 3-month nickel, NOT SMM Chinese
#            nickel. Basis risk during periods when CN/Western
#            metals decouple (tariff news, supply shocks).
#   COBALT_TE  TE scrape of LME cobalt (`LCO1:COM`). NOT SMM
#              Chinese cobalt. Same basis-risk caveat.
#   LITHIUM_TE TE scrape of Chinese lithium (unclear exact contract;
#              not GFEX lithium carbonate futures). Maybe partially
#              aligned but not exact.
#
#   LIT      Global X Lithium ETF — equity proxy. RETAINED FOR BACKTEST
#            ONLY because it has yfinance daily history. The TE scrape
#            doesn't expose historicals, and we don't yet have a GFEX
#            scraper.
#
# **Practical impact:** with three mismatched proxies, our NNLS-fitted
# weights have absorbed the basis empirically (~5 pt walk-forward
# RMSE). The official methodology weights (Cu 41.6%, Li 30.5%,
# Ni 13.2%, Co 8.9%, Pa 4.7%, Pt 1.1%) only reproduce the index if
# fed with Truflation's actual GFEX/SMM-priced inputs.
#
# **Future work:** swap to direct GFEX lithium futures + SMM cobalt +
# SMM nickel scrapes. Should bring live RMSE from ~5 pt → ~2-3 pt
# and validate the official weights.
COBALT_TE = "COBALT_TE"
LITHIUM_TE = "LITHIUM_TE"
NICKEL_TE = "NICKEL_TE"

TRUEV_PHASE1_SYMBOLS: tuple[str, ...] = (
    "HG=F", LITHIUM_TE, NICKEL_TE, "PA=F", "PL=F", COBALT_TE,
)

# Subset that yfinance can serve (used by backtest helpers — keeps the
# LIT equity proxy because it has dense daily history that TE doesn't,
# and retains NICK.L since it has historical bars that the backtest
# harness needs)
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
        "LIT": (10.0, 200.0),      # Global X Lithium ETF $/share (backtest only)
        # NICK.L retained for backtest harness only — TE nickel has no
        # historicals, so daily-bar backtests fall back to NICK.L's
        # yfinance-served daily Closes.
        "NICK.L": (0.01, 5.0),     # WisdomTree Nickel ETC USD/share (FX-stripped, backtest fallback)
        "PA=F": (200.0, 5000.0),   # Palladium $/oz
        "PL=F": (200.0, 5000.0),   # Platinum $/oz
        COBALT_TE: (10_000.0, 200_000.0),     # Cobalt $/tonne via TE
        LITHIUM_TE: (10_000.0, 1_000_000.0),  # Lithium CNY/tonne via TE
        NICKEL_TE: (5_000.0, 80_000.0),       # Nickel $/tonne via TE (LME 3M)
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
        yfinance for the cleanly-listed front-month futures (HG=F, PA=F,
        PL=F), TE scrape for the three sentinel symbols (LITHIUM_TE,
        COBALT_TE, NICKEL_TE).

        NICKEL_TE returns LME 3-month nickel in USD/T directly — no FX
        strip, no LSE-close gap, no GBp conversion. Replaces the legacy
        NICK.L (WisdomTree ETC) proxy which had to be FX-stripped via
        GBPUSD=X and froze when LSE closed. NICK.L is retained in the
        backtest-only symbol set since TE has no historicals.
        """
        out: dict[str, float] = {}
        te_sentinels = {COBALT_TE, LITHIUM_TE, NICKEL_TE}
        yf_syms = [s for s in self._symbols if s not in te_sentinels]
        # Legacy NICK.L path: only fires if NICK.L is in the symbol set
        # (backtest harnesses). The live basket uses NICKEL_TE instead.
        needs_fx = "NICK.L" in self._symbols
        fx_sym = "GBPUSD=X"
        all_yf = list(yf_syms) + ([fx_sym] if needs_fx else [])
        gbpusd: float | None = None
        if all_yf:
            try:
                handle = yf.Tickers(" ".join(all_yf))
            except Exception as exc:
                logger.warning("yf.Tickers init failed: %s", exc)
                handle = None
            raw: dict[str, float] = {}
            for sym in all_yf:
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
                    raw[sym] = close
                except Exception as exc:
                    logger.warning("yfinance fetch failed for %s: %s", sym, exc)
            if needs_fx:
                gbpusd = raw.get(fx_sym)
            for sym in yf_syms:
                if sym not in raw:
                    continue
                if sym == "NICK.L":
                    if gbpusd is None or gbpusd <= 0:
                        logger.warning(
                            "NICK.L: GBPUSD fetch failed; dropping nickel "
                            "this poll rather than feeding GBp value into a "
                            "USD-anchored basket",
                        )
                        continue
                    # GBp → GBP → USD. /100 = pence-to-pound conversion.
                    out[sym] = raw[sym] * gbpusd / 100.0
                else:
                    out[sym] = raw[sym]

        # TE scrapes (synchronous httpx). One commodity per sentinel.
        if COBALT_TE in self._symbols:
            price = get_te_spot(TE_COBALT)
            if price is not None and price > 0:
                out[COBALT_TE] = price
        if LITHIUM_TE in self._symbols:
            price = get_te_spot(TE_LITHIUM)
            if price is not None and price > 0:
                out[LITHIUM_TE] = price
        if NICKEL_TE in self._symbols:
            price = get_te_spot(TE_NICKEL)
            if price is not None and price > 0:
                out[NICKEL_TE] = price
        return out
