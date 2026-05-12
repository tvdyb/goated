"""truev_fit_weights — empirically fit Truflation EV basket quantities
from published-index actuals + yfinance commodity closes.

Treats the index as a Laspeyres form `V[d] = Σ Q_metal × p_metal[d]`
and runs NNLS to solve for `Q_metal` over a fit window. Converts to
% weights at a reference date (today by default).

Used to derive Q1 2026 weights when Truflation hasn't published the
post-rebalance methodology data. The Dec-31-2025 rebalance set the
vehicle mix to 54% HEV, 28% BEV, 18% PHEV, 0.03% FCEV — but the
per-vehicle metal intensities aren't public, so we recover the
basket empirically from the actual-index time series.

Three fits run by default:
  - Q1 only (2026-01-01 → 2026-03-31)
  - Q2 only (2026-04-01 → today)
  - Whole period (2026-01-01 → today)

Cobalt is excluded from the regression (no daily yfinance history);
the cobalt slot is preserved at the Q4 weight (8.22%) when promoting
fitted weights to a live config.

Usage:
    python -m deploy.truev_fit_weights --csv ev_commodity_prices.csv

    python -m deploy.truev_fit_weights --csv ev_commodity_prices.csv \\
        --output /tmp/fitted_weights.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import statistics
import sys
from datetime import date, timedelta
from typing import Any

import numpy as np
from scipy.optimize import nnls

from deploy.truev_backtest_csv import (
    _close_on_or_before,
    _fetch_yf_closes,
    _read_actuals_csv,
)
from feeds.truflation import TRUEV_YFINANCE_SYMBOLS

logger = logging.getLogger("truev_fit_weights")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m deploy.truev_fit_weights")
    p.add_argument("--csv", required=True,
                   help="Path to actual-index CSV (date,price).")
    p.add_argument("--reference-date", default=None,
                   help="Date for converting fitted Q to %% weights "
                        "(YYYY-MM-DD). Default = last day in fit window.")
    p.add_argument("--output", default=None,
                   help="Optional JSON path to dump fitted weights "
                        "(usable by deploy/lipmm_run as a config import).")
    p.add_argument("--verbose", action="store_true",
                   help="DEBUG-level logging.")
    return p.parse_args(argv)


# ── Fit helpers ─────────────────────────────────────────────────────


def _build_design_matrix(
    actuals: dict[date, float],
    yf: dict[str, dict[date, float]],
    symbols: tuple[str, ...],
    start: date, end: date,
) -> tuple[np.ndarray, np.ndarray, list[date]]:
    """Build X (n_days × n_symbols) and y (n_days,) for NNLS.

    Skips days where any symbol has no on-or-before close within
    a 6-day fallback window.
    """
    rows: list[list[float]] = []
    targets: list[float] = []
    dates: list[date] = []
    for d in sorted(actuals.keys()):
        if d < start or d > end:
            continue
        row: list[float] = []
        ok = True
        for sym in symbols:
            hit = _close_on_or_before(yf.get(sym, {}), d)
            if hit is None:
                ok = False
                break
            row.append(hit[1])
        if not ok:
            continue
        rows.append(row)
        targets.append(actuals[d])
        dates.append(d)
    return np.array(rows, dtype=float), np.array(targets, dtype=float), dates


def _fit_nnls(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Solve min ||y - X·Q||² s.t. Q ≥ 0. Returns (Q, residual_norm)."""
    Q, residual = nnls(X, y)
    return Q, float(residual)


def _residual_stats(X: np.ndarray, y: np.ndarray, Q: np.ndarray) -> dict:
    pred = X @ Q
    err = pred - y
    abs_err = np.abs(err)
    return {
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mae": float(np.mean(abs_err)),
        "bias": float(np.mean(err)),
        "max_abs": float(np.max(abs_err)),
        "rmse_pct": float(np.sqrt(np.mean((err / y) ** 2)) * 100),
    }


def _to_pct_weights(
    Q: np.ndarray, prices_at_ref: list[float], ref_value: float,
    symbols: tuple[str, ...],
) -> dict[str, float]:
    """Convert fitted Q to % weights at a reference date.

    w[metal] = Q[metal] × p_metal[ref] / V[ref]

    These sum to ~1 if the fit is good (residual is small at ref).
    Cobalt is missing; the sum will be ~(1 - cobalt_share) if the
    basket is otherwise well-explained.
    """
    out: dict[str, float] = {}
    for i, sym in enumerate(symbols):
        out[sym] = Q[i] * prices_at_ref[i] / ref_value if ref_value else 0.0
    return out


def _print_fit(
    label: str, Q: np.ndarray, dates: list[date],
    stats: dict, pct_weights: dict[str, float], ref_date: date,
    ref_value: float, symbols: tuple[str, ...],
) -> None:
    print(f"  ── {label} ────────────────────────────────────")
    print(f"    fit days: {len(dates)} ({dates[0]} → {dates[-1]})")
    print(f"    bias:     {stats['bias']:+.3f} pts")
    print(f"    MAE:      {stats['mae']:.3f} pts")
    print(f"    RMSE:     {stats['rmse']:.3f} pts ({stats['rmse_pct']:.3f}%)")
    print(f"    max err:  {stats['max_abs']:.3f} pts")
    print()
    print(f"    fitted Q (Laspeyres quantities, "
          f"per representative vehicle):")
    for i, sym in enumerate(symbols):
        print(f"      Q[{sym:>8s}]  =  {Q[i]:>12.6f}")
    print()
    pct_sum = sum(pct_weights.values())
    print(f"    % weights at {ref_date} (ref index = {ref_value:.2f}):")
    for sym in symbols:
        print(f"      w[{sym:>8s}]  =  {pct_weights[sym] * 100:>6.3f}%")
    print(f"      {'sum':>10s}  =  {pct_sum * 100:>6.3f}%  "
          f"(remainder ≈ cobalt + residual)")
    print()


