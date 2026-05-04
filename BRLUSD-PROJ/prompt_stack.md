# USD/BRL Touch-Barrier Market Making — Sequential Research Prompt Stack

## Preamble

This file is a stack of sixteen self-contained research prompts. Execute them **one at a time, each in a fresh context window**. Copy a single phase's prompt block into a new conversation, run it to completion, save its output, then move to the next phase.

### Folder layout

All outputs live in a `./research/` subfolder of the working directory. File naming is fixed:

```
./research/phase_01_fx_market_structure.md
./research/phase_02_fx_mm_pricing_models.md
./research/phase_03_barrier_option_pricing.md
./research/phase_04_fx_em_tooling.md
./research/phase_05_brazil_internal_drivers.md
./research/phase_06_brl_external_drivers.md
./research/phase_07_brazil_political_calendar.md
./research/phase_08_usdbrl_iv_surface.md
./research/phase_09_discretionary_em_fx.md
./research/phase_10_systematic_fx.md
./research/phase_11_adverse_selection.md
./research/phase_12_data_streams_for_theo.md
./research/phase_13_kxusdbrlmax_contract.md
./research/phase_14_theo_and_quote_policy.md
./research/phase_15_data_tooling_stack.md
./research/phase_16_strategy_synthesis.md
```

Create the `./research/` directory before starting Phase 1 if it does not already exist.

### Execution conventions (apply to every prompt)

1. **Statelessness.** Every prompt assumes a fresh context window. It must read the prior `.md` files it explicitly names from `./research/` before doing any new research. If any expected prior file is missing, halt immediately and surface the gap rather than improvising.
2. **Primary sources.** Every prompt requires aggressive use of `web_search` and `web_fetch`. Citations must point to primary sources where possible: BIS, IMF, central bank publications (BCB, Federal Reserve, ECB), exchange documentation (CME, B3, ICE), academic journals (Journal of Finance, RFS, JFE, Journal of Financial Economics, Journal of Financial Markets, Review of Financial Studies, Journal of International Money and Finance), preprint servers (SSRN, arXiv, NBER, CEPR), regulatory filings (CFTC, CVM), and named practitioner research notes.
3. **Citation density and depth.** Each phase specifies a target word count and a minimum number of distinct cited sources. Treat these as floors, not ceilings.
4. **Uncertainty preservation.** Speculation must be labeled. Do not present a contested empirical claim or a contested model assumption as settled. When evidence is mixed, present the disagreement.
5. **Theo-quality lens.** Phases 5–16 must explicitly state, in a dedicated subsection, what input(s) to the eventual theoretical-value (theo) computation the phase produces and at what cadence.
6. **Adverse-selection lens.** Phases 5–16 must explicitly state, in a dedicated subsection, the adverse-selection implications: which information windows the phase's content opens up, who is plausibly informed, and how an uninformed market maker is exposed.
7. **No equation hand-waving.** Use LaTeX-in-Markdown (`$...$` inline, `$$...$$` display) for every nontrivial equation. State assumptions and notation explicitly.
8. **Out-of-sample discipline.** Phases 1–12 contain zero references to Kalshi, prediction markets, binary or one-touch contracts traded on prediction venues, or any specific Kalshi series. Foundational research stays clean. Phase 13 is the first introduction of Kalshi.
9. **Output format.** Each output file begins with: title, phase number, date generated, list of prior phases consumed, target word count actually achieved, and a count of distinct sources cited. Then the body.

### Cross-cutting deliverable: the theo

The downstream artifact this stack supports is a **high-quality theoretical value** for a long-dated USD/BRL one-touch barrier contract resolving on whether USD/BRL touches above 4.9999 at any point before December 31, 2026, plus a quote policy that places two-sided liquidity around that theo while qualifying for any liquidity-incentive program offered on the series. Hedging is an open second-order question. Every phase from 5 onward must keep the question "how does this sharpen the theo or reduce adverse selection?" in view.

---

## Phase 1 — USD/BRL FX Market Structure Foundations

```
You are executing Phase 1 of 16 in a research stack on USD/BRL FX market structure
and emerging-market FX market making. This is the foundational phase. There are no
prior phases to consume.

Goal
Produce a deep, structural reference document on the USD/BRL complex as a financial
market. The downstream stack will reason about which venue's price is the "true"
price at any moment, what the basis dynamics between venues look like, and which
participants drive flow at which times. Your output is the substrate for every later
phase.

Method
Use web_search and web_fetch aggressively. Prioritize primary sources: BCB
(Banco Central do Brasil) publications and circulars, CVM filings, B3 contract
specifications, CME Group product specifications, BIS Triennial Central Bank Survey
of Foreign Exchange and OTC Derivatives Markets (most recent and prior surveys),
IMF Article IV consultations on Brazil, Anbima publications. Supplement with named
academic and practitioner sources where the primary record is incomplete.

Deliverable
Save to ./research/phase_01_fx_market_structure.md. Target 4,000–6,000 words,
≥25 distinct sources cited inline.

Required sections in the output
1. Spot interbank market and conventions: settlement (T+2), Brazilian and US holiday
   calendars and their interaction, quoting conventions (USDBRL is quoted as BRL
   per USD), tick size norms, typical interbank spreads in calm vs stressed regimes.
2. Onshore deliverable spot vs offshore NDF: the Brazilian capital-account regime,
   why offshore NDFs dominate for non-resident participants, the historical IOF tax
   on FX inflows and its current status, BCB Resolution 4.373 (and predecessor
   Resolution 2.689) on non-resident portfolio investment, the BCB authorization
   regime for FX dealers (bancos autorizados a operar em câmbio), the role of the
   Sistema do Banco Central (SISBACEN) FX registration system.
3. CME BRL futures (6L) and BRL options: contract specs (size, tick, settlement
   method, last trading day), trading hours, liquidity profile by tenor, role as a
   hedging venue for offshore dealers.
4. B3 (formerly BM&FBovespa) FX complex: DOL (full-size USD/BRL future, USD 50,000
   notional), WDO (mini USD/BRL future, USD 10,000 notional), DR1 (rolling spot
   future), DI futures and pre-DI swaps, the cupom cambial curve (DDI futures, FRC
   forwards), WTI-style "casado" trade combining DOL with cash settlement. Document
   that B3 is the deepest BRL futures market in the world by volume.
5. BCB intervention regime: spot intervention auctions, line auctions (leilão de
   linha for USD liquidity provision via repos), traditional swap auctions (swap
   cambial tradicional, sells USD forward), reverse swap auctions (swap reverso),
   cupom cambial intervention. Cite the BCB's stated reaction function from its
   Inflation Reports and from BCB Working Papers.
6. PTAX fixing: the methodology (BCB polls dealers four times per day, computes the
   mean of the trimmed dealer quotes; the day's PTAX is the mean of the four
   intraday windows), the publication time, the D2 settlement convention for many
   BRL-denominated contracts (DOL settles to PTAX of the day prior to expiry), and
   the documented controversy around PTAX manipulation.
7. Market hours and price discovery flow: the daily handover from Asia to Europe
   to NY, B3's session hours (DOL trades roughly 9:00–18:00 BRT with after-hours),
   CME 6L's near-24-hour electronic session, how price discovery typically flows
   between venues during BCB intervention, US data releases, and Brazilian data
   releases.
8. Participant taxonomy: Brazilian commercial banks (Itaú, Bradesco, Santander
   Brasil, BB, Caixa), foreign banks operating onshore (JPM, Citi, HSBC, Goldman),
   Brazilian exporters (Vale, Petrobras, JBS, agribusiness exporters) and importers,
   real-money portfolio investors (foreign pension funds via Resolution 4.373),
   foreign hedge funds in NDF and CME, Brazilian hedge funds and family offices,
   retail via B3 (the rise of WDO retail trading post-2018), high-frequency firms
   on B3 and CME.
9. A "venue map" diagram in ASCII or markdown table: rows are venues
   (interbank spot, NDF, CME 6L, B3 DOL, B3 WDO, BCB auctions), columns are
   (price-discovery weight, typical participant mix, typical session, latency to
   public data, hedging utility for an offshore market maker).
10. A glossary of Portuguese-language FX terms practitioners will encounter (casado,
    cupom cambial, dólar futuro, leilão de linha, contrato a termo, etc.).

Sources to prioritize
- BCB website (bcb.gov.br) — Circulars on FX market regulation, intervention
  announcements, FX statistics, working paper series.
- B3 contract specifications pages for DOL, WDO, DI, DDI.
- CME Group product pages for 6L and BRL options.
- BIS Triennial Survey reports (most recent — search "BIS Triennial Central Bank
  Survey foreign exchange turnover").
- Goldfajn & Olivares (BCB working papers on FX intervention).
- Garcia & Volpon, "DNDFs: A More Efficient Way to Intervene in FX Markets?" (BCB
  working paper).
- Kohlscheen, Murcia, Contreras (BIS) on EM FX.
- Chamon, Garcia, Souza (BCB / IMF) on FX intervention effectiveness.

Do NOT
- Mention Kalshi, prediction markets, binary contracts, one-touch contracts on
  prediction venues, or any prediction-market series. This is pure FX market
  structure.
- Substitute textbook generalities for primary-source detail. If you cannot find
  the BCB's specific intervention auction format from primary sources, say so.
- Treat 2024 IOF rates as still in force. Verify current status of IOF on FX
  transactions as of 2026.
- Confuse PTAX (BCB fixing) with the WMR 4pm London fix. They are different
  mechanisms.
```

---

## Phase 2 — FX Market Making Pricing Models (General → EM-Specific)

