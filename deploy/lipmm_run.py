"""lipmm_run — single-command deploy for any Kalshi event.

Wires the lipmm framework against one Kalshi event (`--event-ticker
KXISMPMI-26MAY` etc.) and brings up the dashboard at port 5050. Bot
starts safe-by-default: stub theo returns confidence=0.0 → no quotes
until the operator sets per-strike theo overrides via the dashboard.

Usage::

    export KALSHI_API_KEY=...
    export KALSHI_PRIVATE_KEY_PATH=...
    export LIPMM_CONTROL_SECRET=$(python -c 'import secrets;print(secrets.token_hex(16))')

    python -m deploy.lipmm_run --event-ticker KXISMPMI-26MAY

Then open http://<host>:5050 and paste the secret.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Any

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from lipmm.control import (
    Broadcaster,
    ControlServer,
    ControlState,
)
from lipmm.execution import OrderManager
from lipmm.execution.adapters import KalshiExchangeAdapter
from lipmm.incentives import EarningsAccrual, KalshiIncentiveProvider
from lipmm.observability import DecisionLogger, RetentionManager
from lipmm.quoting.strategies import (
    DefaultLIPQuoting,
    DefaultLIPQuotingConfig,
    StickyDefenseConfig,
    StickyDefenseQuoting,
)
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    MaxOrdersPerCycleGate,
    MaxPositionPerSideGate,
    MidDeltaGate,
    RiskRegistry,
)
from lipmm.runner import LIPRunner, RunnerConfig
from lipmm.theo import TheoRegistry

from deploy._stub_theo import StubTheoProvider

logger = logging.getLogger("lipmm_run")


# ── Required env vars ──────────────────────────────────────────────


_REQUIRED_ENV_VARS = (
    "KALSHI_API_KEY",
    "KALSHI_PRIVATE_KEY_PATH",
    "LIPMM_CONTROL_SECRET",
)


def _validate_env() -> None:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        sys.stderr.write(
            "ERROR: missing required env vars: " + ", ".join(missing) + "\n\n"
        )
        if "LIPMM_CONTROL_SECRET" in missing:
            sys.stderr.write(
                "Generate one with:\n"
                "  export LIPMM_CONTROL_SECRET=\"$(python -c "
                "'import secrets; print(secrets.token_hex(16))')\"\n\n"
                "Save the printed value — you'll paste it on the dashboard "
                "login page.\n\n"
            )
        if "KALSHI_API_KEY" in missing or "KALSHI_PRIVATE_KEY_PATH" in missing:
            sys.stderr.write(
                "Set your Kalshi credentials:\n"
                "  export KALSHI_API_KEY=...\n"
                "  export KALSHI_PRIVATE_KEY_PATH=/path/to/private_key.pem\n\n"
            )
        sys.exit(2)


# ── Ticker source ──────────────────────────────────────────────────


_SKIPPED_MARKET_STATUSES = {
    "settled", "finalized", "closed", "unopened", "deactivated",
}


def _markets_from_event_response(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """Kalshi returns markets as a sibling top-level field by default,
    OR nested inside `event` when with_nested_markets=true. Read both
    paths and dedupe so either response shape works.
    """
    event = resp.get("event") or {}
    nested = event.get("markets") or []
    sibling = resp.get("markets") or []
    return list(nested) + list(sibling)


def _filter_tradable_tickers(markets: list[dict[str, Any]]) -> list[str]:
    """Status filter is a deny-list, not allow-list. Kalshi uses
    'active' for tradable markets. Anything not in the deny-list is
    treated as tradable — better to over-quote and have strategy/risk
    gates filter than to silently drop strikes."""
    seen: set[str] = set()
    out: list[str] = []
    for m in markets:
        status = m.get("status", "active")
        if status in _SKIPPED_MARKET_STATUSES:
            continue
        t = m.get("ticker") or m.get("market_ticker")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


class _MultiEventTickerSource:
    """TickerSource that yields markets across ALL events currently
    in `ControlState.active_events`. The operator adds/removes events
    via the dashboard at runtime; the cycle picks up the change next
    iteration.

    Per-event failures are tolerated (logged) — one event with a stale
    ticker shouldn't blank out the whole bot.
    """

    def __init__(self, client: KalshiClient, control_state: Any) -> None:
        self._client = client
        self._state = control_state

    async def list_active_tickers(self, _exchange: Any) -> list[str]:
        events = sorted(self._state.all_events())
        if not events:
            return []
        # Fetch each event's market list. Sequential is fine — typically
        # 1-5 events; gather would only matter at much larger fan-out.
        all_markets: list[dict[str, Any]] = []
        per_event_seen_status: dict[str, set[str]] = {}
        for ev in events:
            try:
                resp = await self._client.get_event(
                    ev, with_nested_markets=True,
                )
            except Exception as exc:
                logger.warning(
                    "TickerSource: get_event(%s) failed: %s", ev, exc,
                )
                continue
            ms = _markets_from_event_response(resp)
            all_markets.extend(ms)
            per_event_seen_status[ev] = {
                m.get("status", "active") for m in ms
            }
        out = _filter_tradable_tickers(all_markets)
        if not out and events:
            logger.warning(
                "TickerSource: 0 tradable markets across %d events: %s; "
                "statuses seen per event: %s",
                len(events), events, per_event_seen_status,
            )
        return out


async def _validate_event(client: KalshiClient, event_ticker: str) -> dict[str, Any]:
    """Used by ControlServer's add_event endpoint: confirm the event
    exists and has tradable markets. Raises on Kalshi error.
    """
    resp = await client.get_event(event_ticker, with_nested_markets=True)
    markets = _markets_from_event_response(resp)
    tradable = _filter_tradable_tickers(markets)
    return {
        "market_count": len(tradable),
        "raw_market_count": len(markets),
        "status": (resp.get("event") or {}).get("status", "?"),
    }


# ── Wire-up ────────────────────────────────────────────────────────


def _build_strategy(name: str) -> Any:
    name_lower = name.lower()
    if name_lower in ("default", "default-lip-quoting", "default_lip"):
        return DefaultLIPQuoting(DefaultLIPQuotingConfig())
    if name_lower in ("sticky", "sticky-defense", "sticky_defense"):
        return StickyDefenseQuoting(StickyDefenseConfig())
    raise ValueError(
        f"unknown --strategy {name!r}; pick 'default' or 'sticky'"
    )


def _build_risk_registry(cap_dollars: float) -> RiskRegistry:
    """Sensible v1 risk gates for a fresh deployment.

    - Per-side notional cap: half the total cap (so worst case the bot
      has full cap_dollars exposed across both sides).
    - Max 20 orders/cycle: prevents pathological churn if the strategy
      goes haywire.
    - Endgame guardrail: don't quote in the last 60s before settlement
      where adverse selection is largest.
    """
    return RiskRegistry([
        MaxNotionalPerSideGate(max_dollars=cap_dollars / 2),
        MaxOrdersPerCycleGate(max_orders=100),
        # Adverse-selection safeguards. Both knobs (max_position_per_side,
        # mid_delta_threshold_c) are tunable per-strike / per-event /
        # globally via the dashboard's Knobs tab.
        MaxPositionPerSideGate(max_position=200),
        MidDeltaGate(mid_delta_threshold_c=8.0),
        EndgameGuardrailGate(
            min_seconds_to_settle=60,
            deep_otm_threshold=5,
            deep_itm_threshold=95,
        ),
    ])


def _series_prefix(event_ticker: str) -> str:
    """KXISMPMI-26MAY → 'KXISMPMI'. Used for stub theo's series_prefix."""
    if "-" in event_ticker:
        return event_ticker.split("-", 1)[0]
    return event_ticker


