"""Liquidity-incentive program awareness for lipmm bots.

Surfaces Kalshi's `/incentive_programs` endpoint (or any future
exchange's equivalent) so the operator can see — per market — what
liquidity-incentive programs are running, how long until they expire,
and the parameters that drive expected payout (period reward, discount
factor, target size).

Architecture:
  - `IncentiveProgram` — frozen dataclass mirroring the API row shape
    plus convenience properties (period_reward_dollars,
    target_size_contracts, time_remaining_s, is_active).
  - `IncentiveProvider` Protocol — `async list_active() -> list[IncentiveProgram]`.
  - `KalshiIncentiveProvider` — concrete implementation hitting the
    public, unauthenticated `/trade-api/v2/incentive_programs` endpoint.
  - `IncentiveCache` — async lifecycle wrapper that refreshes the
    snapshot on a schedule (hourly default), tolerates fetch failures
    by keeping the last good snapshot, and exposes a per-ticker lookup.
"""

from lipmm.incentives.base import IncentiveProgram, IncentiveProvider
from lipmm.incentives.cache import IncentiveCache
from lipmm.incentives.kalshi import KalshiIncentiveProvider

__all__ = [
    "IncentiveCache",
    "IncentiveProgram",
    "IncentiveProvider",
    "KalshiIncentiveProvider",
]
