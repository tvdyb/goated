# ACT-02 handoff

**Status.** complete

**Files written or edited.**
| Path | Lines added | Lines removed | Purpose |
|---|---|---|---|
| config/commodities.yaml | ~45 | 2 | Replaced soy stub with fully-populated block (cme_symbol, Kalshi block, fees, position cap, event calendar, trading hours, Pyth feed) |
| config/pyth_feeds.yaml | 7 | 0 | Added soy Pyth Hermes feed entry |
| tests/test_soy_config.py | 90 | 0 | New test file validating soy config completeness |
| state/action_02/plan.md | ~50 | 0 | Implementation plan |

**Tests added.**
| Path | Test count | Pass | Fail |
|---|---|---|---|
| tests/test_soy_config.py | 13 | 13 | 0 |

**Gaps closed (with rationale).**
- GAP-100: Closed. The soy block at `config/commodities.yaml` now has all required fields: `cme_symbol: "ZS"`, Kalshi block (`series: "KXSOYBEANW"`, event ticker pattern, bucket grid source, 24/7 trading hours, reference price mode), fee schedule (taker formula + 25% maker), position cap ($25,000 max loss), CBOT trading hours, event calendar (WASDE, Crop Progress, Export Inspections, Grain Stocks), Pyth feed ID, model config, and `stub: true` removed. Registry now loads soy as a configured commodity with a GBMTheo instance.

**Frozen interfaces honoured.** None (no frozen contracts exist yet).

**New interfaces emitted.** None.

**Decisions encountered and resolved.** None. Used working defaults from F3 and Phase 07 research for all parameter values.

**Decisions encountered and deferred.** None. Position cap and Pyth feed ID flagged in config comments as needing verification against live sources (Appendix A and Pyth Hermes respectively) but these are operational verifications, not design decisions.

**Open issues for verifier.**
- Pyth soybean feed ID (`0xbfa30e...`) sourced from Pyth's published registry. Should be spot-checked against live Hermes endpoint before production use.
- Position cap $25,000 is a default assumption; actual per-contract limit requires Appendix A inspection.

**Done-when checklist.**
- [x] `soy` block in `config/commodities.yaml` is fully populated (no `stub: true`)
- [x] `config/pyth_feeds.yaml` has a `soy` entry
- [x] `Registry` loads `soy` as a configured commodity (not stub) — test passes
- [x] All existing tests still pass (63/63)
- [x] No non-negotiable violations introduced

**Resumption notes (if status is mid-flight).** N/A — action is complete.
