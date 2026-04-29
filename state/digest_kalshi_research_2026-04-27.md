# Digest — Kalshi research findings — 2026-04-27

**Author.** orchestrator (live API investigation)
**Phase scope.** Pre-Wave-0-implementation: empirical validation of F3 assumptions against Kalshi's actual API and live market state.

---

## Critical finding

**`KXSOYBEANW` is not currently a Liquidity Incentive Program (LIP)
market.** The strategy as framed in F3 assumes it is. This is a
project-level finding requiring decision.

Evidence: `GET /trade-api/v2/incentive_programs?type=liquidity&status=active&limit=100`
returned 100 active liquidity-incentive programs as of 2026-04-27.
Zero are for any `KXSOYBEAN*` market. Active LIP markets are
sports-event prediction (NBA, MLB, IPL, NHL coach), political
prediction (Trump-related, primary races), commodity *price-level*
prediction (gas prices, CPI), and macro (Mexico unemployment, UK
retail). Soybean weeklies aren't on the list.

---

## Other major findings (factual, from live API)

### KXSOYBEANW market structure — corrects an audit assumption

The audit (F1/F2/F3) framed `KXSOYBEANW` as **bucket markets**. The
live API shows them as **half-line "above-strike" markets** — each
"market" within an Event has only a `floor_strike`, no `cap_strike`,
and resolves Yes if the soybean SON-contract close exceeds the floor.

- Strike spacing: uniform 5¢ steps (e.g., 1151.99, 1156.99, 1161.99...)
- Strikes per Event: 20+ (one Event observed: `KXSOYBEANW-26MAY0114`,
  20 markets returned in one page, cursor implies more).
- Settlement source: Pyth feed, contract `SON6` (per-market
  `custom_strike.front_month_contract`).
- Settlement timer: 1 hour after expiration.
- Roll rule: switches to next month 15 business days before current
  contract's last trading day. (F3 assumed FND-2 BD; this is FND-15
  BD.)

Implication for ACT-04 (bucket grid): "buckets" must be derived
synthetically from the half-line ladder via
`Yes_bucket(ℓ_i, ℓ_{i+1}) = Yes(>ℓ_i) - Yes(>ℓ_{i+1})`. The corridor
decomposition in F3 ACT-13 is already the right design; just under-
stand it operates on independent half-lines, not on Kalshi-native
bucket primitives.

### Liquidity is real on KXSOYBEANW — but no LIP rewards

Sample orderbook (`KXSOYBEANW-26MAY0114-T1201.99`, mid-strike):
- Yes bid: 0.25 (87 contracts), 0.24 (200), 0.14 (18), 0.11 (321),
  0.09 (40), 0.07 (250), 0.03 (2022).
- Yes ask: 0.35 (85), 0.36 (200), 0.48 (101), 0.67 (101), 0.84 (48),
  0.85 (250), 0.86 (2022), 0.99 (1).
- Spread: 10¢ wide. Significant edge for tight quoting.
- Total visible depth: ~3000 contracts each side.

This is meaningful liquidity for a pure spread-capture strategy.
Without LIP, the question becomes whether spread capture net of
fees, hedge slippage, and adverse selection is positive. F1 framing.

### LIP API endpoint, contract, and economics

- **Endpoint.** `GET /trade-api/v2/incentive_programs`
- **Filters.** `status` (all/active/upcoming/closed/paid_out),
  `type` (all/liquidity/volume), `limit` (max 10000), `cursor`.
- **No auth required for read access.** Public endpoint.
- **No `market_ticker` filter** — must fetch all and filter
  client-side.
- **No WebSocket equivalent** — must poll for pool changes.
- **`period_reward`** in centi-cents (1/100th of a cent).
  Observed range: 200,000 (= $2/day) to 10,000,000 (= $100/day) per
  market.
- **`target_size_fp`** (string): observed values 250–2500 contracts.
- **`discount_factor_bps`** (int32): observed values 4000 (40%) and
  5000 (50%). This is the per-market distance-multiplier decay, not
  a fixed curve. Lower bps = steeper decay = harsher to be off the
  inside.
- **Per-market periods** are short (typically 1–7 days) and per-leg
  of multi-leg events get individual reward pools.

### Pool sizes are smaller than F3 assumed

F3 KC-LIP-01 sets the kill threshold at $50/day across all
KXSOYBEANW markets. Observed daily pools on currently-eligible
markets:

- Smallest: $2.00/day (KXUE Mexico unemployment, KXUKRETAIL,
  KXNBAMENTION).
- Median: ~$5–10/day per market.
- Largest single-market: $100/day (KXUMICHOVR Michigan over/under).
- Largest *aggregate* per Event family observed: KXTRUMPTIME has 5
  legs × $20/day = $100/day total.

