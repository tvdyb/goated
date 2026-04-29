# Phase T-70 — Weather-Driven Distribution Skew

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Context
Research synthesis §2.1: during U.S. pod-fill (Jun-Aug) and South American
pod-fill (Jan-Feb), deteriorating weather forecasts shift the soybean density
upward AND fatten the upper tail. The 2012 drought produced limit-up sequences.

NOAA GEFS ensemble forecasts (free) and ECMWF AIFS (free, +2h latency)
provide the raw weather data. The pipeline: weather → yield anomaly →
price distribution shift.

## Outputs
- `feeds/weather/gefs_client.py`:
  - Pull GEFS ensemble mean/spread for Corn Belt temperature + precipitation.
  - 6-10 day and 8-14 day outlooks.
  - Compute anomaly vs 30-year climate normal.
- `engine/weather_skew.py`:
  - Map weather anomaly to yield risk:
    - Hot + dry during pod-fill = negative yield shock = price up + tail up.
    - Cool + wet = positive yield = price down, tails narrow.
  - Output: (mean_shift_cents, vol_adjustment_pct) to apply to density.
  - Active only during growing season (Jun-Aug U.S., Jan-Feb S. America).
  - Outside growing season: returns (0, 0).
- Updated density computation: apply weather skew on top of base density.
- `tests/test_weather_skew.py`

## Data sources (all free, no API key needed)
- NOAA GEFS: `https://nomads.ncep.noaa.gov/` (ensemble forecasts)
- NOAA CPC 6-10 / 8-14 day outlook: `https://www.cpc.ncep.noaa.gov/`
- ECMWF AIFS: `https://aifs.ecmwf.int/` (open data, +2h latency)
- Climate normals: NOAA 1991-2020 normals (static download)

## Success criteria
- Weather skew activates during Jun-Aug and Jan-Feb only.
- A hot/dry forecast shifts density upward and widens.
- A cool/wet forecast narrows density.
- Outside growing season: no effect.
