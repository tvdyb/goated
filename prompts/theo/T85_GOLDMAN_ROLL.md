# Phase T-85 — Goldman Roll Window Detection

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Context
Research synthesis §3.2: during the Goldman Sachs Commodity Index roll window
(typically 5th-9th business day of the month), predictable index-driven flow
moves the front-month ZS price. When the roll falls inside a Kalshi settlement
window, the density mean should be adjusted for the expected roll-driven drift.

## Outputs
- `engine/goldman_roll.py`:
  - Calendar of Goldman roll windows (5th-9th business day each month).
  - `is_in_roll_window(date) -> bool`
  - `roll_drift_cents(date) -> float` — expected downward pressure during roll
    (typically -2 to -5c from sell pressure on front month).
- Updated density computation: apply roll drift to mean when in window.
- `tests/test_goldman_roll.py`

## Data needed
- Goldman roll schedule: public, deterministic (5th-9th business day).
- No external API needed.

## Success criteria
- Roll window correctly identified for any month.
- Density mean shifts down 2-5c during roll window.
- No effect outside the window.
