# Audit Phase D — Topic 7/10: Order Management & Matching Assumptions

This is the OMS slice of the Phase D synthesis. It cross-checks every Phase
C claim tagged `oms` against what the `goated` codebase actually does (and,
overwhelmingly, does not do). Read alongside `audit/audit_A_cartography.md`
and the Phase B set; the latter is empty for this topic.

---

## 1. Scope

The OMS surface in scope spans: Kalshi REST and WebSocket order-lifecycle
endpoints, the matching engine semantics they sit on top of (price-time
FIFO, "or-better" crossing, IOC/FOK/GTC, post_only / reduce_only,
self-trade prevention, RFQ legs), local mirroring of the resting book and
queue position, fill ingestion and reconciliation against `GET
/portfolio/{positions,fills,settlements}`, kill-switch primitives, rate-limit
shaping, idempotency on retried sends, and cancel/replace race handling
between the local view and the exchange. The strategy-adjacent surface —
when to widen, withdraw, or pull quotes around scheduled events, locked
limits, and overnight regimes — is included because Phase 02 and Phase 10
explicitly attach the `oms` tag to those policy claims (`audit_C_phase02_pricing_models.md:91, 92, 101`;
`audit_C_phase10_strategy_synthesis.md:85, 87, 88, 91, 92`).

`audit_A_cartography.md:213-231` enumerates the entire module inventory:
`feeds-pyth`, `state-tick-store`, `state-market-surfaces`, `state-errors`,
`models-interface`, `models-gbm`, `models-registry`, `engine-pricer`,
`engine-scheduler`, `engine-calendar`, `validation-sanity`, plus
benchmarks/tests/calibration. None of these slugs touch order lifecycle,
fills, cancel/replace, queue position, matching, or any Kalshi REST/WS
surface. Cartography Red Flag #2 (`audit_A_cartography.md:242-245`) records
this directly: "No file in the repo imports, references, or implements
anything Kalshi-specific — no REST client, no contract schema, no order
submission. The whole Kalshi-facing side of the system is absent." The
Phase B set therefore contains zero deep-dives that would normally feed
this topic; this is consistent with the prompt's expectation
("the set is expected to be empty"). The closest tangential modules —
`engine-scheduler` (a priority-queue skeleton with no producer per
`audit_A_cartography.md:254-257`), `engine-calendar` (WTI-only trading
hours per `audit_A_cartography.md:297-301`), and `validation-sanity`
(theo-side `[0,1]` clamp per `validation/sanity.py:53-57`) — are
referenced where the structural shape is at least adjacent to an OMS
claim, but they do not implement OMS behavior.

## 2. Audit Table

