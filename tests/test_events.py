"""Tests for feeds.kalshi.events -- Bucket grid + Event puller.

Covers GAP-075 (bucket-grid ingest) and GAP-079 (bucket data structures).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from feeds.kalshi.events import (
    Bucket,
    BucketGrid,
    EventPuller,
    EventSnapshot,
    build_bucket_grid,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _make_market(
    ticker: str,
    floor_strike: float | None,
    cap_strike: float | None,
    status: str = "open",
) -> dict[str, object]:
    """Build a minimal market dict matching Kalshi API shape."""
    return {
        "ticker": ticker,
        "floor_strike": floor_strike,
        "cap_strike": cap_strike,
        "status": status,
    }


def _sample_markets() -> list[dict[str, object]]:
    """Build a realistic 5-bucket soybean grid.

    Layout:
      Bucket 1: (-inf, 1020.0)   lower tail
      Bucket 2: [1020.0, 1040.0)
      Bucket 3: [1040.0, 1060.0)
      Bucket 4: [1060.0, 1080.0)
      Bucket 5: [1080.0, +inf)   upper tail
    """
    return [
        _make_market("KXSOYBEANW-26APR24-1", None, 1020.0),
        _make_market("KXSOYBEANW-26APR24-2", 1020.0, 1040.0),
        _make_market("KXSOYBEANW-26APR24-3", 1040.0, 1060.0),
        _make_market("KXSOYBEANW-26APR24-4", 1060.0, 1080.0),
        _make_market("KXSOYBEANW-26APR24-5", 1080.0, None),
    ]


def _sample_event_response() -> dict[str, object]:
    """Build a mock response from GET /events/{event_ticker}."""
    return {
        "event": {
            "event_ticker": "KXSOYBEANW-26APR24",
            "series_ticker": "KXSOYBEANW",
            "title": "Soybean Futures Weekly Apr 24",
            "status": "open",
        },
        "markets": _sample_markets(),
    }


# ── Bucket ────────────────────────────────────────────────────────────


class TestBucket:
    def test_lower_tail(self) -> None:
        b = Bucket(ticker="T-1", bucket_index=1, lower=None, upper=100.0, status="open")
        assert b.is_lower_tail
        assert not b.is_upper_tail
        assert not b.is_interior
        assert b.width is None

    def test_upper_tail(self) -> None:
        b = Bucket(ticker="T-5", bucket_index=5, lower=200.0, upper=None, status="open")
        assert not b.is_lower_tail
        assert b.is_upper_tail
        assert not b.is_interior
        assert b.width is None

    def test_interior(self) -> None:
        b = Bucket(ticker="T-3", bucket_index=3, lower=100.0, upper=120.0, status="open")
        assert not b.is_lower_tail
        assert not b.is_upper_tail
        assert b.is_interior
        assert b.width == pytest.approx(20.0)


# ── BucketGrid construction ──────────────────────────────────────────


class TestBuildBucketGrid:
    def test_valid_5_bucket_grid(self) -> None:
        markets = _sample_markets()
        grid = build_bucket_grid(markets)

        assert grid.n_buckets == 5
        assert grid.lower_tail.is_lower_tail
        assert grid.upper_tail.is_upper_tail
        assert len(grid.interior_buckets) == 3

    def test_sorted_by_lower_bound(self) -> None:
        # Provide markets in reversed order
        markets = list(reversed(_sample_markets()))
        grid = build_bucket_grid(markets)

        assert grid.buckets[0].is_lower_tail
        assert grid.buckets[-1].is_upper_tail
        for i in range(1, len(grid.buckets) - 1):
            assert grid.buckets[i].lower is not None
            if i > 1:
                prev_lower = grid.buckets[i - 1].lower
                assert prev_lower is not None
                assert grid.buckets[i].lower > prev_lower  # type: ignore[operator]

    def test_minimal_2_bucket_grid(self) -> None:
        """Lower tail + upper tail only (no interior)."""
        markets = [
            _make_market("KXSOYBEANW-26APR24-1", None, 1050.0),
            _make_market("KXSOYBEANW-26APR24-2", 1050.0, None),
        ]
        grid = build_bucket_grid(markets)
        assert grid.n_buckets == 2
        assert grid.lower_tail.upper == 1050.0
        assert grid.upper_tail.lower == 1050.0

    def test_bucket_for_price_lower_tail(self) -> None:
        grid = build_bucket_grid(_sample_markets())
        b = grid.bucket_for_price(1000.0)
        assert b.is_lower_tail

    def test_bucket_for_price_interior(self) -> None:
        grid = build_bucket_grid(_sample_markets())
        b = grid.bucket_for_price(1045.0)
        assert b.lower == 1040.0
        assert b.upper == 1060.0

    def test_bucket_for_price_upper_tail(self) -> None:
        grid = build_bucket_grid(_sample_markets())
        b = grid.bucket_for_price(1100.0)
        assert b.is_upper_tail

    def test_bucket_for_price_on_boundary(self) -> None:
        """Price exactly on a boundary belongs to the bucket starting there."""
        grid = build_bucket_grid(_sample_markets())
        b = grid.bucket_for_price(1040.0)
        assert b.lower == 1040.0
        assert b.upper == 1060.0

    def test_rejects_empty_markets(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            build_bucket_grid([])

    def test_rejects_missing_ticker(self) -> None:
        markets = [{"floor_strike": None, "cap_strike": 100.0, "status": "open"}]
        with pytest.raises(ValueError, match="ticker"):
            build_bucket_grid(markets)

    def test_rejects_missing_status(self) -> None:
        markets = [{"ticker": "KXSOYBEANW-26APR24-1", "floor_strike": None, "cap_strike": 100.0}]
        with pytest.raises(ValueError, match="status"):
            build_bucket_grid(markets)

    def test_rejects_no_lower_tail(self) -> None:
        markets = [
            _make_market("KXSOYBEANW-26APR24-1", 1000.0, 1020.0),
            _make_market("KXSOYBEANW-26APR24-2", 1020.0, None),
        ]
        with pytest.raises(ValueError, match="lower tail"):
            build_bucket_grid(markets)

    def test_rejects_no_upper_tail(self) -> None:
        markets = [
            _make_market("KXSOYBEANW-26APR24-1", None, 1020.0),
            _make_market("KXSOYBEANW-26APR24-2", 1020.0, 1040.0),
        ]
        with pytest.raises(ValueError, match="upper tail"):
            build_bucket_grid(markets)

    def test_rejects_gap_between_buckets(self) -> None:
        markets = [
            _make_market("KXSOYBEANW-26APR24-1", None, 1020.0),
            _make_market("KXSOYBEANW-26APR24-2", 1020.0, 1040.0),
            # Gap: 1040 -> 1050 missing
            _make_market("KXSOYBEANW-26APR24-3", 1050.0, None),
        ]
        with pytest.raises(ValueError, match="MECE gap"):
            build_bucket_grid(markets)

    def test_rejects_single_bucket(self) -> None:
        markets = [_make_market("KXSOYBEANW-26APR24-1", None, 1020.0)]
        with pytest.raises(ValueError, match="at least 2"):
            build_bucket_grid(markets)


# ── EventPuller ───────────────────────────────────────────────────────


class TestEventPuller:
    @pytest.fixture
    def mock_client(self) -> MagicMock:
        client = MagicMock()
        client.get_event = AsyncMock()
        client.get_events = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_pull_event(self, mock_client: MagicMock) -> None:
        mock_client.get_event.return_value = _sample_event_response()

        puller = EventPuller(mock_client)
        snap = await puller.pull_event("KXSOYBEANW-26APR24")

        assert snap.event_ticker == "KXSOYBEANW-26APR24"
        assert snap.series_ticker == "KXSOYBEANW"
        assert snap.expiry_date == date(2026, 4, 24)
        assert snap.status == "open"
        assert snap.bucket_grid.n_buckets == 5
        assert isinstance(snap.fetched_at, datetime)
        mock_client.get_event.assert_called_once_with("KXSOYBEANW-26APR24")

    @pytest.mark.asyncio
    async def test_pull_event_rejects_missing_event_key(
        self, mock_client: MagicMock,
    ) -> None:
        mock_client.get_event.return_value = {"markets": []}
        puller = EventPuller(mock_client)
        with pytest.raises(ValueError, match="missing 'event' key"):
            await puller.pull_event("KXSOYBEANW-26APR24")

    @pytest.mark.asyncio
    async def test_pull_event_rejects_missing_markets(
        self, mock_client: MagicMock,
    ) -> None:
        mock_client.get_event.return_value = {
            "event": {"event_ticker": "KXSOYBEANW-26APR24", "series_ticker": "KXSOYBEANW", "title": "t", "status": "open"},
        }
        puller = EventPuller(mock_client)
        with pytest.raises(ValueError, match="missing or invalid 'markets'"):
            await puller.pull_event("KXSOYBEANW-26APR24")

    @pytest.mark.asyncio
    async def test_pull_event_rejects_empty_markets(
        self, mock_client: MagicMock,
    ) -> None:
        mock_client.get_event.return_value = {
            "event": {"event_ticker": "KXSOYBEANW-26APR24", "series_ticker": "KXSOYBEANW", "title": "t", "status": "open"},
            "markets": [],
        }
        puller = EventPuller(mock_client)
        with pytest.raises(ValueError, match="no child markets"):
            await puller.pull_event("KXSOYBEANW-26APR24")

    @pytest.mark.asyncio
    async def test_pull_active_events(self, mock_client: MagicMock) -> None:
        mock_client.get_events.return_value = {
            "events": [
                {"event_ticker": "KXSOYBEANW-26MAY01"},
                {"event_ticker": "KXSOYBEANW-26APR24"},
            ],
            "cursor": None,
        }
        # Both events return the same response (different tickers in real life)
        mock_client.get_event.return_value = _sample_event_response()

        puller = EventPuller(mock_client)
        snapshots = await puller.pull_active_events("KXSOYBEANW")

        # Should be sorted by expiry date
        assert len(snapshots) == 2
        assert snapshots[0].expiry_date <= snapshots[1].expiry_date

    @pytest.mark.asyncio
    async def test_pull_active_events_pagination(
        self, mock_client: MagicMock,
    ) -> None:
        # First page returns cursor, second page returns no cursor
        mock_client.get_events.side_effect = [
            {
                "events": [{"event_ticker": "KXSOYBEANW-26APR24"}],
                "cursor": "page2",
            },
            {
                "events": [{"event_ticker": "KXSOYBEANW-26MAY01"}],
                "cursor": None,
            },
        ]
        mock_client.get_event.return_value = _sample_event_response()

        puller = EventPuller(mock_client)
        snapshots = await puller.pull_active_events("KXSOYBEANW")

        assert len(snapshots) == 2
        assert mock_client.get_events.call_count == 2

    @pytest.mark.asyncio
    async def test_pull_active_events_skips_bad_event(
        self, mock_client: MagicMock,
    ) -> None:
        mock_client.get_events.return_value = {
            "events": [
                {"event_ticker": "KXSOYBEANW-26APR24"},
                {"event_ticker": "KXSOYBEANW-26MAY01"},
            ],
            "cursor": None,
        }
        # First event succeeds, second fails
        mock_client.get_event.side_effect = [
            _sample_event_response(),
            ValueError("bad data"),
        ]

        puller = EventPuller(mock_client)
        snapshots = await puller.pull_active_events("KXSOYBEANW")

        # Should skip the bad event and return only the good one
        assert len(snapshots) == 1
