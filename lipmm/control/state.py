"""ControlState — central mutable state the runner consults each cycle.

Source of truth for all operator-controlled runtime state:
  - Pause scopes (global, per-ticker, per-side)
  - Kill switch (off / killed / armed)
  - Strategy/risk knob overrides
  - State version counter (for optimistic concurrency in future Phase 3)

In-process, async-locked. Reset on bot restart by virtue of being in-memory
(deliberate user choice — knob changes don't persist across restarts).

Side locks (Phase 2) and tab presence (Phase 3) will live here too but
aren't implemented yet. The class shape leaves room for them without
breaking the v1 API.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)


SideName = Literal["bid", "ask"]


@dataclass(frozen=True)
class ControlConfig:
    """Static config for ControlState. Knob constraints live here."""
    # Permitted knob names + (min, max) bounds. Unknown knobs are rejected.
    # Bounds use float; integer knobs are validated to be whole-numbered.
    knob_bounds: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        # DefaultLIPQuoting knobs
        "min_theo_confidence": (0.0, 1.0),
        "match_best_min_confidence": (0.0, 1.0),
        "penny_inside_min_confidence": (0.0, 1.0),
        "penny_inside_distance": (1.0, 10.0),
        "theo_tolerance_c": (-50.0, 50.0),
        "max_distance_from_best": (0.0, 50.0),
        "desert_threshold_c": (0.0, 50.0),
        "dollars_per_side": (0.0, 100.0),
        "max_distance_from_extremes_c": (0.0, 99.0),
        # TruEV-provider-specific: inflates the lognormal σ to absorb
        # model RMSE (default 0 = no inflation). Set on the Knobs tab
        # to e.g. 8 for honest at-the-money probabilities. Read by
        # TruEVTheoProvider each cycle from state.all_knobs().
        "truev_model_rmse_pts": (0.0, 50.0),
        # StickyDefenseQuoting knobs
        "sticky_min_distance_from_theo": (0.0, 50.0),
        "sticky_desert_jump_cents": (0.0, 50.0),
        # Risk gate knobs
        "max_notional_per_side_dollars": (0.0, 1000.0),
        "max_orders_per_cycle": (1.0, 1000.0),
        "max_position_per_side": (0.0, 100000.0),
        "mid_delta_threshold_c": (0.0, 100.0),
    })


class KillState(str, Enum):
    """Kill switch lifecycle. OFF → KILLED (via /control/kill) → ARMED
    (via /control/arm) → OFF (after first successful resume).

    KILLED  — strategy stops quoting, all resting orders cancelled by the
              runner's kill handler. Manual orders blocked.
    ARMED   — operator has acknowledged the kill; strategy still paused
              but resume is allowed. Distinguishes "killed and forgotten"
              from "killed and being recovered."
    OFF     — normal operation.
    """
    OFF = "off"
    KILLED = "killed"
    ARMED = "armed"


class PauseScope(str, Enum):
    """Granularity of a pause command."""
    GLOBAL = "global"
    TICKER = "ticker"
    SIDE = "side"


@dataclass
class _Pauses:
    """Internal: tracks all current pause states."""
    global_paused: bool = False
    paused_tickers: set[str] = field(default_factory=set)
    # Set of (ticker, side) tuples
    paused_sides: set[tuple[str, SideName]] = field(default_factory=set)


@dataclass(frozen=True)
class TheoOverride:
    """A manual theo value the operator has plugged in via the dashboard.

    Lives in `ControlState.theo_overrides[ticker]`. The runner consults
    this BEFORE calling the registered TheoProvider — if an override
    exists, the override wins and the provider is skipped entirely.

    The strategy doesn't know it's an override; it just receives a
    `TheoResult` whose `source` reads `manual-override:{actor}` or
    `manual-override-mid:{actor}` for the market-following variant.

    Two `mode`s are supported:
      - `"fixed"`: theo = yes_probability (operator-typed, static).
      - `"track_mid"`: theo = (best_bid + best_ask) / 200 each cycle,
        computed live from the orderbook. `yes_probability` is unused
        at quote time but kept as a placeholder so the dataclass stays
        well-formed. The strategy still uses `confidence` to pick its
        3-tier mode (penny-inside / match / follow). One-sided or
        crossed books force confidence to 0 that cycle so the strategy
        skips the strike.

    Runtime-only: cleared on bot restart by virtue of being in-memory
    (matches the knob-override convention). The dashboard surfaces a
    "cleared on restart" reminder so the operator doesn't lean on
    overrides for long-term state.
    """
    yes_probability: float    # in [0,1]
    confidence: float         # in [0,1]; controls whether strategy quotes
    reason: str               # operator-provided audit string
    set_at: float             # unix timestamp
    actor: str                # who set it (from JWT)
    mode: Literal["fixed", "track_mid"] = "fixed"
    auto_clear_at: float | None = None
    """Unix timestamp at which the runner stops honoring this override
    (treated as if cleared). None = no auto-expiry. Used for
    time-bounded manual market making sessions: operator can pin a
    strike for N minutes and walk away knowing the override expires
    on its own. The state isn't auto-deleted (so the operator can
    still see the expired override on the dashboard with a "expired"
    badge) — it's just ignored at quote time."""


