# Phase 07 — Kalshi Weekly Soybean Price-Range Contract: Structural Dissection

## Abstract

KalshiEX LLC, a CFTC-designated contract market, lists a series of weekly event contracts on CBOT soybean settlement prices under the ticker stem `KXSOYBEANW`. Each weekly expiry fans out into a grid of binary price-range ("bucket") markets; buying a single bucket pays $1 if the Friday reference price lands inside the bucket's strike range and $0 otherwise, making the product a portfolio of digital options on the underlying. This phase takes the sample contract `kxsoybeanw-26apr2417` as an anchor and dissects the legal, mechanical, and technological layers the exchange exposes: the Rule 40.2(a) self-certification template, the Rulebook chapters that govern priority and settlement, the cent-granular tick and $0.01–$0.99 price bands, the published taker fee formula, the RSA-PSS authenticated REST/WebSocket API, and the outstanding ambiguities — chiefly the exact CBOT reference month and settlement snapshot time — that must be resolved from the live product page or the per-contract Terms and Conditions before a pricing engine can be wired up.

---

## 1. Contract identification

Kalshi organizes its contracts in a four-level hierarchy — Series → Event → Market → (Contract side, Yes/No) — and all identifiers flow from a common Series ticker via hyphenation. The Series ticker for the weekly soybean product is `KXSOYBEANW`, which parses as `KX` (the branded commodity-series prefix introduced during the 2024 product reorganization) + `SOYBEAN` (underlying stem) + `W` (weekly cadence). The Series is permanent; Events spawn from it on a weekly cycle, and each Event spawns a cluster of Markets, one per price bucket. Ticker conventions are documented on Kalshi's developer site ([Kalshi Docs — Market Ticker](https://docs.kalshi.com/websockets/market-ticker); [Kalshi API Reference](https://docs.kalshi.com/api-reference)).

The sample contract `kxsoybeanw-26apr2417` decomposes as follows:

