# Audit Phase D — Topic 4: Kalshi Contract Handling

Auditor: derivatives quant, contract-handling lane.
Inputs consumed:
- `audit/audit_C_phase07_kalshi_contract.md` (C07 claims, 1–115).
- `audit/audit_C_phase09_kalshi_stack.md` (C09 claims, 1–83) — tagged `contract`
  rows only.
- `audit/audit_A_cartography.md` for module-scope resolution.
- Phase B deep-dives that nominally touch the Kalshi adjacency:
  `audit_B_engine-pricer.md`, `audit_B_engine-calendar.md`,
  `audit_B_engine-scheduler.md`, `audit_B_state-market-surfaces.md`,
  `audit_B_validation-sanity.md`. None of them describes a module that
  implements the Kalshi-side surface; this is documented at length in the
  scope section below.

Severity vocabulary used in this file: `blocker`, `major`, `minor`,
`nice-to-have`. Gap-class vocabulary: `missing`, `wrong`, `partial`,
`already-good`, `divergent-intentional`. The instruction set defines a
contract-handling `missing` as itself a blocker-grade observation; this
audit honours that escalation.

---

## 1. Scope

### 1.1 Top-line finding (read first)

**No Kalshi contract module exists in this repository.** The repo is a
Python 3.11 prototype that consumes Pyth Hermes ticks, fits per-
commodity IV and basis surfaces, and computes per-strike survival
probabilities `P(S_T > K)` via a single GBM kernel. It produces a
*theo* and stops. Conversion of that theo into a Kalshi Yes/No quote,
order, fee estimate, position-limit check, or settlement
reconciliation does not happen anywhere in the tree.

Cartography flagged this explicitly (red flag 2,
`audit_A_cartography.md:243-245`): "No file in the repo imports,
references, or implements anything Kalshi-specific — no REST client,
no contract schema, no order submission. The whole Kalshi-facing side
of the system is absent." The README's promise of a `feeds/` directory
ingesting "Pyth, CME, options, Kalshi, macro" (red flag 1) is matched
on disk by `feeds/pyth_ws.py` alone.

### 1.2 The "Kalshi" string surface

