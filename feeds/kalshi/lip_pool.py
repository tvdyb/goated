"""LIP (Liquidity Incentive Program) pool data ingest and persistence.

Pulls active LIP reward periods and pool sizes per KXSOYBEANW market,
persists to DuckDB, refreshes daily.

Data source strategy:
  1. Config overrides from config/lip_pools.yaml (manual entry fallback)
  2. Kalshi REST API market metadata (if LIP fields are present)

Non-negotiables enforced:
  - No pandas; DuckDB direct
  - asyncio for I/O only
  - Fail-loud on missing/corrupted data
  - Type hints on all public interfaces
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# ── Data model ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LIPRewardPeriod:
    """A single LIP reward period for a specific market."""

    market_ticker: str
    pool_size_usd: float
    start_date: date
    end_date: date
    active: bool
    source: str  # "api", "config", or "manual"
    captured_at: datetime

    def __post_init__(self) -> None:
        if not self.market_ticker:
            raise ValueError("market_ticker must be non-empty")
        if self.pool_size_usd < 0:
            raise ValueError(
                f"pool_size_usd must be non-negative, got {self.pool_size_usd}"
            )
        if self.end_date < self.start_date:
            raise ValueError(
                f"end_date ({self.end_date}) must be >= start_date ({self.start_date})"
            )
        if self.source not in ("api", "config", "manual"):
            raise ValueError(f"source must be 'api', 'config', or 'manual', got {self.source!r}")


# ── Errors ────────────────────────────────────────────────────────────


class LIPPoolError(Exception):
    """Base error for LIP pool operations."""


class LIPPoolDataError(LIPPoolError):
    """Raised when LIP pool data is missing or corrupted."""


# ── Config loader ─────────────────────────────────────────────────────


def load_config_pools(config_path: Path) -> list[LIPRewardPeriod]:
    """Load LIP pool data from a YAML config file.

    Expected format::

        pools:
          - market_ticker: "KXSOYBEANW-26APR27-17"
            pool_size_usd: 250.00
            start_date: "2026-04-20"
            end_date: "2026-04-27"
          - market_ticker: "KXSOYBEANW-26APR27-18"
            pool_size_usd: 150.00
            start_date: "2026-04-20"
            end_date: "2026-04-27"

    Raises:
        LIPPoolDataError: If config is malformed or missing required fields.
        FileNotFoundError: If config file does not exist (caller decides
            whether this is fatal).
    """
    import yaml  # lazy import — only needed when config file exists

    if not config_path.exists():
        raise FileNotFoundError(f"LIP pool config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())
    if not isinstance(raw, dict) or "pools" not in raw:
        raise LIPPoolDataError(
            f"Config file {config_path} must contain a 'pools' key with a list"
        )

    pools_raw = raw["pools"]
    if not isinstance(pools_raw, list):
        raise LIPPoolDataError(
            f"'pools' in {config_path} must be a list, got {type(pools_raw).__name__}"
        )

    now = datetime.now(timezone.utc)
    periods: list[LIPRewardPeriod] = []
    for i, entry in enumerate(pools_raw):
        try:
            start = _parse_date(entry["start_date"])
            end = _parse_date(entry["end_date"])
            period = LIPRewardPeriod(
                market_ticker=str(entry["market_ticker"]),
                pool_size_usd=float(entry["pool_size_usd"]),
                start_date=start,
                end_date=end,
                active=end >= now.date(),
                source="config",
                captured_at=now,
            )
            periods.append(period)
        except (KeyError, TypeError, ValueError) as exc:
            raise LIPPoolDataError(
                f"Invalid pool entry at index {i} in {config_path}: {exc}"
            ) from exc

    return periods


def _parse_date(value: Any) -> date:
    """Parse a date from string or date object."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Cannot parse date from {type(value).__name__}: {value!r}")


# ── API parser ────────────────────────────────────────────────────────


def parse_api_lip_data(
    market_ticker: str,
    market_data: dict[str, Any],
) -> LIPRewardPeriod | None:
    """Extract LIP reward period from Kalshi market API response.

    Returns None if the market response does not contain LIP pool data.
    Raises LIPPoolDataError if LIP data is present but malformed.
    """
    # Check for LIP-related fields in market metadata.
    # Kalshi API field names are speculative — we check several plausible keys.
    lip_data: dict[str, Any] | None = None

    for key in ("liquidity_incentive", "lip", "reward_pool", "incentive_pool"):
        if key in market_data:
            lip_data = market_data[key]
            break

    if lip_data is None:
        # Also check top-level fields that might indicate pool info
        if "pool_size" in market_data or "reward_pool_size" in market_data:
            pool_size = market_data.get("pool_size") or market_data.get("reward_pool_size")
            start = market_data.get("reward_start_date") or market_data.get("lip_start_date")
            end = market_data.get("reward_end_date") or market_data.get("lip_end_date")
            if pool_size is not None and start is not None and end is not None:
                lip_data = {
                    "pool_size_usd": pool_size,
                    "start_date": start,
                    "end_date": end,
                }

    if lip_data is None:
        return None

    if not isinstance(lip_data, dict):
        raise LIPPoolDataError(
            f"LIP data for {market_ticker} must be a dict, got {type(lip_data).__name__}"
        )

    try:
        pool_size = float(lip_data["pool_size_usd"])
        start = _parse_date(lip_data["start_date"])
        end = _parse_date(lip_data["end_date"])
    except (KeyError, ValueError, TypeError) as exc:
        raise LIPPoolDataError(
            f"Malformed LIP data for {market_ticker}: {exc}"
        ) from exc

    now = datetime.now(timezone.utc)
    return LIPRewardPeriod(
        market_ticker=market_ticker,
        pool_size_usd=pool_size,
        start_date=start,
        end_date=end,
        active=end >= now.date(),
        source="api",
        captured_at=now,
    )


