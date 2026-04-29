# Review — Phase 15: M0 Spike Validation

**Date.** 2026-04-27
**Reviewer.** review agent (independent of Phase 10 executor)
**Reviewed artifacts.**
- `research/m0_spike_soy_monthly.ipynb` (18 cells)
- `state/digest_phase_10_m0_spike.md`
- Kalshi live API (re-pulled independently)
- Mathematical verification (BL, SVI, Black-76, Durrleman)

---

## Verdict: FAIL

Three FAIL-severity findings. The notebook cannot execute to completion
and cannot produce real comparison data due to API field name mismatches
and a numpy 2.x incompatibility.

---

## Findings

### F-01. FAIL — Notebook crashes on `np.trapz` (removed in numpy 2.x)

**File:** `research/m0_spike_soy_monthly.ipynb`, cells `xhfbdz88mg`, `c4biz97plhw`
**Claim:** Notebook is runnable end-to-end.
**Evidence:** System numpy is 2.4.4. `np.trapz` was removed in numpy 2.0
(replaced by `np.trapezoid`). The notebook uses `np.trapz` in at least 6
locations across the BL density and SVI-smoothed density cells.
**Impact:** Notebook crashes at Step 5a. No density is computed. All
downstream cells fail.
**Fix:** Replace all `np.trapz(...)` with `np.trapezoid(...)` or
`from scipy.integrate import trapezoid`.

---

### F-02. FAIL — API field name mismatch: market snapshot prices

**File:** `research/m0_spike_soy_monthly.ipynb`, cells `akkxkha8rcw` and `vv70rh5sem`
**Claim:** Notebook extracts `yes_bid`, `yes_ask`, `last_price` from market data.
**Evidence:** Independent API pull of `KXSOYBEANW-26APR2417` markets shows:
- Actual field names: `yes_bid_dollars`, `yes_ask_dollars`, `last_price_dollars`
- Notebook checks: `m.get("yes_bid")`, `m.get("yes_ask")`, `m.get("last_price")`
- All three return `None` for every market.

Additionally, the API returns prices as **dollar strings** (e.g., `"0.9900"`)
not cent integers. The notebook's scaling logic (`lp / 100 if lp > 1`) is
designed for cent integers and would be wrong even if field names matched.

**Impact:** No bid/ask/last_price data is extracted from any market. The
notebook's midpoint reconstruction falls through all three branches
(bid/ask, last_price, trades) — see F-03 for the trades branch.

**Verified data (independent pull):**
```
KXSOYBEANW-26APR2417-T1140.99:
  floor_strike: 1140.99           (correctly parseable)
  yes_bid_dollars: "0.0000"       (notebook looks for yes_bid → None)
  yes_ask_dollars: "1.0000"       (notebook looks for yes_ask → None)
  last_price_dollars: "0.9900"    (notebook looks for last_price → None)
  result: "yes"                   (correctly parseable)
  expiration_value: "1176.88"     (settlement price — not used by notebook)
```

---

### F-03. FAIL — API field name mismatch: trade prices

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `vv70rh5sem`
**Claim:** Trades endpoint provides `yes_price` or `price` for VWAP midpoint reconstruction.
**Evidence:** Independent API pull of trades for `KXSOYBEANW-26APR2417-T1175.99`:
- Actual field name: `yes_price_dollars` (string, e.g., `"0.9900"`)
- Notebook checks: `t.get("yes_price", t.get("price"))` → both return `None`

**Impact:** The trades fallback also produces no prices. Combined with F-02,
`kalshi_mid = None` for ALL markets. The summary table (cell `li972ok9co9`)
produces zero rows. The notebook falls through to the synthetic-noise
fallback in cell `ldp90e382ad`, which generates random Kalshi midpoints —
this is not a valid comparison.

---

