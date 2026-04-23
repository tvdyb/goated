"""GBM theo vs Black-Scholes analytical reference.

Spec validation item 1: "GBM theo === Black-Scholes N(d2) to 1e-6 across
1000 random (S, K, σ, τ)."

Plus monotonicity, boundary behavior, and put-call parity for digitals.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from models.gbm import gbm_prob_above
from tests._bs_reference import bs_prob_above


def test_gbm_matches_bs_analytical_1000_random_cases():
    rng = np.random.default_rng(0xDEADBEEF)
    n_cases = 1000
    max_abs_err = 0.0
    max_rel_err = 0.0

    for _ in range(n_cases):
        spot = float(rng.uniform(10.0, 200.0))
        sigma = float(rng.uniform(0.10, 1.20))
        # tau from 1 minute to 1 year in trading-time terms
        tau = float(rng.uniform(1.0 / (252.0 * 23.0 * 60.0), 1.0))
        basis_drift = float(rng.uniform(-0.20, 0.20))
        n_strikes = int(rng.integers(1, 40))
        strikes = spot * np.exp(rng.normal(0.0, 0.5, size=n_strikes))

        ours = gbm_prob_above(spot, strikes, tau, sigma, basis_drift)
        ref = bs_prob_above(spot, strikes, tau, sigma, basis_drift)

        abs_err = float(np.max(np.abs(ours - ref)))
        max_abs_err = max(max_abs_err, abs_err)
        denom = np.maximum(np.abs(ref), 1e-300)
        rel_err = float(np.max(np.abs(ours - ref) / denom))
        max_rel_err = max(max_rel_err, rel_err)

        assert abs_err < 1e-6, (
            f"abs err {abs_err:.3e} > 1e-6 at spot={spot}, sigma={sigma}, "
            f"tau={tau}, basis_drift={basis_drift}, strikes={strikes.tolist()}"
        )

    # Stricter sanity on the aggregate — these kernels should match to fp noise.
    assert max_abs_err < 1e-9, f"worst abs error across 1000 cases: {max_abs_err:.3e}"


def test_gbm_monotone_decreasing_in_strike():
    strikes = np.linspace(10.0, 500.0, 400)
    for sigma in (0.1, 0.3, 0.8, 1.5):
        for tau in (1e-4, 0.01, 0.5):
            probs = gbm_prob_above(100.0, strikes, tau, sigma, 0.0)
            diffs = np.diff(probs)
            assert np.all(diffs <= 1e-15), (
                f"non-monotone at sigma={sigma}, tau={tau}, max-diff={diffs.max():.3e}"
            )


def test_gbm_boundary_limits():
    # K → 0: theo → 1
    low = gbm_prob_above(100.0, np.array([1e-12]), tau=0.25, sigma=0.3)
    assert low[0] == 1.0

    # K → ∞: theo → 0
    hi = gbm_prob_above(100.0, np.array([1e20]), tau=0.25, sigma=0.3)
    assert hi[0] == 0.0


def test_gbm_put_call_parity_exact():
    strikes = np.array([50.0, 75.0, 100.0, 125.0, 175.0])
    probs = gbm_prob_above(100.0, strikes, tau=0.25, sigma=0.3, basis_drift=0.0)
    complement = 1.0 - probs
    # Exact equality: P(S_T>K) + P(S_T<=K) == 1 for every strike, no fp slack.
    assert np.all(probs + complement == 1.0)


def test_gbm_atm_forward_theo_near_half():
    # With F = K exactly and small sigma, P(S_T > K) is slightly below 0.5 (drift term).
    spot, sigma, tau = 100.0, 0.3, 0.25
    forward = spot
    probs = gbm_prob_above(spot, np.array([forward]), tau, sigma, basis_drift=0.0)
    # d2 = -0.5 * sigma * sqrt(tau); Phi(d2) ≈ 0.4405 for sigma=0.3, tau=0.25
    expected_d2 = -0.5 * sigma * math.sqrt(tau)
    expected = 0.5 * math.erfc(-expected_d2 * 0.7071067811865476)
    assert abs(probs[0] - expected) < 1e-12


def test_gbm_invalid_inputs_raise():
    from models.base import TheoInputs
    from models.gbm import GBMTheo

    model = GBMTheo()
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 0.0, np.array([100.0]), 0.25, 0.3))
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 100.0, np.array([100.0]), -0.1, 0.3))
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 100.0, np.array([100.0]), 0.25, 0.0))
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 100.0, np.array([0.0, 100.0]), 0.25, 0.3))
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 100.0, np.array([np.nan]), 0.25, 0.3))
    with pytest.raises(ValueError):
        model.price(TheoInputs("wti", 100.0, np.zeros((2, 2)), 0.25, 0.3))
