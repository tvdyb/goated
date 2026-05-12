"""truev_backtest_csv — backtest the TruEV reconstruction model
against a published-index CSV (the only ground truth that doesn't
require strike-boundary triangulation through Kalshi-settled events).

Provide a CSV with columns `date,price` (one row per published day).
The script:

  1. Computes realized σ_annual from log returns of the actual index.
     This is THE number to plug into the lognormal pricer's
     `--truev-vol`. No model assumption required.

  2. Walk-forward reconstruction backtest. For each day D in the
     range, anchor on (D-1, V[D-1]) plus D-1's yfinance commodity
     closes, then use D's commodity closes to predict V[D]. Compares
     model[D] vs actual[D]. Reports RMSE, mean error, max error,
     and the worst-N days.

  3. Optional CSV dump of per-day rows.

Usage:
    python -m deploy.truev_backtest_csv \\
        --csv ev_commodity_prices.csv

    python -m deploy.truev_backtest_csv \\
        --csv ev_commodity_prices.csv \\
        --start 2026-01-01

    python -m deploy.truev_backtest_csv \\
        --csv ev_commodity_prices.csv \\
        --start 2026-01-01 --output /tmp/bt.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import statistics
import sys
from datetime import date, timedelta
from typing import Any

from feeds.truflation import TRUEV_YFINANCE_SYMBOLS
from lipmm.theo.providers._truev_index import (
    DEFAULT_WEIGHTS_BACKTEST,
    TruEvAnchor,
    reconstruct_index,
)

logger = logging.getLogger("truev_backtest_csv")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m deploy.truev_backtest_csv")
    p.add_argument("--csv", required=True,
                   help="Path to the actual-index CSV (date,price).")
    p.add_argument("--start", default="2026-01-01",
                   help="Backtest start date (YYYY-MM-DD). Default 2026-01-01.")
    p.add_argument("--end", default=None,
                   help="Backtest end date (YYYY-MM-DD). Default = last "
                        "available date in the CSV.")
    p.add_argument("--output", default=None,
                   help="Optional CSV output path for per-day rows.")
    p.add_argument("--worst", type=int, default=10,
                   help="Print this many worst-residual days (default 10).")
    p.add_argument("--verbose", action="store_true",
                   help="DEBUG-level logging.")
    return p.parse_args(argv)


def _read_actuals_csv(path: str) -> dict[date, float]:
    """Returns date → published index value, sorted by date."""
    out: dict[date, float] = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = date.fromisoformat(row["date"].strip())
                v = float(row["price"])
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("skipping malformed row %r: %s", row, exc)
                continue
            out[d] = v
    return dict(sorted(out.items()))


def _realized_sigma(actuals: dict[date, float]) -> tuple[float, float, int]:
    """Daily and annualized stdev of log returns. Annualization at √252."""
    days = sorted(actuals.keys())
    rets: list[float] = []
    for prev_d, cur_d in zip(days, days[1:]):
        v0, v1 = actuals[prev_d], actuals[cur_d]
        if v0 > 0 and v1 > 0:
            rets.append(math.log(v1 / v0))
    if len(rets) < 2:
        return 0.0, 0.0, len(rets)
    sd = statistics.pstdev(rets)
    return sd, sd * math.sqrt(252), len(rets)


def _fetch_yf_closes(
    symbols: tuple[str, ...], start: date, end: date,
) -> dict[str, dict[date, float]]:
    """Returns per-symbol date → close mapping over the [start, end] window.

    Uses a single yfinance batch download, then maps `Close` columns
    into a date-indexed dict. Missing days (weekends, holidays) just
    aren't present in the dict — the caller falls back to the most
    recent prior trading day.
    """
    import yfinance as yf
    # yfinance `end` is exclusive; pad both sides for weekend coverage.
    pad_start = (start - timedelta(days=7)).isoformat()
    pad_end = (end + timedelta(days=2)).isoformat()
    df = yf.download(
        list(symbols), start=pad_start, end=pad_end,
        progress=False, auto_adjust=False, threads=True,
    )
    out: dict[str, dict[date, float]] = {sym: {} for sym in symbols}
    if df.empty:
        return out
    closes = df["Close"] if "Close" in df.columns else df
    # Single-symbol path returns a Series-like; multi returns columns.
    for sym in symbols:
        try:
            col = closes[sym]
        except (KeyError, ValueError):
            continue
        for ts, val in col.items():
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if v != v or v <= 0:  # NaN check
                continue
            out[sym][ts.date()] = v
    return out


def _close_on_or_before(
    series: dict[date, float], target: date, lookback: int = 6,
) -> tuple[date, float] | None:
    """Find the most recent (date, close) on or before `target`,
    looking back at most `lookback` calendar days (skipping
    weekends/holidays)."""
    for offset in range(lookback + 1):
        d = target - timedelta(days=offset)
        if d in series:
            return d, series[d]
    return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    actuals = _read_actuals_csv(args.csv)
    if not actuals:
        print("ERROR: empty / malformed CSV", file=sys.stderr)
        return 2

    days_all = sorted(actuals.keys())
    csv_first, csv_last = days_all[0], days_all[-1]

    try:
        start = date.fromisoformat(args.start)
    except ValueError:
        print(f"ERROR: bad --start {args.start!r}", file=sys.stderr)
        return 2
    end = date.fromisoformat(args.end) if args.end else csv_last
    if start < csv_first:
        print(f"warn: --start {start} before CSV first {csv_first}; "
              f"clamping to {csv_first}")
        start = csv_first
    if end > csv_last:
        end = csv_last

    print()
    print(f"  CSV:        {args.csv}")
    print(f"  CSV range:  {csv_first} → {csv_last} ({len(actuals)} days)")
    print(f"  Backtest:   {start} → {end}")
    print()

    # ── Part 1: realized σ ──────────────────────────────────────────
    actuals_window = {d: v for d, v in actuals.items() if start <= d <= end}
    sd_d, sd_a, n_rets = _realized_sigma(actuals_window)
    print("  ── Realized σ (annualized at √252) ─────────────────────")
    print(f"    n returns:        {n_rets}")
    print(f"    σ_daily:          {sd_d:.4%}" if sd_d else "    σ_daily: 0")
    print(f"    σ_annual:         {sd_a:.4%}" if sd_a else "    σ_annual: 0")
    print(f"    → plug into:      --truev-vol {sd_a:.3f}")
    print()

    # ── Part 2: walk-forward reconstruction backtest ───────────────
    # We need yfinance closes from (start - 1 day) to end, since each
    # day uses the previous day as anchor.
    print("  ── Walk-forward reconstruction backtest ───────────────")
    print("  Pulling yfinance closes for", ", ".join(TRUEV_YFINANCE_SYMBOLS), "…")
    print()

    yf_closes = _fetch_yf_closes(
        TRUEV_YFINANCE_SYMBOLS, start - timedelta(days=7), end,
    )
    coverage = {sym: len(s) for sym, s in yf_closes.items()}
    print(f"    yfinance coverage: {coverage}")
    print()

    weights = DEFAULT_WEIGHTS_BACKTEST
    rows: list[dict[str, Any]] = []
    days_in_window = sorted(d for d in actuals_window.keys() if d > start)
    skipped = 0
    for cur in days_in_window:
        prev = max(d for d in actuals if d < cur)
        actual_v = actuals[cur]
        anchor_v = actuals[prev]

        # Need closes for every modeled symbol on prev and cur.
        anchor_prices: dict[str, float] = {}
        cur_prices: dict[str, float] = {}
        ok = True
        for sym in weights.weights.keys():
            a = _close_on_or_before(yf_closes.get(sym, {}), prev)
            c = _close_on_or_before(yf_closes.get(sym, {}), cur)
            if a is None or c is None:
                ok = False
                break
            anchor_prices[sym] = a[1]
            cur_prices[sym] = c[1]
        if not ok:
            skipped += 1
            continue

        try:
            anchor = TruEvAnchor(
                anchor_date=prev.isoformat(),
                anchor_index_value=anchor_v,
                anchor_prices=anchor_prices,
            )
            model_v = reconstruct_index(cur_prices, weights, anchor)
        except ValueError:
            skipped += 1
            continue

        residual = model_v - actual_v
        rows.append({
            "date": cur.isoformat(),
            "anchor_date": prev.isoformat(),
            "anchor_value": anchor_v,
            "actual": actual_v,
            "model": model_v,
            "residual": residual,
            "abs_residual": abs(residual),
            "rel_pct": residual / actual_v * 100 if actual_v else 0.0,
        })

    if not rows:
        print("  no scoreable days — skipped:", skipped)
        return 0

    residuals = [r["residual"] for r in rows]
    abs_res = [r["abs_residual"] for r in rows]
    pct_res = [abs(r["rel_pct"]) for r in rows]
    rmse = math.sqrt(statistics.fmean(r * r for r in residuals))
    mae = statistics.fmean(abs_res)
    bias = statistics.fmean(residuals)
    max_err = max(abs_res)
    rmse_pct = math.sqrt(statistics.fmean((r / a * 100) ** 2 for r, a in
                                          zip(residuals,
                                              [row["actual"] for row in rows])))

    print(f"    days scored:      {len(rows)} (skipped {skipped})")
    print(f"    bias (mean err):  {bias:+.3f} pts")
    print(f"    MAE:              {mae:.3f} pts")
    print(f"    RMSE:             {rmse:.3f} pts")
    print(f"    RMSE (%):         {rmse_pct:.3f}%")
    print(f"    max |error|:      {max_err:.3f} pts")
    print(f"    mean |%|:         {statistics.fmean(pct_res):.3f}%")
    print()

    rows_sorted = sorted(rows, key=lambda r: r["abs_residual"], reverse=True)
    print(f"  ── Worst {min(args.worst, len(rows_sorted))} days ─────────────────────────────")
    print(f"    {'date':<12} {'actual':>10} {'model':>10} {'resid':>9} {'pct':>7}")
    for r in rows_sorted[:args.worst]:
        print(f"    {r['date']:<12} {r['actual']:>10.2f} {r['model']:>10.2f} "
              f"{r['residual']:>+9.3f} {r['rel_pct']:>+7.3f}%")
    print()

    if args.output:
        with open(args.output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  per-day rows written → {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
