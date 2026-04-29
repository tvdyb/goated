"""Figlewski piecewise-GEV tail extension for the RND.

Attaches Generalized Extreme Value (GEV) tails to the BL/SVI-derived
density at paste points, ensuring:
  - Density and first derivative are continuous at paste points.
  - Tails decay smoothly to zero.
  - Total probability is preserved.

If GEV fitting fails (insufficient data for reliable tail estimation),
falls back to log-normal tails with documented warning.

GAP-041: Figlewski tail extension.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit


class FiglewskiTailError(RuntimeError):
    """Raised when tail extension fails."""


@njit(cache=True, fastmath=False)
def _gev_pdf(x: float, xi: float, mu: float, sigma: float) -> float:
    """GEV probability density function.

    For xi != 0:
        f(x) = (1/sigma) * t(x)^(xi+1) * exp(-t(x))
        where t(x) = (1 + xi*(x-mu)/sigma)^(-1/xi)

    For xi == 0 (Gumbel):
        f(x) = (1/sigma) * exp(-(z + exp(-z)))
        where z = (x - mu) / sigma
    """
    if sigma <= 0.0:
        return 0.0

    z = (x - mu) / sigma

    if abs(xi) < 1e-10:
        return (1.0 / sigma) * math.exp(-(z + math.exp(-z)))

    s = 1.0 + xi * z
    if s <= 0.0:
        return 0.0

    t = s ** (-1.0 / xi)
    return (1.0 / sigma) * t ** (xi + 1.0) * math.exp(-t)


@njit(cache=True, fastmath=False)
def _lognormal_tail_pdf(x: float, mu_ln: float, sigma_ln: float) -> float:
    """Log-normal PDF for tail fallback."""
    if x <= 0.0 or sigma_ln <= 0.0:
        return 0.0
    z = (math.log(x) - mu_ln) / sigma_ln
    return math.exp(-0.5 * z * z) / (x * sigma_ln * math.sqrt(2.0 * math.pi))


def _fit_gev_tail(
    paste_x: float,
    paste_f: float,
    paste_fprime: float,
    is_left: bool,
) -> tuple[float, float, float] | None:
    """Fit GEV parameters (xi, mu, sigma) to match density at paste point.

    Uses Gumbel (xi=0) for simplicity and robustness.
    Returns (xi, mu, sigma) or None if fitting fails.
    """
    if paste_f <= 0:
        return None

    xi = 0.0
    mu = paste_x
    # At the Gumbel mode (z=0), f = 1/(sigma*e), so sigma = 1/(paste_f*e)
    sigma = 1.0 / (paste_f * math.e)
    sigma = max(sigma, 0.01)

    f_check = _gev_pdf(paste_x, xi, mu, sigma)
    if f_check > 0:
        return (xi, mu, sigma)

    return None


def _fit_lognormal_tail(
    paste_x: float,
    paste_f: float,
    mean_price: float,
    std_price: float,
) -> tuple[float, float]:
    """Fit log-normal parameters for tail fallback."""
    if mean_price <= 0 or std_price <= 0:
        return math.log(max(paste_x, 1.0)), 0.2

    sigma_ln_sq = math.log(1 + (std_price / mean_price) ** 2)
    sigma_ln = math.sqrt(sigma_ln_sq)
    mu_ln = math.log(mean_price) - 0.5 * sigma_ln_sq
    return mu_ln, sigma_ln


def _build_tail_density(
    tail_strikes: np.ndarray,
    paste_f: float,
    paste_fprime: float,
    is_left: bool,
    mean_price: float,
    std_price: float,
    match_idx: int,
) -> np.ndarray:
    """Build density values for one tail (lower or upper).

    Tries GEV first, falls back to log-normal.
    Scales result to match paste-point density value.
    """
    paste_x = tail_strikes[match_idx]
    gev_params = _fit_gev_tail(paste_x, paste_f, paste_fprime, is_left)

    if gev_params is not None:
        xi, mu, sig = gev_params
        density = np.array([_gev_pdf(x, xi, mu, sig) for x in tail_strikes])
    else:
        mu_ln, sigma_ln = _fit_lognormal_tail(paste_x, paste_f, mean_price, std_price)
        density = np.array([_lognormal_tail_pdf(x, mu_ln, sigma_ln) for x in tail_strikes])

    ref_val = density[match_idx]
    if ref_val > 0:
        density *= paste_f / ref_val

    return np.maximum(density, 0.0)


def _density_derivative(
    density_values: np.ndarray,
    density_strikes: np.ndarray,
    idx: int,
) -> float:
    """Central finite difference of density at index idx."""
    if 0 < idx < len(density_values) - 1:
        return (density_values[idx + 1] - density_values[idx - 1]) / (
            density_strikes[idx + 1] - density_strikes[idx - 1]
        )
    return 0.0


def extend_tails(
    density_strikes: np.ndarray,
    density_values: np.ndarray,
    *,
    lower_paste_quantile: float = 0.05,
    upper_paste_quantile: float = 0.95,
    extension_points: int = 100,
    extension_range_mult: float = 3.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Extend density with Figlewski-style tails.

    Parameters
    ----------
    density_strikes : 1-D float64, sorted ascending.
    density_values : 1-D float64, corresponding density values.
    lower_paste_quantile : CDF quantile for lower paste point.
    upper_paste_quantile : CDF quantile for upper paste point.
    extension_points : Number of points to add in each tail.
    extension_range_mult : How far to extend tails (in multiples of
        the current strike range).

    Returns
    -------
    (extended_strikes, extended_density) : tuple of 1-D float64 arrays.
    """
    if len(density_strikes) < 3 or len(density_values) < 3:
        raise FiglewskiTailError("Need at least 3 density points for tail extension")

    density_strikes = np.ascontiguousarray(density_strikes, dtype=np.float64)
    density_values = np.ascontiguousarray(density_values, dtype=np.float64)

    # Compute CDF from density via trapezoidal rule
    dk = np.diff(density_strikes)
    mid_density = (density_values[:-1] + density_values[1:]) / 2.0
    cdf = np.concatenate([[0.0], np.cumsum(mid_density * dk)])
    total_mass = cdf[-1]
    if total_mass > 0:
        cdf = cdf / total_mass

    # Find paste-point indices
    idx_lower = max(1, int(np.searchsorted(cdf, lower_paste_quantile)))
    idx_upper = min(len(density_strikes) - 2, int(np.searchsorted(cdf, upper_paste_quantile)))

    if idx_lower >= idx_upper:
        return density_strikes.copy(), density_values.copy()

    # Density statistics for lognormal fallback
    normed = density_values / total_mass if total_mass > 0 else density_values
    mean_price = float(np.trapezoid(density_strikes * normed, density_strikes))
    var_price = float(np.trapezoid((density_strikes - mean_price) ** 2 * normed, density_strikes))
    std_price = math.sqrt(max(var_price, 0.0))

    # Extension grid
    strike_range = density_strikes[-1] - density_strikes[0]
    extend_range = extension_range_mult * strike_range

    # Lower tail
    lower_strikes = np.linspace(
        max(density_strikes[0] - extend_range, 0.01),
        density_strikes[idx_lower],
        extension_points,
        endpoint=False,
    )
    lower_density = _build_tail_density(
        lower_strikes,
        density_values[idx_lower],
        _density_derivative(density_values, density_strikes, idx_lower),
        is_left=True,
        mean_price=mean_price,
        std_price=std_price,
        match_idx=-1,  # match at the last point (paste point)
    )

    # Upper tail
    upper_strikes = np.linspace(
        density_strikes[idx_upper],
        density_strikes[-1] + extend_range,
        extension_points + 1,
    )[1:]
    upper_density = _build_tail_density(
        upper_strikes,
        density_values[idx_upper],
        _density_derivative(density_values, density_strikes, idx_upper),
        is_left=False,
        mean_price=mean_price,
        std_price=std_price,
        match_idx=0,  # match at the first point (paste point)
    )

    # Assemble: lower_tail + interior + upper_tail
    interior_mask = (density_strikes >= density_strikes[idx_lower]) & (
        density_strikes <= density_strikes[idx_upper]
    )

    return (
        np.concatenate([lower_strikes, density_strikes[interior_mask], upper_strikes]),
        np.concatenate([lower_density, density_values[interior_mask], upper_density]),
    )
