# SELF-PROMPT — Full build prompt-stack constructor

**How to use this file.** Open a new Claude Code window in
`~/Documents/GitHub/goated`. Paste **everything between the START
MARKER and END MARKER** below as your first message. The agent will
spend that session building a complete prompt stack at
`prompts/build/`. You then execute those prompts one at a time in
further fresh sessions.

The prompt builder does NOT implement code. It only writes prompt
files. Code implementation happens later, in the per-phase contexts
that consume the prompts the builder produced.

---

## ===== START MARKER =====

You are the prompt-stack-builder for the `goated` project. Your single
job in this session is to produce a complete, robust, ordered set of
prompts at `prompts/build/` that, when executed sequentially in
**fresh context windows**, take the project from its current state
through to a live, paper-trade-validated, asymmetric-market-making
system on Kalshi commodity monthly markets, hedged via Interactive
Brokers.

You will NOT implement code. You will NOT run tests. You will NOT
modify production code. You will produce **prompt files** under
`prompts/build/`. Each prompt file is a self-contained instruction
set for a future agent to execute in its own fresh context.

---

### Step 1 — Establish ground truth by reading these artifacts

Read in this order. Do not skip. Do not summarize from memory.

1. `ONBOARDING.md` — project orientation.
2. `audit/audit_F3_refactor_plan_lip.md` — the F3 plan. *Note:
   superseded in spirit by F4 thinking; see step 2 below.*
3. `audit/audit_F_refactor_plan.md` (F1) — the original audit-aligned
   plan. Read sections 1, 3, 11, 12.
4. `audit/audit_E_gap_register.md` §3 (themes) and §4 (counts).
5. `audit/audit_A_cartography.md` §9 (modules) and §10 (red flags).
6. `state/PROJECT_CONTEXT.md` — current operative state.
7. `state/dependency_graph.md` — what's built and verified.
8. `state/decisions_log.md` — resolved decisions.
9. `state/digest_kalshi_research_2026-04-27.md` — live API findings,
   including the LIP-eligibility result and the half-line market
   structure correction.
10. `state/wave_0_gate.md` — the NO-GO decision and pivot
    recommendation from the orchestrator.
11. `prompts/README.md` — prompt-stack architecture.
12. `prompts/00_BOOT.md` through `prompts/09_WAVE_GATE.md` — the
    existing prompt stack patterns (you will reuse this style).
13. `prompts/SELF_PROMPT_PREMISE.md` — the canonical strategic
    premise (read this last, after establishing the rest of context;
    it is the authoritative statement of what the project is now
    building).
14. `mm-setup-main/README.md` and `mm-setup-main/kalshi_rewards_app.py`
    — the friend's reference code. Note its anti-arb logic and
    reward-formula. We are NOT copying its strategy (that's LIP
    rebate farming, which is excluded under the post-NO-GO pivot).
    But the anti-arb logic, RSA-PSS signing reference, and
    cancel-zero-reward sweeper are useful patterns to port.

After reading: produce a one-paragraph confirmation that you have
loaded each file. If any file is missing, halt and report exactly
which file with the path.

---

### Step 2 — Internalize the strategic pivot (F4)

The project is no longer building toward F3 (LIP-pool-share farming on
soybean weeklies — that strategy is dead because `KXSOYBEANW` is not
LIP-eligible). It is also not building toward F1's pure A-S/CJ
edge-driven framing (overengineered for the actual trade frequency).

**The new operating thesis (F4):**

Asymmetric market-making on Kalshi **commodity monthly** markets,
priced against an empirical risk-neutral density (RND) extracted from
CME options on the underlying futures. Quote two-sided around a
fair-value derived from CME-implied probabilities, not around Kalshi's
midpoint. Withdraw the side facing adverse flow (taker-imbalance
detector) and the entire book during news windows (settlement-gap
gate). Hedge residual delta on CBOT futures via Interactive Brokers
where a futures hedge exists (soy, corn). Run un-hedged on the rest
(nickel, lithium, sugar — no IB-accessible hedge instruments).

**Target series (in order of build priority):**

1. `KXSOYBEANMON` — soy monthly. Hedgeable via ZS futures. Most
   developed CME options chain. First implementation.
