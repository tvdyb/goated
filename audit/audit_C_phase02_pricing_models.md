# Audit C — Phase 02: Market Making Pricing Models

## 1. Source Summary

The source artifact (`research/phase_02_market_making_pricing_models.md`) is a literature survey that reproduces the canonical equations of three converging market-making model families — inventory-based (Ho–Stoll, Grossman–Miller), information-based (Glosten–Milgrom, Kyle, PIN/VPIN), and stochastic-optimal-control (Avellaneda–Stoikov, GLFT, Cartea–Jaimungal) — and then maps where their assumptions break for agricultural commodities, soybeans in particular. It introduces limit-order-book microstructure (Cont–de Larrard queue model, Cont–Kukanov–Stoikov order-flow imbalance), stochastic-volatility / jump extensions (Heston, Merton, Bates), and commodity-specific overlays (seasonal vol, theory of storage, index-roll flows, USDA-event jumps, overnight thinness, exchange limit-up truncation). It closes with a practitioner-stack summary contrasting academic models against industry practice and an explicit list of problems pricing models do *not* solve (hedging, capital allocation, risk limits, when-to-stop). The artifact's central argument: canonical market-making formulas are necessary but insufficient for soybean quoting; commodity-specific extensions must be grafted onto the HJB skeleton.

## 2. Claims Table