Three live files contain the string "Kalshi" in docstrings or comments
without implementing any mechanic: `engine/event_calendar.py:4`
(describes τ as time to "the Kalshi settle"), `state/iv_surface.py:9`
(IV strip should be "the weekly expiry closest to the Kalshi settle"),
and `tests/test_end_to_end.py:69` (comment "2 hrs before Kalshi
settle"). All three describe intent only.

### 1.3 Phase B coverage check

No Phase B file owns the Kalshi contract surface.
`audit_B_engine-pricer.md`, `audit_B_engine-calendar.md`,
`audit_B_engine-scheduler.md`, `audit_B_state-market-surfaces.md`,
`audit_B_validation-sanity.md`, `audit_B_models-gbm.md`,
`audit_B_models-registry.md`, `audit_B_state-tick-store.md`, and
`audit_B_feeds-pyth.md` all confirm Pyth-side or pure-math
responsibilities. The audit's code-citation column therefore points at
either the empty target (the README's promised but absent files) or
the cartography red flag that documents the absence.

### 1.4 Claim universe

74 `contract`-tagged claim IDs are in scope: C07-01..07, 09..32, 35..38,
49..51, 53, 54, 56..59, 61, 63..67, 72..74, 77..84, 86, 102, 104..106,
108..110, 112..115; plus C09-12, C09-26, C09-27, C09-38, C09-75.

---

## 2. Audit table

Conventions: `Claim` is a one-line abstract; the authoritative wording
is the Phase C row of the same ID. `Code does` says what the code
actually implements; `absent` means no code exists for the mechanic.
`Code citation` is a path:line range or `no module` (the absence
itself is the citation, anchored by `audit_A_cartography.md:213-230`'s
exhaustive package inventory).

| C-id | Claim (one-line) | Code does | Gap | Severity | Code citation |
|---|---|---|---|---|---|
| C07-01 | Series → Event → Market → Yes/No four-level identifier hierarchy. | absent — no ticker schema or parser. | missing | blocker | no module — `audit_A_cartography.md:213-230`. |
| C07-02 | Series ticker `KXSOYBEANW`. | absent — string never appears in source. | missing | blocker | no module — confirmed by grep. |
| C07-03 | Event ticker format `{SERIES}-YYMONDD`; `KXSOYBEANW-26APR24` ⇒ Apr 24 2026. | absent — no event-ticker formatter or parser. | missing | blocker | no module. |
| C07-04 | URL slug `/markets/{series}/{slug}/{market}` (slug cosmetic). | absent — no URL builder. | missing | minor | no module. |
| C07-05 | Trailing integer `…-17` is an *ordinal bucket index*, not a strike. | absent — code's only "strike" concept is a CME-style float price. | missing | blocker | `models/base.py:33-41`; `engine/pricer.py:77-86`. |
| C07-06 | Some products use letter-prefixed strike suffixes; `KXSOYBEANW` uses integer index. | absent. | missing | nice-to-have | no module. |
| C07-07 | Bucket enumeration via `GET /events/KXSOYBEANW-26APR24` reading `floor_strike`/`cap_strike`/`strike_type`. | absent — no HTTP client to Kalshi; `httpx` declared but unused. | missing | blocker | `pyproject.toml:16`; `audit_A_cartography.md:246-249`. |
| C07-09 | Bucket table is week-stable, repositions weekly. | absent — no per-week snapshot. | missing | major | no module. |
| C07-10 | Per-contract reference price lives in Appendix A T&C. | absent — no Appendix-A loader. | missing | blocker | no module. |
| C07-11 | Appendix A names Source Agency, Underlying, Payout Criterion, Expiration Value. | absent. | missing | blocker | no module. |
| C07-12 | 40.2(a) permits non-binding clarifications to access instructions. | absent — no change-detection logic. | missing | minor | no module. |
| C07-13 | No public Appendix A indexed for `KXSOYBEANW` as of research window. | absent and unmonitored. | missing | major | no module. |
| C07-14 | Reference price almost certainly = front-month CBOT soybean daily settle. | absent — engine consumes Pyth ticks only, not CBOT settle. | missing | blocker | `feeds/pyth_ws.py:1-145`; `audit_A_cartography.md:108-112`. |
| C07-15 | Front-month for week of Apr 20–24 2026 is May 2026 (`ZSK26`). | absent — `soy` block has no `cme_symbol`/roll/month. | missing | blocker | `config/commodities.yaml:58-60`. |
| C07-16 | CBOT Rule 813 daily settle = VWAP of close window, ~1:20 p.m. CT. | absent — no settlement-time scheduler. | missing | blocker | no module. |
| C07-17 | Plausible alternatives (2:20 CT last trade, Kalshi snap, VWAP) need to live in Appendix A. | absent — no settlement-mode enum. | missing | blocker | no module. |
| C07-18 | CBOT soybean cycle Jan/Mar/May/Jul/Aug/Sep/Nov. | absent — no contract-cycle table. | missing | blocker | no module. |
| C07-19 | Soybean FND = 2 business days before first business day of delivery month. | absent — no FND logic. | missing | blocker | no module. |
| C07-20 | Apr 24 2026 < May FND (Apr 30) ⇒ May front-month and physically deliverable. | absent — no calendar that knows this. | missing | blocker | no module. |
| C07-21 | Friday-inside-roll-window behaviour depends on Appendix A roll-rule choice. | absent. | missing | blocker | no module. |
| C07-22 | Rule 7.2(b): exchange may adjust expiration date/time on data disruption. | absent — no exchange-adjustment listener. | missing | major | no module. |
| C07-23 | Rule 7.2(a): exchange may designate new Source Agency / Underlying. | absent. | missing | major | no module. |
| C07-24 | Recommendation: implement daily-settle assumption as a config parameter. | absent — no `kalshi_reference_price_mode`-style field anywhere. | missing | blocker | `config/commodities.yaml:6-85`. |
| C07-25 | Event = MECE buckets tiling the plausible settle range. | absent — engine produces probabilities at independent strikes; no MECE check. | missing | blocker | `engine/pricer.py:48`; `validation/sanity.py:38-68`. |
| C07-26 | Buckets are user-extensible; exchange adds them at discretion. | absent — no listener for new-market events. | missing | major | no module. |
| C07-27 | Standard tiling: fixed-width interior buckets (10¢/20¢/25¢) anchored on round numbers. | absent — no bucket width concept. | missing | major | no module. |
| C07-28 | Each Event has open-ended tail buckets ("below $X", "above $Y"). | absent — engine cannot represent open-ended intervals; "below $X" tail not derived anywhere. | missing | blocker | `models/gbm.py:26-42`. |
| C07-29 | Bucket grid edges fixed at listing; do not roll intraweek. | absent — no listing snapshot. | missing | major | no module. |
| C07-30 | Rule 13.1(g): specifications fixed at first day of trading except per Rules 2.8/7.2. | absent. | missing | major | no module. |
| C07-31 | Typical Event = 10–20 interior buckets + 2 tails. | absent. | missing | minor | no module. |
| C07-32 | Bucket payoff: Yes pays $1 iff `ℓ ≤ S_T < u`. | absent — no corridor digital is computed; only half-line `P(S_T > K)`. | missing | blocker | `models/gbm.py:36-41`. |
| C07-35 | Kalshi event contracts are binary (digital) options with $1 notional. | partial — math primitive present (`P(S_T > K)`), no contract wrapper. | partial | blocker | `models/gbm.py:26-42`; `models/base.py:44-52`. |
| C07-36 | Rule 6.3(a) binary payoff codification. | absent — no settlement function. | missing | blocker | no module. |
| C07-37 | Yes price ∈ $[0.01, 0.99]; $0/$1 settled-only. | wrong band — sanity clamps `[0, 1]`, not the tighter Kalshi quote band. | wrong | blocker | `validation/sanity.py:53-57`. |
| C07-38 | Yes posts $P, No posts $1 − P at entry. | absent — no order-construction code. | missing | blocker | no module. |
| C07-49 | Rule 13.1(c): minimum quote increment $0.01. | absent — no tick-size, no rounding step. | missing | blocker | `models/gbm.py:36-41`. |
| C07-50 | Rule 13.1(c) allows $0.02 override; until checked, assume $0.01. | absent. | missing | major | no module. |
| C07-51 | Quotes clamped to closed interval `[$0.01, $0.99]`. | wrong band — sanity clamps `[0, 1]`. | wrong | blocker | `validation/sanity.py:53-57`. |
| C07-53 | Rule 5.19: per-contract position limits in T&C. | absent — no position tracker. | missing | blocker | no module. |
| C07-54 | Position Limit = max-loss dollars, not contract count. | absent — no max-loss calculator. | missing | blocker | no module. |
| C07-56 | Default working assumption: $25,000 max-loss/member. | absent — no constant, no config field. | missing | blocker | no module. |
| C07-57 | Rule 5.16 Position Accountability Levels. | absent — no PAL model. | missing | major | no module. |
| C07-58 | DMM exemption from Rule 5.15 position limits. | absent — no MM-status flag. | missing | minor | no module. |
| C07-59 | DMM PAL = 10× non-MM. | absent. | missing | nice-to-have | no module. |
| C07-61 | Rule 5.15 prohibits wash and pre-arranged trades. | absent — no wash-trade detector, no STP. | missing | blocker | no module. |
| C07-63 | Rule 5.11(c)(b) $0.20 No Cancellation Range around FMV. | absent. | missing | major | no module. |
| C07-64 | Trade-cancellation review window: 15 minutes; decisions final. | absent — no review-window timer. | missing | major | no module. |
| C07-65 | Taker fee `ceil(0.07 · P(1−P) · 100) / 100`. | absent — no fee function. | missing | blocker | no module. |
| C07-66 | Maker fee = 25% of taker. | absent. | missing | blocker | no module. |
| C07-67 | Maker fees only on fill; cancels free. | absent — no order-state machine. | missing | blocker | no module. |
| C07-72 | Open: commodity-specific fee surcharge unverified. | absent — no fee-schedule loader. | missing | major | no module. |
| C07-73 | Event-specific fee surcharges on large one-offs. | absent. | missing | minor | no module. |
| C07-74 | No separate settlement fee under Rule 6.3. | absent — and moot until settlement code exists. | missing | nice-to-have | no module. |
| C07-77 | Rule 13.1(d): Market Outcomes posted by 11:59 pm ET on determination day. | absent — no outcome poller. | missing | major | no module. |
| C07-78 | Rule 7.1 Outcome Review extension: same 11:59 ET cutoff. | absent. | missing | major | no module. |
| C07-79 | Same-day commodity weeklies settle "by early evening ET". | absent — no settlement-time prior. | missing | minor | no module. |
| C07-80 | Source Agency typically underlying exchange (CME), with vendor fallback. | absent — no Source Agency abstraction. | missing | major | no module. |
| C07-81 | Friday holiday → Rule 7.2(b) rolls settlement to next trading day. | absent — calendar has no holiday set, no roll logic. | missing | blocker | `engine/event_calendar.py:30-38, 76-79`. |
| C07-82 | CBOT soybean ~7%-of-price daily limit, semi-annual reset. | absent — no limit-move guard. | missing | major | no module. |
| C07-83 | Limit-lock-day settle = limit-trip price. | absent. | missing | major | no module. |
| C07-84 | Rule 6.3(d) settlement mechanics. | absent — no DCO interaction. No DB to write to (`audit_A_cartography.md:114`). | missing | blocker | no module. |
| C07-86 | Rule 7.1 Outcome Review Committee discretion. | absent. | missing | minor | no module. |
| C07-102 | Chapter 4 MM designation. | absent. | missing | minor | no module. |
| C07-104 | KalshiEX DCM-designated Nov 4 2020. | absent — no regulatory metadata. | missing | nice-to-have | no module. |
| C07-105 | DCM subject to 17 CFR Parts 38/40; new contracts via 40.2(a). | absent. | missing | nice-to-have | no module. |
| C07-106 | 40.2(a) filing structure. | absent. | missing | nice-to-have | no module. |
| C07-108 | Commodities hub trades 24/7 including weekends (launched Apr 15 2026). | wrong — only registered calendar treats weekends as closed. | wrong | blocker | `engine/event_calendar.py:30-38, 76-79`. |
| C07-109 | No CFTC enforcement against commodities suite as of research date. | absent. | missing | nice-to-have | no module. |
| C07-110 | Klear DCO; fully cash-collateralised; no variation margin. | absent — no clearing-side abstraction. | missing | major | no module. |
| C07-112 | Open: default May-26 ZS daily settle as config param. | absent — no config knob. | missing | blocker | `config/commodities.yaml:58-60`. |
| C07-113 | Open: rulebook silent on intraweek bucket re-centering. | absent — no `market_lifecycle_v2` listener. | missing | major | no module. |
| C07-114 | Open: members may or may not earn interest on idle collateral. | absent — no treasury model. | missing | nice-to-have | no module. |
| C07-115 | Open: FCM may add pre-trade caps when routing through Robinhood Derivatives. | absent — no broker-routing layer. | missing | major | no module. |
| C09-12 | RFQ submission via `POST /communications/rfq` capped at 100 open RFQs. | absent — no RFQ submitter. | missing | major | no module. |
| C09-26 | Rulebook v1.18 Chapter 4 MM designation (reduced fees, Rule 5.19 exemption, 10× PAL). | absent. | missing | minor | no module. |
| C09-27 | Retail-to-small-prop ⇒ base taker/maker schedule. | absent — base schedule itself absent. | missing | blocker | no module. |
| C09-38 | A `KXSOYBEANW` Event opens Friday, settles the following Friday. | absent — no Friday-open/close lifecycle. | missing | blocker | no module. |
| C09-75 | Rule 5.19 limits in max-loss dollars, default $25k per member. | absent — no limit field, no enforcement. | missing | blocker | no module. |

74 claims total. Distribution: 70 `missing`, 1 `partial` (C07-35:
digital math primitive present without contract wrapper), 3 `wrong`
(C07-37 and C07-51: sanity clamps `[0, 1]` instead of Kalshi's
`[$0.01, $0.99]` quote band; C07-108: the only registered trading
calendar treats weekends as closed, which is the opposite of what the
Apr 15 2026 commodities-hub launch announces for soybeans), 0
`already-good`, 0 `divergent-intentional`. The README's promised
Kalshi surface is unbuilt rather than deliberately omitted.

---

## 3. Narrative discussion of every blocker

By Phase D's escalation rule, every contract `missing` is presumptively
a blocker. The blockers fall into eleven mechanic-families.

**Family 1 — No HTTP/WebSocket client to Kalshi (C07-07, C07-87,
C09-01..03, C09-07..14).** The repo's only network code is
`feeds/pyth_ws.py` (Pyth Hermes WS, `audit_A_cartography.md:215`). No
Kalshi REST client, no Kalshi WS client, no RSA-PSS signer, no rate-
limiter. `httpx` is declared but unused (red flag 3,
`audit_A_cartography.md:246-249`). The engine cannot reach
`GET /events/KXSOYBEANW-26APR24` (C07-07) nor subscribe to
`orderbook_delta`/`fill`/`market_lifecycle_v2` (C09-13), so every
downstream mechanic is unreachable even if implemented. This is the
foundational blocker.

**Family 2 — Reference-price observable is wrong (C07-14..17, C07-24,
C07-112).** `engine/pricer.py:59-79` reads `tick.price` from the Pyth
tick store and feeds it as `spot`. Pyth's soybean feed (which is not
even populated today — `soy` is `stub: true` in
`config/commodities.yaml:58-60`) is *not* the CBOT daily settlement
price; it diverges by basis, snapshot time, and feed methodology. The
Phase 7 §2 ¶4 recommendation (C07-24) — make the reference observable a
config parameter — is unimplemented; no `kalshi_reference_price_mode`
field exists anywhere in the YAML. A pricer that calibrates on Pyth
and settles on CBOT carries a systematic bias every Friday afternoon.

**Family 3 — No bucket/corridor representation (C07-05, C07-25,
C07-28, C07-32, C07-35, C07-39).** `models/gbm.py:26-42` computes
`P(S_T > K)` (a half-line digital). The Kalshi primitive is the
corridor digital `1{ℓ ≤ S_T < u}`. The math exists (a corridor is the
difference of two half-lines, C07-40); the data structure does not.
There is no `Event` aggregate, no `Bucket(floor, cap)` record, no
sum-to-one consistency check (C07-39 — the sanity checker at
`validation/sanity.py:59-67` enforces only monotonicity, which is
necessary but not sufficient for a MECE bucket family). C07-25's MECE
requirement cannot be expressed against a vector of independent,
unbounded strikes.

**Family 4 — Tail buckets unrepresentable (C07-28).** "Above $Y" is
coincidentally `P(S_T > Y)` from the existing kernel; "below $X"
requires `1 − Φ(d₂(X))`, which no call site derives. Tails bracket
limit-up/limit-down lock days (C07-83), so this is not an edge case.

**Family 5 — Tick-size and price-band gates wrong (C07-37, C07-49,
C07-51).** `validation/sanity.py:53-57` enforces `[0, 1]` — correct for
the survival probability `P(S_T > K)`, wrong for a Kalshi *quote*,
which lives in `[0.01, 0.99]` during trading (C07-37, C07-51). There
is no rounding-to-`$0.01`-tick step (C07-49). A deep-OTM theo of, say,
0.0023 passes sanity but would be rejected as a Yes quote. C07-51 is
recorded as `wrong` because the existing band is the wrong band for
the post-theo quote step.

**Family 6 — Order types and TIF (C07-67 plus its non-`contract`
neighbours C07-44, 45, 60).** No `Order` class, no submit method, no
TIF enum, no `post_only`/`reduce_only`/`buy_max_cost`/STP knobs.
Maker-fee accounting (C07-67) requires a cancel-vs-fill state
transition that does not exist.

**Family 7 — Fee math (C07-65, C07-66, C07-67, C09-27).** Neither the
taker fee `ceil(0.07 · P · (1 − P) · 100) / 100` nor the 25%
maker rate appears in source. No fee module, no per-trade cost
calculator. Inside-spread net edge cannot be computed; cancel-vs-fill
asymmetry (C07-67) cannot be applied.

**Family 8 — Position limits (C07-53, C07-54, C07-56, C09-75).** No
position store, no max-loss aggregator, no per-bucket exposure tracker
(C09-76), no `buy_max_cost` per-request cap (C09-77 is unreachable
because there are no requests). The $25,000 default working assumption
(C07-56) does not appear as a constant anywhere.

**Family 9 — Settlement and clearing (C07-36, C07-38, C07-84,
C07-110).** Nothing takes the Friday CBOT settle, runs it through a
bucket grid, marks each held bucket Yes/No, and reconciles against a
Klear DCO statement. Cartography records no database of any kind
(`audit_A_cartography.md:114`) — there is nowhere to write the
post-settlement state even if the function existed. C07-110's full-
cash-collateralisation premise underpins C09-54's no-colocation
argument; the audit cannot certify any of that until settlement
exists.

**Family 10 — Calendar and expiry handling (C07-22, C07-77, C07-78,
C07-81, C07-108, C09-38).** `engine/event_calendar.py:30-38` is a
hard-coded WTI windows table (Sun-18:00 → Fri-17:00 ET, weekends
closed); `__init__` registers only `wti`
(`engine/event_calendar.py:76-79`, red flag 14). C07-108 says the
commodities hub trades 24/7 including weekends — the current calendar
under-counts by exactly the weekend for any 24/7 commodity, biasing τ
low and pulling probabilities toward 0.5 (since `d₂ ∝ 1/√τ`). C07-81
has no holiday set to roll. C07-22/77/78 (exchange-initiated
adjustments, outcome-publication windows) have no representation. C09-38
(Friday-open / Friday-close one-week cadence) has no event-cycle clock.
Combined with family 2, τ is the second of the two pricing inputs that
is known to be wrong before anyone places an order.

**Family 11 — Trade cancellation, wash-trade, and STP (C07-61, C07-63,
C07-64).** No order-state machine ⇒ no $0.20 No Cancellation Range
adjudication, no 15-minute review timer, no wash-trade prevention. The
wash-trade exposure is sharper than it looks: a market-maker quoter
with Yes and No legs on adjacent buckets can mechanically self-cross
under race conditions, and STP is the mechanic that prevents it.

These eleven families cover every `blocker`-rated row in §2. No
blocker is being argued down.

---

## 4. Ambiguities

These are research-side ambiguities the Phase 7 / Phase 9 distillations
explicitly flagged. They carry forward into this audit because the code
has nothing to say about them — the code does not even host the
configuration knobs that would let an operator pin them down.

1. **Reference contract month and snap time (C07-14, C07-16, C07-17,
   C07-24, C07-112).** Phase 7 calls this "the single largest pricing
   unknown." The audit cannot resolve it; it can only note that the
   engine has no `kalshi_reference_price_mode`, `kalshi_reference_snap`,
   or equivalent configuration field.
2. **Per-contract position limit (C07-56, C09-75).** Default working
   assumption is $25,000 max-loss per member. No constant of that name
   appears in source.
3. **Live bucket grid (C07-08, C07-31, C07-111).** The exact bucket
   count and edges for `KXSOYBEANW-26APR24-17` are unknown because
   `kalshi.com` returned HTTP 429 throughout the research window. The
   engine cannot fetch them either; there is no client.
4. **Tick-size override (C07-50).** Rule 13.1(c) permits a $0.02
   override; until verified, $0.01 is assumed. Neither value is
   represented.
5. **Commodity-specific fee surcharge (C07-72).** Unverified during
   research because the canonical `kalshi-fee-schedule.pdf` returned
   429. Audit cannot speak to it; the engine has no surcharge field.
6. **Intraweek bucket re-centering trigger (C07-113).** Rulebook is
   silent; Appendix A may carry permissive language. The engine has no
   listener for `market_lifecycle_v2` so it would not learn of a
   re-centering even if one occurred.
7. **Interest on idle collateral (C07-114).** Rule 8.1 silent. No
   treasury model.
8. **FCM pre-trade caps (C07-115).** If routed through Robinhood
   Derivatives, additional caps apply. No broker-routing layer exists.
9. **Limit-day settlement-price construction (C07-83).** Phase 7 says
   "Appendix A is expected to defer to the daily settlement price as
   published by the exchange," which on a locked day equals the limit
   price. The engine has no awareness of CBOT's ~7%-of-price daily
   limit (C07-82) and would not represent the resulting point-mass at
   the limit even if it did.
10. **Roll behaviour at First Notice Day (C07-21).** Whether the
    contract follows CME's roll calendar or tracks Most-Active is
    Appendix-A-defined and unimplemented either way.

The asymmetry between the research-side ambiguities and the code-side
silence is itself the audit observation: the engine does not host a
configuration surface where these unknowns could be parameterised. Even
if Appendix A were located tomorrow, there would be no place to put
its values.

---

## 5. Open questions for maintainers

1. **Where does the Kalshi side live?** The README (`README.md:3`)
   describes a "Live Kalshi commodity theo engine" with a Kalshi-facing
   surface that is entirely absent (red flag 2). Is the Kalshi side
   intentionally deferred to a downstream service that consumes this
   repo's `TheoOutput`, or is it a missing in-repo deliverable? The
   four declared-but-unused deps (`httpx`/`structlog`/`python-dateutil`/
   `pytz`, red flag 3) suggest in-repo.
2. **Who produces `settle_ns`?** `engine/event_calendar.py:96` consumes
   it; today only tests and the benchmark harness hand-set it. Which
   component is intended to compute the Friday-settle timestamp from a
   Kalshi event ticker?
3. **Who picks the IV strip?** `state/iv_surface.py:9` says "the weekly
   expiry closest to the Kalshi settle"; the surface accepts whatever
   the caller injects. Which component does the expiry-pick (weekly
   Friday vs. SDNC vs. monthly), and where does it live?
4. **Where does the Kalshi quote-band gate live?** Should
   `validation/sanity.py` host the `[0.01, 0.99]` and tick-size gates
   (C07-37, C07-49, C07-51), or should those be a separate publish-
   layer gate so "the math is broken" stays distinguishable from "the
   venue would reject this quote"?
5. **Corridor primitive — model layer or orchestrator?** Should the
   bucket digital `P(ℓ ≤ S_T < u) = Φ(d₂(ℓ)) − Φ(d₂(u))` be computed
   in one numba kernel per Event, or composed at the pricer from two
   half-line calls? The choice affects hot-path allocation count.
6. **What flips the `stub` flag for `soy`?** `config/commodities.yaml:58-60`
   declares `soy: model: gbm, stub: true`. What set of keys (feed ID,
   tick-size, bucket grid source, fee schedule version, position-limit
   USD, reference-price mode, trading-hours session, holiday calendar)
   should the YAML carry once the stub flag is removed?
7. **Soybean trading-hours schedule — 24/7 or CBOT-aligned?** C07-108
   says the commodities hub trades 24/7; the underlying CBOT does not.
   Which schedule should `TradingCalendar.register_handler("soy", …)`
   carry?
8. **Where does the fee module live?** `engine/`, a new `kalshi/`
   package, or a future `oms/` layer?
9. **Does the unused scheduler set the event vocabulary?**
   `engine/scheduler.py` is declared but unused (red flag 5). When the
   Kalshi side is added, will `orderbook_delta`/`fill`/
   `market_lifecycle_v2` events get their own priorities alongside
   `TICK`/`IV_UPDATE`/…, or will the scheduler be replaced?
10. **Pre-ship acceptance test?** Cartography records no CI
    (`audit_A_cartography.md:186-188`). Given contract handling is
    presumptively blocker-grade, is there a planned paper-trade test
    against Kalshi demo (C09-25) with venue-rejection counts as the
    pass/fail signal?

---

## 6. Coda — what does exist

The digital-pricing primitive (`models/gbm.py:26-42`, computing
`P(S_T > K) = Φ(d₂)`) is the math core a corridor-digital Kalshi
pricer would need on the hot path; the Phase B audit
(`audit_B_models-gbm.md`) records its validation gates and BS-parity
tests. The model layer is not the blocker; the contract layer is. The
engine has built the easy half (a fast, JIT-compiled, parity-tested
digital kernel) and has not yet built the hard half (bucket geometry,
fee math, order construction, expiry calendars, settlement
reconciliation, and the API client to talk to the venue at all). The
74 contract-tagged claims yield 70 `missing`, 1 `partial`, 3 `wrong`,
and 0 `already-good`.
