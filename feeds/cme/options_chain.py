"""EOD options chain puller for ZS (soybean) and ZC (corn) futures options.

F4-ACT-02: closes GAP-046 (CME ZS option-chain ingest) and
GAP-047 (put-call parity arbitrage prune).

Data source: CME Group's public delayed quotes (EOD settlement data).
The chain includes: strike, call price, put price, implied volatility
(if available from source), open interest, and volume.

Put-call parity check (GAP-047):
  For each strike: |C - P - (F*exp(-rT) - K*exp(-rT))| < threshold
  Log violations. Raise CMEParityError if >25% of strikes violate.

This module is async (I/O only) per non-negotiables. The chain data
is returned as numpy arrays, not pandas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import numpy as np

from feeds.cme.errors import CMEChainError, CMEParityError

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OptionsChain:
    """EOD options chain for a single expiry.

    All array fields are 1-D numpy arrays of the same length (one entry
    per strike). Prices are in the same units as the underlying (cents/bu
    for ZS/ZC).
    """

    symbol: str           # e.g. "ZS"
    expiry: date          # Options expiry date
    as_of: date           # Date the data was pulled / applies to
    underlying_settle: float  # Underlying futures settlement price

    strikes: np.ndarray       # float64, strike prices
    call_prices: np.ndarray   # float64, call settlement/last prices
    put_prices: np.ndarray    # float64, put settlement/last prices
    call_ivs: np.ndarray | None   # float64 or None, call implied vols
    put_ivs: np.ndarray | None    # float64 or None, put implied vols
    call_oi: np.ndarray | None    # int64 or None, call open interest
    put_oi: np.ndarray | None     # int64 or None, put open interest
    call_volume: np.ndarray | None  # int64 or None, call volume
    put_volume: np.ndarray | None   # int64 or None, put volume

    def __post_init__(self) -> None:
        n = len(self.strikes)
        if len(self.call_prices) != n or len(self.put_prices) != n:
            raise CMEChainError(
                f"Array length mismatch: strikes={n}, "
                f"calls={len(self.call_prices)}, puts={len(self.put_prices)}",
                source="OptionsChain",
            )
        if n == 0:
            raise CMEChainError(
                f"Empty options chain for {self.symbol} expiry {self.expiry}",
                source="OptionsChain",
            )


# ---------------------------------------------------------------------------
# CME product configuration
# ---------------------------------------------------------------------------

_CME_OPTIONS_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Options/Settlements"
    "/{product_id}/OOF"
)

# CME product IDs for options settlement lookups.
_OPTIONS_PRODUCT_IDS: dict[str, str] = {
    "ZS": "323",   # Soybean options on futures (OZS)
    "ZC": "306",   # Corn options on futures (OZC)
}

# Default cache directory.
_DEFAULT_CACHE_DIR = Path("data/cme_options")


def _validate_symbol(symbol: str) -> str:
    """Validate symbol and return CME options product ID."""
    product_id = _OPTIONS_PRODUCT_IDS.get(symbol)
    if product_id is None:
        raise CMEChainError(
            f"Unsupported symbol '{symbol}'. "
            f"Supported: {sorted(_OPTIONS_PRODUCT_IDS)}",
            source="options_chain",
        )
    return product_id


# ---------------------------------------------------------------------------
# Put-call parity check (GAP-047)
# ---------------------------------------------------------------------------

def check_put_call_parity(
    chain: OptionsChain,
    *,
    risk_free_rate: float = 0.05,
    violation_threshold: float = 0.02,
    max_violation_frac: float = 0.25,
) -> list[int]:
    """Check put-call parity on an options chain.

    For European-style options on futures:
      C - P = F*exp(-rT) - K*exp(-rT)
    where F is the futures price (underlying_settle).

    For American-style (which CBOT options technically are), the parity
    is approximate but still useful for flagging data errors.

    Args:
        chain: The options chain to check.
        risk_free_rate: Annual risk-free rate for discounting.
        violation_threshold: Relative threshold for flagging a violation
            (as a fraction of the underlying price).
        max_violation_frac: If more than this fraction of strikes violate,
            raise CMEParityError.

    Returns:
        List of strike indices that violate parity.

    Raises:
        CMEParityError: If >max_violation_frac of strikes violate.
    """
    fwd = chain.underlying_settle
    strikes = chain.strikes
    calls = chain.call_prices
    puts = chain.put_prices

    # Time to expiry in years (approximate from dates).
    days_to_expiry = (chain.expiry - chain.as_of).days
    if days_to_expiry <= 0:
        # Expired or same-day: skip parity check.
        return []

    tau = days_to_expiry / 365.25
    discount = np.exp(-risk_free_rate * tau)

    # Put-call parity for futures options: C - P = (F - K) * discount
    theoretical_diff = (fwd - strikes) * discount
    actual_diff = calls - puts

    abs_error = np.abs(actual_diff - theoretical_diff)
    threshold_abs = violation_threshold * fwd

    violations = np.where(abs_error > threshold_abs)[0].tolist()

    n_violations = len(violations)
    n_total = len(strikes)
    violation_frac = n_violations / n_total if n_total > 0 else 0.0

    if violation_frac > max_violation_frac:
        raise CMEParityError(
            f"Put-call parity: {n_violations}/{n_total} strikes "
            f"({violation_frac:.1%}) violate threshold {violation_threshold:.1%} "
            f"on {chain.symbol} expiry {chain.expiry}. "
            f"Max allowed: {max_violation_frac:.0%}. "
            f"Largest error: {abs_error.max():.4f} (threshold: {threshold_abs:.4f})",
            source="put_call_parity",
        )

    return violations


# ---------------------------------------------------------------------------
# Chain puller
# ---------------------------------------------------------------------------

async def pull_options_chain(
    symbol: str,
    expiry: date,
    *,
    trade_date: date | None = None,
    underlying_settle: float | None = None,
    timeout_s: float = 30.0,
    cache_dir: Path | None = None,
) -> OptionsChain:
    """Pull EOD options chain from CME Group's public delayed data.

    Args:
        symbol: Futures symbol ('ZS' or 'ZC').
        expiry: Options expiry date.
        trade_date: Trade date for the EOD data. Defaults to today.
        underlying_settle: If known, the underlying futures settlement
            price. If None, will be extracted from the chain data.
        timeout_s: HTTP request timeout.
        cache_dir: Optional directory to cache chain data.

    Returns:
        OptionsChain with all available fields populated.

    Raises:
        CMEChainError: On HTTP failure, parse error, or missing data.
    """
    product_id = _validate_symbol(symbol)
    as_of = trade_date or date.today()

    # Check cache first.
    if cache_dir is not None:
        cached = _read_chain_cache(cache_dir, symbol, expiry, as_of)
        if cached is not None:
            return cached

    url = _CME_OPTIONS_URL.format(product_id=product_id)
    params = {
        "tradeDate": as_of.strftime("%m/%d/%Y"),
    }
    headers = {
        "User-Agent": "goated-cme-ingest/0.1",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise CMEChainError(
            f"HTTP error pulling {symbol} options chain for {as_of}: {exc}",
            source="options_chain",
        ) from exc

    if resp.status_code != 200:
        raise CMEChainError(
            f"HTTP {resp.status_code} pulling {symbol} options chain for {as_of}. "
            f"Body: {resp.text[:500]}",
            source="options_chain",
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise CMEChainError(
            f"Failed to parse JSON for {symbol} options on {as_of}: {exc}",
            source="options_chain",
        ) from exc

    chain = _parse_options_response(data, symbol, expiry, as_of, underlying_settle)

    if cache_dir is not None:
        _write_chain_cache(cache_dir, chain)

    return chain


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_settle_price(val: str) -> float | None:
    """Parse a settlement/price string from CME data. Returns None for missing."""
    if not val or val in ("-", "UNCH", ""):
        return None
    try:
        cleaned = val.replace(",", "").replace("'", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_int_field(val: str | int | None) -> int | None:
    """Parse an integer field (OI, volume). Returns None for missing."""
    if val is None or val in ("", "-"):
        return None
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _build_sorted_float(lst: list[float | None], order: np.ndarray) -> np.ndarray | None:
    """Build a sorted float64 array from a list with possible Nones."""
    if all(v is None for v in lst):
        return None
    arr = np.array([v if v is not None else np.nan for v in lst], dtype=np.float64)
    return arr[order]


def _build_sorted_int(lst: list[int | None], order: np.ndarray) -> np.ndarray | None:
    """Build a sorted int64 array from a list with possible Nones."""
    if all(v is None for v in lst):
        return None
    arr = np.array([v if v is not None else 0 for v in lst], dtype=np.int64)
    return arr[order]


def _extract_records(settlements: list[dict]) -> tuple[
    list[float], list[float], list[float],
    list[float | None], list[float | None],
    list[int | None], list[int | None],
    list[int | None], list[int | None],
]:
    """Extract strike-level data from CME settlement records."""
    strikes: list[float] = []
    calls: list[float] = []
    puts: list[float] = []
    c_ivs: list[float | None] = []
    p_ivs: list[float | None] = []
    c_oi: list[int | None] = []
    p_oi: list[int | None] = []
    c_vol: list[int | None] = []
    p_vol: list[int | None] = []

    for record in settlements:
        strike = _parse_settle_price(str(record.get("strike", "")))
        if strike is None or strike <= 0:
            continue
        call_settle = _parse_settle_price(record.get("call", ""))
        put_settle = _parse_settle_price(record.get("put", ""))
        if call_settle is None or put_settle is None:
            continue

        strikes.append(strike)
        calls.append(call_settle)
        puts.append(put_settle)
        c_ivs.append(_parse_settle_price(record.get("callIV", "")))
        p_ivs.append(_parse_settle_price(record.get("putIV", "")))
        c_oi.append(_parse_int_field(record.get("callOI")))
        p_oi.append(_parse_int_field(record.get("putOI")))
        c_vol.append(_parse_int_field(record.get("callVol")))
        p_vol.append(_parse_int_field(record.get("putVol")))

    return strikes, calls, puts, c_ivs, p_ivs, c_oi, p_oi, c_vol, p_vol


def _parse_options_response(
    data: dict,
    symbol: str,
    target_expiry: date,
    as_of: date,
    underlying_settle: float | None,
) -> OptionsChain:
    """Parse CME options settlement JSON into an OptionsChain."""
    settlements = data.get("settlements")
    if not settlements:
        raise CMEChainError(
            f"No settlement records in CME response for {symbol} options on {as_of}",
            source="options_chain",
        )

    strikes_l, calls_l, puts_l, c_ivs, p_ivs, c_oi, p_oi, c_vol, p_vol = (
        _extract_records(settlements)
    )

    if not strikes_l:
        raise CMEChainError(
            f"No valid strike data found for {symbol} expiry {target_expiry} "
            f"on {as_of}. The CME response may not contain data for this expiry.",
            source="options_chain",
        )

    strikes = np.array(strikes_l, dtype=np.float64)
    call_prices = np.array(calls_l, dtype=np.float64)
    put_prices = np.array(puts_l, dtype=np.float64)

    order = np.argsort(strikes, kind="stable")
    strikes = strikes[order]
    call_prices = call_prices[order]
    put_prices = put_prices[order]

    if underlying_settle is None:
        mid_idx = len(strikes) // 2
        underlying_settle = call_prices[mid_idx] - put_prices[mid_idx] + strikes[mid_idx]
        if underlying_settle <= 0:
            raise CMEChainError(
                f"Could not determine underlying settle price for {symbol} "
                f"expiry {target_expiry} on {as_of}",
                source="options_chain",
            )

    return OptionsChain(
        symbol=symbol,
        expiry=target_expiry,
        as_of=as_of,
        underlying_settle=underlying_settle,
        strikes=strikes,
        call_prices=call_prices,
        put_prices=put_prices,
        call_ivs=_build_sorted_float(c_ivs, order),
        put_ivs=_build_sorted_float(p_ivs, order),
        call_oi=_build_sorted_int(c_oi, order),
        put_oi=_build_sorted_int(p_oi, order),
        call_volume=_build_sorted_int(c_vol, order),
        put_volume=_build_sorted_int(p_vol, order),
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _chain_cache_path(
    cache_dir: Path, symbol: str, expiry: date, as_of: date
) -> Path:
    return cache_dir / f"{symbol}_{expiry.isoformat()}_{as_of.isoformat()}_chain.npz"


def _read_chain_cache(
    cache_dir: Path, symbol: str, expiry: date, as_of: date
) -> OptionsChain | None:
    """Read cached chain, or None if not cached."""
    path = _chain_cache_path(cache_dir, symbol, expiry, as_of)
    if not path.exists():
        return None
    try:
        loaded = np.load(str(path), allow_pickle=False)
        return OptionsChain(
            symbol=symbol,
            expiry=expiry,
            as_of=as_of,
            underlying_settle=float(loaded["underlying_settle"]),
            strikes=loaded["strikes"],
            call_prices=loaded["call_prices"],
            put_prices=loaded["put_prices"],
            call_ivs=loaded.get("call_ivs"),
            put_ivs=loaded.get("put_ivs"),
            call_oi=loaded.get("call_oi"),
            put_oi=loaded.get("put_oi"),
            call_volume=loaded.get("call_volume"),
            put_volume=loaded.get("put_volume"),
        )
    except (ValueError, KeyError, OSError):
        return None


def _write_chain_cache(cache_dir: Path, chain: OptionsChain) -> None:
    """Write chain to npz cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _chain_cache_path(cache_dir, chain.symbol, chain.expiry, chain.as_of)
    save_kwargs: dict[str, np.ndarray] = {
        "underlying_settle": np.array([chain.underlying_settle]),
        "strikes": chain.strikes,
        "call_prices": chain.call_prices,
        "put_prices": chain.put_prices,
    }
    for name, arr in [
        ("call_ivs", chain.call_ivs),
        ("put_ivs", chain.put_ivs),
        ("call_oi", chain.call_oi),
        ("put_oi", chain.put_oi),
        ("call_volume", chain.call_volume),
        ("put_volume", chain.put_volume),
    ]:
        if arr is not None:
            save_kwargs[name] = arr
    np.savez(str(path), **save_kwargs)
