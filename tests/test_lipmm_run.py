"""Smoke tests for the deploy/lipmm_run.py entry point.

The deploy script is glue between framework components that are each
unit-tested. We don't try to retest the framework here; we verify:

  - The module imports without errors.
  - argparse exposes the expected flags.
  - Missing env vars produce a clean SystemExit(2) with helpful output.
  - Helper functions (_build_strategy, _build_risk_registry,
    _series_prefix, _validate_env) behave as documented.
  - StubTheoProvider conforms to the TheoProvider protocol and returns
    confidence=0.0 for any ticker.

Live Kalshi calls are NOT tested here. End-to-end smoke is the operator's
job (eyes on the dashboard, real API keys).
"""

from __future__ import annotations

import asyncio

import pytest

from deploy._stub_theo import StubTheoProvider
from lipmm.quoting.strategies import DefaultLIPQuoting, StickyDefenseQuoting
from lipmm.risk import (
    EndgameGuardrailGate,
    MaxNotionalPerSideGate,
    MaxOrdersPerCycleGate,
    RiskRegistry,
)
from lipmm.theo import TheoProvider, TheoResult


# ── StubTheoProvider ───────────────────────────────────────────────


def test_stub_theo_implements_protocol() -> None:
    p = StubTheoProvider("KXISMPMI")
    assert isinstance(p, TheoProvider)
    assert p.series_prefix == "KXISMPMI"


@pytest.mark.asyncio
async def test_stub_theo_returns_zero_confidence() -> None:
    p = StubTheoProvider("KX")
    await p.warmup()
    result = await p.theo("KX-T1-T55")
    assert isinstance(result, TheoResult)
    assert result.confidence == 0.0
    assert result.source.startswith("stub:")
    await p.shutdown()


@pytest.mark.asyncio
async def test_stub_theo_warmup_shutdown_no_op() -> None:
    """Stub lifecycle should be safe to call multiple times."""
    p = StubTheoProvider("KX")
    await p.warmup()
    await p.warmup()
    await p.shutdown()
    await p.shutdown()


# ── Helper functions ───────────────────────────────────────────────


def test_build_strategy_default() -> None:
    from deploy.lipmm_run import _build_strategy
    s = _build_strategy("default")
    assert isinstance(s, DefaultLIPQuoting)


def test_build_strategy_sticky() -> None:
    from deploy.lipmm_run import _build_strategy
    s = _build_strategy("sticky")
    assert isinstance(s, StickyDefenseQuoting)


def test_build_strategy_unknown_raises() -> None:
    from deploy.lipmm_run import _build_strategy
    with pytest.raises(ValueError, match="unknown --strategy"):
        _build_strategy("nonsense")


def test_build_risk_registry_has_three_gates() -> None:
    from deploy.lipmm_run import _build_risk_registry
    r = _build_risk_registry(cap_dollars=100.0)
    assert isinstance(r, RiskRegistry)
    # Inspect the gates directly via the registry's internal list
    gate_types = {type(g) for g in r._gates}  # noqa: SLF001
    assert MaxNotionalPerSideGate in gate_types
    assert MaxOrdersPerCycleGate in gate_types
    assert EndgameGuardrailGate in gate_types


def test_build_risk_registry_per_side_cap_is_half_total() -> None:
    """$100 total cap → $50 per side (so worst-case both sides exposed)."""
    from deploy.lipmm_run import _build_risk_registry
    r = _build_risk_registry(cap_dollars=200.0)
    notional_gate = next(
        g for g in r._gates  # noqa: SLF001
        if isinstance(g, MaxNotionalPerSideGate)
    )
    assert notional_gate._max_dollars == 100.0  # noqa: SLF001


def test_series_prefix_extracts_first_segment() -> None:
    from deploy.lipmm_run import _series_prefix
    assert _series_prefix("KXISMPMI-26MAY") == "KXISMPMI"
    assert _series_prefix("KXSOYBEANW-26APR27") == "KXSOYBEANW"
    # No dash → return as-is
    assert _series_prefix("PLAIN") == "PLAIN"


# ── argparse surface ───────────────────────────────────────────────


