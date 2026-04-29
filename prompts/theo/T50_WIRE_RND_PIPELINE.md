# Phase T-50 — Wire Full RND Pipeline into Live System

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-45 must show PASS (IBKR data is valid and RND pipeline produces correct output).

## Context
The full RND pipeline (`engine/rnd/pipeline.py`) was built in Phase 50 of the
build stack: BL → SVI → Figlewski → bucket integration. It's been tested on
synthetic and real CME data. Now wire it into the live market maker to replace
the synthetic GBM.

## Outputs
- Updated `deploy/main.py`:
  - On startup: pull IBKR options chain.
  - Each cycle: if chain is fresh (< 15 min), use `compute_rnd()`. Else refresh.
  - Fall back to synthetic GBM if IBKR is down or chain pull fails.
- Updated `deploy/lip_mode.py` — same RND integration.
- Updated `deploy/dashboard.py` — show "RND" or "Synthetic" as pricing source.

## Success criteria
- Live system uses RND-derived fair values when IBKR data is available.
- Fallback to synthetic works seamlessly.
- RND theo differs from synthetic by ≤ 2c on ATM strikes, more on wings.
- No increase in adverse selection (RND should reduce it).
- Dashboard clearly shows which pricing source is active.
