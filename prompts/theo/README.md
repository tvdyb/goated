# Theo Stack — `prompts/theo/`

This directory contains the prompt stack for improving the theoretical
pricing (theo) of the Kalshi commodity market maker. Each phase builds
a specific edge from the research synthesis (Phase 10) into a working
component wired into `deploy/lip_mode.py` and `deploy/main.py`.

**Context:** The system is LIVE on Kalshi KXSOYBEANMON with a synthetic
GBM theo (hardcoded 15% vol, forward guessed from Kalshi quotes). This
stack replaces that with progressively better fair values using data
sources that are either free or already available.

---

## Execution order

Run each phase in a **fresh Claude Code session**. Each prompt is
self-contained — it reads `CLAUDE.md`, `prompts/build/PREMISE.md`,
and the specific files it needs.

| Phase | File | Purpose | Data needed | Est. time |
|---|---|---|---|---|
| T-00 | `T00_PYTH_FORWARD.md` | Wire Pyth real-time ZS price as forward | None (free API) | 1-2 hr |
| T-05 | `T05_REVIEW_PYTH.md` | **Review.** Validate Pyth forward vs Kalshi quotes | None | 30 min |
| T-10 | `T10_KALSHI_IMPLIED_VOL.md` | Back out vol from Kalshi ATM bid/ask | None (own data) | 1-2 hr |
| T-15 | `T15_REVIEW_IMPLIED_VOL.md` | **Review.** Validate implied vol vs historical | None | 30 min |
| T-20 | `T20_SEASONAL_VOL.md` | Monthly vol regime overlay | None (lookup table) | 1 hr |
| T-25 | `T25_MARKOUT_TRACKER.md` | Per-bucket fill markout tracking (1m/5m/30m) | None (own fills) | 2-3 hr |
| T-30 | `T30_REVIEW_MARKOUT.md` | **Review.** Analyze markout data, identify toxic buckets | None | 1 hr |
| T-35 | `T35_QUEUE_AMEND.md` | Replace cancel-and-replace with amend for LIP | None (API change) | 2 hr |
| T-40 | `T40_IBKR_OPTIONS_CHAIN.md` | Pull ZS options chain via IB Gateway API | IBKR account + IB Gateway | 2-3 hr |
| T-45 | `T45_REVIEW_IBKR_DATA.md` | **Review.** Validate IBKR chain vs synthetic | IBKR running | 1 hr |
| T-50 | `T50_WIRE_RND_PIPELINE.md` | Replace synthetic GBM with full RND pipeline | IBKR data flowing | 2-3 hr |
| T-55 | `T55_REVIEW_RND_LIVE.md` | **Review.** Compare RND theo vs synthetic on live fills | IBKR running | 1-2 hr |
| T-60 | `T60_WASDE_NLP.md` | Auto-parse USDA WASDE releases → density updates | None (free USDA data) | 3-4 hr |
| T-65 | `T65_REVIEW_WASDE.md` | **Review.** Backtest WASDE density updates on history | None | 1-2 hr |
| T-70 | `T70_WEATHER_SKEW.md` | GEFS/ECMWF weather → yield → distribution skew | None (free NOAA/ECMWF) | 4-6 hr |
| T-75 | `T75_REVIEW_WEATHER.md` | **Review.** Validate weather skew on historical events | None | 2 hr |
| T-80 | `T80_FLB_OVERLAY.md` | Favorite-longshot bias correction from settled data | Historical settlements | 2-3 hr |
| T-85 | `T85_GOLDMAN_ROLL.md` | Goldman roll window detection + density drift | None (public calendar) | 1 hr |
| T-90 | `T90_INTEGRATION_TEST.md` | Full theo stack integration test + PnL attribution | All above | 2-3 hr |

**Total estimated: 30-45 hours of agent time.**

---

## Dependency table

```
T-00 ──> T-05 ──> T-10 ──> T-15 ──┐
                                    ├──> T-20 ──> T-25 ──> T-30 ──> T-35
                                    │
T-40 ──> T-45 ──> T-50 ──> T-55 ──┘
                                    │
T-60 ──> T-65 ──────────────────────┤
T-70 ──> T-75 ──────────────────────┤
T-80 ───────────────────────────────┤
T-85 ───────────────────────────────┤
                                    └──> T-90
```

Key gates:
- T-05 (Pyth review) gates T-10. If Pyth feed is unreliable, fall back to Kalshi-inferred forward.
- T-15 (implied vol review) gates T-20 (seasonal vol builds on calibrated vol).
- T-45 (IBKR review) gates T-50 (need validated data before wiring RND).
- T-55 (RND live review) is the biggest gate — proves whether full RND beats synthetic.
- T-90 requires all prior phases.

Parallelizable:
- T-00 and T-40 can run concurrently (Pyth is independent of IBKR).
- T-60, T-70, T-80, T-85 can all run concurrently (independent density overlays).
- T-25 can start anytime after T-15 (just needs the bot running with fills).

---

## Data source prerequisites

Before starting this stack, the operator must have:

1. **Kalshi API keys** (already have)
2. **IBKR margin account** with CME ag market data subscription (~$10/mo) — needed for T-40+
3. **IB Gateway** installed and running — needed for T-40+

The following are free and require no accounts:
- Pyth Network Hermes API (T-00)
- USDA WASDE releases from usda.gov (T-60)
- NOAA GEFS ensemble forecasts (T-70)
- ECMWF AIFS open data (T-70)
