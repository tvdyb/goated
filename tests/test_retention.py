"""Tests for the disk-budget retention manager."""

from __future__ import annotations

import asyncio
import gzip
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lipmm.observability import RetentionManager, RetentionStats


# ── Helpers ─────────────────────────────────────────────────────────


def _make_log(dir_: Path, name: str, body: str = "{\"x\":1}\n", repeats: int = 1) -> Path:
    p = dir_ / name
    p.write_text(body * repeats, encoding="utf-8")
    return p


def _fixed_clock_for(date_str: str) -> "callable":
    """Return a clock that maps to UTC midnight of `date_str` (so the
    manager treats `date_str` as 'today')."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts = dt.timestamp()
    return lambda: ts


# ── Constructor validation ─────────────────────────────────────────


def test_init_rejects_nonpositive_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_total_bytes"):
        RetentionManager(tmp_path, max_total_bytes=0)


def test_init_rejects_nonpositive_interval(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_interval_s"):
        RetentionManager(tmp_path, max_total_bytes=1024, run_interval_s=0)


def test_run_once_on_missing_dir_returns_empty(tmp_path: Path) -> None:
    mgr = RetentionManager(tmp_path / "does-not-exist", max_total_bytes=1024)
    stats = mgr.run_once()
    assert stats.files_seen == 0
    assert stats.bytes_before == 0


# ── Compression ─────────────────────────────────────────────────────


def test_compresses_closed_file(tmp_path: Path) -> None:
    _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=500)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    assert stats.files_compressed == 1
    assert not (tmp_path / "decisions_2026-04-01.jsonl").exists()
    assert (tmp_path / "decisions_2026-04-01.jsonl.gz").exists()


def test_today_file_is_never_compressed(tmp_path: Path) -> None:
    _make_log(tmp_path, "decisions_2026-04-30.jsonl", repeats=500)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    assert stats.files_compressed == 0
    assert (tmp_path / "decisions_2026-04-30.jsonl").exists()


def test_today_subrotated_file_is_never_compressed(tmp_path: Path) -> None:
    """Sub-rotated files for today (e.g. .01.jsonl) are still considered
    today's and skipped — the logger may rotate to them under load."""
    _make_log(tmp_path, "decisions_2026-04-30.01.jsonl", repeats=500)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    assert stats.files_compressed == 0
    assert (tmp_path / "decisions_2026-04-30.01.jsonl").exists()


def test_already_gzipped_file_is_not_recompressed(tmp_path: Path) -> None:
    """Idempotency: a .jsonl.gz file is left alone."""
    src = _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=10)
    # Pre-compress
    gz = tmp_path / "decisions_2026-04-01.jsonl.gz"
    with src.open("rb") as r, gzip.open(gz, "wb") as w:
        w.write(r.read())
    src.unlink()
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    assert stats.files_compressed == 0
    assert gz.exists()


def test_gzip_disabled_keeps_jsonl_intact(tmp_path: Path) -> None:
    p = _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=500)
    mgr = RetentionManager(
        tmp_path, max_total_bytes=10**9,
        gzip_closed=False, clock=_fixed_clock_for("2026-04-30"),
    )
    stats = mgr.run_once()
    assert stats.files_compressed == 0
    assert p.exists()


def test_compression_actually_shrinks_bytes(tmp_path: Path) -> None:
    """JSONL is highly compressible — verify the manager records a
    non-trivial bytes_saved."""
    _make_log(tmp_path, "decisions_2026-04-01.jsonl",
              body='{"ticker":"KX-T123","theo":0.42,"side":"bid"}\n',
              repeats=5000)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    # Highly compressible repeating JSONL → expect at least 5x ratio
    assert stats.bytes_after < stats.bytes_before / 5


# ── Eviction ────────────────────────────────────────────────────────


def test_evicts_oldest_until_under_cap(tmp_path: Path) -> None:
    # Three files, ~1000 bytes each. Cap is 1500 → only newest survives.
    p1 = _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=100)  # ~700b
    p2 = _make_log(tmp_path, "decisions_2026-04-02.jsonl", repeats=100)
    p3 = _make_log(tmp_path, "decisions_2026-04-03.jsonl", repeats=100)
    # mtime tweaks so order is unambiguous
    os.utime(p1, (1000, 1000))
    os.utime(p2, (2000, 2000))
    os.utime(p3, (3000, 3000))
    clock = _fixed_clock_for("2026-04-30")
    # Disable compression to make byte math obvious
    mgr = RetentionManager(
        tmp_path, max_total_bytes=900, gzip_closed=False, clock=clock,
    )
    stats = mgr.run_once()
    assert stats.files_evicted >= 1
    assert not p1.exists()  # oldest gone
    assert p3.exists()      # newest survives


