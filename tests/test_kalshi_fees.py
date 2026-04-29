"""Tests for fees.kalshi_fees -- ACT-10.

Covers taker fee, maker fee, round-trip cost, edge cases, FeeSchedule
config loading, and fail-loud behavior on invalid inputs.
"""

from __future__ import annotations

import math

import pytest

from fees.kalshi_fees import (
    FeeSchedule,
    maker_fee,
    round_trip_cost,
    taker_fee,
)


# ---------------------------------------------------------------------------
# Taker fee
# ---------------------------------------------------------------------------


class TestTakerFee:
    def test_midpoint(self) -> None:
        """P=0.50: ceil(0.07 * 0.25 * 100) / 100 = ceil(1.75)/100 = 0.02."""
        assert taker_fee(0.50) == 0.02

    def test_p022(self) -> None:
        """Worked example from Phase 07: P=0.22 -> ceil(0.07*0.22*0.78*100)/100 = ceil(1.2012)/100 = 0.02."""
        assert taker_fee(0.22) == 0.02

    def test_p010(self) -> None:
        """P=0.10: ceil(0.07 * 0.10 * 0.90 * 100) / 100 = ceil(0.63)/100 = 0.01."""
        assert taker_fee(0.10) == 0.01

    def test_p090(self) -> None:
        """P=0.90: same as P=0.10 by symmetry."""
        assert taker_fee(0.90) == 0.01

    def test_min_price(self) -> None:
        """P=0.01: ceil(0.07 * 0.01 * 0.99 * 100) / 100 = ceil(0.0693)/100 = 0.01."""
        assert taker_fee(0.01) == 0.01

    def test_max_price(self) -> None:
        """P=0.99: same as P=0.01 by symmetry."""
        assert taker_fee(0.99) == 0.01

    def test_symmetry(self) -> None:
        """fee(P) == fee(1-P) for a grid of prices."""
        for cents in range(1, 100):
            p = cents / 100.0
            assert taker_fee(p) == taker_fee(1.0 - p), f"Symmetry broken at P={p}"

    def test_fee_never_zero(self) -> None:
        """Fee is always >= 0.01 within the valid band (ceiling guarantees this)."""
        for cents in range(1, 100):
            p = cents / 100.0
            assert taker_fee(p) >= 0.01

    def test_fee_peaks_at_midpoint(self) -> None:
        """Fee is maximized at P=0.50."""
        peak = taker_fee(0.50)
        for cents in range(1, 100):
            p = cents / 100.0
            assert taker_fee(p) <= peak

    def test_surcharge_added(self) -> None:
        """Surcharge is added on top of the base fee."""
        base = taker_fee(0.50)
        with_surcharge = taker_fee(0.50, surcharge=0.05)
        assert with_surcharge == base + 0.05


# ---------------------------------------------------------------------------
# Maker fee
# ---------------------------------------------------------------------------


class TestMakerFee:
    def test_midpoint(self) -> None:
        """P=0.50: ceil(0.25 * 0.07 * 0.25 * 100) / 100 = ceil(0.4375)/100 = 0.01."""
        assert maker_fee(0.50) == 0.01

    def test_p022(self) -> None:
        """P=0.22: ceil(0.25 * 0.07 * 0.22 * 0.78 * 100) / 100 = ceil(0.3003)/100 = 0.01."""
        assert maker_fee(0.22) == 0.01

    def test_min_price(self) -> None:
        """P=0.01: ceil(0.25 * 0.07 * 0.01 * 0.99 * 100) / 100 = ceil(0.017325)/100 = 0.01."""
        assert maker_fee(0.01) == 0.01

    def test_max_price(self) -> None:
        assert maker_fee(0.99) == 0.01

    def test_maker_leq_taker(self) -> None:
        """Maker fee <= taker fee for all valid prices."""
        for cents in range(1, 100):
            p = cents / 100.0
            assert maker_fee(p) <= taker_fee(p), f"Maker > taker at P={p}"

    def test_symmetry(self) -> None:
        for cents in range(1, 100):
            p = cents / 100.0
            assert maker_fee(p) == maker_fee(1.0 - p), f"Symmetry broken at P={p}"


# ---------------------------------------------------------------------------
# Round-trip cost
# ---------------------------------------------------------------------------


class TestRoundTripCost:
    def test_taker_taker_midpoint(self) -> None:
        """Taker-taker at P=0.50: 0.02 + 0.02 = 0.04."""
        assert round_trip_cost(0.50, "taker", "taker") == 0.04

    def test_maker_taker_midpoint(self) -> None:
        """Maker-taker at P=0.50: 0.01 + 0.02 = 0.03."""
        assert round_trip_cost(0.50, "maker", "taker") == 0.03

    def test_maker_maker_midpoint(self) -> None:
        """Maker-maker at P=0.50: 0.01 + 0.01 = 0.02."""
        assert round_trip_cost(0.50, "maker", "maker") == 0.02

    def test_taker_maker_midpoint(self) -> None:
        """Taker-maker at P=0.50: 0.02 + 0.01 = 0.03."""
        assert round_trip_cost(0.50, "taker", "maker") == 0.03

    def test_at_edge_prices(self) -> None:
        """Round trip at P=0.01: taker-taker = 0.01 + 0.01 = 0.02."""
        assert round_trip_cost(0.01, "taker", "taker") == 0.02

    def test_round_trip_with_surcharge(self) -> None:
        """Surcharge applies to both legs."""
        base = round_trip_cost(0.50, "taker", "taker")
        with_surcharge = round_trip_cost(0.50, "taker", "taker", surcharge=0.01)
        assert with_surcharge == base + 0.02  # +0.01 per leg


