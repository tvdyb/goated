"""Tests for the TheoNotebook registry + TruEVNotebook rendering."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lipmm.control.notebooks import NotebookRegistry, TheoNotebook
from lipmm.theo.providers import (
    DEFAULT_WEIGHTS_LIVE,
    TruEvAnchor,
    TruEVConfig,
    TruEVNotebook,
    TruEVTheoProvider,
)


# ── NotebookRegistry ─────────────────────────────────────────────────


class _StubNotebook:
    """Minimal TheoNotebook implementation for registry tests."""

    def __init__(self, key: str, label: str, body: str = "<div>stub</div>") -> None:
        self.key = key
        self.label = label
        self._body = body

    async def render(self) -> str:
        return self._body


def test_registry_starts_empty() -> None:
    reg = NotebookRegistry()
    assert len(reg) == 0
    assert reg.list() == []
    assert reg.get("missing") is None


def test_registry_register_and_lookup() -> None:
    reg = NotebookRegistry()
    nb = _StubNotebook("truev", "TruEV basket")
    reg.register(nb)
    assert len(reg) == 1
    assert reg.get("truev") is nb
    assert reg.list() == [("truev", "TruEV basket")]


def test_registry_preserves_insertion_order() -> None:
    reg = NotebookRegistry()
    reg.register(_StubNotebook("a", "A"))
    reg.register(_StubNotebook("b", "B"))
    reg.register(_StubNotebook("c", "C"))
    assert reg.list() == [("a", "A"), ("b", "B"), ("c", "C")]


def test_registry_rejects_duplicate_key() -> None:
    reg = NotebookRegistry()
    reg.register(_StubNotebook("truev", "TruEV"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_StubNotebook("truev", "TruEV again"))


def test_registry_rejects_empty_key() -> None:
    reg = NotebookRegistry()
    with pytest.raises(ValueError, match="non-empty"):
        reg.register(_StubNotebook("", "empty"))


def test_stub_satisfies_protocol() -> None:
    """isinstance-with-Protocol check (Protocol is @runtime_checkable)."""
    assert isinstance(_StubNotebook("k", "L"), TheoNotebook)


# ── TruEVNotebook ────────────────────────────────────────────────────


class _StubForwardSource:
    """Forward-source double exposing the two methods TruEVNotebook needs."""

    def __init__(self, prices: dict[str, tuple[float, float]]) -> None:
        self._prices = prices

    def latest_prices(self) -> dict[str, tuple[float, float]]:
        return dict(self._prices)

    def oldest_age_seconds(self, *, now: float | None = None) -> float:
        if not self._prices:
            return float("inf")
        if now is None:
            import time
            now = time.time()
        return max(now - ts for (_p, ts) in self._prices.values())


def _make_provider(prices: dict[str, tuple[float, float]]) -> TruEVTheoProvider:
    """Build a TruEVTheoProvider with stubbed forward source."""
    anchor = TruEvAnchor(
        anchor_date="2026-05-12",
        anchor_index_value=1313.23,
        anchor_prices={
            "HG=F":       6.6505,
            "NICKEL_TE":  18990.0,
            "COBALT_TE":  56290.0,
            "PA=F":       1506.0,
            "LITHIUM_TE": 195250.0,
            "PL=F":       2127.10,
        },
    )
    cfg = TruEVConfig(
        # Far-future settlement so the provider doesn't degenerate
        settlement_time_iso=datetime(
            2099, 1, 1, tzinfo=timezone.utc
        ).isoformat(),
        weights=DEFAULT_WEIGHTS_LIVE,
        anchor=anchor,
        annualized_vol=0.15,
        max_confidence=1.0,
    )
    return TruEVTheoProvider(cfg, _StubForwardSource(prices))


@pytest.mark.asyncio
async def test_truev_notebook_render_all_components_present() -> None:
    """Render produces HTML containing each component label + the
    implied basket level when all six prices are present."""
    import time
    now = time.time()
    prices = {
        "HG=F":       (6.7000, now),
        "NICKEL_TE":  (18876.0, now),
        "COBALT_TE":  (56290.0, now),
        "PA=F":       (1510.0, now),
        "LITHIUM_TE": (200000.0, now),
        "PL=F":       (2150.0, now),
    }
    nb = TruEVNotebook(provider=_make_provider(prices))
    out = await nb.render()
    # Every component label appears
    for label in ("Copper", "Nickel", "Cobalt", "Palladium", "Lithium", "Platinum"):
        assert label in out, f"missing label {label!r}"
    # Anchor metadata appears
    assert "2026-05-12" in out
    assert "1313.23" in out
    # Implied basket section appears (we got an implied since all symbols present)
    assert "Implied basket" in out
    # Non-empty HTML response
    assert len(out) > 500


@pytest.mark.asyncio
async def test_truev_notebook_render_handles_missing_components() -> None:
    """Render gracefully reports missing components when forward source
    is incomplete — no exception, returns HTML with a placeholder."""
    import time
    nb = TruEVNotebook(provider=_make_provider({
        "HG=F": (6.7, time.time()),  # only one symbol present
    }))
    out = await nb.render()
    assert "missing" in out.lower() or "Implied basket unavailable" in out or "unavailable" in out
    # Still renders without raising
    assert "<table" in out


@pytest.mark.asyncio
async def test_truev_notebook_key_and_label_are_stable() -> None:
    """Notebook exposes constant key/label suitable for the registry."""
    nb = TruEVNotebook(provider=_make_provider({}))
    assert nb.key == "truev"
    assert nb.label == "TruEV basket"


@pytest.mark.asyncio
async def test_truev_notebook_satisfies_protocol() -> None:
    """isinstance check confirms TruEVNotebook implements TheoNotebook."""
    nb = TruEVNotebook(provider=_make_provider({}))
    assert isinstance(nb, TheoNotebook)
