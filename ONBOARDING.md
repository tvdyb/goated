# Onboarding — `goated`

Welcome. This document is the orientation pack for someone walking into
this repo cold. Read it in order; budget 30–45 minutes.

---

## 1. What this project is supposed to be

The mission is to build a market-making system that quotes on Kalshi
**`KXSOYBEANW`** — Kalshi's weekly soybean price-range bucket markets —
and hedges the resulting Kalshi inventory on the CBOT ZS soybean
futures market. Each `KXSOYBEANW` Event is a set of mutually-exclusive
buckets (e.g. "ZS settles between $10.50 and $10.60") that resolve at
the end of the trading week against a CBOT-derived reference price.
Profit comes from quoting buckets at a spread around an internally-
modelled fair value, then hedging the residual delta on CBOT. The
ultimate edge is two things: extracting a more accurate risk-neutral
density (RND) from CME options than what Kalshi quotes imply, and
running a queue-aware market-making policy on top of that density.

This is a non-trivial systems build: a pricing model, a Kalshi
order-management surface, a CME hedge leg, a position store with
risk gates, a kill switch, and a backtest harness all need to exist
together for the strategy to be testable, let alone profitable.

---

## 2. What actually exists today

The repo is a **working WTI single-name GBM theo engine** of about
2,000 LoC. It ingests one Pyth Hermes feed for WTI crude, maintains
a per-commodity tick ring buffer plus a per-commodity ATM IV scalar
plus a Pyth↔CME basis drift scalar, and computes `P(S_T > K) = Φ(d₂)`
on demand under a single-name GBM with constant σ. There is a
benchmark harness, an analytical parity test against Black-Scholes,
and a sanity-check layer that raises on stale, out-of-bounds, or
non-monotone outputs.

What is **not** in the repo — despite what `README.md:3` says about a
"Live Kalshi commodity theo engine" — is anything Kalshi-facing. No
REST client, no WebSocket consumer, no signing, no contract schema, no
order builder, no bucket grid, no position store, no hedge leg, no
backtest harness. The thirteen non-WTI commodities in
`config/commodities.yaml` are all flagged `stub: true` and any of them
will raise `NotImplementedError` the moment the pricer asks for τ.

The cartography (`audit/audit_A_cartography.md`) has the file-by-file
inventory; section 9 has the module table; section 10 has the 15 red
flags. Read it once before reading anything else in `audit/`.

---

## 3. The research: ten phases, ~3,000 lines of markdown

Before the audit, the team produced ten long-form research documents in
`research/` covering every domain the system touches. They are not
imported by code; they are the spec the audit graded the code against.
In rough order:

| Phase | File | What's in it |
|---|---|---|
| 01 | `phase_01_soybean_market_structure.md` | Soybean fundamentals, USDA release calendar, CBOT contract structure, basis behaviour |
| 02 | `phase_02_market_making_pricing_models.md` | Avellaneda–Stoikov, Cartea–Jaimungal, GLFT, Glosten–Milgrom, Kyle, Heston, Bates, jump-diffusion |
| 03 | `phase_03_tooling_and_infrastructure.md` | Data vendor landscape, latency budgets, ingest patterns |
| 04 | `phase_04_discretionary_strategies.md` | Practitioner playbooks (crush spread, calendar, WASDE fade, weather entry) |
| 05 | `phase_05_systematic_strategies.md` | TSMOM, Donchian, carry, cross-sectional momentum, COT signals |
| 06 | `phase_06_data_streams.md` | Specific feeds: NWP weather, USDA REST, COT, FX, satellite, SAm fundamentals |
| 07 | `phase_07_kalshi_contract_structure.md` | Kalshi rulebook, REST/WS endpoints, RSA-PSS signing, ticker schema, fees, risk limits |
| 08 | `phase_08_synthesis_pricing.md` | Density extraction (BL, SVI, Figlewski), bucket integration, measure overlay |
| 09 | `phase_09_kalshi_stack.md` | The full Kalshi-side ops stack: WS multiplex, reconciliation, kill switch, capture, FCM |
| 10 | `phase_10_strategy_synthesis.md` | The milestone roadmap (M0–M4) and the seven `C10-KC` kill criteria |

Each phase produced a numbered claim register (e.g. C02-01, C07-39,
C10-KC-04) that the audit later cited. You don't need to read the
research cover-to-cover to be useful — most of it is reachable through
the audit, which compresses it by ~10×.

---

## 4. The audit: six phases, A → F

Every audit file lives in `audit/`. The phases were:

**Phase A — Cartography.** One file (`audit_A_cartography.md`).
Inventories every module, every file, every external dep, every red
flag. The factual baseline.

**Phase B — Per-module deep dives.** Nine files, one per non-trivial
module: `audit_B_engine-pricer.md`, `audit_B_models-gbm.md`,
`audit_B_feeds-pyth.md`, etc. Treats each module as a system unto
itself.

**Phase C — Research distillation.** Ten files (`audit_C_phase01_*.md`
through `audit_C_phase10_*.md`), one per research phase. Compresses each
phase into a tagged claim register. C-ids (`C02-44`, `C07-83`, etc.)
were assigned here and are the citation backbone for everything later.

