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
    if_version: int | None = Field(
        default=None, ge=0,
        description="Optimistic concurrency: if set, command is rejected "
                    "with 409 if the server's state version != if_version. "
                    "None = no check (last-write-wins, default).",
    )

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
    if_version: int | None = Field(default=None, ge=0)

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
    if_version: int | None = Field(default=None, ge=0)


class ArmRequest(BaseModel):
    """POST /control/arm body."""
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


# ── Knob updates ────────────────────────────────────────────────────


class KnobUpdateRequest(BaseModel):
    """POST /control/set_knob body. Bounds-validated server-side against
    ControlConfig.knob_bounds at apply time (not here — names are
    deployment-configurable)."""
    name: str = Field(min_length=1, max_length=64)
    value: float
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class KnobClearRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


# ── Strategy swap (placeholder for now) ─────────────────────────────


class SwapStrategyRequest(BaseModel):
    """POST /control/swap_strategy body. Phase 1 ships the endpoint
    but only validates the request — actual strategy hot-swap requires
    coordination with the runner that's deferred to Phase 2."""
    strategy_name: str = Field(min_length=1, max_length=64,
                               description="e.g. 'default-lip-quoting' or 'sticky-defense'")
    request_id: str = Field(min_length=8, max_length=128)


# ── Manual orders + side locks ──────────────────────────────────────


class ManualOrderRequest(BaseModel):
    """POST /control/manual_order body."""
    ticker: str = Field(min_length=1, max_length=128)
    side: Literal["bid", "ask"]
    count: int = Field(gt=0, le=100_000,
                       description="Contracts to place")
    limit_price_cents: int = Field(ge=1, le=99,
                                   description="Limit price in cents (1..99)")
    lock_after: bool = Field(
        default=False,
        description="If true, lock this side after a successful place "
                    "(strategy stops quoting it until /unlock_side or auto-expiry)",
    )
    lock_auto_unlock_seconds: float | None = Field(
        default=None, ge=1.0, le=86400.0,
        description="If lock_after, auto-unlock after this many seconds "
                    "(1..86400). None = manual unlock only.",
    )
    reason: str = Field(default="", max_length=512,
                        description="Operator-provided reason for audit")
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class ManualOrderResponse(BaseModel):
    """POST /control/manual_order response. Distinguishes succeeded /
    risk_vetoed / exchange_rejected so the UI can render the right message."""
    succeeded: bool
    risk_vetoed: bool
    action: str                         # SideExecution.action enum value
    reason: str                         # human-readable
    order_id: str | None = None
    price_cents: int | None = None
    size: int | None = None
    latency_ms: int = 0
    risk_audit: list[dict] = Field(default_factory=list)
    lock_applied: bool = False
    lock_auto_unlock_at: float | None = None
    new_version: int
    request_id: str
    actor: str


class LockSideRequest(BaseModel):
    """POST /control/lock_side body. Operator-initiated lock, not from a
    manual order's lock_after flag."""
    ticker: str = Field(min_length=1, max_length=128)
    side: Literal["bid", "ask"]
    reason: str = Field(default="", max_length=512)
    auto_unlock_seconds: float | None = Field(
        default=None, ge=1.0, le=86400.0,
        description="Auto-unlock TTL in seconds. None = manual only.",
    )
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class UnlockSideRequest(BaseModel):
    """POST /control/unlock_side body."""
    ticker: str = Field(min_length=1, max_length=128)
    side: Literal["bid", "ask"]
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class LockEntry(BaseModel):
    """One entry in the GET /control/locks response."""
    ticker: str
    side: str
    mode: str
    reason: str
    locked_at: float
    auto_unlock_at: float | None


class LocksResponse(BaseModel):
    """GET /control/locks response."""
    locks: list[LockEntry]


# ── Theo override (manual operator-set fair value) ────────────────


class SetTheoOverrideRequest(BaseModel):
    """POST /control/set_theo_override body.

    `yes_cents` is the operator-friendly form (1..99 integer); the
    server converts to a float `yes_probability` in [0.01, 0.99] before
    storing. `confidence` is on the framework's calibrated scale; 1.0 =
    "trust this within 1c on a 100c scale." `reason` is required and
    must be ≥4 chars to make the audit trail useful.
    """
    ticker: str = Field(min_length=1, max_length=128)
    yes_cents: int = Field(ge=1, le=99,
                           description="Operator's fair-value estimate in cents (1..99)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = Field(min_length=4, max_length=512,
                        description="Required audit string — why this override?")
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class ClearTheoOverrideRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)


