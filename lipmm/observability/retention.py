"""Disk-budget retention for decision-log files.

A `RetentionManager` periodically:
  1. gzips closed (non-today) `decisions_*.jsonl` files in-place
     (~10–15× compression for typical JSONL),
  2. if total bytes still exceed `max_total_bytes`, deletes oldest
     files first (by mtime) until the directory is back under cap.

It does NOT touch the file the `DecisionLogger` is currently appending
to: today's UTC date is detected by string-match on the filename so the
manager never races the writer's buffered append.

Failure mode: every operation is wrapped — disk full, permission denied,
race with a concurrent process — and produces a one-line WARNING. The
sweep is idempotent (re-running on an already-compressed dir is a no-op
beyond the listing scan), so a transient error self-heals on the next
hourly tick.

The class is `time.time`-injectable (`clock=` kwarg) so tests don't need
to monkeypatch the clock to exercise today/yesterday boundaries.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


# Match decisions_YYYY-MM-DD.jsonl and sub-rotated decisions_YYYY-MM-DD.NN.jsonl
# (and their .gz variants). Anchored to avoid matching arbitrary files in
# the same directory.
_FILE_RE = re.compile(
    r"^decisions_(?P<date>\d{4}-\d{2}-\d{2})(?:\.(?P<sub>\d{2}))?\.jsonl(?:\.gz)?$"
)


@dataclass
class RetentionStats:
    bytes_before: int = 0
    bytes_after: int = 0
    files_seen: int = 0
    files_compressed: int = 0
    files_evicted: int = 0
    bytes_evicted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def bytes_saved(self) -> int:
        return self.bytes_before - self.bytes_after


class RetentionManager:
    """Hourly disk-budget enforcer for the decision-log directory.

    Usage (manual):
        mgr = RetentionManager(Path("logs/decisions"), max_total_bytes=2 * 1024**3)
        await mgr.start()
        ...
        await mgr.stop()

    Usage (one-shot, e.g. tests):
        stats = RetentionManager(d, max_total_bytes=10_000).run_once()
    """

    def __init__(
        self,
        target_dir: str | Path,
        max_total_bytes: int,
        *,
        gzip_closed: bool = True,
        run_interval_s: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_total_bytes <= 0:
            raise ValueError(f"max_total_bytes must be > 0, got {max_total_bytes}")
        if run_interval_s <= 0:
            raise ValueError(f"run_interval_s must be > 0, got {run_interval_s}")
        self._target_dir = Path(target_dir)
        self._max_total_bytes = int(max_total_bytes)
        self._gzip_closed = gzip_closed
        self._run_interval_s = float(run_interval_s)
        self._clock = clock
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    # ── Public API ─────────────────────────────────────────────────

    def run_once(self) -> RetentionStats:
        """One full sweep: compress closed files, then evict oldest until
        under the byte cap. Safe to call repeatedly."""
        stats = RetentionStats()
        if not self._target_dir.exists():
            return stats
        today_str = self._utc_date_str()
        try:
            entries = self._scan(today_str)
        except OSError as exc:
            stats.errors.append(f"scan failed: {exc}")
            return stats
        stats.files_seen = len(entries)
        stats.bytes_before = sum(size for _, _, size, _ in entries)

        if self._gzip_closed:
            entries = self._compress_closed(entries, today_str, stats)

        # Recompute total after compression for eviction decision
        total = sum(size for _, _, size, _ in entries)
        if total > self._max_total_bytes:
            entries = self._evict_oldest(entries, total, stats)

        stats.bytes_after = sum(size for _, _, size, _ in entries)
        return stats

    async def start(self) -> None:
        """Spawn the periodic sweep as a background task. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the background loop. Idempotent."""
        if self._task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._task.cancel()
        except Exception:
            pass
        self._task = None
        self._stop_event = None

    # ── Internal ───────────────────────────────────────────────────

    def _utc_date_str(self) -> str:
        ts = self._clock()
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    def _scan(
        self, today_str: str,
    ) -> list[tuple[Path, float, int, str]]:
        """Return [(path, mtime, size, date_str), ...] for managed files."""
        out: list[tuple[Path, float, int, str]] = []
        for entry in self._target_dir.iterdir():
            if not entry.is_file():
                continue
            m = _FILE_RE.match(entry.name)
            if m is None:
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            out.append((entry, st.st_mtime, st.st_size, m.group("date")))
        # Stable order: by mtime asc, then name asc
        out.sort(key=lambda t: (t[1], t[0].name))
        return out

    def _is_today(self, file_date: str, today_str: str) -> bool:
        return file_date == today_str

    def _compress_closed(
        self,
        entries: list[tuple[Path, float, int, str]],
        today_str: str,
        stats: RetentionStats,
    ) -> list[tuple[Path, float, int, str]]:
        """Gzip every non-today `.jsonl` file in-place. Returns the
        updated entry list reflecting the post-compression filesystem."""
        out: list[tuple[Path, float, int, str]] = []
        for path, mtime, size, date_str in entries:
            if path.suffix == ".gz":
                out.append((path, mtime, size, date_str))
                continue
            if self._is_today(date_str, today_str):
                out.append((path, mtime, size, date_str))
                continue
            try:
                new_path = self._gzip_in_place(path)
                new_st = new_path.stat()
                stats.files_compressed += 1
                out.append((new_path, new_st.st_mtime, new_st.st_size, date_str))
            except Exception as exc:
                stats.errors.append(f"compress {path.name}: {exc}")
                logger.warning("retention: compress %s failed: %s", path.name, exc)
                out.append((path, mtime, size, date_str))
        # Re-sort because mtimes may have shifted
        out.sort(key=lambda t: (t[1], t[0].name))
        return out

    @staticmethod
    def _gzip_in_place(path: Path) -> Path:
        """Compress `path` to `path.gz`, then unlink the original.

        Crash safety: only unlink after the gzip is fully written and
        flushed. A crash between write and unlink leaves both files;
        the next sweep treats the existing `.gz` as already-compressed
        (skipped by the `path.suffix == '.gz'` branch) and the original
        gets re-compressed (overwriting the prior `.gz`) — slightly
        wasteful but correct.
        """
        gz_path = path.with_suffix(path.suffix + ".gz")
        with path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        # gzip.GzipFile.close() flushes; an extra fsync gives crash safety.
        with gz_path.open("rb") as fh:
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        path.unlink()
        return gz_path

    def _evict_oldest(
        self,
        entries: list[tuple[Path, float, int, str]],
        total_bytes: int,
        stats: RetentionStats,
    ) -> list[tuple[Path, float, int, str]]:
        """Delete oldest files (by mtime) until total ≤ cap. Today's
        file is never evicted (we'd lose the live tail)."""
        today_str = self._utc_date_str()
        survivors: list[tuple[Path, float, int, str]] = []
        # Two passes: first identify what to delete, then delete.
        # entries is already sorted oldest→newest.
        running = total_bytes
        marked_dead: set[Path] = set()
        for path, mtime, size, date_str in entries:
            if running <= self._max_total_bytes:
                break
            if self._is_today(date_str, today_str):
                continue  # never evict the live file
            marked_dead.add(path)
            running -= size

        for path, mtime, size, date_str in entries:
            if path in marked_dead:
                try:
                    path.unlink()
                    stats.files_evicted += 1
                    stats.bytes_evicted += size
                except Exception as exc:
                    stats.errors.append(f"evict {path.name}: {exc}")
                    logger.warning("retention: evict %s failed: %s", path.name, exc)
                    survivors.append((path, mtime, size, date_str))
            else:
                survivors.append((path, mtime, size, date_str))
        return survivors

    async def _loop(self) -> None:
        assert self._stop_event is not None
        try:
            while not self._stop_event.is_set():
                try:
                    stats = await asyncio.to_thread(self.run_once)
                    if stats.files_compressed or stats.files_evicted:
                        logger.info(
                            "retention sweep: compressed=%d evicted=%d "
                            "bytes_saved=%d errors=%d",
                            stats.files_compressed, stats.files_evicted,
                            stats.bytes_saved, len(stats.errors),
                        )
                except Exception as exc:
                    logger.warning("retention sweep crashed: %s", exc)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._run_interval_s,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
