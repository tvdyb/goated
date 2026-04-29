"""Main entry point for the live market-making system.

Wires together: CME ingest -> RND pipeline -> quoter -> Kalshi order
submission -> position tracking -> risk monitoring -> hedge trigger ->
IB hedge execution.

Synchronous main loop; asyncio for I/O only (per non-negotiable).

Usage:
    python -m deploy.main --config deploy/config.yaml
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

from attribution.pnl import FillRecord, PnLTracker
from engine.goldman_roll import is_in_roll_window, roll_drift_cents
from engine.implied_vol import calibrate_vol, extract_strike_mids_from_orderbooks
from engine.kill import KillSwitch, TriggerResult, batch_cancel_all
from engine.wasde_density import (
    WASDEAdjustment,
    WASDEDensityConfig,
    apply_wasde_shift,
    create_adjustment,
)
from engine.quoter import (
    EventBook,
    QuoteAction,
    QuoteActionType,
    QuoterConfig,
    StrikeBook,
    compute_quotes,
)
from engine.risk import RiskGate, RiskLimits
from engine.weather_skew import (
    WeatherSkewResult,
    apply_weather_skew,
    compute_weather_skew,
)
from feeds.weather.gefs_client import create_outlook_from_manual
from engine.rnd.bucket_integrator import BucketPrices
from engine.rnd.pipeline import RNDValidationError, compute_rnd
from engine.settlement_gate import GateState, SettlementGateConfig, gate_state
from engine.taker_imbalance import ImbalanceConfig, TakerImbalanceDetector
from feeds.usda.wasde_parser import (
    WASDEConsensus,
    WASDEParseError,
    WASDESurprise,
    compute_surprise,
    parse_wasde_file,
    parse_wasde_json,
)
from feeds.ibkr.options_chain import IBKRChainError, IBKROptionsChainPuller
from feeds.pyth.forward import PythForwardProvider, load_pyth_forward_config
from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from hedge.delta_aggregator import aggregate_delta
from hedge.ibkr_client import HedgeConnectionError, IBKRClient
from hedge.sizer import compute_hedge_size
from hedge.trigger import HedgeTrigger
from state.positions import Fill, PositionStore

logger = logging.getLogger("deploy.main")

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------


def load_config(path: str) -> dict[str, Any]:
    """Load YAML config file."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file {path} did not produce a dict")
    return cfg


def _build_quoter_config(cfg: dict[str, Any]) -> QuoterConfig:
    q = cfg.get("quoter", {})
    series = cfg.get("series", [{}])
    s = series[0] if series else {}
    return QuoterConfig(
        min_half_spread_cents=q.get("min_half_spread_cents", 2),
        max_half_spread_cents=q.get("max_half_spread_cents", 4),
        inventory_skew_gamma=q.get("inventory_skew_gamma", 0.1),
        max_contracts_per_strike=s.get("max_contracts_per_strike", q.get("max_contracts_per_strike", 3)),
        fee_threshold_cents=q.get("fee_threshold_cents", 1),
        taker_rate=q.get("taker_rate", 0.07),
        maker_fraction=q.get("maker_fraction", 0.25),
    )


def _build_risk_limits(cfg: dict[str, Any]) -> RiskLimits:
    r = cfg.get("risk", {})
    return RiskLimits(
        aggregate_delta_cap=r.get("aggregate_delta_cap", 500),
        per_event_delta_cap=r.get("per_event_delta_cap", 200),
        max_loss_cents=r.get("max_total_inventory_usd", 1000) * 100,
    )


def _build_settlement_gate_config(cfg: dict[str, Any]) -> SettlementGateConfig:
    sg = cfg.get("settlement_gate", {})
    return SettlementGateConfig(
        pull_before=float(sg.get("pre_window_seconds", 60)),
        post_window=float(sg.get("post_window_minutes", 15)) * 60,
    )


def _build_imbalance_config(cfg: dict[str, Any]) -> ImbalanceConfig:
    ti = cfg.get("taker_imbalance", {})
    return ImbalanceConfig(
        window_seconds=ti.get("window_seconds", 60.0),
        threshold=ti.get("threshold", 0.7),
        cooldown_seconds=ti.get("cooldown_seconds", 120.0),
        min_trades=ti.get("min_trades", 5),
    )


# ---------------------------------------------------------------------------
# MarketMaker — the main orchestrator
# ---------------------------------------------------------------------------


