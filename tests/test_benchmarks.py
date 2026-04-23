"""Budget-asserting latency tests.

Run with `pytest tests/test_benchmarks.py -v`. These share the benchmark
machinery from `benchmarks/run.py` but use tighter iteration counts so
they run in a few seconds.

Budgets (from spec):
  * GBMTheo.price (20 strikes):           p99 <   50μs
  * Pricer.reprice_market (1 market):     p99 <  200μs
  * Full book (50 markets × 20 strikes):  p99 <  200ms
  * tick→theo (ingest + reprice):         p99 <  250μs

Failing any of these is a real regression — the hot path is too slow to
hit the live-trading repricing rate the engine is designed for.
"""

from __future__ import annotations

import numpy as np

from benchmarks.harness import build_full_book_pricer, warm_kernel
from benchmarks.run import (
    bench_full_book,
    bench_model_price_api,
    bench_pricer_single_market,
    bench_tick_to_theo,
    time_fn,
)
from models.gbm import _gbm_prob_above


def test_kernel_under_10us_for_20_strikes():
    warm_kernel()
    strikes = np.linspace(70.0, 80.0, 20).astype(np.float64)
    out = np.empty_like(strikes)
    stats = time_fn(
        "kernel-20",
        lambda: _gbm_prob_above(75.0, strikes, 0.01, 0.35, 0.0, out),
        n_iter=3_000,
        budget_ns=10_000,
    )
    assert stats.passed, (
        f"kernel p99={stats.p99_ns/1000:.2f}μs > 10μs (p50={stats.p50_ns/1000:.2f}μs)"
    )


def _primed_ctx():
    warm_kernel()
    ctx = build_full_book_pricer(n_markets=50, n_strikes=20)
    for c in ctx.commodities:
        ctx.pricer.reprice_market(c, ctx.strikes, ctx.settle_ns, now_ns=ctx.now_ns)
    return ctx


def test_gbm_price_under_50us_per_market():
    ctx = _primed_ctx()
    stats = bench_model_price_api(ctx)
    assert stats.passed, (
        f"GBMTheo.price p99={stats.p99_ns/1000:.2f}μs > 50μs budget "
        f"(p50={stats.p50_ns/1000:.2f}μs)"
    )


def test_pricer_single_market_under_200us():
    ctx = _primed_ctx()
    stats = bench_pricer_single_market(ctx)
    assert stats.passed, (
        f"Pricer.reprice_market p99={stats.p99_ns/1000:.2f}μs > 200μs budget "
        f"(p50={stats.p50_ns/1000:.2f}μs)"
    )


def test_full_book_under_200ms():
    ctx = _primed_ctx()
    stats = bench_full_book(ctx)
    assert stats.passed, (
        f"Full book p99={stats.p99_ns/1e6:.2f}ms > 200ms budget "
        f"(p50={stats.p50_ns/1e6:.2f}ms)"
    )


def test_tick_to_theo_under_250us():
    ctx = _primed_ctx()
    stats = bench_tick_to_theo(ctx)
    assert stats.passed, (
        f"tick→theo p99={stats.p99_ns/1000:.2f}μs > 250μs budget "
        f"(p50={stats.p50_ns/1000:.2f}μs)"
    )
