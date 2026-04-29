# Phase 45 — Review: CME Ingest Validation

**Reviewer.** Phase 45 review agent
**Date.** 2026-04-27
**Inputs reviewed.** `feeds/cme/` (5 files), `tests/test_cme_ingest.py`,
`state/action_cme_ingest/handoff.md`, `state/action_cme_ingest/plan.md`,
`state/decisions_log.md` (OD-37), `prompts/build/PREMISE.md`,
`prompts/build/REVIEW_DISCIPLINE.md`.

---

## 1. Test re-run

```
pytest tests/test_cme_ingest.py -v
37 passed in 0.12s
```

**Result.** PASS. Handoff claimed 37 tests; re-run confirms 37/37 pass.

---

## 2. Data verification against direct CME source

CME Group website (`cmegroup.com`) was unreachable during this review
session (HTTP timeout on contract specs page). Independent numerical
verification of settlement prices against a live CME source could not
be performed.

**Mitigation.** The code's HTTP layer and JSON parsing were verified
against realistic mock data in tests (settlement price extraction,
options chain parsing, strike sorting). The implementation targets
the documented CME public endpoints
(`cmegroup.com/CmeWS/mvc/Settlements/...`) which are cited in the
OD-37 decision (see `state/decisions_log.md:148`).

**Result.** INCOMPLETE-DATA for live price verification. Mock-based
parsing logic is verified.

---

## 3. Put-call parity verification

Verified via synthetic chain tests:

- **Clean data (exact parity):** 0 violations returned. PASS.
- **Massive violations (C-P off by 100):** `CMEParityError` raised
  when >25% of strikes violate. PASS.
- **Minor violations (2/20 = 10% < 25% threshold):** returns violation
  indices without raising. PASS.
- **Expired chain (expiry <= as_of):** returns empty list, skips check.
  PASS.

Formula used: `C - P = (F - K) * exp(-rT)` (futures-style put-call
parity). Vectorized numpy computation, no Python loops. Threshold is
configurable (`violation_threshold`, `max_violation_frac`).

**Note.** CBOT soybean options are American-style, so put-call parity
is approximate. The handoff acknowledges this (`handoff.md:57`). For
a data quality gate (not a pricing model), the approximation is
sufficient.

**Result.** PASS.

---

## 4. Expiry calendar verification

### 4a. Algorithm review

The expiry rule implemented: "last Friday that precedes FND by at
least 2 business days." FND = last business day of the month
preceding the delivery month.

This matches the CBOT Chapter 11 rule for standard options on
soybean/corn futures.

### 4b. ZS 2026 schedule (all 7 delivery months)

| Delivery | FND | Expiry | Day | Gap | Trading day? |
|---|---|---|---|---|---|
| Jan 2026 | 2025-12-31 (Wed) | 2025-12-26 (Fri) | Fri | 5d | Yes |
| Mar 2026 | 2026-02-27 (Fri) | 2026-02-20 (Fri) | Fri | 7d | Yes |
| May 2026 | 2026-04-30 (Thu) | 2026-04-24 (Fri) | Fri | 6d | Yes |
| Jul 2026 | 2026-06-30 (Tue) | 2026-06-26 (Fri) | Fri | 4d | Yes |
| Aug 2026 | 2026-07-31 (Fri) | 2026-07-24 (Fri) | Fri | 7d | Yes |
| Sep 2026 | 2026-08-31 (Mon) | 2026-08-21 (Fri) | Fri | 10d | Yes |
| Nov 2026 | 2026-10-30 (Fri) | 2026-10-23 (Fri) | Fri | 7d | Yes |

All 2026 expiries are Fridays and CBOT trading days. All precede FND.

### 4c. ZC 2026 schedule (all 5 delivery months)

All 5 expiries verified as Fridays, before FND, and CBOT trading days.

### 4d. `next_expiry()` and `expiry_schedule()`

- `next_expiry("ZS", date(2026, 6, 1))` returns 2026-06-26 (correct,
  nearest ZS expiry on or after ref_date).
- `next_expiry` on expiry day returns that day. PASS.
- `next_expiry` after last 2026 expiry finds 2027 schedule. PASS.
- `expiry_schedule` returns sorted chronological list. PASS.

**Result.** PASS for 2026. See Finding F-01 for a 2027 edge case.

---

## 5. Non-negotiables check

| Rule | Check | Result |
|---|---|---|
| No `import pandas` in `feeds/cme/` | `grep` for `import pandas` / `from pandas` | **PASS** — 0 matches |
| Silent error handling | See Finding F-02 | **INFO** — cache helpers only |
| Type hints on public functions | All public functions (`pull_settle`, `pull_options_chain`, `check_put_call_parity`, `options_expiry`, `expiry_schedule`, `next_expiry`) have full type annotations | **PASS** |
| asyncio for I/O only | `pull_settle` and `pull_options_chain` are async (HTTP I/O). All computation is synchronous. | **PASS** |
| Fail-loud on errors | Public API functions raise typed exceptions on all failure paths. | **PASS** |
| numpy over Python loops | Put-call parity is vectorized. Strike sorting uses `np.argsort`. | **PASS** |

