"""Sticky-quote state machine for LIP defense against drag attacks.

PRIVATE module — public interface is `lipmm.quoting.strategies.StickyDefenseQuoting`.
This file is the lifted state machine; the wrapping QuotingStrategy lives in
`sticky_defense.py`.

Implements a per-side hysteresis: races aggressively when pennied, then locks
in the aggressive position and only releases gradually after sustained 1.0x
mult AND theo stability. Defeats LIP-pump-and-relax attackers who rely on
forcing fast snap-back when they pull their stack.

States (per side, per strike):
- NORMAL:     standard quoting (whatever upstream computes)
- AGGRESSIVE: someone pennied us, race to floor (jump_cents inside best,
              bounded by min_distance_from_theo)
- RELAXING:   conditions met, slowly walking back to natural target over
              `relax_total_steps` cycles
- COOLDOWN:   safety circuit breaker if AGGRESSIVE persists too long

Transitions:
  NORMAL → AGGRESSIVE on pennying detection
  AGGRESSIVE → RELAXING when N consecutive cycles at 1.0x AND theo stable
  AGGRESSIVE → COOLDOWN if duration > max_aggressive_seconds
  RELAXING → AGGRESSIVE on re-pennying
  RELAXING → NORMAL when relax_step >= total_steps OR gap closed
  COOLDOWN → NORMAL after cooldown_seconds
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


StateName = Literal["NORMAL", "AGGRESSIVE", "RELAXING", "COOLDOWN"]


@dataclass
class StickyConfig:
    """Configuration for the sticky-quote state machine."""

    # When pennying, how many cents to jump inside best (default 5)
    desert_jump_cents: int = 5
    # Floor on distance from theo: never quote within this many cents of theo
    min_distance_from_theo: int = 15
    # Cycles at 1.0x mult required before unlocking (default 15 ≈ 45s at 3s cycle)
    snapshots_at_1x_required: int = 15
    # Theo can't drift more than this between aggressive entry and relax start
    theo_stability_cents: float = 2.0
    # Theo range (max - min) over the at-1x buffer must be under this
    theo_range_cents: float = 3.0
    # How many discrete relax steps to walk back to natural target
    relax_total_steps: int = 10
    # Safety circuit breaker: max time in AGGRESSIVE before cooldown
    max_aggressive_duration_seconds: float = 300.0
    # Cooldown duration before re-engaging
    cooldown_seconds: float = 600.0


@dataclass
class SideState:
    state: StateName = "NORMAL"
    aggressive_entered_at: float | None = None
    theo_at_aggressive_entry: float | None = None
    theo_buffer: deque[float] = field(default_factory=lambda: deque(maxlen=15))
    consecutive_1x_count: int = 0
    relax_start_price: int | None = None
    relax_initial_target: int | None = None
    relax_min_step: float | None = None
    relax_step: int = 0
    cooldown_until: float | None = None
    current_price: int = 0  # last quote actually issued


class StickyQuoter:
    """Wraps natural quoting logic with a per-side sticky state machine.

    Usage:
        sq = StickyQuoter(StickyConfig())
        actual_price = sq.compute(
            ticker="...", side="ask", natural_target=74,
            best_other_side=75, our_current=74, fair=7,
            now=time.time(),
        )
    """

    def __init__(self, cfg: StickyConfig | None = None) -> None:
        self._cfg = cfg or StickyConfig()
        self._states: dict[tuple[str, str], SideState] = {}
        # Resize the theo buffer to match required sample count
        self._buffer_size = self._cfg.snapshots_at_1x_required

    def _get_state(self, ticker: str, side: str) -> SideState:
        key = (ticker, side)
        if key not in self._states:
            st = SideState()
            st.theo_buffer = deque(maxlen=self._buffer_size)
            self._states[key] = st
        return self._states[key]

    def state_of(self, ticker: str, side: str) -> StateName:
        return self._get_state(ticker, side).state

    def snapshot(self, ticker: str, side: str) -> dict:
        """Return a serializable snapshot of (ticker, side) state.

        This is the public contract for state introspection. Callers (e.g. the
        decision logger in lip_mode.py) should use this instead of reaching
        into `_get_state(...)` and accessing private fields, so that changes
        to SideState's internal layout don't silently break consumers.

        Fields:
          - state: current state name (NORMAL/AGGRESSIVE/RELAXING/COOLDOWN)
          - consecutive_1x_count: cycles at 1.0x mult
          - current_price: tracked desired price (int cents)
          - relax_step: position within relaxation walk (0 if not relaxing)
          - aggressive_entered_at: raw float unix timestamp or None
          - theo_buffer: list (NOT deque) of recent theo values; copy is safe
          - cooldown_until: raw float unix timestamp or None
        """
        st = self._get_state(ticker, side)
        return {
            "state": st.state,
            "consecutive_1x_count": int(st.consecutive_1x_count),
            "current_price": int(st.current_price),
            "relax_step": int(st.relax_step),
            "aggressive_entered_at": st.aggressive_entered_at,
            "theo_buffer": list(st.theo_buffer),
            "cooldown_until": st.cooldown_until,
        }

    def compute(
        self,
        *,
        ticker: str,
        side: str,                  # "ask" or "bid"
        natural_target: int,        # what active/desert logic would post (int cents)
        best_relevant: int,         # current best on this side (int cents)
        our_current: int,           # what we're currently posted at, 0 if none
        fair: float,                # current theo on this side, in cents
        now: float,                 # current timestamp (seconds)
        min_distance_from_theo_override: int | None = None,
    ) -> tuple[int, StateName, list[dict]]:
        """Return (price_to_post, state_name, transitions).

        `transitions` is a list of dicts, one per state change in this call.
        Each dict has at minimum {"from": StateName, "to": StateName, "reason": dict}
        where the reason dict carries kind-specific structured data (durations,
        theo buffer ranges, gap-closed flags, etc.). Empty list if no transition
        occurred this cycle.

        Conventions:
          - For "ask" side: lower price = more aggressive. Pennying = best dropped.
          - For "bid" side: higher price = more aggressive. Pennying = best rose.
          - natural_target is upstream's "I would post here in normal market"
          - best_relevant is current best on the side we're on
          - fair is theo for the side held (theo_yes for ask side selling Yes, etc.)
          - min_distance_from_theo_override: optional per-call widening of the
            anti-spoofing safe zone. None → use cfg.min_distance_from_theo.
            Wrapping strategies (StickyDefenseQuoting) use this to scale
            protection by theo confidence without mutating the machine's cfg.

        First call for a (ticker, side) initializes state in NORMAL.
        """
        transitions: list[dict] = []
        if side not in ("ask", "bid"):
            raise ValueError(f"side must be 'ask' or 'bid', got {side!r}")
        st = self._get_state(ticker, side)

        # Sign convention: side_sign=+1 for ask (relaxing UP increases price),
        # -1 for bid (relaxing DOWN decreases price).
        side_sign = 1 if side == "ask" else -1

        # --- Initialize on first call ---
        if st.current_price == 0 and our_current == 0:
            st.current_price = natural_target
            return natural_target, st.state, transitions

        # If our_current was set externally (e.g., from API truth) sync state
        if our_current > 0 and st.current_price == 0:
            st.current_price = our_current

        # --- COOLDOWN handling ---
        if st.state == "COOLDOWN":
            if st.cooldown_until is None or now >= st.cooldown_until:
                logger.info(
                    "STICKY TRANSITION %s %s: COOLDOWN -> NORMAL "
                    "(current_price=%d, fair=%.2f, natural_target=%d)",
                    ticker, side, st.current_price, fair, natural_target,
                )
                transitions.append({
                    "from": "COOLDOWN", "to": "NORMAL",
                    "reason": {
                        "kind": "cooldown_expired",
                        "natural_target": int(natural_target),
                        "fair": float(fair),
                    },
                })
                st.state = "NORMAL"
                st.cooldown_until = None
                st.current_price = natural_target
                return natural_target, "NORMAL", transitions
            # Stay in cooldown — return 0 to signal "don't post"
            return 0, "COOLDOWN", transitions

        # --- Detect pennying ---
        # For ask: pennied if best dropped below where we'd want to be
        # natural_target uses desert logic which already pennies inside best,
        # so if natural_target moved AGGRESSIVE direction vs our_current, we're pennied
        natural_more_aggressive = (
            (side == "ask" and natural_target < st.current_price) or
            (side == "bid" and natural_target > st.current_price)
        )

        # --- AGGRESSIVE entry / continuation on pennying ---
        if natural_more_aggressive:
            # Compute aggressive target: jump inside best by desert_jump_cents,
            # bounded by min_distance_from_theo (or override for this call)
            jump = self._cfg.desert_jump_cents
            min_dist = (
                min_distance_from_theo_override
                if min_distance_from_theo_override is not None
                else self._cfg.min_distance_from_theo
            )

            if side == "ask":
                jump_target = best_relevant - jump
                theo_floor = int(round(fair + min_dist))
                aggressive_price = max(jump_target, theo_floor)
            else:  # bid
                jump_target = best_relevant + jump
                theo_ceiling = int(round(fair - min_dist))
                aggressive_price = min(jump_target, theo_ceiling)

            # Clamp to sane range
            aggressive_price = max(1, min(99, aggressive_price))

            if st.state in ("NORMAL", "RELAXING"):
                logger.info(
                    "STICKY TRANSITION %s %s: %s -> AGGRESSIVE "
                    "(best=%dc, jump_target=%dc, current=%dc -> %dc, "
                    "fair=%.2f, cycle_count=%d)",
                    ticker, side, st.state, best_relevant, jump_target,
                    st.current_price, aggressive_price, fair,
                    st.consecutive_1x_count,
                )
                transitions.append({
                    "from": st.state, "to": "AGGRESSIVE",
                    "reason": {
                        "kind": "pennied",
                        "best_relevant": int(best_relevant),
                        "jump_target": int(jump_target),
                        "prev_price": int(st.current_price),
                        "new_price": int(aggressive_price),
                        "fair": float(fair),
                    },
                })
                st.state = "AGGRESSIVE"
                st.aggressive_entered_at = now
                st.theo_at_aggressive_entry = fair
                st.theo_buffer.clear()
                st.consecutive_1x_count = 0
                st.relax_step = 0
                st.relax_start_price = None

            st.current_price = aggressive_price
            return aggressive_price, "AGGRESSIVE", transitions

        # --- AGGRESSIVE: not pennied this cycle, accumulate at-1x cycles ---
        if st.state == "AGGRESSIVE":
            # Circuit breaker
            if (
                st.aggressive_entered_at is not None
                and (now - st.aggressive_entered_at) > self._cfg.max_aggressive_duration_seconds
            ):
                duration_s = now - st.aggressive_entered_at
                logger.warning(
                    "STICKY TRANSITION %s %s: AGGRESSIVE -> COOLDOWN "
                    "(duration=%.1fs, max=%.0fs, current_price=%d, fair=%.2f, "
                    "cycle_count=%d)",
                    ticker, side, duration_s,
                    self._cfg.max_aggressive_duration_seconds,
                    st.current_price, fair, st.consecutive_1x_count,
                )
                transitions.append({
                    "from": "AGGRESSIVE", "to": "COOLDOWN",
                    "reason": {
                        "kind": "max_duration_exceeded",
                        "duration_s": round(duration_s, 1),
                        "max_duration_s": float(self._cfg.max_aggressive_duration_seconds),
                        "current_price": int(st.current_price),
                        "fair": float(fair),
                        "cycle_count": int(st.consecutive_1x_count),
                    },
                })
                st.state = "COOLDOWN"
                st.cooldown_until = now + self._cfg.cooldown_seconds
                return 0, "COOLDOWN", transitions

            # Check if currently at 1.0x: our_current is the best on our side
            at_1x = our_current > 0 and our_current == best_relevant
            if at_1x:
                st.consecutive_1x_count += 1
            else:
                st.consecutive_1x_count = 0

            # Track theo over recent cycles
            st.theo_buffer.append(fair)

            # Conditions to transition to RELAXING
            buffer_full = len(st.theo_buffer) >= self._cfg.snapshots_at_1x_required
            cycles_ok = st.consecutive_1x_count >= self._cfg.snapshots_at_1x_required
            theo_anchor_ok = (
                st.theo_at_aggressive_entry is not None
                and abs(fair - st.theo_at_aggressive_entry) < self._cfg.theo_stability_cents
            )
            theo_range_ok = True
            if buffer_full:
                tb_max = max(st.theo_buffer)
                tb_min = min(st.theo_buffer)
                theo_range_ok = (tb_max - tb_min) < self._cfg.theo_range_cents

            if cycles_ok and theo_anchor_ok and theo_range_ok and buffer_full:
                # Enter RELAXING
                gap = (natural_target - st.current_price) * side_sign
                tb_min = min(st.theo_buffer) if st.theo_buffer else fair
                tb_max = max(st.theo_buffer) if st.theo_buffer else fair
                duration_s = (now - st.aggressive_entered_at) if st.aggressive_entered_at else 0.0
                if gap <= 0:
                    # Already at or past natural — go straight to NORMAL
                    logger.info(
                        "STICKY TRANSITION %s %s: AGGRESSIVE -> NORMAL "
                        "(gap_closed, current_price=%d, natural=%d, fair=%.2f, "
                        "duration=%.1fs)",
                        ticker, side, st.current_price, natural_target, fair,
                        duration_s,
                    )
                    transitions.append({
                        "from": "AGGRESSIVE", "to": "NORMAL",
                        "reason": {
                            "kind": "gap_closed",
                            "current_price": int(st.current_price),
                            "natural_target": int(natural_target),
                            "fair": float(fair),
                            "duration_s": round(duration_s, 1),
                        },
                    })
                    st.state = "NORMAL"
                    st.current_price = natural_target
                    return natural_target, "NORMAL", transitions

                logger.info(
                    "STICKY TRANSITION %s %s: AGGRESSIVE -> RELAXING "
                    "(start=%dc, target=%dc, gap=%d, steps=%d, "
                    "theo_buf_min=%.2f, theo_buf_max=%.2f, fair=%.2f, "
                    "duration=%.1fs, cycle_count=%d)",
                    ticker, side, st.current_price, natural_target, gap,
                    self._cfg.relax_total_steps,
                    tb_min, tb_max, fair, duration_s,
                    st.consecutive_1x_count,
                )
                transitions.append({
                    "from": "AGGRESSIVE", "to": "RELAXING",
                    "reason": {
                        "kind": "gates_met",
                        "duration_s": round(duration_s, 1),
                        "theo_buf_min": round(float(tb_min), 2),
                        "theo_buf_max": round(float(tb_max), 2),
                        "start_price": int(st.current_price),
                        "target": int(natural_target),
                        "gap": int(gap),
                        "total_steps": int(self._cfg.relax_total_steps),
                        "cycle_count": int(st.consecutive_1x_count),
                    },
                })
                st.state = "RELAXING"
                st.relax_start_price = st.current_price
                st.relax_initial_target = natural_target
                st.relax_min_step = abs(gap) / self._cfg.relax_total_steps
                st.relax_step = 0
                # Fall through to RELAXING handling below

            else:
                # Stay AGGRESSIVE; price unchanged from last cycle
                return st.current_price, "AGGRESSIVE", transitions

        # --- RELAXING: walk back gradually ---
        if st.state == "RELAXING":
            st.relax_step += 1
            remaining = max(1, self._cfg.relax_total_steps - st.relax_step + 1)
            current_target = natural_target  # recomputed fresh each cycle
            gap = (current_target - st.current_price) * side_sign

            if gap <= 0:
                logger.info(
                    "STICKY TRANSITION %s %s: RELAXING -> NORMAL "
                    "(target_moved_past, current_price=%d, target=%d, "
                    "fair=%.2f, relax_step=%d)",
                    ticker, side, st.current_price, current_target, fair,
                    st.relax_step,
                )
                transitions.append({
                    "from": "RELAXING", "to": "NORMAL",
                    "reason": {
                        "kind": "target_moved_past",
                        "current_price": int(st.current_price),
                        "target": int(current_target),
                        "fair": float(fair),
                        "relax_step": int(st.relax_step),
                    },
                })
                st.state = "NORMAL"
                st.current_price = current_target
                return current_target, "NORMAL", transitions

            ideal_step = gap / remaining
            min_step = st.relax_min_step or 1.0
            actual_step = max(min_step, ideal_step, 1.0)
            new_price = st.current_price + int(round(actual_step)) * side_sign

            # Clamp so we don't overshoot moving target
            if side == "ask":
                new_price = min(new_price, current_target)
            else:
                new_price = max(new_price, current_target)
            new_price = max(1, min(99, new_price))

            st.current_price = new_price

            if st.relax_step >= self._cfg.relax_total_steps or new_price == current_target:
                logger.info(
                    "STICKY TRANSITION %s %s: RELAXING -> NORMAL "
                    "(completed, relax_step=%d/%d, price=%dc, target=%d, fair=%.2f)",
                    ticker, side, st.relax_step, self._cfg.relax_total_steps,
                    new_price, current_target, fair,
                )
                transitions.append({
                    "from": "RELAXING", "to": "NORMAL",
                    "reason": {
                        "kind": "completed",
                        "relax_step": int(st.relax_step),
                        "total_steps": int(self._cfg.relax_total_steps),
                        "final_price": int(new_price),
                        "target": int(current_target),
                        "fair": float(fair),
                    },
                })
                st.state = "NORMAL"

            return new_price, st.state, transitions

        # --- NORMAL fall-through: just pass through natural_target ---
        st.current_price = natural_target
        return natural_target, "NORMAL", transitions

    def reset(self, ticker: str | None = None) -> None:
        """Clear state. If ticker is given, only that ticker's sides; else all."""
        if ticker is None:
            self._states.clear()
        else:
            for key in list(self._states.keys()):
                if key[0] == ticker:
                    del self._states[key]