# ── DuckDB store ──────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lip_reward_periods (
    market_ticker  VARCHAR NOT NULL,
    pool_size_usd  DOUBLE NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    active         BOOLEAN NOT NULL,
    source         VARCHAR NOT NULL,
    captured_at    TIMESTAMP NOT NULL,
    UNIQUE (market_ticker, start_date, end_date)
);
"""


class LIPPoolStore:
    """DuckDB-backed store for LIP reward period data.

    Follows the CaptureStore pattern from ACT-01.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = duckdb.connect(db_path)
        self._conn.execute("SET TimeZone='UTC'")
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)

    def upsert(self, period: LIPRewardPeriod) -> None:
        """Insert or update a LIP reward period.

        On conflict (same market_ticker + start_date + end_date), updates
        pool_size_usd, active, source, and captured_at.
        """
        # DuckDB supports INSERT OR REPLACE on UNIQUE constraints
        # We delete-then-insert for clarity since DuckDB's ON CONFLICT
        # support varies by version.
        self._conn.execute(
            "DELETE FROM lip_reward_periods "
            "WHERE market_ticker = ? AND start_date = ? AND end_date = ?",
            [period.market_ticker, period.start_date, period.end_date],
        )
        self._conn.execute(
            "INSERT INTO lip_reward_periods "
            "(market_ticker, pool_size_usd, start_date, end_date, active, source, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                period.market_ticker,
                period.pool_size_usd,
                period.start_date,
                period.end_date,
                period.active,
                period.source,
                # Store as naive UTC (DuckDB TIMESTAMP has no tz)
                period.captured_at.replace(tzinfo=None)
                if period.captured_at.tzinfo is not None
                else period.captured_at,
            ],
        )

    def get_active_periods(self) -> list[LIPRewardPeriod]:
        """Return all currently-active LIP reward periods."""
        rows = self._conn.execute(
            "SELECT market_ticker, pool_size_usd, start_date, end_date, "
            "active, source, captured_at "
            "FROM lip_reward_periods WHERE active = TRUE "
            "ORDER BY market_ticker, start_date"
        ).fetchall()
        return [self._row_to_period(row) for row in rows]

    def get_periods_for_market(self, market_ticker: str) -> list[LIPRewardPeriod]:
        """Return all LIP reward periods for a specific market."""
        rows = self._conn.execute(
            "SELECT market_ticker, pool_size_usd, start_date, end_date, "
            "active, source, captured_at "
            "FROM lip_reward_periods WHERE market_ticker = ? "
            "ORDER BY start_date",
            [market_ticker],
        ).fetchall()
        return [self._row_to_period(row) for row in rows]

    def get_all_periods(self) -> list[LIPRewardPeriod]:
        """Return all LIP reward periods (active and inactive)."""
        rows = self._conn.execute(
            "SELECT market_ticker, pool_size_usd, start_date, end_date, "
            "active, source, captured_at "
            "FROM lip_reward_periods "
            "ORDER BY market_ticker, start_date"
        ).fetchall()
        return [self._row_to_period(row) for row in rows]

    def mark_expired(self, as_of: date | None = None) -> int:
        """Mark periods past their end_date as inactive.

        Returns the number of periods marked inactive.
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc).date()
        # Count before update to compute affected rows
        count_before = self._conn.execute(
            "SELECT COUNT(*) FROM lip_reward_periods "
            "WHERE end_date < ? AND active = TRUE",
            [as_of],
        ).fetchone()
        affected = count_before[0] if count_before else 0
        if affected > 0:
            self._conn.execute(
                "UPDATE lip_reward_periods SET active = FALSE "
                "WHERE end_date < ? AND active = TRUE",
                [as_of],
            )
        return affected

    def count(self) -> int:
        """Return total number of reward periods stored."""
        result = self._conn.execute(
            "SELECT COUNT(*) FROM lip_reward_periods"
        ).fetchone()
        return result[0] if result else 0

    def total_active_pool_usd(self) -> float:
        """Return sum of pool_size_usd across all active periods."""
        result = self._conn.execute(
            "SELECT COALESCE(SUM(pool_size_usd), 0.0) FROM lip_reward_periods "
            "WHERE active = TRUE"
        ).fetchone()
        return float(result[0]) if result else 0.0

    @staticmethod
    def _row_to_period(row: tuple) -> LIPRewardPeriod:
        """Convert a DuckDB row tuple to LIPRewardPeriod."""
        captured_at = row[6]
        if isinstance(captured_at, datetime) and captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        start = row[2] if isinstance(row[2], date) else date.fromisoformat(str(row[2]))
        end = row[3] if isinstance(row[3], date) else date.fromisoformat(str(row[3]))
        return LIPRewardPeriod(
            market_ticker=str(row[0]),
            pool_size_usd=float(row[1]),
            start_date=start,
            end_date=end,
            active=bool(row[4]),
            source=str(row[5]),
            captured_at=captured_at,
        )

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()

    def export_parquet(self, path: str) -> None:
        """Export lip_reward_periods to Parquet."""
        self._conn.execute(
            f"COPY lip_reward_periods TO '{path}' (FORMAT PARQUET)"
        )


# ── Refresh orchestrator ──────────────────────────────────────────────


async def refresh_lip_pools(
    *,
    store: LIPPoolStore,
    client: Any | None = None,
    series_ticker: str = "KXSOYBEANW",
    config_path: Path | None = None,
) -> int:
    """Refresh LIP pool data from config and/or API.

    Steps:
      1. Load config overrides if config_path exists.
      2. If a KalshiClient is provided, query market metadata for LIP fields.
      3. Upsert all discovered periods into the store.
      4. Mark expired periods inactive.

    Args:
        store: LIPPoolStore to persist data into.
        client: Optional KalshiClient (from ACT-03). If None, config-only mode.
        series_ticker: Series to query for (default KXSOYBEANW).
        config_path: Path to lip_pools.yaml config. None to skip config.

    Returns:
        Number of periods upserted (new + updated).

    Raises:
        LIPPoolDataError: If no data source yields any periods and
            no periods exist in the store. Fail-loud.
    """
    periods: list[LIPRewardPeriod] = []

    # Step 1: Config overrides
    if config_path is not None:
        try:
            config_periods = load_config_pools(config_path)
            periods.extend(config_periods)
            logger.info(
                "Loaded %d LIP pool periods from config %s",
                len(config_periods),
                config_path,
            )
        except FileNotFoundError:
            logger.debug("No LIP pool config at %s, skipping", config_path)

    # Step 2: API data (if client available)
    if client is not None:
        api_periods = await _fetch_api_pools(client, series_ticker)
        # Config overrides API: skip API periods that already have a config entry
        config_keys = {
            (p.market_ticker, p.start_date, p.end_date) for p in periods
        }
        for ap in api_periods:
            key = (ap.market_ticker, ap.start_date, ap.end_date)
            if key not in config_keys:
                periods.append(ap)
        logger.info(
            "Fetched %d LIP pool periods from API for %s",
            len(api_periods),
            series_ticker,
        )

    # Step 3: Upsert
    upserted = 0
    for period in periods:
        store.upsert(period)
        upserted += 1

    # Step 4: Mark expired
    expired_count = store.mark_expired()
    if expired_count > 0:
        logger.info("Marked %d expired LIP reward periods as inactive", expired_count)

    # Fail-loud: if we found nothing and store is empty, something is wrong
    if upserted == 0 and store.count() == 0:
        raise LIPPoolDataError(
            f"No LIP pool data found from any source for {series_ticker}. "
            "Provide config/lip_pools.yaml or ensure Kalshi API returns LIP data."
        )

    logger.info(
        "LIP pool refresh complete: %d upserted, %d total, $%.2f active pool",
        upserted,
        store.count(),
        store.total_active_pool_usd(),
    )

    return upserted


async def _fetch_api_pools(
    client: Any,
    series_ticker: str,
) -> list[LIPRewardPeriod]:
    """Fetch LIP pool data from Kalshi API market metadata.

    Iterates through events for the series and checks each market's
    metadata for LIP pool information.
    """
    periods: list[LIPRewardPeriod] = []

    try:
        events_resp = await client.get_events(series_ticker=series_ticker, status="open")
    except Exception as exc:
        logger.warning("Failed to fetch events for %s: %s", series_ticker, exc)
        return periods

    events = events_resp.get("events", [])
    for event in events:
        event_ticker = event.get("event_ticker", "")
        markets = event.get("markets", [])

        for market in markets:
            ticker = market.get("ticker", "")
            if not ticker:
                continue

            # Try parsing LIP data from the event-level market summary
            period = parse_api_lip_data(ticker, market)
            if period is not None:
                periods.append(period)
                continue

            # If not in event response, try fetching individual market
            try:
                market_resp = await client.get_market(ticker)
                market_detail = market_resp.get("market", market_resp)
                period = parse_api_lip_data(ticker, market_detail)
                if period is not None:
                    periods.append(period)
            except Exception as exc:
                logger.warning(
                    "Failed to fetch market detail for %s: %s", ticker, exc
                )

    return periods
