"""truev_smoke — read-only diagnostics for the KXTRUEV theo model.

Pulls live yfinance prices for the 4-component basket, reconstructs
today's index value, fetches each strike's current Kalshi orderbook,
and prints a side-by-side table of model P(YES) vs Kalshi mid.

Usage:
    python -m deploy.truev_smoke --event-ticker KXTRUEV-26MAY07
    python -m deploy.truev_smoke --event-ticker KXTRUEV-26MAY07 --anchor-index 1295.0
    python -m deploy.truev_smoke --event-ticker KXTRUEV-26MAY07 --vol 0.4

NO orders are placed. Read-only. Safe to run any time.

Operator workflow:
  1. Run this BEFORE going live to sanity-check the model. Big
     divergence between model and Kalshi mid → either edge is real, or
     the anchor is stale.
  2. If model_index ≠ Kalshi-implied spot by >30 points, recalibrate:
     read truflation.com/marketplace/ev-index for today's value, pass
     via --anchor-index <new_value>.
  3. Iterate σ via --vol if the strike-curve shape doesn't match.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import replace

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from feeds.truflation import TruEvForwardSource
from lipmm.theo.providers import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_Q4_2025,
    TruEVConfig,
    TruEVTheoProvider,
    TruEvAnchor,
    reconstruct_index,
)

logger = logging.getLogger("truev_smoke")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m deploy.truev_smoke")
    p.add_argument("--event-ticker", required=True,
                   help="e.g. KXTRUEV-26MAY07")
    p.add_argument("--settlement-iso", default="",
                   help="Settlement ISO datetime (default: 7:59 PM EDT today)")
    p.add_argument("--anchor-index", type=float, default=None,
                   help="Override anchor index value (else uses placeholder)")
    p.add_argument("--anchor-date", default=None,
                   help="Override anchor date label (informational)")
    p.add_argument("--vol", type=float, default=0.30,
                   help="Annualized σ (default 0.30)")
    p.add_argument("--max-confidence", type=float, default=0.7,
                   help="Confidence cap (default 0.7)")
    p.add_argument("--direction", choices=["above", "below"], default="above")
    p.add_argument("--log-level", default="WARNING",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


def _default_settlement_iso(event_ticker: str) -> str:
    """Best-effort default: today at 7:59 PM EDT (Kalshi market close).
    Operator should override via --settlement-iso once the actual
    settlement time is confirmed from the event metadata."""
    from datetime import datetime, timedelta, timezone
    # EDT = UTC-4; close at 19:59 EDT = 23:59 UTC
    today = datetime.now(timezone.utc).date()
    iso = f"{today.isoformat()}T23:59:00+00:00"
    return iso


def _kalshi_mid_from_book(yes_levels, no_levels) -> tuple[int | None, int | None]:
    """Return (best_bid_c, best_ask_c) in cents from Kalshi orderbook
    (yes_levels = yes-bids dollars-strings; no_levels = no-bids).
    Best yes-ask is derived from highest no-bid: ask_c = 100 − no_bid_c."""
    best_bid_c = None
    if yes_levels:
        prices = [float(p) for p, _s in yes_levels]
        best_bid_c = int(round(max(prices) * 100))
    best_ask_c = None
    if no_levels:
        no_bids = [float(p) for p, _s in no_levels]
        best_ask_c = int(round((1.0 - max(no_bids)) * 100))
    return best_bid_c, best_ask_c


async def _amain(args: argparse.Namespace) -> int:
    auth = KalshiAuth()
    client = KalshiClient(auth=auth)
    await client.open()

    # Build anchor — possibly override the placeholder index value
    anchor = DEFAULT_ANCHOR_PLACEHOLDER
    if args.anchor_index is not None or args.anchor_date is not None:
        anchor = TruEvAnchor(
            anchor_date=args.anchor_date or anchor.anchor_date,
            anchor_index_value=args.anchor_index if args.anchor_index is not None
                else anchor.anchor_index_value,
            anchor_prices=dict(anchor.anchor_prices),
        )

    settlement_iso = args.settlement_iso or _default_settlement_iso(args.event_ticker)

    cfg = TruEVConfig(
        settlement_time_iso=settlement_iso,
        weights=DEFAULT_WEIGHTS_Q4_2025,
        anchor=anchor,
        annualized_vol=args.vol,
        max_confidence=args.max_confidence,
        direction=args.direction,
    )

    forward = TruEvForwardSource(poll_interval_s=120.0)
    provider = TruEVTheoProvider(cfg, forward)

    try:
        await provider.warmup()  # primes forward source

        # Header
        print()
        print("=" * 80)
        print(f"  TruEV smoke — {args.event_ticker}")
        print("=" * 80)
        print(f"  settlement_iso:   {settlement_iso}")
        print(f"  anchor_date:      {anchor.anchor_date}")
        print(f"  anchor_index:     {anchor.anchor_index_value}")
        print(f"  σ (annualized):   {args.vol:.4f}")
        print(f"  max_confidence:   {args.max_confidence}")
        print(f"  direction:        {args.direction}")
        print()
        print("  yfinance prices (today vs anchor):")
        prices = forward.latest_prices()
        for sym, w in cfg.weights.weights.items():
            now_p = prices.get(sym)
            anchor_p = anchor.anchor_prices.get(sym)
            if now_p is None:
                print(f"    {sym:6s}  weight={w:.4f}  today=MISSING  anchor={anchor_p}")
                continue
            ratio = (now_p[0] / anchor_p) if anchor_p else float("nan")
            print(
                f"    {sym:6s}  weight={w:.4f}  today={now_p[0]:.4f}  "
                f"anchor={anchor_p:.4f}  ratio={ratio:.4f}"
            )

        # Reconstruct
        try:
            current = {sym: prices[sym][0] for sym in cfg.weights.weights}
            model_index = reconstruct_index(current, cfg.weights, anchor)
            print(f"\n  reconstructed model_index: {model_index:.4f}")
        except (KeyError, ValueError) as exc:
            print(f"\n  ERROR reconstructing index: {exc}")
            return 2

        # Fetch event + strikes
        print()
        print("=" * 80)
        print(f"  Per-strike model P vs Kalshi mid")
        print("=" * 80)
        try:
            resp = await client.get_event(
                args.event_ticker, with_nested_markets=True,
            )
        except Exception as exc:
            print(f"  ERROR fetching event: {exc}")
            return 3

        event = resp.get("event") or {}
        markets = (event.get("markets") or []) + (resp.get("markets") or [])
        # Dedupe
        seen = set()
        unique = []
        for m in markets:
            t = m.get("ticker")
            if t and t not in seen:
                seen.add(t)
                unique.append(m)

        # Sort by strike (parse from ticker)
        def _strike_of(m):
            t = m.get("ticker", "")
            last = t.rsplit("-", 1)[-1]
            if last.startswith("T"):
                try:
                    return float(last[1:])
                except ValueError:
                    return 0.0
            return 0.0
        unique.sort(key=_strike_of)

        if not unique:
            print(f"  no markets found under {args.event_ticker}")
            return 4

        # Header row
        print()
        print(f"  {'TICKER':40s}  {'STRIKE':>10s}  {'MODEL %':>9s}  "
              f"{'MID %':>8s}  {'BID':>5s}  {'ASK':>5s}  {'Δ %':>7s}  "
              f"{'CONF':>5s}")

        skipped = 0
        for m in unique:
            t = m.get("ticker", "?")
            strike = _strike_of(m)
            status = m.get("status")
            if status not in ("active", None):
                skipped += 1
                continue

            # Theo
            try:
                theo = await provider.theo(t)
            except Exception as exc:
                print(f"  {t:40s}  theo error: {exc}")
                continue

            model_pct = theo.yes_probability * 100
            conf = theo.confidence

            # Kalshi mid
            try:
                ob = await client.get_orderbook(t)
                fp = ob.get("orderbook_fp") or {}
                yes_bids = fp.get("yes_dollars") or []
                no_bids = fp.get("no_dollars") or []
                bid_c, ask_c = _kalshi_mid_from_book(yes_bids, no_bids)
                if bid_c is not None and ask_c is not None:
                    mid_c = (bid_c + ask_c) / 2
                    delta = model_pct - mid_c
                    print(
                        f"  {t:40s}  {strike:10.2f}  {model_pct:9.2f}  "
                        f"{mid_c:8.2f}  {bid_c:5d}  {ask_c:5d}  {delta:+7.2f}  "
                        f"{conf:5.2f}"
                    )
                else:
                    bid_str = str(bid_c) if bid_c is not None else "-"
                    ask_str = str(ask_c) if ask_c is not None else "-"
                    print(
                        f"  {t:40s}  {strike:10.2f}  {model_pct:9.2f}  "
                        f"{'-':>8s}  {bid_str:>5s}  {ask_str:>5s}  "
                        f"{'-':>7s}  {conf:5.2f}"
                    )
            except Exception as exc:
                print(f"  {t:40s}  orderbook error: {exc}")

        if skipped > 0:
            print(f"\n  ({skipped} non-active strikes skipped)")

        # Verdict
        print()
        print("=" * 80)
        print("  Anchor verification:")
        print(f"  If `model_index` is far from the at-the-money strike's")
        print(f"  Kalshi mid (>30 pts on a ~1290 base), the anchor is stale.")
        print(f"  Recalibrate via --anchor-index <today_truflation_value>.")
        print("=" * 80)
        print()

    finally:
        await provider.shutdown()
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
