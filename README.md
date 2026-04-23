# goated

Live Kalshi commodity theo engine. Computes `P(S_T > K)` for every listed Kalshi commodity market, anchored to the Pyth oracle feed (Kalshi's settlement source).

## Status

Deliverable 2: benchmark harness + budget tests. WTI GBM end-to-end ships
from deliverable 1.

## Measured latency (M-series macOS, single process)

```
kernel _gbm_prob_above  (n_strikes= 1)   p50  0.25μs  p99  0.29μs
kernel _gbm_prob_above  (n_strikes=20)   p50  0.54μs  p99  0.58μs
kernel _gbm_prob_above  (n_strikes=50)   p50  1.00μs  p99  1.04μs
GBMTheo.price           (20 strikes)     p50  4.71μs  p99  5.21μs   (budget 50μs)
Pricer.reprice_market   (1 market)       p50 17.33μs  p99 18.84μs   (budget 200μs)
FULL BOOK               (50 × 20 strk)   p50  864μs   p99  936μs    (budget 200ms)
tick→theo (ingest+price, 1 market)       p50 18.38μs  p99 22.17μs   (budget 250μs)
```

Full book clears its 200ms budget by ~200×, leaving comfortable headroom
for jump-diffusion FFT and regime-switch models later. Re-run with
`python -m benchmarks.run`.

## Latency targets

| Model | Per-market | Full book (50 mkts) |
|---|---|---|
| GBM | <50μs | — |
| Jump-diffusion (Carr-Madan FFT) | <500μs | — |
| Regime-switch | <100μs | — |
| Point-mass | <50μs | — |
| **All models, full book** | — | **<200ms** |

## Layout

```
feeds/         Async data ingestion (Pyth, CME, options, Kalshi, macro)
state/         In-memory shared state (tick ring buffer, IV surface, basis)
models/        Per-commodity model families (GBM, jump-diffusion, HMM, point-mass, student-t)
engine/        Pricer loop, asyncio scheduler, trading-hours calendar
calibration/   Offline nightly jobs (vol, jump MLE, HMM fit, IV event strip)
validation/    Backtest, Pyth↔CME reconciliation, pre-publish sanity checks
config/        commodities.yaml (per-commodity overrides), pyth_feeds.yaml
tests/         Analytical parity, monotonicity, boundary behavior, feed failure
benchmarks/    p50/p99 latency harness per model and full-book repricing
```

## Dev setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Non-negotiables

- No pandas in the hot path; no Python-level loops over markets or strikes.
- No Monte Carlo in the hot path; MC is for offline validation only.
- No silent failures: stale Pyth publishers, out-of-bounds IV, feed dropouts → raise, don't publish.
- `scipy.special.ndtr` over `scipy.stats.norm.cdf`.
- `numba.njit` on all hot-path math.
- Theo is `P(Pyth_at_T > K)`, not `P(CME_front_at_T > K)`. Model the basis.