| C-id | Claim (one-line summary) | What the code does | Gap class | Severity | Code citation(s) | Notes |
|---|---|---|---|---|---|---|
| C07-42 | Kalshi CLOB runs price-time FIFO under Rule 5.9 (`audit_C_phase07_kalshi_contract.md:52`). | No order book model, no FIFO simulator, no Kalshi client. The only "ordering" anywhere is `asyncio.PriorityQueue` for repricing tasks. | missing | blocker | `audit_A_cartography.md:242-245`; `engine/scheduler.py:21-26` (unrelated TICK/IV/BASIS priority enum) | The matching-engine semantics the strategy depends on are entirely unmodeled. |
| C07-43 | Limit orders cross "or better" until filled or limit binds; residual rests passively (`audit_C_phase07_kalshi_contract.md:53`). | No representation of resting vs. taker fills; no residual handling. | missing | blocker | `audit_A_cartography.md:213-231` | Without this the simulator can't price expected fill given a marketable quote. |
| C07-44 | Order types: `limit`, `market`; TIFs: `fill_or_kill`, `good_till_canceled`, `immediate_or_cancel` (`audit_C_phase07_kalshi_contract.md:54`). | No `Order` dataclass, no TIF enum, no transport. | missing | blocker | `audit_A_cartography.md:242-245` | A quoter cannot encode IOC/FOK/GTC; backtest assumes nothing. |
| C07-45 | Schema also exposes `post_only`, `reduce_only`, `buy_max_cost`, `self_trade_prevention_type` (`audit_C_phase07_kalshi_contract.md:55`). | None of these flags are referenced anywhere in source. | missing | major | grep across `feeds/`, `engine/`, `state/`, `models/`, `validation/` returns no hits for `post_only|reduce_only|buy_max_cost|self_trade_prevention`. | C08-110 explicitly assumes `post_only`; absent in code. |
| C07-46 | 200,000 open-order cap per member (`audit_C_phase07_kalshi_contract.md:56`). | No tracking of open-order count anywhere; no resting book. | missing | nice-to-have | `audit_A_cartography.md:213-231` | Only matters once a quoter is wired. |
| C07-47, C07-48 | RFQ channel auto-sequences quotes; legs sit at lowest time priority at price (`audit_C_phase07_kalshi_contract.md:57-58`). | No RFQ producer or consumer; `/communications` not implemented. | missing | minor | `audit_A_cartography.md:242-245` | Optional execution channel; not on the MVS path. |
| C07-49, C07-51 | Tick is $0.01; quotes clamped to [$0.01, $0.99] (`audit_C_phase07_kalshi_contract.md:59, 61`). | `validation/sanity.py:53-57` rejects theo outputs outside `[0, 1]`; that bounds the model's *probability output*, not an outgoing quote, and admits 0.00/1.00 which the exchange disallows pre-settlement. | partial | major | `validation/sanity.py:53-57` | Gap: no quote-side rounding to 1¢ ticks, no clamp to `[0.01, 0.99]`. The sanity check is necessary upstream but not sufficient downstream. |
| C07-50 | Tick could be overridden to $0.02 for soybeans (`audit_C_phase07_kalshi_contract.md:60`). | No tick-size lookup keyed on contract; no quote rounding at all. | missing | nice-to-have | `audit_A_cartography.md:242-245` | Latent until soybean contract terms are pinned (research debated). |
| C07-52 | Min trade size = 1 contract; no exchange-wide max (`audit_C_phase07_kalshi_contract.md:62`). | No size handling. | missing | minor | `audit_A_cartography.md:213-231` | Trivial once an order builder exists. |
| C07-53, C07-54, C07-55 | Position limits per-contract, expressed as **dollars of max loss**; translate via ⌊limit/P⌋ Yes / ⌊limit/(1−P)⌋ No (`audit_C_phase07_kalshi_contract.md:63-65`). | No position store, no max-loss accounting; cannot evaluate the inequality at all. | missing | blocker | `audit_A_cartography.md:213-231` | C07-54 is load-bearing for the risk gate (C08-109, C02-82). |
| C07-56 | $25,000 max-loss working assumption for `KXSOYBEANW` (`audit_C_phase07_kalshi_contract.md:66`). | No constants of any kind for Kalshi position caps; not even a TODO marker. | missing | major | `audit_A_cartography.md:242-245` | Even the conservative default is not encoded. |
| C07-58 | DMM exempt from Rule 5.15 limits (`audit_C_phase07_kalshi_contract.md:68`). | No member/role concept. | missing | nice-to-have | `audit_A_cartography.md:213-231` | Only relevant under MM agreement. |
| C07-60 | STP modes: `taker_at_cross` and `maker` (`audit_C_phase07_kalshi_contract.md:70`). | Not encoded; no per-strategy STP policy decision. | missing | major | `audit_A_cartography.md:242-245` | A two-sided quoter without explicit STP risks wash-trade flags (C07-61). |
| C07-61 | Rule 5.15 prohibits wash and pre-arranged trades (`audit_C_phase07_kalshi_contract.md:71`). | No wash-detection guard locally. | missing | major | `audit_A_cartography.md:213-231` | Compounding gap with C07-60. |
| C07-63, C07-64 | $0.20 No Cancellation Range and 15-minute review window (`audit_C_phase07_kalshi_contract.md:73-74`). | No trade-bust handling, no review submission path. | missing | minor | `audit_A_cartography.md:242-245` | Operational; falls outside hot path but matters in incident response. |
| C07-67 | Cancels of resting orders are free of maker fees (`audit_C_phase07_kalshi_contract.md:77`). | No fee model anywhere; cancel economics not modeled. | missing | minor | `audit_A_cartography.md:213-231` | Couples to amend-vs-cancel choice (C09-21, C10-48). |
| C07-84, C07-85 | Settlement debits/credits at $1 × ITM contracts; no variation margin in life of contract (`audit_C_phase07_kalshi_contract.md:94-95`). | No portfolio accounting, no settlement crediting. | missing | major | `audit_A_cartography.md:213-231` | Required for end-of-event reconciliation (C09-79). |
| C07-92 | Trading endpoints: `POST /portfolio/orders`, `DELETE /portfolio/orders/{id}`, `GET /portfolio/orders`, `GET /portfolio/fills`, `GET /portfolio/positions` (`audit_C_phase07_kalshi_contract.md:102`). | `pyproject.toml:16` declares `httpx ≥ 0.27` but `audit_A_cartography.md:248-249` confirms `grep` for `import httpx` returns zero hits. No client, no URL, no method binding. | missing | blocker | `audit_A_cartography.md:248-249`; `pyproject.toml:16` (declared, unused) | The runtime dep is allocated but no consumer exists. |
| C07-93 | Single Kalshi WS at `wss://api.elections.kalshi.com/`, channels include `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders` (`audit_C_phase07_kalshi_contract.md:103`). | `feeds/pyth_ws.py` is the only WebSocket client and points at Hermes, not Kalshi (`config/pyth_feeds.yaml:7`). | missing | blocker | `feeds/pyth_ws.py:1-20`; `audit_A_cartography.md:104-112`; `config/pyth_feeds.yaml:7` | All real-time order/fill state requires this channel. |
| C07-95, C07-96, C07-97 | Auth = RSA-PSS-SHA256, signing message = ms-timestamp + method + path-without-query, base64 signature, three required headers (`audit_C_phase07_kalshi_contract.md:105-107`). | No signing module, no key loader, no header builder. | missing | blocker | `audit_A_cartography.md:242-245` | Without these every REST call returns 401. |
| C07-99 | Tiered leaky-bucket reads/writes per second (Basic 200/100 → Prime 4,000/4,000) (`audit_C_phase07_kalshi_contract.md:109`). | No token-bucket scheduler; `engine/scheduler.py` is a priority queue, not a rate limiter. | missing | major | `engine/scheduler.py:21-59`; `audit_A_cartography.md:254-257` | A live quoter saturates the budget per C10-33; without shaping the first 429 is unmanageable. |
| C07-100 | Default request cost 10 tokens; cancel cost 2; batches not discounted (`audit_C_phase07_kalshi_contract.md:110`). | No cost accounting in any module. | missing | major | `audit_A_cartography.md:213-231` | Tightly coupled to C07-99. |
| C07-101 | 429 carries no `Retry-After`; clients must back off locally (`audit_C_phase07_kalshi_contract.md:111`). | No retry/backoff handler; even `feeds/pyth_ws.py` (Hermes) has only the lazy `websockets` import (`feeds/pyth_ws.py:123`) and no exponential-backoff loop on the ingest path. | missing | major | `feeds/pyth_ws.py:120-145`; `audit_A_cartography.md:303-306` | Worse than absent — the only existing WS client doesn't model backoff either, so the established idiom is also missing. |
| C07-115 | FCM-routed access (Robinhood Derivatives etc.) inherits broker pre-trade-risk caps (`audit_C_phase07_kalshi_contract.md:125`). | No member/FCM model, no pre-trade-risk hook. | missing | nice-to-have | `audit_A_cartography.md:213-231` | Latent ambiguity, irrelevant absent any client. |
| C08-50 | Kalshi runs price-time FIFO with five-level depth visibility (`audit_C_phase08_synthesis_pricing.md:75`). | No book mirror, no depth concept. | missing | major | `audit_A_cartography.md:242-245` | Required for the trade-through probability of C08-52. |
| C08-52 | Trade-through probability $\mu_i/(\mu_i+\nu_i)$ from market-order vs. cancel intensity (`audit_C_phase08_synthesis_pricing.md:77`). | No intensity estimator; no historical fill/cancel store. | missing | major | `audit_A_cartography.md:213-231` | Quoting policy that isn't queue-aware overprices passive fills. |
| C08-61 | LMSR's two-sided-quote subsidy guarantee does not transfer to Kalshi (`audit_C_phase08_synthesis_pricing.md:86`). | The pricer (`engine/pricer.py:45-90`) computes a closed-form GBM theo and stops; no quoting-policy layer assumes subsidized depth. | already-good | nice-to-have | `engine/pricer.py:1-13` ("market → theo" only); `models/gbm.py` | Trivially "already-good" because nothing builds on the LMSR fallacy — the pricing layer has no downstream MM module to be misled. Evidence: cartography lists no MM/quoter module (`audit_A_cartography.md:213-231`). |
| C08-97 | Engine should keep a deterministic event calendar with $(\kappa_t^{spread}, \kappa_t^{width})$ multipliers around releases (`audit_C_phase08_synthesis_pricing.md:122`). | `engine/event_calendar.py:30-79` is only a τ calculator (WTI session-hours dict) with no κ multipliers and no per-event entries. `config/commodities.yaml` declares an `event_calendar[].{name, day_of_week, time_et, vol_adjustment}` block (`audit_A_cartography.md:147-152`) — i.e., the *config* anticipates κ — but no code reads `vol_adjustment`. | partial | major | `engine/event_calendar.py:30-79`; `audit_A_cartography.md:147-152` | Schema present, code absent. Naming collision with the in-engine "trading-hours" calendar makes the gap easy to miss. |
| C08-98 | Pull quotes 30–60 s before release, wait, refit, repost (`audit_C_phase08_synthesis_pricing.md:123`). | No quote pull, no quote post; `engine/pricer.py` only returns a theo, never a quote. | missing | major | `engine/pricer.py:45-90` | Strategy-side OMS missing. |
| C08-108 | Hedge stage I: send ZS futures and option orders to CME, reconcile each second (`audit_C_phase08_synthesis_pricing.md:133`). | No CME client; cartography confirms ("CME / options chains / Kalshi API / macro feeds — referenced in the README layout text and in research/ but not implemented anywhere", `audit_A_cartography.md:110-112`). | missing | blocker | `audit_A_cartography.md:110-112` | Hedge loop is a precondition for any commodity OMS. |
| C08-109 | Risk-gating stage J: per-bucket and aggregate-delta caps; block quotes that breach thresholds (`audit_C_phase08_synthesis_pricing.md:134`). | No risk gate. The only gate on the hot path is `validation/sanity.py:38-68`, which checks finiteness, `[0,1]`, and monotonicity of the theo — not delta caps, not bucket caps, not stress thresholds. | partial | blocker | `validation/sanity.py:38-68`; `engine/pricer.py:89` | Architectural shape is "fail closed before publishing" (good), but the published artifact is the theo, not a quote, and the gate has no inventory inputs. |
| C08-110 | Pipeline stage K: post via REST `/portfolio/orders` with `post_only`; subscribe to `orderbook_delta`, `ticker`, `trade`, `fill`; re-quote on triggers; token-bucket + 429 backoff (`audit_C_phase08_synthesis_pricing.md:135`). | None of the named REST/WS endpoints, flags, triggers, or backoff is implemented anywhere in source. | missing | blocker | `audit_A_cartography.md:104-112, 242-245`; `feeds/pyth_ws.py:120-145` | This is the canonical OMS pipeline; its complete absence dominates the rest of the table. |
| C09-06 | FIX 5.0 SP2 session for Order Entry / Drop Copy / Listener (`audit_C_phase09_kalshi_stack.md:16`). | No FIX dependency declared, no engine, no session config. | missing | nice-to-have | `pyproject.toml:9-20`; `audit_A_cartography.md:213-231` | Premier+ only; not MVP. |
| C09-09 | Order endpoints: `POST /orders`, `DELETE /orders/{id}`, `POST /orders/{id}/amend`, `POST /orders/{id}/decrease`, plus batch (`audit_C_phase09_kalshi_stack.md:19`). | None of the order-lifecycle methods are implemented; no client. | missing | blocker | `audit_A_cartography.md:242-245` | Cancel/replace race handling is moot when no client exists. |
| C09-10 | Queue-position endpoints `GET /orders/{id}/queue_position` and `/queue_positions` (`audit_C_phase09_kalshi_stack.md:20`). | No call site, no local queue-position store, no derivation from `orderbook_delta`. | missing | major | `audit_A_cartography.md:213-231` | C10-47 calls queue position "observable, action-able"; the code makes it neither. |
| C09-11 | Portfolio reconciliation via `GET /portfolio/{positions, fills, balance, settlements}` (`audit_C_phase09_kalshi_stack.md:21`). | No portfolio store, no reconciliation job. | missing | blocker | `audit_A_cartography.md:213-231` | Without this the local view never matches exchange truth (file-specific question 4). |
| C09-13 | One WebSocket multiplexes `orderbook_delta`, `ticker`, `trade`, `fill`, `user_orders`, etc. (`audit_C_phase09_kalshi_stack.md:23`). | The repo's only WS connects to Hermes (`feeds/pyth_ws.py:1-20, 130`) for `price_update` only. | missing | blocker | `feeds/pyth_ws.py:1-20`; `audit_A_cartography.md:104-112` | Different exchange, different protocol; nothing reusable. |
| C09-15, C09-16, C09-17, C09-18 | Token-bucket tier table; default 10 tokens; cancel discounted to 2; batch un-discounted; 429 with no `Retry-After` (`audit_C_phase09_kalshi_stack.md:25-28`). | No token accounting; no per-endpoint cost table. | missing | major | `engine/scheduler.py:21-59` (priority enum, not a token bucket); `audit_A_cartography.md:254-257` | Phase 09 says this is the binding constraint per C10-33; the code has none of it. |
| C09-21 | Amend resting orders for small mid-adjustments; only cancel when pulling a bucket (`audit_C_phase09_kalshi_stack.md:31`). | No amend path; no cancel path. The amend-vs-cancel decision rule is impossible to express against an empty client. | missing | major | `audit_A_cartography.md:242-245` | C10-48 explicitly cites amend over cancel/replace as the queue-priority preservation mechanism. |
| C09-58 | Tick-to-quote budget 40–60 ms inclusive of ack (`audit_C_phase09_kalshi_stack.md:68`). | The benchmark harness (`benchmarks/run.py` per `audit_A_cartography.md:226`) measures only `tick → theo`; there is no quote latency budget because there is no quote leg. | partial | major | `audit_A_cartography.md:226`; `engine/pricer.py:45-90` | Half the budget is built (compute) and asserted; the network half is unrepresented. |
| C09-71, C09-72 | Kill-switch primitives: `DELETE /orders/batch` and order-group trigger (`audit_C_phase09_kalshi_stack.md:81-82`). | No kill switch; no panic flush. | missing | blocker | `audit_A_cartography.md:213-231` | Required for any live-trading authorization. |
| C09-74 | `reduce_only` retry layer reopens quotes only after a cold-start check (`audit_C_phase09_kalshi_stack.md:84`). | No retry layer at all (covered by C07-101 gap). | missing | major | `audit_A_cartography.md:303-306` | Compounds the rate-limit gap. |
| C09-77 | `buy_max_cost` per-request dollar cap as second-layer limit (`audit_C_phase09_kalshi_stack.md:87`). | No order builder; no per-request cap. | missing | major | `audit_A_cartography.md:242-245` | Defense-in-depth absent. |
| C09-79 | Three-times-per-session reconciliation: open, intraday, EOD (`audit_C_phase09_kalshi_stack.md:89`). | No reconciler. The only periodic job hooks are the scheduler skeleton priorities `EVENT_CAL = 30, TIMER = 90` (`engine/scheduler.py:21-26`); no producer pushes a reconciliation task. | missing | blocker | `engine/scheduler.py:21-26, 36-59` | Direct answer to file-specific question 4: local view never converges to exchange truth because there is no comparator. |
| C09-81 | FIX Drop Copy is the institutional reconciliation channel (Premier+) (`audit_C_phase09_kalshi_stack.md:91`). | Not implemented; not even a stub. | missing | nice-to-have | `audit_A_cartography.md:213-231` | Premier+ tier; deferred. |
| C10-17 | Pull quotes 30–60 s before 12:00 ET print, refit, repost (`audit_C_phase10_strategy_synthesis.md:29`). | Same gap as C08-98; no quote-pull mechanism. | missing | major | `engine/pricer.py:45-90`; `audit_A_cartography.md:242-245` | |
| C10-33 | Premier-tier rate limit headroom is the binding constraint at 20-bucket sub-second cadence (`audit_C_phase10_strategy_synthesis.md:45`). | No headroom calculator; no bucket-strip representation. | missing | major | `engine/scheduler.py:21-59` | Until C07-99 is implemented this remains a research-only constraint. |
| C10-47 | Queue position is observable and action-able via the `/queue_position` endpoint (`audit_C_phase10_strategy_synthesis.md:59`). | No call to that endpoint; no local queue-position cache. | missing | major | `audit_A_cartography.md:213-231` | Direct answer to file-specific question 1: the code does not model queue position. |
| C10-48 | Latency races don't bind; queue-priority preservation via amend dominates cancel-and-replace (`audit_C_phase10_strategy_synthesis.md:60`). | Cancel/replace race is *vacuously* absent — there is nothing to race. | missing | major | `audit_A_cartography.md:242-245` | Direct answer to file-specific question 3: race handling is not implemented because the surface is unbuilt. |
| C10-73 | Pull or radically widen quotes when CBOT is closed (`audit_C_phase10_strategy_synthesis.md:85`). | `engine/event_calendar.py` carries WTI hours only (Sun 18:00 ET → Fri 17:00 ET; `engine/event_calendar.py:30-38, 76-79`); CBOT grain hours are not registered, and there is no quote-side hook that consumes "closed" status. `audit_A_cartography.md:297-301` confirms only `wti` is registered. | missing | major | `engine/event_calendar.py:30-38, 76-79`; `audit_A_cartography.md:297-301` | Even if the CBOT calendar were registered, the consumer doesn't exist. |
| C10-75, C10-76 | Basic too tight; Advanced is the realistic MVP ceiling; a 429 in a release window forces wearing adverse selection (`audit_C_phase10_strategy_synthesis.md:87-88`). | No tier configuration; no 429 handler. | missing | major | `audit_A_cartography.md:213-231` | Same as C07-99 / C07-101. |
| C10-79 | Milestone-2 sandbox: ≥4¢ each side, $500/$5,000 caps, amend-not-cancel, kill-switch (`audit_C_phase10_strategy_synthesis.md:91`). | None of the per-bucket caps, spread floor, or kill switch is encoded. | missing | blocker | `audit_A_cartography.md:213-231` | This is the explicit Milestone-2 contract; the code stops at Milestone-1 (theo). |
| C10-80 | Milestone-3 hedge loop via FCM API; 3× session reconciliation (`audit_C_phase10_strategy_synthesis.md:92`). | No FCM client. | missing | major | `audit_A_cartography.md:110-112` | Downstream of C09-79. |
| C02-65, C02-72, C02-81 | Regime overlay around scheduled events; widen/withdraw overnight; regime layer for releases and stress (`audit_C_phase02_pricing_models.md:75, 82, 91`). | No regime detector, no κ-spread / κ-width multiplier; `config/commodities.yaml` declares `event_calendar[].vol_adjustment` slots but no code reader (`audit_A_cartography.md:147-152`). | partial | major | `audit_A_cartography.md:147-152` (declared schema) | Closely linked to C08-97 partial. |
| C02-82 | Hard inventory/delta/gamma limits supersede pricing-model output and truncate the policy (`audit_C_phase02_pricing_models.md:92`). | `validation/sanity.py:38-68` rejects malformed theo but knows nothing about inventory or Greeks. | partial | blocker | `validation/sanity.py:38-68` | Architectural shape (gate before publish) is right; the gate has no inventory inputs. |
| C02-91 | Pricing models do not specify when to stop quoting under locked limits, breakers, or liquidity collapse — a meta-decision above the model (`audit_C_phase02_pricing_models.md:101`). | The pricer raises `StaleDataError` / `InsufficientPublishersError` (`engine/pricer.py:32-33, 60-69`) so it fails closed on bad inputs. There is no equivalent meta-layer for exchange-state stop conditions, but there is also no quoting layer to govern. | partial | major | `engine/pricer.py:32-33, 60-69`; `state/errors.py` | Fail-closed pattern exists upstream; never reaches the quote-pull surface. |
| C01-36 | CBOT grains use price *limits* (a lock, not a halt) — new prints cannot beyond limit (`audit_C_phase01_market_structure.md:62`). | No detection of locked-limit conditions; no behaviour switch. | missing | major | `audit_A_cartography.md:213-231` | Required for the C02-91 meta-decision. |
| C06-04 | CBOT grain matching is FIFO with implied spread pricing — outright quoter without order-ID visibility cannot reason about queue position vs. implied crush (`audit_C_phase06_data_streams.md:14`). | No CBOT order-book ingestion; only Pyth `price_update` (`feeds/pyth_ws.py:60-118`). | missing | minor | `feeds/pyth_ws.py:60-118` | Affects the futures-hedge leg, not the Kalshi leg. |

