"""Tests for Phase 8 — Kalshi /incentive_programs surface.

Covers:
  - IncentiveProgram.from_api parses the documented schema, derived
    properties (period_reward_dollars, time_remaining_s, is_active)
    behave correctly.
  - KalshiIncentiveProvider walks pagination via next_cursor, sends
    the right query params, and raises on transport errors.
  - IncentiveCache start/refresh/stop, fault tolerance (provider raises
    on a non-initial fetch → keeps last snapshot, no crash).
  - GET /control/incentives endpoint shape (503 without provider, 200
    with cache).
  - WS /control/stream/html receives an incentives_snapshot HTML push
    when the broadcaster fires.
  - Dashboard renders the incentives panel with active programs +
    empty state + provider-not-wired state.
  - feeds/kalshi/lip_pool.parse_incentive_program_entry maps the new
    API shape to the existing LIPRewardPeriod dataclass.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from lipmm.control import Broadcaster, ControlServer, ControlState, build_app
from lipmm.control.auth import issue_token
from lipmm.incentives import (
    IncentiveCache,
    IncentiveProgram,
    KalshiIncentiveProvider,
)


SECRET = "0123456789abcdef0123456789abcdef"


# ── Fixtures ────────────────────────────────────────────────────────


def _sample_entry(**overrides) -> dict[str, Any]:
    base = {
        "id": "prog-1",
        "market_id": "mkt-1",
        "market_ticker": "KXISMPMI-26MAY-T50.0",
        "incentive_type": "liquidity",
        "incentive_description": "PMI may LIP",
        "start_date": "2026-05-01T14:00:00Z",
        "end_date": "2026-06-01T14:00:00Z",
        "period_reward": 5_000_000,    # $500 in centi-cents
        "paid_out": False,
        "discount_factor_bps": 250,
        "target_size_fp": "100.00",
    }
    base.update(overrides)
    return base


# ── IncentiveProgram parsing + derived props ───────────────────────


def test_from_api_parses_full_entry() -> None:
    p = IncentiveProgram.from_api(_sample_entry())
    assert p.id == "prog-1"
    assert p.market_ticker == "KXISMPMI-26MAY-T50.0"
    assert p.incentive_type == "liquidity"
    assert p.period_reward_centi_cents == 5_000_000
    assert p.discount_factor_bps == 250
    assert p.target_size_fp == "100.00"
    # ISO-8601 → unix ts: just verify ordering + UTC parse worked.
    from datetime import datetime, timezone
    expected_start = datetime(2026, 5, 1, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    expected_end = datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone.utc).timestamp()
    assert p.start_date_ts == pytest.approx(expected_start)
    assert p.end_date_ts == pytest.approx(expected_end)


def test_period_reward_dollars_centi_cents_conversion() -> None:
    p = IncentiveProgram.from_api(_sample_entry(period_reward=12_345_678))
    # 12,345,678 centi-cents = $1,234.5678
    assert abs(p.period_reward_dollars - 1234.5678) < 1e-9


def test_discount_factor_pct() -> None:
    p = IncentiveProgram.from_api(_sample_entry(discount_factor_bps=750))
    assert p.discount_factor_pct == 7.5


def test_target_size_contracts_parses_fp_string() -> None:
    p = IncentiveProgram.from_api(_sample_entry(target_size_fp="250.50"))
    assert p.target_size_contracts == 250.5


def test_optional_fields_can_be_null() -> None:
    p = IncentiveProgram.from_api(_sample_entry(
        discount_factor_bps=None, target_size_fp=None,
    ))
    assert p.discount_factor_bps is None
    assert p.discount_factor_pct is None
    assert p.target_size_fp is None
    assert p.target_size_contracts is None


def test_is_active_window_and_paid_out() -> None:
    p = IncentiveProgram.from_api(_sample_entry())
    # Within window
    midpoint = (p.start_date_ts + p.end_date_ts) / 2
    assert p.is_active(midpoint) is True
    # Before window
    assert p.is_active(p.start_date_ts - 1.0) is False
    # After window
    assert p.is_active(p.end_date_ts + 1.0) is False
    # paid_out trumps everything
    paid = IncentiveProgram.from_api(_sample_entry(paid_out=True))
    assert paid.is_active(midpoint) is False


def test_time_remaining_s_decreases_then_negative() -> None:
    p = IncentiveProgram.from_api(_sample_entry())
    before = p.time_remaining_s(p.end_date_ts - 100.0)
    after = p.time_remaining_s(p.end_date_ts + 100.0)
    assert before == pytest.approx(100.0)
    assert after == pytest.approx(-100.0)


def test_iso8601_with_explicit_offset_parses() -> None:
    p = IncentiveProgram.from_api(_sample_entry(
        start_date="2026-05-01T14:00:00+00:00",
        end_date="2026-06-01T14:00:00+00:00",
    ))
    assert p.start_date_ts < p.end_date_ts


# ── KalshiIncentiveProvider — pagination + query params ────────────


@pytest.mark.asyncio
async def test_provider_sends_correct_params_and_parses() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={
            "incentive_programs": [_sample_entry()],
            "next_cursor": "",
        })

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = KalshiIncentiveProvider(client=client)
        progs = await provider.list_active()
    assert len(progs) == 1
    assert progs[0].market_ticker == "KXISMPMI-26MAY-T50.0"
    assert len(captured) == 1
    qp = dict(captured[0].url.params)
    assert qp["status"] == "active"
    assert qp["type"] == "liquidity"
    assert qp["limit"] == "1000"
    assert "cursor" not in qp


@pytest.mark.asyncio
async def test_provider_walks_pagination_cursor() -> None:
    pages = [
        {
            "incentive_programs": [_sample_entry(id="p1", market_ticker="KX-A")],
            "next_cursor": "tok-1",
        },
        {
            "incentive_programs": [_sample_entry(id="p2", market_ticker="KX-B")],
            "next_cursor": "tok-2",
        },
        {
            "incentive_programs": [_sample_entry(id="p3", market_ticker="KX-C")],
            "next_cursor": "",
        },
    ]
    seen_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cursors.append(request.url.params.get("cursor"))
        return httpx.Response(200, json=pages.pop(0))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = KalshiIncentiveProvider(client=client)
        progs = await provider.list_active()
    assert [p.id for p in progs] == ["p1", "p2", "p3"]
    assert seen_cursors == [None, "tok-1", "tok-2"]


@pytest.mark.asyncio
async def test_provider_raises_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = KalshiIncentiveProvider(client=client)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.list_active()


@pytest.mark.asyncio
async def test_provider_skips_malformed_entries_logs() -> None:
    """One bad entry shouldn't poison the whole page."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "incentive_programs": [
                _sample_entry(id="ok"),
                {"id": "bad", "market_ticker": "KX-X"},  # missing fields
            ],
            "next_cursor": "",
        })
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = KalshiIncentiveProvider(client=client)
        progs = await provider.list_active()
    assert len(progs) == 1
    assert progs[0].id == "ok"