```
You are executing Phase 2 of 16. Prior context required: read
./research/phase_01_fx_market_structure.md fully before beginning. If that file
does not exist, halt and report the gap; do not proceed.

Goal
Survey market making pricing models with an FX lens, then narrow to EM-specific
adaptations and frictions. Output is the canonical reference for how an FX dealer
prices and skews quotes, against which any later FX-market-making model in this
project will be benchmarked.

Method
Read Phase 1 first. Then web_search and web_fetch. Prioritize the academic
primary literature (the cited authors below) and the BIS / central-bank working
paper literature on FX microstructure. Supplement with practitioner books and
named dealer research where peer-reviewed sources are thin.

Deliverable
Save to ./research/phase_02_fx_mm_pricing_models.md. Target 5,000–7,000 words,
≥30 distinct sources cited inline. Mathematical formulations are required —
present the canonical equations with notation explicitly defined.

Required sections in the output
1. Glosten–Milgrom (1985) sequential trade model: setup, the bid-ask spread as
   compensation for adverse selection, application to FX dealer quoting.
2. Kyle (1985) and Kyle (1989) auction models: lambda as the depth coefficient,
   the linkage to FX dealer inventory.
3. Easley–O'Hara PIN, and Easley–López de Prado–O'Hara VPIN: estimation
   procedures and the empirical FX-applied literature.
4. The FX microstructure approach of Lyons: cite "The Microstructure Approach to
   Exchange Rates" (MIT Press, 2001), Evans & Lyons "Order Flow and Exchange Rate
   Dynamics" (JPE 2002), Evans & Lyons "Exchange Rate Fundamentals and Order Flow"
   (NBER 2007). Document the order-flow → exchange-rate evidence.
5. Continuous-time inventory models: Avellaneda–Stoikov (2008) "High-frequency
   trading in a limit order book," Guéant–Lehalle–Tapia (2013) "Dealing with the
   inventory risk: a solution to the market making problem," Cartea–Jaimungal
   (multiple papers, especially their textbook "Algorithmic and High-Frequency
   Trading," 2015). Present the AS reservation price and optimal spread:
   $$r(s,t) = s - q\gamma\sigma^2(T-t)$$
   $$\delta^a + \delta^b = \gamma\sigma^2(T-t) + \frac{2}{\gamma}\ln\left(1+\frac{\gamma}{k}\right)$$
   with notation defined. Discuss extensions to FX (asymmetric arrival rates,
   multi-currency, dealer client tiers).
6. Optimal execution theory adjacent to MM: Almgren–Chriss; Bertsimas–Lo;
   Obizhaeva–Wang. Brief, since this is a hedging-side concern.
7. EM-specific frictions: wider spreads, asymmetric information from local
   banks (the BIS literature on EM dealer informational advantages), intervention
   regimes that break stationarity (the cited Kohlscheen / Chamon / Garcia
   literature), jump risk around political news, regime switches between calm
   and crisis. Emphasize how these violate the assumptions of the
   Avellaneda–Stoikov class of models.
8. Dealer-quote practitioner mechanics in FX: skew on spot, vol, and risk
   reversals; size tiers (small clients get tight quotes, large macro funds get
   wide quotes); quote fade (last-look) after large hits; the role of streaming
   vs RFQ; the BIS literature on "internalisation" vs "externalisation" of
   client flow.
9. Bringing it together: a synthesis section on "what an EM-FX market maker
   actually solves," distilling which model components matter most for a
   small/medium dealer in BRL — adverse selection > inventory > microstructural
   noise.
10. Adverse-selection implications: with reference to Phase 1, identify which
    USD/BRL participant types are presumptively informed and what the dealer-quote
    response is in each case.

Theo-input contribution
This phase does not produce theo inputs directly; it produces the model machinery
that the theo + quote policy in Phase 14 will draw from. Make this explicit in
the output's closing section.

Sources to prioritize
- Avellaneda & Stoikov (2008), Quantitative Finance.
- Guéant, Lehalle, Tapia (2013), Mathematics and Financial Economics.
- Cartea, Jaimungal & Penalva, "Algorithmic and High-Frequency Trading" (CUP 2015).
- Lyons, "The Microstructure Approach to Exchange Rates" (MIT 2001).
- Evans & Lyons, several JPE / JIE / RFS papers on FX order flow.
- Easley, Kiefer, O'Hara, Paperman on PIN.
- Easley, López de Prado, O'Hara on VPIN.
- BIS Working Papers and Quarterly Review articles on FX dealer behavior and
  internalisation (e.g., Schrimpf & Sushko; Drehmann & Sushko).
- Bjønnes & Rime on FX dealer behavior.

Do NOT
- Mention Kalshi, prediction markets, or binary/touch contracts on prediction
  venues.
- Substitute generic algorithmic-trading textbook material where FX-specific or
  EM-specific evidence exists.
- Confuse the Avellaneda–Stoikov MM model with the Almgren–Chriss execution
  model — they solve different problems.
```

---

## Phase 3 — Barrier Option Pricing (Standalone, No Kalshi)

```
You are executing Phase 3 of 16. No prior phases are required for content, but
you must check that ./research/phase_01_fx_market_structure.md and
./research/phase_02_fx_mm_pricing_models.md exist (the stack expects sequential
execution). If either is missing, halt and report.

Goal
Produce a comprehensive technical reference on barrier option pricing, with
emphasis on one-touch contracts. The downstream theo computation will price a
long-dated upside one-touch on USD/BRL, so the smile-dependence and discrete
monitoring sections matter most. This is an options-pricing literature review.

Method
Use web_search and web_fetch. Pull primary papers from SSRN, journal pages, and
practitioner-textbook excerpts. Where equations are central, transcribe them
correctly with notation defined.

Deliverable
Save to ./research/phase_03_barrier_option_pricing.md. Target 6,000–8,000 words,
≥30 distinct sources cited. Equations required throughout in LaTeX.

Required sections in the output
1. Taxonomy of barrier options: knock-in vs knock-out, up vs down, and the
   reduction of one-touches and no-touches to combinations of barriers and
   digitals. Show the parity:
   $$C^{up\text{-}out} + C^{up\text{-}in} = C^{vanilla}$$
   and the analogous one-touch ↔ digital decomposition.
2. Closed-form barrier pricing under GBM: Reiner–Rubinstein (1991) and
   Rubinstein–Reiner formulas for the eight standard barrier types. State each
   formula with full notation. Include the one-touch price formula explicitly:
   for a continuously monitored upside one-touch with barrier $B > S_0$,
   payoff $\mathbf{1}\{\max_{t\in[0,T]} S_t \ge B\}$,
   show the closed form involving the normal CDF, $\mu$, $\sigma$, and the
   reflection-principle log moneyness.
3. The reflection principle and first-passage densities for Brownian motion
   with drift. Derive (or transcribe with citation) the joint density of the
   running maximum and the terminal value.
4. Discrete-monitoring corrections: Broadie–Glasserman–Kou (1997) "A continuity
   correction for discrete barrier options" — the σ√Δt shift:
   $$B_{disc} = B \cdot \exp(\beta \sigma \sqrt{\Delta t})$$
   where $\beta \approx 0.5826$. Explain the intuition and the derivation in
   broad terms. Discuss when this matters (frequent monitoring vs daily fix).
5. Stochastic volatility extensions: Heston model barrier pricing, the
   challenges (no closed form, requires PDE or MC), the literature on Heston
   barrier MC (Broadie–Kaya for exact simulation; Andersen QE scheme). SABR
   model and its limits for barrier products.
6. Local volatility: Dupire (1994) and the calibration of local vol from the
   implied vol surface. The well-known overpricing bias of pure local-vol for
   forward-starting and barrier products (Hagan et al., "Managing Smile Risk").
7. Stochastic-Local Volatility (SLV): the practitioner standard for FX
   barrier pricing. Cite Lipton, Tataru–Fisher, Ren–Madan–Qian. SLV combines the
   marginal-distribution match of local vol with the dynamics of stochastic
   vol, and is widely cited as the production model for FX exotics desks.
8. Jump models: Merton (1976) jump-diffusion, Bates (1996) SVJ, Kou (2002)
   double-exponential jumps. Show the touch probability impact of even small
   jump intensities — for a barrier far from spot, jump models materially raise
   touch probabilities relative to GBM.
9. Monte Carlo for barrier products with Brownian-bridge correction
   (Beaglehole–Dybvig–Zhou 1997, Glasserman 2004 "Monte Carlo Methods in
   Financial Engineering" Ch. 6). The bridge correction is essential to avoid
   underestimating touch probabilities when discretizing.
10. Static replication of barrier options: Carr–Bowie–Ellis "Static Hedging of
    Exotic Options" (JoF 1998), Derman–Ergener–Kani "Static Options
    Replication." Present the replication recipe for a one-touch using
    a strip of vanilla calls/puts.
11. Greeks of one-touches: derive (or transcribe) the delta, gamma, vega, and
    theta near and far from the barrier. Discuss:
    - Gamma explosion as spot approaches barrier near expiry.
    - Vega sign flip: a one-touch that is far in-the-money (i.e., spot near
      barrier with time remaining) has negative vega — more vol means higher
      probability of touch already realized, but also more probability of paths
      that reach the barrier and stay above. Document the sign-flip region
      precisely.
    - Theta: positive for unobserved one-touches (probability decays with time
      remaining), negative for already-touched.
    - Delta discontinuity at expiry.
12. Smile-dependence of one-touch prices: present the calibration sensitivity —
    for an upside one-touch on USD/BRL with barrier above spot and 7 months to
    expiry, small changes in upside-wing skew (25Δ risk-reversal) translate to
    large changes in fitted touch probability. Cite Hakala–Wystup "Foreign
    Exchange Risk" and the DKK / Wystup literature.
13. Why GBM is a particularly bad model for these contracts: combine the smile,
    jump, and stochastic-vol arguments. State the practical implication: any
    serious theo for a long-dated FX one-touch must be calibrated to the vol
    surface, not assume a flat vol.

Adverse-selection implications
N/A for Phase 3 — this is a pricing-theory phase.

Theo-input contribution
N/A directly. State explicitly that this phase produces the modeling toolkit
that Phase 14 will instantiate.

Sources to prioritize
- Reiner & Rubinstein (1991), "Breaking down the barriers," RISK.
- Rubinstein & Reiner (1991), "Unscrambling the binary code," RISK.
- Broadie, Glasserman & Kou (1997), Mathematical Finance.
- Beaglehole, Dybvig & Zhou (1997), Financial Analysts Journal.
- Glasserman (2004), "Monte Carlo Methods in Financial Engineering."
- Hagan, Kumar, Lesniewski, Woodward, "Managing Smile Risk."
- Wystup, "FX Options and Structured Products" (Wiley).
- Carr, Bowie & Ellis (1998), JoF.
- Lipton, "The vol smile problem," and Lipton & Sepp on SLV.
- Bates (1996), RFS; Kou (2002), Management Science; Merton (1976), JFE.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues. This is a pure options literature review.
- Confuse American digitals with one-touches — they are different (a one-touch
  pays at touch time or at expiry depending on convention; American digital
  pays only at expiry if breached).
- Treat the σ√Δt Broadie correction as the only discrete-monitoring fix; note
  that it assumes Brownian dynamics.
- Skip the smile-dependence discussion — it is the most important practical
  message of the phase.
```

---

## Phase 4 — Tooling and Infrastructure for FX / EM-FX Traders

