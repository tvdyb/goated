# Decisions log — `goated`

Append-only record of decisions made during the project. Never
edit prior entries; if a decision is superseded, append a new
entry citing the prior one.

Entry format follows `prompts/06_DECISION_RESOLVE.md` Step 4.

---

## OD-01 — Project scope: research is the spec — RESOLVED

**Date.** 2026-04-27
**Resolver.** project lead
**Question.** Is the C02/C08/C10 corpus the spec the live code is
being built toward, or is it research input the system may decline
to implement?
**Resolution.** The research corpus IS the spec. The audit gap
register and the plan stand as written.
**Rationale.**
- Codebase explicitly aspires to "Live Kalshi commodity theo
  engine" per `README.md:3`.
- Audit was framed as plan-against-research; alternative would
  invalidate the audit, not just amend the plan.
**Affected actions.** All.
**Reconsideration trigger.** A scope-narrowing decision by a
business owner. Engineering does not unilaterally narrow scope.
**Source / authority.** Direct project-lead decision in
conversation, 2026-04-27.

---

## OD-11 — FCM vendor: Interactive Brokers — RESOLVED

**Date.** 2026-04-27
**Resolver.** project lead
**Question.** Which FCM (IB / AMP / Tradovate) for the CBOT ZS hedge
leg?
**Resolution.** Interactive Brokers, with IB Gateway running headless
plus `ib_insync` async wrapper. Standard-tier account; CME futures
permission required. Paper-trading account stood up in parallel.
**Rationale.**
- IB has broadest coverage (futures + future-options + equities + FX)
  in case the engine extends to other Kalshi `KX*` markets.
- `ib_insync` is the de-facto community standard for IB API in Python.
- Most mature API tooling among the three vendors.
**Affected actions.** ACT-20 (hedge-leg foundation).
**Reconsideration trigger.** If IB pricing or API stability becomes
problematic, revisit AMP or Tradovate. The action is parameterised
behind an FCM interface to enable the swap.
**Source / authority.** Direct project-lead decision in conversation,
2026-04-27.

---

## OD-18 — Forward-capture tiering — RESOLVED

**Date.** 2026-04-27
**Resolver.** orchestrator (proposed and accepted)
**Question.** Is anyone already running a Kalshi tape capture we can
pick up, vs. starting from scratch?
**Resolution.** Reframed into two tiers. Phase 1a: REST polling
sentinel (orderbook snapshots + trades + settled outcomes), no auth,
M0-sufficient, starts day-zero. Phase 1b: full WebSocket forward-
capture (orderbook_delta + ticker + trade + fill), required from M1
onward, lands before M0 evaluation closes.
**Rationale.**
- Kalshi REST exposes settled outcomes + trade prints + current
  orderbook snapshot; that is sufficient for the M0 backtest.
- M1 (would-quote simulation) needs historical book reconstruction
  that REST cannot provide retroactively.
- Two tiers separate "cheap, instant" capture from "needs auth and
  deeper engineering" capture.
**Affected actions.** ACT-01.
**Reconsideration trigger.** If a third-party data vendor begins
reselling Kalshi historical orderbook data, Phase 1b may become
optional. As of 2026-04-27, no such vendor exists.
**Source / authority.** Audit research and project-lead decision,
2026-04-27.

---

## OD-31 — Operating cadence: low-frequency periodic quoting — RESOLVED

**Date.** 2026-04-27
**Resolver.** project lead
**Question.** What operating cadence does the system target? HF
microsecond-budget, mid-frequency seconds-budget, or low-frequency
30s-budget?
**Resolution.** Low-frequency periodic-quoting service. 30-second
baseline reprice cadence; sub-second event reflex on USDA / weather
releases; threshold-driven hedge fire rate ~1-3/day. Provisioned for
5 trades/min peak (~100x observed actual rate of 2-3 trades/bucket/
day on `KXSOYBEANW`). Synchronous main loop; `asyncio` for I/O only.
**Rationale.**
- `KXSOYBEANW` actual trade rate is 2-3/bucket/day; HF latency
  budgets are six orders of magnitude over-provisioned.
