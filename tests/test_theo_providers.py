"""Tests for the accessible TheoProvider integrations:
  - `function_provider` decorator
  - `FilePollTheoProvider` (CSV + JSON, staleness, errors)
  - `HttpPollTheoProvider` (mocked transport, staleness, errors)
  - Wildcard '*' series-prefix routing in the registry
  - CLI spec parsing in deploy.lipmm_run
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from lipmm.theo import TheoRegistry, TheoResult
from lipmm.theo.providers import (
    FilePollTheoProvider,
    HttpPollTheoProvider,
    function_provider,
)


# ── function_provider decorator ─────────────────────────────────────


@pytest.mark.asyncio
async def test_function_provider_routes_through_registry() -> None:
    @function_provider(series_prefix="KXISMPMI", source="test-fn")
    async def fn(ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=0.7, confidence=0.9,
            computed_at=0.0, source="test-fn",
        )
    reg = TheoRegistry()
    reg.register(fn)
    res = await reg.theo("KXISMPMI-26MAY-50")
    assert res.yes_probability == 0.7
    assert res.confidence == 0.9
    assert res.source == "test-fn"


@pytest.mark.asyncio
async def test_function_provider_wildcard_prefix() -> None:
    @function_provider(series_prefix="*", source="wildcard")
    async def fn(ticker: str) -> TheoResult:
        return TheoResult(
            yes_probability=0.5, confidence=0.5,
            computed_at=0.0, source="wildcard",
        )
    reg = TheoRegistry()
    reg.register(fn)
    # Wildcard serves any unmatched prefix
    r1 = await reg.theo("KXANY-X-1")
    r2 = await reg.theo("OTHEREVENT-2")
    assert r1.source == r2.source == "wildcard"


def test_function_provider_rejects_empty_prefix() -> None:
    with pytest.raises(ValueError, match="series_prefix"):
        function_provider(series_prefix="")


# ── Wildcard registry routing ───────────────────────────────────────


@pytest.mark.asyncio
async def test_registry_wildcard_loses_to_exact_prefix() -> None:
    """Specific-prefix providers always win over '*'."""
    @function_provider(series_prefix="*", source="fallback")
    async def wild(ticker: str) -> TheoResult:
        return TheoResult(0.5, 0.5, 0.0, "fallback")

    @function_provider(series_prefix="KXISMPMI", source="specific")
    async def specific(ticker: str) -> TheoResult:
        return TheoResult(0.6, 0.6, 0.0, "specific")

    reg = TheoRegistry()
    reg.register(wild)
    reg.register(specific)
    r1 = await reg.theo("KXISMPMI-26MAY-50")
    r2 = await reg.theo("OTHER-99")
    assert r1.source == "specific"
    assert r2.source == "fallback"


# ── FilePollTheoProvider — CSV ──────────────────────────────────────


@pytest.mark.asyncio
async def test_file_poll_loads_csv(tmp_path: Path) -> None:
    p = tmp_path / "theos.csv"
    p.write_text(
        "ticker,yes_cents,confidence,reason\n"
        "KX-A,82,0.85,model-v1\n"
        "KX-B,40,0.50,model-v1\n"
    )
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=0.1,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.yes_probability == pytest.approx(0.82)
        assert r.confidence == 0.85
        r2 = await prov.theo("KX-B")
        assert r2.yes_probability == pytest.approx(0.40)
        assert r2.confidence == 0.50
        # Unknown ticker → confidence 0
        miss = await prov.theo("KX-Z")
        assert miss.confidence == 0.0
        assert "no-row" in miss.source
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_loads_json_dict_shape(tmp_path: Path) -> None:
    p = tmp_path / "theos.json"
    p.write_text(json.dumps({
        "KX-A": {"yes_cents": 82, "confidence": 0.85, "reason": "x"},
    }))
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=0.1,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.yes_probability == pytest.approx(0.82)
        assert r.confidence == 0.85
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_loads_json_list_shape(tmp_path: Path) -> None:
    p = tmp_path / "theos.json"
    p.write_text(json.dumps([
        {"ticker": "KX-A", "yes_cents": 82, "confidence": 0.85},
        {"ticker": "KX-B", "yes_cents": 40, "confidence": 0.50},
    ]))
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=0.1,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-B")
        assert r.yes_probability == pytest.approx(0.40)
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_skips_malformed_rows(tmp_path: Path) -> None:
    p = tmp_path / "theos.csv"
    p.write_text(
        "ticker,yes_cents,confidence,reason\n"
        "KX-A,82,0.85,ok\n"
        "KX-OUT-OF-RANGE,150,0.85,bad\n"
        "KX-BAD-CONF,50,1.5,bad\n"
        ",30,0.5,no-ticker\n"
        "KX-NONNUMERIC,abc,0.5,bad\n"
        "KX-OK2,40,0.5,ok\n"
    )
    prov = FilePollTheoProvider(str(p), series_prefix="*")
    await prov.warmup()
    try:
        # Two valid rows survived; the others were dropped
        r1 = await prov.theo("KX-A")
        r2 = await prov.theo("KX-OK2")
        assert r1.confidence == 0.85
        assert r2.confidence == 0.5
        bad = await prov.theo("KX-OUT-OF-RANGE")
        assert bad.confidence == 0.0  # not in snapshot → no-row
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_picks_up_changes(tmp_path: Path) -> None:
    p = tmp_path / "theos.csv"
    p.write_text(
        "ticker,yes_cents,confidence,reason\n"
        "KX-A,50,0.5,initial\n"
    )
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=0.05,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.yes_probability == pytest.approx(0.50)
        # Bump mtime + rewrite
        time.sleep(0.05)  # ensure mtime resolution moves
        p.write_text(
            "ticker,yes_cents,confidence,reason\n"
            "KX-A,75,0.9,updated\n"
        )
        os.utime(p, None)
        # Wait for at least one poll cycle
        await asyncio.sleep(0.2)
        r2 = await prov.theo("KX-A")
        assert r2.yes_probability == pytest.approx(0.75)
        assert r2.confidence == 0.9
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_staleness_drops_confidence(tmp_path: Path) -> None:
    p = tmp_path / "theos.csv"
    p.write_text(
        "ticker,yes_cents,confidence,reason\n"
        "KX-A,82,0.9,initial\n"
    )
    # Very tight staleness threshold so we cross it without waiting long.
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=10.0,
        staleness_threshold_s=0.05,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.confidence == 0.9
        await asyncio.sleep(0.1)
        r2 = await prov.theo("KX-A")
        assert r2.confidence == 0.0
        assert ":stale" in r2.source
        # The yes_probability is still preserved for inspection
        assert r2.yes_probability == pytest.approx(0.82)
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_staleness_disabled_when_none(tmp_path: Path) -> None:
    p = tmp_path / "theos.csv"
    p.write_text(
        "ticker,yes_cents,confidence,reason\n"
        "KX-A,82,0.9,initial\n"
    )
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=10.0,
        staleness_threshold_s=None,
    )
    await prov.warmup()
    try:
        await asyncio.sleep(0.1)
        r = await prov.theo("KX-A")
        assert r.confidence == 0.9  # never goes stale
    finally:
        await prov.shutdown()


@pytest.mark.asyncio
async def test_file_poll_missing_file_keeps_running(tmp_path: Path) -> None:
    p = tmp_path / "missing.csv"
    prov = FilePollTheoProvider(
        str(p), series_prefix="*", refresh_s=0.05,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.confidence == 0.0  # empty snapshot
        # Now create the file mid-run
        p.write_text("ticker,yes_cents,confidence,reason\nKX-A,50,0.5,x\n")
        await asyncio.sleep(0.2)
        r2 = await prov.theo("KX-A")
        assert r2.confidence == 0.5
    finally:
        await prov.shutdown()


def test_file_poll_rejects_invalid_args(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    with pytest.raises(ValueError, match="series_prefix"):
        FilePollTheoProvider(str(p), series_prefix="")
    with pytest.raises(ValueError, match="refresh_s"):
        FilePollTheoProvider(str(p), series_prefix="*", refresh_s=0)


# ── HttpPollTheoProvider ────────────────────────────────────────────


def _mock_transport(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_http_poll_loads_initial_snapshot() -> None:
    payload = json.dumps({
        "KX-A": {"yes_cents": 82, "confidence": 0.85},
    })
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=payload)
    client = _mock_transport(handler)
    prov = HttpPollTheoProvider(
        "http://example/theos", series_prefix="*", refresh_s=0.05,
        client=client,
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.yes_probability == pytest.approx(0.82)
        assert r.confidence == 0.85
    finally:
        await prov.shutdown()
        await client.aclose()


@pytest.mark.asyncio
async def test_http_poll_keeps_last_good_on_error() -> None:
    payloads = [
        json.dumps({"KX-A": {"yes_cents": 82, "confidence": 0.9}}),
        # second call will 500
    ]
    call_n = {"n": 0}
    def handler(req: httpx.Request) -> httpx.Response:
        call_n["n"] += 1
        if call_n["n"] == 1:
            return httpx.Response(200, text=payloads[0])
        return httpx.Response(500, text="boom")
    client = _mock_transport(handler)
    prov = HttpPollTheoProvider(
        "http://example/theos", series_prefix="*", refresh_s=0.05,
        client=client, staleness_threshold_s=None,  # don't hide last-good
    )
    await prov.warmup()
    try:
        r = await prov.theo("KX-A")
        assert r.confidence == 0.9
        # Wait for next poll which will 500
        await asyncio.sleep(0.2)
        r2 = await prov.theo("KX-A")
        assert r2.confidence == 0.9  # last good preserved
    finally:
        await prov.shutdown()
        await client.aclose()


@pytest.mark.asyncio
async def test_http_poll_sends_bearer_header() -> None:
    seen_auth = {}
    def handler(req: httpx.Request) -> httpx.Response:
        seen_auth["v"] = req.headers.get("authorization", "")
        return httpx.Response(200, text=json.dumps({}))
    client = _mock_transport(handler)
    prov = HttpPollTheoProvider(
        "http://example/theos", series_prefix="*", refresh_s=0.05,
        bearer="my-secret-token", client=client,
    )
    await prov.warmup()
    try:
        await prov.theo("KX-A")
    finally:
        await prov.shutdown()
        await client.aclose()
    assert seen_auth["v"] == "Bearer my-secret-token"


# ── CLI spec parsing ────────────────────────────────────────────────


def test_cli_spec_parsing_defaults() -> None:
    from deploy.lipmm_run import _parse_provider_spec
    assert _parse_provider_spec("/tmp/x.csv", kind="csv") == (
        "/tmp/x.csv", "*", None,
    )
    assert _parse_provider_spec("/tmp/x.csv:KXISMPMI", kind="csv") == (
        "/tmp/x.csv", "KXISMPMI", None,
    )
    assert _parse_provider_spec("/tmp/x.csv:KXISMPMI:10", kind="csv") == (
        "/tmp/x.csv", "KXISMPMI", 10.0,
    )


def test_cli_spec_parsing_http_url() -> None:
    """HTTP specs are tricky because URL contains ':'. Parser must
    correctly peel off the trailing prefix/refresh fields without
    mangling the URL."""
    from deploy.lipmm_run import _parse_provider_spec
    assert _parse_provider_spec(
        "http://host:8001/theos", kind="http",
    ) == ("http://host:8001/theos", "*", None)
    assert _parse_provider_spec(
        "http://host:8001/theos:KXISMPMI", kind="http",
    ) == ("http://host:8001/theos", "KXISMPMI", None)
    assert _parse_provider_spec(
        "http://host:8001/theos:KXISMPMI:2", kind="http",
    ) == ("http://host:8001/theos", "KXISMPMI", 2.0)


def test_cli_argparse_repeatable() -> None:
    from deploy.lipmm_run import _parse_args
    ns = _parse_args([
        "--theo-csv", "/tmp/a.csv",
        "--theo-csv", "/tmp/b.csv:KXISMPMI",
        "--theo-http", "http://localhost:8001/theos",
    ])
    assert ns.theo_csv == ["/tmp/a.csv", "/tmp/b.csv:KXISMPMI"]
    assert ns.theo_http == ["http://localhost:8001/theos"]
    assert ns.theo_json == []
