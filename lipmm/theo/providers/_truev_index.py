"""Truflation EV Commodity Index reconstruction.

Pure math — no I/O. Caller supplies current commodity prices and we
return a reconstructed index value, anchored to a known historical
(date, index_value) pair.

Methodology summary (per Truflation v1.41):
  - Index = arithmetic mean of futures prices for a basket of EV
    battery metals (copper, lithium, nickel, cobalt, palladium,
    platinum), weighted by per-vehicle metal intensity × prior-year
    EV-type production share.
  - Weights rebalance quarterly (Jan/Apr/Jul/Oct 1).
  - Daily publication; Kalshi binaries close ~7:59 PM EDT day-of and
    settle on the next day's print.

Phase 1 simplification: we model only the four cleanly-yfinance-
available components (Cu, Li, Pd, Pt). Their weights are renormalized
to sum to 1.0, effectively assuming nickel + cobalt move with the
basket. That's a ~20% basket-coverage gap that biases us when nickel/
cobalt diverge from the rest. The smoke CLI surfaces the implied
delta vs Kalshi mids so the operator can spot drift.

Reconstruction formula (anchored multiplicative):

    index_today = anchor_index_value × Σᵢ wᵢ × (priceᵢ_today / priceᵢ_anchor)

where the sum runs over the modeled components and weights sum to 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TruEvAnchor:
    """Calibration anchor for the multiplicative index reconstruction.

    Holds:
      - `anchor_date`: ISO YYYY-MM-DD of the anchor day. Used for logging
        and operator visibility; the date itself isn't read by the math.
      - `anchor_index_value`: the published Truflation index value on the
        anchor day. e.g. 1290.40.
      - `anchor_prices`: closing futures prices for each modeled
        commodity on the anchor day. Keys MUST match the symbols in
        the corresponding TruEvWeights.
    """
    anchor_date: str
    anchor_index_value: float
    anchor_prices: Mapping[str, float]

    def __post_init__(self) -> None:
        if self.anchor_index_value <= 0:
            raise ValueError(
                f"anchor_index_value must be > 0, got {self.anchor_index_value}"
            )
        for sym, p in self.anchor_prices.items():
            if p <= 0:
                raise ValueError(
                    f"anchor price for {sym!r} must be > 0, got {p}"
                )


@dataclass(frozen=True)
class TruEvWeights:
    """Per-component basket weights for one quarterly rebalance window.

    Weights MUST sum to 1.0 within float tolerance. Symbols MUST be the
    same set as the keys in the corresponding TruEvAnchor.anchor_prices.

    `quarter_start_iso` is informational — operator updates the weights
    table manually each quarter per Truflation's published methodology.
    """
    quarter_start_iso: str
    weights: Mapping[str, float]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"weights must sum to 1.0; got {total} from {dict(self.weights)}"
            )
        for sym, w in self.weights.items():
            if w < 0 or w > 1:
                raise ValueError(
                    f"weight for {sym!r} must be in [0, 1], got {w}"
                )


def reconstruct_index(
    current_prices: Mapping[str, float],
    weights: TruEvWeights,
    anchor: TruEvAnchor,
) -> float:
    """Anchored multiplicative index reconstruction.

    Returns the today-implied index value:
        anchor_index_value × Σᵢ wᵢ × (priceᵢ_today / priceᵢ_anchor)

    Raises ValueError if any modeled symbol is missing from
    `current_prices` or `anchor.anchor_prices`. Caller should gate on
    forward-source freshness BEFORE calling this — passing in stale
    prices produces a stale index value, not an error.
    """
    # Validate symbol coverage
    expected = set(weights.weights.keys())
    missing_today = expected - set(current_prices.keys())
    missing_anchor = expected - set(anchor.anchor_prices.keys())
    if missing_today:
        raise ValueError(
            f"current_prices missing modeled symbols: {sorted(missing_today)}"
        )
    if missing_anchor:
        raise ValueError(
            f"anchor.anchor_prices missing modeled symbols: {sorted(missing_anchor)}"
        )

    basket_return = 0.0
    for sym, w in weights.weights.items():
        p_today = current_prices[sym]
        p_anchor = anchor.anchor_prices[sym]
        if p_today <= 0:
            raise ValueError(
                f"current_prices[{sym!r}] must be > 0, got {p_today}"
            )
        # p_anchor > 0 guaranteed by TruEvAnchor.__post_init__
        basket_return += w * (p_today / p_anchor)

    return anchor.anchor_index_value * basket_return


# ── Phase-1 default weights + anchor ────────────────────────────────
#
# Phase 1 models 4 of the 6 components, with weights renormalized to
# sum to 1.0. Original Q4-2025 weights (per Truflation v1.41 §6.3):
#   Copper      0.3865    HG=F (Comex futures)
#   Lithium     0.3354    LIT  (Global X Lithium ETF — proxy)
#   Nickel      0.1227    (excluded — no clean yfinance ticker)
#   Cobalt      0.0822    (excluded — no clean yfinance ticker)
#   Palladium   0.0607    PA=F
#   Platinum    0.0125    PL=F
# Modeled subset sums to 0.7951; we divide each by 0.7951 to renormalize.
_Q4_2025_RAW = {
    "HG=F": 0.3865,   # Copper
    "LIT":  0.3354,   # Lithium ETF proxy (was LTH=F, dropped — too illiquid)
    "PA=F": 0.0607,   # Palladium
    "PL=F": 0.0125,   # Platinum
}
_Q4_2025_TOTAL = sum(_Q4_2025_RAW.values())
DEFAULT_WEIGHTS_Q4_2025 = TruEvWeights(
    quarter_start_iso="2025-10-01",
    weights={k: v / _Q4_2025_TOTAL for k, v in _Q4_2025_RAW.items()},
)

# Default anchor — bootstrapped on 2026-05-07 from live yfinance prints.
# anchor_index_value of 1290.40 was the prior research figure; the
# backtest auto-calibrates a better one. Operator should replace with
# a fresh truflation.com value before going live.
DEFAULT_ANCHOR_PLACEHOLDER = TruEvAnchor(
    anchor_date="2026-05-07",
    # 1281.98 was the RMSE-minimizing anchor from the 2026-04-15 →
    # 2026-05-06 backtest (RMSE 13.2 points, 17 daily settlements,
    # against the LIT-as-lithium 4-component basket). Should be
    # refreshed any time the basket weights change (quarterly) or
    # nickel/cobalt feeds are added (Phase 2).
    anchor_index_value=1281.9841,
    anchor_prices={
        "HG=F": 6.20,     # 2026-05-07 yfinance closes
        "LIT": 90.57,
        "PA=F": 1555.50,
        "PL=F": 2073.50,
    },
)