```
You are executing Phase 4 of 16. Prior phases required: Phase 1, Phase 2,
Phase 3. Confirm all three .md files exist in ./research/ before starting; halt
if any are missing.

Goal
Inventory the tooling and infrastructure ecosystem that serious FX traders
(and EM-FX desks specifically) actually use. The downstream stack will pick a
minimum-viable subset for a small prototype. Be honest about cost tiers and
retail accessibility.

Method
Web research across vendor sites, Stack Overflow / Quant.SE threads,
practitioner blog posts, BIS / IOSCO surveys of trading-system usage.

Deliverable
Save to ./research/phase_04_fx_em_tooling.md. Target 3,500–5,000 words, ≥25
distinct sources cited. Tabular comparisons strongly encouraged.

Required sections in the output
1. Market data:
   - Institutional-only: Bloomberg FXGO, Refinitiv FXall, EBS Direct, Reuters
     Matching (now LSEG), CME Direct / iLink, B3 PUMA, Cinnober/Nasdaq
     trading systems.
   - Brazil-specific: B3 market data feeds, CMA Brasil, Broadcast (Bloomberg /
     Valor PRO), Anbima curves.
   - Central-bank data: BCB SGS API (Sistema Gerenciador de Séries Temporais),
     BCB Olinda API (newer), BCB intervention announcements.
   - Affordable/retail-accessible: TradingView, Investing.com, Yahoo Finance,
     CME public delayed feeds, Polygon.io, Tiingo, Twelve Data, FRED.
   For each, document: data covered, latency, cost tier, API quality, history
   depth.
2. Pricing engines / quant libraries:
   - Institutional: MUREX, Calypso, Numerix, FINCAD, Murex MX.3, in-house
     systems at major dealers.
   - Open-source / commodity: QuantLib (with Python bindings), py_vollib,
     finmc, optopsy, vectorbt, NAG library, Wilmott practitioner libraries.
   - Specifically for FX exotics: Numerix and FINCAD are the two named
     practitioner standards; QuantLib has barrier pricers but production-grade
     SLV calibration is non-trivial.
3. Execution venues / platforms:
   - FXGO, FXall, 360T, ParFX, EBS BrokerTec, Reuters Matching.
   - For listed FX futures and options: CME Direct, B3 ProfitChart, ICE for
     other crosses.
   - For OTC FX options: SuperDerivatives, ICAP / TP ICAP, Tullett Prebon.
   - For credit-FX: MarketAxess.
4. Data vendors specifically covering Brazil:
   - B3 itself (multiple feed tiers), CMA Brasil, Broadcast Bloomberg, Valor
     PRO, Anbima (curves and indices), BCB (free APIs), Banco do Brasil
     research, Itaú research.
5. Risk and portfolio systems:
   - RiskMetrics legacy, Bloomberg PORT, Numerix CrossAsset, ION Trading
     systems, Murex MX.3 risk modules, in-house VaR systems.
6. Open-source Python stacks for FX-aware research:
   - QuantLib-Python, py_vollib, optopsy, vectorbt, mlfinlab, arctic / arcticdb
     for tick storage, KDB+/q for serious tick storage, ClickHouse as a free
     alternative.
   - For SLV / SVI calibration: explicit notes on what's actually open-source
     production-quality (mostly nothing — most institutions roll their own).
7. Realistic stack for a small prop / single-trader operation:
   - Data: BCB SGS/Olinda (free), FRED (free), CME delayed via free Polygon
     tier, B3 via paid feed (~$X/month), Brazilian news from Valor PRO
     (~$Y/month).
   - Pricing: QuantLib-Python for vanillas and basic barriers; build-your-own
     SLV calibration (not trivial — flag this as a multi-week effort) or pay
     for FINCAD Analytics Suite.
   - Execution: depends on Phase 13's findings — defer.
   - Backtesting: pandas + arctic + numba; KDB+ overkill for daily-tick FX.
   Include a price-tagged comparison table.

Adverse-selection implications
For each named data source, flag latency-to-public: data sources with high
latency relative to the institutional feed create adverse-selection risk for a
trader relying on them. Specifically: BCB intervention announcements appear on
their website within minutes but are visible in interbank flow earlier;
COPOM minutes release time is widely known; Focus Report releases at a fixed
time on Mondays.

Theo-input contribution
Identify which tools are required to feed the theo loop (spot, vol surface,
rates) at what update cadences. The Phase 14 theo will need: spot ticks
(seconds), vol surface (refresh hourly is plausible for a 7-month barrier),
rates curves (daily), macro inputs (event-driven). Match each requirement to
specific tools.

Sources to prioritize
- BIS Triennial Survey commentary on dealer infrastructure.
- Quant.StackExchange threads and Wilmott forums for practitioner tool reviews.
- Vendor websites for primary specs — but cross-check vendor claims against
  practitioner reports.
- Anbima.com.br and bcb.gov.br for Brazil-specific data infrastructure.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Recommend a tool you cannot cite a real practitioner using. No vendor
  marketing copy.
- Skip cost tiers — a $5,000/year subscription and a $200,000/year subscription
  are different facts and must be flagged distinctly.
```

---

## Phase 5 — Brazilian Internal Drivers (Fiscal, Monetary, BCB, Real Economy)

```
You are executing Phase 5 of 16. Prior phases required: Phases 1–4. Read all
four .md files in ./research/ before beginning; halt if any are missing.

Goal
Build a complete reference of the domestic Brazilian drivers of USD/BRL: the
monetary regime, the fiscal trajectory, the credit and real-economy cycle, and
the calendar of data releases that move the pair. The downstream theo will
overlay regime-shift conditioning on this; the quote policy will widen and pull
around the events catalogued here.

Method
Web research with primary sources: BCB publications and APIs, Brazilian
National Treasury (Tesouro Nacional) publications, IBGE (Instituto Brasileiro
de Geografia e Estatística) for IPCA / GDP / employment, Anbima for fiscal
curve data, Valor and Folha for political-fiscal context, IMF Article IV,
World Bank, BCB Working Paper series (English).

Deliverable
Save to ./research/phase_05_brazil_internal_drivers.md. Target 5,000–7,000
words, ≥30 distinct sources cited.

Required sections in the output
1. BCB monetary regime: Selic policy rate setting, COPOM (Comitê de Política
   Monetária) cadence (8 meetings per year, dates published a year in advance),
   the inflation-targeting band (currently the CMN-set target with a
   tolerance band — verify current numbers as of 2026), the BCB independence
   law (LC 179/2021) and what it does and does not protect, the BCB's stated
   reaction function from Inflation Reports.
2. Inflation calendar: IPCA (full month, mid-month release), IPCA-15
   (half-month, late-month release), IGP-M (FGV-published wholesale + retail
   composite, used in many rental and contract indices), the Focus
   expectations report (weekly Monday morning, BCB-aggregated dealer
   expectations). Document exact release times in BRT.
3. Fiscal trajectory and framework: the new fiscal framework / arcabouço fiscal
   (Lula government, 2023, replacing the prior teto de gastos / spending cap
   regime), primary deficit dynamics, gross debt/GDP trajectory, the role of
   IPCA-indexed (NTN-B) and Selic-indexed (LFT) and pre-fixed (NTN-F, LTN)
   debt in fiscal sensitivity. Cite Tesouro Nacional Annual Debt Report.
4. Treasury auction calendar: weekly/biweekly schedule, instruments, recent
   auction results format (where available via Tesouro Nacional API).
5. BCB foreign reserves and intervention reaction function: current reserves
   stockpile (~USD 350bn historically), intervention instruments (already
   covered in Phase 1 — recap and link), which BCB officials are most
   market-sensitive (Diretor de Política Monetária, Diretor de Política
   Econômica), historical episodes of large interventions (2002, 2008, 2015,
   2020, 2022).
6. Local rates curve and FX linkage: DI futures (B3) as the headline pre-fixed
   curve, NTN-B real-rate curve, the term-structure decomposition (real rates
   + expected inflation + risk premium), the empirical link between DI
   shocks and USD/BRL — typically a steepening at the long end weakens BRL
   when fiscal-driven, but tightening at the short end (Selic hike
   expectations) strengthens BRL.
7. Real-economy drivers: GDP (IBGE quarterly), industrial production (PIM-PF
   monthly), retail sales (PMC monthly), employment (Caged monthly admin data
   and PNAD monthly survey), credit aggregates (BCB's monthly note on credit).
   Document publication times and typical USD/BRL reactions where empirically
   documented (IMF Selected Issues papers; BCB Working Papers).
8. Credit cycle: the share of earmarked credit (BNDES, rural credit,
   real-estate credit), the role of state-owned banks (BB, Caixa) in
   credit allocation, the household-debt-service ratio, the corporate
   leverage cycle.

Adverse-selection implications
Produce a checklist of "informed-trader windows for USD/BRL driven by Brazilian
internal events," with publication time in BRT and CT, and a brief note on
which participant types likely receive material information first (BCB
intervention dealers; COPOM-meeting-day flow; large local banks for IPCA-15
preview via their internal forecasts; Tesouro auction results visible to
participating banks before public release).

Theo-input contribution
Enumerate every input from this phase that the theo will use:
- Selic and DI curve → drift adjustment in the GBM/SLV-with-drift theo.
- Inflation differentials (IPCA vs US CPI) → real-rate decomposition for the
  long-end forward.
- BCB intervention regime indicator → conditioning variable for jump intensity
  in a Bates/Kou-style model.
- COPOM and Focus release calendar → event flags for quote-policy widening.
Provide cadences (daily for curves, monthly for IPCA, weekly for Focus,
event-driven for COPOM).

Sources to prioritize
- bcb.gov.br (Inflation Reports, COPOM minutes in English, BCB Working Papers).
- tesourotransparente.gov.br and tesouro.fazenda.gov.br for fiscal data.
- ibge.gov.br for real-economy data.
- fazenda.gov.br for fiscal framework documents.
- IMF Article IV consultation on Brazil (most recent).
- BCB Working Paper series — search bcb.gov.br for English PDFs.
- Anbima.com.br for curve construction methodology.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Cite obsolete fiscal framework details (the spending cap is gone — verify
  what is currently in force).
- Treat BCB independence as absolute; flag the political-pressure dimension
  even though it does not change the formal law.
- Skip the Adverse-selection implications and Theo-input contribution
  subsections — they are mandatory from this phase forward.
```

---

## Phase 6 — External and Global Drivers of BRL

```
You are executing Phase 6 of 16. Prior phases required: Phases 1–5. Confirm all
five .md files in ./research/ before beginning; halt if any are missing.

Goal
Catalog the global / cross-asset drivers of USD/BRL with empirically documented
betas where available. The downstream theo will use cross-asset conditioning
(DXY level, EM risk index, commodity terms-of-trade, US-Brazil rate
differential) to refine the drift estimate and to flag regime shifts.

Method
Web research; primary sources where possible (FRED for US data, BIS for global
flows, EPFR for portfolio flows where freely accessible, CFTC for IMM
positioning, S&P GSCI documentation for commodity indices).

Deliverable
Save to ./research/phase_06_brl_external_drivers.md. Target 4,500–6,500 words,
≥25 distinct sources cited. Include at least one regression-evidence table
summarizing documented betas across multiple papers.

Required sections in the output
1. DXY and EUR/USD as the dominant external driver. Document the empirical
   beta of USD/BRL to DXY across sub-periods (calm vs crisis). Cite at least
   three papers or BIS notes.
2. US rates and the Fed: Fed funds futures, SOFR curve, Treasury yields. The
   widening/narrowing of the US-Brazil rate differential as a carry signal.
   Cite Lustig–Roussanov–Verdelhan (2011) "Common Risk Factors in Currency
   Markets," RFS.
3. Risk-on / risk-off regime: VIX, MOVE, EM equity (MSCI EM), EMBI+ Brazil
   spread, Brazil sovereign CDS. Document the typical BRL reaction in
   risk-off events (sharp depreciation; vol spike).
4. Terms of trade — BRL as a commodity currency: iron ore (single largest
   Brazilian export), soybean and soybean meal, crude oil (Petrobras),
   sugar/coffee. Cite Cashin, Céspedes, Sahay (IMF Working Paper) on commodity
   currencies; Chen & Rogoff "Commodity Currencies" (JIE 2003); Ferraro,
   Rogoff & Rossi "Can Oil Prices Forecast Exchange Rates?"
5. Other LATAM FX correlation regime: USD/MXN, USD/COP, USD/CLP, USD/PEN. The
   BRL-MXN correlation and when it breaks (Mexico-specific or Brazil-specific
   shocks). Document with rolling-correlation evidence.
6. China demand: Caixin and NBS PMIs, iron ore imports, industrial production.
   The transmission mechanism through commodity prices.
7. Portfolio flows: EPFR weekly aggregates, CFTC IMM positioning on BRL (note
   that BRL is a relatively small CFTC contract — caveat the noise), B3
   non-resident equity and futures flows (B3 publishes daily).
8. Cross-asset BRL betas table: rows are regimes (calm 2017–2019, COVID 2020,
   tightening cycle 2021–2023, election cycle 2026 — with appropriate caveats
   about beta instability), columns are BRL beta to (DXY, US 10Y, VIX, iron
   ore, EMBI Brazil). Cite each cell or flag as estimated.

Adverse-selection implications
Most external data releases are public-information events with tight latency
(Bloomberg / Reuters timestamping). Adverse selection arises chiefly from:
(a) participants with private cross-asset positioning information — large
macro funds rebalancing across pairs; (b) exotics dealers' Greek-driven
hedging flow that leaks intent to interbank; (c) fund-level redemption flow
that is private to a fund admin.

Theo-input contribution
- DXY level → multiplicative drift adjustment.
- US-Brazil 1Y rate differential → forward-rate input.
- VIX or MOVE → regime indicator that switches between low-vol and high-vol
  regimes in the SLV-with-jumps model.
- Iron ore + soybean → conditioning for the structural drift.
Cadence: spot daily for most; intraday for DXY and US rates.

Sources to prioritize
- Lustig, Roussanov, Verdelhan (2011), RFS.
- Chen & Rogoff (2003), JIE.
- BIS Quarterly Review issues on EM FX (multiple).
- IMF Selected Issues papers on Brazil.
- CFTC Commitments of Traders historical archive.
- EPFR Global commentary (publicly excerpted via BBG / Reuters).

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Treat documented betas as time-invariant. Cross-asset betas in EM FX are
  among the most regime-dependent in finance.
- Confuse one-day reaction empirics with longer-horizon predictability.
```

