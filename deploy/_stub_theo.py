"""StubTheoProvider — safe-by-default theo for new-market deployment.

Returns `TheoResult(confidence=0.0)` for every ticker so the bot won't
quote anything until the operator sets per-ticker overrides via the
dashboard's "Theo overrides" panel (Phase 7).

Why this is the right v1 for new markets:

- The lipmm framework only ships GBM-commodity theo; it has no math
  for ISM PMI, sports, politics, etc.
- Operators usually want to validate plumbing (auth, ticker discovery,
  control plane, dashboard, decision logging) before plugging in real
  theo math. A stub at confidence=0.0 means a misconfigured deploy
  can't accidentally place trades — the worst outcome is "bot sat
  there doing nothing".
- Once operator's algorithmic theo is ready, swap this for a real
  `TheoProvider` implementation. Nothing else in the deploy script
  changes.
"""

from __future__ import annotations

from lipmm.theo import TheoProvider, TheoResult


class StubTheoProvider(TheoProvider):
    """No-op theo: every ticker returns confidence=0.0.

    The default `DefaultLIPQuoting` config skips any side whose
    `theo.confidence < min_theo_confidence` (default 0.5), so this
    provider effectively halts quoting at the strategy layer. The
    operator drives quoting per-strike via dashboard overrides until
    they swap in a real provider.
    """

    def __init__(self, series_prefix: str) -> None:
        self.series_prefix = series_prefix

    async def warmup(self) -> None:
        """No-op — nothing to initialize."""

    async def shutdown(self) -> None:
        """No-op — nothing to flush."""

    async def theo(self, ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=0.5,
            confidence=0.0,
            computed_at=0.0,
            source="stub:no-theo",
            extras={"hint": "set theo override via dashboard"},
        )
