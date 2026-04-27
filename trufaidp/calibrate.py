"""Vol/correlation calibration for the basket-GBM pricer.

Pulls hourly token prices from CoinGecko for the configured window,
aligns them on a common timestamp grid, computes log-returns, and
estimates per-token annualized vol + the constituent correlation
matrix. Output drops back into config.yaml as `sigma_annual` and
`correlation` for the live pricer.
"""

from __future__ import annotations

import numpy as np

from trufaidp.feed import fetch_history

_HOURS_PER_YEAR = 24.0 * 365.0


def _align_hourly(symbols: list[str], series: dict[str, tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """Bucket each (ts_ms, price) series to hourly grid (floor), inner-join
    across symbols, return (timestamps_hour, prices[T, m]) aligned in `symbols`
    order. CoinGecko hourly bars are already ~1h apart; this just enforces a
    common grid via a hash-set intersection on the floored timestamps."""
    floored: dict[str, dict[int, float]] = {}
    for sym in symbols:
        ts, px = series[sym]
        bucket: dict[int, float] = {}
        for t, p in zip(ts, px):
            bucket[int(t) // 3_600_000] = float(p)
        floored[sym] = bucket

    common = set.intersection(*(set(b.keys()) for b in floored.values()))
    if len(common) < 24:
        raise ValueError(f"only {len(common)} aligned hourly bars across constituents — need >= 24")
    hours = np.array(sorted(common), dtype=np.int64)
    prices = np.empty((hours.size, len(symbols)), dtype=np.float64)
    for j, sym in enumerate(symbols):
        b = floored[sym]
        for i, h in enumerate(hours):
            prices[i, j] = b[int(h)]
    return hours, prices


def calibrate(symbols: list[str], coingecko_ids: dict[str, str], days: int) -> tuple[dict[str, float], list[list[float]]]:
    series = {sym: fetch_history(coingecko_ids[sym], days=days) for sym in symbols}
    _hours, prices = _align_hourly(symbols, series)

    log_px = np.log(prices)
    rets = np.diff(log_px, axis=0)

    sigma_hourly = rets.std(axis=0, ddof=1)
    sigma_annual = sigma_hourly * np.sqrt(_HOURS_PER_YEAR)

    corr = np.corrcoef(rets, rowvar=False)
    if not np.all(np.isfinite(corr)):
        raise ValueError("correlation matrix has non-finite entries — check input series")

    return (
        {sym: float(sigma_annual[i]) for i, sym in enumerate(symbols)},
        corr.tolist(),
    )
