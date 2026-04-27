# Audit Phase D — Backtesting and Historical Data

Phase: D, topic 8 of 10. Severity scale: blocker / major / minor /
nice-to-have. Gap classes: missing / wrong / partial / already-good /
divergent-intentional.

---

## 1. Scope

This file audits the codebase against the `backtest`-tagged claims surfaced
across the Phase C distillations
(`audit/audit_C_phase01_market_structure.md` through
`audit/audit_C_phase10_strategy_synthesis.md`). The remit is the seven
file-specific questions listed in the brief: realism of CLOB fill
simulation, transaction-cost modelling, look-ahead bias, survivorship
bias, tick-level vs aggregate use, honesty about Kalshi historical-data
gaps, and capacity/market-impact treatment in performance measurement.

**Latency-harness vs. backtest disclaimer.** The repository contains a
`benchmarks/` directory (`benchmarks/harness.py`, `benchmarks/run.py`,
326 LoC per `audit/audit_A_cartography.md:226`). It is documented in its
own header (`benchmarks/run.py:1-15`) as a *latency* harness — three
scenarios: single-market theo latency, full-book repricing latency at
N=50, and tick-to-theo latency. Its synthetic context
(`benchmarks/harness.py:33-52`) wires a `Pricer` to N synthetic
commodities sharing WTI's calendar, runs the kernel many times, and
asserts p99 budgets. It is wall-clock measurement of the live hot path,
not historical replay. There is no `backtest/` package, no historical
data loader, no fill simulator, no transaction-cost engine, no walk-forward
runner, and no P&L attribution module anywhere in the source tree
(confirmed by inventory at `audit/audit_A_cartography.md:213-231` and by
`grep -rn -i backtest --include="*.py"` returning a single docstring
mention at `state/tick_store.py:10`). Per the instructions, latency
benchmarks ≠ historical backtests; nothing in `benchmarks/` is treated as
already-good for any backtest claim in this report.

