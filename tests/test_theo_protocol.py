"""Tests for lipmm.theo: TheoResult contract, registry routing, GBM provider.

These tests are the protocol's contract. If they break, downstream code
(sticky, decision logger, dashboard) breaks.
"""

from __future__ import annotations

import time

import pytest

from lipmm.theo import TheoProvider, TheoRegistry, TheoResult
from lipmm.theo.providers.gbm_commodity import GbmCommodityConfig, GbmCommodityTheo


# ── TheoResult dataclass contract ─────────────────────────────────────


def test_theo_result_validates_probability_range() -> None:
    with pytest.raises(ValueError):
        TheoResult(yes_probability=1.5, confidence=0.5, computed_at=0, source="x")
    with pytest.raises(ValueError):
        TheoResult(yes_probability=-0.1, confidence=0.5, computed_at=0, source="x")


def test_theo_result_validates_confidence_range() -> None:
    with pytest.raises(ValueError):
        TheoResult(yes_probability=0.5, confidence=1.5, computed_at=0, source="x")
    with pytest.raises(ValueError):
        TheoResult(yes_probability=0.5, confidence=-0.1, computed_at=0, source="x")


def test_theo_result_yes_cents_rounding() -> None:
    r = TheoResult(yes_probability=0.234, confidence=1.0, computed_at=0, source="x")
    assert r.yes_cents == 23
    assert r.no_cents == 77

    # Boundary
    r2 = TheoResult(yes_probability=0.005, confidence=1.0, computed_at=0, source="x")
    assert r2.yes_cents == 0


def test_theo_result_extras_default_empty() -> None:
    r = TheoResult(yes_probability=0.5, confidence=1.0, computed_at=0, source="x")
    assert r.extras == {}


# ── TheoProvider protocol structural typing ────────────────────────────


def test_gbm_provider_satisfies_protocol() -> None:
    """isinstance check against runtime_checkable Protocol."""
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
    )
    provider = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (10.0, time.time()),
        vol_hook=lambda: (0.15, 5, time.time()),
    )
    assert isinstance(provider, TheoProvider)
    assert provider.series_prefix == "KXTEST"


# ── Registry routing ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_registry_routes_by_prefix() -> None:
    reg = TheoRegistry()
    cfg = GbmCommodityConfig(
        series_prefix="KXSOYBEANMON",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
    )
    provider = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    reg.register(provider)

    result = await reg.theo("KXSOYBEANMON-26APR3017-T1186.99")
    assert result.source == "GBM-commodity"
    assert 0 <= result.yes_probability <= 1


@pytest.mark.asyncio
async def test_registry_unmatched_ticker_returns_zero_confidence() -> None:
    """Unregistered series returns a result with confidence=0, not an exception."""
    reg = TheoRegistry()
    result = await reg.theo("KXUNKNOWN-26APR3017-T1186.99")
    assert result.confidence == 0.0
    assert result.source == "registry:no-provider"
    assert result.extras["prefix"] == "KXUNKNOWN"


@pytest.mark.asyncio
async def test_registry_warmup_runs_all_providers() -> None:
    reg = TheoRegistry()

    class _CountingProvider:
        series_prefix = "KX1"
        warmup_count = 0
        async def warmup(self) -> None:
            self.warmup_count += 1
        async def shutdown(self) -> None: pass
        async def theo(self, ticker: str) -> TheoResult:
            return TheoResult(yes_probability=0.5, confidence=1.0, computed_at=0, source="t")

    p = _CountingProvider()
    reg.register(p)
    await reg.warmup_all()
    assert p.warmup_count == 1


@pytest.mark.asyncio
async def test_registry_warmup_swallows_provider_errors() -> None:
    """One provider failing warmup shouldn't crash the bot startup."""
    reg = TheoRegistry()

    class _BadProvider:
        series_prefix = "KXBAD"
        async def warmup(self) -> None:
            raise RuntimeError("boom")
        async def shutdown(self) -> None: pass
        async def theo(self, ticker: str) -> TheoResult:
            return TheoResult(yes_probability=0.5, confidence=0.0, computed_at=0, source="bad")

    reg.register(_BadProvider())
    # Should not raise
    await reg.warmup_all()


