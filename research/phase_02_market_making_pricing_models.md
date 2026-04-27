# Phase 02 — Market Making Pricing Models: From Ho–Stoll to Commodity-Specific Adaptations

## Abstract

A market maker continuously posts two-sided quotes around an estimated fair value and earns the
bid–ask spread in exchange for bearing three risks: inventory-holding under exogenous price
noise, adverse selection against better-informed counterparties, and volatility/jump risk from
discrete events. The academic literature has addressed these risks along three historically
distinct threads — inventory control (Ho–Stoll, 1981; Grossman–Miller, 1988), information economics
(Glosten–Milgrom, 1985; Kyle, 1985; Easley et al., 1996, 2012), and stochastic optimal control
(Avellaneda–Stoikov, 2008; Guéant–Lehalle–Fernández-Tapia, 2013; Cartea–Jaimungal–Penalva, 2015)
— that converge in modern practice around an HJB-derived reservation price augmented by
order-flow-imbalance and queue-position signals. This survey reproduces the core equations of
each framework, compares their domains of applicability, and then examines where commodity
markets, and soybeans in particular, break the assumptions those frameworks rest on:
deterministic seasonal volatility regimes, storage-induced mean reversion, index-roll order
flow, discrete scheduled information events (USDA reports), and thin overnight liquidity with
gap risk. The central argument is that canonical market-making models are a necessary but
insufficient toolkit for agricultural futures; commodity-specific adaptations — stochastic
volatility, jump-diffusion, regime-switching, and explicit event-risk awareness — must be
grafted onto the stochastic-control skeleton for a soybean market-making quoter to survive
weather markets and WASDE days.

---

## 1. Framing: what a market maker's pricing problem actually is

A market maker's pricing problem is the continuous choice of a bid $p^b_t$ and an ask $p^a_t$
around a reference (mid or fair) price $S_t$, subject to three sources of risk:

1. **Inventory risk.** Between the time the market maker buys at $p^b$ and the time she unwinds
   at $p^a$, the reference price $S_t$ moves; her inventory $q_t$ accumulates mark-to-market P&L
   at rate $q_t \, dS_t$.
2. **Adverse selection.** Trades that hit her quotes are not randomly signed; an informed
   counterparty will preferentially lift the ask when $S_t$ is about to rise and hit the bid
   when $S_t$ is about to fall, producing a realized execution price worse than the quoted
   midpoint.
3. **Volatility / jump risk.** $S_t$ itself does not follow a clean Brownian motion; it is
   subject to stochastic volatility, scheduled announcements, and overnight gaps that can move
   the fair value by multiple ticks before the quote engine re-prices.

Formally, the market maker chooses a *quoting policy* $(\delta^a, \delta^b)$, where $\delta^a =
p^a - S$ and $\delta^b = S - p^b$ are half-spreads around the reference price. Her cash and
inventory evolve as:

$$
dX_t = (S_t + \delta^a_t)\,dN^a_t - (S_t - \delta^b_t)\,dN^b_t
$$

$$
dq_t = dN^b_t - dN^a_t, \qquad dS_t = \mu_t\,dt + \sigma_t\,dW_t + \text{jumps},
$$

where $N^a, N^b$ are point processes counting executions, whose intensities depend on
$(\delta^a, \delta^b)$ and on the state of the limit order book. The pricing problem is then to
choose $(\delta^a_t, \delta^b_t)$ to maximize a utility of terminal wealth $U(X_T + q_T S_T)$ or,
equivalently, expected P&L less a quadratic inventory penalty. Every model surveyed below is
a different choice of objective, intensity, and state.

## 2. Inventory-based models

### 2.1 Ho & Stoll (1981)

[Ho and Stoll's 1981 *Journal of Financial Economics* paper](https://www.sciencedirect.com/science/article/abs/pii/0304405X81900209)
is the canonical inventory model. A risk-averse monopolist dealer with CARA utility faces
stochastic buy and sell arrivals whose intensities $\lambda^a(\delta^a)$, $\lambda^b(\delta^b)$
are decreasing in the half-spread. The dealer's value function $V(q, W, t)$ (inventory $q$,
wealth $W$, time $t$) satisfies an HJB with the optimal half-spread

$$
\delta^{a,b} = \underbrace{\frac{1}{2}s}_{\text{spread}} \; \mp \; \underbrace{\gamma \sigma^2 (T-t)\,q}_{\text{inventory skew}},
$$

with $s$ the "spread at zero inventory" and $\gamma$ the CARA coefficient. The key result is
that the *midpoint* of the dealer's quotes is not the true mid $S$ but a *reservation price*
$r = S - \gamma \sigma^2 (T-t) q$, shifted *against* her inventory. A dealer long inventory
quotes lower bid and lower ask to attract sells-against-her and deter buys-from-her. This
inventory-skew intuition is the germ of every subsequent market-making model. Ho and Stoll
extend the single-dealer model to competitive dealers in [a 1983 JoF paper](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1983.tb02282.x),
a framework that anticipates modern multi-maker limit-order-book equilibria.