---

## Phase 7 — Brazilian Political and Fiscal Calendar (2026 Election Dynamics)

```
You are executing Phase 7 of 16. Prior phases required: Phases 1–6. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Build a calendar of political and fiscal-event drivers that fall within the
contract life (now through end-2026). The Brazilian general election is the
single largest political-uncertainty driver in scope. Use academic and
practitioner literature on currency dynamics around EM elections to inform
expected USD/BRL behavior windows.

Method
Web research. Primary sources: TSE (Tribunal Superior Eleitoral) for the
electoral calendar, Câmara dos Deputados and Senado Federal for the
congressional calendar, STF for major decisions calendar, polling firm
publications (Datafolha, Quaest, Genial/Quaest, Atlas Intel, Ipec), academic
papers on election uncertainty and currency dynamics.

Deliverable
Save to ./research/phase_07_brazil_political_calendar.md. Target 4,000–5,500
words, ≥25 distinct sources cited.

Required sections in the output
1. The 2026 Brazilian electoral calendar in detail: TSE-published dates for
   first round (October 4, 2026), runoff (October 25, 2026 if applicable),
   the campaign period start, the official poll publication blackout period,
   the winner-takes-office date (January 1, 2027 for federal executive — but
   contract resolves December 31, 2026 — the inauguration is OUT of the
   contract window). Include congressional and gubernatorial elections (held
   the same day).
2. Historical USD/BRL behavior around Brazilian elections — case studies:
   - 2002 Lula election: the canonical case of pre-election currency
     depreciation, "Lula crisis," the Lula letter (Carta ao Povo Brasileiro),
     IMF program. Document USDBRL trajectory from June 2002 to December 2002.
   - 2014 Dilma re-election: documented USD/BRL reaction to polls.
   - 2018 Bolsonaro election: documented reaction to polls.
   - 2022 Lula return: documented reaction to polls and to the transition
     period fiscal noise.
3. Polling-vs-FX correlations from the literature: cite at least three papers
   that quantify EM polling moves to FX moves (e.g., Frieden, Stein on EM
   politics; Pástor & Veronesi "Political Uncertainty and Risk Premia" JFE
   2013; Kelly, Pástor & Veronesi "The Price of Political Uncertainty" JoF
   2016; Bechtel & Liesch on emerging markets).
4. Brazilian polling landscape: Datafolha (Folha-owned, gold standard
   historically), Quaest (newer, Genial-funded), Atlas Intel (data-driven,
   often cited), Ipec (formerly Ibope), Paraná Pesquisas. Publication
   cadences and methodology differences. Note that polling firms have
   institutional reputational stakes — a market maker should weight polls
   methodologically, not naively.
5. Fiscal-political flashpoints in 2026: budget vote timing (LDO and LOA),
   congressional recess calendars (the Brazilian Congress recesses
   January–February and July), STF decision calendar for fiscal-affecting
   decisions, mid-year budget revisions (PLOA / PLN). Document any pending
   STF or congressional fiscal cases as of the latest available
   information.
6. Institutional independence stress points: the BCB independence law
   (LC 179/2021), the appointment cycle for BCB directors and the
   incumbent president (verify the current president's term — Galípolo
   appointed January 2025), congressional confirmations as windows of
   FX vol.
7. Academic literature on currency dynamics around EM elections:
   - Pástor & Veronesi "Political Uncertainty and Risk Premia" (JFE 2013).
   - Kelly, Pástor & Veronesi "The Price of Political Uncertainty" (JoF 2016).
   - Frieden on currency politics.
   - Bechtel & Liesch on EM.
   - Brazilian-specific: Garcia, Goldfajn, Werlang historical IMF/BCB
     papers on FX during election years.

Adverse-selection implications
Election cycles create the most acute informed-trader windows. Specifically:
- Polls released in scheduled time windows (typically Mondays/Thursdays
  evenings BRT for the major firms) — significant participants subscribe to
  poll-data services that publish minutes earlier than free public release.
- "Cross-tabs" and internal polling commissioned by parties leak through
  political-consultancy channels.
- Major debate dates (TV debate calendar) produce vol spikes from prepared
  positioning.
- STF decisions are sometimes signaled hours in advance through journalistic
  channels.
Produce a daily/weekly checklist of presumptively dangerous days for an
uninformed market maker.

Theo-input contribution
- Election-week proximity → conditioning indicator for elevated jump
  intensity in the SLV+jumps model.
- Poll-aggregator level (e.g., Atlas Intel rolling average of Lula vs
  challenger) → drift conditioning. Cite published research on poll-FX
  elasticities for magnitude.
- Fiscal-noise indicator (count of fiscal-affecting STF rulings or
  congressional votes scheduled in next N days) → vol surface upward shift.
Cadence: weekly during normal periods, daily entering October.

Sources to prioritize
- TSE.jus.br for electoral calendar.
- Datafolha, Quaest, Atlas Intel publication archives.
- Pástor & Veronesi (2013, 2016).
- Garcia, Goldfajn historical Brazilian crisis papers.
- IMF and World Bank country reports on Brazil 2025–2026.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Predict election outcomes. The brief is about volatility and informed-flow
  windows, not directional forecasts.
- Confuse first-round and runoff dates.
- Skip the Adverse-selection and Theo-input subsections.
```

---

## Phase 8 — USD/BRL Implied Volatility Surface

```
You are executing Phase 8 of 16. Prior phases required: Phases 1–7. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Deep technical reference on the USD/BRL implied volatility surface — where it
trades, how it is quoted, how it is constructed, its dominant patterns, and
how to extract the corner of the surface that matters most for a long-dated
upside one-touch barrier (the upside wing at 6–7-month tenor).

Method
Web research. Primary sources: BIS Triennial Survey on FX options turnover,
CME BRL options data and specs, B3 DOL options specs, OTC vol-quote
conventions documents (Wystup, Castagna), academic papers on FX options
(Carr–Wu, Bakshi–Carr–Wu, Della Corte–Sarno–Tsiakas).

Deliverable
Save to ./research/phase_08_usdbrl_iv_surface.md. Target 5,000–7,000 words,
≥30 distinct sources cited. Equations required.

Required sections in the output
1. Where USD/BRL options trade:
   - CME listed BRL options on 6L futures: contract spec, tick, expiry cycle,
     liquidity profile by tenor. Document that liquidity beyond ~3 months is
     thin on CME.
   - OTC NDF options market: dominant for tenors > 3 months. Cite BIS
     Triennial for global market share.
   - B3 listed options on DOL future: domestic Brazilian retail and
     institutional flow.
2. OTC FX option quoting conventions: the quote is in implied vol, not price.
   Strikes are quoted as ATM, 25-delta and 10-delta risk reversals (RR) and
   butterflies (BF). The ATM convention is typically delta-neutral straddle
   (DNS) for short tenors and forward-ATM for longer. Premium-included delta
   is the EM-FX standard. Cite Castagna "FX Options and Smile Risk" (Wiley
   2010) and Wystup "FX Options and Structured Products" (Wiley 2006).
3. Standard tenor structure: 1W, 1M, 3M, 6M, 1Y, 2Y. Document USD/BRL
   typical liquidity at each tenor.
4. Risk reversals and butterflies as smile descriptors:
   - 25Δ RR = vol(25Δ call) − vol(25Δ put). Positive RR means calls (USD
     calls = BRL puts) are bid relative to puts (USD puts = BRL calls).
   - 25Δ BF = (vol(25Δ call) + vol(25Δ put))/2 − ATM vol.
   - Map RR/BF/ATM into a five-strike surface (ATM, 25Δ call, 25Δ put,
     10Δ call, 10Δ put).
5. Vanna–Volga method for surface construction: the EM-FX practitioner
   standard for completing a surface from three quoted strikes. Cite
   Castagna & Mercurio "The Vanna–Volga Method for Implied Volatilities."
   Walk through the formula:
   $$V^{VV}(K) = V^{BS}(K) + \sum_{i=1}^{3} x_i(K) \left[V^{mkt}(K_i) - V^{BS}(K_i)\right]$$
   with the weights $x_i$ derived from vega/vanna/volga matching.
6. SABR and SVI fits: SABR (Hagan et al. 2002) for smile parameterization,
   SVI (Gatheral 2004) for total-variance parameterization. Discuss when each
   is preferred. Note that SVI's no-arbitrage conditions (Gatheral & Jacquier
   2014) matter for downstream barrier pricing.
7. Term-structure dynamics: how the ATM term structure typically slopes
   (upward in calm, inverted near events), and how USD/BRL term-structure
   reacts to COPOM and FOMC.
8. Dominant patterns of USD/BRL skew: consistently positive 25Δ RR (USD calls
   bid) reflecting BRL crash risk. Document the historical range (e.g.,
   2.5–6.5 vol points) and the regimes where it widens. Cite Carr–Wu (2007)
   "Stochastic Skew in Currency Options" RFS.
9. Surface dynamics around shocks: a stylized walk-through of how the surface
   moves around (a) BCB intervention surprise, (b) COPOM surprise, (c) US
   data surprise, (d) Brazilian political shock. Reference the academic
   literature on jump-vol response (Bakshi–Carr–Wu 2008 RFS).
10. Mapping surface to a 7-month upside one-touch:
    - The relevant strike is the barrier-equivalent log moneyness; for a
      barrier 4.9999 with spot at, say, 5.20, the relevant moneyness is the
      out-of-the-money put wing for spot expressed in BRL/USD, or
      equivalently the in-the-money / out-of-the-money depending on
      orientation. Be careful with the quote convention.
    - The upside wing's 25Δ and 10Δ vol points dominate the touch
      probability — show the sensitivity numerically with a stylized
      Vanna–Volga example.
    - Discuss why thin-liquidity 6M–7M tenor on CME forces reliance on OTC
      indications, and the practical workaround of using nearest-tenor
      listed quotes plus a term-structure interpolation.

Adverse-selection implications
Vol-surface moves frequently lead spot moves — a pattern documented in the
academic literature (e.g., Ni, Pearson, Poteshman, "Stock Price Clustering
on Option Expiration Dates," and the broader options-leading-spot
literature). For USD/BRL specifically: jumps in the 25Δ RR often precede
spot dislocations by minutes to hours. A market maker on a barrier product
who reads only spot will be informationally behind a market maker who reads
the OTC vol surface. Document specific informed-trader windows where vol
surface moves are presumptively informed.

Theo-input contribution
- Full vol surface (5×6 grid: 5 strikes × 6 tenors) → SLV calibration target.
- 25Δ and 10Δ upside-wing vol → primary driver of theo touch probability
  for the 4.9999 barrier.
- ATM term structure → drift-volatility interaction in the SLV calibration.
Cadence: surface refresh hourly during liquid hours; intraday refresh of
ATM and 25Δ RR every 15 minutes during NY session.

Sources to prioritize
- Castagna (2010), "FX Options and Smile Risk."
- Wystup (2006), "FX Options and Structured Products."
- Hagan, Kumar, Lesniewski, Woodward (2002), Wilmott Magazine.
- Gatheral (2004), "A Parsimonious Arbitrage-Free Implied Volatility
  Parameterization with Application to the Valuation of Volatility
  Derivatives."
- Gatheral & Jacquier (2014), Quantitative Finance, on no-arbitrage SVI.
- Carr & Wu (2007), RFS, "Stochastic Skew in Currency Options."
- Bakshi, Carr, Wu (2008), RFS.
- Della Corte, Sarno, Tsiakas (multiple JoF/RFS papers).
- BIS Triennial Survey on FX options turnover.
- CME BRL options product page and historical data.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Substitute equity-options conventions for FX-options conventions. The
  delta-quoting is fundamentally different.
- Skip the upside-wing sensitivity discussion — it is the most important
  practical message of the phase.
- Skip the Adverse-selection or Theo-input subsections.
```