# ── GBM commodity provider behavior ───────────────────────────────────


def _settle_iso_in(seconds: float) -> str:
    """Build an ISO settlement timestamp `seconds` from now (UTC)."""
    t = time.gmtime(time.time() + seconds)
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", t)


@pytest.mark.asyncio
async def test_gbm_atm_strike_yields_50pct() -> None:
    """For F=K, small tau, theo Yes ≈ 50% (only tiny drift correction)."""
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso=_settle_iso_in(86400),  # 1 day to settle
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.85, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    # Strike == forward (T1185.00 → $11.85)
    result = await p.theo("KXTEST-99JAN01-T1185.00")
    assert 0.40 <= result.yes_probability <= 0.55


@pytest.mark.asyncio
async def test_gbm_deep_otm_yields_low_probability() -> None:
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso=_settle_iso_in(86400),
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (10.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    # Strike at $20 vs forward $10 → log(0.5) far below; even at vol=16% tau=1d
    result = await p.theo("KXTEST-99JAN01-T2000.00")
    assert result.yes_probability < 0.01


@pytest.mark.asyncio
async def test_gbm_confidence_full_when_inputs_fresh() -> None:
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",  # far future → tau full
        confident_tau_hours=6.0,
        confident_vol_strikes=3,
        forward_freshness_threshold_s=120.0,
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),  # fresh now
        vol_hook=lambda: (0.16, 5, time.time()),    # 5 strikes used (>3 confident threshold)
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert result.confidence > 0.95


@pytest.mark.asyncio
async def test_gbm_confidence_drops_with_stale_forward() -> None:
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
        forward_freshness_threshold_s=120.0,
    )
    p = GbmCommodityTheo(
        cfg,
        # Forward fetched 60s ago → freshness ≈ 0.5
        forward_hook=lambda: (11.0, time.time() - 60),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert 0.4 < result.confidence < 0.6


@pytest.mark.asyncio
async def test_gbm_confidence_drops_with_sparse_vol() -> None:
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
        confident_vol_strikes=5,
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 1, time.time()),  # only 1 strike used → 1/5 = 0.2
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert result.confidence <= 0.25


@pytest.mark.asyncio
async def test_gbm_confidence_drops_near_settlement() -> None:
    """tau < confident_tau_hours scales the tau_factor down."""
    # Settlement in 1 hour → tau_factor = 1/6 ≈ 0.167
    settle_dt = time.gmtime(time.time() + 3600)
    settle_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", settle_dt)
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso=settle_iso,
        confident_tau_hours=6.0,
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert result.confidence < 0.25


@pytest.mark.asyncio
async def test_gbm_post_settlement_returns_zero_confidence() -> None:
    """Past settlement time → degenerate result, never raises."""
    settle_iso = "1970-01-01T00:00:00+00:00"  # ancient past
    cfg = GbmCommodityConfig(series_prefix="KXTEST", settlement_time_iso=settle_iso)
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert result.confidence == 0.0
    assert "post-settlement" in result.source


@pytest.mark.asyncio
async def test_gbm_bad_ticker_returns_zero_confidence() -> None:
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    result = await p.theo("malformed-ticker-without-T-strike")
    assert result.confidence == 0.0
    assert "bad-ticker" in result.source


@pytest.mark.asyncio
async def test_gbm_extras_contains_breakdown() -> None:
    """Decision-log analysis depends on extras being structured and complete."""
    cfg = GbmCommodityConfig(
        series_prefix="KXTEST",
        settlement_time_iso="2099-01-01T00:00:00+00:00",
    )
    p = GbmCommodityTheo(
        cfg,
        forward_hook=lambda: (11.0, time.time()),
        vol_hook=lambda: (0.16, 5, time.time()),
    )
    result = await p.theo("KXTEST-99JAN01-T1100.00")
    assert "strike" in result.extras
    assert "forward_dollars" in result.extras
    assert "vol" in result.extras
    assert "tau_seconds" in result.extras
    assert "d2" in result.extras
    assert "confidence_breakdown" in result.extras
    assert set(result.extras["confidence_breakdown"].keys()) == {
        "forward_freshness", "vol_quality", "tau_factor",
    }
