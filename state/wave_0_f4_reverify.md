# Wave 0 F4 Re-verification Report

**Phase.** 20 -- Verify Wave 0 Integrity Under F4
**Date.** 2026-04-27
**Auditor.** Phase 20 orchestrator

---

## 1. Test results

```
pytest tests/ -- 637 passed, 0 failed (24.37s)
```

Matches the 637 tests claimed in `state/wave_0_gate.md`. No regressions.

---

## 2. Verify.md audit

All 16 Wave 0 verify.md files exist with PASS verdicts dated 2026-04-27.

| Action | Verdict | Date | Consistent with dependency_graph.md? |
|---|---|---|---|
| ACT-01 (capture) | PASS | 2026-04-27 | Yes |
| ACT-02 (soy yaml) | PASS | 2026-04-27 | Yes |
| ACT-03 (Kalshi client) | PASS | 2026-04-27 | Yes |
| ACT-04 (ticker + bucket) | PASS | 2026-04-27 | Yes |
| ACT-05 (WS multiplex) | PASS | 2026-04-27 | Yes |
| ACT-06 (order builder) | PASS | 2026-04-27 | Yes |
| ACT-07 (24/7 calendar) | PASS | 2026-04-27 | Yes |
| ACT-08 (settle resolver) | PASS | 2026-04-27 | Yes |
| ACT-09 (positions) | PASS | 2026-04-27 | Yes |
| ACT-10 (fees) | PASS | 2026-04-27 | Yes |
| ACT-11 (kill primitives) | PASS | 2026-04-27 | Yes |
| ACT-12 (risk gates) | PASS | 2026-04-27 | Yes |
| ACT-13 (corridor adapter) | PASS | 2026-04-27 | Yes |
| ACT-LIP-POOL (pool ingest) | PASS | 2026-04-27 | Yes |
| ACT-LIP-SCORE (score tracker) | PASS | 2026-04-27 | Yes |
| ACT-LIP-VIAB (viability) | PASS | 2026-04-27 | Yes |

---

## 3. Per-action F4 adaptation assessment

| Action | F4 adaptation check | Result | Severity | Notes |
|---|---|---|---|---|
| ACT-01 (capture) | Does REST poller handle `KXSOYBEANMON`? | READY | info | Default is `KXSOYBEANW` (`capture.py:48`) but constructor accepts `series_ticker` param (`capture.py:88`). Config-only change at instantiation. |
| ACT-02 (soy yaml) | Does `commodities.yaml` have `KXSOYBEANMON` entry? | NEEDS CONFIG | warn | `commodities.yaml:73` has `series: "KXSOYBEANW"` only. A `KXSOYBEANMON` Kalshi block must be added (or the existing entry updated). Flagged for F4-ACT-01. |
| ACT-03 (REST client) | Is client series-agnostic? | READY | info | All methods accept ticker strings as parameters. No hardcoded series references in logic. |
| ACT-04 (ticker + bucket) | Does parser handle `KXSOYBEANMON-*`? | READY | info | Regex `_EVENT_RE` and `_MARKET_RE` (`ticker.py:37-44`) use generic `[A-Z][A-Z0-9]+` prefix. Handles both `KXSOYBEANW` and `KXSOYBEANMON` identically. |
| ACT-05 (WS multiplex) | Are subscriptions ticker-agnostic? | READY | info | Subscriptions accept `market_tickers` list. No series filtering or validation. |
| ACT-06 (order builder) | Is builder market-agnostic? | READY | info | `OrderSpec.ticker` is a plain string. Quote-band `[1c, 99c]` and tick size 1c are universal across Kalshi. |
| ACT-07 (calendar) | Does it handle monthly Event cadence? | READY | info | 24/7 soybean handler (`event_calendar.py:84-88`) computes pure calendar time. Cadence (weekly vs monthly) does not affect tau calculation. Friday-holiday roll applies to both. |
| ACT-08 (settle resolver) | Roll rule: FND-2 BD vs FND-15 BD? | **FINDING** | **warn** | `cbot_settle.py:165-172` implements FND - 2 BD. Per `state/digest_kalshi_research_2026-04-27.md`, Kalshi's actual roll rule for soybean contracts is FND - **15** BD. This discrepancy must be fixed in F4-ACT-01. The code is correct for CBOT physical delivery roll; it is wrong for Kalshi's reference-contract switching. |
| ACT-09 (positions) | Does store handle monthly Events? | READY | info | Aggregates by `event_ticker` string extracted via `parse_market_ticker()`. Series-agnostic. |
| ACT-10 (fees) | Same fee model for monthlies? | READY | info | Fee formula is price-dependent, not series-dependent. Config must define fees for the new series (handled by F4-ACT-01 config update). |
| ACT-11 (kill primitives) | Are primitives market-agnostic? | READY | info | `batch_cancel_all()` works on order IDs. Event/market filtering uses string prefix matching. |
| ACT-12 (risk gates) | Are gates market-agnostic? | READY | info | Delta cap, per-Event cap, and max-loss are read from config by commodity. Config must define position caps for monthlies (handled by F4-ACT-01). |
| ACT-13 (corridor adapter) | Works on half-line markets? | READY | info | `corridor.py:38-67` implements generic boundary decomposition: `out[i] = prob_above[i-1] - prob_above[i]`. Operates on any MECE-validated strike grid. Exactly the right structure for `KXSOYBEANMON` half-line markets. |
| ACT-LIP-POOL | Not used in F4 | N/A | info | Retained for optionality. Ticker-generic code. No adaptation needed. |
| ACT-LIP-SCORE | Not used in F4 | N/A | info | Retained for optionality. Ticker-generic code. No adaptation needed. |
| ACT-LIP-VIAB | Not used in F4 | N/A | info | Retained for optionality. Reusable on any product family. No adaptation needed. |

