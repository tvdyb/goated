"""Structured decision logging — JSONL append-only recorder.

Lifted from the soy-bot's `engine/decision_logger.py`. Mechanics unchanged:
daily UTC rotation, sub-rotation at MAX_FILE_BYTES, throttled fsync,
depth trim helper. Only difference is the SCHEMA_VERSION is namespaced
("lipmm-1.0" not "1.0") so lipmm-emitted logs are distinguishable from
the legacy soy-bot's logs.

Format choice: JSONL (one JSON object per line) over CSV. Reasoning:
  - CSV forces a flat schema; nested fields (orderbook depth, theo extras)
    don't fit cleanly.
  - JSONL handles arbitrary nesting, is greppable, parses with
    pandas.read_json(..., lines=True).
  - Self-contained records mean an LLM agent can read any single line and
    reason about that decision without column-meaning context.

Rotation:
  - Daily rotation by UTC date (settlement boundaries are UTC-aligned for
    most exchanges; using local-time would create analysis headaches).
  - Sub-rotation: when a daily file exceeds MAX_FILE_BYTES, append .NN
    suffix and start a new file.

Performance:
  - fsync() is called at most once per second (FSYNC_INTERVAL_S). Between
    fsyncs the OS write buffer absorbs writes.
  - Writes are sync-buffered in Python (line-buffered). At ~20 records/sec
    the cost is ~30µs per record — not a hot-path concern.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Schema namespace. Bump when schema fields are added/removed/renamed.
# Namespacing with "lipmm-" lets analyst tools distinguish records emitted
# by the lipmm framework from any legacy soy-bot logs.
SCHEMA_VERSION = "lipmm-1.1"  # bumped to 1.1 when "risk" top-level key was added

# Rotate to a new file when the current daily file exceeds this many bytes.
# At ~1.5KB per record × 20 records/sec, hits 500MB after ~4.6 hours.
MAX_FILE_BYTES = 500 * 1024 * 1024

# fsync at most this often (seconds). OS buffers absorb writes between syncs.
FSYNC_INTERVAL_S = 1.0

# Cap orderbook depth in records to keep size bounded. Top N levels per side.
DEPTH_TRIM_LEVELS = 10


def _utc_iso(ts: float | None = None) -> str:
    """Return ISO8601 UTC timestamp with millisecond precision."""
    if ts is None:
        ts = time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # Format: 2026-04-30T19:23:45.123Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}Z"


def _utc_date_str(ts: float | None = None) -> str:
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def trim_depth(depth: list[tuple[int, float]] | list[list]) -> list[list]:
    """Trim depth to top N levels and convert tuples to lists for JSON."""
    if not depth:
        return []
    out: list[list] = []
    for entry in depth[:DEPTH_TRIM_LEVELS]:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            out.append([int(entry[0]), float(entry[1])])
    return out


class DecisionLogger:
    """Append-only JSONL logger for trading decisions.

    Thread-safe: writes are serialized through a lock. The bot's main loop
    is single-threaded asyncio so contention is rare; the lock guards
    against any future thread sharing the logger (e.g., a sidecar dashboard).
    """

    def __init__(self, log_dir: str = "logs/decisions") -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh: Any | None = None
        self._cur_date: str = ""
        self._cur_path: Path | None = None
        self._last_fsync: float = 0.0
        self._closed = False

    def _open_today(self, ts: float) -> None:
        """(Re)open the file for today, with sub-rotation if oversize."""
        date_str = _utc_date_str(ts)
        idx = 0
        while True:
            if idx == 0:
                path = self._log_dir / f"decisions_{date_str}.jsonl"
            else:
                path = self._log_dir / f"decisions_{date_str}.{idx:02d}.jsonl"
            if not path.exists() or path.stat().st_size < MAX_FILE_BYTES:
                break
            idx += 1
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
        self._fh = open(path, "a", buffering=1, encoding="utf-8")
        self._cur_date = date_str
        self._cur_path = path
        self._last_fsync = time.time()

    def _ensure_open(self, ts: float) -> None:
        date_str = _utc_date_str(ts)
        if self._fh is None or self._cur_date != date_str:
            self._open_today(ts)
        elif self._cur_path is not None and self._cur_path.exists():
            try:
                if self._cur_path.stat().st_size >= MAX_FILE_BYTES:
                    self._open_today(ts)
            except OSError:
                pass

    def log(self, record: dict[str, Any]) -> None:
        """Append one record to today's JSONL file.

        Always sets schema_version. Always succeeds (errors logged, not
        raised) so a logging failure can never crash the trading loop.
        """
        if self._closed:
            return
        try:
            record.setdefault("schema_version", SCHEMA_VERSION)
            record.setdefault("timestamp_utc", _utc_iso())
            # default=str is the safety net: any non-JSON-serializable value
            # (datetime, Decimal, numpy.float64, custom classes) gets
            # stringified rather than raising. The trading loop must never
            # be brought down by a logging serialization error.
            line = json.dumps(record, default=str, separators=(",", ":")) + "\n"
            with self._lock:
                self._ensure_open(time.time())
                if self._fh is None:
                    return
                self._fh.write(line)
                # Throttled fsync: at most once per second.
                now = time.time()
                if now - self._last_fsync >= FSYNC_INTERVAL_S:
                    try:
                        self._fh.flush()
                        os.fsync(self._fh.fileno())
                    except OSError:
                        pass
                    self._last_fsync = now
        except Exception as exc:
            logger.warning("DECISION_LOG: write failed: %s", exc)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._fh is not None:
                try:
                    self._fh.flush()
                    os.fsync(self._fh.fileno())
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
