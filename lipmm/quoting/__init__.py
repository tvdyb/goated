"""Quoting strategy plugin system.

A `QuotingStrategy` takes the market context (theo, orderbook, our resting
state, time-to-settle) and returns a `QuotingDecision` — what to post on the
bid side, what to post on the ask side, and any state transitions worth
logging.

Different markets need different LIP-farming behaviors:

  - Mid-strikes near the money: defend against drag attacks → sticky machine
  - Deep wings: penny inside best with anti-spoofing, no sticky
  - Inverted books (best_bid > theo > best_ask, common near settlement):
    no-cross guard
  - Sports binary markets: less likely to face systematic drag attacks,
    different anti-spoofing tolerances

Strategies compose smaller building blocks (anti-spoofing, sizers, sticky,
robust-best filters) however they want, but the bot's core only sees the
QuotingStrategy interface.

Concrete strategies live in `lipmm.quoting.strategies/`. Default ships with
the framework (`DefaultLIPQuoting`); per-market strategies are dropped in
as additional files and selected by config at startup.
"""

from lipmm.quoting.base import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    QuotingStrategy,
    SideDecision,
)

__all__ = [
    "OrderbookSnapshot",
    "OurState",
    "QuotingDecision",
    "QuotingStrategy",
    "SideDecision",
]
