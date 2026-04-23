"""End-to-end: tick → state → pricer → theo matches BS analytical.

Exercises every module in deliverable 1 in one path, and covers every
failure mode the pricer is required to raise on (stale tick, insufficient
publishers, missing IV, missing basis, stub commodity).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from engine.event_calendar import TradingCalendar
from engine.pricer import InsufficientPublishersError, Pricer
from models.gbm import GBMTheo
from models.registry import Registry
from state.basis import BasisModel
from state.errors import MissingStateError, StaleDataError
from state.iv_surface import IVSurface
from state.tick_store import TickStore
from tests._bs_reference import bs_prob_above
from validation.sanity import SanityChecker

ET = ZoneInfo("America/New_York")
CONFIG = Path(__file__).resolve().parents[1] / "config" / "commodities.yaml"


def _build_pricer() -> tuple[Pricer, Registry, TickStore, IVSurface, BasisModel, TradingCalendar]:
    registry = Registry(CONFIG)
    tick_store = TickStore()
    tick_store.register("wti")
    iv_surface = IVSurface(max_staleness_ms=60_000)
    basis_model = BasisModel(max_staleness_ms=60_000)
    calendar = TradingCalendar()
    sanity = SanityChecker()
    pricer = Pricer(
        registry=registry,
        tick_store=tick_store,
        iv_surface=iv_surface,
        basis_model=basis_model,
        calendar=calendar,
        sanity=sanity,
    )
    return pricer, registry, tick_store, iv_surface, basis_model, calendar


def test_registry_loads_wti_as_gbm():
    registry = Registry(CONFIG)
    assert isinstance(registry.get("wti"), GBMTheo)
    # stubs are in the registry but not instantiable
    assert "brent" in registry.commodities()
    assert "wti" in registry.commodities(configured_only=True)
    assert "brent" not in registry.commodities(configured_only=True)


def test_stub_commodity_raises_on_get():
    registry = Registry(CONFIG)
    with pytest.raises(NotImplementedError):
        registry.get("brent")


def test_end_to_end_wti_matches_bs_analytical():
    pricer, _, tick_store, iv_surface, basis_model, calendar = _build_pricer()

    # Monday 12:00 ET, 2 hrs before Kalshi settle (same session)
    now_et = datetime(2026, 4, 20, 12, 0, tzinfo=ET)
    settle_et = datetime(2026, 4, 20, 14, 0, tzinfo=ET)
    now_ns = int(now_et.timestamp() * 1_000_000_000)
    settle_ns = int(settle_et.timestamp() * 1_000_000_000)

    tick_store.push("wti", ts_ns=now_ns, price=75.0, n_publishers=6)
    iv_surface.set_atm("wti", sigma=0.35, ts_ns=now_ns)
    basis_model.set("wti", basis_drift_annualized=0.0, ts_ns=now_ns)

    strikes = np.array([70.0, 72.5, 75.0, 77.5, 80.0])
    out = pricer.reprice_market("wti", strikes, settle_ns, now_ns=now_ns)

    tau = calendar.tau_years("wti", now_ns, settle_ns)
    expected = bs_prob_above(75.0, strikes, tau, 0.35, 0.0)
    np.testing.assert_allclose(out.probabilities, expected, atol=1e-9)
    assert out.commodity == "wti"
    assert out.model_name == "gbm"
    assert out.source_tick_seq == 1
    # monotonic, in [0,1], matching shape — sanity checker ran without raising


def test_stale_pyth_tick_raises():
    pricer, _, tick_store, iv_surface, basis_model, _ = _build_pricer()
    now_et = datetime(2026, 4, 20, 12, 0, tzinfo=ET)
    now_ns = int(now_et.timestamp() * 1_000_000_000)
    tick_ns = now_ns - 10_000 * 1_000_000  # 10s old; WTI budget is 2s
    tick_store.push("wti", ts_ns=tick_ns, price=75.0, n_publishers=6)
    iv_surface.set_atm("wti", sigma=0.35, ts_ns=now_ns)
    basis_model.set("wti", basis_drift_annualized=0.0, ts_ns=now_ns)
    with pytest.raises(StaleDataError):
        pricer.reprice_market(
            "wti", np.array([75.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )


def test_insufficient_publishers_raises():
    pricer, _, tick_store, iv_surface, basis_model, _ = _build_pricer()
    now_ns = int(datetime(2026, 4, 20, 12, 0, tzinfo=ET).timestamp() * 1_000_000_000)
    tick_store.push("wti", ts_ns=now_ns, price=75.0, n_publishers=3)  # min is 5
    iv_surface.set_atm("wti", sigma=0.35, ts_ns=now_ns)
    basis_model.set("wti", basis_drift_annualized=0.0, ts_ns=now_ns)
    with pytest.raises(InsufficientPublishersError):
        pricer.reprice_market(
            "wti", np.array([75.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )


def test_missing_iv_raises():
    pricer, _, tick_store, _, basis_model, _ = _build_pricer()
    now_ns = int(datetime(2026, 4, 20, 12, 0, tzinfo=ET).timestamp() * 1_000_000_000)
    tick_store.push("wti", ts_ns=now_ns, price=75.0, n_publishers=6)
    basis_model.set("wti", basis_drift_annualized=0.0, ts_ns=now_ns)
    with pytest.raises(MissingStateError):
        pricer.reprice_market(
            "wti", np.array([75.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )


def test_missing_basis_raises():
    pricer, _, tick_store, iv_surface, _, _ = _build_pricer()
    now_ns = int(datetime(2026, 4, 20, 12, 0, tzinfo=ET).timestamp() * 1_000_000_000)
    tick_store.push("wti", ts_ns=now_ns, price=75.0, n_publishers=6)
    iv_surface.set_atm("wti", sigma=0.35, ts_ns=now_ns)
    with pytest.raises(MissingStateError):
        pricer.reprice_market(
            "wti", np.array([75.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )


def test_missing_tick_raises():
    pricer, _, _, iv_surface, basis_model, _ = _build_pricer()
    now_ns = int(datetime(2026, 4, 20, 12, 0, tzinfo=ET).timestamp() * 1_000_000_000)
    iv_surface.set_atm("wti", sigma=0.35, ts_ns=now_ns)
    basis_model.set("wti", basis_drift_annualized=0.0, ts_ns=now_ns)
    with pytest.raises(MissingStateError):
        pricer.reprice_market(
            "wti", np.array([75.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )


def test_stub_commodity_refuses_to_price():
    pricer, _, tick_store, iv_surface, basis_model, _ = _build_pricer()
    # Register and prime state for a stub so the pricer gets past those checks
    tick_store.register("brent")
    now_ns = int(datetime(2026, 4, 20, 12, 0, tzinfo=ET).timestamp() * 1_000_000_000)
    tick_store.push("brent", ts_ns=now_ns, price=79.0, n_publishers=6)
    iv_surface.set_atm("brent", sigma=0.35, ts_ns=now_ns)
    basis_model.set("brent", basis_drift_annualized=0.0, ts_ns=now_ns)
    with pytest.raises((NotImplementedError, KeyError)):
        # brent trading calendar isn't implemented either; NotImplementedError
        # from calendar or registry, whichever triggers first.
        pricer.reprice_market(
            "brent", np.array([80.0]), now_ns + 3600 * 1_000_000_000, now_ns=now_ns
        )