(Forty-five rows above; each has a one-line C-file reference and a code- or
cartography-anchored citation.)

## 3. Narrative — Blockers and Majors

The dominant finding is structural. Cartography Red Flag #2
(`audit_A_cartography.md:242-245`) names it directly: "the whole
Kalshi-facing side of the system is absent." Every claim in Phase C
tagged `oms` whose object is a Kalshi REST/WS endpoint, an order flag, a
matching-engine semantic, a fill, a position, a kill switch, or a rate-limit
shape resolves to `missing`. Within `missing`, the severity stratifies by
which gap blocks Milestone-2 (passive two-sided quoting, per
`audit_C_phase10_strategy_synthesis.md:91`) versus which is a Milestone-3
or institutional-tier enhancement.

**Blockers.** Eleven rows are tagged `blocker` because, individually or
as a tight cluster, they prevent submitting a single live order. The cluster
`{C07-92, C07-93, C07-95, C07-96, C07-97, C09-09, C09-13}` covers the REST
trading endpoints, the WebSocket multiplex, and the RSA-PSS signing
machinery. The runtime dependency `httpx ≥ 0.27` is declared in
`pyproject.toml:16` but `audit_A_cartography.md:248-249` confirms zero
import sites — the dependency was anticipated and then never bound.
The sibling cluster `{C07-42, C07-43, C07-44, C07-53, C07-54, C07-55}` covers
the matching-engine semantics and position-limit accounting that any
quoter-side fill simulator would need; the codebase models none of them.
`{C07-84, C07-85, C09-11, C09-79}` cover settlement crediting and
multi-cadence portfolio reconciliation — the primitives behind the
file-specific question "does the local view eventually match exchange
truth?" Without `GET /portfolio/{positions,fills,settlements}` calls
and without a comparator job, the answer is mechanically "no": there is
no local view to compare. `{C09-71, C09-72, C10-79}` cover the kill
switch — `DELETE /orders/batch`, the order-group trigger, and the
Milestone-2 stop conditions. A trading authorization that requires a
verifiable kill primitive cannot be granted against a codebase that
contains none.

