from __future__ import annotations

import pytest

from trufaidp.index import calibrate_quantities, reconstruct, stack_arrays


def test_calibrate_then_reconstruct_recovers_anchor():
    prices = {"FET": 0.40, "RENDER": 3.0, "TAO": 220.0, "AKT": 1.5, "AIOZ": 0.05, "PRIME": 4.0}
    weights = {"FET": 0.20, "RENDER": 0.20, "TAO": 0.25, "AKT": 0.15, "AIOZ": 0.10, "PRIME": 0.10}
    index_value = 60.0

    q = calibrate_quantities(index_value, prices, weights)
    assert reconstruct(q, prices) == pytest.approx(index_value, rel=1e-12)

    for sym, n in q.items():
        contribution = n * prices[sym]
        assert contribution == pytest.approx(weights[sym] * index_value, rel=1e-12)


def test_reconstruct_scales_with_prices():
    q = {"A": 2.0, "B": 5.0}
    p1 = {"A": 10.0, "B": 4.0}
    p2 = {"A": 20.0, "B": 8.0}
    assert reconstruct(q, p2) == pytest.approx(2.0 * reconstruct(q, p1))


def test_calibrate_rejects_bad_weights():
    with pytest.raises(ValueError):
        calibrate_quantities(60.0, {"A": 1.0}, {"A": 0.5})
    with pytest.raises(ValueError):
        calibrate_quantities(60.0, {"A": 1.0}, {"B": 1.0})


def test_stack_arrays_orders_by_symbols():
    syms = ["A", "B", "C"]
    q = {"C": 3.0, "A": 1.0, "B": 2.0}
    p = {"A": 10.0, "B": 20.0, "C": 30.0}
    s = {"A": 0.5, "B": 0.6, "C": 0.7}
    corr = [[1.0, 0.1, 0.2], [0.1, 1.0, 0.3], [0.2, 0.3, 1.0]]

    qa, pa, sa, ca = stack_arrays(syms, q, p, s, corr)
    assert list(qa) == [1.0, 2.0, 3.0]
    assert list(pa) == [10.0, 20.0, 30.0]
    assert list(sa) == [0.5, 0.6, 0.7]
    assert ca.shape == (3, 3)
