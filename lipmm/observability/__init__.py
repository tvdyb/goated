"""Observability — structured per-cycle decision logging.

The framework's `LIPRunner` accepts a `decision_recorder` callback that
receives one structured record per (ticker, cycle). This package provides:

  - `DecisionLogger`: the canonical JSONL recorder. Daily UTC rotation,
    sub-rotation at 500MB, throttled fsync, depth trimming.
  - `build_record`: pure helper that turns runner inputs into the canonical
    schema dict. Useful for non-DecisionLogger consumers (e.g., a future
    Postgres backend or a metrics exporter).

Schema is namespaced as "lipmm-1.0" so log files from lipmm-bots are
distinguishable from any prior soy-bot logs that used "1.0" / "1.1".

Records are market-agnostic: the `market_meta` field is an arbitrary dict
the operator populates (per-strike data, per-event tags, etc.). The schema
itself doesn't assume any commodity / sport / political market shape.

Privacy: records contain order IDs, prices, and theo internals. No PII.
Don't upload to public services without review — competitive LIP info.
"""

from lipmm.observability.decision_logger import (
    DEPTH_TRIM_LEVELS,
    SCHEMA_VERSION,
    DecisionLogger,
    trim_depth,
)
from lipmm.observability.retention import RetentionManager, RetentionStats
from lipmm.observability.schema import build_operator_command_record, build_record

__all__ = [
    "DEPTH_TRIM_LEVELS",
    "DecisionLogger",
    "RetentionManager",
    "RetentionStats",
    "SCHEMA_VERSION",
    "build_operator_command_record",
    "build_record",
    "trim_depth",
]
