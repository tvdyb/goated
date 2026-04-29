# Phase T-60 — WASDE NLP Auto-Parse → Density Updates

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Context
USDA WASDE reports are released monthly (typically 12th of month, noon ET).
They move soybean prices by 10-50c in 30 seconds. The research synthesis
(§3.3) documents historical sensitivity: ~+18c/bu per -1M bushel ending-stocks
surprise. Currently, the settlement gate pulls all orders pre-WASDE. But
post-release, we should re-enter with an updated density.

## Outputs
- `feeds/usda/wasde_parser.py`:
  - Pull WASDE PDF/data from USDA website on release.
  - Extract soybean ending stocks, production, exports.
  - Compare to consensus (from prior WASDE or manually configured).
  - Compute delta vs consensus in million bushels.
- `engine/wasde_density.py`:
  - Convert WASDE delta to mean-shift on density.
  - Sensitivity: ~18c per 1M bushel ending-stocks surprise (configurable).
  - Apply mean-shift to the current RND or synthetic density.
- Updated `deploy/main.py` and `deploy/lip_mode.py`:
  - Post-WASDE (after settlement gate re-opens): use WASDE-adjusted density.
  - Decay the adjustment over 24 hours (market absorbs the information).
- `tests/test_wasde_parser.py` — parse a historical WASDE PDF.

## Data source
- USDA WASDE: `https://usda.library.cornell.edu/concern/publications/3t945q76s`
- Or USDA ERS API: `https://api.ers.usda.gov/` (free, no key needed for WASDE)
- Consensus: manually configured or scraped from free sources.

## Success criteria
- Parser correctly extracts soybean ending stocks from WASDE data.
- Density mean-shift is applied correctly post-release.
- The system re-enters the market faster than manual traders after WASDE.
