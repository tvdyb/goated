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
        incentive_cache: "Any | None" = None,
        earnings_accrual: "Any | None" = None,
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
        self._incentive_cache = incentive_cache
        self._earnings_accrual = earnings_accrual

        self._running = False
        self._cycle_id = 0
        # Per-cycle aggregation of orderbooks the strategy already pulled.
        # Reset at the top of each cycle, populated by _process_ticker,
        # broadcast at the end so the dashboard's strike grid sees Yes/No
        # best prices + L2 depth in lockstep with the runner.
        self._cycle_orderbooks: list[dict[str, Any]] = []
        # Position cache: ticker → Yes contract qty (positive = long).
        # Refreshed once per cycle from exchange.list_positions(). Used
        # by MaxPositionPerSideGate to veto sides that would deepen an
        # already-lopsided position.
        self._position_cache: dict[str, int] = {}

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

        # Refresh balance once per cycle so OrderManager can skip
        # placements that would push past available cash. Kalshi
        # auto-cancels collateral-short orders and the operator gets
        # push-notification spam; the skip turns those into a quiet
        # no-op. Failures don't block the cycle — when balance is
        # unknown, OrderManager falls back to legacy (no check).
        try:
            balance = await self._exchange.get_balance()
            self._om.set_available_cash_cents(balance.cash_dollars * 100.0)
        except Exception as exc:
            logger.info("balance refresh failed: %s", exc)
            self._om.set_available_cash_cents(None)

        # Refresh position cache once per cycle. One API call regardless
        # of strike count. Failures here don't block the cycle — gates
        # that read positions just see {} and won't veto.
        try:
            positions = await self._exchange.list_positions()
            self._position_cache = {p.ticker: int(p.quantity) for p in positions}
        except Exception as exc:
            logger.info("position cache refresh failed: %s", exc)

        # Round-robin: rotate the iteration starting point each cycle
        # so a per-cycle gate (MaxOrdersPerCycleGate) doesn't always
        # veto the same trailing strikes. With N tickers and a cap of
        # M orders, every strike gets a turn within N/M cycles.
        if tickers:
            offset = self._cycle_id % len(tickers)
            tickers = tickers[offset:] + tickers[:offset]

        # One log line per cycle so the operator can tell from the
        # screen output whether the runner is actually iterating.
        logger.info(
            "cycle %d: iterating %d ticker(s)", self._cycle_id, len(tickers),
        )

        for ticker in tickers:
            # Re-check kill / global-pause on EVERY ticker iteration.
            # If kill fires mid-cycle (e.g., 100-strike cycle, kill at
            # strike #50), the remaining 50 strikes must NOT be
            # processed — otherwise we'd place orders that the
            # background cancel sweep then has to clean up. This
            # check is just a state read (microseconds) so the cost
            # of running it 100x per cycle is negligible.
            if self._control is not None and self._control.should_skip_cycle():
                logger.info(
                    "cycle %d: kill/pause fired mid-cycle, halting remaining %d ticker(s)",
                    self._cycle_id,
                    len(tickers) - tickers.index(ticker),
                )
                break
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

        # End-of-cycle: accrue LIP earnings (running tally), then
        # broadcast per-strike orderbooks. Best-effort; never crashes
        # the cycle.
        if self._earnings_accrual is not None and self._incentive_cache is not None:
            try:
                self._accrue_earnings()
            except Exception as exc:
                logger.info("earnings accrual failed: %s", exc)

        if self._broadcaster is not None and self._cycle_orderbooks:
            try:
                payload = {
                    "strikes": self._cycle_orderbooks,
                    "last_cycle_ts": time.time(),
                }
                if self._earnings_accrual is not None:
                    payload["accrual"] = self._earnings_accrual.snapshot()
                await self._broadcaster.broadcast_orderbook(payload)
            except Exception as exc:
                logger.info("orderbook broadcast failed: %s", exc)

    def _accrue_earnings(self) -> None:
        """End-of-cycle helper: for each strike with a live LIP program
        and an orderbook, compute pool_share and accrue. Idempotent
        (track() ignores zero/negative inputs)."""
        from lipmm.incentives import compute_strike_score
        cycle_dt = float(self._cfg.cycle_seconds)
        # Snapshot incentive programs by ticker for fast lookup.
        try:
            programs = self._incentive_cache.snapshot()
        except Exception:
            return
        progs_by_ticker: dict[str, Any] = {}
        for p in programs:
            progs_by_ticker.setdefault(p.market_ticker, p)
        for entry in self._cycle_orderbooks:
            ticker = entry.get("ticker")
            if not ticker:
                continue
            prog = progs_by_ticker.get(ticker)
            if prog is None:
                continue
            df_bps = getattr(prog, "discount_factor_bps", None)
            target = getattr(prog, "target_size_contracts", None)
            if df_bps is None or target is None:
                continue
            df = df_bps / 10000.0
            period_duration_s = max(
                0.0,
                float(getattr(prog, "end_date_ts", 0) or 0)
                - float(getattr(prog, "start_date_ts", 0) or 0),
            )
            if period_duration_s <= 0:
                continue
            # Resting orders for this strike: read from OrderManager.
            our_orders = []
            for side in ("bid", "ask"):
                ro = self._om.get_resting(ticker, side)
                if ro is not None:
                    our_orders.append({
                        "order_id": ro.order_id,
                        "side": side,
                        "price_cents": ro.price_cents,
                        "size": ro.size,
                    })
            try:
                score = compute_strike_score(
                    our_orders=our_orders,
                    yes_levels=entry.get("yes_levels", []),
                    no_levels=entry.get("no_levels", []),
                    best_bid_c=int(entry.get("best_bid_c", 0)),
                    best_ask_c=int(entry.get("best_ask_c", 100)),
                    discount_factor=df,
                    target_size_contracts=float(target),
                )
            except Exception:
                continue
            self._earnings_accrual.track(
                ticker, score.pool_share,
                float(prog.period_reward_dollars),
                period_duration_s,
                cycle_dt,
            )

    async def _process_ticker(self, ticker: str) -> None:
        now_ts = time.time()
        time_to_settle_s = (
            max(0.0, self._cfg.settlement_time_ts - now_ts)
            if self._cfg.settlement_time_ts else 0.0
        )

        # 1. Orderbook (must come before theo because market-following
        # overrides need best_bid/best_ask to compute the mid).
        ob_levels = await self._exchange.get_orderbook(ticker)

        # Sub-cent tick detection: Kalshi's place_order API is
        # integer-cents-only. Some markets show fractional-cent levels
        # in the orderbook (e.g., 97.8¢). The bot rounds those to the
        # nearest integer cent and quotes anyway — we'd rather quote
        # slightly suboptimally than not at all. The badge on the
        # dashboard tells the operator which markets are affected so
        # they can choose to pause manually if the adverse selection
        # is unacceptable.
        if ob_levels.has_subcent_ticks:
            logger.info(
                "subcent_market: %s has sub-cent tick granularity in book; "
                "quoting at rounded integer cents", ticker,
            )

        # Compute best_bid / best_ask excluding our own resting orders
        cur_bid = self._om.get_resting(ticker, "bid")
        cur_ask = self._om.get_resting(ticker, "ask")
        # OrderManager.RestingOrder stores cents only (Phase-2 adds t1c
        # to RestingOrder if we need exact subcent self-exclusion). For
        # now, t1c ≈ price_cents × 10 — coarse but lets the rest of the
        # pipeline use t1c uniformly.
        cur_bid_px_t1c = (cur_bid.price_cents * 10) if cur_bid else 0
        cur_bid_size = cur_bid.size if cur_bid else 0
        cur_ask_px_t1c = (cur_ask.price_cents * 10) if cur_ask else 0
        cur_ask_size = cur_ask.size if cur_ask else 0
        # _best_excluding_self works in t1c units now (orderbook levels are t1c).
        best_bid_t1c = _best_excluding_self(
            ob_levels.yes_levels, cur_bid_px_t1c, cur_bid_size,
        )
        # ask = 1000 - best No-bid (inverted), excluding our No-side reflection
        our_no_for_ask_t1c = (1000 - cur_ask_px_t1c) if cur_ask_px_t1c > 0 else 0
        best_no_bid_t1c = _best_excluding_self(
            ob_levels.no_levels, our_no_for_ask_t1c, cur_ask_size,
        )
        best_ask_t1c = (1000 - best_no_bid_t1c) if best_no_bid_t1c > 0 else 1000
        # Cents-rounded for legacy callers / display
        best_bid = (best_bid_t1c + 5) // 10  # nearest cent
        best_ask = (best_ask_t1c + 5) // 10

        ob_snapshot = OrderbookSnapshot(
            yes_depth=ob_levels.yes_levels,
            no_depth=ob_levels.no_levels,
            best_bid=best_bid,
            best_ask=best_ask,
            best_bid_t1c=best_bid_t1c,
            best_ask_t1c=best_ask_t1c,
            tick_schedule=list(ob_levels.tick_schedule),
        )

        # 2. Theo. If the operator has plugged in a manual override via
        # the dashboard for this ticker, skip the registered TheoProvider
        # entirely and feed the strategy a TheoResult derived from the
        # override. Source string is "manual-override:{actor}" or
        # "manual-override-mid:{actor}" so analysts can identify
        # override-driven decisions in the log.
        override = (
            self._control.get_theo_override(ticker)
            if self._control is not None else None
        )
        if override is not None and override.mode == "track_mid":
            # Market-following: theo = orderbook mid each cycle.
            # Degenerate book (one-sided or crossed) → confidence=0
            # so the strategy skips both sides safely.
            if best_bid_t1c > 0 and best_ask_t1c < 1000 and best_bid_t1c < best_ask_t1c:
                # Mid in t1c precision so sub-cent mids carry through.
                mid_t1c = (best_bid_t1c + best_ask_t1c) / 2.0
                mid_cents = mid_t1c / 10.0
                theo = TheoResult(
                    yes_probability=mid_t1c / 1000.0,
                    confidence=override.confidence,
                    computed_at=now_ts,
                    source=f"manual-override-mid:{override.actor}",
                    extras={
                        "override_reason": override.reason,
                        "mid_cents": mid_cents,
                        "mid_t1c": mid_t1c,
                        "best_bid_c": best_bid, "best_ask_c": best_ask,
                        "best_bid_t1c": best_bid_t1c, "best_ask_t1c": best_ask_t1c,
                    },
                )
            else:
                theo = TheoResult(
                    yes_probability=0.5,
                    confidence=0.0,
                    computed_at=now_ts,
                    source=f"manual-override-mid:{override.actor}",
                    extras={
                        "override_reason": override.reason,
                        "skip_reason": "degenerate book — track-mid disabled",
                        "best_bid_c": best_bid, "best_ask_c": best_ask,
                    },
                )
        elif override is not None:
            theo = TheoResult(
                yes_probability=override.yes_probability,
                confidence=override.confidence,
                computed_at=override.set_at,
                source=f"manual-override:{override.actor}",
                extras={"override_reason": override.reason},
            )
        else:
            theo = await self._theo.theo(ticker)

        # Per-strike orderbook view for the dashboard's strike grid.
        # We push the FULL visible book (capped defensively at 50 levels
        # each side) because the LIP scorer needs to walk down to the
        # qualifying threshold (Target Size can be up to 20,000 contracts
        # per Appendix A — far past top-5 in any realistic book). The
        # depth-ladder UI slices to top 5 at render time.
        self._cycle_orderbooks.append({
            "ticker": ticker,
            "best_bid_c": int(best_bid),
            "best_ask_c": int(best_ask),
            "yes_levels": [
                {"price_cents": int(p) // 10, "price_t1c": int(p), "size": float(sz)}
                for (p, sz) in ob_levels.yes_levels[:50]
            ],
            "no_levels": [
                {"price_cents": int(p) // 10, "price_t1c": int(p), "size": float(sz)}
                for (p, sz) in ob_levels.no_levels[:50]
            ],
            "ts": now_ts,
        })

        # 3. Strategy decision
        cur_bid_px = (cur_bid_px_t1c + 5) // 10 if cur_bid_px_t1c else 0
        cur_ask_px = (cur_ask_px_t1c + 5) // 10 if cur_ask_px_t1c else 0
        our_state = OurState(
            cur_bid_px=cur_bid_px,
            cur_bid_size=cur_bid_size,
            cur_bid_id=cur_bid.order_id if cur_bid else None,
            cur_ask_px=cur_ask_px,
            cur_ask_size=cur_ask_size,
            cur_ask_id=cur_ask.order_id if cur_ask else None,
            cur_bid_px_t1c=cur_bid_px_t1c,
            cur_ask_px_t1c=cur_ask_px_t1c,
        )
        # Apply control-plane runtime knob overrides if a ControlState
        # is wired. Per-strike > per-event > global precedence: strikes
        # under an event get the merged dict from
        # `effective_knobs_for(ticker)` so operator-pinned values for
        # one strike don't leak to its siblings.
        control_overrides = (
            self._control.control_overrides_for_strategy(ticker=ticker)
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
        # Distinct semantics:
        #   pause → force skip → OrderManager cancels existing order.
        #     "Stop quoting this side; if there's a resting order, pull it."
        #   lock  → bypass OrderManager entirely → existing order stays.
        #     "Hands off this side; whatever's resting stays resting,
        #      and the strategy can't place new orders on it either."
        # Applied AFTER the strategy decision so the strategy's reasoning
        # is still captured in the decision-log record before override.
        # `bypass_apply` collects sides where OM.apply must NOT be called
        # (the locked-side case); read by step 4 below.
        bypass_apply: set[str] = set()
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
                        f"control plane: {_side_name} locked (no OM apply)"
                        + (f" — {lock.reason}" if lock and lock.reason else "")
                    )
                    bypass_apply.add(_side_name)
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
                control_overrides=(
                    self._control.effective_knobs_for(ticker)
                    if self._control is not None else None
                ),
                position_quantity=self._position_cache.get(ticker, 0),
            )
            decision, risk_audit = await self._risk.evaluate(risk_ctx)

        # 4. Apply via OrderManager — but bypass for sides that are
        # locked. The lock semantics ("hands off") require leaving the
        # existing OM state untouched: don't cancel, don't place. The
        # OM's skip-path WOULD cancel any resting order, so we have to
        # short-circuit here. Manual orders survive next cycle this way.
        from lipmm.execution.order_manager import SideExecution as _SideExec
        if "bid" in bypass_apply:
            bid_outcome = _SideExec(
                action="skipped",
                reason="locked side — OrderManager bypassed",
            )
        else:
            bid_outcome = await self._om.apply(
                ticker, "bid", decision.bid, self._exchange,
            )
        if "ask" in bypass_apply:
            ask_outcome = _SideExec(
                action="skipped",
                reason="locked side — OrderManager bypassed",
            )
        else:
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