def _print_banner(
    *, event_ticker: str, host: str, port: int, strategy: str,
    cap_dollars: float, log_dir: str,
) -> None:
    secret_preview = os.environ.get("LIPMM_CONTROL_SECRET", "")[:6] + "…"
    print(
        f"\n"
        f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"   lipmm bot starting\n"
        f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"   events:    {event_ticker or '(none — add via dashboard)'}\n"
        f"   strategy:  {strategy}\n"
        f"   cap:       ${cap_dollars:.0f}\n"
        f"   logs:      {log_dir}\n"
        f"   dashboard: http://{host}:{port}\n"
        f"   secret:    {secret_preview} (32 hex chars total)\n"
        f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"  Stub theo loaded — bot is SAFE: confidence=0.0 means it\n"
        f"  won't quote any strike until you set theo overrides via\n"
        f"  the dashboard's 'Theo overrides' panel.\n"
        f"\n"
        f"  Open the dashboard, paste the secret, and start trading.\n"
        f"\n",
        flush=True,
    )


# ── Main async entry ───────────────────────────────────────────────


async def _amain(args: argparse.Namespace) -> int:
    log_dir = args.decision_log_dir or f"logs/{args.event_ticker}_decisions"
    os.makedirs(log_dir, exist_ok=True)

    # 1. Auth + Kalshi client + adapter
    auth = KalshiAuth()  # reads env vars
    client = KalshiClient(auth=auth)
    await client.open()
    exchange = KalshiExchangeAdapter.from_client(client)

    # Sweep any zombie resting orders from a prior session before the
    # runner starts. Without this, Kalshi continues to lock collateral
    # against orders the OrderManager doesn't know about — the bot's
    # in-memory commitment view diverges from reality and new orders
    # get auto-cancelled with "insufficient collateral" notifications.
    try:
        zombies = await exchange.list_resting_orders()
        if zombies:
            ids = [o.order_id for o in zombies]
            logger.info(
                "startup: sweeping %d zombie resting order(s) from prior session",
                len(ids),
            )
            results = await exchange.cancel_orders(ids)
            cancelled = sum(1 for ok in results.values() if ok)
            logger.info("startup: cancelled %d/%d zombie orders", cancelled, len(ids))
    except Exception as exc:
        logger.warning(
            "startup: zombie sweep failed (%s); proceeding anyway. "
            "If you see 'insufficient collateral' notifications, "
            "manually cancel resting orders on Kalshi and restart.",
            exc,
        )

    # 2. Parse and pre-validate seed event tickers (if any).
    # `--event-ticker` is now optional and accepts comma-separated values.
    # When omitted, the bot starts with no events; the operator adds them
    # via the dashboard.
    seed_event_tickers: list[str] = []
    if args.event_ticker:
        seed_event_tickers = [
            t.strip().upper() for t in args.event_ticker.split(",") if t.strip()
        ]

    state = ControlState()
    for ev in seed_event_tickers:
        try:
            event_resp = await client.get_event(ev, with_nested_markets=True)
        except Exception as exc:
            logger.error(
                "Could not fetch event %s: %s. Check spelling and API access; "
                "skipping this seed event.", ev, exc,
            )
            continue
        event = event_resp.get("event") or {}
        markets = _markets_from_event_response(event_resp)
        n_markets = len(markets)
        logger.info(
            "Seed event %s: %d markets, status=%s",
            ev, n_markets, event.get("status", "?"),
        )
        await state.add_event(ev)

    if not seed_event_tickers:
        logger.info(
            "No seed events. Bot will sit idle until the operator adds "
            "events via the dashboard's events strip."
        )

    # 3. Build the rest
    order_manager = OrderManager()
    theo_registry = TheoRegistry()
    # External theo providers from CLI flags (--theo-csv, --theo-json,
    # --theo-http). These override the per-prefix stub fallback below.
    cli_providers = _build_theo_providers_from_args(args)
    cli_prefixes: set[str] = set()
    for prov in cli_providers:
        theo_registry.register(prov)
        cli_prefixes.add(prov.series_prefix)
    # Register stub theo providers for each seed event's series prefix
    # ONLY if no CLI provider already covers that prefix (specifically or
    # via "*" wildcard). For events added later via the dashboard, the
    # registry's no-provider fallback (or the wildcard) handles them.
    #
    # Special-case: KXTRUEV gets a real TruEV theo provider (not a
    # stub). Settlement time is required — operator passes via
    # --truev-settlement-iso. Anchor and σ have sane defaults but can
    # be overridden via flags.
    has_wildcard = "*" in cli_prefixes
    seen_prefixes: set[str] = set()
    truev_providers: list[Any] = []
    for ev in seed_event_tickers:
        prefix = _series_prefix(ev)
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        if prefix in cli_prefixes or has_wildcard:
            continue  # CLI provider already covers this prefix
        if prefix == "KXTRUEV":
            from feeds.truflation import TruEvForwardSource
            from lipmm.theo.providers import (
                DEFAULT_ANCHOR_PLACEHOLDER,
                DEFAULT_WEIGHTS_Q4_2025,
                TruEVConfig,
                TruEVTheoProvider,
                TruEvAnchor,
            )
            if not args.truev_settlement_iso:
                logger.error(
                    "KXTRUEV detected but --truev-settlement-iso missing; "
                    "falling back to StubTheoProvider. Pass e.g. "
                    "--truev-settlement-iso 2026-05-07T23:59:00+00:00"
                )
                theo_registry.register(StubTheoProvider(prefix))
                continue
            anchor = DEFAULT_ANCHOR_PLACEHOLDER
            if (args.truev_anchor_index is not None
                    or args.truev_anchor_date is not None):
                anchor = TruEvAnchor(
                    anchor_date=args.truev_anchor_date or anchor.anchor_date,
                    anchor_index_value=(
                        args.truev_anchor_index
                        if args.truev_anchor_index is not None
                        else anchor.anchor_index_value
                    ),
                    anchor_prices=dict(anchor.anchor_prices),
                )
            cfg = TruEVConfig(
                settlement_time_iso=args.truev_settlement_iso,
                weights=DEFAULT_WEIGHTS_Q4_2025,
                anchor=anchor,
                annualized_vol=args.truev_vol,
                max_confidence=args.truev_max_confidence,
            )
            forward_src = TruEvForwardSource(poll_interval_s=120.0)
            prov = TruEVTheoProvider(cfg, forward_src)
            theo_registry.register(prov)
            truev_providers.append(prov)
            logger.info(
                "registered TruEVTheoProvider: prefix=%s settle=%s "
                "σ=%.3f anchor_date=%s anchor_idx=%.4f",
                prefix, args.truev_settlement_iso,
                args.truev_vol, anchor.anchor_date, anchor.anchor_index_value,
            )
            continue
        theo_registry.register(StubTheoProvider(prefix))
    strategy = _build_strategy(args.strategy)
    risk = _build_risk_registry(args.cap_dollars)
    decision_logger = DecisionLogger(log_dir=log_dir)
    broadcaster = Broadcaster()

    # Decision recorder: writes to JSONL AND broadcasts to dashboard tabs.
    recorder = broadcaster.as_decision_recorder(decision_logger)

    ticker_source = _MultiEventTickerSource(client, state)

    # Earnings accrual + IncentiveCache built externally so the runner
    # and the ControlServer share the same cache (single Kalshi
    # /incentive_programs poll, single accrual tally).
    from lipmm.incentives import IncentiveCache
    from lipmm.observability.earnings_history import EarningsHistory
    incentive_cache = IncentiveCache(
        KalshiIncentiveProvider(), refresh_s=3600.0,
    )
    earnings_accrual = EarningsAccrual()
    # Persistent $/hr history; survives bot restarts. One sample per
    # minute appended to a JSONL under the same directory tree as
    # decision logs so retention sweeps can reach it later.
    earnings_history = EarningsHistory(
        history_path=os.path.join(log_dir, "earnings_history.jsonl"),
    )
    # Fill-markout tracker. mid_fetch_hook closes over the exchange so
    # the tracker can sample post-fill mids on its own schedule
    # (asyncio.sleep + get_orderbook). In-memory; resets on restart.
    from lipmm.observability.markout import MarkoutTracker
    async def _markout_mid_hook(ticker: str) -> float | None:
        try:
            ob = await exchange.get_orderbook(ticker)
        except Exception:
            return None
        # best yes-bid in cents from yes-levels; best yes-ask = 100 - max(no-levels)
        if not ob.yes_levels or not ob.no_levels:
            return None
        best_bid_t1c = ob.yes_levels[0][0]
        best_no_bid_t1c = ob.no_levels[0][0]
        bb_c = best_bid_t1c // 10
        ba_c = (1000 - best_no_bid_t1c) // 10
        if 0 < bb_c < ba_c < 100:
            return (bb_c + ba_c) / 2.0
        return None
    markout_tracker = MarkoutTracker(_markout_mid_hook)

    runner = LIPRunner(
        config=RunnerConfig(
            cycle_seconds=args.cycle_seconds,
            # market_meta is static metadata — drop event_ticker since
            # the active set is now mutable. Decision-log records still
            # carry per-decision `ticker`, which is what matters.
            market_meta={"seed_events": seed_event_tickers},
        ),
        theo_registry=theo_registry,
        strategy=strategy,
        order_manager=order_manager,
        exchange=exchange,
        ticker_source=ticker_source,
        decision_recorder=recorder,
        risk_registry=risk,
        control_state=state,
        broadcaster=broadcaster,
        incentive_cache=incentive_cache,
        earnings_accrual=earnings_accrual,
        earnings_history=earnings_history,
        markout=markout_tracker,
    )

    # 4. ControlServer: dashboard + incentive cache + retention.
    async def _validator(event_ticker: str) -> dict[str, Any]:
        return await _validate_event(client, event_ticker)

    server = ControlServer(
        state,
        decision_logger=decision_logger,
        kill_handler=runner.cancel_all_resting,
        order_manager=order_manager,
        exchange=exchange,
        risk_registry=risk,
        broadcaster=broadcaster,
        mount_dashboard=True,
        event_validator=_validator,
        rate_limit_stats=lambda: client.rate_limiter.stats(),
        runtime_refresh_s=5.0,
        incentive_cache=incentive_cache,
        earnings_history=earnings_history,
        markout_tracker=markout_tracker,
    )

    retention = RetentionManager(
        target_dir=log_dir,
        max_total_bytes=args.retention_bytes,
        run_interval_s=3600.0,
    )

    # 5. Banner before any blocking startup work
    _print_banner(
        event_ticker=args.event_ticker,
        host=args.host, port=args.port,
        strategy=args.strategy,
        cap_dollars=args.cap_dollars,
        log_dir=log_dir,
    )

    # 6. SIGINT handler
    stop_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("signal received; stopping…")
        stop_event.set()
        runner.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows or restricted env
            pass

    # 7. Start everything
    await server.start(host=args.host, port=args.port)
    await retention.start()
    runner_task = asyncio.create_task(runner.run())

    try:
        # Wait for either runner to finish (unlikely without signal) or
        # stop_event to be set.
        await stop_event.wait()
    finally:
        runner.stop()
        try:
            await asyncio.wait_for(runner_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("runner did not stop in 10s; cancelling")
            runner_task.cancel()
        # Pull every resting order before exiting so the operator
        # doesn't leave naked quotes on Kalshi after a Ctrl+C.
        try:
            cancelled = await asyncio.wait_for(
                runner.cancel_all_resting(), timeout=15.0,
            )
            logger.info("shutdown: cancelled %d resting orders", cancelled)
        except asyncio.TimeoutError:
            logger.warning(
                "shutdown: cancel_all_resting timed out — "
                "orders may remain on the book; check the dashboard"
            )
        except Exception as exc:
            logger.warning("shutdown: cancel_all_resting failed: %s", exc)
        await retention.stop()
        await server.stop()
        decision_logger.close()
        await client.close()
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m deploy.lipmm_run",
        description="Run lipmm bot + dashboard against one Kalshi event.",
    )
    p.add_argument(
        "--event-ticker", required=False, default="",
        help=(
            "Optional comma-separated list of Kalshi event tickers to seed at "
            "startup, e.g. 'KXISMPMI-26MAY' or 'KXISMPMI-26MAY,KXOTHER-26JUN'. "
            "Operator can add/remove events at runtime from the dashboard's "
            "events strip. Omit entirely to start with no active events."
        ),
    )
    p.add_argument(
        "--cap-dollars", type=float, default=100.0,
        help="Per-side notional cap (default 100.0)",
    )
    p.add_argument(
        "--strategy", default="default", choices=["default", "sticky"],
        help="Quoting strategy (default 'default' = DefaultLIPQuoting)",
    )
    p.add_argument(
        "--cycle-seconds", type=float, default=3.0,
        help="Cycle interval in seconds (default 3.0)",
    )
    p.add_argument(
        "--host", default=os.environ.get("LIPMM_DASHBOARD_HOST", "0.0.0.0"),
        help="Dashboard bind host (default 0.0.0.0; reads LIPMM_DASHBOARD_HOST)",
    )
    p.add_argument(
        "--port", type=int,
        default=int(os.environ.get("LIPMM_DASHBOARD_PORT", "5050")),
        help="Dashboard port (default 5050; reads LIPMM_DASHBOARD_PORT)",
    )
    p.add_argument(
        "--decision-log-dir", default=None,
        help="Directory for JSONL decision logs "
             "(default 'logs/<event-ticker>_decisions')",
    )
    p.add_argument(
        "--retention-bytes", type=int, default=2 * 1024 * 1024 * 1024,
        help="Decision-log disk cap in bytes (default 2 GiB)",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    # ── External theo-provider integration ─────────────────────────
    # Each flag is repeatable: pass --theo-csv multiple times to
    # register multiple file watchers, etc. Spec format:
    #   --theo-csv  PATH[:SERIES_PREFIX[:REFRESH_S]]
    #   --theo-json PATH[:SERIES_PREFIX[:REFRESH_S]]
    #   --theo-http URL[:SERIES_PREFIX[:REFRESH_S]]
    # When SERIES_PREFIX is omitted, '*' (wildcard — serves all events)
    # is used. When REFRESH_S is omitted, the provider's default is.
    p.add_argument(
        "--theo-csv", action="append", default=[], metavar="SPEC",
        help=(
            "Register a FilePollTheoProvider on a CSV file. "
            "Spec: 'PATH[:SERIES_PREFIX[:REFRESH_S]]'. SERIES_PREFIX "
            "defaults to '*' (wildcard). Repeatable."
        ),
    )
    p.add_argument(
        "--theo-json", action="append", default=[], metavar="SPEC",
        help=(
            "Register a FilePollTheoProvider on a JSON file. "
            "Spec: 'PATH[:SERIES_PREFIX[:REFRESH_S]]'. Repeatable."
        ),
    )
    p.add_argument(
        "--theo-http", action="append", default=[], metavar="SPEC",
        help=(
            "Register an HttpPollTheoProvider on a JSON URL. "
            "Spec: 'URL[:SERIES_PREFIX[:REFRESH_S]]'. URL must include "
            "scheme. Repeatable."
        ),
    )
    # ── TruEV-specific flags (only consumed when an event with prefix
    # KXTRUEV is seeded). Settlement is required because the daily
    # binary lognormal pricer needs a fixed settle time. Operator
    # should set anchor_index from truflation.com/marketplace/ev-index
    # and σ from observed daily range or a recent calibration.
    p.add_argument(
        "--truev-settlement-iso", default="",
        help="REQUIRED for KXTRUEV markets. ISO 8601 datetime "
             "(e.g. '2026-05-07T23:59:00+00:00') of the binary settle.",
    )
    p.add_argument(
        "--truev-vol", type=float, default=0.30,
        help="Annualized σ for the TruEV lognormal pricer (default 0.30).",
    )
    p.add_argument(
        "--truev-anchor-index", type=float, default=None,
        help="Override the placeholder anchor index value. Read today's "
             "value from truflation.com/marketplace/ev-index.",
    )
    p.add_argument(
        "--truev-anchor-date", default=None,
        help="Informational label for the anchor date (default 2026-05-07).",
    )
    p.add_argument(
        "--truev-max-confidence", type=float, default=0.7,
        help="Cap on TruEV theo confidence (default 0.7). σ is "
             "uncalibrated in Phase 1, so we don't go beyond active-match "
             "mode by default.",
    )
    return p.parse_args(argv)


def _parse_provider_spec(
    spec: str, *, kind: str,
) -> tuple[str, str, float | None]:
    """Parse 'PATH[:PREFIX[:REFRESH_S]]' or 'URL[:PREFIX[:REFRESH_S]]'.

    URLs have to be handled carefully because of the ':' in the scheme.
    For http/https URLs, we recognize the scheme and split AFTER the
    optional port/path tail using rsplit on ':' twice.
    """
    parts = spec.split(":") if kind != "http" else None
    # HTTP: special-case parsing because URL contains ":".
    if kind == "http":
        # 'http://host:port/path:PREFIX:REFRESH'
        # Approach: try to identify the URL prefix by matching a
        # scheme. The URL ends just before the first ':' that follows
        # the path. Easiest heuristic: split from the right; if the
        # rightmost colon's left side parses as URL+something we
        # recognize as a series prefix or refresh, peel it off.
        url, prefix, refresh = spec, "*", None
        # Try peeling from the right twice.
        for _ in range(2):
            head, _, tail = url.rpartition(":")
            if not head or "://" not in head:
                break
            # `tail` is either a refresh number or a prefix; both must
            # NOT contain '/' (URLs do).
            if "/" in tail:
                break
            try:
                refresh_candidate = float(tail)
                if refresh is None:
                    refresh = refresh_candidate
                    url = head
                    continue
            except ValueError:
                pass
            # Otherwise treat as a prefix.
            if prefix == "*":
                prefix = tail
                url = head
                continue
            break
        return url, prefix, refresh
    # File specs: split on ':' (paths shouldn't contain ':' on POSIX).
    if not parts:
        raise ValueError(f"empty {kind} spec")
    path = parts[0]
    prefix = parts[1] if len(parts) >= 2 and parts[1] else "*"
    refresh: float | None = None
    if len(parts) >= 3 and parts[2]:
        refresh = float(parts[2])
    return path, prefix, refresh


def _build_theo_providers_from_args(
    args: argparse.Namespace,
) -> list[Any]:
    """Construct provider instances from CLI flags. Caller registers
    them on the TheoRegistry."""
    from lipmm.theo.providers import (
        FilePollTheoProvider,
        HttpPollTheoProvider,
    )
    out: list[Any] = []
    for spec in args.theo_csv:
        path, prefix, refresh = _parse_provider_spec(spec, kind="csv")
        kwargs: dict[str, Any] = {
            "series_prefix": prefix, "format": "csv",
        }
        if refresh is not None:
            kwargs["refresh_s"] = refresh
        out.append(FilePollTheoProvider(path, **kwargs))
        logger.info(
            "registered theo provider: csv path=%s prefix=%r refresh_s=%s",
            path, prefix, refresh,
        )
    for spec in args.theo_json:
        path, prefix, refresh = _parse_provider_spec(spec, kind="json")
        kwargs = {"series_prefix": prefix, "format": "json"}
        if refresh is not None:
            kwargs["refresh_s"] = refresh
        out.append(FilePollTheoProvider(path, **kwargs))
        logger.info(
            "registered theo provider: json path=%s prefix=%r refresh_s=%s",
            path, prefix, refresh,
        )
    for spec in args.theo_http:
        url, prefix, refresh = _parse_provider_spec(spec, kind="http")
        kwargs = {"series_prefix": prefix}
        if refresh is not None:
            kwargs["refresh_s"] = refresh
        out.append(HttpPollTheoProvider(url, **kwargs))
        logger.info(
            "registered theo provider: http url=%s prefix=%r refresh_s=%s",
            url, prefix, refresh,
        )
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    _validate_env()
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