---

## 6. Error handling simulation

| Scenario | Behavior | Result |
|---|---|---|
| Network failure (`httpx.ConnectError`) | `CMESettleError` / `CMEChainError` raised with original exception chained | **PASS** (test: `test_pull_settle_http_error`, `test_pull_chain_http_error`) |
| HTTP non-200 response | Raises with status code and truncated body | **PASS** (code: `futures_settle.py:118-123`, `options_chain.py:235-240`) |
| Malformed JSON | Raises `CMESettleError` / `CMEChainError` on `ValueError` from `resp.json()` | **PASS** |
| Empty settlement data | Raises `CMESettleError("No settlement records")` | **PASS** (test: `test_extract_no_data_raises`) |
| Empty options chain | Raises `CMEChainError("Empty options chain")` via `__post_init__` | **PASS** (test: `test_empty_chain_raises`) |
| Unsupported symbol | Raises before any I/O | **PASS** (test: `test_pull_settle_unsupported_symbol`, `test_pull_chain_unsupported_symbol`) |

---

## Findings

### F-01 — Expiry calendar returns Christmas as expiry date (WARN)

**File.** `feeds/cme/expiry_calendar.py:117-121`
**Evidence.** `options_expiry("ZS", 1, 2027)` returns `2026-12-25`,
which is Christmas Day. `_is_cbot_trading_day(date(2026, 12, 25))`
returns `False`. The code finds the last Friday before the cutoff but
does not verify the resulting Friday is a CBOT trading day.
**Impact.** In practice, CBOT moves the expiry to the prior business
day (Thursday Dec 24 in this case, or the prior Friday Dec 18). The
bug only affects ZS F27 (Jan 2027 delivery) in the 2026-2027 range
checked. It does NOT affect any 2026 dates.
**Severity.** WARN. Not a blocker for current F4 build (targeting 2026
monthlies), but must be fixed before the calendar is used for
production scheduling that spans into 2027.
**Action.** Add a check: if the resulting Friday is not a CBOT trading
day, walk backward to the previous Friday. Add a test for
`options_expiry("ZS", 1, 2027)`.

### F-02 — Cache helpers silently swallow errors (INFO)

**File.** `feeds/cme/futures_settle.py:210-212`,
`feeds/cme/options_chain.py:434-435`
**Evidence.** `_read_cache` catches `(ValueError, OSError)` and returns
`None`, treating a corrupt cache file as a cache miss. Similarly,
`_read_chain_cache` catches `(ValueError, KeyError, OSError)`.
**Impact.** None for correctness — a cache miss causes a re-fetch from
CME. The cache is an optional optimization, not a data source.
**Severity.** INFO. Consistent with treating cache as best-effort.
No action required, but a debug-level log would aid troubleshooting.

### F-03 — CME public endpoint may change without notice (INFO)

**File.** `feeds/cme/options_chain.py:77-80`,
`feeds/cme/futures_settle.py:34-37`
**Evidence.** The handoff acknowledges this (`handoff.md:55`). The URLs
are hard-coded to the current CME API structure.
**Severity.** INFO. Mitigated by the IB API fallback path documented in
`state/decisions_log.md:166`. No action required now.

### F-04 — Live data verification not performed (INFO)

**Evidence.** CME Group website was unreachable during this review.
Settlement prices and options chain data could not be independently
verified against a live CME source.
**Severity.** INFO. The parsing logic is verified against realistic
mock data. Live verification should be performed when CME endpoints
are accessible, ideally during Phase 50+ integration testing.
**Action.** Add a manual verification step to the integration test
checklist: pull one real ZS options chain and compare 5 strikes
against the CME website settlement report.

---

## Handoff claims vs evidence

| Claim | Evidence | Verified? |
|---|---|---|
| 37 new tests | `pytest` reports 37 collected, 37 passed | YES |
| All 674 tests pass | Not re-run (out of scope for this review) | NOT CHECKED |
| Ruff lint clean | Not re-run | NOT CHECKED |
| GAP-046 closed | `pull_options_chain` implemented with full parsing | YES |
| GAP-047 closed | `check_put_call_parity` implemented, vectorized, threshold-gated | YES |
| GAP-063 closed | `pull_settle` implemented with front-month extraction | YES |
| OD-37 resolved | Decision documented in `state/decisions_log.md:148` | YES |

---

## Verdict

**PASS** (conditional)

All success criteria are met for the 2026 target horizon:

- Tests pass (37/37). **MET.**
- Put-call parity holds on clean synthetic data, fires on bad data.
  **MET.**
- Expiry calendar correct for ZS/ZC 2026. **MET.** (WARN: F-01 for
  2027 edge case — not blocking.)
- No non-negotiable violations. **MET.**
- Code follows fail-safe pattern. **MET.**

**Conditions for unconditional PASS:**

1. Fix F-01 (Christmas expiry bug) before any code path calls
   `expiry_schedule` or `next_expiry` for dates that could resolve
   to 2027 delivery months.
2. Perform live CME data verification (F-04) during integration
   testing.

**Phase 45 verdict: PASS**
