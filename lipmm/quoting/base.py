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

    `yes_depth` and `no_depth` are sorted highest-price-first
    (best-first by Kalshi convention). Each entry is (price_cents, size).
    `best_bid` is highest Yes bid excluding our own resting orders;
    `best_ask` is computed via 100 - best_no_bid (also excluding ours).
    """

    yes_depth: list[tuple[int, float]]
    no_depth: list[tuple[int, float]]
    best_bid: int            # highest Yes bid (excluding ours), 0 if empty
    best_ask: int            # lowest Yes ask (excluding ours), 100 if empty


@dataclass(frozen=True)
class OurState:
    """What we currently have resting on Kalshi for this strike."""

    cur_bid_px: int          # 0 if no order
    cur_bid_size: int        # 0 if no order
    cur_bid_id: str | None
    cur_ask_px: int          # 0 if no order
    cur_ask_size: int        # 0 if no order
    cur_ask_id: str | None


# ── Outputs the strategy returns ──────────────────────────────────────


@dataclass(frozen=True)
class SideDecision:
    """Strategy's decision for one side (bid or ask) of one strike.

      price:  cents, in [1, 99]. Ignored if skip=True.
      size:   contracts. Ignored if skip=True.
      skip:   True → bot cancels any existing order on this side and does NOT
              place a new one. Use for COOLDOWN, theo-confidence-too-low,
              sticky-bypass-dead-strike, etc.
      reason: human-readable, surfaced in decision logs and dashboards.
              Should be specific enough that an analyst (or LLM) reading
              "amend bid 22→23 (penny inside 24c best)" gets the why.
      extras: strategy-specific debugging detail (sticky state, anti-spoof
              calculations, etc.). Goes into decision-log record.
    """

    price: int
    size: int
    skip: bool = False
    reason: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


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
