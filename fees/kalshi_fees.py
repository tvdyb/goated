"""Kalshi taker/maker fee model and round-trip cost calculation.

Fee formulas sourced from Phase 07 research (research/phase_07_kalshi_contract_structure.md
section 6) and confirmed against config/commodities.yaml soy.fees entries from ACT-02.

Closes GAP-007 (fee formula), GAP-152 (round-trip cost subtraction).
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Allowed trade roles for round-trip calculation
# ---------------------------------------------------------------------------

_VALID_ROLES = frozenset({"taker", "maker"})

# Price band enforced by Kalshi (Rule 13.1(c), $0.01 -- $0.99 inclusive)
_MIN_PRICE = 0.01
_MAX_PRICE = 0.99

# ---------------------------------------------------------------------------
# Pure functions -- stateless, no config dependency
# ---------------------------------------------------------------------------


def _validate_price(price: float) -> None:
    """Raise ValueError if price is outside the Kalshi [$0.01, $0.99] band."""
    if not (_MIN_PRICE <= price <= _MAX_PRICE):
        raise ValueError(
            f"Price {price!r} outside Kalshi band [{_MIN_PRICE}, {_MAX_PRICE}]"
        )


def taker_fee(
    price: float,
    *,
    taker_rate: float = 0.07,
    surcharge: float = 0.0,
) -> float:
    """Kalshi taker fee per contract.

    Formula: ceil(taker_rate * P * (1 - P) * 100) / 100 + surcharge

    Parameters
    ----------
    price : float
        Traded price in dollars, must be in [0.01, 0.99].
    taker_rate : float
        Base fee rate (default 0.07 per Kalshi fee schedule).
    surcharge : float
        Per-contract surcharge in dollars (default 0.0; no commodity
        surcharge confirmed for KXSOYBEANW).

    Returns
    -------
    float
        Fee in dollars, rounded to the cent via ceiling.

    Raises
    ------
    ValueError
        If price is outside the [$0.01, $0.99] band.
    """
    _validate_price(price)
    raw_cents = taker_rate * price * (1.0 - price) * 100.0
    fee = math.ceil(raw_cents) / 100.0
    return fee + surcharge


def maker_fee(
    price: float,
    *,
    taker_rate: float = 0.07,
    maker_fraction: float = 0.25,
    surcharge: float = 0.0,
) -> float:
    """Kalshi maker fee per contract.

    Formula: ceil(maker_fraction * taker_rate * P * (1 - P) * 100) / 100 + surcharge

    Parameters
    ----------
    price : float
        Traded price in dollars, must be in [0.01, 0.99].
    taker_rate : float
        Base taker fee rate (default 0.07).
    maker_fraction : float
        Maker fee as fraction of taker fee (default 0.25).
    surcharge : float
        Per-contract surcharge in dollars (default 0.0).

    Returns
    -------
    float
        Fee in dollars, rounded to the cent via ceiling.

    Raises
    ------
    ValueError
        If price is outside the [$0.01, $0.99] band.
    """
    _validate_price(price)
    raw_cents = maker_fraction * taker_rate * price * (1.0 - price) * 100.0
    fee = math.ceil(raw_cents) / 100.0
    return fee + surcharge


def round_trip_cost(
    price: float,
    buy_role: str,
    sell_role: str,
    *,
    taker_rate: float = 0.07,
    maker_fraction: float = 0.25,
    surcharge: float = 0.0,
) -> float:
    """Round-trip fee cost for a buy + sell at the same price.

    Parameters
    ----------
    price : float
        Traded price in dollars, must be in [0.01, 0.99].
    buy_role : str
        "taker" or "maker" for the buy leg.
    sell_role : str
        "taker" or "maker" for the sell leg.
    taker_rate : float
        Base taker fee rate (default 0.07).
    maker_fraction : float
        Maker fee as fraction of taker fee (default 0.25).
    surcharge : float
        Per-contract surcharge in dollars (default 0.0).

    Returns
    -------
    float
        Total round-trip fee in dollars (buy fee + sell fee).

    Raises
    ------
    ValueError
        If price is out of band or role is not "taker"/"maker".
    """
    if buy_role not in _VALID_ROLES:
        raise ValueError(f"buy_role must be one of {_VALID_ROLES}, got {buy_role!r}")
    if sell_role not in _VALID_ROLES:
        raise ValueError(f"sell_role must be one of {_VALID_ROLES}, got {sell_role!r}")

    kwargs = dict(
        taker_rate=taker_rate,
        maker_fraction=maker_fraction,
        surcharge=surcharge,
    )

    def _leg_fee(role: str) -> float:
        if role == "taker":
            return taker_fee(price, taker_rate=kwargs["taker_rate"], surcharge=kwargs["surcharge"])
        else:
            return maker_fee(price, **kwargs)

    return _leg_fee(buy_role) + _leg_fee(sell_role)


# ---------------------------------------------------------------------------
# FeeSchedule -- config-backed, per-series
# ---------------------------------------------------------------------------


class FeeSchedule:
    """Fee schedule for a specific Kalshi series, loaded from commodity config.

    The constructor reads the ``fees`` block from the commodity config dict
    (as parsed from ``config/commodities.yaml``).  It fails loud if the
    config is missing the required fee fields.

    Parameters
    ----------
    series : str
        Kalshi series ticker, e.g. ``"KXSOYBEANW"``.
    commodity_config : dict
        The per-commodity dict from ``commodities.yaml`` (e.g. the value
        under the ``soy`` key).  Must contain a ``kalshi.series`` matching
        *series* and a ``fees`` sub-dict with ``taker_formula`` and
        ``maker_fraction``.

    Raises
    ------
    ValueError
        If the config is missing required fields, or the series does not
        match the config's ``kalshi.series``.
    """

    def __init__(self, series: str, commodity_config: dict[str, Any]) -> None:
        # Validate kalshi block exists
        kalshi_block = commodity_config.get("kalshi")
        if kalshi_block is None:
            raise ValueError(
                f"Commodity config has no 'kalshi' block; cannot build "
                f"FeeSchedule for series {series!r}"
            )

        config_series = kalshi_block.get("series")
        if config_series != series:
            raise ValueError(
                f"Series mismatch: requested {series!r} but config has "
                f"kalshi.series={config_series!r}"
            )

        # Validate fees block
        fees_block = commodity_config.get("fees")
        if fees_block is None:
            raise ValueError(
                f"Commodity config for series {series!r} has no 'fees' block"
            )

        # Parse taker_rate from taker_formula string
        # Expected format: "ceil(0.07 * P * (1 - P) * 100) / 100"
        taker_formula: str = fees_block.get("taker_formula", "")
        if not taker_formula:
            raise ValueError(
                f"fees.taker_formula is missing or empty for series {series!r}"
            )
        self._taker_rate = _parse_taker_rate(taker_formula)

        maker_frac = fees_block.get("maker_fraction")
        if maker_frac is None:
            raise ValueError(
                f"fees.maker_fraction is missing for series {series!r}"
            )
        self._maker_fraction: float = float(maker_frac)

        surcharge_raw = fees_block.get("surcharge")
        self._surcharge: float = float(surcharge_raw) if surcharge_raw is not None else 0.0

        self._series = series

    @property
    def series(self) -> str:
        return self._series

    @property
    def taker_rate(self) -> float:
        return self._taker_rate

    @property
    def maker_fraction(self) -> float:
        return self._maker_fraction

    @property
    def surcharge(self) -> float:
        return self._surcharge

    def taker_fee(self, price: float) -> float:
        """Taker fee per contract at *price*."""
        return taker_fee(
            price, taker_rate=self._taker_rate, surcharge=self._surcharge
        )

    def maker_fee(self, price: float) -> float:
        """Maker fee per contract at *price*."""
        return maker_fee(
            price,
            taker_rate=self._taker_rate,
            maker_fraction=self._maker_fraction,
            surcharge=self._surcharge,
        )

    def round_trip_cost(
        self, price: float, buy_role: str = "taker", sell_role: str = "taker"
    ) -> float:
        """Round-trip cost (buy + sell) per contract at *price*."""
        return round_trip_cost(
            price,
            buy_role,
            sell_role,
            taker_rate=self._taker_rate,
            maker_fraction=self._maker_fraction,
            surcharge=self._surcharge,
        )

    def __repr__(self) -> str:
        return (
            f"FeeSchedule(series={self._series!r}, taker_rate={self._taker_rate}, "
            f"maker_fraction={self._maker_fraction}, surcharge={self._surcharge})"
        )


# ---------------------------------------------------------------------------
# Helper: parse taker rate from formula string
# ---------------------------------------------------------------------------


def _parse_taker_rate(formula: str) -> float:
    """Extract the numeric rate from a taker_formula string.

    Expected pattern: ``"ceil(<rate> * P * (1 - P) * 100) / 100"``
    where ``<rate>`` is a float like ``0.07``.

    Raises
    ------
    ValueError
        If the formula cannot be parsed.
    """
    # Strip whitespace and look for the leading coefficient
    # "ceil(0.07 * P * (1 - P) * 100) / 100"
    import re

    match = re.search(r"ceil\(\s*([0-9]*\.?[0-9]+)\s*\*\s*P", formula)
    if match is None:
        raise ValueError(
            f"Cannot parse taker_rate from formula: {formula!r}. "
            f"Expected pattern: ceil(<rate> * P * (1 - P) * 100) / 100"
        )
    return float(match.group(1))
