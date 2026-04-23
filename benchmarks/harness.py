"""Shared fixtures for latency benchmarks.

`build_full_book_pricer(n_markets)` stands up a Pricer wired to `n_markets`
synthetic commodities that all share WTI's trading-session schedule and a
fresh `GBMTheo`. That lets us measure the per-market pricer overhead at
realistic scale without needing every real commodity's calendar online.

`warm_kernel()` forces numba compilation so benchmarks measure steady-state
latency, not one-time JIT cost.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import yaml

from engine.event_calendar import TradingCalendar, _SECONDS_PER_TRADING_YEAR_WTI, _wti_trading_seconds
from engine.pricer import Pricer
from models.gbm import _gbm_prob_above, gbm_prob_above
from models.registry import Registry
from state.basis import BasisModel
from state.iv_surface import IVSurface
from state.tick_store import TickStore
from validation.sanity import SanityChecker

ET = ZoneInfo("America/New_York")


@dataclass
class BenchContext:
    pricer: Pricer
    tick_store: TickStore
    iv_surface: IVSurface
    basis_model: BasisModel
    calendar: TradingCalendar
    registry: Registry
    commodities: list[str]
    now_ns: int
    settle_ns: int
    strikes: np.ndarray
    _tmp: Path  # keep reference so file isn't deleted until context drops


def warm_kernel() -> None:
    """Force numba compilation of `_gbm_prob_above` before timing."""
    strikes = np.linspace(50.0, 150.0, 8)
    out = np.empty_like(strikes)
    _gbm_prob_above(100.0, strikes, 0.1, 0.3, 0.0, out)
    _ = gbm_prob_above(100.0, strikes, 0.1, 0.3, 0.0)


def _synthetic_config(n_markets: int) -> dict:
    """All markets use the WTI config verbatim except for name."""
    wti_cfg = {
        "pyth_feed_id": "0x" + "ab" * 32,
        "pyth_min_publishers": 5,
        "pyth_max_staleness_ms": 2000,
        "model": "gbm",
    }
    return {f"bench_{i:02d}": wti_cfg.copy() for i in range(n_markets)}


def build_full_book_pricer(n_markets: int = 50, n_strikes: int = 20) -> BenchContext:
    cfg_dict = _synthetic_config(n_markets)
    tmp = Path(tempfile.mkdtemp(prefix="goated_bench_")) / "commodities.yaml"
    tmp.write_text(yaml.safe_dump(cfg_dict))
    registry = Registry(tmp)

    tick_store = TickStore()
    iv_surface = IVSurface(max_staleness_ms=60_000)
    basis_model = BasisModel(max_staleness_ms=60_000)
    calendar = TradingCalendar()
    sanity = SanityChecker()

    # Monday 12:00 ET with 2-hr-to-settle — same session, well within budget
    now_et = datetime(2026, 4, 20, 12, 0, tzinfo=ET)
    settle_et = datetime(2026, 4, 20, 14, 0, tzinfo=ET)
    now_ns = int(now_et.timestamp() * 1_000_000_000)
    settle_ns = int(settle_et.timestamp() * 1_000_000_000)

    commodities = sorted(cfg_dict)
    for c in commodities:
        tick_store.register(c)
        tick_store.push(c, ts_ns=now_ns, price=75.0, n_publishers=6)
        iv_surface.set_atm(c, sigma=0.35, ts_ns=now_ns)
        basis_model.set(c, basis_drift_annualized=0.0, ts_ns=now_ns)
        calendar.register_handler(c, _wti_trading_seconds, _SECONDS_PER_TRADING_YEAR_WTI)

    strikes = np.linspace(70.0, 80.0, n_strikes).astype(np.float64)

    pricer = Pricer(
        registry=registry,
        tick_store=tick_store,
        iv_surface=iv_surface,
        basis_model=basis_model,
        calendar=calendar,
        sanity=sanity,
    )
    return BenchContext(
        pricer=pricer,
        tick_store=tick_store,
        iv_surface=iv_surface,
        basis_model=basis_model,
        calendar=calendar,
        registry=registry,
        commodities=commodities,
        now_ns=now_ns,
        settle_ns=settle_ns,
        strikes=strikes,
        _tmp=tmp,
    )
