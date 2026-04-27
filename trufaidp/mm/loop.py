"""Live MM loop for KXTRUFAIDP-26APR27.

Cycle (~1Hz):
  1. Compute theo for all 15 strikes (basket-GBM, ~ms).
  2. Fetch each strike's order book (REST GET, sequential — 15 calls
     in ~1s). Tighten this up with WS later.
  3. Read positions snapshot.
  4. Build StrikeBook per ticker → quoter → list[Quote].
  5. RiskGate.check() decides OK / PASSIVE_ONLY / PULL_ALL.
  6. OrderManager.reconcile(desired) — diff vs open, cancel+place
     only on changes (preserves queue priority).
  7. On signal / fatal exception: cancel_all() + exit.

Run via `python -m trufaidp.mm.loop` (live) or `--dry-run` (logs
intended actions, no API placement).
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from trufaidp.kalshi import KalshiClient
from trufaidp.mm.order_manager import OrderManager
from trufaidp.mm.quoter import QuoterConfig, StrikeBook, decide_quotes
from trufaidp.mm.risk import RiskConfig, RiskGate, RiskState
from trufaidp.pricer import _load_config, _DEFAULT_CONFIG, price_once


_log = logging.getLogger("trufaidp.mm.loop")


def _ticker_for_strike(event_ticker: str, strike: float) -> str:
    return f"{event_ticker}-T{strike:.2f}"


def _seconds_to_settlement(settlement_iso: str) -> float:
    settlement = datetime.fromisoformat(settlement_iso.replace("Z", "+00:00"))
    return (settlement - datetime.now(timezone.utc)).total_seconds()


def run(*, dry_run: bool, cycle_seconds: float = 1.0) -> None:
    cfg = _load_config(_DEFAULT_CONFIG)
    event = cfg["event_ticker"]
    settlement_iso = cfg["settlement_utc"]
    strikes = cfg["strikes"]
    tickers = [_ticker_for_strike(event, k) for k in strikes]

    client = KalshiClient()
    om = OrderManager(client, dry_run=dry_run)
    quoter_cfg = QuoterConfig()
    risk = RiskGate(RiskConfig(
        aggregate_position_limit=quoter_cfg.aggregate_position_limit,
        per_strike_position_limit=quoter_cfg.per_strike_position_limit,
    ))

    stop = {"flag": False}

    def _handler(*_):
        _log.warning("signal received — cancelling all and exiting")
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)

    try:
        while not stop["flag"]:
            cycle_start = time.monotonic()
            try:
                snap = price_once(_DEFAULT_CONFIG)
            except Exception as exc:
                _log.error("theo compute failed: %s", exc)
                risk.record_error()
                time.sleep(cycle_seconds)
                continue

            theo_cents_by_ticker: dict[str, int] = {}
            yes_prob_by_strike = dict(zip(strikes, snap.yes_prob))
            for k, t in zip(strikes, tickers):
                theo_cents_by_ticker[t] = max(1, min(99, int(round(yes_prob_by_strike[k] * 100))))

            try:
                pos_list = client.get_positions()
            except Exception as exc:
                _log.error("get_positions failed: %s", exc)
                risk.record_error()
                time.sleep(cycle_seconds)
                continue

            positions: dict[str, int] = {t: 0 for t in tickers}
            for p in pos_list:
                if p.ticker in positions:
                    positions[p.ticker] = p.position

            seconds_left = _seconds_to_settlement(settlement_iso)
            state = risk.check(
                seconds_to_settlement=seconds_left,
                positions_by_strike=positions,
                theos_by_strike=theo_cents_by_ticker,
            )

            if state is RiskState.PULL_ALL:
                cancelled = om.cancel_all()
                if cancelled:
                    _log.warning("PULL_ALL: cancelled %d orders (state reason logged earlier)", cancelled)
                _sleep_remainder(cycle_start, cycle_seconds)
                continue

            books: list[StrikeBook] = []
            for ticker in tickers:
                try:
                    ob = client.get_orderbook(ticker)
                except Exception as exc:
                    _log.error("get_orderbook(%s) failed: %s", ticker, exc)
                    risk.record_error()
                    continue
                best_yes = max((p for p, _ in ob.yes), default=0)
                best_no = max((p for p, _ in ob.no), default=0)
                books.append(StrikeBook(
                    ticker=ticker,
                    theo_cents=theo_cents_by_ticker[ticker],
                    best_yes_bid=best_yes,
                    best_no_bid=best_no,
                    yes_position=positions[ticker],
                ))

            agg = sum(abs(p) for p in positions.values())
            desired: list = []
            for sb in books:
                quotes = decide_quotes(sb, agg, quoter_cfg)
                if state is RiskState.PASSIVE_ONLY:
                    quotes = [q for q in quotes if _is_offload(q.side, sb.yes_position)]
                desired.extend(quotes)

            try:
                cancels, placements = om.reconcile(desired)
            except Exception as exc:
                _log.error("reconcile failed, cancelling all: %s", exc)
                risk.record_error()
                om.cancel_all()
                time.sleep(cycle_seconds)
                continue

            _log.info(
                "cycle: state=%s tickers=%d desired=%d cancels=%d placements=%d agg_pos=%d sec_left=%.0f",
                state.value, len(books), len(desired), cancels, placements, agg, seconds_left,
            )

            _sleep_remainder(cycle_start, cycle_seconds)
    finally:
        try:
            n = om.cancel_all()
            _log.warning("shutdown: cancelled %d orders", n)
        finally:
            client.close()


def _is_offload(side, yes_position: int) -> bool:
    from trufaidp.kalshi import Side
    if yes_position > 0:
        return side is Side.NO_BUY
    if yes_position < 0:
        return side is Side.YES_BUY
    return False


def _sleep_remainder(cycle_start: float, target_seconds: float) -> None:
    elapsed = time.monotonic() - cycle_start
    remaining = target_seconds - elapsed
    if remaining > 0:
        time.sleep(remaining)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="log intended orders, no API placement")
    parser.add_argument("--cycle-seconds", type=float, default=1.0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        run(dry_run=args.dry_run, cycle_seconds=args.cycle_seconds)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
