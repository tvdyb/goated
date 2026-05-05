"""LIPRunner — the per-cycle orchestrator.

Each cycle, for each active ticker:
  1. Pull fresh orderbook (via ExchangeClient)
  2. Compute theo (via TheoRegistry)
  3. Build inputs and ask the QuotingStrategy what to quote
  4. Apply the strategy's decision via OrderManager → exchange
  5. Optionally hand the cycle's record to a decision logger

Decoupled from market specifics:
  - `TickerSource` plugin determines which tickers to quote
  - `ExchangeClient` is whichever venue we're trading on
  - `TheoRegistry` routes per-series; new markets register new providers
  - `QuotingStrategy` is whatever LIP-farming behavior fits this market
  - `decision_recorder` callback (optional) takes a per-cycle dict for logging

Things this module deliberately doesn't do:
  - Forward / vol fetching (that's TheoProvider's responsibility)
  - Maintenance window handling (separate `MaintenanceManager`, future)
  - Risk gates (separate `RiskGate` layer, future)
  - Markout tracking (separate observability layer, future)
  - Decision logging schema (the recorder is just a callable; schema lives
    in whatever logger the user plugs in)
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from lipmm.execution import ExchangeClient, OrderManager
from lipmm.observability.schema import build_record

# Lazy import to avoid circular dependency at module-load time
# (lipmm/__init__.py exports both control + runner). Type-checked lazily.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lipmm.control.broadcaster import Broadcaster
    from lipmm.control.state import ControlState
from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
)
from lipmm.risk import RiskContext, RiskRegistry
from lipmm.theo import TheoRegistry, TheoResult

logger = logging.getLogger(__name__)


# ── Plugins ───────────────────────────────────────────────────────────


@runtime_checkable
class TickerSource(Protocol):
    """Resolves the set of tickers the bot should quote on this cycle.

    Could be: "all currently-open Kalshi events under series X" (queries
    the exchange), "list from config", "active strikes near a forward
    price," etc. Implementations decide their own caching policy.
    """
    async def list_active_tickers(
        self, exchange: ExchangeClient,
    ) -> list[str]:
        ...


# Optional callback the runner invokes once per (ticker, cycle) with a dict
# describing what happened. Decision-log adapters plug in here.
DecisionRecorder = Callable[[dict], Awaitable[None] | None]


# ── Config ────────────────────────────────────────────────────────────


@dataclass
class RunnerConfig:
    cycle_seconds: float = 3.0
    settlement_time_ts: float | None = None  # unix ts; if set, used to
    # compute time_to_settle_s passed to QuotingStrategy. None → 0.
    fail_loud_on_strike_error: bool = False  # if False, log + continue
    # Operator-provided static metadata flowed into every decision-log record's
    # `market_meta` field. Useful for tagging records with the underlying
    # asset name, settlement schedule, market category, etc. The framework
    # doesn't introspect this; consumers (analyst tools) do.
    market_meta: dict[str, str] = field(default_factory=dict)


# ── The runner ────────────────────────────────────────────────────────


class LIPRunner:
    """Orchestrates the bot's main loop.

    Dependencies injected at construction. `run()` blocks until SIGINT or
    until `stop()` is called from another task. Per-cycle exceptions on
    individual strikes are caught and logged so one bad ticker can't take
    down the whole loop (configurable via `fail_loud_on_strike_error`).
    """

    def __init__(
        self,
        *,
        config: RunnerConfig,
        theo_registry: TheoRegistry,
        strategy: QuotingStrategy,
        order_manager: OrderManager,
        exchange: ExchangeClient,
        ticker_source: TickerSource,
        decision_recorder: DecisionRecorder | None = None,
        risk_registry: RiskRegistry | None = None,
        control_state: "ControlState | None" = None,
        broadcaster: "Broadcaster | None" = None,
    ) -> None:
        self._cfg = config
        self._theo = theo_registry
        self._strategy = strategy
        self._om = order_manager
        self._exchange = exchange
        self._ticker_source = ticker_source
        self._recorder = decision_recorder
        self._risk = risk_registry
        self._control = control_state
        self._broadcaster = broadcaster

        self._running = False
        self._cycle_id = 0
        # Per-cycle aggregation of orderbooks the strategy already pulled.
        # Reset at the top of each cycle, populated by _process_ticker,
        # broadcast at the end so the dashboard's strike grid sees Yes/No
        # best prices + L2 depth in lockstep with the runner.
        self._cycle_orderbooks: list[dict[str, Any]] = []

    async def run(self) -> None:
        """Main loop. Returns on stop()."""
        self._running = True
        logger.info(
            "LIPRunner: starting (cycle=%.1fs, strategy=%s)",
            self._cfg.cycle_seconds, self._strategy.name,
        )

        # Lifecycle warmups
        await self._theo.warmup_all()
        await self._strategy.warmup()
        await self._om.reconcile(self._exchange)

        try:
            while self._running:
                cycle_start = time.monotonic()
                try:
                    await self._cycle()
                except Exception as exc:
                    logger.exception("LIPRunner: cycle exception: %s", exc)

                elapsed = time.monotonic() - cycle_start
                sleep_for = max(0.05, self._cfg.cycle_seconds - elapsed)
                await asyncio.sleep(sleep_for)
        finally:
            await self._strategy.shutdown()
            await self._theo.shutdown_all()
            logger.info("LIPRunner: stopped")

    def stop(self) -> None:
        """Request main loop to exit after current cycle."""
        self._running = False

    async def cancel_all_resting(self) -> int:
        """Cancel every resting order. Returns the count cancelled.

        Wired to the control plane's kill handler. Idempotent: safe to
        call when there are no resting orders. Best-effort: errors on
        individual cancels are logged but don't prevent other cancels.
        """
        resting = self._om.all_resting()
        order_ids = [o.order_id for o in resting.values()]
        if not order_ids:
            return 0
        try:
            results = await self._exchange.cancel_orders(order_ids)
            cancelled = sum(1 for ok in results.values() if ok)
            # OrderManager keeps an in-memory view; reconcile after bulk cancel
            # so subsequent cycles don't think we still have resting orders.
            await self._om.reconcile(self._exchange)
            return cancelled
        except Exception as exc:
            logger.warning("LIPRunner.cancel_all_resting failed: %s", exc)
            return 0

    # ── one cycle ────────────────────────────────────────────────────

    async def _cycle(self) -> None:
        self._cycle_id += 1
        # Reset per-cycle orderbook aggregation. Each _process_ticker
        # appends one entry; we broadcast the whole list at end-of-cycle.
        self._cycle_orderbooks = []

        # Control plane: top-of-cycle gate. If killed or globally paused,
        # skip the entire cycle — no theo, no orders, no decision records.
        # The kill handler (cancel-all) was invoked at /control/kill time;
        # we don't re-cancel here.
        if self._control is not None and self._control.should_skip_cycle():
            return

        try:
            tickers = await self._ticker_source.list_active_tickers(self._exchange)
        except Exception as exc:
            logger.warning("LIPRunner: ticker source failed: %s", exc)
            return

        # One log line per cycle so the operator can tell from the
        # screen output whether the runner is actually iterating.
        logger.info(
            "cycle %d: iterating %d ticker(s)", self._cycle_id, len(tickers),
        )

        for ticker in tickers:
            # Per-ticker pause check (cheap, before any I/O).
            if self._control is not None and self._control.should_skip_ticker(ticker):
                continue
            try:
                await self._process_ticker(ticker)
            except Exception as exc:
                if self._cfg.fail_loud_on_strike_error:
                    raise
                logger.exception(
                    "LIPRunner: error processing %s: %s", ticker, exc,
                )

        # End-of-cycle: broadcast the aggregated per-strike orderbooks
        # so the dashboard's strike grid stays in lockstep with the
        # runner. Best-effort; never crashes the cycle.
        if self._broadcaster is not None and self._cycle_orderbooks:
            try:
                await self._broadcaster.broadcast_orderbook({
                    "strikes": self._cycle_orderbooks,
                    "last_cycle_ts": time.time(),
                })
            except Exception as exc:
                logger.info("orderbook broadcast failed: %s", exc)

    async def _process_ticker(self, ticker: str) -> None:
        now_ts = time.time()
        time_to_settle_s = (
            max(0.0, self._cfg.settlement_time_ts - now_ts)
            if self._cfg.settlement_time_ts else 0.0
        )

        # 1. Theo. If the operator has plugged in a manual override via
        # the dashboard for this ticker, skip the registered TheoProvider
        # entirely and feed the strategy a TheoResult derived from the
        # override. Source string is "manual-override:{actor}" so analysts
        # can identify override-driven decisions in the log.
        override = (
            self._control.get_theo_override(ticker)
            if self._control is not None else None
        )
        if override is not None:
            theo = TheoResult(
                yes_probability=override.yes_probability,
                confidence=override.confidence,
                computed_at=override.set_at,
                source=f"manual-override:{override.actor}",
                extras={"override_reason": override.reason},
            )
        else:
            theo = await self._theo.theo(ticker)

        # 2. Orderbook (will be ExchangeClient's job)
        ob_levels = await self._exchange.get_orderbook(ticker)
        # Compute best_bid / best_ask excluding our own resting orders
        cur_bid = self._om.get_resting(ticker, "bid")
        cur_ask = self._om.get_resting(ticker, "ask")
        cur_bid_px = cur_bid.price_cents if cur_bid else 0
        cur_bid_size = cur_bid.size if cur_bid else 0
        cur_ask_px = cur_ask.price_cents if cur_ask else 0
        cur_ask_size = cur_ask.size if cur_ask else 0
        best_bid = _best_excluding_self(
            ob_levels.yes_levels, cur_bid_px, cur_bid_size,
        )
        # ask = 100 - best No-bid (inverted), excluding our No-side reflection
        our_no_for_ask = (100 - cur_ask_px) if cur_ask_px > 0 else 0
        best_no_bid = _best_excluding_self(
            ob_levels.no_levels, our_no_for_ask, cur_ask_size,
        )
        best_ask = (100 - best_no_bid) if best_no_bid > 0 else 100

        ob_snapshot = OrderbookSnapshot(
            yes_depth=ob_levels.yes_levels,
            no_depth=ob_levels.no_levels,
            best_bid=best_bid,
            best_ask=best_ask,
        )

        # Per-strike orderbook view for the dashboard's strike grid.
        # Top 5 levels each side keeps the broadcast small; the depth
        # ladder UI only ever shows top 5.
        self._cycle_orderbooks.append({
            "ticker": ticker,
            "best_bid_c": int(best_bid),
            "best_ask_c": int(best_ask),
            "yes_levels": [
                {"price_cents": int(p), "size": float(sz)}
                for (p, sz) in ob_levels.yes_levels[:5]
            ],
            "no_levels": [
                {"price_cents": int(p), "size": float(sz)}
                for (p, sz) in ob_levels.no_levels[:5]
            ],
            "ts": now_ts,
        })

        # 3. Strategy decision
        our_state = OurState(
            cur_bid_px=cur_bid_px,
            cur_bid_size=cur_bid_size,
            cur_bid_id=cur_bid.order_id if cur_bid else None,
            cur_ask_px=cur_ask_px,
            cur_ask_size=cur_ask_size,
            cur_ask_id=cur_ask.order_id if cur_ask else None,
        )
        # Apply control-plane runtime knob overrides if a ControlState is wired.
        control_overrides = (
            self._control.control_overrides_for_strategy()
            if self._control is not None else None
        )
        decision: QuotingDecision = await self._strategy.quote(
            ticker=ticker,
            theo=theo,
            orderbook=ob_snapshot,
            our_state=our_state,
            now_ts=now_ts,
            time_to_settle_s=time_to_settle_s,
            control_overrides=control_overrides,
        )

        # 3a. Per-side pause AND per-side lock from control plane.
        # Force skip on any paused or locked side. Applied AFTER strategy
        # decision so the strategy's reasoning is captured in the
        # decision-log record before being overridden.
        if self._control is not None:
            from lipmm.quoting.base import SideDecision as _SideDecision
            for _side_name in ("bid", "ask"):
                paused = self._control.is_side_paused(ticker, _side_name)
                locked = self._control.is_side_locked(ticker, _side_name, now_ts=now_ts)
                if not (paused or locked):
                    continue
                # Build the skip reason (lock takes priority in messaging
                # since it carries operator-provided context)
                if locked:
                    lock = self._control.get_side_lock(ticker, _side_name)
                    skip_reason = (
                        f"control plane: {_side_name} locked"
                        + (f" — {lock.reason}" if lock and lock.reason else "")
                    )
                else:
                    skip_reason = f"control plane: {_side_name} paused"
                if _side_name == "bid" and not decision.bid.skip:
                    decision = QuotingDecision(
                        bid=_SideDecision(
                            price=0, size=0, skip=True,
                            reason=skip_reason,
                            extras=decision.bid.extras,
                        ),
                        ask=decision.ask,
                        transitions=list(decision.transitions),
                    )
                elif _side_name == "ask" and not decision.ask.skip:
                    decision = QuotingDecision(
                        bid=decision.bid,
                        ask=_SideDecision(
                            price=0, size=0, skip=True,
                            reason=skip_reason,
                            extras=decision.ask.extras,
                        ),
                        transitions=list(decision.transitions),
                    )

        # 3b. Optional risk evaluation: gates can veto bid/ask sides,
        # turning them into skip=True. Audit trail goes into the decision log.
        risk_audit: list[dict] = []
        if self._risk is not None:
            # Compute aggregate views for context
            resting = self._om.all_resting()
            agg_count = len(resting)
            agg_notional = sum(
                ro.price_cents * ro.size / 100.0 for ro in resting.values()
            )
            risk_ctx = RiskContext(
                ticker=ticker,
                cycle_id=self._cycle_id,
                decision=decision,
                theo=theo,
                our_state=our_state,
                time_to_settle_s=time_to_settle_s,
                now_ts=now_ts,
                all_resting_count=agg_count,
                all_resting_notional=agg_notional,
            )
            decision, risk_audit = await self._risk.evaluate(risk_ctx)

        # 4. Apply via OrderManager
        bid_outcome = await self._om.apply(
            ticker, "bid", decision.bid, self._exchange,
        )
        ask_outcome = await self._om.apply(
            ticker, "ask", decision.ask, self._exchange,
        )

        # 5. Optional decision recording — uses canonical lipmm schema.
        if self._recorder is not None:
            record = build_record(
                cycle_id=self._cycle_id,
                ts=now_ts,
                ticker=ticker,
                theo=theo,
                orderbook=ob_snapshot,
                our_state=our_state,
                decision=decision,
                bid_outcome=bid_outcome,
                ask_outcome=ask_outcome,
                market_meta=self._cfg.market_meta,
                risk_audit=risk_audit,
            )
            try:
                result = self._recorder(record)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("LIPRunner: decision_recorder failed: %s", exc)


# ── helpers ──────────────────────────────────────────────────────────


def _best_excluding_self(
    levels: list[tuple[int, float]],
    our_price: int,
    our_size: int,
) -> int:
    """Return the best (highest) price level after excluding `our_size`
    from the level at `our_price`. Walks levels in order; returns 0 if
    nothing remains."""
    for px, sz in levels:
        if px == our_price and our_size > 0:
            if sz - our_size > 0.5:
                return px
            continue  # we are this entire level; look deeper
        return px
    return 0
