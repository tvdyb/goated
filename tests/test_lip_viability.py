"""Tests for ACT-LIP-VIAB -- LIP viability analysis framework.

Uses synthetic DuckDB data to verify all analysis pipeline stages.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone

import duckdb
import pytest

from analysis.lip_viability import (
    CompetitionEstimate,
    DailyPoolTotal,
    InsufficientDataError,
    LIPViabilityAnalyzer,
    RevenueProjection,
    ScoreSimulation,
    ViabilityConfig,
    ViabilityReport,
    _compute_visible_score,
    _parse_levels_json,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _create_capture_db(path: str, days: int = 5, markets: int = 3) -> None:
    """Create a synthetic capture DuckDB with orderbook snapshots."""
    conn = duckdb.connect(path)
    conn.execute("SET TimeZone='UTC'")

    conn.execute("""
        CREATE TABLE orderbook_snapshots (
            ticker VARCHAR NOT NULL,
            captured_at TIMESTAMP WITH TIME ZONE NOT NULL,
            yes_levels VARCHAR NOT NULL,
            no_levels VARCHAR NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE trades (
            ticker VARCHAR NOT NULL,
            trade_id VARCHAR NOT NULL,
            count INTEGER NOT NULL,
            yes_price_cents INTEGER NOT NULL,
            taker_side VARCHAR NOT NULL,
            created_time TIMESTAMP WITH TIME ZONE NOT NULL,
            UNIQUE (trade_id)
        )
    """)

    conn.execute("""
        CREATE TABLE market_events (
            ticker VARCHAR NOT NULL,
            event_ticker VARCHAR NOT NULL,
            title VARCHAR,
            status VARCHAR NOT NULL,
            yes_bid_cents INTEGER,
            yes_ask_cents INTEGER,
            last_price_cents INTEGER,
            volume INTEGER,
            open_interest INTEGER,
            result VARCHAR,
            floor_strike DOUBLE,
            cap_strike DOUBLE,
            captured_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)

    base = date(2026, 4, 20)
    for d in range(days):
        dt = base + __import__("datetime").timedelta(days=d)
        ts = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=timezone.utc)

        for m in range(markets):
            ticker = f"KXSOYBEANW-26APR27-{17 + m}"

            # Synthetic orderbook: 3 yes levels, 3 no levels
            # Best bid at 50c, levels at 49c, 48c
            # Best no at 52c, levels at 51c, 50c
            yes_levels = json.dumps([[50, 100], [49, 80], [48, 60]])
            no_levels = json.dumps([[52, 90], [51, 70], [50, 50]])

            conn.execute(
                "INSERT INTO orderbook_snapshots VALUES (?, ?, ?, ?)",
                [ticker, ts, yes_levels, no_levels],
            )

    conn.close()


def _create_pool_db(
    path: str,
    pool_size: float = 200.0,
    markets: int = 3,
    days: int = 5,
) -> None:
    """Create a synthetic LIP pool DuckDB."""
    conn = duckdb.connect(path)
    conn.execute("SET TimeZone='UTC'")

    conn.execute("""
        CREATE TABLE lip_reward_periods (
            market_ticker VARCHAR NOT NULL,
            pool_size_usd DOUBLE NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            active BOOLEAN NOT NULL,
            source VARCHAR NOT NULL,
            captured_at TIMESTAMP NOT NULL,
            UNIQUE (market_ticker, start_date, end_date)
        )
    """)

    base = date(2026, 4, 20)
    now = datetime(2026, 4, 27, 0, 0, 0)
    for d in range(days):
        start = base + __import__("datetime").timedelta(days=d)
        end = start + __import__("datetime").timedelta(days=6)
        for m in range(markets):
            ticker = f"KXSOYBEANW-26APR27-{17 + m}"
            conn.execute(
                "INSERT INTO lip_reward_periods VALUES (?, ?, ?, ?, ?, ?, ?)",
                [ticker, pool_size / markets, start, end, True, "config", now],
            )

    conn.close()


@pytest.fixture
def capture_db(tmp_path):
    """Create a temporary capture database."""
    path = str(tmp_path / "capture.duckdb")
    _create_capture_db(path)
    return path


@pytest.fixture
def pool_db(tmp_path):
    """Create a temporary pool database."""
    path = str(tmp_path / "pool.duckdb")
    _create_pool_db(path)
    return path


@pytest.fixture
def analyzer(capture_db, pool_db):
    """Create an analyzer with default config."""
    a = LIPViabilityAnalyzer(capture_db, pool_db)
    yield a
    a.close()


# ── Unit tests: helper functions ──────────────────────────────────────


