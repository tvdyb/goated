"""Calibrate token quantities + cov matrix and write back into config.yaml.

Usage:
    python -m trufaidp.scripts.calibrate

Reads `trufaidp/config.yaml`. The `anchor` block must be filled in
(index_value, prices, target_weights from the latest Truflation
publish). Quantities are solved from anchor; sigma_annual + correlation
come from a `cov_window_days` window of CoinGecko hourly bars.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from trufaidp.calibrate import calibrate
from trufaidp.index import calibrate_quantities

_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


def main() -> None:
    with _CONFIG.open() as f:
        cfg = yaml.safe_load(f)

    anchor = cfg.get("anchor") or {}
    if not anchor.get("index_value") or not anchor.get("prices") or not anchor.get("target_weights"):
        raise RuntimeError("anchor.{index_value, prices, target_weights} must all be set")

    quantities = calibrate_quantities(
        index_value=float(anchor["index_value"]),
        prices={k: float(v) for k, v in anchor["prices"].items()},
        target_weights={k: float(v) for k, v in anchor["target_weights"].items()},
    )

    symbols = [c["symbol"] for c in cfg["constituents"]]
    cg_ids = {c["symbol"]: c["coingecko_id"] for c in cfg["constituents"]}
    sigma_annual, corr = calibrate(symbols, cg_ids, days=int(cfg["cov_window_days"]))

    cfg["quantities"] = quantities
    cfg["sigma_annual"] = sigma_annual
    cfg["correlation"] = corr

    with _CONFIG.open("w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    print(f"wrote quantities for {len(quantities)} symbols")
    print(f"wrote sigma_annual: {sigma_annual}")
    print(f"wrote {len(corr)}x{len(corr[0])} correlation matrix")


if __name__ == "__main__":
    main()
