"""Shared state errors.

`MissingStateError` — required state has never been primed (e.g., no IV set
for this commodity yet). Raised instead of a silent fallback.

`StaleDataError` — state exists but is older than its staleness budget.
Raised instead of using stale data to compute a theo.
"""


class MissingStateError(LookupError):
    pass


class StaleDataError(RuntimeError):
    pass
