"""Pydantic request/response models for the control plane.

Why pydantic here (lipmm core stays pydantic-free):
  - FastAPI integration: automatic 422 on validation failure, automatic
    OpenAPI schema generation for the dashboard's API client.
  - Per-field validators encode the contract loudly (e.g.
    `count > 0`, `1 <= price <= 99`) so an operator can't squeak through
    a malformed manual-order request.
  - lipmm core itself uses plain dataclasses; pydantic is scoped to the
    HTTP boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from lipmm.control.state import KillState, PauseScope


# ── Auth ────────────────────────────────────────────────────────────


class AuthRequest(BaseModel):
    """POST /control/auth body."""
    secret: str = Field(min_length=16, description="Shared deployment secret")
    actor: str = Field(default="operator", max_length=64,
                       description="Optional actor name for audit")


class AuthResponse(BaseModel):
    token: str
    expires_in_seconds: int
    actor: str


# ── Pause / resume ──────────────────────────────────────────────────


class PauseRequest(BaseModel):
    """POST /control/pause body."""
    scope: PauseScope
    ticker: str | None = Field(default=None, min_length=1, max_length=128)
    side: Literal["bid", "ask"] | None = None
    request_id: str = Field(min_length=8, max_length=128,
                            description="Idempotency key for audit")

    @model_validator(mode="after")
    def _scope_requires_extras(self) -> "PauseRequest":
        if self.scope in (PauseScope.TICKER, PauseScope.SIDE) and not self.ticker:
            raise ValueError(f"ticker required when scope={self.scope.value}")
        if self.scope == PauseScope.SIDE and self.side is None:
            raise ValueError("side required when scope=side")
        return self


class ResumeRequest(BaseModel):
    """POST /control/resume body. Same shape as PauseRequest."""
    scope: PauseScope
    ticker: str | None = Field(default=None, min_length=1, max_length=128)
    side: Literal["bid", "ask"] | None = None
    request_id: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _scope_requires_extras(self) -> "ResumeRequest":
        if self.scope in (PauseScope.TICKER, PauseScope.SIDE) and not self.ticker:
            raise ValueError(f"ticker required when scope={self.scope.value}")
        if self.scope == PauseScope.SIDE and self.side is None:
            raise ValueError("side required when scope=side")
        return self


# ── Kill / arm ──────────────────────────────────────────────────────


class KillRequest(BaseModel):
    """POST /control/kill body."""
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="", max_length=512,
                        description="Operator-provided reason for audit")


class ArmRequest(BaseModel):
    """POST /control/arm body."""
    request_id: str = Field(min_length=8, max_length=128)


# ── Knob updates ────────────────────────────────────────────────────


class KnobUpdateRequest(BaseModel):
    """POST /control/set_knob body. Bounds-validated server-side against
    ControlConfig.knob_bounds at apply time (not here — names are
    deployment-configurable)."""
    name: str = Field(min_length=1, max_length=64)
    value: float
    request_id: str = Field(min_length=8, max_length=128)


class KnobClearRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=128)


# ── Strategy swap (placeholder for now) ─────────────────────────────


class SwapStrategyRequest(BaseModel):
    """POST /control/swap_strategy body. Phase 1 ships the endpoint
    but only validates the request — actual strategy hot-swap requires
    coordination with the runner that's deferred to Phase 2."""
    strategy_name: str = Field(min_length=1, max_length=64,
                               description="e.g. 'default-lip-quoting' or 'sticky-defense'")
    request_id: str = Field(min_length=8, max_length=128)


# ── State snapshot response ─────────────────────────────────────────


class StateResponse(BaseModel):
    """GET /control/state response. Mirror of ControlState.snapshot()."""
    version: int
    kill_state: KillState
    global_paused: bool
    paused_tickers: list[str]
    paused_sides: list[list[str]]   # [[ticker, side], ...]
    knob_overrides: dict[str, float]


# ── Generic command response ────────────────────────────────────────


class CommandResponse(BaseModel):
    """Returned by every successful command endpoint. Includes the
    new state version so the dashboard can update its cached version
    counter without an extra round-trip."""
    ok: bool = True
    new_version: int
    request_id: str
    actor: str


class HealthResponse(BaseModel):
    ok: bool = True
    state_version: int
