"""GBM commodity theo provider.

Black-76 lognormal model for continuously-priced commodity markets where:
  - There's a known underlying spot/forward price feed (TE, yfinance, IBKR)
  - Volatility can be estimated (from option chain or historical)
  - Settlement is at a known timestamp

Suitable for: KXSOYBEANMON, KXCORNMON, KXCATTLEMON, KXWHEATMON,
              KXCRUDE, KXNATGAS, etc.
NOT suitable for: discrete event markets (sports, politics, weather binary
                  events) — for those, use a different provider.

The provider takes its forward and vol via dependency injection: callable
hooks that return current values. This keeps the provider testable in
isolation and lets the bot's existing forward/vol stacks be reused without
the provider knowing or caring how they work.

Confidence calibration:
  forward_freshness × vol_quality × tau_factor
  - forward_freshness: 1.0 if forward fetched <60s ago, drops linearly to 0
    at threshold (default 120s)
  - vol_quality: 1.0 if vol calibrated from 3+ ATM strikes, scales linearly
  - tau_factor: 1.0 if >6h to settle, drops linearly to 0 at settle
    (small tau amplifies forward errors → less trust)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from scipy.special import ndtr

from lipmm.theo.base import TheoResult

logger = logging.getLogger(__name__)


# Hooks the provider calls to fetch upstream data.
# Forward hook returns (forward_price_dollars, fetched_at_unix_ts).
# Vol hook returns (vol_annualized, num_strikes_used_for_calibration, calibrated_at_unix_ts).
# Both are sync — the bot's existing forward/vol caches are sync; making them
# async would require changing the bot's hot loop.
ForwardHook = Callable[[], tuple[float, float]]
VolHook = Callable[[], tuple[float, int, float]]


@dataclass
class GbmCommodityConfig:
    series_prefix: str
    settlement_time_iso: str
    forward_freshness_threshold_s: float = 120.0
    confident_tau_hours: float = 6.0
    confident_vol_strikes: int = 3
    fallback_vol: float = 0.16


class GbmCommodityTheo:
    """TheoProvider for continuous-priced commodity markets via Black-76."""

    def __init__(
        self,
        cfg: GbmCommodityConfig,
        forward_hook: ForwardHook,
        vol_hook: VolHook,
    ) -> None:
        self._cfg = cfg
        self.series_prefix = cfg.series_prefix
        self._forward_hook = forward_hook
        self._vol_hook = vol_hook
        self._settlement_dt = datetime.fromisoformat(cfg.settlement_time_iso)

    async def warmup(self) -> None:
        # Provider is stateless beyond config and hooks — the hooks own caching.
        # Probe both hooks once to surface configuration errors at startup
        # rather than on the first cycle.
        try:
            self._forward_hook()
            self._vol_hook()
        except Exception as exc:
            logger.warning(
                "GbmCommodityTheo[%s]: warmup probe failed: %s",
                self.series_prefix, exc,
            )

    async def shutdown(self) -> None:
        return

    async def theo(self, ticker: str) -> TheoResult:
        now = time.time()

        try:
            strike = self._parse_strike(ticker)
        except ValueError as exc:
            return _degenerate(now, self.series_prefix, "bad-ticker",
                               extras={"ticker": ticker, "error": str(exc)})

        try:
            forward, forward_ts = self._forward_hook()
        except Exception as exc:
            return _degenerate(now, self.series_prefix, "forward-fetch-failed",
                               extras={"ticker": ticker, "error": repr(exc)})

        try:
            vol, n_strikes, vol_ts = self._vol_hook()
        except Exception as exc:
            return _degenerate(now, self.series_prefix, "vol-fetch-failed",
                               extras={"ticker": ticker, "error": repr(exc)})

        settle_ts = self._settlement_dt.timestamp()
        tau_seconds = settle_ts - now
        if tau_seconds <= 0:
            return _degenerate(now, self.series_prefix, "post-settlement",
                               extras={"ticker": ticker, "tau_seconds": tau_seconds})

        if forward <= 0 or vol <= 0:
            return _degenerate(now, self.series_prefix, "degenerate-inputs",
                               extras={"forward": forward, "vol": vol})

        tau_years = tau_seconds / (365.25 * 86400)
        sig_sqrt_t = max(vol * math.sqrt(tau_years), 1e-12)
        d2 = (math.log(forward / strike) - 0.5 * vol * vol * tau_years) / sig_sqrt_t
        prob = float(ndtr(d2))
        prob = max(0.0, min(1.0, prob))

        # Confidence components
        forward_age_s = max(0.0, now - forward_ts) if forward_ts > 0 else 1e9
        forward_freshness = max(
            0.0, 1.0 - forward_age_s / max(1.0, self._cfg.forward_freshness_threshold_s)
        )
        vol_quality = min(1.0, n_strikes / max(1, self._cfg.confident_vol_strikes))
        tau_factor = min(1.0, tau_seconds / (self._cfg.confident_tau_hours * 3600))

        confidence = forward_freshness * vol_quality * tau_factor
        confidence = max(0.0, min(1.0, confidence))

        return TheoResult(
            yes_probability=prob,
            confidence=confidence,
            computed_at=min(forward_ts, vol_ts) if (forward_ts and vol_ts) else now,
            source="GBM-commodity",
            extras={
                "strike": strike,
                "forward_dollars": forward,
                "forward_age_s": round(forward_age_s, 1),
                "vol": vol,
                "vol_strikes_used": n_strikes,
                "tau_years": tau_years,
                "tau_seconds": round(tau_seconds, 1),
                "d2": d2,
                "confidence_breakdown": {
                    "forward_freshness": round(forward_freshness, 3),
                    "vol_quality": round(vol_quality, 3),
                    "tau_factor": round(tau_factor, 3),
                },
            },
        )

    @staticmethod
    def _parse_strike(ticker: str) -> float:
        """Extract strike from Kalshi ticker, in DOLLARS (matching forward unit).

        Kalshi convention: ticker strike is in cents per bushel
        (e.g. 'T1186.99' = 1186.99 cents = $11.8699 / bu). The forward_hook
        is expected to return dollars, so we divide by 100 here to keep both
        sides of the Black-76 ratio in the same unit.
        """
        last = ticker.rsplit("-", 1)[-1]
        if not last.startswith("T"):
            raise ValueError(f"ticker {ticker!r} has no T-prefixed strike segment")
        try:
            return float(last[1:]) / 100.0
        except ValueError as e:
            raise ValueError(f"cannot parse strike from {last!r}: {e}") from e


def _degenerate(
    now: float, series_prefix: str, reason: str,
    extras: dict[str, Any] | None = None,
) -> TheoResult:
    """Build a zero-confidence result with a reason in `source`. Used for any
    case where the provider can't compute reliably — caller's confidence-aware
    logic will skip quoting on this strike."""
    return TheoResult(
        yes_probability=0.5,
        confidence=0.0,
        computed_at=now,
        source=f"GBM-commodity:{reason}",
        extras=extras or {},
    )
