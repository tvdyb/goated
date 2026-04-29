"""ACT-LIP-VIAB -- LIP viability analysis framework.

Loads captured orderbook + pool data from DuckDB, simulates our score at
full presence, and produces a structured go/no-go recommendation.

Data sources:
  - CaptureStore (ACT-01): orderbook_snapshots, market_events
  - LIPPoolStore (ACT-LIP-POOL): lip_reward_periods
  - fees.kalshi_fees (ACT-10): maker fee model

Non-negotiables enforced:
  - No pandas; DuckDB SQL queries + dataclasses
  - Type hints on all public interfaces
  - Fail-loud on insufficient data (< 3 days captured)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import duckdb

from fees.kalshi_fees import maker_fee

logger = logging.getLogger(__name__)

# ── Errors ────────────────────────────────────────────────────────────


class InsufficientDataError(Exception):
    """Raised when captured data covers fewer than the minimum required days."""


class ViabilityError(Exception):
    """Base error for viability analysis failures."""


# ── Configuration ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ViabilityConfig:
    """Configuration for the viability analysis.

    Attributes:
        min_days: Minimum number of days of captured data required.
        target_size_multiplier: Multiplier on Target Size for full-presence
            simulation (OD-33' default 1.5).
        default_target_size: Default Target Size if not discoverable from
            pool data (100 contracts per Kalshi LIP docs).
        decay_ticks: Distance multiplier decay (ticks from inside to zero).
        hedge_cost_per_day_usd: Placeholder daily hedge cost.
        revenue_threshold_per_day_usd: KC-LIP-01 threshold.
        share_threshold_pct: KC-LIP-02 threshold (minimum projected share %).
        maker_fee_price: Representative mid-price for fee estimation.
        taker_rate: Kalshi taker fee rate.
        maker_fraction: Maker fee as fraction of taker fee.
    """

    min_days: int = 3
    target_size_multiplier: float = 1.5
    default_target_size: float = 100.0
    decay_ticks: int = 5
    hedge_cost_per_day_usd: float = 5.0
    revenue_threshold_per_day_usd: float = 50.0
    share_threshold_pct: float = 5.0
    maker_fee_price: float = 0.50
    taker_rate: float = 0.07
    maker_fraction: float = 0.25


# ── Result structures ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DailyPoolTotal:
    """Pool total for one date."""

    dt: date
    total_pool_usd: float
    market_count: int


@dataclass(frozen=True, slots=True)
class CompetitionEstimate:
    """Competition density estimate for one snapshot date."""

    dt: date
    avg_distinct_levels_per_market: float
    avg_total_resting_size: float
    snapshot_count: int


@dataclass(frozen=True, slots=True)
class ScoreSimulation:
    """Simulated score at full presence for one snapshot."""

    dt: date
    our_simulated_score: float
    total_visible_score: float
    projected_share_pct: float
    market_count: int


@dataclass(frozen=True, slots=True)
class RevenueProjection:
    """Projected revenue over the observation period."""

    daily_gross_usd: float
    daily_fees_usd: float
    daily_hedge_cost_usd: float
    daily_net_usd: float
    weekly_net_usd: float
    monthly_net_usd: float


@dataclass(frozen=True, slots=True)
class ViabilityReport:
    """Full viability analysis report.

    Structured output with go/no-go recommendation per KC-LIP-01 and KC-LIP-02.
    """

    observation_start: date
    observation_end: date
    days_observed: int

    # Pool data
    daily_pool_totals: list[DailyPoolTotal]
    avg_daily_pool_usd: float

    # Competition
    competition_estimates: list[CompetitionEstimate]
    avg_distinct_levels: float

    # Score simulation
    score_simulations: list[ScoreSimulation]
    avg_projected_share_pct: float

    # Revenue
    revenue: RevenueProjection

    # Go/no-go
    go: bool
    kill_criteria_triggered: list[str]
    recommendation: str


# ── Core analysis engine ──────────────────────────────────────────────


class LIPViabilityAnalyzer:
    """Viability analysis engine.

    Connects to two DuckDB databases (capture + pool) and runs the
    analysis pipeline.

    Args:
        capture_db_path: Path to the CaptureStore DuckDB file.
        pool_db_path: Path to the LIPPoolStore DuckDB file.
        config: Analysis configuration.
    """

    def __init__(
        self,
        capture_db_path: str,
        pool_db_path: str,
        config: ViabilityConfig | None = None,
    ) -> None:
        self._capture_conn = duckdb.connect(capture_db_path, read_only=True)
        self._pool_conn = duckdb.connect(pool_db_path, read_only=True)
        self._config = config or ViabilityConfig()

    def close(self) -> None:
        """Close both DuckDB connections."""
        self._capture_conn.close()
        self._pool_conn.close()

    # ── Step 1: Data sufficiency check ────────────────────────────────

    def _check_data_sufficiency(self) -> tuple[date, date, int]:
        """Verify minimum data coverage. Returns (start, end, days).

        Raises:
            InsufficientDataError: If fewer than min_days of snapshots exist.
        """
        result = self._capture_conn.execute(
            "SELECT MIN(captured_at::DATE), MAX(captured_at::DATE), "
            "COUNT(DISTINCT captured_at::DATE) "
            "FROM orderbook_snapshots"
        ).fetchone()

        if result is None or result[0] is None:
            raise InsufficientDataError(
                "No orderbook snapshots found in capture database"
            )

        start_date, end_date, distinct_days = result[0], result[1], result[2]

        if distinct_days < self._config.min_days:
            raise InsufficientDataError(
                f"Only {distinct_days} day(s) of captured data found; "
                f"minimum {self._config.min_days} required. "
                f"Range: {start_date} to {end_date}"
            )

        return start_date, end_date, distinct_days

    # ── Step 2: Daily pool totals ─────────────────────────────────────

    def _compute_daily_pool_totals(self) -> list[DailyPoolTotal]:
        """Sum pool_size_usd across all active KXSOYBEANW markets per day.

        Uses the LIP reward periods table. For each day in the observation
        window, sums pool sizes for periods whose [start_date, end_date]
        covers that day.
        """
        rows = self._pool_conn.execute(
            "SELECT start_date, "
            "       SUM(pool_size_usd) AS total_pool, "
            "       COUNT(*) AS market_count "
            "FROM lip_reward_periods "
            "WHERE market_ticker LIKE 'KXSOYBEANW%' "
            "GROUP BY start_date "
            "ORDER BY start_date"
        ).fetchall()

        if not rows:
            # Fall back: check if there are any periods at all
            count = self._pool_conn.execute(
                "SELECT COUNT(*) FROM lip_reward_periods"
            ).fetchone()
            if count and count[0] == 0:
                logger.warning("No LIP reward periods found in pool database")
            return []

        return [
            DailyPoolTotal(
                dt=row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0])),
                total_pool_usd=float(row[1]),
                market_count=int(row[2]),
            )
            for row in rows
        ]

    # ── Step 3: Competition density ───────────────────────────────────

    def _estimate_competition(self) -> list[CompetitionEstimate]:
        """Count distinct price levels with resting orders per snapshot.

        Each price level with size > 0 is a proxy for a distinct participant.
        We parse the JSON yes_levels and no_levels from orderbook_snapshots.
        """
        rows = self._capture_conn.execute(
            "SELECT captured_at::DATE AS dt, "
            "       ticker, "
            "       yes_levels, "
            "       no_levels "
            "FROM orderbook_snapshots "
            "ORDER BY dt, ticker"
        ).fetchall()

        if not rows:
            return []

        # Aggregate per day
        day_data: dict[date, list[tuple[int, float]]] = {}
        for row in rows:
            dt = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            yes_raw = row[2]
            no_raw = row[3]

            yes_levels = _parse_levels_json(yes_raw)
            no_levels = _parse_levels_json(no_raw)

            n_levels = len(yes_levels) + len(no_levels)
            total_size = sum(s for _, s in yes_levels) + sum(s for _, s in no_levels)

            if dt not in day_data:
                day_data[dt] = []
            day_data[dt].append((n_levels, total_size))

        estimates: list[CompetitionEstimate] = []
        for dt in sorted(day_data.keys()):
            entries = day_data[dt]
            avg_levels = sum(e[0] for e in entries) / len(entries) if entries else 0.0
            avg_size = sum(e[1] for e in entries) / len(entries) if entries else 0.0
            estimates.append(
                CompetitionEstimate(
                    dt=dt,
                    avg_distinct_levels_per_market=avg_levels,
                    avg_total_resting_size=avg_size,
                    snapshot_count=len(entries),
                )
            )

        return estimates

    # ── Step 4: Score simulation ──────────────────────────────────────

    def _simulate_score_at_full_presence(self) -> list[ScoreSimulation]:
        """Simulate our LIP score assuming full presence.

        Full presence means:
          - Resting at best bid (yes side) with target_size * multiplier
          - Resting at best ask (no side) with target_size * multiplier
          - Distance multiplier = 1.0 (at inside)

        Our simulated score = 2 * target_size * multiplier * 1.0
        (both sides, at inside, full distance multiplier)

        Total visible score = sum over all levels of (size * dist_mult)
        plus our simulated addition.
        """
        rows = self._capture_conn.execute(
            "SELECT captured_at::DATE AS dt, "
            "       ticker, "
            "       yes_levels, "
            "       no_levels "
            "FROM orderbook_snapshots "
            "ORDER BY dt, ticker"
        ).fetchall()

        if not rows:
            return []

        our_size_per_side = (
            self._config.default_target_size * self._config.target_size_multiplier
        )
        # Our score: at best price on each side, multiplier = 1.0
        our_score_per_snapshot = our_size_per_side * 2.0  # both sides

        day_data: dict[date, list[tuple[float, float, str]]] = {}
        for row in rows:
            dt = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            ticker = str(row[1])
            yes_levels = _parse_levels_json(row[2])
            no_levels = _parse_levels_json(row[3])

            # Compute total visible score from existing orderbook
            visible_score = _compute_visible_score(
                yes_levels, no_levels, self._config.decay_ticks
            )

            if dt not in day_data:
                day_data[dt] = []
            day_data[dt].append((visible_score, our_score_per_snapshot, ticker))

        simulations: list[ScoreSimulation] = []
        for dt in sorted(day_data.keys()):
            entries = day_data[dt]
            # Unique markets
            markets = set(e[2] for e in entries)
            # Average across all snapshots for this day
            total_visible = sum(e[0] for e in entries) / len(entries)
            our_avg = our_score_per_snapshot  # constant per snapshot

            # Total with us added
            total_with_us = total_visible + our_avg

            if total_with_us > 0:
                share = (our_avg / total_with_us) * 100.0
            else:
                share = 0.0

            simulations.append(
                ScoreSimulation(
                    dt=dt,
                    our_simulated_score=our_avg,
                    total_visible_score=total_visible,
                    projected_share_pct=share,
                    market_count=len(markets),
                )
            )

        return simulations

    # ── Step 5: Revenue projection ────────────────────────────────────

    def _project_revenue(
        self,
        avg_daily_pool_usd: float,
        avg_share_pct: float,
    ) -> RevenueProjection:
        """Project revenue from pool share, deducting fees and hedge cost.

        Fee estimate: we assume fills happen at a representative price,
        and we pay maker fees. The fee is a per-contract cost; we estimate
        daily fill volume as ~ 2 * target_size * multiplier contracts
        (one round-trip per day as a conservative placeholder).
        """
        daily_gross = avg_daily_pool_usd * (avg_share_pct / 100.0)

        # Fee estimate: maker fee on assumed daily fills
        fee_per_contract = maker_fee(
            self._config.maker_fee_price,
            taker_rate=self._config.taker_rate,
            maker_fraction=self._config.maker_fraction,
        )
        # Conservative estimate: 1 round-trip per day per side
        estimated_daily_contracts = (
            self._config.default_target_size * self._config.target_size_multiplier * 2
        )
        daily_fees = fee_per_contract * estimated_daily_contracts

        daily_hedge = self._config.hedge_cost_per_day_usd
        daily_net = daily_gross - daily_fees - daily_hedge

        return RevenueProjection(
            daily_gross_usd=round(daily_gross, 2),
            daily_fees_usd=round(daily_fees, 2),
            daily_hedge_cost_usd=round(daily_hedge, 2),
            daily_net_usd=round(daily_net, 2),
            weekly_net_usd=round(daily_net * 7, 2),
            monthly_net_usd=round(daily_net * 30, 2),
        )

    # ── Step 6: Go/no-go ─────────────────────────────────────────────

    def run(self) -> ViabilityReport:
        """Execute the full viability analysis pipeline.

        Returns:
            ViabilityReport with all computed fields and go/no-go.

        Raises:
            InsufficientDataError: If < min_days of data captured.
        """
        # Step 1: Data check
        start_date, end_date, days_observed = self._check_data_sufficiency()

        # Step 2: Pool totals
        daily_pools = self._compute_daily_pool_totals()
        avg_daily_pool = (
            sum(p.total_pool_usd for p in daily_pools) / len(daily_pools)
            if daily_pools
            else 0.0
        )

        # Step 3: Competition
        competition = self._estimate_competition()
        avg_levels = (
            sum(c.avg_distinct_levels_per_market for c in competition)
            / len(competition)
            if competition
            else 0.0
        )

        # Step 4: Score simulation
        scores = self._simulate_score_at_full_presence()
        avg_share = (
            sum(s.projected_share_pct for s in scores) / len(scores)
            if scores
            else 0.0
        )

        # Step 5: Revenue
        revenue = self._project_revenue(avg_daily_pool, avg_share)

        # Step 6: Go/no-go
        kills: list[str] = []
        if revenue.daily_net_usd < self._config.revenue_threshold_per_day_usd:
            kills.append(
                f"KC-LIP-01: projected net ${revenue.daily_net_usd:.2f}/day "
                f"< ${self._config.revenue_threshold_per_day_usd:.2f}/day threshold"
            )
        if avg_share < self._config.share_threshold_pct:
            kills.append(
                f"KC-LIP-02: projected share {avg_share:.1f}% "
                f"< {self._config.share_threshold_pct:.1f}% threshold"
            )

        go = len(kills) == 0

        if go:
            recommendation = (
                f"GO -- Projected ${revenue.daily_net_usd:.2f}/day net "
                f"({avg_share:.1f}% share of ${avg_daily_pool:.2f}/day pool). "
                f"Proceed to Wave 1."
            )
        else:
            recommendation = (
                f"NO-GO -- {len(kills)} kill criteria triggered. "
                + " | ".join(kills)
                + " Consider pivoting to different KX* market family or "
                "revisiting edge-driven (F1) framing."
            )

        return ViabilityReport(
            observation_start=start_date,
            observation_end=end_date,
            days_observed=days_observed,
            daily_pool_totals=daily_pools,
            avg_daily_pool_usd=round(avg_daily_pool, 2),
            competition_estimates=competition,
            avg_distinct_levels=round(avg_levels, 2),
            score_simulations=scores,
            avg_projected_share_pct=round(avg_share, 2),
            revenue=revenue,
            go=go,
            kill_criteria_triggered=kills,
            recommendation=recommendation,
        )


# ── Helpers ───────────────────────────────────────────────────────────


def _parse_levels_json(raw: str) -> list[tuple[int, float]]:
    """Parse a JSON-encoded levels array from CaptureStore.

    Format: [[price_cents, size], ...].
    Returns list of (price_cents, size) tuples with size > 0.
    """
    if not raw:
        return []
    try:
        levels = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [(int(p), float(s)) for p, s in levels if float(s) > 0]


def _compute_visible_score(
    yes_levels: list[tuple[int, float]],
    no_levels: list[tuple[int, float]],
    decay_ticks: int,
) -> float:
    """Compute total visible LIP score from orderbook levels.

    Uses linear distance multiplier: 1.0 at best, decaying to 0.0
    over decay_ticks.
    """
    score = 0.0

    # Yes side: best bid = max price
    if yes_levels:
        best_bid = max(p for p, _ in yes_levels)
        for price, size in yes_levels:
            dist = abs(price - best_bid)
            if dist == 0:
                mult = 1.0
            elif dist >= decay_ticks:
                mult = 0.0
            else:
                mult = 1.0 - float(dist) / float(decay_ticks)
            score += size * mult

    # No side: best no bid = max price on no side
    if no_levels:
        best_no = max(p for p, _ in no_levels)
        for price, size in no_levels:
            dist = abs(price - best_no)
            if dist == 0:
                mult = 1.0
            elif dist >= decay_ticks:
                mult = 0.0
            else:
                mult = 1.0 - float(dist) / float(decay_ticks)
            score += size * mult

    return score
