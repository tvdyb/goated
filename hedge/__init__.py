"""IBKR hedge leg for Kalshi commodity monthly market-making.

Provides:
- IBKRClient: async wrapper around IB Gateway via ib_insync
- aggregate_delta: compute portfolio delta from Kalshi positions + RND
- compute_hedge_size: convert dollar-delta to futures contracts
- HedgeTrigger: threshold-triggered hedge execution with cooldown
"""

from hedge.delta_aggregator import aggregate_delta
from hedge.sizer import compute_hedge_size
from hedge.trigger import HedgeTrigger

__all__ = [
    "aggregate_delta",
    "compute_hedge_size",
    "HedgeTrigger",
]
