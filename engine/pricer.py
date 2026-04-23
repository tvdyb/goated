"""Main repricing loop: market → theo.

One `Pricer.reprice_market(commodity, strikes, settle_ns)` call:
  1. reads the latest Pyth tick for `commodity` (raises if missing/stale)
  2. enforces publisher floor per `commodities.yaml`
  3. reads ATM IV (raises if missing/stale)
  4. reads basis drift (raises if missing/stale)
  5. computes trading-time τ via `TradingCalendar`
  6. calls the registered model's `price()`
  7. sanity-checks the output before returning

Any check that fails raises. A wrong theo trades; a missing theo doesn't.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from engine.event_calendar import TradingCalendar
from models.base import TheoInputs, TheoOutput
from models.registry import Registry
from state.basis import BasisModel
from state.errors import StaleDataError
from state.iv_surface import IVSurface
from state.tick_store import TickStore
from validation.sanity import SanityChecker


class InsufficientPublishersError(RuntimeError):
    pass


@dataclass(slots=True)
class Pricer:
    registry: Registry
    tick_store: TickStore
    iv_surface: IVSurface
    basis_model: BasisModel
    calendar: TradingCalendar
    sanity: SanityChecker

    def reprice_market(
        self,
        commodity: str,
        strikes: np.ndarray,
        settle_ns: int,
        *,
        now_ns: int | None = None,
    ) -> TheoOutput:
        now_ns = time.time_ns() if now_ns is None else now_ns

        cfg = self.registry.config(commodity)
        max_staleness_ms = int(cfg.raw.get("pyth_max_staleness_ms", 2000))
        min_publishers = int(cfg.raw.get("pyth_min_publishers", 5))

        tick = self.tick_store.latest(commodity)
        staleness_ms = (now_ns - tick.ts_ns) / 1e6
        if staleness_ms > max_staleness_ms:
            raise StaleDataError(
                f"{commodity}: Pyth tick stale by {staleness_ms:.0f}ms "
                f"(budget {max_staleness_ms}ms)"
            )
        if tick.n_publishers < min_publishers:
            raise InsufficientPublishersError(
                f"{commodity}: {tick.n_publishers} publishers < floor {min_publishers}"
            )

        sigma = self.iv_surface.atm(commodity, now_ns=now_ns)
        basis_drift = self.basis_model.get(commodity, now_ns=now_ns)
        tau = self.calendar.tau_years(commodity, now_ns, settle_ns)
        if tau <= 0.0:
            raise ValueError(f"{commodity}: non-positive tau {tau} (settle {settle_ns} <= now {now_ns})")

        inputs = TheoInputs(
            commodity=commodity,
            spot=tick.price,
            strikes=np.ascontiguousarray(strikes, dtype=np.float64),
            tau=tau,
            sigma=sigma,
            basis_drift=basis_drift,
            as_of_ns=now_ns,
            source_tick_seq=tick.seq,
        )
        model = self.registry.get(commodity)
        output = model.price(inputs)
        self.sanity.check(output, spot=tick.price)
        return output
