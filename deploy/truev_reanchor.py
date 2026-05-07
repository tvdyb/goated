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

    # Pull yfinance closes for the 5 yfinance components on anchor_date.
    # We use a 5-day window starting 2 days before to handle weekends.
    import yfinance as yf
    syms = ("HG=F", "LIT", "NICK.L", "PA=F", "PL=F")
    start = (anchor_date - timedelta(days=4)).isoformat()
    end = (anchor_date + timedelta(days=2)).isoformat()
    closes: dict[str, float] = {}
    for sym in syms:
        try:
            h = yf.Ticker(sym).history(start=start, end=end)
        except Exception as exc:
            print(f"  {sym}: yfinance fetch failed: {exc}")
            continue
        # Find the most recent close on-or-before anchor_date
        best = None
        for idx, row in h.iterrows():
            d = idx.date()
            if d <= anchor_date:
                best = (d, float(row["Close"]))
        if best is None:
            print(f"  {sym}: no close available on or before {anchor_date}")
            continue
        actual_date, close = best
        closes[sym] = close
        marker = "" if actual_date == anchor_date else f"  (using {actual_date} — closest available)"
        print(f"  {sym:8s} {anchor_date}  close={close:.4f}{marker}")

    # Cobalt: TE spot only — no historicals. Use today's spot as proxy.
    print()
    try:
        from feeds.tradingeconomics.spot import get_cobalt_spot
        cobalt = get_cobalt_spot()
        if cobalt is None:
            print("  COBALT_TE: TE scrape failed — operator must fill in manually")
            cobalt = 0.0
        else:
            print(f"  COBALT_TE: today's TE spot = {cobalt:.2f} (used as "
                  f"proxy for {anchor_date} — TE has no historicals)")
            closes["COBALT_TE"] = cobalt
    except Exception as exc:
        print(f"  COBALT_TE: error {exc}")

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
    for sym in ("HG=F", "LIT", "NICK.L", "COBALT_TE", "PA=F", "PL=F"):
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
