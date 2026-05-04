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
        "theo_tolerance_c": (0.0, 50.0),
        "max_distance_from_best": (0.0, 50.0),
        "dollars_per_side": (0.0, 100.0),
        # StickyDefenseQuoting knobs
        "sticky_min_distance_from_theo": (0.0, 50.0),
        "sticky_desert_jump_cents": (0.0, 50.0),
        # Risk gate knobs
        "max_notional_per_side_dollars": (0.0, 1000.0),
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

    def all_side_locks(self) -> dict[tuple[str, SideName], SideLock]:
        """All current locks. Useful for the dashboard's locks-overview
        endpoint. Doesn't auto-expire — operator sees stale-but-not-yet-
        cleared locks for transparency."""
        return dict(self._side_locks)

    def get_knob(self, name: str) -> float | None:
        """Returns the current override for a knob, or None if no override."""
        return self._knob_overrides.get(name)

    def all_knobs(self) -> dict[str, float]:
        return dict(self._knob_overrides)

    def control_overrides_for_strategy(self) -> dict[str, Any]:
        """The dict passed to `strategy.quote(control_overrides=...)`.

        Just an alias for `all_knobs()` today; isolating the call in case
        the format diverges later (e.g. nested per-strategy keys)."""
        return dict(self._knob_overrides)

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

    async def unlock_side(self, ticker: str, side: SideName) -> int:
        """Remove a lock. No-op if no lock exists; still bumps version
        so dashboards see the operator action."""
        if side not in ("bid", "ask"):
            raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")
        async with self._lock:
            self._side_locks.pop((ticker, side), None)
            return self._bump_version()

    # ── Internal ─────────────────────────────────────────────────────

    def _bump_version(self) -> int:
        """Must be called under self._lock. Returns the new version."""
        self._version += 1
        return self._version