**Majors.** The major rows further split into three families.

The first is *matching-engine consequence handling*: STP modes
(C07-60), wash-trade prohibition (C07-61), the `[0.01, 0.99]` price band
and 1¢ tick (C07-49 / C07-51), `post_only` and `reduce_only` (C07-45),
queue position (C09-10, C10-47), trade-through probability (C08-52),
and amend-over-cancel-and-replace (C09-21, C10-48). These are the
behaviours the strategy depends on at the *micro-structure* layer. The
codebase has `validation/sanity.py:53-57` clamping the theo to `[0,1]`,
which is genuinely adjacent to the price-band claim — a probability output
in `[0, 1]` is an upper-bound envelope on the legal Yes-side quote — but it
admits the absorbing states `0` and `1`, which the exchange refuses
pre-settlement, and it operates on the model output, not on a dispatched
quote. The classification was therefore `partial` rather than `missing`
for C07-49 / C07-51 and otherwise `missing`.

The second is *rate-limit and reliability shape*: the tier table
(C07-99 / C09-15), the per-endpoint cost table (C07-100 / C09-16, C09-17),
and the 429-without-Retry-After contract (C07-101 / C09-18 / C10-76). The
priority-queue skeleton in `engine/scheduler.py:21-59` superficially
looks like a candidate host — it has an `IntEnum` of priorities and an
`asyncio.PriorityQueue` consumer — but it is a within-process *ordering*
mechanism for repricing tasks, not a token-bucket *rate limiter*, and per
`audit_A_cartography.md:254-257` no producer submits to it. The Hermes
WebSocket client `feeds/pyth_ws.py:120-145` likewise has no
exponential-backoff loop on the ingest path; the only nod to reliability
is the lazy-import deferral at `feeds/pyth_ws.py:123`. C10-33's claim that
"rate-limit headroom rather than co-location is the binding constraint" at
Premier-tier sub-second 20-bucket cadence describes exactly the dimension
the codebase has not begun to model.

