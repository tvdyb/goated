# Wave 1 (F4) status

**Goal.** Deliver the RND pipeline (CME options -> IV surface -> BL density -> SVI -> Figlewski tails -> bucket integration) and validate RND accuracy against settled Kalshi monthly outcomes (M0 gate on KC-F4-01).

**Action count.** 4 (F4-ACT-01, F4-ACT-02, F4-ACT-03, F4-ACT-15)

**Critical path.** F4-ACT-01 (S) -> F4-ACT-02 (L) -> F4-ACT-03 (XL) -> F4-ACT-15 (M)

---

## Track assignments

| Track | Actions | Type | Notes |
|---|---|---|---|
| T1 | F4-ACT-01 -> F4-ACT-03 (IV refactor sub-stage first, then BL+SVI+Figlewski+bucket after T2 delivers) -> F4-ACT-15 | serial | Critical path. Starts with monthlies adaptations (S, ~1d), then the IV surface refactor sub-stage of F4-ACT-03 while T2 works on CME ingest. Converges with T2 at the BL density extraction step. Ends with M0 spike notebook. |
| T2 | F4-ACT-02 (after F4-ACT-01 completes) | serial | CME options chain ingest. Unblocked once F4-ACT-01 lands. Delivers chain data that F4-ACT-03's BL+bucket stages consume. |

**Parallelism note.** F4-ACT-03 is decomposable:
- Sub-stage 1 (IV surface refactor): depends on F4-ACT-01 only. Can start while F4-ACT-02 is in flight.
- Sub-stages 2-5 (BL extraction, SVI fitter, Figlewski tails, bucket integration): depend on F4-ACT-02's chain data. Must wait for T2.

This means T1 and T2 can overlap for ~1-2 weeks during the F4-ACT-02 / F4-ACT-03-sub1 window, reducing the critical path from ~6 weeks to ~4 weeks.

---

## Cross-track sync points

| Sync point | From | To | Condition |
|---|---|---|---|
| SP-01 | F4-ACT-01 | F4-ACT-02 | F4-ACT-01 verified-complete (commodities.yaml updated, roll rule fixed) |
| SP-02 | F4-ACT-01 | F4-ACT-03 sub-stage 1 | F4-ACT-01 verified-complete |
| SP-03 | F4-ACT-02 | F4-ACT-03 sub-stages 2-5 | CME chain ingest producing valid IV data for at least 1 ZS expiry |
| SP-04 | F4-ACT-03 | F4-ACT-15 | RND pipeline callable offline with historical chain data |

---

## Pre-actions from Phase 20/25 findings

Both WARN-severity findings from Phase 20/25 are already scoped into F4-ACT-01:

| Finding | Severity | Remediation | Action |
|---|---|---|---|
| FND-25-01: ACT-08 roll rule FND-2 BD | warn | Change offset from 2 to 15 BD in `cbot_settle.py:165-172` | F4-ACT-01 |
| FND-25-02: commodities.yaml lacks KXSOYBEANMON | warn | Add KXSOYBEANMON Kalshi block | F4-ACT-01 |
| FND-25-03: capture.py default is KXSOYBEANW | info | Pass KXSOYBEANMON at instantiation | F4-ACT-01 |

No additional pre-actions needed.

---

## M0 spike status (from Phase 15)

Phase 15 returned **FAIL** on the M0 spike notebook (`research/m0_spike_soy_monthly.ipynb`). The failure is **technical** (3 bugs), NOT an edge-hypothesis rejection:

| Finding | Type | Impact |
|---|---|---|
| F-01: `np.trapz` removed in numpy 2.x | crash | Notebook cannot execute past Step 5a |
| F-02: API field names `yes_bid` vs `yes_bid_dollars` | data | No bid/ask prices extracted |
| F-03: Trade field `yes_price` vs `yes_price_dollars` | data | No trade prices extracted |

The mathematical methodology (BL density, SVI, Durrleman butterfly-arb condition) was independently validated as correct. The notebook's comparison of RND-vs-Kalshi-midpoint was never executed with real data -- it fell through to a synthetic-noise fallback.

**Resolution:** F4-ACT-15 supersedes the old notebook. It will:
1. Use the production RND pipeline (F4-ACT-03) instead of inline code.
2. Use real CME options chain data (F4-ACT-02) instead of synthetic chains.
3. Use correct Kalshi API field names (fixes F-02, F-03).
4. Use `np.trapezoid` (fixes F-01).

