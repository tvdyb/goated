# goated

Live Kalshi commodity theo engine. Computes `P(S_T > K)` for every listed Kalshi commodity market, anchored to the Pyth oracle feed (Kalshi's settlement source).

## Status

Deliverable 1: skeleton + WTI GBM end-to-end with Black-Scholes analytical parity tests.

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