The third is *risk gating and event-window shaping*: the κ-spread /
κ-width multipliers around scheduled events (C08-97), the
pull-wait-refit-repost protocol (C08-98 / C10-17), the per-bucket and
aggregate-delta caps (C08-109), and the hard inventory/delta/gamma
limits that supersede the pricing-model output (C02-82). The
configuration file `config/commodities.yaml` already anticipates an
`event_calendar[].vol_adjustment` field per
`audit_A_cartography.md:147-152`, so the *schema* anticipates κ
multipliers — but no code reader exists. The pricer's hot path
(`engine/pricer.py:45-90`) ends at the sanity gate; the gate has no
inventory inputs and no event-state inputs. This was scored `partial`
across the relevant rows (C02-65, C02-81, C02-82, C02-91, C08-97,
C08-109): the fail-closed *pattern* is in place upstream of theo
publication, but the consumer-side pull/repost/widen surface is unbuilt.

A separate observation worth surfacing: the engine *trading-hours*
calendar (`engine/event_calendar.py:30-79`) and the strategy-level
*event* calendar (C08-97, `vol_adjustment` per event) are conceptually
distinct artifacts that have collided on the same noun in the prose. The
former is τ accounting (WTI session hours, used by `engine/pricer.py:73`);
the latter is per-release κ shaping. Phase B did not flag the collision
because there is no Phase B file for the latter — it does not yet exist
in code.