class TheoOverrideEntry(BaseModel):
    """One row in the GET /control/state theo_overrides list."""
    ticker: str
    yes_probability: float
    yes_cents: int
    confidence: float
    reason: str
    set_at: float
    actor: str


# ── Runtime snapshot (positions / resting orders / balance) ────────


class PositionEntry(BaseModel):
    """One row in the GET /control/runtime positions list."""
    ticker: str
    quantity: int
    avg_cost_cents: int
    realized_pnl_dollars: float
    fees_paid_dollars: float


class RestingOrderEntry(BaseModel):
    """One row in the resting-orders list."""
    ticker: str
    side: Literal["bid", "ask"]
    order_id: str
    price_cents: int
    size: int


class BalanceEntry(BaseModel):
    cash_dollars: float
    portfolio_value_dollars: float


class RuntimeSnapshotResponse(BaseModel):
    """GET /control/runtime — current positions + resting orders + balance.

    Tolerant of partial failure: if one of the three async calls raised,
    the corresponding field is an empty list/None and `errors` enumerates
    what failed. Operator can still see what we have.
    """
    positions: list[PositionEntry] = Field(default_factory=list)
    resting_orders: list[RestingOrderEntry] = Field(default_factory=list)
    balance: BalanceEntry | None = None
    total_realized_pnl_dollars: float = 0.0
    total_fees_paid_dollars: float = 0.0
    errors: list[str] = Field(default_factory=list)
    ts: float


class OrderbookLevel(BaseModel):
    """One price-level row in the L2 depth ladder."""
    price_cents: int = Field(ge=1, le=99)
    size: float = Field(ge=0)


class StrikeOrderbook(BaseModel):
    """Per-strike orderbook snapshot. `yes_levels` and `no_levels` are
    descending by price (highest first); `best_bid_c` / `best_ask_c` are
    derived from those, excluding our own resting orders, exactly as the
    runner already computes them for the strategy."""
    ticker: str
    best_bid_c: int = Field(ge=0, le=100)
    best_ask_c: int = Field(ge=0, le=100)
    yes_levels: list[OrderbookLevel] = Field(default_factory=list)
    no_levels: list[OrderbookLevel] = Field(default_factory=list)
    ts: float


class OrderbookSnapshotResponse(BaseModel):
    """GET /control/orderbooks response. Mirror of the cached snapshot
    that the runner emits each cycle."""
    strikes: list[StrikeOrderbook] = Field(default_factory=list)
    last_cycle_ts: float = 0.0
    ts: float


class IncentiveProgramEntry(BaseModel):
    """One row in /control/incentives. Operator-friendly: dollars and
    seconds-remaining precomputed; the raw centi-cents and ISO strings
    stay on the framework dataclass."""
    id: str
    market_ticker: str
    market_id: str
    incentive_type: str
    incentive_description: str = ""
    start_date_ts: float
    end_date_ts: float
    period_reward_dollars: float
    discount_factor_bps: int | None = None
    discount_factor_pct: float | None = None
    target_size_contracts: float | None = None
    paid_out: bool = False
    time_remaining_s: float


class IncentiveSnapshotResponse(BaseModel):
    """GET /control/incentives response."""
    programs: list[IncentiveProgramEntry] = Field(default_factory=list)
    last_refresh_ts: float = 0.0
    last_refresh_age_s: float | None = None
    ts: float


class CancelOrderRequest(BaseModel):
    """POST /control/cancel_order body — surgical cancel by exchange order_id."""
    order_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=512)
    request_id: str = Field(min_length=8, max_length=128)
    if_version: int | None = Field(default=None, ge=0)
    auto_lock: bool = Field(
        default=True,
        description=(
            "When True (default), engage a side-lock on (ticker, side) "
            "after a successful cancel so the next runner cycle won't "
            "immediately re-place the order. Operator must call "
            "/control/unlock_side to resume quoting on that side."
        ),
    )


class CancelOrderResponse(BaseModel):
    cancelled: bool
    order_id: str
    ticker: str | None = None
    side: str | None = None
    new_version: int
    request_id: str
    actor: str


# ── State snapshot response ─────────────────────────────────────────


class StateResponse(BaseModel):
    """GET /control/state response. Mirror of ControlState.snapshot()."""
    version: int
    kill_state: KillState
    global_paused: bool
    paused_tickers: list[str]
    paused_sides: list[list[str]]   # [[ticker, side], ...]
    knob_overrides: dict[str, float]
    side_locks: list[LockEntry] = Field(default_factory=list)
    theo_overrides: list[TheoOverrideEntry] = Field(default_factory=list)


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
