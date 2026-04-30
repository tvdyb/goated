"""LIP-optimized market maker mode.

Maximizes Kalshi Liquidity Incentive Program score by:
- Staying on the book as much as possible (no unnecessary cancel/replace)
- Posting at best bid/ask (1.0x multiplier vs 0.5x at 1c away)
- Larger size (target 300 contracts to qualify)
- Both sides on all LIP-eligible strikes

LIP scoring (discount_factor=0.5):
  score = size * (0.5 ^ distance_from_best_in_cents)
  At best: 1.0x. 1c away: 0.5x. 2c away: 0.25x.

Usage:
    python -m deploy.lip_mode --config deploy/config_lip.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import random
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import yaml
from scipy.special import ndtr

from engine.implied_vol import calibrate_vol
from engine.markout import MarkoutTracker
from engine.wasde_density import WASDEAdjustment, WASDEDensityConfig, create_adjustment
from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from feeds.kalshi.errors import KalshiResponseError
from feeds.pyth.forward import PythForwardProvider, load_pyth_forward_config
from feeds.usda.wasde_parser import (
    WASDEConsensus,
    WASDEParseError,
    WASDESurprise,
    compute_surprise,
    parse_wasde_file,
)

logger = logging.getLogger("deploy.lip_mode")

_ET = ZoneInfo("America/New_York")
LIP_DISCOUNT = 0.5


def load_config(path: str) -> dict[str, Any]:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config {path} did not produce a dict")
    return cfg


class LIPMarketMaker:
    """LIP-optimized market maker.

    Key differences from spread-capture mode:
    - Only cancels orders when the target price changes
    - Posts at best bid/ask (not penny-inside)
    - Larger size
    - Minimizes time off the book
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._running = False
        self._kalshi_client: KalshiClient | None = None

        lip = cfg.get("lip", {})
        self._size_base = lip.get("contracts_per_side", 50)
        self._size_jitter = lip.get("size_jitter", 4)  # randomize ± this amount
        self._size = self._size_base  # current size (re-randomized per strike)
        self._max_half_spread = lip.get("max_half_spread_cents", 4)
        self._min_half_spread = lip.get("min_half_spread_cents", 2)
        self._cycle_seconds = cfg.get("loop", {}).get("cycle_seconds", 30)
        self._ticker_prefix = cfg.get("series", [{}])[0].get(
            "ticker_prefix", "KXSOYBEANMON"
        )
        self._vol = cfg.get("synthetic", {}).get("vol", 0.15)
        self._max_dist = lip.get("max_distance_from_best", 2)
        self._theo_tolerance = lip.get("theo_tolerance", 2)

        # yfinance forward ticker (May soybeans)
        self._yf_ticker = cfg.get("synthetic", {}).get("yf_ticker", "ZSK26.CBT")
        self._yf_cache: float | None = None
        self._yf_cache_time: float = 0.0
        self._yf_cache_ttl: float = 60.0  # refresh every 60s

        # LIP-eligible strikes (floor_strike values from Kalshi)
        raw_eligible = lip.get("eligible_strikes", [])
        self._eligible_strikes: set[float] = {
            float(s) / 100.0 for s in raw_eligible
        } if raw_eligible else set()

        # Settlement time override (use instead of Kalshi expiration_time)
        settle_str = cfg.get("synthetic", {}).get("settlement_time", "")
        self._settlement_override: datetime | None = None
        if settle_str:
            try:
                self._settlement_override = datetime.fromisoformat(settle_str)
                logger.info("SETTLEMENT: override=%s", self._settlement_override)
            except (ValueError, TypeError) as exc:
                logger.warning("SETTLEMENT: invalid override %r: %s", settle_str, exc)

        # State: what we currently have resting
        # market_ticker -> {"bid_id": str, "bid_px": int, "ask_id": str, "ask_px": int}
        self._resting: dict[str, dict[str, Any]] = {}
        self._market_tickers: dict[float, str] = {}
        self._forward_override: float = cfg.get("synthetic", {}).get("forward_override", 0.0)
        self._forward_estimate: float = self._forward_override
        self._days_to_settlement: float = 2.0
        self._last_forward_source: str = "unknown"

        # WASDE density adjustment
        wasde_cfg = cfg.get("wasde", {})
        self._wasde_config = WASDEDensityConfig(
            sensitivity_cents_per_mbu=wasde_cfg.get("sensitivity_cents_per_mbu", 18.0),
            decay_half_life_hours=wasde_cfg.get("decay_half_life_hours", 6.0),
            max_shift_cents=wasde_cfg.get("max_shift_cents", 100.0),
        )
        self._wasde_adjustment: WASDEAdjustment | None = None
        self._wasde_data_path: str | None = wasde_cfg.get("data_path")
        self._wasde_consensus = WASDEConsensus(
            ending_stocks=wasde_cfg.get("consensus_ending_stocks"),
            production=wasde_cfg.get("consensus_production"),
            exports=wasde_cfg.get("consensus_exports"),
        )

        # Markout tracker
        markout_cfg = cfg.get("markout", {})
        self._markout = MarkoutTracker(
            rolling_window_s=float(markout_cfg.get("rolling_window_s", 3600.0)),
            toxic_threshold_cents=float(markout_cfg.get("toxic_threshold_cents", -2.0)),
        )
        self._toxic_spread_multiplier = float(markout_cfg.get("toxic_spread_multiplier", 2.0))
        self._last_theo: dict[str, float] = {}  # market_ticker -> theo_cents
        self._fill_ids_seen: set[str] = set()

        # Pyth forward disabled — yfinance handles forward now
        self._pyth_provider: PythForwardProvider | None = None

    async def startup(self) -> None:
        api_key = os.environ.get("KALSHI_API_KEY", "")
        private_key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if not api_key or not private_key_path:
            raise RuntimeError(
                "KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH env vars required"
            )
        pem = Path(private_key_path).read_bytes()
        auth = KalshiAuth(api_key=api_key, private_key_pem=pem)
        api_cfg = self._cfg.get("api", {})
        base_url = api_cfg.get("kalshi_base", "https://api.elections.kalshi.com")
        self._kalshi_client = KalshiClient(auth=auth, base_url=base_url)
        await self._kalshi_client.open()
        logger.info("STARTUP: connected to Kalshi")

        # Cancel any existing orders to start clean
        await self._cancel_all()
        logger.info("STARTUP: complete")

    async def shutdown(self) -> None:
        logger.info("SHUTDOWN: cancelling all orders")
        await self._cancel_all()
        if self._kalshi_client:
            await self._kalshi_client.close()
        logger.info("SHUTDOWN: complete")

    def _scheduled_maintenance_window(self, now: datetime | None = None) -> bool:
        """Kalshi's scheduled weekly maintenance: Thursday 3-5 AM ET.

        Empirically Kalshi can start the window ~50 minutes early (we've seen
        503s on /exchange/status as early as 02:10 ET on a Thursday). Buffer
        is set to 02:00 ET start to cover early starts without being overly
        aggressive on other days/times.
        """
        if now is None:
            now = datetime.now(_ET)
        # weekday() returns Mon=0..Sun=6, so Thursday=3
        if now.weekday() != 3:
            return False
        mins = now.hour * 60 + now.minute
        return (2 * 60) <= mins < (5 * 60)

    async def _check_maintenance(self) -> tuple[bool, str]:
        """Returns (is_maintenance, reason).

        Cheap pre-check for the scheduled Thursday 3-5 AM ET window — if we're
        in it, assume maintenance without calling the API.

        Outside the scheduled window, query /exchange/status (single-attempt).
        Treat 5xx on the status endpoint as a maintenance signal too — the
        endpoint going 503 IS the maintenance.
        """
        if self._scheduled_maintenance_window():
            return True, "scheduled Thursday 3-5 AM ET window"

        assert self._kalshi_client is not None
        try:
            status = await self._kalshi_client.get_exchange_status()
            exchange_active = bool(status.get("exchange_active", True))
            trading_active = bool(status.get("trading_active", True))
            if not exchange_active:
                return True, f"API: exchange_active=false (resume {status.get('exchange_estimated_resume_time', 'unknown')})"
            if not trading_active:
                return True, "API: trading_active=false (outside trading hours)"
            return False, "API: exchange+trading both active"
        except KalshiResponseError as exc:
            # 5xx on the status endpoint = exchange itself is unhealthy.
            # Treat as maintenance to stop quoting until it recovers.
            if 500 <= (exc.status_code or 0) < 600:
                return True, f"API {exc.status_code} on /exchange/status — likely maintenance"
            return False, f"API status check non-5xx error (continuing): {exc}"
        except Exception as exc:
            return False, f"API status check failed (continuing): {exc}"

    # Legacy alias kept for _write_theo_state's status field
    def _in_maintenance_window(self) -> bool:
        return self._scheduled_maintenance_window()

    async def run(self) -> None:
        self._running = True
        logger.info("LIP MODE: starting (fast cycle=%ds, size=%d)", self._cycle_seconds, self._size_base)

        cycle_count = 0
        maintenance_active = False

        while self._running:
            cycle_start = time.monotonic()
            try:
                # --- Maintenance gate (Kalshi /exchange/status, fallback to schedule) ---
                in_maint, maint_reason = await self._check_maintenance()
                if in_maint:
                    if not maintenance_active:
                        logger.warning("MAINTENANCE: entering — %s", maint_reason)
                        try:
                            await self._cancel_all()
                        except Exception as exc:
                            logger.warning("MAINTENANCE: cancel failed: %s", exc)
                        maintenance_active = True
                    # Keep dashboard heartbeat alive during idle
                    self._write_theo_state()
                    # Re-check status every 60s during maintenance
                    await asyncio.sleep(60)
                    continue
                elif maintenance_active:
                    logger.info("MAINTENANCE: window ended — %s", maint_reason)
                    # Flush any stragglers Kalshi may still have from before
                    # maintenance — covers the case where pre-maintenance
                    # cancel_all silently failed because the API was already
                    # going down. Internal _resting is cleared, but Kalshi's
                    # state might not be.
                    try:
                        await self._cancel_all()
                        logger.info("MAINTENANCE: post-resume flush complete")
                    except Exception as exc:
                        logger.warning("MAINTENANCE: post-resume flush failed: %s", exc)
                    maintenance_active = False

                # Get active event + strikes (cached by _get_active_event)
                event_ticker, all_strikes = await self._get_active_event()
                if event_ticker is None:
                    await asyncio.sleep(5)
                    continue

                if self._eligible_strikes:
                    all_strikes = np.array([
                        s for s in all_strikes if s in self._eligible_strikes
                    ], dtype=np.float64)

                if len(all_strikes) == 0:
                    await asyncio.sleep(5)
                    continue

                # Wait for yfinance before placing any orders
                yf_fwd = self._pull_yfinance_forward()
                if yf_fwd is None or yf_fwd <= 0:
                    logger.warning("LIP: waiting for yfinance forward")
                    await asyncio.sleep(5)
                    continue

                # Recalibrate vol every 10th cycle (~30s)
                if cycle_count % 10 == 0:
                    all_obs = await self._pull_orderbooks(all_strikes)
                    self._calibrate_vol_from_orderbooks(all_strikes, all_obs)

                # Compute targets
                targets = self._compute_targets(all_strikes)

                # Store theo for markout
                now_ts = time.time()
                for strike, fair_cents in targets.items():
                    ticker = self._market_tickers.get(strike, "")
                    if ticker:
                        self._last_theo[ticker] = float(fair_cents)
                self._markout.update(now_ts, self._last_theo)

                # Process ALL strikes — pull orderbook + reposition each
                for strike in all_strikes:
                    await self._process_single_strike(float(strike), targets)

                # Process fills + markout every 5th cycle (~15s)
                if cycle_count % 5 == 0:
                    await self._process_fills_for_markout(time.time())
                    self._write_markout_file()
                    toxic_list = self._markout.get_toxic_strikes()
                    if toxic_list:
                        logger.warning(
                            "LIP CYCLE: TOXIC strikes: %s",
                            [t.split("-")[-1] for t in toxic_list],
                        )

                self._write_theo_state()

                cycle_count += 1

            except Exception as exc:
                logger.error("LIP CYCLE error: %s", exc, exc_info=True)

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.1, self._cycle_seconds - elapsed)
            await asyncio.sleep(sleep_time)

    async def _cycle(self) -> None:
        assert self._kalshi_client is not None

        # 1. Get active event + strikes
        event_ticker, kalshi_strikes = await self._get_active_event()
        if event_ticker is None:
            logger.info("LIP CYCLE: no active event")
            return

        # Filter to LIP-eligible strikes only
        if self._eligible_strikes:
            kalshi_strikes = np.array([
                s for s in kalshi_strikes if s in self._eligible_strikes
            ], dtype=np.float64)
            if len(kalshi_strikes) == 0:
                logger.info("LIP CYCLE: no eligible strikes")
                return
            logger.info("LIP CYCLE: %d eligible strikes", len(kalshi_strikes))

        # 2. Pull current orderbooks to know where best bid/ask are
        orderbooks = await self._pull_orderbooks(kalshi_strikes)

        # 2b. Calibrate vol from orderbook mid-prices
        self._calibrate_vol_from_orderbooks(kalshi_strikes, orderbooks)

        # 3. Compute target prices (synthetic GBM fair -> best bid/ask strategy)
        targets = self._compute_targets(kalshi_strikes)

        # 3b. Store theo values for markout tracking and update tracker
        now_ts = time.time()
        for strike, fair_cents in targets.items():
            ticker = self._market_tickers.get(strike, "")
            if ticker:
                self._last_theo[ticker] = float(fair_cents)
        self._markout.update(now_ts, self._last_theo)

        # 3c. Get toxic strikes
        toxic_tickers = set(self._markout.get_toxic_strikes())

        # 4. For each strike: post at widest spread that:
        #    a) qualifies for LIP top-300
        #    b) stays within max_distance_from_best of the actual best bid/ask
        #    c) NEVER crosses theo (anti-spoofing defense)
        #
        #    Rule (c) is the key defense against spoofing attacks where someone
        #    places a fake order to move the best price, causing us to move our
        #    order to an unfavorable price, then they trade against us and cancel.
        final_targets: dict[str, tuple[int, int]] = {}
        lip_target = 300

        for strike in kalshi_strikes:
            ticker = self._market_tickers.get(strike, "")
            if not ticker:
                continue

            fair = targets.get(strike, 50)
            is_toxic = ticker in toxic_tickers
            max_dist = int(self._max_dist * self._toxic_spread_multiplier) if is_toxic else self._max_dist
            ob = orderbooks.get(ticker, {})
            yes_depth = ob.get("yes_depth", [])
            no_depth = ob.get("no_depth", [])

            cur = self._resting.get(ticker, {})
            our_bid_px = cur.get("bid_px", 0)
            our_ask_px = cur.get("ask_px", 0)

            # Find best bid/ask (excluding our own orders)
            best_bid = 0
            for px, sz in yes_depth:
                if px == our_bid_px:
                    if sz - self._size > 0.5:
                        best_bid = px
                        break
                else:
                    best_bid = px
                    break

            best_no_bid = 0
            our_no_px = 100 - our_ask_px if our_ask_px > 0 else 0
            for px, sz in no_depth:
                if px == our_no_px:
                    if sz - self._size > 0.5:
                        best_no_bid = px
                        break
                else:
                    best_no_bid = px
                    break
            best_ask = (100 - best_no_bid) if best_no_bid > 0 else 100

            # --- Determine market regime: active or desert ---
            desert_threshold = 10  # if best is >10c from theo, it's a desert
            bid_is_desert = best_bid > 0 and abs(fair - best_bid) > desert_threshold
            ask_is_desert = best_ask < 100 and abs(best_ask - fair) > desert_threshold

            # --- BID ---
            if best_bid <= 0:
                bid = fair - self._max_half_spread
            elif bid_is_desert:
                # Desert: penny the best bid (1.0x LIP, any fill has huge edge)
                bid = best_bid + 1
            elif fair >= 97:
                # Deep ITM: match best bid (safe, will profit at settlement)
                bid = best_bid
            else:
                # Active market: stay 1c behind best
                bid = best_bid - max_dist

            # Check LIP: would we be in top 300 at this bid?
            yes_ahead = sum(
                (sz - self._size if px == our_bid_px else sz)
                for px, sz in yes_depth if px > bid
            )
            if yes_ahead + self._size > lip_target:
                bid = best_bid

            # ANTI-SPOOFING: ALWAYS cap at theo + tolerance (even in desert)
            bid = min(bid, fair - 1 + self._theo_tolerance)

            # --- ASK ---
            if best_ask >= 100:
                ask = fair + self._max_half_spread
            elif ask_is_desert:
                # Desert: penny the best ask (1.0x LIP, any fill has huge edge)
                ask = best_ask - 1
            elif fair <= 3:
                # Deep OTM: match best ask (safe, will profit at settlement)
                ask = best_ask
            elif fair >= 97:
                # Deep ITM: match best ask (safe, any fill profits 2c+)
                ask = best_ask
            else:
                # Active market: stay 1c behind best
                ask = best_ask + max_dist

            # Check LIP on No side
            target_no_px = 100 - ask
            no_ahead = sum(
                (sz - self._size if px == our_no_px else sz)
                for px, sz in no_depth if px > target_no_px
            )
            if no_ahead + self._size > lip_target:
                ask = best_ask

            # ANTI-SPOOFING: ALWAYS floor at theo - tolerance (even in desert)
            ask = max(ask, fair + 1 - self._theo_tolerance)

            # Clamp
            bid = max(1, min(99, bid))
            ask = max(1, min(99, ask))

            if bid >= ask:
                bid = fair - 1
                ask = fair + 1

            bid = max(1, min(99, bid))
            ask = max(1, min(99, ask))

            if bid < ask:
                spread = ask - bid
                bid_dist = best_bid - bid if best_bid > 0 else 0
                ask_dist = ask - best_ask if best_ask < 100 else 0
                bid_mult = LIP_DISCOUNT ** max(0, bid_dist)
                ask_mult = LIP_DISCOUNT ** max(0, ask_dist)
                final_targets[ticker] = (bid, ask)
                toxic_tag = " [TOXIC]" if is_toxic else ""
                logger.info(
                    "LIP %s: bid=%dc(%dc from best,%.2fx) "
                    "ask=%dc(%dc from best,%.2fx) spread=%dc%s",
                    ticker.split("-")[-1],
                    bid, bid_dist, bid_mult,
                    ask, ask_dist, ask_mult, spread, toxic_tag,
                )
                logger.debug(
                    "LIP %s: fair=%dc bid=%dc ask=%dc yes_ahead=%.0f no_ahead=%.0f",
                    ticker.split("-")[-1], fair, bid, ask,
                    sum(sz for _, sz in yes_depth),
                    sum(sz for _, sz in no_depth),
                )

        # 5. Smart update: amend orders whose price changed (1 API call vs 2)
        n_amended = 0
        n_placed = 0
        n_kept = 0
        n_fallback = 0

        for ticker, (target_bid, target_ask) in final_targets.items():
            current = self._resting.get(ticker, {})
            cur_bid_px = current.get("bid_px", 0)
            cur_ask_px = current.get("ask_px", 0)
            cur_bid_id = current.get("bid_id", "")
            cur_ask_id = current.get("ask_id", "")

            # Update bid if price changed
            if cur_bid_px != target_bid:
                if cur_bid_id:
                    # Try amend first (preserves queue position, 1 API call)
                    amended = await self._try_amend(
                        cur_bid_id, yes_price=target_bid, count=self._size,
                    )
                    if amended:
                        self._resting.setdefault(ticker, {})["bid_px"] = target_bid
                        n_amended += 1
                    else:
                        # Fallback: cancel + place
                        n_fallback += 1
                        await self._cancel_and_place_bid(ticker, target_bid)
                else:
                    # No existing order — place new
                    await self._place_bid(ticker, target_bid)
                    n_placed += 1
            else:
                n_kept += 1

            # Update ask if price changed
            if cur_ask_px != target_ask:
                if cur_ask_id:
                    amended = await self._try_amend(
                        cur_ask_id, yes_price=target_ask, count=self._size,
                    )
                    if amended:
                        self._resting.setdefault(ticker, {})["ask_px"] = target_ask
                        n_amended += 1
                    else:
                        n_fallback += 1
                        await self._cancel_and_place_ask(ticker, target_ask)
                else:
                    await self._place_ask(ticker, target_ask)
                    n_placed += 1
            else:
                n_kept += 1

        # Remove orders for strikes no longer in targets
        for ticker in list(self._resting.keys()):
            if ticker not in final_targets:
                current = self._resting[ticker]
                for key in ("bid_id", "ask_id"):
                    oid = current.get(key, "")
                    if oid:
                        try:
                            await self._kalshi_client.cancel_order(oid)
                            n_cancelled += 1
                        except Exception:
                            pass
                del self._resting[ticker]

        # 6. Process fills for markout tracking
        await self._process_fills_for_markout(now_ts)

        # Log toxic strikes
        toxic_list = self._markout.get_toxic_strikes()
        if toxic_list:
            logger.warning(
                "LIP CYCLE: TOXIC strikes (widened): %s",
                [t.split("-")[-1] for t in toxic_list],
            )

        # Write markout stats to shared file for dashboard
        self._write_markout_file()

        logger.info(
            "LIP CYCLE: amended=%d placed=%d kept=%d fallback=%d resting=%d strikes "
            "markout_active=%d markout_done=%d",
            n_amended, n_placed, n_kept, n_fallback, len(self._resting),
            self._markout.active_count(), self._markout.completed_count(),
        )

    async def _process_fills_for_markout(self, now_ts: float) -> None:
        """Pull recent fills and record them for markout tracking."""
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_fills(limit=50)
            fills = resp.get("fills", [])
            for f in fills:
                fill_id = f.get("trade_id", f.get("fill_id", ""))
                if not fill_id or fill_id in self._fill_ids_seen:
                    continue
                self._fill_ids_seen.add(fill_id)

                ticker = f.get("ticker", "")
                if not ticker:
                    continue

                count = int(float(f.get("count", f.get("count_fp", "0"))))
                if count <= 0:
                    continue

                yes_price_str = f.get("yes_price", f.get("yes_price_dollars", "0"))
                price_cents = int(round(float(yes_price_str) * 100)) if "." in str(yes_price_str) else int(yes_price_str)

                action = f.get("action", "buy")
                side = "buy" if action == "buy" else "sell"
                theo = self._last_theo.get(ticker, float(price_cents))

                self._markout.record_fill(
                    timestamp=now_ts,
                    market_ticker=ticker,
                    side=side,
                    fill_price_cents=price_cents,
                    theo_at_fill_cents=theo,
                )
                logger.info(
                    "MARKOUT: recorded fill %s %s %s @ %dc (theo=%.1fc)",
                    side, ticker.split("-")[-1], fill_id, price_cents, theo,
                )
        except Exception as exc:
            logger.warning("MARKOUT: failed to process fills: %s", exc)

    def _calibrate_vol_from_orderbooks(
        self,
        kalshi_strikes: np.ndarray,
        orderbooks: dict[str, dict[str, Any]],
    ) -> None:
        """Calibrate vol from Kalshi orderbook mid-prices on near-ATM strikes."""
        if self._forward_estimate <= 0 or self._days_to_settlement <= 0:
            return

        tau = max(0.1, self._days_to_settlement) / 365.0
        fallback = self._cfg.get("synthetic", {}).get("vol", 0.15)

        strike_mids: list[tuple[float, float]] = []
        for strike in kalshi_strikes:
            ticker = self._market_tickers.get(strike, "")
            if not ticker:
                continue
            ob = orderbooks.get(ticker, {})
            best_bid = ob.get("best_bid", 0)
            best_ask = ob.get("best_ask", 100)
            if best_bid > 0 and best_ask < 100 and best_bid < best_ask:
                mid_prob = (best_bid + best_ask) / 200.0
                strike_mids.append((strike, mid_prob))

        self._vol = calibrate_vol(
            forward=self._forward_estimate,
            strike_mids=strike_mids,
            tau=tau,
            fallback=fallback,
        )

    async def _process_single_strike(
        self, strike: float, targets: dict[float, int]
    ) -> None:
        """Process one strike: pull orderbook, compute target, update orders."""
        assert self._kalshi_client is not None
        ticker = self._market_tickers.get(strike, "")
        if not ticker:
            return

        # Randomize size to reduce bot fingerprint
        self._size = max(1, self._size_base + random.randint(
            -self._size_jitter, self._size_jitter
        ))

        fair = targets.get(strike, 50)
        toxic_tickers = set(self._markout.get_toxic_strikes())
        is_toxic = ticker in toxic_tickers
        max_dist = int(self._max_dist * self._toxic_spread_multiplier) if is_toxic else self._max_dist
        lip_target = 300

        # Pull orderbook for this strike
        ob_dict = await self._pull_orderbooks(np.array([strike]))
        ob = ob_dict.get(ticker, {})
        yes_depth = ob.get("yes_depth", [])
        no_depth = ob.get("no_depth", [])

        cur = self._resting.get(ticker, {})
        our_bid_px = cur.get("bid_px", 0)
        our_ask_px = cur.get("ask_px", 0)

        # Find best bid/ask (excluding our own orders)
        best_bid = 0
        for px, sz in yes_depth:
            if px == our_bid_px:
                if sz - self._size > 0.5:
                    best_bid = px
                    break
            else:
                best_bid = px
                break

        best_no_bid = 0
        our_no_px = 100 - our_ask_px if our_ask_px > 0 else 0
        for px, sz in no_depth:
            if px == our_no_px:
                if sz - self._size > 0.5:
                    best_no_bid = px
                    break
            else:
                best_no_bid = px
                break
        best_ask = (100 - best_no_bid) if best_no_bid > 0 else 100

        # --- Determine market regime ---
        # Desert = best price is far from theo. Use proportional threshold:
        # >10c OR >30% of fair value (catches low-priced strikes like 9c theo)
        desert_threshold = 10
        bid_is_desert = best_bid > 0 and (
            abs(fair - best_bid) > desert_threshold
            or (fair > 0 and abs(fair - best_bid) / max(fair, 1) > 0.3)
        )
        ask_is_desert = best_ask < 100 and (
            abs(best_ask - fair) > desert_threshold
            or (fair > 0 and abs(best_ask - fair) / max(100 - fair, 1) > 0.3)
        )

        # --- BID ---
        if best_bid <= 0:
            bid = fair - self._max_half_spread
        elif bid_is_desert:
            bid = best_bid + 1
        elif fair >= 97:
            bid = best_bid
        else:
            bid = best_bid - max_dist

        yes_ahead = sum(
            (sz - self._size if px == our_bid_px else sz)
            for px, sz in yes_depth if px > bid
        )
        if yes_ahead + self._size > lip_target:
            bid = best_bid

        # ANTI-SPOOFING: ALWAYS cap at theo + tolerance (even in desert)
        bid = min(bid, fair - 1 + self._theo_tolerance)

        # --- ASK ---
        if best_ask >= 100:
            ask = fair + self._max_half_spread
        elif ask_is_desert:
            ask = best_ask - 1
        elif fair <= 3:
            # Deep OTM: match best ask (safe, settles No)
            ask = best_ask
        elif fair >= 97:
            # Deep ITM: match best ask (safe, any fill profits 2c+)
            ask = best_ask
        else:
            ask = best_ask + max_dist

        target_no_px = 100 - ask
        no_ahead = sum(
            (sz - self._size if px == our_no_px else sz)
            for px, sz in no_depth if px > target_no_px
        )
        if no_ahead + self._size > lip_target:
            ask = best_ask

        # ANTI-SPOOFING: ALWAYS floor at theo - tolerance (even in desert)
        ask = max(ask, fair + 1 - self._theo_tolerance)

        # Clamp
        bid = max(1, min(99, bid))
        ask = max(1, min(99, ask))

        if bid >= ask:
            bid = fair - 1
            ask = fair + 1
        bid = max(1, min(99, bid))
        ask = max(1, min(99, ask))

        if bid >= ask:
            return

        # --- Update orders ---
        cur_bid_px = cur.get("bid_px", 0)
        cur_ask_px = cur.get("ask_px", 0)
        cur_bid_id = cur.get("bid_id", "")
        cur_ask_id = cur.get("ask_id", "")

        bid_dist = best_bid - bid if best_bid > 0 else 0
        ask_dist = ask - best_ask if best_ask < 100 else 0
        bid_mult = LIP_DISCOUNT ** max(0, bid_dist)
        ask_mult = LIP_DISCOUNT ** max(0, ask_dist)
        toxic_tag = " [TOXIC]" if is_toxic else ""
        regime = "desert" if (bid_is_desert or ask_is_desert) else "active"

        # --- Anti-churn: only reposition if multiplier dropped below 0.25x ---
        # BUT force a fresh recompute every ~30s to re-penny if competitor relaxed.
        min_acceptable_mult = 0.25
        force_refresh = (time.time() % 30) < self._cycle_seconds  # roughly every 30s

        cur_bid_ok = False
        if cur_bid_px > 0 and best_bid > 0:
            cur_bid_dist = best_bid - cur_bid_px
            cur_bid_mult = LIP_DISCOUNT ** max(0, cur_bid_dist)
            cur_bid_ahead = sum(
                (sz - self._size if px == cur_bid_px else sz)
                for px, sz in yes_depth if px > cur_bid_px
            )
            cur_bid_in_300 = cur_bid_ahead + self._size <= lip_target
            cur_bid_ok = cur_bid_in_300 and cur_bid_mult >= min_acceptable_mult

        cur_ask_ok = False
        if cur_ask_px > 0 and best_ask < 100:
            cur_ask_dist = cur_ask_px - best_ask
            cur_ask_mult = LIP_DISCOUNT ** max(0, cur_ask_dist)
            cur_no_px = 100 - cur_ask_px
            cur_ask_ahead = sum(
                (sz - self._size if px == cur_no_px else sz)
                for px, sz in no_depth if px > cur_no_px
            )
            cur_ask_in_300 = cur_ask_ahead + self._size <= lip_target
            cur_ask_ok = cur_ask_in_300 and cur_ask_mult >= min_acceptable_mult

        # Update bid: reposition if multiplier < 0.25x, no order, or periodic refresh
        bid_needs_update = (not cur_bid_ok or cur_bid_px == 0 or force_refresh) and cur_bid_px != bid
        if bid_needs_update:
            if cur_bid_id:
                amended = await self._try_amend(cur_bid_id, yes_price=bid, count=self._size)
                if amended:
                    self._resting.setdefault(ticker, {})["bid_px"] = bid
                else:
                    await self._cancel_and_place_bid(ticker, bid)
            else:
                await self._place_bid(ticker, bid)

        # Update ask: reposition if multiplier < 0.25x, no order, or periodic refresh
        ask_needs_update = (not cur_ask_ok or cur_ask_px == 0 or force_refresh) and cur_ask_px != ask
        if ask_needs_update:
            if cur_ask_id:
                amended = await self._try_amend(cur_ask_id, yes_price=ask, count=self._size)
                if amended:
                    self._resting.setdefault(ticker, {})["ask_px"] = ask
                else:
                    await self._cancel_and_place_ask(ticker, ask)
            else:
                await self._place_ask(ticker, ask)

        logger.info(
            "LIP %s [%s]: bid=%dc(%.2fx) ask=%dc(%.2fx) spread=%dc fair=%dc%s",
            ticker.split("-")[-1], regime,
            bid, bid_mult, ask, ask_mult, ask - bid, fair, toxic_tag,
        )

    def _compute_targets(self, kalshi_strikes: np.ndarray) -> dict[float, int]:
        """Compute fair value in cents for each strike via synthetic GBM."""
        forward = self._forward_estimate
        if forward <= 0:
            forward = float(kalshi_strikes[len(kalshi_strikes) // 2])
            self._forward_estimate = forward

        # Apply WASDE mean-shift to forward (decaying)
        if self._wasde_adjustment is not None:
            now_ts = time.time()
            if self._wasde_adjustment.is_expired(now_ts):
                logger.info("WASDE: adjustment expired, clearing")
                self._wasde_adjustment = None
            else:
                shift_cents = self._wasde_adjustment.current_shift_cents(now_ts)
                forward = forward + shift_cents / 100.0
                logger.info(
                    "LIP WASDE: forward shifted %.4f -> %.4f (%.1fc)",
                    self._forward_estimate, forward, shift_cents,
                )

        sigma = self._vol
        tau = max(0.1, self._days_to_settlement) / 365.0
        sig_sqrt_t = max(sigma * math.sqrt(tau), 1e-12)

        targets: dict[float, int] = {}
        for k in kalshi_strikes:
            d2 = (math.log(forward / k) - 0.5 * sigma ** 2 * tau) / sig_sqrt_t
            survival = float(ndtr(d2))
            targets[float(k)] = int(round(survival * 100))
        return targets

    async def _get_active_event(self) -> tuple[str | None, np.ndarray]:
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_events(
                series_ticker=self._ticker_prefix, status="open", limit=5
            )
            events = resp.get("events", [])
            if not events:
                return None, np.array([])

            event_ticker = events[0]["event_ticker"]
            detail = await self._kalshi_client.get_event(event_ticker)
            markets = detail.get("markets", [])

            strikes = []
            self._market_tickers = {}
            for m in markets:
                fs = m.get("floor_strike")
                t = m.get("ticker", "")
                if fs is not None and t:
                    s = float(fs) / 100.0
                    strikes.append(s)
                    self._market_tickers[s] = t

            # Forward priority:
            #   1. config override (manual)
            #   2. Trading Economics (canonical — Kalshi resolves against this)
            #   3. yfinance (CBOT, can be stale during overnight session)
            #   4. Pyth (currently dead for soy, kept for future)
            #   5. Kalshi-inferred ATM heuristic (last resort)
            self._last_forward_source = "unknown"
            if self._forward_override > 0:
                self._forward_estimate = self._forward_override
                self._last_forward_source = "config override"
                logger.info("FORWARD: override=%.4f $/bu", self._forward_override)
            else:
                te_fwd_cents = None
                try:
                    from feeds.tradingeconomics.soybean import get_soybean_price
                    te_fwd_cents = get_soybean_price()
                except Exception as exc:
                    logger.warning("FORWARD: TE fetch failed: %s", exc)

                if te_fwd_cents is not None and te_fwd_cents > 0:
                    self._forward_estimate = te_fwd_cents / 100.0
                    self._last_forward_source = "Trading Economics"
                    logger.info("FORWARD: TradingEconomics=%.4f $/bu (%.2fc)", self._forward_estimate, te_fwd_cents)
                else:
                    yf_fwd = self._pull_yfinance_forward()
                    if yf_fwd is not None and yf_fwd > 0:
                        self._forward_estimate = yf_fwd / 100.0
                        self._last_forward_source = f"yfinance ({self._yf_ticker})"
                        logger.info("FORWARD: yfinance %s=%.4f $/bu (%.1fc) [TE unavailable]", self._yf_ticker, self._forward_estimate, yf_fwd)
                    else:
                        _pf = None
                        if self._pyth_provider is not None and self._pyth_provider.pyth_available:
                            _pf = self._pyth_provider.forward_price
                        if _pf is not None and _pf > 0:
                            self._forward_estimate = _pf
                            self._last_forward_source = "Pyth"
                            logger.info("FORWARD: Pyth ZS=%.4f $/bu [TE+yfinance unavailable]", _pf)
                        else:
                            for m in markets:
                                bid = float(m.get("yes_bid_dollars") or 0)
                                ask = float(m.get("yes_ask_dollars") or 1)
                                mid = (bid + ask) / 2
                                if 0.4 <= mid <= 0.6:
                                    fs = m.get("floor_strike")
                                    if fs:
                                        self._forward_estimate = float(fs) / 100.0
                                        break
                            self._last_forward_source = "Kalshi ATM-heuristic"
                            logger.warning("FORWARD: Kalshi=%.4f (TE/yfinance/Pyth all unavailable)", self._forward_estimate)

            # Days to settlement: prefer override > Kalshi expiration_time
            if self._settlement_override is not None:
                now_aware = datetime.now(self._settlement_override.tzinfo)
                days = (self._settlement_override - now_aware).total_seconds() / 86400
                self._days_to_settlement = max(0.1, days)
                logger.info(
                    "SETTLEMENT: %.1f hours to settle (override)",
                    self._days_to_settlement * 24,
                )
            else:
                for m in markets:
                    et = m.get("expiration_time", "")
                    if et:
                        try:
                            exp_dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
                            days = (exp_dt - datetime.now(exp_dt.tzinfo)).total_seconds() / 86400
                            self._days_to_settlement = max(0.5, days)
                        except (ValueError, TypeError):
                            pass
                        break

            if not strikes:
                return None, np.array([])

            return event_ticker, np.array(sorted(strikes), dtype=np.float64)
        except Exception as exc:
            logger.error("Failed to get active event: %s", exc)
            return None, np.array([])

    async def _pull_orderbooks(
        self, kalshi_strikes: np.ndarray
    ) -> dict[str, dict[str, Any]]:
        """Pull full orderbook for each strike.

        Returns ticker -> {
            "best_bid": int, "best_ask": int,
            "yes_depth": [(price_cents, size), ...],  # sorted best-first
            "no_depth": [(price_cents, size), ...],
        }
        """
        assert self._kalshi_client is not None
        result: dict[str, dict[str, Any]] = {}

        for strike in kalshi_strikes:
            ticker = self._market_tickers.get(strike, "")
            if not ticker:
                continue
            try:
                ob = await self._kalshi_client.get_orderbook(ticker)
                ob_fp = ob.get("orderbook_fp", {})
                yes_lvls = ob_fp.get("yes_dollars", [])
                no_lvls = ob_fp.get("no_dollars", [])

                # Parse depth
                yes_depth = sorted(
                    [(int(round(float(lv[0]) * 100)), float(lv[1])) for lv in yes_lvls],
                    key=lambda x: -x[0],  # best (highest) bid first
                )
                no_depth = sorted(
                    [(int(round(float(lv[0]) * 100)), float(lv[1])) for lv in no_lvls],
                    key=lambda x: -x[0],  # best (highest) no-bid first
                )

                best_bid = yes_depth[0][0] if yes_depth else 0
                best_ask = (100 - no_depth[0][0]) if no_depth else 100

                result[ticker] = {
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "yes_depth": yes_depth,
                    "no_depth": no_depth,
                }
            except Exception:
                result[ticker] = {
                    "best_bid": 0, "best_ask": 100,
                    "yes_depth": [], "no_depth": [],
                }

        return result

    @property
    def markout_tracker(self) -> MarkoutTracker:
        return self._markout

    def _write_markout_file(self) -> None:
        """Write markout stats to JSON for dashboard consumption."""
        import json
        stats = self._markout.bucket_stats()
        data = [
            {
                "market_ticker": bs.market_ticker,
                "avg_1m": round(bs.avg_1m, 2),
                "avg_5m": round(bs.avg_5m, 2),
                "avg_30m": round(bs.avg_30m, 2),
                "n_fills": bs.n_fills,
            }
            for bs in stats
        ]
        try:
            with open("state/markout.json", "w") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("MARKOUT: failed to write markout file: %s", exc)

    def _write_theo_state(self) -> None:
        """Write current theo inputs to JSON for dashboard consumption."""
        import json

        now = time.time()
        wasde_state: dict[str, Any] = {"active": False}
        if self._wasde_adjustment is not None and not self._wasde_adjustment.is_expired(now):
            shift = self._wasde_adjustment.current_shift_cents(now)
            elapsed_h = (now - self._wasde_adjustment.release_timestamp) / 3600.0
            half_life_h = self._wasde_adjustment.decay_half_life_s / 3600.0
            wasde_state = {
                "active": True,
                "current_shift_cents": shift,
                "initial_shift_cents": self._wasde_adjustment.mean_shift_cents,
                "elapsed_hours": elapsed_h,
                "half_life_hours": half_life_h,
            }

        forward_source = self._last_forward_source or "unknown"

        data = {
            "ts": now,
            "vol_calibrated": self._vol,
            "vol_fallback": self._cfg.get("synthetic", {}).get("vol", 0.15),
            "forward_dollars": self._forward_estimate,
            "forward_source": forward_source,
            "days_to_settlement": self._days_to_settlement,
            "size_base": self._size_base,
            "size_jitter": self._size_jitter,
            "size_last": self._size,
            "wasde": wasde_state,
            "maintenance_active": self._in_maintenance_window(),
        }
        try:
            with open("state/theo_state.json", "w") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("THEO STATE: failed to write: %s", exc)

    async def _try_amend(
        self,
        order_id: str,
        *,
        yes_price: int | None = None,
        no_price: int | None = None,
        count: int | None = None,
    ) -> bool:
        """Try to amend a resting order. Returns True on success, False on failure."""
        assert self._kalshi_client is not None
        try:
            await self._kalshi_client.amend_order(
                order_id, yes_price=yes_price, no_price=no_price, count=count,
            )
            return True
        except KalshiResponseError as exc:
            logger.warning("LIP AMEND failed (order=%s): %s — falling back to cancel+place", order_id[:8], exc)
            return False
        except Exception as exc:
            logger.warning("LIP AMEND error (order=%s): %s — falling back to cancel+place", order_id[:8], exc)
            return False

    async def _cancel_and_place_bid(self, ticker: str, target_bid: int) -> None:
        """Cancel existing bid and place new one (fallback from amend)."""
        assert self._kalshi_client is not None
        cur = self._resting.get(ticker, {})
        cur_bid_id = cur.get("bid_id", "")
        if cur_bid_id:
            try:
                await self._kalshi_client.cancel_order(cur_bid_id)
            except Exception:
                pass
        await self._place_bid(ticker, target_bid)

    async def _cancel_and_place_ask(self, ticker: str, target_ask: int) -> None:
        """Cancel existing ask and place new one (fallback from amend)."""
        assert self._kalshi_client is not None
        cur = self._resting.get(ticker, {})
        cur_ask_id = cur.get("ask_id", "")
        if cur_ask_id:
            try:
                await self._kalshi_client.cancel_order(cur_ask_id)
            except Exception:
                pass
        await self._place_ask(ticker, target_ask)

    async def _place_bid(self, ticker: str, target_bid: int) -> None:
        """Place a new bid order."""
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.create_order(
                ticker=ticker,
                action="buy",
                side="yes",
                order_type="limit",
                count=self._size,
                yes_price=target_bid,
                post_only=True,
            )
            order = resp.get("order", {})
            oid = order.get("order_id", "")
            self._resting.setdefault(ticker, {})["bid_id"] = oid
            self._resting[ticker]["bid_px"] = target_bid
        except Exception as exc:
            logger.warning("LIP: failed bid %s @ %dc: %s", ticker, target_bid, exc)
            self._resting.setdefault(ticker, {})["bid_id"] = ""
            self._resting[ticker]["bid_px"] = 0

    async def _place_ask(self, ticker: str, target_ask: int) -> None:
        """Place a new ask order."""
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.create_order(
                ticker=ticker,
                action="sell",
                side="yes",
                order_type="limit",
                count=self._size,
                yes_price=target_ask,
                post_only=True,
            )
            order = resp.get("order", {})
            oid = order.get("order_id", "")
            self._resting.setdefault(ticker, {})["ask_id"] = oid
            self._resting[ticker]["ask_px"] = target_ask
        except Exception as exc:
            logger.warning("LIP: failed ask %s @ %dc: %s", ticker, target_ask, exc)
            self._resting.setdefault(ticker, {})["ask_id"] = ""
            self._resting[ticker]["ask_px"] = 0

    def _pull_yfinance_forward(self) -> float | None:
        """Pull ZS front-month price from yfinance. Returns price in cents or None."""
        now = time.time()
        if self._yf_cache is not None and (now - self._yf_cache_time) < self._yf_cache_ttl:
            return self._yf_cache

        try:
            import yfinance as yf
            tk = yf.Ticker(self._yf_ticker)
            hist = tk.history(period="1d")
            if hist.empty:
                logger.warning("YFINANCE: no data for %s", self._yf_ticker)
                return self._yf_cache  # return stale cache if available
            close = float(hist["Close"].iloc[-1])
            # Sanity check: soybean price should be 800-2000 cents/bushel
            if close < 500 or close > 2500:
                logger.warning("YFINANCE: price %.1f outside sanity range", close)
                return self._yf_cache
            self._yf_cache = close
            self._yf_cache_time = now
            return close
        except Exception as exc:
            logger.warning("YFINANCE: failed to pull %s: %s", self._yf_ticker, exc)
            return self._yf_cache

    async def _cancel_all(self) -> None:
        if not self._kalshi_client:
            return
        try:
            resp = await self._kalshi_client.get_orders(status="resting", limit=200)
            for o in resp.get("orders", []):
                try:
                    await self._kalshi_client.cancel_order(o["order_id"])
                except Exception:
                    pass
        except Exception:
            pass
        self._resting.clear()


def main() -> None:
    parser = argparse.ArgumentParser(description="Goated LIP mode")
    parser.add_argument("--config", default="deploy/config_lip.yaml")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)-25s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = load_config(args.config)
    mm = LIPMarketMaker(cfg)

    loop = asyncio.new_event_loop()

    def _signal_handler() -> None:
        mm._running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    async def _run() -> None:
        await mm.startup()
        try:
            await mm.run()
        finally:
            await mm.shutdown()

    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