### W-01. WARN — Settlement price available but not used

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `p4ue22mmw7`
**Claim:** Settlement price inferred from YES/NO resolution flip.
**Evidence:** The API provides `expiration_value: "1176.88"` on every market.
The notebook infers settlement as the midpoint of the flip:
`(1175.99 + 1180.99) / 2 = 1178.49`. The error is 1.61 (0.14%).
**Impact:** The synthetic chain is centered at 1178.49 instead of 1176.88.
All density computations inherit this offset. Minor for 5c Kalshi
bucket spacing but avoidable.
**Fix:** Use `m.get("expiration_value")` for the spot price when available.

---

### W-02. WARN — last_price_dollars values are end-of-life, not mid-life

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `vv70rh5sem`
**Evidence (independent pull):**
```
Strike    Result  last_price_dollars
1090.99   yes     0.9900    (deep ITM near expiry)
1150.99   yes     0.9800    (ITM near expiry)
1175.99   yes     0.9900    (just ITM near expiry)
1180.99   no      0.0800    (just OTM near expiry)
1190.99   no      0.5100    (traded at 51c earlier — informative)
1200.99   no      0.5200    (traded at 52c earlier — informative)
1220.99   no      0.2700    (traded at 27c earlier — informative)
```
**Impact:** Even if F-02 were fixed, most YES-resolved strikes have
`last_price = 0.99` and most far-OTM NO strikes have near-zero prices.
Only strikes near the settlement boundary (1180-1220) have informative
mid-life prices. A proper comparison needs time-stamped trade data from
WELL BEFORE settlement, not last-ever-price.
**Mitigation:** The trades endpoint has `created_time` which could filter
to "trades >24h before settlement." The notebook does not do this.

---

### W-03. WARN — Verdict threshold is overly generous

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `ldp90e382ad`
**Claim:** Phase 10 spec defines REJECTED as "model not closer on >40% of strikes."
**Evidence:** The elif condition is `frac_model_closer >= 0.40 or mean_advantage >= 0`.
The `or mean_advantage >= 0` clause means a scenario with model closer on only
20% of strikes but +0.1c average advantage gets INCONCLUSIVE, not REJECTED.
**Impact:** The REJECTED verdict is essentially unreachable unless the model
is BOTH less accurate AND has negative advantage. This weakens the kill
criterion evaluation.

---

### W-04. WARN — `np.trapz` deprecated; will fail on numpy >= 2.0

**File:** `research/m0_spike_soy_monthly.ipynb`, cells `xhfbdz88mg`, `c4biz97plhw`
**Note:** This is the same root cause as F-01 but listed separately for
the `%pip install` cell which does not pin numpy version.
The `%pip install numpy` in cell `t4h3o21y9g` will install numpy >= 2.0
on any modern Python, causing immediate crash.
**Fix:** Either pin `numpy<2` or replace `np.trapz` with
`np.trapezoid` (numpy 2.x) or `scipy.integrate.trapezoid`.

---

### I-01. INFO — `custom_strike` field does not exist in API response

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `akkxkha8rcw`
**Evidence:** The market object has `floor_strike` (float) and
`strike_type: "greater"`. There is no `custom_strike` field.
**Impact:** None — the notebook's fallback `m.get("floor_strike")`
correctly parses the strike. The `custom_strike` branch is dead code.

---

### I-02. INFO — No settled KXSOYBEANMON events exist

**Evidence:** `GET /events?series_ticker=KXSOYBEANMON&status=settled` returns
empty list. Also empty for `KXCORNMON`.
**Impact:** The notebook correctly falls back to `KXSOYBEANW` (3 settled
events available). This is documented as a limitation in the digest.

---

### I-03. INFO — Black-76 pricing formula is mathematically correct

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `p4ue22mmw7`
**Verification:** Independent computation of ATM call with S=K=1000,
sigma=0.2, T=1, r=0 yields C=79.6557, matching the notebook's function
to 4 decimal places.

---

