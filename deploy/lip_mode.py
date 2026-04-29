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
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import yaml
from scipy.special import ndtr

from engine.wasde_density import WASDEAdjustment, WASDEDensityConfig, create_adjustment
from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
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
        self._size = lip.get("contracts_per_side", 50)
        self._max_half_spread = lip.get("max_half_spread_cents", 4)
        self._min_half_spread = lip.get("min_half_spread_cents", 2)
        self._cycle_seconds = cfg.get("loop", {}).get("cycle_seconds", 30)
        self._ticker_prefix = cfg.get("series", [{}])[0].get(
            "ticker_prefix", "KXSOYBEANMON"
        )
        self._vol = cfg.get("synthetic", {}).get("vol", 0.15)
        self._max_dist = lip.get("max_distance_from_best", 2)

        # LIP-eligible strikes (floor_strike values from Kalshi)
        raw_eligible = lip.get("eligible_strikes", [])
        self._eligible_strikes: set[float] = {
            float(s) / 100.0 for s in raw_eligible
        } if raw_eligible else set()

        # State: what we currently have resting
        # market_ticker -> {"bid_id": str, "bid_px": int, "ask_id": str, "ask_px": int}
        self._resting: dict[str, dict[str, Any]] = {}
        self._market_tickers: dict[float, str] = {}
        self._forward_estimate: float = 0.0
        self._days_to_settlement: float = 2.0

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

        # Pyth forward price provider
        self._pyth_provider: PythForwardProvider | None = None
        pyth_cfg_path = cfg.get("pyth_feeds_config", "config/pyth_feeds.yaml")
        try:
            with open(pyth_cfg_path) as f:
                pyth_cfg = yaml.safe_load(f)
            pyth_fwd_cfg = load_pyth_forward_config(pyth_cfg)
            self._pyth_provider = PythForwardProvider(pyth_fwd_cfg)
        except Exception as exc:
            logger.warning("Pyth forward not configured: %s", exc)

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

        # Pyth forward provider
        if self._pyth_provider is not None:
            try:
                await self._pyth_provider.start()
                logger.info("STARTUP: Pyth forward provider started")
            except Exception as exc:
                logger.warning("STARTUP: Pyth forward start failed: %s", exc)
                self._pyth_provider = None

        # Cancel any existing orders to start clean
        await self._cancel_all()
        logger.info("STARTUP: complete")

    async def shutdown(self) -> None:
        logger.info("SHUTDOWN: cancelling all orders")
        await self._cancel_all()
        if self._pyth_provider is not None:
            try:
                await self._pyth_provider.stop()
            except Exception:
                pass
        if self._kalshi_client:
            await self._kalshi_client.close()
        logger.info("SHUTDOWN: complete")

    async def run(self) -> None:
        self._running = True
        logger.info("LIP MODE: starting (cycle=%ds, size=%d)", self._cycle_seconds, self._size)

        while self._running:
            cycle_start = time.monotonic()
            try:
                await self._cycle()
            except Exception as exc:
                logger.error("LIP CYCLE error: %s", exc, exc_info=True)

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, self._cycle_seconds - elapsed)
            if sleep_time > 0:
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

        # 2. Compute target prices (synthetic GBM fair -> best bid/ask strategy)
        targets = self._compute_targets(kalshi_strikes)

        # 3. Pull current orderbooks to know where best bid/ask are
        orderbooks = await self._pull_orderbooks(kalshi_strikes)

        # 4. For each strike: post at widest spread that:
        #    a) qualifies for LIP top-300
        #    b) stays within max_distance_from_best of the actual best bid/ask
        #
        #    Rule (b) ensures we always have a meaningful LIP multiplier.
        #    With max_dist=2: multiplier >= 0.25x. No more 0.00x dead orders.
        final_targets: dict[str, tuple[int, int]] = {}
        lip_target = 300

        for strike in kalshi_strikes:
            ticker = self._market_tickers.get(strike, "")
            if not ticker:
                continue

            fair = targets.get(strike, 50)
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

            # --- BID: max_dist cents below best bid, but check LIP ---
            if best_bid > 0:
                bid = best_bid - self._max_dist
            else:
                bid = fair - self._max_half_spread

            # Check LIP: would we be in top 300 at this bid?
            yes_ahead = sum(
                (sz - self._size if px == our_bid_px else sz)
                for px, sz in yes_depth if px > bid
            )
            if yes_ahead + self._size > lip_target:
                # Too crowded even at this price — move closer to best
                bid = best_bid

            # --- ASK: max_dist cents above best ask, but check LIP ---
            if best_ask < 100:
                ask = best_ask + self._max_dist
            else:
                ask = fair + self._max_half_spread

            # Check LIP on No side
            target_no_px = 100 - ask
            no_ahead = sum(
                (sz - self._size if px == our_no_px else sz)
                for px, sz in no_depth if px > target_no_px
            )
            if no_ahead + self._size > lip_target:
                ask = best_ask

            # Clamp
            bid = max(1, min(99, bid))
            ask = max(1, min(99, ask))

            if bid >= ask:
                bid = best_bid - 1 if best_bid > 1 else 1
                ask = best_ask + 1 if best_ask < 99 else 99

            bid = max(1, min(99, bid))
            ask = max(1, min(99, ask))

            if bid < ask:
                spread = ask - bid
                bid_dist = best_bid - bid if best_bid > 0 else 0
                ask_dist = ask - best_ask if best_ask < 100 else 0
                bid_mult = LIP_DISCOUNT ** max(0, bid_dist)
                ask_mult = LIP_DISCOUNT ** max(0, ask_dist)
                final_targets[ticker] = (bid, ask)
                logger.info(
                    "LIP %s: bid=%dc(%dc from best,%.2fx) "
                    "ask=%dc(%dc from best,%.2fx) spread=%dc",
                    ticker.split("-")[-1],
                    bid, bid_dist, bid_mult,
                    ask, ask_dist, ask_mult, spread,
                )
                logger.debug(
                    "LIP %s: fair=%dc bid=%dc ask=%dc yes_ahead=%.0f no_ahead=%.0f",
                    ticker.split("-")[-1], fair, bid, ask,
                    sum(sz for _, sz in yes_depth),
                    sum(sz for _, sz in no_depth),
                )

        # 5. Smart update: only cancel/replace orders whose price changed
        n_placed = 0
        n_kept = 0
        n_cancelled = 0

        for ticker, (target_bid, target_ask) in final_targets.items():
            current = self._resting.get(ticker, {})
            cur_bid_px = current.get("bid_px", 0)
            cur_ask_px = current.get("ask_px", 0)
            cur_bid_id = current.get("bid_id", "")
            cur_ask_id = current.get("ask_id", "")

            # Update bid if price changed
            if cur_bid_px != target_bid:
                # Cancel old bid
                if cur_bid_id:
                    try:
                        await self._kalshi_client.cancel_order(cur_bid_id)
                        n_cancelled += 1
                    except Exception:
                        pass

                # Place new bid
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
                    n_placed += 1
                except Exception as exc:
                    logger.warning("LIP: failed bid %s @ %dc: %s", ticker, target_bid, exc)
                    self._resting.setdefault(ticker, {})["bid_id"] = ""
                    self._resting[ticker]["bid_px"] = 0
            else:
                n_kept += 1

            # Update ask if price changed
            if cur_ask_px != target_ask:
                if cur_ask_id:
                    try:
                        await self._kalshi_client.cancel_order(cur_ask_id)
                        n_cancelled += 1
                    except Exception:
                        pass

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
                    n_placed += 1
                except Exception as exc:
                    logger.warning("LIP: failed ask %s @ %dc: %s", ticker, target_ask, exc)
                    self._resting.setdefault(ticker, {})["ask_id"] = ""
                    self._resting[ticker]["ask_px"] = 0
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

        logger.info(
            "LIP CYCLE: placed=%d kept=%d cancelled=%d resting=%d strikes",
            n_placed, n_kept, n_cancelled, len(self._resting),
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
        tau = max(0.5, self._days_to_settlement) / 365.0
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

            # Forward: prefer Pyth real-time ZS, fall back to Kalshi
            _pf = None
            if self._pyth_provider is not None and self._pyth_provider.pyth_available:
                _pf = self._pyth_provider.forward_price
            if _pf is not None and _pf > 0:
                self._forward_estimate = _pf
                logger.info("FORWARD: Pyth ZS=%.4f $/bu", _pf)
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
                logger.info("FORWARD: Kalshi=%.4f (Pyth N/A)", self._forward_estimate)

            # Days to settlement
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
