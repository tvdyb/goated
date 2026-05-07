"""Truflation EV index forward sources.

The TruEvForwardSource polls yfinance for the four cleanly-available
EV-basket commodities (Cu, Li, Pd, Pt) on a schedule. Used by
`lipmm.theo.providers.truev.TruEVTheoProvider` to compute today's
basket value and price KXTRUEV-* binary contracts.

Phase 2 will add LME nickel and Fastmarkets cobalt feeds.
"""

from feeds.truflation.forward import TruEvForwardSource, TRUEV_PHASE1_SYMBOLS

__all__ = ["TruEvForwardSource", "TRUEV_PHASE1_SYMBOLS"]