class TestParseLevelsJson:
    def test_valid_json(self) -> None:
        raw = json.dumps([[50, 100], [49, 80]])
        levels = _parse_levels_json(raw)
        assert levels == [(50, 100.0), (49, 80.0)]

    def test_empty_string(self) -> None:
        assert _parse_levels_json("") == []

    def test_invalid_json(self) -> None:
        assert _parse_levels_json("not-json") == []

    def test_filters_zero_size(self) -> None:
        raw = json.dumps([[50, 100], [49, 0], [48, 60]])
        levels = _parse_levels_json(raw)
        assert len(levels) == 2
        assert levels[0] == (50, 100.0)
        assert levels[1] == (48, 60.0)


class TestComputeVisibleScore:
    def test_single_level_each_side(self) -> None:
        yes = [(50, 100.0)]
        no = [(52, 90.0)]
        score = _compute_visible_score(yes, no, decay_ticks=5)
        # Both at best -> mult = 1.0 each
        assert score == pytest.approx(190.0)

    def test_multiple_levels_with_decay(self) -> None:
        # Best bid at 50, level at 49 -> dist=1, mult=0.8 (decay=5)
        yes = [(50, 100.0), (49, 100.0)]
        no: list[tuple[int, float]] = []
        score = _compute_visible_score(yes, no, decay_ticks=5)
        # 100*1.0 + 100*0.8 = 180
        assert score == pytest.approx(180.0)

    def test_beyond_decay_zero_score(self) -> None:
        # Best at 50, level at 44 -> dist=6 >= 5 -> mult=0.0
        yes = [(50, 100.0), (44, 200.0)]
        no: list[tuple[int, float]] = []
        score = _compute_visible_score(yes, no, decay_ticks=5)
        # 100*1.0 + 200*0.0 = 100
        assert score == pytest.approx(100.0)

    def test_empty_book(self) -> None:
        score = _compute_visible_score([], [], decay_ticks=5)
        assert score == 0.0


# ── Integration tests: pipeline stages ────────────────────────────────


class TestDataSufficiency:
    def test_sufficient_data(self, capture_db, pool_db) -> None:
        a = LIPViabilityAnalyzer(capture_db, pool_db)
        start, end, days = a._check_data_sufficiency()
        assert days >= 3
        a.close()

    def test_insufficient_data(self, tmp_path) -> None:
        """Less than 3 days -> raises InsufficientDataError."""
        path = str(tmp_path / "sparse_capture.duckdb")
        _create_capture_db(path, days=2)
        pool_path = str(tmp_path / "pool2.duckdb")
        _create_pool_db(pool_path)
        a = LIPViabilityAnalyzer(path, pool_path)
        with pytest.raises(InsufficientDataError, match="Only 2 day"):
            a._check_data_sufficiency()
        a.close()

    def test_empty_db(self, tmp_path) -> None:
        """Empty database -> raises InsufficientDataError."""
        path = str(tmp_path / "empty.duckdb")
        _create_capture_db(path, days=0)
        pool_path = str(tmp_path / "pool_empty.duckdb")
        _create_pool_db(pool_path)
        a = LIPViabilityAnalyzer(path, pool_path)
        with pytest.raises(InsufficientDataError, match="No orderbook"):
            a._check_data_sufficiency()
        a.close()


class TestDailyPoolTotals:
    def test_pool_totals_computed(self, analyzer) -> None:
        totals = analyzer._compute_daily_pool_totals()
        assert len(totals) > 0
        for t in totals:
            assert isinstance(t, DailyPoolTotal)
            assert t.total_pool_usd > 0
            assert t.market_count > 0


class TestCompetitionEstimate:
    def test_competition_estimated(self, analyzer) -> None:
        estimates = analyzer._estimate_competition()
        assert len(estimates) > 0
        for e in estimates:
            assert isinstance(e, CompetitionEstimate)
            # 3 yes levels + 3 no levels = 6 per snapshot
            assert e.avg_distinct_levels_per_market == pytest.approx(6.0)
            assert e.snapshot_count > 0


class TestScoreSimulation:
    def test_score_simulation(self, analyzer) -> None:
        scores = analyzer._simulate_score_at_full_presence()
        assert len(scores) > 0
        for s in scores:
            assert isinstance(s, ScoreSimulation)
            assert s.our_simulated_score > 0
            assert s.total_visible_score > 0
            assert 0 < s.projected_share_pct < 100

    def test_full_presence_increases_share(self, capture_db, pool_db) -> None:
        """Larger target_size_multiplier => higher share."""
        config_low = ViabilityConfig(target_size_multiplier=1.0)
        config_high = ViabilityConfig(target_size_multiplier=3.0)

        a_low = LIPViabilityAnalyzer(capture_db, pool_db, config_low)
        a_high = LIPViabilityAnalyzer(capture_db, pool_db, config_high)

        scores_low = a_low._simulate_score_at_full_presence()
        scores_high = a_high._simulate_score_at_full_presence()

        avg_low = sum(s.projected_share_pct for s in scores_low) / len(scores_low)
        avg_high = sum(s.projected_share_pct for s in scores_high) / len(scores_high)

        assert avg_high > avg_low

        a_low.close()
        a_high.close()