| id | claim | research citation | certainty | topic tag(s) |
|---|---|---|---|---|
| C02-01 | A market maker faces three risk sources: inventory risk, adverse selection, and volatility/jump risk. | §1, lines 28–40 | established | pricing-model; inventory |
| C02-02 | Half-spreads are defined as $\delta^a = p^a - S$ and $\delta^b = S - p^b$ around a reference $S_t$. | §1, lines 42–44 | established | pricing-model |
| C02-03 | Cash and inventory dynamics: $dX_t = (S_t + \delta^a_t)\,dN^a_t - (S_t - \delta^b_t)\,dN^b_t$, $dq_t = dN^b_t - dN^a_t$, $dS_t = \mu_t\,dt + \sigma_t\,dW_t + \text{jumps}$. | §1, lines 46–52 | established | pricing-model; inventory |
| C02-04 | Quoting objective: maximize $U(X_T + q_T S_T)$ or expected P&L less a quadratic inventory penalty. | §1, lines 55–58 | established | pricing-model; inventory |
| C02-05 | Ho–Stoll optimal half-spread: $\delta^{a,b} = \tfrac{1}{2}s \mp \gamma \sigma^2 (T-t)\,q$. | §2.1, lines 64–72 | established | pricing-model; inventory |
| C02-06 | Ho–Stoll reservation price: $r = S - \gamma \sigma^2 (T-t)\,q$. | §2.1, lines 74–77 | established | pricing-model; inventory |
| C02-07 | A dealer long inventory quotes lower bid and lower ask (skew against inventory). | §2.1, lines 76–79 | established | pricing-model; inventory |
| C02-08 | Stoll (1978) decomposes the spread into holding cost, order cost, and information cost. | §2.1, lines 82–86 | established | pricing-model |
| C02-09 | Grossman–Miller price concession: $P_1 - E[P_2 \mid \mathcal{F}_1] = \frac{a \sigma^2_\epsilon}{M+1}\,i$. | §2.2, lines 95–99 | established | pricing-model; inventory; market-structure |
| C02-10 | The supply of immediacy is endogenous; effective $M$ falls when volatility rises because capital reallocates. | §2.2, lines 103–105 | established | market-structure; inventory |
| C02-11 | Post-WASDE limit-order-book depth collapses, briefly reducing effective $M$ and widening the Grossman–Miller concession in grains. | §2.2, lines 105–108 | established | market-structure; inventory |
| C02-12 | Glosten–Milgrom Bayesian quotes: $\text{ask}_t = E[V \mid \mathcal{F}_t, \text{buy}]$, $\text{bid}_t = E[V \mid \mathcal{F}_t, \text{sell}]$. | §3.1, lines 121–125 | established | pricing-model |
| C02-13 | The Glosten–Milgrom spread widens monotonically in $\alpha$ (informed share) and in $V_H - V_L$. | §3.1, lines 126–128 | established | pricing-model |
| C02-14 | Glosten–Milgrom-style adverse selection can collapse the market in an Akerlof-style breakdown. | §3.1, lines 128–129 | established | pricing-model; market-structure |
| C02-15 | Kyle (1985) linear equilibrium: $\lambda = \tfrac{1}{2}\sqrt{\sigma_v^2/\sigma_u^2}$, $\beta = \sqrt{\sigma_u^2/\sigma_v^2}$, $p = p_0 + \lambda y$. | §3.2, lines 140–144 | established | pricing-model; market-structure |
| C02-16 | Kyle's $\lambda$ is price impact per unit order flow; market depth is $1/\lambda$. | §3.2, lines 146–148 | established | market-structure |
| C02-17 | PIN: $\text{PIN} = \frac{\alpha \mu}{\alpha \mu + 2\varepsilon}$, where $\mu$ is informed arrival rate and $\varepsilon$ per-side uninformed rate. | §3.3, lines 161–165 | established | pricing-model |
| C02-18 | VPIN: $\text{VPIN} = \frac{\sum_{\tau=1}^{n} |V_\tau^B - V_\tau^S|}{n V}$, with $V$ the equal-volume bucket size. | §3.3, lines 174–178 | established | pricing-model; market-structure |
| C02-19 | VPIN's predictive power around the May 2010 flash crash is contested; Andersen–Bondarenko show much of it is mechanical from bucketing. | §3.3, lines 180–184 | debated | pricing-model |
| C02-20 | The academic verdict treats VPIN as a *realized* (not forward-looking) order-flow-toxicity measure. | §3.3, lines 184–185 | established | pricing-model |
| C02-21 | Avellaneda–Stoikov objective: $\max E[-\exp(-\gamma(X_T + q_T S_T))]$ with $dS_t = \sigma\,dW_t$. | §4.1, lines 195–199 | established | pricing-model |
| C02-22 | A–S execution intensities decay exponentially with distance from mid: $\lambda^{a,b}(\delta) = A\,e^{-k \delta}$. | §4.1, lines 202–204 | established | pricing-model |
| C02-23 | The A–S value function $u(t,s,x,q)$ satisfies a specific HJB combining diffusion of $S_t$ with two intensity-weighted control terms. | §4.1, lines 207–212 | established | pricing-model |
| C02-24 | A–S reservation price: $r(s, q, t) = s - q\,\gamma \sigma^2 (T-t)$ (identical in form to Ho–Stoll). | §4.1, lines 217–219 | established | pricing-model; inventory |
| C02-25 | A–S optimal symmetric total spread: $\delta^a + \delta^b = \gamma \sigma^2 (T-t) + \frac{2}{\gamma}\ln(1 + \gamma/k)$. | §4.1, lines 224–226 | established | pricing-model |
| C02-26 | A–S optimal quotes: $p^a = r + \tfrac{1}{2}(\delta^a+\delta^b)$, $p^b = r - \tfrac{1}{2}(\delta^a+\delta^b)$. | §4.1, lines 230–233 | established | pricing-model |
| C02-27 | Spread independence from inventory in baseline A–S is an artifact of CARA + exponential intensity; relaxing either dependency restores inventory-dependent spreads. | §4.1, lines 236–240 | established | pricing-model; inventory |
| C02-28 | GLFT asymptotic ask quote: $\delta^{a*}(q) \approx \frac{1}{\gamma}\ln(1+\gamma/k) + \sqrt{\frac{\sigma^2 \gamma}{2 k A}(1+\gamma/k)^{1+k/\gamma}}\cdot(2q+1)$. | §4.2, lines 253–256 | established | pricing-model; inventory |
| C02-29 | GLFT asymptotic total spread at $q=0$: $\Psi \approx \frac{2}{\gamma}\ln(1+\gamma/k) + \sigma\sqrt{\frac{\gamma}{k A}\,g(\gamma, k)}$. | §4.2, lines 260–262 | established | pricing-model |
| C02-30 | GLFT imposes hard inventory bounds $q \in \{-Q, \ldots, +Q\}$ as a built-in constraint. | §4.2, lines 248–250 | established | inventory; pricing-model |
| C02-31 | Cartea–Jaimungal–Ricci ("Buy Low Sell High"): fill rate depends on a latent short-term price drift, so optimal quotes contain a term proportional to the alpha signal. | §4.3, lines 277–281 | established | pricing-model; strategy |
| C02-32 | Cartea–Wang (2020) embed an alpha signal $\alpha_t$ in the drift; optimal quotes shift both reservation price and spread asymmetry with signal strength. | §4.3, lines 286–289 | established | pricing-model; strategy |
| C02-33 | Guéant (2017) generalizes to non-exponential intensities and multi-asset hedged quoting with cross-asset inventory penalties. | §4.3, lines 290–293 | established | pricing-model; hedging; inventory |
| C02-34 | Cont–de Larrard probability of next mid-up move under symmetric intensities: $P(\text{up} \mid q^b, q^a) = \frac{q^b}{q^b + q^a}$. | §5.1, lines 312–314 | established | market-structure; density |
| C02-35 | Huang–Lehalle–Rosenbaum queue-reactive model: arrival intensities depend on queue size, so thin queues collapse faster than thick ones. | §5.1, lines 317–321 | established | market-structure; density |
| C02-36 | Queue-front orders are disproportionately adverse-selected relative to queue-back orders. | §5.1, lines 320–321 | established | market-structure |
| C02-37 | Cont–Kukanov–Stoikov OFI per book update: $e_n = \mathbb{1}\{p^b_n \ge p^b_{n-1}\}q^b_n - \mathbb{1}\{p^b_n \le p^b_{n-1}\}q^b_{n-1} - \mathbb{1}\{p^a_n \le p^a_{n-1}\}q^a_n + \mathbb{1}\{p^a_n \ge p^a_{n-1}\}q^a_{n-1}$. | §5.2, lines 327–332 | established | market-structure; data-ingest |
| C02-38 | Contemporaneous mid-price changes are linear in OFI with slope inversely proportional to depth: $\Delta p \approx \text{OFI}/\text{depth}$. | §5.2, lines 336–340 | established | market-structure; pricing-model |
| C02-39 | The OFI slope is a direct, non-parametric estimate of Kyle's $\lambda$ at top of book. | §5.2, lines 342–344 | established | market-structure |
| C02-40 | OFI linearity holds across asset classes; Federal Reserve U.S. Treasury research replicates the relation. | §5.2, lines 344–347 | established | market-structure |
| C02-41 | For soybeans, OFI at the top three price levels is computable from the CME MBO/MBP feed. | §5.2, lines 347–348 | established | data-ingest; market-structure |
| C02-42 | Heston model: $dS_t = \mu S_t dt + \sqrt{v_t}S_t dW^S_t$, $dv_t = \kappa(\theta-v_t)dt + \xi\sqrt{v_t}dW^v_t$, $d\langle W^S, W^v\rangle = \rho dt$. | §6, lines 358–362 | established | pricing-model |
| C02-43 | With Heston vol, the A–S reservation price becomes $r_t = S_t - q_t\,\gamma\,v_t\,(T-t)$ and any $\sigma^2$ slot is replaced by $v_t$. | §6, lines 367–370 | established | pricing-model; inventory |
| C02-44 | Soybean $v_t$ has a strong seasonal component and an autocorrelation structure unlike equity indices. | §6, lines 372–374 | established | density; market-structure |
| C02-45 | Merton jump-diffusion: $\frac{dS_t}{S_{t^-}} = (\mu - \lambda\kappa)dt + \sigma dW_t + (J_t-1)dN_t$, with $N_t \sim \text{Poisson}(\lambda)$ and lognormal $J_t$. | §6, lines 379–381 | established | pricing-model |
| C02-46 | Bates SVJ (Heston + Merton jumps) is needed to match both the smile and the term structure of implied vol. | §6, lines 383–385 | established | pricing-model |
| C02-47 | Soybean scheduled events (WASDE, Crop Progress) are modeled as predictable jump dates with stochastic sizes. | §6, lines 386–388 | established | pricing-model; market-structure |
| C02-48 | Unscheduled soybean events (sudden weather shocks, export bans) are true Poisson arrivals. | §6, lines 387–388 | established | pricing-model; market-structure |
| C02-49 | Models ignoring jumps will systematically under-quote spreads on WASDE mornings and over-quote during quiet August afternoons with benign weather. | §6, lines 388–390 | established | pricing-model |
| C02-50 | Soybean 30-day implied volatility systematically peaks around July 4, stays elevated through pod-fill in August, then collapses at harvest. | §7.1, lines 397–400 | established | density |
| C02-51 | $\sigma$ in the A–S formula must be time-varying and calendar-indexed, not estimated from a trailing window. | §7.1, lines 402–404 | established | pricing-model; density |
| C02-52 | Kaldor–Working forward relation: $F_t(T) = S_t\,e^{(r + u - y)(T-t)}$, with $r$ rate, $u$ storage cost, $y$ convenience yield. | §7.2, lines 414–416 | established | pricing-model |
| C02-53 | Backwardation ($F < S$) occurs when inventories are scarce and convenience yield is large; contango when abundant. | §7.2, lines 418–420 | established | market-structure |
| C02-54 | Deaton–Laroque: with a non-negativity constraint on inventory, commodity prices follow a nonlinear AR with occasional stockout explosions. | §7.2, lines 422–425 | established | inventory; market-structure |
| C02-55 | Routledge–Seppi–Spatt: the convenience yield is endogenous, a function of inventory state, and the equilibrium curve embeds timing options. | §7.2, lines 425–427 | established | inventory; market-structure |
| C02-56 | The reservation-price drift term should incorporate mean reversion toward a long-run level when inventories are extreme. | §7.2, lines 427–431 | established | pricing-model; inventory |
| C02-57 | Forward-curve shape (contango vs. backwardation) signals the direction of carry/roll, which dominates inventory-holding cost in quiet weeks. | §7.2, lines 430–432 | established | strategy; market-structure |
| C02-58 | The "Goldman roll" closes 20% of a contract on each of business days 5–9 of the month preceding expiry, opening the corresponding amount in the next deferred. | §7.3, lines 436–438 | established | market-structure; strategy |
| C02-59 | A statistically robust calendar-spread front-running pattern occurs around index-roll dates (Yu CFTC; Irwin–Sanders–Yan). | §7.3, lines 439–442 | established | strategy; market-structure |
| C02-60 | Estimated cost of the index roll to investors is ~3.6% per year across commodities. | §7.3, lines 442–443 | established | market-structure |
| C02-61 | The soybean roll generates predictable front–back calendar spread flow, transient depth asymmetries at the deferred leg, and information-free order flow. | §7.3, lines 443–446 | established | market-structure |
| C02-62 | Index-roll order flow should widen the adverse-selection premium less than an unscheduled trade of the same size. | §7.3, lines 444–446 | established | strategy; pricing-model |
| C02-63 | WASDE-day diurnal volatility pattern: subdued at open, eases mid-morning, spikes immediately after 11:00 a.m. CT, fades within an hour. | §7.4, lines 449–454 | established | market-structure; density |
| C02-64 | The 2013 shift to in-session WASDE release sharply increased jump clustering on report days. | §7.4, lines 455–458 | established | market-structure |
| C02-65 | Best practice on report days is a regime-switching overlay: pull quotes or widen the spread by a multiplicative factor $\kappa_t$ for a window around release, calibrated from historical jump variance. | §7.4, lines 460–462 | established | strategy; oms |
| C02-66 | Cartea–Jaimungal accommodates event-driven regime change via a deterministic, time-indexed jump intensity $\lambda_t^J$ in the value function. | §7.4, lines 462–464 | established | pricing-model |
| C02-67 | The empirical calibration of "which report moves the market how much" is only partly answered by the academic literature. | §7.4, lines 464–465 | practitioner-lore | pricing-model |
| C02-68 | Soybeans trade Sunday 7:00 p.m. CT through Friday 7:45 a.m. CT with a brief daily maintenance gap. | §7.5, lines 467–470 | established | market-structure |
| C02-69 | Day-session soybean volume is roughly 8–10× the overnight hourly rate. | §7.5, lines 471–473 | established | market-structure; density |
| C02-70 | Poisson-intensity assumption with a single $A$ parameter breaks down; $A$ should be time-of-day and day-of-week indexed. | §7.5, lines 473–475 | established | pricing-model |
| C02-71 | $dS_t = \sigma dW_t$ overstates small-move probability overnight and understates gap probability; a mixture of low-variance diffusion and a heavy-tailed jump component is required. | §7.5, lines 475–478 | established | pricing-model; density |
| C02-72 | Most prop market makers widen spreads or withdraw during overnight hours rather than rely on the closed-form quoting policy. | §7.5, lines 477–480 | practitioner-lore | strategy; oms |
| C02-73 | Overnight, the GLFT closed-form is "not a quoting policy but a warning signal" about how conservative to be. | §7.5, lines 478–480 | practitioner-lore | pricing-model; strategy |
| C02-74 | Soybean returns exhibit persistent leptokurtosis that no single-factor GBM captures. | §7.6, lines 483–486 | established | density |
| C02-75 | The minimum viable model for grain volatility is GARCH/Heston-style stochastic vol plus jumps. | §7.6, lines 486–488 | established | pricing-model; density |
| C02-76 | The variable-limit rule (soybeans ≥ 50¢/bu initial limit, expanding 50%) caps observed fat tails via exchange-imposed truncation; price moves during a lock are censored from the book. | §7.6, lines 488–492 | established | market-structure; density |
| C02-77 | Vol estimators fit to observed prices are downward-biased when limit-locking censors true moves. | §7.6, lines 490–492 | established | density |
| C02-78 | Practitioner stack item 1: a short-horizon alpha signal, almost always OFI-based plus trade-sign imbalance, sometimes augmented with cross-asset lead–lag (crush, corn–soy ratio). | §8, lines 504–507 | practitioner-lore | strategy; market-structure |
| C02-79 | Practitioner stack item 2: a reservation-price skew against inventory à la Ho–Stoll/A–S, with a hard inventory cap as in GLFT and a linear skew coefficient calibrated to realized vol. | §8, lines 508–510 | practitioner-lore | pricing-model; inventory |
| C02-80 | Practitioner stack item 3: spread = max(GLFT-style nominal spread, adverse-selection-protection spread keyed to recent signed flow plus VPIN-like toxicity). | §8, lines 511–513 | practitioner-lore | pricing-model |
| C02-81 | Practitioner stack item 4: a regime layer that widens spreads or withdraws quotes around scheduled events (WASDE, NFP), overnight, and during identified stress. | §8, lines 514–515 | practitioner-lore | strategy; oms |
| C02-82 | Practitioner stack item 5: risk-manager hard limits (notional inventory, delta, gamma) supersede optimizer output and truncate the policy. | §8, lines 516–517 | practitioner-lore | inventory; oms |
| C02-83 | Production desks run dozens of alpha signals in the drift term; most academic papers assume zero drift. | §8, lines 519–521 | practitioner-lore | strategy; pricing-model |
| C02-84 | Practitioners measure adverse selection via rolling realized spreads / post-trade mark-out at 1s, 5s, 60s rather than estimating PIN/VPIN. | §8, lines 521–523 | practitioner-lore | observability; backtest |
| C02-85 | Event-day calibration ("how much do I widen on USDA days") is proprietary, varies by desk, and is under-published. | §8, lines 523–526 | practitioner-lore | pricing-model |
| C02-86 | A commodity market maker quoting ZS may hedge in real time with ZC, ZM, ZL, MATIF rapeseed, or the Dalian complex. | §8, lines 530–532 | practitioner-lore | hedging |
| C02-87 | Cross-asset intensities are estimated empirically from trade and quote data; optimal hedge ratios rebalance more frequently than any stochastic-control model prescribes because transaction costs and basis risk dominate. | §8, lines 532–536 | practitioner-lore | hedging; backtest |
| C02-88 | Pricing models do not specify how to hedge (delta, gamma, crush-spread); hedging is a separate optimization layer. | §9, lines 540–543 | established | hedging |
| C02-89 | Pricing models do not specify capital deployment across contracts, books, and strategies. | §9, lines 543–545 | established | strategy |
| C02-90 | Pricing models do not set risk limits (inventory caps, loss-per-day, liquidity covenants); these are exogenous and truncate the policy. | §9, lines 545–547 | established | inventory |
| C02-91 | Pricing models do not specify when to stop quoting (locked limits, circuit breakers, structural liquidity collapse) — that is a meta-decision above the pricing model. | §9, lines 549–551 | established | oms; strategy |

