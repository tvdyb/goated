"""Trading Economics generic spot-price scraper.

TE's public commodity pages embed a JSON blob like:

    "symbol":"LN1:COM"...,"last":19085.500000000000,"name":"Nickel"

We anchor on the symbol prefix when known, falling back to the
commodity name. Returns the current "last" price in whatever unit TE
reports (typically $/tonne for metals, ¢/bushel for grains, etc.).

Caller is responsible for unit conversion / sanity bounds. Cache TTL
is 60s by default — TE updates aren't real-time and the page is HTML
(rendering ~400 KB), so hammering once a minute is plenty.

Live theo only — TE shut down their free historical-data API in early
2026, so this module gives spot at *now*, not a time series. For
backtest, see the per-commodity yfinance proxies in
feeds/truflation/forward.py.

Generalization of feeds/tradingeconomics/soybean.py.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class TeSpotConfig:
    """One commodity's scrape config.

    Args:
      slug:           URL slug under /commodity/ (e.g. "nickel", "cobalt").
      symbol_prefix:  Expected `"symbol":"…"` value to anchor the regex on
                      (e.g. "LN1:COM" for nickel). Avoids picking up other
                      symbols on the page.
      sanity_lo:      Reject scraped prices below this (paranoia / parser bug).
      sanity_hi:      Reject scraped prices above this.
    """
    slug: str
    symbol_prefix: str
    sanity_lo: float
    sanity_hi: float

    @property
    def url(self) -> str:
        return f"https://tradingeconomics.com/commodity/{self.slug}"


# Built-in configs for the metals we care about.
TE_NICKEL = TeSpotConfig(
    slug="nickel", symbol_prefix="LN1:COM",
    sanity_lo=5_000.0, sanity_hi=80_000.0,   # $/tonne, historical range
)
TE_COBALT = TeSpotConfig(
    slug="cobalt", symbol_prefix="LCO1:COM",
    sanity_lo=10_000.0, sanity_hi=200_000.0,
)
TE_LITHIUM = TeSpotConfig(
    slug="lithium", symbol_prefix="LC:COM",
    sanity_lo=10_000.0, sanity_hi=1_000_000.0,  # CNY/T, very wide
)


# Per-config cache: {slug: (price, fetched_at_ts)}
_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL_S = 60.0


def _build_regex(symbol_prefix: str) -> re.Pattern:
    """Anchor: `"symbol":"<prefix>"…"last":NNN`. The 0-1500 char window
    between fields tolerates TE's JSON layout drift."""
    escaped = re.escape(symbol_prefix)
    return re.compile(
        r'"symbol"\s*:\s*"' + escaped + r'"[^{}]{0,1500}?"last"\s*:\s*([0-9]+\.?[0-9]*)',
        re.DOTALL,
    )


def get_te_spot(
    cfg: TeSpotConfig,
    *,
    timeout_s: float = 10.0,
    use_cache: bool = True,
    client: httpx.Client | None = None,
) -> float | None:
    """Fetch current spot for one commodity. Returns None on any
    failure (network, parse, sanity). Cached for 60s by default.

    Pass `client` to share an httpx.Client across multiple calls (one
    less TLS handshake per refresh). Otherwise creates a per-call
    client.
    """
    now = time.time()
    cached = _cache.get(cfg.slug)
    if use_cache and cached is not None and (now - cached[1]) < _CACHE_TTL_S:
        return cached[0]

    own_client = client is None
    try:
        if own_client:
            client = httpx.Client(timeout=timeout_s, follow_redirects=True)
        try:
            r = client.get(cfg.url, headers={"User-Agent": _USER_AGENT})
        finally:
            if own_client and client is not None:
                client.close()
    except Exception as exc:
        logger.warning("TE %s: fetch failed: %s", cfg.slug, exc)
        return cached[0] if cached else None

    if r.status_code != 200:
        logger.warning("TE %s: status %d", cfg.slug, r.status_code)
        return cached[0] if cached else None

    pattern = _build_regex(cfg.symbol_prefix)
    m = pattern.search(r.text)
    if m is None:
        logger.warning("TE %s: regex did not match (page format changed?)",
                       cfg.slug)
        return cached[0] if cached else None
    try:
        price = float(m.group(1))
    except (ValueError, IndexError) as exc:
        logger.warning("TE %s: parse error: %s", cfg.slug, exc)
        return cached[0] if cached else None
    if not (cfg.sanity_lo <= price <= cfg.sanity_hi):
        logger.warning(
            "TE %s: scraped price %.4f outside sanity bounds [%.0f, %.0f]",
            cfg.slug, price, cfg.sanity_lo, cfg.sanity_hi,
        )
        return cached[0] if cached else None
    _cache[cfg.slug] = (price, now)
    return price


# ── Convenience wrappers ────────────────────────────────────────────


def get_nickel_spot(**kwargs) -> float | None:
    """Current nickel spot in $/tonne (LME 3-month)."""
    return get_te_spot(TE_NICKEL, **kwargs)


def get_cobalt_spot(**kwargs) -> float | None:
    """Current cobalt spot in $/tonne (LME)."""
    return get_te_spot(TE_COBALT, **kwargs)


def get_lithium_spot(**kwargs) -> float | None:
    """Current lithium carbonate spot in CNY/tonne (China spot).
    Note: unit is CNY, not USD. For TruEV, units don't matter as long
    as they're consistent across the anchor and current samples."""
    return get_te_spot(TE_LITHIUM, **kwargs)
