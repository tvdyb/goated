# Phase 25 Review: Wave 0 Integrity Audit

**Phase.** 25 -- Wave 0 Integrity Audit
**Date.** 2026-04-27
**Auditor.** Phase 25 orchestrator
**Inputs.** PREMISE.md, REVIEW_DISCIPLINE.md, wave_0_f4_reverify.md, dependency_graph.md, audit_E_gap_register.md, all Wave 0 source code

---

## 1. Test results

```
pytest tests/ -v -- 637 passed, 0 failed (25.37s)
```

Matches Phase 20's claim of 637 tests and the `wave_0_gate.md` claim. Independently re-run; no regressions.

---

## 2. Gap closure verification

Every gap claimed closed by each Wave 0 action was verified by reading the actual code at the cited location. Four independent audit agents verified the code in parallel.

### ACT-01 (capture): GAP-148, GAP-173

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-148 | Forward-captured tapes (orderbook, trades, events) not being captured | `feeds/kalshi/capture.py:76-350` — REST polling for orderbooks, trades, events with DuckDB persistence | CLOSED |
| GAP-173 | Forward-capture asset not being recorded | `feeds/kalshi/capture.py:37,107,320,348` — CaptureStore persistence, async I/O, exponential backoff | CLOSED |

### ACT-02 (soy yaml): GAP-100

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-100 | Soybean config block has `stub: true` only | `config/commodities.yaml:58-109` — full soy config with CME symbol ZS, Kalshi block, fee schedule, position cap, trading hours | CLOSED |

### ACT-03 (Kalshi client): GAP-071, GAP-072, GAP-073

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-071 | Kalshi REST/WS client absent; no httpx, no signing, no endpoint binding | `feeds/kalshi/client.py:24,51-428` — httpx AsyncClient, full REST endpoint bindings, retry logic | CLOSED |
| GAP-072 | RSA-PSS-SHA256 signing / key loader / header builder absent | `feeds/kalshi/auth.py:23,80-120` — RSA-PSS with SHA-256, MGF1, salt_length=32, base64 encoding, 3-header builder | CLOSED |
| GAP-073 | Tiered token-bucket pacer / per-endpoint cost table / 429 backoff absent | `feeds/kalshi/rate_limiter.py:18-114` — 5-tier token bucket (BASIC to PRIME), separate read/write buckets, async backoff | CLOSED |

### ACT-04 (ticker + bucket): GAP-074, GAP-075, GAP-079

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-074 | Series/Event/Market four-level ticker schema and parser absent | `feeds/kalshi/ticker.py:48-158` — ParsedSeriesTicker, ParsedEventTicker, ParsedMarketTicker dataclasses with parse/format | CLOSED |
| GAP-075 | Event endpoint floor_strike/cap_strike not consumed; no bucket-grid ingest | `feeds/kalshi/events.py:177-396` — build_bucket_grid() processes floor_strike/cap_strike, EventPuller calls API | CLOSED |
| GAP-079 | Bucket/corridor data structures, MECE check, open-ended tail handling absent | `feeds/kalshi/events.py:37-314` — Bucket dataclass, BucketGrid with MECE validation (tail checks, contiguity, finite bounds) | CLOSED |

### ACT-05 (WS multiplex): GAP-131

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-131 | Kalshi WebSocket multiplex (orderbook_delta, ticker, trade, fill, user_orders) absent | `feeds/kalshi/ws.py:56-644` — typed event dataclasses, handler registration, subscribe(), dispatch for orderbook_delta/fill/user_order channels | CLOSED |

### ACT-06 (order builder): GAP-080, GAP-081, GAP-082

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-080 | [$0.01, $0.99] quote-band gate absent | `feeds/kalshi/orders.py:30-212` — MIN_PRICE_CENTS=1, MAX_PRICE_CENTS=99, validate_price_cents() enforces band | CLOSED |
| GAP-081 | $0.01 tick rounding (with optional $0.02 override) absent | `feeds/kalshi/orders.py:34,74-383` — DEFAULT_TICK_SIZE_CENTS=1, round_to_tick() with parametric tick_size_cents | CLOSED |
| GAP-082 | Order types, TIFs, and flags not encoded | `feeds/kalshi/orders.py:40-263` — Side, Action, OrderType, TimeInForce, SelfTradePreventionType enums; OrderSpec with post_only, reduce_only, buy_max_cost | CLOSED |

### ACT-07 (24/7 calendar): GAP-087, GAP-089

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-087 | KXSOYBEANW 24/7 trading calendar not registered; only WTI session wired | `engine/event_calendar.py:81-88,164` — _soy_trading_seconds() registered as "soy" handler, uses 24/7 calendar-time accounting | CLOSED |
| GAP-089 | Friday-holiday Rule 7.2(b) roll-to-next-trading-day logic absent | `engine/event_calendar.py:101-151` — _CBOT_HOLIDAYS frozenset (2026-2027), _is_cbot_trading_day(), settle_date_roll() with forward roll | CLOSED |