**Phase D — Topic audits.** Ten files, one per system topic:
`pricing_model`, `density`, `data_ingest`, `contract`, `hedging`,
`inventory`, `oms`, `backtest`, `strategy`, `observability`. Each
crosses the C-id register against the codebase, tags every claim as
`already-good` / `partial` / `wrong` / `missing` / `divergent-
intentional`, and assigns severity (blocker / major / minor / nice-
to-have) and effort tier (S / M / L / XL).

**Phase E — Gap register.** One file (`audit_E_gap_register.md`).
Merges all ten Phase-D files into a deduplicated register of 185 gaps
(GAP-001 through GAP-185), with primary and detail tables, six cross-
cutting themes, and an Appendix B of "open questions for maintainers."

**Phase F — Refactor plan.** One file (`audit_F_refactor_plan.md`).
Groups the 185 gaps into 59 actions (ACT-01 through ACT-59) sequenced
into five waves with explicit dependencies, plus 16 kill criteria and
30 outstanding decisions. This is the action document.

---

## 5. What the audit found (the headlines)

Six themes from `audit_E_gap_register.md` §3 capture the shape of the
work:

**5.1 The Kalshi side is the foundational blocker.** Roughly a third
of the blocker rows trace to a single absence: there is no Kalshi
REST/WS client. No signing, no rate limiter, no ticker schema, no
bucket-grid puller, no order builder, no fill ingest. Until at least
the read side of this surface exists, every observability primitive
layered on top of it has no foothold.

**5.2 The pricing layer is built around the wrong epistemology.** The
live model emits a *theoretical* density at strikes (GBM with constant
σ); the spec calls for an *empirical* RND extracted from a CME option
surface (Breeden–Litzenberger, then SVI, then Figlewski tails, then
bucket integration). This is a kind mismatch, not a parameter mismatch.

