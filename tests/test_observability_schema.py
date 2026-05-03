"""Tests for lipmm.observability.schema.build_record.

Locks in the canonical decision-record schema. If a future change adds /
removes / renames a top-level key, these tests fail loudly so we update
SCHEMA_VERSION and downstream consumers in the same change.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from lipmm.execution.order_manager import SideExecution
from lipmm.observability import SCHEMA_VERSION, DecisionLogger, build_record
from lipmm.observability.decision_logger import DEPTH_TRIM_LEVELS
from lipmm.quoting import (
    OrderbookSnapshot,
    OurState,
    QuotingDecision,
    SideDecision,
)
from lipmm.theo import TheoResult


# ── fixtures ──────────────────────────────────────────────────────────


def _theo() -> TheoResult:
    return TheoResult(
        yes_probability=0.42,
        confidence=0.75,
        computed_at=1700000000.0,
        source="test-provider",
        extras={"forward": 11.85, "vol": 0.16},
    )


def _ob() -> OrderbookSnapshot:
    return OrderbookSnapshot(
        yes_depth=[(45, 100.0), (44, 200.0), (43, 50.0)],
        no_depth=[(45, 100.0), (44, 200.0)],
        best_bid=45,
        best_ask=55,
    )


def _our_state() -> OurState:
    return OurState(
        cur_bid_px=44, cur_bid_size=10, cur_bid_id="bid-abc",
        cur_ask_px=56, cur_ask_size=10, cur_ask_id="ask-def",
    )


def _decision() -> QuotingDecision:
    return QuotingDecision(
        bid=SideDecision(
            price=44, size=10, skip=False, reason="active-follow",
            extras={"mode": "active"},
        ),
        ask=SideDecision(
            price=56, size=10, skip=False, reason="active-follow",
            extras={"mode": "active"},
        ),
        transitions=[
            {"side": "bid", "from": "NORMAL", "to": "AGGRESSIVE",
             "reason": {"kind": "test"}},
        ],
    )


def _exec(action: str = "no_change") -> SideExecution:
    return SideExecution(
        action=action,  # type: ignore[arg-type]
        reason="test",
        order_id="o-1",
        price_cents=44,
        size=10,
        latency_ms=5,
    )


def _build(**overrides: Any) -> dict:
    """Build a record with sensible defaults; overrides replace specific kwargs."""
    kwargs: dict[str, Any] = dict(
        cycle_id=1,
        ts=1700000000.5,
        ticker="KX-T50.00",
        theo=_theo(),
        orderbook=_ob(),
        our_state=_our_state(),
        decision=_decision(),
        bid_outcome=_exec("amend"),
        ask_outcome=_exec("place_new"),
    )
    kwargs.update(overrides)
    return build_record(**kwargs)


# ── 1. Top-level schema shape ─────────────────────────────────────────


def test_build_record_has_all_required_top_level_keys() -> None:
    """If this fails, downstream consumers (analyst tools, dashboards)
    that filter on these keys will break. Bump SCHEMA_VERSION when changing."""
    rec = _build()
    required = {
        "cycle_id", "ts", "ticker", "market_meta",
        "theo", "orderbook", "our_state",
        "decision", "transitions", "outcome", "risk",
    }
    assert set(rec.keys()) == required, (
        f"top-level schema drift: missing={required - set(rec.keys())}, "
        f"unexpected={set(rec.keys()) - required}"
    )


def test_top_level_types() -> None:
    rec = _build()
    assert isinstance(rec["cycle_id"], int)
    assert isinstance(rec["ts"], float)
    assert isinstance(rec["ticker"], str)
    assert isinstance(rec["market_meta"], dict)
    assert isinstance(rec["theo"], dict)
    assert isinstance(rec["orderbook"], dict)
    assert isinstance(rec["our_state"], dict)
    assert isinstance(rec["decision"], dict)
    assert isinstance(rec["transitions"], list)
    assert isinstance(rec["outcome"], dict)


# ── 2. market_meta passthrough ───────────────────────────────────────


def test_market_meta_default_is_empty_dict() -> None:
    rec = _build()
    assert rec["market_meta"] == {}


def test_market_meta_passthrough() -> None:
    """Operator-provided market_meta survives unchanged."""
    meta = {"underlying": "soybean", "settlement_iso": "2026-04-30T17:00:00-04:00"}
    rec = _build(market_meta=meta)
    assert rec["market_meta"] == meta
    # Ensure it's a copy (mutation shouldn't leak back)
    rec["market_meta"]["new_key"] = "test"
    assert "new_key" not in meta


def test_market_meta_works_with_arbitrary_keys() -> None:
    """Schema doesn't validate market_meta contents — operators put
    whatever makes sense for their market type."""
    sport_meta = {"event_id": "MLB-2026-NYM-LAD", "innings_played": 5}
    rec = _build(market_meta=sport_meta)
    assert rec["market_meta"] == sport_meta


# ── 3. Theo / orderbook / our_state preservation ─────────────────────


def test_theo_extras_preserved() -> None:
    rec = _build()
    assert rec["theo"]["extras"] == {"forward": 11.85, "vol": 0.16}
    assert rec["theo"]["yes_probability"] == 0.42
    assert rec["theo"]["yes_cents"] == 42
    assert rec["theo"]["confidence"] == 0.75
    assert rec["theo"]["source"] == "test-provider"


def test_orderbook_depth_trimmed() -> None:
    """Deep books get cut at DEPTH_TRIM_LEVELS so records stay bounded."""
    deep_yes = [(50 - i, 100.0) for i in range(50)]
    deep_no = [(50 - i, 100.0) for i in range(50)]
    ob = OrderbookSnapshot(
        yes_depth=deep_yes, no_depth=deep_no,
        best_bid=50, best_ask=51,
    )
    rec = _build(orderbook=ob)
    assert len(rec["orderbook"]["yes_depth"]) == DEPTH_TRIM_LEVELS
    assert len(rec["orderbook"]["no_depth"]) == DEPTH_TRIM_LEVELS
    # Top of book preserved
    assert rec["orderbook"]["yes_depth"][0] == [50, 100.0]


def test_orderbook_tuples_converted_to_lists() -> None:
    """JSON serialization needs lists, not tuples."""
    rec = _build()
    for entry in rec["orderbook"]["yes_depth"]:
        assert isinstance(entry, list)


def test_our_state_includes_order_ids() -> None:
    rec = _build()
    assert rec["our_state"]["cur_bid_id"] == "bid-abc"
    assert rec["our_state"]["cur_ask_id"] == "ask-def"
    assert rec["our_state"]["cur_bid_px"] == 44
    assert rec["our_state"]["cur_ask_size"] == 10


# ── 4. Decision + transitions preservation ───────────────────────────


def test_decision_extras_preserved_per_side() -> None:
    rec = _build()
    assert rec["decision"]["bid_extras"] == {"mode": "active"}
    assert rec["decision"]["ask_extras"] == {"mode": "active"}


def test_transitions_propagate_unchanged() -> None:
    rec = _build()
    assert len(rec["transitions"]) == 1
    assert rec["transitions"][0]["side"] == "bid"
    assert rec["transitions"][0]["from"] == "NORMAL"
    assert rec["transitions"][0]["to"] == "AGGRESSIVE"


# ── 5. Outcome captures all OrderManager fields ──────────────────────


def test_outcome_captures_action_reason_id_latency() -> None:
    rec = _build()
    assert rec["outcome"]["bid_action"] == "amend"
    assert rec["outcome"]["bid_order_id"] == "o-1"
    assert rec["outcome"]["bid_latency_ms"] == 5
    assert rec["outcome"]["ask_action"] == "place_new"


# ── 6. Round-trip through DecisionLogger ─────────────────────────────


def test_record_round_trips_through_decision_logger(tmp_path) -> None:
    """End-to-end: build_record → DecisionLogger.log → JSONL on disk →
    parse back. Schema version stamped automatically by logger."""
    rec = _build()
    logger = DecisionLogger(log_dir=str(tmp_path))
    logger.log(rec)
    logger.close()

    files = list(tmp_path.glob("decisions_*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    # Schema version stamped by logger
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["schema_version"] == "lipmm-1.1"
    # User content preserved
    assert parsed["ticker"] == "KX-T50.00"
    assert parsed["theo"]["yes_cents"] == 42