- **Series ticker:** `KXSOYBEANW`.
- **Event ticker:** `KXSOYBEANW-26APR24` — year (`26` = 2026), month (`APR`), day-of-month (`24`). April 24, 2026 is a Friday; that is the Expiration Date. Kalshi's event-level ticker uses the YY-MON-DD composition; the URL surface lowercases it and concatenates.
- **Market ticker (bucket):** `KXSOYBEANW-26APR24-17` — the trailing `17` is an ordinal bucket index within the Event, not a dollar threshold. Kalshi does use human-readable strike suffixes in some products (the exchange's public examples include `HIGHNY-22DEC23-B53.5` for a weather bucket centered at 53.5°F, and `FED-23DEC-T3.00` for a rate-threshold market). For `KXSOYBEANW` the visible convention is the integer-index form. The canonical way to enumerate bucket edges programmatically is to issue `GET /trade-api/v2/events/KXSOYBEANW-26APR24` and read the `floor_strike`, `cap_strike`, and `strike_type` fields on each child market ([Kalshi API — Markets and Events endpoints](https://docs.kalshi.com/api-reference)).

The URL slug structure is `/markets/{series_ticker}/{series_human_slug}/{market_ticker}`; it encodes only the market ticker, not a dollar strike. Series and Event tickers are the keys that anchor the REST and WebSocket calls; the slug is cosmetic.

Live page contents (order book depth, Yes/No quotes, timestamp-stamped bucket table) could not be retrieved during the research window — `kalshi.com` consistently returned HTTP 429 to every WebFetch attempt. Flagged as an ambiguity in §10; the bucket table is stable across a trading week but changes week-over-week as the exchange repositions strikes around the prevailing front-month futures price.

## 2. Underlying reference

Kalshi's rulebook does not embed per-contract reference-price specifications — those live in the Appendix A "Terms and Conditions" attached to each CFTC self-certification filing ([KalshiEX Rulebook v1.18, Chapter 13](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf); Rule 13.1 specifies only cross-contract uniform terms). The Appendix A structure, verified against the September 24, 2025 `COMPETITIONREALITYELIM` filing and re-used across Kalshi products, names a hierarchy of **Source Agencies**, an **Underlying** definition, a **Payout Criterion**, and an **Expiration Value** ([KalshiEX 40.2(a) filing, Sep 24, 2025](https://www.cftc.gov/sites/default/files/filings/ptc/25/09/ptc09242531143.pdf)). The filing template explicitly states: "A new Source Agency can be added via a Part 40 amendment" and "All instructions on how to access the Underlying are non-binding and are provided for convenience only and are not part of the binding Terms and Conditions of the Contract. They may be clarified at any time."

For `KXSOYBEANW` the load-bearing question is *which* settlement price on *which* CBOT soybean futures contract is read on the Friday expiry. Kalshi has not yet indexed a public Appendix A for `KXSOYBEANW` in the CFTC SIRT portal ([CFTC SIRT — rules & product filings search](https://sirt.cftc.gov/sirt/sirt.aspx); [CFTC DCM oversight page](https://www.cftc.gov/IndustryOversight/DCM/index.htm)), and the live product page was unavailable. Based on the analogous weekly WTI product (`KXWTIW`) and the CME roll calendar, the reference is almost certainly the **front-month CBOT soybean futures daily settlement price**, which during the week of April 20–24, 2026 is the May 2026 contract (`ZSK26`). CBOT Rule 813 defines daily settlements as a VWAP of trades in a fixed settlement window, and the exchange publishes them in the Daily Bulletin shortly after the 1:20 p.m. CT close ([CME Group — Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html); cross-referenced to the soybean contract specs at [CME Soybean Contract Specs](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.contractSpecs.html)). That settlement is the natural, unambiguous, exchange-published number for a DCM to cite; Kalshi's alternate options would be the 2:20 p.m. CT last trade, a Kalshi-chosen snap, or a VWAP window — any of these would need to appear in the Terms and Conditions to be binding.

Whichever reference is chosen, two roll-and-holiday edge cases matter for a pricing engine:

- **Front-month roll.** The CBOT soybean contract cycle is January, March, May, July, August, September, November. The "front month" ambiguates in the week before First Notice Day (two business days prior to the first business day of the delivery month). April 24, 2026 is comfortably before May First Notice Day (April 30), so May remains unambiguously front-month and physically deliverable that Friday. But on a Friday falling inside a rolling window, Kalshi must specify whether it follows the CME roll calendar (moves to the next month after First Notice) or tracks the Most-Active contract. Appendix A would pin this down.
- **CBOT holiday or early-close.** Rule 7.2(b) of the Kalshi rulebook grants the exchange power to "adjust the Expiration Date and the timing of Expiration of the Contract" if the Expiration Value "cannot be determined accurately at Expiration, including but not limited to the rescheduling or cancellation of an event whose outcome governs a Contract's Underlying, or delayed data from a source" ([KalshiEX Rulebook v1.18, Rule 7.2](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)). Rule 7.2(a) additionally permits Kalshi to "designate a new Source Agency and Underlying for that Contract." In practice this would cover a CBOT market disruption; the exchange's Notices section is the publication channel.

Pending inspection of the `KXSOYBEANW` Appendix A, the right pricing-engine approach is to implement the daily-settle assumption and treat it as a configuration parameter. The resolution-time ambiguity is the single largest pricing unknown in this product.

## 3. Bucket structure

A `KXSOYBEANW` Event comprises a set of mutually exclusive, collectively exhaustive **buckets** — each a Kalshi Market with its own ticker, order book, and Yes/No quote — that together tile the plausible range of the Friday settle. Kalshi's help center describes the buckets as user-extensible: traders can "request additional strikes" and the exchange adds them at its discretion ([Kalshi Help — Request Additional Strikes](https://help.kalshi.com/en/articles/13823834-request-additional-strikes)). The standard tiling pattern observed across analogous Kalshi commodity weeklies (`KXWTIW`, `KXGOLD`, `KXBTC`) is:

- Fixed-width interior buckets. For soybeans the natural unit is cents per bushel; likely candidates are 10¢, 20¢, or 25¢-wide buckets depending on the week's expected range. The exchange anchors the grid on round numbers ($10.00, $10.25, $10.50, …) rather than on the spot-minus-offset value at listing.
- Open-ended **tail** buckets at both ends — a "below $X.XX" bucket and an "above $Y.YY" bucket — so that any realized settle, no matter how extreme, sits inside exactly one bucket.
- **Edges fixed at listing.** The bucket grid is posted when the Event opens (typically the preceding Friday afternoon, as the previous week's Event settles) and does not roll with the underlying during the life of the Event. Rule 13.1(g) confirms this: "Specifications shall be fixed as of the first day of trading of a Contract, except as provided in Rule 2.8 and Rule 7.2 of these Rules or as set forth in Rules specific to a Contract."
- A typical weekly commodity Event lists 10–20 interior buckets plus two tails; the 17 in the sample ticker is consistent with that ordinal range, though the exact count for this Event could not be pulled live.

The semantic structure of each bucket is straightforward: bucket *i* with edges $[\ell_i, u_i)$ pays **Yes = $1** if the Expiration Value $S_T$ satisfies $\ell_i \le S_T < u_i$, and **No = $1** otherwise. The Yes side's price is the market-implied probability of the bucket being hit; the No side's price is one minus that, modulo fees and market impact. Because buckets are disjoint and exhaustive, the *vector* of Yes prices across buckets for a single Event forms a discrete probability distribution (ignoring the spread and the $0.01 minimum increment).

Pending the live page, I cannot record bucket-specific edges or prices. A timestamped snapshot should be taken from the `/events/KXSOYBEANW-26APR24` API response on first run of the pricing engine; the snapshot will change week over week as the exchange repositions the grid and will tick intraweek as traders quote against it.

## 4. Payoff mapping

Kalshi event contracts are binary (digital) options with a one-dollar notional. The September 24, 2025 self-certification template states the payoff in plain English: "the Contract's payout structure is characterized by the payment of an absolute amount to the holder of one side of the option and no payment to the counterparty. … If the Market Outcome is 'Yes,' meaning that an event occurs that is encompassed within the Payout Criterion, then the long position holders are paid an absolute amount proportional to the size of their position and the short position holders receive no payment" ([KalshiEX 40.2(a) filing template](https://www.cftc.gov/sites/default/files/filings/ptc/25/09/ptc09242531143.pdf)). The rulebook codifies the same mechanic in Rule 6.3(a): "When a Contract expires and has a Payout Criterion that encompasses the Expiration Value of the Underlying, such Contract will pay the Settlement Value for such Contracts (e.g. $1.00) to the holders of long positions in such Contracts. Conversely, when a Contract expires and has a Payout Criterion that does NOT encompass the Expiration Value of the Underlying, such Contract will pay the Settlement Value for such Contracts (e.g. $1.00) to the holders of short positions in such Contracts."

Formally, for a bucket *i* with edges $[\ell_i, u_i)$, the Yes-side payoff at expiry $T$ given reference price $S_T$ is

$$
\text{payoff}^{\text{Yes}}_i(S_T) = \mathbf{1}\{\ell_i \le S_T < u_i\},
$$

and the No side pays $1 - \text{payoff}^{\text{Yes}}_i(S_T)$. Per the Appendix A template, positions carry a "one-dollar notional value" and are priced between $0.01 and $0.99 inclusive — the $0.00 and $1.00 absorbing states exist only after settlement. Both sides of the trade are fully collateralized at entry: the Yes buyer posts $P$ per contract (where $P$ is the Yes price in dollars) and the No buyer posts $1 - P$ per contract, matching their maximum loss.

A holding of the full vector of buckets for one Event — one contract Yes on every bucket, bought at prices $P_1, \ldots, P_n$ — replicates a risk-free $1 with total cost $\sum_i P_i$. Because buckets are disjoint and exhaustive, $\sum_i P_i^{\text{Yes}} = 1$ in an arbitrage-free market, net of fees and minimum-increment rounding. This is the baseline consistency check for any pricing engine.

The portfolio-equivalence to a strip of digital options on a CBOT soybean futures settlement is exact. A single bucket is equivalent to a **digital-corridor option** that pays $1 if $S_T \in [\ell_i, u_i)$, which in turn decomposes into the difference of two cash-or-nothing digital calls: $\mathbf{1}\{S_T \ge \ell_i\} - \mathbf{1}\{S_T \ge u_i\}$. Given a smooth risk-neutral density on the settle, the Breeden-Litzenberger identity says the Yes prices pin down the density at bucket-scale resolution. Operationally, the KXSOYBEANW strip is a tradable discretization of the Friday-settle risk-neutral distribution, to which CBOT's far richer ZS options surface is the continuous counterpart.

## 5. Order book, order types, and matching

All Kalshi trading runs on a **central limit order book** with price-time (FIFO) priority. Rulebook v1.18 Rule 5.9 states: "Kalshi's central limit order book matches Orders in an open and competitive manner. … Kalshi's trading algorithms execute all trades by matching orders according first by price and then time priority. This means that Orders and quotes entered at different prices will be executed in order of price, from best to worst, regardless of what time they were placed on the Platform, and Orders and quotes placed on the Platform at the same price will be executed in order of time, from oldest to most recent" ([KalshiEX Rulebook v1.18](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)). Filling is "or better": a limit order crosses through the book until filled or until the limit binds, and residual quantity rests as a passive order (Rule 5.10 in v1.18).

**Order types and time-in-force.** The REST create-order endpoint accepts `limit` and `market` order `types`. Time-in-force values are `fill_or_kill` (FOK), `good_till_canceled` (GTC), and `immediate_or_cancel` (IOC). The schema additionally exposes `post_only` and `reduce_only` flags, a `buy_max_cost` dollar cap (which imposes implicit FOK behavior), and a `self_trade_prevention_type` enum with values `taker_at_cross` and `maker` ([Kalshi API — Orders endpoint](https://docs.kalshi.com/api-reference)). Members are capped at 200,000 open orders at once.

**Pre-execution communications / RFQ.** Rule 5.3(b) (v1.15) exposes a formal RFQ channel: a Requester posts a two-sided Request for Quote with a quantity; Quoters reply with two-sided Quotes; upon acceptance and a 15-second confirmation timer, Kalshi auto-sequences the two orders into the book, with the RFQ legs placed at the lowest time priority of any resting order at that price. Any price improvement available in the resting book is consumed first ([KalshiEX Rulebook v1.15, Rule 5.3](https://cdn.robinhood.com/assets/robinhood/legal/KalshiEX_LLC_Rulebook.pdf)).

**Tick size.** Rule 13.1(c): "The minimum quote increment for each Contract is $0.01 per Contract unless otherwise specified in a Contract's terms and conditions." The minimum fluctuation is one cent; both the Yes and No sides quote on the same grid. Price bands clamp quotes to the closed interval [$0.01, $0.99], per every Appendix A template in the CFTC filings.

**Order size and position limits.** The minimum unit of trading is one contract (Rule 13.1(a)); there is no exchange-wide maximum order quantity. Position limits are imposed per-contract under Rule 5.19 (v1.18, Rule 5.17 in v1.15): "Kalshi may impose Position Limits on all Contracts, which will be specified in each contract's Terms and Conditions." The rulebook defines a Position Limit as "the maximum loss that can be incurred as a result of a position in a Contract" — that is, Kalshi expresses limits in *dollars of max loss* rather than contract count, which on a Yes-priced-$0.30 bucket translates to ⌊limit/0.30⌋ contracts on the Yes side or ⌊limit/0.70⌋ on the No side. The exact per-contract limit for `KXSOYBEANW` was not retrievable; prior Kalshi commodity products have used a $25,000 max-loss framework, which would be the default assumption until Appendix A is inspected. Position Accountability Levels under Rule 5.16 add a second, softer layer: crossing the Accountability Level triggers a reporting obligation and a potential liquidation direction from Compliance without automatic violation. Designated Market Makers under Chapter 4 are exempt from Rule 5.15 position limits on contracts covered by their Market Maker agreement and operate at Accountability Levels "10 times the Position Accountability Levels for non-Market Makers" (Rule 4.5).

**Self-trade prevention.** The `self_trade_prevention_type` enum on create-order offers two modes: `taker_at_cross` (the incoming aggressor is reduced or canceled at the cross, preserving any same-member maker side) and `maker` (the resting maker leg is canceled, letting the taker execute against other participants). Rule 5.15 independently prohibits wash trades and pre-arranged trades.

**Book depth visibility.** Rule 5.13 guarantees that members can see "the current best bid and offer on the Platform, the open interest, the trade volume, as well as the depth of the order book up to the fifth level of prices" — five levels each side.

**Trade cancellation / No Cancellation Range.** Rule 5.11(c)(b) establishes a $0.20 No Cancellation Range around Kalshi's calculated fair market value at the time of the questioned trade. Trades inside the range stand; trades outside may, but need not, be canceled or adjusted at Kalshi's discretion. Review requests must be filed within 15 minutes of execution and decisions are "final and not subject to appeal."

## 6. Fees

Kalshi's canonical fee schedule lives at `https://kalshi.com/docs/kalshi-fee-schedule.pdf`, which I could not fetch during the research window. The help center summarizes the structure at a high level — "Kalshi charges a transaction fee on the expected earnings on the contract" and "some markets have fees that are different from those of other markets" for event-specific surcharges ([Kalshi Help — Fees](https://help.kalshi.com/en/articles/13823805-fees)) — and defers to the PDF for the formula. The formula as reported consistently across multiple secondary sources ([marketmath.io — Kalshi fees](https://marketmath.io/platforms/kalshi); [Whirligig Bear — Maker/Taker Math on Kalshi](https://whirligigbear.substack.com/p/makertaker-math-on-kalshi)) is:

- **Taker fee per contract:** $\text{fee}_{\text{taker}}(P) = \lceil 0.07 \cdot P \cdot (1 - P) \cdot 100 \rceil / 100$, expressed in dollars, where $P \in [0.01, 0.99]$ is the traded price.
- **Maker fee per contract:** 25% of the taker fee, i.e. $\text{fee}_{\text{maker}}(P) = \lceil 0.0175 \cdot P \cdot (1 - P) \cdot 100 \rceil / 100$. Maker fees apply only when a resting order is eventually filled; canceling a resting order is free.

The fee is symmetric in $P$ and peaks at $P = 0.50$, where the taker fee rounds up to $\lceil 0.0175 \cdot 100 \rceil / 100 = 0.02$ — i.e., **2¢ per contract for the taker, 0.5¢ for the maker at the 50¢ quote**. At $P = 0.10$ or $P = 0.90$, the taker fee is $\lceil 0.07 \cdot 0.09 \cdot 100 \rceil / 100 = 0.01$, i.e., one cent. At $P = 0.01$ or $P = 0.99$, $\lceil 0.07 \cdot 0.0099 \cdot 100 \rceil / 100 = 0.01$ — the fee floors at one cent, not zero, because of the ceiling. (Note: some secondary summaries report a 1.75¢ result at $P = 0.50$ by omitting the ceiling; the formula as quoted above with ceiling rounds to 2¢. Verify against the authoritative PDF before go-live.)

Event-specific surcharges have historically appeared on large one-off contracts such as the 2024 U.S. presidential election. Whether the commodities hub carries a commodity-specific surcharge above the base formula could not be verified without the PDF; treat it as an ambiguity.

Kalshi does not charge a separate settlement fee (Rule 6.3 does not impose one). Withdrawal fees, if any, are posted to the fee schedule per Rule 6.4.

**Worked example.** A taker buying 100 contracts of a `KXSOYBEANW` bucket quoted Yes at $P = 0.22$ pays: $0.07 \times 0.22 \times 0.78 \times 100 = 1.2012$ cents per contract → ceil to 2¢ per contract → $2.00 total fee. A maker resting at the same price pays $0.07 \times 0.22 \times 0.78 \times 0.25 \times 100 = 0.30$ cents per contract → ceil to 1¢ → $1.00 total. The fee is material at the one-cent tick: on a mid-grid bucket where the Yes quote is $0.50, a maker-then-taker round trip costs $0.005 per dollar of notional, or 50 bps round-trip.

## 7. Resolution and settlement

Rule 13.1(d) sets the posting deadline: "All Market Outcomes will be posted on Kalshi's website no later than 11:59 pm ET on the day that such Market Outcomes are determined. If the Market Outcome Review Process is initiated under Rule 7.1, the final Market Outcome will be posted on Kalshi's website no later than 11:59 pm ET on the day that the Outcome Review Committee reaches a determination on the Contract's final Market Outcome" ([KalshiEX Rulebook v1.18](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)). The reference price for `KXSOYBEANW-26APR24` is almost certainly read on Friday, April 24, 2026 — the CBOT daily settle posts in mid-afternoon Central time — and outcomes posted within hours. The exchange's standard cadence on analogous products (`KXWTIW`, `KXGOLD`) is same-day settlement by early evening ET.

**Source of reference price.** Appendix A will name the Source Agency — typically the exchange operating the underlying contract (CME Group for soybeans), with fallback to an independent data vendor if the exchange feed is disrupted. Rule 7.2(a) retains Kalshi's discretion to designate a new Source Agency via an objective and verifiable alternative, announced on the website.

**Holiday handling.** Rule 7.2(b) permits the exchange to "adjust the Expiration Date and the timing of Expiration of the Contract" for delayed data, a canceled/rescheduled event, or similar. If April 24 fell on a CBOT holiday (none in 2026), settlement would roll to the next trading day. If the CBOT halts or is on limit-move status at close, Rule 7.2(b) also gives Kalshi cover to adjust.

**Limit-move days.** CBOT soybean futures carry variable daily limits (roughly 7% of price, reset semi-annually; see Phase 01, §2.4). If the May 2026 contract locks limit-up or limit-down on a Friday, the settlement price is the limit-trip price — a single point that crisply resolves every bucket but which, on an unusually volatile day, may not reflect the no-limit "true" price. Kalshi's Appendix A would need to state that the settlement price is "the daily settlement price as published by the exchange," which by construction is the limit price on a locked day. No special handling is implied by the rulebook.

**Settlement mechanics.** On the Settlement Date, Kalshi instructs its Clearing House (Klear, the affiliated DCO) to: (i) notify all members, (ii) debit the settlement account by $1 × (number of in-the-money contracts), (iii) credit winning members' accounts, (iv) delete all contracts from member accounts (Rule 6.3(d)). Fully-collateralized margining means no variation margin is exchanged during the life of the contract; the entire settlement flow is a batch credit on the single resolution day.

**Market Outcome Review Process.** Rule 7.1 empowers Kalshi to suspend a settlement and convene an Outcome Review Committee if there is a dispute about whether the Payout Criterion is satisfied or if the reference data is ambiguous. The Committee's determination is final. For a commodity contract tied to an exchange settle, this path is unlikely to be triggered — the CBOT settlement number is unambiguous — but the mechanism exists.

## 8. API and market access

Kalshi's trading API is REST + WebSocket. Documentation at [docs.kalshi.com](https://docs.kalshi.com/api-reference) specifies:

- **REST base URL (production):** `https://api.elections.kalshi.com/trade-api/v2`. The `/elections/` subdomain is a legacy artifact of Kalshi's 2024 election products and is the canonical production host.
- **REST base URL (demo):** `https://demo-api.kalshi.co/trade-api/v2` for sandbox testing.
- **Market-data endpoints:** `GET /markets` (with `status` filter: `unopened`, `open`, `closed`, `settled`), `GET /markets/{ticker}`, `GET /markets/{ticker}/orderbook`, `GET /markets/{ticker}/candlesticks` (1-min / 1-hour / 1-day aggregations), `GET /markets/trades`, plus batch-orderbook retrieval. Event enumeration via `GET /events`, `GET /events/{ticker}`, `GET /events/{ticker}/metadata`, `GET /events/{ticker}/candlesticks`. Historical data lives under `/historical/*` with a documented live-vs-historical boundary cutoff.
- **Trading endpoints:** `POST /portfolio/orders` (create), `DELETE /portfolio/orders/{id}` (cancel), `GET /portfolio/orders`, `GET /portfolio/fills`, `GET /portfolio/positions`, RFQ submission under `/communications`.
- **WebSocket:** single connection to `wss://api.elections.kalshi.com/` multiplexes subscriptions by channel. Channels include `orderbook_delta`, `ticker`, `trade`, `fill`, `market_positions`, `market_lifecycle_v2`, `multivariate_market_lifecycle`, `communications`, `order_group_updates`, `user_orders`. Subscribe via a JSON `subscribe` command naming the channel set and the target `market_ticker` (e.g., `KXSOYBEANW-26APR24-17`).

**Authentication.** API calls are authenticated with an RSA key pair ([Kalshi Docs — API Keys](https://docs.kalshi.com/getting_started/api_keys)):

- Signing algorithm: **RSA-PSS with SHA-256**, MGF1 (SHA-256), salt length equal to digest length (32 bytes).
- Message to sign: the concatenation of `KALSHI-ACCESS-TIMESTAMP` (ms since epoch, as ASCII decimal), the HTTP method, and the request path *without query parameters*.
- Signature: base64-encoded.
- Required headers: `KALSHI-ACCESS-KEY` (UUID Key ID), `KALSHI-ACCESS-TIMESTAMP`, `KALSHI-ACCESS-SIGNATURE`.
- Private keys are not recoverable post-generation.

**Rate limits.** Tiered leaky-bucket scheme, tokens/sec per bucket ([Kalshi Docs — Rate Limits](https://docs.kalshi.com/getting_started/rate_limits)):

- Basic: 200 reads / 100 writes.
- Advanced: 300 / 300.
- Premier: 1,000 / 1,000.
- Paragon: 2,000 / 2,000.
- Prime: 4,000 / 4,000.

Default request cost: 10 tokens (so Basic = 10 full-cost writes/sec). Order cancels are cheaper (2 tokens). Over-quota returns HTTP 429 with body `{"error": "too many requests"}` and no `Retry-After` header — clients must implement exponential backoff. Batch requests are not discounted.

**Market-maker program.** Chapter 4 of the rulebook (Rules 4.1–4.5) establishes a Market Maker designation with: (i) reduced fees, (ii) Rule 5.15 position-limit exemption on contracts covered by the Market Maker agreement, (iii) Position Accountability Levels ten times those of non-Market Makers (Rule 4.5(a)), (iv) bespoke quoting obligations (spread cap, minimum depth, time-in-book). Kalshi has discretion over designation; more than one Market Maker program may run concurrently. No public MM roster is published.

## 9. Regulatory and operational

KalshiEX LLC was designated by the CFTC as a Designated Contract Market under Section 5 of the Commodity Exchange Act and CFTC Regulation 38.3(a) on **November 4, 2020** ([CFTC Press Release 8302-20](https://www.cftc.gov/PressRoom/PressReleases/8302-20)). As a DCM, Kalshi is subject to 17 CFR Part 38 (DCM core principles) and Part 40 (product-listing self-certifications).

New contracts are listed under **CFTC Regulation 40.2(a)**. Every Kalshi product filing carries the boilerplate "Pursuant to Section 5c(c) of the Commodity Exchange Act and Section 40.2(a) of the regulations of the Commodity Futures Trading Commission, KalshiEX LLC (Kalshi), a registered DCM, hereby notifies the Commission that it is self-certifying the … contract" ([KalshiEX 40.2(a) filing template](https://www.cftc.gov/sites/default/files/filings/ptc/25/09/ptc09242531143.pdf)). The filing comprises: (i) an explanation and analysis letter, (ii) a certification paragraph, (iii) Appendix A with the public Terms and Conditions, and (iv) Confidential Appendices B (further considerations), C (source agency), and D (core-principles compliance), the last three protected under a FOIA confidential-treatment request. Filings are concurrently posted at `https://kalshi.com/regulatory/filings`.

The commodities hub — including `KXSOYBEANW` — was publicly announced on **April 15, 2026**, rolling soybeans, corn, wheat, sugar, coffee, copper, nickel, diesel, lithium, and natural gas into the existing WTI / Brent / gold / silver set, with 24/7 trading including weekends ([Kalshi News — Commodities Hub launch](https://news.kalshi.com/p/kalshi-launches-commodities-hub-new-markets); cross-referenced by [Crypto Briefing — Kalshi Commodities Expansion](https://cryptobriefing.com/24-7-commodities-trading-kalshi-expansion/)). No CFTC disapproval or enforcement action has been reported against the commodities suite as of the research date. Kalshi's prior regulatory history is not unblemished — the CFTC disapproved Kalshi's "Congressional Control" political contracts in September 2023 ([CFTC Press Release 8780-23](https://www.cftc.gov/PressRoom/PressReleases/8780-23)) — but that action was confined to event contracts involving U.S. federal elections under Section 5c(c) and does not bear on commodity-referenced products, which align directly with the traditional DCM mandate.

Kalshi describes itself to retail as a CFTC-regulated exchange, with FCM and self-clearing member access models ([Kalshi Help — How is Kalshi Regulated?](https://help.kalshi.com/en/articles/13823765-how-is-kalshi-regulated)). Clearing is performed by Kalshi's affiliated DCO, Klear, under rulebook Chapter 6. All positions are fully cash-collateralized (Rule 6.1(b)); there is no variation margin and no daily mark-to-market cash flow — the settlement date is the only cash movement.

## 10. Open ambiguities and questions to resolve before pricing

1. **Live-page bucket grid and Yes/No prices for `KXSOYBEANW-26APR24-17`.** `kalshi.com` HTTP 429'd every fetch attempt during the research window. Resolve by authenticated `GET /events/KXSOYBEANW-26APR24` and record the `floor_strike` / `cap_strike` / `yes_bid` / `yes_ask` on each child market as a timestamped snapshot.
2. **Exact CBOT reference.** Appendix A of the as-filed 40.2(a) document — not yet located in the public SIRT index — will name the reference contract month, the settlement price type (daily settle vs. 2:20 p.m. CT close vs. VWAP), the roll rule at First Notice Day, and any fallback source. Until then, the pricing engine should treat the reference as a configuration parameter defaulted to "May 2026 ZS daily settle" and double-check via a paper-trade after the first resolved week.
3. **Per-contract position limit.** Rule 5.19 defers to Terms and Conditions, which were unretrievable. The default working assumption is a $25,000 max-loss cap per member (consistent with prior Kalshi commodity products), with the caveat that this number needs confirmation against the Appendix A of the first `KXSOYBEANW` filing.
4. **Fee surcharge.** Whether commodities markets carry an event-specific surcharge above the base $0.07 P(1-P)$ taker / 25%-of-taker maker formula is not confirmed. The `kalshi-fee-schedule.pdf` is the authoritative source.
5. **Tick size override.** Rule 13.1(c) permits per-contract tick-size overrides. Soybeans could plausibly use a $0.02 tick to thin the book; until checked, assume $0.01.
6. **Bucket grid change policy.** The rulebook does not specify when Kalshi can add or re-center buckets intraweek in response to a large price move. Appendix A may contain "additional strikes can be added as needed" language (as the `COMPETITIONREALITYELIM` template does), but the trigger and timing are unspecified.
7. **CBOT holiday / limit-move resolution.** Rule 7.2(b) is discretionary. Pricing engines should scenario-plan for a limit-down day falling on a Friday expiry.
8. **Market-maker program eligibility and fee rebates.** Chapter 4 establishes the framework; the specific program terms (spread cap, minimum bid/ask size, uptime requirement, rebate schedule) live in a separate Market Maker Agreement that is not public.
9. **Collateral earnings / interest treatment.** Rule 8.1 covers investment of participant funds; whether members earn interest on unused collateral (as on some competing venues) is not addressed in the public rulebook and should be confirmed.
10. **FCM access vs. self-clearing.** Retail access generally runs through Robinhood Derivatives (a Kalshi FCM) and other integrated brokers; self-clearing membership is a separate path with different onboarding. A pricing engine running as a self-clearing member has direct API access; one routing through an FCM inherits any additional constraints imposed by that FCM (order-size caps, pre-trade risk checks).

## Key takeaways

- `KXSOYBEANW` is a weekly **binary digital-corridor** structure tiled over the plausible Friday CBOT soybean settle, implemented as a set of Kalshi Markets under a single Event. Each bucket pays $1 Yes if the Friday settle lands in its range and $0 otherwise.
- Ticker parses hierarchically: Series `KXSOYBEANW` → Event `KXSOYBEANW-26APR24` → Market `KXSOYBEANW-26APR24-17`. The trailing integer is an ordinal bucket index, not a price.
- The reference price is almost certainly the front-month CBOT soybean futures daily settlement on the expiration Friday — for the sample contract, the May 2026 contract (ZSK26) on April 24, 2026 — but the precise settlement source and snapshot time must be confirmed from the per-contract Appendix A.
- All Kalshi contracts use cent-granular pricing with a $0.01–$0.99 price band, one-dollar notional, FIFO price-time matching (Rule 5.9), five-level book visibility (Rule 5.13), a $0.20 No Cancellation Range around fair-market value (Rule 5.11), and per-contract position limits stated as maximum-loss dollar caps.
- Fees follow the closed-form $\lceil 0.07 \cdot P(1-P) \cdot 100 \rceil / 100$ taker formula, 25%-of-taker maker, peaking at 2¢ per contract at $P = 0.50$ and flooring at 1¢ near the price-band edges.
- API access is REST + WebSocket, authenticated with RSA-PSS SHA-256 signatures over `{ts}{method}{path}`, rate-limited in a tiered leaky-bucket scheme. Over-limit returns 429 with no `Retry-After` header.
- Kalshi is a CFTC DCM designated November 4, 2020; new products self-certify under 17 CFR 40.2(a). The commodities hub including soybeans launched April 15, 2026 and trades 24/7. Clearing is at affiliated DCO Klear; positions are fully cash-collateralized with no variation margin.
- Market Makers under Chapter 4 receive fee benefits, position-limit exemptions, and 10×-higher Position Accountability Levels in exchange for quoting obligations specified in a non-public Market Maker Agreement.
- The single largest unknown for pricing is the reference-price specification (contract month, settlement type, snap time); the next largest is whether commodity markets carry any event-specific fee surcharge above the base formula.

## References

- [Kalshi Markets — `kxsoybeanw-26apr2417` contract page (inaccessible at research time, HTTP 429)](https://kalshi.com/markets/kxsoybeanw/soybean-weekly/kxsoybeanw-26apr2417)
- [Kalshi Markets — `KXSOYBEANW` series landing (inaccessible at research time, HTTP 429)](https://kalshi.com/markets/kxsoybeanw)
- [Kalshi Regulatory — Rulebook & Contract Rules hub](https://kalshi.com/regulatory/rulebook)
- [Kalshi Regulatory — Filings (public 40.2(a) submissions)](https://kalshi.com/regulatory/filings)
- [KalshiEX LLC Rulebook v1.15 (January 17, 2025)](https://cdn.robinhood.com/assets/robinhood/legal/KalshiEX_LLC_Rulebook.pdf)
- [KalshiEX LLC Rulebook v1.18 (2025, posted via CFTC filing)](https://www.cftc.gov/sites/default/files/filings/orgrules/25/07/rules07012525155.pdf)
- [Kalshi API Reference — endpoints, schemas](https://docs.kalshi.com/api-reference)
- [Kalshi API Docs — Market Ticker conventions](https://docs.kalshi.com/websockets/market-ticker)
- [Kalshi API Docs — API Keys (RSA-PSS signing)](https://docs.kalshi.com/getting_started/api_keys)
- [Kalshi API Docs — Authenticated-Request Quick Start](https://docs.kalshi.com/getting_started/quick_start_authenticated_requests)
- [Kalshi API Docs — Rate Limits (tiered leaky-bucket)](https://docs.kalshi.com/getting_started/rate_limits)
- [Kalshi API Docs — Master endpoint index (`llms.txt`)](https://docs.kalshi.com/llms.txt)
- [Kalshi Help Center — Fees](https://help.kalshi.com/en/articles/13823805-fees)
- [Kalshi Help Center — Request Additional Strikes](https://help.kalshi.com/en/articles/13823834-request-additional-strikes)
- [Kalshi Help Center — How is Kalshi regulated?](https://help.kalshi.com/en/articles/13823765-how-is-kalshi-regulated)
- [Kalshi News — Commodities Hub launch (April 2026)](https://news.kalshi.com/p/kalshi-launches-commodities-hub-new-markets)
- [Kalshi Fee Schedule PDF (canonical; inaccessible at research time, HTTP 429)](https://kalshi.com/docs/kalshi-fee-schedule.pdf)
- [CFTC Press Release 8302-20 — KalshiEX LLC designated as a DCM (Nov 4, 2020)](https://www.cftc.gov/PressRoom/PressReleases/8302-20)
- [CFTC Press Release 8780-23 — CFTC disapproves KalshiEX Congressional Control contracts (Sep 22, 2023)](https://www.cftc.gov/PressRoom/PressReleases/8780-23)
- [CFTC DCM oversight page](https://www.cftc.gov/IndustryOversight/DCM/index.htm)
- [CFTC SIRT (Submissions Information Research Tool) — filings search](https://sirt.cftc.gov/sirt/sirt.aspx)
- [KalshiEX LLC 40.2(a) filing — template (Sep 24, 2025; `COMPETITIONREALITYELIM`)](https://www.cftc.gov/sites/default/files/filings/ptc/25/09/ptc09242531143.pdf)
- [KalshiEX LLC 40.2(a) filing (Sep 2, 2025)](https://www.cftc.gov/sites/default/files/filings/ptc/25/09/ptc09022529868.pdf)
- [KalshiEX LLC 40.2(a) filing (Aug 5, 2025)](https://www.cftc.gov/sites/default/files/filings/ptc/25/08/ptc08052527990.pdf)
- [KalshiEX LLC 40.2(a) filing (Jun 25, 2025)](https://www.cftc.gov/sites/default/files/filings/ptc/25/06/ptc06252524763.pdf)
- [KalshiEX LLC 40.2(a) filing (Jan 22, 2025)](https://www.cftc.gov/sites/default/files/filings/ptc/25/01/ptc01222514045.pdf)
- [KalshiEX LLC Rulebook Amendment — Position Limits (Feb 2023)](https://www.cftc.gov/sites/default/files/filings/orgrules/23/02/rule022123kexdcm002.pdf)
- [CME Group — CBOT Soybean Futures Contract Specs](https://www.cmegroup.com/markets/agriculture/oilseeds/soybean.contractSpecs.html)
- [CME Group — Daily Bulletin (settlement-price publication)](https://www.cmegroup.com/market-data/daily-bulletin.html)
- [CBOT Rulebook Chapter 11 — Soybean Futures (PDF)](https://www.cmegroup.com/rulebook/CBOT/II/11/11.pdf)
- [marketmath.io — Kalshi Fees Explained (secondary, fee-formula cross-check)](https://marketmath.io/platforms/kalshi)
- [Whirligig Bear — Maker/Taker Math on Kalshi (secondary, fee-formula cross-check)](https://whirligigbear.substack.com/p/makertaker-math-on-kalshi)
- [Crypto Briefing — Kalshi Commodities Expansion (secondary, launch confirmation)](https://cryptobriefing.com/24-7-commodities-trading-kalshi-expansion/)
- [Bloomberg — Kalshi Expands Commodities Prediction Markets (April 15, 2026; paywalled)](https://www.bloomberg.com/news/articles/2026-04-15/kalshi-expands-commodities-predictions-market-on-war-volatility)
