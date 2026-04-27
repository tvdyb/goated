from __future__ import annotations

import math

import numpy as np
import pytest

from trufaidp.basket_gbm import basket_gbm_prob_above


def _identity_corr(m: int) -> np.ndarray:
    return np.eye(m, dtype=np.float64)


def test_single_asset_matches_lognormal_closed_form():
    quantities = np.array([1.0])
    spots = np.array([60.0])
    sigmas = np.array([0.8])
    corr = _identity_corr(1)
    tau = 1.0 / 365.0
    strikes = np.array([55.0, 60.0, 65.0])

    p = basket_gbm_prob_above(quantities, spots, sigmas, corr, tau, strikes)

    sigma = sigmas[0]
    F = spots[0]
    for i, k in enumerate(strikes):
        d2 = (math.log(F / k) - 0.5 * sigma * sigma * tau) / (sigma * math.sqrt(tau))
        expected = 0.5 * math.erfc(-d2 / math.sqrt(2.0))
        assert p[i] == pytest.approx(expected, abs=1e-12)


def test_monotone_decreasing_in_strike():
    quantities = np.array([2.0, 5.0, 0.1, 30.0, 100.0, 8.0])
    spots = np.array([0.5, 3.0, 220.0, 1.5, 0.05, 4.0])
    sigmas = np.array([1.0, 0.9, 1.1, 0.8, 1.2, 1.0])
    corr = 0.4 * np.ones((6, 6)) + 0.6 * np.eye(6)
    tau = 5.0 / 365.0
    strikes = np.linspace(40.0, 80.0, 15)

    p = basket_gbm_prob_above(quantities, spots, sigmas, corr, tau, strikes)
    assert np.all(np.diff(p) <= 1e-12)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_zero_vol_collapses_to_indicator():
    quantities = np.array([1.0, 1.0, 1.0])
    spots = np.array([20.0, 20.0, 20.0])
    sigmas = np.array([0.0, 0.0, 0.0])
    corr = _identity_corr(3)
    tau = 0.01
    strikes = np.array([55.0, 60.0, 60.0001, 65.0])

    p = basket_gbm_prob_above(quantities, spots, sigmas, corr, tau, strikes)
    expected_index = 60.0
    expected = np.array([1.0 if expected_index > k else 0.0 for k in strikes])
    np.testing.assert_array_equal(p, expected)


def test_higher_correlation_widens_distribution():
    quantities = np.array([1.0, 1.0])
    spots = np.array([30.0, 30.0])
    sigmas = np.array([1.0, 1.0])
    tau = 1.0 / 52.0
    strikes = np.array([80.0])

    corr_low = np.array([[1.0, 0.0], [0.0, 1.0]])
    corr_high = np.array([[1.0, 0.95], [0.95, 1.0]])

    p_low = basket_gbm_prob_above(quantities, spots, sigmas, corr_low, tau, strikes)[0]
    p_high = basket_gbm_prob_above(quantities, spots, sigmas, corr_high, tau, strikes)[0]
    assert p_high > p_low


def test_validates_inputs():
    q = np.array([1.0, 1.0])
    s = np.array([10.0, 10.0])
    v = np.array([0.5, 0.5])
    c = np.eye(2)
    k = np.array([20.0])

    with pytest.raises(ValueError):
        basket_gbm_prob_above(q, s, v, c, -1.0, k)
    with pytest.raises(ValueError):
        basket_gbm_prob_above(q, np.array([0.0, 10.0]), v, c, 1e-3, k)
    with pytest.raises(ValueError):
        basket_gbm_prob_above(q, s, v, np.eye(3), 1e-3, k)
    with pytest.raises(ValueError):
        basket_gbm_prob_above(q, s, v, c, 1e-3, np.array([0.0]))