2. `KXCORNMON` — corn monthly. Hedgeable via ZC futures. Same shape
   as soy.
3. `KXSUGARMON` — sugar monthly. ICE-EU hedge instrument; not
   IB-accessible by default. Run un-hedged or skip.
4. `KXNICKELMON` — nickel monthly. LME hedge; not accessible. Run
   un-hedged.
5. `KXLITHIUMMON` — lithium monthly. CME has lithium hydroxide
   futures; thin liquidity. Probably un-hedged.

Realistic economic target: **$20-35k/year net side income** across
the 5 series, conditional on the RND model being meaningfully better
than Kalshi's quoted midpoints (the M0 test).

**The settlement-gap risk is the binding constraint.** A USDA WASDE
print can move soybean futures 2% in a minute, vaporizing 42¢ Kalshi
spreads in seconds. Every quoting decision must be conditional on
time-to-settlement and event proximity.

**What's already built (Wave 0, all 16 actions verified-complete):**

ACT-01 (forward-capture tape sentinel), ACT-02 (commodities.yaml fill-in),
ACT-03 (Kalshi REST client + RSA-PSS + rate limiter), ACT-04 (ticker
+ bucket grid + Event puller), ACT-05 (WS multiplex with fills +
orderbook deltas), ACT-06 (order builder + tick rounding +
quote-band), ACT-07 (24/7 calendar + Friday roll), ACT-08 (settle
resolver + roll), ACT-09 (position store), ACT-10 (fee model),
ACT-11 (kill primitives), ACT-12 (risk gates), ACT-13 (corridor
adapter), ACT-LIP-POOL (pool ingest), ACT-LIP-SCORE (score tracker),
ACT-LIP-VIAB (viability framework). Total: ~611 tests passing.

**What's missing for F4:**

- CLAUDE.md for the codebase (Step 3 will produce a prompt to create it)
- M0 spike notebook validating the RND-vs-Kalshi edge hypothesis on
  one settled `KXSOYBEANMON` Event
- CME options chain ingest (ZS first; ZC second)
- BL → SVI → Figlewski RND extractor with arb constraints
- Bucket integrator on Kalshi half-line strike grid
- Asymmetric quoter (only post on the discrepancy side; skip when
  Kalshi mid is in line with model fair)
- Taker-imbalance detector (rolling-window WS `trade` channel
  classifier)
- Settlement-gap risk gate (pre-USDA-window pull-all + size-down
  ladder, wired into kill switch)
- IBKR Gateway + `ib_insync` integration for ZS / ZC hedge leg
- Settlement-gap scenario harness
- Backtest M0 validator (live system scored against settled-week
  outcomes)
- Live PnL attribution per market per hour

Read `prompts/SELF_PROMPT_PREMISE.md` if it exists. If it doesn't, you
will create it as part of Step 3.

---

### Step 3 — Produce the prompt stack

Create the directory `prompts/build/` and produce the following
prompt files. Each prompt must be **self-contained** — it must
include the premise restatement, the file-reading directives, the
success criteria, and the output format. A fresh agent reading any
single prompt should be able to execute that phase without any
external context other than what the prompt cites.

**Numbering convention.** Two-digit phase, with `5x` reserved for
review phases that follow execution phases. So `10` is the M0 spike
execution, `15` is its review; `30` is Wave 0 re-verify, `35` is its
review; etc.

**Required prompt files (15 total):**

