# ACT-06 Plan -- Order builder + types + tick rounding + quote-band

**Action:** ACT-06
**Wave:** 0
**Effort:** M
**Deps:** ACT-04 (complete-pending-verify)
**Gaps closed:** GAP-080 (quote-band), GAP-081 (tick rounding), GAP-082 (order types/TIF/flags), GAP-122 (buy_max_cost)

---

## Scope

Single module `feeds/kalshi/orders.py` providing:

1. **Enums and types** -- `Side`, `Action`, `OrderType`, `TimeInForce`, `SelfTradePreventionType` as strict string enums. No stringly-typed API payloads leak past this module.

2. **Tick rounding** -- `round_to_tick(price_cents: int, tick_size_cents: int = 1) -> int`. Rounds to the nearest valid tick. Fail-loud if the result falls outside the quote-band.

3. **Quote-band enforcement** -- All price inputs are validated against `[1, 99]` (cents). `0` and `100` are rejected (those are settlement-only states). Configurable tick size defaulting to 1 cent per Rule 13.1(c), with optional 2-cent override.

4. **OrderSpec dataclass** -- Immutable, validated order specification with all fields needed by `KalshiClient.create_order()`. Construction validates all invariants; invalid specs raise `ValueError`.

5. **Order builder functions**:
   - `build_limit_order(...)` -- constructs a validated `OrderSpec` for a single limit order.
   - `build_two_sided_quote(...)` -- constructs a (bid, ask) pair of `OrderSpec` objects for market-making.

6. **Payload serialization** -- `OrderSpec.to_payload() -> dict[str, Any]` produces the exact dict expected by `KalshiClient.create_order()`.

---

## Constraints (from non-negotiables + research)

- No pandas.
- Type hints on all public interfaces.
- Fail-loud: invalid prices, zero/negative quantities, bad sides all raise `ValueError`.
- Prices are integer cents internally (matching Kalshi API: `yes_price` and `no_price` are ints in [1,99]).
- Quote-band: `[$0.01, $0.99]` i.e. cents [1, 99]. Per Phase 07 section 5: "Price bands clamp quotes to the closed interval [$0.01, $0.99]".
- Tick size: $0.01 default (1 cent), with optional $0.02 override per Rule 13.1(c).
- `buy_max_cost` support as optional second-layer limit (GAP-122).
- `post_only` defaults to True for maker quotes (LIP scoring rewards resting orders).

---

## Testing plan

File: `tests/test_orders.py`

- Tick rounding: valid prices, edge cases (1, 99), 2-cent tick
- Quote-band rejection: 0, 100, negative, >99
- OrderSpec construction: valid limit, valid market
- Two-sided quote: bid < ask, both valid
- Payload serialization: matches KalshiClient.create_order kwargs
- Edge cases: quantity=0 rejected, empty ticker rejected

---

## Estimated LOC

~250 implementation + ~200 tests = ~450 total.
