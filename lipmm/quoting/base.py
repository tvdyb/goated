"""QuotingStrategy protocol and the dataclasses that flow in/out.

The bot's hot loop, for each strike per cycle, builds the inputs and asks
the strategy:

    decision = await strategy.quote(
        ticker=...,
        theo=theo_result,
        orderbook=ob_snapshot,
        our_state=our_resting_state,
        now_ts=time.time(),
        time_to_settle_s=tau_seconds,
    )

The strategy returns a QuotingDecision. The bot then translates that into
order placements / amendments / cancellations. The strategy DOES NOT touch
the Kalshi API directly — separation of concerns.

Strategies own any internal state (sticky machines, last-prices history,
toxic-strike sets) and persist it across `quote()` calls within a single
bot session. State is in-memory; bot restart resets it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lipmm.theo import TheoResult


# ── Inputs the strategy receives ──────────────────────────────────────


@dataclass(frozen=True)
class OrderbookSnapshot:
    """One cycle's view of an orderbook for one strike.

    Two coexisting unit views:
      - **t1c (tenths-of-a-cent)**: `yes_depth`, `no_depth`,
        `best_bid_t1c`, `best_ask_t1c`. 10 t1c = 1¢. Sub-cent
        markets carry levels like 977 (= 97.7¢). The strategy uses
        these when it cares about sub-cent precision.
      - **cents (rounded)**: `best_bid`, `best_ask`. Legacy facade —
        rounded to nearest whole cent for simple display. Strategies
        that don't care about sub-cent can keep using these.

    `tick_schedule` describes the per-range tick granularity (see
    `lipmm.execution.base.TickSchedule`). Strategy looks up the
    applicable tick at any given price via `tick_at(schedule, p)`.
    """

    yes_depth: list[tuple[int, float]]   # [(price_t1c, size), ...]
    no_depth: list[tuple[int, float]]
    best_bid: int            # highest Yes bid (excluding ours), 0 if empty (cents, rounded)
    best_ask: int            # lowest Yes ask (excluding ours), 100 if empty (cents, rounded)
    best_bid_t1c: int = -1   # sentinel: -1 = "derive from cents × 10"
    best_ask_t1c: int = -1   # sentinel: -1 = "derive from cents × 10"
    tick_schedule: list = field(default_factory=lambda: [(10, 990, 10)])

    def __post_init__(self) -> None:
        # Auto-derive t1c from cents when caller (e.g. legacy test)
        # only provided cents. Lossy on sub-cent but lets old code paths
        # keep working unchanged.
        if self.best_bid_t1c == -1:
            object.__setattr__(self, "best_bid_t1c", self.best_bid * 10)
        if self.best_ask_t1c == -1:
            object.__setattr__(
                self, "best_ask_t1c",
                self.best_ask * 10 if self.best_ask < 100 else 1000,
            )


@dataclass(frozen=True)
class OurState:
    """What we currently have resting on Kalshi for this strike."""

    cur_bid_px: int          # 0 if no order (cents, rounded)
    cur_bid_size: int        # 0 if no order
    cur_bid_id: str | None
    cur_ask_px: int          # 0 if no order (cents, rounded)
    cur_ask_size: int        # 0 if no order
    cur_ask_id: str | None
    cur_bid_px_t1c: int = 0  # tenths-of-a-cent; 0 if no order
    cur_ask_px_t1c: int = 0  # tenths-of-a-cent; 0 if no order


# ── Outputs the strategy returns ──────────────────────────────────────


@dataclass(frozen=True)
class SideDecision:
    """Strategy's decision for one side (bid or ask) of one strike.

      price:    cents, in [1, 99]. Ignored if skip=True. Always set;
                rounded from price_t1c when sub-cent.
      price_t1c:tenths-of-a-cent; precise quote price. Adapter routes
                through Kalshi's fractional path when this isn't a
                whole-cent multiple. Defaults to price × 10.
      size:     contracts. Ignored if skip=True.
      skip:     True → bot cancels any existing order on this side and
                does NOT place a new one.
      reason:   human-readable, surfaced in decision logs and dashboards.
      extras:   strategy-specific debugging detail.
    """

    price: int
    size: int
    skip: bool = False
    reason: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    price_t1c: int | None = None

    def effective_t1c(self) -> int:
        """Return the precise quote price in t1c. Falls back to
        `price * 10` when the strategy didn't set price_t1c."""
        return self.price_t1c if self.price_t1c is not None else self.price * 10


@dataclass(frozen=True)
class QuotingDecision:
    """Full per-strike quoting result for one cycle."""

    bid: SideDecision
    ask: SideDecision
    # State-machine transitions emitted this cycle (for decision-log records).
    # Each entry is a strategy-defined dict with at minimum
    # {"side": "bid"|"ask", "from": str, "to": str, "reason": dict}.
    transitions: list[dict[str, Any]] = field(default_factory=list)


# ── The protocol ──────────────────────────────────────────────────────


@runtime_checkable
class QuotingStrategy(Protocol):
    """A pluggable LIP-farming strategy.

    Every strategy implements:
      - `name`: short human-readable identifier surfaced in decision logs.
      - `warmup` / `shutdown`: lifecycle hooks (mostly no-ops; provided for
        symmetry with TheoProvider).
      - `quote(...)`: the per-strike per-cycle decision.

    Strategies MUST NOT touch the Kalshi API or any I/O. They are pure
    decision functions over the inputs they receive. Side effects (placing
    orders, amending, cancelling) happen in the bot's core after seeing
    the QuotingDecision.

    Strategies MAY hold internal state (sticky state machines, recent-price
    histories, etc.) that survives across `quote()` calls.
    """

    name: str

    async def warmup(self) -> None:
        ...

    async def shutdown(self) -> None:
        ...

    async def quote(
        self,
        *,
        ticker: str,
        theo: TheoResult,
        orderbook: OrderbookSnapshot,
        our_state: OurState,
        now_ts: float,
        time_to_settle_s: float,
        control_overrides: dict[str, Any] | None = None,
    ) -> QuotingDecision:
        """Compute the strike's quoting decision.

        `control_overrides`: optional dict of runtime knob overrides from
        the dashboard control plane. Strategies that consume overrides
        should look up documented keys (see strategy docstrings) and use
        them in place of their configured defaults. Strategies that don't
        consume overrides should ignore the kwarg — keeping the protocol
        backward-compatible."""
        ...