### I-04. INFO — BL density extraction formula is mathematically correct

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `xhfbdz88mg`
**Verification:** BL applied to Black-76 calls with flat vol recovers
a density peaked near spot (995.0 for S=1000, consistent with lognormal
mode < mean). Area pre-normalization: 0.73 (expected < 1 due to finite
grid truncation). Post-normalization: 1.000000. Survival at spot: 0.459
(reasonable for 1-month lognormal with slight negative drift from
discounting).

---

### I-05. INFO — SVI formula and Durrleman condition are correct

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `hihoq4in5`
**Verification:**
- SVI at k=0: w = a + b*sigma = 0.014, matches analytical. Correct.
- SVI symmetry at rho=0: w(+k) = w(-k). Confirmed.
- Durrleman g(k) for test SVI params: min = 0.706, all non-negative.
  Formula `(1 - k*w'/(2*w))^2 - w'^2/4*(1/w+1/4) + w''/2` matches
  Gatheral-Jacquier (2014).

---

### I-06. INFO — Summary table arithmetic formulas are correct

**File:** `research/m0_spike_soy_monthly.ipynb`, cell `li972ok9co9`
- Model error: `|model_yes - realized| * 100` (cents). Correct.
- Kalshi error: `|kalshi_mid - realized| * 100` (cents). Correct.
- Advantage: `kalshi_error - model_error` (positive = model better). Correct.

Note: the formulas are correct but will never execute on real data due to
F-02 and F-03 (all `kalshi_mid` values are None).

---

### I-07. INFO — Digest verdict of INCONCLUSIVE is consistent

**File:** `state/digest_phase_10_m0_spike.md`
**Evidence:** The digest states "INCONCLUSIVE (expected for M0 spike)"
and correctly identifies that a synthetic chain makes the comparison
circular. This is honest and appropriate. However, the digest does NOT
mention that the notebook is broken (F-01 through F-03) — it presents
the synthetic fallback as the expected path, when in reality the notebook
would crash before reaching it (F-01).

---

## Independent API verification summary

| Check | Notebook claim | Independent result | Match? |
|---|---|---|---|
| KXSOYBEANMON settled events | Falls back to KXSOYBEANW | Correct: 0 settled MON events | YES |
| KXSOYBEANW settled events | Uses most recent | 3 events available, most recent: KXSOYBEANW-26APR2417 | YES |
| Market count | Parsed from API | 30 markets | Verifiable |
| Strike parsing | Uses floor_strike | floor_strike present (1090.99 to 1235.99) | YES |
| Resolution outcomes | yes/no from result field | Confirmed: YES for <=1175.99, NO for >=1180.99 | YES |
| Settlement price | Inferred from YES/NO flip | expiration_value=1176.88 (not used by notebook) | PARTIAL |
| Midpoint data | From yes_bid/yes_ask/last_price | Fields are yes_bid_dollars/yes_ask_dollars/last_price_dollars | NO (F-02) |
| Trade prices | From yes_price in trades | Field is yes_price_dollars | NO (F-03) |

---

## Mandatory fixes before re-review

1. Replace all `np.trapz` with `np.trapezoid` or `scipy.integrate.trapezoid` (F-01).
2. Fix market field names: `yes_bid_dollars`, `yes_ask_dollars`, `last_price_dollars` (F-02).
3. Fix trade field name: `yes_price_dollars`, and parse as `float(str_value)` not cents (F-03).
4. Use `expiration_value` for settlement price when available (W-01).
5. Filter trades by `created_time` to exclude end-of-life trades (W-02).
6. Tighten INCONCLUSIVE/REJECTED verdict boundary (W-03).

---

## FAIL

The notebook has 3 FAIL-severity findings (F-01, F-02, F-03) that prevent
it from executing and from producing real comparison data. The mathematical
methodology (BL, SVI, Durrleman, bucket integration) is correct. The Kalshi
API integration for event discovery and strike/resolution parsing works.
But the price data extraction is broken, and the notebook crashes on
numpy >= 2.0.

Phase 10 must be re-executed with these fixes before Phase 15 can PASS.
