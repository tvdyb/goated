# ACT-10 Plan -- Kalshi taker/maker fee model + round-trip cost subtraction

**Action.** ACT-10
**Wave.** 0
**Effort.** M
**Deps.** ACT-02 (verified-complete)
**Closes gaps.** GAP-007, GAP-152, partially GAP-142

---

## Scope

Fee-only accounting. LIP rewards are posted by the attribution layer
(ACT-LIP-PNL), not by this module.

## Fee formulas (from Phase 07 research + commodities.yaml)

### Taker fee

```
fee_taker(P) = ceil(0.07 * P * (1 - P) * 100) / 100
```

where P is the traded price in dollars, P in [0.01, 0.99].

- Symmetric in P: fee(P) == fee(1 - P).
- Peaks at P = 0.50: ceil(0.07 * 0.25 * 100) / 100 = ceil(1.75) / 100 = 0.02.
- Floors at 0.01 near price-band edges (P = 0.01 or P = 0.99).

### Maker fee

```
fee_maker(P) = ceil(maker_fraction * 0.07 * P * (1 - P) * 100) / 100
```

where maker_fraction = 0.25 (from commodities.yaml soy.fees.maker_fraction).
At P = 0.50: ceil(0.0175 * 0.25 * 100) / 100 = ceil(0.4375) / 100 = 0.01.

### Surcharge

Per commodities.yaml: `surcharge: null`. No commodity surcharge confirmed
for KXSOYBEANW. The module will accept an optional surcharge and add it
per-contract if non-null.

### Round-trip cost

```
round_trip(P, buy_role, sell_role) = fee(P, buy_role) + fee(P, sell_role)
```

Typical scenarios:
- taker-taker: most expensive (aggressive entry + aggressive exit)
- maker-taker: typical MM (passive entry, aggressive exit / filled exit)
- maker-maker: cheapest (passive both sides, rare in practice)

## Design

### Module: `fees/kalshi_fees.py`

Public interface:

```python
def taker_fee(price: float, *, taker_rate: float = 0.07, surcharge: float = 0.0) -> float
def maker_fee(price: float, *, taker_rate: float = 0.07, maker_fraction: float = 0.25, surcharge: float = 0.0) -> float
def round_trip_cost(price: float, buy_role: str, sell_role: str, *, taker_rate: float = 0.07, maker_fraction: float = 0.25, surcharge: float = 0.0) -> float
```

### FeeSchedule class: `fees/kalshi_fees.py`

Loads fee parameters from commodities.yaml for a given series. Fail-loud
if no fee config exists for the requested series.

```python
class FeeSchedule:
    def __init__(self, series: str, config: dict) -> None: ...
    def taker_fee(self, price: float) -> float: ...
    def maker_fee(self, price: float) -> float: ...
    def round_trip_cost(self, price: float, buy_role: str, sell_role: str) -> float: ...
```

### Package: `fees/__init__.py`

Re-exports public API. Contains `load_fee_schedule(series, config_path)` helper.

### Non-negotiables compliance

- Fail-loud: ValueError on price outside [0.01, 0.99], on unknown series,
  on missing fee config.
- No pandas.
- Type hints on all public functions.
- Simple arithmetic -- no numba needed for fee lookups (not hot-path math).
- Pure Python math.ceil for the ceiling operation.

## Test plan

File: `tests/test_kalshi_fees.py`

1. Taker fee at P=0.50 -> 0.02
2. Taker fee at P=0.22 -> 0.02 (worked example from Phase 07)
3. Taker fee at P=0.01 -> 0.01
4. Taker fee at P=0.99 -> 0.01
5. Taker fee symmetry: fee(P) == fee(1-P) for grid of prices
6. Maker fee at P=0.50 -> 0.01
7. Maker fee at P=0.22 -> 0.01
8. Round-trip taker-taker at P=0.50 -> 0.04
9. Round-trip maker-taker at P=0.50 -> 0.03
10. Round-trip maker-maker at P=0.50 -> 0.02
11. ValueError on P=0.00, P=1.00, P=-0.01, P=1.50
12. FeeSchedule loads from soy config and computes correctly
13. FeeSchedule raises on unknown series
