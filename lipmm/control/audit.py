"""Operator-command audit emission.

Every successful (and every failed) command writes one record into the
DecisionLogger with `record_type: "operator_command"`. Analysts grep by
record_type to filter operator events from quoting decisions.

The DecisionLogger is shared with the runner — same JSONL file, same
rotation. Operator commands sit in the timeline alongside the strategy
decisions they affected.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from lipmm.observability import DecisionLogger, build_operator_command_record

logger = logging.getLogger(__name__)


def emit_audit(
    decision_logger: DecisionLogger | None,
    *,
    request_id: str,
    actor: str,
    command_type: str,
    command_payload: dict[str, Any],
    state_version_before: int,
    state_version_after: int,
    succeeded: bool,
    error: str | None = None,
    side_effect_summary: dict[str, Any] | None = None,
) -> None:
    """Write an operator-command audit record.

    No-op if the decision logger is None — the control plane stays
    functional even without observability wired in (useful for tests).
    Failures inside the logger are swallowed: an audit-emit failure
    must never break the command pipeline.
    """
    if decision_logger is None:
        return
    try:
        record = build_operator_command_record(
            ts=time.time(),
            request_id=request_id,
            actor=actor,
            command_type=command_type,
            command_payload=command_payload,
            state_version_before=state_version_before,
            state_version_after=state_version_after,
            succeeded=succeeded,
            error=error,
            side_effect_summary=side_effect_summary,
        )
        decision_logger.log(record)
    except Exception as exc:
        logger.warning(
            "audit emit failed (command=%s, request_id=%s): %s",
            command_type, request_id, exc,
        )