# ---------------------------------------------------------------------------
# Input validation (fail-loud)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_price_zero(self) -> None:
        with pytest.raises(ValueError, match="outside Kalshi band"):
            taker_fee(0.00)

    def test_price_one(self) -> None:
        with pytest.raises(ValueError, match="outside Kalshi band"):
            taker_fee(1.00)

    def test_price_negative(self) -> None:
        with pytest.raises(ValueError, match="outside Kalshi band"):
            taker_fee(-0.01)

    def test_price_above_one(self) -> None:
        with pytest.raises(ValueError, match="outside Kalshi band"):
            taker_fee(1.50)

    def test_invalid_buy_role(self) -> None:
        with pytest.raises(ValueError, match="buy_role"):
            round_trip_cost(0.50, "aggressor", "taker")

    def test_invalid_sell_role(self) -> None:
        with pytest.raises(ValueError, match="sell_role"):
            round_trip_cost(0.50, "taker", "passive")

    def test_maker_fee_price_zero(self) -> None:
        with pytest.raises(ValueError, match="outside Kalshi band"):
            maker_fee(0.00)


# ---------------------------------------------------------------------------
# FeeSchedule (config-backed)
# ---------------------------------------------------------------------------


_SOY_CONFIG = {
    "kalshi": {
        "series": "KXSOYBEANW",
        "event_ticker_pattern": "KXSOYBEANW-{YY}{MON}{DD}",
    },
    "fees": {
        "taker_formula": "ceil(0.07 * P * (1 - P) * 100) / 100",
        "maker_fraction": 0.25,
        "surcharge": None,
    },
}


class TestFeeSchedule:
    def test_loads_from_soy_config(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        assert fs.series == "KXSOYBEANW"
        assert fs.taker_rate == 0.07
        assert fs.maker_fraction == 0.25
        assert fs.surcharge == 0.0

    def test_taker_fee(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        assert fs.taker_fee(0.50) == 0.02

    def test_maker_fee(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        assert fs.maker_fee(0.50) == 0.01

    def test_round_trip(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        assert fs.round_trip_cost(0.50, "taker", "taker") == 0.04

    def test_round_trip_maker_taker(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        assert fs.round_trip_cost(0.50, "maker", "taker") == 0.03

    def test_series_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="Series mismatch"):
            FeeSchedule("KXWTIW", _SOY_CONFIG)

    def test_missing_kalshi_block_raises(self) -> None:
        with pytest.raises(ValueError, match="no 'kalshi' block"):
            FeeSchedule("KXSOYBEANW", {"fees": {}})

    def test_missing_fees_block_raises(self) -> None:
        config = {"kalshi": {"series": "KXSOYBEANW"}}
        with pytest.raises(ValueError, match="no 'fees' block"):
            FeeSchedule("KXSOYBEANW", config)

    def test_missing_taker_formula_raises(self) -> None:
        config = {
            "kalshi": {"series": "KXSOYBEANW"},
            "fees": {"maker_fraction": 0.25},
        }
        with pytest.raises(ValueError, match="taker_formula is missing"):
            FeeSchedule("KXSOYBEANW", config)

    def test_missing_maker_fraction_raises(self) -> None:
        config = {
            "kalshi": {"series": "KXSOYBEANW"},
            "fees": {"taker_formula": "ceil(0.07 * P * (1 - P) * 100) / 100"},
        }
        with pytest.raises(ValueError, match="maker_fraction is missing"):
            FeeSchedule("KXSOYBEANW", config)

    def test_with_surcharge(self) -> None:
        config = dict(_SOY_CONFIG)
        config["fees"] = dict(_SOY_CONFIG["fees"])
        config["fees"]["surcharge"] = 0.03
        fs = FeeSchedule("KXSOYBEANW", config)
        assert fs.surcharge == 0.03
        assert fs.taker_fee(0.50) == 0.02 + 0.03

    def test_repr(self) -> None:
        fs = FeeSchedule("KXSOYBEANW", _SOY_CONFIG)
        r = repr(fs)
        assert "KXSOYBEANW" in r
        assert "0.07" in r

    def test_custom_taker_rate(self) -> None:
        """Config with a different taker rate parses correctly."""
        config = {
            "kalshi": {"series": "KXWTIW"},
            "fees": {
                "taker_formula": "ceil(0.10 * P * (1 - P) * 100) / 100",
                "maker_fraction": 0.20,
                "surcharge": None,
            },
        }
        fs = FeeSchedule("KXWTIW", config)
        assert fs.taker_rate == 0.10
        assert fs.maker_fraction == 0.20
