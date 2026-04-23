"""Standalone latency benchmarks.

Run with:

    python -m benchmarks.run

Covers the three scenarios required by the spec:

  1. Single-market theo latency (p50, p99) per model type
  2. Full-book repricing latency with N=50 active markets
  3. Tick-to-theo latency: Pyth message → ingest → reprice

Timings use `time.perf_counter_ns()`. Numba JIT is warmed before measurement
so percentiles reflect steady-state, not compilation cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from benchmarks.harness import BenchContext, build_full_book_pricer, warm_kernel
from feeds.pyth_ws import PythHermesFeed
from models.base import TheoInputs
from models.gbm import GBMTheo, _gbm_prob_above


@dataclass(frozen=True, slots=True)
class LatencyStats:
    label: str
    n: int
    p50_ns: int
    p99_ns: int
    mean_ns: int
    max_ns: int
    budget_ns: int | None = None

    @property
    def passed(self) -> bool:
        return self.budget_ns is None or self.p99_ns <= self.budget_ns

    def pretty(self) -> str:
        fmt = lambda ns: (  # noqa: E731
            f"{ns / 1000.0:8.2f}μs" if ns < 10_000_000 else f"{ns / 1_000_000.0:7.2f}ms"
        )
        budget = (
            f"  (budget {fmt(self.budget_ns)})" if self.budget_ns is not None else ""
        )
        status = "" if self.budget_ns is None else ("  ✓" if self.passed else "  ✗")
        return (
            f"{self.label:<48}  n={self.n:>6d}  "
            f"p50 {fmt(self.p50_ns)}  p99 {fmt(self.p99_ns)}  "
            f"mean {fmt(self.mean_ns)}  max {fmt(self.max_ns)}{budget}{status}"
        )


def _percentiles(samples_ns: np.ndarray, p: float) -> int:
    return int(np.percentile(samples_ns, p))


def time_fn(label: str, fn, *, n_iter: int, budget_ns: int | None = None, warmup: int = 200) -> LatencyStats:
    for _ in range(warmup):
        fn()
    samples = np.empty(n_iter, dtype=np.int64)
    for i in range(n_iter):
        t0 = time.perf_counter_ns()
        fn()
        samples[i] = time.perf_counter_ns() - t0
    return LatencyStats(
        label=label,
        n=n_iter,
        p50_ns=_percentiles(samples, 50),
        p99_ns=_percentiles(samples, 99),
        mean_ns=int(samples.mean()),
        max_ns=int(samples.max()),
        budget_ns=budget_ns,
    )


def bench_kernel_varying_strikes() -> list[LatencyStats]:
    out_stats: list[LatencyStats] = []
    for n_strikes in (1, 5, 20, 50):
        strikes = np.linspace(70.0, 80.0, n_strikes).astype(np.float64)
        out = np.empty_like(strikes)

        def go():
            _gbm_prob_above(75.0, strikes, 0.01, 0.35, 0.0, out)

        out_stats.append(
            time_fn(f"kernel _gbm_prob_above  (n_strikes={n_strikes:2d}, preallocated)",
                  go, n_iter=10_000)
        )
    return out_stats


def bench_model_price_api(ctx: BenchContext) -> LatencyStats:
    model = GBMTheo()
    inputs = TheoInputs(
        commodity="wti",
        spot=75.0,
        strikes=ctx.strikes,
        tau=0.001,
        sigma=0.35,
        basis_drift=0.0,
        as_of_ns=ctx.now_ns,
        source_tick_seq=1,
    )
    return time_fn(
        "GBMTheo.price (20 strikes, validation + alloc)",
        lambda: model.price(inputs),
        n_iter=10_000,
        budget_ns=50_000,  # spec: <50μs per market
    )


def bench_pricer_single_market(ctx: BenchContext) -> LatencyStats:
    commodity = ctx.commodities[0]
    return time_fn(
        "Pricer.reprice_market (full pipeline, 1 market)",
        lambda: ctx.pricer.reprice_market(
            commodity, ctx.strikes, ctx.settle_ns, now_ns=ctx.now_ns
        ),
        n_iter=5_000,
        budget_ns=200_000,  # 200ms / 50 markets = 4ms avg, we target much better
    )


def bench_full_book(ctx: BenchContext) -> LatencyStats:
    def go():
        for c in ctx.commodities:
            ctx.pricer.reprice_market(c, ctx.strikes, ctx.settle_ns, now_ns=ctx.now_ns)

    return time_fn(
        f"FULL BOOK reprice ({len(ctx.commodities)} markets × 20 strikes)",
        go,
        n_iter=500,
        budget_ns=200_000_000,  # spec: <200ms
    )


def bench_tick_to_theo(ctx: BenchContext) -> LatencyStats:
    commodity = ctx.commodities[0]
    cfg = ctx.registry.config(commodity)
    feed = PythHermesFeed(
        endpoint="wss://unused.invalid",
        feed_id_to_commodity={cfg.raw["pyth_feed_id"]: commodity},
        tick_store=ctx.tick_store,
    )
    # Synthetic Pyth message with publish_time pinned to the context's `now`.
    # We don't advance it across iterations — the goal is to measure ingest +
    # reprice throughput, not to validate staleness semantics.
    tmpl = {
        "type": "price_update",
        "price_feed": {
            "id": cfg.raw["pyth_feed_id"],
            "price": {
                "price": "7500000000",
                "conf": "1000000",
                "expo": -8,
                "publish_time": ctx.now_ns // 1_000_000_000,
                "num_publishers": 6,
            },
        },
    }

    def go():
        feed.ingest_message(tmpl)
        ctx.pricer.reprice_market(
            commodity, ctx.strikes, ctx.settle_ns, now_ns=ctx.now_ns
        )

    return time_fn(
        "tick→theo  (Pyth ingest + Pricer.reprice_market)",
        go,
        n_iter=5_000,
        budget_ns=250_000,  # ingest + reprice; should be close to pricer alone
    )


def main() -> int:
    warm_kernel()
    ctx = build_full_book_pricer(n_markets=50, n_strikes=20)
    # Warm the pricer path — first call pulls in imports + compiles numba caches
    for c in ctx.commodities:
        ctx.pricer.reprice_market(c, ctx.strikes, ctx.settle_ns, now_ns=ctx.now_ns)

    results: list[LatencyStats] = []
    results.extend(bench_kernel_varying_strikes())
    results.append(bench_model_price_api(ctx))
    results.append(bench_pricer_single_market(ctx))
    results.append(bench_full_book(ctx))
    results.append(bench_tick_to_theo(ctx))

    print()
    print("-" * 118)
    print("goated latency benchmarks")
    print("-" * 118)
    for r in results:
        print(r.pretty())
    print("-" * 118)

    failed = [r for r in results if not r.passed]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
