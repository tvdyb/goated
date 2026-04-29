# Phase T-10 — Kalshi-Implied Vol Calibration

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-05 must show PASS (reliable forward price).

## Context
The synthetic GBM uses a hardcoded 15% annualized vol. This is a guess.
We can do better by back-calculating the implied vol from Kalshi's own
ATM bid/ask prices — the market is telling us what vol it's pricing.

Given: forward F, strike K, time to expiry T, and the Kalshi mid-price
for "above K" = P_market, we can solve for sigma in:

    P_model(F, K, T, sigma) = N(d2) where d2 = (ln(F/K) - 0.5*sig^2*T) / (sig*sqrt(T))

by bisecting on sigma until P_model ≈ P_market.

The ATM strike (closest to forward) gives the most stable estimate.
Multiple near-ATM strikes can be averaged for robustness.

## Inputs
1. `deploy/lip_mode.py` — current `_synthetic_rnd` method with hardcoded vol.
2. `deploy/main.py` — same.
3. Pyth forward (from T-00).
4. Kalshi orderbook data (already pulled each cycle).

## Outputs
- `engine/implied_vol.py` — module that:
  - Takes forward, list of (strike, market_mid) pairs, time to expiry.
  - Bisects for sigma on 2-4 near-ATM strikes.
  - Returns calibrated vol (annualized).
  - Falls back to 15% if calibration fails (< 3 liquid strikes, or vol outside [5%, 80%]).
- Updated `deploy/lip_mode.py` — uses calibrated vol instead of hardcoded 15%.
- Updated `deploy/main.py` — same.
- `tests/test_implied_vol.py` — unit tests with known option prices.

## Success criteria
- Calibrated vol changes when the market moves (not stuck at 15%).
- Vol is reasonable for soybeans (typically 12-25% for nearby, higher in summer).
- Vol updates each cycle from fresh orderbook data.
- Fallback to 15% works when ATM strikes are illiquid.
- All existing tests pass.

## Key notes
- Use `scipy.special.ndtr` (not `norm.cdf`) per non-negotiable.
- Bisection bounds: [0.01, 1.50] for annualized vol.
- Only use strikes within 10c of forward for calibration (near-ATM).
- Weight by inverse bid-ask spread (tighter = more informative).
- This is NOT hot-path code — runs once per cycle (30s), bisection is fine.
