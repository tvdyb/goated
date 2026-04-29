# ACT-12 Plan -- Risk Gates

**Action:** ACT-12 (risk gates: aggregate book-delta cap + per-Event cap)
**Wave:** 0
**Effort:** M (reduced)
**Deps:** ACT-09 (complete-pending-verify), ACT-11 (verified-complete)

---

## Gaps closed

- GAP-118: Aggregate net-delta cap on unhedged portfolio
- GAP-119: Per-Event signed dollar-exposure tracker vs Appendix-A limit
- GAP-120: Risk-gating stage J -- block quotes that breach per-bucket / aggregate-delta / scenario thresholds

---

## Design

### Module: `engine/risk.py`

Three risk caps enforced as hard gates:

1. **Aggregate book-delta cap** -- total signed exposure (sum of signed_qty across all positions) must stay within `[-aggregate_delta_cap, +aggregate_delta_cap]`.
2. **Per-Event exposure cap** -- signed exposure for any single event must stay within `[-per_event_delta_cap, +per_event_delta_cap]`.
3. **Max-loss cap** -- total worst-case loss across all positions must stay within `max_loss_cents` (derived from config `position_cap.max_loss_dollars * 100`).

### Gate types

- **Pre-trade gate (`check_pre_trade`)**: given the current PositionStore and a proposed order (market_ticker, signed_delta_qty, cost_per_contract_cents), simulate the resulting position and check all three caps. Raises `RiskBreachError` if any would be breached.
- **Post-trade check (`check_post_trade`)**: after a fill is applied, verify that caps are still respected. If breached (e.g., due to race), returns a `TriggerResult` that the kill switch can act on.

### Integration

- Reads current state from `PositionStore` (ACT-09).
- Post-trade breach produces a `TriggerResult` (ACT-11) that can be registered as a kill-switch trigger.
- Config loaded from `config/commodities.yaml` under `soy.position_cap.max_loss_dollars` with overridable constructor args for all three caps.

### Non-negotiables

- Fail-loud: `RiskBreachError` on pre-trade breach (never silently reject).
- No pandas.
- Full type hints.
- Thread-safe (reads PositionStore which is already locked).