### ACT-08 (settle resolver): GAP-076, GAP-077, GAP-078

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-076 | Appendix-A reference-price-mode loader absent | `engine/cbot_settle.py:78-82,237-274` — load_reference_price_mode() with cbot_daily_settle/cbot_vwap/kalshi_snapshot modes | CLOSED |
| GAP-077 | CBOT Rule 813 daily-settle resolver and front-month roll calendar absent | `engine/cbot_settle.py:36-44,59-69,194-225` — ZS_MONTH_CODES, ZSContract with ticker property (e.g. ZSK26), front_month() | CLOSED |
| GAP-078 | Soybean FND logic and roll-window resolver absent | `engine/cbot_settle.py:141-172` — first_notice_date(), roll_date() with _subtract_business_days(fnd, 2) | CLOSED |

### ACT-09 (positions): GAP-083, GAP-116, GAP-119

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-083 | Position-limit accounting (Rule 5.19 max-loss dollars) absent | `state/positions.py:110-293` — MarketPosition.max_loss_cents, event_max_loss_cents(), total_max_loss_cents() | CLOSED |
| GAP-116 | Per-bucket inventory store / position registry absent | `state/positions.py:89-240` — PositionStore keyed by market_ticker, MarketPosition with signed qty and cost basis | CLOSED |
| GAP-119 | Per-bucket / per-Event signed dollar-exposure tracker absent | `state/positions.py:128-272` — EventExposure dataclass, get_event_exposure(), get_all_event_exposures() | CLOSED |

### ACT-10 (fees): GAP-007, GAP-152

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-007 | Kalshi taker fee ceil(0.07*P*(1-P)*100)/100 and 25% maker rate not modelled | `fees/kalshi_fees.py:37-108` — taker_fee() and maker_fee() with correct formula, taker_rate=0.07, maker_fraction=0.25 | CLOSED |
| GAP-152 | Maker/taker fee model and round-trip cost subtraction absent | `fees/kalshi_fees.py:111-282` — round_trip_cost() computing buy+sell fees, FeeSchedule wrapper | CLOSED |

### ACT-11 (kill primitives): GAP-171

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-171 | Kill-switch primitives (DELETE batch + order-group trigger) absent | `engine/kill.py:80-461` — batch_cancel_all() with retry, KillSwitch class with add_trigger()/check_and_fire(), TriggerCondition protocol | CLOSED |

### ACT-12 (risk gates): GAP-118, GAP-120

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-118 | Aggregate net-delta cap on unhedged portfolio absent | `engine/risk.py:223-235,292-306` — pre-trade check vs aggregate_delta_cap, post-trade check, raises RiskBreachError | CLOSED |
| GAP-120 | Risk-gating stage J (per-bucket/aggregate-delta/scenario thresholds) absent | `engine/risk.py:208-341` — pre-trade gate (delta+per-Event+max-loss), post-trade gate, kill-trigger integration via make_kill_trigger() | CLOSED |

### ACT-13 (corridor adapter): GAP-005

| GAP | Register description | Code evidence | Verdict |
|-----|---------------------|---------------|---------|
| GAP-005 | Bucket payoff 1{l_i <= S_T < u_i} and corridor decomposition D(l)-D(u) not implemented | `engine/corridor.py:38-177` — _corridor_prices() numba kernel: out[0]=1-prob_above[0], out[i]=prob_above[i-1]-prob_above[i], out[N-1]=prob_above[N-2]; sum-to-1 gate raises CorridorSumError | CLOSED |

---

## 3. Additional gaps from dependency_graph.md

The dependency graph claims additional gaps closed beyond the Phase 25 prompt's explicit list. These were also verified by the audit agents:

| Action | Extra GAPs | Status |
|--------|-----------|--------|
| ACT-06 | GAP-122 (post_only default) | CLOSED — `orders.py:280` defaults post_only=True |
| ACT-09 | GAP-117, GAP-125 | CLOSED — per-bucket tracking and cost-basis accounting in positions.py |
| ACT-12 | GAP-119 (shared with ACT-09) | CLOSED — risk.py references positions store for exposure checks |

---

## 4. Phase 20 F4 adaptation cross-check

Each finding from Phase 20's report was independently verified against the current codebase.

### FND-01 (WARN): ACT-08 roll rule is FND-2 BD, not FND-15 BD

**Phase 20 claim:** `engine/cbot_settle.py:165-172` uses FND minus 2 business days.
**Independent verification:** Confirmed. `roll_date()` at line 172 calls `_subtract_business_days(fnd, 2)`. Docstring at line 166 says "2 business days before FND." For Kalshi's reference-contract switching on monthlies, this should be FND-15 BD per live API investigation. Scoped to F4-ACT-01.
**Severity:** warn
**Accuracy of Phase 20:** Correct.

### FND-02 (WARN): commodities.yaml lacks KXSOYBEANMON entry