Finally, the file-specific audit questions resolve as follows from the
table.

*Queue position on Kalshi's CLOB.* Not modeled. C09-10 and C10-47 are
both `missing` / `major`. There is no local cache, no derivation from
`orderbook_delta`, no API call site.

*Self-trade prevention.* Not modeled. C07-45 (the STP enum on the order
schema) and C07-60 (the two STP modes) are both `missing` / `major`. The
adjacent wash-trade rule (C07-61) is `missing` for the same reason.

*Race-condition handling on cancel/replace.* Vacuously not handled.
C10-48 is `missing` / `major`: the strategy claim is that amend
preserves time priority and dominates cancel-and-replace, but the code
has neither cancel nor replace.

*Fill reconciliation and convergence to exchange truth.* Not possible.
C09-11, C09-79, C09-81 are all `missing`; C09-79 is a `blocker` because
it is the *comparator* job. There is no scheduler-driven reconciler and
no portfolio store to reconcile.

*Idempotency on retried sends.* Not addressed in research as a tagged
claim and not implemented in code. The closest research surface is
C07-101 / C09-18 (429 without `Retry-After`); the closest code surface
is `feeds/pyth_ws.py:120-145`, which is an ingest client with no
backoff. A request-side dedupe / client-order-ID layer is absent.

