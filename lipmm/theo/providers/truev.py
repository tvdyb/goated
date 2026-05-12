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

    `state_ref` (optional): a ControlState (or anything with a
    `.knob_overrides` attribute returning a dict). When wired, the
    provider reads the `truev_model_rmse_pts` knob each call to
    inflate the lognormal σ for model-uncertainty-aware probabilities.
    Default 0 = no inflation, original behavior. Set on the dashboard
    Knobs tab to a value like 8 (= calibrated live RMSE) for honest
    at-the-money probabilities.
    """

    def __init__(
        self,
        cfg: TruEVConfig,
        forward: TruEvForwardSource,
        state_ref: Any = None,
    ) -> None:
        self._cfg = cfg
        self.series_prefix = cfg.series_prefix
        self._forward = forward
        self._state_ref = state_ref
        try:
            self._settlement_dt = datetime.fromisoformat(cfg.settlement_time_iso)
        except ValueError as exc:
            raise ValueError(
                f"settlement_time_iso {cfg.settlement_time_iso!r} is not a "
                "valid ISO 8601 datetime"
            ) from exc

    # Default model RMSE in points when the operator hasn't set the knob.
    # **0 = no inflation by default.** Earlier we shipped 8 (calibrated
    # walk-forward RMSE + basis risk estimate) but the symmetric σ-
    # widening it applies to the lognormal pricer creates a pathology
    # at the wings: it pushes deep-OTM probabilities from ~0% up to
    # 17-27% and deep-ITM down from ~100% to ~85%, making the bot eager
    # to buy lottery tickets at inflated prices and sell sure-things
    # too cheap. The math is "right" given the stated RMSE, but the
    # tradeoff is bad because counterparty market prices on the wings
    # carry more information than our calibrated RMSE captures.
    # Operator can opt in via the `truev_model_rmse_pts` knob if they
    # understand the boundary distortion. For asymmetric distrust use
    # `theo_tolerance_c` (negative values) instead.
    DEFAULT_MODEL_RMSE_PTS = 0.0

    def _get_model_rmse_pts(self) -> float:
        """Read the `truev_model_rmse_pts` knob from the wired
        ControlState, with safe fallback to DEFAULT_MODEL_RMSE_PTS
        (= 8.0, calibrated from live backtest + basis risk estimate)
        when state isn't wired OR when the knob isn't explicitly set.
        Operator can set the knob to 0 if they want to disable
        inflation."""
        if self._state_ref is None:
            return self.DEFAULT_MODEL_RMSE_PTS
        try:
            knobs = self._state_ref.all_knobs()
        except Exception:
            return self.DEFAULT_MODEL_RMSE_PTS
        val = knobs.get("truev_model_rmse_pts")
        if val is None:
            return self.DEFAULT_MODEL_RMSE_PTS
        try:
            return max(0.0, float(val))
        except (TypeError, ValueError):
            return self.DEFAULT_MODEL_RMSE_PTS

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

        # Model RMSE inflation. The σ above is realized vol over tau —
        # it captures "the index could random-walk away from S between
        # now and settle." It does NOT capture "our reconstructed S
        # could be wrong vs Truflation's actual published value by
        # ~5-10 pts of model RMSE." We add the model RMSE in quadrature
        # so the effective lognormal distribution widens to account
        # for the fact that we don't really know S to the cent — we
        # know it ± RMSE.
        #
        #     σ_realized_pts  = σ × √τ × S        (in points)
        #     σ_combined_pts  = √(σ_realized² + RMSE²)   (in points)
        #     σ_eff_√τ        = σ_combined_pts / S      (back to ratio)
        #
        # Operator dials this in via the `truev_model_rmse_pts` knob
        # (dashboard Knobs tab). Default 0 → no inflation, original
        # behavior. Recommended 5-10 pts based on calibrated walk-
        # forward RMSE.
        # Always compute the RAW (uninflated) probability so the dashboard
        # can show both side-by-side and the operator can see exactly what
        # the RMSE-inflation knob is doing.
        sig_sqrt_t_raw = sig_sqrt_t
        d2_raw = (math.log(S / strike)
                  - 0.5 * sig_sqrt_t_raw * sig_sqrt_t_raw) / sig_sqrt_t_raw
        p_above_raw = max(0.0, min(1.0, float(ndtr(d2_raw))))
        yes_prob_raw = p_above_raw if cfg.direction == "above" else 1.0 - p_above_raw

        model_rmse_pts = self._get_model_rmse_pts()
        if model_rmse_pts > 0:
            sigma_realized_pts = sig_sqrt_t * S
            sigma_combined_pts = math.sqrt(
                sigma_realized_pts ** 2 + model_rmse_pts ** 2
            )
            sig_sqrt_t = max(sigma_combined_pts / max(S, 1e-9), 1e-12)

        d2 = (math.log(S / strike) - 0.5 * sig_sqrt_t * sig_sqrt_t) / sig_sqrt_t
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
                "model_rmse_pts": round(model_rmse_pts, 2),
                "sig_sqrt_t_effective": round(sig_sqrt_t, 6),
                "d2": round(d2, 4),
                # Raw (uninflated) probability and d2 — useful for the UI
                # to show "raw model vs RMSE-adjusted" side-by-side and
                # for the operator to see the magnitude of the haircut.
                "yes_probability_raw": round(yes_prob_raw, 6),
                "yes_cents_raw": round(yes_prob_raw * 100, 2),
                "d2_raw": round(d2_raw, 4),
                "direction": cfg.direction,
                "confidence_breakdown": {
                    "forward_freshness": round(forward_freshness, 3),
                    "tau_factor": round(tau_factor, 3),
                    "max_cap": cfg.max_confidence,
                },
            },
        )