**Decision gate (DG-01):** After F4-ACT-02 delivers real CME chain data and before F4-ACT-03's BL step integrates it, run a quick sanity check: does the raw options chain look reasonable (put-call parity holds, no stale quotes dominate, at least 10 strikes with non-trivial OI)? If NO, escalate to operator on CME data source viability (OD-37).

---

## Action details

### F4-ACT-01 — Wave 0 adaptations for monthlies

| Field | Value |
|---|---|
| Effort | S (~1 day) |
| Track | T1 (first) |
| Wave 0 deps | ACT-02 (met), ACT-04 (met), ACT-08 (met) |
| F4 deps | none |
| Deliverables | 1. `cbot_settle.py` roll rule -> FND-15 BD (configurable via yaml). 2. `commodities.yaml` KXSOYBEANMON block. 3. Ticker parser verification for monthly format. 4. Capture target config for KXSOYBEANMON. |
| Tests | Update `test_cbot_settle.py` roll assertions; add KXSOYBEANMON ticker parsing tests; corridor adapter with monthly-spaced strikes. |
| Code locations | `engine/cbot_settle.py`, `config/commodities.yaml`, `feeds/kalshi/ticker.py`, `feeds/kalshi/capture.py` |

### F4-ACT-02 — CME options chain ingest

| Field | Value |
|---|---|
| Effort | L (~1-2 weeks) |
| Track | T2 |
| Wave 0 deps | ACT-02 (met) |
| F4 deps | F4-ACT-01 |
| Deliverables | 1. `feeds/cme/options_chain.py` — EOD chain pull for ZS (front 3 expiries). 2. Put-call parity prune. 3. Chain-to-IV converter. 4. CBOT daily settlement price pull. |
| Tests | Chain pull with synthetic data; put-call parity prune correctness; settle pull format validation. |
| Code locations | `feeds/cme/` (new package), `config/commodities.yaml` (vendor config) |
| Decision gate | OD-37 (CME options chain vendor): IB API historical options (default, cheapest), CME DataMine (fallback), Quandl (alternative). Resolve at action start. |

### F4-ACT-03 — RND extractor pipeline

| Field | Value |
|---|---|
| Effort | XL (~2-3 weeks) |
| Track | T1 (after F4-ACT-01; sub-stage 1 overlaps with T2) |
| Wave 0 deps | ACT-13 (met) |
| F4 deps | F4-ACT-01, F4-ACT-02 |
| Deliverables | 1. IV surface refactor: `(commodity, strike, expiry) -> IV` grid. 2. BL density extraction: `f_T = e^(rT) * d^2C/dK^2`. 3. SVI fitter per expiry with butterfly/calendar arb constraints. 4. Figlewski piecewise-GEV tail attachment. 5. Bucket integration with sum-to-1 gate. 6. Variance rescaling for non-co-terminal expiries. 7. TheoOutput shape change (bid/ask + per-bucket Greeks). |
| Tests | Analytical parity: BL on BS call surface recovers lognormal density. SVI fit reproduces known smile. Figlewski tails integrate to expected mass. Sum-to-1 within tolerance. Non-co-terminal rescaling preserves total probability. |
| Code locations | `state/iv_surface.py` (refactor), `models/rnd_pipeline.py` (new), `models/svi.py` (new), `models/figlewski.py` (new), `models/base.py` (TheoOutput), `validation/sanity.py` |
| Gaps closed | GAP-006, GAP-036, GAP-037, GAP-038, GAP-041, GAP-042, GAP-043, GAP-044, GAP-045, GAP-049, GAP-101, GAP-003 |

### F4-ACT-15 — M0 spike notebook (GO/NO-GO gate)

| Field | Value |
|---|---|
| Effort | M (~2-3 days) |
| Track | T1 (last) |
| Wave 0 deps | ACT-01 (met) |
| F4 deps | F4-ACT-01, F4-ACT-02, F4-ACT-03 |
| Deliverables | Jupyter notebook that: 1. Pulls historical CME ZS options chain. 2. Pulls settled KXSOYBEANMON outcomes. 3. Runs F4-ACT-03 RND pipeline offline. 4. Scores RND-implied bucket prices against realized outcomes. 5. Outputs GO/NO-GO on KC-F4-01. |
| Kill criterion | KC-F4-01: RND misses by >3c on >50% of buckets across 4+ settled Events -> project halts. |
| Phase 15 bug fixes | np.trapezoid (not np.trapz), yes_bid_dollars/yes_ask_dollars/yes_price_dollars field names, expiration_value for settlement price. |
| Data depth | OD-40: 4 settled monthly Events minimum. If fewer exist, verdict is INCONCLUSIVE and Wave 2 proceeds with a re-evaluation gate at F4-ACT-09. |

