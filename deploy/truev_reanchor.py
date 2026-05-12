"""truev_reanchor — pull yesterday's commodity closes + prompt for the
Truflation EV-index value, print a config snippet to paste into
`lipmm/theo/providers/_truev_index.py`.

Truflation publishes the EV index ONCE per day at end-of-day. The
TheoProvider's anchor MUST be (yesterday's published value, yesterday's
component closes) — any other anchor produces a biased model.

Usage:
    python -m deploy.truev_reanchor                  # uses yesterday
    python -m deploy.truev_reanchor --date 2026-05-06  # specific day
    python -m deploy.truev_reanchor --date 2026-05-06 --index 1259.69

If --index is omitted, the script asks the operator interactively to
read it off truflation.com/marketplace/ev-index. Cobalt has no daily
yfinance feed; the script uses today's TE spot as a proxy (cobalt
moves slowly day-to-day, acceptable bias).

Output is a Python dict ready to drop into DEFAULT_ANCHOR_PLACEHOLDER
or pass via --truev-anchor-index / --truev-anchor-date flags.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m deploy.truev_reanchor")
    p.add_argument("--date", default=None,
                   help="ISO date (YYYY-MM-DD) for anchor day. "
                        "Defaults to yesterday (last completed Truflation print).")
    p.add_argument("--index", type=float, default=None,
                   help="Truflation EV-index value for anchor day. "
                        "If omitted, prompts interactively.")
    return p.parse_args(argv)


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.date:
        try:
            anchor_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: invalid date {args.date!r}; expected YYYY-MM-DD",
                  file=sys.stderr)
            return 2
    else:
        anchor_date = _yesterday()

    # Pull yfinance closes for the 4 yfinance-clean components on
    # anchor_date. We use a 5-day window starting 2 days before to
    # handle weekends. Lithium is fetched from TE-spot below (no longer
    # uses LIT-the-equity-ETF for live theo) and cobalt is the same.
    import yfinance as yf
    syms = ("HG=F", "NICK.L", "PA=F", "PL=F")
    start = (anchor_date - timedelta(days=4)).isoformat()
    end = (anchor_date + timedelta(days=2)).isoformat()
    closes: dict[str, float] = {}
    for sym in syms:
        try:
            h = yf.Ticker(sym).history(start=start, end=end)
        except Exception as exc:
            print(f"  {sym}: yfinance fetch failed: {exc}")
            continue
        # Find the most recent close on-or-before anchor_date.
        # IMPORTANT: this can fall back to a STALE close if anchor_date
        # itself has no data (yfinance backfill lag). The fall-back is
        # the same family of bug the lithium / cobalt TE-spot branches
        # had — silent staleness zeroes the day's signal. Marker below
        # surfaces it visually so the operator can spot it.
        best = None
        for idx, row in h.iterrows():
            d = idx.date()
            close_val = float(row["Close"]) if row["Close"] == row["Close"] else None
            if close_val is None or close_val <= 0:
                continue   # skip NaN closes; backfill may take a day
            if d <= anchor_date:
                best = (d, close_val)
        if best is None:
            print(f"  {sym}: no close available on or before {anchor_date}")
            continue
        actual_date, close = best
        closes[sym] = close
        if actual_date != anchor_date:
            marker = (f"  ⚠️ STALE: using {actual_date} (yfinance has no "
                      f"non-NaN close for {anchor_date}); rerun later "
                      f"once data backfills")
        else:
            marker = ""
        print(f"  {sym:8s} {anchor_date}  close={close:.4f}{marker}")

    # TE-only commodities: cobalt + lithium. TE has no historicals so we
    # have to use the live spot as a proxy for the anchor day's close.
    # **Latent bug**: if the live spot has moved AFTER the anchor day's
    # actual close, that delta gets zeroed in tomorrow's reconstruction
    # (we'd compute today/anchor with anchor=current_spot, so day-over-
    # day moves disappear). Best mitigation: re-anchor as soon after the
    # truflation EOD print as possible, ideally same evening, so the TE
    # spot we capture is close to that day's close.
    print()
    try:
        from feeds.tradingeconomics.spot import (
            get_cobalt_spot, get_lithium_spot,
        )
        for label, key, fetcher in [
            ("COBALT_TE",  "COBALT_TE",  get_cobalt_spot),
            ("LITHIUM_TE", "LITHIUM_TE", get_lithium_spot),
        ]:
            v = fetcher()
            if v is None or v <= 0:
                print(f"  {label}: TE scrape failed — fill in manually")
                continue
            print(f"  {label}: live TE spot = {v:.2f} (used as proxy "
                  f"for {anchor_date} close — TE has no historicals; "
                  f"latent staleness if spot has drifted since "
                  f"truflation cutoff)")
            closes[key] = float(v)
    except Exception as exc:
        print(f"  TE scrape error: {exc}")

    # Index value: arg, env, or prompt
    print()
    if args.index is not None:
        index_value = args.index
    else:
        url = "https://truflation.com/marketplace/ev-index"
        print(f"  Read the EV-index value for {anchor_date} from:")
        print(f"     {url}")
        try:
            raw = input("  anchor_index_value (e.g. 1259.69): ").strip()
            index_value = float(raw)
        except (ValueError, EOFError, KeyboardInterrupt):
            print("\n  no index value provided; skipping")
            return 1

    # Output: Python dict snippet
    print()
    print("=" * 78)
    print("  Anchor block — paste into lipmm/theo/providers/_truev_index.py")
    print("  (replaces the body of DEFAULT_ANCHOR_PLACEHOLDER)")
    print("=" * 78)
    print()
    print(f'    anchor_date="{anchor_date.isoformat()}",')
    print(f"    anchor_index_value={index_value},  # truflation.com print")
    print(f"    anchor_prices={{")
    # Order matches the live TRUEV_PHASE1_SYMBOLS basket: 6 components,
    # LITHIUM_TE replaces the old LIT equity-ETF proxy.
    for sym in ("HG=F", "LITHIUM_TE", "NICK.L", "COBALT_TE", "PA=F", "PL=F"):
        v = closes.get(sym)
        if v is None:
            print(f'        "{sym}": 0.0,  # MISSING — fill in manually')
        else:
            print(f'        "{sym}": {v:.4f},')
    print(f"    }},")
    print()
    print("Or pass via CLI flags on lipmm_run:")
    print(f"  --truev-anchor-date {anchor_date.isoformat()} \\")
    print(f"  --truev-anchor-index {index_value}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
