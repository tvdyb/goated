# ACT-02 implementation plan

## Scope

- Gaps closed: GAP-100 — Soybean block in `config/commodities.yaml:58-60` has `stub: true` only; no `cme_symbol`, no Kalshi block, no fee schedule, no position-cap fields, no bucket-grid source.
- Code locations to touch: `config/commodities.yaml` (primary), `config/pyth_feeds.yaml` (add soy feed entry)
- New modules to create: none
- Tests to add: `tests/test_soy_config.py` — validates that the registry loads `soy` as a configured (non-stub) commodity with all required fields

## Approach

Replace the `soy` stub block in `config/commodities.yaml` with a fully-specified entry modeled on the WTI block but parameterized for CBOT soybeans and `KXSOYBEANW`. The block includes:

1. **Pyth feed**: Soybean/USD feed from Pyth Hermes. The feed_id is sourced from the Pyth price-feeds registry. `pyth_min_publishers: 5`, `pyth_max_staleness_ms: 2000` (same thresholds as WTI).

2. **CME parameters**: `cme_symbol: "ZS"`, soybean contract cycle Jan/Mar/May/Jul/Aug/Sep/Nov, FND-based roll rule (2 BD before first BD of delivery month per Phase 01), options symbol `OZS`.

3. **Model**: remains `"gbm"` — the corridor adapter (ACT-13) will route the GBM density through bucket decomposition. `vol_source`, `vol_fallback`, `drift`, `basis_model` match WTI defaults.

4. **Kalshi block**: `series: "KXSOYBEANW"`, event ticker pattern, bucket-grid source from `GET /events/{event_ticker}` endpoint, 24/7 trading hours per C07-108.

5. **Fee schedule**: taker = ceil(0.07 * P * (1-P) * 100) / 100, maker = 25% of taker. Per Phase 07 research, no commodity surcharge confirmed.

6. **Position cap**: `max_loss_dollars: 25000` — the default from Phase 07 research ($25,000 max-loss framework for commodity products, pending Appendix A verification).

7. **Event calendar**: WASDE (monthly, ~12th, 12:00 ET), Crop Progress (Mon 4:00 PM ET Apr-Nov), Export Inspections (Mon 11:00 AM ET), Grain Stocks (quarterly). These are the soy-relevant scheduled releases per Phase 01/06.

8. **Pyth feeds config**: Add a `soy` entry to `config/pyth_feeds.yaml` mirroring the WTI pattern.

Remove `stub: true` so the registry builds a `GBMTheo` instance for `soy`.

## Dependencies on frozen interfaces

None. No frozen interface contracts exist yet (`state/interfaces/` is empty).

## Risks

- Pyth soybean feed ID: sourced from Pyth's published registry but should be verified against the live Hermes endpoint before go-live. If the feed is not yet live on Pyth Hermes, the config is still correct for when it comes online; `pyth_ws.py` will raise on connection failure (fail-loud).
- Position cap $25,000 is a default assumption from Phase 07; the actual per-contract limit needs Appendix A verification (flagged in config comment).

## Done-when

- [ ] `soy` block in `config/commodities.yaml` is fully populated (no `stub: true`)
- [ ] `config/pyth_feeds.yaml` has a `soy` entry
- [ ] `Registry` loads `soy` as a configured commodity (not stub) — test passes
- [ ] All existing tests still pass
- [ ] No non-negotiable violations introduced
