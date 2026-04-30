"""Trading Economics soybean spot price scraper.

Kalshi's KXSOYBEANMON event resolves against the Trading Economics soybean
1-minute close at the settlement timestamp. So Trading Economics is the
canonical reference price — yfinance/CBOT can be 3+ cents stale during
overnight CBOT session.

This module scrapes the public Trading Economics soybean page and parses
the embedded JSON for the last price.

Usage:
    from feeds.tradingeconomics.soybean import get_soybean_price
    price_cents = get_soybean_price()  # returns float in cents/bushel, or None
"""

from __future__ import annotations

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

_URL = "https://tradingeconomics.com/commodity/soybeans"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# TE embeds: ..."symbol":"S 1:COM","last":1185.475..."name":"Soybeans"...
# The "symbol" field comes immediately before "last" in the JSON snippet,
# so anchor on it (and verify "Soybeans" is nearby).
_PRICE_RE = re.compile(
    r'"symbol"\s*:\s*"S\s*1:COM"[^{}]{0,500}?"last"\s*:\s*([0-9]+\.?[0-9]*)',
    re.DOTALL,
)
# Fallback: anchor on Soybeans name in either direction
_PRICE_RE_FALLBACK = re.compile(
    r'"last"\s*:\s*([0-9]+\.?[0-9]*)[^{}]{0,500}?"name"\s*:\s*"Soybeans"',
    re.DOTALL,
)

_cache_price: float | None = None
_cache_ts: float = 0.0
_CACHE_TTL_S = 60.0


def _parse_price(html: str) -> float | None:
    m = _PRICE_RE.search(html)
    if not m:
        m = _PRICE_RE_FALLBACK.search(html)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (ValueError, IndexError):
        return None


def get_soybean_price(
    *,
    timeout_s: float = 5.0,
    use_cache: bool = True,
) -> float | None:
    """Fetch current soybean price from Trading Economics in cents/bushel.

    Returns None on any failure (network, parse, sanity-check).
    Caches successful results for 60s to avoid hammering the page.
    """
    global _cache_price, _cache_ts
    now = time.time()
    if use_cache and _cache_price is not None and (now - _cache_ts) < _CACHE_TTL_S:
        return _cache_price

    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            r = client.get(_URL, headers={"User-Agent": _USER_AGENT})
            if r.status_code != 200:
                logger.warning("TE: HTTP %s on soybean fetch", r.status_code)
                return _cache_price
            price = _parse_price(r.text)
    except Exception as exc:
        logger.warning("TE: fetch failed: %s", exc)
        return _cache_price

    if price is None:
        logger.warning("TE: failed to parse price from response")
        return _cache_price

    # Sanity: soybeans live between $5 and $25 per bushel (500-2500 cents).
    if not (500.0 <= price <= 2500.0):
        logger.warning("TE: parsed price %.2f outside sanity range", price)
        return _cache_price

    _cache_price = price
    _cache_ts = now
    logger.info("TE: soybean price = %.4fc/bu", price)
    return price


def get_cached_age_s() -> float:
    """Seconds since last successful TE fetch (or 1e9 if never)."""
    return (time.time() - _cache_ts) if _cache_ts > 0 else 1e9