## 3. What This File Does NOT Claim

The artifact is explicitly a *pricing* survey and deliberately defers several adjacent problems. It does not specify a hedging algorithm — delta, gamma, crush-spread, and basis hedges are flagged as out of scope (see C02-88). It does not solve capital allocation across contracts/books/strategies (C02-89). It does not set numeric risk limits (inventory caps, daily loss limits, liquidity covenants) — those are exogenous (C02-90). It does not specify *when* a quoter should pull off (locked limits, circuit breakers, structural liquidity collapse), characterizing that as a meta-decision (C02-91). On parameter grounds, the file does not provide numeric values for $\gamma$, $A$, $k$, or $Q$, nor does it propose a specific event-day spread multiplier $\kappa_t$ — the calibration is flagged as proprietary (C02-67, C02-85). It does not give published parameter tables for any major desk (Optiver, HRT, Jane Street). It does not describe testing/backtest harnesses, latency budgets, or observability/telemetry stacks; it does not address contract specifications beyond a passing reference to soybean trading hours (C02-68) and the variable-limit rule (C02-76). It does not describe cross-asset hedge math beyond noting that Guéant's multi-asset extension exists. It does not enumerate specific USDA report categories' historical jump variance (Crop Progress vs. WASDE vs. Grain Stocks vs. Prospective Plantings vs. Crop Production are named but not separately calibrated). It also does not commit to a specific trade-signing rule for VPIN — only that one is "often based on price changes within the bucket".