---

## 4. Findings summary

### FND-01 (WARN): ACT-08 roll rule is FND-2 BD, not FND-15 BD

**Location.** `engine/cbot_settle.py:165-172`
**Description.** The `roll_date()` function computes FND minus 2 business days. Per live API investigation (`state/digest_kalshi_research_2026-04-27.md`), Kalshi switches the reference contract 15 business days before FND, not 2. The current code is correct for CBOT physical delivery roll timing but incorrect for Kalshi's reference-contract selection on `KXSOYBEANMON` (and `KXSOYBEANW`).
**Impact.** If used as-is for monthlies, the theo engine would reference the wrong ZS contract for approximately 2.5 weeks before each roll.
**Remediation.** F4-ACT-01 must change the offset from 2 to 15 (or make it configurable via `commodities.yaml`). Already documented in the F4 plan (`audit/audit_F4_refactor_plan_asymmetric_mm.md` section 3, section 10 F4-ACT-01).

### FND-02 (WARN): commodities.yaml lacks KXSOYBEANMON entry

**Location.** `config/commodities.yaml:72-77`
**Description.** The soy config block has `kalshi.series: "KXSOYBEANW"` only. No `KXSOYBEANMON` series or separate commodity entry exists. All production code is series-agnostic, but the config layer must be extended.
**Impact.** Cannot instantiate capture, fees, or risk gates for `KXSOYBEANMON` without config update.
**Remediation.** F4-ACT-01 must add `KXSOYBEANMON` to `commodities.yaml` (new Kalshi block or separate commodity entry). Already documented in the F4 plan.

### FND-03 (INFO): All other Wave 0 actions are natively F4-compatible

13 of 16 actions require zero code changes. The 3 LIP-specific actions are retained for optionality. The production codebase was designed series-agnostic from the start, validating the Wave 0 engineering quality.

---

## 5. Overall verdict

**ADAPTATIONS-NEEDED**

Wave 0 code integrity is confirmed: all 16 actions pass verification, all 637 tests pass, and the dependency graph is consistent. However, two findings require remediation before F4 Wave 1 can proceed:

1. **FND-01 (WARN):** ACT-08 roll rule offset must change from FND-2 BD to FND-15 BD.
2. **FND-02 (WARN):** `commodities.yaml` must add `KXSOYBEANMON` series configuration.

Both are already scoped into **F4-ACT-01** (Wave 0 adaptations for monthlies, effort S). No other Wave 0 action requires code changes. The Wave 0 engineering carries forward cleanly into F4.

---

## 6. Consistency with F4 plan

The F4 plan (`audit/audit_F4_refactor_plan_asymmetric_mm.md` section 3) already documents both findings:

| F4 plan statement | This audit's finding | Consistent? |
|---|---|---|
| "ACT-08: **Needs fix** -- Roll rule is FND-15 BD, not FND-2 BD. Fix in F4-ACT-01" | FND-01 confirms FND-2 BD in code | Yes |
| "ACT-02: Add `KXSOYBEANMON` Kalshi block (F4-ACT-01)" | FND-02 confirms no monthly entry | Yes |
| "ACT-04: Parser already handles `KX*MON` ticker format" | Confirmed: regex is series-agnostic | Yes |
| "ACT-13: Already implements half-line corridor decomposition" | Confirmed: generic boundary math | Yes |
| "ACT-07: Monthlies also trade 24/7; calendar logic unchanged" | Confirmed: 24/7 soy handler | Yes |

No surprises. The F4 plan's "What carries forward" section is accurate.
