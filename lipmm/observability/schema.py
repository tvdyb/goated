"""Canonical decision-record schema for lipmm.

The `LIPRunner` calls `build_record(...)` once per (ticker, cycle) and passes
the resulting dict to whatever `decision_recorder` callback is configured.
The default `DecisionLogger` writes those dicts as JSONL lines; alternative
recorders (Postgres, Prometheus exporter, etc.) can consume the same dict.

Schema is deliberately market-agnostic. The `market_meta` field is a
free-form dict the operator populates via TickerSource or runner config —
that's where commodity / sport / political market specifics go. The rest
of the schema is the same regardless of market type.

Schema version is governed by `lipmm.observability.SCHEMA_VERSION` and
auto-stamped by `DecisionLogger.log` if absent. `build_record` does NOT
stamp the version itself — that lets non-DecisionLogger consumers read raw
records and stamp their own versions if they re-emit.

Top-level keys (always present):
    cycle_id           — int, monotonic per-runner-instance counter
    ts                 — float, unix timestamp at record-build time
    ticker             — str, the Kalshi ticker
    market_meta        — dict, operator-provided metadata (may be {})
    theo               — dict, projected from TheoResult
    orderbook          — dict, snapshot of best/depth (depth trimmed)
    our_state          — dict, our currently-resting bid/ask state
    decision           — dict, the strategy's QuotingDecision (post-risk-veto)
    transitions        — list, state transitions emitted this cycle
    outcome            — dict, what OrderManager actually did
    risk               — list, audit trail of risk-gate verdicts (may be [])
"""

from __future__ import annotations

from typing import Any

from lipmm.execution.order_manager import SideExecution
from lipmm.observability.decision_logger import DEPTH_TRIM_LEVELS
from lipmm.quoting.base import OrderbookSnapshot, OurState, QuotingDecision
from lipmm.theo.base import TheoResult


def build_record(
    *,
    cycle_id: int,
    ts: float,
    ticker: str,
    theo: TheoResult,
    orderbook: OrderbookSnapshot,
    our_state: OurState,
    decision: QuotingDecision,
    bid_outcome: SideExecution,
    ask_outcome: SideExecution,
    market_meta: dict[str, Any] | None = None,
    risk_audit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the canonical lipmm decision-record dict.

    All inputs are framework types; output is a plain dict suitable for
    JSON serialization and downstream filtering by `tools/grep_decisions.py`
    or any equivalent.

    `market_meta` is whatever operator-defined dict makes sense for the
    market type. Examples: `{"underlying": "soybean", "settlement_iso": "..."}`
    for commodity markets, `{"event_id": "MLB-2026-NYM-LAD", "game_starts_at": "..."}`
    for sports markets. The framework doesn't introspect this field.
    """
    return {
        "cycle_id": cycle_id,
        "ts": ts,
        "ticker": ticker,
        "market_meta": dict(market_meta) if market_meta else {},
        "theo": {
            "yes_probability": theo.yes_probability,
            "yes_cents": theo.yes_cents,
            "confidence": theo.confidence,
            "source": theo.source,
            "computed_at": theo.computed_at,
            "extras": dict(theo.extras),
        },
        "orderbook": {
            "best_bid": orderbook.best_bid,
            "best_ask": orderbook.best_ask,
            "yes_depth": _trim(orderbook.yes_depth),
            "no_depth": _trim(orderbook.no_depth),
        },
        "our_state": {
            "cur_bid_px": our_state.cur_bid_px,
            "cur_bid_size": our_state.cur_bid_size,
            "cur_bid_id": our_state.cur_bid_id,
            "cur_ask_px": our_state.cur_ask_px,
            "cur_ask_size": our_state.cur_ask_size,
            "cur_ask_id": our_state.cur_ask_id,
        },
        "decision": {
            "bid_price": decision.bid.price,
            "bid_size": decision.bid.size,
            "bid_skip": decision.bid.skip,
            "bid_reason": decision.bid.reason,
            "bid_extras": dict(decision.bid.extras),
            "ask_price": decision.ask.price,
            "ask_size": decision.ask.size,
            "ask_skip": decision.ask.skip,
            "ask_reason": decision.ask.reason,
            "ask_extras": dict(decision.ask.extras),
        },
        "transitions": list(decision.transitions),
        "outcome": {
            "bid_action": bid_outcome.action,
            "bid_reason": bid_outcome.reason,
            "bid_order_id": bid_outcome.order_id,
            "bid_latency_ms": bid_outcome.latency_ms,
            "ask_action": ask_outcome.action,
            "ask_reason": ask_outcome.reason,
            "ask_order_id": ask_outcome.order_id,
            "ask_latency_ms": ask_outcome.latency_ms,
        },
        "risk": list(risk_audit) if risk_audit else [],
    }


def _trim(depth: list[tuple[int, float]]) -> list[list]:
    """Trim depth to DEPTH_TRIM_LEVELS and convert tuples → lists."""
    if not depth:
        return []
    out: list[list] = []
    for entry in depth[:DEPTH_TRIM_LEVELS]:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            out.append([int(entry[0]), float(entry[1])])
    return out
