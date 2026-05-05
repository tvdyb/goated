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
from lipmm.incentives import KalshiIncentiveProvider
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
        MaxOrdersPerCycleGate(max_orders=20),
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
    # Register stub theo providers for each seed event's series prefix so
    # the registry has explicit entries (cosmetic — the registry's
    # no-provider fallback also returns confidence=0). For events added
    # later via the dashboard, the fallback handles them transparently.
    seen_prefixes: set[str] = set()
    for ev in seed_event_tickers:
        prefix = _series_prefix(ev)
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        theo_registry.register(StubTheoProvider(prefix))
    strategy = _build_strategy(args.strategy)
    risk = _build_risk_registry(args.cap_dollars)
    decision_logger = DecisionLogger(log_dir=log_dir)
    broadcaster = Broadcaster()

    # Decision recorder: writes to JSONL AND broadcasts to dashboard tabs.
    recorder = broadcaster.as_decision_recorder(decision_logger)

    ticker_source = _MultiEventTickerSource(client, state)
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
        runtime_refresh_s=5.0,
        incentive_provider=KalshiIncentiveProvider(),
        incentives_refresh_s=3600.0,
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
    return p.parse_args(argv)


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
