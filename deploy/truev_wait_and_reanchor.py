"""Wait for Kalshi to settle the next KXTRUEV event, then auto-update
DEFAULT_ANCHOR_PLACEHOLDER in lipmm/theo/providers/_truev_index.py.

Designed for unattended overnight use. Polls Kalshi every 5 minutes
(default) until the event's `expiration_value` is populated, fetches
same-day component closes (yfinance + TE), rewrites the anchor block
with an atomic backup-validate-replace, and exits.

    python -m deploy.truev_wait_and_reanchor                     # auto-detect pending event
    python -m deploy.truev_wait_and_reanchor --event KXTRUEV-26MAY11
    python -m deploy.truev_wait_and_reanchor --poll-seconds 120

Logs both to stdout AND logs/truev_autoanchor_<utcts>.log so you can
review progress in the morning.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yfinance as yf

from feeds.tradingeconomics.spot import TE_COBALT, TE_LITHIUM, get_te_spot


REPO_ROOT = Path(__file__).resolve().parent.parent
TRUEV_INDEX_PY = REPO_ROOT / "lipmm" / "theo" / "providers" / "_truev_index.py"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Matches the entire `DEFAULT_ANCHOR_PLACEHOLDER = TruEvAnchor(...)` block,
# including its leading comment lines (re.DOTALL so '.' spans newlines).
ANCHOR_BLOCK_RE = re.compile(
    r"DEFAULT_ANCHOR_PLACEHOLDER = TruEvAnchor\(\n.*?\n\)",
    re.DOTALL,
)

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("truev_autoanchor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    fmt.converter = time.gmtime
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


def event_ticker_to_iso_date(event_ticker: str) -> str:
    """KXTRUEV-26MAY11 -> '2026-05-11'."""
    suffix = event_ticker.split("-", 1)[1]
    yy, mon3, dd = suffix[:2], suffix[2:5], suffix[5:7]
    return f"20{yy}-{MONTHS[mon3]}-{dd}"


async def auto_detect_pending(client: httpx.AsyncClient, logger: logging.Logger) -> str | None:
    """Return the most-recent KXTRUEV event with `closed` markets and no
    `expiration_value` yet. Returns None if no such event exists."""
    r = await client.get(
        f"{KALSHI_BASE}/events",
        params={"series_ticker": "KXTRUEV", "limit": 50},
    )
    r.raise_for_status()
    events = r.json().get("events", [])
    for e in events:
        et = e["event_ticker"]
        r2 = await client.get(
            f"{KALSHI_BASE}/events/{et}",
            params={"with_nested_markets": "true"},
        )
        if r2.status_code != 200:
            continue
        body = r2.json()
        markets = body.get("event", {}).get("markets") or body.get("markets") or []
        if not markets:
            continue
        any_settled = any(m.get("expiration_value") for m in markets)
        if any_settled:
            logger.info(f"  {et}: already settled, skipping")
            continue
        any_closed = any(m.get("status") == "closed" for m in markets)
        if not any_closed:
            logger.info(f"  {et}: still active (not closed yet)")
            continue
        return et
    return None


async def poll_for_settlement(
    event_ticker: str,
    poll_seconds: float,
    logger: logging.Logger,
) -> float:
    """Block until `expiration_value` is populated for any market in the event.
    Returns the float value."""
    async with httpx.AsyncClient(timeout=15) as client:
        n = 0
        while True:
            try:
                r = await client.get(
                    f"{KALSHI_BASE}/events/{event_ticker}",
                    params={"with_nested_markets": "true"},
                )
                if r.status_code != 200:
                    logger.warning(f"poll: HTTP {r.status_code} (will retry)")
                else:
                    body = r.json()
                    markets = body.get("event", {}).get("markets") or body.get("markets") or []
                    vals = [m.get("expiration_value") for m in markets if m.get("expiration_value")]
                    if vals:
                        unique = list({v for v in vals})
                        if len(unique) > 1:
                            logger.warning(f"inconsistent expiration_values: {unique}; using first")
                        return float(unique[0])
            except Exception as exc:
                logger.warning(f"poll error: {exc!r} (will retry)")
            n += 1
            # Heartbeat every ~hour (assuming default 5-min poll).
            if n % max(1, int(3600 // poll_seconds)) == 0:
                logger.info(f"...still waiting on {event_ticker} (poll #{n})")
            await asyncio.sleep(poll_seconds)


def _isnan(v: float) -> bool:
    return isinstance(v, float) and math.isnan(v)


def latest_close_at_or_before(
    sym: str,
    target_iso: str,
    logger: logging.Logger,
) -> tuple[str | None, float | None]:
    """Return (date_iso, close) for the latest non-NaN close <= target_iso."""
    try:
        h = yf.Ticker(sym).history(period="14d")
    except Exception as exc:
        logger.warning(f"yfinance {sym}: fetch failed: {exc!r}")
        return None, None
    if h.empty:
        logger.warning(f"yfinance {sym}: empty history")
        return None, None
    best_date = None
    best_close = None
    for dt, close in zip(h.index, h["Close"]):
        dt_iso = dt.strftime("%Y-%m-%d")
        if dt_iso > target_iso:
            continue
        if _isnan(float(close)):
            continue
        if best_date is None or dt_iso > best_date:
            best_date = dt_iso
            best_close = float(close)
    return best_date, best_close


def pull_component_prices(
    settle_date_iso: str,
    logger: logging.Logger,
    *,
    te_overrides: dict[str, float] | None = None,
    prev_te_anchor: dict[str, float] | None = None,
    te_drift_threshold: float = 0.01,
) -> tuple[dict[str, float], dict[str, str]]:
    """Returns (prices, source_notes). Raises if anything required is missing.

    For TE-only commodities (LITHIUM_TE, COBALT_TE), `get_te_spot()` returns
    *current* spot, NOT a historical EOD. If TE has already rolled to the
    next day's value by the time we re-anchor, we'd record today's price as
    yesterday's anchor — silently zeroing out the day-over-day signal.

    Guard:
      - `te_overrides` lets the operator supply known good EOD values for
        LITHIUM_TE and/or COBALT_TE. When present, those bypass the scrape.
      - `prev_te_anchor` is the previous anchor's TE values. If the live
        scrape differs by more than `te_drift_threshold` (default 1%) from
        the prior anchor AND no override is supplied, we RAISE rather than
        silently absorb the drift. This forces operator-in-the-loop on the
        boundary case.
    """
    prices: dict[str, float] = {}
    notes: dict[str, str] = {}
    te_overrides = te_overrides or {}

    for sym in ("HG=F", "PA=F", "PL=F"):
        d, v = latest_close_at_or_before(sym, settle_date_iso, logger)
        if v is None:
            raise RuntimeError(f"required yfinance symbol {sym} unavailable at/before {settle_date_iso}")
        prices[sym] = v
        notes[sym] = f"yfinance close {d}"
        logger.info(f"  {sym} = {v} ({d})")

    # Nickel: TE LME 3-month USD/T (replaces the legacy NICK.L + GBPUSD
    # FX-strip path — TE returns USD/T directly, no GBp conversion, no
    # LSE-close gap during US/Asia sessions).
    from feeds.tradingeconomics.spot import TE_NICKEL
    for label, key in (("NICKEL_TE", TE_NICKEL), ("LITHIUM_TE", TE_LITHIUM), ("COBALT_TE", TE_COBALT)):
        if label in te_overrides:
            v = float(te_overrides[label])
            prices[label] = v
            notes[label] = f"operator override (bypasses TE drift risk)"
            logger.info(f"  {label} = {v} (operator override)")
            continue
        scraped = get_te_spot(key)
        if scraped is None or scraped <= 0:
            raise RuntimeError(f"TE scrape failed for {label}")
        scraped = float(scraped)
        if prev_te_anchor and label in prev_te_anchor:
            prev = prev_te_anchor[label]
            drift = abs(scraped - prev) / prev
            if drift > te_drift_threshold:
                raise RuntimeError(
                    f"{label}: live TE scrape {scraped} differs from previous "
                    f"anchor {prev} by {drift*100:.2f}% (> {te_drift_threshold*100:.1f}%). "
                    f"This likely means TE has rolled into the next day's value. "
                    f"Re-run with --{label.lower()}={prev_te_anchor[label]:.0f} "
                    f"(operator-confirmed EOD for {settle_date_iso}) or accept-as-is "
                    f"with --te-drift-threshold {drift+0.001:.4f}"
                )
        prices[label] = scraped
        notes[label] = f"live TE scrape at re-anchor time"
        logger.info(f"  {label} = {scraped}")

    return prices, notes


def render_anchor_block(
    settle_date_iso: str,
    event_ticker: str,
    value: float,
    prices: dict[str, float],
    notes: dict[str, str],
) -> str:
    """Compose the replacement DEFAULT_ANCHOR_PLACEHOLDER block."""
    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""DEFAULT_ANCHOR_PLACEHOLDER = TruEvAnchor(
    # **CRITICAL**: anchor MUST be a real (date, published TruEV value,
    # same-day component closes) triple. Truflation publishes the
    # index ONCE per day at end-of-day; an RMSE-minimizing fit across
    # multiple days is NOT a valid anchor — it produces an inflated
    # base value that biases today's reconstructed index above truth.
    #
    # Auto-rewritten by deploy/truev_wait_and_reanchor.py
    # source event: {event_ticker} (Kalshi expiration_value)
    # rewrite UTC : {utc_now}
    anchor_date="{settle_date_iso}",
    anchor_index_value={value:.4f},  # Kalshi-settled value for {settle_date_iso}
    anchor_prices={{
        "HG=F": {prices['HG=F']!r},          # {notes['HG=F']}
        "LITHIUM_TE": {prices['LITHIUM_TE']!r},  # {notes['LITHIUM_TE']}
        "NICKEL_TE": {prices['NICKEL_TE']!r},  # {notes['NICKEL_TE']}
        "COBALT_TE": {prices['COBALT_TE']!r},   # {notes['COBALT_TE']}
        "PA=F": {prices['PA=F']!r},        # {notes['PA=F']}
        "PL=F": {prices['PL=F']!r},        # {notes['PL=F']}
    }},
)"""