| File | Purpose |
|---|---|
| `prompts/build/00_INIT_CLAUDEMD.md` | Create the codebase's `CLAUDE.md` from the audit + Wave-0 state. |
| `prompts/build/05_INIT_F4_PLAN.md` | Produce `audit/audit_F4_refactor_plan_asymmetric_mm.md` formalizing the F4 thesis with action set, dependency graph, kill criteria. |
| `prompts/build/10_RESEARCH_M0_SPIKE.md` | Build a notebook at `research/m0_spike_soy_monthly.ipynb` that validates the RND-vs-Kalshi edge hypothesis on one settled `KXSOYBEANMON` Event. Pure research, no production code. |
| `prompts/build/15_REVIEW_M0_SPIKE.md` | **Review phase.** Independently re-validate the M0 spike's claims against fresh real data. Reject any claim made without numerical evidence. |
| `prompts/build/20_VERIFY_WAVE_0_INTEGRITY.md` | Re-verify every Wave 0 action's `verify.md` is current; re-run pytest; flag drift. |
| `prompts/build/25_REVIEW_WAVE_0.md` | **Review phase.** Independently audit each of the 16 actions against the F1 gap register and the actual code. Validate every gap-closure claim. |
| `prompts/build/30_PLAN_WAVE_1_F4.md` | Produce `state/wave_1_status.md` reflecting the F4 Wave 1 plan, with track assignments. |
| `prompts/build/40_IMPL_CME_INGEST.md` | Implement CME options chain + futures ingest for ZS, ZC. Vendor: free EOD from cmegroup.com or low-cost API. |
| `prompts/build/45_REVIEW_CME_INGEST.md` | **Review phase.** Validate ingested data against direct CME source. Check arb constraints (call vs put parity). |
| `prompts/build/50_IMPL_RND_PIPELINE.md` | Implement BL → SVI calibration → arb constraints → Figlewski tails → bucket integrator. |
| `prompts/build/55_REVIEW_RND_PIPELINE.md` | **Review phase.** Score the RND on N settled weeks. Compare to Kalshi midpoints. Quantify edge. |
| `prompts/build/60_IMPL_ASYMMETRIC_QUOTER.md` | Implement asymmetric quoter + taker-imbalance detector + settlement-gap gate. |
| `prompts/build/65_REVIEW_QUOTER.md` | **Review phase.** Paper-trade the quoter on `demo-api.kalshi.co` for ≥7 days. Validate it doesn't blow up risk gates. |
| `prompts/build/70_IMPL_IBKR_HEDGE.md` | Implement IBKR Gateway + `ib_insync` hedge leg for ZS / ZC. |
| `prompts/build/75_REVIEW_IBKR_HEDGE.md` | **Review phase.** Paper-trade a complete round-trip (Kalshi fill → IB hedge → settlement → unwind). Validate slippage and timing. |
| `prompts/build/80_LIVE_SMALL_DEPLOYMENT.md` | Final integration. Wire everything together. Begin live with capital cap of $1k for first 2 weeks. |
| `prompts/build/85_REVIEW_LIVE.md` | **Review phase.** PnL attribution after first 2 weeks live. Decide: scale up, hold, or shut down based on KC criteria. |
| `prompts/build/90_OPERATIONAL_CADENCE.md` | Define ongoing review cadence (weekly PnL review, monthly model recalibration, quarterly strategy reassessment). |

In addition to the build prompts, create these reference files in the
same directory:

- `prompts/build/README.md` — table of contents, execution order,
  per-phase prerequisites.
- `prompts/build/PREMISE.md` — the canonical F4 strategic premise.
  Every build prompt must read this on entry.
- `prompts/build/REVIEW_DISCIPLINE.md` — the discipline that all
  `*_REVIEW_*.md` prompts must enforce. See "Review-phase
  discipline" below.

---

### Step 4 — Review-phase discipline (CRITICAL)

The review phases are the project's defense against agent hallucination,
memory-based reasoning, and unvalidated optimism. They must enforce
extreme rigor. Every review prompt you produce must include the
following operating principles **verbatim**:

