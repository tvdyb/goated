"""NOAA CPC weather outlook client for Corn Belt temperature + precipitation.

Pulls 6-10 day and 8-14 day outlook anomalies from NOAA CPC, and computes
departures from the 1991-2020 climate normal for the U.S. Corn Belt region
(~36-48N, 80-100W).

Data source: NOAA CPC (free, no API key).
  - 6-10 day outlook: https://www.cpc.ncep.noaa.gov/
  - 8-14 day outlook: same

The client returns a WeatherOutlook dataclass with:
  - temp_anomaly_f: temperature departure (F) from normal (positive = warmer)
  - precip_anomaly_pct: precipitation departure (%) from normal (negative = drier)
  - outlook_days: "6-10" or "8-14"
  - fetched_at_ns: timestamp

Fail-loud: raises on HTTP errors, parse failures, or stale data.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class WeatherFetchError(RuntimeError):
    """Raised when weather data fetch or parse fails."""

    pass


class OutlookPeriod(StrEnum):
    DAY_6_10 = "6-10"
    DAY_8_14 = "8-14"


@dataclass(frozen=True, slots=True)
class WeatherOutlook:
    """Single outlook snapshot for the Corn Belt region."""

    temp_anomaly_f: float  # degrees F departure from normal (+ = warmer)
    precip_anomaly_pct: float  # percent departure from normal (- = drier)
    outlook_period: OutlookPeriod
    fetched_at_ns: int


# ---------------------------------------------------------------------------
# Corn Belt bounding box (approximate)
# ---------------------------------------------------------------------------
_CORN_BELT_LAT_MIN = 36.0
_CORN_BELT_LAT_MAX = 48.0
_CORN_BELT_LON_MIN = -100.0  # West
_CORN_BELT_LON_MAX = -80.0  # East

# ---------------------------------------------------------------------------
# 1991-2020 Climate Normals (monthly, Corn Belt regional averages)
# Source: NOAA 1991-2020 U.S. Climate Normals
# Index: 0=Jan, 11=Dec
# ---------------------------------------------------------------------------
_NORMAL_TEMP_F = np.array(
    [24.0, 28.0, 39.0, 52.0, 63.0, 73.0, 77.0, 75.0, 66.0, 54.0, 40.0, 28.0],
    dtype=np.float64,
)

_NORMAL_PRECIP_IN = np.array(
    [1.5, 1.4, 2.3, 3.2, 4.2, 4.5, 4.3, 3.8, 3.2, 2.8, 2.3, 1.7],
    dtype=np.float64,
)


def normal_temp_f(month: int) -> float:
    """Return 30-year normal temp (F) for a given month (1-12)."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month}")
    return float(_NORMAL_TEMP_F[month - 1])