Earlier, [Stoll (1978)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1978.tb02053.x)
decomposes the bid–ask spread into three components — holding cost, order cost, and
information cost — a decomposition that remains the canonical taxonomy for interpreting
observed spreads and that structures the later econometric work of [Glosten and Harris](https://www.acsu.buffalo.edu/~keechung/MGF743/Readings/B3%20Glosten%20and%20Harris,%201988%20JFE.pdf)
and [Hasbrouck (1991)](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1991.tb03749.x).

### 2.2 Grossman–Miller (1988)

[Grossman and Miller's 1988 JoF paper](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1988.tb04594.x)
reframes liquidity itself as the *price of immediacy*: at $t=1$ an "initial trader" needs to
unwind a position but a matching counterparty only arrives at $t=2$; market makers bridge the
gap by absorbing the inventory at $t=1$ and unwinding at $t=2$, earning a concession for the
inventory risk over one period. In equilibrium with $M$ market makers of CARA coefficient $a$
and per-period variance $\sigma^2_\epsilon$,

$$
P_1 - E[P_2 \mid \mathcal{F}_1] \; = \; \frac{a \sigma^2_\epsilon}{M+1} \, i,
$$

where $i$ is the size of the inventory shock. The price concession is proportional to the
shock size, scales with market-maker risk aversion and volatility, and shrinks in the number of
liquidity providers. Two consequences matter for commodity markets: (i) the *supply of
immediacy* is endogenous — when vol rises, effective $M$ falls because capital reallocates —
and (ii) one-period autocorrelation of returns is a direct consequence of market-maker
inventory cycles, which Grossman–Miller formalize. In grains this effect is visible in the
post-WASDE minutes, when limit-order-book depth collapses and the effective $M$ briefly
plummets; the Grossman–Miller concession widens accordingly.

## 3. Adverse-selection / information-based models

### 3.1 Glosten & Milgrom (1985)

[Glosten and Milgrom (1985, JFE)](https://www.sciencedirect.com/science/article/pii/0304405X85900443)
abstract away inventory entirely and derive a bid–ask spread purely from asymmetric
information. A risk-neutral competitive market maker observes a sequential arrival of trades,
each from either an informed trader (fraction $\alpha$) who knows the true value
$V \in \{V_L, V_H\}$ or a liquidity trader (fraction $1-\alpha$) who buys or sells with equal
probability. Bayesian updating gives

$$
\text{ask}_t = E[V \mid \mathcal{F}_t, \text{trade}=\text{buy}], \qquad
\text{bid}_t = E[V \mid \mathcal{F}_t, \text{trade}=\text{sell}],
$$

so that the market maker's expected profit conditional on the trade is zero and the spread
$\text{ask} - \text{bid}$ is entirely adverse-selection compensation. The spread widens
monotonically in $\alpha$ and in $V_H - V_L$; it can *collapse the market* when
adverse selection is severe enough (Akerlof-style breakdown). The [Milgrom/Stanford reprint](https://milgrom.people.stanford.edu/wp-content/uploads/1984/09/Bid-Ask-and-Transaction-Prices.pdf)
is the clearest derivation.

### 3.2 Kyle (1985)

[Kyle's 1985 *Econometrica* model](https://people.duke.edu/~qc2/BA532/1985%20EMA%20Kyle.pdf)
studies a single risk-neutral informed trader submitting order size $x$ at a batch auction,
noise traders whose aggregate order is $u \sim \mathcal{N}(0, \sigma^2_u)$, and a competitive
market maker who observes only the total order $y = x + u$ and sets price $p = E[V \mid y]$. The
linear equilibrium has

$$
x = \beta(v - p_0), \quad p = p_0 + \lambda y, \quad
\lambda = \frac{1}{2}\sqrt{\frac{\sigma^2_v}{\sigma^2_u}}, \quad
\beta = \sqrt{\frac{\sigma^2_u}{\sigma^2_v}},
$$

where $\sigma^2_v$ is the variance of the terminal value. The $\lambda$ coefficient — *Kyle's
lambda* — is the price impact per unit of order flow and is the inverse of "market depth"
$1/\lambda$. In the [sequential-auction extension](https://www.kellogg.northwestern.edu/research/math/papers/570.pdf),
the informed trader optimally spreads his trades over the session, and prices follow Brownian
motion under $\lambda$, with full information incorporated by $T$. Kyle's lambda is the
foundational measure of liquidity in the price-impact literature and the object that much of
agent-based market microstructure research since has tried to estimate empirically.

### 3.3 PIN and VPIN

[Easley, Kiefer, O'Hara and Paperman (1996, JoF)](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb04074.x),
building on Glosten–Milgrom, developed the *Probability of Informed Trading* (PIN). A Poisson
mixture model assumes daily buys $B_t$ and sells $S_t$ are driven by balanced liquidity flow
plus an information-event component arriving with probability $\alpha$; given the event, the
informed flow has known buy/sell direction. PIN is the population share of informed orders:

$$
\text{PIN} = \frac{\alpha \mu}{\alpha \mu + 2\varepsilon},
$$

where $\mu$ is the informed arrival rate and $\varepsilon$ the per-side uninformed rate.
Maximum-likelihood estimation on daily trade counts [is implemented in multiple R packages](https://journal.r-project.org/articles/RJ-2023-044/)
and has become the standard empirical measure of adverse selection in equity markets.

For high-frequency markets, [Easley, López de Prado, and O'Hara (2012)](https://www.quantresearch.org/VPIN.pdf)
proposed VPIN, the *Volume-synchronized PIN*, which bins trades by equal-volume buckets rather
than calendar time, using a trade-signing rule (often based on price changes within the
bucket). VPIN is:

$$
\text{VPIN} = \frac{\sum_{\tau=1}^{n} |V_\tau^B - V_\tau^S|}{n V},
$$

where $V$ is the bucket size and $V_\tau^B$, $V_\tau^S$ are the buy/sell volumes in bucket
$\tau$. Easley et al. argued VPIN spiked around the May 2010 flash crash; [Andersen and
Bondarenko (2014)](https://www.sciencedirect.com/science/article/abs/pii/S1386418113000189)
showed empirically that much of VPIN's predictive power is a mechanical consequence of
bucketing and that it did not, in fact, lead the flash crash. VPIN remains widely used as an
order-flow toxicity filter at HFT market-making desks, but the academic verdict is that it is
a *realized* rather than *forward-looking* measure.

## 4. Stochastic optimal control market making

### 4.1 Avellaneda & Stoikov (2008)

[Avellaneda and Stoikov's 2008 paper](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf)
is the modern industry benchmark. A single market maker on a single asset maximizes
exponential utility of terminal wealth over $[0,T]$:

$$
\max_{\delta^a, \delta^b} \; E\left[ -\exp\!\left(-\gamma (X_T + q_T S_T)\right) \right],
$$

with $S_t$ arithmetic Brownian motion ($dS_t = \sigma\,dW_t$) and execution intensities
decaying exponentially in distance from the mid,

$$
\lambda^{a,b}(\delta) = A\,e^{-k \delta}.
$$

The value function $u(t, s, x, q)$ solves the HJB

$$
u_t + \tfrac{1}{2}\sigma^2 u_{ss}
+ \max_{\delta^a}\!\Big\{\lambda^a(\delta^a)\!\left[u(t,s,x+(s+\delta^a),q-1) - u\right]\Big\}
+ \max_{\delta^b}\!\Big\{\lambda^b(\delta^b)\!\left[u(t,s,x-(s-\delta^b),q+1) - u\right]\Big\} = 0.
$$

With a CARA ansatz the problem decouples into (i) an *indifference* step that yields the
*reservation price*

$$
r(s, q, t) = s - q\,\gamma \sigma^2 (T-t),
$$

— identical in form to Ho–Stoll — and (ii) a *quoting* step that sets the optimal symmetric
spread around $r$:

$$
\delta^a + \delta^b \; = \; \gamma \sigma^2 (T-t) + \frac{2}{\gamma} \ln\!\left(1 + \frac{\gamma}{k}\right).
$$

The optimal quotes are then

$$
p^a = r + \tfrac{1}{2}(\delta^a + \delta^b), \qquad
p^b = r - \tfrac{1}{2}(\delta^a + \delta^b).
$$

Three features matter. First, the total spread has an inventory-risk term
$\gamma \sigma^2 (T-t)$ and an adverse-selection-like term $\frac{2}{\gamma}\ln(1+\gamma/k)$;
the latter captures the trade-off between wider spreads (more profit per trade) and lower
execution probability. Second, the reservation price *skews* against inventory linearly.
Third, the spread is *independent of inventory* in this baseline, an artifact of exponential
utility + exponential intensity that disappears when either assumption is relaxed. The paper
also derives a short-horizon "symmetric" approximation in which the market maker is treated as
if running at $T = \infty$ with a hard inventory cap.

### 4.2 Guéant, Lehalle & Fernández-Tapia (2013)

[GLFT](https://arxiv.org/abs/1105.3115) ([published 2013 in *Mathematics and Financial
Economics*](https://link.springer.com/article/10.1007/s11579-012-0087-0)) is the cleanest
closed-form generalization. They impose hard inventory bounds $q \in \{-Q, \ldots, +Q\}$ and
transform the HJB for the function $v(q,t) = \exp(-\gamma \theta(q,t))$ into a linear system of
ODEs, which in the infinite-horizon, symmetric case reduces to an eigenvalue problem with
closed-form asymptotic quotes

$$
\delta^{a*}(q) \approx \frac{1}{\gamma}\ln\!\left(1 + \frac{\gamma}{k}\right)
  + \sqrt{\frac{\sigma^2 \gamma}{2 k A}\,\left(1+\frac{\gamma}{k}\right)^{1+k/\gamma}} \cdot (2q+1),
$$

and symmetrically for the bid. The *asymptotic total spread* at $q=0$ is

$$
\Psi \; \approx \; \frac{2}{\gamma}\ln\!\left(1+\frac{\gamma}{k}\right) + \sigma\sqrt{\frac{\gamma}{k A}\,g(\gamma, k)},
$$

a formula that Lehalle's desk at Capital Fund Management and many sell-side quoting engines
parameterize directly. GLFT is attractive because it (a) has an inventory *penalty* term that
appears linearly in quote skew, (b) admits hard inventory bounds (which are always imposed by
risk management), and (c) yields spreads that depend on both volatility and order-arrival
intensity in an interpretable way.

### 4.3 Cartea, Jaimungal & Penalva and extensions

[Cartea, Jaimungal and Penalva (2015, Cambridge)](https://assets.cambridge.org/97811070/91146/frontmatter/9781107091146_frontmatter.pdf)
is the current standard reference, synthesizing a decade of the authors' own papers under a
single stochastic-control umbrella. Several extensions are especially relevant for commodity
market making:

- **Adverse selection via asymmetric fill intensities.** [Cartea, Jaimungal and Ricci (2014,
  SIAM JFM, *Buy Low Sell High*)](https://epubs.siam.org/doi/10.1137/130911196) make the fill
  rate depend on a latent short-term price drift: when the market maker posts against the
  prevailing order flow, executions are more frequent *and* adversely selected. This reshapes
  the HJB so that the optimal quote includes a term proportional to the alpha signal.
- **Risk metrics and fine-tuning.** [Cartea & Jaimungal (2015, *Mathematical Finance*)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2010417)
  introduce performance criteria for HF quoting strategies (realized-spread capture, inventory
  cost-of-capital, quadratic running penalty) that map cleanly onto how desks actually measure
  P&L attribution.
- **Alpha signals.** [Cartea and Wang (2020)](https://ora.ox.ac.uk/objects/uuid:c2ba6656-8eab-4b2e-a24a-e9e842d1378f/files/s41687h481)
  explicitly embed a signal $\alpha_t$ (e.g., order-flow-imbalance-derived price forecast) in
  the drift term and show that optimal quotes shift both the reservation price and the spread
  asymmetry in response to signal strength.
- **Generalized intensities and multi-asset.** [Guéant (2017)](https://arxiv.org/abs/1605.01862)
  extends the framework to non-exponential intensities and to multi-asset hedged quoting with
  cross-asset inventory penalties — the natural mathematical skeleton for quoting the
  soybean-meal-oil complex jointly.

Taken together, Cartea–Jaimungal and the Guéant line form a mature toolkit: the HJB is the
universal skeleton, and different intensity specifications, drift terms, and penalty structures
slot in as application-specific plugins.

## 5. Limit order book microstructure

Pricing models assume a reference $S_t$ exists; microstructure models ask how $S_t$ and the
arrival intensities $\lambda^{a,b}$ are *manufactured* by the queuing dynamics of the book.

### 5.1 Queue-position and hazard-rate models

[Cont and de Larrard (2013, SIAM JFM)](https://epubs.siam.org/doi/10.1137/110856605) model the
book as a Markovian queue: market orders, limit orders, and cancellations at the best bid/ask
arrive as independent Poissons, and the mid changes deterministically when a queue depletes.
Under this model the probability of the next price move being up, conditional on queue sizes
$(q^b, q^a)$, is

$$
P(\text{up} \mid q^b, q^a) \; = \; \frac{q^b}{q^b + q^a}
$$

under symmetric-intensity assumptions, and the hazard rate of a book "event" inherits closed
form. [Huang, Lehalle and Rosenbaum (2015, JASA, *queue-reactive model*)](https://arxiv.org/abs/1312.0563)
generalize this: arrival intensities depend on the queue size (so that thin queues collapse
faster than thick ones) and produce realistic multi-level book dynamics, which in turn let a
market maker estimate her *queue position* — a critical input when posting at best because
queue-front orders are disproportionately adverse-selected against queue-back orders.

### 5.2 Order-flow imbalance

[Cont, Kukanov and Stoikov (2014, JFE)](https://academic.oup.com/jfec/article-abstract/12/1/47/816163)
operationalize the most robust microstructural price-formation signal: *order-flow imbalance*
(OFI). Define, for each book update,

$$
e_n = \mathbb{1}\{p^b_n \ge p^b_{n-1}\}\,q^b_n - \mathbb{1}\{p^b_n \le p^b_{n-1}\}\,q^b_{n-1}
     - \mathbb{1}\{p^a_n \le p^a_{n-1}\}\,q^a_n + \mathbb{1}\{p^a_n \ge p^a_{n-1}\}\,q^a_{n-1}.
$$

Aggregating $e_n$ over an interval yields OFI. Cont, Kukanov and Stoikov document that, in a
panel of 50 U.S. stocks, contemporaneous mid-price changes are *linear* in OFI with slope
inversely proportional to average depth:

$$
\Delta p \; \approx \; \frac{\text{OFI}}{\text{depth}}.
$$

This is the empirical workhorse behind virtually every modern market-maker's short-horizon
alpha signal. OFI is also the predictor that ties market-making practice back to Kyle's
lambda — the slope above is a direct, non-parametric estimate of $\lambda$ at the book's top
of book. [Federal Reserve research on U.S. Treasury markets](https://www.federalreserve.gov/econres/notes/feds-notes/order-flow-imbalances-and-amplification-of-price-movements-evidence-from-u-s-treasury-markets-20251103.html)
extends the OFI framework to fixed-income futures and shows the same linearity holds across
asset classes. For soybeans, the analogous construction at the top three price levels is
computable from the CME MBO/MBP feed.

## 6. Stochastic volatility and jumps: why GBM is a bad fit for soybeans

Most market-making derivations take $dS_t = \sigma\,dW_t$ or $dS_t = \mu_t\,dt + \sigma\,dW_t$
with constant $\sigma$. For agricultural commodities this is a qualitative misspecification.

[Heston (1993, RFS)](https://academic.oup.com/rfs/article-abstract/6/2/327/1574747) replaces
constant variance with a square-root process:

$$
dS_t = \mu S_t\,dt + \sqrt{v_t}\,S_t\,dW^S_t, \qquad
dv_t = \kappa(\theta - v_t)\,dt + \xi\sqrt{v_t}\,dW^v_t, \quad
d\langle W^S, W^v\rangle = \rho\,dt,
$$

and derives a closed-form characteristic-function-based call price. For quoting, Heston's
contribution is not the option formula but the *mean-reverting vol process*: the reservation
price in Avellaneda–Stoikov becomes

$$
r_t = S_t - q_t\,\gamma\,v_t\,(T-t),
$$

and any spread formula with $\sigma^2$ in it now uses $v_t$. Empirically $v_t$ is not smooth in
agricultural markets; it has a strong seasonal component (see §7) and an autocorrelation
structure that is very different from equity indices.

Jumps are more important still. [Merton (1976, JFE)](https://www.sciencedirect.com/science/article/abs/pii/0304405X76900222)
adds a compound Poisson to a geometric Brownian motion:

$$
\frac{dS_t}{S_{t^-}} = (\mu - \lambda\kappa)\,dt + \sigma\,dW_t + (J_t - 1)\,dN_t,
$$

where $N_t$ is Poisson$(\lambda)$ and $J_t$ is the lognormal jump size. [Bates (1996, RFS)](https://academic.oup.com/rfs/article/9/1/69/1583938)
combines Heston with Merton jumps (the "SVJ" model) and shows the combination is needed to
match both the smile and the term structure of implied vol in DM options. For soybean markets,
the analog is that scheduled events (WASDE, Crop Progress) are well-modeled as predictable
jump dates with stochastic sizes; unscheduled events (sudden weather shocks, export bans) are
true Poisson arrivals. Any market-making model that ignores the jump component will
systematically under-quote spreads on WASDE mornings and over-quote them during quiet August
afternoons when the weather forecast is benign.

## 7. Commodity-specific adaptations and failures

### 7.1 Seasonality in volatility

Agricultural futures have a *deterministic seasonal vol regime*. [CME's white paper "Vol is
High by the Fourth of July"](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html)
documents that soybean 30-day implied volatility systematically peaks around July 4 and
remains elevated through pod-fill in August, before collapsing as harvest clarifies yield.
[CME's "Weather Markets in Grain Futures"](https://www.cmegroup.com/education/whitepapers/weather-markets-in-grain-futures.html)
describes the qualitative regime shift. [Cambridge's 2025 *Impact of Fundamentals on
Volatility Measures*](https://www.cambridge.org/core/journals/journal-of-agricultural-and-applied-economics/article/impact-of-fundamentals-on-volatility-measures-of-agricultural-substitutes/85476330FE20DF7D437A828046AF7544)
confirms the effect econometrically. The practical implication: $\sigma$ in the Avellaneda–Stoikov
formula must be *time-varying and calendar-indexed*, not estimated from a trailing window.

### 7.2 Mean reversion and the theory of storage

[Kaldor (1939, *Review of Economic Studies*)](https://academic.oup.com/restud/article/7/1/1/1538784)
and [Working (1949, *AER*)](https://www.jstor.org/stable/1828509) founded the *theory of
storage*: the relation between futures and spot prices is governed by the cost of storage
minus a convenience yield, and the forward curve therefore carries information about
inventories. The Kaldor–Working relation,

$$
F_t(T) = S_t\,e^{(r + u - y)(T-t)},
$$

with $r$ the interest rate, $u$ storage cost, and $y$ convenience yield, predicts
*backwardation* ($F < S$) when inventories are scarce and $y$ large, and *contango* when
abundant.

[Deaton and Laroque (1992)](https://www.princeton.edu/~deaton/downloads/On_The_Behaviour_of_Commodity_Prices.pdf)
formalize the dynamics: with a non-negativity constraint on inventory, commodity prices follow
a nonlinear autoregressive process with occasional "stockout" explosions. [Routledge, Seppi,
and Spatt (2000, JoF)](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00248) derive the
full equilibrium forward curve with embedded timing options, showing that the convenience
yield is *endogenous* and a function of inventory state. For a market maker, the implication
is twofold: (i) spot-level mean reversion biases the short-horizon drift term $\mu_t$ in the
quoting formula — the reservation price should incorporate a drift toward a long-run mean when
inventories are extreme — and (ii) forward-curve shape (contango vs. backwardation) provides
a *signal* for the direction of the carry/roll, which dominates inventory-holding cost in
quiet weeks.

### 7.3 Roll-related flows and their microstructure signature

Commodity-index investors (S&P GSCI, Bloomberg Commodity Index) systematically roll long
futures exposure forward. The "Goldman roll" closes 20% of a contract on each of business
days 5–9 of the month preceding expiry and opens the corresponding amount in the next
deferred month. [Yu's CFTC study (2011)](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_33_yu.pdf)
and [Irwin, Sanders and Yan](https://scotthirwin.com/wp-content/uploads/2022/02/Irwin_Sanders_Yan_AEPP_All.pdf)
find a statistically robust *calendar-spread* front-running pattern around these dates, with
estimated cost to index investors of ~3.6% per year across commodities. For soybean market
makers, the roll creates (i) a predictable spread-flow in the front–back calendar, (ii)
transient depth asymmetries at the deferred leg, and (iii) information-free order flow that
should *widen the adverse-selection premium less* than an unscheduled trade of the same size.

### 7.4 Scheduled information events (USDA)

The WASDE, Crop Progress, Grain Stocks, Prospective Plantings, and Crop Production reports
are released on a fixed calendar. [Mosquera et al.'s 2024 *Applied Economics Letters* paper
on WASDE calendar effects](https://www.tandfonline.com/doi/full/10.1080/13504851.2024.2373337)
documents that release days exhibit *distinct diurnal volatility patterns*: volatility is
subdued at the open, eases mid-morning, and spikes immediately after 11:00 a.m. CT before
fading within an hour. [Silveira et al. (2025, *J. Futures Markets*)](https://onlinelibrary.wiley.com/doi/10.1002/fut.22601)
report similar reactions in corn. [Adjemian and co-authors (AJAE, *Are Corn Futures Prices
Getting Jumpy*)](https://onlinelibrary.wiley.com/doi/am-pdf/10.1002/ajae.12030) show that, with
the 2013 shift to in-session release, jump clustering on report days increased sharply.

The implication for a quoting engine is stark: *stationarity assumptions in the HJB fail
periodically and predictably*. Best practice is a regime-switching overlay — pull quotes or
widen the spread by a multiplicative factor $\kappa_t$ for a window around each release,
parameterized from historical jump variance on comparable release dates. The
Cartea–Jaimungal framework accommodates this via a deterministic, time-indexed jump-intensity
$\lambda_t^J$ in the value function, but the *calibration* — which report moves the market
how much — is an empirical question that the academic literature only partly answers.

### 7.5 Overnight session thinness and gap risk

Soybeans trade from Sunday 7:00 p.m. CT through Friday 7:45 a.m. CT with a brief daily
maintenance gap (see Phase 01). Overnight liquidity is a fraction of day-session liquidity —
[StoneX practitioner notes](https://futures.stonex.com/blog/commodity-trading-hours-timing-is-everything)
and CME's contract-specification guides document day-session volumes of roughly 8–10x the
overnight hourly rate. Overnight depth thinness has two consequences. First, Poisson-intensity
assumptions with a *single* $A$ parameter break down: $A$ should be time-of-day and
day-of-week indexed. Second, the $dS_t = \sigma\,dW_t$ model overstates the probability of
small moves overnight and understates the probability of gaps; a mixture of low-variance
diffusion and a heavier-tailed jump component is needed. In practice, most prop market makers
simply widen spreads or withdraw during overnight hours, treating the session as one in which
the GLFT closed-form is *not a quoting policy but a warning signal* about how conservative to
be.

### 7.6 Fat tails and non-Gaussian returns

Beyond seasonality and events, soybean returns exhibit persistent leptokurtosis that no
single-factor GBM captures. Econometric work on grain volatility (see the [MIDAS soybean
volatility paper](https://www.sciencedirect.com/science/article/abs/pii/S1057521923002363))
and the broader literature on [volatility dynamics of agricultural futures](https://www.sciencedirect.com/science/article/pii/S0140988324004626)
consistently find GARCH/Heston-style volatility plus jumps as the minimum viable model. Phase
01 documented the variable-limit rule (soybeans ≥ 50¢/bu initial limit, expanding 50%) which
caps *observed* fat tails via an exchange-imposed truncation; when the market locks limit, the
"true" price move is censored from the book, and any vol estimator fit to observed prices is
downward-biased.

## 8. Practical model deployment: academia vs. practice

The academic literature is dominated by stochastic-control market-making models (Avellaneda–
Stoikov → GLFT → Cartea–Jaimungal). In industry the picture is considerably messier. A survey
across published practitioner material ([Lehalle & Laruelle's *Market Microstructure in
Practice*, 2nd ed.](https://www.worldscientific.com/worldscibooks/10.1142/10739),
public [Optiver](https://www.bloomberg.com/news/features/2025-08-17/optiver-opens-nyc-office-to-challenge-citadel-securities-jane-street)
coverage, and HRT/Jane Street recruitment materials) suggests the following practitioner
stack:

1. **A short-horizon alpha signal.** Essentially always OFI-based (Cont, Kukanov and Stoikov
   style) plus trade-sign imbalance; sometimes augmented with cross-asset lead–lag
   (soybean meal–oil crush, corn–soybean ratio). This is the single most important component
   and has virtually no pure-academic equivalent in Avellaneda–Stoikov.
2. **A reservation-price skew against inventory,** parameterized à la Ho–Stoll / Avellaneda–
   Stoikov, usually with a hard inventory cap as in GLFT and a linear skew coefficient
   calibrated to realized vol.
3. **A spread that is the maximum of a GLFT-style nominal spread and an
   adverse-selection-protection spread** keyed to recent signed trade flow and VPIN-like
   toxicity.
4. **A regime layer** that widens spreads or withdraws quotes around scheduled events
   (WASDE, NFP for equities), overnight, and during identified stress.
5. **Risk-manager-imposed hard limits** (notional inventory, delta, gamma) that supersede the
   optimizer's output and truncate the policy.

The gap between academia and practice is most visible in three places. First, *signals*:
production desks run dozens of alpha signals in the drift term; most academic papers assume
zero drift. Second, *adverse-selection estimation*: practitioners rarely estimate PIN/VPIN and
instead use rolling realized spreads (post-trade mark-out at 1s, 5s, 60s) as the empirical
measure of whether they are being picked off. Third, *event handling*: the Cartea–Jaimungal
framework can accommodate deterministic jumps but the calibration — "how much do I widen on
USDA days?" — is proprietary, varies by desk, and is under-published. Conference talks from
[Optiver at QuantMinds](https://www.ainvest.com/news/optiver-asymmetric-gambit-17b-options-trader-reshaping-york-high-frequency-landscape-2508/)
and from HRT on futures market-making typically discuss the *shape* of their approach without
giving the parameter tables that would let an academic replicate it — a durable practice–theory
gap.

A second gap is *multi-asset hedging*. The commodity market maker quoting ZS can hedge in
real-time with ZC, ZM, ZL, MATIF rapeseed, or the Dalian complex; the Guéant multi-asset
extension gives the theoretical scaffold, but in practice cross-asset intensities are
estimated empirically from trade and quote data, and the optimal hedge ratios are rebalanced
more frequently than any stochastic-control model would prescribe because transaction costs
and basis risk dominate.

## 9. What a pricing model does NOT solve

Pricing models produce a two-sided quote. They do *not* tell the market maker:

- **How to hedge.** Delta, gamma, and crush-spread hedges are a separate optimization layer
  (Phase 03 in this research stack).
- **How much capital to deploy.** Capital allocation across contracts, books, and strategies
  is a portfolio problem that takes quoting P&L as an input rather than solving for it.
- **What the risk limits should be.** Inventory caps, loss-per-day limits, and liquidity
  covenants are exogenous constraints that truncate the quoting policy but are themselves set
  by risk management, not the quoter.
- **When to stop quoting.** The decision to pull quotes around extreme events (locked limits,
  circuit breakers, structural liquidity collapse) is a meta-decision that sits above the
  pricing model.

These are the domains of subsequent phases in this research stack.

---

## Key takeaways

- The canonical market-making pricing models divide cleanly into inventory-based (Ho–Stoll,
  Grossman–Miller), information-based (Glosten–Milgrom, Kyle, PIN/VPIN), and stochastic-control
  (Avellaneda–Stoikov, GLFT, Cartea–Jaimungal) families; the modern synthesis is an HJB
  with an inventory penalty, an intensity function, and optional adverse-selection and
  alpha-signal drifts.
- The Avellaneda–Stoikov reservation-price formula $r = S - q\gamma\sigma^2(T-t)$ and the GLFT
  closed-form spread are the industry skeleton; the Cartea–Jaimungal extensions plug in alpha
  signals, adverse selection, and multi-asset inventory penalties.
- Short-horizon alpha from order-flow imbalance (Cont–Kukanov–Stoikov) is the most important
  practitioner input not captured by the baseline academic formulas.
- Single-factor GBM is fundamentally wrong for soybeans: seasonality, mean reversion from
  storage theory (Kaldor, Working, Deaton–Laroque, Routledge–Seppi–Spatt), index-roll flows,
  scheduled USDA jump events, overnight thinness, and fat tails all violate its assumptions
  in qualitatively different directions.
- The academic/practitioner gap is largest in three places: signals in the drift term,
  empirical mark-out-based adverse-selection measurement, and event-day calibration. Published
  practitioner material gives the shape but rarely the parameters.
- Pricing is necessary but not sufficient: hedging, capital allocation, and risk limits are
  separate problems that consume the pricing model's output as an input.

## References

Academic papers (primary):

1. [Avellaneda, M. & Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance*, 8(3), 217–224.](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf)
2. [Bates, D. (1996). Jumps and stochastic volatility: Exchange rate processes implicit in Deutsche mark options. *Review of Financial Studies*, 9(1), 69–107.](https://academic.oup.com/rfs/article/9/1/69/1583938)
3. [Cartea, Á., Jaimungal, S. & Penalva, J. (2015). *Algorithmic and High-Frequency Trading*. Cambridge University Press.](https://assets.cambridge.org/97811070/91146/frontmatter/9781107091146_frontmatter.pdf)
4. [Cartea, Á., Jaimungal, S. & Ricci, J. (2014). Buy low, sell high: A high-frequency trading perspective. *SIAM Journal on Financial Mathematics*, 5(1), 415–444.](https://epubs.siam.org/doi/10.1137/130911196)
5. [Cartea, Á. & Jaimungal, S. (2015). Risk metrics and fine tuning of high-frequency trading strategies. *Mathematical Finance*, 25(3), 576–611.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2010417)
6. [Cartea, Á. & Wang, Y. (2020). Market making with alpha signals. *International Journal of Theoretical and Applied Finance*.](https://ora.ox.ac.uk/objects/uuid:c2ba6656-8eab-4b2e-a24a-e9e842d1378f/files/s41687h481)
7. [Cont, R. & de Larrard, A. (2013). Price dynamics in a Markovian limit order market. *SIAM Journal on Financial Mathematics*, 4, 1–25.](https://epubs.siam.org/doi/10.1137/110856605)
8. [Cont, R., Kukanov, A. & Stoikov, S. (2014). The price impact of order book events. *Journal of Financial Econometrics*, 12(1), 47–88.](https://academic.oup.com/jfec/article-abstract/12/1/47/816163)
9. [Deaton, A. & Laroque, G. (1992). On the behaviour of commodity prices. *Review of Economic Studies*, 59(1), 1–23.](https://www.princeton.edu/~deaton/downloads/On_The_Behaviour_of_Commodity_Prices.pdf)
10. [Easley, D., Kiefer, N. M., O'Hara, M. & Paperman, J. B. (1996). Liquidity, information, and infrequently traded stocks. *Journal of Finance*, 51(4), 1405–1436.](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb04074.x)
11. [Easley, D., López de Prado, M. & O'Hara, M. (2012). Flow toxicity and liquidity in a high-frequency world. *Review of Financial Studies*, 25(5), 1457–1493.](https://www.quantresearch.org/VPIN.pdf)
12. [Glosten, L. & Milgrom, P. (1985). Bid, ask and transaction prices in a specialist market with heterogeneously informed traders. *Journal of Financial Economics*, 14(1), 71–100.](https://milgrom.people.stanford.edu/wp-content/uploads/1984/09/Bid-Ask-and-Transaction-Prices.pdf)
13. [Grossman, S. J. & Miller, M. H. (1988). Liquidity and market structure. *Journal of Finance*, 43(3), 617–633.](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1988.tb04594.x)
14. [Guéant, O. (2017). Optimal market making. *Applied Mathematical Finance*, 24(2), 112–154.](https://arxiv.org/abs/1605.01862)
15. [Guéant, O., Lehalle, C.-A. & Fernández-Tapia, J. (2013). Dealing with the inventory risk: A solution to the market making problem. *Mathematics and Financial Economics*, 7, 477–507.](https://link.springer.com/article/10.1007/s11579-012-0087-0)
16. [Hasbrouck, J. (1991). Measuring the information content of stock trades. *Journal of Finance*, 46(1), 179–207.](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1991.tb03749.x)
17. [Heston, S. L. (1993). A closed-form solution for options with stochastic volatility with applications to bond and currency options. *Review of Financial Studies*, 6(2), 327–343.](https://academic.oup.com/rfs/article-abstract/6/2/327/1574747)
18. [Ho, T. & Stoll, H. R. (1981). Optimal dealer pricing under transactions and return uncertainty. *Journal of Financial Economics*, 9(1), 47–73.](https://www.sciencedirect.com/science/article/abs/pii/0304405X81900209)
19. [Ho, T. & Stoll, H. R. (1983). The dynamics of dealer markets under competition. *Journal of Finance*, 38(4), 1053–1074.](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1983.tb02282.x)
20. [Huang, W., Lehalle, C.-A. & Rosenbaum, M. (2015). Simulating and analyzing order book data: The queue-reactive model. *Journal of the American Statistical Association*, 110(509), 107–122.](https://arxiv.org/abs/1312.0563)
21. [Kaldor, N. (1939). Speculation and economic stability. *Review of Economic Studies*, 7(1), 1–27.](https://academic.oup.com/restud/article/7/1/1/1538784)
22. [Kyle, A. S. (1985). Continuous auctions and insider trading. *Econometrica*, 53(6), 1315–1336.](https://people.duke.edu/~qc2/BA532/1985%20EMA%20Kyle.pdf)
23. [Merton, R. C. (1976). Option pricing when underlying stock returns are discontinuous. *Journal of Financial Economics*, 3(1–2), 125–144.](https://www.sciencedirect.com/science/article/abs/pii/0304405X76900222)
24. [Routledge, B. R., Seppi, D. J. & Spatt, C. S. (2000). Equilibrium forward curves for commodities. *Journal of Finance*, 55(3), 1297–1338.](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00248)
25. [Stoll, H. R. (1978). The supply of dealer services in securities markets. *Journal of Finance*, 33(4), 1133–1151.](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1978.tb02053.x)
26. [Working, H. (1949). The theory of price of storage. *American Economic Review*, 39(6), 1254–1262.](https://www.jstor.org/stable/1828509)

Commodity-specific empirical and practitioner sources:

27. [Adjemian, M. K. & Irwin, S. H. (2020). Are corn futures prices getting "jumpy"? *American Journal of Agricultural Economics*, 102(2).](https://onlinelibrary.wiley.com/doi/am-pdf/10.1002/ajae.12030)
28. [Andersen, T. G. & Bondarenko, O. (2014). VPIN and the flash crash. *Journal of Financial Markets*, 17, 1–46.](https://www.sciencedirect.com/science/article/abs/pii/S1386418113000189)
29. [CME Group, "Vol Is High by the Fourth of July" (white paper).](https://www.cmegroup.com/articles/whitepapers/vol-is-high-by-the-fourth-of-july.html)
30. [CME Group, "Weather Markets in Grain Futures" (white paper).](https://www.cmegroup.com/education/whitepapers/weather-markets-in-grain-futures.html)
31. [Irwin, S. H., Sanders, D. R. & Yan, L. (2022). The order flow cost of index rolling in commodity futures markets. *Applied Economic Perspectives and Policy*.](https://scotthirwin.com/wp-content/uploads/2022/02/Irwin_Sanders_Yan_AEPP_All.pdf)
32. [Lehalle, C.-A. & Laruelle, S. (2018). *Market Microstructure in Practice* (2nd ed.). World Scientific.](https://www.worldscientific.com/worldscibooks/10.1142/10739)
33. [Mosquera, S., Garcia, P. & Etienne, X. (2024). Exploring calendar effects: The impact of WASDE releases on grain futures market volatility. *Applied Economics Letters*.](https://www.tandfonline.com/doi/full/10.1080/13504851.2024.2373337)
34. [Silveira, R., Mattos, F. et al. (2025). The reaction of corn futures markets to U.S. and Brazilian crop reports. *Journal of Futures Markets*.](https://onlinelibrary.wiley.com/doi/10.1002/fut.22601)
35. [Yu, C. (2011). Limits to arbitrage and commodity index investment: Front-running the Goldman roll. CFTC White Paper.](https://www.cftc.gov/sites/default/files/idc/groups/public/@swaps/documents/file/plstudy_33_yu.pdf)
