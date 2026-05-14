"""FastAPI app + ControlServer wrapper.

`build_app(state, decision_logger=None, kill_handler=None)` constructs a
FastAPI app bound to the given ControlState instance. The kill_handler
callback (provided by LIPRunner) is invoked when /control/kill fires; it
should cancel all resting orders. `decision_logger` is the DecisionLogger
the runner is using — operator-command audits are written to it.

`ControlServer` wraps the app + uvicorn lifecycle so callers can:

    server = ControlServer(state, decision_logger=logger,
                           kill_handler=runner.do_kill)
    await server.start(host="0.0.0.0", port=8080)   # background task
    ...
    await server.stop()

Every protected endpoint requires a valid JWT in the Authorization
header. Auth dependency raises 401 on missing/invalid/expired tokens.

Endpoints in v1 (Phase 1):
  POST /control/auth          — exchange shared secret for JWT (unprotected)
  GET  /control/state         — full ControlState snapshot
  GET  /control/health        — liveness probe (also unprotected)
  POST /control/pause         — apply a pause (scope: global/ticker/side)
  POST /control/resume        — clear a pause
  POST /control/kill          — trip the kill switch + cancel-all
  POST /control/arm           — KILLED → ARMED (operator acknowledges)
  POST /control/set_knob      — runtime knob override
  POST /control/clear_knob    — clear an override
  POST /control/swap_strategy — placeholder (deferred to Phase 2)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from lipmm.control.audit import emit_audit
from lipmm.control.auth import (
    DEFAULT_TOKEN_TTL_S,
    constant_time_secret_compare,
    get_secret,
    issue_token,
    require_auth,
    verify_token,
)
from lipmm.control.broadcaster import Broadcaster
from lipmm.control.commands import (
    AddEventRequest,
    AddEventResponse,
    EventKnobClearRequest,
    EventKnobUpdateRequest,
    StrikeKnobClearRequest,
    StrikeKnobUpdateRequest,
    ArmRequest,
    AuthRequest,
    AuthResponse,
    CancelOrderRequest,
    CancelOrderResponse,
    ClearTheoOverrideRequest,
    CommandResponse,
    ExploitMarketEntry,
    ExploitStartRequest,
    ExploitStateResponse,
    ExploitTickerRequest,
    HealthResponse,
    IncentiveProgramEntry,
    IncentiveSnapshotResponse,
    KillRequest,
    KnobClearRequest,
    KnobUpdateRequest,
    LockEntry,
    LockSideRequest,
    LocksResponse,
    ManualOrderRequest,
    ManualOrderResponse,
    OrderbookSnapshotResponse,
    PauseRequest,
    RemoveEventRequest,
    RemoveEventResponse,
    ResumeRequest,
    RuntimeSnapshotResponse,
    SetTheoOverrideRequest,
    StateResponse,
    SwapStrategyRequest,
    UnlockSideRequest,
)
from lipmm.incentives import IncentiveCache
from lipmm.control.manual_orders import submit_manual_order
from lipmm.control.state import ControlState, KillState, PauseScope
from lipmm.execution import ExchangeClient, OrderManager
from lipmm.observability import DecisionLogger
from lipmm.risk import RiskRegistry

logger = logging.getLogger(__name__)


# Type alias for the kill handler callback. Signature: returns the count
# of orders cancelled (for audit).
KillHandler = Callable[[], Awaitable[int]]


def build_app(
    state: ControlState,
    *,
    decision_logger: DecisionLogger | None = None,
    kill_handler: KillHandler | None = None,
    secret: str | None = None,
    order_manager: OrderManager | None = None,
    exchange: ExchangeClient | None = None,
    risk_registry: RiskRegistry | None = None,
    broadcaster: Broadcaster | None = None,
    mount_dashboard: bool = False,
    incentive_cache: IncentiveCache | None = None,
    event_validator: Any = None,
    rate_limit_stats: Any = None,
    exploit_state: Any = None,
    exploit_kill_handler: Any = None,
    earnings_history: Any = None,
    markout_tracker: Any = None,
    notebook_registry: "Any | None" = None,
) -> FastAPI:
    """Construct the FastAPI app. Caller wires in the ControlState and
    optional collaborators:
      - decision_logger: for audit emission of every command
      - kill_handler: invoked by /control/kill (cancel-all)
      - secret: overrides env-var lookup (useful for tests)
      - order_manager + exchange: required for manual-order endpoints
        (Phase 2). If either is None, /control/manual_order returns 503.
      - risk_registry: optional; if present, manual orders flow through
        the same gates as strategy decisions
      - mount_dashboard: if True, attaches the Phase 4 htmx + Jinja
        dashboard at /, /login, /dashboard, /static, and the WS
        /control/stream/html endpoint. Requires a broadcaster.
    """
    app = FastAPI(
        title="lipmm Control Plane",
        description="HTTP control surface for runtime bot management.",
        version="0.2.0",
    )
    # Stash collaborators on app.state so route handlers can find them
    # without importing module-level globals.
    app.state.control_state = state
    app.state.decision_logger = decision_logger
    app.state.kill_handler = kill_handler
    app.state.control_secret = secret  # None → require_auth reads env
    app.state.order_manager = order_manager
    app.state.exchange = exchange
    app.state.risk_registry = risk_registry
    app.state.broadcaster = broadcaster
    app.state.incentive_cache = incentive_cache
    # Optional async callable: `event_validator(event_ticker)` →
    # awaits, returns a dict {"market_count": int, "status": str}.
    # Used by /control/add_event to confirm the ticker exists on the
    # exchange before adding to active_events. Raises on failure.
    app.state.event_validator = event_validator
    # Optional callable returning a dict of rate-limit stats (read/write
    # tokens available, total 429s, total throttle waits). When wired,
    # surfaces in the GET /control/runtime payload + dashboard.
    app.state.rate_limit_stats = rate_limit_stats
    # Optional exploit-mode integration (separate runner). When wired,
    # /control/exploit/* endpoints become functional; otherwise they
    # 503. exploit_kill_handler is awaited on /kill or /kill_all so the
    # runner can cancel its resting orders synchronously.
    app.state.exploit_state = exploit_state
    app.state.exploit_kill_handler = exploit_kill_handler
    # Optional persistent earnings-history tracker. When wired,
    # /control/earnings_history returns the $/hr histogram for the
    # dashboard's earnings tab. None → endpoint returns an empty
    # fragment.
    app.state.earnings_history = earnings_history
    # Optional fill-markout tracker for the dashboard's markout tab.
    # When None, /control/markout returns an empty placeholder.
    app.state.markout_tracker = markout_tracker
    # Optional theo-notebooks registry. Each registered notebook
    # contributes a modular widget to the dashboard's Notebooks tab.
    # When None, the tab shows an empty placeholder.
    app.state.notebook_registry = notebook_registry
    if broadcaster is not None:
        broadcaster.attach_state(state)

    def _check_if_version(req_if_version: int | None) -> None:
        """Optimistic concurrency: if the client sent if_version, the
        server's current version must match. Mismatch → 409 with the
        current snapshot so the client can re-render and retry."""
        if req_if_version is None:
            return
        if state.version != req_if_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "version_mismatch",
                    "client_if_version": req_if_version,
                    "server_version": state.version,
                    "snapshot": state.snapshot(),
                },
            )

    async def _broadcast_change(
        command_type: str,
        request_id: str | None = None,
        actor: str | None = None,
    ) -> None:
        """Push the new state snapshot to all WS subscribers. No-op if no
        broadcaster is wired."""
        if broadcaster is None:
            return
        try:
            await broadcaster.broadcast_state_change(
                command_type, state.snapshot(),
                request_id=request_id, actor=actor,
            )
        except Exception as exc:
            logger.warning("state_change broadcast failed: %s", exc)

    # ── Unprotected endpoints ──────────────────────────────────────

    @app.get("/control/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, state_version=state.version)

    @app.post("/control/auth", response_model=AuthResponse)
    async def auth(req: AuthRequest) -> AuthResponse:
        from lipmm.control.auth import get_secret
        expected = secret if secret is not None else get_secret()
        if not constant_time_secret_compare(req.secret, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid secret",
            )
        token = issue_token(secret=expected, actor=req.actor)
        return AuthResponse(
            token=token,
            expires_in_seconds=DEFAULT_TOKEN_TTL_S,
            actor=req.actor,
        )

    # ── Protected endpoints ────────────────────────────────────────

    @app.get("/control/state", response_model=StateResponse)
    async def get_state(actor: str = Depends(require_auth)) -> StateResponse:
        snap = state.snapshot()
        return StateResponse(**snap)

    @app.post("/control/pause", response_model=CommandResponse)
    async def post_pause(
        req: PauseRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        new_version: int
        try:
            if req.scope == PauseScope.GLOBAL:
                new_version = await state.pause_global()
            elif req.scope == PauseScope.TICKER:
                new_version = await state.pause_ticker(req.ticker)
            elif req.scope == PauseScope.SIDE:
                new_version = await state.pause_side(req.ticker, req.side)
            else:
                raise HTTPException(400, f"unknown scope: {req.scope}")
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="pause", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="pause", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("pause", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/resume", response_model=CommandResponse)
    async def post_resume(
        req: ResumeRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        # Reject resume_global if killed: operator must arm first.
        if req.scope == PauseScope.GLOBAL and state.is_killed():
            err = "cannot resume from killed state; call /control/arm first"
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="resume", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=err,
            )
            raise HTTPException(409, err)
        try:
            if req.scope == PauseScope.GLOBAL:
                if state.is_armed():
                    new_version = await state.resume_after_kill()
                else:
                    new_version = await state.resume_global()
            elif req.scope == PauseScope.TICKER:
                new_version = await state.resume_ticker(req.ticker)
            elif req.scope == PauseScope.SIDE:
                new_version = await state.resume_side(req.ticker, req.side)
            else:
                raise HTTPException(400, f"unknown scope: {req.scope}")
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="resume", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="resume", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("resume", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/kill", response_model=CommandResponse)
    async def post_kill(
        req: KillRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        """Engage the kill switch.

        Latency-critical: responds **immediately** after the state
        mutation (sub-50ms typically) so the dashboard reflects "killed"
        instantly. Order cancellation runs in the BACKGROUND because
        cancelling N orders against Kalshi can take seconds (per-order
        REST calls under rate limits). The runner sees is_killed=True
        within microseconds of the state mutation, so it stops placing
        new orders even before cancellation finishes.

        Background task emits a follow-up audit + broadcast when the
        cancel sweep completes (or fails), so the operator sees the
        final orders_cancelled count without polling.
        """
        _check_if_version(req.if_version)
        version_before = state.version
        new_version = await state.kill()
        # Broadcast the state change FIRST so connected dashboards
        # render "killed" immediately. Other tabs converge in <1s.
        await _broadcast_change("kill", request_id=req.request_id, actor=actor)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="kill", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
            side_effect_summary={"cancellation": "in_progress"},
        )

        # Fire-and-forget the cancel sweep. Don't await it.
        handler = request.app.state.kill_handler
        if handler is not None:
            async def _cancel_sweep() -> None:
                try:
                    cancelled = await handler()
                except Exception as exc:
                    logger.exception("kill cancel sweep failed: %s", exc)
                    emit_audit(
                        request.app.state.decision_logger,
                        request_id=req.request_id + ":cancel-sweep",
                        actor=actor,
                        command_type="kill_cancel_sweep",
                        command_payload={},
                        state_version_before=new_version,
                        state_version_after=state.version,
                        succeeded=False,
                        error=f"cancel_all_resting raised: {exc!r}",
                    )
                    return
                logger.info("kill cancel sweep finished: %d orders cancelled", cancelled)
                emit_audit(
                    request.app.state.decision_logger,
                    request_id=req.request_id + ":cancel-sweep",
                    actor=actor,
                    command_type="kill_cancel_sweep",
                    command_payload={},
                    state_version_before=new_version,
                    state_version_after=state.version,
                    succeeded=True,
                    side_effect_summary={"orders_cancelled": cancelled},
                )
                # Push a fresh runtime snapshot so the dashboard sees
                # the resting-orders panel empty out without waiting
                # for the next 5s tick.
                broadcaster = request.app.state.broadcaster
                collect = request.app.state.collect_runtime
                if broadcaster is not None and callable(collect):
                    try:
                        snap = await collect()
                        await broadcaster.broadcast_runtime(snap)
                    except Exception as exc:
                        logger.info(
                            "post-kill runtime broadcast failed: %s", exc,
                        )

            asyncio.create_task(_cancel_sweep())

        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/arm", response_model=CommandResponse)
    async def post_arm(
        req: ArmRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.arm()
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="arm", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(409, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="arm", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("arm", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/set_knob", response_model=CommandResponse)
    async def post_set_knob(
        req: KnobUpdateRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.set_knob(req.name, req.value)
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="set_knob", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="set_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("set_knob", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/clear_knob", response_model=CommandResponse)
    async def post_clear_knob(
        req: KnobClearRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        new_version = await state.clear_knob(req.name)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="clear_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("clear_knob", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    # ── Per-scope knob overrides (event / strike) ─────────────────

    @app.post("/control/set_event_knob", response_model=CommandResponse)
    async def post_set_event_knob(
        req: EventKnobUpdateRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.set_event_knob(
                req.event_ticker, req.name, req.value,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="set_event_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "set_event_knob", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/clear_event_knob", response_model=CommandResponse)
    async def post_clear_event_knob(
        req: EventKnobClearRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        new_version = await state.clear_event_knob(req.event_ticker, req.name)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="clear_event_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "clear_event_knob", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/set_strike_knob", response_model=CommandResponse)
    async def post_set_strike_knob(
        req: StrikeKnobUpdateRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.set_strike_knob(
                req.ticker, req.name, req.value, side=req.side,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="set_strike_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "set_strike_knob", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/clear_strike_knob", response_model=CommandResponse)
    async def post_clear_strike_knob(
        req: StrikeKnobClearRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        new_version = await state.clear_strike_knob(
            req.ticker, req.name, side=req.side,
        )
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="clear_strike_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "clear_strike_knob", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    # ── Phase 2: manual orders + side locks ────────────────────────

    @app.post("/control/manual_order", response_model=ManualOrderResponse)
    async def post_manual_order(
        req: ManualOrderRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> ManualOrderResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        om = request.app.state.order_manager
        ex = request.app.state.exchange
        if om is None or ex is None:
            err = "manual orders require an OrderManager + ExchangeClient wired into ControlServer"
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="manual_order",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=err,
            )
            raise HTTPException(503, err)
        # Honor kill switch: refuse manual orders when killed.
        if state.is_killed():
            err = "manual orders refused: bot is in KILLED state; arm + resume first"
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="manual_order",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=err,
            )
            raise HTTPException(409, err)
        try:
            outcome = await submit_manual_order(
                state=state, order_manager=om, exchange=ex,
                risk_registry=request.app.state.risk_registry,
                ticker=req.ticker, side=req.side, count=req.count,
                limit_price_cents=req.limit_price_cents,
                lock_after=req.lock_after,
                lock_auto_unlock_seconds=req.lock_auto_unlock_seconds,
                reason=req.reason,
            )
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="manual_order",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        # Audit the outcome whether it succeeded, was risk-vetoed, or rejected.
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="manual_order",
            command_payload=req.model_dump(),
            state_version_before=version_before,
            state_version_after=state.version,
            succeeded=outcome.succeeded,
            error=(None if outcome.succeeded
                   else outcome.execution.reason),
            side_effect_summary={
                "action": outcome.execution.action,
                "order_id": outcome.execution.order_id,
                "price_cents": outcome.execution.price_cents,
                "size": outcome.execution.size,
                "latency_ms": outcome.execution.latency_ms,
                "risk_vetoed": outcome.risk_vetoed,
                "lock_applied": outcome.lock_applied,
                "lock_auto_unlock_at": outcome.lock_auto_unlock_at,
                "risk_audit": outcome.risk_audit,
            },
        )
        # Broadcast: even risk-vetoed orders may have changed state
        # (e.g. version bumped if lock was set). Always broadcast so all
        # tabs stay in sync.
        await _broadcast_change(
            "manual_order", request_id=req.request_id, actor=actor,
        )
        return ManualOrderResponse(
            succeeded=outcome.succeeded,
            risk_vetoed=outcome.risk_vetoed,
            action=outcome.execution.action,
            reason=outcome.execution.reason,
            order_id=outcome.execution.order_id,
            price_cents=outcome.execution.price_cents,
            size=outcome.execution.size,
            latency_ms=outcome.execution.latency_ms,
            risk_audit=outcome.risk_audit,
            lock_applied=outcome.lock_applied,
            lock_auto_unlock_at=outcome.lock_auto_unlock_at,
            new_version=state.version,
            request_id=req.request_id,
            actor=actor,
        )

    @app.post("/control/lock_side", response_model=CommandResponse)
    async def post_lock_side(
        req: LockSideRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        import time as _t
        version_before = state.version
        auto_unlock_at = (
            _t.time() + req.auto_unlock_seconds
            if req.auto_unlock_seconds else None
        )
        try:
            new_version = await state.lock_side(
                req.ticker, req.side,
                reason=req.reason, auto_unlock_at=auto_unlock_at,
            )
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="lock_side",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="lock_side",
            command_payload=req.model_dump(),
            state_version_before=version_before,
            state_version_after=new_version,
            succeeded=True,
            side_effect_summary={"auto_unlock_at": auto_unlock_at},
        )
        await _broadcast_change("lock_side", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/unlock_side", response_model=CommandResponse)
    async def post_unlock_side(
        req: UnlockSideRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.unlock_side(req.ticker, req.side)
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="unlock_side",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="unlock_side",
            command_payload=req.model_dump(),
            state_version_before=version_before,
            state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change("unlock_side", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    # ── Multi-event: add / remove events at runtime ────────────────

    @app.post("/control/add_event", response_model=AddEventResponse)
    async def post_add_event(
        req: AddEventRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> AddEventResponse:
        _check_if_version(req.if_version)
        validator = request.app.state.event_validator
        market_count = 0
        # Validate via the operator-supplied async callable. If no
        # validator is wired (tests), skip validation and trust the
        # operator. Production deploys always pass one.
        if validator is not None:
            try:
                info = await validator(req.event_ticker)
            except Exception as exc:
                emit_audit(
                    request.app.state.decision_logger,
                    request_id=req.request_id, actor=actor,
                    command_type="add_event",
                    command_payload=req.model_dump(),
                    state_version_before=state.version,
                    state_version_after=state.version,
                    succeeded=False,
                    error=f"event_validator raised: {exc!r}",
                )
                raise HTTPException(
                    400, f"event {req.event_ticker!r} not found or unreachable: {exc}",
                ) from exc
            market_count = int(info.get("market_count", 0))
            if market_count == 0:
                emit_audit(
                    request.app.state.decision_logger,
                    request_id=req.request_id, actor=actor,
                    command_type="add_event",
                    command_payload=req.model_dump(),
                    state_version_before=state.version,
                    state_version_after=state.version,
                    succeeded=False,
                    error="event has 0 tradable markets",
                )
                raise HTTPException(
                    400,
                    f"event {req.event_ticker!r} exists but has 0 tradable markets",
                )

        version_before = state.version
        try:
            new_version = await state.add_event(req.event_ticker)
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="add_event",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc

        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="add_event",
            command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
            side_effect_summary={"market_count": market_count},
        )
        await _broadcast_change("add_event", request_id=req.request_id, actor=actor)
        return AddEventResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
            event_ticker=req.event_ticker.strip().upper(),
            market_count=market_count,
        )

    @app.post("/control/remove_event", response_model=RemoveEventResponse)
    async def post_remove_event(
        req: RemoveEventRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> RemoveEventResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        normalized = req.event_ticker.strip().upper()

        # Optionally cancel any resting orders on this event's tickers
        # BEFORE removing the event, so the runner doesn't attempt one
        # last cycle on tickers that are about to be dropped.
        cancelled = 0
        if req.cancel_resting:
            om = request.app.state.order_manager
            ex = request.app.state.exchange
            if om is not None and ex is not None:
                target_ids: list[str] = []
                # ticker convention: "{event_ticker}-{strike}". Match by
                # exact prefix + dash to avoid false positives (e.g.
                # KXISMPMI matching KXISMPMIBOGUS).
                prefix = normalized + "-"
                for (ticker, _side), order in om.all_resting().items():
                    if ticker.upper().startswith(prefix):
                        target_ids.append(order.order_id)
                if target_ids:
                    try:
                        results = await ex.cancel_orders(target_ids)
                        cancelled = sum(1 for ok in results.values() if ok)
                        await om.reconcile(ex)
                    except Exception as exc:
                        logger.warning(
                            "remove_event: bulk cancel failed (%s); "
                            "removing event anyway, orders may remain", exc,
                        )

        try:
            new_version = await state.remove_event(req.event_ticker)
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="remove_event",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc

        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="remove_event",
            command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
            side_effect_summary={"cancelled_orders": cancelled},
        )
        await _broadcast_change(
            "remove_event", request_id=req.request_id, actor=actor,
        )
        return RemoveEventResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
            event_ticker=normalized, cancelled_orders=cancelled,
        )

    # ── Phase 7: manual theo overrides ─────────────────────────────

    @app.post("/control/set_theo_override", response_model=CommandResponse)
    async def post_set_theo_override(
        req: SetTheoOverrideRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        try:
            new_version = await state.set_theo_override(
                req.ticker,
                yes_probability=req.yes_cents / 100.0,
                confidence=req.confidence,
                reason=req.reason,
                actor=actor,
                mode=req.mode,
                auto_clear_seconds=req.auto_clear_seconds,
            )
        except ValueError as exc:
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="set_theo_override",
                command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=str(exc),
            )
            raise HTTPException(400, str(exc)) from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="set_theo_override",
            command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "set_theo_override", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/clear_theo_override", response_model=CommandResponse)
    async def post_clear_theo_override(
        req: ClearTheoOverrideRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        _check_if_version(req.if_version)
        version_before = state.version
        new_version = await state.clear_theo_override(req.ticker)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="clear_theo_override",
            command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        await _broadcast_change(
            "clear_theo_override", request_id=req.request_id, actor=actor,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    # ── Phase 6: runtime snapshot + surgical cancel ────────────────

    async def _collect_runtime() -> dict[str, Any]:
        """Snapshot positions + resting orders + balance for the dashboard.

        Resting orders come from the OrderManager's in-memory state (free,
        sync). Positions and balance are async REST calls; we run them in
        parallel and tolerate partial failure — the operator sees what we
        got, plus an `errors` array for the failed calls.
        """
        om = app.state.order_manager
        ex = app.state.exchange
        errors: list[str] = []
        resting_entries: list[dict[str, Any]] = []
        position_entries: list[dict[str, Any]] = []
        balance_entry: dict[str, Any] | None = None
        total_realized = 0.0
        total_fees = 0.0

        if om is not None:
            try:
                for (ticker, side), ro in sorted(
                    om.all_resting().items(), key=lambda kv: kv[0],
                ):
                    resting_entries.append({
                        "ticker": ticker, "side": side,
                        "order_id": ro.order_id,
                        "price_cents": ro.price_cents,
                        "size": ro.size,
                    })
            except Exception as exc:
                errors.append(f"order_manager.all_resting: {exc}")

        if ex is not None:
            positions_task = asyncio.create_task(ex.list_positions())
            balance_task = asyncio.create_task(ex.get_balance())
            results = await asyncio.gather(
                positions_task, balance_task, return_exceptions=True,
            )
            positions_result, balance_result = results
            if isinstance(positions_result, Exception):
                errors.append(f"exchange.list_positions: {positions_result}")
            else:
                for p in positions_result:
                    position_entries.append({
                        "ticker": p.ticker,
                        "quantity": p.quantity,
                        "avg_cost_cents": p.avg_cost_cents,
                        "realized_pnl_dollars": p.realized_pnl_dollars,
                        "fees_paid_dollars": p.fees_paid_dollars,
                    })
                    total_realized += p.realized_pnl_dollars
                    total_fees += p.fees_paid_dollars
            if isinstance(balance_result, Exception):
                errors.append(f"exchange.get_balance: {balance_result}")
            else:
                balance_entry = {
                    "cash_dollars": balance_result.cash_dollars,
                    "portfolio_value_dollars": balance_result.portfolio_value_dollars,
                }

        # Rate-limit stats from the Kalshi client (when wired). Lets the
        # dashboard show whether we're getting throttled / 429'd.
        rate_limit = None
        rls = app.state.rate_limit_stats
        if callable(rls):
            try:
                rate_limit = rls()
            except Exception as exc:
                errors.append(f"rate_limit_stats: {exc}")

        return {
            "positions": position_entries,
            "resting_orders": resting_entries,
            "balance": balance_entry,
            "total_realized_pnl_dollars": total_realized,
            "total_fees_paid_dollars": total_fees,
            "rate_limit": rate_limit,
            "errors": errors,
            "ts": time.time(),
        }

    app.state.collect_runtime = _collect_runtime

    def _collect_incentives() -> dict[str, Any]:
        """Snapshot the current incentives cache for HTTP/WS consumers.
        Returns an empty `programs` list when no cache is wired."""
        cache = app.state.incentive_cache
        if cache is None:
            return {
                "programs": [],
                "last_refresh_ts": 0.0,
                "last_refresh_age_s": None,
                "ts": time.time(),
            }
        now_ts = time.time()
        programs = cache.snapshot()
        out: list[dict[str, Any]] = []
        for p in programs:
            entry = p.to_dict()
            entry["time_remaining_s"] = p.time_remaining_s(now_ts)
            out.append(entry)
        return {
            "programs": out,
            "last_refresh_ts": cache.last_refresh_ts,
            "last_refresh_age_s": cache.last_refresh_age_s,
            "ts": now_ts,
        }

    app.state.collect_incentives = _collect_incentives

    # ── Exploit-mode endpoints ────────────────────────────────────────

    def _require_exploit_state():
        es = app.state.exploit_state
        if es is None:
            raise HTTPException(503, "exploit-mode not wired into this deployment")
        return es

    @app.post("/control/exploit/start", response_model=CommandResponse)
    async def post_exploit_start(
        req: ExploitStartRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        """Register / reconfigure a market for exploit mode."""
        es = _require_exploit_state()
        from lipmm.exploit.state import ExploitConfig
        version_before = es.version
        try:
            cfg = ExploitConfig(
                ticker=req.ticker.upper(),
                bid_target_c=req.bid_target_c,
                ask_target_c=req.ask_target_c,
                step_c=req.step_c,
                contracts_per_round=req.contracts_per_round,
                predator_offset_c=req.predator_offset_c,
                cycle_seconds=req.cycle_seconds,
                cooldown_between_legs_s=req.cooldown_between_legs_s,
                cooldown_after_round_s=req.cooldown_after_round_s,
                max_loss_dollars=req.max_loss_dollars,
                predator_absence_timeout_cycles=req.predator_absence_timeout_cycles,
                max_rounds=req.max_rounds,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        es.add(cfg)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="exploit_start", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=es.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_start", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=state.version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/exploit/pause", response_model=CommandResponse)
    async def post_exploit_pause(
        req: ExploitTickerRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        es = _require_exploit_state()
        ticker = req.ticker.upper()
        m = es.pause(ticker)
        if m is None:
            raise HTTPException(404, f"no exploit market for {ticker}")
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="exploit_pause", command_payload=req.model_dump(),
            state_version_before=state.version, state_version_after=state.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_pause", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=state.version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/exploit/resume", response_model=CommandResponse)
    async def post_exploit_resume(
        req: ExploitTickerRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        es = _require_exploit_state()
        ticker = req.ticker.upper()
        m = es.resume(ticker)
        if m is None:
            raise HTTPException(404, f"no exploit market for {ticker}")
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="exploit_resume", command_payload=req.model_dump(),
            state_version_before=state.version, state_version_after=state.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_resume", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=state.version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/exploit/kill", response_model=CommandResponse)
    async def post_exploit_kill(
        req: ExploitTickerRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        es = _require_exploit_state()
        ticker = req.ticker.upper()
        m = es.kill(ticker, reason=f"operator kill by {actor}")
        if m is None:
            raise HTTPException(404, f"no exploit market for {ticker}")
        # Best-effort cancel: spawn the kill_handler so cancels don't
        # block the response. Mirrors the global /control/kill pattern.
        kh = app.state.exploit_kill_handler
        if kh is not None:
            asyncio.create_task(kh())
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="exploit_kill", command_payload=req.model_dump(),
            state_version_before=state.version, state_version_after=state.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_kill", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=state.version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/exploit/kill_all", response_model=CommandResponse)
    async def post_exploit_kill_all(
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        es = _require_exploit_state()
        n = es.kill_all(reason=f"operator kill_all by {actor}")
        kh = app.state.exploit_kill_handler
        if kh is not None:
            asyncio.create_task(kh())
        emit_audit(
            request.app.state.decision_logger,
            request_id=f"exploit-killall-{int(time.time())}", actor=actor,
            command_type="exploit_kill_all",
            command_payload={"killed_count": n},
            state_version_before=state.version, state_version_after=state.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_kill_all", request_id="exploit-killall", actor=actor)
        return CommandResponse(
            new_version=state.version, request_id="exploit-killall", actor=actor,
        )

    @app.post("/control/exploit/remove", response_model=CommandResponse)
    async def post_exploit_remove(
        req: ExploitTickerRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        """Drop the market entirely from exploit state. Operator must
        ensure no resting orders remain; a prior /kill is recommended."""
        es = _require_exploit_state()
        ticker = req.ticker.upper()
        m = es.remove(ticker)
        if m is None:
            raise HTTPException(404, f"no exploit market for {ticker}")
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="exploit_remove", command_payload=req.model_dump(),
            state_version_before=state.version, state_version_after=state.version,
            succeeded=True,
        )
        await _broadcast_change("exploit_remove", request_id=req.request_id, actor=actor)
        return CommandResponse(
            new_version=state.version, request_id=req.request_id, actor=actor,
        )

    @app.get("/control/exploit/state", response_model=ExploitStateResponse)
    async def get_exploit_state(
        actor: str = Depends(require_auth),
    ) -> ExploitStateResponse:
        es = _require_exploit_state()
        now = time.time()
        rows: list[ExploitMarketEntry] = []
        for ticker, m in es.all_markets().items():
            rows.append(ExploitMarketEntry(
                ticker=ticker,
                phase=m.phase.value,
                leading_side=m.leading_side,
                current_ladder_c=int(m.current_ladder_c),
                paused=m.paused,
                round_counter=m.round_counter,
                realized_pnl_dollars=m.realized_pnl_dollars(),
                bid_target_c=m.config.bid_target_c,
                ask_target_c=m.config.ask_target_c,
                step_c=m.config.step_c,
                contracts_per_round=m.config.contracts_per_round,
                max_loss_dollars=m.config.max_loss_dollars,
                last_reason=m.last_reason,
                started_at_ts=m.started_at_ts,
                cooldown_remaining_s=max(0.0, m.cooldown_until_ts - now),
            ))
        return ExploitStateResponse(
            markets=rows, version=es.version, ts=now,
        )

    @app.get("/control/markout")
    async def get_markout(
        actor: str = Depends(require_auth),
    ) -> Any:
        """HTML fragment for the markout tab. Reads the tracker's
        in-memory snapshot of per-ticker stats. Returns an empty
        placeholder when no tracker is wired."""
        from fastapi.responses import HTMLResponse
        from lipmm.control.web.renderer import render_markout
        mo = app.state.markout_tracker
        if mo is None:
            return HTMLResponse(
                '<div class="text-[11px]" style="color: var(--ink-dim);">'
                'markout tracker not wired into this deployment'
                '</div>'
            )
        try:
            stats = mo.snapshot()
        except Exception as exc:
            return HTMLResponse(
                f'<div class="text-[11px]" style="color: var(--no);">'
                f'error reading markout: {exc}'
                f'</div>'
            )
        return HTMLResponse(render_markout(stats))

    @app.get("/control/pnl_grid")
    async def get_pnl_grid(
        actor: str = Depends(require_auth),
    ) -> Any:
        """HTML fragment for the PnL tab. Reads the most-recently-cached
        runtime + orderbook snapshots from the broadcaster and renders
        per-position PnL rows with totals."""
        from fastapi.responses import HTMLResponse
        from lipmm.control.web.renderer import render_pnl_grid
        bc = app.state.broadcaster
        runtime = getattr(bc, "last_runtime", None) if bc else None
        orderbooks = getattr(bc, "last_orderbook", None) if bc else None
        snap = state.snapshot()
        return HTMLResponse(render_pnl_grid(runtime, orderbooks, snap))

    @app.get("/control/earnings_history")
    async def get_earnings_history(
        actor: str = Depends(require_auth),
    ) -> Any:
        """Return an HTML fragment for the dashboard's earnings tab.
        Reads the persisted history file, computes histogram + stats,
        renders bars. Returns an empty placeholder when no history is
        wired."""
        from fastapi.responses import HTMLResponse
        eh = app.state.earnings_history
        if eh is None:
            return HTMLResponse(
                '<div class="text-[11px]" style="color: var(--ink-dim);">'
                'earnings history not wired into this deployment'
                '</div>'
            )
        try:
            stats = eh.histogram()
        except Exception as exc:
            return HTMLResponse(
                f'<div class="text-[11px]" style="color: var(--no);">'
                f'error reading earnings history: {exc}'
                f'</div>'
            )
        from lipmm.control.web.renderer import render_earnings_history
        return HTMLResponse(render_earnings_history(stats))

    @app.get("/control/notebooks")
    async def list_notebooks(
        actor: str = Depends(require_auth),
    ) -> Any:
        """Return the list of registered theo notebooks.

        Each notebook is a provider-contributed modular widget. The
        dashboard polls /control/notebooks/{key} for the selected
        notebook's HTML fragment.
        """
        registry = app.state.notebook_registry
        if registry is None:
            return {"notebooks": []}
        return {
            "notebooks": [
                {"key": key, "label": label}
                for key, label in registry.list()
            ]
        }

    @app.get("/control/notebooks/{key}")
    async def get_notebook(
        key: str,
        actor: str = Depends(require_auth),
    ) -> Any:
        """Return the HTML fragment for a registered notebook."""
        from fastapi.responses import HTMLResponse
        registry = app.state.notebook_registry
        if registry is None:
            raise HTTPException(status_code=404, detail="no notebook registry")
        nb = registry.get(key)
        if nb is None:
            raise HTTPException(status_code=404, detail=f"unknown notebook: {key}")
        try:
            html_fragment = await nb.render()
        except Exception as exc:
            return HTMLResponse(
                f'<div style="color: var(--no, #f87171); font-size: 11px;">'
                f'notebook render failed: {type(exc).__name__}: {exc}'
                f'</div>',
                status_code=500,
            )
        return HTMLResponse(html_fragment)

    @app.get("/control/orderbooks", response_model=OrderbookSnapshotResponse)
    async def get_orderbooks(
        actor: str = Depends(require_auth),
    ) -> OrderbookSnapshotResponse:
        """Return the last per-strike orderbook snapshot the runner
        emitted. Empty `strikes` list (with current `ts`) when the
        runner hasn't pushed yet (no broadcaster wired or no cycles
        completed)."""
        b = app.state.broadcaster
        snap: dict[str, Any] | None = b.last_orderbook if b is not None else None
        if snap is None:
            return OrderbookSnapshotResponse(
                strikes=[], last_cycle_ts=0.0, ts=time.time(),
            )
        return OrderbookSnapshotResponse(
            strikes=snap.get("strikes", []),
            last_cycle_ts=snap.get("last_cycle_ts", 0.0),
            ts=time.time(),
        )

    @app.get("/control/incentives", response_model=IncentiveSnapshotResponse)
    async def get_incentives(
        actor: str = Depends(require_auth),
    ) -> IncentiveSnapshotResponse:
        if app.state.incentive_cache is None:
            raise HTTPException(
                503, "incentive cache not wired into ControlServer "
                "(pass an IncentiveProvider on construction)",
            )
        return IncentiveSnapshotResponse(**_collect_incentives())

    @app.get("/control/runtime", response_model=RuntimeSnapshotResponse)
    async def get_runtime(
        actor: str = Depends(require_auth),
    ) -> RuntimeSnapshotResponse:
        if app.state.exchange is None and app.state.order_manager is None:
            raise HTTPException(
                503, "runtime requires an OrderManager and/or ExchangeClient "
                "wired into ControlServer",
            )
        snap = await _collect_runtime()
        return RuntimeSnapshotResponse(**snap)

    @app.post("/control/cancel_order", response_model=CancelOrderResponse)
    async def post_cancel_order(
        req: CancelOrderRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CancelOrderResponse:
        _check_if_version(req.if_version)
        om = request.app.state.order_manager
        ex = request.app.state.exchange
        if om is None or ex is None:
            err = "cancel_order requires an OrderManager + ExchangeClient wired into ControlServer"
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="cancel_order", command_payload=req.model_dump(),
                state_version_before=state.version,
                state_version_after=state.version,
                succeeded=False, error=err,
            )
            raise HTTPException(503, err)

        version_before = state.version
        located = om.find_by_order_id(req.order_id)
        if located is None:
            err = f"order_id={req.order_id!r} not in OrderManager state"
            emit_audit(
                request.app.state.decision_logger,
                request_id=req.request_id, actor=actor,
                command_type="cancel_order", command_payload=req.model_dump(),
                state_version_before=version_before,
                state_version_after=state.version,
                succeeded=False, error=err,
            )
            raise HTTPException(404, err)
        ticker, side, _ = located

        # Per-(ticker, side) lock so this can't race a concurrent apply()
        # from the runner cycle on the same key.
        lock = om._lock_for((ticker, side))  # noqa: SLF001 — intra-package use
        async with lock:
            try:
                cancelled = await ex.cancel_order(req.order_id)
            except Exception as exc:
                emit_audit(
                    request.app.state.decision_logger,
                    request_id=req.request_id, actor=actor,
                    command_type="cancel_order",
                    command_payload=req.model_dump(),
                    state_version_before=version_before,
                    state_version_after=state.version,
                    succeeded=False, error=f"exchange.cancel_order raised: {exc!r}",
                )
                raise HTTPException(500, f"exchange.cancel_order error: {exc!r}") from exc
            # Drop from OrderManager state regardless of cancelled bool —
            # if the exchange says "already gone" (False) the bot's view
            # was stale anyway.
            om.forget(ticker, side)

        # Auto-lock the (ticker, side) so the runner's next cycle skips
        # this side instead of immediately re-placing the order. Operator
        # must explicitly "lift lock" to resume. Per-side, so the other
        # side keeps quoting.
        if req.auto_lock:
            try:
                await state.lock_side(
                    ticker, side,
                    reason=(
                        f"auto-locked after operator cancel of "
                        f"{req.order_id} ({req.reason})"
                        if req.reason else
                        f"auto-locked after operator cancel of {req.order_id}"
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "auto_lock after cancel_order failed: %s; "
                    "side will be re-quoted next cycle", exc,
                )

        # Bump state version so dashboards re-render and so the version
        # advances visibly in the audit log.
        async with state._lock:  # noqa: SLF001 — intra-package
            new_version = state._bump_version()  # noqa: SLF001

        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="cancel_order", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
            side_effect_summary={
                "exchange_confirmed": cancelled,
                "ticker": ticker,
                "side": side,
                "order_id": req.order_id,
            },
        )
        await _broadcast_change("cancel_order", request_id=req.request_id, actor=actor)
        # Push an immediate runtime snapshot so the cancelled row drops
        # from open dashboards within the broadcast loop, not the next 5s tick.
        if broadcaster is not None:
            try:
                snap = await _collect_runtime()
                await broadcaster.broadcast_runtime(snap)
            except Exception as exc:
                logger.warning("post-cancel runtime broadcast failed: %s", exc)
        return CancelOrderResponse(
            cancelled=cancelled,
            order_id=req.order_id,
            ticker=ticker, side=side,
            new_version=new_version,
            request_id=req.request_id, actor=actor,
        )

    @app.get("/control/locks", response_model=LocksResponse)
    async def get_locks(actor: str = Depends(require_auth)) -> LocksResponse:
        locks = state.all_side_locks()
        entries = [
            LockEntry(
                ticker=ticker, side=side,
                mode=lock.mode, reason=lock.reason,
                locked_at=lock.locked_at,
                auto_unlock_at=lock.auto_unlock_at,
            )
            for (ticker, side), lock in sorted(locks.items(), key=lambda kv: kv[0])
        ]
        return LocksResponse(locks=entries)

    # ── Phase 3: WebSocket stream ─────────────────────────────────

    @app.websocket("/control/stream")
    async def control_stream(websocket: WebSocket) -> None:
        """Authenticated WebSocket stream for live state push.

        Auth: token via `?token=...` query param (browsers can't set
        Authorization on a WS upgrade). Token validated before accept;
        invalid → 1008 close (policy violation).

        On accept the server sends one initial event with the current
        state snapshot, then streams events: state_change, decision,
        tab_connected/disconnected, heartbeat. Tab gets a unique tab_id
        in the initial frame so the dashboard can show "I'm tab X".

        Server doesn't expect inbound messages from the client in v1
        — it's read-only push. Future phases may use inbound for
        client→server pings or subscription filters.
        """
        if broadcaster is None:
            # No broadcaster wired → reject; the operator should rebuild
            # the app with broadcaster= or use HTTP polling.
            await websocket.close(code=1011, reason="no broadcaster wired")
            return

        # 1. Auth via query param.
        token = websocket.query_params.get("token", "")
        if not token:
            await websocket.close(code=1008, reason="missing token")
            return
        secret_to_use = (
            websocket.app.state.control_secret
            if websocket.app.state.control_secret is not None
            else get_secret()
        )
        try:
            from jose import JWTError, jwt as _jwt
            claims = _jwt.decode(token, secret_to_use, algorithms=["HS256"])
            actor = claims.get("sub", "operator")
        except Exception as exc:
            await websocket.close(code=1008, reason=f"invalid token: {exc}")
            return

        # 2. Accept + silently register in the broadcaster.
        await websocket.accept()
        tab_id = await broadcaster.register(websocket)

        # 3. Send the initial snapshot frame DIRECTLY to the new tab
        # before notifying others. Order: initial → tab_connected (to
        # others) → live events.
        try:
            await websocket.send_json({
                "event_type": "initial",
                "tab_id": tab_id,
                "actor": actor,
                "snapshot": state.snapshot(),
                "presence": broadcaster.presence(),
                "total_tabs": broadcaster.tab_count,
                "ts": time.time(),
            })
            # Notify the OTHER tabs that someone joined
            await broadcaster.notify_join(tab_id)

            # 4. Read loop: just consume client messages and discard. The
            # WS is server-push; client messages aren't acted on in v1
            # (they keep the connection alive and let us detect disconnect).
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    break
        except Exception as exc:
            logger.info("WS tab_id=%s closed unexpectedly: %s", tab_id, exc)
        finally:
            await broadcaster.unregister(tab_id)

    @app.post("/control/swap_strategy", response_model=CommandResponse)
    async def post_swap_strategy(
        req: SwapStrategyRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        """Phase 1: validates the request but doesn't actually swap.
        Strategy hot-swap is deferred to Phase 2 (needs runner-side
        coordination)."""
        # Audit the request — operator can see we accepted it but didn't
        # actually swap, useful for telemetry on demand for the feature.
        version_before = state.version
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="swap_strategy",
            command_payload=req.model_dump(),
            state_version_before=version_before,
            state_version_after=version_before,
            succeeded=False,
            error="strategy hot-swap deferred to Phase 2 of the control plane",
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="strategy hot-swap is deferred to Phase 2",
        )

    # ── Phase 4: optional dashboard mount ──────────────────────────
    if mount_dashboard:
        if broadcaster is None:
            raise ValueError(
                "mount_dashboard=True requires a broadcaster — pass one explicitly "
                "or use ControlServer which auto-creates one"
            )
        from lipmm.control.web import mount_dashboard as _mount
        _mount(app, broadcaster=broadcaster, state=state, secret=secret)

    return app


class ControlServer:
    """Wraps a FastAPI app + uvicorn lifecycle for in-process serving.

    The server runs in the same asyncio event loop as the bot. start()
    spawns a background task hosting uvicorn; stop() cancels it.

    Designed so the runner owns the lifecycle:

        server = ControlServer(state, decision_logger=logger,
                               kill_handler=runner.cancel_all_resting)
        await server.start(host="0.0.0.0", port=8080)
        try:
            await runner.run()
        finally:
            await server.stop()
    """

    def __init__(
        self,
        state: ControlState,
        *,
        decision_logger: DecisionLogger | None = None,
        kill_handler: KillHandler | None = None,
        secret: str | None = None,
        order_manager: OrderManager | None = None,
        exchange: ExchangeClient | None = None,
        risk_registry: RiskRegistry | None = None,
        broadcaster: Broadcaster | None = None,
        mount_dashboard: bool = False,
        runtime_refresh_s: float | None = 5.0,
        incentive_provider: "Any | None" = None,
        incentives_refresh_s: float | None = 3600.0,
        incentive_cache: "IncentiveCache | None" = None,
        event_validator: Any = None,
        rate_limit_stats: Any = None,
        earnings_history: Any = None,
        markout_tracker: Any = None,
        notebook_registry: "Any | None" = None,
    ) -> None:
        self._state = state
        # Auto-create a broadcaster if none provided — the server's WS
        # endpoint requires one to function.
        self._broadcaster = broadcaster if broadcaster is not None else Broadcaster()
        # Use a pre-built cache when provided (so runner + server share
        # one); else auto-wrap a passed IncentiveProvider; else None.
        if incentive_cache is not None:
            self._incentive_cache = incentive_cache
        elif incentive_provider is not None and incentives_refresh_s is not None:
            self._incentive_cache = IncentiveCache(
                incentive_provider, refresh_s=incentives_refresh_s,
            )
        else:
            self._incentive_cache = None
        self._app = build_app(
            state,
            decision_logger=decision_logger,
            kill_handler=kill_handler,
            secret=secret,
            order_manager=order_manager,
            exchange=exchange,
            risk_registry=risk_registry,
            broadcaster=self._broadcaster,
            mount_dashboard=mount_dashboard,
            incentive_cache=self._incentive_cache,
            event_validator=event_validator,
            rate_limit_stats=rate_limit_stats,
            earnings_history=earnings_history,
            markout_tracker=markout_tracker,
            notebook_registry=notebook_registry,
        )
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None
        # Periodic runtime broadcast: pulls positions + resting + balance
        # every `runtime_refresh_s` seconds and pushes via the broadcaster.
        # Set to None to disable (used by tests that don't wire an
        # ExchangeClient).
        self._runtime_refresh_s = runtime_refresh_s
        self._runtime_task: asyncio.Task | None = None
        self._runtime_stop: asyncio.Event | None = None
        # Incentive broadcast loop: pulls the cache snapshot and pushes
        # via the broadcaster. The cache itself owns the upstream fetch
        # cadence; this loop is just rebroadcast at the same interval so
        # all dashboards stay in sync immediately after a refresh.
        self._incentives_refresh_s = incentives_refresh_s
        self._incentives_task: asyncio.Task | None = None
        self._incentives_stop: asyncio.Event | None = None

    @property
    def broadcaster(self) -> Broadcaster:
        return self._broadcaster

    @property
    def app(self) -> FastAPI:
        return self._app

    @property
    def incentive_cache(self) -> "IncentiveCache | None":
        """Public accessor so the runner can share this server's
        IncentiveCache (for end-of-cycle earnings accrual)."""
        return self._incentive_cache

    async def start(
        self, *, host: str = "127.0.0.1", port: int = 8080,
        log_level: str = "warning",
    ) -> None:
        """Start uvicorn as a background asyncio task. Returns once the
        server has indicated readiness (via uvicorn's started flag)."""
        if self._task is not None and not self._task.done():
            raise RuntimeError("ControlServer already running")
        config = uvicorn.Config(
            self._app, host=host, port=port,
            log_level=log_level, lifespan="off",
            # Avoid uvicorn installing its own signal handlers which
            # would conflict with the bot's existing handler.
            use_colors=False,
        )
        self._server = uvicorn.Server(config)
        # Suppress uvicorn's own signal-handler installation which
        # conflicts with the bot's main-loop handlers.
        self._server.install_signal_handlers = lambda: None
        self._task = asyncio.create_task(self._server.serve())
        # Brief yield so uvicorn can set up before we return
        for _ in range(100):
            if self._server.started:
                # Start the broadcaster's heartbeat once the server is up.
                await self._broadcaster.start_heartbeat()
                # Spawn the periodic runtime-snapshot loop if enabled.
                if self._runtime_refresh_s is not None:
                    self._runtime_stop = asyncio.Event()
                    self._runtime_task = asyncio.create_task(self._runtime_loop())
                # Spawn the incentives cache + broadcast loop if wired.
                if self._incentive_cache is not None:
                    await self._incentive_cache.start()
                    self._incentives_stop = asyncio.Event()
                    self._incentives_task = asyncio.create_task(
                        self._incentives_loop(),
                    )
                return
            await asyncio.sleep(0.01)

    async def _runtime_loop(self) -> None:
        """Periodically pull a runtime snapshot and broadcast it.

        Runs in the same loop as the FastAPI app. Tolerates partial /
        total failure: `_collect_runtime` already swallows individual
        errors and returns what it can; the broadcaster fan-out drops
        slow clients without affecting the rest.
        """
        assert self._runtime_stop is not None
        assert self._runtime_refresh_s is not None
        collect = getattr(self._app.state, "collect_runtime", None)
        if collect is None:
            return
        try:
            while not self._runtime_stop.is_set():
                try:
                    snap = await collect()
                    await self._broadcaster.broadcast_runtime(snap)
                except Exception as exc:
                    logger.warning("runtime sweep failed: %s", exc)
                try:
                    await asyncio.wait_for(
                        self._runtime_stop.wait(),
                        timeout=self._runtime_refresh_s,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _incentives_loop(self) -> None:
        """Periodically pull the cache snapshot and broadcast it as an
        `incentives_snapshot` event. The cache itself handles the
        upstream fetch + fault tolerance; this loop is only rebroadcast.
        """
        assert self._incentives_stop is not None
        assert self._incentives_refresh_s is not None
        collect = getattr(self._app.state, "collect_incentives", None)
        if collect is None:
            return
        # Push once immediately so dashboards see data without waiting.
        try:
            snap = collect()
            await self._broadcaster.broadcast_incentives(snap)
        except Exception as exc:
            logger.warning("initial incentives broadcast failed: %s", exc)
        try:
            while not self._incentives_stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._incentives_stop.wait(),
                        timeout=self._incentives_refresh_s,
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    snap = collect()
                    await self._broadcaster.broadcast_incentives(snap)
                except Exception as exc:
                    logger.warning("incentives broadcast tick failed: %s", exc)
        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        # Stop the incentives loop + cache first.
        if self._incentives_task is not None:
            if self._incentives_stop is not None:
                self._incentives_stop.set()
            try:
                await asyncio.wait_for(self._incentives_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._incentives_task.cancel()
            self._incentives_task = None
            self._incentives_stop = None
        if self._incentive_cache is not None:
            await self._incentive_cache.stop()
        # Stop the runtime loop first so it doesn't push during shutdown.
        if self._runtime_task is not None:
            if self._runtime_stop is not None:
                self._runtime_stop.set()
            try:
                await asyncio.wait_for(self._runtime_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._runtime_task.cancel()
            self._runtime_task = None
            self._runtime_stop = None
        # Stop heartbeat next so it doesn't try to push during shutdown.
        await self._broadcaster.stop_heartbeat()
        await self._broadcaster.close_all()
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        self._server = None
