"""Entry point: python -m feeds.kalshi.capture

Runs the KXSOYBEANW REST polling sentinel until SIGINT/SIGTERM.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from feeds.kalshi.capture import run_sentinel


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi KXSOYBEANW REST capture sentinel")
    parser.add_argument("--db-path", default="data/capture/kalshi_capture.duckdb",
                        help="DuckDB database path (default: data/capture/kalshi_capture.duckdb)")
    parser.add_argument("--ob-interval", type=float, default=60.0,
                        help="Orderbook/trades polling interval in seconds (default: 60)")
    parser.add_argument("--event-interval", type=float, default=300.0,
                        help="Event refresh interval in seconds (default: 300)")
    parser.add_argument("--series-ticker", default="KXSOYBEANW",
                        help="Series ticker to capture (default: KXSOYBEANW)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    asyncio.run(
        run_sentinel(
            db_path=args.db_path,
            ob_interval_s=args.ob_interval,
            event_interval_s=args.event_interval,
            series_ticker=args.series_ticker,
        )
    )


if __name__ == "__main__":
    main()