---

## Phase 9 — Discretionary EM FX Strategies

```
You are executing Phase 9 of 16. Prior phases required: Phases 1–8. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Catalog the repertoire of discretionary EM FX trading strategies, with USD/BRL
emphasis. The downstream theo and quote policy will not implement these
directly, but will use them to anticipate informed flow and to widen quotes
around the events that discretionary funds trade.

Method
Web research; named practitioner sources (books, dealer research notes,
interviews where on the record), BIS / IMF working papers on EM FX dealer
behavior, academic papers on FX intervention effectiveness.

Deliverable
Save to ./research/phase_09_discretionary_em_fx.md. Target 4,000–6,000 words,
≥25 distinct sources cited.

Required sections in the output
1. Intervention trading: front-running BCB auctions, fading post-auction
   moves. Cite the BCB intervention literature (Chamon, Garcia, Souza;
   Kohlscheen; Goldfajn). Document the auction announcement timing on the
   BCB website.
2. Positioning-based trading: CFTC IMM data on BRL (released Friday for
   Tuesday positions), B3 non-resident positioning (released daily by B3),
   the contrarian vs trend-following positioning trades.
3. Event trading: COPOM, FOMC, US CPI, Brazilian IPCA, election poll
   releases. The decision framework — pre-event positioning vs post-event
   chase. Cite Mueller, Tahbaz-Salehi, Vedolin (RFS 2017) "Exchange Rates
   and Monetary Policy Uncertainty."
4. Carry-vs-vol regime trading: when carry attracts inflows vs when vol
   shock unwinds them. The regime indicators (G10 vs EM vol, EM equity).
5. Real-money flow anticipation: month-end fixing flows (the
   "London 4pm fix" for BRL is muted but exists; the Brazilian PTAX D-1
   fixing for D-2 settlement creates predictable flows), dividend
   remittance season for foreign-owned Brazilian corporates (Vale,
   Ambev, etc. — mostly Q1 and Q2), IPO flow.
6. Narrative trading: fiscal-credibility cycles, China narrative, Fed
   narrative. Decision frameworks for when to fade and when to ride a
   narrative.
7. Practitioner sources: Mohamed El-Erian "When Markets Collide" (PIMCO
   perspective on EM); Stanley Druckenmiller interviews on EM trades;
   Ray Dalio / Bridgewater public-facing research; Goldman Sachs FX
   Watch (when publicly excerpted); Citi EM FX Strategy notes (when
   publicly excerpted); the BIS Working Paper series on EM FX
   intervention; IMF Working Papers on EM FX.

Adverse-selection implications
Discretionary funds are themselves the informed-trader population in many
of these patterns. Specifically:
- Pre-COPOM positioning by macro funds with strong rate-call conviction.
- Pre-poll positioning by funds with private polling subscriptions.
- Real-money flow that the bank dealing the corporate hedge knows hours
  in advance.
- BCB auction front-running by participating banks who see auction
  announcements in their dealer feeds before public release.
Produce an updated "informed-trader windows" checklist building on Phase 7.

Theo-input contribution
- Carry indicator (US-Brazil 1Y rate diff) → drift component (already
  flagged Phase 5 — confirm cadence).
- Positioning indicator (CFTC IMM net) → conditioning on jump intensity
  for stretched positioning (large net long BRL = more downside jump
  risk).
- Real-money flow calendar → quote-policy event flag (do not feed the
  theo directly; feed the quote policy).
Cadence: weekly for CFTC IMM, daily for B3 non-resident, event-driven
for the rest.

Sources to prioritize
- Chamon, Garcia, Souza (BCB / IMF) on FX intervention.
- BIS Working Papers on EM FX (Kohlscheen, Murcia, Contreras, others).
- Mueller, Tahbaz-Salehi, Vedolin (RFS 2017).
- El-Erian, "When Markets Collide" (McGraw-Hill 2008).
- Burnside, Eichenbaum, Rebelo on carry trade (multiple JFE/RFS papers).
- Goldman Sachs FX Watch publicly excerpted notes (cite carefully).

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Treat anecdotal practitioner trades as rigorous evidence — frame them
  as the source identifies them.
- Skip the Adverse-selection or Theo-input subsections.
```

---

## Phase 10 — Systematic FX Strategies

```
You are executing Phase 10 of 16. Prior phases required: Phases 1–9. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Survey systematic FX strategies — carry, momentum, value, vol carry,
factor models — with EM FX and USD/BRL applicability flagged. The downstream
quote policy will incorporate systematic-flow indicators where they
demonstrably improve theo or reduce adverse selection.

Method
Web research focused on the academic primary literature. SSRN, NBER, journal
pages.

Deliverable
Save to ./research/phase_10_systematic_fx.md. Target 5,000–7,000 words, ≥35
distinct sources cited. Equations required where signal definitions are
mathematical.

Required sections in the output
1. FX carry trade:
   - Lustig & Verdelhan (2007), AER, "The Cross Section of Foreign Currency
     Risk Premia and Consumption Growth Risk."
   - Lustig, Roussanov, Verdelhan (2011), RFS, "Common Risk Factors in
     Currency Markets" — the HML_FX factor.
   - Burnside, Eichenbaum, Rebelo (multiple), "Carry Trade and Momentum
     in Currency Markets."
   - The DBV index and Deutsche Bank G10 carry index.
   - Brazilian-specific: BRL has historically been a top-quartile carry
     currency. Document the time-series of BRL carry rank.
2. FX momentum: Menkhoff, Sarno, Schmeling, Schrimpf (2012), JFE, "Currency
   Momentum Strategies." Signal: 1M / 3M / 6M / 12M trailing returns.
3. FX value: Asness, Moskowitz, Pedersen (2013), JoF, "Value and Momentum
   Everywhere." FX value typically uses real-exchange-rate deviation from
   PPP.
4. Vol carry / vol selling: Della Corte, Ramadorai, Sarno (2016), RFS,
   "Volatility Risk Premia and Exchange Rate Predictability." The
   short-vol trade in EM FX is uniquely dangerous because EM vol blows
   out asymmetrically.
5. Term-structure / forward-bias-adjusted carry: refinements to vanilla
   carry that account for the slope of the forward curve.
6. Risk-reversal-based skew strategies: trading the 25Δ RR as a
   directional signal. Cite Brunnermeier, Nagel, Pedersen (2008), "Carry
   Trades and Currency Crashes," NBER Macroeconomics Annual.
7. Dollar-factor models: Verdelhan (2018), JoF, "The Share of Systematic
   Variation in Bilateral Exchange Rates"; Lustig–Roussanov–Verdelhan
   dollar factor.
8. Intermediary-based factor models for FX: He, Kelly, Manela (2017), JFE,
   "Intermediary Asset Pricing: New Evidence from Many Asset Classes."
9. EM-FX-specific systematic work: BIS Working Papers, IMF WP, BCB WP
   series. Identify any papers with USD/BRL-specific systematic-strategy
   evidence.
10. ML approaches: NLP on COPOM minutes (Brazilian central-bank text is
    dense and idiosyncratic — cite any published applications),
    gradient-boosted models on macro inputs, the limitations of ML on FX
    where regime breaks dominate.
11. Capacity, decay, and applicability to single-pair USD/BRL view: many
    systematic FX strategies are portfolio strategies (cross-sectional
    sort of currencies). For a single-pair theo, the relevant outputs are
    (a) signal levels for BRL relative to its history, (b) crowding
    indicators (CFTC IMM, EPFR).

Adverse-selection implications
Systematic flows are themselves a major source of informed (or
informed-looking) flow. Specifically: month-end rebalancing of systematic
funds; quarter-end carry index reconstitutions (DBV, etc.); momentum
unwinds at trend reversals. All produce predictable flow that a market
maker should anticipate.

Theo-input contribution
- BRL carry-rank percentile vs G10 EM peers → conditioning indicator for
  jump risk (high carry = crowded long BRL = downside jump risk).
- 1M/3M/12M momentum signal → optional drift adjustment, but flag as
  weak for a 7-month barrier.
- Vol risk premium (1M ATM IV − 1M realized vol) → conditioning for the
  vol-of-vol component in SLV.
Cadence: daily for signals, monthly for portfolio recalibration.

Sources to prioritize
- Lustig & Verdelhan (2007), AER.
- Lustig, Roussanov, Verdelhan (2011), RFS.
- Menkhoff, Sarno, Schmeling, Schrimpf (2012), JFE.
- Asness, Moskowitz, Pedersen (2013), JoF.
- Della Corte, Ramadorai, Sarno (2016), RFS.
- Brunnermeier, Nagel, Pedersen (2008), NBER Macro Annual.
- Verdelhan (2018), JoF.
- He, Kelly, Manela (2017), JFE.
- BCB Working Paper series for Brazil-specific work.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Apply portfolio-level cross-sectional FX strategies as if they were
  single-pair signals.
- Skip the Adverse-selection or Theo-input subsections.
```

---

## Phase 11 — Adverse Selection in Two-Sided Markets (Theory and FX-Specific Patterns)

