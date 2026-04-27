from __future__ import annotations

import httpx
import numpy as np

_BASE = "https://api.coingecko.com/api/v3"
_TIMEOUT = 10.0

__all__ = ["fetch_spot", "fetch_history"]


def fetch_spot(coingecko_ids: list[str]) -> dict[str, float]:
    ids_param = ",".join(coingecko_ids)
    r = httpx.get(
        f"{_BASE}/simple/price",
        params={"ids": ids_param, "vs_currencies": "usd"},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()

    out: dict[str, float] = {}
    missing: list[str] = []
    for cid in coingecko_ids:
        entry = data.get(cid)
        if entry is None or "usd" not in entry:
            missing.append(cid)
            continue
        out[cid] = float(entry["usd"])
    if missing:
        raise ValueError(f"CoinGecko response missing ids: {missing}")
    return out


def fetch_history(
    coingecko_id: str, days: int, vs_currency: str = "usd"
) -> tuple[np.ndarray, np.ndarray]:
    r = httpx.get(
        f"{_BASE}/coins/{coingecko_id}/market_chart",
        params={"vs_currency": vs_currency, "days": days},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()

    prices = data.get("prices")
    if prices is None:
        raise ValueError(f"CoinGecko market_chart missing 'prices' for {coingecko_id}")
    if not prices:
        raise ValueError(f"CoinGecko market_chart returned empty prices for {coingecko_id}")

    arr = np.asarray(prices, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(
            f"CoinGecko market_chart 'prices' has unexpected shape {arr.shape} for {coingecko_id}"
        )
    timestamps = arr[:, 0].astype(np.int64)
    values = arr[:, 1].astype(np.float64)
    return timestamps, values