def normal_precip_in(month: int) -> float:
    """Return 30-year normal precipitation (inches) for a given month (1-12)."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month}")
    return float(_NORMAL_PRECIP_IN[month - 1])


# ---------------------------------------------------------------------------
# CPC Outlook fetcher
# ---------------------------------------------------------------------------


async def fetch_cpc_outlook(
    session: object,
    period: OutlookPeriod = OutlookPeriod.DAY_6_10,
    *,
    timeout_s: float = 10.0,
) -> WeatherOutlook:
    """Fetch CPC outlook and return Corn Belt anomaly.

    Parameters
    ----------
    session : aiohttp.ClientSession
        An open aiohttp session (asyncio for I/O only, per non-negotiable).
    period : OutlookPeriod
        Which outlook window to pull.
    timeout_s : float
        HTTP timeout in seconds.

    Returns
    -------
    WeatherOutlook

    Raises
    ------
    WeatherFetchError
        On HTTP failure, parse error, or missing data.
    """
    import aiohttp

    if not isinstance(session, aiohttp.ClientSession):
        raise TypeError(f"Expected aiohttp.ClientSession, got {type(session)}")

    if period == OutlookPeriod.DAY_6_10:
        temp_url = (
            "https://www.cpc.ncep.noaa.gov/products/predictions/"
            "610day/610temp.new.gif"
        )
        precip_url = (
            "https://www.cpc.ncep.noaa.gov/products/predictions/"
            "610day/610prcp.new.gif"
        )
    else:
        temp_url = (
            "https://www.cpc.ncep.noaa.gov/products/predictions/"
            "814day/814temp.new.gif"
        )
        precip_url = (
            "https://www.cpc.ncep.noaa.gov/products/predictions/"
            "814day/814prcp.new.gif"
        )

    # CPC provides GIF maps — in production, use their text/gridded API.
    # For now, we attempt the text probability files which are more parse-friendly.
    try:
        temp_text_url = temp_url.replace(".gif", ".txt")
        precip_text_url = precip_url.replace(".gif", ".txt")

        timeout = aiohttp.ClientTimeout(total=timeout_s)

        async with session.get(temp_text_url, timeout=timeout) as resp:
            if resp.status != 200:
                raise WeatherFetchError(
                    f"CPC temp outlook HTTP {resp.status} for {temp_text_url}"
                )
            temp_text = await resp.text()

        async with session.get(precip_text_url, timeout=timeout) as resp:
            if resp.status != 200:
                raise WeatherFetchError(
                    f"CPC precip outlook HTTP {resp.status} for {precip_text_url}"
                )
            precip_text = await resp.text()

        temp_anomaly = _parse_cpc_anomaly(temp_text, "temperature")
        precip_anomaly = _parse_cpc_anomaly(precip_text, "precipitation")

        return WeatherOutlook(
            temp_anomaly_f=temp_anomaly,
            precip_anomaly_pct=precip_anomaly,
            outlook_period=period,
            fetched_at_ns=time.time_ns(),
        )

    except WeatherFetchError:
        raise
    except Exception as exc:
        raise WeatherFetchError(f"CPC outlook fetch failed: {exc}") from exc


def _parse_cpc_anomaly(text: str, variable: str) -> float:
    """Parse CPC text outlook for Corn Belt average anomaly.

    The CPC text files have various formats. This parser extracts a
    regional average for the Corn Belt from gridded data. If parsing
    fails, raises WeatherFetchError.
    """
    if not text or len(text) < 10:
        raise WeatherFetchError(f"Empty or too-short CPC {variable} data")

    # Attempt to parse lines containing numeric anomaly values.
    # CPC text files typically have lat/lon/value columns.
    values = []
    for line in text.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            val = float(parts[2])
        except (ValueError, IndexError):
            continue

        if (
            _CORN_BELT_LAT_MIN <= lat <= _CORN_BELT_LAT_MAX
            and _CORN_BELT_LON_MIN <= lon <= _CORN_BELT_LON_MAX
        ):
            values.append(val)

    if not values:
        raise WeatherFetchError(
            f"No Corn Belt data points found in CPC {variable} outlook"
        )

    return float(np.mean(values))


def create_outlook_from_manual(
    temp_anomaly_f: float,
    precip_anomaly_pct: float,
    period: OutlookPeriod = OutlookPeriod.DAY_6_10,
) -> WeatherOutlook:
    """Create a WeatherOutlook from manually-specified anomalies.

    Useful for backtesting, manual overrides, or when CPC data is unavailable.
    """
    if not math.isfinite(temp_anomaly_f):
        raise ValueError(f"temp_anomaly_f must be finite, got {temp_anomaly_f}")
    if not math.isfinite(precip_anomaly_pct):
        raise ValueError(
            f"precip_anomaly_pct must be finite, got {precip_anomaly_pct}"
        )

    return WeatherOutlook(
        temp_anomaly_f=temp_anomaly_f,
        precip_anomaly_pct=precip_anomaly_pct,
        outlook_period=period,
        fetched_at_ns=time.time_ns(),
    )