class MarketMaker:
    """Single-process market-making orchestrator.

    Runs a periodic loop that wires all components together.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._running = False

        # -- Build sub-components --
        self._quoter_config = _build_quoter_config(cfg)
        self._risk_limits = _build_risk_limits(cfg)
        self._sg_config = _build_settlement_gate_config(cfg)
        self._imbalance_config = _build_imbalance_config(cfg)

        # Core state
        self._position_store = PositionStore()
        self._risk_gate = RiskGate(self._position_store, self._risk_limits)
        self._imbalance_detector = TakerImbalanceDetector(self._imbalance_config)
        self._pnl_tracker = PnLTracker()

        # Hedge
        hedge_cfg = cfg.get("hedge", {})
        self._hedge_trigger = HedgeTrigger(
            threshold=hedge_cfg.get("threshold_contracts", 3.0),
            cooldown_s=hedge_cfg.get("cooldown_s", 60.0),
        )
        self._ib_client = IBKRClient(
            disconnect_timeout_s=cfg.get("risk", {}).get(
                "hedge_disconnect_timeout_s", 15.0
            ),
        )

        # Kalshi client (initialized in startup)
        self._kalshi_client: KalshiClient | None = None

        # Kill switch (initialized in startup)
        self._kill_switch: KillSwitch | None = None

        # Loop timing
        self._cycle_seconds = cfg.get("loop", {}).get("cycle_seconds", 30)

        # Series config
        self._series = cfg.get("series", [])
        if not self._series:
            raise ValueError("No series configured in config")

        # Track open order IDs -> market_ticker for kill switch
        self._open_orders: list[tuple[str, str]] = []

        # Strike -> Kalshi market ticker mapping (populated by _get_active_event)
        self._market_tickers: dict[float, str] = {}

        # Synthetic RND parameters
        self._forward_estimate: float = 0.0  # updated from Pyth or Kalshi quotes
        self._vol_estimate: float = cfg.get("synthetic", {}).get("vol", 0.15)
        self._days_to_settlement: float = 2.0

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

        # IBKR options chain puller (for real RND pipeline)
        ibkr_chain_cfg = cfg.get('ibkr_chain', {})
        self._ibkr_chain_enabled = ibkr_chain_cfg.get('enabled', False)
        self._ibkr_chain_puller: IBKROptionsChainPuller | None = None
        if self._ibkr_chain_enabled:
            api_cfg = self._cfg.get('api', {})
            self._ibkr_chain_puller = IBKROptionsChainPuller(
                host=ibkr_chain_cfg.get('host', api_cfg.get('ib_gateway_host', '127.0.0.1')),
                port=int(ibkr_chain_cfg.get('port', api_cfg.get('ib_gateway_port', 4002))),
                client_id=ibkr_chain_cfg.get('client_id', 10),
                cache_ttl_s=float(ibkr_chain_cfg.get('cache_ttl_s', 900.0)),
            )

        # Capital cap
        self._max_loss_cents = self._risk_limits.max_loss_cents

        # Weather skew (Phase T-70)
        weather_cfg = cfg.get("weather_skew", {})
        self._weather_skew_enabled = weather_cfg.get("enabled", False)
        self._weather_temp_anomaly_f: float = weather_cfg.get("temp_anomaly_f", 0.0)
        self._weather_precip_anomaly_pct: float = weather_cfg.get("precip_anomaly_pct", 0.0)

        # WASDE density adjustment
        wasde_cfg = cfg.get("wasde", {})
        self._wasde_config = WASDEDensityConfig(
            sensitivity_cents_per_mbu=wasde_cfg.get("sensitivity_cents_per_mbu", 18.0),
            decay_half_life_hours=wasde_cfg.get("decay_half_life_hours", 6.0),
            max_shift_cents=wasde_cfg.get("max_shift_cents", 100.0),
        )
        self._wasde_adjustment: WASDEAdjustment | None = None
        self._wasde_consensus = WASDEConsensus(
            ending_stocks=wasde_cfg.get("consensus_ending_stocks"),
            production=wasde_cfg.get("consensus_production"),
            exports=wasde_cfg.get("consensus_exports"),
        )
        self._wasde_data_path: str | None = wasde_cfg.get("data_path")
        self._wasde_was_pulled = False  # track if gate was PULL_ALL last cycle

    # ── Startup ────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Initialize connections and load initial data."""
        logger.info("STARTUP: initializing market maker")

        # Kalshi client
        api_key = os.environ.get("KALSHI_API_KEY", "")
        private_key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if not api_key or not private_key_path:
            raise RuntimeError(
                "KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH env vars required"
            )

        private_key_pem = Path(private_key_path).read_bytes()
        auth = KalshiAuth(api_key=api_key, private_key_pem=private_key_pem)

        api_cfg = self._cfg.get("api", {})
        base_url = api_cfg.get("kalshi_base", "https://api.elections.kalshi.com")
        self._kalshi_client = KalshiClient(auth=auth, base_url=base_url)
        await self._kalshi_client.open()
        logger.info("STARTUP: Kalshi client connected")

        # Pyth forward provider
        if self._pyth_provider is not None:
            try:
                await self._pyth_provider.start()
                logger.info("STARTUP: Pyth forward provider started")
            except Exception as exc:
                logger.warning("STARTUP: Pyth forward start failed: %s", exc)
                self._pyth_provider = None

        # IB client
        series_cfg = self._series[0]
        if series_cfg.get("hedge_enabled", False):
            ib_host = os.environ.get(
                "IB_GATEWAY_HOST",
                api_cfg.get("ib_gateway_host", "127.0.0.1"),
            )
            ib_port = int(
                os.environ.get(
                    "IB_GATEWAY_PORT",
                    str(api_cfg.get("ib_gateway_port", 4001)),
                )
            )
            ib_client_id = api_cfg.get("ib_client_id", 1)
            try:
                await self._ib_client.connect(ib_host, ib_port, ib_client_id)
                logger.info("STARTUP: IB Gateway connected")
            except HedgeConnectionError as exc:
                logger.warning(
                    "STARTUP: IB Gateway connection failed: %s. "
                    "Running without hedge.",
                    exc,
                )

        # IBKR options chain puller
        if self._ibkr_chain_puller is not None:
            try:
                await self._ibkr_chain_puller.connect()
                logger.info('STARTUP: IBKR options chain puller connected')
            except IBKRChainError as exc:
                logger.warning(
                    'STARTUP: IBKR chain puller connection failed: %s. '
                    'Falling back to synthetic RND.',
                    exc,
                )
                self._ibkr_chain_puller = None

        # Kill switch
        self._kill_switch = KillSwitch(client=self._kalshi_client)
        self._kill_switch.add_trigger(self._risk_gate.make_kill_trigger())

        # IB disconnect trigger — only if hedge is enabled
        if self._series[0].get("hedge_enabled", False) and self._ib_client.connected:
            def _delta_port_fn() -> float:
                return self._compute_delta()

            self._kill_switch.add_trigger(
                self._hedge_trigger.make_kill_trigger(
                    lambda: self._ib_client.connected,
                    _delta_port_fn,
                )
            )

        # PnL drawdown trigger
        pnl_threshold_pct = self._cfg.get("risk", {}).get(
            "kill_switch_pnl_threshold_pct", 5
        )
        pnl_threshold_cents = int(self._max_loss_cents * pnl_threshold_pct / 100)

        def _pnl_drawdown_trigger() -> TriggerResult:
            total_loss = self._position_store.total_max_loss_cents()
            if total_loss > pnl_threshold_cents:
                return TriggerResult(
                    fired=True,
                    name="pnl_drawdown",
                    detail=f"max_loss={total_loss}c > threshold={pnl_threshold_cents}c",
                )
            return TriggerResult(fired=False, name="pnl_drawdown")

        self._kill_switch.add_trigger(_pnl_drawdown_trigger)

        # Reconcile positions
        await self._reconcile_positions()

        logger.info("STARTUP: complete")

    # ── Shutdown ───────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Graceful shutdown: cancel all orders, close connections."""
        logger.info("SHUTDOWN: initiating graceful shutdown")
        self._running = False

        # Cancel all resting Kalshi orders
        if self._kalshi_client is not None:
            try:
                order_ids = [oid for oid, _ in self._open_orders]
                if order_ids:
                    await batch_cancel_all(self._kalshi_client, order_ids)
                    logger.info(
                        "SHUTDOWN: cancelled %d resting orders", len(order_ids)
                    )
            except Exception as exc:
                logger.error("SHUTDOWN: error cancelling orders: %s", exc)

            await self._kalshi_client.close()

        # Stop Pyth forward provider
        if self._pyth_provider is not None:
            try:
                await self._pyth_provider.stop()
            except Exception:
                pass

        # Disconnect IB
        if self._ib_client.connected:
            await self._ib_client.disconnect()
            logger.info("SHUTDOWN: IB disconnected")

        # Disconnect IBKR chain puller
        if self._ibkr_chain_puller is not None and self._ibkr_chain_puller.connected:
            await self._ibkr_chain_puller.disconnect()
            logger.info('SHUTDOWN: IBKR chain puller disconnected')

        # Write PnL summary
        self._pnl_tracker.write_summary()
        logger.info("SHUTDOWN: complete")

    # ── Main loop ──────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the main trading loop."""
        self._running = True
        logger.info("MAIN LOOP: starting (cycle=%ds)", self._cycle_seconds)

        while self._running:
            cycle_start = time.monotonic()
            try:
                await self._cycle()
            except Exception as exc:
                logger.error("MAIN LOOP: cycle error: %s", exc, exc_info=True)
                # On error, try to cancel all orders as safety measure
                try:
                    order_ids = [oid for oid, _ in self._open_orders]
                    if order_ids and self._kalshi_client is not None:
                        await batch_cancel_all(self._kalshi_client, order_ids)
                        self._open_orders.clear()
                except Exception:
                    logger.error("MAIN LOOP: error in safety cancel", exc_info=True)

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, self._cycle_seconds - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _cycle(self) -> None:
        """Execute one iteration of the main trading loop."""
        assert self._kalshi_client is not None
        now = datetime.now(_ET)
        now_ts = time.time()

        # 0. Cancel ALL resting orders (pull fresh list from API)
        try:
            resp = await self._kalshi_client.get_orders(status="resting", limit=100)
            live_orders = resp.get("orders", [])
            if live_orders:
                logger.info("CYCLE: cancelling %d resting orders", len(live_orders))
                for o in live_orders:
                    try:
                        await self._kalshi_client.cancel_order(o["order_id"])
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("CYCLE: failed to fetch/cancel orders: %s", exc)
        self._open_orders.clear()

        # 1. Get active event and strikes
        series_cfg = self._series[0]
        event_ticker, kalshi_strikes = await self._get_active_event(
            series_cfg["ticker_prefix"]
        )
        if event_ticker is None:
            logger.info("CYCLE: no active event for %s", series_cfg["ticker_prefix"])
            return

        # 2. Pull orderbooks (needed for vol calibration before fair value)
        event_book = await self._pull_orderbooks(event_ticker, kalshi_strikes)

        # 2b. Calibrate vol from Kalshi orderbook mid-prices
        self._calibrate_vol_from_orderbooks(event_book)

        # 3. Compute fair values — try IBKR RND pipeline, fall back to synthetic
        bucket_prices = await self._compute_fair_values(kalshi_strikes)

        # 4. Settlement gate
        gate = gate_state(now, series="soy", config=self._sg_config)
        logger.info(
            "CYCLE: gate=%s size_mult=%.2f spread_mult=%.2f next=%s tte=%.0fs",
            gate.state.name,
            gate.size_mult,
            gate.spread_mult,
            gate.next_event_name,
            gate.time_to_event_seconds,
        )

        # 4b. WASDE density adjustment
        #   - When gate transitions from PULL_ALL to non-PULL_ALL (post-WASDE),
        #     load WASDE data and create adjustment if available.
        #   - Apply decaying mean-shift to bucket_prices while adjustment is active.
        if gate.state == GateState.PULL_ALL and "WASDE" in gate.next_event_name:
            self._wasde_was_pulled = True
        elif self._wasde_was_pulled and gate.state != GateState.PULL_ALL:
            # Gate just re-opened after WASDE — try to load and apply adjustment
            self._wasde_was_pulled = False
            self._try_load_wasde_adjustment(now_ts)

        if self._wasde_adjustment is not None:
            if self._wasde_adjustment.is_expired(now_ts):
                logger.info("WASDE: adjustment expired, clearing")
                self._wasde_adjustment = None
            else:
                try:
                    bucket_prices = apply_wasde_shift(
                        bucket_prices,
                        self._wasde_adjustment,
                        forward=self._forward_estimate,
                        sigma=self._vol_estimate,
                        tau=max(1.0, self._days_to_settlement) / 365.0,
                        now=now_ts,
                    )
                except Exception as exc:
                    logger.error("WASDE: density shift failed: %s", exc)

        # 5. Taker imbalance
        imbalance = self._imbalance_detector.current_signal(now_ts)
        withdraw_side = imbalance.withdraw_side if imbalance else None

        # 6. Risk gate pre-check
        risk_ok = not self._risk_gate.check_post_trade().fired

        # 7. Capital cap check
        current_loss = self._position_store.total_max_loss_cents()
        if current_loss >= self._max_loss_cents:
            logger.warning(
                "CYCLE: capital cap reached (%dc >= %dc), risk_ok=False",
                current_loss,
                self._max_loss_cents,
            )
            risk_ok = False

        # 8. Quoter
        inventory = self._get_inventory()
        actions = compute_quotes(
            rnd_prices=bucket_prices,
            event_book=event_book,
            inventory=inventory,
            risk_ok=risk_ok,
            gate_size_mult=gate.size_mult,
            gate_spread_mult=gate.spread_mult,
            imbalance_withdraw_side=withdraw_side,
            config=self._quoter_config,
        )

        # 9. Execute quote actions
        await self._execute_actions(actions)

        # 10. Process fills and update positions
        await self._process_fills(event_ticker)

        # 11. Hedge check
        if series_cfg.get("hedge_enabled", False) and self._ib_client.connected:
            delta_port = aggregate_delta(
                self._position_store, bucket_prices, event_ticker
            )
            if self._hedge_trigger.should_hedge(delta_port):
                n_contracts = compute_hedge_size(
                    delta_port,
                    self._forward_estimate,
                )
                if n_contracts != 0:
                    side = "buy" if n_contracts > 0 else "sell"
                    try:
                        result = await self._ib_client.place_hedge(
                            series_cfg["cme_symbol"],
                            abs(n_contracts),
                            side,
                        )
                        self._hedge_trigger.record_hedge()
                        logger.info("CYCLE: hedge placed: %s", result)
                    except HedgeConnectionError as exc:
                        logger.error("CYCLE: hedge failed: %s", exc)

        # 12. Kill switch check
        if self._kill_switch is not None:
            # Refresh open orders from API to avoid stale IDs
            await self._refresh_open_orders()
            order_ids = [oid for oid, _ in self._open_orders]
            if order_ids:
                try:
                    ks_result = await self._kill_switch.check_and_fire(order_ids)
                except Exception as exc:
                    logger.error("CYCLE: kill switch error: %s", exc)
                    self._open_orders.clear()
                    ks_result = None
                if ks_result and ks_result.fired:
                    logger.warning(
                        "CYCLE: KILL SWITCH FIRED — trigger=%s, cancelled=%d orders",
                        ks_result.trigger_name,
                        len(ks_result.cancelled_ids),
                    )
                self._open_orders.clear()

        # 13. Log PnL
        self._pnl_tracker.log_cycle(
            position_store=self._position_store,
            bucket_prices=bucket_prices,
            event_ticker=event_ticker,
        )

        logger.info(
            "CYCLE: complete — actions=%d, open_orders=%d, max_loss=%dc",
            len(actions),
            len(self._open_orders),
            self._position_store.total_max_loss_cents(),
        )

    # ── Helpers ────────────────────────────────────────────────────

    async def _compute_fair_values(self, kalshi_strikes: np.ndarray) -> BucketPrices:
        """Compute bucket prices: IBKR RND pipeline -> synthetic fallback.

        If IBKR chain puller is connected, pulls the real options chain
        and runs the full RND pipeline. On any failure, falls back to
        synthetic GBM.
        """
        if self._ibkr_chain_puller is not None and self._ibkr_chain_puller.connected:
            try:
                series_cfg = self._series[0]
                chain = await self._ibkr_chain_puller.pull(
                    series_cfg.get("cme_symbol", "ZS"),
                )
                bucket_prices = compute_rnd(chain, kalshi_strikes)
                logger.info(
                    "CYCLE: IBKR RND pipeline — %d strikes, underlying=%.2f, "
                    "bucket_sum=%.4f",
                    len(chain.strikes),
                    chain.underlying_settle,
                    bucket_prices.bucket_sum,
                )
                return bucket_prices
            except (IBKRChainError, RNDValidationError) as exc:
                logger.warning(
                    "CYCLE: IBKR RND failed, falling back to synthetic: %s", exc
                )
            except Exception as exc:
                logger.error(
                    "CYCLE: unexpected error in IBKR RND, falling back to synthetic: %s",
                    exc,
                )

        return self._synthetic_rnd(kalshi_strikes)

    def _calibrate_vol_from_orderbooks(self, event_book: EventBook) -> None:
        """Calibrate vol from Kalshi orderbook mid-prices on near-ATM strikes."""
        if self._forward_estimate <= 0 or self._days_to_settlement <= 0:
            return

        tau = max(0.5, self._days_to_settlement) / 365.0
        fallback = self._cfg.get("synthetic", {}).get("vol", 0.15)

        strike_mids = [
            (sb.strike, (sb.best_bid_cents + sb.best_ask_cents) / 200.0)
            for sb in event_book.strike_books
            if sb.best_bid_cents > 0 and sb.best_ask_cents < 100
            and sb.best_bid_cents < sb.best_ask_cents
        ]

        self._vol_estimate = calibrate_vol(
            forward=self._forward_estimate,
            strike_mids=strike_mids,
            tau=tau,
            fallback=fallback,
        )

    def _synthetic_rnd(self, kalshi_strikes: np.ndarray) -> BucketPrices:
        """Compute fair values via synthetic GBM (Black-76).

        P(S > K) = N(d2) where d2 = (ln(F/K) - 0.5*sig^2*T) / (sig*sqrt(T))

        Forward is estimated from Kalshi quotes (midpoint of the strike
        closest to 50c survival). Vol is configurable (default 15%).
        """
        forward = self._forward_estimate
        if forward <= 0:
            # Estimate from strikes: use the middle strike as rough forward
            forward = float(kalshi_strikes[len(kalshi_strikes) // 2])
            self._forward_estimate = forward

        # Goldman roll drift: shift forward down during GSCI roll window
        today = datetime.now(_ET).date()
        drift_cents = 0.0
        try:
            drift_cents = roll_drift_cents(today)
        except ValueError:
            pass  # outside maintained holiday range — no adjustment
        if drift_cents != 0.0:
            # Forward is in dollars (e.g. 10.67); drift is in cents
            forward = forward + drift_cents / 100.0
            logger.info("GOLDMAN ROLL: drift=%.1fc, adjusted forward=%.4f", drift_cents, forward)

        sigma = self._vol_estimate

        # Weather-driven distribution skew (Phase T-70)
        # Active during growing season only (Jun-Aug U.S., Jan-Feb S.A.)
        if self._weather_skew_enabled:
            try:
                outlook = create_outlook_from_manual(
                    self._weather_temp_anomaly_f,
                    self._weather_precip_anomaly_pct,
                )
                skew = compute_weather_skew(outlook, as_of=today)
                if skew.mean_shift_cents != 0.0 or skew.vol_adjustment_pct != 0.0:
                    # forward is in dollars; shift is in cents
                    adj_fwd, adj_sig = apply_weather_skew(
                        forward * 100.0, sigma, skew
                    )
                    forward = adj_fwd / 100.0
                    sigma = adj_sig
                    logger.info(
                        "WEATHER SKEW: shift=%.1fc vol_adj=%.1f%% -> fwd=%.4f sig=%.1f%%",
                        skew.mean_shift_cents,
                        skew.vol_adjustment_pct * 100,
                        forward,
                        sigma * 100,
                    )
            except Exception as exc:
                logger.warning("WEATHER SKEW: failed: %s", exc)

        # Estimate days to settlement from event (default 2 days)
        tau = max(1.0, self._days_to_settlement) / 365.0
        sig_sqrt_t = sigma * math.sqrt(tau)

        sig_sqrt_t = max(sig_sqrt_t, 1e-12)

        survival = np.array([
            float(ndtr(
                (math.log(forward / k) - 0.5 * sigma ** 2 * tau) / sig_sqrt_t
            ))
            for k in kalshi_strikes
        ])

        n_buckets = len(kalshi_strikes) + 1
        bucket_yes = np.zeros(n_buckets, dtype=np.float64)
        bucket_yes[0] = 1.0 - survival[0]
        for i in range(1, len(survival)):
            bucket_yes[i] = survival[i - 1] - survival[i]
        bucket_yes[-1] = survival[-1]

        logger.info(
            "SYNTHETIC RND: forward=%.4f vol=%.1f%% tau=%.4f (%.1f days) strikes=%d",
            forward, sigma * 100, tau, tau * 365, len(kalshi_strikes),
        )

        return BucketPrices(
            kalshi_strikes=kalshi_strikes,
            survival=survival,
            bucket_yes=bucket_yes,
            bucket_sum=float(bucket_yes.sum()),
            n_buckets=n_buckets,
        )

    async def _get_active_event(
        self,
        ticker_prefix: str,
    ) -> tuple[str | None, np.ndarray]:
        """Find the next active Kalshi event and extract strike grid.

        Also populates self._market_tickers: strike -> actual market ticker.
        """
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_events(
                series_ticker=ticker_prefix, status="open", limit=5
            )
            events = resp.get("events", [])
            if not events:
                return None, np.array([])

            # Pick the earliest open event
            event = events[0]
            event_ticker = event["event_ticker"]

            # Fetch event detail for markets (events list doesn't include them)
            detail = await self._kalshi_client.get_event(event_ticker)
            markets = detail.get("markets", [])

            strikes = []
            self._market_tickers: dict[float, str] = {}
            for m in markets:
                strike_val = m.get("floor_strike")
                ticker = m.get("ticker", "")
                if strike_val is not None and ticker:
                    # floor_strike is in cents/bushel (e.g. 1066.99)
                    # Convert to dollars for RND (e.g. 10.6699)
                    strike_dollars = float(strike_val) / 100.0
                    strikes.append(strike_dollars)
                    self._market_tickers[strike_dollars] = ticker

            if not strikes:
                logger.warning("No strikes found for event %s", event_ticker)
                return None, np.array([])

            # Forward: prefer Pyth real-time ZS, fall back to Kalshi
            _pyth_fwd = None
            if (
                self._pyth_provider is not None
                and self._pyth_provider.pyth_available
            ):
                _pyth_fwd = self._pyth_provider.forward_price

            if _pyth_fwd is not None and _pyth_fwd > 0:
                self._forward_estimate = _pyth_fwd
                logger.info("FORWARD: Pyth ZS=%.4f $/bu", _pyth_fwd)
            else:
                best_forward = float(sorted(strikes)[len(strikes) // 2])
                for m in markets:
                    bid_str = m.get("yes_bid_dollars", "0")
                    ask_str = m.get("yes_ask_dollars", "1")
                    bid = float(bid_str) if bid_str else 0.0
                    ask = float(ask_str) if ask_str else 1.0
                    mid = (bid + ask) / 2.0
                    if 0.40 <= mid <= 0.60:
                        fs = m.get("floor_strike")
                        if fs is not None:
                            best_forward = float(fs) / 100.0
                            break
                self._forward_estimate = best_forward
                logger.info(
                    "FORWARD: Kalshi-inferred=%.4f (Pyth unavailable)",
                    best_forward,
                )

            # Estimate days to settlement from expiration_time
            for m in markets:
                et = m.get("expiration_time", "")
                if et:
                    try:
                        exp_dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
                        days_left = (exp_dt - datetime.now(exp_dt.tzinfo)).total_seconds() / 86400.0
                        self._days_to_settlement = max(0.5, days_left)
                    except (ValueError, TypeError):
                        pass
                    break

            logger.info(
                "EVENT: %s — %d strikes, forward=%.4f, days_to_settle=%.1f",
                event_ticker, len(strikes), self._forward_estimate, self._days_to_settlement,
            )

            return event_ticker, np.array(sorted(strikes), dtype=np.float64)

        except Exception as exc:
            logger.error("Failed to get active event: %s", exc)
            return None, np.array([])

    async def _pull_orderbooks(
        self,
        event_ticker: str,
        kalshi_strikes: np.ndarray,
    ) -> EventBook:
        """Pull orderbook snapshots for all strikes in an event."""
        assert self._kalshi_client is not None
        strike_books: list[StrikeBook] = []

        for strike in kalshi_strikes:
            market_ticker = self._market_tickers.get(strike, "")
            if not market_ticker:
                continue

            try:
                ob = await self._kalshi_client.get_orderbook(market_ticker)
                # Kalshi returns: {"orderbook_fp": {"yes_dollars": [[price, size], ...], "no_dollars": [...]}}
                orderbook_fp = ob.get("orderbook_fp", ob.get("orderbook", {}))

                yes_levels = orderbook_fp.get("yes_dollars", [])
                no_levels = orderbook_fp.get("no_dollars", [])

                # yes_dollars are bids for Yes side: [[price_str, size_str], ...]
                # Prices are in dollars (e.g. "0.45" = 45 cents)
                best_bid = 0
                best_ask = 100
                if yes_levels:
                    best_bid = max(
                        int(round(float(lvl[0]) * 100))
                        for lvl in yes_levels
                    )
                if no_levels:
                    # No bids: best no bid price -> Yes ask = 100 - no_bid
                    best_no_bid = max(
                        int(round(float(lvl[0]) * 100))
                        for lvl in no_levels
                    )
                    best_ask = 100 - best_no_bid

                strike_books.append(
                    StrikeBook(
                        market_ticker=market_ticker,
                        strike=strike,
                        best_bid_cents=best_bid,
                        best_ask_cents=best_ask,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to pull orderbook for %s: %s", market_ticker, exc
                )
                strike_books.append(
                    StrikeBook(
                        market_ticker=market_ticker,
                        strike=strike,
                        best_bid_cents=0,
                        best_ask_cents=100,
                    )
                )

        return EventBook(event_ticker=event_ticker, strike_books=strike_books)

    async def _execute_actions(self, actions: list[QuoteAction]) -> None:
        """Execute quote actions via Kalshi REST API."""
        assert self._kalshi_client is not None
        new_open: list[tuple[str, str]] = []

        for action in actions:
            if action.action_type == QuoteActionType.CANCEL:
                # Cancel any resting orders for this market
                to_cancel = [
                    oid
                    for oid, ticker in self._open_orders
                    if ticker == action.market_ticker
                ]
                for oid in to_cancel:
                    try:
                        await self._kalshi_client.cancel_order(oid)
                    except Exception as exc:
                        logger.warning("Failed to cancel order %s: %s", oid, exc)
                # Remove cancelled from open orders
                self._open_orders = [
                    (oid, t)
                    for oid, t in self._open_orders
                    if t != action.market_ticker
                ]

            elif action.action_type == QuoteActionType.PLACE_BID:
                # Cancel existing bids for this market first
                await self._cancel_side(action.market_ticker, "bid")
                try:
                    resp = await self._kalshi_client.create_order(
                        ticker=action.market_ticker,
                        action="buy",
                        side="yes",
                        order_type="limit",
                        count=action.size,
                        yes_price=action.price_cents,
                        post_only=True,
                    )
                    order = resp.get("order", {})
                    order_id = order.get("order_id", "")
                    if order_id:
                        new_open.append((order_id, action.market_ticker))
                except Exception as exc:
                    logger.warning(
                        "Failed to place bid on %s: %s",
                        action.market_ticker,
                        exc,
                    )

            elif action.action_type == QuoteActionType.PLACE_ASK:
                await self._cancel_side(action.market_ticker, "ask")
                try:
                    # Selling Yes = placing ask
                    resp = await self._kalshi_client.create_order(
                        ticker=action.market_ticker,
                        action="sell",
                        side="yes",
                        order_type="limit",
                        count=action.size,
                        yes_price=action.price_cents,
                        post_only=True,
                    )
                    order = resp.get("order", {})
                    order_id = order.get("order_id", "")
                    if order_id:
                        new_open.append((order_id, action.market_ticker))
                except Exception as exc:
                    logger.warning(
                        "Failed to place ask on %s: %s",
                        action.market_ticker,
                        exc,
                    )

        self._open_orders.extend(new_open)

    async def _cancel_side(self, market_ticker: str, side: str) -> None:
        """Cancel existing orders on one side for a market.

        Since we don't track bid vs ask order IDs separately, this
        cancels all orders for the market. A future optimization can
        track sides.
        """
        # For now, skip side-specific cancellation -- orders are replaced
        # each cycle anyway.
        pass

    async def _process_fills(self, event_ticker: str) -> None:
        """Pull recent fills and apply to position store."""
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_fills(limit=50)
            fills = resp.get("fills", [])
            for f in fills:
                fill_id = f.get("trade_id", f.get("fill_id", ""))
                if not fill_id:
                    continue
                ticker = f.get("ticker", "")
                if not ticker:
                    continue

                count = int(float(f.get("count", f.get("count_fp", "0"))))
                if count <= 0:
                    continue

                yes_price_str = f.get("yes_price", f.get("yes_price_dollars", "0"))
                price_cents = int(round(float(yes_price_str) * 100)) if "." in str(yes_price_str) else int(yes_price_str)
                price_cents = max(1, min(99, price_cents))

                fill = Fill(
                    market_ticker=ticker,
                    side=f.get("side", "yes"),
                    action=f.get("action", "buy"),
                    count=count,
                    price_cents=price_cents,
                    fill_id=str(fill_id),
                )
                self._position_store.apply_fill(fill)

                # Record for PnL attribution
                self._pnl_tracker.record_fill(FillRecord(
                    timestamp=time.time(),
                    market_ticker=ticker,
                    side=f.get("side", "yes"),
                    action=f.get("action", "buy"),
                    count=count,
                    price_cents=price_cents,
                    fill_id=str(fill_id),
                ))

        except Exception as exc:
            logger.error("Failed to process fills: %s", exc)

    async def _reconcile_positions(self) -> None:
        """Reconcile local positions against Kalshi API.

        Kalshi API returns positions with:
        - ticker: market ticker
        - position_fp: signed quantity as float string (e.g. "11.00")
        We convert to the format expected by PositionStore.reconcile().
        """
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_positions(limit=100)
            api_positions = resp.get("market_positions", [])

            # Convert Kalshi format to what PositionStore.reconcile expects
            converted = []
            for p in api_positions:
                ticker = p.get("ticker", "")
                position_fp = p.get("position_fp", "0")
                qty = int(float(position_fp))
                if qty != 0:
                    converted.append({
                        "ticker": ticker,
                        "market_exposure": qty,
                    })

            if converted:
                self._position_store.reconcile(converted)
            logger.info(
                "STARTUP: position reconciliation passed (%d positions)",
                len(converted),
            )
        except Exception as exc:
            logger.warning("STARTUP: position reconciliation: %s", exc)

    def _get_inventory(self) -> dict[str, int]:
        """Get signed inventory per market ticker."""
        snap = self._position_store.snapshot()
        return {ticker: pos.signed_qty for ticker, pos in snap.items()}

    def _compute_delta(self) -> float:
        """Compute current portfolio delta (for kill switch trigger)."""
        # Get active event ticker from open orders
        event_tickers = set()
        for _, ticker in self._open_orders:
            parts = ticker.rsplit("-", 1)
            if len(parts) == 2:
                event_tickers.add(parts[0])

        if not event_tickers:
            return 0.0

        # Use the first event
        event_ticker = next(iter(event_tickers))
        try:
            # We need bucket prices for delta computation
            # Use a simple estimate: sum of signed positions
            snap = self._position_store.snapshot()
            return sum(
                pos.signed_qty
                for pos in snap.values()
                if pos.event_ticker == event_ticker
            )
        except Exception:
            return 0.0

    async def _refresh_open_orders(self) -> None:
        """Refresh the list of open orders from the Kalshi API."""
        assert self._kalshi_client is not None
        try:
            resp = await self._kalshi_client.get_orders(status="resting", limit=100)
            orders = resp.get("orders", [])
            self._open_orders = [
                (o["order_id"], o.get("ticker", ""))
                for o in orders
                if o.get("order_id")
            ]
        except Exception as exc:
            logger.warning("Failed to refresh open orders: %s", exc)


    def _try_load_wasde_adjustment(self, now_ts: float) -> None:
        """Load WASDE data and create density adjustment post-release."""
        if self._wasde_adjustment is not None:
            return
        try:
            if self._wasde_data_path:
                report = parse_wasde_file(self._wasde_data_path)
            else:
                logger.info("WASDE: no data_path configured, skipping adjustment")
                return
            surprise = compute_surprise(report, consensus=self._wasde_consensus)
            self._wasde_adjustment = create_adjustment(
                surprise, release_timestamp=now_ts, config=self._wasde_config,
            )
            logger.info(
                "WASDE: loaded — es_delta=%.1f Mbu, shift=%.1fc/bu",
                surprise.ending_stocks_delta,
                self._wasde_adjustment.mean_shift_cents,
            )
        except WASDEParseError as exc:
            logger.warning("WASDE: failed to load data: %s", exc)
        except Exception as exc:
            logger.error("WASDE: unexpected error: %s", exc)

    def load_wasde_adjustment(
        self, surprise: WASDESurprise, release_timestamp: float | None = None,
    ) -> None:
        """Manually inject a WASDE adjustment (for testing or manual entry)."""
        self._wasde_adjustment = create_adjustment(
            surprise, release_timestamp=release_timestamp, config=self._wasde_config,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Goated market maker")
    parser.add_argument(
        "--config",
        default="deploy/config.yaml",
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)-25s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = load_config(args.config)
    mm = MarketMaker(cfg)

    # Signal handling for graceful shutdown
    loop = asyncio.new_event_loop()

    def _signal_handler() -> None:
        logger.info("Signal received, shutting down...")
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