def update_anchor_file(
    settle_date_iso: str,
    event_ticker: str,
    value: float,
    prices: dict[str, float],
    notes: dict[str, str],
    logger: logging.Logger,
) -> None:
    text = TRUEV_INDEX_PY.read_text()
    m = ANCHOR_BLOCK_RE.search(text)
    if not m:
        raise RuntimeError("Could not locate DEFAULT_ANCHOR_PLACEHOLDER block in _truev_index.py")

    new_block = render_anchor_block(settle_date_iso, event_ticker, value, prices, notes)
    new_text = text[: m.start()] + new_block + text[m.end():]

    backup = TRUEV_INDEX_PY.with_suffix(TRUEV_INDEX_PY.suffix + f".bak.{int(time.time())}")
    shutil.copy2(TRUEV_INDEX_PY, backup)
    logger.info(f"backup: {backup}")

    TRUEV_INDEX_PY.write_text(new_text)
    logger.info(f"wrote {TRUEV_INDEX_PY}")

    # Validate via subprocess (clean import).
    check = subprocess.run(
        [
            sys.executable, "-c",
            "from lipmm.theo.providers._truev_index import DEFAULT_ANCHOR_PLACEHOLDER as a;"
            "print(a.anchor_date, a.anchor_index_value, len(a.anchor_prices))",
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if check.returncode != 0:
        logger.error(f"VALIDATION FAILED — restoring backup\n{check.stderr}")
        shutil.copy2(backup, TRUEV_INDEX_PY)
        raise RuntimeError("anchor write failed validation; restored from backup")
    logger.info(f"validation OK: {check.stdout.strip()}")


async def main_async(args: argparse.Namespace) -> int:
    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"truev_autoanchor_{ts}.log"
    logger = setup_logger(log_path)
    logger.info(f"starting; log: {log_path}")

    event = args.event
    if not event:
        async with httpx.AsyncClient(timeout=15) as client:
            event = await auto_detect_pending(client, logger)
        if not event:
            logger.error("no pending KXTRUEV event found (all recent events already settled)")
            return 1
        logger.info(f"auto-detected pending event: {event}")
    else:
        logger.info(f"using event: {event}")

    settle_date_iso = event_ticker_to_iso_date(event)
    logger.info(f"settle date (ISO): {settle_date_iso}")
    logger.info(f"poll interval: {args.poll_seconds:.0f}s")

    value = await poll_for_settlement(event, args.poll_seconds, logger)
    logger.info(f"SETTLED: {event} expiration_value = {value}")

    # Pull the EXISTING anchor's TE values so we can drift-check the new scrape.
    from lipmm.theo.providers._truev_index import DEFAULT_ANCHOR_PLACEHOLDER as prev_anchor
    prev_te = {
        "LITHIUM_TE": prev_anchor.anchor_prices.get("LITHIUM_TE"),
        "COBALT_TE":  prev_anchor.anchor_prices.get("COBALT_TE"),
        "NICKEL_TE":  prev_anchor.anchor_prices.get("NICKEL_TE"),
    }
    prev_te = {k: v for k, v in prev_te.items() if v is not None}

    te_overrides: dict[str, float] = {}
    if args.lithium_te is not None:
        te_overrides["LITHIUM_TE"] = args.lithium_te
    if args.cobalt_te is not None:
        te_overrides["COBALT_TE"] = args.cobalt_te
    if args.nickel_te is not None:
        te_overrides["NICKEL_TE"] = args.nickel_te

    logger.info("fetching same-day component closes...")
    try:
        prices, notes = pull_component_prices(
            settle_date_iso, logger,
            te_overrides=te_overrides,
            prev_te_anchor=prev_te,
            te_drift_threshold=args.te_drift_threshold,
        )
    except RuntimeError as exc:
        logger.error(f"FAILED: {exc}")
        logger.error("Anchor file NOT modified. Supply --lithium-te / --cobalt-te and re-run.")
        return 3

    logger.info("rewriting anchor file...")
    update_anchor_file(settle_date_iso, event, value, prices, notes, logger)

    logger.info(f"DONE. anchor now: date={settle_date_iso}  value={value}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--event", default=None,
        help="KXTRUEV event ticker (e.g. KXTRUEV-26MAY11); auto-detect pending if omitted",
    )
    p.add_argument(
        "--poll-seconds", type=float, default=300.0,
        help="seconds between Kalshi polls (default 300 = 5 min)",
    )
    p.add_argument(
        "--lithium-te", type=float, default=None,
        help="operator-confirmed EOD LITHIUM_TE value (bypasses live TE scrape — use when TE has rolled into next-day's value)",
    )
    p.add_argument(
        "--cobalt-te", type=float, default=None,
        help="operator-confirmed EOD COBALT_TE value (bypasses live TE scrape)",
    )
    p.add_argument(
        "--nickel-te", type=float, default=None,
        help="operator-confirmed EOD NICKEL_TE value (bypasses live TE scrape)",
    )
    p.add_argument(
        "--te-drift-threshold", type=float, default=0.01,
        help="max relative drift between live TE scrape and previous anchor before requiring operator override (default 0.01 = 1 pct)",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
