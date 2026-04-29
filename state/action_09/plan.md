# ACT-09 Plan -- Position store + per-Event signed exposure + max-loss accounting

**Action.** ACT-09
**Wave.** 0
**Status.** mid-flight
**Deps.** ACT-04 (complete-pending-verify -- ticker + bucket grid)
**Blocks.** ACT-12 (risk gates)

---

## Scope

Implement `state/positions.py` -- the authoritative in-process position
store for all Kalshi markets. This module closes GAP-083 (position-limit
accounting), GAP-116 (per-bucket inventory store), GAP-117 (cash/inventory
dynamics from fills), GAP-119 (per-Event signed dollar exposure), GAP-125
(full-cash-collateralisation accounting), and GAP-130 (configurable
sandbox caps).

## Data model

### MarketPosition (per-market)
- `market_ticker: str` -- e.g. `KXSOYBEANW-26APR24-17`
- `signed_qty: int` -- +long / -short (Yes contracts)
- `avg_cost_cents: float` -- volume-weighted average cost in cents [1..99]
- `realized_pnl_cents: int` -- accumulated realized PnL in cents
- `total_cost_cents: int` -- total cost paid for current position (for max-loss)

### Per-Event aggregation (computed, not stored separately)
- Signed exposure = sum of signed_qty across all markets in the event
- Max-loss = sum of worst-case loss across all markets in the event

### Max-loss accounting (Kalshi binary payoff)
- Long position (signed_qty > 0): max loss = total_cost_cents (paid to buy Yes contracts)
- Short position (signed_qty < 0): max loss = abs(signed_qty) * 100 - total_cost_cents
  (sold Yes at some price; worst case they settle at $1.00)

## API surface

```python
class PositionStore:
    def apply_fill(self, fill: Fill) -> None
    def get_position(self, market_ticker: str) -> MarketPosition
    def get_event_exposure(self, event_ticker: str) -> EventExposure
    def get_all_event_exposures(self) -> dict[str, EventExposure]
    def max_loss_cents(self, market_ticker: str) -> int
    def event_max_loss_cents(self, event_ticker: str) -> int
    def total_max_loss_cents(self) -> int
    def reconcile(self, api_positions: list[dict]) -> list[str]
    def snapshot(self) -> dict[str, MarketPosition]
    def clear(self) -> None
```

## Fill dataclass

```python
@dataclass(frozen=True, slots=True)
class Fill:
    market_ticker: str
    side: str          # "yes" or "no"
    action: str        # "buy" or "sell"
    count: int         # positive
    price_cents: int   # 1..99
    fill_id: str
```

## Thread safety

All mutation methods acquire a `threading.Lock`. Read methods also acquire
the lock to ensure consistent snapshots. The lock is per-PositionStore
instance.

## Reconciliation

`reconcile()` accepts the parsed response from `GET /portfolio/positions`.
It compares API-reported quantities against the local store and returns a
list of discrepancy descriptions. If any discrepancy is found, the method
raises `PositionReconciliationError` (fail-loud).

## Non-negotiables compliance

- No pandas.
- No silent failures: stale or inconsistent state raises.
- Type hints throughout.
- Fail-loud on reconciliation mismatch.

## Test plan

- Fill application: buy yes, buy no, sell yes, sell no
- Position sign conventions: long = positive, short = negative
- Per-event exposure aggregation across multiple buckets
- Max-loss: long-only, short-only, mixed
- Opposing positions in the same event
- Empty store edge cases
- Reconciliation: match, mismatch raises
- Thread safety: concurrent fills
- Fill with invalid data raises

## Files

- `state/positions.py` -- implementation
- `tests/test_positions.py` -- tests
- `state/action_09/plan.md` -- this file
- `state/action_09/handoff.md` -- handoff (post-implementation)