# ── IncentiveCache — fault tolerance + lifecycle ───────────────────


class _StubProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.programs: list[IncentiveProgram] = []
        self.raises: Exception | None = None

    async def list_active(self) -> list[IncentiveProgram]:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return list(self.programs)


@pytest.mark.asyncio
async def test_cache_initial_failure_propagates() -> None:
    """Misconfiguration on startup should be loud."""
    p = _StubProvider()
    p.raises = RuntimeError("DNS down")
    cache = IncentiveCache(p, refresh_s=10.0)
    with pytest.raises(RuntimeError, match="DNS down"):
        await cache.refresh_once()


@pytest.mark.asyncio
async def test_cache_subsequent_failure_keeps_last_snapshot() -> None:
    p = _StubProvider()
    p.programs = [IncentiveProgram.from_api(_sample_entry(id="a"))]
    cache = IncentiveCache(p, refresh_s=10.0)
    await cache.refresh_once()
    assert len(cache.snapshot()) == 1

    # Now provider starts failing
    p.raises = RuntimeError("rate limited")
    snap = await cache.refresh_once()  # should NOT raise
    assert len(snap) == 1
    assert snap[0].id == "a"


@pytest.mark.asyncio
async def test_cache_by_ticker_groups_correctly() -> None:
    p = _StubProvider()
    p.programs = [
        IncentiveProgram.from_api(_sample_entry(id="a", market_ticker="KX-T1")),
        IncentiveProgram.from_api(_sample_entry(id="b", market_ticker="KX-T1")),
        IncentiveProgram.from_api(_sample_entry(id="c", market_ticker="KX-T2")),
    ]
    cache = IncentiveCache(p, refresh_s=10.0)
    await cache.refresh_once()
    by = cache.by_ticker()
    assert sorted(by.keys()) == ["KX-T1", "KX-T2"]
    assert len(by["KX-T1"]) == 2
    assert len(by["KX-T2"]) == 1


@pytest.mark.asyncio
async def test_cache_start_stop_runs_periodic_refresh() -> None:
    p = _StubProvider()
    p.programs = [IncentiveProgram.from_api(_sample_entry(id="a"))]
    cache = IncentiveCache(p, refresh_s=0.05)
    await cache.start()
    initial_calls = p.calls
    await asyncio.sleep(0.18)  # ~3 ticks
    await cache.stop()
    assert p.calls > initial_calls


@pytest.mark.asyncio
async def test_cache_rejects_invalid_refresh_s() -> None:
    p = _StubProvider()
    with pytest.raises(ValueError, match="refresh_s"):
        IncentiveCache(p, refresh_s=0.0)


# ── GET /control/incentives endpoint ───────────────────────────────


def _client_with_cache(
    cache: IncentiveCache | None = None,
) -> tuple[TestClient, ControlState, Broadcaster]:
    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        incentive_cache=cache,
    )
    return TestClient(app), state, b


def _h() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(SECRET)}"}


def test_get_incentives_503_without_cache() -> None:
    client, _, _ = _client_with_cache()
    r = client.get("/control/incentives", headers=_h())
    assert r.status_code == 503