```
REVIEW-PHASE DISCIPLINE — DO NOT VIOLATE

You are reviewing work done in a prior context. You did not produce
this work. You have NO MEMORY of what was intended; only what was
written.

ABSOLUTE RULES:

1. DO NOT trust any numerical claim. Every number cited in handoffs,
   reports, or commit messages must be re-derived from the underlying
   data. If the claim is "we passed 611 tests," you re-run pytest.
   If the claim is "soy monthly has 33 trades/7d," you pull
   /trade-api/v2/markets/trades and count.

2. DO NOT use your training-data knowledge of Kalshi, CME, IBKR, or
   any market when validating live numbers. Pull from APIs. If the
   API is unreachable, fail the review.

3. DO NOT accept hand-waved completeness. If a handoff claims "all
   gaps closed," you read each gap row in audit_E_gap_register.md
   and check the cited code location, line by line, against the
   current state of the file.

4. DO NOT skip tests. If a phase claims "tests pass," you run them.
   If they fail, the phase fails review regardless of what was
   reported.

5. DO NOT extrapolate. If the spike validates RND-vs-Kalshi edge on
   1 Event, do not conclude the strategy works on 12 Events. Cite
   only what the data supports.

6. DO NOT cite memory of past sessions. Sessions reset. The artifacts
   are the truth. If you don't see it in a file, it doesn't exist.

7. DO surface every disagreement between claim and evidence as a
   FINDING. Specific (file:line), actionable (what to do), severity
   (info / warn / fail).

8. DO require numerical thresholds. "Edge looks good" is not a
   pass criterion. "RND-implied bucket prices were within 3¢ of
   realized outcomes on 8/10 buckets across 1 Event" is.

9. DO produce a verdict: PASS, FAIL, or INCOMPLETE-DATA. Append it
   to the phase's review file. Do not advance to the next phase
   without PASS.

10. DO NOT modify production code. You are an auditor, not an
    implementer. If you find a defect, write a finding, not a fix.
```

Each review prompt should ALSO include:
- The exact list of files to read (the work being reviewed).
- The exact set of API calls / pytest commands / data pulls to run
  for validation.
- The numerical thresholds for PASS / FAIL.
- The append-only output format for the review file.

---

### Step 5 — Per-prompt structure

Every prompt file you produce must follow this skeleton:

```
# Phase NN — <phase name>

## Premise (ALWAYS READ FIRST)
Read prompts/build/PREMISE.md. If it does not exist, halt.

## Prerequisites
- Phase MM (the prior phase) must show PASS in its review file.
- Files that must exist: ...
- Decisions resolved: ...

## Inputs
- (list of files to read, in order)

## Outputs
- (list of files to produce, with paths)
- (list of artifacts: tests, notebooks, code modules)

## Success criteria
- Specific numerical / behavioral targets.

## Step-by-step instructions
(detailed body)

## Handoff
- Update state/PROJECT_CONTEXT.md with phase complete.
- Append entry to state/decisions_log.md if any OD was resolved
  during this phase.
- Write phase digest to state/digest_phase_NN_<name>.md.
```

For review prompts specifically, additionally include:

```
## Review discipline
Read prompts/build/REVIEW_DISCIPLINE.md. Apply every rule.

## Validation procedure
1. Re-read claims from prior phase: <files>
2. Re-pull live data: <API endpoints and parameters>
3. Re-run tests: <commands>
4. For each numerical claim, perform independent calculation: <list>
5. Compute findings: list each specific deviation with severity.

## Verdict
Append PASS / FAIL / INCOMPLETE-DATA to state/review_phase_NN.md
with all findings.
```

---

### Step 6 — Strategic premise file content

When you create `prompts/build/PREMISE.md`, it must contain (at
minimum):

- The F4 thesis (asymmetric MM on commodity monthlies, priced from
  CME-implied RND, hedged on IBKR where possible).
- Target series, in priority order, with each series' hedge
  instrument or `none`.
- The settlement-gap risk as the binding constraint.
- The realistic economic target ($20-35k/year net for a focused
  operation across the 5 series).
- The kill criteria (M0 fails → strategy dead; settlement-gap
  losses exceed gross spread → reconfigure; capital efficiency
  below opportunity cost for 6 months → exit).
- The non-negotiables inherited from `README.md` (no pandas in
  hot path, fail-loud on bad inputs, `numba.njit` on hot-path
  math, `scipy.special.ndtr` not `scipy.stats.norm.cdf`,
  `post_only=True` on every order, never crossing the spread).
- An explicit list of what the project is NOT building: pure LIP
  rebate farming, A-S/CJ optimal control, FIX 4.4, microsecond
  budgets, hot-standby topology, full alpha layer.

---

### Step 7 — Build-prompt README content

`prompts/build/README.md` must contain:

- Execution order: 00 → 05 → 10 → 15 → 20 → 25 → 30 → 40 → 45 → 50 →
  55 → 60 → 65 → 70 → 75 → 80 → 85 → 90.
- Estimated wall-clock per phase.
- A dependency table showing which phases gate which.
- An explicit operator instruction: "Run each phase in a fresh Claude
  Code session. Read its prerequisites. Do not skip review phases."
