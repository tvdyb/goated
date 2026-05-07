"""Truflation EV index forward sources.

The TruEvForwardSource polls live commodity prices for the EV-basket
metals. Backends:
  - yfinance for HG=F, LIT, NICK.L, PA=F, PL=F (5 daily-history
    yfinance tickers)
  - TradingEconomics scrape for cobalt (live spot only — no historicals)

Used by `lipmm.theo.providers.truev.TruEVTheoProvider` to compute
today's basket value and price KXTRUEV-* binary contracts.
"""

from feeds.truflation.forward import (
    COBALT_TE,
    TRUEV_PHASE1_SYMBOLS,
    TRUEV_YFINANCE_SYMBOLS,
    TruEvForwardSource,
)

__all__ = [
    "COBALT_TE",
    "TRUEV_PHASE1_SYMBOLS",
    "TRUEV_YFINANCE_SYMBOLS",
    "TruEvForwardSource",
]