## 4. Cross-Links

C02-50 (seasonal vol peaks around July 4, elevated through pod-fill, collapses at harvest) and C02-63 (WASDE-day diurnal pattern with 11:00 a.m. CT spike) appear to depend on a Phase 01 calendar/hours artifact (the artifact itself cross-references "see Phase 01" at line 470 for soybean trading hours and at line 489 for the variable-limit rule), implying Phase 01 carries the canonical session and limit-rule claims that C02-68 and C02-76 restate.

C02-58 through C02-62 (Goldman roll mechanics, calendar-spread front-running, ~3.6% annual cost) plausibly contradict or constrain a "naive" inventory penalty model — the artifact itself notes index-roll order flow should widen the adverse-selection premium *less* than an unscheduled trade, suggesting any Phase 03 hedging or Phase 04+ strategy file that treats all order flow as informationally equivalent would conflict with C02-62.

C02-86 and C02-87 (cross-asset hedging with ZC, ZM, ZL, MATIF, Dalian; empirically estimated cross-asset intensities) point downstream to a hedging-phase artifact (the file labels hedging as "Phase 03 in this research stack" at line 543) — those phase files should carry the operational counterpart to the multi-asset Guéant extension referenced in C02-33.

C02-67, C02-85 (event-day calibration is proprietary and under-published) and C02-84 (mark-out at 1s, 5s, 60s as the practical adverse-selection metric) are signals to verify that any observability/backtest phase artifact carries empirical-calibration claims, since this file flags both as gaps the academic literature does not close.