- The Phase-02 A-S/CJ literature is wrong-objective for this rate.
- LIP scoring is snapshot-based at 1Hz; sub-second reaction is
  sufficient.
**Affected actions.** Most. Drove the F1->F2->F3 refactor.
**Reconsideration trigger.** If observed trade rate exceeds 1
trade/sec on any market we participate in (i.e., 1000x current), revisit.
**Source / authority.** Direct project-lead observation of soybean
market activity, 2026-04-27. Confirmed by Kalshi public market data.

---

## OD-32'/OD-33'/OD-34'/OD-36 — LIP-specific decisions — INVALIDATED

**Date.** 2026-04-27
**Resolver.** F4 strategic pivot
**Question.** Market-selection, target-size, distance-multiplier, and
event-window policies under the LIP framing.
**Resolution.** All four invalidated by the F4 pivot. KXSOYBEANW is
not LIP-eligible; the F4 plan targets commodity monthlies under a
spread-capture framing, not LIP pool-share.
**Rationale.** Wave 0 gate NO-GO confirmed KXSOYBEANW has no LIP
program. F4 pivots to asymmetric market-making where income is
spread capture, not pool share. LIP-specific policy decisions no
longer apply.
**Affected actions.** F3 ACT-LIP-COMPETITOR (dropped),
ACT-LIP-MULTI (dropped), ACT-LIP-RECON (dropped).
**Source / authority.** F4 strategic pivot, formalized in Phase 05.

---

## OD-06/OD-20 — CME ingest source — UPDATED

**Date.** 2026-04-27
**Resolver.** F4 plan formalization
**Question.** CME options chain ingest source: Databento or
alternative?
**Resolution.** Updated from F1/F3 assumption (Databento). F4 uses
Pyth for L1 spot (already live) + low-cost vendor or CME DataMine
for EOD options chain (NOT Databento). IB API historical options
data is the cheapest option (free with IB account per OD-11).
New decision OD-37 introduced for vendor choice.
**Rationale.** Databento is over-provisioned for F4's needs.
MBP/MBO depth reconstruction (the reason for Databento) is not
needed — F4 uses EOD chain data only. IB API is free and already
required for the hedge leg.
**Affected actions.** F4-ACT-02 (CME ingest).
**Source / authority.** F4 plan formalization, Phase 05.

---

## OD-37 — CME options chain vendor: CME Group public delayed data — RESOLVED

**Date.** 2026-04-27
**Resolver.** F4-ACT-02 implementation
**Question.** Which vendor for the ZS options chain? Options: (a) CME
DataMine (free delayed EOD, paid real-time), (b) Quandl/Nasdaq Data
Link, (c) IB API historical options data (free with account), (d) CME
Group public delayed settlement data (free, no account).
**Resolution.** CME Group public delayed settlement data via
`cmegroup.com/CmeWS/mvc/Settlements/` endpoints. JSON format, no API
key required, provides EOD settlement prices, strikes, call/put prices,
IVs, OI, and volume.
**Rationale.**
- Free and requires no API key or account setup.
- Structured JSON response (same data as the CME website settlement
  reports).
- Sufficient for F4's EOD chain data needs.
- IB API historical options (the OD-37 default from the F4 plan)
  remains available as fallback but requires IB Gateway running.
- Databento is over-provisioned (MBP/MBO not needed for EOD chain).
**Affected actions.** F4-ACT-02 (CME ingest), F4-ACT-03 (RND pipeline
consumes the chain data).
**Reconsideration trigger.** If CME public endpoint becomes unreliable,
rate-limited, or changes format in a way that breaks parsing, switch
to IB API historical options.
**Source / authority.** Implementation decision during F4-ACT-02, Phase 40.

---

(append new entries below this line)