def test_argparse_event_ticker_optional() -> None:
    """Multi-event change: `--event-ticker` is now optional. With no flag,
    bot starts with no seed events; operator adds via dashboard."""
    from deploy.lipmm_run import _parse_args
    ns = _parse_args([])
    assert ns.event_ticker == ""


def test_argparse_accepts_event_ticker_only() -> None:
    from deploy.lipmm_run import _parse_args
    ns = _parse_args(["--event-ticker", "KXISMPMI-26MAY"])
    assert ns.event_ticker == "KXISMPMI-26MAY"
    assert ns.cap_dollars == 100.0
    assert ns.strategy == "default"
    assert ns.cycle_seconds == 3.0
    assert ns.port == 5050


def test_argparse_accepts_comma_separated_events() -> None:
    """Multi-event change: --event-ticker accepts comma-separated list."""
    from deploy.lipmm_run import _parse_args
    ns = _parse_args(["--event-ticker", "KXISMPMI-26MAY,KXOTHER-26JUN"])
    assert ns.event_ticker == "KXISMPMI-26MAY,KXOTHER-26JUN"


def test_argparse_strategy_choices() -> None:
    from deploy.lipmm_run import _parse_args
    with pytest.raises(SystemExit):
        _parse_args(["--event-ticker", "X", "--strategy", "made-up"])


# ── Env-var validation ─────────────────────────────────────────────


def test_validate_env_fails_when_missing(monkeypatch, capsys) -> None:
    from deploy.lipmm_run import _validate_env
    for v in ("KALSHI_API_KEY", "KALSHI_PRIVATE_KEY_PATH", "LIPMM_CONTROL_SECRET"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(SystemExit) as exc_info:
        _validate_env()
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "missing required env vars" in captured.err
    assert "LIPMM_CONTROL_SECRET" in captured.err
    # Helpful generation hint when secret is missing
    assert "secrets.token_hex(16)" in captured.err


def test_validate_env_passes_when_all_set(monkeypatch) -> None:
    from deploy.lipmm_run import _validate_env
    monkeypatch.setenv("KALSHI_API_KEY", "x")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/dev/null")
    monkeypatch.setenv("LIPMM_CONTROL_SECRET", "0" * 32)
    _validate_env()  # should not raise


def test_validate_env_partial_missing_lists_only_missing(monkeypatch, capsys) -> None:
    from deploy.lipmm_run import _validate_env
    monkeypatch.setenv("KALSHI_API_KEY", "x")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/dev/null")
    monkeypatch.delenv("LIPMM_CONTROL_SECRET", raising=False)
    with pytest.raises(SystemExit):
        _validate_env()
    captured = capsys.readouterr()
    assert "LIPMM_CONTROL_SECRET" in captured.err
    assert "KALSHI_API_KEY" not in captured.err.split("\n", 1)[0]


# ── Module-level imports ───────────────────────────────────────────


def test_module_imports_cleanly() -> None:
    """Pure import smoke — ensures no top-level error escapes."""
    import deploy.lipmm_run as m
    assert callable(m.main)
    assert callable(m._amain)
    assert hasattr(m, "_MultiEventTickerSource")
    assert hasattr(m, "_validate_event")


# ── _MultiEventTickerSource against both response shapes ──────────


class _StubState:
    """Minimal ControlState stand-in: holds an event-tickers set."""
    def __init__(self, events: list[str] | None = None) -> None:
        self._events = set(events or [])
    def all_events(self) -> set[str]:
        return set(self._events)


@pytest.mark.asyncio
async def test_multi_event_source_handles_nested_markets() -> None:
    """Phase 11: when Kalshi returns markets nested inside event, the
    source must extract them."""
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            return {
                "event": {
                    "event_ticker": event_ticker,
                    "markets": [
                        {"ticker": "KX-T49", "status": "open"},
                        {"ticker": "KX-T50", "status": "open"},
                        {"ticker": "KX-T51", "status": "settled"},
                    ],
                },
            }

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-EVENT"]))
    tickers = await src.list_active_tickers(None)
    assert sorted(tickers) == ["KX-T49", "KX-T50"]


@pytest.mark.asyncio
async def test_multi_event_source_handles_sibling_markets() -> None:
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            return {
                "event": {"event_ticker": event_ticker},
                "markets": [
                    {"ticker": "KX-T49", "status": "open"},
                    {"ticker": "KX-T50", "status": "open"},
                ],
            }

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-EVENT"]))
    tickers = await src.list_active_tickers(None)
    assert sorted(tickers) == ["KX-T49", "KX-T50"]


@pytest.mark.asyncio
async def test_multi_event_source_dedupes_when_both_paths_populated() -> None:
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            return {
                "event": {
                    "event_ticker": event_ticker,
                    "markets": [{"ticker": "KX-T1", "status": "open"}],
                },
                "markets": [{"ticker": "KX-T1", "status": "open"}],
            }

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-EVENT"]))
    tickers = await src.list_active_tickers(None)
    assert tickers == ["KX-T1"]


@pytest.mark.asyncio
async def test_multi_event_source_treats_active_as_tradable() -> None:
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            return {
                "event": {"event_ticker": event_ticker},
                "markets": [
                    {"ticker": "KX-ACTIVE", "status": "active"},
                    {"ticker": "KX-OPEN", "status": "open"},
                    {"ticker": "KX-NEW", "status": "some-future-status"},
                    {"ticker": "KX-MISSING-STATUS"},
                    {"ticker": "KX-SETTLED", "status": "settled"},
                    {"ticker": "KX-CLOSED", "status": "closed"},
                    {"ticker": "KX-FINALIZED", "status": "finalized"},
                    {"ticker": "KX-UNOPENED", "status": "unopened"},
                    {"ticker": "KX-DEACTIVATED", "status": "deactivated"},
                ],
            }

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-EVENT"]))
    tickers = await src.list_active_tickers(None)
    assert sorted(tickers) == [
        "KX-ACTIVE", "KX-MISSING-STATUS", "KX-NEW", "KX-OPEN",
    ]


@pytest.mark.asyncio
async def test_multi_event_source_tolerates_per_event_failures() -> None:
    """One event raising shouldn't blank out the whole bot — other
    events still yield their markets."""
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            if event_ticker == "KX-BAD":
                raise RuntimeError("kalshi 503")
            return {
                "event": {"event_ticker": event_ticker},
                "markets": [{"ticker": "KX-OK-T1", "status": "active"}],
            }

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-BAD", "KX-GOOD"]))
    tickers = await src.list_active_tickers(None)
    assert tickers == ["KX-OK-T1"]


@pytest.mark.asyncio
async def test_multi_event_source_empty_set_returns_empty() -> None:
    """No active events → empty list. Bot sits idle."""
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, *a, **k):
            raise AssertionError("must not be called when no events")

    src = _MultiEventTickerSource(_Stub(), _StubState([]))
    tickers = await src.list_active_tickers(None)
    assert tickers == []


