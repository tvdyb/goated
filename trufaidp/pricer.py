"""End-to-end live pricer for KXTRUFAIDP-26APR27.

Reads `trufaidp/config.yaml`, pulls live token prices, reconstructs
the index, computes time-to-settlement, and returns P(I_T > K) for
every Kalshi strike. Run as a script to print theos for all 15
strikes; or import `price_once()` to embed in a polling loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from trufaidp.basket_gbm import basket_gbm_prob_above
from trufaidp.feed import fetch_spot
from trufaidp.index import reconstruct, stack_arrays

_SECONDS_PER_YEAR = 365.0 * 24.0 * 3600.0
_DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


@dataclass(frozen=True, slots=True)
class TheoSnapshot:
    as_of_utc: datetime
    index_value: float
    tau_years: float
    strikes: np.ndarray
    yes_prob: np.ndarray
    constituent_prices: dict[str, float]


def _load_config(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def price_once(config_path: Path = _DEFAULT_CONFIG) -> TheoSnapshot:
    cfg = _load_config(config_path)

    symbols = [c["symbol"] for c in cfg["constituents"]]
    cg_ids = {c["symbol"]: c["coingecko_id"] for c in cfg["constituents"]}

    quantities = cfg.get("quantities") or {}
    sigmas = cfg.get("sigma_annual") or {}
    corr = cfg.get("correlation") or []

    if not quantities:
        raise RuntimeError("config.quantities is empty — run scripts/calibrate.py first")
    if not sigmas or not corr:
        raise RuntimeError("config.sigma_annual / correlation empty — run scripts/calibrate.py first")
    missing = set(symbols) - set(quantities)
    if missing:
        raise RuntimeError(f"config.quantities missing: {sorted(missing)}")

    spot_by_id = fetch_spot([cg_ids[s] for s in symbols])
    prices = {s: spot_by_id[cg_ids[s]] for s in symbols}

    index_value = reconstruct(quantities, prices)

    settlement = datetime.fromisoformat(cfg["settlement_utc"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    tau_seconds = (settlement - now).total_seconds()
    if tau_seconds <= 0:
        raise RuntimeError(f"settlement already passed: now={now} settlement={settlement}")
    tau = tau_seconds / _SECONDS_PER_YEAR

    q, p, s, c = stack_arrays(symbols, quantities, prices, sigmas, corr)
    strikes = np.asarray(cfg["strikes"], dtype=np.float64)

    yes_prob = basket_gbm_prob_above(q, p, s, c, tau, strikes)

    return TheoSnapshot(
        as_of_utc=now,
        index_value=index_value,
        tau_years=tau,
        strikes=strikes,
        yes_prob=yes_prob,
        constituent_prices=prices,
    )


def main() -> None:
    snap = price_once()
    print(f"as_of_utc        : {snap.as_of_utc.isoformat()}")
    print(f"index_value      : {snap.index_value:.4f}")
    print(f"tau_years        : {snap.tau_years:.6f} ({snap.tau_years * 365 * 24:.2f} hours)")
    print("constituent prices:")
    for sym, px in snap.constituent_prices.items():
        print(f"  {sym:8s} {px:>12.6f}")
    print(f"\n{'strike':>8s}  {'P(yes)':>8s}  {'cents':>6s}")
    for k, p in zip(snap.strikes, snap.yes_prob):
        print(f"{k:>8.2f}  {p:>8.4f}  {round(p * 100):>4d}c")


if __name__ == "__main__":
    main()
