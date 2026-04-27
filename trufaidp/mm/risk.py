"""Pre-trade risk gates and kill-switch state.

The MM loop calls `RiskGate.check()` once per cycle. It returns one
of three states:

  OK            — quotes flow normally
  PULL_ALL      — cancel all open orders and stop quoting (theo
                  unstable, settlement imminent, agg cap breach)
  PASSIVE_ONLY  — cancel both-side quoting; only quote the side that
                  reduces inventory (per-strike limit hit somewhere)

Triggers:
  * Aggregate abs(yes-equivalent) across strikes >= aggregate cap.
  * Time-to-settlement <= settlement_pull_seconds.
  * Theo jumped >= theo_jump_kill_cents between consecutive ticks
    (likely stale feed or basket repricing event — pause briefly).
  * Any HTTP / placement error count >= error_kill_threshold per
    minute.

`PULL_ALL` is sticky for `cooldown_seconds` once tripped, so a brief
theo glitch can't immediately re-enable quoting.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class RiskState(str, Enum):
    OK = "ok"
    PASSIVE_ONLY = "passive_only"
    PULL_ALL = "pull_all"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    aggregate_position_limit: int = 300
    per_strike_position_limit: int = 50
    settlement_pull_seconds: float = 5 * 60.0      # pull 5 min before settlement
    theo_jump_kill_cents: int = 8                  # >= 8c move in one tick → pause
    cooldown_seconds: float = 30.0
    error_kill_threshold: int = 5                  # 5 errors / 60s window


@dataclass(slots=True)
class RiskGate:
    cfg: RiskConfig
    _last_theo_cents: dict[str, int] = field(default_factory=dict)
    _error_times: deque = field(default_factory=lambda: deque(maxlen=64))
    _pull_until_ts: float = 0.0

    def record_error(self) -> None:
        self._error_times.append(time.time())

    def _recent_error_count(self) -> int:
        cutoff = time.time() - 60.0
        while self._error_times and self._error_times[0] < cutoff:
            self._error_times.popleft()
        return len(self._error_times)

    def check(
        self,
        *,
        seconds_to_settlement: float,
        positions_by_strike: dict[str, int],
        theos_by_strike: dict[str, int],
    ) -> RiskState:
        now = time.time()

        if now < self._pull_until_ts:
            return RiskState.PULL_ALL
        if seconds_to_settlement <= self.cfg.settlement_pull_seconds:
            return RiskState.PULL_ALL
        if self._recent_error_count() >= self.cfg.error_kill_threshold:
            self._pull_until_ts = now + self.cfg.cooldown_seconds
            return RiskState.PULL_ALL

        for ticker, theo in theos_by_strike.items():
            prev = self._last_theo_cents.get(ticker)
            if prev is not None and abs(theo - prev) >= self.cfg.theo_jump_kill_cents:
                self._pull_until_ts = now + self.cfg.cooldown_seconds
                self._last_theo_cents[ticker] = theo
                return RiskState.PULL_ALL
            self._last_theo_cents[ticker] = theo

        agg = sum(abs(p) for p in positions_by_strike.values())
        if agg >= self.cfg.aggregate_position_limit:
            return RiskState.PASSIVE_ONLY

        if any(abs(p) >= self.cfg.per_strike_position_limit for p in positions_by_strike.values()):
            return RiskState.PASSIVE_ONLY

        return RiskState.OK
