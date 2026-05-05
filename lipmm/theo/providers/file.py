"""`FilePollTheoProvider` — load theos from a CSV or JSON file polled on
a schedule.

The simplest "accessible" integration path: any external tool (Python,
R, shell, jq from cron, a notebook) that can write a file can feed
theos to the bot. The provider polls the file every `refresh_s`,
re-parses on change (mtime), and serves the parsed snapshot to the
runner each cycle.

Format auto-detection by extension (.csv vs .json), or pass `format=`
explicitly.

CSV format:

    ticker,yes_cents,confidence,reason
    KXISMPMI-26MAY-50,82,0.85,pmi-bayes-v1
    KXISMPMI-26MAY-51,75,0.80,pmi-bayes-v1

JSON format (either dict or list shape):

    {
      "KXISMPMI-26MAY-50": {"yes_cents": 82, "confidence": 0.85, "reason": "..."},
      ...
    }

    or

    [
      {"ticker": "KXISMPMI-26MAY-50", "yes_cents": 82, "confidence": 0.85},
      ...
    ]

Staleness:
  - default: if the file's mtime is older than 3× refresh_s, returned
    confidence drops to 0.0 for every ticker → strategy skips. This
    prevents the bot from quoting off a frozen model.
  - Pass `staleness_threshold_s=None` to opt out (last-good-forever).
  - Pass an explicit number to override the default multiplier.

Errors are logged at WARNING; the last good snapshot stays valid until
the next successful read.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from lipmm.theo.base import TheoResult

logger = logging.getLogger(__name__)


_DEFAULT_REFRESH_S = 5.0
_DEFAULT_STALENESS_MULT = 3.0


@dataclass(frozen=True)
class _Entry:
    yes_probability: float
    confidence: float
    reason: str


def _parse_csv(text: str) -> dict[str, _Entry]:
    out: dict[str, _Entry] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue
            yes_cents = int(row["yes_cents"])
            confidence = float(row["confidence"])
            reason = (row.get("reason") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("FilePollTheoProvider: skipping bad row %r: %s", row, exc)
            continue
        if not (1 <= yes_cents <= 99):
            logger.warning(
                "FilePollTheoProvider: yes_cents=%s out of [1,99] for %s; skip",
                yes_cents, ticker,
            )
            continue
        if not (0.0 <= confidence <= 1.0):
            logger.warning(
                "FilePollTheoProvider: confidence=%s out of [0,1] for %s; skip",
                confidence, ticker,
            )
            continue
        out[ticker] = _Entry(
            yes_probability=yes_cents / 100.0,
            confidence=confidence, reason=reason,
        )
    return out


def _parse_json(text: str) -> dict[str, _Entry]:
    out: dict[str, _Entry] = {}
    data = json.loads(text)
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = (
            (entry.get("ticker", ""), entry)
            for entry in data
            if isinstance(entry, dict)
        )
    else:
        raise ValueError(f"unexpected JSON top-level type: {type(data).__name__}")
    for ticker, entry in items:
        ticker = (ticker or "").strip()
        if not ticker or not isinstance(entry, dict):
            continue
        try:
            yes_cents = int(entry["yes_cents"])
            confidence = float(entry["confidence"])
            reason = str(entry.get("reason", "")).strip()
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "FilePollTheoProvider: skipping bad entry %r: %s", entry, exc,
            )
            continue
        if not (1 <= yes_cents <= 99) or not (0.0 <= confidence <= 1.0):
            logger.warning(
                "FilePollTheoProvider: out-of-range fields for %s; skip", ticker,
            )
            continue
        out[ticker] = _Entry(
            yes_probability=yes_cents / 100.0,
            confidence=confidence, reason=reason,
        )
    return out


class FilePollTheoProvider:
    """TheoProvider that loads theos from a polled CSV/JSON file.

    Args:
      path: file to watch.
      series_prefix: registry routing key. Pass '*' to serve all events.
      refresh_s: poll interval. Default 5s.
      format: 'csv', 'json', or 'auto' (default — by file extension).
      staleness_threshold_s: above this age (file unchanged), confidence
        drops to 0. Default 3× refresh_s. Pass None to disable.
      source: identifying string baked into TheoResult.source.
    """

    def __init__(
        self,
        path: str,
        *,
        series_prefix: str,
        refresh_s: float = _DEFAULT_REFRESH_S,
        format: Literal["csv", "json", "auto"] = "auto",
        staleness_threshold_s: float | None = -1.0,
        source: str = "file-poll",
    ) -> None:
        if not series_prefix:
            raise ValueError("series_prefix required (use '*' for wildcard)")
        if refresh_s <= 0:
            raise ValueError(f"refresh_s must be > 0, got {refresh_s}")
        self.series_prefix = series_prefix
        self._path = path
        self._refresh_s = float(refresh_s)
        self._format = format
        # Sentinel -1.0 → "use default"; allows None to mean "disable".
        if staleness_threshold_s == -1.0:
            self._staleness_threshold_s: float | None = (
                _DEFAULT_STALENESS_MULT * self._refresh_s
            )
        else:
            self._staleness_threshold_s = staleness_threshold_s
        self._source = source

        self._snapshot: dict[str, _Entry] = {}
        self._snapshot_mtime: float = 0.0
        self._snapshot_loaded_at: float = 0.0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ── TheoProvider protocol ──────────────────────────────────────

    async def warmup(self) -> None:
        # Initial load synchronously so the first cycle has data.
        await self._reload_if_changed()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._poll_loop())

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def theo(self, ticker: str) -> TheoResult:
        now = time.time()
        entry = self._snapshot.get(ticker)
        if entry is None:
            return TheoResult(
                yes_probability=0.5, confidence=0.0,
                computed_at=now, source=f"{self._source}:no-row",
                extras={"path": self._path, "ticker": ticker},
            )
        if self._is_stale(now):
            return TheoResult(
                yes_probability=entry.yes_probability,
                confidence=0.0,
                computed_at=now, source=f"{self._source}:stale",
                extras={
                    "path": self._path,
                    "snapshot_age_s": now - self._snapshot_loaded_at,
                    "stored_confidence": entry.confidence,
                },
            )
        return TheoResult(
            yes_probability=entry.yes_probability,
            confidence=entry.confidence,
            computed_at=self._snapshot_loaded_at,
            source=self._source,
            extras={"path": self._path, "reason": entry.reason},
        )

    # ── internals ──────────────────────────────────────────────────

    def _is_stale(self, now: float) -> bool:
        if self._staleness_threshold_s is None:
            return False
        if self._snapshot_loaded_at == 0.0:
            return True
        return (now - self._snapshot_loaded_at) > self._staleness_threshold_s

    def _resolve_format(self) -> str:
        if self._format != "auto":
            return self._format
        ext = os.path.splitext(self._path)[1].lower()
        return "json" if ext == ".json" else "csv"

    async def _poll_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self._refresh_s,
                    )
                    return  # stop fired
                except asyncio.TimeoutError:
                    pass
                await self._reload_if_changed()
        except asyncio.CancelledError:
            return

    async def _reload_if_changed(self) -> None:
        try:
            stat = os.stat(self._path)
        except FileNotFoundError:
            logger.warning("FilePollTheoProvider: %s not found", self._path)
            return
        except OSError as exc:
            logger.warning("FilePollTheoProvider: stat(%s) failed: %s", self._path, exc)
            return
        if stat.st_mtime <= self._snapshot_mtime:
            return  # no change since last load
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            logger.warning("FilePollTheoProvider: read %s failed: %s", self._path, exc)
            return
        fmt = self._resolve_format()
        try:
            if fmt == "json":
                snapshot = _parse_json(text)
            else:
                snapshot = _parse_csv(text)
        except Exception as exc:
            logger.warning(
                "FilePollTheoProvider: parse %s failed: %s — keeping last good snapshot",
                self._path, exc,
            )
            return
        self._snapshot = snapshot
        self._snapshot_mtime = stat.st_mtime
        self._snapshot_loaded_at = time.time()
        logger.info(
            "FilePollTheoProvider: loaded %d entries from %s",
            len(snapshot), self._path,
        )
