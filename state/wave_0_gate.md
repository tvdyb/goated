# Wave 0 gate — 2026-04-27

**Wave goal.** LIP-ready quoting surface — sign, quote two-sided continuously at the inside, capture tape, kill cleanly, attribute pool share. Ends with ACT-LIP-VIAB go/no-go gate.

**Decision.** NO-GO

---

## Audit clean?

**Yes.** All 16 Wave 0 actions are `verified-complete` in
`state/dependency_graph.md` as of 2026-04-27. No drift escalations
open. No verify-failed actions pending.

---

## Integration tests

**637 passed, 0 failed** (`pytest tests/` — full suite, 23.58s).

No regressions across 22 test files covering all Wave 0 deliverables.

---

## Wave-specific gate criteria (Wave 0)

### Pre-condition: Is the target product family LIP-eligible?

**NO.** Per `state/digest_kalshi_research_2026-04-27.md`, live API
investigation on 2026-04-27 confirmed that `KXSOYBEANW` (and all
`KXSOYBEAN*` variants) are **not present** in Kalshi's active
Liquidity Incentive Program list.

Source: `GET /trade-api/v2/incentive_programs?type=liquidity&status=active&limit=100`
returned 100 active LIP programs. Zero match any `KXSOYBEAN*` ticker.

Active LIP markets are: sports prediction (NBA, MLB, IPL, NHL),
political prediction (Trump-related, primary races), commodity
price-level prediction (gas prices, CPI), and macro (Mexico
unemployment, UK retail). Agricultural commodity weeklies are absent.

**This is a pre-condition failure.** The entire F3 economic model —
LIP pool share as primary income — is inapplicable to `KXSOYBEANW`.
The remaining gate criteria are evaluated for completeness but are
moot given this finding.

### KC-LIP-01 — Pool sizes too small

| Criterion | Result |
|---|---|
| Observed daily LIP pool across KXSOYBEANW | **$0/day** (no LIP program exists) |
| Threshold | $50/day for 4 consecutive weeks |
| **Triggered?** | **YES — maximally. Pool is zero, not merely small.** |

### KC-LIP-02 — Competition too dense

| Criterion | Result |
|---|---|
| Projected pool share at full presence | **N/A** (no pool to share) |
| Threshold | < 5% for 2 consecutive reward periods |
| **Triggered?** | **YES — by construction. No pool, no share.** |

### KC-LIP-03 — Distance-multiplier curve too aggressive

| Criterion | Result |
|---|---|
| Assessment | Not evaluable (no LIP program on KXSOYBEANW) |
| **Triggered?** | N/A |

### ACT-LIP-VIAB code-complete?

**Yes.** The viability analysis framework (`analysis/lip_viability.py`)
is implemented, verified, and would produce a structured NO-GO report
when pointed at any data set showing zero LIP pools for the target
product family. The framework is reusable for any product family —
only the ticker filter changes.

---

## Kill criteria evaluated

| KC | Triggered? | Notes |
|---|---|---|
| KC-LIP-01 (pool too small) | **YES** | Pool is $0 — KXSOYBEANW not on LIP |
| KC-LIP-02 (competition too dense) | **YES** | No pool to share; share is undefined |
| KC-LIP-03 (distance multiplier) | N/A | No LIP program to evaluate |
| KC-LIP-04 (adverse selection > pool) | N/A | No pool |
| KC-LIP-05 (hedge cost > pool) | N/A | No pool |
| KC-LIP-06 (LIP program ended) | **PARTIAL** | LIP exists but never included KXSOYBEANW |
| KC-AUD-01 through KC-AUD-09 | Not triggered | Code quality criteria all pass |

---

## Additional findings from live API research

The digest (`state/digest_kalshi_research_2026-04-27.md`) also
surfaced corrections to audit assumptions:

1. **Market structure correction.** KXSOYBEANW markets are
   **half-line "above-strike"** (floor_strike only, no cap_strike),
   not native buckets. Bucket prices must be derived via
   `Yes_bucket(L_i, L_{i+1}) = Yes(>L_i) - Yes(>L_{i+1})`. ACT-13's
   corridor decomposition is the right design for this.

2. **Roll rule correction.** Settlement contract rolls at FND minus
   **15** business days, not FND minus 2 as ACT-08 assumed. This
   needs remediation if the project continues on KXSOYBEANW.

3. **Liquidity is real.** 10¢ spreads and ~3000 contracts of depth
   at mid-strikes. Meaningful for spread capture even without LIP.

4. **LIP pool sizes on eligible markets.** Observed range: $2–100/day
   per market. Largest aggregate: KXTRUMPTIME at ~$100/day across 5
   legs. Most markets $5–10/day.

---

## Recommendation

**NO-GO on Wave 1 under F3 (LIP-on-KXSOYBEANW) framing.**

The economic premise of F3 — that KXSOYBEANW is LIP-eligible and that
LIP pool share is the primary income stream — is empirically false as
of 2026-04-27. The kill criteria worked exactly as designed: they
caught a non-viable assumption before Waves 1–4 engineering (~28
additional actions) was committed.

**The Wave 0 engineering is NOT wasted.** All 16 actions produce
reusable infrastructure:
- Kalshi REST client, WebSocket, signing, rate limiter (ACT-03/05)
- Ticker parsing, order builder, position store, risk gates (ACT-04/06/09/12)
- Kill switch primitives (ACT-11)
- Forward-capture pipeline (ACT-01)
- Corridor pricing adapter (ACT-13)
- Fee model (ACT-10)
- LIP scoring framework — reusable on any LIP-eligible product (ACT-LIP-POOL/SCORE/VIAB)

These are product-family-agnostic building blocks. The pivot decision
is about which product family to target, not whether to discard code.

**Three pivot paths are available. Human decision required.**

See the orchestrator's recommendation below the sign-off.

---

## Sign-off

**Gate agent:** orchestrator
**Decision:** NO-GO
**Human sign-off required:** YES — before any further engineering.

---

*This is a Wave 0 NO-GO. Per prompts/09_WAVE_GATE.md §"Special
handling — Wave 0 NO-GO": the project's economic premise is broken.
Human stakeholders must decide the pivot path before engineering
resumes.*
