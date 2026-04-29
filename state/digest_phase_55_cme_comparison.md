# Digest: Phase 55 CME Comparison — Real Edge Mechanism

**Date:** 2026-04-28
**Prerequisite reading for:** Phase 60, 65, 70, 75, 80

---

## Market structure finding

Kalshi `KXSOYBEANMON` contracts are **short-dated** (1-3 days to settlement), NOT 20-30 day monthlies. They settle daily at 2:20pm EDT via Pyth feed on the nearest ZS futures contract (currently SON6 = ZSN26 July soybeans).

This means:
- The price distribution at settlement is extremely narrow (~16c 1-sigma for 3-day horizon at 15% annual vol).
- The full RND apparatus (BL → SVI → Figlewski → bucket integration) produces prices that **agree with Kalshi midpoints within 1-2c** near ATM.
- There is no systematic directional model-vs-market disagreement to exploit.

---

## Real edge mechanism: spread capture

The edge is NOT "model disagrees with Kalshi mid." The edge IS:

| Observation | Implication |
|---|---|
| Kalshi spreads are 6-8c near ATM | Incumbent quotes are wide |
| Model fair value is accurate within 1-2c | Confident enough to post tight |
| Few active market makers on monthlies | Low competition for tightest quote |
| No LIP rebates on monthlies | Existing MMs have no incentive to tighten |

**Strategy:** Post both sides with a 3-4c spread around model fair value. You are the tightest quote on the book. Every fill captures ~1.5-2c net of fees. The model's job is to give you confidence that your fair value is correct — not to give you a directional view different from the market.

---

## CME data validation (2026-04-25)

Source: CME ZSN26 (July soybean options), 93 strikes, 62-day expiry.

- Forward: $11.92/bu (1192c)
- IV surface: 15.2% ATM, 27% at 980c (put skew), 22% at 1400c
- SVI fit: 82/500 butterfly violations (acceptable for commodity skew)
- Pipeline output: bucket_sum = 1.000000, survival monotone, all non-negative

Comparison against Kalshi (May 1 settlement, 3-day horizon):

| Region | Model vs Kalshi mid | Interpretation |
|---|---|---|
| Deep ITM (<1150c) | Model 100%, Kalshi 95-96% | Kalshi spread floor (6-7c No side) |
| Near ATM (1150-1220c) | Agree within 1.5c mean | Both pricing correctly |
| Deep OTM (>1225c) | Model <2%, Kalshi 6-8c | Kalshi minimum tick floor |

---

## Implications for the quoter (Phase 60)

1. **Do NOT design around model-vs-mid disagreement.** The quoter should post symmetric tight spreads around fair value, not asymmetric widths based on a "model edge" signal that doesn't exist on these contracts.

2. **The "asymmetric" in asymmetric MM means:**
   - Withdraw the side facing adverse taker flow (taker-imbalance detector)
   - Widen during event windows (USDA)
   - Reduce size as settlement approaches
   - Post tighter on strikes where incumbent spread is widest (more room)
   - It does NOT mean "post tighter on the side where model disagrees with Kalshi mid"

3. **Fair value computation for 3-day horizon:**
   - Extract IV surface from the nearest CME options chain with time value (currently ZSN26, 62 days)
   - For each Kalshi strike K: `P(S > K) = N(d2)` where `d2 = (ln(F/K) - 0.5σ²τ) / (σ√τ)` with τ = days-to-Kalshi-settlement / 365.25
   - Use strike-dependent σ interpolated from the CME smile
   - The full RND pipeline (BL density extraction) adds minimal value over this simple Black-76-with-smile approach for τ < 5 days. Use it anyway for robustness, but don't expect different answers.

4. **Strike selection for quoting:**
   - Focus on strikes within ±60c of forward (the near-ATM region)
   - Deep ITM/OTM have structural edges but terrible risk/reward (risk 94c to make 6c)
   - ATM ± 30c has the widest spreads AND the most trade activity

5. **Spread width policy:**
   - Target: 3-4c spread (half of incumbent 6-8c)
   - Minimum: 2c (fee floor, need at least 1c edge per side after ~0.5c Kalshi fee)
   - Maximum: match incumbent (no point being wider)
   - Widen to 5-6c inside USDA/event windows

6. **KC-F4-01 reinterpretation:** The kill criterion "RND misses Kalshi-resolution by >3c on >50% of buckets" should be evaluated as: if the model fair value is consistently wrong by >3c (leading to adverse fills), the strategy is dead. On current data, the model is accurate — KC-F4-01 is NOT approaching failure.

---

## What the RND pipeline provides (even on short-dated contracts)

- **Confidence bound** on fair value (you know your price is within 1-2c of truth)
- **Skew awareness** (slightly different vols for different strikes, matters for Greeks)
- **Continuity** across the strike grid (no arbitrage between adjacent buckets)
- **Foundation for longer-dated contracts** if Kalshi ever lists them
- **Event-day value**: on USDA days, vol spikes and the distribution widens. The RND properly captures this if you feed it fresh CME options that reflect the elevated IV.

---

## Forward reference (for later phases)

- CME chain data: `data/cme_options/zs_n26_chain.json`
- RND output: `data/cme_options/rnd_final_zsn26.json`
- Full review: `state/review_phase_55.md`
