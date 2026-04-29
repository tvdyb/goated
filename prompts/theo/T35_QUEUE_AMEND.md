# Phase T-35 — Queue Management via Amend

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- T-15 must show PASS.

## Context
Currently we cancel-and-replace orders when the target price changes. This:
1. Takes us off the book for 1-2 seconds (lost LIP snapshots).
2. Loses queue priority (we go to back of queue at new price).

Kalshi supports order amendment (`PATCH /portfolio/orders/{order_id}`). Amending
preserves queue position when only size changes, and moves to new price with
fresh priority when price changes — but it's one API call instead of two
(cancel + place), halving the off-book time.

## Outputs
- `feeds/kalshi/client.py` — add `amend_order(order_id, *, yes_price, count)` method.
- Updated `deploy/lip_mode.py`:
  - When target price changes: amend instead of cancel + place.
  - When target price is the same: do nothing (already implemented).
  - Track order IDs for amendment.
- `tests/test_amend.py` — test amend flow with mocked API.

## Success criteria
- Price changes use amend (1 API call) instead of cancel + place (2 calls).
- Off-book time reduced by ~50%.
- LIP score should increase measurably (more snapshots with orders on book).
- Fallback to cancel+place if amend endpoint returns error.

## Key notes
- Check if Kalshi supports `PATCH /portfolio/orders/{order_id}` — the friend's
  code references an amend endpoint. If it doesn't exist, this phase is a NO-OP.
- Test on a single strike first before rolling out to all 7.