@dataclass(frozen=True)
class SideLock:
    """A lock on a strike-side that the strategy must respect.

    Locks are stronger than pauses: pauses are operator-driven and the
    operator manually unpauses them; locks have semantic intent (often
    set automatically by manual orders via the `lock_after` flag) and
    can self-expire on a timestamp.

    Modes (Phase 2 supports "lock" only; "reduce_only" deferred until
    position-aware infrastructure lands):
      - "lock":        strategy emits skip=True for this side until unlocked
      - "reduce_only": strategy may only place orders that reduce position
                       (DEFERRED — needs position polling, not in v1)

    Auto-unlock:
      - auto_unlock_at: unix timestamp; lazily cleared when checked past it
      - None:           manual unlock only
    """
    mode: Literal["lock", "reduce_only"]
    reason: str
    locked_at: float
    auto_unlock_at: float | None = None


class ControlState:
    """Mutable shared state. All mutations bump the version counter and
    take the async lock. Reads are unsynchronized (consistent under
    asyncio's single-threaded model)."""

    def __init__(self, cfg: ControlConfig | None = None) -> None:
        self._cfg = cfg or ControlConfig()
        self._lock = asyncio.Lock()
        self._version: int = 0
        self._pauses = _Pauses()
        self._kill_state: KillState = KillState.OFF
        # knob_overrides[name] = value. Strategies/runner read these and
        # use them in place of configured defaults when present.
        self._knob_overrides: dict[str, float] = {}
        # side_locks[(ticker, side)] = SideLock; strategy must respect.
        self._side_locks: dict[tuple[str, SideName], SideLock] = {}
        # theo_overrides[ticker] = TheoOverride; runner consults this
        # BEFORE calling the registered TheoProvider.
        self._theo_overrides: dict[str, TheoOverride] = {}
        # Active event tickers. The MultiEventTickerSource reads this
        # set each cycle and yields all open markets across them. The
        # operator adds/removes via the dashboard. Runtime-only.
        self._active_events: set[str] = set()
        # Per-event knob overrides: event_ticker → {knob_name: value}.
        # Layered between global knob_overrides and strike-level
        # overrides. Runtime-only.
        self._event_knob_overrides: dict[str, dict[str, float]] = {}
        # Per-strike knob overrides: strike_ticker → {knob_name: value}.
        # Highest precedence among "both-side" overrides.
        self._strike_knob_overrides: dict[str, dict[str, float]] = {}
        # Per-strike PER-SIDE knob overrides:
        #   (strike_ticker, side) → {knob_name: value}    side ∈ {"bid","ask"}
        # Layered ON TOP of strike-level both-side overrides — lets the
        # operator dial in different (e.g.) `theo_tolerance_c` for the
        # bid vs ask side of one strike. Most useful when the operator
        # has asymmetric trust in their theo (e.g. willing to fill on
        # the YES side but skittish on the NO side, or vice versa).
        self._strike_side_knob_overrides: dict[
            tuple[str, str], dict[str, float]
        ] = {}

    @property
    def version(self) -> int:
        return self._version

    # ── Reads (lock-free; async-safe under single-threaded asyncio) ──

    def is_killed(self) -> bool:
        return self._kill_state == KillState.KILLED

    def is_armed(self) -> bool:
        """In ARMED state — kill cleared, but resume not yet issued."""
        return self._kill_state == KillState.ARMED

    def kill_state(self) -> KillState:
        return self._kill_state

    def is_global_paused(self) -> bool:
        return self._pauses.global_paused

    def is_ticker_paused(self, ticker: str) -> bool:
        return ticker in self._pauses.paused_tickers

    def is_side_paused(self, ticker: str, side: SideName) -> bool:
        return (ticker, side) in self._pauses.paused_sides

    def should_skip_cycle(self) -> bool:
        """The runner asks this at the top of every cycle. True →
        skip the entire cycle (no theo, no orders, just sleep)."""
        return self.is_killed() or self.is_global_paused()

    def should_skip_ticker(self, ticker: str) -> bool:
        """The runner asks this for each ticker."""
        return self.should_skip_cycle() or self.is_ticker_paused(ticker)

    def is_side_locked(
        self, ticker: str, side: SideName, now_ts: float | None = None,
    ) -> bool:
        """True if the side has a SideLock and it hasn't expired.

        Lazily expires locks past their auto_unlock_at — the read path
        is the only place that checks expiry, avoiding a separate cron.
        Caller passes now_ts to avoid a clock call when iterating; if
        omitted, time.time() is used.
        """
        lock = self._side_locks.get((ticker, side))
        if lock is None:
            return False
        if lock.auto_unlock_at is not None:
            import time as _t
            t = now_ts if now_ts is not None else _t.time()
            if t >= lock.auto_unlock_at:
                # Lazy unlock: expire the lock without taking the async lock
                # (idempotent — concurrent expires resolve to the same state).
                self._side_locks.pop((ticker, side), None)
                return False
        return True

    def get_side_lock(
        self, ticker: str, side: SideName,
    ) -> SideLock | None:
        """Returns the SideLock for inspection, or None if not locked.
        Does NOT auto-expire — use is_side_locked() for the runner's check."""
        return self._side_locks.get((ticker, side))

    def get_theo_override(self, ticker: str) -> TheoOverride | None:
        """Returns the operator-set theo override for `ticker`, or None.

        Called by the runner each cycle BEFORE the registered TheoProvider —
        if an override exists, it short-circuits the provider entirely.

        Honors `auto_clear_at`: an override past its expiry is treated
        as if absent (returns None). The actual record stays in the
        dict so the dashboard can still display "expired N min ago"
        for transparency.
        """
        ov = self._theo_overrides.get(ticker)
        if ov is None:
            return None
        if ov.auto_clear_at is not None:
            import time as _t
            if _t.time() >= ov.auto_clear_at:
                return None
        return ov

    def all_theo_overrides(self) -> dict[str, TheoOverride]:
        """All current overrides. Used by the dashboard's overview render."""
        return dict(self._theo_overrides)

    def all_side_locks(self) -> dict[tuple[str, SideName], SideLock]:
        """All current locks. Useful for the dashboard's locks-overview
        endpoint. Doesn't auto-expire — operator sees stale-but-not-yet-
        cleared locks for transparency."""
        return dict(self._side_locks)

    def all_events(self) -> set[str]:
        """Set of currently-active event tickers. Empty set = bot quotes
        nothing (no markets to iterate). The MultiEventTickerSource
        reads this each cycle."""
        return set(self._active_events)

    def has_event(self, ticker: str) -> bool:
        return ticker in self._active_events

    def get_knob(self, name: str) -> float | None:
        """Returns the current override for a knob, or None if no override."""
        return self._knob_overrides.get(name)

    def all_knobs(self) -> dict[str, float]:
        return dict(self._knob_overrides)

    def all_event_knobs(self) -> dict[str, dict[str, float]]:
        """Per-event knob override map: event_ticker → {name: value}."""
        return {
            ev: dict(knobs) for ev, knobs in self._event_knob_overrides.items()
        }

    def all_strike_knobs(self) -> dict[str, dict[str, float]]:
        """Per-strike knob override map: strike_ticker → {name: value}.
        Both-side overrides only; per-side via `all_strike_side_knobs()`."""
        return {
            t: dict(knobs) for t, knobs in self._strike_knob_overrides.items()
        }

    def all_strike_side_knobs(self) -> dict[str, dict[str, dict[str, float]]]:
        """Per-strike-per-side knob overrides:
            strike_ticker → {side: {name: value}}    side ∈ {"bid", "ask"}
        """
        out: dict[str, dict[str, dict[str, float]]] = {}
        for (ticker, side), knobs in self._strike_side_knob_overrides.items():
            out.setdefault(ticker, {})[side] = dict(knobs)
        return out

    def effective_knobs_for(
        self, ticker: str, side: str | None = None,
    ) -> dict[str, float]:
        """Return the merged knob dict for `ticker`, applying precedence:

            strike-side ("bid"|"ask")  >  strike (both)  >  event  >  global

        When `side` is "bid" or "ask", per-side strike overrides layer
        on top of the both-side overrides. When None or "both", only
        the both-side strike overrides apply (legacy behavior — what
        callers got before per-side overrides existed).

        Caller should fall back to the strategy's config default for
        any knob NOT in the returned dict.
        """
        merged: dict[str, float] = dict(self._knob_overrides)
        # Event prefix = everything before the last '-'. Same convention
        # the renderer uses (KXISMPMI-26MAY-50 → KXISMPMI-26MAY).
        event = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
        merged.update(self._event_knob_overrides.get(event, {}))
        merged.update(self._strike_knob_overrides.get(ticker, {}))
        if side in ("bid", "ask"):
            merged.update(
                self._strike_side_knob_overrides.get((ticker, side), {})
            )
        return merged

    def control_overrides_for_strategy(
        self, ticker: str | None = None,
    ) -> dict[str, Any]:
        """The dict passed to `strategy.quote(control_overrides=...)`.

        When `ticker` is given, returns the merged
        `effective_knobs_for(ticker)` so per-strike / per-event
        overrides take effect. When None (legacy / non-ticker callers
        like the runtime broadcast), returns just the global map.
        """
        if ticker is None:
            return dict(self._knob_overrides)
        return self.effective_knobs_for(ticker)

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for `GET /control/state`. Includes the
        version so dashboards can detect drift between polls."""
        return {
            "version": self._version,
            "kill_state": self._kill_state.value,
            "global_paused": self._pauses.global_paused,
            "paused_tickers": sorted(self._pauses.paused_tickers),
            "paused_sides": sorted(
                [list(t) for t in self._pauses.paused_sides]
            ),
            "knob_overrides": dict(self._knob_overrides),
            "side_locks": [
                {
                    "ticker": ticker, "side": side,
                    "mode": lock.mode, "reason": lock.reason,
                    "locked_at": lock.locked_at,
                    "auto_unlock_at": lock.auto_unlock_at,
                }
                for (ticker, side), lock in sorted(
                    self._side_locks.items(), key=lambda kv: kv[0],
                )
            ],
            "theo_overrides": [
                {
                    "ticker": ticker,
                    "yes_probability": ov.yes_probability,
                    "yes_cents": round(ov.yes_probability * 100, 1),
                    "confidence": ov.confidence,
                    "reason": ov.reason,
                    "set_at": ov.set_at,
                    "actor": ov.actor,
                    "mode": ov.mode,
                    "auto_clear_at": ov.auto_clear_at,
                }
                for ticker, ov in sorted(self._theo_overrides.items())
            ],
            "active_events": sorted(self._active_events),
            "event_knob_overrides": {
                ev: dict(knobs)
                for ev, knobs in sorted(self._event_knob_overrides.items())
            },
            "strike_knob_overrides": {
                t: dict(knobs)
                for t, knobs in sorted(self._strike_knob_overrides.items())
            },
            # Per-strike-per-side overrides. Schema:
            #   { ticker: { "bid": {name: value}, "ask": {name: value} } }
            # Sides only appear when at least one override is set on
            # them, so empty dict ≡ no per-side overrides anywhere.
            "strike_side_knob_overrides": self.all_strike_side_knobs(),
        }

    # ── Mutations (locked + version-bumped) ─────────────────────────

    async def pause_global(self) -> int:
        async with self._lock:
            self._pauses.global_paused = True
            return self._bump_version()

    async def resume_global(self) -> int:
        """Clears global pause. Does NOT clear ticker/side pauses (those
        survive — operator may want bot mostly running with specific
        scopes still paused)."""
        async with self._lock:
            self._pauses.global_paused = False
            return self._bump_version()

    async def pause_ticker(self, ticker: str) -> int:
        async with self._lock:
            self._pauses.paused_tickers.add(ticker)
            return self._bump_version()

    async def resume_ticker(self, ticker: str) -> int:
        async with self._lock:
            self._pauses.paused_tickers.discard(ticker)
            return self._bump_version()

    async def pause_side(self, ticker: str, side: SideName) -> int:
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        async with self._lock:
            self._pauses.paused_sides.add((ticker, side))
            return self._bump_version()

    async def resume_side(self, ticker: str, side: SideName) -> int:
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        async with self._lock:
            self._pauses.paused_sides.discard((ticker, side))
            return self._bump_version()

    async def kill(self) -> int:
        """Trip the kill switch. Strategy stops quoting; runner cancels
        all resting orders. Resume requires explicit /arm followed by
        /resume to make it deliberate."""
        async with self._lock:
            self._kill_state = KillState.KILLED
            self._pauses.global_paused = True
            return self._bump_version()

    async def arm(self) -> int:
        """Move from KILLED → ARMED. Operator acknowledges the kill is
        done being investigated. /resume after this returns to normal."""
        async with self._lock:
            if self._kill_state != KillState.KILLED:
                raise ValueError(
                    f"can only arm from KILLED state, current={self._kill_state.value}"
                )
            self._kill_state = KillState.ARMED
            return self._bump_version()

    async def resume_after_kill(self) -> int:
        """ARMED → OFF, also clears global pause (operator is ready to
        trade again). Per-ticker / per-side pauses survive."""
        async with self._lock:
            if self._kill_state != KillState.ARMED:
                raise ValueError(
                    f"can only resume from ARMED state, current={self._kill_state.value}; "
                    f"call /arm first"
                )
            self._kill_state = KillState.OFF
            self._pauses.global_paused = False
            return self._bump_version()

    async def set_knob(self, name: str, value: float) -> int:
        """Set a runtime knob override. Bounds-validated against
        ControlConfig.knob_bounds. Unknown knobs raise."""
        if name not in self._cfg.knob_bounds:
            raise ValueError(
                f"unknown knob {name!r}; permitted: {sorted(self._cfg.knob_bounds)}"
            )
        lo, hi = self._cfg.knob_bounds[name]
        v = float(value)
        if not (lo <= v <= hi):
            raise ValueError(
                f"knob {name}={v} out of bounds [{lo}, {hi}]"
            )
        async with self._lock:
            self._knob_overrides[name] = v
            return self._bump_version()

    async def clear_knob(self, name: str) -> int:
        """Remove an override; strategy reverts to its configured default
        on the next cycle."""
        async with self._lock:
            self._knob_overrides.pop(name, None)
            return self._bump_version()

    async def set_event_knob(
        self, event_ticker: str, name: str, value: float,
    ) -> int:
        """Set a knob override for one event. Layered between global
        and strike overrides — wins over global for strikes under
        this event prefix; loses to strike-level overrides on the
        same knob name.
        """
        if name not in self._cfg.knob_bounds:
            raise ValueError(
                f"unknown knob {name!r}; permitted: {sorted(self._cfg.knob_bounds)}"
            )
        lo, hi = self._cfg.knob_bounds[name]
        if value < lo or value > hi:
            raise ValueError(
                f"knob {name!r}={value} out of bounds [{lo}, {hi}]"
            )
        ev = event_ticker.strip().upper()
        if not ev:
            raise ValueError("event_ticker required")
        async with self._lock:
            self._event_knob_overrides.setdefault(ev, {})[name] = float(value)
            return self._bump_version()

    async def clear_event_knob(
        self, event_ticker: str, name: str | None = None,
    ) -> int:
        """Clear a single per-event knob (when `name` is given) or
        every per-event knob for that event (when `name` is None).
        Idempotent — bumps version even on no-op."""
        ev = event_ticker.strip().upper()
        async with self._lock:
            if name is None:
                self._event_knob_overrides.pop(ev, None)
            else:
                if ev in self._event_knob_overrides:
                    self._event_knob_overrides[ev].pop(name, None)
                    if not self._event_knob_overrides[ev]:
                        self._event_knob_overrides.pop(ev, None)
            return self._bump_version()

    async def set_strike_knob(
        self, ticker: str, name: str, value: float, side: str = "both",
    ) -> int:
        """Per-strike knob override.

        `side`: "both" (default — applies to bid AND ask), "bid", or "ask".
        Per-side overrides layer ON TOP of "both" — so an operator can
        set `dollars_per_side=5` for both sides AND `dollars_per_side=10`
        only on the bid. The bid then sees 10, the ask still sees 5.
        """
        if name not in self._cfg.knob_bounds:
            raise ValueError(
                f"unknown knob {name!r}; permitted: {sorted(self._cfg.knob_bounds)}"
            )
        lo, hi = self._cfg.knob_bounds[name]
        if value < lo or value > hi:
            raise ValueError(
                f"knob {name!r}={value} out of bounds [{lo}, {hi}]"
            )
        if not ticker or not ticker.strip():
            raise ValueError("ticker required")
        if side not in ("both", "bid", "ask"):
            raise ValueError(
                f"side must be 'both', 'bid', or 'ask'; got {side!r}"
            )
        async with self._lock:
            if side == "both":
                self._strike_knob_overrides.setdefault(ticker, {})[name] = float(value)
            else:
                key = (ticker, side)
                self._strike_side_knob_overrides.setdefault(key, {})[name] = float(value)
            return self._bump_version()

    async def clear_strike_knob(
        self, ticker: str, name: str | None = None, side: str = "both",
    ) -> int:
        """Clear a per-strike knob.

        `side`: "both" clears the both-side override; "bid"/"ask" clears
        only that side's override (the both-side override stays). When
        `name` is None, clears every knob for that (ticker, side).
        """
        if side not in ("both", "bid", "ask"):
            raise ValueError(
                f"side must be 'both', 'bid', or 'ask'; got {side!r}"
            )
        async with self._lock:
            if side == "both":
                if name is None:
                    self._strike_knob_overrides.pop(ticker, None)
                else:
                    if ticker in self._strike_knob_overrides:
                        self._strike_knob_overrides[ticker].pop(name, None)
                        if not self._strike_knob_overrides[ticker]:
                            self._strike_knob_overrides.pop(ticker, None)
            else:
                key = (ticker, side)
                if name is None:
                    self._strike_side_knob_overrides.pop(key, None)
                elif key in self._strike_side_knob_overrides:
                    self._strike_side_knob_overrides[key].pop(name, None)
                    if not self._strike_side_knob_overrides[key]:
                        self._strike_side_knob_overrides.pop(key, None)
            return self._bump_version()

    async def lock_side(
        self,
        ticker: str,
        side: SideName,
        *,
        reason: str = "",
        auto_unlock_at: float | None = None,
        mode: Literal["lock", "reduce_only"] = "lock",
    ) -> int:
        """Place a lock on a strike-side. The runner consults this each
        cycle and forces skip=True on locked sides.

        For Phase 2 only `mode="lock"` is supported (full skip);
        `mode="reduce_only"` is reserved for a future phase that adds
        position-aware skip semantics.
        """
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        if mode != "lock":
            raise ValueError(
                f"mode={mode!r} not supported in Phase 2; only 'lock' for now"
            )
        import time as _t
        async with self._lock:
            self._side_locks[(ticker, side)] = SideLock(
                mode=mode,
                reason=reason,
                locked_at=_t.time(),
                auto_unlock_at=auto_unlock_at,
            )
            return self._bump_version()

    async def set_theo_override(
        self,
        ticker: str,
        yes_probability: float,
        *,
        confidence: float = 1.0,
        reason: str,
        actor: str = "operator",
        mode: Literal["fixed", "track_mid"] = "fixed",
        auto_clear_seconds: float | None = None,
    ) -> int:
        """Plug a manual theo value for `ticker`. Strict bounds:
        `yes_probability ∈ [0,1]`, `confidence ∈ [0,1]`, reason non-empty
        (the dashboard enforces ≥4 chars; here we allow any non-empty
        for testability).

        Once set, the runner skips the TheoProvider for this ticker and
        feeds the strategy a TheoResult derived from these values. Use
        `clear_theo_override(ticker)` to undo.

        `mode="track_mid"` enables market-following mode: at quote time
        the runner computes theo from the orderbook mid each cycle.
        `yes_probability` is then unused but still validated for shape;
        a sensible placeholder (e.g. 0.5) is fine.
        """
        if not (0.0 <= yes_probability <= 1.0):
            raise ValueError(
                f"yes_probability must be in [0,1]; got {yes_probability}"
            )
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0,1]; got {confidence}"
            )
        if not reason or not reason.strip():
            raise ValueError("reason required for theo override")
        if mode not in ("fixed", "track_mid"):
            raise ValueError(
                f"mode must be 'fixed' or 'track_mid', got {mode!r}"
            )
        if auto_clear_seconds is not None:
            if auto_clear_seconds <= 0 or auto_clear_seconds > 86400 * 7:
                raise ValueError(
                    f"auto_clear_seconds must be in (0, 7d], got {auto_clear_seconds}"
                )
        import time as _t
        now = _t.time()
        auto_clear_at = (now + auto_clear_seconds) if auto_clear_seconds else None
        async with self._lock:
            self._theo_overrides[ticker] = TheoOverride(
                yes_probability=float(yes_probability),
                confidence=float(confidence),
                reason=reason.strip(),
                set_at=now,
                actor=actor,
                mode=mode,
                auto_clear_at=auto_clear_at,
            )
            return self._bump_version()

    async def clear_theo_override(self, ticker: str) -> int:
        """Remove the override for `ticker`. No-op if no override
        exists; still bumps version so dashboards see the action."""
        async with self._lock:
            self._theo_overrides.pop(ticker, None)
            return self._bump_version()

    async def unlock_side(self, ticker: str, side: SideName) -> int:
        """Remove a lock. No-op if no lock exists; still bumps version
        so dashboards see the operator action."""
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        async with self._lock:
            self._side_locks.pop((ticker, side), None)
            return self._bump_version()

    async def add_event(self, event_ticker: str) -> int:
        """Add an event to the active-events set. The
        MultiEventTickerSource yields markets under all active events
        each cycle, so this immediately makes the bot start tracking
        the new event's markets.

        Idempotent: re-adding an existing event is a no-op (still bumps
        version so dashboards re-render).
        """
        if not event_ticker or not event_ticker.strip():
            raise ValueError("event_ticker required")
        normalized = event_ticker.strip().upper()
        async with self._lock:
            self._active_events.add(normalized)
            return self._bump_version()

    async def remove_event(self, event_ticker: str) -> int:
        """Remove an event. No-op if not present; bumps version so
        dashboards re-render either way. Resting orders on the event's
        tickers are NOT cancelled here — that's the caller's
        responsibility (see the cancel_resting flag in the HTTP
        endpoint)."""
        if not event_ticker:
            raise ValueError("event_ticker required")
        normalized = event_ticker.strip().upper()
        async with self._lock:
            self._active_events.discard(normalized)
            return self._bump_version()

    # ── Internal ─────────────────────────────────────────────────────

    def _bump_version(self) -> int:
        """Must be called under self._lock. Returns the new version."""
        self._version += 1
        return self._version