**Phase B inputs.** No Phase B file is named `*backtest*`. The
deep-dives whose responsibilities tangentially touch this topic are
`audit/audit_B_state-tick-store.md` (tick history is referenced in the
docstring as backtest storage but has no reader),
`audit/audit_B_validation-sanity.md` (the README's `validation/`
description claims "Backtest, Pyth↔CME reconciliation, pre-publish
sanity checks", but only the third exists in code), and
`audit/audit_B_engine-pricer.md` / `audit_B_engine-scheduler.md` (the
hot path the latency harness measures). Cartography records the
absence of a backtest module independently
(`audit/audit_A_cartography.md:81-83`, `:236-241`). No Phase B file was
ever produced for `benchmarks/`; the brief authorises reading the
files in `benchmarks/` directly, which I have done.

**Operational stance.** Because no real backtest module exists, the
default classification is `missing`, and severities are assigned by the
operational consequence of the gap rather than by code-quality
considerations. The codebase is positioned in the cartography as a
"Live Kalshi commodity theo engine" (`audit/audit_A_cartography.md:3-4`)
and the README aspires to that role, but the Kalshi-facing surface is
absent (`audit/audit_A_cartography.md:242-245`); the backtest absence
sits inside that broader gap and is not an isolated oversight.

---

## 2. Audit table

Citations are repo-relative path:line. `cart` is shorthand for
`audit/audit_A_cartography.md`. For `missing` rows the code-side
reference is to the cartography slot or to the closest infrastructure
that would have hosted the implementation.

| C-id | Claim (1-line) | What code does | Gap class | Severity | Code citation(s) | Notes |
|---|---|---|---|---|---|---|
| C10-77 | Milestone 0: pull historical CME ZS option chains via Databento, fit SVI + Figlewski tails, score against settled Kalshi weeks. | No Databento client, no SVI fitter, no RND code, no historical pull, no settled-Kalshi compare loop. | missing | blocker | `cart:213-231` (no `data/`, `vendor/`, `backtest/`, `density/`, `kalshi/` modules) | This is the strategic gating milestone in Phase 10's plan; nothing downstream can run without it. |
| C10-82 | Milestone gating: M1 may not begin until M0 produces positive expected edge after fees on simulated mids over four consecutive settled weeks. | No notion of milestones, simulated mids, or post-fee edge anywhere in the source. | missing | blocker | `cart:81-83`, `cart:213-231` | The discipline cannot be enforced because the inputs (M0 outputs) do not exist. |
| C10-43 | Single-market trend on ZS reduces to a small mean-shift on a weekly bucket grid. | No bucket grid, no signal computation, no historical ZS series in the repo. | missing | major | `cart:213-231` (no Kalshi or trend module) | Bears on whether single-market trend is worth backtesting at all on the weekly grid; cannot be answered without one. |
| C10-51 | Per-bucket adverse-selection alpha must be calibrated live week-by-week — not backtestable without own fills. | No fill stream, no mark-out computation. | missing | major | `cart:236-241`; `validation/sanity.py` (only validation file) | The claim is itself a partial dispensation — it says backtest cannot answer this — but the code also lacks the *live* harness it points to. |
| C09-62 | [MVS] Three tapes must be stored: Kalshi `orderbook_delta`+`ticker`+`trade`+`fill`; CME ZS/ZM/ZL L1 + EOD options chain; fundamentals + weather. | None of the three tapes is captured. The only on-disk persistence is YAML config (`cart:117-125`); even `calibration/params/` is empty. | missing | blocker | `audit_B_state-tick-store.md:540-552`; `cart:60-83` | Without the three tapes there is no historical input for any backtest the project later wants to run. |
| C09-23 | No public bulk-download or FIX Drop-Copy archive of Kalshi book depth; backfill via 1-min/60-min/day candles or per-trade prints. | The codebase neither pulls Kalshi candles nor per-trade prints; there is no Kalshi REST client at all. | missing | blocker | `cart:242-245`; no client in `feeds/` (`cart:68-69`) | Independent of any future tape, the project must capture forward-going Kalshi data immediately because the backfill resolution is permanently degraded. |
| C09-25 | Kalshi demo validates signing/handshake but does not reproduce production flow; a separate paper-trading layer at the quoter level is still required. | No demo client, no paper-trading layer, no quoter wired to Kalshi. | missing | major | `cart:242-245` | Closely related to the M0 fill-simulator gap. |
| C09-64 | [MVS] DuckDB + Parquet on S3 with `httpfs` is both MVP and a serviceable recommended choice. | No DuckDB import, no Parquet read/write, no S3 SDK, no `httpfs`. `pyproject.toml:9-20` declares numpy/scipy/numba/yaml/websockets/httpx/structlog/dateutil/pytz only. | missing | major | `pyproject.toml:9-20`; `cart:114-115` | The recommended storage substrate has not been adopted. |
| C09-66 | [RECOMMENDED upgrade] ArcticDB for tick workloads where Parquet partition overhead hurts. | Not adopted. | missing | nice-to-have | `pyproject.toml:9-20` | Phase C tags this as a future upgrade, so missing is not yet a major gap. |
| C09-69 | The pandas/numpy/scipy/statsmodels + polars + DuckDB stack is adequate for Kalshi backtesting. | numpy and scipy are present (`pyproject.toml:9-20`); pandas/statsmodels/polars/DuckDB are not. There is no backtest using any of them. | partial | minor | `pyproject.toml:9-13` | The math kernel for a future backtest is partly present, the data plane is not. |
| C09-70 | The dominant research question is BL calibration quality, which is SciPy-native. | scipy is in deps (`pyproject.toml:10`) but no BL pipeline exists; only one model (`models/gbm.py:1-105`) is implemented. | missing | blocker | `models/gbm.py:1-105`; `cart:213-231` (no density module) | BL/SVI/Figlewski are nowhere in the source. |
| C08-43 | Order-arrival decay $k_i$ must be estimated empirically from Kalshi fills. | No fills are ingested or stored. | missing | major | `cart:242-245` | This claim is the empirical underpinning of any maker-side backtest. |
| C08-44 | Poisson-intensity ansatz is noisy on thin Kalshi buckets. | Not addressed: no λ-fitting code, so no opportunity to detect noise. | missing | major | `cart:213-231` | Realism caveat for any future fill simulator on Kalshi CLOB. |
| C08-60 | Kalshi outcome-price-sum-to-1 condition is often violated by 2–5¢ slack net of fees. | No grid model, no sum-to-1 reconstruction, no slack measurement. The pre-publish sanity check is per-strike monotonicity (`validation/sanity.py:43-63`) and does not cross-bucket. | missing | major | `validation/sanity.py:43-63`; `cart:81-83` | Important arbitrage-slack realism that any backtest must respect. |
| C08-89 | Required scenario tests: WASDE-day P&L on historical moves; weather-shock with Bates-SVJ; expiry-day liquidity collapse. | No scenario engine. The only "stress" is `tests/test_benchmarks.py`'s 50-market latency stress (`audit_B_engine-pricer.md`–referenced). | missing | major | `cart:166-184`; no `scenarios/` module | Sub-claim trio: WASDE day, weather shock, expiry collapse — none has a hook. |
| C08-91 | Round-trip maker-then-taker on a 50¢ bucket ≈ 0.5¢ + 2¢ = 2.5¢ ≈ 250 bps. | No fee table, no maker/taker fee accounting, no cost subtraction anywhere. | missing | blocker | `cart:213-231`; no fees in `config/commodities.yaml` (`cart:144-152`) | Without fees, every gross-edge number a future backtest produces will be misleading by ≥250 bps per round-trip on the bucket. |
| C08-111 | Pipeline stage L: weekly P&L attribution across edge / inventory / hedge / fees, fed back into $(A_i, k_i, \gamma)$. | No P&L computation, no attribution. The only weekly-cadence object in code is the trading calendar (`engine/event_calendar.py:1-110`). | missing | major | `engine/event_calendar.py:1-110`; `cart:166-184` | Core feedback loop for the maker book; cannot run without M0 → M1 outputs. |
| C08-112 | Open empirical question: bias and variance of Kalshi bucket Yes prices vs RND probabilities over first 12–24 settled weeks. | Cannot be answered without a backtest harness; none exists. | missing | major | `cart:213-231` | This is the question Milestone 0 (C10-77) is supposed to answer. |
| C08-113 | Open empirical question: fill-intensity $\lambda_i(\delta)$ on Kalshi by bucket and time-of-day. | Same as above. | missing | major | `cart:242-245` | Tied to C10-51, which dispenses backtesting in favour of live calibration. |
| C08-115 | Open empirical question: realised adverse-selection mark-out on Kalshi fills around WASDE/ESR/Crop Progress. | No mark-out code, no event windowing on fills. | missing | major | `cart:166-184` (no scenario module); `engine/event_calendar.py:30-38` (only WTI session windows) | Phase C signals this question is open *and* important; backtest infrastructure is the only way to close it. |
| C08-118 | Open empirical question: do bucket Yes prices sum to 1.00 in practice or is there persistent slack? | No grid model that could check this. | missing | minor | `validation/sanity.py:43-63` (per-strike only) | Could be added to `validation/sanity.py` once a Kalshi grid model exists. |
| C08-121 | Open empirical question: marginal value of Figlewski tail vs lognormal extrapolation, measured as P&L on end buckets. | No tail fitter, no end-bucket P&L. | missing | major | `cart:213-231` | Directly Milestone 0–dependent. |
| C07-39 | Sum of Yes bucket prices = $1 in an arbitrage-free market net of fees and rounding — baseline consistency check for any pricing engine. | The pre-publish sanity check is per-strike monotone non-increasing (`validation/sanity.py:35-67`); it does not reconstruct the full Yes vector or its sum. | missing | major | `validation/sanity.py:43-67` | Phase C explicitly tags this as the baseline pricing-engine check; the code's sanity checker is one step away in the same package but not implemented. |
| C07-91 | Historical data lives under `/historical/*` with a documented live-vs-historical boundary. | No Kalshi REST client, so `/historical/*` is not consumed. | missing | major | `cart:242-245` | The boundary is precisely the asymmetry that makes Kalshi backtests dangerous; ignoring it is worse than naively pulling. |
| C07-88 | REST sandbox/demo base URL is `https://demo-api.kalshi.co/trade-api/v2`. | No reference to demo URL in code. | missing | nice-to-have | `cart:101-115` (no Kalshi service) | A trivial config artifact, but its absence confirms the broader Kalshi gap. |
| C07-112 | Until Appendix A is located, treat the CBOT reference as a config parameter defaulted to "May 2026 ZS daily settle" and double-check via paper-trade. | `config/commodities.yaml:34-85` carries stub entries for nat_gas/wheat/coffee/nickel/lithium but no soybean entry, no `cme_reference_contract`, no settle reference. | missing | major | `config/commodities.yaml:34-85`; `audit_A_cartography.md:144-152` | This is the contract-month config the paper-trade flow is supposed to verify, and the paper-trade flow itself is the M0–M1 fill simulator. |
| C05-10 | ZS-alone TSMOM net Sharpe 0.15–0.3 after 3–5 ticks round-trip + roll slippage. | No TSMOM code, no roll model, no tick-cost subtraction. | missing | major | `cart:213-231` | Direct quantitative target a backtest would aim to reproduce. |
| C05-24 | With 40–50 years of clean CBOT data and 12 months, ~40 independent monthly observations expose seasonal mining to FDR. | No seasonal-mining code, no FDR correction, no historical CBOT dataset in repo. | missing | minor | `cart:117-125` (only on-disk data is YAML config) | Methodological warning that any future seasonal backtest must respect; latent until then. |
| C05-32 | McLean–Pontiff: cross-sectional equity-predictor alpha drops ~58% post-publication. | Not addressed. | missing | nice-to-have | `cart:213-231` | Pure literature claim; relevant only when a backtest is built and a discount factor must be chosen. |
| C05-33 | Realistic commodity-factor expectation: 30–40% below in-sample Sharpe. | Not addressed. | missing | minor | `cart:213-231` | Companion to C05-70 — the discount that should be applied to any reported in-sample Sharpe. |
| C05-60 | Point-in-time DB mandatory for any USDA-data backtest because USDA frequently revises. | No USDA ingestion, no PIT store. | missing | major | `cart:117-125` (only YAML config); `pyproject.toml:9-20` (no DB driver) | Look-ahead-bias guarantee that the project's later USDA work must respect. |
| C05-68 | Mou (2011): Goldman-roll front-running Sharpe up to 4.4. | Not addressed. | missing | nice-to-have | `cart:213-231` | Literature-only; demands no infrastructure on its own. |
| C05-70 | Multiply 2000–2015 published Sharpe ratios by 0.6–0.7 for live-money planning. | Not addressed. | missing | minor | `cart:213-231` | Discount factor for any backtest-derived Sharpe; latent until a Sharpe is produced. |
| C05-73 | Fuertes–Miffre–Rallis: ~10× annual turnover; ~0.7% annual cost drag at 0.069% round-trip; scales linearly. | No turnover counter, no cost drag in any model. | missing | major | `cart:213-231` | Capacity/cost primitive that any future signal book must implement. |
| C05-75 | Net Sharpe 0.3–0.4 realistic given gross 0.6 after costs and capacity. | Not addressed. | missing | minor | `cart:213-231` | Same family as C05-33, C05-70. |
| C04-08 | Naïve crush mean-reversion is unprofitable after 1.5¢/bu transaction costs (Rechner & Poitras 1993). | No crush spread, no mean-reversion strategy, no 1.5¢ cost knob. | missing | major | `cart:213-231` (no strategy module) | Calibration of the soybean-complex cost realism that any candidate strategy must clear. |
| C04-09 | A 3¢ entry filter on the same crush book lifts EP from −0.35¢ to +1.74¢/bu. | Not addressed. | missing | major | `cart:213-231` | Filter rule is the canonical "did your backtest model fees correctly" sanity check on the crush book. |
| C04-37 | Fades fail on genuine regime change (Sept 2025 Grain Stocks shock). | Not addressed. | missing | minor | `cart:213-231` | Methodological caveat for fade-on-event strategies; demands regime-conditional sub-sample testing. |
| C03-72 | Backtesters split into event-driven (Backtrader) and vectorized (VectorBT/Numba); a framework choice must declare which camp. | The repo has neither framework; no declaration in `pyproject.toml:9-29` or README. | missing | minor | `pyproject.toml:9-29`; `cart:114-115` | The project has not yet had to make this choice because no backtest is being built. |
| C03-67 | kdb+/q is the canonical HFT tick store. | Not adopted; tick history lives in a numpy ring (`state/tick_store.py:31-66`) with no reader. | divergent-intentional | nice-to-have | `state/tick_store.py:31-66`; `audit_B_state-tick-store.md:544-552` | The numpy ring is a deliberate prototype-stage substitute; the divergence is reasonable for the live theo path but does not constitute a backtest store. |
| C03-69 | OneTick is the second institutional tick DB. | Not adopted. | missing | nice-to-have | `pyproject.toml:9-20` | Tooling-choice claim only. |
| C03-70 | QuantHouse HOD provides 15+ years of normalised tick history. | Not adopted; no commercial vendor in the project. | missing | nice-to-have | `pyproject.toml:9-20` | Pure tooling option; nice-to-have absent any commitment. |
| C03-74 | For larger-than-memory work, polars/DuckDB/ArcticDB are the emerging trio. | None adopted. | missing | minor | `pyproject.toml:9-20` | Same family as C09-64/66. |
| C03-92 | Retail-accessible full-depth historical CBOT-grain options tapes are still thin; Databento + DataMine are partial. | No Databento or DataMine integration; no options tape consumer. | missing | major | `cart:101-115`; `cart:117-125` | Phase C names the *honest gap* in available history; the code does not address the narrowed sourcing problem at all. |
| C03-36 | Descartes Labs reports an 11-year U.S. corn yield-forecast backtest beating USDA mid-cycle estimates. | No vendor integration. | missing | nice-to-have | `cart:101-115` | Optional input; only relevant if a yield-driven signal is later coded. |
| C03-39 | Gro Intelligence aggregates 170k+ datasets; mid-2024 funding difficulties pushed many to in-house Gro-style pipelines. | No replacement pipeline. | missing | nice-to-have | `cart:101-115` | Same family as C03-36. |
| C03-48 | ERA5/ERA5-Land are the dominant input for backtested weather-yield models. | No ERA5 ingestion. | missing | nice-to-have | `cart:101-115` | Pure data-source claim. |
| C02-84 | Practitioners measure adverse selection via rolling realised spreads / mark-out at 1s, 5s, 60s. | No mark-out, no rolling-spread tracker. | missing | major | `cart:213-231` | Companion to C08-115; this is the actual measurement convention any Kalshi backtest must adopt. |
| C02-87 | Cross-asset hedge intensities are estimated empirically from trade and quote data; optimal hedge ratios rebalance more often than stochastic-control models prescribe. | No hedge-ratio estimator. The basis surface (`state/basis.py:19-48`) holds an annualised drift only. | missing | minor | `state/basis.py:19-48` | Hedge realism that a maker-book backtest must capture. |
| C01-53 | CME white paper: soybean 30-day implied volatility commonly peaks near July 4 and stays high into pod-fill. | Not addressed; the only IV object is a single ATM scalar (`state/iv_surface.py:21-48`) with no seasonal pattern. | missing | minor | `state/iv_surface.py:21-48` | Latent seasonal calibration any soy IV model would need to reproduce. |
| C01-54 | Soybean "peak July 4, bottom early October" is broken in drought (1988, 2012) and flood years. | Not addressed. | missing | nice-to-have | `cart:213-231` | Methodological carve-out; relevant only when a seasonality strategy is coded. |
| C01-74 | CME notes WASDE "reduces uncertainty in corn and soybean markets around 70% of the time." | Not addressed; no WASDE ingestion, no event-window measurement. | missing | minor | `engine/event_calendar.py:30-38` (no WASDE entry); `cart:166-184` | Event-window scaffolding does not exist for non-WTI commodities yet. |
| C06-48 | ECMWF ENS (51-member ensemble) and ERA5 reanalysis are part of ECMWF open-data. | No ECMWF integration. | missing | nice-to-have | `cart:101-115` | Pure data-source claim. |
| C06-57 | USACE NDC LPMS archive is the practitioner's window into Illinois/Mississippi River bottleneck conditions driving Gulf basis. | Not addressed. | missing | nice-to-have | `cart:101-115` | Same family. |
| C05-04 / C05-07 / C05-09 / C05-13 / C05-14 / C05-15 / C05-16 / C05-18 / C05-27 / C05-28 / C05-31 | Literature-Sharpe benchmarks for TSMOM, carry, term-structure, basis-momentum across various date ranges and universes. | Not addressed. | missing | nice-to-have | `cart:213-231` | Pure literature; relevant only as comparators when a backtest is built. Grouped here because they impose no incremental code requirement on top of "a backtest must exist." |
| C05-11 | Aspect Capital's longest underwater period was March 2016 → September 2021. | Not addressed. | missing | nice-to-have | `cart:213-231` | Drawdown-tolerance comparator; latent. |
| C05-38 | Unfiltered crush mean-reversion loses after 1.5¢/bu costs; 3¢ filter changes sign. | Same as C04-08 / C04-09 (reiterated by Rechner & Poitras). | missing | major | `cart:213-231` | Already classified above; included for completeness so the C-id is not orphaned. |
| C05-51 | Anyamba et al. (2021) NDVI-based corn/soy yield R² figures. | Not addressed; no NDVI consumer. | missing | nice-to-have | `cart:101-115` | Pure data-relationship claim. |
| C05-59 | Gradient-boosting on tabular fundamentals delivers 2–5pp R² gain on monthly price-change prediction over linear baselines. | No ML stack — `pyproject.toml:9-20` carries no scikit-learn, lightgbm, xgboost, or catboost. | missing | nice-to-have | `pyproject.toml:9-20` | Optional alpha source. |

---

## 3. Narrative discussion of blockers and majors

The core finding is that this repository does not contain a backtest of
any kind. A grep for the word `backtest` across `*.py` returns one hit,
in a docstring at `state/tick_store.py:10` that announces a "backtest
and feature-computation" use case for the 1,000,000-tick ring buffer —
yet the same module exposes no public history-reading method. The
audit at `audit/audit_B_state-tick-store.md:544-552` records this gap
and notes that all readers in the live tree call `latest()` only, which
makes the ring's history dimension dead allocation. The `validation/`
package, which the README at `README.md:44` advertises as housing
"Backtest, Pyth↔CME reconciliation, pre-publish sanity checks", in
fact contains only `validation/sanity.py` and an empty `__init__.py`
(`audit/audit_B_validation-sanity.md:473-480`,
`audit/audit_A_cartography.md:81-83`). Everything else the brief asks
about — CLOB fill realism, fees, slippage, look-ahead bias, survivorship,
Kalshi data-gap honesty, capacity/impact — sits inside that hole.

**Blockers.** Five rows are classified as blockers and they
mutually-gate subsequent work.

C10-77 (Milestone 0: offline reproduction with Databento) is the
strategic root: SVI fitting, Figlewski-tailed RND, model-bucket
probabilities, RND-vs-realized hit-rate calibration, and a measure-
overlay bias estimate all hang off it. None of these primitives exist.
The closest extant module is `models/gbm.py:1-105`, a single-name
lognormal $P(S_T > K) = \Phi(d_2)$ kernel — useful for the live theo,
silent on RND construction. `models/registry.py:32-38` (cartography red
flag #7) leaves `jump_diffusion`, `regime_switch`, `point_mass`, and
`student_t` commented out. C10-82 is dependent on C10-77: gating
discipline cannot run without M0 outputs, and there is no fees model,
no simulated mid, and nothing to compare to.

C09-62 (the three required tapes — Kalshi orderbook_delta + ticker +
trade + fill, CME L1 + EOD options chain, fundamentals + weather) is a
data-plane blocker. The only on-disk data is YAML configuration plus
an empty `calibration/params/` directory
(`audit/audit_A_cartography.md:117-125`). C09-23 compounds it: Kalshi
has no public bulk-download archive of book depth, so the only way to
get historical Kalshi depth is to record it forward in time. Every day
not captured is permanent. C09-23 is itself classified as a blocker —
independent of any backtest ambition, the project should be writing a
Kalshi tape today and is not (no Kalshi REST client anywhere —
`audit/audit_A_cartography.md:242-245`).

C08-91 (round-trip cost ≈ 250 bps on 50¢ buckets) is a blocker because
every future backtest output is meaningless without fee modelling. The
hot path at `engine/pricer.py:1-90` produces probabilities, not P&L,
and there is no slot to subtract maker/taker fees. A backtest on top
of the current state would systematically overstate edge by more than
plausible weekly-bucket alpha. C09-70 is the BL-quality blocker:
scipy is in the dep set (`pyproject.toml:10`) but no SVI, Figlewski,
or smile fitter exists, so any RND-driven backtest could not ship.

**Majors.** Four families.

*Fill-simulation realism* (C08-43, C08-44, C08-113, C10-51, C10-43).
Phase C is unusually explicit that thin Kalshi CLOB markets violate
the Avellaneda–Stoikov $\lambda(\delta) = A e^{-k\delta}$ ansatz —
Poisson intensity is noisy on Kalshi bucket volumes (C08-44) — and
C10-51 dispenses with backtesting fill intensity entirely in favour
of live calibration. The codebase satisfies neither path: no fill
simulator, no live mark-out (`audit/audit_A_cartography.md:213-231`).
This sets the lower bound on how realistic any future maker-book
backtest can be.

*Transaction costs* (C04-08, C04-09, C05-10, C05-73, C08-91, C02-84,
C02-87). Costs in this domain are not a rounding error. Rechner &
Poitras (C04-08, C05-38) show naïve crush mean-reversion changes sign
under 1.5¢/bu round-trip cost, and a 3¢ entry filter (C04-09) moves
expected per-trade profit from −0.35¢ to +1.74¢. Fuertes–Miffre–Rallis
(C05-73, ~10× annual at 0.069% = ~0.7% drag, linear scaling) implies
that ignoring turnover-induced cost drag will mis-rank strategies. The
code has no turnover counter, no fee table, no slippage knob.

*Look-ahead and survivorship* (C05-60, C05-24, C09-23). The PIT
mandate (C05-60) is the canonical USDA pitfall — monthly revisions,
annual benchmarks — and the moment a USDA feature is added, PIT
discipline is required (no consumer today,
`audit/audit_A_cartography.md:101-115`). C05-24 is the parallel
multiple-comparison-FDR warning for seasonal mining (~40 independent
monthly observations from 40 years × 12 months). C09-23 is the
survivorship analogue: forward-only capture means there is no recorded
universe of dead contracts and any reconstructed history skews toward
contracts that traded enough to leave candle prints.

*Scenario and attribution* (C08-89, C08-111, C08-112, C08-115, C08-121,
C07-39, C07-91). C08-89 names three required scenarios (WASDE-day,
weather-shock with Bates-SVJ, expiry-day collapse) — no hooks in the
source. C08-111's weekly P&L attribution loop (edge / inventory /
hedge / fees) has no home; the only weekly-cadence object is the
trading calendar (`engine/event_calendar.py:1-110`). C07-39 — sum of
Yes-bucket prices = $1 net of fees and rounding — is an *immediate*
extension to `validation/sanity.py` once a Kalshi grid model exists;
the existing per-strike monotone check
(`validation/sanity.py:43-67`) is strictly weaker than the cross-bucket
check the research demands.

**Capacity and market impact.** C05-70 (multiply 2000-2015 Sharpes by
0.6–0.7), C05-75 (gross 0.6 → net 0.3–0.4 after costs and capacity),
and C05-33 (commodity-factor 30–40% in-sample discount) are the three
quantitative discount-factor claims. The codebase has neither a Sharpe
calculation nor a reporting layer, so these discounts do not yet
attach to any number — consistent with the broader hole.

**Latency vs. backtest, restated.** Nothing in
`benchmarks/run.py:1-179` or `benchmarks/harness.py:1-326` is
classified as `already-good` for a backtest claim. The harness times
the live theo on synthetic data; it does not replay history, simulate
fills, subtract fees, measure P&L, or iterate over a strategy
parameter grid. Treating it as a backtest substrate would be a
category error. It does show the project has engineering taste for
percentile budgets and warmed-kernel measurement
(`benchmarks/run.py:51-58`, `benchmarks/harness.py:48-49`) that
should transfer — but the harness itself is not a backtest.

---

## 4. Ambiguities

1. **Tick-store history intent.** `state/tick_store.py:9-11`
   advertises ring history as backtest-and-feature-computation
   storage, yet no public read method exists.
   `audit/audit_B_state-tick-store.md:615-619` records the same
   open question. It is unclear whether a future commit will add a
   `slice(begin_ts, end_ts)` reader (in which case the 1M default
   capacity is justified) or whether the docstring is aspirational
   (in which case the capacity should drop to ~hundreds and the
   memory footprint with it). The audit treats this as `partial`
   for tick-history *capture* but `missing` for any *replay*
   surface — but the partial-versus-missing line depends on intent
   that the source does not reveal.

2. **Validation-package scope.** `README.md:44` claims
   `validation/` will host "Backtest, Pyth↔CME reconciliation,
   pre-publish sanity checks". Only the third exists
   (`audit/audit_B_validation-sanity.md:539-543`,
   `audit/audit_A_cartography.md:81-83`). It is unclear whether the
   Backtest and Reconciliation responsibilities are meant to land in
   `validation/` or whether they were re-scoped to a future
   `backtest/` and `reconciliation/` package. The README is
   evidence the project once intended the former; the current
   directory layout is consistent with either.

3. **Latency-harness reusability.** `benchmarks/harness.py:33-52`
   builds a synthetic full-book context that resembles, structurally,
   what a backtest fixture would need (registry, tick store, IV
   surface, basis, calendar, strikes). It is unclear whether that
   harness was written as a stepping-stone toward a backtest
   fixture or whether it is purely scaffold for latency tests. A
   maintainer note one way or the other would change how easily the
   gap can be filled.

4. **Calibration directory.** `calibration/params/` is empty save
   for `.gitkeep`; `.gitignore:21-22` excludes `*.json`. The
   intended consumer of nightly calibration JSON (jump MLE, HMM fit,
   IV strip per `README.md:36-48`) is not coded. Because backtest
   workflows often pull calibrations PIT, the policy of the
   to-be-built calibration store on freezing parameters at trade
   time is a meaningful design ambiguity; it cannot be resolved from
   the source.

5. **Kalshi sandbox use.** C09-25 calls out that the demo
   environment validates signing but does not reproduce production
   flow, and that a paper-trading layer is still required at the
   quoter level. Whether the intent is to build that paper layer in
   `validation/` (per the README), in a future `backtest/`, or as
   live-traffic shadow mode is not specified anywhere. Each choice
   would produce a materially different fill-simulation realism
   profile.

6. **Fee accounting locus.** Whether Phase 10's expected fee
   subtraction (C08-91, C04-08, C04-09) belongs at the model layer
   (i.e. `models/*.py` returns net theo), at the strategy layer
   (planned), or at a P&L attribution layer (C08-111) is not
   declared. The current pricer surfaces `P(S_T > K)`, not P&L; the
   architectural slot for fees has not been carved.

---

## 5. Open questions for maintainers

1. **Milestone-tracker for M0 (C10-77).** Is there an external
   tracker for the Databento → SVI → Figlewski → settled-Kalshi-week
   pipeline, or is `research/phase_10_strategy_synthesis.md` the
   only authoritative record? If a tracker exists, the C10-77 /
   C10-82 blockers may be ahead-of-schedule rather than missing.

2. **Private branches.** Cartography
   (`audit/audit_A_cartography.md:213-231`) reflects HEAD on the
   working branch only. Does a separate branch carry `backtest/`,
   a Kalshi client, or a fee model?

3. **Forward-capture status.** Has the project begun writing the
   Kalshi orderbook_delta + ticker + trade + fill tape (C09-62)
   anywhere external to the repo? C09-23 makes the cost asymmetric;
   the source contains no evidence either way.

4. **Fee table source-of-truth.** Where will the Kalshi maker/taker
   schedule live (`kalshi_fees:` block in `config/`, a future
   `kalshi/` package, or hard-coded)? C08-91 cites 0.5¢ maker /
   2¢ taker on $1 notional; `commodities.yaml` has no fee fields
   (`audit/audit_A_cartography.md:144-152`).

5. **CME options-chain vendor commitment.** C10-77 names Databento
   Standard at $199/mo; C03-92 notes only-partial coverage. Is
   Databento committed? `pyproject.toml:9-20` has no client.

6. **Survivorship strategy on Kalshi.** Forward-capture cannot
   recover pre-capture dead-contract universes. Is the plan to
   (i) accept a forward-only universe, (ii) backfill via per-trade
   prints (C09-23) and accept bias, or (iii) treat survivorship as
   out-of-scope for the first 12–24 settled weeks?

7. **Look-ahead policy on USDA features.** Will USDA features
   (C05-60) be ingested via a PIT API (archived WASDE PDFs at
   original publication time) or via the latest-revision endpoint?
   The latter is the default look-ahead trap.

8. **Scenario-test home.** C08-89's three scenarios need a home —
   `benchmarks/`, a new `scenarios/`, `validation/`, or
   integration tests under `tests/`? The choice determines whether
   the latency-budget discipline (`benchmarks/run.py:204-205`)
   carries over.

9. **P&L attribution stack.** Will C08-111's four-line attribution
   be built on pandas, polars, or DuckDB (per C09-69)? None are in
   `pyproject.toml:9-20` today.

10. **Validation surface for sum-to-1.** Should `validation/sanity.py`
    be extended to enforce C07-39 once a Kalshi grid model exists,
    or should sum-to-1 live in a separate Kalshi-specific module?
    The current per-strike monotone check
    (`validation/sanity.py:43-67`) is one logical step away.

---

*End of `audit_D_backtest.md`.*
