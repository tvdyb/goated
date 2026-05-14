"""BasketSnapshotLogger — daemonized per-N-minute writer of the TruEV
basket reconstruction.

TradingEconomics scrapes (LITHIUM_TE, COBALT_TE, NICKEL_TE) expose only
*current* spot — no historicals. That means when we re-anchor in the
morning, we have no way to verify "what did our basket think the
basket was at 23:59 UTC last night?" or "what was LITHIUM_TE at the
EOD print window?"

This logger fixes that. It runs alongside the bot, samples the
TruEvForwardSource cache every N minutes (default 15), reconstructs
the basket via `reconstruct_index`, and appends one JSONL line per
sample to a daily-rotated file under `<log_dir>/basket_snapshots/`.

Each line shape:

    {
      "ts": 1715642400.12,
      "iso": "2026-05-14T22:30:00Z",
      "anchor_date": "2026-05-13",
      "anchor_value": 1316.85,
      "implied_basket": 1311.02,
      "components": {
        "HG=F":       {"price": 6.5765, "age_s": 12.3},
        "NICKEL_TE":  {"price": 18881.0, "age_s": 47.1},
        ...
      }
    }

Operator can query later with `jq` / a small inspector script — no
external dependencies needed for the writer itself.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from feeds.truflation.forward import TruEvForwardSource
    from lipmm.theo.providers._truev_index import TruEvAnchor, TruEvWeights

logger = logging.getLogger(__name__)


class BasketSnapshotLogger:
    """Periodic writer of basket snapshots for retrospective anchoring."""

    def __init__(
        self,
        *,
        forward: "TruEvForwardSource",
        weights: "TruEvWeights",
        anchor: "TruEvAnchor",
        log_dir: Path,
        interval_s: float = 900.0,
    ) -> None:
        self._forward = forward
        self._weights = weights
        self._anchor = anchor
        self._dir = Path(log_dir) / "basket_snapshots"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._interval_s = float(interval_s)
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Spawn the background loop. Writes one snapshot immediately
        so the log isn't empty for the first interval."""
        if self._running:
            return
        self._running = True
        self._capture()  # immediate first sample
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "BasketSnapshotLogger started (interval=%.0fs, dir=%s)",
            self._interval_s, self._dir,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.info("BasketSnapshotLogger task ended: %s", exc)
            self._task = None

    async def _loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval_s)
                if not self._running:
                    break
                try:
                    self._capture()
                except Exception as exc:
                    logger.warning("snapshot capture failed: %s", exc)
        except asyncio.CancelledError:
            raise

    def _capture(self) -> None:
        """Read the forward cache + compute basket + append a JSONL row."""
        from lipmm.theo.providers._truev_index import reconstruct_index

        now = time.time()
        prices_ts = self._forward.latest_prices()
        components: dict[str, dict[str, float]] = {}
        for sym, (price, fetched_at) in prices_ts.items():
            components[sym] = {
                "price": float(price),
                "age_s": round(now - fetched_at, 1),
            }

        # Implied basket: only when all modeled symbols are present
        modeled = set(self._weights.weights.keys())
        present = set(prices_ts.keys())
        implied: float | None = None
        if modeled.issubset(present):
            try:
                current = {sym: prices_ts[sym][0] for sym in modeled}
                implied = float(reconstruct_index(
                    current, self._weights, self._anchor,
                ))
            except Exception as exc:
                logger.warning("reconstruct_index failed: %s", exc)

        record: dict[str, Any] = {
            "ts": round(now, 2),
            "iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "anchor_date": self._anchor.anchor_date,
            "anchor_value": float(self._anchor.anchor_index_value),
            "implied_basket": implied,
            "components": components,
        }

        # Daily-rotated file: snapshots_YYYY-MM-DD.jsonl (UTC date).
        utc_date = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
        out_path = self._dir / f"snapshots_{utc_date}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