```
You are executing Phase 11 of 16. Prior phases required: Phases 1–10. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Standalone deep dive on adverse selection in two-sided markets: the theory,
the empirical FX-specific patterns, and the practitioner toolkit for detecting
and minimizing adverse selection. This is the centerpiece for the quote-policy
design in Phase 14.

Method
Web research; primary academic sources for theory; BIS / dealer research for
FX-specific empirics.

Deliverable
Save to ./research/phase_11_adverse_selection.md. Target 5,500–7,500 words,
≥35 distinct sources cited. Equations required throughout.

Required sections in the output
1. Theoretical foundations:
   - Glosten & Milgrom (1985), JFE, sequential trade model. Derive the
     bid-ask spread:
     $$\text{ask} = \mathbb{E}[V \mid \text{buy}], \quad
       \text{bid} = \mathbb{E}[V \mid \text{sell}]$$
     and the implication that spreads widen with the probability of
     informed trading.
   - Kyle (1985), Econometrica. Lambda, the price impact:
     $$\Delta p = \lambda \cdot q$$
     and the sequential auctions extension (Kyle 1989).
   - Easley & O'Hara (1987, 1992) PIN. The PIN estimation procedure via
     trade classification.
   - Easley, López de Prado, O'Hara (2012, 2014) VPIN — the
     volume-clock-based real-time PIN proxy.
   - Cont, Kukanov & Stoikov (2014), Quantitative Finance, "The Price
     Impact of Order Book Events."
2. Quote fade and last-look in FX:
   - The post-trade markout literature: Almgren et al. (multiple) on
     equities; the FX-specific work on last-look (BIS FX Global Code on
     last-look transparency).
   - Empirical FX dealer quote-fade evidence: cite at least three
     empirical papers.
3. FX-specific informed-trader populations:
   - Corporate hedgers with private cash-flow info — they know their own
     hedge calendar.
   - Central-bank counterparties in the dealer chain — the BCB auction
     dealer sees the auction before public.
   - Momentum funds during trends.
   - Macro hedge funds before US data releases.
   - Internal flow: bank-internal client flow that the dealer
     internalizes vs externalizes.
4. The WMR 4pm London fix: the information-laden window literature. Cite
   Evans (2018) on fix windows; Melvin & Prins on fix; the FX fix
   investigations (FCA, CFTC settlements with major banks 2014–2015).
   For BRL specifically: WMR 4pm London window has muted but real
   activity; the PTAX D-1 / D-2 BRT window is the BRL-specific
   information-laden window.
5. Asian / London / NY session handover: each session handover is a
   liquidity transition window where stale quotes from the closing
   region are picked off by participants in the opening region.
6. EM-FX-specific information leakage:
   - Offshore NDF vs onshore spot: the basis between them carries flow
     information; participants with access to both venues are
     informationally advantaged.
   - BCB intervention dealers: privileged access to BCB intent.
   - Local Brazilian banks: privileged access to corporate hedge calendar.
7. Real-time detection mechanics:
   - PIN estimation in moving windows (challenges: noisy on intraday
     timescales).
   - VPIN: more robust to intraday application; Easley–López de
     Prado–O'Hara recipe.
   - Order-flow imbalance (OFI) as a fast adverse-selection proxy.
   - Post-trade markouts (1m, 5m, 30m, 1h, 1d) as a calibration
     diagnostic. Show how to convert markouts into a quote-widening
     decision.
8. Practitioner techniques to minimize adverse selection:
   - Quote sizing tiers: small clients get tight, large macro funds get
     wide (this is the FX dealer norm — cite BIS).
   - Quote fade after large hits: "last-look" in FX; widen-on-trade in
     order-book products.
   - Pull on news: kill quotes 30 seconds before scheduled releases (US
     CPI, COPOM, BCB intervention announcements).
   - Widen during fixings.
   - Asymmetric quote widths when inventory-skewed — already long?
     Tighten the offer, widen the bid.
9. Mandatory checklist: produce a comprehensive list of "informed-trader
   windows for USD/BRL" with timestamps in BRT and CT. Include scheduled
   recurring events (COPOM, FOMC, US CPI, IPCA, IPCA-15, Focus, BCB
   intervention windows, PTAX windows, WMR fix, B3 closing auction,
   Brazilian poll release windows during election season). Each row:
   event, time BRT, time CT, presumptively informed populations, suggested
   quote-policy reaction.

Theo-input contribution
- Real-time markout statistics → quote-policy parameter (spread widening
  multiplier when recent markout > X bp).
- VPIN level → indicator for elevated informed trading.
- Event-window indicator (binary or seconds-to-event) → quote-policy
  pull/widen trigger.
Cadence: real-time for all.

Sources to prioritize
- Glosten & Milgrom (1985), JFE.
- Kyle (1985), Econometrica.
- Easley, Kiefer, O'Hara, Paperman; Easley & O'Hara (multiple).
- Easley, López de Prado, O'Hara (2012 RFS, 2014 JFE).
- Cont, Kukanov, Stoikov (2014), Quantitative Finance.
- BIS FX Global Code documentation (latest revision).
- Evans (2018) and the WMR fix literature.
- FCA and CFTC settlements 2014–2015 for FX fix scandal facts.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues.
- Confuse adverse selection with inventory cost. They are distinct
  components of the bid-ask spread.
- Skip the mandatory informed-trader-windows checklist — this is the
  Phase 14 input.
```

---

## Phase 12 — Data Streams for USD/BRL Theo Construction

```
You are executing Phase 12 of 16. Prior phases required: Phases 1–11. Confirm
all .md files exist in ./research/ before beginning; halt if any are missing.

Goal
Catalog every data stream relevant to constructing a high-quality theo for a
long-dated USD/BRL touch barrier. This is a feed-by-feed inventory: spot,
options, forwards, BCB / macro, political, news, weather, satellite.

Method
Web research; vendor sites; central bank API documentation; academic notes
on data sources used in FX research.

Deliverable
Save to ./research/phase_12_data_streams_for_theo.md. Target 4,500–6,500
words, ≥30 distinct sources cited. Tabular format strongly encouraged.

Required sections in the output
1. Spot and intraday FX:
   - Interbank spot: EBS, Reuters Matching (institutional only).
   - CME 6L front-month future as a public proxy.
   - B3 DOL futures as the deepest BRL futures market.
   - Free / cheap proxies: Polygon.io, Twelve Data, TradingView, Yahoo
     Finance USDBRL=X.
2. Options data:
   - CME BRL options chain (free with delay; paid for real-time).
   - B3 DOL options chain.
   - OTC NDF options indications: where to source (Bloomberg / Reuters
     terminals required for live quotes; SuperDerivatives for historical).
3. Forwards / NDFs:
   - NDF curve from any accessible source (Bloomberg, Reuters; or
     constructed from cupom cambial).
   - Cupom cambial from B3.
4. BCB data:
   - SGS API (https://api.bcb.gov.br/dados/serie/...) — interest rates,
     FX, BoP, all free, well-documented.
   - Olinda API (newer; more granular data).
   - Intervention auction announcements (real-time on bcb.gov.br during
     business hours).
   - Reserves data (monthly note).
   - Focus expectations report (weekly Monday morning, free download).
5. Macro releases:
   - IBGE for IPCA, IPCA-15, GDP, industrial production (PIM-PF), retail
     sales (PMC), employment (PNAD).
   - Caged for monthly admin employment.
   - Tesouro Nacional for fiscal data.
6. External / global:
   - FRED (St. Louis Fed) for US data — Treasury yields, Fed funds
     futures-implied rates, US CPI, ISM, etc.
   - BIS for global aggregates (FX turnover, debt securities,
     consolidated banking statistics).
   - CFTC Commitments of Traders for IMM positioning.
   - EPFR Global for portfolio flows (paid; institutional pricing).
7. Political:
   - Poll aggregators (Atlas Intel, Quaest, Datafolha publication
     calendars).
   - Brazilian congressional calendars (Câmara dos Deputados, Senado).
   - STF decision calendar.
   - TSE for electoral logistics.
8. News and unstructured:
   - Bloomberg, Reuters (institutional).
   - Valor, Folha, Estadão (Brazilian).
   - Twitter/X for poll release timing.
9. Commodity prices for terms-of-trade conditioning:
   - LME for iron ore (or Platts via S&P Global).
   - CBOT for soybean (ZS futures front month).
   - WTI for oil (CL futures front month).
   - Sugar #11 (SB), coffee C (KC) on ICE.
10. Each entry: publisher, access method, frequency, latency, cost tier,
    role in theo (level / vol / drift / regime / event flag), and
    adverse-selection implications (does this release create an
    informed-trader window).

Adverse-selection implications
Cross-reference each data source against the Phase 11 informed-trader
windows checklist. Specifically flag: low-latency feeds where retail-tier
data is materially behind institutional (a 30-second delay on CME free
data vs real-time iLink is exploitable in fast-moving markets). For
political data: poll subscription services (e.g., Atlas Intel
subscriber feed) publish minutes earlier than free public release —
this is a real adverse-selection vector.

Theo-input contribution
Master table mapping every theo input from Phases 5–11 to a specific data
source from this phase. Columns: theo input, source, latency, refresh
cadence, cost tier, fallback source.

Sources to prioritize
- bcb.gov.br/api documentation pages (SGS and Olinda).
- ibge.gov.br data publication calendars.
- cme.com market data product pages.
- b3.com.br data products.
- fred.stlouisfed.org.
- bis.org statistics.
- cftc.gov COT historical archive.

Do NOT
- Mention Kalshi, prediction markets, or any binary/touch contracts on
  prediction venues. Phase 13 is the first Kalshi mention.
- Recommend a feed without a verifiable cost tier.
- Skip the Adverse-selection or Theo-input subsections.
```

---

## Phase 13 — KXUSDBRLMAX Contract Structural Analysis (First Kalshi Mention)

