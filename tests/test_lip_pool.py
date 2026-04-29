"""Tests for LIP pool data ingest (ACT-LIP-POOL).

Covers:
  - LIPRewardPeriod data model creation and validation
  - DuckDB persistence (write + read back)
  - Upsert semantics (new period added, existing period updated)
  - Expired period detection (mark_expired)
  - Config-based fallback loading
  - Missing data handling (fail-loud)
  - API data parsing
  - Refresh orchestrator logic
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from feeds.kalshi.lip_pool import (
    LIPPoolDataError,
    LIPPoolStore,
    LIPRewardPeriod,
    load_config_pools,
    parse_api_lip_data,
    refresh_lip_pools,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def sample_period(now: datetime) -> LIPRewardPeriod:
    return LIPRewardPeriod(
        market_ticker="KXSOYBEANW-26APR27-17",
        pool_size_usd=250.00,
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 27),
        active=True,
        source="config",
        captured_at=now,
    )


@pytest.fixture()
def store() -> LIPPoolStore:
    """Create an in-memory DuckDB LIPPoolStore."""
    s = LIPPoolStore(db_path=":memory:")
    yield s
    s.close()


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    return tmp_path


# ── Data model tests ──────────────────────────────────────────────────


class TestLIPRewardPeriod:
    """Test LIPRewardPeriod dataclass creation and validation."""

    def test_valid_creation(self, sample_period: LIPRewardPeriod) -> None:
        assert sample_period.market_ticker == "KXSOYBEANW-26APR27-17"
        assert sample_period.pool_size_usd == 250.00
        assert sample_period.active is True
        assert sample_period.source == "config"

    def test_empty_ticker_raises(self, now: datetime) -> None:
        with pytest.raises(ValueError, match="market_ticker must be non-empty"):
            LIPRewardPeriod(
                market_ticker="",
                pool_size_usd=100.0,
                start_date=date(2026, 4, 20),
                end_date=date(2026, 4, 27),
                active=True,
                source="config",
                captured_at=now,
            )

    def test_negative_pool_size_raises(self, now: datetime) -> None:
        with pytest.raises(ValueError, match="pool_size_usd must be non-negative"):
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=-10.0,
                start_date=date(2026, 4, 20),
                end_date=date(2026, 4, 27),
                active=True,
                source="config",
                captured_at=now,
            )

    def test_end_before_start_raises(self, now: datetime) -> None:
        with pytest.raises(ValueError, match="end_date .* must be >= start_date"):
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=100.0,
                start_date=date(2026, 4, 27),
                end_date=date(2026, 4, 20),
                active=True,
                source="config",
                captured_at=now,
            )

    def test_invalid_source_raises(self, now: datetime) -> None:
        with pytest.raises(ValueError, match="source must be"):
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=100.0,
                start_date=date(2026, 4, 20),
                end_date=date(2026, 4, 27),
                active=True,
                source="unknown",
                captured_at=now,
            )

    def test_zero_pool_size_ok(self, now: datetime) -> None:
        """Zero pool size is valid (market with no reward)."""
        p = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-17",
            pool_size_usd=0.0,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 27),
            active=True,
            source="manual",
            captured_at=now,
        )
        assert p.pool_size_usd == 0.0

    def test_frozen(self, sample_period: LIPRewardPeriod) -> None:
        """LIPRewardPeriod is immutable."""
        with pytest.raises(AttributeError):
            sample_period.pool_size_usd = 999.0  # type: ignore[misc]


# ── DuckDB persistence tests ─────────────────────────────────────────


class TestLIPPoolStore:
    """Test DuckDB-backed LIPPoolStore."""

    def test_upsert_and_read_back(
        self, store: LIPPoolStore, sample_period: LIPRewardPeriod
    ) -> None:
        store.upsert(sample_period)
        assert store.count() == 1

        periods = store.get_all_periods()
        assert len(periods) == 1
        p = periods[0]
        assert p.market_ticker == sample_period.market_ticker
        assert p.pool_size_usd == sample_period.pool_size_usd
        assert p.start_date == sample_period.start_date
        assert p.end_date == sample_period.end_date
        assert p.active is True
        assert p.source == "config"

    def test_upsert_updates_existing(
        self, store: LIPPoolStore, now: datetime
    ) -> None:
        """Upserting with same key (ticker+dates) updates the record."""
        period_v1 = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-17",
            pool_size_usd=200.00,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 27),
            active=True,
            source="config",
            captured_at=now,
        )
        store.upsert(period_v1)
        assert store.count() == 1

        period_v2 = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-17",
            pool_size_usd=300.00,  # updated pool size
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 27),
            active=True,
            source="api",
            captured_at=now,
        )
        store.upsert(period_v2)
        assert store.count() == 1  # still one record

        periods = store.get_all_periods()
        assert periods[0].pool_size_usd == 300.00
        assert periods[0].source == "api"

    def test_multiple_markets(self, store: LIPPoolStore, now: datetime) -> None:
        for i, ticker in enumerate(["KXSOYBEANW-26APR27-17", "KXSOYBEANW-26APR27-18"]):
            store.upsert(
                LIPRewardPeriod(
                    market_ticker=ticker,
                    pool_size_usd=100.0 + i * 50,
                    start_date=date(2026, 4, 20),
                    end_date=date(2026, 4, 27),
                    active=True,
                    source="config",
                    captured_at=now,
                )
            )
        assert store.count() == 2
        assert store.total_active_pool_usd() == 250.0

    def test_get_active_periods(self, store: LIPPoolStore, now: datetime) -> None:
        active = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-17",
            pool_size_usd=200.00,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 27),
            active=True,
            source="config",
            captured_at=now,
        )
        inactive = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-18",
            pool_size_usd=100.00,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 10),
            active=False,
            source="config",
            captured_at=now,
        )
        store.upsert(active)
        store.upsert(inactive)

        active_periods = store.get_active_periods()
        assert len(active_periods) == 1
        assert active_periods[0].market_ticker == "KXSOYBEANW-26APR27-17"

    def test_get_periods_for_market(
        self, store: LIPPoolStore, now: datetime
    ) -> None:
        for i in range(3):
            store.upsert(
                LIPRewardPeriod(
                    market_ticker="KXSOYBEANW-26APR27-17",
                    pool_size_usd=100.0 * (i + 1),
                    start_date=date(2026, 4, 1 + i * 7),
                    end_date=date(2026, 4, 7 + i * 7),
                    active=i == 2,
                    source="config",
                    captured_at=now,
                )
            )
        periods = store.get_periods_for_market("KXSOYBEANW-26APR27-17")
        assert len(periods) == 3

    def test_mark_expired(self, store: LIPPoolStore, now: datetime) -> None:
        """Periods past end_date are marked inactive."""
        past = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-17",
            pool_size_usd=200.00,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 15),
            active=True,
            source="config",
            captured_at=now,
        )
        future = LIPRewardPeriod(
            market_ticker="KXSOYBEANW-26APR27-18",
            pool_size_usd=300.00,
            start_date=date(2026, 4, 20),
            end_date=date(2026, 5, 20),
            active=True,
            source="config",
            captured_at=now,
        )
        store.upsert(past)
        store.upsert(future)

        # Mark expired as of today (2026-04-27)
        store.mark_expired(as_of=date(2026, 4, 27))

        active = store.get_active_periods()
        assert len(active) == 1
        assert active[0].market_ticker == "KXSOYBEANW-26APR27-18"

        all_periods = store.get_all_periods()
        past_period = [p for p in all_periods if p.market_ticker == "KXSOYBEANW-26APR27-17"][0]
        assert past_period.active is False

    def test_total_active_pool_usd_empty(self, store: LIPPoolStore) -> None:
        assert store.total_active_pool_usd() == 0.0

    def test_file_backed_store(self, now: datetime, tmp_path: Path) -> None:
        """Store persists to file and can be reopened."""
        db_file = str(tmp_path / "lip_pool.duckdb")
        s1 = LIPPoolStore(db_path=db_file)
        s1.upsert(
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=250.00,
                start_date=date(2026, 4, 20),
                end_date=date(2026, 4, 27),
                active=True,
                source="config",
                captured_at=now,
            )
        )
        s1.close()

        s2 = LIPPoolStore(db_path=db_file)
        assert s2.count() == 1
        periods = s2.get_all_periods()
        assert periods[0].pool_size_usd == 250.00
        s2.close()


# ── Config loader tests ───────────────────────────────────────────────


class TestConfigLoader:
    """Test loading LIP pool data from YAML config."""

    def test_load_valid_config(self, config_dir: Path) -> None:
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text(
            "pools:\n"
            '  - market_ticker: "KXSOYBEANW-26APR27-17"\n'
            "    pool_size_usd: 250.00\n"
            '    start_date: "2026-04-20"\n'
            '    end_date: "2026-04-27"\n'
            '  - market_ticker: "KXSOYBEANW-26APR27-18"\n'
            "    pool_size_usd: 150.00\n"
            '    start_date: "2026-04-20"\n'
            '    end_date: "2026-04-27"\n'
        )
        periods = load_config_pools(config_file)
        assert len(periods) == 2
        assert periods[0].market_ticker == "KXSOYBEANW-26APR27-17"
        assert periods[0].pool_size_usd == 250.00
        assert periods[0].source == "config"
        assert periods[1].pool_size_usd == 150.00

    def test_missing_config_raises(self, config_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config_pools(config_dir / "nonexistent.yaml")

    def test_malformed_config_raises(self, config_dir: Path) -> None:
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text("not_pools: true\n")
        with pytest.raises(LIPPoolDataError, match="must contain a 'pools' key"):
            load_config_pools(config_file)

    def test_missing_field_raises(self, config_dir: Path) -> None:
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text(
            "pools:\n"
            '  - market_ticker: "KXSOYBEANW-26APR27-17"\n'
            "    pool_size_usd: 250.00\n"
            # missing start_date and end_date
        )
        with pytest.raises(LIPPoolDataError, match="Invalid pool entry"):
            load_config_pools(config_file)

    def test_pools_not_list_raises(self, config_dir: Path) -> None:
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text("pools: not_a_list\n")
        with pytest.raises(LIPPoolDataError, match="must be a list"):
            load_config_pools(config_file)


# ── API parser tests ──────────────────────────────────────────────────


class TestAPIParser:
    """Test parsing LIP data from Kalshi API responses."""

    def test_no_lip_data_returns_none(self) -> None:
        market_data = {"ticker": "KXSOYBEANW-26APR27-17", "status": "open"}
        result = parse_api_lip_data("KXSOYBEANW-26APR27-17", market_data)
        assert result is None

    def test_lip_data_in_nested_field(self) -> None:
        market_data = {
            "ticker": "KXSOYBEANW-26APR27-17",
            "liquidity_incentive": {
                "pool_size_usd": 250.0,
                "start_date": "2026-04-20",
                "end_date": "2026-04-27",
            },
        }
        result = parse_api_lip_data("KXSOYBEANW-26APR27-17", market_data)
        assert result is not None
        assert result.pool_size_usd == 250.0
        assert result.source == "api"

    def test_lip_data_in_top_level_fields(self) -> None:
        market_data = {
            "ticker": "KXSOYBEANW-26APR27-17",
            "pool_size": 300.0,
            "reward_start_date": "2026-04-20",
            "reward_end_date": "2026-04-27",
        }
        result = parse_api_lip_data("KXSOYBEANW-26APR27-17", market_data)
        assert result is not None
        assert result.pool_size_usd == 300.0

    def test_malformed_lip_data_raises(self) -> None:
        market_data = {
            "ticker": "KXSOYBEANW-26APR27-17",
            "liquidity_incentive": {
                "pool_size_usd": "not_a_number",
                "start_date": "2026-04-20",
                "end_date": "2026-04-27",
            },
        }
        with pytest.raises(LIPPoolDataError, match="Malformed LIP data"):
            parse_api_lip_data("KXSOYBEANW-26APR27-17", market_data)

    def test_lip_data_non_dict_raises(self) -> None:
        market_data = {
            "ticker": "KXSOYBEANW-26APR27-17",
            "liquidity_incentive": "invalid",
        }
        with pytest.raises(LIPPoolDataError, match="must be a dict"):
            parse_api_lip_data("KXSOYBEANW-26APR27-17", market_data)


# ── Refresh orchestrator tests ────────────────────────────────────────


class TestRefreshLipPools:
    """Test the refresh_lip_pools async orchestrator."""

    def test_refresh_from_config(
        self, store: LIPPoolStore, config_dir: Path
    ) -> None:
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text(
            "pools:\n"
            '  - market_ticker: "KXSOYBEANW-26APR27-17"\n'
            "    pool_size_usd: 250.00\n"
            '    start_date: "2026-04-20"\n'
            '    end_date: "2026-05-20"\n'
        )
        count = asyncio.get_event_loop().run_until_complete(
            refresh_lip_pools(store=store, config_path=config_file)
        )
        assert count == 1
        assert store.count() == 1

    def test_refresh_no_data_empty_store_raises(
        self, store: LIPPoolStore
    ) -> None:
        """Fail-loud when no data sources and store is empty."""
        with pytest.raises(LIPPoolDataError, match="No LIP pool data found"):
            asyncio.get_event_loop().run_until_complete(
                refresh_lip_pools(store=store)
            )

    def test_refresh_no_data_existing_store_ok(
        self, store: LIPPoolStore, now: datetime
    ) -> None:
        """If store already has data, empty refresh is OK (no new data to add)."""
        store.upsert(
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=250.00,
                start_date=date(2026, 4, 20),
                end_date=date(2026, 5, 20),
                active=True,
                source="config",
                captured_at=now,
            )
        )
        # This should not raise because store already has data
        count = asyncio.get_event_loop().run_until_complete(
            refresh_lip_pools(store=store)
        )
        assert count == 0

    def test_refresh_marks_expired(
        self, store: LIPPoolStore, now: datetime, config_dir: Path
    ) -> None:
        """Refresh marks past periods as inactive."""
        # Insert an already-expired period
        store.upsert(
            LIPRewardPeriod(
                market_ticker="KXSOYBEANW-26APR27-17",
                pool_size_usd=200.00,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 15),
                active=True,
                source="config",
                captured_at=now,
            )
        )
        # Refresh with a config that adds a new active period
        config_file = config_dir / "lip_pools.yaml"
        config_file.write_text(
            "pools:\n"
            '  - market_ticker: "KXSOYBEANW-26APR27-18"\n'
            "    pool_size_usd: 300.00\n"
            '    start_date: "2026-04-20"\n'
            '    end_date: "2026-05-20"\n'
        )
        asyncio.get_event_loop().run_until_complete(
            refresh_lip_pools(store=store, config_path=config_file)
        )

        active = store.get_active_periods()
        assert len(active) == 1
        assert active[0].market_ticker == "KXSOYBEANW-26APR27-18"