@pytest.mark.asyncio
async def test_multi_event_source_unions_across_events() -> None:
    """Markets across multiple events appear in the result, deduped."""
    from deploy.lipmm_run import _MultiEventTickerSource

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            if event_ticker == "KX-A":
                return {"event": {}, "markets": [
                    {"ticker": "KX-A-T1", "status": "active"},
                    {"ticker": "KX-A-T2", "status": "active"},
                ]}
            if event_ticker == "KX-B":
                return {"event": {}, "markets": [
                    {"ticker": "KX-B-T1", "status": "active"},
                ]}
            return {"event": {}, "markets": []}

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-A", "KX-B"]))
    tickers = await src.list_active_tickers(None)
    assert sorted(tickers) == ["KX-A-T1", "KX-A-T2", "KX-B-T1"]


@pytest.mark.asyncio
async def test_multi_event_source_passes_with_nested_markets_kwarg() -> None:
    from deploy.lipmm_run import _MultiEventTickerSource

    seen_kwargs: dict = {}

    class _Stub:
        async def get_event(self, event_ticker, *, with_nested_markets=False):
            seen_kwargs["with_nested_markets"] = with_nested_markets
            return {"event": {}, "markets": []}

    src = _MultiEventTickerSource(_Stub(), _StubState(["KX-EVENT"]))
    await src.list_active_tickers(None)
    assert seen_kwargs["with_nested_markets"] is True
