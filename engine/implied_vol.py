"""Kalshi-implied volatility calibration.

Back-calculates annualized vol from Kalshi orderbook mid-prices on
near-ATM strikes using bisection on the Black-76 survival formula:

    P(S > K) = N(d2)  where  d2 = (ln(F/K) - 0.5*sig^2*T) / (sig*sqrt(T))

Runs once per cycle (30s) — bisection is fine here (not hot-path).
"""

from __future__ import annotations

import logging
import math

from scipy.special import ndtr

from engine.seasonal_vol import clamp_vol, get_seasonal_vol_midpoint

logger = logging.getLogger("engine.implied_vol")

# Bisection bounds for annualized vol
_VOL_LO = 0.01
_VOL_HI = 1.50

# Convergence
_BISECT_TOL = 1e-6
_BISECT_MAX_ITER = 60

# Sanity bounds on calibrated vol
_VOL_MIN = 0.05
_VOL_MAX = 0.80

# Default fallback (used only when no month is provided)
DEFAULT_VOL = 0.15

# Only use strikes within this many $/bu of forward
_ATM_WINDOW = 0.10  # 10 cents


def _survival_prob(forward: float, strike: float, tau: float, sigma: float) -> float:
    """P(S > K) under GBM = N(d2)."""
    sig_sqrt_t = sigma * math.sqrt(tau)
    if sig_sqrt_t < 1e-15:
        return 1.0 if forward > strike else 0.0
    d2 = (math.log(forward / strike) - 0.5 * sigma**2 * tau) / sig_sqrt_t
    return float(ndtr(d2))


def _implied_vol_bisect(
    forward: float,
    strike: float,
    tau: float,
    market_prob: float,
) -> float | None:
    """Bisect for sigma such that N(d2) ≈ market_prob.

    Returns None if bisection fails to converge or result is outside
    [_VOL_MIN, _VOL_MAX].
    """
    if market_prob <= 0.01 or market_prob >= 0.99:
        return None
    if tau <= 0.0 or forward <= 0.0 or strike <= 0.0:
        return None

    lo, hi = _VOL_LO, _VOL_HI

    for _ in range(_BISECT_MAX_ITER):
        mid = (lo + hi) / 2.0
        model_prob = _survival_prob(forward, strike, tau, mid)
        diff = model_prob - market_prob

        if abs(diff) < _BISECT_TOL:
            break

        # Higher vol -> survival prob moves toward 0.5
        # If strike <= forward (ATM/ITM "above K"), higher vol lowers survival
        # If strike > forward (OTM "above K"), higher vol raises survival
        if strike <= forward:
            # ATM/ITM: higher vol decreases survival prob
            if model_prob > market_prob:
                lo = mid  # need more vol to decrease prob
            else:
                hi = mid
        else:
            # OTM: higher vol increases survival prob
            if model_prob < market_prob:
                lo = mid  # need more vol to increase prob
            else:
                hi = mid

    sigma = (lo + hi) / 2.0
    if sigma < _VOL_MIN or sigma > _VOL_MAX:
        return None
    return sigma


def calibrate_vol(
    forward: float,
    strike_mids: list[tuple[float, float]],
    tau: float,
    fallback: float = DEFAULT_VOL,
    month: int | None = None,
) -> float:
    """Calibrate annualized vol from Kalshi near-ATM strikes.

    Args:
        forward: Forward price in $/bu (e.g. 10.67).
        strike_mids: List of (strike, market_mid) where strike is in $/bu
            and market_mid is the survival probability (0-1 scale, e.g. 0.45).
        tau: Time to expiry in years (e.g. 2/365).
        fallback: Vol to return if calibration fails (ignored when month is set;
            seasonal midpoint is used instead).
        month: Calendar month (1-12) for seasonal vol regime. When provided,
            the seasonal midpoint replaces the flat fallback and the calibrated
            vol is clamped to seasonal [floor, ceiling].

    Returns:
        Calibrated annualized vol, or seasonal/flat fallback if calibration fails.
    """
    effective_fallback = get_seasonal_vol_midpoint(month) if month is not None else fallback

    if tau <= 0.0 or forward <= 0.0:
        logger.warning("IMPLIED VOL: invalid inputs (forward=%.4f, tau=%.4f), using fallback", forward, tau)
        return effective_fallback

    # Filter to near-ATM strikes
    near_atm = [
        (k, mid) for k, mid in strike_mids
        if abs(k - forward) <= _ATM_WINDOW and 0.02 < mid < 0.98
    ]

    if len(near_atm) < 3:
        logger.info(
            "IMPLIED VOL: only %d near-ATM strikes (need 3), using fallback %.1f%%",
            len(near_atm), effective_fallback * 100,
        )
        return effective_fallback

    # Bisect for vol on each near-ATM strike
    vols: list[float] = []
    weights: list[float] = []

    for strike, market_mid in near_atm:
        iv = _implied_vol_bisect(forward, strike, tau, market_mid)
        if iv is not None:
            vols.append(iv)
            # Weight by how close to ATM (closer = more informative)
            dist = abs(strike - forward)
            w = 1.0 / (dist + 0.001)  # avoid division by zero
            weights.append(w)

    if len(vols) < 2:
        logger.info(
            "IMPLIED VOL: only %d valid bisections (need 2), using fallback %.1f%%",
            len(vols), effective_fallback * 100,
        )
        return effective_fallback

    # Weighted average
    total_w = sum(weights)
    calibrated = sum(v * w for v, w in zip(vols, weights)) / total_w

    # Final sanity check
    if calibrated < _VOL_MIN or calibrated > _VOL_MAX:
        logger.warning(
            "IMPLIED VOL: calibrated %.1f%% outside [%.0f%%, %.0f%%], using fallback",
            calibrated * 100, _VOL_MIN * 100, _VOL_MAX * 100,
        )
        return effective_fallback

    # Apply seasonal clamp if month provided
    if month is not None:
        clamped = clamp_vol(calibrated, month)
        if clamped != calibrated:
            logger.info(
                "IMPLIED VOL: clamped %.1f%% -> %.1f%% by seasonal regime (month=%d)",
                calibrated * 100, clamped * 100, month,
            )
            calibrated = clamped

    logger.info(
        "IMPLIED VOL: calibrated %.1f%% from %d strikes (of %d near-ATM)",
        calibrated * 100, len(vols), len(near_atm),
    )
    return calibrated


def extract_strike_mids_from_orderbooks(
    kalshi_strikes: list[float],
    market_tickers: dict[float, str],
    orderbooks: dict[str, dict],
) -> list[tuple[float, float]]:
    """Extract (strike, mid_probability) pairs from Kalshi orderbook data.

    Args:
        kalshi_strikes: Strike prices in $/bu.
        market_tickers: Strike -> Kalshi market ticker mapping.
        orderbooks: ticker -> {"best_bid": int, "best_ask": int, ...} in cents.

    Returns:
        List of (strike, mid_prob) where mid_prob is in [0, 1].
    """
    result: list[tuple[float, float]] = []
    for strike in kalshi_strikes:
        ticker = market_tickers.get(strike, "")
        if not ticker:
            continue
        ob = orderbooks.get(ticker, {})
        best_bid = ob.get("best_bid", 0)
        best_ask = ob.get("best_ask", 100)

        # Skip illiquid strikes (no bid or no ask)
        if best_bid <= 0 or best_ask >= 100:
            continue
        # Skip crossed/locked books
        if best_bid >= best_ask:
            continue

        mid_cents = (best_bid + best_ask) / 2.0
        mid_prob = mid_cents / 100.0
        result.append((strike, mid_prob))

    return result
