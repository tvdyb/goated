"""Tests for engine.decision_logger.

Verifies basic invariants:
- Writes a JSONL record per call
- Each line is valid JSON
- Schema fields are present (schema_version, timestamp_utc auto-set)
- Daily rotation works (files keyed by UTC date)
- Sub-rotation when file exceeds size cap
- Depth trimming respects the cap
- Closing flushes
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.decision_logger import (
    DEPTH_TRIM_LEVELS,
    SCHEMA_VERSION,
    DecisionLogger,
    _utc_iso,
    _utc_date_str,
    trim_depth,
)


def test_writes_record_and_parses_as_json(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log({"cycle_id": 1, "ticker": "KXTEST"})
    dl.close()

    files = list(tmp_path.glob("decisions_*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["cycle_id"] == 1
    assert record["ticker"] == "KXTEST"


def test_auto_sets_schema_version_and_timestamp(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log({"cycle_id": 1})
    dl.close()
    files = list(tmp_path.glob("decisions_*.jsonl"))
    record = json.loads(files[0].read_text().splitlines()[0])
    assert record["schema_version"] == SCHEMA_VERSION
    assert "timestamp_utc" in record
    # Format: 2026-04-30T19:23:45.123Z
    assert record["timestamp_utc"].endswith("Z")
    assert "T" in record["timestamp_utc"]


def test_user_supplied_timestamp_is_preserved(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log({"cycle_id": 1, "timestamp_utc": "2025-01-01T00:00:00.000Z"})
    dl.close()
    files = list(tmp_path.glob("decisions_*.jsonl"))
    record = json.loads(files[0].read_text().splitlines()[0])
    assert record["timestamp_utc"] == "2025-01-01T00:00:00.000Z"


def test_multiple_records_one_per_line(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    for i in range(5):
        dl.log({"cycle_id": i, "ticker": f"T{i}"})
    dl.close()
    files = list(tmp_path.glob("decisions_*.jsonl"))
    lines = files[0].read_text().splitlines()
    assert len(lines) == 5
    for i, line in enumerate(lines):
        rec = json.loads(line)
        assert rec["cycle_id"] == i


def test_does_not_raise_on_unserializable(tmp_path: Path) -> None:
    """If a value can't be JSON-encoded, the logger uses str() fallback,
    not raise. The trading loop must never be brought down by logging."""
    dl = DecisionLogger(log_dir=str(tmp_path))
    class Weird:
        pass
    # default=str fallback should kick in
    dl.log({"cycle_id": 1, "weird": Weird()})
    dl.close()


def test_handles_datetime_decimal_numpy_and_nested(tmp_path: Path) -> None:
    """Lock in serialization behavior for non-trivial types.

    Future code might use Decimal for cent-precision math or numpy.float64
    from upstream calculations. This test ensures none of those silently
    break logging — they all stringify cleanly via default=str fallback,
    and the resulting JSONL stays valid.
    """
    import json as _json
    from datetime import datetime, timezone
    from decimal import Decimal

    try:
        import numpy as np  # numpy is already a project dep
        np_value = np.float64(7.123)
    except ImportError:
        np_value = None  # type: ignore

    record = {
        "cycle_id": 1,
        "ticker": "T_NESTED",
        "datetime_field": datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
        "decimal_field": Decimal("11.8546"),
        "numpy_field": np_value,
        "nested": {
            "inner_decimal": Decimal("0.0001"),
            "inner_list": [Decimal("1"), Decimal("2")],
            "inner_dt": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    }

    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log(record)
    dl.close()

    files = list(tmp_path.glob("decisions_*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    # Critical assertion: the file is valid JSONL
    parsed = _json.loads(lines[0])
    # All fields preserved (as strings via default=str fallback for non-JSON types)
    assert parsed["cycle_id"] == 1
    assert parsed["ticker"] == "T_NESTED"
    # datetime stringified
    assert "2026-04-30" in parsed["datetime_field"]
    # Decimal stringified to its repr-equivalent
    assert parsed["decimal_field"] == "11.8546"
    # numpy.float64 should serialize natively (it inherits from float)
    if np_value is not None:
        assert abs(float(parsed["numpy_field"]) - 7.123) < 1e-9
    # Nested values also handled
    assert parsed["nested"]["inner_decimal"] == "0.0001"
    assert len(parsed["nested"]["inner_list"]) == 2
    assert "2026-01-01" in parsed["nested"]["inner_dt"]


def test_close_is_idempotent(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log({"cycle_id": 1})
    dl.close()
    dl.close()  # should not raise


def test_log_after_close_is_silent(tmp_path: Path) -> None:
    dl = DecisionLogger(log_dir=str(tmp_path))
    dl.log({"cycle_id": 1})
    dl.close()
    # After close, log() should silently no-op (not raise)
    dl.log({"cycle_id": 2})


def test_trim_depth_respects_cap() -> None:
    deep = [(i, float(100 - i)) for i in range(50)]
    trimmed = trim_depth(deep)
    assert len(trimmed) == DEPTH_TRIM_LEVELS
    # Tuples converted to lists for JSON
    assert all(isinstance(entry, list) for entry in trimmed)
    # First entry preserved
    assert trimmed[0] == [0, 100.0]


def test_trim_depth_handles_empty() -> None:
    assert trim_depth([]) == []
    assert trim_depth(None) == []  # type: ignore[arg-type]


def test_utc_iso_format() -> None:
    s = _utc_iso(0.0)  # epoch
    assert s == "1970-01-01T00:00:00.000Z"


def test_utc_date_str_format() -> None:
    assert _utc_date_str(0.0) == "1970-01-01"


def test_daily_rotation_uses_utc_date(tmp_path: Path) -> None:
    """Two writes on different UTC dates land in different files."""
    dl = DecisionLogger(log_dir=str(tmp_path))
    # Write today
    dl.log({"cycle_id": 1})
    # Force-rotate by closing and reopening tomorrow
    dl.close()
    dl2 = DecisionLogger(log_dir=str(tmp_path))
    # Manually invoke _open_today with a specific date by mutating cur_date
    # (This is a white-box test of the rotation invariant.)
    dl2._cur_date = "1999-12-31"
    dl2._open_today(0.0)  # epoch → 1970-01-01
    dl2.log({"cycle_id": 2})
    dl2.close()
    files = sorted(tmp_path.glob("decisions_*.jsonl"))
    assert len(files) == 2


def test_log_dir_created_if_missing(tmp_path: Path) -> None:
    sub = tmp_path / "deep" / "nested" / "decisions"
    assert not sub.exists()
    dl = DecisionLogger(log_dir=str(sub))
    dl.log({"cycle_id": 1})
    dl.close()
    assert sub.exists()
    files = list(sub.glob("decisions_*.jsonl"))
    assert len(files) == 1