*Matching semantics vs. Kalshi's actual rules.* Across C07-42, C07-43,
C07-44, C07-49, C07-51, C08-50, and C08-61, the code makes no claim at
all about matching semantics — it simply does not represent a book.
C08-61 is the one row classified `already-good` because the LMSR-subsidy
fallacy that the research warns against is *not* embedded anywhere
downstream of the GBM pricer; there is no MM module to inherit the
fallacy.

## 4. Ambiguities

**A.** C07-50 (potential $0.02 tick override for soybeans) is itself
flagged `debated` in research (`audit_C_phase07_kalshi_contract.md:60`).
Until the soybean Appendix A is retrieved, the working assumption is
$0.01. The audit row scores this `missing` because the code carries no
tick at all; an alternative `divergent-intentional` reading (the code
declines to commit to a tick until research resolves) is not supported
because no comment, TODO, or default constant marks the deferral.

**B.** C07-56 ($25,000 max-loss default for `KXSOYBEANW`) is also
`debated` in research. The code is silent. Same reasoning as A.

**C.** C08-97 vs. `engine/event_calendar.py`. The engine module is named
"event calendar" but its responsibility is τ-years computation per
trading-hours session, not per-release κ shaping. The configuration block
`event_calendar[].{name, day_of_week, time_et, vol_adjustment}` per
`audit_A_cartography.md:147-152` is structurally compatible with C08-97
but has no consumer. Whether the intended OMS event-calendar is meant to
be a sibling module or an extension of `engine-calendar` is undetermined
from cartography alone.

