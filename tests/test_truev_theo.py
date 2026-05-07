"""Unit tests for TruEVTheoProvider — uses a FakeForwardSource so the
tests run offline (no yfinance dependency)."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

import pytest

from lipmm.theo.providers._truev_index import (
    DEFAULT_ANCHOR_PLACEHOLDER,
    DEFAULT_WEIGHTS_Q4_2025,
)
from lipmm.theo.providers.truev import TruEVConfig, TruEVTheoProvider


class FakeForwardSource:
    """Stand-in for TruEvForwardSource; no yfinance, fully synchronous
    state. Tests inject prices + ages directly."""

    def __init__(
        self,
        prices: dict[str, float],
        age_seconds: float = 0.0,
    ) -> None:
        now = time.time()
        ts = now - age_seconds
        self._cache: dict[str, tuple[float, float]] = {
            sym: (price, ts) for sym, price in prices.items()
        }
        self._symbols = tuple(prices.keys())
        self.started = False
        self.stopped = False

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._symbols

    def latest_prices(self) -> dict[str, tuple[float, float]]:
        return dict(self._cache)

    def oldest_age_seconds(self, *, now: float | None = None) -> float:
        if not self._cache or len(self._cache) < len(self._symbols):
            return float("inf")
        ts_now = now if now is not None else time.time()
        return max(ts_now - ts for (_p, ts) in self._cache.values())

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _future_iso(hours: float = 6.0) -> str:
    """ISO 8601 datetime N hours in the future, UTC."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_iso(hours: float = 1.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# ── Lifecycle ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warmup_starts_forward_source() -> None:
    fwd = FakeForwardSource({sym: p for sym, p in DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices.items()})
    cfg = TruEVConfig(settlement_time_iso=_future_iso(6))
    p = TruEVTheoProvider(cfg, fwd)
    await p.warmup()
    assert fwd.started is True
    await p.shutdown()
    assert fwd.stopped is True


def test_invalid_settlement_iso_raises() -> None:
    fwd = FakeForwardSource({})
    with pytest.raises(ValueError, match="ISO 8601"):
        TruEVTheoProvider(
            TruEVConfig(settlement_time_iso="not-an-iso-date"),
            fwd,
        )


# ── Strike at the index value → P ≈ 0.5 ──────────────────────────


@pytest.mark.asyncio
async def test_strike_at_index_value_yields_p_near_half() -> None:
    """When K = S exactly, with σ²τ small, P(YES_above) ≈ 0.5."""
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(3),  # 3 hours
        annualized_vol=0.30,
    )
    p = TruEVTheoProvider(cfg, fwd)
    # Anchor maps anchor_prices→anchor_index_value; strike at that value.
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value
    ticker = f"KXTRUEV-26MAY07-T{strike:.2f}"
    res = await p.theo(ticker)
    assert 0.45 < res.yes_probability < 0.55
    assert res.confidence > 0
    assert res.source == "TruEV"