**5.3 "Schema declared, no consumer" pattern.** The repo carries
several YAML/code declarations whose consumers were never written: the
event calendar (`config/commodities.yaml:24-28`), the calibration
package (`calibration/__init__.py` is empty; `.gitignore` reserves
`calibration/params/*.json`), the scheduler (`engine/scheduler.py:21-26`
declares priorities but no producer submits to it), the IV surface
(docstring claims additive upgrade but the public reader signature
doesn't admit a strike axis).

**5.4 Universe shape is wrong.** README and research target soybeans;
code is WTI-only with thirteen stub commodities. `engine/event_calendar.
py:30-38` registers WTI sessions only; `TickStore` keys per single
commodity; `TheoInputs.spot` is scalar. None of the strategy work
(crush, calendar, bean/corn, cross-sectional momentum) has a universe
to operate on.

**5.5 Name collisions hide gaps.** Three are significant: `state/basis.py`
is *not* the hedge-leg basis the spec names (same word, different
mechanic); `engine/event_calendar.py` is a τ-years calculator, not
the per-release κ-multiplier event calendar the spec names; `validation/
sanity.py` clamps `[0, 1]` (correct for probability, wrong for Kalshi
quote which lives in `[0.01, 0.99]`).

**5.6 Fail-safe pattern is theo-scoped, not book-scoped.** The pricer
raises rather than publishing a wrong number — the right pattern. But
the discipline is per-quote, not per-book. There is no global state, no
re-arm protocol, no kill switch. The C09-73 four-trigger kill switch
(signed-delta breach, intraweek PnL drawdown, hedge heartbeat fail,
Kalshi WS reconnect storm) needs to be layered on top.

---

## 6. The plan: 59 actions in 5 waves

`audit_F_refactor_plan.md` groups the 185 gaps into 59 actions
sequenced as follows:

| Wave | Goal | Actions | Effort |
|---|---|---|---|
| 0 | Minimum tradeable surface — sign, throttle, send, capture, cap | 13 (ACT-01–ACT-13) | ~5 ew critical path |
| 1 | Structural correctness — RND pipeline, A–S/CJ control loop, hedge leg, kill switch end-to-end, M0 backtest | 13 (ACT-14–ACT-26) | XL-dominated |
| 2 | Quoting and pricing quality — Heston/Bates SV, matrix skew, vertical-spread hedge, microstructure | 12 (ACT-27–ACT-38) | mostly parallel |
| 3 | Signals and strategy — weather, COT, soybean complex, TSMOM, event-driven | 11 (ACT-39–ACT-49) | mostly parallel |
| 4 | Hardening — observability, topology, calibration substrate, backtest realism | 10 (ACT-50–ACT-59) | leaves |

Each action cites at least one research C-id and one code location, and
tags as refactor / feature / bugfix. Section 8 of that file has the
full dependency DAG; section 9 calls out parallelisable vs serial work
per wave.

The single most important callout: **ACT-01 (forward-capture tape) has
no prerequisites and every uncaptured day is permanently lost.** Start
it on day zero, even if everything else is paused for decisions.

---

## 7. Decisions you have to make

`audit_F_refactor_plan.md` §11 lists 30 outstanding decisions
(`OD-01`–`OD-30`). They split into three groups:

**Governance / scope (OD-01, OD-02, OD-08, OD-23).** Is the C02/C08/C10
research corpus the spec the system is being built toward, or is it
optional input? Is the WTI-only shape an early-deliverable scoping
that flips, or an unacknowledged divergence? Are weather and logistics
in the MVS or deferred? Until OD-01 is answered, the entire 59-action
plan is a hypothesis.

**Vendor / integration (OD-06, OD-11, OD-12, OD-15, OD-19, OD-20).**
Soybean ingest via Pyth or Databento? FCM vendor — IB, AMP, or
Tradovate? FCM vs self-clear? Kalshi rate-limit tier — Standard,
Premier, or Premier+? CME options chain vendor — Databento or
alternative? Where does the fee table live? These gate the effort
estimates on the relevant actions.

**Parameter / policy (OD-04, OD-05, OD-13, OD-14, OD-16, OD-17,
OD-21, OD-22, OD-24, OD-25, OD-26, OD-27, OD-28, OD-29, OD-30).**
Density refresh sync or async? Sum-to-1 assertion hard or soft?
Reconciliation cadence — scheduler or out-of-process? STP default —
`taker_at_cross` or `maker`? Kill switch in-process or separate
watchdog? CBOT lock detection from CME L1 or Pyth? Survivorship
strategy on Kalshi? USDA look-ahead policy? Measure-overlay form?
Kill-switch N (hedge-heartbeat seconds) and K (Kalshi WS
reconnects/min) thresholds? `vol_adjustment` semantics? `SanityError`
fan-out? `buy_max_cost` enforcement layer? Σᵢⱼ estimator?
Practitioner corpus selection? The plan ships working assumptions for
every one of these so engineering can proceed; treat them as
defaults to revisit, not commitments.

The triage advice from the previous response stands: **OD-01, OD-11,
OD-18 (forward-capture status today) are the three that gate
day-zero work.** Everything else can be answered in parallel with
ACT-01 starting.

---

## 8. How to read the audit files

If you have one hour, read in this order:

1. `audit_A_cartography.md` §9 (module inventory) and §10 (red flags)
   — 10 minutes.
2. `audit_E_gap_register.md` §3 (cross-cutting themes) — 10 minutes.
3. `audit_F_refactor_plan.md` §1, §3, §8 (executive summary, Wave 0
   table, dependency graph) — 15 minutes.
4. `audit_F_refactor_plan.md` §11 (outstanding decisions) — 10 minutes.
5. `audit_F_refactor_plan.md` §12 (kill criteria) — 5 minutes.

If you have a day, also read:

6. The research phase that matches your working area (e.g. Phase 7 if
   you're building the Kalshi client; Phase 8 if you're building the
   density pipeline; Phase 2 if you're building the pricer).
7. The matching `audit_C_phaseNN_*.md` (claim register) and
   `audit_D_<topic>.md` (topic audit).
8. The two or three Phase-B per-module audits for the modules you'll
   touch.

The Phase-D files are the most directly actionable — they tell you
which C-ids hit which file:line ranges and how each one was scored.

---

## 9. Where to start

Concretely, in your first week:

1. **Read this doc and the five files in §8.1 above.** Don't try to
   read every Phase D — read the one that matches the wave/action
   you'll work on.
2. **Push for resolution on OD-01, OD-11, OD-18.** Even informal
   resolution unblocks half the plan. OD-18 in particular: if anyone
   on the team has already started writing a Kalshi tape externally,
   ACT-01 can be downgraded to a pickup, and that frees an engineer.
3. **Stand up the kill-criteria checks as scripts.** Several
   `KC-AUD-NN` items in `audit_F_refactor_plan.md` §12 are one-shot
   measurements. `KC-AUD-02` is literally `grep -rn "import httpx"
   --include="*.py"`. Wire them into a `kill_criteria/` directory so
   they become buttons, not arguments.
4. **Pick a Wave-0 action whose dependencies are clear** (ACT-02,
   ACT-07, or ACT-01 if OD-18 says "no, nobody is capturing yet")
   and ship it.
5. **Convert the 59 actions into your tracker of choice.** GitHub
   Projects / Linear / Jira — whatever the team uses. The DAG in §8
   is your column structure; the per-action prose is the issue body.

Two things to internalise as you start writing code:

- **The non-negotiables in `README.md:59-66` are real.** No pandas in
  the hot path. No silent failures. `numba.njit` on hot-path math.
  `scipy.special.ndtr` over `scipy.stats.norm.cdf`. The fail-safe
  pattern at `engine/pricer.py:62-75` and `validation/sanity.py:38-68`
  is the template every new module should follow.
- **The pricing model and the Kalshi client are independent
  workstreams once Wave 0 ACT-02/ACT-03 are done.** They re-converge
  at ACT-13 (corridor adapter) and ACT-17 (proper RND pipeline). Two
  engineers can work in parallel without much coordination friction
  for most of Wave 1.

Welcome aboard. The audit is dense; the plan is concrete; the failure
modes are named in advance. Most of the real questions left are
governance and vendor decisions, not engineering ones.
