"""TruEV theo provider for KXTRUEV-* daily Kalshi binary contracts.

Models tomorrow's Truflation EV Commodity Index settle as lognormal
in the time-to-settle, anchored to today's reconstructed basket value
from yfinance commodity futures.

Per-strike P(YES_above_K) = Φ(d2) where:

    d2 = (ln(S / K) - 0.5 σ² τ) / (σ √τ)

S is today's reconstructed basket index value, K is the strike, σ is
the annualized vol (config), τ is years-to-settle. For "below K"
markets, P(YES) = 1 - Φ(d2).

Confidence calibration:
    confidence = clamp(forward_freshness × tau_factor, 0, 0.7)

Capped at 0.7 in Phase 1 because σ is uncalibrated. Operator can crank
up via per-strike knob overrides if comfortable. The confidence-aware
strategy uses this to pick mode (active-penny / match / follow / skip).

Strike parsing: Kalshi tickers like `KXTRUEV-26MAY07-T1290.40` carry
the threshold in the last hyphen-segment after the `T` prefix. The
`yes_sub_title` of each market documents whether YES means "above" or
"below" — Phase 1 assumes "above" (the convention for the 26-APR-22
example we know about). We default to above and let the operator
override per-strike via theo override if a particular market is
inverted.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from scipy.special import ndtr

from feeds.truflation import TruEvForwardSource
from lipmm.theo.base import TheoResult
from lipmm.theo.providers._truev_index import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_Q4_2025,
    TruEvAnchor,
    TruEvWeights,
    reconstruct_index,
)

logger = logging.getLogger(__name__)


@dataclass
class TruEVConfig:
    """Per-event configuration for the TruEV theo provider.

    Required: settlement_time_iso. Defaults are reasonable for Phase 1
    (4-component basket, σ=30%, conservative confidence cap).
    """
    settlement_time_iso: str                 # ISO 8601 (e.g. "2026-05-07T19:59:00-04:00")
    series_prefix: str = "KXTRUEV"
    weights: TruEvWeights = field(
        default_factory=lambda: DEFAULT_WEIGHTS_Q4_2025,
    )
    anchor: TruEvAnchor = field(
        default_factory=lambda: DEFAULT_ANCHOR_PLACEHOLDER,
    )
    annualized_vol: float = 0.20             # empirically implied σ_annual from KXTRUEV 5-component backtest 2026-04-15..05-06
    forward_freshness_threshold_s: float = 300.0
    confident_tau_hours: float = 6.0
    max_confidence: float = 0.7              # cap until σ is calibrated
    direction: Literal["above", "below"] = "above"
    """For ambiguous markets where YES is 'below strike' (rare on KXTRUEV
    per the Apr-22 precedent), set to 'below' globally. Per-strike
    inversions are handled via dashboard theo overrides."""


def _parse_strike_dollars(ticker: str) -> float:
    """Extract strike value from Kalshi ticker. Last hyphen segment
    starts with 'T' followed by the threshold in dollars (e.g.
    'T1290.40' = 1290.40)."""
    last = ticker.rsplit("-", 1)[-1]
    if not last.startswith("T"):
        raise ValueError(f"ticker {ticker!r} has no T-prefixed strike segment")
    try:
        return float(last[1:])
    except ValueError as exc:
        raise ValueError(f"cannot parse strike from {last!r}: {exc}") from exc


def _degenerate(
    now: float, reason: str, extras: dict[str, Any] | None = None,
) -> TheoResult:
    return TheoResult(
        yes_probability=0.5,
        confidence=0.0,
        computed_at=now,
        source=f"TruEV:{reason}",
        extras=extras or {},
    )


class TruEVTheoProvider:
    """TheoProvider for KXTRUEV-* daily binary contracts.

    Owns a TruEvForwardSource for live commodity prices. `warmup()`
    starts the source's poll loop; `shutdown()` stops it.
    """

    def __init__(
        self,
        cfg: TruEVConfig,
        forward: TruEvForwardSource,
    ) -> None:
        self._cfg = cfg
        self.series_prefix = cfg.series_prefix
        self._forward = forward
        try:
            self._settlement_dt = datetime.fromisoformat(cfg.settlement_time_iso)
        except ValueError as exc:
            raise ValueError(
                f"settlement_time_iso {cfg.settlement_time_iso!r} is not a "
                "valid ISO 8601 datetime"
            ) from exc

    async def warmup(self) -> None:
        await self._forward.start()

    async def shutdown(self) -> None:
        await self._forward.stop()

    async def theo(self, ticker: str) -> TheoResult:
        now = time.time()
        cfg = self._cfg

        # Strike parsing
        try:
            strike = _parse_strike_dollars(ticker)
        except ValueError as exc:
            return _degenerate(now, "bad-ticker",
                               extras={"ticker": ticker, "error": str(exc)})

        # Time to settle
        settle_ts = self._settlement_dt.timestamp()
        tau_seconds = settle_ts - now
        if tau_seconds <= 0:
            return _degenerate(now, "post-settle",
                               extras={"ticker": ticker, "tau_seconds": tau_seconds})

        # Forward source: gather current prices + freshness
        prices_ts = self._forward.latest_prices()
        # We need ALL modeled symbols present.
        modeled = set(cfg.weights.weights.keys())
        missing = modeled - set(prices_ts.keys())
        if missing:
            return _degenerate(
                now, "forward-incomplete",
                extras={"missing_symbols": sorted(missing)},
            )

        current_prices = {sym: prices_ts[sym][0] for sym in modeled}
        oldest_age = self._forward.oldest_age_seconds(now=now)

        # Reconstruct today's basket index
        try:
            S = reconstruct_index(current_prices, cfg.weights, cfg.anchor)
        except ValueError as exc:
            return _degenerate(now, "index-reconstruction-failed",
                               extras={"error": str(exc)})

        if S <= 0 or strike <= 0:
            return _degenerate(now, "degenerate-inputs",
                               extras={"S": S, "strike": strike})

        # Lognormal binary pricer
        sigma = float(cfg.annualized_vol)
        if sigma <= 0:
            return _degenerate(now, "non-positive-vol",
                               extras={"sigma": sigma})
        tau_years = tau_seconds / (365.25 * 86400)
        sig_sqrt_t = max(sigma * math.sqrt(tau_years), 1e-12)
        d2 = (math.log(S / strike) - 0.5 * sigma * sigma * tau_years) / sig_sqrt_t
        p_above = float(ndtr(d2))
        p_above = max(0.0, min(1.0, p_above))

        if cfg.direction == "above":
            yes_prob = p_above
        else:
            yes_prob = 1.0 - p_above

        # Confidence components
        forward_freshness = max(
            0.0,
            1.0 - oldest_age / max(1.0, cfg.forward_freshness_threshold_s),
        )
        tau_factor = min(1.0, tau_seconds / (cfg.confident_tau_hours * 3600))
        raw_conf = forward_freshness * tau_factor
        confidence = max(0.0, min(cfg.max_confidence, raw_conf))

        return TheoResult(
            yes_probability=yes_prob,
            confidence=confidence,
            computed_at=now - oldest_age,  # data-freshness ts
            source="TruEV",
            extras={
                "strike": strike,
                "model_index": round(S, 4),
                "anchor_index": cfg.anchor.anchor_index_value,
                "anchor_date": cfg.anchor.anchor_date,
                "current_prices": {sym: round(p, 4) for sym, p in current_prices.items()},
                "forward_age_s": round(oldest_age, 1),
                "tau_seconds": round(tau_seconds, 1),
                "tau_years": round(tau_years, 6),
                "sigma": sigma,
                "d2": round(d2, 4),
                "direction": cfg.direction,
                "confidence_breakdown": {
                    "forward_freshness": round(forward_freshness, 3),
                    "tau_factor": round(tau_factor, 3),
                    "max_cap": cfg.max_confidence,
                },
            },
        )