**Phase 20 claim:** `config/commodities.yaml:73` has `series: "KXSOYBEANW"` only.
**Independent verification:** Confirmed. Line 73 reads `series: "KXSOYBEANW"`. No `KXSOYBEANMON` entry exists anywhere in the file. Scoped to F4-ACT-01.
**Severity:** warn
**Accuracy of Phase 20:** Correct.

### FND-03 (INFO): All other Wave 0 actions are natively F4-compatible

**Phase 20 claim:** 13 of 16 actions require zero code changes; code is series-agnostic.
**Independent verification:** Confirmed.
- `ticker.py:37-44`: regex `[A-Z][A-Z0-9]+` handles both KXSOYBEANW and KXSOYBEANMON.
- `corridor.py:38-67`: generic boundary decomposition, operates on any MECE-validated strike grid.
- `capture.py:88`: constructor accepts `series_ticker` param, default is just a constant.
- `orders.py`: OrderSpec.ticker is a plain string, no series validation.
- `ws.py`: subscriptions accept market_tickers list, no series filtering.
- `event_calendar.py:81-88`: 24/7 handler is cadence-agnostic (weekly vs monthly doesn't affect tau).
- `positions.py`: aggregates by event_ticker string via parse_market_ticker().
- `kill.py`: batch cancel works on order IDs, event filtering uses string prefix.
- `risk.py`: limits read from config by commodity, series-agnostic logic.
**Severity:** info
**Accuracy of Phase 20:** Correct.

---

## 5. Verify.md audit

All 16 Wave 0 verify.md files were confirmed present with PASS verdicts in the Phase 20 report, and all 16 actions show `verified-complete` status in `dependency_graph.md`. Cross-referencing:

| Action | dependency_graph status | Phase 20 verdict | Consistent |
|--------|------------------------|-------------------|------------|
| ACT-01 | verified-complete | PASS | Yes |
| ACT-02 | verified-complete | PASS | Yes |
| ACT-03 | verified-complete | PASS | Yes |
| ACT-04 | verified-complete | PASS | Yes |
| ACT-05 | verified-complete | PASS | Yes |
| ACT-06 | verified-complete | PASS | Yes |
| ACT-07 | verified-complete | PASS | Yes |
| ACT-08 | verified-complete | PASS | Yes |
| ACT-09 | verified-complete | PASS | Yes |
| ACT-10 | verified-complete | PASS | Yes |
| ACT-11 | verified-complete | PASS | Yes |
| ACT-12 | verified-complete | PASS | Yes |
| ACT-13 | verified-complete | PASS | Yes |
| ACT-LIP-POOL | verified-complete | PASS | Yes |
| ACT-LIP-SCORE | verified-complete | PASS | Yes |
| ACT-LIP-VIAB | verified-complete | PASS | Yes |

---

## 6. Findings summary

### FAIL-severity findings

None.

### WARN-severity findings

**FND-25-01 (WARN): ACT-08 roll rule offset is FND-2 BD, not FND-15 BD**
- Location: `engine/cbot_settle.py:165-172`
- Claimed: gap closed (FND logic + roll window)
- Reality: gap IS closed for the original F3 scope (CBOT physical delivery roll). For F4 (Kalshi reference-contract switching on monthlies), the offset must change from 2 to 15.
- Remediation: scoped to F4-ACT-01. Does not block PASS — the code correctly implements what Wave 0 specified; the F4 adaptation is documented.

**FND-25-02 (WARN): commodities.yaml lacks KXSOYBEANMON series entry**
- Location: `config/commodities.yaml:73`
- Claimed: soy config complete (GAP-100 closed)
- Reality: GAP-100 IS closed — soy is no longer stub. But config only covers KXSOYBEANW, not KXSOYBEANMON.
- Remediation: scoped to F4-ACT-01. Does not block PASS — Wave 0 targeted KXSOYBEANW.

### INFO-severity findings

**FND-25-03 (INFO): capture.py default series is KXSOYBEANW**
- Location: `feeds/kalshi/capture.py:48`
- Constructor accepts series_ticker param (line 88). Config-only change for F4.

**FND-25-04 (INFO): All 24 gap closures verified against actual code**
- Zero discrepancies between claimed and actual gap closures.
- Every GAP-id cited in dependency_graph.md was traced to concrete code implementing the described functionality.

---

## 7. Verdict

**PASS**

Justification:
1. **Test suite passes.** 637/637 tests pass, matching Phase 20 and wave_0_gate.md claims.
2. **Zero FAIL-severity findings.** No gap claimed closed is actually open.
3. **All 24 gap closures confirmed.** Each GAP-id was independently verified by reading actual code at the cited locations.
4. **Phase 20 report is accurate.** All three findings (FND-01, FND-02, FND-03) independently confirmed.
5. **All 16 verify.md files show PASS.** Consistent with dependency_graph.md.
6. **F4 adaptation needs documented.** Two WARN-severity items (roll offset, monthly config) are scoped to F4-ACT-01 and do not block Wave 0 integrity.

Wave 0 engineering carries forward cleanly into F4. The codebase is ready for F4 implementation phases.
