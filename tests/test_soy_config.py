"""ACT-02: verify soy config in commodities.yaml is fully populated.

Tests that:
1. Registry loads soy as a configured (non-stub) commodity.
2. All required fields are present in the raw config.
3. Pyth feeds config has a soy entry.
4. Soy model builds successfully (GBMTheo instance).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from models.registry import Registry

CONFIG = Path(__file__).resolve().parents[1] / "config" / "commodities.yaml"
PYTH_FEEDS = Path(__file__).resolve().parents[1] / "config" / "pyth_feeds.yaml"


@pytest.fixture
def registry() -> Registry:
    return Registry(CONFIG)


class TestSoyCommoditiesYaml:
    def test_soy_is_not_stub(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        assert not cfg.is_stub, "soy should not be a stub"

    def test_soy_model_is_gbm(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        assert cfg.model_name == "gbm"

    def test_soy_theo_instance_exists(self, registry: Registry) -> None:
        theo = registry.get("soy")
        assert theo is not None

    def test_soy_in_configured_commodities(self, registry: Registry) -> None:
        assert "soy" in registry.commodities(configured_only=True)

    def test_soy_has_cme_symbol(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        assert cfg.raw.get("cme_symbol") == "ZS"

    def test_soy_has_pyth_feed_id(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        feed_id = cfg.raw.get("pyth_feed_id")
        assert feed_id is not None
        assert feed_id.startswith("0x")
        assert len(feed_id) == 66  # 0x + 64 hex chars

    def test_soy_has_kalshi_block(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        kalshi = cfg.raw.get("kalshi")
        assert kalshi is not None
        assert kalshi["series"] == "KXSOYBEANW"
        assert "bucket_grid_source" in kalshi
        assert "trading_hours" in kalshi
        assert "reference_price_mode" in kalshi

    def test_soy_has_fee_schedule(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        fees = cfg.raw.get("fees")
        assert fees is not None
        assert "taker_formula" in fees
        assert fees["maker_fraction"] == 0.25

    def test_soy_has_position_cap(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        cap = cfg.raw.get("position_cap")
        assert cap is not None
        assert cap["max_loss_dollars"] == 25000

    def test_soy_has_event_calendar(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        events = cfg.raw.get("event_calendar")
        assert events is not None
        assert len(events) >= 3
        event_names = {e["name"] for e in events}
        assert "WASDE" in event_names
        assert "Crop_Progress" in event_names

    def test_soy_has_cme_contract_cycle(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        cycle = cfg.raw.get("cme_contract_cycle")
        assert cycle == "F/H/K/N/Q/U/X"

    def test_soy_has_trading_hours(self, registry: Registry) -> None:
        cfg = registry.config("soy")
        hours = cfg.raw.get("trading_hours")
        assert hours is not None
        assert "cbot_session" in hours
        assert "kalshi_session" in hours
        assert hours["kalshi_session"] == "24_7"


class TestPythFeedsYaml:
    def test_soy_in_pyth_feeds(self) -> None:
        with PYTH_FEEDS.open() as f:
            doc = yaml.safe_load(f)
        feeds = doc.get("feeds", {})
        assert "soy" in feeds
        soy = feeds["soy"]
        assert soy["feed_id"].startswith("0x")
        assert "SO" in soy["symbol"]  # e.g. Commodities.SON6/USD
        assert soy["expected_publishers_floor"] >= 1
        assert soy["max_staleness_ms"] > 0
