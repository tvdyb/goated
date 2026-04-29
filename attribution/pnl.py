"""PnL attribution for live trading.

Tracks per-fill entry data and computes attribution categories:
- spread_capture: half-spread earned on maker fills
- adverse_selection: markout loss (model fair moved against us)
- hedge_slippage: cost of IB hedge vs model delta
- kalshi_fees: maker fees on Kalshi fills
- ib_fees: IB commissions + slippage

Hourly aggregation. CSV output for first deployment (lightweight).

Non-negotiables: no pandas, fail-loud, type hints.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from state.positions import PositionStore

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path("output/pnl")


@dataclass(frozen=True, slots=True)
class FillRecord:
    """A single fill for PnL tracking."""

    timestamp: float
    market_ticker: str
    side: str
    action: str
    count: int
    price_cents: int
    fill_id: str
    model_fair_cents: int = 0
    kalshi_mid_cents: int = 0


@dataclass(slots=True)
class HourlyBucket:
    """Aggregated PnL for one hour."""

    hour_start: float = 0.0
    spread_capture_cents: int = 0
    adverse_selection_cents: int = 0
    hedge_slippage_cents: int = 0
    kalshi_fees_cents: int = 0
    ib_fees_cents: int = 0
    n_fills: int = 0
    n_cycles: int = 0

    @property
    def net_pnl_cents(self) -> int:
        return (
            self.spread_capture_cents
            - self.adverse_selection_cents
            - self.hedge_slippage_cents
            - self.kalshi_fees_cents
            - self.ib_fees_cents
        )


class PnLTracker:
    """Live PnL attribution tracker.

    Records fills, computes attribution, aggregates hourly, writes CSV.
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir or _OUTPUT_DIR
        self._fills: list[FillRecord] = []
        self._hourly: list[HourlyBucket] = []
        self._current_hour: HourlyBucket | None = None
        self._current_hour_start: int = 0

    def record_fill(self, fill: FillRecord) -> None:
        """Record a fill for attribution."""
        self._fills.append(fill)
        bucket = self._get_or_create_bucket(fill.timestamp)
        bucket.n_fills += 1

        # Spread capture estimate: |price - 50| cents per contract
        # (simplified: assumes fair ~= 50 for spread capture accounting)
        if fill.model_fair_cents > 0:
            if fill.action == "buy":
                # Bought at price, fair is model_fair -> capture = fair - price
                capture = (fill.model_fair_cents - fill.price_cents) * fill.count
            else:
                # Sold at price -> capture = price - fair
                capture = (fill.price_cents - fill.model_fair_cents) * fill.count
            bucket.spread_capture_cents += max(0, capture)
            bucket.adverse_selection_cents += max(0, -capture)

        # Kalshi maker fee estimate: ~0.25 * 0.07 * P * (1-P) * count
        p = fill.price_cents / 100.0
        fee_per_contract = max(1, int(0.07 * 0.25 * p * (1 - p) * 100 + 0.999))
        bucket.kalshi_fees_cents += fee_per_contract * fill.count

    def record_hedge(
        self,
        timestamp: float,
        n_contracts: int,
        slippage_cents: int,
        ib_commission_cents: int,
    ) -> None:
        """Record a hedge execution for attribution."""
        bucket = self._get_or_create_bucket(timestamp)
        bucket.hedge_slippage_cents += slippage_cents
        bucket.ib_fees_cents += ib_commission_cents

    def log_cycle(
        self,
        position_store: PositionStore,
        bucket_prices: object | None = None,
        event_ticker: str = "",
    ) -> None:
        """Called each cycle to log state."""
        bucket = self._get_or_create_bucket(time.time())
        bucket.n_cycles += 1

        total_loss = position_store.total_max_loss_cents()
        snap = position_store.snapshot()
        n_positions = sum(1 for p in snap.values() if p.signed_qty != 0)

        logger.info(
            "PNL: max_loss=%dc positions=%d fills_this_hour=%d net_pnl=%dc",
            total_loss,
            n_positions,
            bucket.n_fills,
            bucket.net_pnl_cents,
        )

    def write_summary(self) -> None:
        """Write hourly PnL to CSV."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"pnl_{int(time.time())}.csv"

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "hour_start",
                "spread_capture_cents",
                "adverse_selection_cents",
                "hedge_slippage_cents",
                "kalshi_fees_cents",
                "ib_fees_cents",
                "net_pnl_cents",
                "n_fills",
                "n_cycles",
            ])
            for h in self._hourly:
                writer.writerow([
                    int(h.hour_start),
                    h.spread_capture_cents,
                    h.adverse_selection_cents,
                    h.hedge_slippage_cents,
                    h.kalshi_fees_cents,
                    h.ib_fees_cents,
                    h.net_pnl_cents,
                    h.n_fills,
                    h.n_cycles,
                ])

        logger.info("PNL: wrote summary to %s (%d hours)", path, len(self._hourly))

    def write_fills(self) -> None:
        """Write raw fills to CSV."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"fills_{int(time.time())}.csv"

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "market_ticker",
                "side",
                "action",
                "count",
                "price_cents",
                "fill_id",
                "model_fair_cents",
                "kalshi_mid_cents",
            ])
            for fill in self._fills:
                writer.writerow([
                    fill.timestamp,
                    fill.market_ticker,
                    fill.side,
                    fill.action,
                    fill.count,
                    fill.price_cents,
                    fill.fill_id,
                    fill.model_fair_cents,
                    fill.kalshi_mid_cents,
                ])

        logger.info("PNL: wrote %d fills to %s", len(self._fills), path)

    def get_daily_summary(self) -> dict[str, int]:
        """Get aggregated daily PnL summary."""
        total = HourlyBucket()
        for h in self._hourly:
            total.spread_capture_cents += h.spread_capture_cents
            total.adverse_selection_cents += h.adverse_selection_cents
            total.hedge_slippage_cents += h.hedge_slippage_cents
            total.kalshi_fees_cents += h.kalshi_fees_cents
            total.ib_fees_cents += h.ib_fees_cents
            total.n_fills += h.n_fills
            total.n_cycles += h.n_cycles
        return {
            "spread_capture_cents": total.spread_capture_cents,
            "adverse_selection_cents": total.adverse_selection_cents,
            "hedge_slippage_cents": total.hedge_slippage_cents,
            "kalshi_fees_cents": total.kalshi_fees_cents,
            "ib_fees_cents": total.ib_fees_cents,
            "net_pnl_cents": total.net_pnl_cents,
            "n_fills": total.n_fills,
            "n_cycles": total.n_cycles,
        }

    def _get_or_create_bucket(self, ts: float) -> HourlyBucket:
        """Get or create the hourly bucket for a timestamp."""
        hour_start = int(ts) // 3600 * 3600
        if self._current_hour is not None and self._current_hour_start == hour_start:
            return self._current_hour

        # New hour
        bucket = HourlyBucket(hour_start=float(hour_start))
        self._hourly.append(bucket)
        self._current_hour = bucket
        self._current_hour_start = hour_start
        return bucket
