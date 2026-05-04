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
from typing import Any, Awaitable, Callable

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from lipmm.control.audit import emit_audit
from lipmm.control.auth import (
    DEFAULT_TOKEN_TTL_S,
    constant_time_secret_compare,
    issue_token,
    require_auth,
)
from lipmm.control.commands import (
    ArmRequest,
    AuthRequest,
    AuthResponse,
    CommandResponse,
    HealthResponse,
    KillRequest,
    KnobClearRequest,
    KnobUpdateRequest,
    PauseRequest,
    ResumeRequest,
    StateResponse,
    SwapStrategyRequest,
)
from lipmm.control.state import ControlState, KillState, PauseScope
from lipmm.observability import DecisionLogger

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
) -> FastAPI:
    """Construct the FastAPI app. Caller wires in the ControlState and
    optional collaborators (logger for audit, kill_handler for the kill
    button). `secret` overrides the env-var lookup (useful for tests)."""
    app = FastAPI(
        title="lipmm Control Plane",
        description="HTTP control surface for runtime bot management.",
        version="0.1.0",
    )
    # Stash collaborators on app.state so route handlers can find them
    # without importing module-level globals.
    app.state.control_state = state
    app.state.decision_logger = decision_logger
    app.state.kill_handler = kill_handler
    app.state.control_secret = secret  # None → require_auth reads env

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
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/resume", response_model=CommandResponse)
    async def post_resume(
        req: ResumeRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
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
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/kill", response_model=CommandResponse)
    async def post_kill(
        req: KillRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        version_before = state.version
        new_version = await state.kill()
        # Invoke the kill handler (cancel all resting orders) AFTER
        # state mutation so the runner sees is_killed=True if it races.
        cancelled = 0
        handler = request.app.state.kill_handler
        if handler is not None:
            try:
                cancelled = await handler()
            except Exception as exc:
                logger.exception("kill_handler raised: %s", exc)
                emit_audit(
                    request.app.state.decision_logger,
                    request_id=req.request_id, actor=actor,
                    command_type="kill",
                    command_payload=req.model_dump(),
                    state_version_before=version_before,
                    state_version_after=new_version,
                    succeeded=False,
                    error=f"kill_handler error: {exc!r}",
                    side_effect_summary={"orders_cancelled": cancelled},
                )
                raise HTTPException(500, f"kill handler error: {exc!r}") from exc
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="kill", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
            side_effect_summary={"orders_cancelled": cancelled},
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/arm", response_model=CommandResponse)
    async def post_arm(
        req: ArmRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
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
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/set_knob", response_model=CommandResponse)
    async def post_set_knob(
        req: KnobUpdateRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
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
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

    @app.post("/control/clear_knob", response_model=CommandResponse)
    async def post_clear_knob(
        req: KnobClearRequest,
        request: Request,
        actor: str = Depends(require_auth),
    ) -> CommandResponse:
        version_before = state.version
        new_version = await state.clear_knob(req.name)
        emit_audit(
            request.app.state.decision_logger,
            request_id=req.request_id, actor=actor,
            command_type="clear_knob", command_payload=req.model_dump(),
            state_version_before=version_before, state_version_after=new_version,
            succeeded=True,
        )
        return CommandResponse(
            new_version=new_version, request_id=req.request_id, actor=actor,
        )

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
    ) -> None:
        self._state = state
        self._app = build_app(
            state, decision_logger=decision_logger,
            kill_handler=kill_handler, secret=secret,
        )
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    @property
    def app(self) -> FastAPI:
        return self._app

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
                return
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        self._server = None