@pytest.mark.asyncio
async def test_strike_far_above_yields_low_p() -> None:
    """K >> S → P(YES_above) ≈ 0."""
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(3),
        annualized_vol=0.30,
    )
    p = TruEVTheoProvider(cfg, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value * 2.0
    res = await p.theo(f"KXTRUEV-26MAY07-T{strike:.2f}")
    assert res.yes_probability < 0.05


@pytest.mark.asyncio
async def test_strike_far_below_yields_high_p() -> None:
    """K << S → P(YES_above) ≈ 1."""
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(3),
        annualized_vol=0.30,
    )
    p = TruEVTheoProvider(cfg, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value * 0.5
    res = await p.theo(f"KXTRUEV-26MAY07-T{strike:.2f}")
    assert res.yes_probability > 0.95


# ── Confidence ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confidence_capped_at_max() -> None:
    """Even with fresh forward + plenty of tau, confidence ≤ max_confidence."""
    fwd = FakeForwardSource(
        dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices),
        age_seconds=0.0,
    )
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(48),  # plenty of tau
        max_confidence=0.7,
    )
    p = TruEVTheoProvider(cfg, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value
    res = await p.theo(f"KXTRUEV-26MAY07-T{strike:.2f}")
    assert res.confidence <= 0.7
    assert res.confidence > 0.6


@pytest.mark.asyncio
async def test_confidence_drops_with_stale_forward() -> None:
    """Forward older than threshold → confidence ≈ 0."""
    fwd = FakeForwardSource(
        dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices),
        age_seconds=10_000.0,  # way past 300s threshold
    )
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(6),
        forward_freshness_threshold_s=300.0,
    )
    p = TruEVTheoProvider(cfg, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value
    res = await p.theo(f"KXTRUEV-26MAY07-T{strike:.2f}")
    assert res.confidence == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_confidence_drops_with_low_tau() -> None:
    """As tau approaches zero, confidence approaches zero."""
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(
        settlement_time_iso=_future_iso(0.05),  # ~3 minutes
        confident_tau_hours=6.0,
    )
    p = TruEVTheoProvider(cfg, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value
    res = await p.theo(f"KXTRUEV-26MAY07-T{strike:.2f}")
    # tau_factor ≈ 0.05 / 6 ≈ 0.008; confidence ≈ 0.008
    assert res.confidence < 0.05


# ── Degenerate paths ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_settle_returns_zero_confidence() -> None:
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(settlement_time_iso=_past_iso(1.0))
    p = TruEVTheoProvider(cfg, fwd)
    res = await p.theo("KXTRUEV-26MAY07-T1290.00")
    assert res.confidence == 0.0
    assert "post-settle" in res.source


@pytest.mark.asyncio
async def test_bad_ticker_returns_zero_confidence() -> None:
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(settlement_time_iso=_future_iso(6))
    p = TruEVTheoProvider(cfg, fwd)
    res = await p.theo("KXTRUEV-26MAY07-NOSTRIKE")
    assert res.confidence == 0.0
    assert "bad-ticker" in res.source


@pytest.mark.asyncio
async def test_missing_forward_symbol_returns_zero_confidence() -> None:
    """Forward source missing one of the modeled commodities → skip."""
    partial = dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices)
    partial.pop("HG=F")  # drop copper
    fwd = FakeForwardSource(partial)
    cfg = TruEVConfig(settlement_time_iso=_future_iso(6))
    p = TruEVTheoProvider(cfg, fwd)
    res = await p.theo("KXTRUEV-26MAY07-T1290.00")
    assert res.confidence == 0.0
    assert "forward-incomplete" in res.source
    assert "HG=F" in res.extras["missing_symbols"]


# ── Direction inversion ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_below_direction_inverts_probability() -> None:
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg_above = TruEVConfig(settlement_time_iso=_future_iso(3), direction="above")
    cfg_below = TruEVConfig(settlement_time_iso=_future_iso(3), direction="below")
    p_above = TruEVTheoProvider(cfg_above, fwd)
    p_below = TruEVTheoProvider(cfg_below, fwd)
    strike = DEFAULT_ANCHOR_PLACEHOLDER.anchor_index_value * 1.05  # above index
    ticker = f"KXTRUEV-26MAY07-T{strike:.2f}"
    res_a = await p_above.theo(ticker)
    res_b = await p_below.theo(ticker)
    # P(above) + P(below) = 1
    assert res_a.yes_probability + res_b.yes_probability == pytest.approx(1.0, abs=1e-9)
    # And P(above) < 0.5 since strike > S
    assert res_a.yes_probability < 0.5


# ── Extras payload ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extras_includes_diagnostics() -> None:
    fwd = FakeForwardSource(dict(DEFAULT_ANCHOR_PLACEHOLDER.anchor_prices))
    cfg = TruEVConfig(settlement_time_iso=_future_iso(6))
    p = TruEVTheoProvider(cfg, fwd)
    res = await p.theo("KXTRUEV-26MAY07-T1290.00")
    e = res.extras
    assert "model_index" in e
    assert "anchor_index" in e
    assert "anchor_date" in e
    assert "current_prices" in e
    assert "tau_seconds" in e
    assert "sigma" in e
    assert "d2" in e
    assert "confidence_breakdown" in e
    assert set(e["confidence_breakdown"].keys()) == {
        "forward_freshness", "tau_factor", "max_cap"
    }
