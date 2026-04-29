"""Tests for engine/settlement_gate.py — settlement-gap risk gate."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine.settlement_gate import (
    GateAction,
    GateState,
    SettlementGateConfig,
    USDAEvent,
    gate_state,
    get_usda_calendar,
    next_event,
    time_to_next_event,
)

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_calendar(release: datetime) -> list[USDAEvent]:
    """Build a single-event calendar for testing."""
    return [USDAEvent(name="TEST-EVENT", release_time=release, series="soy")]


def _dt(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=_ET)


# ---------------------------------------------------------------------------
# Tests: USDA calendar
# ---------------------------------------------------------------------------


class TestUSDACalendar:
    def test_calendar_not_empty(self):
        cal = get_usda_calendar()
        assert len(cal) > 0

    def test_calendar_sorted(self):
        cal = get_usda_calendar()
        for i in range(1, len(cal)):
            assert cal[i].release_time >= cal[i - 1].release_time

    def test_wasde_present(self):
        cal = get_usda_calendar()
        wasde = [e for e in cal if "WASDE" in e.name]
        assert len(wasde) == 12  # monthly

    def test_crop_progress_present(self):
        cal = get_usda_calendar()
        cp = [e for e in cal if "CropProgress" in e.name]
        # Approximately 35 Mondays in Apr-Nov
        assert len(cp) >= 30


class TestNextEvent:
    def test_finds_next(self):
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = _dt(2026, 5, 10, 10, 0)
        ev = next_event(now, "soy", cal)
        assert ev is not None
        assert ev.name == "TEST-EVENT"

    def test_none_when_past(self):
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = _dt(2026, 5, 13, 10, 0)
        ev = next_event(now, "soy", cal)
        assert ev is None

    def test_series_filter(self):
        cal = [USDAEvent("TEST", _dt(2026, 5, 12, 12, 0), series="corn")]
        ev = next_event(_dt(2026, 5, 10), "soy", cal)
        assert ev is None


class TestTimeToNextEvent:
    def test_positive_delta(self):
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = _dt(2026, 5, 12, 11, 0)
        td = time_to_next_event(now, "soy", cal)
        assert td is not None
        assert td.total_seconds() == pytest.approx(3600.0)


# ---------------------------------------------------------------------------
# Tests: Gate state machine
# ---------------------------------------------------------------------------


class TestGateStateNormal:
    def test_far_from_event(self):
        """Days before any event -> NORMAL."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = _dt(2026, 5, 5, 10, 0)  # 7 days before

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.NORMAL
        assert result.size_mult == 1.0
        assert result.spread_mult == 1.0


class TestGateStateSizeDown:
    def test_24h_before_is_size_down_75(self):
        """20h before event -> SIZE_DOWN_75."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(hours=20)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.SIZE_DOWN_75
        assert result.size_mult == 0.75
        assert result.spread_mult == 1.0

    def test_15h_before_is_size_down_50(self):
        """15h before event -> SIZE_DOWN_50."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(hours=15)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.SIZE_DOWN_50
        assert result.size_mult == 0.50

    def test_9h_before_is_size_down_25(self):
        """9h before event -> SIZE_DOWN_25."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(hours=9)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.SIZE_DOWN_25
        assert result.size_mult == 0.25


class TestGateStateWidened:
    def test_3h_before_is_widened(self):
        """3h before event -> WIDENED."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(hours=3)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.WIDENED
        assert result.size_mult == 0.25
        assert result.spread_mult == 2.0


class TestGateStatePullAll:
    def test_30s_before_is_pull_all(self):
        """30s before event -> PULL_ALL."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(seconds=30)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.PULL_ALL
        assert result.size_mult == 0.0

    def test_5min_after_is_pull_all(self):
        """5min after event -> PULL_ALL (within post-window)."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release + timedelta(minutes=5)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.PULL_ALL
        assert result.size_mult == 0.0

    def test_20min_after_is_normal(self):
        """20min after event -> NORMAL (post-window expired)."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release + timedelta(minutes=20)

        result = gate_state(now, "soy", calendar=cal)
        assert result.state == GateState.NORMAL


class TestGateStateLadder:
    """Verify the full size-down ladder progression."""

    def test_monotone_size_reduction(self):
        """Size should decrease monotonically approaching event."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)

        hours = [25, 22, 20, 16, 13, 10, 8, 4, 2, 0.5]
        sizes = []
        for h in hours:
            now = release - timedelta(hours=h)
            result = gate_state(now, "soy", calendar=cal)
            sizes.append(result.size_mult)

        # Size should be non-increasing
        for i in range(1, len(sizes)):
            assert sizes[i] <= sizes[i - 1], (
                f"Size increased from {sizes[i-1]} to {sizes[i]} "
                f"at {hours[i-1]}h -> {hours[i]}h before event"
            )


class TestGateConfigOverride:
    def test_custom_pull_before(self):
        """Custom pull_before timing."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        config = SettlementGateConfig(pull_before=300.0)  # 5min before

        # 2min before with 5min pull_before -> PULL_ALL
        now = release - timedelta(minutes=2)
        result = gate_state(now, "soy", config=config, calendar=cal)
        assert result.state == GateState.PULL_ALL

    def test_custom_post_window(self):
        """Custom post-window duration."""
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        config = SettlementGateConfig(post_window=30 * 60)  # 30min

        # 20min after with 30min post_window -> PULL_ALL
        now = release + timedelta(minutes=20)
        result = gate_state(now, "soy", config=config, calendar=cal)
        assert result.state == GateState.PULL_ALL


class TestGateNextEventName:
    def test_reports_event_name(self):
        release = _dt(2026, 5, 12, 12, 0)
        cal = _make_calendar(release)
        now = release - timedelta(hours=10)
        result = gate_state(now, "soy", calendar=cal)
        assert result.next_event_name == "TEST-EVENT"
