"""truev_backtest — historical accuracy of the TruEV theo model.

Pulls every settled `KXTRUEV-*` event from Kalshi, resolves the
implied actual index value from the strike-resolution boundary,
pulls yfinance historical commodity closes for the same dates,
and reports model-vs-actual residuals + implied annualized σ.

Output:
  - Per-day table: date | actual | model | residual | basket_return
  - Summary block: N days, mean error, RMSE, max error, σ_implied,
    best-fit anchor index value (RMSE-minimizing)
  - Optional CSV dump (--output-csv PATH)

Read-only — no orders placed, no state mutated. Safe to run any time.

Usage:
    python -m deploy.truev_backtest --series KXTRUEV
    python -m deploy.truev_backtest --series KXTRUEV --output-csv /tmp/truev.csv
    python -m deploy.truev_backtest --series KXTRUEV --max-events 50
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta
from typing import Any

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from feeds.truflation import TRUEV_YFINANCE_SYMBOLS
from lipmm.theo.providers._truev_index import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_BACKTEST,
    TruEvAnchor,
    TruEvWeights,
    reconstruct_index,
)

logger = logging.getLogger("truev_backtest")


# ── CLI ──────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m deploy.truev_backtest")
    p.add_argument("--series", default="KXTRUEV",
                   help="Kalshi series ticker (default KXTRUEV)")
    p.add_argument("--max-events", type=int, default=500,
                   help="Cap on settled events to fetch (default 500). "
                        "Pagination stops early on cursor exhaustion.")
    p.add_argument("--anchor-date", default=None,
                   help="Override anchor date label (informational)")
    p.add_argument("--anchor-index", type=float, default=None,
                   help="Override anchor index value (else uses placeholder)")
    p.add_argument("--output-csv", default=None,
                   help="Optional CSV path for the per-day rows")
    p.add_argument("--auto-calibrate-anchor", action="store_true",
                   help="Search the anchor_index_value that minimizes RMSE "
                        "and report it. Doesn't write to disk — operator "
                        "copies into config manually.")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


# ── Date parsing from event ticker ───────────────────────────────────


_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _date_from_event_ticker(ticker: str) -> date_cls | None:
    """Parse 'KXTRUEV-26MAY07' → date(2026, 5, 7).
    Kalshi convention: YY MMM DD. Returns None on parse failure."""
    parts = ticker.split("-")
    if len(parts) < 2:
        return None
    tail = parts[-1]                    # "26MAY07"
    if len(tail) != 7:
        return None
    try:
        yy = int(tail[0:2])
        mon = tail[2:5].upper()
        dd = int(tail[5:7])
        if mon not in _MONTHS:
            return None
        return date_cls(2000 + yy, _MONTHS[mon], dd)
    except ValueError:
        return None


# ── Strike-boundary resolution ───────────────────────────────────────


@dataclass(frozen=True)
class _Strike:
    ticker: str
    threshold: float
    result: str                       # "yes" / "no" / "" / etc

    @property
    def settled(self) -> bool:
        return self.result in ("yes", "no")


def _strike_threshold_from_market(m: dict[str, Any]) -> float | None:
    """Pull the threshold value from a market dict. Tries floor_strike,
    cap_strike, then a `T<num>` segment of the ticker."""
    for k in ("floor_strike", "cap_strike", "strike"):
        v = m.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    t = m.get("ticker", "")
    last = t.rsplit("-", 1)[-1]
    if last.startswith("T"):
        try:
            return float(last[1:])
        except ValueError:
            return None
    return None


def _exact_actual_value_from_expiration(
    markets: list[dict[str, Any]],
) -> float | None:
    """Read the exact TruEV settle value from any market's
    `expiration_value` field (Kalshi populates this with the
    underlying's settlement reference price). All markets in the
    same event share the same expiration_value, so we just take the
    first one that has a parseable numeric.

    Replaces the older boundary-midpoint estimate which was off by
    up to half a strike's spacing (~5 pts on a typical 10-pt grid).
    """
    for m in markets:
        v = m.get("expiration_value")
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _implied_actual_value(markets: list[dict[str, Any]]) -> float | None:
    """Fallback: derive the actual value from strike-resolution
    boundaries when `expiration_value` isn't populated.

    Convention assumed: each strike `T_K` resolves YES iff
    settle_value > K (i.e. "above K"). Used only when the exact
    value is missing — yields up to ±(strike_spacing/2) error.
    """
    rows: list[_Strike] = []
    for m in markets:
        thr = _strike_threshold_from_market(m)
        if thr is None:
            continue
        rows.append(_Strike(
            ticker=m.get("ticker", ""),
            threshold=thr,
            result=str(m.get("result") or "").lower(),
        ))
    rows = [r for r in rows if r.settled]
    if not rows:
        return None
    rows.sort(key=lambda r: r.threshold)
    last_yes_idx = None
    first_no_idx = None
    for i, r in enumerate(rows):
        if r.result == "yes":
            last_yes_idx = i
        elif r.result == "no" and first_no_idx is None:
            first_no_idx = i
    if last_yes_idx is None and first_no_idx is None:
        return None
    if last_yes_idx is None:
        return rows[0].threshold - 1.0
    if first_no_idx is None:
        return rows[-1].threshold + 1.0
    if last_yes_idx + 1 != first_no_idx:
        last_no_idx = max(
            (i for i, r in enumerate(rows) if r.result == "no"),
            default=None,
        )
        first_yes_idx = min(
            (i for i, r in enumerate(rows) if r.result == "yes"),
            default=None,
        )
        if (last_no_idx is not None and first_yes_idx is not None
                and last_no_idx + 1 == first_yes_idx):
            return 0.5 * (rows[last_no_idx].threshold + rows[first_yes_idx].threshold)
        return None
    return 0.5 * (rows[last_yes_idx].threshold + rows[first_no_idx].threshold)


# ── Fetch ────────────────────────────────────────────────────────────


async def _fetch_settled_events(
    client: KalshiClient, *, series: str, max_events: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(out) < max_events:
        resp = await client.get_events(
            series_ticker=series, status="settled",
            limit=min(200, max_events - len(out)),
            cursor=cursor,
        )
        events = resp.get("events") or []
        if not events:
            break
        out.extend(events)
        cursor = resp.get("cursor") or resp.get("next_cursor")
        if not cursor:
            break
    return out[:max_events]


def _fetch_yfinance_history(
    symbols: tuple[str, ...], start: date_cls, end: date_cls,
) -> dict[str, dict[date_cls, float]]:
    """Returns {symbol: {date: close}}. End date is inclusive — we add
    one day to yfinance's exclusive end. Forward-fills weekend gaps
    using the most recent prior close (including pre-`start` data so
    `start` itself is filled even if it's a non-trading day)."""
    import yfinance as yf
    out: dict[str, dict[date_cls, float]] = {sym: {} for sym in symbols}
    yf_end = end + timedelta(days=2)        # inclusive + buffer
    yf_start = start - timedelta(days=14)   # buffer for forward-fill

    for sym in symbols:
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(start=yf_start.isoformat(), end=yf_end.isoformat())
        except Exception as exc:
            logger.warning("yfinance fetch %s failed: %s", sym, exc)
            continue
        if hist.empty:
            logger.warning("yfinance: no history for %s", sym)
            continue
        # Collect (date, close) pairs sorted ascending
        raw: list[tuple[date_cls, float]] = []
        for dt_idx, row in hist.iterrows():
            d = dt_idx.date()
            try:
                c = float(row["Close"])
            except (KeyError, ValueError, TypeError):
                continue
            if c > 0:
                raw.append((d, c))
        if not raw:
            logger.warning("yfinance: %s parsed no valid closes", sym)
            continue
        raw.sort(key=lambda x: x[0])

        # For each date in [start, end], use the most recent yfinance
        # close at-or-before that date. raw is sorted, so we sweep it
        # forward as `cur` advances.
        i = 0
        cur = start
        # Seed: advance i to the latest raw[i][0] <= start
        while i + 1 < len(raw) and raw[i + 1][0] <= start:
            i += 1
        while cur <= end:
            while i + 1 < len(raw) and raw[i + 1][0] <= cur:
                i += 1
            if raw[i][0] <= cur:
                out[sym][cur] = raw[i][1]
            cur += timedelta(days=1)
    return out


# ── Stats ────────────────────────────────────────────────────────────


def _compute_implied_sigma(
    actuals_by_date: dict[date_cls, float],
) -> tuple[float, float, int]:
    """Returns (sigma_daily, sigma_annual, n_returns) from log returns
    of the actual series. Skips weekend/holiday gaps. Returns (0, 0, 0)
    if fewer than 2 data points."""
    sorted_dates = sorted(actuals_by_date.keys())
    if len(sorted_dates) < 2:
        return 0.0, 0.0, 0
    rets: list[float] = []
    for prev, curr in zip(sorted_dates, sorted_dates[1:]):
        v_prev = actuals_by_date[prev]
        v_curr = actuals_by_date[curr]
        if v_prev <= 0 or v_curr <= 0:
            continue
        rets.append(math.log(v_curr / v_prev))
    if len(rets) < 2:
        return 0.0, 0.0, len(rets)
    sigma_d = statistics.pstdev(rets)
    sigma_a = sigma_d * math.sqrt(252)
    return sigma_d, sigma_a, len(rets)


def _best_fit_anchor(
    rows: list[tuple[date_cls, float, dict[str, float]]],
    weights: TruEvWeights,
    anchor_prices: dict[str, float],
    anchor_date: str,
) -> tuple[float, float]:
    """Search the anchor_index_value that minimizes RMSE between
    model and actual across the rows. The model is linear in
    anchor_index_value, so the optimal is closed-form.

    For a single anchor_a value:
      model_t = a × b_t       where b_t = Σ wᵢ × (priceᵢ_t / priceᵢ_anchor)
      residual_t = a × b_t − actual_t
      RMSE² ∝ Σ (a × b_t − actual_t)²
    Setting d/da = 0:
      a* = Σ b_t × actual_t  /  Σ b_t²
    """
    bs: list[float] = []
    actuals: list[float] = []
    for d, actual, prices_t in rows:
        try:
            b_t = sum(
                w * (prices_t[sym] / anchor_prices[sym])
                for sym, w in weights.weights.items()
            )
        except (KeyError, ZeroDivisionError):
            continue
        bs.append(b_t)
        actuals.append(actual)
    if not bs:
        return 0.0, float("inf")
    num = sum(b * a for b, a in zip(bs, actuals))
    den = sum(b * b for b in bs)
    if den == 0:
        return 0.0, float("inf")
    a_star = num / den
    sq_err = sum((a_star * b - act) ** 2 for b, act in zip(bs, actuals))
    rmse = math.sqrt(sq_err / len(bs))
    return a_star, rmse


# ── Main ─────────────────────────────────────────────────────────────


async def _amain(args: argparse.Namespace) -> int:
    auth = KalshiAuth()
    client = KalshiClient(auth=auth)
    await client.open()

    # Build anchor (placeholder unless overridden)
    anchor = DEFAULT_ANCHOR_PLACEHOLDER
    if args.anchor_index is not None or args.anchor_date is not None:
        anchor = TruEvAnchor(
            anchor_date=args.anchor_date or anchor.anchor_date,
            anchor_index_value=(
                args.anchor_index if args.anchor_index is not None
                else anchor.anchor_index_value
            ),
            anchor_prices=dict(anchor.anchor_prices),
        )

    # 5-component basket for backtest (Cu / Li / Ni / Pd / Pt). Cobalt
    # is excluded because its only viable feed (TE scrape) has no
    # historicals; live theo uses 6 components (DEFAULT_WEIGHTS_Q4_2025).
    weights = DEFAULT_WEIGHTS_BACKTEST

    print()
    print("=" * 80)
    print(f"  TruEV backtest — series={args.series}")
    print("=" * 80)
    print(f"  anchor_date:   {anchor.anchor_date}")
    print(f"  anchor_index:  {anchor.anchor_index_value}")
    print(f"  weights:       {dict(weights.weights)}")
    print()

    # 1. Pull settled events
    try:
        events = await _fetch_settled_events(
            client, series=args.series, max_events=args.max_events,
        )
    except Exception as exc:
        print(f"  ERROR fetching events: {exc}")
        await client.close()
        return 2
    print(f"  pulled {len(events)} settled event(s)")
    if not events:
        print("  no settled events — backtest needs historical data; bail")
        await client.close()
        return 0

    # 2. Per-event: actual index value from strike boundary
    rows: list[tuple[date_cls, str, float]] = []  # (date, event_ticker, actual)
    for ev in events:
        et = ev.get("event_ticker") or ev.get("ticker")
        if not et:
            continue
        d = _date_from_event_ticker(et)
        if d is None:
            logger.info("skipping %s — unparseable date", et)
            continue
        try:
            er = await client.get_event(et, with_nested_markets=True)
        except Exception as exc:
            logger.warning("get_event(%s) failed: %s", et, exc)
            continue
        nested = (er.get("event") or {}).get("markets") or []
        sibling = er.get("markets") or []
        markets = list(nested) + list(sibling)
        # Dedupe by ticker
        seen = set()
        unique = []
        for m in markets:
            t = m.get("ticker")
            if t and t not in seen:
                seen.add(t)
                unique.append(m)
        # Prefer the exact `expiration_value` Kalshi populates with
        # the underlying settle reference; fall back to strike-
        # boundary midpoint only when missing.
        actual = _exact_actual_value_from_expiration(unique)
        if actual is None:
            actual = _implied_actual_value(unique)
            if actual is None:
                logger.info("skipping %s — no boundary", et)
                continue
        rows.append((d, et, actual))

    rows.sort(key=lambda r: r[0])
    print(f"  resolved {len(rows)} dated actual value(s) from settlement boundaries")
    if not rows:
        print("  no resolvable actual values — done")
        await client.close()
        return 0

    # 3. Yfinance history
    earliest = rows[0][0]
    latest = rows[-1][0]
    print(f"  date range: {earliest} → {latest}")
    print()
    print("  pulling yfinance history…")
    hist = _fetch_yfinance_history(TRUEV_YFINANCE_SYMBOLS, earliest, latest)
    print()

    # 4. Filter to symbols with adequate yfinance coverage. Drop any
    # symbol covering less than 50% of the date range — typically
    # LTH=F (CME Lithium Hydroxide is too illiquid on yfinance).
    min_coverage = 0.5
    span_days = (latest - earliest).days + 1
    usable_symbols: list[str] = []
    for sym in weights.weights:
        coverage = len(hist.get(sym, {})) / max(1, span_days)
        if coverage < min_coverage:
            print(f"  dropping {sym}: yfinance coverage "
                  f"{coverage:.1%} < {min_coverage:.0%} threshold")
        else:
            usable_symbols.append(sym)
    if not usable_symbols:
        print("  no symbol passed the coverage threshold — done")
        await client.close()
        return 0

    if set(usable_symbols) != set(weights.weights):
        # Renormalize the weights + anchor over the usable subset.
        raw_total = sum(weights.weights[s] for s in usable_symbols)
        weights = TruEvWeights(
            quarter_start_iso=weights.quarter_start_iso,
            weights={s: weights.weights[s] / raw_total for s in usable_symbols},
        )
        anchor = TruEvAnchor(
            anchor_date=anchor.anchor_date,
            anchor_index_value=anchor.anchor_index_value,
            anchor_prices={s: anchor.anchor_prices[s] for s in usable_symbols},
        )
        print(f"  proceeding with renormalized weights: {dict(weights.weights)}")
        print()

    # 5. Compute model per row
    table_rows: list[tuple[date_cls, float, float, float, dict[str, float]]] = []
    for d, et, actual in rows:
        prices_t: dict[str, float] = {}
        ok = True
        for sym in weights.weights:
            v = hist.get(sym, {}).get(d)
            if v is None:
                ok = False
                break
            prices_t[sym] = v
        if not ok:
            logger.info("skipping %s — yfinance missing for one symbol", d)
            continue
        try:
            model = reconstruct_index(prices_t, weights, anchor)
        except (ValueError, KeyError) as exc:
            logger.info("skipping %s — model error: %s", d, exc)
            continue
        residual = model - actual
        table_rows.append((d, actual, model, residual, prices_t))

    if not table_rows:
        print("  no rows had complete yfinance + actual data — done")
        await client.close()
        return 0

    # 6. Print per-day table
    sym_list = sorted(weights.weights.keys())
    sym_header = "  ".join(f"{s:>9s}" for s in sym_list)
    print("=" * 80)
    print(f"  {'DATE':>10s}  {'ACTUAL':>9s}  {'MODEL':>9s}  {'Δ':>8s}    {sym_header}")
    print("=" * 80)
    for d, actual, model, residual, prices_t in table_rows:
        sym_cols = "  ".join(f"{prices_t[s]:9.4f}" for s in sym_list)
        print(
            f"  {d}  {actual:9.2f}  {model:9.2f}  {residual:+8.2f}    {sym_cols}"
        )

    # 6. Summary
    actuals_by_date = {r[0]: r[1] for r in table_rows}
    residuals = [r[3] for r in table_rows]
    abs_res = [abs(x) for x in residuals]
    rmse = math.sqrt(sum(x * x for x in residuals) / len(residuals))
    sigma_d, sigma_a, n_ret = _compute_implied_sigma(actuals_by_date)

    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print(f"  N rows:          {len(table_rows)}")
    print(f"  mean residual:   {statistics.mean(residuals):+.3f}  (model − actual)")
    print(f"  median residual: {statistics.median(residuals):+.3f}")
    print(f"  RMSE:            {rmse:.3f}")
    print(f"  max |residual|:  {max(abs_res):.3f}")
    print(f"  implied σ_daily: {sigma_d:.5f}  (n_returns={n_ret})")
    print(f"  implied σ_annual:{sigma_a:.4f}   ← drop into --truev-vol")

    if args.auto_calibrate_anchor:
        rows_for_fit = [(d, a, p) for (d, a, _m, _r, p) in table_rows]
        a_star, rmse_star = _best_fit_anchor(
            rows_for_fit, weights, dict(anchor.anchor_prices), anchor.anchor_date,
        )
        print()
        print(f"  best-fit anchor_index_value: {a_star:.4f}  (RMSE={rmse_star:.3f})")
        print(f"    drop into config:")
        print(f"      anchor_date='{anchor.anchor_date}', "
              f"anchor_index_value={a_star:.4f},")
        print(f"      anchor_prices={dict(anchor.anchor_prices)}")
    print("=" * 80)

    # 8. Optional CSV
    if args.output_csv:
        with open(args.output_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "actual", "model", "residual"] + sym_list)
            for d, actual, model, residual, prices_t in table_rows:
                w.writerow([
                    d.isoformat(),
                    f"{actual:.4f}",
                    f"{model:.4f}",
                    f"{residual:.4f}",
                ] + [f"{prices_t[s]:.6f}" for s in sym_list])
        print(f"  CSV written: {args.output_csv}")

    await client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s | %(message)s",
    )
    if not os.environ.get("KALSHI_API_KEY") or not os.environ.get("KALSHI_PRIVATE_KEY_PATH"):
        sys.stderr.write(
            "ERROR: set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH env vars.\n"
        )
        return 2
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
