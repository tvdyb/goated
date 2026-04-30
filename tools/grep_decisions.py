#!/usr/bin/env python3
"""Read JSONL decision logs from logs/decisions/ and apply filters.

Designed for quick post-hoc questions like:
    What did the bot do on T1186.99 between 19:00 and 20:00 UTC today?
    Which cycles entered AGGRESSIVE → COOLDOWN this week?
    Show every cycle where amend latency exceeded 200ms.

Usage examples:
    python tools/grep_decisions.py --ticker T1186.99 --date 2026-04-30
    python tools/grep_decisions.py --state AGGRESSIVE --side ask --last-n 50
    python tools/grep_decisions.py --transition "AGGRESSIVE -> COOLDOWN"
    python tools/grep_decisions.py --early-return --tail 20
    python tools/grep_decisions.py --ticker T1186.99 --since 19:00 --until 20:00

By default reads today's UTC file. Use --date YYYY-MM-DD or --all-files
to widen the time range.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


LOG_DIR = Path("logs/decisions")


def utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def files_for(date: str | None, all_files: bool) -> list[Path]:
    if all_files:
        return sorted(LOG_DIR.glob("decisions_*.jsonl"))
    target = date or utc_today_str()
    out: list[Path] = []
    base = LOG_DIR / f"decisions_{target}.jsonl"
    if base.exists():
        out.append(base)
    out.extend(sorted(LOG_DIR.glob(f"decisions_{target}.[0-9][0-9].jsonl")))
    return out


def stream(files: list[Path]) -> Iterator[dict]:
    for path in files:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            continue


def parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def matches(record: dict, args: argparse.Namespace) -> bool:
    if args.ticker:
        if args.ticker not in (record.get("ticker") or ""):
            return False
    if args.state:
        states = []
        for side_dict in (record.get("sticky_state") or {}).values():
            if side_dict and side_dict.get("state"):
                states.append(side_dict["state"])
        if args.state not in states:
            return False
    if args.side:
        side_dict = (record.get("sticky_state") or {}).get(args.side)
        if not side_dict:
            return False
        if args.state and side_dict.get("state") != args.state:
            return False
    if args.transition:
        wants = args.transition  # e.g., "AGGRESSIVE -> COOLDOWN"
        try:
            from_state, to_state = [s.strip() for s in wants.split("->")]
        except ValueError:
            return False
        for tr in (record.get("transitions") or []):
            if tr.get("from") == from_state and tr.get("to") == to_state:
                if not args.side or tr.get("side") == args.side:
                    return True
        return False
    if args.early_return:
        if not (record.get("decision") or {}).get("early_return_reason"):
            return False
    if args.action:
        decision = record.get("decision") or {}
        if args.action not in (decision.get("bid_action"), decision.get("ask_action")):
            return False
    if args.since or args.until:
        ts_str = record.get("timestamp_utc", "")
        if not ts_str:
            return False
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return False
        if args.since:
            sh, sm = parse_hhmm(args.since)
            since_dt = ts.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if ts < since_dt:
                return False
        if args.until:
            uh, um = parse_hhmm(args.until)
            until_dt = ts.replace(hour=uh, minute=um, second=0, microsecond=0)
            if ts > until_dt:
                return False
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Filter and print decision-log JSONL records.",
    )
    p.add_argument("--ticker", help="substring match on ticker")
    p.add_argument("--state", help="match if any side is in this state",
                   choices=["NORMAL", "AGGRESSIVE", "RELAXING", "COOLDOWN"])
    p.add_argument("--side", help="restrict to this side", choices=["bid", "ask"])
    p.add_argument("--transition", help='e.g. "AGGRESSIVE -> COOLDOWN"')
    p.add_argument("--early-return", action="store_true",
                   help="only records with early_return_reason set")
    p.add_argument("--action",
                   help="match if either side took this action "
                        "(amend|cancel_and_replace|place_new|no_change|cooldown_cancel)")
    p.add_argument("--since", help='HH:MM (UTC) lower bound for today/--date')
    p.add_argument("--until", help='HH:MM (UTC) upper bound')
    p.add_argument("--date", help="UTC date YYYY-MM-DD (default: today)")
    p.add_argument("--all-files", action="store_true",
                   help="scan every file in logs/decisions/")
    p.add_argument("--tail", type=int, default=0,
                   help="show only the last N matching records")
    p.add_argument("--last-n", type=int, default=0,
                   help="alias for --tail")
    p.add_argument("--count", action="store_true",
                   help="print count of matches instead of records")
    p.add_argument("--compact", action="store_true",
                   help="one-line summary per record instead of full JSON")
    args = p.parse_args()

    if args.last_n and not args.tail:
        args.tail = args.last_n

    files = files_for(args.date, args.all_files)
    if not files:
        print(f"no log files found in {LOG_DIR}/", file=sys.stderr)
        return 1

    matched: list[dict] = []
    for record in stream(files):
        if matches(record, args):
            matched.append(record)

    if args.tail:
        matched = matched[-args.tail:]

    if args.count:
        print(len(matched))
        return 0

    for r in matched:
        if args.compact:
            ts = r.get("timestamp_utc", "?")[:23]
            tk = (r.get("ticker") or "?")[-12:]
            d = r.get("decision") or {}
            ss = r.get("sticky_state") or {}
            ask_st = (ss.get("ask") or {}).get("state", "?")
            bid_st = (ss.get("bid") or {}).get("state", "?")
            print(
                f"{ts}  {tk}  bid:{bid_st:11s} ask:{ask_st:11s}  "
                f"final {d.get('final_bid','-')}/{d.get('final_ask','-')}  "
                f"{d.get('bid_action','')}/{d.get('ask_action','')}  "
                f"{d.get('early_return_reason') or ''}"
            )
        else:
            print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