---

## External dependencies

| Dependency | Status | Impact | Mitigation |
|---|---|---|---|
| IB account with CME futures permission | Pending (OD-11 resolved, account application in progress) | Blocks F4-ACT-05 (Wave 2), not Wave 1 | Paper-trading account for development |
| CME options chain data source (OD-37) | Unresolved | Blocks F4-ACT-02 | Default: IB API historical options (free). Fallback: CME DataMine |
| Settled KXSOYBEANMON events | Unknown count | May limit F4-ACT-15 M0 depth | If <4 settled events, verdict is INCONCLUSIVE; re-evaluate at F4-ACT-09 with more data |
| Phase 15 M0 spike | FAIL (technical bugs) | Does not block Wave 1 | Bugs are fixed in F4-ACT-15 which supersedes the old notebook |

---

## Wave-end gate

Wave 1 is complete when ALL of the following hold:
1. F4-ACT-01 verified-complete (monthly adaptations landed, tests pass).
2. F4-ACT-02 verified-complete (CME chain ingest producing valid data for at least 1 ZS expiry).
3. F4-ACT-03 verified-complete (RND pipeline produces per-bucket Yes-prices from real chain data, sum-to-1 within tolerance).
4. F4-ACT-15 produces a GO/NO-GO verdict on KC-F4-01.
   - **GO:** Wave 2 proceeds.
   - **NO-GO:** Project halts. Report to operator.
   - **INCONCLUSIVE** (insufficient settled data): Wave 2 proceeds with a mandatory re-evaluation gate at F4-ACT-09 (M0 backtest validator).

---

## Risks and escalations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| CME data source unavailable or too expensive | Low | Blocks F4-ACT-02 | IB API (free) is default. CME DataMine delayed EOD is free. Escalate to operator only if both fail. |
| M0 spike INCONCLUSIVE due to insufficient settled monthly data | Medium | Cannot confirm edge hypothesis | Proceed to Wave 2 with re-evaluation gate. The backtest harness (F4-ACT-09) will accumulate more data. |
| SVI fitter fails butterfly/calendar arb on >25% of fits | Low | KC-AUD-03 triggered | Investigate SABR/BP fallback (GAP-039/040, currently deferred). Escalate to operator. |
| F4-ACT-03 XL effort underestimated | Medium | Critical path extends | Sub-stage decomposition allows incremental delivery. IV refactor can be verified independently. |
| Phase 15 FAIL indicates deeper M0 methodology problems | Very Low | Edge hypothesis untestable | Mathematical methodology was independently validated as correct (I-03 through I-06 in Phase 15 review). Only API integration was broken. |

---

## Estimated wall-clock

| Phase | Duration | Parallelism |
|---|---|---|
| F4-ACT-01 (monthlies adapt) | ~1 day | Sequential (unblocks everything) |
| F4-ACT-02 + F4-ACT-03 sub-stage 1 (CME ingest + IV refactor) | ~1-2 weeks | Parallel on T1/T2 |
| F4-ACT-03 sub-stages 2-5 (BL + SVI + Figlewski + bucket) | ~1-2 weeks | Sequential after T2 delivers |
| F4-ACT-15 (M0 spike) | ~2-3 days | Sequential after F4-ACT-03 |
| **Total** | **~3-5 weeks** | 2 parallel tracks |

---

## Execution order summary

```
Day 1:     F4-ACT-01 (monthlies adapt, S)
           |
Day 2:     +-- T1: F4-ACT-03 sub-stage 1 (IV surface refactor)
           +-- T2: F4-ACT-02 (CME options chain ingest)
           |       |
Week 2-3:  |       +-- [DG-01: chain data sanity check]
           |       |
           +-- SP-03: T2 delivers chain data to T1
           |
Week 3-4:  T1: F4-ACT-03 sub-stages 2-5 (BL + SVI + Figlewski + bucket)
           |
Week 4-5:  T1: F4-ACT-15 (M0 spike notebook)
           |
           +-- [M0 GATE: GO / NO-GO / INCONCLUSIVE on KC-F4-01]
```