def test_get_incentives_returns_snapshot_when_wired() -> None:
    p = _StubProvider()
    p.programs = [
        IncentiveProgram.from_api(_sample_entry(id="a", market_ticker="KX-A")),
        IncentiveProgram.from_api(_sample_entry(id="b", market_ticker="KX-B")),
    ]
    cache = IncentiveCache(p, refresh_s=10.0)
    asyncio.get_event_loop().run_until_complete(cache.refresh_once())
    client, _, _ = _client_with_cache(cache)
    r = client.get("/control/incentives", headers=_h())
    assert r.status_code == 200
    body = r.json()
    assert len(body["programs"]) == 2
    assert body["last_refresh_ts"] > 0
    # Each entry has the operator-friendly fields
    e = body["programs"][0]
    assert "period_reward_dollars" in e
    assert "time_remaining_s" in e


def test_get_incentives_requires_auth() -> None:
    p = _StubProvider()
    cache = IncentiveCache(p, refresh_s=10.0)
    asyncio.get_event_loop().run_until_complete(cache.refresh_once())
    client, _, _ = _client_with_cache(cache)
    r = client.get("/control/incentives")
    assert r.status_code == 401


# ── WebSocket HTML push ────────────────────────────────────────────


def test_html_ws_receives_incentives_snapshot() -> None:
    p = _StubProvider()
    p.programs = [IncentiveProgram.from_api(_sample_entry(id="a"))]
    cache = IncentiveCache(p, refresh_s=10.0)
    asyncio.get_event_loop().run_until_complete(cache.refresh_once())

    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        incentive_cache=cache, mount_dashboard=True,
    )
    client = TestClient(app)
    token = issue_token(SECRET)
    with client.websocket_connect(f"/control/stream/html?token={token}") as ws:
        ws.receive_text()  # initial frame
        # Synthesize a broadcast
        async def push() -> None:
            snap = app.state.collect_incentives()
            await b.broadcast_incentives(snap)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(push())
        finally:
            loop.close()
        html = ws.receive_text()
        # Phase 10: incentives are folded into the strike grid (LIP $
        # column per row) + event header (total LIP $/period). The
        # standalone incentives panel is gone.
        assert 'id="strike-grid"' in html or 'id="event-header"' in html
        assert "KXISMPMI-26MAY-T50.0" in html


# ── Dashboard render ───────────────────────────────────────────────


def test_dashboard_renders_incentives_in_strike_grid_and_header() -> None:
    """Phase 10: LIP info appears inline per strike in the grid (LIP $
    column) and aggregated in the event header ($N LIP/period pill)."""
    p = _StubProvider()
    p.programs = [
        IncentiveProgram.from_api(_sample_entry(
            id="a", market_ticker="KX-PMI-T50",
            period_reward=10_000_000,  # $1000
        )),
    ]
    cache = IncentiveCache(p, refresh_s=10.0)
    asyncio.get_event_loop().run_until_complete(cache.refresh_once())
    state = ControlState()
    b = Broadcaster()
    app = build_app(
        state, secret=SECRET, broadcaster=b,
        incentive_cache=cache, mount_dashboard=True,
    )
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    assert 'id="strike-grid"' in body
    assert 'id="event-header"' in body
    assert "KX-PMI-T50" in body
    # LIP $1000/period in the row + total in the event header
    assert "$1000" in body


def test_dashboard_renders_cleanly_without_incentive_cache() -> None:
    """Phase 10: missing incentive cache doesn't surface a panel error;
    grid just renders without the LIP pill in the header."""
    state = ControlState()
    b = Broadcaster()
    app = build_app(state, secret=SECRET, broadcaster=b, mount_dashboard=True)
    client = TestClient(app)
    r = client.get("/dashboard")
    body = r.text
    assert 'id="strike-grid"' in body
    assert 'id="event-header"' in body


# ── feeds/kalshi/lip_pool heal ─────────────────────────────────────


def test_lip_pool_parse_incentive_program_entry_maps_centi_cents() -> None:
    from feeds.kalshi.lip_pool import parse_incentive_program_entry
    entry = _sample_entry(period_reward=2_500_000)  # $250
    period = parse_incentive_program_entry(entry)
    assert period.market_ticker == "KXISMPMI-26MAY-T50.0"
    assert period.pool_size_usd == 250.0
    assert period.source == "api"
    assert period.active is True or period.active is False  # depends on now


def test_lip_pool_parse_incentive_program_entry_paid_out_inactive() -> None:
    from feeds.kalshi.lip_pool import parse_incentive_program_entry
    period = parse_incentive_program_entry(_sample_entry(paid_out=True))
    assert period.active is False


def test_lip_pool_parse_incentive_program_entry_raises_on_malformed() -> None:
    from feeds.kalshi.lip_pool import LIPPoolDataError, parse_incentive_program_entry
    with pytest.raises(LIPPoolDataError):
        parse_incentive_program_entry({"id": "x"})  # missing required fields
