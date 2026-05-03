"""Concrete QuotingStrategy implementations.

Drop one file per strategy. The framework's core never has to change to
add a new strategy.

Conventions:
  - Strategy class name suffixed with `Quoting` (e.g. `DefaultLIPQuoting`,
    `StickyDefenseQuoting`, `LockToTheoQuoting`).
  - Each strategy file has a `Config` dataclass for its tunables, separate
    from the strategy class itself, so config can be loaded from YAML and
    passed in.
"""

from lipmm.quoting.strategies.default import (
    DefaultLIPQuoting,
    DefaultLIPQuotingConfig,
)
from lipmm.quoting.strategies.sticky_defense import (
    StickyDefenseConfig,
    StickyDefenseQuoting,
    default_sticky,
)

__all__ = [
    "DefaultLIPQuoting",
    "DefaultLIPQuotingConfig",
    "StickyDefenseConfig",
    "StickyDefenseQuoting",
    "default_sticky",
]