- A status table the operator updates by hand after each phase
  completes.
- A "What to do if a review phase returns FAIL" section: do not
  proceed; remediate the failed phase; re-run its review; only
  advance on PASS.

---

### Step 8 — Output gate

Before declaring the prompt-stack build complete, verify:

1. All 18 prompt files exist at the specified paths.
2. Each follows the per-prompt structure (Step 5).
3. Each review prompt includes the Review-Phase Discipline verbatim
   (Step 4).
4. `prompts/build/README.md`, `prompts/build/PREMISE.md`, and
   `prompts/build/REVIEW_DISCIPLINE.md` exist.
5. Total prompt-stack file count: 21 (18 phases + 3 reference).

Produce a final summary listing each file produced, its size in
lines, and a one-line description.

If you find that you cannot produce a phase prompt because critical
information is missing (e.g., you cannot specify the M0 spike's API
endpoints because you don't have access to live Kalshi documentation
in the build session), surface this as a HALT condition rather than
guessing. List specifically what's missing.

---

### Constraints during this session

- DO NOT implement any production code. Build prompts only.
- DO NOT run pytest or modify any file outside `prompts/build/`,
  `prompts/SELF_PROMPT_PREMISE.md`, `state/PROJECT_CONTEXT.md`
  (small touchup only).
- DO NOT spawn subagents to "speed things up." Build prompts
  sequentially. Quality matters more than speed in this session.
- DO use Read, Write, Glob, Grep freely on the existing repo.
- DO take however many tokens you need. This session's only job
  is to produce the build stack correctly.

---

### When done

Produce a final message in this exact structure:

```
## Build-stack production complete

**Files produced:** <count>
**Total lines:** <count>

**Manifest:**
- prompts/build/00_INIT_CLAUDEMD.md (<lines>)
- prompts/build/05_INIT_F4_PLAN.md (<lines>)
- ...
- prompts/build/README.md (<lines>)
- prompts/build/PREMISE.md (<lines>)
- prompts/build/REVIEW_DISCIPLINE.md (<lines>)

**Operator's first move:**
1. Open a fresh Claude Code session in this repo.
2. Paste the contents of prompts/build/00_INIT_CLAUDEMD.md as the
   first message.
3. Wait for that session to complete the CLAUDE.md.
4. Open a new fresh session.
5. Paste prompts/build/05_INIT_F4_PLAN.md.
6. Repeat through all 18 phases.

**Outstanding warnings:** <list anything that came up during
build that the operator should be aware of, or "none">
```

---

## ===== END MARKER =====

---

## Operator notes (do NOT include in the pasted prompt)

After the prompt-builder session completes, you'll have a
`prompts/build/` directory ready to drive ~18 fresh sessions
sequentially. Each session is small and focused. Review sessions
specifically should be run on a fresh model context with no prior
conversation — the whole point is independent eyes.

Expected total wall-clock for end-to-end execution: 4-8 weeks,
depending on (a) how long the IBKR account approval takes (you said
asap), (b) whether each review phase passes first-try, (c) whether
M0 spike validates edge or returns no-go.

The two most important phases for the project's economic premise:

- **Phase 10 / 15** (M0 spike + review): if the M0 spike returns
  no-edge, the entire F4 thesis dies. Stop work. Reconsider.
- **Phase 80 / 85** (live small + review): the actual proof of
  whether $20-35k/year is real. Two weeks live with $1k capital cap
  is the test.

Everything else is plumbing.

---

## Why this works across context windows

Each build prompt is self-contained. Each review prompt is
adversarial to the work being reviewed (different agent, different
context, validates from data). The premise file is the durable
anchor. The state files (`PROJECT_CONTEXT.md`, `decisions_log.md`,
`dependency_graph.md`, `digest_*.md`) carry working memory between
sessions.

If a session blows up mid-phase (context cap, fatal error), the
next session reads the in-progress phase's partial output plus
`prompts/04_HANDOFF.md`-style continuation and resumes. The
artifacts are the state.

The review phases are the project's immune system. They exist
specifically to catch agents that confidently assert untrue things
based on training data or sloppy intermediate reasoning. Their
discipline is non-negotiable: no claim without evidence, no
extrapolation, no skipping tests.
