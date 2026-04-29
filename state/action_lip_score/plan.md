# Plan -- ACT-LIP-SCORE (LIP Score Tracker)

**Action.** ACT-LIP-SCORE
**Wave.** 0
**Deps.** ACT-04 (verified-complete), ACT-LIP-POOL (verified-complete)
**Effort.** L
**Module.** `feeds/kalshi/lip_score.py`
**Tests.** `tests/test_lip_score.py`

---

## Goal

Compute our snapshot-level LIP Score continuously (per market, per
side, per snapshot), estimate visible competitor Score from the public
orderbook, project rolling expected pool share, and emit structured
telemetry for the attribution layer (ACT-LIP-PNL, Wave 1).

---

## Design

### 1. Per-snapshot score computation

```
our_score(market, t) = SUM over our_resting_orders(market, t)
                         [ order.size * dist_mult(order, bba(t)) ]
```

`bba(t)` = best bid / best ask at snapshot time t.

### 2. Distance multiplier function

```
dist_mult(order_price, best_price, decay_ticks) -> float in [0.0, 1.0]

  distance = abs(order_price - best_price)  # in ticks (cents)
  if distance == 0: return 1.0
  if distance >= decay_ticks: return 0.0
  return 1.0 - distance / decay_ticks       # linear decay (default)
```

Configurable via `decay_ticks` parameter (default: 5, per OD-34'
working default -- linear decay over 5 ticks). Curve shape is
pluggable (linear default; step/exponential via subclass or callable).

### 3. Visible total score estimation

Same formula applied to all visible orderbook levels (from WS
`orderbook_snapshot` / `orderbook_delta` maintained state). Each level
contributes `level_size * dist_mult(level_price, best_price)`.

### 4. Projected pool share

```
projected_share(market, period) = mean over snapshots
    [our_score / visible_total_score]

projected_reward(market, period) = projected_share
    * pool(market, period)
```

Division guarded: if `visible_total_score == 0`, share = 0.0 (no
liquidity visible => undefined; conservative default).

### 5. Rolling window statistics

Track score and share over configurable windows (default: 1h, 1d).
Use a bounded deque of `(timestamp, our_score, total_score)` tuples
with numpy for efficient mean/std computation over the window.

### 6. Telemetry emission

`ScoreSnapshot` dataclass emitted per market per snapshot tick,
containing: market_ticker, timestamp, our_score, total_score,
projected_share, our_resting_size, target_size_threshold,
below_target_flag. Collected by the attribution layer.

### 7. Target Size threshold check

Flag when our total resting size per side is below the market's
Target Size. `below_target_size(market, side)` returns bool.
Target Size is configurable per market (default: 100 contracts,
per LIP docs range 100-20,000).

---

## Non-negotiables

- No pandas.
- Type hints on all public interfaces.
- Fail-loud on missing orderbook data (raise, don't silently return 0).
- `numba.njit` on the distance multiplier inner loop (hot path, 1Hz
  per market per side).
- No silent failures.

---

## File layout

- `feeds/kalshi/lip_score.py` -- score computation, orderbook state,
  rolling stats, telemetry types
- `tests/test_lip_score.py` -- unit tests

---

## Test plan

1. Distance multiplier at various distances (0, 1, mid, boundary, beyond).
2. Score computation with known orders and known orderbook.
3. Projected share calculation (normal, zero-total, single-participant).
4. Rolling window stats (add snapshots, window expiry, mean/std).
5. Target Size threshold detection (below, at, above).
6. Edge cases: empty orderbook, no competitors, all orders outside decay.
