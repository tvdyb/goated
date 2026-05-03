"""Theo provider plugin system for LIP market making.

The bot quotes against `theo` (theoretical fair Yes-probability) on every
strike. Different markets need wildly different theo computations:

  - Continuous commodity markets (soy, corn): Black-76 with forward + vol
  - Binary sports markets: aggregated sportsbook lines
  - Political/election markets: poll aggregators with Bayesian decay
  - Weather, macro, policy: each their own data source

This module defines a uniform protocol (`TheoProvider`) and a registry
(`TheoRegistry`) that routes ticker → provider by Kalshi series prefix.
Concrete provider implementations live in `lipmm/theo/providers/` and
are interchangeable: the bot's pricing loop, sticky machine, decision
logger, and dashboard all consume `TheoResult` without knowing which
provider produced it.

Adding a new market type means writing one new file in `providers/` and
registering it at startup. Nothing in the core template changes.
"""

from lipmm.theo.base import TheoProvider, TheoResult
from lipmm.theo.registry import TheoRegistry

__all__ = ["TheoProvider", "TheoResult", "TheoRegistry"]
