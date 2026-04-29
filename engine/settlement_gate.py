"""Settlement-gap risk gate for USDA event windows.

Reads a static USDA event calendar and returns a gate state that controls
the quoter's size, spread, and pull behavior in the run-up to and aftermath
of scheduled USDA releases.

Gate states:
- NORMAL: business as usual (size_mult=1.0, spread_mult=1.0)
- SIZE_DOWN_75: 24h-18h before release (size_mult=0.75, spread_mult=1.0)
- SIZE_DOWN_50: 18h-12h before release (size_mult=0.50, spread_mult=1.0)
- SIZE_DOWN_25: 12h-6h before release (size_mult=0.25, spread_mult=1.0)
- WIDENED: 6h before to 60s before release (size_mult=0.25, spread_mult=2.0)
- PULL_ALL: 60s before to 15min after release (size_mult=0.0, spread_mult=inf)

The pre-window pull (60s) ensures all resting orders are cancelled before
the release. The post-window (15min) allows the market to settle before
re-entering.

USDA event schedule for soybean markets:
- WASDE: monthly, usually 12th of month, 12:00 noon ET
- Crop Progress: weekly Mon 16:00 ET, Apr-Nov (growing season)
- Quarterly Grain Stocks: late March/June/Sept/Dec, 12:00 noon ET
- Prospective Plantings: late March, 12:00 noon ET
- Acreage: late June, 12:00 noon ET

Closes: F4-ACT-11 (settlement-gap risk gate), F4-ACT-06 (partial: event clock).

Non-negotiables: fail-loud, no pandas, type hints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Gate state
# ---------------------------------------------------------------------------


class GateState(Enum):
    """Settlement gate state."""

    NORMAL = auto()
    SIZE_DOWN_75 = auto()
    SIZE_DOWN_50 = auto()
    SIZE_DOWN_25 = auto()
    WIDENED = auto()
    PULL_ALL = auto()


@dataclass(frozen=True, slots=True)
class GateAction:
    """Gate output consumed by the quoter.

    Attributes:
        state: Current gate state.
        size_mult: Size multiplier (1.0 = normal, 0.0 = cancel all).
        spread_mult: Spread multiplier (1.0 = normal, 2.0 = doubled).
        next_event_name: Name of the upcoming event (for logging).
        time_to_event_seconds: Seconds until the next event (negative = past).
    """

    state: GateState
    size_mult: float
    spread_mult: float
    next_event_name: str
    time_to_event_seconds: float


# ---------------------------------------------------------------------------
# Gate config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SettlementGateConfig:
    """Timing parameters for the settlement gate.

    All durations in seconds.
    """

    size_down_start: float = 24 * 3600      # 24h before release
    widen_start: float = 6 * 3600           # 6h before release
    pull_before: float = 60.0               # 60s before release
    post_window: float = 15 * 60            # 15min after release
    widen_spread_mult: float = 2.0          # spread doubles in widened zone


# ---------------------------------------------------------------------------
# USDA Event Calendar (static for 2026)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class USDAEvent:
    """A single USDA release event.

    Attributes:
        name: Human-readable name.
        release_time: ET datetime of the release.
        series: Which commodity series this affects.
    """

    name: str
    release_time: datetime
    series: str = "soy"  # default to soybean


def _dt(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    """Construct an ET datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=_ET)


def _usda_calendar_2026() -> list[USDAEvent]:
    """Static USDA event calendar for 2026, soybean-relevant releases."""
    events: list[USDAEvent] = []

    # WASDE monthly reports (typically 12th of month, noon ET)
    wasde_dates = [
        (1, 12), (2, 10), (3, 10), (4, 9), (5, 12),
        (6, 11), (7, 10), (8, 12), (9, 11), (10, 9),
        (11, 10), (12, 9),
    ]
    for month, day in wasde_dates:
        events.append(USDAEvent(
            name=f"WASDE-2026-{month:02d}",
            release_time=_dt(2026, month, day, 12, 0),
        ))

    # Crop Progress: weekly Monday 16:00 ET, April through November
    # Generate all Mondays in Apr-Nov 2026
    start = datetime(2026, 4, 1, tzinfo=_ET)
    end = datetime(2026, 11, 30, tzinfo=_ET)
    d = start
    while d <= end:
        if d.weekday() == 0:  # Monday
            events.append(USDAEvent(
                name=f"CropProgress-{d.strftime('%Y%m%d')}",
                release_time=d.replace(hour=16, minute=0, second=0),
            ))
        d += timedelta(days=1)

    # Quarterly Grain Stocks (noon ET)
    events.append(USDAEvent(name="GrainStocks-2026Q1", release_time=_dt(2026, 3, 31, 12, 0)))
    events.append(USDAEvent(name="GrainStocks-2026Q2", release_time=_dt(2026, 6, 30, 12, 0)))
    events.append(USDAEvent(name="GrainStocks-2026Q3", release_time=_dt(2026, 9, 30, 12, 0)))
    events.append(USDAEvent(name="GrainStocks-2026Q4", release_time=_dt(2026, 12, 23, 12, 0)))

    # Prospective Plantings (late March, noon ET)
    events.append(USDAEvent(name="Plantings-2026", release_time=_dt(2026, 3, 31, 12, 0)))

    # Acreage (late June, noon ET)
    events.append(USDAEvent(name="Acreage-2026", release_time=_dt(2026, 6, 30, 12, 0)))

    # Sort by release time
    events.sort(key=lambda e: e.release_time)
    return events


