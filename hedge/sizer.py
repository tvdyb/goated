"""ZS/ZC futures hedge sizer.

Converts portfolio dollar-delta to a number of CBOT futures contracts.

One ZS contract = 5,000 bushels of soybeans.
One ZC contract = 5,000 bushels of corn.

N_contracts = round(delta_port / (contract_size * underlying_price))

Minimum hedge: 1 contract when triggered.

Non-negotiables: no pandas, fail-loud, type hints.
"""

from __future__ import annotations

# Contract multipliers (bushels per contract)
ZS_CONTRACT_SIZE: int = 5_000  # soybeans
ZC_CONTRACT_SIZE: int = 5_000  # corn


def compute_hedge_size(
    delta_port: float,
    underlying_price: float,
    contract_size: int = ZS_CONTRACT_SIZE,
) -> int:
    """Compute the number of futures contracts to hedge.

    Args:
        delta_port: Portfolio delta in dollar terms. Positive means
            long underlying exposure (need to sell futures to hedge).
        underlying_price: Current price of the underlying per unit
            (e.g. $/bushel for ZS).
        contract_size: Number of units per contract (default 5000
            for ZS soybeans).

    Returns:
        Signed number of contracts to trade. Positive = buy,
        negative = sell. The sign convention is:
        - delta_port > 0 (long exposure) -> negative (sell futures)
        - delta_port < 0 (short exposure) -> positive (buy futures)

    Raises:
        ValueError: If underlying_price <= 0 or contract_size <= 0.
    """
    if underlying_price <= 0:
        raise ValueError(
            f"underlying_price must be positive, got {underlying_price}"
        )
    if contract_size <= 0:
        raise ValueError(
            f"contract_size must be positive, got {contract_size}"
        )

    notional_per_contract = contract_size * underlying_price
    raw = delta_port / notional_per_contract

    # Round to nearest integer
    n = round(raw)

    # Minimum 1 contract if we're hedging at all
    if n == 0 and abs(raw) > 0:
        n = 1 if raw > 0 else -1

    # Hedge direction: offset the delta
    # delta_port > 0 -> sell futures (return negative)
    # delta_port < 0 -> buy futures (return positive)
    return -n