```
You are executing Phase 13 of 16. This is the FIRST phase that introduces
Kalshi. Prior phases required: Phases 1–12 (the entire foundational stack).
Read all twelve prior .md files in ./research/ before beginning; halt and
report if any are missing.

Goal
Dissect the KXUSDBRLMAX series and the specific contract
(https://kalshi.com/markets/kxusdbrlmax/usdbrl-max/kxusdbrlmax-26dec31). The
output must answer every structural question that determines the theo and
the quote policy: what reference rate triggers the touch, monitoring
discreteness, exact barrier and resolution mechanics, settlement and
resolution timing, fee math, position limits, API access, and whether any
liquidity-incentive program is active on this series.

Method
Use web_fetch on the contract page, the series page, the Kalshi rulebook,
the Kalshi fee schedule, and Kalshi's API documentation. Search the CFTC's
DCM filings database for KXUSDBRLMAX self-certification documents (at
sirt.cftc.gov or cftc.gov). Search the Kalshi blog and Kalshi's market
maker documentation pages. Use web_search liberally.

Deliverable
Save to ./research/phase_13_kxusdbrlmax_contract.md. Target 3,500–5,000
words, ≥15 distinct primary sources cited (the Kalshi rulebook, contract
spec, the CFTC filing, the API docs, fee schedule, plus any Kalshi
incentive program documentation count as separate sources).

Required sections in the output
1. Contract identification: full series ticker (KXUSDBRLMAX), the specific
   contract identifier for the December 31, 2026 expiry, market title and
   description as posted, link.
2. Reference rate for the touch — answer precisely:
   - What venue's price triggers the touch? Spot interbank? PTAX? CME 6L
     front-month? B3 DOL? An aggregator like Bloomberg BFIX?
   - Quote precision: how many decimal places? Does 4.9999 vs 5.0000
     matter at the tick level on the reference venue?
   - Reference rate publication times.
3. Monitoring discreteness — answer precisely:
   - Continuous (any tick on the reference venue counts) or discrete
     (only specific timestamps — daily fix, hourly snapshot)?
   - If discrete, exact timestamps in UTC and BRT and CT.
   - This determines whether the Broadie–Glasserman–Kou σ√Δt correction
     applies, and how large.
4. Exact barrier level and resolution mechanics for ambiguous prints:
   - Barrier value: 4.9999.
   - "Above" vs "at or above" — strict inequality or weak?
   - Tie-handling for prints exactly at 4.9999.
   - Resolution authority and dispute mechanism.
5. Settlement and resolution timing:
   - When does the contract resolve once the touch occurs?
   - When does it resolve as NO if no touch occurs by December 31, 2026?
   - Payout amount per contract.
6. Strike / series structure:
   - Is KXUSDBRLMAX a single barrier or a family of strikes?
   - If a family: list the active strikes and their quoting density.
   - Are there parallel KXUSDBRLMIN (downside touch) or KXUSDBRLAT (no
     touch) markets?
7. Order types, tick size, fee math:
   - Available order types (limit, IOC, FOK, post-only).
   - Tick size in cents.
   - Maker / taker fee schedule with worked example: a 100-contract
     limit order filled at 23 cents — what is the fee in cents per
     contract and in dollars total? Cite the fee page. Include any
     special FX-series fee tier if one exists.
   - Position limits per account; per-side limits if any.
8. Liquidity incentive program — answer precisely:
   - Does Kalshi run an MM program for KXUSDBRLMAX, or for the broader
     FX series, or for binary touch contracts? Search Kalshi's
     incentive page (kalshi.com/incentives or kalshi.com/market-makers).
   - Spread / depth / uptime requirements, if any.
   - Rebate or rewards structure — per-contract, per-share-of-volume,
     or scaled by quote tightness?
   - Eligibility: open enrollment or by application?
   - Is the program filed publicly with the CFTC, or only published on
     Kalshi's site?
   - Historical changes to the program (search for prior versions).
9. API access:
   - REST endpoints relevant to placing orders, cancelling, and reading
     positions for this series.
   - WebSocket for real-time orderbook and trade data.
   - Historical data availability (how far back, what fields).
   - Sandbox / testnet availability and parity with prod.
   - Rate limits (requests/sec, weight system if any).
   - Authentication mechanism (API key, RSA signing, OAuth?).
10. Liquidity snapshot: at the time of writing this phase, capture a
    snapshot of the orderbook on the contract page — best bid, best
    ask, depth at top of book, recent trades. This is a one-time
    snapshot, not a longitudinal study.
11. Formal payoff function — the mandatory deliverable. State precisely,
    using the rulebook's reference-rate-and-monitoring rule:
    $$\text{payoff} = \mathbf{1}\{\max_{t \in \mathcal{T}} S^{ref}_t \ge B\}$$
    where $\mathcal{T}$ is the monitoring set (continuous interval
    $[t_0, T]$ or discrete grid), $S^{ref}_t$ is the rulebook's
    reference rate, and $B = 4.9999$. State the inequality direction
    explicitly per the rulebook.

Adverse-selection implications
Specifically for this series:
- The reference rate's venue determines who is informationally
  advantaged. If reference is PTAX, then dealers in BCB's PTAX poll
  panel are advantaged. If CME 6L, then iLink subscribers vs free-feed
  users.
- Latency from reference-venue tick to Kalshi orderbook response is the
  adverse-selection window for a passive market maker. Estimate in
  seconds.
- The discrete vs continuous monitoring rule determines whether
  sub-second jumps create adverse selection — discrete monitoring
  collapses sub-second risk; continuous amplifies it.

Theo-input contribution
This phase produces no new market-data inputs — it produces the
mathematical specification (the payoff function and the reference rate)
that the theo computes against. Phase 14 will combine the Phase 8 vol
surface, the Phase 6/5 drift inputs, and this phase's specification.

Sources to prioritize
- The KXUSDBRLMAX contract page itself (web_fetch).
- Kalshi rulebook (kalshi.com/rulebook or equivalent).
- Kalshi fee schedule.
- Kalshi API documentation (trading-api.readme.io or current equivalent).
- Kalshi market maker / incentives documentation.
- CFTC DCM self-certification filing for KXUSDBRLMAX (search
  sirt.cftc.gov for "KXUSDBRLMAX" or "USDBRL").
- Any Kalshi blog post or press release introducing the FX series.

Do NOT
- Speculate on rule details that are not in the rulebook. If the
  rulebook is silent on a point, say so explicitly and flag it as a
  question to escalate to Kalshi support.
- Conflate the series rulebook with the general Kalshi rulebook — both
  may govern the contract.
- Skip the formal payoff function — it is the canonical deliverable.
- Skip the Adverse-selection implications subsection.
```

---

## Phase 14 — Synthesis: Touch-Barrier Theo + Quote Policy

```
You are executing Phase 14 of 16. Prior phases required: Phases 1–13. Read
all thirteen prior .md files in ./research/ before beginning; halt if any are
missing.

Goal
Produce the bridge document: a complete specification of the theoretical-value
computation and the quote-generation policy for the KXUSDBRLMAX contract,
combining everything from Phases 1–13. Output should be implementation-ready
in the sense that an engineer could turn it into pseudocode without further
research, but it does not contain production code — it contains pseudocode and
the design decisions that constrain code.

Method
This is a synthesis phase. Minimal new web research; heavy reliance on prior
phases. Where a synthesis decision depends on a fact you cannot find in
Phases 1–13, web_search to fill the gap and cite.

Deliverable
Save to ./research/phase_14_theo_and_quote_policy.md. Target 6,000–9,000
words, ≥20 cited sources (drawn from prior phases is fine, but cite each
inline). Pseudocode required for the theo computation and the quote
generation loop.

Required sections in the output
1. Theo construction algorithm:
   1.1. Inputs (with citation back to Phase 12's master mapping table):
        - Spot $S_t$ from the chosen venue (the same venue the Phase 13
          rulebook treats as reference, if available; otherwise a
          high-correlation proxy with documented basis).
        - Vol surface from CME BRL options + B3 DOL options + OTC NDF
          option indications (as feasible).
        - Domestic rate $r^{BRL}$ from DI curve.
        - Foreign rate $r^{USD}$ from SOFR curve.
        - Drift adjustments from carry (Phase 5) and external regime
          (Phase 6).
        - Conditioning indicators from Phase 7 (election proximity),
          Phase 5 (BCB intervention regime), Phase 8 (vol-surface
          regime), Phase 11 (real-time markout / VPIN).
   1.2. Model choice — recommend Stochastic-Local Volatility with
        Bates-style jumps (SLV+J) for this product. Justify against
        alternatives:
        - Pure GBM: rejected (smile-blind; Phase 3 shows this is
          materially mispriced for upside touches).
        - Heston: rejected (no automatic smile fit for short-dated
          calibration target; no jumps).
        - Local vol: rejected (forward-skew bias, well-documented
          overpricing of forward-starting and barrier products; Phase 3).
        - SLV (Lipton, Tataru–Fisher): closer, but jumpless.
        - SLV with Bates-style jumps: justified.
        Acknowledge the calibration cost (multi-week effort) and propose
        a phased implementation: start with calibrated Heston + Brownian
        bridge MC; upgrade to SLV+J in a later milestone.
   1.3. Calibration procedure:
        - Vanilla calibration target: the surface from Phase 8.
        - Outer leg fits SVI per maturity (with Gatheral–Jacquier
          no-arbitrage constraints).
        - Inner leg fits the SLV mixing parameter and jump intensity to
          reproduce the surface.
   1.4. Touch-probability computation:
        - Primary: Monte Carlo with Brownian-bridge correction, $N \ge
          500{,}000$ paths, antithetic variates, daily time step (with
          sub-day refinement near barrier events).
        - Cross-check 1: closed-form GBM upside-touch with a Vanna–Volga
          smile-skew-adjusted vol — gives a sanity range.
        - Cross-check 2: a static-replication calculation using a strip
          of vanilla calls (Carr–Bowie–Ellis from Phase 3).
        - Discrepancy threshold: if MC and Vanna–Volga GBM differ by
          more than 5 percentage points in touch probability, escalate
          to a pricing review — likely a calibration bug.
   1.5. Theo update cadence:
        - Spot-driven: recompute on every spot tick if cheap; otherwise
          every 1 second.
        - Vol-surface-driven: recompute on surface refresh (hourly
          baseline; 15-minute during NY session).
        - Macro / event-driven: recompute on event flag toggle.
   1.6. Pseudocode (not full code) for the theo computation loop.

2. Near-barrier regime handling:
   - As $S_t \to B$ from below, the one-touch theo approaches 1 from
     below. The Greek profile changes character — gamma explodes, vega
     sign-flips (already covered in Phase 3 — recap).
   - Quote-policy rule: when $|S_t - B| < $ X bp (e.g., 25 bp on
     log-scale), widen quotes by Y× the calm-regime spread and reduce
     size by Z×. Calibrate X, Y, Z from Phase 11 markout sensitivity.
   - Pull-on-near-touch rule: if $S_t \ge B - \epsilon$ for some
     pre-defined $\epsilon$, cancel all resting offers (the contract is
     about to go to 1; resting offers are toxic).

3. Adverse-selection-adjusted quote policy:
   - Use Phase 11's framework. Real-time inputs:
     - Recent markout (rolling 1m, 5m, 30m, 1h windows).
     - VPIN.
     - Order-flow imbalance (OFI).
     - Event-window indicator (binary or seconds-to-event from the
       Phase 11 informed-trader-windows checklist).
   - Mapping: for each input, define a multiplicative adjustment to the
     base spread. Combine multiplicatively (with a cap to avoid
     runaway widening).
   - Asymmetric quote width when inventory-skewed: if net long contracts
     > $L$, widen the bid by an additional $\alpha \cdot |q|$ where $q$
     is signed inventory.

4. Liquidity-incentive-aware quote policy (per Phase 13's findings):
   - Formulate the trade-off as an optimization:
     $$\max_{\delta^{bid}, \delta^{ask}, q^{bid}, q^{ask}}
       \mathbb{E}[\text{rebate} - \text{adverse selection cost} -
       \text{inventory cost}]$$
     subject to two-sided-presence and minimum-depth requirements from
     the incentive program.
   - Concrete sub-questions:
     - Do tighter quotes attract more flow, and if so does the rebate
       outweigh the worse markouts?
     - At what spread width does the rebate-per-contract just offset
       the expected adverse-selection cost-per-contract?
     - Should the incentive-eligibility rule be hard (always meet
       requirements) or soft (drop out during high-vol windows when
       adverse selection dominates)?
   - Decision rule: parameterize three regimes (incentive-priority,
     adverse-selection-priority, hybrid) and define the regime-switching
     conditions.

5. Hedging — open question, candidate enumeration:
   - CME BRL futures (6L) — the most accessible hedge. Liquidity profile
     reasonable; basis to KXUSDBRLMAX reference rate is small but exists.
     Contract size USD 100,000 notional.
   - Listed CME BRL options — to hedge convexity (gamma, vega) of the
     touch.
   - B3 DOL futures — deeper liquidity, but Brazilian account, FX
     conversion costs, regulatory friction.
   - OTC NDF / NDF options — ideal for large size but requires ISDA
     and a prime broker willing to quote.
   - Hedging policy options:
     - No hedge — accept directional exposure, smaller capital
       deployment.
     - Delta-only hedge with CME 6L — simplest; rebalance on
       threshold-trigger (delta exceeds X contracts).
     - Delta + vega hedge — adds CME BRL options for convexity.
     - Static replication — a strip of CME BRL calls held throughout;
       rebalance only at large vol-surface moves.
   - Decision deferred to a later phase / milestone, but enumerate the
     pros and cons for each.

6. Risk limits and kill criteria:
   - Hard position limit per side.
   - Hard daily-loss limit.
   - Soft daily-loss limit triggering quote widening.
   - Stale-data kill: if spot feed has not ticked in N seconds during
     a known-active session, pull all orders.
   - Vol-surface kill: if no vol-surface update in M minutes, pull all
     orders.
   - Theo-discrepancy kill (per 1.4): if MC vs Vanna–Volga > 5pp,
     pull all orders and escalate.

7. Pseudocode for the quote-generation loop (synchronous, ~1Hz):
   - Read spot, recent fills, current inventory, current event-flag
     state.
   - Compute theo (or use cached if recent enough).
   - Compute adverse-selection multiplier from real-time stats.
   - Compute base spread (from Phase 2 AS-style formula or from
     incentive-program minimum).
   - Apply adverse-selection multiplier, near-barrier adjustment,
     inventory skew.
   - Produce target bid, ask, sizes.
   - Diff against currently resting orders; cancel and place as needed.
   - Log markouts on any new fills.

Adverse-selection implications
Already integrated throughout. Restate the top-line: the highest-impact
adverse-selection vector for this product is informed flow in the seconds
following an unobserved spot move on the reference venue. The quote loop
must read the reference venue (or the closest proxy) at lower latency
than any observable Kalshi orderbook move.

Theo-input contribution
This phase produces the theo itself. Cross-reference back to Phase 12's
master input mapping.

Sources to prioritize
- All prior phases.
- Lipton (multiple papers on SLV).
- Andersen QE for Heston MC.
- Glasserman (2004) Ch. 6 for Brownian-bridge MC.
- Castagna (2010) for Vanna–Volga in the FX context.

Do NOT
- Write production code. Pseudocode only.
- Re-derive material already in prior phases — cite and link.
- Skip the hedging-enumeration section because hedging is "deferred."
  The enumeration itself is the deliverable.
```