If KXSOYBEANW joined LIP at these levels, with 20 strikes per Event,
expected pool would be $40–200/day per Event — at the low end of
what makes the strategy worth doing.

### Kalshi REST API auth (relevant for ACT-03)

- **Header set:** `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`,
  `KALSHI-ACCESS-TIMESTAMP` (unix ms).
- **Signature:** RSA-PSS over concatenation of
  `timestamp + HTTP_method + path`.
- **Demo environment:** `demo-api.kalshi.co` (separate API keys, fake
  money). Use this for paper-trading and integration testing.
- **Production API base:** `https://api.elections.kalshi.com/trade-api/v2/`
  (note: `elections.kalshi.com` despite covering all market types).

### WebSocket channels confirmed

Public channels (no per-channel auth): `ticker`, `trade`,
`market_lifecycle_v2`, multivariate-lifecycle, `control_frames`.
Private channels: `orderbook_delta`, `fill`, `market_positions`,
`communications`, `order_group_updates`.

ACT-05 (WS multiplex) reduction stays correct: subscribe to
`fill` + `user_orders` + `orderbook_delta` (the latter for ACT-LIP-
COMPETITOR's competitor-presence estimation).

---

## Implications for the plan

### Decision that needs to be made (urgent)

**OD-37 (NEW) — KXSOYBEANW LIP eligibility.** Three branches:

1. **Wait-and-see.** Email Kalshi support to advocate for
   KXSOYBEANW LIP inclusion; in the meantime, build to F3 assuming
   LIP eligibility will arrive. Risk: build for months on an
   assumption that never materialises.
2. **Pivot to LIP-eligible product family.** Pick a market currently
   on LIP — KXUMICHOVR ($100/day pool), KXTRUMPTIME ($20/day per
   leg), KXIPL ($5/day × 10 legs = $50/day). Each has its own
   pricing model; the engine generalises (ACT-LIP-MULTI is the lift)
   but the RND/hedge story is product-specific.
3. **Drop LIP framing.** Build for spread capture on KXSOYBEANW
   with the actual liquidity observed today (~10¢ spreads, ~3000
   contracts of depth at mid-strike). This is closer to F1 (edge-
   driven) framing but at low frequency. Economics unclear without
   a backtest.

### Other plan adjustments

- **ACT-04 documentation.** Note that "bucket" is a derived view over
  half-lines. The native Kalshi primitive is the >-strike. ACT-13's
  corridor decomposition is unchanged.
- **ACT-08 settle resolver.** Roll rule is FND-15 BD, not FND-2 BD.
  Audit had this wrong.
- **ACT-LIP-POOL.** Use `GET /trade-api/v2/incentive_programs` with
  `status=active`; refresh every few hours; filter client-side by
  market_ticker prefix matching the configured product family.
- **ACT-LIP-VIAB.** The viability check now has a binary
  preliminary outcome: "is the target product family on LIP at all?"
  If not, pivot before observing pool size dynamics.

---

## Recommended next moves

1. **Pause KXSOYBEANW-specific implementation work.** ACT-02 (soy
   yaml) and ACT-13 (corridor adapter) are general enough to keep,
   but ACT-LIP-VIAB on `KXSOYBEANW` will return NO-GO immediately
   on current data.

2. **Email Kalshi support today.** Two questions:
   - "Is `KXSOYBEANW` on the LIP roadmap? Any planned inclusion
     date?"
   - "Confirm that `discount_factor_bps` represents the maximum
     distance-multiplier decay percentage; clarify the function from
     `discount_factor_bps` to `distance_multiplier(d)` for a quote
     d cents from the inside."

3. **Run ACT-LIP-VIAB-PIVOT.** Same machinery, different target:
   pick the top 3 LIP-eligible market families by pool size
   (KXUMICHOVR, KXTRUMPTIME, KXIPL) and run the same viability
   analysis on each. Output: which family has the best
   pool/competition tradeoff for our infrastructure.

4. **Update F3 → F4** with the corrected market structure (half-
   lines not buckets), corrected roll rule (FND-15 BD), and the LIP
   eligibility issue parameterised so the same engine can target
   different product families.

---

## Sources

- [Kalshi LIP help article](https://help.kalshi.com/incentive-programs/liquidity-incentive-program)
- [Kalshi MM Program help article](https://help.kalshi.com/en/articles/13823819-how-to-become-a-market-maker-on-kalshi)
- [Kalshi API docs — Get Incentives](https://docs.kalshi.com/api-reference/incentive-programs/get-incentives)
- Live Kalshi REST API responses captured 2026-04-27.
