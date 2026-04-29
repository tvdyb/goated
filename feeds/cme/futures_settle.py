"""CBOT daily settlement price puller for ZS (soybean) and ZC (corn) futures.

Closes GAP-063: CME EOD Settlements pull.

Settlement source: CME Group's public preliminary settlements data.
CME publishes daily settlement prices at:
  - Preliminary: ~12:00am CT after the trading session
  - Final: ~10:00am CT next business day

This module provides an async function to pull the daily settlement price
for a given futures symbol and date. The implementation uses CME Group's
public data API for delayed/EOD settlement data.

If the pull fails (HTTP error, missing data, parse failure), it raises
CMESettleError — never returns a default or partial result.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import numpy as np

from feeds.cme.errors import CMESettleError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# CME Group delayed quotes URL pattern for settlement data.
# This is the public-facing delayed data endpoint.
_CME_SETTLE_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements"
    "/{product_id}/FUT"
)

# CME product IDs for settlement lookups.
_PRODUCT_IDS: dict[str, str] = {
    "ZS": "320",   # Soybean futures
    "ZC": "300",   # Corn futures
}

# Default cache directory for settlement data.
_DEFAULT_CACHE_DIR = Path("data/cme_settle")

# Month code to number mapping for CME contract months.
_MONTH_CODES: dict[str, int] = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
_NUM_TO_CODE: dict[int, str] = {v: k for k, v in _MONTH_CODES.items()}


def _validate_symbol(symbol: str) -> str:
    """Validate symbol and return CME product ID."""
    product_id = _PRODUCT_IDS.get(symbol)
    if product_id is None:
        raise CMESettleError(
            f"Unsupported symbol '{symbol}'. Supported: {sorted(_PRODUCT_IDS)}",
            source="futures_settle",
        )
    return product_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def pull_settle(
    symbol: str,
    settle_date: date,
    *,
    timeout_s: float = 30.0,
    cache_dir: Path | None = None,
) -> float:
    """Pull the daily settlement price for a futures contract.

    Args:
        symbol: Futures symbol ('ZS' or 'ZC').
        settle_date: The settlement date to query.
        timeout_s: HTTP request timeout in seconds.
        cache_dir: Optional directory to cache settlement data.

    Returns:
        Settlement price as a float (in cents per bushel for ZS/ZC).

    Raises:
        CMESettleError: On HTTP failure, missing data, or parse errors.
    """
    product_id = _validate_symbol(symbol)

    # Check cache first.
    if cache_dir is not None:
        cached = _read_cache(cache_dir, symbol, settle_date)
        if cached is not None:
            return cached

    url = _CME_SETTLE_URL.format(product_id=product_id)
    params = {
        "tradeDate": settle_date.strftime("%m/%d/%Y"),
    }
    headers = {
        "User-Agent": "goated-cme-ingest/0.1",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise CMESettleError(
            f"HTTP error pulling {symbol} settlement for {settle_date}: {exc}",
            source="futures_settle",
        ) from exc

    if resp.status_code != 200:
        raise CMESettleError(
            f"HTTP {resp.status_code} pulling {symbol} settlement for {settle_date}. "
            f"Body: {resp.text[:500]}",
            source="futures_settle",
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise CMESettleError(
            f"Failed to parse JSON for {symbol} settlement on {settle_date}: {exc}",
            source="futures_settle",
        ) from exc

    settle_price = _extract_front_month_settle(data, symbol, settle_date)

    # Cache the result.
    if cache_dir is not None:
        _write_cache(cache_dir, symbol, settle_date, settle_price)

    return settle_price


def _extract_front_month_settle(
    data: dict,
    symbol: str,
    settle_date: date,
) -> float:
    """Extract the front-month settlement price from CME JSON response.

    Raises CMESettleError if the data is missing or malformed.
    """
    settlements = data.get("settlements")
    if not settlements:
        raise CMESettleError(
            f"No settlement records in CME response for {symbol} on {settle_date}",
            source="futures_settle",
        )

    # Find the front-month contract (first non-spread entry).
    for record in settlements:
        month_str = record.get("month", "")
        settle_str = record.get("settle", "")

        # Skip spread entries and empty records.
        if not month_str or not settle_str or settle_str == "-":
            continue

        try:
            settle_price = float(settle_str.replace(",", "").replace("'", ""))
        except (ValueError, TypeError) as exc:
            raise CMESettleError(
                f"Failed to parse settlement price '{settle_str}' "
                f"for {symbol} {month_str} on {settle_date}: {exc}",
                source="futures_settle",
            ) from exc

        if not np.isfinite(settle_price) or settle_price <= 0:
            raise CMESettleError(
                f"Invalid settlement price {settle_price} for "
                f"{symbol} {month_str} on {settle_date}",
                source="futures_settle",
            )

        return settle_price

    raise CMESettleError(
        f"No valid settlement price found for {symbol} on {settle_date}",
        source="futures_settle",
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(cache_dir: Path, symbol: str, settle_date: date) -> Path:
    """Cache file path for a specific symbol and date."""
    return cache_dir / f"{symbol}_{settle_date.isoformat()}_settle.txt"


def _read_cache(cache_dir: Path, symbol: str, settle_date: date) -> float | None:
    """Read cached settlement price, or None if not cached."""
    path = _cache_path(cache_dir, symbol, settle_date)
    if not path.exists():
        return None
    try:
        text = path.read_text().strip()
        val = float(text)
        if np.isfinite(val) and val > 0:
            return val
    except (ValueError, OSError):
        pass
    return None


def _write_cache(
    cache_dir: Path, symbol: str, settle_date: date, price: float
) -> None:
    """Write settlement price to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol, settle_date)
    path.write_text(f"{price}\n")