---

## Phase 15 — Data & Tooling Stack Tailored to the Contract

```
You are executing Phase 15 of 16. Prior phases required: Phases 1–14. Read
all fourteen prior .md files in ./research/ before beginning; halt if any are
missing.

Goal
Distill Phases 4 and 12 into a minimum-viable and recommended data + tooling
stack for prototype market making on KXUSDBRLMAX. Include Kalshi's API
specifics from Phase 13. Identify the cheapest path to good-enough USD/BRL
spot, the cheapest path to a usable vol surface, and the cheapest path to
BCB / macro data. Compute and latency budget for the theo loop. Storage and
backtesting. Risk and ops.

Method
Synthesis with light incremental web research where pricing tiers have
changed since Phases 4 and 12 were written.

Deliverable
Save to ./research/phase_15_data_tooling_stack.md. Target 3,500–5,000 words,
≥20 distinct sources cited.

Required sections in the output
1. Minimum-viable stack (small prototype, single-trader budget):
   - Spot: free CME delayed front-month 6L from Polygon.io free tier or
     equivalent. Acknowledge the latency penalty and quantify it.
   - Vol surface: CME BRL options end-of-day from CME free data + manual
     surface updates intraday from any visible OTC indications. Or
     subscribe to a single mid-tier vendor (~$X/mo).
   - Rates: BCB SGS API (free) for DI curve construction; FRED (free)
     for SOFR.
   - BCB / macro: free SGS + Olinda APIs.
   - Political: free public poll publication monitoring + manual.
   - Kalshi: official Python SDK + WebSocket orderbook stream.
   - Pricing: QuantLib-Python for SVI / SABR fit + custom Brownian-bridge
     MC. Numba-JIT for the MC kernel.
   - Storage: ArcticDB or DuckDB for tick-level archives.
   - Compute: a single Mac mini / NUC running 24/7 is sufficient for
     the synchronous 1Hz loop.
   - Total monthly recurring cost target: <$200/mo.
2. Recommended stack (better-than-MVP, still small operation):
   - Spot: paid real-time CME 6L feed.
   - Vol surface: a paid OTC vol indication source (specific vendor; cite
     pricing).
   - Pricing: invest engineering time in SLV + jump calibration; use
     QuantLib for SVI fit, custom code for SLV mixing.
   - All other items: same as MVP but upgrade where bottleneck is
     identified.
   - Total monthly recurring cost target: $1,000–3,000/mo.
3. Compute and latency budget for the theo loop:
   - Theo recomputation triggers: spot tick, vol-surface refresh,
     event flag toggle.
   - Target end-to-end latency from spot tick to Kalshi order
     update: <500 ms with MVP stack; <100 ms with recommended stack.
   - Justify why these latencies are sufficient (Phase 13 reference
     rate cadence; Phase 11 informed-trader-window analysis).
4. Storage and backtesting:
   - Kalshi historical data: how far back? Per Phase 13, document
     availability.
   - BRL futures and options history for backtesting the theo offline
     (CME Datamine, Quandl/Nasdaq Data Link, B3 historical).
   - Backtesting framework: simple bar-replay against historical theo
     vs historical Kalshi marks; emphasize the lookahead-bias risk.
5. Risk and ops:
   - Kill switch wiring (Phase 14 risk limits implementation).
   - Position reconciliation (poll Kalshi positions every N seconds vs
     internal state).
   - Alerting on stale data, fill anomalies, theo-discrepancy
     escalations.
   - Logging schema for fills, markouts, theo snapshots.
   - Monitoring dashboard requirements (live PnL, position by strike if
     applicable, theo vs market spread, recent markouts, event-flag
     state).

Adverse-selection implications
The MVP stack's free-CME-delayed-feed introduces material
adverse-selection risk during fast moves. Explicit mitigation: widen
quotes by a factor accounting for the delay, or pull during high-vol
windows. Document a delay-aware quote-policy adjustment.

Theo-input contribution
This phase makes Phase 14's theo implementable on real infrastructure.
Cross-reference Phase 14's input list to Phase 15's specific data
sources.

Sources to prioritize
- Kalshi API docs (already cited Phase 13).
- Vendor pages for any cited paid feed (verify pricing as of writing).
- ArcticDB and DuckDB documentation.
- QuantLib-Python documentation for SVI and barrier pricers.

Do NOT
- Recommend a vendor whose pricing you cannot cite from a current
  source.
- Treat MVP-stack latency as a non-issue. It is the dominant
  adverse-selection risk in the MVP.
- Skip the Adverse-selection or Theo-input subsections.
```

---

## Phase 16 — Strategy Synthesis and Open Questions

```
You are executing Phase 16 of 16, the final phase. Prior phases required:
Phases 1–15. Read all fifteen prior .md files in ./research/ before
beginning; halt if any are missing.

Goal
Pull Phases 9 (discretionary), 10 (systematic), 11 (adverse selection), and
14 (theo + quote policy) forward into a single strategic synthesis. Identify
which discretionary and systematic edges meaningfully sharpen the theo or
reduce adverse selection vs a naive quoting baseline. Enumerate open
empirical questions, kill criteria, and a milestone-based prototype roadmap.

Method
Pure synthesis with optional light web research for any open question that a
single new search could close.

Deliverable
Save to ./research/phase_16_strategy_synthesis.md. Target 4,000–6,000 words,
≥15 distinct sources cited.

Required sections in the output
1. Edges that sharpen the theo:
   - From Phase 5 (BCB intervention regime conditioning).
   - From Phase 6 (DXY / cross-asset drift conditioning).
   - From Phase 7 (election-proximity jump-intensity conditioning).
   - From Phase 8 (live OTC vol-surface vs CME-implied surface basis).
   - From Phase 9 (real-money flow calendar — month-end, dividend
     remittance season).
   - From Phase 10 (carry and momentum signals as drift adjustments).
   For each: rate the marginal expected impact on theo accuracy
   (Low / Medium / High) with justification.
2. Edges that reduce adverse selection:
   - From Phase 11 (real-time markout, VPIN, event-pull rules).
   - From Phase 13 (latency-aware quote-policy adjustments).
   - From Phase 8 (vol-surface-as-leading-indicator quote pulls).
   - From Phase 9 (BCB auction front-running detection — if BCB-dealer
     flow visible to your data feed).
   For each: rate the marginal expected impact (Low / Medium / High).
3. Naive quoting baseline definition:
   - Two-sided post-only quotes at fixed-width around a constant theo
     of 50%. This is the dumbest possible MM strategy and exists only
     to define a baseline.
   - First upgrade: quotes around a calibrated theo (Phase 14 step 1).
   - Second upgrade: quotes around a calibrated theo with adverse-
     selection-adjusted spread (Phase 14 step 3).
   - Third upgrade: with liquidity-incentive optimization (Phase 14
     step 4).
   - Fourth upgrade: with hedging (Phase 14 step 5).
4. Open empirical questions (each requires future data work, not more
   reading):
   - Empirical correlation between front-month BRL-future ticks and the
     implied touch probability computed from CME BRL options for the
     7-month barrier — is the cross-asset alignment tight enough to
     trust as a fast theo proxy?
   - Markout structure on Kalshi KXUSDBRLMAX fills: how do markouts
     scale with time horizon, and where does the markout flatten?
   - Election-week vol blow-out empirics: how does the implied touch
     probability typically move in the 4 weeks around a Brazilian
     presidential first round?
   - Liquidity-incentive program economics — given Phase 13's program
     details, what is the empirically-realized rebate-per-contract for a
     consistent two-sided quoter, and how does it compare to typical
     adverse-selection cost?
5. Kill criteria for the entire prototype:
   - K-1: backtested theo R² vs historical Kalshi marks on settled
     contracts < some threshold (specify).
   - K-2: live markouts on filled quotes exceed Y% of captured
     spread over W weeks of paper-trading.
   - K-3: liquidity-incentive program is discontinued before live
     deployment.
   - K-4: SLV+J calibration cannot be made stable on the available
     vol-surface data within Z weeks of engineering.
   - K-5: regulatory or operational changes to KXUSDBRLMAX rulebook
     materially alter the payoff function.
6. Milestone-based prototype roadmap:
   - M0: Repo scaffold; project skeleton; CI; data ingestion stubs.
   - M1: Offline theo reproduction — replicate the calibrated theo on
     historical data; backtest vs historical settled KXUSDBRLMAX
     marks (or analogous historical FX-touch markets if available).
   - M2: Paper-trade quoting against live Kalshi orderbook with the
     calibrated theo; collect markout statistics; tune
     adverse-selection multipliers.
   - M3: Small-capital live quoting with kill switches engaged; track
     liquidity-incentive participation; compare realized vs expected
     rebate.
   - M4: Hedging-loop addition — start with delta-only CME 6L; measure
     hedge cost vs adverse-selection-cost reduction.
   - M5: SLV+J upgrade; vega hedging; scale capital.
   For each milestone: estimated engineering effort, key risks, exit
   criteria into the next milestone.
7. Final synthesis: in <500 words, the executive case for the project's
   viability and the dominant uncertainties.

Adverse-selection implications
Subsumed throughout — the entire phase is partly about adverse-selection
edges.

Theo-input contribution
This phase does not produce new theo inputs; it ranks the existing inputs
by expected marginal value and identifies the empirical work needed to
validate the rankings.

Sources to prioritize
- All prior phases (cite inline).
- One or two recent practitioner blog posts or papers on the
  performance of EM-FX market-making strategies, if any are
  publicly available.

Do NOT
- Add new strategy ideas not grounded in prior-phase research.
- Skip the milestone roadmap — it is the project's planning artifact.
- Skip the Adverse-selection or Theo-input subsections (even though
  they are short here).
```

---

## End of stack

Execution order is strict: Phase 1 → Phase 16. Each phase is one fresh context window. Save outputs as named. The Phase 13 introduction of Kalshi is the discipline gate — Phases 1–12 must stay clean of any prediction-market reference.