class TestRevenueProjection:
    def test_revenue_with_fees_and_hedge(self, analyzer) -> None:
        rev = analyzer._project_revenue(avg_daily_pool_usd=500.0, avg_share_pct=20.0)
        assert isinstance(rev, RevenueProjection)
        # Gross = 500 * 0.20 = 100
        assert rev.daily_gross_usd == pytest.approx(100.0)
        # Fees > 0
        assert rev.daily_fees_usd > 0
        # Hedge cost = $5 default
        assert rev.daily_hedge_cost_usd == pytest.approx(5.0)
        # Net = gross - fees - hedge
        assert rev.daily_net_usd == pytest.approx(
            rev.daily_gross_usd - rev.daily_fees_usd - rev.daily_hedge_cost_usd
        )
        # Weekly = 7 * daily
        assert rev.weekly_net_usd == pytest.approx(rev.daily_net_usd * 7)
        # Monthly = 30 * daily
        assert rev.monthly_net_usd == pytest.approx(rev.daily_net_usd * 30)


# ── Go/no-go threshold tests ─────────────────────────────────────────


class TestGoNoGo:
    def test_go_with_large_pool(self, tmp_path) -> None:
        """Large pool + low competition -> GO."""
        cap_path = str(tmp_path / "cap_go.duckdb")
        pool_path = str(tmp_path / "pool_go.duckdb")
        # Minimal orderbook (small competition), large pool
        _create_capture_db(cap_path, days=5, markets=2)
        _create_pool_db(pool_path, pool_size=1000.0, markets=2, days=5)

        config = ViabilityConfig(
            revenue_threshold_per_day_usd=10.0,
            share_threshold_pct=1.0,
        )
        a = LIPViabilityAnalyzer(cap_path, pool_path, config)
        report = a.run()
        a.close()

        assert isinstance(report, ViabilityReport)
        assert report.go is True
        assert len(report.kill_criteria_triggered) == 0
        assert "GO" in report.recommendation

    def test_nogo_pool_too_small(self, tmp_path) -> None:
        """Tiny pool -> NO-GO (KC-LIP-01)."""
        cap_path = str(tmp_path / "cap_nogo.duckdb")
        pool_path = str(tmp_path / "pool_nogo.duckdb")
        _create_capture_db(cap_path, days=5, markets=2)
        _create_pool_db(pool_path, pool_size=5.0, markets=2, days=5)

        config = ViabilityConfig(
            revenue_threshold_per_day_usd=50.0,
            share_threshold_pct=1.0,
        )
        a = LIPViabilityAnalyzer(cap_path, pool_path, config)
        report = a.run()
        a.close()

        assert report.go is False
        assert any("KC-LIP-01" in k for k in report.kill_criteria_triggered)
        assert "NO-GO" in report.recommendation

    def test_nogo_competition_too_dense(self, tmp_path) -> None:
        """High share threshold -> NO-GO (KC-LIP-02)."""
        cap_path = str(tmp_path / "cap_dense.duckdb")
        pool_path = str(tmp_path / "pool_dense.duckdb")
        _create_capture_db(cap_path, days=5, markets=2)
        _create_pool_db(pool_path, pool_size=1000.0, markets=2, days=5)

        config = ViabilityConfig(
            revenue_threshold_per_day_usd=1.0,
            share_threshold_pct=99.0,  # impossibly high
        )
        a = LIPViabilityAnalyzer(cap_path, pool_path, config)
        report = a.run()
        a.close()

        assert report.go is False
        assert any("KC-LIP-02" in k for k in report.kill_criteria_triggered)

    def test_insufficient_data_raises(self, tmp_path) -> None:
        """Run with < 3 days -> InsufficientDataError."""
        cap_path = str(tmp_path / "cap_short.duckdb")
        pool_path = str(tmp_path / "pool_short.duckdb")
        _create_capture_db(cap_path, days=2)
        _create_pool_db(pool_path)

        a = LIPViabilityAnalyzer(cap_path, pool_path)
        with pytest.raises(InsufficientDataError):
            a.run()
        a.close()


class TestFullReport:
    def test_report_structure(self, capture_db, pool_db) -> None:
        """Verify all fields of ViabilityReport are populated."""
        a = LIPViabilityAnalyzer(capture_db, pool_db)
        report = a.run()
        a.close()

        assert report.days_observed >= 3
        assert report.observation_start <= report.observation_end
        assert len(report.daily_pool_totals) > 0
        assert report.avg_daily_pool_usd >= 0
        assert len(report.competition_estimates) > 0
        assert report.avg_distinct_levels >= 0
        assert len(report.score_simulations) > 0
        assert report.avg_projected_share_pct >= 0
        assert isinstance(report.revenue, RevenueProjection)
        assert isinstance(report.go, bool)
        assert isinstance(report.recommendation, str)
        assert len(report.recommendation) > 0