# Module-level calendar (singleton)
_CALENDAR: list[USDAEvent] | None = None


def get_usda_calendar() -> list[USDAEvent]:
    """Return the USDA event calendar (lazily loaded singleton)."""
    global _CALENDAR
    if _CALENDAR is None:
        _CALENDAR = _usda_calendar_2026()
    return _CALENDAR


def next_event(
    now: datetime,
    series: str = "soy",
    calendar: list[USDAEvent] | None = None,
) -> USDAEvent | None:
    """Find the next upcoming USDA event for the given series.

    Returns None if no future events exist in the calendar.
    """
    cal = calendar or get_usda_calendar()
    for event in cal:
        if event.series == series and event.release_time > now:
            return event
    return None


def time_to_next_event(
    now: datetime,
    series: str = "soy",
    calendar: list[USDAEvent] | None = None,
) -> timedelta | None:
    """Return timedelta to the next event. None if no future events."""
    ev = next_event(now, series, calendar)
    if ev is None:
        return None
    return ev.release_time - now


# ---------------------------------------------------------------------------
# Gate computation
# ---------------------------------------------------------------------------


def gate_state(
    now: datetime,
    series: str = "soy",
    config: SettlementGateConfig | None = None,
    calendar: list[USDAEvent] | None = None,
) -> GateAction:
    """Compute the current gate state based on proximity to USDA events.

    Parameters
    ----------
    now : datetime (must be timezone-aware, ET preferred).
    series : Commodity series filter.
    config : Gate timing configuration.
    calendar : Override calendar (for testing).

    Returns
    -------
    GateAction with size/spread multipliers for the quoter.
    """
    if config is None:
        config = SettlementGateConfig()
    cal = calendar or get_usda_calendar()

    # Find the nearest event (past or future within post-window)
    best_event: USDAEvent | None = None
    best_seconds: float = float("inf")

    for event in cal:
        if event.series != series:
            continue
        delta = (event.release_time - now).total_seconds()
        # Consider events from 24h before to post_window after
        if -config.post_window <= delta <= config.size_down_start:
            if abs(delta) < abs(best_seconds):
                best_seconds = delta
                best_event = event

    if best_event is None:
        # No nearby event — find next future event for logging
        nxt = next_event(now, series, cal)
        name = nxt.name if nxt else "none"
        tte = (nxt.release_time - now).total_seconds() if nxt else float("inf")
        return GateAction(
            state=GateState.NORMAL,
            size_mult=1.0,
            spread_mult=1.0,
            next_event_name=name,
            time_to_event_seconds=tte,
        )

    seconds_to_event = best_seconds  # positive = before event

    # Post-window: event already happened, within post_window
    if seconds_to_event < 0:
        if abs(seconds_to_event) <= config.post_window:
            return GateAction(
                state=GateState.PULL_ALL,
                size_mult=0.0,
                spread_mult=float("inf"),
                next_event_name=best_event.name,
                time_to_event_seconds=seconds_to_event,
            )

    # Pre-window pull: within pull_before seconds of release
    if 0 <= seconds_to_event <= config.pull_before:
        return GateAction(
            state=GateState.PULL_ALL,
            size_mult=0.0,
            spread_mult=float("inf"),
            next_event_name=best_event.name,
            time_to_event_seconds=seconds_to_event,
        )

    # Widened zone: 6h to pull_before
    if config.pull_before < seconds_to_event <= config.widen_start:
        return GateAction(
            state=GateState.WIDENED,
            size_mult=0.25,
            spread_mult=config.widen_spread_mult,
            next_event_name=best_event.name,
            time_to_event_seconds=seconds_to_event,
        )

    # Size-down ladder: 24h to 6h, in 6h blocks
    # 24h-18h: 75%, 18h-12h: 50%, 12h-6h: 25%
    if config.widen_start < seconds_to_event <= 12 * 3600:
        return GateAction(
            state=GateState.SIZE_DOWN_25,
            size_mult=0.25,
            spread_mult=1.0,
            next_event_name=best_event.name,
            time_to_event_seconds=seconds_to_event,
        )

    if 12 * 3600 < seconds_to_event <= 18 * 3600:
        return GateAction(
            state=GateState.SIZE_DOWN_50,
            size_mult=0.50,
            spread_mult=1.0,
            next_event_name=best_event.name,
            time_to_event_seconds=seconds_to_event,
        )

    if 18 * 3600 < seconds_to_event <= config.size_down_start:
        return GateAction(
            state=GateState.SIZE_DOWN_75,
            size_mult=0.75,
            spread_mult=1.0,
            next_event_name=best_event.name,
            time_to_event_seconds=seconds_to_event,
        )

    # Should not reach here, but safety fallback
    return GateAction(
        state=GateState.NORMAL,
        size_mult=1.0,
        spread_mult=1.0,
        next_event_name=best_event.name,
        time_to_event_seconds=seconds_to_event,
    )