# ── Main ────────────────────────────────────────────────────────────


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

    # Determine fit windows
    q1_start = date(2026, 1, 1)
    q1_end = date(2026, 3, 31)
    q2_start = date(2026, 4, 1)
    q2_end = csv_last
    whole_start, whole_end = q1_start, csv_last

    print()
    print(f"  CSV:        {args.csv}")
    print(f"  CSV range:  {csv_first} → {csv_last} ({len(actuals)} days)")
    print(f"  Fit symbols: {', '.join(TRUEV_YFINANCE_SYMBOLS)}")
    print(f"  (cobalt not fitted; preserved at Q4 weight when promoting)")
    print()

    # Pull yfinance closes spanning all fit windows + a 1-week pad
    yf = _fetch_yf_closes(
        TRUEV_YFINANCE_SYMBOLS,
        q1_start - timedelta(days=7), whole_end,
    )
    coverage = {sym: len(s) for sym, s in yf.items()}
    print(f"    yfinance coverage: {coverage}")
    print()

    # Reference date for % weights conversion (last fit day if nothing passed)
    if args.reference_date:
        ref_date = date.fromisoformat(args.reference_date)
    else:
        ref_date = whole_end
    if ref_date not in actuals:
        # fall back to most recent on-or-before
        ref_date = max(d for d in actuals if d <= ref_date)
    ref_value = actuals[ref_date]
    ref_prices = []
    for sym in TRUEV_YFINANCE_SYMBOLS:
        hit = _close_on_or_before(yf.get(sym, {}), ref_date)
        if hit is None:
            print(f"ERROR: no yfinance close for {sym} on or before {ref_date}",
                  file=sys.stderr)
            return 2
        ref_prices.append(hit[1])
    print(f"    Reference date: {ref_date} (V={ref_value:.2f})")
    print()

    fits: dict[str, dict[str, Any]] = {}

    for label, start, end in [
        ("Q1 only (2026-01-01 → 2026-03-31)", q1_start, q1_end),
        ("Q2 only (2026-04-01 → today)", q2_start, q2_end),
        ("Whole period (2026-01-01 → today)", whole_start, whole_end),
    ]:
        X, y, dates = _build_design_matrix(
            actuals, yf, TRUEV_YFINANCE_SYMBOLS, start, end,
        )
        if len(dates) < 6:
            print(f"  ── {label} ─ SKIPPED ({len(dates)} days, need ≥ 6)")
            print()
            continue
        Q, _resid = _fit_nnls(X, y)
        stats = _residual_stats(X, y, Q)
        pct_weights = _to_pct_weights(
            Q, ref_prices, ref_value, TRUEV_YFINANCE_SYMBOLS,
        )
        _print_fit(label, Q, dates, stats, pct_weights, ref_date, ref_value,
                   TRUEV_YFINANCE_SYMBOLS)
        fits[label] = {
            "start": start.isoformat(), "end": end.isoformat(),
            "n_days": len(dates),
            "Q": {sym: float(q) for sym, q in zip(TRUEV_YFINANCE_SYMBOLS, Q)},
            "pct_weights": pct_weights,
            "stats": stats,
        }

    # ── Promotion-ready output ─────────────────────────────────────
    # Rebuild a 6-component weight dict keyed for live use:
    # LIT → LITHIUM_TE swap, cobalt re-injected at Q4 weight, all
    # weights renormalized to sum to 1.0.
    print("  ── Promotion-ready weights (Whole-period fit) ─────────")
    whole_label = "Whole period (2026-01-01 → today)"
    if whole_label in fits:
        wp = fits[whole_label]["pct_weights"]
        cobalt_q4 = 0.0822
        # Scale fitted 5 weights so they sum to (1 - cobalt_q4).
        fitted_sum = sum(wp.values()) or 1.0
        scale = (1.0 - cobalt_q4) / fitted_sum
        promote = {
            "HG=F":       wp["HG=F"] * scale,
            "LITHIUM_TE": wp["LIT"] * scale,        # key swap
            "NICK.L":     wp["NICK.L"] * scale,
            "COBALT_TE":  cobalt_q4,
            "PA=F":       wp["PA=F"] * scale,
            "PL=F":       wp["PL=F"] * scale,
        }
        total = sum(promote.values())
        print(f"    (cobalt re-injected at Q4 weight {cobalt_q4:.4f}, "
              f"others rescaled by {scale:.4f})")
        print(f"    sum = {total:.6f}")
        for sym, w in promote.items():
            print(f"      {sym:>10s}  =  {w * 100:>6.3f}%")
        print()
        fits["promote"] = promote

    if args.output:
        with open(args.output, "w") as f:
            json.dump(fits, f, indent=2, default=str)
        print(f"  fits → {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
