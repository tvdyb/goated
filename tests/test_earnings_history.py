"""Tests for EarningsHistory — persistent samples + $/hr histogram."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from lipmm.observability.earnings_history import EarningsHistory


def _tmp_history(tmp_path) -> EarningsHistory:
    return EarningsHistory(
        history_path=str(tmp_path / "earnings.jsonl"),
        sample_interval_s=0.0,  # disable rate-limiting for tests
    )


# ── record() basic semantics ────────────────────────────────────────


def test_record_writes_jsonl_line(tmp_path) -> None:
    eh = _tmp_history(tmp_path)
    ok = eh.record(total_dollars=1.5, elapsed_s=300.0, now_ts=1000.0)
    assert ok is True
    with open(eh.path) as f:
        line = f.readline().strip()
    obj = json.loads(line)
    assert obj["total_dollars"] == 1.5
    assert obj["elapsed_s"] == 300.0
    assert obj["ts"] == 1000.0


def test_record_rate_limited(tmp_path) -> None:
    eh = EarningsHistory(
        history_path=str(tmp_path / "rl.jsonl"),
        sample_interval_s=60.0,
    )
    assert eh.record(1.0, 60.0, now_ts=1000.0) is True
    # Within the interval → skipped
    assert eh.record(2.0, 120.0, now_ts=1059.0) is False
    # After the interval → accepted
    assert eh.record(2.0, 120.0, now_ts=1061.0) is True


def test_record_rejects_negative_inputs(tmp_path) -> None:
    eh = _tmp_history(tmp_path)
    assert eh.record(-1.0, 60.0, now_ts=1000.0) is False
    assert eh.record(1.0, -1.0, now_ts=1001.0) is False


# ── histogram() aggregation ─────────────────────────────────────────


def test_histogram_empty_when_no_samples(tmp_path) -> None:
    eh = _tmp_history(tmp_path)
    stats = eh.histogram()
    assert stats.n_samples == 0
    assert stats.cumulative_dollars == 0.0
    assert stats.elapsed_s == 0.0
    assert stats.avg_dollars_per_hour == 0.0
    assert all(c == 0 for (_lo, _hi, c) in stats.bins)


def test_histogram_two_sample_rate(tmp_path) -> None:
    """Two samples 1 hour apart with $1 delta → 1 $/hr."""
    eh = _tmp_history(tmp_path)
    eh.record(0.0, 0.0, now_ts=1000.0)
    eh.record(1.0, 3600.0, now_ts=1000.0 + 3600.0)
    stats = eh.histogram()
    assert stats.n_samples == 2
    assert stats.cumulative_dollars == pytest.approx(1.0)
    assert stats.avg_dollars_per_hour == pytest.approx(1.0)
    assert stats.peak_dollars_per_hour == pytest.approx(1.0)


def test_histogram_handles_restart_via_negative_delta(tmp_path) -> None:
    """A drop in total_dollars (bot restart) skips that window — no
    negative rate, no overcounted samples."""
    eh = _tmp_history(tmp_path)
    eh.record(2.0, 7200.0, now_ts=1000.0)        # accumulated $2 after 2h
    eh.record(0.5, 1800.0, now_ts=2000.0)        # restart: down to $0.5
    eh.record(1.0, 3600.0, now_ts=5600.0)        # then 1h passes
    stats = eh.histogram()
    # Two windows, but the restart window dropped → only one rate counted
    assert stats.n_samples == 3
    # The good window: 1.0 - 0.5 = 0.5 $ over 3600s = 0.5 $/hr
    assert stats.peak_dollars_per_hour == pytest.approx(0.5)
    assert stats.avg_dollars_per_hour == pytest.approx(0.5)


def test_histogram_bins_distribution(tmp_path) -> None:
    """Three windows landing in different bins."""
    eh = _tmp_history(tmp_path)
    # Window 1: 0.04 $/hr (in [0, 0.05) bin)
    eh.record(0.0, 0.0, now_ts=1000.0)
    eh.record(0.04, 3600.0, now_ts=1000.0 + 3600.0)
    # Window 2: 1.5 $/hr (in [1.00, 2.00) bin)
    eh.record(1.04 + 0.5, 3600.0 * 2, now_ts=1000.0 + 3600.0 * 2)
    # Window 3: 6 $/hr (in [4.00, 8.00) bin)
    eh.record(1.04 + 0.5 + 6.0, 3600.0 * 3, now_ts=1000.0 + 3600.0 * 3)
    stats = eh.histogram()
    # Sum of bin counts == n_windows == n_samples - 1 = 3
    total = sum(c for (_lo, _hi, c) in stats.bins)
    assert total == 3


def test_histogram_handles_malformed_lines(tmp_path) -> None:
    """Garbage lines are silently skipped."""
    path = str(tmp_path / "bad.jsonl")
    with open(path, "w") as f:
        f.write("not json\n")
        f.write('{"ts": 1000, "total_dollars": 0, "elapsed_s": 0}\n')
        f.write('{"missing_fields": true}\n')
        f.write('{"ts": 2000, "total_dollars": 1.0, "elapsed_s": 1000}\n')
    eh = EarningsHistory(history_path=path, sample_interval_s=0.0)
    stats = eh.histogram()
    assert stats.n_samples == 2  # two valid lines


def test_histogram_persists_across_instance(tmp_path) -> None:
    """Restarting EarningsHistory on the same path reads existing samples."""
    path = str(tmp_path / "persist.jsonl")
    eh1 = EarningsHistory(history_path=path, sample_interval_s=0.0)
    eh1.record(0.0, 0.0, now_ts=1000.0)
    eh1.record(1.0, 3600.0, now_ts=4600.0)
    # Simulate bot restart: new instance, same file
    eh2 = EarningsHistory(history_path=path, sample_interval_s=0.0)
    stats = eh2.histogram()
    assert stats.n_samples == 2
    assert stats.cumulative_dollars == pytest.approx(1.0)
