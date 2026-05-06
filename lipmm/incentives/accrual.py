"""In-memory LIP earnings accrual — running estimate of $ earned.

Each runner cycle, for every strike with a live `pool_share × pool`
rate, we accrue an estimate of what we'd have earned if we held that
share for the cycle's duration. Sum across cycles → running tally
per strike. Sum strikes → per-event tally. Sum events → grand total.

These are estimates, not Kalshi-confirmed payouts. They're useful as
a real-time progress indicator; reconciliation against actual payouts
is a separate offline concern.

Math (per cycle, per strike):
    accrual_dollars = pool_share × period_reward × (cycle_dt / period_duration)

This is the integral of the per-second rate (pool_share × pool /
period_s) over `cycle_dt` seconds. If pool_share stays steady through
the entire period, summing N×period_duration_s/cycle_dt cycles gives
exactly pool_share × pool — the expected payout. In practice
pool_share fluctuates, so the running sum tracks how much we've
accrued under the *observed* time-series of shares.

State is in-memory (resets on bot restart). Persistence across
restarts is a future enhancement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time


@dataclass
class _StrikeAccrual:
    earnings: float = 0.0
    cycles: int = 0
    started_at: float = field(default_factory=time.time)
    last_updated_at: float = 0.0
    last_pool_share: float = 0.0


def _event_ticker_of(strike: str) -> str:
    return strike.rsplit("-", 1)[0] if "-" in strike else strike


class EarningsAccrual:
    """Running tally of LIP earnings, updated once per runner cycle.

    Usage:
      acc = EarningsAccrual()
      # Each cycle, after computing per-strike pool_share:
      acc.track(ticker, pool_share, period_reward_dollars, period_duration_s, cycle_dt_s)
      # On render:
      acc.snapshot()  # → dict for the dashboard
    """

    def __init__(self) -> None:
        self._strikes: dict[str, _StrikeAccrual] = {}
        self._started_at: float = time.time()

    def track(
        self,
        ticker: str,
        pool_share: float,
        period_reward_dollars: float,
        period_duration_s: float,
        cycle_dt_s: float,
        *,
        now_ts: float | None = None,
    ) -> None:
        """Accrue this cycle's contribution for one strike."""
        if not ticker or pool_share <= 0 or period_reward_dollars <= 0:
            return
        if period_duration_s <= 0 or cycle_dt_s <= 0:
            return
        accrual = pool_share * period_reward_dollars * (
            cycle_dt_s / period_duration_s
        )
        if accrual <= 0:
            return
        ts = now_ts if now_ts is not None else time.time()
        sa = self._strikes.get(ticker)
        if sa is None:
            sa = _StrikeAccrual(started_at=ts)
            self._strikes[ticker] = sa
        sa.earnings += accrual
        sa.cycles += 1
        sa.last_updated_at = ts
        sa.last_pool_share = pool_share

    def per_strike(self) -> dict[str, float]:
        return {t: sa.earnings for t, sa in self._strikes.items()}

    def per_event(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for t, sa in self._strikes.items():
            ev = _event_ticker_of(t)
            out[ev] = out.get(ev, 0.0) + sa.earnings
        return out

    def total(self) -> float:
        return sum(sa.earnings for sa in self._strikes.values())

    def snapshot(self) -> dict:
        """Operator-facing snapshot for dashboard consumption."""
        now = time.time()
        return {
            "started_at": self._started_at,
            "elapsed_s": now - self._started_at,
            "total_dollars": self.total(),
            "per_strike": self.per_strike(),
            "per_event": self.per_event(),
        }
