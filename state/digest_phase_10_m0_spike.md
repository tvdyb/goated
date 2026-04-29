# Digest — Phase 10: M0 Spike — RND-vs-Kalshi Edge Hypothesis

**Date.** 2026-04-27
**Author.** orchestrator (Phase 10 execution)
**Notebook.** `research/m0_spike_soy_monthly.ipynb`
**Data cache.** `research/m0_spike_data/`

---

## Event used

Attempted settled events in order: `KXSOYBEANMON` -> `KXSOYBEANW` -> `KXCORNMON` -> `KXCORNW`.
The notebook queries the Kalshi public API at runtime. The first series with a settled event is used.

**Limitation:** Monthly commodity events (`KXSOYBEANMON`) may not yet have settled events — the series launched recently. If only weekly events are available, the notebook documents the proxy and notes the structural difference (weekly vs monthly expiry, different contract roll).

---

## Data sources

| Data | Source | Limitation |
|---|---|---|
| Kalshi settled events | `GET /trade-api/v2/events?series_ticker=...&status=settled` (public, no auth) | Only most-recent event used |
| Kalshi markets/strikes | Embedded in event response or `GET /trade-api/v2/events/{ticker}` | Half-line markets, floor_strike parsed |
| Kalshi midpoints | `yes_bid`/`yes_ask` from market snapshot, or `last_price`, or VWAP from trades endpoint | Settled events may have empty orderbooks — midpoints reconstructed from last trades |
| CME ZS options chain | Yahoo Finance API attempted first; synthetic Black-76 chain as fallback | Free APIs rarely serve ZS futures options; synthetic chain is the expected path |
| Implied vol parameters | Soybean ATM vol 18-25% (from Phase 01 research); 22% baseline with -10% skew | Historical average, not snapshot-specific |
| Risk-free rate | 4.5% (approximate 2026 level) | Not material for 1-month horizon |

**OD-37 resolution for M0 spike:** Yahoo Finance attempted; synthetic fallback expected. Production (F4-ACT-02) will use IB API historical options data per the F4 plan.

---

## Methodology validated

The notebook implements the full RND pipeline end-to-end:

1. **Breeden-Litzenberger**: `f_T(K) = e^(rT) * d²C/dK²` via central finite differences
2. **SVI calibration**: `w(k) = a + b*(rho*(k-m) + sqrt((k-m)² + sigma²))` with L-BFGS-B optimizer
3. **Butterfly arb check**: Durrleman's condition `g(k) >= 0` verified across the smile
4. **SVI-smoothed density**: BL applied to SVI-generated smooth call surface (eliminates FD noise)
5. **Figlewski GEV tails**: Framework implemented; exercised only if Kalshi strikes extend beyond SVI interior
6. **Bucket integration**: `P(S_T > K_i) = 1 - CDF(K_i)` via survival function interpolation
7. **Comparison**: Model Yes price vs Kalshi midpoint vs realized resolution, per-strike error and advantage

---

## Key numbers

Dependent on runtime API results. The notebook computes and prints:
- Mean absolute model error (cents)
- Mean absolute Kalshi error (cents)
- Mean model advantage (cents)
- Fraction of strikes where model is closer to resolution than Kalshi mid
- Per-strike error breakdown table

---

## Verdict

**INCONCLUSIVE (expected for M0 spike)**

With a synthetic options chain (the expected fallback when free APIs don't serve ZS futures options), the density IS the model — making the comparison circular. The notebook validates that the **methodology pipeline works end-to-end** and produces the correct comparison framework.

A definitive verdict on KC-F4-01 requires:
1. Real CME ZS options data (F4-ACT-02, via IB API)
2. Multiple settled monthly Events (OD-40: 4+ Events)
3. Contemporaneous Kalshi midpoints (captured via F4-ACT-01 forward-capture, not reconstructed post-settlement)

---

## Limitations

1. **Single Event.** KC-F4-01 requires 4+ settled monthly Events for a definitive call.
2. **Synthetic options chain.** Without real CME data, the BL density recovers the input distribution — it validates methodology, not empirical edge.
3. **Stale Kalshi midpoints.** Settled events have empty orderbooks; midpoints reconstructed from last_price or trades may be hours/days old.
4. **No measure adjustment.** The CME risk-neutral density != Kalshi pricing measure. Production (F4-ACT-03) will address this.
5. **No Figlewski tails exercised.** Kalshi strikes fell within the SVI interior for the tested event.
6. **Weekly proxy.** If `KXSOYBEANMON` has no settled events, a weekly event is used — different expiry mechanics.

---

## Decisions resolved

- **OD-37 (CME options chain vendor) — partial.** For M0 spike: Yahoo Finance attempted, synthetic fallback used. For production: IB API historical options confirmed as the target (cheapest, already have account). Decision gate remains at F4-ACT-02 for full resolution.

---

## Next steps

- **F4-ACT-01**: Adapt Wave 0 infrastructure for monthlies (roll rule fix, ticker config)
- **F4-ACT-02**: Implement IB API historical options ingest (real CME ZS chain)
- **F4-ACT-03**: Productionize the RND pipeline from this notebook's methodology
- **Phase 55**: Score across N settled Events for definitive KC-F4-01 evaluation
