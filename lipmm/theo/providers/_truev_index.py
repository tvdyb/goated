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
# Q4-2025 weights per Truflation v1.41 §6.3.
# Six components total. Sources:
#   Copper      0.3865    HG=F      (yfinance Comex)
#   Lithium     0.3354    LIT       (yfinance Global X Lithium ETF — proxy
#                                    for CME LTH=F which is too illiquid)
#   Nickel      0.1227    NICK.L    (yfinance WisdomTree Nickel ETC, LSE)
#   Cobalt      0.0822    COBALT_TE (TradingEconomics scrape — LIVE ONLY,
#                                    no historicals; backtest excludes
#                                    cobalt and renormalizes the other 5)
#   Palladium   0.0607    PA=F      (yfinance NYMEX)
#   Platinum    0.0125    PL=F      (yfinance NYMEX)
# Sum of LIVE weights = 1.0. Sum of BACKTEST weights (cobalt excluded
# and renormalized) is also 1.0 — see DEFAULT_WEIGHTS_BACKTEST.
_Q4_2025_RAW = {
    "HG=F":       0.3865,
    "LITHIUM_TE": 0.3354,   # was "LIT" — now TE China lithium spot
    "NICK.L":     0.1227,
    "COBALT_TE":  0.0822,
    "PA=F":       0.0607,
    "PL=F":       0.0125,
}
DEFAULT_WEIGHTS_Q4_2025 = TruEvWeights(
    quarter_start_iso="2025-10-01",
    weights=dict(_Q4_2025_RAW),
)

# Q1 2026 weights — fitted via NNLS regression against operator-supplied
# `indexAndBasket.csv` (118 clean days of actuals + all 6 components,
# Jan 1 → Apr 28, 2026). In-sample RMSE = 4.46 pts (0.37%). Bias ≈ 0.
#
# These weights reflect the **Dec 31, 2025 quarterly rebalance** that
# set the EV-type production mix to:
#     HEV   53.99%
#     BEV   27.97%
#     PHEV  18.01%
#     FCEV   0.03%
#
# No further rebalance has occurred between then and the time these
# weights were fit, so all 118 days share the same true weight vector
# and the whole-period regression is the most-data estimate available.
# (Earlier subset-fits suggesting "Q1 vs Q2 divergence" were small-
# sample regression noise, NOT a real rebalance.)
#
# Compared to Q4 2025: copper jumped 39% → 57% (HEVs are Cu-heavy with
# minimal battery), lithium collapsed 34% → 5% (HEVs use small NiMH
# instead of Li-ion packs). Treating Q4 weights as a default for Q1
# produces meaningfully wrong theos.
_Q1_2026_FITTED_RAW = {
    "HG=F":       0.57336,    # Copper — biggest contributor; HEVs Cu-heavy
    "NICK.L":     0.21884,    # Nickel
    "COBALT_TE":  0.07736,    # Cobalt
    "PA=F":       0.07512,    # Palladium
    "LITHIUM_TE": 0.04943,    # Lithium — collapsed from Q4 due to HEV mix
    "PL=F":       0.00776,    # Platinum
}
_Q1_TOTAL = sum(_Q1_2026_FITTED_RAW.values())
DEFAULT_WEIGHTS_Q1_2026 = TruEvWeights(
    quarter_start_iso="2026-01-01",
    weights={k: v / _Q1_TOTAL for k, v in _Q1_2026_FITTED_RAW.items()},
)

# Live default: ship Q1 2026 weights, since the rebalance happened on
# Dec 31, 2025 and these are what's actually driving the published
# index right now. Q4_2025 stays in the file for historical reference
# and downstream tests that pinned the Q4 numbers.
DEFAULT_WEIGHTS_LIVE = DEFAULT_WEIGHTS_Q1_2026

# Backtest weights: cobalt excluded (no daily history) AND lithium
# substituted back to LIT (the equity proxy is the only lithium series
# with yfinance history). Other 4 weights renormalized to sum to 1.0.
# Used by deploy/truev_backtest_csv.py + deploy/truev_backtest.py —
# both walk historical data, both predate the live TE-lithium swap.
_BACKTEST_RAW = {
    "HG=F":   _Q4_2025_RAW["HG=F"],
    "LIT":    _Q4_2025_RAW["LITHIUM_TE"],   # proxy substitution
    "NICK.L": _Q4_2025_RAW["NICK.L"],
    "PA=F":   _Q4_2025_RAW["PA=F"],
    "PL=F":   _Q4_2025_RAW["PL=F"],
}
_BACKTEST_TOTAL = sum(_BACKTEST_RAW.values())
DEFAULT_WEIGHTS_BACKTEST = TruEvWeights(
    quarter_start_iso="2025-10-01",
    weights={k: v / _BACKTEST_TOTAL for k, v in _BACKTEST_RAW.items()},
)

# Default anchor — bootstrapped on 2026-05-07 from live data.
# Operator should refresh with a fresh truflation.com value when
# quarterly weights change or basket coverage shifts.
DEFAULT_ANCHOR_PLACEHOLDER = TruEvAnchor(
    # **CRITICAL**: anchor MUST be a real (date, published TruEV value,
    # same-day component closes) triple. Truflation publishes the
    # index ONCE per day at end-of-day; an RMSE-minimizing fit across
    # multiple days is NOT a valid anchor — it produces an inflated
    # base value that biases today's reconstructed index above truth.
    #
    # Re-anchor each morning before bot start: pull yesterday's
    # truflation.com EV-index close + yesterday's yfinance closes for
    # each component, plug in here.
    anchor_date="2026-05-10",
    anchor_index_value=1264.69,  # truflation.com/marketplace/ev-index,
                                 # operator-confirmed value as of
                                 # 2026-05-10 (most recent Truflation
                                 # print before the May 11 settle window).
    anchor_prices={
        # Yfinance closes for the most recent trading day (2026-05-08;
        # markets were closed Sat-Sun). These are what the May 10
        # truflation print is based on (Truflation can't refresh on
        # weekends; the 1264.69 reflects the Fri-EOD basket).
        "HG=F": 6.249,             # 2026-05-08 yfinance Comex copper close
        "LITHIUM_TE": 194_000.0,   # current TE China carbonate spot
                                   # (proxy for May 8 EOD; TE has no
                                   # historicals so we accept this
                                   # latent staleness — when TE next
                                   # ticks, the model will absorb the
                                   # move with this anchor as baseline.)
        "NICK.L": 0.22427,         # = 16.545 GBp × GBPUSD_2026-05-08
                                   # (1.355565) / 100 = USD per share.
                                   # FX-stripped via the same conversion
                                   # the live forward source applies.
        "COBALT_TE": 56_290.0,     # current TE LME cobalt spot (proxy
                                   # for May 8 EOD — cobalt has been
                                   # flat for over a week so the
                                   # latent staleness is lossless).
        "PA=F": 1482.60,           # 2026-05-08 NYMEX palladium close
        "PL=F": 2047.20,           # 2026-05-08 NYMEX platinum close
    },
)