**D.** C02-91 / C01-36 (locked-limit halt semantics on CBOT grains). The
code has no detector for the underlying-futures lock state. Whether this
is meant to live in the (non-existent) Kalshi OMS layer — to suspend
quoting when the underlying is locked — or in a (non-existent) CME
ingest layer is unstated. Scored `missing` / `major` rather than tagged
ambiguous because either interpretation produces the same gap.

**E.** C07-115 (FCM-routed access). Whether `goated` will route through
Robinhood Derivatives or self-clear is undetermined. Scored
`missing` / `nice-to-have` because the routing decision precedes any
client implementation.

## 5. Open Questions for Maintainers

1. **OMS module ownership.** Where will the Kalshi REST/WS client live?
   `feeds/`, alongside `pyth_ws.py`, or a new `oms/` package? The
   cartography lists `feeds-pyth` but no `feeds-kalshi` or `oms`
   (`audit_A_cartography.md:213-231`). A naming decision blocks the
   Phase B deep-dive that this Phase D row was promised.

2. **`event_calendar` semantics.** Will the per-release κ-spread / κ-width
   shaping (C08-97) extend `engine/event_calendar.py` (currently τ-only)
   or live in a new module that consumes the existing
   `event_calendar[].vol_adjustment` config block? The config schema
   anticipates the field; the τ calculator does not read it.

3. **Reconciliation cadence.** C09-79 specifies open / intraday / EOD.
   Will reconciliation be driven by `engine/scheduler.py` priorities
   (`EVENT_CAL = 30`, `TIMER = 90` per `engine/scheduler.py:21-26`), or
   by an out-of-process job? The skeleton appears compatible with the
   former but is currently unused.

4. **STP policy default.** Will the quoter post with
   `self_trade_prevention_type = taker_at_cross` or `maker` (C07-60)?
   The choice affects two-sided-quote dynamics under near-cross
   conditions and has no in-code default.

5. **Tier choice.** Which Kalshi rate-limit tier does the design assume?
   C09-20 / C10-75 argue Advanced is the MVP ceiling for a 15-bucket
   strip; the code carries no tier configuration constant.

6. **Idempotency contract.** Will retries on `POST /portfolio/orders`
   carry a client-order-ID for dedupe, or rely on the exchange-side
   submission contract? Not addressed in research and not modeled in
   code; needs a design call before any retry layer is written.

7. **Kill-switch authorization.** C09-71 / C09-72 / C10-79 require a
   kill primitive. Will it sit inside the in-process scheduler (so a
   Python-level error path can fire it) or as a separate watchdog
   process with its own credentials? Affects key-rotation policy
   referenced in `audit_C_phase09_kalshi_stack.md:106`.

8. **CBOT lock detection ownership.** C01-36 / C02-91 imply the OMS
   should pull or widen quotes when CBOT is locked-limit. Will the
   detector ingest CME L1 (which currently has no client per
   `audit_A_cartography.md:110-112`), or rely on a derived signal from
   Pyth (which already exists)?

9. **Calibration → OMS handshake.** The `calibration/` package is empty
   per `audit_A_cartography.md:122-125, 230`. Where do κ multipliers,
   trade-through intensities $\mu_i / \nu_i$ (C08-52), and queue-arrival
   models live, and how do they reach the (still-unwritten) quoter at
   runtime?

10. **FCM vs. self-clear.** C07-115 is open in research. The decision
    constrains pre-trade-risk hooks (C03-28 / C03-29) and the order-size
    cap surface; a default needs to be picked before order-builder design.

---

*End of Phase D, topic 7 of 10.*