def test_today_file_never_evicted_even_when_oversize(tmp_path: Path) -> None:
    """If today's file alone exceeds the cap, it stays — eviction only
    operates on closed files."""
    p_today = _make_log(tmp_path, "decisions_2026-04-30.jsonl", repeats=10000)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(
        tmp_path, max_total_bytes=100, gzip_closed=False, clock=clock,
    )
    stats = mgr.run_once()
    assert p_today.exists()
    assert stats.files_evicted == 0


def test_eviction_after_compression(tmp_path: Path) -> None:
    """Compression should run first; if still over cap, evict oldest."""
    _make_log(tmp_path, "decisions_2026-04-01.jsonl",
              body='{"a":"b"}\n' * 10, repeats=100)
    _make_log(tmp_path, "decisions_2026-04-02.jsonl",
              body='{"a":"b"}\n' * 10, repeats=100)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=200, clock=clock)
    stats = mgr.run_once()
    # Files were compressed first
    assert stats.files_compressed == 2
    # Total may still exceed 200B → at least one evicted
    assert stats.bytes_after <= stats.bytes_before
    survivors = sorted(p.name for p in tmp_path.iterdir())
    assert "decisions_2026-04-02.jsonl.gz" in survivors  # newer wins ties


# ── Stats reporting ─────────────────────────────────────────────────


def test_stats_track_bytes_saved(tmp_path: Path) -> None:
    _make_log(tmp_path, "decisions_2026-04-01.jsonl",
              body='{"key":"val"}\n', repeats=2000)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)
    stats = mgr.run_once()
    assert stats.bytes_before > 0
    assert stats.bytes_saved > 0
    assert stats.bytes_after == stats.bytes_before - stats.bytes_saved


def test_stats_records_errors_for_unwritable(tmp_path: Path, monkeypatch) -> None:
    """If the gzip step blows up, the error is captured but the sweep
    proceeds without raising."""
    p = _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=10)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10**9, clock=clock)

    def _boom(_path: Path) -> Path:
        raise OSError("simulated disk error")

    monkeypatch.setattr(mgr, "_gzip_in_place", staticmethod(_boom))
    stats = mgr.run_once()
    assert stats.files_compressed == 0
    assert any("compress" in e for e in stats.errors)
    # Original file still present after failure
    assert p.exists()


# ── Glob safety ─────────────────────────────────────────────────────


def test_unrelated_files_are_left_alone(tmp_path: Path) -> None:
    """The manager must not touch files that don't match the pattern."""
    keep = tmp_path / "README.md"
    keep.write_text("hi")
    weird = tmp_path / "audit.csv"
    weird.write_text("a,b\n1,2\n")
    _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=10)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(tmp_path, max_total_bytes=10, clock=clock)
    mgr.run_once()
    assert keep.exists()
    assert weird.exists()


# ── Async lifecycle ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_stop_idempotent(tmp_path: Path) -> None:
    mgr = RetentionManager(tmp_path, max_total_bytes=1024, run_interval_s=10.0)
    await mgr.start()
    await mgr.start()  # second call no-op
    await mgr.stop()
    await mgr.stop()  # idempotent


@pytest.mark.asyncio
async def test_background_loop_runs_at_least_once(tmp_path: Path) -> None:
    """With a tiny run_interval_s, the background loop should sweep at
    least once before stop()."""
    _make_log(tmp_path, "decisions_2026-04-01.jsonl", repeats=200)
    clock = _fixed_clock_for("2026-04-30")
    mgr = RetentionManager(
        tmp_path, max_total_bytes=10**9,
        run_interval_s=0.05, clock=clock,
    )
    await mgr.start()
    # Wait long enough for one sweep to fire and complete
    await asyncio.sleep(0.15)
    await mgr.stop()
    # File should be compressed
    assert (tmp_path / "decisions_2026-04-01.jsonl.gz").exists()
